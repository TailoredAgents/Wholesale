"use client";

import type { Call, Device } from "@twilio/voice-sdk";

export type ProspectingAudioLinkState =
  | "idle"
  | "requesting_microphone"
  | "ready"
  | "connecting"
  | "audio_established"
  | "reconnecting"
  | "ended"
  | "error";

export type ProspectingMicrophoneState =
  | "unchecked"
  | "requesting"
  | "granted"
  | "denied"
  | "unsupported"
  | "error";

export type ProspectingSoftphoneStatus = {
  audioLink: ProspectingAudioLinkState;
  microphone: ProspectingMicrophoneState;
  muted: boolean;
  message: string | null;
};

type SoftphoneCallbacks = {
  onStatus: (status: ProspectingSoftphoneStatus) => void;
  onTokenWillExpire: () => void | Promise<void>;
};

type SoftphoneDependencies = {
  loadVoiceSdk?: () => Promise<typeof import("@twilio/voice-sdk")>;
  requestMicrophone?: () => Promise<MediaStream>;
};

type ConnectResult = {
  call: Call;
};

const INITIAL_STATUS: ProspectingSoftphoneStatus = {
  audioLink: "idle",
  microphone: "unchecked",
  muted: false,
  message: null,
};

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "The browser calling connection failed.";
}

/**
 * Client-only boundary around Twilio's browser SDK.
 *
 * The runtime SDK is imported only after an operator explicitly initializes the
 * headset. Voice JWTs stay inside the Device instance and are never written to
 * browser storage, URLs, logs, or rendered state.
 */
export class ProspectingSoftphone {
  private callbacks: SoftphoneCallbacks;
  private call: Call | null = null;
  private connectPromise: Promise<ConnectResult> | null = null;
  private device: Device | null = null;
  private generation = 0;
  private initializePromise: Promise<void> | null = null;
  private latestToken = "";
  private loadVoiceSdk: () => Promise<typeof import("@twilio/voice-sdk")>;
  private microphoneSupported: boolean;
  private requestMicrophone: () => Promise<MediaStream>;
  private status: ProspectingSoftphoneStatus = INITIAL_STATUS;

  constructor(callbacks: SoftphoneCallbacks, dependencies: SoftphoneDependencies = {}) {
    this.callbacks = callbacks;
    this.loadVoiceSdk = dependencies.loadVoiceSdk ?? (() => import("@twilio/voice-sdk"));
    this.microphoneSupported = Boolean(
      dependencies.requestMicrophone ?? navigator.mediaDevices?.getUserMedia,
    );
    this.requestMicrophone = dependencies.requestMicrophone ?? (() =>
      navigator.mediaDevices.getUserMedia({ audio: true })
    );
  }

  get currentStatus() {
    return this.status;
  }

  get hasLiveAudio() {
    return Boolean(this.call) && !["ended", "error"].includes(this.status.audioLink);
  }

  private publish(update: Partial<ProspectingSoftphoneStatus>) {
    this.status = { ...this.status, ...update };
    this.callbacks.onStatus(this.status);
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

  async connect(callIntentId: string): Promise<ConnectResult> {
    const device = this.device;
    if (!device) throw new Error("Initialize the browser headset before calling.");
    if (this.call || this.connectPromise) {
      throw new Error("Only one browser call can be active at a time.");
    }

    this.publish({ audioLink: "connecting", muted: false, message: null });
    const generation = this.generation;
    const connectPromise = (async () => {
      const call = await device.connect({ params: { CallIntentId: callIntentId } });
      if (generation !== this.generation) {
        call.disconnect();
        throw new Error("Browser audio initialization was cancelled.");
      }
      this.call = call;
      this.bindCallEvents(call);
      return { call };
    })();
    this.connectPromise = connectPromise;
    try {
      return await connectPromise;
    } catch (error) {
      if (generation !== this.generation) throw error;
      this.call = null;
      this.publish({ audioLink: "error", message: errorMessage(error) });
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

  disconnectLocalAudio() {
    this.call?.disconnect();
  }

  destroy() {
    this.generation += 1;
    this.call?.disconnect();
    this.call = null;
    this.device?.destroy();
    this.device = null;
    this.latestToken = "";
    this.status = INITIAL_STATUS;
    this.callbacks.onStatus(this.status);
  }

  private bindCallEvents(call: Call) {
    // SDK events describe the browser/Twilio audio root only. Seller answer and
    // connection truth always comes from the server-side dial-leg snapshot.
    const publishForCurrentCall = (update: Partial<ProspectingSoftphoneStatus>) => {
      if (this.call === call) this.publish(update);
    };
    call.on("ringing", () => publishForCurrentCall({ audioLink: "connecting", message: null }));
    call.on("accept", () =>
      publishForCurrentCall({ audioLink: "audio_established", message: "Browser audio established." }),
    );
    call.on("reconnecting", () =>
      publishForCurrentCall({ audioLink: "reconnecting", message: "Browser audio is reconnecting." }),
    );
    call.on("reconnected", () =>
      publishForCurrentCall({ audioLink: "audio_established", message: "Browser audio restored." }),
    );
    call.on("mute", (muted: boolean) => publishForCurrentCall({ muted }));
    call.on("error", (error: unknown) => {
      if (this.call !== call) return;
      this.call = null;
      this.publish({ audioLink: "error", message: errorMessage(error) });
    });
    for (const event of ["cancel", "disconnect", "reject"] as const) {
      call.on(event, () => {
        if (this.call !== call) return;
        this.call = null;
        this.publish({ audioLink: "ended", muted: false, message: "Browser audio ended." });
      });
    }
  }
}
