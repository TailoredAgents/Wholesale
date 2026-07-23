# Roadmap

Last updated: July 22, 2026

This is the canonical Stonegate build sequence. It follows the approved ten-phase operating plan
from reliability through the integrated AI agent system.

The completed interface and public-site modernization track is defined separately in
`EXPERIENCE_UPGRADE_ROADMAP.md`. It improves organization, usability, aesthetics, accessibility,
performance, and conversion measurement without replacing the business-workflow sequence below.

`CURRENT_STATE.md` is the source of truth for what exists today. `OPERATING_MODEL.md` defines the
business roles, handoffs, compensation policy, AI portfolio, and operating standards that these
phases implement.

Phase 10 now has a dedicated implementation sequence in `AI_AUTOMATION_ROADMAP.md`.
`AI_AGENTS.md` is the technical source of truth for agent architecture and authority.

## Status Definitions

- **Complete:** The phase exit criteria have been demonstrated.
- **Partial:** Useful production code exists, but one or more material deliverables remain.
- **Foundational:** Supporting records or screens exist, but the end-to-end workflow is not ready.
- **Not started:** No material implementation exists yet.

## Parallel Integration Track

Status: Waiting on external A2P review and provider configuration.

Twilio, Google Workspace email, and custom-domain setup run in parallel with the numbered build
phases. They do not change the business-workflow order and should not leave internal development
idle.

The application code for SMS, Voice, recording/transcription, AI call review, and Google Workspace
email is implemented. Production acceptance remains pending for:

- Approval of Stonegate's dedicated A2P Campaign and attachment of its dedicated SMS number.
- Final Twilio Messaging Service, sender, Voice API key, and TwiML App configuration.
- Recording disclosure and retention-policy approval before recording is enabled.
- Custom-domain selection and Render, Clerk, CORS, Google, and provider URL updates.
- Google Workspace domain, operational mailboxes, OAuth configuration, and mailbox connections.

## Phase Status Snapshot

| Phase | Status | Current position |
| --- | --- | --- |
| 1. Reliability and Test Foundation | Partial | Implementation complete; production operator checks remain |
| 2. Operating Model Data Foundation | Complete | Markets, campaigns, versioned economics, role credits, operating modes, and launch controls are auditable |
| 3. Campaign and List Management | Complete | CSV imports, screening evidence, costs, callable batches, and quality reporting are operational |
| 4. VA Prospecting Workbench | Complete | Guided assigned queue, approved scripts, callbacks, handoff review, and scorecards are operational |
| 5. Lead Manager Operating System | Complete | SLA-controlled handoff, guided qualification, daily queue, and scorecards are operational |
| 6. Appointments and Field Acquisitions | Complete | Dispatch, month/week/day calendar, meeting brief, mobile inspection, negotiation, evidence transfer, and scorecards are operational |
| 7. Underwriting and Offer Governance | Complete | Explainable valuation, approved authority, concessions, and price discussions are auditable end to end |
| 8. Contracts and Transaction Coordination | Complete | Controlled contract packages, private documents, closing parties, deadlines, evidence, and funding gates are operational |
| 9. Buyers, Dispositions, and Finance | Complete | Provider-neutral buyer placement, disposition, reconciliation, compensation, and accounting export are operational |
| 10. Integrated AI Agent System | Partial | AI1-AI5 are implemented in code; production signoff, measured pilots, and remaining role copilots remain |

Phase 7 was intentionally advanced before Phases 2-6 were complete because dependable comps and
offer controls were prioritized for seller conversations. That work is retained. It does not mark
the earlier dependencies complete or require any rework.

## Phase 1: Reliability And Test Foundation

Status: Partial. Implementation is complete; production verification remains.

Goal: Make continued development and deployment safe without depending on live providers.

Delivered:

- Worker heartbeat, grouped failures, isolated retries, and readiness checks.
- Threshold-based alert webhooks and an external `/ready` monitoring target.
- Guarded database backup and isolated restore-verification scripts.
- Deterministic demo organizations, users, leads, appointments, underwriting, transactions,
  buyers, communications, and provider-safe SMS/email simulators.
