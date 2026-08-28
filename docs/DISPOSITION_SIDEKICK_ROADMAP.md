# Stonegate Buyer Network And Disposition Sidekick Roadmap

Last updated: August 27, 2026

> **Current status: DS0-DS2 complete; DS3-DS12 planned.** Stonegate now has the audited,
> provider-independent Buyer Network foundation described in DS1 and the role-scoped Disposition
> Desk described in DS2, alongside its existing deal-specific disposition cases, package generation,
> buyer ranking, proof-of-funds evidence, engagement and offer records, primary and backup buyer
> selection, reconciliation, and review-only Disposition Copilot. Later phases remain plans and are
> not proof that those capabilities are live.

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
| Buyer criteria and reliability history | `Buyer`, `BuyerCriteria`, and buyer read models | Extend and normalize |
| Buyer Inbox conversation | `apps/api/app/services/inbox.py` | Reuse with explicit relationship ownership |
| Disposition access roles | `apps/api/app/domain/rbac.py` | Reuse and refine only if required |
| Unified Deal workspace | `apps/web/src/app/os/deals` | Reuse as the deal source of truth |
| Disposition case setup | `apps/web/src/app/os/dispositions/disposition-setup-workspace.tsx` | Reuse |
| Assignment, double-close, and novation strategy selection | Disposition case setup | Reuse |
| Investor package approval and PDF | Disposition workspace and disposition services | Extend |
| Internal buyer ranking | Disposition services | Replace exact-token limitations with structured matching |
| Proof-of-funds upload | Disposition buyer proof workflow | Surface on the buyer profile and reuse |
| Inquiry, showing, follow-up, and deposit logs | Disposition workspace | Reuse and improve |
| Offer records and primary/backup selection | Disposition workspace | Reuse and improve |
| Reconciliation and accounting export | Disposition workspace | Reuse |
| Review-only Disposition Copilot foundation | Disposition Copilot and AI control plane | Extend through measured pilots |
| Twilio and Resend communications | Communications and Inbox services | Reuse behind approved outreach controls |
| Object storage and document evidence | Existing file and document services | Reuse |

## 6. Known Starting Gaps

The current foundation is not yet the intended daily disposition system.

### 6.1 Buyer Network Gaps

- Manual Add Buyer is the only general list-intake path.
- There is no edit-after-create, reviewed merge, deactivate, archive, or restore workflow.
- Phone and email are not normalized into stable duplicate keys.
- Manual creation has no duplicate preview.
- The newest 100 buyers are returned without true pagination or server-side network search.
- Buyer source, relationship owner, creator, import batch, external IDs, and last verification are
  not structured.
- Incomplete buyers can enter the active matching pool instead of a Needs Review stage.
- Buyer records do not provide a complete relationship timeline, next follow-up, tier, tags, or
  assigned specialist.
- Proof of funds is primarily handled inside a matched deal rather than as reusable buyer evidence.
- One phone and one email do not adequately represent organizations with several contacts.
- House and Land buy boxes are not yet modeled and matched with sufficient precision.

### 6.2 Deal Disposition Gaps

- Internal matches and external candidates do not appear in one deduplicated deal buyer pool.
- Buyer matching relies on limited exact market and property-type intersections.
- There is no explicit candidate progression from discovered to reviewed, shortlisted, contacted,
  interested, showing, offer, pass, selected, backup, or fallout.
- There is no operator-focused Today view combining deals, buyer replies, follow-ups, offers, POF,
  deposits, and closing deadlines.
- The approved campaign release is simulated and sends no email or SMS.
- Buyer replies and campaign delivery state are not yet a governed disposition loop.
- Offer comparison and risk explanation need a clearer operator experience.

### 6.3 Provider Gaps

- No InvestorLift adapter exists in the repository.
- The existing external discovery surface is legacy DealMachine scaffolding and is not the target
  provider architecture.
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

Before DS8 implementation, Stonegate must obtain written confirmation of:

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

**Status: Planned.**

### Goal

Turn a contact list into reusable relationship and purchasing intelligence.

### Work

- Add House, Land, or Both asset focus.
- Add strategy, property type, state, county, city, ZIP, radius, and exclusion criteria.
- Add minimum and maximum price, preferred margin, funding method, and capacity.
- Add House rehab tolerance and residential preferences.
- Add Land acreage, use, zoning, access, utilities, terrain, flood or wetlands tolerance, and other
  appropriately sourced criteria.
