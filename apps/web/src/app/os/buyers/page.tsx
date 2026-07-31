import { getBuyers, getDashboardData, getWorkspaceProfile } from "../../lib/api";
import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { StatusBadge } from "../_components/design-system";
import { BuyersWorkspace } from "./buyers-workspace";

export const dynamic = "force-dynamic";

export default async function BuyersPage({
  searchParams,
}: {
  searchParams?: Promise<{ buyer?: string; tab?: string }>;
}) {
  const params = await searchParams;
  const [dashboard, buyerData, profile] = await Promise.all([
    getDashboardData(),
    getBuyers(),
    getWorkspaceProfile(),
  ]);
  const contractLeads = dashboard.leads.filter((lead) =>
    ["under_contract", "closed"].includes(lead.stage_key),
  );

  return (
    <WorkspacePage>
      <PageHeader
        description="Qualify buyer evidence, compare purchasing criteria, and keep the active deal pool ready."
        eyebrow="Deal flow / buyer evidence"
        meta={<StatusBadge tone={buyerData.apiConnected ? "success" : "danger"}>{buyerData.apiConnected ? `${buyerData.buyers.length} buyer records` : "Buyer CRM unavailable"}</StatusBadge>}
        title="Buyers"
      />
      <BuyersWorkspace
        buyers={buyerData.buyers}
        canEdit={Boolean(profile?.permissions.includes("buyers:edit"))}
        contractLeads={contractLeads}
        initialBuyerId={params?.buyer}
        initialTab={params?.tab}
      />
    </WorkspacePage>
  );
}
