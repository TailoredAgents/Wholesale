"use client";

import { useAuth } from "@clerk/nextjs";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  CircleDollarSign,
  CircleSlash2,
  Clock3,
  RefreshCw,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  UsersRound,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  ProspectingDialerAnalytics,
  ProspectingDialerDimensionScorecard,
  ProspectingDialerScorecardMetrics,
} from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./prospecting.module.css";

type AnalyticsFilters = {
  dateFrom: string;
  dateTo: string;
  cohortId: string;
  source: string;
  campaignId: string;
  callerUserId: string;
  dialMode: string;
};

type BreakdownKey = "va" | "campaign" | "cohort" | "list" | "dial_mode";
type MetricFormat = "count" | "money" | "percent" | "per-hour" | "minutes" | "seconds" | "score" | "trend";
type MetricStatus = "known" | "partial" | "unknown" | "not_applicable";
type ScorecardMetricKey = Exclude<
  keyof ProspectingDialerScorecardMetrics,
  "coverage" | "status_by_key"
>;

const moneyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});
const numberFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
const preciseFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

function initialFilters(data: ProspectingDialerAnalytics): AnalyticsFilters {
  return {
    dateFrom: data.period.date_from,
    dateTo: data.period.date_to,
    cohortId: data.filters.cohort_id ?? "",
    source: data.filters.source ?? "",
    campaignId: data.filters.campaign_id ?? "",
    callerUserId: data.filters.caller_user_id ?? "",
    dialMode: data.filters.dial_mode ?? "",
  };
}

function formatMetric(value: number, format: MetricFormat) {
  if (format === "money") return moneyFormatter.format(value / 100);
  if (format === "percent") return `${preciseFormatter.format(value / 100)}%`;
  if (format === "per-hour") return preciseFormatter.format(value / 100);
  if (format === "minutes") {
    return value < 60 ? `${numberFormatter.format(value)} min` : `${numberFormatter.format(value / 60)} hr`;
  }
  if (format === "seconds") return `${numberFormatter.format(value)} sec`;
  if (format === "trend") {
    const percentage = value / 100;
    return `${percentage > 0 ? "+" : ""}${preciseFormatter.format(percentage)}%`;
  }
  return numberFormatter.format(value);
}

function MetricValue({
  format = "count",
  status,
  value,
}: {
  format?: MetricFormat;
  status?: MetricStatus;
  value: number | null;
}) {
  if (status === "not_applicable") return <span className={styles.analyticsUnavailable}>Not applicable</span>;
  if (status === "unknown") return <span className={styles.analyticsUnavailable}>Unavailable</span>;
  if (status === "partial" && value === null) {
    return <span className={styles.analyticsPartialMetric}>Unavailable <em>Partial evidence</em></span>;
  }
  if (value === null) return <span className={styles.analyticsUnavailable}>Unavailable</span>;
  if (status === "partial") {
    return <span className={styles.analyticsPartialMetric}>{formatMetric(value, format)} <em>Partial</em></span>;
  }
  return <>{formatMetric(value, format)}</>;
}

function metricStatus(metrics: ProspectingDialerScorecardMetrics, key: ScorecardMetricKey) {
  return metrics.status_by_key?.[key];
}

function sourceCategory(value: string) {
  const normalized = value.toLowerCase();
  if (normalized.includes("native") || normalized.includes("stonegate")) return "native";
  if (normalized.includes("batch")) return "batchdialer";
  if (
    normalized.includes("paid") ||
    normalized.includes("facebook") ||
    normalized.includes("google")
  ) {
    return "paid";
  }
  return "other";
}

function sourceLabel(value: string) {
  const category = sourceCategory(value);
  if (category === "native") return "Native Stonegate";
  if (category === "batchdialer") return "BatchDialer";
  if (category === "paid") return "Paid ads";
  return labelize(value);
}

function formatUtcDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function readinessCopy(status: ProspectingDialerAnalytics["readiness"]["status"]) {
  if (status === "ready_for_controlled_pilot") {
    return {
      label: "Technical checks ready",
      detail: "Eligible for a controlled pilot only. D10 operating acceptance is still required.",
      className: styles.analyticsReadinessReady,
    };
  }
  if (status === "needs_review") {
    return {
      label: "Manager review required",
      detail: "Warnings or incomplete evidence must be reviewed before a controlled pilot.",
      className: styles.analyticsReadinessWarning,
    };
  }
  return {
    label: "Controlled pilot blocked",
    detail: "Resolve every blocking technical check before native dialing is tested.",
    className: styles.analyticsReadinessBlocked,
  };
}

function CoverageCard({ label, value }: { label: string; value: number | null }) {
  const measured = value !== null;
  const lowCoverage = measured && value < 7500;
  return (
    <div className={!measured ? styles.analyticsCoverageUnknown : lowCoverage ? styles.analyticsCoverageLow : undefined}>
      <span>{label}</span>
      <strong>{measured ? `${numberFormatter.format(value / 100)}%` : "Unavailable"}</strong>
      <small>{!measured ? "Evidence coverage was not reported" : lowCoverage ? "Below the 75% evidence target" : "Records with required evidence"}</small>
    </div>
  );
}

function FunnelCard({
  detail,
  label,
  metricKey,
  metrics,
}: {
  detail: string;
  label: string;
  metricKey: ScorecardMetricKey;
  metrics: ProspectingDialerScorecardMetrics;
}) {
  const value = metrics[metricKey];
  const status = metricStatus(metrics, metricKey);
  return (
    <div>
      <span>{label}</span>
      <strong><MetricValue status={status} value={value} /></strong>
      <small>{value === null || status === "unknown" ? "Required source evidence is unavailable" : status === "not_applicable" ? "This metric does not apply to the selected source" : detail}</small>
    </div>
  );
}

