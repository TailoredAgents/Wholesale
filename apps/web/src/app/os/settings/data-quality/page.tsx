import { getAcquisitionOperations, getDashboardData } from "../../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../../_components/page-contracts";
import { OperationsWorkspace } from "../../operations/operations-workspace";
import { requireSettingsSection } from "../section-access";

export const dynamic = "force-dynamic";

export default async function DataQualitySettingsPage() {
  await requireSettingsSection("data-quality");
  const [{ operations, apiConnected }, dashboard] = await Promise.all([
    getAcquisitionOperations(),
    getDashboardData(),
  ]);
  return (
    <WorkspacePage>
      <PageHeader
        description="Review possible duplicate records and protect the quality of company data."
        eyebrow="Settings"
        meta={apiConnected ? "Live quality queue" : "API unavailable"}
        title="Data & Quality"
      />
      {operations ? (
        <OperationsWorkspace
          initialTab="quality"
          leads={dashboard.leads}
          operations={operations}
          showMetrics={false}
          showTabs={false}
        />
      ) : (
        <SectionPanel description="Check API authentication and deployment status." title="Data quality unavailable">
          <div />
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}

