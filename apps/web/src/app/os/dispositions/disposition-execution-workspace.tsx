"use client";

import {
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  Download,
  Headphones,
  Mail,
  MessageSquareText,
  Pause,
  PhoneCall,
  Play,
  RefreshCw,
  ShieldAlert,
  SkipForward,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import type {
  BuyerProfile,
  BuyerTimelineItem,
  DispositionExecutionCandidate,
  DispositionExecutionShowing,
  DispositionExecutionWorkspace,
  DispositionPackageShareLinkIssued,
} from "../../lib/api";
import { useWebPhone } from "../_components/web-phone-provider";
import { labelize } from "../os-utils";
import styles from "./disposition-execution-workspace.module.css";
import { DispositionQueueBuilder } from "./disposition-queue-builder";

type Requester = <T>(path: string, options?: RequestInit) => Promise<T>;
type VoiceCallIntent = {
  id: string;
  conversation_id: string;
  recipient: string;
  from_number: string;
  status: string;
  expires_at: string;
  recording_enabled: boolean;
};
type Outcome =
  | "interested"
  | "showing_scheduled"
  | "offer_expected"
  | "callback"
  | "no_answer"
  | "voicemail"
  | "not_interested"
  | "wrong_number"
  | "do_not_contact";
type SessionUpdate = {
  state?: "active" | "paused";
  current_buyer_id?: string | null;
  advance_to_next?: boolean;
  rerank_queue?: boolean;
  skipped_buyer_ids?: string[];
  buyer_id?: string;
  sms_draft?: string | null;
  email_subject?: string | null;
  email_draft?: string | null;
  email_sender_alias_id?: string | null;
  notes_draft?: string | null;
  callback_at?: string | null;
  selected_outcome?: Outcome | null;
  current_step?: "sms" | "call" | "email" | "outcome";
};
type EmailSenderAlias = {
  id: string;
  email_address: string;
  display_name: string;
  is_default: boolean;
  can_send: boolean;
};
type EmailConfiguration = {
  items: EmailSenderAlias[];
  provider: string;
  provider_configured: boolean;
  configuration_blockers: string[];
};
type EmailSendResult = {
  communication_id: string;
  provider_message_id: string;
  provider_thread_id: string;
  status: string;
  recipient: string;
};

const OUTCOMES: Array<{ value: Outcome; label: string; tone: "positive" | "neutral" | "negative" }> = [
  { value: "interested", label: "Interested", tone: "positive" },
  { value: "showing_scheduled", label: "Showing scheduled", tone: "positive" },
  { value: "offer_expected", label: "Offer expected", tone: "positive" },
  { value: "callback", label: "Callback", tone: "neutral" },
  { value: "no_answer", label: "No answer", tone: "neutral" },
  { value: "voicemail", label: "Voicemail", tone: "neutral" },
  { value: "not_interested", label: "Not interested", tone: "negative" },
  { value: "wrong_number", label: "Wrong number", tone: "negative" },
  { value: "do_not_contact", label: "Do not contact", tone: "negative" },
];

function idempotency(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}

function localDateTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : "Not scheduled";
}

