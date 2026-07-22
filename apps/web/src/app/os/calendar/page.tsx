import { getFieldOperationsOverview } from "../../lib/api";
import styles from "../page.module.css";
import { CalendarWorkspace } from "./calendar-workspace";

export const dynamic = "force-dynamic";

export default async function CalendarPage() {
  const { fieldOperations, apiConnected } = await getFieldOperationsOverview();

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Team schedule</p>
          <h2>Calendar</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Internal scheduling</span>
          <strong className={apiConnected ? styles.ready : styles.warning}>
            {apiConnected ? "Schedule current" : "API unavailable"}
          </strong>
        </div>
      </header>

      {fieldOperations ? (
        <CalendarWorkspace data={fieldOperations} />
      ) : (
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Calendar unavailable</h3>
            <span>An acquisitions or management role is required.</span>
          </div>
        </section>
      )}
    </>
  );
}
