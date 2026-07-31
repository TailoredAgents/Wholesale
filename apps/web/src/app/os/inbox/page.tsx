import { redirect } from "next/navigation";

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
  searchParams: Promise<{
    conversation?: string;
    compose?: string;
    lead?: string;
    manage?: string;
    view?: string;
  }>;
}) {
  const params = await searchParams;
  if (params.manage === "email") redirect("/os/settings/communications");
  const requestedFilter = params.view as InboxFilterKey | undefined;

  return (
    <InboxWorkspace
      initialFilter={requestedFilter && inboxFilters.has(requestedFilter) ? requestedFilter : "team"}
      initialConversationId={params.conversation ?? null}
      initialEmailAdminOpen={false}
      initialGlobalComposeOpen={params.compose === "email"}
      initialLeadId={params.lead ?? null}
      key={params.compose === "email" ? "compose-email" : "inbox"}
    />
  );
}
