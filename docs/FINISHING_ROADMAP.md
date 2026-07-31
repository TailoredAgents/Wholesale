# Stonegate Product Finishing Roadmap

Last updated: July 30, 2026

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
| IA private-OS organization | IA1 contract, IA2 11-destination shell, and IA3 permission-filtered Settings consolidation implemented | Implement IA4 through IA10 with route compatibility and role acceptance |
| F1 Production reliability | Reliability tooling implemented | Restore, revocation, readiness, and optional monitoring acceptance |
| F2 Company setup | User, role, seat, team, market, and acceptance workflows implemented | Configure and test actual staff and counterparties |
| F3 Operating policy | Restrictive application gates removed at Owner direction | External policy review as Stonegate prepares live outreach |
| F4 Documents and e-signature | Storage and SignWell workflows implemented | Production provider, document, remote-sign, and iPad-sign acceptance |
| F5 Buyers and dispositions | Buyer CRM and DealMachine adapter implemented | Provider activation near first deal and full placement simulation |
| F6 Accounting and marketing | Internal books, reports, Copilots, and ad adapters implemented | CPA close and ad-provider acceptance |
| F7 Underwriting proof | V2.2 and calibration workflows implemented | Verified Georgia outcomes and operator review |
| F8 Resend email | Two-way mailbox system implemented and provider configured | Controlled production mailbox acceptance |
| F9 Twilio communications | SMS, Voice, recording, and transcription code implemented | A2P approval and dedicated provider acceptance |
| F10 AI pilots | All Copilots enabled in supervised draft-only mode | Model replay, measured pilots, and narrow promotion decisions |

## Active Sub-Roadmaps

- `CRM_INFORMATION_ARCHITECTURE_ROADMAP.md` owns the planned private-OS navigation, workspace
  consolidation, record-layout, route-compatibility, and role-acceptance program. It reorganizes
  the existing platform without authorizing a second CRM or duplicate business records.
- `PUBLIC_SITE_CONVERSION_ROADMAP.md` owns the seller-site conversion program.
- `AI_AUTOMATION_ROADMAP.md` owns the measured path from supervised Copilots to narrow automation.
- `VA_DIALER_ROADMAP.md` now owns the one-by-one VA calling workflow. External multi-line dialing
  and BatchDialer were retired by Owner decision on July 30, 2026.

These sub-roadmaps extend the product boundaries above. They do not authorize a parallel CRM,
communications history, or AI system.

## Recommended Order

The practical order from the current state is:

1. Execute the CRM information-architecture roadmap while preserving current route compatibility.
2. Finish F8 Resend controlled acceptance.
3. Complete F2 actual staff setup as people join.
4. Finish F4 SignWell and contract acceptance before the first live seller agreement.
5. Resume F9 immediately after A2P approval.
6. Run F5 buyer and disposition acceptance as the first contract approaches.
7. Run F1 restore and access-revocation checks before broad employee use.
8. Begin F7 outcome collection with every reviewed analysis.
9. Complete F6 accounting acceptance before relying on the first closed period.
10. Review F3 outreach and recording policy before broad campaigns or recording activation.
11. Run F10 Copilot pilots after the underlying human workflows have real operating volume.

Some phases overlap. Their exit criteria remain independent.

## F1. Production Reliability Acceptance

### Already Implemented

- API health and dependency readiness
- worker heartbeat and stale-worker readiness checks
- durable operational failures and retries
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
6. Confirm `/ready` reports a fresh worker heartbeat.
7. Optionally configure Sentry and an owner-controlled alert webhook.

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
- transaction documents, facts, parties, and checklists
- database and S3-compatible private storage adapters
- retention, checksum, private-download, and malware-scan state
- SignWell account verification and webhook registration
- envelope, recipient, event, status, and completed-document evidence
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

Use `GEORGIA_CONTRACT_PACKET.md` and `SIGNWELL_COUNSEL_BRIEF.md` for document boundaries.

### Exit Criteria

- An approved package is sent, signed, reconciled, and retained.
- The completed PDF and provider events attach to the correct transaction.
- Remote and in-person signatures use the same approved package and audit trail.
- Missing or conflicting required facts block release.
- Unauthorized roles cannot send or download restricted documents.

