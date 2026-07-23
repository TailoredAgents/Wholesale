import { AlertTriangle, ArrowRight, BadgeDollarSign, Landmark, Receipt, WalletCards } from "lucide-react";
import Link from "next/link";

import {
  getDashboardData,
  getDispositionOverview,
  getFinanceCopilotOverview,
  getFinanceOverview,
  getWorkspaceProfile,
} from "../../lib/api";
import { ManagementJourney } from "../_components/management-journey";
import { ManagementCopilotPanel } from "../_components/management-copilot-panel";
import { ManagementSummaryStrip } from "../_components/management-summary-strip";
import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { ReportingPeriod, type ReportingPeriodKey } from "../_components/reporting-period";
import { StatusBadge } from "../_components/design-system";
import { labelize } from "../os-utils";
import { FinanceForms } from "./finance-forms";
import styles from "../_components/management-workspaces.module.css";

export const dynamic = "force-dynamic";

function money(cents: number | null) {
  if (cents === null) return "Not set";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(cents / 100);
}

function percent(value: number) {
  return `${value.toFixed(1)}%`;
}

function delta(current: number, previous: number | undefined) {
  if (previous === undefined) return "Lifetime total";
  if (previous === 0) return current === 0 ? "No change" : "New in this period";
  const change = ((current - previous) / Math.abs(previous)) * 100;
  return `${change >= 0 ? "+" : ""}${change.toFixed(1)}% vs prior period`;
}

function date(value: string) {
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(new Date(value));
}

