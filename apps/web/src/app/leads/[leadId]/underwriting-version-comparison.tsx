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

function changedEvidence(current: Version, baseline: Version) {
  const currentComps = new Map(current.comp_snapshot.map((comp) => [comp.key, comp]));
  const baselineComps = new Map(baseline.comp_snapshot.map((comp) => [comp.key, comp]));
  const added = [...currentComps.values()].filter((comp) => !baselineComps.has(comp.key));
  const removed = [...baselineComps.values()].filter((comp) => !currentComps.has(comp.key));
  const currentRepairs = new Map(
    current.repair_snapshot.map((item) => [item.category, item]),
  );
  const baselineRepairs = new Map(
    baseline.repair_snapshot.map((item) => [item.category, item]),
  );
  const repairCategories = new Set([...currentRepairs.keys(), ...baselineRepairs.keys()]);
  const changedRepairs = [...repairCategories].filter((category) => {
    const next = currentRepairs.get(category);
    const prior = baselineRepairs.get(category);
    return JSON.stringify(next ?? null) !== JSON.stringify(prior ?? null);
  });
  return { added, removed, changedRepairs };
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
  const evidence = changedEvidence(current, baseline);
  const adjustmentChanged =
    JSON.stringify(current.adjustment_snapshot) !== JSON.stringify(baseline.adjustment_snapshot);

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

      <div className={styles.versionEvidenceChanges}>
        <article>
          <span>Comparable set</span>
          <strong>
            {current.comp_snapshot.length} selected / {labelize(current.comp_search_level)} search
          </strong>
          <p>
            {evidence.added.length || evidence.removed.length
              ? `${evidence.added.length} added; ${evidence.removed.length} removed.`
              : "No selected-comp changes."}
          </p>
          {evidence.added.length ? <small>Added: {evidence.added.map((item) => item.address).join("; ")}</small> : null}
          {evidence.removed.length ? <small>Removed: {evidence.removed.map((item) => item.address).join("; ")}</small> : null}
        </article>
        <article>
          <span>Repair scope</span>
          <strong>
            {current.repair_snapshot.length} categories / {current.repair_catalog_version ?? "No catalog"}
          </strong>
          <p>
            {evidence.changedRepairs.length
              ? `${evidence.changedRepairs.length} changed: ${evidence.changedRepairs.map(labelize).join(", ")}.`
              : "No repair-category changes."}
          </p>
        </article>
        <article data-changed={adjustmentChanged}>
          <span>Adjustment research</span>
          <strong>
            {current.adjustment_snapshot
              ? `${labelize(current.adjustment_snapshot.status)} / ${current.adjustment_snapshot.supported_count} supported`
              : "Not recorded"}
          </strong>
          <p>
            {current.adjustment_snapshot
              ? `${current.adjustment_snapshot.withheld_count} withheld; shadow ARV change ${formatMoney(current.adjustment_snapshot.point_delta_cents)}.`
              : "No shadow adjustment evidence on this version."}
          </p>
        </article>
      </div>
    </div>
  );
}
