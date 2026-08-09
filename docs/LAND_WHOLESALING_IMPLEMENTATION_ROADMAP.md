# Stonegate House And Land Wholesaling Implementation Roadmap

Last updated: August 8, 2026

## Decision

StonegateOS remains one operating system for both house and land wholesaling. Land will not receive
a separate CRM, Inbox, Calendar, buyer database, deal pipeline, worker, or AI system. Every
opportunity carries an explicit `asset_class` of `house` or `land`; qualification, research,
valuation, site work, contracts, and buyer matching adapt to that class while the shared lifecycle
remains unchanged.

The common lifecycle is:

`Lead arrives -> research -> contact and follow-up -> appointment -> offer -> contract -> buyer -> closing`

`property_type` remains the detailed physical classification, such as `single_family`,
`mobile_home`, or `land`. It is not the workflow discriminator. Existing Stonegate records default
to `house` so this upgrade does not silently change current operations.

## Non-Negotiable Invariants

1. Existing House behavior remains operationally unchanged.
2. House research, comps, valuation, and reports must never be reused for Land, or vice versa.
3. Land never uses residential ARV, rehab, room, or price-per-living-square-foot math.
4. Automated flood, wetlands, soil, zoning, utility, access, and similar results are screening
   evidence unless a qualified human verifies them.
5. Stonegate never represents automated research as proof that a parcel is buildable.
6. Provider AVMs are benchmarks, not substitutes for saved comparable-sale math.
7. Offers, contracts, external outreach, buyer selection, and other consequential actions retain
   their current human-approval boundaries.
8. Land workflows can be disabled without deleting records or reverting database migrations.
9. DealMachine is not a dependency for the Land launch.
10. Work is performed only on `main`; implementation remains uncommitted and unpushed until the
    owner requests otherwise.

## Stage 0 - Safety, Baseline, And Rollback

### Work

- Preserve and validate the existing uncommitted Inbox upgrade as a separate scope.
- Add `LAND_WORKFLOW_ENABLED=false` and readiness reporting.
- Record the domain and cache-isolation decisions in durable documentation.
- Preserve the current House test suite as the regression baseline.

### Exit Criteria

- The existing API and web checks pass.
- Land behavior is disabled by default.
- No unfinished Land path can affect production House leads.

## Stage 1 - Shared Asset And Property Identity Foundation

### Work

- Add `asset_class` to Campaign, Prospect, and Lead with `house|land` validation and a `house`
  backfill/default.
- Add asset scope to Prospecting and Lead Manager qualification script versions so one approved
  House script and one approved Land script can coexist.
- Add versioned `qualification_context` JSON to Lead for strategy-specific seller statements.
- Add canonical parcel/APN identity to Property.
- Permit a Land property to use a complete street address or a parcel-first identity consisting of
  APN, county, and state.
- Add `research_profile` to property snapshots and research runs.
- Add `valuation_profile` to market analyses and underwriting versions.
- Add structured criteria metadata to Buyer criteria.
- Make property identity signatures, freshness checks, invalidation, and idempotency profile-aware.

### Exit Criteria

- Every active opportunity resolves to House, Land, or an explicit review state.
- Existing records resolve to House without manual edits.
- Addressed and parcel-only Land records have stable, non-colliding identities.
- House and Land snapshots cannot cross-reuse.

## Stage 2 - Intake, Prospecting, And Handoff Propagation

### Work

- Propagate `asset_class` through manual entry, public intake, Facebook/Zapier, Inbox conversion,
  inbound-call conversion, imports, VA prospecting, warm handoff, duplicate review, and audits.
- Default existing public and Facebook house funnels explicitly to House.
- Let a Land campaign stamp imports, prospects, handoffs, and resulting leads as Land.
- Add House/Land badges, URL filters, and counts to Leads and related work queues.
- Include Land context in staff lead SMS alerts.
- Keep one Leads navigation item and one seller conversation timeline.

### Exit Criteria

- A VA Land campaign creates a Land CRM lead without re-entry.
- Existing Facebook/Zapier submissions create House leads unless explicitly mapped to Land.
- Inbox and manual conversions can choose House or Land.
- Attribution and duplicate history remain intact.

## Stage 3 - Qualification, Calls, Follow-Up, And AI Context

### Work

