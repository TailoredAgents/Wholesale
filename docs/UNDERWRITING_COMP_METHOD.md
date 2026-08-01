# Stonegate Underwriting Method

## Version Status

- **Current implemented method:** Underwriting V2.2 calculations with `adaptive_v1` closed-sale
  discovery plus implemented U3.1-U3.4 evidence and review controls.
- **Approved target:** Underwriting V3, planned as an in-place upgrade to V2.2.
- **Current operating authority:** V2.2 formulas remain live. Implemented evidence and workflow
  phases may improve the inputs and explanations without activating unfinished V3 formulas.
- **V3 roadmap authority:** The planned V3 section at the end of this document governs the upgrade
  sequence. Planned behavior must not be presented to staff as if it already exists.

V3 does not create a second underwriting system. It extends the existing market-analysis service,
repair estimates, field inspections, underwriting versions, offer approvals, reports, audit events,
and calibration cases. Existing V2.2 analyses remain immutable and readable after V3 is introduced.

## Purpose

Underwriting V2.2 creates an auditable acquisition recommendation. It does not approve an
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

The analysis performs one deterministic address-resolution sequence:

1. Try the staff-entered full address.
2. Reuse a previously provider-confirmed formatted address when available.
3. Retry the provider-standard `Street, City, State, ZIP` format.
4. Retry normalized street suffixes such as `Trail` to `Trl`.
5. Accept a fallback only when street number, city, state, ZIP, and an overall match score meet
   the configured identity threshold.

Every attempt, provider response status, resolved address, match score, and rejection reason is
saved. A result with a different street number, city, state, or ZIP is never silently accepted.
If the RentCast AVM remains unavailable but an acceptable property record is found, Stonegate
continues with screened recorded sales and clearly marks the AVM unavailable. If the subject
property itself cannot be identified, the analysis stops instead of comping the wrong property.

The underwriting subject is assembled field by field from the RentCast property record, then the
AVM subject, then the CRM property type when provider data is absent. Every retained subject field
records its source. Owner names and provider mailing-address data are excluded from the property
validation snapshot. An address mismatch or missing record lowers confidence and requires review,
but does not hide the calculations or prevent report generation.

## Comparable Search

Fresh provider evidence uses three controlled searches, stopping as soon as the evidence threshold
is met:

| Level | Radius | Sale age | Bedrooms | Bathrooms | Living area | Year built |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Preferred | 0.5 mile | 180 days | exact | +/- 0.5 | +/- 15% | +/- 15 years |
| Expanded | 1 mile | 365 days | +/- 1 | +/- 1 | +/- 20% | +/- 25 years |
| Extended | 3 miles | 730 days | +/- 1 | +/- 1 | +/- 25% | +/- 35 years |

Each query returns up to 50 public property records. Wider results are deduplicated by RentCast
property ID or normalized address, and a repeated sale keeps the earliest level where it appeared.
The system stops with at least three screened closed sales when available market-area evidence is
adequate. If subject and comp subdivisions are both available, at least two selected sales must
match the subject subdivision. Missing subdivision data does not invent a mismatch, but it creates
a visible micro-market warning.

The final screen rejects the subject property, missing sale price/date, different property type,
bed/bath difference over one, and records beyond the active level's bounded size or age limit.
Eligible sales are scored for distance, recency, living area, age, lot, and subdivision fit. Each
sale receives an A-D fit grade plus its search level. Extended-only evidence receives stronger
distance and recency penalties and cannot receive an A or B grade.

When at least three physically eligible records have been human-verified as renovated, the
engine calculates that group's median price per square foot. It rejects only extreme
renovated records using a median absolute deviation test plus wide percentage guardrails.
Unknown and as-is records are not rejected for a low price because condition may explain the
difference. The five best remaining records are saved; all excluded records retain a reason,
including the renovated-group median used for a price-per-square-foot rejection.

If the extended search remains insufficient, the final level becomes `manual`. Stonegate saves the
best suitable labeled evidence, the exact shortage, and the next action. It does not silently use
an active listing, AVM value, subject sale, different property type, or otherwise rejected record
to reach three comps. RentCast radius and subdivision fields remain evidence, not a definitive
market boundary, so the reviewer must still evaluate school district, flood influence, traffic
corridor, design, and other competing-market differences.

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

Confidence is a visible 100-point evidence score:

| Factor | Maximum |
| --- | ---: |
| Confirmed subject address | 20 |
| Quantity of screened recorded sales | 25 |
| Physical and market fit of those sales | 25 |
| Human-confirmed renovated/as-is condition evidence | 15 |
| Precision of the supported ARV range | 10 |
| Agreement across provider and secondary sources | 5 |

The UI and PDFs show every factor, its points, and an explanation. Confidence tiers are `High`
at 85-100, `Moderate` at 70-84, `Low` at 50-69, and `Insufficient` below 50. A preliminary ARV
without three renovated comps is capped below 60 regardless of the other evidence.

Manual review is required when:

- Confidence is below 75.
- Fewer than three renovated comps are confirmed.
- Fewer than two as-is comps are confirmed.
- The comp-supported ARV range is too wide.
- The AVM materially disagrees with recorded sales.
- Subject facts disagree across sources.

Even when evidence thresholds are met, a human must approve the acquisition decision.

## Controlled Secondary Research

On a fresh complete analysis, the existing OpenAI Responses API integration may run one bounded
web-search pass when `OPENAI_WEB_SEARCH_ENABLED=true`. It:

