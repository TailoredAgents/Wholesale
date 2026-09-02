# Stonegate Buyer Network And Disposition Sidekick Roadmap

Last updated: September 1, 2026

> **September 1 advisory-workflow decision:** Dispositions is an operator-led desk, not a forced
> sequence. Owner/plan/mode setup, launch readiness, package completeness, proof, coverage, and
> backup items are informational checklist evidence and never workflow locks. Staff may shop an
> incomplete deal, review the full pool, choose any buyer, and rank, call, follow up, log activity,
> or record offers in the order the situation requires. Hard gates are limited to tenant/RBAC;
> STOP, Do Not Contact, suppression, and channel permission; usable destinations/senders and
> provider availability; and truthful signature, assignment, deposit, and funding evidence. Exact
> package, outreach, provider-handoff, and buyer-selection approvals remain audited actions, but the
> standard Disposition representative has those narrow authorities without unrelated admin access
> or a routine manager wait. This decision supersedes stricter phase-history language below.

> **September 1 CRM parity follow-up:** House and Land now share the evidence-backed external
> signed-contract handoff, Disposition case, exact external investor-packet approval, and
> asset-aware buyer-pool refresh. Older phase-history statements below that describe Land matching
> or package readiness as future work apply to those earlier phases. Generated Land packets,
> residential outreach, Offer Room, InvestorLift, and Disposition Copilot remain unavailable for
> Land.

> **Current status: DS0-DS8 complete; the DS9 repository implementation is complete but its
> measured pilot is NOT MET; the DS10 derived House management dashboard is implemented; live
> InvestorLift transport and expanded DS10 attribution/cost controls remain pending; DS11's
> governed repository implementation and production API configuration are complete, while DS12
> repository preparation is complete and controlled real-deal acceptance remains pending.**
> Stonegate now has the audited,
> provider-independent Buyer Network foundation described in DS1 and the role-scoped Disposition
> Desk described in DS2, plus the buyer profiles, independently versioned House and Land buy boxes,
> relationship follow-ups, reusable proof review, and asset-safe House matching described in DS3.
> DS4 adds the unified, explainable House deal buyer pool, staged external evidence, explicit
> external-to-network review, versioned score history, and shortlist-visible House release controls.
> DS5 adds the House-only, evidence-classified advisory launch-readiness workspace; immutable
> package versions; exact approved stored investor PDFs; private-economics separation;
> material-change visibility; and exact package-version linkage for prepared recipients. DS6 adds governed,
> House-only email and SMS outreach to selected buyers already in Stonegate's owned Buyer Network:
> immutable exact-message revisions, a 25 recipient-channel cap, separate human approval, dynamic
> eligibility checks, durable delivery state, and Buyer Inbox reply review. Existing deal-specific
> engagement and offer records, primary and backup buyer selection, reconciliation, and review-only
> Disposition Copilot remain in place. DS7 adds the governed House Offer Room, immutable offer and
> negotiation history, representative-approved primary selection with advisory backup coverage,
> canonical closing checkpoints,
> deduplicated deadline escalation, controlled replacement, and evidence-based buyer outcomes.
> DS8 now adds an exact-artifact handoff with approved/Preliminary provenance, deterministic
> public-only payloads, manual
> InvestorLift link and activity reconciliation, staged human review, export, and history-preserving
> disconnect controls. DS9 adds a citation-gated, House-only, draft-only daily Copilot with four-way
> human review, immutable trace evidence, and explicit evaluation gates. Its production pilot has
> not met the required 50 decisive reviews across 10 cases. No direct InvestorLift API is claimed or
> enabled because its transport contract remains unverified. DS10 adds a read-only management view
> derived from canonical House disposition evidence while explicitly leaving campaign-cost,
> correction-capable attribution, and causal performance claims pending. DS11 now supplies bounded,
> cost-governed DealMachine buyer discovery; bulk CSV buyer migration is not planned because Alex
> will maintain Stonegate-owned relationships one at a time. The DS12 preparation now also includes
> immediate House case creation after purchase-contract execution, advisory owner/setup hydration,
> opt-in package-ready staff alerts, expiring investor-package links, a focused one-at-a-time call
> queue alongside the unrestricted full Buyer pool, permission-aware pre-call SMS and voice, and
> showing follow-up. The advisory
> enhancement removes package/readiness gates from ordinary buyer work. DS12 remains the final
> supervised launch and operator-acceptance gate. Land outreach and
> live InvestorLift transport remain future
> work. DS6
> repository completion is not proof of production-provider acceptance; that remains a DS12 gate.

