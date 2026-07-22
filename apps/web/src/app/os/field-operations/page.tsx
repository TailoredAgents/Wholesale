import { getFieldOperationsOverview } from "../../lib/api";
import { AcquisitionJourney } from "../_components/acquisition-journey";
import { PageHeader, SectionPanel, WorkspacePage } from "../_components/page-contracts";
import { FieldOperationsWorkspace } from "./field-operations-workspace";

export const dynamic = "force-dynamic";

const fieldViews = new Set(["dispatch", "calendar", "meetings", "capacity"]);

export default async function FieldOperationsPage({
  searchParams,
}: {
  searchParams: Promise<{ appointment?: string; lead?: string; view?: string }>;
}) {
  const params = await searchParams;
  const { fieldOperations, apiConnected } = await getFieldOperationsOverview();
  const initialView = fieldViews.has(params.view ?? "")
    ? (params.view as "dispatch" | "calendar" | "meetings" | "capacity")
    : "dispatch";

  return (
    <WorkspacePage>
      <PageHeader
        description="Seller appointment dispatch, closer capacity, meeting preparation, property evidence, and visit outcomes."
        eyebrow="Appointment execution"
        meta={apiConnected ? "Capacity current" : "API unavailable"}
        title="Field Operations"
      />
      <AcquisitionJourney active="field-operations" />

      {fieldOperations ? (
        <FieldOperationsWorkspace
          data={fieldOperations}
          initialAppointmentId={params.appointment ?? ""}
          initialLeadId={params.lead ?? ""}
          initialView={initialView}
        />
      ) : (
        <SectionPanel description="An acquisitions or management role is required." title="Field dispatch unavailable">
          <div />
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}
