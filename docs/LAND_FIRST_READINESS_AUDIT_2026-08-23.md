# Land-First Readiness Audit

**Date:** August 23, 2026

**Status:** Readiness audit plus Phase 1 ingress remediation; not authorization to activate production Land execution

**Near-term operating target:** Approximately 80% Land / 20% House

**Later operating target:** Approximately 50% Land / 50% House

## Executive conclusion

Stonegate should continue using one operating system and one CRM for House and Land opportunities. The repository already has the correct foundation for that model: explicit asset classes, isolated House and Land profiles, asset-aware scripts and call intelligence, parcel-first Land research, a deterministic closed-sale Land valuation workflow, and guards that prevent Land records from entering House-only execution paths.

The system is ready for a controlled **Land lead intake, qualification, research, and valuation pilot**. It is not yet ready to run the complete Land wholesaling lifecycle without manual controls. The largest unfinished areas are official diligence evidence, dedicated Land field work, approved offer and contract execution, e-sign and transaction workflows, Land buyer matching and disposition, and production acceptance using real parcels.

The most urgent technical blocker identified by this audit was the direct BatchDialer handoff. Phase 1 now adds an explicit, organization-scoped provider-campaign-to-asset mapping, requires House or Land selection for Stonegate-created campaigns, preserves BatchDialer APN/county identity when available, and quarantines qualified handoffs from unmapped campaigns before CRM mutation. The remaining production step is to deploy the migration and classify every active BatchDialer campaign in Prospecting -> Analytics. Acreage and richer Land lead-sheet evidence remain follow-on enrichment work. An 80%-Land operating model must never rely on a source-name guess or a global Land default.

The repository and Render Blueprint currently default `LAND_WORKFLOW_ENABLED` to `false` for both the API and worker. That is the correct safe default until the launch gates in this document have been satisfied and the owner explicitly authorizes activation.

## Scope and evidence

This audit reviewed the repository implementation and its operating documentation. The Phase 1 remediation described below subsequently changed repository code and tests, but did not change live configuration, live data, or credentials.

Targeted regression coverage was run from `apps/api`:

```text
uv run pytest tests/test_assets.py tests/test_asset_prospecting.py \
  tests/test_land_call_intelligence.py tests/test_land_workflow_guards.py \
  tests/test_land_underwriting.py tests/test_property_intelligence.py -q

30 passed
```

Warnings were present, but none of the targeted tests failed.

## As-built capability matrix

