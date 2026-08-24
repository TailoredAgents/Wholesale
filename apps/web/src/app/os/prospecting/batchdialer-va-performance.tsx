"use client";

import { useAuth } from "@clerk/nextjs";
import {
  Activity,
  AlertTriangle,
  CalendarCheck2,
  Check,
  Clock3,
  Headphones,
  Link2,
  RefreshCw,
  ShieldCheck,
  UserCheck,
  UsersRound,
} from "lucide-react";
import {
  type CSSProperties,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type {
  BatchDialerAgentMapping,
  BatchDialerAgentMappings,
  BatchDialerCampaignMappings,
  BatchDialerVaCoachReport,
  BatchDialerVaPerformance,
  BatchDialerVaPerformanceAgent,
  BatchDialerVaPerformanceMetrics,
} from "../../lib/api";
import styles from "./batchdialer-va-performance.module.css";
import { BatchDialerCampaignMappingsPanel } from "./batchdialer-campaign-mappings";

type RangeKey = "today" | "7" | "30";
type NullableMetricKey = Exclude<
  keyof BatchDialerVaPerformanceMetrics,
  "first_call_at" | "last_call_at"
>;

const numberFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
const integerFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

const scorecardColumns: Array<{
  key: NullableMetricKey;
  label: string;
  format?: "duration" | "minutes" | "rate";
}> = [
  { key: "calls", label: "Calls" },
  { key: "unique_contacts", label: "Unique contacts" },
  { key: "identified_contact_coverage_basis_points", label: "Contact ID coverage", format: "rate" },
  { key: "human_contacts", label: "Human contacts" },
  { key: "human_contact_rate_basis_points", label: "Human rate", format: "rate" },
  { key: "recorded_call_seconds", label: "Recorded duration", format: "duration" },
  { key: "recorded_duration_coverage_basis_points", label: "Duration coverage", format: "rate" },
  { key: "inferred_calling_minutes", label: "Observed span", format: "minutes" },
  { key: "qualified_candidates", label: "Candidates" },
  { key: "evidence_accepted_candidates", label: "Evidence accepted" },
  { key: "evidence_acceptance_rate_basis_points", label: "Acceptance rate", format: "rate" },
  { key: "verified_handoffs", label: "New handoffs" },
  { key: "qualification_false_positives", label: "False positives" },
  { key: "appointments_set", label: "Appts set" },
  { key: "appointments_held", label: "Appts held" },
  { key: "signed_contracts", label: "Contracts" },
  { key: "closed_transactions", label: "Closed" },
];

function formatCount(value: number | null) {
  return value === null ? "Unavailable" : integerFormatter.format(value);
}

function formatDuration(value: number | null) {
  if (value === null) return "Unavailable";
  const seconds = Math.max(0, Math.round(value));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m ${remainder}s`;
  return `${remainder}s`;
}

function formatMinutes(value: number | null) {
  if (value === null) return "Unavailable";
  return value < 60
    ? `${numberFormatter.format(value)} min`
    : `${numberFormatter.format(value / 60)} hr`;
}

function formatRate(value: number | null) {
  return value === null ? "Unavailable" : `${numberFormatter.format(value / 100)}%`;
}

function formatMetric(
  metrics: BatchDialerVaPerformanceMetrics,
  key: NullableMetricKey,
  format?: "duration" | "minutes" | "rate",
) {
  const value = metrics[key];
  if (format === "duration") return formatDuration(value);
  if (format === "minutes") return formatMinutes(value);
  if (format === "rate") return formatRate(value);
  return formatCount(value);
}

function datePartsInTimeZone(date: Date, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone,
  }).formatToParts(date);
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${value.year}-${value.month}-${value.day}`;
}

function shiftIsoDate(value: string, days: number) {
  const [year, month, day] = value.split("-").map(Number);
  const shifted = new Date(Date.UTC(year, month - 1, day + days));
  return shifted.toISOString().slice(0, 10);
}

function rangeDates(range: RangeKey, timeZone: string) {
  const dateTo = datePartsInTimeZone(new Date(), timeZone);
  const dayCount = range === "today" ? 1 : Number(range);
  return { dateFrom: shiftIsoDate(dateTo, -(dayCount - 1)), dateTo };
}

function inferRange(data: BatchDialerVaPerformance | null): RangeKey {
  if (!data) return "7";
  const start = new Date(`${data.date_from}T00:00:00Z`).getTime();
  const end = new Date(`${data.date_to}T00:00:00Z`).getTime();
  const days = Math.round((end - start) / 86_400_000) + 1;
  if (days === 1) return "today";
  if (days === 30) return "30";
  return "7";
}

function formatLocalTimestamp(value: string | null, timeZone: string) {
  if (!value) return "Unavailable";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Unavailable";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone,
    timeZoneName: "short",
  }).format(parsed);
}

