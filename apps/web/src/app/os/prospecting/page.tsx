import { getProspectingWorkbench } from "../../lib/api";
import styles from "../page.module.css";
import { ProspectingWorkspace } from "./prospecting-workspace";

export const dynamic = "force-dynamic";

export default async function ProspectingPage() {
  const { prospecting, apiConnected } = await getProspectingWorkbench();

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>VA prospecting</p>
          <h2>Prospecting</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Queue control</span>
          <strong className={apiConnected ? styles.ready : styles.warning}>
            {apiConnected ? "Assigned records only" : "API unavailable"}
          </strong>
        </div>
      </header>

      {prospecting ? (
        <ProspectingWorkspace
          data={prospecting}
          key={
            prospecting.current_entry
              ? `${prospecting.current_entry.id}:${prospecting.current_entry.status}:${prospecting.current_entry.attempt_count}:${prospecting.current_entry.active_attempt?.id ?? "ready"}`
              : `empty:${prospecting.queue.ready}:${prospecting.queue.completed}`
          }
        />
      ) : (
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Prospecting workbench unavailable</h3>
            <span>An assigned caller or acquisition-management role is required.</span>
          </div>
        </section>
      )}
    </>
  );
}