- Deployment smoke tests, CI shell validation, access-revocation coverage, and production
  simulation safeguards.
- Operator procedures in `PHASE_1_RELIABILITY.md`.

Remaining:

- Configure an owner-controlled production alert destination and external uptime monitor.
- Run and record the first isolated production restore drill.
- Run and record the production access-revocation check.

Result: New features can be developed and tested without damaging production or requiring live
providers.

## Phase 2: Operating Model Data Foundation

Status: Complete.

Goal: Make the database and permissions accurately represent Stonegate's approved operating model.

Delivered:

- Separate owner, Lead Manager, Acquisitions Closer, disposition, coordination, and restricted VA
  user/team responsibilities.
- Organization-scoped permissions, user administration, team assignment, and append-only audits.
- Calling-list records and assignments.
- First-class markets, territories, outreach campaigns, and pre-lead prospects with a management
  workspace, normalization, source-row deduplication, and audit events.
- Cold records remain prospects with suppression review pending until a later qualified handoff
  creates a CRM lead.
- Foundational compensation rules, revenue, deduction, and calculation records.
- Owner-activated compensation plan versions with acquisition reserve, company-margin target,
  role percentages, caps, effective dates, and immutable historical versions.
- Explicit lead-level role credits with contribution evidence, approval decisions, and a 100%
  allocation ceiling per role.
- Versioned human-led, AI-operated/human-managed, and human-oversight disposition modes. AI modes
  remain locked until their later evaluation and approval requirements are satisfied.
- Versioned market launch checklists covering service area, economics, legal review, communications,
  closing partners, buyers, staffing, attribution, and final owner approval.
- Dedicated owner-level permission gates and append-only audit events for every new write.
- A dedicated Business Setup workspace for plan history, contribution review, and launch evidence.

Result: The database accurately represents how Stonegate operates before specialized workspaces are
built on it.

## Phase 3: Campaign And List Management

Status: Complete.

Goal: Manage outreach lists, assignment, compliance evidence, cost, and quality inside Stonegate.

Delivered:

- Campaign and pre-lead prospect records with import lineage, cost, suppression, and quality
  workflows.
- Calling lists, lead entries, VA assignment, attempt history, dispositions, and progress.
- Lead address normalization, conservative duplicate review, merge, and merge auditing.
- Organization-level suppression and consent enforcement in communication workflows.
- CSV import with reusable vendor mappings, preview-before-commit, exact-file replay protection,
  and retained row-level validation, duplicate, suppression, and review outcomes.
- Prospect telephone and canonical property-address normalization before CRM lead creation.
- Import-time company suppression and imported vendor DNC screening with durable evidence. Records
  without clear DNC evidence may be retained for review but cannot enter a calling batch.
- Audited manager screening review can attach a later provider/reference result and recalculate
  eligibility without erasing the original import evidence.
- Campaign budgets, list-purchase and enrichment costs, exact VA labor attribution, and prospect
  calling batches that admit only eligible records.
- Campaign progress, spend, remaining budget, bad-data rate, duplicate rate, conversion rate,
  cost-per-prospect, cost-per-callable-record, and batch completion reporting.
- A dedicated Campaigns workspace for performance, mappings, imports, costs, batches, and file
  history.

Result: Stonegate can manage outreach internally without disconnected spreadsheets.

## Phase 4: VA Prospecting Workbench

Status: Complete.

Goal: Give cold callers a focused, restricted workflow for working assigned prospects and handing
off genuine seller interest.

Delivered:

- Restricted VA role, export prevention, assigned-list access, attempt history, dispositions, and
  audited VA-to-acquisitions handoff.
- Handoff ownership, watcher, notification, and read-only controls.
- Simulated communication providers for development while Twilio remains pending.
- One-prospect-at-a-time calling workspace.
- Versioned approved caller script and required outcome rules.
- Guided interest questions and callback scheduling from the prospect queue.
- Clear warm-lead creation and handoff review inside the dedicated workspace.
- Daily VA performance, connect, handoff, data-quality, and call-quality scorecards.
- Immutable attempt history tied to the exact approved script version and assigned prospect batch.
- DNC and wrong-number outcomes immediately block further queue use; callback outcomes return only
  when due.
