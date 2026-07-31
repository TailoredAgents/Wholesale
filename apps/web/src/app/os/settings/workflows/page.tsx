import { getAcquisitionOperations, getDashboardData } from "../../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../../_components/page-contracts";
import { OperationsWorkspace } from "../../operations/operations-workspace";
import { requireSettingsSection } from "../section-access";

export const dynamic = "force-dynamic";

export default async function WorkflowSettingsPage() {
  await requireSettingsSection("workflows");
  const [{ operations, apiConnected }, dashboard] = await Promise.all([
    getAcquisitionOperations(),
    getDashboardData(),
  ]);
  return (
    <WorkspacePage>
      <PageHeader
        description="Create and maintain approved follow-up plans used by the operating team."
        eyebrow="Settings"
        meta={apiConnected ? "Live workflow controls" : "API unavailable"}
        title="Workflows"
      />
      {operations ? (
        <OperationsWorkspace
          initialTab="follow-up"
          leads={dashboard.leads}
          operations={operations}
          showMetrics={false}
          showTabs={false}
        />
      ) : (
        <SectionPanel description="Check API authentication and deployment status." title="Workflow settings unavailable">
          <div />
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}

