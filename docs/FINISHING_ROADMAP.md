# Stonegate Product Finishing Roadmap

Last updated: August 22, 2026

## Purpose

This is the canonical remaining sequence for taking Stonegate from an implemented business
platform to a production-proven Georgia operation.

`SYSTEM_MAP.md` describes what exists. This roadmap includes only:

- unfinished external configuration
- real-company setup
- controlled provider acceptance
- professional review
- real-world calibration
- supervised AI pilots

Git history preserves completed build phases. A feature is not missing merely because an external
acceptance step remains.

## Status Rules

- **Implemented** means the workflow exists in code.
- **Configured** means the required production account and values are present.
- **Active** means a controlled end-to-end production test passed.
- **Accepted** means the named Stonegate owner or professional approved the result.

Do not mark a phase finished from code alone when its exit criteria require production evidence.

## Product Boundaries

- Extend the existing CRM, Inbox, calendar, buyer CRM, Finance system, and AI control plane.
- Do not create parallel business databases or a second AI system.
- PostgreSQL remains the operational source of truth.
- Posted journal entries remain the financial-statement source of truth.
- External providers connect through adapters while Stonegate retains normalized records,
  permissions, evidence, and audit history.
- Provider names and environment variables belong in `SETUP_REFERENCE.md`.
- Secret values never belong in Git or documentation.

## Current Summary

| Phase | Current state | Remaining proof |
| --- | --- | --- |
| IA private-OS organization | IA1-IA10 implemented, including the 11-destination shell, consolidated workspaces, compatibility routes, record context, and permission-filtered Settings | Complete real-role acceptance and retain compatibility evidence before removing any legacy route |
| F1 Production reliability | Reliability tooling, fail-closed authentication, fair worker scheduling, and dependency gates implemented | Restore, revocation, readiness, and optional monitoring acceptance |
| F2 Company setup | User, role, seat, team, market, and acceptance workflows implemented | Configure and test actual staff and counterparties |
| F3 Operating policy | Restrictive application gates removed at Owner direction | External policy review as Stonegate prepares live outreach |
| F4 Documents and e-signature | Storage, offer-authority snapshots, execution evidence, and SignWell workflows implemented | Production provider, document, remote-sign, and iPad-sign acceptance |
| F5 Buyers and dispositions | Buyer CRM implemented; optional DealMachine adapter disabled; campaign delivery is simulation-only | Controlled buyer placement plus a manual or implemented live delivery procedure |
| F6 Accounting and marketing | Internal books, reports, Copilots, and ad adapters implemented | CPA close and ad-provider acceptance |
| F7 Underwriting proof | Stonegate Valuation V3.1, RentCast, and RealEstateAPI candidate evidence are implemented; V2.2 is a technical rollback only | Run the AI Comp Analyst pilot, collect verified Georgia outcomes, and monitor accuracy and corrections |
| F8 Resend email | Two-way mailbox system, leased processing, bounded retry, and dead-letter handling implemented | Controlled production mailbox and failure-path acceptance |
| F9 Twilio communications | SMS, Voice, recording, transcription, reviewed AI notes, retry/exhaustion, and manual recovery implemented; seller A2P approved | Seller SMS, Voice, recording authorization, AI-note, failure, retention, and deletion acceptance before launch |
| Native VA dialer | D0-D10 foundation is implemented but was not production-accepted; the owner selected BatchDialer as the production dialer | Execute BD0 dormancy without deleting native records, evidence, migrations, or shared communication behavior |
| BatchDialer direct integration | Direct-only implementation and repository verification complete: fixed-host client, durable polling, transcript evidence gate, visible Tasks review, accepted-handoff processing, manual-appointment task, health visibility, normalized VA performance, explicit agent mapping, and draft-only evidence-cited coaching | Confirm production fact backfill, map each provider agent, run controlled qualified/appointment/review results, review one coaching draft, and reconcile provider CDRs for 24 hours |
| F10 AI pilots | All Copilots enabled in supervised draft-only mode | Model replay, measured pilots, and narrow promotion decisions |

## Active Sub-Roadmaps

