import {
  getBuyer,
  getBuyerProfile,
  getBuyers,
  getDashboardData,
  getWorkspaceProfile,
} from "../../lib/api";
import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { StatusBadge } from "../_components/design-system";
import { BuyersWorkspace } from "./buyers-workspace";

export const dynamic = "force-dynamic";

type BuyerSearchParams = {
  asset?: string | string[];
  buyer?: string | string[];
  create?: string | string[];
  owner?: string | string[];
  page?: string | string[];
  q?: string | string[];
  returnTo?: string | string[];
  source?: string | string[];
  status?: string | string[];
  tab?: string | string[];
};

function firstValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

function positivePage(value: string | undefined) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}

export default async function BuyersPage({
  searchParams,
}: {
  searchParams?: Promise<BuyerSearchParams>;
}) {
  const rawParams = await searchParams;
  const requestedReturnTo = firstValue(rawParams?.returnTo);
  const asset: "" | "house" | "land" | "both" = (["house", "land", "both"] as const).find(
      (asset) => asset === firstValue(rawParams?.asset),
    ) ?? "";
  const params = {
    asset,
    buyer: firstValue(rawParams?.buyer),
    create: firstValue(rawParams?.create) === "1",
    owner: firstValue(rawParams?.owner) ?? "",
    page: positivePage(firstValue(rawParams?.page)),
    q: firstValue(rawParams?.q) ?? "",
    returnTo: requestedReturnTo?.startsWith("/os/") ? requestedReturnTo : undefined,
    source: firstValue(rawParams?.source) ?? "",
    status: firstValue(rawParams?.status) ?? "",
    tab: firstValue(rawParams?.tab),
  };
  const [dashboard, buyerData, profile] = await Promise.all([
    getDashboardData(),
    getBuyers({
      assetClass: params.asset,
      ownerUserId: params.owner,
      page: params.page,
      q: params.q,
      sourceKey: params.source,
      status: params.status,
    }),
    getWorkspaceProfile(),
  ]);
  const selectedBuyerId = params.buyer ?? buyerData.buyers[0]?.id;
  const buyerProfileResult = selectedBuyerId
    ? await getBuyerProfile(selectedBuyerId)
    : { profile: null, errorMessage: null };
  const buyerProfile = buyerProfileResult.profile;
  const selectedBuyer = buyerProfile?.buyer ?? (
    params.buyer && !buyerData.buyers.some((buyer) => buyer.id === params.buyer)
      ? await getBuyer(params.buyer)
      : null
  );
  const contractLeads = dashboard.leads.filter((lead) =>
    ["under_contract", "closed"].includes(lead.stage_key),
  );

  return (
    <WorkspacePage>
      <PageHeader
        description="Qualify buyer evidence, compare purchasing criteria, and keep the active deal pool ready."
        eyebrow="Deal flow / buyer evidence"
        meta={<StatusBadge tone={buyerData.apiConnected ? "success" : "danger"}>{buyerData.apiConnected ? `${buyerData.total} matching buyer${buyerData.total === 1 ? "" : "s"}` : "Buyer CRM unavailable"}</StatusBadge>}
        title="Buyers"
      />
      <BuyersWorkspace
        key={`${params.q}|${params.status}|${params.owner}|${params.source}|${params.asset}|${buyerData.page}|${selectedBuyerId ?? ""}|${params.create ? "create" : "browse"}`}
        buyers={buyerData.buyers}
        apiError={buyerData.errorMessage}
        canEdit={Boolean(profile?.permissions.includes("buyers:edit"))}
        canManageProof={Boolean(profile?.permissions.includes("buyers:manage_proof"))}
        canViewProof={Boolean(profile?.permissions.includes("buyers:view_proof"))}
        contractLeads={contractLeads}
        initialBuyerId={params?.buyer}
        initialCreate={params.create}
        initialFilters={{
          asset: params.asset,
          owner: params.owner,
          q: params.q,
          source: params.source,
          status: params.status,
        }}
        page={buyerData.page}
        pageSize={buyerData.pageSize}
        relationshipOwners={buyerData.relationshipOwners}
        returnTo={params.returnTo}
        selectedBuyer={selectedBuyer}
        selectedProfile={buyerProfile}
        profileError={buyerProfileResult.errorMessage}
        sourceOptions={buyerData.sourceOptions}
        initialTab={params?.tab}
        total={buyerData.total}
      />
    </WorkspacePage>
  );
}
