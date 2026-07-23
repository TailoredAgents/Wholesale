import { ArrowRight, BadgeDollarSign, ChartNoAxesCombined, CircleDollarSign, Megaphone, UsersRound } from "lucide-react";
import Link from "next/link";

import {
  getMarketingCopilotOverview,
  getMarketingOverview,
  getWorkspaceProfile,
} from "../../lib/api";
import { ManagementJourney } from "../_components/management-journey";
import { ManagementCopilotPanel } from "../_components/management-copilot-panel";
import { ManagementSummaryStrip } from "../_components/management-summary-strip";
import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { ReportingPeriod, type ReportingPeriodKey } from "../_components/reporting-period";
import { StatusBadge } from "../_components/design-system";
import { labelize } from "../os-utils";
import { OfflineExportButton } from "./offline-export-button";
import styles from "../_components/management-workspaces.module.css";
import marketingStyles from "./marketing.module.css";

export const dynamic = "force-dynamic";

function money(cents: number | null) {
  if (cents === null) return "N/A";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(cents / 100);
}

function roas(basisPoints: number | null) {
  return basisPoints === null ? "N/A" : `${(basisPoints / 10000).toFixed(2)}x`;
}

function delta(current: number, previous: number | null | undefined) {
  if (previous === null || previous === undefined) return "Lifetime total";
  if (previous === 0) return current === 0 ? "No change" : "New in this period";
  const change = ((current - previous) / Math.abs(previous)) * 100;
  return `${change >= 0 ? "+" : ""}${change.toFixed(1)}% vs prior period`;
}

function date(value: string) {
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(new Date(value));
}

function mask(value: string) {
  return value.length <= 10 ? value : `${value.slice(0, 6)}...${value.slice(-4)}`;
}

function percentage(basisPoints: number | null) {
  return basisPoints === null ? "No baseline" : `${(basisPoints / 100).toFixed(1)}%`;
}

function vitalValue(metric: string, value: number) {
  return metric === "CLS" ? value.toFixed(3) : `${Math.round(value)} ms`;
}

function vitalTone(metric: string, value: number) {
  const good = metric === "LCP" ? value <= 2500 : metric === "INP" ? value <= 200 : value <= 0.1;
  const poor = metric === "LCP" ? value > 4000 : metric === "INP" ? value > 500 : value > 0.25;
  return good ? "success" : poor ? "danger" : "warning";
}