- Create separate approved House and Land VA/Lead Manager scripts.
- Store seller-reported Land facts in `qualification_context`, separate from provider research.
- Cover ownership, motivation, timeline, price, acreage, APN, access/frontage, utilities, survey,
  septic/perc, taxes, HOA/restrictions, prior testing, and known concerns.
- Extend Call Intelligence's strict structured schema and evidence mapping for Land.
- Auto-populate only empty CRM fields from transcript-supported facts.
- Render notes in Inbox, lead Summary, Activity, timeline, and AI context.
- Make Lead Manager, Prospecting, Acquisitions, and follow-up copilots use asset-specific gaps and
  questions.

### Exit Criteria

- Land qualification does not require house repairs, rooms, or living-area facts.
- A completed Land call produces evidence-backed notes and fills appropriate empty fields.
- House call extraction and follow-up behavior remain unchanged.

## Stage 4 - Land Property Intelligence

### Work

- Dispatch property research by profile: House keeps the current path; Land uses a dedicated
  Land-intelligence path.
- Support address-first and APN-first provider resolution.
- Reuse and extend RealEstateAPI normalization for APN, legal description, acreage, zoning, water,
  sewer, assessed land value, taxes, sale history, owner evidence, and optional imagery.
- Add reliable official screening evidence for flood, wetlands, soils, slope, septic, access,
  utilities, zoning, and county records where machine-readable sources support it.
- Save every fact with source, observation time, freshness, conflict state, and
  `unknown|screened|verified` status.
- Use the existing map and make imagery optional.
- Calculate Land-specific completeness and confidence.

### Exit Criteria

- A Land research run produces one reusable snapshot without duplicate paid calls.
- Partial results and provider failures remain visible and actionable.
- The interface does not imply unsupported buildability.

## Stage 5 - Land Comparable Math, Valuation, And Offer Governance

### Work

- Add a dedicated deterministic Land valuation service and a sibling Land valuation workspace.
- Never route Land through residential V2/V3 ARV and repair math.
- Select closed-sale evidence by use/zoning, acreage, buyer market, geography, access, utilities,
  environmental/topography signals, recency, and arms-length evidence.
- Support price per acre and price per lot with explicit acreage-ratio tiers. Version 1 applies no
  unsupported acreage multiplier; the saved adjustment factor remains `1.0` until Stonegate has
  reviewed calibration evidence for a different policy.
- Make building square footage optional for Land manual comps while preserving House validation.
- Produce supported retail range, quick-sale buyer range, assignment target, closing/title reserve,
  curative reserve, uncertainty reserve, opening guidance, seller ceiling, and confidence.
- Keep provider estimates as benchmarks only.
- Block or escalate actionable guidance when APN, acreage, legal access, or adequate evidence is
  missing.
- Persist immutable versions and update reports, comparison, calibration, and approval payloads
  without labeling Land values as ARV.

### Exit Criteria

- Every Land value and offer output is reproducible from saved evidence.
- Sparse or unsafe cases fail closed or require explicit human review.
- Existing House golden/regression behavior remains unchanged.

## Stage 6 - Calendar And Land Site Visits

### Work

- Add a color-coded Land site-visit appointment to the shared Calendar.
- Branch the field workspace by asset class.
- Capture parcel confirmation, access, frontage, utilities, terrain, drainage, surrounding uses,
  dumping/environmental concerns, boundary markers, signs, restrictions, photographs, seller
  discussion, and outcome.
- Do not require room observations or create a repair estimate for Land.
- Transfer Land observations and photographs into the saved property/valuation evidence chain.

### Exit Criteria

- A Land appointment can be scheduled, completed, photographed, and transferred to underwriting.
- House walkthrough and repair workflows remain unchanged.

## Stage 7 - Contracts And Transaction Controls

### Work

- Scope contract templates by asset class.
- Add APN, legal-description, and Land-diligence merge fields.
- Require title, access/easement, survey, zoning/use, utilities, septic/perc when applicable,
  environmental screening, taxes/liens, due-diligence, and closing-attorney checklist items.
- Block Land e-signature until a counsel-approved Georgia vacant-land agreement/addendum and the
  required parcel identity are active.
- Reuse the existing Deal, Transaction, assignment, reconciliation, and accounting lifecycle.

### Exit Criteria

- Stonegate cannot silently send its residential agreement for Land.
- An approved Land contract can proceed through title, assignment, buyer deposit, and closing.

## Stage 8 - Buyers And Dispositions

### Work

- Add Land investor/developer/adjacent-owner categorization and structured criteria for county,
  ZIP, acreage, zoning/use, access, utilities, price, and price per acre/lot.
