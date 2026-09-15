import { Archive, CircleOff } from "lucide-react";
import Link from "next/link";

import {
  getAcquisitionOperations,
  getDashboardData,
  getUnderwritingCalibration,
  getWorkspaceProfile,
} from "../../lib/api";
import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { normalizeLeadSortKey, normalizeLeadViewKey } from "../os-utils";
import { LeadsWorkspace } from "./leads-workspace";
import { NewLeadControl } from "./new-lead-control";
import { SellerLeadsNav, type SellerLeadsView } from "./seller-leads-nav";
import { SellerTodayWorkspace } from "./seller-today-workspace";
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
    ["today", "queue"].includes(requestedView)
      ? "today"
      : requestedView === "underwriting"
        ? "underwriting"
        : "database";

  const [dashboard, profile, { operations }, calibrationResult] = await Promise.all([
    getDashboardData(),
    getWorkspaceProfile(),
    getAcquisitionOperations(),
    operationalView === "underwriting"
      ? getUnderwritingCalibration()
      : Promise.resolve({ calibration: null, apiConnected: true }),
  ]);

  const canEditLead = Boolean(profile?.permissions.includes("leads:edit"));
  const canRecordOutsideOffer = Boolean(profile?.permissions.includes("leads:edit"));
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
    activeView === "today"
      ? "Today"
      : activeView === "underwriting"
        ? "Underwriting Queue"
        : "Leads";
  const description =
    activeView === "today"
      ? "Handle real seller activity, scheduled reminders, and today’s appointments without manufactured busywork."
      : activeView === "underwriting"
        ? "Prepare defensible values and offers for qualified seller opportunities."
        : "Search, filter, assign, and move every active seller opportunity from one database.";

  return (
    <WorkspacePage wide={display === "board"}>
      <PageHeader
        actions={
          <>
            {canEditLead && profile ? (
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

      {activeView === "today" ? (
        <SellerTodayWorkspace
          appointments={operations?.appointments ?? []}
          initialLeadId={first(params.lead)}
          leads={dashboard.leads}
          notifications={operations?.notifications ?? []}
          profile={profile}
          tasks={dashboard.openTaskQueue}
        />
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
          canEditLead={canEditLead}
          canImportExecutedContract={canImportExecutedContract}
          canRecordOutsideOffer={canRecordOutsideOffer}
          key={`leads-${display}`}
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