> **September 1 navigation amendment:** Dispositions is now a first-class left-navigation desk at
> `/os/deals?view=disposition`, while Deal and Disposition Case records remain canonical and shared.
> Active Deal cards link directly to Packet, Find buyers, Reach out, and Offers; operator controls
> are organized as Packet, Find buyers, One-to-one, Bulk outreach, and Offers & closing. External
> distribution is under More, and reconciliation is reached through Deal Finance.

## 1. Purpose And Authority

This roadmap defines the approved direction for Stonegate's buyer relationship system and the
staff-facing Disposition Sidekick.

Use [DISPOSITION_ADVISORY_WORKFLOW_RELEASE_PLAN.md](./DISPOSITION_ADVISORY_WORKFLOW_RELEASE_PLAN.md)
for the September 1 release boundaries, migration order, acceptance criteria, and risk controls.

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

One common employee path is:

`Add and maintain investors -> contract signed -> package prepared -> buyers ranked -> outreach
approved -> replies and showings tracked -> offers compared -> primary and backups selected ->
deposit and closing protected -> outcome improves buyer intelligence`

This is not a state machine. The specialist may move among package, pool, calls, follow-up,
activity, and offers in any useful order, including shopping before the package is complete. The
desk keeps the checklist visible rather than forcing earlier items closed.

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
6. Package and message claims retain their evidence classification; missing or uncertain evidence
   is disclosed rather than converted into a workflow lock or silently presented as verified fact.
7. Governed bulk outreach preserves an exact human-approved recipient, channel, destination, and
   message revision. The standard Disposition representative is the authorized human for ordinary
   operation; no separate manager handoff is required.
8. AI cannot accept an offer, select a final buyer, change deal economics, release a contract, sign
   an agreement, or mark a deal funded.
9. Buyer ranking must be explainable and may not rank solely by highest offer or provider score.
10. A primary buyer must not erase viable backup coverage. Backup coverage is recommended and
    visible, not required before the operator can select or keep working the primary.
11. House and Land buy boxes and matching evidence remain asset-aware. Residential ARV and rehab
    logic must not be applied to Land.
12. Every material buyer, outreach, offer, selection, deadline, and AI action is auditable.
13. External delivery and provider sync can be disabled without deleting Stonegate records.
14. Provider failures must not block staff from using the owned Buyer Network manually.
15. Setup and readiness checklists never lock ranking, pool access, calls, follow-up, engagement,
    offers, or another otherwise authorized disposition action.
16. Hard gates are limited to tenant/RBAC, communication suppression and channel eligibility,
    usable destinations/senders and provider availability, and truthful signature/assignment/
    deposit/funding evidence.

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
- DealMachine's deal-specific House buyer discovery now has sequential search tiers, durable credit
  budgets, result-reuse controls, and a production API configuration. Controlled real-deal
  usefulness and credit reconciliation remain DS12 acceptance work. Buyer discovery is independent
  from the disabled DealMachine underwriting-comp role.
- A complete public InvestorLift REST API contract, authentication model, rate limits, webhook
  catalog, sandbox, and God Mode or Artemis data endpoints have not been verified.
- Provider-specific objects must not leak into Stonegate's canonical Buyer and Deal models.

## 7. Target Disposition Desk

The disposition specialist receives one role-scoped workspace with the following sections.

### 7.1 Today

- Contracted deals requiring action.
- Packages with missing or conflicting evidence to review.
- New and unread buyer replies.
- Buyer calls and follow-ups due today.
- Proof of funds missing or nearing expiration.
- Showings and access requests requiring coordination.
- Offers awaiting review or counter decisions.
- Earnest-money and closing deadlines.
- Deals with weak buyer coverage or elevated fallout risk.

Every item shows an owner, deadline, reason, and suggested direct action. The operator may choose a
different useful action.

### 7.2 Active Deals

