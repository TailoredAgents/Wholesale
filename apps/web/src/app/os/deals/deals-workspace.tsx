"use client";

import {
  AlertTriangle,
  ArrowRight,
  Banknote,
  CalendarClock,
  CheckCircle2,
  Columns3,
  FileCheck2,
  List,
  Rows3,
  UserRoundCheck,
  UsersRound,
} from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import type {
  DealOverview,
  DealQueueItem,
  DispositionOverview,
  TransactionOverview,
} from "../../lib/api";
import { labelize } from "../os-utils";
import { DispositionWorkspace } from "../dispositions/disposition-workspace";
import { TransactionWorkspace } from "../transactions/transaction-workspace";
import styles from "./deals.module.css";

type DealTab = "summary" | "contract" | "closing" | "documents" | "parties" | "disposition" | "finance" | "timeline";
type DealView = "all" | "closing-exceptions" | "ready-for-disposition" | "buyer-needed" | "finance-review" | "completed" | "disposition";
type DispositionTab = "package" | "buyers" | "execution" | "outreach" | "offers" | "provider" | "reconciliation";
type Display = "queue" | "table" | "board";

const views: Array<{ key: DealView; label: string }> = [
  { key: "all", label: "Active" },
  { key: "closing-exceptions", label: "Closing exceptions" },
  { key: "ready-for-disposition", label: "Ready for disposition" },
  { key: "buyer-needed", label: "Buyer needed" },
  { key: "finance-review", label: "Finance review" },
  { key: "completed", label: "Completed" },
  { key: "disposition", label: "Disposition desk" },
];

const tabs: Array<{ key: DealTab; label: string }> = [
  { key: "summary", label: "Summary" },
  { key: "contract", label: "Contract" },
  { key: "closing", label: "Closing" },
  { key: "documents", label: "Documents" },
  { key: "parties", label: "Parties" },
  { key: "disposition", label: "Disposition" },
  { key: "finance", label: "Finance" },
  { key: "timeline", label: "Timeline" },
];

function money(cents: number | null) {
  return cents == null ? "Not set" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(cents / 100);
}

function shortDate(value: string | null) {
  return value ? new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "Not set";
}

function tone(status: string) {
  if (["executed", "funded", "approved", "closed"].includes(status)) return "success";
  if (["cancelled", "reconciliation_required"].includes(status)) return "danger";
  if (["approval_pending", "awaiting_signature", "draft", "ready_for_reconciliation"].includes(status)) return "warning";
  return "neutral";
}

function Status({ label, value }: { label: string; value: string }) {
  return <div className={styles.statusCell}><span>{label}</span><strong data-tone={tone(value)}>{labelize(value)}</strong></div>;
}

function includesView(item: DealQueueItem, view: DealView) {
  if (view === "disposition") return item.disposition_case_id !== null && !["funded", "cancelled"].includes(item.closing_status);
  if (view === "completed") return ["funded", "cancelled"].includes(item.closing_status);
  if (["funded", "cancelled"].includes(item.closing_status)) return false;
  if (view === "closing-exceptions") return item.blockers.some((blocker) => blocker.domain === "closing");
  if (view === "ready-for-disposition") return item.disposition_status === "ready_to_open";
  if (view === "buyer-needed") return ["buyer_matching", "marketing", "offer_review"].includes(item.disposition_status) && !item.selected_buyer_name;
  if (view === "finance-review") return ["draft", "ready_for_reconciliation", "reconciliation_required"].includes(item.finance_status);
  return true;
}

function boardColumn(item: DealQueueItem) {
  if (["funded", "cancelled"].includes(item.closing_status)) return "Complete";
  if (item.contract_status !== "executed") return "Contract";
  if (item.blockers.some((blocker) => blocker.domain === "closing")) return "Closing";
  if (
    item.disposition_status === "ready_to_open" ||
    (["buyer_matching", "marketing", "offer_review"].includes(item.disposition_status) &&
      !item.selected_buyer_name)
  ) return "Disposition";
  if (["draft", "ready_for_reconciliation", "reconciliation_required"].includes(item.finance_status)) return "Finance";
  return "Closing";
}

function hrefFor(current: { deal?: string; display: Display; tab: DealTab; view: DealView }, patch: Partial<typeof current>) {
  const value = { ...current, ...patch };
  const params = new URLSearchParams({ display: value.display, tab: value.tab, view: value.view });
  if (value.deal) params.set("deal", value.deal);
  return `/os/deals?${params.toString()}`;
}

