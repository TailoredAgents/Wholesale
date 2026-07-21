"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import type { AcquisitionOperations, LeadListItem } from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./operations.module.css";

type Tab = "today" | "calling" | "team" | "quality" | "follow-up";
type RequestStatus = "idle" | "saving" | "saved" | "error";

const tabs: Array<{ key: Tab; label: string }> = [
  { key: "today", label: "Calendar" },
  { key: "calling", label: "Calling lists" },
  { key: "team", label: "Team" },
  { key: "quality", label: "Data quality" },
  { key: "follow-up", label: "Follow-up plans" },
];

function formValue(formData: FormData, key: string) {
  return String(formData.get(key) ?? "").trim();
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function roleLabel(user: AcquisitionOperations["users"][number]) {
  return user.role_keys.map(labelize).join(", ") || "No role";
}

export function OperationsWorkspace({
  operations,
  leads,
}: {
  operations: AcquisitionOperations;
  leads: LeadListItem[];
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [activeTab, setActiveTab] = useState<Tab>("today");
  const [status, setStatus] = useState<RequestStatus>("idle");
  const [message, setMessage] = useState("");
  const [selectedListId, setSelectedListId] = useState(operations.calling_lists[0]?.id ?? "");
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );
  const selectedList = operations.calling_lists.find((item) => item.id === selectedListId);
  const activeUsers = operations.users.filter((user) => user.is_active);
  const acquisitionUsers = activeUsers.filter((user) =>
    user.role_keys.some((role) => ["administrator", "acquisition_manager", "acquisition_rep"].includes(role)),
  );
  const openLeadOptions = leads.filter((lead) => !lead.archived_at);
  const pendingDuplicates = operations.duplicate_candidates.filter(
    (candidate) => candidate.status === "pending",
  );

  async function headers() {
    const token = await getToken().catch(() => null);
    const result: Record<string, string> = { "Content-Type": "application/json" };
    if (token) result.Authorization = `Bearer ${token}`;
    else result["X-Dev-User-Email"] = devUserEmail;
    return result;
  }

  async function mutate(path: string, method: "POST" | "PATCH", body?: object) {
    setStatus("saving");
    setMessage("");
    try {
      const response = await fetch(`${apiBaseUrl}${path}`, {
        method,
        headers: await headers(),
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "The operation could not be completed.");
      }
      setStatus("saved");
      router.refresh();
      return true;
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "The operation could not be completed.");
      return false;
    }
  }

  async function submitUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const saved = await mutate("/api/v1/operations/users", "POST", {
      display_name: formValue(data, "display_name"),
      email: formValue(data, "email"),
      role_key: formValue(data, "role_key"),
    });
    if (saved) form.reset();
  }

  async function submitTeam(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const saved = await mutate("/api/v1/operations/teams", "POST", {
      name: formValue(data, "name"),
      team_type: formValue(data, "team_type"),
      manager_user_id: formValue(data, "manager_user_id") || null,
    });
    if (saved) form.reset();
  }

  async function submitTeamMember(event: FormEvent<HTMLFormElement>, teamId: string) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await mutate(`/api/v1/operations/teams/${teamId}/members`, "POST", {
      user_id: formValue(data, "user_id"),
      membership_role: formValue(data, "membership_role"),
    });
  }

  async function setUserActive(user: AcquisitionOperations["users"][number]) {
    await mutate(`/api/v1/operations/users/${user.id}`, "PATCH", {
      is_active: !user.is_active,
      reason: user.is_active
        ? "Workspace access deactivated by an operations manager."
        : "Workspace access restored by an operations manager.",
    });
  }

  function openSavedView(resourceType: string) {
    if (resourceType === "appointments") setActiveTab("today");
    else if (resourceType === "calling_lists") setActiveTab("calling");
    else router.push(resourceType === "inbox" ? "/os/inbox" : "/os/leads");
  }

  async function resolveDuplicate(candidateId: string, action: "merge" | "not_duplicate") {
    if (action === "merge" && !window.confirm("Merge these records and archive the secondary lead? Its history will be preserved.")) return;
    await mutate(`/api/v1/operations/duplicates/${candidateId}/resolve`, "POST", {
      action,
      notes:
        action === "merge"
          ? "Confirmed duplicate; secondary record archived with history preserved."
          : "Reviewed as separate seller records.",
    });
  }

  async function submitCallingList(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const saved = await mutate("/api/v1/operations/calling-lists", "POST", {
      name: formValue(data, "name"),
      description: formValue(data, "description") || null,
      default_assignee_user_id: formValue(data, "default_assignee_user_id") || null,
    });
    if (saved) form.reset();
  }

  async function addLeadToList(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedListId) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const saved = await mutate(
      `/api/v1/operations/calling-lists/${selectedListId}/leads`,
      "POST",
      {
        lead_ids: [formValue(data, "lead_id")],
        assigned_user_id: formValue(data, "assigned_user_id") || null,
      },
    );
    if (saved) form.reset();
  }

  async function submitAttempt(event: FormEvent<HTMLFormElement>, entryId: string) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const disposition = formValue(data, "disposition");
    await mutate(`/api/v1/operations/calling-list-entries/${entryId}`, "PATCH", {
      status: ["callback", "follow_up"].includes(disposition) ? "in_progress" : "completed",
      disposition,
      notes: formValue(data, "notes") || null,
      handoff_user_id: formValue(data, "handoff_user_id") || null,
    });
  }

  async function submitSavedView(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const resource = formValue(data, "resource_type");
    const saved = await mutate("/api/v1/operations/saved-views", "POST", {
      name: formValue(data, "name"),
      resource_type: resource,
      filters: resource === "appointments" ? { status: "scheduled" } : { status: "active" },
      is_shared: false,
      team_id: null,
    });
    if (saved) form.reset();
  }

  async function submitPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const saved = await mutate("/api/v1/operations/follow-up-plans", "POST", {
      name: formValue(data, "name"),
      description: formValue(data, "description") || null,
      steps: [
        { delay_days: 1, action_type: "call", title: "Personal seller follow-up", body: null },
        {
          delay_days: 3,
          action_type: "sms",
          title: "Seller check-in draft",
          body: formValue(data, "sms_body"),
        },
        { delay_days: 7, action_type: "task", title: "Review seller status", body: null },
      ],
    });
    if (saved) form.reset();
  }

  return (
    <section className={styles.workspace}>
      <div className={styles.metrics}>
        <div><span>Internal calendar</span><strong>{operations.appointments.filter((item) => ["scheduled", "rescheduled"].includes(item.status)).length}</strong></div>
        <div><span>Unread alerts</span><strong>{operations.unread_notification_count}</strong></div>
        <div><span>Calling progress</span><strong>{operations.calling_lists.reduce((sum, item) => sum + item.completed_records, 0)} / {operations.calling_lists.reduce((sum, item) => sum + item.total_records, 0)}</strong></div>
        <div><span>Duplicate reviews</span><strong>{pendingDuplicates.length}</strong></div>
      </div>

      <div className={styles.tabBar} role="tablist" aria-label="Acquisition operations views">
        {tabs.filter((tab) => operations.can_manage || !["team", "quality", "follow-up"].includes(tab.key)).map((tab) => (
          <button
            aria-selected={activeTab === tab.key}
            className={activeTab === tab.key ? styles.activeTab : undefined}
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            role="tab"
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>

      {status !== "idle" ? (
        <div className={`${styles.feedback} ${styles[status]}`} role="status">
          {status === "saving" ? "Saving changes..." : status === "saved" ? "Changes saved." : message}
        </div>
      ) : null}

      {activeTab === "today" ? (
        <div className={styles.twoColumn}>
          <div className={styles.section}>
            <div className={styles.sectionHeader}><div><span>Stonegate schedule</span><h3>Internal calendar</h3></div><strong>{operations.appointments.length}</strong></div>
            <div className={styles.rows}>
              {operations.appointments.length === 0 ? <p className={styles.empty}>No upcoming appointments.</p> : null}
              {operations.appointments.map((appointment) => (
                <Link className={styles.appointmentRow} href={`/os/leads/${appointment.lead_id}?tab=communications`} key={appointment.id}>
                  <time>{formatDate(appointment.scheduled_start_at)}</time>
                  <div><strong>{appointment.seller_name}</strong><span>{appointment.property_address}</span></div>
                  <div className={styles.rowMeta}><span>{appointment.owner_name ?? "Unassigned"}</span><span className={styles.badge}>{labelize(appointment.status)}</span></div>
                </Link>
              ))}
            </div>
          </div>
          <div className={styles.section}>
            <div className={styles.sectionHeader}><div><span>Alerts</span><h3>Needs attention</h3></div><strong>{operations.unread_notification_count}</strong></div>
            <div className={styles.rows}>
              {operations.notifications.length === 0 ? <p className={styles.empty}>No active notifications.</p> : null}
              {operations.notifications.map((notification) => (
                <div className={styles.notificationRow} key={notification.id}>
                  <div><strong>{notification.title}</strong><p>{notification.body}</p><time>{formatDate(notification.created_at)}</time></div>
                  <div className={styles.inlineActions}>
                    {notification.action_url ? <Link href={notification.action_url}>Open</Link> : null}
                    {!notification.read_at ? <button onClick={() => mutate(`/api/v1/operations/notifications/${notification.id}/read`, "PATCH")} type="button">Mark read</button> : null}
                  </div>
                </div>
              ))}
            </div>
            {operations.saved_views.length ? (
              <div className={styles.savedViews}>
                <span>Saved views</span>
                {operations.saved_views.map((view) => (
                  <button key={view.id} onClick={() => openSavedView(view.resource_type)} type="button">
                    {view.name}
                  </button>
                ))}
              </div>
            ) : null}
            <form className={styles.inlineForm} onSubmit={submitSavedView}>
              <label><span>Saved view name</span><input name="name" required placeholder="My scheduled visits" /></label>
              <label><span>View</span><select name="resource_type"><option value="appointments">Appointments</option><option value="calling_lists">Calling lists</option><option value="leads">Leads</option><option value="inbox">Inbox</option></select></label>
              <button type="submit">Save view</button>
            </form>
          </div>
        </div>
      ) : null}

      {activeTab === "calling" ? (
        <div className={styles.section}>
          <div className={styles.sectionHeader}><div><span>Prospecting</span><h3>Calling execution</h3></div><select aria-label="Selected calling list" value={selectedListId} onChange={(event) => setSelectedListId(event.target.value)}><option value="">Select a list</option>{operations.calling_lists.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div>
          {operations.can_manage ? (
            <div className={styles.formBand}>
              <form onSubmit={submitCallingList}><h4>Create list</h4><label><span>Name</span><input name="name" required /></label><label><span>Default caller</span><select name="default_assignee_user_id"><option value="">Unassigned</option>{activeUsers.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select></label><label><span>Description</span><input name="description" /></label><button type="submit">Create list</button></form>
              <form onSubmit={addLeadToList}><h4>Add seller</h4><label><span>Lead</span><select name="lead_id" required><option value="">Select lead</option>{openLeadOptions.map((lead) => <option key={lead.id} value={lead.id}>{lead.seller_name} · {lead.property_street_address}</option>)}</select></label><label><span>Caller</span><select name="assigned_user_id"><option value="">List default</option>{activeUsers.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select></label><button disabled={!selectedListId} type="submit">Add to list</button></form>
            </div>
          ) : null}
          {selectedList ? <div className={styles.progress}><span style={{ width: `${selectedList.total_records ? Math.round((selectedList.completed_records / selectedList.total_records) * 100) : 0}%` }} /></div> : null}
          <div className={styles.callingRows}>
            {selectedList?.entries.length === 0 ? <p className={styles.empty}>This list has no assigned sellers.</p> : null}
            {selectedList?.entries.map((entry) => (
              <div className={styles.callingRow} key={entry.id}>
                <div className={styles.leadIdentity}><Link href={`/os/leads/${entry.lead_id}`}>{entry.seller_name}</Link><span>{entry.property_address}</span><small>{entry.attempt_count} attempts · {entry.assigned_user_name ?? "Unassigned"}</small></div>
                <form onSubmit={(event) => submitAttempt(event, entry.id)}>
                  <select aria-label="Call disposition" defaultValue={entry.disposition ?? "no_answer"} name="disposition"><option value="no_answer">No answer</option><option value="callback">Callback</option><option value="follow_up">Follow up</option><option value="interested">Interested</option><option value="appointment_set">Appointment set</option><option value="not_interested">Not interested</option><option value="wrong_number">Wrong number</option><option value="dnc">Do not call</option></select>
                  <select aria-label="Handoff owner" name="handoff_user_id"><option value="">No handoff</option>{acquisitionUsers.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select>
                  <input aria-label="Attempt notes" name="notes" placeholder="Outcome notes" defaultValue={entry.notes ?? ""} />
                  <button type="submit">Record</button>
                </form>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {activeTab === "team" ? (
        <div className={styles.twoColumn}>
          <div className={styles.section}>
            <div className={styles.sectionHeader}><div><span>Access</span><h3>Workspace users</h3></div><strong>{activeUsers.length}</strong></div>
            <div className={styles.rows}>{operations.users.map((user) => <div className={styles.userRow} key={user.id}><div><strong>{user.display_name}</strong><span>{user.email}</span></div><div><span>{roleLabel(user)}</span><small>{user.open_leads} leads · {user.open_tasks} tasks</small></div><button className={styles.secondaryButton} onClick={() => setUserActive(user)} type="button">{user.is_active ? "Deactivate" : "Reactivate"}</button></div>)}</div>
            <form className={styles.stackForm} onSubmit={submitUser}><h4>Add individual login</h4><label><span>Name</span><input name="display_name" required /></label><label><span>Email</span><input name="email" required type="email" /></label><label><span>Role</span><select name="role_key"><option value="prospecting_caller">VA caller</option><option value="acquisition_rep">Acquisitions rep</option><option value="acquisition_manager">Acquisitions manager</option><option value="disposition_rep">Dispositions rep</option><option value="transaction_coordinator">Transaction coordinator</option></select></label><button type="submit">Create user</button></form>
          </div>
          <div className={styles.section}>
            <div className={styles.sectionHeader}><div><span>Structure</span><h3>Teams</h3></div><strong>{operations.teams.length}</strong></div>
            <div className={styles.rows}>{operations.teams.map((team) => <div className={styles.teamRow} key={team.id}><div><strong>{team.name}</strong><span>{labelize(team.team_type)} · {team.manager_name ?? "No manager"}</span><small>{team.members.length} members</small></div><form onSubmit={(event) => submitTeamMember(event, team.id)}><select aria-label={`Add member to ${team.name}`} name="user_id" required><option value="">Add member</option>{activeUsers.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select><select aria-label="Membership role" name="membership_role"><option value="member">Member</option><option value="manager">Manager</option></select><button type="submit">Add</button></form></div>)}</div>
            <form className={styles.stackForm} onSubmit={submitTeam}><h4>Create team</h4><label><span>Name</span><input name="name" required /></label><label><span>Function</span><select name="team_type"><option value="prospecting">Prospecting</option><option value="acquisitions">Acquisitions</option><option value="dispositions">Dispositions</option><option value="operations">Operations</option></select></label><label><span>Manager</span><select name="manager_user_id"><option value="">No manager</option>{activeUsers.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select></label><button type="submit">Create team</button></form>
          </div>
        </div>
      ) : null}

      {activeTab === "quality" ? (
        <div className={styles.section}>
          <div className={styles.sectionHeader}><div><span>Review queue</span><h3>Possible duplicate leads</h3></div><button onClick={() => mutate("/api/v1/operations/duplicates/scan", "POST")} type="button">Scan active leads</button></div>
          <div className={styles.rows}>{pendingDuplicates.length === 0 ? <p className={styles.empty}>No possible duplicates need review.</p> : pendingDuplicates.map((candidate) => <div className={styles.duplicateRow} key={candidate.id}><div><strong>{candidate.primary_label}</strong><span>Compared with {candidate.duplicate_label}</span><small>{candidate.match_reasons.join(" · ")} · {candidate.match_score}% match</small></div><div className={styles.inlineActions}><button onClick={() => resolveDuplicate(candidate.id, "not_duplicate")} type="button">Keep separate</button><button className={styles.dangerButton} onClick={() => resolveDuplicate(candidate.id, "merge")} type="button">Merge records</button></div></div>)}</div>
        </div>
      ) : null}

      {activeTab === "follow-up" ? (
        <div className={styles.twoColumn}>
          <div className={styles.section}>
            <div className={styles.sectionHeader}><div><span>Approved cadence</span><h3>Follow-up plans</h3></div><strong>{operations.follow_up_plans.length}</strong></div>
            <div className={styles.rows}>{operations.follow_up_plans.length === 0 ? <p className={styles.empty}>No follow-up plans created.</p> : operations.follow_up_plans.map((plan) => <div className={styles.planRow} key={plan.id}><div><strong>{plan.name}</strong><span>{plan.description ?? "No description"}</span><small>{plan.steps.length} steps · {plan.active_enrollments} active</small></div><form onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); void mutate(`/api/v1/operations/follow-up-plans/${plan.id}/enroll`, "POST", { lead_id: formValue(data, "lead_id") }); }}><select name="lead_id" required><option value="">Select seller</option>{openLeadOptions.map((lead) => <option key={lead.id} value={lead.id}>{lead.seller_name}</option>)}</select><button type="submit">Enroll</button></form></div>)}</div>
          </div>
          <div className={styles.section}>
            <div className={styles.sectionHeader}><div><span>Human reviewed</span><h3>Create a starter cadence</h3></div></div>
            <form className={styles.stackForm} onSubmit={submitPlan}><label><span>Plan name</span><input name="name" required placeholder="Warm seller follow-up" /></label><label><span>Description</span><textarea name="description" rows={3} /></label><label><span>Day 3 SMS draft</span><textarea name="sms_body" required rows={5} placeholder="Hi, this is Stonegate Home Buyers..." /></label><div className={styles.cadence}><span>Day 1 · Personal call</span><span>Day 3 · SMS approval</span><span>Day 7 · Review task</span></div><button type="submit">Create plan</button></form>
          </div>
        </div>
      ) : null}
    </section>
  );
}