- Searches only for public, property-level evidence.
- Prioritizes county/municipal records, assessor records, permits, and dated brokerage listings.
- Excludes owner, occupant, tenant, phone, email, and other personal information.
- Cannot estimate ARV, repairs, an offer, or a price range.
- Cannot modify comps, valuation math, or CRM facts.
- Keeps only facts tied to URLs that the search actually consulted.
- Stores source titles, URLs, limitations, conflicts, model, and token usage with the immutable
  analysis.

Secondary research corroborates or challenges the primary provider evidence. It never becomes a
second valuation engine. A conflict lowers source-agreement confidence and appears in the review
list. Search failure does not block the RentCast/recorded-sales workflow.

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
prices, price per square foot, subject-size indicators, comp rationale, confidence factors,
resolved-address evidence, cited public sources, and decision controls.
The client PDF shows the report stage but excludes
Stonegate's repair budget, assignment, profit, and negotiation assumptions; it presents only
property facts, as-is/renovated value evidence, comparable sales, cited public sources, and
limitations.

Applying a comp review reuses its chosen immutable analysis. The primary `Run complete analysis`
or `Refresh complete analysis` action performs address resolution, provider retrieval, secondary
research when enabled, comp screening, confidence scoring, repair math, and buyer economics in one
workflow.

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

## Concession And Price-Discussion Governance

An approved plan begins with its opening offer. Every increase is a sequential concession tied to
that plan and must state why Stonegate is moving and what the seller gives in exchange. A proposed
amount through target or stretch is authorized by the approved ladder. An amount above stretch and
at or below the ceiling creates a manager approval request. An amount above the ceiling is rejected
and requires revised underwriting and a newly approved plan.

Only an authorized concession can be presented. Field and manual workflows store the presented
amount, seller counter, channel, notes, actor, appointment, and concession in an append-only event
ledger. An accepted amount must equal the most recently presented governed offer. Approving a new
plan supersedes older approved plans and cancels their unused concession authority while retaining
already presented offers and decisions as historical evidence.

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
- Median absolute seller-contract variance. This is an operating comparison to the predicted
  ceiling, not a claim that the negotiated contract should equal the ceiling.
- Operator comp-review override rate, measured against the immutable automated source analysis.

Fewer than 10 cases is an insufficient sample. Ten through 49 cases builds evidence. At 50 cases,
the market is ready for a human formula review. No threshold enables automatic formula changes;
changes require documented review, a new methodology version, and continued human offer approval.

The provider scorecard uses Stonegate pilot monitoring thresholds rather than representing them as
universal appraisal standards:

- Fewer than 10 verified outcomes: `insufficient_evidence`.
- Median absolute ARV error above 12% or range coverage below 70%: `monitor`.
- Median absolute ARV error above 15% or range coverage below 60%:
  `provider_review_required`.
- A market with at least 10 cases and none of those warning conditions: `adequate`.

These thresholds organize review; they do not prove a valuation is correct. Every formula or
provider proposal freezes the current scorecard into a decision record. A change can be drafted
before 50 cases but cannot be approved before the selected market scope reaches 50 verified cases.
Approval requires an authorized person and written decision notes. Rejection and continuing the
current method are also retained, so later reviewers can see why Stonegate did or did not change.

Provider adequacy is measured separately by market. RentCast remains the active source until the
verified error, range misses, or operator override burden justifies a licensed sold-data source.
RESO defines real-estate data standards; it is not itself a data provider. Adding "RESO data"
therefore requires a licensed MLS or vendor that implements those standards.

## Validation Before Autonomy

Before broad operational reliance:

1. Back-test at least 50 known deals against an acquisitions manager's comp set.
2. Track predicted ARV against resale or verified retail outcome.
3. Track repair estimate against scoped budget and final spend.
4. Track predicted buyer maximum against actual buyer offers.
5. Review errors by market, property type, price band, and confidence band.
6. Add licensed MLS/RESO sold data when available.
7. Keep offer sending and contract commitments behind human approval.

## Underwriting V3 Upgrade Roadmap

### Product Objective

Underwriting V3 should let the closer move from an address to a supportable appointment offer with
the least practical manual work while preserving the evidence needed to challenge, explain, or
correct every conclusion. It must work as one Stonegate workflow before the appointment, during an
iPad walkthrough, and during offer preparation.

The system should help Austin answer five questions:

1. Did Stonegate identify the correct property?
2. What are the best available closed sales, and how strong is each one?
3. What would this specific property likely cost to renovate to the selected target finish?
4. What can a real buyer pay while preserving the intended exit economics?
5. What price can Stonegate open at, negotiate toward, and never exceed without new approval?

### Upgrade Principles

1. **Extend existing records.** Reuse the current lead, property, market analysis, repair estimate,
   inspection, underwriting version, offer plan, report, audit, and calibration records.
2. **One workflow, multiple evidence stages.** Preliminary, pre-meeting reviewed, and walkthrough
   verified are increasingly supported versions of the same deal, not separate tools.
3. **Closed sales remain primary.** Active or pending listings, AVMs, market trends, and public web
   research provide context but cannot silently replace closed-sale support.
4. **Broaden searches transparently.** The system may use older, farther, or less physically similar
   sales when better evidence is unavailable, but it must label the tradeoff and preserve the reason.
5. **Unknown never means zero.** Missing condition or repair evidence creates uncertainty, a reserve,
   or a verification item. It cannot silently remove cost or risk.
6. **AI interprets evidence; governed math prices it.** AI may suggest scope from seller answers,
   transcripts, notes, and photos. A versioned cost catalog and deterministic formulas calculate the
   dollars. A human confirms consequential inputs.
