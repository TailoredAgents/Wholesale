import { getTransactionOverview } from "../../lib/api";
import { DealJourney } from "../_components/deal-journey";
import { PageHeader, SectionPanel, WorkspacePage } from "../_components/page-contracts";
import { StatusBadge } from "../_components/design-system";
import { TransactionWorkspace } from "./transaction-workspace";

export const dynamic = "force-dynamic";

export default async function TransactionsPage({
  searchParams,
}: {
  searchParams: Promise<{ transaction?: string }>;
}) {
  const [{ transactions, apiConnected }, params] = await Promise.all([
    getTransactionOverview(),
    searchParams,
  ]);
  return (
    <WorkspacePage>
      <PageHeader
        description="Control contracts, evidence, deadlines, closing parties, and funding from one record."
        eyebrow="Deal flow / contract to funding"
        meta={<StatusBadge tone={apiConnected ? "success" : "danger"}>{apiConnected ? "Closing queue current" : "Queue unavailable"}</StatusBadge>}
        title="Transactions"
      />
      <DealJourney active="transactions" />
      {transactions ? (
        <TransactionWorkspace initialData={transactions} initialTransactionId={params.transaction} />
      ) : (
        <SectionPanel description="A deal-access role and an available API connection are required." title="Transaction workspace unavailable">
          The server did not return transaction data.
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}
