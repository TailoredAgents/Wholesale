"use client";

import { useAuth } from "@clerk/nextjs";
import {
  Headphones,
  Mic,
  MicOff,
  Pause,
  PhoneCall,
  PhoneOff,
  Play,
  RefreshCw,
  ShieldAlert,
  Square,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  ProspectingDialerContext,
  ProspectingDialLeg,
  ProspectingDialSessionControl,
  ProspectingDialSessionSnapshot,
  ProspectingEntry,
  ProspectingVoiceCall,
  ProspectingVoiceSession,
} from "../../lib/api";
import {
  ProspectingSoftphone,
  type ProspectingSoftphoneStatus,
} from "./prospecting-softphone";
import {
  dialerControlAvailability,
  isPendingLeaseRecoveryForLease,
  isNativeDialerFeatureReady,
  shouldNativeDialerOwnStart,
  shouldDiscardPendingMutation,
  shouldProtectNavigation,
  shouldRecoverExpiredLease,
  type ProspectingDialerLeadership,
} from "./prospecting-dialer-policy";
import styles from "./prospecting.module.css";

export type ActiveProspectingDialerLease = {
  sessionId: string;
  browserSessionId: string;
  leaseToken: string;
};

export type ProspectingDialerRuntime = {
  sessionState: ProspectingDialSessionSnapshot["session"]["state"] | null;
  legStatus: ProspectingDialLeg["status"] | null;
  terminalResult: string | null;
  providerError: string | null;
  recipient: string | null;
  technicalFailure: boolean;
  wrapUpReady: boolean;
};

type StoredDialerLease = ActiveProspectingDialerLease & {
  userId: string;
};

type PendingDialerSessionStart = {
  userId: string;
  entryId: string;
  campaignId: string;
  cohortId: string;
  callingBatchId: string;
  browserSessionId: string;
  idempotencyKey: string;
};

type PendingDialerLeaseRecovery = {
  userId: string;
  sessionId: string;
  previousBrowserSessionId: string;
  newBrowserSessionId: string;
};

const INITIAL_SOFTPHONE_STATUS: ProspectingSoftphoneStatus = {
  audioLink: "idle",
  microphone: "unchecked",
  muted: false,
  message: null,
};

const TERMINAL_SESSION_STATES = new Set(["ended", "stopped", "failed", "expired"]);
const TERMINAL_LEG_STATES = new Set([
  "cancelled",
  "no_answer",
  "busy",
  "failed",
  "completed",
]);
const HISTORY_GUARD_STATE_KEY = "__stonegateProspectingCallGuard";
function storageKey(userId: string) {
  return `stonegate:prospecting:dialer:${userId}`;
}

function pendingStartStorageKey(userId: string) {
  return `stonegate:prospecting:dialer-start:${userId}`;
}

function pendingRecoveryStorageKey(userId: string) {
  return `stonegate:prospecting:dialer-recovery:${userId}`;
}

