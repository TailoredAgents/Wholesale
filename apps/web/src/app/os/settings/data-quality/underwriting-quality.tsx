import { BarChart3, Bot, Clock3, FileSearch, Gauge, Hammer, ListChecks, MapPinned, Search } from "lucide-react";
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
  const baseline = calibration.baseline;
  const minimum = calibration.minimum_sample_for_formula_review;

  return (
    <>
      <section className={styles.metricRibbon} aria-label="Underwriting performance">
        <div><Gauge size={17} /><span>Median ARV error</span><strong>{percent(overall.median_absolute_error_percentage)}</strong></div>
        <div><BarChart3 size={17} /><span>Directional bias</span><strong>{percent(overall.median_error_percentage, true)}</strong></div>
        <div><FileSearch size={17} /><span>Range coverage</span><strong>{percent(overall.range_coverage_percentage)}</strong></div>
        <div><MapPinned size={17} /><span>Tracked markets</span><strong>{calibration.markets.length}</strong></div>
      </section>

      {baseline ? (
        <>
          <section className={styles.metricRibbon} aria-label="Underwriting operating baseline">
            <div><Search size={17} /><span>Analysis runs</span><strong>{baseline.analysis_count}</strong></div>
            <div><ListChecks size={17} /><span>Median selected comps</span><strong>{baseline.median_selected_comp_count ?? "--"}</strong></div>
            <div><Gauge size={17} /><span>Median comp yield</span><strong>{percent(baseline.median_comp_yield_percentage)}</strong></div>
            <div><Clock3 size={17} /><span>Median run time</span><strong>{baseline.median_duration_ms === null ? "--" : `${baseline.median_duration_ms.toFixed(0)} ms`}</strong></div>
          </section>
          <section className={styles.metricRibbon} aria-label="Underwriting evidence quality">
            <div><ListChecks size={17} /><span>Comp overrides</span><strong>{percent(baseline.comp_review_override_percentage)}</strong></div>
            <div><Bot size={17} /><span>AI scope corrections</span><strong>{percent(baseline.ai_scope_correction_percentage)}</strong></div>
            <div><Hammer size={17} /><span>Catalog repair error</span><strong>{percent(baseline.repair_catalog_median_absolute_error_percentage)}</strong></div>
            <div><FileSearch size={17} /><span>Catalog outcomes</span><strong>{baseline.repair_catalog_case_count}</strong></div>
          </section>
        </>
      ) : null}

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

      <section className={styles.section}>
        <header>
          <div><span>Error attribution</span><h3>Evidence segment scorecards</h3></div>
          <strong>{calibration.segments.length} segments</strong>
        </header>
        <div aria-label="Underwriting evidence segment scorecards" className={styles.tableWrap} tabIndex={0}>
          <table>
            <thead>
              <tr>
                <th>Dimension</th>
                <th>Segment</th>
                <th>Verified</th>
                <th>ARV error</th>
                <th>Range</th>
                <th>Repair error</th>
                <th>Comp overrides</th>
              </tr>
            </thead>
            <tbody>
              {calibration.segments.length ? (
                calibration.segments.map((segment) => (
                  <tr key={`${segment.dimension}-${segment.segment_key}`}>
                    <td>{labelize(segment.dimension)}</td>
                    <td><strong>{labelize(segment.segment_key)}</strong></td>
                    <td>{segment.sample_count}</td>
                    <td>{percent(segment.median_absolute_error_percentage)}</td>
                    <td>{percent(segment.range_coverage_percentage)}</td>
                    <td>
                      {percent(segment.repair_median_absolute_error_percentage)}
                      <small>{segment.repair_sample_count} outcome(s)</small>
                    </td>
                    <td>{percent(segment.comp_review_override_percentage)}</td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan={7}>Record verified outcomes to attribute errors to saved evidence.</td></tr>
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
