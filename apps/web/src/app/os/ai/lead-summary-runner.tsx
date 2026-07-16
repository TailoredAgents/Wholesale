"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import type { LeadListItem } from "../../lib/api";
import styles from "../page.module.css";

type Status = "idle" | "saving" | "saved" | "error";

export function LeadSummaryRunner({ leads }: { leads: LeadListItem[] }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState("");
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

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const leadId = String(formData.get("lead_id") ?? "");
    setStatus("saving");
    setMessage("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/ai/lead-intake-summary`, {
        method: "POST",
        headers: await getHeaders(),
        body: JSON.stringify({ lead_id: leadId }),
      });
      const payload = (await response.json()) as { status?: string; error_message?: string };
      if (!response.ok) {
        throw new Error("Unable to run lead summary agent.");
      }
      if (payload.status === "failed") {
        setStatus("error");
        setMessage(payload.error_message ?? "AI run failed.");
      } else {
        setStatus("saved");
        setMessage("Lead summary run logged for review.");
      }
      router.refresh();
    } catch {
      setStatus("error");
      setMessage("Unable to run lead summary agent.");
    }
  }

  return (
    <form className={styles.financeForm} onSubmit={submit}>
      <h3>Lead Intake Summary Agent</h3>
      <label>
        <span>Lead</span>
        <select name="lead_id" required>
          <option value="">Select lead</option>
          {leads.map((lead) => (
            <option key={lead.id} value={lead.id}>
              {lead.seller_name} - {lead.property_address}
            </option>
          ))}
        </select>
      </label>
      <button disabled={status === "saving" || leads.length === 0} type="submit">
        {status === "saving" ? "Running summary..." : "Run OpenAI summary"}
      </button>
      {status !== "idle" ? (
        <p className={styles[status]}>{message || status}</p>
      ) : null}
    </form>
  );
}
