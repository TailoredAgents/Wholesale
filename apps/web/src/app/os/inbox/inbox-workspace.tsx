"use client";

import { useAuth } from "@clerk/nextjs";
import {
  ArrowRightLeft,
  CalendarClock,
  Check,
  ChevronRight,
  CircleAlert,
  Clock3,
  FileText,
  Inbox,
  Mail,
  MailOpen,
  MessageSquare,
  NotebookPen,
  Phone,
  RefreshCw,
  Reply,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  UserRound,
  Users,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import styles from "./inbox.module.css";

type Me = {
  user_id: string;
  email: string;
  permissions: string[];
};

type Watcher = {
  user_id: string;
  email: string;
  display_name: string;
  source: string;
  notification_level: string;
  is_muted: boolean;
};

type Conversation = {
  id: string;
  lead_id: string;
  contact_id: string;
  seller_name: string;
  property_address: string;
  assigned_user_id: string | null;
  assigned_user_email: string | null;
  assigned_user_display_name: string | null;
  status: string;
  queue_key: string;
  priority: string;
  unread_count: number;
  last_activity_at: string | null;
  last_inbound_at: string | null;
  last_outbound_at: string | null;
  watchers: Watcher[];
  created_at: string;
  updated_at: string;
};

type TimelineItem = {
  id: string;
  item_type: "communication" | "assignment" | "appointment";
  direction: "inbound" | "outbound" | "internal" | null;
  channel: string;
  status: string;
  provider: string | null;
  subject: string | null;
  body: string;
  actor_user_id: string | null;
  actor_display_name: string | null;
  occurred_at: string;
};

type ConversationDetail = Conversation & {
  preferred_name: string | null;
  contact_methods: Array<{
    method_type: string;
    value: string;
    is_primary: boolean;
  }>;
  source: string;
  stage_key: string;
  lead_temperature: string | null;
  motivation: string | null;
  desired_timeline: string | null;
  property_condition: string | null;
  occupancy_status: string | null;
  appointment_status: string | null;
  next_follow_up_at: string | null;
  property_type: string | null;
  property_county: string | null;
  timeline: TimelineItem[];
  open_tasks: Array<{
    id: string;
    title: string;
    task_type: string;
    status: string;
    priority: string;
    due_at: string | null;
  }>;
  appointments: Array<{
    id: string;
    appointment_type: string;
    status: string;
    scheduled_start_at: string;
    scheduled_end_at: string | null;
    location_type: string;
    location: string | null;
    notes: string | null;
  }>;
  sms_eligibility: {
    can_send: boolean;
    recipient: string | null;
    consent_status: string;
    is_suppressed: boolean;
    provider_configured: boolean;
    within_allowed_hours: boolean;
    blockers: string[];
  };
};

type Assignee = {
  user_id: string;
  email: string;
  display_name: string;
  role_keys: string[];
};

type FilterKey = "mine" | "unassigned" | "team" | "needs_reply" | "appointments" | "unread";
type MobilePane = "conversations" | "thread" | "details";
type ComposerChannel = "sms" | "email" | "call" | "note";

const filters: Array<{
  key: FilterKey;
  label: string;
  icon: typeof Inbox;
}> = [
  { key: "mine", label: "Mine", icon: UserRound },
  { key: "unassigned", label: "Unassigned", icon: Inbox },
  { key: "team", label: "Team", icon: Users },
  { key: "needs_reply", label: "Needs reply", icon: Reply },
  { key: "appointments", label: "Appointments", icon: CalendarClock },
  { key: "unread", label: "Unread", icon: MailOpen },
];

const composerChannels: Array<{
  key: ComposerChannel;
  label: string;
  icon: typeof MessageSquare;
}> = [
  { key: "sms", label: "SMS", icon: MessageSquare },
  { key: "email", label: "Email", icon: Mail },
  { key: "call", label: "Call", icon: Phone },
  { key: "note", label: "Note", icon: NotebookPen },
];

const managerQueueOptions = [
  { value: "va_prospecting", label: "VA prospecting" },
  { value: "qualified", label: "Qualified" },
  { value: "appointment_set", label: "Appointment set" },
  { value: "acquisitions_follow_up", label: "Acquisitions follow-up" },
];

const acquisitionQueueOptions = managerQueueOptions.filter(
  (option) => option.value !== "va_prospecting",
);

function labelize(value: string | null | undefined) {
  if (!value) return "Not captured";
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function formatCompactTime(value: string | null) {
  if (!value) return "No activity";
  const date = new Date(value);
  const now = new Date();
  if (date.toDateString() === now.toDateString()) {
    return new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      minute: "2-digit",
    }).format(date);
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  }).format(date);
}

