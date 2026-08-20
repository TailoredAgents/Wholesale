"use client";

import { useAuth } from "@clerk/nextjs";
import {
  AlertTriangle,
  CheckCircle2,
  CircleSlash2,
  ClipboardCheck,
  Gauge,
  LockKeyhole,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import type {
  CampaignManagementOverview,
  ProspectingDialerOperations,
  ProspectingDialerPilotAttempt,
  ProspectingDialerPilotOverview,
} from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./prospecting.module.css";

type MutationMethod = "POST" | "PUT";
type EvidenceKind =
  | "smoke_test"
  | "kill_switch"
  | "batchdialer_comparison"
  | "rollback";
type ReviewPayload = Record<string, unknown>;
type ProviderCostDraft = {
  actualCostDollars: string;
  providerReference: string;
};
type ProviderCostItem = {
  provider_call_id: string;
  actual_cost_cents: number | null;
  currency: "USD";
  provider_reference: string;
};
type SmokeCallCandidate = {
  attemptId: string;
  callRecordId: string;
  providerCallIds: string[];
};

const terminalPilotStatuses = new Set(["accepted", "rejected", "rolled_back", "revoked", "cancelled"]);
const acceptancePhrase = "ACCEPT SINGLE-LINE DIALER";
const rejectionPhrase = "REJECT SINGLE-LINE DIALER";
const rollbackPhraseRequired = "ROLL BACK SINGLE-LINE PILOT";
const revokePhraseRequired = "REVOKE SINGLE-LINE DIALER";

function formatDateTime(value: string | null | undefined) {
  if (!value) return "Not reported";
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatMoney(cents: number | null | undefined) {
  if (cents == null) return "Not reported";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(cents / 100);
}

function operationKey(prefix: string, id: string) {
  return `${prefix}-${id}-${Date.now()}-${crypto.randomUUID()}`;
}

function responseError(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) return fallback;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return String(item);
      })
      .join(" ");
  }
  return fallback;
}

function gateClass(status: string) {
  if (status === "pass") return styles.pilotGatePass;
  if (status === "block") return styles.pilotGateBlock;
  if (status === "warning") return styles.pilotGateWarning;
  return styles.pilotGatePending;
}

function reviewClass(status: string | null | undefined) {
  if (status === "passed") return styles.statusGood;
  if (status === "failed") return styles.pilotStatusBlocked;
  if (status) return styles.statusWarning;
  return styles.statusNeutral;
}

function localDateTimeValue(date = new Date()) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 19);
}

function dateKeyInTimeZone(value: string, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    day: "2-digit",
    month: "2-digit",
    timeZone,
    year: "numeric",
  }).formatToParts(new Date(value));
  const part = (type: Intl.DateTimeFormatPartTypes) => (
    parts.find((item) => item.type === type)?.value ?? ""
  );
  return `${part("year")}-${part("month")}-${part("day")}`;
}

function centsFromDollarInput(value: string) {
  const normalized = value.trim();
  if (!/^\d+(?:\.\d{1,2})?$/.test(normalized)) return null;
  const [wholeDollars, fractionalDollars = ""] = normalized.split(".");
  const cents = Number(wholeDollars) * 100 + Number(fractionalDollars.padEnd(2, "0"));
  if (!Number.isSafeInteger(cents) || cents < 0 || cents > 100_000) return null;
  return cents;
}

function providerCostItemsFromDraft(
  providerCallIds: string[],
  providerCosts: Record<string, ProviderCostDraft>,
): ProviderCostItem[] {
  return [...new Set(providerCallIds)].map((providerCallId) => ({
    provider_call_id: providerCallId,
    actual_cost_cents: centsFromDollarInput(
      providerCosts[providerCallId]?.actualCostDollars ?? "",
    ),
    currency: "USD",
    provider_reference: providerCosts[providerCallId]?.providerReference.trim() ?? "",
  }));
}

function providerCostsAreComplete(
  providerCallIds: string[],
  providerCostItems: ProviderCostItem[],
  maximumItems: number,
) {
  return providerCallIds.length >= 1 &&
    providerCallIds.length <= maximumItems &&
    new Set(providerCallIds).size === providerCallIds.length &&
    providerCostItems.every((item) => (
      item.actual_cost_cents !== null && item.provider_reference.length > 0
    ));
}

function ProviderCostFields({
  disabled,
  emptyMessage,
  providerCallIds,
  providerCosts,
  onChange,
}: {
  disabled: boolean;
  emptyMessage: string;
  providerCallIds: string[];
  providerCosts: Record<string, ProviderCostDraft>;
  onChange: (providerCallId: string, value: ProviderCostDraft) => void;
}) {
  const uniqueProviderCallIds = [...new Set(providerCallIds)];
  const providerCostItems = providerCostItemsFromDraft(providerCallIds, providerCosts);

  return (
    <div className={styles.pilotProviderCosts}>
      <header>
        <div><strong>Provider cost reconciliation</strong><span>{providerCallIds.length} provider call{providerCallIds.length === 1 ? "" : "s"}</span></div>
        <small>Enter the provider-reported USD charge and source reference for every exact root and seller-child call ID. A documented $0 charge is valid; Stonegate verifies one-to-one coverage and owns the billing decision.</small>
      </header>
      {uniqueProviderCallIds.map((providerCallId, index) => (
        <div className={styles.pilotProviderCostRow} key={providerCallId}>
          <div><span>Provider call {index + 1}</span><code>{providerCallId}</code></div>
          <label>
            <span>Actual cost (USD)</span>
            <input
              disabled={disabled}
              inputMode="decimal"
              max="1000"
              min="0"
              onChange={(event) => onChange(providerCallId, {
                actualCostDollars: event.target.value,
                providerReference: providerCosts[providerCallId]?.providerReference ?? "",
              })}
              placeholder="0.02"
              required
              step="0.01"
              type="number"
              value={providerCosts[providerCallId]?.actualCostDollars ?? ""}
            />
          </label>
          <label>
            <span>Provider reference</span>
            <input
              disabled={disabled}
              maxLength={500}
              onChange={(event) => onChange(providerCallId, {
                actualCostDollars: providerCosts[providerCallId]?.actualCostDollars ?? "",
                providerReference: event.target.value,
              })}
              placeholder="Usage export row, invoice, or provider record"
              required
              value={providerCosts[providerCallId]?.providerReference ?? ""}
            />
          </label>
        </div>
      ))}
      {!providerCallIds.length ? <p className={styles.dialerInlineWarning}>{emptyMessage}</p> : null}
      {uniqueProviderCallIds.length !== providerCallIds.length ? <p className={styles.dialerInlineWarning}>Duplicate provider call IDs were returned. Reconciliation remains blocked until the call records are corrected.</p> : null}
      {providerCostItems.length && providerCostItems.every((item) => item.actual_cost_cents !== null) ? <p className={styles.pilotProviderCostTotal}>Entered provider total: {formatMoney(providerCostItems.reduce((total, item) => total + (item.actual_cost_cents ?? 0), 0))}</p> : null}
    </div>
  );
}

