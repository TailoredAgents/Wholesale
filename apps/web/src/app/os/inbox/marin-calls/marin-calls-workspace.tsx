"use client";

import { useAuth } from "@clerk/nextjs";
import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  CalendarClock,
  Check,
  CheckCircle2,
  Clock3,
  ExternalLink,
  Flag,
  PhoneIncoming,
  RefreshCw,
  Search,
  UserRound,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import styles from "./marin-calls.module.css";

type ReviewFlag =
  | "awkward_wording"
  | "interruption"
  | "wrong_information"
  | "missed_intent"
  | "poor_qualification"
  | "failed_transfer"
  | "technical_failure"
  | "privacy_or_compliance";

type Review = {
  status: "unreviewed" | "reviewed" | "flagged" | "resolved";
  flags: ReviewFlag[];
  notes: string | null;
  reviewed_by_user_id: string | null;
  reviewer_name: string | null;
  reviewed_at: string | null;
};

type MarinCall = {
  id: string;
  call_record_id: string | null;
  caller_number: string;
  seller_name: string | null;
  property_address: string | null;
  lead_id: string | null;
  status: string;
  outcome: string;
  summary: string | null;
  received_at: string;
  answered_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  transcript_available: boolean;
  transcript_turn_count: number;
  model: string | null;
  voice: string | null;
  prompt_version: string | null;
  error: string | null;
  needs_review: boolean;
  review_reasons: string[];
  review: Review;
};

type MarinCallDetail = MarinCall & {
  transcript: Array<{ speaker: "caller" | "marin"; text: string }>;
  captured_details: Record<string, unknown>;
  tool_events: Array<{ name: string; succeeded: boolean; occurred_at: string | null }>;
  callback_at: string | null;
  callback_reason: string | null;
  transfer_number: string | null;
};

type MarinStats = {
  timezone: string;
  total_calls: number;
  total_unique_callers: number;
  calls_today: number;
  calls_7_days: number;
  calls_30_days: number;
  unique_callers_30_days: number;
  repeat_callers_30_days: number;
  completed_calls_30_days: number;
  failed_calls_30_days: number;
  transferred_calls_30_days: number;
  scheduled_callbacks_30_days: number;
  interested_calls_30_days: number;
  leads_created_30_days: number;
  needs_review: number;
  average_duration_seconds_30_days: number | null;
};

type Dashboard = {
  items: MarinCall[];
  total: number;
  stats: MarinStats;
  generated_at: string;
};

type FilterKey = "all" | "needs_review" | "unreviewed" | "flagged" | "failed";

const flagOptions: Array<{ key: ReviewFlag; label: string }> = [
  { key: "awkward_wording", label: "Awkward wording" },
  { key: "interruption", label: "Interrupted caller" },
  { key: "wrong_information", label: "Wrong information" },
  { key: "missed_intent", label: "Missed caller intent" },
  { key: "poor_qualification", label: "Poor qualification" },
  { key: "failed_transfer", label: "Transfer problem" },
  { key: "technical_failure", label: "Technical failure" },
  { key: "privacy_or_compliance", label: "Privacy or compliance" },
];

const detailLabels: Record<string, string> = {
  seller_name: "Seller",
  street_address: "Property",
  city: "City",
  state: "State",
  postal_code: "ZIP",
  property_type: "Property type",
  occupancy_status: "Occupancy",
  property_condition: "Condition",
  desired_timeline: "Timeline",
  motivation: "Motivation",
  asking_price: "Asking price",
  notes: "Notes",
};

async function responseError(response: Response) {
  const fallback = `Request failed (${response.status}).`;
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail || fallback;
  } catch {
    return fallback;
  }
}

