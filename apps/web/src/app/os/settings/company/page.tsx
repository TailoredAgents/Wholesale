import { getDashboardData, getOperatingModelOverview } from "../../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../../_components/page-contracts";
import { OperatingModelWorkspace } from "../../operating-model/operating-model-workspace";
import { requireSettingsSection } from "../section-access";

export const dynamic = "force-dynamic";

export default async function CompanySettingsPage() {
  await requireSettingsSection("company");
  const [{ operatingModel, apiConnected }, dashboard] = await Promise.all([
    getOperatingModelOverview(),
    getDashboardData(),
  ]);

  return (
    <WorkspacePage>
      <PageHeader
        description="Define company seats, approved counterparties, and role readiness."
        eyebrow="Settings"
        meta={apiConnected ? "Live company controls" : "API unavailable"}
        title="Company"
      />
      {operatingModel ? (
        <OperatingModelWorkspace
          initialTab="setup"
          leads={dashboard.leads}
          operatingModel={operatingModel}
          showTabs={false}
        />
      ) : (
        <SectionPanel description="Check API authentication and deployment status." title="Company settings unavailable">
          <div />
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}

