"use client";

import { useAuth } from "@clerk/nextjs";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import styles from "./page.module.css";

type Status = "idle" | "saving" | "saved" | "error";

function formString(formData: FormData, key: string) {
  return String(formData.get(key) ?? "").trim();
}

function optionalDateTime(formData: FormData, key: string) {
  const value = formString(formData, key);
  return value ? new Date(value).toISOString() : null;
}

export function LeadActionForm({ leadId }: { leadId: string }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [noteStatus, setNoteStatus] = useState<Status>("idle");
  const [taskStatus, setTaskStatus] = useState<Status>("idle");
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

  async function handleNoteSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    setNoteStatus("saving");

    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}/notes`, {
        method: "POST",
        headers: await getHeaders(),
        body: JSON.stringify({ note: formString(formData, "note") }),
      });

      if (!response.ok) {
        throw new Error("Unable to add note.");
      }

      form.reset();
      setNoteStatus("saved");
      router.refresh();
    } catch {
      setNoteStatus("error");
    }
  }

  async function handleTaskSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    setTaskStatus("saving");

    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}/tasks`, {
        method: "POST",
        headers: await getHeaders(),
        body: JSON.stringify({
          title: formString(formData, "title"),
          priority: formString(formData, "priority") || "normal",
          due_at: optionalDateTime(formData, "due_at"),
        }),
      });

      if (!response.ok) {
        throw new Error("Unable to create task.");
      }

      form.reset();
      setTaskStatus("saved");
      router.refresh();
    } catch {
      setTaskStatus("error");
    }
  }

  return (
    <div className={styles.actionForms}>
      <form className={styles.noteForm} onSubmit={handleNoteSubmit}>
        <label>
          <span>Add note</span>
          <textarea
            name="note"
            placeholder="Call summary, seller objection, repair context, or decision."
            required
            rows={4}
          />
        </label>
        <button disabled={noteStatus === "saving"} type="submit">
          Save note
        </button>
        {noteStatus !== "idle" ? <p className={styles[noteStatus]}>{noteStatus}</p> : null}
      </form>

      <form className={styles.taskForm} onSubmit={handleTaskSubmit}>
        <label>
          <span>Next action</span>
          <input name="title" placeholder="Call seller, schedule walkthrough, send offer" required />
        </label>
        <div className={styles.taskGrid}>
          <label>
            <span>Due</span>
            <input name="due_at" type="datetime-local" />
          </label>
          <label>
            <span>Priority</span>
            <select name="priority" defaultValue="normal">
              <option value="urgent">Urgent</option>
              <option value="high">High</option>
              <option value="normal">Normal</option>
              <option value="low">Low</option>
            </select>
          </label>
        </div>
        <button disabled={taskStatus === "saving"} type="submit">
          Create follow-up
        </button>
        {taskStatus !== "idle" ? <p className={styles[taskStatus]}>{taskStatus}</p> : null}
      </form>
    </div>
  );
}
