import { getDashboardData, getOperatingModelOverview } from "../../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../../_components/page-contracts";
import { OperatingModelWorkspace } from "../../operating-model/operating-model-workspace";
import { requireSettingsSection } from "../section-access";

export const dynamic = "force-dynamic";

export default async function FinancePolicySettingsPage() {
  await requireSettingsSection("finance-policy");
  const [{ operatingModel, apiConnected }, dashboard] = await Promise.all([
    getOperatingModelOverview(),
    getDashboardData(),
  ]);
  return (
    <WorkspacePage>
      <PageHeader
        description="Control compensation policy, role-credit decisions, and version history."
        eyebrow="Settings"
        meta={apiConnected ? "Versioned and auditable" : "API unavailable"}
        title="Finance Policy"
      />
      {operatingModel ? (
        <OperatingModelWorkspace
          allowedTabs={["active", "credits", "history"]}
          initialTab="active"
          leads={dashboard.leads}
          operatingModel={operatingModel}
        />
      ) : (
        <SectionPanel description="Check API authentication and deployment status." title="Finance policy unavailable">
          <div />
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}

