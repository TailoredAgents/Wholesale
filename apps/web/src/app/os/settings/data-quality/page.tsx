import {
  getAcquisitionOperations,
  getDashboardData,
  getUnderwritingCalibration,
  getWorkspaceProfile,
} from "../../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../../_components/page-contracts";
import { OperationsWorkspace } from "../../operations/operations-workspace";
import { requireSettingsSection } from "../section-access";
import { UnderwritingQuality } from "./underwriting-quality";

export const dynamic = "force-dynamic";

export default async function DataQualitySettingsPage() {
  await requireSettingsSection("data-quality");
  const profile = await getWorkspaceProfile();
  const canManageRecords = Boolean(
    profile?.permissions.includes("operations:manage") ||
      profile?.permissions.includes("records:delete_or_archive") ||
      profile?.permissions.includes("audit:view"),
  );
  const canReviewValuation = Boolean(
    profile?.permissions.includes("underwriting:edit") ||
      profile?.permissions.includes("underwriting:approve_arv"),
  );
  const [{ operations, apiConnected }, dashboard, calibrationResult] = await Promise.all([
    getAcquisitionOperations(),
    getDashboardData(),
    canReviewValuation
      ? getUnderwritingCalibration()
      : Promise.resolve({ calibration: null, apiConnected: true }),
  ]);
  return (
    <WorkspacePage>
      <PageHeader
        description="Review duplicate records and monitor the evidence quality behind Stonegate valuations."
        eyebrow="Settings"
        meta={apiConnected ? "Live quality queue" : "API unavailable"}
        title="Data & Quality"
      />
      {canManageRecords && operations ? (
        <OperationsWorkspace
          initialTab="quality"
          leads={dashboard.leads}
          operations={operations}
          showMetrics={false}
          showTabs={false}
        />
      ) : canManageRecords ? (
        <SectionPanel description="Check API authentication and deployment status." title="Data quality unavailable">
          <div />
        </SectionPanel>
      ) : null}
      {canReviewValuation && calibrationResult.calibration ? (
        <UnderwritingQuality calibration={calibrationResult.calibration} />
      ) : canReviewValuation ? (
        <SectionPanel
          description="The calibration API is unavailable or no valuation evidence can be loaded."
          title="Valuation quality unavailable"
        >
          <div />
        </SectionPanel>
      ) : null}
    </WorkspacePage>
  );
}
