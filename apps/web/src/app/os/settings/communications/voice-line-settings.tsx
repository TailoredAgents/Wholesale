"use client";

import { useAuth } from "@clerk/nextjs";
import { Phone, Plus, Save } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import styles from "../settings.module.css";

type VoiceLine = {
  id: string;
  phone_number: string;
  label: string;
  status: string;
  is_default: boolean;
  inbound_route: string;
  assigned_user_name: string | null;
};

export function VoiceLineSettings() {
  const { getToken } = useAuth();
  const [lines, setLines] = useState<VoiceLine[]>([]);
  const [busyId, setBusyId] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () =>
      process.env.NEXT_PUBLIC_DEV_USER_EMAIL ??
      "richardaustindugger@users.noreply.github.com",
    [],
  );

  const request = useCallback(
    async <T,>(path: string, init?: RequestInit): Promise<T> => {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;
      const response = await fetch(`${apiBaseUrl}${path}`, {
        ...init,
        headers: { ...headers, ...init?.headers },
        cache: "no-store",
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? `Request failed with status ${response.status}.`);
      }
      return (await response.json()) as T;
    },
    [apiBaseUrl, devUserEmail, getToken],
  );

  const load = useCallback(async () => {
    const payload = await request<{ items: VoiceLine[] }>("/api/v1/voice/lines");
    setLines(payload.items);
  }, [request]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      void load().catch((loadError: unknown) => {
        setError(loadError instanceof Error ? loadError.message : "Voice lines could not load.");
      });
    }, 0);
    return () => window.clearTimeout(handle);
  }, [load]);

  async function createLine(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusyId("new");
    setMessage("");
    setError("");
    try {
      await request("/api/v1/voice/lines", {
        method: "POST",
        body: JSON.stringify({
          phone_number: String(data.get("phone_number") ?? "").trim(),
          label: String(data.get("label") ?? "").trim(),
          inbound_route: String(data.get("inbound_route") ?? "conversation_owner"),
          is_default: data.get("is_default") === "on",
        }),
      });
      form.reset();
      await load();
      setMessage("Voice line added.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Voice line could not be added.");
    } finally {
      setBusyId("");
    }
  }

  async function saveLine(event: FormEvent<HTMLFormElement>, lineId: string) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusyId(lineId);
    setMessage("");
    setError("");
    try {
      await request(`/api/v1/voice/lines/${lineId}`, {
        method: "PATCH",
        body: JSON.stringify({
          label: String(data.get("label") ?? "").trim(),
          status: String(data.get("status") ?? "active"),
          inbound_route: String(data.get("inbound_route") ?? "conversation_owner"),
          is_default: data.get("is_default") === "on",
        }),
      });
      await load();
      setMessage("Voice line updated.");
    } catch (saveError) {
      setError(
        saveError instanceof Error ? saveError.message : "Voice line could not be updated.",
      );
    } finally {
      setBusyId("");
    }
  }

  return (
    <section className={styles.voiceSection}>
      <header>
        <div>
          <span>Twilio Voice</span>
          <h2>Company voice lines</h2>
          <p>Keep phone numbers company-owned and control how inbound calls enter Stonegate.</p>
        </div>
        <Phone aria-hidden="true" size={20} />
      </header>

      {error ? <p className={styles.settingsError} role="alert">{error}</p> : null}
      {message ? <p className={styles.settingsSuccess} role="status">{message}</p> : null}

      <div className={styles.voiceGrid}>
        {lines.map((line) => (
          <form key={line.id} onSubmit={(event) => saveLine(event, line.id)}>
            <div className={styles.voiceLineHeading}>
              <strong>{line.phone_number}</strong>
              <small>{line.assigned_user_name ?? "Unassigned"}</small>
            </div>
            <label>
              <span>Label</span>
              <input defaultValue={line.label} name="label" required />
            </label>
            <label>
              <span>Status</span>
              <select defaultValue={line.status} name="status">
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </label>
            <label>
              <span>Inbound route</span>
              <select defaultValue={line.inbound_route} name="inbound_route">
                <option value="conversation_owner">Conversation owner</option>
                <option value="assigned_user">Assigned user</option>
                <option value="voicemail">Voicemail</option>
              </select>
            </label>
            <label className={styles.checkLabel}>
              <input defaultChecked={line.is_default} name="is_default" type="checkbox" />
              <span>Default company line</span>
            </label>
            <button disabled={busyId === line.id} type="submit">
              <Save aria-hidden="true" size={15} />
              Save
            </button>
          </form>
        ))}

        <form className={styles.newVoiceLine} onSubmit={createLine}>
          <div className={styles.voiceLineHeading}>
            <strong>Add company line</strong>
            <Plus aria-hidden="true" size={17} />
          </div>
          <label>
            <span>Phone number</span>
            <input name="phone_number" placeholder="+16785550100" required type="tel" />
          </label>
          <label>
            <span>Label</span>
            <input name="label" placeholder="Acquisitions main" required />
          </label>
          <label>
            <span>Inbound route</span>
            <select defaultValue="conversation_owner" name="inbound_route">
              <option value="conversation_owner">Conversation owner</option>
              <option value="assigned_user">Assigned user</option>
              <option value="voicemail">Voicemail</option>
            </select>
          </label>
          <label className={styles.checkLabel}>
            <input name="is_default" type="checkbox" />
            <span>Default company line</span>
          </label>
          <button disabled={busyId === "new"} type="submit">
            <Plus aria-hidden="true" size={15} />
            Add line
          </button>
        </form>
      </div>
    </section>
  );
}