| Capability | Current state | Evidence | Readiness judgment |
| --- | --- | --- | --- |
| One CRM with explicit House/Land separation | Built | `apps/api/app/domain/assets.py`; migrations `0091_unified_asset_foundation.py` and `0092_land_identity_and_valuation.py` | Ready as the architectural foundation |
| Asset-profile isolation | Built | `apps/api/app/domain/assets.py` | Ready; must remain a non-negotiable invariant |
| Land feature flag | Built, default off | `apps/api/app/core/config.py`; `render.yaml` | Ready as a kill switch; live-state alignment must be verified before activation |
| Native Stonegate campaign/import/handoff asset propagation | Built and tested | `apps/api/tests/test_asset_prospecting.py` | Ready for sources that use this path |
| Direct BatchDialer asset propagation | Phase 1 implemented; deployment/classification pending | `apps/api/app/services/batchdialer_direct.py`; `apps/api/app/services/batchdialer_campaign_mapping.py`; migration `0112_batchdialer_campaign_asset_mapping.py` | Ready to deploy, then every active campaign must be explicitly classified |
| Parcel-first Land identity | Built at the domain/valuation layer | `apps/api/app/domain/assets.py`; migration `0092_land_identity_and_valuation.py` | Ready, but source adapters must preserve APN/county/state |
| Asset-specific qualification and scripts | Built | `apps/api/tests/test_land_call_intelligence.py`; `apps/api/app/services/lead_manager_copilot.py` | Ready for a pilot after staff acceptance |
| Land call intelligence and note mapping | Built | `apps/api/tests/test_land_call_intelligence.py` | Ready for a pilot; production transcript quality should be sampled |
| Land subject-property research | Built | `apps/api/app/services/property_intelligence.py`; `apps/api/tests/test_property_intelligence.py` | Ready for a pilot with provider cost controls |
| Residential AVM/comp isolation for Land | Built and tested | `apps/api/tests/test_property_intelligence.py`; `apps/api/tests/test_land_underwriting.py` | Ready; regression guard must remain |
| Deterministic Land closed-sale valuation | Built | `apps/api/tests/test_land_underwriting.py`; `docs/LAND_VALUATION_METHOD.md` | Ready for controlled analyst use, not autonomous offer issuance |
| Immutable valuation versions and paid-call reuse | Built | `apps/api/tests/test_land_underwriting.py` | Ready; monitor cache correctness and provider spend |
| Manual Land comparable workflow | Not complete | `docs/LAND_VALUATION_METHOD.md` | Required before broad production use |
| Official flood/wetland/soil/slope/access/utility/zoning evidence | Not complete | `docs/LAND_WHOLESALING_IMPLEMENTATION_ROADMAP.md` | High-priority diligence gap |
| Land-specific site-visit workflow | Not complete | Land roadmap; current field workspace is guarded | Required only where remote diligence is insufficient |
| House-only execution guards | Built and tested | `apps/api/app/services/leads.py`; `apps/api/app/services/transactions.py`; `apps/api/tests/test_land_workflow_guards.py` | Ready and necessary |
| Land offer approval and reporting | Partial | `docs/LAND_VALUATION_METHOD.md` | Not ready for consequential offers |
| Counsel-approved Land contract/e-sign/checklist | Not complete | `docs/LAND_WHOLESALING_IMPLEMENTATION_ROADMAP.md` | Launch blocker for contract-to-close automation |
| Land buyer criteria, matching, package, and disposition | Not complete | `docs/LAND_WHOLESALING_IMPLEMENTATION_ROADMAP.md` | Launch blocker for end-to-end disposition |
| Land-aware AI assistance | Partial | `apps/api/app/services/ai.py`; House guards in acquisition/transaction copilots | Useful context exists, but execution copilots are not Land-ready |
| Asset-segmented performance reporting | Partial | `apps/api/app/services/acquisition_performance.py` | Needs normalization before comparing mixed House/Land workloads |
| Production pilot and acceptance | Not complete | Land roadmap | Required before broad activation |

## Severity-ranked findings

### Critical

#### C1. Direct BatchDialer leads could silently become House leads - remediated in Phase 1

Before Phase 1, the direct BatchDialer integration normalized address fields and provider campaign data, but its handoff omitted `asset_class`, property type, APN, county, and acreage. Public intake could therefore derive an otherwise valid Land opportunity as House.

Relevant implementation:

- `apps/api/app/services/batchdialer_direct.py` - fail-closed mapping resolution, Land identity validation, normalization, and handoff.
- `apps/api/app/services/batchdialer_campaign_mapping.py` - manager mapping, audit history, held-event requeue, and historical mismatch visibility.
- `apps/api/app/services/public_intake.py` - lead creation and fallback around lines 1813-1842.
- `apps/api/app/schemas/public_intake.py` - intake fields and defaults around lines 195-204.
- `apps/api/app/models/foundation.py` and migration `0112_batchdialer_campaign_asset_mapping.py` - nullable fail-closed campaign mapping with mapper and timestamp evidence.
- `docs/BATCHDIALER_API_CONTRACT.md` - lead-sheet support is not proven around lines 75-101.

**Current disposition:** Implemented in repository code. Unknown, missing, or invalid mappings are quarantined as non-overridable review items before provider enrichment or CRM creation. Saving a mapping requeues only events held for a mapping reason. Parcel-only Land can enter with APN, county, and provider state without a fabricated House address. Previously created leads are never silently rewritten; mismatch counts and sample records are shown to managers. Production still requires migration deployment and explicit classification of all active campaigns. Acreage and richer lead-sheet preservation remain open enrichment work.

### High

