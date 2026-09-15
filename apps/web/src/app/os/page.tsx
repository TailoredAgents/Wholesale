import {
  AlertTriangle,
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  Clock3,
  ListChecks,
  MessageSquareReply,
} from "lucide-react";
import Link from "next/link";

import { CompleteTaskButton } from "../complete-task-button";
import {
  getDashboardData,
  getExecutiveCopilotOverview,
  getFieldOperationsOverview,
  getInboxAttentionSummary,
  getWorkspaceProfile,
  type SpeedToLeadTask,
} from "../lib/api";
import { StatusBadge } from "./_components/design-system";
import { ManagementCopilotLauncher } from "./_components/management-copilot-launcher";
import { PageHeader, WorkspacePage } from "./_components/page-contracts";
import { isOwnerProfile, primaryRoleLabel } from "./os-navigation";
import {
  formatDateTime,
  getPipelineStageCount,
  getWorkspaceQueues,
  labelize,
  pipelineStages,
} from "./os-utils";
import styles from "./dashboard.module.css";

export const dynamic = "force-dynamic";

type PriorityItem = {
  id: string;
  category: string;
  title: string;
  detail: string;
  href: string;
  status: string;
  tone: "danger" | "warning" | "info" | "neutral";
  task?: SpeedToLeadTask;
};

function dashboardDescription(roleKeys: string[]) {
  if (roleKeys.includes("acquisition_rep")) {
    return "Your seller replies, manual reminders, meetings, and offer preparation in priority order.";
  }
  if (roleKeys.includes("acquisition_manager")) {
    return "Team replies, reminders, scheduled commitments, and offer exceptions that need attention.";
  }
  if (roleKeys.some((role) => ["owner", "founder_operator", "ceo"].includes(role))) {
    return "Company priorities, seller response, appointments, and deal-readiness exceptions.";
  }
  return "The seller and acquisition work requiring attention across the operating system.";
}

function taskPriority(task: SpeedToLeadTask): PriorityItem {
  const isOverdue = task.due_status === "overdue";
  return {
    id: `task-${task.task_id}`,
    category: labelize(task.task_type),
    title: task.title,
    detail: `${task.seller_name ?? "Operational work"} · ${formatDateTime(task.due_at)}`,
    href: `/os/tasks?item=task:${task.task_id}`,
    status: isOverdue ? "Overdue" : "Due today",
    tone: isOverdue ? "danger" : "warning",
    task,
  };
}

