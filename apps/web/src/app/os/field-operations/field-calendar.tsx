"use client";

/* eslint-disable react-hooks/set-state-in-effect */

import {
  Building2,
  CalendarClock,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  CircleSlash2,
  House,
  MapPin,
  Phone,
  Plus,
  UserRound,
  Video,
} from "lucide-react";
import { CSSProperties, Fragment, useEffect, useMemo, useState } from "react";

import type { FieldCalendarAppointment, FieldOperationsOverview } from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./field-operations.module.css";
import { useFieldApi } from "./use-field-api";

type CalendarMode = "month" | "week" | "day" | "agenda";

function startOfDay(value: Date) {
  const result = new Date(value);
  result.setHours(0, 0, 0, 0);
  return result;
}

function addDays(value: Date, amount: number) {
  const result = new Date(value);
  result.setDate(result.getDate() + amount);
  return result;
}

function startOfWeek(value: Date) {
  return addDays(startOfDay(value), -value.getDay());
}

function startOfMonthGrid(value: Date) {
  return startOfWeek(new Date(value.getFullYear(), value.getMonth(), 1));
}

function sameDay(left: Date, right: Date) {
  return (
    left.getFullYear() === right.getFullYear() &&
    left.getMonth() === right.getMonth() &&
    left.getDate() === right.getDate()
  );
}

