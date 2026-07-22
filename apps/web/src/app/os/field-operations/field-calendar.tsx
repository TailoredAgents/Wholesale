"use client";

/* eslint-disable react-hooks/set-state-in-effect */

import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  MapPin,
  UserRound,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { FieldCalendarAppointment, FieldOperationsOverview } from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./field-operations.module.css";
import { useFieldApi } from "./use-field-api";

type CalendarMode = "month" | "week" | "day";

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

function rangeFor(mode: CalendarMode, cursor: Date) {
  if (mode === "month") {
    const startsAt = startOfMonthGrid(cursor);
    return { startsAt, endsAt: addDays(startsAt, 42) };
  }
  if (mode === "week") {
    const startsAt = startOfWeek(cursor);
    return { startsAt, endsAt: addDays(startsAt, 7) };
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
  else result.setDate(result.getDate() + direction * (mode === "week" ? 7 : 1));
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
  return (
    <button
      className={compact ? styles.compactCalendarEvent : styles.calendarEvent}
      onClick={() => onOpen(appointment)}
      title={`Open ${appointment.seller_name}'s meeting workspace`}
      type="button"
    >
      <span>{timeLabel(appointment.scheduled_start_at)}</span>
      <strong>{appointment.seller_name}</strong>
      {!compact ? <small>{appointment.property_address}</small> : null}
    </button>
  );
}

export function FieldCalendar({
  data,
  onOpenMeeting,
}: {
  data: FieldOperationsOverview;
  onOpenMeeting: (appointmentId: string) => void;
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
          {data.can_manage ? (
            <label>
              <UserRound size={15} />
              <select onChange={(event) => setOwnerId(event.target.value)} value={ownerId}>
                <option value="">All closers</option>
                {data.users.map((user) => (
                  <option key={user.id} value={user.id}>{user.name}</option>
                ))}
              </select>
            </label>
          ) : null}
          <div className={styles.calendarModes} aria-label="Calendar display" role="group">
            {(["month", "week", "day"] as const).map((item) => (
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
                  {!items.length ? <span className={styles.noEvents}>No meetings</span> : null}
                </div>
              </section>
            );
          })}
        </div>
      ) : null}

      {!loading && mode === "day" ? (
        <div className={styles.dayAgenda}>
          {appointments.map((appointment) => (
            <button key={appointment.id} onClick={() => open(appointment)} type="button">
              <time>{timeLabel(appointment.scheduled_start_at)}</time>
              <span>
                <strong>{appointment.seller_name}</strong>
                <small><MapPin size={14} />{appointment.property_address}</small>
                <small><UserRound size={14} />{appointment.closer_name} · {labelize(appointment.field_status)}</small>
              </span>
              <CalendarDays size={18} />
            </button>
          ))}
          {!appointments.length ? <p className={styles.empty}>No field meetings scheduled for this day.</p> : null}
        </div>
      ) : null}
    </section>
  );
}