#### H1. The full Land execution lifecycle is intentionally unfinished

The current system does not yet provide official diligence evidence, a dedicated Land site workflow, approved offer issuance, a counsel-approved Land contract and transaction checklist, or Land buyer disposition. House-only guards correctly prevent accidental reuse of residential execution paths.

**Required disposition:** Keep those stages manual or blocked until their dedicated phases and launch gates are complete.

#### H2. Land is disabled by repository defaults

`LAND_WORKFLOW_ENABLED` defaults to `false` in the application and Render Blueprint for both API and worker services.

**Required disposition:** Keep the default off. When the pilot is authorized, change API and worker together, verify live environment alignment, and use a canary scope rather than enabling every source and market at once.

#### H3. Official diligence coverage is insufficient for consequential decisions

The research profile does not yet have authoritative, standardized evidence adapters for flood, wetlands, soils/septic, slope/topography, legal access/frontage, utilities, zoning, and county-specific restrictions.

**Required disposition:** Add evidence with source, retrieval time, match confidence, status, conflicts, freshness, and cost. Unknown must remain unknown; provider absence must never be treated as a clean result.

#### H4. Valuation is not yet calibrated for broad offer automation

The deterministic valuation foundation is strong, but manual Land comps, reporting, sparse-market policy, real-parcel calibration, and consequential offer approval remain unfinished.

**Required disposition:** Use valuation as analyst support during the pilot. Do not let AI or a provider benchmark autonomously set or transmit an offer.

#### H5. Legal and disposition paths are not Land-ready

No counsel-approved Land template, merge-field contract, e-sign flow, Land transaction checklist, Land buyer criteria, or disposition package has completed acceptance.

**Required disposition:** Treat signed-contract and disposition automation as closed launch gates, not post-launch polish.

### Medium

#### M1. Current operating documentation conflicts with the intended staffing model

Several manuals still describe Devon as Lead Manager and Austin as the closer, with a formal handoff between them. The intended current model is that Austin and Devon each own assigned acquisition opportunities from response through contract, with backup coverage.

**Required disposition:** Publish one current ownership rule and update all role manuals together.

#### M2. KPI comparisons can punish the person receiving the harder asset/source mix

Existing acquisition performance logic includes House-shaped CRM hygiene assumptions. Raw speed, conversion, appointment, and valuation statistics are not directly comparable when one person receives more Land, sparse-data, cold, or out-of-market records.

**Required disposition:** Segment by asset, source, campaign, market, and lead temperature; normalize before producing individual rankings or blended scores.

#### M3. AI readiness is narrower than the roadmap implies

Land context exists in `apps/api/app/services/ai.py`, but Acquisitions Copilot is blocked for Land and transaction/disposition copilots remain House-guarded.

**Required disposition:** Mark Land AI readiness as partial. Add asset-specific evaluation suites and explicit prohibited outputs before expanding automation.

#### M4. Remote-first Land operations are not yet codified end to end

Land often does not require an in-person appointment, but current operational materials are still appointment-led and House-centric.

**Required disposition:** Define phone/video parcel review, diligence, valuation, follow-up, and approval as the default Land path. Use field visits only for access, terrain, dumping, boundaries, seller meetings, or material offer risk.

### Low

#### L1. Documentation contains stale progress labels and encoding defects

The BatchDialer roadmap still says implementation is in progress despite most implementation phases being marked complete, historical readiness fields are easy to misread as current, and a few documents contain mojibake.

**Required disposition:** Correct these during the documentation truth-reset phase.

## Operating decisions for an 80% Land / 20% House mix

### Business and ownership model

1. Keep one OS and CRM, with explicit asset-aware behavior rather than separate systems.
2. Keep Austin and Devon as full-cycle acquisition owners for their assigned opportunities, from first response through contract readiness.
3. Assign within the asset-qualified Austin/Devon pool using a deterministic round robin plus capacity safeguards. Backup coverage must not silently change permanent ownership.
4. Do not globally default new records to Land. House Facebook and website funnels remain House unless that source is explicitly configured otherwise. Approved Land VA and BatchDialer campaigns map to Land.
5. An unknown source/campaign mapping goes to review. It does not become a House or Land lead by guesswork.

