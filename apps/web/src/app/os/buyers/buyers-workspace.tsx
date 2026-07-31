"use client";

import { BadgeDollarSign, Building2, Plus, Search, ShieldCheck, UsersRound, X } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import type { BuyerListItem, LeadListItem } from "../../lib/api";
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
  return ["received", "verified", "current"].includes(status);
}

type BuyerTab = "summary" | "criteria" | "deals" | "evidence";

const buyerTabs: Array<{ key: BuyerTab; label: string }> = [
  { key: "summary", label: "Summary" },
  { key: "criteria", label: "Criteria & markets" },
  { key: "deals", label: "Active deals" },
  { key: "evidence", label: "Proof & capacity" },
];

export function BuyersWorkspace({
  buyers,
  canEdit,
  contractLeads,
  initialBuyerId,
  initialTab,
}: {
  buyers: BuyerListItem[];
  canEdit: boolean;
  contractLeads: LeadListItem[];
  initialBuyerId?: string;
  initialTab?: string;
}) {
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState(
    buyers.some((buyer) => buyer.id === initialBuyerId) ? initialBuyerId! : buyers[0]?.id ?? null,
  );
  const [activeTab, setActiveTab] = useState<BuyerTab>(
    buyerTabs.some((tab) => tab.key === initialTab) ? initialTab as BuyerTab : "summary",
  );
  const [mobileDetailOpen, setMobileDetailOpen] = useState(
    buyers.some((buyer) => buyer.id === initialBuyerId),
  );
  const [showCreate, setShowCreate] = useState(false);
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return buyers;
    return buyers.filter((buyer) => [buyer.name, buyer.company_name, buyer.email, buyer.phone, buyer.criteria?.markets, buyer.criteria?.property_types].some((value) => value?.toLowerCase().includes(normalized)));
  }, [buyers, query]);
  const selected = buyers.find((buyer) => buyer.id === selectedId) ?? filtered[0] ?? null;
  const active = buyers.filter((buyer) => buyer.status === "active").length;
  const verified = buyers.filter((buyer) => proofVerified(buyer.proof_of_funds_status)).length;
  const expired = buyers.filter((buyer) => buyer.proof_of_funds_status === "expired" || (buyer.proof_of_funds_expires_at && new Date(buyer.proof_of_funds_expires_at) < new Date())).length;
  const blocker = !selected ? "No buyer selected" : !proofVerified(selected.proof_of_funds_status) ? "Proof of funds" : !selected.email && !selected.phone ? "Contact method" : !selected.criteria?.markets ? "Buy box criteria" : "No active blocker";

  function updateLocation(buyerId: string | null, tab: BuyerTab) {
    const values = new URLSearchParams({ tab });
    if (buyerId) values.set("buyer", buyerId);
    window.history.replaceState(null, "", `/os/buyers?${values.toString()}`);
  }

  function selectBuyer(buyerId: string) {
    setSelectedId(buyerId);
    setMobileDetailOpen(true);
    updateLocation(buyerId, activeTab);
  }

  function selectTab(tab: BuyerTab) {
    setActiveTab(tab);
    updateLocation(selected?.id ?? null, tab);
  }

  function buyerReturnPath() {
    const values = new URLSearchParams({ tab: activeTab });
    if (selected?.id) values.set("buyer", selected.id);
    return `/os/buyers?${values.toString()}`;
  }

  return (
    <section aria-label="Buyer management" className={styles.workspace}>
      <DealControlStrip
        authority={{ label: "Authority", value: canEdit ? "Buyer CRM editor" : "View only", detail: canEdit ? "Changes remain audited" : "No edit permission", tone: canEdit ? "success" : "warning" }}
        blocker={{ label: "Primary blocker", value: blocker, detail: selected?.name ?? "No buyer evidence", tone: blocker === "No active blocker" ? "success" : "warning" }}
        deadline={{ label: "Evidence expiry", value: selected?.proof_of_funds_expires_at ? new Date(selected.proof_of_funds_expires_at).toLocaleDateString() : "Not recorded", detail: `${expired} expired records`, tone: expired ? "danger" : "neutral" }}
        evidence={{ label: "Proof of funds", value: selected ? labelize(selected.proof_of_funds_status) : "No buyer selected", detail: selected ? `${reliability(selected)} reliability` : `${verified} verified buyers`, tone: selected && proofVerified(selected.proof_of_funds_status) ? "success" : "warning" }}
        nextAction={{ label: "Authorized next step", value: blocker === "Proof of funds" ? "Verify buyer funds" : blocker === "Buy box criteria" ? "Complete buy box" : contractLeads.length ? "Compare active deals" : "Maintain buyer record", detail: `${contractLeads.length} deals need buyer coverage`, tone: "info" }}
      />

      <section className={styles.metrics} aria-label="Buyer network summary">
        <div><UsersRound size={17} /><span>Active buyers</span><strong>{active}</strong></div>
        <div><ShieldCheck size={17} /><span>POF verified</span><strong>{verified}</strong></div>
        <div><Building2 size={17} /><span>Deals needing buyers</span><strong>{contractLeads.length}</strong></div>
        <div><BadgeDollarSign size={17} /><span>Expired evidence</span><strong>{expired}</strong></div>
      </section>

      <div className={styles.toolbar}>
        <label><Search size={15} /><span className={styles.srOnly}>Search buyers</span><input onChange={(event) => setQuery(event.target.value)} placeholder="Search buyer, company, market, or property type" type="search" value={query} /></label>
        {canEdit ? <button onClick={() => setShowCreate(true)} type="button"><Plus size={15} />Add buyer</button> : null}
      </div>

      <section className={styles.split}>
        <aside className={styles.queue} aria-label="Buyer records">
          <header><span>Buyer CRM</span><strong>{filtered.length} shown</strong></header>
          {filtered.length === 0 ? <p className={styles.empty}>No buyers match this search.</p> : filtered.map((buyer) => <button className={buyer.id === selected?.id ? styles.selectedBuyer : styles.buyerRow} key={buyer.id} onClick={() => selectBuyer(buyer.id)} type="button"><div><strong>{buyer.name}</strong><StatusBadge tone={buyer.status === "active" ? "success" : "neutral"}>{labelize(buyer.status)}</StatusBadge></div><span>{buyer.company_name ?? labelize(buyer.buyer_type)}</span><dl><div><dt>POF</dt><dd>{labelize(buyer.proof_of_funds_status)}</dd></div><div><dt>Maximum</dt><dd>{money(buyer.max_purchase_price_cents)}</dd></div></dl></button>)}
        </aside>
        <section className={`${styles.detail} ${mobileDetailOpen ? styles.detailOpen : ""}`}>
          {selected ? <><header className={styles.buyerHeader}><div><span>{labelize(selected.buyer_type)}</span><h2>{selected.name}</h2><p>{selected.company_name ?? "Independent buyer"}</p></div><div className={styles.headerStatus}><StatusBadge tone={proofVerified(selected.proof_of_funds_status) ? "success" : "warning"}>POF {labelize(selected.proof_of_funds_status)}</StatusBadge><button aria-label="Close buyer details" onClick={() => setMobileDetailOpen(false)} type="button"><X size={17} /></button></div></header>
            <nav aria-label="Buyer record sections" className={styles.localTabs}>{buyerTabs.map((tab) => <button aria-current={activeTab === tab.key ? "page" : undefined} className={activeTab === tab.key ? styles.activeTab : ""} key={tab.key} onClick={() => selectTab(tab.key)} type="button">{tab.label}</button>)}</nav>
            {activeTab === "summary" ? <div className={styles.detailGrid}>
              <section className={styles.panel}><header><div><span>Relationship</span><h3>Buyer snapshot</h3></div></header><dl><div><dt>Status</dt><dd>{labelize(selected.status)}</dd></div><div><dt>Reliability</dt><dd>{reliability(selected)}</dd></div><div><dt>Completed deals</dt><dd>{selected.completed_deals}</dd></div><div><dt>Failed deals</dt><dd>{selected.failed_deals}</dd></div><div><dt>Added</dt><dd>{new Date(selected.created_at).toLocaleDateString()}</dd></div></dl></section>
              <section className={styles.panel}><header><div><span>Next work</span><h3>Qualification status</h3></div></header><dl><div><dt>Primary blocker</dt><dd>{blocker}</dd></div><div><dt>Email</dt><dd>{selected.email ?? "Missing"}</dd></div><div><dt>Phone</dt><dd>{selected.phone ?? "Missing"}</dd></div><div><dt>Proof of funds</dt><dd>{labelize(selected.proof_of_funds_status)}</dd></div><div><dt>Maximum purchase</dt><dd>{money(selected.max_purchase_price_cents)}</dd></div></dl></section>
            </div> : null}
            {activeTab === "criteria" ? <div className={styles.singlePanel}><section className={styles.panel}><header><div><span>Buy box</span><h3>Purchasing criteria</h3></div></header><dl><div><dt>Markets</dt><dd>{selected.criteria?.markets ?? "Not set"}</dd></div><div><dt>Property types</dt><dd>{selected.criteria?.property_types ?? "Not set"}</dd></div><div><dt>Price range</dt><dd>{money(selected.criteria?.min_price_cents ?? null)} - {money(selected.criteria?.max_price_cents ?? selected.max_purchase_price_cents)}</dd></div><div><dt>Rehab levels</dt><dd>{selected.criteria?.rehab_levels ?? "Not set"}</dd></div><div><dt>Notes</dt><dd>{selected.criteria?.notes ?? selected.notes ?? "No criteria notes"}</dd></div></dl></section></div> : null}
            {activeTab === "evidence" ? <div className={styles.singlePanel}><section className={styles.panel}><header><div><span>Qualification</span><h3>Proof and capacity</h3></div></header><dl><div><dt>Proof of funds</dt><dd>{labelize(selected.proof_of_funds_status)}</dd></div><div><dt>Evidence expires</dt><dd>{selected.proof_of_funds_expires_at ? new Date(selected.proof_of_funds_expires_at).toLocaleDateString() : "Not set"}</dd></div><div><dt>Maximum purchase</dt><dd>{money(selected.max_purchase_price_cents)}</dd></div><div><dt>Reliability</dt><dd>{reliability(selected)}</dd></div><div><dt>Deal history</dt><dd>{selected.completed_deals} completed / {selected.failed_deals} failed</dd></div></dl></section></div> : null}
            {activeTab === "deals" ? <section className={styles.dealPool}><header><div><span>Available inventory</span><h3>Active deals to compare</h3></div><strong>{contractLeads.length}</strong></header>{contractLeads.length ? contractLeads.map((lead) => <Link href={`/os/leads/${lead.id}?returnTo=${encodeURIComponent(buyerReturnPath())}`} key={lead.id}><div><strong>{lead.property_address}</strong><span>{labelize(lead.property_type)}</span></div><small>{lead.seller_name} · {labelize(lead.stage_key)} · {lead.property_city}, {lead.property_state}</small></Link>) : <p className={styles.empty}>No contracted deals need buyer placement.</p>}</section> : null}
          </> : <div className={styles.emptyState}><UsersRound size={24} /><h2>No buyer selected</h2><p>Search the buyer network or add the first qualified buyer.</p></div>}
        </section>
        {mobileDetailOpen ? <button aria-label="Close buyer details" className={styles.mobileBackdrop} onClick={() => setMobileDetailOpen(false)} type="button" /> : null}
      </section>

      <section className={styles.comparison}>
        <header><div><span>Network comparison</span><h3>Qualification and capacity</h3></div></header>
        <div><table><thead><tr><th>Buyer</th><th>Status</th><th>POF</th><th>Reliability</th><th>Maximum</th><th>Markets</th><th>Deal history</th></tr></thead><tbody>{filtered.map((buyer) => <tr key={buyer.id}><td><button onClick={() => selectBuyer(buyer.id)} type="button">{buyer.name}</button><small>{buyer.company_name}</small></td><td>{labelize(buyer.status)}</td><td>{labelize(buyer.proof_of_funds_status)}</td><td>{reliability(buyer)}</td><td>{money(buyer.max_purchase_price_cents)}</td><td>{buyer.criteria?.markets ?? "Not set"}</td><td>{buyer.completed_deals} closed / {buyer.failed_deals} failed</td></tr>)}</tbody></table></div>
      </section>

      <Drawer
        description="Create a qualified buyer record with contact, funding, and purchasing criteria."
        onClose={() => setShowCreate(false)}
        open={showCreate}
        title="Add qualified buyer"
      >
        <BuyerForm onSaved={() => setShowCreate(false)} />
      </Drawer>
    </section>
  );
}
