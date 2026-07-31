import { BarChart3, FileSearch, Gauge, MapPinned } from "lucide-react";
import Link from "next/link";

import type { UnderwritingCalibration } from "../../../lib/api";
import { StatusBadge } from "../../_components/design-system";
import { labelize } from "../../os-utils";
import styles from "../../_components/deal-workspaces.module.css";
import { CalibrationGovernance } from "../../underwriting/calibration-governance";

function percent(value: number | null, signed = false) {
  if (value === null) return "--";
  return `${signed && value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function money(cents: number | null) {
  if (cents === null) return "--";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function adequacyTone(value: string): "success" | "warning" | "danger" | "neutral" {
  if (value === "adequate") return "success";
  if (value === "monitor") return "warning";
  if (value === "provider_review_required") return "danger";
  return "neutral";
}

export function UnderwritingQuality({
  calibration,
}: {
  calibration: UnderwritingCalibration;
}) {
  const overall = calibration.overall;
  const minimum = calibration.minimum_sample_for_formula_review;

  return (
    <>
      <section className={styles.metricRibbon} aria-label="Underwriting performance">
        <div><Gauge size={17} /><span>Median ARV error</span><strong>{percent(overall.median_absolute_error_percentage)}</strong></div>
        <div><BarChart3 size={17} /><span>Directional bias</span><strong>{percent(overall.median_error_percentage, true)}</strong></div>
        <div><FileSearch size={17} /><span>Range coverage</span><strong>{percent(overall.range_coverage_percentage)}</strong></div>
        <div><MapPinned size={17} /><span>Tracked markets</span><strong>{calibration.markets.length}</strong></div>
      </section>

      <section className={styles.section}>
        <header>
          <div><span>Valuation quality</span><h3>Provider and methodology scorecard</h3></div>
          <strong>{calibration.provider_scorecards.length} scorecards</strong>
        </header>
        <div aria-label="Underwriting market scorecard" className={styles.tableWrap} tabIndex={0}>
          <table>
            <thead>
              <tr>
                <th>Market</th>
                <th>Provider</th>
                <th>Verified</th>
                <th>ARV error</th>
                <th>Bias</th>
                <th>Range</th>
                <th>Comp overrides</th>
                <th>Adequacy</th>
              </tr>
            </thead>
            <tbody>
              {calibration.provider_scorecards.length ? (
                calibration.provider_scorecards.map((market) => (
                  <tr key={`${market.market_key}-${market.providers.join("-")}`}>
                    <td>
                      <strong>{market.market_key}</strong>
                      <small>
                        {market.methodology_versions.length
                          ? market.methodology_versions.join(", ")
                          : "Method version unavailable"}
                      </small>
                    </td>
                    <td>{market.providers.length ? market.providers.join(", ") : "Unknown"}</td>
                    <td>{market.sample_count} / {minimum}</td>
                    <td>{percent(market.median_absolute_error_percentage)}</td>
                    <td>{percent(market.median_error_percentage, true)}</td>
                    <td>{percent(market.range_coverage_percentage)}</td>
                    <td>
                      {market.comp_review_override_percentage === null
                        ? "--"
                        : `${percent(market.comp_review_override_percentage)} (${market.comp_review_override_count})`}
                    </td>
                    <td>
                      <StatusBadge tone={adequacyTone(market.provider_adequacy)}>
                        {labelize(market.provider_adequacy)}
                      </StatusBadge>
                      {market.failure_patterns.map((pattern) => (
                        <small key={pattern}>{pattern}</small>
                      ))}
                    </td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan={8}>Record verified outcomes to begin market calibration.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <CalibrationGovernance
        decisions={calibration.decisions}
        markets={calibration.markets}
      />

      <section className={styles.section}>
        <header>
          <div><span>Accuracy ledger</span><h3>Verified outcome history</h3></div>
          <strong>{calibration.cases.length} records</strong>
        </header>
        <div aria-label="Verified outcome history table" className={styles.tableWrap} tabIndex={0}>
          <table>
            <thead>
              <tr><th>Property</th><th>Market</th><th>Evidence</th><th>Provider</th><th>Predicted ARV</th><th>Verified ARV</th><th>Error</th><th>Range</th></tr>
            </thead>
            <tbody>
              {calibration.cases.length ? (
                calibration.cases.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <Link href={`/os/leads/${item.lead_id}?tab=valuation`}>{item.property_address}</Link>
                      <small>{item.seller_name}</small>
                    </td>
                    <td>{item.market_key}</td>
                    <td>{labelize(item.benchmark_type)}</td>
                    <td>{labelize(item.provider)}<small>{item.methodology_version ?? "Unversioned"} / {item.confidence_score}% confidence</small></td>
                    <td>{money(item.predicted_arv_point_cents)}</td>
                    <td>{money(item.benchmark_arv_cents)}</td>
                    <td>{percent(item.arv_error_percentage, true)}</td>
                    <td>
                      <StatusBadge tone={item.arv_range_hit ? "success" : item.arv_range_hit === false ? "danger" : "neutral"}>
                        {item.arv_range_hit === null ? "No range" : item.arv_range_hit ? "Inside" : "Outside"}
                      </StatusBadge>
                    </td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan={8}>No verified outcomes have been recorded.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
