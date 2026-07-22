import { getProspectingWorkbench } from "../../lib/api";
import { AcquisitionJourney } from "../_components/acquisition-journey";
import { PageHeader, SectionPanel, WorkspacePage } from "../_components/page-contracts";
import { ProspectingWorkspace } from "./prospecting-workspace";

export const dynamic = "force-dynamic";

export default async function ProspectingPage() {
  const { prospecting, apiConnected } = await getProspectingWorkbench();

  return (
    <WorkspacePage>
      <PageHeader
        description="Assigned outreach, call outcomes, qualification evidence, callbacks, and warm handoff."
        eyebrow="Caller execution"
        meta={apiConnected ? "Assigned records only" : "API unavailable"}
        title="Prospecting"
      />
      <AcquisitionJourney active="prospecting" />

      {prospecting ? (
        <ProspectingWorkspace
          data={prospecting}
          key={
            prospecting.current_entry
              ? `${prospecting.current_entry.id}:${prospecting.current_entry.status}:${prospecting.current_entry.attempt_count}:${prospecting.current_entry.active_attempt?.id ?? "ready"}`
              : `empty:${prospecting.queue.ready}:${prospecting.queue.completed}`
          }
        />
      ) : (
        <SectionPanel description="An assigned caller or acquisition-management role is required." title="Prospecting workbench unavailable">
          <div />
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}
