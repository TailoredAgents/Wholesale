import Link from "next/link";

import { getDashboardData } from "../../lib/api";
import {
  formatDateTime,
  getTaskCountsByLead,
  labelize,
  pipelineStages,
} from "../os-utils";
import styles from "../page.module.css";

export const dynamic = "force-dynamic";

export default async function PipelinePage() {
  const dashboard = await getDashboardData();
  const pipelineCounts = new Map(
    dashboard.summary.pipeline.map((stage) => [stage.stage_key, stage.count]),
  );
  const taskCountsByLead = getTaskCountsByLead(dashboard.openTaskQueue);

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Pipeline</p>
          <h2>Seller Pipeline</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Active leads</span>
          <strong className={styles.ready}>{dashboard.leads.length}</strong>
        </div>
      </header>

      <section className={styles.boardSection}>
        <div className={styles.sectionHeader}>
          <div>
            <p className={styles.eyebrow}>Stages</p>
            <h3>Move leads from contact to offer</h3>
          </div>
          <span>{dashboard.openTaskQueue.length} open tasks</span>
        </div>
        <div className={styles.pipelineBoard}>
          {pipelineStages.map((stage) => {
            const stageLeads = dashboard.leads.filter((lead) => lead.stage_key === stage.key);
            return (
              <article className={styles.pipelineColumn} key={stage.key}>
                <div className={styles.columnHeader}>
                  <h4>{stage.label}</h4>
                  <span>{pipelineCounts.get(stage.key) ?? 0}</span>
                </div>
                <div className={styles.leadCards}>
                  {stageLeads.length === 0 ? <p className={styles.emptyColumn}>No leads</p> : null}
                  {stageLeads.map((lead) => (
                    <Link className={styles.leadCard} href={`/os/leads/${lead.id}`} key={lead.id}>
                      <strong>{lead.seller_name}</strong>
                      <span>{lead.property_address}</span>
                      <small>
                        {labelize(lead.source)} · {labelize(lead.lead_temperature ?? "no_temp")}
                      </small>
                      <small>
                        Next: {formatDateTime(lead.next_follow_up_at)} · Tasks:{" "}
                        {taskCountsByLead.get(lead.id) ?? 0}
                      </small>
                    </Link>
                  ))}
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </>
  );
}
