"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { CalibrationOutcomeForm } from "./calibration-outcome-form";
import {
  CompCopilotPanel,
  type CompCopilotAction,
} from "./comp-copilot-panel";
import {
  MarketAdjustmentPanel,
  type MarketAdjustment,
} from "./adjustment-shadow-panel";
import {
  ComparableReviewWorkbench,
  COMPARABLE_EXCLUDED_REASONS,
  COMPARABLE_INCLUDED_REASONS,
  type CompAnalystRecommendation,
  type CompCondition,
  type CompReviewDraft,
  type MarketComparable,
  type SubjectProperty,
} from "./comparable-review-workbench";
import { ManualCompControl } from "./manual-comp-control";
import { GuidedRepairScope } from "./guided-repair-scope";
import {
  RepairEstimate,
  RepairEstimateControl,
  RepairEstimateItem,
} from "./repair-estimate-control";
import styles from "./page.module.css";

type RepairEntryMode = "system" | "total" | "itemized";
type VerificationStatus =
  | "preliminary"
  | "pre_meeting_reviewed"
  | "walkthrough_verified";
type PreMeetingInputs = {
  verification_status: VerificationStatus;
  report_stage: VerificationStatus;
  current_condition: string | null;
  target_condition: string;
  repair_level: string;
  repair_estimate_source: string;
  base_rehab_override_cents: number | null;
  repair_items: RepairEstimateItem[];
  contingency_override_percentage: number | null;
  holding_period_months: number;
  repair_notes: string | null;
  custom_inputs_applied: boolean;
  repair_estimate_id?: string | null;
  repair_estimate_contractor_name?: string | null;
  repair_estimate_date?: string | null;
  repair_estimate_reference?: string | null;
  repair_catalog_version?: string | null;
  repair_scenario?: RepairScenario | null;
};

type RepairScenario = {
  version?: string;
  total_low_cents?: number;
  total_expected_cents?: number;
  total_high_cents?: number;
  unknown_reserve_cents?: number;
  unknown_item_count?: number;
  specialist_item_count?: number;
  warnings?: string[];
};

type ConfidenceFactor = {
  key: string;
  label: string;
  score: number;
  maximum: number;
  summary: string;
};

type SecondaryEvidence = {
  research_version?: string;
  status?: string;
  summary?: string;
  address_match?: string;
  facts?: {
    fact_type: string;
    value: string;
    source_url: string;
    source_title: string;
  }[];
  conflicts?: {
    field: string;
    primary_value: string;
    web_value: string;
    source_url: string;
    explanation: string;
  }[];
  limitations?: string[];
  sources?: { url: string; title: string }[];
  comparable_candidates?: Array<{
    formatted_address: string;
    sale_price_dollars: number;
    sale_date: string;
    source_grade: "corroborated" | "cited_single_source";
    valuation_eligible: boolean;
    source_urls?: string[];
  }>;
  valuation_candidate_count?: number;
};

type CompSearchAttempt = {
  level: "preferred" | "expanded" | "extended" | "manual";
  radius_miles: number | null;
  days_old: number | null;
  bedroom_tolerance: number | null;
  bathroom_tolerance: number | null;
  square_footage_tolerance_percentage: number | null;
  year_built_tolerance_years: number | null;
  returned_count: number;
  unique_added_count: number;
  duplicate_count: number;
  cumulative_unique_count: number;
  selected_count: number;
  rejected_count: number;
  same_subdivision_count: number;
  expansion_reason: string | null;
  provider_error: string | null;
};

type CompSearchSummary = {
  strategy_version: string;
  final_level: "preferred" | "expanded" | "extended" | "manual";
  sufficient_closed_sales: boolean;
  minimum_closed_sales: number;
  total_provider_results: number;
  total_unique_sales: number;
  duplicate_count: number;
  subject_subdivision: string | null;
  same_subdivision_count: number;
  market_area_warning: string | null;
  evidence_shortage_reason: string | null;
  next_action: string | null;
  manual_verified_sale_count: number;
  manual_duplicate_count: number;
  ai_research_sale_count?: number;
  ai_research_duplicate_count?: number;
  ai_research_selected_count?: number;
  ai_research_source_count?: number;
  attempts: CompSearchAttempt[];
};

type SupportingEvidence = {
  status: "completed" | "partial" | "unavailable";
  evidence_role: "supporting_only";
  valuation_use: "excluded_from_arv_and_offer_math";
  sale_listings: Array<{
    provider_id: string | null;
    formatted_address: string | null;
    status: string;
    listing_type: string | null;
    asking_price_cents: number | null;
    bedrooms: number | null;
    bathrooms: number | null;
    square_footage: number | null;
    listed_date: string | null;
    days_on_market: number | null;
  }>;
  market_context: {
    zip_code: string | null;
    last_updated_date: string | null;
    median_list_price_cents: number | null;
    average_list_price_cents: number | null;
    median_price_per_square_foot_cents: number | null;
    average_days_on_market: number | null;
    median_days_on_market: number | null;
    total_listings: number | null;
    new_listings: number | null;
    median_list_price_change_percentage: number | null;
  } | null;
  errors: string[];
};

type EvidenceCitation = {
  evidence_id?: string | null;
  source_url?: string | null;
};

type AiCompRecommendation = CompAnalystRecommendation & {
  comp_key: string;
  condition_reason?: string | null;
  micro_market_concerns?: string[];
  citations?: EvidenceCitation[];
};

type AiRangeExplanation = {
  driver: string;
  affected_comp_keys?: string[];
  explanation: string;
  resolution_question?: string | null;
  citations?: EvidenceCitation[];
};

type AiDuplicateCandidate = {
  comp_keys?: string[];
  reason?: string;
  citations?: EvidenceCitation[];
};

type AiEvidenceConflict = {
  comp_keys?: string[];
  field?: string;
  description?: string;
  citations?: EvidenceCitation[];
};

type AiMicroMarketConcern = {
  comp_keys?: string[];
  concern: string;
  why_it_matters?: string;
  citations?: EvidenceCitation[];
};

type AiMissingQuestion = {
  question: string;
  why_it_matters?: string;
  related_comp_keys?: string[];
  citations?: EvidenceCitation[];
};

type AiCompAnalystContent = {
  status?: string;
  summary?: string;
  comp_recommendations?: AiCompRecommendation[];
  duplicate_candidates?: AiDuplicateCandidate[];
  conflicts?: AiEvidenceConflict[];
  micro_market_concerns?: AiMicroMarketConcern[];
  missing_questions?: AiMissingQuestion[];
  range_explanations?: AiRangeExplanation[];
  limitations?: string[];
};

type AiCompAnalystEnvelope = AiCompAnalystContent & {
  version?: string;
  status: "completed" | "insufficient" | "unavailable" | "rejected";
  mode?: string | null;
  valuation_use?: string | null;
  human_review_required?: boolean;
  model?: string | null;
  error?: string | null;
  analysis?: AiCompAnalystContent | null;
};

type ExternalBenchmark = {
  provider: string;
  label?: string | null;
  point_cents?: number | null;
  low_cents?: number | null;
  high_cents?: number | null;
  status?: string | null;
  source_url?: string | null;
  captured_at?: string | null;
  valuation_use?: string | null;
};