function formatDateTime(value: string | null) {
  if (!value) return "Not recorded";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatShortDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatDuration(seconds: number | null) {
  if (seconds === null) return "Not available";
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return minutes ? `${minutes}m ${remainder}s` : `${remainder}s`;
}

function labelize(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function reviewLabel(review: Review) {
  if (review.status === "unreviewed") return "Not reviewed";
  return labelize(review.status);
}

export function MarinCallsWorkspace() {
  const { getToken } = useAuth();
  const apiBase = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () =>
      process.env.NEXT_PUBLIC_DEV_USER_EMAIL ??
      "richardaustindugger@users.noreply.github.com",
    [],
  );
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<MarinCallDetail | null>(null);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewFlags, setReviewFlags] = useState<ReviewFlag[]>([]);
  const [reviewNotes, setReviewNotes] = useState("");

  const authHeaders = useCallback(
    async (json = false) => {
      const headers: Record<string, string> = { Accept: "application/json" };
      const token = await getToken().catch(() => null);
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;
      if (json) headers["Content-Type"] = "application/json";
      return headers;
    },
    [devUserEmail, getToken],
  );

  const loadDashboard = useCallback(
    async (quiet = false) => {
      if (!quiet) setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${apiBase}/api/v1/voice/marin-calls?days=30&limit=200`, {
          cache: "no-store",
          headers: await authHeaders(),
        });
        if (!response.ok) throw new Error(await responseError(response));
        const payload = (await response.json()) as Dashboard;
        setDashboard(payload);
        if (payload.items.length === 0) setDetail(null);
        setSelectedId((current) =>
          current && payload.items.some((item) => item.id === current)
            ? current
            : payload.items[0]?.id ?? null,
        );
      } catch (failure) {
        setError(failure instanceof Error ? failure.message : "Unable to load Marin calls.");
      } finally {
        if (!quiet) setLoading(false);
      }
    },
    [apiBase, authHeaders],
  );

  const loadDetail = useCallback(
    async (callbackId: string, signal?: AbortSignal) => {
      setDetailLoading(true);
      setError(null);
      try {
        const response = await fetch(`${apiBase}/api/v1/voice/marin-calls/${callbackId}`, {
          cache: "no-store",
          headers: await authHeaders(),
          signal,
        });
        if (!response.ok) throw new Error(await responseError(response));
        const payload = (await response.json()) as MarinCallDetail;
        setDetail(payload);
        setReviewFlags(payload.review.flags);
        setReviewNotes(payload.review.notes ?? "");
      } catch (failure) {
        if (failure instanceof DOMException && failure.name === "AbortError") return;
        setError(failure instanceof Error ? failure.message : "Unable to load this call.");
      } finally {
        if (!signal?.aborted) setDetailLoading(false);
      }
    },
    [apiBase, authHeaders],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => void loadDashboard(), 0);
    return () => window.clearTimeout(timer);
  }, [loadDashboard]);

  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => void loadDetail(selectedId, controller.signal), 0);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [loadDetail, selectedId]);

  useEffect(() => {
    const timer = window.setInterval(() => void loadDashboard(true), 30_000);
    return () => window.clearInterval(timer);
  }, [loadDashboard]);

  const visibleCalls = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (dashboard?.items ?? []).filter((item) => {
      const matchesFilter =
        filter === "all" ||
        (filter === "needs_review" && item.needs_review) ||
        (filter === "unreviewed" && item.review.status === "unreviewed") ||
        (filter === "flagged" && item.review.status === "flagged") ||
        (filter === "failed" && item.status === "failed");
      if (!matchesFilter) return false;
      if (!query) return true;
      return [item.caller_number, item.seller_name, item.property_address, item.summary]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query));
    });
  }, [dashboard?.items, filter, search]);

  async function saveReview(status: "reviewed" | "flagged" | "resolved") {
    if (!detail || saving) return;
    const flags = status === "reviewed" ? [] : reviewFlags;
    if (status === "flagged" && flags.length === 0) {
      setError("Choose at least one issue before flagging this call.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const response = await fetch(`${apiBase}/api/v1/voice/marin-calls/${detail.id}/review`, {
        method: "PATCH",
        headers: await authHeaders(true),
        body: JSON.stringify({ status, flags, notes: reviewNotes.trim() || null }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const payload = (await response.json()) as MarinCallDetail;
      setDetail(payload);
      setReviewFlags(payload.review.flags);
      setReviewNotes(payload.review.notes ?? "");
      setDashboard((current) =>
        current
          ? {
              ...current,
              items: current.items.map((item) => (item.id === payload.id ? payload : item)),
            }
          : current,
      );
      void loadDashboard(true);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Unable to save this review.");
    } finally {
      setSaving(false);
    }
  }

  function toggleFlag(flag: ReviewFlag) {
    setReviewFlags((current) =>
      current.includes(flag) ? current.filter((item) => item !== flag) : [...current, flag],
    );
  }

  const capturedDetails = detail
    ? Object.entries(detail.captured_details).filter(
        ([key, value]) => detailLabels[key] && value !== null && value !== "" && value !== false,
      )
    : [];

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <p className={styles.eyebrow}>Seller communications / quality</p>
          <h1>Marin Calls</h1>
          <p>See every caller, inspect the conversation, and record exactly what needs improvement.</p>
        </div>
        <div className={styles.headerActions}>
          <Link className={styles.secondaryAction} href="/os/inbox">
            <ArrowLeft size={16} aria-hidden="true" />
            Inbox
          </Link>
          <button
            className={styles.primaryAction}
            onClick={() => {
              void loadDashboard();
              if (selectedId) void loadDetail(selectedId);
            }}
            type="button"
          >
            <RefreshCw size={16} aria-hidden="true" />
            Refresh
          </button>
        </div>
      </header>

      {error ? (
        <div className={styles.errorBanner} role="alert">
          <AlertTriangle size={17} aria-hidden="true" />
          <span>{error}</span>
          <button aria-label="Dismiss error" onClick={() => setError(null)} type="button">
            <Check size={16} aria-hidden="true" />
          </button>
        </div>
      ) : null}

      <section className={styles.statsGrid} aria-label="Marin call activity">
        <article>
          <PhoneIncoming size={17} aria-hidden="true" />
          <span>Today</span>
          <strong>{dashboard?.stats.calls_today ?? 0}</strong>
          <small>{dashboard?.stats.timezone ?? "America/New_York"}</small>
        </article>
        <article>
          <CalendarClock size={17} aria-hidden="true" />
          <span>Last 7 days</span>
          <strong>{dashboard?.stats.calls_7_days ?? 0}</strong>
          <small>{dashboard?.stats.calls_30_days ?? 0} in 30 days</small>
        </article>
        <article>
          <Users size={17} aria-hidden="true" />
          <span>Unique callers</span>
          <strong>{dashboard?.stats.unique_callers_30_days ?? 0}</strong>
          <small>{dashboard?.stats.repeat_callers_30_days ?? 0} repeat callers</small>
        </article>
        <article>
          <UserRound size={17} aria-hidden="true" />
          <span>Seller results</span>
          <strong>{dashboard?.stats.interested_calls_30_days ?? 0}</strong>
          <small>{dashboard?.stats.leads_created_30_days ?? 0} leads created</small>
        </article>
        <article>
          <ExternalLink size={17} aria-hidden="true" />
          <span>Human handoffs</span>
          <strong>{dashboard?.stats.transferred_calls_30_days ?? 0}</strong>
          <small>{dashboard?.stats.scheduled_callbacks_30_days ?? 0} callbacks booked</small>
        </article>
        <article data-alert={(dashboard?.stats.needs_review ?? 0) > 0}>
          <Flag size={17} aria-hidden="true" />
          <span>Needs review</span>
          <strong>{dashboard?.stats.needs_review ?? 0}</strong>
          <small>{dashboard?.stats.failed_calls_30_days ?? 0} technical failures</small>
        </article>
      </section>

      <section className={styles.workspace}>
        <aside className={styles.callRail} aria-label="Marin call list">
          <div className={styles.railHeader}>
            <div>
              <p>Recent calls</p>
              <strong>{dashboard?.total ?? 0} in this period</strong>
            </div>
            {loading ? <RefreshCw className={styles.spin} size={16} aria-label="Loading" /> : null}
          </div>
          <label className={styles.searchBox}>
            <Search size={15} aria-hidden="true" />
            <span className={styles.visuallyHidden}>Search Marin calls</span>
            <input
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search caller, seller, or property"
              type="search"
              value={search}
            />
          </label>
          <div className={styles.filters} aria-label="Filter calls">
            {(
              [
                ["all", "All"],
                ["needs_review", "Needs review"],
                ["unreviewed", "Unreviewed"],
                ["flagged", "Flagged"],
                ["failed", "Failed"],
              ] as Array<[FilterKey, string]>
            ).map(([key, label]) => (
              <button
                aria-pressed={filter === key}
                data-active={filter === key}
                key={key}
                onClick={() => setFilter(key)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
          <div className={styles.callList}>
            {!loading && visibleCalls.length === 0 ? (
              <div className={styles.emptyList}>
                <Bot size={22} aria-hidden="true" />
                <strong>No calls in this view</strong>
                <span>Try another filter or clear the search.</span>
              </div>
            ) : null}
            {visibleCalls.map((call) => (
              <button
                className={styles.callRow}
                data-active={selectedId === call.id}
                key={call.id}
                onClick={() => setSelectedId(call.id)}
                type="button"
              >
                <span className={styles.callRowTop}>
                  <strong>{call.seller_name || call.caller_number}</strong>
                  <time dateTime={call.received_at}>{formatShortDate(call.received_at)}</time>
                </span>
                <span className={styles.callRowAddress}>
                  {call.property_address || (call.seller_name ? call.caller_number : "Identity not captured")}
                </span>
                <span className={styles.callRowBottom}>
                  <span data-outcome={call.outcome}>{labelize(call.outcome)}</span>
                  <small>{formatDuration(call.duration_seconds)}</small>
                  {call.needs_review ? <em>Review</em> : null}
                </span>
              </button>
            ))}
          </div>
          <footer className={styles.railFooter}>
            <span>{dashboard?.stats.total_calls ?? 0} calls all time</span>
            <span>{dashboard?.stats.total_unique_callers ?? 0} people</span>
          </footer>
        </aside>

        <main className={styles.detailPane}>
          {!detail && !detailLoading ? (
            <div className={styles.emptyDetail}>
              <Bot size={28} aria-hidden="true" />
              <strong>Select a Marin call</strong>
              <span>The transcript and quality review will appear here.</span>
            </div>
          ) : null}
          {detailLoading ? (
            <div className={styles.emptyDetail}>
              <RefreshCw className={styles.spin} size={22} aria-hidden="true" />
              <strong>Loading conversation</strong>
            </div>
          ) : null}
          {detail && !detailLoading ? (
            <>
              <header className={styles.detailHeader}>
                <div>
                  <p>Inbound seller callback</p>
                  <h2>{detail.seller_name || detail.caller_number}</h2>
                  <span>{detail.property_address || detail.caller_number}</span>
                </div>
                <div className={styles.detailHeaderActions}>
                  <span data-status={detail.review.status}>{reviewLabel(detail.review)}</span>
                  {detail.lead_id ? (
                    <Link href={`/os/leads/${detail.lead_id}`}>
                      Open lead <ExternalLink size={13} aria-hidden="true" />
                    </Link>
                  ) : null}
                </div>
              </header>

              {detail.needs_review ? (
                <div className={styles.reviewAlert}>
                  <AlertTriangle size={17} aria-hidden="true" />
                  <div>
                    <strong>Review recommended</strong>
                    <span>{detail.review_reasons.join(" · ")}</span>
                  </div>
                </div>
              ) : null}

              <div className={styles.detailColumns}>
                <section className={styles.transcriptColumn} aria-label="Call transcript">
                  <div className={styles.callSummary}>
                    <div>
                      <span>Result</span>
                      <strong>{labelize(detail.outcome)}</strong>
                    </div>
                    <div>
                      <span>Received</span>
                      <strong>{formatDateTime(detail.received_at)}</strong>
                    </div>
                    <div>
                      <span>Duration</span>
                      <strong>{formatDuration(detail.duration_seconds)}</strong>
                    </div>
                    <div>
                      <span>Agent version</span>
                      <strong>{detail.prompt_version || "Not recorded"}</strong>
                    </div>
                  </div>

                  {detail.summary ? (
                    <div className={styles.summaryNote}>
                      <span>Marin’s summary</span>
                      <p>{detail.summary}</p>
                    </div>
                  ) : null}

                  <div className={styles.sectionHeading}>
                    <div>
                      <p>Conversation</p>
                      <h3>Caller and Marin transcript</h3>
                    </div>
                    <span>{detail.transcript.length} turns</span>
                  </div>
                  <div className={styles.transcript}>
                    {detail.transcript.length === 0 ? (
                      <div className={styles.transcriptEmpty}>
                        <AlertTriangle size={18} aria-hidden="true" />
                        <span>No transcript was captured for this call.</span>
                      </div>
                    ) : null}
                    {detail.transcript.map((turn, index) => (
                      <div className={styles.transcriptTurn} data-speaker={turn.speaker} key={`${turn.speaker}-${index}`}>
                        <strong>{turn.speaker === "caller" ? "Caller" : "Marin"}</strong>
                        <p>{turn.text}</p>
                      </div>
                    ))}
                  </div>
                  <p className={styles.transcriptNotice}>
                    Realtime transcripts are review aids and may not exactly match what the caller said.
                  </p>
                </section>

                <aside className={styles.reviewPane} aria-label="Marin quality review">
                  <section>
                    <div className={styles.sectionHeading}>
                      <div>
                        <p>Human review</p>
                        <h3>What should Marin improve?</h3>
                      </div>
                    </div>
                    <div className={styles.flagGrid}>
                      {flagOptions.map((option) => (
                        <label key={option.key} data-selected={reviewFlags.includes(option.key)}>
                          <input
                            checked={reviewFlags.includes(option.key)}
                            onChange={() => toggleFlag(option.key)}
                            type="checkbox"
                          />
                          <span>{option.label}</span>
                        </label>
                      ))}
                    </div>
                    <label className={styles.notesField}>
                      <span>Reviewer notes</span>
                      <textarea
                        onChange={(event) => setReviewNotes(event.target.value)}
                        placeholder="What happened, and what should Marin do differently?"
                        rows={5}
                        value={reviewNotes}
                      />
                    </label>
                    <div className={styles.reviewActions}>
                      <button
                        disabled={saving}
                        onClick={() => void saveReview(reviewFlags.length ? "flagged" : "reviewed")}
                        type="button"
                      >
                        {reviewFlags.length ? <Flag size={14} aria-hidden="true" /> : <CheckCircle2 size={14} aria-hidden="true" />}
                        {saving ? "Saving" : reviewFlags.length ? "Save issue" : "Mark reviewed"}
                      </button>
                      {detail.review.status === "flagged" ? (
                        <button
                          className={styles.resolveButton}
                          disabled={saving}
                          onClick={() => void saveReview("resolved")}
                          type="button"
                        >
                          <Check size={14} aria-hidden="true" />
                          Resolve
                        </button>
                      ) : null}
                    </div>
                    {detail.review.reviewed_at ? (
                      <p className={styles.reviewHistory}>
                        {reviewLabel(detail.review)} by {detail.review.reviewer_name || "Stonegate staff"} on {formatDateTime(detail.review.reviewed_at)}
                      </p>
                    ) : null}
                  </section>

                  {capturedDetails.length ? (
                    <section>
                      <div className={styles.sectionHeading}>
                        <div>
                          <p>CRM capture</p>
                          <h3>Seller details</h3>
                        </div>
                      </div>
                      <dl className={styles.capturedDetails}>
                        {capturedDetails.map(([key, value]) => (
                          <div key={key}>
                            <dt>{detailLabels[key]}</dt>
                            <dd>{String(value)}</dd>
                          </div>
                        ))}
                      </dl>
                    </section>
                  ) : null}

                  {detail.tool_events.length ? (
                    <section>
                      <div className={styles.sectionHeading}>
                        <div>
                          <p>System activity</p>
                          <h3>Actions Marin took</h3>
                        </div>
                      </div>
                      <ul className={styles.toolEvents}>
                        {detail.tool_events.map((event, index) => (
                          <li key={`${event.name}-${index}`}>
                            {event.succeeded ? (
                              <CheckCircle2 size={14} aria-hidden="true" />
                            ) : (
                              <AlertTriangle size={14} aria-hidden="true" />
                            )}
                            <span>
                              <strong>{labelize(event.name)}</strong>
                              <small>{formatDateTime(event.occurred_at)}</small>
                            </span>
                          </li>
                        ))}
                      </ul>
                    </section>
                  ) : null}

                  <section className={styles.technicalDetails}>
                    <div>
                      <Clock3 size={14} aria-hidden="true" />
                      <span>{detail.model || "Realtime model not recorded"}</span>
                    </div>
                    <div>
                      <Bot size={14} aria-hidden="true" />
                      <span>{detail.voice ? `${labelize(detail.voice)} voice` : "Voice not recorded"}</span>
                    </div>
                  </section>
                </aside>
              </div>
            </>
          ) : null}
        </main>
      </section>
    </div>
  );
}
