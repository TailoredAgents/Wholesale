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

function optionalDateTime(formData: FormData, key: string) {
  const value = formString(formData, key);
  return value ? new Date(value).toISOString() : null;
}

export function CommunicationLogForm({ leadId }: { leadId: string }) {
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
      const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}/communications`, {
        method: "POST",
        headers: await getHeaders(),
        body: JSON.stringify({
          direction: formString(formData, "direction"),
          channel: formString(formData, "channel"),
          status: formString(formData, "status"),
          subject: optionalFormString(formData, "subject"),
          body: formString(formData, "body"),
          occurred_at: optionalDateTime(formData, "occurred_at"),
        }),
      });

      if (!response.ok) {
        throw new Error("Unable to log communication.");
      }

      form.reset();
      setStatus("saved");
      router.refresh();
    } catch {
      setStatus("error");
    }
  }

  return (
    <form className={styles.communicationForm} onSubmit={handleSubmit}>
      <div className={styles.taskGrid}>
        <label>
          <span>Direction</span>
          <select name="direction" defaultValue="outbound">
            <option value="outbound">Outbound</option>
            <option value="inbound">Inbound</option>
            <option value="internal">Internal</option>
          </select>
        </label>
        <label>
          <span>Channel</span>
          <select name="channel" defaultValue="call">
            <option value="call">Call</option>
            <option value="sms">SMS</option>
            <option value="email">Email</option>
            <option value="voicemail">Voicemail</option>
            <option value="note">Note</option>
          </select>
        </label>
      </div>
      <div className={styles.taskGrid}>
        <label>
          <span>Status</span>
          <select name="status" defaultValue="logged">
            <option value="logged">Logged</option>
            <option value="draft">Draft</option>
            <option value="sent">Sent</option>
            <option value="received">Received</option>
            <option value="failed">Failed</option>
            <option value="blocked">Blocked</option>
          </select>
        </label>
        <label>
          <span>Occurred</span>
          <input name="occurred_at" type="datetime-local" />
        </label>
      </div>
      <label>
        <span>Subject</span>
        <input name="subject" maxLength={255} placeholder="First contact, callback, objection" />
      </label>
      <label>
        <span>Summary</span>
        <textarea
          name="body"
          placeholder="What happened, what the seller said, and what should happen next."
          required
          rows={4}
        />
      </label>
      <button disabled={status === "saving"} type="submit">
        Log communication
      </button>
      {status !== "idle" ? <p className={styles[status]}>{status}</p> : null}
    </form>
  );
}
