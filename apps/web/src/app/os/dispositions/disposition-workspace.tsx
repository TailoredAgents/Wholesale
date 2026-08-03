"use client";

import { useAuth } from "@clerk/nextjs";
import {
  Check,
  CircleDollarSign,
  DatabaseZap,
  Download,
  LoaderCircle,
  Megaphone,
  SearchCheck,
  ShieldCheck,
  Upload,
  UserPlus,
  UsersRound,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import type {
  BuyerDataProvider,
  BuyerDiscoveryEstimate,
  BuyerDiscoveryRun,
  DispositionCopilotOverview,
  DispositionCopilotRecommendation,
  DispositionOverview,
} from "../../lib/api";
import { CopilotLauncher } from "../_components/copilot-launcher";
import { labelize } from "../os-utils";
import { DispositionCopilotPanel } from "./disposition-copilot-panel";
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

function creditSummary(summary: Record<string, unknown> | null) {
  if (!summary) return "Credit use unavailable";
  const properties = typeof summary.properties === "number" ? summary.properties : null;
  const people = typeof summary.people === "number" ? summary.people : null;
  if (properties == null && people == null) return "Credit use recorded by DealMachine";
  return `${properties ?? 0} property + ${people ?? 0} owner credits used`;
}

export function DispositionWorkspace({
  initialCaseId,
  initialData,
  initialTab = "package",
}: {
  initialCaseId?: string;
  initialData: DispositionOverview;
  initialTab?: Tab;
}) {
  const { getToken } = useAuth();
  const [data, setData] = useState(initialData);
  const [selectedId, setSelectedId] = useState(
    initialData.cases.some((item) => item.id === initialCaseId)
      ? initialCaseId ?? null
      : initialData.cases[0]?.id ?? null,
  );
  const [tab, setTab] = useState<Tab>(initialTab);
  const [copilot, setCopilot] = useState<DispositionCopilotOverview | null>(null);
  const [copilotCaseId, setCopilotCaseId] = useState<string | null>(null);
  const [buyerProvider, setBuyerProvider] = useState<BuyerDataProvider | null>(null);
  const [discoveryEstimate, setDiscoveryEstimate] = useState<BuyerDiscoveryEstimate | null>(null);
  const [discovery, setDiscovery] = useState<BuyerDiscoveryRun | null>(null);
  const [selectedCandidates, setSelectedCandidates] = useState<string[]>([]);
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

  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    void request<DispositionCopilotOverview>(
      `/api/v1/dispositions/cases/${selectedId}/copilot`,
    )
      .then((result) => {
        if (active) {
          setCopilot(result);
          setCopilotCaseId(selectedId);
        }
      })
      .catch(() => {
        if (active) {
          setCopilot(null);
          setCopilotCaseId(selectedId);
        }
      });
    void request<BuyerDataProvider>("/api/v1/buyers/provider")
      .then(async (result) => {
        const provider = result.configured
          ? await request<BuyerDataProvider>("/api/v1/buyers/provider/readiness")
          : result;
        if (active) setBuyerProvider(provider);
      })
      .catch(() => {
        if (active) setBuyerProvider(null);
      });
    void request<BuyerDiscoveryRun | null>(
      `/api/v1/buyers/discovery-runs/latest?case_id=${selectedId}`,
    )
      .then((result) => {
        if (active) {
          setDiscovery(result);
          setDiscoveryEstimate(null);
          setSelectedCandidates([]);
        }
      })
      .catch(() => {
        if (active) {
          setDiscovery(null);
          setDiscoveryEstimate(null);
          setSelectedCandidates([]);
        }
      });
    return () => {
      active = false;
    };
  // The request helper intentionally follows the selected case and current Clerk session.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

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
      if (selectedId) {
        setCopilot(
          await request<DispositionCopilotOverview>(
            `/api/v1/dispositions/cases/${selectedId}/copilot`,
          ),
        );
        setCopilotCaseId(selectedId);
      }
      setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save.");
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

  async function generateCopilot() {
    if (!selected) return;
    await action(
      () =>
        request(`/api/v1/dispositions/cases/${selected.id}/copilot/analyze`, {
          method: "POST",
          body: JSON.stringify({}),
        }),
      "Disposition guidance prepared for review.",
    );
  }

  async function discoverExternalBuyers() {
    if (!selected || !discoveryEstimate?.enough_credits) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await request<BuyerDiscoveryRun>("/api/v1/buyers/discovery-runs", {
        method: "POST",
        body: JSON.stringify({
          disposition_case_id: selected.id,
          max_candidates: 25,
          confirmed_estimated_credits: discoveryEstimate.estimated_credits,
        }),
      });
      setDiscovery(result);
      void request<BuyerDataProvider>("/api/v1/buyers/provider/readiness")
        .then(setBuyerProvider)
        .catch(() => undefined);
      setDiscoveryEstimate(null);
      setSelectedCandidates(
        result.candidates
          .filter((item) => item.status === "review")
          .slice(0, 10)
          .map((item) => item.id),
      );
      setMessage(
        `${result.result_count} provider candidates ranked. Review the preselected top ten before importing.`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Buyer discovery failed.");
    } finally {
      setBusy(false);
    }
  }

  async function previewExternalBuyerCost() {
    if (!selected) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await request<BuyerDiscoveryEstimate>(
        "/api/v1/buyers/discovery-runs/estimate",
        {
          method: "POST",
          body: JSON.stringify({
            disposition_case_id: selected.id,
            max_candidates: 25,
          }),
        },
      );
      setDiscoveryEstimate(result);
      setMessage(result.message);
    } catch (error) {
      setDiscoveryEstimate(null);
      setMessage(error instanceof Error ? error.message : "Credit preview failed.");
    } finally {
      setBusy(false);
    }
  }

  async function importExternalBuyers() {
    if (!selected || !discovery || !selectedCandidates.length) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await request<BuyerDiscoveryRun>(
        `/api/v1/buyers/discovery-runs/${discovery.id}/import`,
        {
          method: "POST",
          body: JSON.stringify({ candidate_ids: selectedCandidates }),
        },
      );
      setDiscovery(result);
      setSelectedCandidates([]);
      if (selected.package_status === "approved") {
        await request(`/api/v1/dispositions/cases/${selected.id}/matches`, {
          method: "POST",
          body: "{}",
        });
      }
      await reload(selected.id);
      setMessage(
        "Selected investors were added to Stonegate. Contact details, buy box, and proof of funds still require verification.",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Buyer import failed.");
    } finally {
      setBusy(false);
    }
  }

  function toggleCandidate(candidateId: string) {
    setSelectedCandidates((current) =>
      current.includes(candidateId)
        ? current.filter((item) => item !== candidateId)
        : [...current, candidateId],
    );
  }

  async function reviewCopilot(
    recommendation: DispositionCopilotRecommendation,
    decision: "accepted" | "edited" | "rejected",
    finalOutput?: DispositionCopilotRecommendation["output_payload"],
  ) {
    await action(
      () =>
        request(
          `/api/v1/dispositions/copilot/recommendations/${recommendation.id}/review`,
          {
            method: "POST",
            body: JSON.stringify({
              decision,
              final_output: finalOutput ?? null,
              notes: "Disposition specialist reviewed the governed draft.",
              estimated_time_saved_seconds: 600,
            }),
          },
        ),
      `Disposition guidance ${labelize(decision).toLowerCase()}.`,
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
    <section aria-label="Disposition management" className={`${styles.workspace} ${styles.embeddedWorkspace}`}>
      {message ? <p className={message.includes("Unable") || message.includes("required") ? styles.notice : styles.success}>{message}</p> : null}

      <section className={`${styles.body} ${styles.embeddedBody}`}>
        <div className={styles.detail}>
          {!selected ? <div className={styles.empty}><UsersRound size={30} /><h3>No disposition cases</h3><p>Executed transactions will appear here when ready for buyer placement.</p></div> : (
            <>
              {copilot && copilotCaseId === selected.id ? (
                <CopilotLauncher
                  attentionCount={copilot.readiness_gaps.length + copilot.risk_alerts.length}
                  description="Reviews buyer fit, package evidence, offers, and placement risks without contacting buyers or selecting an offer."
                  name="Disposition Copilot"
                  score={copilot.readiness_score}
                  summary={copilot.risk_alerts[0]?.reason ?? copilot.readiness_gaps[0] ?? "Buyer placement evidence is ready for review."}
                >
                  <DispositionCopilotPanel
                    busy={busy}
                    copilot={copilot}
                    onGenerate={generateCopilot}
                    onReview={reviewCopilot}
                  />
                </CopilotLauncher>
              ) : null}
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

              {tab === "buyers" ? <div className={styles.buyerTab}>
                <section className={styles.discoveryPanel}>
                  <header>
                    <div><span><DatabaseZap size={14} />External buyer intelligence</span><h4>DealMachine candidate search</h4><p>{buyerProvider?.message ?? "Checking buyer-data connection."}</p>{buyerProvider?.connected ? <small>{buyerProvider.plan_name ?? "DealMachine"} plan · {buyerProvider.credits_remaining?.toLocaleString() ?? "Unknown"} credits available{buyerProvider.billing_cycle_end ? ` · resets ${new Date(buyerProvider.billing_cycle_end).toLocaleDateString()}` : ""}</small> : null}</div>
                    <div className={styles.discoveryActions}>
                      <button disabled={busy || !buyerProvider?.live_search_enabled} onClick={previewExternalBuyerCost} type="button"><SearchCheck size={15} />Preview search cost</button>
                      <button disabled={busy || !discoveryEstimate?.enough_credits} onClick={discoverExternalBuyers} type="button"><DatabaseZap size={15} />{discoveryEstimate ? `Run search (up to ${discoveryEstimate.estimated_credits} credits)` : "Run buyer search"}</button>
                      <button disabled={busy || !selectedCandidates.length} onClick={importExternalBuyers} type="button"><UserPlus size={15} />Import selected ({selectedCandidates.length})</button>
                    </div>
                  </header>
                  {discoveryEstimate ? <p className={styles.discoveryEstimate}>{discoveryEstimate.total_matching_properties.toLocaleString()} matching recent purchases · samples up to {discoveryEstimate.provider_result_limit} properties · estimates {discoveryEstimate.estimated_property_credits} property and {discoveryEstimate.estimated_people_credits} owner credits. Running the search requires the explicit confirmation button above.</p> : null}
                  {discovery?.candidates.length ? <div className={styles.candidateList}>
                    {discovery.candidates.map((candidate, index) => {
                      const selectable = candidate.status === "review";
                      return <label className={selectable ? styles.candidate : styles.importedCandidate} key={candidate.id}>
                        <input checked={selectedCandidates.includes(candidate.id)} disabled={!selectable || busy} onChange={() => toggleCandidate(candidate.id)} type="checkbox" />
                        <span className={styles.rank}>{index + 1}</span>
                        <span><strong>{candidate.name}</strong><small>{candidate.market} · {candidate.property_types.join(", ")}</small></span>
                        <span><strong>{(candidate.score_basis_points / 100).toFixed(0)}%</strong><small>{candidate.observed_purchase_count} observed purchase{candidate.observed_purchase_count === 1 ? "" : "s"} · {candidate.no_mortgage_count} no-mortgage signal{candidate.no_mortgage_count === 1 ? "" : "s"}</small></span>
                        <span><strong>{candidate.last_purchase_date ? new Date(`${candidate.last_purchase_date}T12:00:00`).toLocaleDateString() : "Date unavailable"}</strong><small>{candidate.email || candidate.phone ? "Contact available" : "Contact needs enrichment"} · {labelize(candidate.status)}</small></span>
                      </label>;
                    })}
                  </div> : <p className={styles.emptyRow}>Run a deal-specific search to find recent local purchasers. Only candidates you approve are added to Stonegate.</p>}
                  {discovery ? <footer><span>{discovery.result_count} ranked candidates</span><span>{creditSummary(discovery.credit_summary)}</span><span>{discovery.imported_count} imported</span><span>No outreach sent</span></footer> : null}
                </section>
                <div className={styles.sectionGrid}>
                  <section className={styles.section}><div className={styles.sectionTitle}><div><span>Evidence-backed ranking</span><h4>Buyer match list</h4></div><strong>{selected.matches.filter((item) => item.qualification_status === "qualified").length} qualified</strong></div><div className={styles.matchList}>{selected.matches.length ? selected.matches.map((match) => <article key={match.id}><div className={styles.matchTop}><span className={styles.rank}>{match.rank}</span><div><strong>{match.buyer_name}</strong><small>{labelize(match.qualification_status)} · POF {labelize(match.proof_status)}</small></div><b>{(match.score_basis_points / 100).toFixed(0)}%</b></div>{!match.latest_proof_document_id ? <form className={styles.proofForm} onSubmit={(event) => uploadProof(event, match.buyer_id)}><input aria-label="Institution" name="institution" placeholder="Bank or lender" required /><input aria-label="Verified amount" name="verified_amount" inputMode="decimal" placeholder="Verified funds" required /><input aria-label="Expires" name="expires_at" type="date" required /><input aria-label="Proof document" name="file" type="file" required /><button disabled={busy} title="Verify proof of funds" type="submit"><Upload size={14} />Verify POF</button></form> : <p className={styles.verified}><ShieldCheck size={14} />Verified evidence attached{match.proof_expires_at ? ` · expires ${new Date(match.proof_expires_at).toLocaleDateString()}` : ""}</p>}</article>) : <p className={styles.emptyRow}>Approve the package, then generate buyer matches.</p>}</div></section>
                  <form className={styles.form} onSubmit={engagement}><div className={styles.sectionTitle}><div><span>Buyer activity</span><h4>Log inquiry or showing</h4></div></div><label><span>Buyer</span><select name="buyer_id" required>{selected.matches.map((item) => <option key={item.id} value={item.buyer_id}>{item.buyer_name}</option>)}</select></label><label><span>Activity</span><select name="engagement_type"><option value="inquiry">Inquiry</option><option value="showing">Showing</option><option value="follow_up">Follow-up</option><option value="deposit">Deposit</option></select></label><label><span>Notes</span><textarea name="notes" required rows={4} /></label><button disabled={busy || !selected.matches.length} type="submit">Log buyer activity</button><div className={styles.activityList}>{selected.engagements.slice(0, 5).map((item) => <p key={item.id}><strong>{item.buyer_name}</strong><span>{labelize(item.engagement_type)} · {item.notes}</span></p>)}</div></form>
                </div>
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
    </section>
  );
}