- `CRM_INFORMATION_ARCHITECTURE_ROADMAP.md` owns the planned private-OS navigation, workspace
  consolidation, record-layout, route-compatibility, and role-acceptance program. It reorganizes
  the existing platform without authorizing a second CRM or duplicate business records.
- `PUBLIC_SITE_CONVERSION_ROADMAP.md` owns the seller-site conversion program.
- `AI_AUTOMATION_ROADMAP.md` owns the measured path from supervised Copilots to narrow automation.
- `BATCHDIALER_DIRECT_INTEGRATION_ROADMAP.md` owns the approved production-dialer architecture,
  native-dialer dormancy, constrained official API contract, sole direct synchronization, manual
  Stonegate appointment boundary, health, reconciliation, and production acceptance.
- `VA_DIALER_ROADMAP.md` preserves the implemented D0-D10 native-dialer architecture and evidence
  as historical engineering context. It no longer authorizes native production acceptance or the
  optional D11/D12 pilots.
- `UNDERWRITING_COMP_METHOD.md` owns the live Stonegate Valuation method, historical V2.2
  compatibility, and ongoing measured calibration.

These sub-roadmaps extend the product boundaries above. They do not authorize a parallel CRM,
communications history, or AI system.

## Recommended Order

The practical order from the current state is:

1. Deploy the completed BD0 native-dialer dormancy and direct BatchDialer runtime under the
   constrained BD1 contract. The official API is the sole BatchDialer integration.
2. Configure the owner-managed direct credential, run controlled qualified and appointment-set
   acceptance, and reconcile provider CDR identities against Stonegate for at least 24 hours.
3. Finish F8 Resend controlled acceptance.
4. Complete F2 actual staff setup as people join.
5. Finish F4 SignWell and contract acceptance before the first live seller agreement.
6. Resume F9 with direct-number seller SMS and shared-line Voice acceptance.
7. Run F5 buyer and disposition acceptance as the first contract approaches.
8. Run F1 restore and access-revocation checks before broad employee use.
9. Begin F7 outcome collection with every reviewed analysis.
10. Complete F6 accounting acceptance before relying on the first closed period.
11. Review F3 outreach and recording policy before broad campaigns or recording activation.
12. Run F10 Copilot pilots after the underlying human workflows have real operating volume.

Some phases overlap. Their exit criteria remain independent.

## F1. Production Reliability Acceptance

### Already Implemented

- API health and dependency readiness
- worker heartbeat and stale-worker readiness checks
- durable operational failures and retries
- one-item-per-operation worker sweeps that prevent a busy queue from starving later work
- independent liveness and main-loop progress/current-operation tracking; production readiness
  tolerates normal provider work and reports a stalled loop only after 600 seconds
- production API and protected-web authentication that fail closed when Clerk is incomplete
- request-type-specific approval visibility and decision checks in both the approval API and Tasks;
  only `audit:view` grants blanket approval-list visibility, and unknown types have no decision path
- Python and Node dependency audits plus explicit web lint, typecheck, and contract checks in CI
- separate throttles for seller intake, seller enrichment, conversion events, and Zapier lead
  intake; production ignores caller `X-Forwarded-For`, uses the edge-owned Cloudflare address, and
  hard-bounds process-local limiter keys
- Resend UUID claim fencing, durable validated-route checkpoints, bounded lifecycle retry,
  manager-only audited dead-letter requeue, and restricted-mailbox routing isolation
- optional owner alert webhook
- optional Sentry integration with default PII capture disabled
- database backup and guarded restore scripts
- smoke tests and scheduled readiness monitoring
- user deactivation and reassignment workflow

### Remaining Actions

1. Run an isolated restore from a real production backup.
2. Confirm the restored database opens and expected records exist.
3. Use a disposable staff account to test deactivation and immediate access loss.
4. Reassign that account's open work and verify history remains attributable.
5. Run the production smoke test against the branded website and API.
6. Confirm `/ready` reports fresh worker liveness, exposes the current operation, remains ready
   during a normal long provider call, and reports `stalled` only after the configured 600-second
   production progress threshold.
7. Confirm Cloudflare owns the production client-IP header path and add distributed edge/WAF rate
   limiting before broad traffic or multiple API instances.
8. Complete controlled Resend mailbox/dead-letter acceptance and decide the attachment malware-
   scanning control.
