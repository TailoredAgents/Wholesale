import Link from "next/link";

import { getDashboardData } from "../../lib/api";
import { formatDateTime, labelize, qualificationFieldCount } from "../os-utils";
import styles from "../page.module.css";

export const dynamic = "force-dynamic";

export default async function LeadsPage() {
  const dashboard = await getDashboardData();
  const newLeads = dashboard.leads.filter((lead) => lead.stage_key === "new");
  const qualifiedLeads = dashboard.leads.filter((lead) =>
    ["qualified", "appointment_scheduled", "underwriting", "offer_ready"].includes(lead.stage_key),
  );

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Leads</p>
          <h2>Seller lead database</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Total leads</span>
          <strong className={styles.ready}>{dashboard.leads.length}</strong>
        </div>
      </header>

      <section className={styles.metrics} aria-label="Lead metrics">
        <article className={styles.metric}>
          <span>New</span>
          <strong>{newLeads.length}</strong>
          <small>Needs first contact</small>
        </article>
        <article className={styles.metric}>
          <span>Qualified+</span>
          <strong>{qualifiedLeads.length}</strong>
          <small>Ready for appointment/offer work</small>
        </article>
        <article className={styles.metric}>
          <span>Paid leads</span>
          <strong>{dashboard.summary.new_paid_leads}</strong>
          <small>New paid sources</small>
        </article>
      </section>

      <section className={styles.panel}>
        <div className={styles.panelHeader}>
          <h3>All Seller Leads</h3>
          <span>{dashboard.leads.length} records</span>
        </div>
        <div className={styles.tableWrap}>
          <table>
            <thead>
              <tr>
                <th>Seller</th>
                <th>Stage</th>
                <th>Source</th>
                <th>Qualification</th>
                <th>Appointment</th>
                <th>Next Follow-Up</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.leads.length === 0 ? (
                <tr>
                  <td>No live seller leads yet</td>
                  <td>Waiting</td>
                  <td>Website</td>
                  <td>0/3</td>
                  <td>None</td>
                  <td>Unscheduled</td>
                </tr>
              ) : null}
              {dashboard.leads.map((lead) => (
                <tr key={lead.id}>
                  <td>
                    <Link className={styles.tableLink} href={`/leads/${lead.id}`}>
                      {lead.seller_name}
                    </Link>
                    <small className={styles.tableSubtext}>{lead.property_address}</small>
                  </td>
                  <td>{labelize(lead.stage_key)}</td>
                  <td>{labelize(lead.source)}</td>
                  <td>{qualificationFieldCount(lead)}/3</td>
                  <td>{labelize(lead.appointment_status)}</td>
                  <td>{formatDateTime(lead.next_follow_up_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