function dateTimeLocalValue(value: string | null | undefined) {
  if (!value) return "";
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function executionCandidates(workspace: DispositionExecutionWorkspace | null) {
  if (!workspace) return [];
  if (workspace.candidates.length) return workspace.candidates;
  return workspace.current_candidate ? [workspace.current_candidate] : [];
}

function selectedCandidate(
  workspace: DispositionExecutionWorkspace | null,
  buyerId: string | null,
) {
  const candidates = executionCandidates(workspace);
  const explicitCandidate = buyerId
    ? candidates.find((candidate) => candidate.buyer_id === buyerId)
    : null;
  return explicitCandidate
    ?? (workspace?.current_candidate?.actionable ? workspace.current_candidate : null)
    ?? candidates.find((candidate) => candidate.actionable)
    ?? null;
}

function executionBuyerReference(candidate: DispositionExecutionCandidate) {
  return {
    buyer_id: candidate.buyer_id,
    ...(candidate.candidate_id ? { candidate_id: candidate.candidate_id } : {}),
  };
}

function hasRankedFit(
  candidate: DispositionExecutionCandidate,
): candidate is DispositionExecutionCandidate & { rank: number; score_basis_points: number } {
  return candidate.ranking_status === "ranked"
    && candidate.rank !== null
    && candidate.score_basis_points !== null;
}

function candidateRankLabel(candidate: DispositionExecutionCandidate) {
  return hasRankedFit(candidate) ? `#${candidate.rank}` : "Unranked";
}

function candidateFitLabel(candidate: DispositionExecutionCandidate) {
  return hasRankedFit(candidate)
    ? `${Math.round(candidate.score_basis_points / 100)}%`
    : "Buyer Network";
}

function isDoNotContact(candidate: DispositionExecutionCandidate) {
  return candidate.relationship_status === "do_not_contact"
    || candidate.action_blockers.some((blocker) => /do not contact|\bdnc\b/i.test(blocker));
}

function isPassedCandidate(candidate: DispositionExecutionCandidate) {
  return candidate.decision_status === "passed" || candidate.lifecycle_stage === "pass";
}

function candidateAvailabilityLabel(candidate: DispositionExecutionCandidate) {
  if (isDoNotContact(candidate)) return "Do not contact";
  if (isPassedCandidate(candidate)) return "Passed";
  return candidate.actionable ? "Available" : "Unavailable";
}

function nextActionableCandidate(
  candidates: DispositionExecutionCandidate[],
  currentBuyerId: string,
  skippedBuyerIds: Set<string>,
) {
  const currentIndex = candidates.findIndex((candidate) => candidate.buyer_id === currentBuyerId);
  const orderedCandidates = currentIndex >= 0
    ? [...candidates.slice(currentIndex + 1), ...candidates.slice(0, currentIndex)]
    : candidates;
  return orderedCandidates.find(
    (candidate) => candidate.actionable && !skippedBuyerIds.has(candidate.buyer_id),
  ) ?? null;
}

export function DispositionExecutionWorkspace({
  canEditBuyers,
  canEditDeals,
  caseId,
  downloadPackage,
  onMessage,
  onWorkspaceChanged,
  request,
}: {
  canEditBuyers: boolean;
  canEditDeals: boolean;
  caseId: string;
  downloadPackage: (path: string) => Promise<void>;
  onMessage: (message: string | null) => void;
  onWorkspaceChanged: () => Promise<unknown> | unknown;
  request: Requester;
}) {
  const [workspace, setWorkspace] = useState<DispositionExecutionWorkspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [smsDraft, setSmsDraft] = useState("");
  const [smsComposerOpen, setSmsComposerOpen] = useState(false);
  const [emailSubject, setEmailSubject] = useState("");
  const [emailDraft, setEmailDraft] = useState("");
  const [emailComposerOpen, setEmailComposerOpen] = useState(false);
  const [emailSenderAliases, setEmailSenderAliases] = useState<EmailSenderAlias[]>([]);
  const [emailSenderId, setEmailSenderId] = useState("");
  const [emailProviderConfigured, setEmailProviderConfigured] = useState<boolean | null>(null);
  const [emailConfigurationBlockers, setEmailConfigurationBlockers] = useState<string[]>([]);
  const [buyerTimeline, setBuyerTimeline] = useState<BuyerTimelineItem[]>([]);
  const [buyerTimelineLoading, setBuyerTimelineLoading] = useState(false);
  const [selectedBuyerId, setSelectedBuyerId] = useState<string | null>(null);
  const [callCountdown, setCallCountdown] = useState<number | null>(null);
  const [countdownBuyerId, setCountdownBuyerId] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [callbackAt, setCallbackAt] = useState("");
  const [selectedOutcome, setSelectedOutcome] = useState<Outcome | null>(null);
  const [savedOutcome, setSavedOutcome] = useState<{ buyerId: string; label: string } | null>(null);
  const [sessionPaused, setSessionPaused] = useState(false);
  const [sessionSkippedBuyerIds, setSessionSkippedBuyerIds] = useState<string[]>([]);
  const [sessionSaveState, setSessionSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const callCountdownTimer = useRef<number | null>(null);
  const buyerIdRef = useRef<string | null>(null);
  const emailIdempotencyKeyRef = useRef<string | null>(null);
  const webPhone = useWebPhone();
  const browserCallActive = webPhone.status.callActive;
  const browserCallActiveRef = useRef(browserCallActive);
  const [outcomeIdempotencyKey, setOutcomeIdempotencyKey] = useState(() =>
    idempotency("dispo-outcome"),
  );

  const applyWorkspace = useCallback((result: DispositionExecutionWorkspace) => {
    const candidates = executionCandidates(result);
    const persistedCandidate = result.session.current_buyer_id
      ? candidates.find(
        (candidate) => candidate.buyer_id === result.session.current_buyer_id,
      )
      : null;
    const nextCandidate = persistedCandidate
      ?? candidates.find(
        (candidate) => candidate.buyer_id === buyerIdRef.current && candidate.actionable,
      )
      ?? (result.current_candidate?.actionable ? result.current_candidate : null)
      ?? candidates.find((candidate) => candidate.actionable)
      ?? null;
    const nextBuyerId = nextCandidate?.buyer_id ?? null;
    const buyerState = nextBuyerId ? result.session.buyer_states[nextBuyerId] : null;
    const lastOutcomeIsWaiting = Boolean(
      nextBuyerId
      && result.session.last_outcome
      && result.session.last_outcome_buyer_id === nextBuyerId
      && result.current_candidate?.buyer_id !== nextBuyerId,
    );
    if (buyerIdRef.current !== nextBuyerId) {
      buyerIdRef.current = nextBuyerId;
      setOutcomeIdempotencyKey(idempotency("dispo-outcome"));
      setSmsComposerOpen(
        buyerState?.current_step === "sms" && buyerState.sms_status === "drafted",
      );
      setEmailComposerOpen(
        buyerState?.current_step === "email" && buyerState.email_status === "drafted",
      );
      setCallCountdown(null);
      setCountdownBuyerId(null);
      setNotes(buyerState?.notes_draft ?? "");
      setCallbackAt(dateTimeLocalValue(buyerState?.callback_at));
      setSelectedOutcome((buyerState?.selected_outcome as Outcome | null | undefined) ?? null);
      setSavedOutcome(lastOutcomeIsWaiting && result.session.last_outcome
        ? { buyerId: nextBuyerId!, label: labelize(result.session.last_outcome) }
        : null);
      setSmsDraft(nextCandidate?.sms_draft ?? "");
      setEmailSubject(nextCandidate?.email_subject ?? "");
      setEmailDraft(nextCandidate?.email_draft ?? "");
      setEmailSenderId(buyerState?.email_sender_alias_id ?? "");
      emailIdempotencyKeyRef.current = null;
      if (callCountdownTimer.current !== null) {
        window.clearInterval(callCountdownTimer.current);
        callCountdownTimer.current = null;
      }
    }
    setSessionPaused(result.session.state === "paused");
    setSessionSkippedBuyerIds(result.session.skipped_buyer_ids);
    setSessionSaveState(result.session.persisted ? "saved" : "idle");
    setSelectedBuyerId(nextBuyerId);
    setWorkspace(result);
  }, []);

  async function chooseCandidate(buyerId: string) {
    const nextCandidate = executionCandidates(workspace).find((candidate) => candidate.buyer_id === buyerId);
    if (!nextCandidate || buyerIdRef.current === buyerId) return;
    if (callCountdownTimer.current !== null) {
      window.clearInterval(callCountdownTimer.current);
      callCountdownTimer.current = null;
    }
    const result = await updateSession(
      {
        current_buyer_id: buyerId,
        skipped_buyer_ids: sessionSkippedBuyerIds.filter((item) => item !== buyerId),
        state: "active",
      },
      "session-cursor",
    );
    if (result) {
      onMessage(`Working ${nextCandidate.name}. This position will resume across visits.`);
    }
  }

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await request<DispositionExecutionWorkspace>(
        `/api/v1/dispositions/cases/${caseId}/execution`,
      );
      applyWorkspace(result);
    } catch (error) {
      onMessage(error instanceof Error ? error.message : "Disposition call queue could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [applyWorkspace, caseId, onMessage, request]);

  useEffect(() => {
    // Initial remote workspace synchronization is intentionally client-side.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const loadEmailConfiguration = useCallback(async () => {
    try {
      const result = await request<EmailConfiguration>("/api/v1/email/aliases");
      setEmailSenderAliases(result.items.filter((item) => item.can_send));
      setEmailProviderConfigured(result.provider_configured);
      setEmailConfigurationBlockers(result.configuration_blockers);
    } catch (error) {
      setEmailSenderAliases([]);
      setEmailProviderConfigured(false);
      setEmailConfigurationBlockers([
        error instanceof Error ? error.message : "Email sending is unavailable for this user.",
      ]);
    }
  }, [request]);

  useEffect(() => {
    // Email configuration is remote authorization state and must be synchronized client-side.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadEmailConfiguration();
  }, [loadEmailConfiguration]);

  useEffect(() => {
    if (!emailSenderAliases.length) return;
    const savedSenderIsAvailable = emailSenderAliases.some(
      (item) => item.id === emailSenderId,
    );
    if (savedSenderIsAvailable) return;
    const defaultSender = emailSenderAliases.find((item) => item.is_default)
      ?? emailSenderAliases[0];
    // Keep the server-authorized default in local composer state until the next draft save.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setEmailSenderId(defaultSender.id);
  }, [emailSenderAliases, emailSenderId]);

  const loadBuyerTimeline = useCallback(async (buyerId: string) => {
    setBuyerTimelineLoading(true);
    try {
      const result = await request<BuyerProfile>(
        `/api/v1/buyers/${buyerId}/profile?timeline_limit=12`,
      );
      if (buyerIdRef.current === buyerId) setBuyerTimeline(result.timeline.items);
    } catch {
      if (buyerIdRef.current === buyerId) setBuyerTimeline([]);
    } finally {
      if (buyerIdRef.current === buyerId) setBuyerTimelineLoading(false);
    }
  }, [request]);

  const activeTimelineBuyerId = selectedCandidate(workspace, selectedBuyerId)?.buyer_id ?? null;

  useEffect(() => {
    if (!activeTimelineBuyerId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setBuyerTimeline([]);
      return;
    }
    void loadBuyerTimeline(activeTimelineBuyerId);
  }, [activeTimelineBuyerId, loadBuyerTimeline]);

  async function refreshOutreachWorkspace() {
    await load();
    const buyerId = buyerIdRef.current;
    if (buyerId) await loadBuyerTimeline(buyerId);
    await loadEmailConfiguration();
  }

  async function refreshQueueBuilderWorkspace() {
    await load();
    const buyerId = buyerIdRef.current;
    if (buyerId) await loadBuyerTimeline(buyerId);
    try {
      await onWorkspaceChanged();
    } catch {
      // Queue changes are already durable; parent readiness can refresh independently.
    }
  }

  useEffect(() => {
    browserCallActiveRef.current = browserCallActive;
  }, [browserCallActive]);

  useEffect(() => {
    return () => {
      if (callCountdownTimer.current !== null) {
        window.clearInterval(callCountdownTimer.current);
      }
    };
  }, []);

  async function action<T>(key: string, operation: () => Promise<T>, success: string) {
    setBusy(key);
    onMessage(null);
    try {
      const result = await operation();
      try {
        await onWorkspaceChanged();
      } catch {
        // The local mutation succeeded; the parent readiness panel can be refreshed independently.
      }
      onMessage(success);
      return result;
    } catch (error) {
      onMessage(error instanceof Error ? error.message : "The disposition action failed.");
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function updateSession(payload: SessionUpdate, key = "session") {
    setBusy(key);
    setSessionSaveState("saving");
    try {
      const result = await request<DispositionExecutionWorkspace>(
        `/api/v1/dispositions/cases/${caseId}/execution/session`,
        {
          method: "PATCH",
          body: JSON.stringify(payload),
        },
      );
      applyWorkspace(result);
      setSessionSaveState("saved");
      return result;
    } catch (error) {
      setSessionSaveState("idle");
      onMessage(error instanceof Error ? error.message : "The outreach session could not be saved.");
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function saveCurrentBuyerState(overrides: Partial<SessionUpdate> = {}) {
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (!candidate || !canEditDeals) return null;
    setSessionSaveState("saving");
    try {
      const result = await request<DispositionExecutionWorkspace>(
        `/api/v1/dispositions/cases/${caseId}/execution/session`,
        {
          method: "PATCH",
          body: JSON.stringify({
            buyer_id: candidate.buyer_id,
            sms_draft: smsDraft,
            email_subject: emailSubject,
            email_draft: emailDraft,
            email_sender_alias_id: emailSenderId || null,
            notes_draft: notes,
            callback_at: callbackAt ? new Date(callbackAt).toISOString() : null,
            selected_outcome: selectedOutcome,
            current_step: "outcome",
            ...overrides,
          }),
        },
      );
      setWorkspace(result);
      setSessionPaused(result.session.state === "paused");
      setSessionSkippedBuyerIds(result.session.skipped_buyer_ids);
      setSessionSaveState("saved");
      return result;
    } catch (error) {
      setSessionSaveState("idle");
      onMessage(error instanceof Error ? error.message : "The investor draft could not be saved.");
      return null;
    }
  }

  async function refreshSessionSnapshot() {
    try {
      const result = await request<DispositionExecutionWorkspace>(
        `/api/v1/dispositions/cases/${caseId}/execution`,
      );
      setWorkspace(result);
      setSessionPaused(result.session.state === "paused");
      setSessionSkippedBuyerIds(result.session.skipped_buyer_ids);
      setSessionSaveState(result.session.persisted ? "saved" : "idle");
    } catch {
      // The completed outreach action remains canonical; the next refresh restores session state.
    }
  }

  async function discardCurrentSmsDraft() {
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (!candidate) return;
    const result = await saveCurrentBuyerState({ sms_draft: null, current_step: "sms" });
    if (!result) return;
    const restoredCandidate = executionCandidates(result).find(
      (item) => item.buyer_id === candidate.buyer_id,
    );
    setSmsDraft(restoredCandidate?.sms_draft ?? "");
    setSmsComposerOpen(false);
    onMessage(`The saved SMS draft for ${candidate.name} was discarded. A fresh deal-aware draft is available.`);
  }

  async function discardCurrentEmailDraft() {
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (!candidate) return;
    const result = await saveCurrentBuyerState({
      email_subject: null,
      email_draft: null,
      current_step: "email",
    });
    if (!result) return;
    const restoredCandidate = executionCandidates(result).find(
      (item) => item.buyer_id === candidate.buyer_id,
    );
    setEmailSubject(restoredCandidate?.email_subject ?? "");
    setEmailDraft(restoredCandidate?.email_draft ?? "");
    setEmailComposerOpen(false);
    emailIdempotencyKeyRef.current = null;
    onMessage(`The saved email draft for ${candidate.name} was discarded. A fresh deal-aware draft is available.`);
  }

  async function insertPacketLinkInEmail() {
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (!candidate || !workspace?.package_pdf_path || !canEditDeals) return;
    const issued = await action(
      "email-packet",
      () => request<DispositionPackageShareLinkIssued>(
        `/api/v1/dispositions/cases/${caseId}/package/share-links`,
        {
          method: "POST",
          body: JSON.stringify({ expires_in_hours: 72 }),
        },
      ),
      `A secure 72-hour investor packet link was created for ${candidate.name}.`,
    );
    if (!issued) return;
    const packetLabel = issued.is_preliminary ? "Preliminary investor packet" : "Investor packet";
    const nextDraft = `${emailDraft.trimEnd()}\n\n${packetLabel} (secure link expires in 72 hours):\n${issued.share_url}`.trim();
    setEmailDraft(nextDraft);
    emailIdempotencyKeyRef.current = null;
    await saveCurrentBuyerState({
      email_draft: nextDraft,
      current_step: "email",
    });
  }

  async function sendFollowUpEmail() {
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (
      !candidate
      || !candidate.actionable
      || !candidate.email
      || !canEditDeals
      || !emailProviderConfigured
      || !emailSenderId
    ) return;
    const subject = emailSubject.trim();
    const body = emailDraft.trim();
    if (!subject || !body) {
      onMessage("Review the email subject and message before sending it.");
      return;
    }
    const saved = await saveCurrentBuyerState({
      email_subject: subject,
      email_draft: body,
      email_sender_alias_id: emailSenderId,
      current_step: "email",
    });
    if (!saved) return;
    emailIdempotencyKeyRef.current ??= idempotency("dispo-email");
    const result = await action(
      "email",
      () => request<EmailSendResult>(
        `/api/v1/dispositions/cases/${caseId}/execution/email`,
        {
          method: "POST",
          body: JSON.stringify({
            ...executionBuyerReference(candidate),
            email_sender_alias_id: emailSenderId,
            subject,
            body,
            idempotency_key: emailIdempotencyKeyRef.current,
          }),
        },
      ),
      `Follow-up email accepted for ${candidate.name}.`,
    );
    if (!result) return;
    emailIdempotencyKeyRef.current = null;
    setEmailComposerOpen(false);
    await refreshSessionSnapshot();
    await loadBuyerTimeline(candidate.buyer_id);
    onMessage(`Follow-up email ${labelize(result.status)} for ${candidate.name}. Delivery and replies will appear in relationship activity.`);
  }

  async function sendSms() {
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (!candidate || !candidate.actionable || !canEditDeals || !candidate.sms.allowed) return;
    const body = smsDraft.trim();
    if (!body) {
      onMessage("Review the introduction and enter a message before sending it.");
      return;
    }
    await saveCurrentBuyerState({ sms_draft: body, current_step: "sms" });
    const result = await action(
      "sms",
      async () => {
        let headsetReady = false;
        if (candidate.voice.allowed && !browserCallActiveRef.current) {
          try {
            await webPhone.initializeHeadset();
            headsetReady = true;
          } catch {
            // The shared phone reports the exact microphone or configuration problem.
            // The reviewed text may still be sent and the cellphone fallback stays available.
          }
        }
        await request(`/api/v1/dispositions/cases/${caseId}/execution/sms`, {
          method: "POST",
          body: JSON.stringify({
            ...executionBuyerReference(candidate),
            body,
            idempotency_key: idempotency("dispo-sms"),
          }),
        });
        return { headsetReady };
      },
      `Introduction text accepted for ${candidate.name}.`,
    );
    if (!result) return;

    await refreshSessionSnapshot();
    await loadBuyerTimeline(candidate.buyer_id);
    setSmsComposerOpen(false);
    if (candidate.voice.allowed) {
      if (result.headsetReady) {
        beginCallCountdown(candidate.buyer_id);
        onMessage(`Introduction text accepted for ${candidate.name}. Browser call starts in 10 seconds unless you cancel.`);
      } else if (browserCallActiveRef.current) {
        onMessage(`Introduction text accepted for ${candidate.name}. Finish the current browser call before calling this buyer.`);
      } else {
        onMessage(`Introduction text accepted for ${candidate.name}. Browser audio is not ready; use the cellphone fallback if needed.`);
      }
    }
  }

  function beginCallCountdown(buyerId: string) {
    if (callCountdownTimer.current !== null) {
      window.clearInterval(callCountdownTimer.current);
    }
    let remaining = 10;
    setCountdownBuyerId(buyerId);
    setCallCountdown(remaining);
    callCountdownTimer.current = window.setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        if (callCountdownTimer.current !== null) {
          window.clearInterval(callCountdownTimer.current);
          callCountdownTimer.current = null;
        }
        setCallCountdown(null);
        void startBrowserCall(buyerId);
        return;
      }
      setCallCountdown(remaining);
    }, 1_000);
  }

  async function startBrowserCall(expectedBuyerId?: string) {
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (!candidate || !candidate.actionable || !canEditDeals || !candidate.voice.allowed) return;
    if (browserCallActiveRef.current) {
      setCallCountdown(null);
      setCountdownBuyerId(null);
      onMessage("End the current browser call before starting the next buyer call.");
      return;
    }
    if (
      (expectedBuyerId && expectedBuyerId !== candidate.buyer_id) ||
      (countdownBuyerId && countdownBuyerId !== candidate.buyer_id)
    ) {
      setCallCountdown(null);
      setCountdownBuyerId(null);
      return;
    }
    if (callCountdownTimer.current !== null) {
      window.clearInterval(callCountdownTimer.current);
      callCountdownTimer.current = null;
    }
    setCallCountdown(null);
    setCountdownBuyerId(null);
    const result = await action(
      "browser-call",
      async () => {
        const intent = await request<VoiceCallIntent>(
          `/api/v1/dispositions/cases/${caseId}/execution/calls`,
          {
            method: "POST",
            body: JSON.stringify({
              ...executionBuyerReference(candidate),
              idempotency_key: idempotency("dispo-browser-call"),
            }),
          },
        );
        await webPhone.startCall({
          callIntentId: intent.id,
          contextHref: `/os/deals?display=queue&tab=disposition&view=all&deal=${workspace?.deal_id ?? ""}`,
          contextLabel: workspace?.property_address ?? "Disposition call queue",
          displayName: candidate.name,
          fromNumber: intent.from_number,
          phoneNumber: intent.recipient,
        });
        return intent;
      },
      `Browser call started for ${candidate.name}.`,
    );
    if (result) {
      await refreshSessionSnapshot();
      await loadBuyerTimeline(candidate.buyer_id);
    }
  }

  async function startCellphoneCall() {
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (!candidate || !candidate.actionable || !canEditDeals || !candidate.voice.allowed) return;
    if (callCountdownTimer.current !== null) {
      window.clearInterval(callCountdownTimer.current);
      callCountdownTimer.current = null;
    }
    setCallCountdown(null);
    setCountdownBuyerId(null);
    const result = await action(
      "cellphone-call",
      async () => {
        const callKey = idempotency("dispo-cellphone-call");
        return request(
          `/api/v1/dispositions/cases/${caseId}/execution/forwarded-calls`,
          {
            method: "POST",
            body: JSON.stringify({
              ...executionBuyerReference(candidate),
              idempotency_key: callKey,
            }),
          },
        );
      },
      `Stonegate is calling your cellphone first, then connecting ${candidate.name}.`,
    );
    if (result) {
      await refreshSessionSnapshot();
      await loadBuyerTimeline(candidate.buyer_id);
    }
  }

  function cancelPreparedCall() {
    if (callCountdownTimer.current !== null) {
      window.clearInterval(callCountdownTimer.current);
      callCountdownTimer.current = null;
    }
    setCallCountdown(null);
    setCountdownBuyerId(null);
    onMessage("The automatic browser call was cancelled. The introduction text remains in the conversation history.");
  }

  async function sendApprovedPacket() {
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (!candidate || !candidate.actionable || !workspace?.package_pdf_path || !canEditDeals || !candidate.sms.allowed) return;
    const firstName = candidate.name.trim().split(/\s+/)[0] || "there";
    const result = await action(
      "packet-sms",
      async () => {
        const issued = await request<DispositionPackageShareLinkIssued>(
          `/api/v1/dispositions/cases/${caseId}/package/share-links`,
          {
            method: "POST",
            body: JSON.stringify({ expires_in_hours: 72 }),
          },
        );
        const issuedPackageLabel = issued.is_preliminary ? "preliminary" : "approved";
        await request(`/api/v1/dispositions/cases/${caseId}/execution/sms`, {
          method: "POST",
          body: JSON.stringify({
            ...executionBuyerReference(candidate),
            body: `Hey ${firstName}, here is the ${issuedPackageLabel} property package for ${workspace.property_address}: ${issued.share_url}`,
            idempotency_key: idempotency("dispo-packet-sms"),
          }),
        });
        return issued;
      },
      `Investor packet text accepted for ${candidate.name}. The secure link expires in 72 hours. If delivery is ever uncertain, check the buyer conversation before retrying.`,
    );
    if (result) {
      const issuedPackageLabel = result.is_preliminary ? "Preliminary" : "Approved";
      onMessage(`${issuedPackageLabel} investor packet text accepted for ${candidate.name}. The secure link expires in 72 hours. If delivery is ever uncertain, check the buyer conversation before retrying.`);
      await load();
      await loadBuyerTimeline(candidate.buyer_id);
    }
  }

  async function recordOutcome(outcome: Outcome, advance: "next" | "stay") {
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (!candidate || !candidate.actionable || !canEditDeals) return;
    if (outcome === "callback" && !callbackAt) {
      onMessage("Choose the requested callback date and time first.");
      return;
    }
    await saveCurrentBuyerState({
      selected_outcome: outcome,
      current_step: "outcome",
    });
    const result = await action(
      `outcome-${outcome}`,
      () => request<DispositionExecutionWorkspace>(
        `/api/v1/dispositions/cases/${caseId}/execution/outcomes`,
        {
          method: "POST",
          body: JSON.stringify({
            ...executionBuyerReference(candidate),
            outcome,
            notes: notes.trim() || null,
            follow_up_at: outcome === "callback" ? new Date(callbackAt).toISOString() : null,
            idempotency_key: outcomeIdempotencyKey,
          }),
        },
      ),
      advance === "next"
        ? `${labelize(outcome)} saved for ${candidate.name}. Moving to the next available investor.`
        : `${labelize(outcome)} saved for ${candidate.name}. Staying on this investor until you choose what is next.`,
    );
    if (result) {
      await loadBuyerTimeline(candidate.buyer_id);
      if (advance === "next") {
        const advanced = await updateSession(
          { advance_to_next: true, state: "active" },
          "session-advance",
        );
        if (!advanced) {
          setWorkspace(result);
          setSavedOutcome({ buyerId: candidate.buyer_id, label: labelize(outcome) });
        } else if (advanced.session.current_buyer_id === candidate.buyer_id) {
          onMessage(`${labelize(outcome)} saved for ${candidate.name}. No other unskipped investor is currently available.`);
        } else {
          onMessage(`${labelize(outcome)} saved. The next investor and queue position are saved.`);
        }
      } else {
        setWorkspace(result);
        setSessionSaveState("saved");
        setSavedOutcome({ buyerId: candidate.buyer_id, label: labelize(outcome) });
      }
    }
  }

  async function continueToNextBuyer() {
    if (!workspace || !savedOutcome) return;
    const result = await updateSession(
      { advance_to_next: true, state: "active" },
      "session-advance",
    );
    if (result) {
      onMessage(result.session.current_buyer_id === savedOutcome.buyerId
        ? "No other unskipped investor is currently available. This completed position remains saved."
        : "Moved to the next available investor. Your new position is saved.");
    }
  }

  async function skipCurrentBuyer() {
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (!candidate || !workspace) return;
    const skippedBuyerIds = new Set([...sessionSkippedBuyerIds, candidate.buyer_id]);
    const result = await updateSession(
      {
        skipped_buyer_ids: [...skippedBuyerIds],
        advance_to_next: true,
      },
      "session-skip",
    );
    if (result) {
      onMessage(result.session.current_buyer_id === candidate.buyer_id
        ? `${candidate.name} is saved as skipped, but no other investor is currently available. No buyer outcome was changed.`
        : `${candidate.name} was skipped and the saved session moved forward. No buyer outcome was changed.`);
    }
  }

  async function pauseSession() {
    if (callCountdownTimer.current !== null) {
      window.clearInterval(callCountdownTimer.current);
      callCountdownTimer.current = null;
    }
    setCallCountdown(null);
    setCountdownBuyerId(null);
    const result = await updateSession(
      {
        state: "paused",
        current_buyer_id: buyerIdRef.current,
        skipped_buyer_ids: sessionSkippedBuyerIds,
      },
      "session-pause",
    );
    if (result) onMessage("Outreach is paused and saved. You can resume this exact investor after leaving or logging back in.");
  }

  async function resumeSession() {
    const result = await updateSession({ state: "active" }, "session-resume");
    if (result) onMessage("Outreach resumed at the saved investor and unfinished step.");
  }

  async function createShowing(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (!candidate || !candidate.actionable || !canEditDeals) return;
    const form = new FormData(event.currentTarget);
    const scheduledAt = String(form.get("scheduled_at") ?? "");
    if (!scheduledAt) {
      onMessage("Choose the showing date and time.");
      return;
    }
    const result = await action(
      "showing",
      () => request<DispositionExecutionWorkspace>(
        `/api/v1/dispositions/cases/${caseId}/execution/showings`,
        {
          method: "POST",
          body: JSON.stringify({
            ...executionBuyerReference(candidate),
            scheduled_at: new Date(scheduledAt).toISOString(),
            access_status: String(form.get("access_status") ?? "pending"),
            notes: String(form.get("showing_notes") ?? "").trim() || null,
            idempotency_key: `dispo-showing-${candidate.buyer_id}-${new Date(scheduledAt).toISOString()}`,
          }),
        },
      ),
      `Showing scheduled with ${candidate.name}. Record the call outcome when the conversation ends.`,
    );
    if (result) {
      applyWorkspace(result);
      await loadBuyerTimeline(candidate.buyer_id);
    }
  }

  async function clearPass() {
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (
      !candidate
      || !isPassedCandidate(candidate)
      || isDoNotContact(candidate)
      || !candidate.candidate_id
      || candidate.lock_version === null
      || !canEditDeals
    ) return;
    const result = await action(
      "clear-pass",
      () => request(
        `/api/v1/dispositions/cases/${caseId}/buyer-pool/candidates/${candidate.candidate_id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            expected_version: candidate.lock_version,
            decision_status: "undecided",
            reason: "Reopened from one-to-one execution.",
          }),
        },
      ),
      `${candidate.name} is available for one-to-one execution again.`,
    );
    if (result !== null) await load();
  }

  async function updateShowing(
    showing: DispositionExecutionShowing,
    status: DispositionExecutionShowing["status"],
    accessStatus: DispositionExecutionShowing["access_status"],
  ) {
    const result = await action(
      `showing-${showing.id}`,
      () => request<DispositionExecutionWorkspace>(
        `/api/v1/dispositions/cases/${caseId}/execution/showings/${showing.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            status,
            access_status: accessStatus,
            scheduled_at: showing.scheduled_at,
            notes: showing.notes,
          }),
        },
      ),
      status === "completed"
        ? "Showing completed. A follow-up task is due in 24 hours."
        : `Showing marked ${labelize(status)}.`,
    );
    if (result) {
      applyWorkspace(result);
      await loadBuyerTimeline(showing.buyer_id);
    }
  }

  if (loading) {
    return <section className={styles.panel}><p className={styles.empty}>Loading the disposition call queue…</p></section>;
  }
  if (!workspace) return null;

  const candidates = executionCandidates(workspace);
  const candidate = selectedCandidate(workspace, selectedBuyerId);
  const outcomeSavedForCurrent = Boolean(
    candidate && savedOutcome?.buyerId === candidate.buyer_id,
  );
  const roleOrBusyDisabled = busy !== null
    || !canEditDeals
    || !candidate?.actionable
    || sessionPaused
    || outcomeSavedForCurrent;
  const smsUnavailable = roleOrBusyDisabled || !candidate?.sms.allowed;
  const voiceUnavailable = roleOrBusyDisabled || !candidate?.voice.allowed || webPhone.busy || browserCallActive;
  const emailUnavailable = busy !== null
    || !canEditDeals
    || !candidate?.actionable
    || !candidate.email
    || sessionPaused
    || !emailProviderConfigured
    || !emailSenderId;
  const packetUnavailable = smsUnavailable || !workspace.package_pdf_path;
  const packageIsPreliminary = workspace.package_is_preliminary
    ?? workspace.package_status !== "approved";
  const packageLabel = packageIsPreliminary ? "preliminary" : "approved";
  const queuePosition = candidate
    ? candidates.findIndex((item) => item.buyer_id === candidate.buyer_id) + 1
    : 0;
  const contactedStages = new Set([
    "contacted", "interested", "showing", "offer", "selected", "backup", "pass", "fallout",
  ]);
  const interestedStages = new Set(["interested", "showing", "offer", "selected", "backup"]);
  const contactedCount = candidates.filter((item) => contactedStages.has(item.lifecycle_stage)).length;
  const interestedCount = candidates.filter((item) => interestedStages.has(item.lifecycle_stage)).length;
  const skippedBuyerIds = new Set(sessionSkippedBuyerIds);
  const serverRecommendedCandidate = workspace.current_candidate
    && workspace.current_candidate.buyer_id !== candidate?.buyer_id
    && !skippedBuyerIds.has(workspace.current_candidate.buyer_id)
    ? workspace.current_candidate
    : null;
  const nextCandidate = serverRecommendedCandidate ?? (candidate
    ? nextActionableCandidate(candidates, candidate.buyer_id, skippedBuyerIds)
    : null);
  const buyerProgress = candidate
    ? workspace.session.buyer_states[candidate.buyer_id]
    : null;
  const currentStep = buyerProgress?.current_step ?? "sms";
  const outcomeNeedsCallback = selectedOutcome === "callback" && !callbackAt;
  const emailHasPacketLink = emailDraft.includes("/api/v1/public/investor-packages/");
  const visibleBuyerTimeline = buyerTimeline.filter(
    (item) => item.category !== "relationship" || !["sms", "email"].includes(item.event_type),
  ).slice(0, 6);
  const inboundReplyCount = buyerTimeline.filter(
    (item) => item.category === "communication" && item.direction === "inbound",
  ).length;

  return (
    <section aria-label="Disposition call queue" className={styles.workspace} id="call-queue" tabIndex={-1}>
      <header className={styles.hero}>
        <div>
          <span>One-to-one investor outreach</span>
          <h3>Outreach session</h3>
          <p>Your investor, drafts, progress, and queue position now resume across visits.</p>
        </div>
        <div className={styles.heroActions}>
          <div><strong>{queuePosition || "–"}</strong><span>of {candidates.length || 0}</span><small>queue position</small></div>
          {workspace.package_pdf_path ? <button className={styles.secondary} disabled={busy !== null} onClick={() => void downloadPackage(workspace.package_pdf_path!)} type="button"><Download size={15} />Open {packageLabel} packet</button> : null}
          <button aria-label="Refresh disposition call queue" className={styles.secondary} disabled={busy !== null || loading} onClick={() => void refreshOutreachWorkspace()} type="button"><RefreshCw size={15} />Refresh</button>
          <span className={styles.sessionSave} data-saving={sessionSaveState === "saving"}>{sessionSaveState === "saving" ? "Saving session…" : workspace.session.persisted ? `Saved · ${labelize(currentStep)}` : "Ready to save"}</span>
          {sessionPaused
            ? <button onClick={() => void resumeSession()} type="button"><Play size={15} />Resume session</button>
            : <button className={styles.secondary} disabled={busy !== null} onClick={() => void pauseSession()} type="button"><Pause size={15} />Pause session</button>}
        </div>
      </header>

      {sessionPaused ? <div className={styles.pausedBanner} role="status"><Pause size={18} /><div><strong>Session paused at {candidate?.name ?? "the current queue position"}</strong><span>Your investor, drafts, skipped list, and unfinished step are saved across visits.</span></div><button onClick={() => void resumeSession()} type="button"><Play size={15} />Resume</button></div> : null}

      {workspace.blockers.length ? (
        <details className={styles.advisoryDetails}>
          <summary><ShieldAlert size={16} />Advisory deal checklist <strong>{workspace.blockers.length}</strong></summary>
          <div>{workspace.blockers.map((item) => <span key={item}>{item}</span>)}<small>These items do not prevent work. Contact controls still follow each investor&apos;s live channel permissions.</small></div>
        </details>
      ) : null}

      <DispositionQueueBuilder
        assetClass={workspace.asset_class}
        canEditBuyers={canEditBuyers}
        canEditDeals={canEditDeals}
        caseId={caseId}
        onMessage={onMessage}
        onQueueChanged={refreshQueueBuilderWorkspace}
        request={request}
      />

      {candidate ? (
        <div className={styles.outreachLayout}>
          <div className={styles.currentInvestor}>
            <section className={`${styles.panel} ${styles.investorOverview}`}>
              <div className={styles.candidateHeader}>
                <div className={styles.rank} data-ranked={hasRankedFit(candidate)}>{candidateRankLabel(candidate)}</div>
                <div><span>Current investor</span><h4>{candidate.name}</h4><p>{candidate.company_name ?? "Independent investor"}</p></div>
                <div className={styles.score} data-ranked={hasRankedFit(candidate)}><strong>{candidateFitLabel(candidate)}</strong><span>{hasRankedFit(candidate) ? "fit score" : "Unranked"}</span></div>
              </div>
              {!candidate.actionable ? <div className={styles.candidateState} data-dnc={isDoNotContact(candidate)}><strong>{outcomeSavedForCurrent ? `${savedOutcome?.label} saved` : candidateAvailabilityLabel(candidate)}</strong><span>{outcomeSavedForCurrent ? "The result is recorded. Stay here or continue to the next investor when ready." : candidate.action_blockers.join(" ") || "This investor is not currently actionable."}</span></div> : null}
              <dl className={styles.profile}>
                <div><dt>Phone</dt><dd>{candidate.phone ?? "Not recorded"}</dd></div>
                <div><dt>Email</dt><dd>{candidate.email ?? "Not recorded"}</dd></div>
                <div><dt>Relationship</dt><dd>{labelize(candidate.relationship_status ?? "unknown")}</dd></div>
                <div><dt>Nearby purchase</dt><dd>{candidate.recent_purchase_reference ?? "No address-level reference saved"}</dd></div>
              </dl>
              <details className={styles.fitEvidence}>
                <summary>{hasRankedFit(candidate) ? "Why this investor ranks here" : "Buyer Network / Unranked"}</summary>
                <div className={styles.evidence}>{hasRankedFit(candidate)
                  ? candidate.score_explanation.slice(0, 5).map((item) => <p key={item}><CheckCircle2 size={14} />{item}</p>)
                  : <p><UserRound size={14} />This canonical Buyer Network record has not been scored by a ranking run. No rank or fit score is implied.</p>}</div>
              </details>
              <div className={styles.investorUtilities}>
                <Link href={`/os/buyers?buyer=${encodeURIComponent(candidate.buyer_id)}`}>Open relationship profile <ArrowRight size={14} /></Link>
                {isPassedCandidate(candidate) && !isDoNotContact(candidate) && candidate.candidate_id && candidate.lock_version !== null ? <button className={styles.secondary} disabled={busy !== null || !canEditDeals} onClick={() => void clearPass()} type="button">{busy === "clear-pass" ? "Clearing pass…" : "Clear pass"}</button> : null}
              </div>
            </section>

            <section className={`${styles.panel} ${styles.cadencePanel}`}>
              <div className={styles.sectionTitle}><MessageSquareText size={18} /><div><span>Investor cadence</span><h4>Text, call, then follow up</h4></div></div>
              <ol className={styles.cadenceSteps}>
                <li data-ready={candidate.actionable && candidate.sms.allowed}><span>1</span><div><strong>SMS</strong><small>{buyerProgress?.sms_status === "sent" ? "Sent · saved" : buyerProgress?.sms_status === "drafted" ? "Draft saved" : candidate.sms.allowed ? "Ready to review" : "Unavailable"}</small></div></li>
                <li data-ready={candidate.actionable && candidate.voice.allowed}><span>2</span><div><strong>Call</strong><small>{buyerProgress?.call_status === "completed" ? "Result saved" : buyerProgress?.call_status === "started" ? "Started · saved" : candidate.voice.allowed ? "Browser or cellphone" : "Unavailable"}</small></div></li>
                <li data-ready={Boolean(candidate.email && emailProviderConfigured && emailSenderId)}><span>3</span><div><strong>Email</strong><small>{buyerProgress?.email_status === "sent" ? "Sent · saved" : buyerProgress?.email_status === "drafted" ? "Draft saved" : candidate.email ? emailProviderConfigured === null ? "Checking sender…" : emailProviderConfigured ? "Ready to review" : "Sender unavailable" : "No email recorded"}</small></div></li>
              </ol>

              <div className={styles.channelSection}>
                <div className={styles.sectionTitle}><MessageSquareText size={17} /><div><span>Step 1</span><h4>Review the introduction SMS</h4></div></div>
                <p className={styles.help}>Nothing sends automatically. Personalize the draft and confirm the final message.</p>
                <PermissionLine allowed={candidate.actionable && candidate.sms.allowed} blockers={[...candidate.action_blockers, ...candidate.sms.blockers]} channel="SMS" status={candidate.sms.status} />

                {!smsComposerOpen ? (
                  <button disabled={smsUnavailable} onClick={() => setSmsComposerOpen(true)} type="button"><MessageSquareText size={16} />Review introduction SMS</button>
                ) : (
                  <div className={styles.smsComposer}>
                    <div className={styles.messageContext}>
                      <div><span>Recipient</span><strong>{candidate.name}</strong><small>{candidate.phone ?? "No phone recorded"}</small></div>
                      <div><span>Property</span><strong>{workspace.property_address}</strong><small>{hasRankedFit(candidate) ? `Ranked investor ${candidateRankLabel(candidate)}` : "Buyer Network / Unranked"}</small></div>
                    </div>
                    <label><span>Editable message</span><textarea aria-label="Introduction SMS draft" onBlur={() => void saveCurrentBuyerState({ current_step: "sms" })} onChange={(event) => { setSmsDraft(event.target.value); setSessionSaveState("idle"); }} rows={5} value={smsDraft} /></label>
                    <small className={styles.characterCount}>{smsDraft.trim().length} characters</small>
                    <div className={styles.composerActions}>
                      <button className={styles.secondary} disabled={busy === "sms"} onClick={() => void discardCurrentSmsDraft()} onMouseDown={(event) => event.preventDefault()} type="button">Discard saved draft</button>
                      <button className={styles.secondary} disabled={busy === "sms"} onClick={() => setSmsComposerOpen(false)} type="button">Close draft</button>
                      <button disabled={smsUnavailable || !smsDraft.trim()} onClick={() => void sendSms()} type="button"><MessageSquareText size={16} />{busy === "sms" ? "Sending…" : "Send SMS and prepare call"}</button>
                    </div>
                  </div>
                )}

                {callCountdown !== null && countdownBuyerId === candidate.buyer_id ? (
                  <div aria-live="polite" className={styles.callCountdown} role="status">
                    <div className={styles.countdownNumber}>{callCountdown}</div>
                    <div><strong>Introduction accepted</strong><span>Calling {candidate.name} in {callCountdown} second{callCountdown === 1 ? "" : "s"}.</span></div>
                    <div className={styles.countdownActions}><button disabled={voiceUnavailable} onClick={() => void startBrowserCall()} type="button">Call now</button><button className={styles.secondary} disabled={busy !== null} onClick={cancelPreparedCall} type="button">Cancel</button></div>
                  </div>
                ) : null}
              </div>

              <div className={styles.channelSection}>
                <div className={styles.sectionTitle}><Headphones size={17} /><div><span>Step 2</span><h4>Call from the Stonegate line</h4></div></div>
                <PermissionLine allowed={candidate.actionable && candidate.voice.allowed} blockers={[...candidate.action_blockers, ...candidate.voice.blockers]} channel="Call" status={candidate.voice.status} />
                <div className={styles.callActions}>
                  <button disabled={voiceUnavailable} onClick={() => void startBrowserCall()} type="button"><Headphones size={16} />{busy === "browser-call" || webPhone.busy ? "Starting browser call…" : browserCallActive ? "Browser call in progress" : `Call ${candidate.name} in browser`}</button>
                  <button className={styles.secondary} disabled={voiceUnavailable} onClick={() => void startCellphoneCall()} type="button"><PhoneCall size={16} />{busy === "cellphone-call" ? "Calling your cellphone…" : "Use my cellphone"}</button>
                </div>
              </div>

              <div className={styles.channelSection}>
                <div className={styles.sectionTitle}><Mail size={17} /><div><span>Step 3</span><h4>Email follow-up</h4></div></div>
                <p className={styles.help}>{candidate.email ? `Review the deal-aware starting draft for ${candidate.email}. Nothing sends until you approve it.` : "Add an email to the relationship profile before sending follow-up."}</p>
                {emailProviderConfigured === false ? <div className={styles.permissionBlocked}><span>Email sender unavailable</span><small>{emailConfigurationBlockers.join(" ") || "Configure an authorized Stonegate sender."}</small></div> : null}
                {emailProviderConfigured === true && !emailSenderAliases.length ? <div className={styles.permissionBlocked}><span>No authorized email sender</span><small>Ask an email administrator to grant this user access to an active Stonegate sender.</small></div> : null}
                <div className={styles.packetActions}>
                  <button className={styles.secondary} disabled={packetUnavailable} onClick={() => void sendApprovedPacket()} type="button"><MessageSquareText size={16} />{busy === "packet-sms" ? "Sending packet…" : `Text ${packageLabel} packet now`}</button>
                  {!emailComposerOpen ? <button disabled={emailUnavailable} onClick={() => setEmailComposerOpen(true)} type="button"><Mail size={16} />{buyerProgress?.email_status === "sent" ? "Review another email" : "Review follow-up email"}</button> : null}
                </div>
                {emailComposerOpen ? (
                  <div className={`${styles.smsComposer} ${styles.emailComposer}`}>
                    <div className={styles.messageContext}>
                      <div><span>Recipient</span><strong>{candidate.name}</strong><small>{candidate.email}</small></div>
                      <div><span>Property</span><strong>{workspace.property_address}</strong><small>{emailHasPacketLink ? "Secure packet link included" : "Packet link optional"}</small></div>
                    </div>
                    <label><span>Stonegate sender</span><select disabled={emailUnavailable} onBlur={() => void saveCurrentBuyerState({ current_step: "email" })} onChange={(event) => { setEmailSenderId(event.target.value); setSessionSaveState("idle"); emailIdempotencyKeyRef.current = null; }} value={emailSenderId}><option value="">Select sender</option>{emailSenderAliases.map((sender) => <option key={sender.id} value={sender.id}>{sender.display_name} · {sender.email_address}</option>)}</select></label>
                    <label><span>Subject</span><input onBlur={() => void saveCurrentBuyerState({ current_step: "email" })} onChange={(event) => { setEmailSubject(event.target.value); setSessionSaveState("idle"); emailIdempotencyKeyRef.current = null; }} value={emailSubject} /></label>
                    <label><span>Editable message</span><textarea aria-label="Investor follow-up email draft" onBlur={() => void saveCurrentBuyerState({ current_step: "email" })} onChange={(event) => { setEmailDraft(event.target.value); setSessionSaveState("idle"); emailIdempotencyKeyRef.current = null; }} rows={9} value={emailDraft} /></label>
                    <small className={styles.characterCount}>{emailDraft.trim().length} characters · Deal-aware starting draft, not an automatic send</small>
                    <div className={styles.composerActions}>
                      <button className={styles.secondary} disabled={busy !== null || !workspace.package_pdf_path || emailHasPacketLink} onClick={() => void insertPacketLinkInEmail()} type="button"><Download size={15} />{emailHasPacketLink ? "Packet link included" : `Insert ${packageLabel} packet link`}</button>
                      <button className={styles.secondary} disabled={busy === "email"} onClick={() => void discardCurrentEmailDraft()} onMouseDown={(event) => event.preventDefault()} type="button">Discard saved draft</button>
                      <button className={styles.secondary} disabled={busy === "email"} onClick={() => setEmailComposerOpen(false)} type="button">Close draft</button>
                      <button disabled={emailUnavailable || !emailSubject.trim() || !emailDraft.trim()} onClick={() => void sendFollowUpEmail()} type="button"><Mail size={16} />{busy === "email" ? "Sending…" : "Send email"}</button>
                    </div>
                  </div>
                ) : null}
              </div>
            </section>

            <section className={`${styles.panel} ${styles.outcomePanel}`}>
              <div className={styles.sectionTitle}><SkipForward size={18} /><div><span>Record result</span><h4>Choose the outcome, then choose what happens next</h4></div></div>
              <div className={styles.outcomeInputs}>
                <label><span>Call notes</span><textarea disabled={outcomeSavedForCurrent || sessionPaused} onBlur={() => void saveCurrentBuyerState({ current_step: "outcome" })} onChange={(event) => { setNotes(event.target.value); setSessionSaveState("idle"); }} placeholder="Interest, buy box, objections, requested next step…" rows={3} value={notes} /></label>
                <label><span>Callback time</span><input disabled={outcomeSavedForCurrent || sessionPaused} onBlur={() => void saveCurrentBuyerState({ current_step: "outcome" })} onChange={(event) => { setCallbackAt(event.target.value); setSessionSaveState("idle"); }} type="datetime-local" value={callbackAt} /><small>Required for Callback. No answer creates a 4-hour retry; voicemail creates a 24-hour follow-up.</small></label>
              </div>
              <div className={styles.outcomes}>{OUTCOMES.map((outcome) => <button aria-pressed={selectedOutcome === outcome.value} data-selected={selectedOutcome === outcome.value} data-tone={outcome.tone} disabled={roleOrBusyDisabled} key={outcome.value} onClick={() => { setSelectedOutcome(outcome.value); void saveCurrentBuyerState({ selected_outcome: outcome.value, current_step: "outcome" }); }} type="button">{outcome.label}</button>)}</div>
              {outcomeSavedForCurrent ? (
                <div className={styles.savedOutcome} role="status"><CheckCircle2 size={18} /><div><strong>{savedOutcome?.label} saved</strong><span>You are still on {candidate.name}. This exact position will resume until you continue.</span></div><button onClick={() => void continueToNextBuyer()} type="button">Next investor <ArrowRight size={15} /></button></div>
              ) : (
                <div className={styles.outcomeActions}>
                  <button className={styles.secondary} disabled={roleOrBusyDisabled || !callbackAt} onClick={() => { setSelectedOutcome("callback"); void recordOutcome("callback", "stay"); }} type="button"><CalendarClock size={15} />Schedule follow-up</button>
                  <button className={styles.secondary} disabled={busy !== null || sessionPaused} onClick={() => void skipCurrentBuyer()} type="button"><SkipForward size={15} />Skip for now</button>
                  <span />
                  <button className={styles.secondary} disabled={roleOrBusyDisabled || !selectedOutcome || outcomeNeedsCallback} onClick={() => selectedOutcome && void recordOutcome(selectedOutcome, "stay")} type="button">{busy?.startsWith("outcome-") ? "Saving…" : "Save & stay"}</button>
                  <button disabled={roleOrBusyDisabled || !selectedOutcome || outcomeNeedsCallback} onClick={() => selectedOutcome && void recordOutcome(selectedOutcome, "next")} type="button">{busy?.startsWith("outcome-") ? "Saving…" : <>Save & next <ArrowRight size={15} /></>}</button>
                </div>
              )}
            </section>

            <details className={styles.secondaryTools}>
              <summary><CalendarClock size={16} /><span><strong>Showing and access tools</strong><small>Schedule access when this investor requests it.</small></span></summary>
              <form className={styles.showingForm} onSubmit={createShowing}>
                <label><span>Date and time</span><input name="scheduled_at" required type="datetime-local" /></label>
                <label><span>Access state</span><select defaultValue="pending" name="access_status"><option value="pending">Access pending</option><option value="confirmed">Access confirmed</option><option value="shared_privately">Shared privately</option><option value="not_required">No access needed</option><option value="not_requested">Not requested</option></select></label>
                <label className={styles.wide}><span>Internal notes</span><input name="showing_notes" placeholder="Do not enter lockbox or alarm codes here." /></label>
                <button disabled={roleOrBusyDisabled} type="submit"><CalendarClock size={16} />Schedule showing</button>
              </form>
            </details>
          </div>

          <aside aria-labelledby="investor-queue-heading" className={styles.queuePanel}>
            <header><div><span>Investor queue</span><h4 id="investor-queue-heading">Who is next</h4></div><strong>{workspace.remaining_candidate_count} available</strong></header>
            <dl className={styles.queueMetrics}>
              <div><dt>Position</dt><dd>{queuePosition || "–"}/{candidates.length}</dd></div>
              <div><dt>Contacted</dt><dd>{contactedCount}</dd></div>
              <div><dt>Interested</dt><dd>{interestedCount}</dd></div>
              <div><dt>Skipped</dt><dd>{sessionSkippedBuyerIds.length}</dd></div>
            </dl>
            <p className={styles.queueGuidance}>Ranking is guidance. Choose any investor to pin this session at that relationship; unavailable channel controls remain enforced individually.</p>
            <ol className={styles.rankedPool}>
              {candidates.map((item) => {
                const selected = item.buyer_id === candidate.buyer_id;
                const skipped = skippedBuyerIds.has(item.buyer_id);
                return (
                  <li key={item.buyer_id}>
                    <button aria-current={selected ? "true" : undefined} className={styles.rankedBuyer} data-actionable={item.actionable} data-selected={selected} data-skipped={skipped} disabled={busy !== null || sessionPaused} onClick={() => void chooseCandidate(item.buyer_id)} type="button">
                      <span className={styles.rankedBuyerRank} data-ranked={hasRankedFit(item)}>{candidateRankLabel(item)}</span>
                      <span className={styles.rankedBuyerIdentity}><strong>{item.name}</strong><small>{skipped ? "Skipped this session" : item.company_name ?? candidateAvailabilityLabel(item)}</small></span>
                      <strong className={styles.rankedBuyerScore} data-ranked={hasRankedFit(item)}>{candidateFitLabel(item)}</strong>
                    </button>
                  </li>
                );
              })}
            </ol>
            <footer><span>Next up</span><strong>{nextCandidate?.name ?? "Choose anyone in the queue"}</strong></footer>
            <section className={styles.relationshipActivity} aria-label={`Recent relationship activity for ${candidate.name}`}>
              <header><div><span>Relationship activity</span><strong>Recent contact</strong></div>{inboundReplyCount ? <b>{inboundReplyCount} inbound</b> : null}</header>
              {buyerTimelineLoading ? <p>Loading activity…</p> : visibleBuyerTimeline.length ? (
                <ol>{visibleBuyerTimeline.map((item) => <li data-inbound={item.direction === "inbound"} key={`${item.category}-${item.id}`}><span>{item.channel ? labelize(item.channel) : labelize(item.event_type)} · {localDateTime(item.occurred_at)}</span><strong>{item.summary}</strong><small>{item.direction ? labelize(item.direction) : item.status ? labelize(item.status) : "Relationship update"}{item.status && item.direction ? ` · ${labelize(item.status)}` : ""}</small></li>)}</ol>
              ) : <p>No relationship activity has been recorded yet.</p>}
              <Link href={`/os/buyers?buyer=${encodeURIComponent(candidate.buyer_id)}`}>Open full relationship history <ArrowRight size={13} /></Link>
            </section>
          </aside>
        </div>
      ) : <section className={styles.panel}><div className={styles.empty}><UserRound size={28} /><strong>No investors are in this outreach queue yet</strong><span>Use Find and rank investors above to pull DealMachine candidates, rank the Buyer Network, or add a known investor. Deal and packet information can stay incomplete while you build and market the list.</span></div></section>}

      {workspace.showings.length ? <details className={styles.secondaryTools}><summary><CalendarClock size={16} /><span><strong>Scheduled showings</strong><small>{workspace.showings.length} access appointment{workspace.showings.length === 1 ? "" : "s"}</small></span></summary><div className={styles.showingList}>{workspace.showings.map((showing) => <ShowingRow busy={busy === `showing-${showing.id}`} canEdit={canEditDeals} key={showing.id} onUpdate={updateShowing} showing={showing} />)}</div></details> : null}
    </section>
  );
}

function PermissionLine({ allowed, blockers, channel, status }: { allowed: boolean; blockers: string[]; channel: string; status: string }) {
  return <div className={allowed ? styles.permissionAllowed : styles.permissionBlocked}><span>{channel} permission: {labelize(status)}</span>{!allowed ? <small>{blockers.join(" ")}</small> : <small>Manual outreach is available; this permission label remains informational.</small>}</div>;
}

function ShowingRow({
  busy,
  canEdit,
  onUpdate,
  showing,
}: {
  busy: boolean;
  canEdit: boolean;
  onUpdate: (showing: DispositionExecutionShowing, status: DispositionExecutionShowing["status"], accessStatus: DispositionExecutionShowing["access_status"]) => Promise<void>;
  showing: DispositionExecutionShowing;
}) {
  const [accessStatus, setAccessStatus] = useState(showing.access_status);
  const finished = ["completed", "cancelled", "no_show"].includes(showing.status);
  return <article><div><strong>{showing.buyer_name}</strong><span>{localDateTime(showing.scheduled_at)}</span><small>{labelize(showing.status)} - {labelize(accessStatus)}{showing.follow_up_task_id ? " - 24-hour follow-up created" : ""}</small></div><select aria-label={`Access status for ${showing.buyer_name}`} disabled={busy || !canEdit || finished} onChange={(event) => setAccessStatus(event.target.value as DispositionExecutionShowing["access_status"])} value={accessStatus}><option value="pending">Access pending</option><option value="confirmed">Access confirmed</option><option value="shared_privately">Shared privately</option><option value="not_required">No access needed</option><option value="not_requested">Not requested</option></select><div><button disabled={busy || !canEdit || finished} onClick={() => void onUpdate(showing, "confirmed", accessStatus)} type="button">Confirm</button><button disabled={busy || !canEdit || finished} onClick={() => void onUpdate(showing, "completed", accessStatus)} type="button">Complete</button><button disabled={busy || !canEdit || finished} onClick={() => void onUpdate(showing, "no_show", accessStatus)} type="button">No show</button></div></article>;
}
