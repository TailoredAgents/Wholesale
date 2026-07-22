"use client";

import { useRouter } from "next/navigation";

import type { FieldOperationsOverview } from "../../lib/api";
import { FieldCalendar } from "../field-operations/field-calendar";

export function CalendarWorkspace({ data }: { data: FieldOperationsOverview }) {
  const router = useRouter();

  return (
    <FieldCalendar
      data={data}
      onOpenMeeting={(appointmentId) =>
        router.push(
          `/os/field-operations?view=meetings&appointment=${encodeURIComponent(appointmentId)}`,
        )
      }
    />
  );
}