### Land acquisition standard

Every qualified Land record should visibly track:

- Ownership and all decision-makers.
- APN, county, state, and acreage.
- Motivation, selling timeline, and asking price.
- Legal and practical access, road frontage, and easements.
- Utilities at or near the parcel.
- Survey availability and boundary knowledge.
- Septic, sewer, well, and perc-test information.
- Zoning, intended use, and subdivision potential where relevant.
- Taxes, HOA/POA, deed restrictions, and known liens.
- Flood, wetland, topography/slope, and environmental signals.
- Prior testing, clearing, improvements, dumping, or encroachments.
- Title concerns and probate/heirship where disclosed.

Unknown answers remain explicit open diligence items. They must not be converted into positive assumptions.

### Appointments and field work

- Default to remote phone/video parcel review and diligence.
- Create an in-person appointment only when access, terrain, dumping, boundaries, seller interaction, or offer risk justifies it.
- A Land opportunity must not appear unqualified merely because it has no physical appointment.

### Queues, routing, and reporting

- Provide separate House and Land working queues and checklist semantics.
- Segment KPIs by asset, source, campaign, market, and lead temperature.
- Measure response and follow-up clocks from the moment a lead becomes actionable, not from a quarantined or incomplete provider event.
- Track provider costs and paid calls by asset, research run, and valuation version.
- Allow explicit comp searches only after the subject identity is accepted and the opportunity merits the cost.

### Controlled activation

Do not activate full Land execution until the pilot counties and buy box, exact BatchDialer mapping, staff scripts, real-parcel calibration, counsel-approved contract, and buyer/closing workflows are approved.

## Operating decisions for a later 50% Land / 50% House mix

1. Retain the same explicit asset model; do not merge House and Land scripts, comp methods, contracts, diligence, buyer criteria, or calibration.
2. Route within the asset-certified owner pool using capacity and round robin rather than a global alternating sequence that ignores workload.
3. Maintain separate House and Land KPI baselines. A blended executive score may be shown only when its weighting is visible.
4. Balance staffing using active actionable leads, due follow-ups, diligence burden, valuation work, appointments, and contracts - not raw lead count alone.
5. Recalibrate scoring and service-level expectations when source or asset mix changes materially.

## Phased implementation roadmap

### Phase 0 - Truth reset and live-state inventory

- Reconcile canonical documents with the current repository and operating model.
- Confirm live API and worker feature flags without changing them.
- Inventory every House and Land source, campaign, owner, script, provider, environment dependency, and blocked stage.
- Define pilot counties, Land buy box, exclusions, spend caps, and owner approval record.
- Record production baselines for House so later work can prove no regression.

**Exit:** One approved as-built map, one remaining-work roadmap, and one live-state checklist agree.

### Phase 1 - Ingress correctness and BatchDialer mapping

**Repository status:** Implemented on August 23, 2026; production deployment and active-campaign classification remain pending.

- Add mandatory organization-scoped mappings from provider campaign to explicit asset class.
- Treat linkage to a local Stonegate Campaign as an optional later enhancement; do not make it a classification dependency.
- Require manager approval for each active mapping.
- Quarantine unknown, renamed, deleted, duplicate, or ambiguous provider campaigns.
- Preserve asset class, APN, county, state, acreage, address, source, campaign, disposition, notes, and raw provider evidence.
- Add replay, rescan, pagination, partial-failure, and idempotency tests.
- Provide an operator reconciliation view for fetched, archived, qualified, quarantined, handed-off, duplicate, and failed records.

**Exit:** A known Land campaign creates only Land candidates/leads, a known House campaign creates only House candidates/leads, and unknown campaigns create neither until reviewed.

### Phase 2 - Daily Land acquisition operations

- Publish the Land qualification script and required evidence checklist.
- Add Land-specific queue labels, filters, next actions, follow-up semantics, and data-completion tasks.
- Implement full-cycle Austin/Devon ownership with backup coverage and auditable assignment.
- Support remote-first parcel-review appointments and selective field escalation.
- Train staff and complete role-based acceptance on desktop and mobile.

