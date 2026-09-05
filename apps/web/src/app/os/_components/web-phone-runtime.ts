"use client";

import type { Call, Device } from "@twilio/voice-sdk";

export type WebPhoneAudioLinkState =
  | "idle"
  | "requesting_microphone"
  | "ready"
  | "incoming_ringing"
  | "connecting"
  | "audio_established"
  | "reconnecting"
  | "ended"
  | "error";

export type WebPhoneMicrophoneState =
  | "unchecked"
  | "requesting"
  | "granted"
  | "denied"
  | "unsupported"
  | "error";

export type WebPhoneStatus = {
  audioLink: WebPhoneAudioLinkState;
  callActive: boolean;
  incomingRegistration: "disabled" | "registering" | "ready" | "error";
  microphone: WebPhoneMicrophoneState;
  muted: boolean;
  message: string | null;
};

export type WebPhoneCallbacks = {
  onIncomingCall?: (call: IncomingWebPhoneCall) => void;
  onStatus: (status: WebPhoneStatus) => void;
  onTokenWillExpire: () => void | Promise<void>;
};

export type IncomingWebPhoneCall = {
  callId: string;
  callerName: string;
  callerNumber: string | null;
  contextHref: string | null;
  lineLabel: string | null;
  lineNumber: string | null;
};

export type WebPhoneDependencies = {
  loadVoiceSdk?: () => Promise<typeof import("@twilio/voice-sdk")>;
  requestMicrophone?: () => Promise<MediaStream>;
};

type ConnectResult = {
  call: Call;
};

export const INITIAL_WEB_PHONE_STATUS: WebPhoneStatus = {
  audioLink: "idle",
  callActive: false,
  incomingRegistration: "disabled",
  microphone: "unchecked",
  muted: false,
  message: null,
};

export class WebPhoneCancelledError extends Error {
  constructor(message = "Browser audio initialization was cancelled.") {
    super(message);
    this.name = "WebPhoneCancelledError";
  }
}

let activeRuntimeOwner: symbol | null = null;

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "The browser calling connection failed.";
}

/**
 * Client-only boundary around Twilio's browser SDK.
 *
 * The runtime SDK is imported only after an operator explicitly initializes a
 * headset. Voice JWTs remain inside the Device instance and are never written
 * to browser storage, URLs, logs, or rendered state.
 */
export class WebPhoneRuntime {
  private callbacks: WebPhoneCallbacks;
  private call: Call | null = null;
  private connectPromise: Promise<ConnectResult> | null = null;
  private crossTabLockRelease: (() => void) | null = null;
  private acquiringOwnership = false;
  private device: Device | null = null;
  private generation = 0;
  private initializePromise: Promise<void> | null = null;
  private incomingCall: Call | null = null;
  private latestToken = "";
  private localDisconnectRequested = false;
  private loadVoiceSdk: () => Promise<typeof import("@twilio/voice-sdk")>;
  private microphoneSupported: boolean;
  private owner = Symbol("stonegate-web-phone");
  private requestMicrophone: () => Promise<MediaStream>;
  private status: WebPhoneStatus = INITIAL_WEB_PHONE_STATUS;

  constructor(callbacks: WebPhoneCallbacks, dependencies: WebPhoneDependencies = {}) {
    this.callbacks = callbacks;
    this.loadVoiceSdk = dependencies.loadVoiceSdk ?? (() => import("@twilio/voice-sdk"));
    this.microphoneSupported = Boolean(
      dependencies.requestMicrophone ?? navigator.mediaDevices?.getUserMedia,
    );
    this.requestMicrophone =
      dependencies.requestMicrophone ?? (() => navigator.mediaDevices.getUserMedia({ audio: true }));
  }

  get currentStatus() {
    return this.status;
  }

  get hasLiveAudio() {
    return Boolean(this.call || this.connectPromise) && !["ended", "error"].includes(this.status.audioLink);
  }

  private publish(update: Partial<WebPhoneStatus>) {
    this.status = { ...this.status, ...update };
    this.callbacks.onStatus(this.status);
  }

  private releaseCallOwnership() {
    if (activeRuntimeOwner === this.owner) activeRuntimeOwner = null;
    this.crossTabLockRelease?.();
    this.crossTabLockRelease = null;
  }

