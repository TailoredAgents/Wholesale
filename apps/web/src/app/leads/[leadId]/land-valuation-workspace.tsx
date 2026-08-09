"use client";

import { useAuth } from "@clerk/nextjs";
import { CalendarDays, FileText, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import styles from "./page.module.css";

type LandComparable = {
  key: string;
  provider_id: string | null;
  formatted_address: string | null;
  parcel_id: string | null;
  county: string | null;
  state: string | null;
  property_use: string | null;
  sale_date: string | null;
  sale_price_cents: number | null;
  acres: number | null;
  price_per_acre_cents: number | null;
  distance_miles: number | null;
  evidence_tier: "preferred" | "expanded" | "extended" | null;
  selection_status: "selected" | "rejected";
  selection_reason: string;
};

type ComparableReviewCandidate = {
  comparable: LandComparable;
  savedReasons: string[];
  wasSelected: boolean;
};

type LandValuation = {
  id: string;
  version_number: number;
  status: "ready" | "needs_review" | "insufficient_evidence";
  guidance_status: "available" | "withheld";
  is_current: boolean;
  valuation_basis: "per_acre" | "per_lot";
  access_evidence_status: "unknown" | "reported" | "verified";
  subject_acres: number;
  supported_value_low_cents: number | null;
  supported_value_cents: number | null;
  supported_value_high_cents: number | null;
  quick_sale_low_cents: number | null;
  quick_sale_high_cents: number | null;
  opening_offer_cents: number | null;
  seller_contract_ceiling_cents: number | null;
  confidence_score: number;
  selected_comps: LandComparable[];
  rejected_comps: LandComparable[];
  review_reasons: string[];
  guidance_blockers: string[];
  subject_snapshot: Record<string, unknown>;
  search_snapshot: Record<string, unknown>;
  created_at: string;
};

type LandOfferPolicy = {
  id: string;
  version_number: number;
  status: "draft" | "active" | "retired";
  title: string;
  quick_sale_discount_low_basis_points: number;
  quick_sale_discount_high_basis_points: number;
  opening_reserve_basis_points: number;
  assignment_fee_cents: number;
  closing_title_reserve_cents: number;
  curative_reserve_cents: number;
  uncertainty_reserve_cents: number;
  maximum_dispersion_basis_points: number;
  minimum_comparable_count: number;
};

type LoadState = "loading" | "ready" | "saving" | "error";

function money(cents: number | null) {
  if (cents === null) return "Not established";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function guidanceMoney(cents: number | null) {
  return cents === null ? "Withheld" : money(cents);
}

function labelize(value: string | null) {
  if (!value) return "Unknown";
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function comparableReviewCandidates(analysis: LandValuation | null) {
  if (!analysis) return [];

  const candidatesByKey = new Map<string, ComparableReviewCandidate>();
  const addCandidate = (comparable: LandComparable, wasSelected: boolean) => {
    if (!comparable.key) return;
    const existing = candidatesByKey.get(comparable.key);
    if (existing) {
      existing.wasSelected ||= wasSelected;
      if (
        comparable.selection_reason
        && !existing.savedReasons.includes(comparable.selection_reason)
      ) {
        existing.savedReasons.push(comparable.selection_reason);
      }
      return;
    }
    candidatesByKey.set(comparable.key, {
      comparable,
      savedReasons: comparable.selection_reason ? [comparable.selection_reason] : [],
      wasSelected,
    });
  };

  analysis.selected_comps.forEach((comparable) => addCandidate(comparable, true));
  analysis.rejected_comps.forEach((comparable) => addCandidate(comparable, false));
  return [...candidatesByKey.values()];
}

async function responseError(response: Response) {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") return payload.detail;
    if (payload.detail) return JSON.stringify(payload.detail);
  } catch {
    // The API may return an empty response.
  }
  return `Request failed (${response.status}).`;
}

export function LandValuationWorkspace({ leadId }: { leadId: string }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [analysis, setAnalysis] = useState<LandValuation | null>(null);
  const [policies, setPolicies] = useState<LandOfferPolicy[]>([]);
  const [selectedCompKeys, setSelectedCompKeys] = useState<string[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [message, setMessage] = useState<string | null>(null);
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () =>
      process.env.NEXT_PUBLIC_DEV_USER_EMAIL
      ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  const getHeaders = useCallback(async () => {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    else headers["X-Dev-User-Email"] = devUserEmail;
    return headers;
  }, [devUserEmail, getToken]);

  const load = useCallback(async () => {
    try {
      const headers = await getHeaders();
      setState("loading");
      setMessage(null);
      const [latestResponse, policyResponse] = await Promise.all([
        fetch(`${apiBaseUrl}/api/v1/leads/${leadId}/land-valuations/latest`, {
          headers,
          cache: "no-store",
        }),
        fetch(`${apiBaseUrl}/api/v1/land-underwriting/offer-policies`, {
          headers,
          cache: "no-store",
        }),
      ]);
      if (!policyResponse.ok) throw new Error(await responseError(policyResponse));
      if (!latestResponse.ok && latestResponse.status !== 404) {
        throw new Error(await responseError(latestResponse));
      }
      const latest = latestResponse.ok
        ? ((await latestResponse.json()) as LandValuation)
        : null;
      setAnalysis(latest);
      setPolicies((await policyResponse.json()) as LandOfferPolicy[]);
      setSelectedCompKeys([
        ...new Set(latest?.selected_comps.map((comp) => comp.key).filter(Boolean) ?? []),
      ]);
      setState("ready");
    } catch (error) {
      setState("error");
      setMessage(error instanceof Error ? error.message : "Unable to load Land valuation.");
    }
  }, [apiBaseUrl, getHeaders, leadId]);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (active) return load();
      return undefined;
    });
    return () => {
      active = false;
    };
  }, [load]);

  async function submitAnalysis(
    formData: FormData,
    options: { sourceAnalysisId?: string; selectedKeys?: string[] } = {},
  ) {
    setState("saving");
    setMessage(null);
    const acreage = String(formData.get("subject_acres_override") ?? "").trim();
    const acreageReference = String(
      formData.get("subject_acres_evidence_reference") ?? "",
    ).trim();
    const accessStatus = String(formData.get("access_evidence_status") ?? "unknown");
    const accessReference = String(formData.get("access_evidence_reference") ?? "").trim();
    const subjectUse = String(formData.get("subject_use_override") ?? "").trim();
    const subjectUseReference = String(
      formData.get("subject_use_evidence_reference") ?? "",
    ).trim();
    const refreshComps = !options.sourceAnalysisId;
    const body: Record<string, unknown> = {
      refresh_comps: refreshComps,
      source_analysis_id: options.sourceAnalysisId,
      search_tier: String(formData.get("search_tier") ?? "preferred"),
      valuation_basis: "per_acre",
      access_evidence_status: accessStatus,
      access_evidence_reference: accessReference || null,
      subject_use_override: subjectUse || null,
      subject_use_evidence_reference: subjectUseReference || null,
      review_note: options.sourceAnalysisId
        ? "Human-reviewed saved comparable set; no provider search requested."
        : "Explicit Land closed-sale search requested from the CRM.",
    };
    if (refreshComps) body.idempotency_key = crypto.randomUUID();
    if (acreage) {
      body.subject_acres_override = Number(acreage);
      body.subject_acres_evidence_reference = acreageReference || null;
    }
    if (options.selectedKeys !== undefined) {
      body.selected_comp_keys = [...new Set(options.selectedKeys)];
    }

    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/leads/${leadId}/land-valuations`,
        {
          method: "POST",
          headers: await getHeaders(),
          body: JSON.stringify(body),
        },
      );
      if (!response.ok) throw new Error(await responseError(response));
      const saved = (await response.json()) as LandValuation;
      setAnalysis(saved);
      setSelectedCompKeys([
        ...new Set(saved.selected_comps.map((comp) => comp.key).filter(Boolean)),
      ]);
      setState("ready");
      setMessage(
        options.sourceAnalysisId
          ? "Reviewed comp set saved without another provider search."
          : "Land sale evidence and valuation saved.",
      );
      router.refresh();
    } catch (error) {
      setState("error");
      setMessage(error instanceof Error ? error.message : "Unable to run Land valuation.");
    }
  }

  async function runSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitAnalysis(new FormData(event.currentTarget));
  }

  async function saveReviewedSet(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!analysis) return;
    await submitAnalysis(new FormData(event.currentTarget), {
      sourceAnalysisId: analysis.id,
      selectedKeys: selectedCompKeys,
    });
  }

  async function createPolicy() {
    setState("saving");
    setMessage(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/land-underwriting/offer-policies`,
        {
          method: "POST",
          headers: await getHeaders(),
          body: JSON.stringify({
            title: "Stonegate Land offer policy",
            quick_sale_discount_low_basis_points: 1500,
            quick_sale_discount_high_basis_points: 2500,
            opening_reserve_basis_points: 1000,
            assignment_fee_cents: 1_500_000,
            closing_title_reserve_cents: 300_000,
            curative_reserve_cents: 500_000,
            uncertainty_reserve_cents: 500_000,
            maximum_dispersion_basis_points: 5000,
            minimum_comparable_count: 3,
            notes: "Initial owner-review draft. Activate only after confirming each amount.",
          }),
        },
      );
      if (!response.ok) throw new Error(await responseError(response));
      const policy = (await response.json()) as LandOfferPolicy;
      setPolicies((current) => [policy, ...current]);
      setState("ready");
      setMessage("Draft policy created. Review the amounts below before activating it.");
    } catch (error) {
      setState("error");
      setMessage(error instanceof Error ? error.message : "Unable to create policy.");
    }
  }

  async function activatePolicy(policy: LandOfferPolicy) {
    if (
      !window.confirm(
        `Activate ${policy.title} v${policy.version_number} for future Land offer guidance?`,
      )
    ) return;
    setState("saving");
    setMessage(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/land-underwriting/offer-policies/${policy.id}/activate`,
        {
          method: "POST",
          headers: await getHeaders(),
          body: JSON.stringify({
            reason: "Owner reviewed and approved this Land offer policy in the CRM.",
          }),
        },
      );
      if (!response.ok) throw new Error(await responseError(response));
      const activePolicy = (await response.json()) as LandOfferPolicy;
      setPolicies((current) =>
        current.map((item) =>
          item.id === activePolicy.id
            ? activePolicy
            : item.status === "active"
              ? { ...item, status: "retired" }
              : item,
        ),
      );
      setState("ready");
      setMessage("Land offer policy activated. Rerun or review the valuation to apply it.");
    } catch (error) {
      setState("error");
      setMessage(error instanceof Error ? error.message : "Unable to activate policy.");
    }
  }

  const activePolicy = policies.find((policy) => policy.status === "active") ?? null;
  const latestDraft = policies.find((policy) => policy.status === "draft") ?? null;
  const searchCount = analysis?.search_snapshot.provider_returned_count;
  const savedComparableCandidates = useMemo(
    () => comparableReviewCandidates(analysis),
    [analysis],
  );

  return (
    <div className={styles.tabGrid}>
      <div className={styles.mainColumn}>
        <section className={styles.sectionPanel} id="land-valuation-search">
          <div className={styles.sectionHeader}>
            <h2>Land closed-sale research</h2>
            <span>Explicit provider search</span>
          </div>
          <form className={styles.underwritingForm} onSubmit={runSearch}>
            <p>
              This button makes one RealEstateAPI Land sale search and saves the returned
              evidence. Opening this tab and reviewing saved sales do not use provider credits.
            </p>
            <div className={styles.taskGrid}>
              <label>
                <span>Search area</span>
                <select name="search_tier" defaultValue="preferred">
                  <option value="preferred">Preferred · 10 miles / 24 months</option>
                  <option value="expanded">Expanded · 25 miles / 36 months</option>
                  <option value="extended">Extended · 50 miles / 60 months</option>
                </select>
              </label>
              <label>
                <span>Legal access evidence</span>
                <select name="access_evidence_status" defaultValue="unknown">
                  <option value="unknown">Not checked</option>
                  <option value="reported">Reported only</option>
                  <option value="verified">Human verified</option>
                </select>
              </label>
            </div>
            <label>
              <span>Access evidence reference</span>
              <input
                name="access_evidence_reference"
                placeholder="County GIS link, plat, title evidence, or documented field review"
              />
            </label>
            <div className={styles.taskGrid}>
              <label>
                <span>Human-reviewed Land use group (optional)</span>
                <select name="subject_use_override" defaultValue="">
                  <option value="">Use saved provider record</option>
                  <option value="residential">Residential</option>
                  <option value="agricultural">Agricultural</option>
                  <option value="commercial">Commercial</option>
                  <option value="industrial">Industrial</option>
                  <option value="recreational">Recreational</option>
                </select>
              </label>
              <label>
                <span>Land-use evidence reference</span>
                <input
                  name="subject_use_evidence_reference"
                  placeholder="Zoning record, county GIS, deed, or reviewed source"
                />
              </label>
            </div>
            <div className={styles.taskGrid}>
              <label>
                <span>Acreage override (optional)</span>
                <input
                  inputMode="decimal"
                  min="0.0001"
                  name="subject_acres_override"
                  placeholder={analysis ? String(analysis.subject_acres) : "Use saved parcel acreage"}
                  step="0.0001"
                  type="number"
                />
              </label>
              <label>
                <span>Acreage evidence for override</span>
                <input
                  name="subject_acres_evidence_reference"
                  placeholder="County parcel record or survey reference"
                />
              </label>
            </div>
            <button disabled={state === "saving"} type="submit">
              {state === "saving" ? "Working..." : "Search closed Land sales and save analysis"}
            </button>
            <small>
              Provider AVMs, House ARV, living-area adjustments, and repair formulas are excluded.
            </small>
          </form>
          {message ? (
            <div className={styles.statusBox}>
              <span>{state === "error" ? "Needs attention" : "Update"}</span>
              <strong>{message}</strong>
            </div>
          ) : null}
        </section>

        <section className={styles.sectionPanel}>
          <div className={styles.sectionHeader}>
            <h2>Saved Land value evidence</h2>
            <span>{analysis ? `Version ${analysis.version_number}` : "Not run"}</span>
          </div>
          {state === "loading" ? <p className={styles.emptyState}>Loading saved evidence...</p> : null}
          {!analysis && state !== "loading" ? (
            <p className={styles.emptyState}>
              No Land valuation is saved yet. Confirm the parcel research, then run the explicit
              closed-sale search above.
            </p>
          ) : null}
          {analysis ? (
            <>
              <dl className={styles.moneyGrid}>
                <div><dt>Supported low</dt><dd>{money(analysis.supported_value_low_cents)}</dd></div>
                <div><dt>Supported value</dt><dd>{money(analysis.supported_value_cents)}</dd></div>
                <div><dt>Supported high</dt><dd>{money(analysis.supported_value_high_cents)}</dd></div>
                <div><dt>Confidence</dt><dd>{analysis.confidence_score}%</dd></div>
                <div>
                  <dt>Quick-sale range</dt>
                  <dd>
                    {analysis.quick_sale_low_cents === null
                      || analysis.quick_sale_high_cents === null
                      ? "Withheld"
                      : `${money(analysis.quick_sale_low_cents)} to ${money(analysis.quick_sale_high_cents)}`}
                  </dd>
                </div>
                <div><dt>Evidence captured</dt><dd>{new Date(analysis.created_at).toLocaleString()}</dd></div>
              </dl>
              {analysis.review_reasons.length ? (
                <div className={styles.recordList}>
                  <article>
                    <div className={styles.recordTitle}>
                      <strong>Review items</strong>
                      <span>{analysis.review_reasons.length}</span>
                    </div>
                    <ul>
                      {analysis.review_reasons.map((reason) => <li key={reason}>{reason}</li>)}
                    </ul>
                  </article>
                </div>
              ) : null}
              {analysis.guidance_blockers.length ? (
                <div className={styles.recordList}>
                  <article>
                    <div className={styles.recordTitle}>
                      <strong>Why offer guidance is withheld</strong>
                      <span>Fail closed</span>
                    </div>
                    <ul>
                      {analysis.guidance_blockers.map((reason) => <li key={reason}>{reason}</li>)}
                    </ul>
                  </article>
                </div>
              ) : null}
            </>
          ) : null}
        </section>

        {analysis && savedComparableCandidates.length > 0 ? (
          <section className={styles.sectionPanel}>
            <div className={styles.sectionHeader}>
              <h2>Comparable Land sales</h2>
              <span>
                {selectedCompKeys.length} selected / {savedComparableCandidates.length} saved
              </span>
            </div>
            <form className={styles.underwritingForm} onSubmit={saveReviewedSet}>
              <p>
                Check every saved sale that should support the conclusion, including a previously
                rejected candidate, or uncheck every sale to reject all. Saving re-evaluates the
                saved evidence and makes no provider call.
              </p>
              <div className={styles.taskGrid}>
                <label>
                  <span>Legal access evidence</span>
                  <select
                    defaultValue={analysis.access_evidence_status}
                    name="access_evidence_status"
                  >
                    <option value="unknown">Not checked</option>
                    <option value="reported">Reported only</option>
                    <option value="verified">Human verified</option>
                  </select>
                </label>
                <label>
                  <span>Access evidence reference</span>
                  <input
                    defaultValue={String(
                      analysis.subject_snapshot.access_evidence_reference ?? "",
                    )}
                    name="access_evidence_reference"
                    placeholder="County GIS, plat, title, or field evidence"
                  />
                </label>
              </div>
              <div className={styles.taskGrid}>
                <label>
                  <span>Human-reviewed Land use group</span>
                  <select
                    defaultValue={
                      analysis.subject_snapshot.land_use_source === "human_override"
                        ? String(analysis.subject_snapshot.land_use ?? "")
                        : ""
                    }
                    name="subject_use_override"
                  >
                    <option value="">Use saved provider record</option>
                    <option value="residential">Residential</option>
                    <option value="agricultural">Agricultural</option>
                    <option value="commercial">Commercial</option>
                    <option value="industrial">Industrial</option>
                    <option value="recreational">Recreational</option>
                  </select>
                </label>
                <label>
                  <span>Land-use evidence reference</span>
                  <input
                    defaultValue={String(
                      analysis.subject_snapshot.land_use_evidence_reference ?? "",
                    )}
                    name="subject_use_evidence_reference"
                    placeholder="Zoning record, county GIS, deed, or reviewed source"
                  />
                </label>
              </div>
              <div className={styles.recordList}>
                {savedComparableCandidates.map((candidate) => {
                  const comp = candidate.comparable;
                  const isSelected = selectedCompKeys.includes(comp.key);
                  return (
                    <article key={comp.key}>
                      <div className={styles.recordTitle}>
                        <label className={styles.checkboxLabel}>
                          <input
                            checked={isSelected}
                            onChange={(event) => setSelectedCompKeys((current) =>
                              event.target.checked
                                ? [...new Set([...current, comp.key])]
                                : current.filter((key) => key !== comp.key),
                            )}
                            type="checkbox"
                          />
                          <strong>
                            {comp.formatted_address ?? comp.parcel_id ?? "Parcel sale"}
                          </strong>
                        </label>
                        <span>{isSelected ? "Include" : "Exclude"}</span>
                      </div>
                      <dl className={styles.moneyGrid}>
                        <div><dt>Sale price</dt><dd>{money(comp.sale_price_cents)}</dd></div>
                        <div><dt>Sale date</dt><dd>{comp.sale_date ?? "Unknown"}</dd></div>
                        <div><dt>Acres</dt><dd>{comp.acres ?? "Unknown"}</dd></div>
                        <div><dt>Price per acre</dt><dd>{money(comp.price_per_acre_cents)}</dd></div>
                        <div><dt>Distance</dt><dd>{comp.distance_miles === null ? "County search" : `${comp.distance_miles.toFixed(2)} mi`}</dd></div>
                        <div><dt>Evidence tier</dt><dd>{labelize(comp.evidence_tier)}</dd></div>
                      </dl>
                      <small>
                        Saved status: {candidate.wasSelected ? "selected" : "rejected"}.
                        {candidate.savedReasons.length
                          ? ` ${candidate.savedReasons.join("; ")}`
                          : " No saved review reason."}
                      </small>
                    </article>
                  );
                })}
              </div>
              <small>
                Provider eligibility and the eight-sale limit are checked again when this saved
                review is submitted.
              </small>
              <input name="search_tier" type="hidden" value={String(analysis.search_snapshot.tier ?? "preferred")} />
              {analysis.subject_snapshot.acreage_source === "human_override" ? (
                <>
                  <input name="subject_acres_override" type="hidden" value={analysis.subject_acres} />
                  <input
                    name="subject_acres_evidence_reference"
                    type="hidden"
                    value={String(analysis.subject_snapshot.acreage_evidence_reference ?? "")}
                  />
                </>
              ) : null}
              <button disabled={state === "saving"} type="submit">
                Save reviewed comp set · no provider search
              </button>
            </form>
          </section>
        ) : null}

        <section className={styles.sectionPanel}>
          <div className={styles.sectionHeader}>
            <h2>Owner-approved Land offer policy</h2>
            <span>{activePolicy ? `Active v${activePolicy.version_number}` : "Required for offers"}</span>
          </div>
          <div className={styles.recordList}>
            {activePolicy ? (
              <PolicyCard policy={activePolicy} />
            ) : (
              <article>
                <div className={styles.recordTitle}>
                  <strong>No active Land offer policy</strong>
                  <span>Offer numbers withheld</span>
                </div>
                <p>
                  Value evidence can still be saved, but Stonegate will not calculate an opening
                  offer or seller ceiling until an owner reviews and activates a policy.
                </p>
              </article>
            )}
            {latestDraft ? (
              <article>
                <PolicyCard policy={latestDraft} />
                <button className={styles.landPolicyAction} disabled={state === "saving"} onClick={() => void activatePolicy(latestDraft)} type="button">
                  Review confirmation and activate this policy
                </button>
              </article>
            ) : (
              <button className={styles.landPolicyAction} disabled={state === "saving"} onClick={() => void createPolicy()} type="button">
                Create recommended policy draft for owner review
              </button>
            )}
          </div>
        </section>
      </div>

      <aside className={styles.valuationSummary}>
        <header>
          <span>Latest saved analysis</span>
          <strong>
            {analysis
              ? analysis.is_current
                ? labelize(analysis.guidance_status)
                : "Needs refresh"
              : "Research first"}
          </strong>
        </header>
        <dl>
          <div><dt>Asset class</dt><dd>Land</dd></div>
          <div><dt>Supported value</dt><dd>{money(analysis?.supported_value_cents ?? null)}</dd></div>
          <div><dt>Opening guidance</dt><dd>{guidanceMoney(analysis?.opening_offer_cents ?? null)}</dd></div>
          <div><dt>Seller ceiling</dt><dd>{guidanceMoney(analysis?.seller_contract_ceiling_cents ?? null)}</dd></div>
          <div><dt>Selected sales</dt><dd>{analysis?.selected_comps.length ?? 0}</dd></div>
          <div><dt>Provider results saved</dt><dd>{typeof searchCount === "number" ? searchCount : "Not run"}</dd></div>
          <div><dt>Residential ARV / repairs</dt><dd>Excluded</dd></div>
        </dl>
        <nav>
          <Link href={`/os/leads/${leadId}?tab=property`}>
            <FileText size={15} />Property evidence
          </Link>
          <a href="#land-valuation-search"><ShieldCheck size={15} />Run Land valuation</a>
          <Link href={`/os/leads/${leadId}?tab=appointments`}>
            <CalendarDays size={15} />Appointments
          </Link>
        </nav>
      </aside>
    </div>
  );
}

function PolicyCard({ policy }: { policy: LandOfferPolicy }) {
  return (
    <div>
      <div className={styles.recordTitle}>
        <strong>{policy.title} · v{policy.version_number}</strong>
        <span>{labelize(policy.status)}</span>
      </div>
      <dl className={styles.moneyGrid}>
        <div><dt>Quick-sale discount</dt><dd>{policy.quick_sale_discount_low_basis_points / 100}% to {policy.quick_sale_discount_high_basis_points / 100}%</dd></div>
        <div><dt>Opening reserve</dt><dd>{policy.opening_reserve_basis_points / 100}%</dd></div>
        <div><dt>Assignment target</dt><dd>{money(policy.assignment_fee_cents)}</dd></div>
        <div><dt>Closing/title reserve</dt><dd>{money(policy.closing_title_reserve_cents)}</dd></div>
        <div><dt>Curative reserve</dt><dd>{money(policy.curative_reserve_cents)}</dd></div>
        <div><dt>Uncertainty reserve</dt><dd>{money(policy.uncertainty_reserve_cents)}</dd></div>
        <div><dt>Minimum sales</dt><dd>{policy.minimum_comparable_count}</dd></div>
        <div><dt>Maximum dispersion</dt><dd>{policy.maximum_dispersion_basis_points / 100}%</dd></div>
      </dl>
    </div>
  );
}
