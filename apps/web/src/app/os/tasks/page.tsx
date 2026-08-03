import { getTaskWorkspace, getWorkspaceProfile } from "../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../_components/page-contracts";
import { primaryRoleLabel } from "../os-navigation";
import { TasksWorkspace, type TaskView } from "./tasks-workspace";

export const dynamic = "force-dynamic";

type SearchValue = string | string[] | undefined;

const taskViews = new Set<TaskView>([
  "mine",
  "today",
  "overdue",
  "upcoming",
  "unscheduled",
  "team",
  "approvals",
  "ai_completed",
  "exceptions",
  "completed",
]);

function first(value: SearchValue) {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export default async function TasksPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, SearchValue>>;
}) {
  const params = (await searchParams) ?? {};
  const [{ workspace, apiConnected }, profile] = await Promise.all([
    getTaskWorkspace(),
    getWorkspaceProfile(),
  ]);
  const requestedView = first(params.view) as TaskView;
  let initialView = taskViews.has(requestedView) ? requestedView : "mine";
  if (initialView === "team" && !workspace?.can_manage_team) initialView = "mine";
  if (initialView === "approvals" && !workspace?.can_decide_approvals) initialView = "mine";

  return (
    <WorkspacePage>
      <PageHeader
        description="See the responsible person, required action, deadline, approvals, and exceptions in one work center."
        eyebrow="Daily execution"
        meta={
          profile
            ? `${primaryRoleLabel(profile)} · ${workspace?.items.filter((item) => item.due_status !== "completed").length ?? 0} open`
            : apiConnected
              ? "Workspace current"
              : "API unavailable"
        }
        title="Tasks"
      />
      {workspace ? (
        <TasksWorkspace
          initialItemId={first(params.item)}
          initialView={initialView}
          initialWorkspace={workspace}
        />
      ) : (
        <SectionPanel
          description="Task access requires an operating role with seller, deal, finance, or operations visibility."
          title="Tasks unavailable"
        >
          <div />
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}
