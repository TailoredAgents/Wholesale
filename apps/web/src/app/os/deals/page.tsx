import { getDealOverview, getDispositionOverview, getTransactionOverview } from "../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../_components/page-contracts";
import { StatusBadge } from "../_components/design-system";
import { DealsWorkspace } from "./deals-workspace";

export const dynamic = "force-dynamic";

export default async function DealsPage({
  searchParams,
}: {
  searchParams: Promise<{ deal?: string; display?: string; tab?: string; view?: string }>;
}) {
  const [dealResult, transactionResult, dispositionResult, params] = await Promise.all([
    getDealOverview(),
    getTransactionOverview(),
    getDispositionOverview(),
    searchParams,
  ]);
  const connected = dealResult.apiConnected && transactionResult.apiConnected && dispositionResult.apiConnected;

  return (
    <WorkspacePage>
      <PageHeader
        description="Run contract, closing, buyer placement, and financial handoff from one deal record."
        eyebrow="Operations / contract to funding"
        meta={<StatusBadge tone={connected ? "success" : "danger"}>{connected ? "Deal queue current" : "Deal data unavailable"}</StatusBadge>}
        title="Deals"
      />
      {dealResult.deals && transactionResult.transactions && dispositionResult.dispositions ? (
        <DealsWorkspace
          initialDealId={params.deal}
          initialDisplay={params.display}
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
