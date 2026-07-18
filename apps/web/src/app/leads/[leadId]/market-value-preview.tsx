"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import styles from "./page.module.css";

type CompCondition = "unknown" | "as_is" | "renovated";

type MarketComparable = {
  provider_id: string | null;
  formatted_address: string | null;
  status: string | null;
  property_type: string | null;
  price_cents: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  square_footage: number | null;
  year_built: number | null;
  distance_miles: number | null;
  days_old: number | null;
  sale_date?: string | null;
  price_source?: string | null;
  verification_status?: string | null;
  condition_classification?: CompCondition | null;
  selection_reason?: string;
  score?: number;
};

type MarketValueEstimate = {
  id?: string;
  provider: string;
  requested_address: string;
  methodology_version?: string;
  estimated_value_cents: number | null;
  estimated_value_low_cents: number | null;
  estimated_value_high_cents: number | null;
  as_is_value_low_cents?: number | null;
  as_is_value_cents?: number | null;
  as_is_value_high_cents?: number | null;
  arv_low_cents?: number | null;
  arv_point_cents?: number | null;
  arv_high_cents?: number | null;
  conservative_arv_cents?: number | null;
  repair_low_cents?: number | null;
  repair_high_cents?: number | null;
  base_rehab_cents?: number | null;
  rehab_contingency_percentage?: number | null;
  total_rehab_cents?: number | null;
  flip_buyer_max_cents?: number | null;
  rental_buyer_max_cents?: number | null;
  recommended_disposition_cents?: number | null;
  seller_contract_ceiling_cents?: number | null;
  transaction_reserve_cents?: number | null;
  recommended_offer_cents?: number | null;
  monthly_rent_cents?: number | null;
  confidence_score?: number;
  manual_review_required?: boolean;
  review_reasons?: string[];
  data_disagreements?: string[];
  assumptions?: Record<string, unknown>;
  comparables?: MarketComparable[];
  selected_comps?: MarketComparable[];
  source_note: string;
};

type Status = "idle" | "loading" | "loaded" | "error";
type ReportAudience = "investor" | "client";

function formatMoney(cents: number | null | undefined) {
  if (cents === null || cents === undefined) {
    return "Not supported";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function formatNumber(value: number | null) {
  return value === null ? "Unknown" : new Intl.NumberFormat("en-US").format(value);
}

function formatDate(value: string | null | undefined) {
  if (!value) {
    return "Date unavailable";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf())
    ? value
    : new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      }).format(parsed);
}

function conditionLabel(value: CompCondition) {
  if (value === "as_is") {
    return "As-is at sale";
  }
  if (value === "renovated") {
    return "Renovated at sale";
  }
  return "Not verified";
}

