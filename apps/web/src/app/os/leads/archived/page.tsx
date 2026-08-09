import Link from "next/link";

import { getArchivedLeads, getWorkspaceProfile } from "../../../lib/api";
import { formatDateTime } from "../../os-utils";
import styles from "../../page.module.css";
import { LeadLifecycleActions } from "../lead-lifecycle-actions";

export const dynamic = "force-dynamic";

export default async function ArchivedLeadsPage() {
  const [{ leads, apiConnected }, profile] = await Promise.all([
    getArchivedLeads(),
    getWorkspaceProfile(),
  ]);
  const canArchiveRecords = Boolean(
    profile?.permissions.includes("records:delete_or_archive"),
  );
  const archivedLeads = leads.filter(
    (lead) => !(
      ["dead", "disqualified"].includes(lead.stage_key)
      && lead.close_out_disposition
      && lead.closed_out_at
    ),
  );

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Leads</p>
          <h1>Archived leads</h1>
        </div>
        <Link className={styles.headerAction} href="/os/leads">
          Back to active leads
        </Link>
      </header>

      <section className={styles.panel}>
        <div className={`${styles.panelHeader} ${styles.archivePanelHeader}`}>
          <div>
            <h3>Duplicate and test records</h3>
            <small>
              {canArchiveRecords
                ? "Open retained read-only history, restore a record, or permanently remove confirmed test data."
                : "These duplicate and test records are read only for your role."}
            </small>
          </div>
          <span>{archivedLeads.length} records</span>
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
              {apiConnected && archivedLeads.length === 0 ? (
                <tr>
                  <td colSpan={4}>No archived leads</td>
                </tr>
              ) : null}
              {archivedLeads.map((lead) => (
                <tr key={lead.id}>
                  <td data-label="Seller">
                    <Link
                      className={styles.tableLink}
                      href={`/os/leads/${lead.id}?returnTo=${encodeURIComponent("/os/leads/archived")}`}
                    >
                      {lead.seller_name}
                    </Link>
                  </td>
                  <td data-label="Property">{lead.property_address}</td>
                  <td data-label="Archived">{formatDateTime(lead.archived_at)}</td>
                  <td data-label="Actions">
                    <LeadLifecycleActions
                      archived
                      canArchiveRecords={canArchiveRecords}
                      canEditLead={false}
                      compact
                      leadId={lead.id}
                    />
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