7. **No fabricated precision.** When local evidence cannot support an adjustment, V3 widens the
   range and lowers confidence instead of inventing a dollar adjustment.
8. **Every recommendation is explainable.** Raw values, adjustments, sources, search tiers,
   overrides, assumptions, and uncertainty remain visible and auditable.
9. **Existing approvals remain authoritative.** V3 does not send an offer, sign a contract, or permit
   an amount above an approved seller ceiling.
10. **Provider-neutral boundaries.** RentCast remains the first provider. Additional sold-data or
    construction-cost providers connect through adapters only after measured need justifies them.

### Target Operator Journey

#### Stage 1: Quick Comp

From the lead, the closer selects **Prepare valuation**. Stonegate verifies the subject, runs the
adaptive comp search, applies a preliminary repair scope from known seller information, and shows a
working ARV and offer range. No itemized dollar knowledge is required. The result is explicitly
`Preliminary` and lists the few facts that would most improve it.

#### Stage 2: Desk Review

Before the appointment, the closer reviews the strongest closed sales, condition evidence, active
market support, search expansion, and conflicts in one workbench. Stonegate recommends a set, but the
closer confirms the final comps and any available renovation classifications. The result becomes
`Pre-meeting reviewed` and can generate an appointment packet.

#### Stage 3: iPad Walkthrough

The existing field inspection becomes the guided property walkthrough. The closer marks each major
component as `Unknown`, `No work`, `Repair`, `Replace`, or `Specialist review`; records quantity and
severity only when useful; takes photos; and dictates notes. AI may prefill suggestions with cited
evidence, but the closer confirms them. The verified scope transfers into the existing repair
estimate and underwriting version records.

#### Stage 4: Offer Decision

Stonegate recalculates the deal and presents a focused decision summary: supported ARV range,
expected and high repair scenarios, buyer maximum, Stonegate contract ceiling, opening offer,
approved negotiation ladder, and unresolved risks. Supporting evidence stays one level below the
summary instead of crowding the seller conversation.

#### Stage 5: Reports And Outcome

The investor report carries complete math and evidence. The client report remains seller-safe and
does not expose Stonegate margins or negotiation authority. Later contractor bids, buyer offers,
resale results, and closing outcomes feed the existing calibration workflow without rewriting the
historical analysis.

### Adaptive Comparable Search Contract

V3 replaces the single fixed recent-sales request with a recorded search ladder. The ranges below
are initial defaults, not claims that radius alone defines a market:

| Level | Default search | Intended use |
| --- | --- | --- |
| Preferred | Same known subdivision/market area when available; approximately 1 mile, 12 months, same property type, and tight physical similarity | Primary closed-sale evidence |
| Expanded | Approximately 2 miles and 18 months with moderately wider physical limits | Fill a thin preferred set while preserving likely buyer competition |
| Extended | Up to approximately 5 miles and 24 months or a documented competing market area | Best available evidence for unusual, rural, or low-volume properties |
| Manual | User-entered verified closed sale with its source and reason | Licensed MLS, agent, closing record, or other trusted evidence absent from the provider |

The engine stops expanding when it has enough strong evidence, not merely enough rows. Search
quality considers subdivision or market area, property type, living area, room count, age, lot,
sale recency, distance, condition evidence, and known location influences. Extended results never
inherit the same confidence as preferred results merely because they pass a wider filter.

Every search attempt stores its parameters, returned count, accepted count, provider cost metadata
when available, timestamp, and reason for expansion. Results are deduplicated across levels. Fresh
provider retrieval is cached with the immutable analysis so comp review and repair changes do not
repeat paid requests.

If fewer than three defensible closed sales remain, V3 still produces a clearly provisional range
when evidence permits. It offers manual comp entry and identifies the exact missing support instead
of returning a generic failure. Active/pending listings and the AVM remain separately labeled
context and cannot be counted as the missing closed sales.

### Comparable Evidence Classes

The workbench keeps four evidence classes visually and mathematically separate:

1. **Closed sales:** primary value evidence.
2. **Active and pending listings:** competition, direction, and ceiling/floor context; not closed
   prices.
3. **AVM and market statistics:** benchmark, trend, and disagreement detection.
4. **Public research and operator evidence:** permits, listing photos or remarks, agent verification,
   and other cited condition or property facts.

Each closed-sale candidate receives a grade:

- **Strong:** same likely market, strong physical fit, recent, and condition evidence suitable for
  the conclusion.
- **Acceptable:** useful with a visible and supportable difference or adjustment.
- **Weak:** best available context but materially different, expanded, or poorly verified.
- **Excluded:** not a credible indicator for the selected conclusion, with a retained reason.

The user can add, include, exclude, or reweight a comp, but every manual decision requires a reason
and creates a new immutable analysis as V2.2 does today.

### V3 Value Adjustment Contract

V3 retains raw recorded prices and price per square foot, but the current full subject-size
indicator becomes a benchmark rather than the controlling value transformation.

The target adjusted-sale formula is:

```text
Recorded sale price
+ supported market-condition/time adjustment
+ supported marginal living-area adjustment
+ supported condition, quality, or feature adjustments
= adjusted comparable indication
```

An adjustment is used only when its source market has enough relevant observations, the method is
stable under replay, and the rate and evidence are stored with the analysis. Candidate methods may
include matched pairs, a robust local model, or a documented market index. The model-development
sample is separate from the final selected comp set so three selected comps are not misrepresented
as a statistically sufficient adjustment model.