function readStoredLease(userId: string): StoredDialerLease | null {
  try {
    const raw = window.sessionStorage.getItem(storageKey(userId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredDialerLease>;
    if (
      parsed.userId !== userId ||
      !parsed.sessionId ||
      !parsed.browserSessionId ||
      !parsed.leaseToken
    ) {
      window.sessionStorage.removeItem(storageKey(userId));
      return null;
    }
    return parsed as StoredDialerLease;
  } catch {
    window.sessionStorage.removeItem(storageKey(userId));
    return null;
  }
}

function writeStoredLease(userId: string, lease: ActiveProspectingDialerLease) {
  window.sessionStorage.setItem(
    storageKey(userId),
    JSON.stringify({ ...lease, userId } satisfies StoredDialerLease),
  );
}

function clearStoredLease(userId: string) {
  window.sessionStorage.removeItem(storageKey(userId));
}

function readPendingStart(userId: string): PendingDialerSessionStart | null {
  try {
    const raw = window.sessionStorage.getItem(pendingStartStorageKey(userId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<PendingDialerSessionStart>;
    if (
      parsed.userId !== userId ||
      !parsed.entryId ||
      !parsed.campaignId ||
      !parsed.cohortId ||
      !parsed.callingBatchId ||
      !parsed.browserSessionId ||
      !parsed.idempotencyKey
    ) {
      window.sessionStorage.removeItem(pendingStartStorageKey(userId));
      return null;
    }
    return parsed as PendingDialerSessionStart;
  } catch {
    window.sessionStorage.removeItem(pendingStartStorageKey(userId));
    return null;
  }
}

function writePendingStart(userId: string, pending: PendingDialerSessionStart) {
  window.sessionStorage.setItem(pendingStartStorageKey(userId), JSON.stringify(pending));
}

function clearPendingStart(userId: string) {
  window.sessionStorage.removeItem(pendingStartStorageKey(userId));
}

function readPendingRecovery(userId: string): PendingDialerLeaseRecovery | null {
  try {
    const raw = window.sessionStorage.getItem(pendingRecoveryStorageKey(userId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<PendingDialerLeaseRecovery>;
    if (
      parsed.userId !== userId ||
      !parsed.sessionId ||
      !parsed.previousBrowserSessionId ||
      !parsed.newBrowserSessionId
    ) {
      window.sessionStorage.removeItem(pendingRecoveryStorageKey(userId));
      return null;
    }
    return parsed as PendingDialerLeaseRecovery;
  } catch {
    window.sessionStorage.removeItem(pendingRecoveryStorageKey(userId));
    return null;
  }
}

function writePendingRecovery(userId: string, pending: PendingDialerLeaseRecovery) {
  window.sessionStorage.setItem(pendingRecoveryStorageKey(userId), JSON.stringify(pending));
}

function clearPendingRecovery(userId: string) {
  window.sessionStorage.removeItem(pendingRecoveryStorageKey(userId));
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "The dialer operation failed.";
}

function sellerStateLabel(leg: ProspectingDialLeg | null) {
  if (!leg) return "No seller call";
  const labels: Record<ProspectingDialLeg["status"], string> = {
    queued: "Ready to call",
    dialing: "Calling seller",
    ringing: "Seller phone ringing",
    answered: "Seller answered",
    connected: "Seller connected",
    cancelling: "Stopping ring",
    cancelled: "Call cancelled",
    no_answer: "No answer",
    busy: "Line busy",
    failed: "Call failed",
    completed: "Call ended",
  };
  return labels[leg.status];
}

function audioStateLabel(status: ProspectingSoftphoneStatus) {
  const labels: Record<ProspectingSoftphoneStatus["audioLink"], string> = {
    idle: "Headset not started",
    requesting_microphone: "Checking microphone",
    ready: "Headset ready",
    connecting: "Connecting browser audio",
    audio_established: "Browser audio established",
    reconnecting: "Browser audio reconnecting",
    ended: "Browser audio ended",
    error: "Browser audio needs attention",
  };
  return labels[status.audioLink];
}

export function ProspectingDialer({
  currentUserId,
  entries,
  selectedEntry,
  onEntryChange,
  onLeaseChange,
  onNativeModeChange,
  onOwnershipChange,
  onRuntimeChange,
  onWorkspaceRefresh,
}: {
  currentUserId: string;
  entries: ProspectingEntry[];
  selectedEntry: ProspectingEntry | null;
  onEntryChange: (entry: ProspectingEntry) => void;
  onLeaseChange: (lease: ActiveProspectingDialerLease | null) => void;
  onNativeModeChange: (available: boolean) => void;
  onOwnershipChange: (leadership: ProspectingDialerLeadership) => void;
  onRuntimeChange: (runtime: ProspectingDialerRuntime) => void;
  onWorkspaceRefresh: () => void;
}) {
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
  const [leadership, setLeadership] = useState<ProspectingDialerLeadership>("checking");
  const [context, setContext] = useState<ProspectingDialerContext | null>(null);
  const [snapshot, setSnapshot] = useState<ProspectingDialSessionSnapshot | null>(null);
  const [lease, setLease] = useState<ActiveProspectingDialerLease | null>(null);
  const [voiceCall, setVoiceCall] = useState<ProspectingVoiceCall | null>(null);
  const [softphoneStatus, setSoftphoneStatus] = useState(INITIAL_SOFTPHONE_STATUS);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [leaseWarning, setLeaseWarning] = useState<string | null>(null);
  const [syncWarning, setSyncWarning] = useState<string | null>(null);
  const [audioLostAfterReload, setAudioLostAfterReload] = useState(false);
  const mountedRef = useRef(false);
  const softphoneRef = useRef<ProspectingSoftphone | null>(null);
  const voiceIdentityRef = useRef<string | null>(null);
  const identityStaleForNextCallRef = useRef(false);
  const tokenRefreshRef = useRef<Promise<void> | null>(null);
  const refreshVoiceTokenRef = useRef<() => Promise<void>>(async () => undefined);
  const heartbeatRef = useRef<Promise<void> | null>(null);
  const pollRef = useRef<Promise<void> | null>(null);
  const reconcileRef = useRef<Promise<ProspectingVoiceCall | null> | null>(null);
  const actionRef = useRef<Promise<void> | null>(null);
  const leaseRef = useRef<ActiveProspectingDialerLease | null>(null);
  const snapshotRef = useRef<ProspectingDialSessionSnapshot | null>(null);
  const voiceCallRef = useRef<ProspectingVoiceCall | null>(null);
  const entriesRef = useRef(entries);
  const selectedEntryIdRef = useRef(selectedEntry?.id ?? null);
  const onEntryChangeRef = useRef(onEntryChange);
  const onLeaseChangeRef = useRef(onLeaseChange);
  const onWorkspaceRefreshRef = useRef(onWorkspaceRefresh);
  const observedLegIdRef = useRef<string | null>(null);

  useEffect(() => {
    entriesRef.current = entries;
    selectedEntryIdRef.current = selectedEntry?.id ?? null;
    onEntryChangeRef.current = onEntryChange;
    onLeaseChangeRef.current = onLeaseChange;
    onWorkspaceRefreshRef.current = onWorkspaceRefresh;
  }, [entries, onEntryChange, onLeaseChange, onWorkspaceRefresh, selectedEntry?.id]);

  const setActiveVoiceCall = useCallback((next: ProspectingVoiceCall | null) => {
    voiceCallRef.current = next;
    setVoiceCall(next);
  }, []);

  const setActiveLease = useCallback(
    (next: ActiveProspectingDialerLease | null) => {
      leaseRef.current = next;
      setLease(next);
      onLeaseChangeRef.current(next);
      if (next) writeStoredLease(currentUserId, next);
      else clearStoredLease(currentUserId);
    },
    [currentUserId],
  );

  const applySnapshot = useCallback(
    (next: ProspectingDialSessionSnapshot) => {
      snapshotRef.current = next;
      setSnapshot(next);
      const currentProspectId = next.current_leg?.prospect_id;
      if (currentProspectId) {
        const matchingEntry = entriesRef.current.find(
          (item) => item.prospect_id === currentProspectId,
        );
        if (matchingEntry && matchingEntry.id !== selectedEntryIdRef.current) {
          onEntryChangeRef.current(matchingEntry);
        }
      }
      const nextLeg = next.current_leg;
      const currentCall = voiceCallRef.current;
      if (!currentCall || currentCall.dial_leg_id !== nextLeg?.id) {
        setActiveVoiceCall(null);
      } else {
        setActiveVoiceCall({
          ...currentCall,
          provider_call_id: nextLeg.provider_call_id ?? currentCall.provider_call_id,
          leg: nextLeg,
        });
      }
      if (TERMINAL_SESSION_STATES.has(next.session.state)) {
        setActiveLease(null);
        clearPendingStart(currentUserId);
        clearPendingRecovery(currentUserId);
        setActiveVoiceCall(null);
        setAudioLostAfterReload(false);
        softphoneRef.current?.destroy();
        voiceIdentityRef.current = null;
      }
    },
    [currentUserId, setActiveLease, setActiveVoiceCall],
  );

  const apiRequest = useCallback(
    async <T,>(path: string, options?: { method?: "GET" | "POST"; body?: object }) => {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;
      const response = await fetch(`${apiBaseUrl}${path}`, {
        method: options?.method ?? "GET",
        headers,
        body: options?.body ? JSON.stringify(options.body) : undefined,
        cache: "no-store",
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        const error = new Error(payload?.detail ?? "The dialer operation could not be completed.");
        Object.assign(error, { status: response.status });
        throw error;
      }
      return (await response.json()) as T;
    },
    [apiBaseUrl, devUserEmail, getToken],
  );

  const refreshVoiceToken = useCallback(async () => {
    if (tokenRefreshRef.current) return tokenRefreshRef.current;
    const currentLease = leaseRef.current;
    if (!currentLease || leadership !== "leader") return;
    const operation = (async () => {
      const voiceSession = await apiRequest<ProspectingVoiceSession>(
        `/api/v1/prospecting/dialer/sessions/${currentLease.sessionId}/voice-session`,
        {
          method: "POST",
          body: {
            browser_session_id: currentLease.browserSessionId,
            lease_token: currentLease.leaseToken,
          },
        },
      );
      if (!voiceSession.can_initialize || !voiceSession.token) {
        throw new Error(voiceSession.blockers.join(" ") || "Browser Voice is not ready.");
      }
      if (
        voiceIdentityRef.current &&
        voiceIdentityRef.current !== voiceSession.identity
      ) {
        if (softphoneRef.current?.hasLiveAudio) {
          identityStaleForNextCallRef.current = true;
          setSyncWarning(
            "The recovered lease will use a new headset identity after this call. Current audio was preserved.",
          );
          return;
        }
        softphoneRef.current?.destroy();
        voiceIdentityRef.current = null;
        identityStaleForNextCallRef.current = false;
        throw new Error("The browser lease changed. Reinitialize the headset before calling.");
      }
      const softphone = softphoneRef.current;
      if (!softphone) throw new Error("The browser headset is unavailable.");
      softphone.updateToken(voiceSession.token);
    })().finally(() => {
      tokenRefreshRef.current = null;
    });
    tokenRefreshRef.current = operation;
    return operation;
  }, [apiRequest, leadership]);

  useEffect(() => {
    refreshVoiceTokenRef.current = refreshVoiceToken;
  }, [refreshVoiceToken]);

  useEffect(() => {
    mountedRef.current = true;
    const softphone = new ProspectingSoftphone({
      onStatus: (status) => {
        if (mountedRef.current) setSoftphoneStatus(status);
      },
      onTokenWillExpire: () => {
        void refreshVoiceTokenRef.current().catch((error) => {
          if (mountedRef.current) setFailure(errorMessage(error));
        });
      },
    });
    softphoneRef.current = softphone;
    return () => {
      mountedRef.current = false;
      softphone.destroy();
      if (softphoneRef.current === softphone) softphoneRef.current = null;
    };
  }, []);

  useEffect(() => {
    let active = true;
    let releaseLock: (() => void) | null = null;
    let pulse: ReturnType<typeof setInterval> | null = null;
    let retry: ReturnType<typeof setInterval> | null = null;
    let lockHeld = false;
    let lockRequestPending = false;
    const channel =
      typeof BroadcastChannel === "undefined"
        ? null
        : new BroadcastChannel(`stonegate:prospecting:dialer-owner:${currentUserId}`);

    if (!("locks" in navigator)) {
      const unsupportedTimer = window.setTimeout(() => setLeadership("unsupported"), 0);
      channel?.close();
      return () => window.clearTimeout(unsupportedTimer);
    }
    const tryAcquireLeadership = () => {
      if (!active || lockHeld || lockRequestPending) return;
      lockRequestPending = true;
      void navigator.locks
        .request(
          `stonegate:prospecting:dialer-owner:${currentUserId}`,
          { ifAvailable: true, mode: "exclusive" },
          async (lock) => {
            lockRequestPending = false;
            if (!active) return;
            if (!lock) {
              setLeadership("passive");
              return;
            }
            lockHeld = true;
            setLeadership("leader");
            channel?.postMessage({ type: "leader-active" });
            pulse = setInterval(
              () => channel?.postMessage({ type: "leader-active" }),
              5_000,
            );
            await new Promise<void>((resolve) => {
              releaseLock = resolve;
            });
            lockHeld = false;
          },
        )
        .catch(() => {
          lockRequestPending = false;
          if (active) setLeadership("unsupported");
        });
    };
    channel?.addEventListener("message", (event) => {
      if (event.data?.type === "leader-released") tryAcquireLeadership();
    });
    tryAcquireLeadership();
    retry = setInterval(tryAcquireLeadership, 3_000);
    return () => {
      active = false;
      channel?.postMessage({ type: "leader-released" });
      if (pulse) clearInterval(pulse);
      if (retry) clearInterval(retry);
      releaseLock?.();
      channel?.close();
    };
  }, [currentUserId]);

  const beginOrReplaySession = useCallback(
    async (pending: PendingDialerSessionStart) => {
      try {
        const result = await apiRequest<ProspectingDialSessionControl>(
          "/api/v1/prospecting/dialer/sessions",
          {
            method: "POST",
            body: {
              campaign_id: pending.campaignId,
              cohort_id: pending.cohortId,
              calling_batch_id: pending.callingBatchId,
              browser_session_id: pending.browserSessionId,
              idempotency_key: pending.idempotencyKey,
              requested_line_count: 1,
            },
          },
        );
        if (!result.lease_token) throw new Error("The dialer session returned no lease.");
        setActiveLease({
          sessionId: result.snapshot.session.id,
          browserSessionId: pending.browserSessionId,
          leaseToken: result.lease_token,
        });
        clearPendingStart(currentUserId);
        applySnapshot(result.snapshot);
        observedLegIdRef.current = result.snapshot.current_leg?.id ?? null;
        onWorkspaceRefreshRef.current();
        return result.snapshot;
      } catch (error) {
        const status = (error as Error & { status?: number }).status;
        if (shouldDiscardPendingMutation(status)) {
          clearPendingStart(currentUserId);
        }
        throw error;
      }
    },
    [apiRequest, applySnapshot, currentUserId, setActiveLease],
  );

  const reconcileVoiceCall = useCallback(
    async (dialLegId: string, restoredAfterReload = false) => {
      if (reconcileRef.current) return reconcileRef.current;
      const operation = (async () => {
        const call = await apiRequest<ProspectingVoiceCall>(
          `/api/v1/prospecting/dialer/legs/${dialLegId}/call`,
        );
        if (snapshotRef.current?.current_leg?.id !== dialLegId) return null;
        setActiveVoiceCall(call);
        const currentSession = snapshotRef.current.session;
        applySnapshot({ session: currentSession, current_leg: call.leg });
        if (
          restoredAfterReload &&
          !TERMINAL_LEG_STATES.has(call.leg.status) &&
          !softphoneRef.current?.hasLiveAudio
        ) {
          setAudioLostAfterReload(true);
        }
        return call;
      })().finally(() => {
        reconcileRef.current = null;
      });
      reconcileRef.current = operation;
      return operation;
    },
    [apiRequest, applySnapshot, setActiveVoiceCall],
  );

  const heartbeat = useCallback(async () => {
    if (heartbeatRef.current) return heartbeatRef.current;
    const operation = (async () => {
      const currentLease = leaseRef.current;
      if (!currentLease || leadership !== "leader") return;
      try {
        const result = await apiRequest<ProspectingDialSessionControl>(
          `/api/v1/prospecting/dialer/sessions/${currentLease.sessionId}/heartbeat`,
          {
            method: "POST",
            body: {
              browser_session_id: currentLease.browserSessionId,
              lease_token: currentLease.leaseToken,
            },
          },
        );
        const nextLease = result.lease_token
          ? { ...currentLease, leaseToken: result.lease_token }
          : currentLease;
        setActiveLease(nextLease);
        const pendingRecovery = readPendingRecovery(currentUserId);
        if (
          isPendingLeaseRecoveryForLease(
            pendingRecovery,
            currentLease,
            currentUserId,
          )
        ) {
          clearPendingRecovery(currentUserId);
        }
        applySnapshot(result.snapshot);
        setLeaseWarning(null);
      } catch (error) {
        const message = errorMessage(error);
        const status = (error as Error & { status?: number }).status;
        const storedRecovery = readPendingRecovery(currentUserId);
        const replaysPendingRecovery = isPendingLeaseRecoveryForLease(
          storedRecovery,
          currentLease,
          currentUserId,
        );
        if (!shouldRecoverExpiredLease(status, message) && !replaysPendingRecovery) {
          setLeaseWarning(message);
          return;
        }
        const recovery = replaysPendingRecovery
          ? storedRecovery
          : {
              userId: currentUserId,
              sessionId: currentLease.sessionId,
              previousBrowserSessionId: currentLease.browserSessionId,
              newBrowserSessionId: crypto.randomUUID(),
            };
        if (!recovery) {
          setLeaseWarning("The browser lease recovery could not be restored.");
          return;
        }
        writePendingRecovery(currentUserId, recovery);
        try {
          const recovered = await apiRequest<ProspectingDialSessionControl>(
            `/api/v1/prospecting/dialer/sessions/${currentLease.sessionId}/recover`,
            {
              method: "POST",
              body: {
                previous_browser_session_id: recovery.previousBrowserSessionId,
                new_browser_session_id: recovery.newBrowserSessionId,
                lease_token: currentLease.leaseToken,
              },
            },
          );
          if (!recovered.lease_token) throw new Error("Dialer recovery returned no lease.");
          const liveAudioPreserved = Boolean(softphoneRef.current?.hasLiveAudio);
          if (liveAudioPreserved) {
            identityStaleForNextCallRef.current = true;
          } else {
            softphoneRef.current?.destroy();
            voiceIdentityRef.current = null;
            identityStaleForNextCallRef.current = false;
            setSoftphoneStatus(INITIAL_SOFTPHONE_STATUS);
          }
          setActiveLease({
            sessionId: currentLease.sessionId,
            browserSessionId: recovery.newBrowserSessionId,
            leaseToken: recovered.lease_token,
          });
          clearPendingRecovery(currentUserId);
          applySnapshot(recovered.snapshot);
          setNotice(
            liveAudioPreserved
              ? "The browser lease was recovered without interrupting the current audio. Reinitialize after wrap-up."
              : "The expired browser lease was recovered. Reinitialize audio before calling.",
          );
          setLeaseWarning(null);
        } catch (recoveryError) {
          const recoveryStatus = (recoveryError as Error & { status?: number }).status;
          if (shouldDiscardPendingMutation(recoveryStatus)) {
            clearPendingRecovery(currentUserId);
          }
          setLeaseWarning(errorMessage(recoveryError));
        }
      }
    })().finally(() => {
      heartbeatRef.current = null;
    });
    heartbeatRef.current = operation;
    return operation;
  }, [apiRequest, applySnapshot, currentUserId, leadership, setActiveLease]);

  const refreshDurableState = useCallback(async () => {
    if (pollRef.current) return pollRef.current;
    const operation = (async () => {
      const currentLease = leaseRef.current;
      const currentSnapshot = snapshotRef.current;
      if (!currentLease || !currentSnapshot || leadership !== "leader") return;
      try {
        const previousLegId = currentSnapshot.current_leg?.id ?? null;
        const next = await apiRequest<ProspectingDialSessionSnapshot>(
          `/api/v1/prospecting/dialer/sessions/${currentLease.sessionId}`,
        );
        applySnapshot(next);
        const nextLegId = next.current_leg?.id ?? null;
        if (nextLegId !== previousLegId) {
          observedLegIdRef.current = nextLegId;
          onWorkspaceRefreshRef.current();
        }
        if (
          next.current_leg &&
          TERMINAL_LEG_STATES.has(next.current_leg.status) &&
          softphoneRef.current?.hasLiveAudio
        ) {
          softphoneRef.current.disconnectLocalAudio();
        }
        setSyncWarning(null);
      } catch (error) {
        setSyncWarning(errorMessage(error));
      }
    })().finally(() => {
      pollRef.current = null;
    });
    pollRef.current = operation;
    return operation;
  }, [apiRequest, applySnapshot, leadership]);

  useEffect(() => {
    if (leadership !== "leader") return;
    let cancelled = false;
    void (async () => {
      try {
        const dialerContext = await apiRequest<ProspectingDialerContext>(
          "/api/v1/prospecting/dialer/context",
        );
        if (cancelled) return;
        setContext(dialerContext);
        const stored = readStoredLease(currentUserId);
        const pending = readPendingStart(currentUserId);
        if (!dialerContext.active_session) {
          setActiveLease(null);
          if (pending) await beginOrReplaySession(pending);
          else clearPendingRecovery(currentUserId);
          return;
        }
        const activeLeg = dialerContext.active_legs.find(
          (item) => item.dial_session_id === dialerContext.active_session?.id,
        ) ?? null;
        const restoredSnapshot = {
          session: dialerContext.active_session,
          current_leg: activeLeg,
        } satisfies ProspectingDialSessionSnapshot;
        applySnapshot(restoredSnapshot);
        observedLegIdRef.current = activeLeg?.id ?? null;
        if (stored?.sessionId === dialerContext.active_session.id) {
          setActiveLease(stored);
        } else if (
          pending &&
          pending.campaignId === dialerContext.active_session.campaign_id
        ) {
          await beginOrReplaySession(pending);
        } else {
          setFailure(
            "This active shift belongs to another browser lease. Wait for it to expire or end it from its owning tab.",
          );
          return;
        }
        if (activeLeg?.call_record_id) {
          void reconcileVoiceCall(activeLeg.id, true).catch((error) => {
            if (!cancelled) setSyncWarning(errorMessage(error));
          });
        }
        window.setTimeout(() => void heartbeat(), 0);
      } catch (error) {
        if (!cancelled) setFailure(errorMessage(error));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    apiRequest,
    applySnapshot,
    beginOrReplaySession,
    currentUserId,
    heartbeat,
    leadership,
    reconcileVoiceCall,
    setActiveLease,
  ]);

  useEffect(() => {
    if (leadership !== "leader" || !lease) return;
    const heartbeatTimer = window.setInterval(() => void heartbeat(), 30_000);
    const pollTimer = window.setInterval(() => void refreshDurableState(), 3_000);
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        void heartbeat();
        void refreshDurableState();
        const activeLeg = snapshotRef.current?.current_leg;
        if (activeLeg?.call_record_id) {
          void reconcileVoiceCall(activeLeg.id).catch((error) => {
            setSyncWarning(errorMessage(error));
          });
        }
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearInterval(heartbeatTimer);
      window.clearInterval(pollTimer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [heartbeat, leadership, lease, reconcileVoiceCall, refreshDurableState]);

  const protectedCallId = snapshot?.current_leg?.call_record_id ?? null;
  const navigationProtectionRequired = shouldProtectNavigation(
    Boolean(lease),
    snapshot?.current_leg ?? null,
    TERMINAL_LEG_STATES,
  );

  useEffect(() => {
    if (!navigationProtectionRequired || !protectedCallId) return;
    const warning =
      "A Stonegate call is active. Leaving this page will disconnect browser audio. Continue?";
    const marker = `${protectedCallId}:${crypto.randomUUID()}`;
    const existingState = window.history.state;
    const guardState =
      existingState && typeof existingState === "object"
        ? { ...existingState, [HISTORY_GUARD_STATE_KEY]: marker }
        : { [HISTORY_GUARD_STATE_KEY]: marker };
    let allowingNavigation = false;
    let pendingDestination: string | null = null;
    window.history.pushState(guardState, "", window.location.href);

    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      if (allowingNavigation) return;
      event.preventDefault();
      event.returnValue = "";
    };
    const guardInternalNavigation = (event: MouseEvent) => {
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return;
      }
      const target = event.target;
      const anchor = target instanceof Element ? target.closest("a[href]") : null;
      if (!anchor || anchor.getAttribute("target") === "_blank") return;
      const destination = new URL(anchor.getAttribute("href") ?? "", window.location.href);
      if (
        destination.origin === window.location.origin &&
        destination.pathname === window.location.pathname &&
        destination.search === window.location.search &&
        destination.hash === window.location.hash
      ) {
        return;
      }
      if (!window.confirm(warning)) {
        event.preventDefault();
        event.stopPropagation();
      } else {
        event.preventDefault();
        event.stopPropagation();
        allowingNavigation = true;
        pendingDestination = destination.href;
        softphoneRef.current?.disconnectLocalAudio();
        window.history.back();
      }
    };
    const guardBrowserBack = () => {
      if (allowingNavigation) {
        if (pendingDestination) window.location.assign(pendingDestination);
        return;
      }
      if (!window.confirm(warning)) {
        window.history.pushState(guardState, "", window.location.href);
      } else {
        allowingNavigation = true;
        softphoneRef.current?.disconnectLocalAudio();
        window.history.back();
      }
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    window.addEventListener("popstate", guardBrowserBack, true);
    document.addEventListener("click", guardInternalNavigation, true);
    return () => {
      window.removeEventListener("beforeunload", warnBeforeUnload);
      window.removeEventListener("popstate", guardBrowserBack, true);
      document.removeEventListener("click", guardInternalNavigation, true);
      if (
        !allowingNavigation &&
        window.history.state?.[HISTORY_GUARD_STATE_KEY] === marker
      ) {
        window.history.back();
      }
    };
  }, [navigationProtectionRequired, protectedCallId]);

  const initializeHeadset = useCallback(async () => {
    const currentLease = leaseRef.current;
    if (!currentLease) throw new Error("Start or restore a dialer shift first.");
    const voiceSession = await apiRequest<ProspectingVoiceSession>(
      `/api/v1/prospecting/dialer/sessions/${currentLease.sessionId}/voice-session`,
      {
        method: "POST",
        body: {
          browser_session_id: currentLease.browserSessionId,
          lease_token: currentLease.leaseToken,
        },
      },
    );
    if (!voiceSession.can_initialize || !voiceSession.token) {
      throw new Error(voiceSession.blockers.join(" ") || "Browser Voice is not ready.");
    }
    if (voiceIdentityRef.current && voiceIdentityRef.current !== voiceSession.identity) {
      if (softphoneRef.current?.hasLiveAudio) {
        throw new Error("Finish the current call before changing the recovered headset identity.");
      }
      softphoneRef.current?.destroy();
      setSoftphoneStatus(INITIAL_SOFTPHONE_STATUS);
      identityStaleForNextCallRef.current = false;
    }
    voiceIdentityRef.current = voiceSession.identity;
    const softphone = softphoneRef.current;
    if (!softphone) throw new Error("The browser headset is unavailable.");
    await softphone.initialize(voiceSession.token);
    identityStaleForNextCallRef.current = false;
    setAudioLostAfterReload(false);
  }, [apiRequest]);

  const runExclusive = useCallback(async (name: string, operation: () => Promise<void>) => {
    if (actionRef.current) return actionRef.current;
    setBusyAction(name);
    setFailure(null);
    setNotice(null);
    const running = operation()
      .catch((error) => setFailure(errorMessage(error)))
      .finally(() => {
        actionRef.current = null;
        setBusyAction(null);
      });
    actionRef.current = running;
    return running;
  }, []);

  const ensureSession = useCallback(async () => {
    const currentLease = leaseRef.current;
    const currentSnapshot = snapshotRef.current;
    if (currentLease && currentSnapshot) return currentSnapshot;
    if (!selectedEntry) throw new Error("Select an assigned prospect first.");
    if (!selectedEntry.cohort_id) throw new Error("This prospect has no calling cohort.");
    const existingPending = readPendingStart(currentUserId);
    if (existingPending && existingPending.entryId !== selectedEntry.id) {
      throw new Error(
        "A prior shift start is awaiting recovery. Return to that selected prospect and retry.",
      );
    }
    const pending =
      existingPending ??
      ({
        userId: currentUserId,
        entryId: selectedEntry.id,
        campaignId: selectedEntry.campaign_id,
        cohortId: selectedEntry.cohort_id,
        callingBatchId: selectedEntry.batch_id,
        browserSessionId: crypto.randomUUID(),
        idempotencyKey: crypto.randomUUID(),
      } satisfies PendingDialerSessionStart);
    writePendingStart(currentUserId, pending);
    return beginOrReplaySession(pending);
  }, [beginOrReplaySession, currentUserId, selectedEntry]);

  const startOrRetry = useCallback(
    () =>
      runExclusive("calling", async () => {
        if (leadership !== "leader") throw new Error("This tab does not own the dialer.");
        const currentSnapshot = await ensureSession();
        const currentLease = leaseRef.current;
        const leg = currentSnapshot.current_leg;
        if (!currentLease || !leg) throw new Error("No eligible prospect was reserved.");
        if (leg.status !== "queued") {
          throw new Error("The current seller call has already started.");
        }
        await initializeHeadset();
        const prepared = await apiRequest<ProspectingVoiceCall>(
          `/api/v1/prospecting/dialer/legs/${leg.id}/browser-call`,
          {
            method: "POST",
            body: {
              browser_session_id: currentLease.browserSessionId,
              lease_token: currentLease.leaseToken,
              idempotency_key: `browser-call:${leg.id}`,
            },
          },
        );
        setActiveVoiceCall(prepared);
        applySnapshot({ session: currentSnapshot.session, current_leg: prepared.leg });
        if (prepared.provider_call_id || prepared.leg.status !== "queued") {
          setAudioLostAfterReload(true);
          throw new Error(
            "The provider call already started. Use the server call controls; Retry will not redial it.",
          );
        }
        try {
          const softphone = softphoneRef.current;
          if (!softphone) throw new Error("The browser headset is unavailable.");
          await softphone.connect(prepared.call_intent_id);
          setNotice("Browser audio is connecting. Seller status will update separately.");
        } catch (error) {
          const reconciled = await apiRequest<ProspectingVoiceCall>(
            `/api/v1/prospecting/dialer/legs/${leg.id}/call`,
          ).catch(() => null);
          if (reconciled) {
            setActiveVoiceCall(reconciled);
            applySnapshot({ session: currentSnapshot.session, current_leg: reconciled.leg });
          }
          throw error;
        }
      }),
    [
      apiRequest,
      applySnapshot,
      ensureSession,
      initializeHeadset,
      leadership,
      runExclusive,
      setActiveVoiceCall,
    ],
  );

  const sessionControl = useCallback(
    (action: "pause" | "resume") =>
      runExclusive(action, async () => {
        const currentLease = leaseRef.current;
        if (!currentLease) throw new Error("There is no active dialer shift.");
        const result = await apiRequest<ProspectingDialSessionControl>(
          `/api/v1/prospecting/dialer/sessions/${currentLease.sessionId}/${action}`,
          {
            method: "POST",
            body: {
              browser_session_id: currentLease.browserSessionId,
              lease_token: currentLease.leaseToken,
            },
          },
        );
        if (result.lease_token) {
          setActiveLease({ ...currentLease, leaseToken: result.lease_token });
        }
        applySnapshot(result.snapshot);
        setNotice(
          result.snapshot.session.pause_after_current
            ? "The shift will pause after this call is dispositioned."
            : action === "pause"
              ? "Calling paused."
              : "Calling resumed.",
        );
      }),
    [apiRequest, applySnapshot, runExclusive, setActiveLease],
  );

  const callControl = useCallback(
    (action: "cancel" | "hangup") =>
      runExclusive(action, async () => {
        const currentLease = leaseRef.current;
        const leg = snapshotRef.current?.current_leg;
        if (!currentLease || !leg || !leg.call_record_id) {
          throw new Error("There is no controlled seller call to end.");
        }
        const result = await apiRequest<ProspectingVoiceCall>(
          `/api/v1/prospecting/dialer/legs/${leg.id}/call/${action}`,
          {
            method: "POST",
            body: {
              browser_session_id: currentLease.browserSessionId,
              lease_token: currentLease.leaseToken,
              reason:
                action === "cancel"
                  ? "Operator stopped the seller phone before connection."
                  : "Operator ended the connected seller call.",
            },
          },
        );
        setActiveVoiceCall(result);
        softphoneRef.current?.disconnectLocalAudio();
        setAudioLostAfterReload(false);
        const currentSession = snapshotRef.current?.session;
        if (currentSession) applySnapshot({ session: currentSession, current_leg: result.leg });
        setNotice(action === "cancel" ? "Seller ringing stopped." : "Seller call ended.");
      }),
    [apiRequest, applySnapshot, runExclusive, setActiveVoiceCall],
  );

  const endShift = useCallback(
    () =>
      runExclusive("ending", async () => {
        const currentLease = leaseRef.current;
        if (!currentLease) throw new Error("There is no active dialer shift.");
        const leg = snapshotRef.current?.current_leg;
        let currentCall = voiceCallRef.current;
        if (leg?.call_record_id && !currentCall) {
          currentCall = await reconcileVoiceCall(leg.id);
        }
        if (currentCall && leg?.status === "queued" && !currentCall.provider_call_id) {
          const cancelled = await apiRequest<ProspectingVoiceCall>(
            `/api/v1/prospecting/dialer/legs/${leg.id}/call/cancel`,
            {
              method: "POST",
              body: {
                browser_session_id: currentLease.browserSessionId,
                lease_token: currentLease.leaseToken,
                reason: "Operator ended the shift before Twilio started the call.",
              },
            },
          );
          setActiveVoiceCall(cancelled);
          softphoneRef.current?.disconnectLocalAudio();
        }
        const result = await apiRequest<ProspectingDialSessionControl>(
          `/api/v1/prospecting/dialer/sessions/${currentLease.sessionId}/end`,
          {
            method: "POST",
            body: {
              browser_session_id: currentLease.browserSessionId,
              lease_token: currentLease.leaseToken,
              reason: "Operator ended the prospecting shift.",
            },
          },
        );
        applySnapshot(result.snapshot);
        setNotice(
          result.snapshot.session.stop_after_current
            ? "The shift will end after the current call is dispositioned."
            : "Shift ended.",
        );
      }),
    [apiRequest, applySnapshot, reconcileVoiceCall, runExclusive, setActiveVoiceCall],
  );

  const toggleMute = useCallback(
    () =>
      runExclusive("updating headset", async () => {
        const softphone = softphoneRef.current;
        if (!softphone?.hasLiveAudio) {
          throw new Error("Browser audio is no longer active.");
        }
        softphone.setMuted(!softphone.currentStatus.muted);
      }),
    [runExclusive],
  );

  const currentLeg = snapshot?.current_leg ?? null;
  const session = snapshot?.session ?? context?.active_session ?? null;
  const technicalFailure = Boolean(
    currentLeg &&
      (["failed", "cancelled"] as ProspectingDialLeg["status"][]).includes(
        currentLeg.status,
      ),
  );

  useEffect(() => {
    onRuntimeChange({
      sessionState: session?.state ?? null,
      legStatus: currentLeg?.status ?? null,
      terminalResult: currentLeg?.terminal_result ?? null,
      providerError: currentLeg?.provider_error_message ?? null,
      recipient: currentLeg?.recipient ?? null,
      technicalFailure,
      wrapUpReady: session?.state === "wrap_up",
    });
  }, [currentLeg, onRuntimeChange, session, technicalFailure]);

  useEffect(
    () => () => {
      onRuntimeChange({
        sessionState: null,
        legStatus: null,
        terminalResult: null,
        providerError: null,
        recipient: null,
        technicalFailure: false,
        wrapUpReady: false,
      });
    }, [onRuntimeChange],
  );
  const isLeader = leadership === "leader";
  const ownsSelectedEntry = selectedEntry?.assigned_user_id === currentUserId;
  const featureReady = isNativeDialerFeatureReady(context);
  const {
    canStart,
    canRetry,
    canPause,
    canResume,
    canStopRinging,
    canHangUp,
    canMute,
    canEndShift,
  } = dialerControlAvailability({
    leadership,
    featureReady,
    hasSelectedEntry: Boolean(selectedEntry && ownsSelectedEntry),
    busy: Boolean(busyAction),
    hasLease: Boolean(lease),
    session,
    leg: currentLeg,
    voiceCall,
    audioLink: softphoneStatus.audioLink,
  });
  const nativeModeOwnsStart = shouldNativeDialerOwnStart({
    context,
    leadership,
    featureReady,
    hasSession: Boolean(session),
    hasLease: Boolean(lease),
  });
  const controlHint = !isLeader
    ? leadership === "passive"
      ? "Call controls are read-only because another tab owns this dialer."
      : "Safe browser ownership is required before calling."
    : !featureReady
      ? "Native calling remains off; continue using BatchDialer."
      : busyAction
        ? `Finish the current action: ${busyAction}.`
        : currentLeg && TERMINAL_LEG_STATES.has(currentLeg.status)
          ? "Save the call disposition below before the next seller can be reserved."
          : session?.state === "paused" || session?.state === "reconnecting"
            ? "Resume the shift to continue."
            : audioLostAfterReload
              ? "Reloaded browser audio cannot reattach; use the available server call control."
              : "Start Calling prepares one durable seller call. No call starts automatically.";

  useEffect(() => {
    onNativeModeChange(nativeModeOwnsStart);
  }, [nativeModeOwnsStart, onNativeModeChange]);

  useEffect(() => {
    onOwnershipChange(leadership);
  }, [leadership, onOwnershipChange]);

  useEffect(
    () => () => {
      onNativeModeChange(false);
      onOwnershipChange("checking");
    },
    [onNativeModeChange, onOwnershipChange],
  );

  return (
    <section className={styles.dialerPanel} aria-labelledby="browser-dialer-title">
      <header>
        <div>
          <span>Native one-line dialer</span>
          <h3 id="browser-dialer-title">Browser calling controls</h3>
        </div>
        <strong className={featureReady ? styles.dialerReady : styles.dialerInactive}>
          {featureReady ? "Ready for controlled testing" : "Inactive"}
        </strong>
      </header>

      {leadership === "passive" ? (
        <div className={styles.dialerWarning} role="status">
          <ShieldAlert aria-hidden="true" size={18} />
          <p><strong>Dialer open in another tab.</strong> This tab is read-only so two calls cannot start.</p>
        </div>
      ) : null}
      {leadership === "unsupported" ? (
        <div className={styles.dialerWarning} role="status">
          <ShieldAlert aria-hidden="true" size={18} />
          <p><strong>Use a supported current browser.</strong> Safe single-tab ownership is unavailable here.</p>
        </div>
      ) : null}
      {context && !featureReady ? (
        <div className={styles.dialerInformation}>
          <p>
            BatchDialer remains the live calling path. Native browser calling stays off until its
            controlled acceptance and later rollout phases are approved.
          </p>
          {context.blockers.length ? <small>{context.blockers.join(" / ")}</small> : null}
        </div>
      ) : null}

      <div className={styles.dialerStates} aria-label="Call connection states">
        <div>
          <PhoneCall aria-hidden="true" size={18} />
          <span>Seller line</span>
          <strong>{sellerStateLabel(currentLeg)}</strong>
          <small>Verified by Stonegate and the Twilio seller leg</small>
        </div>
        <div>
          <Headphones aria-hidden="true" size={18} />
          <span>Browser audio</span>
          <strong>{audioStateLabel(softphoneStatus)}</strong>
          <small>
            {softphoneStatus.microphone === "granted"
              ? "Microphone allowed"
              : `Microphone: ${softphoneStatus.microphone}`}
          </small>
        </div>
        <div>
          <ShieldAlert aria-hidden="true" size={18} />
          <span>Shift</span>
          <strong>{session ? session.state.replaceAll("_", " ") : "Not started"}</strong>
          <small>One seller line maximum</small>
        </div>
      </div>

      {audioLostAfterReload && currentLeg && !TERMINAL_LEG_STATES.has(currentLeg.status) ? (
        <div className={styles.dialerWarning} role="status">
          <ShieldAlert aria-hidden="true" size={18} />
          <p>
            <strong>Durable call restored; browser audio did not reattach.</strong> Use Stop Ringing
            or Hang Up below. Reloading never starts another call automatically.
          </p>
        </div>
      ) : null}

      <div className={styles.dialerControls} aria-label="Browser calling controls">
        <button
          aria-describedby="browser-dialer-control-hint"
          className={styles.primaryButton}
          disabled={!canStart}
          onClick={() => void startOrRetry()}
          title={!featureReady ? "Native calling is not enabled." : undefined}
          type="button"
        >
          <PhoneCall aria-hidden="true" size={16} /> Start Calling
        </button>
        <button
          aria-describedby="browser-dialer-control-hint"
          disabled={!canRetry}
          onClick={() => void startOrRetry()}
          title="Retry the same prepared call; this never silently creates another intent."
          type="button"
        >
          <RefreshCw aria-hidden="true" size={16} /> Retry
        </button>
        <button
          aria-describedby="browser-dialer-control-hint"
          disabled={!canPause}
          onClick={() => void sessionControl("pause")}
          type="button"
        >
          <Pause aria-hidden="true" size={16} /> Pause
        </button>
        <button
          aria-describedby="browser-dialer-control-hint"
          disabled={!canResume}
          onClick={() => void sessionControl("resume")}
          type="button"
        >
          <Play aria-hidden="true" size={16} /> Resume
        </button>
        <button
          aria-describedby="browser-dialer-control-hint"
          disabled={!canStopRinging}
          onClick={() => void callControl("cancel")}
          type="button"
        >
          <PhoneOff aria-hidden="true" size={16} /> Stop Ringing
        </button>
        <button
          aria-pressed={softphoneStatus.muted}
          aria-describedby="browser-dialer-control-hint"
          disabled={!canMute}
          onClick={() => void toggleMute()}
          type="button"
        >
          {softphoneStatus.muted ? <MicOff aria-hidden="true" size={16} /> : <Mic aria-hidden="true" size={16} />}
          {softphoneStatus.muted ? "Unmute" : "Mute"}
        </button>
        <button
          aria-describedby="browser-dialer-control-hint"
          disabled={!canHangUp}
          onClick={() => void callControl("hangup")}
          type="button"
        >
          <PhoneOff aria-hidden="true" size={16} /> Hang Up
        </button>
        <button
          aria-describedby="browser-dialer-control-hint"
          className={styles.dangerButton}
          disabled={!canEndShift}
          onClick={() => void endShift()}
          type="button"
        >
          <Square aria-hidden="true" size={15} /> End Shift
        </button>
      </div>

      <p className={styles.dialerControlHint} id="browser-dialer-control-hint">
        {controlHint}
      </p>

      <div aria-atomic="true" aria-live="polite" className={styles.dialerStatus} role="status">
        {busyAction ? <span>Working: {busyAction}...</span> : null}
        {notice ? <span>{notice}</span> : null}
        {softphoneStatus.message ? <span>{softphoneStatus.message}</span> : null}
        {failure ? <strong>{failure}</strong> : null}
        {leaseWarning ? <strong>Dialer control: {leaseWarning}</strong> : null}
        {syncWarning ? <strong>Call status sync: {syncWarning}</strong> : null}
        {session?.pause_after_current ? <span>Pause queued after current disposition.</span> : null}
        {session?.stop_after_current ? <span>End Shift queued after current disposition.</span> : null}
      </div>
    </section>
  );
}
