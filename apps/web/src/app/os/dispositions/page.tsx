import { redirect } from "next/navigation";

import { getDealOverview, getDispositionOverview } from "../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../_components/page-contracts";
import { StatusBadge } from "../_components/design-system";
import { DispositionSetupWorkspace } from "./disposition-setup-workspace";

export const dynamic = "force-dynamic";

export default async function DispositionsPage({
  searchParams,
}: {
  searchParams: Promise<{ case?: string; transaction?: string }>;
}) {
  const [params, dispositionResult, dealResult] = await Promise.all([
    searchParams,
    getDispositionOverview(),
    getDealOverview(),
  ]);
  if (params.case) {
    redirect(`/os/dispositions/${encodeURIComponent(params.case)}`);
  }

  const dealIdByTransaction = Object.fromEntries(
    (dealResult.deals?.items ?? []).map((item) => [item.transaction_id, item.id]),
  );
  const connected = dispositionResult.apiConnected && dealResult.apiConnected;

  return (
    <WorkspacePage>
      <PageHeader
        description="Recover or manually start buyer placement for an executed purchase agreement. Ongoing work stays in the dedicated outreach desk."
        eyebrow="Deals / setup"
        meta={<StatusBadge tone={connected ? "success" : "danger"}>{connected ? "Eligible contracts current" : "Setup unavailable"}</StatusBadge>}
        title="Open disposition case"
      />
      {dispositionResult.dispositions ? (
        <DispositionSetupWorkspace
          canViewPrivateEconomics={dispositionResult.dispositions.can_view_private_economics}
          dealIdByTransaction={dealIdByTransaction}
          eligibleTransactions={dispositionResult.dispositions.eligible_transactions}
          initialTransactionId={params.transaction}
        />
      ) : (
        <SectionPanel description="A disposition-access role and an available API connection are required." title="Disposition setup unavailable">
          The server did not return eligible contracted deals.
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}
