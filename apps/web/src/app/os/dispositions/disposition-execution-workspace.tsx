"use client";

import {
  CalendarClock,
  CheckCircle2,
  Download,
  MessageSquareText,
  PhoneCall,
  RefreshCw,
  ShieldAlert,
  SkipForward,
  UserRound,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

import type {
  DispositionExecutionShowing,
  DispositionExecutionWorkspace,
  DispositionPackageShareLinkIssued,
} from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./disposition-execution-workspace.module.css";

type Requester = <T>(path: string, options?: RequestInit) => Promise<T>;
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

export function DispositionExecutionWorkspace({
  canEditDeals,
  caseId,
  downloadPackage,
  onMessage,
  request,
}: {
  canEditDeals: boolean;
  caseId: string;
  downloadPackage: (path: string) => Promise<void>;
  onMessage: (message: string | null) => void;
  request: Requester;
}) {
  const [workspace, setWorkspace] = useState<DispositionExecutionWorkspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [smsDraft, setSmsDraft] = useState("");
  const [notes, setNotes] = useState("");
  const [callbackAt, setCallbackAt] = useState("");
  const [outcomeIdempotencyKey, setOutcomeIdempotencyKey] = useState(() =>
    idempotency("dispo-outcome"),
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await request<DispositionExecutionWorkspace>(
        `/api/v1/dispositions/cases/${caseId}/execution`,
      );
      setWorkspace(result);
      setSmsDraft(result.current_candidate?.sms_draft ?? "");
    } catch (error) {
      onMessage(error instanceof Error ? error.message : "Disposition call queue could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [caseId, onMessage, request]);

  useEffect(() => {
    void load();
  }, [load]);

  const currentCandidateId = workspace?.current_candidate?.candidate_id ?? null;
  useEffect(() => {
    if (currentCandidateId) {
      setOutcomeIdempotencyKey(idempotency("dispo-outcome"));
    }
  }, [currentCandidateId]);

  async function action<T>(key: string, operation: () => Promise<T>, success: string) {
    setBusy(key);
    onMessage(null);
    try {
      const result = await operation();
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
    const candidate = workspace?.current_candidate;
    if (!candidate) return;
    const result = await action(
      "sms",
      () => request(`/api/v1/dispositions/cases/${caseId}/execution/sms`, {
        method: "POST",
        body: JSON.stringify({
          candidate_id: candidate.candidate_id,
          body: smsDraft,
          idempotency_key: idempotency("dispo-sms"),
        }),
      }),
      `Pre-call text accepted for ${candidate.name}.`,
    );
    if (result) await load();
  }

  async function startCall() {
    const candidate = workspace?.current_candidate;
    if (!candidate) return;
    await action(
      "call",
      () => request(`/api/v1/dispositions/cases/${caseId}/execution/calls`, {
        method: "POST",
        body: JSON.stringify({
          candidate_id: candidate.candidate_id,
          idempotency_key: idempotency("dispo-call"),
        }),
      }),
      `Stonegate is calling your cellphone first, then connecting ${candidate.name}.`,
    );
  }

  async function sendApprovedPacket() {
    const candidate = workspace?.current_candidate;
    if (!candidate || !workspace?.package_pdf_path) return;
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
        await request(`/api/v1/dispositions/cases/${caseId}/execution/sms`, {
          method: "POST",
          body: JSON.stringify({
            candidate_id: candidate.candidate_id,
            body: `Hey ${firstName}, here is the approved property package for ${workspace.property_address}: ${issued.share_url}`,
            idempotency_key: idempotency("dispo-packet-sms"),
          }),
        });
        return issued;
      },
      `Approved investor packet text accepted for ${candidate.name}. The secure link expires in 72 hours. If delivery is ever uncertain, check the buyer conversation before retrying.`,
    );
    if (result) await load();
  }

  async function recordOutcome(outcome: Outcome) {
    const candidate = workspace?.current_candidate;
    if (!candidate) return;
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
            candidate_id: candidate.candidate_id,
            outcome,
            notes: notes.trim() || null,
            follow_up_at: outcome === "callback" ? new Date(callbackAt).toISOString() : null,
            idempotency_key: outcomeIdempotencyKey,
          }),
        },
      ),
      `${labelize(outcome)} recorded. The queue moved to the next ranked buyer.`,
    );
    if (result) {
      setWorkspace(result);
      setSmsDraft(result.current_candidate?.sms_draft ?? "");
      setNotes("");
      setCallbackAt("");
    }
  }

  async function createShowing(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const candidate = workspace?.current_candidate;
    if (!candidate) return;
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
            candidate_id: candidate.candidate_id,
            scheduled_at: new Date(scheduledAt).toISOString(),
            access_status: String(form.get("access_status") ?? "pending"),
            notes: String(form.get("showing_notes") ?? "").trim() || null,
            idempotency_key: `dispo-showing-${candidate.candidate_id}-${new Date(scheduledAt).toISOString()}`,
          }),
        },
      ),
      `Showing scheduled with ${candidate.name}. Record the call outcome when the conversation ends.`,
    );
    if (result) setWorkspace(result);
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
    if (result) setWorkspace(result);
  }

  if (loading) {
    return <section className={styles.panel}><p className={styles.empty}>Loading the disposition call queue…</p></section>;
  }
  if (!workspace) return null;

  const candidate = workspace.current_candidate;
  const disabled = busy !== null || !canEditDeals;

  return (
    <section aria-label="Disposition call queue" className={styles.workspace}>
      <header className={styles.hero}>
        <div>
          <span>One-to-one buyer execution</span>
          <h3>Disposition call queue</h3>
          <p>{workspace.property_address}</p>
        </div>
        <div className={styles.heroActions}>
          <strong>{workspace.remaining_candidate_count}</strong>
          <span>ranked buyers remaining</span>
          <button aria-label="Refresh disposition call queue" disabled={disabled} onClick={() => void load()} type="button"><RefreshCw size={15} />Refresh</button>
        </div>
      </header>

      {workspace.blockers.length ? (
        <div className={styles.blockers} role="status">
          <ShieldAlert size={19} />
          <div><strong>Queue needs attention</strong>{workspace.blockers.map((item) => <span key={item}>{item}</span>)}</div>
        </div>
      ) : null}

      {candidate ? (
        <div className={styles.executionGrid}>
          <section className={styles.panel}>
            <div className={styles.candidateHeader}>
              <div className={styles.rank}>#{candidate.rank}</div>
              <div><span>Current buyer</span><h4>{candidate.name}</h4><p>{candidate.company_name ?? "Independent investor"}</p></div>
              <div className={styles.score}><strong>{Math.round(candidate.score_basis_points / 100)}%</strong><span>fit score</span></div>
            </div>
            <dl className={styles.profile}>
              <div><dt>Phone</dt><dd>{candidate.phone ?? "Not recorded"}</dd></div>
              <div><dt>Email</dt><dd>{candidate.email ?? "Not recorded"}</dd></div>
              <div><dt>Relationship</dt><dd>{labelize(candidate.relationship_status ?? "unknown")}</dd></div>
              <div><dt>Nearby purchase</dt><dd>{candidate.recent_purchase_reference ?? "No address-level reference saved"}</dd></div>
            </dl>
            <div className={styles.evidence}>
              <strong>Why this buyer ranks here</strong>
              {candidate.score_explanation.slice(0, 5).map((item) => <p key={item}><CheckCircle2 size={14} />{item}</p>)}
            </div>
            {workspace.package_pdf_path ? <button className={styles.secondary} disabled={busy !== null} onClick={() => void downloadPackage(workspace.package_pdf_path!)} type="button"><Download size={15} />Open approved investor packet</button> : null}
          </section>

          <section className={styles.panel}>
            <div className={styles.sectionTitle}><MessageSquareText size={18} /><div><span>Step 1</span><h4>Permission-aware pre-call text</h4></div></div>
            <textarea aria-label="Pre-call SMS draft" onChange={(event) => setSmsDraft(event.target.value)} rows={5} value={smsDraft} />
            <PermissionLine allowed={candidate.sms.allowed} blockers={candidate.sms.blockers} channel="SMS" status={candidate.sms.status} />
            <button disabled={disabled || !candidate.sms.allowed || !smsDraft.trim()} onClick={() => void sendSms()} type="button"><MessageSquareText size={16} />{busy === "sms" ? "Sending…" : "Send pre-call text"}</button>
            <div className={styles.divider} />
            <div className={styles.sectionTitle}><PhoneCall size={18} /><div><span>Step 2</span><h4>Call from the Stonegate line</h4></div></div>
            <p className={styles.help}>This is a deliberate one-at-a-time call. Stonegate rings your cellphone first, then connects the buyer.</p>
            <PermissionLine allowed={candidate.voice.allowed} blockers={candidate.voice.blockers} channel="Call" status={candidate.voice.status} />
            <button disabled={disabled || !candidate.voice.allowed} onClick={() => void startCall()} type="button"><PhoneCall size={16} />{busy === "call" ? "Starting call…" : `Call ${candidate.name}`}</button>
            <div className={styles.divider} />
            <div className={styles.sectionTitle}><Download size={18} /><div><span>While connected</span><h4>Send the approved investor packet</h4></div></div>
            <p className={styles.help}>Creates a revocable link to the exact approved, investor-safe PDF and texts it only to this buyer.</p>
            <button disabled={disabled || !candidate.sms.allowed || !workspace.package_pdf_path} onClick={() => void sendApprovedPacket()} type="button"><MessageSquareText size={16} />{busy === "packet-sms" ? "Sending packet…" : "Text approved packet"}</button>
          </section>

          <section className={`${styles.panel} ${styles.fullWidth}`}>
            <div className={styles.sectionTitle}><SkipForward size={18} /><div><span>Step 3</span><h4>Record the result and move to the next buyer</h4></div></div>
            <div className={styles.outcomeInputs}>
              <label><span>Call notes</span><textarea onChange={(event) => setNotes(event.target.value)} placeholder="Interest, buy box, objections, requested next step…" rows={3} value={notes} /></label>
              <label><span>Callback time</span><input onChange={(event) => setCallbackAt(event.target.value)} type="datetime-local" value={callbackAt} /><small>Required only for Callback. No-answer gets a 4-hour retry task; voicemail gets a 24-hour task.</small></label>
            </div>
            <div className={styles.outcomes}>{OUTCOMES.map((outcome) => <button data-tone={outcome.tone} disabled={disabled} key={outcome.value} onClick={() => void recordOutcome(outcome.value)} type="button">{outcome.label}</button>)}</div>
          </section>

          <section className={`${styles.panel} ${styles.fullWidth}`}>
            <div className={styles.sectionTitle}><CalendarClock size={18} /><div><span>Showing control</span><h4>Schedule access without placing codes in outreach</h4></div></div>
            <form className={styles.showingForm} onSubmit={createShowing}>
              <label><span>Date and time</span><input name="scheduled_at" required type="datetime-local" /></label>
              <label><span>Access state</span><select defaultValue="pending" name="access_status"><option value="pending">Access pending</option><option value="confirmed">Access confirmed</option><option value="shared_privately">Shared privately</option><option value="not_required">No access needed</option><option value="not_requested">Not requested</option></select></label>
              <label className={styles.wide}><span>Internal notes</span><input name="showing_notes" placeholder="Do not enter lockbox or alarm codes here." /></label>
              <button disabled={disabled} type="submit"><CalendarClock size={16} />Schedule showing</button>
            </form>
          </section>
        </div>
      ) : <section className={styles.panel}><div className={styles.empty}><UserRound size={28} /><strong>No buyer is waiting in this queue</strong><span>Refresh the buyer pool or review candidates that still need Buyer Network approval.</span></div></section>}

      {workspace.showings.length ? <section className={styles.panel}><div className={styles.sectionTitle}><CalendarClock size={18} /><div><span>Structured showing state</span><h4>Buyer access and follow-up</h4></div></div><div className={styles.showingList}>{workspace.showings.map((showing) => <ShowingRow busy={busy === `showing-${showing.id}`} canEdit={canEditDeals} key={showing.id} onUpdate={updateShowing} showing={showing} />)}</div></section> : null}
    </section>
  );
}

