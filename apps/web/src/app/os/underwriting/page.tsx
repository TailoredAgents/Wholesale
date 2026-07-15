import Link from "next/link";

import { getDashboardData } from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "../page.module.css";

export const dynamic = "force-dynamic";

export default async function UnderwritingPage() {
  const dashboard = await getDashboardData();
  const underwritingLeads = dashboard.leads.filter((lead) =>
    ["underwriting", "offer_pending_approval", "offer_ready", "offer_presented"].includes(
      lead.stage_key,
    ),
  );

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Underwriting</p>
          <h2>Offer preparation workspace</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Underwriting leads</span>
          <strong className={styles.ready}>{underwritingLeads.length}</strong>
        </div>
      </header>

      <section className={styles.contentGrid}>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Ready For Analysis</h3>
            <span>{underwritingLeads.length} leads</span>
          </div>
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Seller</th>
                  <th>Stage</th>
                  <th>Condition</th>
                  <th>Asking</th>
                  <th>Mortgage</th>
                </tr>
              </thead>
              <tbody>
                {underwritingLeads.length === 0 ? (
                  <tr>
                    <td>No leads in underwriting yet</td>
                    <td>Clear</td>
                    <td>Unknown</td>
                    <td>Unknown</td>
                    <td>Unknown</td>
                  </tr>
                ) : null}
                {underwritingLeads.map((lead) => (
                  <tr key={lead.id}>
                    <td>
                      <Link className={styles.tableLink} href={`/os/leads/${lead.id}`}>
                        {lead.seller_name}
                      </Link>
                      <small className={styles.tableSubtext}>{lead.property_address}</small>
                    </td>
                    <td>{labelize(lead.stage_key)}</td>
                    <td>{labelize(lead.property_condition)}</td>
                    <td>{lead.asking_price ?? "Unknown"}</td>
                    <td>{lead.mortgage_balance ?? "Unknown"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Underwriting Checklist</h3>
            <span>Next module</span>
          </div>
          <div className={styles.approvals}>
            <p>ARV comp review</p>
            <p>Repair estimate</p>
            <p>Seller net target</p>
            <p>Offer ceiling</p>
            <p>Approval request</p>
            <p>Contract package</p>
          </div>
        </article>
      </section>
    </>
  );
}
