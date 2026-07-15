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

export function UnderwritingForm({ leadId }: { leadId: string }) {
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
      const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}/underwriting`, {
        method: "POST",
        headers: await getHeaders(),
        body: JSON.stringify({
          status: formString(formData, "status"),
          arv_low_cents: optionalCents(formData, "arv_low"),
          arv_high_cents: optionalCents(formData, "arv_high"),
          repair_low_cents: optionalCents(formData, "repair_low"),
          repair_high_cents: optionalCents(formData, "repair_high"),
          max_offer_cents: optionalCents(formData, "max_offer"),
          recommended_offer_cents: optionalCents(formData, "recommended_offer"),
          offer_strategy: optionalFormString(formData, "offer_strategy"),
          notes: optionalFormString(formData, "notes"),
        }),
      });

      if (!response.ok) {
        throw new Error("Unable to save underwriting.");
      }

      form.reset();
      setStatus("saved");
      router.refresh();
    } catch {
      setStatus("error");
    }
  }

  return (
    <form className={styles.underwritingForm} onSubmit={handleSubmit}>
      <div className={styles.taskGrid}>
        <label>
          <span>Status</span>
          <select name="status" defaultValue="needs_review">
            <option value="draft">Draft</option>
            <option value="needs_review">Needs review</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
        </label>
        <label>
          <span>Strategy</span>
          <select name="offer_strategy" defaultValue="cash_offer">
            <option value="cash_offer">Cash offer</option>
            <option value="novations">Novation</option>
            <option value="creative_finance">Creative finance</option>
            <option value="nurture">Nurture</option>
          </select>
        </label>
      </div>
      <div className={styles.taskGrid}>
        <label>
          <span>ARV low</span>
          <input name="arv_low" inputMode="decimal" placeholder="260000" />
        </label>
        <label>
          <span>ARV high</span>
          <input name="arv_high" inputMode="decimal" placeholder="285000" />
        </label>
      </div>
      <div className={styles.taskGrid}>
        <label>
          <span>Repair low</span>
          <input name="repair_low" inputMode="decimal" placeholder="35000" />
        </label>
        <label>
          <span>Repair high</span>
          <input name="repair_high" inputMode="decimal" placeholder="50000" />
        </label>
      </div>
      <div className={styles.taskGrid}>
        <label>
          <span>Max offer</span>
          <input name="max_offer" inputMode="decimal" placeholder="170000" />
        </label>
        <label>
          <span>Recommended offer</span>
          <input name="recommended_offer" inputMode="decimal" placeholder="162500" />
        </label>
      </div>
      <label>
        <span>Notes</span>
        <textarea
          name="notes"
          maxLength={2000}
          placeholder="Comp rationale, repair assumptions, seller net, risks, and approval context."
          rows={4}
        />
      </label>
      <button disabled={status === "saving"} type="submit">
        Save underwriting version
      </button>
      {status !== "idle" ? <p className={styles[status]}>{status}</p> : null}
    </form>
  );
}
