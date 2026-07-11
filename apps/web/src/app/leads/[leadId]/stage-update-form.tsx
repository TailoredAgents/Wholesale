"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import styles from "./page.module.css";

const stages = [
  ["new", "New"],
  ["contact_attempt_due", "Contact attempt due"],
  ["attempting_contact", "Attempting contact"],
  ["contacted", "Contacted"],
  ["qualification_in_progress", "Qualification in progress"],
  ["qualified", "Qualified"],
  ["appointment_scheduled", "Appointment scheduled"],
  ["underwriting", "Underwriting"],
  ["offer_pending_approval", "Offer pending approval"],
  ["offer_ready", "Offer ready"],
  ["offer_presented", "Offer presented"],
  ["negotiating", "Negotiating"],
  ["long_term_follow_up", "Long-term follow-up"],
  ["under_contract", "Under contract"],
  ["disqualified", "Disqualified"],
  ["dead", "Dead"],
  ["reopened", "Reopened"],
];

type Status = "idle" | "saving" | "saved" | "error";

export function StageUpdateForm({
  leadId,
  currentStage,
}: {
  leadId: string;
  currentStage: string;
}) {
  const router = useRouter();
  const [status, setStatus] = useState<Status>("idle");
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    setStatus("saving");

    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}/stage`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-Dev-User-Email": devUserEmail,
        },
        body: JSON.stringify({
          stage_key: String(formData.get("stage_key") ?? currentStage),
          reason: String(formData.get("reason") ?? "").trim() || null,
        }),
      });

      if (!response.ok) {
        throw new Error("Unable to update lead stage.");
      }

      setStatus("saved");
      router.refresh();
    } catch {
      setStatus("error");
    }
  }

  return (
    <form className={styles.stageForm} onSubmit={handleSubmit}>
      <label>
        <span>Stage</span>
        <select name="stage_key" defaultValue={currentStage}>
          {stages.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>Reason</span>
        <input name="reason" placeholder="Optional audit note" />
      </label>
      <button disabled={status === "saving"} type="submit">
        Update stage
      </button>
      {status !== "idle" ? <p className={styles[status]}>{status}</p> : null}
    </form>
  );
}