V3 must guard against double counting. For example, bedroom count normally overlaps with living
area, and a renovated-condition adjustment must not duplicate an item already reflected in the
target-finish comparison. Unsupported differences reduce grade or confidence instead of receiving
a guessed dollar value. The reconciled conclusion remains within the supportable adjusted range.

### Guided Repair Scope Contract

The existing `System`, `Total`, and `Itemized` modes remain compatible. Itemized mode evolves from
blank dollar inputs into a guided scope.

Each category stores, where applicable:

- component status: `unknown`, `no_work`, `repair`, `replace`, or `specialist_review`
- severity or finish level
- quantity and unit
- low, expected, and high system cost
- manual override and override reason
- evidence source and references
- AI suggestion, confidence, and confirmation status
- inspection verification status

The first categories remain roof, HVAC, plumbing, electrical, foundation, kitchen, bathrooms,
flooring, paint/drywall, windows/doors, exterior, landscaping, permits, cleanup, and other. Their
inputs become component-specific: roof area or scope, HVAC system count, bathroom count, window
count, flooring/paint area, kitchen finish level, and minor/partial/full system work.

The cost engine uses a versioned catalog with effective dates, Georgia market or ZIP/metro factors,
unit costs, minimum charges, labor/material components when available, and source notes. It returns
low, expected, and high totals plus contingency. A manual amount remains available on every row and
always shows that it replaced the system amount.

Unknown high-risk components receive an explicit uncertainty treatment. Foundation, structural,
major electrical, major plumbing, environmental, and similar concerns may require specialist
review. That warning does not hide the valuation or PDFs, but it widens repair/offer scenarios and
appears in the appointment plan.

Initially, Stonegate can maintain an internal Georgia cost catalog. A licensed source such as
RSMeans or another construction-cost provider is optional later. Actual walkthrough scopes,
contractor bids, and completed project costs calibrate the internal catalog by market and category;
AI does not silently train on or change those rates.

### AI Repair Assistant Contract

The existing Acquisitions Copilot gains a repair-scope tool rather than becoming a second agent or
valuation engine. It may:

- extract reported repair facts from qualification answers, communications, and transcripts
- identify likely component conditions from supported inspection photos
- turn dictated walkthrough notes into structured draft scope items
- identify contradictions or missing evidence
- recommend the next highest-value inspection question or photo
- explain why the governed cost engine produced a range

It may not independently confirm a component, set a manual price, erase an unknown, approve ARV,
change offer authority, or represent a repair budget as a contractor quote. Every suggestion keeps
its source evidence and requires human confirmation before it changes the working scope.

### Planned Implementation Phases

#### U3.1: Compatibility, Baseline, And Evaluation Cases

**Status:** Implemented July 31, 2026.

- Freeze representative V2.2 analyses and expected calculations as regression fixtures.
- Add ordinary, thin-market, rural, unique-property, conflicting-data, provider-failure, repair,
  and adversarial test cases.
- Define additive V3 API/schema contracts and V2.2 read compatibility.
- Record baseline comp yield, operator overrides, completion time, ARV error, range coverage, and
  repair error from available cases.
- Put V3 calculation activation behind a methodology version or controlled feature flag.

**Exit:** Existing analyses and reports remain readable; baseline fixtures pass; every later phase
has measurable acceptance cases.

Implementation record:

- V2.2 golden fixtures preserve verified ARV, as-is, repair, buyer-economics, seller-ceiling, and
  opening-offer outputs.
- Regression cases cover ordinary, thin-market, rural/older, unique-property, conflicting-source,
  provider-failure, adversarial-sale, and repair-entry behavior.
- `UNDERWRITING_ACTIVE_METHODOLOGY_VERSION=v2.2` pins the active runner.
- `UNDERWRITING_V3_SHADOW_ENABLED=true` now runs the implemented adjustment method beside V2.2;
  `UNDERWRITING_ACTIVE_METHODOLOGY_VERSION=v3` remains rejected until controlled rollout.
- New analyses store methodology control, execution duration, provider/candidate/selected/rejected
  counts, comp yield, cache reuse, manual-review state, and comp-review override counts in existing
  immutable analysis metadata.
- The existing calibration API now includes an all-analysis operating baseline while retaining ARV,
  range-coverage, repair, disposition, seller-ceiling, and reviewed-outcome metrics.
- Legacy analyses without the new metadata continue to read with optional V3 fields absent.

#### U3.2: Adaptive Closed-Sale Discovery

**Status:** Implemented July 31, 2026.

- Add the preferred, expanded, extended, and manual search levels.
- Use subdivision evidence when available and retain market-area warnings.
- Cache, deduplicate, grade, and explain every returned sale.
- Continue safely when the AVM is unavailable but verified subject and closed-sale evidence exist.
- Replace generic insufficient-comp failures with a search summary and next action.

**Exit:** Thin-market test properties either produce the best available labeled set or a precise
evidence shortage; the engine never silently substitutes an unsuitable property or listing price.

Implementation record:

- Fresh analyses use `adaptive_v1` closed-sale discovery. Preferred search is 0.5 mile / 180 days
  with tight physical filters, expanded search is 1 mile / 365 days with the prior V2.2 physical
  limits, and extended search is 3 miles / 730 days with bounded 25% living-area and 35-year age
  tolerances.
- Search stops as soon as at least three screened sales satisfy the available market-area evidence.
  When the subject subdivision and returned subdivision data are available, at least two selected
  sales must match that subdivision before the provider search is considered sufficient.