9. Optionally configure Sentry and an owner-controlled alert webhook.

Credential rotation and MFA rollout remain known risks but are excluded from this phase at the
Owner's current direction.

### Exit Criteria

- One real backup has been restored into an isolated database.
- One staff-revocation test has passed.
- Website, OS, API, worker, database, and key-value dependencies pass readiness checks.
- Any configured alert destination receives a controlled test.

## F2. Company Configuration And Role Acceptance

### Already Implemented

- individual users and local role assignments
- teams and team membership
- operating seats and backups
- staff role manuals and My Setup acceptance
- markets, territories, closer profiles, and availability
- campaign, script, compensation, and role-credit configuration
- counterparties and market launch checklists
- role-aware navigation and server-side permissions

### Initial Team Plan

- Austin: Owner/CEO and Acquisitions Closer
- Devon: Lead Manager and Dispositions during the initial period
- Conner: transaction paperwork, bookkeeping, and finance support
- Michael: later Lead Manager transition
- two or three individually authenticated VA Callers

The approved operating and compensation details remain in `OPERATING_MODEL.md`.

### Remaining Actions

1. Create one Stonegate user for each real employee and contractor.
2. Have each person create or use their own Clerk login.
3. Assign only the roles needed for that person's current work.
4. Configure initial teams, primary owner, backup coverage, and routing.
5. Configure Georgia markets, territories, closer hours, travel buffer, and unavailable time.
6. Approve the current VA and Lead Manager scripts.
7. Activate the approved compensation plan and current role credits.
8. Add the selected closing attorney, title/closing contacts, contractors, and vendors.
9. Have each person test their normal workflow and prohibited areas.
10. Record their role acceptance in My Setup and manager approval in Operating Model.

### Exit Criteria

- Every active person has an individual login.
- Each role can complete its work without Owner-only workarounds.
- VAs cannot access underwriting, contracts, buyers, finance, exports, or unrelated records.
- Finance and restricted mail remain visible only to authorized users.
- Staff and manager acceptance records are complete.

## F3. Operating Policy Review

### Current Product Decision

Application-level DNC screening evidence, policy approval, training acknowledgment, and broad
recording-policy gates were removed at the Owner's direction.

The system still honors:

- explicit seller opt-outs
- explicit do-not-contact values
- Stonegate company suppression
- invalid contact data
- provider failures
- SMS STOP and START state
- role and mailbox permissions

### Remaining External Actions

Before broad live outreach or recording:

1. Have the appropriate professional review Stonegate's planned states, channels, scripts, and
   contractor practices.
2. Approve seller SMS consent language and A2P campaign claims.
3. Approve call-recording disclosure and retention behavior.
4. Train VAs and employees on the approved operating policy.
5. Keep any future in-product policy tooling advisory unless the Owner explicitly requests a
   blocking control.

### Exit Criteria

- Stonegate management has approved the operating policy used by actual staff.
- Provider registration claims match the public site and real workflow.
- Recording remains disabled until its disclosure decision is documented.

## F4. Documents, Contracts, And SignWell

### Already Implemented

- versioned internal contract sources and generated PDFs
- contract packages and human approval
- purchase-agreement authority snapshots tied to the approved offer plan, underwriting version,
  seller-agreed/current transaction price, and exact governing concession
- stale-authority revalidation before approval, sending, SignWell delivery, and execution
- transaction documents, facts, parties, and checklists
- database and S3-compatible private storage adapters
- retention, checksum, private-download, and malware-scan state
- SignWell account verification and webhook registration
- envelope, recipient, event, status, and completed-document evidence
- durable one-active-send reservation, unsent-draft-first delivery, saved-draft resume, ambiguous
  outcome blocking, and monotonic webhook/API reconciliation
- tenant-scoped verified-draft attachment, audited empty-intent abandonment, one-time terminal
  failure release, and bounded public webhook ingestion
- authority mutexes across plans, agreements, concessions, and presentations while any purchase
  package remains signable, plus audited withdrawal for manually sent packages
- exact executed-document type/status/scan checks and audited manual execution attestation
- remote signature and in-person iPad signing
- simulation and focused automated tests

### Remaining Actions

