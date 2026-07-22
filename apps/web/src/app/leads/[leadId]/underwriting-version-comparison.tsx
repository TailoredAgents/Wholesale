"use client";

import { useMemo, useState } from "react";

import type { LeadDetail } from "../../lib/api";
import styles from "./page.module.css";

type Version = LeadDetail["underwriting_versions"][number];

function formatMoney(cents: number | null) {
  if (cents === null) {
    return "Not recorded";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function formatDelta(current: number | null, baseline: number | null) {
  if (current === null || baseline === null) {
    return "No comparison";
  }
  const difference = current - baseline;
  const prefix = difference > 0 ? "+" : "";
  return `${prefix}${formatMoney(difference)}`;
}

function midpoint(low: number | null, high: number | null) {
  if (low === null && high === null) {
    return null;
  }
  if (low === null) {
    return high;
  }
  if (high === null) {
    return low;
  }
  return Math.round((low + high) / 2);
}

function labelize(value: string | null) {
  return value ? value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()) : "Not recorded";
}

export function UnderwritingVersionComparison({ versions }: { versions: Version[] }) {
  const [currentId, setCurrentId] = useState(versions[0]?.id ?? "");
  const [baselineId, setBaselineId] = useState(versions[1]?.id ?? versions[0]?.id ?? "");
  const current = useMemo(
    () => versions.find((version) => version.id === currentId) ?? versions[0],
    [currentId, versions],
  );
  const baseline = useMemo(
    () => versions.find((version) => version.id === baselineId) ?? versions[1] ?? versions[0],
    [baselineId, versions],
  );

  if (!current || !baseline || versions.length < 2) {
    return null;
  }

  const rows = [
    {
      label: "ARV point",
      current: current.arv_point_cents ?? midpoint(current.arv_low_cents, current.arv_high_cents),
      baseline:
        baseline.arv_point_cents ?? midpoint(baseline.arv_low_cents, baseline.arv_high_cents),
    },
    {
      label: "Total repairs",
      current: current.total_rehab_cents ?? current.repair_high_cents,
      baseline: baseline.total_rehab_cents ?? baseline.repair_high_cents,
    },
    {
      label: "Buyer disposition",
      current: current.recommended_disposition_cents,
      baseline: baseline.recommended_disposition_cents,
    },
    {
      label: "Seller ceiling",
      current: current.seller_contract_ceiling_cents ?? current.max_offer_cents,
      baseline: baseline.seller_contract_ceiling_cents ?? baseline.max_offer_cents,
    },
    {
      label: "Opening recommendation",
      current: current.recommended_offer_cents,
      baseline: baseline.recommended_offer_cents,
    },
  ];

  return (
    <div className={styles.versionComparison}>
      <div className={styles.versionComparisonHeader}>
        <div>
          <strong>Version comparison</strong>
          <span>Review what changed before relying on a newer offer range.</span>
        </div>
        <div className={styles.versionSelectors}>
          <label>
            <span>Current</span>
            <select onChange={(event) => setCurrentId(event.target.value)} value={current.id}>
              {versions.map((version) => (
                <option key={version.id} value={version.id}>
                  Version {version.version_number}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Compare with</span>
            <select onChange={(event) => setBaselineId(event.target.value)} value={baseline.id}>
              {versions.map((version) => (
                <option key={version.id} value={version.id}>
                  Version {version.version_number}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div className={styles.versionContext}>
        <span>
          V{current.version_number}: {labelize(current.report_stage)} /{" "}
          {labelize(current.repair_estimate_source ?? current.source)}
        </span>
        <span>
          V{baseline.version_number}: {labelize(baseline.report_stage)} /{" "}
          {labelize(baseline.repair_estimate_source ?? baseline.source)}
        </span>
      </div>

      <div className={styles.versionComparisonTable}>
        <div className={styles.versionComparisonLabels}>
          <span>Metric</span>
          <span>Version {current.version_number}</span>
          <span>Version {baseline.version_number}</span>
          <span>Change</span>
        </div>
        {rows.map((row) => (
          <div className={styles.versionComparisonRow} key={row.label}>
            <strong>{row.label}</strong>
            <span>{formatMoney(row.current)}</span>
            <span>{formatMoney(row.baseline)}</span>
            <span
              className={
                row.current !== null && row.baseline !== null && row.current !== row.baseline
                  ? styles.versionChanged
                  : undefined
              }
            >
              {formatDelta(row.current, row.baseline)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
