"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import type { LeadDetail } from "../../lib/api";
import styles from "./page.module.css";

type Appointment = LeadDetail["appointments"][number];
type Status = "idle" | "saving" | "saved" | "error";

function formValue(formData: FormData, key: string) {
  return String(formData.get(key) ?? "").trim();
}

export function AppointmentOutcomeForm({
  leadId,
  appointments,
}: {
  leadId: string;
  appointments: Appointment[];
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
  const actionable = appointments.filter((item) =>
    ["scheduled", "rescheduled"].includes(item.status),
  );

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const appointmentId = formValue(data, "appointment_id");
    const outcomeStatus = formValue(data, "status");
    const followUp = formValue(data, "next_follow_up_at");
    setStatus("saving");

    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;
      const response = await fetch(
        `${apiBaseUrl}/api/v1/leads/${leadId}/appointments/${appointmentId}`,
        {
          method: "PATCH",
          headers,
          body: JSON.stringify({
            status: outcomeStatus,
            outcome: formValue(data, "outcome") || null,
            notes: formValue(data, "notes") || null,
            next_follow_up_at: followUp ? new Date(followUp).toISOString() : null,
            reason: `Appointment marked ${outcomeStatus} from the lead workspace.`,
          }),
        },
      );
      if (!response.ok) throw new Error("Unable to update appointment.");
      setStatus("saved");
      router.refresh();
    } catch {
      setStatus("error");
    }
  }

  if (actionable.length === 0) {
    return <p className={styles.emptyState}>No scheduled appointment needs an outcome.</p>;
  }

  return (
    <form className={styles.appointmentForm} onSubmit={handleSubmit}>
      <label>
        <span>Appointment</span>
        <select name="appointment_id" required>
          {actionable.map((appointment) => (
            <option key={appointment.id} value={appointment.id}>
              {new Date(appointment.scheduled_start_at).toLocaleString()} · {appointment.appointment_type}
            </option>
          ))}
        </select>
      </label>
      <div className={styles.taskGrid}>
        <label>
          <span>Outcome status</span>
          <select name="status" defaultValue="completed">
            <option value="completed">Completed</option>
            <option value="no_show">No show</option>
            <option value="cancelled">Cancelled</option>
            <option value="rescheduled">Rescheduled</option>
          </select>
        </label>
        <label>
          <span>Next follow-up</span>
          <input name="next_follow_up_at" type="datetime-local" />
        </label>
      </div>
      <label>
        <span>Outcome</span>
        <textarea
          name="outcome"
          maxLength={1000}
          placeholder="Decision, objections, property findings, and commitments. Required when completed."
          rows={4}
        />
      </label>
      <label>
        <span>Internal notes</span>
        <textarea name="notes" maxLength={1000} rows={3} />
      </label>
      <button disabled={status === "saving"} type="submit">Update appointment</button>
      {status !== "idle" ? <p className={styles[status]}>{status}</p> : null}
    </form>
  );
}