function companyDateKey(value: string | Date) {
  const parts = new Intl.DateTimeFormat("en-US", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "America/New_York",
    year: "numeric",
  }).formatToParts(typeof value === "string" ? new Date(value) : value);
  const keyed = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${keyed.year}-${keyed.month}-${keyed.day}`;
}

function isToday(value: string) {
  return companyDateKey(value) === companyDateKey(new Date());
}

export default async function Home() {
  const [dashboard, profile, fieldResult, executiveCopilot, inboxAttention] = await Promise.all([
    getDashboardData(),
    getWorkspaceProfile(),
    getFieldOperationsOverview(),
    getExecutiveCopilotOverview(30),
    getInboxAttentionSummary(),
  ]);
  const roleKeys = profile?.role_keys ?? [];
  const individualAcquisitions = roleKeys.includes("acquisition_rep") &&
    !roleKeys.includes("acquisition_manager");
  const scopedLeads = individualAcquisitions && profile
    ? dashboard.leads.filter((lead) => lead.assigned_user_email === profile.email)
    : dashboard.leads;
  const scopedTasks = individualAcquisitions && profile
    ? dashboard.openTaskQueue.filter((task) => task.assigned_user_email === profile.email)
    : dashboard.openTaskQueue;
  const scopedAppointments = (fieldResult.fieldOperations?.upcoming_appointments ?? []).filter(
    (appointment) =>
      !individualAcquisitions ||
      !profile ||
      appointment.closer_name.toLowerCase() === profile.display_name.toLowerCase(),
  );
  const { overdueTasks, dueTasks, offerQueue } =
    getWorkspaceQueues(scopedLeads, scopedTasks);
  const speedTaskIds = new Set(dashboard.speedToLeadQueue.map((task) => task.task_id));
  const scopedSpeedTasks = scopedTasks.filter((task) => speedTaskIds.has(task.task_id));
  const seenTaskIds = new Set<string>();
  const seenLeadIds = new Set<string>();
  const priorities: PriorityItem[] = [];
  const todayKey = companyDateKey(new Date());
  const manualRemindersDue = scopedLeads.filter((lead) => {
    const reminder = lead.primary_next_action;
    return Boolean(
      reminder?.action_type === "follow_up" &&
      reminder.due_at &&
      companyDateKey(reminder.due_at) <= todayKey,
    );
  });
  const tasksDueToday = dueTasks.filter((task) => task.due_at && isToday(task.due_at));

  if (inboxAttention.needs_reply_count > 0) {
    priorities.push({
      id: "inbox-needs-reply",
      category: "Conversations",
      title: `${inboxAttention.needs_reply_count} ${
        inboxAttention.needs_reply_count === 1 ? "conversation needs" : "conversations need"
      } a reply`,
      detail: inboxAttention.overdue_reply_count > 0
        ? `${inboxAttention.overdue_reply_count} beyond the response target`
        : "Waiting for a team response",
      href: "/os/inbox?view=needs_reply",
      status: inboxAttention.overdue_reply_count > 0 ? "Overdue" : "Waiting",
      tone: inboxAttention.overdue_reply_count > 0 ? "danger" : "warning",
    });
  }

  for (const task of [...overdueTasks, ...scopedSpeedTasks, ...tasksDueToday]) {
    if (seenTaskIds.has(task.task_id)) continue;
    priorities.push(taskPriority(task));
    seenTaskIds.add(task.task_id);
    if (task.lead_id) seenLeadIds.add(task.lead_id);
  }
  for (const appointment of scopedAppointments.filter((item) => isToday(item.scheduled_start_at))) {
    if (seenLeadIds.has(appointment.lead_id)) continue;
    priorities.push({
      id: `appointment-${appointment.id}`,
      category: "Seller meeting",
      title: appointment.seller_name,
      detail: `${formatDateTime(appointment.scheduled_start_at)} · ${appointment.property_address}`,
      href: `/os/calendar?view=appointment&appointment=${appointment.id}`,
      status: isToday(appointment.scheduled_start_at) ? "Today" : "Scheduled",
      tone: isToday(appointment.scheduled_start_at) ? "info" : "neutral",
    });
    seenLeadIds.add(appointment.lead_id);
  }
  const unassignedLeads = dashboard.leads.filter((lead) => !lead.assigned_user_email).length;
  const todayAppointments = scopedAppointments.filter((appointment) =>
    isToday(appointment.scheduled_start_at),
  ).length;
  const pipelineCounts = new Map(
    dashboard.summary.pipeline.map((stage) => [stage.stage_key, stage.count]),
  );
  const roleLabel = profile ? primaryRoleLabel(profile) : "Workspace user";
  const showTeamExceptions = !profile || isOwnerProfile(profile) ||
    profile.role_keys.some((role) =>
      ["administrator", "operations_assistant", "acquisition_manager"].includes(role),
    );

  return (
    <WorkspacePage>
      <PageHeader
        actions={
          <div className={styles.headerActions}>
            <Link className={styles.primaryHeaderAction} href="/os/leads?view=today">
              <ListChecks aria-hidden="true" size={16} />Open Today
            </Link>
            {executiveCopilot ? (
              <ManagementCopilotLauncher
                endpointBase="/api/v1/dashboard/executive-copilot"
                initialData={executiveCopilot}
              />
            ) : null}
          </div>
        }
        description={dashboardDescription(roleKeys)}
        eyebrow={profile ? `${profile.display_name} · ${roleLabel}` : "Daily command center"}
        meta={dashboard.apiConnected ? "Live workspace data" : "API fallback view"}
        title="Home"
      />

      {!dashboard.apiConnected ? (
        <div className={styles.connectionWarning} role="status">
          <AlertTriangle aria-hidden="true" size={18} />
          <div>
            <strong>Live operations data is unavailable</strong>
            <span>The page is showing an empty fallback until the API reconnects.</span>
          </div>
        </div>
      ) : null}
      <section className={styles.dailyMetrics} aria-label="Daily work summary">
        <Link className={styles.dangerMetric} href="/os/inbox?view=needs_reply">
          <span><MessageSquareReply aria-hidden="true" size={16} />Needs reply</span>
          <strong>{inboxAttention.needs_reply_count}</strong>
          <small>{inboxAttention.overdue_reply_count} beyond response target</small>
        </Link>
        <Link className={styles.warningMetric} href="/os/leads?view=today">
          <span><Clock3 aria-hidden="true" size={16} />Reminders due</span>
          <strong>{manualRemindersDue.length}</strong>
          <small>Only reminders set by your team</small>
        </Link>
        <Link className={styles.infoMetric} href="/os/calendar">
          <span><CalendarDays aria-hidden="true" size={16} />Meetings today</span>
          <strong>{todayAppointments}</strong>
          <small>Scheduled commitments only</small>
        </Link>
        <Link className={styles.brandMetric} href="/os/leads?view=underwriting">
          <span><CheckCircle2 aria-hidden="true" size={16} />Offer prep</span>
          <strong>{offerQueue.length}</strong>
          <small>Underwriting and approval stages</small>
        </Link>
      </section>

      <section className={styles.commandGrid}>
        <section className={styles.priorityPanel} aria-labelledby="priority-heading">
          <header>
            <div>
              <p>Priority order</p>
              <h2 id="priority-heading">Work requiring attention</h2>
            </div>
            <Link href="/os/leads?view=today">Open Today <ArrowRight aria-hidden="true" size={15} /></Link>
          </header>
          <div className={styles.priorityList}>
            {priorities.slice(0, 8).map((item) => (
              <article key={item.id}>
                <div className={styles.priorityCopy}>
                  <span>{item.category}</span>
                  <Link href={item.href}>{item.title}</Link>
                  <small>{item.detail}</small>
                </div>
                <StatusBadge tone={item.tone}>{item.status}</StatusBadge>
                <Link aria-label={`Open ${item.title}`} className={styles.openPriority} href={item.href}>
                  <ArrowRight aria-hidden="true" size={16} />
                </Link>
                {item.task &&
                item.task.work_kind !== "primary_next_action" &&
                profile?.permissions.includes("leads:edit") ? (
                  <CompleteTaskButton taskId={item.task.task_id} />
                ) : null}
              </article>
            ))}
            {!priorities.length ? (
              <div className={styles.clearState}>
                <CheckCircle2 aria-hidden="true" size={24} />
                <strong>Nothing needs attention</strong>
                <span>New replies, due reminders, and scheduled work will appear here.</span>
              </div>
            ) : null}
          </div>
        </section>

        <aside className={styles.exceptionPanel} aria-labelledby="exceptions-heading">
          <header>
            <p>Live workload</p>
            <h2 id="exceptions-heading">
              {individualAcquisitions ? "My work snapshot" : "Company snapshot"}
            </h2>
          </header>
          <div>
            <Link href="/os/inbox?view=needs_reply">
              <span>Conversations needing reply</span>
              <strong>{inboxAttention.needs_reply_count}</strong>
            </Link>
            {showTeamExceptions ? (
              <Link href="/os/inbox?view=needs_reply">
                <span>Unassigned conversations</span>
                <strong>{inboxAttention.unassigned_needs_reply_count}</strong>
              </Link>
            ) : null}
            {showTeamExceptions ? (
              <Link href="/os/leads">
                <span>Unassigned seller leads</span>
                <strong>{unassignedLeads}</strong>
              </Link>
            ) : null}
            <Link href="/os/leads?view=today">
              <span>Manual reminders due</span>
              <strong>{manualRemindersDue.length}</strong>
            </Link>
            <Link href="/os/tasks?view=approvals">
              <span>Offers pending approval</span>
              <strong>{dashboard.summary.offers_pending}</strong>
            </Link>
          </div>
          <footer>
            <strong>{scopedLeads.length}</strong>
            <span>{individualAcquisitions ? "assigned active leads" : "active seller leads"}</span>
          </footer>
        </aside>
      </section>

      <section className={styles.pipelinePulse} aria-labelledby="pipeline-heading">
        <header>
          <div>
            <p>Pipeline pulse</p>
            <h2 id="pipeline-heading">Active seller stages</h2>
          </div>
          <Link href="/os/leads?display=board">Open Pipeline <ArrowRight aria-hidden="true" size={15} /></Link>
        </header>
        <div>
          {pipelineStages.slice(0, 8).map((stage) => (
            <Link href={`/os/leads?display=board&stage=${stage.key}`} key={stage.key}>
              <span>{stage.label}</span>
              <strong>{getPipelineStageCount(stage, pipelineCounts)}</strong>
            </Link>
          ))}
        </div>
      </section>
    </WorkspacePage>
  );
}