- Warm prospects become CRM leads only at handoff, preserving campaign attribution, qualification,
  appointments, conversation ownership, owner watchers, and review history.
- Acquisitions can accept or return a handoff with a required correction reason. Corrections create
  a new attempt rather than rewriting the original call.

Result: A VA can work an assigned list and hand interested sellers to the Lead Manager without
unnecessary access to the main OS.

## Phase 5: Lead Manager Operating System

Status: Complete.

Goal: Ensure every interested seller receives structured qualification, ownership, nurture, and
appointment follow-up.

Delivered:

- Audited warm handoff, conversation assignment, watchers, owner notifications, and workload
  visibility.
- Qualification gaps, lead quality, urgency, and deterministic next-best-action guidance.
- Follow-up plans, next-contact tasks, neglected-lead notifications, saved views, duplicate merge,
  and qualified appointment creation.
- Shared inbox with chronological SMS, email, calls, recordings, transcripts, and internal notes.
- Internal calendar, appointment reminders, and team workload reporting.
- A configurable warm-handoff acceptance SLA with worker-driven escalation, management alerts,
  age visibility, and immutable audit evidence.
- A dedicated Lead Manager daily desk for handoff acceptance, qualification, due follow-up,
  same-day appointments, and neglected-lead exceptions.
- Automatic workload-aware routing for public website inquiries, plus migration of existing active
  CRM leads into the same controlled queue.
- Versioned, manager-approved guided qualification standards. Each completed session retains the
  exact script version, structured answers, completeness score, user, and timestamp.
- Required dated next actions for every active qualified lead. Completion creates the CRM task,
  updates the lead, and creates an internal appointment when appropriate.
- Trailing 30-day scorecards for acceptance speed, SLA compliance, qualification, appointments
  set and held, no-shows, contracts, and follow-up protection.
- Lead Manager and owner permissions keep individual queues scoped while management retains team
  visibility and intervention rights.

Result: Every interested seller receives structured qualification and follow-up.

## Phase 6: Appointments And Field Acquisitions

Status: Complete.

Goal: Prepare for, conduct, document, and complete acquisition appointments inside Stonegate.

Delivered:

- Internal Stonegate calendar with reschedule, cancel, no-show, complete, outcome, recovery, and
  reminder workflows.
- Appointment ownership, notifications, notes, lead context, and underwriting access.
- Dedicated `/os/field-operations` dispatch desk with qualified-lead queue, explainable slot
  evaluation, closer selection, and upcoming field calendar.
- Effective working days and hours, daily appointment capacity, unavailable blocks, configured
  territory coverage, and static travel buffers for each closer.
- Manager-only conflict overrides requiring a reason, with the selected closer's violations,
  candidate snapshot, appointment decision, activity, notification, and audit history preserved.
- Lead Manager appointment requests route into Field Dispatch instead of silently assigning a new
  field appointment to the Lead Manager; existing scheduled appointments remain intact.
- Full internal month, week, and day calendar with closer filters and direct meeting launch.
- Versioned pre-appointment brief combining seller, property, qualification, underwriting,
  approved ceiling, unresolved questions, likely objections, open tasks, and logistics.
- Mobile property inspection with authenticated photographs, room observations, repair scope,
  occupancy, utilities, access, title, and safety evidence.
- Decision-maker confirmation, seller objections, commitments, price movement, outcome, and dated
  follow-up capture with server-enforced approved offer ceilings.
- Reviewed field-evidence transfer that creates a repair estimate and new draft underwriting
  version without changing prior approved values.
- Trailing 30-day closer preparation and outcome-documentation scorecards.

Deferred optimization: optional live drive-time estimates if operating data shows that static
travel buffers are insufficient at scale.

Result: The closer can prepare for, attend, document, and complete an acquisition appointment
entirely inside Stonegate.

## Phase 7: Underwriting And Offer Governance

Status: Complete.

Goal: Make every price recommendation explainable, versioned, evidence-backed, and approved before
use.

Delivered:

- Recorded-sale comparable search, scoring, visible exclusions, manual include/exclude review,
  reason presets, bounded weighting, and immutable recalculation versions.
- RentCast address validation, canonical duplicate keys, provider matching, property-fact
  provenance, and subject normalization.
- Repair presets, itemized scopes, contingency, contractor/walkthrough/internal estimates, and
  underwriting version comparison.
- Verified outcomes, immutable calibration snapshots, and ARV, repair, range-coverage, and
  disposition backtesting metrics.
- Immutable offer-ceiling requests, opening/target/stretch/walk-away negotiation plans,
  supersession, stale-version protection, human approval, and accountable decisions.
- Investor and client PDF reports that remain available when renovation status is unconfirmed.
- Versioned seller-meeting briefs, objection preparation, and field evidence coordinated with the
  Phase 6 meeting workflow.
- Append-only price-discussion history, sequential concession records, required concession reasons
  and seller exchanges, and field outcomes linked to the governing authority.
- Automatic authority through target and stretch, explicit manager approval above stretch, hard
  blocking above the approved ceiling, and cancellation of unused authority when a newer plan is
  approved.

Deferred enhancements, not Phase 7 blockers:

- Optional ATTOM or MLS/RESO enrichment behind the property-data adapter when justified.
- Final investor and client report branding after the custom domain and contact details are final.

Result: Every price recommendation is explainable, versioned, and approved before use.

## Phase 8: Contracts And Transaction Coordination

Status: Complete for the provider-neutral manual workflow.

Goal: Take an executed seller contract through funded closing without outside checklists.

Delivered:

- Dedicated transaction coordination queue with risk, deadline, progress, and closing metrics.
- Versioned contract packages with immutable terms snapshots and human approval before sending.
- State-specific, versioned legal-template library with explicit internal approval. Stonegate must
  upload attorney-reviewed documents; the application does not invent legal language.
- Private transaction documents with authenticated downloads and signed-agreement, earnest-money,
  title, payoff, assignment, closing, and funding evidence types.
- Manual sent and executed controls. A lead becomes `under_contract` only after a signed purchase
  agreement is attached to the approved package and execution is recorded.
- Closing-attorney, title-company, seller, buyer, lender, and other closing-party records.
- Earnest-money, due-diligence, assignment, title, and closing milestones.
- Owned, dependency-aware closing checklist with evidence links and immutable transaction events.
- Funded-closing gate requiring an executed package, funding evidence, and every required checklist
  item to be complete or marked not applicable.
- Lead Deal-tab handoff into the central transaction workspace.

Remaining:

- Select and connect an e-signature provider adapter after the manual workflow is proven in live
  closings.
- Move binary files to dedicated object storage when volume warrants it; authorization remains in
  Stonegate.
- Add automated deadline escalation and provider communication after email and Voice activation.

Result: Stonegate can take an executed contract through closing without outside checklists.

## Phase 9: Buyers, Dispositions, And Finance

Status: Complete for the provider-neutral manual workflow.

Goal: Move a contracted deal to a qualified buyer, reconcile proceeds, and calculate compensation
correctly.

Delivered:

- Dedicated disposition queue opened only from executed, closing, or funded transactions.
- Deal-level snapshots that freeze the compensation-plan version and disposition operating mode
  before buyer-placement work starts.
- Buyer CRM, criteria, proof-of-funds documents and expiration, reliability history, and
  deterministic ranked matching. Current verified proof is required for buyer selection.
- Human-approved investor packages, authenticated PDF export, approved recipient pools, and a
  simulated campaign release that intentionally sends no external communication.
- Buyer inquiries, showings, follow-ups, offers, earnest-money terms, primary selection, and backup
  buyer records on the same disposition case.
- Revenue, deductions, Adjusted Deal Margin, role-credit payouts, transaction-coordinator caps,
  company-margin target checks, owner reconciliation approval, and accounting CSV export.
- Source/campaign performance, CPL, contract cost, ROAS, and offline-conversion records.

Remaining:

- Connect approved disposition campaigns to email/SMS only after provider activation and final
  recipient/compliance acceptance testing.
