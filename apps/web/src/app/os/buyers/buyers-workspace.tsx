"use client";

import { useAuth } from "@clerk/nextjs";
import {
  Archive,
  ArchiveRestore,
  BadgeDollarSign,
  Building2,
  ChevronLeft,
  ChevronRight,
  MessageSquare,
  Pencil,
  Plus,
  Search,
  ShieldCheck,
  UsersRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState, useTransition } from "react";

import type { BuyerListItem, BuyerRelationshipOwner, LeadListItem } from "../../lib/api";
import { DealControlStrip } from "../_components/deal-control-strip";
import { Drawer, StatusBadge } from "../_components/design-system";
import { labelize } from "../os-utils";
import { BuyerForm } from "./buyer-form";
import styles from "./buyers.module.css";

function money(cents: number | null) {
  if (cents === null) return "Not set";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(cents / 100);
}

function reliability(buyer: BuyerListItem) {
  return `${(buyer.reliability_score_basis_points / 100).toFixed(0)}%`;
}

function proofVerified(status: string) {
  return status === "received" || status === "verified";
}

function displayDate(value: string | null | undefined, includeTime = false) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not recorded";
  return includeTime ? date.toLocaleString() : date.toLocaleDateString();
}

function permissionLabel(buyer: BuyerListItem, channel: "phone" | "sms") {
  const permission = channel === "phone" ? buyer.phone_permission : buyer.sms_permission;
  return permission.status === "granted" ? "Permission recorded" : labelize(permission.status || "not recorded");
}

type BuyerTab = "summary" | "criteria" | "deals" | "evidence";

const buyerTabs: Array<{ key: BuyerTab; label: string }> = [
  { key: "summary", label: "Summary" },
  { key: "criteria", label: "Criteria & markets" },
  { key: "deals", label: "Active deals" },
  { key: "evidence", label: "Proof & capacity" },
];

type BuyerFilters = { owner: string; q: string; source: string; status: string };

