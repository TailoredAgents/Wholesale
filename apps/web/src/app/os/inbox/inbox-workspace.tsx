"use client";

import { useAuth } from "@clerk/nextjs";
import {
  Archive,
  ArrowRightLeft,
  Bot,
  CalendarClock,
  Check,
  ChevronRight,
  CircleAlert,
  Clock3,
  Download,
  FileText,
  Headphones,
  Inbox,
  Mail,
  MailOpen,
  MessageSquare,
  NotebookPen,
  Phone,
  PhoneCall,
  Play,
  Plus,
  Paperclip,
  RefreshCw,
  Reply,
  Search,
  Send,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  UserRound,
  Users,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  EmailAdminPanel,
  type EmailSenderAlias,
} from "./email-admin-panel";
import { GlobalEmailCompose } from "./global-email-compose";
import {
  MessageAttachment,
  type MessageAttachmentData,
} from "./message-attachment";
import { LinkedMessageText } from "./linked-message-text";
import {
  GeneralEmailActions,
  type LinkableLead,
} from "./general-email-actions";
import {
  CallRecordingPlayer,
  type CallRecordingPlayerHandle,
} from "./call-recording-player";
import { buildCallQuickRead } from "./call-quick-read";
import {
  pendingOutboundTwilioSmsKey,
  SMS_DELIVERY_REFRESH_INTERVAL_MS,
  SMS_DELIVERY_REFRESH_MAX_ATTEMPTS,
} from "./sms-delivery";
import { SmsPermissionControl } from "../_components/sms-permission-control";
import { useWebPhone } from "../_components/web-phone-provider";
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
  conversation_type: "lead" | "transaction" | "buyer" | "general";
  lead_id: string | null;
  buyer_id: string | null;
  contact_id: string;
  seller_name: string;
  property_address: string;
  assigned_user_id: string | null;
  assigned_user_email: string | null;
  assigned_user_display_name: string | null;
  assigned_team_id: string | null;
  source_alias_id: string | null;
  visibility_scope: "standard" | "restricted";
  status: string;
  queue_key: string;
  priority: string;
  mail_category: string | null;
  merged_into_conversation_id: string | null;
  unread_count: number;
  last_activity_at: string | null;
  last_inbound_at: string | null;
  last_outbound_at: string | null;
  response_state: "none" | "waiting" | "due_soon" | "overdue";
  response_kind: "first" | "follow_up" | null;
  response_age_minutes: number | null;
  response_target_minutes: number | null;
  response_due_at: string | null;
  closed_at: string | null;
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
  status_detail: string | null;
  subject: string | null;
  body: string;
  actor_user_id: string | null;
  actor_display_name: string | null;
  occurred_at: string;
  call_id: string | null;
  duration_seconds: number | null;
  recording_id: string | null;
  recording_status: string | null;
  recording_retention_expires_at: string | null;
  recording_deleted_at: string | null;
  transcript: CallTranscript | null;
  attachments: MessageAttachmentData[];
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
  mortgage_balance: string | null;
  mortgage_or_title: string | null;
  repairs: string[];
  objections: string[];
  commitments: string[];
  next_action: string | null;
  follow_up_at: string | null;
  appointment_details: string | null;
  confidence: number;
  evidence: CallNoteEvidence[];
  parcel_id?: string | null;
  acreage?: string | null;
  legal_description?: string | null;
  access_or_frontage?: string | null;
  utilities?: string | null;
  zoning_or_use?: string | null;
  septic_or_perc?: string | null;
  taxes_or_hoa?: string | null;
  terrain_or_environmental_concerns?: string | null;
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
  quick_read_summary: string | null;
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
  source: string | null;
  stage_key: string | null;
  lead_temperature: string | null;
  motivation: string | null;
  desired_timeline: string | null;
  property_condition: string | null;
  occupancy_status: string | null;
  appointment_status: string | null;
  next_follow_up_at: string | null;
  property_type: string | null;
  asset_class: "house" | "land" | null;
  property_parcel_id: string | null;
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

type EmailTemplate = {
  id: string;
  created_by_user_id: string;
  name: string;
  subject_template: string;
  body_template: string;
  is_shared: boolean;
  is_active: boolean;
};

