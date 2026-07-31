import { redirect } from "next/navigation";

import { getDealOverview } from "../../lib/api";

export const dynamic = "force-dynamic";

const transactionTabs = new Set(["contract", "closing", "documents", "parties", "timeline"]);

export default async function TransactionsPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string; transaction?: string }>;
}) {
  const [params, { deals }] = await Promise.all([searchParams, getDealOverview()]);
  const selected = deals?.items.find((item) => item.transaction_id === params.transaction);
  const query = new URLSearchParams({
    display: "queue",
    tab: transactionTabs.has(params.tab ?? "") ? params.tab! : "closing",
    view: "all",
  });
  if (selected) query.set("deal", selected.id);
  redirect(`/os/deals?${query.toString()}`);
}