export function DealsWorkspace({
  canApproveBuyerSelection,
  canEditBuyers,
  canEditDeals,
  canManageOutreach,
  canApproveOutreach,
  canSendBulk,
  canViewDisposition,
  canViewOutreach,
  deals,
  dispositions,
  initialDealId,
  initialDisplay,
  initialDispositionTab,
  initialTab,
  initialView,
  transactions,
}: {
  canApproveBuyerSelection: boolean;
  canEditBuyers: boolean;
  canEditDeals: boolean;
  canManageOutreach: boolean;
  canApproveOutreach: boolean;
  canSendBulk: boolean;
  canViewDisposition: boolean;
  canViewOutreach: boolean;
  deals: DealOverview;
  dispositions: DispositionOverview | null;
  initialDealId?: string;
  initialDisplay?: string;
  initialDispositionTab?: string;
  initialTab?: string;
  initialView?: string;
  transactions: TransactionOverview | null;
}) {
  const view = views.some((item) => item.key === initialView) ? initialView as DealView : "all";
  const display = ["queue", "table", "board"].includes(initialDisplay ?? "") ? initialDisplay as Display : "queue";
  const tab = tabs.some((item) => item.key === initialTab) ? initialTab as DealTab : "summary";
  const requestedDispositionTab = (["package", "buyers", "execution", "outreach", "offers", "provider", "reconciliation"] as DispositionTab[]).includes(initialDispositionTab as DispositionTab)
    ? initialDispositionTab as DispositionTab
    : "package";
  const dispositionTab = requestedDispositionTab === "outreach" && !canViewOutreach
    ? "package"
    : requestedDispositionTab;
  const filtered = useMemo(() => deals.items.filter((item) => includesView(item, view)), [deals.items, view]);
  const selected = deals.items.find((item) => item.id === initialDealId) ?? filtered[0] ?? null;
  const current = { deal: selected?.id, display, tab, view };
  const counts = Object.fromEntries(views.map((item) => [item.key, deals.items.filter((deal) => includesView(deal, item.key)).length]));
  const availableViews = canViewDisposition ? views : views.filter((item) => item.key !== "disposition");

  return (
    <div className={styles.workspace}>
      <section aria-label="Deal summary" className={styles.metrics}>
        <div><FileCheck2 size={18} /><span>Active deals</span><strong>{deals.metrics.active}</strong></div>
        <div><AlertTriangle size={18} /><span>Closing exceptions</span><strong>{deals.metrics.closing_exceptions}</strong></div>
        <div><UsersRound size={18} /><span>Buyer needed</span><strong>{deals.metrics.buyer_needed}</strong></div>
        <div><Banknote size={18} /><span>Finance review</span><strong>{deals.metrics.finance_review}</strong></div>
        <div><CheckCircle2 size={18} /><span>Completed</span><strong>{deals.metrics.completed}</strong></div>
      </section>

      <section className={styles.index}>
        <header className={styles.indexHeader}>
          <nav aria-label="Saved deal views" className={styles.savedViews}>
            {availableViews.map((item) => <Link className={view === item.key ? styles.activeView : ""} href={item.key === "disposition" ? "/os/deals?view=disposition" : hrefFor(current, { deal: undefined, view: item.key })} key={item.key}>{item.label}<span>{counts[item.key]}</span></Link>)}
          </nav>
          <div className={styles.displaySwitch} aria-label="Deal display">
            <Link aria-label="Queue view" className={display === "queue" ? styles.activeDisplay : ""} href={hrefFor(current, { display: "queue" })} title="Queue"><List size={16} /></Link>
            <Link aria-label="Table view" className={display === "table" ? styles.activeDisplay : ""} href={hrefFor(current, { display: "table" })} title="Table"><Rows3 size={16} /></Link>
            <Link aria-label="Board view" className={display === "board" ? styles.activeDisplay : ""} href={hrefFor(current, { display: "board" })} title="Board"><Columns3 size={16} /></Link>
          </div>
        </header>

        {filtered.length === 0 ? <div className={styles.empty}><CheckCircle2 size={24} /><strong>No deals in this view</strong><span>Choose another saved view to continue.</span></div> : null}
        {display === "queue" && filtered.length ? <div className={styles.queue}>{filtered.map((item) => <Link className={selected?.id === item.id ? styles.selectedRow : styles.queueRow} href={hrefFor(current, { deal: item.id })} key={item.id}><div><strong>{item.property_address}</strong><span>{item.seller_name}</span></div><Status label="Contract" value={item.contract_status} /><Status label="Closing" value={item.closing_status} /><Status label="Disposition" value={item.disposition_status} /><div className={styles.next}><span>Next action</span><strong>{item.primary_next_action?.title ?? item.blockers[0]?.label ?? "Monitor deal"}</strong></div><ArrowRight size={16} /></Link>)}</div> : null}
        {display === "table" && filtered.length ? <div className={styles.tableWrap}><table><thead><tr><th>Property / seller</th><th>Contract</th><th>Closing</th><th>Disposition</th><th>Finance</th><th>Close</th><th>Owner</th><th /></tr></thead><tbody>{filtered.map((item) => <tr key={item.id}><td><strong>{item.property_address}</strong><span>{item.seller_name}</span></td><td>{labelize(item.contract_status)}</td><td>{labelize(item.closing_status)}</td><td>{labelize(item.disposition_status)}</td><td>{labelize(item.finance_status)}</td><td>{shortDate(item.closing_date)}</td><td>{item.coordinator_name ?? item.owner_name ?? "Unassigned"}</td><td><Link aria-label={`Open ${item.property_address}`} href={hrefFor(current, { deal: item.id })}><ArrowRight size={16} /></Link></td></tr>)}</tbody></table></div> : null}
        {display === "board" && filtered.length ? <div className={styles.board}>{["Contract", "Closing", "Disposition", "Finance", "Complete"].map((column) => { const columnItems = filtered.filter((item) => boardColumn(item) === column); return <section key={column}><header><strong>{column}</strong><span>{columnItems.length}</span></header>{columnItems.map((item) => <Link href={hrefFor(current, { deal: item.id })} key={item.id}><strong>{item.property_address}</strong><span>{item.seller_name}</span><small>{item.blockers[0]?.label ?? "On track"}</small></Link>)}</section>; })}</div> : null}
      </section>

      {selected ? <section className={styles.record}>
        <header className={styles.recordHeader}>
          <div><span>{labelize(selected.stage_key)}</span><h2>{selected.property_address}</h2><p>{selected.seller_name} - {labelize(selected.property_type ?? "property type not recorded")}</p></div>
          <div className={styles.recordLinks}><Link href={`/os/leads/${selected.lead_id}?returnTo=${encodeURIComponent(hrefFor(current, {}))}`}>Seller lead</Link><strong>{money(selected.contract_price_cents)}</strong><span>Contract price</span></div>
        </header>
        <div className={styles.statusStrip}>
          <Status label="Contract" value={selected.contract_status} />
          <Status label="Closing" value={selected.closing_status} />
          <Status label="Disposition" value={selected.disposition_status} />
          <Status label="Finance" value={selected.finance_status} />
        </div>
        <nav aria-label="Deal record sections" className={styles.tabs}>{tabs.map((item) => <Link className={tab === item.key ? styles.activeTab : ""} href={hrefFor(current, { tab: item.key })} key={item.key}>{item.label}</Link>)}</nav>
        <div className={styles.recordBody}>
          {tab === "summary" ? <DealSummary canViewEconomics={deals.can_view_economics} deal={selected} /> : null}
          {["contract", "closing", "documents", "parties", "timeline"].includes(tab) && transactions ? <TransactionWorkspace initialData={transactions} initialTab={tab as "contract" | "closing" | "documents" | "parties" | "timeline"} initialTransactionId={selected.transaction_id} key={`${selected.transaction_id}-${tab}`} /> : null}
          {["contract", "closing", "documents", "parties", "timeline"].includes(tab) && !transactions ? <SubsystemUnavailable label="Transaction details" /> : null}
          {tab === "disposition" && selected.disposition_case_id && dispositions ? <DispositionWorkspace canApproveBuyerSelection={canApproveBuyerSelection} canApproveOutreach={canApproveOutreach} canEditBuyers={canEditBuyers} canEditDeals={canEditDeals} canManageOutreach={canManageOutreach} canSendBulk={canSendBulk} canViewOutreach={canViewOutreach} dealId={selected.id} initialCaseId={selected.disposition_case_id} initialData={dispositions} initialTab={dispositionTab} key={`${selected.disposition_case_id}-${dispositionTab}`} /> : null}
          {tab === "finance" && selected.disposition_case_id && dispositions ? <DispositionWorkspace canApproveBuyerSelection={canApproveBuyerSelection} canApproveOutreach={canApproveOutreach} canEditBuyers={canEditBuyers} canEditDeals={canEditDeals} canManageOutreach={canManageOutreach} canSendBulk={canSendBulk} canViewOutreach={canViewOutreach} dealId={selected.id} initialCaseId={selected.disposition_case_id} initialData={dispositions} initialTab="reconciliation" key={`${selected.disposition_case_id}-finance`} /> : null}
          {(tab === "disposition" || tab === "finance") && selected.disposition_case_id && !dispositions ? <SubsystemUnavailable label="Disposition details" /> : null}
          {(tab === "disposition" || tab === "finance") && !selected.disposition_case_id ? <div className={styles.contextEmpty}><UsersRound size={24} /><strong>Disposition has not started</strong><p>Open a disposition case after the purchase agreement is executed. The existing transaction remains the source record.</p><Link href={`/os/dispositions?transaction=${selected.transaction_id}`}>Open disposition setup <ArrowRight size={15} /></Link></div> : null}
        </div>
      </section> : null}
    </div>
  );
}

