"use client";

/* eslint-disable react-hooks/set-state-in-effect */

import { useAuth } from "@clerk/nextjs";
import { Check, CircleDollarSign, MessageSquareText, ShieldCheck, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import styles from "./page.module.css";

type OfferPlan = {
  id: string;
  opening_offer_cents: number;
  target_contract_cents: number;
  stretch_contract_cents: number;
  seller_ceiling_cents: number;
  underwriting_version_number: number;
};

type Concession = {
  id: string;
  approval_request_id: string | null;
  sequence_number: number;
  status: string;
  authority_basis: string;
  previous_offer_cents: number;
  proposed_offer_cents: number;
  seller_counter_cents: number | null;
  reason: string;
  seller_exchange: string;
  decision_notes: string | null;
  requested_by_name: string;
  presented_at: string | null;
  created_at: string;
};

type NegotiationEvent = {
  id: string;
  actor_name: string;
  event_type: string;
  channel: string;
  amount_cents: number | null;
  seller_counter_cents: number | null;
  notes: string;
  seller_response: string | null;
  occurred_at: string;
};

type Ledger = {
  active_plan: OfferPlan | null;
  concessions: Concession[];
  events: NegotiationEvent[];
  can_approve: boolean;
};

const channels = ["in_person", "phone", "sms", "email"] as const;

function money(cents: number | null) {
  if (cents === null) return "Not recorded";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function cents(value: string) {
  if (!value.trim()) return null;
  const amount = Number(value.replace(/[$,\s]/g, ""));
  return Number.isFinite(amount) && amount >= 0 ? Math.round(amount * 100) : null;
}

function dollars(value: number | null | undefined) {
  return value === null || value === undefined ? "" : String(Math.round(value / 100));
}

function labelize(value: string) {
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function detailMessage(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== "object") return fallback;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return (
      detail
        .map((item) =>
          item && typeof item === "object" && "msg" in item ? String(item.msg) : "",
        )
        .filter(Boolean)
        .join(" ") || fallback
    );
  }
  return fallback;
}

export function NegotiationGovernance({ leadId }: { leadId: string }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [previousOffer, setPreviousOffer] = useState("");
  const [proposedOffer, setProposedOffer] = useState("");
  const [sellerCounter, setSellerCounter] = useState("");
  const [reason, setReason] = useState("");
  const [sellerExchange, setSellerExchange] = useState("");
  const [eventType, setEventType] = useState("price_discussion");
  const [eventChannel, setEventChannel] = useState("phone");
  const [eventAmount, setEventAmount] = useState("");
  const [eventCounter, setEventCounter] = useState("");
  const [eventNotes, setEventNotes] = useState("");
  const [eventResponse, setEventResponse] = useState("");
  const [decisionNotes, setDecisionNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  const headers = useCallback(
    async (json = false) => {
      const token = await getToken().catch(() => null);
      const result: Record<string, string> = token
        ? { Authorization: `Bearer ${token}` }
        : { "X-Dev-User-Email": devUserEmail };
      if (json) result["Content-Type"] = "application/json";
      return result;
    },
    [devUserEmail, getToken],
  );

  const load = useCallback(async () => {
    const response = await fetch(
      `${apiBaseUrl}/api/v1/leads/${leadId}/underwriting/negotiation-ledger`,
      { headers: await headers() },
    );
    if (!response.ok) throw new Error("Unable to load negotiation governance.");
    const payload = (await response.json()) as Ledger;
    setLedger(payload);
    const latestPresented = payload.events.find(
      (item) =>
        item.amount_cents !== null &&
        ["concession_presented", "field_offer_presented", "agreement"].includes(
          item.event_type,
        ),
    );
    const governed = latestPresented?.amount_cents ?? payload.active_plan?.opening_offer_cents;
    setPreviousOffer(dollars(governed));
    setProposedOffer("");
  }, [apiBaseUrl, headers, leadId]);

  useEffect(() => {
    let active = true;
    load()
      .catch((caught) => {
        if (active) {
          setError(
            caught instanceof Error ? caught.message : "Unable to load negotiation governance.",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [load]);

  async function send(path: string, method: string, body: object, success: string) {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(`${apiBaseUrl}${path}`, {
        method,
        headers: await headers(true),
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        throw new Error(
          detailMessage(
            await response.json().catch(() => null),
            "The change could not be saved.",
          ),
        );
      }
      await load();
      setNotice(success);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The change could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  async function requestConcession(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ledger?.active_plan) return;
    const previous = cents(previousOffer);
    const proposed = cents(proposedOffer);
    if (previous === null || proposed === null) {
      setError("Enter valid previous and proposed offer amounts.");
      return;
    }
    await send(
      `/api/v1/leads/${leadId}/underwriting/concessions`,
      "POST",
      {
        offer_negotiation_plan_id: ledger.active_plan.id,
        previous_offer_cents: previous,
        proposed_offer_cents: proposed,
        seller_counter_cents: cents(sellerCounter),
        reason,
        seller_exchange: sellerExchange,
      },
      proposed <= ledger.active_plan.stretch_contract_cents
        ? "Concession authorized inside the approved ladder."
        : "Manager exception sent for approval.",
    );
    setReason("");
    setSellerExchange("");
    setSellerCounter("");
  }

  async function present(concession: Concession) {
    await send(
      `/api/v1/leads/${leadId}/underwriting/concessions/${concession.id}/present`,
      "POST",
      {
        channel: eventChannel,
        notes: `Presented authorized concession ${money(concession.proposed_offer_cents)} to the seller.`,
        seller_response: null,
      },
      "Presented amount added to the negotiation ledger.",
    );
  }

  async function decide(concession: Concession, status: "approved" | "rejected") {
    if (!concession.approval_request_id) return;
    if (status === "rejected" && !decisionNotes.trim()) {
      setError("Add decision notes before rejecting the exception.");
      return;
    }
    await send(
      `/api/v1/approvals/${concession.approval_request_id}/decision`,
      "PATCH",
      {
        status,
        decision_notes: decisionNotes.trim() || "Approved within the existing hard ceiling.",
      },
      `Concession ${status}.`,
    );
    setDecisionNotes("");
  }

  async function recordEvent(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ledger?.active_plan) return;
    await send(
      `/api/v1/leads/${leadId}/underwriting/negotiation-events`,
      "POST",
      {
        offer_negotiation_plan_id: ledger.active_plan.id,
        event_type: eventType,
        channel: eventChannel,
        amount_cents: cents(eventAmount),
        seller_counter_cents: cents(eventCounter),
        notes: eventNotes,
        seller_response: eventResponse.trim() || null,
        objections: [],
      },
      "Price discussion added to the permanent ledger.",
    );
    setEventAmount("");
    setEventCounter("");
    setEventNotes("");
    setEventResponse("");
  }

  if (loading) return <p className={styles.emptyState}>Loading negotiation authority...</p>;
  if (!ledger?.active_plan) {
    return (
      <p className={styles.emptyState}>
        Approve an offer plan to activate the negotiation ledger.
      </p>
    );
  }

  const plan = ledger.active_plan;
  return (
    <div className={styles.negotiationGovernance} id="negotiation-governance">
      <div className={styles.authorityHeader}>
        <div>
          <span>
            <ShieldCheck size={16} /> Active authority / Underwriting v
            {plan.underwriting_version_number}
          </span>
          <strong>
            {money(plan.opening_offer_cents)} opening to {money(plan.seller_ceiling_cents)} hard
            ceiling
          </strong>
        </div>
        <span className={styles.governanceState}>Controlled</span>
      </div>
      <dl className={styles.authorityLadder}>
        <div><dt>Opening</dt><dd>{money(plan.opening_offer_cents)}</dd><small>Approved starting point</small></div>
        <div><dt>Target</dt><dd>{money(plan.target_contract_cents)}</dd><small>Reason + seller exchange</small></div>
        <div><dt>Stretch</dt><dd>{money(plan.stretch_contract_cents)}</dd><small>Last pre-approved step</small></div>
        <div><dt>Ceiling</dt><dd>{money(plan.seller_ceiling_cents)}</dd><small>Manager exception only</small></div>
      </dl>

      <div className={styles.governanceWorkspaces}>
        <form className={styles.governanceForm} onSubmit={requestConcession}>
          <header><CircleDollarSign size={18} /><div><strong>Request next concession</strong><span>Document what Stonegate receives in exchange.</span></div></header>
          <div className={styles.governanceMoneyGrid}>
            <label><span>Current offer</span><div><b>$</b><input min="0" readOnly value={previousOffer} /></div></label>
            <label><span>Proposed offer</span><div><b>$</b><input min="0" onChange={(event) => setProposedOffer(event.target.value)} required step="500" value={proposedOffer} /></div></label>
            <label><span>Seller counter</span><div><b>$</b><input min="0" onChange={(event) => setSellerCounter(event.target.value)} step="500" value={sellerCounter} /></div></label>
          </div>
          <label><span>Why move the price?</span><textarea minLength={10} onChange={(event) => setReason(event.target.value)} required rows={3} value={reason} /></label>
          <label><span>Seller exchange</span><textarea minLength={3} onChange={(event) => setSellerExchange(event.target.value)} placeholder="Example: signed today, vacant delivery, or flexible closing" required rows={3} value={sellerExchange} /></label>
          <button disabled={saving} type="submit">{saving ? "Saving..." : "Request concession"}</button>
        </form>

        <form className={styles.governanceForm} onSubmit={recordEvent}>
          <header><MessageSquareText size={18} /><div><strong>Log price discussion</strong><span>Keep phone and meeting context attached to the offer.</span></div></header>
          <div className={styles.governanceSelectGrid}>
            <label><span>Event</span><select onChange={(event) => setEventType(event.target.value)} value={eventType}><option value="price_discussion">Price discussion</option><option value="seller_counter">Seller counter</option><option value="objection">Objection</option><option value="follow_up">Follow-up</option><option value="agreement">Agreement</option></select></label>
            <label><span>Channel</span><select onChange={(event) => setEventChannel(event.target.value)} value={eventChannel}>{channels.map((channel) => <option key={channel} value={channel}>{labelize(channel)}</option>)}</select></label>
            <label><span>Stonegate amount</span><div><b>$</b><input min="0" onChange={(event) => setEventAmount(event.target.value)} step="500" value={eventAmount} /></div></label>
            <label><span>Seller counter</span><div><b>$</b><input min="0" onChange={(event) => setEventCounter(event.target.value)} step="500" value={eventCounter} /></div></label>
          </div>
          <label><span>Discussion notes</span><textarea minLength={3} onChange={(event) => setEventNotes(event.target.value)} required rows={3} value={eventNotes} /></label>
          <label><span>Seller response</span><textarea onChange={(event) => setEventResponse(event.target.value)} rows={3} value={eventResponse} /></label>
          <button disabled={saving} type="submit">Record discussion</button>
        </form>
      </div>

      <section className={styles.concessionLedger}>
        <header><div><strong>Concession ledger</strong><span>{ledger.concessions.length} governed moves</span></div></header>
        {ledger.concessions.length === 0 ? <p>No concessions recorded. The opening offer remains active.</p> : null}
        {ledger.concessions.map((item) => (
          <article key={item.id}>
            <div className={styles.concessionSequence}>#{item.sequence_number}</div>
            <div className={styles.concessionMain}>
              <div><strong>{money(item.previous_offer_cents)} <span>to</span> {money(item.proposed_offer_cents)}</strong><span className={`${styles.concessionStatus} ${styles[`concessionStatus_${item.status}`] ?? ""}`}>{labelize(item.status)}</span></div>
              <p>{item.reason}</p>
              <small>Exchange: {item.seller_exchange}</small>
              {item.decision_notes ? <small>Decision: {item.decision_notes}</small> : null}
            </div>
            <div className={styles.concessionAction}>
              <small>{labelize(item.authority_basis)}</small>
              {item.status === "pending" && ledger.can_approve ? (
                <div className={styles.concessionDecision}>
                  <input aria-label="Decision notes" onChange={(event) => setDecisionNotes(event.target.value)} placeholder="Decision notes" value={decisionNotes} />
                  <button aria-label="Approve concession" disabled={saving} onClick={() => void decide(item, "approved")} title="Approve concession" type="button"><Check size={15} /></button>
                  <button aria-label="Reject concession" className={styles.rejectConcession} disabled={saving} onClick={() => void decide(item, "rejected")} title="Reject concession" type="button"><X size={15} /></button>
                </div>
              ) : null}
              {item.status === "pending" && !ledger.can_approve ? <span>Manager review</span> : null}
              {["authorized", "approved"].includes(item.status) ? <button disabled={saving} onClick={() => void present(item)} type="button">Record presented</button> : null}
            </div>
          </article>
        ))}
      </section>

      <section className={styles.negotiationTimeline}>
        <header><strong>Price discussion history</strong><span>{ledger.events.length} entries</span></header>
        {ledger.events.length === 0 ? <p>No price discussions recorded.</p> : null}
        {ledger.events.slice(0, 12).map((item) => (
          <article key={item.id}>
            <span className={styles.timelineMark} />
            <div><strong>{labelize(item.event_type)}</strong><span>{item.actor_name} / {labelize(item.channel)} / {new Date(item.occurred_at).toLocaleString()}</span><p>{item.notes}</p>{item.seller_response ? <small>Seller: {item.seller_response}</small> : null}</div>
            <div className={styles.timelineAmounts}>{item.amount_cents !== null ? <strong>{money(item.amount_cents)}</strong> : null}{item.seller_counter_cents !== null ? <small>Counter {money(item.seller_counter_cents)}</small> : null}</div>
          </article>
        ))}
      </section>
      {notice ? <p className={styles.governanceNotice}>{notice}</p> : null}
      {error ? <p className={styles.offerPlanError}>{error}</p> : null}
    </div>
  );
}