- Repeated records from wider queries are deduplicated by provider ID or normalized address while
  preserving the earliest, strongest discovery level. Later responses may fill missing fields but
  cannot silently relabel a sale as preferred evidence.
- Every unique sale retains its preferred, expanded, or extended level, A-D fit grade, subdivision
  relationship, score, inclusion result, and explanation. Extended-only sales receive stronger
  distance and recency penalties and cannot receive an A or B grade.
- Search metadata records every query's radius, age and physical tolerances, returned and unique
  counts, duplicates, cumulative selected/rejected counts, subdivision support, provider errors,
  final level, shortage reason, and next action.
- If all provider levels remain thin, the analysis still saves the best available labeled evidence,
  marks the final level `manual`, and explains the exact shortage. It does not insert a listing,
  AVM value, or unsuitable property to reach the count threshold.
- A verified RentCast subject record plus screened closed sales can produce a provisional analysis
  when the AVM is unavailable. AVM fields and unsupported as-is value remain empty rather than
  being invented.
- Saved adaptive sales and search metadata are reused for repair changes and comp review. A fresh
  provider search occurs only when market data is explicitly refreshed.
- The lead Underwriting view and both PDF report types expose the search conclusion. The investor
  comparable table also prints each comp's grade, search level, and subdivision when available.
- Focused acceptance tests cover preferred stopping, controlled expansion, deduplication,
  subdivision expansion, complete evidence shortage, later provider outage, cache reuse, and
  AVM-unavailable continuity.

#### U3.3: Supporting Evidence And Manual Comps

**Status:** Implemented July 31, 2026.

- Add RentCast active/pending sale listings as separately labeled support.
- Add ZIP/market trend evidence for context and candidate time-adjustment research.
- Add manual closed-sale entry with source, verification, condition evidence, and duplicate checks.
- Preserve bounded public research and condition-source links.
- Keep optional future MLS/RESO or second-provider adapters behind the same normalized contract.

**Exit:** The operator can finish a defensible review when RentCast misses a known sale without
turning active listings, internet claims, or AVMs into fake closed comps.

Implementation record:

- Fresh provider runs collect nearby active sale listings from `/listings/sale` and ZIP-level sale
  market statistics from `/markets`. Both are normalized behind a provider-neutral supporting
  evidence contract and cached with the immutable analysis.
- RentCast currently documents `Active` and `Inactive` listing states, not a distinct pending
  search state. Stonegate retrieves active inventory and will preserve a provider-supplied pending
  label if a future approved adapter supports one; it does not relabel inactive inventory as
  pending.
- Supporting listings retain asking price, status, list date, days on market, physical facts, and
  source. ZIP context retains asking-price, price-per-square-foot, inventory, days-on-market, and
  history fields when supplied. These records are explicitly marked `supporting_only` and
  `excluded_from_arv_and_offer_math`.
- `UnderwritingManualComparable` stores one organization- and lead-scoped closed sale with address,
  closing date and price, physical facts, condition classification/evidence, verification source,
  source reference/link, verification notes, creator, status, and audit timestamps.
- Authorized users add or void manual sales from the existing lead Valuation & Offer workspace and
  choose which active records participate in the next analysis. Voiding affects future analyses;
  prior saved analyses remain immutable.
- Manual entry rejects the subject property, future closing dates, duplicate active manual sales,
  and sales already present in the latest provider evidence. Analysis-time deduplication also
  prefers the provider record if a later provider refresh returns the same address and closing
  date.
- Included manual sales enter the existing recorded-sale scorer as `manual_verified` core evidence.
  They use the same physical and outlier screening, carry a Manual search label and source warning,
  and cannot receive an A or B grade. A source-verified record is not automatically a good comp.
- Active listings, ZIP statistics, public research, and AVM output never enter the comparable list
  or offer formulas. They appear in a separate OS section and separate PDF section with the same
  limitation.
- Cached repair changes and comparable reviews reuse provider evidence but re-resolve selected
  manual records from the database. This prevents stale or voided evidence from being silently
  copied into a new analysis.
- API acceptance coverage proves sparse provider evidence can be supplemented by verified manual
  closings while an active listing remains outside the comp set. It also covers persistence,
  source retention, duplicate rejection, report output, removal, provider requests, and normalized
  market context.

#### U3.4: Comparable Review Workbench

**Status:** Implemented July 31, 2026.

- Recompose the current comp table into a side-by-side subject and candidate review workspace.
- Show grade, search level, raw sale, adjusted indication, distance, direction, sale date, physical
  differences, condition evidence, source, and inclusion rationale.
- Provide focused filters and a map/location view when an approved map source is available.
- Recommend a final set while keeping include/exclude/reweight authority with the reviewer.
- Hide advanced evidence until requested and keep the decision summary visible.

**Exit:** Austin can identify, verify, and explain the final comp set without moving among unrelated
pages or decoding provider fields.

Implementation record:

- The existing immutable comp-review endpoint remains the only review path. The workbench is a new
  operator interface over that versioned calculation and audit behavior, not a second valuation
  engine or parallel comp record.
- The API returns the saved canonical subject facts with the analysis. Provider sales retain
  coordinates when supplied, a calculated eight-point direction from the subject, and the engine's
  original selected/rejected status and rationale even after a reviewer changes the decision.
- A persistent subject band anchors the address, property type, subdivision, beds, baths, living
  area, year, and lot evidence. Every candidate shows raw closed price, subject-size indication,
  price per square foot, sale date, distance/direction, grade, search level, and a side-by-side
  physical comparison.