function SubsystemUnavailable({ label }: { label: string }) {
  return <div className={styles.contextEmpty}><AlertTriangle size={24} /><strong>{label} unavailable</strong><p>The active record could not be loaded. Refresh the page or check the API connection.</p></div>;
}

function DealSummary({ canViewEconomics, deal }: { canViewEconomics: boolean; deal: DealQueueItem }) {
  return <div className={styles.summaryGrid}>
    <section><header><div><span>Primary work</span><h3>Next action</h3></div><CalendarClock size={18} /></header><div className={styles.primaryAction}><strong>{deal.primary_next_action?.title ?? deal.blockers[0]?.label ?? "Monitor deal through closing"}</strong><span>{deal.primary_next_action?.responsible_user_email ?? deal.coordinator_name ?? deal.owner_name ?? "Owner not assigned"}</span><small>{deal.primary_next_action?.due_at ? `Due ${shortDate(deal.primary_next_action.due_at)}` : `Next deadline ${shortDate(deal.next_deadline)}`}</small></div></section>
    <section><header><div><span>Control center</span><h3>Active blockers</h3></div><AlertTriangle size={18} /></header><div className={styles.blockers}>{deal.blockers.length ? deal.blockers.map((item) => <div key={item.key}><span data-severity={item.severity} /><strong>{item.label}</strong><small>{labelize(item.domain)}</small></div>) : <p><CheckCircle2 size={16} /> No active blockers</p>}</div></section>
    <section><header><div><span>Execution</span><h3>Deal evidence</h3></div><FileCheck2 size={18} /></header><dl><div><dt>Closing date</dt><dd>{shortDate(deal.closing_date)}</dd></div><div><dt>Checklist</dt><dd>{deal.checklist_complete}/{deal.checklist_total}</dd></div><div><dt>Documents</dt><dd>{deal.document_count}</dd></div><div><dt>Buyer matches</dt><dd>{deal.buyer_match_count}</dd></div><div><dt>Buyer offers</dt><dd>{deal.buyer_offer_count}</dd></div><div><dt>Selected buyer</dt><dd>{deal.selected_buyer_name ?? "Not selected"}</dd></div></dl></section>
    <section><header><div><span>Economics</span><h3>Deal outcome</h3></div><Banknote size={18} /></header>{canViewEconomics ? <dl><div><dt>Contract price</dt><dd>{money(deal.contract_price_cents)}</dd></div><div><dt>Assignment fee</dt><dd>{money(deal.assignment_fee_cents)}</dd></div><div><dt>Company profit</dt><dd>{deal.company_profit_cents == null ? "Not reconciled" : money(deal.company_profit_cents)}</dd></div><div><dt>Company margin</dt><dd>{deal.company_margin_basis_points == null ? "Not reconciled" : `${(deal.company_margin_basis_points / 100).toFixed(0)}%`}</dd></div></dl> : <div className={styles.restricted}><UserRoundCheck size={22} /><strong>Financial details restricted</strong><span>Deal status remains visible for coordination.</span></div>}</section>
  </div>;
}
