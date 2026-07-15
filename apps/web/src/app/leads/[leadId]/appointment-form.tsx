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

function requiredDateTime(formData: FormData, key: string) {
  return new Date(formString(formData, key)).toISOString();
}

function optionalDateTime(formData: FormData, key: string) {
  const value = formString(formData, key);
  return value ? new Date(value).toISOString() : null;
}

export function AppointmentForm({ leadId }: { leadId: string }) {
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
      const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}/appointments`, {
        method: "POST",
        headers: await getHeaders(),
        body: JSON.stringify({
          appointment_type: formString(formData, "appointment_type"),
          status: formString(formData, "status"),
          scheduled_start_at: requiredDateTime(formData, "scheduled_start_at"),
          scheduled_end_at: optionalDateTime(formData, "scheduled_end_at"),
          location_type: formString(formData, "location_type"),
          location: optionalFormString(formData, "location"),
          notes: optionalFormString(formData, "notes"),
        }),
      });

      if (!response.ok) {
        throw new Error("Unable to schedule appointment.");
      }

      form.reset();
      setStatus("saved");
      router.refresh();
    } catch {
      setStatus("error");
    }
  }

  return (
    <form className={styles.appointmentForm} onSubmit={handleSubmit}>
      <div className={styles.taskGrid}>
        <label>
          <span>Type</span>
          <select name="appointment_type" defaultValue="seller_call">
            <option value="seller_call">Seller call</option>
            <option value="walkthrough">Walkthrough</option>
            <option value="offer_review">Offer review</option>
            <option value="follow_up">Follow-up</option>
          </select>
        </label>
        <label>
          <span>Status</span>
          <select name="status" defaultValue="scheduled">
            <option value="scheduled">Scheduled</option>
            <option value="rescheduled">Rescheduled</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
            <option value="no_show">No show</option>
          </select>
        </label>
      </div>
      <div className={styles.taskGrid}>
        <label>
          <span>Start</span>
          <input name="scheduled_start_at" required type="datetime-local" />
        </label>
        <label>
          <span>End</span>
          <input name="scheduled_end_at" type="datetime-local" />
        </label>
      </div>
      <div className={styles.taskGrid}>
        <label>
          <span>Location type</span>
          <select name="location_type" defaultValue="phone">
            <option value="phone">Phone</option>
            <option value="property">Property</option>
            <option value="video">Video</option>
            <option value="office">Office</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label>
          <span>Location</span>
          <input name="location" maxLength={500} placeholder="Phone, address, or meeting link" />
        </label>
      </div>
      <label>
        <span>Notes</span>
        <textarea
          name="notes"
          maxLength={1000}
          placeholder="Access details, seller preferences, inspection priorities, or prep notes."
          rows={4}
        />
      </label>
      <button disabled={status === "saving"} type="submit">
        Schedule appointment
      </button>
      {status !== "idle" ? <p className={styles[status]}>{status}</p> : null}
    </form>
  );
}
