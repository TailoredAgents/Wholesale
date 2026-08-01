import { redirect } from "next/navigation";

import {
  InboxWorkspace,
  type ComposerChannel,
  type InboxFilterKey,
} from "./inbox-workspace";

export const dynamic = "force-dynamic";

const inboxFilters = new Set<InboxFilterKey>([
  "mine",
  "unassigned",
  "team",
  "needs_reply",
  "appointments",
  "unread",
]);
const composerChannels = new Set<ComposerChannel>(["sms", "email", "call", "note"]);

export default async function InboxPage({
  searchParams,
}: {
  searchParams: Promise<{
    conversation?: string;
    compose?: string;
    channel?: string;
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
      initialChannel={
        params.channel && composerChannels.has(params.channel as ComposerChannel)
          ? (params.channel as ComposerChannel)
          : "sms"
      }
      key={params.compose === "email" ? "compose-email" : "inbox"}
    />
  );
}
