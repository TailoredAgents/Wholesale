"use client";

import { useAuth } from "@clerk/nextjs";
import {
  BadgeDollarSign,
  Check,
  CircleDollarSign,
  Download,
  FileCheck2,
  LoaderCircle,
  Megaphone,
  Plus,
  ShieldCheck,
  Upload,
  UsersRound,
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";

import type { DispositionCase, DispositionOverview } from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./dispositions.module.css";

type Tab = "package" | "buyers" | "offers" | "reconciliation";

function money(cents: number | null) {
  return cents == null
    ? "Not set"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
      }).format(cents / 100);
}

function cents(value: FormDataEntryValue | null) {
  return Math.round(Number(String(value ?? "").replace(/[$,]/g, "")) * 100);
}

export function DispositionWorkspace({ initialData }: { initialData: DispositionOverview }) {
  const { getToken } = useAuth();
  const [data, setData] = useState(initialData);
  const [selectedId, setSelectedId] = useState(initialData.cases[0]?.id ?? null);
  const [tab, setTab] = useState<Tab>("package");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const apiBase = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devEmail = useMemo(
    () =>
      process.env.NEXT_PUBLIC_DEV_USER_EMAIL ??
      "richardaustindugger@users.noreply.github.com",
    [],
  );
  const selected = data.cases.find((item) => item.id === selectedId) ?? null;

  async function headers(json = true) {
    const token = await getToken().catch(() => null);
    const value: Record<string, string> = {};
    if (json) value["Content-Type"] = "application/json";
    if (token) value.Authorization = `Bearer ${token}`;
    else value["X-Dev-User-Email"] = devEmail;
    return value;
  }

  async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers: { ...(await headers(!(options.body instanceof Blob))), ...(options.headers ?? {}) },
    });
    if (!response.ok) {
      const payload = (await response.json().catch(() => ({}))) as { detail?: string };
      throw new Error(payload.detail ?? "Request failed.");
    }
    return response.json() as Promise<T>;
  }

  async function reload(preferredId = selectedId) {
    const next = await request<DispositionOverview>("/api/v1/dispositions");
    setData(next);
    setSelectedId(preferredId ?? next.cases[0]?.id ?? null);
  }

  async function action(work: () => Promise<unknown>, success: string) {
    setBusy(true);
    setMessage(null);
    try {
      await work();
      await reload();
      setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save.");
    } finally {
      setBusy(false);
    }
  }

  async function openCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const next = await request<DispositionCase>("/api/v1/dispositions/cases", {
      method: "POST",
      body: JSON.stringify({
        transaction_id: values.get("transaction_id"),
        strategy: values.get("strategy"),
        asking_price_cents: cents(values.get("asking_price")),
        minimum_acceptable_cents: cents(values.get("minimum_price")),
        operating_mode_key: "human_led",
        notes: values.get("notes") || null,
      }),
    });
    await reload(next.id);
    setSelectedId(next.id);
    setMessage("Disposition case opened with its compensation plan frozen.");
    form.reset();
  }

  async function submitCase(event: FormEvent<HTMLFormElement>) {
    setBusy(true);
    setMessage(null);
    try {
      await openCase(event);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to open case.");
    } finally {
      setBusy(false);
    }
  }

  async function offer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const buyerId = String(values.get("buyer_id"));
    const match = selected.matches.find((item) => item.buyer_id === buyerId);
    await action(
      () =>
        request(`/api/v1/dispositions/cases/${selected.id}/offers`, {
          method: "POST",
          body: JSON.stringify({
            buyer_id: buyerId,
            amount_cents: cents(values.get("amount")),
            earnest_money_cents: cents(values.get("earnest_money")),
            financing_type: values.get("financing_type"),
            proof_document_id: match?.latest_proof_document_id ?? null,
            notes: values.get("notes") || null,
          }),
        }),
      "Buyer offer recorded.",
    );
    form.reset();
  }

  async function engagement(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    await action(
      () =>
        request(`/api/v1/dispositions/cases/${selected.id}/engagements`, {
          method: "POST",
          body: JSON.stringify({
            buyer_id: values.get("buyer_id"),
            engagement_type: values.get("engagement_type"),
            status: "logged",
            notes: values.get("notes") || null,
          }),
        }),
      "Buyer activity logged.",
    );
    form.reset();
  }

  async function selectBuyer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const values = new FormData(event.currentTarget);
    await action(
      () =>
        request(`/api/v1/dispositions/cases/${selected.id}/buyer-selection`, {
          method: "POST",
          body: JSON.stringify({
            primary_offer_id: values.get("primary_offer_id"),
            backup_offer_id: values.get("backup_offer_id") || null,
            reason: values.get("reason"),
          }),
        }),
      "Buyer selection approved and documented.",
    );
  }

  async function uploadProof(event: FormEvent<HTMLFormElement>, buyerId: string) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const file = values.get("file") as File;
    if (!file?.size) return;
    const params = new URLSearchParams({
      file_name: file.name,
      content_type: file.type || "application/octet-stream",
      institution_name: String(values.get("institution") || ""),
      verified_amount_cents: String(cents(values.get("verified_amount"))),
      expires_at: new Date(String(values.get("expires_at"))).toISOString(),
    });
    await action(
      () =>
        request(`/api/v1/dispositions/buyers/${buyerId}/proof?${params}`, {
          method: "POST",
          headers: { "Content-Type": file.type || "application/octet-stream" },
          body: file,
        }),
      "Proof of funds verified.",
    );
    form.reset();
  }

  async function download(path: string, fileName: string) {
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch(`${apiBase}${path}`, { headers: await headers(false) });
      if (!response.ok) throw new Error("Export is not ready.");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to export.");
    } finally {
      setBusy(false);
    }
  }

  const post = (path: string) => request(path, { method: "POST", body: "{}" });

  return (
    <main className={styles.workspace}>
      <section className={styles.metrics}>
        <div><Megaphone size={18} /><span>Active cases</span><strong>{data.metrics.active_cases}</strong></div>
        <div><FileCheck2 size={18} /><span>Packages pending</span><strong>{data.metrics.packages_pending}</strong></div>
        <div><UsersRound size={18} /><span>Buyer selected</span><strong>{data.metrics.buyer_selected}</strong></div>
        <div><BadgeDollarSign size={18} /><span>Reconcile</span><strong>{data.metrics.reconciliation_pending}</strong></div>
        <div><ShieldCheck size={18} /><span>Below 30% target</span><strong>{data.metrics.below_margin_target}</strong></div>
      </section>

      {message ? <p className={message.includes("Unable") || message.includes("required") ? styles.notice : styles.success}>{message}</p> : null}

      <section className={styles.body}>
        <aside className={styles.queue}>
          <div className={styles.queueHeader}><div><span>Disposition queue</span><strong>{data.cases.length} cases</strong></div></div>
          {data.cases.map((item) => (
            <button className={item.id === selectedId ? styles.selectedQueueItem : styles.queueItem} key={item.id} onClick={() => setSelectedId(item.id)} type="button">
              <div><strong>{item.seller_name}</strong><span>{labelize(item.status)}</span></div>
              <p>{item.property_address}</p>
              <dl><div><dt>Ask</dt><dd>{money(item.asking_price_cents)}</dd></div><div><dt>Minimum</dt><dd>{money(item.minimum_acceptable_cents)}</dd></div></dl>
            </button>
          ))}
          {data.eligible_transactions.length ? (
            <form className={styles.openForm} onSubmit={submitCase}>
              <div className={styles.formTitle}><Plus size={15} /><strong>Open contracted deal</strong></div>
              <label><span>Transaction</span><select name="transaction_id" required>{data.eligible_transactions.map((item) => <option key={item.id} value={item.id}>{item.property_address}</option>)}</select></label>
              <label><span>Strategy</span><select name="strategy"><option value="assignment">Assignment</option><option value="double_close">Double close</option><option value="novation">Novation</option></select></label>
              <label><span>Investor asking price</span><input name="asking_price" inputMode="decimal" required /></label>
              <label><span>Approved minimum</span><input name="minimum_price" inputMode="decimal" required /></label>
              <label><span>Internal notes</span><textarea name="notes" rows={2} /></label>
              <button disabled={busy} type="submit">Open case</button>
            </form>
          ) : null}
        </aside>

        <div className={styles.detail}>
          {!selected ? <div className={styles.empty}><UsersRound size={30} /><h3>No disposition cases</h3><p>Executed transactions will appear here when ready for buyer placement.</p></div> : (
            <>
              <header className={styles.dealHeader}><div><span>{labelize(selected.strategy)} · {selected.operating_mode_label}</span><h3>{selected.property_address}</h3><p>{selected.seller_name} · {selected.compensation_plan_label}</p></div><div><span>Approved floor</span><strong>{money(selected.minimum_acceptable_cents)}</strong></div></header>
              <nav className={styles.tabs}>{(["package", "buyers", "offers", "reconciliation"] as Tab[]).map((item) => <button className={tab === item ? styles.activeTab : ""} key={item} onClick={() => setTab(item)} type="button">{labelize(item)}</button>)}</nav>

              {tab === "package" ? <div className={styles.sectionGrid}>
                <section className={styles.section}><div className={styles.sectionTitle}><div><span>Controlled release</span><h4>Investor package</h4></div><strong>{labelize(selected.package_status)}</strong></div><dl className={styles.facts}><div><dt>Property</dt><dd>{selected.property_address}</dd></div><div><dt>Type</dt><dd>{selected.property_type ?? "Not recorded"}</dd></div><div><dt>Asking price</dt><dd>{money(selected.asking_price_cents)}</dd></div><div><dt>Minimum acceptable</dt><dd>{money(selected.minimum_acceptable_cents)}</dd></div><div><dt>Operating model</dt><dd>{selected.operating_mode_label}</dd></div><div><dt>Compensation</dt><dd>{selected.compensation_plan_label}</dd></div></dl></section>
                <section className={styles.actionPanel}><div className={styles.sectionTitle}><div><span>Human approvals</span><h4>Release controls</h4></div></div>
                  <button disabled={busy || selected.package_status === "approved"} onClick={() => action(() => post(`/api/v1/dispositions/cases/${selected.id}/package/approve`), "Investor package approved.")} type="button"><Check size={15} />Approve package</button>
                  <button disabled={busy || selected.package_status !== "approved"} onClick={() => action(() => post(`/api/v1/dispositions/cases/${selected.id}/matches`), "Buyer pool scored against this deal." )} type="button"><UsersRound size={15} />Refresh buyer ranking</button>
                  <button disabled={busy || !selected.matches.some((item) => item.qualification_status === "qualified")} onClick={() => action(() => post(`/api/v1/dispositions/cases/${selected.id}/campaigns/release`), "Approved campaign simulated. No messages were sent." )} type="button"><Megaphone size={15} />Approve simulated release</button>
                  <button disabled={busy || selected.package_status !== "approved"} onClick={() => download(`/api/v1/dispositions/cases/${selected.id}/package.pdf`, "stonegate-investor-package.pdf")} type="button"><Download size={15} />Investor PDF</button>
                  <p>No buyer communication is sent in Phase 9. The release records the approved recipient pool for a future email/SMS adapter.</p>
                </section>
              </div> : null}

              {tab === "buyers" ? <div className={styles.sectionGrid}>
                <section className={styles.section}><div className={styles.sectionTitle}><div><span>Evidence-backed ranking</span><h4>Buyer match list</h4></div><strong>{selected.matches.filter((item) => item.qualification_status === "qualified").length} qualified</strong></div><div className={styles.matchList}>{selected.matches.length ? selected.matches.map((match) => <article key={match.id}><div className={styles.matchTop}><span className={styles.rank}>{match.rank}</span><div><strong>{match.buyer_name}</strong><small>{labelize(match.qualification_status)} · POF {labelize(match.proof_status)}</small></div><b>{(match.score_basis_points / 100).toFixed(0)}%</b></div>{!match.latest_proof_document_id ? <form className={styles.proofForm} onSubmit={(event) => uploadProof(event, match.buyer_id)}><input aria-label="Institution" name="institution" placeholder="Bank or lender" required /><input aria-label="Verified amount" name="verified_amount" inputMode="decimal" placeholder="Verified funds" required /><input aria-label="Expires" name="expires_at" type="date" required /><input aria-label="Proof document" name="file" type="file" required /><button disabled={busy} title="Verify proof of funds" type="submit"><Upload size={14} />Verify POF</button></form> : <p className={styles.verified}><ShieldCheck size={14} />Verified evidence attached{match.proof_expires_at ? ` · expires ${new Date(match.proof_expires_at).toLocaleDateString()}` : ""}</p>}</article>) : <p className={styles.emptyRow}>Approve the package, then generate buyer matches.</p>}</div></section>
                <form className={styles.form} onSubmit={engagement}><div className={styles.sectionTitle}><div><span>Buyer activity</span><h4>Log inquiry or showing</h4></div></div><label><span>Buyer</span><select name="buyer_id" required>{selected.matches.map((item) => <option key={item.id} value={item.buyer_id}>{item.buyer_name}</option>)}</select></label><label><span>Activity</span><select name="engagement_type"><option value="inquiry">Inquiry</option><option value="showing">Showing</option><option value="follow_up">Follow-up</option><option value="deposit">Deposit</option></select></label><label><span>Notes</span><textarea name="notes" required rows={4} /></label><button disabled={busy || !selected.matches.length} type="submit">Log buyer activity</button><div className={styles.activityList}>{selected.engagements.slice(0, 5).map((item) => <p key={item.id}><strong>{item.buyer_name}</strong><span>{labelize(item.engagement_type)} · {item.notes}</span></p>)}</div></form>
              </div> : null}

              {tab === "offers" ? <div className={styles.sectionGrid}>
                <section className={styles.section}><div className={styles.sectionTitle}><div><span>Offer control</span><h4>Buyer offers</h4></div><strong>{selected.offers.length}</strong></div><div className={styles.offerList}>{selected.offers.map((item) => <article key={item.id}><div><strong>{item.buyer_name}</strong><span>{labelize(item.status)}</span></div><b>{money(item.amount_cents)}</b><small>{money(item.earnest_money_cents)} deposit · {labelize(item.financing_type)}</small></article>)}{!selected.offers.length ? <p className={styles.emptyRow}>No buyer offers recorded.</p> : null}</div></section>
                <div className={styles.rightStack}><form className={styles.form} onSubmit={offer}><div className={styles.sectionTitle}><div><span>Document evidence</span><h4>Record offer</h4></div></div><label><span>Buyer</span><select name="buyer_id" required>{selected.matches.map((item) => <option key={item.id} value={item.buyer_id}>{item.buyer_name}</option>)}</select></label><div className={styles.twoFields}><label><span>Offer</span><input name="amount" inputMode="decimal" required /></label><label><span>Earnest money</span><input name="earnest_money" defaultValue="5000" inputMode="decimal" required /></label></div><label><span>Financing</span><select name="financing_type"><option value="cash">Cash</option><option value="hard_money">Hard money</option><option value="private_money">Private money</option></select></label><label><span>Notes</span><textarea name="notes" rows={3} /></label><button disabled={busy || !selected.matches.length} type="submit">Record offer</button></form>
                  <form className={styles.form} onSubmit={selectBuyer}><div className={styles.sectionTitle}><div><span>Human decision</span><h4>Approve buyer</h4></div></div><label><span>Primary offer</span><select name="primary_offer_id" required>{selected.offers.map((item) => <option key={item.id} value={item.id}>{item.buyer_name} · {money(item.amount_cents)}</option>)}</select></label><label><span>Backup offer</span><select name="backup_offer_id"><option value="">No backup</option>{selected.offers.map((item) => <option key={item.id} value={item.id}>{item.buyer_name} · {money(item.amount_cents)}</option>)}</select></label><label><span>Selection reason</span><textarea name="reason" required rows={3} placeholder="Price, verified funds, reliability, and closing capacity" /></label><button disabled={busy || !selected.offers.length} type="submit"><Check size={15} />Approve selection</button></form></div>
              </div> : null}

              {tab === "reconciliation" ? <div className={styles.sectionGrid}>
                <section className={styles.section}><div className={styles.sectionTitle}><div><span>Closing statement</span><h4>Deal reconciliation</h4></div><strong>{selected.reconciliation ? labelize(selected.reconciliation.status) : "Not calculated"}</strong></div>{selected.reconciliation ? <><dl className={styles.facts}><div><dt>Collected deal revenue</dt><dd>{money(selected.reconciliation.gross_revenue_cents)}</dd></div><div><dt>Acquisition reserve</dt><dd>-{money(selected.reconciliation.acquisition_reserve_cents)}</dd></div><div><dt>Deal-specific costs</dt><dd>-{money(selected.reconciliation.deal_deductions_cents)}</dd></div><div><dt>Adjusted deal margin</dt><dd>{money(selected.reconciliation.adjusted_deal_margin_cents)}</dd></div><div><dt>Commission payouts</dt><dd>{money(selected.reconciliation.total_compensation_cents)}</dd></div><div><dt>Company profit</dt><dd>{money(selected.reconciliation.company_profit_cents)}</dd></div><div><dt>Company share</dt><dd>{(selected.reconciliation.company_margin_basis_points / 100).toFixed(1)}% / {(selected.reconciliation.target_margin_basis_points / 100).toFixed(0)}% target</dd></div></dl><div className={styles.payouts}>{selected.reconciliation.payouts.map((item) => <div key={item.id}><span>{labelize(item.role_key)} · {item.user_name ?? "Unassigned"}</span><strong>{money(item.amount_cents)}</strong></div>)}</div></> : <p className={styles.emptyRow}>Fund the transaction and record collected revenue in Finance before calculating.</p>}</section>
                <section className={styles.actionPanel}><div className={styles.sectionTitle}><div><span>Owner control</span><h4>Close the books</h4></div></div><button disabled={busy || !selected.selected_buyer_id} onClick={() => action(() => post(`/api/v1/dispositions/cases/${selected.id}/reconciliation`), "Closing statement calculated from collected revenue and the frozen plan." )} type="button"><CircleDollarSign size={15} />Calculate statement</button><button disabled={busy || selected.reconciliation?.status !== "draft"} onClick={() => action(() => request(`/api/v1/dispositions/cases/${selected.id}/reconciliation/decision`, { method: "POST", body: JSON.stringify({ decision: "approved", notes: "Owner reviewed closing statement and payout allocation.", approve_below_target: false }) }), "Closing statement and commission payouts approved." )} type="button"><Check size={15} />Approve payouts</button><button disabled={busy || selected.reconciliation?.status !== "approved"} onClick={() => download(`/api/v1/dispositions/cases/${selected.id}/accounting.csv`, "stonegate-accounting-export.csv")} type="button"><Download size={15} />Accounting CSV</button><p>Approval is blocked when commission credit is unassigned or company profit falls below the active plan target.</p></section>
              </div> : null}
            </>
          )}
        </div>
      </section>
      {busy ? <div className={styles.busy}><LoaderCircle className={styles.spin} size={16} />Working</div> : null}
    </main>
  );
}
