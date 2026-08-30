# Stonegate Buyer Network And Disposition Sidekick Roadmap

Last updated: August 29, 2026

> **Current status: DS0-DS8 complete; the DS9 repository implementation is complete but its
> measured pilot is NOT MET; the DS10 derived House management dashboard is implemented; live
> InvestorLift transport, expanded DS10 attribution/cost controls, and DS11-DS12 remain pending.** Stonegate now has the audited,
> provider-independent Buyer Network foundation described in DS1 and the role-scoped Disposition
> Desk described in DS2, plus the buyer profiles, independently versioned House and Land buy boxes,
> relationship follow-ups, reusable proof review, and asset-safe House matching described in DS3.
> DS4 adds the unified, explainable House deal buyer pool, staged external evidence, explicit
> external-to-network review, versioned score history, and shortlist-aware House release controls.
> DS5 adds the House-only, evidence-classified launch-readiness workspace; immutable package
> versions; approval-gated, stored investor PDFs; private-economics separation; material-change
> invalidation; and exact package-version linkage for prepared recipients. DS6 adds governed,
> House-only email and SMS outreach to selected buyers already in Stonegate's owned Buyer Network:
> immutable exact-message revisions, a 25 recipient-channel cap, separate human approval, dynamic
> eligibility checks, durable delivery state, and Buyer Inbox reply review. Existing deal-specific
> engagement and offer records, primary and backup buyer selection, reconciliation, and review-only
> Disposition Copilot remain in place. DS7 adds the governed House Offer Room, immutable offer and
> negotiation history, manager-approved primary and backup coverage, canonical closing checkpoints,
> deduplicated deadline escalation, controlled replacement, and evidence-based buyer outcomes.
> DS8 now adds an exact approved-package handoff, deterministic public-only payloads, manual
> InvestorLift link and activity reconciliation, staged human review, export, and history-preserving
> disconnect controls. DS9 adds a citation-gated, House-only, draft-only daily Copilot with four-way
> human review, immutable trace evidence, and explicit evaluation gates. Its production pilot has
> not met the required 50 decisive reviews across 10 cases. No direct InvestorLift API is claimed or
> enabled because its transport contract remains unverified. DS10 adds a read-only management view
> derived from canonical House disposition evidence while explicitly leaving campaign-cost,
> correction-capable attribution, and causal performance claims pending. Land outreach and
> DS11-DS12 remain plans. DS6
> repository completion is not proof of production-provider acceptance; that remains a DS12 gate.

## 1. Purpose And Authority

This roadmap defines the approved direction for Stonegate's buyer relationship system and the
staff-facing Disposition Sidekick.

The target is not merely a list of investors or an InvestorLift clone. The target is one operating
workspace that helps a human disposition specialist:

1. Build and protect Stonegate's permanent investor network.
2. Prepare every contracted property for accurate buyer presentation.
3. Find the best-fit buyers from owned and external sources.
4. Run disciplined, approved outreach and follow-up.
5. Compare offers on price, certainty, timing, and execution risk.
6. Protect the deal with proof, deposits, deadlines, and backup buyers.
7. Learn which buyers, channels, and disposition actions produce completed assignments.

Application code, database migrations, production settings, and observed provider behavior remain
the truth about what exists. A roadmap phase may be marked complete only after its exit criteria and
tests pass. Documentation must never describe planned behavior as live behavior.

## 2. Business Decision

Stonegate remains the permanent system of record for buyers, relationships, deal evidence,
communications, offers, and disposition outcomes.

The Buyer Network combines three clearly identified pools:

1. **Agent relationships:** investors brought in and actively managed by a disposition specialist.
2. **Stonegate network:** the company's accumulated buyers from prior deals, referrals, inquiries,
   and other authorized sources.
3. **External candidates:** potential buyers discovered or reached through InvestorLift or another
   approved provider for a specific deal.

External providers amplify reach and supply market signals. They do not own Stonegate's operational
history or replace the canonical Buyer record.

A provider candidate remains staged until a human reviews it. Only an approved candidate becomes a
canonical Stonegate buyer. Provider identity, source, evidence, and last-sync time remain attached
after conversion so provenance is never lost.

## 3. Simple Operating Model

The intended employee experience is:

`Add and maintain investors -> contract signed -> package prepared -> buyers ranked -> outreach
approved -> replies and showings tracked -> offers compared -> primary and backups selected ->
deposit and closing protected -> outcome improves buyer intelligence`

The Disposition Sidekick performs research, organization, drafting, prioritization, reminders, and
risk explanation. The human disposition specialist owns relationships, conversations,
negotiations, recipient approval, offer recommendations, and placement results.

## 4. Non-Negotiable Product Boundaries

1. Stonegate is the source of truth; no provider becomes the only copy of a relationship or offer.
2. Only investor data Stonegate is authorized to use may be imported or entered.
3. The system never infers phone or SMS permission merely because a phone number or buyer record
   exists. Permission source and evidence remain reviewable and editable.
4. Duplicate records are never silently merged. A human chooses whether to use an existing buyer,
   merge reviewed records, or preserve distinct contacts.
5. An external candidate does not enter the permanent Buyer Network until a human approves it.
6. Unverified property claims are not included in an approved investor package.
7. Outreach requires an authorized human to approve the package, recipients, channel, and message.
8. AI cannot accept an offer, select a final buyer, change deal economics, release a contract, sign
   an agreement, or mark a deal funded.
9. Buyer ranking must be explainable and may not rank solely by highest offer or provider score.
10. A primary buyer must not erase viable backup coverage.
11. House and Land buy boxes and matching evidence remain asset-aware. Residential ARV and rehab
    logic must not be applied to Land.
12. Every material buyer, outreach, offer, selection, deadline, and AI action is auditable.
13. External delivery and provider sync can be disabled without deleting Stonegate records.
14. Provider failures must not block staff from using the owned Buyer Network manually.

## 5. Existing Foundation To Reuse

