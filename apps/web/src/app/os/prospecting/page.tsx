import { ListChecks, Megaphone, SlidersHorizontal } from "lucide-react";
import Link from "next/link";

import {
  getAcquisitionOperations,
  getCampaignManagementOverview,
  getProspectingDialerOperations,
  getProspectingInboundCallbacks,
  getProspectingWorkbench,
  getWorkspaceProfile,
} from "../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../_components/page-contracts";
import { CampaignManagementWorkspace } from "../campaigns/campaign-management-workspace";
import { ProspectingDialerControl } from "./prospecting-dialer-control";
import { ProspectingWorkspace } from "./prospecting-workspace";
import styles from "./prospecting.module.css";

export const dynamic = "force-dynamic";

type ProspectingView = "campaigns" | "dialer-control" | "my-calls";

export default async function ProspectingPage({
  searchParams,
}: {
  searchParams?: Promise<{
    campaign?: string | string[];
    campaignView?: string | string[];
    view?: string | string[];
  }>;
}) {
  const params = await searchParams;
  const profile = await getWorkspaceProfile();
  const canManage = Boolean(profile?.permissions.includes("operations:manage"));
  const requestedView = Array.isArray(params?.view) ? params.view[0] : params?.view;
  const view: ProspectingView = canManage
    ? requestedView === "my-calls" ||
      requestedView === "campaigns" ||
      requestedView === "dialer-control"
      ? requestedView
      : "campaigns"
    : "my-calls";
  const campaignId = Array.isArray(params?.campaign) ? params.campaign[0] : params?.campaign;
  const campaignView = Array.isArray(params?.campaignView)
    ? params.campaignView[0]
    : params?.campaignView;
  const [
    { prospecting, apiConnected },
    campaignResult,
    operationsResult,
    dialerOperationsResult,
    callbackResult,
  ] =
    await Promise.all([
      view === "my-calls" || (canManage && view === "dialer-control")
        ? getProspectingWorkbench()
        : Promise.resolve({ prospecting: null, apiConnected: true }),
      canManage && (view === "campaigns" || view === "dialer-control")
        ? getCampaignManagementOverview()
        : Promise.resolve({ campaignManagement: null, apiConnected: true }),
      canManage && view === "campaigns"
        ? getAcquisitionOperations()
        : Promise.resolve({ operations: null, apiConnected: true }),
      canManage && view === "dialer-control"
        ? getProspectingDialerOperations()
        : Promise.resolve({ dialerOperations: null, apiConnected: true }),
      view === "my-calls"
        ? getProspectingInboundCallbacks()
        : Promise.resolve({ callbacks: null, apiConnected: true }),
    ]);
  const campaignManagement = campaignResult.campaignManagement;
  const operations = operationsResult.operations;
  const dialerOperations = dialerOperationsResult.dialerOperations;
  const callbacks = callbackResult.callbacks;
  const connected =
    apiConnected &&
    campaignResult.apiConnected &&
    operationsResult.apiConnected &&
    dialerOperationsResult.apiConnected &&
    callbackResult.apiConnected;

  return (
    <WorkspacePage>
      <PageHeader
        description={
          view === "campaigns"
            ? "Create outreach campaigns, import prospect lists, assign calling work, and measure results."
            : view === "dialer-control"
              ? "Activate callers and campaigns, monitor live sessions, and recover stalled calling work safely."
              : "Work assigned prospects, handle callbacks, record call outcomes, and complete warm handoffs."
        }
        eyebrow={
          view === "campaigns"
            ? "Outreach management"
            : view === "dialer-control"
              ? "Dialer operations"
              : "Caller execution"
        }
        meta={connected ? (canManage ? "Campaigns and assigned calls" : "Assigned records only") : "API unavailable"}
        title="Prospecting"
      />
      <nav aria-label="Prospecting views" className={styles.hubNavigation}>
        {canManage ? (
          <>
            <Link
              aria-current={view === "campaigns" ? "page" : undefined}
              className={view === "campaigns" ? styles.activeHubNavigation : undefined}
              href="/os/prospecting?view=campaigns"
            >
              <Megaphone aria-hidden="true" size={16} />
              <span>Campaigns</span>
            </Link>
            <Link
              aria-current={view === "dialer-control" ? "page" : undefined}
              className={view === "dialer-control" ? styles.activeHubNavigation : undefined}
              href="/os/prospecting?view=dialer-control"
            >
              <SlidersHorizontal aria-hidden="true" size={16} />
              <span>Dialer control</span>
            </Link>
          </>
        ) : null}
        <Link
          aria-current={view === "my-calls" ? "page" : undefined}
          className={view === "my-calls" ? styles.activeHubNavigation : undefined}
          href="/os/prospecting?view=my-calls"
        >
          <ListChecks aria-hidden="true" size={16} />
          <span>My Calls</span>
          {prospecting?.queue.ready ? <strong>{prospecting.queue.ready}</strong> : null}
        </Link>
      </nav>

      {view === "campaigns" && canManage && campaignManagement && operations ? (
        <CampaignManagementWorkspace
          data={campaignManagement}
          initialCampaignId={campaignId}
          initialTab={campaignView}
          markets={operations.markets}
          territories={operations.territories}
        />
      ) : view === "campaigns" && canManage ? (
        <SectionPanel description="Campaign data could not be loaded from the API." title="Campaign management unavailable">
          <div />
        </SectionPanel>
      ) : view === "dialer-control" && canManage && dialerOperations ? (
        <ProspectingDialerControl
          cohortsAvailable={campaignResult.apiConnected && campaignManagement !== null}
          initialCohorts={campaignManagement?.cohorts ?? []}
          initialData={dialerOperations}
          scripts={prospecting?.scripts ?? []}
        />
      ) : view === "dialer-control" && canManage ? (
        <SectionPanel description="Dialer operations could not be loaded from the API." title="Dialer control unavailable">
          <div />
        </SectionPanel>
      ) : prospecting ? (
        <ProspectingWorkspace
          data={prospecting}
          initialCallbacks={callbacks ?? { items: [], total: 0 }}
          initialCallbacksAvailable={callbackResult.apiConnected && callbacks !== null}
          key={
            prospecting.current_entry
              ? `${prospecting.current_entry.id}:${prospecting.current_entry.status}:${prospecting.current_entry.attempt_count}:${prospecting.current_entry.active_attempt?.id ?? "ready"}`
              : `empty:${prospecting.queue.ready}:${prospecting.queue.completed}`
          }
        />
      ) : (
        <SectionPanel description="An assigned caller or acquisition-management role is required." title="Prospecting workbench unavailable">
          <div />
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}