**Exit:** A VA or acquisition owner can move a Land lead from intake through qualified valuation readiness without using House questions or workarounds.

**Repository progress on August 23, 2026:** The Phase 2 implementation adds one canonical Land
acquisition profile to Land lead records, visibly separates seller-reported statements from
provider screening and CRM parcel identity, derives seller-information and conflict-aware
valuation-review readiness, and replaces House-shaped qualification prompts with Land questions.
The daily procedure and the no-offer-authority boundary are published in
`LAND_ACQUISITION_OPERATIONS_PLAYBOOK.md`. Production staff acceptance and real-parcel pilot
evidence remain required before this phase is treated as operationally accepted.

### Phase 3 - Official diligence evidence

- Add official or authoritative sources for flood, wetlands, soils/septic, slope/topography, access/frontage, utilities, zoning, taxes, and county restrictions.
- Store provenance, retrieval time, matched identity, confidence, freshness, cost, raw reference, and conflicts.
- Distinguish clear, present, absent, unknown, unsupported, stale, and conflicting states.
- Add manual fallback and county-specific escalation paths.

**Exit:** Consequential diligence fields are evidence-backed or explicitly unresolved.

### Phase 4 - Land valuation completion

- Add manual Land comparable entry and review.
- Complete sparse-market, zero-comp, acreage-band, road/access, utility, flood/wetland, zoning, and outlier policies.
- Produce a versioned valuation report/PDF with subject identity, selected and rejected comps, adjustments, range, confidence, caveats, provider costs, and analyst approval.
- Calibrate against real pilot parcels and known outcomes.
- Require human approval before any consequential offer guidance is sent.

**Exit:** Approved analysts reproduce the same result from the same saved evidence and can explain every material adjustment.

### Phase 5 - Selective Land site work

- Add a Land-specific field checklist for access, road condition, terrain, drainage, dumping, improvements, utilities, visible boundaries, neighboring uses, and photos.
- Transfer field evidence into the same immutable property profile and valuation version.
- Keep site work optional unless a material risk or operating policy requires it.

**Exit:** Field evidence improves the Land record without invoking House repair or room-based inspection workflows.

### Phase 6 - Offer, legal, and transaction execution

- Obtain counsel approval for the Land purchase agreement, addenda, disclosures, assignment language, and state/county variants.
- Implement versioned merge fields, offer approval, e-sign, audit trail, title/closing checklist, deposit, due diligence, extension, and cancellation controls.
- Prevent House templates from being selected for Land.

**Exit:** A test Land deal can move from approved valuation through signed contract and closing checklist with correct documents and audit evidence.

### Phase 7 - Land buyers and disposition

- Add Land buyer profiles for geography, acreage, zoning/use, access, utilities, price, closing speed, funding proof, and exclusions.
- Build deterministic candidate filtering and explainable ranking.
- Create a Land-specific marketing package and controlled outbound workflow.
- Track interest, offers, follow-ups, assignment, and closing outcomes.

**Exit:** A contracted Land deal can be matched and marketed without residential buyer assumptions.

### Phase 8 - Asset-aware AI and measurement

- Add Land-specific prompts, evaluations, prohibited outputs, evidence citations, and confidence rules.
- Prevent AI from inventing access, buildability, utilities, zoning, title, or offer authority.
- Segment acquisition, research, valuation, contract, and disposition metrics by asset and source.
- Normalize staff comparisons for workload and lead quality.

**Exit:** AI suggestions are evidence-linked and evaluators detect cross-asset leakage or unsupported claims.

### Phase 9 - Pilot, reconcile, and scale

- Run a three-county canary with approved campaigns and a small real-parcel set.
- Reconcile source -> intake -> lead -> research -> valuation -> offer -> contract -> buyer outcomes daily.
- Review provider spend, misclassification, duplicates, identity conflicts, staff usability, and House regressions.
- Expand toward the 80% Land mix only after owner sign-off.
- Rebalance toward 50/50 later using capacity and asset-specific economics rather than arbitrary volume.

