"use client";

import { useAuth } from "@clerk/nextjs";
import type { Call, Device } from "@twilio/voice-sdk";
import {
  ArrowRightLeft,
  Bot,
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
  Mic,
  MicOff,
  NotebookPen,
  Phone,
  PhoneCall,
  PhoneOff,
  Play,
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
  call_id: string | null;
  duration_seconds: number | null;
  recording_id: string | null;
  recording_status: string | null;
  transcript: CallTranscript | null;
};

type CallNoteEvidence = {
  field: string;
  segment_index: number;
  start_seconds: number;
  supporting_text: string;
};

type StructuredCallNotes = {
  summary: string;
  motivation: string | null;
  timeline: string | null;
  property_condition: string | null;
  occupancy_status: string | null;
  asking_price: string | null;
  mortgage_or_title: string | null;
  repairs: string[];
  objections: string[];
  commitments: string[];
  next_action: string | null;
  follow_up_at: string | null;
  appointment_details: string | null;
  confidence: number;
  evidence: CallNoteEvidence[];
};

type CallTranscript = {
  id: string;
  status: string;
  model_name: string | null;
  language: string | null;
  transcript_text: string | null;
  speaker_segments: Array<{
    index?: number;
    speaker?: string;
    start?: number;
    end?: number;
    text?: string;
  }>;
  confidence_score: number | null;
  structured_notes: StructuredCallNotes | null;
  approval_request_id: string | null;
  approved_by_user_id: string | null;
  approved_at: string | null;
  error_message: string | null;
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
  voice_eligibility: {
    can_call: boolean;
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
type VoiceStatus =
  | "disabled"
  | "loading"
  | "ready"
  | "connecting"
  | "ringing"
  | "incoming"
  | "active"
  | "ended"
  | "error";

type VoiceSession = {
  can_initialize: boolean;
  identity: string;
  token: string | null;
  expires_at: string | null;
  line: {
    id: string;
    phone_number: string;
    label: string;
  } | null;
  recording_enabled: boolean;
  blockers: string[];
};

type VoiceCallIntent = {
  id: string;
  conversation_id: string;
  recipient: string;
  from_number: string;
  status: string;
  expires_at: string;
  recording_enabled: boolean;
};

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

function formatDuration(totalSeconds: number | null) {
  if (totalSeconds === null) return "No duration";
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
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

const callNoteFieldOptions: Array<{ key: keyof StructuredCallNotes; label: string }> = [
  { key: "motivation", label: "Motivation" },
  { key: "timeline", label: "Timeline" },
  { key: "property_condition", label: "Condition" },
  { key: "occupancy_status", label: "Occupancy" },
  { key: "asking_price", label: "Asking price" },
];

function listToText(values: string[]) {
  return values.join("\n");
}

function textToList(value: string) {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function CallTranscriptPanel({
  transcript,
  canReview,
  onReview,
}: {
  transcript: CallTranscript;
  canReview: boolean;
  onReview: (
    transcriptId: string,
    payload: {
      status: "approved" | "rejected";
      structured_notes: StructuredCallNotes;
      decision_notes: string | null;
      apply_field_updates: string[];
      create_follow_up_task: boolean;
    },
  ) => Promise<void>;
}) {
  const [notes, setNotes] = useState<StructuredCallNotes | null>(transcript.structured_notes);
  const [selectedFields, setSelectedFields] = useState<string[]>(
    callNoteFieldOptions
      .filter((item) => Boolean(transcript.structured_notes?.[item.key]))
      .map((item) => item.key),
  );
  const [createTask, setCreateTask] = useState(Boolean(transcript.structured_notes?.next_action));
  const [decisionNotes, setDecisionNotes] = useState("");
  const [reviewStatus, setReviewStatus] = useState<"idle" | "saving">("idle");

  const updateNote = <K extends keyof StructuredCallNotes>(
    key: K,
    value: StructuredCallNotes[K],
  ) => {
    setNotes((current) => (current ? { ...current, [key]: value } : current));
  };

  const submitReview = async (status: "approved" | "rejected") => {
    if (!notes) return;
    setReviewStatus("saving");
    try {
      await onReview(transcript.id, {
        status,
        structured_notes: notes,
        decision_notes: decisionNotes.trim() || null,
        apply_field_updates: status === "approved" ? selectedFields : [],
        create_follow_up_task: status === "approved" && createTask,
      });
    } finally {
      setReviewStatus("idle");
    }
  };

  return (
    <details className={styles.transcriptPanel}>
      <summary>
        <span>
          <Bot size={14} aria-hidden="true" />
          AI call intelligence
        </span>
        <span className={styles.transcriptStatus} data-status={transcript.status}>
          {labelize(transcript.status)}
        </span>
      </summary>
      <div className={styles.transcriptBody}>
        {transcript.error_message ? (
          <p className={styles.transcriptError}>{transcript.error_message}</p>
        ) : null}
        {notes ? (
          <section className={styles.notesReview} aria-label="AI call-note review">
            <div className={styles.notesReviewHeader}>
              <strong>Review draft</strong>
              <span>{notes.confidence}% AI confidence</span>
            </div>
            <label>
              Summary
              <textarea
                disabled={!canReview || transcript.status !== "needs_review"}
                onChange={(event) => updateNote("summary", event.target.value)}
                value={notes.summary}
              />
            </label>
            <div className={styles.notesGrid}>
              {callNoteFieldOptions.map((item) => (
                <label key={item.key}>
                  {item.label}
                  <input
                    disabled={!canReview || transcript.status !== "needs_review"}
                    onChange={(event) =>
                      updateNote(item.key, event.target.value || null)
                    }
                    value={String(notes[item.key] ?? "")}
                  />
                </label>
              ))}
              <label>
                Mortgage or title
                <input
                  disabled={!canReview || transcript.status !== "needs_review"}
                  onChange={(event) =>
                    updateNote("mortgage_or_title", event.target.value || null)
                  }
                  value={notes.mortgage_or_title ?? ""}
                />
              </label>
              <label>
                Next action
                <input
                  disabled={!canReview || transcript.status !== "needs_review"}
                  onChange={(event) => updateNote("next_action", event.target.value || null)}
                  value={notes.next_action ?? ""}
                />
              </label>
              <label>
                Follow-up time
                <input
                  disabled={!canReview || transcript.status !== "needs_review"}
                  onChange={(event) => updateNote("follow_up_at", event.target.value || null)}
                  placeholder="ISO date/time if stated"
                  value={notes.follow_up_at ?? ""}
                />
              </label>
            </div>
            <div className={styles.notesGrid}>
              {(["repairs", "objections", "commitments"] as const).map((key) => (
                <label key={key}>
                  {labelize(key)} (one per line)
                  <textarea
                    disabled={!canReview || transcript.status !== "needs_review"}
                    onChange={(event) => updateNote(key, textToList(event.target.value))}
                    value={listToText(notes[key])}
                  />
                </label>
              ))}
            </div>
            {canReview && transcript.status === "needs_review" ? (
              <div className={styles.reviewControls}>
                <fieldset>
                  <legend>Fill empty lead fields</legend>
                  {callNoteFieldOptions
                    .filter((item) => Boolean(notes[item.key]))
                    .map((item) => (
                      <label key={item.key}>
                        <input
                          checked={selectedFields.includes(item.key)}
                          onChange={(event) =>
                            setSelectedFields((current) =>
                              event.target.checked
                                ? [...current, item.key]
                                : current.filter((key) => key !== item.key),
                            )
                          }
                          type="checkbox"
                        />
                        {item.label}
                      </label>
                    ))}
                  {notes.next_action ? (
                    <label>
                      <input
                        checked={createTask}
                        onChange={(event) => setCreateTask(event.target.checked)}
                        type="checkbox"
                      />
                      Create follow-up task
                    </label>
                  ) : null}
                </fieldset>
                <label>
                  Review note
                  <input
                    onChange={(event) => setDecisionNotes(event.target.value)}
                    placeholder="Optional correction or decision reason"
                    value={decisionNotes}
                  />
                </label>
                <div className={styles.reviewActions}>
                  <button
                    disabled={reviewStatus === "saving"}
                    onClick={() => void submitReview("rejected")}
                    type="button"
                  >
                    Reject draft
                  </button>
                  <button
                    className={styles.approveButton}
                    disabled={reviewStatus === "saving"}
                    onClick={() => void submitReview("approved")}
                    type="button"
                  >
                    <Check size={14} aria-hidden="true" />
                    {reviewStatus === "saving" ? "Saving" : "Approve notes"}
                  </button>
                </div>
              </div>
            ) : null}
          </section>
        ) : (
          <p className={styles.transcriptPending}>
            {transcript.status === "failed"
              ? "Transcription will retry automatically."
              : "Recording is queued for transcription."}
          </p>
        )}
        {transcript.speaker_segments.length > 0 ? (
          <details className={styles.transcriptText}>
            <summary>Full transcript</summary>
            <div>
              {transcript.speaker_segments.map((segment, index) => (
                <p key={`${segment.start ?? 0}-${index}`}>
                  <strong>
                    {segment.speaker || "Speaker"} ·{" "}
                    {formatDuration(Math.round(segment.start ?? 0))}
                  </strong>
                  <span>{segment.text}</span>
                </p>
              ))}
            </div>
          </details>
        ) : transcript.transcript_text ? (
          <details className={styles.transcriptText}>
            <summary>Full transcript</summary>
            <p>{transcript.transcript_text}</p>
          </details>
        ) : null}
      </div>
    </details>
  );
}

export function InboxWorkspace() {
  const { getToken } = useAuth();
  const timelineEndRef = useRef<HTMLDivElement>(null);
  const smsIdempotencyKeyRef = useRef<string | null>(null);
  const voiceDeviceRef = useRef<Device | null>(null);
  const activeCallRef = useRef<Call | null>(null);
  const recordingUrlsRef = useRef<Record<string, string>>({});
  const [me, setMe] = useState<Me | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [assignees, setAssignees] = useState<Assignee[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterKey>("team");
  const [search, setSearch] = useState("");
  const [mobilePane, setMobilePane] = useState<MobilePane>("conversations");
  const [channel, setChannel] = useState<ComposerChannel>("sms");
  const [callComposerMode, setCallComposerMode] = useState<"browser" | "log">("browser");
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
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>("disabled");
  const [voiceSession, setVoiceSession] = useState<VoiceSession | null>(null);
  const [voiceMessage, setVoiceMessage] = useState("Calling is off");
  const [voiceCaller, setVoiceCaller] = useState<string | null>(null);
  const [callStartedAt, setCallStartedAt] = useState<number | null>(null);
  const [callElapsed, setCallElapsed] = useState(0);
  const [callMuted, setCallMuted] = useState(false);
  const [recordingUrls, setRecordingUrls] = useState<Record<string, string>>({});
  const [recordingLoadingId, setRecordingLoadingId] = useState<string | null>(null);

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

  const reviewTranscript = useCallback(
    async (
      transcriptId: string,
      payload: {
        status: "approved" | "rejected";
        structured_notes: StructuredCallNotes;
        decision_notes: string | null;
        apply_field_updates: string[];
        create_follow_up_task: boolean;
      },
    ) => {
      await request(`/api/v1/voice/transcripts/${transcriptId}/review`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      if (selectedId) {
        await Promise.all([loadConversations(), loadDetail(selectedId)]);
      }
    },
    [loadConversations, loadDetail, request, selectedId],
  );

  const finishCall = useCallback(() => {
    activeCallRef.current = null;
    setCallStartedAt(null);
    setCallElapsed(0);
    setCallMuted(false);
    setVoiceCaller(null);
    setVoiceStatus("ended");
    setVoiceMessage("Call ended");
    const conversationId = selectedId;
    window.setTimeout(() => {
      setVoiceStatus((current) => (current === "ended" ? "ready" : current));
      setVoiceMessage((current) => (current === "Call ended" ? "Ready for calls" : current));
    }, 1600);
    if (conversationId) {
      void Promise.all([loadConversations(), loadDetail(conversationId)]);
    }
  }, [loadConversations, loadDetail, selectedId]);

  const wireCall = useCallback(
    (call: Call, incoming: boolean) => {
      activeCallRef.current = call;
      call.on("ringing", () => {
        setVoiceStatus("ringing");
        setVoiceMessage(incoming ? "Incoming call" : "Ringing seller");
      });
      call.on("accept", () => {
        setVoiceStatus("active");
        setVoiceMessage("Call connected");
        setCallStartedAt(Date.now());
      });
      call.on("disconnect", finishCall);
      call.on("cancel", finishCall);
      call.on("reject", finishCall);
      call.on("error", (callError: Error) => {
        setVoiceStatus("error");
        setVoiceMessage(callError.message || "Call failed");
        setError(callError.message || "Twilio could not complete the call.");
        activeCallRef.current = null;
      });
    },
    [finishCall],
  );

  const enableCalling = useCallback(async (): Promise<Device | null> => {
    if (voiceDeviceRef.current) return voiceDeviceRef.current;
    setVoiceStatus("loading");
    setVoiceMessage("Connecting secure phone");
    try {
      const session = await request<VoiceSession>("/api/v1/voice/session");
      setVoiceSession(session);
      if (!session.can_initialize || !session.token) {
        const message = session.blockers.join(" ") || "Calling is not available.";
        setVoiceStatus("disabled");
        setVoiceMessage(message);
        setError(message);
        return null;
      }
      const { Device: TwilioDevice } = await import("@twilio/voice-sdk");
      if (!TwilioDevice.isSupported) {
        throw new Error("This browser does not support secure browser calling.");
      }
      const device = new TwilioDevice(session.token, {
        closeProtection: "A Stonegate call is still active.",
        tokenRefreshMs: 60_000,
      });
      device.on("registered", () => {
        setVoiceStatus("ready");
        setVoiceMessage(`Ready on ${session.line?.phone_number ?? "Stonegate line"}`);
      });
      device.on("unregistered", () => {
        setVoiceStatus("disabled");
        setVoiceMessage("Calling is off");
      });
      device.on("error", (deviceError: Error) => {
        setVoiceStatus("error");
        setVoiceMessage(deviceError.message || "Phone connection failed");
        setError(deviceError.message || "Twilio Voice could not connect.");
      });
      device.on("incoming", (call: Call) => {
        const caller = call.parameters.From || call.customParameters.get("From") || "Unknown caller";
        setVoiceCaller(caller);
        setVoiceStatus("incoming");
        setVoiceMessage("Incoming Stonegate call");
        wireCall(call, true);
      });
      device.on("tokenWillExpire", async () => {
        try {
          const refreshed = await request<VoiceSession>("/api/v1/voice/session");
          if (refreshed.token) {
            device.updateToken(refreshed.token);
            setVoiceSession(refreshed);
          }
        } catch {
          setError("The phone session could not be refreshed. Finish the call and reconnect.");
        }
      });
      voiceDeviceRef.current = device;
      await device.register();
      return device;
    } catch (voiceError) {
      const message =
        voiceError instanceof Error ? voiceError.message : "Unable to initialize browser calling.";
      setVoiceStatus("error");
      setVoiceMessage(message);
      setError(message);
      return null;
    }
  }, [request, wireCall]);

  const startCall = useCallback(async () => {
    if (!detail || activeCallRef.current) return;
    const canPlaceCalls =
      me?.permissions.includes("communications:place_calls") ||
      (me?.permissions.includes("communications:place_assigned_calls") &&
        detail.assigned_user_id === me.user_id);
    if (!canPlaceCalls) {
      setError("This conversation must be assigned to you before you can call.");
      return;
    }
    if (!detail.voice_eligibility.can_call) {
      setError(detail.voice_eligibility.blockers.join(" "));
      return;
    }
    setError(null);
    const device = voiceDeviceRef.current ?? (await enableCalling());
    if (!device) return;
    try {
      setVoiceCaller(detail.preferred_name || detail.seller_name);
      setCallElapsed(0);
      setVoiceStatus("connecting");
      setVoiceMessage(`Calling ${detail.voice_eligibility.recipient}`);
      const intent = await request<VoiceCallIntent>(
        `/api/v1/voice/conversations/${detail.id}/call-intents`,
        {
          method: "POST",
          body: JSON.stringify({ idempotency_key: window.crypto.randomUUID() }),
        },
      );
      const call = await device.connect({
        params: { CallIntentId: intent.id },
      });
      wireCall(call, false);
    } catch (voiceError) {
      const message = voiceError instanceof Error ? voiceError.message : "Call could not start.";
      setVoiceStatus("error");
      setVoiceMessage(message);
      setVoiceCaller(null);
      setError(message);
    }
  }, [detail, enableCalling, me, request, wireCall]);

  const loadRecording = useCallback(
    async (recordingId: string) => {
      if (recordingUrlsRef.current[recordingId]) return;
      setRecordingLoadingId(recordingId);
      try {
        const response = await fetch(
          `${apiBaseUrl}/api/v1/voice/recordings/${recordingId}/media`,
          {
            headers: await getHeaders(),
            cache: "no-store",
          },
        );
        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          throw new Error(displayError(payload, "Recording could not be loaded."));
        }
        const url = URL.createObjectURL(await response.blob());
        recordingUrlsRef.current[recordingId] = url;
        setRecordingUrls((current) => ({ ...current, [recordingId]: url }));
      } catch (recordingError) {
        setError(
          recordingError instanceof Error
            ? recordingError.message
            : "Recording could not be loaded.",
        );
      } finally {
        setRecordingLoadingId(null);
      }
    },
    [apiBaseUrl, getHeaders],
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

  useEffect(() => {
    if (voiceStatus !== "active" || callStartedAt === null) {
      return;
    }
    const updateElapsed = () => {
      setCallElapsed(Math.max(0, Math.floor((Date.now() - callStartedAt) / 1000)));
    };
    updateElapsed();
    const interval = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(interval);
  }, [callStartedAt, voiceStatus]);

  useEffect(
    () => () => {
      voiceDeviceRef.current?.destroy();
      for (const url of Object.values(recordingUrlsRef.current)) {
        URL.revokeObjectURL(url);
      }
    },
    [],
  );

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
  const isVoiceComposer = channel === "call" && callComposerMode === "browser";
  const isCallInProgress = ["connecting", "ringing", "incoming", "active"].includes(
    voiceStatus,
  );
  const canUseSms =
    me?.permissions.includes("communications:send_sms") ||
    me?.permissions.includes("communications:send_assigned_sms");
  const canSubmitComposer =
    Boolean(body.trim()) &&
    composerStatus !== "saving" &&
    !isVoiceComposer &&
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

  function acceptIncomingCall() {
    const call = activeCallRef.current;
    if (!call) return;
    call.accept();
    setVoiceStatus("connecting");
    setVoiceMessage("Connecting call");
  }

  function rejectIncomingCall() {
    activeCallRef.current?.reject();
    finishCall();
  }

  function endActiveCall() {
    activeCallRef.current?.disconnect();
  }

  function toggleCallMute() {
    const call = activeCallRef.current;
    if (!call) return;
    const nextMuted = !callMuted;
    call.mute(nextMuted);
    setCallMuted(nextMuted);
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
        <div className={styles.headerActions}>
          <button
            className={styles.phoneStatusButton}
            data-status={voiceStatus}
            disabled={voiceStatus === "loading"}
            onClick={() => void enableCalling()}
            title={voiceMessage}
            type="button"
          >
            <PhoneCall size={16} aria-hidden="true" />
            {voiceStatus === "disabled" || voiceStatus === "error"
              ? "Enable calling"
              : voiceMessage}
          </button>
          <button className={styles.refreshButton} onClick={() => void refreshInbox()} type="button">
            <RefreshCw size={16} aria-hidden="true" />
            Refresh
          </button>
        </div>
      </header>

      {["connecting", "ringing", "incoming", "active"].includes(voiceStatus) ? (
        <section className={styles.callDock} aria-live="polite">
          <span className={styles.callDockIcon}>
            <PhoneCall size={18} aria-hidden="true" />
          </span>
          <div>
            <strong>{voiceCaller || "Stonegate call"}</strong>
            <span>
              {voiceMessage}
              {voiceStatus === "active" ? ` · ${formatDuration(callElapsed)}` : ""}
            </span>
          </div>
          <div className={styles.callDockActions}>
            {voiceStatus === "incoming" ? (
              <>
                <button
                  className={styles.acceptCallButton}
                  onClick={acceptIncomingCall}
                  title="Answer call"
                  type="button"
                >
                  <Phone size={17} aria-hidden="true" />
                  <span className={styles.visuallyHidden}>Answer call</span>
                </button>
                <button
                  className={styles.endCallButton}
                  onClick={rejectIncomingCall}
                  title="Decline call"
                  type="button"
                >
                  <PhoneOff size={17} aria-hidden="true" />
                  <span className={styles.visuallyHidden}>Decline call</span>
                </button>
              </>
            ) : (
              <>
                {voiceStatus === "active" ? (
                  <button
                    className={styles.muteCallButton}
                    data-muted={callMuted}
                    onClick={toggleCallMute}
                    title={callMuted ? "Unmute microphone" : "Mute microphone"}
                    type="button"
                  >
                    {callMuted ? (
                      <MicOff size={17} aria-hidden="true" />
                    ) : (
                      <Mic size={17} aria-hidden="true" />
                    )}
                    <span className={styles.visuallyHidden}>
                      {callMuted ? "Unmute microphone" : "Mute microphone"}
                    </span>
                  </button>
                ) : null}
                <button
                  className={styles.endCallButton}
                  onClick={endActiveCall}
                  title="End call"
                  type="button"
                >
                  <PhoneOff size={17} aria-hidden="true" />
                  <span className={styles.visuallyHidden}>End call</span>
                </button>
              </>
            )}
          </div>
        </section>
      ) : null}

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
                    <button
                      disabled={isCallInProgress}
                      onClick={() => void startCall()}
                      title={`Call ${primaryPhone.value} from Stonegate`}
                      type="button"
                    >
                      <Phone size={17} aria-hidden="true" />
                      <span className={styles.visuallyHidden}>Call seller</span>
                    </button>
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
                      } ${item.channel === "call" ? styles.callMessage : ""}`}
                      key={item.id}
                    >
                      <div className={styles.messageMeta}>
                        <span>{labelize(item.channel)}</span>
                        <time>{formatDateTime(item.occurred_at)}</time>
                      </div>
                      {item.subject ? <strong>{item.subject}</strong> : null}
                      <p>{item.body}</p>
                      {item.channel === "call" ? (
                        <>
                          <div className={styles.callMetadata}>
                            <span>{formatDuration(item.duration_seconds)}</span>
                            {item.recording_id &&
                            item.recording_status === "completed" &&
                            me?.permissions.includes("communications:access_recordings") ? (
                              recordingUrls[item.recording_id] ? (
                                <audio
                                  controls
                                  preload="none"
                                  src={recordingUrls[item.recording_id]}
                                >
                                  Call recording
                                </audio>
                              ) : (
                                <button
                                  disabled={recordingLoadingId === item.recording_id}
                                  onClick={() => void loadRecording(item.recording_id as string)}
                                  type="button"
                                >
                                  <Play size={13} aria-hidden="true" />
                                  {recordingLoadingId === item.recording_id
                                    ? "Loading"
                                    : "Play recording"}
                                </button>
                              )
                            ) : item.recording_status &&
                              item.recording_status !== "completed" ? (
                              <span>Recording {labelize(item.recording_status)}</span>
                            ) : null}
                          </div>
                          {item.transcript &&
                          me?.permissions.includes("communications:access_recordings") ? (
                            <CallTranscriptPanel
                              canReview={Boolean(
                                me.permissions.includes("leads:edit") &&
                                  me.permissions.includes(
                                    "communications:access_recordings",
                                  ),
                              )}
                              key={item.transcript.id}
                              onReview={reviewTranscript}
                              transcript={item.transcript}
                            />
                          ) : null}
                        </>
                      ) : null}
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
                  {channel === "call" ? (
                    <>
                      <div className={styles.callModeToggle}>
                        <button
                          className={
                            callComposerMode === "browser" ? styles.activeDirection : undefined
                          }
                          onClick={() => setCallComposerMode("browser")}
                          type="button"
                        >
                          <PhoneCall size={13} aria-hidden="true" />
                          Browser
                        </button>
                        <button
                          className={callComposerMode === "log" ? styles.activeDirection : undefined}
                          onClick={() => setCallComposerMode("log")}
                          type="button"
                        >
                          <NotebookPen size={13} aria-hidden="true" />
                          Log external
                        </button>
                      </div>
                      {callComposerMode === "log" ? (
                        <div className={styles.directionToggle}>
                          <button
                            className={
                              direction === "outbound" ? styles.activeDirection : undefined
                            }
                            onClick={() => setDirection("outbound")}
                            type="button"
                          >
                            Outbound
                          </button>
                          <button
                            className={
                              direction === "inbound" ? styles.activeDirection : undefined
                            }
                            onClick={() => setDirection("inbound")}
                            type="button"
                          >
                            Inbound
                          </button>
                        </div>
                      ) : (
                        <span className={styles.voiceLabel}>
                          <PhoneCall size={14} aria-hidden="true" />
                          Secure browser call
                        </span>
                      )}
                    </>
                  ) : channel === "sms" || channel === "email" ? (
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
                {isVoiceComposer ? (
                  <div className={styles.voiceComposer}>
                    <div
                      className={
                        detail.voice_eligibility.can_call
                          ? styles.voiceReady
                          : styles.voiceBlocked
                      }
                    >
                      {detail.voice_eligibility.can_call ? (
                        <ShieldCheck size={15} aria-hidden="true" />
                      ) : (
                        <ShieldAlert size={15} aria-hidden="true" />
                      )}
                      <span>
                        {detail.voice_eligibility.can_call
                          ? `Call ${detail.voice_eligibility.recipient} from ${
                              voiceSession?.line?.phone_number || "the Stonegate line"
                            }`
                          : detail.voice_eligibility.blockers.join(" ")}
                      </span>
                    </div>
                    <button
                      disabled={
                        !detail.voice_eligibility.can_call ||
                        ["connecting", "ringing", "incoming", "active"].includes(voiceStatus)
                      }
                      onClick={() => void startCall()}
                      type="button"
                    >
                      <PhoneCall size={17} aria-hidden="true" />
                      {voiceStatus === "loading" ? "Connecting phone" : "Call seller"}
                    </button>
                  </div>
                ) : (
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
                )}
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
                <div
                  className={
                    detail.voice_eligibility.can_call
                      ? styles.contactVoiceReady
                      : styles.contactVoiceBlocked
                  }
                >
                  {detail.voice_eligibility.can_call ? (
                    <PhoneCall size={14} aria-hidden="true" />
                  ) : (
                    <ShieldAlert size={14} aria-hidden="true" />
                  )}
                  <span>
                    {detail.voice_eligibility.can_call
                      ? "Voice eligible"
                      : detail.voice_eligibility.is_suppressed
                        ? "Calling suppressed"
                        : `Phone permission ${labelize(detail.voice_eligibility.consent_status)}`}
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
