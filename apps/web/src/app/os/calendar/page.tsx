import {
  getFieldAppointmentWorkspace,
  getFieldOperationsOverview,
} from "../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../_components/page-contracts";
import { FieldOperationsWorkspace } from "../field-operations/field-operations-workspace";

export const dynamic = "force-dynamic";

type CalendarView = "calendar" | "dispatch" | "meetings" | "capacity";
type SearchValue = string | string[] | undefined;

function first(value: SearchValue) {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function normalizeView(value: string): CalendarView {
  if (value === "dispatch") return "dispatch";
  if (value === "appointment" || value === "meetings") return "meetings";
  if (value === "availability" || value === "capacity") return "capacity";
  return "calendar";
}

export default async function CalendarPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, SearchValue>>;
}) {
  const params = (await searchParams) ?? {};
  const appointmentId = first(params.appointment);
  const initialView = appointmentId ? "meetings" : normalizeView(first(params.view));
  const [{ fieldOperations, apiConnected }, initialWorkspace] = await Promise.all([
    getFieldOperationsOverview(),
    appointmentId
      ? getFieldAppointmentWorkspace(appointmentId)
      : Promise.resolve(null),
  ]);
  const permittedView =
    initialView === "capacity" && !fieldOperations?.can_manage ? "calendar" : initialView;
  const title =
    permittedView === "dispatch"
      ? "Appointment Dispatch"
      : permittedView === "meetings"
        ? "Appointment Workspace"
        : permittedView === "capacity"
          ? "Availability"
          : "Calendar";
  const description =
    permittedView === "dispatch"
      ? "Schedule qualified sellers with the right closer, territory, capacity, and travel buffer."
      : permittedView === "meetings"
        ? "Prepare, inspect, present, negotiate, record the outcome, and complete approved in-person signing."
        : permittedView === "capacity"
          ? "Manage closer working hours, appointment capacity, territories, and unavailable time."
          : "Coordinate seller meetings, closer capacity, and field preparation from one internal schedule.";

  return (
    <WorkspacePage>
      <PageHeader
        description={description}
        eyebrow="Appointments"
        meta={apiConnected ? "Schedule current" : "API unavailable"}
        title={title}
      />
      {fieldOperations ? (
        <FieldOperationsWorkspace
          basePath="/os/calendar"
          data={fieldOperations}
          initialAppointmentId={appointmentId}
          initialLeadId={first(params.lead)}
          initialWorkspace={initialWorkspace}
          initialView={permittedView}
        />
      ) : (
        <SectionPanel
          description="An acquisitions or management role is required."
          title="Calendar unavailable"
        >
          <div />
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}
