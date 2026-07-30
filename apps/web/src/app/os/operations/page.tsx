import { getAcquisitionOperations, getDashboardData } from "../../lib/api";
import { ManagementJourney } from "../_components/management-journey";
import { PageHeader, SectionPanel, WorkspacePage } from "../_components/page-contracts";
import {
  OperationsWorkspace,
  type OperationsTab,
} from "./operations-workspace";

export const dynamic = "force-dynamic";

const operationsTabs = new Set<OperationsTab>([
  "today",
  "structure",
  "calling",
  "team",
  "quality",
  "follow-up",
]);

export default async function AcquisitionOperationsPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const params = await searchParams;
  const initialTab = operationsTabs.has(params.tab as OperationsTab)
    ? (params.tab as OperationsTab)
    : "team";
  const [{ operations, apiConnected }, dashboard] = await Promise.all([
    getAcquisitionOperations(),
    getDashboardData(),
  ]);

  return (
    <WorkspacePage>
      <PageHeader
        description="Employee accounts, access, team structure, operational configuration, and quality controls."
        eyebrow="Workspace management"
        meta={apiConnected ? "Live operations" : "API unavailable"}
        title="Team & Access"
      />
      <ManagementJourney active="team-access" />

      {operations ? (
        <OperationsWorkspace
          initialTab={initialTab}
          key={initialTab}
          leads={dashboard.leads}
          operations={operations}
        />
      ) : (
        <SectionPanel description="Check API authentication and deployment status." title="Operations unavailable">
          <div />
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}
