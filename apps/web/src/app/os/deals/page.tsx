import {
  getDealOverview,
  getDispositionDesk,
  getDispositionOverview,
  getTransactionOverview,
  getWorkspaceProfile,
} from "../../lib/api";
import type { DispositionDeskCategory } from "../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../_components/page-contracts";
import { StatusBadge } from "../_components/design-system";
import { DealsWorkspace } from "./deals-workspace";
import { DispositionDeskWorkspace } from "./disposition-desk-workspace";
import styles from "./deals.module.css";

export const dynamic = "force-dynamic";

export default async function DealsPage({
  searchParams,
}: {
  searchParams: Promise<{
    deal?: string;
    desk?: string;
    deskPage?: string;
    display?: string;
    dispositionTab?: string;
    scope?: string;
    tab?: string;
    view?: string;
  }>;
}) {
  const params = await searchParams;
  const dispositionScope = params.scope === "team" ? "team" : "mine";

  if (params.view === "disposition") {
    const deskCategories = new Set<DispositionDeskCategory>([
      "today",
      "active_deals",
      "buyer_follow_ups",
      "replies",
      "offers",
      "deadlines",
    ]);
    const selectedDesk = deskCategories.has(params.desk as DispositionDeskCategory)
      ? params.desk as DispositionDeskCategory
      : "today";
    const parsedPage = Number.parseInt(params.deskPage ?? "1", 10);
    const deskPage = Number.isSafeInteger(parsedPage) && parsedPage > 0 ? parsedPage : 1;
    const dispositionDeskResult = await getDispositionDesk(
      dispositionScope,
      selectedDesk,
      (deskPage - 1) * 100,
    );
    const deskStatus = !dispositionDeskResult.apiConnected
      ? { label: "Disposition desk unavailable", tone: "danger" as const }
      : dispositionDeskResult.isStale
        ? { label: "Disposition desk needs refresh", tone: "warning" as const }
        : { label: "Disposition desk current", tone: "success" as const };

    return (
      <WorkspacePage>
        <PageHeader
          description="Prioritize buyer placement, replies, offers, follow-ups, and deadlines from one daily desk."
          eyebrow="Operations / disposition"
          meta={
            <StatusBadge tone={deskStatus.tone}>{deskStatus.label}</StatusBadge>
          }
          title="Deals"
        />
        <DispositionDeskWorkspace
          apiConnected={dispositionDeskResult.apiConnected}
          data={dispositionDeskResult.desk}
          errorMessage={dispositionDeskResult.errorMessage}
          initialDesk={selectedDesk}
          initialPage={deskPage}
          isStale={dispositionDeskResult.isStale}
        />
      </WorkspacePage>
    );
  }

  const transactionTabs = new Set(["contract", "closing", "documents", "parties", "timeline"]);
  const dispositionTabs = new Set(["disposition", "finance"]);
  const [dealResult, transactionResult, dispositionResult, profile] = await Promise.all([
    getDealOverview(),
    transactionTabs.has(params.tab ?? "")
      ? getTransactionOverview()
      : Promise.resolve({ transactions: null, apiConnected: true }),
    dispositionTabs.has(params.tab ?? "")
      ? getDispositionOverview()
      : Promise.resolve({ dispositions: null, apiConnected: true }),
    getWorkspaceProfile(),
  ]);
  const connected = dealResult.apiConnected && transactionResult.apiConnected && dispositionResult.apiConnected;
  const profileAvailable = profile !== null;
  const canViewDisposition = Boolean(
    profile?.permissions.includes("deals:view") &&
    profile.permissions.includes("buyers:view"),
  );
  const canManageOutreach = Boolean(
    profile?.permissions.includes("dispositions:manage_outreach"),
  );
  const canApproveOutreach = Boolean(
    profile?.permissions.includes("dispositions:approve_outreach"),
  );
  const canViewOutreach = Boolean(
    profile?.permissions.includes("buyers:view") &&
    (canManageOutreach || canApproveOutreach),
  );

  return (
    <WorkspacePage>
      <PageHeader
        description="Run contract, closing, buyer placement, and financial handoff from one deal record."
        eyebrow="Operations / contract to funding"
        meta={
          <StatusBadge tone={!profileAvailable || !connected ? "danger" : "success"}>
            {!profileAvailable
              ? "Access profile unavailable"
              : connected
                ? "Deal queue current"
                : "Deal data unavailable"}
          </StatusBadge>
        }
        title="Deals"
      />
      {!profileAvailable ? (
        <div className={styles.profileWarning} role="alert">
          <strong>Workspace access could not be verified.</strong>
          <span>Deal data may remain visible, but editing and disposition navigation are disabled until the access profile reloads.</span>
        </div>
      ) : null}
      {dealResult.deals ? (
        <DealsWorkspace
          canApproveOutreach={canApproveOutreach}
          canEditBuyers={Boolean(profile?.permissions.includes("buyers:edit"))}
          canEditDeals={Boolean(profile?.permissions.includes("deals:edit"))}
          canManageOutreach={canManageOutreach}
          canSendBulk={Boolean(profile?.permissions.includes("communications:send_bulk"))}
          canViewDisposition={canViewDisposition}
          canViewOutreach={canViewOutreach}
          initialDealId={params.deal}
          initialDisplay={params.display}
          initialDispositionTab={params.dispositionTab}
          initialTab={params.tab}
          initialView={params.view}
          deals={dealResult.deals}
          dispositions={dispositionResult.dispositions}
          transactions={transactionResult.transactions}
        />
      ) : (
        <SectionPanel description="A deal-access role and an available API connection are required." title="Deal workspace unavailable">
          The server did not return the unified deal record.
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}
