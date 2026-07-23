import {
  AlertTriangle,
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Inbox,
  ListChecks,
  UserRoundCheck,
} from "lucide-react";
import Link from "next/link";

import { CompleteTaskButton } from "../complete-task-button";
import {
  getDashboardData,
  getExecutiveCopilotOverview,
  getFieldOperationsOverview,
  getWorkspaceProfile,
  type LeadListItem,
  type SpeedToLeadTask,
} from "../lib/api";
import { StatusBadge } from "./_components/design-system";
import { ManagementCopilotPanel } from "./_components/management-copilot-panel";
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
    return "Your assigned seller follow-up, meetings, and offer preparation in priority order.";
  }
  if (roleKeys.includes("acquisition_manager")) {
    return "Team response, qualification, scheduling, and offer exceptions that need intervention.";
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
    detail: `${task.seller_name} · ${formatDateTime(task.due_at)}`,
    href: `/os/inbox?lead=${task.lead_id}`,
    status: isOverdue ? "Overdue" : "Due next",
    tone: isOverdue ? "danger" : "warning",
    task,
  };
}

function leadPriority(
  lead: LeadListItem,
  category: string,
  status: string,
  href: string,
  tone: PriorityItem["tone"],
): PriorityItem {
  return {
    id: `${category}-${lead.id}`,
    category,
    title: lead.seller_name,
    detail: lead.property_address,
    href,
    status,
    tone,
  };
}

function isToday(value: string) {
  return new Date(value).toDateString() === new Date().toDateString();
}

