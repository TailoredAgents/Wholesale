"use client";

import {
  Check,
  ExternalLink,
  List,
  MapPinned,
  RotateCcw,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";

import styles from "./page.module.css";

export type CompCondition = "unknown" | "as_is" | "renovated";

export type MarketComparable = {
  provider_id: string | null;
  formatted_address: string | null;
  status: string | null;
  property_type: string | null;
  price_cents: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  square_footage: number | null;
  year_built: number | null;
  lot_size?: number | null;
  distance_miles: number | null;
  latitude?: number | null;
  longitude?: number | null;
  direction_from_subject?: string | null;
  days_old: number | null;
  sale_date?: string | null;
  price_source?: string | null;
  verification_status?: string | null;
  condition_classification?: CompCondition | null;
  condition_evidence?: string | null;
  adjusted_value_cents?: number | null;
  price_per_square_foot_cents?: number | null;
  weight?: number | null;
  selection_status?: string;
  selection_reason?: string;
  score?: number;
  engine_selection_status?: "selected" | "rejected" | null;
  engine_selection_reason?: string | null;
  review_decision?: "included" | "excluded" | null;
  review_reason?: string | null;
  manual_weight_percentage?: number | null;
  subdivision?: string | null;
  subdivision_match?: boolean | null;
  search_level?: "preferred" | "expanded" | "extended" | "manual" | null;
  comp_grade?: "A" | "B" | "C" | "D" | null;
  search_warnings?: string[];
  evidence_source?: string | null;
  source_reference?: string | null;
  source_url?: string | null;
  verification_notes?: string | null;
  source_providers?: string[];
  corroborating_sources?: string[];
  corroborated?: boolean | null;
  source_overlap_count?: number | null;
  field_conflicts?: Array<{
    field: string;
    selected_value?: unknown;
    material?: boolean;
    severity?: "info" | "review" | "high";
    summary?: string;
    observations?: Array<{
      provider?: string;
      value?: unknown;
    }>;
  }>;
  source_conflicts?: Array<
    | string
    | {
        field?: string | null;
        summary?: string | null;
        explanation?: string | null;
        material?: boolean | null;
        severity?: "info" | "review" | "high" | null;
      }
  >;
};

export type CompAnalystRecommendation = {
  recommendation: "include" | "exclude" | "review";
  reason: string;
  confidence?: number | null;
  condition_hypothesis?: CompCondition | "mixed" | null;
};

export type CompReviewDraft = {
  included: boolean;
  reason: string;
  weight_percentage: number;
};

export type SubjectProperty = {
  formattedAddress?: string | null;
  propertyType?: string | null;
  bedrooms?: number | null;
  bathrooms?: number | null;
  squareFootage?: number | null;
  yearBuilt?: number | null;
  lotSize?: number | null;
  subdivision?: string | null;
  latitude?: number | null;
  longitude?: number | null;
};

export const COMPARABLE_INCLUDED_REASONS = [
  "Strong subject match",
  "Best available nearby sale",
  "Verified renovated sale",
  "Verified as-is sale",
  "Condition-adjusted match",
];

export const COMPARABLE_EXCLUDED_REASONS = [
  "Different condition",
  "Location not comparable",
  "Size or design mismatch",
  "Sale too old",
  "Price outlier",
  "Data quality concern",
];

type ReviewFilter = "all" | "included" | "excluded";
type ReviewView = "compare" | "location";
type ReviewSort = "fit" | "distance" | "recent" | "value";

type ComparableReviewWorkbenchProps = {
  adjustedIndications?: Record<string, number | null | undefined>;
  analystRecommendations?: Record<string, CompAnalystRecommendation>;
  comparables: MarketComparable[];
  conditionOverrides: Record<string, CompCondition>;
  disabled: boolean;
  onApply: () => void;
  onConditionChange: (compKey: string, condition: CompCondition) => void;
  onRestoreRecommendation: () => void;
  onReviewChange: (compKey: string, decision: CompReviewDraft) => void;
  requestedAddress: string;
  review: Record<string, CompReviewDraft>;
  saving: boolean;
  subject: SubjectProperty;
};

export function ComparableReviewWorkbench({
  adjustedIndications = {},
  analystRecommendations = {},
  comparables,
  conditionOverrides,
  disabled,
  onApply,
  onConditionChange,
  onRestoreRecommendation,
  onReviewChange,
  requestedAddress,
  review,
  saving,
  subject,
}: ComparableReviewWorkbenchProps) {
  const [query, setQuery] = useState("");
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("all");
  const [gradeFilter, setGradeFilter] = useState("all");
  const [levelFilter, setLevelFilter] = useState("all");
  const [sort, setSort] = useState<ReviewSort>("fit");
  const [view, setView] = useState<ReviewView>("compare");

  const filteredComparables = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return comparables
      .filter((comp, index) => {
        const decision = reviewDraftFor(review, comp, index);
        if (reviewFilter === "included" && !decision.included) {
          return false;
        }
        if (reviewFilter === "excluded" && decision.included) {
          return false;
        }
        if (gradeFilter !== "all" && comp.comp_grade !== gradeFilter) {
          return false;
        }
        if (levelFilter !== "all" && comp.search_level !== levelFilter) {
          return false;
        }
        if (
          normalizedQuery &&
          !`${comp.formatted_address ?? ""} ${comp.subdivision ?? ""}`
            .toLowerCase()
            .includes(normalizedQuery)
        ) {
          return false;
        }
        return true;
      })
      .sort((left, right) => compareComps(left, right, sort, adjustedIndications));
  }, [adjustedIndications, comparables, gradeFilter, levelFilter, query, review, reviewFilter, sort]);

  const includedCount = comparables.filter(
    (comp, index) => reviewDraftFor(review, comp, index).included,
  ).length;
  const changedCount = comparables.filter((comp, index) => {
    const decision = reviewDraftFor(review, comp, index);
    const engineIncluded = engineRecommended(comp);
    const key = comparableKey(comp, index);
    return (
      decision.included !== engineIncluded ||
      decision.weight_percentage !== 100 ||
      (conditionOverrides[key] ?? "unknown") !==
        (comp.condition_classification ?? "unknown")
    );
  }).length;
  const grades = [...new Set(comparables.map((comp) => comp.comp_grade).filter(Boolean))]
    .sort() as string[];
  const levels = [
    ...new Set(comparables.map((comp) => comp.search_level).filter(Boolean)),
  ] as string[];

  return (
    <section className={styles.compWorkbench} aria-label="Comparable review workbench">
      <header className={styles.compWorkbenchHeader}>
        <div>
          <span className={styles.sectionEyebrow}>Evidence decision</span>
          <h3>Comparable review</h3>
          <p>Final recorded-sale set for this valuation version.</p>
        </div>
        <div className={styles.compWorkbenchModes} aria-label="Comparable view">
          <button
            aria-pressed={view === "compare"}
            onClick={() => setView("compare")}
            type="button"
          >
            <List aria-hidden="true" size={15} />
            Compare
          </button>
          <button
            aria-pressed={view === "location"}
            onClick={() => setView("location")}
            type="button"
          >
            <MapPinned aria-hidden="true" size={15} />
            Location
          </button>
        </div>
      </header>

      <div className={styles.compDecisionSummary}>
        <div>
          <span>Included</span>
          <strong>{includedCount}</strong>
        </div>
        <div>
          <span>Excluded</span>
          <strong>{comparables.length - includedCount}</strong>
        </div>
        <div>
          <span>Draft changes</span>
          <strong>{changedCount}</strong>
        </div>
        <button onClick={onRestoreRecommendation} type="button">
          <RotateCcw aria-hidden="true" size={15} />
          Restore system set
        </button>
      </div>

      <SubjectBand requestedAddress={requestedAddress} subject={subject} />

      <div className={styles.compReviewToolbar}>
        <label className={styles.compSearchField}>
          <Search aria-hidden="true" size={15} />
          <span className={styles.srOnly}>Search address or subdivision</span>
          <input
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search address or subdivision"
            value={query}
          />
        </label>
        <div className={styles.compFilterSegment} aria-label="Decision filter">
          {(["all", "included", "excluded"] as ReviewFilter[]).map((option) => (
            <button
              aria-pressed={reviewFilter === option}
              key={option}
              onClick={() => setReviewFilter(option)}
              type="button"
            >
              {titleCase(option)}
            </button>
          ))}
        </div>
        <label>
          <span className={styles.srOnly}>Filter by grade</span>
          <select onChange={(event) => setGradeFilter(event.target.value)} value={gradeFilter}>
            <option value="all">All grades</option>
            {grades.map((grade) => (
              <option key={grade} value={grade}>
                Grade {grade}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className={styles.srOnly}>Filter by search level</span>
          <select onChange={(event) => setLevelFilter(event.target.value)} value={levelFilter}>
            <option value="all">All search levels</option>
            {levels.map((level) => (
              <option key={level} value={level}>
                {titleCase(level)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className={styles.srOnly}>Sort comparables</span>
          <select onChange={(event) => setSort(event.target.value as ReviewSort)} value={sort}>
            <option value="fit">Best fit</option>
            <option value="distance">Nearest</option>
            <option value="recent">Most recent</option>
            <option value="value">Highest indication</option>
          </select>
        </label>
      </div>

      {view === "location" ? (
        <ComparableLocationView
          comparables={filteredComparables}
          requestedAddress={requestedAddress}
          review={review}
          subject={subject}
        />
      ) : (
        <div className={styles.compCandidateList}>
          {filteredComparables.map((comp, index) => {
            const originalIndex = comparables.indexOf(comp);
            const compKey = comparableKey(comp, originalIndex >= 0 ? originalIndex : index);
            const decision = reviewDraftFor(
              review,
              comp,
              originalIndex >= 0 ? originalIndex : index,
            );
            const condition = conditionOverrides[compKey] ?? "unknown";
            return (
              <ComparableCandidate
                adjustedIndicationCents={adjustedIndications[compKey]}
                analystRecommendation={analystRecommendations[compKey]}
                comp={comp}
                compKey={compKey}
                condition={condition}
                decision={decision}
                key={compKey}
                onConditionChange={onConditionChange}
                onReviewChange={onReviewChange}
                subject={subject}
              />
            );
          })}
          {!filteredComparables.length ? (
            <div className={styles.compEmptyState}>
              <SlidersHorizontal aria-hidden="true" size={20} />
              <strong>No comparables match these filters.</strong>
              <button
                onClick={() => {
                  setQuery("");
                  setReviewFilter("all");
                  setGradeFilter("all");
                  setLevelFilter("all");
                }}
                type="button"
              >
                Clear filters
              </button>
            </div>
          ) : null}
        </div>
      )}

      <footer className={styles.compReviewFooter}>
        <div>
          <strong>{includedCount} sales will control the recalculation</strong>
          <span>
            Applying creates a new saved analysis; this version and its evidence remain unchanged.
          </span>
        </div>
        <button
          disabled={saving || disabled || !comparables.length || includedCount === 0}
          onClick={onApply}
          type="button"
        >
          <Check aria-hidden="true" size={16} />
          {saving ? "Applying..." : "Apply review and recalculate"}
        </button>
      </footer>
    </section>
  );
}

function SubjectBand({
  requestedAddress,
  subject,
}: {
  requestedAddress: string;
  subject: SubjectProperty;
}) {
  return (
    <section className={styles.compSubjectBand} aria-label="Subject property facts">
      <div className={styles.compSubjectIdentity}>
        <span>Subject property</span>
        <strong>{subject.formattedAddress ?? requestedAddress}</strong>
        <small>
          {[subject.propertyType, subject.subdivision].filter(Boolean).join(" / ") ||
            "Property facts from the saved analysis"}
        </small>
      </div>
      <Fact label="Beds" value={formatNumber(subject.bedrooms)} />
      <Fact label="Baths" value={formatNumber(subject.bathrooms)} />
      <Fact label="Living area" value={formatMeasurement(subject.squareFootage, "sqft")} />
      <Fact label="Year built" value={formatNumber(subject.yearBuilt)} />
      <Fact label="Lot" value={formatMeasurement(subject.lotSize, "sqft")} />
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.compSubjectFact}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ComparableCandidate({
  adjustedIndicationCents,
  analystRecommendation,
  comp,
  compKey,
  condition,
  decision,
  onConditionChange,
  onReviewChange,
  subject,
}: {
  adjustedIndicationCents?: number | null;
  analystRecommendation?: CompAnalystRecommendation;
  comp: MarketComparable;
  compKey: string;
  condition: CompCondition;
  decision: CompReviewDraft;
  onConditionChange: (compKey: string, condition: CompCondition) => void;
  onReviewChange: (compKey: string, decision: CompReviewDraft) => void;
  subject: SubjectProperty;
}) {
  const reasonOptions = decision.included
    ? COMPARABLE_INCLUDED_REASONS
    : COMPARABLE_EXCLUDED_REASONS;
  const recommended = engineRecommended(comp);
  const overridden = recommended !== decision.included;
  const sourceBadges = comparableSourceBadges(comp);
  const sourceConflicts = comparableSourceConflicts(comp);
  const usesAdjustedIndication = typeof adjustedIndicationCents === "number";

  return (
    <article
      className={`${styles.compCandidate} ${
        decision.included ? styles.compIncluded : styles.compExcluded
      }`}
    >
      <header className={styles.compCandidateHeader}>
        <div className={styles.compGrade} data-grade={comp.comp_grade ?? "D"}>
          <span>Grade</span>
          <strong>{comp.comp_grade ?? "--"}</strong>
        </div>
        <div className={styles.compCandidateIdentity}>
          <div>
            <strong>{comp.formatted_address ?? "Unknown address"}</strong>
            <span>
              {titleCase(comp.search_level ?? "legacy")} search / Match {comp.score ?? "?"}
            </span>
          </div>
          <div className={styles.compBadges}>
            {sourceBadges.map((source) => (
              <span className={styles.compSourceBadge} key={source}>
                {source}
              </span>
            ))}
            {comp.corroborated === true ? (
              <span className={styles.compOverlapBadge}>Corroborated</span>
            ) : sourceBadges.length > 1 || (comp.source_overlap_count ?? 0) > 1 ? (
              <span className={styles.compOverlapBadge}>Cross-sourced</span>
            ) : null}
            {sourceConflicts.length ? (
              <span className={styles.compConflictBadge}>Source conflict</span>
            ) : null}
            {analystRecommendation ? (
              <span className={styles.compAiBadge}>
                AI draft: {titleCase(analystRecommendation.recommendation)}
              </span>
            ) : null}
            <span className={recommended ? styles.systemPick : styles.systemReject}>
              {recommended ? "System pick" : "System excluded"}
            </span>
            {overridden ? <span className={styles.reviewOverride}>Reviewer changed</span> : null}
          </div>
        </div>
        <label className={styles.compIncludeToggle}>
          <input
            checked={decision.included}
            onChange={(event) => {
              const included = event.target.checked;
              onReviewChange(compKey, {
                ...decision,
                included,
                reason: included
                  ? COMPARABLE_INCLUDED_REASONS[0]
                  : COMPARABLE_EXCLUDED_REASONS[0],
              });
            }}
            type="checkbox"
          />
          <span>{decision.included ? "Included" : "Excluded"}</span>
        </label>
      </header>

      <div className={styles.compValueStrip}>
        <div>
          <span>Recorded sale</span>
          <strong>{formatMoney(comp.price_cents)}</strong>
          <small>{formatDate(comp.sale_date)}</small>
        </div>
        <div>
          <span>{usesAdjustedIndication ? "Adjusted indication" : "Subject-size indication"}</span>
          <strong>
            {formatMoney(
              usesAdjustedIndication ? adjustedIndicationCents : comp.adjusted_value_cents,
            )}
          </strong>
          <small>
            {usesAdjustedIndication
              ? "Recorded sale plus locally supported adjustments"
              : `${formatMoney(comp.price_per_square_foot_cents)} / sqft`}
          </small>
        </div>
        <div>
          <span>Location</span>
          <strong>{formatDistance(comp.distance_miles, comp.direction_from_subject)}</strong>
          <small>{comp.subdivision ?? "Subdivision unavailable"}</small>
        </div>
      </div>

      <div className={styles.compSideBySide} role="table" aria-label="Subject comparison">
        <div className={styles.compComparisonHead} role="row">
          <span role="columnheader">Property fact</span>
          <span role="columnheader">Subject</span>
          <span role="columnheader">Comparable</span>
          <span role="columnheader">Difference</span>
        </div>
        <ComparisonRow
          compValue={comp.square_footage}
          label="Living area"
          subjectValue={subject.squareFootage}
          unit="sqft"
        />
        <ComparisonRow
          compValue={comp.bedrooms}
          label="Bedrooms"
          subjectValue={subject.bedrooms}
        />
        <ComparisonRow
          compValue={comp.bathrooms}
          label="Bathrooms"
          subjectValue={subject.bathrooms}
        />
        <ComparisonRow
          compValue={comp.year_built}
          label="Year built"
          subjectValue={subject.yearBuilt}
          year
        />
        <ComparisonRow
          compValue={comp.lot_size}
          label="Lot size"
          subjectValue={subject.lotSize}
          unit="sqft"
        />
      </div>

      <div className={styles.compReviewControls}>
        <label>
          <span>Condition at sale</span>
          <select
            aria-label={`Condition at sale for ${comp.formatted_address ?? "comparable"}`}
            onChange={(event) =>
              onConditionChange(compKey, event.target.value as CompCondition)
            }
            value={condition}
          >
            {(["unknown", "as_is", "renovated"] as CompCondition[]).map((value) => (
              <option key={value} value={value}>
                {conditionLabel(value)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Decision reason</span>
          <select
            aria-label={`Decision reason for ${comp.formatted_address ?? "comparable"}`}
            onChange={(event) =>
              onReviewChange(compKey, { ...decision, reason: event.target.value })
            }
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
        <label className={styles.compWeightControl}>
          <span>Evidence weight: {decision.weight_percentage}%</span>
          <input
            aria-label={`Evidence weight for ${comp.formatted_address ?? "comparable"}`}
            disabled={!decision.included}
            max="150"
            min="50"
            onChange={(event) =>
              onReviewChange(compKey, {
                ...decision,
                weight_percentage: Number(event.target.value),
              })
            }
            step="5"
            type="range"
            value={decision.weight_percentage}
          />
        </label>
      </div>

      <details className={styles.compEvidenceDetails}>
        <summary>Evidence and rationale</summary>
        <div>
          <section>
            <span>System rationale</span>
            <p>{comp.engine_selection_reason ?? comp.selection_reason ?? "No rationale saved."}</p>
          </section>
          <section>
            <span>Condition evidence</span>
            <p>{comp.condition_evidence ?? "No condition evidence recorded."}</p>
          </section>
          <section>
            <span>Source</span>
            <p>
              {sourceBadges.length
                ? sourceBadges.join(" / ")
                : titleCase(comp.evidence_source ?? "provider record")}
              {comp.source_reference ? ` / ${comp.source_reference}` : ""}
              {comp.source_url ? (
                <a href={comp.source_url} rel="noreferrer" target="_blank">
                  Open source <ExternalLink aria-hidden="true" size={13} />
                </a>
              ) : null}
            </p>
          </section>
          {sourceConflicts.length ? (
            <section>
              <span>Source conflicts</span>
              <ul>
                {sourceConflicts.map((conflict, index) => (
                  <li key={`${conflict}-${index}`}>{conflict}</li>
                ))}
              </ul>
            </section>
          ) : null}
          {analystRecommendation ? (
            <section>
              <span>AI analyst draft</span>
              <p>
                {titleCase(analystRecommendation.recommendation)}: {analystRecommendation.reason}
                {typeof analystRecommendation.confidence === "number"
                  ? ` (${Math.round(analystRecommendation.confidence)}% confidence)`
                  : ""}
              </p>
            </section>
          ) : null}
          {comp.verification_notes ? (
            <section>
              <span>Verification notes</span>
              <p>{comp.verification_notes}</p>
            </section>
          ) : null}
          {comp.search_warnings?.length ? (
            <section>
              <span>Evidence warnings</span>
              <ul>
                {comp.search_warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      </details>
    </article>
  );
}

function ComparisonRow({
  compValue,
  label,
  subjectValue,
  unit,
  year = false,
}: {
  compValue: number | null | undefined;
  label: string;
  subjectValue: number | null | undefined;
  unit?: string;
  year?: boolean;
}) {
  return (
    <div className={styles.compComparisonRow} role="row">
      <strong role="cell">{label}</strong>
      <span role="cell">{formatMeasurement(subjectValue, unit)}</span>
      <span role="cell">{formatMeasurement(compValue, unit)}</span>
      <span role="cell">{formatDifference(subjectValue, compValue, unit, year)}</span>
    </div>
  );
}

function ComparableLocationView({
  comparables,
  requestedAddress,
  review,
  subject,
}: {
  comparables: MarketComparable[];
  requestedAddress: string;
  review: Record<string, CompReviewDraft>;
  subject: SubjectProperty;
}) {
  const points = relativeLocationPoints(subject, comparables);
  return (
    <div className={styles.compLocationLayout}>
      <div className={styles.compLocationPlot}>
        <span className={styles.compassNorth}>N</span>
        <span className={styles.compassEast}>E</span>
        <span className={styles.compassSouth}>S</span>
        <span className={styles.compassWest}>W</span>
        <div className={styles.locationRingInner} />
        <div className={styles.locationRingOuter} />
        <div className={styles.subjectLocationDot} title={requestedAddress}>
          S
        </div>
        {points.map(({ comp, left, top }, index) => {
          const compKey = comparableKey(comp, comparables.indexOf(comp));
          const included = review[compKey]?.included ?? comp.selection_status !== "rejected";
          return (
            <div
              className={`${styles.compLocationDot} ${
                included ? styles.locationIncluded : styles.locationExcluded
              }`}
              key={compKey}
              style={{ left: `${left}%`, top: `${top}%` }}
              title={`${comp.formatted_address ?? "Comparable"}: ${formatDistance(
                comp.distance_miles,
                comp.direction_from_subject,
              )}`}
            >
              {index + 1}
            </div>
          );
        })}
        {!points.length ? (
          <div className={styles.locationUnavailable}>
            Coordinate positions are unavailable for the filtered sales.
          </div>
        ) : null}
      </div>
      <div className={styles.compLocationLegend}>
        <div>
          <strong>Relative location</strong>
          <span>{requestedAddress}</span>
          <small>Distance and direction evidence; not a parcel or neighborhood boundary map.</small>
        </div>
        {comparables.map((comp, index) => {
          const compKey = comparableKey(comp, index);
          const included = review[compKey]?.included ?? comp.selection_status !== "rejected";
          const pointIndex = points.findIndex((point) => point.comp === comp);
          return (
            <div className={styles.compLocationLegendRow} key={compKey}>
              <span data-included={included}>{pointIndex >= 0 ? pointIndex + 1 : "-"}</span>
              <div>
                <strong>{comp.formatted_address ?? "Unknown address"}</strong>
                <small>
                  {formatDistance(comp.distance_miles, comp.direction_from_subject)} / Grade {comp.comp_grade ?? "--"}
                </small>
              </div>
              {included ? <Check aria-label="Included" size={15} /> : <X aria-label="Excluded" size={15} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function relativeLocationPoints(subject: SubjectProperty, comparables: MarketComparable[]) {
  if (
    typeof subject.latitude !== "number" ||
    typeof subject.longitude !== "number"
  ) {
    return [];
  }
  const positioned = comparables.flatMap((comp) =>
    typeof comp.latitude === "number" && typeof comp.longitude === "number"
      ? [
          {
            comp,
            x:
              (comp.longitude - subject.longitude!) *
              Math.cos((subject.latitude! * Math.PI) / 180),
            y: comp.latitude - subject.latitude!,
          },
        ]
      : [],
  );
  const maxOffset = Math.max(
    ...positioned.map((point) => Math.hypot(point.x, point.y)),
    0.00001,
  );
  return positioned.map((point) => ({
    comp: point.comp,
    left: 50 + (point.x / maxOffset) * 38,
    top: 50 - (point.y / maxOffset) * 38,
  }));
}

function comparableKey(comp: MarketComparable, index: number) {
  return comp.provider_id ?? comp.formatted_address ?? `comp-${index}`;
}

function reviewDraftFor(
  review: Record<string, CompReviewDraft>,
  comp: MarketComparable,
  index: number,
) {
  const key = comparableKey(comp, index);
  return (
    review[key] ?? {
      included: comp.selection_status !== "rejected",
      reason:
        comp.selection_status === "rejected"
          ? COMPARABLE_EXCLUDED_REASONS[0]
          : COMPARABLE_INCLUDED_REASONS[0],
      weight_percentage: 100,
    }
  );
}

function engineRecommended(comp: MarketComparable) {
  if (comp.engine_selection_status) {
    return comp.engine_selection_status === "selected";
  }
  return comp.selection_status !== "rejected";
}

function compareComps(
  left: MarketComparable,
  right: MarketComparable,
  sort: ReviewSort,
  adjustedIndications: Record<string, number | null | undefined>,
) {
  if (sort === "distance") {
    return nullableNumber(left.distance_miles, Number.MAX_SAFE_INTEGER) -
      nullableNumber(right.distance_miles, Number.MAX_SAFE_INTEGER);
  }
  if (sort === "recent") {
    return nullableNumber(left.days_old, Number.MAX_SAFE_INTEGER) -
      nullableNumber(right.days_old, Number.MAX_SAFE_INTEGER);
  }
  if (sort === "value") {
    return nullableNumber(comparableIndication(right, adjustedIndications), -1) -
      nullableNumber(comparableIndication(left, adjustedIndications), -1);
  }
  return nullableNumber(right.score, -1) - nullableNumber(left.score, -1);
}

function comparableIndication(
  comp: MarketComparable,
  adjustedIndications: Record<string, number | null | undefined>,
) {
  const key = comp.provider_id ?? comp.formatted_address;
  return (key ? adjustedIndications[key] : undefined) ?? comp.adjusted_value_cents;
}

function comparableSourceBadges(comp: MarketComparable) {
  const labels = [
    ...(comp.source_providers ?? []),
    ...(comp.corroborating_sources ?? []),
    comp.evidence_source,
  ]
    .filter((value): value is string => Boolean(value?.trim()))
    .map(sourceLabel);
  return [...new Set(labels)];
}

function comparableSourceConflicts(comp: MarketComparable) {
  const savedConflicts = (comp.source_conflicts ?? []).map((conflict) => {
    if (typeof conflict === "string") {
      return conflict;
    }
    const explanation = conflict.summary ?? conflict.explanation ?? "Provider observations disagree.";
    const detail = conflict.field ? `${titleCase(conflict.field)}: ${explanation}` : explanation;
    return conflict.material === false ? `Minor provider variance: ${detail}` : detail;
  });
  const fieldConflicts = (comp.field_conflicts ?? []).map((conflict) => {
    const observedProviders = [
      ...new Set(
        (conflict.observations ?? [])
          .map((observation) => observation.provider)
          .filter((provider): provider is string => Boolean(provider)),
      ),
    ].map(sourceLabel);
    const scope = observedProviders.length
      ? ` across ${observedProviders.join(" and ")}`
      : " across providers";
    const explanation = conflict.summary ?? `${titleCase(conflict.field)} differs${scope}.`;
    const detail = conflict.summary ? `${titleCase(conflict.field)}: ${explanation}` : explanation;
    return conflict.material === false ? `Minor provider variance: ${detail}` : detail;
  });
  return [...new Set([...savedConflicts, ...fieldConflicts])];
}

function sourceLabel(value: string) {
  const normalized = value.trim().toLowerCase();
  if (normalized.includes("rentcast")) return "RentCast";
  if (normalized.includes("dealmachine")) return "DealMachine";
  if (normalized.includes("manual")) return "Manual verified";
  if (normalized.includes("ai_web") || normalized.includes("public")) return "Public cited";
  if (normalized === "provider_record") return "Provider record";
  return titleCase(value);
}

function nullableNumber(value: number | null | undefined, fallback: number) {
  return typeof value === "number" ? value : fallback;
}

function formatMoney(cents: number | null | undefined) {
  if (cents === null || cents === undefined) {
    return "Unavailable";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function formatDate(value: string | null | undefined) {
  if (!value) {
    return "Sale date unavailable";
  }
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      }).format(date);
}

function formatNumber(value: number | null | undefined) {
  return value === null || value === undefined
    ? "--"
    : new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(value);
}

function formatMeasurement(value: number | null | undefined, unit?: string) {
  const formatted = formatNumber(value);
  return formatted === "--" || !unit ? formatted : `${formatted} ${unit}`;
}

function formatDifference(
  subjectValue: number | null | undefined,
  compValue: number | null | undefined,
  unit?: string,
  year = false,
) {
  if (typeof subjectValue !== "number" || typeof compValue !== "number") {
    return "Unknown";
  }
  const difference = compValue - subjectValue;
  if (difference === 0) {
    return "Same";
  }
  const sign = difference > 0 ? "+" : "";
  if (year) {
    return `${sign}${formatNumber(difference)} years`;
  }
  const percentage = subjectValue !== 0 ? Math.round((difference / subjectValue) * 100) : null;
  return `${sign}${formatNumber(difference)}${unit ? ` ${unit}` : ""}${
    percentage === null ? "" : ` (${sign}${percentage}%)`
  }`;
}

function formatDistance(distance: number | null | undefined, direction?: string | null) {
  if (typeof distance !== "number") {
    return direction ?? "Distance unavailable";
  }
  return `${distance.toFixed(distance < 1 ? 2 : 1)} mi${direction ? ` ${direction}` : ""}`;
}

function conditionLabel(value: CompCondition) {
  if (value === "as_is") {
    return "As-is / dated";
  }
  if (value === "renovated") {
    return "Renovated";
  }
  return "Unknown";
}

function titleCase(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}