| Existing capability | Current location | Decision |
| --- | --- | --- |
| Manual buyer creation and list | `apps/api/app/routers/buyers.py`, `apps/web/src/app/os/buyers` | Extend |
| Buyer criteria and reliability history | `Buyer`, `BuyerBuyBox`, `BuyerBuyBoxVersion`, legacy `BuyerCriteria`, and buyer read models | Reused in the DS4 evidence score |
| Buyer Inbox conversation | `apps/api/app/services/inbox.py` | Reuse with explicit relationship ownership |
| Disposition access roles | `apps/api/app/domain/rbac.py` | Reuse and refine only if required |
| Unified Deal workspace | `apps/web/src/app/os/deals` | Reuse as the deal source of truth |
| Disposition case setup | `apps/web/src/app/os/dispositions/disposition-setup-workspace.tsx` | Reuse |
| Assignment, double-close, and novation strategy selection | Disposition case setup | Reuse |
| Investor package approval and PDF | Disposition workspace and disposition services | Extend |
| Internal buyer ranking | Disposition services | Extended in DS4 with versioned, explainable House pool scoring |
| Proof-of-funds evidence and review | Buyer profile and disposition proof workflows | Reuse with explicit verification |
| Inquiry, showing, follow-up, and deposit logs | Disposition workspace | Reuse and improve |
| Offer records and primary/backup selection | Disposition workspace | Reuse and improve |
| Reconciliation and accounting export | Disposition workspace | Reuse |
| Review-only Disposition Copilot foundation | Disposition Copilot and AI control plane | Extend through measured pilots |
| Twilio and Resend communications | Communications and Inbox services | Reuse behind approved outreach controls |
| Object storage and document evidence | Existing file and document services | Reuse |

## 6. Known Starting Gaps

The audited starting foundation was not yet the intended daily disposition system. Completed-phase
sections below supersede the starting gaps that those phases resolved.

### 6.1 Buyer Network Gaps

- Manual Add Buyer is the only general list-intake path.
- There is no edit-after-create, reviewed merge, deactivate, archive, or restore workflow.
- Phone and email are not normalized into stable duplicate keys.
- Manual creation has no duplicate preview.
- The newest 100 buyers are returned without true pagination or server-side network search.
- Buyer source, relationship owner, creator, import batch, external IDs, and last verification are
  not structured.
- One phone and one email do not adequately represent organizations with several contacts.
- Immutable House buyer-pool runs and score evidence are implemented. Automated Land matching and
  Land campaign release are not yet implemented.

### 6.2 Deal Disposition Gaps

- Internal buyers and staged external candidates now appear in one deduplicated House deal buyer
  pool. A corresponding Land execution and release lane is not yet active.
- House pool scoring now evaluates structured market, asset, price, strategy, funding, capacity,
  proof, activity, reliability, and relationship evidence. Land scoring remains future work.
- Deal-candidate lifecycle and reviewed shortlist/pass decisions are implemented. DS6 now records
  governed delivery state and reply review for selected owned-network recipients. Broader operator
  workflow and offer-room progression remain later-phase work.
- There is no operator-focused Today view combining deals, buyer replies, follow-ups, offers, POF,
  deposits, and closing deadlines.
- The DS5 **Prepare recipient pool** action remains a non-sending `prepared_not_sent` audit step.
  DS6's separate Outreach review and release path is the only implemented live-send path.
- DS6 reconciles replies only when they can be tied safely to prior governed outreach; ambiguous
  replies create review work instead of changing buyer or offer state automatically.
- Offer comparison and risk explanation need a clearer operator experience.

### 6.3 Provider Gaps

- A provider-neutral interface and manual-only InvestorLift adapter now exist. No verified or
  enabled InvestorLift REST, GraphQL, webhook, or polling transport exists.
- The existing external discovery surface is legacy DealMachine scaffolding and is not the target
  provider transport architecture.
- A complete public InvestorLift REST API contract, authentication model, rate limits, webhook
  catalog, sandbox, and God Mode or Artemis data endpoints have not been verified.
- Provider-specific objects must not leak into Stonegate's canonical Buyer and Deal models.

## 7. Target Disposition Desk

The disposition specialist receives one role-scoped workspace with the following sections.

### 7.1 Today

- Contracted deals requiring action.
- Packages blocked by missing or conflicting evidence.
- New and unread buyer replies.
- Buyer calls and follow-ups due today.
- Proof of funds missing or nearing expiration.
- Showings and access requests requiring coordination.
- Offers awaiting review or counter decisions.
- Earnest-money and closing deadlines.
- Deals with weak buyer coverage or elevated fallout risk.

Every item shows an owner, deadline, reason, and direct next action.

### 7.2 Active Deals

Each contracted deal shows:

- property and seller identity;
- contract, disposition, closing, and finance status;
- assignment, double-close, or novation strategy;
- contract price, desired assignment fee, minimum acceptable economics, and closing date;
- package readiness and evidence blockers;
- candidate, shortlisted, contacted, interested, showing, and offer counts;
- primary and backup buyer coverage;
- assigned disposition owner; and
- the next required action.

### 7.3 Buyer Network

The permanent Buyer Network supports:

- fast one-by-one buyer entry;
- duplicate preview before creation;
- buyer and contact editing;
- relationship owner and source;
- House, Land, or Both asset focus;
- structured markets and buy boxes;
- funding and proof-of-funds evidence;
- tier, temperature, tags, status, and verification state;
- last contact, next follow-up, and relationship timeline;
- closed-deal, offer, fallout, and reliability history;
- archive, suppression, and restore controls; and
- pagination, filters, and server-side search.

### 7.4 Deal Buyer Pool

Every deal uses a single candidate workspace with source filters for:

- My Buyers;
- Stonegate Network; and
- InvestorLift or other staged external candidates.

Candidate cards show:

- canonical identity and duplicate state;
- relationship owner, tier, and last contact;
- source evidence and provider identity;
- buy-box fit and an explanation of the match;
- activity and location evidence;
- proof, funding capacity, and expiration;
- prior offers, purchases, closes, fallouts, and retrades;
- outreach and reply state; and
- recommended next action.

Humans can shortlist candidates without first converting every external candidate into a permanent
buyer.

### 7.5 Outreach

The disposition specialist can:

1. Approve a fact-checked package.
2. Select or adjust a recipient shortlist.
3. Review channel eligibility and suppression.
4. Review and edit drafted email or SMS content.
5. Approve release.
6. Monitor delivery, replies, inquiries, address requests, passes, and follow-ups.
7. Continue each buyer relationship through the shared Inbox.

Bulk delivery must be bounded, observable, idempotent, and recoverable. A provider retry cannot
send the same campaign twice.

### 7.6 Offers And Closing Protection

Offer comparison includes:

- purchase or assignment amount;
- earnest money amount and due date;
- requested inspection or due-diligence period;
- contingencies and special terms;
- proposed closing date;
- proof-of-funds coverage and expiration;
- funding method and confidence;
- buyer reliability and prior completion history; and
- estimated fallout or retrade risk with supporting evidence.

