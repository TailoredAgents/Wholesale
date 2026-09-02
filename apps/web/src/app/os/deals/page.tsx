import {
  getDealOverview,
  getDispositionDesk,
  getDispositionIntelligence,
  getDispositionOverview,
  getTransactionOverview,
  getWorkspaceProfile,
} from "../../lib/api";
import type { DispositionDeskCategory, DispositionIntelligenceQuery } from "../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../_components/page-contracts";
import { StatusBadge } from "../_components/design-system";
import { DealsWorkspace } from "./deals-workspace";
import { DispositionDeskWorkspace } from "./disposition-desk-workspace";
import { DispositionIntelligenceWorkspace } from "./disposition-intelligence-workspace";
import styles from "./deals.module.css";

export const dynamic = "force-dynamic";

export default async function DealsPage({
  searchParams,
}: {
  searchParams: Promise<{
    deal?: string;
    deal_id?: string;
    desk?: string;
    deskPage?: string;
    display?: string;
    dispositionTab?: string;
    buyer_id?: string;
    agent_user_id?: string;
    source?: string;
    market?: string;
    asset_class?: string;
    start_at?: string;
    end_at?: string;
    scope?: string;
    tab?: string;
    view?: string;
  }>;
}) {
  const params = await searchParams;
  const dispositionScope = params.scope === "team" ? "team" : "mine";

  if (params.view === "disposition") {
    if (params.desk === "performance") {
      const intelligenceFilters: DispositionIntelligenceQuery = {
        deal_id: params.deal_id,
        buyer_id: params.buyer_id,
        agent_user_id: params.agent_user_id,
        source: params.source,
        market: params.market,
        asset_class: params.asset_class,
        start_at: params.start_at,
        end_at: params.end_at,
      };
      const intelligenceResult = await getDispositionIntelligence(intelligenceFilters);
      const intelligenceState = intelligenceResult.intelligence?.data_state;
      const intelligenceStatus = !intelligenceResult.apiConnected
        ? { label: "Performance unavailable", tone: "danger" as const }
        : intelligenceState === "partial"
          ? { label: "Performance evidence partial", tone: "warning" as const }
          : intelligenceState === "unavailable"
            ? { label: "No performance evidence", tone: "danger" as const }
            : { label: "Performance evidence current", tone: "success" as const };

      return (
        <WorkspacePage>
          <PageHeader
            description="Understand completed disposition outcomes, buyer reliability, cycle time, source performance, and correction signals."
            eyebrow="Operations / dispositions / intelligence"
            meta={<StatusBadge tone={intelligenceStatus.tone}>{intelligenceStatus.label}</StatusBadge>}
            title="Dispositions"
          />
          <DispositionIntelligenceWorkspace
            apiConnected={intelligenceResult.apiConnected}
            data={intelligenceResult.intelligence}
            errorMessage={intelligenceResult.errorMessage}
            filters={intelligenceFilters}
          />
        </WorkspacePage>
      );
    }

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
          eyebrow="Operations / buyer placement"
          meta={
            <StatusBadge tone={deskStatus.tone}>{deskStatus.label}</StatusBadge>
          }
          title="Dispositions"
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
          canApproveBuyerSelection={Boolean(profile?.permissions.includes("dispositions:approve_buyer_selection"))}
          canApproveOutreach={canApproveOutreach}
          canEditBuyers={Boolean(profile?.permissions.includes("buyers:edit"))}
          canEditDeals={Boolean(profile?.permissions.includes("deals:edit"))}
          canManageOutreach={canManageOutreach}
          canRecordExecutedContract={Boolean(
            profile?.permissions.includes("contracts:record_executed") ||
              profile?.permissions.includes("contracts:modify"),
          )}
          canSendBulk={Boolean(
            profile?.permissions.includes("dispositions:send_bulk_outreach")
              || profile?.permissions.includes("communications:send_bulk"),
          )}
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
