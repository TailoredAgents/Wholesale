import Link from "next/link";

import { getArchivedLeads } from "../../../lib/api";
import { formatDateTime } from "../../os-utils";
import styles from "../../page.module.css";
import { LeadLifecycleActions } from "../lead-lifecycle-actions";

export const dynamic = "force-dynamic";

export default async function ArchivedLeadsPage() {
  const { leads, apiConnected } = await getArchivedLeads();

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Leads</p>
          <h2>Archived leads</h2>
        </div>
        <Link className={styles.headerAction} href="/os/leads">
          Back to active leads
        </Link>
      </header>

      <section className={styles.panel}>
        <div className={`${styles.panelHeader} ${styles.archivePanelHeader}`}>
          <div>
            <h3>Archived records</h3>
            <small>Restore records or permanently remove confirmed test entries.</small>
          </div>
          <span>{leads.length} records</span>
        </div>
        {!apiConnected ? <p className={styles.panelMessage}>Archived leads are unavailable.</p> : null}
        <div className={`${styles.tableWrap} ${styles.archiveTable}`}>
          <table>
            <thead>
              <tr>
                <th>Seller</th>
                <th>Property</th>
                <th>Archived</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {apiConnected && leads.length === 0 ? (
                <tr>
                  <td colSpan={4}>No archived leads</td>
                </tr>
              ) : null}
              {leads.map((lead) => (
                <tr key={lead.id}>
                  <td data-label="Seller">{lead.seller_name}</td>
                  <td data-label="Property">{lead.property_address}</td>
                  <td data-label="Archived">{formatDateTime(lead.archived_at)}</td>
                  <td data-label="Actions">
                    <LeadLifecycleActions archived compact leadId={lead.id} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
