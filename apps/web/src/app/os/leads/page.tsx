import { Archive, CircleOff } from "lucide-react";
import Link from "next/link";

import {
  getAcquisitionOperations,
  getDashboardData,
  getLeadManagerOverview,
  getUnderwritingCalibration,
  getWorkspaceProfile,
} from "../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../_components/page-contracts";
import { normalizeLeadSortKey, normalizeLeadViewKey } from "../os-utils";
import { LeadManagerWorkspace } from "../lead-manager/lead-manager-workspace";
import { LeadsWorkspace } from "./leads-workspace";
import { NewLeadControl } from "./new-lead-control";
import { SellerLeadsNav, type SellerLeadsView } from "./seller-leads-nav";
import { SellerUnderwritingWorkspace } from "./seller-underwriting-workspace";

export const dynamic = "force-dynamic";

type SearchValue = string | string[] | undefined;

function first(value: SearchValue) {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export default async function LeadsPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, SearchValue>>;
}) {
  const params = (await searchParams) ?? {};
  const requestedView = first(params.view);
  const requestedSavedView = normalizeLeadViewKey(requestedView);
  const requestedDisplay = first(params.display) === "board" ? "board" : "table";
  const requestedAsset = ["house", "land"].includes(first(params.asset))
    ? first(params.asset)
    : "all";
  const operationalView: SellerLeadsView =
    requestedView === "queue"
      ? "queue"
      : requestedView === "underwriting"
        ? "underwriting"
        : "database";

  const [dashboard, profile, { operations }, leadManagerResult, calibrationResult] =
    await Promise.all([
      getDashboardData(),
      getWorkspaceProfile(),
      getAcquisitionOperations(),
      operationalView === "queue"
        ? getLeadManagerOverview()
        : Promise.resolve({ leadManager: null, apiConnected: true }),
      operationalView === "underwriting"
        ? getUnderwritingCalibration()
        : Promise.resolve({ calibration: null, apiConnected: true }),
    ]);

  const canCreateLead = Boolean(profile?.permissions.includes("leads:edit"));
  const canImportExecutedContract = Boolean(
    profile?.permissions.includes("contracts:record_executed") ||
      profile?.permissions.includes("contracts:modify"),
  );
  const canUnderwrite = Boolean(
    profile?.permissions.includes("underwriting:edit") ||
      profile?.permissions.includes("underwriting:approve_arv"),
  );
  const activeView =
    operationalView === "underwriting" && !canUnderwrite ? "database" : operationalView;
  const display = activeView === "database" ? requestedDisplay : "table";
  const title =
    activeView === "queue"
      ? "Lead Queue"
      : activeView === "underwriting"
        ? "Underwriting Queue"
        : "Leads";
  const description =
    activeView === "queue"
      ? "Work warm handoffs, qualification, appointments, follow-up, and neglected-lead exceptions."
      : activeView === "underwriting"
        ? "Prepare defensible values and offers for qualified seller opportunities."
        : "Search, filter, assign, and move every active seller opportunity from one database.";

  return (
    <WorkspacePage>
      <PageHeader
        actions={
          <>
            {canCreateLead && profile ? (
              <NewLeadControl
                currentUserId={profile.user_id}
                initialOpen={first(params.new) === "lead"}
                users={operations?.users ?? []}
              />
            ) : null}
            <Link href="/os/leads/closed">
              <CircleOff aria-hidden="true" size={15} />
              Closed
            </Link>
            <Link href="/os/leads/archived">
              <Archive aria-hidden="true" size={15} />
              Archived
            </Link>
          </>
        }
        description={description}
        eyebrow="Seller operations"
        meta={`${dashboard.leads.length} active records`}
        title={title}
      />
      <SellerLeadsNav active={activeView} display={display} />

      {activeView === "queue" ? (
        leadManagerResult.leadManager ? (
          <LeadManagerWorkspace
            data={leadManagerResult.leadManager}
            initialLeadId={first(params.lead)}
          />
        ) : (
          <SectionPanel
            description="An acquisitions or management role is required."
            title="Lead queue unavailable"
          >
            <div />
          </SectionPanel>
        )
      ) : null}

      {activeView === "underwriting" ? (
        <SellerUnderwritingWorkspace
          calibration={calibrationResult.calibration}
          initialLeadId={first(params.lead)}
          leads={dashboard.leads}
        />
      ) : null}

      {activeView === "database" ? (
        <LeadsWorkspace
          canEditLead={canCreateLead}
          canImportExecutedContract={canImportExecutedContract}
          canRecordOutsideOffer={canCreateLead}
          initialDisplay={display}
          initialAsset={requestedAsset as "all" | "house" | "land"}
          initialLeadId={first(params.lead)}
          initialOwner={first(params.owner) || "all"}
          initialQuery={first(params.q)}
          initialSort={normalizeLeadSortKey(first(params.sort), requestedSavedView)}
          initialStage={first(params.stage) || "all"}
          initialView={requestedSavedView}
          leads={dashboard.leads}
          newPaidLeadCount={dashboard.summary.new_paid_leads}
          tasks={dashboard.openTaskQueue}
        />
      ) : null}
    </WorkspacePage>
  );
}