export default async function FinancePage({ searchParams }: { searchParams: Promise<{ period?: string }> }) {
  const params = await searchParams;
  const period: ReportingPeriodKey = params.period === "30" || params.period === "90" ? params.period : "all";
  const periodDays = period === "all" ? undefined : Number(period);
  const copilotPeriodDays = periodDays ?? 365;
  const [dashboard, financeData, dispositionData, profile, financeCopilot] = await Promise.all([
    getDashboardData(),
    getFinanceOverview(periodDays),
    getDispositionOverview(),
    getWorkspaceProfile(),
    getFinanceCopilotOverview(copilotPeriodDays),
  ]);
  const finance = financeData.finance;
  const previous = finance.previous_summary ?? undefined;
  const margin = finance.summary.collected_revenue_cents
    ? (finance.summary.company_net_cents / finance.summary.collected_revenue_cents) * 100
    : 0;
  const reconciliationExceptions = dispositionData.dispositions?.cases.filter((item) =>
    !item.reconciliation || item.reconciliation.status !== "approved" || item.reconciliation.company_margin_basis_points < item.reconciliation.target_margin_basis_points,
  ) ?? [];
  const pendingRevenue = finance.revenue_records.filter((item) => item.status === "pending");
  const canChangeComp = Boolean(profile?.permissions.includes("compensation:change_rules"));
  const periodLabel = period === "all" ? "All recorded time" : `Last ${period} days`;
  const primaryException = reconciliationExceptions[0] ?? null;

  return <WorkspacePage>
    <PageHeader
      actions={<ReportingPeriod active={period} basePath="/os/finance" />}
      description="Monitor cash, margin, reconciliation exceptions, commissions, and ledger evidence."
      eyebrow="Business / financial control"
      meta={<StatusBadge tone={financeData.apiConnected ? "success" : "danger"}>{financeData.apiConnected ? "Ledger current" : "Finance unavailable"}</StatusBadge>}
      title="Finance"
    />
    <ManagementJourney active="finance" />
    <ManagementSummaryStrip
      authority={{ label: "Authority", value: canChangeComp ? "Financial controller" : "Ledger access", detail: canChangeComp ? "Compensation rules may be changed" : "Compensation policy is view only", tone: canChangeComp ? "success" : "info" }}
      comparison={{ label: "Company net trend", value: delta(finance.summary.company_net_cents, previous?.company_net_cents), detail: `${percent(margin)} of collected revenue`, tone: finance.summary.company_net_cents >= 0 ? "success" : "danger" }}
      exception={{ label: "Primary exception", value: primaryException ? "Reconciliation needs review" : pendingRevenue.length ? `${pendingRevenue.length} revenue records pending` : "No financial exception", detail: primaryException?.property_address ?? "Current period controls are clear", tone: primaryException || pendingRevenue.length ? "warning" : "success" }}
      nextAction={{ label: "Management next step", value: primaryException ? "Open deal reconciliation" : pendingRevenue.length ? "Review pending revenue" : "Monitor margin", detail: "Source records remain linked", tone: "info" }}
      period={{ label: "Reporting basis", value: periodLabel, detail: finance.period_start_at ? `${date(finance.period_start_at)} through today` : "Lifetime ledger", tone: "neutral" }}
    />
    {financeCopilot ? (
      <ManagementCopilotPanel
        endpointBase="/api/v1/finance/copilot"
        initialData={financeCopilot}
      />
    ) : null}

    <section className={styles.metricGrid} aria-label="Financial performance">
      <div><Landmark size={17} /><span>Collected revenue</span><strong>{money(finance.summary.collected_revenue_cents)}</strong><small>{delta(finance.summary.collected_revenue_cents, previous?.collected_revenue_cents)}</small></div>
      <div><Receipt size={17} /><span>Deal deductions</span><strong>{money(finance.summary.deductions_cents)}</strong><small>{delta(finance.summary.deductions_cents, previous?.deductions_cents)}</small></div>
      <div><BadgeDollarSign size={17} /><span>Compensation</span><strong>{money(finance.summary.compensation_cents)}</strong><small>{delta(finance.summary.compensation_cents, previous?.compensation_cents)}</small></div>
      <div><WalletCards size={17} /><span>Marketing spend</span><strong>{money(finance.summary.marketing_spend_cents)}</strong><small>{delta(finance.summary.marketing_spend_cents, previous?.marketing_spend_cents)}</small></div>
      <div><Landmark size={17} /><span>Company net</span><strong>{money(finance.summary.company_net_cents)}</strong><small>{percent(margin)} retained margin</small></div>
    </section>

    <section className={styles.exceptionBand}>
      <div className={styles.sectionHeading}><div><span>Exception management</span><h2>Reconciliation and revenue</h2></div><strong>{reconciliationExceptions.length + pendingRevenue.length} open</strong></div>
      <div className={styles.exceptionGrid}>
        <section>
          <header><div><span>Deal reconciliation</span><h3>Margin and payout exceptions</h3></div><StatusBadge tone={reconciliationExceptions.length ? "warning" : "success"}>{reconciliationExceptions.length} open</StatusBadge></header>
          {reconciliationExceptions.length ? reconciliationExceptions.map((item) => <Link href={`/os/dispositions?case=${item.id}`} key={item.id}><AlertTriangle size={15} /><div><strong>{item.property_address}</strong><span>{!item.reconciliation ? "Closing statement not calculated" : `${(item.reconciliation.company_margin_basis_points / 100).toFixed(1)}% company margin`}</span></div><ArrowRight size={14} /></Link>) : <p className={styles.empty}>No reconciliation exceptions are open.</p>}
        </section>
        <section>
          <header><div><span>Cash collection</span><h3>Pending revenue evidence</h3></div><StatusBadge tone={pendingRevenue.length ? "warning" : "success"}>{pendingRevenue.length} pending</StatusBadge></header>
          {pendingRevenue.length ? pendingRevenue.map((record) => <Link href={record.lead_id ? `/os/leads/${record.lead_id}` : "/os/finance"} key={record.id}><Receipt size={15} /><div><strong>{record.seller_name ?? "Unlinked revenue"}</strong><span>{money(record.amount_cents)} · {labelize(record.source)}</span></div><ArrowRight size={14} /></Link>) : <p className={styles.empty}>No pending revenue records require evidence.</p>}
        </section>
      </div>
    </section>

    <section className={styles.section}>
      <div className={styles.sectionHeading}><div><span>Source ledger</span><h2>Revenue records</h2></div><strong>{finance.revenue_records.length} records</strong></div>
      <div className={styles.tableWrap}><table><thead><tr><th>Deal</th><th>Source</th><th>Status</th><th>Gross amount</th><th>Received</th><th>Source record</th></tr></thead><tbody>{finance.revenue_records.length ? finance.revenue_records.map((record) => <tr key={record.id}><td><strong>{record.seller_name ?? "Unlinked"}</strong><small>{record.property_address ?? "No property linked"}</small></td><td>{labelize(record.source)}</td><td><StatusBadge tone={record.status === "collected" ? "success" : record.status === "pending" ? "warning" : "neutral"}>{labelize(record.status)}</StatusBadge></td><td>{money(record.amount_cents)}</td><td>{date(record.received_at)}</td><td>{record.lead_id ? <Link href={`/os/leads/${record.lead_id}`}>Open lead</Link> : "Not linked"}</td></tr>) : <tr><td colSpan={6}>No revenue records exist in this reporting period.</td></tr>}</tbody></table></div>
    </section>

    <section className={styles.twoColumn}>
      <section className={styles.section}>
        <div className={styles.sectionHeading}><div><span>Commission ledger</span><h2>Compensation calculations</h2></div><strong>{finance.compensation_calculations.length}</strong></div>
        <div className={styles.compList}>{finance.compensation_calculations.length ? finance.compensation_calculations.map((item) => <div key={item.id}><div><strong>{labelize(item.role_key)}</strong><StatusBadge tone={item.status === "calculated" ? "info" : "neutral"}>{labelize(item.status)}</StatusBadge></div><dl><div><dt>Basis</dt><dd>{money(item.basis_amount_cents)}</dd></div><div><dt>Rate</dt><dd>{(item.basis_points / 100).toFixed(1)}%</dd></div><div><dt>Commission</dt><dd>{money(item.calculated_amount_cents)}</dd></div></dl></div>) : <p className={styles.empty}>No commission calculations in this period.</p>}</div>
      </section>
      <section className={styles.section}>
        <div className={styles.sectionHeading}><div><span>Active policy</span><h2>Compensation rules</h2></div><Link href="/os/operating-model">Open policy history</Link></div>
        <div className={styles.policyList}>{finance.compensation_rules.filter((item) => item.is_active).map((rule) => <div key={rule.id}><div><strong>{rule.name}</strong><span>{labelize(rule.role_key)}</span></div><b>{(rule.basis_points / 100).toFixed(1)}%</b><small>{labelize(rule.applies_to)} · effective {date(rule.effective_start_at)}</small></div>)}</div>
      </section>
    </section>

    <details className={styles.controlTools}>
      <summary>Ledger entry controls</summary>
      <div><p>Manual entries are operational controls. They remain separate from performance reporting and are recorded in the audit trail.</p><FinanceForms leads={dashboard.leads} /></div>
    </details>
  </WorkspacePage>;
}
