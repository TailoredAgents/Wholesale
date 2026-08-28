"use client";

import { usePathname, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  DatabaseZap,
  Link2,
  RefreshCw,
  Search,
  SearchCheck,
  ShieldCheck,
  Upload,
  UserCheck,
  UserPlus,
  UsersRound,
  XCircle,
} from "lucide-react";
import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";

import type {
  BuyerDataProvider,
  BuyerDiscoveryEstimate,
  BuyerDiscoveryRun,
  DispositionBuyerPoolEntry,
  DispositionBuyerPoolPage,
  DispositionBuyerPoolSource,
  DispositionBuyerPoolStage,
  DispositionMatch,
} from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./dispositions.module.css";

type Requester = <T>(path: string, options?: RequestInit) => Promise<T>;
type ConversionAction = "create_new" | "link_existing" | "reject";
type EditorAction = "pass" | "shortlist" | "clear" | ConversionAction;

const SOURCES: Array<{ value: DispositionBuyerPoolSource; label: string }> = [
  { value: "all", label: "All sources" },
  { value: "mine", label: "My buyers" },
  { value: "network", label: "Stonegate network" },
  { value: "external", label: "External candidates" },
];

const STAGES: Array<{ value: DispositionBuyerPoolStage; label: string }> = [
  { value: "all", label: "All stages" },
  { value: "discovered", label: "Discovered" },
  { value: "needs_review", label: "Needs review" },
  { value: "eligible", label: "Eligible" },
  { value: "shortlisted", label: "Shortlisted" },
  { value: "contacted", label: "Contacted" },
  { value: "interested", label: "Interested" },
  { value: "showing", label: "Showing" },
  { value: "offer", label: "Offer" },
  { value: "pass", label: "Passed" },
  { value: "selected", label: "Selected" },
  { value: "backup", label: "Backup" },
  { value: "fallout", label: "Fallout" },
];

function evidenceText(evidence: Record<string, unknown>) {
  for (const key of ["label", "reason", "description", "message", "summary", "value"]) {
    const value = evidence[key];
    if (typeof value === "string" && value.trim()) return value;
    if (typeof value === "number") return `${labelize(key)}: ${value}`;
  }
  return Object.entries(evidence)
    .filter(([, value]) => value != null && typeof value !== "object")
    .slice(0, 3)
    .map(([key, value]) => `${labelize(key)}: ${String(value)}`)
    .join(" · ") || "Evidence recorded in the current match run.";
}

function isPassed(entry: DispositionBuyerPoolEntry) {
  return entry.decision_status === "passed" || entry.lifecycle_stage === "pass";
}

function isShortlisted(entry: DispositionBuyerPoolEntry) {
  return entry.decision_status === "shortlisted" || entry.lifecycle_stage === "shortlisted";
}