function formatDateTime(value: string | null) {
  if (!value) return "Not scheduled";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function hasNeedsReply(conversation: Conversation) {
  if (!conversation.last_inbound_at) return false;
  if (!conversation.last_outbound_at) return true;
  return new Date(conversation.last_inbound_at) > new Date(conversation.last_outbound_at);
}

function displayError(payload: unknown, fallback: string) {
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  return fallback;
}

export function InboxWorkspace() {
  const { getToken } = useAuth();
  const timelineEndRef = useRef<HTMLDivElement>(null);
  const smsIdempotencyKeyRef = useRef<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [assignees, setAssignees] = useState<Assignee[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterKey>("team");
  const [search, setSearch] = useState("");
  const [mobilePane, setMobilePane] = useState<MobilePane>("conversations");
  const [channel, setChannel] = useState<ComposerChannel>("sms");
  const [direction, setDirection] = useState<"inbound" | "outbound">("outbound");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [composerStatus, setComposerStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [handoffStatus, setHandoffStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [assigneeId, setAssigneeId] = useState("");
  const [queueKey, setQueueKey] = useState("acquisitions_follow_up");
  const [handoffReason, setHandoffReason] = useState("Reassigned from the shared inbox.");

  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  const getHeaders = useCallback(async () => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
      headers["X-Dev-User-Email"] = devUserEmail;
      return headers;
    }
    const token = await getToken().catch(() => null);
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    } else {
      headers["X-Dev-User-Email"] = devUserEmail;
    }
    return headers;
  }, [devUserEmail, getToken]);

  const request = useCallback(
    async <T,>(path: string, init?: RequestInit): Promise<T> => {
      const response = await fetch(`${apiBaseUrl}${path}`, {
        ...init,
        headers: {
          ...(await getHeaders()),
          ...init?.headers,
        },
        cache: "no-store",
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(displayError(payload, `Request failed with status ${response.status}.`));
      }
      return (await response.json()) as T;
    },
    [apiBaseUrl, getHeaders],
  );

  const loadConversations = useCallback(async () => {
    const payload = await request<{ items: Conversation[] }>("/api/v1/inbox/conversations");
    setConversations(payload.items);
    setSelectedId((current) => {
      if (current && payload.items.some((item) => item.id === current)) return current;
      return payload.items[0]?.id ?? null;
    });
    return payload.items;
  }, [request]);

  const loadDetail = useCallback(
    async (conversationId: string) => {
      setDetailLoading(true);
      try {
        const item = await request<ConversationDetail>(
          `/api/v1/inbox/conversations/${conversationId}`,
        );
        setDetail(item);
        if (item.unread_count > 0) {
          await request<Conversation>(`/api/v1/inbox/conversations/${conversationId}/read`, {
            method: "PATCH",
          });
          setConversations((current) =>
            current.map((conversation) =>
              conversation.id === conversationId
                ? { ...conversation, unread_count: 0 }
                : conversation,
            ),
          );
          setDetail((current) =>
            current?.id === conversationId ? { ...current, unread_count: 0 } : current,
          );
        }
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Unable to load conversation.");
        setDetail(null);
      } finally {
        setDetailLoading(false);
      }
    },
    [request],
  );

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [currentUser] = await Promise.all([request<Me>("/api/v1/me"), loadConversations()]);
        if (!active) return;
        setMe(currentUser);
        if (
          currentUser.permissions.includes("communications:manage_assignments") ||
          currentUser.permissions.includes("communications:handoff_assigned")
        ) {
          const payload = await request<{ items: Assignee[] }>("/api/v1/inbox/assignees");
          if (!active) return;
          setAssignees(payload.items);
          setAssigneeId(payload.items[0]?.user_id ?? "");
        }
      } catch (loadError) {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : "Unable to load inbox.");
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [loadConversations, request]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      if (selectedId) void loadDetail(selectedId);
      else setDetail(null);
    }, 0);
    return () => window.clearTimeout(handle);
  }, [loadDetail, selectedId]);

  useEffect(() => {
    timelineEndRef.current?.scrollIntoView({ block: "end" });
  }, [detail?.id, detail?.timeline.length]);

  const counts = useMemo(() => {
    const currentUserId = me?.user_id;
    return {
      mine: conversations.filter((item) => item.assigned_user_id === currentUserId).length,
      unassigned: conversations.filter((item) => !item.assigned_user_id).length,
      team: conversations.length,
      needs_reply: conversations.filter(hasNeedsReply).length,
      appointments: conversations.filter((item) => item.queue_key === "appointment_set").length,
      unread: conversations.filter((item) => item.unread_count > 0).length,
    };
  }, [conversations, me?.user_id]);

  const visibleConversations = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return conversations.filter((item) => {
      const matchesFilter =
        filter === "team" ||
        (filter === "mine" && item.assigned_user_id === me?.user_id) ||
        (filter === "unassigned" && !item.assigned_user_id) ||
        (filter === "needs_reply" && hasNeedsReply(item)) ||
        (filter === "appointments" && item.queue_key === "appointment_set") ||
        (filter === "unread" && item.unread_count > 0);
      const matchesSearch =
        !normalizedSearch ||
        item.seller_name.toLowerCase().includes(normalizedSearch) ||
        item.property_address.toLowerCase().includes(normalizedSearch);
      return matchesFilter && matchesSearch;
    });
  }, [conversations, filter, me?.user_id, search]);

  const canHandoff =
    me?.permissions.includes("communications:manage_assignments") ||
    me?.permissions.includes("communications:handoff_assigned");
  const canManageAssignments = me?.permissions.includes("communications:manage_assignments");
  const queueOptions = canManageAssignments ? managerQueueOptions : acquisitionQueueOptions;
  const primaryPhone = detail?.contact_methods.find((method) => method.method_type === "phone");
  const primaryEmail = detail?.contact_methods.find((method) => method.method_type === "email");
  const nextAppointment = detail?.appointments.find((appointment) =>
    ["scheduled", "rescheduled"].includes(appointment.status),
  );
  const nextTask = detail?.open_tasks[0];
  const isLiveSms = channel === "sms" && direction === "outbound";
  const canUseSms =
    me?.permissions.includes("communications:send_sms") ||
    me?.permissions.includes("communications:send_assigned_sms");
  const canSubmitComposer =
    Boolean(body.trim()) &&
    composerStatus !== "saving" &&
    (!isLiveSms || Boolean(canUseSms && detail?.sms_eligibility.can_send));

  function selectConversation(conversationId: string) {
    setSelectedId(conversationId);
    setMobilePane("thread");
    setError(null);
  }

  async function refreshInbox() {
    setError(null);
    try {
      await loadConversations();
      if (selectedId) await loadDetail(selectedId);
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Unable to refresh inbox.");
    }
  }

  async function submitCommunication(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail || !body.trim()) return;
    setComposerStatus("saving");
    setError(null);
    try {
      if (isLiveSms) {
        smsIdempotencyKeyRef.current ??= window.crypto.randomUUID();
        await request(`/api/v1/inbox/conversations/${detail.id}/messages/sms`, {
          method: "POST",
          body: JSON.stringify({
            body: body.trim(),
            idempotency_key: smsIdempotencyKeyRef.current,
          }),
        });
        smsIdempotencyKeyRef.current = null;
      } else {
        await request(`/api/v1/leads/${detail.lead_id}/communications`, {
          method: "POST",
          body: JSON.stringify({
            direction: channel === "note" ? "internal" : direction,
            channel,
            status: direction === "inbound" && channel !== "note" ? "received" : "logged",
            subject: subject.trim() || null,
            body: body.trim(),
            occurred_at: null,
          }),
        });
      }
      setSubject("");
      setBody("");
      setComposerStatus("saved");
      await Promise.all([loadConversations(), loadDetail(detail.id)]);
      window.setTimeout(() => setComposerStatus("idle"), 1800);
    } catch (submitError) {
      setComposerStatus("idle");
      setError(
        submitError instanceof Error ? submitError.message : "Unable to log communication.",
      );
    }
  }

  async function submitHandoff(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail || !assigneeId || !handoffReason.trim()) return;
    setHandoffStatus("saving");
    setError(null);
    try {
      await request(`/api/v1/inbox/conversations/${detail.id}/handoff`, {
        method: "POST",
        body: JSON.stringify({
          assigned_user_id: assigneeId,
          queue_key: queueKey,
          reason: handoffReason.trim(),
        }),
      });
      setHandoffStatus("saved");
      const items = await loadConversations();
      if (items.some((item) => item.id === detail.id)) {
        await loadDetail(detail.id);
      }
      window.setTimeout(() => setHandoffStatus("idle"), 1800);
    } catch (handoffError) {
      setHandoffStatus("idle");
      setError(handoffError instanceof Error ? handoffError.message : "Unable to hand off lead.");
    }
  }

  return (
    <>
      <header className={styles.pageHeader}>
        <div>
          <p className={styles.eyebrow}>Communications</p>
          <h2>Shared inbox</h2>
        </div>
        <button className={styles.refreshButton} onClick={() => void refreshInbox()} type="button">
          <RefreshCw size={16} aria-hidden="true" />
          Refresh
        </button>
      </header>

      {error ? (
        <div className={styles.errorBanner} role="alert">
          <CircleAlert size={17} aria-hidden="true" />
          <span>{error}</span>
          <button onClick={() => setError(null)} type="button" aria-label="Dismiss error">
            <Check size={16} aria-hidden="true" />
          </button>
        </div>
      ) : null}

      <nav className={styles.mobilePaneNav} aria-label="Inbox panes">
        <button
          className={mobilePane === "conversations" ? styles.activeMobilePane : undefined}
          onClick={() => setMobilePane("conversations")}
          type="button"
        >
          <Inbox size={16} aria-hidden="true" />
          Inbox
        </button>
        <button
          className={mobilePane === "thread" ? styles.activeMobilePane : undefined}
          disabled={!detail}
          onClick={() => setMobilePane("thread")}
          type="button"
        >
          <MessageSquare size={16} aria-hidden="true" />
          Thread
        </button>
        <button
          className={mobilePane === "details" ? styles.activeMobilePane : undefined}
          disabled={!detail}
          onClick={() => setMobilePane("details")}
          type="button"
        >
          <FileText size={16} aria-hidden="true" />
          Details
        </button>
      </nav>

      <section className={styles.inboxFrame} aria-label="Shared conversation inbox">
        <aside
          className={styles.conversationPane}
          data-mobile-active={mobilePane === "conversations"}
        >
          <div className={styles.filterRail}>
            {filters.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  className={filter === item.key ? styles.activeFilter : undefined}
                  key={item.key}
                  onClick={() => setFilter(item.key)}
                  type="button"
                >
                  <Icon size={16} aria-hidden="true" />
                  <span>{item.label}</span>
                  <strong>{counts[item.key]}</strong>
                </button>
              );
            })}
          </div>

          <div className={styles.listHeader}>
            <div>
              <strong>{filters.find((item) => item.key === filter)?.label}</strong>
              <span>{visibleConversations.length} conversations</span>
            </div>
            <label className={styles.searchBox}>
              <Search size={15} aria-hidden="true" />
              <input
                aria-label="Search conversations"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search seller or property"
                type="search"
                value={search}
              />
            </label>
          </div>

          <div className={styles.conversationList}>
            {loading ? <p className={styles.emptyState}>Loading conversations...</p> : null}
            {!loading && visibleConversations.length === 0 ? (
              <p className={styles.emptyState}>No conversations in this view.</p>
            ) : null}
            {visibleConversations.map((item) => (
              <button
                className={selectedId === item.id ? styles.activeConversation : undefined}
                key={item.id}
                onClick={() => selectConversation(item.id)}
                type="button"
              >
                <span className={styles.avatar} aria-hidden="true">
                  {item.seller_name.charAt(0).toUpperCase()}
                </span>
                <span className={styles.conversationCopy}>
                  <span className={styles.conversationTopline}>
                    <strong>{item.seller_name}</strong>
                    <time>{formatCompactTime(item.last_activity_at)}</time>
                  </span>
                  <span className={styles.address}>{item.property_address}</span>
                  <span className={styles.listMeta}>
                    <span>{labelize(item.queue_key)}</span>
                    {hasNeedsReply(item) ? <em>Needs reply</em> : null}
                  </span>
                </span>
                {item.unread_count > 0 ? (
                  <span className={styles.unreadBadge}>{item.unread_count}</span>
                ) : null}
              </button>
            ))}
          </div>
        </aside>

        <main className={styles.threadPane} data-mobile-active={mobilePane === "thread"}>
          {!detail && !detailLoading ? (
            <div className={styles.threadEmpty}>
              <MessageSquare size={30} aria-hidden="true" />
              <strong>Select a conversation</strong>
              <span>Seller communication and internal activity will appear here.</span>
            </div>
          ) : null}
          {detailLoading ? <div className={styles.threadEmpty}>Loading conversation...</div> : null}
          {detail && !detailLoading ? (
            <>
              <header className={styles.threadHeader}>
                <div>
                  <div className={styles.threadTitleRow}>
                    <h3>{detail.preferred_name || detail.seller_name}</h3>
                    <span className={styles.stageBadge}>{labelize(detail.stage_key)}</span>
                  </div>
                  <p>{detail.property_address}</p>
                </div>
                <div className={styles.contactActions}>
                  {primaryPhone ? (
                    <a href={`tel:${primaryPhone.value}`} title={`Call ${primaryPhone.value}`}>
                      <Phone size={17} aria-hidden="true" />
                      <span className={styles.visuallyHidden}>Call seller</span>
                    </a>
                  ) : null}
                  {primaryEmail ? (
                    <a href={`mailto:${primaryEmail.value}`} title={`Email ${primaryEmail.value}`}>
                      <Mail size={17} aria-hidden="true" />
                      <span className={styles.visuallyHidden}>Email seller</span>
                    </a>
                  ) : null}
                  <button
                    onClick={() => setMobilePane("details")}
                    title="Open seller details"
                    type="button"
                  >
                    <FileText size={17} aria-hidden="true" />
                    <span className={styles.visuallyHidden}>Open seller details</span>
                  </button>
                </div>
              </header>

              <div className={styles.timeline}>
                {detail.timeline.length === 0 ? (
                  <div className={styles.timelineEmpty}>
                    <MessageSquare size={22} aria-hidden="true" />
                    <span>No communication logged yet.</span>
                  </div>
                ) : null}
                {detail.timeline.map((item) =>
                  item.item_type === "communication" ? (
                    <article
                      className={`${styles.message} ${
                        item.direction === "outbound"
                          ? styles.outboundMessage
                          : item.direction === "internal"
                            ? styles.internalMessage
                            : styles.inboundMessage
                      }`}
                      key={item.id}
                    >
                      <div className={styles.messageMeta}>
                        <span>{labelize(item.channel)}</span>
                        <time>{formatDateTime(item.occurred_at)}</time>
                      </div>
                      {item.subject ? <strong>{item.subject}</strong> : null}
                      <p>{item.body}</p>
                      <small>
                        {item.actor_display_name || (item.direction === "inbound" ? "Seller" : "Team")}
                        {" · "}
                        {labelize(item.status)}
                      </small>
                    </article>
                  ) : (
                    <div className={styles.systemEvent} key={item.id}>
                      {item.item_type === "appointment" ? (
                        <CalendarClock size={15} aria-hidden="true" />
                      ) : (
                        <ArrowRightLeft size={15} aria-hidden="true" />
                      )}
                      <div>
                        <strong>{item.subject}</strong>
                        <span>{item.body}</span>
                        <time>{formatDateTime(item.occurred_at)}</time>
                      </div>
                    </div>
                  ),
                )}
                <div ref={timelineEndRef} />
              </div>

              <form className={styles.composer} onSubmit={submitCommunication}>
                <div className={styles.composerTabs} role="tablist" aria-label="Communication channel">
                  {composerChannels.map((item) => {
                    const Icon = item.icon;
                    return (
                      <button
                        aria-selected={channel === item.key}
                        className={channel === item.key ? styles.activeComposerTab : undefined}
                        key={item.key}
                        onClick={() => setChannel(item.key)}
                        role="tab"
                        type="button"
                      >
                        <Icon size={15} aria-hidden="true" />
                        {item.label}
                      </button>
                    );
                  })}
                </div>
                <div className={styles.composerControls}>
                  {channel !== "note" ? (
                    <div className={styles.directionToggle}>
                      <button
                        className={direction === "outbound" ? styles.activeDirection : undefined}
                        onClick={() => setDirection("outbound")}
                        type="button"
                      >
                        Outbound
                      </button>
                      <button
                        className={direction === "inbound" ? styles.activeDirection : undefined}
                        onClick={() => setDirection("inbound")}
                        type="button"
                      >
                        Inbound
                      </button>
                    </div>
                  ) : (
                    <span className={styles.internalLabel}>Internal note</span>
                  )}
                  {channel === "email" ? (
                    <input
                      aria-label="Email subject"
                      maxLength={255}
                      onChange={(event) => setSubject(event.target.value)}
                      placeholder="Subject"
                      value={subject}
                    />
                  ) : null}
                </div>
                {isLiveSms ? (
                  <div
                    className={
                      detail.sms_eligibility.can_send
                        ? styles.smsReady
                        : styles.smsBlocked
                    }
                  >
                    {detail.sms_eligibility.can_send ? (
                      <ShieldCheck size={15} aria-hidden="true" />
                    ) : (
                      <ShieldAlert size={15} aria-hidden="true" />
                    )}
                    <span>
                      {detail.sms_eligibility.can_send
                        ? canUseSms
                          ? `Ready to send to ${detail.sms_eligibility.recipient}`
                          : "Your role cannot send seller text messages."
                        : detail.sms_eligibility.blockers.join(" ")}
                    </span>
                  </div>
                ) : null}
                <div className={styles.composerBody}>
                  <textarea
                    aria-label={`${labelize(channel)} details`}
                    maxLength={channel === "sms" ? 1600 : 4000}
                    onChange={(event) => {
                      if (event.target.value !== body) smsIdempotencyKeyRef.current = null;
                      setBody(event.target.value);
                    }}
                    placeholder={
                      channel === "note"
                        ? "Add a note for the Stonegate team..."
                        : `Log the ${channel} conversation...`
                    }
                    required
                    rows={3}
                    value={body}
                  />
                  <button disabled={!canSubmitComposer} type="submit">
                    {composerStatus === "saved" ? (
                      <Check size={17} aria-hidden="true" />
                    ) : (
                      <Send size={17} aria-hidden="true" />
                    )}
                    {composerStatus === "saving"
                      ? "Saving"
                      : composerStatus === "saved"
                        ? isLiveSms
                          ? "Sent"
                          : "Logged"
                        : isLiveSms
                          ? "Send SMS"
                          : `Log ${channel === "note" ? "note" : channel.toUpperCase()}`}
                  </button>
                </div>
              </form>
            </>
          ) : null}
        </main>

        <aside className={styles.detailPane} data-mobile-active={mobilePane === "details"}>
          {!detail ? (
            <div className={styles.detailEmpty}>Select a conversation to view seller context.</div>
          ) : (
            <>
              <header className={styles.detailHeader}>
                <div>
                  <span>Lead context</span>
                  <h3>{detail.seller_name}</h3>
                </div>
                <Link href={`/os/leads/${detail.lead_id}`}>
                  Full record
                  <ChevronRight size={15} aria-hidden="true" />
                </Link>
              </header>

              <section className={styles.detailSection}>
                <h4>Contact</h4>
                <div className={styles.contactList}>
                  {detail.contact_methods.length === 0 ? <span>No contact methods</span> : null}
                  {detail.contact_methods.map((method) => (
                    <a
                      href={
                        method.method_type === "phone"
                          ? `tel:${method.value}`
                          : method.method_type === "email"
                            ? `mailto:${method.value}`
                            : undefined
                      }
                      key={`${method.method_type}-${method.value}`}
                    >
                      {method.method_type === "phone" ? (
                        <Phone size={15} aria-hidden="true" />
                      ) : (
                        <Mail size={15} aria-hidden="true" />
                      )}
                      <span>
                        <strong>{labelize(method.method_type)}</strong>
                        <small>{method.value}</small>
                      </span>
                    </a>
                  ))}
                </div>
                <div
                  className={
                    detail.sms_eligibility.can_send
                      ? styles.contactSmsReady
                      : styles.contactSmsBlocked
                  }
                >
                  {detail.sms_eligibility.can_send ? (
                    <ShieldCheck size={14} aria-hidden="true" />
                  ) : (
                    <ShieldAlert size={14} aria-hidden="true" />
                  )}
                  <span>
                    {detail.sms_eligibility.can_send
                      ? "SMS eligible"
                      : detail.sms_eligibility.is_suppressed
                        ? "SMS suppressed"
                        : `SMS consent ${labelize(detail.sms_eligibility.consent_status)}`}
                  </span>
                </div>
              </section>

              <section className={styles.detailSection}>
                <h4>Property</h4>
                <p className={styles.propertyAddress}>{detail.property_address}</p>
                <dl className={styles.contextGrid}>
                  <div>
                    <dt>Type</dt>
                    <dd>{labelize(detail.property_type)}</dd>
                  </div>
                  <div>
                    <dt>County</dt>
                    <dd>{detail.property_county || "Not captured"}</dd>
                  </div>
                  <div>
                    <dt>Source</dt>
                    <dd>{labelize(detail.source)}</dd>
                  </div>
                  <div>
                    <dt>Temperature</dt>
                    <dd>{labelize(detail.lead_temperature)}</dd>
                  </div>
                </dl>
              </section>

              <section className={styles.detailSection}>
                <h4>Qualification</h4>
                <dl className={styles.detailList}>
                  <div>
                    <dt>Motivation</dt>
                    <dd>{detail.motivation || "Not captured"}</dd>
                  </div>
                  <div>
                    <dt>Timeline</dt>
                    <dd>{labelize(detail.desired_timeline)}</dd>
                  </div>
                  <div>
                    <dt>Condition</dt>
                    <dd>{labelize(detail.property_condition)}</dd>
                  </div>
                  <div>
                    <dt>Occupancy</dt>
                    <dd>{labelize(detail.occupancy_status)}</dd>
                  </div>
                </dl>
              </section>

              <section className={styles.detailSection}>
                <h4>Next action</h4>
                {nextAppointment ? (
                  <div className={styles.nextAction}>
                    <CalendarClock size={17} aria-hidden="true" />
                    <div>
                      <strong>{labelize(nextAppointment.appointment_type)}</strong>
                      <span>{formatDateTime(nextAppointment.scheduled_start_at)}</span>
                    </div>
                  </div>
                ) : nextTask ? (
                  <div className={styles.nextAction}>
                    <Clock3 size={17} aria-hidden="true" />
                    <div>
                      <strong>{nextTask.title}</strong>
                      <span>{formatDateTime(nextTask.due_at)}</span>
                    </div>
                  </div>
                ) : (
                  <p className={styles.mutedText}>No open task or appointment.</p>
                )}
              </section>

              <section className={styles.detailSection}>
                <h4>Ownership</h4>
                <div className={styles.ownerRow}>
                  <span className={styles.ownerAvatar} aria-hidden="true">
                    {(detail.assigned_user_display_name || "?").charAt(0)}
                  </span>
                  <div>
                    <strong>{detail.assigned_user_display_name || "Unassigned"}</strong>
                    <span>{labelize(detail.queue_key)}</span>
                  </div>
                </div>
                {detail.watchers.length > 0 ? (
                  <div className={styles.watchers}>
                    <span>Following</span>
                    <div>
                      {detail.watchers.map((watcher) => (
                        <span title={watcher.email} key={watcher.user_id}>
                          {watcher.display_name.charAt(0).toUpperCase()}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
              </section>

              {canHandoff && assignees.length > 0 ? (
                <section className={styles.detailSection}>
                  <h4>Assign or hand off</h4>
                  <form className={styles.handoffForm} onSubmit={submitHandoff}>
                    <label>
                      <span>Owner</span>
                      <select
                        onChange={(event) => setAssigneeId(event.target.value)}
                        value={assigneeId}
                      >
                        {assignees.map((assignee) => (
                          <option key={assignee.user_id} value={assignee.user_id}>
                            {assignee.display_name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Queue</span>
                      <select onChange={(event) => setQueueKey(event.target.value)} value={queueKey}>
                        {queueOptions.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Reason</span>
                      <textarea
                        maxLength={500}
                        onChange={(event) => setHandoffReason(event.target.value)}
                        required
                        rows={2}
                        value={handoffReason}
                      />
                    </label>
                    <button disabled={handoffStatus === "saving"} type="submit">
                      {handoffStatus === "saved" ? (
                        <Check size={16} aria-hidden="true" />
                      ) : (
                        <ArrowRightLeft size={16} aria-hidden="true" />
                      )}
                      {handoffStatus === "saving"
                        ? "Saving"
                        : handoffStatus === "saved"
                          ? "Updated"
                          : "Update ownership"}
                    </button>
                  </form>
                </section>
              ) : null}
            </>
          )}
        </aside>
      </section>
    </>
  );
}