- Add payment-state progression and QuickBooks Online behind the accounting adapter if funded-deal
  volume justifies it; the approved CSV is the current controlled handoff.
- Move proof and package files to object storage when volume warrants it.
- Human-led and AI-assisted disposition performance comparison without retroactive compensation
  changes.

Result: Stonegate can move a contract to a buyer, reconcile proceeds, and calculate compensation
correctly.

## Phase 10: Integrated AI Agent System

Status: Control plane implemented; controlled pilots pending.

Goal: Connect evaluated, permissioned AI agents to completed deterministic workflows.

Delivered:

- Agent definitions, prompt versions, tool permissions, run and tool-call logs, approval records,
  failure tracking, and cost telemetry.
- Recording transcription, speaker segments, structured Call Intelligence notes, supporting
  evidence, and required human review.
- Deterministic safeguards that prevent AI from approving offers or bypassing communication rules.
- Stonegate Orchestrator with dry-run mode, retries, budgets, trace review, and rollback controls.
- Versioned evaluation datasets and promotion thresholds for each agent capability.
- Prospecting Intelligence, Lead Manager Support, Appointment Preparation, Underwriting, Negotiation
  Coach, Disposition, Buyer Relationship, Transaction, Finance, Marketing, Compliance, and
  Executive agents.
- Idempotent event intake, a governed 14-agent portfolio, deterministic fixture evaluations,
  human-approved capability promotion, and an operator control-center UI.
- External execution remains blocked in every baseline agent tool policy.

Remaining:

- Replace fixture outputs with recorded, redacted production examples and model replay for each
  capability before its first pilot.
- Run measured draft-only pilots and establish quality, correction, failure, cost, and business
  outcome baselines.
- Enable narrow, reversible internal actions one capability at a time only after owner approval.
- Keep external actions blocked until the provider, compliance, monitoring, and rollback acceptance
  checks are complete; offer, contract, payment, compensation, and legal authority remain human.
- Agent quality, correction, failure, cost, and business-outcome reporting.

The remaining work proceeds in the ten AI phases defined in `AI_AUTOMATION_ROADMAP.md`. AI1 role
contracts, AI2 golden-case infrastructure, AI3 production runtime, AI4 Lead Manager Copilot, AI5
Prospecting Copilot and Call Quality, and AI6 Acquisitions Copilot are complete in code. Production
acceptance and approved-dataset replay remain before activating measured pilots.

Result: Stonegate's approved agent portfolio assists each role without bypassing human authority,
evidence requirements, compliance controls, or financial approvals.

## Ordering Rules

- Finish Phase 1 production checks before broad team onboarding.
- Resume the parallel integration track as provider approvals become available.
- Retain the completed deterministic workflows in Phases 2-7 before adding downstream automation.
- Complete deterministic operating workflows before enabling corresponding AI actions.
- Do not enable AI authority over offers, contracts, buyers, payments, compensation, or legal
  representations.
- Treat security, accessibility, responsive behavior, speed, and visual quality as acceptance
  criteria throughout the build rather than a substitute for missing workflows.

## Next Build Checkpoint

1. Record the Phase 1 restore, alerting, uptime, and access-revocation operator checks.
2. Run one complete Phase 8 manual contract-to-funding simulation with an attorney-approved test
   template and redacted documents.
3. Run one complete Phase 9 contract-to-buyer-to-reconciliation simulation with redacted evidence.
4. Complete the AI3 production acceptance checklist: provider monitoring, staging shutdown test,
   and approved-dataset model replay.
5. Activate and separately measure the AI4 Lead Manager and AI5 Prospecting draft-only pilots.
6. Begin AI7 Transaction Copilot and Document Intelligence without granting legal, signature,
   contract, or external-send authority.
7. Resume provider acceptance work as A2P, Voice, email, and domain dependencies become available.

## Explicitly Deferred

- Fully autonomous seller negotiation.
- AI authority to approve offers, contracts, buyers, payments, or compensation.
- A custom carrier, email-delivery network, e-signature system, or accounting ledger.
- Cold SMS to purchased, scraped, transferred, or non-consented leads.