- Add tier, temperature, tags, relationship status, last contact, next follow-up, and verification.
- Surface calls, messages, inquiries, offers, purchases, closes, retrades, fallout, and notes on one
  timeline.
- Surface reusable proof-of-funds evidence with amount, source, verification, expiration, and
  document access.
- Version buy-box changes so historical deal matches remain explainable.

### Exit Criteria

- The specialist can maintain a buyer's actual purchasing criteria without free-text dependence.
- House and Land criteria do not cross-match incorrectly.
- POF and relationship history can be reviewed from the buyer profile.
- A buyer can be followed up with through the shared communications timeline.

## DS4 - Unified Explainable Deal Buyer Pool

**Status: Planned.**

### Goal

Combine owned relationships and staged provider candidates into one deal-specific work queue without
losing provenance or polluting the permanent Buyer Network.

### Work

- Define the deal-candidate lifecycle: Discovered, Needs Review, Shortlisted, Contacted, Interested,
  Showing, Offer, Pass, Selected, Backup, and Fallout.
- Add My Buyers, Stonegate Network, and External Candidate source filters.
- Expand matching to structured market, asset, price, strategy, funding, capacity, proof, activity,
  reliability, and relationship evidence.
- Record an explainable score breakdown and disqualifying reasons.
- Detect likely identity overlap between internal and external candidates.
- Let humans shortlist without converting every external result into a Buyer.
- Require approval before converting an external candidate to the canonical network.
- Preserve score and evidence versions for later evaluation.

### Exit Criteria

- One deal shows all eligible sources without duplicate outreach.
- Every score includes understandable supporting and conflicting evidence.
- Staged external candidates do not appear as permanent active buyers before approval.
- Human overrides and pass reasons are recorded.

## DS5 - Deal Launch And Investor Package Readiness

**Status: Planned.**

### Goal

Prepare an accurate, persuasive, reusable package for the current contracted deal and every future
deal.

### Work

- Reuse Deal, contract, property intelligence, valuation, repair, photo, file, and title evidence.
- Add a launch-readiness checklist with source freshness and conflict visibility.
- Separate verified facts, seller statements, provider signals, Stonegate analysis, and unknowns.
- Store approved asking price, minimum acceptable economics, desired assignment fee, and approval
  authority without exposing private floors to buyers.
- Produce channel-ready summaries and the existing investor PDF from one approved package version.
- Invalidate or require reapproval when material deal facts change.
- Record who approved the package and which version each recipient received.

### Exit Criteria

- No unverified property claim is presented as fact.
- Package blockers are explicit and actionable.
- A package version is reproducible from saved evidence.
- Recipient-visible information never includes internal pricing floors or private notes.

## DS6 - Governed Live Outreach And Reply Loop

**Status: Planned.**

### Goal

Replace the simulated release with bounded, human-approved buyer communication using Stonegate's
existing communication providers.

### Work

- Add recipient selection, channel eligibility, suppression, and permission preflight.
- Draft email and SMS from the approved package without inventing facts.
- Require an authorized human to review and approve the package, recipients, and messages.
- Send idempotently through approved Resend and Twilio configurations.
- Record queued, sent, delivered, failed, bounced, blocked, replied, and opted-out states.
- Route buyer replies into the correct Buyer Inbox conversation and deal candidate.
- Create follow-up tasks from replies and approved cadence rules.
- Provide pause, cancel-unsent, retry-failed, and provider-degraded controls.
- Prevent provider callbacks or worker retries from duplicating delivery.

### Exit Criteria

- A supervised release reaches only the approved recipients once.
- Delivery and reply state reconcile to both the deal and buyer timeline.
- Suppressed or ineligible contacts are excluded with an explanation.
- The campaign can be paused without losing audit history.
- Existing seller communications remain unaffected.

## DS7 - Offer Room And Closing Protection

**Status: Planned.**

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

### Exit Criteria

- The agent can explain why the recommended buyer is stronger than a higher nominal offer.
- Primary and backup coverage remains visible until completion.
- Deadline alerts are actionable and deduplicated.
- Completed and failed outcomes update buyer history without erasing original evidence.

## DS8 - InvestorLift Provider Adapter

**Status: Planned; blocked from implementation until provider contract verification.**

### Goal

Use InvestorLift for reach, transaction intelligence, marketplace activity, and engagement signals
while Stonegate keeps ownership of the workflow and relationships.

