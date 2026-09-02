"use client";

import {
  AlertTriangle,
  Check,
  DatabaseZap,
  Link2,
  Pin,
  RefreshCw,
  SearchCheck,
  ShieldCheck,
  UserPlus,
  UsersRound,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import type {
  BuyerDataProvider,
  BuyerDiscoveryEstimate,
  BuyerDiscoveryRun,
  BuyerDiscoverySearchTier,
  BuyerDiscoverySummary,
  BuyerListItem,
  BuyerListResponse,
  BuyerRelationshipOwner,
  DispositionBuyerPoolEntry,
  DispositionBuyerPoolPage,
} from "../../lib/api";
import { Drawer } from "../_components/design-system";
import { BuyerForm } from "../buyers/buyer-form";
import { labelize } from "../os-utils";
import styles from "./disposition-queue-builder.module.css";

type Requester = <T>(path: string, options?: RequestInit) => Promise<T>;

const DISCOVERY_TIERS: Array<{
  value: BuyerDiscoverySearchTier;
  label: string;
  targetCandidates: number;
  creditCap: number;
}> = [
  { value: "best_fit", label: "Best-Fit 10", targetCandidates: 10, creditCap: 30 },
  { value: "expanded", label: "Expand Nearby 20", targetCandidates: 20, creditCap: 60 },
  { value: "regional", label: "Regional Investors 40", targetCandidates: 40, creditCap: 120 },
];

function money(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function sourceLabel(entry: DispositionBuyerPoolEntry) {
  if (entry.source_type === "external") {
    return entry.provider ? `${labelize(entry.provider)} discovery` : "External discovery";
  }
  return entry.source_type === "mine" ? "My relationship" : "Stonegate network";
}

function availabilityLabel(entry: DispositionBuyerPoolEntry) {
  if (!entry.buyer_id) return "Review required";
  if (entry.decision_status === "passed" || entry.lifecycle_stage === "pass") return "Passed on this deal";
  return entry.eligibility_status === "eligible" ? "Ready in queue" : "Available with warnings";
}

export function DispositionQueueBuilder({
  assetClass,
  canEditBuyers,
  canEditDeals,
  caseId,
  onMessage,
  onQueueChanged,
  request,
}: {
  assetClass: string;
  canEditBuyers: boolean;
  canEditDeals: boolean;
  caseId: string;
  onMessage: (message: string | null) => void;
  onQueueChanged: () => Promise<void>;
  request: Requester;
}) {
  const [pool, setPool] = useState<DispositionBuyerPoolPage | null>(null);
  const [provider, setProvider] = useState<BuyerDataProvider | null>(null);
  const [summary, setSummary] = useState<BuyerDiscoverySummary | null>(null);
  const [estimates, setEstimates] = useState<Partial<Record<BuyerDiscoverySearchTier, BuyerDiscoveryEstimate>>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reviewCandidateId, setReviewCandidateId] = useState<string | null>(null);
  const [reviewReason, setReviewReason] = useState("");
  const [manualBuyerOpen, setManualBuyerOpen] = useState(false);
  const [builderOpen, setBuilderOpen] = useState(false);
  const [relationshipOwners, setRelationshipOwners] = useState<BuyerRelationshipOwner[]>([]);
  const [sourceOptions, setSourceOptions] = useState<string[]>(["manual"]);

  const loadPool = useCallback(async () => {
    const result = await request<DispositionBuyerPoolPage>(
      `/api/v1/dispositions/cases/${caseId}/buyer-pool?page=1&page_size=100&source=all&stage=all`,
      { cache: "no-store" },
    );
    setPool(result);
    setBuilderOpen((current) => current || !result.entries.some((entry) => entry.buyer_id));
    return result;
  }, [caseId, request]);

  const loadDiscovery = useCallback(async () => {
    if (assetClass !== "house") {
      setProvider(null);
      setSummary(null);
      return;
    }
    const providerResult = await request<BuyerDataProvider>("/api/v1/buyers/provider");
    const readyProvider = providerResult.configured
      ? await request<BuyerDataProvider>("/api/v1/buyers/provider/readiness")
      : providerResult;
    setProvider(readyProvider);
    const summaryResult = await request<BuyerDiscoverySummary>(
      `/api/v1/buyers/discovery-summary?case_id=${encodeURIComponent(caseId)}`,
    );
    setSummary(summaryResult);
  }, [assetClass, caseId, request]);

  const loadBuyerOptions = useCallback(async () => {
    if (!canEditBuyers) return;
    const result = await request<BuyerListResponse>("/api/v1/buyers?limit=1&offset=0");
    setRelationshipOwners(result.owner_options);
    setSourceOptions(Array.from(new Set(["manual", ...result.source_options])));
  }, [canEditBuyers, request]);

  useEffect(() => {
    let active = true;
    // Initial provider and queue synchronization is intentionally client-side.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void Promise.allSettled([loadPool(), loadDiscovery(), loadBuyerOptions()])
      .then((results) => {
        if (!active) return;
        const poolFailure = results[0].status === "rejected" ? results[0].reason : null;
        const discoveryFailure = results[1].status === "rejected" ? results[1].reason : null;
        const failure = poolFailure ?? discoveryFailure;
        if (failure) {
          setError(failure instanceof Error ? failure.message : "The investor queue controls could not be loaded.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [loadBuyerOptions, loadDiscovery, loadPool]);

  async function rebuildQueue(pinBuyerId?: string) {
    await request(`/api/v1/dispositions/cases/${caseId}/buyer-pool/runs`, {
      method: "POST",
      body: "{}",
    });
    await request(`/api/v1/dispositions/cases/${caseId}/execution/session`, {
      method: "PATCH",
      body: JSON.stringify({
        rerank_queue: true,
        ...(pinBuyerId ? { current_buyer_id: pinBuyerId } : {}),
      }),
    });
    await Promise.all([loadPool(), onQueueChanged()]);
  }

  async function rerankQueue() {
    if (!canEditDeals) return;
    setBusy("rerank");
    setError(null);
    onMessage(null);
    try {
      await rebuildQueue();
      onMessage("The latest explainable ranking is now in the outreach queue. Your current investor and saved progress were preserved.");
    } catch (actionError) {
      const detail = actionError instanceof Error ? actionError.message : "The outreach queue could not be reranked.";
      setError(detail);
      onMessage(detail);
    } finally {
      setBusy(null);
    }
  }

  async function pinBuyer(buyerId: string, buyerName: string) {
    if (!canEditDeals) return;
    setBusy(`pin-${buyerId}`);
    setError(null);
    onMessage(null);
    try {
      await request(`/api/v1/dispositions/cases/${caseId}/execution/session`, {
        method: "PATCH",
        body: JSON.stringify({ current_buyer_id: buyerId }),
      });
      await onQueueChanged();
      onMessage(`${buyerName} is pinned as the current investor. This position will resume across visits.`);
    } catch (actionError) {
      const detail = actionError instanceof Error ? actionError.message : "The investor could not be pinned.";
      setError(detail);
      onMessage(detail);
    } finally {
      setBusy(null);
    }
  }

  async function previewTier(searchTier: BuyerDiscoverySearchTier) {
    const tier = DISCOVERY_TIERS.find((item) => item.value === searchTier);
    if (!tier || !canEditBuyers || !canEditDeals || !summary?.unlocked_tiers.includes(searchTier)) return;
    setBusy(`estimate-${searchTier}`);
    setError(null);
    onMessage(null);
    try {
      const estimate = await request<BuyerDiscoveryEstimate>("/api/v1/buyers/discovery-runs/estimate", {
        method: "POST",
        body: JSON.stringify({
          disposition_case_id: caseId,
          search_tier: searchTier,
          max_candidates: tier.targetCandidates,
        }),
      });
      setEstimates((current) => ({ ...current, [searchTier]: estimate }));
      onMessage(estimate.message);
    } catch (actionError) {
      const detail = actionError instanceof Error ? actionError.message : "The DealMachine estimate could not be loaded.";
      setError(detail);
      onMessage(detail);
    } finally {
      setBusy(null);
    }
  }

  async function runTier(searchTier: BuyerDiscoverySearchTier) {
    const tier = DISCOVERY_TIERS.find((item) => item.value === searchTier);
    const estimate = estimates[searchTier];
    if (!tier || !estimate || !estimate.enough_credits || !canEditBuyers || !canEditDeals) return;
    setBusy(`run-${searchTier}`);
    setError(null);
    onMessage(null);
    let run: BuyerDiscoveryRun;
    try {
      run = await request<BuyerDiscoveryRun>("/api/v1/buyers/discovery-runs", {
        method: "POST",
        body: JSON.stringify({
          disposition_case_id: caseId,
          search_tier: searchTier,
          confirmed_estimated_credits: estimate.estimated_credits,
          confirmed_request_fingerprint: estimate.request_fingerprint,
          max_candidates: tier.targetCandidates,
        }),
      });
    } catch (actionError) {
      const detail = actionError instanceof Error ? actionError.message : "DealMachine discovery could not be completed.";
      setError(detail);
      onMessage(detail);
      setBusy(null);
      return;
    }

    setEstimates((current) => {
      const next = { ...current };
      delete next[searchTier];
      return next;
    });
    try {
      await request(`/api/v1/dispositions/cases/${caseId}/buyer-pool/runs`, {
        method: "POST",
        body: "{}",
      });
      await request(`/api/v1/dispositions/cases/${caseId}/execution/session`, {
        method: "PATCH",
        body: JSON.stringify({ rerank_queue: true }),
      });
      await Promise.all([loadPool(), loadDiscovery(), onQueueChanged()]);
      onMessage(run.reused
        ? `${run.result_count} saved ${tier.label} results were reused. No provider credits were spent and no outreach was sent.`
        : `${run.result_count} DealMachine candidates were staged here for your review. No outreach was sent.`);
    } catch {
      await Promise.allSettled([loadPool(), loadDiscovery()]);
      const detail = `${run.result_count} ${tier.label} results were saved, but the outreach queue refresh did not finish. Do not run the search again; refresh this panel to load the saved results. No outreach was sent.`;
      setError(detail);
      onMessage(detail);
    } finally {
      setBusy(null);
    }
  }

  async function reviewCandidate(
    entry: DispositionBuyerPoolEntry,
    decision: "create_new" | "link_existing" | "reject",
  ) {
    const reason = reviewReason.trim();
    if (!canEditBuyers || !canEditDeals || reason.length < 3) return;
    setBusy(`review-${entry.candidate_id}`);
    setError(null);
    onMessage(null);
    try {
      await request<DispositionBuyerPoolPage>(
        `/api/v1/dispositions/cases/${caseId}/buyer-pool/candidates/${entry.candidate_id}/conversion`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_version: entry.lock_version,
            decision,
            reason,
            ...(decision === "link_existing" && entry.possible_buyer_id
              ? { existing_buyer_id: entry.possible_buyer_id }
              : {}),
          }),
        },
      );
      const nextPool = await loadPool();
      const reviewed = nextPool.entries.find((item) => item.candidate_id === entry.candidate_id);
      if (decision === "reject") {
        setPool(nextPool);
        onMessage(`${entry.name} was rejected for import. No Buyer Network record was changed.`);
      } else {
        if (!reviewed?.buyer_id) throw new Error("The approved buyer was saved, but the canonical relationship could not be identified. Refresh before outreach.");
        await rebuildQueue(reviewed.buyer_id);
        onMessage(`${entry.name} was approved into the Buyer Network, reranked, and pinned for outreach. Nothing was sent.`);
      }
      setReviewCandidateId(null);
      setReviewReason("");
    } catch (actionError) {
      const detail = actionError instanceof Error ? actionError.message : "The candidate review could not be saved.";
      setError(detail);
      onMessage(detail);
    } finally {
      setBusy(null);
    }
  }

  async function manualBuyerSaved(buyer: BuyerListItem) {
    setManualBuyerOpen(false);
    setBusy(`manual-${buyer.id}`);
    setError(null);
    onMessage(null);
    try {
      await rebuildQueue(buyer.id);
      onMessage(`${buyer.name} was added to the Buyer Network, reranked, and pinned for outreach. Verify criteria whenever useful; nothing was sent.`);
    } catch (actionError) {
      const detail = actionError instanceof Error ? actionError.message : "The buyer was added, but the outreach queue could not be refreshed.";
      setError(detail);
      onMessage(detail);
    } finally {
      setBusy(null);
    }
  }

  const entries = pool?.entries ?? [];
  const stagedEntries = entries.filter((entry) => entry.source_type === "external" && !entry.buyer_id);
  const queueEntries = entries.filter((entry) => entry.buyer_id);
  const ownedCount = pool?.run?.source_counts.internal ?? queueEntries.filter((entry) => entry.source_type !== "external").length;
  const approvedExternalCount = queueEntries.filter((entry) => entry.source_type === "external").length;
  const currentRun = pool?.run ? `Ranking v${pool.run.version_number}` : "No ranking yet";

  return (
    <>
      <details className={styles.builder} onToggle={(event) => setBuilderOpen(event.currentTarget.open)} open={builderOpen}>
        <summary>
          <span className={styles.summaryIcon}><UsersRound size={18} /></span>
          <span className={styles.summaryCopy}>
            <strong>Find and rank investors</strong>
            <small>Pull DealMachine results, add known buyers, and build the outreach list here</small>
          </span>
          <span className={styles.summaryMetrics}>
            <b>{queueEntries.length} in queue</b>
            <small>{stagedEntries.length} awaiting review · {currentRun}</small>
          </span>
        </summary>

        <div className={styles.body}>
          <header className={styles.overview}>
            <div>
              <span>Queue controls</span>
              <h4>Owned relationships and reviewed discoveries, together</h4>
              <p>Ranking is guidance. Alex can pin anyone, skip anyone in the call queue, and work with incomplete deal or buyer information.</p>
            </div>
            <dl>
              <div><dt>Owned network</dt><dd>{ownedCount}</dd></div>
              <div><dt>Approved external</dt><dd>{approvedExternalCount}</dd></div>
              <div><dt>Needs review</dt><dd>{stagedEntries.length}</dd></div>
              <div><dt>Visible results</dt><dd>{pool ? `${entries.length}/${pool.total}` : "—"}</dd></div>
            </dl>
            <div className={styles.primaryActions}>
              <button disabled={Boolean(busy) || loading || !canEditDeals} onClick={() => void rerankQueue()} type="button"><RefreshCw size={15} />{busy === "rerank" ? "Reranking…" : "Rerank queue"}</button>
              <button className={styles.secondary} disabled={Boolean(busy) || !canEditBuyers || !canEditDeals} onClick={() => setManualBuyerOpen(true)} type="button"><UserPlus size={15} />Add buyer</button>
            </div>
          </header>

          {error ? <div className={styles.error} role="alert"><AlertTriangle size={16} /><span>{error}</span><button disabled={loading || Boolean(busy)} onClick={() => { setError(null); void loadPool(); }} type="button">Retry</button></div> : null}

          <section className={styles.discovery} aria-labelledby="outreach-discovery-heading">
            <header>
              <div><span><DatabaseZap size={14} />DealMachine discovery</span><h4 id="outreach-discovery-heading">Expand only when the owned network needs help</h4></div>
              {assetClass === "house" && provider?.connected ? <small>{provider.plan_name ?? "Connected plan"} · {provider.credits_remaining?.toLocaleString() ?? "Unknown"} credits remaining</small> : null}
            </header>
            {assetClass !== "house" ? (
              <div className={styles.landNotice}><ShieldCheck size={17} /><div><strong>Land-safe queue building is active</strong><p>Owned Land buyers, manual additions, and Land-aware reranking are available. DealMachine&apos;s current search is residential, so it stays off instead of applying House assumptions to Land.</p></div></div>
            ) : (
              <>
                {!provider?.live_search_enabled ? <p className={styles.providerNotice}>{provider?.message ?? "Checking the DealMachine connection…"}</p> : null}
                <div className={styles.tiers}>
                  {DISCOVERY_TIERS.map((tier, index) => {
                    const status = summary?.tier_statuses.find((item) => item.search_tier === tier.value);
                    const estimate = estimates[tier.value];
                    const completed = status?.completed ?? false;
                    const unlocked = status?.unlocked ?? false;
                    const latestRun = status?.latest_run;
                    const reconciliationRequired = Boolean(latestRun && !completed && (latestRun.status === "running" || (latestRun.status === "failed" && latestRun.actual_credits == null)));
                    const maximumCost = status?.maximum_estimated_cost_usd ?? tier.creditCap * (summary?.approximate_cost_per_credit_usd ?? 0.0075);
                    return (
                      <article data-available={unlocked && !completed && !reconciliationRequired} key={tier.value}>
                        <div><span>Tier {index + 1}</span><strong>{tier.label}</strong><small>Up to {tier.targetCandidates} net-new candidates · {tier.creditCap}-credit cap · about {money(maximumCost)} max</small></div>
                        <p>{completed ? `${latestRun?.result_count ?? 0} saved results · ${latestRun?.actual_credits ?? 0} actual credits` : reconciliationRequired ? "Prior search needs credit reconciliation before another spend." : unlocked ? "Available · cost preview is free" : `Complete or reuse Tier ${index} first.`}</p>
                        {estimate ? <p className={styles.estimate}>{estimate.reused ? "Reuse saved results · " : ""}{estimate.total_matching_properties.toLocaleString()} matching purchases · {estimate.estimated_credits} estimated credits ({money(estimate.estimated_cost_usd)})</p> : null}
                        <div>
                          <button className={styles.secondary} disabled={Boolean(busy) || !unlocked || completed || reconciliationRequired || !provider?.live_search_enabled || !canEditBuyers || !canEditDeals} onClick={() => void previewTier(tier.value)} type="button"><SearchCheck size={14} />{busy === `estimate-${tier.value}` ? "Checking…" : "Preview cost"}</button>
                          <button disabled={Boolean(busy) || !estimate?.enough_credits || completed || !canEditBuyers || !canEditDeals} onClick={() => void runTier(tier.value)} type="button"><DatabaseZap size={14} />{busy === `run-${tier.value}` ? "Searching…" : estimate?.reused ? "Reuse results" : "Run search"}</button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              </>
            )}
            <footer><span>Cost and scope shown before search</span><span>Human approval before Buyer Network import</span><span>Never sends outreach automatically</span></footer>
          </section>

          <section className={styles.pool} aria-labelledby="outreach-pool-heading">
            <header><div><span>Unified ranked list</span><h4 id="outreach-pool-heading">Review discoveries or pin anyone already in the network</h4></div><button className={styles.secondary} disabled={Boolean(busy) || loading} onClick={() => void loadPool()} type="button"><RefreshCw size={14} />Refresh list</button></header>
            {loading ? <p className={styles.empty}>Loading investor sources and ranking…</p> : entries.length ? (
              <ol>
                {entries.map((entry) => {
                  const reviewing = reviewCandidateId === entry.candidate_id;
                  const externalCandidate = entry.source_type === "external" && !entry.buyer_id;
                  return (
                    <li data-review={externalCandidate} key={entry.candidate_id}>
                      <span className={styles.rank}>{entry.rank ?? "—"}</span>
                      <div className={styles.identity}>
                        <strong>{entry.name}</strong>
                        <small>{entry.company_name ?? "Independent investor"} · {entry.phone ?? entry.email ?? "No contact recorded"}</small>
                        <span><b>{sourceLabel(entry)}</b><b data-warning={externalCandidate}>{availabilityLabel(entry)}</b></span>
                      </div>
                      <div className={styles.fit}><strong>{Math.round(entry.score_basis_points / 100)}%</strong><small>{entry.score_explanation[0] ?? "Current evidence scored"}</small></div>
                      <div className={styles.rowActions}>
                        {entry.buyer_id ? <button disabled={Boolean(busy) || !canEditDeals} onClick={() => void pinBuyer(entry.buyer_id!, entry.name)} type="button"><Pin size={14} />{busy === `pin-${entry.buyer_id}` ? "Pinning…" : "Pin for outreach"}</button> : <button disabled={Boolean(busy) || !canEditBuyers || !canEditDeals} onClick={() => { setReviewCandidateId(reviewing ? null : entry.candidate_id); setReviewReason(""); }} type="button"><ShieldCheck size={14} />Review</button>}
                      </div>
                      {reviewing ? (
                        <div className={styles.reviewEditor}>
                          <div><strong>Review provider evidence</strong><p>{entry.score_explanation.slice(0, 3).join(" ") || "DealMachine evidence is staged as a signal and still needs your judgment."}</p>{entry.purchase_evidence.length ? <ul className={styles.purchaseEvidence}>{entry.purchase_evidence.slice(0, 2).map((purchase, index) => <li key={purchase.provider_property_id ?? `${entry.candidate_id}-purchase-${index}`}><strong>{purchase.address}</strong><span>{purchase.purchase_date ? new Date(`${purchase.purchase_date}T12:00:00`).toLocaleDateString() : "Date not recorded"} · {purchase.purchase_price_cents == null ? "Price not recorded" : money(purchase.purchase_price_cents / 100)}</span></li>)}</ul> : null}{entry.possible_buyer_id ? <small><Link2 size={12} />Possible existing match: {entry.possible_buyer_name ?? entry.possible_buyer_company_name ?? "Buyer Network record"}</small> : null}</div>
                          <label><span>Review reason</span><textarea autoFocus maxLength={1000} onChange={(event) => setReviewReason(event.target.value)} placeholder="What did you review, and why is this the right decision?" rows={2} value={reviewReason} /></label>
                          <div>
                            <button className={styles.secondary} disabled={Boolean(busy)} onClick={() => { setReviewCandidateId(null); setReviewReason(""); }} type="button"><X size={14} />Cancel</button>
                            <button className={styles.secondary} disabled={Boolean(busy) || reviewReason.trim().length < 3} onClick={() => void reviewCandidate(entry, "reject")} type="button"><X size={14} />Reject</button>
                            {entry.possible_buyer_id ? <button disabled={Boolean(busy) || reviewReason.trim().length < 3} onClick={() => void reviewCandidate(entry, "link_existing")} type="button"><Link2 size={14} />Link existing</button> : null}
                            <button disabled={Boolean(busy) || reviewReason.trim().length < 3} onClick={() => void reviewCandidate(entry, "create_new")} type="button"><Check size={14} />Approve new buyer</button>
                          </div>
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ol>
            ) : <p className={styles.empty}>No ranked results are saved yet. Rerank the owned network or add a buyer manually.</p>}
          </section>
        </div>
      </details>

      <Drawer description="Create the relationship now, then verify House or Land criteria whenever useful. The buyer will be reranked and pinned without losing this outreach session." onClose={() => setManualBuyerOpen(false)} open={manualBuyerOpen} title="Add an investor to this queue">
        <BuyerForm onCancel={() => setManualBuyerOpen(false)} onSaved={(buyer) => void manualBuyerSaved(buyer)} onUseExisting={(buyerId) => { setManualBuyerOpen(false); void rebuildQueue(buyerId).then(() => onMessage("The existing Buyer Network relationship was pinned for outreach.")).catch((actionError: unknown) => onMessage(actionError instanceof Error ? actionError.message : "The existing buyer could not be pinned.")); }} relationshipOwners={relationshipOwners} sourceOptions={sourceOptions} />
      </Drawer>
    </>
  );
}
