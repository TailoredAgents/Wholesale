import styles from "./page.module.css";

type RateEvidence = {
  key: string;
  label: string;
  status: "supported" | "unsupported";
  unit?: string | null;
  rate?: number | null;
  sample_count: number;
  pair_count: number;
  reason?: string | null;
};

type AdjustmentComponent = {
  key: string;
  label: string;
  amount_cents: number;
  rate: number;
  unit: string;
  difference: number;
  applied_difference: number;
  extrapolation_limited: boolean;
};

type CompAdjustment = {
  comp_key: string;
  formatted_address?: string | null;
  sale_price_cents: number;
  total_adjustment_cents: number;
  adjusted_indication_cents: number;
  gross_adjustment_percentage: number;
  requires_review: boolean;
  components: AdjustmentComponent[];
  relative_weight_percentage?: number | null;
  distance_from_point_cents?: number | null;
  distance_from_point_percentage?: number | null;
  range_position?: string | null;
  evidence_source?: string | null;
  verification_status?: string | null;
};

type RangeDriver =
  | string
  | {
      key?: string | null;
      label?: string | null;
      summary?: string | null;
      explanation?: string | null;
      impact?: string | null;
      impact_cents?: number | null;
      comp_keys?: string[];
      evidence_keys?: string[];
      severity?: "info" | "review" | "high" | string;
    };

export type MarketAdjustment = {
  version: string;
  calculation_version?: string;
  status: "supported" | "partial" | "unsupported";
  valuation_use:
    | "live_human_reviewed_underwriting"
    | "shadow_only_excluded_from_offer_math";
  baseline: {
    arv_low_cents?: number | null;
    arv_point_cents?: number | null;
    arv_high_cents?: number | null;
  };
  conclusion: {
    arv_low_cents?: number | null;
    arv_point_cents?: number | null;
    arv_high_cents?: number | null;
    confidence_score: number;
    confidence_tier: string;
    comp_count: number;
  };
  comparison: {
    point_delta_cents?: number | null;
    point_delta_percentage?: number | null;
  };
  rate_evidence: RateEvidence[];
  comp_adjustments: CompAdjustment[];
  range_drivers?: RangeDriver[];
  range_diagnostics?: {
    version?: string;
    policy?: string;
    artificial_padding_applied?: boolean;
    raw_sale_span_cents?: number | null;
    adjusted_indication_span_cents?: number | null;
    adjustment_span_change_cents?: number | null;
    supported_range_width_cents?: number | null;
    supported_range_percentage?: number | null;
    drivers?: RangeDriver[];
  } | null;
  warnings: string[];
};

