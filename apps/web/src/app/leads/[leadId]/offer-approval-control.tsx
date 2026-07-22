"use client";

import { useAuth } from "@clerk/nextjs";
import { Check, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { LeadDetail } from "../../lib/api";
import styles from "./page.module.css";

type UnderwritingVersion = LeadDetail["underwriting_versions"][number];

type OfferPlan = {
  id: string;
  lead_id: string;
  property_id: string;
  underwriting_version_id: string;
  underwriting_version_number: number;
  market_analysis_id: string | null;
  approval_request_id: string | null;
  status: string;
  seller_asking_price_cents: number | null;
  arv_low_cents: number | null;
  arv_point_cents: number | null;
  arv_high_cents: number | null;
  total_rehab_cents: number | null;
  disposition_cents: number | null;
  opening_offer_cents: number;
  target_contract_cents: number;
  stretch_contract_cents: number;
  seller_ceiling_cents: number;
  seller_context: string | null;
  rationale: string;
  source_snapshot: Record<string, unknown>;
  approval_status: string | null;
  decision_notes: string | null;
  decided_by_user_id: string | null;
  decided_at: string | null;
  created_at: string;
};

type PlanListResponse = {
  items: OfferPlan[];
  can_approve: boolean;
};

function formatMoney(cents: number | null) {
  if (cents === null) return "Unknown";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function dollarsToCents(value: string) {
  const amount = Number(value.replace(/[$,\s]/g, ""));
  return Number.isFinite(amount) && amount >= 0 ? Math.round(amount * 100) : null;
}

function centsToDollars(value: number | null) {
  return value === null ? "" : String(Math.round(value / 100));
}

function roundTo500(cents: number) {
  return Math.round(cents / 50_000) * 50_000;
}

function ladderFor(version: UnderwritingVersion | undefined) {
  const ceiling = version?.seller_contract_ceiling_cents ?? version?.max_offer_cents ?? null;
  if (!ceiling) {
    return { opening: "", target: "", stretch: "" };
  }
  const opening = Math.min(version?.recommended_offer_cents ?? roundTo500(ceiling * 0.9), ceiling);
  const spread = ceiling - opening;
  return {
    opening: centsToDollars(opening),
    target: centsToDollars(roundTo500(opening + spread * 0.4)),
    stretch: centsToDollars(roundTo500(opening + spread * 0.75)),
  };
}

function askingPriceInput(value: string | null) {
  if (!value) return "";
  const amount = Number(value.replace(/[$,\s]/g, ""));
  return Number.isFinite(amount) ? String(amount) : "";
}

function labelize(value: string | null) {
  if (!value) return "Unknown";
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function OfferApprovalControl({
  askingPrice,
  leadId,
  versions,
}: {
  askingPrice: string | null;
  leadId: string;
  versions: UnderwritingVersion[];
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const initialVersion = versions[0];
  const initialLadder = ladderFor(initialVersion);
  const [plans, setPlans] = useState<OfferPlan[]>([]);
  const [canApprove, setCanApprove] = useState(false);
  const [selectedVersionId, setSelectedVersionId] = useState(initialVersion?.id ?? "");
  const [sellerAsking, setSellerAsking] = useState(() => askingPriceInput(askingPrice));
  const [opening, setOpening] = useState(initialLadder.opening);
  const [target, setTarget] = useState(initialLadder.target);
  const [stretch, setStretch] = useState(initialLadder.stretch);
  const [sellerContext, setSellerContext] = useState("");
  const [rationale, setRationale] = useState("");
  const [decisionNotes, setDecisionNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );
  const selectedVersion = versions.find((version) => version.id === selectedVersionId);
  const ceiling = selectedVersion?.seller_contract_ceiling_cents ?? selectedVersion?.max_offer_cents ?? null;

  const getHeaders = useCallback(async () => {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    else headers["X-Dev-User-Email"] = devUserEmail;
    return headers;
  }, [devUserEmail, getToken]);

  const fetchPlans = useCallback(async () => {
    const response = await fetch(
      `${apiBaseUrl}/api/v1/leads/${leadId}/underwriting/offer-plans`,
      { headers: await getHeaders() },
    );
    if (!response.ok) throw new Error("Unable to load offer approvals.");
    return (await response.json()) as PlanListResponse;
  }, [apiBaseUrl, getHeaders, leadId]);

  const loadPlans = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await fetchPlans();
      setPlans(payload.items);
      setCanApprove(payload.can_approve);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load offer approvals.");
    } finally {
      setLoading(false);
    }
  }, [fetchPlans]);

  useEffect(() => {
    let active = true;
    async function loadInitialPlans() {
      try {
        const payload = await fetchPlans();
        if (!active) return;
        setPlans(payload.items);
        setCanApprove(payload.can_approve);
        setError(null);
      } catch (caught) {
        if (!active) return;
        setError(caught instanceof Error ? caught.message : "Unable to load offer approvals.");
      } finally {
        if (active) setLoading(false);
      }
    }
    void loadInitialPlans();
    return () => {
      active = false;
    };
  }, [fetchPlans]);

  function selectVersion(versionId: string) {
    const version = versions.find((item) => item.id === versionId);
    const next = ladderFor(version);
    setSelectedVersionId(versionId);
    setOpening(next.opening);
    setTarget(next.target);
    setStretch(next.stretch);
    setError(null);
  }

  async function requestApproval(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedVersion || !ceiling) {
      setError("Select an underwriting version with a seller ceiling.");
      return;
    }
    const amounts = {
      opening_offer_cents: dollarsToCents(opening),
      target_contract_cents: dollarsToCents(target),
      stretch_contract_cents: dollarsToCents(stretch),
    };
    if (Object.values(amounts).some((amount) => amount === null)) {
      setError("Enter valid opening, target, and stretch amounts.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const headers = await getHeaders();
      headers["Content-Type"] = "application/json";
      const response = await fetch(
        `${apiBaseUrl}/api/v1/leads/${leadId}/underwriting/offer-plans`,
        {
          method: "POST",
          headers,
          body: JSON.stringify({
            underwriting_version_id: selectedVersion.id,
            seller_asking_price_cents: dollarsToCents(sellerAsking),
            ...amounts,
            seller_context: sellerContext.trim() || null,
            rationale: rationale.trim(),
          }),
        },
      );
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "Unable to request offer approval.");
      }
      const saved = (await response.json()) as OfferPlan;
      setPlans((current) => [
        saved,
        ...current.map((plan) =>
          plan.status === "pending"
            ? { ...plan, status: "cancelled", approval_status: "cancelled" }
            : plan,
        ),
      ]);
      setRationale("");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to request offer approval.");
    } finally {
      setSaving(false);
    }
  }

  async function decide(plan: OfferPlan, status: "approved" | "rejected") {
    if (!plan.approval_request_id) return;
    if (status === "rejected" && !decisionNotes.trim()) {
      setError("Enter decision notes before rejecting this plan.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const headers = await getHeaders();
      headers["Content-Type"] = "application/json";
      const response = await fetch(
        `${apiBaseUrl}/api/v1/approvals/${plan.approval_request_id}/decision`,
        {
          method: "PATCH",
          headers,
          body: JSON.stringify({
            status,
            decision_notes: decisionNotes.trim() || `Offer ceiling ${status}.`,
          }),
        },
      );
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "Unable to record the approval decision.");
      }
      setDecisionNotes("");
      await loadPlans();
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to record the decision.");
    } finally {
      setSaving(false);
    }
  }

  if (versions.length === 0) {
    return <p className={styles.emptyState}>Create an underwriting version before requesting an offer ceiling.</p>;
  }

  return (
    <div className={styles.offerApprovalControl}>
      <form className={styles.offerPlanForm} onSubmit={requestApproval}>
        <div className={styles.offerPlanSource}>
          <label>
            <span>Underwriting source</span>
            <select onChange={(event) => selectVersion(event.target.value)} value={selectedVersionId}>
              {versions.map((version) => (
                <option key={version.id} value={version.id}>
                  Version {version.version_number} / {labelize(version.status)}
                </option>
              ))}
            </select>
          </label>
          <dl>
            <div><dt>ARV</dt><dd>{formatMoney(selectedVersion?.arv_point_cents ?? null)}</dd></div>
            <div><dt>Repairs</dt><dd>{formatMoney(selectedVersion?.total_rehab_cents ?? selectedVersion?.repair_high_cents ?? null)}</dd></div>
            <div><dt>Disposition</dt><dd>{formatMoney(selectedVersion?.recommended_disposition_cents ?? null)}</dd></div>
            <div><dt>Ceiling</dt><dd>{formatMoney(ceiling)}</dd></div>
          </dl>
        </div>

        <div className={styles.offerLadderInputs}>
          <label><span>Seller asking</span><div><b>$</b><input min="0" onChange={(event) => setSellerAsking(event.target.value)} step="500" type="number" value={sellerAsking} /></div></label>
          <label><span>Opening</span><div><b>$</b><input min="0" onChange={(event) => setOpening(event.target.value)} required step="500" type="number" value={opening} /></div></label>
          <label><span>Target</span><div><b>$</b><input min="0" onChange={(event) => setTarget(event.target.value)} required step="500" type="number" value={target} /></div></label>
          <label><span>Stretch</span><div><b>$</b><input min="0" onChange={(event) => setStretch(event.target.value)} required step="500" type="number" value={stretch} /></div></label>
          <label><span>Walk-away ceiling</span><div><b>$</b><input readOnly value={ceiling ? Math.round(ceiling / 100) : ""} /></div></label>
        </div>

        <div className={styles.offerNarrativeGrid}>
          <label>
            <span>Seller context</span>
            <textarea maxLength={2000} onChange={(event) => setSellerContext(event.target.value)} placeholder="Price expectations, priorities, objections, and commitments" rows={3} value={sellerContext} />
          </label>
          <label>
            <span>Approval rationale</span>
            <textarea maxLength={2000} minLength={10} onChange={(event) => setRationale(event.target.value)} placeholder="Evidence and economics supporting this negotiation plan" required rows={3} value={rationale} />
          </label>
        </div>
        <div className={styles.offerPlanFooter}>
          <span>{ceiling ? `Hard ceiling ${formatMoney(ceiling)}` : "Seller ceiling unavailable"}</span>
          <button disabled={saving || !ceiling} type="submit">
            {saving ? "Submitting..." : "Request offer approval"}
          </button>
        </div>
      </form>

      <div className={styles.offerPlanHistory}>
        <div className={styles.offerPlanHistoryHeader}>
          <strong>Approval history</strong>
          <span>{loading ? "Loading" : `${plans.length} plans`}</span>
        </div>
        {plans.length === 0 && !loading ? <p>No offer plans submitted.</p> : null}
        {plans.slice(0, 5).map((plan) => (
          <article key={plan.id}>
            <div className={styles.offerPlanTitle}>
              <div>
                <strong>Version {plan.underwriting_version_number}</strong>
                <span>{new Date(plan.created_at).toLocaleString()}</span>
              </div>
              <span className={`${styles.offerStatus} ${styles[`offerStatus_${plan.status}`] ?? ""}`}>
                {labelize(plan.status)}
              </span>
            </div>
            <dl className={styles.offerLadderSummary}>
              <div><dt>Opening</dt><dd>{formatMoney(plan.opening_offer_cents)}</dd></div>
              <div><dt>Target</dt><dd>{formatMoney(plan.target_contract_cents)}</dd></div>
              <div><dt>Stretch</dt><dd>{formatMoney(plan.stretch_contract_cents)}</dd></div>
              <div><dt>Ceiling</dt><dd>{formatMoney(plan.seller_ceiling_cents)}</dd></div>
            </dl>
            <p>{plan.rationale}</p>
            {plan.decision_notes ? <small>Decision: {plan.decision_notes}</small> : null}
            {plan.status === "pending" ? (
              canApprove ? (
                <div className={styles.offerDecision}>
                  <label>
                    <span>Decision notes</span>
                    <textarea onChange={(event) => setDecisionNotes(event.target.value)} placeholder="Approval conditions or rejection reason" rows={2} value={decisionNotes} />
                  </label>
                  <div>
                    <button disabled={saving} onClick={() => void decide(plan, "approved")} title="Approve seller ceiling" type="button"><Check size={16} />Approve</button>
                    <button className={styles.rejectButton} disabled={saving} onClick={() => void decide(plan, "rejected")} title="Reject seller ceiling" type="button"><X size={16} />Reject</button>
                  </div>
                </div>
              ) : (
                <small>Awaiting an authorized offer approver.</small>
              )
            ) : null}
          </article>
        ))}
      </div>
      {error ? <p className={styles.offerPlanError}>{error}</p> : null}
    </div>
  );
}