1. Decide whether database document storage is acceptable for the controlled first launch or
   configure the selected Cloudflare R2 private bucket.
2. Activate SignWell using the values in `SETUP_REFERENCE.md`.
3. Verify the current Stonegate purchase-agreement source and signer fields.
4. Obtain professional approval of the Georgia language when Stonegate is ready for that review.
5. Run one complete remote-signature test.
6. Run one complete in-person iPad signing test.
7. Confirm webhook reconciliation and completed PDF storage.
8. Run one redacted contract-to-funding simulation with documents and checklist evidence.
9. Change the approved offer source after creating a test package and confirm approval/send/sign or
   execution is blocked until a new package captures current authority.
10. Test manual execution with the wrong document type, a non-executed status, and a valid exact
    executed copy plus verification reason.
11. Test the provider-create crash window with both a matching orphan draft and a verified empty
    provider account; exercise attach and abandon without creating a duplicate document.
12. Confirm authority stays frozen for every signable provider/manual package, then test provider
    cancellation/reconciliation and the audited manual withdrawal flow.

Use `GEORGIA_CONTRACT_PACKET.md` and `SIGNWELL_COUNSEL_BRIEF.md` for document boundaries.

### Exit Criteria

- An approved package is sent, signed, reconciled, and retained.
- The completed PDF and provider events attach to the correct transaction.
- Remote and in-person signatures use the same approved package and audit trail.
- Missing or conflicting required facts block release.
- A stale offer plan, underwriting version, seller agreement, price, or concession blocks release.
- Manual and provider completion retain the exact executed document and authority evidence.
- Unauthorized roles cannot send or download restricted documents.

## F5. Buyer And Disposition Acceptance

### Already Implemented

- buyer CRM, criteria, proof, capacity, engagement, and offers
- disposition cases, package approval, matching, campaigns, selection, and reconciliation
- deterministic buyer ranking
- optional disabled DealMachine adapter retained only for deliberate future reactivation
- duplicate protection and audit history
- Disposition Copilot in supervised draft-only mode
- simulation-only campaign release that records the approved recipients without sending outreach

### Current Provider Decision

DealMachine is not part of the current launch plan. Its adapter remains disabled and must not be
presented to staff as a working buyer source. It can be evaluated later only through a deliberate
Owner decision and a new quality, billing, contact-permission, and production acceptance test.

The current **release campaign** action is also not an external send. It creates a
`simulated_released` campaign, marks reviewed recipients in the case, and records audit evidence.
Stonegate therefore needs either a documented controlled manual email/call procedure for the first
deal or a separately implemented and accepted live disposition-delivery channel.

### Remaining Actions

1. Build the first internal buyer list and verify criteria, contact permission, capacity, and proof.
2. Decide and document whether the first controlled deal will use individually reviewed manual
   email/calls or wait for an implemented live campaign channel.
3. Send one approved deal package only after operational email and the selected delivery procedure
   are accepted.
4. Confirm the simulation action itself sends no email or SMS and cannot be mistaken for delivery.
5. Record engagement, offers, deposits, primary buyer, backup buyer, and verified proof.
6. Complete one contract-to-buyer-to-reconciliation simulation before the first live assignment.
7. If DealMachine or another buyer-data source is reconsidered later, run a separate provider
   quality, credit/cost, duplicate, DNC, and selective-import acceptance phase first.

### Exit Criteria

- Provider candidates do not overwrite trusted buyer records.
- One approved package reaches a controlled audience.
- Replies and offers attach to the correct case.
- Proof and buyer-selection approval cannot be bypassed.
- Reconciliation produces the expected revenue, deductions, compensation, and margin.
- Staff can tell the difference between simulation evidence and an actual external delivery.

## F6. Accounting And Marketing Acceptance

### Already Implemented

- internal double-entry ledger and chart of accounts
- accounting periods, journal preparation, approval, posting, reversal, and source links
- operational posting rules
- vendors, bills, W-9 status, obligations, and private evidence
- bank account labels, statement preview/import, matching, and reconciliation
- Profit and Loss, Balance Sheet, Cash Flow, Trial Balance, General Ledger, schedules, and CPA ZIP
- Finance and Tax Copilots in supervised draft-only mode
- Google Data Manager and Meta Conversions API adapters
- stable event IDs, hashed identifiers, retries, and provider audit

