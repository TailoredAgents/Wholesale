"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { CalibrationOutcomeForm } from "./calibration-outcome-form";
import {
  RepairEstimate,
  RepairEstimateControl,
  RepairEstimateItem,
} from "./repair-estimate-control";
import styles from "./page.module.css";

type CompCondition = "unknown" | "as_is" | "renovated";
type RepairEntryMode = "system" | "total" | "itemized";
type VerificationStatus =
  | "preliminary"
  | "pre_meeting_reviewed"
  | "walkthrough_verified";
type RepairCategory =
  | "roof"
  | "hvac"
  | "plumbing"
  | "electrical"
  | "foundation"
  | "kitchen"
  | "bathrooms"
  | "flooring"
  | "paint_drywall"
  | "windows_doors"
  | "exterior"
  | "landscaping"
  | "permits"
  | "cleanup"
  | "other";

type RepairItem = {
  category: RepairCategory;
  estimated_cost_cents: number;
  details?: string | null;
};

type PreMeetingInputs = {
  verification_status: VerificationStatus;
  report_stage: VerificationStatus;
  current_condition: string | null;
  target_condition: string;
  repair_level: string;
  repair_estimate_source: string;
  base_rehab_override_cents: number | null;
  repair_items: RepairItem[];
  contingency_override_percentage: number | null;
  holding_period_months: number;
  repair_notes: string | null;
  custom_inputs_applied: boolean;
  repair_estimate_id?: string | null;
  repair_estimate_contractor_name?: string | null;
  repair_estimate_date?: string | null;
  repair_estimate_reference?: string | null;
};

type MarketComparable = {
  provider_id: string | null;
  formatted_address: string | null;
  status: string | null;
  property_type: string | null;
  price_cents: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  square_footage: number | null;
  year_built: number | null;
  distance_miles: number | null;
  days_old: number | null;
  sale_date?: string | null;
  price_source?: string | null;
  verification_status?: string | null;
  condition_classification?: CompCondition | null;
  adjusted_value_cents?: number | null;
  price_per_square_foot_cents?: number | null;
  weight?: number | null;
  selection_status?: string;
  selection_reason?: string;
  score?: number;
  review_decision?: "included" | "excluded" | null;
  review_reason?: string | null;
  manual_weight_percentage?: number | null;
};

type CompReviewDraft = {
  included: boolean;
  reason: string;
  weight_percentage: number;
};

type MarketValueEstimate = {
  id?: string;
  provider: string;
  requested_address: string;
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
  flip_buyer_max_cents?: number | null;
  rental_buyer_max_cents?: number | null;
  recommended_disposition_cents?: number | null;
  seller_contract_ceiling_cents?: number | null;
  transaction_reserve_cents?: number | null;
  recommended_offer_cents?: number | null;
  monthly_rent_cents?: number | null;
  confidence_score?: number;
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
  source_note: string;
};

type Status = "idle" | "loading" | "loaded" | "error";
type ReportAudience = "investor" | "client";

const REPAIR_CATEGORIES: { key: RepairCategory; label: string }[] = [
  { key: "roof", label: "Roof" },
  { key: "hvac", label: "HVAC" },
  { key: "plumbing", label: "Plumbing" },
  { key: "electrical", label: "Electrical" },
  { key: "foundation", label: "Foundation" },
  { key: "kitchen", label: "Kitchen" },
  { key: "bathrooms", label: "Bathrooms" },
  { key: "flooring", label: "Flooring" },
  { key: "paint_drywall", label: "Paint / drywall" },
  { key: "windows_doors", label: "Windows / doors" },
  { key: "exterior", label: "Exterior" },
  { key: "landscaping", label: "Landscaping" },
  { key: "permits", label: "Permits" },
  { key: "cleanup", label: "Cleanup" },
  { key: "other", label: "Other" },
];

const REPAIR_PRESET_WEIGHTS: Record<
  string,
  Partial<Record<RepairCategory, number>>
