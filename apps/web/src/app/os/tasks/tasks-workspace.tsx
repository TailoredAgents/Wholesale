"use client";

import { useAuth } from "@clerk/nextjs";
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  Bot,
  Check,
  CheckCheck,
  Clock3,
  ExternalLink,
  Search,
  Sparkles,
  UsersRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useRef, useState } from "react";

import type { TaskWorkspace, TaskWorkspaceItem } from "../../lib/api";
import { StatusBadge } from "../_components/design-system";
import { formatDateTime, labelize } from "../os-utils";
import styles from "./tasks.module.css";

export type TaskView =
  | "mine"
  | "today"
  | "overdue"
  | "upcoming"
  | "unscheduled"
  | "team"
  | "approvals"
  | "ai_completed"
  | "exceptions"
  | "completed";

type MutationStatus = "idle" | "saving" | "error";

const baseViews: Array<{ key: TaskView; label: string }> = [
  { key: "mine", label: "My Tasks" },
  { key: "today", label: "Do Today" },
  { key: "overdue", label: "Overdue" },
  { key: "upcoming", label: "Upcoming" },
  { key: "unscheduled", label: "Unscheduled" },
];

function dueTone(
  status: TaskWorkspaceItem["due_status"],
): "danger" | "warning" | "success" | "neutral" {
  if (status === "overdue") return "danger";
  if (status === "today") return "warning";
  if (status === "completed") return "success";
  return "neutral";
}

function kindLabel(item: TaskWorkspaceItem) {
  if (item.work_kind === "primary_next_action") return "Primary action";
  if (item.work_kind === "operational_exception") return "Exception";
  if (item.work_kind === "approval") return "Approval";
  if (item.work_kind === "ai_review") return "AI review";
  if (item.work_kind === "ai_completed") return "AI completed";
  if (item.work_kind === "ai_in_progress") return "AI working";
  return "Supporting task";
}

function kindTone(
  item: TaskWorkspaceItem,
): "info" | "warning" | "danger" | "neutral" {
  if (item.work_kind === "primary_next_action") return "info";
  if (item.work_kind === "approval") return "warning";
  if (item.work_kind === "ai_review") return "warning";
  if (item.work_kind === "ai_completed") return "info";
  if (item.work_kind === "ai_in_progress") return "info";
  if (item.work_kind === "operational_exception") return "danger";
  return "neutral";
}

function ownerLabel(item: TaskWorkspaceItem) {
  return item.assigned_user_name ?? item.assigned_user_email?.split("@")[0] ?? "Unassigned";
}

function defaultSuccessorDue() {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  date.setHours(10, 0, 0, 0);
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 16);
}

function matchesView(
  item: TaskWorkspaceItem,
  view: TaskView,
  currentUserId: string,
) {
  if (view === "ai_completed") return item.work_kind === "ai_completed";
  if (view === "completed") {
    return item.due_status === "completed" && item.work_kind !== "ai_completed";
  }
  if (item.due_status === "completed") return false;
  if (view === "mine") return item.assigned_user_id === currentUserId;
  if (view === "today") return item.due_status === "today";
  if (view === "overdue") return item.due_status === "overdue";
  if (view === "upcoming") return item.due_status === "upcoming";
  if (view === "unscheduled") return item.due_status === "unscheduled";
  if (view === "approvals") {
    return item.work_kind === "approval" || item.work_kind === "ai_review";
  }
  if (view === "exceptions") return item.attention_flags.length > 0;
  return true;
}

type AiRecommendation = {
  action: string;
  reason: string;
  confidence: number | null;
};

type AiNextTask = {
  title: string;
  reason: string;
  dueTiming: string;
};

function aiRecommendations(item: TaskWorkspaceItem): AiRecommendation[] {
  const raw = (item.ai_output ?? {}).recommended_actions;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((value) => {
    if (!value || typeof value !== "object") return [];
    const candidate = value as Record<string, unknown>;
    const action = typeof candidate.action === "string" ? candidate.action : "";
    if (!action) return [];
    return [{
      action,
      reason: typeof candidate.reason === "string" ? candidate.reason : "",
      confidence: typeof candidate.confidence === "number" ? candidate.confidence : null,
    }];
  });
}

function aiStringList(item: TaskWorkspaceItem, key: string) {
  const raw = (item.ai_output ?? {})[key];
  return Array.isArray(raw) ? raw.filter((value): value is string => typeof value === "string") : [];
}

