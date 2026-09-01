"use client";

import {
  CalendarClock,
  CheckCircle2,
  Download,
  Headphones,
  MessageSquareText,
  PhoneCall,
  RefreshCw,
  ShieldAlert,
  SkipForward,
  UserRound,
} from "lucide-react";
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
  const callCountdownTimer = useRef<number | null>(null);
  const buyerIdRef = useRef<string | null>(null);
  const webPhone = useWebPhone();
  const browserCallActive = webPhone.status.callActive;
  const browserCallActiveRef = useRef(browserCallActive);
  const [outcomeIdempotencyKey, setOutcomeIdempotencyKey] = useState(() =>
    idempotency("dispo-outcome"),
  );

  const applyWorkspace = useCallback((result: DispositionExecutionWorkspace) => {
    const candidates = executionCandidates(result);
    const nextCandidate = candidates.find(
      (candidate) => candidate.buyer_id === buyerIdRef.current && candidate.actionable,
    )
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

  async function recordOutcome(outcome: Outcome) {
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
      `${labelize(outcome)} recorded. The queue moved to the next available buyer.`,
    );
    if (result) {
      applyWorkspace(result);
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
  const roleOrBusyDisabled = busy !== null || !canEditDeals || !candidate?.actionable;
  const smsUnavailable = roleOrBusyDisabled || !candidate?.sms.allowed;
  const voiceUnavailable = roleOrBusyDisabled || !candidate?.voice.allowed || webPhone.busy || browserCallActive;
  const packetUnavailable = smsUnavailable || !workspace.package_pdf_path;
  const packageIsPreliminary = workspace.package_is_preliminary
    ?? workspace.package_status !== "approved";
  const packageLabel = packageIsPreliminary ? "preliminary" : "approved";

  return (
    <section aria-label="Disposition call queue" className={styles.workspace} id="call-queue" tabIndex={-1}>
      <header className={styles.hero}>
        <div>
          <span>One-to-one buyer execution</span>
          <h3>Disposition call queue</h3>
          <p>{workspace.property_address}</p>
        </div>
        <div className={styles.heroActions}>
          <strong>{workspace.remaining_candidate_count}</strong>
          <span>buyers available</span>
          <button aria-label="Refresh disposition call queue" disabled={busy !== null || loading} onClick={() => void load()} type="button"><RefreshCw size={15} />Refresh</button>
        </div>
      </header>

      {candidates.length ? (
        <section aria-labelledby="buyer-network-heading" className={styles.buyerSelector}>
          <div className={styles.selectorIntroduction}>
            <span>Buyer Network</span>
            <h4 id="buyer-network-heading">Work the buyer who makes sense now</h4>
            <p>Ranked fit is guidance, not a queue gate. Unranked network buyers remain available for deliberate one-to-one work.</p>
          </div>
          <label className={styles.selectorControl}>
            <span>Active buyer</span>
            <select
              aria-label="Choose a buyer from Buyer Network"
              disabled={busy !== null}
              onChange={(event) => chooseCandidate(event.target.value)}
              value={candidate?.buyer_id ?? ""}
            >
              {!candidate ? <option disabled value="">Select a buyer</option> : null}
              {candidates.map((item) => (
                <option key={item.buyer_id} value={item.buyer_id}>
                  {hasRankedFit(item)
                    ? `${candidateRankLabel(item)} ${item.name} - ${candidateFitLabel(item)} fit`
                    : `${item.name} - Buyer Network / Unranked`}
                </option>
              ))}
            </select>
          </label>
          <ol className={styles.rankedPool}>
            {candidates.map((item) => {
              const selected = item.buyer_id === candidate?.buyer_id;
              return (
                <li key={item.buyer_id}>
                  <button
                    aria-current={selected ? "true" : undefined}
                    className={styles.rankedBuyer}
                    data-actionable={item.actionable}
                    data-selected={selected}
                    disabled={busy !== null}
                    onClick={() => chooseCandidate(item.buyer_id)}
                    type="button"
                  >
                    <span className={styles.rankedBuyerRank} data-ranked={hasRankedFit(item)}>{candidateRankLabel(item)}</span>
                    <span className={styles.rankedBuyerIdentity}>
                      <strong>{item.name}</strong>
                      <small>{item.company_name ?? "Independent investor"}</small>
                    </span>
                    <span className={styles.rankedBuyerChannels}>
                      <small data-allowed={item.actionable}>{candidateAvailabilityLabel(item)}</small>
                      <small data-allowed={item.actionable && item.sms.allowed}>SMS {item.actionable && item.sms.allowed ? "ready" : "unavailable"}</small>
                      <small data-allowed={item.actionable && item.voice.allowed}>Call {item.actionable && item.voice.allowed ? "ready" : "unavailable"}</small>
                    </span>
                    <strong className={styles.rankedBuyerScore} data-ranked={hasRankedFit(item)}>{candidateFitLabel(item)}</strong>
                  </button>
                </li>
              );
            })}
          </ol>
        </section>
      ) : null}

      {workspace.blockers.length ? (
        <div className={styles.blockers} role="status">
          <ShieldAlert size={19} />
          <div><strong>Advisory checklist</strong>{workspace.blockers.map((item) => <span key={item}>{item}</span>)}<span>These items do not prevent logging work. Contact controls still follow the buyer&apos;s live channel permissions.</span></div>
        </div>
      ) : null}

      {candidate ? (
        <div className={styles.executionGrid}>
          <section className={styles.panel}>
            <div className={styles.candidateHeader}>
              <div className={styles.rank} data-ranked={hasRankedFit(candidate)}>{candidateRankLabel(candidate)}</div>
              <div><span>Current buyer</span><h4>{candidate.name}</h4><p>{candidate.company_name ?? "Independent investor"}</p></div>
              <div className={styles.score} data-ranked={hasRankedFit(candidate)}><strong>{candidateFitLabel(candidate)}</strong><span>{hasRankedFit(candidate) ? "fit score" : "Unranked"}</span></div>
            </div>
            {!candidate.actionable ? <div className={styles.candidateState} data-dnc={isDoNotContact(candidate)}><strong>{candidateAvailabilityLabel(candidate)}</strong><span>{candidate.action_blockers.join(" ") || "This buyer is not currently actionable."}</span></div> : null}
            <dl className={styles.profile}>
              <div><dt>Phone</dt><dd>{candidate.phone ?? "Not recorded"}</dd></div>
              <div><dt>Email</dt><dd>{candidate.email ?? "Not recorded"}</dd></div>
              <div><dt>Relationship</dt><dd>{labelize(candidate.relationship_status ?? "unknown")}</dd></div>
              <div><dt>Nearby purchase</dt><dd>{candidate.recent_purchase_reference ?? "No address-level reference saved"}</dd></div>
            </dl>
            <div className={styles.evidence}>
              <strong>{hasRankedFit(candidate) ? "Why this buyer ranks here" : "Buyer Network / Unranked"}</strong>
              {hasRankedFit(candidate)
                ? candidate.score_explanation.slice(0, 5).map((item) => <p key={item}><CheckCircle2 size={14} />{item}</p>)
                : <p><UserRound size={14} />This canonical Buyer Network record has not been scored by a ranking run. No rank or fit score is implied.</p>}
            </div>
            {isPassedCandidate(candidate) && !isDoNotContact(candidate) && candidate.candidate_id && candidate.lock_version !== null ? <button className={styles.secondary} disabled={busy !== null || !canEditDeals} onClick={() => void clearPass()} type="button">{busy === "clear-pass" ? "Clearing pass…" : "Clear pass"}</button> : null}
            {workspace.package_pdf_path ? <button className={styles.secondary} disabled={busy !== null} onClick={() => void downloadPackage(workspace.package_pdf_path!)} type="button"><Download size={15} />Open {packageLabel} investor packet</button> : null}
          </section>

          <section className={styles.panel}>
            <div className={styles.sectionTitle}><MessageSquareText size={18} /><div><span>Step 1</span><h4>Review the introduction text</h4></div></div>
            <p className={styles.help}>Nothing sends automatically. Open the draft, personalize it, then confirm the final message.</p>
            <PermissionLine allowed={candidate.actionable && candidate.sms.allowed} blockers={[...candidate.action_blockers, ...candidate.sms.blockers]} channel="SMS" status={candidate.sms.status} />

            {!smsComposerOpen ? (
              <button
                disabled={smsUnavailable}
                onClick={() => setSmsComposerOpen(true)}
                type="button"
              >
                <MessageSquareText size={16} />Review introduction text
              </button>
            ) : (
              <div className={styles.smsComposer}>
                <div className={styles.messageContext}>
                  <div><span>Recipient</span><strong>{candidate.name}</strong><small>{candidate.phone ?? "No phone recorded"}</small></div>
                  <div><span>Property</span><strong>{workspace.property_address}</strong><small>{hasRankedFit(candidate) ? `Ranked buyer ${candidateRankLabel(candidate)}` : "Buyer Network / Unranked"}</small></div>
                </div>
                <label>
                  <span>Editable message</span>
                  <textarea aria-label="Introduction SMS draft" onChange={(event) => setSmsDraft(event.target.value)} rows={6} value={smsDraft} />
                </label>
                <small className={styles.characterCount}>{smsDraft.trim().length} characters</small>
                <div className={styles.composerActions}>
                  <button
                    className={styles.secondary}
                    disabled={busy === "sms"}
                    onClick={() => setSmsComposerOpen(false)}
                    type="button"
                  >
                    Cancel
                  </button>
                  <button disabled={smsUnavailable || !smsDraft.trim()} onClick={() => void sendSms()} type="button">
                    <MessageSquareText size={16} />
                    {busy === "sms" ? "Sending…" : "Send text and prepare call"}
                  </button>
                </div>
              </div>
            )}

            {callCountdown !== null && countdownBuyerId === candidate.buyer_id ? (
              <div aria-live="polite" className={styles.callCountdown} role="status">
                <div className={styles.countdownNumber}>{callCountdown}</div>
                <div>
                  <strong>Introduction accepted</strong>
                  <span>Calling {candidate.name} in {callCountdown} second{callCountdown === 1 ? "" : "s"}.</span>
                </div>
                <div className={styles.countdownActions}>
                  <button disabled={voiceUnavailable} onClick={() => void startBrowserCall()} type="button">Call now</button>
                  <button className={styles.secondary} disabled={busy !== null} onClick={cancelPreparedCall} type="button">Cancel</button>
                </div>
              </div>
            ) : null}

            <div className={styles.divider} />
            <div className={styles.sectionTitle}><Headphones size={18} /><div><span>Step 2</span><h4>Call from the Stonegate line</h4></div></div>
            <p className={styles.help}>Browser calling is preferred for this deliberate one-at-a-time queue. Your cellphone remains available as a fallback.</p>
            <PermissionLine allowed={candidate.actionable && candidate.voice.allowed} blockers={[...candidate.action_blockers, ...candidate.voice.blockers]} channel="Call" status={candidate.voice.status} />
            <div className={styles.callActions}>
              <button disabled={voiceUnavailable} onClick={() => void startBrowserCall()} type="button"><Headphones size={16} />{busy === "browser-call" || webPhone.busy ? "Starting browser call…" : browserCallActive ? "Browser call in progress" : `Call ${candidate.name} in browser`}</button>
              <button className={styles.secondary} disabled={voiceUnavailable} onClick={() => void startCellphoneCall()} type="button"><PhoneCall size={16} />{busy === "cellphone-call" ? "Calling your cellphone…" : "Call through my cellphone"}</button>
            </div>
            <div className={styles.divider} />
            <div className={styles.sectionTitle}><Download size={18} /><div><span>While connected</span><h4>Send the available investor packet</h4></div></div>
            <p className={styles.help}>Creates a revocable link to the exact buyer-safe PDF and texts it only to this buyer. An incomplete version is labeled Preliminary.</p>
            <button disabled={packetUnavailable} onClick={() => void sendApprovedPacket()} type="button"><MessageSquareText size={16} />{busy === "packet-sms" ? "Sending packet…" : `Text ${packageLabel} packet`}</button>
          </section>

          <section className={`${styles.panel} ${styles.fullWidth}`}>
            <div className={styles.sectionTitle}><SkipForward size={18} /><div><span>Step 3</span><h4>Record the result and move to the next buyer</h4></div></div>
            <div className={styles.outcomeInputs}>
              <label><span>Call notes</span><textarea onChange={(event) => setNotes(event.target.value)} placeholder="Interest, buy box, objections, requested next step…" rows={3} value={notes} /></label>
              <label><span>Callback time</span><input onChange={(event) => setCallbackAt(event.target.value)} type="datetime-local" value={callbackAt} /><small>Required only for Callback. No-answer gets a 4-hour retry task; voicemail gets a 24-hour task.</small></label>
            </div>
            <div className={styles.outcomes}>{OUTCOMES.map((outcome) => <button data-tone={outcome.tone} disabled={roleOrBusyDisabled} key={outcome.value} onClick={() => void recordOutcome(outcome.value)} type="button">{outcome.label}</button>)}</div>
          </section>

          <section className={`${styles.panel} ${styles.fullWidth}`}>
            <div className={styles.sectionTitle}><CalendarClock size={18} /><div><span>Showing control</span><h4>Schedule access without placing codes in outreach</h4></div></div>
            <form className={styles.showingForm} onSubmit={createShowing}>
              <label><span>Date and time</span><input name="scheduled_at" required type="datetime-local" /></label>
              <label><span>Access state</span><select defaultValue="pending" name="access_status"><option value="pending">Access pending</option><option value="confirmed">Access confirmed</option><option value="shared_privately">Shared privately</option><option value="not_required">No access needed</option><option value="not_requested">Not requested</option></select></label>
              <label className={styles.wide}><span>Internal notes</span><input name="showing_notes" placeholder="Do not enter lockbox or alarm codes here." /></label>
              <button disabled={roleOrBusyDisabled} type="submit"><CalendarClock size={16} />Schedule showing</button>
            </form>
          </section>
        </div>
      ) : <section className={styles.panel}><div className={styles.empty}><UserRound size={28} /><strong>No buyer is available for one-to-one work</strong><span>Review the visible Buyer Network records and their contact controls, or add another canonical buyer.</span></div></section>}

      {workspace.showings.length ? <section className={styles.panel}><div className={styles.sectionTitle}><CalendarClock size={18} /><div><span>Structured showing state</span><h4>Buyer access and follow-up</h4></div></div><div className={styles.showingList}>{workspace.showings.map((showing) => <ShowingRow busy={busy === `showing-${showing.id}`} canEdit={canEditDeals} key={showing.id} onUpdate={updateShowing} showing={showing} />)}</div></section> : null}
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