  private acquireCallOwnership(): Promise<void> | null {
    if (activeRuntimeOwner && activeRuntimeOwner !== this.owner) {
      throw new Error("Only one browser call can be active at a time.");
    }
    if (typeof window === "undefined" || typeof navigator === "undefined" || !navigator.locks) {
      activeRuntimeOwner = this.owner;
      return null;
    }

    return (async () => {
      let reportAvailability: (available: boolean) => void = () => undefined;
      const availability = new Promise<boolean>((resolve) => {
        reportAvailability = resolve;
      });
      void navigator.locks
        .request("stonegate:browser-phone:active-call", { ifAvailable: true }, async (lock) => {
          if (!lock) {
            reportAvailability(false);
            return;
          }
          await new Promise<void>((resolve) => {
            this.crossTabLockRelease = resolve;
            activeRuntimeOwner = this.owner;
            reportAvailability(true);
          });
        })
        .catch(() => reportAvailability(false));
      if (!(await availability)) {
        throw new Error("Another Stonegate tab already has an active browser call.");
      }
    })();
  }

  reserveCallOwnership(): Promise<void> | null {
    if (
      this.call ||
      this.connectPromise ||
      this.acquiringOwnership ||
      (activeRuntimeOwner && activeRuntimeOwner !== this.owner)
    ) {
      throw new Error("Only one browser call can be active at a time.");
    }
    if (activeRuntimeOwner === this.owner) return null;

    this.acquiringOwnership = true;
    try {
      const ownership = this.acquireCallOwnership();
      if (!ownership) {
        this.acquiringOwnership = false;
        return null;
      }
      return ownership.finally(() => {
        this.acquiringOwnership = false;
      });
    } catch (error) {
      this.acquiringOwnership = false;
      throw error;
    }
  }

  releaseCallReservation(): void {
    if (this.call || this.connectPromise) return;
    this.releaseCallOwnership();
  }

  async initialize(token: string): Promise<void> {
    this.latestToken = token;
    if (this.device) {
      this.device.updateToken(token);
      this.latestToken = "";
      this.publish({ message: null });
      return;
    }

    if (this.initializePromise) return this.initializePromise;
    const generation = this.generation;
    this.initializePromise = this.initializeDevice(generation)
      .catch((error) => {
        if (generation === this.generation) this.latestToken = "";
        throw error;
      })
      .finally(() => {
        this.initializePromise = null;
      });
    return this.initializePromise;
  }

  private async initializeDevice(generation: number): Promise<void> {
    if (!this.microphoneSupported) {
      this.publish({
        audioLink: "error",
        microphone: "unsupported",
        message: "This browser cannot access a microphone.",
      });
      throw new Error("This browser cannot access a microphone.");
    }

    this.publish({
      audioLink: "requesting_microphone",
      microphone: "requesting",
      message: "Waiting for microphone permission.",
    });

    try {
      const stream = await this.requestMicrophone();
      stream.getTracks().forEach((track) => track.stop());
      if (generation !== this.generation) throw new Error("Headset initialization was cancelled.");
      this.publish({ microphone: "granted", message: null });
    } catch (error) {
      if (generation !== this.generation) throw error;
      const denied = error instanceof DOMException && error.name === "NotAllowedError";
      this.publish({
        audioLink: "error",
        microphone: denied ? "denied" : "error",
        message: denied
          ? "Microphone access is blocked. Allow it in your browser, then retry."
          : errorMessage(error),
      });
      throw error;
    }

    const { Device: TwilioDevice } = await this.loadVoiceSdk();
    if (generation !== this.generation) throw new WebPhoneCancelledError();
    if (!TwilioDevice.isSupported) {
      this.publish({
        audioLink: "error",
        microphone: "unsupported",
        message: "Browser calling is not supported on this device.",
      });
      throw new Error("Browser calling is not supported on this device.");
    }

    const device = new TwilioDevice(this.latestToken, {
      closeProtection: "A Stonegate call is active. Leave this page and end the audio?",
      enableImprovedSignalingErrorPrecision: true,
      logLevel: "error",
      maxCallSignalingTimeoutMs: 30_000,
      tokenRefreshMs: 60_000,
    });
    device.on("error", (error: unknown) => {
      if (generation !== this.generation || this.device !== device) return;
      this.publish({
        audioLink: this.call ? this.status.audioLink : "error",
        message: errorMessage(error),
      });
    });
    device.on("registered", () => {
      if (generation !== this.generation || this.device !== device) return;
      this.publish({ incomingRegistration: "ready", message: null });
    });
    device.on("unregistered", () => {
      if (generation !== this.generation || this.device !== device) return;
      this.publish({ incomingRegistration: "disabled" });
    });
    device.on("incoming", (call: Call) => {
      if (generation !== this.generation || this.device !== device) {
        call.ignore();
        return;
      }
      void this.captureIncomingCall(call, generation);
    });
    device.on("tokenWillExpire", () => {
      if (generation !== this.generation || this.device !== device) return;
      void this.callbacks.onTokenWillExpire();
    });
    if (generation !== this.generation) {
      device.destroy();
      throw new Error("Headset initialization was cancelled.");
    }
    this.device = device;
    this.latestToken = "";
    this.publish({ audioLink: "ready", message: null });
  }

