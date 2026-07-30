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
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import type {
  ProspectHandoff,
  ProspectingCallQuality,
  ProspectingCallQualityOutput,
  ProspectingCopilotOutput,
  ProspectingCopilotRecommendation,
  ProspectingEntry,
  ProspectingWorkbenchOverview,
} from "../../lib/api";
import { CopilotLauncher } from "../_components/copilot-launcher";
import { labelize } from "../os-utils";
import styles from "./prospecting.module.css";

type View = "workbench" | "quality" | "handoffs" | "performance" | "scripts";
type RequestStatus = "idle" | "saving" | "saved" | "error";
type QueueFilter = "due" | "callbacks" | "corrections" | "scheduled" | "waiting" | "all";

const outcomes = [
  ["no_answer", "No answer"],
  ["left_voicemail", "Left voicemail"],
  ["callback_requested", "Callback requested"],
  ["follow_up", "Follow up later"],
  ["interested", "Interested seller"],
  ["appointment_set", "Appointment set"],
  ["not_interested", "Not interested"],
  ["wrong_number", "Wrong number"],
  ["do_not_call", "Do not call"],
] as const;

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

export function ProspectingWorkspace({ data }: { data: ProspectingWorkbenchOverview }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [view, setView] = useState<View>("workbench");
  const [status, setStatus] = useState<RequestStatus>("idle");
  const [message, setMessage] = useState("");
  const [outcome, setOutcome] = useState("no_answer");
  const [entry, setEntry] = useState<ProspectingEntry | null>(data.current_entry);
  const [selectedCopilotEntryId, setSelectedCopilotEntryId] = useState(
    data.current_entry?.id ?? data.copilot.work_items[0]?.entry_id ?? "",
  );
  const [localRecommendation, setLocalRecommendation] =
    useState<ProspectingCopilotRecommendation | null>(null);
  const [editingBrief, setEditingBrief] = useState(false);
  const [editedSummary, setEditedSummary] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("due");
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
  const activeAttempt = entry?.active_attempt ?? null;
  const requiresCallback = ["callback_requested", "follow_up"].includes(outcome);
  const isWarm = ["interested", "appointment_set"].includes(outcome);
  const isAppointment = outcome === "appointment_set";
  const capturesQualification = [
    "callback_requested",
    "follow_up",
    "interested",
    "appointment_set",
  ].includes(outcome);
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

  async function startCurrent() {
    if (!entry) return;
    const result = await request<ProspectingEntry>(
      `/api/v1/prospecting/entries/${entry.id}/start`,
      "POST",
    );
    if (result) setEntry(result);
  }

  async function completeCurrent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeAttempt || !data.active_script) return;
    const form = event.currentTarget;
    const formData = new FormData(form);
    const answers = Object.fromEntries(
      data.active_script.qualification_questions
        .map((question) => [question.key, value(formData, question.key)])
        .filter(([, answer]) => Boolean(answer)),
    );
    const result = await request<ProspectingEntry>(
      `/api/v1/prospecting/attempts/${activeAttempt.id}/complete`,
      "POST",
      {
        outcome,
        qualification_answers: answers,
        notes: value(formData, "notes") || null,
        callback_at: requiresCallback
          ? localDateTimeToIso(value(formData, "callback_at"))
          : null,
        handoff_user_id: isWarm ? value(formData, "handoff_user_id") || null : null,
        appointment_start_at: isAppointment
          ? localDateTimeToIso(value(formData, "appointment_start_at"))
          : null,
        appointment_location_type: isAppointment
          ? value(formData, "appointment_location_type") || null
          : null,
        appointment_location: isAppointment
          ? value(formData, "appointment_location") || null
          : null,
        compliance_flags: formData
          .getAll("compliance_flags")
          .map((flag) => String(flag)),
      },
    );
    if (result) {
      setEntry(
        data.queue_entries.find(
          (item) => item.id !== result.id && item.is_actionable,
        ) ?? null,
      );
      form.reset();
      setOutcome("no_answer");
      router.refresh();
    }
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
        <div><span>Scheduled</span><strong>{data.queue.callbacks_scheduled}</strong></div>
        <div><span>Corrections</span><strong>{data.queue.corrections}</strong></div>
        <div><span>In progress</span><strong>{data.queue.in_progress}</strong></div>
        <div><span>Handoffs waiting</span><strong>{data.queue.handoff_pending}</strong></div>
      </section>

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
          <ShiftQueue
            activeAttemptId={activeAttempt?.id ?? null}
            batchQueues={data.batch_queues}
            entries={data.queue_entries}
            filter={queueFilter}
            onFilter={setQueueFilter}
            onSelect={(selected) => {
              setEntry(selected);
              setSelectedCopilotEntryId(selected.id);
              setLocalRecommendation(null);
            }}
            selectedEntryId={entry?.id ?? ""}
          />
          <WorkbenchView
            activeAttempt={activeAttempt}
            activeScript={data.active_script}
            acquisitionUsers={data.acquisition_users}
            capturesQualification={capturesQualification}
            entry={entry}
            isAppointment={isAppointment}
            isWarm={isWarm}
            onComplete={completeCurrent}
            onOutcomeChange={setOutcome}
            onStart={startCurrent}
            outcome={outcome}
            requiresCallback={requiresCallback}
            returnedHandoffs={data.returned_handoffs}
            saving={status === "saving"}
            key={entry?.id ?? "empty-queue"}
          />
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
                  <div><strong>v{script.version_number} · {script.title}</strong><span>{labelize(script.status)} · {script.created_by_name}</span></div>
                  {script.status === "draft" ? <button onClick={() => approveScript(script.id)} type="button">Approve</button> : <span>{script.approved_at ? formatDateTime(script.approved_at) : "Not approved"}</span>}
                </article>
              ))}
            </div>
          </div>
          <form className={styles.scriptForm} onSubmit={createScript}>
            <div className={styles.sectionHeader}><div><span>New immutable version</span><h3>Draft caller script</h3></div></div>
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
                    <label><span>Suggested disposition</span><select value={correction.suggested_disposition} onChange={(event) => updateCorrection("suggested_disposition", event.target.value as ProspectingCallQualityOutput["suggested_disposition"])}>{outcomes.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
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
  onFilter,
  onSelect,
  selectedEntryId,
}: {
  activeAttemptId: string | null;
  batchQueues: ProspectingWorkbenchOverview["batch_queues"];
  entries: ProspectingEntry[];
  filter: QueueFilter;
  onFilter: (filter: QueueFilter) => void;
  onSelect: (entry: ProspectingEntry) => void;
  selectedEntryId: string;
}) {
  const visibleEntries = entries.filter((item) => {
    if (filter === "due") return item.is_actionable;
    if (filter === "callbacks") return item.queue_kind === "callback_due";
    if (filter === "corrections") return item.queue_kind === "correction_required";
    if (filter === "scheduled") return item.queue_kind === "callback_scheduled";
    if (filter === "waiting") return item.queue_kind === "handoff_pending";
    return true;
  });
  const filters: Array<{ key: QueueFilter; label: string }> = [
    { key: "due", label: "Due now" },
    { key: "callbacks", label: "Callbacks" },
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
              {batch.callbacks_due} callbacks · {batch.corrections} corrections ·{" "}
              {batch.ready} ready
            </small>
            <em className={batch.provider_sync_status === "stonegate_direct" ? styles.syncReady : styles.syncPending}>
              {batch.provider_sync_status === "stonegate_direct"
                ? "Stonegate direct"
                : "Provider not connected"}
            </em>
          </div>
        ))}
      </div>
      <div className={styles.queueRows}>
        {visibleEntries.map((item) => {
          const blockedByActiveAttempt = Boolean(
            activeAttemptId && item.id !== selectedEntryId,
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
                {item.queue_kind === "correction_required" ? <AlertTriangle size={15} /> : null}
                {item.queue_kind === "in_progress" ? <PhoneCall size={15} /> : null}
                {item.queue_kind === "ready" ? <UserRoundCheck size={15} /> : null}
                {item.queue_kind === "callback_scheduled" ? <Clock3 size={15} /> : null}
                {labelize(item.queue_kind)}
              </span>
              <strong>{item.legal_name}</strong>
              <small>{item.property_address ?? item.phone ?? "No property details"}</small>
              <span>{item.campaign_name} · {item.assigned_user_name}</span>
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

function WorkbenchView({
  activeAttempt,
  activeScript,
  acquisitionUsers,
  capturesQualification,
  entry,
  isAppointment,
  isWarm,
  onComplete,
  onOutcomeChange,
  onStart,
  outcome,
  requiresCallback,
  returnedHandoffs,
  saving,
}: {
  activeAttempt: ProspectingEntry["active_attempt"];
  activeScript: ProspectingWorkbenchOverview["active_script"];
  acquisitionUsers: ProspectingWorkbenchOverview["acquisition_users"];
  capturesQualification: boolean;
  entry: ProspectingEntry | null;
  isAppointment: boolean;
  isWarm: boolean;
  onComplete: (event: FormEvent<HTMLFormElement>) => void;
  onOutcomeChange: (outcome: string) => void;
  onStart: () => void;
  outcome: string;
  requiresCallback: boolean;
  returnedHandoffs: ProspectHandoff[];
  saving: boolean;
}) {
  const [callbackValue, setCallbackValue] = useState("");
  function setQuickCallback(hoursFromNow: number) {
    const target = new Date(Date.now() + hoursFromNow * 60 * 60 * 1000);
    const localTarget = new Date(target.getTime() - target.getTimezoneOffset() * 60 * 1000);
    setCallbackValue(localTarget.toISOString().slice(0, 16));
  }
  if (!activeScript) {
    return <section className={styles.emptyState}><span>Queue paused</span><h3>An approved caller script is required</h3><p>An acquisition manager must approve a script version before assigned prospects can be worked.</p></section>;
  }
  if (!entry) {
    return <section className={styles.emptyState}><span>Queue clear</span><h3>No assigned prospect is due</h3><p>Future callbacks remain scheduled and will return here when due.</p></section>;
  }
  const returned = returnedHandoffs.find((handoff) => handoff.prospect_id === entry.prospect_id);
  const priorAnswers =
    entry.attempts.find((attempt) => attempt.status === "completed")
      ?.qualification_answers ?? {};
  return (
    <section className={styles.workbenchGrid}>
      <aside className={styles.prospectPanel}>
        <div className={styles.queuePosition}><span>{entry.batch_name}</span><strong>{labelize(entry.queue_kind)}</strong></div>
        <div className={styles.sellerIdentity}><span>{entry.campaign_name}</span><h3>{entry.legal_name}</h3><p>{entry.property_address ?? "Property address unavailable"}</p></div>
        <div className={styles.providerState}>
          <span>{labelize(entry.dialer_mode)}</span>
          <strong className={entry.provider_sync_status === "stonegate_direct" ? styles.syncReady : styles.syncPending}>
            {entry.provider_sync_status === "stonegate_direct"
              ? "Stonegate direct"
              : "Provider not connected"}
          </strong>
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
            <details key={attempt.id}>
              <summary><strong>{attempt.outcome ? labelize(attempt.outcome) : "Attempt"}</strong><span>{formatDateTime(attempt.completed_at)}</span></summary>
              {attempt.callback_at ? <p>Callback: {formatDateTime(attempt.callback_at)}</p> : null}
              {attempt.notes ? <p>{attempt.notes}</p> : null}
              {Object.entries(attempt.qualification_answers).length ? (
                <dl>
                  {Object.entries(attempt.qualification_answers).map(([key, answer]) => (
                    <div key={key}><dt>{labelize(key)}</dt><dd>{answer}</dd></div>
                  ))}
                </dl>
              ) : null}
            </details>
          ))}
          {!entry.attempts.some((attempt) => attempt.status === "completed") ? <p>No prior attempts.</p> : null}
        </div>
      </aside>

      <div className={styles.scriptPanel}>
        <div className={styles.scriptVersion}><span>Approved script</span><strong>v{activeScript.version_number} · {activeScript.title}</strong></div>
        <blockquote>{activeScript.opening_script}</blockquote>
        {!activeAttempt ? (
          <div className={styles.startAction}><p>Start locks this record to you until an outcome is saved.</p><button className={styles.primaryButton} disabled={saving} onClick={onStart} type="button">Start prospect</button></div>
        ) : (
          <div className={styles.questionGuide}>
            {activeScript.qualification_questions.map((question, index) => (
              <div key={question.key}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{question.label}{question.required_for_handoff ? " *" : ""}</strong><p>{question.prompt}</p></div></div>
            ))}
          </div>
        )}
      </div>

      <aside className={styles.outcomePanel}>
        <div className={styles.sectionHeader}><div><span>Required record</span><h3>Call outcome</h3></div></div>
        {activeAttempt ? (
          <form onSubmit={onComplete}>
            <fieldset className={styles.outcomeChoices}>
              <legend>Disposition</legend>
              {outcomes.map(([key, label]) => (
                <button
                  aria-pressed={outcome === key}
                  className={outcome === key ? styles.selectedOutcome : undefined}
                  key={key}
                  onClick={() => onOutcomeChange(key)}
                  type="button"
                >
                  {label}
                </button>
              ))}
            </fieldset>
            {capturesQualification ? activeScript.qualification_questions.map((question) => (
              <label key={question.key}><span>{question.label}{question.required_for_handoff && isWarm ? " *" : ""}</span>{question.answer_type === "choice" ? <select name={question.key} defaultValue={priorAnswers[question.key] ?? ""}><option value="">Select</option>{question.choices.map((choice) => <option key={choice}>{choice}</option>)}</select> : <input defaultValue={priorAnswers[question.key] ?? ""} name={question.key} />}</label>
            )) : null}
            {requiresCallback ? <div className={styles.callbackControl}><label><span>Callback date and time</span><input name="callback_at" onChange={(event) => setCallbackValue(event.target.value)} required type="datetime-local" value={callbackValue} /></label><div><button onClick={() => setQuickCallback(1)} type="button">In 1 hour</button><button onClick={() => setQuickCallback(24)} type="button">Tomorrow</button><button onClick={() => setQuickCallback(72)} type="button">In 3 days</button></div></div> : null}
            {isWarm ? <label><span>Acquisitions owner</span><select name="handoff_user_id" required><option value="">Select owner</option>{acquisitionUsers.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select></label> : null}
            {isAppointment ? <><label><span>Appointment date and time</span><input name="appointment_start_at" required type="datetime-local" /></label><label><span>Meeting type</span><select defaultValue="seller_property" name="appointment_location_type"><option value="seller_property">Seller property</option><option value="phone">Phone</option><option value="video">Video</option><option value="office">Office</option></select></label><label><span>Meeting location</span><input name="appointment_location" placeholder="Defaults to the property" /></label></> : null}
            <label><span>Call notes</span><textarea name="notes" placeholder="Objections, commitments, and next action" /></label>
            <fieldset className={styles.complianceChecks}>
              <legend>Escalate immediately</legend>
              <label><input name="compliance_flags" type="checkbox" value="seller_complaint" /><span>Seller complaint</span></label>
              <label><input name="compliance_flags" type="checkbox" value="identity_unclear" /><span>Caller identity unclear</span></label>
              <label><input name="compliance_flags" type="checkbox" value="policy_uncertainty" /><span>Policy uncertainty</span></label>
              <label><input name="compliance_flags" type="checkbox" value="recording_disclosure_issue" /><span>Recording disclosure issue</span></label>
            </fieldset>
            <button className={styles.primaryButton} disabled={saving} type="submit">Save outcome</button>
          </form>
        ) : <p className={styles.empty}>Start the prospect to unlock the guided outcome form.</p>}
      </aside>
    </section>
  );
}