export function MarketAdjustmentPanel({
  adjustment,
  arvPointCents,
  arvLowCents,
  arvHighCents,
  workingGuidance = false,
}: {
  adjustment: MarketAdjustment;
  arvPointCents?: number | null;
  arvLowCents?: number | null;
  arvHighCents?: number | null;
  workingGuidance?: boolean;
}) {
  const supportedRates = adjustment.rate_evidence.filter(
    (evidence) => evidence.status === "supported",
  );
  const rangeDrivers = rangeDriverItems(adjustment, arvPointCents, arvLowCents, arvHighCents);
  const pointLabel = workingGuidance ? "Working ARV" : "Stonegate ARV";
  const rangeLabel = workingGuidance ? "Working range" : "Supported range";

  return (
    <section className={styles.adjustmentShadow} aria-label="Market-supported valuation adjustments">
      <header className={styles.adjustmentShadowHeader}>
        <div>
          <span>Stonegate valuation conclusion</span>
          <strong>{workingGuidance ? "Adjusted-sales working guidance" : "Adjusted closed-sale ARV"}</strong>
        </div>
        <div className={styles.adjustmentStatus}>
          <span>{statusLabel(adjustment.status)}</span>
          <small>Provider AVMs do not control this conclusion or offer math.</small>
        </div>
      </header>

      <div className={styles.adjustmentShadowMetrics}>
        <div className={styles.adjustmentPrimaryMetric}>
          <span>{pointLabel}</span>
          <strong>{formatMoney(arvPointCents)}</strong>
          <small>Weighted conclusion from adjusted closed sales</small>
        </div>
        <div className={styles.adjustmentRangeMetric}>
          <span>{rangeLabel}</span>
          <strong>
            {formatMoney(arvLowCents)} to {formatMoney(arvHighCents)}
          </strong>
          <small>
            {adjustment.conclusion.comp_count} adjusted closed sales
          </small>
        </div>
        <div>
          <span>Local rate support</span>
          <strong>{supportedRates.length}</strong>
          <small>property differences supported by nearby sales</small>
        </div>
        <div>
          <span>Confidence</span>
          <strong>{workingGuidance ? "Review" : `${adjustment.conclusion.confidence_score}%`}</strong>
          <small>{workingGuidance ? "two-sale working guidance" : adjustment.conclusion.confidence_tier}</small>
        </div>
      </div>

      {rangeDrivers.length ? (
        <details className={styles.rangeDriverDetails}>
          <summary>{rangeSummaryLabel(arvPointCents, arvLowCents, arvHighCents)}</summary>
          {adjustment.range_diagnostics ? (
            <div className={styles.rangeDiagnosticMetrics}>
              <span>
                Raw sale span
                <strong>{formatMoney(adjustment.range_diagnostics.raw_sale_span_cents)}</strong>
              </span>
              <span>
                Adjusted indication span
                <strong>
                  {formatMoney(adjustment.range_diagnostics.adjusted_indication_span_cents)}
                </strong>
              </span>
              <span>
                Supported range width
                <strong>
                  {formatMoney(adjustment.range_diagnostics.supported_range_width_cents)}
                </strong>
              </span>
            </div>
          ) : null}
          <div className={styles.rangeDriverList}>
            {rangeDrivers.map((driver, index) => (
              <article data-severity={driver.severity} key={`${driver.key}-${index}`}>
                <div>
                  <strong>{driver.label}</strong>
                  {driver.impact ? <span>{driver.impact}</span> : null}
                </div>
                <small>{driver.summary}</small>
              </article>
            ))}
          </div>
        </details>
      ) : null}

      <div className={styles.adjustmentRateSummary}>
        <strong>Supported local adjustments</strong>
        <div>
          {supportedRates.length ? (
            supportedRates.map((evidence) => (
              <span key={evidence.key}>
                {evidence.label}: {formatRate(evidence)}
              </span>
            ))
          ) : (
            <small>No adjustment rate met the evidence threshold. Sales remain usable with a wider range.</small>
          )}
        </div>
      </div>

      <details className={styles.adjustmentShadowDetails}>
        <summary>Review rate support and withheld adjustments</summary>
        <div className={styles.adjustmentRateList}>
          {adjustment.rate_evidence.map((evidence) => (
            <article key={evidence.key}>
              <div>
                <strong>{evidence.label}</strong>
                <span data-supported={evidence.status === "supported"}>
                  {evidence.status === "supported" ? "Supported" : "Withheld"}
                </span>
              </div>
              <small>
                {evidence.status === "supported"
                  ? `${formatRate(evidence)} from ${evidence.sample_count} sales and ${evidence.pair_count} pairs.`
                  : evidence.reason}
              </small>
            </article>
          ))}
        </div>
      </details>

      <details className={styles.adjustmentShadowDetails}>
        <summary>Review comparable adjustment math</summary>
        <div className={styles.adjustmentCompList}>
          {adjustment.comp_adjustments.map((comp) => (
            <article key={comp.comp_key}>
              <div className={styles.adjustmentCompHeader}>
                <div>
                  <strong>{comp.formatted_address ?? comp.comp_key}</strong>
                  <small>
                    Recorded sale {formatMoney(comp.sale_price_cents)} · {sourceLabel(comp.evidence_source)}
                  </small>
                </div>
                <div>
                  <span>{formatSignedMoney(comp.total_adjustment_cents)}</span>
                  <strong>{formatMoney(comp.adjusted_indication_cents)}</strong>
                  <small>
                    {typeof comp.relative_weight_percentage === "number"
                      ? `${comp.relative_weight_percentage.toFixed(1)}% conclusion weight`
                      : "Saved evidence weight"}
                    {comp.range_position ? ` · ${comp.range_position.replaceAll("_", " ")}` : ""}
                    {typeof comp.distance_from_point_cents === "number"
                      ? ` · ${formatSignedMoney(comp.distance_from_point_cents)} from ARV`
                      : ""}
                  </small>
                </div>
              </div>
              {comp.components.length ? (
                <div className={styles.adjustmentComponents}>
                  {comp.components.map((component) => (
                    <span key={component.key}>
                      {component.label} {formatSignedMoney(component.amount_cents)}
                      {component.extrapolation_limited ? " (limited to observed range)" : ""}
                    </span>
                  ))}
                </div>
              ) : (
                <small>No supported dollar adjustment was applied.</small>
              )}
              {comp.requires_review ? (
                <small className={styles.adjustmentReviewFlag}>Review required</small>
              ) : null}
            </article>
          ))}
        </div>
      </details>

      {adjustment.warnings.length ? (
        <small className={styles.adjustmentShadowWarning}>{adjustment.warnings.join(" ")}</small>
      ) : null}
    </section>
  );
}

