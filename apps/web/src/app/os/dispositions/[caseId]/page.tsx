import Link from "next/link";

import {
  getDispositionCase,
  getWorkspaceProfileResult,
} from "../../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../../_components/page-contracts";
import { StatusBadge } from "../../_components/design-system";
import { WorkspaceRecovery } from "../../_components/workspace-recovery";
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
  const [{ caseId }, query] = await Promise.all([params, searchParams]);
  const [dispositionResult, profileResult] = await Promise.all([
    getDispositionCase(caseId),
    getWorkspaceProfileResult(),
  ]);
  const requestedTab = query.tab ?? query.dispositionTab;
  const initialTab = workspaceTabs.has(requestedTab as DispositionWorkspaceTab)
    ? requestedTab as DispositionWorkspaceTab
    : "execution";
  const profile = profileResult.profile;

  if (!dispositionResult.dispositionCase || !dispositionResult.apiConnected) {
    return (
      <WorkspacePage>
        <PageHeader
          actions={<Link href="/os/deals?view=disposition">Disposition desk</Link>}
          description="Stonegate is preserving this deal address while the API reconnects."
          eyebrow="Operations / dispositions"
          meta={<StatusBadge tone="warning">Reconnecting</StatusBadge>}
          title="Disposition workspace temporarily unavailable"
        />
        <WorkspaceRecovery
          autoRetry={dispositionResult.connectionState === "unavailable"}
          detail={dispositionResult.errorMessage}
          title={dispositionResult.connectionState === "unauthorized"
            ? "Disposition access could not be verified"
            : undefined}
        />
      </WorkspacePage>
    );
  }

  if (!profile) {
    return (
      <WorkspacePage>
        <PageHeader
          actions={<Link href="/os/deals?view=disposition">Disposition desk</Link>}
          description="The deal loaded, but Stonegate is waiting to verify your workspace permissions."
          eyebrow="Operations / dispositions"
          meta={<StatusBadge tone="warning">Verifying access</StatusBadge>}
          title="Disposition workspace temporarily unavailable"
        />
        <WorkspaceRecovery
          autoRetry={profileResult.connectionState === "unavailable"}
          detail={profileResult.errorMessage}
          title={profileResult.connectionState === "unauthorized"
            ? "Disposition access could not be verified"
            : undefined}
        />
      </WorkspacePage>
    );
  }

  const dispositionCase = dispositionResult.dispositionCase;
  const canManageOutreach = Boolean(profile?.permissions.includes("dispositions:manage_outreach"));
  const canApproveOutreach = Boolean(profile?.permissions.includes("dispositions:approve_outreach"));
  const canViewOutreach = Boolean(profile?.permissions.includes("dispositions:view"));

  if (!dispositionCase) {
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
    <WorkspacePage wide>
      <PageHeader
        actions={<><Link href="/os/deals?view=disposition&desk=active_deals&scope=team">Disposition desk</Link>{profile?.permissions.includes("deals:view") ? <Link href={`/os/deals?view=all&display=queue&deal=${dispositionCase.deal_id}&tab=summary`}>Full deal record</Link> : null}</>}
        description={`${dispositionCase.asset_class === "land" ? "Land" : "House"} deal for ${dispositionCase.seller_name}. Work the ranked investor queue; packet and offer tools remain available.`}
        eyebrow="Dispositions / deal marketing"
        meta={<StatusBadge tone="success">Workspace current</StatusBadge>}
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
        dealId={dispositionCase.deal_id}
        initialCaseId={caseId}
        initialData={{
          can_view_private_economics: profile.permissions.includes("dispositions:view_private_economics"),
          metrics: {
            active_cases: dispositionCase.status === "closed" || dispositionCase.status === "cancelled" ? 0 : 1,
            packages_pending: dispositionCase.package_status === "approved" ? 0 : 1,
            buyer_selected: dispositionCase.selected_buyer_id ? 1 : 0,
            reconciliation_pending: dispositionCase.reconciliation?.status === "draft" ? 1 : 0,
            below_margin_target: dispositionCase.reconciliation
              && dispositionCase.reconciliation.company_margin_basis_points
                < dispositionCase.reconciliation.target_margin_basis_points ? 1 : 0,
          },
          eligible_transactions: [],
          cases: [dispositionCase],
        }}
        initialTab={initialTab}
        key={`${caseId}-${initialTab}`}
        variant="dedicated"
      />
    </WorkspacePage>
  );
}
