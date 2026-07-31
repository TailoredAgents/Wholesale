import {
  AlertTriangle,
  ArrowRight,
  CheckCheck,
  FileCheck2,
  Handshake,
} from "lucide-react";
import Link from "next/link";

import {
  getApprovalRequests,
  getDispositionOverview,
  getTransactionOverview,
  getWorkspaceProfile,
} from "../../lib/api";
import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { StatusBadge } from "../_components/design-system";
import { isOwnerProfile } from "../os-navigation";
import styles from "../_components/workspace-hub.module.css";

export const dynamic = "force-dynamic";

export default async function DealsPage() {
  const [transactionResult, dispositionResult, approvalResult, profile] = await Promise.all([
    getTransactionOverview(),
    getDispositionOverview(),
    getApprovalRequests(),
    getWorkspaceProfile(),
  ]);
  const owner = profile ? isOwnerProfile(profile) : false;
  const canViewDeals = owner || Boolean(profile?.permissions.includes("deals:view"));
  const canViewApprovals =
    owner ||
    Boolean(
      profile?.permissions.some((permission) =>
        ["offers:approve", "contracts:send"].includes(permission),
      ),
    );
  const transactions = transactionResult.transactions;
  const dispositions = dispositionResult.dispositions;
  const pendingApprovals = approvalResult.approvals.filter(
    (approval) => approval.status === "pending",
  );

  return (
    <WorkspacePage>
      <PageHeader
        description="Contracts, closing work, buyer placement, and controlled decisions for active deals."
        eyebrow="Operations"
        meta={
          <StatusBadge tone={canViewDeals ? "success" : "warning"}>
            {canViewDeals ? "Deal access active" : "Limited access"}
          </StatusBadge>
        }
        title="Deals"
      />

      <section aria-label="Deal summary" className={styles.metricStrip}>
        <div>
          <FileCheck2 aria-hidden="true" size={18} />
          <span>Active transactions</span>
          <strong>{transactions?.metrics.active ?? 0}</strong>
        </div>
        <div>
          <Handshake aria-hidden="true" size={18} />
          <span>Active dispositions</span>
          <strong>{dispositions?.metrics.active_cases ?? 0}</strong>
        </div>
        <div>
          <CheckCheck aria-hidden="true" size={18} />
          <span>Pending approvals</span>
          <strong>{pendingApprovals.length}</strong>
        </div>
        <div>
          <AlertTriangle aria-hidden="true" size={18} />
          <span>Overdue closings</span>
          <strong>{transactions?.metrics.overdue ?? 0}</strong>
        </div>
      </section>

      <div className={styles.hubGrid}>
        {canViewDeals ? (
          <section className={styles.hubSection}>
            <header>
              <div>
                <span>Closing</span>
                <h2>Transactions</h2>
                <p>Contract evidence, deadlines, title work, funding, and closing status.</p>
              </div>
              <StatusBadge tone={transactions?.metrics.overdue ? "danger" : "success"}>
                {transactions?.metrics.overdue
                  ? `${transactions.metrics.overdue} overdue`
                  : "No overdue closings"}
              </StatusBadge>
            </header>
            <Link className={styles.primaryRow} href="/os/transactions">
              <div>
                <strong>Open transaction workspace</strong>
                <span>
                  {transactions?.metrics.due_next_seven_days ?? 0} deadlines due in the next 7 days
                </span>
              </div>
              <ArrowRight aria-hidden="true" size={17} />
            </Link>
          </section>
        ) : null}

        {canViewDeals ? (
          <section className={styles.hubSection}>
            <header>
              <div>
                <span>Buyer placement</span>
                <h2>Dispositions</h2>
                <p>Deal packages, buyer matches, offers, selection, and reconciliation.</p>
              </div>
              <StatusBadge tone={dispositions?.metrics.packages_pending ? "warning" : "neutral"}>
                {dispositions?.metrics.packages_pending ?? 0} packages pending
              </StatusBadge>
            </header>
            <Link className={styles.primaryRow} href="/os/dispositions">
              <div>
                <strong>Open disposition workspace</strong>
                <span>
                  {dispositions?.metrics.buyer_selected ?? 0} cases have a selected buyer
                </span>
              </div>
              <ArrowRight aria-hidden="true" size={17} />
            </Link>
          </section>
        ) : null}

        {canViewApprovals ? (
          <section className={styles.hubSection}>
            <header>
              <div>
                <span>Control gate</span>
                <h2>Approvals</h2>
                <p>Review the source evidence before authorizing controlled deal actions.</p>
              </div>
              <StatusBadge tone={pendingApprovals.length ? "warning" : "success"}>
                {pendingApprovals.length} pending
              </StatusBadge>
            </header>
            <Link className={styles.primaryRow} href="/os/tasks?view=approvals">
              <div>
                <strong>Open approval queue</strong>
                <span>Decisions remain attached to their source records and audit history</span>
              </div>
              <ArrowRight aria-hidden="true" size={17} />
            </Link>
          </section>
        ) : null}
      </div>
    </WorkspacePage>
  );
}