function ReviewFacts({
  disabled,
  kind,
  onSave,
  providerCallIds = [],
}: {
  disabled: boolean;
  kind: "attempt" | "shift";
  onSave: (facts: ReviewPayload) => Promise<boolean>;
  providerCallIds?: string[];
}) {
  const reviewId = useId();
  const [notes, setNotes] = useState("");
  const [facts, setFacts] = useState<Record<string, boolean>>({});
  const [billingReference, setBillingReference] = useState("");
  const [providerCosts, setProviderCosts] = useState<Record<string, ProviderCostDraft>>(() => (
    Object.fromEntries(providerCallIds.map((providerCallId) => [
      providerCallId,
      { actualCostDollars: "", providerReference: "" },
    ]))
  ));
  const questions = kind === "attempt"
    ? [
        ["recording_reviewed", "Recording or call evidence was reviewed"],
        ["provider_cost_verified", "Provider cost was reconciled to the source record"],
        ["compliance_clear", "No compliance or seller-experience issue was found"],
      ]
    : [
        ["no_duplicate_calls", "No duplicate-call incident was found"],
        ["no_lost_answers", "No answered call or assigned work was lost"],
        ["no_stuck_sessions", "No session remained stuck"],
        ["provider_billing_verified", "Provider billing and daily caps were reconciled"],
        ["kill_switches_verified", "Pause, stop, and kill switches were verified"],
        ["compliance_clear", "No compliance or seller-experience issue was found"],
      ];
  const providerCostItems = providerCostItemsFromDraft(providerCallIds, providerCosts);
  const providerCostsComplete = kind === "attempt" || (
    providerCostsAreComplete(providerCallIds, providerCostItems, 250)
  );
  const complete = questions.every(([key]) => typeof facts[key] === "boolean") &&
    (kind === "attempt" || (billingReference.trim().length > 0 && providerCostsComplete));

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!complete || notes.trim().length < 8) return;
    const saved = await onSave({
      ...facts,
      ...(kind === "shift" ? {
        billing_evidence_reference: billingReference.trim(),
        provider_cost_items: providerCostItems,
      } : {}),
      reason: notes.trim(),
    });
    if (saved) setNotes("");
  }

  return (
    <form className={styles.pilotReviewForm} onSubmit={submit}>
      <fieldset disabled={disabled}>
        <legend>Record observed facts</legend>
        {questions.map(([key, label]) => (
          <div aria-labelledby={`${reviewId}-${key}`} className={styles.pilotBooleanRow} key={key} role="radiogroup">
            <span id={`${reviewId}-${key}`}>{label}</span>
            <label><input checked={facts[key] === true} name={key} onChange={() => setFacts((current) => ({ ...current, [key]: true }))} type="radio" /> Yes</label>
            <label><input checked={facts[key] === false} name={key} onChange={() => setFacts((current) => ({ ...current, [key]: false }))} type="radio" /> No</label>
          </div>
        ))}
      </fieldset>
      {kind === "shift" ? (
        <>
          <ProviderCostFields
            disabled={disabled}
            emptyMessage="No provider call IDs were returned for this shift. Refresh after provider records are complete; billing review remains blocked."
            onChange={(providerCallId, value) => setProviderCosts((current) => ({
              ...current,
              [providerCallId]: value,
            }))}
            providerCallIds={providerCallIds}
            providerCosts={providerCosts}
          />
          <label>
            <span>Billing evidence reference</span>
            <input disabled={disabled} maxLength={1000} onChange={(event) => setBillingReference(event.target.value)} placeholder="Twilio usage export, invoice, or reconciliation record" required value={billingReference} />
          </label>
        </>
      ) : null}
      <label>
        <span>Reviewer notes</span>
        <textarea disabled={disabled} maxLength={2000} minLength={8} onChange={(event) => setNotes(event.target.value)} placeholder="Record what you verified and any follow-up needed." required value={notes} />
      </label>
      <button className={styles.primaryButton} disabled={disabled || !complete || notes.trim().length < 8} type="submit">
        Save factual review
      </button>
      <small>Stonegate calculates pass or fail from these facts and the underlying call records.</small>
    </form>
  );
}

function EvidenceCapture({
  disabled,
  kind,
  onSave,
  smokeCallCandidates = [],
  smokeProviderCallIds = [],
  title,
  description,
}: {
  disabled: boolean;
  kind: EvidenceKind;
  onSave: (kind: EvidenceKind, evidence: Record<string, unknown>) => Promise<boolean>;
  smokeCallCandidates?: SmokeCallCandidate[];
  smokeProviderCallIds?: string[];
  title: string;
  description: string;
}) {
  const [summary, setSummary] = useState("");
  const [facts, setFacts] = useState<Record<string, boolean>>({});
  const [observedAt, setObservedAt] = useState(() => localDateTimeValue());
  const [reference, setReference] = useState("");
  const [selectedCallRecordIds, setSelectedCallRecordIds] = useState<string[]>([]);
  const [providerCosts, setProviderCosts] = useState<Record<string, ProviderCostDraft>>({});
  const questions: Array<[string, string]> = kind === "smoke_test"
    ? [["controlled_numbers_only", "Only controlled owner or staff numbers were used"]]
    : kind === "kill_switch"
      ? [
          ["company_switch_tested", "Company switch was turned off, stopped the session, and was turned back on"],
          ["campaign_switch_tested", "Campaign switch was turned off, stopped the session, and was turned back on"],
          ["idle_sessions_stopped", "No pilot session remained active after the drills"],
          ["low_dial_cap_block_tested", "The saved daily dial cap was reached and another dial was blocked"],
        ]
      : kind === "batchdialer_comparison"
        ? [
            ["separate_cohort", "The BatchDialer comparison cohort is separate"],
            ["zero_overlap", "Zero overlapping records were verified"],
          ]
        : [
            ["campaign_pause_tested", "Native campaign pause was tested"],
            ["sessions_end_tested", "Native sessions were ended safely"],
            ["unworked_records_returnable", "Unworked records can return to BatchDialer"],
            ["native_evidence_remains_read_only", "Native evidence remains read-only"],
          ];
  const candidateByCallRecordId = new Map(
    smokeCallCandidates.map((candidate) => [candidate.callRecordId, candidate]),
  );
  const ids = selectedCallRecordIds.filter((id) => candidateByCallRecordId.has(id));
  const selectedProviderCallIds = smokeProviderCallIds;
  const smokeProviderCostItems = providerCostItemsFromDraft(
    selectedProviderCallIds,
    providerCosts,
  );
  const smokeProviderCostsComplete = providerCostsAreComplete(
    selectedProviderCallIds,
    smokeProviderCostItems,
    100,
  );
  const complete = questions.every(([key]) => facts[key] === true) &&
    summary.trim().length >= 8 &&
    (kind !== "smoke_test" || (ids.length > 0 && smokeProviderCostsComplete)) &&
    (kind !== "batchdialer_comparison" || reference.trim().length > 0) &&
    (kind === "batchdialer_comparison" || Boolean(observedAt));

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!complete) return;
    const evidence = kind === "smoke_test"
      ? {
          controlled_numbers_only: true,
          completed_at: new Date(observedAt).toISOString(),
          call_record_ids: ids,
          provider_cost_items: smokeProviderCostItems,
          summary: summary.trim(),
        }
      : kind === "kill_switch"
        ? {
            company_switch_tested: true,
            campaign_switch_tested: true,
            idle_sessions_stopped: true,
            low_dial_cap_block_tested: true,
            tested_at: new Date(observedAt).toISOString(),
            summary: summary.trim(),
          }
        : kind === "batchdialer_comparison"
          ? {
              separate_cohort: true,
              overlapping_record_count: 0,
              batchdialer_cohort_reference: reference.trim(),
              comparison_summary: summary.trim(),
            }
          : {
              campaign_pause_tested: true,
              sessions_end_tested: true,
              unworked_records_returnable: true,
              native_evidence_remains_read_only: true,
              tested_at: new Date(observedAt).toISOString(),
              summary: summary.trim(),
            };
    const saved = await onSave(kind, evidence);
    if (saved) {
      setSummary("");
      if (kind === "smoke_test") setSelectedCallRecordIds([]);
    }
  }

  return (
    <details className={styles.pilotEvidenceCard}>
      <summary>
        <span>{title}</span>
        <small>{description}</small>
      </summary>
      <form onSubmit={submit}>
        <fieldset disabled={disabled}>
          <legend>Confirm only what was actually observed</legend>
          {questions.map(([key, label]) => (
            <label key={key}><input checked={facts[key] === true} onChange={(event) => setFacts((current) => ({ ...current, [key]: event.target.checked }))} type="checkbox" /> {label}</label>
          ))}
        </fieldset>
        {kind === "kill_switch" ? <p className={styles.pilotServerEvidenceNote}>Perform both off/on switch drills and the low-cap block first. Stonegate matches this time to durable server audit events, stopped sessions, and dial-leg counts; these checkboxes cannot make the gate pass by themselves.</p> : null}
        {kind === "rollback" ? <p className={styles.pilotServerEvidenceNote}>Perform the rollback rehearsal first. Stonegate retains the server evidence and keeps the gate blocked when the recorded drill cannot be verified.</p> : null}
        {kind !== "batchdialer_comparison" ? <label><span>Observed at</span><input disabled={disabled} onChange={(event) => setObservedAt(event.target.value)} required step="1" type="datetime-local" value={observedAt} /></label> : null}
        {kind === "smoke_test" ? (
          <fieldset className={styles.pilotCallRecordChoices} disabled={disabled || !smokeCallCandidates.length}>
            <legend>Completed controlled call records</legend>
            {smokeCallCandidates.map((candidate) => (
              <label key={candidate.callRecordId}>
                <input
                  checked={selectedCallRecordIds.includes(candidate.callRecordId)}
                  onChange={(event) => setSelectedCallRecordIds((current) => (
                    event.target.checked
                      ? [...new Set([...current, candidate.callRecordId])]
                      : current.filter((item) => item !== candidate.callRecordId)
                  ))}
                  type="checkbox"
                />
                <span><code>{candidate.callRecordId}</code><small>{candidate.providerCallIds.length} exact provider ID{candidate.providerCallIds.length === 1 ? "" : "s"}: {candidate.providerCallIds.join(", ")}</small></span>
              </label>
            ))}
            {!smokeCallCandidates.length ? <span>Complete an answered controlled-number seller call with one exact durable call record, signed child evidence, and root/child provider IDs, then refresh this page.</span> : null}
          </fieldset>
        ) : null}
        {kind === "smoke_test" ? (
          <ProviderCostFields
            disabled={disabled || !ids.length}
            emptyMessage="No provider-started smoke IDs are available yet. Finish the smoke attempts, then refresh before reconciling costs."
            onChange={(providerCallId, value) => setProviderCosts((current) => ({
              ...current,
              [providerCallId]: value,
            }))}
            providerCallIds={selectedProviderCallIds}
            providerCosts={providerCosts}
          />
        ) : null}
        {kind === "smoke_test" && smokeProviderCallIds.length > 100 ? <p className={styles.dialerInlineWarning}>This smoke stage exceeded its 50-reservation / 100-provider-ID safety boundary. Roll back this pilot and begin a new controlled smoke test.</p> : null}
        {kind === "batchdialer_comparison" ? <label><span>BatchDialer cohort reference</span><input disabled={disabled} maxLength={500} onChange={(event) => setReference(event.target.value)} placeholder="Campaign, list, or cohort reference" required value={reference} /></label> : null}
        <label>
          <span>Evidence summary</span>
          <textarea disabled={disabled} maxLength={2000} minLength={8} onChange={(event) => setSummary(event.target.value)} placeholder="State what happened and where the evidence can be verified." required value={summary} />
        </label>
        <button className={styles.secondaryButton} disabled={disabled || !complete} type="submit">Save evidence</button>
      </form>
    </details>
  );
}

