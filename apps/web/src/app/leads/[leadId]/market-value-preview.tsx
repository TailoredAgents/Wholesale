"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import styles from "./page.module.css";

type MarketComparable = {
  provider_id: string | null;
  formatted_address: string | null;
  status: string | null;
  listing_type: string | null;
  property_type: string | null;
  price_cents: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  square_footage: number | null;
  year_built: number | null;
  distance_miles: number | null;
  days_old: number | null;
  correlation: number | null;
};

type MarketValueEstimate = {
  id?: string;
  underwriting_version_id?: string | null;
  provider: string;
  requested_address: string;
  estimated_value_cents: number | null;
  estimated_value_low_cents: number | null;
  estimated_value_high_cents: number | null;
  arv_low_cents?: number | null;
  arv_high_cents?: number | null;
  repair_low_cents?: number | null;
  repair_high_cents?: number | null;
  mao_low_cents?: number | null;
  mao_high_cents?: number | null;
  recommended_offer_cents?: number | null;
  confidence_score?: number;
  comparables: MarketComparable[];
  selected_comps?: MarketComparable[];
  rejected_comps?: MarketComparable[];
  source_note: string;
};

type Status = "idle" | "loading" | "loaded" | "error";
type ReportStatus = "idle" | "loading" | "error";

function formatMoney(cents: number | null) {
  if (cents === null) {
    return "Unknown";
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

function formatPercent(value: number | null) {
  if (value === null) {
    return "Unknown";
  }
  return `${Math.round(value * 100)}%`;
}

export function MarketValuePreview({ leadId }: { leadId: string }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [status, setStatus] = useState<Status>("idle");
  const [estimate, setEstimate] = useState<MarketValueEstimate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reportStatus, setReportStatus] = useState<ReportStatus>("idle");
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  async function getHeaders() {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = {};
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    } else {
      headers["X-Dev-User-Email"] = devUserEmail;
    }
    return headers;
  }

  async function createAnalysis() {
    setStatus("loading");
    setError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/leads/${leadId}/underwriting/market-analysis`,
        { headers: await getHeaders(), method: "POST" },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? "Unable to pull market value.");
      }
      setEstimate((await response.json()) as MarketValueEstimate);
      setStatus("loaded");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to analyze comps.");
      setStatus("error");
    }
  }

  async function openReport() {
    if (!estimate?.id) {
      return;
    }
    setReportStatus("loading");
    setError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/leads/${leadId}/underwriting/market-analysis/${estimate.id}/report.pdf`,
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
      setReportStatus("idle");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to build report.");
      setReportStatus("error");
    }
  }

  const comps = estimate?.selected_comps ?? estimate?.comparables ?? [];

  return (
    <section className={styles.marketValuePanel}>
      <div className={styles.marketValueHeader}>
        <div>
          <strong>RentCast comp analysis</strong>
          <span>Creates a draft ARV and offer ceiling for review</span>
        </div>
        <button disabled={status === "loading"} onClick={createAnalysis} type="button">
          {status === "loading" ? "Analyzing..." : "Analyze comps"}
        </button>
      </div>

      {error ? <p className={styles.error}>{error}</p> : null}

      {estimate ? (
        <div className={styles.marketValueResult}>
          <dl>
            <div>
              <dt>Estimate</dt>
              <dd>{formatMoney(estimate.estimated_value_cents)}</dd>
            </div>
            <div>
              <dt>ARV range</dt>
              <dd>
                {formatMoney(estimate.arv_low_cents ?? estimate.estimated_value_low_cents)} to{" "}
                {formatMoney(estimate.arv_high_cents ?? estimate.estimated_value_high_cents)}
              </dd>
            </div>
            <div>
              <dt>Offer ceiling</dt>
              <dd>
                {formatMoney(estimate.mao_low_cents ?? null)} to{" "}
                {formatMoney(estimate.mao_high_cents ?? null)}
              </dd>
            </div>
          </dl>
          <dl>
            <div>
              <dt>Repairs</dt>
              <dd>
                {formatMoney(estimate.repair_low_cents ?? null)} to{" "}
                {formatMoney(estimate.repair_high_cents ?? null)}
              </dd>
            </div>
            <div>
              <dt>Recommended</dt>
              <dd>{formatMoney(estimate.recommended_offer_cents ?? null)}</dd>
            </div>
            <div>
              <dt>Confidence</dt>
              <dd>{estimate.confidence_score ?? "Unknown"}%</dd>
            </div>
          </dl>
          <p>{estimate.source_note}</p>
          {estimate.id ? (
            <button
              className={styles.secondaryButton}
              disabled={reportStatus === "loading"}
              onClick={openReport}
              type="button"
            >
              {reportStatus === "loading" ? "Building report..." : "Open PDF report"}
            </button>
          ) : null}
          <div className={styles.compList}>
            {comps.slice(0, 5).map((comp, index) => (
              <article key={comp.provider_id ?? `${comp.formatted_address}-${index}`}>
                <div>
                  <strong>{comp.formatted_address ?? "Unknown address"}</strong>
                  <span>{formatMoney(comp.price_cents)}</span>
                </div>
                <small>
                  {comp.status ?? "Unknown status"} / {comp.property_type ?? "Unknown type"} /{" "}
                  {formatNumber(comp.square_footage)} sqft / {formatPercent(comp.correlation)}
                </small>
                <small>
                  {comp.distance_miles ?? "Unknown"} mi / {comp.days_old ?? "Unknown"} days old /{" "}
                  {comp.bedrooms ?? "?"} bd {comp.bathrooms ?? "?"} ba
                </small>
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