function aiNextTask(item: TaskWorkspaceItem): AiNextTask | null {
  const raw = (item.ai_output ?? {}).next_task;
  if (!raw || typeof raw !== "object") return null;
  const candidate = raw as Record<string, unknown>;
  const title = typeof candidate.title === "string" ? candidate.title : "";
  if (!title) return null;
  return {
    title,
    reason: typeof candidate.reason === "string" ? candidate.reason : "",
    dueTiming: typeof candidate.due_timing === "string" ? candidate.due_timing : "",
  };
}

function aiConfidence(item: TaskWorkspaceItem) {
  const raw = (item.ai_output ?? {}).confidence;
  return typeof raw === "number" ? raw : null;
}

export function TasksWorkspace({
  initialItemId,
  initialView,
  initialWorkspace,
}: {
  initialItemId: string;
  initialView: TaskView;
  initialWorkspace: TaskWorkspace;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [workspace, setWorkspace] = useState(initialWorkspace);
  const [view, setView] = useState(initialView);
  const [query, setQuery] = useState("");
  const [owner, setOwner] = useState("all");
  const [selectedId, setSelectedId] = useState(initialItemId);
  const [status, setStatus] = useState<MutationStatus>("idle");
  const [error, setError] = useState("");
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  const devUserEmail =
    process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com";

  const views = useMemo(() => {
    const result = [...baseViews];
    if (workspace.can_manage_team) result.push({ key: "team", label: "Team" });
    if (workspace.can_decide_approvals) {
      result.push({ key: "approvals", label: "Needs Approval" });
    }
    result.push({ key: "ai_completed", label: "AI Completed" });
    result.push({ key: "exceptions", label: "Exceptions" });
    result.push({ key: "completed", label: "Completed" });
    return result;
  }, [workspace.can_decide_approvals, workspace.can_manage_team]);
  const owners = useMemo(
    () =>
      Array.from(
        new Map(
          workspace.items
            .filter((item) => item.assigned_user_id)
            .map((item) => [
              item.assigned_user_id!,
              {
                id: item.assigned_user_id!,
                label: ownerLabel(item),
              },
            ]),
        ).values(),
      ).sort((a, b) => a.label.localeCompare(b.label)),
    [workspace.items],
  );
  const counts = useMemo(
    () =>
      Object.fromEntries(
        views.map((savedView) => [
          savedView.key,
          workspace.items.filter((item) =>
            matchesView(item, savedView.key, workspace.current_user_id),
          ).length,
        ]),
      ) as Record<TaskView, number>,
    [views, workspace.current_user_id, workspace.items],
  );
  const visibleItems = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return workspace.items.filter((item) => {
      const matchesOwner =
        owner === "all" ||
        (owner === "unassigned" && item.assigned_user_id === null) ||
        item.assigned_user_id === owner;
      const matchesQuery =
        !normalizedQuery ||
        `${item.title} ${item.source_record_label} ${item.source_record_detail ?? ""} ${item.task_type}`
          .toLowerCase()
          .includes(normalizedQuery);
      return (
        matchesView(item, view, workspace.current_user_id) &&
        matchesOwner &&
        matchesQuery
      );
    });
  }, [owner, query, view, workspace.current_user_id, workspace.items]);
  const selected =
    workspace.items.find((item) => item.id === selectedId) ??
    visibleItems[0] ??
    null;
  const selectedAiNextTask = selected ? aiNextTask(selected) : null;
  const selectedAiConfidence = selected ? aiConfidence(selected) : null;
  const openItems = workspace.items.filter((item) => item.due_status !== "completed");
  const metrics = {
    primary: openItems.filter((item) => item.work_kind === "primary_next_action").length,
    overdue: openItems.filter((item) => item.due_status === "overdue").length,
    approvals: openItems.filter(
      (item) => item.work_kind === "approval" || item.work_kind === "ai_review",
    ).length,
    aiCompleted: workspace.items.filter((item) => item.work_kind === "ai_completed").length,
  };

  async function headers() {
    const token = await getToken().catch(() => null);
    return {
      "Content-Type": "application/json",
      ...(token
        ? { Authorization: `Bearer ${token}` }
        : { "X-Dev-User-Email": devUserEmail }),
    };
  }

  async function refreshWorkspace() {
    const response = await fetch(`${apiBaseUrl}/api/v1/tasks/workspace`, {
      headers: await headers(),
      cache: "no-store",
    });
    if (!response.ok) throw new Error("The Tasks workspace could not be refreshed.");
    setWorkspace((await response.json()) as TaskWorkspace);
  }

  function selectView(nextView: TaskView) {
    setView(nextView);
    setSelectedId("");
    const params = new URLSearchParams();
    if (nextView !== "mine") params.set("view", nextView);
    router.replace(params.size ? `/os/tasks?${params}` : "/os/tasks", { scroll: false });
  }

  function selectItem(item: TaskWorkspaceItem) {
    setSelectedId(item.id);
    const params = new URLSearchParams();
    if (view !== "mine") params.set("view", view);
    params.set("item", item.id);
    router.replace(`/os/tasks?${params}`, { scroll: false });
  }

  async function completeSupporting(item: TaskWorkspaceItem) {
    if (!item.task_id || status === "saving") return;
    setStatus("saving");
    setError("");
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/tasks/${item.task_id}/complete`,
        {
          method: "PATCH",
          headers: await headers(),
          body: JSON.stringify({
            outcome: "completed",
            completion_notes: "Completed from Stonegate Tasks.",
          }),
        },
      );
      if (!response.ok) throw new Error(await responseMessage(response));
      await refreshWorkspace();
      setStatus("idle");
    } catch (reason) {
      setStatus("error");
      setError(reason instanceof Error ? reason.message : "The task could not be completed.");
    }
  }

  async function completePrimary(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected?.task_id || status === "saving") return;
    const data = new FormData(event.currentTarget);
    const terminal = data.get("terminal") === "on";
    const successorDue = String(data.get("successor_due_at") ?? "");
    setStatus("saving");
    setError("");
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/tasks/${selected.task_id}/complete`,
        {
          method: "PATCH",
          headers: await headers(),
          body: JSON.stringify({
            outcome: String(data.get("outcome") ?? ""),
            completion_notes: String(data.get("completion_notes") ?? "") || null,
            successor: terminal
              ? null
              : {
                  title: String(data.get("successor_title") ?? ""),
                  task_type: String(data.get("successor_type") ?? "follow_up"),
                  due_at: successorDue ? new Date(successorDue).toISOString() : null,
                  responsible_user_id: selected.assigned_user_id,
                  priority: String(data.get("successor_priority") ?? "normal"),
                },
          }),
        },
      );
      if (!response.ok) throw new Error(await responseMessage(response));
      await refreshWorkspace();
      dialogRef.current?.close();
      setStatus("idle");
      setSelectedId("");
    } catch (reason) {
      setStatus("error");
      setError(reason instanceof Error ? reason.message : "The action could not be completed.");
    }
  }

  async function decideApproval(decision: "approved" | "rejected") {
    if (!selected?.approval_id || status === "saving") return;
    const notes = window.prompt(
      decision === "approved"
        ? "Optional decision notes"
        : "Why is this request being rejected?",
      "",
    );
    if (notes === null) return;
    setStatus("saving");
    setError("");
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/approvals/${selected.approval_id}/decision`,
        {
          method: "PATCH",
          headers: await headers(),
          body: JSON.stringify({
            status: decision,
            decision_notes: notes || null,
          }),
        },
      );
      if (!response.ok) throw new Error(await responseMessage(response));
      await refreshWorkspace();
      setStatus("idle");
    } catch (reason) {
      setStatus("error");
      setError(reason instanceof Error ? reason.message : "The decision could not be recorded.");
    }
  }

  async function decideAiWork(decision: "accepted" | "rejected") {
    if (!selected?.ai_event_id || status === "saving") return;
    const notes = window.prompt(
      decision === "accepted"
        ? "Optional review notes"
        : "Why should this AI result be rejected?",
      "",
    );
    if (notes === null) return;
    setStatus("saving");
    setError("");
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/tasks/ai-work/${selected.ai_event_id}/review`,
        {
          method: "PATCH",
          headers: await headers(),
          body: JSON.stringify({ decision, notes: notes || null }),
        },
      );
      if (!response.ok) throw new Error(await responseMessage(response));
      await refreshWorkspace();
      setSelectedId("");
      setStatus("idle");
    } catch (reason) {
      setStatus("error");
      setError(reason instanceof Error ? reason.message : "The AI review could not be recorded.");
    }
  }

  return (
    <section className={styles.workspace}>
      <section className={styles.metrics} aria-label="Tasks summary">
        <div><CheckCheck size={17} /><span>Primary actions</span><strong>{metrics.primary}</strong></div>
        <div><Clock3 size={17} /><span>Overdue</span><strong>{metrics.overdue}</strong></div>
        <div><BadgeCheck size={17} /><span>Needs approval</span><strong>{metrics.approvals}</strong></div>
        <div><Sparkles size={17} /><span>AI completed</span><strong>{metrics.aiCompleted}</strong></div>
      </section>

      <nav className={styles.savedViews} aria-label="Task views">
        {views.map((savedView) => (
          <button
            aria-pressed={view === savedView.key}
            className={view === savedView.key ? styles.activeView : undefined}
            key={savedView.key}
            onClick={() => selectView(savedView.key)}
            type="button"
          >
            <span>{savedView.label}</span>
            <strong>{counts[savedView.key]}</strong>
          </button>
        ))}
      </nav>

      <div className={styles.toolbar}>
        <label className={styles.searchField}>
          <Search aria-hidden="true" size={16} />
          <input
            aria-label="Search tasks and approvals"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search work, seller, property, or deal"
            type="search"
            value={query}
          />
        </label>
        {workspace.can_manage_team ? (
          <label className={styles.ownerFilter}>
            <UsersRound aria-hidden="true" size={15} />
            <select
              aria-label="Filter by owner"
              onChange={(event) => setOwner(event.target.value)}
              value={owner}
            >
              <option value="all">All owners</option>
              <option value="unassigned">Unassigned</option>
              {owners.map((item) => (
                <option key={item.id} value={item.id}>{item.label}</option>
              ))}
            </select>
          </label>
        ) : null}
        <span className={styles.resultCount}>{visibleItems.length} shown</span>
      </div>

      {error ? <p className={styles.error} role="alert">{error}</p> : null}

      <div className={styles.workGrid}>
        <div className={styles.queue} aria-label={`${labelize(view)} work`}>
          {visibleItems.map((item) => (
            <button
              aria-pressed={selected?.id === item.id}
              className={selected?.id === item.id ? styles.selectedRow : styles.queueRow}
              key={item.id}
              onClick={() => selectItem(item)}
              type="button"
            >
              <div className={styles.rowHeading}>
                <StatusBadge tone={kindTone(item)}>{kindLabel(item)}</StatusBadge>
                <StatusBadge tone={dueTone(item.due_status)}>{labelize(item.due_status)}</StatusBadge>
              </div>
              <strong>{item.title}</strong>
              <span>{item.source_record_label}</span>
              <small>{item.source_record_detail ?? labelize(item.source_record_type)}</small>
              <dl>
                <div><dt>Owner</dt><dd>{ownerLabel(item)}</dd></div>
                <div><dt>Due</dt><dd>{formatDateTime(item.due_at)}</dd></div>
              </dl>
            </button>
          ))}
          {!visibleItems.length ? (
            <div className={styles.emptyState}>
              <CheckCheck aria-hidden="true" size={24} />
              <strong>No work matches this view</strong>
              <span>Change the view, owner, or search filters.</span>
            </div>
          ) : null}
        </div>

        <aside className={styles.detail} aria-label="Selected work detail">
          {selected ? (
            <>
              <header>
                <div>
                  <span>{kindLabel(selected)}</span>
                  <h2>{selected.title}</h2>
                  <p>{selected.summary ?? selected.source_record_detail}</p>
                </div>
                <StatusBadge tone={dueTone(selected.due_status)}>
                  {labelize(selected.status)}
                </StatusBadge>
              </header>
              <dl className={styles.facts}>
                <div><dt>Source record</dt><dd>{selected.source_record_label}</dd></div>
                <div><dt>Owner</dt><dd>{ownerLabel(selected)}</dd></div>
                <div><dt>Due</dt><dd>{formatDateTime(selected.due_at)}</dd></div>
                <div><dt>Work type</dt><dd>{labelize(selected.task_type)}</dd></div>
                {selected.outcome ? <div><dt>Outcome</dt><dd>{labelize(selected.outcome)}</dd></div> : null}
              </dl>
              {selected.attention_flags.length ? (
                <section className={styles.attention}>
                  <AlertTriangle aria-hidden="true" size={17} />
                  <div>
                    <strong>Needs attention</strong>
                    <span>{selected.attention_flags.map(labelize).join(" · ")}</span>
                  </div>
                </section>
              ) : null}
              {selected.item_type === "ai_work" && Object.keys(selected.ai_output ?? {}).length ? (
                <section className={styles.aiOutput}>
                  <header>
                    <Bot aria-hidden="true" size={18} />
                    <div>
                      <strong>Prepared by Stonegate AI</strong>
                      <span>{labelize(selected.capability_key ?? "AI assistance")}</span>
                    </div>
                    {selectedAiConfidence !== null ? (
                      <strong>{selectedAiConfidence}% confidence</strong>
                    ) : null}
                  </header>
                  {selectedAiNextTask ? (
                    <div className={styles.aiRecommendations}>
                      <strong>Recommended next step</strong>
                      <article>
                        <div>
                          <strong>{selectedAiNextTask.title}</strong>
                          {selectedAiNextTask.reason ? (
                            <p>{selectedAiNextTask.reason}</p>
                          ) : null}
                        </div>
                        {selectedAiNextTask.dueTiming ? (
                          <span>{labelize(selectedAiNextTask.dueTiming)}</span>
                        ) : null}
                      </article>
                    </div>
                  ) : null}
                  {aiRecommendations(selected).length ? (
                    <div className={styles.aiRecommendations}>
                      <strong>Recommended actions</strong>
                      {aiRecommendations(selected).map((recommendation, index) => (
                        <article key={`${recommendation.action}-${index}`}>
                          <div>
                            <strong>{recommendation.action}</strong>
                            {recommendation.reason ? <p>{recommendation.reason}</p> : null}
                          </div>
                          {recommendation.confidence !== null ? (
                            <span>{recommendation.confidence}%</span>
                          ) : null}
                        </article>
                      ))}
                    </div>
                  ) : null}
                  {aiStringList(selected, "risks").length ? (
                    <div className={styles.aiEvidence}>
                      <strong>Risks</strong>
                      <p>{aiStringList(selected, "risks").join(" · ")}</p>
                    </div>
                  ) : null}
                  {aiStringList(selected, "qualification_gaps").length ? (
                    <div className={styles.aiEvidence}>
                      <strong>Still need to confirm</strong>
                      <p>{aiStringList(selected, "qualification_gaps").join(" · ")}</p>
                    </div>
                  ) : null}
                  {aiStringList(selected, "recommended_questions").length ? (
                    <div className={styles.aiEvidence}>
                      <strong>Questions to ask</strong>
                      <p>{aiStringList(selected, "recommended_questions").join(" · ")}</p>
                    </div>
                  ) : null}
                  {aiStringList(selected, "uncertainties").length ? (
                    <div className={styles.aiEvidence}>
                      <strong>Still unknown</strong>
                      <p>{aiStringList(selected, "uncertainties").join(" · ")}</p>
                    </div>
                  ) : null}
                  {aiStringList(selected, "evidence").length ? (
                    <div className={styles.aiEvidence}>
                      <strong>Based on</strong>
                      <p>{aiStringList(selected, "evidence").map(labelize).join(" · ")}</p>
                    </div>
                  ) : null}
                </section>
              ) : null}
              <div className={styles.detailActions}>
                {selected.source_url ? (
                  <Link href={selected.source_url}>
                    Open source <ExternalLink aria-hidden="true" size={15} />
                  </Link>
                ) : null}
                {selected.item_type === "task" &&
                selected.can_complete &&
                selected.work_kind === "primary_next_action" ? (
                  <button
                    className={styles.primaryButton}
                    onClick={() => {
                      setError("");
                      dialogRef.current?.showModal();
                    }}
                    type="button"
                  >
                    <Check aria-hidden="true" size={15} />
                    Complete and continue
                  </button>
                ) : null}
                {selected.item_type === "task" &&
                selected.can_complete &&
                selected.work_kind !== "primary_next_action" ? (
                  <button
                    className={styles.primaryButton}
                    disabled={status === "saving"}
                    onClick={() => void completeSupporting(selected)}
                    type="button"
                  >
                    <Check aria-hidden="true" size={15} />
                    Mark complete
                  </button>
                ) : null}
                {selected.item_type === "approval" &&
                selected.can_decide &&
                !selected.review_url ? (
                  <>
                    <button
                      className={styles.primaryButton}
                      disabled={status === "saving"}
                      onClick={() => void decideApproval("approved")}
                      type="button"
                    >
                      Approve
                    </button>
                    <button
                      disabled={status === "saving"}
                      onClick={() => void decideApproval("rejected")}
                      type="button"
                    >
                      Reject
                    </button>
                  </>
                ) : null}
                {selected.item_type === "ai_work" && selected.can_decide ? (
                  <>
                    <button
                      className={styles.primaryButton}
                      disabled={status === "saving"}
                      onClick={() => void decideAiWork("accepted")}
                      type="button"
                    >
                      <Check aria-hidden="true" size={15} />
                      Accept brief
                    </button>
                    <button
                      disabled={status === "saving"}
                      onClick={() => void decideAiWork("rejected")}
                      type="button"
                    >
                      Reject
                    </button>
                  </>
                ) : null}
              </div>
              {selected.item_type === "approval" && selected.review_url ? (
                <p className={styles.reviewNote}>
                  Review and decide this request at its source so the underlying evidence remains visible.
                </p>
              ) : null}
            </>
          ) : (
            <div className={styles.detailEmpty}>
              <ArrowRight aria-hidden="true" size={22} />
              <strong>Select work to review</strong>
              <span>Its owner, deadline, source, and allowed action will appear here.</span>
            </div>
          )}
        </aside>
      </div>

      <dialog className={styles.completionDialog} ref={dialogRef}>
        <form onSubmit={completePrimary}>
          <header>
            <div>
              <span>Primary next action</span>
              <h2>Record outcome and continue</h2>
            </div>
            <button
              aria-label="Close completion dialog"
              onClick={() => dialogRef.current?.close()}
              type="button"
            >
              <X aria-hidden="true" size={18} />
            </button>
          </header>
          <p>
            Active seller leads and deals must leave this step with one owner, one next action,
            and one due date.
          </p>
          <label>
            <span>Outcome</span>
            <input
              name="outcome"
              placeholder="Seller reached, appointment completed, document sent"
              required
            />
          </label>
          <label>
            <span>Completion notes</span>
            <textarea
              name="completion_notes"
              placeholder="What happened and what matters for the next person?"
              rows={3}
            />
          </label>
          <fieldset>
            <legend>Successor action</legend>
            <label>
              <span>Next action</span>
              <input
                defaultValue={selected ? `Follow up on ${selected.source_record_label}` : ""}
                name="successor_title"
                required
              />
            </label>
            <div className={styles.dialogGrid}>
              <label>
                <span>Action type</span>
                <select defaultValue="follow_up" name="successor_type">
                  <option value="call">Call</option>
                  <option value="sms">Text</option>
                  <option value="email">Email</option>
                  <option value="appointment">Appointment</option>
                  <option value="underwriting">Underwriting</option>
                  <option value="contract">Contract</option>
                  <option value="buyer_follow_up">Buyer follow-up</option>
                  <option value="follow_up">Other follow-up</option>
                </select>
              </label>
              <label>
                <span>Due</span>
                <input defaultValue={defaultSuccessorDue()} name="successor_due_at" required type="datetime-local" />
              </label>
              <label>
                <span>Priority</span>
                <select defaultValue="normal" name="successor_priority">
                  <option value="urgent">Urgent</option>
                  <option value="high">High</option>
                  <option value="normal">Normal</option>
                  <option value="low">Low</option>
                </select>
              </label>
            </div>
          </fieldset>
          <label className={styles.terminalCheck}>
            <input
              name="terminal"
              onChange={(event) => {
                const form = event.currentTarget.form;
                if (!form) return;
                for (const fieldName of ["successor_title", "successor_due_at"]) {
                  const field = form.elements.namedItem(fieldName);
                  if (field instanceof HTMLInputElement) {
                    field.disabled = event.target.checked;
                    field.required = !event.target.checked;
                  }
                }
              }}
              type="checkbox"
            />
            <span>
              <strong>The source record is already closed</strong>
              <small>The API verifies this before allowing completion without a successor.</small>
            </span>
          </label>
          {error ? <p className={styles.dialogError} role="alert">{error}</p> : null}
          <footer>
            <button onClick={() => dialogRef.current?.close()} type="button">Cancel</button>
            <button className={styles.primaryButton} disabled={status === "saving"} type="submit">
              <Check aria-hidden="true" size={15} />
              {status === "saving" ? "Saving" : "Complete and set next action"}
            </button>
          </footer>
        </form>
      </dialog>
    </section>
  );
}

async function responseMessage(response: Response) {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? "The request could not be completed.";
  } catch {
    return "The request could not be completed.";
  }
}
