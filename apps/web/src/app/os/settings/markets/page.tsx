import {
  getAcquisitionOperations,
  getDashboardData,
  getOperatingModelOverview,
} from "../../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../../_components/page-contracts";
import { OperatingModelWorkspace } from "../../operating-model/operating-model-workspace";
import { OperationsWorkspace } from "../../operations/operations-workspace";
import { requireSettingsSection } from "../section-access";

export const dynamic = "force-dynamic";

export default async function MarketSettingsPage() {
  await requireSettingsSection("markets");
  const [{ operations, apiConnected }, { operatingModel }, dashboard] = await Promise.all([
    getAcquisitionOperations(),
    getOperatingModelOverview(),
    getDashboardData(),
  ]);

  return (
    <WorkspacePage>
      <PageHeader
        description="Control service areas, territory ownership, and evidence required before expansion."
        eyebrow="Settings"
        meta={apiConnected ? "Live market controls" : "API unavailable"}
        title="Markets & Territories"
      />
      {operations ? (
        <OperationsWorkspace
          initialTab="structure"
          leads={dashboard.leads}
          operations={operations}
          showMetrics={false}
          showTabs={false}
          structureScope="markets"
        />
      ) : (
        <SectionPanel description="Check API authentication and deployment status." title="Market settings unavailable">
          <div />
        </SectionPanel>
      )}
      {operatingModel && operations?.markets.length ? (
        <OperatingModelWorkspace
          initialTab="launches"
          leads={dashboard.leads}
          operatingModel={operatingModel}
          showMetrics={false}
          showTabs={false}
        />
      ) : null}
    </WorkspacePage>
  );
}
