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
};

export type MarketAdjustment = {
  version: string;
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

  return (
    <section className={styles.adjustmentShadow} aria-label="Market-supported valuation adjustments">
      <header className={styles.adjustmentShadowHeader}>
        <div>
          <span>Stonegate valuation adjustments</span>
          <strong>{statusLabel(adjustment.status)}</strong>
        </div>
        <small>Local evidence used to support the saved ARV and offer calculations.</small>
      </header>

      <div className={styles.adjustmentShadowMetrics}>
        <div>
          <span>{workingGuidance ? "Working ARV" : "Stonegate ARV"}</span>
          <strong>{formatMoney(arvPointCents)}</strong>
        </div>
        <div>
          <span>{workingGuidance ? "Working range" : "Supported range"}</span>
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
                  <small>Recorded sale {formatMoney(comp.sale_price_cents)}</small>
                </div>
                <div>
                  <span>{formatSignedMoney(comp.total_adjustment_cents)}</span>
                  <strong>{formatMoney(comp.adjusted_indication_cents)}</strong>
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