export function ProspectingPilotAcceptance({
  campaignManagement,
  dialerOperations,
  initialApiConnected,
  initialData,
}: {
  campaignManagement: CampaignManagementOverview | null;
  dialerOperations: ProspectingDialerOperations | null;
  initialApiConnected: boolean;
  initialData: ProspectingDialerPilotOverview | null;
}) {
  const { getToken } = useAuth();
  const [data, setData] = useState(initialData);
  const [apiAvailable, setApiAvailable] = useState(initialApiConnected);
  const [accessRevoked, setAccessRevoked] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [lastSuccessAt, setLastSuccessAt] = useState<string | null>(
    initialApiConnected ? new Date().toISOString() : null,
  );
  const [callerId, setCallerId] = useState(dialerOperations?.callers[0]?.id ?? "");
  const [campaignId, setCampaignId] = useState(dialerOperations?.campaigns[0]?.id ?? "");
  const [cohortId, setCohortId] = useState("");
  const [batchId, setBatchId] = useState("");
  const [lineId, setLineId] = useState(dialerOperations?.eligible_lines[0]?.id ?? "");
  const [acceptPhrase, setAcceptPhrase] = useState("");
  const [acceptNotes, setAcceptNotes] = useState("");
  const [rejectPhrase, setRejectPhrase] = useState("");
  const [rejectNotes, setRejectNotes] = useState("");
  const [rollbackPhrase, setRollbackPhrase] = useState("");
  const [rollbackReason, setRollbackReason] = useState("");
  const [revokePhrase, setRevokePhrase] = useState("");
  const [revokeReason, setRevokeReason] = useState("");
  const [controlledNumberEvidence, setControlledNumberEvidence] = useState("");
  const [controlledPhoneNumberList, setControlledPhoneNumberList] = useState("");
  const [nonOverlapEvidence, setNonOverlapEvidence] = useState("");
  const [startReason, setStartReason] = useState("");
  const [submitReason, setSubmitReason] = useState("");
  const mountedRef = useRef(true);
  const requestSequenceRef = useRef(0);
  const requestControllerRef = useRef<AbortController | null>(null);
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  const headers = useCallback(async () => {
    const token = await getToken().catch(() => null);
    const result: Record<string, string> = { "Content-Type": "application/json" };
    if (token) result.Authorization = `Bearer ${token}`;
    else result["X-Dev-User-Email"] = devUserEmail;
    return result;
  }, [devUserEmail, getToken]);

  const refresh = useCallback(async () => {
    const requestSequence = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestSequence;
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 12_000);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/prospecting/dialer/pilot`,
        { headers: await headers(), cache: "no-store", signal: controller.signal },
      );
      if (response.status === 401 || response.status === 403) {
        if (mountedRef.current && requestSequence === requestSequenceRef.current) {
          setData(null);
          setAccessRevoked(true);
          setApiAvailable(false);
          setError("Your controlled-pilot access expired or was removed. The prior pilot snapshot was cleared.");
        }
        return;
      }
      const payload = (await response.json().catch(() => null)) as ProspectingDialerPilotOverview | null;
      if (!response.ok || !payload || !Array.isArray(payload.gates)) {
        throw new Error(responseError(payload, "Controlled-pilot evidence is temporarily unavailable."));
      }
      if (mountedRef.current && requestSequence === requestSequenceRef.current) {
        setData(payload);
        setApiAvailable(true);
        setAccessRevoked(false);
        setError("");
        setLastSuccessAt(new Date().toISOString());
      }
    } catch (requestError) {
      if (mountedRef.current && requestSequence === requestSequenceRef.current) {
        setApiAvailable(false);
        setError(
          requestError instanceof Error && requestError.name !== "AbortError"
            ? requestError.message
            : "Controlled-pilot evidence timed out. The prior confirmed snapshot remains visible.",
        );
      }
    } finally {
      window.clearTimeout(timeout);
      if (requestControllerRef.current === controller) requestControllerRef.current = null;
    }
  }, [apiBaseUrl, headers]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      requestSequenceRef.current += 1;
      requestControllerRef.current?.abort();
    };
  }, []);

  const runMutation = useCallback(async (
    action: string,
    path: string,
    method: MutationMethod,
    body: Record<string, unknown>,
    successMessage: string,
  ) => {
    setBusyAction(action);
    setMessage("");
    setError("");
    try {
      const response = await fetch(`${apiBaseUrl}${path}`, {
        method,
        headers: await headers(),
        body: JSON.stringify(body),
      });
      const payload = await response.json().catch(() => null);
      if (response.status === 401 || response.status === 403) {
        setData(null);
        setAccessRevoked(true);
        setApiAvailable(false);
        throw new Error("Your controlled-pilot access expired or was removed.");
      }
      if (!response.ok) throw new Error(responseError(payload, "The controlled-pilot change could not be saved."));
      setMessage(successMessage);
      await refresh();
      return true;
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The controlled-pilot change could not be saved.");
      return false;
    } finally {
      setBusyAction(null);
    }
  }, [apiBaseUrl, headers, refresh]);

  const pilot = data?.pilot ?? null;
  const attempts = useMemo(() => data?.attempt_review_queue ?? [], [data?.attempt_review_queue]);
  const attemptReviews = useMemo(() => data?.attempt_reviews ?? [], [data?.attempt_reviews]);
  const shifts = useMemo(() => data?.shift_reviews ?? [], [data?.shift_reviews]);
  const attemptReviewById = useMemo(
    () => new Map(attemptReviews.map((review) => [review.attempt_id, review])),
    [attemptReviews],
  );
  const reviewedShiftDates = useMemo(
    () => new Set(shifts.map((shift) => shift.shift_date)),
    [shifts],
  );
  const shiftCandidates = useMemo(() => {
    if (!pilot?.timezone) return [];
    const reviewedAttemptIds = new Set(attemptReviews.map((review) => review.attempt_id));
    const byDate = new Map<string, {
      shift_date: string;
      representative_session_id: string;
      session_ids: string[];
      call_record_ids: string[];
      completed_at: string | null;
      reserved_attempt_count: number;
      placed_call_count: number;
      all_attempts_complete: boolean;
      all_attempts_reviewed: boolean;
      provider_call_ids: string[];
    }>();
    for (const attempt of attempts) {
      if (!attempt.counts_toward_production_shift) continue;
      const shiftDate = dateKeyInTimeZone(attempt.started_at, pilot.timezone);
      if (reviewedShiftDates.has(shiftDate)) continue;
      const current = byDate.get(shiftDate) ?? {
        shift_date: shiftDate,
        representative_session_id: attempt.dial_session_id,
        session_ids: [],
        call_record_ids: [],
        completed_at: attempt.completed_at,
        reserved_attempt_count: 0,
        placed_call_count: 0,
        all_attempts_complete: true,
        all_attempts_reviewed: true,
        provider_call_ids: [],
      };
      current.reserved_attempt_count += 1;
      if (attempt.placed_call) current.placed_call_count += 1;
      current.session_ids.push(attempt.dial_session_id);
      current.call_record_ids.push(...attempt.call_record_ids);
      if (
        attempt.completed_at &&
        (!current.completed_at || new Date(attempt.completed_at) > new Date(current.completed_at))
      ) {
        current.completed_at = attempt.completed_at;
      }
      current.all_attempts_complete = current.all_attempts_complete && Boolean(attempt.completed_at);
      current.all_attempts_reviewed = current.all_attempts_reviewed && reviewedAttemptIds.has(attempt.attempt_id);
      current.provider_call_ids.push(...(attempt.provider_call_ids ?? []));
      byDate.set(shiftDate, current);
    }
    return [...byDate.values()].map((candidate) => ({
      ...candidate,
      session_ids: [...new Set(candidate.session_ids)],
      call_record_ids: [...new Set(candidate.call_record_ids)],
    })).filter((candidate) => (
      candidate.all_attempts_complete &&
      candidate.all_attempts_reviewed &&
      candidate.placed_call_count >= pilot.minimum_attempts_per_shift
    ));
  }, [attemptReviews, attempts, pilot, reviewedShiftDates]);
  const smokeProviderCallIds = useMemo(() => attempts
    .filter((attempt) => attempt.acceptance_stage === "smoke_testing")
    .flatMap((attempt) => attempt.provider_call_ids ?? []), [attempts]);
  const smokeCallCandidates = useMemo(() => attempts.flatMap((attempt) => {
    if (
      attempt.acceptance_stage !== "smoke_testing" ||
      !attempt.smoke_test_eligible ||
      !attempt.completed_at ||
      attempt.call_record_ids.length !== 1 ||
      attempt.provider_call_ids.length < 2
    ) {
      return [];
    }
    return [{
      attemptId: attempt.attempt_id,
      callRecordId: attempt.call_record_ids[0],
      providerCallIds: attempt.provider_call_ids,
    }];
  }).filter((candidate, index, values) => (
    values.findIndex((item) => item.callRecordId === candidate.callRecordId) === index
  )), [attempts]);
  const allowedActions = useMemo(() => data?.allowed_actions ?? [], [data?.allowed_actions]);
  const hasAction = useCallback((action: string, conservativeFallback = false) => (
    data ? allowedActions.includes(action) : conservativeFallback
  ), [allowedActions, data]);
  const allGatesPass = Boolean(data?.gates.length) && data!.gates.every((gate) => gate.status === "pass");
  const progress = {
    passed_shifts: data?.passed_shift_count ?? 0,
    required_shifts: pilot?.required_clean_shift_count ?? 3,
    reviewed_attempts: data?.total_reviewed_attempts ?? 0,
    total_attempts: attempts.length,
    total_attempts_required: pilot?.minimum_total_attempts ?? 75,
  };
  const controlledPhoneNumbers = useMemo(
    () => controlledPhoneNumberList
      .split(/[\n,]+/)
      .map((item) => item.trim())
      .filter(Boolean),
    [controlledPhoneNumberList],
  );
  const controlledPhoneNumbersValid = controlledPhoneNumbers.length >= 1 &&
    controlledPhoneNumbers.length <= 10 &&
    new Set(controlledPhoneNumbers).size === controlledPhoneNumbers.length &&
    controlledPhoneNumbers.every((number) => /^\+(?:1\d{10}|[2-9]\d{10,14})$/.test(number));

  const callerOptions = useMemo(
    () => (dialerOperations?.callers ?? []).filter((caller) => caller.is_active && caller.calling_enabled),
    [dialerOperations],
  );
  const selectedCallerId = callerOptions.some((caller) => caller.id === callerId)
    ? callerId
    : callerOptions[0]?.id ?? "";
  const selectedProfile = (dialerOperations?.profiles ?? []).find((profile) => (
    profile.user_id === selectedCallerId
  ));
  const campaignOptions = useMemo(
    () => (dialerOperations?.campaigns ?? []).filter((campaign) => campaign.enabled),
    [dialerOperations],
  );
  const selectedCampaignId = campaignOptions.some((campaign) => campaign.id === campaignId)
    ? campaignId
    : campaignOptions[0]?.id ?? "";
  const selectedCampaign = campaignOptions.find((campaign) => campaign.id === selectedCampaignId);
  const cohortOptions = useMemo(
    () => (campaignManagement?.cohorts ?? []).filter((cohort) => cohort.campaign_id === selectedCampaignId),
    [campaignManagement, selectedCampaignId],
  );
  const selectedCohortId = cohortOptions.some((cohort) => cohort.id === cohortId)
    ? cohortId
    : cohortOptions[0]?.id ?? "";
  const selectedCohort = cohortOptions.find((cohort) => cohort.id === selectedCohortId);
  const batchOptions = useMemo(
    () => (campaignManagement?.calling_batches ?? []).filter((batch) => (
      batch.campaign_id === selectedCampaignId &&
      (!selectedCohortId || batch.cohort_id === selectedCohortId) &&
      (!selectedCallerId || batch.assigned_user_id === selectedCallerId) &&
      batch.status !== "completed"
    )),
    [campaignManagement, selectedCallerId, selectedCampaignId, selectedCohortId],
  );
  const selectedBatchId = batchOptions.some((batch) => batch.id === batchId)
    ? batchId
    : batchOptions[0]?.id ?? "";
  const selectedBatch = batchOptions.find((batch) => batch.id === selectedBatchId);
  const lineOptions = useMemo(
    () => (dialerOperations?.eligible_lines ?? []).filter((line) => (
      line.status === "active" &&
      Boolean(selectedProfile?.voice_line_id) &&
      line.id === selectedProfile?.voice_line_id &&
      line.assigned_user_id === selectedCallerId
    )),
    [dialerOperations, selectedCallerId, selectedProfile?.voice_line_id],
  );
  const selectedLineId = lineOptions.some((line) => line.id === lineId)
    ? lineId
    : lineOptions[0]?.id ?? "";
  const selectedLine = lineOptions.find((line) => line.id === selectedLineId);
  const createPreflightBlockers = useMemo(() => {
    const blockers: string[] = [];
    if (!dialerOperations?.feature_enabled) blockers.push("The native dialer feature is not enabled.");
    if (!dialerOperations?.company_enabled) blockers.push("The company native-dialer switch is off.");
    if (
      dialerOperations?.configured_line_cap !== 1 ||
      dialerOperations?.implemented_line_cap !== 1 ||
      dialerOperations?.effective_line_cap !== 1
    ) {
      blockers.push("Company, implemented, and effective line caps must all equal one.");
    }
    if (!selectedCallerId) blockers.push("Select an active caller with calling enabled.");
    if (!selectedProfile) {
      blockers.push("The selected caller does not have a dialer profile.");
    } else {
      if (
        selectedProfile.status !== "active" ||
        !selectedProfile.user_is_active ||
        !selectedProfile.user_calling_enabled
      ) {
        blockers.push("The selected caller profile must be active and calling-enabled.");
      }
      if (
        selectedProfile.default_line_count !== 1 ||
        selectedProfile.max_line_count !== 1 ||
        selectedProfile.effective_line_count !== 1
      ) {
        blockers.push("The caller's default, maximum, and effective line caps must equal one.");
      }
      if (
        selectedProfile.daily_dial_limit == null ||
        selectedProfile.daily_dial_limit < 25 ||
        selectedProfile.daily_dial_limit > 50
      ) {
        blockers.push("The caller's daily dial cap must be between 25 and 50 so a clean shift can reach the required 25 seller calls.");
      }
      if (
        selectedProfile.daily_spend_limit_cents == null ||
        selectedProfile.daily_spend_limit_cents < 1 ||
        selectedProfile.daily_spend_limit_cents > 1_000
      ) {
        blockers.push("The caller's daily provider-spend cap must be between $0.01 and $10.00.");
      }
      if (selectedProfile.recording_policy !== "company_policy") {
        blockers.push("The caller must use the company recording policy.");
      }
      if (!selectedProfile.voice_line_id) {
        blockers.push("The caller needs an exact dedicated voice line.");
      }
    }
    if (!selectedCampaign || selectedCampaign.max_concurrent_legs !== 1) {
      blockers.push("The selected campaign must be enabled with a one-line cap.");
    }
    if (!selectedCohort || selectedCohort.dialer_mode !== "one_line_power") {
      blockers.push("The selected cohort must use one_line_power mode.");
    }
    if (!selectedBatch) {
      blockers.push("Select an active calling batch assigned to this caller and cohort.");
    } else {
      if (selectedBatch.dialer_mode !== "one_line_power") {
        blockers.push("The selected calling batch must use one_line_power mode.");
      }
      if (selectedBatch.total_entries < 75 || selectedBatch.total_entries > 250) {
        blockers.push("The controlled calling batch must contain 75–250 records.");
      }
    }
    if (
      !selectedLine ||
      selectedLine.id !== selectedProfile?.voice_line_id ||
      selectedLine.assigned_user_id !== selectedCallerId ||
      selectedLine.max_concurrent_legs !== 1
    ) {
      blockers.push("The selected line must be the caller's active, assigned, one-line profile line.");
    }
    return [...new Set(blockers)];
  }, [
    dialerOperations,
    selectedBatch,
    selectedCallerId,
    selectedCampaign,
    selectedCohort,
    selectedLine,
    selectedProfile,
  ]);
  const createReady = Boolean(
    selectedCallerId && selectedCampaignId && selectedCohortId && selectedBatchId &&
    selectedLineId && campaignManagement && dialerOperations && apiAvailable &&
    createPreflightBlockers.length === 0,
  );

  async function createPilot(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!createReady) return;
    await runMutation(
      "create",
      "/api/v1/prospecting/dialer/pilots",
      "POST",
      {
        caller_user_id: selectedCallerId,
        campaign_id: selectedCampaignId,
        cohort_id: selectedCohortId,
        prospect_calling_batch_id: selectedBatchId,
        voice_line_id: selectedLineId,
        expected_revision: 0,
        idempotency_key: operationKey("pilot-create", selectedBatchId),
      },
      "The controlled pilot was drafted. Review every gate before starting it.",
    );
  }

  async function mutatePilot(action: string, suffix: string, successMessage: string, extra: Record<string, unknown> = {}, method: MutationMethod = "POST") {
    if (!pilot) return false;
    return runMutation(
      action,
      `/api/v1/prospecting/dialer/pilots/${pilot.id}/${suffix}`,
      method,
      {
        ...extra,
        expected_revision: pilot.revision,
        idempotency_key: operationKey(`pilot-${action}`, pilot.id),
      },
      successMessage,
    );
  }

  async function saveEvidence(kind: EvidenceKind, evidence: Record<string, unknown>) {
    return mutatePilot(
      `evidence-${kind}`,
      "evidence",
      `${labelize(kind)} evidence was saved.`,
      { [kind]: evidence },
      "PUT",
    );
  }

  async function reviewAttempt(attempt: ProspectingDialerPilotAttempt, facts: ReviewPayload) {
    return mutatePilot(
      `attempt-${attempt.attempt_id}`,
      `attempts/${attempt.attempt_id}/review`,
      "The attempt review was saved and its gate was recalculated.",
      facts,
    );
  }

  async function reviewShift(sessionId: string, shiftDate: string, facts: ReviewPayload) {
    return mutatePilot(
      `shift-${sessionId}`,
      `shifts/${sessionId}/review`,
      "The shift review was saved and its gate was recalculated.",
      { ...facts, shift_date: shiftDate },
    );
  }

  const ownerAuthorized = allowedActions.includes("accept") || allowedActions.includes("reject");
  const ownerCanAccept = Boolean(
    pilot && ownerAuthorized && allGatesPass && acceptancePhrase &&
    hasAction("accept", pilot.status === "ready_for_owner_review"),
  );
  const ownerCanReject = Boolean(
    pilot && ownerAuthorized && hasAction("reject", pilot.status === "ready_for_owner_review"),
  );
  const ownerCanRevoke = Boolean(
    pilot && pilot.status === "accepted" && hasAction("revoke", false),
  );
  const terminal = pilot ? terminalPilotStatuses.has(pilot.status) : false;

  if (accessRevoked && !data) {
    return (
      <section aria-live="assertive" className={styles.pilotAccessRevoked} role="alert">
        <LockKeyhole aria-hidden="true" size={22} />
        <div><h2>Pilot acceptance access unavailable</h2><p>{error}</p><strong>No prior pilot evidence is retained in this view.</strong></div>
      </section>
    );
  }

  return (
    <div aria-busy={Boolean(busyAction)} className={styles.pilotWorkspace}>
      {message ? <p aria-live="polite" className={styles.notice}>{message}</p> : null}
      {error ? (
        <p aria-live="assertive" className={styles.error}>
          {error}{lastSuccessAt && data ? ` Last confirmed ${formatDateTime(lastSuccessAt)}.` : ""}
        </p>
      ) : null}

      <section className={styles.pilotHero}>
        <div>
          <span>D10 operating acceptance</span>
          <h2>{pilot ? labelize(pilot.status) : "No controlled pilot has been drafted"}</h2>
          <p>Technical readiness permits a test. Only verified shifts and an explicit owner decision can approve native calling for production.</p>
        </div>
        <button className={styles.secondaryButton} disabled={Boolean(busyAction)} onClick={() => void refresh()} type="button">
          <RefreshCw aria-hidden="true" size={16} /> Refresh evidence
        </button>
      </section>

      {!apiAvailable ? (
        <section className={styles.pilotUnavailable} role="status">
          <AlertTriangle aria-hidden="true" size={19} />
          <div><strong>Live pilot evidence is unavailable</strong><p>{data ? "The last confirmed snapshot remains visible, but all changes are paused." : "Reconnect to the API before drafting or approving a pilot."}</p></div>
        </section>
      ) : null}

      <section aria-label="Pilot acceptance stages" className={styles.pilotStageGrid}>
        <article>
          <Gauge aria-hidden="true" size={19} />
          <div><span>1. Technical readiness</span><strong>{data?.gates.some((gate) => gate.status === "block") ? "Blocked" : data?.gates.length ? "Measured" : "Pending"}</strong><small>D9 checks and current configuration</small></div>
        </article>
        <article>
          <ClipboardCheck aria-hidden="true" size={19} />
          <div><span>2. Controlled shifts</span><strong>{pilot?.status === "smoke_testing" ? "Smoke test required" : `${progress.passed_shifts} of ${progress.required_shifts} passed`}</strong><small>{pilot?.status === "smoke_testing" ? "Only saved test numbers are callable" : `${progress.reviewed_attempts} of ${progress.total_attempts} attempts reviewed`}</small></div>
        </article>
        <article>
          <ShieldCheck aria-hidden="true" size={19} />
          <div><span>3. Owner acceptance</span><strong>{pilot?.status === "accepted" ? "Accepted" : pilot?.status === "ready_for_owner_review" ? (ownerAuthorized ? "Owner review" : "Owner required") : terminal ? labelize(pilot?.status ?? "closed") : "Not submitted"}</strong><small>Never inferred from technical readiness</small></div>
        </article>
      </section>

      {!pilot || hasAction("create", false) ? (
        <section className={styles.pilotSection}>
          <header><div><span>Controlled scope</span><h2>Draft one small native-dialer pilot</h2></div><span className={styles.statusWarning}>Not accepted</span></header>
          <p className={styles.pilotSectionDescription}>The server fixes the safety policy: one caller and line, a 75-250 record batch, at least 3 reviewed shifts, at least 25 terminal signed seller calls and 60 minutes of provider-signed right-party conversation time per shift, 75 qualifying seller calls total, and a daily cap of 25–50 reservations plus no more than $10.</p>
          <form className={styles.pilotCreateForm} onSubmit={createPilot}>
            <label><span>VA / caller</span><select onChange={(event) => { setCallerId(event.target.value); setBatchId(""); setLineId(""); }} required value={selectedCallerId}><option value="">Select caller</option>{callerOptions.map((caller) => <option key={caller.id} value={caller.id}>{caller.display_name}</option>)}</select></label>
            <label><span>Campaign</span><select onChange={(event) => { setCampaignId(event.target.value); setCohortId(""); setBatchId(""); }} required value={selectedCampaignId}><option value="">Select campaign</option>{campaignOptions.map((campaign) => <option key={campaign.id} value={campaign.id}>{campaign.name}</option>)}</select></label>
            <label><span>Non-overlapping cohort</span><select onChange={(event) => { setCohortId(event.target.value); setBatchId(""); }} required value={selectedCohortId}><option value="">Select cohort</option>{cohortOptions.map((cohort) => <option key={cohort.id} value={cohort.id}>{cohort.name}</option>)}</select></label>
            <label><span>Calling batch</span><select onChange={(event) => setBatchId(event.target.value)} required value={selectedBatchId}><option value="">Select batch</option>{batchOptions.map((batch) => <option key={batch.id} value={batch.id}>{batch.name} - {batch.total_entries} records</option>)}</select></label>
            <label><span>Dedicated line</span><select onChange={(event) => setLineId(event.target.value)} required value={selectedLineId}><option value="">Select line</option>{lineOptions.map((line) => <option key={line.id} value={line.id}>{line.label} - {line.phone_number}</option>)}</select></label>
            <div className={styles.pilotCreateAction}><strong>Safety caps are policy-controlled</strong><span>No editable override is available in this screen.</span><button className={styles.primaryButton} disabled={Boolean(busyAction) || !createReady || !hasAction("create", true)} type="submit">Draft controlled pilot</button></div>
          </form>
          {createPreflightBlockers.length ? (
            <div aria-live="polite" className={styles.pilotCreateBlockers} role="status">
              <strong>Pilot creation is blocked until:</strong>
              <ul>{createPreflightBlockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>
            </div>
          ) : <p className={styles.pilotCreateReady}><CheckCircle2 aria-hidden="true" size={16} /> The exact one-line profile, caps, recording policy, line, cohort, and 75–250 record batch pass frontend preflight. The API will verify them again.</p>}
          {!campaignManagement || !dialerOperations ? <p className={styles.dialerInlineWarning}>Campaign or dialer configuration could not be loaded. Pilot creation is paused to prevent an overlapping or incomplete scope.</p> : null}
        </section>
      ) : null}

      {pilot ? (
        <>
          <section className={styles.pilotSection}>
            <header><div><span>Immutable scope</span><h2>{pilot.campaign_name} - {pilot.caller_name}</h2></div><span className={terminal ? styles.statusNeutral : styles.statusWarning}>{labelize(pilot.status)}</span></header>
            <dl className={styles.pilotScopeGrid}>
              <div><dt>Cohort</dt><dd>{pilot.cohort_name ?? "Not reported"}</dd></div>
              <div><dt>Calling batch</dt><dd>{pilot.calling_batch_name ?? "Not reported"}</dd></div>
              <div><dt>Dedicated line</dt><dd>{pilot.voice_line_number}</dd></div>
              <div><dt>Revision</dt><dd>{pilot.revision}</dd></div>
              <div><dt>Daily dial cap</dt><dd>{pilot.daily_dial_limit}</dd></div>
              <div><dt>Daily spend cap</dt><dd>{formatMoney(pilot.daily_spend_limit_cents)}</dd></div>
              <div><dt>Started</dt><dd>{formatDateTime(pilot.started_at)}</dd></div>
              <div><dt>Configuration</dt><dd>{data?.configuration_matches === false ? "Changed - review required" : "Matches pilot scope"}</dd></div>
            </dl>
            {pilot.status === "smoke_testing" ? <p className={styles.dialerInlineWarning}>Only the saved owner/staff test records can be called now. Complete an answered controlled call with a durable recording, refresh, then select its call record under Smoke test. Valid evidence promotes the pilot to running.</p> : null}
            {hasAction("start", pilot.status === "draft") ? (
              <form className={styles.pilotPreflightForm} onSubmit={(event) => {
                event.preventDefault();
                if (!controlledPhoneNumbersValid || controlledNumberEvidence.trim().length < 8 || nonOverlapEvidence.trim().length < 8 || startReason.trim().length < 8) return;
                void mutatePilot("start", "start", "The controlled-number smoke test began.", {
                  controlled_numbers_only: true,
                  controlled_phone_numbers: controlledPhoneNumbers,
                  controlled_number_evidence: controlledNumberEvidence.trim(),
                  batchdialer_cohort_is_separate: true,
                  batchdialer_non_overlap_evidence: nonOverlapEvidence.trim(),
                  reason: startReason.trim(),
                });
              }}>
                <strong>Preflight evidence required before the first call</strong>
                <label><span>Controlled owner/staff phone numbers</span><textarea aria-describedby="controlled-number-guidance" maxLength={1300} onChange={(event) => setControlledPhoneNumberList(event.target.value)} placeholder={"+16785550101\n+16785550102"} required value={controlledPhoneNumberList} /><small id="controlled-number-guidance">Enter 1-10 unique E.164 numbers, one per line. Each number must already exist as a test record in this selected calling batch so the coordinator can reserve it.</small>{controlledPhoneNumberList && !controlledPhoneNumbersValid ? <em>Use unique US or international numbers beginning with + and country code.</em> : null}</label>
                <label><span>Controlled-number evidence</span><textarea maxLength={1000} minLength={8} onChange={(event) => setControlledNumberEvidence(event.target.value)} placeholder="List the owner/staff test numbers and how they were verified." required value={controlledNumberEvidence} /></label>
                <label><span>BatchDialer non-overlap evidence</span><textarea maxLength={1000} minLength={8} onChange={(event) => setNonOverlapEvidence(event.target.value)} placeholder="Name the separate comparison cohort and how zero overlap was checked." required value={nonOverlapEvidence} /></label>
                <label><span>Reason to start</span><textarea maxLength={1000} minLength={8} onChange={(event) => setStartReason(event.target.value)} placeholder="Why this exact pilot scope is safe to begin." required value={startReason} /></label>
                <button className={styles.primaryButton} disabled={Boolean(busyAction) || !apiAvailable || !controlledPhoneNumbersValid || controlledNumberEvidence.trim().length < 8 || nonOverlapEvidence.trim().length < 8 || startReason.trim().length < 8} type="submit">Begin controlled-number smoke test</button>
              </form>
            ) : null}
            {hasAction("submit", pilot.status === "running") ? (
              <form className={styles.pilotSubmitForm} onSubmit={(event) => {
                event.preventDefault();
                if (submitReason.trim().length < 8) return;
                void mutatePilot("submit", "submit", "The pilot was submitted for final owner review.", { reason: submitReason.trim() });
              }}>
                <label><span>Submission reason and evidence summary</span><textarea maxLength={2000} minLength={8} onChange={(event) => setSubmitReason(event.target.value)} placeholder="Summarize why the completed evidence is ready for owner review." required value={submitReason} /></label>
                <button className={styles.secondaryButton} disabled={Boolean(busyAction) || !apiAvailable || submitReason.trim().length < 8} type="submit">Submit completed pilot</button>
              </form>
            ) : null}
          </section>

          <section className={styles.pilotSection}>
            <header><div><span>Authoritative decisions</span><h2>Acceptance gates</h2></div><span className={allGatesPass ? styles.statusGood : styles.statusWarning}>{allGatesPass ? "All pass" : "Not ready"}</span></header>
            <p className={styles.pilotSectionDescription}>These states come from Stonegate&apos;s API. A manager note cannot turn a failed control green.</p>
            <div className={styles.pilotGateGrid}>
              {(data?.gates ?? []).map((gate) => {
                const Icon = gate.status === "pass" ? CheckCircle2 : gate.status === "block" ? CircleSlash2 : AlertTriangle;
                return <article className={gateClass(gate.status)} key={gate.key}><Icon aria-hidden="true" size={18} /><div><strong>{gate.label}</strong><p>{gate.detail}</p></div><span>{labelize(gate.status)}</span></article>;
              })}
              {!data?.gates.length ? <p className={styles.dialerEmptyState}>No gate evidence was returned. Owner acceptance remains disabled.</p> : null}
            </div>
          </section>

          <section className={styles.pilotSection}>
            <header><div><span>Required observations</span><h2>Preflight, cost, comparison, and rollback evidence</h2></div><span className={styles.statusNeutral}>Typed evidence</span></header>
            <div className={styles.pilotEvidenceGrid}>
              <EvidenceCapture description="Select answered controlled seller calls, then reconcile every root and child provider ID from the entire ended smoke stage." disabled={Boolean(busyAction) || terminal || !apiAvailable || !hasAction("update_evidence", true)} kind="smoke_test" onSave={saveEvidence} smokeCallCandidates={smokeCallCandidates} smokeProviderCallIds={smokeProviderCallIds} title="Smoke test" />
              <EvidenceCapture description="Exercise both company and campaign off/on switches, safe session stops, and the saved low daily dial cap." disabled={Boolean(busyAction) || terminal || !apiAvailable || !hasAction("update_evidence", true)} kind="kill_switch" onSave={saveEvidence} title="Server-observed switch test" />
              <EvidenceCapture description="Compare the isolated native cohort against the separate BatchDialer cohort." disabled={Boolean(busyAction) || terminal || !apiAvailable || !hasAction("update_evidence", true)} kind="batchdialer_comparison" onSave={saveEvidence} title="BatchDialer comparison" />
              <EvidenceCapture description="Confirm unworked records can return safely without losing the audit trail." disabled={Boolean(busyAction) || terminal || !apiAvailable || !hasAction("update_evidence", true)} kind="rollback" onSave={saveEvidence} title="Rollback rehearsal" />
            </div>
          </section>

          <section className={styles.pilotSection}>
            <header><div><span>Every call reviewed</span><h2>Attempt evidence</h2></div><span className={styles.statusNeutral}>{progress.reviewed_attempts} / {progress.total_attempts}</span></header>
            {attempts.length ? (
              <div aria-label="Controlled pilot attempts" className={styles.pilotTableWrap} role="region" tabIndex={0}>
                <table>
                  <thead><tr><th scope="col">Call</th><th scope="col">Target</th><th scope="col">Outcome</th><th scope="col">Server evidence</th><th scope="col">Review</th></tr></thead>
                  <tbody>
                    {attempts.map((attempt) => {
                      const review = attemptReviewById.get(attempt.attempt_id);
                      const status = review?.status ?? attempt.review_status;
                      return (
                        <tr key={attempt.attempt_id}>
                          <th scope="row"><strong>{formatDateTime(attempt.started_at)}</strong><small>Session {attempt.dial_session_id.slice(0, 8)}</small></th>
                          <td>Recipient protected<small>Attempt {attempt.attempt_id.slice(0, 8)}</small></td>
                          <td>{attempt.outcome ? labelize(attempt.outcome) : "Pending"}<small>{attempt.blocker ?? "No queue blocker reported"}</small></td>
                          <td>{review ? <><span>{review.server_terminal_leg_count} / {review.server_dial_leg_count} legs terminal</span><small>Disposition {review.disposition_complete ? "complete" : "incomplete"} - Callback {review.callback_required ? (review.callback_reconciled ? "reconciled" : "open") : "not required"} - Handoff {review.handoff_required ? (review.handoff_reconciled ? "reconciled" : "open") : "not required"}</small></> : <><span>Awaiting immutable snapshot</span><small>Stonegate will calculate server facts when reviewed.</small></>}</td>
                          <td><span className={reviewClass(status)}>{labelize(status)}</span>{review ? <small>{formatDateTime(review.reviewed_at)} - {review.reason}</small> : <details><summary>Review call</summary><ReviewFacts disabled={Boolean(busyAction) || terminal || !apiAvailable || !hasAction("review_attempt", true)} kind="attempt" onSave={(facts) => reviewAttempt(attempt, facts)} /></details>}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : <p className={styles.dialerEmptyState}>No pilot attempts are on file yet. Start the controlled pilot before reviewing calls.</p>}
          </section>

          <section className={styles.pilotSection}>
            <header><div><span>Complete-shift review</span><h2>Controlled shifts</h2></div><span className={styles.statusNeutral}>{progress.passed_shifts} / {progress.required_shifts} passed</span></header>
            <p className={styles.pilotSectionDescription}>A production shift becomes reviewable after its minimum signed seller calls are terminal and every reservation has an immutable review. End every production session and verify provider-signed right-party conversation minutes before saving the one-time local-date review. Ringing, machines, and wrong parties do not add productive minutes. Smoke attempts stay outside these production totals.</p>
            <div className={styles.pilotShiftGrid}>
              {shifts.map((shift, index) => (
                <article key={shift.id}>
                  <header>
                    <div><strong>Reviewed shift {index + 1}</strong><span>{shift.shift_date} ({shift.timezone})</span></div>
                    <span className={reviewClass(shift.status)}>{labelize(shift.status)}</span>
                  </header>
                  <dl>
                    <div><dt>Reservations</dt><dd>{shift.reserved_attempt_count}</dd></div>
                    <div><dt>Provider started</dt><dd>{shift.provider_started_attempt_count}</dd></div>
                    <div><dt>Seller calls</dt><dd>{shift.placed_call_count}</dd></div>
                    <div><dt>Right-party talk time</dt><dd>{shift.productive_minutes} min</dd></div>
                  </dl>
                  <p>{formatDateTime(shift.reviewed_at)} - {shift.reason}</p>
                </article>
              ))}
              {shiftCandidates.map((candidate) => (
                <article key={candidate.shift_date}>
                  <header>
                    <div><strong>Daily shift awaiting review</strong><span>{candidate.shift_date} ({pilot.timezone}) - completed {formatDateTime(candidate.completed_at)}</span></div>
                    <span className={styles.statusWarning}>Needs review</span>
                  </header>
                  <p>{candidate.placed_call_count} signed seller calls and {candidate.reserved_attempt_count} completed, reviewed reservations across {candidate.session_ids.length} production session{candidate.session_ids.length === 1 ? "" : "s"}, {candidate.call_record_ids.length} call record{candidate.call_record_ids.length === 1 ? "" : "s"}, and {candidate.provider_call_ids.length} billable provider IDs. Stonegate aggregates the entire local date when this review is submitted.</p>
                  <ReviewFacts disabled={Boolean(busyAction) || terminal || !apiAvailable || !hasAction("review_shift", true)} kind="shift" onSave={(facts) => reviewShift(candidate.representative_session_id, candidate.shift_date, facts)} providerCallIds={candidate.provider_call_ids} />
                </article>
              ))}
              {!shifts.length && !shiftCandidates.length ? <p className={styles.dialerEmptyState}>No completed shifts are available for review.</p> : null}
            </div>
          </section>

          {!terminal ? (
            <section className={styles.pilotDangerSection}>
              <header><div><span>Immediate fallback</span><h2>Rollback to BatchDialer</h2></div><RotateCcw aria-hidden="true" size={20} /></header>
              <p>Rollback pauses the native campaign, safely ends sessions, preserves evidence, and identifies the unworked remainder for a separate controlled return to the fallback workflow.</p>
              <form onSubmit={(event) => { event.preventDefault(); if (rollbackPhrase === rollbackPhraseRequired && rollbackReason.trim().length >= 8) void mutatePilot("rollback", "rollback", "Rollback completed and the native pilot was stopped.", { confirmation_phrase: rollbackPhrase, return_unworked_cohort_to_batchdialer: true, preserve_native_evidence_read_only: true, reason: rollbackReason.trim() }); }}>
                <label><span>Reason</span><textarea maxLength={2000} minLength={8} onChange={(event) => setRollbackReason(event.target.value)} required value={rollbackReason} /></label>
                <label><span>Type exactly: <strong>{rollbackPhraseRequired}</strong></span><input autoComplete="off" maxLength={120} onChange={(event) => setRollbackPhrase(event.target.value)} required value={rollbackPhrase} /></label>
                <button className={styles.dangerButton} disabled={Boolean(busyAction) || !apiAvailable || rollbackPhrase !== rollbackPhraseRequired || rollbackReason.trim().length < 8 || !hasAction("rollback", true)} type="submit">Rollback native pilot</button>
              </form>
            </section>
          ) : null}

          <section className={styles.pilotOwnerSection}>
            <header><div><span>Final authority</span><h2>Owner decision</h2></div><ShieldCheck aria-hidden="true" size={20} /></header>
            <p>Technical readiness and manager reviews do not activate production. Only an authorized owner can record this immutable decision.</p>
            {pilot.status === "ready_for_owner_review" && !ownerAuthorized ? <p className={styles.dialerInlineWarning}>You can manage and review the pilot, but an owner must sign in to accept or reject it.</p> : null}
            {!terminal && !allGatesPass ? <p className={styles.dialerInlineWarning}>Every authoritative gate must pass before acceptance is enabled.</p> : null}
            {pilot.status === "accepted" ? <>
              <p className={styles.pilotAcceptedNotice}><CheckCircle2 aria-hidden="true" size={18} /> Production acceptance was recorded {formatDateTime(pilot.accepted_at)}.</p>
              {ownerCanRevoke ? <div className={styles.pilotDecisionGrid}>
                <form onSubmit={(event) => { event.preventDefault(); if (revokePhrase === revokePhraseRequired && revokeReason.trim().length >= 8) void mutatePilot("revoke", "revoke", "Owner authorization was revoked; unstarted work was released and provider-authorized work is draining safely.", { confirmation_phrase: revokePhrase, reason: revokeReason.trim() }); }}>
                  <strong>Revoke production authorization</strong><p>Use this if the approved scope must stop. Stonegate blocks every new seller bridge that has not already been authorized, safely drains provider work already authorized or in progress, preserves all evidence, and requires a new D10 pilot before native calling can resume.</p>
                  <label><span>Owner revocation reason</span><textarea maxLength={2000} minLength={8} onChange={(event) => setRevokeReason(event.target.value)} required value={revokeReason} /></label>
                  <label><span>Type exactly: <strong>{revokePhraseRequired}</strong></span><input autoComplete="off" maxLength={120} onChange={(event) => setRevokePhrase(event.target.value)} required value={revokePhrase} /></label>
                  <button className={styles.dangerButton} disabled={Boolean(busyAction) || !apiAvailable || revokePhrase !== revokePhraseRequired || revokeReason.trim().length < 8 || !hasAction("revoke", false)} type="submit">Revoke native dialer authorization</button>
                </form>
              </div> : <p className={styles.dialerInlineWarning}>Only an authorized owner can revoke this accepted production scope.</p>}
            </> : (
              terminal ? <p className={styles.dialerInlineWarning}>{pilot.status === "rejected" ? `The owner rejected this pilot ${formatDateTime(pilot.rejected_at)}.` : pilot.status === "rolled_back" ? `This pilot was rolled back ${formatDateTime(pilot.rolled_back_at)}.` : pilot.status === "cancelled" ? `This draft pilot was cancelled ${formatDateTime(pilot.cancelled_at)}${pilot.cancellation_reason ? `: ${pilot.cancellation_reason}` : "."}` : `This pilot was revoked ${formatDateTime(pilot.revoked_at)}${pilot.revocation_reason ? `: ${pilot.revocation_reason}` : "."}`}</p> : pilot.status !== "ready_for_owner_review" ? <p className={styles.dialerInlineWarning}>Complete the controlled evidence and submit the pilot before an owner decision can be recorded.</p> : <div className={styles.pilotDecisionGrid}>
                <form onSubmit={(event) => { event.preventDefault(); if (ownerCanAccept && acceptPhrase === acceptancePhrase && acceptNotes.trim().length >= 8) void mutatePilot("accept", "decision", "Owner acceptance was recorded.", { decision: "accept", confirmation_phrase: acceptPhrase, reason: acceptNotes.trim() }); }}>
                  <strong>Accept native dialer</strong><p>Type the server-issued phrase and record why the evidence supports production use.</p>
                  <label><span>Owner decision note</span><textarea maxLength={2000} minLength={8} onChange={(event) => setAcceptNotes(event.target.value)} required value={acceptNotes} /></label>
                  <label><span>Type exactly: <strong>{acceptancePhrase || "Phrase unavailable"}</strong></span><input autoComplete="off" maxLength={120} onChange={(event) => setAcceptPhrase(event.target.value)} required value={acceptPhrase} /></label>
                  <button className={styles.primaryButton} disabled={Boolean(busyAction) || !apiAvailable || !ownerCanAccept || acceptPhrase !== acceptancePhrase || acceptNotes.trim().length < 8} type="submit">Record owner acceptance</button>
                </form>
                <form onSubmit={(event) => { event.preventDefault(); if (ownerCanReject && rejectPhrase === rejectionPhrase && rejectNotes.trim().length >= 8) void mutatePilot("reject", "decision", "Owner rejection was recorded.", { decision: "reject", confirmation_phrase: rejectPhrase, reason: rejectNotes.trim() }); }}>
                  <strong>Reject pilot</strong><p>Rejecting preserves the evidence and keeps the native dialer outside production.</p>
                  <label><span>Owner rejection note</span><textarea maxLength={2000} minLength={8} onChange={(event) => setRejectNotes(event.target.value)} required value={rejectNotes} /></label>
                  <label><span>Type exactly: <strong>{rejectionPhrase}</strong></span><input autoComplete="off" maxLength={120} onChange={(event) => setRejectPhrase(event.target.value)} required value={rejectPhrase} /></label>
                  <button className={styles.dangerButton} disabled={Boolean(busyAction) || !apiAvailable || !ownerCanReject || rejectPhrase !== rejectionPhrase || rejectNotes.trim().length < 8} type="submit">Record owner rejection</button>
                </form>
              </div>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
