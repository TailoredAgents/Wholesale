"use client";

import { useAuth } from "@clerk/nextjs";
import { Check, ExternalLink, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import type { SpeedToLeadTask } from "../../lib/api";
import { StatusBadge, TableShell } from "../_components/design-system";
import { formatDateTime, labelize } from "../os-utils";
import styles from "./work-queue.module.css";

export type QueueView = "all" | "mine" | "overdue" | "due" | "unscheduled";
type CompletionStatus = "idle" | "saving" | "error";

const savedViews: Array<{ key: QueueView; label: string }> = [
  { key: "all", label: "All work" },
  { key: "mine", label: "My work" },
  { key: "overdue", label: "Overdue" },
  { key: "due", label: "Due next" },
  { key: "unscheduled", label: "Unscheduled" },
];

function ownerLabel(email: string | null) {
  if (!email) return "Unassigned";
  return email.split("@")[0]?.replace(/[._-]+/g, " ") || email;
}

function nextAction(task: SpeedToLeadTask) {
  const communicationTask = ["speed_to_lead", "call", "sms", "email", "follow_up"].some(
    (signal) => task.task_type.includes(signal),
  );
  if (communicationTask) {
    return { href: `/os/inbox?lead=${task.lead_id}`, label: "Open conversation" };
  }
  if (task.task_type.includes("appointment")) {
    return { href: "/os/calendar", label: "Open calendar" };
  }
  return { href: `/os/leads/${task.lead_id}`, label: "Open lead" };
}

function dueTone(status: string): "danger" | "warning" | "neutral" {
  if (status === "overdue") return "danger";
  if (status === "due") return "warning";
  return "neutral";
}

export function WorkQueueWorkspace({
  canComplete,
  currentUserEmail,
  initialTasks,
  initialView,
}: {
  canComplete: boolean;
  currentUserEmail: string | null;
  initialTasks: SpeedToLeadTask[];
  initialView: QueueView;
}) {
  const { getToken } = useAuth();
  const [tasks, setTasks] = useState(initialTasks);
  const [view, setView] = useState<QueueView>(initialView);
  const [query, setQuery] = useState("");
  const [owner, setOwner] = useState("all");
  const [selected, setSelected] = useState<string[]>([]);
  const [completionStatus, setCompletionStatus] = useState<CompletionStatus>("idle");
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  const devUserEmail =
    process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com";

  const owners = useMemo(
    () =>
      Array.from(
        new Set(tasks.map((task) => task.assigned_user_email).filter((email): email is string => Boolean(email))),
      ).sort(),
    [tasks],
  );
  const counts = useMemo(
    () => ({
      all: tasks.length,
      mine: currentUserEmail
        ? tasks.filter((task) => task.assigned_user_email === currentUserEmail).length
        : 0,
      overdue: tasks.filter((task) => task.due_status === "overdue").length,
      due: tasks.filter((task) => task.due_status === "due").length,
      unscheduled: tasks.filter((task) => task.due_status === "unscheduled").length,
    }),
    [currentUserEmail, tasks],
  );
  const visibleTasks = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return tasks.filter((task) => {
      const matchesView =
        view === "all" ||
        (view === "mine" && task.assigned_user_email === currentUserEmail) ||
        task.due_status === view;
      const matchesOwner =
        owner === "all" ||
        (owner === "unassigned" && !task.assigned_user_email) ||
        task.assigned_user_email === owner;
      const matchesQuery =
        !normalizedQuery ||
        `${task.title} ${task.seller_name} ${task.property_address} ${task.task_type}`
          .toLowerCase()
          .includes(normalizedQuery);
      return matchesView && matchesOwner && matchesQuery;
    });
  }, [currentUserEmail, owner, query, tasks, view]);
  const allVisibleSelected =
    visibleTasks.length > 0 && visibleTasks.every((task) => selected.includes(task.task_id));

  async function completeTasks(taskIds: string[]) {
    if (!taskIds.length || completionStatus === "saving") return;
    setCompletionStatus("saving");
    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;

      const results = await Promise.all(
        taskIds.map(async (taskId) => {
          try {
            const response = await fetch(`${apiBaseUrl}/api/v1/tasks/${taskId}/complete`, {
              method: "PATCH",
              headers,
              body: JSON.stringify({ reason: "Completed from the Stonegate Work Queue." }),
            });
            return { completed: response.ok, taskId };
          } catch {
            return { completed: false, taskId };
          }
        }),
      );
      const completedIds = results
        .filter((result) => result.completed)
        .map((result) => result.taskId);
      const failedIds = results.filter((result) => !result.completed).map((result) => result.taskId);
      setTasks((current) => current.filter((task) => !completedIds.includes(task.task_id)));
      setSelected((current) => current.filter((taskId) => failedIds.includes(taskId)));
      setCompletionStatus(failedIds.length ? "error" : "idle");
    } catch {
      setCompletionStatus("error");
    }
  }

  function completeSelected() {
    if (!selected.length) return;
    const confirmed = window.confirm(
      `Mark ${selected.length} selected ${selected.length === 1 ? "task" : "tasks"} complete?`,
    );
    if (confirmed) void completeTasks(selected);
  }

  return (
    <section className={styles.workspace}>
      <div className={styles.savedViews} aria-label="Saved task views">
        {savedViews.map((item) => (
          <button
            aria-pressed={view === item.key}
            className={view === item.key ? styles.activeView : undefined}
            key={item.key}
            onClick={() => {
              setView(item.key);
              setSelected([]);
            }}
            type="button"
          >
            <span>{item.label}</span>
            <strong>{counts[item.key]}</strong>
          </button>
        ))}
      </div>

      <div className={styles.toolbar}>
        <label className={styles.searchField}>
          <Search aria-hidden="true" size={16} />
          <input
            aria-label="Search open tasks"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search task, seller, or property"
            type="search"
            value={query}
          />
        </label>
        <label className={styles.ownerFilter}>
          <span>Owner</span>
          <select onChange={(event) => setOwner(event.target.value)} value={owner}>
            <option value="all">All owners</option>
            <option value="unassigned">Unassigned</option>
            {owners.map((email) => (
              <option key={email} value={email}>
                {ownerLabel(email)}
              </option>
            ))}
          </select>
        </label>
        <span className={styles.resultCount}>{visibleTasks.length} shown</span>
        {canComplete && selected.length ? (
          <button
            className={styles.bulkButton}
            disabled={completionStatus === "saving"}
            onClick={completeSelected}
            type="button"
          >
            <Check aria-hidden="true" size={16} />
            {completionStatus === "saving"
              ? "Completing"
              : `Complete selected (${selected.length})`}
          </button>
        ) : null}
      </div>

      {completionStatus === "error" ? (
        <p className={styles.error} role="alert">
          Some tasks could not be completed. Confirmed tasks were removed; failed tasks remain selected.
        </p>
      ) : null}

      <TableShell label="Open task queue">
        <table className={styles.taskTable}>
          <thead>
            <tr>
              {canComplete ? (
                <th className={styles.checkColumn}>
                  <input
                    aria-label="Select all visible tasks"
                    checked={allVisibleSelected}
                    onChange={(event) => {
                      const visibleIds = visibleTasks.map((task) => task.task_id);
                      setSelected((current) =>
                        event.target.checked
                          ? Array.from(new Set([...current, ...visibleIds]))
                          : current.filter((taskId) => !visibleIds.includes(taskId)),
                      );
                    }}
                    type="checkbox"
                  />
                </th>
              ) : null}
              <th>Task</th>
              <th>Seller</th>
              <th>Owner</th>
              <th>Due</th>
              <th>Next action</th>
              {canComplete ? <th className={styles.actionColumn}>Complete</th> : null}
            </tr>
          </thead>
          <tbody>
            {visibleTasks.map((task) => {
              const action = nextAction(task);
              return (
                <tr key={task.task_id}>
                  {canComplete ? (
                    <td className={styles.checkColumn}>
                      <input
                        aria-label={`Select ${task.title}`}
                        checked={selected.includes(task.task_id)}
                        onChange={(event) =>
                          setSelected((current) =>
                            event.target.checked
                              ? [...current, task.task_id]
                              : current.filter((taskId) => taskId !== task.task_id),
                          )
                        }
                        type="checkbox"
                      />
                    </td>
                  ) : null}
                  <td>
                    <strong>{task.title}</strong>
                    <small>{labelize(task.task_type)} · {labelize(task.priority)}</small>
                  </td>
                  <td>
                    <Link href={`/os/leads/${task.lead_id}`}>{task.seller_name}</Link>
                    <small>{task.property_address}</small>
                  </td>
                  <td>{ownerLabel(task.assigned_user_email)}</td>
                  <td>
                    <StatusBadge tone={dueTone(task.due_status)}>{labelize(task.due_status)}</StatusBadge>
                    <small>{formatDateTime(task.due_at)}</small>
                  </td>
                  <td>
                    <Link className={styles.nextAction} href={action.href}>
                      {action.label}
                      <ExternalLink aria-hidden="true" size={13} />
                    </Link>
                    <small>{labelize(task.stage_key)}</small>
                  </td>
                  {canComplete ? (
                    <td className={styles.actionColumn}>
                      <button
                        aria-label={`Complete ${task.title}`}
                        className={styles.completeButton}
                        disabled={completionStatus === "saving"}
                        onClick={() => void completeTasks([task.task_id])}
                        type="button"
                      >
                        <Check aria-hidden="true" size={15} />
                      </button>
                    </td>
                  ) : null}
                </tr>
              );
            })}
            {!visibleTasks.length ? (
              <tr>
                <td colSpan={canComplete ? 7 : 5}>
                  <div className={styles.emptyState}>
                    <strong>No tasks match this view</strong>
                    <span>Change the saved view, owner, or search filters.</span>
                  </div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </TableShell>
    </section>
  );
}
