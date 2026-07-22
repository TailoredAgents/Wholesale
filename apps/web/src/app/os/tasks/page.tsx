import { getDashboardData, getWorkspaceProfile } from "../../lib/api";
import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { primaryRoleLabel } from "../os-navigation";
import { WorkQueueWorkspace, type QueueView } from "./work-queue-workspace";

export const dynamic = "force-dynamic";

const queueViews = new Set<QueueView>(["all", "mine", "overdue", "due", "unscheduled"]);

export default async function TasksPage({
  searchParams,
}: {
  searchParams: Promise<{ view?: string }>;
}) {
  const params = await searchParams;
  const [dashboard, profile] = await Promise.all([getDashboardData(), getWorkspaceProfile()]);
  const isIndividualContributor = profile?.role_keys.includes("acquisition_rep") ?? false;
  const requestedView = params.view as QueueView | undefined;
  const initialView = requestedView && queueViews.has(requestedView)
    ? requestedView
    : isIndividualContributor
      ? "mine"
      : "all";
  const canComplete =
    profile?.permissions.includes("leads:edit") ?? process.env.NODE_ENV === "development";

  return (
    <WorkspacePage>
      <PageHeader
        description="Triage assigned follow-up, due work, and seller next actions without losing record context."
        eyebrow="Daily execution"
        meta={profile ? `${primaryRoleLabel(profile)} · ${dashboard.openTaskQueue.length} open` : null}
        title="Work Queue"
      />
      <WorkQueueWorkspace
        canComplete={canComplete}
        currentUserEmail={profile?.email ?? null}
        initialTasks={dashboard.openTaskQueue}
        initialView={initialView}
      />
    </WorkspacePage>
  );
}
