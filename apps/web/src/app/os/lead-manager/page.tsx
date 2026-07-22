import { getLeadManagerOverview } from "../../lib/api";
import styles from "../page.module.css";
import { LeadManagerWorkspace } from "./lead-manager-workspace";

export const dynamic = "force-dynamic";

export default async function LeadManagerPage() {
  const { leadManager, apiConnected } = await getLeadManagerOverview();

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Warm lead operations</p>
          <h2>Lead Manager desk</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Daily control</span>
          <strong className={apiConnected ? styles.ready : styles.warning}>
            {apiConnected ? "Queue current" : "API unavailable"}
          </strong>
        </div>
      </header>

      {leadManager ? (
        <LeadManagerWorkspace data={leadManager} />
      ) : (
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Lead Manager desk unavailable</h3>
            <span>An acquisitions or management role is required.</span>
          </div>
        </section>
      )}
    </>
  );
}
