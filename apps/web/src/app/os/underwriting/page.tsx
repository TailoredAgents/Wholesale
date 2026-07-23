import { ArrowRight, BarChart3, FileSearch, Gauge, MapPinned } from "lucide-react";
import Link from "next/link";

import { getDashboardData, getUnderwritingCalibration } from "../../lib/api";
import { DealControlStrip } from "../_components/deal-control-strip";
import { DealJourney } from "../_components/deal-journey";
import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { StatusBadge } from "../_components/design-system";
import { labelize } from "../os-utils";
import styles from "../_components/deal-workspaces.module.css";

export const dynamic = "force-dynamic";

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

function readiness(value: string) {
  if (value === "formula_review_ready") return "Review ready";
  if (value === "building_evidence") return "Building evidence";
  return "Insufficient sample";
}

export default async function UnderwritingPage({
  searchParams,
}: {
  searchParams: Promise<{ lead?: string }>;
}) {
  const [dashboard, calibrationResult, params] = await Promise.all([
    getDashboardData(),
    getUnderwritingCalibration(),
    searchParams,
  ]);
  const calibration = calibrationResult.calibration;
  const underwritingLeads = dashboard.leads.filter((lead) =>
    ["underwriting", "offer_pending_approval", "offer_ready", "offer_presented"].includes(
      lead.stage_key,
    ),
  );
  const selected =
    underwritingLeads.find((lead) => lead.id === params.lead) ?? underwritingLeads[0] ?? null;
  const overall = calibration?.overall;
  const sampleCount = overall?.sample_count ?? 0;
  const minimum = calibration?.minimum_sample_for_formula_review ?? 50;
  const missingEvidence = selected
    ? [selected.property_condition, selected.asking_price, selected.mortgage_balance].filter(
        (value) => !value || value.toLowerCase() === "unknown",
      ).length
    : 0;

  return (
    <WorkspacePage>
      <PageHeader
        description="Build defensible value ranges, expose missing evidence, and prepare an authorized offer."
        eyebrow="Deal flow / evidence"
        meta={
          <StatusBadge tone={calibrationResult.apiConnected ? "success" : "danger"}>
            {calibrationResult.apiConnected ? "Evidence current" : "Calibration unavailable"}
          </StatusBadge>
        }
        title="Underwriting"
      />
      <DealJourney active="underwriting" />
      <DealControlStrip
        authority={{
          label: "Authority",
          value: "Underwriter prepares",
          detail: "Offer approval remains separate",
          tone: "info",
        }}
        blocker={{
          label: "Primary blocker",
          value: selected ? (missingEvidence ? `${missingEvidence} ${missingEvidence === 1 ? "fact" : "facts"} missing` : "No intake blocker") : "No deal selected",
          detail: selected?.seller_name ?? "Waiting for underwriting",
          tone: missingEvidence ? "warning" : selected ? "success" : "neutral",
        }}
        deadline={{
          label: "Review queue",
          value: `${underwritingLeads.length} active`,
          detail: `${calibration?.uncalibrated_analysis_count ?? 0} outcomes need verification`,
        }}
        evidence={{
          label: "Verified evidence",
          value: `${sampleCount} cases`,
          detail: `${sampleCount} of ${minimum} readiness threshold`,
          tone: sampleCount >= minimum ? "success" : "warning",
        }}
        nextAction={{
          label: "Authorized next step",
          value: selected ? "Open comp analysis" : "Wait for qualified deal",
          detail: selected?.property_address ?? "Nothing requires action",
          tone: selected ? "success" : "neutral",
        }}
      />

      <section className={styles.metricRibbon} aria-label="Underwriting performance">
        <div><Gauge size={17} /><span>Median ARV error</span><strong>{percent(overall?.median_absolute_error_percentage ?? null)}</strong></div>
        <div><BarChart3 size={17} /><span>Directional bias</span><strong>{percent(overall?.median_error_percentage ?? null, true)}</strong></div>
        <div><FileSearch size={17} /><span>Range coverage</span><strong>{percent(overall?.range_coverage_percentage ?? null)}</strong></div>
        <div><MapPinned size={17} /><span>Tracked markets</span><strong>{calibration?.markets.length ?? 0}</strong></div>
      </section>

      <section className={styles.splitWorkspace}>
        <aside className={styles.queue} aria-label="Underwriting queue">
          <header><div><span>Analysis queue</span><strong>{underwritingLeads.length} deals</strong></div></header>
          {underwritingLeads.length === 0 ? <p className={styles.empty}>No deals are waiting for underwriting.</p> : null}
          {underwritingLeads.map((lead) => {
            const active = selected?.id === lead.id;
            return (
              <Link className={active ? styles.selectedRow : styles.queueRow} href={`/os/underwriting?lead=${lead.id}`} key={lead.id}>
                <div><strong>{lead.seller_name}</strong><StatusBadge tone={lead.stage_key === "offer_pending_approval" ? "warning" : "info"}>{labelize(lead.stage_key)}</StatusBadge></div>
                <span>{lead.property_address}</span>
                <dl><div><dt>Condition</dt><dd>{labelize(lead.property_condition)}</dd></div><div><dt>Asking</dt><dd>{lead.asking_price ?? "Unknown"}</dd></div></dl>
              </Link>
            );
          })}
        </aside>

        <main className={styles.detail}>
          {selected ? (
            <>
              <header className={styles.detailHeader}>
                <div><span>{labelize(selected.stage_key)}</span><h2>{selected.seller_name}</h2><p>{selected.property_address}</p></div>
                <Link className={styles.primaryLink} href={`/os/leads/${selected.id}#underwriting`}>Analyze comps <ArrowRight size={15} /></Link>
              </header>
              <div className={styles.detailGrid}>
                <section className={styles.section}>
                  <header><div><span>Decision inputs</span><h3>Seller and property evidence</h3></div></header>
                  <dl className={styles.factList}>
                    <div><dt>Property condition</dt><dd>{labelize(selected.property_condition)}</dd></div>
                    <div><dt>Seller asking price</dt><dd>{selected.asking_price ?? "Missing"}</dd></div>
                    <div><dt>Mortgage balance</dt><dd>{selected.mortgage_balance ?? "Missing"}</dd></div>
                    <div><dt>Motivation</dt><dd>{selected.motivation ?? "Missing"}</dd></div>
                    <div><dt>Timeline</dt><dd>{selected.desired_timeline ?? "Missing"}</dd></div>
                    <div><dt>Lead source</dt><dd>{labelize(selected.source)}</dd></div>
                  </dl>
                </section>
                <section className={styles.section}>
                  <header><div><span>Calibration</span><h3>How much trust is earned</h3></div><StatusBadge tone={sampleCount >= minimum ? "success" : "warning"}>{readiness(overall?.readiness ?? "insufficient_sample")}</StatusBadge></header>
                  <div className={styles.explanation}>
                    <strong>{sampleCount} verified outcomes</strong>
                    <p>Stonegate compares saved predictions with later verified values. Formula changes remain manual until the sample is large enough for review.</p>
                  </div>
                  <Link className={styles.secondaryLink} href={`/os/leads/${selected.id}#underwriting`}>Review evidence and report</Link>
                </section>
              </div>
            </>
          ) : <div className={styles.emptyState}><FileSearch size={24} /><h2>No underwriting work</h2><p>Qualified deals will appear here when they are ready for value analysis.</p></div>}
        </main>
      </section>

      <section className={styles.section}>
        <header><div><span>Accuracy ledger</span><h3>Verified outcome history</h3></div><strong>{calibration?.cases.length ?? 0} records</strong></header>
        <div className={styles.tableWrap}>
          <table><thead><tr><th>Property</th><th>Market</th><th>Evidence</th><th>Predicted ARV</th><th>Verified ARV</th><th>Error</th><th>Range</th></tr></thead>
            <tbody>
              {calibration?.cases.length ? calibration.cases.map((item) => <tr key={item.id}><td><Link href={`/os/leads/${item.lead_id}#underwriting`}>{item.property_address}</Link><small>{item.seller_name}</small></td><td>{item.market_key}</td><td>{labelize(item.benchmark_type)}</td><td>{money(item.predicted_arv_point_cents)}</td><td>{money(item.benchmark_arv_cents)}</td><td>{percent(item.arv_error_percentage, true)}</td><td><StatusBadge tone={item.arv_range_hit ? "success" : item.arv_range_hit === false ? "danger" : "neutral"}>{item.arv_range_hit === null ? "No range" : item.arv_range_hit ? "Inside" : "Outside"}</StatusBadge></td></tr>) : <tr><td colSpan={7}>No verified outcomes have been recorded.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </WorkspacePage>
  );
}
