"use client";

import { useAuth } from "@clerk/nextjs";
import { CheckCircle2, CircleAlert, Copy, Phone, Plus, Save } from "lucide-react";
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
  assigned_team_id: string | null;
  assigned_team_name: string | null;
  ring_strategy: "sequential" | "simultaneous";
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
  voice_forwarding_number: string | null;
  voice_forwarding_enabled: boolean;
};

type VoiceLineTeam = {
  id: string;
  name: string;
  team_type: string;
};

type VoiceReadiness = {
  configured: boolean;
  line_id: string | null;
  line_phone_number: string | null;
  inbound_webhook_url: string;
  outbound_twiml_app_url: string;
  status_callback_url: string;
  recording_callback_url: string;
  checks: Array<{
    key: string;
    label: string;
    required: boolean;
    ready: boolean;
    detail: string;
  }>;
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
  const [teams, setTeams] = useState<VoiceLineTeam[]>([]);
  const [readiness, setReadiness] = useState<VoiceReadiness | null>(null);
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
    const [payload, readinessPayload] = await Promise.all([
      request<{
        items: VoiceLine[];
        users: VoiceLineUser[];
        teams: VoiceLineTeam[];
      }>("/api/v1/voice/lines"),
      request<VoiceReadiness>("/api/v1/voice/readiness"),
    ]);
    setLines(payload.items);
    setUsers(payload.users);
    setTeams(payload.teams);
    setReadiness(readinessPayload);
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
          assigned_team_id: String(data.get("assigned_team_id") ?? "") || null,
          inbound_route: String(data.get("inbound_route") ?? "conversation_owner"),
          ring_strategy: String(data.get("ring_strategy") ?? "simultaneous"),
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
          assigned_team_id: String(data.get("assigned_team_id") ?? "") || null,
          status: String(data.get("status") ?? "active"),
          inbound_route: String(data.get("inbound_route") ?? "conversation_owner"),
          ring_strategy: String(data.get("ring_strategy") ?? "sequential"),
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

  async function saveForwarding(event: FormEvent<HTMLFormElement>, userId: string) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusyId(`user:${userId}`);
    setMessage("");
    setError("");
    try {
      await request(`/api/v1/voice/users/${userId}/forwarding`, {
        method: "PATCH",
        body: JSON.stringify({
          voice_forwarding_number:
            String(data.get("voice_forwarding_number") ?? "").trim() || null,
          voice_forwarding_enabled: data.get("voice_forwarding_enabled") === "on",
        }),
      });
      await load();
      setMessage("Staff call destination updated.");
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "Staff call destination could not be updated.",
      );
    } finally {
      setBusyId("");
    }
  }

  async function copyValue(value: string) {
    setError("");
    try {
      await navigator.clipboard.writeText(value);
      setMessage("Webhook URL copied.");
    } catch {
      setMessage("");
      setError("The browser could not copy that URL.");
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

      {readiness ? (
        <div className={styles.voiceReadiness} data-ready={readiness.configured}>
          <div className={styles.voiceReadinessHeading}>
            <div>
              <strong>{readiness.configured ? "Ready for forwarded-call testing" : "Voice setup incomplete"}</strong>
              <small>{readiness.line_phone_number ?? "No active acquisitions line"}</small>
            </div>
            {readiness.configured ? (
              <CheckCircle2 aria-hidden="true" size={20} />
            ) : (
              <CircleAlert aria-hidden="true" size={20} />
            )}
          </div>
          <div className={styles.voiceChecks}>
            {readiness.checks.map((check) => (
              <div data-ready={check.ready} key={check.key}>
                {check.ready ? (
                  <CheckCircle2 aria-hidden="true" size={15} />
                ) : (
                  <CircleAlert aria-hidden="true" size={15} />
                )}
                <span>
                  <strong>{check.label}{check.required ? "" : " (optional)"}</strong>
                  <small>{check.detail}</small>
                </span>
              </div>
            ))}
          </div>
          <div className={styles.voiceUrls}>
            {[["Number Voice webhook", readiness.inbound_webhook_url]].map(([label, value]) => (
              <div key={label}>
                <span><strong>{label}</strong><code>{value}</code></span>
                <button
                  aria-label={`Copy ${label}`}
                  onClick={() => void copyValue(value)}
                  title={`Copy ${label}`}
                  type="button"
                >
                  <Copy aria-hidden="true" size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className={styles.forwardingSection}>
        <div className={styles.forwardingHeading}>
          <div>
            <span>Call destinations</span>
            <h3>Staff ring settings</h3>
          </div>
          <Phone aria-hidden="true" size={18} />
        </div>
        <div className={styles.forwardingGrid}>
          {users.map((user) => (
            <form
              key={`${user.id}:${user.voice_forwarding_number ?? ""}:${user.voice_forwarding_enabled}`}
              onSubmit={(event) => saveForwarding(event, user.id)}
            >
              <div>
                <strong>{user.display_name}</strong>
                <small>{user.email}</small>
              </div>
              <label>
                <span>Cellphone</span>
                <input
                  defaultValue={user.voice_forwarding_number ?? ""}
                  name="voice_forwarding_number"
                  placeholder="+14045550100"
                  type="tel"
                />
              </label>
              <label className={styles.checkLabel}>
                <input
                  defaultChecked={user.voice_forwarding_enabled}
                  name="voice_forwarding_enabled"
                  type="checkbox"
                />
                <span>Ring cellphone</span>
              </label>
              <button disabled={busyId === `user:${user.id}`} type="submit">
                <Save aria-hidden="true" size={15} />
                Save
              </button>
            </form>
          ))}
        </div>
      </div>

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
              <span>Department team</span>
              <select defaultValue={line.assigned_team_id ?? ""} name="assigned_team_id">
                <option value="">Primary and fallback only</option>
                {teams.map((team) => (
                  <option key={team.id} value={team.id}>{team.name}</option>
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
              <span>Ring strategy</span>
              <select defaultValue={line.ring_strategy} name="ring_strategy">
                <option value="sequential">In order</option>
                <option value="simultaneous">Everyone at once</option>
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
            <span>Department team</span>
            <select defaultValue="" name="assigned_team_id">
              <option value="">Primary and fallback only</option>
              {teams.map((team) => (
                <option key={team.id} value={team.id}>{team.name}</option>
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
            <span>Ring strategy</span>
            <select defaultValue="simultaneous" name="ring_strategy">
              <option value="sequential">In order</option>
              <option value="simultaneous">Everyone at once</option>
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
