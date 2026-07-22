import Link from "next/link";

import { getDashboardData, getUnderwritingCalibration } from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "../page.module.css";

export const dynamic = "force-dynamic";

function formatPercent(value: number | null, signed = false) {
  if (value === null) {
    return "--";
  }
  const prefix = signed && value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(1)}%`;
}

function formatMoney(cents: number | null) {
  if (cents === null) {
    return "--";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function readinessLabel(value: string) {
  if (value === "formula_review_ready") {
    return "Review ready";
  }
  if (value === "building_evidence") {
    return "Building evidence";
  }
  return "Insufficient sample";
}

export default async function UnderwritingPage() {
  const [dashboard, calibrationResult] = await Promise.all([
    getDashboardData(),
    getUnderwritingCalibration(),
  ]);
  const calibration = calibrationResult.calibration;
  const underwritingLeads = dashboard.leads.filter((lead) =>
    ["underwriting", "offer_pending_approval", "offer_ready", "offer_presented"].includes(
      lead.stage_key,
    ),
  );
  const overall = calibration?.overall;

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Underwriting</p>
          <h2>Offer preparation and accuracy</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Verified outcomes</span>
          <strong className={styles.ready}>{overall?.sample_count ?? 0}</strong>
        </div>
      </header>

      <section className={styles.metrics}>
        <article className={styles.metric}>
          <span>Calibration cases</span>
          <strong>{overall?.sample_count ?? 0}</strong>
          <small>{calibration?.uncalibrated_analysis_count ?? 0} analyses need outcomes</small>
        </article>
        <article className={styles.metric}>
          <span>Median ARV error</span>
          <strong>{formatPercent(overall?.median_absolute_error_percentage ?? null)}</strong>
          <small>Absolute difference from verified value</small>
        </article>
        <article className={styles.metric}>
          <span>Directional bias</span>
          <strong>{formatPercent(overall?.median_error_percentage ?? null, true)}</strong>
          <small>Positive means estimates ran high</small>
        </article>
        <article className={styles.metric}>
          <span>Range coverage</span>
          <strong>{formatPercent(overall?.range_coverage_percentage ?? null)}</strong>
          <small>Verified ARV landed inside the saved range</small>
        </article>
        <article className={styles.metric}>
          <span>Formula readiness</span>
          <strong className={styles.metricStatus}>
            {readinessLabel(overall?.readiness ?? "insufficient_sample")}
          </strong>
          <small>
            {overall?.sample_count ?? 0} / {calibration?.minimum_sample_for_formula_review ?? 50}
            {" "}minimum cases
          </small>
        </article>
      </section>

      <section className={styles.contentGrid}>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Ready For Analysis</h3>
            <span>{underwritingLeads.length} leads</span>
          </div>
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Seller</th>
                  <th>Stage</th>
                  <th>Condition</th>
                  <th>Asking</th>
                  <th>Mortgage</th>
                </tr>
              </thead>
              <tbody>
                {underwritingLeads.length === 0 ? (
                  <tr>
                    <td>No leads in underwriting yet</td>
                    <td>Clear</td>
                    <td>Unknown</td>
                    <td>Unknown</td>
                    <td>Unknown</td>
                  </tr>
                ) : null}
                {underwritingLeads.map((lead) => (
                  <tr key={lead.id}>
                    <td>
                      <Link className={styles.tableLink} href={`/os/leads/${lead.id}`}>
                        {lead.seller_name}
                      </Link>
                      <small className={styles.tableSubtext}>{lead.property_address}</small>
                    </td>
                    <td>{labelize(lead.stage_key)}</td>
                    <td>{labelize(lead.property_condition)}</td>
                    <td>{lead.asking_price ?? "Unknown"}</td>
                    <td>{lead.mortgage_balance ?? "Unknown"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Market Evidence</h3>
            <span>{calibration?.markets.length ?? 0} markets</span>
          </div>
          <div className={styles.calibrationMarketList}>
            {!calibrationResult.apiConnected ? (
              <p className={styles.panelMessage}>Calibration data is unavailable.</p>
            ) : null}
            {calibration?.markets.length === 0 ? (
              <div className={styles.calibrationEmpty}>
                Record verified outcomes from saved comp analyses to establish local accuracy.
              </div>
            ) : null}
            {calibration?.markets.map((market) => (
              <div className={styles.calibrationMarketRow} key={market.market_key}>
                <div>
                  <strong>{market.market_key}</strong>
                  <span>{readinessLabel(market.readiness)}</span>
                </div>
                <dl>
                  <div>
                    <dt>Cases</dt>
                    <dd>{market.sample_count}</dd>
                  </div>
                  <div>
                    <dt>ARV error</dt>
                    <dd>{formatPercent(market.median_absolute_error_percentage)}</dd>
                  </div>
                  <div>
                    <dt>Coverage</dt>
                    <dd>{formatPercent(market.range_coverage_percentage)}</dd>
                  </div>
                </dl>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className={styles.calibrationHistory}>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <h3>Verified Outcome History</h3>
              <small>Immutable predictions compared with later evidence</small>
            </div>
            <span>{calibration?.cases.length ?? 0} records</span>
          </div>
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Property</th>
                  <th>Evidence</th>
                  <th>Predicted ARV</th>
                  <th>Benchmark ARV</th>
                  <th>Error</th>
                  <th>Range</th>
                </tr>
              </thead>
              <tbody>
                {calibration?.cases.length === 0 ? (
                  <tr>
                    <td>No verified outcomes recorded</td>
                    <td>--</td>
                    <td>--</td>
                    <td>--</td>
                    <td>--</td>
                    <td>--</td>
                  </tr>
                ) : null}
                {calibration?.cases.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <Link className={styles.tableLink} href={`/os/leads/${item.lead_id}`}>
                        {item.seller_name}
                      </Link>
                      <small className={styles.tableSubtext}>{item.property_address}</small>
                    </td>
                    <td>
                      {labelize(item.benchmark_type)}
                      <small className={styles.tableSubtext}>
                        {new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(
                          new Date(item.evidence_date),
                        )}
                      </small>
                    </td>
                    <td>{formatMoney(item.predicted_arv_point_cents)}</td>
                    <td>{formatMoney(item.benchmark_arv_cents)}</td>
                    <td>{formatPercent(item.arv_error_percentage, true)}</td>
                    <td>
                      <span
                        className={item.arv_range_hit ? styles.due : styles.unscheduled}
                      >
                        {item.arv_range_hit === null
                          ? "No range"
                          : item.arv_range_hit
                            ? "Inside"
                            : "Outside"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </>
  );
}
