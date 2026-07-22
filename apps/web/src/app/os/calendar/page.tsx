import { getFieldOperationsOverview } from "../../lib/api";
import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { CalendarWorkspace } from "./calendar-workspace";

export const dynamic = "force-dynamic";

export default async function CalendarPage() {
  const { fieldOperations, apiConnected } = await getFieldOperationsOverview();

  return (
    <WorkspacePage>
      <PageHeader
        description="Coordinate seller meetings, closer capacity, and field preparation from one internal schedule."
        eyebrow="Team schedule"
        meta={apiConnected ? "Schedule current" : "API unavailable"}
        title="Calendar"
      />
      {fieldOperations ? (
        <CalendarWorkspace data={fieldOperations} />
      ) : (
        <section role="status">
          Calendar access requires an acquisitions or management role.
        </section>
      )}
    </WorkspacePage>
  );
}