- Make buyer ranking asset-aware and prevent House-only buyers from qualifying for Land deals.
- Produce a Land package containing property/parcel identity, APN, acreage, map, legal description,
  zoning/use screening, access, utilities, flood/wetland flags, taxes, comps, pricing, photographs,
  and unresolved diligence.
- Reuse the existing proof-of-funds, engagement, offers, primary/backup selection, campaign,
  approval, and reconciliation records.
- Launch with manually verified buyers; treat RealEstateAPI cash-land-buyer discovery as a later,
  separately previewed, cost-controlled enhancement.

### Exit Criteria

- A contracted Land deal can be packaged, matched, offered, assigned, and closed in the existing
  Deals workspace.
- DealMachine is not required.

## Stage 9 - Verification, Pilot, Deployment, And Documentation

### Work

- Add migration/backfill, intake, profile-isolation, provider-credit, comp math, sparse-market,
  calls, AI, field workflow, buyer matching, contract, permission, and responsive UI coverage.
- Run API lint, strict type checking, the full API suite, web lint, OS/underwriting contract audits,
  and the production web build.
- Deploy migration, API, worker, and web with Land disabled.
- Run controlled addressed and parcel-only internal Land records.
- Enable a three-county Georgia pilot and compare Stonegate results against human underwriting.
- Monitor provider cost, research failures, qualification quality, conversion, contract, buyer
  coverage, assignment spread, and time-to-close.
- Enable automatic Land research for production VA handoffs only after acceptance.
- Update System Map, User Manual, Operating Model, AI documentation, setup references, and the
  Land valuation methodology.

### Exit Criteria

- A VA Land opportunity completes this path inside Stonegate:

  `Land lead -> staff alert -> parcel research -> qualification -> call notes -> follow-up ->`
  `valuation -> site visit -> approved offer -> contract -> buyer package -> assignment -> close`

- Existing House operations pass their full regression suite.
- Disabling the Land feature immediately removes unfinished Land actions without deleting data.

## Owner-Provided Launch Gates

These items do not block early implementation, but they block live Land activation:

1. The initial three-county Georgia pilot and buy-box boundaries.
2. Controlled real parcels for provider and valuation acceptance.
3. A counsel-approved Georgia vacant-land purchase agreement or addendum.
4. The live VA campaign/list source and final handoff mapping.

## Progress Log

The implemented Land value and cost-control rules are documented in
[`LAND_VALUATION_METHOD.md`](./LAND_VALUATION_METHOD.md).

Safety checkpoint completed August 8, 2026: Land records now receive a clear `409` guard if any
residential ARV, comp, repair, offer-approval, negotiation, field-walkthrough, acquisitions-copilot,
valuation-report, residential transaction/package/e-signature, house-buyer disposition, or
in-person house-signing path is invoked. The Leads, Pipeline, valuation, Files, underwriting queue,
appointment, contract, and deal workspaces also hide or clearly quarantine incompatible House
actions and legacy House evidence. Legacy execution records remain readable and cancellable for
audit, but cannot advance. These guards remain in place until the corresponding Land stage is
implemented and verified.

- [x] Stage 0 - Safety, baseline, and rollback
- [x] Stage 1 - Shared asset and property identity foundation
- [~] Stage 2 - Intake, prospecting, and handoff propagation (primary manual, public,
  Facebook/Zapier, Inbox, campaign, import, VA, filter, and alert paths complete)
- [x] Stage 3 - Qualification, calls, follow-up, and AI context
- [~] Stage 4 - Land Property Intelligence (profile-safe address/APN RealEstateAPI facts path,
  county-scoped parcel identity, conflict checks, and paid-call cache are complete; official
  flood, wetland, soil, slope, septic, utility, access, zoning, and county screening sources
  remain)
- [~] Stage 5 - Land comparable math, valuation, and offer governance (deterministic saved-sale
  math, one-call explicit search, zero-call review, immutable versions, fail-closed access and
  evidence gates, versioned owner offer policy, property-profile overlay, API, and CRM workspace
  are complete; manual Land comps, report/calibration output, and consequential offer approval
  integration remain)
- [ ] Stage 6 - Calendar and Land site visits
- [ ] Stage 7 - Contracts and transaction controls
- [ ] Stage 8 - Buyers and dispositions
- [ ] Stage 9 - Verification, pilot, deployment, and documentation
