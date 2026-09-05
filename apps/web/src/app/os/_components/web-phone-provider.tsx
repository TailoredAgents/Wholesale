"use client";

import { useAuth } from "@clerk/nextjs";
import {
  ExternalLink,
  Grid3x3,
  Mic,
  MicOff,
  Phone,
  PhoneIncoming,
  PhoneOff,
  X,
} from "lucide-react";
import Link from "next/link";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  INITIAL_WEB_PHONE_STATUS,
  WebPhoneCancelledError,
  WebPhoneRuntime,
  type WebPhoneStatus,
} from "./web-phone-runtime";
import styles from "./web-phone.module.css";

type VoiceLine = {
  id: string;
  phone_number: string;
  label: string;
  department_key: string;
};

type RawVoiceSession = {
  can_initialize: boolean;
  identity: string;
  token: string | null;
  expires_at: string | null;
  line: VoiceLine | null;
  recording_enabled: boolean;
  blockers: string[];
};

export type WebPhoneSession = Omit<RawVoiceSession, "token">;

export type WebPhoneCallTarget = {
  callIntentId: string;
  direction?: "inbound" | "outbound";
  displayName: string;
  phoneNumber?: string | null;
  fromNumber?: string | null;
  fromLabel?: string | null;
  contextLabel?: string | null;
  contextHref?: string | null;
};

export type ActiveWebPhoneCall = WebPhoneCallTarget & {
  requestedAt: number;
  audioEstablishedAt: number | null;
};

type WebPhoneContextValue = {
  acceptIncomingCall: () => void;
  activeCall: ActiveWebPhoneCall | null;
  busy: boolean;
  disableIncomingCalls: () => Promise<void>;
  enableIncomingCalls: () => Promise<void>;
  hangUp: () => void;
  incomingEnabled: boolean;
  initializeHeadset: () => Promise<void>;
  prepareAndStartCall: (
    prepareTarget: () => Promise<WebPhoneCallTarget>,
  ) => Promise<void>;
  rejectIncomingCall: () => void;
  reset: () => void;
  sendDigits: (digits: string) => void;
  session: WebPhoneSession | null;
  startCall: (target: WebPhoneCallTarget) => Promise<void>;
  status: WebPhoneStatus;
  toggleMute: () => void;
};

type VoiceCallStatus = {
  status: string;
  terminal: boolean;
};

const WebPhoneContext = createContext<WebPhoneContextValue | null>(null);
const dtmfKeys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"];

function detailMessage(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) return fallback;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) =>
        item && typeof item === "object" && "msg" in item
          ? String((item as { msg?: unknown }).msg ?? "")
          : "",
      )
      .filter(Boolean);
    if (messages.length) return messages.join(" ");
  }
  return fallback;
}

function safeSession(session: RawVoiceSession): WebPhoneSession {
  return {
    blockers: session.blockers,
    can_initialize: session.can_initialize,
    expires_at: session.expires_at,
    identity: session.identity,
    line: session.line,
    recording_enabled: session.recording_enabled,
  };
}

function audioStateLabel(status: WebPhoneStatus) {
  const labels: Record<WebPhoneStatus["audioLink"], string> = {
    idle: "Headset idle",
    requesting_microphone: "Waiting for microphone",
    ready: "Headset ready",
    incoming_ringing: "Incoming call",
    connecting: "Connecting browser call",
    audio_established: "Browser audio connected",
    reconnecting: "Reconnecting browser audio",
    ended: "Call ended",
    error: "Browser call needs attention",
  };
  return labels[status.audioLink];
}

function completedCallMessage(status: string) {
  const messages: Record<string, string> = {
    busy: "The recipient's line was busy.",
    canceled: "The call was canceled before it connected.",
    completed: "Call completed.",
    failed: "The phone network could not complete the call.",
    "no-answer": "The recipient did not answer.",
  };
  return messages[status] ?? "Call ended.";
}

