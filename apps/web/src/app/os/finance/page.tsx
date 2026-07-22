import { getDashboardData, getFinanceOverview } from "../../lib/api";
import { labelize } from "../os-utils";
import { FinanceForms } from "./finance-forms";
import styles from "../page.module.css";

export const dynamic = "force-dynamic";

function formatMoney(cents: number | null) {
  if (cents === null) {
    return "Not set";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function formatPercent(basisPoints: number) {
  return `${(basisPoints / 100).toFixed(2)}%`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
  }).format(new Date(value));
}

export default async function FinancePage() {
  const [dashboard, financeData] = await Promise.all([getDashboardData(), getFinanceOverview()]);
  const finance = financeData.finance;

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Finance</p>
          <h2>Finance</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Finance data</span>
          <strong className={financeData.apiConnected ? styles.ready : styles.warning}>
            {financeData.apiConnected ? "Live ledger" : "API fallback"}
          </strong>
        </div>
      </header>

      <section className={styles.metrics}>
        <article className={styles.metric}>
          <span>Collected revenue</span>
          <strong>{formatMoney(finance.summary.collected_revenue_cents)}</strong>
          <small>{formatMoney(finance.summary.pending_revenue_cents)} pending</small>
        </article>
        <article className={styles.metric}>
          <span>Deal deductions</span>
          <strong>{formatMoney(finance.summary.deductions_cents)}</strong>
          <small>Direct deal costs</small>
        </article>
        <article className={styles.metric}>
          <span>Net revenue</span>
          <strong>{formatMoney(finance.summary.net_revenue_cents)}</strong>
          <small>Before comp and marketing</small>
        </article>
        <article className={styles.metric}>
          <span>Compensation</span>
          <strong>{formatMoney(finance.summary.compensation_cents)}</strong>
          <small>{finance.compensation_rules.length} active rule records</small>
        </article>
        <article className={styles.metric}>
          <span>Company net</span>
          <strong>{formatMoney(finance.summary.company_net_cents)}</strong>
          <small>{formatMoney(finance.summary.marketing_spend_cents)} marketing spend</small>
        </article>
      </section>

      <section className={styles.contentGrid}>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Finance Entry</h3>
            <span>Manual ledger</span>
          </div>
          <FinanceForms leads={dashboard.leads} />
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Revenue Ledger</h3>
            <span>{finance.revenue_records.length} records</span>
          </div>
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Deal</th>
                  <th>Source</th>
                  <th>Status</th>
                  <th>Amount</th>
                  <th>Received</th>
                </tr>
              </thead>
              <tbody>
                {finance.revenue_records.length === 0 ? (
                  <tr>
                    <td>No revenue records yet</td>
                    <td>None</td>
                    <td>Clear</td>
                    <td>$0</td>
                    <td>None</td>
                  </tr>
                ) : null}
                {finance.revenue_records.map((record) => (
                  <tr key={record.id}>
                    <td>
                      {record.seller_name ?? "Unlinked"}
                      <small className={styles.tableSubtext}>
                        {record.property_address ?? "No property linked"}
                      </small>
                    </td>
                    <td>{labelize(record.source)}</td>
                    <td>{labelize(record.status)}</td>
                    <td>{formatMoney(record.amount_cents)}</td>
                    <td>{formatDate(record.received_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Compensation Calculations</h3>
            <span>{finance.compensation_calculations.length} calculations</span>
          </div>
          <div className={styles.buyerList}>
            {finance.compensation_calculations.length === 0 ? (
              <p>No compensation calculated yet.</p>
            ) : null}
            {finance.compensation_calculations.map((calculation) => (
              <article key={calculation.id}>
                <div>
                  <strong>{labelize(calculation.role_key)}</strong>
                  <span>{labelize(calculation.status)}</span>
                </div>
                <dl>
                  <div>
                    <dt>Basis</dt>
                    <dd>{formatMoney(calculation.basis_amount_cents)}</dd>
                  </div>
                  <div>
                    <dt>Rate</dt>
                    <dd>{formatPercent(calculation.basis_points)}</dd>
                  </div>
                  <div>
                    <dt>Amount</dt>
                    <dd>{formatMoney(calculation.calculated_amount_cents)}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Deductions And Spend</h3>
            <span>{finance.deductions.length + finance.marketing_spend.length} records</span>
          </div>
          <div className={styles.buyerList}>
            {finance.deductions.map((deduction) => (
              <article key={deduction.id}>
                <div>
                  <strong>{labelize(deduction.category)}</strong>
                  <span>{formatDate(deduction.incurred_at)}</span>
                </div>
                <small>{formatMoney(deduction.amount_cents)} direct deal deduction</small>
              </article>
            ))}
            {finance.marketing_spend.map((spend) => (
              <article key={spend.id}>
                <div>
                  <strong>{labelize(spend.source)}</strong>
                  <span>{formatDate(spend.spend_month_at)}</span>
                </div>
                <small>
                  {formatMoney(spend.amount_cents)}
                  {spend.campaign ? ` / ${spend.campaign}` : ""}
                </small>
              </article>
            ))}
            {finance.deductions.length === 0 && finance.marketing_spend.length === 0 ? (
              <p>No deductions or marketing spend recorded yet.</p>
            ) : null}
          </div>
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Compensation Rules</h3>
            <span>{finance.compensation_rules.length} rules</span>
          </div>
          <div className={styles.buyerList}>
            {finance.compensation_rules.length === 0 ? <p>No compensation rules yet.</p> : null}
            {finance.compensation_rules.map((rule) => (
              <article key={rule.id}>
                <div>
                  <strong>{rule.name}</strong>
                  <span>{rule.is_active ? "Active" : "Inactive"}</span>
                </div>
                <dl>
                  <div>
                    <dt>Role</dt>
                    <dd>{labelize(rule.role_key)}</dd>
                  </div>
                  <div>
                    <dt>Basis</dt>
                    <dd>{labelize(rule.applies_to)}</dd>
                  </div>
                  <div>
                    <dt>Rate</dt>
                    <dd>{formatPercent(rule.basis_points)}</dd>
                  </div>
                  <div>
                    <dt>Start</dt>
                    <dd>{formatDate(rule.effective_start_at)}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        </article>
      </section>
    </>
  );
}
