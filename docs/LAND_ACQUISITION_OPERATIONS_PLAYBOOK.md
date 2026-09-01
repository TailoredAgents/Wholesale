# Stonegate Land Acquisition Operations Playbook

**Effective repository date:** August 23, 2026

**Operating assumption:** Approximately 80% Land / 20% House initially, moving toward 50% / 50%

**Scope:** Land intake through qualification and valuation readiness

**Not authorization for:** Offer issuance, contract execution, closing, or Land disposition

**September 1 follow-up:** This playbook still does not grant that authority, but Stonegate now has
separate evidence-backed catch-up actions for an outside Land offer, an already-signed Land
agreement, an exact external investor packet, and asset-aware buyer-pool review.

## Purpose

Stonegate uses one CRM for House and Land opportunities, but it does not use one generic workflow.
Every record has an explicit asset class. Land records use parcel facts, Land seller questions,
Land research, and Land valuation. House questions, residential ARV, repair math, room inspections,
and House documents do not apply to Land.

Austin and Devon are full-cycle acquisition owners for assigned opportunities. A VA may source,
contact, and qualify a seller, but the assigned acquisition owner controls the next action,
valuation review, negotiation, and any later consequential decision.

## Source And Intake Rules

1. Every approved Land campaign must be explicitly mapped to **Land** before it can create CRM
   records. Every approved House campaign must be explicitly mapped to **House**.
2. An unknown, missing, or disabled campaign mapping is quarantined for manager review. The system
   must not guess the asset class.
3. An addressed parcel may enter with its street address. A parcel without a reliable street
   address may enter with APN, county, and state.
4. Existing records are not reclassified from House to Land unless retained source evidence proves
   the original campaign was an approved Land campaign.
5. Duplicate contacts or leads are not created merely because the asset is Land. Continue work in
   the existing Stonegate contact, Inbox thread, and lead record whenever identity matches.

## Daily Workflow

### 1. VA qualification

The VA opens the assigned Land prospect and uses the approved Land script. The VA records what the
seller actually says, marks unknown items as unknown, and never converts a guess into a fact.

The minimum seller interview covers:

- Ownership, title holders, and all decision-makers.
- Motivation, desired timeline, and asking price.
- APN and approximate acreage when known.
- Legal and practical access, road frontage, and easements.
- Utilities at the parcel, at the road, nearby, or unknown.
- Survey availability and known boundaries or corners.
- Septic, sewer, well, soil, and perc-test information.
- Seller-stated zoning, current use, intended use, and subdivision knowledge.
- Taxes, delinquency, HOA/POA, road fees, and known restrictions.
- Flooding, wetlands, drainage, slope, dumping, contamination, or other environmental concerns.
- Prior surveys, testing, permits, clearing, roads, wells, or improvements.
- Liens, probate, heirs, co-owners, and other title concerns.

When the seller is genuinely interested, the VA completes the approved qualified handoff. A
voicemail, no answer, wrong number, or unsupported disposition is not a qualified seller lead.

### 2. Acquisition-owner review

The assigned acquisition owner opens the lead and reviews the dedicated **Land acquisition
profile**. The profile separates:

- **Seller reported:** what the seller or staff recorded from a seller conversation. This is useful
  qualification evidence but remains unverified.
- **Provider screening:** property-record, zoning, tax, utility, flood, wetland, ownership, or other
  provider signals. These help identify research needs but are not proof of legal access,
  buildability, ownership authority, or a permitted use.
- **CRM record:** canonical parcel identity such as APN, county, and state.

If sources disagree, the fact remains visibly conflicted. The owner resolves the discrepancy from
the appropriate source instead of choosing the more favorable answer.

### 3. Complete seller information

Use the Land qualification editor and the profile's open-question list. Ask only unanswered Land
questions. Do not require property condition, room details, repair estimates, occupancy, or a
physical walkthrough merely because those are normal House fields.

An explicit **Not applicable** answer is different from **Unknown**. Use Not applicable only after
the seller or reviewer establishes that the question truly does not apply.

### 4. Research and diligence

Confirm the parcel identity before spending money on comparable searches. Review APN, county,
state, acreage, coordinates, land use, and the latest saved Land property-research snapshot.

Treat automated zoning, flood, wetlands, utility, soil, septic, access, and restriction results as
screening evidence unless the record cites an authoritative source at the required evidence level.
Missing provider data remains unknown; it does not mean clear, absent, buildable, or available.

### 5. Readiness decision

The Land profile can show:

- **Needs seller information:** required seller questions remain unanswered.
- **Needs diligence review:** the seller interview is complete, but unknown or conflicting facts
  still require independent research.
- **Ready for valuation review:** the qualification record is complete enough for an acquisition
  owner to review saved parcel and comparable evidence.

**Ready for valuation review is not offer approval.** It does not authorize an offer, contract,
signature, marketing package, or disposition activity. Existing identity, evidence, access,
valuation, policy, and human-approval gates remain in force.

### 6. Remote-first next action

Phone or video parcel review is the normal Land path. Schedule an in-person visit only when access,
road condition, terrain, drainage, dumping, boundaries, improvements, seller interaction, or
material offer risk justifies it. A Land opportunity is not incomplete merely because it has no
physical appointment.

Record a concrete next action and due date before leaving the lead. Follow-up continues according
to seller timing until the lead is closed out, disqualified, or moved forward under an approved
process.

## Data Rules

1. Seller statements are lead-scoped. Do not copy one seller's statements to another opportunity
   that happens to reference the same parcel.
2. Canonical APN, county, and state stay on the Property record.
3. Provider research stays in versioned Property Intelligence evidence.
4. Seller-reported Land facts stay in the versioned `qualification_context.land_acquisition_v1`
   namespace. Legacy Land keys remain readable during migration.
5. Unknown values remain unknown. No workflow may transform missing data into absent, clear,
   verified, buildable, or available.
6. House and Land research snapshots, comparable evidence, valuation methods, and execution paths
   remain isolated.

## Manager Quality Review

Managers should sample Land records weekly and verify:

- Campaign-to-asset mappings are complete and correct.
- Qualified handoffs contain an interested seller rather than voicemail or no-answer activity.
- Seller answers are specific enough to be useful and unsupported fields remain unknown.
- Provider screening is not presented as seller confirmation or official proof.
- Open questions, conflicts, next actions, and due dates are visible.
- In-person appointments are used selectively rather than as a default qualification gate.
- House ARV, repair, generated/e-signed contract, and residential outreach tools remain blocked for
  Land. External signed-contract evidence and the asset-aware Disposition package/Buyer pool are
  available through their separate governed workflows.
- KPIs are segmented by House/Land, source, campaign, and lead temperature before staff are compared.

## Activation Boundary

`LAND_WORKFLOW_ENABLED` remains the production kill switch. Keep it disabled until the owner has
approved the pilot scope and the current migration, campaign mappings, scripts, staff acceptance,
real-parcel checks, provider cost limits, and monitoring have passed. Full Land execution still
requires the later roadmap gates for authoritative diligence, valuation calibration, counsel-
approved documents, transaction controls, buyer matching, and disposition.