Each contracted deal shows:

- property and seller identity;
- contract, disposition, closing, and finance status;
- assignment, double-close, or novation strategy;
- contract price, desired assignment fee, minimum acceptable economics, and closing date;
- package readiness and advisory evidence findings;
- candidate, shortlisted, contacted, interested, showing, and offer counts;
- primary and backup buyer coverage;
- assigned disposition owner; and
- the suggested next action.

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
buyer. The full pool remains visible, and the specialist may choose any appropriate buyer; rank
order and prior-buyer completion never constrain selection.

### 7.5 Outreach

The disposition specialist can use these controls in any useful order:

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

The disposition specialist approves a primary buyer and adds one or more backups when available.
Missing backup coverage remains visible but does not block selection. Deposit, agreement, title,
access, and closing deadlines remain
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
| Outreach campaign and recipient | Exact package/artifact provenance, human-approved message release, and per-recipient state |
| Buyer engagement | Inquiry, reply, showing, address request, pass, or follow-up |
| Buyer offer | Structured economics, dates, terms, proof, and status |
| Buyer selection | Human-approved primary and backup coverage |
| Provider sync run | Bounded request, result, cost, errors, and replay state |
| Provider discovery budget | Per-search, per-deal, and monthly credit authority and reconciliation |

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
handoff: copy or export one exact usable Stonegate package, visibly preserve **Preliminary** when it
was not approved/current, record the InvestorLift property ID and URL, and reconcile responses and
offers into Stonegate. The manual fallback must remain usable even after an adapter is released.

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
- Show an owner, due time, reason, advisory risk/checklist state, and suggested direct action on
  every queue item without constraining another authorized action.
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
- Updated the current House matcher to use the structured House buy box and score proof availability
  and freshness as explainable evidence. Missing or expired proof remains an advisory risk rather
  than excluding the buyer or locking other deal work. Each saved match records the exact buy-box
  version, criteria snapshot, and matcher version used to make the decision.
- Preserved legacy free-text `BuyerCriteria` records for history and review while excluding them
  from authoritative matching.

### Delivered Scope Decision

Uploading proof records it as **Received** only. It cannot be represented as **Verified** proof
until an authorized human explicitly verifies the amount, source, and expiration. Missing or
unverified proof remains visible evidence but does not prevent ranking, contact, activity, an
offer, or selection. Generic buyer editing cannot bypass the proof-status review workflow, and
proof access and decisions remain auditable.

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
- Integrated House campaign release with the canonical pool while preserving reviewed shortlist,
  pass, and other decision history as context. The operator may explicitly choose any appropriate
  canonical buyer; release eligibility is limited to real communication-integrity checks rather
  than shortlist, proof, rank, or readiness state. The immutable scored entry is not rewritten when
  current proof or buyer state changes.

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
- Provides an actionable but advisory launch-readiness checklist that identifies warnings, unknowns,
  source freshness, material conflicts, and the workspace where a staff member can remediate each
  issue without locking another disposition action.
- Records a field-level evidence manifest that distinguishes verified facts, seller statements,
  provider signals, Stonegate analysis, and unknowns instead of presenting every input as fact.
- Keeps buyer-visible package data separate from purchase basis, minimum acceptable economics,
  desired assignment fee, approval authority, and other private operating information. Private
  economics require a dedicated permission and are not copied into recipient-visible summaries or
  PDFs.
- Creates append-only package versions with policy and renderer versions, a canonical source
  fingerprint, evidence and readiness snapshots, and channel-ready email and SMS summaries.
- Requires the authorized Disposition representative to attest to a specific draft and record an
  approval reason. A changed material source fingerprint marks the approved artifact stale for
  current use and calls for a new version; matching, calls, engagement, and offers continue.
- Renders the investor PDF once at approval, stores the exact bytes, filename, size, and SHA-256,
  and serves that saved artifact rather than rebuilding it from mutable live records.
- Binds every simulated campaign and prepared recipient audit row to the exact package version,
  approved/Preliminary state, and artifact hash while preserving the buyer identity and destination
  observed at preparation time.

### Current Boundary

- DS5 was delivered first for House. The September 1 parity work makes the advisory readiness and
  exact external-PDF path available to Land while generated Land packets and residential release
  remain unavailable.