export default async function MarketingPage({ searchParams }: { searchParams: Promise<{ period?: string }> }) {
  const params = await searchParams;
  const period: ReportingPeriodKey = params.period === "30" || params.period === "90" ? params.period : "all";
  const periodDays = period === "all" ? undefined : Number(period);
  const copilotPeriodDays = periodDays ?? 365;
  const [{ marketing, apiConnected }, profile, marketingCopilot] = await Promise.all([
    getMarketingOverview(periodDays),
    getWorkspaceProfile(),
    getMarketingCopilotOverview(copilotPeriodDays),
  ]);
  const previous = marketing.previous_summary;
  const periodLabel = period === "all" ? "All recorded time" : `Last ${period} days`;
  const exceptions = marketing.campaigns.filter((campaign) =>
    (campaign.marketing_spend_cents > 0 && campaign.leads_created === 0) ||
    (campaign.leads_created > 0 && campaign.contracted_leads === 0) ||
    (campaign.return_on_ad_spend_basis_points !== null && campaign.return_on_ad_spend_basis_points < 10000),
  );
  const canExport = Boolean(profile?.permissions.some((permission) => ["financials:view", "communications:send_bulk"].includes(permission)));
  const primary = exceptions[0] ?? null;
  const submitRate = marketing.campaigns.reduce((total, item) => total + item.form_starts, 0)
    ? marketing.campaigns.reduce((total, item) => total + item.form_submits, 0) / marketing.campaigns.reduce((total, item) => total + item.form_starts, 0) * 100
    : 0;
  const funnel = marketing.public_funnel;
  const funnelRows = [
    ["Public page views", funnel.page_views],
    ["Address offer starts", funnel.offer_starts],
    ["Form starts", funnel.form_starts],
    ["Property step complete", funnel.step_completions.property ?? 0],
    ["Situation step complete", funnel.step_completions.situation ?? 0],
    ["Details step complete", funnel.step_completions.details ?? 0],
    ["Successful submissions", funnel.form_submits],
  ] as const;

  return <WorkspacePage>
    <PageHeader
      actions={<ReportingPeriod active={period} basePath="/os/marketing" />}
      description="Compare source economics, attributable outcomes, and conversion export readiness."
      eyebrow="Business / growth economics"
      meta={<StatusBadge tone={apiConnected ? "success" : "danger"}>{apiConnected ? "Attribution current" : "Marketing data unavailable"}</StatusBadge>}
      title="Marketing"
    />
    <ManagementJourney active="marketing" />
    <ManagementSummaryStrip
      authority={{ label: "Authority", value: canExport ? "Attribution operator" : "Reporting view", detail: canExport ? "Offline exports may be generated" : "Export controls are hidden", tone: canExport ? "success" : "info" }}
      comparison={{ label: "Revenue trend", value: delta(marketing.summary.collected_revenue_cents, previous?.collected_revenue_cents), detail: `${roas(marketing.summary.return_on_ad_spend_basis_points)} return on spend`, tone: (marketing.summary.return_on_ad_spend_basis_points ?? 0) >= 10000 ? "success" : "warning" }}
      exception={{ label: "Primary exception", value: primary ? `${labelize(primary.source)} needs review` : marketing.summary.pending_offline_exports ? `${marketing.summary.pending_offline_exports} exports pending` : "No growth exception", detail: primary ? `${money(primary.marketing_spend_cents)} spend · ${primary.contracted_leads} contracts` : "Tracked sources are reconciled", tone: primary || marketing.summary.pending_offline_exports ? "warning" : "success" }}
      nextAction={{ label: "Management next step", value: primary ? "Review source economics" : marketing.summary.pending_offline_exports ? "Process conversion exports" : "Monitor attribution", detail: "Metrics drill into source records", tone: "info" }}
      period={{ label: "Reporting basis", value: periodLabel, detail: marketing.period_start_at ? `${date(marketing.period_start_at)} through today` : "Lifetime attribution", tone: "neutral" }}
    />
    {marketingCopilot ? (
      <ManagementCopilotPanel
        endpointBase="/api/v1/marketing/copilot"
        initialData={marketingCopilot}
      />
    ) : null}

    <section className={styles.metricGrid} aria-label="Marketing performance">
      <div><BadgeDollarSign size={17} /><span>Marketing spend</span><strong>{money(marketing.summary.total_spend_cents)}</strong><small>{delta(marketing.summary.total_spend_cents, previous?.total_spend_cents)}</small></div>
      <div><CircleDollarSign size={17} /><span>Attributed revenue</span><strong>{money(marketing.summary.collected_revenue_cents)}</strong><small>{delta(marketing.summary.collected_revenue_cents, previous?.collected_revenue_cents)}</small></div>
      <div><UsersRound size={17} /><span>Cost per lead</span><strong>{money(marketing.summary.cost_per_lead_cents)}</strong><small>{marketing.summary.leads_created} attributed leads</small></div>
      <div><Megaphone size={17} /><span>Cost per contract</span><strong>{money(marketing.summary.cost_per_contract_cents)}</strong><small>{marketing.summary.contracted_leads} contracts</small></div>
      <div><ChartNoAxesCombined size={17} /><span>Return on ad spend</span><strong>{roas(marketing.summary.return_on_ad_spend_basis_points)}</strong><small>{submitRate.toFixed(1)}% form-start conversion</small></div>
    </section>

    <section className={styles.section}>
      <div className={styles.sectionHeading}><div><span>Public experience baseline</span><h2>Offer journey and real-user performance</h2></div><strong>{percentage(funnel.start_to_submit_rate_basis_points)} start-to-submit</strong></div>
      <div className={marketingStyles.funnelLayout}>
        <div className={marketingStyles.funnelRows}>
          {funnelRows.map(([label, count], index) => <div key={label}><span>{index + 1}</span><strong>{label}</strong><b>{count}</b></div>)}
        </div>
        <aside>
          <h3>Journey friction</h3>
          <dl>
            <div><dt>Validation events</dt><dd>{funnel.validation_errors}</dd></div>
            <div><dt>Submit attempts</dt><dd>{funnel.submit_attempts}</dd></div>
            <div><dt>Submit failures</dt><dd>{funnel.submit_errors}</dd></div>
            <div><dt>Abandonments</dt><dd>{funnel.form_abandons}</dd></div>
          </dl>
          <p>Counts are anonymous browser-session events. Field values are not included.</p>
        </aside>
      </div>
      <div className={marketingStyles.vitalGrid} aria-label="Core Web Vitals p75">
        {marketing.web_vitals.length ? marketing.web_vitals.map((metric) => <article key={metric.metric}><div><strong>{metric.metric} p75</strong><StatusBadge tone={vitalTone(metric.metric, metric.p75_value)}>{vitalValue(metric.metric, metric.p75_value)}</StatusBadge></div><p>{metric.sample_count} real-user samples · {percentage(metric.good_rate_basis_points)} rated good</p></article>) : <p className={styles.empty}>No real-user Core Web Vitals samples have been recorded in this period.</p>}
      </div>
    </section>

    <section className={styles.exceptionBand}>
      <div className={styles.sectionHeading}><div><span>Exception management</span><h2>Source economics requiring attention</h2></div><strong>{exceptions.length} sources</strong></div>
      <div className={marketingStyles.exceptionRows}>{exceptions.length ? exceptions.map((campaign) => <Link href={`/os/leads?q=${encodeURIComponent(campaign.source)}`} key={`${campaign.source}-${campaign.medium}-${campaign.campaign}`}><div><strong>{labelize(campaign.source)}</strong><span>{[campaign.medium, campaign.campaign].filter((value) => !["unknown", "uncategorized"].includes(value)).map(labelize).join(" / ") || "Uncategorized campaign"}</span></div><dl><div><dt>Spend</dt><dd>{money(campaign.marketing_spend_cents)}</dd></div><div><dt>Leads</dt><dd>{campaign.leads_created}</dd></div><div><dt>Contracts</dt><dd>{campaign.contracted_leads}</dd></div><div><dt>ROAS</dt><dd>{roas(campaign.return_on_ad_spend_basis_points)}</dd></div></dl><ArrowRight size={15} /></Link>) : <p className={styles.empty}>No source economics exceptions appear in this period.</p>}</div>
    </section>

    <section className={styles.section}>
      <div className={styles.sectionHeading}><div><span>Attribution ledger</span><h2>Campaign and source performance</h2></div><strong>{marketing.campaigns.length} rows</strong></div>
      <div className={styles.tableWrap}><table><thead><tr><th>Source / campaign</th><th>Views</th><th>Starts</th><th>Submits</th><th>Leads</th><th>Contracts</th><th>Spend</th><th>Revenue</th><th>CPL</th><th>ROAS</th><th>Records</th></tr></thead><tbody>{marketing.campaigns.length ? marketing.campaigns.map((campaign) => <tr key={`${campaign.source}-${campaign.medium}-${campaign.campaign}`}><td><strong>{labelize(campaign.source)}</strong><small>{[campaign.medium, campaign.campaign].filter((value) => !["unknown", "uncategorized"].includes(value)).map(labelize).join(" / ") || "No campaign"}</small></td><td>{campaign.page_views}</td><td>{campaign.form_starts}</td><td>{campaign.form_submits}</td><td>{campaign.leads_created}</td><td>{campaign.contracted_leads}</td><td>{money(campaign.marketing_spend_cents)}</td><td>{money(campaign.collected_revenue_cents)}</td><td>{money(campaign.cost_per_lead_cents)}</td><td>{roas(campaign.return_on_ad_spend_basis_points)}</td><td><Link href={`/os/leads?q=${encodeURIComponent(campaign.source)}`}>View leads</Link></td></tr>) : <tr><td colSpan={11}>No campaign data exists in this reporting period.</td></tr>}</tbody></table></div>
    </section>

    <section className={styles.section}>
      <div className={styles.sectionHeading}><div><span>Revenue feedback</span><h2>Offline conversion queue</h2></div><strong>{marketing.offline_exports.length} records</strong></div>
      <div className={marketingStyles.exportLayout}>
        <div>{marketing.offline_exports.length ? marketing.offline_exports.map((item) => <article key={item.id}><div><strong>{labelize(item.platform)}</strong><StatusBadge tone={item.status === "exported" ? "success" : item.status === "failed" ? "danger" : "warning"}>{labelize(item.status)}</StatusBadge></div><dl><div><dt>Event</dt><dd>{labelize(item.event_name)}</dd></div><div><dt>Click ID</dt><dd>{mask(item.click_id)}</dd></div><div><dt>Value</dt><dd>{money(item.value_cents)}</dd></div><div><dt>Attempts</dt><dd>{item.attempt_count}</dd></div></dl>{item.lead_id ? <Link href={`/os/leads/${item.lead_id}`}>Open attributed lead</Link> : null}{item.last_error ? <p>{item.last_error}</p> : null}</article>) : <p className={styles.empty}>No offline conversion records have been generated.</p>}</div>
        <aside><h3>Export controls</h3><p>Generate records only after collected revenue can be tied to a captured platform click identifier. Generation does not upload data to an ad platform.</p>{canExport ? <OfflineExportButton /> : <StatusBadge tone="warning">Your role cannot generate exports</StatusBadge>}</aside>
      </div>
    </section>
  </WorkspacePage>;
}
