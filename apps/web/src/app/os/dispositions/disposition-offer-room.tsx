"use client";

import {
  AlertTriangle,
  ArrowRightLeft,
  BadgeDollarSign,
  CalendarClock,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleDollarSign,
  FileCheck2,
  History,
  LoaderCircle,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  Trophy,
  UserCheck,
  UsersRound,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import type {
  DispositionClosingCheckpoint,
  DispositionOfferRoomOffer,
  DispositionOfferRoomWorkspace,
} from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./disposition-offer-room.module.css";

type Request = <T>(path: string, options?: RequestInit) => Promise<T>;
type TimelineTab = "negotiation" | "selection" | "outcomes";
type PlacementStepState = "complete" | "current" | "pending" | "warning";

type PlacementStep = {
  key: string;
  label: string;
  detail: string;
  href: string;
  resolved: boolean;
  warning?: boolean;
};

type BuyerOption = {
  buyer_id: string;
  buyer_name: string;
  latest_proof_document_id: string | null;
};

function money(cents: number | null, currency = "USD") {
  if (cents == null) return "Not provided";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function cents(value: FormDataEntryValue | null) {
  const normalized = String(value ?? "").replace(/[$,]/g, "").trim();
  return normalized ? Math.round(Number(normalized) * 100) : null;
}

function optionalNumber(value: FormDataEntryValue | null) {
  const normalized = String(value ?? "").trim();
  return normalized === "" ? null : Number(normalized);
}

function iso(value: FormDataEntryValue | null) {
  const normalized = String(value ?? "").trim();
  return normalized ? new Date(normalized).toISOString() : null;
}

function dateTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : "Not provided";
}

function shortDate(value: string | null) {
  return value ? new Date(value).toLocaleDateString() : "Not provided";
}

function percent(basisPoints: number) {
  return `${Math.max(0, Math.min(100, basisPoints / 100)).toFixed(0)}%`;
}

function signedPercent(basisPoints: number) {
  return `${basisPoints > 0 ? "+" : ""}${(basisPoints / 100).toFixed(0)}%`;
}

function idempotency(prefix: string) {
  return `${prefix}:${crypto.randomUUID()}`;
}

function riskTone(score: number) {
  if (score >= 7000) return "danger";
  if (score >= 3500) return "warning";
  return "success";
}

function displayEvidence(evidence: Record<string, unknown>) {
  return Object.entries(evidence)
    .filter(([, value]) => value !== null && value !== "")
    .map(([key, value]) => `${labelize(key)}: ${Array.isArray(value) ? value.join(", ") : String(value)}`)
    .join("; ");
}

function isCheckpointOverdue(checkpoint: DispositionClosingCheckpoint) {
  return !["completed", "waived", "cancelled"].includes(checkpoint.status)
    && new Date(checkpoint.due_at).getTime() < Date.now();
}

function hasCanonicalChecklistEvidence(checkpoint: DispositionClosingCheckpoint) {
  if (checkpoint.canonical_source !== "transaction_checklist" || !checkpoint.source_record_id) return false;
  const documentId = checkpoint.evidence.evidence_document_id;
  const evidenceNotes = checkpoint.evidence.evidence_notes;
  return Boolean(
    (typeof documentId === "string" && documentId.trim())
      || (typeof evidenceNotes === "string" && evidenceNotes.trim().length >= 3),
  );
}

function PlacementPath({ steps }: { steps: PlacementStep[] }) {
  const currentIndex = steps.findIndex((step) => !step.resolved);
  const resolvedCount = steps.filter((step) => step.resolved).length;
  const nextStep = currentIndex >= 0 ? steps[currentIndex] : null;

  return (
    <section aria-labelledby="placement-path-heading" className={styles.placementPath}>
      <div className={styles.placementPathHeader}>
        <div>
          <span>Interested buyer to funded closing</span>
          <h5 id="placement-path-heading">Deal placement path</h5>
          <p>Stonegate shows the next missing step from saved evidence. Nothing is marked complete from a guess.</p>
        </div>
        <div className={styles.placementProgress}>
          <strong>{resolvedCount} of {steps.length}</strong>
          <span>steps secured</span>
        </div>
      </div>
      <ol className={styles.placementSteps}>
        {steps.map((step, index) => {
          const state: PlacementStepState = step.warning
            ? "warning"
            : step.resolved
              ? "complete"
              : index === currentIndex
                ? "current"
                : "pending";
          return (
            <li data-state={state} key={step.key}>
              <span className={styles.placementStepIcon}>
                {state === "complete" ? <Check aria-hidden="true" size={14} /> : state === "warning" ? <AlertTriangle aria-hidden="true" size={14} /> : index + 1}
              </span>
              <div>
                <strong>{step.label}</strong>
                <small>{step.detail}</small>
              </div>
              {state === "current" ? <a aria-current="step" href={step.href}>Do this next</a> : null}
            </li>
          );
        })}
      </ol>
      <div className={styles.placementNextAction} data-complete={!nextStep}>
        {nextStep ? <><ArrowRightLeft aria-hidden="true" size={16} /><div><span>Next action</span><strong>{nextStep.detail}</strong></div><a href={nextStep.href}>Open step</a></> : <><CheckCircle2 aria-hidden="true" size={17} /><div><span>Placement complete</span><strong>The funded close is preserved in buyer reliability history.</strong></div></>}
      </div>
    </section>
  );
}

function OfferCard({
  currency,
  offer,
  primaryOfferId,
  backupOfferIds,
}: {
  currency: string;
  offer: DispositionOfferRoomOffer;
  primaryOfferId: string | null;
  backupOfferIds: Set<string>;
}) {
  const isPrimary = primaryOfferId === offer.id;
  const isBackup = backupOfferIds.has(offer.id);
  const supporting_evidence = offer.risk_flags.map((flag) => displayEvidence(flag.evidence)).filter(Boolean);
  return (
    <article
      className={styles.offerCard}
      data-primary={isPrimary}
      data-recommended={offer.is_recommended}
    >
      <header className={styles.offerCardHeader}>
        <div>
          <small>Rank {offer.comparison_rank || "-"}</small>
          <strong>{offer.buyer_name}</strong>
        </div>
        <b>{money(offer.amount_cents, currency)}</b>
        <div className={styles.badges}>
          {isPrimary ? <span className={styles.badge} data-tone="success">Primary</span> : null}
          {isBackup ? <span className={styles.badge} data-tone="success">Backup</span> : null}
          {offer.is_recommended ? <span className={styles.badge} data-tone="success">Best executable evidence</span> : null}
          <span className={styles.badge} data-tone={riskTone(offer.risk_score_basis_points)}>{percent(offer.risk_score_basis_points)} risk</span>
          <span className={styles.badge}>{labelize(offer.status)}</span>
        </div>
      </header>

      <dl className={styles.comparisonFacts}>
        <div><dt>Offer amount</dt><dd>{money(offer.amount_cents, currency)}</dd></div>
        <div><dt>Earnest money</dt><dd>{money(offer.earnest_money_cents, currency)}</dd></div>
        <div><dt>Deposit due</dt><dd>{shortDate(offer.deposit_due_at)}</dd></div>
        <div><dt>Due diligence</dt><dd>{offer.due_diligence_days == null ? "Not provided" : `${offer.due_diligence_days} days`}</dd></div>
        <div><dt>Closing</dt><dd>{shortDate(offer.proposed_closing_at)}</dd></div>
        <div><dt>Funding</dt><dd>{labelize(offer.funding_method)}</dd></div>
        <div><dt>Proof of funds</dt><dd>{labelize(offer.proof_status)}{offer.proof_verified_amount_cents != null ? ` - ${money(offer.proof_verified_amount_cents, currency)}` : ""}</dd></div>
        <div><dt>Proof expires</dt><dd>{shortDate(offer.proof_expires_at)}</dd></div>
        <div><dt>Reliability</dt><dd>{percent(offer.reliability_score_basis_points)}</dd></div>
        <div><dt>Risk</dt><dd>{percent(offer.risk_score_basis_points)}</dd></div>
        <div><dt>Execution score</dt><dd>{percent(offer.execution_score_basis_points)}</dd></div>
      </dl>
      <div aria-label={`Execution score ${percent(offer.execution_score_basis_points)}`} className={styles.scoreBar} role="img">
        <span style={{ width: percent(offer.execution_score_basis_points) }} />
      </div>

      {offer.strengths.length ? (
        <div className={styles.evidenceGroup}>
          <strong>Execution strengths</strong>
          {offer.strengths.map((strength) => <p key={strength}><ShieldCheck aria-hidden="true" size={13} />{strength}</p>)}
        </div>
      ) : null}
      {offer.risk_flags.length ? (
        <div className={styles.evidenceGroup}>
          <strong>Risk flags and evidence</strong>
          {offer.risk_flags.map((flag) => (
            <p data-severity={flag.severity} key={`${flag.code}-${flag.message}`}>
              <AlertTriangle aria-hidden="true" size={13} />
              <span>{flag.message}{displayEvidence(flag.evidence) ? ` Evidence: ${displayEvidence(flag.evidence)}` : ""}</span>
            </p>
          ))}
        </div>
      ) : (
        <div className={styles.evidenceGroup}><p><CheckCircle2 aria-hidden="true" size={13} />No material execution risk is currently evidenced.</p></div>
      )}
      {offer.reliability_evidence.length ? <div className={styles.evidenceGroup}><strong>Reliability evidence</strong>{offer.reliability_evidence.map((item) => <p key={item}><ShieldCheck aria-hidden="true" size={13} />{item}</p>)}</div> : null}
      {offer.contingencies.length ? <div className={styles.evidenceGroup}><strong>Contingencies {offer.contingencies_confirmed ? "- buyer confirmed" : "- not yet confirmed"}</strong>{offer.contingencies.map((item) => <p key={item}><ShieldAlert aria-hidden="true" size={13} />{item}</p>)}</div> : <div className={styles.evidenceGroup}><strong>Contingencies</strong><p><ShieldAlert aria-hidden="true" size={13} />{offer.contingencies_confirmed ? "Buyer confirmed no contingencies." : "Unknown - buyer terms have not been confirmed."}</p></div>}
      {supporting_evidence.length ? <span hidden>{supporting_evidence.join("; ")}</span> : null}
      {offer.special_terms || offer.notes ? <p className={styles.offerNotes}>{[offer.special_terms, offer.notes].filter(Boolean).join("\n\n")}</p> : null}
    </article>
  );
}

function CheckpointRow({
  busy,
  checkpoint: deadline,
  buyerName,
  canApproveWaiver,
  canEdit,
  onDecision,
}: {
  busy: boolean;
  checkpoint: DispositionClosingCheckpoint;
  buyerName: string | null;
  canApproveWaiver: boolean;
  canEdit: boolean;
  onDecision: (checkpoint: DispositionClosingCheckpoint, status: "completed" | "waived", evidenceNote?: string) => void;
}) {
  const complete = deadline.status === "completed";
  const waived = deadline.status === "waived";
  const cancelled = deadline.status === "cancelled";
  const terminal = complete || waived || cancelled;
  const overdue = deadline.is_overdue || isCheckpointOverdue(deadline);
  const canonicalReadOnly = ["transaction", "transaction_checklist"].includes(deadline.canonical_source);
  const depositDecision = deadline.checkpoint_type === "buyer_deposit" && !canonicalReadOnly;
  const [evidenceNote, setEvidenceNote] = useState("");
  const evidenceReady = evidenceNote.trim().length >= 10;
  return (
    <article className={styles.checkpoint} data-overdue={overdue} data-status={deadline.status}>
      <span className={styles.checkpointIcon}>{terminal ? <Check aria-hidden="true" size={15} /> : overdue ? <AlertTriangle aria-hidden="true" size={15} /> : <CalendarClock aria-hidden="true" size={15} />}</span>
      <div>
        <strong>{deadline.label}</strong>
        <span>{labelize(deadline.checkpoint_type)}{deadline.buyer_name || buyerName ? ` - ${deadline.buyer_name ?? buyerName}` : ""}</span>
        <small>{complete ? `Completed ${dateTime(deadline.completed_at)}` : waived ? `Explicitly waived ${dateTime(deadline.completed_at)}` : cancelled ? "Cancelled" : overdue ? `Missed deadline - due ${dateTime(deadline.due_at)}` : `Due ${dateTime(deadline.due_at)}`}</small>
        {deadline.notes ? <small>{deadline.notes}</small> : null}
      </div>
      <div className={styles.checkpointActions}>
        {!terminal && depositDecision ? <label className={styles.depositEvidence} htmlFor={`deposit-evidence-${deadline.id}`}><span>Deposit evidence note</span><input id={`deposit-evidence-${deadline.id}`} maxLength={500} minLength={10} onChange={(event) => setEvidenceNote(event.target.value)} placeholder="Receipt, confirmation, or waiver basis (10+ characters)" value={evidenceNote} /></label> : null}
        {!terminal && depositDecision ? <div className={styles.depositDecisions}><button className={styles.inlineButton} disabled={!canEdit || busy || !evidenceReady} onClick={() => onDecision(deadline, "completed", evidenceNote.trim())} type="button"><Check size={13} />Record deposit</button><button className={styles.waiveButton} disabled={!canEdit || !canApproveWaiver || busy || !evidenceReady} onClick={() => onDecision(deadline, "waived", evidenceNote.trim())} title={!canApproveWaiver ? "Manager approval is required to waive a buyer deposit." : undefined} type="button">Waive deposit</button>{!canApproveWaiver ? <small>Manager approval is required to waive a deposit.</small> : null}</div> : null}
        {!terminal && !depositDecision && !canonicalReadOnly ? <button className={styles.inlineButton} disabled={!canEdit || busy} onClick={() => onDecision(deadline, "completed")} type="button"><Check size={13} />Complete milestone</button> : null}
        {!terminal && canonicalReadOnly ? <small>Update in Deal / Transaction</small> : null}
      </div>
    </article>
  );
}

export function DispositionOfferRoom({
  buyers,
  canApproveBuyerSelection,
  canEditDeals,
  canViewPrivateEconomics,
  caseId,
  onCaseChanged,
  onMessage,
  request,
}: {
  buyers: BuyerOption[];
  canApproveBuyerSelection: boolean;
  canEditDeals: boolean;
  canViewPrivateEconomics: boolean;
  caseId: string;
  onCaseChanged: () => Promise<unknown> | unknown;
  onMessage: (message: string) => void;
  request: Request;
}) {
  const [data, setData] = useState<DispositionOfferRoomWorkspace | null>(null);
  const [loadedCaseId, setLoadedCaseId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [timelineTab, setTimelineTab] = useState<TimelineTab>("negotiation");
  const statusRef = useRef<HTMLDivElement>(null);
  const requestRef = useRef(request);
  const loadSequenceRef = useRef(0);
  const pendingIdempotencyKeysRef = useRef(new Map<string, string>());

  function pendingIdempotencyKey(action: string, prefix: string) {
    const existing = pendingIdempotencyKeysRef.current.get(action);
    if (existing) return existing;
    const created = idempotency(prefix);
    pendingIdempotencyKeysRef.current.set(action, created);
    return created;
  }

  function clearPendingIdempotencyKey(action: string) {
    pendingIdempotencyKeysRef.current.delete(action);
  }

  useEffect(() => {
    requestRef.current = request;
  }, [request]);

  const load = useCallback(async () => {
    const sequence = ++loadSequenceRef.current;
    setLoading(true);
    setError(null);
    try {
      const workspace = await requestRef.current<DispositionOfferRoomWorkspace>(
        `/api/v1/dispositions/cases/${caseId}/offer-room`,
        { cache: "no-store" },
      );
      if (sequence !== loadSequenceRef.current) return;
      setData(workspace);
      setLoadedCaseId(caseId);
    } catch (loadError) {
      if (sequence !== loadSequenceRef.current) return;
      setError(loadError instanceof Error ? loadError.message : "Unable to load the Offer Room.");
    } finally {
      if (sequence === loadSequenceRef.current) setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    const sequence = ++loadSequenceRef.current;
    void requestRef.current<DispositionOfferRoomWorkspace>(
      `/api/v1/dispositions/cases/${caseId}/offer-room`,
      { cache: "no-store" },
    )
      .then((workspace) => {
        if (sequence !== loadSequenceRef.current) return;
        setData(workspace);
        setLoadedCaseId(caseId);
      })
      .catch((loadError: unknown) => {
        if (sequence !== loadSequenceRef.current) return;
        setError(loadError instanceof Error ? loadError.message : "Unable to load the Offer Room.");
      })
      .finally(() => {
        if (sequence === loadSequenceRef.current) setLoading(false);
      });
    return () => {
      loadSequenceRef.current += 1;
    };
  }, [caseId]);

  async function mutate(
    actionKey: string,
    work: () => Promise<DispositionOfferRoomWorkspace>,
    successMessage: string,
  ) {
    if (!canEditDeals) {
      const detail = "Your role can review the Offer Room but cannot change it.";
      setError(detail);
      onMessage(detail);
      return false;
    }
    setBusyAction(actionKey);
    setError(null);
    setSuccess(null);
    try {
      setData(await work());
      await onCaseChanged();
      setSuccess(successMessage);
      onMessage(successMessage);
      return true;
    } catch (mutationError) {
      const detail = mutationError instanceof Error ? mutationError.message : "Unable to update the Offer Room.";
      setError(detail);
      onMessage(detail);
      requestAnimationFrame(() => statusRef.current?.focus());
      return false;
    } finally {
      setBusyAction(null);
    }
  }

  async function recordOffer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const buyerId = String(values.get("buyer_id"));
    const buyer = buyers.find((item) => item.buyer_id === buyerId);
    const idempotencyAction = `offer:${caseId}`;
    const saved = await mutate(
      "offer",
      () => requestRef.current(`/api/v1/dispositions/cases/${caseId}/offer-room/offers`, {
        method: "POST",
        body: JSON.stringify({
          idempotency_key: pendingIdempotencyKey(idempotencyAction, "offer"),
          buyer_id: buyerId,
          amount_cents: cents(values.get("amount")),
          earnest_money_cents: cents(values.get("earnest_money")),
          deposit_due_at: iso(values.get("deposit_due_at")),
          due_diligence_days: optionalNumber(values.get("due_diligence_days")),
          contingencies: String(values.get("contingencies") ?? "").split(",").map((item) => item.trim()).filter(Boolean),
          contingencies_confirmed: values.get("contingencies_confirmed") === "on",
          proposed_closing_at: iso(values.get("proposed_closing_at")),
          funding_method: values.get("funding_method") || "unknown",
          funding_confidence_basis_points: Number(values.get("funding_confidence") || 0) * 100,
          proof_document_id: buyer?.latest_proof_document_id ?? null,
          special_terms: values.get("special_terms") || null,
          notes: values.get("notes") || null,
          change_reason: "Offer received and terms normalized for human comparison.",
        }),
      }),
      "Buyer offer normalized and added to the comparison.",
    );
    if (saved) {
      clearPendingIdempotencyKey(idempotencyAction);
      form.reset();
    }
  }

  async function reviseOffer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!data) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const offer = data.offers.find((item) => item.id === String(values.get("offer_id")));
    if (!offer) return;
    const buyer = normalizedBuyers.find((item) => item.buyer_id === offer.buyer_id);
    const proofDocumentId = buyer?.latest_proof_document_id ?? offer.proof_document_id;
    const idempotencyAction = `offer-revision:${caseId}:${offer.id}`;
    const payload: Record<string, unknown> = {
      idempotency_key: pendingIdempotencyKey(idempotencyAction, "offer-revision"),
      expected_lock_version: offer.lock_version,
      change_reason: values.get("revision_reason"),
    };
    const addIfEntered = (formField: string, payloadField: string, value: unknown) => {
      if (String(values.get(formField) ?? "").trim() !== "") payload[payloadField] = value;
    };
    addIfEntered("amount", "amount_cents", cents(values.get("amount")));
    addIfEntered("earnest_money", "earnest_money_cents", cents(values.get("earnest_money")));
    addIfEntered("deposit_due_at", "deposit_due_at", iso(values.get("deposit_due_at")));
    addIfEntered("due_diligence_days", "due_diligence_days", optionalNumber(values.get("due_diligence_days")));
    if (String(values.get("contingencies") ?? "").trim() !== "") {
      payload.contingencies = String(values.get("contingencies")).split(",").map((item) => item.trim()).filter(Boolean);
    }
    if (String(values.get("contingencies_confirmed") ?? "").trim() !== "") {
      payload.contingencies_confirmed = values.get("contingencies_confirmed") === "true";
    }
    addIfEntered("proposed_closing_at", "proposed_closing_at", iso(values.get("proposed_closing_at")));
    addIfEntered("funding_method", "funding_method", values.get("funding_method"));
    if (String(values.get("funding_confidence") ?? "").trim() !== "") {
      payload.funding_confidence_basis_points = Number(values.get("funding_confidence")) * 100;
    }
    addIfEntered("special_terms", "special_terms", values.get("special_terms"));
    addIfEntered("notes", "notes", values.get("notes"));
    if (proofDocumentId) payload.proof_document_id = proofDocumentId;
    const saved = await mutate(
      "revise-offer",
      () => requestRef.current(`/api/v1/dispositions/cases/${caseId}/offer-room/offers/${offer.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
      "Offer terms revised without erasing the earlier evidence.",
    );
    if (saved) {
      clearPendingIdempotencyKey(idempotencyAction);
      form.reset();
    }
  }

  async function recordNegotiation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!data) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const offer = data.offers.find((item) => item.id === String(values.get("offer_id")));
    if (!offer) return;
    const idempotencyAction = `negotiation:${caseId}:${offer.id}`;
    const saved = await mutate(
      "negotiation",
      () => requestRef.current(`/api/v1/dispositions/cases/${caseId}/offer-room/offers/${offer.id}/negotiations`, {
        method: "POST",
        body: JSON.stringify({
          idempotency_key: pendingIdempotencyKey(idempotencyAction, "negotiation"),
          event_type: values.get("event_type"),
          direction: values.get("direction"),
          summary: values.get("notes"),
          metadata: cents(values.get("proposed_amount")) == null
            ? {}
            : { proposed_amount_cents: cents(values.get("proposed_amount")) },
          occurred_at: new Date().toISOString(),
        }),
      }),
      "Negotiation history recorded.",
    );
    if (saved) {
      clearPendingIdempotencyKey(idempotencyAction);
      form.reset();
    }
  }

  async function approveSelection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canApproveBuyerSelection) {
      const detail = "Your role can compare offers but cannot approve primary or backup buyers.";
      setError(detail);
      onMessage(detail);
      return;
    }
    const form = event.currentTarget;
    const values = new FormData(form);
    const primaryOfferId = String(values.get("primary_offer_id") ?? "");
    const backupOfferId = String(values.get("backup_offer_id") ?? "");
    const primaryOffer = data?.offers.find((offer) => offer.id === primaryOfferId);
    const backupOffer = data?.offers.find((offer) => offer.id === backupOfferId);
    if (!primaryOffer || !backupOffer) {
      const detail = "Select a current primary offer and backup offer before approval.";
      setError(detail);
      onMessage(detail);
      return;
    }
    if (primaryOfferId === backupOfferId || primaryOffer.buyer_id === backupOffer.buyer_id) {
      const detail = "Primary and backup coverage must use offers from different buyers.";
      setError(detail);
      onMessage(detail);
      requestAnimationFrame(() => statusRef.current?.focus());
      return;
    }
    const idempotencyAction = `selection:${caseId}`;
    const saved = await mutate(
      "selection",
      () => requestRef.current(`/api/v1/dispositions/cases/${caseId}/offer-room/selections`, {
        method: "POST",
        body: JSON.stringify({
          idempotency_key: pendingIdempotencyKey(idempotencyAction, "selection"),
          primary_offer_id: primaryOfferId,
          backup_offer_ids: [backupOfferId],
          expected_offer_lock_versions: {
            [primaryOfferId]: primaryOffer.lock_version,
            [backupOfferId]: backupOffer.lock_version,
          },
          expected_selection_lock_version: data?.current_selection?.lock_version ?? null,
          reason: values.get("selection_reason"),
          eligibility_override_reason: values.get("eligibility_override_reason") || null,
        }),
      }),
      "Human buyer selection approved and preserved.",
    );
    if (saved) {
      clearPendingIdempotencyKey(idempotencyAction);
      form.reset();
    }
  }

  async function createCheckpoint(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const idempotencyAction = `checkpoint:${caseId}`;
    const saved = await mutate(
      "checkpoint",
      () => requestRef.current(`/api/v1/dispositions/cases/${caseId}/offer-room/checkpoints`, {
        method: "POST",
        body: JSON.stringify({
          idempotency_key: pendingIdempotencyKey(idempotencyAction, "checkpoint"),
          selection_id: data?.current_selection?.id ?? null,
          checkpoint_type: values.get("checkpoint_type"),
          label: values.get("label"),
          due_at: iso(values.get("due_at")),
          offer_id: values.get("offer_id") || null,
          notes: values.get("notes") || null,
          evidence: {},
        }),
      }),
      "Closing-protection milestone added.",
    );
    if (saved) {
      clearPendingIdempotencyKey(idempotencyAction);
      form.reset();
    }
  }

  async function completeCheckpoint(
    deadline: DispositionClosingCheckpoint,
    status: "completed" | "waived",
    evidenceNote?: string,
  ) {
    if (status === "waived" && !canApproveBuyerSelection) {
      const detail = "Manager approval is required to waive a buyer deposit.";
      setError(detail);
      onMessage(detail);
      return;
    }
    const depositDecision = deadline.checkpoint_type === "buyer_deposit";
    if (depositDecision && (!evidenceNote || evidenceNote.trim().length < 10)) {
      const detail = "Record at least 10 characters of deposit confirmation or waiver evidence first.";
      setError(detail);
      onMessage(detail);
      return;
    }
    await mutate(
      `checkpoint-${deadline.id}`,
      () => requestRef.current(`/api/v1/dispositions/cases/${caseId}/offer-room/checkpoints/${deadline.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          expected_lock_version: deadline.lock_version,
          status,
          notes: deadline.notes,
          evidence: depositDecision
            ? {
                confirmation_note: evidenceNote,
                decision: status === "completed" ? "received" : "waived",
              }
            : deadline.evidence,
          reason: depositDecision
            ? status === "completed"
              ? "Disposition specialist recorded buyer deposit receipt evidence."
              : "Disposition specialist explicitly waived the buyer deposit with evidence."
            : "Milestone completion confirmed by the disposition specialist.",
        }),
      }),
      `${deadline.label} marked ${status === "completed" ? "complete" : "waived"}.`,
    );
  }

  async function scanDeadlines() {
    await mutate(
      "scan",
      () => requestRef.current(`/api/v1/dispositions/cases/${caseId}/offer-room/deadlines/scan`, {
        method: "POST",
      }),
      "Closing deadlines refreshed and duplicate alerts suppressed.",
    );
  }

  async function acknowledgeAlert(alertId: string) {
    await mutate(
      `alert-${alertId}`,
      () => requestRef.current(`/api/v1/dispositions/cases/${caseId}/offer-room/alerts/${alertId}/acknowledge`, {
        method: "POST",
        body: JSON.stringify({ reason: "Disposition specialist reviewed the missed-deadline alert." }),
      }),
      "Deadline alert acknowledged; the underlying milestone remains visible.",
    );
  }

  async function replacePrimary(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canApproveBuyerSelection) {
      const detail = "Buyer replacement requires the buyer-selection approval permission.";
      setError(detail);
      onMessage(detail);
      return;
    }
    if (!data?.current_selection) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const idempotencyAction = `replacement:${caseId}:${data.current_selection.id}`;
    const saved = await mutate(
      "replacement",
      () => requestRef.current(`/api/v1/dispositions/cases/${caseId}/offer-room/selections/${data.current_selection?.id}/replace-primary`, {
        method: "POST",
        body: JSON.stringify({
          idempotency_key: pendingIdempotencyKey(idempotencyAction, "replacement"),
          expected_lock_version: data.current_selection?.lock_version,
          replacement_offer_id: values.get("replacement_offer_id"),
          outcome_type: values.get("outcome_type"),
          cause_category: values.get("cause_category"),
          reason: values.get("replacement_reason"),
          details: values.get("replacement_details") || null,
          evidence: {},
        }),
      }),
      "Backup buyer activated and the replaced selection preserved.",
    );
    if (saved) {
      clearPendingIdempotencyKey(idempotencyAction);
      form.reset();
    }
  }

  async function recordOutcome(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const offer = data?.offers.find((item) => item.id === String(values.get("offer_id")));
    if (!offer) return;
    const currentSelectionOfferIds = new Set([
      data?.current_selection?.primary?.offer_id,
      ...(data?.current_selection?.backups.map((item) => item.offer_id) ?? []),
    ].filter((offerId): offerId is string => Boolean(offerId)));
    const idempotencyAction = `outcome:${caseId}:${offer.id}`;
    const saved = await mutate(
      "outcome",
      () => requestRef.current(`/api/v1/dispositions/cases/${caseId}/offer-room/outcomes`, {
        method: "POST",
        body: JSON.stringify({
          idempotency_key: pendingIdempotencyKey(idempotencyAction, "outcome"),
          offer_id: offer.id,
          selection_id: currentSelectionOfferIds.has(offer.id)
            ? data?.current_selection?.id ?? null
            : null,
          outcome_type: values.get("outcome_type"),
          cause_category: values.get("cause_category"),
          reason: values.get("outcome_reason"),
          details: values.get("outcome_details") || null,
          evidence: {},
          occurred_at: new Date().toISOString(),
        }),
      }),
      "Buyer outcome recorded and retained for reliability history.",
    );
    if (saved) {
      clearPendingIdempotencyKey(idempotencyAction);
      form.reset();
    }
  }

  const seenBuyerIds = new Set<string>();
  const normalizedBuyers = buyers.filter((buyer) => {
    if (seenBuyerIds.has(buyer.buyer_id)) return false;
    seenBuyerIds.add(buyer.buyer_id);
    return true;
  });

  if (!data || loadedCaseId !== caseId) {
    if (!loading && error) {
      return <div className={styles.loadError} role="alert"><ShieldAlert aria-hidden="true" size={24} /><strong>Offer Room unavailable</strong><p>{error}</p><button onClick={() => void load()} type="button">Retry</button></div>;
    }
    return <div aria-busy="true" aria-live="polite" className={styles.loading} role="status"><LoaderCircle aria-hidden="true" className={styles.spin} size={18} />Loading Offer Room</div>;
  }

  const currentPrimary = data.current_selection?.primary ?? null;
  const currentBackups = data.current_selection?.backups ?? [];
  const closingComplete = Boolean(
    currentPrimary
      && data.outcomes.some((outcome) =>
        outcome.outcome_type === "completed_close" && outcome.offer_id === currentPrimary.offer_id,
      ),
  );
  const backupOfferIds = new Set(currentBackups.map((item) => item.offer_id));
  const offers = [...data.offers].sort((left, right) => left.comparison_rank - right.comparison_rank);
  const selectableOffers = offers.filter((offer) => ["received", "countering", "selected", "backup"].includes(offer.status));
  const selectionCoverageReady = new Set(selectableOffers.map((offer) => offer.buyer_id)).size >= 2;
  const offersById = new Map(offers.map((offer) => [offer.id, offer]));
  const currentCoverageSlots = [currentPrimary, ...currentBackups].filter((slot) => slot !== null);
  const staleCoverageSlots = closingComplete ? [] : currentCoverageSlots.filter((slot) => {
    const liveOffer = offersById.get(slot.offer_id);
    const approvedLockVersion = Number(slot.offer_snapshot.lock_version);
    return !liveOffer || !Number.isFinite(approvedLockVersion) || liveOffer.lock_version !== approvedLockVersion;
  });
  const liveCoverageBlockers = closingComplete ? [] : currentCoverageSlots.flatMap((slot) =>
    slot.readiness_blockers.map((blocker) => `${slot.buyer_name}: ${blocker}`),
  );
  const overdue = data.checkpoints.filter((checkpoint) => checkpoint.is_overdue || isCheckpointOverdue(checkpoint));
  const criticalAlerts = data.alerts.filter((alert) => alert.severity === "danger");
  const attention = criticalAlerts[0] ?? data.alerts[0] ?? null;
  const attentionCheckpoint = attention
    ? data.checkpoints.find((checkpoint) => checkpoint.id === attention.checkpoint_id) ?? null
    : null;
  const primaryOffer = currentPrimary ? offersById.get(currentPrimary.offer_id) ?? null : null;
  const offerForVerification = primaryOffer ?? offers[0] ?? null;
  const generatedAt = new Date(data.generated_at).getTime();
  const termsVerified = Boolean(
    offerForVerification
      && offerForVerification.proof_status === "verified"
      && offerForVerification.proof_verified_amount_cents != null
      && offerForVerification.proof_verified_amount_cents >= offerForVerification.amount_cents
      && offerForVerification.proof_expires_at
      && new Date(offerForVerification.proof_expires_at).getTime() > generatedAt
      && offerForVerification.proposed_closing_at
      && new Date(offerForVerification.proposed_closing_at).getTime() > generatedAt
      && offerForVerification.contingencies_confirmed,
  );
  const checkpointForPrimary = (checkpoint: DispositionClosingCheckpoint) => Boolean(
    currentPrimary
      && data.current_selection
      && checkpoint.selection_id === data.current_selection.id
      && checkpoint.offer_id === currentPrimary.offer_id,
  );
  const depositCheckpoint = data.checkpoints.find((checkpoint) =>
    checkpointForPrimary(checkpoint)
      && checkpoint.checkpoint_type === "buyer_deposit"
      && checkpoint.canonical_source === "buyer_offer"
      && checkpoint.source_record_id === currentPrimary?.offer_id,
  ) ?? null;
  const primaryEarnestMoneyCents = primaryOffer?.earnest_money_cents;
  const depositKnown = primaryEarnestMoneyCents != null;
  const depositRequired = Boolean(
    currentPrimary && primaryEarnestMoneyCents != null && primaryEarnestMoneyCents > 0,
  );
  const depositNotRequired = Boolean(
    currentPrimary && primaryEarnestMoneyCents === 0,
  );
  const depositWaived = depositCheckpoint?.status === "waived";
  const depositEvidence = depositCheckpoint?.evidence ?? {};
  const depositSupportNote = depositEvidence.confirmation_note ?? depositEvidence.support_note;
  const depositDecisionResolved = Boolean(
    currentPrimary
      && (depositNotRequired || (
        (depositCheckpoint?.status === "completed" || depositWaived)
        && typeof depositSupportNote === "string"
        && depositSupportNote.replace(/\s/g, "").length >= 10
      )),
  );
  const canonicalChecklistComplete = (checkpointType: "title" | "access") => {
    const checkpoints = data.checkpoints.filter((checkpoint) =>
      checkpointForPrimary(checkpoint)
        && checkpoint.checkpoint_type === checkpointType
        && checkpoint.canonical_source === "transaction_checklist"
        && checkpoint.status !== "cancelled",
    );
    return checkpoints.length > 0
      && checkpoints.every((checkpoint) => checkpoint.status === "completed" && hasCanonicalChecklistEvidence(checkpoint));
  };
  const titleComplete = canonicalChecklistComplete("title");
  const accessComplete = canonicalChecklistComplete("access");
  const placementSteps: PlacementStep[] = [
    {
      key: "offer",
      label: "Buyer offer recorded",
      detail: offers.length ? `${offers.length} buyer offer${offers.length === 1 ? " is" : "s are"} available for comparison.` : "Record an interested buyer's complete offer terms.",
      href: "#record-buyer-offer",
      resolved: offers.length > 0,
    },
    {
      key: "verification",
      label: "Proof and terms verified",
      detail: closingComplete ? "Funding preserved the verified offer terms used at close." : termsVerified ? "Proof of funds, closing date, and contingencies are confirmed." : "Verify proof of funds, closing date, and contingencies.",
      href: "#offer-comparison-heading",
      resolved: closingComplete || termsVerified,
    },
    {
      key: "coverage",
      label: "Primary and backup approved",
      detail: currentPrimary && currentBackups.length ? `${currentPrimary.buyer_name} is primary with protected backup coverage.` : "Approve one primary buyer and at least one different backup.",
      href: "#buyer-coverage",
      resolved: closingComplete || Boolean(currentPrimary && currentBackups.length && !staleCoverageSlots.length && !liveCoverageBlockers.length),
    },
    {
      key: "agreement",
      label: data.strategy_agreement.label,
      detail: data.strategy_agreement.ready
        ? "The executed assignment, current approved buyer, signed identity, and approved economics all match."
        : data.strategy_agreement.blockers.join(" "),
      href: "#buyer-coverage",
      resolved: data.strategy_agreement.ready,
    },
    {
      key: "deposit",
      label: closingComplete ? "Deposit decision preserved at close" : depositWaived ? "Buyer deposit waived" : !depositKnown ? "Buyer deposit terms unresolved" : depositRequired ? "Buyer deposit secured" : "No buyer deposit required",
      detail: closingComplete
        ? "Canonical funding preserved the deposit receipt, waiver, or explicit zero used at close."
        : depositWaived
        ? "A manager-approved waiver is recorded. Stonegate keeps this as an open warning instead of treating cash as received."
        : depositDecisionResolved
          ? depositRequired ? "The current buyer offer has a recorded receipt and support note." : "The approved offer requires no earnest-money deposit."
          : !depositKnown
            ? "Revise the approved offer to an explicit zero or record a manager-approved canonical waiver."
            : "Record the current buyer's deposit receipt and support note.",
      href: "#closing-protection-heading",
      resolved: closingComplete || depositDecisionResolved,
      warning: !closingComplete && depositWaived,
    },
    {
      key: "title-access",
      label: "Title and access cleared",
      detail: titleComplete && accessComplete ? "Title and property-access milestones are complete." : "Complete both the title and property-access milestones.",
      href: "#closing-protection-heading",
      resolved: closingComplete || (titleComplete && accessComplete),
    },
    {
      key: "closing",
      label: "Funded and closed",
      detail: closingComplete ? "Canonical transaction funding recorded the completed close." : "Complete funding in the Deal record; Stonegate will record the close automatically.",
      href: "#closing-protection-heading",
      resolved: closingComplete,
    },
  ];

  return (
    <div className={styles.workspace} id="offer-room">
      {error ? <div className={styles.error} ref={statusRef} role="alert" tabIndex={-1}><span>{error}</span><button disabled={loading || busyAction !== null} onClick={() => void load()} type="button"><RefreshCw aria-hidden="true" size={13} />Refresh Offer Room</button></div> : null}
      {success ? <p aria-live="polite" className={styles.success} role="status">{success}</p> : null}

      <header className={styles.hero}>
        <div>
          <span className={styles.eyebrow}><Trophy aria-hidden="true" size={15} />House disposition - Offer Room and closing protection</span>
          <h4>Choose the strongest executable buyer</h4>
          <p>A higher price can still be a weaker executable offer. Compare the saved terms, proof, reliability, and risk evidence before a human approves primary and backup coverage.</p>
        </div>
        <div className={styles.heroStats}>
          <div><strong>{offers.length}</strong><span>Offers compared</span></div>
          <div><strong>{currentBackups.length}</strong><span>Backups protected</span></div>
          <div><strong>{overdue.length}</strong><span>Missed deadlines</span></div>
        </div>
      </header>

      {attention || overdue.length ? (
        <div className={styles.attentionStrip} role="alert">
          <AlertTriangle aria-hidden="true" size={18} />
          <div><strong>{attention?.title ?? attentionCheckpoint?.label ?? "Missed deadline requires action"}</strong><p>{attention?.message ?? `${overdue[0]?.label} is overdue. Confirm completion or activate a ranked backup.`}</p></div>
          <button className={styles.secondaryButton} disabled={busyAction !== null || !canEditDeals} onClick={() => void scanDeadlines()} type="button"><RefreshCw aria-hidden="true" size={14} />Refresh deadlines</button>
        </div>
      ) : null}

      <PlacementPath steps={placementSteps} />

      <div className={styles.selectionGrid}>
        <section aria-labelledby="offer-comparison-heading" className={styles.panel}>
          <div className={styles.sectionHeading}>
            <div><span>Side-by-side decision evidence</span><h5 id="offer-comparison-heading">Best-executable comparison</h5><p>The recommendation explains evidence only. It never selects a buyer.</p></div>
            <strong>{offers.length ? `Updated ${dateTime(data.generated_at)}` : "Awaiting offers"}</strong>
          </div>
          {offers.length ? <div className={styles.comparisonViewport}>{offers.map((offer) => <OfferCard backupOfferIds={backupOfferIds} currency={data.currency} key={offer.id} offer={offer} primaryOfferId={currentPrimary?.offer_id ?? null} />)}</div> : <div className={styles.empty}><BadgeDollarSign aria-hidden="true" size={26} /><strong>No buyer offers recorded</strong><p>Record an interested buyer&apos;s complete terms below to start the comparison.</p></div>}
        </section>

        <aside className={styles.selectionCard} id="buyer-coverage">
          <span>Current coverage</span>
          <h5>Human-approved primary and backups</h5>
          <p>Coverage remains visible until a completed close or a documented replacement.</p>
          <div className={styles.coverageSlots}>
            <div className={styles.coverageSlot}><span>Primary buyer</span><strong>{currentPrimary?.buyer_name ?? "Not selected"}</strong><small className={!currentPrimary ? styles.coverageEmpty : undefined}>{currentPrimary ? `${money(currentPrimary.amount_cents, data.currency)} - ${labelize(currentPrimary.readiness_status)}` : "Human approval required"}</small></div>
            <div className={styles.coverageSlot}><span>Backup coverage</span><strong>{currentBackups.length ? currentBackups.map((item) => item.buyer_name).join(", ") : "None"}</strong><small className={!currentBackups.length ? styles.coverageEmpty : undefined}>{currentBackups.length ? `${currentBackups.filter((item) => item.readiness_status === "ready").length} of ${currentBackups.length} ready` : "Add a viable backup"}</small></div>
          </div>
          {data.current_selection?.reason ? <p className={styles.selectionReason}>{data.current_selection.reason}</p> : null}
          {staleCoverageSlots.length ? <p className={styles.permissionNote}>Coverage approval is stale because current offer terms changed for {staleCoverageSlots.map((slot) => slot.buyer_name).join(", ")}. Review the live comparison and reapprove coverage below—even when keeping the same primary and backup.</p> : null}
          {liveCoverageBlockers.length ? <p className={styles.permissionNote}>Live coverage blockers: {liveCoverageBlockers.join("; ")}</p> : null}

          <form aria-label={data.current_selection ? "Approve a new buyer coverage version" : "Approve primary and backup buyer coverage"} key={data.current_selection ? `${data.current_selection.id}-${data.current_selection.lock_version}` : "initial-coverage"} onSubmit={approveSelection}>
            {data.current_selection ? <p className={styles.permissionNote}>This approves a new coverage version after reviewing current terms. You may keep the same primary and backup or replace either one. Earlier selections remain in history.</p> : null}
            <label><span>Primary offer</span><select defaultValue={currentPrimary?.offer_id ?? ""} disabled={!selectionCoverageReady || !canViewPrivateEconomics || !canApproveBuyerSelection} name="primary_offer_id" required><option value="">Select primary</option>{selectableOffers.map((offer) => <option key={offer.id} value={offer.id}>{offer.buyer_name} - {money(offer.amount_cents, data.currency)}</option>)}</select></label>
            <label><span>Backup offer</span><select defaultValue={currentBackups[0]?.offer_id ?? ""} disabled={!selectionCoverageReady || !canViewPrivateEconomics || !canApproveBuyerSelection} name="backup_offer_id" required><option value="">Select a different backup</option>{selectableOffers.map((offer) => <option key={offer.id} value={offer.id}>{offer.buyer_name} - {money(offer.amount_cents, data.currency)}</option>)}</select></label>
            <label><span>{data.current_selection ? "Coverage revision reason" : "Selection reason"}</span><textarea minLength={10} name="selection_reason" placeholder={data.current_selection ? "Explain why this new primary and backup coverage version is required." : "Explain price, proof, deposit, timing, reliability, and material tradeoffs."} required rows={4} /></label>
            <label><span>Advanced readiness exception (optional)</span><textarea minLength={10} name="eligibility_override_reason" placeholder="Explain the controlled POF, match, or timing exception." rows={3} /><small>Use only for a documented readiness exception. The approved minimum price cannot be overridden.</small></label>
            <p className={styles.permissionNote}>Unselected viable offers stay available for negotiation or later backup replacement.</p>
            {!canViewPrivateEconomics ? <p className={styles.permissionNote}>Offer comparison is visible, but your role cannot approve a buyer against Stonegate&apos;s private floor.</p> : null}
            {canViewPrivateEconomics && !canApproveBuyerSelection ? <p className={styles.permissionNote}>Comparison access only. A selection approver must choose the primary and backup buyers.</p> : null}
            {!selectionCoverageReady ? <p className={styles.permissionNote}>At least two viable offers from different buyers are required for protected primary and backup coverage.</p> : null}
            <button className={styles.button} disabled={busyAction !== null || !canEditDeals || !canViewPrivateEconomics || !canApproveBuyerSelection || !selectionCoverageReady} type="submit"><UserCheck aria-hidden="true" size={14} />{canApproveBuyerSelection ? data.current_selection ? staleCoverageSlots.length ? "Reapprove changed coverage" : "Approve new coverage version" : "Approve primary and backup" : "Approval permission required"}</button>
          </form>
        </aside>
      </div>

      <div className={styles.operationsGrid}>
        <section aria-labelledby="closing-protection-heading" className={styles.panel} id="closing-milestones">
          <div className={styles.sectionHeading}>
            <div><span>Execution safeguards</span><h5 id="closing-protection-heading">Closing protection checklist</h5><p>Agreement, Signature, Deposit, Access, Title, buyer response, and Closing remain visible through completion.</p></div>
            <button className={styles.secondaryButton} disabled={busyAction !== null || !canEditDeals} onClick={() => void scanDeadlines()} type="button"><RefreshCw aria-hidden="true" size={14} />Scan deadlines</button>
          </div>
          <div className={styles.checkpointList}>
            {data.checkpoints.map((deadline) => <CheckpointRow busy={busyAction !== null} buyerName={deadline.offer_id ? offersById.get(deadline.offer_id)?.buyer_name ?? null : null} canApproveWaiver={canApproveBuyerSelection} canEdit={canEditDeals} checkpoint={deadline} key={deadline.id} onDecision={(item, status, note) => void completeCheckpoint(item, status, note)} />)}
            {!data.checkpoints.length ? <div className={styles.empty}><FileCheck2 aria-hidden="true" size={24} /><strong>No closing milestones yet</strong><p>Add the agreement, signature, deposit, access, title, and closing dates after a buyer is selected.</p></div> : null}
          </div>
        </section>

        <div className={styles.rightStack}>
          <section className={styles.panel}>
            <div className={styles.sectionHeading}><div><span>Actionable and deduplicated</span><h5>Deadline alerts</h5></div><strong>{data.alerts.length} open</strong></div>
            <div className={styles.alertList}>{data.alerts.map((alert) => <article className={styles.alertItem} data-severity={alert.severity} key={alert.id}><AlertTriangle aria-hidden="true" size={15} /><div><strong>{alert.title}</strong><span>{alert.message}</span><p>Due {dateTime(alert.due_at)}</p>{!alert.acknowledged_at ? <button className={styles.inlineButton} disabled={busyAction !== null || !canEditDeals} onClick={() => void acknowledgeAlert(alert.id)} type="button">Acknowledge alert</button> : <small>Acknowledged {dateTime(alert.acknowledged_at)}</small>}</div></article>)}{!data.alerts.length ? <div className={styles.empty}><CheckCircle2 aria-hidden="true" size={23} /><strong>No deadline alerts</strong><p>Current recorded milestones are on track.</p></div> : null}</div>
          </section>

          <section className={styles.panel}>
            <div className={styles.sectionHeading}><div><span>Rapid recovery</span><h5>Ranked replacement options</h5></div><strong>{data.replacement_options.length} available</strong></div>
            <div className={styles.replacementList}>{data.replacement_options.map((item) => <article className={styles.replacementItem} data-eligible={item.eligible} key={item.offer_id}><div><strong>{item.buyer_name}</strong><span>Rank {item.comparison_rank} - {percent(item.execution_score_basis_points)} execution - {percent(item.risk_score_basis_points)} risk</span></div><strong>{money(item.amount_cents, data.currency)}</strong><p>{item.blockers.length ? item.blockers.join("; ") : item.backup_rank ? `Approved backup rank ${item.backup_rank}` : "Eligible ranked offer"}</p></article>)}{!data.replacement_options.length ? <div className={styles.empty}><UsersRound aria-hidden="true" size={23} /><strong>No eligible replacement</strong><p>Keep viable backup offers current before the primary buyer misses a deadline.</p></div> : null}</div>
            <form className={styles.formBody} onSubmit={replacePrimary}>
              <label><span>Replacement offer</span><select disabled={!canApproveBuyerSelection || !data.replacement_options.some((item) => item.eligible)} name="replacement_offer_id" required><option value="">Select ranked backup</option>{data.replacement_options.filter((item) => item.eligible).map((item) => <option key={item.offer_id} value={item.offer_id}>{item.buyer_name} - {money(item.amount_cents, data.currency)}</option>)}</select></label>
              <div className={styles.twoFields}><label><span>Primary outcome</span><select name="outcome_type"><option value="missed_deadline">Missed deadline</option><option value="withdrawal">Withdrawal</option><option value="fallout">Fallout</option><option value="retrade">Retrade</option></select></label><label><span>Cause</span><select name="cause_category"><option value="buyer">Buyer</option><option value="seller">Seller</option><option value="title">Title</option><option value="property">Property</option><option value="stonegate">Stonegate</option><option value="external">External</option></select></label></div>
              <label><span>Replacement reason</span><textarea minLength={10} name="replacement_reason" placeholder="Record the missed obligation and why this backup is executable." required rows={3} /></label>
              <label><span>Supporting details</span><textarea name="replacement_details" rows={2} /></label>
              {!canApproveBuyerSelection ? <p className={styles.permissionNote}>A selection approver must activate a replacement buyer.</p> : null}
              <button className={styles.dangerButton} disabled={busyAction !== null || !canEditDeals || !canViewPrivateEconomics || !canApproveBuyerSelection || !data.current_selection || !data.replacement_options.some((item) => item.eligible)} type="submit"><ArrowRightLeft aria-hidden="true" size={14} />{canApproveBuyerSelection ? "Activate backup buyer" : "Approval permission required"}</button>
            </form>
          </section>
        </div>
      </div>

      <section className={styles.timelinePanel}>
        <div className={styles.sectionHeading}><div><span>Evidence-preserving record</span><h5>Negotiation history and decisions</h5><p>Revisions, human selections, replacements, and outcomes remain reviewable.</p></div><History aria-hidden="true" size={18} /></div>
        <div aria-label="Offer Room history" className={styles.timelineTabs} role="tablist">
          {(["negotiation", "selection", "outcomes"] as TimelineTab[]).map((item) => <button aria-controls="offer-room-history-panel" aria-selected={timelineTab === item} id={`offer-room-${item}-tab`} key={item} onClick={() => setTimelineTab(item)} role="tab" type="button">{item === "negotiation" ? "Negotiation history" : item === "selection" ? "Selection history" : "Outcome history"}</button>)}
        </div>
        <div aria-labelledby={`offer-room-${timelineTab}-tab`} className={styles.timelineList} id="offer-room-history-panel" role="tabpanel">
          {timelineTab === "negotiation" ? data.negotiation_history.map((item) => <article className={styles.timelineItem} key={item.id}><div><strong>{item.buyer_name} - {labelize(item.event_type)}</strong><span>{labelize(item.direction)}</span></div><time>{dateTime(item.occurred_at)}</time><p>{item.summary}</p>{Object.keys(item.metadata).length ? <small>{displayEvidence(item.metadata)}</small> : null}</article>) : null}
          {timelineTab === "selection" ? data.selection_history.map((item) => <article className={styles.timelineItem} key={item.id}><div><strong>{item.primary?.buyer_name ?? "Selection cleared"}</strong><span>{item.backups.length ? `Backups: ${item.backups.map((backup) => backup.buyer_name).join(", ")}` : "No backup coverage"}</span></div><time>{dateTime(item.approved_at)}</time><p>{item.reason}</p></article>) : null}
          {timelineTab === "outcomes" ? data.outcomes.map((item) => <article className={styles.timelineItem} key={item.id}><div><strong>{item.buyer_name} - {labelize(item.outcome_type)}</strong><span>{labelize(item.cause_category)} cause - {signedPercent(item.reliability_delta_basis_points)} reliability</span></div><time>{dateTime(item.occurred_at)}</time><p>{item.reason}</p>{item.details ? <small>{item.details}</small> : null}</article>) : null}
          {timelineTab === "negotiation" && !data.negotiation_history.length ? <div className={styles.empty}><History aria-hidden="true" size={22} /><strong>No negotiation events</strong><p>Record counters and material term changes without overwriting the original offer.</p></div> : null}
          {timelineTab === "selection" && !data.selection_history.length ? <div className={styles.empty}><UserCheck aria-hidden="true" size={22} /><strong>No selection history</strong><p>A human-approved primary and backup decision will appear here.</p></div> : null}
          {timelineTab === "outcomes" && !data.outcomes.length ? <div className={styles.empty}><CircleDollarSign aria-hidden="true" size={22} /><strong>No buyer outcomes</strong><p>Passes, withdrawals, fallouts, retrades, and completed closes will appear here.</p></div> : null}
        </div>
      </section>

      <div className={styles.formsGrid}>
        <details className={styles.form} id="record-buyer-offer">
          <summary><div><span>Normalized evidence</span><h5>Record buyer offer</h5><p>Capture every execution term, not only price.</p></div><ChevronDown aria-hidden="true" size={17} /></summary>
          <form className={styles.formBody} onSubmit={recordOffer}>
            <label><span>Buyer</span><select name="buyer_id" required><option value="">Select buyer</option>{normalizedBuyers.map((buyer) => <option key={buyer.buyer_id} value={buyer.buyer_id}>{buyer.buyer_name}</option>)}</select></label>
            <div className={styles.twoFields}><label><span>Offer amount</span><input inputMode="decimal" name="amount" required /></label><label><span>Earnest money (optional)</span><input inputMode="decimal" name="earnest_money" placeholder="Unknown if not stated" /></label></div>
            <div className={styles.twoFields}><label><span>Deposit due</span><input name="deposit_due_at" type="datetime-local" /></label><label><span>Due diligence days</span><input min="0" name="due_diligence_days" type="number" /></label></div>
            <div className={styles.twoFields}><label><span>Proposed closing</span><input name="proposed_closing_at" type="datetime-local" /></label><label><span>Funding</span><select defaultValue="unknown" name="funding_method"><option value="unknown">Unknown</option><option value="cash">Cash</option><option value="hard_money">Hard money</option><option value="private_money">Private money</option><option value="conventional">Conventional</option></select></label></div>
            <label><span>Funding confidence</span><select defaultValue="0" name="funding_confidence"><option value="0">Unknown</option><option value="25">Weak</option><option value="50">Uncertain</option><option value="75">Strong</option><option value="100">Verified</option></select></label>
            <label><span>Contingencies</span><input name="contingencies" placeholder="Inspection, financing, partner approval" /></label>
            <label className={styles.checkLabel}><input name="contingencies_confirmed" type="checkbox" /><span>Buyer confirmed these contingency terms (leave the field blank only if the buyer confirmed none).</span></label>
            <label><span>Special terms</span><textarea name="special_terms" rows={3} /></label>
            <label><span>Human notes</span><textarea name="notes" rows={3} /></label>
            <small>Current saved proof of funds is attached when available. Recording an offer does not select the buyer.</small>
            <button disabled={busyAction !== null || !canEditDeals || !normalizedBuyers.length} type="submit"><BadgeDollarSign aria-hidden="true" size={14} />Record offer</button>
          </form>
        </details>

        <details className={styles.form}>
          <summary><div><span>Evidence-preserving revision</span><h5>Revise offer terms</h5><p>Save changed terms without replacing the original history.</p></div><ChevronDown aria-hidden="true" size={17} /></summary>
          <form className={styles.formBody} onSubmit={reviseOffer}>
            <label><span>Offer</span><select name="offer_id" required><option value="">Select offer</option>{offers.map((offer) => <option key={offer.id} value={offer.id}>{offer.buyer_name} - {money(offer.amount_cents, data.currency)}</option>)}</select></label>
            <div className={styles.twoFields}><label><span>Revised amount (optional)</span><input inputMode="decimal" name="amount" placeholder="Keep current" /></label><label><span>Revised earnest money (optional)</span><input inputMode="decimal" name="earnest_money" placeholder="Keep current" /></label></div>
            <div className={styles.twoFields}><label><span>Deposit due</span><input name="deposit_due_at" type="datetime-local" /></label><label><span>Due diligence days</span><input min="0" name="due_diligence_days" type="number" /></label></div>
            <div className={styles.twoFields}><label><span>Proposed closing</span><input name="proposed_closing_at" type="datetime-local" /></label><label><span>Funding</span><select defaultValue="" name="funding_method"><option value="">Keep current</option><option value="unknown">Unknown</option><option value="cash">Cash</option><option value="hard_money">Hard money</option><option value="private_money">Private money</option><option value="conventional">Conventional</option></select></label></div>
            <label><span>Funding confidence</span><select defaultValue="" name="funding_confidence"><option value="">Keep current</option><option value="0">Unknown</option><option value="25">Weak</option><option value="50">Uncertain</option><option value="75">Strong</option><option value="100">Verified</option></select></label>
            <label><span>Contingencies (optional change)</span><input name="contingencies" placeholder="Keep current when blank" /></label>
            <label><span>Contingency confirmation</span><select defaultValue="" name="contingencies_confirmed"><option value="">Keep current</option><option value="false">Not yet confirmed</option><option value="true">Buyer confirmed listed terms or none</option></select></label>
            <label><span>Special terms</span><textarea name="special_terms" rows={3} /></label>
            <label><span>Notes</span><textarea name="notes" rows={3} /></label>
            <label><span>Revision reason</span><textarea minLength={3} name="revision_reason" required rows={3} /></label>
            <small>Blank revision fields keep their saved values. A newer verified proof-of-funds document is attached when available.</small>
            <button disabled={busyAction !== null || !canEditDeals || !offers.length} type="submit"><RotateCcw aria-hidden="true" size={14} />Save revised terms</button>
          </form>
        </details>

        <details className={styles.form}>
          <summary><div><span>Conversation record</span><h5>Log negotiation</h5><p>Preserve counters, proof requests, and material buyer responses.</p></div><ChevronDown aria-hidden="true" size={17} /></summary>
          <form className={styles.formBody} onSubmit={recordNegotiation}>
            <label><span>Offer</span><select name="offer_id" required><option value="">Select offer</option>{offers.map((offer) => <option key={offer.id} value={offer.id}>{offer.buyer_name}</option>)}</select></label>
            <div className={styles.twoFields}><label><span>Event</span><select name="event_type"><option value="counter">Counter</option><option value="note">Note</option><option value="request">Request</option><option value="response">Response</option><option value="retrade">Retrade</option></select></label><label><span>Direction</span><select name="direction"><option value="inbound">Inbound from buyer</option><option value="outbound">Outbound to buyer</option><option value="internal">Internal</option></select></label></div>
            <label><span>Proposed amount</span><input inputMode="decimal" name="proposed_amount" /></label>
            <label><span>Negotiation notes</span><textarea minLength={3} name="notes" required rows={4} /></label>
            <button disabled={busyAction !== null || !canEditDeals || !offers.length} type="submit"><History aria-hidden="true" size={14} />Record negotiation</button>
          </form>
        </details>

        <details className={styles.form}>
          <summary><div><span>Deadline protection</span><h5>Add closing milestone</h5><p>Create an owned deadline after buyer selection.</p></div><ChevronDown aria-hidden="true" size={17} /></summary>
          <form className={styles.formBody} onSubmit={createCheckpoint}>
            <label><span>Milestone</span><select name="checkpoint_type"><option value="buyer_agreement">Buyer agreement</option><option value="buyer_signature">Buyer signature</option><option value="buyer_deposit">Buyer deposit</option><option value="buyer_response">Buyer response</option><option value="access">Access</option><option value="title">Title</option><option value="closing">Closing</option></select></label>
            <label><span>Label</span><input name="label" placeholder="Earnest money received" required /></label>
            <label><span>Due date and time</span><input name="due_at" required type="datetime-local" /></label>
            <label><span>Related offer</span><select name="offer_id"><option value="">Whole deal</option>{offers.map((offer) => <option key={offer.id} value={offer.id}>{offer.buyer_name}</option>)}</select></label>
            <label><span>Notes</span><textarea name="notes" rows={3} /></label>
            <button disabled={busyAction !== null || !canEditDeals || !data.current_selection} type="submit"><CalendarClock aria-hidden="true" size={14} />Add milestone</button>
          </form>
        </details>

        <details className={styles.form}>
          <summary><div><span>Reliability evidence</span><h5>Record outcome</h5><p>Save pass, withdrawal, fallout, retrade, or completed close.</p></div><ChevronDown aria-hidden="true" size={17} /></summary>
          <form className={styles.formBody} onSubmit={recordOutcome}>
            <label><span>Offer</span><select name="offer_id" required><option value="">Select offer</option>{offers.map((offer) => <option key={offer.id} value={offer.id}>{offer.buyer_name}</option>)}</select></label>
            <label><span>Outcome</span><select name="outcome_type"><option value="pass">Pass</option><option value="withdrawal">Withdrawal</option><option value="fallout">Fallout</option><option value="retrade">Retrade</option></select></label>
            <label><span>Cause</span><select name="cause_category"><option value="buyer">Buyer</option><option value="seller">Seller</option><option value="title">Title</option><option value="property">Property</option><option value="stonegate">Stonegate</option><option value="external">External</option></select></label>
            <label><span>Outcome reason</span><textarea minLength={10} name="outcome_reason" required rows={4} /></label>
            <label><span>Supporting details</span><textarea name="outcome_details" rows={3} /></label>
            <small>Outcomes update documented buyer history without erasing evidence. A funded transaction records the completed close automatically.</small>
            <button disabled={busyAction !== null || !canEditDeals || !offers.length} type="submit"><CircleDollarSign aria-hidden="true" size={14} />Record outcome</button>
          </form>
        </details>
      </div>

      {busyAction ? <div className={styles.busy}><LoaderCircle aria-hidden="true" className={styles.spin} size={16} />Working</div> : null}
    </div>
  );
}
