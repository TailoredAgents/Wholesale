# Underwriting V2.1 Method

## Purpose

Underwriting V2.1 creates an auditable acquisition recommendation. It does not approve an
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

## Address And Subject Validation

Stonegate keeps the staff-entered address as the CRM record and stores RentCast's returned address
separately. Common suffixes, directionals, state codes, and ZIP+4/ZIP5 are normalized for duplicate
matching. Provider confirmation compares street number/name, city, state, ZIP, and unit evidence;
the match score, issues, provider property ID, reviewer-visible facts, and timestamp are audited.
Editing the CRM address clears stale validation.

The underwriting subject is assembled field by field from the RentCast property record, then the
AVM subject, then the CRM property type when provider data is absent. Every retained subject field
records its source. Owner names and provider mailing-address data are excluded from the property
validation snapshot. An address mismatch or missing record lowers confidence and requires review,
but does not hide the calculations or prevent report generation.

## Comparable Search

The initial provider query uses:

- Same property type.
- One-mile radius.
- Sale within 365 days.
- Bedrooms and bathrooms within one.
- Living area within 20% at retrieval and final screening.
- Year built within 25 years.
- Up to 50 candidate records.

The final screen rejects the subject property, missing sale price/date, different property
type, living-area difference over 20%, bed/bath difference over one, and age difference over
25 years. Eligible sales are scored for distance, recency, living area, age, and lot fit. The
living-area score penalty increases as the size difference grows.

When at least three physically eligible records have been human-verified as renovated, the
engine calculates that group's median price per square foot. It rejects only extreme
renovated records using a median absolute deviation test plus wide percentage guardrails.
Unknown and as-is records are not rejected for a low price because condition may explain the
difference. The five best remaining records are saved; all excluded records retain a reason,
including the renovated-group median used for a price-per-square-foot rejection.

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
as-is comps are required for a comp-supported as-is conclusion. Before three renovated comps
are confirmed, selected recorded sales that are not classified as as-is still produce a
preliminary ARV, offer calculation, and report. Confirmation upgrades the conclusion from
preliminary to comp-supported; it does not unlock the calculation. The AVM is displayed
separately as a screening benchmark and cannot drive the seller ceiling.

## Value Conclusions

For each physically similar sale, the engine stores:

- The unmodified recorded sale price.
- Recorded sale price per square foot.
- A subject-size indicator: sale price / comp living area x subject living area.

The subject-size indicator is an investor screening calculation, not an appraisal adjustment
or claim that every square foot has equal contributory value. It is used only after property
type and physical similarity screens, and the raw sale remains visible for review.

The engine uses score-weighted subject-size indicator quartiles:

- 25th percentile: supported low.
- 50th percentile: point estimate.
- 75th percentile: supported high.

ARV uses confirmed renovated comps when at least three exist. Before that threshold, it uses
selected recorded sales that have not been confirmed as as-is and clearly labels the result
preliminary. As-is value uses confirmed as-is comps when at least two exist. The conservative
ARV applies a confidence haircut to the point estimate while remaining inside the calculated
range:

- 2% at confidence 80 or higher.
- 5% at confidence 60-79.
- 8% below confidence 60.

No time, bed/bath, condition, quality, or feature dollar adjustment is fabricated. Material
differences reduce score or reject the comp. A licensed appraisal-grade adjustment model
would require market-supported paired-sales evidence rather than a rule-of-thumb rate.

## Repair Scope

The basic comp setup asks only for:

- A system screening budget, user-entered total, or itemized repair budget.
- Repair scope.
- Optional repair details, estimate source notes, and items to verify during the walkthrough.

Standard-flip finish, scope-based contingency, and a six-month holding period remain explicit,
documented defaults. They are not basic comp questions because target finish was not changing
the comparable math, contingency can be derived from repair scope, and holding period belongs
to buyer economics. These defaults can be changed later in advanced underwriting when needed.

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
buyer profit floor determined by repair scope. Advanced underwriting can change the holding
period; for example, nine months applies 9% when the six-month default is 6%. All base
percentages are explicit environment settings.

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
- The comp-supported ARV range is too wide.
- The AVM materially disagrees with recorded sales.
- Subject facts disagree across sources.