## F5. Buyer And Disposition Acceptance

### Already Implemented

- buyer CRM, criteria, proof, capacity, engagement, and offers
- disposition cases, package approval, matching, campaigns, selection, and reconciliation
- deterministic buyer ranking
- DealMachine adapter, provider status, discovery runs, candidates, evidence, and selective import
- duplicate protection and audit history
- Disposition Copilot in supervised draft-only mode

### Current Provider Decision

DealMachine is the selected first buyer-data provider. Subscription and API activation are
deliberately deferred until Stonegate is close to a contracted deal so monthly cost is not wasted.

### Remaining Actions

1. Activate the appropriate DealMachine API access near the first deal.
2. Run controlled buyer discovery for a known market and property.
3. Review data quality, contacts, activity, score explanations, duplicates, and cost.
4. Import only approved candidates into the existing buyer CRM.
5. Verify initial buyer criteria and proof.
6. Send one approved deal package after operational email is accepted.
7. Record engagement, offers, deposits, primary buyer, and backup buyer.
8. Complete one contract-to-buyer-to-reconciliation simulation.

### Exit Criteria

- Provider candidates do not overwrite trusted buyer records.
- One approved package reaches a controlled audience.
- Replies and offers attach to the correct case.
- Proof and buyer-selection approval cannot be bypassed.
- Reconciliation produces the expected revenue, deductions, compensation, and margin.

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

1. Configure the approved Google and Meta advertising accounts.
2. Map qualified lead, appointment, contract, and funded events to provider actions.
3. Enter credentials in Render.
4. Use provider test modes for controlled delivery.
5. Confirm acceptance, deduplication, retries, and audit history.
6. Keep budgets and published campaign changes under human authority.

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
- verified outcome records
- market scorecards and methodology decision ledger

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

### Exit Criteria

- The first market has enough verified cases for the approved review threshold.
- Material bias and failure patterns are documented.
- Stonegate has decided whether RentCast is adequate for that market.
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
- browser Voice tokens and call intents
- company lines, inbound routing, status history, and missed-call work
- recording callbacks, private media, disclosure state, retention, and deletion
- OpenAI transcription, speaker segments, structured notes, and human review

### Current Blocker

Stonegate's dedicated A2P campaign failed its initial provider review and requires correction,
resubmission, approval, and number attachment. Another company's campaign, number, or webhooks must
not be used.

### Remaining SMS Actions

1. Resubmit the A2P campaign using the current branded URLs and actual consent flow.
2. Create or select Stonegate's dedicated Messaging Service.
3. Attach the dedicated approved 10DLC number.
4. Enter the values in Render.
5. Configure the signed inbound and status callbacks.
6. Test outbound, delivered, failed, inbound, STOP, blocked send, START, HELP, and callback replay.

### Remaining Voice Actions

1. Use Stonegate's dedicated Voice number.
2. Create the API key SID and secret for browser tokens.
3. Create the TwiML App and configure outbound instructions.
4. Enter Voice values in Render.
5. Configure inbound, status, dial-result, recording, and disclosure callbacks.
6. Test browser registration, outbound, inbound, no-answer, missed-call work, and reassignment.
7. Keep recording disabled until the Owner approves the disclosure and retention behavior.
8. When approved, test recording, transcription, review, private access, and deletion.

### Exit Criteria

- Dedicated SMS and Voice acceptance suites pass.
- Every communication attaches to the correct conversation.
- Seller thread history survives staff reassignment.
- Opt-out and provider failures remain visible and enforceable.
- Recording activation is an explicit separate decision.

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
5. Dedicated Twilio communications pass after A2P approval, or Stonegate launches with those
   channels deliberately disabled and a documented manual communication process.
6. One buyer and disposition simulation reaches reconciliation.
7. The accounting process has an accepted opening and first close plan.
8. Underwriting outcomes are recorded from the first live analyses onward.
9. Copilots remain supervised until their own pilots pass.
10. The Owner has current user, setup, recovery, and escalation instructions.

Launch-ready does not mean autonomous. It means the human operation can run through one controlled,
auditable system while unaccepted providers and AI actions remain clearly bounded.
