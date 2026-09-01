# Stonegate Land Valuation Method

Last updated: August 8, 2026
Live methodology key: `land_v1.0`

## Purpose And Boundary

Stonegate Land Valuation is a dedicated, deterministic closed-sale method for Land leads. It does
not use House ARV, living square footage, room counts, repair estimates, residential V2/V3 math,
or a provider AVM. AI may summarize saved evidence and missing diligence; it does not select,
weight, calculate, or alter the conclusion.

The subject property record comes from the immutable current `land_v1` property-intelligence
snapshot. RealEstateAPI supports the documented [Property Detail](https://developer.realestateapi.com/reference/property-detail-api-1)
lookup used by this workflow. Comparable research uses the documented
[Property Search](https://developer.realestateapi.com/reference/property-search-api) filters for
Land, arms-length sale evidence, sale date, lot size, and geography.

## Provider And Cost Boundary

- A property-research run uses one Property Detail request and saves the result for reuse.
- The Land Valuation tab never searches merely because it was opened.
- **Search closed Land sales and save analysis** makes one explicit Property Search request.
- Every paid-search request carries a lead-scoped idempotency key. Replaying the same request key
  returns its saved analysis instead of spending another provider call, and same-parcel leads keep
  separate valuation histories.
- The request is capped by `LAND_VALUATION_MAX_PROVIDER_RESULTS`, currently defaulted to 25.
- Reviewing or rejecting saved comparable evidence creates a new immutable analysis with zero
  provider calls.
- Selected and rejected candidates remain saved and visible, so a reviewer can restore a rejected
  sale or recover from a reject-all decision without another provider search.
- Changing acreage, valuation basis, or per-lot count invalidates the saved sale indications and
  requires a fresh explicit search.

## Subject Identity And Evidence

The Land subject must have either a complete address or a county-scoped parcel identity:

`state | normalized county | normalized APN`

APN formatting punctuation is ignored, but meaningful zeroes are preserved. The same APN in two
counties is not the same property. An APN/provider mismatch fails closed and does not overwrite the
CRM property.

The calculation needs positive acreage from the current saved property record or a human override
with an evidence reference. A human may map the subject to one supported use group—residential,
agricultural, commercial, industrial, or recreational—with a cited source. A generic or unmapped
zoning code is not treated as verified Land use.

## Comparable Search Tiers

| Tier | Radius | Recency | Comparable acreage / subject acreage |
| --- | ---: | ---: | ---: |
| Preferred | 10 miles | 24 months | 0.50 to 2.00 |
| Expanded | 25 miles | 36 months | 0.33 to 3.00 |
| Extended | 50 miles | 60 months | 0.20 to 5.00 |

Extended evidence always requires review and cannot produce actionable offer guidance in version
1. When subject coordinates are unavailable, the provider may use county geography for research,
but offer guidance remains withheld until coordinates support distance-based comparison.

## Comparable Eligibility

A selected comparable must have:

- A Land property type.
- Positive closed-sale price and valid sale date.
- Positive acreage for per-acre analysis, or a verified lot count for per-lot analysis.
- A supported evidence tier.
- A mapped Land-use group compatible with the subject.
- A parcel identity different from the subject.
- Arms-length evidence from the provider search filter.

Duplicates, the subject parcel, transfers without required unit evidence, unknown/incompatible
uses, out-of-tier sales, and human-rejected candidates are saved with their rejection reason.

## Deterministic Math

All money calculations use integer cents and `Decimal`. Acres are stored to four decimal places.

For per-acre analysis:

`comparable price per acre = closed-sale price / comparable acres`

`subject indication = comparable price per acre × subject acres`

Per-lot analysis uses the same structure with verified lot counts. Version 1 applies no unsupported
acreage multiplier. Every saved comparable has an adjustment factor of `1.0`; acreage similarity
is controlled by the declared ratio tiers instead.

Eligible candidates receive a deterministic score based on tier, distance, recency, acreage
similarity, and known use. At most eight are selected. Each selected sale's weight is its score
divided by the total selected score.

The conclusion is the weighted distribution of saved subject indications:

- Supported low: weighted 25th percentile.
- Supported point: weighted 50th percentile.
- Supported high: weighted 75th percentile.
- Final money outputs: half-up rounding to the nearest $100.

Provider AVMs are excluded from every formula.

## Offer-Policy Math

An owner must activate a versioned Land offer policy before actionable guidance is available. A
new draft starts with reviewable defaults; creating a draft does not activate it.

Before Stonegate presents a saved analysis as current, it rechecks the lead/property relationship,
current property identity signature, current research snapshot, snapshot expiration, and active
offer-policy version. A change in any of those conditions immediately withholds quick-sale and
offer guidance without altering the historical analysis.

`quick-sale low = supported low × (1 - high quick-sale discount)`

`quick-sale high = supported point × (1 - low quick-sale discount)`

`seller contract ceiling = quick-sale low - assignment target - closing/title reserve - curative reserve - uncertainty reserve`

`opening guidance = seller contract ceiling × (1 - opening reserve)`

The initial recommended draft is 15% to 25% quick-sale discount, 10% opening reserve, $15,000
assignment target, $3,000 closing/title reserve, $5,000 curative reserve, $5,000 uncertainty
reserve, three minimum comparable sales, and 50% maximum comparable dispersion. These are business
policy defaults, not universal market facts. The owner must inspect them before activation.

## Fail-Closed Guidance Gates

A supported research range may appear while offer guidance remains withheld. Opening guidance and
seller ceiling stay null unless all of these pass:

- Current, matching, unexpired `land_v1` property snapshot.
- APN and positive acreage with no unresolved identity conflict.
- Subject coordinates.
- Supported subject Land-use group.
- Human-verified legal access with evidence reference.
- Active owner-approved offer policy.
- At least the policy minimum of eligible closed sales and at least two Preferred/Expanded sales.
- Known, compatible use for every selected sale.
- No Extended-tier selected sale.
- Comparable dispersion at or below the active policy limit.
- Positive seller ceiling after all reserves.

Rejecting every provider candidate is valid. Stonegate saves an insufficient-evidence analysis and
withholds all offer guidance.

## Immutability And Audit

Each analysis stores the exact property snapshot, raw normalized candidates, selected and rejected
sales, weights, subject indications, policy snapshot, calculation assumptions, blockers, provider
request bounds, returned count, estimated credit usage, lineage, creator, and timestamp. A reviewed
analysis points to its source analysis. Neither valuation nor review mutates the source property
snapshot or an earlier analysis.

## Remaining Launch Work

- Dedicated manual Land comparable evidence.
- Official flood, wetland, soil, slope, septic, utility, access, zoning, and county screening
  integrations with evidence status.
- Land valuation report and calibration workspaces.
- Consequential Land offer approval.
- Land site-visit, counsel-approved generated/e-signed contract, generated buyer-package, and
  automated disposition-outreach workflows.

Until those stages are verified, consequential Land offer approval, Stonegate-generated contracts,
e-signature, generated packets, and automated outreach remain blocked even when research guidance
is available. Staff may separately record a real outside offer or already-executed agreement and
may approve the exact externally prepared investor packet for asset-aware buyer-pool review.