- All, Included, Excluded, grade, search-level, address/subdivision, and sort controls narrow the
  working set without removing any candidate from the decision payload.
- System Pick and System Excluded labels preserve the engine recommendation. Reviewer Changed
  identifies an inclusion override. Restore System Set returns inclusion decisions and weights to
  that recommendation without overwriting condition evidence.
- Include/exclude, truthful decision reason, condition classification, and 50-150% evidence weight
  remain reviewer-controlled. Applying still requires a decision for every source candidate and
  creates a new immutable analysis.
- Advanced rationale, warnings, condition evidence, verification notes, and source links remain
  collapsed until requested. The included/excluded/change summary and recalculation action remain
  visible in the workbench.
- The Location view plots provider-coordinate sales relative to the subject without adding a map
  vendor or claiming parcel/neighborhood boundaries. Sales without coordinates remain in the
  location evidence list with their available distance/direction.
- Desktop, 1024-pixel tablet, and 768-pixel layouts were checked without horizontal overflow. The
  lead detail workspace now moves its supporting sidebar below the primary work area at tablet
  widths so valuation evidence is not compressed.

#### U3.5: Market-Supported Adjustment Engine

**Status:** Implemented July 31, 2026.

- Retain V2.2 results for shadow comparison.
- Replace full price-per-square-foot scaling as the controlling transformation.
- Add governed time and marginal living-area adjustments only when evidence thresholds pass.
- Add condition, quality, lot, basement, garage, pool, or other feature adjustments only when the
  local evidence supports them.
- Detect collinearity/double counting, cap unsupported extrapolation, and store every rate/source.
- Rework confidence to include search expansion and adjustment support.

**Exit:** Every adjusted dollar is reproducible and sourced; unsupported cases remain usable with a
wider range instead of fabricated precision.

Implementation record:

- Every new analysis keeps the unchanged V2.2 ARV and offer calculation as live authority and saves
  a `v3.0-adjustment-shadow` comparison in analysis metadata. The shadow has no write path into
  ARV, buyer maximum, seller ceiling, opening offer, approvals, or contracts.
- The shadow begins each indication at the recorded closed-sale price. It does not use V2.2's full
  price-per-square-foot scaling as its controlling transformation.
- A market-conditions rate is applied only when at least four physically similar sales provide at
  least three local time-pair observations across at least 120 days. The saved evidence includes
  every pair, monthly rate, source comp key, method, sample count, and observed time span.
- A living-area rate is applied only when at least three sales provide at least three stable local
  matched-pair observations and meaningful area variation. The rate is a marginal contribution,
  not the average property price per square foot.
- Lot adjustments require their own stronger evidence and are withheld when lot area is strongly
  correlated with living area. Bedroom/bathroom adjustments are withheld while living area is used
  unless separate local evidence can prevent double counting.
- Garage, pool, and basement facts are normalized from RentCast county-record features. A feature
  adjustment requires the subject fact, at least three local sales with the feature, three without,
  and stable matched-pair evidence. Correlated feature rates cannot both be applied.
- Known as-is sales remain outside the ARV set. Condition and quality adjustments remain zero until
  consistently classified local paired sales support them; unknown evidence is never treated as a
  renovated fact.
- Time and physical differences cannot be extrapolated beyond the observed local pair range. Every
  comp stores the source rate, raw difference, applied difference, dollar component, total
  adjustment, adjusted indication, gross adjustment percentage, and review flag.
- Shadow confidence separately scores closed-sale depth, A/B comp quality, supported adjustment
  rates, search expansion, and indications needing extrapolation or magnitude review. Weak or
  expanded evidence widens the displayed shadow range instead of inventing a precise rate.
- Valuation & Offer now shows live V2.2 and shadow ARV side by side, supported/withheld rates, and
  expandable per-comp dollar math. The interface repeatedly labels the result as research only.
- Regression coverage proves the V2.2 golden results remain unchanged and covers supported living
  area/time rates, collinearity blocking, thin-market continuity, methodology control, API
  persistence, and read-back.

#### U3.6: Guided Repair Scope And Georgia Cost Catalog

**Status:** Implemented July 31, 2026; Georgia allowance calibration and operator acceptance remain.

- Extend repair items compatibly with status, severity, quantity/unit, ranges, source, uncertainty,
  override, and confirmation fields.
- Add `Unknown`, `No work`, `Repair`, `Replace`, and `Specialist review` controls.
- Build versioned component formulas and Georgia market factors.
- Preserve direct total and manual line-item amounts for experienced users and contractor bids.
- Add explicit unknown-component reserves and low/expected/high repair scenarios.

**Exit:** A user who does not know repair prices can create a transparent initial budget by stating
what needs work; manual estimates and immutable contractor evidence still work.

**Implementation record:**

- The existing repair-estimate record now accepts status, severity, quantity/unit, source,
  confirmation, uncertainty, override reason, system range, and catalog-version evidence. Existing
  manual items and contractor labor/material bids remain readable and retain their entered totals.
- The first server-authoritative catalog is `ga-2026.07-v1` for Georgia / Metro Atlanta. Its
  component allowances, minimums, quantity rules, and specialist flags are internal acquisition
  planning assumptions, not contractor quotes.
- Valuation & Offer provides touch-friendly `Not assessed`, `Unknown`, `No work`, `Repair`,
  `Replace`, and `Specialist review` decisions. Subject square footage and bathroom count supply
  explainable starting quantities where available.
- Every guided run saves low, expected, and high repair scenarios. Unknown work contributes a
  visible allowance and specialist warning instead of silently becoming zero.