function timeLabel(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

const appointmentVisuals = {
  phone: { label: "Phone", className: "eventPhone", icon: Phone },
  property: { label: "At property", className: "eventProperty", icon: House },
  video: { label: "Video", className: "eventVideo", icon: Video },
  office: { label: "Office", className: "eventOffice", icon: Building2 },
  other: { label: "Other", className: "eventOther", icon: CalendarClock },
} as const;

function appointmentVisual(appointment: FieldCalendarAppointment) {
  if (appointment.status === "cancelled") {
    return { label: "Cancelled", className: "eventCancelled", icon: CircleSlash2 };
  }
  return (
    appointmentVisuals[appointment.location_type as keyof typeof appointmentVisuals] ??
    appointmentVisuals.other
  );
}

function appointmentEnd(appointment: FieldCalendarAppointment) {
  if (appointment.scheduled_end_at) return new Date(appointment.scheduled_end_at);
  return new Date(new Date(appointment.scheduled_start_at).getTime() + 60 * 60 * 1000);
}

function appointmentDurationMinutes(appointment: FieldCalendarAppointment) {
  const start = new Date(appointment.scheduled_start_at).getTime();
  return Math.max(15, Math.round((appointmentEnd(appointment).getTime() - start) / 60_000));
}

function appointmentTimeRange(appointment: FieldCalendarAppointment) {
  return `${timeLabel(appointment.scheduled_start_at)} – ${timeLabel(appointmentEnd(appointment).toISOString())}`;
}

function appointmentBlockStyle(appointment: FieldCalendarAppointment): CSSProperties {
  return {
    "--appointment-block-height": `${Math.max(
      54,
      appointmentDurationMinutes(appointment) * 0.8,
    )}px`,
  } as CSSProperties;
}

function rangeFor(mode: CalendarMode, cursor: Date) {
  if (mode === "month") {
    const startsAt = startOfMonthGrid(cursor);
    return { startsAt, endsAt: addDays(startsAt, 42) };
  }
  if (mode === "week") {
    const startsAt = startOfWeek(cursor);
    return { startsAt, endsAt: addDays(startsAt, 7) };
  }
  if (mode === "agenda") {
    const startsAt = startOfDay(cursor);
    return { startsAt, endsAt: addDays(startsAt, 30) };
  }
  const startsAt = startOfDay(cursor);
  return { startsAt, endsAt: addDays(startsAt, 1) };
}

function calendarTitle(mode: CalendarMode, cursor: Date) {
  if (mode === "month") {
    return new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric" }).format(cursor);
  }
  if (mode === "week") {
    const start = startOfWeek(cursor);
    const end = addDays(start, 6);
    return `${start.toLocaleDateString("en-US", { month: "short", day: "numeric" })} – ${end.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}`;
  }
  if (mode === "agenda") {
    const end = addDays(startOfDay(cursor), 29);
    return `${cursor.toLocaleDateString("en-US", { month: "short", day: "numeric" })} – ${end.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}`;
  }
  return cursor.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

function shiftCursor(mode: CalendarMode, cursor: Date, direction: number) {
  const result = new Date(cursor);
  if (mode === "month") result.setMonth(result.getMonth() + direction);
  else result.setDate(result.getDate() + direction * (mode === "week" ? 7 : mode === "agenda" ? 30 : 1));
  return result;
}

function AppointmentButton({
  appointment,
  compact = false,
  onOpen,
}: {
  appointment: FieldCalendarAppointment;
  compact?: boolean;
  onOpen: (appointment: FieldCalendarAppointment) => void;
}) {
  const visual = appointmentVisual(appointment);
  const Icon = visual.icon;
  const className = `${compact ? styles.compactCalendarEvent : styles.calendarEvent} ${styles[visual.className]}`;
  const timeRange = appointmentTimeRange(appointment);
  return (
    <button
      aria-label={`${visual.label} appointment, ${labelize(appointment.appointment_type)}, ${appointment.seller_name}, ${timeRange}`}
      className={className}
      onClick={() => onOpen(appointment)}
      style={compact ? undefined : appointmentBlockStyle(appointment)}
      title={`${visual.label} - ${labelize(appointment.appointment_type)} - ${timeRange}`}
      type="button"
    >
      <span className={styles.eventTime}>
        <Icon aria-hidden="true" size={compact ? 10 : 13} />
        {compact ? timeLabel(appointment.scheduled_start_at) : timeRange}
      </span>
      <strong>{appointment.seller_name}</strong>
      {!compact ? (
        <>
          <small className={styles.eventPurpose}>{labelize(appointment.appointment_type)}</small>
          <small><MapPin aria-hidden="true" size={12} />{appointment.property_address}</small>
          <small><UserRound aria-hidden="true" size={12} />{appointment.closer_name}</small>
        </>
      ) : null}
    </button>
  );
}

export function FieldCalendar({
  data,
  onOpenMeeting,
  onSchedule,
}: {
  data: FieldOperationsOverview;
  onOpenMeeting: (appointmentId: string) => void;
  onSchedule: (startsAt?: Date) => void;
}) {
  const { request } = useFieldApi();
  const [mode, setMode] = useState<CalendarMode>("month");
  const [cursor, setCursor] = useState(() => new Date());
  const [ownerId, setOwnerId] = useState("");
  const [appointments, setAppointments] = useState<FieldCalendarAppointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const range = useMemo(() => rangeFor(mode, cursor), [cursor, mode]);

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams({
      starts_at: range.startsAt.toISOString(),
      ends_at: range.endsAt.toISOString(),
    });
    if (ownerId) params.set("owner_user_id", ownerId);
    setLoading(true);
    setError("");
    request<{ appointments: FieldCalendarAppointment[] }>(
      `/api/v1/field-operations/calendar?${params}`,
    )
      .then((payload) => {
        if (active) setAppointments(payload.appointments);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Calendar unavailable.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [ownerId, range.endsAt, range.startsAt, request]);

  const open = (appointment: FieldCalendarAppointment) => onOpenMeeting(appointment.id);
  const days = useMemo(
    () =>
      Array.from({ length: mode === "month" ? 42 : 7 }, (_, index) =>
        addDays(mode === "month" ? range.startsAt : startOfWeek(cursor), index),
      ),
    [cursor, mode, range.startsAt],
  );

  return (
    <section className={styles.calendarShell}>
      <header className={styles.calendarToolbar}>
        <div className={styles.calendarNavigation}>
          <button
            aria-label="Previous calendar period"
            onClick={() => setCursor((value) => shiftCursor(mode, value, -1))}
            title="Previous"
            type="button"
          >
            <ChevronLeft size={17} />
          </button>
          <button className={styles.todayButton} onClick={() => setCursor(new Date())} type="button">
            Today
          </button>
          <button
            aria-label="Next calendar period"
            onClick={() => setCursor((value) => shiftCursor(mode, value, 1))}
            title="Next"
            type="button"
          >
            <ChevronRight size={17} />
          </button>
          <h3>{calendarTitle(mode, cursor)}</h3>
        </div>
        <div className={styles.calendarControls}>
          <button
            className={styles.calendarScheduleButton}
            onClick={() => onSchedule(cursor)}
            type="button"
          >
            <Plus size={15} />
            Schedule
          </button>
          {data.can_manage ? (
            <label>
              <UserRound size={15} />
              <select
                aria-label="Filter calendar by closer"
                onChange={(event) => setOwnerId(event.target.value)}
                value={ownerId}
              >
                <option value="">All closers</option>
                {data.users.map((user) => (
                  <option key={user.id} value={user.id}>{user.name}</option>
                ))}
              </select>
            </label>
          ) : null}
          <div className={styles.calendarModes} aria-label="Calendar display" role="group">
            {(["month", "week", "day", "agenda"] as const).map((item) => (
              <button
                className={mode === item ? styles.activeMode : ""}
                key={item}
                onClick={() => setMode(item)}
                type="button"
              >
                {labelize(item)}
              </button>
            ))}
          </div>
        </div>
      </header>

      <div className={styles.calendarLegend} aria-label="Appointment color legend">
        {Object.values(appointmentVisuals).map((item) => {
          const Icon = item.icon;
          return (
            <span className={styles[item.className]} key={item.label}>
              <Icon aria-hidden="true" size={12} />
              {item.label}
            </span>
          );
        })}
        <span className={styles.eventCancelled}>
          <CircleSlash2 aria-hidden="true" size={12} />
          Cancelled
        </span>
      </div>

      {error ? <p className={styles.error}>{error}</p> : null}
      {loading ? <div className={styles.calendarLoading}>Loading calendar…</div> : null}

      {!loading && mode === "month" ? (
        <div className={styles.monthCalendar}>
          {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => (
            <div className={styles.weekday} key={day}>{day}</div>
          ))}
          {days.map((day) => {
            const items = appointments.filter((item) => sameDay(new Date(item.scheduled_start_at), day));
            return (
              <div
                className={`${styles.monthDay} ${day.getMonth() !== cursor.getMonth() ? styles.outsideMonth : ""} ${sameDay(day, new Date()) ? styles.today : ""}`}
                key={day.toISOString()}
              >
                <button
                  aria-label={`Show ${day.toLocaleDateString()}`}
                  className={styles.dayNumber}
                  onClick={() => { setCursor(day); setMode("day"); }}
                  type="button"
                >
                  {day.getDate()}
                </button>
                {items.length === 0 ? (
                  <button
                    aria-label={`Schedule an appointment on ${day.toLocaleDateString()}`}
                    className={styles.emptyDaySchedule}
                    onClick={() => onSchedule(day)}
                    title="Schedule appointment"
                    type="button"
                  >
                    <Plus size={13} />
                    Schedule
                  </button>
                ) : null}
                <div className={styles.monthEvents}>
                  {items.slice(0, 3).map((item) => (
                    <AppointmentButton appointment={item} compact key={item.id} onOpen={open} />
                  ))}
                  {items.length > 3 ? (
                    <button className={styles.moreEvents} onClick={() => { setCursor(day); setMode("day"); }} type="button">
                      +{items.length - 3} more
                    </button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      ) : null}

      {!loading && mode === "week" ? (
        <div className={styles.weekCalendar}>
          {days.map((day) => {
            const items = appointments.filter((item) => sameDay(new Date(item.scheduled_start_at), day));
            return (
              <section className={sameDay(day, new Date()) ? styles.currentWeekDay : ""} key={day.toISOString()}>
                <button className={styles.weekDayHeader} onClick={() => { setCursor(day); setMode("day"); }} type="button">
                  <span>{day.toLocaleDateString("en-US", { weekday: "short" })}</span>
                  <strong>{day.getDate()}</strong>
                </button>
                <div className={styles.weekEvents}>
                  {items.map((item) => <AppointmentButton appointment={item} key={item.id} onOpen={open} />)}
                  {!items.length ? (
                    <button
                      className={styles.noEventsSchedule}
                      onClick={() => onSchedule(day)}
                      type="button"
                    >
                      <Plus size={13} />
                      Schedule
                    </button>
                  ) : null}
                </div>
              </section>
            );
          })}
        </div>
      ) : null}

      {!loading && mode === "day" ? (
        <div className={styles.dayAgenda}>
          <button
            className={styles.dayScheduleButton}
            onClick={() => onSchedule(cursor)}
            type="button"
          >
            <Plus size={15} />
            Schedule on this day
          </button>
          {appointments.map((appointment) => (
            <AppointmentButton appointment={appointment} key={appointment.id} onOpen={open} />
          ))}
          {!appointments.length ? <p className={styles.empty}>No field meetings scheduled for this day.</p> : null}
        </div>
      ) : null}

      {!loading && mode === "agenda" ? (
        <div className={styles.agendaCalendar}>
          {appointments
            .slice()
            .sort(
              (left, right) =>
                new Date(left.scheduled_start_at).getTime() -
                new Date(right.scheduled_start_at).getTime(),
            )
            .map((appointment, index, sorted) => {
              const appointmentDate = new Date(appointment.scheduled_start_at);
              const visual = appointmentVisual(appointment);
              const Icon = visual.icon;
              const previousDate = index
                ? new Date(sorted[index - 1]!.scheduled_start_at)
                : null;
              const showDate = !previousDate || !sameDay(appointmentDate, previousDate);
              return (
                <Fragment key={appointment.id}>
                  {showDate ? (
                    <h4>
                      {appointmentDate.toLocaleDateString("en-US", {
                        weekday: "long",
                        month: "long",
                        day: "numeric",
                      })}
                    </h4>
                  ) : null}
                  <button
                    aria-label={`${visual.label} appointment, ${labelize(appointment.appointment_type)}, ${appointment.seller_name}, ${appointmentTimeRange(appointment)}`}
                    className={`${styles.agendaEvent} ${styles[visual.className]}`}
                    onClick={() => open(appointment)}
                    title={`${visual.label} - ${labelize(appointment.appointment_type)}`}
                    type="button"
                  >
                    <time><Icon aria-hidden="true" size={13} />{appointmentTimeRange(appointment)}</time>
                    <span>
                      <strong>{appointment.seller_name}</strong>
                      <small><MapPin aria-hidden="true" size={14} />{appointment.property_address}</small>
                    </span>
                    <span>
                      <strong>{appointment.closer_name}</strong>
                      <small>{labelize(appointment.appointment_type)} · {labelize(appointment.status)}</small>
                    </span>
                    <CalendarDays aria-hidden="true" size={18} />
                  </button>
                </Fragment>
              );
            })}
          {!appointments.length ? (
            <p className={styles.empty}>No field meetings scheduled in the next 30 days.</p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
