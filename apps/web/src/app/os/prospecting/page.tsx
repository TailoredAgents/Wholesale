import { ArrowRight, Headphones, RefreshCw, ShieldCheck } from "lucide-react";

import {
  getBatchDialerAgentMappings,
  getBatchDialerCampaignMappings,
  getBatchDialerVaPerformance,
  getWorkspaceProfile,
} from "../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../_components/page-contracts";
import { BatchDialerVaPerformanceSection } from "./batchdialer-va-performance";
import styles from "./prospecting.module.css";

export const dynamic = "force-dynamic";

function BatchDialerBoundary({ canManage }: { canManage: boolean }) {
  return (
    <section className={styles.batchDialerBoundary} aria-labelledby="batchdialer-boundary-title">
      <header>
        <div>
          <span>Approved calling path</span>
          <h2 id="batchdialer-boundary-title">Cold calling happens in BatchDialer</h2>
          <p>
            BatchDialer owns campaigns, dialing, number rotation, calling cadence, and cold-call
            results. Stonegate receives the supported results and becomes the CRM once a seller
            qualifies.
          </p>
        </div>
        <strong>
          <ShieldCheck aria-hidden="true" size={17} /> One production dialer
        </strong>
      </header>

      <ol className={styles.batchDialerFlow}>
        <li>
          <Headphones aria-hidden="true" size={18} />
          <div>
            <span>1. Call</span>
            <strong>Work the assigned campaign in BatchDialer</strong>
            <p>Use the provider&apos;s queue, phone numbers, scripts, and cadence.</p>
          </div>
        </li>
        <li>
          <RefreshCw aria-hidden="true" size={18} />
          <div>
            <span>2. Sync</span>
            <strong>Record the truthful result there</strong>
            <p>Stonegate retrieves supported call records and evidence through the direct API.</p>
          </div>
        </li>
        <li>
          <ArrowRight aria-hidden="true" size={18} />
          <div>
            <span>3. Continue</span>
            <strong>Work qualified sellers in Stonegate</strong>
            <p>Accepted handoffs enter Leads; appointment claims create visible review work.</p>
          </div>
        </li>
      </ol>

      <div className={styles.batchDialerBoundaryNote}>
        <strong>No duplicate dialing or call disposition is required in Stonegate.</strong>
        <span>
          Stonegate&apos;s regular phone remains available for individual seller, buyer, attorney, and
          relationship conversations. It is not a cold-calling power dialer.
        </span>
        {!canManage ? (
          <span>
            As a caller, complete your assigned cold-calling work in BatchDialer. Return to
            Stonegate only for CRM work that has been handed off to you.
          </span>
        ) : null}
      </div>
    </section>
  );
}

export default async function ProspectingPage() {
  const profile = await getWorkspaceProfile();
  const canManage = Boolean(profile?.permissions.includes("operations:manage"));
  const [performanceResult, agentMappingsResult, campaignMappingsResult] = canManage
    ? await Promise.all([
        getBatchDialerVaPerformance(),
        getBatchDialerAgentMappings(),
        getBatchDialerCampaignMappings(),
      ])
    : [
        { vaPerformance: null, apiConnected: true },
        { agentMappings: null, apiConnected: true },
        { campaignMappings: null, apiConnected: true },
      ];
  const connected =
    performanceResult.apiConnected &&
    agentMappingsResult.apiConnected &&
    campaignMappingsResult.apiConnected;

  return (
    <WorkspacePage>
      <PageHeader
        description="Run seller cold outreach in BatchDialer, then monitor synchronized results and qualified handoffs in Stonegate."
        eyebrow="Seller prospecting"
        meta={canManage ? (connected ? "BatchDialer data connected" : "BatchDialer sync needs attention") : "BatchDialer calling workflow"}
        title="Prospecting"
      />

      <BatchDialerBoundary canManage={canManage} />

      {canManage ? (
        <BatchDialerVaPerformanceSection
          initialApiConnected={performanceResult.apiConnected && agentMappingsResult.apiConnected}
          initialData={performanceResult.vaPerformance}
          initialMappings={agentMappingsResult.agentMappings}
          initialCampaignMappings={campaignMappingsResult.campaignMappings}
          initialCampaignMappingsAvailable={campaignMappingsResult.apiConnected}
        />
      ) : (
        <SectionPanel
          description="Stonegate does not maintain a second calling queue. Your assigned campaign, next number, and cold-call disposition stay in BatchDialer."
          title="Your calling workspace is BatchDialer"
        >
          <div className={styles.batchDialerStaffInstruction}>
            <strong>Finish the call and select its result in BatchDialer.</strong>
            <p>
              Qualified sellers and supported appointment claims synchronize into Stonegate for
              the appropriate CRM owner. You do not need to recreate the call here.
            </p>
          </div>
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}