**Exit:** All launch gates pass for a sustained acceptance window and rollback has been rehearsed.

## Migration and backfill plan

1. **Create mappings first.** Add a mandatory organization-scoped mapping from provider campaign ID and its stable identity evidence to an explicit asset class. Store approval status, approver, effective date, and audit history. A link to a local Stonegate Campaign may be added later as an optional operational enhancement; it is not required for the classification control.
2. **Do not rewrite existing defaults blindly.** Existing internal Campaign, Prospect, and Lead records remain House unless explicit retained evidence proves they originated from a mapped Land campaign or were manually classified as Land.
3. **Dry-run BatchDialer reclassification.** Produce counts grouped by provider campaign, current asset, proposed asset, lead state, APN completeness, owner, and downstream artifacts. No mutation occurs during the dry run.
4. **Review ambiguous records.** Renamed campaigns, missing campaign IDs, conflicting source fields, and records with residential downstream execution enter a review queue.
5. **Reclassify only from exact evidence.** A prior direct BatchDialer record may change House -> Land only when the retained event links to an approved mapping. Generic `property_type`, an address string, or seller notes alone are not sufficient for automated reclassification.
6. **Invalidate profile-dependent outputs safely.** When a record changes asset class, invalidate incompatible research snapshots, comp analyses, offer guidance, tasks, and AI outputs. Preserve old evidence and activity as read-only audit history.
7. **Rebuild Land evidence selectively.** Enqueue Land subject research only when the feature flag is enabled for the canary and parcel/address identity is usable. Paid comp work remains explicit.
8. **Backfill parcel identity conservatively.** Populate APN only from an exact APN + county + state source match. Do not parse an APN from placeholder or malformed address text.
9. **Backfill reporting dimensions.** Add asset/source/campaign dimensions to historical attribution without rewriting original timestamps or owner history.
10. **Version operational artifacts.** Scripts, policies, contracts, scorecards, and mappings are versioned; do not mutate historical versions in place.
11. **Make every batch reversible.** Record affected IDs, previous values, new values, reason, operator, timestamp, and run ID. Roll back by run ID, not by broad query.
12. **Reconcile after each batch.** Compare counts, identities, queue state, downstream guards, provider costs, and House baseline metrics before proceeding.

## Test and acceptance matrix

| Area | Required scenarios | Acceptance standard |
| --- | --- | --- |
| Schema and migrations | Upgrade/downgrade where supported, idempotent backfill, tenant scoping, existing House defaults | No cross-tenant or silent asset mutation |
| Batch campaign mapping | Known Land, known House, unknown, disabled, renamed, duplicate, deleted, conflicting mapping | Only approved exact mappings hand off; all ambiguity is visible |
| Polling resilience | Pagination, lookback overlap, replay, crash after fetch, crash after archive, rate limit, partial page failure | Exactly-once business effect with safe retry |
| Asset propagation | Public website, Facebook/Meta, native prospecting, CSV/import, Batch direct, manual entry | Asset remains explicit from source through lead and downstream profile |
| Parcel identity | Same APN across counties, missing APN, malformed APN, address mismatch, provider conflict | County/state scoped identity; conflicts block consequential work |
| Qualification | Land and House scripts, required questions, unknowns, owner handoff, notes | No cross-asset questions or silently completed unknowns |
| Call intelligence | Land transcript, House transcript, voicemail, bad audio, retry, structured field mapping | Correct asset schema; unsupported claims are not auto-populated |
| Research spend | Cache hit, cache miss, cap reached, retry, provider outage, automatic background run | Caps enforced; no automatic paid comp search; cost recorded |
| Official diligence | Clear, present, absent, unknown, stale, conflicting, unsupported county | State and provenance are explicit; absence is not inferred from no data |
| Land valuation | Determinism, manual comps, comp rejection, acreage differences, sparse/zero comps, outliers | Reproducible versioned math with fail-closed offer guidance |
| Cross-asset guards | Land repair estimate, House comp engine, House field workflow, House contract, House disposition | Every incompatible path remains blocked with a useful explanation |
| Site work | Remote-only, required visit, photos, conflicting observations, evidence transfer | No room/repair assumptions; evidence retained with provenance |
| Offer/legal | Approval limits, wrong template, missing merge fields, e-sign failure, cancellation/extension | Counsel-approved version only; complete immutable audit trail |
| Buyers/disposition | Geography, acreage/use exclusions, insufficient evidence, ranking explanation, duplicate buyer | Eligible Land buyers only; ranking is explainable |
| AI | Unsupported access/buildability claim, autonomous price/offer, wrong asset context, missing evidence | Prohibited outputs blocked; every claim linked to saved evidence |
| Roles and UX | VA, acquisitions owner, manager, admin; desktop and mobile | Least privilege, clear queues, no hidden consequential action |
| Reporting | House/Land/source/campaign splits, mixed workloads, quarantine clocks | Reconciles to source and does not mis-rank staff due to mix |
| Production acceptance | Real pilot parcels, active mapped campaign, 24-hour reconciliation, House regression suite | Zero silent misclassification or guard bypass; owner signs off |

