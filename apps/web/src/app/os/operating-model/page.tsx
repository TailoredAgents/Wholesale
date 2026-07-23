import { getDashboardData, getOperatingModelOverview, getWorkspaceProfile } from "../../lib/api";
import { ManagementJourney } from "../_components/management-journey";
import { ManagementSummaryStrip } from "../_components/management-summary-strip";
import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { StatusBadge } from "../_components/design-system";
import { OperatingModelWorkspace } from "./operating-model-workspace";

export const dynamic = "force-dynamic";

function percent(basisPoints: number) {
  return `${(basisPoints / 100).toFixed(1)}%`;
}

export default async function OperatingModelPage() {
  const [{ operatingModel, apiConnected }, dashboard, profile] = await Promise.all([
    getOperatingModelOverview(),
    getDashboardData(),
    getWorkspaceProfile(),
  ]);
  const activePlan = operatingModel?.compensation_plans.find((plan) => plan.status === "active");
  const draftPlans = operatingModel?.compensation_plans.filter((plan) => plan.status === "draft") ?? [];
  const pendingCredits = operatingModel?.role_credits.filter((credit) => credit.status === "proposed") ?? [];
  const blockedLaunches = operatingModel?.launch_checklists.filter((checklist) => checklist.status === "blocked") ?? [];
  const pendingDecisions = draftPlans.length + pendingCredits.length;
  const canManage = Boolean(profile?.permissions.includes("operating_model:manage"));
  const primaryException = blockedLaunches.length
    ? `${blockedLaunches.length} market launch${blockedLaunches.length === 1 ? "" : "es"} blocked`
    : pendingDecisions
      ? `${pendingDecisions} decision${pendingDecisions === 1 ? "" : "s"} pending`
      : "No policy exception";

  return (
    <WorkspacePage>
      <PageHeader
        description="Control compensation policy, contribution decisions, and evidence-based market expansion."
        eyebrow="Business / policy control"
        meta={<StatusBadge tone={apiConnected ? "success" : "danger"}>{apiConnected ? "Versioned and auditable" : "Operating model unavailable"}</StatusBadge>}
        title="Operating Model"
      />
      <ManagementJourney active="operating-model" />
      <ManagementSummaryStrip
        authority={{ label: "Authority", value: canManage ? "Owner policy control" : "No management authority", detail: "Activations and decisions remain audited", tone: canManage ? "success" : "warning" }}
        comparison={{ label: "Company target", value: activePlan ? percent(activePlan.target_company_margin_basis_points) : "Not established", detail: activePlan ? `${activePlan.name} v${activePlan.version_number}` : "Activate a reviewed policy", tone: activePlan ? "success" : "warning" }}
        exception={{ label: "Primary exception", value: primaryException, detail: blockedLaunches[0]?.market_name ?? (pendingDecisions ? "Review pending policy work" : "Current controls are clear"), tone: blockedLaunches.length ? "danger" : pendingDecisions ? "warning" : "success" }}
        nextAction={{ label: "Management next step", value: blockedLaunches.length ? "Resolve launch evidence" : pendingDecisions ? "Review pending decisions" : "Monitor active policy", detail: "Changes create a new audit record", tone: "info" }}
        period={{ label: "Policy basis", value: activePlan ? `Active version ${activePlan.version_number}` : "No active version", detail: activePlan?.effective_start_at ? `Effective ${new Date(activePlan.effective_start_at).toLocaleDateString()}` : "Historical versions remain available", tone: "neutral" }}
      />

      {operatingModel ? (
        <OperatingModelWorkspace
          leads={dashboard.leads.filter((lead) => !lead.archived_at)}
          operatingModel={operatingModel}
        />
      ) : (
        <section>
          <p>Owner-level operating-model access is required.</p>
        </section>
      )}
    </WorkspacePage>
  );
}