### Remaining Accounting Actions

1. Have the CPA approve entity facts, accounting method, tax year, opening date, chart of accounts,
   and posting policies.
2. Enter and approve opening balances.
3. Process one real or fully redacted funded deal through reconciliation and journals.
4. Import and reconcile one actual statement.
5. Complete one month close.
6. Have the CPA review the statements and CPA export.
7. Record corrections through adjustments or reversals.

### Remaining Marketing Actions

1. Preserve the accepted Meta Pixel/Conversions API configuration and configure Google only when
   that ad account is ready.
2. Map qualified lead, appointment, contract, and funded events to provider actions.
3. Enter credentials in Render.
4. Use provider test modes for each newly activated delivery path.
5. Confirm acceptance, deduplication, retries, and audit history.
6. Keep budgets and published campaign changes under human authority.
7. Keep the production Facebook Page ID and allowed instant-form IDs current. Monitor the
   secretless Zapier endpoint's burst limit, rolling daily circuit, accepted form IDs, and Zap
   History; these controls reduce abuse but do not cryptographically prove Meta provenance.
8. Run one real production-form acceptance from Meta through Zapier into the CRM, property
   research, speed-to-lead work, and each opted-in employee's internal SMS alert.

### Exit Criteria

- Posted journals balance and reconcile to the same closed period.
- One funded deal produces one reviewed accounting result.
- One bank statement reconciles with no unexplained difference.
- The CPA accepts the first report package and operating procedure.
- Test conversion events reach the correct ad accounts without duplicates.

## F7. Underwriting Calibration And Market Proof

### Already Implemented

- Underwriting V2.2 complete-analysis workflow
- address retries and subject identity checks
- recorded-sale continuity when AVM coverage fails
- bounded cited public-record research
- comp screening, outlier handling, price-per-square-foot context, and condition review
- ARV, as-is, repair, offer, confidence, and investor/client reports
- immutable comp-review versions
- adaptive preferred, expanded, extended, and manual closed-sale discovery
- comp deduplication, A-D grades, subdivision evidence, and precise shortage guidance
- provisional closed-sale continuity when the AVM is unavailable
- verified outcome records
- market scorecards and methodology decision ledger
- weighted interpolated adjusted-sale ranges with explicit range drivers and no generic percentage
  padding
- normalized RentCast and RealEstateAPI closed-sale evidence with cross-provider deduplication,
  field provenance, conflict visibility, provider-failure isolation, and credit accounting
- internal provider-audit reporting that keeps external AVMs out of Stonegate ARV and offer math
- a bounded AI Comp Analyst draft that cites saved evidence, identifies review work, and has no
  price or seller authority

### Implemented In-Place V3 Upgrade

`UNDERWRITING_COMP_METHOD.md` defines U3.1-U3.10. The upgrade preserves the existing subject,
market-analysis, repair-estimate, field-inspection, underwriting-version, approval, report, audit,
and calibration records. Its target capabilities are:

- adaptive closed-sale discovery with explicit search expansion and manual verified comps
- separate active/pending, AVM, market-trend, and public-research evidence
- a focused comp review workbench
- market-supported adjustments replacing full price-per-square-foot scaling as the controlling
  transformation
- a guided repair scope with Georgia cost catalog, ranges, overrides, and unknown-risk treatment
- human-confirmed AI repair assistance and an upgraded iPad walkthrough
- one progressive Quick Comp, Desk Review, Walkthrough, and Offer Decision workflow
- updated reports, calibration, internal rollback comparison, and supervised operation

### Implemented U4 Comp Intelligence Extension

U4 is implemented behind default-safe controls. RealEstateAPI comparable evidence can be disabled,
observed in shadow mode without changing valuation math, or admitted as candidate closed-sale
evidence after a measured promotion decision. Exact subject matching, saved provider records, and
snapshot reuse bound cost and data scope. Provider failures do not prevent RentCast-backed analysis.

