# Underwriting V2 Method

## Purpose

Underwriting V2 creates an auditable acquisition recommendation. It does not approve an
offer. A qualified user must verify comparable condition, repair scope, title, buyer demand,
and exit assumptions before changing an underwriting version from `needs_review`.

## Evidence Hierarchy

The engine keeps three conclusions separate:

1. **As-is value:** what the property may be worth in its current condition.
2. **After-repair value (ARV):** the supported retail value after a defined renovation.
3. **Contract recommendation:** the amount Stonegate can pay while preserving a viable exit.

RentCast's `/properties` endpoint supplies property records and recorded sale history.
Recorded sale price and date are the core comp evidence. The `/avm/value` result is retained
as a benchmark and disagreement check; its comparable `price` fields are listing prices and
are not treated as closed-sale prices.

## Comparable Search

The initial provider query uses:

- Same property type.
- One-mile radius.
- Sale within 365 days.
- Bedrooms and bathrooms within one.
- Living area within 20% at retrieval and 25% at final screening.
- Year built within 25 years.
- Up to 50 candidate records.

The final screen rejects the subject property, missing sale price/date, different property
type, living-area difference over 25%, bed/bath difference over one, and age difference over
25 years. Eligible sales are scored for distance, recency, living area, age, and lot fit. The
five best records are saved; all excluded records retain a reason.

The search does not cross a neighborhood boundary intentionally. RentCast radius search is a
geographic screen, so the reviewer must still reject sales from a different subdivision,
school district, flood influence, traffic corridor, or other competing market.

## Condition Classification

Every selected sale starts as `unknown`. A reviewer classifies it as:

- `renovated`: credible evidence shows condition comparable to the target finished product.
- `as_is`: credible evidence shows dated, distressed, or unrenovated condition.
- `unknown`: evidence is absent or inconclusive.

Evidence may come from MLS photos/remarks, listing archives, permits, or direct verification.
The system records that the classification was human-supplied. It does not infer renovation
quality from sale price.

At least three renovated comps are required for a supported ARV conclusion. At least two
as-is comps are required for a comp-supported as-is conclusion. Until those thresholds are
met, the AVM is only a benchmark and manual review remains required.

## Value Conclusions

The engine uses score-weighted sale-price quartiles:

- 25th percentile: supported low.
- 50th percentile: point estimate.
- 75th percentile: supported high.

ARV uses confirmed renovated comps when at least three exist. As-is value uses confirmed
as-is comps when at least two exist. The conservative ARV applies a confidence haircut to the
point estimate while remaining inside the supported range:

- 2% at confidence 80 or higher.
- 5% at confidence 60-79.
- 8% below confidence 60.

No time, square-foot, bed/bath, or condition dollar adjustment is fabricated. Until a
reviewed adjustment model is implemented, material differences reduce score or reject the
comp.

## Repair Scope

The user can prepare an analysis with structured inputs before a seller meeting:

- Current property condition and target finish.
- A system screening budget, user-entered total, or itemized repair budget.
- A contingency percentage and expected holding period.
- Repair details, estimate source notes, and items to verify during the walkthrough.

Itemized costs take precedence over a user-entered total, so repair costs cannot be counted
twice. The selected base budget receives contingency once to produce total rehab.

Every saved analysis is labeled `Preliminary`, `Pre-meeting reviewed`, or
`Walkthrough verified`. Entering custom facts automatically promotes a preliminary analysis
to pre-meeting reviewed. The label records how thoroughly the inputs have been checked; it
does not approve an offer or remove the human review gate.

When the system screening budget is used, the selected scope controls the estimate:

| Scope | Base range | Contingency |
| --- | ---: | ---: |
| Light cosmetic | $15-$25/sqft | 10% |
| Moderate renovation | $30-$50/sqft | 15% |
| Heavy renovation | $60-$90/sqft | 20% |
| Structural/full rebuild | $100-$140/sqft | 25% |

The base budget is the midpoint of the range. A user-entered total or itemized budget replaces
that midpoint while retaining the system range in the audit record. All repair budgets remain
estimates until supported by a walkthrough scope and contractor pricing.

## Buyer Economics

The flip-buyer maximum is:

```text
Conservative ARV
- total rehab
- purchase costs
- financing and holding costs
- resale costs
- required buyer profit
= flip buyer maximum
```

Defaults are 2% purchase costs, 6% financing/holding for six months, 8% resale costs, and a
buyer profit floor determined by repair scope. Financing and holding cost scales with the
entered holding period; for example, nine months applies 9% when the six-month default is 6%.
All base percentages are explicit environment settings.

When RentCast rent support exists for an eligible single-family exit, the engine also
estimates stabilized value from net operating income and the configured target cap rate.
The higher supported flip or rental maximum becomes the recommended disposition price.

The seller negotiation limits are:

```text
Recommended disposition
- assignment fee
- transaction reserve
= seller contract ceiling

Seller contract ceiling
- negotiation reserve
= opening recommendation
```

The old 65-70% rule is calculated only as an internal comparison. It is not the controlling
offer formula.

## Confidence And Review Gates

Confidence combines comp count and fit, condition evidence, value-range spread, AVM
agreement, and subject-data agreement. Manual review is required when:

- Confidence is below 75.
- Fewer than three renovated comps are confirmed.
- Fewer than two as-is comps are confirmed.
- The ARV range is too wide.
- The AVM materially disagrees with recorded sales.
- Subject facts disagree across sources.

Even when evidence thresholds are met, a human must approve the acquisition decision.

## Reports And Audit

Every run saves immutable raw provider responses, selected/rejected comps, classifications,
assumptions, review reasons, data disagreements, calculation outputs, and a linked
underwriting version.

The investor PDF includes the report stage, structured repair inputs, itemized costs and
notes, buyer economics, repair contingency, seller ceiling, opening recommendation, comp
rationale, and decision controls. The client PDF shows the report stage but excludes
Stonegate's repair budget, assignment, profit, and negotiation assumptions; it presents only
property facts, as-is/renovated value evidence, comparable sales, and limitations.

Changing classifications or repair scope reuses the latest saved provider evidence and does
not consume another market-data pull. `Refresh market data` deliberately retrieves new data.

## Validation Before Autonomy

Before broad operational reliance:

1. Back-test at least 50 known deals against an acquisitions manager's comp set.
2. Track predicted ARV against resale or verified retail outcome.
3. Track repair estimate against scoped budget and final spend.
4. Track predicted buyer maximum against actual buyer offers.
5. Review errors by market, property type, price band, and confidence band.
6. Add licensed MLS/RESO sold data when available.
7. Keep offer sending and contract commitments behind human approval.

## Primary Sources

- RentCast property records: https://developers.rentcast.io/reference/property-records
- RentCast property valuation: https://developers.rentcast.io/reference/property-valuation
- RentCast long-term rent estimate: https://developers.rentcast.io/reference/rent-estimate-long-term
- Fannie Mae comparable sales: https://selling-guide.fanniemae.com/sel/b4-1.3-08/comparable-sales
- Fannie Mae sales comparison approach: https://selling-guide.fanniemae.com/sel/b4-1.3-07/sales-comparison-approach-section-appraisal-report
- Fannie Mae comparable adjustments: https://selling-guide.fanniemae.com/sel/b4-1.3-09/adjustments-comparable-sales