The disposition specialist recommends a primary buyer and at least one backup when available. Final
selection remains human-approved. Deposit, agreement, title, access, and closing deadlines remain
visible until the transaction is completed or the buyer is replaced.

## 8. Canonical Data And Provider Boundaries

The implementation should preserve the following conceptual boundaries even if existing models are
extended rather than replaced.

| Concept | Purpose |
| --- | --- |
| Buyer | Canonical investor or buying entity |
| Buyer contact and contact method | People, phones, emails, permission, and verification |
| Buyer relationship | Owner, source, tier, status, last touch, next follow-up, and notes |
| Buyer criteria version | Historical House or Land buy box with effective dates |
| Buyer evidence | POF, funding, transaction, purchase, and reliability evidence |
| Buyer source link | Provider, external ID, original source, and last sync |
| External buyer candidate | Deal-scoped provider result awaiting review |
| Deal buyer candidate | Canonical or external candidate progression for one deal |
| Outreach campaign and recipient | Approved package release and per-recipient state |
| Buyer engagement | Inquiry, reply, showing, address request, pass, or follow-up |
| Buyer offer | Structured economics, dates, terms, proof, and status |
| Buyer selection | Human-approved primary and backup coverage |
| Provider sync run | Bounded request, result, cost, errors, and replay state |
| Buyer import batch | Future CSV mapping, row outcome, idempotency, and rollback scope |

Provider payloads are stored as source evidence where necessary, but provider schemas must not
become the only representation of Stonegate business data.

## 9. InvestorLift Boundary And Verification Gate

Public InvestorLift documentation currently verifies buyer-search, engagement, marketplace,
campaign, offer, analytics, import/export, and Zapier capabilities. It does not establish a complete
public direct API contract for the Stonegate use case.

Before implementing or enabling live DS8 transport, Stonegate must obtain written confirmation of:

1. API documentation, authentication, and sandbox access.
2. Subscription level and additional fees required for API access.
3. Create and update endpoints for properties, photos, documents, pricing, and status.
4. Webhooks or polling contracts for inquiries, views, address requests, favorites, offers, and
   accepted offers.
5. Whether God Mode transaction evidence and Artemis engagement are API-accessible.
6. Buyer import, export, rental, unlock, and permanent-list rules.
7. Rate limits, retry rules, retention, support response, and service limits.
8. Data ownership and full-export rights if Stonegate cancels.

Useful provider references:

- [Stonegate InvestorLift provider verification record](INVESTORLIFT_PROVIDER_VERIFICATION.md)

