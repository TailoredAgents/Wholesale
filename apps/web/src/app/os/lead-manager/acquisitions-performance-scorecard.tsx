"use client";

import { useAuth } from "@clerk/nextjs";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  RefreshCw,
  ShieldCheck,
  Target,
  UsersRound,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  AcquisitionsPerformanceDimension,
  AcquisitionsPerformanceOverview,
  AcquisitionsPerformanceScorecard as PerformanceScorecard,
} from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./acquisitions-performance-scorecard.module.css";

type PeriodDays = 30 | 90;

const REQUEST_TIMEOUT_MS = 12_000;
const numberFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
const integerFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const evidenceNumberFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 });

function formatScore(value: number | null) {
  return value === null ? "Unavailable" : numberFormatter.format(value);
}

function formatBasisPoints(value: number) {
  return `${numberFormatter.format(value / 100)}%`;
}

function formatWeight(value: number) {
  return `${numberFormatter.format(value / 100)}%`;
}

function formatPeriodDate(value: string) {
  const parsed = new Date(value.includes("T") ? value : `${value}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(parsed);
}

function formatSnapshotTimestamp(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(parsed);
}

function dimensionScore(dimension: AcquisitionsPerformanceDimension) {
  return dimension.status === "ready" ? dimension.score : null;
}

function dimensionScoreLabel(dimension: AcquisitionsPerformanceDimension) {
  if (dimension.status === "building") return "Building";
  return formatScore(dimensionScore(dimension));
}

function measuredEvidenceLabel(dimension: AcquisitionsPerformanceDimension) {
  if (dimension.status === "building") {
    return "Numeric score withheld until the minimum sample is reached.";
  }
  return dimension.display_value || "No measured value available.";
}

function evidenceOperands(dimension: AcquisitionsPerformanceDimension) {
  if (dimension.numerator === null || dimension.denominator === null) return null;
  const numerator = evidenceNumberFormatter.format(dimension.numerator);
  const denominator = evidenceNumberFormatter.format(dimension.denominator);

  switch (dimension.key) {
    case "speed_to_lead":
      return `${numerator} timing points / ${denominator} possible timing points`;
    case "follow_up_discipline":
      return `${numerator} on-time completions / ${denominator} due follow-ups`;
    case "conversation_quality":
      return `${numerator} total score points / ${denominator} reviewed calls`;
    case "qualification_quality":
      return `${numerator} total score points / ${denominator} completed qualifications`;
    case "crm_hygiene":
      return `${numerator} completed checks / ${denominator} eligible checks`;
    case "appointment_execution":
      return `${numerator} documented outcomes / ${denominator} matured appointments`;
    case "mature_outcomes":
      return `${numerator} successful credited share / ${denominator} matured credited share`;
  }
}

function statusTone(status: string) {
  const normalized = status.toLowerCase();
  if (
    normalized.includes("ready") ||
    normalized.includes("reliable") ||
    normalized.includes("sufficient") ||
    normalized.includes("high")
  ) {
    return styles.statusGood;
  }
  if (
    normalized.includes("provisional") ||
    normalized.includes("partial") ||
    normalized.includes("medium") ||
    normalized.includes("limited")
  ) {
    return styles.statusCaution;
  }
  return styles.statusMuted;
}

function dimensionLabelMap(scorecards: PerformanceScorecard[]): Map<string, string> {
  return new Map<string, string>(
    scorecards.flatMap((scorecard) =>
      scorecard.dimensions.map((dimension) => [dimension.key, dimension.label] as const),
    ),
  );
}

function EvidenceStatus({ status }: { status: string }) {
  return (
    <span className={`${styles.statusBadge} ${statusTone(status)}`}>
      {labelize(status)}
    </span>
  );
}

function DimensionBar({ dimension }: { dimension: AcquisitionsPerformanceDimension }) {
  const score = dimensionScore(dimension);
  const barWidth = score === null ? 0 : Math.min(100, Math.max(0, score));
  const scoreClass =
    dimension.status === "building"
      ? styles.building
      : score === null
        ? styles.unavailable
        : styles.dimensionScore;

  return (
    <div className={styles.dimension}>
      <div className={styles.dimensionHeading}>
        <div>
          <strong>{dimension.label}</strong>
          <span>{formatWeight(dimension.weight_basis_points)} weight</span>
        </div>
        <strong className={scoreClass}>
          {dimensionScoreLabel(dimension)}{score === null ? "" : "/100"}
        </strong>
      </div>
      <div
        aria-label={`${dimension.label} score`}
        aria-valuemax={score === null ? undefined : 100}
        aria-valuemin={score === null ? undefined : 0}
        aria-valuenow={score === null ? undefined : score}
        className={`${styles.scoreTrack} ${score === null ? styles.scoreTrackUnavailable : ""}`}
        role={score === null ? undefined : "progressbar"}
      >
        <span style={{ width: `${barWidth}%` }} />
      </div>
      <div className={styles.dimensionEvidence}>
        <EvidenceStatus status={dimension.status} />
        <span>
          {integerFormatter.format(dimension.sample_size)} observed
          {dimension.minimum_sample_size > 0
            ? ` / ${integerFormatter.format(dimension.minimum_sample_size)} needed`
            : ""}
        </span>
      </div>
      <p>{measuredEvidenceLabel(dimension)}</p>
      {dimension.detail ? <small>{dimension.detail}</small> : null}
    </div>
  );
}

function RepScorecard({ scorecard }: { scorecard: PerformanceScorecard }) {
  return (
    <article className={styles.repCard}>
      <header className={styles.repHeader}>
        <div>
          <span>Acquisitions specialist</span>
          <h3>{scorecard.user_name}</h3>
          <EvidenceStatus status={scorecard.reliability_status} />
        </div>
        <div className={styles.overallScore}>
          <strong className={scorecard.overall_score === null ? styles.unavailable : undefined}>
            {formatScore(scorecard.overall_score)}
          </strong>
          {scorecard.overall_score === null ? null : <span>/100</span>}
          <small>Overall</small>
        </div>
      </header>

      <div className={styles.coverage}>
        <div>
          <span>Evidence coverage</span>
          <strong>{formatBasisPoints(scorecard.coverage_basis_points)}</strong>
        </div>
        <div
          aria-label={`${scorecard.user_name} evidence coverage`}
          aria-valuemax={100}
          aria-valuemin={0}
          aria-valuenow={scorecard.coverage_basis_points / 100}
          className={styles.coverageTrack}
          role="progressbar"
        >
          <span
            style={{
              width: `${Math.min(100, Math.max(0, scorecard.coverage_basis_points / 100))}%`,
            }}
          />
        </div>
      </div>

      <section className={styles.dimensionList} aria-label={`${scorecard.user_name} weighted dimensions`}>
        {scorecard.dimensions.length ? (
          scorecard.dimensions.map((dimension) => (
            <DimensionBar dimension={dimension} key={dimension.key} />
          ))
        ) : (
          <p className={styles.empty}>No dimension evidence is available for this period.</p>
        )}
      </section>

      <div className={styles.coachingGrid}>
        <section>
          <h4><CheckCircle2 size={16} />Evidence-backed strengths</h4>
          {scorecard.strengths.length ? (
            <ul>{scorecard.strengths.map((item) => <li key={item}>{item}</li>)}</ul>
          ) : (
            <p>No confirmed strength yet; more evidence may be needed.</p>
          )}
        </section>
        <section>
          <h4><Target size={16} />Coaching focus</h4>
          {scorecard.focus_areas.length ? (
            <ul>{scorecard.focus_areas.map((item) => <li key={item}>{item}</li>)}</ul>
          ) : (
            <p>No coaching focus was identified for this period.</p>
          )}
        </section>
      </div>

      {scorecard.warnings.length ? (
        <div className={styles.cardWarnings}>
          {scorecard.warnings.map((warning) => (
            <p key={warning}><AlertTriangle size={15} />{warning}</p>
          ))}
        </div>
      ) : null}
    </article>
  );
}

export function AcquisitionsPerformanceScorecard() {
  const { getToken, isLoaded } = useAuth();
  const [periodDays, setPeriodDays] = useState<PeriodDays>(30);
  const [data, setData] = useState<AcquisitionsPerformanceOverview | null>(null);
  const [attemptedPeriodDays, setAttemptedPeriodDays] = useState<PeriodDays | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const mountedRef = useRef(true);
  const dataRef = useRef<AcquisitionsPerformanceOverview | null>(null);
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

  const loadPerformance = useCallback(async () => {
    if (!isLoaded) return;
    const requestSequence = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestSequence;
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    let didTimeout = false;
    let timeoutId: number | null = null;
    const timeoutTask = new Promise<never>((_, reject) => {
      timeoutId = window.setTimeout(() => {
        didTimeout = true;
        controller.abort();
        reject(new Error("The acquisitions performance request exceeded its 12-second limit."));
      }, REQUEST_TIMEOUT_MS);
    });
    const priorSnapshotVisible = dataRef.current?.period_days === periodDays;
    setAttemptedPeriodDays(periodDays);
    setLoading(true);
    setError("");
    setAnnouncement(
      priorSnapshotVisible ? `Refreshing the ${periodDays}-day performance snapshot.` : "",
    );

    try {
      const requestTask = (async () => {
        const token = await getToken().catch(() => null);
        const headers: Record<string, string> = { Accept: "application/json" };
        if (token) headers.Authorization = `Bearer ${token}`;
        else headers["X-Dev-User-Email"] = devUserEmail;
        const query = new URLSearchParams({ period_days: String(periodDays) });
        const response = await fetch(
          `${apiBaseUrl}/api/v1/lead-manager/performance?${query.toString()}`,
          { cache: "no-store", headers, signal: controller.signal },
        );
        const payload = (await response.json().catch(() => null)) as
          | AcquisitionsPerformanceOverview
          | { detail?: string }
          | null;

        if (response.status === 401 || response.status === 403) {
          return { accessDenied: true as const, payload: null };
        }
        if (!response.ok || !payload || !("scorecards" in payload)) {
          throw new Error(
            payload && "detail" in payload && payload.detail
              ? payload.detail
              : "The acquisitions performance report could not be loaded.",
          );
        }
        return { accessDenied: false as const, payload };
      })();
      const result = await Promise.race([requestTask, timeoutTask]);

      if (result.accessDenied) {
        if (mountedRef.current && requestSequence === requestSequenceRef.current) {
          dataRef.current = null;
          setData(null);
          setError("Your performance-report access expired or was removed.");
          setAnnouncement("");
        }
        return;
      }
      if (mountedRef.current && requestSequence === requestSequenceRef.current) {
        dataRef.current = result.payload;
        setData(result.payload);
        setAnnouncement(
          `${periodDays}-day performance snapshot refreshed. Generated ${formatSnapshotTimestamp(result.payload.period_end)}.`,
        );
      }
    } catch (requestError) {
      if (mountedRef.current && requestSequence === requestSequenceRef.current) {
        if (didTimeout) {
          setError(
            priorSnapshotVisible
              ? "The performance request timed out. The prior confirmed snapshot remains visible."
              : `The performance request timed out before a ${periodDays}-day snapshot could be confirmed.`,
          );
        } else if (requestError instanceof Error && requestError.name !== "AbortError") {
          setError(requestError.message);
        }
        setAnnouncement("");
      }
    } finally {
      if (timeoutId !== null) window.clearTimeout(timeoutId);
      if (mountedRef.current && requestSequence === requestSequenceRef.current) {
        setLoading(false);
      }
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null;
      }
    }
  }, [apiBaseUrl, devUserEmail, getToken, isLoaded, periodDays]);

  useEffect(() => {
    const scheduledLoad = window.setTimeout(() => {
      void loadPerformance();
    }, 0);
    return () => window.clearTimeout(scheduledLoad);
  }, [loadPerformance]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      requestSequenceRef.current += 1;
      requestControllerRef.current?.abort();
    };
  }, []);

  const confirmedData = data?.period_days === periodDays ? data : null;
  const periodRequestAttempted = attemptedPeriodDays === periodDays;
  const requestPending = !isLoaded || !periodRequestAttempted || loading;
  const dimensionLabels = useMemo(
    () => dimensionLabelMap(confirmedData?.scorecards ?? []),
    [confirmedData?.scorecards],
  );
  const rawRows = useMemo(
    () => (confirmedData?.scorecards ?? []).flatMap((scorecard) =>
      scorecard.dimensions.map((dimension) => ({ dimension, scorecard })),
    ),
    [confirmedData?.scorecards],
  );

  return (
    <section
      aria-busy={requestPending}
      aria-label="Acquisitions performance scorecard"
      className={styles.workspace}
    >
      <p aria-atomic="true" aria-live="polite" className={styles.srOnly} role="status">
        {announcement}
      </p>
      <header className={styles.header}>
        <div className={styles.headerCopy}>
          <span><BarChart3 size={15} />Governed sales coaching</span>
          <h2>Acquisitions performance</h2>
          <p>
            Compare speed, follow-up, conversation quality, and outcomes using auditable
            Stonegate evidence. Missing evidence stays unavailable instead of becoming a zero.
          </p>
        </div>
        <div className={styles.controls}>
          <div aria-label="Performance period" className={styles.periodSelector} role="group">
            {([30, 90] as const).map((days) => (
              <button
                aria-pressed={periodDays === days}
                className={periodDays === days ? styles.activePeriod : ""}
                disabled={requestPending && periodDays === days}
                key={days}
                onClick={() => setPeriodDays(days)}
                type="button"
              >
                {days} days
              </button>
            ))}
          </div>
          <button className={styles.refreshButton} disabled={requestPending} onClick={() => void loadPerformance()} type="button">
            <RefreshCw className={requestPending ? styles.spinning : ""} size={16} />
            {requestPending ? (confirmedData ? "Refreshing" : "Loading") : "Refresh"}
          </button>
        </div>
      </header>

      {error ? (
        <div className={styles.error} role="alert">
          <AlertTriangle size={17} />
          <span>{error}</span>
        </div>
      ) : null}

      {!confirmedData && requestPending ? (
        <div className={styles.loading} role="status">
          <RefreshCw className={styles.spinning} size={20} />
          <span>Building the {periodDays}-day evidence scorecard...</span>
        </div>
      ) : null}

      {!confirmedData && isLoaded && periodRequestAttempted && !loading && !error ? (
        <div className={styles.emptyState}>
          <UsersRound size={24} />
          <strong>No eligible acquisitions specialists found</strong>
          <p>Scores will appear when eligible reps and source evidence exist in this period.</p>
        </div>
      ) : null}

      {confirmedData ? (
        <>
          <div className={styles.reportMeta}>
            <div>
              <span className={confirmedData.shadow_mode ? styles.shadowBadge : styles.activeBadge}>
                <ShieldCheck size={15} />
                {confirmedData.shadow_mode ? "Shadow score" : "Active score policy"}
              </span>
              <span>
                {formatPeriodDate(confirmedData.period_start)} - {formatPeriodDate(confirmedData.period_end)}
              </span>
              <span>Snapshot generated {formatSnapshotTimestamp(confirmedData.period_end)}</span>
              <span>Policy {confirmedData.policy_version}</span>
            </div>
            <p>
              {confirmedData.shadow_mode
                ? "Shadow mode is coaching-only. It does not change lead assignment, pay, employment decisions, or automation."
                : "This scorecard is a coaching aid and should be reviewed with its evidence and reliability status."}
            </p>
          </div>

          {confirmedData.warnings.length ? (
            <div className={styles.warningList} role="status">
              <strong><AlertTriangle size={16} />Evidence notes</strong>
              {confirmedData.warnings.map((warning) => <p key={warning}>{warning}</p>)}
            </div>
          ) : null}

          {confirmedData.scorecards.length ? (
            <div className={styles.repGrid}>
              {confirmedData.scorecards.map((scorecard) => (
                <RepScorecard key={scorecard.user_id} scorecard={scorecard} />
              ))}
            </div>
          ) : (
            <div className={styles.emptyState}>
              <UsersRound size={24} />
              <strong>No scorecards are available</strong>
              <p>The report loaded, but no eligible rep had evidence in this period.</p>
            </div>
          )}

          <section className={styles.evidenceSection}>
            <div className={styles.sectionHeading}>
              <div>
                <span>Auditable inputs</span>
                <h3 id="acquisitions-raw-evidence-heading">Raw scoring evidence</h3>
              </div>
              <p>Use the sample and status columns before drawing conclusions from a score.</p>
            </div>
            {rawRows.length ? (
              <div
                aria-labelledby="acquisitions-raw-evidence-heading"
                className={styles.tableWrap}
                role="region"
                tabIndex={0}
              >
                <table>
                  <caption className={styles.srOnly}>
                    Raw acquisitions performance evidence by specialist and dimension
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Specialist</th>
                      <th scope="col">Dimension</th>
                      <th scope="col">Weight</th>
                      <th scope="col">Score</th>
                      <th scope="col">Measured evidence</th>
                      <th scope="col">Sample</th>
                      <th scope="col">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rawRows.map(({ dimension, scorecard }) => (
                      <tr key={`${scorecard.user_id}-${dimension.key}`}>
                        <th scope="row">{scorecard.user_name}</th>
                        <td>{dimension.label}</td>
                        <td>{formatWeight(dimension.weight_basis_points)}</td>
                        <td
                          className={
                            dimension.status === "building"
                              ? styles.building
                              : dimensionScore(dimension) === null
                                ? styles.unavailable
                                : undefined
                          }
                        >
                          {dimensionScoreLabel(dimension)}
                        </td>
                        <td>
                          <strong>{measuredEvidenceLabel(dimension)}</strong>
                          {evidenceOperands(dimension) ? (
                            <small>{evidenceOperands(dimension)}</small>
                          ) : null}
                        </td>
                        <td>
                          {integerFormatter.format(dimension.sample_size)}
                          <small>Minimum {integerFormatter.format(dimension.minimum_sample_size)}</small>
                        </td>
                        <td><EvidenceStatus status={dimension.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className={styles.empty}>No raw dimension evidence is available for this period.</p>
            )}
          </section>

          <details className={styles.methodology} open>
            <summary>
              <span><ShieldCheck size={17} />Methodology and weights</span>
              <small>Policy {confirmedData.policy_version}</small>
            </summary>
            <div className={styles.methodologyBody}>
              <p>
                The overall score is the evidence-weighted result of the dimensions below.
                Building dimensions with low sample sizes withhold their numeric score and do not
                enter the overall result. Unavailable evidence is not silently converted to zero.
              </p>
              <div className={styles.weightGrid}>
                {Object.entries(confirmedData.weights).map(([key, weight]) => (
                  <div key={key}>
                    <span>{dimensionLabels.get(key) ?? labelize(key)}</span>
                    <strong>{formatWeight(weight)}</strong>
                  </div>
                ))}
              </div>
              <p className={styles.methodologyNote}>
                Conversation quality is based only on recorded, reviewable call evidence. Scores
                support coaching; managers should inspect the evidence before evaluating either rep.
              </p>
            </div>
          </details>
        </>
      ) : null}
    </section>
  );
}