- Campaign release in DS5 is preparation and audit simulation only. Recipient rows remain
  `prepared_not_sent`, and **Prepare recipient pool** itself sends no email or SMS.
- DS6 subsequently added a separate governed outreach revision, approval, delivery, suppression,
  reconciliation, reply, retry, pause, and cancel-unsent workflow for eligible House recipients.

### Exit Criteria

- No unverified property claim is presented as fact.
- Package findings are explicit, actionable, and never workflow locks.
- A package version is reproducible from saved evidence.
- Recipient-visible information never includes internal pricing floors or private notes.

## DS6 - Governed Live Outreach And Reply Loop

**Status: Complete as of August 28, 2026, for governed outreach to Stonegate-owned buyers in the
current House disposition workflow. Production-provider acceptance remains DS12 work.**

### Goal

Replace the simulated release with bounded, human-approved buyer communication using Stonegate's
existing communication providers.

### Delivered

- Adds a House-only **Outreach** workspace that remains reachable while package/readiness checklist
  work is incomplete. Staff select the exact owned-network buyers and email and/or SMS channel for
  each buyer; an attached or linked package uses its exact usable artifact and retains a visible
  Preliminary state when applicable.
- Enforces a hard limit of 25 recipient-channel deliveries per immutable revision. Choosing email
  and SMS for one buyer counts as two deliveries.
- Captures the exact Resend alias or Twilio Dispositions buyer-relations line, recipient identity,
  destination, package version, approved PDF hash, rendered subject/body, body hash, and recipient
  manifest in the approval record.
- Limits merge fields to buyer name, company name, public property address, and package reference.
  Private economics, seller notes, and unverified claims are not automatically available to the
  outreach template.
- Requires the authorized Disposition representative to review the exact recipient/channel/message
  revision, affirm an attestation, record a reason, and approve its SHA-256-bound manifest before
  release. Managing a buyer or preparing a recipient pool does not send a message.
- Rechecks tenant/role scope, STOP/Do Not Contact and suppression state, channel permission,
  current destination, approved sender state, and provider readiness before queueing and again
  before provider delivery. When a package is included, its exact artifact identity is preserved.
- Records the prepared campaign's first live release time and advances a House case from Buyer
  Matching to Marketed only after at least one delivery passes the live release preflight and is
  actually queued.
- Delivers email through Resend with the exact bound PDF and SMS through the selected Twilio
  buyer-relations line. Durable dispatch and idempotency records prevent known callback or worker
  replay from creating another send. An uncertain SMS or email provider boundary is held for review
  rather than retried automatically; Resend concurrent-idempotency responses are also treated as
  acceptance-unknown instead of safely retryable.
- Records prepared, approved, queued, claimed, provider-accepted, sent, delivered, failed,
  delivery-unknown, suppressed, opted-out, replied, and cancelled outcomes, and aggregates them on
  the revision without erasing earlier audit history.
- Provides reason-required **Pause**, **Resume**, **Cancel unsent**, and authorized-representative
  **Retry failed** controls. Retry is limited to failures Stonegate can identify as safely retryable.
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
- The 25-delivery hard cap is not configurable upward through this workspace. The standard
  Disposition representative may approve the exact revision and explicitly release or resume it;
  there is no normal manager wait.
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
- Require human approval for the primary selection and preserve advisory backup coverage.
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
- The standard Disposition representative has the separate buyer-selection approval permission and
  approves one primary without a manager wait. Different-buyer backups are added when available;
  their absence remains a warning rather than a selection gate. Recording or ranking an offer never
  selects it automatically. Revised selected terms make the frozen slot stale and require a new
  approved selection version before that version supports assignment or funding.
- Transaction closing, buyer-deposit, and relevant title/access/closing checklist dates synchronize
  into the Offer Room. Canonical transaction rows remain editable only in their source workspace.
- The communications worker raises one versioned alert for a missed deadline. Alerts flow to the
  Disposition Desk and can be acknowledged without erasing the missed checkpoint.
- The authorized Disposition representative can replace the primary with an available backup while recording the prior
  buyer's outcome, cause, details, and supporting evidence.
