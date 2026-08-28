import { getBuyer, getBuyers, getDashboardData, getWorkspaceProfile } from "../../lib/api";
import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { StatusBadge } from "../_components/design-system";
import { BuyersWorkspace } from "./buyers-workspace";

export const dynamic = "force-dynamic";

type BuyerSearchParams = {
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
  const params = {
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
      ownerUserId: params.owner,
      page: params.page,
      q: params.q,
      sourceKey: params.source,
      status: params.status,
    }),
    getWorkspaceProfile(),
  ]);
  const selectedBuyer = params.buyer && !buyerData.buyers.some((buyer) => buyer.id === params.buyer)
    ? await getBuyer(params.buyer)
    : null;
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
        key={`${params.q}|${params.status}|${params.owner}|${params.source}|${buyerData.page}|${params.buyer ?? ""}|${params.create ? "create" : "browse"}`}
        buyers={buyerData.buyers}
        apiError={buyerData.errorMessage}
        canEdit={Boolean(profile?.permissions.includes("buyers:edit"))}
        contractLeads={contractLeads}
        initialBuyerId={params?.buyer}
        initialCreate={params.create}
        initialFilters={{
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
        sourceOptions={buyerData.sourceOptions}
        initialTab={params?.tab}
        total={buyerData.total}
      />
    </WorkspacePage>
  );
}
