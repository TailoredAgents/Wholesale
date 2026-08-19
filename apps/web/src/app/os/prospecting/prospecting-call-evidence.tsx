"use client";

import { useAuth } from "@clerk/nextjs";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Download,
  FileText,
  LoaderCircle,
  Play,
  RefreshCw,
  Sparkles,
  Trash2,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  ProspectingAttemptEvidence,
  ProspectingCallTranscript,
} from "../../lib/api";
import {
  CallRecordingPlayer,
  type CallRecordingPlayerHandle,
} from "../inbox/call-recording-player";
import { buildCallQuickRead } from "../inbox/call-quick-read";
import { labelize } from "../os-utils";
import {
  buildEvidenceFacts,
  evidenceStatusPresentation,
  formatEvidenceTimestamp,
  formatSuggestionValue,
  suggestionPresentation,
  type EvidenceStatusPresentation,
} from "./prospecting-call-evidence-state";
import styles from "./prospecting.module.css";

type LoadState = "loading" | "ready" | "error";
type ActionState = "idle" | "saving";

function responseError(payload: unknown, fallback: string) {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return fallback;
}

function formatDateTime(value: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function ProspectingCallEvidence({
  attemptId,
  onPresentationChange,
}: {
  attemptId: string;
  onPresentationChange: (presentation: EvidenceStatusPresentation) => void;
}) {
  const { getToken } = useAuth();
  const playerRef = useRef<CallRecordingPlayerHandle | null>(null);
  const [evidence, setEvidence] = useState<ProspectingAttemptEvidence | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [retryState, setRetryState] = useState<ActionState>("idle");
  const [downloadState, setDownloadState] = useState<ActionState>("idle");
  const [deleteState, setDeleteState] = useState<ActionState>("idle");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteReason, setDeleteReason] = useState("");
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

  const getHeaders = useCallback(async () => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const token = await getToken().catch(() => null);
    if (token) headers.Authorization = `Bearer ${token}`;
    else headers["X-Dev-User-Email"] = devUserEmail;
    return headers;
  }, [devUserEmail, getToken]);

  const loadEvidence = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const response = await fetch(
          `${apiBaseUrl}/api/v1/prospecting/attempts/${attemptId}/evidence`,
          {
            cache: "no-store",
            headers: await getHeaders(),
            signal,
          },
        );
        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          throw new Error(
            responseError(payload, `Call evidence could not be loaded (${response.status}).`),
          );
        }
        const payload = (await response.json()) as ProspectingAttemptEvidence;
        setError(null);
        setEvidence(payload);
        setLoadState("ready");
        onPresentationChange(evidenceStatusPresentation(payload.evidence_status));
      } catch (loadError) {
        if (signal?.aborted) return;
        setLoadState("error");
        setError(
          loadError instanceof Error ? loadError.message : "Call evidence could not be loaded.",
        );
      }
    },
    [apiBaseUrl, attemptId, getHeaders, onPresentationChange],
  );

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => void loadEvidence(controller.signal), 0);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [loadEvidence]);

  useEffect(() => {
    if (!evidence || !["processing", "recording_ready", "failed"].includes(evidence.evidence_status)) {
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => void loadEvidence(controller.signal), 12000);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [evidence, loadEvidence]);

  const notes = evidence?.transcript?.structured_notes ?? null;
  const quickRead = notes
    ? buildCallQuickRead(notes, evidence?.transcript?.quick_read_summary ?? null)
    : [];
  const facts = notes ? buildEvidenceFacts(notes) : [];

  const seekTo = useCallback((seconds: number) => {
    void playerRef.current?.seekTo(seconds, { play: true });
  }, []);

  const retryTranscript = async () => {
    const transcript = evidence?.transcript;
    if (!transcript || !evidence.capabilities.can_retry) return;
    setRetryState("saving");
    setError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/voice/transcripts/${transcript.id}/retry`,
        {
          method: "POST",
          headers: await getHeaders(),
          body: JSON.stringify({}),
        },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(responseError(payload, "Call intelligence could not be retried."));
      }
      const nextTranscript = (await response.json()) as ProspectingCallTranscript;
      setEvidence((current) =>
        current
          ? {
              ...current,
              transcript: nextTranscript,
              evidence_status: "processing",
              capabilities: { ...current.capabilities, can_retry: false },
            }
          : current,
      );
      onPresentationChange(evidenceStatusPresentation("processing"));
    } catch (retryError) {
      setError(
        retryError instanceof Error
          ? retryError.message
          : "Call intelligence could not be retried.",
      );
    } finally {
      setRetryState("idle");
    }
  };

  const downloadTranscript = async () => {
    const transcript = evidence?.transcript;
    if (!transcript || !evidence.capabilities.can_download_transcript) return;
    setDownloadState("saving");
    setError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/voice/transcripts/${transcript.id}/download`,
        { cache: "no-store", headers: await getHeaders() },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(responseError(payload, "Transcript could not be downloaded."));
      }
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `stonegate-prospecting-transcript-${transcript.id}.txt`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (downloadError) {
      setError(
        downloadError instanceof Error ? downloadError.message : "Transcript could not be downloaded.",
      );
    } finally {
      setDownloadState("idle");
    }
  };

  const deleteRecording = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const recording = evidence?.recording;
    if (
      !recording ||
      !evidence.capabilities.can_delete ||
      deleteReason.trim().length < 10
    ) {
      return;
    }
    setDeleteState("saving");
    setError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/voice/recordings/${recording.id}`,
        {
          method: "DELETE",
          headers: await getHeaders(),
          body: JSON.stringify({ reason: deleteReason.trim() }),
        },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(responseError(payload, "Call audio could not be deleted."));
      }
      setDeleteOpen(false);
      setDeleteReason("");
      await loadEvidence();
    } catch (deleteError) {
      setError(
        deleteError instanceof Error ? deleteError.message : "Call audio could not be deleted.",
      );
    } finally {
      setDeleteState("idle");
    }
  };

  if (loadState === "loading") {
    return (
      <div aria-live="polite" className={styles.evidenceLoading} role="status">
        <LoaderCircle aria-hidden="true" size={16} />
        Loading recording and AI notes...
      </div>
    );
  }

  if (loadState === "error" || !evidence) {
    return (
      <div className={styles.evidenceError} role="alert">
        <AlertTriangle aria-hidden="true" size={16} />
        <div>
          <strong>Call evidence could not be loaded</strong>
          <p>{error ?? "Try again."}</p>
          <button onClick={() => void loadEvidence()} type="button">
            <RefreshCw aria-hidden="true" size={13} /> Retry loading
          </button>
        </div>
      </div>
    );
  }

  const presentation = evidenceStatusPresentation(evidence.evidence_status);
  const recording = evidence.recording;
  const transcript = evidence.transcript;
  const transcriptSegments = transcript?.speaker_segments.filter((segment) =>
    Boolean(segment.text?.trim()),
  ) ?? [];
  const hasTranscript = Boolean(
    transcript && (transcriptSegments.length || transcript.transcript_text?.trim()),
  );
  const retainedUntil = formatDateTime(recording?.retention_expires_at ?? null);
  const deletedAt = formatDateTime(recording?.deleted_at ?? null);

  return (
    <section className={styles.callEvidence} aria-label="Call evidence">
      <header className={styles.callEvidenceHeader}>
        <div>
          <Bot aria-hidden="true" size={17} />
          <div>
            <strong>{presentation.label}</strong>
            <p>{presentation.detail}</p>
          </div>
        </div>
        <span data-tone={presentation.tone}>{labelize(evidence.evidence_status)}</span>
      </header>

      {error ? <p className={styles.callEvidenceActionError} role="alert">{error}</p> : null}

      <section className={styles.callEvidenceSection} aria-label="Call recording">
        <div className={styles.callEvidenceSectionHeading}>
          <strong>Recording</strong>
          {recording?.duration_seconds ? (
            <span>{formatEvidenceTimestamp(recording.duration_seconds)}</span>
          ) : null}
        </div>
        {recording && recording.status === "completed" && evidence.capabilities.can_play ? (
          <CallRecordingPlayer
            apiBaseUrl={apiBaseUrl}
            canDownload={evidence.capabilities.can_download_audio}
            getHeaders={getHeaders}
            onError={setError}
            recordingId={recording.id}
            ref={playerRef}
          />
        ) : recording?.status === "deleted" || recording?.deleted_at ? (
          <p className={styles.callEvidenceEmpty}>
            Audio deleted{deletedAt ? ` ${deletedAt}` : ""}.
          </p>
        ) : recording ? (
          <p className={styles.callEvidenceEmpty}>Recording {labelize(recording.status)}.</p>
        ) : (
          <p className={styles.callEvidenceEmpty}>No retained recording is available.</p>
        )}
        {recording?.status === "completed" && retainedUntil ? (
          <p className={styles.callEvidenceRetention}>Audio retained until {retainedUntil}.</p>
        ) : null}
        {recording?.status === "completed" && evidence.capabilities.can_delete ? (
          <div className={styles.callEvidenceDelete}>
            {!deleteOpen ? (
              <button onClick={() => setDeleteOpen(true)} type="button">
                <Trash2 aria-hidden="true" size={13} /> Delete call audio
              </button>
            ) : (
              <form onSubmit={deleteRecording}>
                <label>
                  Deletion reason
                  <input
                    autoFocus
                    minLength={10}
                    onChange={(event) => setDeleteReason(event.target.value)}
                    placeholder="Why must this audio be deleted early?"
                    required
                    value={deleteReason}
                  />
                </label>
                <div>
                  <button
                    disabled={deleteState === "saving"}
                    onClick={() => {
                      setDeleteOpen(false);
                      setDeleteReason("");
                    }}
                    type="button"
                  >
                    Cancel
                  </button>
                  <button
                    disabled={deleteState === "saving" || deleteReason.trim().length < 10}
                    type="submit"
                  >
                    {deleteState === "saving" ? "Deleting" : "Delete audio"}
                  </button>
                </div>
              </form>
            )}
          </div>
        ) : null}
      </section>

      {quickRead.length ? (
        <section className={styles.callEvidenceQuickRead} aria-label="Quick read">
          <div><Sparkles aria-hidden="true" size={15} /><strong>Quick read</strong></div>
          <dl>
            {quickRead.map((item) => (
              <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>
            ))}
          </dl>
        </section>
      ) : null}

      {facts.length ? (
        <section className={styles.callEvidenceSection} aria-label="Call facts">
          <div className={styles.callEvidenceSectionHeading}>
            <strong>Facts captured from the call</strong>
            {notes ? <span>{notes.confidence}% AI confidence</span> : null}
          </div>
          <dl className={styles.callEvidenceFacts}>
            {facts.map((fact) => (
              <div key={fact.key}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>
            ))}
          </dl>
        </section>
      ) : null}

      {evidence.suggestions.length ? (
        <section className={styles.callEvidenceSection} aria-label="AI qualification suggestions">
          <div className={styles.callEvidenceSectionHeading}>
            <strong>Qualification evidence</strong>
            <span>{evidence.suggestions.length} item{evidence.suggestions.length === 1 ? "" : "s"}</span>
          </div>
          <div className={styles.callEvidenceSuggestions}>
            {evidence.suggestions.map((suggestion) => {
              const suggestionState = suggestionPresentation(suggestion);
              return (
                <article key={suggestion.question_key} data-tone={suggestionState.tone}>
                  <div>
                    <strong>{labelize(suggestion.question_key)}</strong>
                    <span>{suggestionState.label}</span>
                  </div>
                  <p><b>AI heard:</b> {formatSuggestionValue(suggestion.suggested_value)}</p>
                  {suggestion.state === "conflict" ? (
                    <p><b>Saved answer:</b> {formatSuggestionValue(suggestion.current_value)}</p>
                  ) : null}
                  {suggestion.evidence.map((item, index) =>
                    evidence.capabilities.can_play ? (
                      <button
                        key={`${item.segment_index}-${index}`}
                        onClick={() => seekTo(item.start_seconds)}
                        title="Play this moment"
                        type="button"
                      >
                        <Play aria-hidden="true" size={11} />
                        {formatEvidenceTimestamp(item.start_seconds)} - {item.supporting_text}
                      </button>
                    ) : (
                      <small key={`${item.segment_index}-${index}`}>
                        {formatEvidenceTimestamp(item.start_seconds)} - {item.supporting_text}
                      </small>
                    ),
                  )}
                </article>
              );
            })}
          </div>
        </section>
      ) : null}

      {transcript && !notes ? (
        <section className={styles.callEvidencePending} data-status={transcript.status}>
          {transcript.status === "exhausted" ? <AlertTriangle aria-hidden="true" size={16} /> : <Bot aria-hidden="true" size={16} />}
          <div>
            <strong>AI call intelligence - {labelize(transcript.status)}</strong>
            <p>
              {transcript.error_message ||
                (transcript.status === "exhausted"
                  ? "Call intelligence stopped after repeated failures."
                  : transcript.status === "failed"
                    ? "A temporary failure occurred. Stonegate will retry automatically."
                    : transcript.status === "processing"
                      ? "AI is transcribing the call and preparing automatic notes."
                      : "This call is queued for transcription.")}
            </p>
            {evidence.capabilities.can_retry ? (
              <button disabled={retryState === "saving"} onClick={() => void retryTranscript()} type="button">
                <RefreshCw aria-hidden="true" size={13} />
                {retryState === "saving" ? "Queueing" : "Retry call intelligence"}
              </button>
            ) : null}
          </div>
        </section>
      ) : null}

      {hasTranscript && transcript ? (
        <details className={styles.callEvidenceTranscript}>
          <summary>
            <span><FileText aria-hidden="true" size={14} /> Full transcript</span>
            <span>{transcriptSegments.length ? `${transcriptSegments.length} segments` : "Complete text"}</span>
          </summary>
          <div>
            {evidence.capabilities.can_download_transcript ? (
              <button disabled={downloadState === "saving"} onClick={() => void downloadTranscript()} type="button">
                <Download aria-hidden="true" size={13} />
                {downloadState === "saving" ? "Downloading" : "Download transcript"}
              </button>
            ) : null}
            <div className={styles.callEvidenceTranscriptText}>
              {transcriptSegments.length ? transcriptSegments.map((segment, index) => (
                <p key={`${segment.start ?? 0}-${index}`}>
                  <span>
                    <strong>{segment.speaker || "Speaker"}</strong>
                    {evidence.capabilities.can_play ? (
                      <button
                        aria-label={`Play recording from ${formatEvidenceTimestamp(segment.start ?? 0)}`}
                        onClick={() => seekTo(segment.start ?? 0)}
                        type="button"
                      >
                        <Play aria-hidden="true" size={10} /> {formatEvidenceTimestamp(segment.start ?? 0)}
                      </button>
                    ) : (
                      <small>{formatEvidenceTimestamp(segment.start ?? 0)}</small>
                    )}
                  </span>
                  <span>{segment.text}</span>
                </p>
              )) : <p><span>{transcript.transcript_text}</span></p>}
            </div>
          </div>
        </details>
      ) : transcript?.status === "approved" || transcript?.status === "completed" ? (
        <p className={styles.callEvidenceEmpty}>No transcript text is available.</p>
      ) : null}

      {evidence.evidence_status === "ready" ? (
        <p className={styles.callEvidenceAutomaticNote}>
          <CheckCircle2 aria-hidden="true" size={14} />
          AI notes are saved automatically. No approval is required.
        </p>
      ) : null}
    </section>
  );
}