- A manual price can replace the expected catalog amount only with a reason; the original system
  range remains attached for comparison.
- Saved internal scopes, walkthrough scopes, and contractor bids all feed the existing analysis,
  offer math, audit history, and PDF route. The investor PDF now prints the component decisions,
  range, evidence status, version, and items to verify without gating report generation.
- Regression coverage preserves the legacy V2.2 golden case and contractor report behavior while
  testing catalog ranges, unknown reserves, overrides, persistence, and read-back.

#### U3.7: AI Scope Assistance And iPad Walkthrough

**Status:** Implemented July 31, 2026; field acceptance and Georgia outcome calibration remain.

- Connect the existing Acquisitions Copilot to structured repair-scope suggestions.
- Use seller answers, calls, notes, inspection observations, and photos as cited inputs.
- Prefill only suggestions and visibly distinguish AI-proposed, user-confirmed, and
  walkthrough-verified facts.
- Upgrade the existing field inspection for fast touch controls, photo/voice capture, autosave,
  poor-connection recovery, and transfer into the existing repair estimate.
- Track AI acceptance, correction, misses, latency, and cost without granting pricing authority.

**Exit:** The iPad workflow creates a walkthrough-verified repair estimate without duplicate entry,
and no AI suggestion becomes a confirmed repair fact silently.

**Implementation record:**

- Calendar's existing appointment walkthrough now uses the same `ga-2026.07-v1` catalog and
  repair-item contract as lead underwriting. A closer records `Not sure`, `No`, `Repair`,
  `Replace`, or `Specialist review`, extent, quantity, optional exact price, and observed evidence.
- Draft edits debounce-save to the API and retain a local iPad backup. The interface distinguishes
  saved, saving, and offline recovery states; submission first flushes the current draft.
- Existing camera capture remains attached to the immutable field inspection. Browser dictation
  can append text to inspector notes; no separate audio or duplicate inspection record is created.
- `underwriting.analyze` is now a supervised Acquisitions Copilot repair-scope capability. It can
  read the appointment brief, seller/qualification facts, approved call notes, current
  underwriting, inspection observations, repair items, and photo metadata/captions. It does not
  receive raw photo bytes in this phase and cannot set a price, offer, or confirmed repair fact.
- Structured AI suggestions require Accept, Correct, or Reject review. Applying an accepted or
  corrected draft adds only missing categories, labels each row `AI proposed`, and leaves it
  `unconfirmed` / `not inspected` until the closer changes the observed work decision.
- The existing review records continue to measure acceptance, correction, rejection, latency,
  token cost, and estimated time saved. Applying a scope writes an audit event but performs no
  seller-facing action.
- Review and transfer evaluates the same field items into one low/expected/high scenario, stores
  them in the existing walkthrough repair estimate, and creates the existing draft underwriting
  version. Prior approved underwriting remains unchanged.

#### U3.8: Unified Valuation And Offer Workspace

**Status:** Implemented July 31, 2026; operator acceptance remains.

- Present Quick Comp, Desk Review, Walkthrough, and Offer Decision as progressive stages of one
  underwriting workspace.
- Make **Prepare valuation** the simple first action and show only the most valuable missing facts.
- Recalculate from the latest immutable evidence without repeating provider calls unnecessarily.
- Keep the focused offer summary visible while advanced math remains expandable.
- Link directly to appointment preparation, field inspection, approved offer plan, reports, and
  in-person contract signing already present in Stonegate.

**Exit:** One lead moves from preliminary analysis to approved negotiation authority without a
parallel record, duplicate repair scope, or unexplained number change.

**Implementation record:**

- The existing seller Valuation & Offer section now presents Quick Comp, Desk Review, Walkthrough,
  and Offer Decision as one progressive workflow. Status comes from the latest underwriting
  version, report stage, field evidence, and approved lead stage; no parallel valuation record was
  introduced.
- **Prepare valuation** is the first-run action. **Recalculate valuation** applies current saved
  repair and comp-review evidence while reusing the retained market snapshot; **Refresh market
  data** is a separate explicit action when new provider evidence is actually needed.
- The workspace surfaces only the first three highest-value missing lead facts above the analysis
  and links directly to the existing Property section for correction.
- A sticky decision summary keeps the current ARV range, repair range, buyer target, opening
  recommendation, and seller ceiling visible while version comparison and manual underwriting
  records remain under an expandable advanced section.
- The same workspace links to the existing appointment or scheduling flow, investor/client
  reports, offer approval and negotiation controls, and Contract & Deal signing flow.
- Responsive layouts stack the decision summary and convert the four-stage rail to two columns on
  narrow screens without creating a second mobile workflow.

#### U3.9: Reports, Explainability, And Calibration

**Status:** Implemented July 31, 2026; verified-outcome collection and operator acceptance remain.

- Update investor and client PDFs for search levels, comp grades, supported adjustments, repair
  scenarios, unknowns, evidence sources, and report stage.
- Keep internal economics and negotiation limits out of the client report.
- Add version comparison for changed comps, adjustments, repairs, and seller ceilings.
- Extend calibration by market, property type, search level, comp grade, repair category, and input
  verification stage.
- Add scorecards for comp yield, operator override burden, AI correction rate, and cost-catalog
  accuracy.

**Exit:** A saved report explains how Stonegate reached its conclusion, and later outcomes can show
which data source, rule, category, or human assumption caused a miss.

**Implementation record:**

