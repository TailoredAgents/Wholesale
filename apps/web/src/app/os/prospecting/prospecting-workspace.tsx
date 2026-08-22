"use client";

import { useAuth } from "@clerk/nextjs";
import {
  AlertTriangle,
  Brain,
  CalendarClock,
  CheckCircle2,
  Clock3,
  FileWarning,
  Pencil,
  PhoneCall,
  ShieldAlert,
  Sparkles,
  UserRoundCheck,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import {
  FormEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type {
  ProspectHandoff,
  ProspectingAttempt,
  ProspectingAttemptCompletionPayload,
  ProspectingCallQuality,
  ProspectingCallQualityOutput,
  ProspectingCopilotOutput,
  ProspectingCopilotRecommendation,
  ProspectingDialerContext,
  ProspectingEntry,
  ProspectingInboundCallback,
  ProspectingInboundCallbackList,
  ProspectingQualificationChecklist,
  ProspectingSellerOutcome,
  ProspectingTechnicalFailurePayload,
  ProspectingWorkbenchOverview,
} from "../../lib/api";
import { CopilotLauncher } from "../_components/copilot-launcher";
import { labelize } from "../os-utils";
import type {
  ActiveProspectingDialerLease,
  ProspectingDialerRuntime,
} from "./prospecting-dialer";
import {
  isManualProspectingMode,
  type ProspectingDialerLeadership,
} from "./prospecting-dialer-policy";
import { ProspectingQualificationChecklist as LiveQualificationChecklist } from "./prospecting-qualification-checklist";
import { pruneQualificationOverrides } from "./prospecting-qualification-state";
import {
  createProspectingWrapUpReceipt,
  createTechnicalFailureReceipt,
  PROSPECTING_OUTCOME_GROUPS,
  PROSPECTING_OUTCOME_OPTIONS,
  prospectingOutcomeOption,
  type ProspectingWrapUpReceipt,
  validateProspectingWrapUp,
} from "./prospecting-wrap-up-state";
import {
  INITIAL_EVIDENCE_PRESENTATION,
  type EvidenceStatusPresentation,
} from "./prospecting-call-evidence-state";
import styles from "./prospecting.module.css";

const ProspectingCallEvidence = dynamic(
  () =>
    import("./prospecting-call-evidence").then(
      (module) => module.ProspectingCallEvidence,
    ),
  {
    loading: () => (
      <p aria-live="polite" className={styles.evidenceLoading} role="status">
        Loading call evidence...
      </p>
    ),
    ssr: false,
  },
);

const ProspectingDialer = dynamic(
  () => import("./prospecting-dialer").then((module) => module.ProspectingDialer),
  { ssr: false },
);

type View = "workbench" | "quality" | "handoffs" | "performance" | "scripts";
type RequestStatus = "idle" | "saving" | "saved" | "error";
type QueueFilter =
  | "due"
  | "callbacks"
  | "retries"
  | "corrections"
  | "scheduled"
  | "waiting"
  | "all";

const EMPTY_DIALER_RUNTIME: ProspectingDialerRuntime = {
  sessionState: null,
  legStatus: null,
  terminalResult: null,
  providerError: null,
  recipient: null,
  technicalFailure: false,
  wrapUpReady: false,
};

type PendingWrapUpSubmission = {
  attemptId: string;
  payload: ProspectingAttemptCompletionPayload;
};

const standardQuestions = [
  ["motivation", "Reason for selling", "What has you considering selling the property?", true],
  ["timeline", "Timeline", "When would you ideally like to sell?", true],
  ["property_condition", "Property condition", "What repairs or updates does the property need?", true],
  ["occupancy", "Occupancy", "Is the property owner occupied, tenant occupied, or vacant?", true],
  ["asking_price", "Price expectation", "Do you have a price in mind?", false],
  ["mortgage_balance", "Mortgage balance", "Is there a mortgage or other debt on the property?", false],
] as const;

function value(data: FormData, key: string) {
  return String(data.get(key) ?? "").trim();
}

function formatDateTime(value: string | null) {
  if (!value) return "Not scheduled";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatPercent(basisPoints: number) {
  return `${(basisPoints / 100).toFixed(1)}%`;
}

function localDateTimeToIso(value: string) {
  return value ? new Date(value).toISOString() : null;
}

function dateToLocalInputValue(value: Date) {
  const localValue = new Date(value.getTime() - value.getTimezoneOffset() * 60 * 1000);
  return localValue.toISOString().slice(0, 16);
}

function CompletedAttemptHistoryItem({ attempt }: { attempt: ProspectingAttempt }) {
  const [expanded, setExpanded] = useState(false);
  const [presentation, setPresentation] = useState<EvidenceStatusPresentation>(
    INITIAL_EVIDENCE_PRESENTATION,
  );
  const updatePresentation = useCallback(
    (nextPresentation: EvidenceStatusPresentation) => setPresentation(nextPresentation),
    [],
  );

  return (
    <details
      className={styles.attemptHistoryItem}
      onToggle={(event) => {
        if (event.target === event.currentTarget) {
          setExpanded(event.currentTarget.open);
        }
      }}
    >
      <summary>
        <span className={styles.attemptHistoryOutcome}>
          <strong>{attempt.outcome ? labelize(attempt.outcome) : "Attempt"}</strong>
          <em data-tone={presentation.tone}>{presentation.label}</em>
        </span>
        <span>{formatDateTime(attempt.completed_at)}</span>
      </summary>
      <div className={styles.attemptHistoryBody}>
        {attempt.callback_at ? <p>Callback: {formatDateTime(attempt.callback_at)}</p> : null}
        {attempt.notes ? <p>{attempt.notes}</p> : null}
        {Object.entries(attempt.qualification_answers).length ? (
          <dl>
            {Object.entries(attempt.qualification_answers).map(([key, answer]) => (
              <div key={key}><dt>{labelize(key)}</dt><dd>{answer}</dd></div>
            ))}
          </dl>
        ) : null}
        {expanded ? (
          <ProspectingCallEvidence
            attemptId={attempt.id}
            onPresentationChange={updatePresentation}
          />
        ) : null}
      </div>
    </details>
  );
}

export function ProspectingWorkspace({
  data,
  dialerContext,
  initialCallbacks,
  initialCallbacksAvailable,
}: {
  data: ProspectingWorkbenchOverview;
  dialerContext: ProspectingDialerContext | null;
  initialCallbacks: ProspectingInboundCallbackList;
  initialCallbacksAvailable: boolean;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const nativeDialerEnabled = dialerContext?.feature_enabled === true;
  const manualAttemptAuthority = isManualProspectingMode(dialerContext);
  const attemptAuthorityKnown = dialerContext !== null;
  const [view, setView] = useState<View>("workbench");
  const [status, setStatus] = useState<RequestStatus>("idle");
  const [message, setMessage] = useState("");
  const [outcome, setOutcome] = useState<ProspectingSellerOutcome>("no_answer");
  const [entrySelection, setEntry] = useState<ProspectingEntry | null>(data.current_entry);
  const [optimisticEntry, setOptimisticEntry] = useState<ProspectingEntry | null>(null);
  const optimisticEntryRef = useRef<ProspectingEntry | null>(null);
  const [selectedCopilotEntryId, setSelectedCopilotEntryId] = useState(
    data.current_entry?.id ?? data.copilot.work_items[0]?.entry_id ?? "",
  );
  const [localRecommendation, setLocalRecommendation] =
    useState<ProspectingCopilotRecommendation | null>(null);
  const [editingBrief, setEditingBrief] = useState(false);
  const [editedSummary, setEditedSummary] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("due");
  const [callbacks, setCallbacks] = useState(initialCallbacks);
  const [callbacksAvailable, setCallbacksAvailable] = useState(initialCallbacksAvailable);
  const [callbacksLastSuccessAt, setCallbacksLastSuccessAt] = useState<string | null>(
    initialCallbacksAvailable ? new Date().toISOString() : null,
  );
  const [openingCallbackId, setOpeningCallbackId] = useState("");
  const callbackRefreshSequenceRef = useRef(0);
  const callbackRefreshControllerRef = useRef<AbortController | null>(null);
  const callbackOpenInFlightRef = useRef(false);
  const callbackOpenSequenceRef = useRef(0);
  const callbackOpenControllerRef = useRef<AbortController | null>(null);
  const callbackOpenBlockedRef = useRef(false);
  const [dialerLease, setDialerLease] =
    useState<ActiveProspectingDialerLease | null>(null);
  const [nativeDialerAvailable, setNativeDialerAvailable] = useState(false);
  const [dialerLeadership, setDialerLeadership] =
    useState<ProspectingDialerLeadership>("checking");
  const [dialerRuntime, setDialerRuntime] =
    useState<ProspectingDialerRuntime>(EMPTY_DIALER_RUNTIME);
  const [lastWrapUp, setLastWrapUp] = useState<ProspectingWrapUpReceipt | null>(null);
  const [pendingWrapUpAttemptId, setPendingWrapUpAttemptId] = useState<string | null>(null);
  const pendingWrapUpRef = useRef<PendingWrapUpSubmission | null>(null);
  const wrapUpInFlightRef = useRef(false);
  const technicalFailureSubmissionRef = useRef<{
    attemptId: string;
    idempotencyKey: string;
  } | null>(null);
  const [qualificationBlocking, setQualificationBlocking] = useState(false);
  const [qualificationOverrides, setQualificationOverrides] = useState<
    Record<string, ProspectingQualificationChecklist>
  >({});
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

  const refreshCallbacks = useCallback(async () => {
    if (!nativeDialerEnabled || document.visibilityState === "hidden") return;
    const requestSequence = callbackRefreshSequenceRef.current + 1;
    callbackRefreshSequenceRef.current = requestSequence;
    callbackRefreshControllerRef.current?.abort();
    const controller = new AbortController();
    callbackRefreshControllerRef.current = controller;
    const timeout = window.setTimeout(() => {
      controller.abort();
      if (requestSequence === callbackRefreshSequenceRef.current) {
        setCallbacksAvailable(false);
      }
    }, 10_000);
    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;
      const response = await fetch(
        `${apiBaseUrl}/api/v1/prospecting/dialer/callbacks`,
        { headers, cache: "no-store", signal: controller.signal },
      );
      if (!response.ok) throw new Error("Callback status is temporarily unavailable.");
      const payload = (await response.json()) as ProspectingInboundCallbackList;
      if (requestSequence !== callbackRefreshSequenceRef.current) return;
      setCallbacks(payload);
      setCallbacksAvailable(true);
      setCallbacksLastSuccessAt(new Date().toISOString());
    } catch {
      if (requestSequence === callbackRefreshSequenceRef.current) {
        setCallbacksAvailable(false);
      }
    } finally {
      window.clearTimeout(timeout);
      if (callbackRefreshControllerRef.current === controller) {
        callbackRefreshControllerRef.current = null;
      }
    }
  }, [apiBaseUrl, devUserEmail, getToken, nativeDialerEnabled]);

  useEffect(() => {
    if (!nativeDialerEnabled) return;
    const interval = window.setInterval(() => void refreshCallbacks(), 20_000);
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") void refreshCallbacks();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      callbackRefreshSequenceRef.current += 1;
      callbackRefreshControllerRef.current?.abort();
      callbackOpenSequenceRef.current += 1;
      callbackOpenControllerRef.current?.abort();
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [nativeDialerEnabled, refreshCallbacks]);
  const queueEntries = useMemo(
    () =>
      data.queue_entries.map((candidate) => {
        const attempt = candidate.active_attempt;
        const checklist = attempt ? qualificationOverrides[attempt.id] : null;
        return checklist && attempt
          ? {
              ...candidate,
              active_attempt: { ...attempt, qualification_checklist: checklist },
            }
          : candidate;
      }),
    [data.queue_entries, qualificationOverrides],
  );
  const currentEntry = useMemo(() => {
    if (!data.current_entry) return null;
    return (
      queueEntries.find((candidate) => candidate.id === data.current_entry?.id) ??
      data.current_entry
    );
  }, [data.current_entry, queueEntries]);
  const entry = useMemo(() => {
    if (!entrySelection) return currentEntry;
    const serverEntry = queueEntries.find(
      (candidate) => candidate.id === entrySelection.id,
    );
    const selected =
      optimisticEntry?.id === entrySelection.id
        ? optimisticEntry
        : serverEntry ?? entrySelection ?? currentEntry;
    const selectedAttempt = selected.active_attempt;
    const checklist = selectedAttempt
      ? qualificationOverrides[selectedAttempt.id]
      : null;
    return checklist && selectedAttempt
      ? {
          ...selected,
          active_attempt: {
            ...selectedAttempt,
            qualification_checklist: checklist,
          },
        }
      : selected;
  }, [currentEntry, entrySelection, optimisticEntry, qualificationOverrides, queueEntries]);
  const activeAttempt = entry?.active_attempt ?? null;
  const entryAssignedToCurrentUser =
    entry?.assigned_user_id === data.current_user_id;
  const callbackOpenBlocked = Boolean(
    dialerLease || (activeAttempt && entryAssignedToCurrentUser),
  );
  useLayoutEffect(() => {
    callbackOpenBlockedRef.current = callbackOpenBlocked;
  }, [callbackOpenBlocked]);
  const ownsAttemptMutationAuthority = Boolean(
    entryAssignedToCurrentUser &&
      (manualAttemptAuthority ||
        (nativeDialerEnabled &&
          ((dialerLeadership === "leader" &&
            (!nativeDialerAvailable || dialerLease)) ||
            (dialerLeadership === "unsupported" && !nativeDialerAvailable)))),
  );
  const qualificationOutcomeBlocked = qualificationBlocking;
  const requiresCallback = ["callback_requested", "follow_up"].includes(outcome);
  const isWarm = ["interested", "appointment_set"].includes(outcome);
  const isAppointment = outcome === "appointment_set";
  const availableViews: Array<{ key: View; label: string; count?: number }> = [
    { key: "workbench", label: "Work queue" },
    {
      key: "quality",
      label: "Call quality",
      count: data.copilot.metrics.escalations || undefined,
    },
    ...(data.can_manage
      ? [{ key: "handoffs" as const, label: "Handoff review", count: data.pending_handoffs.length }]
      : []),
    { key: "performance", label: "Performance" },
    ...(data.can_manage ? [{ key: "scripts" as const, label: "Caller scripts" }] : []),
  ];

  const selectEntry = useCallback((selected: ProspectingEntry) => {
    const retainedWrapUp =
      pendingWrapUpRef.current?.attemptId === selected.active_attempt?.id
        ? pendingWrapUpRef.current
        : null;
    if (!retainedWrapUp) {
      pendingWrapUpRef.current = null;
      setPendingWrapUpAttemptId(null);
    }
    if (technicalFailureSubmissionRef.current?.attemptId !== selected.active_attempt?.id) {
      technicalFailureSubmissionRef.current = null;
    }
    optimisticEntryRef.current = null;
    setOptimisticEntry(null);
    setEntry(selected);
    setQualificationBlocking(false);
    setOutcome(retainedWrapUp?.payload.outcome ?? "no_answer");
    setSelectedCopilotEntryId(selected.id);
    setLocalRecommendation(null);
    setLastWrapUp(null);
  }, []);

  const openCallback = useCallback(async (callback: ProspectingInboundCallback) => {
    if (
      !callback.can_open ||
      !callback.batch_entry_id ||
      callbackOpenBlockedRef.current ||
      callbackOpenInFlightRef.current
    ) return;
    callbackOpenInFlightRef.current = true;
    const requestSequence = callbackOpenSequenceRef.current + 1;
    callbackOpenSequenceRef.current = requestSequence;
    const controller = new AbortController();
    callbackOpenControllerRef.current = controller;
    const timeout = window.setTimeout(() => {
      controller.abort();
      if (requestSequence !== callbackOpenSequenceRef.current) return;
      callbackOpenSequenceRef.current += 1;
      callbackOpenInFlightRef.current = false;
      if (callbackOpenControllerRef.current === controller) {
        callbackOpenControllerRef.current = null;
      }
      setOpeningCallbackId("");
      setStatus("error");
      setMessage("Opening the callback timed out. Try again when the connection is stable.");
    }, 15_000);
    setOpeningCallbackId(callback.id);
    setMessage("");
    setStatus("saving");
    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;
      const response = await fetch(
        `${apiBaseUrl}/api/v1/prospecting/dialer/callbacks/${callback.id}/prospect`,
        { headers, cache: "no-store", signal: controller.signal },
      );
      const errorPayload = (await response.clone().json().catch(() => null)) as
        | { detail?: string }
        | null;
      if (!response.ok) {
        throw new Error(errorPayload?.detail ?? "The matched prospect could not be opened.");
      }
      const selected = (await response.json()) as ProspectingEntry;
      if (requestSequence !== callbackOpenSequenceRef.current) return;
      if (callbackOpenBlockedRef.current) {
        throw new Error("Finish or stop the current dialer session before opening a callback.");
      }
      selectEntry(selected);
      setView("workbench");
      setStatus("idle");
      setMessage(`Opened ${callback.prospect_name ?? "the matched prospect"} from the callback card.`);
    } catch (callbackError) {
      if (requestSequence !== callbackOpenSequenceRef.current) return;
      setStatus("error");
      setMessage(
        callbackError instanceof Error
          ? callbackError.message
          : "The matched prospect could not be opened.",
      );
    } finally {
      window.clearTimeout(timeout);
      if (requestSequence === callbackOpenSequenceRef.current) {
        callbackOpenInFlightRef.current = false;
        if (callbackOpenControllerRef.current === controller) {
          callbackOpenControllerRef.current = null;
        }
        setOpeningCallbackId("");
      }
    }
  }, [apiBaseUrl, devUserEmail, getToken, selectEntry]);

  const applyOptimisticEntry = useCallback((selected: ProspectingEntry) => {
    optimisticEntryRef.current = selected;
    setOptimisticEntry(selected);
    setEntry(selected);
  }, []);

  useEffect(() => {
    const pending = optimisticEntryRef.current;
    if (!pending) return;
    const serverEntry = data.queue_entries.find((item) => item.id === pending.id);
    const serverHasMutation = pending.active_attempt
      ? serverEntry?.active_attempt?.id === pending.active_attempt.id
      : !serverEntry || !serverEntry.active_attempt;
    if (!serverHasMutation) return;
    optimisticEntryRef.current = null;
    setOptimisticEntry(null);
    if (!serverEntry && data.current_entry) setEntry(data.current_entry);
  }, [data.current_entry, data.queue_entries]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const retainedAttemptIds = new Set(
        data.queue_entries.flatMap((candidate) =>
          candidate.active_attempt ? [candidate.active_attempt.id] : [],
        ),
      );
      if (data.current_entry?.active_attempt) {
        retainedAttemptIds.add(data.current_entry.active_attempt.id);
      }
      const pendingAttempt = optimisticEntryRef.current?.active_attempt;
      if (pendingAttempt) retainedAttemptIds.add(pendingAttempt.id);
      setQualificationOverrides((current) =>
        pruneQualificationOverrides(current, retainedAttemptIds),
      );
    }, 0);
    return () => window.clearTimeout(timer);
  }, [data.current_entry, data.queue_entries]);

  const updateQualificationChecklist = useCallback(
    (attemptId: string, checklist: ProspectingQualificationChecklist) => {
      setQualificationOverrides((current) => ({
        ...current,
        [attemptId]: checklist,
      }));
    },
    [],
  );

  const refreshWorkspace = useCallback(() => {
    router.refresh();
  }, [router]);

  async function request<T>(path: string, method: "POST", body?: object): Promise<T | null> {
    setStatus("saving");
    setMessage("");
    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;
      const response = await fetch(`${apiBaseUrl}${path}`, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "The operation could not be completed.");
      }
      setStatus("saved");
      setMessage("Saved.");
      return (await response.json()) as T;
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "The operation could not be completed.");
      return null;
    }
  }

  async function requestWrapUp<T>(
    path: string,
    body: object,
  ): Promise<{ data: T | null; retryable: boolean }> {
    setStatus("saving");
    setMessage("");
    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;
      const response = await fetch(`${apiBaseUrl}${path}`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        const retryable =
          [408, 425, 429].includes(response.status) || response.status >= 500;
        setStatus("error");
        setMessage(
          `${payload?.detail ?? "The wrap-up could not be completed."}${
            retryable ? " Use Retry safe wrap-up; Stonegate will send the exact same request." : ""
          }`,
        );
        return { data: null, retryable };
      }
      setStatus("saved");
      setMessage("Wrap-up saved by Stonegate.");
      return { data: (await response.json()) as T, retryable: false };
    } catch (error) {
      setStatus("error");
      setMessage(
        `${
          error instanceof Error ? error.message : "The wrap-up response was lost."
        } Use Retry safe wrap-up; Stonegate will send the exact same request.`,
      );
      return { data: null, retryable: true };
    }
  }

  async function startCurrent() {
    if (!entry) return;
    pendingWrapUpRef.current = null;
    setPendingWrapUpAttemptId(null);
    setLastWrapUp(null);
    technicalFailureSubmissionRef.current = null;
    const result = await request<ProspectingEntry>(
      `/api/v1/prospecting/entries/${entry.id}/start`,
      "POST",
    );
    if (result) applyOptimisticEntry(result);
  }

  async function completeCurrent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeAttempt || !entry?.script) return;
    if (wrapUpInFlightRef.current) return;
    const form = event.currentTarget;
    const formData = new FormData(form);
    let pending = pendingWrapUpRef.current;
    if (!pending || pending.attemptId !== activeAttempt.id) {
      const callbackAt = value(formData, "callback_at");
      const handoffUserId = value(formData, "handoff_user_id");
      const appointmentStartAt = value(formData, "appointment_start_at");
      const appointmentLocationType = value(formData, "appointment_location_type");
      const appointmentLocation = value(formData, "appointment_location");
      const validationMessage = validateProspectingWrapUp({
        outcome,
        callbackAt,
        handoffUserId,
        appointmentStartAt,
        appointmentLocationType,
        appointmentLocation,
        propertyAddress: entry.property_address,
        qualificationSaveBlocked: qualificationOutcomeBlocked,
        missingWarmHandoffCount: isWarm
          ? activeAttempt.qualification_checklist.missing_required_keys.length
          : 0,
        nativeDialer: nativeDialerAvailable,
        nativeWrapUpReady: dialerRuntime.wrapUpReady,
        technicalFailure: dialerRuntime.technicalFailure,
      });
      if (validationMessage) {
        setStatus("error");
        setMessage(validationMessage);
        return;
      }
      pending = {
        attemptId: activeAttempt.id,
        payload: {
          outcome,
          idempotency_key: crypto.randomUUID(),
          browser_session_id: dialerLease?.browserSessionId ?? null,
          lease_token: dialerLease?.leaseToken ?? null,
          qualification_answers: {},
          notes: value(formData, "notes") || null,
          callback_at: requiresCallback ? localDateTimeToIso(callbackAt) : null,
          handoff_user_id: isWarm ? handoffUserId || null : null,
          appointment_start_at: isAppointment
            ? localDateTimeToIso(appointmentStartAt)
            : null,
          appointment_location_type: isAppointment
            ? (appointmentLocationType as ProspectingAttemptCompletionPayload["appointment_location_type"])
            : null,
          appointment_location: isAppointment ? appointmentLocation || null : null,
          compliance_flags: formData
            .getAll("compliance_flags")
            .map((flag) => String(flag)),
        },
      };
      pendingWrapUpRef.current = pending;
      setPendingWrapUpAttemptId(activeAttempt.id);
    }

    wrapUpInFlightRef.current = true;
    const result = await requestWrapUp<ProspectingEntry>(
      `/api/v1/prospecting/attempts/${activeAttempt.id}/complete`,
      pending.payload,
    ).finally(() => {
      wrapUpInFlightRef.current = false;
    });
    if (result.data) {
      const savedEntry = result.data;
      const savedOutcome = pending.payload.outcome;
      pendingWrapUpRef.current = null;
      setPendingWrapUpAttemptId(null);
      setLastWrapUp(
        createProspectingWrapUpReceipt(
          savedEntry,
          savedOutcome,
          activeAttempt.id,
          dialerRuntime.recipient ?? entry.phone,
        ),
      );
      if (dialerLease) applyOptimisticEntry(savedEntry);
      else {
        optimisticEntryRef.current = null;
        setOptimisticEntry(null);
        setEntry(
          data.queue_entries.find(
            (item) => item.id !== savedEntry.id && item.is_actionable,
          ) ?? null,
        );
      }
      form.reset();
      setOutcome("no_answer");
      router.refresh();
    } else if (!result.retryable) {
      pendingWrapUpRef.current = null;
      setPendingWrapUpAttemptId(null);
    }
  }

  async function completeTechnicalFailure() {
    if (!activeAttempt || !entry || !dialerLease) {
      setStatus("error");
      setMessage("The active native dialer lease is required to record a technical failure.");
      return;
    }
    if (wrapUpInFlightRef.current) return;
    let pending = technicalFailureSubmissionRef.current;
    if (!pending || pending.attemptId !== activeAttempt.id) {
      pending = { attemptId: activeAttempt.id, idempotencyKey: crypto.randomUUID() };
      technicalFailureSubmissionRef.current = pending;
    }
    const payload: ProspectingTechnicalFailurePayload = {
      idempotency_key: pending.idempotencyKey,
      browser_session_id: dialerLease.browserSessionId,
      lease_token: dialerLease.leaseToken,
    };
    wrapUpInFlightRef.current = true;
    const result = await request<ProspectingEntry>(
      `/api/v1/prospecting/attempts/${activeAttempt.id}/technical-failure`,
      "POST",
      payload,
    ).finally(() => {
      wrapUpInFlightRef.current = false;
    });
    if (!result) return;
    technicalFailureSubmissionRef.current = null;
    pendingWrapUpRef.current = null;
    setPendingWrapUpAttemptId(null);
    setLastWrapUp(createTechnicalFailureReceipt(result, activeAttempt.id));
    applyOptimisticEntry(result);
    router.refresh();
  }

  async function reviewHandoff(
    event: FormEvent<HTMLFormElement>,
    handoff: ProspectHandoff,
    decision: "accepted" | "needs_correction" | "rejected",
  ) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const result = await request(
      `/api/v1/prospecting/handoffs/${handoff.id}/decision`,
      "POST",
      {
        decision,
        reason_code: value(formData, "reason_code") || null,
        reason: value(formData, "reason") || null,
      },
    );
    if (result) router.refresh();
  }

  async function createScript(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const result = await request("/api/v1/prospecting/scripts", "POST", {
      asset_class: value(formData, "asset_class") || "house",
      title: value(formData, "title"),
      opening_script: value(formData, "opening_script"),
      qualification_questions: standardQuestions.map(([key, label, fallbackPrompt, required]) => ({
        key,
        label,
        prompt: value(formData, `${key}_prompt`) || fallbackPrompt,
        answer_type:
          key === "occupancy" ? "choice" : "text",
        choices:
          key === "occupancy" ? ["Owner occupied", "Tenant occupied", "Vacant"] : [],
        required_for_handoff: required,
      })),
    });
    if (result) {
      form.reset();
      router.refresh();
    }
  }

  async function approveScript(scriptId: string) {
    const result = await request(`/api/v1/prospecting/scripts/${scriptId}/approve`, "POST");
    if (result) router.refresh();
  }

  async function analyzeProspect(entryId: string) {
    const result = await request<{
      message: string;
      recommendation: ProspectingCopilotRecommendation | null;
    }>(`/api/v1/prospecting/entries/${entryId}/copilot/analyze`, "POST", {});
    if (result?.recommendation) {
      setLocalRecommendation(result.recommendation);
      setEditedSummary(result.recommendation.output_payload.pre_call_summary);
    } else if (result) {
      setMessage(result.message);
    }
  }

  async function reviewProspectBrief(
    recommendation: ProspectingCopilotRecommendation,
    decision: "accepted" | "edited" | "rejected",
  ) {
    const finalOutput: ProspectingCopilotOutput | undefined =
      decision === "edited"
        ? {
            ...recommendation.output_payload,
            pre_call_summary: editedSummary.trim(),
          }
        : undefined;
    const result = await request(
      `/api/v1/prospecting/copilot/recommendations/${recommendation.id}/review`,
      "POST",
      {
        decision,
        final_output: finalOutput,
        notes: reviewNotes.trim() || null,
        estimated_time_saved_seconds: 120,
      },
    );
    if (result) {
      setLocalRecommendation({
        ...recommendation,
        status: decision,
        output_payload: finalOutput ?? recommendation.output_payload,
        reviewed_at: new Date().toISOString(),
      });
      setEditingBrief(false);
    }
  }

  async function analyzeQuality(attemptId: string) {
    const result = await request(
      `/api/v1/prospecting/attempts/${attemptId}/quality/analyze`,
      "POST",
    );
    if (result) router.refresh();
  }

  async function reviewQuality(
    item: ProspectingCallQuality,
    decision: "approved" | "corrected" | "rejected",
    finalOutput?: ProspectingCallQualityOutput,
  ) {
    const result = await request(
      `/api/v1/prospecting/attempts/${item.attempt_id}/quality/review`,
      "POST",
      {
        decision,
        final_output: finalOutput,
        notes: decision === "corrected" ? "Manager corrected the coaching output." : null,
      },
    );
    if (result) router.refresh();
  }

  return (
    <div className={styles.workspace}>
      <section className={styles.metrics} aria-label="Prospecting queue summary">
        <div><span>Due now</span><strong>{data.queue.ready}</strong></div>
        <div><span>Callbacks due</span><strong>{data.queue.callbacks_due}</strong></div>
        <div><span>Retries due</span><strong>{data.queue.retries_due ?? 0}</strong></div>
        <div><span>Scheduled</span><strong>{data.queue.callbacks_scheduled + (data.queue.retries_scheduled ?? 0)}</strong></div>
        <div><span>Corrections</span><strong>{data.queue.corrections}</strong></div>
        <div><span>In progress</span><strong>{data.queue.in_progress}</strong></div>
        <div><span>Handoffs waiting</span><strong>{data.queue.handoff_pending}</strong></div>
      </section>

      {nativeDialerEnabled ? (
        <section aria-labelledby="callback-heading" className={styles.callbackPanel}>
          <header>
            <div>
              <span>Inbound call routing</span>
              <h2 id="callback-heading">Recent callbacks</h2>
              <p>Caller matches update here without changing the prospect or call you are working.</p>
            </div>
            <button className={styles.secondaryButton} onClick={() => void refreshCallbacks()} type="button">
              Refresh callbacks
            </button>
          </header>
          {!callbacksAvailable ? (
            <p className={styles.dialerInlineWarning} role="status">
              Callback status is temporarily unavailable. Existing cards are the last confirmed
              snapshot{callbacksLastSuccessAt ? ` from ${formatDateTime(callbacksLastSuccessAt)}` : ""}.
            </p>
          ) : null}
          <div className={styles.callbackCardGrid}>
            {callbacks.items.map((callback) => (
              <article className={styles.callbackCard} key={callback.id}>
                <div className={styles.callbackCardHeader}>
                  <div>
                    <strong>{callback.prospect_name ?? callback.caller_number}</strong>
                    <span>{callback.property_address ?? "Property not matched"}</span>
                  </div>
                  <span
                    className={
                      callback.match_status === "matched"
                        ? styles.statusGood
                        : callback.match_status === "pending"
                          ? styles.statusNeutral
                          : styles.statusWarning
                    }
                  >
                    {labelize(callback.match_status)}
                  </span>
                </div>
                <dl>
                  <div><dt>Caller</dt><dd>{callback.caller_number}</dd></div>
                  <div><dt>Status</dt><dd>{labelize(callback.status)}</dd></div>
                  <div><dt>Received</dt><dd>{formatDateTime(callback.received_at)}</dd></div>
                  <div><dt>Match confidence</dt><dd>{formatPercent(callback.match_confidence_basis_points)}</dd></div>
                </dl>
                <div className={styles.callbackCardFooter}>
                  <small>
                    {callback.match_status === "ambiguous"
                      ? `${callback.candidate_count} possible prospects — review before calling back.`
                      : callback.match_status === "unknown"
                        ? "No assigned prospect matched this number."
                        : callback.assigned_user_name
                          ? `Assigned to ${callback.assigned_user_name}`
                          : callback.voice_line_label}
                  </small>
                  <button
                    className={styles.primaryButton}
                    disabled={
                      !callback.can_open ||
                      callbackOpenBlocked ||
                      Boolean(openingCallbackId)
                    }
                    onClick={() => void openCallback(callback)}
                    title={
                      callbackOpenBlocked
                        ? "Finish the current call before opening another prospect."
                        : undefined
                    }
                    type="button"
                  >
                    {openingCallbackId === callback.id ? "Opening..." : "Open prospect"}
                  </button>
                </div>
              </article>
            ))}
            {callbacksAvailable && !callbacks.items.length ? (
              <p className={styles.dialerEmptyState}>No recent callbacks are waiting for this caller.</p>
            ) : null}
          </div>
        </section>
      ) : null}

      <nav className={styles.viewTabs} aria-label="Prospecting views">
        {availableViews.map((item) => (
          <button
            aria-pressed={view === item.key}
            className={view === item.key ? styles.activeTab : undefined}
            key={item.key}
            onClick={() => setView(item.key)}
            type="button"
          >
            {item.label}{item.count ? ` (${item.count})` : ""}
          </button>
        ))}
      </nav>

      {message ? (
        <p className={status === "error" ? styles.error : styles.notice}>{message}</p>
      ) : null}

      {nativeDialerEnabled ? (
        <ProspectingDialer
          currentUserId={data.current_user_id}
          entries={queueEntries}
          onEntryChange={selectEntry}
          onLeaseChange={setDialerLease}
          onNativeModeChange={setNativeDialerAvailable}
          onOwnershipChange={setDialerLeadership}
          onRuntimeChange={setDialerRuntime}
          onWorkspaceRefresh={refreshWorkspace}
          selectedEntry={entry}
        />
      ) : null}

      {lastWrapUp ? <WrapUpReceipt receipt={lastWrapUp} /> : null}

      {view === "workbench" ? (
        <>
          <CopilotLauncher
            attentionCount={data.copilot.work_items.length}
            description="Prepares assigned call context, approved script guidance, handoff notes, and reviewed call coaching."
            name="Prospecting Copilot"
            summary={data.copilot.work_items.find((item) => item.entry_id === selectedCopilotEntryId)?.recommended_action ?? "The assigned calling queue is ready."}
            triggerLabel="Prepare selected call"
          >
            <ProspectingCopilotPrep
              copilot={data.copilot}
              editing={editingBrief}
              editedSummary={editedSummary}
              localRecommendation={localRecommendation}
              onAnalyze={analyzeProspect}
              onEdit={() => setEditingBrief(true)}
              onEditedSummary={setEditedSummary}
              onReview={reviewProspectBrief}
              onReviewNotes={setReviewNotes}
              onSelect={(entryId) => {
                setSelectedCopilotEntryId(entryId);
                setLocalRecommendation(null);
                setEditingBrief(false);
              }}
              reviewNotes={reviewNotes}
              saving={status === "saving"}
              selectedEntryId={selectedCopilotEntryId}
            />
          </CopilotLauncher>
          <div className={styles.workbenchFlow}>
            <ShiftQueue
              activeAttemptId={activeAttempt?.id ?? null}
              batchQueues={data.batch_queues}
              entries={queueEntries}
              filter={queueFilter}
              lockSelectionToCurrentAttempt={Boolean(
                activeAttempt && entryAssignedToCurrentUser,
              )}
              onFilter={setQueueFilter}
              onSelect={selectEntry}
              selectedEntryId={entry?.id ?? ""}
            />
            <WorkbenchView
              activeAttempt={activeAttempt}
              acquisitionUsers={data.acquisition_users}
              attemptAuthorityKnown={attemptAuthorityKnown}
              canMutateAttempt={ownsAttemptMutationAuthority}
              canAutosaveQualification={ownsAttemptMutationAuthority}
              dialerLease={dialerLease}
              entry={entry}
              entryAssignedToCurrentUser={entryAssignedToCurrentUser}
              isAppointment={isAppointment}
              isWarm={isWarm}
              manualAttemptAuthority={manualAttemptAuthority}
              nativeDialerAvailable={nativeDialerAvailable}
              nativeDialerEnabled={nativeDialerEnabled}
              nativeDialerLeaseActive={Boolean(dialerLease)}
              nativeWrapUpReady={dialerRuntime.wrapUpReady}
              onComplete={completeCurrent}
              onTechnicalFailure={completeTechnicalFailure}
              onQualificationBlockingChange={setQualificationBlocking}
              onQualificationChecklistChange={updateQualificationChecklist}
              onOutcomeChange={(nextOutcome) => {
                if (pendingWrapUpRef.current?.attemptId !== activeAttempt?.id) {
                  setOutcome(nextOutcome);
                }
              }}
              onStart={startCurrent}
              outcome={outcome}
              requiresCallback={requiresCallback}
              returnedHandoffs={data.returned_handoffs}
              saving={status === "saving" || qualificationOutcomeBlocked}
              technicalFailure={dialerRuntime.technicalFailure}
              technicalFailureDetail={
                dialerRuntime.providerError ?? dialerRuntime.terminalResult
              }
              wrapUpRetryPending={pendingWrapUpAttemptId === activeAttempt?.id}
              key={`${entry?.id ?? "empty-queue"}:${activeAttempt?.id ?? "not-started"}`}
            />
          </div>
        </>
      ) : null}

      {view === "quality" ? (
        <CallQualityView
          canManage={data.can_manage}
          items={data.copilot.quality_queue}
          onAnalyze={analyzeQuality}
          onReview={reviewQuality}
          saving={status === "saving"}
        />
      ) : null}

      {view === "handoffs" && data.can_manage ? (
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div><span>Acquisitions review</span><h3>Warm seller handoffs</h3></div>
            <strong>{data.pending_handoffs.length} waiting</strong>
          </div>
          <div className={styles.handoffList}>
            {data.pending_handoffs.length === 0 ? (
              <p className={styles.empty}>No handoffs are awaiting review.</p>
            ) : null}
            {data.pending_handoffs.map((handoff) => (
              <article className={styles.handoff} key={handoff.id}>
                <header>
                  <div><strong>{handoff.seller_name}</strong><span>{handoff.property_address}</span></div>
                  <Link href={`/os/leads/${handoff.lead_id}`}>Open lead</Link>
                </header>
                <dl className={styles.handoffMeta}>
                  <div><dt>Caller</dt><dd>{handoff.caller_name}</dd></div>
                  <div><dt>Assigned to</dt><dd>{handoff.assigned_user_name}</dd></div>
                  <div><dt>Outcome</dt><dd>{labelize(handoff.outcome)}</dd></div>
                  <div><dt>Submitted</dt><dd>{formatDateTime(handoff.submitted_at)}</dd></div>
                </dl>
                <div className={styles.answerGrid}>
                  {Object.entries(handoff.qualification_answers).map(([key, answer]) => (
                    <div key={key}><span>{labelize(key)}</span><strong>{answer}</strong></div>
                  ))}
                </div>
                {handoff.notes ? <p className={styles.handoffNotes}>{handoff.notes}</p> : null}
                <div className={styles.reviewActions}>
                  <form
                    className={styles.reviewForm}
                    onSubmit={(event) => reviewHandoff(event, handoff, "accepted")}
                  >
                    <label><span>Acceptance note</span><input name="reason" placeholder="Optional" /></label>
                    <button className={styles.primaryButton} type="submit">Accept handoff</button>
                  </form>
                  <form
                    className={styles.reviewForm}
                    onSubmit={(event) => reviewHandoff(event, handoff, "needs_correction")}
                  >
                    <label>
                      <span>Correction type</span>
                      <select name="reason_code" defaultValue="correction_qualification" required>
                        <option value="correction_decision_maker">Decision maker</option>
                        <option value="correction_property_details">Property details</option>
                        <option value="correction_interest_evidence">Interest evidence</option>
                        <option value="correction_follow_up_permission">Follow-up permission</option>
                        <option value="correction_qualification">Qualification answers</option>
                        <option value="correction_other">Other correction</option>
                      </select>
                    </label>
                    <label><span>Required correction</span><input name="reason" placeholder="Tell the caller exactly what is missing" required /></label>
                    <button className={styles.secondaryButton} type="submit">Return for correction</button>
                  </form>
                  <form
                    className={styles.reviewForm}
                    onSubmit={(event) => reviewHandoff(event, handoff, "rejected")}
                  >
                    <label>
                      <span>Rejection type</span>
                      <select name="reason_code" defaultValue="rejected_not_interested" required>
                        <option value="rejected_not_interested">Not interested</option>
                        <option value="rejected_wrong_party">Wrong party</option>
                        <option value="rejected_duplicate">Duplicate</option>
                        <option value="rejected_already_sold">Already sold</option>
                        <option value="rejected_invalid_property">Invalid property</option>
                        <option value="rejected_no_follow_up_permission">No follow-up permission</option>
                        <option value="rejected_other">Other rejection</option>
                      </select>
                    </label>
                    <label><span>Rejection reason</span><input name="reason" placeholder="Explain why this is not a warm lead" required /></label>
                    <button className={styles.dangerButton} type="submit">Reject handoff</button>
                  </form>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {view === "performance" ? (
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div><span>Trailing seven days</span><h3>Caller performance</h3></div>
          </div>
          <div className={styles.tableWrap}>
            <table>
              <thead><tr><th>Date</th><th>Caller</th><th>Attempts</th><th>Contacts</th><th>Contact rate</th><th>Handoffs</th><th>Accepted</th><th>Script completion</th><th>Bad data</th><th>DNC</th></tr></thead>
              <tbody>
                {data.scorecards.map((row) => (
                  <tr key={`${row.caller_user_id}-${row.score_date}`}>
                    <td>{row.score_date}</td><td><strong>{row.caller_name}</strong></td><td>{row.attempts}</td><td>{row.contacts}</td><td>{formatPercent(row.contact_rate_basis_points)}</td><td>{row.handoffs}</td><td>{row.accepted_handoffs}</td><td>{formatPercent(row.script_completion_rate_basis_points)}</td><td>{formatPercent(row.data_quality_issue_rate_basis_points)}</td><td>{row.dnc_requests}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.scorecards.length === 0 ? <p className={styles.empty}>Performance appears after completed attempts.</p> : null}
          </div>
        </section>
      ) : null}

      {view === "scripts" && data.can_manage ? (
        <section className={styles.scriptLayout}>
          <div className={styles.section}>
            <div className={styles.sectionHeader}><div><span>Controlled revisions</span><h3>Caller script history</h3></div></div>
            <div className={styles.scriptList}>
              {data.scripts.map((script) => (
                <article key={script.id}>
                  <div><strong>v{script.version_number} · {script.title}</strong><span>{labelize(script.asset_class)} · {labelize(script.status)} · {script.created_by_name}</span></div>
                  {script.status === "draft" ? <button onClick={() => approveScript(script.id)} type="button">Approve</button> : <span>{script.approved_at ? formatDateTime(script.approved_at) : "Not approved"}</span>}
                </article>
              ))}
            </div>
          </div>
          <form className={styles.scriptForm} onSubmit={createScript}>
            <div className={styles.sectionHeader}><div><span>New immutable version</span><h3>Draft caller script</h3></div></div>
            <label><span>Property workflow</span><select defaultValue="house" name="asset_class"><option value="house">House</option><option value="land">Land</option></select></label>
            <label><span>Version title</span><input name="title" placeholder="Stonegate seller conversation" required /></label>
            <label><span>Opening</span><textarea name="opening_script" placeholder="Introduce Stonegate, identify the property, and ask permission to continue." required /></label>
            {standardQuestions.map(([key, label, prompt]) => (
              <label key={key}><span>{label} prompt</span><input defaultValue={prompt} name={`${key}_prompt`} required /></label>
            ))}
            <button className={styles.primaryButton} type="submit">Create draft version</button>
          </form>
        </section>
      ) : null}
    </div>
  );
}

function ProspectingCopilotPrep({
  copilot,
  editedSummary,
  editing,
  localRecommendation,
  onAnalyze,
  onEdit,
  onEditedSummary,
  onReview,
  onReviewNotes,
  onSelect,
  reviewNotes,
  saving,
  selectedEntryId,
}: {
  copilot: ProspectingWorkbenchOverview["copilot"];
  editedSummary: string;
  editing: boolean;
  localRecommendation: ProspectingCopilotRecommendation | null;
  onAnalyze: (entryId: string) => void;
  onEdit: () => void;
  onEditedSummary: (value: string) => void;
  onReview: (
    recommendation: ProspectingCopilotRecommendation,
    decision: "accepted" | "edited" | "rejected",
  ) => void;
  onReviewNotes: (value: string) => void;
  onSelect: (entryId: string) => void;
  reviewNotes: string;
  saving: boolean;
  selectedEntryId: string;
}) {
  const selected =
    copilot.work_items.find((item) => item.entry_id === selectedEntryId) ?? null;
  const recommendation =
    localRecommendation?.entry_id === selectedEntryId
      ? localRecommendation
      : copilot.recommendations.find((item) => item.entry_id === selectedEntryId) ?? null;
  const output = recommendation?.output_payload ?? null;
  return (
    <section className={styles.copilotPrep}>
      <div className={styles.copilotGuard}>
        <div><ShieldAlert size={17} /><strong>Draft-only Prospecting Copilot</strong></div>
        <span>Cannot call, change eligibility, select a disposition, or submit a handoff.</span>
        <small>
          Runtime {labelize(copilot.runtime_status)} · Priority tools {labelize(copilot.priority_capability_status)}
        </small>
      </div>
      <div className={styles.prepGrid}>
        <aside className={styles.priorityQueue}>
          <header><div><span>Eligibility-first ranking</span><h3>Assigned priorities</h3></div><Brain size={18} /></header>
          {copilot.work_items.map((item) => (
            <button
              className={selectedEntryId === item.entry_id ? styles.selectedPriority : ""}
              key={item.entry_id}
              onClick={() => onSelect(item.entry_id)}
              type="button"
            >
              <span>{item.priority_score} · {labelize(item.priority_band)}</span>
              <strong>{item.seller_name}</strong>
              <small>{item.property_address ?? "Address incomplete"}</small>
              <p>{item.recommended_action}</p>
            </button>
          ))}
          {!copilot.work_items.length ? <p className={styles.empty}>No eligible assigned record is due.</p> : null}
        </aside>
        <div className={styles.preCallBrief}>
          {selected ? (
            <>
              <header>
                <div><span>Pre-call preparation</span><h3>{selected.seller_name}</h3><p>{selected.campaign_name}</p></div>
                <button
                  disabled={saving || recommendation?.status === "draft"}
                  onClick={() => onAnalyze(selected.entry_id)}
                  type="button"
                >
                  <Sparkles size={15} />{recommendation ? "Refresh brief" : "Generate brief"}
                </button>
              </header>
              <div className={styles.deterministicPrep}>
                <strong>{selected.recommended_action}</strong>
                {selected.reasons.map((reason) => <span key={reason}>{reason}</span>)}
                {selected.data_quality_warnings.map((warning) => <span className={styles.warning} key={warning}><FileWarning size={14} />{warning}</span>)}
              </div>
              {output && recommendation ? (
                <div className={styles.generatedPrep}>
                  <div className={styles.prepSummary}>
                    <div><span>Seller brief</span>{editing ? <textarea onChange={(event) => onEditedSummary(event.target.value)} rows={4} value={editedSummary} /> : <p>{output.pre_call_summary}</p>}</div>
                    <strong>{output.confidence}% confidence</strong>
                  </div>
                  <div className={styles.prepColumns}>
                    <section><span>Opening guidance</span><p>{output.opening_guidance}</p></section>
                    <section><span>Why now</span><p>{output.priority_explanation}</p></section>
                    <section><span>Required questions</span><ul>{output.required_questions.map((item) => <li key={item}>{item}</li>)}</ul></section>
                    <section><span>Compliance reminders</span><ul>{output.compliance_reminders.map((item) => <li key={item}>{item}</li>)}</ul></section>
                  </div>
                  <details><summary>Property, attempts, evidence, and data warnings</summary><div className={styles.evidenceColumns}><section><span>Property</span><ul>{output.property_context.map((item) => <li key={item}>{item}</li>)}</ul></section><section><span>Prior attempts</span><ul>{output.prior_attempt_context.map((item) => <li key={item}>{item}</li>)}</ul></section><section><span>Evidence</span><ul>{output.evidence.map((item) => <li key={item}>{item}</li>)}</ul></section><section><span>Warnings</span><ul>{output.data_quality_warnings.map((item) => <li key={item}>{item}</li>)}</ul></section></div></details>
                  {recommendation.status === "draft" ? (
                    <footer className={styles.briefReview}>
                      {editing ? <input onChange={(event) => onReviewNotes(event.target.value)} placeholder="What did you correct?" value={reviewNotes} /> : null}
                      <div>
                        <button className={styles.rejectAction} disabled={saving} onClick={() => onReview(recommendation, "rejected")} type="button"><XCircle size={15} />Reject</button>
                        <button className={styles.editAction} disabled={saving} onClick={onEdit} type="button"><Pencil size={15} />Correct</button>
                        <button disabled={saving} onClick={() => onReview(recommendation, editing ? "edited" : "accepted")} type="button"><CheckCircle2 size={15} />{editing ? "Save correction" : "Accept brief"}</button>
                      </div>
                    </footer>
                  ) : <p className={styles.reviewedBrief}><CheckCircle2 size={15} />Reviewed: {labelize(recommendation.status)}. No call or record action was taken.</p>}
                </div>
              ) : (
                <div className={styles.prepEmpty}><Brain size={22} /><strong>Generate a governed pre-call brief</strong><p>Deterministic eligibility and priority are already active. AI generation must be enabled separately.</p></div>
              )}
            </>
          ) : <p className={styles.empty}>Select an eligible assigned prospect.</p>}
        </div>
      </div>
    </section>
  );
}

function CallQualityView({
  canManage,
  items,
  onAnalyze,
  onReview,
  saving,
}: {
  canManage: boolean;
  items: ProspectingCallQuality[];
  onAnalyze: (attemptId: string) => void;
  onReview: (
    item: ProspectingCallQuality,
    decision: "approved" | "corrected" | "rejected",
    finalOutput?: ProspectingCallQualityOutput,
  ) => void;
  saving: boolean;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [correction, setCorrection] = useState<ProspectingCallQualityOutput | null>(null);

  function beginCorrection(item: ProspectingCallQuality) {
    if (!item.ai_output) return;
    setEditingId(item.id);
    setCorrection(structuredClone(item.ai_output));
  }

  function updateCorrection(
    field: keyof ProspectingCallQualityOutput,
    value: ProspectingCallQualityOutput[keyof ProspectingCallQualityOutput],
  ) {
    setCorrection((current) => (current ? { ...current, [field]: value } : current));
  }

  return (
    <section className={styles.section}>
      <div className={styles.sectionHeader}>
        <div><span>Evidence-gated coaching</span><h3>Prospecting call quality</h3></div>
        <strong>{items.filter((item) => item.escalation_required).length} escalations</strong>
      </div>
      <div className={styles.qualityList}>
        {items.map((item) => {
          const output = item.final_output ?? item.ai_output;
          return (
            <article className={item.escalation_required ? styles.escalatedQuality : ""} key={item.id}>
              <header>
                <div><strong>{item.seller_name}</strong><span>{item.caller_name} · {item.outcome ? labelize(item.outcome) : "No outcome"}</span></div>
                <span className={styles.qualityStatus}>{labelize(item.status)}</span>
              </header>
              {item.compliance_flags.length ? <p className={styles.complianceAlert}><ShieldAlert size={15} />{item.compliance_flags.map(labelize).join(", ")}</p> : null}
              <div className={styles.scoreStrip}>
                {Object.entries(item.deterministic_scores).map(([key, score]) => (
                  <div key={key}><span>{labelize(key.replace("_score", ""))}</span><strong>{score === null ? "Evidence needed" : `${score}%`}</strong></div>
                ))}
              </div>
              {output ? (
                <div className={styles.coachingOutput}>
                  <p>{output.call_summary}</p>
                  <div><section><span>Suggested disposition</span><strong>{labelize(output.suggested_disposition)}</strong><p>{output.disposition_reason}</p></section><section><span>Coaching</span><ul>{output.coaching_points.map((point) => <li key={point}>{point}</li>)}</ul></section></div>
                </div>
              ) : <p className={styles.qualityExplanation}>{item.transcript_available ? "Approved transcript ready for governed analysis." : "Transcript-based scores are unavailable until a disclosed recording is transcribed and approved."}</p>}
              {editingId === item.id && correction ? (
                <div className={styles.qualityCorrection}>
                  <label><span>Manager summary</span><textarea rows={3} value={correction.call_summary} onChange={(event) => updateCorrection("call_summary", event.target.value)} /></label>
                  <div className={styles.correctionGrid}>
                    <label><span>Suggested disposition</span><select value={correction.suggested_disposition} onChange={(event) => updateCorrection("suggested_disposition", event.target.value as ProspectingCallQualityOutput["suggested_disposition"])}>{PROSPECTING_OUTCOME_OPTIONS.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}</select></label>
                    <label><span>Confidence</span><input max="100" min="0" type="number" value={correction.confidence} onChange={(event) => updateCorrection("confidence", Number(event.target.value))} /></label>
                    {(["script_adherence_score", "qualification_completeness_score", "objection_handling_score", "data_quality_score", "handoff_quality_score"] as const).map((field) => (
                      <label key={field}><span>{labelize(field.replace("_score", ""))}</span><input max="100" min="0" type="number" value={correction[field]} onChange={(event) => updateCorrection(field, Number(event.target.value))} /></label>
                    ))}
                  </div>
                  <label><span>Disposition reason</span><textarea rows={2} value={correction.disposition_reason} onChange={(event) => updateCorrection("disposition_reason", event.target.value)} /></label>
                  <label><span>Coaching points, one per line</span><textarea rows={3} value={correction.coaching_points.join("\n")} onChange={(event) => updateCorrection("coaching_points", event.target.value.split("\n").map((point) => point.trim()).filter(Boolean))} /></label>
                </div>
              ) : null}
              <footer>
                {item.transcript_available && !output ? <button disabled={saving} onClick={() => onAnalyze(item.attempt_id)} type="button"><Sparkles size={15} />Analyze call</button> : null}
                {canManage && item.status === "needs_review" && item.ai_output ? editingId === item.id && correction ? <><button className={styles.rejectAction} disabled={saving} onClick={() => { setEditingId(null); setCorrection(null); }} type="button">Cancel correction</button><button disabled={saving} onClick={() => onReview(item, "corrected", correction)} type="button"><CheckCircle2 size={15} />Save correction</button></> : <><button className={styles.rejectAction} disabled={saving} onClick={() => onReview(item, "rejected")} type="button">Reject coaching</button><button className={styles.editAction} disabled={saving} onClick={() => beginCorrection(item)} type="button"><Pencil size={15} />Correct</button><button disabled={saving} onClick={() => onReview(item, "approved")} type="button">Approve coaching</button></> : null}
              </footer>
            </article>
          );
        })}
        {!items.length ? <p className={styles.empty}>Quality records appear after completed prospecting attempts.</p> : null}
      </div>
    </section>
  );
}

function ShiftQueue({
  activeAttemptId,
  batchQueues,
  entries,
  filter,
  lockSelectionToCurrentAttempt,
  onFilter,
  onSelect,
  selectedEntryId,
}: {
  activeAttemptId: string | null;
  batchQueues: ProspectingWorkbenchOverview["batch_queues"];
  entries: ProspectingEntry[];
  filter: QueueFilter;
  lockSelectionToCurrentAttempt: boolean;
  onFilter: (filter: QueueFilter) => void;
  onSelect: (entry: ProspectingEntry) => void;
  selectedEntryId: string;
}) {
  const visibleEntries = entries.filter((item) => {
    if (filter === "due") return item.is_actionable;
    if (filter === "callbacks") return item.queue_kind === "callback_due";
    if (filter === "retries") return item.queue_kind === "retry_due";
    if (filter === "corrections") return item.queue_kind === "correction_required";
    if (filter === "scheduled") {
      return ["callback_scheduled", "retry_scheduled"].includes(item.queue_kind);
    }
    if (filter === "waiting") return item.queue_kind === "handoff_pending";
    return true;
  });
  const filters: Array<{ key: QueueFilter; label: string }> = [
    { key: "due", label: "Due now" },
    { key: "callbacks", label: "Callbacks" },
    { key: "retries", label: "Retries" },
    { key: "corrections", label: "Corrections" },
    { key: "scheduled", label: "Scheduled" },
    { key: "waiting", label: "Waiting" },
    { key: "all", label: "All assigned" },
  ];
  return (
    <section className={styles.shiftQueue}>
      <header>
        <div><span>Assigned shift</span><h3>Calling queue</h3></div>
        <nav aria-label="Calling queue filters">
          {filters.map((item) => (
            <button
              aria-pressed={filter === item.key}
              className={filter === item.key ? styles.activeQueueFilter : undefined}
              key={item.key}
              onClick={() => onFilter(item.key)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </nav>
      </header>
      <div className={styles.batchStrip}>
        {batchQueues.map((batch) => (
          <div key={batch.batch_id}>
            <span>{batch.campaign_name}</span>
            <strong>{batch.batch_name}</strong>
            <small>
              {batch.callbacks_due} callbacks · {batch.retries_due ?? 0} retries ·{" "}
              {batch.corrections} corrections ·{" "}
              {batch.ready} ready
            </small>
            <em className={styles.syncReady}>One-by-one calling</em>
          </div>
        ))}
      </div>
      <div className={styles.queueRows}>
        {visibleEntries.map((item) => {
          const blockedByActiveAttempt = Boolean(
            lockSelectionToCurrentAttempt &&
            activeAttemptId &&
            item.id !== selectedEntryId,
          );
          return (
            <button
              className={item.id === selectedEntryId ? styles.selectedQueueRow : undefined}
              disabled={blockedByActiveAttempt}
              key={item.id}
              onClick={() => onSelect(item)}
              type="button"
            >
              <span className={styles.queueState}>
                {item.queue_kind === "callback_due" ? <CalendarClock size={15} /> : null}
                {item.queue_kind === "retry_due" ? <Clock3 size={15} /> : null}
                {item.queue_kind === "correction_required" ? <AlertTriangle size={15} /> : null}
                {item.queue_kind === "in_progress" ? <PhoneCall size={15} /> : null}
                {item.queue_kind === "ready" ? <UserRoundCheck size={15} /> : null}
                {["callback_scheduled", "retry_scheduled"].includes(item.queue_kind) ? <Clock3 size={15} /> : null}
                {labelize(item.queue_kind)}
              </span>
              <strong>{item.legal_name}</strong>
              <small>{item.property_address ?? item.phone ?? "No property details"}</small>
              <span>{item.campaign_name} · {item.assigned_user_name}</span>
              {item.active_attempt?.qualification_checklist ? (
                <span className={styles.queueQualificationProgress}>
                  <span>
                    Qualification {item.active_attempt.qualification_checklist.answered_count}/
                    {item.active_attempt.qualification_checklist.total_count}
                  </span>
                  <progress
                    aria-label={`${item.legal_name} qualification progress`}
                    max={Math.max(
                      item.active_attempt.qualification_checklist.total_count,
                      1,
                    )}
                    value={item.active_attempt.qualification_checklist.answered_count}
                  />
                </span>
              ) : null}
              <time>{item.next_attempt_at ? formatDateTime(item.next_attempt_at) : `Record ${item.sequence_number}`}</time>
            </button>
          );
        })}
        {!visibleEntries.length ? (
          <p className={styles.empty}>No assigned records match this queue view.</p>
        ) : null}
      </div>
    </section>
  );
}

function WrapUpReceipt({ receipt }: { receipt: ProspectingWrapUpReceipt }) {
  const nextAction = receipt.nextAttemptAt
    ? receipt.nextAction.replace(
        receipt.nextAttemptAt,
        formatDateTime(receipt.nextAttemptAt),
      )
    : receipt.nextAction;
  return (
    <section
      aria-live="polite"
      className={`${styles.wrapUpReceipt} ${styles[`wrapUpReceipt_${receipt.tone}`]}`}
      role="status"
    >
      <CheckCircle2 aria-hidden="true" size={20} />
      <div>
        <span>Server-confirmed wrap-up · {receipt.sellerName}</span>
        <strong>{receipt.title}</strong>
        <p>{receipt.detail}</p>
        <small>
          {nextAction} · Queue status: {labelize(receipt.savedStatus)}
        </small>
      </div>
    </section>
  );
}

function WorkbenchView({
  activeAttempt,
  acquisitionUsers,
  attemptAuthorityKnown,
  canMutateAttempt,
  canAutosaveQualification,
  dialerLease,
  entry,
  entryAssignedToCurrentUser,
  isAppointment,
  isWarm,
  manualAttemptAuthority,
  nativeDialerAvailable,
  nativeDialerEnabled,
  nativeDialerLeaseActive,
  nativeWrapUpReady,
  onComplete,
  onOutcomeChange,
  onQualificationBlockingChange,
  onQualificationChecklistChange,
  onStart,
  onTechnicalFailure,
  outcome,
  requiresCallback,
  returnedHandoffs,
  saving,
  technicalFailure,
  technicalFailureDetail,
  wrapUpRetryPending,
}: {
  activeAttempt: ProspectingEntry["active_attempt"];
  acquisitionUsers: ProspectingWorkbenchOverview["acquisition_users"];
  attemptAuthorityKnown: boolean;
  canMutateAttempt: boolean;
  canAutosaveQualification: boolean;
  dialerLease: ActiveProspectingDialerLease | null;
  entry: ProspectingEntry | null;
  entryAssignedToCurrentUser: boolean;
  isAppointment: boolean;
  isWarm: boolean;
  manualAttemptAuthority: boolean;
  nativeDialerAvailable: boolean;
  nativeDialerEnabled: boolean;
  nativeDialerLeaseActive: boolean;
  nativeWrapUpReady: boolean;
  onComplete: (event: FormEvent<HTMLFormElement>) => void;
  onOutcomeChange: (outcome: ProspectingSellerOutcome) => void;
  onQualificationBlockingChange: (blocked: boolean) => void;
  onQualificationChecklistChange: (
    attemptId: string,
    checklist: ProspectingQualificationChecklist,
  ) => void;
  onStart: () => void;
  onTechnicalFailure: () => void;
  outcome: ProspectingSellerOutcome;
  requiresCallback: boolean;
  returnedHandoffs: ProspectHandoff[];
  saving: boolean;
  technicalFailure: boolean;
  technicalFailureDetail: string | null;
  wrapUpRetryPending: boolean;
}) {
  const [callbackValue, setCallbackValue] = useState("");
  const [appointmentLocationType, setAppointmentLocationType] =
    useState("seller_property");
  const [minimumDateTime] = useState(() =>
    dateToLocalInputValue(new Date(Date.now() + 60_000)),
  );
  const selectedOutcome = prospectingOutcomeOption(outcome);
  function setQuickCallback(hoursFromNow: number) {
    const target = new Date(Date.now() + hoursFromNow * 60 * 60 * 1000);
    setCallbackValue(dateToLocalInputValue(target));
  }
  if (!entry) {
    return <section className={styles.emptyState}><span>Queue clear</span><h3>No assigned prospect is due</h3><p>Future callbacks remain scheduled and will return here when due.</p></section>;
  }
  const activeScript = entry.script;
  if (!activeScript) {
    return <section className={styles.emptyState}><span>Queue paused</span><h3>An approved caller script is required</h3><p>An acquisition manager must approve the exact {entry.asset_class} script version pinned to this record before it can be worked.</p></section>;
  }
  const returned = returnedHandoffs.find((handoff) => handoff.prospect_id === entry.prospect_id);
  const missingWarmHandoffLabels = activeAttempt
    ? activeAttempt.qualification_checklist.missing_required_keys.map(
        (key) =>
          activeAttempt.qualification_checklist.items.find(
            (item) => item.question_key === key,
          )?.label ?? labelize(key),
      )
    : [];
  return (
    <section className={styles.workbenchGrid}>
      <aside className={styles.prospectPanel}>
        <div className={styles.queuePosition}><span>{entry.batch_name}</span><strong>{labelize(entry.queue_kind)}</strong></div>
        <div className={styles.sellerIdentity}>
          <span>{entry.source_name} · {entry.campaign_name}</span>
          <h3>{entry.legal_name}</h3>
          <p>{entry.property_address ?? "Property address unavailable"}</p>
          <div className={styles.prospectBadges}>
            <strong>{entry.asset_class === "land" ? "Land" : "House"}</strong>
            {entry.warnings.map((warning) => (
              <em key={warning}><AlertTriangle aria-hidden="true" size={13} />{warning}</em>
            ))}
          </div>
        </div>
        <div className={styles.providerState}>
          <span>Calling method</span>
          <strong className={styles.syncReady}>One-by-one calling</strong>
        </div>
        <dl className={styles.contactList}>
          {(entry.contact_points.length
            ? entry.contact_points
            : [
                ...(entry.phone ? [{ contact_type: "phone", value: entry.phone, rank: 1, is_primary: true, validation_status: "valid" }] : []),
                ...(entry.email ? [{ contact_type: "email", value: entry.email, rank: 1, is_primary: true, validation_status: "valid" }] : []),
              ]
          ).map((contact) => (
            <div key={`${contact.contact_type}-${contact.value}`}>
              <dt>{labelize(contact.contact_type)} {contact.rank}{contact.is_primary ? " · Primary" : ""}</dt>
              <dd>{contact.contact_type === "phone" ? <a href={`tel:${contact.value}`}>{contact.value}</a> : contact.value}</dd>
            </div>
          ))}
          <div><dt>Prior attempts</dt><dd>{entry.attempt_count}</dd></div>
          <div><dt>Last outcome</dt><dd>{entry.disposition ? labelize(entry.disposition) : "None"}</dd></div>
          <div><dt>Next commitment</dt><dd>{formatDateTime(entry.next_attempt_at)}</dd></div>
          <div><dt>Assigned caller</dt><dd>{entry.assigned_user_name}</dd></div>
        </dl>
        {returned ? <div className={styles.correction}><strong>Correction requested</strong><p>{returned.review_reason}</p></div> : null}
        <div className={styles.attemptHistory}>
          <span>Attempt history</span>
          {entry.attempts.filter((attempt) => attempt.status === "completed").map((attempt) => (
            <CompletedAttemptHistoryItem attempt={attempt} key={attempt.id} />
          ))}
          {!entry.attempts.some((attempt) => attempt.status === "completed") ? <p>No prior attempts.</p> : null}
        </div>
      </aside>

      <div className={styles.scriptPanel}>
        <div className={styles.scriptVersion}><span>Approved script</span><strong>v{activeScript.version_number} · {activeScript.title}</strong></div>
        <blockquote>{activeScript.opening_script}</blockquote>
        {!activeAttempt ? !entryAssignedToCurrentUser ? (
          <div className={styles.startAction}>
            <p>This record is assigned to {entry.assigned_user_name}. Manager monitoring is read-only.</p>
          </div>
        ) : !attemptAuthorityKnown ? (
          <div className={styles.startAction}>
            <p>Calling mode could not be confirmed. Refresh before starting this prospect.</p>
          </div>
        ) : nativeDialerEnabled ? (
          <div className={styles.startAction}>
            <p>
              {nativeDialerLeaseActive
                ? "The native dialer is confirming this reserved attempt. Call controls remain above."
                : "Use Start Calling above. The native dialer will lock the selected record and open its qualification form."}
            </p>
          </div>
        ) : manualAttemptAuthority ? (
          <div className={styles.startAction}><p>Start locks this record to you until an outcome is saved.</p><button className={styles.primaryButton} disabled={saving} onClick={onStart} type="button">Start prospect</button></div>
        ) : (
          <div className={styles.startAction}>
            <p>Calling is unavailable until Stonegate can confirm the approved calling mode.</p>
          </div>
        ) : (
          <LiveQualificationChecklist
            attemptId={activeAttempt.id}
            canAutosave={canAutosaveQualification}
            checklist={activeAttempt.qualification_checklist}
            key={activeAttempt.id}
            lease={dialerLease}
            onBlockingChange={onQualificationBlockingChange}
            onChecklistChange={onQualificationChecklistChange}
          />
        )}
      </div>

      <aside className={styles.outcomePanel}>
        <div className={styles.sectionHeader}><div><span>Required wrap-up</span><h3>Seller outcome</h3></div></div>
        {activeAttempt ? canMutateAttempt ? (
          technicalFailure ? (
            <div className={`${styles.technicalOutcomeBoundary} ${styles.technicalOutcomeActive}`}>
              <AlertTriangle aria-hidden="true" size={20} />
              <div>
                <strong>Technical failure — not a seller disposition</strong>
                <p>
                  The provider could not complete this call. Do not mark the seller as uninterested,
                  wrong number, or do-not-call because of a carrier or browser failure.
                </p>
                {technicalFailureDetail ? <small>{technicalFailureDetail}</small> : null}
                <button
                  className={styles.secondaryButton}
                  disabled={saving || !dialerLease}
                  onClick={onTechnicalFailure}
                  type="button"
                >
                  Record technical failure and return to queue
                </button>
              </div>
            </div>
          ) : (
            <form key={activeAttempt.id} onSubmit={onComplete}>
              <div className={styles.wrapUpGate} data-ready={!nativeDialerAvailable || nativeWrapUpReady}>
                <ShieldAlert aria-hidden="true" size={17} />
                <div>
                  <strong>
                    {nativeDialerAvailable
                      ? nativeWrapUpReady
                        ? "Call ended — wrap-up required"
                        : "Seller call still active"
                      : "Outcome required before the next record"}
                  </strong>
                  <p>
                    {nativeDialerAvailable && !nativeWrapUpReady
                      ? "You can prepare the result now. Saving unlocks only after the server enters wrap-up."
                      : "The next call remains blocked until Stonegate validates and saves this result."}
                  </p>
                </div>
              </div>
              <fieldset
                className={styles.wrapUpFields}
                disabled={saving || wrapUpRetryPending}
              >
                <legend>Seller result details</legend>
                <div className={styles.outcomeChoices} role="group" aria-label="Seller disposition">
                  {PROSPECTING_OUTCOME_GROUPS.map((group) => (
                    <section key={group.key}>
                      <span>{group.label}</span>
                      {PROSPECTING_OUTCOME_OPTIONS.filter(
                        (option) => option.group === group.key,
                      ).map((option) => (
                        <button
                          aria-pressed={outcome === option.key}
                          className={outcome === option.key ? styles.selectedOutcome : undefined}
                          key={option.key}
                          onClick={() => onOutcomeChange(option.key)}
                          type="button"
                        >
                          <strong>{option.label}</strong>
                          <small>{option.description}</small>
                        </button>
                      ))}
                    </section>
                  ))}
                </div>
                <p className={styles.outcomeAutomation} role="status">
                  <CheckCircle2 aria-hidden="true" size={15} />
                  <span><strong>After save:</strong> {selectedOutcome.automation}</span>
                </p>
                {requiresCallback ? (
                  <div className={styles.callbackControl}>
                    <label>
                      <span>Callback date and time</span>
                      <input
                        min={minimumDateTime}
                        name="callback_at"
                        onChange={(event) => setCallbackValue(event.target.value)}
                        required
                        type="datetime-local"
                        value={callbackValue}
                      />
                    </label>
                    <div>
                      <button onClick={() => setQuickCallback(1)} type="button">In 1 hour</button>
                      <button onClick={() => setQuickCallback(24)} type="button">Tomorrow</button>
                      <button onClick={() => setQuickCallback(72)} type="button">In 3 days</button>
                    </div>
                  </div>
                ) : null}
                {isWarm ? (
                  <label>
                    <span>Acquisitions owner</span>
                    <select name="handoff_user_id" required>
                      <option value="">Select owner</option>
                      {acquisitionUsers.map((user) => (
                        <option key={user.id} value={user.id}>{user.display_name}</option>
                      ))}
                    </select>
                  </label>
                ) : null}
                {isAppointment ? (
                  <>
                    <label>
                      <span>Appointment date and time</span>
                      <input min={minimumDateTime} name="appointment_start_at" required type="datetime-local" />
                    </label>
                    <label>
                      <span>Meeting type</span>
                      <select
                        name="appointment_location_type"
                        onChange={(event) => setAppointmentLocationType(event.target.value)}
                        required
                        value={appointmentLocationType}
                      >
                        <option value="seller_property">Seller property</option>
                        <option value="phone">Phone</option>
                        <option value="video">Video</option>
                        <option value="office">Office</option>
                      </select>
                    </label>
                    <label>
                      <span>Meeting location</span>
                      <input
                        name="appointment_location"
                        placeholder={
                          appointmentLocationType === "seller_property" && entry.property_address
                            ? `Uses saved property: ${entry.property_address}`
                            : "Phone number, video link, office, or property address"
                        }
                        required={
                          appointmentLocationType !== "seller_property" ||
                          !entry.property_address
                        }
                      />
                    </label>
                  </>
                ) : null}
                <label>
                  <span>Call notes</span>
                  <textarea name="notes" placeholder="Objections, commitments, and next action" />
                </label>
                <div className={styles.complianceChecks} role="group" aria-label="Escalate immediately">
                  <strong>Escalate immediately</strong>
                  <label><input name="compliance_flags" type="checkbox" value="seller_complaint" /><span>Seller complaint</span></label>
                  <label><input name="compliance_flags" type="checkbox" value="identity_unclear" /><span>Caller identity unclear</span></label>
                  <label><input name="compliance_flags" type="checkbox" value="policy_uncertainty" /><span>Policy uncertainty</span></label>
                  <label><input name="compliance_flags" type="checkbox" value="recording_disclosure_issue" /><span>Recording disclosure issue</span></label>
                </div>
              </fieldset>
              {isWarm && missingWarmHandoffLabels.length ? (
                <p className={styles.outcomeRequirement} role="status">
                  Complete before warm handoff: {missingWarmHandoffLabels.join(", ")}.
                </p>
              ) : null}
              {wrapUpRetryPending ? (
                <p className={styles.safeRetryNotice} role="status">
                  The first response was uncertain. Retry sends the exact same protected wrap-up;
                  fields stay locked so a lost response cannot create a different result.
                </p>
              ) : null}
              <button
                className={styles.primaryButton}
                disabled={
                  saving ||
                  (isWarm && missingWarmHandoffLabels.length > 0) ||
                  (nativeDialerAvailable && !nativeWrapUpReady)
                }
                type="submit"
              >
                {wrapUpRetryPending ? "Retry safe wrap-up" : "Save outcome and unlock next call"}
              </button>
            </form>
          )
        ) : (
          <div className={styles.monitoringOnly}>
            <strong>Read-only manager view</strong>
            <p>{entry.assigned_user_name} owns this active call and its final disposition.</p>
          </div>
        ) : <p className={styles.empty}>Start the prospect to unlock the guided outcome form.</p>}
      </aside>
    </section>
  );
}
