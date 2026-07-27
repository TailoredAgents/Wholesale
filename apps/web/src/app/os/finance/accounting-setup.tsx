"use client";

import { useAuth } from "@clerk/nextjs";
import { BookOpenCheck, CircleAlert, Landmark, Scale, ShieldCheck } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import type { AccountingSetup } from "../../lib/api";
import { StatusBadge } from "../_components/design-system";
import { labelize } from "../os-utils";
import styles from "./accounting-setup.module.css";

type SaveStatus = "idle" | "saving" | "saved" | "error";

export function AccountingSetupPanel({
  setup,
  canEdit,
}: {
  setup: AccountingSetup;
  canEdit: boolean;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [status, setStatus] = useState<SaveStatus>("idle");
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

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("saving");
    const data = new FormData(event.currentTarget);
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    else headers["X-Dev-User-Email"] = devUserEmail;
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/finance/accounting/profile`, {
        method: "PUT",
        headers,
        body: JSON.stringify({
          legal_entity_name: String(data.get("legal_entity_name") ?? ""),
          entity_type: String(data.get("entity_type") ?? ""),
          federal_tax_classification: String(
            data.get("federal_tax_classification") ?? "",
          ),
          accounting_method: String(data.get("accounting_method") ?? ""),
          tax_year_end_month: Number(data.get("tax_year_end_month") ?? 12),
          tax_year_end_day: Number(data.get("tax_year_end_day") ?? 31),
          books_start_date: String(data.get("books_start_date") ?? "") || null,
          home_state: String(data.get("home_state") ?? "GA"),
          owner_compensation_treatment: String(
            data.get("owner_compensation_treatment") ?? "",
          ),
          notes: String(data.get("notes") ?? "") || null,
        }),
      });
      if (!response.ok) throw new Error("Unable to update accounting profile.");
      setStatus("saved");
      router.refresh();
    } catch {
      setStatus("error");
    }
  }

  const groupedAccounts = Object.entries(
    setup.accounts.reduce<Record<string, AccountingSetup["accounts"]>>(
      (groups, account) => {
        (groups[account.account_type] ??= []).push(account);
        return groups;
      },
      {},
    ),
  );

  return (
    <section className={styles.workspace}>
      <header className={styles.header}>
        <div>
          <span>Accounting foundation</span>
          <h2>Books and tax setup</h2>
        </div>
        <StatusBadge tone={setup.profile.status === "ready" ? "success" : "warning"}>
          {setup.readiness_score}% ready
        </StatusBadge>
      </header>

      <div className={styles.summary}>
        <div>
          <Landmark size={16} />
          <span>Policy</span>
          <strong>Version {setup.profile.policy_version}</strong>
        </div>
        <div>
          <BookOpenCheck size={16} />
          <span>Accounts</span>
          <strong>{setup.accounts.length}</strong>
        </div>
        <div>
          <Scale size={16} />
          <span>Tax year</span>
          <strong>{setup.profile.tax_rule_year}</strong>
        </div>
        <div>
          <ShieldCheck size={16} />
          <span>Tax review</span>
          <strong>{labelize(setup.tax_copilot.mode)}</strong>
        </div>
      </div>

      <div className={styles.body}>
        <form className={styles.profile} onSubmit={save}>
          <div className={styles.subheading}>
            <div>
              <span>Company profile</span>
              <h3>Accounting basis</h3>
            </div>
            <StatusBadge tone={setup.readiness_gaps.length ? "warning" : "success"}>
              {setup.readiness_gaps.length
                ? `${setup.readiness_gaps.length} decisions`
                : "Complete"}
            </StatusBadge>
          </div>
          <div className={styles.fields}>
            <label>
              Legal entity name
              <input
                defaultValue={setup.profile.legal_entity_name}
                disabled={!canEdit}
                name="legal_entity_name"
                required
              />
            </label>
            <label>
              Entity type
              <select
                defaultValue={setup.profile.entity_type}
                disabled={!canEdit}
                name="entity_type"
              >
                <option value="undecided">Not confirmed</option>
                <option value="sole_proprietor">Sole proprietor</option>
                <option value="single_member_llc">Single-member LLC</option>
                <option value="multi_member_llc">Multi-member LLC</option>
                <option value="corporation">Corporation</option>
              </select>
            </label>
            <label>
              Federal tax classification
              <select
                defaultValue={setup.profile.federal_tax_classification}
                disabled={!canEdit}
                name="federal_tax_classification"
              >
                <option value="undecided">Not confirmed</option>
                <option value="disregarded_entity">Disregarded entity</option>
                <option value="partnership">Partnership</option>
                <option value="s_corporation">S corporation</option>
                <option value="c_corporation">C corporation</option>
              </select>
            </label>
            <label>
              Accounting method
              <select
                defaultValue={setup.profile.accounting_method}
                disabled={!canEdit}
                name="accounting_method"
              >
                <option value="undecided">Not confirmed</option>
                <option value="cash">Cash</option>
                <option value="accrual">Accrual</option>
              </select>
            </label>
            <label>
              Books start date
              <input
                defaultValue={setup.profile.books_start_date ?? ""}
                disabled={!canEdit}
                name="books_start_date"
                type="date"
              />
            </label>
            <label>
              Owner compensation
              <select
                defaultValue={setup.profile.owner_compensation_treatment}
                disabled={!canEdit}
                name="owner_compensation_treatment"
              >
                <option value="pending">Not confirmed</option>
                <option value="owner_draw">Owner draw</option>
                <option value="payroll">Payroll</option>
                <option value="guaranteed_payment">Guaranteed payment</option>
              </select>
            </label>
            <label>
              Tax year end month
              <input
                defaultValue={setup.profile.tax_year_end_month}
                disabled={!canEdit}
                max={12}
                min={1}
                name="tax_year_end_month"
                type="number"
              />
            </label>
            <label>
              Tax year end day
              <input
                defaultValue={setup.profile.tax_year_end_day}
                disabled={!canEdit}
                max={31}
                min={1}
                name="tax_year_end_day"
                type="number"
              />
            </label>
            <label>
              Home state
              <input
                defaultValue={setup.profile.home_state}
                disabled={!canEdit}
                maxLength={2}
                name="home_state"
              />
            </label>
            <label className={styles.notes}>
              Policy notes
              <textarea
                defaultValue={setup.profile.notes ?? ""}
                disabled={!canEdit}
                name="notes"
                rows={3}
              />
            </label>
          </div>
          {setup.readiness_gaps.length ? (
            <div className={styles.gaps}>
              {setup.readiness_gaps.map((gap) => (
                <span key={gap}>
                  <CircleAlert size={13} />
                  {gap}
                </span>
              ))}
            </div>
          ) : null}
          {canEdit ? (
            <div className={styles.actions}>
              <button disabled={status === "saving"} type="submit">
                {status === "saving" ? "Saving..." : "Save accounting profile"}
              </button>
              <span aria-live="polite">
                {status === "saved"
                  ? "Saved"
                  : status === "error"
                    ? "Unable to save"
                    : ""}
              </span>
            </div>
          ) : null}
        </form>

        <div className={styles.tax}>
          <div className={styles.subheading}>
            <div>
              <span>Tax and deductions</span>
              <h3>Review readiness</h3>
            </div>
            <StatusBadge
              tone={
                setup.tax_copilot.readiness_score >= 80
                  ? "success"
                  : setup.tax_copilot.readiness_score >= 50
                    ? "warning"
                    : "danger"
              }
            >
              {setup.tax_copilot.readiness_score}%
            </StatusBadge>
          </div>
          <dl className={styles.taxMetrics}>
            <div>
              <dt>Source records</dt>
              <dd>{setup.tax_copilot.source_records}</dd>
            </div>
            <div>
              <dt>Missing purpose</dt>
              <dd>{setup.tax_copilot.records_missing_notes}</dd>
            </div>
          </dl>
          <div className={styles.scope}>
            {setup.tax_copilot.review_scope.map((item) => (
              <span key={item}>
                <ShieldCheck size={13} />
                {item}
              </span>
            ))}
          </div>
        </div>
      </div>

      <details className={styles.chart}>
        <summary>Chart of accounts · {setup.accounts.length} active accounts</summary>
        <div className={styles.accountGroups}>
          {groupedAccounts.map(([type, accounts]) => (
            <section key={type}>
              <h3>{labelize(type)}</h3>
              {(accounts ?? []).map((account) => (
                <div key={account.id}>
                  <b>{account.code}</b>
                  <span>
                    <strong>{account.name}</strong>
                    <small>{account.description}</small>
                  </span>
                  {account.deal_tracking ? <em>Deal</em> : null}
                </div>
              ))}
            </section>
          ))}
        </div>
      </details>

      <footer className={styles.policy}>
        {setup.policy_notes.map((note) => (
          <span key={note}>{note}</span>
        ))}
      </footer>
    </section>
  );
}