- House assignment packages bind the approved buyer identity and offer economics. Approval,
  delivery, execution, replacement, and funding revalidate that authority so an old-buyer or stale-
  terms agreement cannot advance after the selection changes.
- Funded transaction close atomically records the selected buyer's completed-close outcome. As a
  truthful financial boundary, House assignment funding requires the selected buyer, matching
  executed-assignee/signature evidence, and buyer-deposit evidence or an explicit authorized
  waiver.
- Only buyer-responsible failure or retrade outcomes reduce buyer history. Seller, title, property,
  Stonegate, and external causes retain the evidence without unfairly penalizing the buyer.

### Known Boundaries

- The Offer Room is House-only. It does not enable Land packaging, Land buyer matching, or Land
  outreach.
- InvestorLift live transport remains unconnected. The DS8 manual handoff records provider evidence
  for review, while Offer Room decisions continue to use governed Stonegate buyer and deal data.
- A promoted backup can leave the deal without another approved backup; the visible advisory
  coverage warning tells staff to seek new backup coverage without blocking other work.
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
- Uses the exact human-approved House package selected for the artifact that will be manually
  published. This artifact-specific requirement does not block any other buyer or offer work. A
  newer revision supersedes every prior draft or approved revision; only the latest exact revision
  may be approved, downloaded, or linked.
- Builds deterministic, checksummed public-only payloads through the package sanitizer while
  preserving whether the source artifact was approved or Preliminary.
  Seller contact data, contract basis, internal floor, desired assignment fee, and other private
  Stonegate economics are rejected or removed from the provider bundle.
- Provides the guided manual workflow: prepare, have the standard Disposition representative
  approve the exact release, download its bundle,
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

## DS11 - Cost-Governed DealMachine Buyer Discovery

**Status: Repository implementation and production API configuration complete as of August 29,
2026. Controlled real-deal provider and operator acceptance remains DS12 work.**

### Goal

Help Alex find likely cash buyers for one contracted House at a time without replacing his owned
relationships, creating an unnecessary bulk-import workflow, or allowing provider credits to be
spent silently.

### Operating Decision

- Alex adds and maintains Stonegate-owned buyers one at a time as he transfers authorized
  relationships or meets a new investor. No CSV buyer migration is planned.
- Stonegate ranks the owned Buyer Network first without a paid provider request.
- DealMachine is a deal-specific reach and purchase-evidence source only when owned-network
  coverage is thin or Alex deliberately wants additional candidates.
- InvestorLift remains the intended later broad-reach provider after its live API contract,
  credentials, rights, costs, and transport behavior are verified.
- DealMachine buyer discovery does not reactivate or depend on DealMachine underwriting comps.

### Implemented Search And Credit Policy

1. Every tier begins with a free cost preview of the exact request that would be submitted.
2. Tier 1 may add up to 10 net-new, deduplicated candidates and has a 30-credit ceiling.
3. Tier 2 unlocks only after Tier 1 completes; Alex should review Tier 1 before choosing to add up
   to 20 additional net-new candidates under a 60-credit ceiling.
4. Tier 3 unlocks only after Tier 2 completes; Alex should review both narrower tiers before
   choosing to add up to 40 additional net-new candidates under a 120-credit ceiling.
5. The three normal tiers therefore remain below the hard 250-credit lifetime limit for one deal.
6. Disposition discovery may use no more than 2,000 credits in one UTC calendar month across the
   organization.
7. DealMachine's preview remains visible and must be confirmed, but the tier ceiling is the
   binding authorization because the live property-and-owner response can cost more than the
   property-only preview. The account, deal, and monthly budgets must each cover the full tier
   ceiling before Stonegate makes the paid request.
8. Identical current results are cached and reused. Reopening or refreshing the screen, retrying a
   response, or double-clicking cannot create a second paid request for the same case/property
   search fingerprint.
9. A materially expanded search requires the next sequential tier; staff cannot jump directly to
   the broadest search.
10. Stonegate commits the tier reservation before calling DealMachine. A running request or failed
    request with unknown final credits blocks every later paid search for that deal until the spend
    is reconciled; it never expires into an automatic retry.

### Delivered Work

- Adds a clear owned-network coverage state before offering paid discovery.
- Makes the 10, 20, and 40 net-new tiers explicit in the Deal Buyer Pool rather than silently using
  one broad default search.