## Launch gates

All of the following must pass before broad Land activation:

- [ ] Pilot counties, buy box, exclusions, and maximum provider spend are approved.
- [ ] API and worker live-state flags are documented and aligned.
- [ ] Every active Land BatchDialer campaign has an approved exact mapping.
- [ ] Unknown and ambiguous BatchDialer campaigns quarantine safely.
- [ ] Land qualification script and required diligence checklist are published.
- [ ] Austin and Devon complete role and workflow acceptance.
- [ ] RealEstateAPI and any official-data dependencies are configured with cost caps and monitoring.
- [ ] Official diligence thresholds and manual fallback rules are approved.
- [ ] Real pilot parcels confirm identity matching and Land valuation behavior.
- [ ] Sparse-market and no-comp behavior fails closed.
- [ ] Counsel approves the Land agreement, addenda, disclosures, and workflow.
- [ ] Buyer criteria, proof-of-funds handling, marketing package, and disposition ownership are approved.
- [ ] Closing attorney/title workflow, earnest money, diligence dates, extensions, and cancellation are documented.
- [ ] Asset-aware monitoring, reconciliation, and alerting are live.
- [ ] Rollback has been rehearsed in a non-production or canary scope.
- [ ] A 24-hour source-to-CRM reconciliation has zero unexplained records.
- [ ] The full House regression suite passes with no material workflow change.
- [ ] The owner gives written authorization for the exact activation scope.

## Rollback plan

### Kill switch and scope

- Keep `LAND_WORKFLOW_ENABLED=false` until the pilot is authorized.
- Enable the API and worker together and begin only with approved campaigns and pilot counties.
- The kill switch stops new Land automation and consequential actions; it must not delete or reclassify existing records.

### Rollback triggers

Immediately stop the canary for any of these conditions:

- Silent House/Land misclassification.
- Cross-profile evidence or comp reuse.
- Unexpected provider-spend increase or cap bypass.
- APN/county/state identity conflict.
- House-only guard bypass.
- Wrong contract/template selection.
- Duplicate handoff, lead, appointment, or task creation.
- Source-to-CRM reconciliation misses.
- Unsupported AI claim used in a consequential decision.

### Rollback actions

1. Disable Land automation in API and worker for the affected scope.
2. Stop new paid research and valuation jobs.
3. Quarantine new Land candidates and preserve their raw source events.
4. Preserve immutable snapshots, analyses, activity, approvals, and BatchDialer evidence.
5. Route active Land opportunities to a manual manager-review queue.
6. Do not relabel Land records as House to make them fit an existing workflow.
7. Leave the House path operational unless the incident is demonstrably shared.
8. Reconcile every affected record and provider charge by incident/run ID.
9. Correct the defect, rerun targeted and House regression tests, and repeat the canary acceptance window.
10. Re-enable only after the owner reviews the incident, correction evidence, reconciliation, and new scope.