> = {
  light: {
    kitchen: 20,
    bathrooms: 15,
    flooring: 20,
    paint_drywall: 25,
    windows_doors: 5,
    exterior: 8,
    landscaping: 3,
    cleanup: 4,
  },
  moderate: {
    roof: 10,
    hvac: 8,
    plumbing: 5,
    electrical: 5,
    kitchen: 22,
    bathrooms: 16,
    flooring: 12,
    paint_drywall: 10,
    windows_doors: 4,
    exterior: 4,
    permits: 2,
    cleanup: 2,
  },
  heavy: {
    roof: 10,
    hvac: 9,
    plumbing: 9,
    electrical: 9,
    foundation: 12,
    kitchen: 16,
    bathrooms: 12,
    flooring: 6,
    paint_drywall: 5,
    windows_doors: 4,
    exterior: 4,
    permits: 2,
    cleanup: 2,
  },
  structural: {
    roof: 10,
    hvac: 8,
    plumbing: 10,
    electrical: 10,
    foundation: 22,
    kitchen: 12,
    bathrooms: 8,
    flooring: 4,
    paint_drywall: 4,
    windows_doors: 4,
    exterior: 4,
    permits: 2,
    cleanup: 2,
  },
};

const REPAIR_CONTINGENCY: Record<string, number> = {
  light: 10,
  moderate: 15,
  heavy: 20,
  structural: 25,
};

const INCLUDED_REASONS = [
  "Strong subject match",
  "Best available nearby sale",
  "Verified renovated sale",
  "Verified as-is sale",
  "Condition-adjusted match",
];

const EXCLUDED_REASONS = [
  "Different condition",
  "Location not comparable",
  "Size or design mismatch",
  "Sale too old",
  "Price outlier",
  "Data quality concern",
];

function emptyRepairAmounts() {
  return Object.fromEntries(
    REPAIR_CATEGORIES.map(({ key }) => [key, ""]),
  ) as Record<RepairCategory, string>;
}

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

function formatDate(value: string | null | undefined) {
  if (!value) {
    return "Date unavailable";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf())
    ? value
    : new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      }).format(parsed);
}