- The investor PDF now retains report stage, search conclusion, comp grades and search levels,
  repair scenarios and unresolved work, evidence sources, and the complete V3 adjustment-shadow
  review. Supported and withheld rates, local sample/pair counts, live-versus-shadow comparison,
  and per-comp adjustment indications are labeled research-only and cannot change offer authority.
- The client PDF now shows seller-safe evidence strength, comp fit, search reach, preparation range,
  unresolved repair items, and the count of supported or withheld local adjustments. Internal buyer
  economics, assignment assumptions, offer recommendations, and seller ceilings remain excluded.
- Lead-detail underwriting versions now expose their linked immutable comp set, search level,
  repair-category snapshot, catalog version, and adjustment summary. The existing comparison shows
  added/removed comps, changed repair categories, adjustment support, and the headline dollar
  changes without creating another version record.
- Calibration now attributes verified outcomes by property type, adaptive search level, each comp
  grade present in the selected set, each active repair category, verification stage, and repair
  catalog version. Grade and repair-category segments may overlap because one analysis can contain
  several of each.
- The operating baseline now includes comp yield, operator override burden, reviewed Acquisitions
  Copilot repair-scope correction rate, and repair-catalog total-budget error against verified actual
  rehab outcomes.
- All scorecards remain descriptive. Samples below the governed threshold cannot activate a formula,
  provider, catalog, or autonomy change without the existing human methodology decision.

#### U3.10: Shadow Validation And Controlled Rollout

**Status:** Implemented controls July 31, 2026; paired production evidence, internal pilot
acceptance, and Owner activation approval remain.

- Replay V2.2 and V3 against redacted known deals before changing the default.
- Review at least 50 suitable cases overall and enough cases per initial Georgia market to avoid
  treating anecdotes as calibration.
- Test dense, suburban, rural, unique, low-comp, wrong-address, provider-failure, and high-risk
  repair scenarios.
- Require Owner acceptance of usability and an authorized methodology decision for activation.
- Roll out to internal users first, monitor errors and overrides, and retain V2.2 rollback/read
  compatibility.
- Keep all offer, contract, and methodology authority human-controlled.

**Exit:** V3 becomes the default only after it demonstrates better evidence coverage or accuracy
without increasing unexplained overrides, unsafe certainty, or operator effort.

Implementation record:

- Every verified outcome can now be tagged as dense-market, suburban, rural, unique-property,
  low-comp, wrong-address recovery, provider-failure recovery, or high-risk-repair evidence.
- Data & Quality pairs the immutable V2.2 conclusion and saved V3 adjustment shadow from the same
  analysis with the later verified ARV. It reports baseline error, shadow error, improvement,
  wins/ties/losses, evidence support, confidence risk, and market-level results.
- Controlled-rollout gates require 50 paired verified cases, at least 10 paired cases in every
  tracked Georgia market, all eight difficult scenarios, non-inferior median shadow accuracy,
  zero high-confidence unsupported conclusions, and enough operator review evidence without an
  override rate above 25%.
- A V3 rollout decision separately requires Owner usability acceptance, internal-pilot review,
  confirmed V2.2 rollback, and confirmation that offers, contracts, and methodology activation
  remain human-controlled. The API rejects approval while any evidence gate is incomplete.
- V2.2 remains the live method. V3 stays comparison-only until the real cohort passes and an
  authorized rollout decision is recorded; configuration still rejects premature V3 activation.
- Migration `0080_underwriting_shadow_replay` adds only validation-scenario evidence to the
  existing calibration case. Analyses, versions, outcomes, decisions, and offers remain the same
  authoritative records.

### Overall Definition Of Done

Underwriting V3 is implemented only when:

- the correct subject is verified before valuation
- the search adapts automatically and explains every expansion
- known good comps can be entered manually with evidence
- active listings and AVMs remain separate from closed-sale conclusions
- the final value no longer depends solely on full price-per-square-foot scaling
- a non-estimator can create a repair scope through component decisions
- every system repair price has a version, location, unit, range, and source
- unknown conditions create visible uncertainty rather than zero cost
- iPad evidence transfers without duplicate entry
- AI suggestions remain sourced, reversible, and human-confirmed
- investor and client reports agree with the saved immutable analysis
- offer ceilings remain approval-gated
- V2.2 history remains readable
- measured Georgia outcomes support the rollout decision

## Primary Sources

- RentCast property records: https://developers.rentcast.io/reference/property-records
- RentCast property data schema: https://developers.rentcast.io/reference/property-data-schema
- RentCast property valuation: https://developers.rentcast.io/reference/property-valuation
- RentCast property listings: https://developers.rentcast.io/reference/property-listings
- RentCast market data: https://developers.rentcast.io/reference/market-data
- RentCast long-term rent estimate: https://developers.rentcast.io/reference/rent-estimate-long-term
- Gordian RSMeans cost data: https://www.gordian.com/products/rsmeans-data-services/
- OpenAI Responses API web search:
  https://developers.openai.com/api/docs/guides/tools-web-search
- Fannie Mae comparable sales: https://selling-guide.fanniemae.com/sel/b4-1.3-08/comparable-sales
- Fannie Mae sales comparison approach: https://selling-guide.fanniemae.com/sel/b4-1.3-07/sales-comparison-approach-section-appraisal-report
- Fannie Mae comparable adjustments: https://selling-guide.fanniemae.com/sel/b4-1.3-09/adjustments-comparable-sales
- FHFA automated valuation model quality controls:
  https://www.fhfa.gov/regulation/federal-register/final-rule/quality-control-standards-for-automated-valuation-models
- RESO Data Dictionary: https://www.reso.org/data-dictionary/