export function MarketValuePreview({ leadId }: { leadId: string }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [status, setStatus] = useState<Status>("idle");
  const [estimate, setEstimate] = useState<MarketValueEstimate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reportLoading, setReportLoading] = useState<ReportAudience | null>(null);
  const [repairLevel, setRepairLevel] = useState("moderate");
  const [conditionOverrides, setConditionOverrides] = useState<Record<string, CompCondition>>(
    {},
  );
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  const getHeaders = useCallback(async () => {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = {};
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    } else {
      headers["X-Dev-User-Email"] = devUserEmail;
    }
    return headers;
  }, [devUserEmail, getToken]);

  const applyEstimate = useCallback((nextEstimate: MarketValueEstimate) => {
    setEstimate(nextEstimate);
    const nextOverrides: Record<string, CompCondition> = {};
    for (const comp of nextEstimate.selected_comps ?? []) {
      const key = comp.provider_id ?? comp.formatted_address;
      if (key) {
        nextOverrides[key] = comp.condition_classification ?? "unknown";
      }
    }
    setConditionOverrides(nextOverrides);
    const savedRepairLevel = nextEstimate.assumptions?.repair_level;
    if (typeof savedRepairLevel === "string") {
      setRepairLevel(savedRepairLevel);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    async function loadLatestAnalysis() {
      setStatus("loading");
      setError(null);
      try {
        const response = await fetch(
          `${apiBaseUrl}/api/v1/leads/${leadId}/underwriting/market-analysis`,
          { headers: await getHeaders(), signal: controller.signal },
        );
        if (response.status === 404) {
          setStatus("idle");
          return;
        }
        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          throw new Error(payload?.detail ?? "Unable to load the latest comp analysis.");
        }
        applyEstimate((await response.json()) as MarketValueEstimate);
        setStatus("loaded");
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === "AbortError") {
          return;
        }
        setError(
          caught instanceof Error
            ? caught.message
            : "Unable to load the latest comp analysis.",
        );
        setStatus("error");
      }
    }

    void loadLatestAnalysis();
    return () => controller.abort();
  }, [apiBaseUrl, applyEstimate, getHeaders, leadId]);

  async function createAnalysis(refreshMarketData = false) {
    setStatus("loading");
    setError(null);
    try {
      const headers = await getHeaders();
      headers["Content-Type"] = "application/json";
      const response = await fetch(
        `${apiBaseUrl}/api/v1/leads/${leadId}/underwriting/market-analysis`,
        {
          body: JSON.stringify({
            target_condition: "standard_flip",
            repair_level: repairLevel,
            comp_condition_overrides: conditionOverrides,
            refresh_market_data: refreshMarketData,
          }),
          headers,
          method: "POST",
        },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? "Unable to run underwriting.");
      }
      applyEstimate((await response.json()) as MarketValueEstimate);
      setStatus("loaded");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to analyze comps.");
      setStatus("error");
    }
  }

  async function openReport(audience: ReportAudience) {
    if (!estimate?.id) {
      return;
    }
    setReportLoading(audience);
    setError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/leads/${leadId}/underwriting/market-analysis/` +
          `${estimate.id}/report.pdf?audience=${audience}`,
        { headers: await getHeaders() },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? "Unable to build report.");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to build report.");
    } finally {
      setReportLoading(null);
    }
  }

  const comps = estimate?.selected_comps ?? estimate?.comparables ?? [];
  const reviewItems = [
    ...(estimate?.review_reasons ?? []),
    ...(estimate?.data_disagreements ?? []),
  ];
  const isLoading = status === "loading";
  const isV2 = estimate?.methodology_version === "v2";

  return (
    <section className={styles.marketValuePanel}>
      <div className={styles.marketValueHeader}>
        <div>
          <span className={styles.underwritingEyebrow}>Underwriting V2</span>
          <strong>Recorded sales and buyer economics</strong>
          <span>Human-reviewed evidence for ARV, repairs, and seller negotiation limits</span>
        </div>
        <div className={styles.marketValueActions}>
          {estimate ? (
            <button
              className={styles.secondaryButton}
              disabled={isLoading}
              onClick={() => createAnalysis(true)}
              type="button"
            >
              Refresh market data
            </button>
          ) : null}
          <button disabled={isLoading} onClick={() => createAnalysis(false)} type="button">
            {isLoading ? "Calculating..." : estimate ? "Recalculate" : "Run analysis"}
          </button>
        </div>
      </div>

      {error ? <p className={styles.error}>{error}</p> : null}

      {estimate ? (
        <div className={styles.marketValueResult}>
          {!isV2 ? (
            <div className={styles.reviewBanner}>
              This saved analysis uses the prior method. Recalculate to create a V2 analysis.
            </div>
          ) : null}
          <div
            className={
              (estimate.manual_review_required ?? true)
                ? styles.reviewBanner
                : styles.evidenceBanner
            }
          >
            <strong>
              {(estimate.manual_review_required ?? true)
                ? "Manual review required"
                : "Evidence threshold met"}
            </strong>
            <span>
              {estimate.confidence_score ?? 0}% confidence. A person must still approve the
              acquisition decision.
            </span>
          </div>

          <dl className={styles.decisionMetrics}>
            <div>
              <dt>As-is benchmark</dt>
              <dd>{formatMoney(estimate.as_is_value_cents)}</dd>
              <small>
                {formatMoney(estimate.as_is_value_low_cents)} to{" "}
                {formatMoney(estimate.as_is_value_high_cents)}
              </small>
            </div>
            <div>
              <dt>Conservative ARV</dt>
              <dd>{formatMoney(estimate.conservative_arv_cents)}</dd>
              <small>
                Supported range {formatMoney(estimate.arv_low_cents)} to{" "}
                {formatMoney(estimate.arv_high_cents)}
              </small>
            </div>
            <div>
              <dt>Total rehab</dt>
              <dd>{formatMoney(estimate.total_rehab_cents)}</dd>
              <small>
                Base {formatMoney(estimate.base_rehab_cents)} +{" "}
                {estimate.rehab_contingency_percentage ?? 0}% contingency
              </small>
            </div>
            <div>
              <dt>Best buyer maximum</dt>
              <dd>{formatMoney(estimate.recommended_disposition_cents)}</dd>
              <small>
                Flip {formatMoney(estimate.flip_buyer_max_cents)} / rental{" "}
                {formatMoney(estimate.rental_buyer_max_cents)}
              </small>
            </div>
            <div>
              <dt>Seller contract ceiling</dt>
              <dd>{formatMoney(estimate.seller_contract_ceiling_cents)}</dd>
              <small>Do not exceed without re-underwriting</small>
            </div>
            <div className={styles.primaryMetric}>
              <dt>Opening recommendation</dt>
              <dd>{formatMoney(estimate.recommended_offer_cents)}</dd>
              <small>Negotiation starting point, not an approved offer</small>
            </div>
          </dl>

          <div className={styles.underwritingControls}>
            <label>
              <span>Repair scope</span>
              <select value={repairLevel} onChange={(event) => setRepairLevel(event.target.value)}>
                <option value="light">Light cosmetic</option>
                <option value="moderate">Moderate renovation</option>
                <option value="heavy">Heavy renovation</option>
                <option value="structural">Structural / full rebuild</option>
              </select>
            </label>
            <div>
              <span>Monthly rent support</span>
              <strong>{formatMoney(estimate.monthly_rent_cents)}</strong>
            </div>
            <div>
              <span>Transaction reserve</span>
              <strong>{formatMoney(estimate.transaction_reserve_cents)}</strong>
            </div>
          </div>

          {reviewItems.length ? (
            <div className={styles.reviewReasons}>
              <strong>Resolve before approval</strong>
              <ul>
                {reviewItems.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className={styles.reportActions}>
            <span>Saved report</span>
            <button
              className={styles.secondaryButton}
              disabled={reportLoading !== null}
              onClick={() => openReport("investor")}
              type="button"
            >
              {reportLoading === "investor" ? "Building..." : "Investor PDF"}
            </button>
            <button
              className={styles.secondaryButton}
              disabled={reportLoading !== null}
              onClick={() => openReport("client")}
              type="button"
            >
              {reportLoading === "client" ? "Building..." : "Client PDF"}
            </button>
          </div>

          <div className={styles.compSectionHeader}>
            <div>
              <strong>Recorded-sale evidence</strong>
              <span>Classify condition from listing photos, MLS remarks, or a verified source.</span>
            </div>
            <span>{comps.length} selected</span>
          </div>
          <div className={styles.compList}>
            {comps.slice(0, 5).map((comp, index) => {
              const compKey = comp.provider_id ?? comp.formatted_address ?? `comp-${index}`;
              const condition = conditionOverrides[compKey] ?? "unknown";
              return (
                <article key={compKey}>
                  <div>
                    <strong>{comp.formatted_address ?? "Unknown address"}</strong>
                    <span>{formatMoney(comp.price_cents)}</span>
                  </div>
                  <small>
                    Recorded {formatDate(comp.sale_date)} / {comp.distance_miles ?? "?"} mi /{" "}
                    {formatNumber(comp.square_footage)} sqft / {comp.bedrooms ?? "?"} bd{" "}
                    {comp.bathrooms ?? "?"} ba
                  </small>
                  <small>
                    Match score {comp.score ?? "?"}/100. {comp.selection_reason}
                  </small>
                  <label className={styles.compCondition}>
                    <span>Condition at sale</span>
                    <select
                      aria-label={`Condition at sale for ${comp.formatted_address ?? "comparable"}`}
                      onChange={(event) =>
                        setConditionOverrides((current) => ({
                          ...current,
                          [compKey]: event.target.value as CompCondition,
                        }))
                      }
                      value={condition}
                    >
                      {(["unknown", "as_is", "renovated"] as CompCondition[]).map((value) => (
                        <option key={value} value={value}>
                          {conditionLabel(value)}
                        </option>
                      ))}
                    </select>
                  </label>
                </article>
              );
            })}
          </div>
          <p>{estimate.source_note}</p>
        </div>
      ) : null}
    </section>
  );
}
