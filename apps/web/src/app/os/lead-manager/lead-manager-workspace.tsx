"use client";

import { useAuth } from "@clerk/nextjs";
import {
  Brain,
  Check,
  CheckCircle2,
  Clock3,
  ExternalLink,
  MessageSquareText,
  Pencil,
  ShieldAlert,
  Sparkles,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import type {
  LeadManagerCase,
  LeadManagerCopilotOutput,
  LeadManagerCopilotRecommendation,
  LeadManagerOverview,
} from "../../lib/api";
import { landStandardQuestions } from "../land-qualification-questions";
import { CopilotLauncher } from "../_components/copilot-launcher";
import { labelize } from "../os-utils";
import { AcquisitionsPerformanceScorecard } from "./acquisitions-performance-scorecard";
import styles from "./lead-manager.module.css";

type View = "today" | "qualification" | "performance" | "standards";
type QualificationNextAction = "call" | "sms" | "email" | "appointment" | "nurture" | "disqualify";

const houseStandardQuestions = [
  ["ownership", "Ownership", "Please confirm who owns the property and how title is held.", true],
  ["decision_makers", "Decision makers", "Who must agree before the property can be sold?", true],
  ["motivation", "Reason for selling", "What has you considering a sale now?", true],
  ["timeline", "Timeline", "When would you ideally like to have this completed?", true],
  ["property_condition", "Property condition", "What repairs or updates does the property need?", true],
  ["occupancy", "Occupancy", "Who currently occupies the property?", true],
  ["asking_price", "Price expectation", "Do you have a price in mind?", false],
  ["mortgage_balance", "Mortgage or liens", "Is there a mortgage, lien, or other balance?", false],
  ["access", "Property access", "How and when can the property be viewed?", true],
] as const;

function formatDateTime(value: string | null) {
  if (!value) return "Not scheduled";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function percent(basisPoints: number) {
  return `${(basisPoints / 100).toFixed(0)}%`;
}

function CaseRow({
  action,
  highlighted = false,
  item,
}: {
  action?: React.ReactNode;
  highlighted?: boolean;
  item: LeadManagerCase;
}) {
  return (
    <article className={`${styles.caseRow} ${highlighted ? styles.highlightedCase : ""}`}>
      <div className={styles.caseIdentity}>
        <strong>{item.seller_name}</strong>
        <span>{item.property_address}</span>
      </div>
      <div className={styles.caseMeta}>
        <span>{labelize(item.asset_class)}</span>
        <span>{labelize(item.source)}</span>
        <span>{item.assigned_user_name}</span>
        <span className={item.is_acceptance_overdue || item.is_next_action_overdue ? styles.late : ""}>
          {item.accepted_at
            ? item.next_action_due_at
              ? `Next ${formatDateTime(item.next_action_due_at)}`
              : `${item.age_hours}h old`
            : `Accept by ${formatDateTime(item.acceptance_due_at)}`}
        </span>
      </div>
      <div className={styles.rowActions}>
        {action}
        <Link aria-label={`Open ${item.seller_name}`} href={item.lead_url} title="Open lead">
          <ExternalLink size={16} />
        </Link>
      </div>
    </article>
  );
}

export function LeadManagerWorkspace({
  data,
  initialLeadId = "",
}: {
  data: LeadManagerOverview;
  initialLeadId?: string;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const initialQualificationCase = data.qualification_queue.find(
    (item) => item.lead_id === initialLeadId,
  );
  const initialCopilotItem = data.copilot.work_items.find((item) => item.lead_id === initialLeadId);
  const [view, setView] = useState<View>(
    initialQualificationCase ? "qualification" : "today",
  );
  const [selectedCaseId, setSelectedCaseId] = useState(
    initialQualificationCase?.id ?? data.qualification_queue[0]?.id ?? "",
  );
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [standardAssetClass, setStandardAssetClass] = useState<"house" | "land">("house");
  const [qualificationNextAction, setQualificationNextAction] =
    useState<QualificationNextAction>("call");
  const [disqualificationReason, setDisqualificationReason] = useState("");
  const [selectedCopilotCaseId, setSelectedCopilotCaseId] = useState(
    initialCopilotItem?.case_id ?? data.copilot.work_items[0]?.case_id ?? "",
  );
  const [localRecommendation, setLocalRecommendation] =
    useState<LeadManagerCopilotRecommendation | null>(null);
  const [editingRecommendation, setEditingRecommendation] = useState(false);
  const [editedSummary, setEditedSummary] = useState("");
  const [editedMessageBody, setEditedMessageBody] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");
  const activeView: View =
    !data.can_manage && (view === "performance" || view === "standards") ? "today" : view;
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );
  const selectedCase = data.qualification_queue.find((item) => item.id === selectedCaseId) ?? null;
  const activeScript = selectedCase
    ? data.active_scripts[selectedCase.asset_class] ?? null
    : null;
  const selectedCopilotItem =
    data.copilot.work_items.find((item) => item.case_id === selectedCopilotCaseId) ?? null;
  const recommendation =
    localRecommendation?.case_id === selectedCopilotCaseId
      ? localRecommendation
      : data.copilot.recommendations.find(
          (item) => item.case_id === selectedCopilotCaseId,
        ) ?? null;
  const copilotOutput = recommendation?.output_payload ?? null;

  async function request<T = unknown>(path: string, body?: object): Promise<T | null> {
    setSaving(true);
    setMessage("");
    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;
      const response = await fetch(`${apiBaseUrl}${path}`, {
        method: "POST",
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "The operation could not be completed.");
      }
      setMessage("Saved.");
      router.refresh();
      return (await response.json()) as T;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The operation could not be completed.");
      return null;
    } finally {
      setSaving(false);
    }
  }

  async function acceptCase(caseId: string) {
    await request(`/api/v1/lead-manager/cases/${caseId}/accept`, {});
  }

  async function analyzeCopilotCase(caseId: string) {
    const result = await request<{
      message: string;
      recommendation: LeadManagerCopilotRecommendation | null;
    }>(`/api/v1/lead-manager/cases/${caseId}/copilot/analyze`, {});
    if (result?.recommendation) {
      setLocalRecommendation(result.recommendation);
      setEditedSummary(result.recommendation.output_payload.summary);
      setEditedMessageBody(result.recommendation.output_payload.message_draft.body);
    } else if (result) {
      setMessage(result.message);
    }
  }

  async function reviewCopilotRecommendation(
    decision: "accepted" | "edited" | "rejected",
  ) {
    if (!recommendation || !copilotOutput) return;
    const finalOutput: LeadManagerCopilotOutput | undefined =
      decision === "edited"
        ? {
            ...copilotOutput,
            summary: editedSummary.trim(),
            message_draft: {
              ...copilotOutput.message_draft,
              body: editedMessageBody.trim(),
            },
          }
        : undefined;
    const result = await request(
      `/api/v1/lead-manager/copilot/recommendations/${recommendation.id}/review`,
      {
        decision,
        final_output: finalOutput,
        notes: reviewNotes.trim() || null,
        estimated_time_saved_seconds: 180,
      },
    );
    if (result) {
      setLocalRecommendation({
        ...recommendation,
        status: decision,
        output_payload: finalOutput ?? copilotOutput,
        reviewed_at: new Date().toISOString(),
      });
      setEditingRecommendation(false);
    }
  }

  async function submitQualification(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCase || !activeScript) return;
    const form = event.currentTarget;
    const formData = new FormData(form);
    const answers = Object.fromEntries(
      activeScript.questions
        .map((question) => [question.key, String(formData.get(question.key) ?? "").trim()])
        .filter(([, answer]) => Boolean(answer)),
    );
    const nextActionType = String(
      formData.get("next_action_type") ?? qualificationNextAction,
    ) as QualificationNextAction;
    const nextActionDue = String(formData.get("next_action_due_at") ?? "");
    const normalizedDisqualificationReason = String(
      formData.get("disqualification_reason") ?? "",
    ).trim();
    if (nextActionType === "disqualify" && normalizedDisqualificationReason.length < 10) {
      setMessage("Explain why this lead should be disqualified in at least 10 characters.");
      return;
    }
    if (nextActionType !== "disqualify" && !nextActionDue) {
      setMessage("Choose a due date and time for the active lead's next action.");
      return;
    }
    const parsedNextActionDue = nextActionDue ? new Date(nextActionDue) : null;
    if (parsedNextActionDue && Number.isNaN(parsedNextActionDue.getTime())) {
      setMessage("Choose a valid due date and time for the next action.");
      return;
    }
    const saved = await request(
      `/api/v1/lead-manager/cases/${selectedCase.id}/qualification`,
      {
        answers,
        next_action_type: nextActionType,
        next_action_due_at: parsedNextActionDue?.toISOString() ?? null,
        disqualification_reason:
          nextActionType === "disqualify" ? normalizedDisqualificationReason : null,
      },
    );
    if (saved) {
      form.reset();
      setQualificationNextAction("call");
      setDisqualificationReason("");
    }
  }

  function selectQualificationCase(caseId: string) {
    setSelectedCaseId(caseId);
    setQualificationNextAction("call");
    setDisqualificationReason("");
    setMessage("");
  }

  async function createScript(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const assetClass = String(formData.get("asset_class") ?? "house") as "house" | "land";
    const standardQuestions = assetClass === "land" ? landStandardQuestions : houseStandardQuestions;
    const saved = await request("/api/v1/lead-manager/scripts", {
      asset_class: assetClass,
      title: String(formData.get("title") ?? "").trim(),
      introduction: String(formData.get("introduction") ?? "").trim(),
      questions: standardQuestions.map(([key, label, prompt, required]) => ({
        key,
        label,
        prompt,
        answer_type: "text",
        choices: [],
        required,
      })),
    });
    if (saved) {
      form.reset();
      setStandardAssetClass("house");
    }
  }

  return (
    <div className={styles.workspace}>
      <section className={styles.metrics} aria-label="Acquisitions Desk queue summary">
        <div><span>Awaiting acceptance</span><strong>{data.metrics.awaiting_acceptance}</strong></div>
        <div className={data.metrics.overdue_acceptance ? styles.riskMetric : ""}><span>Overdue SLA</span><strong>{data.metrics.overdue_acceptance}</strong></div>
        <div><span>Qualification due</span><strong>{data.metrics.qualification_due}</strong></div>
        <div><span>Follow-ups due</span><strong>{data.metrics.follow_up_due}</strong></div>
        <div><span>Appointments today</span><strong>{data.metrics.appointments_today}</strong></div>
        <div className={data.metrics.neglected_leads ? styles.riskMetric : ""}><span>Neglected</span><strong>{data.metrics.neglected_leads}</strong></div>
      </section>

      <CopilotLauncher
        attentionCount={data.copilot.work_items.length}
        description="Prepares seller summaries, qualification questions, follow-up drafts, and appointment proposals without changing CRM records or contacting sellers."
        name="Lead Manager Copilot"
        summary={selectedCopilotItem?.recommended_action ?? "No active seller case needs AI preparation."}
        triggerLabel="Review AI assistance"
      >
        <div className={styles.copilotView}>
          <section className={styles.copilotGuard}>
            <div>
              <ShieldAlert size={18} />
              <span>
                <strong>Draft-only pilot</strong>
                Copilot can analyze and prepare work. It cannot send, schedule, edit CRM facts, or transfer ownership.
              </span>
            </div>
            <span className={styles.runtimeState}>
              Runtime {labelize(data.copilot.runtime_status)} · Lead tools {labelize(data.copilot.capability_status)}
            </span>
          </section>

          <section className={styles.copilotMetrics} aria-label="Copilot pilot metrics">
            <div><span>Drafts generated</span><strong>{data.copilot.metrics.generated_count}</strong></div>
            <div><span>Reviewed</span><strong>{data.copilot.metrics.reviewed_count}</strong></div>
            <div><span>Accepted or corrected</span><strong>{percent(data.copilot.metrics.acceptance_rate_basis_points)}</strong></div>
            <div><span>Correction rate</span><strong>{percent(data.copilot.metrics.correction_rate_basis_points)}</strong></div>
            <div><span>Estimated time saved</span><strong>{data.copilot.metrics.estimated_time_saved_minutes}m</strong></div>
          </section>

          <div className={styles.copilotWorkbench}>
            <aside className={styles.copilotQueue}>
              <div className={styles.sectionHeader}>
                <div><span>Deterministic ranking</span><h3>Needs attention</h3></div>
                <Brain size={19} />
              </div>
              {data.copilot.work_items.map((item) => (
                <button
                  className={selectedCopilotCaseId === item.case_id ? styles.selectedWorkItem : ""}
                  key={item.case_id}
                  onClick={() => {
                    setSelectedCopilotCaseId(item.case_id);
                    setLocalRecommendation(null);
                    setEditingRecommendation(false);
                    setReviewNotes("");
                  }}
                  type="button"
                >
                  <span className={`${styles.priorityBand} ${styles[item.priority_band]}`}>
                    {item.priority_score} · {labelize(item.priority_band)}
                  </span>
                  <strong>{item.seller_name}</strong>
                  <small>{item.property_address}</small>
                  <p>{item.recommended_action}</p>
                </button>
              ))}
              {!data.copilot.work_items.length ? (
                <p className={styles.empty}>No active Lead Queue work needs review.</p>
              ) : null}
            </aside>

            <section className={styles.copilotBrief}>
              {selectedCopilotItem ? (
                <>
                  <header className={styles.briefHeader}>
                    <div>
                      <span>Human-reviewed seller brief</span>
                      <h3>{selectedCopilotItem.seller_name}</h3>
                      <p>{selectedCopilotItem.property_address}</p>
                    </div>
                    <div className={styles.briefActions}>
                      <Link href={selectedCopilotItem.lead_url}>Open lead <ExternalLink size={14} /></Link>
                      <button
                        disabled={saving || recommendation?.status === "draft"}
                        onClick={() => analyzeCopilotCase(selectedCopilotItem.case_id)}
                        type="button"
                      >
                        <Sparkles size={15} />
                        {recommendation ? "Refresh brief" : "Generate brief"}
                      </button>
                    </div>
                  </header>

                  <div className={styles.deterministicEvidence}>
                    <div>
                      <span>Recommended now</span>
                      <strong>{selectedCopilotItem.recommended_action}</strong>
                    </div>
                    {selectedCopilotItem.alerts.map((alert) => (
                      <p key={alert}><ShieldAlert size={15} />{alert}</p>
                    ))}
                  </div>

                  {copilotOutput && recommendation ? (
                    <div className={styles.briefBody}>
                      <div className={styles.briefSummary}>
                        <div>
                          <span>Copilot summary</span>
                          {editingRecommendation ? (
                            <textarea
                              onChange={(event) => setEditedSummary(event.target.value)}
                              rows={5}
                              value={editedSummary}
                            />
                          ) : <p>{copilotOutput.summary}</p>}
                        </div>
                        <span className={styles.confidence}>{copilotOutput.confidence}% confidence</span>
                      </div>

                      <div className={styles.briefColumns}>
                        <section>
                          <span>Why this is next</span>
                          <p>{copilotOutput.priority_explanation}</p>
                        </section>
                        <section>
                          <span>Handoff brief</span>
                          <p>{copilotOutput.handoff_summary}</p>
                        </section>
                        <section>
                          <span>Qualification gaps</span>
                          {copilotOutput.qualification_gaps.length ? (
                            <ul>{copilotOutput.qualification_gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
                          ) : <p>No material gaps identified.</p>}
                        </section>
                        <section>
                          <span>Questions to ask</span>
                          {copilotOutput.recommended_questions.length ? (
                            <ul>{copilotOutput.recommended_questions.map((question) => <li key={question}>{question}</li>)}</ul>
                          ) : <p>No additional questions proposed.</p>}
                        </section>
                      </div>

                      <section className={styles.messageDraft}>
                        <div>
                          <MessageSquareText size={17} />
                          <span>{labelize(copilotOutput.message_draft.channel)} draft · Not sent</span>
                        </div>
                        {editingRecommendation ? (
                          <textarea
                            onChange={(event) => setEditedMessageBody(event.target.value)}
                            rows={4}
                            value={editedMessageBody}
                          />
                        ) : <p>{copilotOutput.message_draft.body || "No message proposed."}</p>}
                      </section>

                      <div className={styles.proposalGrid}>
                        <section>
                          <span>Task proposal</span>
                          <strong>{copilotOutput.next_task.title}</strong>
                          <p>{copilotOutput.next_task.reason}</p>
                          <small>{copilotOutput.next_task.due_timing}</small>
                        </section>
                        <section>
                          <span>Appointment proposal</span>
                          <strong>{copilotOutput.appointment_proposal.recommended ? "Recommended" : "Not yet"}</strong>
                          <p>{copilotOutput.appointment_proposal.reason}</p>
                        </section>
                      </div>

                      <details className={styles.supportingEvidence}>
                        <summary>Evidence and risks</summary>
                        <div>
                          <section><span>Evidence</span><ul>{copilotOutput.evidence.map((item) => <li key={item}>{item}</li>)}</ul></section>
                          <section><span>Risks</span>{copilotOutput.risks.length ? <ul>{copilotOutput.risks.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No material risks listed.</p>}</section>
                        </div>
                      </details>

                      {recommendation.status === "draft" ? (
                        <footer className={styles.reviewBar}>
                          {editingRecommendation ? (
                            <label>
                              <span>Correction note</span>
                              <input onChange={(event) => setReviewNotes(event.target.value)} placeholder="What did you correct?" value={reviewNotes} />
                            </label>
                          ) : null}
                          <div>
                            <button className={styles.rejectButton} disabled={saving} onClick={() => reviewCopilotRecommendation("rejected")} type="button"><XCircle size={15} />Reject</button>
                            <button className={styles.editButton} disabled={saving} onClick={() => {
                              setEditingRecommendation(true);
                              setEditedSummary(copilotOutput.summary);
                              setEditedMessageBody(copilotOutput.message_draft.body);
                            }} type="button"><Pencil size={15} />Correct</button>
                            <button disabled={saving} onClick={() => reviewCopilotRecommendation(editingRecommendation ? "edited" : "accepted")} type="button"><CheckCircle2 size={15} />{editingRecommendation ? "Save correction" : "Accept brief"}</button>
                          </div>
                        </footer>
                      ) : (
                        <p className={styles.reviewedState}><CheckCircle2 size={16} />Reviewed: {labelize(recommendation.status)}. No CRM action was applied.</p>
                      )}
                    </div>
                  ) : (
                    <div className={styles.emptyBrief}>
                      <Brain size={24} />
                      <strong>Generate a governed seller brief</strong>
                      <p>The deterministic queue is already active. Generation requires the AI runtime and Lead Manager capability to be enabled.</p>
                    </div>
                  )}
                </>
              ) : <p className={styles.empty}>Select an active seller case.</p>}
            </section>
          </div>
        </div>
      </CopilotLauncher>

      <nav className={styles.tabs} aria-label="Acquisitions Desk views">
        {([
          ["today", "Daily queue"],
          ["qualification", "Qualification"],
          ...(data.can_manage
            ? [
                ["performance", "Performance"],
                ["standards", "Standards"],
              ]
            : []),
        ] as Array<[View, string]>).map(([key, label]) => (
          <button className={activeView === key ? styles.activeTab : ""} key={key} onClick={() => setView(key)} type="button">{label}</button>
        ))}
      </nav>

      {message ? <p className={message === "Saved." ? styles.notice : styles.error}>{message}</p> : null}

      {activeView === "today" ? (
        <div className={styles.queueGrid}>
          <section className={styles.queueSection}>
            <div className={styles.sectionHeader}><div><span>First priority</span><h3>Accept warm handoffs</h3></div><Clock3 size={19} /></div>
            {data.awaiting_acceptance.length ? data.awaiting_acceptance.map((item) => (
              <CaseRow action={<button disabled={saving} onClick={() => acceptCase(item.id)} type="button"><Check size={15} />Accept</button>} highlighted={item.lead_id === initialLeadId} item={item} key={item.id} />
            )) : <p className={styles.empty}>No warm handoffs are waiting.</p>}
          </section>
          <section className={styles.queueSection}>
            <div className={styles.sectionHeader}><div><span>Due now</span><h3>Seller follow-up</h3></div><Clock3 size={19} /></div>
            {data.follow_up_queue.length ? data.follow_up_queue.map((item) => <CaseRow highlighted={item.lead_id === initialLeadId} item={item} key={item.id} />) : <p className={styles.empty}>No follow-ups are currently overdue.</p>}
          </section>
          <section className={styles.queueSection}>
            <div className={styles.sectionHeader}><div><span>Calendar</span><h3>Today&apos;s appointments</h3></div><Check size={19} /></div>
            {data.appointments_today.length ? data.appointments_today.map((item) => <CaseRow highlighted={item.lead_id === initialLeadId} item={item} key={item.id} />) : <p className={styles.empty}>No seller appointments today.</p>}
          </section>
          <section className={styles.queueSection}>
            <div className={styles.sectionHeader}><div><span>Exception queue</span><h3>Neglected leads</h3></div><ShieldAlert size={19} /></div>
            {data.neglected_queue.length ? data.neglected_queue.map((item) => <CaseRow highlighted={item.lead_id === initialLeadId} item={item} key={item.id} />) : <p className={styles.empty}>Every active seller has a protected next action.</p>}
          </section>
        </div>
      ) : null}

      {activeView === "qualification" ? (
        <div className={styles.qualificationLayout}>
          <aside className={styles.qualificationList}>
            <div className={styles.sectionHeader}><div><span>Assigned queue</span><h3>Needs qualification</h3></div></div>
            {data.qualification_queue.map((item) => (
              <button className={selectedCaseId === item.id ? styles.selectedCase : ""} key={item.id} onClick={() => selectQualificationCase(item.id)} type="button"><strong>{item.seller_name}</strong><span>{labelize(item.asset_class)} · {item.property_address}</span></button>
            ))}
            {!data.qualification_queue.length ? <p className={styles.empty}>Qualification queue is clear.</p> : null}
          </aside>
          <section className={styles.qualificationForm}>
            {selectedCase && activeScript ? (
              <form key={selectedCase.id} onSubmit={submitQualification}>
                <div className={styles.scriptHeader}><div><span>{labelize(selectedCase.asset_class)} · Script v{activeScript.version_number}</span><h3>{selectedCase.seller_name}</h3><p>{activeScript.introduction}</p></div><Link href={selectedCase.lead_url}>Open full lead</Link></div>
                <div className={styles.questionGrid}>
                  {activeScript.questions.map((question) => (
                    <label key={question.key}><span>{question.label}{question.required ? " *" : ""}</span><small>{question.prompt}</small><textarea name={question.key} required={question.required} rows={2} /></label>
                  ))}
                </div>
                <div className={styles.nextAction}>
                  <label>
                    <span>Next action</span>
                    <select
                      name="next_action_type"
                      onChange={(event) => {
                        const nextAction = event.target.value as QualificationNextAction;
                        setQualificationNextAction(nextAction);
                        if (nextAction !== "disqualify") setDisqualificationReason("");
                      }}
                      value={qualificationNextAction}
                    >
                      <option value="call">Call</option>
                      <option value="sms">Text</option>
                      <option value="email">Email</option>
                      <option value="appointment">Seller appointment</option>
                      <option value="nurture">Nurture follow-up</option>
                      <option value="disqualify">Disqualify and close</option>
                    </select>
                  </label>
                  {qualificationNextAction === "disqualify" ? (
                    <label>
                      <span>Disqualification reason *</span>
                      <small>This closes the lead and stops its tasks, reminders, appointments, and overdue follow-up warnings.</small>
                      <textarea
                        autoFocus
                        maxLength={500}
                        minLength={10}
                        name="disqualification_reason"
                        onChange={(event) => setDisqualificationReason(event.target.value)}
                        placeholder="Example: Spam submission with an invalid phone number."
                        required
                        rows={3}
                        value={disqualificationReason}
                      />
                    </label>
                  ) : (
                    <label>
                      <span>Due date and time *</span>
                      <input name="next_action_due_at" required type="datetime-local" />
                    </label>
                  )}
                  <button
                    className={qualificationNextAction === "disqualify" ? styles.disqualifyButton : undefined}
                    disabled={saving}
                    type="submit"
                  >
                    <Check size={16} />
                    {qualificationNextAction === "disqualify" ? "Close as disqualified" : "Complete qualification"}
                  </button>
                </div>
              </form>
            ) : <p className={styles.empty}>{selectedCase ? `A manager must approve a ${labelize(selectedCase.asset_class)} qualification standard before this lead can be worked.` : "Select a lead to begin."}</p>}
          </section>
        </div>
      ) : null}

      {activeView === "performance" && data.can_manage ? (
        <AcquisitionsPerformanceScorecard />
      ) : null}

      {activeView === "standards" && data.can_manage ? (
        <div className={styles.standardsGrid}>
          <section className={styles.standardForm}>
            <div className={styles.sectionHeader}><div><span>Controlled process</span><h3>Create qualification version</h3></div></div>
            <form onSubmit={createScript}>
              <label><span>Lead type</span><select name="asset_class" onChange={(event) => setStandardAssetClass(event.target.value as "house" | "land")} value={standardAssetClass}><option value="house">House</option><option value="land">Land</option></select></label>
              <label><span>Version name</span><input defaultValue="Stonegate Lead Qualification" name="title" required /></label>
              <label><span>Opening guidance</span><textarea defaultValue="Confirm the seller's situation carefully. Explain that these questions help Stonegate determine whether a direct sale is a reasonable fit." name="introduction" required rows={4} /></label>
              <div aria-live="polite" className={styles.standardQuestionPreview}>
                <strong>{standardAssetClass === "land" ? "Land seller checklist" : "House seller checklist"}</strong>
                <p>
                  This creates a draft with {standardAssetClass === "land" ? landStandardQuestions.length : houseStandardQuestions.length} questions. A manager must approve it before the team can use it.
                </p>
                <ol aria-label="Draft qualification questions" tabIndex={0}>
                  {(standardAssetClass === "land" ? landStandardQuestions : houseStandardQuestions).map(([, label, prompt]) => (
                    <li key={label}><span>{label}</span><small>{prompt}</small></li>
                  ))}
                </ol>
              </div>
              <button disabled={saving} type="submit">Create draft</button>
            </form>
          </section>
          <section className={styles.versionList}>
            <div className={styles.sectionHeader}><div><span>Version history</span><h3>Qualification standards</h3></div></div>
            {data.scripts.map((script) => <div className={styles.versionRow} key={script.id}><div><strong>{labelize(script.asset_class)} · v{script.version_number} · {script.title}</strong><span>{labelize(script.status)} · {script.questions.length} questions</span></div>{script.status === "draft" ? <button disabled={saving} onClick={() => request(`/api/v1/lead-manager/scripts/${script.id}/approve`)} type="button">Approve</button> : <span className={styles.approved}>Approved</span>}</div>)}
          </section>
        </div>
      ) : null}
    </div>
  );
}
