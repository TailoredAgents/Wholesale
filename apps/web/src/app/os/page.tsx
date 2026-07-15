import Link from "next/link";

import { CompleteTaskButton } from "../complete-task-button";
import styles from "./page.module.css";
import { getDashboardData } from "../lib/api";
import {
  boardStages,
  formatDateTime,
  formatMoney,
  formatTime,
  getTaskCountsByLead,
  getWorkspaceQueues,
  labelize,
  pipelineStages,
  qualificationFieldCount,
} from "./os-utils";

export const dynamic = "force-dynamic";

export default async function Home() {
  const dashboard = await getDashboardData();
  const pipelineCounts = new Map(
    dashboard.summary.pipeline.map((stage) => [stage.stage_key, stage.count]),
  );
  const sourcePerformance = dashboard.summary.source_performance;
  const openTasks = dashboard.openTaskQueue;
  const { overdueTasks, dueTasks, needsQualification, appointmentQueue, offerQueue } =
    getWorkspaceQueues(dashboard.leads, openTasks);
  const leadsByStage = new Map(
    boardStages.map((stage) => [
      stage.key,
      dashboard.leads.filter((lead) => lead.stage_key === stage.key).slice(0, 5),
    ]),
  );
  const openTaskCountsByLead = getTaskCountsByLead(openTasks);
  const metrics = [
    {
      label: "New paid leads",
      value: String(dashboard.summary.new_paid_leads),
      detail: "Speed-to-lead queue",
    },
    {
      label: "Open tasks",
      value: String(openTasks.length),
      detail: `${overdueTasks.length} overdue / ${dueTasks.length} due`,
    },
    {
      label: "Offers pending",
      value: String(dashboard.summary.offers_pending),
      detail: "Manager approval",
    },
    {
      label: "Active contracts",
      value: String(dashboard.summary.active_contracts),
      detail: "Transaction pipeline",
    },
    {
      label: "Collected revenue",
      value: formatMoney(dashboard.summary.collected_revenue_cents),
      detail: "Current month",
    },
  ];

  return (
    <>
        <header className={styles.header}>
          <div>
            <p className={styles.eyebrow}>Local foundation</p>
            <h2>Acquisition command center</h2>
          </div>
          <div className={styles.statusGroup} aria-label="System status">
            <span>API localhost:8000</span>
            <strong className={dashboard.apiConnected ? styles.ready : styles.warning}>
              {dashboard.apiConnected ? "Live database data" : "API fallback view"}
            </strong>
          </div>
        </header>

        <section className={styles.metrics} aria-label="Current month metrics">
          {metrics.map((metric) => (
            <article className={styles.metric} key={metric.label}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
              <small>{metric.detail}</small>
            </article>
          ))}
        </section>

        <section className={styles.workQueues} id="work" aria-label="Acquisition work queues">
          <article className={styles.queuePanel}>
            <div className={styles.panelHeader}>
              <h3>Overdue Follow-Up</h3>
              <span>{overdueTasks.length} tasks</span>
            </div>
            <div className={styles.queueList}>
              {overdueTasks.length === 0 ? <p>No overdue follow-up.</p> : null}
              {overdueTasks.slice(0, 5).map((task) => (
                <div className={styles.queueItem} key={task.task_id}>
                  <div>
                    <Link className={styles.tableLink} href={`/leads/${task.lead_id}`}>
                      {task.seller_name}
                    </Link>
                    <span>{task.title}</span>
                    <small>{formatDateTime(task.due_at)}</small>
                  </div>
                  <CompleteTaskButton taskId={task.task_id} />
                </div>
              ))}
            </div>
          </article>

          <article className={styles.queuePanel}>
            <div className={styles.panelHeader}>
              <h3>Needs Qualification</h3>
              <span>{needsQualification.length} leads</span>
            </div>
            <div className={styles.queueList}>
              {needsQualification.length === 0 ? <p>No qualification gaps.</p> : null}
              {needsQualification.slice(0, 5).map((lead) => (
                <Link className={styles.queueLead} href={`/leads/${lead.id}`} key={lead.id}>
                  <strong>{lead.seller_name}</strong>
                  <span>{lead.property_address}</span>
                  <small>
                    {qualificationFieldCount(lead)}/3 fields captured · {labelize(lead.source)}
                  </small>
                </Link>
              ))}
            </div>
          </article>

          <article className={styles.queuePanel}>
            <div className={styles.panelHeader}>
              <h3>Appointments</h3>
              <span>{appointmentQueue.length} leads</span>
            </div>
            <div className={styles.queueList}>
              {appointmentQueue.length === 0 ? <p>No appointment work queued.</p> : null}
              {appointmentQueue.slice(0, 5).map((lead) => (
                <Link className={styles.queueLead} href={`/leads/${lead.id}`} key={lead.id}>
                  <strong>{lead.seller_name}</strong>
                  <span>{labelize(lead.appointment_status ?? "not_scheduled")}</span>
                  <small>{lead.property_address}</small>
                </Link>
              ))}
            </div>
          </article>

          <article className={styles.queuePanel}>
            <div className={styles.panelHeader}>
              <h3>Offers To Prepare</h3>
              <span>{offerQueue.length} leads</span>
            </div>
            <div className={styles.queueList}>
              {offerQueue.length === 0 ? <p>No offers waiting.</p> : null}
              {offerQueue.slice(0, 5).map((lead) => (
                <Link className={styles.queueLead} href={`/leads/${lead.id}`} key={lead.id}>
                  <strong>{lead.seller_name}</strong>
                  <span>{labelize(lead.stage_key)}</span>
                  <small>{lead.property_address}</small>
                </Link>
              ))}
            </div>
          </article>
        </section>

        <section className={styles.boardSection} id="pipeline" aria-label="Acquisition pipeline">
          <div className={styles.sectionHeader}>
            <div>
              <p className={styles.eyebrow}>Pipeline</p>
              <h3>Seller acquisition board</h3>
            </div>
            <span>{dashboard.leads.length} active leads</span>
          </div>
          <div className={styles.pipelineBoard}>
            {boardStages.map((stage) => (
              <article className={styles.pipelineColumn} key={stage.key}>
                <div className={styles.columnHeader}>
                  <h4>{stage.label}</h4>
                  <span>{pipelineCounts.get(stage.key) ?? 0}</span>
                </div>
                <div className={styles.leadCards}>
                  {(leadsByStage.get(stage.key) ?? []).length === 0 ? (
                    <p className={styles.emptyColumn}>No leads</p>
                  ) : null}
                  {(leadsByStage.get(stage.key) ?? []).map((lead) => (
                    <Link className={styles.leadCard} href={`/leads/${lead.id}`} key={lead.id}>
                      <strong>{lead.seller_name}</strong>
                      <span>{lead.property_address}</span>
                      <small>
                        {labelize(lead.source)} · {labelize(lead.lead_temperature ?? "no_temp")}
                      </small>
                      <small>
                        Next: {formatDateTime(lead.next_follow_up_at)} · Tasks:{" "}
                        {openTaskCountsByLead.get(lead.id) ?? 0}
                      </small>
                    </Link>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.contentGrid}>
          <div className={styles.panel} id="leads">
            <div className={styles.panelHeader}>
              <h3>Speed-To-Lead Queue</h3>
              <span>Open contact tasks</span>
            </div>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Source</th>
                    <th>Due</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {dashboard.speedToLeadQueue.length === 0 ? (
                    <tr>
                      <td>No open contact tasks</td>
                      <td>Waiting for seller submissions</td>
                      <td>Clear</td>
                      <td>Ready</td>
                      <td></td>
                    </tr>
                  ) : null}
                  {dashboard.speedToLeadQueue.map((task) => (
                    <tr key={task.task_id}>
                      <td>
                        <Link className={styles.tableLink} href={`/leads/${task.lead_id}`}>
                          {task.seller_name}
                        </Link>
                        <small className={styles.tableSubtext}>{task.property_address}</small>
                      </td>
                      <td>{labelize(task.source)}</td>
                      <td>{formatTime(task.due_at)}</td>
                      <td>
                        <span className={styles[task.due_status]}>{labelize(task.due_status)}</span>
                      </td>
                      <td>
                        <CompleteTaskButton taskId={task.task_id} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <h3>Lead List</h3>
              <span>Recent sellers</span>
            </div>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Source</th>
                    <th>Stage</th>
                    <th>Owner</th>
                  </tr>
                </thead>
                <tbody>
                  {dashboard.leads.length === 0 ? (
                    <tr>
                      <td>No live seller leads yet</td>
                      <td>Website</td>
                      <td>Waiting for first submission</td>
                      <td>Unassigned</td>
                    </tr>
                  ) : null}
                  {dashboard.leads.map((lead) => (
                    <tr key={lead.id}>
                      <td>
                        <Link className={styles.tableLink} href={`/leads/${lead.id}`}>
                          {lead.seller_name}
                        </Link>
                      </td>
                      <td>{labelize(lead.source)}</td>
                      <td>{labelize(lead.stage_key)}</td>
                      <td>{lead.assigned_user_email ?? "Unassigned"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <h3>Source Performance</h3>
              <span>Public site conversion events</span>
            </div>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Views</th>
                    <th>Starts</th>
                    <th>Abandons</th>
                    <th>Submits</th>
                    <th>Calls</th>
                    <th>Leads</th>
                  </tr>
                </thead>
                <tbody>
                  {sourcePerformance.length === 0 ? (
                    <tr>
                      <td>No source data yet</td>
                      <td>0</td>
                      <td>0</td>
                      <td>0</td>
                      <td>0</td>
                      <td>0</td>
                      <td>0</td>
                    </tr>
                  ) : null}
                  {sourcePerformance.map((source) => (
                    <tr key={`${source.source}-${source.medium}-${source.campaign}`}>
                      <td>
                        {labelize(source.source)}
                        <small className={styles.tableSubtext}>
                          {[source.medium, source.campaign]
                            .filter((value) => !["unknown", "uncategorized"].includes(value))
                            .map(labelize)
                            .join(" / ") || "No campaign"}
                        </small>
                      </td>
                      <td>{source.page_views}</td>
                      <td>{source.form_starts}</td>
                      <td>{source.form_abandons}</td>
                      <td>{source.form_submits}</td>
                      <td>{source.call_clicks}</td>
                      <td>{source.leads_created}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className={styles.panel} id="underwriting">
            <div className={styles.panelHeader}>
              <h3>Seller Pipeline</h3>
              <span>Core stages</span>
            </div>
            <ol className={styles.pipeline}>
              {pipelineStages.map((stage) => (
                <li key={stage.key}>
                  <span>{stage.label}</span>
                  <strong>{pipelineCounts.get(stage.key) ?? 0}</strong>
                </li>
              ))}
            </ol>
          </div>

          <div className={styles.panel} id="approvals">
            <div className={styles.panelHeader}>
              <h3>Approval Queue</h3>
              <span>Human controlled</span>
            </div>
            <div className={styles.approvals}>
              <p>ARV approvals</p>
              <p>Repair budgets</p>
              <p>Seller offer ceilings</p>
              <p>Contract sends</p>
              <p>Buyer selection</p>
            </div>
          </div>
        </section>
    </>
  );
}