function statusLabel(status: MarketAdjustment["status"]) {
  if (status === "supported") return "Locally supported";
  if (status === "partial") return "Partial support";
  return "Insufficient evidence";
}

function rangeDriverItems(
  adjustment: MarketAdjustment,
  arvPointCents?: number | null,
  arvLowCents?: number | null,
  arvHighCents?: number | null,
) {
  const explicitDrivers =
    adjustment.range_drivers ?? adjustment.range_diagnostics?.drivers ?? [];
  const explicit = explicitDrivers.map((driver, index) => {
    if (typeof driver === "string") {
      return {
        key: `saved-${index}`,
        label: "Saved range diagnostic",
        summary: driver,
        impact: null,
        severity: "info",
      };
    }
    return {
      key: driver.key ?? `saved-${index}`,
      label: driver.label ?? "Range driver",
      summary: driver.summary ?? driver.explanation ?? "Review the saved valuation evidence.",
      impact:
        typeof driver.impact_cents === "number"
          ? formatMoney(driver.impact_cents)
          : driver.impact
            ? driver.impact.replaceAll("_", " ")
            : null,
      severity: driver.severity ?? "info",
    };
  });
  if (explicit.length) {
    return explicit;
  }

  const derived: Array<{
    key: string;
    label: string;
    summary: string;
    impact: string | null;
    severity: string;
  }> = [];
  if (
    typeof arvLowCents === "number" &&
    typeof arvHighCents === "number" &&
    arvHighCents >= arvLowCents
  ) {
    const width = arvHighCents - arvLowCents;
    const percentage =
      typeof arvPointCents === "number" && arvPointCents > 0
        ? Math.round((width / arvPointCents) * 100)
        : null;
    derived.push({
      key: "adjusted-spread",
      label: "Adjusted-sale dispersion",
      summary: `The selected adjusted indications span ${formatMoney(width)}${
        percentage === null ? "" : `, or ${percentage}% of the Stonegate ARV`
      }.`,
      impact: "Observed spread",
      severity: percentage !== null && percentage > 15 ? "high" : "info",
    });
  }

  const withheld = adjustment.rate_evidence.filter(
    (evidence) => evidence.status === "unsupported",
  );
  if (withheld.length) {
    derived.push({
      key: "withheld-adjustments",
      label: "Withheld adjustments",
      summary: `${withheld.length} property difference${withheld.length === 1 ? " was" : "s were"} not assigned a dollar adjustment because local evidence did not meet the support threshold.`,
      impact: "Preserves uncertainty",
      severity: "review",
    });
  }

  const reviewCount = adjustment.comp_adjustments.filter((comp) => comp.requires_review).length;
  if (reviewCount) {
    derived.push({
      key: "review-required",
      label: "Comparable review",
      summary: `${reviewCount} adjusted sale${reviewCount === 1 ? " requires" : "s require"} human review before the conclusion should be approved.`,
      impact: "Review needed",
      severity: "high",
    });
  }
  return derived;
}

function sourceLabel(value?: string | null) {
  if (!value) return "source saved";
  const normalized = value.toLowerCase();
  if (normalized.includes("rentcast")) return "RentCast";
  if (normalized.includes("dealmachine")) return "DealMachine";
  if (normalized.includes("realestateapi")) return "RealEstateAPI";
  if (normalized.includes("manual")) return "manual verified";
  if (normalized.includes("ai_web") || normalized.includes("public")) return "public cited";
  return value.replaceAll("_", " ");
}

function rangeSummaryLabel(
  arvPointCents?: number | null,
  arvLowCents?: number | null,
  arvHighCents?: number | null,
) {
  if (
    typeof arvPointCents === "number" &&
    arvPointCents > 0 &&
    typeof arvLowCents === "number" &&
    typeof arvHighCents === "number" &&
    (arvHighCents - arvLowCents) / arvPointCents >= 0.15
  ) {
    return "Why this supported range is broad";
  }
  return "What drives this supported range";
}

function formatMoney(value?: number | null) {
  if (value === null || value === undefined) return "--";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value / 100);
}

function formatSignedMoney(value?: number | null) {
  if (value === null || value === undefined) return "--";
  return `${value > 0 ? "+" : ""}${formatMoney(value)}`;
}

function formatRate(evidence: RateEvidence) {
  if (evidence.rate === null || evidence.rate === undefined) return "--";
  if (evidence.unit === "monthly_compound_rate") {
    return `${(evidence.rate * 100).toFixed(2)}% / month`;
  }
  if (evidence.unit === "cents_per_square_foot") {
    return `${formatMoney(evidence.rate)} / sqft`;
  }
  if (evidence.unit === "cents_per_lot_square_foot") {
    return `${formatMoney(evidence.rate)} / lot sqft`;
  }
  return formatMoney(evidence.rate);
}
