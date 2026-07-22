"use client";

import { AlertTriangle, ArrowRight, CalendarClock, Clock3, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import type { FieldOperationsOverview } from "../../lib/api";
import { FieldCalendar } from "../field-operations/field-calendar";
import { formatDateTime } from "../os-utils";
import styles from "./calendar.module.css";

export function CalendarWorkspace({ data }: { data: FieldOperationsOverview }) {
  const router = useRouter();
  const nextAppointments = data.upcoming_appointments.slice(0, 5);

  return (
    <div className={styles.layout}>
      <aside className={styles.summary} aria-label="Schedule summary">
        <header>
          <p>Today</p>
          <h2>Schedule status</h2>
        </header>
        <div className={styles.metrics}>
          <div>
            <CalendarClock aria-hidden="true" size={16} />
            <span>Appointments</span>
            <strong>{data.metrics.appointments_today}</strong>
          </div>
          <div>
            <Clock3 aria-hidden="true" size={16} />
            <span>Ready to schedule</span>
            <strong>{data.metrics.ready_to_schedule}</strong>
          </div>
          <div data-warning={data.metrics.unassigned_today > 0}>
            <UserRound aria-hidden="true" size={16} />
            <span>Unassigned today</span>
            <strong>{data.metrics.unassigned_today}</strong>
          </div>
          <div data-warning={data.metrics.at_capacity_today > 0}>
            <AlertTriangle aria-hidden="true" size={16} />
            <span>At capacity</span>
            <strong>{data.metrics.at_capacity_today}</strong>
          </div>
        </div>
        <section className={styles.upcoming}>
          <div>
            <h3>Coming up</h3>
            <Link href="/os/field-operations?view=dispatch">Dispatch <ArrowRight size={13} /></Link>
          </div>
          {nextAppointments.map((appointment) => (
            <button
              key={appointment.id}
              onClick={() =>
                router.push(
                  `/os/field-operations?view=meetings&appointment=${encodeURIComponent(appointment.id)}`,
                )
              }
              type="button"
            >
              <span>{formatDateTime(appointment.scheduled_start_at)}</span>
              <strong>{appointment.seller_name}</strong>
              <small>{appointment.closer_name}</small>
            </button>
          ))}
          {!nextAppointments.length ? <p>No upcoming seller meetings.</p> : null}
        </section>
      </aside>

      <main className={styles.calendarArea}>
        <FieldCalendar
          data={data}
          onOpenMeeting={(appointmentId) =>
            router.push(
              `/os/field-operations?view=meetings&appointment=${encodeURIComponent(appointmentId)}`,
            )
          }
        />
      </main>
    </div>
  );
}