- Enforces the 30, 60, and 120 per-tier ceilings, the 250-credit per-deal limit, and the 2,000-credit
  monthly limit on the server, not only in the interface.
- Shows the zero-credit preview, property-credit estimate, people-credit estimate, total estimate,
  dollar equivalent, prior spend on the deal, and remaining monthly allowance before confirmation.
- Re-estimates the exact request at execution and requires both buyer-edit and deal-edit authority,
  the provider's current estimate, and the exact request fingerprint returned by preview. If the
  property, price, scope, or preview changes, a new preview is required. Package changes do not
  invalidate otherwise identical paid-search results. The 30, 60, or 120
  credit tier ceiling—not the lower preview—is the hard spend authorization and budget reservation.
- Records actual versus estimated credits, provider balance, request fingerprint, result version,
  actor, timing, and errors for every paid attempt.
- Accepts a live charge above the property-only preview when it remains inside the explicitly shown
  tier ceiling; it still fails closed if the final charge exceeds that ceiling or lacks complete
  credit telemetry.
- Reuses current saved candidates and source evidence before permitting another paid request, and
  makes concurrent or replayed requests idempotent.
- Persists the spend reservation before crossing the paid-provider boundary. An interrupted or
  incompletely reported request blocks another paid search for that deal pending reconciliation,
  while the owned Buyer Network remains usable.
- Deduplicates each tier against earlier DealMachine results and Stonegate's owned Buyer Network so
  the tier count represents net-new candidates rather than repeated records.
- Keeps results staged inside the deal. Alex must shortlist, pass, link to an existing buyer, or
  create a **Needs Review** buyer explicitly.
- Preserves provider identity, purchase evidence, freshness, contact-quality warnings, and DNC
  signals. A discovered phone or email does not establish outreach permission, proof of funds, or
  a verified buy box.
- Keeps every search and review action House-only until a separate Land disposition design and
  acceptance phase exists.
- Records the source, credit, candidate, import, offer, and outcome evidence needed for DS12 to
  measure useful-candidate yield, duplicate rate, credits per Alex-approved candidate, and whether
  paid discovery produced an offer, backup, or completed assignment.
- Keeps a provider kill switch. Provider failure or exhausted credits must never block manual work
  with the owned Buyer Network.

### Exit Criteria

- Free preview is verified not to consume credits, and every paid request remains within the exact
  confirmed tier, deal, and monthly limits.
- Sequential tiers, duplicate clicks, retries, and concurrent requests cannot produce duplicate
  spend, candidates, or Buyer records.
- Every used credit reconciles to a saved request and actual provider response.
- No provider candidate becomes an active buyer, receives outreach, gains permission, or gains
  proof or buy-box authority without human review.
- Alex can complete owned-network review, preview, search, shortlist/pass, and link/create decisions
  without developer assistance.
- At least three bounded real-deal searches are reviewed for candidate usefulness and credit cost
  before the limits are expanded or DealMachine becomes routine.

## DS12 - Final Launch And Operator Acceptance

**Status: Repository preparation complete; controlled live-deal acceptance pending.**

### Goal

Use a real Stonegate contracted property with Alex as the supervised end-to-end launch and operator
acceptance case while keeping external communication and binding decisions human-controlled.

### Repository Preparation Already Delivered

- An executed House or Land purchase agreement creates one idempotent disposition case immediately.
  The case records an active authorized owner, compensation plan, and operating mode when available;
  missing setup remains advisory on the same open case and is hydrated after configuration changes.
- Approval of the current investor-package version can queue one staff SMS only when the selected
  owner is still authorized, has explicitly opted into staff alerts, and has a valid mobile number.
- Exact packet artifacts can be shared through auditable, expiring, revocable links tied to their
  version and hash. A link retains the artifact's **Preliminary** or approved state at issue and
  reports later source/version freshness without silently upgrading old bytes. A failed packet SMS
  triggers a best-effort immediate revocation.
- Alex has the full ranked Buyer pool plus a focused one-at-a-time execution queue with buyer
  profiles, saved match evidence, permission-aware pre-call SMS, a Stonegate voice call, structured
  outcomes, callbacks, retry tasks, showings, private access-status tracking, and one 24-hour
  post-showing follow-up. The queue does not lock the full pool or another task, and
  package/readiness state does not prevent buyer work.
