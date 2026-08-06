"use client";

import { useAuth } from "@clerk/nextjs";
import {
  AlertTriangle,
  CalendarDays,
  Check,
  ClipboardCheck,
  Clock3,
  ExternalLink,
  MapPin,
  Plus,
  Route,
  Settings2,
  UserRoundCheck,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import type {
  DispatchCandidate,
  DispatchSlotEvaluation,
  FieldAppointmentWorkspace,
  FieldOperationsOverview,
} from "../../lib/api";
import { labelize } from "../os-utils";
import { FieldCalendar } from "./field-calendar";
import { FieldMeetingWorkspace } from "./field-meeting-workspace";
import styles from "./field-operations.module.css";

type View = "dispatch" | "calendar" | "meetings" | "capacity";

function formatDateTime(value: string | null) {
  if (!value) return "Not scheduled";
  return new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function localInputValue(date: Date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function minuteLabel(value: number) {
  const hours = Math.floor(value / 60);
  const minutes = value % 60;
  const suffix = hours >= 12 ? "PM" : "AM";
  const displayHour = hours % 12 || 12;
  return `${displayHour}:${String(minutes).padStart(2, "0")} ${suffix}`;
}

function candidateStatus(candidate: DispatchCandidate) {
  if (candidate.eligible) return "Available";
  return candidate.violations.map(labelize).join(" · ");
}

export function FieldOperationsWorkspace({
  basePath = "/os/calendar",
  data,
  initialAppointmentId = "",
  initialLeadId = "",
  initialScheduleAt = "",
  initialScheduleOpen = false,
  initialWorkspace = null,
  initialView = "dispatch",
}: {
  basePath?: string;
  data: FieldOperationsOverview;
  initialAppointmentId?: string;
  initialLeadId?: string;
  initialScheduleAt?: string;
  initialScheduleOpen?: boolean;
  initialWorkspace?: FieldAppointmentWorkspace | null;
  initialView?: View;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const initialStart = useMemo(() => {
    const value = new Date();
    value.setDate(value.getDate() + 1);
    value.setHours(10, 0, 0, 0);
    return localInputValue(value);
  }, []);
  const initialEnd = useMemo(() => {
    const value = new Date();
    value.setDate(value.getDate() + 1);
    value.setHours(11, 30, 0, 0);
    return localInputValue(value);
  }, []);
  const initialComposerStart = useMemo(() => {
    const requested = initialScheduleAt ? new Date(initialScheduleAt) : null;
    if (requested && !Number.isNaN(requested.getTime())) {
      if (requested.getHours() === 0 && requested.getMinutes() === 0) {
        requested.setHours(10, 0, 0, 0);
      }
      return localInputValue(requested);
    }
    return initialStart;
  }, [initialScheduleAt, initialStart]);
  const initialComposerEnd = useMemo(() => {
    const value = new Date(initialComposerStart);
    value.setHours(value.getHours() + 1);
    return localInputValue(value);
  }, [initialComposerStart]);
  const initialAppointmentLead =
    data.schedulable_leads.find((lead) => lead.id === initialLeadId) ??
    data.schedulable_leads[0] ??
    null;
  const [view, setView] = useState<View>(initialView);
  const [requestedAppointmentId, setRequestedAppointmentId] = useState(initialAppointmentId);
  const [selectedLeadId, setSelectedLeadId] = useState(
    data.ready_leads.some((lead) => lead.id === initialLeadId)
      ? initialLeadId
      : data.ready_leads[0]?.id ?? "",
  );
  const [startAt, setStartAt] = useState(initialStart);
  const [endAt, setEndAt] = useState(initialEnd);
  const [evaluation, setEvaluation] = useState<DispatchSlotEvaluation | null>(null);
  const [selectedCloserId, setSelectedCloserId] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [editingUserId, setEditingUserId] = useState(data.users[0]?.id ?? "");
  const [appointmentComposerOpen, setAppointmentComposerOpen] = useState(initialScheduleOpen);
  const [appointmentLeadId, setAppointmentLeadId] = useState(initialAppointmentLead?.id ?? "");
  const [appointmentStartAt, setAppointmentStartAt] = useState(initialComposerStart);
  const [appointmentEndAt, setAppointmentEndAt] = useState(initialComposerEnd);
  const [appointmentLocationType, setAppointmentLocationType] = useState("phone");
  const [appointmentLocation, setAppointmentLocation] = useState(
    initialAppointmentLead?.phone_number ?? "",
  );
  const [appointmentOwnerId, setAppointmentOwnerId] = useState(
    initialAppointmentLead?.current_owner_user_id &&
      data.users.some((user) => user.id === initialAppointmentLead.current_owner_user_id)
      ? initialAppointmentLead.current_owner_user_id
      : "",
  );
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );
  const selectedLead = data.ready_leads.find((item) => item.id === selectedLeadId) ?? null;
  const selectedCandidate =
    evaluation?.candidates.find((item) => item.user_id === selectedCloserId) ?? null;
  const editingProfile = data.profiles.find((item) => item.user_id === editingUserId) ?? null;
  const appointmentLead =
    data.schedulable_leads.find((item) => item.id === appointmentLeadId) ?? null;

  function viewUrl(nextView: View, appointmentId = "", leadId = "") {
    const params = new URLSearchParams();
    const publicView =
      nextView === "calendar"
        ? "schedule"
        : nextView === "meetings"
          ? "appointment"
          : nextView === "capacity"
            ? "availability"
            : "dispatch";
    if (publicView !== "schedule") params.set("view", publicView);
    if (appointmentId) params.set("appointment", appointmentId);
    if (leadId) params.set("lead", leadId);
    const query = params.toString();
    return query ? `${basePath}?${query}` : basePath;
  }

  function chooseView(nextView: View) {
    setView(nextView);
    router.replace(
      viewUrl(
        nextView,
        nextView === "meetings" ? requestedAppointmentId : "",
        nextView === "dispatch" ? selectedLeadId : "",
      ),
      { scroll: false },
    );
  }

  function openAppointmentComposer(startsAt?: Date) {
    if (startsAt) {
      const start = new Date(startsAt);
      if (start.getHours() === 0 && start.getMinutes() === 0) {
        start.setHours(10, 0, 0, 0);
      }
      const end = new Date(start.getTime() + 60 * 60 * 1000);
      setAppointmentStartAt(localInputValue(start));
      setAppointmentEndAt(localInputValue(end));
    }
    setAppointmentComposerOpen(true);
  }

  function closeAppointmentComposer() {
    setAppointmentComposerOpen(false);
    router.replace(
      viewUrl(view, view === "meetings" ? requestedAppointmentId : ""),
      { scroll: false },
    );
  }

  function selectAppointmentLead(leadId: string) {
    const lead = data.schedulable_leads.find((item) => item.id === leadId) ?? null;
    setAppointmentLeadId(leadId);
    setAppointmentLocation(
      appointmentLocationType === "property"
        ? lead?.property_address ?? ""
        : appointmentLocationType === "phone"
          ? lead?.phone_number ?? ""
          : "",
    );
    const ownerId = lead?.current_owner_user_id;
    setAppointmentOwnerId(
      ownerId && data.users.some((user) => user.id === ownerId) ? ownerId : "",
    );
  }

  function selectAppointmentLocationType(locationType: string) {
    setAppointmentLocationType(locationType);
    setAppointmentLocation(
      locationType === "property"
        ? appointmentLead?.property_address ?? ""
        : locationType === "phone"
          ? appointmentLead?.phone_number ?? ""
          : "",
    );
  }

  async function request<T>(path: string, method: string, body?: object): Promise<T | null> {
    setSaving(true);
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
      if (response.status === 204) return {} as T;
      return (await response.json()) as T;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The operation could not be completed.");
      return null;
    } finally {
      setSaving(false);
    }
  }

  async function evaluate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedLeadId) return;
    const result = await request<DispatchSlotEvaluation>("/api/v1/field-operations/evaluate", "POST", {
      lead_id: selectedLeadId,
      scheduled_start_at: new Date(startAt).toISOString(),
      scheduled_end_at: new Date(endAt).toISOString(),
    });
    if (!result) return;
    setEvaluation(result);
    setSelectedCloserId(
      result.candidates.find((candidate) => candidate.eligible)?.user_id ??
        result.candidates[0]?.user_id ??
        "",
    );
  }

  async function dispatch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!evaluation || !selectedCloserId) return;
    const form = new FormData(event.currentTarget);
    const result = await request<{ appointment_id: string }>(
      "/api/v1/field-operations/dispatch",
      "POST",
      {
        lead_id: selectedLeadId,
        closer_user_id: selectedCloserId,
        scheduled_start_at: evaluation.scheduled_start_at,
        scheduled_end_at: evaluation.scheduled_end_at,
        appointment_type: String(form.get("appointment_type") ?? "seller_appointment"),
        location_type: String(form.get("location_type") ?? "property"),
        notes: String(form.get("notes") ?? "").trim() || null,
        override_conflicts: form.get("override_conflicts") === "on",
        override_reason: String(form.get("override_reason") ?? "").trim() || null,
      },
    );
    if (!result) return;
    setMessage("Appointment dispatched and added to the internal calendar.");
    setEvaluation(null);
    setRequestedAppointmentId(result.appointment_id);
    setView("meetings");
    router.replace(viewUrl("meetings", result.appointment_id), { scroll: false });
    router.refresh();
  }

  async function scheduleAppointment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!appointmentLeadId) return;
    const form = new FormData(event.currentTarget);
    const scheduledStartAt = new Date(appointmentStartAt).toISOString();
    const result = await request<{
      appointments: Array<{
        id: string;
        status: string;
        scheduled_start_at: string;
      }>;
    }>(`/api/v1/leads/${appointmentLeadId}/appointments`, "POST", {
      appointment_type: String(form.get("appointment_type") ?? "seller_call"),
      status: "scheduled",
      scheduled_start_at: scheduledStartAt,
      scheduled_end_at: new Date(appointmentEndAt).toISOString(),
      location_type: appointmentLocationType,
      location: appointmentLocation.trim() || null,
      notes: String(form.get("notes") ?? "").trim() || null,
      owner_user_id: appointmentOwnerId || null,
    });
    if (!result) return;
    const created = result.appointments.find(
      (item) =>
        item.status === "scheduled" &&
        item.scheduled_start_at.slice(0, 19) === scheduledStartAt.slice(0, 19),
    );
    setMessage("Appointment scheduled and added to the internal calendar.");
    setAppointmentComposerOpen(false);
    if (created) {
      setRequestedAppointmentId(created.id);
      setView("meetings");
      router.replace(viewUrl("meetings", created.id), { scroll: false });
    } else {
      setView("calendar");
      router.replace(viewUrl("calendar"), { scroll: false });
    }
    router.refresh();
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingUserId) return;
    const form = new FormData(event.currentTarget);
    const territoryIds = data.territories
      .filter((territory) => form.get(`territory_${territory.id}`) === "on")
      .map((territory) => territory.id);
    const result = await request(
      `/api/v1/field-operations/profiles/${editingUserId}`,
      "PUT",
      {
        timezone: String(form.get("timezone")),
        working_days: [0, 1, 2, 3, 4, 5, 6].filter(
          (day) => form.get(`working_day_${day}`) === "on",
        ),
        workday_start_minute: Number(form.get("workday_start_minute")),
        workday_end_minute: Number(form.get("workday_end_minute")),
        daily_capacity: Number(form.get("daily_capacity")),
        default_appointment_minutes: Number(form.get("default_appointment_minutes")),
        travel_buffer_minutes: Number(form.get("travel_buffer_minutes")),
        home_base_postal_code: String(form.get("home_base_postal_code") ?? "").trim() || null,
        territory_enforcement_enabled: form.get("territory_enforcement_enabled") === "on",
        is_active: form.get("is_active") === "on",
        territory_ids: territoryIds,
      },
    );
    if (result) {
      setMessage("Closer capacity settings saved.");
      router.refresh();
    }
  }

  async function addBlock(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingProfile) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const result = await request(
      `/api/v1/field-operations/profiles/${editingProfile.id}/blocks`,
      "POST",
      {
        block_type: String(values.get("block_type")),
        starts_at: new Date(String(values.get("starts_at"))).toISOString(),
        ends_at: new Date(String(values.get("ends_at"))).toISOString(),
        reason: String(values.get("reason") ?? "").trim(),
      },
    );
    if (result) {
      setMessage("Unavailable time added.");
      form.reset();
      router.refresh();
    }
  }

  async function removeBlock(blockId: string) {
    const result = await request(`/api/v1/field-operations/blocks/${blockId}`, "DELETE");
    if (result) {
      setMessage("Unavailable time removed.");
      router.refresh();
    }
  }

  return (
    <div className={styles.workspace}>
      <section className={styles.metrics} aria-label="Calendar operations summary">
        <div><span>Ready to schedule</span><strong>{data.metrics.ready_to_schedule}</strong></div>
        <div><span>Appointments today</span><strong>{data.metrics.appointments_today}</strong></div>
        <div className={data.metrics.unassigned_today ? styles.riskMetric : ""}><span>Unassigned today</span><strong>{data.metrics.unassigned_today}</strong></div>
        <div className={data.metrics.at_capacity_today ? styles.riskMetric : ""}><span>Closers at capacity</span><strong>{data.metrics.at_capacity_today}</strong></div>
      </section>

      <nav className={styles.tabs} aria-label="Calendar views">
        <button className={view === "calendar" ? styles.activeTab : ""} onClick={() => chooseView("calendar")} type="button"><CalendarDays size={16} />Schedule</button>
        <button className={view === "dispatch" ? styles.activeTab : ""} onClick={() => chooseView("dispatch")} type="button"><Route size={16} />Dispatch</button>
        <button className={view === "meetings" ? styles.activeTab : ""} onClick={() => chooseView("meetings")} type="button"><ClipboardCheck size={16} />Appointment</button>
        {data.can_manage ? <button className={view === "capacity" ? styles.activeTab : ""} onClick={() => chooseView("capacity")} type="button"><Settings2 size={16} />Availability</button> : null}
        <button className={styles.newAppointmentButton} onClick={() => openAppointmentComposer()} type="button"><Plus size={16} />Schedule appointment</button>
      </nav>

      {message ? <p className={message.includes("saved") || message.includes("added") || message.includes("dispatched") || message.includes("removed") ? styles.notice : styles.error}>{message}</p> : null}

      {appointmentComposerOpen ? (
        <div className={styles.appointmentComposerBackdrop} role="presentation">
          <section
            aria-labelledby="appointment-composer-title"
            aria-modal="true"
            className={styles.appointmentComposer}
            onKeyDown={(event) => {
              if (event.key === "Escape") closeAppointmentComposer();
            }}
            role="dialog"
          >
            <header>
              <div>
                <span>Calendar</span>
                <h3 id="appointment-composer-title">Schedule an appointment</h3>
                <p>Create a phone, property, video, or office meeting from one place.</p>
              </div>
              <button
                aria-label="Close appointment form"
                onClick={closeAppointmentComposer}
                title="Close"
                type="button"
              >
                <X size={18} />
              </button>
            </header>
            {data.schedulable_leads.length > 0 ? (
              <form onSubmit={scheduleAppointment}>
                <label className={styles.composerFullField}>
                  <span>Seller or property</span>
                  <select
                    autoFocus
                    onChange={(event) => selectAppointmentLead(event.target.value)}
                    required
                    value={appointmentLeadId}
                  >
                    {data.schedulable_leads.map((lead) => (
                      <option key={lead.id} value={lead.id}>
                        {lead.seller_name} — {lead.property_address}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Meeting format</span>
                  <select
                    onChange={(event) => selectAppointmentLocationType(event.target.value)}
                    value={appointmentLocationType}
                  >
                    <option value="phone">Phone</option>
                    <option value="property">At the property</option>
                    <option value="video">Video</option>
                    <option value="office">Office</option>
                    <option value="other">Other</option>
                  </select>
                </label>
                <label>
                  <span>Purpose</span>
                  <select defaultValue="seller_call" name="appointment_type">
                    <option value="seller_call">Seller call</option>
                    <option value="walkthrough">Property walkthrough</option>
                    <option value="offer_review">Offer review</option>
                    <option value="follow_up">Follow-up</option>
                  </select>
                </label>
                <label>
                  <span>Starts</span>
                  <input
                    onChange={(event) => setAppointmentStartAt(event.target.value)}
                    required
                    type="datetime-local"
                    value={appointmentStartAt}
                  />
                </label>
                <label>
                  <span>Ends</span>
                  <input
                    min={appointmentStartAt}
                    onChange={(event) => setAppointmentEndAt(event.target.value)}
                    required
                    type="datetime-local"
                    value={appointmentEndAt}
                  />
                </label>
                <label>
                  <span>Assigned team member</span>
                  <select
                    onChange={(event) => setAppointmentOwnerId(event.target.value)}
                    value={appointmentOwnerId}
                  >
                    <option value="">Use the lead owner</option>
                    {data.users.map((user) => (
                      <option key={user.id} value={user.id}>{user.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>
                    {appointmentLocationType === "phone"
                      ? "Phone number"
                      : appointmentLocationType === "property"
                        ? "Property address"
                        : "Location or meeting link"}
                  </span>
                  <input
                    onChange={(event) => setAppointmentLocation(event.target.value)}
                    placeholder={
                      appointmentLocationType === "video"
                        ? "Paste the meeting link"
                        : "Add the meeting location"
                    }
                    value={appointmentLocation}
                  />
                </label>
                <label className={styles.composerFullField}>
                  <span>Preparation notes</span>
                  <textarea
                    maxLength={1000}
                    name="notes"
                    placeholder="Seller expectations, access instructions, or topics to cover"
                    rows={3}
                  />
                </label>
                <footer className={styles.composerFullField}>
                  <button onClick={closeAppointmentComposer} type="button">
                    Cancel
                  </button>
                  <button disabled={saving} type="submit">
                    <CalendarDays size={16} />
                    {saving ? "Scheduling" : "Schedule appointment"}
                  </button>
                </footer>
              </form>
            ) : (
              <div className={styles.composerEmpty}>
                <p>No accessible seller leads are available to schedule.</p>
                <Link href="/os/leads">Open Leads</Link>
              </div>
            )}
          </section>
        </div>
      ) : null}

      {view === "dispatch" ? (
        <div className={styles.dispatchLayout}>
          <aside className={styles.leadQueue}>
            <div className={styles.sectionHeader}><div><span>Qualified sellers</span><h3>Needs appointment</h3></div><strong>{data.ready_leads.length}</strong></div>
            <div className={styles.leadRows}>
              {data.ready_leads.map((lead) => (
                <button className={selectedLeadId === lead.id ? styles.selectedLead : ""} key={lead.id} onClick={() => { setSelectedLeadId(lead.id); setEvaluation(null); }} type="button">
                  <strong>{lead.seller_name}</strong>
                  <span>{lead.property_address}</span>
                  <small>{lead.county ?? "County unknown"} · {lead.current_owner_name ?? "Unassigned"}</small>
                  <small>Requested {formatDateTime(lead.next_follow_up_at)}</small>
                </button>
              ))}
              {!data.ready_leads.length ? <p className={styles.empty}>No qualified sellers are waiting for an appointment.</p> : null}
            </div>
          </aside>

          <section className={styles.dispatchDesk}>
            {selectedLead ? (
              <>
                <div className={styles.selectedSummary}>
                  <div><span>Selected seller</span><h3>{selectedLead.seller_name}</h3><p><MapPin size={15} />{selectedLead.property_address}</p></div>
                  <Link aria-label={`Open ${selectedLead.seller_name}`} href={selectedLead.lead_url} title="Open lead"><ExternalLink size={17} /></Link>
                </div>
                <form className={styles.slotForm} onSubmit={evaluate}>
                  <label><span>Starts</span><input onChange={(event) => setStartAt(event.target.value)} required type="datetime-local" value={startAt} /></label>
                  <label><span>Ends</span><input onChange={(event) => setEndAt(event.target.value)} required type="datetime-local" value={endAt} /></label>
                  <button disabled={saving || !data.profiles.length} type="submit"><Clock3 size={16} />Check capacity</button>
                </form>
                {!data.profiles.length ? <div className={styles.callout}><AlertTriangle size={17} /><p>A manager must configure at least one closer before appointments can be dispatched.</p></div> : null}

                {evaluation ? (
                  <form className={styles.dispatchForm} onSubmit={dispatch}>
                    <div className={styles.evaluationHeader}><div><span>Slot evaluation</span><h3>{evaluation.territory_name ?? "No matching territory"}</h3></div><strong>{evaluation.candidates.filter((item) => item.eligible).length} available</strong></div>
                    <div className={styles.candidates}>
                      {evaluation.candidates.map((candidate) => (
                        <label className={`${styles.candidate} ${selectedCloserId === candidate.user_id ? styles.selectedCandidate : ""}`} key={candidate.user_id}>
                          <input checked={selectedCloserId === candidate.user_id} name="closer" onChange={() => setSelectedCloserId(candidate.user_id)} type="radio" value={candidate.user_id} />
                          <span className={candidate.eligible ? styles.availableIcon : styles.conflictIcon}>{candidate.eligible ? <Check size={15} /> : <AlertTriangle size={15} />}</span>
                          <span><strong>{candidate.user_name}</strong><small>{candidate.daily_booked_count}/{candidate.daily_capacity} booked · {candidate.travel_buffer_minutes}m travel buffer</small></span>
                          <em className={candidate.eligible ? styles.available : styles.conflict}>{candidateStatus(candidate)}</em>
                        </label>
                      ))}
                    </div>
                    <div className={styles.appointmentFields}>
                      <label><span>Appointment type</span><select name="appointment_type"><option value="seller_appointment">Seller appointment</option><option value="property_walkthrough">Property walkthrough</option><option value="offer_presentation">Offer presentation</option></select></label>
                      <label><span>Location</span><select name="location_type"><option value="property">Property</option><option value="office">Office</option><option value="phone">Phone</option><option value="video">Video</option></select></label>
                      <label className={styles.fullField}><span>Preparation note</span><textarea name="notes" placeholder="Access instructions, seller expectations, or appointment context" rows={2} /></label>
                    </div>
                    {selectedCandidate?.violations.length && data.can_manage ? (
                      <div className={styles.overrideBox}>
                        <label className={styles.checkLabel}><input name="override_conflicts" type="checkbox" />Override these conflicts</label>
                        <label><span>Required manager reason</span><textarea name="override_reason" rows={2} /></label>
                      </div>
                    ) : null}
                    <button disabled={saving || !selectedCloserId || Boolean(selectedCandidate?.violations.length && !data.can_manage)} type="submit"><UserRoundCheck size={16} />Dispatch appointment</button>
                  </form>
                ) : null}
              </>
            ) : <p className={styles.empty}>Select a qualified seller to begin scheduling.</p>}
          </section>
        </div>
      ) : null}

      {view === "calendar" ? (
        <FieldCalendar
          data={data}
          onOpenMeeting={(appointmentId) => {
            setRequestedAppointmentId(appointmentId);
            setView("meetings");
            router.replace(viewUrl("meetings", appointmentId), { scroll: false });
          }}
          onSchedule={openAppointmentComposer}
        />
      ) : null}

      {view === "meetings" ? (
        <FieldMeetingWorkspace
          data={data}
          initialWorkspace={initialWorkspace}
          onAppointmentChange={(appointmentId) => {
            setRequestedAppointmentId(appointmentId);
            router.replace(viewUrl("meetings", appointmentId), { scroll: false });
          }}
          requestedAppointmentId={requestedAppointmentId}
        />
      ) : null}

      {view === "capacity" && data.can_manage ? (
        <div className={styles.capacityLayout}>
          <section className={styles.profileConfig}>
            <div className={styles.sectionHeader}><div><span>Dispatch rules</span><h3>Closer capacity</h3></div></div>
            <label className={styles.userSelect}><span>Closer</span><select onChange={(event) => setEditingUserId(event.target.value)} value={editingUserId}>{data.users.map((user) => <option key={user.id} value={user.id}>{user.name}{user.profile_configured ? " · configured" : ""}</option>)}</select></label>
            {editingUserId ? (
              <form className={styles.profileForm} key={editingUserId} onSubmit={saveProfile}>
                <label><span>Timezone</span><input defaultValue={editingProfile?.timezone ?? "America/New_York"} name="timezone" required /></label>
                <label><span>Home ZIP</span><input defaultValue={editingProfile?.home_base_postal_code ?? ""} name="home_base_postal_code" /></label>
                <label><span>Day starts</span><select defaultValue={editingProfile?.workday_start_minute ?? 540} name="workday_start_minute">{[480, 540, 600, 660, 720].map((value) => <option key={value} value={value}>{minuteLabel(value)}</option>)}</select></label>
                <label><span>Day ends</span><select defaultValue={editingProfile?.workday_end_minute ?? 1020} name="workday_end_minute">{[960, 1020, 1080, 1140, 1200].map((value) => <option key={value} value={value}>{minuteLabel(value)}</option>)}</select></label>
                <label><span>Daily appointments</span><input defaultValue={editingProfile?.daily_capacity ?? 4} max={20} min={1} name="daily_capacity" type="number" /></label>
                <label><span>Appointment length</span><input defaultValue={editingProfile?.default_appointment_minutes ?? 90} max={480} min={15} name="default_appointment_minutes" step={15} type="number" /></label>
                <label><span>Travel buffer</span><input defaultValue={editingProfile?.travel_buffer_minutes ?? 30} max={240} min={0} name="travel_buffer_minutes" step={15} type="number" /></label>
                <fieldset className={styles.fullField}><legend>Working days</legend><div className={styles.dayChecks}>{["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day, index) => <label key={day}><input defaultChecked={editingProfile?.working_days.includes(index) ?? index < 5} name={`working_day_${index}`} type="checkbox" />{day}</label>)}</div></fieldset>
                <fieldset className={styles.fullField}><legend>Territories</legend><div className={styles.territoryChecks}>{data.territories.map((territory) => <label key={territory.id}><input defaultChecked={editingProfile?.territory_ids.includes(territory.id) ?? false} name={`territory_${territory.id}`} type="checkbox" /><span><strong>{territory.name}</strong><small>{territory.market_name} · {territory.county_names.join(", ") || "ZIP-defined"}</small></span></label>)}</div></fieldset>
                <label className={styles.checkLabel}><input defaultChecked={editingProfile?.territory_enforcement_enabled ?? true} name="territory_enforcement_enabled" type="checkbox" />Require territory match</label>
                <label className={styles.checkLabel}><input defaultChecked={editingProfile?.is_active ?? true} name="is_active" type="checkbox" />Active for dispatch</label>
                <button disabled={saving} type="submit"><Check size={16} />Save capacity</button>
              </form>
            ) : <p className={styles.empty}>Add an eligible acquisitions user before configuring capacity.</p>}
          </section>

          <section className={styles.blockConfig}>
            <div className={styles.sectionHeader}><div><span>Exceptions</span><h3>Unavailable time</h3></div></div>
            {editingProfile ? (
              <>
                <form className={styles.blockForm} onSubmit={addBlock}>
                  <label><span>Type</span><select name="block_type"><option value="unavailable">Unavailable</option><option value="personal">Personal</option><option value="company">Company</option><option value="travel">Travel</option></select></label>
                  <label><span>Starts</span><input name="starts_at" required type="datetime-local" /></label>
                  <label><span>Ends</span><input name="ends_at" required type="datetime-local" /></label>
                  <label><span>Reason</span><input name="reason" required /></label>
                  <button disabled={saving} type="submit">Add block</button>
                </form>
                <div className={styles.blockRows}>
                  {editingProfile.blocks.map((block) => <div key={block.id}><span><strong>{labelize(block.block_type)}</strong>{block.reason}</span><span>{formatDateTime(block.starts_at)} to {formatDateTime(block.ends_at)}</span><button aria-label="Remove unavailable time" disabled={saving} onClick={() => removeBlock(block.id)} title="Remove block" type="button">Remove</button></div>)}
                  {!editingProfile.blocks.length ? <p className={styles.empty}>No upcoming unavailable time.</p> : null}
                </div>
              </>
            ) : <p className={styles.empty}>Save a closer profile before adding unavailable time.</p>}
          </section>
        </div>
      ) : null}
    </div>
  );
}