  updateToken(token: string) {
    if (!this.device) throw new Error("The browser headset is not initialized.");
    this.device.updateToken(token);
  }

  async registerIncomingCalls(): Promise<void> {
    const device = this.device;
    if (!device) throw new Error("Initialize the browser headset before receiving calls.");
    if (this.status.incomingRegistration === "ready") return;
    this.publish({ incomingRegistration: "registering", message: null });
    try {
      await device.register();
      this.publish({ incomingRegistration: "ready", message: null });
    } catch (error) {
      this.publish({ incomingRegistration: "error", message: errorMessage(error) });
      throw error;
    }
  }

  async unregisterIncomingCalls(): Promise<void> {
    if (this.hasLiveAudio) {
      throw new Error("Finish the current call before turning off incoming browser calls.");
    }
    const device = this.device;
    if (!device || this.status.incomingRegistration === "disabled") return;
    await device.unregister();
    this.publish({ incomingRegistration: "disabled", message: null });
  }

  async connect(callIntentId: string): Promise<ConnectResult> {
    const device = this.device;
    if (!device) throw new Error("Initialize the browser headset before calling.");
    const generation = this.generation;
    if (
      this.call ||
      this.connectPromise ||
      this.acquiringOwnership ||
      (activeRuntimeOwner && activeRuntimeOwner !== this.owner)
    ) {
      throw new Error("Only one browser call can be active at a time.");
    }

    const reservation = this.reserveCallOwnership();
    if (reservation) await reservation;
    if (generation !== this.generation) {
      this.releaseCallOwnership();
      throw new WebPhoneCancelledError();
    }
    this.publish({ audioLink: "connecting", callActive: true, muted: false, message: null });
    this.localDisconnectRequested = false;
    const connectPromise = (async () => {
      const call = await device.connect({ params: { CallIntentId: callIntentId } });
      if (generation !== this.generation) {
        call.disconnect();
        throw new WebPhoneCancelledError();
      }
      this.call = call;
      this.bindCallEvents(call);
      return { call };
    })();
    this.connectPromise = connectPromise;
    try {
      return await connectPromise;
    } catch (error) {
      if (generation !== this.generation) throw new WebPhoneCancelledError();
      this.call = null;
      this.releaseCallOwnership();
      this.publish({ audioLink: "error", callActive: false, message: errorMessage(error) });
      throw error;
    } finally {
      if (this.connectPromise === connectPromise) this.connectPromise = null;
    }
  }

  setMuted(muted: boolean) {
    if (!this.call) throw new Error("There is no active browser audio connection.");
    this.call.mute(muted);
    this.publish({ muted });
  }

  acceptIncomingCall() {
    const call = this.incomingCall;
    if (!call || this.call !== call || this.status.audioLink !== "incoming_ringing") {
      throw new Error("There is no incoming browser call to answer.");
    }
    this.incomingCall = null;
    this.localDisconnectRequested = false;
    this.publish({ audioLink: "connecting", callActive: true, message: "Connecting the caller." });
    call.accept();
  }

  declineIncomingCall() {
    const call = this.incomingCall;
    if (!call || this.call !== call) return;
    this.incomingCall = null;
    this.call = null;
    this.releaseCallOwnership();
    // Ignore closes only this browser leg. Twilio can continue ringing the
    // other registered browsers and screened cellphones in the shared Dial.
    call.ignore();
    this.publish({
      audioLink: "ended",
      callActive: false,
      muted: false,
      message: "Incoming call declined. The caller can continue to another Stonegate phone.",
    });
  }

