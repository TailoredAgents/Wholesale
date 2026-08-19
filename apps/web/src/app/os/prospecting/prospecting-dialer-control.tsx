"use client";

import { useAuth } from "@clerk/nextjs";
import {
  AlertTriangle,
  CheckCircle2,
  CircleStop,
  Gauge,
  PhoneCall,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  UsersRound,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  CampaignManagementOverview,
  ProspectingDialerOperations,
  ProspectingDialerProfile,
  ProspectingScript,
} from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./prospecting.module.css";

type MutationMethod = "POST" | "PUT";
type ProspectingCohort = CampaignManagementOverview["cohorts"][number];

function formatDateTime(value: string | null) {
  if (!value) return "Not reported";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function operationKey(prefix: string, id: string) {
  return `${prefix}-${id}-${Date.now()}-${crypto.randomUUID()}`;
}

function healthLabel(value: string) {
  return value === "healthy" ? "Healthy" : labelize(value);
}

function localDateValue(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

type RequestRunner = <T>(
  path: string,
  method: MutationMethod,
  body: object,
  successMessage: string,
) => Promise<T | null>;

function SwitchControl({
  checked,
  description,
  disabled,
  label,
  onSave,
}: {
  checked: boolean;
  description: string;
  disabled: boolean;
  label: string;
  onSave: (enabled: boolean, reason: string) => Promise<void>;
}) {
  const [enabled, setEnabled] = useState(checked);
  const [reason, setReason] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (reason.trim().length < 3 || enabled === checked) return;
    await onSave(enabled, reason.trim());
    setReason("");
  }

  return (
    <form className={styles.dialerOperationForm} onSubmit={submit}>
      <div className={styles.dialerSwitchRow}>
        <div>
          <strong>{label}</strong>
          <p>{description}</p>
        </div>
        <label className={styles.dialerSwitch}>
          <input
            aria-label={label}
            checked={enabled}
            disabled={disabled}
            onChange={(event) => setEnabled(event.target.checked)}
            type="checkbox"
          />
          <span aria-hidden="true" />
          <b>{enabled ? "On" : "Off"}</b>
        </label>
      </div>
      {enabled !== checked ? (
        <div className={styles.dialerOperationActionRow}>
          <label>
            <span>Reason for change</span>
            <input
              minLength={3}
              onChange={(event) => setReason(event.target.value)}
              placeholder={enabled ? "Why calling is being enabled" : "Why calling is being paused"}
              required
              value={reason}
            />
          </label>
          <button className={styles.primaryButton} disabled={disabled || reason.trim().length < 3} type="submit">
            Save switch
          </button>
        </div>
      ) : null}
    </form>
  );
}

function ProfileEditor({
  candidate,
  disabled,
  lines,
  profile,
  runRequest,
  refresh,
}: {
  candidate: { id: string; display_name: string; email: string; is_active: boolean; calling_enabled: boolean };
  disabled: boolean;
  lines: ProspectingDialerOperations["eligible_lines"];
  profile: ProspectingDialerProfile | null;
  runRequest: RequestRunner;
  refresh: () => Promise<void>;
}) {
  const [status, setStatus] = useState(profile?.status ?? "inactive");
  const [lineId, setLineId] = useState(profile?.voice_line_id ?? "");
  const [dailyDialLimit, setDailyDialLimit] = useState(
    profile?.daily_dial_limit ? String(profile.daily_dial_limit) : "",
  );
  const [dailySpend, setDailySpend] = useState(
    profile?.daily_spend_limit_cents != null
      ? (profile.daily_spend_limit_cents / 100).toFixed(2)
      : "",
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = await runRequest(
      `/api/v1/prospecting/dialer/profiles/${candidate.id}`,
      "PUT",
      {
        status,
        voice_line_id: lineId || null,
        default_line_count: 1,
        max_line_count: 1,
        recording_policy: "company_policy",
        daily_dial_limit: dailyDialLimit ? Number(dailyDialLimit) : null,
        daily_spend_limit_cents: dailySpend
          ? Math.round(Number(dailySpend) * 100)
          : null,
        metadata: { configured_from: "dialer_control" },
      },
      `${candidate.display_name}'s dialer profile was saved.`,
    );
    if (result) await refresh();
  }

  const selectedLine = lines.find((line) => line.id === lineId);
  const profileBlocked = !candidate.is_active || !candidate.calling_enabled;

  return (
    <form className={styles.dialerProfileCard} onSubmit={submit}>
      <header>
        <div>
          <strong>{candidate.display_name}</strong>
          <span>{candidate.email}</span>
        </div>
        <span className={profile?.status === "active" ? styles.statusGood : styles.statusNeutral}>
          {profile ? labelize(profile.status) : "Not configured"}
        </span>
      </header>
      {profileBlocked ? (
        <p className={styles.dialerInlineWarning}>
          This user must be active with outbound calling enabled before their dialer can run.
        </p>
      ) : null}
      <div className={styles.dialerProfileGrid}>
        <label>
          <span>Dedicated outbound line</span>
          <select onChange={(event) => setLineId(event.target.value)} required={status === "active"} value={lineId}>
            <option value="">Select a line</option>
            {lines.map((line) => (
              <option key={line.id} value={line.id}>
                {line.label} · {line.phone_number}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Caller status</span>
          <select onChange={(event) => setStatus(event.target.value as typeof status)} value={status}>
            <option value="inactive">Inactive</option>
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
          </select>
        </label>
        <label>
          <span>Daily dial limit</span>
          <input min={1} onChange={(event) => setDailyDialLimit(event.target.value)} placeholder="No limit" type="number" value={dailyDialLimit} />
        </label>
        <label>
          <span>Daily spend limit</span>
          <input min={0} onChange={(event) => setDailySpend(event.target.value)} placeholder="No limit" step="0.01" type="number" value={dailySpend} />
        </label>
      </div>
      <div className={styles.dialerProfileFooter}>
        <p>
          <ShieldCheck aria-hidden="true" size={15} />
          One live line · Company recording policy
          {selectedLine ? ` · ${selectedLine.max_concurrent_legs} provider leg capacity` : ""}
        </p>
        <button className={styles.primaryButton} disabled={disabled || profileBlocked} type="submit">
          Save caller setup
        </button>
      </div>
    </form>
  );
}

function SessionControl({
  disabled,
  item,
  refresh,
  runRequest,
}: {
  disabled: boolean;
  item: ProspectingDialerOperations["sessions"][number];
  refresh: () => Promise<void>;
  runRequest: RequestRunner;
}) {
  const [stopMode, setStopMode] = useState<"safe_drain" | "cancel_unanswered">("safe_drain");
  const [stopReason, setStopReason] = useState("");
  const [recoveryAction, setRecoveryAction] = useState<"reconcile" | "release_orphan" | "mark_failed">("reconcile");
  const [recoveryReason, setRecoveryReason] = useState("");
  const session = item.session;
  const needsRecovery = item.health_status !== "healthy";

  async function stop(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const prompt = stopMode === "safe_drain"
      ? "Stop after the current connected call? Unanswered calls will not be interrupted."
      : "Cancel unanswered calls now and stop this session? A connected call will be preserved.";
    if (!window.confirm(prompt)) return;
    const result = await runRequest(
      `/api/v1/prospecting/dialer/operations/sessions/${session.id}/stop`,
      "POST",
      {
        mode: stopMode,
        reason: stopReason.trim(),
        idempotency_key: operationKey("manager-stop", session.id),
      },
      `Stop command sent for ${item.caller_name}.`,
    );
    if (result) {
      setStopReason("");
      await refresh();
    }
  }

  async function recover(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!window.confirm(`Run ${labelize(recoveryAction)} for ${item.caller_name}'s session?`)) return;
    const result = await runRequest(
      `/api/v1/prospecting/dialer/operations/sessions/${session.id}/recover`,
      "POST",
      {
        action: recoveryAction,
        reason: recoveryReason.trim(),
        idempotency_key: operationKey("manager-recovery", session.id),
      },
      `Recovery command sent for ${item.caller_name}.`,
    );
    if (result) {
      setRecoveryReason("");
      await refresh();
    }
  }

  return (
    <article className={styles.dialerSessionCard}>
      <header>
        <div>
          <strong>{item.caller_name}</strong>
          <span>{item.campaign_name} · {item.voice_line_label ?? "No line"}</span>
        </div>
        <span className={item.health_status === "healthy" ? styles.statusGood : styles.statusWarning}>
          {healthLabel(item.health_status)}
        </span>
      </header>
      <dl className={styles.dialerSessionFacts}>
        <div><dt>Session</dt><dd>{labelize(session.state)}</dd></div>
        <div><dt>Current leg</dt><dd>{item.current_leg_status ? labelize(item.current_leg_status) : "None"}</dd></div>
        <div><dt>Heartbeat</dt><dd>{formatDateTime(session.heartbeat_at)}</dd></div>
        <div><dt>Line limit</dt><dd>{session.effective_line_count} of 1</dd></div>
      </dl>
      <div className={styles.dialerSessionActions}>
        <form onSubmit={stop}>
          <strong><CircleStop aria-hidden="true" size={16} /> Stop session</strong>
          <label>
            <span>Stop behavior</span>
            <select onChange={(event) => setStopMode(event.target.value as typeof stopMode)} value={stopMode}>
              <option value="safe_drain">Safe drain after current call</option>
              <option value="cancel_unanswered">Cancel unanswered calls</option>
            </select>
          </label>
          <label>
            <span>Reason for stopping</span>
            <input minLength={3} onChange={(event) => setStopReason(event.target.value)} placeholder="Required reason" required value={stopReason} />
          </label>
          <button className={styles.dangerButton} disabled={disabled || stopReason.trim().length < 3} type="submit">Stop safely</button>
        </form>
        {needsRecovery ? (
          <form onSubmit={recover}>
            <strong><RotateCcw aria-hidden="true" size={16} /> Guarded recovery</strong>
            <label>
              <span>Recovery action</span>
              <select onChange={(event) => setRecoveryAction(event.target.value as typeof recoveryAction)} value={recoveryAction}>
                <option value="reconcile">Reconcile provider state</option>
                <option value="release_orphan">Release orphaned work</option>
                <option value="mark_failed">Mark session failed</option>
              </select>
            </label>
            <label>
              <span>Reason for recovery</span>
              <input minLength={3} onChange={(event) => setRecoveryReason(event.target.value)} placeholder="Required recovery reason" required value={recoveryReason} />
            </label>
            <button className={styles.secondaryButton} disabled={disabled || recoveryReason.trim().length < 3} type="submit">Run recovery</button>
          </form>
        ) : null}
      </div>
    </article>
  );
}

function CallingPolicyCreator({
  campaigns,
  disabled,
  onCreated,
  runRequest,
  scripts,
}: {
  campaigns: ProspectingDialerOperations["campaigns"];
  disabled: boolean;
  onCreated: (cohort: ProspectingCohort) => void;
  runRequest: RequestRunner;
  scripts: ProspectingScript[];
}) {
  const approvedScripts = scripts.filter((script) => script.status === "approved");
  const [campaignId, setCampaignId] = useState(campaigns[0]?.id ?? "");
  const [name, setName] = useState("");
  const [scriptId, setScriptId] = useState(approvedScripts[0]?.id ?? "");
  const [startHour, setStartHour] = useState("9");
  const [endHour, setEndHour] = useState("20");
  const [timezone, setTimezone] = useState("America/New_York");
  const [startsOn, setStartsOn] = useState(() => localDateValue());
  const selectedCampaignId = campaigns.some((campaign) => campaign.id === campaignId)
    ? campaignId
    : campaigns[0]?.id ?? "";
  const selectedScriptId = approvedScripts.some((script) => script.id === scriptId)
    ? scriptId
    : approvedScripts[0]?.id ?? "";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedName = name.trim();
    const start = Number(startHour);
    const end = Number(endHour);
    if (!selectedCampaignId || !selectedScriptId || !normalizedName || start === end) return;
    const slug = normalizedName
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 64) || "calling-policy";
    const result = await runRequest<ProspectingCohort>(
      "/api/v1/campaign-management/cohorts",
      "POST",
      {
        campaign_id: selectedCampaignId,
        script_version_id: selectedScriptId,
        name: normalizedName,
        code: `${slug}-${Date.now().toString().slice(-6)}`,
        source_name: "Stonegate native dialer",
        list_type: "outbound prospecting",
        market_label: "Georgia",
        dialer_mode: "one_line_power",
        call_window_start_hour: start,
        call_window_end_hour: end,
        timezone,
        starts_on: startsOn,
        ends_on: null,
        cohort_metadata: { configured_from: "dialer_control" },
      },
      `${normalizedName} calling policy was created.`,
    );
    if (result) {
      onCreated(result);
      setName("");
    }
  }

  return (
    <details className={styles.dialerPolicyCreator}>
      <summary>Create calling hours + script policy</summary>
      <form onSubmit={submit}>
        <p>
          This creates the campaign cohort that controls when a VA may call and which approved script appears in their workbench.
        </p>
        <div className={styles.dialerPolicyGrid}>
          <label>
            <span>Campaign</span>
            <select onChange={(event) => setCampaignId(event.target.value)} required value={selectedCampaignId}>
              {campaigns.map((campaign) => <option key={campaign.id} value={campaign.id}>{campaign.name}</option>)}
            </select>
          </label>
          <label>
            <span>Policy name</span>
            <input onChange={(event) => setName(event.target.value)} placeholder="Georgia weekday calling" required value={name} />
          </label>
          <label>
            <span>Approved caller script</span>
            <select disabled={!approvedScripts.length} onChange={(event) => setScriptId(event.target.value)} required value={selectedScriptId}>
              {!approvedScripts.length ? <option value="">No approved scripts</option> : null}
              {approvedScripts.map((script) => (
                <option key={script.id} value={script.id}>{script.title} · v{script.version_number}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Starts on</span>
            <input onChange={(event) => setStartsOn(event.target.value)} required type="date" value={startsOn} />
          </label>
          <label>
            <span>Earliest call hour</span>
            <input max={23} min={0} onChange={(event) => setStartHour(event.target.value)} required type="number" value={startHour} />
          </label>
          <label>
            <span>Latest call hour</span>
            <input max={24} min={1} onChange={(event) => setEndHour(event.target.value)} required type="number" value={endHour} />
          </label>
          <label>
            <span>Calling timezone</span>
            <select onChange={(event) => setTimezone(event.target.value)} value={timezone}>
              <option value="America/New_York">Eastern</option>
              <option value="America/Chicago">Central</option>
              <option value="America/Denver">Mountain</option>
              <option value="America/Los_Angeles">Pacific</option>
            </select>
          </label>
        </div>
        {Number(startHour) === Number(endHour) ? (
          <p className={styles.dialerInlineWarning}>The start and end hours must be different.</p>
        ) : null}
        {!approvedScripts.length ? (
          <p className={styles.dialerInlineWarning}>
            Approve a caller script in My Calls → Caller scripts before creating this policy.
          </p>
        ) : null}
        <div className={styles.dialerPolicyFooter}>
          <Link href="/os/prospecting?view=my-calls">Review caller scripts</Link>
          <button
            className={styles.primaryButton}
            disabled={disabled || !campaigns.length || !approvedScripts.length || Number(startHour) === Number(endHour)}
            type="submit"
          >
            Create policy
          </button>
        </div>
      </form>
    </details>
  );
}

export function ProspectingDialerControl({
  cohortsAvailable,
  initialCohorts,
  initialData,
  scripts,
}: {
  cohortsAvailable: boolean;
  initialCohorts: ProspectingCohort[];
  initialData: ProspectingDialerOperations;
  scripts: ProspectingScript[];
}) {
  const { getToken } = useAuth();
  const [data, setData] = useState(initialData);
  const [cohorts, setCohorts] = useState(initialCohorts);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [operationsAvailable, setOperationsAvailable] = useState(true);
  const [operationsLastSuccessAt, setOperationsLastSuccessAt] = useState<string | null>(
    new Date().toISOString(),
  );
  const mountedRef = useRef(true);
  const busyRef = useRef(false);
  const refreshSequenceRef = useRef(0);
  const refreshControllerRef = useRef<AbortController | null>(null);
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  const headers = useCallback(async () => {
    const token = await getToken().catch(() => null);
    const result: Record<string, string> = { "Content-Type": "application/json" };
    if (token) result.Authorization = `Bearer ${token}`;
    else result["X-Dev-User-Email"] = devUserEmail;
    return result;
  }, [devUserEmail, getToken]);

  const refresh = useCallback(async () => {
    if (busyRef.current || document.visibilityState === "hidden") return;
    const requestSequence = refreshSequenceRef.current + 1;
    refreshSequenceRef.current = requestSequence;
    refreshControllerRef.current?.abort();
    const controller = new AbortController();
    refreshControllerRef.current = controller;
    const timeout = window.setTimeout(() => {
      controller.abort();
      if (mountedRef.current && requestSequence === refreshSequenceRef.current) {
        setOperationsAvailable(false);
      }
    }, 10_000);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/prospecting/dialer/operations`,
        { headers: await headers(), cache: "no-store", signal: controller.signal },
      );
      if (!response.ok) throw new Error("Dialer health is temporarily unavailable.");
      const payload = (await response.json()) as ProspectingDialerOperations;
      if (mountedRef.current && requestSequence === refreshSequenceRef.current) {
        setData(payload);
        setOperationsAvailable(true);
        setOperationsLastSuccessAt(new Date().toISOString());
      }
    } catch {
      if (mountedRef.current && requestSequence === refreshSequenceRef.current) {
        setOperationsAvailable(false);
      }
    } finally {
      window.clearTimeout(timeout);
      if (refreshControllerRef.current === controller) {
        refreshControllerRef.current = null;
      }
    }
  }, [apiBaseUrl, headers]);

  useEffect(() => {
    mountedRef.current = true;
    const interval = window.setInterval(() => void refresh(), 15_000);
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      mountedRef.current = false;
      refreshSequenceRef.current += 1;
      refreshControllerRef.current?.abort();
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [refresh]);

  const runRequest = useCallback<RequestRunner>(async (path, method, body, successMessage) => {
    setBusy(true);
    busyRef.current = true;
    setMessage("");
    setError("");
    try {
      const response = await fetch(`${apiBaseUrl}${path}`, {
        method,
        headers: await headers(),
        body: JSON.stringify(body),
      });
      const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
      if (!response.ok) throw new Error(payload?.detail ?? "The dialer change could not be saved.");
      setMessage(successMessage);
      return payload as never;
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The dialer change could not be saved.");
      return null;
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }, [apiBaseUrl, headers]);

  const profileByUserId = useMemo(
    () => new Map(data.profiles.map((profile) => [profile.user_id, profile])),
    [data.profiles],
  );
  const candidates = useMemo(() => {
    if (data.callers?.length) return data.callers;
    return data.profiles.map((profile) => ({
      id: profile.user_id,
      display_name: profile.user_name,
      email: profile.user_email,
      is_active: profile.user_is_active,
      calling_enabled: profile.user_calling_enabled,
    }));
  }, [data.callers, data.profiles]);
  const activeCampaigns = data.campaigns.filter((campaign) => campaign.enabled).length;
  const scriptById = useMemo(
    () => new Map(scripts.map((script) => [script.id, script])),
    [scripts],
  );

  return (
    <div className={styles.dialerOperationsWorkspace}>
      {message ? <p aria-live="polite" className={styles.notice}>{message}</p> : null}
      {error ? <p aria-live="assertive" className={styles.error}>{error}</p> : null}

      <section className={styles.dialerOperationsHero}>
        <div>
          <span>Activation state</span>
          <h2>{data.feature_enabled && data.company_enabled ? "Native dialer is live" : "Native dialer is paused"}</h2>
          <p>
            Deployment access, the company switch, campaign permission, caller setup, and a dedicated line must all be ready before a VA can dial.
          </p>
        </div>
        <button className={styles.secondaryButton} disabled={busy} onClick={() => void refresh()} type="button">
          <RefreshCw aria-hidden="true" size={16} /> Refresh health
        </button>
      </section>

      {!operationsAvailable ? (
        <p className={styles.dialerInlineWarning} role="status">
          Live dialer health is temporarily unavailable. Values below are the last confirmed
          snapshot{operationsLastSuccessAt ? ` from ${formatDateTime(operationsLastSuccessAt)}` : ""}.
        </p>
      ) : null}

      <section aria-label="Dialer health" className={styles.dialerHealthGrid}>
        <div><Gauge aria-hidden="true" size={18} /><span>Worker</span><strong>{labelize(data.health.worker_status)}</strong><small>{formatDateTime(data.health.worker_heartbeat_at)}</small></div>
        <div><PhoneCall aria-hidden="true" size={18} /><span>Live sessions</span><strong>{data.health.active_session_count}</strong><small>{data.health.active_leg_count} active legs</small></div>
        <div><AlertTriangle aria-hidden="true" size={18} /><span>Needs attention</span><strong>{data.health.stale_session_count + data.health.reconnecting_session_count}</strong><small>{data.health.open_recovery_failure_count} recovery failures</small></div>
        <div><UsersRound aria-hidden="true" size={18} /><span>Callbacks</span><strong>{data.health.callback_waiting_count}</strong><small>{data.health.missed_callback_task_count} missed-call tasks</small></div>
      </section>

      <section className={styles.dialerOperationsSection}>
        <header>
          <div><span>Company controls</span><h2>Calling activation</h2></div>
          <span className={data.feature_enabled ? styles.statusGood : styles.statusWarning}>
            Deployment {data.feature_enabled ? "enabled" : "disabled"}
          </span>
        </header>
        {!data.feature_enabled ? (
          <p className={styles.dialerInlineWarning}>
            The deployment feature flag is off. The company switch below is preserved, but calling cannot start until the deployment is enabled.
          </p>
        ) : null}
        <SwitchControl
          checked={data.company_enabled}
          description="Master control for all Stonegate native outbound calling. Existing calls are not silently discarded."
          disabled={busy}
          key={`company:${data.company_enabled}`}
          label="Company native dialer"
          onSave={async (enabled, reason) => {
            const result = await runRequest(
              "/api/v1/prospecting/dialer/switches/company",
              "PUT",
              { enabled, reason },
              `Company dialer ${enabled ? "enabled" : "paused"}.`,
            );
            if (result) await refresh();
          }}
        />
        <dl className={styles.dialerCaps}>
          <div><dt>Configured cap</dt><dd>{data.configured_line_cap}</dd></div>
          <div><dt>Built cap</dt><dd>{data.implemented_line_cap}</dd></div>
          <div><dt>Effective now</dt><dd>{data.effective_line_cap}</dd></div>
          <div><dt>Safety policy</dt><dd>One line</dd></div>
        </dl>
      </section>

      <section className={styles.dialerOperationsSection}>
        <header>
          <div><span>Campaign controls</span><h2>Approved calling campaigns</h2></div>
          <span className={styles.statusNeutral}>{activeCampaigns} of {data.campaigns.length} enabled</span>
        </header>
        <div className={styles.dialerCampaignGrid}>
          {data.campaigns.map((campaign) => (
            <SwitchControl
              checked={campaign.enabled}
              description={`${labelize(campaign.status)} campaign · enforced at one line for D8`}
              disabled={busy}
              key={`${campaign.id}:${campaign.enabled}`}
              label={campaign.name}
              onSave={async (enabled, reason) => {
                const result = await runRequest(
                  `/api/v1/prospecting/dialer/switches/campaigns/${campaign.id}`,
                  "PUT",
                  { enabled, reason },
                  `${campaign.name} ${enabled ? "enabled" : "paused"}.`,
                );
                if (result) await refresh();
              }}
            />
          ))}
          {!data.campaigns.length ? <p className={styles.dialerEmptyState}>No prospecting campaigns are available.</p> : null}
        </div>
      </section>

      <section className={styles.dialerOperationsSection}>
        <header>
          <div><span>Operating policy</span><h2>Calling hours and scripts</h2></div>
          <Link className={styles.dialerTextLink} href="/os/prospecting?view=campaigns">Open campaign workspace</Link>
        </header>
        <p className={styles.dialerSectionDescription}>
          Calling policies are campaign cohorts. Each one binds an approved script to a local calling window before records are assigned to a VA.
        </p>
        <div className={styles.dialerPolicyList}>
          {data.campaigns.map((campaign) => {
            const campaignCohorts = cohorts.filter((cohort) => cohort.campaign_id === campaign.id);
            return (
              <article key={campaign.id}>
                <header><strong>{campaign.name}</strong><span>{campaignCohorts.length} policies</span></header>
                {campaignCohorts.length ? (
                  <div>
                    {campaignCohorts.map((cohort) => {
                      const script = cohort.script_version_id ? scriptById.get(cohort.script_version_id) : null;
                      return (
                        <dl key={cohort.id}>
                          <div><dt>Policy</dt><dd>{cohort.name}</dd></div>
                          <div><dt>Hours</dt><dd>{cohort.call_window_start_hour}:00–{cohort.call_window_end_hour}:00</dd></div>
                          <div><dt>Timezone</dt><dd>{cohort.timezone.replace("America/", "")}</dd></div>
                          <div><dt>Script</dt><dd>{script ? `${script.title} · v${script.version_number}` : "No approved script bound"}</dd></div>
                        </dl>
                      );
                    })}
                  </div>
                ) : <p>No calling-hours policy has been created for this campaign.</p>}
              </article>
            );
          })}
        </div>
        <CallingPolicyCreator
          campaigns={data.campaigns}
          disabled={busy || !cohortsAvailable}
          onCreated={(cohort) => setCohorts((current) => [...current, cohort])}
          runRequest={runRequest}
          scripts={scripts}
        />
        {!cohortsAvailable ? (
          <p className={styles.dialerInlineWarning} role="status">
            Calling policies could not be loaded, so policy creation is paused to prevent duplicates.
          </p>
        ) : null}
      </section>

      <section className={styles.dialerOperationsSection}>
        <header>
          <div><span>Caller setup</span><h2>VA dialer profiles</h2></div>
          <span className={styles.statusNeutral}>{data.profiles.filter((profile) => profile.status === "active").length} active</span>
        </header>
        <p className={styles.dialerSectionDescription}>
          Every caller gets a dedicated Stonegate line, company recording policy, and a hard one-line limit. Daily caps are optional safeguards.
        </p>
        <div className={styles.dialerProfileList}>
          {candidates.map((candidate) => (
            <ProfileEditor
              candidate={candidate}
              disabled={busy}
              key={`${candidate.id}:${profileByUserId.get(candidate.id)?.status ?? "new"}:${profileByUserId.get(candidate.id)?.voice_line_id ?? "none"}:${profileByUserId.get(candidate.id)?.daily_dial_limit ?? "none"}:${profileByUserId.get(candidate.id)?.daily_spend_limit_cents ?? "none"}`}
              lines={data.eligible_lines}
              profile={profileByUserId.get(candidate.id) ?? null}
              refresh={refresh}
              runRequest={runRequest}
            />
          ))}
          {!candidates.length ? (
            <p className={styles.dialerEmptyState}>
              No eligible callers are available. Give a user outbound-calling access, then refresh this view.
            </p>
          ) : null}
        </div>
      </section>

      <section className={styles.dialerOperationsSection}>
        <header>
          <div><span>Live operations</span><h2>Sessions and recovery</h2></div>
          <span className={data.health.stale_session_count ? styles.statusWarning : styles.statusGood}>
            {data.health.stale_session_count ? `${data.health.stale_session_count} stale` : "No stale sessions"}
          </span>
        </header>
        <div className={styles.dialerSessionList}>
          {data.sessions.map((item) => (
            <SessionControl disabled={busy} item={item} key={item.session.id} refresh={refresh} runRequest={runRequest} />
          ))}
          {!data.sessions.length ? <p className={styles.dialerEmptyState}>No active dialer sessions.</p> : null}
        </div>
      </section>

      <section className={styles.dialerOperationsSection}>
        <header>
          <div><span>Audit trail</span><h2>Recent operational errors</h2></div>
          <span className={data.recent_errors.length ? styles.statusWarning : styles.statusGood}>
            {data.recent_errors.length ? `${data.recent_errors.length} recent` : "Clear"}
          </span>
        </header>
        <div className={styles.dialerErrorList}>
          {data.recent_errors.map((item, index) => (
            <article key={`${item.occurred_at}:${item.code}:${index}`}>
              <AlertTriangle aria-hidden="true" size={17} />
              <div><strong>{labelize(item.code)}</strong><p>{item.message}</p></div>
              <span>{formatDateTime(item.occurred_at)}{item.recoverable ? " · Recoverable" : ""}</span>
            </article>
          ))}
          {!data.recent_errors.length ? (
            <p className={styles.dialerEmptyState}><CheckCircle2 aria-hidden="true" size={17} /> No recent dialer errors.</p>
          ) : null}
        </div>
      </section>
    </div>
  );
}
