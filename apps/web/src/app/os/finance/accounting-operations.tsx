"use client";

import { useAuth } from "@clerk/nextjs";
import {
  BadgeCheck,
  CircleDollarSign,
  FileCheck2,
  Link2,
  ReceiptText,
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import type {
  AccountingOperations,
  AccountingSetup,
} from "../../lib/api";
import { StatusBadge } from "../_components/design-system";
import { labelize } from "../os-utils";
import styles from "./accounting-operations.module.css";

function money(cents: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(cents / 100);
}

function cents(value: string) {
  const parsed = Number(value.replace(/[$,]/g, ""));
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : 0;
}

function tone(
  status: string,
): "neutral" | "info" | "success" | "warning" | "danger" {
  if (status === "approved" || status === "ready" || status === "linked") {
    return "success";
  }
  if (status === "draft" || status === "rule_review") return "info";
  if (status === "needs_evidence" || status === "payable") return "warning";
  if (status === "exception" || status === "disputed") return "danger";
  return "neutral";
}

export function AccountingOperationsPanel({
  workspace,
  setup,
  permissions,
}: {
  workspace: AccountingOperations;
  setup: AccountingSetup;
  permissions: {
    manageRules: boolean;
    prepare: boolean;
    approvePayments: boolean;
  };
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () =>
      process.env.NEXT_PUBLIC_DEV_USER_EMAIL ??
      "richardaustindugger@users.noreply.github.com",
    [],
  );
  const expenseAccounts = setup.accounts.filter(
    (account) =>
      account.is_active &&
      ["expense", "cost_of_revenue"].includes(account.account_type),
  );

  async function request(path: string, body: Record<string, unknown>) {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) headers.Authorization = `Bearer ${token}`;
    else headers["X-Dev-User-Email"] = devUserEmail;
    const response = await fetch(`${apiBaseUrl}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const data = (await response.json().catch(() => null)) as {
        detail?: string;
      } | null;
      throw new Error(data?.detail ?? "Accounting request failed.");
    }
  }

  async function action(work: () => Promise<void>, success: string) {
    setBusy(true);
    setMessage("");
    try {
      await work();
      setMessage(success);
      router.refresh();
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Accounting request failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function createObligation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const evidence = String(form.get("evidence") ?? "").trim();
    await action(
      () =>
        request("/api/v1/finance/accounting/obligations", {
          obligation_type: String(form.get("obligation_type") ?? ""),
          counterparty_name: String(form.get("counterparty_name") ?? ""),
          expense_account_key:
            String(form.get("expense_account_key") ?? "") || null,
          amount_cents: cents(String(form.get("amount") ?? "")),
          status: "approved",
          due_at: String(form.get("due_at") ?? "") || null,
          evidence_references: evidence ? [evidence] : [],
          notes: String(form.get("notes") ?? "") || null,
        }),
      "Approved obligation added to the accounting queue.",
    );
    event.currentTarget.reset();
  }

  async function recordPayment(
    type: "obligation" | "commission",
    id: string,
  ) {
    const reference = window.prompt(
      "Enter the check number, transfer ID, or payment reference:",
    );
    if (!reference) return;
    const evidence = window.prompt(
      "Enter the receipt, statement, or payment evidence reference:",
    );
    if (!evidence) return;
    const path =
      type === "commission"
        ? `/api/v1/finance/accounting/commission-payouts/${id}/status`
        : `/api/v1/finance/accounting/obligations/${id}/status`;
    await action(
      () =>
        request(path, {
          status: "paid",
          payment_reference: reference,
          evidence_references: [evidence],
        }),
      "Payment recorded. A settlement draft is now available.",
    );
  }

  return (
    <section className={styles.workspace}>
      <header className={styles.header}>
        <div>
          <span>F6C operational accounting</span>
          <h2>Posting and payment control</h2>
        </div>
        <StatusBadge
          tone={workspace.exception_count ? "warning" : "success"}
        >
          {workspace.exception_count
            ? `${workspace.exception_count} evidence exceptions`
            : "Sources controlled"}
        </StatusBadge>
      </header>

      <div className={styles.metrics}>
        <div>
          <FileCheck2 size={17} />
          <span>Rules awaiting approval</span>
          <strong>{workspace.draft_rule_count}</strong>
        </div>
        <div>
          <ReceiptText size={17} />
          <span>Ready to draft</span>
          <strong>{workspace.ready_item_count}</strong>
        </div>
        <div>
          <Link2 size={17} />
          <span>Linked sources</span>
          <strong>
            {
              workspace.source_items.filter(
                (item) => item.readiness === "linked",
              ).length
            }
          </strong>
        </div>
      </div>

      {workspace.draft_rule_count ? (
        <section className={styles.rules}>
          <div className={styles.sectionHeading}>
            <div>
              <span>Versioned policy</span>
              <h3>Posting rules require owner approval</h3>
            </div>
          </div>
          <div className={styles.ruleGrid}>
            {workspace.rules
              .filter((rule) => rule.status === "draft")
              .map((rule) => (
                <article key={rule.id}>
                  <div>
                    <strong>{rule.name}</strong>
                    <StatusBadge tone="info">Version {rule.version_number}</StatusBadge>
                  </div>
                  <p>{rule.description}</p>
                  <small>
                    {labelize(rule.debit_account_key)} /{" "}
                    {labelize(rule.credit_account_key)}
                  </small>
                  {permissions.manageRules ? (
                    <button
                      disabled={busy}
                      onClick={() =>
                        void action(
                          () =>
                            request(
                              `/api/v1/finance/accounting/posting-rules/${rule.id}/approve`,
                              {},
                            ),
                          `${rule.name} approved.`,
                        )
                      }
                      type="button"
                    >
                      <BadgeCheck size={14} />
                      Approve rule
                    </button>
                  ) : null}
                </article>
              ))}
          </div>
        </section>
      ) : null}

      <section>
        <div className={styles.sectionHeading}>
          <div>
            <span>Source-linked work queue</span>
            <h3>Operational records ready for accounting</h3>
          </div>
          <strong>{workspace.source_items.length} items</strong>
        </div>
        <div className={styles.tableWrap}>
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Amount</th>
                <th>Readiness</th>
                <th>Control detail</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {workspace.source_items.length ? (
                workspace.source_items.map((item) => (
                  <tr
                    key={`${item.source_type}-${item.source_id}-${item.posting_purpose}`}
                  >
                    <td>
                      <strong>{item.label}</strong>
                      <small>
                        {labelize(item.source_type)} /{" "}
                        {labelize(item.posting_purpose)}
                      </small>
                    </td>
                    <td>{money(item.amount_cents)}</td>
                    <td>
                      <StatusBadge tone={tone(item.readiness)}>
                        {labelize(item.readiness)}
                      </StatusBadge>
                    </td>
                    <td>{item.readiness_detail}</td>
                    <td>
                      {item.readiness === "ready" && permissions.prepare ? (
                        <button
                          disabled={busy}
                          onClick={() =>
                            void action(
                              () =>
                                request(
                                  "/api/v1/finance/accounting/operations/draft",
                                  {
                                    source_type: item.source_type,
                                    source_id: item.source_id,
                                    posting_purpose: item.posting_purpose,
                                  },
                                ),
                              "Balanced journal prepared for review.",
                            )
                          }
                          type="button"
                        >
                          Prepare draft
                        </button>
                      ) : item.journal_entry_id ? (
                        <span className={styles.linked}>
                          {labelize(item.journal_status ?? "linked")}
                        </span>
                      ) : item.source_type === "deal_payout" &&
                        item.posting_purpose === "accrued" &&
                        item.status === "approved" &&
                        permissions.approvePayments ? (
                        <button
                          disabled={busy}
                          onClick={() =>
                            void action(
                              () =>
                                request(
                                  `/api/v1/finance/accounting/commission-payouts/${item.source_id}/status`,
                                  { status: "payable" },
                                ),
                              "Commission marked payable.",
                            )
                          }
                          type="button"
                        >
                          Mark payable
                        </button>
                      ) : item.source_type === "deal_payout" &&
                        item.posting_purpose === "accrued" &&
                        item.status === "payable" &&
                        permissions.approvePayments ? (
                        <button
                          disabled={busy}
                          onClick={() =>
                            void recordPayment("commission", item.source_id)
                          }
                          type="button"
                        >
                          Record paid
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5}>No operational sources are waiting.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <details className={styles.obligationComposer}>
        <summary>Add payable, reimbursement, or owner distribution</summary>
        <form onSubmit={(event) => void createObligation(event)}>
          <label>
            <span>Type</span>
            <select name="obligation_type">
              <option value="vendor_payable">Vendor payable</option>
              <option value="contractor_payable">Contractor payable</option>
              <option value="reimbursement">Reimbursement</option>
              <option value="owner_distribution">Owner distribution</option>
            </select>
          </label>
          <label>
            <span>Payee</span>
            <input name="counterparty_name" required />
          </label>
          <label>
            <span>Amount</span>
            <input inputMode="decimal" name="amount" required />
          </label>
          <label>
            <span>Expense account</span>
            <select name="expense_account_key">
              <option value="">Not applicable</option>
              {expenseAccounts.map((account) => (
                <option key={account.id} value={account.system_key}>
                  {account.code} {account.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Due</span>
            <input name="due_at" type="date" />
          </label>
          <label>
            <span>Evidence reference</span>
            <input
              name="evidence"
              placeholder="Invoice, receipt, or approval ID"
              required
            />
          </label>
          <label className={styles.notes}>
            <span>Business purpose</span>
            <textarea name="notes" rows={2} />
          </label>
          <button disabled={busy || !permissions.prepare} type="submit">
            <CircleDollarSign size={15} />
            Add approved obligation
          </button>
        </form>
      </details>

      {workspace.obligations.length ? (
        <section>
          <div className={styles.sectionHeading}>
            <div>
              <span>Payment states</span>
              <h3>Open obligations</h3>
            </div>
          </div>
          <div className={styles.obligations}>
            {workspace.obligations.map((obligation) => (
              <article key={obligation.id}>
                <div>
                  <strong>{obligation.counterparty_name}</strong>
                  <StatusBadge tone={tone(obligation.status)}>
                    {labelize(obligation.status)}
                  </StatusBadge>
                </div>
                <span>
                  {labelize(obligation.obligation_type)} /{" "}
                  {money(obligation.amount_cents)}
                </span>
                {permissions.approvePayments &&
                obligation.status === "approved" ? (
                  <button
                    disabled={busy}
                    onClick={() =>
                      void action(
                        () =>
                          request(
                            `/api/v1/finance/accounting/obligations/${obligation.id}/status`,
                            { status: "payable" },
                          ),
                        "Obligation marked payable.",
                      )
                    }
                    type="button"
                  >
                    Mark payable
                  </button>
                ) : permissions.approvePayments &&
                  obligation.status === "payable" ? (
                  <button
                    disabled={busy}
                    onClick={() =>
                      void recordPayment("obligation", obligation.id)
                    }
                    type="button"
                  >
                    Record paid
                  </button>
                ) : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}
      <p className={styles.message}>{message}</p>
    </section>
  );
}
