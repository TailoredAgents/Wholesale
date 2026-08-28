"use client";

import { useAuth } from "@clerk/nextjs";
import {
  Check,
  CircleDollarSign,
  Download,
  LoaderCircle,
  UsersRound,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import type {
  DispositionCopilotOverview,
  DispositionCopilotRecommendation,
  DispositionOverview,
} from "../../lib/api";
import { CopilotLauncher } from "../_components/copilot-launcher";
import { labelize } from "../os-utils";
import { DispositionBuyerPool } from "./disposition-buyer-pool";
import { DispositionCopilotPanel } from "./disposition-copilot-panel";
import { DispositionPackageReadiness } from "./disposition-package-readiness";
import { DispositionOutreachWorkspace } from "./disposition-outreach-workspace";
import styles from "./dispositions.module.css";

type Tab = "package" | "buyers" | "outreach" | "offers" | "reconciliation";

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

export function DispositionWorkspace({
  canEditBuyers,
  canEditDeals,
  canManageOutreach,
  canApproveOutreach,
  canSendBulk,
  canViewOutreach,
  dealId,
  initialCaseId,
  initialData,
  initialTab = "package",
}: {
  canEditBuyers: boolean;
  canEditDeals: boolean;
  canManageOutreach: boolean;
  canApproveOutreach: boolean;
  canSendBulk: boolean;
  canViewOutreach: boolean;
  dealId: string;
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
  const [tab, setTab] = useState<Tab>(
    initialTab === "outreach" && !canViewOutreach ? "package" : initialTab,
  );
  const [copilot, setCopilot] = useState<DispositionCopilotOverview | null>(null);
  const [copilotCaseId, setCopilotCaseId] = useState<string | null>(null);
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

  async function action(
    work: () => Promise<unknown>,
    success: string,
    allowed = canEditDeals,
  ) {
    if (!allowed) {
      setMessage("Your role can view this disposition record but cannot change it.");
      return;
    }
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
    if (!canEditDeals) {
      setMessage("Your role can view this disposition record but cannot change it.");
      return;
    }
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
    if (!canEditDeals) {
      setMessage("Your role can view this disposition record but cannot change it.");
      return;
    }
    if (!selected) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const engagementType = String(values.get("engagement_type") ?? "inquiry");
    const scheduledValue = String(values.get("scheduled_at") ?? "").trim();
    const scheduledAt = engagementType === "follow_up" && scheduledValue
      ? new Date(scheduledValue).toISOString()
      : null;
    await action(
      () =>
        request(`/api/v1/dispositions/cases/${selected.id}/engagements`, {
          method: "POST",
          body: JSON.stringify({
            buyer_id: values.get("buyer_id"),
            engagement_type: engagementType,
            status: scheduledAt ? "scheduled" : "logged",
            scheduled_at: scheduledAt,
            notes: values.get("notes") || null,
          }),
        }),
      "Buyer activity logged.",
    );
    form.reset();
  }

  async function selectBuyer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canEditDeals) {
      setMessage("Your role can view this disposition record but cannot change it.");
      return;
    }
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
    if (!canEditBuyers) {
      setMessage("Your role can view buyer evidence but cannot change it.");
      return;
    }
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
      canEditBuyers,
    );
    form.reset();
  }

  async function download(path: string, fileName: string) {
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch(`${apiBase}${path}`, {
        cache: "no-store",
        headers: await headers(false),
      });
      if (!response.ok) throw new Error("Export is not ready.");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      const contentDisposition = response.headers.get("Content-Disposition") ?? "";
      const encodedName = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
      const quotedName = contentDisposition.match(/filename="([^"]+)"/i)?.[1];
      link.download = encodedName ? decodeURIComponent(encodedName) : quotedName ?? fileName;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to export.");
    } finally {
      setBusy(false);
    }
  }

  const post = (path: string) => request(path, { method: "POST", body: "{}" });

  function selectWorkspaceTab(nextTab: Tab) {
    setTab(nextTab);
    const url = new URL(window.location.href);
    url.searchParams.set("dispositionTab", nextTab);
    window.history.replaceState(null, "", `${url.pathname}?${url.searchParams.toString()}${url.hash}`);
  }

  const messageIsError = Boolean(
    message && /(unable|failed|could not|unavailable|error|missing|required|must |cannot|can't|not found|stale|blocked)/i.test(message),
  );

  return (
    <section aria-label="Disposition management" className={`${styles.workspace} ${styles.embeddedWorkspace}`}>
      {message ? <p aria-live="polite" className={messageIsError ? styles.notice : styles.success} role={messageIsError ? "alert" : "status"}>{message}</p> : null}
      {!canEditDeals ? <p className={styles.notice} role="status">Read-only access: disposition actions are disabled for your role.</p> : null}

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
                    canEdit={canEditDeals}
                    copilot={copilot}
                    onGenerate={generateCopilot}
                    onReview={reviewCopilot}
                  />
                </CopilotLauncher>
              ) : null}
              <nav aria-label="Disposition deal sections" className={styles.tabs}>{(["package", "buyers", "outreach", "offers", "reconciliation"] as Tab[]).filter((item) => item !== "outreach" || canViewOutreach).map((item) => <button aria-current={tab === item ? "page" : undefined} className={tab === item ? styles.activeTab : ""} key={item} onClick={() => selectWorkspaceTab(item)} type="button">{item === "buyers" ? "Buyer pool" : labelize(item)}</button>)}</nav>

              {tab === "package" ? (
                <DispositionPackageReadiness
                  canEditDeals={canEditDeals}
                  caseId={selected.id}
                  dealId={dealId}
                  download={download}
                  key={selected.id}
                  leadId={selected.lead_id}
                  onCaseChanged={() => reload(selected.id)}
                  onMessage={setMessage}
                  qualifiedBuyerCount={selected.matches.filter((item) => item.qualification_status === "qualified").length}
                  request={request}
                />
              ) : null}

              {tab === "buyers" ? (
                <DispositionBuyerPool
                  activityPanel={<form className={styles.form} onSubmit={engagement}><div className={styles.sectionTitle}><div><span>Buyer activity</span><h4>Log inquiry, showing, or follow-up</h4></div></div><label><span>Buyer</span><select name="buyer_id" required>{selected.matches.map((item) => <option key={item.id} value={item.buyer_id}>{item.buyer_name}</option>)}</select></label><label><span>Activity</span><select name="engagement_type"><option value="inquiry">Inquiry</option><option value="showing">Showing</option><option value="follow_up">Follow-up</option><option value="deposit">Deposit</option></select></label><label><span>Follow-up date and time</span><input name="scheduled_at" type="datetime-local" /><small>Used when the activity is a follow-up.</small></label><label><span>Notes</span><textarea name="notes" required rows={4} /></label><button disabled={busy || !canEditDeals || !selected.matches.length} type="submit">Log buyer activity</button><div className={styles.activityList}>{selected.engagements.slice(0, 5).map((item) => <p key={item.id}><strong>{item.buyer_name}</strong><span>{labelize(item.engagement_type)} - {item.scheduled_at ? "Scheduled " + new Date(item.scheduled_at).toLocaleString() + " - " : ""}{item.notes}</span></p>)}</div></form>}
                  canEditBuyers={canEditBuyers}
                  canEditDeals={canEditDeals}
                  caseId={selected.id}
                  key={selected.id}
                  legacyMatches={selected.matches}
                  onLegacyReload={() => reload(selected.id)}
                  onMessage={setMessage}
                  onUploadProof={uploadProof}
                  packageApproved={selected.package_status === "approved"}
                  parentBusy={busy}
                  request={request}
                />
              ) : null}

              {tab === "outreach" && canViewOutreach ? (
                <DispositionOutreachWorkspace
                  canApprove={canApproveOutreach}
                  canManage={canManageOutreach}
                  canSendBulk={canSendBulk}
                  caseId={selected.id}
                  key={selected.id}
                  onMessage={setMessage}
                  request={request}
                />
              ) : null}

              {tab === "offers" ? <div className={styles.sectionGrid}>
                <section className={styles.section}><div className={styles.sectionTitle}><div><span>Offer control</span><h4>Buyer offers</h4></div><strong>{selected.offers.length}</strong></div><div className={styles.offerList}>{selected.offers.map((item) => <article key={item.id}><div><strong>{item.buyer_name}</strong><span>{labelize(item.status)}</span></div><b>{money(item.amount_cents)}</b><small>{money(item.earnest_money_cents)} deposit - {labelize(item.financing_type)}</small></article>)}{!selected.offers.length ? <p className={styles.emptyRow}>No buyer offers recorded.</p> : null}</div></section>
                <div className={styles.rightStack}><form className={styles.form} onSubmit={offer}><div className={styles.sectionTitle}><div><span>Document evidence</span><h4>Record offer</h4></div></div><label><span>Buyer</span><select name="buyer_id" required>{selected.matches.map((item) => <option key={item.id} value={item.buyer_id}>{item.buyer_name}</option>)}</select></label><div className={styles.twoFields}><label><span>Offer</span><input name="amount" inputMode="decimal" required /></label><label><span>Earnest money</span><input name="earnest_money" defaultValue="5000" inputMode="decimal" required /></label></div><label><span>Financing</span><select name="financing_type"><option value="cash">Cash</option><option value="hard_money">Hard money</option><option value="private_money">Private money</option></select></label><label><span>Notes</span><textarea name="notes" rows={3} /></label><button disabled={busy || !canEditDeals || !selected.matches.length} type="submit">Record offer</button></form>
                  <form className={styles.form} onSubmit={selectBuyer}><div className={styles.sectionTitle}><div><span>Human decision</span><h4>Approve buyer</h4></div></div><label><span>Primary offer</span><select name="primary_offer_id" required>{selected.offers.map((item) => <option key={item.id} value={item.id}>{item.buyer_name} - {money(item.amount_cents)}</option>)}</select></label><label><span>Backup offer</span><select name="backup_offer_id"><option value="">No backup</option>{selected.offers.map((item) => <option key={item.id} value={item.id}>{item.buyer_name} - {money(item.amount_cents)}</option>)}</select></label><label><span>Selection reason</span><textarea name="reason" required rows={3} placeholder="Price, verified funds, reliability, and closing capacity" /></label><button disabled={busy || !canEditDeals || !selected.offers.length} type="submit"><Check size={15} />Approve selection</button></form></div>
              </div> : null}

              {tab === "reconciliation" ? <div className={styles.sectionGrid}>
                <section className={styles.section}><div className={styles.sectionTitle}><div><span>Closing statement</span><h4>Deal reconciliation</h4></div><strong>{selected.reconciliation ? labelize(selected.reconciliation.status) : "Not calculated"}</strong></div>{selected.reconciliation ? <><dl className={styles.facts}><div><dt>Collected deal revenue</dt><dd>{money(selected.reconciliation.gross_revenue_cents)}</dd></div><div><dt>Acquisition reserve</dt><dd>-{money(selected.reconciliation.acquisition_reserve_cents)}</dd></div><div><dt>Deal-specific costs</dt><dd>-{money(selected.reconciliation.deal_deductions_cents)}</dd></div><div><dt>Adjusted deal margin</dt><dd>{money(selected.reconciliation.adjusted_deal_margin_cents)}</dd></div><div><dt>Commission payouts</dt><dd>{money(selected.reconciliation.total_compensation_cents)}</dd></div><div><dt>Company profit</dt><dd>{money(selected.reconciliation.company_profit_cents)}</dd></div><div><dt>Company share</dt><dd>{(selected.reconciliation.company_margin_basis_points / 100).toFixed(1)}% / {(selected.reconciliation.target_margin_basis_points / 100).toFixed(0)}% target</dd></div></dl><div className={styles.payouts}>{selected.reconciliation.payouts.map((item) => <div key={item.id}><span>{labelize(item.role_key)} - {item.user_name ?? "Unassigned"}</span><strong>{money(item.amount_cents)}</strong></div>)}</div></> : <p className={styles.emptyRow}>Fund the transaction and record collected revenue in Finance before calculating.</p>}</section>
                <section className={styles.actionPanel}><div className={styles.sectionTitle}><div><span>Owner control</span><h4>Close the books</h4></div></div><button disabled={busy || !canEditDeals || !selected.selected_buyer_id} onClick={() => action(() => post(`/api/v1/dispositions/cases/${selected.id}/reconciliation`), "Closing statement calculated from collected revenue and the frozen plan." )} type="button"><CircleDollarSign size={15} />Calculate statement</button><button disabled={busy || !canEditDeals || selected.reconciliation?.status !== "draft"} onClick={() => action(() => request(`/api/v1/dispositions/cases/${selected.id}/reconciliation/decision`, { method: "POST", body: JSON.stringify({ decision: "approved", notes: "Owner reviewed closing statement and payout allocation.", approve_below_target: false }) }), "Closing statement and commission payouts approved." )} type="button"><Check size={15} />Approve payouts</button><button disabled={busy || selected.reconciliation?.status !== "approved"} onClick={() => download(`/api/v1/dispositions/cases/${selected.id}/accounting.csv`, "stonegate-accounting-export.csv")} type="button"><Download size={15} />Accounting CSV</button><p>Approval is blocked when commission credit is unassigned or company profit falls below the active plan target.</p></section>
              </div> : null}
            </>
          )}
        </div>
      </section>
      {busy ? <div className={styles.busy}><LoaderCircle className={styles.spin} size={16} />Working</div> : null}
    </section>
  );
}
