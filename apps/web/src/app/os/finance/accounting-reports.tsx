"use client";

import { useAuth } from "@clerk/nextjs";
import {
  AlertTriangle,
  BadgeCheck,
  Download,
  FileSpreadsheet,
  Landmark,
  Scale,
  TrendingUp,
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import type {
  AccountingReportSection,
  AccountingReports,
} from "../../lib/api";
import { Button, StatusBadge } from "../_components/design-system";
import { labelize } from "../os-utils";
import styles from "./accounting-reports.module.css";

function money(cents: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(cents / 100);
}

function reportRows(section: AccountingReportSection) {
  return (
    <>
      {section.lines.map((line) => (
        <tr key={line.account_id}>
          <td>{line.code}</td>
          <td>{line.name}</td>
          <td>{money(line.ending_balance_cents)}</td>
        </tr>
      ))}
      <tr className={styles.total}>
        <td colSpan={2}>{section.label}</td>
        <td>{money(section.total_cents)}</td>
      </tr>
    </>
  );
}

function closeTone(status: string): "success" | "warning" | "danger" {
  if (status === "pass") return "success";
  if (status === "warning") return "warning";
  return "danger";
}

export function AccountingReportsPanel({
  reports,
}: {
  reports: AccountingReports;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const apiBase = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devEmail = useMemo(
    () =>
      process.env.NEXT_PUBLIC_DEV_USER_EMAIL ??
      "richardaustindugger@users.noreply.github.com",
    [],
  );

  function changePeriod(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const query = new URLSearchParams({
      report_start: String(data.get("report_start")),
      report_end: String(data.get("report_end")),
    });
    router.push(`/os/finance?${query}`);
  }

  async function downloadCpaPackage() {
    setBusy(true);
    setMessage("");
    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = token
        ? { Authorization: `Bearer ${token}` }
        : { "X-Dev-User-Email": devEmail };
      const query = new URLSearchParams({
        start_on: reports.period_start_on,
        end_on: reports.period_end_on,
      });
      const response = await fetch(
        `${apiBase}/api/v1/finance/accounting/reports/cpa-export?${query}`,
        { headers },
      );
      if (!response.ok) throw new Error("The CPA package could not be generated.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = window.document.createElement("a");
      anchor.href = url;
      anchor.download = `stonegate-cpa-${reports.period_start_on}-${reports.period_end_on}.zip`;
      anchor.click();
      URL.revokeObjectURL(url);
      setMessage("CPA package downloaded from posted ledger records.");
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "The CPA package could not be generated.",
      );
    } finally {
      setBusy(false);
    }
  }

  const close = reports.close_readiness;
  const payables = reports.payables.reduce(
    (total, item) => total + item.amount_cents,
    0,
  );

  return (
    <section className={styles.workspace}>
      <header>
        <div>
          <span>F6E financial reporting</span>
          <h2>Statements, close, and CPA handoff</h2>
        </div>
        <StatusBadge tone={close.ready_to_close ? "success" : "warning"}>
          {close.ready_to_close
            ? "Ready to close"
            : `${close.blocking_count} close blockers`}
        </StatusBadge>
      </header>

      <div className={styles.toolbar}>
        <form onSubmit={changePeriod}>
          <label>
            From
            <input
              defaultValue={reports.period_start_on}
              name="report_start"
              required
              type="date"
            />
          </label>
          <label>
            Through
            <input
              defaultValue={reports.period_end_on}
              name="report_end"
              required
              type="date"
            />
          </label>
          <Button icon={<FileSpreadsheet size={14} />} size="small">
            Run reports
          </Button>
        </form>
        <Button
          disabled={busy}
          icon={<Download size={14} />}
          onClick={() => void downloadCpaPackage()}
          size="small"
          type="button"
          variant="secondary"
        >
          Download CPA package
        </Button>
      </div>

      <div className={styles.metrics}>
        <div>
          <TrendingUp size={17} />
          <span>Net income</span>
          <strong>{money(reports.profit_and_loss.net_income_cents)}</strong>
        </div>
        <div>
          <Landmark size={17} />
          <span>Cash change</span>
          <strong>{money(reports.cash_flow.net_change_cents)}</strong>
        </div>
        <div>
          <Scale size={17} />
          <span>Total assets</span>
          <strong>{money(reports.balance_sheet.total_assets_cents)}</strong>
        </div>
        <div>
          <FileSpreadsheet size={17} />
          <span>Open payables</span>
          <strong>{money(payables)}</strong>
        </div>
      </div>

      <div className={styles.statements}>
        <section>
          <div className={styles.heading}>
            <div>
              <span>Income statement</span>
              <h3>Profit and loss</h3>
            </div>
            <strong>{labelize(reports.accounting_method)} basis</strong>
          </div>
          <div className={styles.table}>
            <table>
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Account</th>
                  <th>Period</th>
                </tr>
              </thead>
              <tbody>
                {reportRows(reports.profit_and_loss.revenue)}
                {reportRows(reports.profit_and_loss.cost_of_revenue)}
                {reportRows(reports.profit_and_loss.operating_expenses)}
                <tr className={styles.grandTotal}>
                  <td colSpan={2}>Net income</td>
                  <td>{money(reports.profit_and_loss.net_income_cents)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <div className={styles.heading}>
            <div>
              <span>Financial position</span>
              <h3>Balance sheet</h3>
            </div>
            <StatusBadge tone={reports.balance_sheet.balanced ? "success" : "danger"}>
              {reports.balance_sheet.balanced ? "Balanced" : "Out of balance"}
            </StatusBadge>
          </div>
          <div className={styles.table}>
            <table>
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Account</th>
                  <th>As of period end</th>
                </tr>
              </thead>
              <tbody>
                {reportRows(reports.balance_sheet.assets)}
                {reportRows(reports.balance_sheet.liabilities)}
                {reportRows(reports.balance_sheet.equity)}
                <tr>
                  <td />
                  <td>Current earnings</td>
                  <td>{money(reports.balance_sheet.current_earnings_cents)}</td>
                </tr>
                <tr className={styles.grandTotal}>
                  <td colSpan={2}>Liabilities and equity</td>
                  <td>
                    {money(
                      reports.balance_sheet.total_liabilities_and_equity_cents,
                    )}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <details>
        <summary>
          <Scale size={15} />
          Trial balance
          <StatusBadge tone={reports.trial_balance.balanced ? "success" : "danger"}>
            {reports.trial_balance.balanced ? "Balanced" : "Review required"}
          </StatusBadge>
        </summary>
        <div className={styles.table}>
          <table>
            <thead>
              <tr>
                <th>Code</th>
                <th>Account</th>
                <th>Debit</th>
                <th>Credit</th>
              </tr>
            </thead>
            <tbody>
              {reports.trial_balance.lines.map((line) => (
                <tr key={line.account_id}>
                  <td>{line.code}</td>
                  <td>{line.name}</td>
                  <td>{line.debit_cents ? money(line.debit_cents) : ""}</td>
                  <td>{line.credit_cents ? money(line.credit_cents) : ""}</td>
                </tr>
              ))}
              <tr className={styles.grandTotal}>
                <td colSpan={2}>Totals</td>
                <td>{money(reports.trial_balance.total_debits_cents)}</td>
                <td>{money(reports.trial_balance.total_credits_cents)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>

      <details>
        <summary>
          <FileSpreadsheet size={15} />
          General ledger
          <strong>{reports.general_ledger.length} lines</strong>
        </summary>
        <div className={styles.table}>
          <table className={styles.ledger}>
            <thead>
              <tr>
                <th>Date</th>
                <th>Entry</th>
                <th>Account</th>
                <th>Memo</th>
                <th>Debit</th>
                <th>Credit</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {reports.general_ledger.map((line, index) => (
                <tr key={`${line.journal_entry_id}-${line.account_code}-${index}`}>
                  <td>{line.entry_date}</td>
                  <td>{line.entry_number}</td>
                  <td>
                    {line.account_code} · {line.account_name}
                  </td>
                  <td>{line.memo}</td>
                  <td>{line.debit_cents ? money(line.debit_cents) : ""}</td>
                  <td>{line.credit_cents ? money(line.credit_cents) : ""}</td>
                  <td>{line.evidence_references.length}</td>
                </tr>
              ))}
              {!reports.general_ledger.length ? (
                <tr>
                  <td colSpan={7}>No posted ledger activity in this period.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </details>

      <details>
        <summary>
          <Landmark size={15} />
          Receivables, payables, and payments
          <strong>
            {reports.receivables.length + reports.payables.length} open
          </strong>
        </summary>
        <div className={styles.schedules}>
          <section>
            <div className={styles.heading}>
              <div>
                <span>Expected proceeds</span>
                <h3>Accounts receivable</h3>
              </div>
              <strong>{reports.receivables.length}</strong>
            </div>
            {reports.receivables.map((item) => (
              <div className={styles.scheduleRow} key={item.id}>
                <div>
                  <strong>{labelize(item.source)}</strong>
                  <span>Expected {item.expected_on}</span>
                </div>
                <b>{money(item.amount_cents)}</b>
              </div>
            ))}
            {!reports.receivables.length ? (
              <p className={styles.empty}>No pending receivables.</p>
            ) : null}
          </section>
          <section>
            <div className={styles.heading}>
              <div>
                <span>Authorized obligations</span>
                <h3>Accounts and commissions payable</h3>
              </div>
              <strong>{reports.payables.length}</strong>
            </div>
            {reports.payables.map((item) => (
              <div className={styles.scheduleRow} key={item.id}>
                <div>
                  <strong>{item.counterparty}</strong>
                  <span>
                    {labelize(item.category)}
                    {item.due_on ? ` · due ${item.due_on}` : ""}
                  </span>
                </div>
                <b>{money(item.amount_cents)}</b>
              </div>
            ))}
            {!reports.payables.length ? (
              <p className={styles.empty}>No approved open payables.</p>
            ) : null}
          </section>
          <section>
            <div className={styles.heading}>
              <div>
                <span>Settlement evidence</span>
                <h3>Payment history</h3>
              </div>
              <strong>{reports.payments.length}</strong>
            </div>
            {reports.payments.map((item) => (
              <div className={styles.scheduleRow} key={item.id}>
                <div>
                  <strong>{item.counterparty}</strong>
                  <span>
                    {item.paid_on} · {labelize(item.category)}
                  </span>
                </div>
                <b>{money(item.amount_cents)}</b>
              </div>
            ))}
            {!reports.payments.length ? (
              <p className={styles.empty}>No recorded payments in this period.</p>
            ) : null}
          </section>
          <section>
            <div className={styles.heading}>
              <div>
                <span>Source-linked economics</span>
                <h3>Deal profitability</h3>
              </div>
              <strong>{reports.deal_profitability.length}</strong>
            </div>
            {reports.deal_profitability.map((item) => (
              <div className={styles.scheduleRow} key={item.deal_id}>
                <div>
                  <strong>Deal {item.deal_id.slice(0, 8)}</strong>
                  <span>
                    {money(item.revenue_cents)} revenue · {money(item.cost_cents)} cost
                  </span>
                </div>
                <b>{money(item.profit_cents)}</b>
              </div>
            ))}
            {!reports.deal_profitability.length ? (
              <p className={styles.empty}>No deal-coded journal lines in this period.</p>
            ) : null}
          </section>
        </div>
      </details>

      <section className={styles.close}>
        <div className={styles.heading}>
          <div>
            <span>Month-end control</span>
            <h3>{close.period_key} close readiness</h3>
          </div>
          <strong>{labelize(close.period_status)}</strong>
        </div>
        <div className={styles.checklist}>
          {close.items.map((item) => (
            <div key={item.key}>
              {item.status === "pass" ? (
                <BadgeCheck size={16} />
              ) : (
                <AlertTriangle size={16} />
              )}
              <div>
                <strong>{item.label}</strong>
                <span>{item.detail}</span>
              </div>
              <StatusBadge tone={closeTone(item.status)}>
                {labelize(item.status)}
              </StatusBadge>
            </div>
          ))}
        </div>
      </section>

      <p className={styles.message} aria-live="polite">
        {message}
      </p>
    </section>
  );
}