function PermissionLine({ allowed, blockers, channel, status }: { allowed: boolean; blockers: string[]; channel: string; status: string }) {
  return <div className={allowed ? styles.permissionAllowed : styles.permissionBlocked}><span>{channel}: {labelize(status)}</span>{!allowed ? <small>{blockers.join(" ")}</small> : <small>Recorded permission and delivery controls are ready.</small>}</div>;
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
  return <article><div><strong>{showing.buyer_name}</strong><span>{localDateTime(showing.scheduled_at)}</span><small>{labelize(showing.status)} · {labelize(accessStatus)}{showing.follow_up_task_id ? " · 24-hour follow-up created" : ""}</small></div><select aria-label={`Access status for ${showing.buyer_name}`} disabled={busy || !canEdit || finished} onChange={(event) => setAccessStatus(event.target.value as DispositionExecutionShowing["access_status"])} value={accessStatus}><option value="pending">Access pending</option><option value="confirmed">Access confirmed</option><option value="shared_privately">Shared privately</option><option value="not_required">No access needed</option><option value="not_requested">Not requested</option></select><div><button disabled={busy || !canEdit || finished} onClick={() => void onUpdate(showing, "confirmed", accessStatus)} type="button">Confirm</button><button disabled={busy || !canEdit || finished} onClick={() => void onUpdate(showing, "completed", accessStatus)} type="button">Complete</button><button disabled={busy || !canEdit || finished} onClick={() => void onUpdate(showing, "no_show", accessStatus)} type="button">No show</button></div></article>;
}
