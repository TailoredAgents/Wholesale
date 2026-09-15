"use client";

import { useAuth } from "@clerk/nextjs";
import { Bell, Check, Clock3, MessageSquareText } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState, type FormEvent } from "react";

import type { LeadListItem } from "../../lib/api";
import { apiErrorMessage, formatDateTime } from "../os-utils";
import styles from "./leads-workspace.module.css";

function localDateTimeValue(value: Date) {
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 16);
}

function suggestedDate(days: number, months = 0) {
  const value = new Date();
  value.setSeconds(0, 0);
  value.setDate(value.getDate() + days);
  value.setMonth(value.getMonth() + months);
  value.setHours(9, 0, 0, 0);
  return localDateTimeValue(value);
}

export function LeadReminderControl({
  canEdit,
  lead,
}: {
  canEdit: boolean;
  lead: LeadListItem;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );
  const reminder =
    lead.primary_next_action?.action_type === "follow_up"
      ? lead.primary_next_action
      : null;
  const [editing, setEditing] = useState(false);
  const [dueAt, setDueAt] = useState(() =>
    reminder?.due_at
      ? localDateTimeValue(new Date(reminder.due_at))
      : suggestedDate(1),
  );
  const [title, setTitle] = useState(
    reminder?.title ?? `Follow up with ${lead.seller_name}`,
  );
  const [smsNotificationEnabled, setSmsNotificationEnabled] = useState(
    reminder?.sms_notification_enabled ?? false,
  );
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  function beginEditing() {
    setDueAt(
      reminder?.due_at
        ? localDateTimeValue(new Date(reminder.due_at))
        : suggestedDate(1),
    );
    setTitle(reminder?.title ?? `Follow up with ${lead.seller_name}`);
    setSmsNotificationEnabled(reminder?.sms_notification_enabled ?? false);
    setNotice(null);
    setEditing(true);
  }

  async function authHeaders() {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    else headers["X-Dev-User-Email"] = devUserEmail;
    return headers;
  }

  async function saveReminder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/leads/${lead.id}/tasks`, {
        method: "POST",
        headers: await authHeaders(),
        body: JSON.stringify({
          title: title.trim() || `Follow up with ${lead.seller_name}`,
          due_at: new Date(dueAt).toISOString(),
          priority: "normal",
          sms_notification_enabled: smsNotificationEnabled,
        }),
      });
      const body = await response.json().catch(() => null) as { detail?: unknown } | null;
      if (!response.ok) {
        throw new Error(apiErrorMessage(body?.detail, "Unable to save this reminder."));
      }
      setEditing(false);
      setNotice("Reminder saved.");
      router.refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Unable to save this reminder.");
    } finally {
      setBusy(false);
    }
  }

  async function completeReminder() {
    if (!reminder) return;
    setBusy(true);
    setNotice(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/tasks/${reminder.task_id}/complete`,
        {
          method: "PATCH",
          headers: await authHeaders(),
          body: JSON.stringify({
            outcome: "completed",
            completion_notes: "Marked done from the Leads workspace.",
          }),
        },
      );
      const body = await response.json().catch(() => null) as { detail?: unknown } | null;
      if (!response.ok) {
        throw new Error(apiErrorMessage(body?.detail, "Unable to mark this reminder done."));
      }
      setNotice("Reminder marked done.");
      router.refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Unable to mark this reminder done.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.reminderControl}>
      <div className={styles.reminderHeading}>
        <span><Bell aria-hidden="true" size={14} />Reminder</span>
        {!editing && canEdit ? (
          <button disabled={busy} onClick={beginEditing} type="button">
            {reminder ? "Reschedule" : "Set reminder"}
          </button>
        ) : null}
      </div>

      {!editing ? (
        reminder ? (
          <div className={styles.reminderSummary}>
            <div>
              <strong>{reminder.title}</strong>
              <span><Clock3 aria-hidden="true" size={13} />{formatDateTime(reminder.due_at)}</span>
              {reminder.sms_notification_enabled ? (
                <span><MessageSquareText aria-hidden="true" size={13} />SMS notification on</span>
              ) : null}
            </div>
            {canEdit ? (
              <button disabled={busy} onClick={() => void completeReminder()} type="button">
                <Check aria-hidden="true" size={14} />Done
              </button>
            ) : null}
          </div>
        ) : (
          <p className={styles.noReminder}>No reminder set. That is okay until someone chooses one.</p>
        )
      ) : (
        <form className={styles.reminderForm} onSubmit={(event) => void saveReminder(event)}>
          <label>
            <span>When</span>
            <input
              min={localDateTimeValue(new Date())}
              onChange={(event) => setDueAt(event.target.value)}
              required
              type="datetime-local"
              value={dueAt}
            />
          </label>
          <div className={styles.reminderPresets} aria-label="Quick reminder dates">
            <button onClick={() => setDueAt(suggestedDate(1))} type="button">Tomorrow</button>
            <button onClick={() => setDueAt(suggestedDate(7))} type="button">1 week</button>
            <button onClick={() => setDueAt(suggestedDate(0, 1))} type="button">1 month</button>
            <button onClick={() => setDueAt(suggestedDate(0, 6))} type="button">6 months</button>
          </div>
          <label>
            <span>What to remember</span>
            <input
              maxLength={255}
              onChange={(event) => setTitle(event.target.value)}
              required
              type="text"
              value={title}
            />
          </label>
          <label className={styles.reminderSmsOption}>
            <input
              checked={smsNotificationEnabled}
              onChange={(event) => setSmsNotificationEnabled(event.target.checked)}
              type="checkbox"
            />
            <span>
              <strong>Text the assigned user when due</strong>
              <small>Uses their cellphone saved under Settings &gt; Communications.</small>
            </span>
          </label>
          {lead.primary_next_action && !reminder ? (
            <small>This replaces the current next action: {lead.primary_next_action.title}</small>
          ) : null}
          <div className={styles.reminderFormActions}>
            <button disabled={busy} onClick={() => setEditing(false)} type="button">Cancel</button>
            <button disabled={busy} type="submit">{busy ? "Saving..." : "Save reminder"}</button>
          </div>
        </form>
      )}
      {notice ? <p className={styles.reminderNotice} aria-live="polite">{notice}</p> : null}
    </div>
  );
}
