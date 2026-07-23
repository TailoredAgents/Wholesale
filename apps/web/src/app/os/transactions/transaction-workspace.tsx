"use client";

import { useAuth } from "@clerk/nextjs";
import {
  AlertTriangle,
  Check,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Download,
  FileCheck2,
  FileText,
  History,
  Landmark,
  LoaderCircle,
  Plus,
  Upload,
  UserRound,
  UsersRound,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import type { TransactionDetail, TransactionOverview } from "../../lib/api";
import { DealControlStrip } from "../_components/deal-control-strip";
import { labelize } from "../os-utils";
import styles from "./transactions.module.css";

type Tab = "closing" | "contract" | "documents" | "parties" | "timeline";
type ContractTemplate = {
  id: string; document_type: string; state_code: string; name: string;
  version_number: number; status: string; file_name: string;
};

function money(cents: number | null) {
  return cents == null ? "Not set" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(cents / 100);
}

function date(value: string | null) {
  return value ? new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "Not set";
}

export function TransactionWorkspace({ initialData, initialTransactionId }: { initialData: TransactionOverview; initialTransactionId?: string }) {
  const { getToken } = useAuth();
  const [overview, setOverview] = useState(initialData);
  const [selectedId, setSelectedId] = useState(initialTransactionId ?? initialData.items[0]?.id ?? null);
  const [detail, setDetail] = useState<TransactionDetail | null>(null);
  const [templates, setTemplates] = useState<ContractTemplate[]>([]);
  const [tab, setTab] = useState<Tab>("closing");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const apiBase = useMemo(() => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000", []);
  const devEmail = useMemo(() => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com", []);

  async function headers(json = true) {
    const token = await getToken().catch(() => null);
    const value: Record<string, string> = {};
    if (json) value["Content-Type"] = "application/json";
    if (token) value.Authorization = `Bearer ${token}`;
    else value["X-Dev-User-Email"] = devEmail;
    return value;
  }

  async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${apiBase}${path}`, { ...options, headers: { ...(await headers(options.body instanceof Blob ? false : true)), ...(options.headers ?? {}) } });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      throw new Error(payload.detail ?? "Request failed.");
    }
    return response.json() as Promise<T>;
  }

  async function reload(transactionId = selectedId) {
    if (!transactionId) return;
    const [nextDetail, nextOverview, nextTemplates] = await Promise.all([
      request<TransactionDetail>(`/api/v1/transactions/${transactionId}`),
      request<TransactionOverview>("/api/v1/transactions"),
      request<ContractTemplate[]>("/api/v1/transactions/templates"),
    ]);
    setDetail(nextDetail);
    setOverview(nextOverview);
    setTemplates(nextTemplates);
  }

  useEffect(() => {
    let active = true;
    if (!selectedId) return;
    Promise.all([
      request<TransactionDetail>(`/api/v1/transactions/${selectedId}`),
      request<ContractTemplate[]>("/api/v1/transactions/templates"),
    ])
      .then(([value, nextTemplates]) => { if (active) { setDetail(value); setTemplates(nextTemplates); } })
      .catch((error) => { if (active) setMessage(error instanceof Error ? error.message : "Unable to load transaction."); });
    return () => { active = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  async function action(work: () => Promise<unknown>) {
    setBusy(true); setMessage(null);
    try { await work(); await reload(); setMessage("Saved."); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Unable to save."); }
    finally { setBusy(false); }
  }

  async function draftContract(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await action(() => request(`/api/v1/transactions/${selectedId}/contract-packages`, { method: "POST", body: JSON.stringify({
      seller_name: data.get("seller_name"), buyer_entity_name: data.get("buyer_entity_name"),
      template_id: data.get("template_id") || null,
      purchase_price_cents: Math.round(Number(data.get("purchase_price")) * 100),
      earnest_money_cents: data.get("earnest_money") ? Math.round(Number(data.get("earnest_money")) * 100) : null,
      closing_date: data.get("closing_date") ? `${data.get("closing_date")}T17:00:00Z` : null,
      inspection_period_days: data.get("inspection_period_days") ? Number(data.get("inspection_period_days")) : null,
      special_terms: data.get("special_terms") || null,
    }) }));
  }

  async function updateClosing(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    const timestamp = (name: string) => data.get(name) ? new Date(String(data.get(name))).toISOString() : null;
    await action(() => request(`/api/v1/transactions/${selectedId}`, { method: "PATCH", body: JSON.stringify({
      title_company: data.get("title_company") || null,
      closing_date: timestamp("closing_date"),
      earnest_money_due_at: timestamp("earnest_money_due_at"),
      due_diligence_deadline: timestamp("due_diligence_deadline"),
      assignment_deadline: timestamp("assignment_deadline"),
    }) }));
  }

  async function uploadTemplate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget); const file = data.get("file") as File;
    if (!file?.size) return;
    const params = new URLSearchParams({ file_name: file.name, document_type: String(data.get("document_type")), state_code: String(data.get("state_code")), name: String(data.get("name")) });
    await action(() => request(`/api/v1/transactions/templates?${params}`, { method: "POST", headers: { "Content-Type": file.type || "application/octet-stream" }, body: file }));
    event.currentTarget.reset();
  }

  async function uploadDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const file = data.get("file") as File;
    if (!file?.size) return;
    const params = new URLSearchParams({ file_name: file.name, document_type: String(data.get("document_type")), title: String(data.get("title") || file.name), document_status: String(data.get("document_status")) });
    const packageId = data.get("package_id"); if (packageId) params.set("package_id", String(packageId));
    await action(() => request(`/api/v1/transactions/${selectedId}/documents?${params}`, { method: "POST", headers: { "Content-Type": file.type || "application/octet-stream" }, body: file }));
    event.currentTarget.reset();
  }

  async function addParty(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    await action(() => request(`/api/v1/transactions/${selectedId}/parties`, { method: "POST", body: JSON.stringify(Object.fromEntries(data)) }));
    event.currentTarget.reset();
  }

  async function addNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    await action(() => request(`/api/v1/transactions/${selectedId}/events`, { method: "POST", body: JSON.stringify({ event_type: "note", summary: data.get("summary") }) }));
    event.currentTarget.reset();
  }

  async function downloadDocument(document: TransactionDetail["documents"][number]) {
    setMessage(null);
    try {
      const response = await fetch(`${apiBase}${document.download_url}`, { headers: await headers(false) });
      if (!response.ok) throw new Error("Download failed.");
      const url = URL.createObjectURL(await response.blob());
      const anchor = window.document.createElement("a"); anchor.href = url; anchor.download = document.file_name; anchor.click(); URL.revokeObjectURL(url);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Download failed."); }
  }

  const requiredOpen = detail?.checklist.filter(
    (item) => item.is_required && item.status !== "complete",
  ) ?? [];
  const nextDeadline = detail
    ? [
        ...detail.checklist.map((item) => item.due_at),
        detail.earnest_money_due_at,
        detail.due_diligence_deadline,
        detail.assignment_deadline,
        detail.closing_date,
      ]
        .filter((value): value is string => Boolean(value))
        .map((value) => new Date(value))
        .filter((value) => !Number.isNaN(value.getTime()) && value >= new Date())
        .sort((left, right) => left.getTime() - right.getTime())[0] ?? null
    : null;
  const pendingPackage = detail?.contract_packages.some((item) => item.status === "pending_approval") ?? false;

  return (
    <div className={styles.workspace}>
      <section className={styles.metrics} aria-label="Transaction summary">
        {[{ label: "Active", value: overview.metrics.active, icon: Landmark }, { label: "Approval", value: overview.metrics.pending_approval, icon: FileCheck2 }, { label: "Due in 7 days", value: overview.metrics.due_next_seven_days, icon: Clock3 }, { label: "Overdue", value: overview.metrics.overdue, icon: AlertTriangle }, { label: "Ready to close", value: overview.metrics.ready_to_close, icon: CircleDollarSign }].map((item) => <div key={item.label}><item.icon size={18} /><span>{item.label}</span><strong>{item.value}</strong></div>)}
      </section>
      <div className={styles.body}>
        <aside className={styles.queue}>
          <div className={styles.queueHeader}><div><span>Closing queue</span><strong>{overview.items.length} active</strong></div></div>
          {overview.items.length === 0 ? <p className={styles.empty}>Open a transaction from a lead&apos;s Deal tab.</p> : overview.items.map((item) => (
            <button className={selectedId === item.id ? styles.selectedQueueItem : styles.queueItem} key={item.id} onClick={() => { setDetail(null); setSelectedId(item.id); }} type="button">
              <div><strong>{item.seller_name}</strong><ChevronRight size={16} /></div><span>{item.property_address}</span>
              <dl><div><dt>Close</dt><dd>{date(item.closing_date)}</dd></div><div><dt>Progress</dt><dd>{item.checklist_complete}/{item.checklist_total}</dd></div></dl>
              {item.risk_flags[0] ? <small><AlertTriangle size={13} />{item.risk_flags[0]}</small> : <small className={styles.clear}><Check size={13} />On track</small>}
            </button>
          ))}
        </aside>
        <main className={styles.detail}>
          {!selectedId ? <div className={styles.emptyState}><FileText size={24} /><h3>No active transactions</h3><p>Open one from the Deal tab on a qualified lead.</p></div> : !detail ? <div className={styles.loading}><LoaderCircle className={styles.spin} size={22} /> Loading transaction</div> : <>
            <header className={styles.dealHeader}><div><span>{labelize(detail.status)}</span><h3>{detail.seller_name}</h3><p>{detail.property_address}</p></div><div><span>Purchase</span><strong>{money(detail.purchase_price_cents)}</strong></div></header>
            <div className={styles.controlStrip}>
              <DealControlStrip
                authority={{ label: "Authority", value: pendingPackage ? "Owner approval" : "Coordinator controls", detail: pendingPackage ? "Contract remains blocked" : detail.coordinator_name ?? "Coordinator unassigned", tone: pendingPackage ? "warning" : "info" }}
                blocker={{ label: "Primary blocker", value: requiredOpen[0]?.title ?? "No required blocker", detail: requiredOpen.length ? `${requiredOpen.length} required items open` : "Required checklist is clear", tone: requiredOpen.length ? "warning" : "success" }}
                deadline={{ label: "Next deadline", value: nextDeadline ? date(nextDeadline.toISOString()) : "No future deadline", detail: detail.closing_date ? `Closing ${date(detail.closing_date)}` : "Closing date missing", tone: nextDeadline ? "info" : "warning" }}
                evidence={{ label: "Evidence", value: `${detail.documents.length} documents`, detail: `${detail.checklist.filter((item) => item.status === "complete").length}/${detail.checklist.length} checklist complete`, tone: detail.documents.length ? "success" : "warning" }}
                nextAction={{ label: "Authorized next step", value: pendingPackage ? "Resolve contract approval" : requiredOpen[0]?.title ?? (detail.status === "funded" ? "Closing complete" : "Confirm funding"), detail: "Server gates remain enforced", tone: detail.status === "funded" ? "success" : "info" }}
              />
            </div>
            <nav className={styles.tabs}>{(["closing", "contract", "documents", "parties", "timeline"] as Tab[]).map((value) => <button className={tab === value ? styles.activeTab : ""} key={value} onClick={() => setTab(value)} type="button">{labelize(value)}</button>)}</nav>
            {message ? <div className={message === "Saved." ? styles.success : styles.notice}>{message}</div> : null}

            {tab === "closing" ? <div className={styles.sectionGrid}>
              <section className={styles.section}><div className={styles.sectionTitle}><div><span>Closing controls</span><h4>Required workflow</h4></div><strong>{detail.checklist.filter((item) => item.status === "complete").length}/{detail.checklist.length}</strong></div>
                <div className={styles.checklist}>{detail.checklist.map((item) => <div className={styles.checkItem} key={item.id}><button aria-label={item.status === "complete" ? "Reopen item" : "Complete item"} disabled={busy} onClick={() => void action(() => request(`/api/v1/transactions/${detail.id}/checklist/${item.id}`, { method: "PATCH", body: JSON.stringify({ status: item.status === "complete" ? "open" : "complete" }) }))} type="button">{item.status === "complete" ? <Check size={15} /> : null}</button><div><strong>{item.title}</strong><span>{item.description}</span><small>{labelize(item.category)} · {item.due_at ? date(item.due_at) : "No deadline"}</small></div></div>)}</div>
              </section>
              <div className={styles.rightStack}><aside className={styles.section}><div className={styles.sectionTitle}><div><span>Deal snapshot</span><h4>Dates and funds</h4></div></div><dl className={styles.facts}><div><dt>Closing</dt><dd>{date(detail.closing_date)}</dd></div><div><dt>Due diligence</dt><dd>{date(detail.due_diligence_deadline)}</dd></div><div><dt>Earnest money</dt><dd>{money(detail.earnest_money_cents)}</dd></div><div><dt>Title opened</dt><dd>{date(detail.title_opened_at)}</dd></div><div><dt>Coordinator</dt><dd>{detail.coordinator_name ?? "Unassigned"}</dd></div></dl>
                <button className={styles.fundButton} disabled={busy || detail.status === "funded"} onClick={() => void action(() => request(`/api/v1/transactions/${detail.id}/close`, { method: "POST", body: JSON.stringify({ outcome: "funded", notes: "Funding and closing confirmed by transaction coordinator." }) }))} type="button"><CircleDollarSign size={16} />Record funded closing</button></aside>
                <form className={styles.form} onSubmit={(event) => void updateClosing(event)}><div className={styles.sectionTitle}><div><span>Milestones</span><h4>Update closing schedule</h4></div></div><label><span>Closing attorney / title company</span><input defaultValue={detail.title_company ?? ""} name="title_company" /></label><label><span>Closing date</span><input defaultValue={detail.closing_date?.slice(0, 16)} name="closing_date" type="datetime-local" /></label><label><span>Earnest money due</span><input defaultValue={detail.earnest_money_due_at?.slice(0, 16)} name="earnest_money_due_at" type="datetime-local" /></label><label><span>Due diligence deadline</span><input defaultValue={detail.due_diligence_deadline?.slice(0, 16)} name="due_diligence_deadline" type="datetime-local" /></label><label><span>Assignment deadline</span><input defaultValue={detail.assignment_deadline?.slice(0, 16)} name="assignment_deadline" type="datetime-local" /></label><button disabled={busy} type="submit"><Check size={16} />Save milestones</button></form>
              </div>
            </div> : null}

            {tab === "contract" ? <div className={styles.sectionGrid}>
              <section className={styles.section}><div className={styles.sectionTitle}><div><span>Version control</span><h4>Contract packages</h4></div></div>
                <div className={styles.packageList}>{detail.contract_packages.map((pkg) => {
                  const signedDocument = detail.documents.find((document) => document.contract_package_id === pkg.id && document.document_type === "signed_purchase_agreement");
                  return <article key={pkg.id}><div><strong>Version {pkg.version_number}</strong><span className={styles.status}>{labelize(pkg.status)}</span></div><p>{pkg.seller_name} · {money(pkg.purchase_price_cents)} · {date(pkg.closing_date)}</p><div className={styles.inlineActions}>{pkg.status === "draft" ? <button disabled={busy} onClick={() => void action(() => request(`/api/v1/transactions/${detail.id}/contract-packages/${pkg.id}/request-approval`, { method: "POST" }))} type="button">Request approval</button> : null}{pkg.status === "pending_approval" && pkg.approval_request_id ? <button disabled={busy} onClick={() => void action(() => request(`/api/v1/approvals/${pkg.approval_request_id}/decision`, { method: "PATCH", body: JSON.stringify({ status: "approved", decision_notes: "Terms reviewed in transaction workspace." }) }))} type="button">Approve package</button> : null}{pkg.status === "approved" ? <button disabled={busy} onClick={() => void action(() => request(`/api/v1/transactions/${detail.id}/contract-packages/${pkg.id}/mark-sent`, { method: "POST" }))} type="button">Record sent</button> : null}{["approved", "sent"].includes(pkg.status) && signedDocument ? <button disabled={busy} onClick={() => void action(() => request(`/api/v1/transactions/${detail.id}/contract-packages/${pkg.id}/mark-executed?document_id=${signedDocument.id}`, { method: "POST" }))} type="button">Record executed</button> : null}{["approved", "sent"].includes(pkg.status) && !signedDocument ? <span className={styles.actionHint}>Upload signed agreement to execute</span> : null}</div></article>;
                })}</div>
              </section>
              <div className={styles.rightStack}><form className={styles.form} onSubmit={(event) => void draftContract(event)}><div className={styles.sectionTitle}><div><span>New version</span><h4>Draft terms snapshot</h4></div></div><label><span>Approved template</span><select name="template_id"><option value="">Terms snapshot only</option>{templates.filter((item) => item.status === "approved").map((item) => <option key={item.id} value={item.id}>{item.name} · v{item.version_number}</option>)}</select></label><label><span>Seller</span><input defaultValue={detail.seller_name} name="seller_name" required /></label><label><span>Buyer entity</span><input name="buyer_entity_name" placeholder="Stonegate purchasing entity" required /></label><div className={styles.twoFields}><label><span>Purchase price</span><input defaultValue={detail.purchase_price_cents / 100} min="1" name="purchase_price" required type="number" /></label><label><span>Earnest money</span><input defaultValue={(detail.earnest_money_cents ?? 0) / 100} min="0" name="earnest_money" type="number" /></label></div><div className={styles.twoFields}><label><span>Closing date</span><input defaultValue={detail.closing_date?.slice(0, 10)} name="closing_date" type="date" /></label><label><span>Inspection days</span><input defaultValue={detail.inspection_period_days ?? ""} min="0" name="inspection_period_days" type="number" /></label></div><label><span>Special terms</span><textarea name="special_terms" rows={3} /></label><button disabled={busy} type="submit"><Plus size={16} />Create version</button></form>
                <form className={styles.form} onSubmit={(event) => void uploadTemplate(event)}><div className={styles.sectionTitle}><div><span>Controlled library</span><h4>Legal template</h4></div><FileCheck2 size={18} /></div><div className={styles.templateList}>{templates.map((item) => <div key={item.id}><span>{item.name} · {item.state_code} v{item.version_number}</span><strong>{labelize(item.status)}</strong>{item.status === "draft" ? <button disabled={busy} onClick={() => void action(() => request(`/api/v1/transactions/templates/${item.id}/approve`, { method: "POST" }))} type="button">Approve</button> : null}</div>)}</div><label><span>Attorney-reviewed file</span><input name="file" required type="file" /></label><label><span>Template name</span><input name="name" required /></label><div className={styles.twoFields}><label><span>Type</span><select name="document_type"><option value="purchase_agreement">Purchase agreement</option><option value="addendum">Addendum</option><option value="assignment_contract">Assignment contract</option></select></label><label><span>State</span><input defaultValue="GA" maxLength={2} name="state_code" required /></label></div><button disabled={busy} type="submit"><Upload size={16} />Add draft template</button></form>
              </div>
            </div> : null}

            {tab === "documents" ? <div className={styles.sectionGrid}>
              <section className={styles.section}><div className={styles.sectionTitle}><div><span>Private file room</span><h4>Transaction documents</h4></div></div><div className={styles.documentList}>{detail.documents.length === 0 ? <p className={styles.empty}>No files uploaded.</p> : detail.documents.map((document) => <div key={document.id}><FileText size={18} /><div><strong>{document.title}</strong><span>{labelize(document.document_type)} · {(document.file_size / 1024).toFixed(0)} KB</span></div><button aria-label={`Download ${document.title}`} onClick={() => void downloadDocument(document)} title="Download" type="button"><Download size={16} /></button></div>)}</div></section>
              <form className={styles.form} onSubmit={(event) => void uploadDocument(event)}><div className={styles.sectionTitle}><div><span>Evidence</span><h4>Upload document</h4></div><Upload size={18} /></div><label><span>File</span><input name="file" required type="file" /></label><label><span>Title</span><input name="title" placeholder="Signed purchase agreement" required /></label><label><span>Document type</span><select name="document_type"><option value="signed_purchase_agreement">Signed purchase agreement</option><option value="earnest_money_receipt">Earnest money receipt</option><option value="seller_disclosure">Seller disclosure</option><option value="title_document">Title document</option><option value="payoff_statement">Payoff statement</option><option value="assignment_contract">Assignment contract</option><option value="closing_statement">Closing statement</option><option value="funding_confirmation">Funding confirmation</option><option value="other">Other</option></select></label><label><span>Contract package</span><select name="package_id"><option value="">No package</option>{detail.contract_packages.map((pkg) => <option key={pkg.id} value={pkg.id}>Version {pkg.version_number}</option>)}</select></label><input name="document_status" type="hidden" value="final" /><button disabled={busy} type="submit"><Upload size={16} />Upload privately</button></form>
            </div> : null}

            {tab === "parties" ? <div className={styles.sectionGrid}><section className={styles.section}><div className={styles.sectionTitle}><div><span>Closing team</span><h4>Parties and contacts</h4></div><UsersRound size={18} /></div><div className={styles.partyList}>{detail.parties.length === 0 ? <p className={styles.empty}>No closing parties added.</p> : detail.parties.map((party) => <div key={party.id}><UserRound size={18} /><div><strong>{party.name}</strong><span>{labelize(party.party_type)}{party.company_name ? ` · ${party.company_name}` : ""}</span><small>{party.email ?? party.phone ?? "No contact method"}</small></div></div>)}</div></section><form className={styles.form} onSubmit={(event) => void addParty(event)}><div className={styles.sectionTitle}><div><span>New contact</span><h4>Add closing party</h4></div></div><label><span>Role</span><select name="party_type"><option value="closing_attorney">Closing attorney</option><option value="title_company">Title company</option><option value="seller">Seller</option><option value="buyer">Buyer</option><option value="lender">Lender</option><option value="other">Other</option></select></label><label><span>Name</span><input name="name" required /></label><label><span>Company</span><input name="company_name" /></label><div className={styles.twoFields}><label><span>Email</span><input name="email" type="email" /></label><label><span>Phone</span><input name="phone" /></label></div><button disabled={busy} type="submit"><Plus size={16} />Add party</button></form></div> : null}

            {tab === "timeline" ? <div className={styles.sectionGrid}><section className={styles.section}><div className={styles.sectionTitle}><div><span>Immutable history</span><h4>Transaction timeline</h4></div><History size={18} /></div><div className={styles.timeline}>{detail.events.map((event) => <div key={event.id}><span /><div><strong>{event.summary}</strong><small>{labelize(event.event_type)} · {event.actor_name ?? "System"} · {new Date(event.occurred_at).toLocaleString()}</small></div></div>)}</div></section><form className={styles.form} onSubmit={(event) => void addNote(event)}><div className={styles.sectionTitle}><div><span>Record context</span><h4>Add timeline note</h4></div></div><label><span>Note</span><textarea name="summary" required rows={5} /></label><button disabled={busy} type="submit"><Plus size={16} />Add note</button></form></div> : null}
          </>}
        </main>
      </div>
    </div>
  );
}