type CompIntelligence = {
  version?: string;
  mode?: "disabled" | "shadow" | "candidate" | string;
  valuation_use?: string | null;
  providers?: Array<{
    provider: string;
    status: string;
    valuation_use?: string | null;
    returned_count?: number;
    normalized_count?: number;
    retained_count?: number;
    unique_count?: number;
    usable_count?: number;
    net_new_count?: number;
    overlap_count?: number;
    dropped_count?: number;
    duplicate_count?: number;
    valuation_eligible_count?: number;
    ineligible_transfer_count?: number;
    conflict_count?: number;
    credits_used?: number | null;
    credits_estimated?: boolean | null;
    credit_cost_status?: string | null;
    latency_ms?: number | null;
    evidence_reused?: boolean;
    source_credits_used?: number | null;
    source_credits_estimated?: boolean | null;
    source_latency_ms?: number | null;
    error?: string | null;
  }>;
  corroborated_sale_count?: number;
  duplicate_count?: number;
  conflict_count?: number;
  source_conflicts?: unknown[];
  external_benchmarks?: ExternalBenchmark[];
  shadow_comps?: MarketComparable[];
  warnings?: string[];
  evidence_reused?: boolean;
};

type MarketValueEstimate = {
  id?: string;
  provider: string;
  requested_address: string;
  subject_property?: SubjectProperty;
  methodology_version?: string;
  estimated_value_cents: number | null;
  estimated_value_low_cents: number | null;
  estimated_value_high_cents: number | null;
  as_is_value_low_cents?: number | null;
  as_is_value_cents?: number | null;
  as_is_value_high_cents?: number | null;
  arv_low_cents?: number | null;
  arv_point_cents?: number | null;
  arv_high_cents?: number | null;
  conservative_arv_cents?: number | null;
  repair_low_cents?: number | null;
  repair_high_cents?: number | null;
  base_rehab_cents?: number | null;
  rehab_contingency_percentage?: number | null;
  total_rehab_cents?: number | null;
  repair_scenario?: RepairScenario | null;
  flip_buyer_max_cents?: number | null;
  rental_buyer_max_cents?: number | null;
  recommended_disposition_cents?: number | null;
  seller_contract_ceiling_cents?: number | null;
  transaction_reserve_cents?: number | null;
  recommended_offer_cents?: number | null;
  monthly_rent_cents?: number | null;
  confidence_score?: number;
  confidence_tier?: string;
  confidence_factors?: ConfidenceFactor[];
  address_evidence?: {
    resolved_address?: string;
    resolution_method?: string;
    match_score?: number;
    status?: string;
    issues?: string[];
  };
  secondary_evidence?: SecondaryEvidence;
  manual_review_required?: boolean;
  review_reasons?: string[];
  data_disagreements?: string[];
  assumptions?: Record<string, unknown>;
  report_stage?: VerificationStatus;
  pre_meeting_inputs?: PreMeetingInputs | null;
  comparables?: MarketComparable[];
  selected_comps?: MarketComparable[];
  rejected_comps?: MarketComparable[];
  subject_square_feet?: number | null;
  comp_search_summary?: CompSearchSummary | null;
  supporting_evidence?: SupportingEvidence | null;
  market_adjustment?: MarketAdjustment | null;
  adjustment_shadow?: MarketAdjustment | null;
  ai_comp_analyst?: AiCompAnalystEnvelope | null;
  comp_intelligence?: CompIntelligence | null;
  external_benchmarks?: ExternalBenchmark[];
  manual_comp_ids?: string[];
  source_note: string;
  created_at?: string;
  market_data_captured_at?: string | null;
  market_data_reused?: boolean;
  source_analysis_id?: string | null;
};

type Status = "idle" | "loading" | "loaded" | "error";
type ReportAudience = "investor" | "client";

const REPAIR_CONTINGENCY: Record<string, number> = {
  light: 10,
  moderate: 15,
  heavy: 20,
  structural: 25,
};

