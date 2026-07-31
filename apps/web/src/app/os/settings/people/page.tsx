import { getAcquisitionOperations, getDashboardData } from "../../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../../_components/page-contracts";
import { OperationsWorkspace } from "../../operations/operations-workspace";
import { requireSettingsSection } from "../section-access";

export const dynamic = "force-dynamic";

export default async function PeopleSettingsPage() {
  await requireSettingsSection("people");
  const [{ operations, apiConnected }, dashboard] = await Promise.all([
    getAcquisitionOperations(),
    getDashboardData(),
  ]);

  return (
    <WorkspacePage>
      <PageHeader
        description="Manage employee accounts, role access, calling eligibility, and functional teams."
        eyebrow="Settings"
        meta={apiConnected ? "Live access controls" : "API unavailable"}
        title="People & Access"
      />
      {operations ? (
        <OperationsWorkspace
          initialTab="team"
          leads={dashboard.leads}
          operations={operations}
          showMetrics={false}
          showTabs={false}
        />
      ) : (
        <SectionPanel description="Check API authentication and deployment status." title="People settings unavailable">
          <div />
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}