The optional AI Comp Analyst runs only in draft mode against evidence already supplied by
Stonegate. Its structured output can explain comp inclusion, source conflict, uncertainty, and
missing review questions. It cannot browse for facts, invent evidence, set ARV, calculate an offer,
recommend a seller ceiling, or apply a dollar adjustment. The deterministic V3.1 calculator
continues to own the supported adjusted-sale range and all dependent economics.

Both capabilities default to disabled until configured. Internal reports retain provider status,
overlap, conflicts, credit use, latency, external benchmarks, and the AI draft. Client reports do
not expose provider operations, model details, or internal review notes.

### Remaining Actions

For every suitable reviewed Georgia analysis:

1. Preserve the original prediction.
2. Record the later verified expert, appraisal, resale, contract, disposition, repair, or closing
   outcome.
3. Review selected and excluded comps.
4. Classify provider or methodology failures.
5. Review market-level bias, absolute error, and range coverage.
6. Do not change formulas from anecdotal cases.
7. Consider another provider only when measured error or operator time justifies it.
8. Require the configured minimum evidence and human approval for method changes.

For ongoing V3 validation:

1. Use the implemented U3.1 fixtures and baseline measurement before changing formulas.
2. Use implemented U3.2-U3.5 adaptive search, supporting evidence, manual comps, operator review,
   and market-supported adjustments before repair expansion.
3. Record verified outcomes and review misses without asking staff to select an engine.
4. Validate implemented U3.6 guided repairs against walkthroughs, written bids, and completed
   Georgia projects; adjust only through a new catalog version.
5. Validate implemented U3.7 iPad autosave, field scope, and human-reviewed AI suggestions during
   real walkthroughs; AI remains unable to confirm repairs or set prices.
6. Validate the implemented U3.8 workspace and U3.9 reports/scorecards with real appointment and
   verified-outcome cases.
7. Monitor verified cases by Georgia market and retain V2.2 only as an engineering rollback while
   V3 remains supervised and human-approved.

For the U4 controlled rollout:

1. Compare RealEstateAPI candidate evidence with RentCast for sale coverage, duplicate matching,
   material field conflicts, latency, and provider credits on the same analyses.
2. Review every cross-provider conflict and confirm that canonical values and source provenance
   remain reproducible from the saved record.
3. Keep RealEstateAPI in candidate mode only while it shows useful evidence gain without
   unacceptable error, operator burden, or credit cost.
4. Run the AI Comp Analyst only in draft mode after fixed-case replay confirms evidence citations,
   prohibited-price controls, incomplete-evidence behavior, and human-review routing.
5. Measure operator acceptance, correction, rejection, latency, and time saved before any broader
   enablement decision.

### Exit Criteria

- V3 remains the default only while unsupported cases stop for review and measured outcomes do not
  show a material accuracy or operator-burden regression.
- The first market has enough verified cases for the approved review threshold.
- Material bias and failure patterns are documented.
- Stonegate has decided whether RentCast alone or RentCast plus RealEstateAPI candidate evidence is
  adequate for that market.
- The RealEstateAPI evaluation documents coverage gain, conflicts, provider failures, latency, and
  credit use while candidate mode remains active.
- The AI Comp Analyst pilot shows evidence-bound drafts with no prohibited valuation or offer
  authority and an acceptable human-correction burden.
- Formula and provider decisions are evidence-backed, versioned, and human approved.

Calibration continues after launch.

## F8. Resend Mailbox Acceptance

### Already Implemented

- provider-neutral email records and Resend delivery
- named, team, general, and restricted aliases
- sender grants, signatures, templates, To/CC/BCC, and attachments
- new email without fake property leads
- signed inbound webhooks and recovery
- exact and bounded reply/thread routing
- routing-exception review
- shared Inbox views and permissions
- assignee, team, watcher, and sender notifications
- first-response, next-response, and owner-escalation timers
- provider status, idempotency, and failure evidence
- production domain, DNS, API key, and webhook configuration
- UUID-fenced processing leases and stale-claim recovery that prevent an expired worker from
  overwriting the reclaimed attempt
- durable validated-route checkpoints and bounded retry for early lifecycle events
- manager-only **Failed events** review with reason-required audited dead-letter requeue
- automatic and manual enforcement that restricted aliases route only to restricted conversations
- attachment-size enforcement from metadata, response length, and streamed bytes

