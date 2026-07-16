"use client";

import { useAuth } from "@clerk/nextjs";
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
  provider: string;
  requested_address: string;
  estimated_value_cents: number | null;
  estimated_value_low_cents: number | null;
  estimated_value_high_cents: number | null;
  comparables: MarketComparable[];
  source_note: string;
};

type Status = "idle" | "loading" | "loaded" | "error";

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
  const { getToken } = useAuth();
  const [status, setStatus] = useState<Status>("idle");
  const [estimate, setEstimate] = useState<MarketValueEstimate | null>(null);
  const [error, setError] = useState<string | null>(null);
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

  async function fetchEstimate() {
    setStatus("loading");
    setError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/leads/${leadId}/underwriting/market-value`,
        { headers: await getHeaders() },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? "Unable to pull market value.");
      }
      setEstimate((await response.json()) as MarketValueEstimate);
      setStatus("loaded");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to pull market value.");
      setStatus("error");
    }
  }

  return (
    <section className={styles.marketValuePanel}>
      <div className={styles.marketValueHeader}>
        <div>
          <strong>RentCast market value</strong>
          <span>Draft ARV support with sale comps</span>
        </div>
        <button disabled={status === "loading"} onClick={fetchEstimate} type="button">
          {status === "loading" ? "Pulling..." : "Pull comps"}
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
              <dt>Range</dt>
              <dd>
                {formatMoney(estimate.estimated_value_low_cents)} to{" "}
                {formatMoney(estimate.estimated_value_high_cents)}
              </dd>
            </div>
            <div>
              <dt>Comps</dt>
              <dd>{estimate.comparables.length}</dd>
            </div>
          </dl>
          <p>{estimate.source_note}</p>
          <div className={styles.compList}>
            {estimate.comparables.slice(0, 5).map((comp, index) => (
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
