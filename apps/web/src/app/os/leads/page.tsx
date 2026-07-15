import Link from "next/link";

import { getDashboardData } from "../../lib/api";
import {
  formatDateTime,
  getFilteredLeads,
  getLeadOperatingStatus,
  getSavedLeadViewCounts,
  labelize,
  normalizeLeadViewKey,
  qualificationFieldCount,
  qualificationFieldTarget,
  savedLeadViews,
} from "../os-utils";
import styles from "../page.module.css";

export const dynamic = "force-dynamic";

type LeadsPageProps = {
  searchParams?: Promise<{ view?: string | string[] }>;
};

export default async function LeadsPage({ searchParams }: LeadsPageProps) {
  const params = await searchParams;
  const dashboard = await getDashboardData();
  const selectedViewKey = normalizeLeadViewKey(params?.view);
  const selectedView = savedLeadViews.find((view) => view.key === selectedViewKey);
  const savedViews = getSavedLeadViewCounts(dashboard.leads, dashboard.openTaskQueue);
  const filteredLeads = getFilteredLeads(
    dashboard.leads,
    dashboard.openTaskQueue,
    selectedViewKey,
  );
  const newLeads = dashboard.leads.filter((lead) => lead.stage_key === "new");
  const qualifiedLeads = dashboard.leads.filter((lead) =>
    ["qualified", "appointment_scheduled", "underwriting", "offer_ready"].includes(lead.stage_key),
  );
  const noFollowUpLeads = dashboard.leads.filter(
    (lead) => !lead.next_follow_up_at && !["dead", "disqualified"].includes(lead.stage_key),
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
        <article className={styles.metric}>
          <span>No follow-up</span>
          <strong>{noFollowUpLeads.length}</strong>
          <small>Needs next dated action</small>
        </article>
      </section>

      <section className={styles.savedViews} aria-label="Saved lead views">
        {savedViews.map((view) => (
          <Link
            className={view.key === selectedViewKey ? styles.activeViewTab : styles.viewTab}
            href={view.key === "all" ? "/os/leads" : `/os/leads?view=${view.key}`}
            key={view.key}
          >
            <span>{view.label}</span>
            <strong>{view.count}</strong>
          </Link>
        ))}
      </section>

      <section className={styles.panel}>
        <div className={styles.panelHeader}>
          <div>
            <h3>{selectedView?.label ?? "All Leads"}</h3>
            <small>{selectedView?.description}</small>
          </div>
          <span>
            {filteredLeads.length} of {dashboard.leads.length} records
          </span>
        </div>
        <div className={styles.tableWrap}>
          <table>
            <thead>
              <tr>
                <th>Seller</th>
                <th>Operating Status</th>
                <th>Stage</th>
                <th>Source</th>
                <th>Qualification</th>
                <th>Next Follow-Up</th>
                <th>Owner</th>
              </tr>
            </thead>
            <tbody>
              {filteredLeads.length === 0 ? (
                <tr>
                  <td>No leads in this view</td>
                  <td>Clear</td>
                  <td>Waiting</td>
                  <td>Website</td>
                  <td>
                    0/{qualificationFieldTarget}
                  </td>
                  <td>Unscheduled</td>
                  <td>Unassigned</td>
                </tr>
              ) : null}
              {filteredLeads.map((lead) => (
                <tr key={lead.id}>
                  <td>
                    <Link className={styles.tableLink} href={`/os/leads/${lead.id}`}>
                      {lead.seller_name}
                    </Link>
                    <small className={styles.tableSubtext}>{lead.property_address}</small>
                  </td>
                  <td>
                    <span className={styles.leadStatus}>
                      {getLeadOperatingStatus(lead, dashboard.openTaskQueue)}
                    </span>
                  </td>
                  <td>{labelize(lead.stage_key)}</td>
                  <td>{labelize(lead.source)}</td>
                  <td>
                    {qualificationFieldCount(lead)}/{qualificationFieldTarget}
                    <small className={styles.tableSubtext}>
                      Appointment: {labelize(lead.appointment_status)}
                    </small>
                  </td>
                  <td>{formatDateTime(lead.next_follow_up_at)}</td>
                  <td>{lead.assigned_user_email ?? "Unassigned"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
