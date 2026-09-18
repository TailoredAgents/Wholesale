import {
  ArrowRight,
  BellRing,
  CalendarDays,
  CheckCircle2,
  Inbox,
  PhoneMissed,
  UserRoundPlus,
} from "lucide-react";
import Link from "next/link";

import type {
  AcquisitionOperations,
  LeadListItem,
  SpeedToLeadTask,
  WorkspaceProfile,
} from "../../lib/api";
import { LeadStageBadge } from "../_components/lead-stage-badge";
import { getPipelineStage, isAddressOnlyLead } from "../os-utils";
import styles from "./seller-today-workspace.module.css";

const COMPANY_TIME_ZONE = "America/New_York";
const MAILBOX_NOTIFICATION_TYPES = new Set([
  "mailbox_inbound",
  "mailbox_response_due",
  "mailbox_owner_escalation",
]);

type Appointment = AcquisitionOperations["appointments"][number];
type Notification = AcquisitionOperations["notifications"][number];

function easternDateKey(value: string | Date) {
  const parts = new Intl.DateTimeFormat("en-US", {
    day: "2-digit",
    month: "2-digit",
    timeZone: COMPANY_TIME_ZONE,
    year: "numeric",
  }).formatToParts(typeof value === "string" ? new Date(value) : value);
  const keyed = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${keyed.year}-${keyed.month}-${keyed.day}`;
}

function easternTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: COMPANY_TIME_ZONE,
  }).format(new Date(value));
}

function easternDateTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    month: "short",
    timeZone: COMPANY_TIME_ZONE,
  }).format(new Date(value));
}

function isPersonalWorkspace(profile: WorkspaceProfile | null) {
  return Boolean(
    profile?.role_keys.includes("acquisition_rep") &&
      !profile.role_keys.includes("acquisition_manager"),
  );
}

function belongsToCurrentUser(
  assignedUserEmail: string | null,
  profile: WorkspaceProfile | null,
  personalOnly: boolean,
) {
  return !personalOnly || !profile || assignedUserEmail === profile.email;
}

function EmptyState({ children }: { children: string }) {
  return (
    <div className={styles.emptyState}>
      <CheckCircle2 aria-hidden="true" size={18} />
      <span>{children}</span>
    </div>
  );
}

function SectionHeading({
  count,
  description,
  icon: Icon,
  title,
}: {
  count: number;
  description: string;
  icon: typeof Inbox;
  title: string;
}) {
  return (
    <header className={styles.sectionHeading}>
      <div className={styles.sectionIcon}><Icon aria-hidden="true" size={18} /></div>
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      <strong>{count}</strong>
    </header>
  );
}

export function SellerTodayWorkspace({
  appointments,
  initialLeadId,
  leads,
  notifications,
  profile,
  tasks,
}: {
  appointments: Appointment[];
  initialLeadId: string;
  leads: LeadListItem[];
  notifications: Notification[];
  profile: WorkspaceProfile | null;
  tasks: SpeedToLeadTask[];
}) {
  const now = new Date();
  const todayKey = easternDateKey(now);
  const personalOnly = isPersonalWorkspace(profile);
  const selectedLead = leads.find((lead) => lead.id === initialLeadId) ?? null;

  const reminders = leads
    .filter((lead) => {
      const reminder = lead.primary_next_action;
      return Boolean(
        reminder?.action_type === "follow_up" &&
          reminder.due_at &&
          easternDateKey(reminder.due_at) <= todayKey &&
          belongsToCurrentUser(
            reminder.responsible_user_email ?? lead.assigned_user_email,
            profile,
            personalOnly,
          ),
      );
    })
    .sort(
      (first, second) =>
        new Date(first.primary_next_action!.due_at!).getTime() -
        new Date(second.primary_next_action!.due_at!).getTime(),
    );

  const missedCallbacks = tasks
    .filter(
      (task) =>
        task.task_type === "missed_prospecting_callback" &&
        belongsToCurrentUser(task.assigned_user_email, profile, personalOnly),
    )
    .sort((first, second) => new Date(first.created_at).getTime() - new Date(second.created_at).getTime());

  const inboxAlerts = Array.from(
    notifications
      .filter(
        (notification) =>
          notification.read_at === null &&
          MAILBOX_NOTIFICATION_TYPES.has(notification.notification_type),
      )
      .reduce((byConversation, notification) => {
        const key = notification.entity_id ?? notification.id;
        if (!byConversation.has(key)) byConversation.set(key, notification);
        return byConversation;
      }, new Map<string, Notification>())
      .values(),
  )
    .sort((first, second) => new Date(second.created_at).getTime() - new Date(first.created_at).getTime());

  const todayAppointments = appointments
    .filter(
      (appointment) =>
        ["scheduled", "rescheduled"].includes(appointment.status) &&
        easternDateKey(appointment.scheduled_start_at) === todayKey,
    )
    .sort(
      (first, second) =>
        new Date(first.scheduled_start_at).getTime() - new Date(second.scheduled_start_at).getTime(),
    );

  const newOrUnassigned = leads
    .filter(
      (lead) =>
        !isAddressOnlyLead(lead) &&
        (getPipelineStage(lead.stage_key)?.key === "new" || !lead.assigned_user_email),
    )
    .sort((first, second) => {
      const assignmentOrder = Number(Boolean(first.assigned_user_email)) - Number(Boolean(second.assigned_user_email));
      if (assignmentOrder !== 0) return assignmentOrder;
      return new Date(second.received_at).getTime() - new Date(first.received_at).getTime();
    });

  const communicationCount = inboxAlerts.length + missedCallbacks.length;
  const totalAttention =
    communicationCount + reminders.length + todayAppointments.length + newOrUnassigned.length;

  return (
    <section className={styles.workspace}>
      <header className={styles.intro}>
        <div>
          <p>Focused workday</p>
          <h2>What actually needs attention today</h2>
          <span>
            This page shows real inbound activity, callbacks, appointments, and reminders your team
            deliberately scheduled. It does not invent follow-up work.
          </span>
        </div>
        <dl className={styles.summary}>
          <div><dt>Attention</dt><dd>{totalAttention}</dd></div>
          <div><dt>Messages & calls</dt><dd>{communicationCount}</dd></div>
          <div><dt>Reminders</dt><dd>{reminders.length}</dd></div>
          <div><dt>Appointments</dt><dd>{todayAppointments.length}</dd></div>
        </dl>
      </header>

      {selectedLead ? (
        <Link className={styles.selectedLead} href={`/os/leads/${selectedLead.id}`}>
          <div>
            <span>Selected seller</span>
            <strong>{selectedLead.seller_name}</strong>
            <small>{selectedLead.property_address}</small>
          </div>
          <LeadStageBadge stageKey={selectedLead.stage_key} />
          <ArrowRight aria-hidden="true" size={16} />
        </Link>
      ) : null}

      <div className={styles.priorityGrid}>
        <section className={styles.panel}>
          <SectionHeading
            count={communicationCount}
            description="New inbound activity and unanswered callbacks"
            icon={Inbox}
            title="Messages & callbacks"
          />
          <div className={styles.rows}>
            {missedCallbacks.slice(0, 4).map((task) => (
              <Link className={styles.row} href={`/os/tasks?item=task:${task.task_id}`} key={task.task_id}>
                <PhoneMissed aria-hidden="true" size={17} />
                <div>
                  <strong>{task.title}</strong>
                  <span>{task.assigned_user_email ?? "Unassigned"}</span>
                </div>
                <small>Return call</small>
              </Link>
            ))}
            {inboxAlerts.slice(0, Math.max(0, 6 - Math.min(4, missedCallbacks.length))).map((notification) => (
              <Link
                className={styles.row}
                href={notification.action_url ?? "/os/inbox?view=needs_reply"}
                key={notification.id}
              >
                <BellRing aria-hidden="true" size={17} />
                <div>
                  <strong>{notification.title}</strong>
                  <span>{notification.body}</span>
                </div>
                <small>{easternDateTime(notification.created_at)}</small>
              </Link>
            ))}
            {communicationCount === 0 ? <EmptyState>No new alert or missed callback is waiting here.</EmptyState> : null}
          </div>
          <Link className={styles.panelAction} href="/os/inbox?view=needs_reply">
            Open live reply queue <ArrowRight aria-hidden="true" size={15} />
          </Link>
        </section>

        <section className={styles.panel}>
          <SectionHeading
            count={reminders.length}
            description="Only reminders deliberately set by your team"
            icon={BellRing}
            title="Reminders due"
          />
          <div className={styles.rows}>
            {reminders.slice(0, 6).map((lead) => (
              <Link className={styles.row} href={`/os/leads/${lead.id}`} key={lead.id}>
                <BellRing aria-hidden="true" size={17} />
                <div>
                  <strong>{lead.primary_next_action?.title ?? "Seller reminder"}</strong>
                  <span>{lead.seller_name} · {lead.property_address}</span>
                </div>
                <small>{easternDateTime(lead.primary_next_action!.due_at!)}</small>
              </Link>
            ))}
            {reminders.length === 0 ? <EmptyState>No manually scheduled reminder is due.</EmptyState> : null}
          </div>
          <Link className={styles.panelAction} href="/os/leads?view=no_follow_up">
            View all reminders <ArrowRight aria-hidden="true" size={15} />
          </Link>
        </section>
      </div>

      <div className={styles.supportGrid}>
        <section className={styles.panel}>
          <SectionHeading
            count={todayAppointments.length}
            description="Scheduled seller meetings on today’s calendar"
            icon={CalendarDays}
            title="Appointments today"
          />
          <div className={styles.rows}>
            {todayAppointments.slice(0, 6).map((appointment) => (
              <Link
                className={styles.row}
                href={`/os/calendar?appointment=${appointment.id}`}
                key={appointment.id}
              >
                <CalendarDays aria-hidden="true" size={17} />
                <div>
                  <strong>{appointment.seller_name}</strong>
                  <span>{appointment.property_address} · {appointment.owner_name ?? "Unassigned"}</span>
                </div>
                <small>{easternTime(appointment.scheduled_start_at)}</small>
              </Link>
            ))}
            {todayAppointments.length === 0 ? <EmptyState>No seller appointment is scheduled today.</EmptyState> : null}
          </div>
          <Link className={styles.panelAction} href="/os/calendar">
            Open calendar <ArrowRight aria-hidden="true" size={15} />
          </Link>
        </section>

        <section className={styles.panel}>
          <SectionHeading
            count={newOrUnassigned.length}
            description="Contact-ready records that are new or need an owner"
            icon={UserRoundPlus}
            title="New & unassigned"
          />
          <div className={styles.rows}>
            {newOrUnassigned.slice(0, 6).map((lead) => (
              <Link className={styles.row} href={`/os/leads/${lead.id}`} key={lead.id}>
                <UserRoundPlus aria-hidden="true" size={17} />
                <div>
                  <strong>{lead.seller_name}</strong>
                  <span>{lead.property_address}</span>
                </div>
                <LeadStageBadge stageKey={lead.stage_key} />
              </Link>
            ))}
            {newOrUnassigned.length === 0 ? <EmptyState>No new or unassigned lead needs sorting.</EmptyState> : null}
          </div>
          <div className={styles.splitActions}>
            <Link href="/os/leads?stage=new">View new</Link>
            <Link href="/os/leads?owner=unassigned">View unassigned</Link>
          </div>
        </section>
      </div>

      <footer className={styles.footerActions}>
        <div>
          <strong>Qualification is lead context, not an overdue task.</strong>
          <span>Use the filter when you are ready to fill missing seller facts.</span>
        </div>
        <Link href="/os/leads?view=needs_qualification">
          View needs qualification <ArrowRight aria-hidden="true" size={15} />
        </Link>
      </footer>
    </section>
  );
}