export function BuyersWorkspace({
  apiError,
  buyers,
  canEdit,
  contractLeads,
  initialBuyerId,
  initialFilters,
  initialTab,
  page,
  pageSize,
  relationshipOwners,
  selectedBuyer,
  sourceOptions,
  total,
}: {
  apiError: string | null;
  buyers: BuyerListItem[];
  canEdit: boolean;
  contractLeads: LeadListItem[];
  initialBuyerId?: string;
  initialFilters: BuyerFilters;
  initialTab?: string;
  page: number;
  pageSize: number;
  relationshipOwners: BuyerRelationshipOwner[];
  selectedBuyer: BuyerListItem | null;
  sourceOptions: string[];
  total: number;
}) {
  const detailBuyers = selectedBuyer && !buyers.some((buyer) => buyer.id === selectedBuyer.id)
    ? [selectedBuyer, ...buyers]
    : buyers;
  const [selectedId, setSelectedId] = useState(
    detailBuyers.some((buyer) => buyer.id === initialBuyerId) ? initialBuyerId! : detailBuyers[0]?.id ?? null,
  );
  const [activeTab, setActiveTab] = useState<BuyerTab>(
    buyerTabs.some((tab) => tab.key === initialTab) ? initialTab as BuyerTab : "summary",
  );
  const [mobileDetailOpen, setMobileDetailOpen] = useState(Boolean(initialBuyerId));
  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [showArchive, setShowArchive] = useState(false);
  const [archiveReason, setArchiveReason] = useState("");
  const [actionStatus, setActionStatus] = useState<"idle" | "opening" | "saving" | "error">("idle");
  const [actionError, setActionError] = useState<string | null>(null);
  const [navigating, startNavigation] = useTransition();
  const { getToken } = useAuth();
  const router = useRouter();
  const apiBaseUrl = useMemo(() => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000", []);
  const selected = detailBuyers.find((buyer) => buyer.id === selectedId) ?? detailBuyers[0] ?? null;
  const activeOnPage = buyers.filter((buyer) => buyer.status === "active").length;
  const verifiedOnPage = buyers.filter((buyer) => proofVerified(buyer.proof_of_funds_status)).length;
  const expiredOnPage = buyers.filter((buyer) => buyer.proof_of_funds_status === "expired" || (buyer.proof_of_funds_expires_at && new Date(buyer.proof_of_funds_expires_at) < new Date())).length;
  const blocker = !selected ? "No buyer selected" : selected.status === "archived" ? "Archived relationship" : !proofVerified(selected.proof_of_funds_status) ? "Proof of funds" : !selected.email && !selected.phone ? "Contact method" : !selected.criteria?.markets ? "Buy box criteria" : "No active blocker";
  const totalPages = Math.max(1, Math.ceil(total / Math.max(1, pageSize)));

  function locationFor(overrides: Partial<BuyerFilters> & { buyer?: string | null; page?: number; tab?: BuyerTab } = {}) {
    const values = new URLSearchParams();
    const merged = { ...initialFilters, ...overrides };
    if (merged.q) values.set("q", merged.q);
    if (merged.status) values.set("status", merged.status);
    if (merged.owner) values.set("owner", merged.owner);
    if (merged.source) values.set("source", merged.source);
    const nextPage = overrides.page ?? page;
    if (nextPage > 1) values.set("page", String(nextPage));
    const buyerId = overrides.buyer === undefined ? selected?.id : overrides.buyer;
    if (buyerId) values.set("buyer", buyerId);
    values.set("tab", overrides.tab ?? activeTab);
    return `/os/buyers?${values.toString()}`;
  }

  function selectBuyer(buyerId: string) {
    setSelectedId(buyerId);
    setMobileDetailOpen(true);
    window.history.replaceState(null, "", locationFor({ buyer: buyerId }));
  }

  function selectTab(tab: BuyerTab) {
    setActiveTab(tab);
    window.history.replaceState(null, "", locationFor({ tab }));
  }

  async function getHeaders() {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    else headers["X-Dev-User-Email"] = process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com";
    return headers;
  }

  async function mutationError(response: Response) {
    try {
      const payload = (await response.json()) as { detail?: string | { message?: string } };
      if (typeof payload.detail === "string") return payload.detail;
      if (payload.detail?.message) return payload.detail.message;
    } catch {
      // Use the status fallback below.
    }
    return `Stonegate could not complete this action (HTTP ${response.status}).`;
  }

  async function openConversation() {
    if (!selected) return;
    setActionStatus("opening");
    setActionError(null);
    const response = await fetch(`${apiBaseUrl}/api/v1/buyers/${selected.id}/conversation`, { method: "POST", headers: await getHeaders() });
    if (!response.ok) {
      setActionError(await mutationError(response));
      setActionStatus("error");
      return;
    }
    const payload = (await response.json()) as { conversation_id: string };
    router.push(`/os/inbox?conversation=${payload.conversation_id}`);
  }

  async function archiveBuyer() {
    if (!selected || archiveReason.trim().length < 2 || actionStatus === "saving") return;
    setActionStatus("saving");
    setActionError(null);
    const response = await fetch(`${apiBaseUrl}/api/v1/buyers/${selected.id}/archive`, {
      method: "POST",
      headers: await getHeaders(),
      body: JSON.stringify({ reason: archiveReason.trim() }),
    });
    if (!response.ok) {
      setActionError(await mutationError(response));
      setActionStatus("error");
      return;
    }
    setActionStatus("idle");
    setShowArchive(false);
    setArchiveReason("");
    router.refresh();
  }

  async function restoreBuyer() {
    if (!selected || actionStatus === "saving" || !window.confirm(`Restore ${selected.name} for review? Do-not-contact restrictions remain in place when applicable.`)) return;
    setActionStatus("saving");
    setActionError(null);
    const response = await fetch(`${apiBaseUrl}/api/v1/buyers/${selected.id}/restore`, { method: "POST", headers: await getHeaders() });
    if (!response.ok) {
      setActionError(await mutationError(response));
      setActionStatus("error");
      return;
    }
    setActionStatus("idle");
    router.refresh();
  }

  function submitFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const href = locationFor({
      buyer: null,
      owner: String(data.get("owner") ?? ""),
      page: 1,
      q: String(data.get("q") ?? "").trim(),
      source: String(data.get("source") ?? ""),
      status: String(data.get("status") ?? ""),
    });
    startNavigation(() => router.push(href));
  }

  function useExisting(buyerId: string) {
    setShowCreate(false);
    setShowEdit(false);
    setSelectedId(buyerId);
    setMobileDetailOpen(true);
    router.push(`/os/buyers?buyer=${encodeURIComponent(buyerId)}&tab=summary`);
  }

  return (
    <section aria-label="Buyer management" className={styles.workspace}>
      <DealControlStrip
        authority={{ label: "Authority", value: canEdit ? "Buyer CRM editor" : "View only", detail: canEdit ? "Changes remain audited" : "No edit permission", tone: canEdit ? "success" : "warning" }}
        blocker={{ label: "Primary blocker", value: blocker, detail: selected?.name ?? "No buyer evidence", tone: blocker === "No active blocker" ? "success" : "warning" }}
        deadline={{ label: "Evidence expiry", value: selected?.proof_of_funds_expires_at ? displayDate(selected.proof_of_funds_expires_at) : "Not recorded", detail: `${expiredOnPage} expired on this page`, tone: expiredOnPage ? "danger" : "neutral" }}
        evidence={{ label: "Proof of funds", value: selected ? labelize(selected.proof_of_funds_status) : "No buyer selected", detail: selected ? `${reliability(selected)} reliability` : `${verifiedOnPage} verified on page`, tone: selected && proofVerified(selected.proof_of_funds_status) ? "success" : "warning" }}
        nextAction={{ label: "Authorized next step", value: blocker === "Proof of funds" ? "Verify buyer funds" : blocker === "Buy box criteria" ? "Complete buy box" : contractLeads.length ? "Compare active deals" : "Maintain buyer record", detail: `${contractLeads.length} deals need buyer coverage`, tone: "info" }}
      />

      <section className={styles.metrics} aria-label="Buyer network summary">
        <div><UsersRound size={17} /><span>Matching buyers</span><strong>{total}</strong></div>
        <div><ShieldCheck size={17} /><span>Active on page</span><strong>{activeOnPage}</strong></div>
        <div><Building2 size={17} /><span>Deals needing buyers</span><strong>{contractLeads.length}</strong></div>
        <div><BadgeDollarSign size={17} /><span>Expired POF on page</span><strong>{expiredOnPage}</strong></div>
      </section>

      <form className={styles.toolbar} onSubmit={submitFilters} role="search">
        <label className={styles.searchField}><Search size={15} /><span className={styles.srOnly}>Search buyers</span><input defaultValue={initialFilters.q} name="q" placeholder="Search name, company, phone, or email" type="search" /></label>
        <label><span className={styles.filterLabel}>Status</span><select defaultValue={initialFilters.status} name="status"><option value="">All statuses</option><option value="needs_review">Needs review</option><option value="active">Active</option><option value="paused">Paused</option><option value="do_not_contact">Do not contact</option><option value="archived">Archived</option></select></label>
        <label><span className={styles.filterLabel}>Owner</span><select defaultValue={initialFilters.owner} name="owner"><option value="">All owners</option>{relationshipOwners.map((owner) => <option key={owner.user_id} value={owner.user_id}>{owner.display_name}</option>)}</select></label>
        <label><span className={styles.filterLabel}>Source</span><select defaultValue={initialFilters.source} name="source"><option value="">All sources</option>{sourceOptions.map((source) => <option key={source} value={source}>{labelize(source)}</option>)}</select></label>
        <button disabled={navigating} type="submit">{navigating ? "Loading..." : "Apply"}</button>
        {Object.values(initialFilters).some(Boolean) ? <Link className={styles.clearFilters} href="/os/buyers">Clear</Link> : null}
        {canEdit ? <button className={styles.addButton} onClick={() => setShowCreate(true)} type="button"><Plus size={15} />Add buyer</button> : null}
      </form>
      <p aria-live="polite" className={styles.resultSummary}>{apiError ? "Buyer search failed." : `${total} matching buyer${total === 1 ? "" : "s"}. Page ${page} of ${totalPages}.`}</p>
      {apiError ? <div className={styles.loadError} role="alert"><strong>Buyer CRM could not load.</strong><span>{apiError}</span><button onClick={() => router.refresh()} type="button">Retry</button></div> : null}

      <section className={styles.split}>
        <aside className={styles.queue} aria-label="Buyer records">
          <header><span>Buyer CRM</span><strong>{buyers.length} on this page</strong></header>
          {buyers.length === 0 ? <p className={styles.empty}>No buyers match these filters.</p> : buyers.map((buyer) => <button className={buyer.id === selected?.id ? styles.selectedBuyer : styles.buyerRow} key={buyer.id} onClick={() => selectBuyer(buyer.id)} type="button"><div><strong>{buyer.name}</strong><StatusBadge tone={buyer.status === "active" ? "success" : buyer.status === "do_not_contact" || buyer.status === "archived" ? "danger" : "neutral"}>{labelize(buyer.status)}</StatusBadge></div><span>{buyer.company_name ?? labelize(buyer.buyer_type)}</span><dl><div><dt>Owner</dt><dd>{buyer.relationship_owner_name ?? "Unassigned"}</dd></div><div><dt>Source</dt><dd>{labelize(buyer.source_key)}</dd></div></dl></button>)}
        </aside>

        <section className={`${styles.detail} ${mobileDetailOpen ? styles.detailOpen : ""}`}>
          {selected ? <>
            <header className={styles.buyerHeader}><div><span>{labelize(selected.buyer_type)}</span><h2>{selected.name}</h2><p>{selected.company_name ?? "Independent buyer"}</p></div><div className={styles.headerStatus}>
              {canEdit && selected.status !== "archived" ? <button className={styles.headerAction} onClick={() => setShowEdit(true)} type="button"><Pencil size={15} />Edit</button> : null}
              {canEdit ? selected.status === "archived" ? <button className={styles.headerAction} disabled={actionStatus === "saving"} onClick={() => void restoreBuyer()} type="button"><ArchiveRestore size={15} />Restore</button> : <button className={styles.headerAction} onClick={() => setShowArchive(true)} type="button"><Archive size={15} />Archive</button> : null}
              {canEdit ? <button className={styles.conversationButton} disabled={actionStatus === "opening"} onClick={() => void openConversation()} type="button"><MessageSquare size={15} />{actionStatus === "opening" ? "Opening" : "Conversation"}</button> : null}
              <StatusBadge tone={proofVerified(selected.proof_of_funds_status) ? "success" : "warning"}>POF {labelize(selected.proof_of_funds_status)}</StatusBadge>
              <button aria-label="Close buyer details" className={styles.mobileClose} onClick={() => setMobileDetailOpen(false)} type="button"><X size={17} /></button>
            </div></header>
            {actionError ? <p className={styles.actionError} role="alert">{actionError}</p> : null}
            <nav aria-label="Buyer record sections" className={styles.localTabs}>{buyerTabs.map((tab) => <button aria-current={activeTab === tab.key ? "page" : undefined} className={activeTab === tab.key ? styles.activeTab : ""} key={tab.key} onClick={() => selectTab(tab.key)} type="button">{tab.label}</button>)}</nav>
            {activeTab === "summary" ? <div className={styles.detailGrid}>
              <section className={styles.panel}><header><div><span>Relationship</span><h3>Buyer snapshot</h3></div></header><dl><div><dt>Status</dt><dd>{labelize(selected.status)}</dd></div><div><dt>Owner</dt><dd>{selected.relationship_owner_name ?? "Unassigned"}</dd></div><div><dt>Source</dt><dd>{labelize(selected.source_key)}{selected.source_detail ? ` - ${selected.source_detail}` : ""}</dd></div><div><dt>External source ID</dt><dd>{selected.source_external_key ?? "Not recorded"}</dd></div><div><dt>Added by</dt><dd>{selected.created_by_name ?? selected.created_by_email ?? "Legacy or automated record"}</dd></div><div><dt>Last verified</dt><dd>{displayDate(selected.last_verified_at, true)}</dd></div><div><dt>Updated</dt><dd>{displayDate(selected.updated_at, true)}</dd></div>{selected.archived_at ? <div><dt>Archived</dt><dd>{displayDate(selected.archived_at, true)} - {selected.archive_reason}</dd></div> : null}</dl></section>
              <section className={styles.panel}><header><div><span>Contactability</span><h3>Permission and contact</h3></div></header><dl><div><dt>Call</dt><dd>{permissionLabel(selected, "phone")} - {displayDate(selected.phone_permission.recorded_at, true)}</dd></div><div><dt>SMS</dt><dd>{permissionLabel(selected, "sms")} - {displayDate(selected.sms_permission.recorded_at, true)}</dd></div><div><dt>Permission source</dt><dd>{selected.phone_permission.source ?? selected.sms_permission.source ?? "Not recorded"}</dd></div><div><dt>Email</dt><dd>{selected.email ?? "Missing"}</dd></div><div><dt>Phone</dt><dd>{selected.phone ?? "Missing"}</dd></div></dl></section>
              <section className={`${styles.panel} ${styles.permissionPanel}`}><header><div><span>Append-only record</span><h3>Permission history</h3></div></header>{selected.permission_history.length ? <ol aria-label="Contact permission history" className={styles.permissionHistory}>{selected.permission_history.map((entry, index) => <li key={`${entry.channel}-${entry.recorded_at ?? "unknown"}-${index}`}><div><strong>{labelize(entry.channel)} - {labelize(entry.status)}</strong>{entry.recorded_at ? <time dateTime={entry.recorded_at}>{displayDate(entry.recorded_at, true)}</time> : <span>Time not recorded</span>}</div><p>Source: {entry.source ? labelize(entry.source) : "Not recorded"}</p><small>{entry.normalized_address ? `Contact: ${entry.normalized_address}` : "Contact value not recorded"}{entry.wording_version ? ` - Wording ${entry.wording_version}` : ""}</small></li>)}</ol> : <p className={styles.permissionHistoryEmpty}>No permission history has been recorded for this buyer.</p>}</section>
            </div> : null}
            {activeTab === "criteria" ? <div className={styles.singlePanel}><section className={styles.panel}><header><div><span>Buy box</span><h3>Purchasing criteria</h3></div></header><dl><div><dt>Criteria version</dt><dd>{selected.criteria ? `Version ${selected.criteria.version_number}` : "Not created"}</dd></div><div><dt>Markets</dt><dd>{selected.criteria?.markets ?? "Not set"}</dd></div><div><dt>Property types</dt><dd>{selected.criteria?.property_types ?? "Not set"}</dd></div><div><dt>Price range</dt><dd>{money(selected.criteria?.min_price_cents ?? null)} - {money(selected.criteria?.max_price_cents ?? selected.max_purchase_price_cents)}</dd></div><div><dt>Rehab levels</dt><dd>{selected.criteria?.rehab_levels ?? "Not set"}</dd></div><div><dt>Notes</dt><dd>{selected.criteria?.notes ?? selected.notes ?? "No criteria notes"}</dd></div></dl></section></div> : null}
            {activeTab === "evidence" ? <div className={styles.singlePanel}><section className={styles.panel}><header><div><span>Qualification</span><h3>Proof and capacity</h3></div></header><dl><div><dt>Proof of funds</dt><dd>{labelize(selected.proof_of_funds_status)}</dd></div><div><dt>Evidence expires</dt><dd>{displayDate(selected.proof_of_funds_expires_at)}</dd></div><div><dt>Maximum purchase</dt><dd>{money(selected.max_purchase_price_cents)}</dd></div><div><dt>Reliability</dt><dd>{reliability(selected)}</dd></div><div><dt>Deal history</dt><dd>{selected.completed_deals} completed / {selected.failed_deals} failed</dd></div></dl></section></div> : null}
            {activeTab === "deals" ? <section className={styles.dealPool}><header><div><span>Available inventory</span><h3>Active deals to compare</h3></div><strong>{contractLeads.length}</strong></header>{contractLeads.length ? contractLeads.map((lead) => <Link href={`/os/leads/${lead.id}?returnTo=${encodeURIComponent(locationFor())}`} key={lead.id}><div><strong>{lead.property_address}</strong><span>{labelize(lead.property_type)}</span></div><small>{lead.seller_name} - {labelize(lead.stage_key)} - {lead.property_city}, {lead.property_state}</small></Link>) : <p className={styles.empty}>No contracted deals need buyer placement.</p>}</section> : null}
          </> : <div className={styles.emptyState}><UsersRound size={24} /><h2>No buyer selected</h2><p>Search the buyer network or add the first qualified buyer.</p></div>}
        </section>
        {mobileDetailOpen ? <button aria-label="Close buyer details" className={styles.mobileBackdrop} onClick={() => setMobileDetailOpen(false)} type="button" /> : null}
      </section>

      <nav aria-label="Buyer result pages" className={styles.pagination}>
        {page > 1 ? <Link href={locationFor({ buyer: null, page: page - 1 })}><ChevronLeft size={16} />Previous</Link> : <span aria-disabled="true"><ChevronLeft size={16} />Previous</span>}
        <strong>Page {page} of {totalPages}</strong>
        {page < totalPages ? <Link href={locationFor({ buyer: null, page: page + 1 })}>Next<ChevronRight size={16} /></Link> : <span aria-disabled="true">Next<ChevronRight size={16} /></span>}
      </nav>

      <section className={styles.comparison}><header><div><span>Current result page</span><h3>Qualification and capacity</h3></div></header><div><table><thead><tr><th>Buyer</th><th>Status</th><th>Owner</th><th>Source</th><th>POF</th><th>Maximum</th><th>Updated</th></tr></thead><tbody>{buyers.map((buyer) => <tr key={buyer.id}><td><button onClick={() => selectBuyer(buyer.id)} type="button">{buyer.name}</button><small>{buyer.company_name}</small></td><td>{labelize(buyer.status)}</td><td>{buyer.relationship_owner_name ?? "Unassigned"}</td><td>{labelize(buyer.source_key)}</td><td>{labelize(buyer.proof_of_funds_status)}</td><td>{money(buyer.max_purchase_price_cents)}</td><td>{displayDate(buyer.updated_at)}</td></tr>)}</tbody></table></div></section>

      <Drawer description="Create a buyer in Needs review, then verify the relationship before activating it." onClose={() => setShowCreate(false)} open={showCreate} title="Add buyer">
        <BuyerForm onCancel={() => setShowCreate(false)} onSaved={(saved) => { setShowCreate(false); setSelectedId(saved.id); router.push(`/os/buyers?buyer=${saved.id}&tab=summary`); }} onUseExisting={useExisting} relationshipOwners={relationshipOwners} sourceOptions={sourceOptions} />
      </Drawer>
      <Drawer description="Update contact, ownership, evidence, and buy-box information." onClose={() => setShowEdit(false)} open={showEdit} title={`Edit ${selected?.name ?? "buyer"}`}>
        {selected ? <BuyerForm buyer={selected} onCancel={() => setShowEdit(false)} onSaved={(saved) => { setShowEdit(false); setSelectedId(saved.id); }} onUseExisting={useExisting} relationshipOwners={relationshipOwners} sourceOptions={sourceOptions} /> : null}
      </Drawer>
      <Drawer description="Archived buyers leave active matching and outreach but keep their audit history." onClose={() => setShowArchive(false)} open={showArchive} title={`Archive ${selected?.name ?? "buyer"}`}>
        <div className={styles.archiveForm}><label><span>Reason</span><textarea autoFocus maxLength={500} onChange={(event) => setArchiveReason(event.target.value)} placeholder="Why should this buyer leave the active network?" value={archiveReason} /></label><p>This does not delete the relationship. You can restore it later.</p>{actionError ? <p className={styles.formError} role="alert">{actionError}</p> : null}<div className={styles.formActions}><button className={styles.secondaryAction} onClick={() => setShowArchive(false)} type="button">Cancel</button><button disabled={archiveReason.trim().length < 2 || actionStatus === "saving"} onClick={() => void archiveBuyer()} type="button">{actionStatus === "saving" ? "Archiving..." : "Archive buyer"}</button></div></div>
      </Drawer>
    </section>
  );
}