function formatMoney(cents: number | null | undefined) {
  if (cents === null || cents === undefined) {
    return "Not supported";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function formatNumber(value: number | null) {
  return value === null ? "Unknown" : new Intl.NumberFormat("en-US").format(value);
}

function reportStageLabel(value: VerificationStatus | undefined) {
  if (value === "walkthrough_verified") {
    return "Walkthrough verified";
  }
  if (value === "pre_meeting_reviewed") {
    return "Pre-meeting reviewed";
  }
  return "Preliminary";
}

function repairSourceLabel(value: PreMeetingInputs["repair_estimate_source"] | undefined) {
  if (value === "contractor_bid") {
    return "Contractor bid";
  }
  if (value === "walkthrough_scope") {
    return "Walkthrough scope";
  }
  if (value === "internal_scope") {
    return "Saved internal scope";
  }
  if (value === "itemized") {
    return "Itemized estimate";
  }
  if (value === "guided_catalog") {
    return "Guided Georgia scope";
  }
  if (value === "user_total") {
    return "User total";
  }
  return "System estimate";
}

function dollarsToCents(value: string) {
  if (!value.trim()) {
    return null;
  }
  const amount = Number(value.replace(/,/g, ""));
  return Number.isFinite(amount) && amount >= 0 ? Math.round(amount * 100) : null;
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) return "Not recorded";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function titleCaseValue(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function providerLabel(value: string) {
  const normalized = value.trim().toLowerCase();
  if (normalized.includes("rentcast")) return "RentCast";
  if (normalized.includes("dealmachine")) return "DealMachine";
  if (normalized.includes("realestateapi")) return "RealEstateAPI";
  return titleCaseValue(value || "Provider");
}

function externalBenchmarksFor(estimate: MarketValueEstimate | null) {
  if (!estimate) return [];
  if (estimate.external_benchmarks?.length) return estimate.external_benchmarks;
  if (estimate.comp_intelligence?.external_benchmarks?.length) {
    return estimate.comp_intelligence.external_benchmarks;
  }
  if (
    typeof estimate.estimated_value_cents !== "number" &&
    typeof estimate.estimated_value_low_cents !== "number" &&
    typeof estimate.estimated_value_high_cents !== "number"
  ) {
    return [];
  }
  return [
    {
      provider: estimate.provider,
      label: `${providerLabel(estimate.provider)} AVM`,
      point_cents: estimate.estimated_value_cents,
      low_cents: estimate.estimated_value_low_cents,
      high_cents: estimate.estimated_value_high_cents,
      valuation_use: "excluded_from_arv_and_offer_math",
    },
  ];
}

function aiCompAnalystFor(estimate: MarketValueEstimate | null) {
  if (!estimate) return null;
  if (estimate.ai_comp_analyst) return estimate.ai_comp_analyst;
  const saved = estimate.assumptions?.ai_comp_analyst;
  return saved && typeof saved === "object" ? (saved as AiCompAnalystEnvelope) : null;
}

function citationLinks(citations: EvidenceCitation[] | undefined) {
  const visible = (citations ?? []).filter(
    (citation) => citation.evidence_id || citation.source_url,
  );
  if (!visible.length) return null;
  return (
    <span className={styles.aiCitationList}>
      {visible.map((citation, index) => {
        const label = citation.evidence_id ?? `Evidence ${index + 1}`;
        return citation.source_url ? (
          <a
            href={citation.source_url}
            key={`${label}-${index}`}
            rel="noreferrer"
            target="_blank"
          >
            {label}
          </a>
        ) : (
          <span key={`${label}-${index}`}>{label}</span>
        );
      })}
    </span>
  );
}

function AiCompAnalystPanel({ envelope }: { envelope: AiCompAnalystEnvelope }) {
  const analysis = envelope.analysis ?? envelope;
  const recommendations = analysis?.comp_recommendations ?? [];
  const rangeExplanations = analysis?.range_explanations ?? [];
  const duplicates = analysis?.duplicate_candidates ?? [];
  const conflicts = analysis?.conflicts ?? [];
  const concerns = analysis?.micro_market_concerns ?? [];
  const questions = analysis?.missing_questions ?? [];
  const limitations = analysis?.limitations ?? [];

  return (
    <details className={styles.aiAnalystPanel} open={envelope.status === "completed"}>
      <summary>
        <span>AI comp analyst</span>
        <strong>{titleCaseValue(envelope.status)}</strong>
        <small>{recommendations.length} comp recommendation(s)</small>
      </summary>
      <div className={styles.aiAnalystBody}>
        <p className={styles.aiAnalystGuardrail}>
          Draft analysis only. AI cannot change the comp set, create a fact or adjustment, set ARV,
          or alter offer math.
        </p>
        {analysis?.summary ? <p>{analysis.summary}</p> : null}
        {recommendations.length ? (
          <section>
            <h4>Comp recommendations</h4>
            <div className={styles.aiRecommendationList}>
              {recommendations.map((recommendation, index) => (
                <article key={`${recommendation.comp_key}-${index}`}>
                  <div>
                    <strong>{recommendation.comp_key}</strong>
                    <span data-recommendation={recommendation.recommendation}>
                      Draft {recommendation.recommendation}
                    </span>
                  </div>
                  <p>{recommendation.reason}</p>
                  <small>
                    Condition hypothesis: {titleCaseValue(recommendation.condition_hypothesis ?? "unknown")}
                    {typeof recommendation.confidence === "number"
                      ? ` · ${Math.round(recommendation.confidence)}% confidence`
                      : ""}
                  </small>
                  {citationLinks(recommendation.citations)}
                </article>
              ))}
            </div>
          </section>
        ) : null}
        {rangeExplanations.length ? (
          <section>
            <h4>AI range explanations</h4>
            <div className={styles.aiRangeList}>
              {rangeExplanations.map((explanation, index) => (
                <article key={`${explanation.driver}-${index}`}>
                  <strong>{explanation.driver}</strong>
                  <p>{explanation.explanation}</p>
                  {explanation.resolution_question ? (
                    <small>Resolve by answering: {explanation.resolution_question}</small>
                  ) : null}
                  {explanation.affected_comp_keys?.length ? (
                    <small>Affected comps: {explanation.affected_comp_keys.join(", ")}</small>
                  ) : null}
                  {citationLinks(explanation.citations)}
                </article>
              ))}
            </div>
          </section>
        ) : null}
        {duplicates.length || conflicts.length || concerns.length ? (
          <section>
            <h4>Evidence checks</h4>
            <ul>
              {duplicates.map((duplicate, index) => (
                <li key={`duplicate-${index}`}>
                  Potential duplicate: {duplicate.reason ?? "review these sales"}
                  {duplicate.comp_keys?.length ? ` (${duplicate.comp_keys.join(", ")})` : ""}
                  {citationLinks(duplicate.citations)}
                </li>
              ))}
              {conflicts.map((conflict, index) => (
                <li key={`conflict-${index}`}>
                  Potential conflict{conflict.field ? ` in ${titleCaseValue(conflict.field)}` : ""}: {conflict.description ?? "review provider evidence"}
                  {conflict.comp_keys?.length ? ` (${conflict.comp_keys.join(", ")})` : ""}
                  {citationLinks(conflict.citations)}
                </li>
              ))}
              {concerns.map((concern, index) => (
                <li key={`${concern.concern}-${index}`}>
                  {concern.concern}
                  {concern.why_it_matters ? `: ${concern.why_it_matters}` : ""}
                  {concern.comp_keys?.length ? ` (${concern.comp_keys.join(", ")})` : ""}
                  {citationLinks(concern.citations)}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        {questions.length ? (
          <section>
            <h4>Questions that could tighten the analysis</h4>
            <ul>
              {questions.map((question, index) => (
                <li key={`${question.question}-${index}`}>
                  {question.question}
                  {question.related_comp_keys?.length
                    ? ` (${question.related_comp_keys.join(", ")})`
                    : ""}
                  {citationLinks(question.citations)}
                  {question.why_it_matters ? ` — ${question.why_it_matters}` : ""}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        {limitations.length ? <small>{limitations.join(" ")}</small> : null}
        {envelope.error ? <small>{envelope.error}</small> : null}
      </div>
    </details>
  );
}

function ExternalBenchmarkPanel({ benchmarks }: { benchmarks: ExternalBenchmark[] }) {
  if (!benchmarks.length) return null;
  return (
    <details className={styles.externalBenchmarks}>
      <summary>
        <span>External benchmarks</span>
        <strong>{benchmarks.length}</strong>
        <small>Secondary value opinions</small>
      </summary>
      <div className={styles.externalBenchmarkBody}>
        <p>
          Provider AVMs are disagreement screens only. They are excluded from Stonegate ARV,
          buyer economics, seller ceiling, and offer math.
        </p>
        <div className={styles.externalBenchmarkGrid}>
          {benchmarks.map((benchmark, index) => (
            <article key={`${benchmark.provider}-${benchmark.label ?? "benchmark"}-${index}`}>
              <div>
                <span>{benchmark.label ?? `${providerLabel(benchmark.provider)} benchmark`}</span>
                <strong>{formatMoney(benchmark.point_cents)}</strong>
              </div>
              <small>
                Provider range {formatMoney(benchmark.low_cents)} to {formatMoney(benchmark.high_cents)}
              </small>
              <small>Excluded from offer math</small>
              {benchmark.source_url ? (
                <a href={benchmark.source_url} rel="noreferrer" target="_blank">
                  Open provider source
                </a>
              ) : null}
            </article>
          ))}
        </div>
      </div>
    </details>
  );
}

function CompIntelligencePanel({ intelligence }: { intelligence: CompIntelligence }) {
  const providers = intelligence.providers ?? [];
  const activeProviderCount = providers.filter(
    (provider) =>
      provider.status === "completed" &&
      (provider.usable_count ?? provider.valuation_eligible_count ?? 0) > 0,
  ).length;
  return (
    <details className={styles.compIntelligencePanel}>
      <summary>
        <span>Comp source coverage</span>
        <strong>{activeProviderCount} evidence provider(s)</strong>
        <small>
          {intelligence.corroborated_sale_count ?? 0} corroborated · {intelligence.duplicate_count ?? 0} duplicate(s) · {intelligence.conflict_count ?? 0} conflict(s)
        </small>
      </summary>
      <div className={styles.compIntelligenceBody}>
        <p>
          {titleCaseValue(intelligence.mode ?? "disabled")} mode. Cross-provider matches are
          deduplicated before weighting, so the same sale never counts twice.
          {intelligence.evidence_reused
            ? " This run reused a previously captured provider snapshot."
            : ""}
        </p>
        <div className={styles.compProviderGrid}>
          {providers.map((provider) => (
            <article key={provider.provider}>
              <div>
                <strong>{providerLabel(provider.provider)}</strong>
                <span>{titleCaseValue(provider.status)}</span>
              </div>
              <small>
                {provider.returned_count ?? 0} returned · {provider.usable_count ?? provider.valuation_eligible_count ?? 0} usable · {provider.net_new_count ?? 0} net-new · {provider.overlap_count ?? 0} overlap
              </small>
              {provider.evidence_reused ? (
                <small>
                  Source capture: {provider.source_credits_used ?? "unknown"} credit(s)
                  {provider.source_credits_estimated ? " (estimated)" : ""}
                  {typeof provider.source_latency_ms === "number"
                    ? ` · ${provider.source_latency_ms.toLocaleString()} ms`
                    : ""}
                </small>
              ) : null}
              <small>
                {provider.dropped_count ?? 0} dropped · {provider.duplicate_count ?? 0} internal duplicate(s) · {provider.ineligible_transfer_count ?? 0} ineligible transfer(s) · {provider.conflict_count ?? 0} conflict(s)
              </small>
              <small>
                {typeof provider.credits_used === "number"
                  ? `${provider.credits_used} credit(s)${provider.credits_estimated ? " (estimated)" : ""}`
                  : "Credit use unavailable"}
                {typeof provider.latency_ms === "number"
                  ? ` · ${provider.latency_ms.toLocaleString()} ms`
                  : ""}
              </small>
              {provider.error ? <small>{provider.error}</small> : null}
            </article>
          ))}
        </div>
        {intelligence.warnings?.length ? <small>{intelligence.warnings.join(" ")}</small> : null}
      </div>
    </details>
  );
}

export function MarketValuePreview({ leadId }: { leadId: string }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [status, setStatus] = useState<Status>("idle");
  const [estimate, setEstimate] = useState<MarketValueEstimate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reportLoading, setReportLoading] = useState<ReportAudience | null>(null);
  const [repairLevel, setRepairLevel] = useState("moderate");
  const [verificationStatus, setVerificationStatus] =
    useState<VerificationStatus>("preliminary");
  const [repairEntryMode, setRepairEntryMode] = useState<RepairEntryMode>("system");
  const [baseRehabInput, setBaseRehabInput] = useState("");
  const [repairItems, setRepairItems] = useState<RepairEstimateItem[]>([]);
  const [repairNotes, setRepairNotes] = useState("");
  const [contingencyInput, setContingencyInput] = useState("");
  const [selectedRepairEstimateId, setSelectedRepairEstimateId] = useState<string | null>(null);
  const [selectedRepairEstimateSource, setSelectedRepairEstimateSource] = useState<string | null>(
    null,
  );
  const [conditionOverrides, setConditionOverrides] = useState<Record<string, CompCondition>>(
    {},
  );
  const [compReview, setCompReview] = useState<Record<string, CompReviewDraft>>({});
  const [reviewSaving, setReviewSaving] = useState(false);
  const [copilotFocus, setCopilotFocus] = useState<{
    compKey: string | null;
    nonce: number;
    view: "compare" | "location";
  } | null>(null);
  const [selectedManualCompIds, setSelectedManualCompIds] = useState<string[] | null>(null);
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  const getHeaders = useCallback(async () => {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = {};
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    } else {
      headers["X-Dev-User-Email"] = devUserEmail;
    }
    return headers;
  }, [devUserEmail, getToken]);

  const applyEstimate = useCallback((nextEstimate: MarketValueEstimate) => {
    setEstimate(nextEstimate);
    const nextOverrides: Record<string, CompCondition> = {};
    const allComps = [
      ...(nextEstimate.selected_comps ?? nextEstimate.comparables ?? []),
      ...(nextEstimate.rejected_comps ?? []),
    ];
    const nextReview: Record<string, CompReviewDraft> = {};
    for (const comp of allComps) {
      const key = comp.provider_id ?? comp.formatted_address;
      if (key) {
        nextOverrides[key] = comp.condition_classification ?? "unknown";
        const included = comp.selection_status !== "rejected";
        nextReview[key] = {
          included,
          reason:
            comp.review_reason ??
            (included
              ? COMPARABLE_INCLUDED_REASONS[0]
              : COMPARABLE_EXCLUDED_REASONS[0]),
          weight_percentage: comp.manual_weight_percentage ?? 100,
        };
      }
    }
    setConditionOverrides(nextOverrides);
    setCompReview(nextReview);
    setSelectedManualCompIds(nextEstimate.manual_comp_ids ?? []);
    const savedRepairLevel = nextEstimate.assumptions?.repair_level;
    if (typeof savedRepairLevel === "string") {
      setRepairLevel(savedRepairLevel);
    }
    const inputs = nextEstimate.pre_meeting_inputs;
    if (inputs) {
      setVerificationStatus(inputs.report_stage);
      setRepairLevel(inputs.repair_level);
      setRepairNotes(inputs.repair_notes ?? "");
      setContingencyInput(
        inputs.contingency_override_percentage === null
          ? ""
          : String(inputs.contingency_override_percentage),
      );
      setSelectedRepairEstimateId(inputs.repair_estimate_id ?? null);
      setSelectedRepairEstimateSource(
        inputs.repair_estimate_id ? inputs.repair_estimate_source : null,
      );
      if (
        inputs.repair_estimate_id ||
        inputs.repair_estimate_source === "itemized" ||
        inputs.repair_estimate_source === "guided_catalog"
      ) {
        setRepairEntryMode("itemized");
        setRepairItems(inputs.repair_items);
        setBaseRehabInput("");
      } else if (inputs.repair_estimate_source === "user_total") {
        setRepairEntryMode("total");
        setBaseRehabInput(
          inputs.base_rehab_override_cents === null
            ? ""
            : String(inputs.base_rehab_override_cents / 100),
        );
        setRepairItems([]);
      } else {
        setRepairEntryMode("system");
        setBaseRehabInput("");
        setRepairItems([]);
      }
    } else {
      setContingencyInput("");
      setRepairItems([]);
      setSelectedRepairEstimateId(null);
      setSelectedRepairEstimateSource(null);
    }
  }, []);

  function markInputsReviewed() {
    setVerificationStatus("pre_meeting_reviewed");
  }

  function detachSavedRepairEstimate() {
    setSelectedRepairEstimateId(null);
    setSelectedRepairEstimateSource(null);
  }

  function applySavedRepairEstimate(repairEstimate: RepairEstimate) {
    setRepairEntryMode("itemized");
    setRepairItems(repairEstimate.scope_items);
    setContingencyInput(String(repairEstimate.contingency_percentage));
    setRepairNotes(repairEstimate.notes ?? "");
    setSelectedRepairEstimateId(repairEstimate.id);
    setSelectedRepairEstimateSource(repairEstimate.source_type);
    markInputsReviewed();
  }

  useEffect(() => {
    const controller = new AbortController();

    async function loadLatestAnalysis() {
      setStatus("loading");
      setError(null);
      try {
        const response = await fetch(
          `${apiBaseUrl}/api/v1/leads/${leadId}/underwriting/market-analysis`,
          { headers: await getHeaders(), signal: controller.signal },
        );
        if (response.status === 404) {
          setStatus("idle");
          return;
        }
        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          throw new Error(payload?.detail ?? "Unable to load the latest comp analysis.");
        }
        applyEstimate((await response.json()) as MarketValueEstimate);
        setStatus("loaded");
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === "AbortError") {
          return;
        }
        setError(
          caught instanceof Error
            ? caught.message
            : "Unable to load the latest comp analysis.",
        );
        setStatus("error");
      }
    }

    void loadLatestAnalysis();
    return () => controller.abort();
  }, [apiBaseUrl, applyEstimate, getHeaders, leadId]);

  function buildAnalysisInputs() {
    const usingSavedEstimate = selectedRepairEstimateId !== null;
    const submittedRepairItems =
      repairEntryMode === "itemized" && !usingSavedEstimate
        ? repairItems
        : [];
    const baseRehabOverride =
      repairEntryMode === "total" && !usingSavedEstimate
        ? dollarsToCents(baseRehabInput)
        : null;
    if (repairEntryMode === "total" && baseRehabOverride === null) {
      throw new Error("Enter the expected base remodel cost.");
    }
    if (
      repairEntryMode === "itemized" &&
      submittedRepairItems.length === 0 &&
      !usingSavedEstimate
    ) {
      throw new Error("Assess at least one repair category.");
    }
    const unexplainedOverride = submittedRepairItems.find(
      (item) =>
        item.manual_override_cents !== null &&
        item.manual_override_cents !== undefined &&
        !item.override_reason?.trim(),
    );
    if (unexplainedOverride) {
      throw new Error(
        `Explain the manual amount for ${unexplainedOverride.category.replaceAll("_", " ")}.`,
      );
    }
    const contingencyPercentage = contingencyInput.trim()
      ? Number(contingencyInput)
      : null;
    if (
      contingencyPercentage !== null &&
      (!Number.isInteger(contingencyPercentage) ||
        contingencyPercentage < 0 ||
        contingencyPercentage > 50)
    ) {
      throw new Error("Contingency must be a whole percentage from 0 to 50.");
    }
    return {
      target_condition: "standard_flip",
      current_condition: null,
      repair_level: repairLevel,
      input_verification_status: verificationStatus,
      base_rehab_override_cents: baseRehabOverride,
      repair_items: submittedRepairItems,
      repair_estimate_id: selectedRepairEstimateId,
      contingency_override_percentage: usingSavedEstimate ? null : contingencyPercentage,
      holding_period_months: 6,
      repair_notes: repairNotes.trim() || null,
      comp_condition_overrides: conditionOverrides,
      manual_comp_ids: selectedManualCompIds,
    };
  }

  async function createAnalysis(refreshMarketData = false) {
    setStatus("loading");
    setError(null);
    try {
      const headers = await getHeaders();
      headers["Content-Type"] = "application/json";
      const response = await fetch(
        `${apiBaseUrl}/api/v1/leads/${leadId}/underwriting/market-analysis`,
        {
          body: JSON.stringify({
            ...buildAnalysisInputs(),
            refresh_market_data: refreshMarketData,
          }),
          headers,
          method: "POST",
        },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? "Unable to run underwriting.");
      }
      applyEstimate((await response.json()) as MarketValueEstimate);
      setStatus("loaded");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to analyze comps.");
      setStatus("error");
    }
  }

  function updateCompReview(compKey: string, decision: CompReviewDraft) {
    setCompReview((current) => ({ ...current, [compKey]: decision }));
    markInputsReviewed();
  }

  function updateCompCondition(compKey: string, condition: CompCondition) {
    setConditionOverrides((current) => ({ ...current, [compKey]: condition }));
    markInputsReviewed();
  }

  function restoreSystemCompSet() {
    if (!estimate) {
      return;
    }
    const allComps = [
      ...(estimate.selected_comps ?? estimate.comparables ?? []),
      ...(estimate.rejected_comps ?? []),
    ];
    const restored: Record<string, CompReviewDraft> = {};
    allComps.forEach((comp, index) => {
      const compKey = comp.provider_id ?? comp.formatted_address ?? `comp-${index}`;
      const included = comp.engine_selection_status
        ? comp.engine_selection_status === "selected"
        : comp.selection_status !== "rejected";
      restored[compKey] = {
        included,
        reason: included
          ? COMPARABLE_INCLUDED_REASONS[0]
          : COMPARABLE_EXCLUDED_REASONS[0],
        weight_percentage: 100,
      };
    });
    setCompReview(restored);
    markInputsReviewed();
  }

  function handleCopilotAction(action: CompCopilotAction) {
    if (action.action_type === "refresh_evidence") {
      document.getElementById("valuation-run-controls")?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
      return;
    }
    setCopilotFocus({
      compKey: action.comp_key,
      nonce: Date.now(),
      view: action.action_type === "verify_micro_market" ? "location" : "compare",
    });
    requestAnimationFrame(() => {
      document.getElementById("comparable-review")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
  }

  async function applyCompReview() {
    if (!estimate?.id) {
      return;
    }
    const decisions = Object.entries(compReview).map(([compKey, decision]) => ({
      comp_key: compKey,
      included: decision.included,
      reason: decision.reason,
      weight_percentage: decision.weight_percentage,
    }));
    if (!decisions.length) {
      setError("Run an analysis before reviewing comparable sales.");
      return;
    }
    setReviewSaving(true);
    setError(null);
    try {
      const headers = await getHeaders();
      headers["Content-Type"] = "application/json";
      const response = await fetch(
        `${apiBaseUrl}/api/v1/leads/${leadId}/underwriting/market-analysis/review`,
        {
          body: JSON.stringify({
            ...buildAnalysisInputs(),
            source_analysis_id: estimate.id,
            comp_review_decisions: decisions,
            refresh_market_data: false,
          }),
          headers,
          method: "POST",
        },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? "Unable to apply the comp review.");
      }
      applyEstimate((await response.json()) as MarketValueEstimate);
      setStatus("loaded");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to apply the comp review.");
    } finally {
      setReviewSaving(false);
    }
  }

  async function openReport(audience: ReportAudience) {
    if (!estimate?.id) {
      return;
    }
    setReportLoading(audience);
    setError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/leads/${leadId}/underwriting/market-analysis/` +
          `${estimate.id}/report.pdf?audience=${audience}`,
        { headers: await getHeaders() },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? "Unable to build report.");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to build report.");
    } finally {
      setReportLoading(null);
    }
  }

  const selectedComps = estimate?.selected_comps ?? estimate?.comparables ?? [];
  const reviewComps = [...selectedComps, ...(estimate?.rejected_comps ?? [])];
  const activeAdjustment = [estimate?.market_adjustment, estimate?.adjustment_shadow].find(
    (adjustment) => adjustment?.valuation_use === "live_human_reviewed_underwriting",
  ) ?? null;
  const adjustedIndications = Object.fromEntries(
    (activeAdjustment?.comp_adjustments ?? []).map((comp) => [
      comp.comp_key,
      comp.adjusted_indication_cents,
    ]),
  );
  const aiCompAnalyst = aiCompAnalystFor(estimate);
  const analystRecommendations = Object.fromEntries(
    (aiCompAnalyst?.comp_recommendations ?? aiCompAnalyst?.analysis?.comp_recommendations ?? []).map((recommendation) => [
      recommendation.comp_key,
      recommendation,
    ]),
  );
  const externalBenchmarks = externalBenchmarksFor(estimate);
  const providerControlsAsIs =
    estimate?.assumptions?.as_is_value_basis === "provider_avm_benchmark";
  const reviewItems = [
    ...(estimate?.review_reasons ?? []),
    ...(estimate?.data_disagreements ?? []),
  ];
  const currentRepairItems = repairItems;
  const isLoading = status === "loading";
  const isCurrentMethod = estimate?.methodology_version === "v3";
  const hasSupportedArv = typeof estimate?.arv_point_cents === "number";
  const isWorkingGuidance =
    estimate?.assumptions?.valuation_evidence_status === "working_two_sale_guidance";
  const hasVerifiedArv =
    !isWorkingGuidance &&
    (estimate?.assumptions?.arv_value_basis === "verified_renovated_recorded_sales" ||
      estimate?.assumptions?.arv_value_basis === "market_supported_adjusted_closed_sales");
  const activeReportStage = estimate?.report_stage ?? verificationStatus;
  const activeRepairSource =
    selectedRepairEstimateSource ??
    (repairEntryMode === "itemized"
      ? "itemized"
      : repairEntryMode === "total"
        ? "user_total"
        : "system_estimate");
  const activeRepairScenario =
    estimate?.repair_scenario ?? estimate?.pre_meeting_inputs?.repair_scenario;

  return (
    <section className={styles.marketValuePanel}>
      <div className={styles.marketValueHeader}>
        <div>
          <span className={styles.underwritingEyebrow}>Stonegate Valuation</span>
          <strong>Market-supported sales and buyer economics</strong>
          <span>Human-reviewed evidence for ARV, repairs, and seller negotiation limits</span>
        </div>
        <div className={styles.marketValueActions} id="valuation-run-controls">
          <button
            disabled={isLoading}
            onClick={() => void createAnalysis(false)}
            type="button"
          >
            {isLoading
              ? "Preparing..."
              : estimate
                ? "Update Stonegate valuation"
                : "Run Stonegate valuation"}
          </button>
          {estimate ? (
            <button
              disabled={isLoading}
              onClick={() => void createAnalysis(true)}
              title="Fetch a new provider snapshot; this may use paid provider credits."
              type="button"
            >
              Refresh market evidence (may use credits)
            </button>
          ) : null}
        </div>
      </div>

      {error ? <p className={styles.error}>{error}</p> : null}

      <details className={styles.preMeetingInputs} open={!estimate}>
        <summary>
          <div>
            <strong>Comp setup</strong>
            <span>Repair scope and an optional budget</span>
          </div>
          <span className={styles.reportStageBadge}>
            {reportStageLabel(activeReportStage)}
          </span>
        </summary>
        <div className={styles.preMeetingBody}>
          <div className={styles.preMeetingGrid}>
            <label>
              <span>Repair scope</span>
              <select
                onChange={(event) => {
                  setRepairLevel(event.target.value);
                  detachSavedRepairEstimate();
                  markInputsReviewed();
                }}
                value={repairLevel}
              >
                <option value="light">Light cosmetic</option>
                <option value="moderate">Moderate renovation</option>
                <option value="heavy">Heavy renovation</option>
                <option value="structural">Structural / full rebuild</option>
              </select>
            </label>
          </div>

          <div className={styles.repairEntryHeader}>
            <div>
              <strong>Remodel estimate</strong>
              <span>{repairSourceLabel(activeRepairSource)}</span>
            </div>
            <div className={styles.segmentedControl} aria-label="Remodel estimate method">
              {(
                [
                  ["system", "System"],
                  ["total", "Total"],
                  ["itemized", "Itemized"],
                ] as [RepairEntryMode, string][]
              ).map(([value, label]) => (
                <button
                  aria-pressed={repairEntryMode === value}
                  className={repairEntryMode === value ? styles.segmentActive : undefined}
                  key={value}
                  onClick={() => {
                    setRepairEntryMode(value);
                    detachSavedRepairEstimate();
                    if (value !== "system") {
                      markInputsReviewed();
                    }
                  }}
                  type="button"
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {repairEntryMode === "total" ? (
            <label className={styles.totalRepairInput}>
              <span>Expected base remodel cost</span>
              <div className={styles.moneyInput}>
                <span>$</span>
                <input
                  inputMode="decimal"
                  min="0"
                  onChange={(event) => {
                    setBaseRehabInput(event.target.value);
                    detachSavedRepairEstimate();
                    markInputsReviewed();
                  }}
                  placeholder="0"
                  step="500"
                  type="number"
                  value={baseRehabInput}
                />
              </div>
            </label>
          ) : null}

          {repairEntryMode === "itemized" ? (
            <GuidedRepairScope
              contingencyPercentage={
                contingencyInput.trim() === ""
                  ? REPAIR_CONTINGENCY[repairLevel] || 15
                  : Number(contingencyInput)
              }
              disabled={isLoading || selectedRepairEstimateId !== null}
              items={repairItems}
              leadId={leadId}
              onChange={(nextItems) => {
                setRepairItems(nextItems);
                detachSavedRepairEstimate();
                markInputsReviewed();
              }}
              repairLevel={repairLevel}
            />
          ) : null}

          {repairEntryMode !== "system" ? (
            <label className={styles.contingencyInput}>
              <span>Contingency reserve</span>
              <div>
                <input
                  disabled={selectedRepairEstimateId !== null}
                  inputMode="numeric"
                  max="50"
                  min="0"
                  onChange={(event) => {
                    setContingencyInput(event.target.value);
                    detachSavedRepairEstimate();
                    markInputsReviewed();
                  }}
                  placeholder={String(REPAIR_CONTINGENCY[repairLevel] ?? 15)}
                  step="1"
                  type="number"
                  value={contingencyInput}
                />
                <span>%</span>
              </div>
            </label>
          ) : null}

          <label className={styles.repairNotes}>
            <span>Repair details and source notes</span>
            <textarea
              maxLength={2000}
              onChange={(event) => {
                setRepairNotes(event.target.value);
                markInputsReviewed();
              }}
              placeholder="Known repairs, estimate source, property risks, or items to verify"
              rows={3}
              value={repairNotes}
            />
          </label>

          <RepairEstimateControl
            contingencyPercentage={
              contingencyInput.trim() === ""
                ? REPAIR_CONTINGENCY[repairLevel] || 15
                : Number(contingencyInput)
            }
            currentItems={currentRepairItems}
            currentNotes={repairNotes}
            leadId={leadId}
            onApply={applySavedRepairEstimate}
            onClear={detachSavedRepairEstimate}
            selectedEstimateId={selectedRepairEstimateId}
          />
        </div>
      </details>

      <ManualCompControl
        leadId={leadId}
        onEvidenceChanged={markInputsReviewed}
        onSelectedIdsChange={setSelectedManualCompIds}
        selectedIds={selectedManualCompIds}
      />

      {estimate ? (
        <div className={styles.marketValueResult}>
          {!isCurrentMethod ? (
            <div className={styles.reviewBanner}>
              This saved analysis uses a historical method. Recalculate to create a current Stonegate Valuation.
            </div>
          ) : null}
          <div
            className={
              (estimate.manual_review_required ?? true)
                ? styles.reviewBanner
                : styles.evidenceBanner
            }
          >
            <strong>
              {(estimate.manual_review_required ?? true)
                ? "Manual review required"
                : "Evidence threshold met"}
            </strong>
            <span>
              {(estimate.confidence_tier ?? "insufficient").replaceAll("_", " ")} confidence
              {" · "}
              {estimate.confidence_score ?? 0}/100. A person must still approve the acquisition
              decision.
            </span>
          </div>

          {activeAdjustment ? (
            <MarketAdjustmentPanel
              adjustment={activeAdjustment}
              arvHighCents={estimate.arv_high_cents}
              arvLowCents={estimate.arv_low_cents}
              arvPointCents={estimate.arv_point_cents}
              workingGuidance={isWorkingGuidance}
            />
          ) : (
            <section
              aria-label="Stonegate valuation conclusion"
              className={`${styles.adjustmentShadow} ${styles.adjustmentUnavailable}`}
            >
              <header className={styles.adjustmentShadowHeader}>
                <div>
                  <span>Stonegate valuation conclusion</span>
                  <strong>{hasSupportedArv ? "Saved historical ARV" : "ARV not supported"}</strong>
                </div>
                <small>Recalculate with the current method to review adjusted closed-sale math.</small>
              </header>
              <div className={styles.adjustmentShadowMetrics}>
                <div className={styles.adjustmentPrimaryMetric}>
                  <span>Stonegate ARV</span>
                  <strong>{formatMoney(estimate.arv_point_cents)}</strong>
                </div>
                <div className={styles.adjustmentRangeMetric}>
                  <span>Supported range</span>
                  <strong>
                    {formatMoney(estimate.arv_low_cents)} to {formatMoney(estimate.arv_high_cents)}
                  </strong>
                </div>
                <div>
                  <span>Valuation status</span>
                  <strong>Recalculation required</strong>
                  <small>Provider AVMs excluded from offer math</small>
                </div>
              </div>
            </section>
          )}

          <div className={styles.evidenceSummary}>
            <div>
              <span>Market evidence snapshot</span>
              <strong>{estimate.market_data_reused ? "Reused snapshot" : "Fresh capture"}</strong>
              <small>{formatTimestamp(estimate.market_data_captured_at)}</small>
            </div>
            <div>
              <span>Subject match</span>
              <strong>
                {(estimate.address_evidence?.status ?? "not checked").replaceAll("_", " ")}
              </strong>
              <small>
                {estimate.address_evidence?.resolved_address ?? estimate.requested_address}
              </small>
            </div>
            <div>
              <span>Core valuation evidence</span>
              <strong>{estimate.selected_comps?.length ?? 0} usable closed sales</strong>
              <small>
                {estimate.comp_search_summary
                  ? `${estimate.comp_search_summary.total_provider_results} provider results · ${estimate.comp_search_summary.ai_research_selected_count ?? 0} cited AI research sale(s)`
                  : "Screened by similarity and price per square foot"}
              </small>
            </div>
            <div>
              <span>Secondary research</span>
              <strong>
                {(estimate.secondary_evidence?.status ?? "unavailable").replaceAll("_", " ")}
              </strong>
              <small>
                {estimate.secondary_evidence?.sources?.length ?? 0} cited sources · {estimate.secondary_evidence?.valuation_candidate_count ?? 0} usable sale candidate(s)
              </small>
            </div>
            <div>
              <span>Supporting market context</span>
              <strong>
                {(estimate.supporting_evidence?.status ?? "unavailable").replaceAll("_", " ")}
              </strong>
              <small>
                {estimate.supporting_evidence?.sale_listings.length ?? 0} active listing(s) · ZIP {estimate.supporting_evidence?.market_context?.zip_code ?? "--"}
              </small>
            </div>
          </div>

          {estimate.comp_intelligence ? (
            <CompIntelligencePanel intelligence={estimate.comp_intelligence} />
          ) : null}

          {estimate.comp_search_summary ? (
            <details className={styles.evidenceDetails}>
              <summary>
                Closed-sale search: {estimate.comp_search_summary.sufficient_closed_sales
                  ? "evidence threshold met"
                  : "more evidence needed"}
              </summary>
              <div className={styles.confidenceFactors}>
                {estimate.comp_search_summary.attempts.map((attempt, index) => (
                  <div key={`${attempt.level}-${index}`}>
                    <span>{attempt.level.replaceAll("_", " ")} level</span>
                    <strong>
                      {attempt.level === "manual"
                        ? "Manual evidence"
                        : `${attempt.radius_miles ?? "--"} mi / ${attempt.days_old ?? "--"} days`}
                    </strong>
                    <small>
                      {attempt.returned_count} returned · {attempt.unique_added_count} new ·{" "}
                      {attempt.duplicate_count} duplicate · {attempt.selected_count} usable
                    </small>
                    {attempt.level !== "manual" ? (
                      <small>
                        Sqft +/- {attempt.square_footage_tolerance_percentage ?? "--"}% · age
                        +/- {attempt.year_built_tolerance_years ?? "--"} yr · beds +/-{" "}
                        {attempt.bedroom_tolerance ?? "--"} · baths +/-{" "}
                        {attempt.bathroom_tolerance ?? "--"}
                      </small>
                    ) : null}
                    {attempt.expansion_reason ? <small>{attempt.expansion_reason}</small> : null}
                    {attempt.provider_error ? <small>{attempt.provider_error}</small> : null}
                  </div>
                ))}
              </div>
              <div className={styles.secondaryEvidence}>
                {estimate.comp_search_summary.subject_subdivision ? (
                  <p>
                    Subject subdivision: {estimate.comp_search_summary.subject_subdivision}.{" "}
                    {estimate.comp_search_summary.same_subdivision_count} selected sale(s)
                    matched it.
                  </p>
                ) : null}
                {estimate.comp_search_summary.market_area_warning ? (
                  <small>{estimate.comp_search_summary.market_area_warning}</small>
                ) : null}
                {estimate.comp_search_summary.evidence_shortage_reason ? (
                  <small>{estimate.comp_search_summary.evidence_shortage_reason}</small>
                ) : null}
                {estimate.comp_search_summary.next_action ? (
                  <p><strong>Next action:</strong> {estimate.comp_search_summary.next_action}</p>
                ) : null}
              </div>
            </details>
          ) : null}

          {estimate.supporting_evidence ? (
            <details className={styles.evidenceDetails}>
              <summary>Supporting listings and ZIP market context</summary>
              <div className={styles.supportingMarketContext}>
                <div className={styles.supportingMarketMetrics}>
                  <div>
                    <span>Median asking price</span>
                    <strong>
                      {formatMoney(
                        estimate.supporting_evidence.market_context?.median_list_price_cents,
                      )}
                    </strong>
                  </div>
                  <div>
                    <span>Median asking price / sqft</span>
                    <strong>
                      {formatMoney(
                        estimate.supporting_evidence.market_context
                          ?.median_price_per_square_foot_cents,
                      )}
                    </strong>
                  </div>
                  <div>
                    <span>Average days on market</span>
                    <strong>
                      {estimate.supporting_evidence.market_context?.average_days_on_market ?? "--"}
                    </strong>
                  </div>
                  <div>
                    <span>Observed listings</span>
                    <strong>
                      {estimate.supporting_evidence.market_context?.total_listings ?? "--"}
                    </strong>
                  </div>
                </div>
                {estimate.supporting_evidence.sale_listings.length ? (
                  <div className={styles.supportingListingList}>
                    {estimate.supporting_evidence.sale_listings.map((listing, index) => (
                      <article key={listing.provider_id ?? `${listing.formatted_address}-${index}`}>
                        <div>
                          <strong>{listing.formatted_address ?? "Unknown address"}</strong>
                          <span>{formatMoney(listing.asking_price_cents)}</span>
                        </div>
                        <small>
                          {listing.status} asking price · {formatNumber(listing.square_footage)} sqft · {listing.days_on_market ?? "--"} days on market
                        </small>
                      </article>
                    ))}
                  </div>
                ) : null}
                <small>
                  Active listings and ZIP statistics are context only. They are never treated as closed sales or used directly in ARV or offer math.
                </small>
                {estimate.supporting_evidence.errors.length ? (
                  <small>{estimate.supporting_evidence.errors.join(" ")}</small>
                ) : null}
              </div>
            </details>
          ) : null}

          {estimate.confidence_factors?.length ? (
            <details className={styles.evidenceDetails}>
              <summary>Why this confidence score</summary>
              <div className={styles.confidenceFactors}>
                {estimate.confidence_factors.map((factor) => (
                  <div key={factor.key}>
                    <span>{factor.label}</span>
                    <strong>
                      {factor.score}/{factor.maximum}
                    </strong>
                    <small>{factor.summary}</small>
                  </div>
                ))}
              </div>
            </details>
          ) : null}

          {estimate.secondary_evidence?.status === "completed" ||
          estimate.secondary_evidence?.status === "insufficient" ? (
            <details className={styles.evidenceDetails}>
              <summary>Secondary public evidence</summary>
              <div className={styles.secondaryEvidence}>
                <p>{estimate.secondary_evidence.summary}</p>
                {estimate.secondary_evidence.facts?.map((fact, index) => (
                  <article key={`${fact.source_url}-${index}`}>
                    <div>
                      <span>{fact.fact_type.replaceAll("_", " ")}</span>
                      <strong>{fact.value}</strong>
                    </div>
                    <a href={fact.source_url} rel="noreferrer" target="_blank">
                      {fact.source_title}
                    </a>
                  </article>
                ))}
                {estimate.secondary_evidence.conflicts?.map((conflict, index) => (
                  <article
                    className={styles.evidenceConflict}
                    key={`${conflict.source_url}-${conflict.field}-${index}`}
                  >
                    <div>
                      <span>Conflict: {conflict.field.replaceAll("_", " ")}</span>
                      <strong>{conflict.explanation}</strong>
                      <small>
                        Provider: {conflict.primary_value} · Public source: {conflict.web_value}
                      </small>
                    </div>
                    <a href={conflict.source_url} rel="noreferrer" target="_blank">
                      Review source
                    </a>
                  </article>
                ))}
                {estimate.secondary_evidence.comparable_candidates?.length ? (
                  <div className={styles.evidenceSources}>
                    <span>AI-discovered closed sales</span>
                    {estimate.secondary_evidence.comparable_candidates.map((candidate) => (
                      <article key={`${candidate.formatted_address}-${candidate.sale_date}`}>
                        <div>
                          <strong>{candidate.formatted_address}</strong>
                          <small>
                            {formatMoney(Math.round(candidate.sale_price_dollars * 100))} · sold {candidate.sale_date} · {candidate.source_grade.replaceAll("_", " ")}
                          </small>
                        </div>
                        {candidate.source_urls?.[0] ? (
                          <a href={candidate.source_urls[0]} rel="noreferrer" target="_blank">
                            Review sale source
                          </a>
                        ) : null}
                      </article>
                    ))}
                  </div>
                ) : null}
                {estimate.secondary_evidence.sources?.length ? (
                  <div className={styles.evidenceSources}>
                    <span>Sources consulted</span>
                    {estimate.secondary_evidence.sources.map((source) => (
                      <a href={source.url} key={source.url} rel="noreferrer" target="_blank">
                        {source.title}
                      </a>
                    ))}
                  </div>
                ) : null}
                {estimate.secondary_evidence.limitations?.length ? (
                  <small>{estimate.secondary_evidence.limitations.join(" ")}</small>
                ) : null}
              </div>
            </details>
          ) : null}

          <dl className={styles.decisionMetrics}>
            {!providerControlsAsIs ? (
              <div>
                <dt>Closed-sale as-is estimate</dt>
                <dd>{formatMoney(estimate.as_is_value_cents)}</dd>
                <small>
                  {formatMoney(estimate.as_is_value_low_cents)} to{" "}
                  {formatMoney(estimate.as_is_value_high_cents)}
                </small>
              </div>
            ) : null}
            <div>
              <dt>
                {hasVerifiedArv
                  ? "Conservative ARV"
                  : isWorkingGuidance
                    ? "Working ARV"
                    : "Preliminary ARV"}
              </dt>
              <dd>{formatMoney(estimate.conservative_arv_cents)}</dd>
              <small>
                {!hasSupportedArv
                  ? "No usable recorded-sale evidence"
                  : `${hasVerifiedArv ? "Comp-supported" : isWorkingGuidance ? "Working" : "Preliminary"} range ${formatMoney(
                      estimate.arv_low_cents,
                    )} to ${formatMoney(estimate.arv_high_cents)}`}
              </small>
            </div>
            <div>
              <dt>Total rehab</dt>
              <dd>{formatMoney(estimate.total_rehab_cents)}</dd>
              <small>
                Base {formatMoney(estimate.base_rehab_cents)} +{" "}
                {estimate.rehab_contingency_percentage ?? 0}% contingency
              </small>
            </div>
            <div>
              <dt>Best buyer maximum</dt>
              <dd>{formatMoney(estimate.recommended_disposition_cents)}</dd>
              <small>
                Flip {formatMoney(estimate.flip_buyer_max_cents)} / rental{" "}
                {formatMoney(estimate.rental_buyer_max_cents)}
              </small>
            </div>
            <div>
              <dt>Seller contract ceiling</dt>
              <dd>{formatMoney(estimate.seller_contract_ceiling_cents)}</dd>
              <small>
                {hasVerifiedArv
                  ? "Do not exceed without re-underwriting"
                  : isWorkingGuidance
                    ? "Working limit; verify another sale before approval"
                    : "Preliminary until comp condition is reviewed"}
              </small>
            </div>
            <div className={styles.primaryMetric}>
              <dt>Opening recommendation</dt>
              <dd>{formatMoney(estimate.recommended_offer_cents)}</dd>
              <small>Negotiation starting point, not an approved offer</small>
            </div>
          </dl>

          {activeRepairScenario ? (
            <div className={styles.repairScenarioResult}>
              <div>
                <span>Repair range</span>
                <strong>
                  {formatMoney(activeRepairScenario.total_low_cents)} to{" "}
                  {formatMoney(activeRepairScenario.total_high_cents)}
                </strong>
                <small>
                  {formatMoney(activeRepairScenario.total_expected_cents)} expected ·{" "}
                  {activeRepairScenario.version ?? "catalog version unavailable"}
                </small>
              </div>
              <div>
                <span>Unconfirmed work</span>
                <strong>
                  {formatMoney(activeRepairScenario.unknown_reserve_cents)} reserved
                </strong>
                <small>
                  {activeRepairScenario.unknown_item_count ?? 0} unknown ·{" "}
                  {activeRepairScenario.specialist_item_count ?? 0} specialist review
                </small>
              </div>
              {activeRepairScenario.warnings?.length ? (
                <ul>
                  {activeRepairScenario.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          <div className={styles.underwritingControls}>
            <div>
              <span>Report stage</span>
              <strong>{reportStageLabel(estimate.report_stage)}</strong>
            </div>
            <div>
              <span>Repair source</span>
              <strong>
                {repairSourceLabel(estimate.pre_meeting_inputs?.repair_estimate_source)}
              </strong>
            </div>
            <div>
              <span>Holding period</span>
              <strong>
                {estimate.pre_meeting_inputs?.holding_period_months ?? 6} months
              </strong>
            </div>
            <div>
              <span>Monthly rent support</span>
              <strong>{formatMoney(estimate.monthly_rent_cents)}</strong>
            </div>
            <div>
              <span>Transaction reserve</span>
              <strong>{formatMoney(estimate.transaction_reserve_cents)}</strong>
            </div>
          </div>

          <ExternalBenchmarkPanel benchmarks={externalBenchmarks} />

          {reviewItems.length ? (
            <div className={styles.reviewReasons}>
              <strong>Resolve before approval</strong>
              <ul>
                {reviewItems.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className={styles.reportActions} id="valuation-reports">
            <span>Saved report</span>
            <button
              className={styles.secondaryButton}
              disabled={reportLoading !== null}
              onClick={() => openReport("investor")}
              type="button"
            >
              {reportLoading === "investor" ? "Building..." : "Investor PDF"}
            </button>
            <button
              className={styles.secondaryButton}
              disabled={reportLoading !== null}
              onClick={() => openReport("client")}
              type="button"
            >
              {reportLoading === "client" ? "Building..." : "Client PDF"}
            </button>
          </div>

          {estimate.id ? <CalibrationOutcomeForm analysisId={estimate.id} /> : null}

          {estimate.id ? (
            <CompCopilotPanel
              analysisId={estimate.id}
              apiBaseUrl={apiBaseUrl}
              getHeaders={getHeaders}
              leadId={leadId}
              onSuggestedAction={handleCopilotAction}
            />
          ) : null}

          {aiCompAnalyst ? <AiCompAnalystPanel envelope={aiCompAnalyst} /> : null}

          <ComparableReviewWorkbench
            adjustedIndications={adjustedIndications}
            analystRecommendations={analystRecommendations}
            comparables={reviewComps}
            conditionOverrides={conditionOverrides}
            disabled={isLoading}
            focusRequest={copilotFocus}
            key={`comp-review-${copilotFocus?.nonce ?? 0}`}
            onApply={applyCompReview}
            onConditionChange={updateCompCondition}
            onRestoreRecommendation={restoreSystemCompSet}
            onReviewChange={updateCompReview}
            requestedAddress={estimate.requested_address}
            review={compReview}
            saving={reviewSaving}
            subject={{
              ...estimate.subject_property,
              squareFootage:
                estimate.subject_property?.squareFootage ?? estimate.subject_square_feet,
            }}
          />
          <p>{estimate.source_note}</p>
        </div>
      ) : null}
    </section>
  );
}
