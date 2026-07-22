import { getDashboardData, getOperatingModelOverview } from "../../lib/api";
import styles from "../page.module.css";
import { OperatingModelWorkspace } from "./operating-model-workspace";

export const dynamic = "force-dynamic";

export default async function OperatingModelPage() {
  const [{ operatingModel, apiConnected }, dashboard] = await Promise.all([
    getOperatingModelOverview(),
    getDashboardData(),
  ]);

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Business setup</p>
          <h2>Operating model controls</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Policy records</span>
          <strong className={apiConnected ? styles.ready : styles.warning}>
            {apiConnected ? "Versioned and auditable" : "API unavailable"}
          </strong>
        </div>
      </header>

      {operatingModel ? (
        <OperatingModelWorkspace
          leads={dashboard.leads.filter((lead) => !lead.archived_at)}
          operatingModel={operatingModel}
        />
      ) : (
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Business setup unavailable</h3>
            <span>Owner-level operating-model access is required</span>
          </div>
        </section>
      )}
    </>
  );
}
