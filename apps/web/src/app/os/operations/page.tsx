import { getAcquisitionOperations, getDashboardData } from "../../lib/api";
import { AcquisitionJourney } from "../_components/acquisition-journey";
import { PageHeader, SectionPanel, WorkspacePage } from "../_components/page-contracts";
import { OperationsWorkspace } from "./operations-workspace";

export const dynamic = "force-dynamic";

export default async function AcquisitionOperationsPage() {
  const [{ operations, apiConnected }, dashboard] = await Promise.all([
    getAcquisitionOperations(),
    getDashboardData(),
  ]);

  return (
    <WorkspacePage>
      <PageHeader
        description="Acquisition capacity, assignments, team controls, quality, and execution exceptions."
        eyebrow="Acquisition management"
        meta={apiConnected ? "Live operations" : "API unavailable"}
        title="Operations"
      />
      <AcquisitionJourney active="operations" />

      {operations ? (
        <OperationsWorkspace leads={dashboard.leads} operations={operations} />
      ) : (
        <SectionPanel description="Check API authentication and deployment status." title="Operations unavailable">
          <div />
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}
