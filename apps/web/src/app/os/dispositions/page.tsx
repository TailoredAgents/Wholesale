import { getDispositionOverview } from "../../lib/api";
import { DealJourney } from "../_components/deal-journey";
import { PageHeader, SectionPanel, WorkspacePage } from "../_components/page-contracts";
import { StatusBadge } from "../_components/design-system";
import { DispositionWorkspace } from "./disposition-workspace";

export const dynamic = "force-dynamic";

export default async function DispositionsPage({
  searchParams,
}: {
  searchParams: Promise<{ case?: string }>;
}) {
  const [{ dispositions, apiConnected }, params] = await Promise.all([
    getDispositionOverview(),
    searchParams,
  ]);
  return (
    <WorkspacePage>
      <PageHeader
        description="Release approved deal evidence, compare qualified buyers, and reconcile the result."
        eyebrow="Deal flow / contract to buyer"
        meta={<StatusBadge tone={apiConnected ? "success" : "danger"}>{apiConnected ? "Buyer placement current" : "Queue unavailable"}</StatusBadge>}
        title="Dispositions"
      />
      <DealJourney active="dispositions" />
      {dispositions ? (
        <DispositionWorkspace initialCaseId={params.case} initialData={dispositions} />
      ) : (
        <SectionPanel description="A deal-access role and active operating plan are required." title="Disposition workspace unavailable">
          The server did not return disposition data.
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}