## Documentation drift requiring correction

### `docs/SYSTEM_MAP.md`

The document presents itself as the canonical as-built system map but does not describe the Land workflow. Its lifecycle remains residential and appointment/repair oriented. It also contains an encoding defect near the early architecture section.

**Correction:** Add the unified asset model, source-to-asset propagation, Land identity/research/valuation, House-only guards, Batch direct limitation, and staged execution boundary.

### `docs/FINISHING_ROADMAP.md` and `docs/DOCUMENTATION.md`

The finishing roadmap contains no Land work. This phase updates the documentation guide to delegate Land remaining work to the Land roadmap and index the Land valuation method and this audit.

**Remaining correction:** Reconcile the finishing roadmap itself with the delegated Land roadmap so its global completion language cannot be mistaken for Land completion.

### `docs/OPERATING_MODEL.md`

The document predates Land and describes a local, appointment-led House lifecycle, Austin as closer, Devon as Lead Manager, and a formal Lead Manager-to-closer handoff.

**Correction:** Replace that staffing model with Austin and Devon as full-cycle acquisition owners for assigned opportunities, document backup coverage, and add remote-first Land operations plus the near-term 80/20 and later 50/50 planning assumptions.

### `docs/USER_MANUAL.md`

The early asset boundary is accurate, but later operating tables still describe comps/repairs and generic contract/disposition behavior as if it applied equally. The BatchDialer section is House-shaped and omits the direct campaign asset-mapping limitation.

**Correction:** Split House and Land instructions after qualification, explain current Land holding screens, and document mapped/quarantined Batch campaigns.

### `docs/STAFF_ROLE_MANUALS.md` and `docs/LEAD_MANAGER_USER_MANUAL.md`

These documents preserve the former Devon-to-Austin handoff and House-specific qualification questions.

**Correction:** Publish current ownership, asset-specific scripts, Land diligence, remote-first appointment rules, and escalation responsibilities.

### `docs/AI_AUTOMATION_ROADMAP.md`

The roadmap does not describe the asset-class model and its acquisition automation remains residential. Repository code provides some Land AI context, but Land execution copilots are guarded.

**Correction:** Mark Land AI readiness as partial, document allowed and prohibited Land outputs, and add evaluation/acceptance work before any roadmap phase is marked complete.

### `docs/BATCHDIALER_DIRECT_INTEGRATION_ROADMAP.md` and `docs/BATCHDIALER_API_CONTRACT.md`

The roadmap header says implementation is in progress while its ledger marks most phases implemented. Historical readiness fields in the API contract can be mistaken for current state.

**Correction:** Separate implemented code, production acceptance, and historical research clearly. Document the now-implemented provider-campaign mapping and the remaining production classification step.

### `docs/LAND_WHOLESALING_IMPLEMENTATION_ROADMAP.md`

The roadmap remains the strongest Land planning source, but a non-negotiable note about not pushing until requested is release-process history rather than durable architecture guidance.

**Correction:** Remove stale release-process language, reconcile completion marks with the narrower current AI and execution state, and link this readiness audit.

### `docs/LAND_VALUATION_METHOD.md`

The method accurately separates deterministic comp math from provider benchmarks and lists meaningful unfinished work. It contains a few encoding defects.

**Correction:** Fix encoding, keep the outstanding launch work explicit, and link valuation acceptance to real-parcel calibration and human offer approval.

## Final readiness statement

The current repository supports a credible Land-first pilot only if Stonegate preserves the feature flag, deploys the direct-source classification migration, explicitly maps every active campaign, limits the pilot to approved campaigns and counties, and treats research/valuation as decision support rather than autonomous offer authority. The system should not be described as end-to-end Land-ready until legal execution, buyer disposition, official diligence, production calibration, and acceptance have passed their gates.

The fastest safe route is not a second CRM or a global Land default. It is to deploy and operate the explicit source mapping now in the repository, operationalize the existing Land qualification/research/valuation foundation, and add each consequential execution stage behind its own evidence and approval gate.
