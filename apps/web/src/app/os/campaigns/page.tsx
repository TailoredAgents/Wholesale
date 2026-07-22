import { getCampaignManagementOverview } from "../../lib/api";
import { AcquisitionJourney } from "../_components/acquisition-journey";
import { PageHeader, SectionPanel, WorkspacePage } from "../_components/page-contracts";
import { CampaignManagementWorkspace } from "./campaign-management-workspace";

export const dynamic = "force-dynamic";

export default async function CampaignsPage() {
  const { campaignManagement, apiConnected } = await getCampaignManagementOverview();

  return (
    <WorkspacePage>
      <PageHeader
        description="Outreach campaigns, imported prospect data, suppression evidence, assignments, and cost control."
        eyebrow="Source preparation"
        meta={apiConnected ? "Screened and traceable" : "API unavailable"}
        title="Campaigns"
      />
      <AcquisitionJourney active="campaigns" />

      {campaignManagement ? (
        <CampaignManagementWorkspace data={campaignManagement} />
      ) : (
        <SectionPanel description="Acquisition-management access is required." title="Campaign management unavailable">
          <div />
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}
