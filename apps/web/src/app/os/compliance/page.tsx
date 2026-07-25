import { getComplianceOverview, getWorkspaceProfile } from "../../lib/api";
import { ManagementJourney } from "../_components/management-journey";
import { ManagementSummaryStrip } from "../_components/management-summary-strip";
import { StatusBadge } from "../_components/design-system";
import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { ComplianceWorkspace } from "./compliance-workspace";

export const dynamic = "force-dynamic";

export default async function CompliancePage() {
  const [{ compliance, apiConnected }, profile] = await Promise.all([
    getComplianceOverview(),
    getWorkspaceProfile(),
  ]);
  const activePolicies =
    compliance?.policies.filter((policy) => policy.status === "active").length ?? 0;
  const openIncidents =
    compliance?.incidents.filter((incident) => incident.status === "open").length ?? 0;
  const currentDnc = compliance?.dnc_sources.some((source) => source.is_current) ?? false;
  const pendingTraining =
    compliance?.training_records.filter((record) => record.status !== "approved").length ??
    0;

  return (
    <WorkspacePage>
      <PageHeader
        description="Approve communication policy, retain DNC evidence, manage training, and inspect operating controls."
        eyebrow="Control / outreach governance"
        meta={
          <StatusBadge tone={apiConnected ? "success" : "danger"}>
            {apiConnected ? "Audit connected" : "Unavailable"}
          </StatusBadge>
        }
        title="Compliance"
      />
      <ManagementJourney active="compliance" />
      <ManagementSummaryStrip
        authority={{
          label: "Authority",
          value: profile?.permissions.includes("operating_model:manage")
            ? "Owner controlled"
            : "Read restricted",
          detail: "Policy decisions create audit records",
          tone: "success",
        }}
        comparison={{
          label: "Active policy",
          value: `${activePolicies}/6 active`,
          detail: "External legal review is required before activation",
          tone: activePolicies === 6 ? "success" : "warning",
        }}
        exception={{
          label: "Open incidents",
          value: String(openIncidents),
          detail: openIncidents ? "Review unresolved outreach issues" : "No open exceptions",
          tone: openIncidents ? "danger" : "success",
        }}
        nextAction={{
          label: "DNC evidence",
          value: currentDnc ? "Current" : "Refresh required",
          detail: "Maximum operating interval is 31 days",
          tone: currentDnc ? "success" : "warning",
        }}
        period={{
          label: "Training",
          value: pendingTraining ? `${pendingTraining} pending` : "Current",
          detail: "Staff completion and manager approval",
          tone: pendingTraining ? "warning" : "neutral",
        }}
      />
      {compliance ? (
        <ComplianceWorkspace compliance={compliance} />
      ) : (
        <p>Owner-level compliance access is required.</p>
      )}
    </WorkspacePage>
  );
}