export function DispositionBuyerPool({
  activityPanel,
  canEditBuyers,
  canEditDeals,
  caseId,
  legacyMatches,
  onLegacyReload,
  onMessage,
  onUploadProof,
  packageApproved,
  parentBusy,
  request,
}: {
  activityPanel: ReactNode;
  canEditBuyers: boolean;
  canEditDeals: boolean;
  caseId: string;
  legacyMatches: DispositionMatch[];
  onLegacyReload: () => Promise<void>;
  onMessage: (message: string | null) => void;
  onUploadProof: (event: FormEvent<HTMLFormElement>, buyerId: string) => Promise<void>;
  packageApproved: boolean;
  parentBusy: boolean;
  request: Requester;
}) {
  const pathname = usePathname();
  const currentSearchParams = useSearchParams();
  const [pool, setPool] = useState<DispositionBuyerPoolPage | null>(null);
  const [source, setSource] = useState<DispositionBuyerPoolSource>("all");
  const [stage, setStage] = useState<DispositionBuyerPoolStage>("all");
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [provider, setProvider] = useState<BuyerDataProvider | null>(null);
  const [estimate, setEstimate] = useState<BuyerDiscoveryEstimate | null>(null);
  const [editor, setEditor] = useState<{
    action: EditorAction;
    candidateId: string;
  } | null>(null);
  const [reason, setReason] = useState("");

  const returnTo = useMemo(() => {
    const query = currentSearchParams.toString();
    return `${pathname}${query ? `?${query}` : ""}`;
  }, [currentSearchParams, pathname]);
  const busy = parentBusy || loading || actionBusy;

  function poolPath(targetPage = page) {
    const query = new URLSearchParams({
      page: String(targetPage),
      page_size: "50",
      source,
      stage,
    });
    if (search) query.set("search", search);
    return `/api/v1/dispositions/cases/${caseId}/buyer-pool?${query.toString()}`;
  }

  async function loadPool(targetPage = page) {
    setLoading(true);
    setError(null);
    try {
      const result = await request<DispositionBuyerPoolPage>(poolPath(targetPage));
      setPool(result);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Buyer pool could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    void request<DispositionBuyerPoolPage>(poolPath())
      .then((result) => {
        if (active) setPool(result);
      })
      .catch((loadError) => {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : "Buyer pool could not be loaded.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
    // The authenticated request helper follows the active Clerk session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, page, search, source, stage]);

  useEffect(() => {
    let active = true;
    void request<BuyerDataProvider>("/api/v1/buyers/provider")
      .then(async (result) => result.configured
        ? request<BuyerDataProvider>("/api/v1/buyers/provider/readiness")
        : result)
      .then((result) => {
        if (active) setProvider(result);
      })
      .catch(() => {
        if (active) setProvider(null);
      });
    return () => {
      active = false;
    };
    // The authenticated request helper follows the active Clerk session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  async function previewExternalBuyerCost() {
    if (!canEditBuyers || !canEditDeals || !packageApproved) return;
    setActionBusy(true);
    setEstimate(null);
    onMessage(null);
    try {
      const result = await request<BuyerDiscoveryEstimate>(
        "/api/v1/buyers/discovery-runs/estimate",
        {
          method: "POST",
          body: JSON.stringify({ disposition_case_id: caseId, max_candidates: 25 }),
        },
      );
      setEstimate(result);
      onMessage(result.message);
    } catch (previewError) {
      onMessage(previewError instanceof Error ? previewError.message : "Credit preview failed.");
    } finally {
      setActionBusy(false);
    }
  }

  async function discoverExternalBuyers() {
    if (!canEditBuyers || !canEditDeals || !packageApproved || !estimate?.enough_credits) return;
    setActionBusy(true);
    onMessage(null);
    try {
      const discoveryRun = await request<BuyerDiscoveryRun>(
        "/api/v1/buyers/discovery-runs",
        {
          method: "POST",
          body: JSON.stringify({
            disposition_case_id: caseId,
            confirmed_estimated_credits: estimate.estimated_credits,
            max_candidates: 25,
          }),
        },
      );
      await request<DispositionBuyerPoolPage>(
        `/api/v1/dispositions/cases/${caseId}/buyer-pool/runs`,
        { method: "POST", body: "{}" },
      );
      const result = await request<DispositionBuyerPoolPage>(
        `/api/v1/dispositions/cases/${caseId}/buyer-pool?page=1&page_size=50&source=external&stage=all`,
      );
      setPool(result);
      setEstimate(null);
      setSource("external");
      setStage("all");
      setPage(1);
      onMessage(`${discoveryRun.result_count} external candidates were staged and ranked inside this deal's buyer pool. No outreach was sent.`);
    } catch (discoveryError) {
      onMessage(discoveryError instanceof Error ? discoveryError.message : "Buyer discovery failed.");
    } finally {
      setActionBusy(false);
    }
  }

  async function updateDecision(
    entry: DispositionBuyerPoolEntry,
    decisionStatus: "shortlisted" | "passed" | "undecided",
    decisionReason?: string,
  ) {
    if (!canEditDeals || !canEditBuyers) return;
    setActionBusy(true);
    onMessage(null);
    try {
      await request(
        `/api/v1/dispositions/cases/${caseId}/buyer-pool/candidates/${entry.candidate_id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            expected_version: entry.lock_version,
            decision_status: decisionStatus,
            ...(decisionStatus === "shortlisted" ? { lifecycle_stage: "shortlisted" } : {}),
            ...(decisionStatus === "passed" ? { lifecycle_stage: "pass" } : {}),
            ...(decisionReason ? { reason: decisionReason } : {}),
          }),
        },
      );
      await loadPool();
      setEditor(null);
      setReason("");
      onMessage(
        decisionStatus === "shortlisted"
          ? "Buyer shortlisted for this deal. No outreach was sent."
          : decisionStatus === "passed"
            ? "Buyer passed for this deal only. The Buyer Network record was not changed."
            : "Deal-specific buyer decision cleared.",
      );
    } catch (decisionError) {
      onMessage(decisionError instanceof Error ? decisionError.message : "Buyer decision could not be saved.");
    } finally {
      setActionBusy(false);
    }
  }

  async function convertCandidate(entry: DispositionBuyerPoolEntry, action: ConversionAction) {
    if (!canEditBuyers || !canEditDeals) return;
    const conversionDecision = action === "link_existing" ? "link_existing" : action === "reject" ? "reject" : "create_new";
    setActionBusy(true);
    onMessage(null);
    try {
      await request(
        `/api/v1/dispositions/cases/${caseId}/buyer-pool/candidates/${entry.candidate_id}/conversion`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_version: entry.lock_version,
            decision: conversionDecision,
            ...(conversionDecision === "link_existing" && entry.possible_buyer_id
              ? { existing_buyer_id: entry.possible_buyer_id }
              : {}),
            ...(reason.trim() ? { reason: reason.trim() } : {}),
          }),
        },
      );
      await Promise.all([loadPool(), onLegacyReload()]);
      setEditor(null);
      setReason("");
      onMessage(
        conversionDecision === "create_new"
          ? "Candidate approved into Stonegate as needs-review. No outreach was sent."
          : conversionDecision === "link_existing"
            ? "External evidence linked to the existing Stonegate buyer. No outreach was sent."
            : "External result rejected. No Buyer Network record was changed.",
      );
    } catch (conversionError) {
      onMessage(conversionError instanceof Error ? conversionError.message : "Candidate review could not be saved.");
    } finally {
      setActionBusy(false);
    }
  }

  function openEditor(candidateId: string, action: EditorAction) {
    setEditor({ action, candidateId });
    setReason("");
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextSearch = searchDraft.trim();
    if (nextSearch === search && page === 1) {
      void loadPool(1);
      return;
    }
    setLoading(true);
    setError(null);
    setPage(1);
    setSearch(nextSearch);
  }

  const firstVisible = pool?.total ? (pool.page - 1) * pool.page_size + 1 : 0;
  const lastVisible = pool ? Math.min(pool.total, (pool.page - 1) * pool.page_size + pool.entries.length) : 0;

  return (
    <div className={styles.buyerTab}>
      <section className={styles.discoveryPanel}>
        <header>
          <div>
            <span><DatabaseZap size={14} />External buyer intelligence</span>
            <h4>Provider candidate search</h4>
            <p>{provider?.message ?? "Checking buyer-data connection."}</p>
            {provider?.connected ? (
              <small>
                {provider.plan_name ?? "DealMachine"} plan · {provider.credits_remaining?.toLocaleString() ?? "Unknown"} credits available
                {provider.billing_cycle_end ? ` · resets ${new Date(provider.billing_cycle_end).toLocaleDateString()}` : ""}
              </small>
            ) : null}
          </div>
          <div className={styles.discoveryActions}>
            <button disabled={busy || !canEditBuyers || !canEditDeals || !packageApproved || !provider?.live_search_enabled} onClick={previewExternalBuyerCost} type="button">
              <SearchCheck size={15} />Preview search cost
            </button>
            <button disabled={busy || !canEditBuyers || !canEditDeals || !packageApproved || !estimate?.enough_credits} onClick={discoverExternalBuyers} type="button">
              <DatabaseZap size={15} />{estimate ? `Run search (up to ${estimate.estimated_credits} credits)` : "Run buyer search"}
            </button>
          </div>
        </header>
        {estimate ? (
          <p className={styles.discoveryEstimate}>
            {estimate.total_matching_properties.toLocaleString()} matching recent purchases · samples up to {estimate.provider_result_limit} properties · estimates {estimate.estimated_property_credits} property and {estimate.estimated_people_credits} owner credits. Running the search requires the explicit confirmation button above.
          </p>
        ) : null}
        {!packageApproved ? <p className={styles.discoveryEstimate}>Approve the investor package before spending provider credits on a deal-specific buyer search.</p> : null}
        <footer>
          <span>External results stay staged</span>
          <span>Human approval required</span>
          <span>No outreach sent</span>
        </footer>
      </section>

      <section aria-label="Deal buyer pool" className={styles.poolPanel}>
        <header className={styles.poolHeader}>
          <div>
            <span><UsersRound size={14} />Unified deal buyer pool</span>
            <h4>Owned relationships and staged candidates</h4>
            <p>Shortlisting never sends outreach. Passing applies only to this deal.</p>
          </div>
          <div>
            <strong>{pool?.total ?? 0}</strong>
            <small>{pool?.run ? `Run v${pool.run.version_number} · ${new Date(pool.run.generated_at).toLocaleString()}` : "No scored run yet"}</small>
          </div>
        </header>

        <form className={styles.poolToolbar} onSubmit={submitSearch}>
          <label>
            <span>Source</span>
            <select value={source} onChange={(event) => { setLoading(true); setError(null); setSource(event.target.value as DispositionBuyerPoolSource); setPage(1); }}>
              {SOURCES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label>
            <span>Stage</span>
            <select value={stage} onChange={(event) => { setLoading(true); setError(null); setStage(event.target.value as DispositionBuyerPoolStage); setPage(1); }}>
              {STAGES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label className={styles.poolSearch}>
            <span>Search</span>
            <div><Search size={14} /><input onChange={(event) => setSearchDraft(event.target.value)} placeholder="Buyer, company, email, or phone" value={searchDraft} /></div>
          </label>
          <button disabled={busy} type="submit">Apply</button>
          <button aria-label="Refresh buyer pool" disabled={busy} onClick={() => void loadPool()} type="button"><RefreshCw size={14} />Refresh</button>
        </form>

        {error ? (
          <div className={styles.poolError} role="alert">
            <AlertTriangle size={16} />
            <span><strong>Buyer pool unavailable</strong>{error}</span>
            <button disabled={loading} onClick={() => void loadPool()} type="button">Retry</button>
          </div>
        ) : null}

        <div className={styles.poolList}>
          {pool?.entries.map((entry) => {
            const passed = isPassed(entry);
            const shortlisted = isShortlisted(entry);
            const isExternalCandidate = entry.source_type === "external" && !entry.buyer_id;
            const buyerHref = entry.buyer_id
              ? `/os/buyers?buyer=${encodeURIComponent(entry.buyer_id)}&returnTo=${encodeURIComponent(returnTo)}`
              : null;
            const possibleBuyerHref = entry.possible_buyer_id
              ? `/os/buyers?buyer=${encodeURIComponent(entry.possible_buyer_id)}&returnTo=${encodeURIComponent(returnTo)}`
              : null;
            const activeEditor = editor?.candidateId === entry.candidate_id ? editor : null;

            return (
              <article className={styles.poolCard} key={entry.id}>
                <div className={styles.poolCardHeader}>
                  <span className={styles.rank}>{entry.rank ?? "—"}</span>
                  <div className={styles.poolIdentity}>
                    <div>
                      <strong>{entry.name}</strong>
                      {entry.company_name ? <span>{entry.company_name}</span> : null}
                    </div>
                    <p>{entry.email || "No email"} · {entry.phone || "No phone"}</p>
                    <div className={styles.poolBadges}>
                      <span data-tone="source">{SOURCES.find((item) => item.value === entry.source_type)?.label ?? labelize(entry.source_type)}</span>
                      <span>{labelize(entry.lifecycle_stage)}</span>
                      <span data-tone={entry.eligibility_status === "eligible" ? "good" : "warning"}>{labelize(entry.eligibility_status)}</span>
                      {entry.overlap_status !== "none" ? <span data-tone="warning">{labelize(entry.overlap_status)}</span> : null}
                    </div>
                  </div>
                  <div className={styles.poolScore}>
                    <strong>{(entry.score_basis_points / 100).toFixed(0)}%</strong>
                    <span>{entry.provider ?? labelize(entry.origin_type)}</span>
                  </div>
                </div>

                <div className={styles.poolEvidence}>
                  <div>
                    <strong>Why it fits</strong>
                    {entry.score_explanation.length
                      ? entry.score_explanation.slice(0, 4).map((item) => <p key={item}><ShieldCheck size={13} />{item}</p>)
                      : entry.supporting_evidence.slice(0, 3).map((item, index) => <p key={`${entry.id}-support-${index}`}><ShieldCheck size={13} />{evidenceText(item)}</p>)}
                    {!entry.score_explanation.length && !entry.supporting_evidence.length ? <small>No supporting explanation was recorded.</small> : null}
                  </div>
                  <div>
                    <strong>Conflicts and blockers</strong>
                    {entry.disqualifying_reasons.map((item) => <p data-tone="danger" key={item}><XCircle size={13} />{item}</p>)}
                    {entry.conflicting_evidence.slice(0, 3).map((item, index) => <p data-tone="warning" key={`${entry.id}-conflict-${index}`}><AlertTriangle size={13} />{evidenceText(item)}</p>)}
                    {!entry.disqualifying_reasons.length && !entry.conflicting_evidence.length ? <small>No blocking evidence recorded.</small> : null}
                  </div>
                </div>

                <dl className={styles.poolFacts}>
                  <div><dt>Proof</dt><dd>{labelize(entry.proof_status)}{entry.proof_expires_at ? ` · ${new Date(entry.proof_expires_at).toLocaleDateString()}` : ""}</dd></div>
                  <div><dt>Relationship</dt><dd>{labelize(entry.relationship_status ?? "not established")}</dd></div>
                  <div><dt>Tier</dt><dd>{labelize(entry.tier ?? "not set")}</dd></div>
                  <div><dt>Temperature</dt><dd>{labelize(entry.temperature ?? "unknown")}</dd></div>
                </dl>

                {entry.decision_reason ? <p className={styles.poolDecisionReason}><strong>Decision note:</strong> {entry.decision_reason}</p> : null}

                {possibleBuyerHref && entry.possible_buyer_name ? (
                  <div className={styles.overlapReview}>
                    <AlertTriangle size={15} />
                    <span>
                      <strong>Possible existing buyer: {entry.possible_buyer_name}</strong>
                      {entry.possible_buyer_company_name ? ` · ${entry.possible_buyer_company_name}` : ""}
                      <small>{labelize(entry.overlap_status)} identity overlap. Review the existing profile before linking.</small>
                    </span>
                    <a href={possibleBuyerHref}>Review possible buyer</a>
                  </div>
                ) : null}

                <div className={styles.poolActions}>
                  <button disabled={busy || !canEditDeals || !canEditBuyers} onClick={() => {
                    if (shortlisted) openEditor(entry.candidate_id, "clear");
                    else if (passed) openEditor(entry.candidate_id, "shortlist");
                    else void updateDecision(entry, "shortlisted");
                  }} type="button">
                    <UserCheck size={14} />{shortlisted ? "Remove shortlist" : "Shortlist"}
                  </button>
                  <button disabled={busy || !canEditDeals || !canEditBuyers} onClick={() => openEditor(entry.candidate_id, passed ? "clear" : "pass")} type="button">
                    <XCircle size={14} />{passed ? "Undo pass" : "Pass for this deal"}
                  </button>
                  {isExternalCandidate ? (
                    <button disabled={busy || !canEditBuyers || !canEditDeals} onClick={() => openEditor(entry.candidate_id, "create_new")} type="button">
                      <UserPlus size={14} />Approve into network
                    </button>
                  ) : null}
                  {isExternalCandidate && entry.possible_buyer_id ? (
                    <button disabled={busy || !canEditBuyers || !canEditDeals} onClick={() => openEditor(entry.candidate_id, "link_existing")} type="button">
                      <Link2 size={14} />Link reviewed match
                    </button>
                  ) : null}
                  {isExternalCandidate ? (
                    <button disabled={busy || !canEditBuyers || !canEditDeals} onClick={() => openEditor(entry.candidate_id, "reject")} type="button">Reject result</button>
                  ) : null}
                  {buyerHref ? <a href={buyerHref}>Review buyer</a> : null}
                </div>

                {activeEditor ? (
                  <form className={styles.poolDecisionEditor} onSubmit={(event) => {
                    event.preventDefault();
                    if (activeEditor.action === "pass") void updateDecision(entry, "passed", reason.trim());
                    else if (activeEditor.action === "shortlist") void updateDecision(entry, "shortlisted", reason.trim());
                    else if (activeEditor.action === "clear") void updateDecision(entry, "undecided", reason.trim());
                    else void convertCandidate(entry, activeEditor.action);
                  }}>
                    <label>
                    <span>{activeEditor.action === "pass" ? "Pass reason" : activeEditor.action === "clear" ? "Change reason" : activeEditor.action === "shortlist" ? "Shortlist reason" : "Review reason"}</span>
                    <textarea autoFocus onChange={(event) => setReason(event.target.value)} placeholder={activeEditor.action === "pass" ? "Why is this buyer not a fit for this deal?" : activeEditor.action === "clear" ? "Why are you clearing the current deal decision?" : activeEditor.action === "shortlist" ? "Why should this previously passed buyer be shortlisted?" : "Why is this the right Buyer Network decision?"} required rows={2} value={reason} />
                    </label>
                    <div>
                      <button disabled={busy || (activeEditor.action === "pass" || activeEditor.action === "shortlist" || activeEditor.action === "clear" ? !reason.trim() : reason.trim().length < 3)} type="submit">
                        {activeEditor.action === "pass" ? "Save pass" : activeEditor.action === "shortlist" ? "Save shortlist" : activeEditor.action === "clear" ? "Clear decision" : activeEditor.action === "create_new" ? "Approve as needs-review" : activeEditor.action === "link_existing" ? "Link existing buyer" : "Reject result"}
                      </button>
                      <button disabled={busy} onClick={() => { setEditor(null); setReason(""); }} type="button">Cancel</button>
                    </div>
                    {activeEditor.action === "create_new" ? <small>Approval adds this candidate to the Buyer Network as needs-review. It does not qualify or contact the buyer.</small> : null}
                  </form>
                ) : null}

              </article>
            );
          })}
          {!loading && !error && !pool?.entries.length ? (
            <div className={styles.poolEmpty}>
              <UsersRound size={24} />
              <strong>No buyers match these filters</strong>
              <p>Refresh the deal match run, change the filters, or run external discovery.</p>
            </div>
          ) : null}
          {loading ? <p className={styles.emptyRow}>Loading the deal buyer pool…</p> : null}
        </div>

        <footer className={styles.poolPagination}>
          <span>{firstVisible}-{lastVisible} of {pool?.total ?? 0}</span>
          <div>
            <button disabled={busy || (pool?.page ?? 1) <= 1} onClick={() => { setLoading(true); setError(null); setPage((current) => Math.max(1, current - 1)); }} type="button">Previous</button>
            <button disabled={busy || !pool || pool.page * pool.page_size >= pool.total} onClick={() => { setLoading(true); setError(null); setPage((current) => current + 1); }} type="button">Next</button>
          </div>
        </footer>
      </section>

      <div className={styles.sectionGrid}>
        <section className={styles.section}>
          <div className={styles.sectionTitle}>
            <div><span>Release evidence</span><h4>Proof-of-funds readiness</h4></div>
            <strong>{legacyMatches.filter((item) => item.qualification_status === "qualified").length} qualified</strong>
          </div>
          <div className={styles.matchList}>
            {legacyMatches.length ? legacyMatches.map((match) => (
              <article key={match.id}>
                <div className={styles.matchTop}>
                  <span className={styles.rank}>{match.rank}</span>
                  <div><strong>{match.buyer_name}</strong><small>{labelize(match.qualification_status)} · POF {labelize(match.proof_status)}</small></div>
                  <b>{(match.score_basis_points / 100).toFixed(0)}%</b>
                </div>
                {!match.latest_proof_document_id ? (
                  <form className={styles.proofForm} onSubmit={(event) => onUploadProof(event, match.buyer_id)}>
                    <input aria-label="Institution" name="institution" placeholder="Bank or lender" required />
                    <input aria-label="Verified amount" name="verified_amount" inputMode="decimal" placeholder="Verified funds" required />
                    <input aria-label="Expires" name="expires_at" type="date" required />
                    <input aria-label="Proof document" name="file" type="file" required />
                    <button disabled={busy || !canEditBuyers} title="Verify proof of funds" type="submit"><Upload size={14} />Verify POF</button>
                  </form>
                ) : (
                  <p className={styles.verified}><ShieldCheck size={14} />Verified evidence attached{match.proof_expires_at ? ` · expires ${new Date(match.proof_expires_at).toLocaleDateString()}` : ""}</p>
                )}
              </article>
            )) : <p className={styles.emptyRow}>Approve the package, then generate buyer matches.</p>}
          </div>
        </section>
        {activityPanel}
        <section className={styles.poolGuidance}>
          <span>Decision boundaries</span>
          <h4>Human control stays explicit</h4>
          <p><UserCheck size={14} /><strong>Shortlist</strong> marks a deal candidate for later recipient review. It sends no email or text.</p>
          <p><XCircle size={14} /><strong>Pass</strong> removes the candidate from this deal only. It does not archive or suppress the buyer.</p>
          <p><UserPlus size={14} /><strong>Approve into network</strong> creates a needs-review buyer relationship. Buy box, contact identity, and proof still require verification.</p>
        </section>
      </div>
    </div>
  );
}
