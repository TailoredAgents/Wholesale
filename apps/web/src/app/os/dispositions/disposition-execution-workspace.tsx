"use client";

import {
  ArrowRight,
  ArrowDown,
  ArrowUp,
  CalendarClock,
  CheckCircle2,
  Download,
  EllipsisVertical,
  GripVertical,
  Headphones,
  Link2,
  Mail,
  MessageSquareText,
  PhoneCall,
  RefreshCw,
  Search,
  ShieldAlert,
  SkipForward,
  Trash2,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import type {
  BuyerProfile,
  BuyerTimelineItem,
  DispositionExecutionCandidate,
  DispositionExecutionSession,
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
type OutreachChannel = "sms" | "call" | "email";
type SessionUpdate = {
  state?: "active" | "paused";
  current_buyer_id?: string | null;
  advance_to_next?: boolean;
  rerank_queue?: boolean;
  queue_buyer_ids?: string[];
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

function money(value: number | null) {
  if (value === null) return "Not recorded";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value / 100);
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
  return hasRankedFit(candidate) ? `#${candidate.rank}` : "Not ranked";
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
  const [emailSubject, setEmailSubject] = useState("");
  const [emailDraft, setEmailDraft] = useState("");
  const [activeChannel, setActiveChannel] = useState<OutreachChannel>("sms");
  const [emailSenderAliases, setEmailSenderAliases] = useState<EmailSenderAlias[]>([]);
  const [emailSenderId, setEmailSenderId] = useState("");
  const [emailProviderConfigured, setEmailProviderConfigured] = useState<boolean | null>(null);
  const [emailConfigurationBlockers, setEmailConfigurationBlockers] = useState<string[]>([]);
  const [buyerProfile, setBuyerProfile] = useState<BuyerProfile | null>(null);
  const [buyerTimeline, setBuyerTimeline] = useState<BuyerTimelineItem[]>([]);
  const [buyerTimelineLoading, setBuyerTimelineLoading] = useState(false);
  const [selectedBuyerId, setSelectedBuyerId] = useState<string | null>(null);
  const [resultComposerOpen, setResultComposerOpen] = useState(false);
  const [notes, setNotes] = useState("");
  const [callbackAt, setCallbackAt] = useState("");
  const [selectedOutcome, setSelectedOutcome] = useState<Outcome | null>(null);
  const [savedOutcome, setSavedOutcome] = useState<{ buyerId: string; label: string } | null>(null);
  const [sessionSkippedBuyerIds, setSessionSkippedBuyerIds] = useState<string[]>([]);
  const [sessionSaveState, setSessionSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const [queueSearch, setQueueSearch] = useState("");
  const [draggingBuyerId, setDraggingBuyerId] = useState<string | null>(null);
  const buyerIdRef = useRef<string | null>(null);
  const buyerTimelineRequestRef = useRef<{
    buyerId: string;
    promise: Promise<void>;
    requestId: symbol;
  } | null>(null);
  const selectedQueueItemRef = useRef<HTMLLIElement>(null);
  const emailIdempotencyKeyRef = useRef<string | null>(null);
  const webPhone = useWebPhone();
  const browserCallActive = webPhone.status.callActive;
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
      setActiveChannel(
        buyerState?.current_step === "call" || buyerState?.current_step === "email"
          ? buyerState.current_step
          : "sms",
      );
      setResultComposerOpen(Boolean(buyerState?.selected_outcome) || lastOutcomeIsWaiting);
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
    }
    setSessionSkippedBuyerIds(result.session.skipped_buyer_ids);
    setSessionSaveState(result.session.persisted ? "saved" : "idle");
    setSelectedBuyerId(nextBuyerId);
    setWorkspace(result);
  }, []);

  function selectCandidateLocally(
    result: DispositionExecutionWorkspace,
    nextCandidate: DispositionExecutionCandidate,
  ) {
    const nextBuyerId = nextCandidate.buyer_id;
    const buyerState = result.session.buyer_states[nextBuyerId];
    const lastOutcomeIsWaiting = Boolean(
      result.session.last_outcome
      && result.session.last_outcome_buyer_id === nextBuyerId
      && result.current_candidate?.buyer_id !== nextBuyerId,
    );
    buyerIdRef.current = nextBuyerId;
    setOutcomeIdempotencyKey(idempotency("dispo-outcome"));
    setActiveChannel(
      buyerState?.current_step === "call" || buyerState?.current_step === "email"
        ? buyerState.current_step
        : "sms",
    );
    setResultComposerOpen(Boolean(buyerState?.selected_outcome) || lastOutcomeIsWaiting);
    setNotes(buyerState?.notes_draft ?? "");
    setCallbackAt(dateTimeLocalValue(buyerState?.callback_at));
    setSelectedOutcome((buyerState?.selected_outcome as Outcome | null | undefined) ?? null);
    setSavedOutcome(lastOutcomeIsWaiting && result.session.last_outcome
      ? { buyerId: nextBuyerId, label: labelize(result.session.last_outcome) }
      : null);
    setSmsDraft(nextCandidate.sms_draft);
    setEmailSubject(nextCandidate.email_subject);
    setEmailDraft(nextCandidate.email_draft);
    setEmailSenderId(buyerState?.email_sender_alias_id ?? "");
    emailIdempotencyKeyRef.current = null;
    setSelectedBuyerId(nextBuyerId);
    setSessionSkippedBuyerIds((current) => current.filter((item) => item !== nextBuyerId));
    setWorkspace({
      ...result,
      session: {
        ...result.session,
        state: "active",
        current_buyer_id: nextBuyerId,
        skipped_buyer_ids: result.session.skipped_buyer_ids.filter(
          (item) => item !== nextBuyerId,
        ),
      },
    });
  }

  async function chooseCandidate(buyerId: string, activateSession = false) {
    const nextCandidate = executionCandidates(workspace).find((candidate) => candidate.buyer_id === buyerId);
    if (!workspace || !nextCandidate || (buyerIdRef.current === buyerId && !activateSession)) return;
    const previousWorkspace = workspace;
    const previousCandidate = selectedCandidate(previousWorkspace, buyerIdRef.current);
    const isChangingBuyer = buyerIdRef.current !== buyerId;
    const nextSkippedBuyerIds = sessionSkippedBuyerIds.filter((item) => item !== buyerId);
    if (isChangingBuyer) selectCandidateLocally(previousWorkspace, nextCandidate);
    setBusy("session-cursor");
    setSessionSaveState("saving");
    try {
      const session = await request<DispositionExecutionSession>(
        `/api/v1/dispositions/cases/${caseId}/execution/session/cursor`,
        {
          method: "PATCH",
          body: JSON.stringify({
            current_buyer_id: buyerId,
            queue_buyer_ids: executionCandidates(previousWorkspace).map((item) => item.buyer_id),
            skipped_buyer_ids: nextSkippedBuyerIds,
          }),
        },
      );
      setWorkspace((current) => current ? { ...current, session } : current);
      setSessionSkippedBuyerIds(session.skipped_buyer_ids);
      setSessionSaveState("saved");
      onMessage(activateSession
        ? `${nextCandidate.name} is ready in the outreach console.`
        : `Selected ${nextCandidate.name}. Your queue order and drafts remain saved.`);
    } catch (error) {
      if (isChangingBuyer && previousCandidate) {
        selectCandidateLocally(previousWorkspace, previousCandidate);
      }
      setSessionSaveState("idle");
      onMessage(error instanceof Error ? error.message : "The selected investor could not be saved.");
    } finally {
      setBusy(null);
    }
  }

  async function saveQueueOrder(buyerIds: string[], message = "QuickDial order saved.") {
    const result = await updateSession({ queue_buyer_ids: buyerIds }, "queue-order");
    if (result) onMessage(message);
  }

  async function moveCandidate(buyerId: string, direction: -1 | 1) {
    const buyerIds = executionCandidates(workspace).map((item) => item.buyer_id);
    const currentIndex = buyerIds.indexOf(buyerId);
    const nextIndex = currentIndex + direction;
    if (currentIndex < 0 || nextIndex < 0 || nextIndex >= buyerIds.length) return;
    [buyerIds[currentIndex], buyerIds[nextIndex]] = [buyerIds[nextIndex], buyerIds[currentIndex]];
    await saveQueueOrder(buyerIds);
  }

  async function makeCandidateNext(buyerId: string) {
    if (buyerId === buyerIdRef.current) return;
    const buyerIds = executionCandidates(workspace).map((item) => item.buyer_id);
    const withoutBuyer = buyerIds.filter((item) => item !== buyerId);
    const currentIndex = withoutBuyer.indexOf(buyerIdRef.current ?? "");
    withoutBuyer.splice(currentIndex >= 0 ? currentIndex + 1 : 0, 0, buyerId);
    await saveQueueOrder(withoutBuyer, "Next investor saved.");
  }

  async function moveCandidateToTop(buyerId: string) {
    const buyerIds = executionCandidates(workspace).map((item) => item.buyer_id);
    const nextOrder = [buyerId, ...buyerIds.filter((item) => item !== buyerId)];
    await saveQueueOrder(nextOrder, "Investor moved to the top of QuickDial.");
  }

  async function moveCandidateBefore(buyerId: string, targetBuyerId: string) {
    if (buyerId === targetBuyerId) return;
    const buyerIds = executionCandidates(workspace).map((item) => item.buyer_id);
    const nextOrder = buyerIds.filter((item) => item !== buyerId);
    const targetIndex = nextOrder.indexOf(targetBuyerId);
    if (targetIndex < 0) return;
    nextOrder.splice(targetIndex, 0, buyerId);
    await saveQueueOrder(nextOrder, "QuickDial order saved by drag and drop.");
  }

  async function removeCandidate(buyerId: string) {
    const candidates = executionCandidates(workspace);
    const currentIndex = candidates.findIndex((item) => item.buyer_id === buyerId);
    if (currentIndex < 0) return;
    const buyerIds = candidates.filter((item) => item.buyer_id !== buyerId).map((item) => item.buyer_id);
    const nextCurrentBuyerId = buyerIdRef.current === buyerId
      ? buyerIds[Math.min(currentIndex, buyerIds.length - 1)] ?? null
      : buyerIdRef.current;
    const result = await updateSession({
      queue_buyer_ids: buyerIds,
      current_buyer_id: nextCurrentBuyerId,
    }, "queue-remove");
    if (result) onMessage("Investor removed from this deal's QuickDial list. Their Buyer Network relationship was kept.");
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

  const loadBuyerTimeline = useCallback((buyerId: string) => {
    const inFlight = buyerTimelineRequestRef.current;
    if (inFlight?.buyerId === buyerId) return inFlight.promise;

    const requestId = Symbol(buyerId);
    const promise = (async () => {
      setBuyerTimelineLoading(true);
      try {
        const result = await request<BuyerProfile>(
          `/api/v1/buyers/${buyerId}/profile?timeline_limit=12`,
        );
        if (buyerIdRef.current === buyerId) {
          setBuyerProfile(result);
          setBuyerTimeline(result.timeline.items);
        }
      } catch {
        if (buyerIdRef.current === buyerId) {
          setBuyerProfile(null);
          setBuyerTimeline([]);
        }
      } finally {
        if (buyerTimelineRequestRef.current?.requestId === requestId) {
          buyerTimelineRequestRef.current = null;
        }
        if (buyerIdRef.current === buyerId) setBuyerTimelineLoading(false);
      }
    })();
    buyerTimelineRequestRef.current = { buyerId, promise, requestId };
    return promise;
  }, [request]);

  const activeTimelineBuyerId = selectedCandidate(workspace, selectedBuyerId)?.buyer_id ?? null;

  useEffect(() => {
    if (!activeTimelineBuyerId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setBuyerProfile(null);
      setBuyerTimeline([]);
      return;
    }
    void loadBuyerTimeline(activeTimelineBuyerId);
  }, [activeTimelineBuyerId, loadBuyerTimeline]);

  useEffect(() => {
    if (!activeTimelineBuyerId) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void loadBuyerTimeline(activeTimelineBuyerId);
      }
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [activeTimelineBuyerId, loadBuyerTimeline]);

  useEffect(() => {
    selectedQueueItemRef.current?.scrollIntoView({ block: "nearest" });
  }, [selectedBuyerId]);

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

  async function action<T>(
    key: string,
    operation: () => Promise<T>,
    success: string,
    refreshParent = false,
  ) {
    setBusy(key);
    onMessage(null);
    try {
      const result = await operation();
      if (refreshParent) {
        try {
          await onWorkspaceChanged();
        } catch {
          // The local mutation succeeded; the parent overview can refresh independently.
        }
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
    setResultComposerOpen(true);
    await Promise.all([
      refreshSessionSnapshot(),
      loadBuyerTimeline(candidate.buyer_id),
    ]);
    onMessage(`Follow-up email ${labelize(result.status)} for ${candidate.name}. Delivery and replies will appear in the conversation.`);
  }

  async function sendSms() {
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (!candidate || !candidate.actionable || !canEditDeals || !candidate.sms.allowed) return;
    const body = smsDraft.trim();
    if (!body) {
      onMessage("Review the introduction and enter a message before sending it.");
      return;
    }
    const result = await action(
      "sms",
      () => request(`/api/v1/dispositions/cases/${caseId}/execution/sms`, {
          method: "POST",
          body: JSON.stringify({
            ...executionBuyerReference(candidate),
            body,
            idempotency_key: idempotency("dispo-sms"),
          }),
        }),
      `Introduction text accepted for ${candidate.name}.`,
    );
    if (!result) return;

    setResultComposerOpen(true);
    await Promise.all([
      refreshSessionSnapshot(),
      loadBuyerTimeline(candidate.buyer_id),
    ]);
  }

  async function startBrowserCall() {
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (!candidate || !candidate.actionable || !canEditDeals || !candidate.voice.allowed) return;
    if (browserCallActive) {
      onMessage("End the current browser call before starting the next buyer call.");
      return;
    }
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
      setResultComposerOpen(true);
      await Promise.all([
        refreshSessionSnapshot(),
        loadBuyerTimeline(candidate.buyer_id),
      ]);
    }
  }

  async function startCellphoneCall() {
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (!candidate || !candidate.actionable || !canEditDeals || !candidate.voice.allowed) return;
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
      setResultComposerOpen(true);
      await Promise.all([
        refreshSessionSnapshot(),
        loadBuyerTimeline(candidate.buyer_id),
      ]);
    }
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
      setResultComposerOpen(true);
      const issuedPackageLabel = result.is_preliminary ? "Preliminary" : "Approved";
      onMessage(`${issuedPackageLabel} investor packet text accepted for ${candidate.name}. The secure link expires in 72 hours. If delivery is ever uncertain, check the buyer conversation before retrying.`);
      await load();
      await loadBuyerTimeline(candidate.buyer_id);
    }
  }

  async function copyPacketLink() {
    if (!workspace?.package_pdf_path || !canEditDeals) return;
    const issued = await action(
      "packet-link",
      () => request<DispositionPackageShareLinkIssued>(
        `/api/v1/dispositions/cases/${caseId}/package/share-links`,
        {
          method: "POST",
          body: JSON.stringify({ expires_in_hours: 72 }),
        },
      ),
      "A secure 72-hour investor packet link was created.",
    );
    if (!issued) return;
    try {
      await navigator.clipboard.writeText(issued.share_url);
      onMessage(`${issued.is_preliminary ? "Preliminary" : "Approved"} investor packet link copied. It expires in 72 hours.`);
    } catch {
      onMessage("The secure packet link was created, but your browser blocked clipboard access. Open Deal & Packet to copy a new link.");
    }
  }

  async function emailInvestorPacket() {
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (
      !candidate
      || !candidate.actionable
      || !candidate.email
      || !workspace?.package_pdf_path
      || !canEditDeals
      || !emailProviderConfigured
      || !emailSenderId
    ) return;
    const firstName = candidate.name.trim().split(/\s+/)[0] || "there";
    const result = await action(
      "packet-email",
      async () => {
        const issued = await request<DispositionPackageShareLinkIssued>(
          `/api/v1/dispositions/cases/${caseId}/package/share-links`,
          {
            method: "POST",
            body: JSON.stringify({ expires_in_hours: 72 }),
          },
        );
        const issuedPackageLabel = issued.is_preliminary ? "preliminary" : "approved";
        const delivery = await request<EmailSendResult>(
          `/api/v1/dispositions/cases/${caseId}/execution/email`,
          {
            method: "POST",
            body: JSON.stringify({
              ...executionBuyerReference(candidate),
              email_sender_alias_id: emailSenderId,
              subject: `${issued.is_preliminary ? "Preliminary " : ""}property package - ${workspace.property_address}`,
              body: `Hi ${firstName},\n\nHere is the ${issuedPackageLabel} property package for ${workspace.property_address}. This secure link expires in 72 hours:\n${issued.share_url}`,
              idempotency_key: idempotency("dispo-packet-email"),
            }),
          },
        );
        return { delivery, issued };
      },
      `Investor packet email accepted for ${candidate.name}.`,
    );
    if (!result) return;
    setResultComposerOpen(true);
    const issuedPackageLabel = result.issued.is_preliminary ? "Preliminary" : "Approved";
    onMessage(`${issuedPackageLabel} investor packet email ${labelize(result.delivery.status)} for ${candidate.name}. The secure link expires in 72 hours; delivery and replies appear in the conversation.`);
    await load();
    await loadBuyerTimeline(candidate.buyer_id);
  }

  async function recordOutcome(outcome: Outcome, advance: "next" | "stay") {
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (!candidate || !candidate.actionable || !canEditDeals) return;
    if (outcome === "callback" && !callbackAt) {
      onMessage("Choose the requested callback date and time first.");
      return;
    }
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
      true,
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
      true,
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
      true,
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
      true,
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
    || outcomeSavedForCurrent;
  const smsUnavailable = roleOrBusyDisabled || !candidate?.sms.allowed;
  const voiceUnavailable = roleOrBusyDisabled || !candidate?.voice.allowed || webPhone.busy || browserCallActive;
  const emailUnavailable = busy !== null
    || !canEditDeals
    || !candidate?.actionable
    || !candidate.email
    || !emailProviderConfigured
    || !emailSenderId;
  const packetUnavailable = smsUnavailable || !workspace.package_pdf_path;
  const packetEmailUnavailable = emailUnavailable || !workspace.package_pdf_path;
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
  const nextCandidate = candidate
    ? nextActionableCandidate(candidates, candidate.buyer_id, skippedBuyerIds)
    : candidates.find((item) => item.actionable && !skippedBuyerIds.has(item.buyer_id)) ?? null;
  const normalizedQueueSearch = queueSearch.trim().toLocaleLowerCase();
  const visibleCandidates = normalizedQueueSearch
    ? candidates.filter((item) => [item.name, item.company_name, item.phone, item.email]
      .some((value) => value?.toLocaleLowerCase().includes(normalizedQueueSearch)))
    : candidates;
  const buyerProgress = candidate
    ? workspace.session.buyer_states[candidate.buyer_id]
    : null;
  const outcomeNeedsCallback = selectedOutcome === "callback" && !callbackAt;
  const emailHasPacketLink = emailDraft.includes("/api/v1/public/investor-packages/");
  const visibleBuyerTimeline = buyerTimeline.filter(
    (item) => item.category !== "relationship" || !["sms", "email"].includes(item.event_type),
  ).slice(0, 12).reverse();
  const inboundReplyCount = buyerTimeline.filter(
    (item) => item.category === "communication" && item.direction === "inbound",
  ).length;
  const activeBuyerProfile = candidate && buyerProfile?.buyer.id === candidate.buyer_id
    ? buyerProfile
    : null;

  return (
    <section aria-label="Investor outreach desk" className={styles.workspace} data-empty={!candidate} id="call-queue" tabIndex={-1}>
      <header className={styles.hero} data-empty={!candidate}>
        <div>
          <span>Investor QuickDial</span>
          <h3>Contact an investor, then move to the next</h3>
          <p>Choose anyone in the queue. Calls, drafts, outcomes, and your exact position save as you work.</p>
        </div>
        <div className={styles.heroActions}>
          {workspace.package_pdf_path ? <button className={styles.secondary} disabled={busy !== null} onClick={() => void downloadPackage(workspace.package_pdf_path!)} type="button"><Download size={15} />Open {packageLabel} packet</button> : null}
          {candidate ? <button aria-label="Refresh disposition call queue" className={styles.secondary} disabled={busy !== null || loading} onClick={() => void refreshOutreachWorkspace()} type="button"><RefreshCw size={15} />Refresh</button> : null}
          {candidate ? <span className={styles.sessionSave} data-saving={sessionSaveState === "saving"}>{sessionSaveState === "saving" ? "Saving…" : workspace.session.persisted ? "Saved" : "Ready to save"}</span> : null}
        </div>
      </header>

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
        currentQueueBuyerIds={candidates.map((item) => item.buyer_id)}
        onMessage={onMessage}
        onQueueChanged={refreshQueueBuilderWorkspace}
        quickDialQueueCount={candidates.length}
        request={request}
      />

      {candidate ? (
        <div className={styles.outreachLayout}>
          <div className={styles.currentInvestor}>
            <section className={`${styles.panel} ${styles.outreachConsole}`}>
              <header className={styles.conversationHeader}>
                <div className={styles.conversationIdentity}>
                  <span>Current investor{hasRankedFit(candidate) ? ` · ${candidateRankLabel(candidate)}` : ""}</span>
                  <h4>{candidate.name}</h4>
                  <p>{candidate.company_name ?? "Independent investor"}</p>
                </div>
                <dl className={styles.conversationMeta}>
                  <div><dt>Phone</dt><dd>{candidate.phone ?? "Not recorded"}</dd></div>
                  <div><dt>Email</dt><dd>{candidate.email ?? "Not recorded"}</dd></div>
                  <div><dt>Relationship</dt><dd>{labelize(candidate.relationship_status ?? "unknown")}</dd></div>
                  <div><dt>Nearby purchase</dt><dd>{candidate.recent_purchase_reference ?? "None saved"}</dd></div>
                </dl>
                <div className={styles.conversationStatus}>
                  {inboundReplyCount ? <b>{inboundReplyCount} inbound</b> : null}
                  {hasRankedFit(candidate) ? <div className={styles.score}><strong>{candidateFitLabel(candidate)}</strong><span>fit score</span></div> : null}
                </div>
              </header>
              {!candidate.actionable ? <div className={styles.candidateState} data-dnc={isDoNotContact(candidate)}><strong>{outcomeSavedForCurrent ? `${savedOutcome?.label} saved` : candidateAvailabilityLabel(candidate)}</strong><span>{outcomeSavedForCurrent ? "The result is recorded. Stay here or continue to the next investor when ready." : candidate.action_blockers.join(" ") || "This investor is not currently actionable."}</span></div> : null}
              <div className={styles.conversationUtilities}>
                <details className={styles.fitEvidence}>
                  <summary>{hasRankedFit(candidate) ? "Why this investor ranks here" : "Ranking details"}</summary>
                  <div className={styles.evidence}>{hasRankedFit(candidate)
                    ? candidate.score_explanation.slice(0, 5).map((item) => <p key={item}><CheckCircle2 size={14} />{item}</p>)
                    : <p><UserRound size={14} />This canonical Buyer Network record has not been scored by a ranking run. No rank or fit score is implied.</p>}</div>
                </details>
                {isPassedCandidate(candidate) && !isDoNotContact(candidate) && candidate.candidate_id && candidate.lock_version !== null ? <button className={styles.secondary} disabled={busy !== null || !canEditDeals} onClick={() => void clearPass()} type="button">{busy === "clear-pass" ? "Clearing pass…" : "Clear pass"}</button> : null}
              </div>
              <section aria-label="Investor packet delivery" className={styles.packetQuickBar}>
                <div><Download size={16} /><span><strong>Investor asks for the packet?</strong><small>Send the current {packageLabel} PDF without leaving the call or conversation.</small></span></div>
                <div>
                  {workspace.package_pdf_path ? <button className={styles.secondary} disabled={busy !== null} onClick={() => void downloadPackage(workspace.package_pdf_path!)} type="button">Open packet</button> : null}
                  <button className={styles.secondary} disabled={!canEditDeals || !workspace.package_pdf_path || busy !== null} onClick={() => void copyPacketLink()} type="button"><Link2 size={14} />{busy === "packet-link" ? "Copying…" : "Copy link"}</button>
                  <button className={styles.secondary} disabled={packetUnavailable} onClick={() => void sendApprovedPacket()} type="button"><MessageSquareText size={14} />{busy === "packet-sms" ? "Sending…" : "Send by text"}</button>
                  <button className={styles.secondary} disabled={packetEmailUnavailable} onClick={() => void emailInvestorPacket()} type="button"><Mail size={14} />{busy === "packet-email" ? "Sending…" : "Send by email"}</button>
                </div>
              </section>
              <InvestorConversation
                candidate={candidate}
                loading={buyerTimelineLoading}
                timeline={visibleBuyerTimeline}
              />
              <div aria-label="Outreach channel" className={styles.channelTabs} role="tablist">
                <button aria-controls="investor-sms" aria-selected={activeChannel === "sms"} id="outreach-text-tab" onClick={() => setActiveChannel("sms")} role="tab" type="button"><MessageSquareText size={15} /><span><strong>Text</strong><small>{buyerProgress?.sms_status === "sent" ? "Sent" : buyerProgress?.sms_status === "drafted" ? "Draft saved" : candidate.sms.allowed ? "Ready" : "Unavailable"}</small></span></button>
                <button aria-controls="investor-call" aria-selected={activeChannel === "call"} id="outreach-call-tab" onClick={() => setActiveChannel("call")} role="tab" type="button"><Headphones size={15} /><span><strong>Call</strong><small>{buyerProgress?.call_status === "completed" ? "Completed" : buyerProgress?.call_status === "started" ? "Started" : candidate.voice.allowed ? "Ready" : "Unavailable"}</small></span></button>
                <button aria-controls="investor-email" aria-selected={activeChannel === "email"} id="outreach-email-tab" onClick={() => setActiveChannel("email")} role="tab" type="button"><Mail size={15} /><span><strong>Email</strong><small>{buyerProgress?.email_status === "sent" ? "Sent" : buyerProgress?.email_status === "drafted" ? "Draft saved" : candidate.email && emailProviderConfigured ? "Ready" : "Unavailable"}</small></span></button>
              </div>
              <div className={styles.channelWorkspace}>

              {activeChannel === "sms" ? <div aria-labelledby="outreach-text-tab" className={styles.channelSection} id="investor-sms" role="tabpanel">
                <div className={styles.sectionTitle}><MessageSquareText size={17} /><div><span>Text</span><h4>Message {candidate.name}</h4></div></div>
                <p className={styles.help}>Write freely from the deal-aware draft. Nothing sends until you choose Send text.</p>
                <PermissionLine allowed={candidate.actionable && candidate.sms.allowed} blockers={[...candidate.action_blockers, ...candidate.sms.blockers]} channel="SMS" status={candidate.sms.status} />
                <div className={styles.smsComposer}>
                  <label><span>To {candidate.phone ?? "No phone recorded"}</span><textarea aria-label="Introduction SMS draft" onBlur={() => void saveCurrentBuyerState({ current_step: "sms" })} onChange={(event) => { setSmsDraft(event.target.value); setSessionSaveState("idle"); }} rows={5} value={smsDraft} /></label>
                  <small className={styles.characterCount}>{smsDraft.trim().length} characters</small>
                  <div className={styles.composerActions}>
                    <button className={styles.secondary} disabled={packetUnavailable} onClick={() => void sendApprovedPacket()} type="button"><Download size={15} />{busy === "packet-sms" ? "Sending packet…" : `Text ${packageLabel} packet`}</button>
                    <button className={styles.secondary} disabled={busy === "sms"} onClick={() => void discardCurrentSmsDraft()} onMouseDown={(event) => event.preventDefault()} type="button">Reset draft</button>
                    <button disabled={smsUnavailable || !smsDraft.trim()} onClick={() => void sendSms()} onMouseDown={(event) => event.preventDefault()} type="button"><MessageSquareText size={16} />{busy === "sms" ? "Sending…" : "Send text"}</button>
                  </div>
                </div>
              </div> : null}

              {activeChannel === "call" ? <div aria-labelledby="outreach-call-tab" className={styles.channelSection} id="investor-call" role="tabpanel">
                <div className={styles.sectionTitle}><Headphones size={17} /><div><span>Call</span><h4>Choose how to call {candidate.name}</h4></div></div>
                <p className={styles.help}>A call begins only when you choose one of these options.</p>
                <PermissionLine allowed={candidate.actionable && candidate.voice.allowed} blockers={[...candidate.action_blockers, ...candidate.voice.blockers]} channel="Call" status={candidate.voice.status} />
                <div className={styles.callActions}>
                  <button disabled={voiceUnavailable} onClick={() => void startBrowserCall()} type="button"><Headphones size={16} />{busy === "browser-call" || webPhone.busy ? "Starting browser call…" : browserCallActive ? "Browser call in progress" : `Call ${candidate.name} in browser`}</button>
                  <button className={styles.secondary} disabled={voiceUnavailable} onClick={() => void startCellphoneCall()} type="button"><PhoneCall size={16} />{busy === "cellphone-call" ? "Calling your cellphone…" : "Use my cellphone"}</button>
                </div>
              </div> : null}

              {activeChannel === "email" ? <div aria-labelledby="outreach-email-tab" className={styles.channelSection} id="investor-email" role="tabpanel">
                <div className={styles.sectionTitle}><Mail size={17} /><div><span>Email</span><h4>Email follow-up</h4></div></div>
                <p className={styles.help}>{candidate.email ? `Review the deal-aware starting draft for ${candidate.email}. Nothing sends until you approve it.` : "Add an email to the relationship profile before sending follow-up."}</p>
                {emailProviderConfigured === false ? <div className={styles.permissionBlocked}><span>Email sender unavailable</span><small>{emailConfigurationBlockers.join(" ") || "Configure an authorized Stonegate sender."}</small></div> : null}
                {emailProviderConfigured === true && !emailSenderAliases.length ? <div className={styles.permissionBlocked}><span>No authorized email sender</span><small>Ask an email administrator to grant this user access to an active Stonegate sender.</small></div> : null}
                <div className={`${styles.smsComposer} ${styles.emailComposer}`}>
                  <label><span>From</span><select disabled={emailUnavailable} onBlur={() => void saveCurrentBuyerState({ current_step: "email" })} onChange={(event) => { setEmailSenderId(event.target.value); setSessionSaveState("idle"); emailIdempotencyKeyRef.current = null; }} value={emailSenderId}><option value="">Select sender</option>{emailSenderAliases.map((sender) => <option key={sender.id} value={sender.id}>{sender.display_name} · {sender.email_address}</option>)}</select></label>
                  <label><span>To {candidate.email ?? "No email recorded"}</span><input aria-label="Investor follow-up email subject" onBlur={() => void saveCurrentBuyerState({ current_step: "email" })} onChange={(event) => { setEmailSubject(event.target.value); setSessionSaveState("idle"); emailIdempotencyKeyRef.current = null; }} placeholder="Subject" value={emailSubject} /></label>
                  <label><span>Message</span><textarea aria-label="Investor follow-up email draft" onBlur={() => void saveCurrentBuyerState({ current_step: "email" })} onChange={(event) => { setEmailDraft(event.target.value); setSessionSaveState("idle"); emailIdempotencyKeyRef.current = null; }} rows={9} value={emailDraft} /></label>
                  <small className={styles.characterCount}>{emailDraft.trim().length} characters · Deal-aware starting draft</small>
                  <div className={styles.composerActions}>
                    <button className={styles.secondary} disabled={busy !== null || !workspace.package_pdf_path || emailHasPacketLink} onClick={() => void insertPacketLinkInEmail()} type="button"><Download size={15} />{emailHasPacketLink ? "Packet link included" : `Insert ${packageLabel} packet link`}</button>
                    <button className={styles.secondary} disabled={busy === "email"} onClick={() => void discardCurrentEmailDraft()} onMouseDown={(event) => event.preventDefault()} type="button">Reset draft</button>
                    <button disabled={emailUnavailable || !emailSubject.trim() || !emailDraft.trim()} onClick={() => void sendFollowUpEmail()} onMouseDown={(event) => event.preventDefault()} type="button"><Mail size={16} />{busy === "email" ? "Sending…" : "Send email"}</button>
                  </div>
                </div>
              </div> : null}
              </div>
              <section className={styles.resultDock}>
                <header>
                  <div><SkipForward size={17} /><span><strong>Finished an interaction?</strong><small>Record a result only when there is something meaningful to save.</small></span></div>
                  <button aria-expanded={resultComposerOpen || outcomeSavedForCurrent} className={styles.secondary} disabled={outcomeSavedForCurrent} onClick={() => setResultComposerOpen((current) => !current)} type="button">{resultComposerOpen ? "Hide result" : "Record result"}</button>
                </header>
                {resultComposerOpen || outcomeSavedForCurrent ? <div className={styles.resultComposer}>
                  <small>No answer creates a 4-hour retry; voicemail creates a 24-hour follow-up.</small>
                  <div className={styles.outcomes}>{OUTCOMES.map((outcome) => <button aria-pressed={selectedOutcome === outcome.value} data-selected={selectedOutcome === outcome.value} data-tone={outcome.tone} disabled={roleOrBusyDisabled} key={outcome.value} onClick={() => { setSelectedOutcome(outcome.value); setSessionSaveState("idle"); }} type="button">{outcome.label}</button>)}</div>
                  <div className={styles.outcomeInputs} data-callback={selectedOutcome === "callback"}>
                    <label><span>Notes</span><textarea disabled={outcomeSavedForCurrent} onBlur={() => void saveCurrentBuyerState({ current_step: "outcome" })} onChange={(event) => { setNotes(event.target.value); setSessionSaveState("idle"); }} placeholder="Interest, objections, or requested next step…" rows={2} value={notes} /></label>
                    {selectedOutcome === "callback" ? <label><span>Callback time</span><input disabled={outcomeSavedForCurrent} onBlur={() => void saveCurrentBuyerState({ current_step: "outcome" })} onChange={(event) => { setCallbackAt(event.target.value); setSessionSaveState("idle"); }} type="datetime-local" value={callbackAt} /><small>Required before saving Callback.</small></label> : null}
                  </div>
                  {outcomeSavedForCurrent ? (
                    <div className={styles.savedOutcome} role="status"><CheckCircle2 size={18} /><div><strong>{savedOutcome?.label} saved</strong><span>You are still on {candidate.name}. This exact position will resume until you continue.</span></div><button onClick={() => void continueToNextBuyer()} type="button">Next investor <ArrowRight size={15} /></button></div>
                  ) : (
                    <div className={styles.outcomeActions}>
                      <button className={styles.secondary} disabled={busy !== null} onClick={() => void skipCurrentBuyer()} type="button"><SkipForward size={15} />Skip for now</button>
                      <span />
                      <button className={styles.secondary} disabled={roleOrBusyDisabled || !selectedOutcome || outcomeNeedsCallback} onClick={() => selectedOutcome && void recordOutcome(selectedOutcome, "stay")} onMouseDown={(event) => event.preventDefault()} type="button">{busy?.startsWith("outcome-") ? "Saving…" : "Save & stay"}</button>
                      <button disabled={roleOrBusyDisabled || !selectedOutcome || outcomeNeedsCallback} onClick={() => selectedOutcome && void recordOutcome(selectedOutcome, "next")} onMouseDown={(event) => event.preventDefault()} type="button">{busy?.startsWith("outcome-") ? "Saving…" : <>Save & next <ArrowRight size={15} /></>}</button>
                    </div>
                  )}
                </div> : null}
              </section>
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
            <header><div><span>Investor queue</span><h4 id="investor-queue-heading">Choose who to contact</h4></div><strong>{workspace.remaining_candidate_count} available</strong></header>
            <dl className={styles.queueMetrics}>
              <div><dt>Position</dt><dd>{queuePosition || "–"}/{candidates.length}</dd></div>
              <div><dt>Contacted</dt><dd>{contactedCount}</dd></div>
              <div><dt>Interested</dt><dd>{interestedCount}</dd></div>
              <div><dt>Skipped</dt><dd>{sessionSkippedBuyerIds.length}</dd></div>
            </dl>
            <label className={styles.queueSearch}><Search aria-hidden="true" size={14} /><input aria-label="Search investor queue" onChange={(event) => setQueueSearch(event.target.value)} placeholder="Search investors" type="search" value={queueSearch} /></label>
            <p className={styles.queueGuidance}>Select anyone to review them, use Contact to begin, or drag rows into your preferred order.</p>
            <ol className={styles.rankedPool}>
              {visibleCandidates.map((item) => {
                const index = candidates.findIndex((candidateItem) => candidateItem.buyer_id === item.buyer_id);
                const selected = item.buyer_id === candidate.buyer_id;
                const isNext = item.buyer_id === nextCandidate?.buyer_id;
                const skipped = skippedBuyerIds.has(item.buyer_id);
                return (
                  <li data-dragging={draggingBuyerId === item.buyer_id} draggable={busy === null} key={item.buyer_id} onDragEnd={() => setDraggingBuyerId(null)} onDragOver={(event) => { if (draggingBuyerId) event.preventDefault(); }} onDragStart={(event) => { setDraggingBuyerId(item.buyer_id); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", item.buyer_id); }} onDrop={(event) => { event.preventDefault(); const draggedBuyerId = draggingBuyerId ?? event.dataTransfer.getData("text/plain"); setDraggingBuyerId(null); if (draggedBuyerId) void moveCandidateBefore(draggedBuyerId, item.buyer_id); }} ref={selected ? selectedQueueItemRef : undefined}>
                    <span aria-hidden="true" className={styles.queueDragHandle}><GripVertical size={13} /></span>
                    <button aria-current={selected ? "true" : undefined} className={styles.rankedBuyer} data-actionable={item.actionable} data-ranked={hasRankedFit(item)} data-selected={selected} data-skipped={skipped} disabled={busy !== null} onClick={() => void chooseCandidate(item.buyer_id)} type="button">
                      {hasRankedFit(item) ? <span className={styles.rankedBuyerRank}>{candidateRankLabel(item)}</span> : null}
                      <span className={styles.rankedBuyerIdentity}><span className={styles.queueIdentityHeader}><strong>{item.name}</strong><span className={styles.queueBadges}>{selected ? <b data-tone="current">Current</b> : null}{isNext ? <b data-tone="next">Next</b> : null}</span></span><small>{skipped ? "Skipped this session" : item.company_name ?? candidateAvailabilityLabel(item)}</small></span>
                      {hasRankedFit(item) ? <strong className={styles.rankedBuyerScore}>{candidateFitLabel(item)}</strong> : null}
                    </button>
                    <div className={styles.queueRowActions}>
                      <button className={styles.queueContactAction} disabled={busy !== null || !item.actionable} onClick={() => void chooseCandidate(item.buyer_id, true)} type="button"><PhoneCall size={12} />Contact</button>
                      <details className={styles.queueRowMenu}>
                        <summary aria-label={`More queue actions for ${item.name}`}><EllipsisVertical size={14} /></summary>
                        <div>
                          <button disabled={busy !== null || selected || !item.actionable} onClick={() => void makeCandidateNext(item.buyer_id)} type="button">Make next</button>
                          <button disabled={busy !== null || index === 0} onClick={() => void moveCandidateToTop(item.buyer_id)} type="button">Move to top</button>
                          <button disabled={busy !== null || index === 0} onClick={() => void moveCandidate(item.buyer_id, -1)} type="button"><ArrowUp size={12} />Move earlier</button>
                          <button disabled={busy !== null || index === candidates.length - 1} onClick={() => void moveCandidate(item.buyer_id, 1)} type="button"><ArrowDown size={12} />Move later</button>
                          <button data-danger="true" disabled={busy !== null} onClick={() => void removeCandidate(item.buyer_id)} type="button"><Trash2 size={12} />Remove</button>
                        </div>
                      </details>
                    </div>
                  </li>
                );
              })}
              {!visibleCandidates.length ? <li className={styles.queueEmpty}>No investors match your search.</li> : null}
            </ol>
            <footer><div><span>Current</span><strong>{candidate.name}</strong></div><div><span>Next</span><strong>{nextCandidate?.name ?? "Choose anyone in the queue"}</strong></div></footer>
          </aside>

          <RelationshipContext
            assetClass={workspace.asset_class}
            candidate={candidate}
            loading={buyerTimelineLoading}
            profile={activeBuyerProfile}
          />
        </div>
      ) : null}

      {workspace.showings.length ? <details className={styles.secondaryTools}><summary><CalendarClock size={16} /><span><strong>Scheduled showings</strong><small>{workspace.showings.length} access appointment{workspace.showings.length === 1 ? "" : "s"}</small></span></summary><div className={styles.showingList}>{workspace.showings.map((showing) => <ShowingRow busy={busy === `showing-${showing.id}`} canEdit={canEditDeals} key={showing.id} onUpdate={updateShowing} showing={showing} />)}</div></details> : null}
    </section>
  );
}

function InvestorConversation({
  candidate,
  loading,
  timeline,
}: {
  candidate: DispositionExecutionCandidate;
  loading: boolean;
  timeline: BuyerTimelineItem[];
}) {
  const timelineRef = useRef<HTMLOListElement>(null);

  useEffect(() => {
    const element = timelineRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [candidate.buyer_id, timeline]);

  return (
    <section aria-label={`Conversation with ${candidate.name}`} className={styles.conversationTimeline}>
      {loading ? <p>Loading conversation…</p> : timeline.length ? (
        <ol aria-live="polite" ref={timelineRef}>{timeline.map((item) => (
          <li data-direction={item.direction ?? "activity"} key={`${item.category}-${item.id}`}>
            <span>{item.channel ? labelize(item.channel) : labelize(item.event_type)} · {localDateTime(item.occurred_at)}</span>
            <strong>{item.summary}</strong>
            <small>{item.direction ? labelize(item.direction) : item.status ? labelize(item.status) : "Relationship update"}{item.status && item.direction ? ` · ${labelize(item.status)}` : ""}</small>
          </li>
        ))}</ol>
      ) : <p>No conversation has been recorded yet. Use the controls below to start one.</p>}
      <footer>
        <span>Shared with the canonical buyer relationship and Inbox history.</span>
      </footer>
    </section>
  );
}

function RelationshipContext({
  assetClass,
  candidate,
  loading,
  profile,
}: {
  assetClass: string;
  candidate: DispositionExecutionCandidate;
  loading: boolean;
  profile: BuyerProfile | null;
}) {
  const buyer = profile?.buyer;
  const buyBox = buyer?.buy_boxes.find((item) => item.asset_class === assetClass)
    ?? buyer?.buy_boxes[0];
  const markets = buyBox?.criteria.geographies
    .slice(0, 3)
    .map((item) => item.state && !item.value.includes(item.state) ? `${item.value}, ${item.state}` : item.value)
    .join(" · ");
  const priceRange = buyBox
    ? `${money(buyBox.criteria.min_price_cents)} – ${money(buyBox.criteria.max_price_cents)}`
    : buyer?.criteria
      ? `${money(buyer.criteria.min_price_cents)} – ${money(buyer.criteria.max_price_cents)}`
      : "Not recorded";

  return (
    <aside aria-label={`Relationship context for ${candidate.name}`} className={styles.relationshipPanel}>
      <header>
        <div><span>Investor relationship</span><h4>Know who you’re contacting</h4></div>
      </header>
      {loading && !buyer ? <p className={styles.relationshipLoading}>Loading relationship context…</p> : (
        <>
          <dl className={styles.relationshipFacts}>
            <div><dt>Owner</dt><dd>{buyer?.relationship_owner_name ?? "Unassigned"}</dd></div>
            <div><dt>Priority</dt><dd>{buyer ? `${buyer.tier === "unclassified" ? "Unclassified" : `Tier ${buyer.tier.toUpperCase()}`} · ${labelize(buyer.temperature)}` : "Not recorded"}</dd></div>
            <div><dt>Markets</dt><dd>{markets || buyer?.criteria?.markets || "Not recorded"}</dd></div>
            <div><dt>Price range</dt><dd>{priceRange}</dd></div>
            <div><dt>Strategies</dt><dd>{buyBox?.criteria.strategies.length ? buyBox.criteria.strategies.map(labelize).join(", ") : "Not recorded"}</dd></div>
            <div><dt>Proof of funds</dt><dd>{buyer ? labelize(buyer.proof_of_funds_status) : "Not recorded"}</dd></div>
            <div><dt>Last contact</dt><dd>{buyer?.last_contact_at ? localDateTime(buyer.last_contact_at) : "No contact recorded"}</dd></div>
            <div><dt>Next follow-up</dt><dd>{buyer?.next_follow_up_at ? localDateTime(buyer.next_follow_up_at) : "None scheduled"}</dd></div>
            <div><dt>Performance</dt><dd>{buyer ? `${buyer.completed_deals} closed · ${buyer.failed_deals} failed` : "Not recorded"}</dd></div>
          </dl>
          {buyer?.notes ? <section className={styles.relationshipNotes}><span>Relationship notes</span><p>{buyer.notes}</p></section> : null}
          {buyer?.tags.length ? <div className={styles.relationshipTags}>{buyer.tags.slice(0, 6).map((tag) => <span key={tag}>{tag}</span>)}</div> : null}
        </>
      )}
      <Link href={`/os/buyers?buyer=${encodeURIComponent(candidate.buyer_id)}`}>Open and update full relationship <ArrowRight size={13} /></Link>
    </aside>
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
