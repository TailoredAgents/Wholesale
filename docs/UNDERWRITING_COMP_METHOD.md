# Underwriting Comp Method

## Purpose

The underwriting assistant should create a draft, not a final offer.

The system should:

1. Pull market data from RentCast.
2. Prefer recent, nearby, similar sale comps.
3. Calculate an ARV range.
4. Estimate repairs from property condition and square footage.
5. Calculate offer ceilings using 65-70% of ARV minus repairs and assignment fee.
6. Save the analysis and a `needs_review` underwriting version.
7. Generate a PDF report so humans can audit the comp choice, math, and mistakes.
8. Require human approval before ARV or offers become official.

## Comp Selection

Use the sales comparison approach:

- Prefer closed/recent comparable sales over active listings.
- Match similar physical/legal characteristics where data is available.
- Prioritize proximity, recency, size, property type, condition, and similarity score.
- Treat active listings as context only because asking price is not the same as market-cleared value.
- Reject comps that are missing price data.
- Save selected and rejected comps with reasons.

Initial screening rules:

- Pull up to 20 RentCast comps.
- Select up to 5 best comps.
- Prefer comps within 1 mile and 90 days.
- Keep 3 comps when available.
- Flag low confidence when comp count is thin or ARV spread is wide.

## ARV Range

When at least 3 selected comps have price and square footage:

- Calculate price per square foot for each selected comp.
- Apply the 25th percentile PPSF to the subject square footage for ARV low.
- Apply the 75th percentile PPSF to the subject square footage for ARV high.

When square footage is not reliable:

- Use the 25th and 75th percentile selected comp prices.

When fewer than 3 selected comps are usable:

- Fall back to RentCast's value range.
- If only a single value exists, use an 8% band around the estimate.

## Repair Range

Initial repair screening uses property condition and subject square footage:

- Cosmetic/good: $15-$25 per square foot.
- Needs repairs/unknown: $30-$50 per square foot.
- Major/full gut/fire: $60-$90 per square foot.
- Structural/tear-down: $100-$140 per square foot.

This is not a contractor bid. It is a screening estimate until a human updates repairs.

## Offer Formula

The system creates a conservative screening range:

- Low offer ceiling: `ARV low x 65% - repair high - assignment fee`.
- High offer ceiling: `ARV high x 70% - repair low - assignment fee`.
- Recommended starting offer: low offer ceiling.

Default assignment fee:

- `$15,000`, controlled by `UNDERWRITING_DEFAULT_ASSIGNMENT_FEE_CENTS`.

The 65-70% rule is a screening tool. It should not override buyer demand, local market speed, repair certainty, title risk, seller motivation, or human approval.

## PDF Audit Report

Every saved market analysis can generate a PDF report.

The report includes:

- Seller/property summary.
- Provider value and value range.
- Draft ARV range.
- Repair range.
- 65-70% offer ceiling math.
- Recommended starting offer.
- Selected comps with score and selection reason.
- Rejected/context comps with rejection reason.
- Human review checklist.

This report is required before trusting the automation because it shows where the system may be wrong.

## Reliability Notes

This is a strong screening setup, not a final autonomous acquisition decision.

Before relying on it heavily:

- Compare generated reports against 20-50 manually comped deals.
- Track where RentCast data is stale, missing, or misleading.
- Add MLS/RESO sold data where licensed.
- Add county/deed/tax validation for ownership and parcel facts.
- Tune repair assumptions and assignment fee by market and buyer feedback.
- Keep human approval for ARV, repairs, and offer ceiling.

## Sources

- Fannie Mae comparable sales guidance: https://selling-guide.fanniemae.com/sel/b4-1.3-08/comparable-sales
- Fannie Mae sales comparison approach: https://selling-guide.fanniemae.com/sel/b4-1.3-07/sales-comparison-approach-section-appraisal-report
- Fannie Mae comparable sale adjustments: https://selling-guide.fanniemae.com/sel/b4-1.3-09/adjustments-comparable-sales
- Investopedia sales comparison approach overview: https://www.investopedia.com/terms/s/sales-comparison-approach.asp
- BiggerPockets 70% rule explanation: https://www.biggerpockets.com/forums/67/topics/1214017-what-is-the-70-rule-in-house-flipping
- Chase 70% rule overview: https://www.chase.com/personal/mortgage/education/buying-a-home/mao-real-estate