  sendDigits(digits: string) {
    if (!this.call || this.status.audioLink !== "audio_established") {
      throw new Error("Wait for browser audio to connect before using the keypad.");
    }
    if (!/^[0-9*#]+$/.test(digits)) {
      throw new Error("The browser keypad received an unsupported tone.");
    }
    this.call.sendDigits(digits);
  }

  disconnectLocalAudio() {
    if (this.call) {
      if (this.incomingCall === this.call) {
        this.declineIncomingCall();
        return;
      }
      this.localDisconnectRequested = true;
      this.call.disconnect();
      return;
    }
    if (!this.connectPromise) return;

    this.generation += 1;
    this.connectPromise = null;
    this.device?.destroy();
    this.device = null;
    this.latestToken = "";
    this.releaseCallOwnership();
    this.publish({
      audioLink: "ended",
      callActive: false,
      incomingRegistration: "disabled",
      muted: false,
      message: "Call ended by you.",
    });
  }

  resetAfterCall() {
    if (this.hasLiveAudio) throw new Error("Finish the current call before clearing it.");
    this.incomingCall = null;
    this.localDisconnectRequested = false;
    this.publish({
      audioLink: this.device ? "ready" : "idle",
      callActive: false,
      muted: false,
      message: null,
    });
  }

  destroy() {
    this.generation += 1;
    if (this.incomingCall) this.incomingCall.ignore();
    else this.call?.disconnect();
    this.call = null;
    this.incomingCall = null;
    this.device?.destroy();
    this.device = null;
    this.latestToken = "";
    this.releaseCallOwnership();
    this.status = INITIAL_WEB_PHONE_STATUS;
    this.callbacks.onStatus(this.status);
  }

  private bindCallEvents(call: Call) {
    // SDK events describe the browser/Twilio audio root only. Recipient answer
    // and connection truth always comes from the server-side dial-leg snapshot.
    const publishForCurrentCall = (update: Partial<WebPhoneStatus>) => {
      if (this.call === call) this.publish(update);
    };
    const activeQualityWarnings = new Set<string>();
    call.on("ringing", () => publishForCurrentCall({ audioLink: "connecting", message: null }));
    call.on("accept", () =>
      publishForCurrentCall({
        audioLink: "audio_established",
        message: "Browser audio established.",
      }),
    );
    call.on("reconnecting", () =>
      publishForCurrentCall({
        audioLink: "reconnecting",
        message: "Browser audio is reconnecting.",
      }),
    );
    call.on("reconnected", () =>
      publishForCurrentCall({
        audioLink: "audio_established",
        message: "Browser audio restored.",
      }),
    );
    call.on("mute", (muted: boolean) => publishForCurrentCall({ muted }));
    call.on("warning", (name: string) => {
      activeQualityWarnings.add(name);
      publishForCurrentCall({
        message: "Call quality is degraded. Check your internet connection or headset.",
      });
    });
    call.on("warning-cleared", (name: string) => {
      activeQualityWarnings.delete(name);
      publishForCurrentCall({
        message:
          activeQualityWarnings.size === 0
            ? "Call quality restored."
            : "Call quality is degraded. Check your internet connection or headset.",
      });
    });
    call.on("error", (error: unknown) => {
      if (this.call !== call) return;
      this.call = null;
      this.incomingCall = null;
      this.localDisconnectRequested = false;
      this.releaseCallOwnership();
      this.publish({
        audioLink: "error",
        callActive: false,
        message: errorMessage(error),
      });
    });
    for (const event of ["cancel", "disconnect", "reject"] as const) {
      call.on(event, () => {
        if (this.call !== call) return;
        const wasIncomingRinging = this.incomingCall === call;
        const endedLocally = this.localDisconnectRequested;
        this.call = null;
        this.incomingCall = null;
        this.localDisconnectRequested = false;
        this.releaseCallOwnership();
        this.publish({
          audioLink: "ended",
          callActive: false,
          muted: false,
          message:
            event === "cancel" && wasIncomingRinging
              ? "Incoming call ended or was answered on another Stonegate phone."
              : event === "reject"
                ? "Incoming call declined."
                : endedLocally
                  ? "Call ended by you."
                  : "Call ended.",
        });
      });
    }
  }

  private async captureIncomingCall(call: Call, generation: number) {
    if (this.call || this.connectPromise || this.incomingCall) {
      call.ignore();
      return;
    }
    try {
      const reservation = this.reserveCallOwnership();
      if (reservation) await reservation;
      if (generation !== this.generation || this.device === null) {
        this.releaseCallOwnership();
        call.ignore();
        return;
      }
      this.call = call;
      this.incomingCall = call;
      this.bindCallEvents(call);
      const callerNumber = call.customParameters.get("CallerNumber") ?? call.parameters.From ?? null;
      const callerName = call.customParameters.get("CallerName") ?? callerNumber ?? "Incoming caller";
      this.callbacks.onIncomingCall?.({
        callId: call.customParameters.get("StonegateCallId") ?? call.parameters.CallSid ?? "incoming",
        callerName,
        callerNumber,
        contextHref: call.customParameters.get("ContextHref") ?? null,
        lineLabel: call.customParameters.get("LineLabel") ?? null,
        lineNumber: call.customParameters.get("LineNumber") ?? null,
      });
      this.publish({
        audioLink: "incoming_ringing",
        callActive: true,
        muted: false,
        message: "Incoming Stonegate call.",
      });
    } catch {
      this.releaseCallOwnership();
      call.ignore();
    }
  }
}
