import { getDashboardData } from "../../lib/api";
import styles from "../page.module.css";

export const dynamic = "force-dynamic";

export default async function BuyersPage() {
  const dashboard = await getDashboardData();
  const contractLeads = dashboard.leads.filter((lead) =>
    ["under_contract", "closed"].includes(lead.stage_key),
  );

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Buyers</p>
          <h2>Disposition workspace</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Deals needing buyers</span>
          <strong className={styles.ready}>{contractLeads.length}</strong>
        </div>
      </header>

      <section className={styles.contentGrid}>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Deal Room Queue</h3>
            <span>{contractLeads.length} deals</span>
          </div>
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Property</th>
                  <th>Seller</th>
                  <th>Stage</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {contractLeads.length === 0 ? (
                  <tr>
                    <td>No contracted deals yet</td>
                    <td>Waiting</td>
                    <td>Clear</td>
                    <td>OS</td>
                  </tr>
                ) : null}
                {contractLeads.map((lead) => (
                  <tr key={lead.id}>
                    <td>{lead.property_address}</td>
                    <td>{lead.seller_name}</td>
                    <td>{lead.stage_key}</td>
                    <td>{lead.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Buyer CRM Foundation</h3>
            <span>Next module</span>
          </div>
          <div className={styles.approvals}>
            <p>Buyer list</p>
            <p>Buying criteria</p>
            <p>Proof of funds</p>
            <p>Market preferences</p>
            <p>Deal blasts</p>
            <p>Buyer offer collection</p>
          </div>
        </article>
      </section>
    </>
  );
}
