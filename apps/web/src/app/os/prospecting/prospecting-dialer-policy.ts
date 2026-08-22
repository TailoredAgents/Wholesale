import type {
  ProspectingDialerContext,
  ProspectingDialLeg,
  ProspectingDialSession,
  ProspectingVoiceCall,
} from "../../lib/api";
import type { ProspectingSoftphoneStatus } from "./prospecting-softphone";

export type ProspectingDialerLeadership =
  | "checking"
  | "leader"
  | "passive"
  | "unsupported";

const RETRYABLE_AUDIO_STATES = new Set(["idle", "ready", "ended", "error"]);
const PRECONNECT_LEG_STATES = new Set(["queued", "dialing", "ringing", "cancelling"]);

export function isManualProspectingMode(context: ProspectingDialerContext | null) {
  return context?.feature_enabled === false;
}

export function isNativeDialerFeatureReady(context: ProspectingDialerContext | null) {
  return Boolean(
    context?.feature_enabled &&
      context.blockers.length === 0 &&
      context.effective_line_cap === 1 &&
      context.profile?.status === "active" &&
      context.profile.user_is_active &&
      context.profile.user_calling_enabled &&
      context.profile.effective_line_count === 1,
  );
}

export function shouldNativeDialerOwnStart({
  context,
  leadership,
  featureReady,
  hasSession,
  hasLease,
}: {
  context: ProspectingDialerContext | null;
  leadership: ProspectingDialerLeadership;
  featureReady: boolean;
  hasSession: boolean;
  hasLease: boolean;
}) {
  return Boolean(
    context === null || leadership !== "leader" || featureReady || hasSession || hasLease,
  );
}

export function shouldRecoverExpiredLease(status: number | undefined, message: string) {
  return status === 409 && message.toLowerCase().includes("expired");
}

export function shouldDiscardPendingMutation(status: number | undefined) {
  return Boolean(status && [400, 401, 403, 404, 405, 422].includes(status));
}

export function isPendingLeaseRecoveryForLease(
  pending: {
    userId: string;
    sessionId: string;
    previousBrowserSessionId: string;
    newBrowserSessionId: string;
  } | null,
  lease: {
    sessionId: string;
    browserSessionId: string;
  },
  userId: string,
) {
  return Boolean(
    pending &&
      pending.userId === userId &&
      pending.sessionId === lease.sessionId &&
      pending.previousBrowserSessionId === lease.browserSessionId &&
      pending.newBrowserSessionId !== lease.browserSessionId,
  );
}

export function shouldProtectNavigation(
  hasLease: boolean,
  leg: ProspectingDialLeg | null,
  terminalLegStates: ReadonlySet<string>,
) {
  return Boolean(hasLease && leg?.call_record_id && !terminalLegStates.has(leg.status));
}

export function dialerControlAvailability({
  leadership,
  featureReady,
  hasSelectedEntry,
  busy,
  hasLease,
  session,
  leg,
  voiceCall,
  audioLink,
}: {
  leadership: ProspectingDialerLeadership;
  featureReady: boolean;
  hasSelectedEntry: boolean;
  busy: boolean;
  hasLease: boolean;
  session: ProspectingDialSession | null;
  leg: ProspectingDialLeg | null;
  voiceCall: ProspectingVoiceCall | null;
  audioLink: ProspectingSoftphoneStatus["audioLink"];
}) {
  const isLeader = leadership === "leader";
  const retryablePreparedCall = Boolean(
    voiceCall &&
      !voiceCall.provider_call_id &&
      voiceCall.leg.status === "queued" &&
      RETRYABLE_AUDIO_STATES.has(audioLink),
  );
  return {
    canStart: Boolean(
      isLeader &&
        featureReady &&
        hasSelectedEntry &&
        !busy &&
        (!session || session.state === "ready") &&
        (!leg || leg.status === "queued") &&
        !voiceCall,
    ),
    canRetry: Boolean(
      isLeader &&
        featureReady &&
        !busy &&
        session?.state === "ready" &&
        retryablePreparedCall,
    ),
    canPause: Boolean(
      isLeader &&
        featureReady &&
        hasLease &&
        session &&
        !["paused", "reconnecting"].includes(session.state) &&
        !busy,
    ),
    canResume: Boolean(
      isLeader &&
        featureReady &&
        hasLease &&
        session &&
        ["paused", "reconnecting"].includes(session.state) &&
        !busy,
    ),
    canStopRinging: Boolean(
      isLeader &&
        hasLease &&
        leg?.call_record_id &&
        PRECONNECT_LEG_STATES.has(leg.status) &&
        !busy,
    ),
    canHangUp: Boolean(
      isLeader &&
        hasLease &&
        leg?.call_record_id &&
        ["answered", "connected"].includes(leg.status) &&
        !busy,
    ),
    canMute: Boolean(
      isLeader && ["audio_established", "reconnecting"].includes(audioLink) && !busy,
    ),
    canEndShift: Boolean(isLeader && hasLease && !busy),
  };
}