- Execution outcomes and showing creation use server-enforced idempotency so retries do not create
  duplicate engagements or follow-up work.
- The Offer Room shows proof, title/access, and coverage gaps as advisory risk. Buyer identity,
  executed assignment/signature evidence, deposit evidence or an authorized waiver, and the
  completed-close outcome remain canonical truth gates at assignment/funding boundaries rather than
  allowing a manually checked box to create a false financial status.
- After a buyer is interested, one common path is to record and compare the offer, approve a primary
  and optional backups, execute the assignment, verify deposit and title/access milestones, confirm
  closing, and preserve the buyer's result and buy-box history. The operator may change the work
  order whenever a truth or communication-integrity gate is not implicated.

These controls are implemented and automatically tested. They are not evidence that Alex has yet
completed the workflow successfully on a production deal; that is the remaining DS12 acceptance
work below.

### Work

- Create an anonymized fixture for automated tests; do not use production seller or buyer data in
  the test suite.
- Run each relevant phase against the live deal only after its automated checks pass.
- Add a controlled initial set of the specialist's highest-quality authorized buyers.
- Verify package facts, internal floors, recipient visibility, and approval history.
- Compare matches against the specialist's judgment and record corrections.
- Exercise the DS11 owned-network-first decision and, if additional reach is justified, one bounded
  DealMachine tier with its preview, credit reconciliation, and staged-candidate review.
- Run the first live outreach with an explicit recipient cap and owner approval.
- Reconcile replies, inquiries, offers, proof, primary selection, advisory backup coverage, deposit,
  and closing.
- Review provider cost, delivery, operational friction, and data quality.
- Fix acceptance failures before general rollout.
- Update Help, SOPs, System Map, deployment variables, and rollback instructions.

### Exit Criteria

- The full workflow is completed without duplicate buyers, messages, offers, or work items.
- Alex can operate the complete workflow without developer assistance.
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
| DS11 | Cost-Governed DealMachine Buyer Discovery | Repository implementation and production API configuration complete; controlled real-deal acceptance pending DS12 |
| DS12 | Final Launch And Operator Acceptance | Repository preparation complete; controlled live-deal acceptance pending with Alex and a real contracted property |

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
explainable House deal buyer pool, DS5 provides the evidence-backed advisory checklist and exact
approved House package
  and prepared-recipient audit trail, DS6 provides the governed owned-buyer email/SMS and reply
  loop, and DS7 provides the human-controlled Offer Room and closing-protection workflow. The DS8
  provider-neutral/manual foundation now supports an exact public-only InvestorLift handoff and
  reviewable provider evidence without claiming live sync. Land now has asset-aware matching and
  exact external-package approval; generated packets, residential outreach, Offer Room, and
  provider handoff remain separate. A live DS8 adapter follows
  only after InvestorLift supplies a verified integration contract and the bounded acceptance gate
  passes. DS9 now makes the Copilot technically measurable and keeps the production pilot explicitly
  **NOT MET**. DS10 now provides a bounded, read-only House management view of retained operating
  outcomes. It does not yet provide a disposition campaign-cost ledger, frozen correction-capable
  attribution, Land intelligence, or causal performance claims.
DS11 deliberately preserves Alex's one-at-a-time relationship-entry process and adds only bounded,
deal-specific DealMachine discovery after free owned-network matching. Its sequential 10/20/40
net-new tiers, 30/60/120 credit ceilings, 250-credit per-deal cap, 2,000-credit monthly cap,
zero-credit preview, recent-result reuse, staged human review, and duplicate-request protection are
implemented and configured on the production API. InvestorLift live transport remains later
provider work after its contract is verified. DS12 is the formal end-to-end launch and
operator-acceptance gate with Alex and a real contracted property. Its repository preparation now
provides immediate case handoff, secure packet delivery, the full Buyer pool plus a focused
one-at-a-time execution queue, showing follow-up, advisory placement evidence, and truthful
assignment/funding boundaries;
only the bounded live pilot and resulting corrections remain before normal-use acceptance.
