import { InboxWorkspace, type InboxFilterKey } from "./inbox-workspace";

export const dynamic = "force-dynamic";

const inboxFilters = new Set<InboxFilterKey>([
  "mine",
  "unassigned",
  "team",
  "needs_reply",
  "appointments",
  "unread",
]);

export default async function InboxPage({
  searchParams,
}: {
  searchParams: Promise<{ lead?: string; view?: string }>;
}) {
  const params = await searchParams;
  const requestedFilter = params.view as InboxFilterKey | undefined;

  return (
    <InboxWorkspace
      initialFilter={requestedFilter && inboxFilters.has(requestedFilter) ? requestedFilter : "team"}
      initialLeadId={params.lead ?? null}
    />
  );
}
