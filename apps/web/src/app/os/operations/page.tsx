import { getAcquisitionOperations, getDashboardData } from "../../lib/api";
import styles from "../page.module.css";
import { OperationsWorkspace } from "./operations-workspace";

export const dynamic = "force-dynamic";

export default async function AcquisitionOperationsPage() {
  const [{ operations, apiConnected }, dashboard] = await Promise.all([
    getAcquisitionOperations(),
    getDashboardData(),
  ]);

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Acquisition operations</p>
          <h2>Operations</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Workspace</span>
          <strong className={apiConnected ? styles.ready : styles.warning}>
            {apiConnected ? "Live operations" : "API unavailable"}
          </strong>
        </div>
      </header>

      {operations ? (
        <OperationsWorkspace leads={dashboard.leads} operations={operations} />
      ) : (
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Operations unavailable</h3>
            <span>Check API authentication and deployment status</span>
          </div>
        </section>
      )}
    </>
  );
}