type ConversationResolution = {
  action: string;
  source_conversation_id: string;
  conversation_id: string;
  lead_id: string | null;
  status: string;
  message: string;
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

export type InboxFilterKey =
  | "mine"
  | "unassigned"
  | "team"
  | "needs_reply"
  | "appointments"
  | "unread"
  | "archived";
type MobilePane = "conversations" | "thread" | "details";
export type ComposerChannel = "sms" | "email" | "call" | "note";
const filters: Array<{
  key: InboxFilterKey;
  label: string;
  icon: typeof Inbox;
}> = [
  { key: "mine", label: "Mine", icon: UserRound },
  { key: "unassigned", label: "Unassigned", icon: Inbox },
  { key: "team", label: "Team", icon: Users },
  { key: "needs_reply", label: "Needs reply", icon: Reply },
  { key: "appointments", label: "Appointments", icon: CalendarClock },
  { key: "unread", label: "Unread", icon: MailOpen },
  { key: "archived", label: "Archived", icon: Archive },
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
  { value: "dispositions", label: "Dispositions" },
];

const acquisitionQueueOptions = managerQueueOptions.filter(
  (option) => !["va_prospecting", "dispositions"].includes(option.value),
);

function labelize(value: string | null | undefined) {
  if (!value) return "Not captured";
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function contactPermissionLabel(status: string) {
  if (status === "granted") return "permission recorded";
  if (status === "revoked") return "not permissioned";
  return "permission not recorded";
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

function formatFileSize(sizeBytes: number) {
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${Math.round(sizeBytes / 1024)} KB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatResponseAge(minutes: number | null) {
  if (minutes === null || minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

async function fileToBase64(file: File) {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return window.btoa(binary);
}

function hasNeedsReply(conversation: Conversation) {
  if (conversation.response_state) return conversation.response_state !== "none";
  if (!conversation.last_inbound_at) return false;
  if (!conversation.last_outbound_at) return true;
  return new Date(conversation.last_inbound_at) > new Date(conversation.last_outbound_at);
}

function isRestrictedAlias(alias: EmailSenderAlias) {
  const configuredScope = String(alias.routing_metadata.visibility_scope ?? "").toLowerCase();
  return (
    configuredScope === "restricted" ||
    ["accounting", "closing", "legal", "transaction", "transactions"].includes(
      alias.purpose_key,
    )
  );
}

function parseEmailRecipients(value: string) {
  return Array.from(
    new Set(
      value
        .split(/[;,]/)
        .map((item) => item.trim().toLowerCase())
        .filter(Boolean),
    ),
  );
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

const callNoteFieldOptions: Array<{
  key: keyof StructuredCallNotes;
  label: string;
}> = [
  { key: "motivation", label: "Motivation" },
  { key: "timeline", label: "Timeline" },
  { key: "property_condition", label: "Condition" },
  { key: "occupancy_status", label: "Occupancy" },
  { key: "asking_price", label: "Asking price" },
  { key: "mortgage_balance", label: "Mortgage balance/payoff" },
];

const landCallNoteFieldOptions: Array<{
  key: keyof StructuredCallNotes;
  label: string;
}> = [
  { key: "parcel_id", label: "Parcel / APN" },
  { key: "acreage", label: "Acreage" },
  { key: "legal_description", label: "Legal description" },
  { key: "access_or_frontage", label: "Access / frontage" },
  { key: "utilities", label: "Utilities" },
  { key: "zoning_or_use", label: "Zoning / stated use" },
  { key: "septic_or_perc", label: "Septic / perc" },
  { key: "taxes_or_hoa", label: "Taxes / HOA" },
  { key: "terrain_or_environmental_concerns", label: "Terrain / environmental concerns" },
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
  apiBaseUrl,
  canReview,
  getHeaders,
  onError,
  onReview,
  onRetry,
  onSeekToSeconds,
}: {
  transcript: CallTranscript;
  apiBaseUrl: string;
  canReview: boolean;
  getHeaders: () => Promise<Record<string, string>>;
  onError: (message: string) => void;
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
  onRetry: (transcriptId: string) => Promise<void>;
  onSeekToSeconds?: (seconds: number) => void;
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
  const [retryStatus, setRetryStatus] = useState<"idle" | "saving">("idle");
  const [transcriptDownloadStatus, setTranscriptDownloadStatus] = useState<"idle" | "saving">(
    "idle",
  );
  const quickReadItems = notes
    ? buildCallQuickRead(notes, transcript.quick_read_summary)
    : [];
  const transcriptSegments = transcript.speaker_segments.filter((segment) =>
    Boolean(segment.text?.trim()),
  );
  const hasFullTranscript =
    transcriptSegments.length > 0 || Boolean(transcript.transcript_text?.trim());

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

  const downloadTranscript = async () => {
    setTranscriptDownloadStatus("saving");
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/voice/transcripts/${transcript.id}/download`,
        {
          headers: await getHeaders(),
          cache: "no-store",
        },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(displayError(payload, "Transcript could not be downloaded."));
      }
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `stonegate-call-transcript-${transcript.id}.txt`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      onError(error instanceof Error ? error.message : "Transcript could not be downloaded.");
    } finally {
      setTranscriptDownloadStatus("idle");
    }
  };

  return (
    <>
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
              <strong>
                {transcript.status === "approved" ? "Automatic call summary" : "Processing note"}
              </strong>
              <span>{notes.confidence}% AI confidence</span>
            </div>
            {transcript.status === "approved" ? (
              <p className={styles.mutedText}>
                Saved automatically to this conversation and the seller record. No approval is
                required.
              </p>
            ) : null}
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
                    onChange={(event) => updateNote(item.key, event.target.value || null)}
                    value={String(notes[item.key] ?? "")}
                  />
                </label>
              ))}
              <label>
                Mortgage or title notes
                <input
                  disabled={!canReview || transcript.status !== "needs_review"}
                  onChange={(event) => updateNote("mortgage_or_title", event.target.value || null)}
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
            {landCallNoteFieldOptions.some((item) => Boolean(notes[item.key])) ? (
              <div className={styles.notesGrid}>
                {landCallNoteFieldOptions.map((item) => (
                  <label key={item.key}>
                    {item.label}
                    <input
                      disabled={!canReview || transcript.status !== "needs_review"}
                      onChange={(event) => updateNote(item.key, event.target.value || null)}
                      value={String(notes[item.key] ?? "")}
                    />
                  </label>
                ))}
              </div>
            ) : null}
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
                  <legend>Review auto-filled CRM fields</legend>
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
            {["approved", "completed"].includes(transcript.status) &&
            quickReadItems.length > 0 ? (
              <section className={styles.callQuickRead} aria-label="Quick read">
                <div className={styles.callQuickReadHeader}>
                  <strong>Quick read</strong>
                  <span>Key points from this call</span>
                </div>
                <dl className={styles.callQuickReadList}>
                  {quickReadItems.map((item) => (
                    <div key={item.label}>
                      <dt>{item.label}</dt>
                      <dd>{item.value}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            ) : null}
          </section>
        ) : (
          <div className={styles.transcriptPending}>
            <p>
              {transcript.status === "exhausted"
                ? "Call intelligence stopped after repeated failures. Retry it when the provider is healthy."
                : transcript.status === "failed"
                  ? "Call intelligence hit a temporary problem and will retry automatically."
                  : transcript.status === "processing"
                    ? "AI is transcribing this recording and preparing the notes."
                    : "Recording is queued for transcription."}
            </p>
            {transcript.status === "exhausted" ? (
              <button
                disabled={retryStatus === "saving"}
                onClick={async () => {
                  setRetryStatus("saving");
                  try {
                    await onRetry(transcript.id);
                  } finally {
                    setRetryStatus("idle");
                  }
                }}
                type="button"
              >
                <RefreshCw size={13} aria-hidden="true" />
                {retryStatus === "saving" ? "Queueing" : "Retry call intelligence"}
              </button>
            ) : null}
          </div>
        )}
        </div>
      </details>
      {hasFullTranscript ? (
        <details className={styles.fullTranscriptPanel}>
          <summary>
            <span>
              <FileText size={14} aria-hidden="true" />
              Full transcript
            </span>
            <span>
              {transcriptSegments.length > 0
                ? `${transcriptSegments.length} segments`
                : "Complete call text"}
            </span>
          </summary>
          <div className={styles.fullTranscriptBody}>
            <button
              disabled={transcriptDownloadStatus === "saving"}
              onClick={() => void downloadTranscript()}
              type="button"
            >
              <Download size={13} aria-hidden="true" />
              {transcriptDownloadStatus === "saving"
                ? "Downloading transcript"
                : "Download transcript (.txt)"}
            </button>
            <div className={styles.transcriptText}>
              <div>
                {transcriptSegments.length > 0 ? (
                  transcriptSegments.map((segment, index) => (
                    <p key={`${segment.start ?? 0}-${index}`}>
                      <span className={styles.transcriptSegmentHeader}>
                        <strong>{segment.speaker || "Speaker"}</strong>
                        {onSeekToSeconds ? (
                          <button
                            aria-label={`Play recording from ${formatDuration(
                              Math.round(segment.start ?? 0),
                            )}`}
                            onClick={() => onSeekToSeconds(Math.max(0, segment.start ?? 0))}
                            title="Jump recording to this moment"
                            type="button"
                          >
                            <Play size={10} aria-hidden="true" />
                            {formatDuration(Math.round(segment.start ?? 0))}
                          </button>
                        ) : (
                          <span>at {formatDuration(Math.round(segment.start ?? 0))}</span>
                        )}
                      </span>
                      <span>{segment.text}</span>
                    </p>
                  ))
                ) : (
                  <p>
                    <span>{transcript.transcript_text}</span>
                  </p>
                )}
              </div>
            </div>
          </div>
        </details>
      ) : null}
    </>
  );
}

const EMAIL_INBOX_REFRESH_INTERVAL_MS = 15_000;
const MAX_EMAIL_ATTACHMENT_BYTES = 10_000_000;

function replySubjectForTimeline(timeline: TimelineItem[]) {
  const latestEmailSubject = [...timeline]
    .reverse()
    .find(
      (item) =>
        item.item_type === "communication" &&
        item.channel === "email" &&
        Boolean(item.subject?.trim()),
    )
    ?.subject?.trim();
  if (!latestEmailSubject) return "";
  return (/^re:/i.test(latestEmailSubject)
    ? latestEmailSubject
    : `Re: ${latestEmailSubject}`
  ).slice(0, 255);
}

export function InboxWorkspace({
  initialFilter = "team",
  initialConversationId = null,
  initialEmailAdminOpen = false,
  initialGlobalComposeOpen = false,
  initialLeadId = null,
  initialChannel = "sms",
}: {
  initialFilter?: InboxFilterKey;
  initialConversationId?: string | null;
  initialEmailAdminOpen?: boolean;
  initialGlobalComposeOpen?: boolean;
  initialLeadId?: string | null;
  initialChannel?: ComposerChannel;
}) {
  const { getToken } = useAuth();
  const webPhone = useWebPhone();
  const timelineEndRef = useRef<HTMLDivElement>(null);
  const smsIdempotencyKeyRef = useRef<string | null>(null);
  const emailIdempotencyKeyRef = useRef<string | null>(null);
  const composerConversationIdRef = useRef<string | null>(null);
  const detailRequestSequenceRef = useRef(0);
  const inboxRefreshInFlightRef = useRef(false);
  const recordingPlayerRefs = useRef<Record<string, CallRecordingPlayerHandle | null>>({});
  const initialSelectionAppliedRef = useRef(false);
  const [me, setMe] = useState<Me | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [assignees, setAssignees] = useState<Assignee[]>([]);
  const [emailAliases, setEmailAliases] = useState<EmailSenderAlias[]>([]);
  const [emailTemplates, setEmailTemplates] = useState<EmailTemplate[]>([]);
  const [emailAliasId, setEmailAliasId] = useState("");
  const [emailProviderConfigured, setEmailProviderConfigured] = useState(false);
  const [emailConfigurationBlockers, setEmailConfigurationBlockers] = useState<string[]>([]);
  const [emailSettingsOpen, setEmailSettingsOpen] = useState(false);
  const [emailAdminOpen, setEmailAdminOpen] = useState(initialEmailAdminOpen);
  const [emailTemplateName, setEmailTemplateName] = useState("");
  const [emailAttachments, setEmailAttachments] = useState<File[]>([]);
  const [emailCc, setEmailCc] = useState("");
  const [emailBcc, setEmailBcc] = useState("");
  const [linkableLeads, setLinkableLeads] = useState<LinkableLead[]>([]);
  const [linkableLeadsLoading, setLinkableLeadsLoading] = useState(false);

  const [globalComposeOpen, setGlobalComposeOpen] = useState(initialGlobalComposeOpen);
  const [mailboxAliasId, setMailboxAliasId] = useState<string | null>(null);
  const [, setEmailSettingsStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<InboxFilterKey>(initialFilter);
  const [search, setSearch] = useState("");
  const [mobilePane, setMobilePane] = useState<MobilePane>("conversations");
  const [channel, setChannel] = useState<ComposerChannel>(initialChannel);
  const [callComposerMode, setCallComposerMode] = useState<
    "browser" | "cellphone" | "log"
  >("browser");
  const [direction, setDirection] = useState<"inbound" | "outbound">("outbound");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [composerStatus, setComposerStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [handoffStatus, setHandoffStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [forwardedCallStatus, setForwardedCallStatus] = useState<
    "idle" | "starting" | "started"
  >("idle");
  const [assigneeId, setAssigneeId] = useState("");
  const [queueKey, setQueueKey] = useState("acquisitions_follow_up");
  const [handoffReason, setHandoffReason] = useState("Reassigned from the shared inbox.");
  const [recordingDeleteTarget, setRecordingDeleteTarget] = useState<string | null>(null);
  const [recordingDeleteReason, setRecordingDeleteReason] = useState("");
  const [recordingDeleteStatus, setRecordingDeleteStatus] = useState<"idle" | "deleting">("idle");

  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  const getHeaders = useCallback(async () => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
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

  const pendingSmsDeliveryKey = useMemo(
    () => pendingOutboundTwilioSmsKey(detail?.timeline ?? []),
    [detail?.timeline],
  );
  const openConversationId = detail?.id ?? null;

  const loadEmailConfiguration = useCallback(async () => {
    const [aliasesPayload, templatesPayload] = await Promise.all([
      request<{
        items: EmailSenderAlias[];
        provider: string;
        provider_configured: boolean;
        configuration_blockers: string[];
      }>("/api/v1/email/aliases"),
      request<{ items: EmailTemplate[] }>("/api/v1/email/templates"),
    ]);
    setEmailAliases(aliasesPayload.items);
    setEmailTemplates(templatesPayload.items);
    setEmailProviderConfigured(aliasesPayload.provider_configured);
    setEmailConfigurationBlockers(aliasesPayload.configuration_blockers);
    setEmailAliasId((current) => {
      if (
        current &&
        aliasesPayload.items.some((alias) => alias.id === current && alias.can_send)
      ) {
        return current;
      }
      return (
        aliasesPayload.items.find((alias) => alias.is_default && alias.can_send)?.id ??
        aliasesPayload.items.find((alias) => alias.can_send)?.id ??
        ""
      );
    });
    return aliasesPayload.items;
  }, [request]);

  const loadConversations = useCallback(async () => {
    const payload = await request<{ items: Conversation[] }>("/api/v1/inbox/conversations");
    setConversations(payload.items);
    const requestedConversation = !initialSelectionAppliedRef.current
      ? payload.items.find((item) =>
          initialConversationId
            ? item.id === initialConversationId
            : initialLeadId
              ? item.lead_id === initialLeadId
              : false,
        )
      : null;
    initialSelectionAppliedRef.current = true;
    setSelectedId((current) => {
      if (current && payload.items.some((item) => item.id === current)) return current;
      return requestedConversation?.id ?? payload.items[0]?.id ?? null;
    });
    if (requestedConversation) setMobilePane("thread");
    return payload.items;
  }, [initialConversationId, initialLeadId, request]);

  const loadDetail = useCallback(
    async (conversationId: string, options: { silent?: boolean } = {}) => {
      const requestSequence = ++detailRequestSequenceRef.current;
      if (!options.silent) setDetailLoading(true);
      try {
        const item = await request<ConversationDetail>(
          `/api/v1/inbox/conversations/${conversationId}`,
        );
        if (requestSequence !== detailRequestSequenceRef.current) return;
        if (composerConversationIdRef.current !== item.id) {
          composerConversationIdRef.current = item.id;
          setSubject(replySubjectForTimeline(item.timeline));
          setBody("");
          setEmailAttachments([]);
          setEmailCc("");
          setEmailBcc("");
          setEmailSettingsOpen(false);
          setComposerStatus("idle");
          smsIdempotencyKeyRef.current = null;
          emailIdempotencyKeyRef.current = null;
        }
        setDetail(item);
        if (item.conversation_type === "general") {
          setChannel(
            initialConversationId === conversationId && initialChannel === "call"
              ? "call"
              : "email",
          );
          setDirection("outbound");
        }
        setQueueKey(item.conversation_type === "buyer" ? "dispositions" : item.queue_key);
        if (item.unread_count > 0) {
          await request<Conversation>(`/api/v1/inbox/conversations/${conversationId}/read`, {
            method: "PATCH",
          });
          if (requestSequence !== detailRequestSequenceRef.current) return;
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
        if (requestSequence === detailRequestSequenceRef.current && !options.silent) {
          setError(loadError instanceof Error ? loadError.message : "Unable to load conversation.");
          setDetail(null);
        }
      } finally {
        if (requestSequence === detailRequestSequenceRef.current && !options.silent) {
          setDetailLoading(false);
        }
      }
    },
    [initialChannel, initialConversationId, request],
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

  const retryTranscript = useCallback(
    async (transcriptId: string) => {
      await request(`/api/v1/voice/transcripts/${transcriptId}/retry`, {
        method: "POST",
      });
      if (selectedId) {
        await Promise.all([loadConversations(), loadDetail(selectedId)]);
      }
    },
    [loadConversations, loadDetail, request, selectedId],
  );

  const startCellphoneCall = useCallback(async () => {
    if (
      !detail ||
      forwardedCallStatus === "starting" ||
      webPhone.busy ||
      webPhone.status.callActive
    ) return;
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
    setChannel("call");
    setCallComposerMode("cellphone");
    setForwardedCallStatus("starting");
    try {
      await request(`/api/v1/voice/conversations/${detail.id}/forwarded-calls`, {
        method: "POST",
        body: JSON.stringify({ idempotency_key: window.crypto.randomUUID() }),
      });
      setForwardedCallStatus("started");
      window.setTimeout(() => setForwardedCallStatus("idle"), 5000);
      window.setTimeout(() => {
        void Promise.all([loadConversations(), loadDetail(detail.id)]);
      }, 1200);
    } catch (callError) {
      setForwardedCallStatus("idle");
      setError(callError instanceof Error ? callError.message : "Call could not start.");
    }
  }, [detail, forwardedCallStatus, loadConversations, loadDetail, me, request, webPhone]);

  const startBrowserCall = useCallback(async () => {
    if (!detail || webPhone.busy) return;
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
    setChannel("call");
    setCallComposerMode("browser");
    try {
      const intent = await request<VoiceCallIntent>(
        `/api/v1/voice/conversations/${detail.id}/call-intents`,
        {
          method: "POST",
          body: JSON.stringify({ idempotency_key: window.crypto.randomUUID() }),
        },
      );
      await webPhone.startCall({
        callIntentId: intent.id,
        contextHref: `/os/inbox?conversation=${encodeURIComponent(detail.id)}&channel=call`,
        contextLabel:
          detail.conversation_type === "buyer"
            ? "Buyer conversation"
            : detail.conversation_type === "general"
              ? "Company conversation"
              : detail.property_address || "Seller conversation",
        displayName: detail.seller_name,
        fromNumber: intent.from_number,
        phoneNumber: intent.recipient,
      });
      window.setTimeout(() => {
        void Promise.all([loadConversations(), loadDetail(detail.id)]);
      }, 1200);
    } catch (callError) {
      setError(callError instanceof Error ? callError.message : "Browser call could not start.");
    }
  }, [detail, loadConversations, loadDetail, me, request, webPhone]);

  async function submitRecordingDeletion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail || !recordingDeleteTarget || recordingDeleteReason.trim().length < 10) return;
    setRecordingDeleteStatus("deleting");
    setError(null);
    try {
      await request(`/api/v1/voice/recordings/${recordingDeleteTarget}`, {
        method: "DELETE",
        body: JSON.stringify({ reason: recordingDeleteReason.trim() }),
      });
      setRecordingDeleteTarget(null);
      setRecordingDeleteReason("");
      await loadDetail(detail.id);
    } catch (deleteError) {
      setError(
        deleteError instanceof Error ? deleteError.message : "Recording could not be deleted.",
      );
    } finally {
      setRecordingDeleteStatus("idle");
    }
  }

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
        if (
          currentUser.permissions.includes("communications:send_email") ||
          currentUser.permissions.includes("communications:send_assigned_email")
        ) {
          await loadEmailConfiguration();
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
  }, [loadConversations, loadEmailConfiguration, request]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      if (selectedId) void loadDetail(selectedId);
      else {
        composerConversationIdRef.current = null;
        setDetail(null);
      }
    }, 0);
    return () => window.clearTimeout(handle);
  }, [loadDetail, selectedId]);

  useEffect(() => {
    const handle = window.setInterval(() => {
      if (
        document.visibilityState !== "visible" ||
        inboxRefreshInFlightRef.current
      ) {
        return;
      }
      inboxRefreshInFlightRef.current = true;
      const refreshes: Promise<unknown>[] = [loadConversations()];
      if (selectedId) refreshes.push(loadDetail(selectedId, { silent: true }));
      void Promise.allSettled(refreshes).finally(() => {
        inboxRefreshInFlightRef.current = false;
      });
    }, EMAIL_INBOX_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(handle);
  }, [loadConversations, loadDetail, selectedId]);

  useEffect(() => {
    if (!openConversationId || !pendingSmsDeliveryKey) return;

    const conversationId = openConversationId;
    let active = true;
    let attemptCount = 0;
    let timer: number | null = null;

    async function refreshPendingSmsDelivery() {
      attemptCount += 1;
      try {
        const refreshed = await request<ConversationDetail>(
          `/api/v1/inbox/conversations/${conversationId}`,
        );
        if (!active) return;
        setDetail((current) => (current?.id === conversationId ? refreshed : current));
        if (
          !pendingOutboundTwilioSmsKey(refreshed.timeline) ||
          attemptCount >= SMS_DELIVERY_REFRESH_MAX_ATTEMPTS
        ) {
          return;
        }
      } catch {
        if (!active || attemptCount >= SMS_DELIVERY_REFRESH_MAX_ATTEMPTS) return;
      }

      timer = window.setTimeout(
        () => void refreshPendingSmsDelivery(),
        SMS_DELIVERY_REFRESH_INTERVAL_MS,
      );
    }

    timer = window.setTimeout(
      () => void refreshPendingSmsDelivery(),
      SMS_DELIVERY_REFRESH_INTERVAL_MS,
    );
    return () => {
      active = false;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [openConversationId, pendingSmsDeliveryKey, request]);

  useEffect(() => {
    if (detail?.conversation_type !== "general" || !me?.permissions.includes("leads:edit")) {
      return;
    }
    let active = true;
    async function loadLinkableLeads() {
      setLinkableLeadsLoading(true);
      try {
        const payload = await request<{ items: LinkableLead[] }>("/api/v1/leads");
        if (active) setLinkableLeads(payload.items);
      } catch (loadError) {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : "Unable to load seller leads.");
        }
      } finally {
        if (active) setLinkableLeadsLoading(false);
      }
    }
    void loadLinkableLeads();
    return () => {
      active = false;
    };
  }, [detail?.conversation_type, me?.permissions, request]);

  useEffect(() => {
    timelineEndRef.current?.scrollIntoView({ block: "end" });
  }, [detail?.id, detail?.timeline.length]);

  const counts = useMemo(() => {
    const currentUserId = me?.user_id;
    const active = conversations.filter((item) => item.status !== "closed");
    return {
      mine: active.filter((item) => item.assigned_user_id === currentUserId).length,
      unassigned: active.filter((item) => !item.assigned_user_id).length,
      team: active.length,
      needs_reply: active.filter(hasNeedsReply).length,
      appointments: active.filter((item) => item.queue_key === "appointment_set").length,
      unread: active.filter((item) => item.unread_count > 0).length,
      archived: conversations.filter((item) => item.status === "closed").length,
      overdue: active.filter((item) => item.response_state === "overdue").length,
    };
  }, [conversations, me?.user_id]);

  const mailboxGroups = useMemo(() => {
    const activeAliases = emailAliases.filter(
      (alias) => alias.status === "active" && alias.inbound_enabled,
    );
    const restricted = activeAliases.filter(isRestrictedAlias);
    const standardAliases = activeAliases.filter((alias) => !isRestrictedAlias(alias));
    const mine = standardAliases.filter(
      (alias) =>
        alias.owner_user_id === me?.user_id ||
        alias.grants.some((grant) => grant.user_id === me?.user_id),
    );
    const myAliasIds = new Set(mine.map((alias) => alias.id));
    const team = standardAliases.filter(
      (alias) =>
        !myAliasIds.has(alias.id) &&
        (alias.alias_type === "department" ||
          Boolean(alias.assigned_team_id) ||
          alias.owner_user_id !== me?.user_id),
    );
    return { mine, team, restricted };
  }, [emailAliases, me?.user_id]);

  const selectedMailboxAlias =
    emailAliases.find((alias) => alias.id === mailboxAliasId) ?? null;

  const visibleConversations = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return conversations.filter((item) => {
      const matchesMailbox =
        mailboxAliasId === null || item.source_alias_id === mailboxAliasId;
      const matchesFilter =
        filter === "archived"
          ? item.status === "closed"
          : item.status !== "closed" &&
            (filter === "team" ||
              (filter === "mine" && item.assigned_user_id === me?.user_id) ||
              (filter === "unassigned" && !item.assigned_user_id) ||
              (filter === "needs_reply" && hasNeedsReply(item)) ||
              (filter === "appointments" && item.queue_key === "appointment_set") ||
              (filter === "unread" && item.unread_count > 0));
      const matchesSearch =
        !normalizedSearch ||
        item.seller_name.toLowerCase().includes(normalizedSearch) ||
        item.property_address.toLowerCase().includes(normalizedSearch) ||
        emailAliases
          .find((alias) => alias.id === item.source_alias_id)
          ?.email_address.toLowerCase()
          .includes(normalizedSearch);
      return matchesMailbox && matchesFilter && matchesSearch;
    });
  }, [conversations, emailAliases, filter, mailboxAliasId, me?.user_id, search]);

  const canHandoff =
    me?.permissions.includes("communications:manage_assignments") ||
    me?.permissions.includes("communications:handoff_assigned");
  const canManageAssignments = me?.permissions.includes("communications:manage_assignments");
  const queueOptions = detail?.conversation_type === "buyer"
    ? managerQueueOptions.filter((option) => option.value === "dispositions")
    : canManageAssignments
      ? managerQueueOptions.filter((option) => option.value !== "dispositions")
      : acquisitionQueueOptions;
  const primaryPhone = detail?.contact_methods.find((method) => method.method_type === "phone");
  const primaryEmail = detail?.contact_methods.find((method) => method.method_type === "email");
  const selectedEmailAlias =
    emailAliases.find((alias) => alias.id === emailAliasId && alias.can_send) ?? null;
  const emailSignature = selectedEmailAlias?.signature_text ?? "";
  const hasEmailSignature = Boolean(emailSignature.trim());
  const emailAttachmentBytes = emailAttachments.reduce((total, file) => total + file.size, 0);
  const emailAttachmentsWithinLimit = emailAttachmentBytes <= MAX_EMAIL_ATTACHMENT_BYTES;
  const nextAppointment = detail?.appointments.find((appointment) =>
    ["scheduled", "rescheduled"].includes(appointment.status),
  );
  const nextTask = detail?.open_tasks[0];
  const callNotes = useMemo(
    () =>
      (detail?.timeline ?? [])
        .filter(
          (item): item is TimelineItem & { transcript: CallTranscript } =>
            Boolean(item.call_id && item.transcript?.structured_notes),
        )
        .sort(
          (left, right) =>
            new Date(right.occurred_at).getTime() - new Date(left.occurred_at).getTime(),
        ),
    [detail?.timeline],
  );
  const isLiveSms = channel === "sms" && direction === "outbound";
  const isLiveEmail = channel === "email";
  const isVoiceComposer = channel === "call" && callComposerMode !== "log";
  const canUseSms =
    me?.permissions.includes("communications:send_sms") ||
    me?.permissions.includes("communications:send_assigned_sms");
  const canManageSmsPermission =
    me?.permissions.includes("leads:edit") ||
    me?.permissions.includes("communications:send_sms") ||
    (me?.permissions.includes("communications:send_assigned_sms") &&
      detail?.assigned_user_id === me.user_id);
  const canManagePhonePermission =
    me?.permissions.includes("leads:edit") ||
    me?.permissions.includes("communications:place_calls") ||
    (me?.permissions.includes("communications:place_assigned_calls") &&
      detail?.assigned_user_id === me.user_id);
  const canUseEmail =
    me?.permissions.includes("communications:send_email") ||
    me?.permissions.includes("communications:send_assigned_email");
  const canComposeGlobalEmail = me?.permissions.includes("communications:send_email");
  const canSubmitComposer =
    Boolean(body.trim()) &&
    composerStatus !== "saving" &&
    !isVoiceComposer &&
    (!isLiveSms || Boolean(canUseSms && detail?.sms_eligibility.can_send)) &&
    (!isLiveEmail ||
      Boolean(
        canUseEmail &&
          primaryEmail &&
          emailProviderConfigured &&
          selectedEmailAlias?.can_send &&
          hasEmailSignature &&
          emailAttachmentsWithinLimit &&
          subject.trim(),
      ));

  function selectConversation(conversationId: string) {
    if (conversationId === selectedId) {
      setMobilePane("thread");
      setError(null);
      return;
    }
    detailRequestSequenceRef.current += 1;
    setDetail(null);
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

  async function convertGeneralEmailToLead(property: {
    asset_class: "house" | "land";
    street_address: string;
    city: string;
    state: string;
    postal_code: string;
    county: string | null;
    property_type: string | null;
    parcel_id: string | null;
  }) {
    if (!detail) return;
    setError(null);
    try {
      const { asset_class, ...propertyPayload } = property;
      const result = await request<ConversationResolution>(
        `/api/v1/inbox/conversations/${detail.id}/convert-to-lead`,
        {
          method: "POST",
          body: JSON.stringify({
            asset_class,
            property: propertyPayload,
            source: "inbound_email",
          }),
        },
      );
      setMailboxAliasId(null);
      setFilter("team");
      await loadConversations();
      setSelectedId(result.conversation_id);
      await loadDetail(result.conversation_id);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Email could not be converted.");
      throw actionError;
    }
  }

  async function linkGeneralEmailToLead(leadId: string) {
    if (!detail) return;
    setError(null);
    try {
      const result = await request<ConversationResolution>(
        `/api/v1/inbox/conversations/${detail.id}/link-to-lead`,
        { method: "POST", body: JSON.stringify({ lead_id: leadId }) },
      );
      setMailboxAliasId(null);
      setFilter("team");
      await loadConversations();
      setSelectedId(result.conversation_id);
      await loadDetail(result.conversation_id);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Email could not be linked.");
      throw actionError;
    }
  }

  async function classifyGeneralEmail(
    category: "general" | "vendor" | "administrative" | "spam" | "archived",
    close: boolean,
    reason?: string,
  ) {
    if (!detail) return;
    setError(null);
    try {
      const result = await request<ConversationResolution>(
        `/api/v1/inbox/conversations/${detail.id}/classification`,
        {
          method: "POST",
          body: JSON.stringify({ category, close, reason: reason ?? null }),
        },
      );
      setMailboxAliasId(null);
      setFilter(close ? "archived" : "team");
      await loadConversations();
      setSelectedId(result.conversation_id);
      await loadDetail(result.conversation_id);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Email could not be classified.");
      throw actionError;
    }
  }

  async function openMergedConversation(conversationId: string) {
    setMailboxAliasId(null);
    setFilter("team");
    setSelectedId(conversationId);
    await loadConversations();
    await loadDetail(conversationId);
  }

  async function handleGlobalEmailSent(conversationId: string) {
    setMailboxAliasId(null);
    setFilter("team");
    setSelectedId(conversationId);
    setMobilePane("thread");
    await loadConversations();
    await loadDetail(conversationId);
    setGlobalComposeOpen(false);
  }

  async function saveCurrentEmailAsTemplate() {
    if (!emailTemplateName.trim() || !subject.trim() || !body.trim()) return;
    setEmailSettingsStatus("saving");
    setError(null);
    try {
      await request("/api/v1/email/templates", {
        method: "POST",
        body: JSON.stringify({
          name: emailTemplateName.trim(),
          subject_template: subject.trim(),
          body_template: body.trim(),
          is_shared: true,
        }),
      });
      setEmailTemplateName("");
      await loadEmailConfiguration();
      setEmailSettingsStatus("saved");
      window.setTimeout(() => setEmailSettingsStatus("idle"), 1500);
    } catch (templateError) {
      setEmailSettingsStatus("idle");
      setError(
        templateError instanceof Error ? templateError.message : "The template could not be saved.",
      );
    }
  }

  function applyEmailTemplate(templateId: string) {
    const template = emailTemplates.find((item) => item.id === templateId);
    if (!template) return;
    setSubject(template.subject_template);
    setBody(template.body_template);
    emailIdempotencyKeyRef.current = null;
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
      } else if (isLiveEmail && selectedEmailAlias) {
        emailIdempotencyKeyRef.current ??= window.crypto.randomUUID();
        const attachments = await Promise.all(
          emailAttachments.map(async (file) => ({
            filename: file.name,
            content_type: file.type || "application/octet-stream",
            content_base64: await fileToBase64(file),
          })),
        );
        await request(`/api/v1/email/conversations/${detail.id}/messages`, {
          method: "POST",
          body: JSON.stringify({
            email_sender_alias_id: selectedEmailAlias.id,
            subject: subject.trim(),
            body: body.trim(),
            cc: parseEmailRecipients(emailCc),
            bcc: parseEmailRecipients(emailBcc),
            idempotency_key: emailIdempotencyKeyRef.current,
            attachments,
          }),
        });
        emailIdempotencyKeyRef.current = null;
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
      if (!isLiveEmail) setSubject("");
      setBody("");
      setEmailAttachments([]);
      setEmailCc("");
      setEmailBcc("");
      setComposerStatus("saved");
      await Promise.all([loadConversations(), loadDetail(detail.id)]);
      window.setTimeout(() => setComposerStatus("idle"), 1800);
    } catch (submitError) {
      setComposerStatus("idle");
      setError(
        submitError instanceof Error
          ? submitError.message
          : isLiveEmail
            ? "Unable to send email."
            : "Unable to log communication.",
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
          <p className={styles.eyebrow}>Seller communications</p>
          <h1>Inbox</h1>
          <span className={styles.headerSummary}>
            {counts.needs_reply} need reply · {counts.overdue} overdue · {counts.unread} unread
          </span>
        </div>
        <div className={styles.headerActions}>
          {canComposeGlobalEmail ? (
            <button
              className={styles.composeEmailButton}
              disabled={!emailProviderConfigured || !emailAliases.some((alias) => alias.can_send)}
              onClick={() => setGlobalComposeOpen(true)}
              title="Compose a new company email"
              type="button"
            >
              <Plus size={16} aria-hidden="true" />
              Compose
            </button>
          ) : null}
          {canUseEmail ? (
            <button
              className={styles.emailStatusButton}
              data-connected={emailAliases.some((alias) => alias.can_send)}
              onClick={() => {
                setChannel("email");
                if (me?.permissions.includes("communications:manage_email_accounts")) {
                  setEmailAdminOpen(true);
                } else {
                  setEmailSettingsOpen(true);
                }
              }}
              title={
                me?.permissions.includes("communications:manage_email_accounts")
                  ? "Manage Stonegate email"
                  : "View available email sender"
              }
              type="button"
            >
              <Mail size={16} aria-hidden="true" />
              {emailAliases.some((alias) => alias.can_send) ? "Email ready" : "Email unavailable"}
            </button>
          ) : null}
          <button
            className={styles.refreshButton}
            onClick={() => void refreshInbox()}
            type="button"
          >
            <RefreshCw size={16} aria-hidden="true" />
            Refresh
          </button>
        </div>
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
                  className={
                    mailboxAliasId === null && filter === item.key
                      ? styles.activeFilter
                      : undefined
                  }
                  key={item.key}
                  onClick={() => {
                    setMailboxAliasId(null);
                    setFilter(item.key);
                  }}
                  type="button"
                >
                  <Icon size={16} aria-hidden="true" />
                  <span>{item.label}</span>
                  <strong>{counts[item.key]}</strong>
                </button>
              );
            })}
          </div>

          {emailAliases.length > 0 ? (
            <nav className={styles.mailboxRail} aria-label="Email mailboxes">
              {(
                [
                  ["My addresses", mailboxGroups.mine],
                  ["Team inboxes", mailboxGroups.team],
                  ["Restricted", mailboxGroups.restricted],
                ] as const
              ).map(([label, aliases]) =>
                aliases.length > 0 ? (
                  <section key={label}>
                    <span>{label}</span>
                    {aliases.map((alias) => {
                      const aliasConversations = conversations.filter(
                        (conversation) =>
                          conversation.source_alias_id === alias.id &&
                          conversation.status !== "closed",
                      );
                      const aliasUnread = aliasConversations.reduce(
                        (total, conversation) => total + conversation.unread_count,
                        0,
                      );
                      return (
                        <button
                          className={
                            mailboxAliasId === alias.id ? styles.activeMailbox : undefined
                          }
                          key={alias.id}
                          onClick={() => {
                            setMailboxAliasId(alias.id);
                            setFilter("team");
                          }}
                          title={alias.email_address}
                          type="button"
                        >
                          {isRestrictedAlias(alias) ? (
                            <ShieldCheck size={14} aria-hidden="true" />
                          ) : (
                            <Mail size={14} aria-hidden="true" />
                          )}
                          <span>{alias.display_name}</span>
                          <strong>{aliasUnread || aliasConversations.length}</strong>
                        </button>
                      );
                    })}
                  </section>
                ) : null,
              )}
            </nav>
          ) : null}

          <div className={styles.listHeader}>
            <div>
              <strong>
                {selectedMailboxAlias?.display_name ??
                  filters.find((item) => item.key === filter)?.label}
              </strong>
              <span>{visibleConversations.length} conversations</span>
            </div>
            {selectedMailboxAlias ? (
              <span className={styles.mailboxContext}>
                {selectedMailboxAlias.email_address}
                {isRestrictedAlias(selectedMailboxAlias) ? " · Restricted" : ""}
              </span>
            ) : null}
            <label className={styles.searchBox}>
              <Search size={15} aria-hidden="true" />
              <input
                aria-label="Search conversations"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search contact, subject, or property"
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
                    <span>
                      {emailAliases.find((alias) => alias.id === item.source_alias_id)
                        ?.display_name ?? labelize(item.queue_key)}
                    </span>
                    {item.priority === "urgent" ? <em className={styles.urgentLabel}>Urgent</em> : null}
                    {hasNeedsReply(item) ? (
                      <em
                        className={styles.responseBadge}
                        data-state={item.response_state}
                      >
                        {item.response_state === "overdue" ? "Overdue" : "Waiting"}{" "}
                        {formatResponseAge(item.response_age_minutes)}
                      </em>
                    ) : null}
                  </span>
                </span>
                {item.unread_count > 0 ? (
                  <span className={styles.unreadBadge}>{item.unread_count}</span>
                ) : null}
              </button>
            ))}
          </div>
        </aside>

        <section aria-label="Conversation thread" className={styles.threadPane} data-mobile-active={mobilePane === "thread"}>
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
                    <span className={styles.stageBadge}>
                      {detail.conversation_type === "general"
                        ? detail.status === "closed"
                          ? labelize(detail.mail_category || "archived")
                          : "Company conversation"
                        : detail.conversation_type === "buyer"
                          ? "Buyer"
                          : labelize(detail.stage_key)}
                    </span>
                  </div>
                  <p>
                    {detail.conversation_type === "general"
                      ? emailAliases.find((alias) => alias.id === detail.source_alias_id)
                          ?.email_address || primaryPhone?.value || "Stonegate company conversation"
                      : detail.conversation_type === "buyer"
                        ? "Stonegate dispositions relationship"
                      : detail.property_address}
                  </p>
                  {detail.response_state !== "none" ? (
                    <span
                      className={styles.threadResponseStatus}
                      data-state={detail.response_state}
                    >
                      {detail.response_kind === "first" ? "First response" : "Follow-up"}{" "}
                      {detail.response_state === "overdue" ? "overdue" : "due"} · waiting{" "}
                      {formatResponseAge(detail.response_age_minutes)}
                    </span>
                  ) : null}
                </div>
                <div className={styles.contactActions}>
                  {primaryPhone ? (
                    <button
                      disabled={webPhone.busy || webPhone.status.callActive}
                      onClick={() => void startBrowserCall()}
                      title={`Call ${primaryPhone.value} in the Stonegate browser phone`}
                      type="button"
                    >
                      <Phone size={17} aria-hidden="true" />
                      <span className={styles.visuallyHidden}>Call seller</span>
                    </button>
                  ) : null}
                  {primaryEmail ? (
                    <button
                      onClick={() => {
                        setChannel("email");
                        setDirection("outbound");
                      }}
                      title={`Email ${primaryEmail.value}`}
                      type="button"
                    >
                      <Mail size={17} aria-hidden="true" />
                      <span className={styles.visuallyHidden}>Email seller</span>
                    </button>
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
                      id={item.call_id ? `call-${item.call_id}` : undefined}
                      key={item.id}
                    >
                      <div className={styles.messageMeta}>
                        <span>
                          {item.channel === "sms" && item.attachments.length > 0
                            ? "MMS"
                            : labelize(item.channel)}
                        </span>
                        <time>{formatDateTime(item.occurred_at)}</time>
                      </div>
                      {item.subject ? <strong>{item.subject}</strong> : null}
                      {item.body.trim() ? (
                        <p>
                          <LinkedMessageText text={item.body} />
                        </p>
                      ) : null}
                      {item.attachments.length > 0 ? (
                        <div className={styles.messageAttachments}>
                          {item.attachments.map((attachment) => (
                            <MessageAttachment
                              apiBaseUrl={apiBaseUrl}
                              attachment={attachment}
                              formatSize={formatFileSize}
                              getHeaders={getHeaders}
                              key={attachment.id}
                              senderLabel={
                                item.direction === "inbound"
                                  ? detail.seller_name
                                  : item.actor_display_name || "Stonegate"
                              }
                            />
                          ))}
                        </div>
                      ) : null}
                      {item.channel === "call" ? (
                        <>
                          <div className={styles.callMetadata}>
                            <span>{formatDuration(item.duration_seconds)}</span>
                            <div className={styles.recordingControls}>
                              {item.recording_id &&
                              item.recording_status === "completed" &&
                              me?.permissions.includes("communications:access_recordings") ? (
                                <CallRecordingPlayer
                                  apiBaseUrl={apiBaseUrl}
                                  getHeaders={getHeaders}
                                  onError={setError}
                                  ref={(player) => {
                                    const recordingId = item.recording_id as string;
                                    if (player) recordingPlayerRefs.current[recordingId] = player;
                                    else delete recordingPlayerRefs.current[recordingId];
                                  }}
                                  recordingId={item.recording_id}
                                />
                              ) : item.recording_status === "deleted" ? (
                                <span>
                                  Audio deleted
                                  {item.recording_deleted_at
                                    ? ` ${formatDateTime(item.recording_deleted_at)}`
                                    : ""}
                                </span>
                              ) : item.recording_status ? (
                                <span>Recording {labelize(item.recording_status)}</span>
                              ) : null}
                              {item.recording_id &&
                              item.recording_status === "completed" &&
                              me?.permissions.includes("communications:manage_recordings") ? (
                                <button
                                  className={styles.deleteRecordingButton}
                                  onClick={() => {
                                    setRecordingDeleteTarget(item.recording_id);
                                    setRecordingDeleteReason("");
                                  }}
                                  title="Delete call audio"
                                  type="button"
                                >
                                  <Trash2 size={13} aria-hidden="true" />
                                  <span className={styles.visuallyHidden}>Delete call audio</span>
                                </button>
                              ) : null}
                            </div>
                          </div>
                          {item.recording_status === "completed" &&
                          item.recording_retention_expires_at ? (
                            <span className={styles.retentionLabel}>
                              Audio retained until{" "}
                              {formatDateTime(item.recording_retention_expires_at)}
                            </span>
                          ) : null}
                          {recordingDeleteTarget === item.recording_id ? (
                            <form
                              className={styles.recordingDeleteForm}
                              onSubmit={submitRecordingDeletion}
                            >
                              <label>
                                Deletion reason
                                <input
                                  autoFocus
                                  minLength={10}
                                  onChange={(event) => setRecordingDeleteReason(event.target.value)}
                                  placeholder="Why must this audio be deleted early?"
                                  required
                                  value={recordingDeleteReason}
                                />
                              </label>
                              <div>
                                <button
                                  disabled={recordingDeleteStatus === "deleting"}
                                  onClick={() => {
                                    setRecordingDeleteTarget(null);
                                    setRecordingDeleteReason("");
                                  }}
                                  type="button"
                                >
                                  Cancel
                                </button>
                                <button
                                  className={styles.confirmRecordingDeleteButton}
                                  disabled={
                                    recordingDeleteStatus === "deleting" ||
                                    recordingDeleteReason.trim().length < 10
                                  }
                                  type="submit"
                                >
                                  <Trash2 size={13} aria-hidden="true" />
                                  {recordingDeleteStatus === "deleting"
                                    ? "Deleting"
                                    : "Delete audio"}
                                </button>
                              </div>
                            </form>
                          ) : null}
                          {item.transcript &&
                          me?.permissions.includes("communications:access_recordings") ? (
                            <CallTranscriptPanel
                              apiBaseUrl={apiBaseUrl}
                              canReview={Boolean(
                                detail.lead_id &&
                                me.permissions.includes("leads:edit") &&
                                item.recording_status === "completed" &&
                                me.permissions.includes("communications:access_recordings"),
                              )}
                              getHeaders={getHeaders}
                              key={item.transcript.id}
                              onError={setError}
                              onReview={reviewTranscript}
                              onRetry={retryTranscript}
                              onSeekToSeconds={
                                item.recording_id && item.recording_status === "completed"
                                  ? (seconds) => {
                                      void recordingPlayerRefs.current[item.recording_id as string]?.seekTo(
                                        seconds,
                                        { play: true },
                                      );
                                    }
                                  : undefined
                              }
                              transcript={item.transcript}
                            />
                          ) : null}
                        </>
                      ) : null}
                      <small>
                        {item.actor_display_name ||
                          (item.direction === "inbound"
                            ? detail.conversation_type === "buyer" ? "Buyer" : "Seller"
                            : "Team")}
                        {" · "}
                        {labelize(item.status)}
                      </small>
                      {item.status_detail ? (
                        <span className={styles.deliveryFailure}>
                          <CircleAlert aria-hidden="true" size={13} />
                          {item.status_detail}
                        </span>
                      ) : null}
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
                <div
                  className={styles.composerTabs}
                  role="tablist"
                  aria-label="Communication channel"
                >
                  {composerChannels
                    .filter(
                      (item) =>
                        detail.conversation_type !== "general" ||
                        item.key === "email" ||
                        (item.key === "call" &&
                          Boolean(me?.permissions.includes("communications:place_calls"))),
                    )
                    .map((item) => {
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
                          <Headphones size={13} aria-hidden="true" />
                          Browser
                        </button>
                        <button
                          className={
                            callComposerMode === "cellphone" ? styles.activeDirection : undefined
                          }
                          onClick={() => setCallComposerMode("cellphone")}
                          type="button"
                        >
                          <PhoneCall size={13} aria-hidden="true" />
                          My cellphone
                        </button>
                        <button
                          className={
                            callComposerMode === "log" ? styles.activeDirection : undefined
                          }
                          onClick={() => setCallComposerMode("log")}
                          type="button"
                        >
                          <NotebookPen size={13} aria-hidden="true" />
                          Log call
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
                            className={direction === "inbound" ? styles.activeDirection : undefined}
                            onClick={() => setDirection("inbound")}
                            type="button"
                          >
                            Inbound
                          </button>
                        </div>
                      ) : (
                        <span className={styles.voiceLabel}>
                          {callComposerMode === "browser" ? (
                            <Headphones size={14} aria-hidden="true" />
                          ) : (
                            <PhoneCall size={14} aria-hidden="true" />
                          )}
                          {callComposerMode === "browser"
                            ? "Stonegate browser phone"
                            : "Stonegate cellphone bridge"}
                        </span>
                      )}
                    </>
                  ) : channel === "sms" ? (
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
                  ) : channel === "email" ? (
                    <div className={styles.emailComposerControls}>
                      <select
                        aria-label="Email sender"
                        onChange={(event) => {
                          setEmailAliasId(event.target.value);
                          emailIdempotencyKeyRef.current = null;
                        }}
                        value={emailAliasId}
                      >
                        <option value="">Select sender</option>
                        {emailAliases
                          .filter((alias) => alias.can_send)
                          .map((alias) => (
                            <option key={alias.id} value={alias.id}>
                              {alias.display_name} · {alias.email_address}
                            </option>
                          ))}
                      </select>
                      <select
                        aria-label="Email template"
                        defaultValue=""
                        onChange={(event) => {
                          applyEmailTemplate(event.target.value);
                          event.target.value = "";
                        }}
                      >
                        <option value="">Use template</option>
                        {emailTemplates.map((template) => (
                          <option key={template.id} value={template.id}>
                            {template.name}
                          </option>
                        ))}
                      </select>
                      <button
                        aria-pressed={emailSettingsOpen}
                        className={styles.emailSettingsToggle}
                        onClick={() => setEmailSettingsOpen((current) => !current)}
                        title="Email settings"
                        type="button"
                      >
                        <Settings2 size={15} aria-hidden="true" />
                        <span className={styles.visuallyHidden}>Email settings</span>
                      </button>
                    </div>
                  ) : (
                    <span className={styles.internalLabel}>Internal note</span>
                  )}
                  {channel === "email" ? (
                    <input
                      aria-label="Email subject"
                      maxLength={255}
                      onChange={(event) => {
                        setSubject(event.target.value);
                        emailIdempotencyKeyRef.current = null;
                      }}
                      placeholder="Subject"
                      value={subject}
                    />
                  ) : null}
                </div>
                {isLiveEmail && emailSettingsOpen ? (
                  <div className={styles.emailSettingsPanel}>
                    <div className={styles.emailSettingsHeader}>
                      <div>
                        <strong>Stonegate sender</strong>
                        <span>
                          {selectedEmailAlias
                            ? selectedEmailAlias.email_address
                            : "No authorized sender"}
                        </span>
                      </div>
                      {me?.permissions.includes("communications:manage_email_accounts") ? (
                        <button onClick={() => setEmailAdminOpen(true)} type="button">
                          <Settings2 size={14} aria-hidden="true" />
                          Manage senders
                        </button>
                      ) : null}
                    </div>
                    {!emailProviderConfigured ? (
                      <p className={styles.emailConfigurationNote}>
                        {emailConfigurationBlockers.join(" ") ||
                          "Resend production delivery is not configured yet."}
                      </p>
                    ) : null}
                    <div className={styles.emailRecipientFields}>
                      <label>
                        <span>To</span>
                        <input
                          disabled
                          value={primaryEmail?.value ?? "No contact email"}
                        />
                      </label>
                      <label>
                        <span>CC</span>
                        <input
                          onChange={(event) => {
                            setEmailCc(event.target.value);
                            emailIdempotencyKeyRef.current = null;
                          }}
                          placeholder="Optional, separate with commas"
                          value={emailCc}
                        />
                      </label>
                      <label>
                        <span>BCC</span>
                        <input
                          onChange={(event) => {
                            setEmailBcc(event.target.value);
                            emailIdempotencyKeyRef.current = null;
                          }}
                          placeholder="Optional, separate with commas"
                          value={emailBcc}
                        />
                      </label>
                    </div>
                    {selectedEmailAlias ? (
                      <div className={styles.emailSettingsGrid}>
                        <div>
                          <strong>{selectedEmailAlias.display_name}</strong>
                          <span>
                            {selectedEmailAlias.owner_user_name ||
                              selectedEmailAlias.assigned_team_name ||
                              "Company managed"}
                          </span>
                        </div>
                        <div>
                          <strong>Signature</strong>
                          <span>{emailSignature || "No signature configured"}</span>
                        </div>
                      </div>
                    ) : null}
                    <div className={styles.emailTemplateBuilder}>
                      <input
                        maxLength={160}
                        onChange={(event) => setEmailTemplateName(event.target.value)}
                        placeholder="Template name"
                        value={emailTemplateName}
                      />
                      <button
                        disabled={!emailTemplateName.trim() || !subject.trim() || !body.trim()}
                        onClick={() => void saveCurrentEmailAsTemplate()}
                        type="button"
                      >
                        <Plus size={14} aria-hidden="true" />
                        Save current draft
                      </button>
                    </div>
                  </div>
                ) : null}
                {isLiveSms ? (
                  <div
                    className={
                      detail.sms_eligibility.can_send ? styles.smsReady : styles.smsBlocked
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
                          ? `Ready to send to ${detail.sms_eligibility.recipient} · ${contactPermissionLabel(detail.sms_eligibility.consent_status)}`
                          : "Your role cannot send seller text messages."
                        : detail.sms_eligibility.blockers.join(" ")}
                    </span>
                  </div>
                ) : null}
                {isLiveEmail ? (
                  <>
                    <div
                      className={
                        canUseEmail &&
                        primaryEmail &&
                        emailProviderConfigured &&
                        selectedEmailAlias &&
                        hasEmailSignature &&
                        emailAttachmentsWithinLimit
                          ? styles.emailReady
                          : styles.emailBlocked
                      }
                    >
                      {canUseEmail &&
                      primaryEmail &&
                      emailProviderConfigured &&
                      selectedEmailAlias &&
                      hasEmailSignature &&
                      emailAttachmentsWithinLimit ? (
                        <ShieldCheck size={15} aria-hidden="true" />
                      ) : (
                        <ShieldAlert size={15} aria-hidden="true" />
                      )}
                      <span>
                        {!canUseEmail
                          ? "Your role cannot send seller email."
                          : !primaryEmail
                            ? "This seller does not have an email address."
                            : !emailProviderConfigured
                              ? emailConfigurationBlockers.join(" ") ||
                                "Email delivery is not configured."
                              : !selectedEmailAlias
                                ? "Select an authorized Stonegate sender."
                                : !hasEmailSignature
                                  ? "Add a professional signature to this sender before emailing."
                                  : !emailAttachmentsWithinLimit
                                    ? `Attachments total ${formatFileSize(emailAttachmentBytes)}. Keep the combined total at or below 10 MB.`
                                    : `Ready to email ${primaryEmail.value} from ${selectedEmailAlias.email_address}. Your signature will be appended.`}
                      </span>
                    </div>
                    <div className={styles.emailAttachmentRow}>
                      <label>
                        <Paperclip size={14} aria-hidden="true" />
                        Attach files
                        <input
                          multiple
                          onChange={(event) => {
                            setEmailAttachments(Array.from(event.target.files ?? []).slice(0, 5));
                            emailIdempotencyKeyRef.current = null;
                          }}
                          type="file"
                        />
                      </label>
                      {emailAttachments.map((file) => (
                        <span key={`${file.name}-${file.size}`}>
                          {file.name} · {formatFileSize(file.size)}
                        </span>
                      ))}
                    </div>
                  </>
                ) : null}
                {isVoiceComposer ? (
                  <div className={styles.voiceComposer}>
                    <div
                      className={
                        detail.voice_eligibility.can_call ? styles.voiceReady : styles.voiceBlocked
                      }
                    >
                      {detail.voice_eligibility.can_call ? (
                        <ShieldCheck size={15} aria-hidden="true" />
                      ) : (
                        <ShieldAlert size={15} aria-hidden="true" />
                      )}
                      <span>
                        {detail.voice_eligibility.can_call
                          ? callComposerMode === "cellphone" && forwardedCallStatus === "started"
                            ? "Answer your cellphone and press 1 to connect."
                            : callComposerMode === "browser"
                              ? `Ready to call ${detail.voice_eligibility.recipient} through this browser · ${contactPermissionLabel(detail.voice_eligibility.consent_status)}.`
                              : `Ready to call ${detail.voice_eligibility.recipient} through your cellphone · ${contactPermissionLabel(detail.voice_eligibility.consent_status)}.`
                          : detail.voice_eligibility.blockers.join(" ")}
                      </span>
                    </div>
                    <button
                      disabled={
                        !detail.voice_eligibility.can_call ||
                        (callComposerMode === "browser"
                          ? webPhone.busy || webPhone.status.callActive
                          : forwardedCallStatus === "starting" ||
                            webPhone.busy ||
                            webPhone.status.callActive)
                      }
                      onClick={() =>
                        void (callComposerMode === "browser"
                          ? startBrowserCall()
                          : startCellphoneCall())
                      }
                      type="button"
                    >
                      {callComposerMode === "browser" ? (
                        <Headphones size={17} aria-hidden="true" />
                      ) : (
                        <PhoneCall size={17} aria-hidden="true" />
                      )}
                      {callComposerMode === "browser"
                        ? webPhone.busy
                          ? "Starting browser call"
                          : "Call in browser"
                        : forwardedCallStatus === "starting"
                          ? "Calling your cellphone"
                          : "Call through my cellphone"}
                    </button>
                  </div>
                ) : (
                  <div className={styles.composerBody}>
                    <textarea
                      aria-label={`${labelize(channel)} details`}
                      maxLength={channel === "sms" ? 1600 : 4000}
                      onChange={(event) => {
                        if (event.target.value !== body) smsIdempotencyKeyRef.current = null;
                        if (event.target.value !== body) emailIdempotencyKeyRef.current = null;
                        setBody(event.target.value);
                      }}
                      placeholder={
                        channel === "note"
                          ? "Add a note for the Stonegate team..."
                          : channel === "email"
                            ? "Write the seller email..."
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
                            : isLiveEmail
                              ? "Sent"
                              : "Logged"
                          : isLiveSms
                            ? "Send SMS"
                            : isLiveEmail
                              ? "Send email"
                              : `Log ${channel === "note" ? "note" : channel.toUpperCase()}`}
                    </button>
                  </div>
                )}
              </form>
            </>
          ) : null}
        </section>

        <aside className={styles.detailPane} data-mobile-active={mobilePane === "details"}>
          {!detail ? (
            <div className={styles.detailEmpty}>Select a conversation to view seller context.</div>
          ) : (
            <>
              <header className={styles.detailHeader}>
                <div>
                  <span>
                    {detail.conversation_type === "general"
                      ? "Company correspondence"
                      : detail.conversation_type === "buyer"
                        ? "Buyer relationship"
                        : "Lead context"}
                  </span>
                  <h3>{detail.seller_name}</h3>
                </div>
                {detail.lead_id ? (
                  <Link href={`/os/leads/${detail.lead_id}`}>
                    Full record
                    <ChevronRight size={15} aria-hidden="true" />
                  </Link>
                ) : detail.buyer_id ? (
                  <Link href={`/os/buyers?buyer=${detail.buyer_id}`}>
                    Buyer record
                    <ChevronRight size={15} aria-hidden="true" />
                  </Link>
                ) : null}
              </header>

              <section className={styles.detailSection}>
                <h4>Contact</h4>
                <div className={styles.contactList}>
                  {detail.contact_methods.length === 0 ? <span>No contact methods</span> : null}
                  {detail.contact_methods.map((method) => (
                    <div
                      className={styles.contactMethod}
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
                    </div>
                  ))}
                </div>
                {detail.lead_id ? (
                  <SmsPermissionControl
                    canManagePhone={Boolean(canManagePhonePermission)}
                    canManageSms={Boolean(canManageSmsPermission)}
                    fallbackConsentStatus={detail.sms_eligibility.consent_status}
                    fallbackPhoneConsentStatus={detail.voice_eligibility.consent_status}
                    isPhoneSuppressed={detail.voice_eligibility.is_suppressed}
                    isSuppressed={detail.sms_eligibility.is_suppressed}
                    key={`${detail.lead_id}:${detail.sms_eligibility.consent_status}:${detail.voice_eligibility.consent_status}:${Number(detail.sms_eligibility.is_suppressed)}:${Number(detail.voice_eligibility.is_suppressed)}:${detail.last_activity_at ?? "initial"}`}
                    leadId={detail.lead_id}
                    onSaved={() => loadDetail(detail.id)}
                    phoneNumber={primaryPhone?.value ?? detail.sms_eligibility.recipient}
                  />
                ) : (
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
                        ? `SMS available · ${contactPermissionLabel(detail.sms_eligibility.consent_status)}`
                        : detail.sms_eligibility.is_suppressed
                          ? `SMS suppressed · ${contactPermissionLabel(detail.sms_eligibility.consent_status)}`
                          : `SMS unavailable · ${contactPermissionLabel(detail.sms_eligibility.consent_status)} · ${detail.sms_eligibility.blockers.join(" ")}`}
                    </span>
                  </div>
                )}
                {!detail.lead_id ? (
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
                        ? `Calling available · ${contactPermissionLabel(detail.voice_eligibility.consent_status)}`
                        : detail.voice_eligibility.is_suppressed
                          ? `Calling suppressed · ${contactPermissionLabel(detail.voice_eligibility.consent_status)}`
                          : `Calling unavailable · ${contactPermissionLabel(detail.voice_eligibility.consent_status)} · ${detail.voice_eligibility.blockers.join(" ")}`}
                    </span>
                  </div>
                ) : null}
              </section>

              {detail.conversation_type === "general" ? (
                <>
                  <section className={styles.detailSection}>
                    <h4>Handle this email</h4>
                    <GeneralEmailActions
                      canClassify={Boolean(canHandoff)}
                      canManage={Boolean(me?.permissions.includes("leads:edit"))}
                      category={detail.mail_category}
                      closed={detail.status === "closed"}
                      leads={linkableLeads}
                      leadsLoading={linkableLeadsLoading}
                      mergedConversationId={detail.merged_into_conversation_id}
                      onClassify={classifyGeneralEmail}
                      onConvert={convertGeneralEmailToLead}
                      onLink={linkGeneralEmailToLead}
                      onOpenMerged={openMergedConversation}
                    />
                  </section>
                  <section className={styles.detailSection}>
                    <h4>Mailbox</h4>
                    <dl className={styles.detailList}>
                      <div>
                        <dt>Receiving address</dt>
                        <dd>
                          {emailAliases.find(
                            (alias) => alias.id === detail.source_alias_id,
                          )?.email_address || "Stonegate company address"}
                        </dd>
                      </div>
                      <div>
                        <dt>Visibility</dt>
                        <dd>{labelize(detail.visibility_scope)}</dd>
                      </div>
                      {detail.mail_category ? (
                        <div>
                          <dt>Category</dt>
                          <dd>{labelize(detail.mail_category)}</dd>
                        </div>
                      ) : null}
                    </dl>
                  </section>
                </>
              ) : detail.conversation_type === "buyer" ? (
                <section className={styles.detailSection}>
                  <h4>Dispositions</h4>
                  <dl className={styles.detailList}>
                    <div><dt>Relationship</dt><dd>Cash buyer / investor</dd></div>
                    <div><dt>Department</dt><dd>Dispositions</dd></div>
                    <div><dt>Communication line</dt><dd>Stonegate Dispositions</dd></div>
                  </dl>
                </section>
              ) : (
                <>
                  <section className={styles.detailSection}>
                    <h4>Property</h4>
                    <p className={styles.propertyAddress}>{detail.property_address}</p>
                    <dl className={styles.contextGrid}>
                      <div>
                        <dt>Lead type</dt>
                        <dd>{labelize(detail.asset_class)}</dd>
                      </div>
                      <div>
                        <dt>Type</dt>
                        <dd>{labelize(detail.property_type)}</dd>
                      </div>
                      <div>
                        <dt>County</dt>
                        <dd>{detail.property_county || "Not captured"}</dd>
                      </div>
                      <div>
                        <dt>Parcel / APN</dt>
                        <dd>{detail.property_parcel_id || "Not captured"}</dd>
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
                    <h4>Call notes</h4>
                    {callNotes.length > 0 ? (
                      <div className={styles.callNotesList}>
                        {callNotes.map((item) => {
                          const transcript = item.transcript;
                          const notes = transcript.structured_notes;
                          if (!notes || !item.call_id) return null;

                          return (
                            <article className={styles.callNoteCard} key={transcript.id}>
                              <div className={styles.callNoteMeta}>
                                <time>{formatDateTime(item.occurred_at)}</time>
                                <span>{labelize(transcript.status)}</span>
                              </div>
                              <strong>{notes.summary}</strong>
                              {notes.next_action ? (
                                <p>
                                  <span>Next:</span> {notes.next_action}
                                </p>
                              ) : null}
                              {notes.parcel_id ? <p><span>Parcel:</span> {notes.parcel_id}</p> : null}
                              {notes.acreage ? <p><span>Acreage:</span> {notes.acreage}</p> : null}
                              {notes.access_or_frontage ? <p><span>Access:</span> {notes.access_or_frontage}</p> : null}
                              <a href={`#call-${item.call_id}`}>
                                Open call in thread
                                <ChevronRight size={12} aria-hidden="true" />
                              </a>
                            </article>
                          );
                        })}
                      </div>
                    ) : (
                      <p className={styles.mutedText}>No processed call notes yet.</p>
                    )}
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
                    {detail.lead_id ? (
                      <Link
                        className={styles.scheduleFromInbox}
                        href={`/os/calendar?view=appointment&schedule=1&lead=${encodeURIComponent(detail.lead_id)}`}
                      >
                        <CalendarClock size={14} aria-hidden="true" />
                        {nextAppointment ? "Schedule another appointment" : "Schedule appointment"}
                      </Link>
                    ) : null}
                  </section>
                </>
              )}

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

              {detail.conversation_type !== "general" &&
              canHandoff &&
              assignees.length > 0 ? (
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
                      <select
                        onChange={(event) => setQueueKey(event.target.value)}
                        value={queueKey}
                      >
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
      {globalComposeOpen && canComposeGlobalEmail ? (
        <GlobalEmailCompose
          aliases={emailAliases}
          apiBaseUrl={apiBaseUrl}
          configurationBlockers={emailConfigurationBlockers}
          getHeaders={getHeaders}
          onClose={() => setGlobalComposeOpen(false)}
          onSent={handleGlobalEmailSent}
          providerConfigured={emailProviderConfigured}
          templates={emailTemplates}
        />
      ) : null}
      {emailAdminOpen &&
      me?.permissions.includes("communications:manage_email_accounts") ? (
        <EmailAdminPanel
          aliases={emailAliases}
          configurationBlockers={emailConfigurationBlockers}
          conversations={conversations.map((conversation) => ({
            id: conversation.id,
            seller_name: conversation.seller_name,
            property_address: conversation.property_address,
          }))}
          onAliasesChanged={async () => {
            await loadEmailConfiguration();
          }}
          onClose={() => setEmailAdminOpen(false)}
          open={emailAdminOpen}
          providerConfigured={emailProviderConfigured}
        />
      ) : null}
    </>
  );
}
