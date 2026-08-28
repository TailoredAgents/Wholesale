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
  const selectedDeal = params.case
    ? dealResult.deals?.items.find((item) => item.disposition_case_id === params.case)
    : null;
  if (params.case) {
    const query = new URLSearchParams({ display: "queue", tab: "disposition", view: "all" });
    if (selectedDeal) query.set("deal", selectedDeal.id);
    redirect(`/os/deals?${query.toString()}`);
  }

  const dealIdByTransaction = Object.fromEntries(
    (dealResult.deals?.items ?? []).map((item) => [item.transaction_id, item.id]),
  );
  const connected = dispositionResult.apiConnected && dealResult.apiConnected;

  return (
    <WorkspacePage>
      <PageHeader
        description="Start buyer placement for an executed purchase agreement. Ongoing disposition work stays inside the Deal record."
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
