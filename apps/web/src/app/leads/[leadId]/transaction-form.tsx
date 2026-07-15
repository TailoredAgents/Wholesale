"use client";

import { useAuth } from "@clerk/nextjs";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import styles from "./page.module.css";

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

export function TransactionForm({ leadId }: { leadId: string }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [status, setStatus] = useState<Status>("idle");
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

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    setStatus("saving");

    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}/transactions`, {
        method: "POST",
        headers: await getHeaders(),
        body: JSON.stringify({
          contract_type: formString(formData, "contract_type"),
          purchase_price_cents: requiredCents(formData, "purchase_price"),
          assignment_fee_cents: optionalCents(formData, "assignment_fee"),
          earnest_money_cents: optionalCents(formData, "earnest_money"),
          title_company: optionalFormString(formData, "title_company"),
          closing_date: optionalDateTime(formData, "closing_date"),
          inspection_period_days: optionalInteger(formData, "inspection_period_days"),
          notes: optionalFormString(formData, "notes"),
        }),
      });

      if (!response.ok) {
        throw new Error("Unable to open transaction.");
      }

      form.reset();
      setStatus("saved");
      router.refresh();
    } catch {
      setStatus("error");
    }
  }

  return (
    <form className={styles.transactionForm} onSubmit={handleSubmit}>
      <div className={styles.taskGrid}>
        <label>
          <span>Contract</span>
          <select name="contract_type" defaultValue="purchase_agreement">
            <option value="purchase_agreement">Purchase agreement</option>
            <option value="assignment_contract">Assignment contract</option>
            <option value="novation">Novation</option>
          </select>
        </label>
        <label>
          <span>Purchase price</span>
          <input name="purchase_price" inputMode="decimal" placeholder="170000" required />
        </label>
      </div>
      <div className={styles.taskGrid}>
        <label>
          <span>Assignment fee</span>
          <input name="assignment_fee" inputMode="decimal" placeholder="25000" />
        </label>
        <label>
          <span>Earnest money</span>
          <input name="earnest_money" inputMode="decimal" placeholder="1000" />
        </label>
      </div>
      <div className={styles.taskGrid}>
        <label>
          <span>Title company</span>
          <input name="title_company" maxLength={255} placeholder="Closing attorney or title" />
        </label>
        <label>
          <span>Closing date</span>
          <input name="closing_date" type="datetime-local" />
        </label>
      </div>
      <label>
        <span>Inspection period</span>
        <input name="inspection_period_days" inputMode="numeric" max={120} min={0} placeholder="7" />
      </label>
      <label>
        <span>Contract notes</span>
        <textarea
          name="notes"
          maxLength={2000}
          placeholder="Seller agreement terms, contingencies, title requirements, and next steps."
          rows={4}
        />
      </label>
      <button disabled={status === "saving"} type="submit">
        Open transaction
      </button>
      {status !== "idle" ? <p className={styles[status]}>{status}</p> : null}
    </form>
  );
}
