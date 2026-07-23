"use client";

import { useAuth } from "@clerk/nextjs";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

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

export function BuyerForm({ onSaved }: { onSaved?: () => void }) {
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
      const response = await fetch(`${apiBaseUrl}/api/v1/buyers`, {
        method: "POST",
        headers: await getHeaders(),
        body: JSON.stringify({
          name: formString(formData, "name"),
          company_name: optionalFormString(formData, "company_name"),
          email: optionalFormString(formData, "email"),
          phone: optionalFormString(formData, "phone"),
          buyer_type: formString(formData, "buyer_type"),
          status: formString(formData, "status"),
          proof_of_funds_status: formString(formData, "proof_of_funds_status"),
          max_purchase_price_cents: optionalCents(formData, "max_purchase_price"),
          notes: optionalFormString(formData, "notes"),
          criteria: {
            markets: optionalFormString(formData, "markets"),
            property_types: optionalFormString(formData, "property_types"),
            min_price_cents: optionalCents(formData, "min_price"),
            max_price_cents: optionalCents(formData, "max_price"),
            rehab_levels: optionalFormString(formData, "rehab_levels"),
            notes: optionalFormString(formData, "criteria_notes"),
          },
        }),
      });

      if (!response.ok) {
        throw new Error("Unable to create buyer.");
      }

      form.reset();
      setStatus("saved");
      router.refresh();
      onSaved?.();
    } catch {
      setStatus("error");
    }
  }

  return (
    <form className={styles.buyerForm} onSubmit={handleSubmit}>
      <label>
        <span>Buyer name</span>
        <input name="name" maxLength={255} placeholder="Acme Cash Buyer" required />
      </label>
      <label>
        <span>Company</span>
        <input name="company_name" maxLength={255} placeholder="Acme Holdings" />
      </label>
      <div className={styles.formGrid}>
        <label>
          <span>Email</span>
          <input name="email" maxLength={255} placeholder="buyer@example.com" type="email" />
        </label>
        <label>
          <span>Phone</span>
          <input name="phone" maxLength={80} placeholder="404-555-0101" />
        </label>
      </div>
      <div className={styles.formGrid}>
        <label>
          <span>Type</span>
          <select name="buyer_type" defaultValue="cash_buyer">
            <option value="cash_buyer">Cash buyer</option>
            <option value="landlord">Landlord</option>
            <option value="flipper">Flipper</option>
            <option value="builder">Builder</option>
            <option value="hedge_fund">Fund</option>
            <option value="agent">Agent</option>
          </select>
        </label>
        <label>
          <span>Status</span>
          <select name="status" defaultValue="active">
            <option value="active">Active</option>
            <option value="paused">Paused</option>
            <option value="inactive">Inactive</option>
          </select>
        </label>
      </div>
      <div className={styles.formGrid}>
        <label>
          <span>Proof of funds</span>
          <select name="proof_of_funds_status" defaultValue="unknown">
            <option value="unknown">Unknown</option>
            <option value="requested">Requested</option>
            <option value="received">Received</option>
            <option value="expired">Expired</option>
            <option value="rejected">Rejected</option>
          </select>
        </label>
        <label>
          <span>Max purchase</span>
          <input name="max_purchase_price" inputMode="decimal" placeholder="250000" />
        </label>
      </div>
      <label>
        <span>Markets</span>
        <input name="markets" placeholder="Atlanta, Decatur, Marietta" />
      </label>
      <label>
        <span>Property types</span>
        <input name="property_types" placeholder="single_family, duplex, land" />
      </label>
      <div className={styles.formGrid}>
        <label>
          <span>Min price</span>
          <input name="min_price" inputMode="decimal" placeholder="75000" />
        </label>
        <label>
          <span>Max price</span>
          <input name="max_price" inputMode="decimal" placeholder="250000" />
        </label>
      </div>
      <label>
        <span>Rehab levels</span>
        <input name="rehab_levels" placeholder="cosmetic, heavy, teardown" />
      </label>
      <label>
        <span>Criteria notes</span>
        <textarea name="criteria_notes" maxLength={2000} rows={3} />
      </label>
      <label>
        <span>Buyer notes</span>
        <textarea name="notes" maxLength={2000} rows={3} />
      </label>
      <button disabled={status === "saving"} type="submit">
        Add buyer
      </button>
      {status !== "idle" ? <p className={styles[status]}>{status}</p> : null}
    </form>
  );
}
