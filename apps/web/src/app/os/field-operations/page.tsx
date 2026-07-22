import { getFieldOperationsOverview } from "../../lib/api";
import styles from "../page.module.css";
import { FieldOperationsWorkspace } from "./field-operations-workspace";

export const dynamic = "force-dynamic";

const fieldViews = new Set(["dispatch", "calendar", "meetings", "capacity"]);

export default async function FieldOperationsPage({
  searchParams,
}: {
  searchParams: Promise<{ appointment?: string; view?: string }>;
}) {
  const params = await searchParams;
  const { fieldOperations, apiConnected } = await getFieldOperationsOverview();
  const initialView = fieldViews.has(params.view ?? "")
    ? (params.view as "dispatch" | "calendar" | "meetings" | "capacity")
    : "dispatch";

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Seller appointment operations</p>
          <h2>Field dispatch</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Internal calendar</span>
          <strong className={apiConnected ? styles.ready : styles.warning}>
            {apiConnected ? "Capacity current" : "API unavailable"}
          </strong>
        </div>
      </header>

      {fieldOperations ? (
        <FieldOperationsWorkspace
          data={fieldOperations}
          initialAppointmentId={params.appointment ?? ""}
          initialView={initialView}
        />
      ) : (
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Field dispatch unavailable</h3>
            <span>An acquisitions or management role is required.</span>
          </div>
        </section>
      )}
    </>
  );
}
