import { getFieldOperationsOverview } from "../../lib/api";
import styles from "../page.module.css";
import { FieldOperationsWorkspace } from "./field-operations-workspace";

export const dynamic = "force-dynamic";

export default async function FieldOperationsPage() {
  const { fieldOperations, apiConnected } = await getFieldOperationsOverview();

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
        <FieldOperationsWorkspace data={fieldOperations} />
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
