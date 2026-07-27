"use client";

import { useAuth } from "@clerk/nextjs";
import {
  BadgeCheck,
  BookCheck,
  CalendarRange,
  CircleDollarSign,
  FilePlus2,
  LockKeyhole,
  Plus,
  RotateCcw,
  Trash2,
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import type { AccountingLedger, AccountingSetup } from "../../lib/api";
import { StatusBadge } from "../_components/design-system";
import { labelize } from "../os-utils";
import styles from "./accounting-ledger.module.css";

type JournalLineDraft = {
  key: string;
  accountingAccountId: string;
  debit: string;
  credit: string;
  memo: string;
};

function localDate() {
  const now = new Date();
  return [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
}

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

function newLine(key = crypto.randomUUID()): JournalLineDraft {
  return {
    key,
    accountingAccountId: "",
    debit: "",
    credit: "",
    memo: "",
  };
}

function tone(status: string): "neutral" | "info" | "success" | "warning" {
  if (status === "posted" || status === "closed" || status === "locked") {
    return "success";
  }
  if (status === "approved" || status === "review") return "info";
  if (status === "reversed") return "neutral";
  return "warning";
}

export function AccountingLedgerPanel({
  ledger,
  setup,
  permissions,
}: {
  ledger: AccountingLedger;
  setup: AccountingSetup;
  permissions: {
    prepare: boolean;
    approve: boolean;
    post: boolean;
    managePeriods: boolean;
  };
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [lines, setLines] = useState<JournalLineDraft[]>([
    newLine("journal-line-1"),
    newLine("journal-line-2"),
  ]);
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
  const currentPeriod = ledger.periods[0] ?? null;
  const debitTotal = lines.reduce((total, line) => total + cents(line.debit), 0);
  const creditTotal = lines.reduce((total, line) => total + cents(line.credit), 0);

  async function request(path: string, body: Record<string, unknown>) {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
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
    return response;
  }

  async function action(work: () => Promise<unknown>, success: string) {
    setBusy(true);
    setMessage("");
    try {
      await work();
      setMessage(success);
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Accounting request failed.");
    } finally {
      setBusy(false);
    }
  }

  async function prepareJournal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await action(
      () =>
        request("/api/v1/finance/accounting/journals", {
          entry_date: String(form.get("entry_date") ?? ""),
          memo: String(form.get("memo") ?? ""),
          source_type: String(form.get("source_type") ?? "manual"),
          source_id: String(form.get("source_id") ?? "") || null,
          posting_rule_version: 1,
          evidence_references: String(form.get("evidence_references") ?? "")
            .split("\n")
            .map((item) => item.trim())
            .filter(Boolean),
          idempotency_key: `manual-${crypto.randomUUID()}`,
          currency: "USD",
          lines: lines.map((line) => ({
            accounting_account_id: line.accountingAccountId,
            debit_cents: cents(line.debit),
            credit_cents: cents(line.credit),
            memo: line.memo || null,
          })),
        }),
      "Balanced journal prepared for review.",
    );
  }

  function updateLine(key: string, patch: Partial<JournalLineDraft>) {
    setLines((current) =>
      current.map((line) => (line.key === key ? { ...line, ...patch } : line)),
    );
  }

  async function changePeriod(status: string) {
    if (!currentPeriod) return;
    let reason: string | null = null;
    if (currentPeriod.status === "closed" && status === "open") {
      reason = window.prompt("Reason for reopening this closed period:");
      if (!reason) return;
    }
    await action(
      () =>
        request(
          `/api/v1/finance/accounting/periods/${currentPeriod.id}/status`,
          { status, reason },
        ),
      `Accounting period moved to ${labelize(status)}.`,
    );
  }

  async function reverseEntry(entryId: string) {
    const reason = window.prompt("Reason for this reversing journal:");
    if (!reason) return;
    await action(
      () =>
        request(`/api/v1/finance/accounting/journals/${entryId}/reverse`, {
          reversal_date: localDate(),
          reason,
          idempotency_key: `reversal-${crypto.randomUUID()}`,
        }),
      "Linked reversing journal prepared for review.",
    );
  }

  return (
    <section className={styles.workspace}>
      <header className={styles.header}>
        <div>
          <span>Double-entry accounting</span>
          <h2>Accounting ledger</h2>
        </div>
        <StatusBadge
          tone={ledger.summary.out_of_balance_entries ? "warning" : "success"}
        >
          {ledger.summary.out_of_balance_entries
            ? "Balance exception"
            : "Ledger balanced"}
        </StatusBadge>
      </header>

      <div className={styles.metrics}>
        <div>
          <FilePlus2 size={16} />
          <span>Draft</span>
          <strong>{ledger.summary.draft_entries}</strong>
        </div>
        <div>
          <BadgeCheck size={16} />
          <span>Approved</span>
          <strong>{ledger.summary.approved_entries}</strong>
        </div>
        <div>
          <BookCheck size={16} />
          <span>Posted</span>
          <strong>{ledger.summary.posted_entries}</strong>
        </div>
        <div>
          <CircleDollarSign size={16} />
          <span>Posted debits</span>
          <strong>{money(ledger.summary.posted_amount_cents)}</strong>
        </div>
      </div>

      {currentPeriod ? (
        <div className={styles.period}>
          <div>
            <CalendarRange size={16} />
            <span>
              <small>Current period</small>
              <strong>{currentPeriod.period_key}</strong>
            </span>
            <StatusBadge tone={tone(currentPeriod.status)}>
              {labelize(currentPeriod.status)}
            </StatusBadge>
          </div>
          <dl>
            <div>
              <dt>Draft</dt>
              <dd>{currentPeriod.draft_entries}</dd>
            </div>
            <div>
              <dt>Approved</dt>
              <dd>{currentPeriod.approved_entries}</dd>
            </div>
            <div>
              <dt>Posted</dt>
              <dd>{currentPeriod.posted_entries}</dd>
            </div>
          </dl>
          {permissions.managePeriods ? (
            <div className={styles.periodActions}>
              {currentPeriod.status === "open" ? (
                <button disabled={busy} onClick={() => void changePeriod("review")}>
                  Start review
                </button>
              ) : null}
              {currentPeriod.status === "review" ? (
                <>
                  <button disabled={busy} onClick={() => void changePeriod("open")}>
                    Return to open
                  </button>
                  <button disabled={busy} onClick={() => void changePeriod("closed")}>
                    Close period
                  </button>
                </>
              ) : null}
              {currentPeriod.status === "closed" ? (
                <>
                  <button disabled={busy} onClick={() => void changePeriod("open")}>
                    Reopen
                  </button>
                  <button disabled={busy} onClick={() => void changePeriod("locked")}>
                    <LockKeyhole size={13} />
                    Lock
                  </button>
                </>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {permissions.prepare ? (
        <details className={styles.composer}>
          <summary>Prepare manual journal</summary>
          <form onSubmit={(event) => void prepareJournal(event)}>
            <div className={styles.entryFields}>
              <label>
                Entry date
                <input defaultValue={localDate()} name="entry_date" required type="date" />
              </label>
              <label>
                Source type
                <select defaultValue="manual" name="source_type">
                  <option value="manual">Manual</option>
                  <option value="closing_statement">Closing statement</option>
                  <option value="bank_statement">Bank statement</option>
                  <option value="vendor_document">Vendor document</option>
                  <option value="adjusting_entry">Adjusting entry</option>
                </select>
              </label>
              <label>
                Source reference
                <input name="source_id" placeholder="Document or record reference" />
              </label>
              <label className={styles.memo}>
                Entry memo
                <input name="memo" required />
              </label>
              <label className={styles.evidence}>
                Evidence references
                <textarea
                  name="evidence_references"
                  placeholder="One document or record reference per line"
                  rows={2}
                />
              </label>
            </div>
            <div className={styles.lines}>
              <div className={styles.lineHeader}>
                <span>Account</span>
                <span>Debit</span>
                <span>Credit</span>
                <span>Memo</span>
                <span />
              </div>
              {lines.map((line) => (
                <div className={styles.line} key={line.key}>
                  <select
                    aria-label="Accounting account"
                    onChange={(event) =>
                      updateLine(line.key, {
                        accountingAccountId: event.target.value,
                      })
                    }
                    required
                    value={line.accountingAccountId}
                  >
                    <option value="">Select account</option>
                    {setup.accounts.map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.code} · {account.name}
                      </option>
                    ))}
                  </select>
                  <input
                    aria-label="Debit amount"
                    inputMode="decimal"
                    onChange={(event) =>
                      updateLine(line.key, {
                        debit: event.target.value,
                        credit: event.target.value ? "" : line.credit,
                      })
                    }
                    placeholder="0.00"
                    value={line.debit}
                  />
                  <input
                    aria-label="Credit amount"
                    inputMode="decimal"
                    onChange={(event) =>
                      updateLine(line.key, {
                        credit: event.target.value,
                        debit: event.target.value ? "" : line.debit,
                      })
                    }
                    placeholder="0.00"
                    value={line.credit}
                  />
                  <input
                    aria-label="Line memo"
                    onChange={(event) =>
                      updateLine(line.key, { memo: event.target.value })
                    }
                    value={line.memo}
                  />
                  <button
                    aria-label="Remove journal line"
                    disabled={lines.length <= 2}
                    onClick={() =>
                      setLines((current) =>
                        current.filter((item) => item.key !== line.key),
                      )
                    }
                    title="Remove line"
                    type="button"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
            <div className={styles.composerFooter}>
              <button
                className={styles.addLine}
                onClick={() => setLines((current) => [...current, newLine()])}
                type="button"
              >
                <Plus size={14} />
                Add line
              </button>
              <div className={debitTotal === creditTotal ? styles.balanced : styles.unbalanced}>
                <span>Debits {money(debitTotal)}</span>
                <span>Credits {money(creditTotal)}</span>
              </div>
              <button
                className={styles.primary}
                disabled={busy || debitTotal <= 0 || debitTotal !== creditTotal}
                type="submit"
              >
                Prepare journal
              </button>
            </div>
          </form>
        </details>
      ) : null}

      <div className={styles.entries}>
        <div className={styles.entriesHeading}>
          <div>
            <span>Journal history</span>
            <h3>Entries and source evidence</h3>
          </div>
          <strong>{ledger.entries.length} shown</strong>
        </div>
        {ledger.entries.length ? (
          ledger.entries.map((entry) => (
            <details className={styles.entry} key={entry.id}>
              <summary>
                <span>
                  <strong>{entry.entry_number}</strong>
                  <small>{entry.entry_date}</small>
                </span>
                <span>
                  <strong>{entry.memo}</strong>
                  <small>
                    {labelize(entry.source_type)}
                    {entry.source_id ? ` · ${entry.source_id}` : ""}
                  </small>
                </span>
                <b>{money(entry.total_debits_cents)}</b>
                <StatusBadge tone={tone(entry.status)}>
                  {labelize(entry.status)}
                </StatusBadge>
              </summary>
              <div className={styles.entryBody}>
                <table>
                  <thead>
                    <tr>
                      <th>Account</th>
                      <th>Debit</th>
                      <th>Credit</th>
                      <th>Memo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entry.lines.map((line) => (
                      <tr key={line.id}>
                        <td>
                          {line.account_code} · {line.account_name}
                        </td>
                        <td>{line.debit_cents ? money(line.debit_cents) : ""}</td>
                        <td>{line.credit_cents ? money(line.credit_cents) : ""}</td>
                        <td>{line.memo ?? ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className={styles.entryMeta}>
                  <span>
                    Evidence:{" "}
                    {entry.evidence_references.length
                      ? entry.evidence_references.join(" · ")
                      : "None linked"}
                  </span>
                  <span>Rule version {entry.posting_rule_version}</span>
                  {entry.reverses_entry_id ? <span>Reversing journal</span> : null}
                  {entry.reversal_entry_id ? <span>Linked reversal posted</span> : null}
                </div>
                <div className={styles.entryActions}>
                  {permissions.approve && entry.status === "draft" ? (
                    <button
                      disabled={busy}
                      onClick={() =>
                        void action(
                          () =>
                            request(
                              `/api/v1/finance/accounting/journals/${entry.id}/approve`,
                              { notes: "Reviewed in Stonegate Finance." },
                            ),
                          "Journal approved for posting.",
                        )
                      }
                    >
                      <BadgeCheck size={14} />
                      Approve
                    </button>
                  ) : null}
                  {permissions.post && entry.status === "approved" ? (
                    <button
                      disabled={busy}
                      onClick={() =>
                        void action(
                          () =>
                            request(
                              `/api/v1/finance/accounting/journals/${entry.id}/post`,
                              { notes: "Posted from Stonegate Finance." },
                            ),
                          "Journal posted.",
                        )
                      }
                    >
                      <BookCheck size={14} />
                      Post
                    </button>
                  ) : null}
                  {permissions.prepare && entry.status === "posted" ? (
                    <button
                      disabled={busy}
                      onClick={() => void reverseEntry(entry.id)}
                    >
                      <RotateCcw size={14} />
                      Prepare reversal
                    </button>
                  ) : null}
                </div>
              </div>
            </details>
          ))
        ) : (
          <p className={styles.empty}>No journals have been prepared.</p>
        )}
      </div>
      <p className={styles.message} aria-live="polite">
        {message}
      </p>
    </section>
  );
}
