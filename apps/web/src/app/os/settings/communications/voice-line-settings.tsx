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
  department_key: "acquisitions" | "dispositions" | "general";
  purpose_key: "seller_conversations" | "buyer_relations" | "company_general";
  assigned_user_id: string | null;
  assigned_user_name: string | null;
  fallback_user_id: string | null;
  fallback_user_name: string | null;
  coverage_timezone: string;
  coverage_start_hour: number;
  coverage_end_hour: number;
  missed_call_action: "fallback_then_voicemail" | "voicemail" | "task_only";
  ownership_complete: boolean;
};

type VoiceLineUser = {
  id: string;
  display_name: string;
  email: string;
};

const hourOptions = Array.from({ length: 25 }, (_, hour) => hour);

function purposeForDepartment(department: string) {
  if (department === "dispositions") return "buyer_relations";
  if (department === "general") return "company_general";
  return "seller_conversations";
}

function labelize(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatHour(hour: number) {
  if (hour === 24) return "Midnight (end of day)";
  if (hour === 0) return "12 AM";
  if (hour === 12) return "12 PM";
  return `${hour > 12 ? hour - 12 : hour} ${hour > 12 ? "PM" : "AM"}`;
}

export function VoiceLineSettings() {
  const { getToken } = useAuth();
  const [lines, setLines] = useState<VoiceLine[]>([]);
  const [users, setUsers] = useState<VoiceLineUser[]>([]);
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
    const payload = await request<{ items: VoiceLine[]; users: VoiceLineUser[] }>(
      "/api/v1/voice/lines",
    );
    setLines(payload.items);
    setUsers(payload.users);
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
    const departmentKey = String(data.get("department_key") ?? "acquisitions");
    setBusyId("new");
    setMessage("");
    setError("");
    try {
      await request("/api/v1/voice/lines", {
        method: "POST",
        body: JSON.stringify({
          phone_number: String(data.get("phone_number") ?? "").trim(),
          label: String(data.get("label") ?? "").trim(),
          department_key: departmentKey,
          purpose_key: purposeForDepartment(departmentKey),
          assigned_user_id: String(data.get("assigned_user_id") ?? "") || null,
          fallback_user_id: String(data.get("fallback_user_id") ?? "") || null,
          inbound_route: String(data.get("inbound_route") ?? "conversation_owner"),
          coverage_timezone: String(data.get("coverage_timezone") ?? "America/New_York"),
          coverage_start_hour: Number(data.get("coverage_start_hour") ?? 9),
          coverage_end_hour: Number(data.get("coverage_end_hour") ?? 20),
          missed_call_action: String(
            data.get("missed_call_action") ?? "fallback_then_voicemail",
          ),
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
    const departmentKey = String(data.get("department_key") ?? "acquisitions");
    setBusyId(lineId);
    setMessage("");
    setError("");
    try {
      await request(`/api/v1/voice/lines/${lineId}`, {
        method: "PATCH",
        body: JSON.stringify({
          label: String(data.get("label") ?? "").trim(),
          department_key: departmentKey,
          purpose_key: purposeForDepartment(departmentKey),
          assigned_user_id: String(data.get("assigned_user_id") ?? "") || null,
          fallback_user_id: String(data.get("fallback_user_id") ?? "") || null,
          status: String(data.get("status") ?? "active"),
          inbound_route: String(data.get("inbound_route") ?? "conversation_owner"),
          coverage_timezone: String(data.get("coverage_timezone") ?? "America/New_York"),
          coverage_start_hour: Number(data.get("coverage_start_hour") ?? 9),
          coverage_end_hour: Number(data.get("coverage_end_hour") ?? 20),
          missed_call_action: String(
            data.get("missed_call_action") ?? "fallback_then_voicemail",
          ),
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
              <div>
                <strong>{line.phone_number}</strong>
                <small>{labelize(line.department_key)} · {labelize(line.purpose_key)}</small>
              </div>
              <span
                className={line.ownership_complete ? styles.lineReady : styles.lineNeedsSetup}
              >
                {line.ownership_complete ? "Ownership ready" : "Needs fallback"}
              </span>
            </div>
            <label>
              <span>Label</span>
              <input defaultValue={line.label} name="label" required />
            </label>
            <label>
              <span>Department</span>
              <select defaultValue={line.department_key} name="department_key">
                <option value="acquisitions">Acquisitions</option>
                <option value="dispositions">Dispositions</option>
                <option value="general">Company general</option>
              </select>
            </label>
            <label>
              <span>Status</span>
              <select defaultValue={line.status} name="status">
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </label>
            <label>
              <span>Primary owner</span>
              <select defaultValue={line.assigned_user_id ?? ""} name="assigned_user_id">
                <option value="">Select primary</option>
                {users.map((user) => (
                  <option key={user.id} value={user.id}>{user.display_name}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Fallback owner</span>
              <select defaultValue={line.fallback_user_id ?? ""} name="fallback_user_id">
                <option value="">Select fallback</option>
                {users.map((user) => (
                  <option key={user.id} value={user.id}>{user.display_name}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Inbound route</span>
              <select defaultValue={line.inbound_route} name="inbound_route">
                <option value="conversation_owner">Conversation owner</option>
                <option value="assigned_user">Primary owner</option>
              </select>
            </label>
            <label>
              <span>Missed-call plan</span>
              <select defaultValue={line.missed_call_action} name="missed_call_action">
                <option value="fallback_then_voicemail">Fallback, then voicemail</option>
                <option value="voicemail">Voicemail</option>
                <option value="task_only">Create follow-up task</option>
              </select>
            </label>
            <label>
              <span>Coverage starts</span>
              <select defaultValue={line.coverage_start_hour} name="coverage_start_hour">
                {hourOptions.slice(0, 24).map((hour) => (
                  <option key={hour} value={hour}>{formatHour(hour)}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Coverage ends</span>
              <select defaultValue={line.coverage_end_hour} name="coverage_end_hour">
                {hourOptions.slice(1).map((hour) => (
                  <option key={hour} value={hour}>{formatHour(hour)}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Coverage timezone</span>
              <select defaultValue={line.coverage_timezone} name="coverage_timezone">
                <option value="America/New_York">Eastern</option>
                <option value="America/Chicago">Central</option>
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
            <span>Department</span>
            <select defaultValue="acquisitions" name="department_key">
              <option value="acquisitions">Acquisitions</option>
              <option value="dispositions">Dispositions</option>
              <option value="general">Company general</option>
            </select>
          </label>
          <label>
            <span>Primary owner</span>
            <select defaultValue="" name="assigned_user_id">
              <option value="">Select primary</option>
              {users.map((user) => (
                <option key={user.id} value={user.id}>{user.display_name}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Fallback owner</span>
            <select defaultValue="" name="fallback_user_id">
              <option value="">Select fallback</option>
              {users.map((user) => (
                <option key={user.id} value={user.id}>{user.display_name}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Inbound route</span>
            <select defaultValue="conversation_owner" name="inbound_route">
              <option value="conversation_owner">Conversation owner</option>
              <option value="assigned_user">Primary owner</option>
            </select>
          </label>
          <label>
            <span>Missed-call plan</span>
            <select defaultValue="fallback_then_voicemail" name="missed_call_action">
              <option value="fallback_then_voicemail">Fallback, then voicemail</option>
              <option value="voicemail">Voicemail</option>
              <option value="task_only">Create follow-up task</option>
            </select>
          </label>
          <label>
            <span>Coverage starts</span>
            <select defaultValue="9" name="coverage_start_hour">
              {hourOptions.slice(0, 24).map((hour) => (
                <option key={hour} value={hour}>{formatHour(hour)}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Coverage ends</span>
            <select defaultValue="20" name="coverage_end_hour">
              {hourOptions.slice(1).map((hour) => (
                <option key={hour} value={hour}>{formatHour(hour)}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Coverage timezone</span>
            <select defaultValue="America/New_York" name="coverage_timezone">
              <option value="America/New_York">Eastern</option>
              <option value="America/Chicago">Central</option>
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