### Work

- Obtain and review the provider materials listed in Section 9.
- Implement a provider interface before provider-specific transport logic.
- Store provider account, property, candidate, campaign, inquiry, and offer IDs as source links.
- Support bounded, replay-safe publish or guided-manual handoff based on verified capabilities.
- Stage God Mode or other buyer discoveries per deal when contractually and technically available.
- Reconcile Artemis or other engagement signals only when their semantics are documented.
- Reconcile inquiries, address requests, offers, accepted offers, and listing status.
- Record sync freshness, cost, counts, anomalies, errors, and provider request IDs.
- Provide manual refresh, retry, disconnect, and export controls.
- Preserve full Stonegate operation when the provider is unavailable or cancelled.

### Exit Criteria

- Integration behavior is based on written provider documentation, not guessed endpoints.
- Provider retries are idempotent and observable.
- External IDs and provenance survive conversion to a canonical Buyer.
- Provider downtime does not block owned-list disposition work.
- Stonegate can export its permanent buyer and deal history independently.

## DS9 - Governed Disposition Copilot

**Status: Planned; foundation exists.**

### Goal

Turn the existing review-only Copilot foundation into a measured daily sidekick without granting it
binding authority.

### Work

- Prepare fact-checked package summaries and identify missing evidence.
- Explain buyer-match strengths, conflicts, and disqualifiers.
- Draft recipient segments, email, SMS, call briefs, and follow-ups.
- Classify replies, inquiries, passes, and offer intent with confidence and evidence references.
- Recommend the next call, proof request, showing, counter, deadline action, or backup activation.
- Summarize offer differences and execution risks without selecting the final buyer.
- Propose buyer preference and reliability updates for human review.
- Record model, prompt, evidence, output, corrections, cost, and reviewer decision.
- Evaluate hallucination, package correction, match relevance, reply classification, and next-action
  usefulness before expanding authority.

### Exit Criteria

- Every recommendation cites saved Stonegate or approved provider evidence.
- The specialist can accept, correct, reject, or ignore a recommendation.
- No AI path can release outreach or bind Stonegate independently.
- Evaluation and pilot thresholds are defined and met.

## DS10 - Management Intelligence And Learning

**Status: Planned.**

### Goal

Measure whether the system and disposition specialist improve completed assignments rather than
merely increasing messages or nominal offers.

### Work

- Measure time from executed contract to package approval, first outreach, first inquiry, first
  offer, buyer selection, deposit, and close.
- Compare agent-owned, Stonegate-network, InvestorLift, and other provider sources.
- Measure assignment spread, campaign cost, cost per offer, cost per selected buyer, and cost per
  completed assignment.
- Measure buyer reply, showing, offer, deposit, closing, retrade, and fallout rates.
- Measure package corrections, match overrides, AI corrections, and backup-buyer saves.
- Build buyer reliability from documented behavior rather than subjective labels alone.
- Separate human-led and AI-assisted outcomes without claiming causation from small samples.
- Provide deal, buyer, agent, source, market, asset, and time filters.

### Exit Criteria

- Management can identify which source produced the winning buyer and completed assignment.
- Vanity metrics remain separate from completed economic outcomes.
- Reliability and agent metrics are explainable and correction-capable.
- Reports reconcile to canonical deal and finance records.

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
| DS3 | Buyer Profiles And Asset-Aware Buy Boxes | Planned |
| DS4 | Unified Explainable Deal Buyer Pool | Planned |
| DS5 | Deal Launch And Investor Package Readiness | Planned |
| DS6 | Governed Live Outreach And Reply Loop | Planned |
| DS7 | Offer Room And Closing Protection | Planned |
| DS8 | InvestorLift Provider Adapter | Planned; provider verification required |
| DS9 | Governed Disposition Copilot | Planned; foundation exists |
| DS10 | Management Intelligence And Learning | Planned |
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

DS2 now provides the specialist's daily command center. DS3-DS7 continue turning the current
provider-independent foundation into the complete relationship, matching, package, outreach,
offer, and closing system. DS8 follows only after InvestorLift supplies a
verified integration contract. DS9 and DS10 make the sidekick measurable rather than speculative.
DS11 remains a future efficiency feature because the immediate migration is expected to be mostly
manual. DS12 is the formal production-acceptance gate, while relevant parts of the current deal may
be used as supervised evidence throughout the build.