### Remaining Actions

Using company-controlled addresses:

1. Confirm Resend shows sending and receiving DNS as verified.
2. Confirm SPF and DKIM; add and monitor DMARC.
3. Send from each approved named and department alias.
4. Test To, CC, BCC, signatures, templates, and attachments.
5. Reply to each alias and confirm the expected person or team inbox.
6. Test one general conversation not tied to a lead.
7. Test one restricted accounting conversation.
8. Confirm unread, Needs Reply, first-response, and follow-up timers.
9. Test a bounce or controlled failure.
10. Confirm duplicate webhooks do not duplicate messages.
11. Confirm an unauthorized user cannot view or send restricted correspondence.
12. Activate closing-party and buyer-package email after the tests pass.
13. Force one temporary processing failure and confirm the event retries after its delay.
14. Simulate an abandoned processing claim and confirm lease recovery plus stale-worker fencing.
15. Test declared and streamed oversize attachments, then confirm a poison event reaches dead-letter
    without blocking later mail and remains visible under manager-only **Failed events**.
16. Correct the poison event, enter a reason, requeue it once, and confirm the audit event.
17. Confirm an early lifecycle webhook retries until its outbound CRM record exists and a validated
    inbound route survives a later attachment/provider failure.
18. Confirm neither automatic nor manual routing can place restricted-alias mail in a standard-
    visibility conversation.
19. Complete external mailbox acceptance and activate malware scanning or formally accept a limited
    manual safe-attachment procedure.

### Exit Criteria

- Outbound and inbound email remains in one correct Stonegate thread.
- Every alias routes to the intended people and permissions.
- Attachments and restricted mail remain protected.
- Delivery and response problems become visible work.
- No Gmail or Google OAuth account is required.

## F9. Twilio SMS And Voice Acceptance

### Already Implemented

- Twilio SMS adapter
- signed inbound and delivery callbacks
- STOP, START, suppression, consent, idempotency, and delivery state
- company lines, cellphone forwarding, inbound routing, status history, and missed-call work
- recording callbacks, private media, disclosure state, retention, and deletion
- OpenAI transcription, speaker segments, structured notes, and human review
- a durable transcription checkpoint before note generation, so note retries reuse paid transcript
  text, plus exponential retry for temporary Call Intelligence failures, a terminal `exhausted`
  state, and an audited Inbox action that queues an authorized manual retry

### Current Status

Stonegate's dedicated seller-inquiry A2P campaign is approved, and internal new-lead alerts for
website and Facebook intake have prior controlled-delivery evidence through Stonegate's
direct-number setup. Repeat that alert
acceptance after the worker credential correction before relying on it for a live ad window. Full
seller SMS acceptance, shared acquisitions Voice routing, and production Voice acceptance remain.
A Messaging Service is optional for the direct-number mode. Another company's campaign, number, or
webhooks must not be used.

### Remaining SMS Actions

1. Confirm Stonegate's dedicated acquisitions 10DLC number remains registered for the approved
   seller-inquiry campaign.
2. Confirm the Account SID, Auth Token, direct sender number, and webhook base URL are present on
   both the API and worker. A Messaging Service SID is optional in this mode.
3. Configure the signed inbound and status callbacks.
4. Repeat one internal staff-alert delivery test, then test seller outbound, delivered, failed,
   inbound, STOP, blocked send, START, HELP, and callback replay as a separate use case.
5. Keep the future buyer/dispositions messaging purpose separate unless its traffic is accurately
   covered by an approved campaign.

### Remaining Voice Actions

1. Use Stonegate's dedicated Voice number.
2. Enter the Account SID, Auth Token, acquisitions number, webhook base URL, and Voice enablement
   values in Render.
3. Configure each number's inbound Voice webhook.
4. Save Austin's and Devon's cellphone destinations and enable forwarding.
5. Test simultaneous inbound ringing, press-1 acceptance, no-answer, voicemail, missed-call work,
   and reassignment.
6. Test outbound cellphone bridging, Stonegate caller ID, and conversation history.
7. For the Owner-selected Georgia-only one-party mode, verify the recorded authorization and
   retention state even when the optional spoken disclosure is blank. Treat the operating policy
   as pending documented acceptance, and do not extend it to another state without reviewing the
   applicable policy.
