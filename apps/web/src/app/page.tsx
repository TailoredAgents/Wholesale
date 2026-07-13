import Link from "next/link";

import { CompleteTaskButton } from "./complete-task-button";
import styles from "./page.module.css";
import { getDashboardData } from "./lib/api";

export const dynamic = "force-dynamic";

const pipelineStages = [
  { key: "new", label: "New" },
  { key: "contacted", label: "Contacted" },
  { key: "underwriting", label: "Underwriting" },
  { key: "offer_ready", label: "Offer ready" },
  { key: "under_contract", label: "Under contract" },
  { key: "closed", label: "Closed" },
];

function formatMoney(cents: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function labelize(value: string) {
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function formatTime(value: string | null) {
  if (!value) {
    return "Unscheduled";
  }
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export default async function Home() {
  const dashboard = await getDashboardData();
  const pipelineCounts = new Map(
    dashboard.summary.pipeline.map((stage) => [stage.stage_key, stage.count]),
  );
  const metrics = [
    {
      label: "New paid leads",
      value: String(dashboard.summary.new_paid_leads),
      detail: "Speed-to-lead queue",
    },
    {
      label: "Contact tasks",
      value: String(dashboard.speedToLeadQueue.length),
      detail: "Open seller follow-up",
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
    <main className={styles.shell}>
      <aside className={styles.sidebar} aria-label="Primary navigation">
        <div>
          <p className={styles.eyebrow}>Oakwell Home Buyers</p>
          <h1>Operating System</h1>
        </div>
        <nav className={styles.nav}>
          <a className={styles.activeNav} href="#dashboard">
            Dashboard
          </a>
          <a href="/get-a-cash-offer">Cash offer form</a>
          <a href="#leads">Leads</a>
          <a href="#underwriting">Underwriting</a>
          <a href="#approvals">Approvals</a>
          <a href="#buyers">Buyers</a>
        </nav>
      </aside>

      <section className={styles.workspace} id="dashboard">
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
      </section>
    </main>
  );
}
