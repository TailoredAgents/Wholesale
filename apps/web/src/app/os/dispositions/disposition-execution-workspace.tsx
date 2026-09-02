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
  DispositionExecutionCandidate,
  DispositionExecutionShowing,
  DispositionExecutionWorkspace,
  DispositionPackageShareLinkIssued,
} from "../../lib/api";
import { useWebPhone } from "../_components/web-phone-provider";
import { labelize } from "../os-utils";
import styles from "./disposition-execution-workspace.module.css";

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
  canEditDeals,
  caseId,
  downloadPackage,
  onMessage,
  onWorkspaceChanged,
  request,
}: {
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
  const [selectedBuyerId, setSelectedBuyerId] = useState<string | null>(null);
  const [callCountdown, setCallCountdown] = useState<number | null>(null);
  const [countdownBuyerId, setCountdownBuyerId] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [callbackAt, setCallbackAt] = useState("");
  const [selectedOutcome, setSelectedOutcome] = useState<Outcome | null>(null);
  const [savedOutcome, setSavedOutcome] = useState<{ buyerId: string; label: string } | null>(null);
  const [sessionPaused, setSessionPaused] = useState(false);
  const [sessionSkippedBuyerIds, setSessionSkippedBuyerIds] = useState<string[]>([]);
  const callCountdownTimer = useRef<number | null>(null);
  const buyerIdRef = useRef<string | null>(null);
  const webPhone = useWebPhone();
  const browserCallActive = webPhone.status.callActive;
  const browserCallActiveRef = useRef(browserCallActive);
  const [outcomeIdempotencyKey, setOutcomeIdempotencyKey] = useState(() =>
    idempotency("dispo-outcome"),
  );

  const applyWorkspace = useCallback((
    result: DispositionExecutionWorkspace,
    { advance = false }: { advance?: boolean } = {},
  ) => {
    const candidates = executionCandidates(result);
    const nextCandidate = (!advance
      ? candidates.find(
        (candidate) => candidate.buyer_id === buyerIdRef.current && candidate.actionable,
      )
      : null)
      ?? (result.current_candidate?.actionable ? result.current_candidate : null)
      ?? candidates.find((candidate) => candidate.actionable)
      ?? null;
    const nextBuyerId = nextCandidate?.buyer_id ?? null;
    if (buyerIdRef.current !== nextBuyerId) {
      buyerIdRef.current = nextBuyerId;
      setOutcomeIdempotencyKey(idempotency("dispo-outcome"));
      setSmsComposerOpen(false);
      setCallCountdown(null);
      setCountdownBuyerId(null);
      setNotes("");
      setCallbackAt("");
      setSelectedOutcome(null);
      setSavedOutcome(null);
      setSmsDraft(nextCandidate?.sms_draft ?? "");
      if (callCountdownTimer.current !== null) {
        window.clearInterval(callCountdownTimer.current);
        callCountdownTimer.current = null;
      }
    }
    setSelectedBuyerId(nextBuyerId);
    setWorkspace(result);
  }, []);

  function chooseCandidate(buyerId: string) {
    const nextCandidate = executionCandidates(workspace).find((candidate) => candidate.buyer_id === buyerId);
    if (!nextCandidate || buyerIdRef.current === buyerId) return;
    if (callCountdownTimer.current !== null) {
      window.clearInterval(callCountdownTimer.current);
      callCountdownTimer.current = null;
    }
    buyerIdRef.current = buyerId;
    setSelectedBuyerId(buyerId);
    setOutcomeIdempotencyKey(idempotency("dispo-outcome"));
    setSmsComposerOpen(false);
    setCallCountdown(null);
    setCountdownBuyerId(null);
    setNotes("");
    setCallbackAt("");
    setSelectedOutcome(null);
    setSavedOutcome(null);
    setSmsDraft(nextCandidate.sms_draft);
    onMessage(`Working ${nextCandidate.name}. Buyer Network context remains visible.`);
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
    await action(
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
    await action(
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
    }
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
    );
    if (result) {
      if (advance === "next") {
        applyWorkspace(result, { advance: true });
      } else {
        setWorkspace(result);
        setSavedOutcome({ buyerId: candidate.buyer_id, label: labelize(outcome) });
      }
    }
  }

  function continueToNextBuyer() {
    if (!workspace || !savedOutcome) return;
    applyWorkspace(workspace, { advance: true });
  }

  function skipCurrentBuyer() {
    const candidate = selectedCandidate(workspace, buyerIdRef.current);
    if (!candidate || !workspace) return;
    const skippedBuyerIds = new Set([...sessionSkippedBuyerIds, candidate.buyer_id]);
    const nextCandidate = nextActionableCandidate(
      executionCandidates(workspace),
      candidate.buyer_id,
      skippedBuyerIds,
    );
    setSessionSkippedBuyerIds([...skippedBuyerIds]);
    if (!nextCandidate) {
      onMessage("No other unskipped investor is available in this browser session. You can choose anyone directly from the queue.");
      return;
    }
    chooseCandidate(nextCandidate.buyer_id);
    onMessage(`${candidate.name} was skipped for this browser session. No buyer record or outcome was changed.`);
  }

  function pauseSession() {
    if (callCountdownTimer.current !== null) {
      window.clearInterval(callCountdownTimer.current);
      callCountdownTimer.current = null;
    }
    setCallCountdown(null);
    setCountdownBuyerId(null);
    setSessionPaused(true);
    onMessage("Outreach is paused in this open browser session. No message, call, or buyer outcome was changed.");
  }

  function resumeSession() {
    setSessionPaused(false);
    onMessage("Outreach resumed at the same investor in this open browser session.");
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
    if (result) applyWorkspace(result);
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
    if (result) applyWorkspace(result);
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
  const nextCandidate = candidate
    ? nextActionableCandidate(candidates, candidate.buyer_id, skippedBuyerIds)
    : null;
  const outcomeNeedsCallback = selectedOutcome === "callback" && !callbackAt;

  return (
    <section aria-label="Disposition call queue" className={styles.workspace} id="call-queue" tabIndex={-1}>
      <header className={styles.hero}>
        <div>
          <span>One-to-one investor outreach</span>
          <h3>Outreach session</h3>
          <p>SMS, call, record the result, then decide whether to stay, advance, skip, or pause.</p>
        </div>
        <div className={styles.heroActions}>
          <div><strong>{queuePosition || "–"}</strong><span>of {candidates.length || 0}</span><small>queue position</small></div>
          {workspace.package_pdf_path ? <button className={styles.secondary} disabled={busy !== null} onClick={() => void downloadPackage(workspace.package_pdf_path!)} type="button"><Download size={15} />Open {packageLabel} packet</button> : null}
          <button aria-label="Refresh disposition call queue" className={styles.secondary} disabled={busy !== null || loading} onClick={() => void load()} type="button"><RefreshCw size={15} />Refresh</button>
          {sessionPaused
            ? <button onClick={resumeSession} type="button"><Play size={15} />Resume session</button>
            : <button className={styles.secondary} disabled={busy !== null} onClick={pauseSession} type="button"><Pause size={15} />Pause session</button>}
        </div>
      </header>

      {sessionPaused ? <div className={styles.pausedBanner} role="status"><Pause size={18} /><div><strong>Session paused at {candidate?.name ?? "the current queue position"}</strong><span>This pause lasts while this screen stays open. Durable resume across visits is Phase 3.</span></div><button onClick={resumeSession} type="button"><Play size={15} />Resume</button></div> : null}

      {workspace.blockers.length ? (
        <details className={styles.advisoryDetails}>
          <summary><ShieldAlert size={16} />Advisory deal checklist <strong>{workspace.blockers.length}</strong></summary>
          <div>{workspace.blockers.map((item) => <span key={item}>{item}</span>)}<small>These items do not prevent work. Contact controls still follow each investor&apos;s live channel permissions.</small></div>
        </details>
      ) : null}

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
                <li data-ready={candidate.actionable && candidate.sms.allowed}><span>1</span><div><strong>SMS</strong><small>{candidate.sms.allowed ? "Ready to review" : "Unavailable"}</small></div></li>
                <li data-ready={candidate.actionable && candidate.voice.allowed}><span>2</span><div><strong>Call</strong><small>{candidate.voice.allowed ? "Browser or cellphone" : "Unavailable"}</small></div></li>
                <li data-ready={Boolean(candidate.email)}><span>3</span><div><strong>Email</strong><small>{candidate.email ? "Address ready; composer arrives in Phase 4" : "No email recorded"}</small></div></li>
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
                    <label><span>Editable message</span><textarea aria-label="Introduction SMS draft" onChange={(event) => setSmsDraft(event.target.value)} rows={5} value={smsDraft} /></label>
                    <small className={styles.characterCount}>{smsDraft.trim().length} characters</small>
                    <div className={styles.composerActions}>
                      <button className={styles.secondary} disabled={busy === "sms"} onClick={() => setSmsComposerOpen(false)} type="button">Cancel</button>
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
                <p className={styles.help}>{candidate.email ? `${candidate.email} is ready. Phase 4 adds the editable one-to-one email draft and send control here.` : "Add an email to the relationship profile before using the Phase 4 email composer."}</p>
                <div className={styles.packetActions}><button disabled={packetUnavailable} onClick={() => void sendApprovedPacket()} type="button"><MessageSquareText size={16} />{busy === "packet-sms" ? "Sending packet…" : `Text ${packageLabel} packet now`}</button></div>
              </div>
            </section>

            <section className={`${styles.panel} ${styles.outcomePanel}`}>
              <div className={styles.sectionTitle}><SkipForward size={18} /><div><span>Record result</span><h4>Choose the outcome, then choose what happens next</h4></div></div>
              <div className={styles.outcomeInputs}>
                <label><span>Call notes</span><textarea disabled={outcomeSavedForCurrent || sessionPaused} onChange={(event) => setNotes(event.target.value)} placeholder="Interest, buy box, objections, requested next step…" rows={3} value={notes} /></label>
                <label><span>Callback time</span><input disabled={outcomeSavedForCurrent || sessionPaused} onChange={(event) => setCallbackAt(event.target.value)} type="datetime-local" value={callbackAt} /><small>Required for Callback. No answer creates a 4-hour retry; voicemail creates a 24-hour follow-up.</small></label>
              </div>
              <div className={styles.outcomes}>{OUTCOMES.map((outcome) => <button aria-pressed={selectedOutcome === outcome.value} data-selected={selectedOutcome === outcome.value} data-tone={outcome.tone} disabled={roleOrBusyDisabled} key={outcome.value} onClick={() => setSelectedOutcome(outcome.value)} type="button">{outcome.label}</button>)}</div>
              {outcomeSavedForCurrent ? (
                <div className={styles.savedOutcome} role="status"><CheckCircle2 size={18} /><div><strong>{savedOutcome?.label} saved</strong><span>You are still on {candidate.name}. Continue when you are ready.</span></div><button onClick={continueToNextBuyer} type="button">Next investor <ArrowRight size={15} /></button></div>
              ) : (
                <div className={styles.outcomeActions}>
                  <button className={styles.secondary} disabled={roleOrBusyDisabled || !callbackAt} onClick={() => { setSelectedOutcome("callback"); void recordOutcome("callback", "stay"); }} type="button"><CalendarClock size={15} />Schedule follow-up</button>
                  <button className={styles.secondary} disabled={busy !== null || sessionPaused} onClick={skipCurrentBuyer} type="button"><SkipForward size={15} />Skip for now</button>
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
            <p className={styles.queueGuidance}>Ranking is guidance. Choose any investor; unavailable channel controls remain enforced individually.</p>
            <ol className={styles.rankedPool}>
              {candidates.map((item) => {
                const selected = item.buyer_id === candidate.buyer_id;
                const skipped = skippedBuyerIds.has(item.buyer_id);
                return (
                  <li key={item.buyer_id}>
                    <button aria-current={selected ? "true" : undefined} className={styles.rankedBuyer} data-actionable={item.actionable} data-selected={selected} data-skipped={skipped} disabled={busy !== null || sessionPaused} onClick={() => chooseCandidate(item.buyer_id)} type="button">
                      <span className={styles.rankedBuyerRank} data-ranked={hasRankedFit(item)}>{candidateRankLabel(item)}</span>
                      <span className={styles.rankedBuyerIdentity}><strong>{item.name}</strong><small>{skipped ? "Skipped this session" : item.company_name ?? candidateAvailabilityLabel(item)}</small></span>
                      <strong className={styles.rankedBuyerScore} data-ranked={hasRankedFit(item)}>{candidateFitLabel(item)}</strong>
                    </button>
                  </li>
                );
              })}
            </ol>
            <footer><span>Next up</span><strong>{nextCandidate?.name ?? "Choose anyone in the queue"}</strong></footer>
          </aside>
        </div>
      ) : <section className={styles.panel}><div className={styles.empty}><UserRound size={28} /><strong>No buyer is available for one-to-one work</strong><span>Review the visible Buyer Network records and their contact controls, or add another canonical buyer.</span></div></section>}

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