function ScorecardTable({ rows }: { rows: ProspectingDialerDimensionScorecard[] }) {
  if (!rows.length) {
    return (
      <p className={styles.dialerEmptyState}>
        No attributable scorecards are available for this breakdown and date range.
      </p>
    );
  }

  return (
    <div aria-label="Prospecting scorecards" className={styles.analyticsTableWrap} tabIndex={0}>
      <table>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Source / mode</th>
            <th scope="col">Entered leads</th>
            <th scope="col">Attempts</th>
            <th scope="col">Human conversations</th>
            <th scope="col">Qualified sellers</th>
            <th scope="col">Accepted handoffs</th>
            <th scope="col">Contracts</th>
            <th scope="col">Closed</th>
            <th scope="col">Total cost</th>
            <th scope="col">Contribution profit</th>
            <th scope="col">Cost / qualified</th>
            <th scope="col">Blocked / failed</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.dimension_type}:${row.dimension_id ?? row.dimension_name}:${index}`}>
              <th scope="row">{row.dimension_name}</th>
              <td>{row.source ? sourceLabel(row.source) : "All sources"}<small>{row.dial_mode ? labelize(row.dial_mode) : "All modes"}</small></td>
              <td><MetricValue status={metricStatus(row.metrics, "entered_leads")} value={row.metrics.entered_leads} /></td>
              <td><MetricValue status={metricStatus(row.metrics, "attempts")} value={row.metrics.attempts} /></td>
              <td><MetricValue status={metricStatus(row.metrics, "human_conversations")} value={row.metrics.human_conversations} /></td>
              <td><MetricValue status={metricStatus(row.metrics, "qualified_sellers")} value={row.metrics.qualified_sellers} /></td>
              <td><MetricValue status={metricStatus(row.metrics, "accepted_handoffs")} value={row.metrics.accepted_handoffs} /></td>
              <td><MetricValue status={metricStatus(row.metrics, "signed_contracts")} value={row.metrics.signed_contracts} /></td>
              <td><MetricValue status={metricStatus(row.metrics, "closed_assignments")} value={row.metrics.closed_assignments} /></td>
              <td><MetricValue format="money" status={metricStatus(row.metrics, "total_cost_cents")} value={row.metrics.total_cost_cents} /></td>
              <td><MetricValue format="money" status={metricStatus(row.metrics, "contribution_profit_cents")} value={row.metrics.contribution_profit_cents} /></td>
              <td><MetricValue format="money" status={metricStatus(row.metrics, "cost_per_qualified_seller_cents")} value={row.metrics.cost_per_qualified_seller_cents} /></td>
              <td><MetricValue status={metricStatus(row.metrics, "blocked_or_failed_calls")} value={row.metrics.blocked_or_failed_calls} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ProspectingAnalytics({ initialData }: { initialData: ProspectingDialerAnalytics }) {
  const { getToken } = useAuth();
  const [data, setData] = useState<ProspectingDialerAnalytics | null>(initialData);
  const [filters, setFilters] = useState(() => initialFilters(initialData));
  const [breakdown, setBreakdown] = useState<BreakdownKey>("va");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [lastSuccessAt, setLastSuccessAt] = useState(() => new Date().toISOString());
  const mountedRef = useRef(true);
  const confirmedFiltersRef = useRef(initialFilters(initialData));
  const requestSequenceRef = useRef(0);
  const requestControllerRef = useRef<AbortController | null>(null);
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

  useEffect(() => () => {
    mountedRef.current = false;
    requestSequenceRef.current += 1;
    requestControllerRef.current?.abort();
  }, []);

  const loadAnalytics = useCallback(async (nextFilters: AnalyticsFilters) => {
    if (nextFilters.dateFrom > nextFilters.dateTo) {
      setError("Start date must be on or before end date.");
      return;
    }

    const requestSequence = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestSequence;
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 12_000);
    const query = new URLSearchParams({
      date_from: nextFilters.dateFrom,
      date_to: nextFilters.dateTo,
    });
    if (nextFilters.cohortId) query.set("cohort_id", nextFilters.cohortId);
    if (nextFilters.source) query.set("source", nextFilters.source);
    if (nextFilters.campaignId) query.set("campaign_id", nextFilters.campaignId);
    if (nextFilters.callerUserId) query.set("caller_user_id", nextFilters.callerUserId);
    if (nextFilters.dialMode) query.set("dial_mode", nextFilters.dialMode);

    setLoading(true);
    setError("");
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/prospecting/dialer/analytics?${query.toString()}`,
        { headers: await headers(), cache: "no-store", signal: controller.signal },
      );
      if (response.status === 401 || response.status === 403) {
        if (mountedRef.current && requestSequence === requestSequenceRef.current) {
          setData(null);
          setError("Your analytics access expired or was removed. The prior snapshot, including financial data, has been cleared.");
        }
        return;
      }
      const payload = (await response.json().catch(() => null)) as
        | ProspectingDialerAnalytics
        | { detail?: string }
        | null;
      if (!response.ok || !payload || !("period" in payload)) {
        throw new Error(
          payload && "detail" in payload && payload.detail
            ? payload.detail
            : "Prospecting analytics are temporarily unavailable.",
        );
      }
      if (mountedRef.current && requestSequence === requestSequenceRef.current) {
        setData(payload);
        const confirmedFilters = initialFilters(payload);
        confirmedFiltersRef.current = confirmedFilters;
        setFilters(confirmedFilters);
        setLastSuccessAt(new Date().toISOString());
      }
    } catch (requestError) {
      if (mountedRef.current && requestSequence === requestSequenceRef.current) {
        setFilters(confirmedFiltersRef.current);
        setError(
          requestError instanceof Error && requestError.name !== "AbortError"
            ? requestError.message
            : "Prospecting analytics timed out. The prior confirmed snapshot remains visible.",
        );
      }
    } finally {
      window.clearTimeout(timeout);
      if (mountedRef.current && requestSequence === requestSequenceRef.current) setLoading(false);
      if (requestControllerRef.current === controller) requestControllerRef.current = null;
    }
  }, [apiBaseUrl, headers]);

  function submitFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadAnalytics(filters);
  }

  const resetFilters = useCallback(() => {
    const reset = {
      dateFrom: initialData.period.date_from,
      dateTo: initialData.period.date_to,
      cohortId: "",
      source: "",
      campaignId: "",
      callerUserId: "",
      dialMode: "",
    };
    setFilters(reset);
    void loadAnalytics(reset);
  }, [initialData.period.date_from, initialData.period.date_to, loadAnalytics]);

  const breakdownRows = useMemo(() => {
    if (!data) return [];
    if (breakdown === "campaign") return data.by_campaign;
    if (breakdown === "cohort") return data.by_cohort;
    if (breakdown === "list") return data.by_list;
    if (breakdown === "dial_mode") return data.by_dial_mode;
    return data.by_va;
  }, [breakdown, data]);

  const comparisonCoverage = useMemo(() => {
    if (!data) return [];
    const categories = new Set(data.by_source.map((row) => sourceCategory(row.source ?? row.dimension_name)));
    return [
      { key: "native", label: "Native Stonegate", available: categories.has("native") },
      { key: "batchdialer", label: "BatchDialer", available: categories.has("batchdialer") },
      { key: "paid", label: "Paid ads", available: categories.has("paid") },
    ];
  }, [data]);

  if (!data) {
    return (
      <section aria-live="assertive" className={styles.analyticsAccessRevoked} role="alert">
        <CircleSlash2 aria-hidden="true" size={22} />
        <div>
          <h2>Prospecting analytics access unavailable</h2>
          <p>{error || "Your session no longer permits this report. Refresh or sign in again after access is restored."}</p>
          <strong>No prior analytics or financial values are retained in this view.</strong>
        </div>
      </section>
    );
  }

  const readiness = readinessCopy(data.readiness.status);
  const summary = data.summary;
  const coverage = summary.coverage;
  const periodLabel = `${formatUtcDate(data.period.date_from)} - ${formatUtcDate(data.period.date_to)} UTC`;

  return (
    <div aria-busy={loading} className={styles.analyticsWorkspace}>
      {error ? (
        <p aria-live="assertive" className={styles.error}>
          {error} Last confirmed: {new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(new Date(lastSuccessAt))}.
        </p>
      ) : null}

      <section className={`${styles.analyticsHero} ${readiness.className}`}>
        <div>
          <span>Controlled-pilot measurement</span>
          <h2>{readiness.label}</h2>
          <p>{readiness.detail}</p>
        </div>
        <div className={styles.analyticsHeroMeta}>
          <strong>{periodLabel}</strong>
          <span>{data.readiness.d10_acceptance_required ? "D10 acceptance required" : "Acceptance status unavailable"}</span>
          {data.period.as_of ? <span>Evidence current through {new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(data.period.as_of))} UTC</span> : null}
        </div>
      </section>

      {data.financials_visible === false || coverage.warnings.length ? (
        <section aria-label="Analytics evidence warnings" className={styles.analyticsDataWarning} role="status">
          <AlertTriangle aria-hidden="true" size={19} />
          <div>
            <strong>Some comparisons are incomplete</strong>
            {data.financials_visible === false ? <p>Financial values are hidden for this account, so profit and cost comparisons are unavailable.</p> : null}
            {coverage.warnings.length ? <ul>{coverage.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : null}
          </div>
        </section>
      ) : null}

      <section className={styles.analyticsSection}>
        <header>
          <div><span>Analysis window</span><h2>Filter scorecards</h2></div>
          <span className={styles.statusNeutral}>Inclusive UTC dates</span>
        </header>
        <form className={styles.analyticsFilters} onSubmit={submitFilters}>
          <label><span>Start date</span><input max={filters.dateTo} onChange={(event) => setFilters((current) => ({ ...current, dateFrom: event.target.value }))} required type="date" value={filters.dateFrom} /></label>
          <label><span>End date</span><input min={filters.dateFrom} onChange={(event) => setFilters((current) => ({ ...current, dateTo: event.target.value }))} required type="date" value={filters.dateTo} /></label>
          <label><span>Source</span><select onChange={(event) => setFilters((current) => ({ ...current, source: event.target.value }))} value={filters.source}><option value="">All sources</option>{data.filter_options.sources.map((source) => <option key={source} value={source}>{sourceLabel(source)}</option>)}</select></label>
          <label><span>Campaign</span><select onChange={(event) => setFilters((current) => ({ ...current, campaignId: event.target.value }))} value={filters.campaignId}><option value="">All campaigns</option>{data.filter_options.campaigns.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label><span>Cohort</span><select onChange={(event) => setFilters((current) => ({ ...current, cohortId: event.target.value }))} value={filters.cohortId}><option value="">All cohorts</option>{data.filter_options.cohorts.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label><span>VA / caller</span><select onChange={(event) => setFilters((current) => ({ ...current, callerUserId: event.target.value }))} value={filters.callerUserId}><option value="">All callers</option>{data.filter_options.callers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label><span>Dial mode</span><select onChange={(event) => setFilters((current) => ({ ...current, dialMode: event.target.value }))} value={filters.dialMode}><option value="">All dial modes</option>{data.filter_options.dial_modes.map((mode) => <option key={mode} value={mode}>{labelize(mode)}</option>)}</select></label>
          <div className={styles.analyticsFilterActions}>
            <button className={styles.secondaryButton} disabled={loading} onClick={resetFilters} type="button">Reset</button>
            <button className={styles.primaryButton} disabled={loading} type="submit">{loading ? <RefreshCw aria-hidden="true" className={styles.analyticsSpinner} size={16} /> : <BarChart3 aria-hidden="true" size={16} />}Apply filters</button>
          </div>
        </form>
      </section>

      <section aria-label="Prospecting funnel" className={styles.analyticsFunnelGrid}>
        <FunnelCard detail="Unique leads entering this selected source or cohort" label="Entered leads" metricKey="entered_leads" metrics={summary} />
        <FunnelCard detail="Outbound attempts" label="Attempts" metricKey="attempts" metrics={summary} />
        <FunnelCard detail="Answered by a human" label="Human conversations" metricKey="human_conversations" metrics={summary} />
        <FunnelCard detail="Confirmed target contact" label="Right-party contacts" metricKey="right_party_contacts" metrics={summary} />
        <FunnelCard detail="Per qualification policy" label="Qualified sellers" metricKey="qualified_sellers" metrics={summary} />
        <FunnelCard detail="Appointments created" label="Appointments set" metricKey="appointments_set" metrics={summary} />
        <FunnelCard detail="Completed appointments" label="Appointments held" metricKey="appointments_held" metrics={summary} />
        <FunnelCard detail="Accepted by acquisitions" label="Accepted handoffs" metricKey="accepted_handoffs" metrics={summary} />
        <FunnelCard detail="Signed seller contracts" label="Contracts" metricKey="signed_contracts" metrics={summary} />
        <FunnelCard detail="Closed assignments" label="Closed" metricKey="closed_assignments" metrics={summary} />
      </section>

      <section className={styles.analyticsSplitGrid}>
        <article className={styles.analyticsSection}>
          <header><div><span>Unit economics</span><h2>Cost and profit</h2></div><CircleDollarSign aria-hidden="true" size={20} /></header>
          <dl className={styles.analyticsMetricList}>
            <div><dt>VA labor cost</dt><dd><MetricValue format="money" status={metricStatus(summary, "labor_cost_cents")} value={summary.labor_cost_cents} /></dd></div>
            <div><dt>Provider cost</dt><dd><MetricValue format="money" status={metricStatus(summary, "provider_cost_cents")} value={summary.provider_cost_cents} /></dd></div>
            <div><dt>List cost</dt><dd><MetricValue format="money" status={metricStatus(summary, "list_cost_cents")} value={summary.list_cost_cents} /></dd></div>
            <div><dt>Other / marketing cost</dt><dd><MetricValue format="money" status={metricStatus(summary, "other_cost_cents")} value={summary.other_cost_cents} /></dd></div>
            <div><dt>Total cost</dt><dd><MetricValue format="money" status={metricStatus(summary, "total_cost_cents")} value={summary.total_cost_cents} /></dd></div>
            <div><dt>Gross revenue</dt><dd><MetricValue format="money" status={metricStatus(summary, "gross_revenue_cents")} value={summary.gross_revenue_cents} /></dd></div>
            <div><dt>Contribution profit</dt><dd><MetricValue format="money" status={metricStatus(summary, "contribution_profit_cents")} value={summary.contribution_profit_cents} /></dd></div>
            <div><dt>Cost / qualified seller</dt><dd><MetricValue format="money" status={metricStatus(summary, "cost_per_qualified_seller_cents")} value={summary.cost_per_qualified_seller_cents} /></dd></div>
            <div><dt>Cost / contract</dt><dd><MetricValue format="money" status={metricStatus(summary, "cost_per_contract_cents")} value={summary.cost_per_contract_cents} /></dd></div>
            <div><dt>Profit / paid VA hour</dt><dd><MetricValue format="money" status={metricStatus(summary, "profit_per_paid_hour_cents")} value={summary.profit_per_paid_hour_cents} /></dd></div>
          </dl>
        </article>

        <article className={styles.analyticsSection}>
          <header><div><span>Efficiency</span><h2>Calling productivity</h2></div><Clock3 aria-hidden="true" size={20} /></header>
          <dl className={styles.analyticsMetricList}>
            <div><dt>Paid VA time</dt><dd><MetricValue format="minutes" status={metricStatus(summary, "paid_minutes")} value={summary.paid_minutes} /></dd></div>
            <div><dt>Productive calling</dt><dd><MetricValue format="minutes" status={metricStatus(summary, "productive_calling_minutes")} value={summary.productive_calling_minutes} /></dd></div>
            <div><dt>Attempts / paid hour</dt><dd><MetricValue format="per-hour" status={metricStatus(summary, "attempts_per_paid_hour_x100")} value={summary.attempts_per_paid_hour_x100} /></dd></div>
            <div><dt>Human talks / paid hour</dt><dd><MetricValue format="per-hour" status={metricStatus(summary, "human_conversations_per_paid_hour_x100")} value={summary.human_conversations_per_paid_hour_x100} /></dd></div>
            <div><dt>Human contact rate</dt><dd><MetricValue format="percent" status={metricStatus(summary, "human_contact_rate_basis_points")} value={summary.human_contact_rate_basis_points} /></dd></div>
            <div><dt>Right-party rate</dt><dd><MetricValue format="percent" status={metricStatus(summary, "right_party_contact_rate_basis_points")} value={summary.right_party_contact_rate_basis_points} /></dd></div>
            <div><dt>Qualified / 100 right-party</dt><dd><MetricValue format="percent" status={metricStatus(summary, "qualified_seller_rate_basis_points")} value={summary.qualified_seller_rate_basis_points} /></dd></div>
            <div><dt>Handoff acceptance</dt><dd><MetricValue format="percent" status={metricStatus(summary, "accepted_handoff_rate_basis_points")} value={summary.accepted_handoff_rate_basis_points} /></dd></div>
            <div><dt>Contract rate</dt><dd><MetricValue format="percent" status={metricStatus(summary, "contract_rate_basis_points")} value={summary.contract_rate_basis_points} /></dd></div>
          </dl>
        </article>
      </section>

      <section className={styles.analyticsSection}>
        <header><div><span>Source comparison</span><h2>Native vs BatchDialer vs paid acquisition</h2></div><span className={styles.statusNeutral}>{data.by_source.length} source scorecards</span></header>
        <p className={styles.analyticsSectionDescription}>Compare business outcomes, not raw dial volume. Source rows can overlap when a paid lead later receives a BatchDialer handoff, so do not add the rows together; the all-source cards above de-duplicate the same lead and downstream records. A source without attributable evidence is marked unavailable for this period.</p>
        <div className={styles.analyticsComparisonCoverage}>
          {comparisonCoverage.map((item) => <div key={item.key}><strong>{item.label}</strong><span className={item.available ? styles.statusGood : styles.statusNeutral}>{item.available ? "Available in period" : "Unavailable in period"}</span></div>)}
        </div>
        <ScorecardTable rows={data.by_source} />
      </section>

      <section className={styles.analyticsSection}>
        <header>
          <div><span>Operating scorecards</span><h2>Performance breakdown</h2></div>
          <label className={styles.analyticsBreakdownSelect}><span>Break down by</span><select aria-label="Scorecard breakdown" onChange={(event) => setBreakdown(event.target.value as BreakdownKey)} value={breakdown}><option value="va">VA / caller</option><option value="campaign">Campaign</option><option value="cohort">Cohort</option><option value="list">List</option><option value="dial_mode">Dial mode</option></select></label>
        </header>
        <ScorecardTable rows={breakdownRows} />
      </section>

      <section className={styles.analyticsSplitGrid}>
        <article className={styles.analyticsSection}>
          <header><div><span>Seller experience</span><h2>Quality and reputation</h2></div><ShieldCheck aria-hidden="true" size={20} /></header>
          <dl className={styles.analyticsMetricList}>
            <div><dt>Calls over 60 seconds</dt><dd><MetricValue status={metricStatus(summary, "conversations_over_60_seconds")} value={summary.conversations_over_60_seconds} /></dd></div>
            <div><dt>Short calls</dt><dd><MetricValue status={metricStatus(summary, "short_calls")} value={summary.short_calls} /></dd></div>
            <div><dt>Silent / dead air</dt><dd><MetricValue status={metricStatus(summary, "silent_or_dead_air_calls")} value={summary.silent_or_dead_air_calls} /></dd></div>
            <div><dt>Blocked / failed</dt><dd><MetricValue status={metricStatus(summary, "blocked_or_failed_calls")} value={summary.blocked_or_failed_calls} /></dd></div>
            <div><dt>No answer</dt><dd><MetricValue status={metricStatus(summary, "no_answer_calls")} value={summary.no_answer_calls} /></dd></div>
            <div><dt>Voicemail</dt><dd><MetricValue status={metricStatus(summary, "voicemail_calls")} value={summary.voicemail_calls} /></dd></div>
            <div><dt>Duplicate incidents</dt><dd><MetricValue status={metricStatus(summary, "duplicate_call_incidents")} value={summary.duplicate_call_incidents} /></dd></div>
            <div><dt>Seller complaints</dt><dd><MetricValue status={metricStatus(summary, "seller_complaints")} value={summary.seller_complaints} /></dd></div>
            <div><dt>DNC requests</dt><dd><MetricValue status={metricStatus(summary, "dnc_requests")} value={summary.dnc_requests} /></dd></div>
            <div><dt>Abandoned calls</dt><dd><MetricValue status={metricStatus(summary, "abandoned_calls")} value={summary.abandoned_calls} /></dd></div>
            <div><dt>Average connection time</dt><dd><MetricValue format="seconds" status={metricStatus(summary, "average_connection_time_seconds")} value={summary.average_connection_time_seconds} /></dd></div>
            <div><dt>Number reputation</dt><dd><MetricValue format="score" status={metricStatus(summary, "number_reputation_score")} value={summary.number_reputation_score} /></dd></div>
            <div><dt>Answer-rate trend</dt><dd className={summary.answer_rate_trend_basis_points !== null && summary.answer_rate_trend_basis_points < 0 ? styles.analyticsNegative : undefined}>{summary.answer_rate_trend_basis_points !== null ? (summary.answer_rate_trend_basis_points < 0 ? <TrendingDown aria-hidden="true" size={15} /> : <TrendingUp aria-hidden="true" size={15} />) : null}<MetricValue format="trend" status={metricStatus(summary, "answer_rate_trend_basis_points")} value={summary.answer_rate_trend_basis_points} /></dd></div>
          </dl>
        </article>

        <article className={styles.analyticsSection}>
          <header><div><span>Evidence completeness</span><h2>Metric coverage</h2></div><UsersRound aria-hidden="true" size={20} /></header>
          <div className={styles.analyticsCoverageGrid}>
            <CoverageCard label="Raw attempts" value={coverage.raw_attempts_basis_points} />
            <CoverageCard label="Paid hours" value={coverage.paid_hours_basis_points} />
            <CoverageCard label="Provider cost" value={coverage.provider_cost_basis_points} />
            <CoverageCard label="Appointment outcomes" value={coverage.appointment_outcomes_basis_points} />
            <CoverageCard label="Profit attribution" value={coverage.profit_basis_points} />
            <CoverageCard label="Number reputation" value={coverage.reputation_basis_points} />
          </div>
          {coverage.warnings.length ? <ul className={styles.analyticsWarningList}>{coverage.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : <p className={styles.analyticsMeasuredNote}><CheckCircle2 aria-hidden="true" size={16} /> No coverage warnings were reported for this view.</p>}
        </article>
      </section>

      <section className={styles.analyticsSection}>
        <header><div><span>Daily movement</span><h2>Volume and answer quality</h2></div><span className={styles.statusNeutral}>{data.daily_trend.length} UTC days</span></header>
        {data.daily_trend.length ? (
          <div aria-label="Daily prospecting trend" className={styles.analyticsTableWrap} tabIndex={0}>
            <table><thead><tr><th scope="col">Date</th><th scope="col">Attempts</th><th scope="col">Human conversations</th><th scope="col">Right-party</th><th scope="col">Accepted handoffs</th><th scope="col">Answer rate</th><th scope="col">Blocked / failed</th></tr></thead><tbody>{data.daily_trend.map((point) => <tr key={point.date}><th scope="row">{formatUtcDate(point.date)}</th><td><MetricValue value={point.attempts} /></td><td><MetricValue value={point.human_conversations} /></td><td><MetricValue value={point.right_party_contacts} /></td><td><MetricValue value={point.accepted_handoffs} /></td><td><MetricValue format="percent" value={point.answer_rate_basis_points} /></td><td><MetricValue value={point.blocked_or_failed_calls} /></td></tr>)}</tbody></table>
          </div>
        ) : <p className={styles.dialerEmptyState}>No daily trend evidence is available for this date range.</p>}
      </section>

      <section className={styles.analyticsSection}>
        <header><div><span>Technical gates</span><h2>Controlled-pilot readiness</h2></div><span className={data.readiness.status === "ready_for_controlled_pilot" ? styles.statusGood : data.readiness.status === "blocked" ? styles.analyticsStatusBlocked : styles.statusWarning}>{readiness.label}</span></header>
        <p className={styles.analyticsSectionDescription}>These checks cover technical readiness only. They do not replace the D10 owner review, controlled shifts, billing verification, or production acceptance.</p>
        {data.readiness.blockers.length ? <div className={styles.analyticsBlockerBox}><AlertTriangle aria-hidden="true" size={18} /><div><strong>Blocking issues</strong><ul>{data.readiness.blockers.map((item) => <li key={item}>{item}</li>)}</ul></div></div> : null}
        {data.readiness.warnings.length ? <div className={styles.analyticsWarningBox}><AlertTriangle aria-hidden="true" size={18} /><div><strong>Review before pilot</strong><ul>{data.readiness.warnings.map((item) => <li key={item}>{item}</li>)}</ul></div></div> : null}
        <div className={styles.analyticsReadinessGrid}>
          {data.readiness.checks.map((check) => {
            const Icon = check.status === "pass" ? CheckCircle2 : check.status === "block" ? CircleSlash2 : AlertTriangle;
            return <article className={check.status === "pass" ? styles.analyticsCheckPass : check.status === "block" ? styles.analyticsCheckBlock : styles.analyticsCheckWarning} key={check.key}><Icon aria-hidden="true" size={18} /><div><strong>{check.label}</strong><p>{check.detail}</p></div><span>{labelize(check.status)}</span></article>;
          })}
          {!data.readiness.checks.length ? <p className={styles.dialerEmptyState}>Readiness checks are unavailable. Do not treat the dialer as pilot ready.</p> : null}
        </div>
      </section>

      <details className={styles.analyticsDefinitions}>
        <summary>How these metrics are calculated</summary>
        <div>
          <p className={styles.analyticsDefinitionMeta}>
            Attribution model: {data.attribution_model_version ?? "not reported"} | Profit formula: {data.profit_formula_version ?? "not reported"}
          </p>
          {data.metric_definitions.map((definition) => <article key={definition.key}><strong>{definition.label}</strong><p>{definition.definition}</p><dl><div><dt>Source records</dt><dd>{definition.source_records.length ? definition.source_records.join(", ") : "Not specified"}</dd></div><div><dt>Attributed at</dt><dd>{labelize(definition.attribution_timestamp)}</dd></div><div><dt>Unavailable when</dt><dd>{definition.unavailable_when ?? "No additional unavailability rule"}</dd></div></dl></article>)}
          {!data.metric_definitions.length ? <p className={styles.dialerEmptyState}>Metric definitions were not returned. Treat ambiguous values as unavailable.</p> : null}
        </div>
      </details>
    </div>
  );
}