8. Test recording, transcription, immediate empty-field CRM population, narrative
   review, internal Inbox/lead note creation, private access, and deletion.
9. Force a temporary transcription or note-generation failure and confirm automatic retry.
10. Exhaust a controlled test transcript, confirm the Inbox explains the state, then use **Retry
    call intelligence** and confirm the successful result remains tied to the same call.

### Exit Criteria

- Dedicated SMS and Voice acceptance suites pass.
- Every communication attaches to the correct conversation.
- Seller thread history survives staff reassignment.
- Opt-out and provider failures remain visible and enforceable.
- Recording authorization remains an explicit, state-scoped operating decision.
- Temporary and exhausted Call Intelligence failures are visible and recoverable without creating
  a duplicate call record.

## F10. AI Production Pilots

### Already Implemented

- one governed AI runtime and shared specialist portfolio
- eight staff-facing Copilots in existing workspaces
- versioned prompts, tools, knowledge, policies, and source evidence
- golden evaluation library and review workflow
- structured model runner, routing, limits, costs, and shutdown
- run, tool, knowledge, review, correction, and promotion history
- draft-only Prospecting, Lead Manager, Acquisitions, Transaction, Disposition, Finance, Tax,
  Marketing, and Executive assistance
- external-action contracts and zero-delivery simulations
- event-driven Lead Manager preparation for website, manual, prospecting-handoff, and inbound-call
  leads, with assigned review in Tasks and accepted briefs logged as internal notes
- Call Intelligence linkage from recording and transcript processing through automatic internal
  note placement to the shared orchestrator-event and run history

### Remaining Actions

For each Copilot separately:

1. Redact representative real Stonegate cases.
2. Review expected outputs and quality thresholds.
3. Replay cases through the production model route.
4. Run a supervised draft-only pilot.
5. Measure factual accuracy, evidence coverage, acceptance, correction, rejection, critical
   failures, latency, cost, time saved, and business outcome.
6. Correct prompts, tools, knowledge, or deterministic workflow gaps.
7. Keep consequential actions human controlled.
8. Consider only one narrow reversible internal promotion at a time.

External sends remain locked until the exact provider, audience, consent, template, monitoring,
canary, automatic pause, and rollback conditions pass a separate release.

### Exit Criteria

- Every promoted capability passes its own evaluation and supervised pilot.
- Staff can review, correct, reject, pause, and audit outputs.
- No Copilot approves offers, contracts, buyers, payments, journals, compensation, legal
  conclusions, tax conclusions, or suppression overrides.
- Any autonomy is limited to one explicitly approved capability and tool.

## Definition Of Launch-Ready

Stonegate is ready for controlled first-market operations when:

1. Actual staff accounts and role acceptance are complete.
2. The production backup, restore, readiness, and access-revocation checks pass.
3. Resend email passes controlled acceptance.
4. SignWell and the actual contract package pass remote and iPad acceptance before live signing.
5. Dedicated Twilio SMS and Voice pass after A2P approval. Because call notes are launch-critical,
   the approved recording authorization, private media, transcription, structured AI draft, human
   correction/rejection/apply, failure visibility, retention, and deletion also pass end to end.
6. One buyer and disposition simulation reaches reconciliation.
7. The accounting process has an accepted opening and first close plan.
8. Underwriting outcomes are recorded from the first live analyses onward.
9. Copilots remain supervised until their own pilots pass.
10. The Owner has current user, setup, recovery, and escalation instructions.
11. One production Facebook instant form reaches the same CRM record, automatic property research,
    speed-to-lead work, and every opted-in staff alert without duplication; the form allowlist and
    secretless-ingress monitoring procedure are recorded.
12. Purchase-agreement authority and manual/provider execution evidence pass both success and
    stale-source blocking tests.
13. Before the first deal is marketed, Stonegate has either an accepted controlled manual buyer-
    outreach procedure or an implemented live disposition-delivery channel. A simulated campaign
    alone is not delivery.

Launch-ready does not mean autonomous. It means the human operation can run through one controlled,
auditable system while unaccepted providers and AI actions remain clearly bounded.
