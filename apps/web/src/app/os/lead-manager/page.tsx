import { getLeadManagerOverview } from "../../lib/api";
import { AcquisitionJourney } from "../_components/acquisition-journey";
import { PageHeader, SectionPanel, WorkspacePage } from "../_components/page-contracts";
import { LeadManagerWorkspace } from "./lead-manager-workspace";

export const dynamic = "force-dynamic";

export default async function LeadManagerPage({
  searchParams,
}: {
  searchParams: Promise<{ lead?: string }>;
}) {
  const params = await searchParams;
  const { leadManager, apiConnected } = await getLeadManagerOverview();

  return (
    <WorkspacePage>
      <PageHeader
        description="Today's warm handoffs, seller qualification, follow-up, appointments, and neglected-lead exceptions."
        eyebrow="Warm lead operations"
        meta={apiConnected ? "Queue current" : "API unavailable"}
        title="Lead Desk"
      />
      <AcquisitionJourney active="lead-manager" />

      {leadManager ? (
        <LeadManagerWorkspace data={leadManager} initialLeadId={params.lead ?? ""} />
      ) : (
        <SectionPanel description="An acquisitions or management role is required." title="Lead Desk unavailable">
          <div />
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}