function elapsedLabel(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

export function WebPhoneProvider({ children }: { children: ReactNode }) {
  const { getToken } = useAuth();
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () =>
      process.env.NEXT_PUBLIC_DEV_USER_EMAIL ??
      "richardaustindugger@users.noreply.github.com",
    [],
  );
  const [activeCall, setActiveCall] = useState<ActiveWebPhoneCall | null>(null);
  const [busy, setBusy] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [keypadOpen, setKeypadOpen] = useState(false);
  const [session, setSession] = useState<WebPhoneSession | null>(null);
  const [status, setStatus] = useState<WebPhoneStatus>(INITIAL_WEB_PHONE_STATUS);
  const activeCallRef = useRef<ActiveWebPhoneCall | null>(null);
  const operationRef = useRef<Promise<void> | null>(null);
  const runtimeRef = useRef<WebPhoneRuntime | null>(null);
  const voiceIdentityRef = useRef<string | null>(null);

  const publishActiveCall = useCallback((next: ActiveWebPhoneCall | null) => {
    activeCallRef.current = next;
    setActiveCall(next);
  }, []);

  const fetchVoiceSession = useCallback(async (): Promise<RawVoiceSession> => {
    const token = await getToken({ skipCache: true }).catch(() => null);
    const headers: Record<string, string> = { Accept: "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    else headers["X-Dev-User-Email"] = devUserEmail;
    const response = await fetch(`${apiBaseUrl}/api/v1/voice/session`, {
      headers,
      cache: "no-store",
    });
    const payload = (await response.json().catch(() => null)) as RawVoiceSession | null;
    if (!response.ok || !payload) {
      throw new Error(detailMessage(payload, "Stonegate could not initialize browser calling."));
    }
    return payload;
  }, [apiBaseUrl, devUserEmail, getToken]);

  const showFailure = useCallback((error: unknown) => {
    const message = error instanceof Error ? error.message : "The browser phone action failed.";
    const runtime = runtimeRef.current;
    setStatus((current) => ({
      ...current,
      audioLink: runtime?.hasLiveAudio ? current.audioLink : "error",
      callActive: Boolean(runtime?.hasLiveAudio),
      message,
    }));
  }, []);

  const refreshVoiceToken = useCallback(async () => {
    try {
      const voiceSession = await fetchVoiceSession();
      setSession(safeSession(voiceSession));
      if (!voiceSession.can_initialize || !voiceSession.token) {
        throw new Error(voiceSession.blockers.join(" ") || "Browser Voice token refresh was blocked.");
      }
      if (voiceIdentityRef.current && voiceIdentityRef.current !== voiceSession.identity) {
        throw new Error("The browser phone identity changed during an active call.");
      }
      runtimeRef.current?.updateToken(voiceSession.token);
    } catch (error) {
      showFailure(error);
    }
  }, [fetchVoiceSession, showFailure]);

  const ensureRuntime = useCallback(() => {
    if (runtimeRef.current) return runtimeRef.current;
    const runtime = new WebPhoneRuntime({
      onIncomingCall: (incoming) => {
        setElapsedSeconds(0);
        setKeypadOpen(false);
        publishActiveCall({
          callIntentId: `incoming:${incoming.callId}`,
          contextHref: incoming.contextHref,
          contextLabel: "Incoming Stonegate call",
          direction: "inbound",
          displayName: incoming.callerName,
          fromLabel: incoming.lineLabel,
          fromNumber: incoming.lineNumber,
          phoneNumber: incoming.callerNumber,
          requestedAt: Date.now(),
          audioEstablishedAt: null,
        });
        window.dispatchEvent(new CustomEvent("stonegate:incoming-phone-call"));
      },
      onStatus: (next) => {
        setStatus(next);
        if (
          next.audioLink === "audio_established" &&
          activeCallRef.current &&
          !activeCallRef.current.audioEstablishedAt
        ) {
          setElapsedSeconds(0);
          publishActiveCall({ ...activeCallRef.current, audioEstablishedAt: Date.now() });
        }
      },
      onTokenWillExpire: refreshVoiceToken,
    });
    runtimeRef.current = runtime;
    return runtime;
  }, [publishActiveCall, refreshVoiceToken]);

  const prepareHeadset = useCallback(async () => {
    const voiceSession = await fetchVoiceSession();
    setSession(safeSession(voiceSession));
    if (!voiceSession.can_initialize || !voiceSession.token) {
      throw new Error(voiceSession.blockers.join(" ") || "Browser Voice is not ready.");
    }

    let runtime = ensureRuntime();
    if (voiceIdentityRef.current && voiceIdentityRef.current !== voiceSession.identity) {
      if (runtime.hasLiveAudio) {
        throw new Error("Finish the current call before changing the browser phone identity.");
      }
      runtime.destroy();
      runtimeRef.current = null;
      runtime = ensureRuntime();
    }
    voiceIdentityRef.current = voiceSession.identity;
    await runtime.initialize(voiceSession.token);
  }, [ensureRuntime, fetchVoiceSession]);

  const runExclusive = useCallback(async (operation: () => Promise<void>) => {
    if (operationRef.current) throw new Error("Another browser phone action is already running.");
    setBusy(true);
    const running = operation();
    operationRef.current = running;
    try {
      await running;
    } finally {
      if (operationRef.current === running) operationRef.current = null;
      setBusy(false);
    }
  }, []);

  const initializeHeadset = useCallback(
    () =>
      runExclusive(async () => {
        try {
          await prepareHeadset();
        } catch (error) {
          showFailure(error);
          throw error;
        }
      }),
    [prepareHeadset, runExclusive, showFailure],
  );

  const connectTarget = useCallback(
    async (target: WebPhoneCallTarget) => {
      if (!target.callIntentId.trim()) throw new Error("A call intent is required for browser calling.");
      if (!target.displayName.trim()) throw new Error("A call recipient is required for browser calling.");
      if (activeCallRef.current && runtimeRef.current?.hasLiveAudio) {
        throw new Error("End the current browser call before starting another one.");
      }
      const next: ActiveWebPhoneCall = {
        ...target,
        callIntentId: target.callIntentId.trim(),
        direction: target.direction ?? "outbound",
        displayName: target.displayName.trim(),
        requestedAt: Date.now(),
        audioEstablishedAt: null,
      };
      setElapsedSeconds(0);
      setKeypadOpen(false);
      publishActiveCall(next);
      try {
        await prepareHeadset();
        const runtime = runtimeRef.current;
        if (!runtime) throw new Error("The browser phone is unavailable.");
        await runtime.connect(next.callIntentId);
      } catch (error) {
        if (!runtimeRef.current?.hasLiveAudio) publishActiveCall(null);
        if (error instanceof WebPhoneCancelledError) throw error;
        showFailure(error);
        throw error;
      }
    },
    [prepareHeadset, publishActiveCall, showFailure],
  );

  const startCall = useCallback(
    async (target: WebPhoneCallTarget) => {
      if (operationRef.current) throw new Error("Another browser phone action is already running.");
      return runExclusive(() => connectTarget(target));
    },
    [connectTarget, runExclusive],
  );

  const prepareAndStartCall = useCallback(
    async (prepareTarget: () => Promise<WebPhoneCallTarget>) => {
      if (operationRef.current) throw new Error("Another browser phone action is already running.");
      if (activeCallRef.current && runtimeRef.current?.hasLiveAudio) {
        throw new Error("End the current browser call before starting another one.");
      }
      return runExclusive(async () => {
        const reservedRuntime = ensureRuntime();
        const reservation = reservedRuntime.reserveCallOwnership();
        if (reservation) await reservation;
        try {
          const target = await prepareTarget();
          await connectTarget(target);
        } catch (error) {
          reservedRuntime.releaseCallReservation();
          throw error;
        }
      });
    },
    [connectTarget, ensureRuntime, runExclusive],
  );

  const hangUp = useCallback(() => {
    setKeypadOpen(false);
    runtimeRef.current?.disconnectLocalAudio();
  }, []);

  const enableIncomingCalls = useCallback(
    () =>
      runExclusive(async () => {
        try {
          await prepareHeadset();
          const runtime = runtimeRef.current;
          if (!runtime) throw new Error("The browser phone is unavailable.");
          await runtime.registerIncomingCalls();
        } catch (error) {
          showFailure(error);
          throw error;
        }
      }),
    [prepareHeadset, runExclusive, showFailure],
  );

  const disableIncomingCalls = useCallback(
    () =>
      runExclusive(async () => {
        const runtime = runtimeRef.current;
        if (!runtime) return;
        await runtime.unregisterIncomingCalls();
        runtime.destroy();
        runtimeRef.current = null;
        voiceIdentityRef.current = null;
        setSession(null);
        setStatus(INITIAL_WEB_PHONE_STATUS);
      }),
    [runExclusive],
  );

  const acceptIncomingCall = useCallback(() => {
    try {
      runtimeRef.current?.acceptIncomingCall();
    } catch (error) {
      showFailure(error);
    }
  }, [showFailure]);

  const rejectIncomingCall = useCallback(() => {
    setKeypadOpen(false);
    runtimeRef.current?.rejectIncomingCall();
  }, []);

  const toggleMute = useCallback(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.hasLiveAudio) throw new Error("There is no active browser call to mute.");
    runtime.setMuted(!runtime.currentStatus.muted);
  }, []);

  const sendDigits = useCallback(
    (digits: string) => {
      try {
        const runtime = runtimeRef.current;
        if (!runtime) throw new Error("The browser phone is unavailable.");
        runtime.sendDigits(digits);
      } catch (error) {
        showFailure(error);
      }
    },
    [showFailure],
  );

  const reset = useCallback(() => {
    const runtime = runtimeRef.current;
    if (runtime?.hasLiveAudio) throw new Error("End the current browser call before closing the phone.");
    if (runtime?.currentStatus.incomingRegistration === "ready") runtime.resetAfterCall();
    else {
      runtime?.destroy();
      runtimeRef.current = null;
      voiceIdentityRef.current = null;
      setSession(null);
    }
    setKeypadOpen(false);
    publishActiveCall(null);
    if (!runtime || runtime.currentStatus.incomingRegistration !== "ready") {
      setStatus(INITIAL_WEB_PHONE_STATUS);
    }
  }, [publishActiveCall]);

  useEffect(() => {
    const establishedAt = activeCall?.audioEstablishedAt;
    if (
      !establishedAt ||
      !["audio_established", "reconnecting"].includes(status.audioLink)
    ) {
      return;
    }
    const update = () => setElapsedSeconds(Math.max(0, Math.floor((Date.now() - establishedAt) / 1000)));
    const interval = window.setInterval(update, 1_000);
    return () => window.clearInterval(interval);
  }, [activeCall?.audioEstablishedAt, status.audioLink]);

  useEffect(() => {
    const intentId = activeCall?.direction === "outbound" ? activeCall.callIntentId : null;
    if (!intentId || !["ended", "error"].includes(status.audioLink)) {
      return;
    }
    const controller = new AbortController();

    async function reconcileProviderResult(callIntentId: string) {
      for (let attempt = 0; attempt < 5; attempt += 1) {
        if (attempt > 0) {
          await new Promise<void>((resolve) => window.setTimeout(resolve, 450 * attempt));
        }
        if (controller.signal.aborted) return;
        const token = await getToken().catch(() => null);
        const headers: Record<string, string> = { Accept: "application/json" };
        if (token) headers.Authorization = `Bearer ${token}`;
        else headers["X-Dev-User-Email"] = devUserEmail;
        const response = await fetch(
          `${apiBaseUrl}/api/v1/voice/call-intents/${encodeURIComponent(callIntentId)}/status`,
          { headers, cache: "no-store", signal: controller.signal },
        ).catch(() => null);
        if (!response?.ok) continue;
        const result = (await response.json().catch(() => null)) as VoiceCallStatus | null;
        if (!result?.terminal) continue;
        setStatus((current) => ({ ...current, message: completedCallMessage(result.status) }));
        return;
      }
    }

    void reconcileProviderResult(intentId);
    return () => controller.abort();
  }, [activeCall, apiBaseUrl, devUserEmail, getToken, status.audioLink]);

  useEffect(
    () => () => {
      runtimeRef.current?.destroy();
      runtimeRef.current = null;
    },
    [],
  );

  const value = useMemo<WebPhoneContextValue>(
    () => ({
      acceptIncomingCall,
      activeCall,
      busy,
      disableIncomingCalls,
      enableIncomingCalls,
      hangUp,
      incomingEnabled: status.incomingRegistration === "ready",
      initializeHeadset,
      prepareAndStartCall,
      rejectIncomingCall,
      reset,
      sendDigits,
      session,
      startCall,
      status,
      toggleMute,
    }),
    [
      acceptIncomingCall,
      activeCall,
      busy,
      disableIncomingCalls,
      enableIncomingCalls,
      hangUp,
      initializeHeadset,
      prepareAndStartCall,
      rejectIncomingCall,
      reset,
      sendDigits,
      session,
      startCall,
      status,
      toggleMute,
    ],
  );
  const panelVisible = Boolean(activeCall) || !["idle", "ready"].includes(status.audioLink);
  const incomingRinging = Boolean(
    activeCall?.direction === "inbound" && status.audioLink === "incoming_ringing",
  );
  const canMute = Boolean(
    activeCall && status.callActive && ["audio_established", "reconnecting"].includes(status.audioLink),
  );
  const canEnd = Boolean(activeCall && status.callActive && !incomingRinging);
  const canUseKeypad = Boolean(
    activeCall && status.callActive && status.audioLink === "audio_established",
  );
  const keypadVisible = keypadOpen && canUseKeypad;

  return (
    <WebPhoneContext.Provider value={value}>
      {children}
      {panelVisible ? (
        <aside
          aria-label="Stonegate browser phone"
          className={`${styles.panel} ${keypadVisible ? styles.panelKeypadOpen : ""}`}
          data-audio-state={status.audioLink}
          id="stonegate-active-phone"
          tabIndex={-1}
        >
          <div className={styles.statusIcon} aria-hidden="true">
            <Phone size={18} />
          </div>
          <div className={styles.callCopy}>
            <span>{activeCall ? activeCall.contextLabel ?? "Stonegate web phone" : "Stonegate web phone"}</span>
            <strong>{activeCall?.displayName ?? audioStateLabel(status)}</strong>
            <small>
              {activeCall?.phoneNumber ? `${activeCall.phoneNumber} · ` : ""}
              <span aria-live="polite">{audioStateLabel(status)}</span>
              {status.audioLink === "audio_established" ? (
                <span aria-live="off"> · {elapsedLabel(elapsedSeconds)}</span>
              ) : null}
            </small>
            {status.message ? <small className={styles.message}>{status.message}</small> : null}
          </div>
          <div className={styles.controls}>
            {activeCall?.contextHref ? (
              <Link aria-label={`Open ${activeCall.displayName}`} href={activeCall.contextHref}>
                <ExternalLink aria-hidden="true" size={16} />
              </Link>
            ) : null}
            <button
              aria-controls="stonegate-active-call-keypad"
              aria-expanded={keypadVisible}
              aria-label={keypadVisible ? "Close call keypad" : "Open call keypad"}
              disabled={!canUseKeypad || busy}
              onClick={() => setKeypadOpen((current) => !current)}
              type="button"
            >
              <Grid3x3 aria-hidden="true" size={17} />
            </button>
            <button
              aria-label={status.muted ? "Unmute browser call" : "Mute browser call"}
              aria-pressed={status.muted}
              disabled={!canMute || busy}
              onClick={() => toggleMute()}
              type="button"
            >
              {status.muted ? <MicOff aria-hidden="true" size={17} /> : <Mic aria-hidden="true" size={17} />}
            </button>
            {incomingRinging ? (
              <button
                aria-label="Answer incoming call"
                className={styles.answerButton}
                disabled={busy}
                onClick={acceptIncomingCall}
                type="button"
              >
                <PhoneIncoming aria-hidden="true" size={17} />
              </button>
            ) : null}
            <button
              aria-label={incomingRinging ? "Decline incoming call" : "End browser call"}
              className={styles.endButton}
              disabled={incomingRinging ? busy : !canEnd}
              id="stonegate-active-phone-end-call"
              onClick={incomingRinging ? rejectIncomingCall : hangUp}
              type="button"
            >
              <PhoneOff aria-hidden="true" size={17} />
            </button>
            {!status.callActive ? (
              <button
                aria-label="Close browser phone"
                disabled={busy}
                onClick={reset}
                type="button"
              >
                <X aria-hidden="true" size={17} />
              </button>
            ) : null}
          </div>
          {keypadVisible ? (
            <div
              aria-label="Active call keypad"
              className={styles.dtmfPad}
              id="stonegate-active-call-keypad"
              role="group"
            >
              {dtmfKeys.map((key) => (
                <button
                  aria-label={`Send ${key === "*" ? "star" : key === "#" ? "pound" : key} tone`}
                  key={key}
                  onClick={() => sendDigits(key)}
                  type="button"
                >
                  {key}
                </button>
              ))}
            </div>
          ) : null}
          {activeCall?.fromNumber || session?.line ? (
            <span className={styles.lineLabel}>
              {activeCall?.direction === "inbound" ? "On" : "From"}{" "}
              {activeCall?.direction === "inbound"
                ? activeCall.fromLabel ?? session?.line?.label ?? "Stonegate"
                : activeCall?.fromLabel ?? (
                    activeCall?.fromNumber && activeCall.fromNumber !== session?.line?.phone_number
                      ? "Stonegate"
                      : session?.line?.label ?? "Stonegate"
                  )}{" "}
              ·{" "}
              {activeCall?.direction === "inbound"
                ? activeCall.fromNumber ?? session?.line?.phone_number
                : activeCall?.fromNumber ?? session?.line?.phone_number}
            </span>
          ) : null}
        </aside>
      ) : null}
    </WebPhoneContext.Provider>
  );
}

export function useWebPhone() {
  const context = useContext(WebPhoneContext);
  if (!context) throw new Error("useWebPhone must be used inside WebPhoneProvider.");
  return context;
}
