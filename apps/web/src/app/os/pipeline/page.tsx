import { getDashboardData } from "../../lib/api";
import { AcquisitionJourney } from "../_components/acquisition-journey";
import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { getPipelineStage, pipelineStages } from "../os-utils";
import { PipelineWorkspace } from "./pipeline-workspace";

export const dynamic = "force-dynamic";

export default async function PipelinePage({
  searchParams,
}: {
  searchParams: Promise<{ stage?: string }>;
}) {
  const params = await searchParams;
  const dashboard = await getDashboardData();
  const requestedStage = params.stage
    ? pipelineStages.find((stage) => stage.key === params.stage) ?? getPipelineStage(params.stage)
    : null;

  return (
    <WorkspacePage>
      <PageHeader
        description="Stage ownership, bottlenecks, and seller next actions across active acquisition opportunities."
        eyebrow="Stage management"
        meta={`${dashboard.leads.length} active leads · ${dashboard.openTaskQueue.length} open tasks`}
        title="Seller Pipeline"
      />
      <AcquisitionJourney active="pipeline" />
      <PipelineWorkspace
        initialStage={requestedStage?.key ?? "all"}
        leads={dashboard.leads}
        tasks={dashboard.openTaskQueue}
      />
    </WorkspacePage>
  );
}
