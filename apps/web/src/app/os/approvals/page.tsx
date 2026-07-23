import { AlertTriangle, ArrowRight, CheckCheck, Clock3, FileCheck2 } from "lucide-react";
import Link from "next/link";

import { getApprovalRequests, getDashboardData, getWorkspaceProfile } from "../../lib/api";
import { DealControlStrip } from "../_components/deal-control-strip";
import { DealJourney } from "../_components/deal-journey";
import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { StatusBadge } from "../_components/design-system";
import { formatDateTime, labelize } from "../os-utils";
import { ApprovalDecisionButtons } from "./approval-decision-buttons";
import styles from "../_components/deal-workspaces.module.css";
import approvalStyles from "./approvals.module.css";

export const dynamic = "force-dynamic";

function metadataEntries(metadata: Record<string, unknown>) {
  return Object.entries(metadata)
    .filter(([key, value]) =>
      value !== null &&
      value !== undefined &&
      typeof value !== "object" &&
      !key.endsWith("_id"),
    )
    .slice(0, 8);
}

function metadataValue(key: string, value: unknown) {
  if (key.endsWith("_cents") && typeof value === "number") {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    }).format(value / 100);
  }
  return String(value);
}

export default async function ApprovalsPage({
  searchParams,
}: {
  searchParams: Promise<{ approval?: string }>;
}) {
  const [dashboard, approvalData, profile, params] = await Promise.all([
    getDashboardData(),
    getApprovalRequests(),
    getWorkspaceProfile(),
    searchParams,
  ]);
  const approvals = approvalData.approvals;
  const pending = approvals.filter((approval) => approval.status === "pending");
  const selected = approvals.find((item) => item.id === params.approval) ?? pending[0] ?? approvals[0] ?? null;
  const sellerOffers = dashboard.leads.filter((lead) =>
    ["offer_pending_approval", "offer_ready"].includes(lead.stage_key),
  );
  const canDecide = Boolean(
    profile?.permissions.some((permission) =>
      ["audit:view", "offers:approve", "contracts:send"].includes(permission),
    ),
  );
  const overdue = pending.filter((item) => item.due_at && new Date(item.due_at) < new Date()).length;

  return (
    <WorkspacePage>
      <PageHeader
        description="Review evidence, understand the consequence, and record an authorized decision."
        eyebrow="Deal flow / control gate"
        meta={<StatusBadge tone={approvalData.apiConnected ? "success" : "danger"}>{approvalData.apiConnected ? `${pending.length} pending` : "Queue unavailable"}</StatusBadge>}
        title="Approvals"
      />
      <DealJourney active="approvals" />
      <DealControlStrip
        authority={{ label: "Decision authority", value: canDecide ? "Authorized reviewer" : "View only", detail: profile?.display_name ?? "Permission check unavailable", tone: canDecide ? "success" : "warning" }}
        blocker={{ label: "Primary blocker", value: selected?.status === "pending" ? "Human decision required" : "No selected blocker", detail: selected?.title ?? "Queue clear", tone: selected?.status === "pending" ? "warning" : "success" }}
        deadline={{ label: "Deadline risk", value: overdue ? `${overdue} overdue` : "No overdue reviews", detail: selected?.due_at ? formatDateTime(selected.due_at) : "No selected deadline", tone: overdue ? "danger" : "success" }}
        evidence={{ label: "Review context", value: selected ? labelize(selected.request_type) : "No request selected", detail: selected?.entity_type ? `Applies to ${labelize(selected.entity_type)}` : "No active entity", tone: selected ? "info" : "neutral" }}
        nextAction={{ label: "Authorized next step", value: selected?.review_url ? "Open source record" : selected?.status === "pending" && canDecide ? "Approve or reject" : "No action", detail: "Every decision is audited", tone: selected?.status === "pending" ? "success" : "neutral" }}
      />

      <section className={styles.metricRibbon} aria-label="Approval queue summary">
        <div><Clock3 size={17} /><span>Pending requests</span><strong>{pending.length}</strong></div>
        <div><AlertTriangle size={17} /><span>Overdue</span><strong>{overdue}</strong></div>
        <div><FileCheck2 size={17} /><span>Seller offers</span><strong>{sellerOffers.length}</strong></div>
        <div><CheckCheck size={17} /><span>Decided</span><strong>{approvals.length - pending.length}</strong></div>
      </section>

      <section className={styles.splitWorkspace}>
        <aside className={styles.queue} aria-label="Approval requests">
          <header><div><span>Decision queue</span><strong>{approvals.length} requests</strong></div></header>
          {approvals.length === 0 ? <p className={styles.empty}>No approval requests are waiting.</p> : null}
          {approvals.map((approval) => (
            <Link className={selected?.id === approval.id ? styles.selectedRow : styles.queueRow} href={`/os/approvals?approval=${approval.id}`} key={approval.id}>
              <div><strong>{approval.title}</strong><StatusBadge tone={approval.status === "pending" ? "warning" : approval.status === "approved" ? "success" : "neutral"}>{labelize(approval.status)}</StatusBadge></div>
              <span>{approval.summary}</span>
              <dl><div><dt>Type</dt><dd>{labelize(approval.request_type)}</dd></div><div><dt>Due</dt><dd>{approval.due_at ? formatDateTime(approval.due_at) : "No deadline"}</dd></div></dl>
            </Link>
          ))}
        </aside>

        <main className={styles.detail}>
          {selected ? <>
            <header className={styles.detailHeader}><div><span>{labelize(selected.request_type)}</span><h2>{selected.title}</h2><p>{selected.summary}</p></div>{selected.review_url ? <Link className={styles.primaryLink} href={selected.review_url}>Open evidence <ArrowRight size={15} /></Link> : null}</header>
            <div className={styles.detailGrid}>
              <section className={styles.section}>
                <header><div><span>Decision record</span><h3>Evidence and consequence</h3></div><StatusBadge tone={selected.status === "pending" ? "warning" : selected.status === "approved" ? "success" : "neutral"}>{labelize(selected.status)}</StatusBadge></header>
                <dl className={styles.factList}>
                  <div><dt>Request type</dt><dd>{labelize(selected.request_type)}</dd></div>
                  <div><dt>Affected record</dt><dd>{labelize(selected.entity_type)}</dd></div>
                  <div><dt>Created</dt><dd>{formatDateTime(selected.created_at)}</dd></div>
                  <div><dt>Decision due</dt><dd>{selected.due_at ? formatDateTime(selected.due_at) : "No deadline"}</dd></div>
                  <div><dt>Consequence</dt><dd>{selected.status === "pending" ? "Workflow remains blocked" : `Workflow may continue: ${labelize(selected.status)}`}</dd></div>
                  {metadataEntries(selected.approval_metadata).map(([key, value]) => <div key={key}><dt>{labelize(key.replace(/_cents$/, ""))}</dt><dd>{metadataValue(key, value)}</dd></div>)}
                </dl>
              </section>
              <aside className={approvalStyles.decisionPanel}>
                <header><div><span>Human authority</span><h3>Record decision</h3></div></header>
                <div><p>Approval permits the next controlled workflow step. Rejection preserves the record and returns it for correction.</p>
                  {selected.status === "pending" && canDecide && !selected.review_url ? <ApprovalDecisionButtons approvalId={selected.id} /> : null}
                  {selected.status === "pending" && selected.review_url ? <Link className={styles.secondaryLink} href={selected.review_url}>Review at source</Link> : null}
                  {selected.status === "pending" && !canDecide ? <StatusBadge tone="warning">Your role cannot decide this request</StatusBadge> : null}
                  {selected.status !== "pending" ? <p><strong>{labelize(selected.status)}</strong><br />{selected.decision_notes ?? "Decision recorded without notes."}</p> : null}
                </div>
              </aside>
            </div>
          </> : <div className={styles.emptyState}><CheckCheck size={24} /><h2>Approval queue clear</h2><p>Controlled requests will appear here with their source evidence and consequences.</p></div>}
        </main>
      </section>

      {sellerOffers.length ? <section className={styles.section}><header><div><span>Seller offers</span><h3>Deals approaching approval</h3></div><strong>{sellerOffers.length} deals</strong></header><div className={approvalStyles.offerGrid}>{sellerOffers.map((lead) => <Link href={`/os/leads/${lead.id}#underwriting`} key={lead.id}><div><strong>{lead.seller_name}</strong><StatusBadge tone="info">{labelize(lead.stage_key)}</StatusBadge></div><span>{lead.property_address}</span><small>{lead.asking_price ? `Seller asks ${lead.asking_price}` : "Seller asking price missing"}</small></Link>)}</div></section> : null}
    </WorkspacePage>
  );
}
