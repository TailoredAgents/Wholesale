"use client";

import { useAuth } from "@clerk/nextjs";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import type { LeadListItem } from "../../lib/api";
import styles from "../page.module.css";

type Status = "idle" | "saving" | "saved" | "error";

function formString(formData: FormData, key: string) {
  return String(formData.get(key) ?? "").trim();
}

function optionalFormString(formData: FormData, key: string) {
  const value = formString(formData, key);
  return value || null;
}

function optionalCents(formData: FormData, key: string) {
  const value = formString(formData, key).replace(/[$,]/g, "");
  if (!value) {
    return null;
  }
  return Math.round(Number(value) * 100);
}

function requiredCents(formData: FormData, key: string) {
  return optionalCents(formData, key) ?? 0;
}

function optionalDateTime(formData: FormData, key: string) {
  const value = formString(formData, key);
  return value ? new Date(value).toISOString() : null;
}

function optionalInteger(formData: FormData, key: string) {
  const value = formString(formData, key);
  return value ? Number(value) : null;
}

export function FinanceForms({ leads }: { leads: LeadListItem[] }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [revenueStatus, setRevenueStatus] = useState<Status>("idle");
  const [deductionStatus, setDeductionStatus] = useState<Status>("idle");
  const [ruleStatus, setRuleStatus] = useState<Status>("idle");
  const [spendStatus, setSpendStatus] = useState<Status>("idle");
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  async function getHeaders() {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    } else {
      headers["X-Dev-User-Email"] = devUserEmail;
    }
    return headers;
  }

  async function submitForm(
    event: FormEvent<HTMLFormElement>,
    endpoint: string,
    body: Record<string, unknown>,
    setStatus: (status: Status) => void,
  ) {
    event.preventDefault();
    const form = event.currentTarget;
    setStatus("saving");

    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/finance/${endpoint}`, {
        method: "POST",
        headers: await getHeaders(),
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        throw new Error("Unable to save finance entry.");
      }

      form.reset();
      setStatus("saved");
      router.refresh();
    } catch {
      setStatus("error");
    }
  }

  return (
    <div className={styles.financeForms}>
      <form
        className={styles.financeForm}
        onSubmit={(event) => {
          const formData = new FormData(event.currentTarget);
          void submitForm(
            event,
            "revenue",
            {
              lead_id: optionalFormString(formData, "lead_id"),
              source: formString(formData, "source"),
              status: formString(formData, "status"),
              amount_cents: requiredCents(formData, "amount"),
              received_at: optionalDateTime(formData, "received_at"),
              notes: optionalFormString(formData, "notes"),
            },
            setRevenueStatus,
          );
        }}
      >
        <h3>Revenue</h3>
        <label>
          <span>Lead</span>
          <select name="lead_id">
            <option value="">No linked lead</option>
            {leads.map((lead) => (
              <option key={lead.id} value={lead.id}>
                {lead.seller_name} / {lead.property_address}
              </option>
            ))}
          </select>
        </label>
        <div className={styles.formGrid}>
          <label>
            <span>Source</span>
            <select name="source" defaultValue="assignment_fee">
              <option value="assignment_fee">Assignment fee</option>
              <option value="double_close">Double close</option>
              <option value="consulting_fee">Consulting fee</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label>
            <span>Status</span>
            <select name="status" defaultValue="collected">
              <option value="collected">Collected</option>
              <option value="pending">Pending</option>
              <option value="void">Void</option>
            </select>
          </label>
        </div>
        <div className={styles.formGrid}>
          <label>
            <span>Amount</span>
            <input name="amount" inputMode="decimal" placeholder="25000" required />
          </label>
          <label>
            <span>Received</span>
            <input name="received_at" type="datetime-local" />
          </label>
        </div>
        <label>
          <span>Notes</span>
          <textarea name="notes" maxLength={2000} rows={3} />
        </label>
        <button disabled={revenueStatus === "saving"} type="submit">
          Record revenue
        </button>
        {revenueStatus !== "idle" ? (
          <p className={styles[revenueStatus]}>{revenueStatus}</p>
        ) : null}
      </form>

      <form
        className={styles.financeForm}
        onSubmit={(event) => {
          const formData = new FormData(event.currentTarget);
          void submitForm(
            event,
            "deductions",
            {
              lead_id: optionalFormString(formData, "lead_id"),
              category: formString(formData, "category"),
              amount_cents: requiredCents(formData, "amount"),
              incurred_at: optionalDateTime(formData, "incurred_at"),
              notes: optionalFormString(formData, "notes"),
            },
            setDeductionStatus,
          );
        }}
      >
        <h3>Deduction</h3>
        <label>
          <span>Lead</span>
          <select name="lead_id">
            <option value="">No linked lead</option>
            {leads.map((lead) => (
              <option key={lead.id} value={lead.id}>
                {lead.seller_name} / {lead.property_address}
              </option>
            ))}
          </select>
        </label>
        <div className={styles.formGrid}>
          <label>
            <span>Category</span>
            <select name="category" defaultValue="title">
              <option value="title">Title</option>
              <option value="attorney">Attorney</option>
              <option value="transaction">Transaction</option>
              <option value="marketing">Marketing</option>
              <option value="seller_credit">Seller credit</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label>
            <span>Amount</span>
            <input name="amount" inputMode="decimal" placeholder="1500" required />
          </label>
        </div>
        <label>
          <span>Incurred</span>
          <input name="incurred_at" type="datetime-local" />
        </label>
        <label>
          <span>Notes</span>
          <textarea name="notes" maxLength={2000} rows={3} />
        </label>
        <button disabled={deductionStatus === "saving"} type="submit">
          Record deduction
        </button>
        {deductionStatus !== "idle" ? (
          <p className={styles[deductionStatus]}>{deductionStatus}</p>
        ) : null}
      </form>

      <form
        className={styles.financeForm}
        onSubmit={(event) => {
          const formData = new FormData(event.currentTarget);
          void submitForm(
            event,
            "compensation-rules",
            {
              name: formString(formData, "name"),
              role_key: formString(formData, "role_key"),
              basis_points: optionalInteger(formData, "basis_points"),
              applies_to: formString(formData, "applies_to"),
              effective_start_at: optionalDateTime(formData, "effective_start_at"),
              effective_end_at: optionalDateTime(formData, "effective_end_at"),
              is_active: true,
              notes: optionalFormString(formData, "notes"),
            },
            setRuleStatus,
          );
        }}
      >
        <h3>Compensation Rule</h3>
        <label>
          <span>Name</span>
          <input name="name" maxLength={255} placeholder="Acquisition rep split" required />
        </label>
        <div className={styles.formGrid}>
          <label>
            <span>Role</span>
            <select name="role_key" defaultValue="acquisition_rep">
              <option value="acquisition_rep">Acquisition rep</option>
              <option value="disposition_rep">Disposition rep</option>
              <option value="transaction_coordinator">Transaction coordinator</option>
              <option value="founder_operator">Founder/operator</option>
              <option value="company">Company</option>
            </select>
          </label>
          <label>
            <span>Basis</span>
            <select name="applies_to" defaultValue="net_revenue">
              <option value="net_revenue">Net revenue</option>
              <option value="gross_revenue">Gross revenue</option>
            </select>
          </label>
        </div>
        <div className={styles.formGrid}>
          <label>
            <span>Basis points</span>
            <input name="basis_points" inputMode="numeric" max={10000} min={0} required />
          </label>
          <label>
            <span>Effective start</span>
            <input name="effective_start_at" type="datetime-local" />
          </label>
        </div>
        <label>
          <span>Effective end</span>
          <input name="effective_end_at" type="datetime-local" />
        </label>
        <label>
          <span>Notes</span>
          <textarea name="notes" maxLength={2000} rows={3} />
        </label>
        <button disabled={ruleStatus === "saving"} type="submit">
          Add rule
        </button>
        {ruleStatus !== "idle" ? <p className={styles[ruleStatus]}>{ruleStatus}</p> : null}
      </form>

      <form
        className={styles.financeForm}
        onSubmit={(event) => {
          const formData = new FormData(event.currentTarget);
          void submitForm(
            event,
            "marketing-spend",
            {
              source: formString(formData, "source"),
              campaign: optionalFormString(formData, "campaign"),
              amount_cents: requiredCents(formData, "amount"),
              spend_month_at: optionalDateTime(formData, "spend_month_at"),
              notes: optionalFormString(formData, "notes"),
            },
            setSpendStatus,
          );
        }}
      >
        <h3>Marketing Spend</h3>
        <div className={styles.formGrid}>
          <label>
            <span>Source</span>
            <input name="source" maxLength={120} placeholder="google_ppc" required />
          </label>
          <label>
            <span>Campaign</span>
            <input name="campaign" maxLength={255} placeholder="atlanta-cash-offer" />
          </label>
        </div>
        <div className={styles.formGrid}>
          <label>
            <span>Amount</span>
            <input name="amount" inputMode="decimal" placeholder="5000" required />
          </label>
          <label>
            <span>Month</span>
            <input name="spend_month_at" type="datetime-local" />
          </label>
        </div>
        <label>
          <span>Notes</span>
          <textarea name="notes" maxLength={2000} rows={3} />
        </label>
        <button disabled={spendStatus === "saving"} type="submit">
          Record spend
        </button>
        {spendStatus !== "idle" ? <p className={styles[spendStatus]}>{spendStatus}</p> : null}
      </form>
    </div>
  );
}
