import styles from "./page.module.css";

const metrics = [
  { label: "New paid leads", value: "0", detail: "Speed-to-lead queue" },
  { label: "Offers pending", value: "0", detail: "Manager approval" },
  { label: "Active contracts", value: "0", detail: "Transaction pipeline" },
  { label: "Collected revenue", value: "$0", detail: "Current month" },
];

const pipelineStages = [
  "New",
  "Contacted",
  "Underwriting",
  "Offer ready",
  "Under contract",
  "Closed",
];

const queueRows = [
  {
    name: "No live seller leads yet",
    source: "Website",
    stage: "Waiting for first submission",
    owner: "Unassigned",
  },
  {
    name: "Local API",
    source: "FastAPI",
    stage: "Health: /health",
    owner: "Port 8000",
  },
  {
    name: "Local database",
    source: "PostgreSQL",
    stage: "Foundation migrated",
    owner: "Postgres 18",
  },
];

export default function Home() {
  return (
    <main className={styles.shell}>
      <aside className={styles.sidebar} aria-label="Primary navigation">
        <div>
          <p className={styles.eyebrow}>Georgia wholesale</p>
          <h1>Operating System</h1>
        </div>
        <nav className={styles.nav}>
          <a className={styles.activeNav} href="#dashboard">
            Dashboard
          </a>
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
            <strong>Postgres ready</strong>
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
              <h3>Lead Queue</h3>
              <span>Speed to lead</span>
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
                  {queueRows.map((row) => (
                    <tr key={row.name}>
                      <td>{row.name}</td>
                      <td>{row.source}</td>
                      <td>{row.stage}</td>
                      <td>{row.owner}</td>
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
                <li key={stage}>
                  <span>{stage}</span>
                  <strong>0</strong>
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
