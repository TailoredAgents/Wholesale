"use client";

import { useAuth } from "@clerk/nextjs";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import type { BuyerListItem } from "../../lib/api";
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

export function BuyerOfferForm({
  buyers,
  leadId,
}: {
  buyers: BuyerListItem[];
  leadId: string;
}) {
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
      const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}/buyer-offers`, {
        method: "POST",
        headers: await getHeaders(),
        body: JSON.stringify({
          buyer_id: formString(formData, "buyer_id"),
          amount_cents: requiredCents(formData, "amount"),
          earnest_money_cents: optionalCents(formData, "earnest_money"),
          financing_type: formString(formData, "financing_type"),
          status: formString(formData, "status"),
          proof_of_funds_received: formData.get("proof_of_funds_received") === "on",
          notes: optionalFormString(formData, "notes"),
        }),
      });

      if (!response.ok) {
        throw new Error("Unable to record buyer offer.");
      }

      form.reset();
      setStatus("saved");
      router.refresh();
    } catch {
      setStatus("error");
    }
  }

  return (
    <form className={styles.buyerOfferForm} onSubmit={handleSubmit}>
      <label>
        <span>Buyer</span>
        <select name="buyer_id" required>
          <option value="">Select buyer</option>
          {buyers.map((buyer) => (
            <option key={buyer.id} value={buyer.id}>
              {buyer.name}
              {buyer.company_name ? ` / ${buyer.company_name}` : ""}
            </option>
          ))}
        </select>
      </label>
      <div className={styles.taskGrid}>
        <label>
          <span>Offer amount</span>
          <input name="amount" inputMode="decimal" placeholder="195000" required />
        </label>
        <label>
          <span>Earnest money</span>
          <input name="earnest_money" inputMode="decimal" placeholder="5000" />
        </label>
      </div>
      <div className={styles.taskGrid}>
        <label>
          <span>Financing</span>
          <select name="financing_type" defaultValue="cash">
            <option value="cash">Cash</option>
            <option value="hard_money">Hard money</option>
            <option value="private_money">Private money</option>
            <option value="conventional">Conventional</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label>
          <span>Status</span>
          <select name="status" defaultValue="received">
            <option value="received">Received</option>
            <option value="countered">Countered</option>
            <option value="accepted">Accepted</option>
            <option value="rejected">Rejected</option>
            <option value="withdrawn">Withdrawn</option>
          </select>
        </label>
      </div>
      <label className={styles.checkboxLabel}>
        <input name="proof_of_funds_received" type="checkbox" />
        <span>Proof of funds received</span>
      </label>
      <label>
        <span>Offer notes</span>
        <textarea
          name="notes"
          maxLength={2000}
          placeholder="Contingencies, closing timeline, deposit terms, and buyer conditions."
          rows={4}
        />
      </label>
      <button disabled={status === "saving" || buyers.length === 0} type="submit">
        Record buyer offer
      </button>
      {buyers.length === 0 ? <p className={styles.error}>Add a buyer before recording offers.</p> : null}
      {status !== "idle" ? <p className={styles[status]}>{status}</p> : null}
    </form>
  );
}