function conditionLabel(value: CompCondition) {
  if (value === "as_is") {
    return "As-is at sale";
  }
  if (value === "renovated") {
    return "Renovated at sale";
  }
  return "Not verified";
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
  const [repairAmounts, setRepairAmounts] =
    useState<Record<RepairCategory, string>>(emptyRepairAmounts);
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
            (included ? INCLUDED_REASONS[0] : EXCLUDED_REASONS[0]),
          weight_percentage: comp.manual_weight_percentage ?? 100,
        };
      }
    }
    setConditionOverrides(nextOverrides);
    setCompReview(nextReview);
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
      if (inputs.repair_estimate_id || inputs.repair_estimate_source === "itemized") {
        setRepairEntryMode("itemized");
        const nextAmounts = emptyRepairAmounts();
        for (const item of inputs.repair_items) {
          nextAmounts[item.category] = String(item.estimated_cost_cents / 100);
        }
        setRepairAmounts(nextAmounts);
        setBaseRehabInput("");
      } else if (inputs.repair_estimate_source === "user_total") {
        setRepairEntryMode("total");
        setBaseRehabInput(
          inputs.base_rehab_override_cents === null
            ? ""
            : String(inputs.base_rehab_override_cents / 100),
        );
        setRepairAmounts(emptyRepairAmounts());
      } else {
        setRepairEntryMode("system");
        setBaseRehabInput("");
        setRepairAmounts(emptyRepairAmounts());
      }
    } else {
      setContingencyInput("");
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
    const nextAmounts = emptyRepairAmounts();
    for (const item of repairEstimate.scope_items) {
      if (item.category in nextAmounts) {
        const category = item.category as RepairCategory;
        const currentCents = dollarsToCents(nextAmounts[category]) ?? 0;
        nextAmounts[category] = String(
          (currentCents + item.estimated_cost_cents) / 100,
        );
      }
    }
    setRepairEntryMode("itemized");
    setRepairAmounts(nextAmounts);
    setContingencyInput(String(repairEstimate.contingency_percentage));
    setRepairNotes(repairEstimate.notes ?? "");
    setSelectedRepairEstimateId(repairEstimate.id);
    setSelectedRepairEstimateSource(repairEstimate.source_type);
    markInputsReviewed();
  }

  function applyRepairPreset() {
    const baseCents = estimate?.base_rehab_cents;
    if (!baseCents || baseCents <= 0) {
      setError("Run the system analysis once before building an itemized preset.");
      return;
    }
    const weights = REPAIR_PRESET_WEIGHTS[repairLevel] ?? REPAIR_PRESET_WEIGHTS.moderate;
    const nextAmounts = emptyRepairAmounts();
    for (const [category, percentage] of Object.entries(weights)) {
      const roundedCents = Math.round((baseCents * percentage) / 10000) * 100;
      nextAmounts[category as RepairCategory] = String(roundedCents / 100);
    }
    setRepairAmounts(nextAmounts);
    setRepairEntryMode("itemized");
    setContingencyInput(String(REPAIR_CONTINGENCY[repairLevel] ?? 15));
    detachSavedRepairEstimate();
    markInputsReviewed();
    setError(null);
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
    const repairItems =
      repairEntryMode === "itemized" && !usingSavedEstimate
        ? REPAIR_CATEGORIES.flatMap(({ key }) => {
            const estimatedCostCents = dollarsToCents(repairAmounts[key]);
            return estimatedCostCents && estimatedCostCents > 0
              ? [{ category: key, estimated_cost_cents: estimatedCostCents }]
              : [];
          })
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
      repairItems.length === 0 &&
      !usingSavedEstimate
    ) {
      throw new Error("Enter at least one itemized repair cost.");
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
      repair_items: repairItems,
      repair_estimate_id: selectedRepairEstimateId,
      contingency_override_percentage: usingSavedEstimate ? null : contingencyPercentage,
      holding_period_months: 6,
      repair_notes: repairNotes.trim() || null,
      comp_condition_overrides: conditionOverrides,
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
  const reviewIncludedCount = Object.values(compReview).filter(
    (decision) => decision.included,
  ).length;
  const reviewItems = [
    ...(estimate?.review_reasons ?? []),
    ...(estimate?.data_disagreements ?? []),
  ];
  const itemizedBaseCents = REPAIR_CATEGORIES.reduce(
    (total, { key }) => total + (dollarsToCents(repairAmounts[key]) ?? 0),
    0,
  );
  const currentRepairItems: RepairEstimateItem[] = REPAIR_CATEGORIES.flatMap(
    ({ key }) => {
      const estimatedCostCents = dollarsToCents(repairAmounts[key]);
      return estimatedCostCents && estimatedCostCents > 0
        ? [{ category: key, estimated_cost_cents: estimatedCostCents }]
        : [];
    },
  );
  const isLoading = status === "loading";
  const isV2 = estimate?.methodology_version === "v2.1";
  const hasSupportedArv = typeof estimate?.arv_point_cents === "number";
  const hasVerifiedArv =
    estimate?.assumptions?.arv_value_basis === "verified_renovated_recorded_sales";
  const activeReportStage = estimate?.report_stage ?? verificationStatus;
  const activeRepairSource =
    selectedRepairEstimateSource ??
    (repairEntryMode === "itemized"
      ? "itemized"
      : repairEntryMode === "total"
        ? "user_total"
        : "system_estimate");

  return (
    <section className={styles.marketValuePanel}>
      <div className={styles.marketValueHeader}>
        <div>
          <span className={styles.underwritingEyebrow}>Underwriting V2.1</span>
          <strong>Recorded sales and buyer economics</strong>
          <span>Human-reviewed evidence for ARV, repairs, and seller negotiation limits</span>
        </div>
        <div className={styles.marketValueActions}>
          {estimate ? (
            <button
              className={styles.secondaryButton}
              disabled={isLoading}
              onClick={() => createAnalysis(true)}
              type="button"
            >
              Refresh market data
            </button>
          ) : null}
          <button disabled={isLoading} onClick={() => createAnalysis(false)} type="button">
            {isLoading ? "Calculating..." : estimate ? "Recalculate" : "Run analysis"}
          </button>
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
            <div className={styles.itemizedScope}>
              <div className={styles.repairPresetBar}>
                <div>
                  <strong>{repairLevel.replaceAll("_", " ")} scope preset</strong>
                  <span>
                    Allocates the saved system base across common work categories.
                  </span>
                </div>
                <button disabled={!estimate?.base_rehab_cents} onClick={applyRepairPreset} type="button">
                  Apply preset
                </button>
              </div>
              <div className={styles.itemizedRepairs}>
                {REPAIR_CATEGORIES.map(({ key, label }) => (
                  <label key={key}>
                    <span>{label}</span>
                    <div className={styles.moneyInput}>
                      <span>$</span>
                      <input
                        aria-label={`${label} estimated cost`}
                        inputMode="decimal"
                        min="0"
                        onChange={(event) => {
                          setRepairAmounts((current) => ({
                            ...current,
                            [key]: event.target.value,
                          }));
                          detachSavedRepairEstimate();
                          markInputsReviewed();
                        }}
                        placeholder="0"
                        step="500"
                        type="number"
                        value={repairAmounts[key]}
                      />
                    </div>
                  </label>
                ))}
                <div className={styles.itemizedTotal}>
                  <span>Itemized base</span>
                  <strong>{formatMoney(itemizedBaseCents)}</strong>
                </div>
              </div>
            </div>
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

      {estimate ? (
        <div className={styles.marketValueResult}>
          {!isV2 ? (
            <div className={styles.reviewBanner}>
              This saved analysis uses the prior method. Recalculate to create a V2.1 analysis.
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
              {estimate.confidence_score ?? 0}% confidence. A person must still approve the
              acquisition decision.
            </span>
          </div>

          <dl className={styles.decisionMetrics}>
            <div>
              <dt>As-is benchmark</dt>
              <dd>{formatMoney(estimate.as_is_value_cents)}</dd>
              <small>
                {formatMoney(estimate.as_is_value_low_cents)} to{" "}
                {formatMoney(estimate.as_is_value_high_cents)}
              </small>
            </div>
            <div>
              <dt>{hasVerifiedArv ? "Conservative ARV" : "Preliminary ARV"}</dt>
              <dd>{formatMoney(estimate.conservative_arv_cents)}</dd>
              <small>
                {!hasSupportedArv
                  ? "No usable recorded-sale evidence"
                  : `${hasVerifiedArv ? "Comp-supported" : "Preliminary"} range ${formatMoney(
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
                  : "Preliminary until comp condition is reviewed"}
              </small>
            </div>
            <div className={styles.primaryMetric}>
              <dt>Opening recommendation</dt>
              <dd>{formatMoney(estimate.recommended_offer_cents)}</dd>
              <small>Negotiation starting point, not an approved offer</small>
            </div>
          </dl>

          {!hasVerifiedArv ? (
            <div className={styles.underwritingControls}>
              <div>
                <span>ARV status</span>
                <strong>{hasSupportedArv ? "Preliminary" : "Unavailable"}</strong>
              </div>
              <div>
                <span>Provider AVM screen</span>
                <strong>
                  {formatMoney(estimate.estimated_value_low_cents)} to{" "}
                  {formatMoney(estimate.estimated_value_high_cents)}
                </strong>
              </div>
              <div>
                <span>AVM use in offer math</span>
                <strong>No</strong>
              </div>
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

          <div className={styles.reportActions}>
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

          <div className={styles.compSectionHeader}>
            <div>
              <strong>Comparable review</strong>
              <span>Recorded sales, condition evidence, and reviewer judgment</span>
            </div>
            <span>
              {reviewIncludedCount} included / {reviewComps.length - reviewIncludedCount}{" "}
              excluded
            </span>
          </div>
          <div className={styles.compList}>
            {reviewComps.map((comp, index) => {
              const compKey = comp.provider_id ?? comp.formatted_address ?? `comp-${index}`;
              const condition = conditionOverrides[compKey] ?? "unknown";
              const decision = compReview[compKey] ?? {
                included: comp.selection_status !== "rejected",
                reason:
                  comp.selection_status === "rejected"
                    ? EXCLUDED_REASONS[0]
                    : INCLUDED_REASONS[0],
                weight_percentage: 100,
              };
              const reasonOptions = decision.included ? INCLUDED_REASONS : EXCLUDED_REASONS;
              return (
                <article
                  className={decision.included ? styles.compIncluded : styles.compExcluded}
                  key={compKey}
                >
                  <div>
                    <div className={styles.compIdentity}>
                      <input
                        aria-label={`${decision.included ? "Exclude" : "Include"} ${
                          comp.formatted_address ?? "comparable"
                        }`}
                        checked={decision.included}
                        onChange={(event) => {
                          const included = event.target.checked;
                          setCompReview((current) => ({
                            ...current,
                            [compKey]: {
                              ...decision,
                              included,
                              reason: included ? INCLUDED_REASONS[0] : EXCLUDED_REASONS[0],
                            },
                          }));
                          markInputsReviewed();
                        }}
                        type="checkbox"
                      />
                      <strong>{comp.formatted_address ?? "Unknown address"}</strong>
                      <span className={styles.compDecisionBadge}>
                        {decision.included ? "Included" : "Excluded"}
                      </span>
                    </div>
                    <span>{formatMoney(comp.price_cents)}</span>
                  </div>
                  <small>
                    Recorded {formatDate(comp.sale_date)} / {comp.distance_miles ?? "?"} mi /{" "}
                    {formatNumber(comp.square_footage)} sqft / {comp.bedrooms ?? "?"} bd{" "}
                    {comp.bathrooms ?? "?"} ba
                  </small>
                  <small>
                    {formatMoney(comp.price_per_square_foot_cents)} per sqft / Subject-size
                    indicator {formatMoney(comp.adjusted_value_cents)}
                  </small>
                  <small>
                    Match score {comp.score ?? "?"}/100. {comp.selection_reason}
                  </small>
                  <div className={styles.compReviewControls}>
                    <label>
                      <span>Condition at sale</span>
                      <select
                        aria-label={`Condition at sale for ${comp.formatted_address ?? "comparable"}`}
                        onChange={(event) => {
                          setConditionOverrides((current) => ({
                            ...current,
                            [compKey]: event.target.value as CompCondition,
                          }));
                          markInputsReviewed();
                        }}
                        value={condition}
                      >
                        {(["unknown", "as_is", "renovated"] as CompCondition[]).map(
                          (value) => (
                            <option key={value} value={value}>
                              {conditionLabel(value)}
                            </option>
                          ),
                        )}
                      </select>
                    </label>
                    <label>
                      <span>Decision reason</span>
                      <select
                        aria-label={`Decision reason for ${comp.formatted_address ?? "comparable"}`}
                        onChange={(event) => {
                          setCompReview((current) => ({
                            ...current,
                            [compKey]: { ...decision, reason: event.target.value },
                          }));
                          markInputsReviewed();
                        }}
                        value={decision.reason}
                      >
                        {!reasonOptions.includes(decision.reason) ? (
                          <option value={decision.reason}>{decision.reason}</option>
                        ) : null}
                        {reasonOptions.map((reason) => (
                          <option key={reason} value={reason}>
                            {reason}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Evidence weight</span>
                      <div className={styles.weightInput}>
                        <input
                          aria-label={`Evidence weight for ${comp.formatted_address ?? "comparable"}`}
                          disabled={!decision.included}
                          max="150"
                          min="50"
                          onChange={(event) => {
                            setCompReview((current) => ({
                              ...current,
                              [compKey]: {
                                ...decision,
                                weight_percentage: Number(event.target.value),
                              },
                            }));
                            markInputsReviewed();
                          }}
                          step="5"
                          type="number"
                          value={decision.weight_percentage}
                        />
                        <span>%</span>
                      </div>
                    </label>
                  </div>
                </article>
              );
            })}
          </div>
          <div className={styles.compReviewFooter}>
            <div>
              <strong>Review version</strong>
              <span>Applying creates a new saved analysis and keeps this version unchanged.</span>
            </div>
            <button
              disabled={reviewSaving || isLoading || !reviewComps.length}
              onClick={applyCompReview}
              type="button"
            >
              {reviewSaving ? "Applying..." : "Apply review and recalculate"}
            </button>
          </div>
          <p>{estimate.source_note}</p>
        </div>
      ) : null}
    </section>
  );
}
