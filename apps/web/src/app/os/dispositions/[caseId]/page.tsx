import Link from "next/link";

import {
  getDealOverview,
  getDispositionOverview,
  getWorkspaceProfile,
} from "../../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../../_components/page-contracts";
import { StatusBadge } from "../../_components/design-system";
import {
  DispositionWorkspace,
  type DispositionWorkspaceTab,
} from "../disposition-workspace";

export const dynamic = "force-dynamic";

const workspaceTabs = new Set<DispositionWorkspaceTab>([
  "overview",
  "package",
  "buyers",
  "execution",
  "outreach",
  "offers",
  "provider",
  "reconciliation",
]);

export default async function DispositionDealPage({
  params,
  searchParams,
}: {
  params: Promise<{ caseId: string }>;
  searchParams: Promise<{ dispositionTab?: string; tab?: string }>;
}) {
  const [{ caseId }, query, dispositionResult, dealResult, profile] = await Promise.all([
    params,
    searchParams,
    getDispositionOverview(),
    getDealOverview(),
    getWorkspaceProfile(),
  ]);
  const dispositionCase = dispositionResult.dispositions?.cases.find((item) => item.id === caseId) ?? null;
  const deal = dealResult.deals?.items.find((item) => item.disposition_case_id === caseId) ?? null;
  const requestedTab = query.tab ?? query.dispositionTab;
  const initialTab = workspaceTabs.has(requestedTab as DispositionWorkspaceTab)
    ? requestedTab as DispositionWorkspaceTab
    : "overview";
  const canManageOutreach = Boolean(profile?.permissions.includes("dispositions:manage_outreach"));
  const canApproveOutreach = Boolean(profile?.permissions.includes("dispositions:approve_outreach"));
  const canViewOutreach = Boolean(
    profile?.permissions.includes("buyers:view")
      && (canManageOutreach || canApproveOutreach),
  );
  const connected = dispositionResult.apiConnected && dealResult.apiConnected && Boolean(profile);

  if (!dispositionCase || !deal || !dispositionResult.dispositions) {
    return (
      <WorkspacePage>
        <PageHeader
          actions={<Link href="/os/deals?view=disposition">Back to disposition desk</Link>}
          description="The selected buyer-placement case could not be loaded from the current workspace scope."
          eyebrow="Operations / dispositions"
          meta={<StatusBadge tone="danger">Workspace unavailable</StatusBadge>}
          title="Disposition deal unavailable"
        />
        <SectionPanel description="Return to the desk and choose an active disposition deal." title="Deal not found">
          This case may have been completed, removed, or moved outside your current access scope.
        </SectionPanel>
      </WorkspacePage>
    );
  }

  return (
    <WorkspacePage>
      <PageHeader
        actions={<><Link href="/os/deals?view=disposition&desk=active_deals">Disposition desk</Link><Link href={`/os/deals?view=all&display=queue&deal=${deal.id}&tab=summary`}>Full deal record</Link></>}
        description={`${dispositionCase.asset_class === "land" ? "Land" : "House"} deal · ${dispositionCase.seller_name} · Work the packet, buyers, dialer, and outreach in any order.`}
        eyebrow="Dispositions / deal marketing"
        meta={<StatusBadge tone={connected ? "success" : "warning"}>{connected ? "Workspace current" : "Access needs review"}</StatusBadge>}
        title={dispositionCase.property_address}
      />
      <DispositionWorkspace
        canApproveBuyerSelection={Boolean(profile?.permissions.includes("dispositions:approve_buyer_selection"))}
        canApproveOutreach={canApproveOutreach}
        canEditBuyers={Boolean(profile?.permissions.includes("buyers:edit"))}
        canEditDeals={Boolean(profile?.permissions.includes("deals:edit"))}
        canManageOutreach={canManageOutreach}
        canSendBulk={Boolean(
          profile?.permissions.includes("dispositions:send_bulk_outreach")
            || profile?.permissions.includes("communications:send_bulk"),
        )}
        canViewOutreach={canViewOutreach}
        dealId={deal.id}
        initialCaseId={caseId}
        initialData={dispositionResult.dispositions}
        initialTab={initialTab}
        key={`${caseId}-${initialTab}`}
        variant="dedicated"
      />
    </WorkspacePage>
  );
}