function MetricCard({
  detail,
  icon,
  label,
  value,
}: {
  detail: string;
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className={styles.metricCard}>
      <span className={styles.metricIcon}>{icon}</span>
      <div>
        <span>{label}</span>
        <strong className={value === "Unavailable" ? styles.unavailable : undefined}>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function OutcomeMetric({
  format = "count",
  label,
  value,
}: {
  format?: "count" | "duration";
  label: string;
  value: number | null;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className={value === null ? styles.unavailable : undefined}>
        {format === "duration" ? formatDuration(value) : formatCount(value)}
      </dd>
    </div>
  );
}

function agentLabel(agent: BatchDialerVaPerformanceAgent) {
  return agent.user_name
    ? `${agent.user_name} (${agent.provider_agent_name})`
    : agent.provider_agent_name;
}

function CoachEvidence({ references }: { references: string[] }) {
  if (!references.length) return null;
  return (
    <small className={styles.coachEvidence}>
      Evidence: {references.join(", ")}
    </small>
  );
}

function coachStaleReason(reason: BatchDialerVaCoachReport["stale_reasons"][number]) {
  if (reason === "evidence_changed") {
    return "The BatchDialer performance evidence changed after this draft was generated.";
  }
  return "The coaching model, prompt, schema, or safety contract changed after this draft was generated.";
}

export function BatchDialerVaPerformanceSection({
  initialApiConnected,
  initialCampaignMappings,
  initialCampaignMappingsAvailable,
  initialData,
  initialMappings,
}: {
  initialApiConnected: boolean;
  initialCampaignMappings: BatchDialerCampaignMappings | null;
  initialCampaignMappingsAvailable: boolean;
  initialData: BatchDialerVaPerformance | null;
  initialMappings: BatchDialerAgentMappings | null;
}) {
  const { getToken } = useAuth();
  const [data, setData] = useState(initialData);
  const [mappings, setMappings] = useState(initialMappings);
  const [range, setRange] = useState<RangeKey>(() => inferRange(initialData));
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(initialApiConnected ? "" : "BatchDialer performance data is temporarily unavailable.");
  const [mappingSelections, setMappingSelections] = useState<Record<string, string>>(
    () => Object.fromEntries((initialMappings?.items ?? []).map((item) => [item.id, item.user_id ?? ""])),
  );
  const [mappingBusyId, setMappingBusyId] = useState("");
  const [mappingStatus, setMappingStatus] = useState<Record<string, { kind: "error" | "success"; text: string }>>({});
  const [coachReport, setCoachReport] = useState<BatchDialerVaCoachReport | null>(null);
  const [coachLoading, setCoachLoading] = useState(false);
  const [coachGenerating, setCoachGenerating] = useState(false);
  const [coachError, setCoachError] = useState("");
  const mountedRef = useRef(true);
  const requestSequenceRef = useRef(0);
  const requestControllerRef = useRef<AbortController | null>(null);
  const coachRequestSequenceRef = useRef(0);
  const coachRequestControllerRef = useRef<AbortController | null>(null);
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  const getHeaders = useCallback(async () => {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    else headers["X-Dev-User-Email"] = devUserEmail;
    return headers;
  }, [devUserEmail, getToken]);

  useEffect(() => () => {
    mountedRef.current = false;
    requestSequenceRef.current += 1;
    requestControllerRef.current?.abort();
    coachRequestSequenceRef.current += 1;
    coachRequestControllerRef.current?.abort();
  }, []);

  const loadLatestCoach = useCallback(async (
    providerAgentId: string,
    dateFrom?: string,
    dateTo?: string,
  ) => {
    coachRequestSequenceRef.current += 1;
    const requestSequence = coachRequestSequenceRef.current;
    coachRequestControllerRef.current?.abort();
    setCoachGenerating(false);
    if (!providerAgentId) {
      setCoachReport(null);
      setCoachError("");
      setCoachLoading(false);
      return;
    }
    const controller = new AbortController();
    coachRequestControllerRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 12_000);
    const query = new URLSearchParams({ provider_agent_id: providerAgentId });
    if (dateFrom) query.set("date_from", dateFrom);
    if (dateTo) query.set("date_to", dateTo);
    setCoachReport(null);
    setCoachLoading(true);
    setCoachError("");
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/prospecting/batchdialer/va-coach/latest?${query.toString()}`,
        { cache: "no-store", headers: await getHeaders(), signal: controller.signal },
      );
      if (response.status === 404) {
        if (mountedRef.current && requestSequence === coachRequestSequenceRef.current) {
          setCoachReport(null);
        }
        return;
      }
      if (response.status === 401 || response.status === 403) {
        if (mountedRef.current && requestSequence === coachRequestSequenceRef.current) {
          setCoachReport(null);
          setCoachError("Your manager coaching access expired or was removed.");
        }
        return;
      }
      const payload = (await response.json().catch(() => null)) as
        | BatchDialerVaCoachReport
        | { detail?: string }
        | null;
      if (
        !response.ok ||
        !payload ||
        !("output" in payload) ||
        !("is_stale" in payload) ||
        !("refresh_required" in payload) ||
        !("stale_reasons" in payload) ||
        !("current_evidence_as_of" in payload) ||
        (!payload.output && !payload.is_stale && !payload.refresh_required)
      ) {
        throw new Error(
          payload && "detail" in payload && payload.detail
            ? payload.detail
            : "The latest coaching draft could not be loaded.",
        );
      }
      if (mountedRef.current && requestSequence === coachRequestSequenceRef.current) {
        setCoachReport(payload);
      }
    } catch (requestError) {
      if (mountedRef.current && requestSequence === coachRequestSequenceRef.current) {
        setCoachError(
          requestError instanceof Error && requestError.name !== "AbortError"
            ? requestError.message
            : "The coaching request timed out.",
        );
      }
    } finally {
      window.clearTimeout(timeout);
      if (mountedRef.current && requestSequence === coachRequestSequenceRef.current) {
        setCoachLoading(false);
      }
      if (coachRequestControllerRef.current === controller) {
        coachRequestControllerRef.current = null;
      }
    }
  }, [apiBaseUrl, getHeaders]);

  useEffect(() => {
    void loadLatestCoach(selectedAgentId, data?.date_from, data?.date_to);
  }, [data?.date_from, data?.date_to, loadLatestCoach, selectedAgentId]);

  const loadPerformance = useCallback(async (nextRange: RangeKey) => {
    const requestSequence = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestSequence;
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 12_000);
    const timeZone = data?.timezone ?? "America/New_York";
    const dates = rangeDates(nextRange, timeZone);
    const query = new URLSearchParams({ date_from: dates.dateFrom, date_to: dates.dateTo });

    setLoading(true);
    setError("");
    try {
      const headers = await getHeaders();
      const [performanceResponse, mappingsResponse] = await Promise.all([
        fetch(`${apiBaseUrl}/api/v1/prospecting/batchdialer/va-performance?${query.toString()}`, {
          cache: "no-store",
          headers,
          signal: controller.signal,
        }),
        fetch(`${apiBaseUrl}/api/v1/prospecting/batchdialer/agent-mappings`, {
          cache: "no-store",
          headers,
          signal: controller.signal,
        }),
      ]);
      if (
        performanceResponse.status === 401 ||
        performanceResponse.status === 403 ||
        mappingsResponse.status === 401 ||
        mappingsResponse.status === 403
      ) {
        if (mountedRef.current && requestSequence === requestSequenceRef.current) {
          setData(null);
          setMappings(null);
          setError("Your BatchDialer analytics access expired or was removed. The prior snapshot has been cleared.");
        }
        return;
      }
      const performancePayload = (await performanceResponse.json().catch(() => null)) as
        | BatchDialerVaPerformance
        | { detail?: string }
        | null;
      const mappingsPayload = (await mappingsResponse.json().catch(() => null)) as
        | BatchDialerAgentMappings
        | { detail?: string }
        | null;
      if (!performanceResponse.ok || !performancePayload || !("summary" in performancePayload)) {
        throw new Error(
          performancePayload && "detail" in performancePayload && performancePayload.detail
            ? performancePayload.detail
            : "BatchDialer performance is temporarily unavailable.",
        );
      }
      if (!mappingsResponse.ok || !mappingsPayload || !("items" in mappingsPayload)) {
        throw new Error(
          mappingsPayload && "detail" in mappingsPayload && mappingsPayload.detail
            ? mappingsPayload.detail
            : "BatchDialer agent mappings are temporarily unavailable.",
        );
      }
      if (mountedRef.current && requestSequence === requestSequenceRef.current) {
        setData(performancePayload);
        setMappings(mappingsPayload);
        setMappingSelections(
          Object.fromEntries(mappingsPayload.items.map((item) => [item.id, item.user_id ?? ""])),
        );
        setRange(nextRange);
        const retainedAgentId = selectedAgentId && performancePayload.agents.some(
          (agent) => agent.provider_agent_id === selectedAgentId,
        )
          ? selectedAgentId
          : "";
        setSelectedAgentId(retainedAgentId);
        void loadLatestCoach(
          retainedAgentId,
          performancePayload.date_from,
          performancePayload.date_to,
        );
      }
    } catch (requestError) {
      if (mountedRef.current && requestSequence === requestSequenceRef.current) {
        setError(
          requestError instanceof Error && requestError.name !== "AbortError"
            ? requestError.message
            : "BatchDialer performance timed out. The prior confirmed snapshot remains visible.",
        );
      }
    } finally {
      window.clearTimeout(timeout);
      if (mountedRef.current && requestSequence === requestSequenceRef.current) setLoading(false);
      if (requestControllerRef.current === controller) requestControllerRef.current = null;
    }
  }, [apiBaseUrl, data?.timezone, getHeaders, loadLatestCoach, selectedAgentId]);

  const selectedAgent = useMemo(
    () => data?.agents.find((agent) => agent.provider_agent_id === selectedAgentId) ?? null,
    [data?.agents, selectedAgentId],
  );
  const displayedMetrics = selectedAgent?.metrics ?? data?.summary ?? null;
  const generateCoach = useCallback(async () => {
    if (!selectedAgent || !data) return;
    coachRequestSequenceRef.current += 1;
    const requestSequence = coachRequestSequenceRef.current;
    coachRequestControllerRef.current?.abort();
    const controller = new AbortController();
    coachRequestControllerRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 45_000);
    setCoachGenerating(true);
    setCoachError("");
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/prospecting/batchdialer/va-coach`,
        {
          method: "POST",
          cache: "no-store",
          headers: await getHeaders(),
          signal: controller.signal,
          body: JSON.stringify({
            provider_agent_id: selectedAgent.provider_agent_id,
            date_from: data.date_from,
            date_to: data.date_to,
          }),
        },
      );
      const payload = (await response.json().catch(() => null)) as
        | BatchDialerVaCoachReport
        | { detail?: string }
        | null;
      if (
        !response.ok ||
        !payload ||
        !("output" in payload) ||
        !("is_stale" in payload) ||
        !("refresh_required" in payload) ||
        !("stale_reasons" in payload) ||
        !("current_evidence_as_of" in payload) ||
        !payload.output ||
        payload.is_stale ||
        payload.refresh_required
      ) {
        throw new Error(
          payload && "detail" in payload && payload.detail
            ? payload.detail
            : "The coaching draft could not be generated.",
        );
      }
      if (mountedRef.current && requestSequence === coachRequestSequenceRef.current) {
        setCoachReport(payload);
      }
    } catch (requestError) {
      if (mountedRef.current && requestSequence === coachRequestSequenceRef.current) {
        setCoachError(
          requestError instanceof Error && requestError.name !== "AbortError"
            ? requestError.message
            : "The coaching draft timed out. Try again after the AI provider recovers.",
        );
      }
    } finally {
      window.clearTimeout(timeout);
      if (mountedRef.current && requestSequence === coachRequestSequenceRef.current) {
        setCoachGenerating(false);
      }
      if (coachRequestControllerRef.current === controller) {
        coachRequestControllerRef.current = null;
      }
    }
  }, [apiBaseUrl, data, getHeaders, selectedAgent]);
  const coachRefreshRequired = Boolean(
    coachReport &&
      (coachReport.is_stale || coachReport.refresh_required || coachReport.output === null),
  );
  const coachOutput = coachReport && !coachRefreshRequired ? coachReport.output : null;
  const coachReconciliationPending = Boolean(loading && selectedAgentId);
  const filteredDailyActivity = useMemo(
    () => (data?.daily_activity ?? [])
      .filter((row) => !selectedAgentId || row.provider_agent_id === selectedAgentId)
      .sort((left, right) => right.date.localeCompare(left.date)),
    [data?.daily_activity, selectedAgentId],
  );
  const hourlyBuckets = useMemo(() => {
    if (!data) return [];
    const buckets = Array.from({ length: 24 }, (_, hour) => ({
      hour,
      calls: null as number | null,
      humanContacts: null as number | null,
      verifiedHandoffs: null as number | null,
      recordedCallSeconds: null as number | null,
    }));
    const hourFormatter = new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      hourCycle: "h23",
      timeZone: data.timezone,
    });
    for (const row of data.hourly_activity) {
      if (selectedAgentId && row.provider_agent_id !== selectedAgentId) continue;
      const parsed = new Date(row.hour_start_at);
      if (Number.isNaN(parsed.getTime())) continue;
      const hourPart = hourFormatter.formatToParts(parsed).find((part) => part.type === "hour")?.value;
      const hour = Number(hourPart);
      if (!Number.isInteger(hour) || hour < 0 || hour > 23) continue;
      const bucket = buckets[hour];
      if (row.calls !== null) bucket.calls = (bucket.calls ?? 0) + row.calls;
      if (row.human_contacts !== null) {
        bucket.humanContacts = (bucket.humanContacts ?? 0) + row.human_contacts;
      }
      if (row.verified_handoffs !== null) {
        bucket.verifiedHandoffs = (bucket.verifiedHandoffs ?? 0) + row.verified_handoffs;
      }
      if (row.recorded_call_seconds !== null) {
        bucket.recordedCallSeconds =
          (bucket.recordedCallSeconds ?? 0) + row.recorded_call_seconds;
      }
    }
    return buckets;
  }, [data, selectedAgentId]);
  const maximumHourlyCalls = Math.max(
    1,
    ...hourlyBuckets.map((bucket) => bucket.calls ?? 0),
  );

  const saveMapping = useCallback(async (mapping: BatchDialerAgentMapping) => {
    const selectedUserId = mappingSelections[mapping.id] ?? "";
    setMappingBusyId(mapping.id);
    setMappingStatus((current) => {
      const next = { ...current };
      delete next[mapping.id];
      return next;
    });
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/prospecting/batchdialer/agent-mappings/${mapping.id}`,
        {
          method: "PATCH",
          cache: "no-store",
          headers: await getHeaders(),
          body: JSON.stringify({ user_id: selectedUserId || null }),
        },
      );
      const payload = (await response.json().catch(() => null)) as
        | BatchDialerAgentMapping
        | { detail?: string }
        | null;
      if (!response.ok) {
        throw new Error(
          payload && "detail" in payload && payload.detail
            ? payload.detail
            : "The agent mapping could not be saved.",
        );
      }
      const selectedUser = mappings?.users.find((user) => user.id === selectedUserId) ?? null;
      const updated = payload && "id" in payload
        ? payload
        : { ...mapping, user_id: selectedUserId || null, user_name: selectedUser?.name ?? null };
      if (!mountedRef.current) return;
      setMappings((current) => current
        ? { ...current, items: current.items.map((item) => item.id === mapping.id ? updated : item) }
        : current);
      setData((current) => current
        ? {
            ...current,
            agents: current.agents.map((agent) =>
              agent.mapping_id === mapping.id || agent.provider_agent_id === mapping.provider_agent_id
                ? { ...agent, user_id: updated.user_id, user_name: updated.user_name }
                : agent,
            ),
          }
        : current);
      setMappingStatus((current) => ({
        ...current,
        [mapping.id]: { kind: "success", text: "Mapping saved." },
      }));
    } catch (requestError) {
      if (!mountedRef.current) return;
      setMappingStatus((current) => ({
        ...current,
        [mapping.id]: {
          kind: "error",
          text: requestError instanceof Error ? requestError.message : "The agent mapping could not be saved.",
        },
      }));
    } finally {
      if (mountedRef.current) setMappingBusyId("");
    }
  }, [apiBaseUrl, getHeaders, mappingSelections, mappings?.users]);

  return (
    <section aria-busy={loading} className={styles.workspace}>
      <header className={styles.header}>
        <div>
          <span>BatchDialer direct integration</span>
          <h2>VA performance</h2>
          <p>See verified calling activity, qualification quality, appointments, and downstream business outcomes.</p>
        </div>
        <div className={styles.headerMeta}>
          <strong>{data ? `${data.date_from} - ${data.date_to}` : "No confirmed period"}</strong>
          <span>{data ? data.timezone : "Timezone unavailable"}</span>
          {data ? <span>Updated {formatLocalTimestamp(data.as_of, data.timezone)}</span> : null}
        </div>
      </header>

      <div className={styles.controls}>
        <div aria-label="Performance date range" className={styles.rangeButtons} role="group">
          {(["today", "7", "30"] as RangeKey[]).map((option) => (
            <button
              aria-pressed={range === option}
              className={range === option ? styles.activeRange : undefined}
              disabled={loading}
              key={option}
              onClick={() => void loadPerformance(option)}
              type="button"
            >
              {option === "today" ? "Today" : `Last ${option} days`}
            </button>
          ))}
        </div>
        <label>
          <span>Agent</span>
          <select value={selectedAgentId} onChange={(event) => setSelectedAgentId(event.target.value)}>
            <option value="">All agents</option>
            {(data?.agents ?? []).map((agent) => (
              <option key={agent.provider_agent_id} value={agent.provider_agent_id}>
                {agentLabel(agent)}
              </option>
            ))}
          </select>
        </label>
        <button
          className={styles.refreshButton}
          disabled={loading}
          onClick={() => void loadPerformance(range)}
          type="button"
        >
          <RefreshCw aria-hidden="true" className={loading ? styles.spinning : undefined} size={16} />
          {loading ? "Refreshing" : "Refresh"}
        </button>
      </div>

      <div className={styles.callDerivedNotice} role="note">
        <Clock3 aria-hidden="true" size={19} />
        <div>
          <strong>Call-derived activity - Not a timeclock</strong>
          <p>Observed calling span is inferred from completed call records. It does not prove paid hours, continuous work, login time, or time spent on non-call tasks.</p>
          {data ? (
            <>
              <p>
                Archive evidence {data.earliest_archived_call_at
                  ? `starts with an observed call on ${formatLocalTimestamp(data.earliest_archived_call_at, data.timezone)}`
                  : "has no observed call yet"}. The connector scans a rolling {data.provider_scan_window_days}-day provider window, so older dates may be incomplete rather than zero.
              </p>
              <p>
                Provider CDR sync: <b>{data.provider_sync_freshness}</b>
                {` (${data.provider_sync_status})`}. Last successful completion: <b>{formatLocalTimestamp(data.provider_sync_last_success_at, data.timezone)}</b>. Expected every {data.provider_sync_poll_interval_seconds} seconds.
                {data.provider_sync_error_present ? " A provider error is recorded; its text is restricted to service logs." : ""}
              </p>
            </>
          ) : null}
          {displayedMetrics ? (
            <div className={styles.activityEvidence}>
              <span>First observed <b>{formatLocalTimestamp(displayedMetrics.first_call_at, data?.timezone ?? "America/New_York")}</b></span>
              <span>Last observed <b>{formatLocalTimestamp(displayedMetrics.last_call_at, data?.timezone ?? "America/New_York")}</b></span>
              <span>Observed span <b>{formatMinutes(displayedMetrics.inferred_calling_minutes)}</b></span>
              <span>Recorded call duration <b>{formatDuration(displayedMetrics.recorded_call_seconds)}</b></span>
            </div>
          ) : null}
        </div>
      </div>

      {error ? <p aria-live="assertive" className={styles.error}>{error}</p> : null}
      {data?.coverage_warnings.length ? (
        <div className={styles.coverageWarnings} role="status">
          <AlertTriangle aria-hidden="true" size={19} />
          <div>
            <strong>Coverage notes</strong>
            <ul>{data.coverage_warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
          </div>
        </div>
      ) : null}

      <BatchDialerCampaignMappingsPanel
        initialAvailable={initialCampaignMappingsAvailable}
        initialData={initialCampaignMappings}
        timeZone={data?.timezone ?? "America/New_York"}
      />

      {displayedMetrics ? (
        <>
          <div aria-label="BatchDialer performance summary" className={styles.metricGrid}>
            <MetricCard detail="Completed outbound records" icon={<Headphones aria-hidden="true" size={18} />} label="Calls" value={formatCount(displayedMetrics.calls)} />
            <MetricCard detail="Calls with a detected person" icon={<UsersRound aria-hidden="true" size={18} />} label="Human contacts" value={formatCount(displayedMetrics.human_contacts)} />
            <MetricCard detail="New Stonegate leads after validation" icon={<ShieldCheck aria-hidden="true" size={18} />} label="Verified handoffs" value={formatCount(displayedMetrics.verified_handoffs)} />
            <MetricCard detail="Appointments recorded as held" icon={<CalendarCheck2 aria-hidden="true" size={18} />} label="Appointments held" value={formatCount(displayedMetrics.appointments_held)} />
            <MetricCard detail="Acquisition contracts signed" icon={<UserCheck aria-hidden="true" size={18} />} label="Signed contracts" value={formatCount(displayedMetrics.signed_contracts)} />
            <MetricCard detail="Transactions recorded as closed" icon={<Check aria-hidden="true" size={18} />} label="Closed transactions" value={formatCount(displayedMetrics.closed_transactions)} />
          </div>

          <section className={styles.panel}>
            <div className={styles.panelHeader}>
              <div>
                <span>Manager scorecard</span>
                <h3>Agent performance and lead quality</h3>
              </div>
              <p>Provider candidates stay separate from verified Stonegate handoffs.</p>
            </div>
            {data?.agents.length ? (
              <div aria-label="BatchDialer agent performance scorecard" className={styles.tableWrap} tabIndex={0}>
                <table>
                  <thead><tr><th scope="col">Agent</th>{scorecardColumns.map((column) => <th key={column.key} scope="col">{column.label}</th>)}</tr></thead>
                  <tbody>
                    {data.agents.map((agent) => (
                      <tr key={agent.provider_agent_id}>
                        <th scope="row"><strong>{agent.user_name ?? agent.provider_agent_name}</strong><small>{agent.user_name ? agent.provider_agent_name : "Stonegate user not mapped"}</small></th>
                        {scorecardColumns.map((column) => (
                          <td className={agent.metrics[column.key] === null ? styles.unavailable : undefined} key={column.key}>
                            {formatMetric(agent.metrics, column.key, column.format)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className={styles.empty}>No agent activity was returned for this period.</p>}
          </section>

          <div className={styles.outcomeGrid}>
            <section className={styles.outcomeCard}>
              <span>Qualification integrity</span><h3>Candidate to verified</h3>
              <dl>
                <OutcomeMetric label="Qualified candidates" value={displayedMetrics.qualified_candidates} />
                <OutcomeMetric label="Evidence accepted" value={displayedMetrics.evidence_accepted_candidates} />
                <OutcomeMetric label="New verified handoffs" value={displayedMetrics.verified_handoffs} />
                <OutcomeMetric label="False positives" value={displayedMetrics.qualification_false_positives} />
                <OutcomeMetric label="Calls with duration" value={displayedMetrics.recorded_duration_calls} />
                <OutcomeMetric format="duration" label="Average recorded duration" value={displayedMetrics.average_recorded_call_seconds} />
              </dl>
              <small>
                Evidence acceptance rate {formatRate(displayedMetrics.evidence_acceptance_rate_basis_points)};
                false-positive rate {formatRate(displayedMetrics.false_positive_rate_basis_points)}.
                Duration coverage {formatRate(displayedMetrics.recorded_duration_coverage_basis_points)}.
                Average duration excludes calls where the provider supplied no duration.
              </small>
            </section>
            <section className={styles.outcomeCard}>
              <span>Appointment funnel</span><h3>Set to entered to held</h3>
              <dl>
                <OutcomeMetric label="Appointments set" value={displayedMetrics.appointments_set} />
                <OutcomeMetric label="Entered in Stonegate" value={displayedMetrics.appointments_entered} />
                <OutcomeMetric label="Handoffs with appointment" value={displayedMetrics.handoffs_with_appointment_entered} />
                <OutcomeMetric label="Appointments held" value={displayedMetrics.appointments_held} />
                <OutcomeMetric label="Signed contracts" value={displayedMetrics.signed_contracts} />
              </dl>
              <small>
                Stonegate appointment-entry rate {formatRate(displayedMetrics.appointments_entered_rate_basis_points)}
                is the share of verified handoffs with at least one entered appointment.
              </small>
            </section>
            <section className={styles.outcomeCard}>
              <span>Call dispositions</span><h3>Non-lead outcomes</h3>
              <dl>
                <OutcomeMetric label="Do not call" value={displayedMetrics.dnc} />
                <OutcomeMetric label="Not interested" value={displayedMetrics.not_interested} />
                <OutcomeMetric label="Voicemail" value={displayedMetrics.voicemails} />
                <OutcomeMetric label="No answer" value={displayedMetrics.no_answers} />
              </dl>
            </section>
          </div>

          <section className={`${styles.panel} ${styles.coachPanel}`}>
            <div className={styles.panelHeader}>
              <div>
                <span>AI manager coach</span>
                <h3>{selectedAgent ? `Draft coaching for ${selectedAgent.user_name ?? selectedAgent.provider_agent_name}` : "Select one agent to prepare coaching"}</h3>
              </div>
              {selectedAgent ? (
                <button
                  className={styles.coachButton}
                  disabled={coachLoading || coachGenerating}
                  onClick={() => void generateCoach()}
                  type="button"
                >
                  <Activity aria-hidden="true" size={16} />
                  {coachGenerating
                    ? "Preparing draft..."
                    : coachRefreshRequired
                      ? "Prepare current coaching draft"
                      : coachReport
                        ? "Refresh coaching draft"
                        : "Prepare coaching draft"}
                </button>
              ) : null}
            </div>
            <div className={styles.coachBoundary} role="note">
              Manager coaching only. This draft never determines discipline, pay, employment status, or work hours. A manager must review the evidence and decide what is useful.
            </div>
            {coachError ? <p aria-live="assertive" className={styles.error}>{coachError}</p> : null}
            {!selectedAgent ? (
              <p className={styles.empty}>Choose an agent above to view or prepare an evidence-backed coaching draft.</p>
            ) : coachLoading || coachReconciliationPending ? (
              <p aria-live="polite" className={styles.empty}>Checking the latest coaching draft against current performance evidence...</p>
            ) : coachReport && coachRefreshRequired ? (
              <div aria-live="polite" className={styles.coachStaleNotice} role="status">
                <AlertTriangle aria-hidden="true" size={20} />
                <div>
                  <strong>Coaching refresh required</strong>
                  <p>This saved draft is out of date and is not shown as current guidance. Prepare a new coaching draft before using it.</p>
                  {coachReport.stale_reasons.length ? (
                    <ul>
                      {coachReport.stale_reasons.map((reason) => (
                        <li key={reason}>{coachStaleReason(reason)}</li>
                      ))}
                    </ul>
                  ) : null}
                  <small>
                    Current evidence checked {formatLocalTimestamp(
                      coachReport.current_evidence_as_of,
                      data?.timezone ?? "America/New_York",
                    )}
                  </small>
                </div>
              </div>
            ) : coachReport && coachOutput ? (
              <div className={styles.coachReport}>
                <div className={styles.coachSummary}>
                  <div>
                    <span>Draft only</span>
                    <strong>{coachOutput.summary.text}</strong>
                    <CoachEvidence references={coachOutput.summary.evidence_refs} />
                  </div>
                  <div className={styles.coachConfidence}>
                    <span>Confidence</span>
                    <strong>{coachOutput.confidence.level}</strong>
                    <p>{coachOutput.confidence.rationale}</p>
                    <CoachEvidence references={coachOutput.confidence.evidence_refs} />
                  </div>
                </div>
                <div className={styles.coachColumns}>
                  <div>
                    <h4>Strengths</h4>
                    {coachOutput.strengths.length ? (
                      <ul>{coachOutput.strengths.map((item, index) => <li key={`${item.observation}:${index}`}><strong>{item.observation}</strong><CoachEvidence references={item.evidence_refs} /></li>)}</ul>
                    ) : <p>No evidence-backed strength was reported.</p>}
                  </div>
                  <div>
                    <h4>Concerns to review</h4>
                    {coachOutput.concerns.length ? (
                      <ul>{coachOutput.concerns.map((item, index) => <li key={`${item.observation}:${index}`}><strong>{item.observation}</strong><CoachEvidence references={item.evidence_refs} /></li>)}</ul>
                    ) : <p>No evidence-backed concern was reported.</p>}
                  </div>
                  <div>
                    <h4>Next-shift actions</h4>
                    {coachOutput.next_shift_actions.length ? (
                      <ol>{coachOutput.next_shift_actions.map((item, index) => <li key={`${item.action}:${index}`}><strong>{item.action}</strong><p>{item.rationale}</p><CoachEvidence references={item.evidence_refs} /></li>)}</ol>
                    ) : <p>No next-shift action was reported.</p>}
                  </div>
                </div>
                <div className={styles.coachReviewGrid}>
                  <div>
                    <h4>Calls to review</h4>
                    {coachOutput.calls_to_review.length ? (
                      <ul>{coachOutput.calls_to_review.map((item) => <li key={item.provider_event_id}><strong>Call {item.provider_event_id}</strong><p>{item.reason}</p><CoachEvidence references={item.evidence_refs} /></li>)}</ul>
                    ) : <p>No specific call was flagged for review.</p>}
                  </div>
                  <div>
                    <h4>Caveats</h4>
                    {coachOutput.comparison_caveats.length ? (
                      <ul>{coachOutput.comparison_caveats.map((item, index) => <li key={`${item.caveat}:${index}`}><strong>{item.caveat}</strong><CoachEvidence references={item.evidence_refs} /></li>)}</ul>
                    ) : <p>No additional comparison caveat was reported.</p>}
                  </div>
                </div>
                <footer className={styles.coachFooter}>
                  <span>Generated {formatLocalTimestamp(coachReport.generated_at, data?.timezone ?? "America/New_York")}</span>
                  <span>Evidence current as of {formatLocalTimestamp(coachReport.current_evidence_as_of, data?.timezone ?? "America/New_York")}</span>
                  <span>{coachReport.reused ? "Reused identical evidence snapshot" : "New evidence snapshot"}</span>
                  <span>{data ? `${data.date_from} - ${data.date_to}` : "Reporting period unavailable"}</span>
                </footer>
              </div>
            ) : (
              <p className={styles.empty}>No coaching draft exists for this agent yet. Prepare one for the selected reporting period when you are ready to review it.</p>
            )}
          </section>

          <section className={styles.panel}>
            <div className={styles.panelHeader}>
              <div><span>Hourly activity</span><h3>When calls occurred</h3></div>
              <p>{selectedAgent ? agentLabel(selectedAgent) : "All agents"} - {data?.timezone}</p>
            </div>
            <div aria-label="Calls by hour" className={styles.timeline}>
              {hourlyBuckets.map((bucket) => {
                const percentage = bucket.calls === null ? 0 : Math.max(3, (bucket.calls / maximumHourlyCalls) * 100);
                const hourLabel = new Intl.DateTimeFormat("en-US", { hour: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(2020, 0, 1, bucket.hour)));
                return (
                  <div className={styles.timelineRow} key={bucket.hour}>
                    <span>{hourLabel}</span>
                    <div className={styles.timelineTrack}>
                      {bucket.calls !== null ? <span aria-hidden="true" style={{ "--activity-width": `${percentage}%` } as CSSProperties} /> : null}
                    </div>
                    <strong className={bucket.calls === null ? styles.unavailable : undefined}>{formatCount(bucket.calls)} calls</strong>
                    <small>{bucket.humanContacts === null ? "Human contacts unavailable" : `${formatCount(bucket.humanContacts)} human`} - {bucket.recordedCallSeconds === null ? "Duration unavailable" : formatDuration(bucket.recordedCallSeconds)} - {bucket.verifiedHandoffs === null ? "Verified unavailable" : `${formatCount(bucket.verifiedHandoffs)} verified`}</small>
                  </div>
                );
              })}
            </div>
          </section>

          <div className={styles.twoColumn}>
            <section className={styles.panel}>
              <div className={styles.panelHeader}><div><span>Daily activity</span><h3>Period trend</h3></div></div>
              {filteredDailyActivity.length ? (
                <div aria-label="BatchDialer daily activity" className={styles.tableWrap} tabIndex={0}>
                  <table><thead><tr><th scope="col">Date</th><th scope="col">Agent</th><th scope="col">Calls</th><th scope="col">Human</th><th scope="col">Verified</th><th scope="col">Recorded duration</th></tr></thead>
                    <tbody>{filteredDailyActivity.map((row) => <tr key={`${row.date}:${row.provider_agent_id}`}><th scope="row">{row.date}</th><td>{row.provider_agent_name}</td><td>{formatCount(row.metrics.calls)}</td><td>{formatCount(row.metrics.human_contacts)}</td><td>{formatCount(row.metrics.verified_handoffs)}</td><td>{formatDuration(row.metrics.recorded_call_seconds)}</td></tr>)}</tbody>
                  </table>
                </div>
              ) : <p className={styles.empty}>No daily activity was returned for this selection.</p>}
            </section>
            <section className={styles.panel}>
              <div className={styles.panelHeader}>
                <div><span>Campaign performance</span><h3>Direct-integration outcomes</h3></div>
                {selectedAgent ? <p>Campaign rows cover all agents; the agent filter does not change them.</p> : null}
              </div>
              {data?.campaigns.length ? (
                <div aria-label="BatchDialer campaign performance" className={styles.tableWrap} tabIndex={0}>
                  <table><thead><tr><th scope="col">Campaign</th><th scope="col">Calls</th><th scope="col">Human</th><th scope="col">Verified</th><th scope="col">Contracts</th><th scope="col">Closed</th></tr></thead>
                    <tbody>{data.campaigns.map((campaign) => <tr key={campaign.provider_campaign_id}><th scope="row">{campaign.campaign_name}</th><td>{formatCount(campaign.metrics.calls)}</td><td>{formatCount(campaign.metrics.human_contacts)}</td><td>{formatCount(campaign.metrics.verified_handoffs)}</td><td>{formatCount(campaign.metrics.signed_contracts)}</td><td>{formatCount(campaign.metrics.closed_transactions)}</td></tr>)}</tbody>
                  </table>
                </div>
              ) : <p className={styles.empty}>No campaign activity was returned for this period.</p>}
            </section>
          </div>

          <section className={styles.panel}>
            <div className={styles.panelHeader}>
              <div><span>Identity mapping</span><h3>Connect BatchDialer agents to Stonegate users</h3></div>
              <p>Saving a mapping changes attribution on future refreshes; it does not create a timeclock.</p>
            </div>
            {mappings?.items.length ? (
              <div aria-label="BatchDialer agent mappings" className={styles.mappingList}>
                {mappings.items.map((mapping) => {
                  const status = mappingStatus[mapping.id];
                  const unchanged = (mappingSelections[mapping.id] ?? "") === (mapping.user_id ?? "");
                  return (
                    <div className={styles.mappingRow} key={mapping.id}>
                      <div className={styles.mappingIdentity}>
                        <Link2 aria-hidden="true" size={17} />
                        <div><strong>{mapping.provider_agent_name}</strong><span>BatchDialer ID {mapping.provider_agent_id}</span><small>Last seen {formatLocalTimestamp(mapping.last_seen_at, data?.timezone ?? "America/New_York")}</small></div>
                      </div>
                      <label><span>Stonegate user</span><select disabled={mappingBusyId === mapping.id} onChange={(event) => setMappingSelections((current) => ({ ...current, [mapping.id]: event.target.value }))} value={mappingSelections[mapping.id] ?? ""}><option value="">Unassigned</option>{mappings.users.map((user) => <option disabled={!user.is_active} key={user.id} value={user.id}>{user.name} - {user.email}{user.is_active ? "" : " (inactive - clear or replace)"}</option>)}</select></label>
                      <button disabled={mappingBusyId === mapping.id || unchanged} onClick={() => void saveMapping(mapping)} type="button">{mappingBusyId === mapping.id ? "Saving..." : "Save mapping"}</button>
                      <p aria-live="polite" className={status?.kind === "error" ? styles.mappingError : styles.mappingSuccess}>{status?.text ?? ""}</p>
                    </div>
                  );
                })}
              </div>
            ) : <p className={styles.empty}>No BatchDialer agents are available to map yet.</p>}
          </section>
        </>
      ) : (
        <div className={styles.emptyState}>
          <Activity aria-hidden="true" size={24} />
          <div><h3>BatchDialer performance is unavailable</h3><p>No call-derived values are shown. Refresh after the direct integration has completed a successful poll.</p></div>
        </div>
      )}
    </section>
  );
}
