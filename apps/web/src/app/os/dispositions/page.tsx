import { getDispositionOverview } from "../../lib/api";
import styles from "../page.module.css";
import { DispositionWorkspace } from "./disposition-workspace";

export const dynamic = "force-dynamic";

export default async function DispositionsPage() {
  const { dispositions, apiConnected } = await getDispositionOverview();
  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Contract to buyer</p>
          <h2>Dispositions</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Buyer placement</span>
          <strong className={apiConnected ? styles.ready : styles.warning}>
            {apiConnected ? "Queue current" : "API unavailable"}
          </strong>
        </div>
      </header>
      {dispositions ? (
        <DispositionWorkspace initialData={dispositions} />
      ) : (
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Disposition workspace unavailable</h3>
            <span>A deal-access role and active business plan are required.</span>
          </div>
        </section>
      )}
    </>
  );
}