export default async function Home() {
  const [dashboard, profile, fieldResult, executiveCopilot] = await Promise.all([
    getDashboardData(),
    getWorkspaceProfile(),
    getFieldOperationsOverview(),
    getExecutiveCopilotOverview(30),
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
  const { overdueTasks, dueTasks, needsQualification, appointmentQueue, offerQueue } =
    getWorkspaceQueues(scopedLeads, scopedTasks);
  const speedTaskIds = new Set(dashboard.speedToLeadQueue.map((task) => task.task_id));
  const scopedSpeedTasks = scopedTasks.filter((task) => speedTaskIds.has(task.task_id));
  const seenTaskIds = new Set<string>();
  const seenLeadIds = new Set<string>();
  const priorities: PriorityItem[] = [];

  for (const task of [...overdueTasks, ...scopedSpeedTasks, ...dueTasks]) {
    if (seenTaskIds.has(task.task_id)) continue;
    priorities.push(taskPriority(task));
    seenTaskIds.add(task.task_id);
    seenLeadIds.add(task.lead_id);
  }
  for (const appointment of scopedAppointments) {
    if (seenLeadIds.has(appointment.lead_id)) continue;
    priorities.push({
      id: `appointment-${appointment.id}`,
      category: "Seller meeting",
      title: appointment.seller_name,
      detail: `${formatDateTime(appointment.scheduled_start_at)} · ${appointment.property_address}`,
      href: `/os/field-operations?view=meetings&appointment=${appointment.id}`,
      status: isToday(appointment.scheduled_start_at) ? "Today" : "Scheduled",
      tone: isToday(appointment.scheduled_start_at) ? "info" : "neutral",
    });
    seenLeadIds.add(appointment.lead_id);
  }
  for (const lead of needsQualification) {
    if (seenLeadIds.has(lead.id)) continue;
    priorities.push(
      leadPriority(
        lead,
        "Qualification",
        "Needs review",
        `/os/leads/${lead.id}`,
        "warning",
      ),
    );
    seenLeadIds.add(lead.id);
  }
  for (const lead of offerQueue) {
    if (seenLeadIds.has(lead.id)) continue;
    priorities.push(
      leadPriority(lead, "Offer preparation", "Ready for work", `/os/leads/${lead.id}`, "info"),
    );
    seenLeadIds.add(lead.id);
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
    profile.role_keys.some((role) => ["administrator", "acquisition_manager"].includes(role));

  return (
    <WorkspacePage>
      <PageHeader
        actions={
          <div className={styles.headerActions}>
            <Link href="/os/inbox"><Inbox aria-hidden="true" size={16} />Inbox</Link>
            <Link href="/os/tasks"><ListChecks aria-hidden="true" size={16} />Work Queue</Link>
            <Link href="/os/calendar"><CalendarDays aria-hidden="true" size={16} />Calendar</Link>
          </div>
        }
        description={dashboardDescription(roleKeys)}
        eyebrow={profile ? `${profile.display_name} · ${roleLabel}` : "Daily command center"}
        meta={dashboard.apiConnected ? "Live workspace data" : "API fallback view"}
        title="Dashboard"
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
      {executiveCopilot ? (
        <ManagementCopilotPanel
          endpointBase="/api/v1/dashboard/executive-copilot"
          initialData={executiveCopilot}
        />
      ) : null}

      <section className={styles.dailyMetrics} aria-label="Daily work summary">
        <Link className={styles.dangerMetric} href="/os/tasks?view=overdue">
          <span><Clock3 aria-hidden="true" size={16} />Overdue</span>
          <strong>{overdueTasks.length}</strong>
          <small>Follow-up past due</small>
        </Link>
        <Link className={styles.warningMetric} href="/os/lead-manager">
          <span><UserRoundCheck aria-hidden="true" size={16} />Qualification</span>
          <strong>{needsQualification.length}</strong>
          <small>Seller records incomplete</small>
        </Link>
        <Link className={styles.infoMetric} href="/os/calendar">
          <span><CalendarDays aria-hidden="true" size={16} />Meetings today</span>
          <strong>{todayAppointments}</strong>
          <small>{appointmentQueue.length} awaiting appointment work</small>
        </Link>
        <Link className={styles.brandMetric} href="/os/underwriting">
          <span><CheckCircle2 aria-hidden="true" size={16} />Offer prep</span>
          <strong>{offerQueue.length}</strong>
          <small>Underwriting or approval</small>
        </Link>
      </section>

      <section className={styles.commandGrid}>
        <section className={styles.priorityPanel} aria-labelledby="priority-heading">
          <header>
            <div>
              <p>Priority order</p>
              <h2 id="priority-heading">Work requiring attention</h2>
            </div>
            <Link href="/os/tasks">Open full queue <ArrowRight aria-hidden="true" size={15} /></Link>
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
                {item.task && profile?.permissions.includes("leads:edit") ? (
                  <CompleteTaskButton taskId={item.task.task_id} />
                ) : null}
              </article>
            ))}
            {!priorities.length ? (
              <div className={styles.clearState}>
                <CheckCircle2 aria-hidden="true" size={24} />
                <strong>No priority exceptions</strong>
                <span>Open seller work will appear here in due-time order.</span>
              </div>
            ) : null}
          </div>
        </section>

        <aside className={styles.exceptionPanel} aria-labelledby="exceptions-heading">
          <header>
            <p>Exceptions</p>
            <h2 id="exceptions-heading">Needs intervention</h2>
          </header>
          <div>
            <Link href="/os/inbox?view=unread">
              <span>Unread conversations</span>
              <strong>{profile?.unread_notification_count ?? 0}</strong>
            </Link>
            {showTeamExceptions ? (
              <Link href="/os/leads">
                <span>Unassigned seller leads</span>
                <strong>{unassignedLeads}</strong>
              </Link>
            ) : null}
            <Link href="/os/tasks?view=unscheduled">
              <span>Tasks without due dates</span>
              <strong>{scopedTasks.filter((task) => task.due_status === "unscheduled").length}</strong>
            </Link>
            <Link href="/os/approvals">
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
          <Link href="/os/pipeline">Open Seller Pipeline <ArrowRight aria-hidden="true" size={15} /></Link>
        </header>
        <div>
          {pipelineStages.slice(0, 8).map((stage) => (
            <Link href={`/os/pipeline?stage=${stage.key}`} key={stage.key}>
              <span>{stage.label}</span>
              <strong>{getPipelineStageCount(stage, pipelineCounts)}</strong>
            </Link>
          ))}
        </div>
      </section>
    </WorkspacePage>
  );
}