- [InvestorLift God Mode FAQ](https://intercom.help/investorlift/en/articles/15138862-god-mode-faq)
- [InvestorLift Artemis Mode](https://intercom.help/investorlift/en/articles/15164832-find-hot-leads-with-artemis-mode)
- [InvestorLift disposition lead workflow](https://intercom.help/investorlift/en/articles/15164885-how-to-track-and-manage-disposition-leads-with-investorlift)
- [InvestorLift Zapier integration reference](https://intercom.help/investorlift/en/articles/15119320-zapier-integration-essentials-supported-triggers-actions-and-fields-in-investorlift)

If a required direct capability is unavailable, the Disposition Desk provides a guided manual
handoff: copy or export the approved Stonegate package, record the InvestorLift property ID and URL,
and reconcile responses and offers into Stonegate. The manual fallback must remain usable even
after an adapter is released.

## 10. Implementation Phases

## DS0 - Repository Audit And Boundary Decision

**Status: Complete as of August 26, 2026.**

### Completed

- Audited Buyer, Deal, Disposition, communications, offer, and Copilot foundations.
- Confirmed that Stonegate Buyer is the canonical relationship record.
- Confirmed that Deal is the canonical contracted-property workspace.
- Confirmed that external candidates must remain staged until reviewed.
- Documented current list, edit, matching, outreach, and provider gaps.
- Established the human and AI authority boundaries in this roadmap.

### Exit Criteria

- The product boundary is documented.
- Existing capabilities and gaps are identified.
- DS1 can begin without creating a second buyer database.

## DS1 - Buyer Network Foundation

**Status: Complete as of August 26, 2026.**

### Goal

Make slow, one-by-one transfer of a disposition specialist's authorized investor relationships safe
and useful before adding volume or external providers.

### Work

- Add normalized email and E.164 phone identity keys without destroying original display values.
- Require a buyer name and at least one usable contact method.
- Add duplicate preview using normalized phone, email, company, and reviewed contextual matches.
- Let the user choose Use Existing or audited Create Separate when duplicates are found.
- Add buyer and contact editing.
- Add Needs Review, Active, Paused, Do Not Contact, and Archived lifecycle states.
- Default incomplete or migrated records to Needs Review rather than Active.
- Add source type, source label, source external key, created by, relationship owner, and last
  verified time.
- Surface phone and SMS permission status, source, evidence, and editable history.
- Add structured Activity and Audit events for every material change.
- Add pause, Do Not Contact, archive, and restore workflows with suppression safeguards.
- Add paginated, filterable, server-searchable buyer reads.
- Preserve existing buyer IDs, criteria, conversations, matches, and deal history.

### Delivered Scope Decision

DS1 deliberately does not perform destructive buyer-record merges. Duplicate review supports Use
Existing or audited Create Separate, and ambiguous provider identities remain in Needs Review.
Reviewed merge is deferred until a later phase can safely reconcile conversations, permission
history, criteria versions, proof, offers, matches, and closed-deal history without losing evidence.

### Exit Criteria

- Alex can add and later edit an investor without developer assistance.
- A likely duplicate is shown before creation and is never silently merged.
- A partially entered investor cannot enter active matching without review.
- More than 100 buyers remain discoverable.
- Relationship owner and source are visible and auditable.
- Existing buyer and disposition regression suites pass.

## DS2 - Disposition Desk

**Status: Complete.**

### Goal

Give the assigned disposition specialist one daily command center instead of requiring navigation
among disconnected deal, buyer, task, and Inbox views.

### Work

- Add Today, Active Deals, Buyer Follow-ups, Replies, Offers, and Deadlines views.
- Use existing Tasks, Calendar, Inbox, Deal, Buyer, and Disposition records rather than duplicate
  work items.
- Scope default views to the signed-in specialist while permitting manager team views.
- Show an owner, due time, reason, blocker, and direct next action on every queue item.
- Add quick actions for Add Buyer, Open Buyer, Open Deal, Log Contact, Schedule Follow-up, Review
  Offer, and Request POF.
- Show buyer-network health and deal buyer-coverage warnings.

### Exit Criteria

- The specialist can identify the day's highest-value work from one screen.
- Every card resolves to a canonical record and action.
- Assigned and manager visibility follows RBAC and team scope.
- Empty, loading, stale, and provider-unavailable states remain actionable.

### Delivered Scope Decision

The Disposition Desk is a URL-backed mode of the canonical Deals workspace at
`/os/deals?view=disposition`; it is not a twelfth top-level OS destination. `/os/dispositions`
remains the setup and compatibility route for opening the first case or resolving an older case
bookmark.

The desk is a read model over canonical Deal, Disposition Case, Buyer, Buyer Engagement, Inbox,
Offer, Task, Transaction, and checklist records. It does not create parallel tasks, replies,
offers, deadlines, or buyer records. **Mine** is the default. Authorized managers may switch to an
actual Dispositions-team view, while owner-level roles may review the organization view. Every
queue item links back to the canonical record where the work is completed.
Large queues retain their full scoped totals and use 100-item, URL-backed pages so work is not
silently hidden by the read-model response limit.

External buyer discovery remains intentionally nonblocking. The desk reports whether the provider
is not configured, configured but unverified, available after a completed run, or unavailable after
a failed run while continuing to surface Stonegate's owned network, deal coverage, POF, offer,
deposit, and closing work. General buyer follow-up scheduling remains limited to the existing
deal-specific Buyer Engagement model until DS3 introduces a reusable relationship-level
next-follow-up field.

## DS3 - Buyer Profiles And Asset-Aware Buy Boxes

**Status: Complete as of August 27, 2026.**

### Goal

Turn a contact list into reusable relationship and purchasing intelligence.

### Completed

- Added independently maintained and versioned House and Land buy boxes. **Both** is a derived
  asset focus when a buyer has both boxes; it is not a third editable criteria record that can drift
  from them.
- Added typed strategy, property type, state, county, city, ZIP, radius, exclusion, price, funding,
  capacity, House preference, and Land preference criteria with asset-specific validation.
- Added buyer tier, temperature, tags, relationship status, profile verification, derived last
  contact, next follow-up, and relationship follow-up controls.
- Added a permission-filtered buyer timeline for saved relationship notes and follow-ups, buyer
  audit activity, communications, and offers the signed-in user is authorized to review.
- Purchase, close, fallout, and retrade history remains future scope and will be added when those
  lifecycle events have authoritative records in a later phase.
- Added reusable proof-of-funds evidence with amount, source, expiration, private document access,
  and an explicit review decision.
- Added dedicated permissions for viewing and managing proof, organization isolation, private
  downloads, and download and review audit events.
- Updated the current House matcher to require a verified structured House buy box and current
  verified proof where applicable. Each saved match records the exact buy-box version, criteria
  snapshot, and matcher version used to make the decision.
- Preserved legacy free-text `BuyerCriteria` records for history and review while excluding them
  from authoritative matching.

### Delivered Scope Decision

Uploading proof records it as **Received** only. It cannot qualify a buyer until an authorized
human explicitly verifies the amount, source, and expiration. Generic buyer editing cannot bypass
that review workflow, and proof access and decisions remain auditable.

House and Land boxes are versioned independently, and identical saves do not create meaningless
new versions. A verified box must contain enough structured information to be operationally useful.
The profile labels reliability as insufficient when Stonegate has no performance history rather
than treating an untested buyer as reliable.

DS3 did not implement automated Land matching or immutable historical match runs. DS4 subsequently
added immutable, versioned House buyer-pool runs and evidence while retaining the legacy match rows
as the current compatibility projection. Automated Land eligibility, matching, and release remain
future work. A generic preferred-margin field was not added because its economic basis is not yet
consistently defined across House and Land strategies; any future field must use explicit,
asset-specific calculation semantics.

### Exit Criteria

- The specialist can maintain a buyer's actual purchasing criteria without free-text dependence.
- House and Land criteria do not cross-match incorrectly.
- POF and relationship history can be reviewed from the buyer profile.
- A buyer can be followed up with through the shared communications timeline.

## DS4 - Unified Explainable Deal Buyer Pool

**Status: Complete as of August 27, 2026, for the current House disposition workflow.**

### Goal

Combine owned relationships and staged provider candidates into one deal-specific work queue without
losing provenance or polluting the permanent Buyer Network.

### Completed

- Defined the deal-candidate lifecycle: Discovered, Needs Review, Shortlisted, Contacted, Interested,
  Showing, Offer, Pass, Selected, Backup, and Fallout.
- Added My Buyers, Stonegate Network, and External Candidate source filters in one deal buyer pool.
- Expanded House matching to structured market, asset, price, strategy, funding, capacity, proof, activity,
  reliability, and relationship evidence.
- Recorded an explainable score breakdown, supporting evidence, conflicting evidence, eligibility,
  and disqualifying reasons for every saved run entry.
- Added stable deal candidates, immutable versioned pool runs and entries, optimistic decision
  locking, and auditable shortlist/pass history across reruns.
- Detected exact and likely identity overlap between internal and external candidates. Exact
  provider evidence is attached to the canonical candidate; ambiguous overlap remains staged for
  human review rather than being silently merged.
- Let humans shortlist or pass on a deal candidate without converting every external result into a
  permanent Buyer.
- Required an explicit reviewed create, link, or reject decision before an external candidate can
  affect the canonical Buyer Network. Approved new buyers enter **Needs Review**, and provider
  identity and evidence remain attached through a source link.
- Captured the buy-box version, proof status and expiration snapshot, score policy, matcher version,
  provenance, and evidence used by each House pool run.
- Integrated House campaign release with the reviewed pool: once pool decisions exist, only
  shortlisted canonical buyers that still satisfy current release eligibility may be recipients.
  The immutable scored entry is not rewritten when current proof or buyer state changes.

### Delivered Scope Decision

DS4 is complete only for Stonegate's current **House** disposition case and release path. The data
model records asset class and remains compatible with independently versioned Land buy boxes, but
Stonegate does not yet claim automated Land buyer eligibility, Land pool scoring, Land campaign
release, or a production-ready Land disposition workflow. Residential evidence and release rules
must not be reused as a substitute for those missing Land controls.

DS4 itself did not activate live email or SMS outreach. DS6 subsequently added the governed owned
Buyer Network delivery and reply loop for the current House workflow. DealMachine results remain
staged provider evidence. DS8 subsequently added the provider-neutral/manual InvestorLift handoff;
verified live InvestorLift transport remains pending.

### Exit Criteria

- One deal shows all eligible sources without duplicate outreach.
- Every score includes understandable supporting and conflicting evidence.
- Staged external candidates do not appear as permanent active buyers before approval.
- Human overrides and pass reasons are recorded.

## DS5 - Deal Launch And Investor Package Readiness

**Status: Complete as of August 27, 2026 for the current House disposition workflow.**

### Goal

Prepare an accurate, persuasive, reusable package for the current contracted deal and every future
deal.

### Delivered

- Reuses the House deal, executed-contract, property-intelligence, underwriting, repair, inspection,
  photo, file, and title evidence already stored in Stonegate.
- Provides an actionable launch-readiness checklist that identifies blockers, warnings, unknowns,
  source freshness, material conflicts, and the workspace where a staff member can remediate each
  issue.
- Records a field-level evidence manifest that distinguishes verified facts, seller statements,
  provider signals, Stonegate analysis, and unknowns instead of presenting every input as fact.
- Keeps buyer-visible package data separate from purchase basis, minimum acceptable economics,
  desired assignment fee, approval authority, and other private operating information. Private
  economics require a dedicated permission and are not copied into recipient-visible summaries or
  PDFs.
- Creates append-only package versions with policy and renderer versions, a canonical source
  fingerprint, evidence and readiness snapshots, and channel-ready email and SMS summaries.
- Requires a separately authorized human approver to attest to a specific current draft and record
  an approval reason. A changed material source fingerprint makes the approved package stale and
  requires a new version and approval before matching or recipient preparation can continue.
- Renders the investor PDF once at approval, stores the exact bytes, filename, size, and SHA-256,
  and serves that saved artifact rather than rebuilding it from mutable live records.
- Binds every simulated campaign and prepared recipient audit row to the exact approved package
  version and artifact hash while preserving the buyer identity and destination observed at
  preparation time.

### Current Boundary

- DS5 is available only for the current House disposition workflow. Land package readiness and Land
  release require a separate asset-safe implementation.
- Campaign release in DS5 is preparation and audit simulation only. Recipient rows remain
  `prepared_not_sent`, and **Prepare recipient pool** itself sends no email or SMS.
- DS6 subsequently added a separate governed outreach revision, approval, delivery, suppression,
  reconciliation, reply, retry, pause, and cancel-unsent workflow for eligible House recipients.

### Exit Criteria

- No unverified property claim is presented as fact.
- Package blockers are explicit and actionable.
- A package version is reproducible from saved evidence.
- Recipient-visible information never includes internal pricing floors or private notes.

## DS6 - Governed Live Outreach And Reply Loop

**Status: Complete as of August 28, 2026, for governed outreach to Stonegate-owned buyers in the
current House disposition workflow. Production-provider acceptance remains DS12 work.**

### Goal

Replace the simulated release with bounded, human-approved buyer communication using Stonegate's
existing communication providers.

### Delivered

- Adds a House-only **Outreach** workspace after the approved package and prepared recipient pool.
  Staff select the exact owned-network buyers and email and/or SMS channel for each buyer.
- Enforces a hard limit of 25 recipient-channel deliveries per immutable revision. Choosing email
  and SMS for one buyer counts as two deliveries.
- Captures the exact Resend alias or Twilio Dispositions buyer-relations line, recipient identity,
  destination, package version, approved PDF hash, rendered subject/body, body hash, and recipient
  manifest in the approval record.
- Limits merge fields to buyer name, company name, public property address, and package reference.
  Private economics, seller notes, and unverified claims are not automatically available to the
  outreach template.
- Requires an authorized human to review the exact recipient/channel/message revision, affirm an
  attestation, record a reason, and approve its SHA-256-bound manifest before release. Managing a
  buyer or preparing a recipient pool does not send a message.
- Rechecks buyer Active status, relationship restrictions, archive state, current destination,
  email suppression, SMS permission/suppression, approved sender state, provider readiness, current
  package fingerprint, and frozen PDF artifact before queueing and again before provider delivery.
- Records the prepared campaign's first live release time and advances a House case from Buyer
  Matching to Marketed only after at least one delivery passes the live release preflight and is
  actually queued.
- Delivers email through Resend with the exact approved PDF and SMS through the selected Twilio
  buyer-relations line. Durable dispatch and idempotency records prevent known callback or worker
  replay from creating another send. An uncertain SMS or email provider boundary is held for review
  rather than retried automatically; Resend concurrent-idempotency responses are also treated as
  acceptance-unknown instead of safely retryable.
- Records prepared, approved, queued, claimed, provider-accepted, sent, delivered, failed,
  delivery-unknown, suppressed, opted-out, replied, and cancelled outcomes, and aggregates them on
  the revision without erasing earlier audit history.
- Provides reason-required **Pause**, **Resume**, **Cancel unsent**, and manager-gated **Retry
  failed** controls. Retry is limited to failures Stonegate can identify as safely retryable.
- Routes safely matched email and SMS replies into the canonical Buyer Inbox conversation, links
  the disposition case, campaign, revision, delivery, and buyer, and creates reply-review tasks.
  Ambiguous replies create reconciliation review work. A clear email unsubscribe from one
  structured sender address creates durable address-level suppression immediately even when the
  campaign match still needs review. Replies never select a buyer, accept an offer, or change
  economics automatically.

### Current Boundary

- DS6 applies only to the current **House** disposition workflow and buyers already approved into
  Stonegate's owned Buyer Network. Land package release and Land outreach remain disabled.
- Live InvestorLift synchronization and automated outreach remain disabled. DS6 does not call
  InvestorLift or convert provider candidates into permanent buyers; DS8's separate manual handoff
  does not change this DS6 boundary.
- The 25-delivery hard cap is not configurable upward through this workspace. A manager must still
  approve the exact revision and explicitly release or resume it.
- **Prepare recipient pool** remains a non-sending DS5 action; communication starts only from the
  separately approved DS6 Outreach revision.
- DS6 uses the existing Resend and Twilio configurations and does not prove that DNS, mailbox,
  carrier registration, phone-number configuration, or real recipient delivery has passed in
  production. Controlled production acceptance and broader rollout remain DS12 work.
- Commercial buyer email requires the non-secret
  `DISPOSITION_OUTREACH_PHYSICAL_POSTAL_ADDRESS` setting to contain Stonegate's complete, valid
  business postal address. Configure the same value on both API and communications worker before
  email outreach; the blank default keeps email blocked. Buyer SMS remains usable without this
  setting when all existing Twilio, permission, and suppression checks pass.

### Exit Criteria

- A supervised release reaches only the approved recipients once.
- Delivery and reply state reconcile to both the deal and buyer timeline.
- Suppressed or ineligible contacts are excluded with an explanation.
- The campaign can be paused without losing audit history.
- Existing seller communications remain unaffected.

## DS7 - Offer Room And Closing Protection

**Status: Complete for the current House disposition workflow as of August 28, 2026.**

### Goal

Help the specialist select the strongest executable offer and protect the assignment through
closing.

### Work

- Normalize offer amount, EMD, due date, contingencies, due diligence, closing date, funding, POF,
  and special terms.
- Compare offers side by side with confidence and risk evidence.
- Highlight expired proof, insufficient verified funds, weak deposits, incompatible dates,
  contingencies, prior fallout, and retrade behavior.
- Preserve human notes and negotiation history.
- Require human approval for primary and backup selections.
- Track agreement, signature, deposit, access, title, closing, and buyer-response deadlines.
- Escalate missed deadlines and support rapid replacement from ranked backups.
- Capture pass, withdrawal, fallout, retrade, and completed-close reasons.

### Delivered Behavior

- The Deal's **Offer Room** normalizes each buyer's amount, earnest money, deposit deadline, due
  diligence, contingencies, proposed closing, funding confidence, proof, special terms, and notes.
- Every material offer change creates an immutable revision. Negotiation events, selection versions,
  replacements, and outcomes remain visible instead of rewriting prior evidence.
- Price, verified funds, proof freshness, buyer reliability, timing, contingencies, and prior buyer
  performance produce explainable risk and execution evidence. The ranking is decision support only.
- A human with the separate buyer-selection approval permission must approve one primary and at
  least one different-buyer backup. Recording or ranking an offer never selects it automatically.
  Revised selected terms make the frozen slot stale and require a new approved coverage version.
- Transaction closing, buyer-deposit, and relevant title/access/closing checklist dates synchronize
  into the Offer Room. Canonical transaction rows remain editable only in their source workspace.
- The communications worker raises one versioned alert for a missed deadline. Alerts flow to the
  Disposition Desk and can be acknowledged without erasing the missed checkpoint.
- A manager can replace the primary with an eligible ranked backup while recording the prior
  buyer's outcome, cause, details, and supporting evidence.
- House assignment packages bind the approved buyer identity and offer economics. Approval,
  delivery, execution, replacement, and funding revalidate that authority so an old-buyer or stale-
  terms agreement cannot advance after the selection changes.
- Funded transaction close atomically records the selected buyer's completed-close outcome. House
  assignment funding requires the current approved selection, matching executed-assignee evidence,
  and buyer-deposit evidence or an explicit manager-documented waiver.
- Only buyer-responsible failure or retrade outcomes reduce buyer history. Seller, title, property,
  Stonegate, and external causes retain the evidence without unfairly penalizing the buyer.

### Known Boundaries

- The Offer Room is House-only. It does not enable Land packaging, Land buyer matching, or Land
  outreach.
- InvestorLift live transport remains unconnected. The DS8 manual handoff records provider evidence
  for review, while Offer Room decisions continue to use governed Stonegate buyer and deal data.
- A promoted backup can leave the deal without another approved backup; the visible coverage warning
  tells staff to qualify and approve new backup coverage.
- Repository verification is not the DS12 supervised production-acceptance test.

### Exit Criteria

- The agent can explain why the recommended buyer is stronger than a higher nominal offer.
- Primary and backup coverage remains visible until completion.
- Deadline alerts are actionable and deduplicated.
- Completed and failed outcomes update buyer history without erasing original evidence.

## DS8 - InvestorLift Provider Adapter

**Status: Provider-neutral/manual foundation complete as of August 28, 2026. Live InvestorLift
transport remains blocked pending provider verification.**

### Goal

Use InvestorLift for reach, transaction intelligence, marketplace activity, and engagement signals
while Stonegate keeps ownership of the workflow and relationships.

### Delivered Manual Foundation

- Implements a provider-neutral boundary and an InvestorLift adapter that explicitly reports
  `manual` mode, no credential requirement, an unverified API contract, and disabled live transport.
- Requires the current human-approved House disposition package before a handoff revision can be
  prepared. A newer revision supersedes every prior draft or approved revision; only the latest
  exact revision may be approved, downloaded, or linked.
- Builds deterministic, checksummed public-only payloads from the approved package sanitizer.
  Seller contact data, contract basis, internal floor, desired assignment fee, and other private
  Stonegate economics are rejected or removed from the provider bundle.
- Provides the guided manual workflow: prepare, approve the exact release, download its bundle,
  publish in InvestorLift manually, and record the resulting provider property ID and HTTPS URL.
- Stores provider account, listing, immutable revision, source-link, staged evidence, and operation
  history with organization isolation, optimistic locking, audit evidence, and replay-safe manual
  link and external-event identifiers.
- Stages manually observed inquiries, engagement, and offers for explicit review. These records
  cannot create or activate a Buyer, select a buyer, accept an offer, release outreach, or change a
  deal stage.
- Provides manual refresh, JSON/CSV export, and history-preserving disconnect controls. A
  disconnected listing cannot be silently reactivated, while Stonegate's owned Buyer Network and
  full provider history remain available.
- Adds role-scoped API and responsive Disposition workspace controls plus migration, API, RBAC,
  tenant-isolation, idempotency, state-machine, private-data, export, and frontend contract tests.

### Live Transport Remaining

- Obtain and review the written provider materials listed in Section 9 and
  `INVESTORLIFT_PROVIDER_VERIFICATION.md`.
- Verify the subscribed account, authentication, sandbox, endpoints, rate and usage limits,
  idempotency, retry rules, event semantics, costs, buyer rights, export, and cancellation terms.
- Add provider-specific publish, update, webhook, or polling transport only for capabilities proven
  by that contract; do not guess God Mode, Artemis, inquiry, offer, or accepted-offer endpoints.
- Run bounded sandbox and supervised production acceptance before enabling any live transport.

### Exit Criteria

- The manual foundation calls no guessed provider endpoint and truthfully identifies the remaining
  verification blockers.
- Manual retries are idempotent and observable; stale revisions cannot be released.
- External IDs, exact public payload hashes, source evidence, reviews, and provenance are durable.
- Provider evidence remains staged and cannot silently affect the canonical Buyer Network.
- Provider downtime or cancellation does not block owned-list disposition work or erase history.
- Stonegate can export its provider evidence and permanent owned buyer/deal history independently.
- Live transport is not complete until the written contract and bounded acceptance gates pass.

## DS9 - Governed Disposition Copilot

**Status: Repository implementation complete; measured pilot NOT MET.**

### Goal

Turn the existing review-only Copilot foundation into a measured daily sidekick without granting it
binding authority.

### Work

- Prepare structured, fact-checked package-summary drafts and identify missing evidence.
- Explain buyer-match strengths, conflicts, and disqualifiers from the current saved buyer pool.
- Draft recipient segments, email, SMS, call briefs, and follow-ups without creating or releasing an
  outreach revision.
- Classify replies, inquiries, passes, offer intent, offers, opt-outs, wrong-person replies, and
  uncertain replies with confidence and saved evidence citations.
- Recommend the next call, proof request, showing, counter, deadline action, backup review, or other
  bounded next step.
- Summarize saved offer differences and execution risks without selecting the final buyer.
- Propose buyer preference and reliability changes for human review without mutating Buyer records.
- Record the evidence fingerprint and structured citations plus model, prompt, token use, cost,
  latency, output, correction, reviewer, quality evaluation, and timestamps.
- Support one immutable **Accept**, **Correct**, **Reject**, or **Ignore** decision per
  recommendation. A duplicate review is rejected as a conflict. Accepting or correcting stale
  evidence is blocked; reject and ignore remain available to close the historical draft honestly.
- Keep every authority flag false and every external action blocked regardless of organization-wide
  AI policy.
- Evaluate authority, citation integrity, package correctness, match relevance, reply
  classification, next-action usefulness, review outcomes, trace coverage, latency, and cost before
  any future capability decision.

### Exit Criteria

- Every material recommendation cites saved Stonegate or approved provider evidence through a
  durable source identifier.
- The specialist can accept, correct, reject, or ignore a recommendation without applying it to an
  operational record.
- Organization, House-only, private-economics, role, idempotency, and stale-evidence boundaries are
  enforced.
- No generation or review path can mutate a Buyer, package, campaign, provider handoff, message,
  offer, selection, contract, transaction, or financial record.
- Repository contract and regression suites pass.
- The measured-pilot gates in `DISPOSITION_COPILOT_REQUIREMENT_MATRIX.md` pass. This cumulative
  criterion is **not met** until at least 50 decisive reviews across 10 cases, at least 10
  applicable evaluations for each scored quality domain, and every quality, citation, authority,
  traceability, and scenario-coverage threshold pass.

## DS10 - Management Intelligence And Learning

**Status: Repository implementation complete for the derived House dashboard; production
reconciliation and expanded attribution/cost controls remain pending.**

### Goal

Measure whether the system and disposition specialist improve completed assignments rather than
merely increasing messages or nominal offers.

### Delivered Repository Scope

- Derive milestone and funnel observations from existing canonical House disposition records rather
  than copying results into a competing reporting ledger.
- Keep outreach, reply, inquiry, and offer activity separate from buyer selection, deposit, funded
  close, and approved reconciled economics.
- Derive buyer reliability context from documented Offer Room outcomes and retained cause evidence.
- Preserve unknown and incomplete source, agent, milestone, and economic evidence rather than
  silently filling gaps.
- Keep the dashboard read-only, organization-scoped, and subject to the existing disposition and
  financial permission boundaries.
- Publish the exact evidence and acceptance boundary in
  `DISPOSITION_INTELLIGENCE_REQUIREMENT_MATRIX.md`.

### Remaining Work

- Add a disposition campaign-cost ledger before calculating cost per offer, selected buyer, or
  completed assignment.
- Add a frozen, correction-capable winning-source decision instead of relying on mutable Buyer
  source context or ambiguous multi-source links.
- Add append-only management corrections and full split-credit agent attribution.
- Add a frozen historical market dimension and canonical cross-provider showing semantics.
- Validate human-led versus AI-assisted comparisons with sufficient production samples; do not
  claim causation from operating mode or small samples.
- Implement and accept a separate Land disposition workflow before adding Land intelligence.

### Exit Criteria

- **Met in repository:** activity metrics remain separate from completed economic outcomes.
- **Met in repository:** displayed House milestones and outcomes are derived from canonical
  disposition, transaction, and approved-reconciliation evidence, with incomplete evidence visible.
- **Met in repository:** the dashboard is read-only and does not mutate operational or financial
  records.
- **Partially met:** source and agent context is explainable where the retained evidence is
  unambiguous, but frozen attribution and append-only correction controls are not implemented.
- **Not met:** attributable campaign cost, cost-per-outcome reporting, Land intelligence, and
  production-validated causal comparisons.

## DS11 - Optional CSV Buyer Migration

**Status: Planned after manual Buyer Network acceptance.**

### Goal

Support larger future migrations without weakening the reviewed one-by-one workflow.

### Work

- Publish a downloadable Stonegate template.
- Accept approved CSV files with explicit encoding and size limits.
- Map source columns to Stonegate fields.
- Preview normalized data, validation errors, duplicates, and missing requirements.
- Require explicit commit after review.
- Store import batch, row key, source, creator, timestamps, and row outcomes.
- Make retries idempotent.
- Support safe rollback by deactivating batch-created records while preserving audit evidence and
  subsequent legitimate activity.
- Gate exports and sensitive bulk actions behind dedicated permissions.

### Exit Criteria

- Re-uploading the same file does not create duplicate buyers.
- Accepted, updated, skipped, duplicate, and rejected rows are explainable.
- Imported records start in the correct review state.
- An authorized manager can audit and safely reverse a bad batch.

## DS12 - Supervised Production Pilot And Acceptance

**Status: Planned.**

### Goal

Use Stonegate's current contracted deal as the supervised real-world acceptance case while keeping
external communication and binding decisions human-controlled.

### Work

- Create an anonymized fixture for automated tests; do not use production seller or buyer data in
  the test suite.
- Run each relevant phase against the live deal only after its automated checks pass.
- Add a controlled initial set of the specialist's highest-quality authorized buyers.
- Verify package facts, internal floors, recipient visibility, and approval history.
- Compare matches against the specialist's judgment and record corrections.
- Run the first live outreach with an explicit recipient cap and owner approval.
- Reconcile replies, inquiries, offers, proof, primary and backup coverage, deposit, and closing.
- Review provider cost, delivery, operational friction, and data quality.
- Fix acceptance failures before general rollout.
- Update Help, SOPs, System Map, deployment variables, and rollback instructions.

### Exit Criteria

- The full workflow is completed without duplicate buyers, messages, offers, or work items.
- The disposition specialist can operate the workflow without developer assistance.
- Stonegate retains complete buyer, outreach, offer, decision, and outcome history.
- Production monitoring and rollback controls are verified.
- Owner approval records the workflow as accepted for normal use.

## 11. Test Strategy

Every implementation phase must include proportionate tests before production use.

### 11.1 Backend

- Organization and role isolation.
- Normalization and duplicate candidate detection.
- Buyer lifecycle, ownership, provenance, criteria versioning, and audit history.
- Pagination, filters, and server search.
- House and Land match isolation.
- Candidate progression and external-to-canonical conversion.
- Package versioning and private-field exclusion.
- Campaign approval, recipient eligibility, suppression, and idempotency.
- Provider webhook or poll replay, ordering, retry, and partial failure.
- Offer comparison, selection, backup, deadline, and fallout state transitions.
- AI evidence, permission, review, cost, and rollback controls.

### 11.2 Web

- Disposition specialist and manager role acceptance.
- Keyboard, mobile, loading, empty, stale, and error states.
- Manual Add Buyer, duplicate review, edit, archive, and restore.
- Today and Active Deal action routing.
- Buyer Pool filters, score explanations, shortlisting, and candidate states.
- Package review, recipient selection, outreach approval, and reply handling.
- Offer comparison and primary or backup approval.

### 11.3 Production Replay

- Use redacted or synthetic buyer and deal fixtures first.
- Replay provider payloads without calling production delivery endpoints.
- Confirm message and sync idempotency before live activation.
- Use a bounded, owner-approved production pilot.
- Record corrections and operational friction as acceptance evidence.

## 12. Release And Rollback Controls

Recommended controls include:

- independent Buyer Network, live outreach, InvestorLift sync, and Copilot feature switches;
- delivery test mode and strict recipient caps;
- provider health, queue age, failure, retry, and cost telemetry;
- campaign pause and cancel-unsent controls;
- provider disconnect without canonical data deletion;
- reversible lifecycle changes instead of destructive deletion;
- migration rollback procedures; and
- a documented manual disposition fallback.

Turning off a provider or AI feature must leave Buyers, Deals, Inbox, Tasks, Calendar, offers, and
manual disposition operations available.

## 13. Success Measures

The product succeeds when it improves completed disposition outcomes and protects relationships.

Primary measures:

- time from executed contract to approved package;
- time to first qualified buyer response;
- time to first executable offer;
- time to primary and backup buyer coverage;
- completed assignment rate;
- assignment fee and contribution profit;
- earnest-money-on-time rate;
- buyer fallout and retrade rate;
- buyer source of completed assignment;
- owned-network share of completed assignments;
- repeat-buyer close rate; and
- disposition specialist follow-up completion and response time.

Quality and safety measures:

- duplicate rate;
- missing or stale buy-box rate;
- package correction rate;
- unverified-claim prevention;
- suppressed-recipient prevention;
- duplicate-delivery prevention;
- offer and provider reconciliation accuracy;
- AI correction and rejection rate; and
- unresolved provider or delivery anomalies.

## 14. Phase Status Ledger

| Phase | Name | Status |
| --- | --- | --- |
| DS0 | Repository Audit And Boundary Decision | Complete |
| DS1 | Buyer Network Foundation | Complete |
| DS2 | Disposition Desk | Complete |
| DS3 | Buyer Profiles And Asset-Aware Buy Boxes | Complete |
| DS4 | Unified Explainable Deal Buyer Pool | Complete for current House disposition workflow |
| DS5 | Deal Launch And Investor Package Readiness | Complete for current House disposition workflow |
| DS6 | Governed Live Outreach And Reply Loop | Complete for owned Buyer Network recipients in the current House disposition workflow; production acceptance pending DS12 |
| DS7 | Offer Room And Closing Protection | Complete for current House disposition workflow |
| DS8 | InvestorLift Provider Adapter | Provider-neutral/manual foundation complete; live transport blocked pending provider verification |
| DS9 | Governed Disposition Copilot | Repository implementation complete; measured pilot NOT MET pending 50 decisive reviews across 10 cases and every quality/safety gate |
| DS10 | Management Intelligence And Learning | Derived canonical House dashboard implemented; production reconciliation and expanded attribution/cost/correction controls pending |
| DS11 | Optional CSV Buyer Migration | Planned after manual acceptance |
| DS12 | Supervised Production Pilot And Acceptance | Planned |

## 15. Documentation Maintenance

After every phase:

1. Update the phase status and Last updated date in this file.
2. Record delivered behavior and known limitations.
3. Update `SYSTEM_MAP.md` only for behavior that is implemented and active.
4. Update Help and staff instructions for employee-visible changes.
5. Update deployment and credential documentation without placing secrets in the repository.
6. Record new provider assumptions, costs, and contract constraints.
7. Preserve test and production-acceptance evidence.

## 16. Recommended Implementation Order

With DS1 complete, the specialist may transfer high-quality, authorized buyer relationships through
the Buyer Network using duplicate review, editing, ownership, lifecycle controls, and pagination.
Ambiguous records should remain in Needs Review rather than being forced into an existing buyer.

DS2 provides the specialist's daily command center, DS3 provides the canonical buyer profile,
separate versioned House and Land buy boxes and proof review, DS4 provides the unified, versioned,
explainable House deal buyer pool, DS5 provides the evidence-backed, approval-gated House package
  and prepared-recipient audit trail, DS6 provides the governed owned-buyer email/SMS and reply
  loop, and DS7 provides the human-controlled Offer Room and closing-protection workflow. The DS8
  provider-neutral/manual foundation now supports an exact public-only InvestorLift handoff and
  reviewable provider evidence without claiming live sync. Land matching and release must receive
  their own asset-safe implementation before being described as live. A live DS8 adapter follows
  only after InvestorLift supplies a verified integration contract and the bounded acceptance gate
  passes. DS9 now makes the Copilot technically measurable and keeps the production pilot explicitly
  **NOT MET**. DS10 now provides a bounded, read-only House management view of retained operating
  outcomes. It does not yet provide a disposition campaign-cost ledger, frozen correction-capable
  attribution, Land intelligence, or causal performance claims.
DS11 remains a future efficiency feature because the immediate migration is expected to be mostly
manual. DS12 is the formal production-acceptance gate, while relevant parts of the current deal may
be used as supervised evidence throughout the build.