Even when evidence thresholds are met, a human must approve the acquisition decision.

## Reports And Audit

Every run saves immutable raw provider responses, selected/rejected comps, classifications,
assumptions, review reasons, data disagreements, calculation outputs, and a linked
underwriting version.

A comp review covers every sale in the source analysis. The reviewer includes or excludes each
sale, confirms its condition, selects a reason, and may apply 50-150% of the engine's original
match weight. Applying the review reruns ARV, confidence, buyer economics, seller ceiling, and
opening recommendation from the retained provider snapshot. It creates a new market analysis and
underwriting version; it never edits the source result. The complete decision set, reviewer,
timestamp, source analysis ID, and resulting values are retained in analysis metadata and the
audit log.

The investor PDF includes the report stage, structured repair inputs, itemized costs and
notes, buyer economics, repair contingency, seller ceiling, opening recommendation, raw comp
prices, price per square foot, subject-size indicators, comp rationale, and decision controls.
The client PDF shows the report stage but excludes
Stonegate's repair budget, assignment, profit, and negotiation assumptions; it presents only
property facts, as-is/renovated value evidence, comparable sales, and limitations.

Changing classifications or repair scope reuses the latest saved provider evidence and does
not consume another market-data pull. `Refresh market data` deliberately retrieves new data.

## Repair Evidence And Presets

Light, moderate, heavy, and structural presets are starting scopes, not market conclusions. They
prefill a normalized item list that the underwriter must adjust for the property. The total is the
sum of the current work items plus the explicit contingency percentage.

Contractor bids, walkthrough estimates, and internal scopes are saved as immutable evidence.
Selecting one uses its itemized scope and contingency in the next analysis and records the source,
contractor, estimate date, and reference in the analysis snapshot. Editing a selected estimate
detaches it and creates a direct working scope; the saved evidence remains unchanged.

The investor report carries the evidence details and cost breakdown. The client report continues
to omit Stonegate's repair and negotiation assumptions. Saved underwriting versions can be
compared on the lead page, but comparison does not approve an offer or replace source review.

## Offer Ceiling Approval

An offer approval always references one immutable underwriting version. The negotiation plan
snapshots its ARV, repair budget, buyer disposition, recommended opening, and seller ceiling before
creating four controlled price points:

- Opening: the first supported price presented to the seller.
- Target: the preferred signed contract price.
- Stretch: the final planned negotiating step below the walk-away limit.
- Seller ceiling: the maximum supported contract price from the saved buyer economics.

The invariant is `opening <= target <= stretch <= seller ceiling`. The UI may prefill intermediate
steps, but the acquisitions user must review the numbers and provide a rationale. A new request
cancels any older pending plan for that lead. Approval is blocked if a newer underwriting version
exists, forcing the team to review the latest evidence instead of approving stale economics.

Only a role with seller-offer approval permission can decide the request. Approval records the
deciding user and notes, marks the source version approved, and moves the lead to `offer_ready`.
Rejection requires notes and returns the lead to underwriting. Approval does not send an offer,
create a contract, or authorize exceeding the recorded ceiling.

## Market Calibration

A verified outcome may be attached to any saved analysis after an expert review, appraisal,
completed resale, or other verified market sale establishes a better benchmark. The case snapshots
the prediction from that exact analysis before storing the later benchmark. Optional actual rehab,
seller contract, and disposition values support additional operating-error checks.

The Underwriting workspace reports these robust portfolio and market metrics:

- Median percentage error to show whether ARV estimates systematically run high or low.
- Median absolute percentage error to show typical ARV miss size without positive and negative
  misses canceling each other.
- Range coverage to show how often the verified ARV falls inside the saved low/high range.
- Overestimate, underestimate, and balanced counts using a two-percentage-point neutral band.
- Median absolute repair and disposition error when actual values are available.

Fewer than 10 cases is an insufficient sample. Ten through 49 cases builds evidence. At 50 cases,
the market is ready for a human formula review. No threshold enables automatic formula changes;
changes require documented review, a new methodology version, and continued human offer approval.

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
