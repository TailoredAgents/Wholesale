import Link from "next/link";

import { getApprovalRequests, getDashboardData } from "../../lib/api";
import { labelize } from "../os-utils";
import { ApprovalDecisionButtons } from "./approval-decision-buttons";
import styles from "../page.module.css";

export const dynamic = "force-dynamic";

export default async function ApprovalsPage() {
  const [dashboard, approvalData] = await Promise.all([
    getDashboardData(),
    getApprovalRequests(),
  ]);
  const approvals = approvalData.approvals;
  const pendingApprovals = approvals.filter((approval) => approval.status === "pending");
  const approvalLeads = dashboard.leads.filter((lead) =>
    ["offer_pending_approval", "offer_ready", "under_contract"].includes(lead.stage_key),
  );

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Approvals</p>
          <h2>Human approval queue</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Approval items</span>
          <strong className={styles.ready}>
            {pendingApprovals.length + approvalLeads.length}
          </strong>
        </div>
      </header>

      <section className={styles.contentGrid}>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Approval Requests</h3>
            <span>{pendingApprovals.length} pending</span>
          </div>
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Request</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Decision</th>
                </tr>
              </thead>
              <tbody>
                {approvals.length === 0 ? (
                  <tr>
                    <td>No approval requests yet</td>
                    <td>None</td>
                    <td>Clear</td>
                    <td>None</td>
                  </tr>
                ) : null}
                {approvals.map((approval) => (
                  <tr key={approval.id}>
                    <td>
                      {approval.title}
                      <small className={styles.tableSubtext}>{approval.summary}</small>
                    </td>
                    <td>{labelize(approval.request_type)}</td>
                    <td>{labelize(approval.status)}</td>
                    <td>
                      {approval.status === "pending" ? (
                        approval.review_url ? (
                          <Link className={styles.tableLink} href={approval.review_url}>
                            Review in inbox
                          </Link>
                        ) : (
                          <ApprovalDecisionButtons approvalId={approval.id} />
                        )
                      ) : (
                        approval.decision_notes ?? "Decided"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Seller Offer Approvals</h3>
            <span>{approvalLeads.length} leads</span>
          </div>
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Seller</th>
                  <th>Stage</th>
                  <th>Temperature</th>
                  <th>Asking</th>
                  <th>Next Follow-Up</th>
                </tr>
              </thead>
              <tbody>
                {approvalLeads.length === 0 ? (
                  <tr>
                    <td>No approval items yet</td>
                    <td>Clear</td>
                    <td>None</td>
                    <td>Unknown</td>
                    <td>Unscheduled</td>
                  </tr>
                ) : null}
                {approvalLeads.map((lead) => (
                  <tr key={lead.id}>
                    <td>
                      <Link className={styles.tableLink} href={`/os/leads/${lead.id}`}>
                        {lead.seller_name}
                      </Link>
                      <small className={styles.tableSubtext}>{lead.property_address}</small>
                    </td>
                    <td>{labelize(lead.stage_key)}</td>
                    <td>{labelize(lead.lead_temperature)}</td>
                    <td>{lead.asking_price ?? "Unknown"}</td>
                    <td>{lead.next_follow_up_at ? "Scheduled" : "Unscheduled"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Approval Types</h3>
            <span>Guardrails</span>
          </div>
          <div className={styles.approvals}>
            <p>ARV approval</p>
            <p>Repair budget approval</p>
            <p>Seller offer ceiling</p>
            <p>Contract send approval</p>
            <p>Buyer selection</p>
            <p>Assignment fee exception</p>
          </div>
        </article>
      </section>
    </>
  );
}
