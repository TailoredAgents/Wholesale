import { Archive } from "lucide-react";
import Link from "next/link";

import {
  getAcquisitionOperations,
  getDashboardData,
  getWorkspaceProfile,
} from "../../lib/api";
import { AcquisitionJourney } from "../_components/acquisition-journey";
import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { normalizeLeadViewKey } from "../os-utils";
import { LeadsWorkspace } from "./leads-workspace";
import { NewLeadControl } from "./new-lead-control";

export const dynamic = "force-dynamic";

export default async function LeadsPage({
  searchParams,
}: {
  searchParams?: Promise<{ new?: string | string[]; view?: string | string[] }>;
}) {
  const params = await searchParams;
  const [dashboard, profile, { operations }] = await Promise.all([
    getDashboardData(),
    getWorkspaceProfile(),
    getAcquisitionOperations(),
  ]);
  const canCreateLead = Boolean(profile?.permissions.includes("leads:edit"));

  return (
    <WorkspacePage>
      <PageHeader
        actions={
          <>
            {canCreateLead && profile ? (
              <NewLeadControl
                currentUserId={profile.user_id}
                initialOpen={params?.new === "lead"}
                users={operations?.users ?? []}
              />
            ) : null}
            <Link href="/os/leads/archived">
              <Archive aria-hidden="true" size={15} />
              Archived Leads
            </Link>
          </>
        }
        description="The complete active seller database, independent of today's queue or pipeline stage."
        eyebrow="Seller system of record"
        meta={`${dashboard.leads.length} active records`}
        title="All Leads"
      />
      <AcquisitionJourney active="leads" />
      <LeadsWorkspace
        initialView={normalizeLeadViewKey(params?.view)}
        leads={dashboard.leads}
        newPaidLeadCount={dashboard.summary.new_paid_leads}
        tasks={dashboard.openTaskQueue}
      />
    </WorkspacePage>
  );
}
