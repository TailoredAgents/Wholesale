# Current State

Last updated: July 22, 2026

## Product

Stonegate Home Buyers is being built as one business platform with two intentionally separate
surfaces:

- A public seller website that explains the service and captures consented property inquiries.
- A private operating system for CRM, communications, underwriting, transactions, buyers,
  finance, marketing intelligence, and controlled AI assistance.

PostgreSQL is the operational source of truth. Clerk provides authentication, but Stonegate's
local roles and permissions remain authoritative for access control.

## Deployment

The application is deployed from `TailoredAgents/Wholesale` on GitHub through a Render Blueprint.
The Render resource names still use the original `oakwell-*` infrastructure names; they must not
be duplicated or renamed casually.

| Resource | Current purpose |
| --- | --- |
| `oakwell-web` | Public website and private Stonegate OS |
| `oakwell-api` | FastAPI application and migrations |
| `oakwell-worker` | Background synchronization, transcription, and retention jobs |
| `oakwell-postgres` | Primary PostgreSQL database |
| `oakwell-key-value` | Redis-compatible coordination resource |

Current public URLs:

- Website: `https://oakwell-web.onrender.com`
- Cash-offer form: `https://oakwell-web.onrender.com/get-a-cash-offer`
- Privacy policy: `https://oakwell-web.onrender.com/privacy-policy`
- Terms: `https://oakwell-web.onrender.com/terms`
- API health: `https://oakwell-api.onrender.com/health`

A branded custom domain is still pending. The Render URLs remain valid until the domain cutover is
complete and should continue to resolve afterward.

## Roadmap Alignment

`ROADMAP.md` is the canonical ten-phase build sequence. Current implementation status against that
sequence is:

| Phase | Status |
| --- | --- |
| 1. Reliability and Test Foundation | Implementation complete; production checks remain |
| 2. Operating Model Data Foundation | Complete |
| 3. Campaign and List Management | Complete |
| 4. VA Prospecting Workbench | Complete |
| 5. Lead Manager Operating System | Complete |
| 6. Appointments and Field Acquisitions | Complete |
| 7. Underwriting and Offer Governance | Complete |
| 8. Contracts and Transaction Coordination | Complete for the manual workflow |
| 9. Buyers, Dispositions, and Finance | Foundational |
| 10. Integrated AI Agent System | Foundational |

The completed underwriting work remains valid. It does not imply that field acquisitions are
complete. Detailed delivered and remaining scope is maintained in `ROADMAP.md`.

## Delivered Capabilities

### Public Website

- Conversion-focused Stonegate homepage with no internal OS navigation.
- Cash-offer request form with duplicate matching, attribution, and conversion tracking.
- Seller pages for inherited homes, repair-heavy homes, and fast-sale situations.
- Public privacy policy and SMS terms.
- Separate, optional, unchecked SMS consent with versioned evidence.
- Form-view, form-start, abandonment, submit, and phone-click conversion events.

### Authentication And Operations

- Clerk sign-in with API-side JWT validation.
- Organization-scoped RBAC, including owner, acquisitions, disposition, and restricted VA roles.
- Live dashboard, task queues, pipeline, lead database, archive, approvals, buyers, finance,
  marketing, underwriting, inbox, and AI control pages.
- Role-aware OS shell with five stable navigation groups, focused role landing routes, global
  workspace search, recent destinations, notification state, and a responsive navigation drawer.
- Role-aware daily command center with prioritized seller work, intervention counts, meeting and
  offer-preparation signals, and a compact pipeline pulse.
- Dense Work Queue with saved ownership and due-state views, contextual next actions, and confirmed
  bulk completion against the existing permission-protected task API.
- Role-filtered acquisition workspace sequence connecting Operations, Campaigns, Prospecting, Lead
  Desk, All Leads, Seller Pipeline, and Field Operations without changing route URLs.
- Append-only activity and audit records for material operations.
- Worker heartbeat and readiness monitoring with durable, grouped failure records.
- Threshold-based failure webhook alerts that omit raw exception details.
- Guarded database backup/restore tooling and read-only deployment smoke tests.
- Deterministic synthetic demo users, leads, appointments, underwriting, transactions, buyers,
  communications, and a simulated shared mailbox.
- SMS and email provider simulation for local end-to-end testing without external delivery.

### Acquisition CRM

- Seller, property, source, qualification, appointment, task, and follow-up records.
- Lead editing, pipeline movement, archive/restore, and controlled permanent deletion.
- Speed-to-lead queue and overdue state.
- Acquisition Ops workspace with daily appointments, notifications, calling lists, team workload,
  duplicate review, saved views, and follow-up plans.
- Owner-managed individual users and operational teams for acquisitions, prospecting,
  dispositions, and coordination.
- Management-only market, territory, outreach-campaign, and pre-lead prospect records with
  organization scoping and append-only audit events.
- Prospect normalization, source-row deduplication, campaign attribution, and suppression-pending
  defaults that keep cold records outside the CRM lead pipeline.
- Reusable CSV vendor mappings, preview-before-commit validation, exact-file replay protection,
  and row-level retained import outcomes.
- Phone and canonical property-address normalization plus exact prospect duplicate detection before
  records enter campaign operations.
- Imported vendor DNC and Stonegate company-suppression evidence. Unscreened records remain review
  only and cannot enter callable batches.
- Audited screening review can attach a later provider/reference decision before a prospect becomes
  callable.
- Campaign cost ledger with list, enrichment, software, advertising, mail, and exact VA labor
  attribution.
- Callable-only prospect batches and campaign reporting for budget, spend, data quality,
  duplicates, suppression, conversions, unit costs, and batch completion.
- Campaigns workspace for performance, imports, mappings, costs, assignments, and file history.
- VA-scoped calling-list execution with attempt history, dispositions, progress, and audited
  handoff to acquisitions.
- Dedicated one-prospect VA workbench using callable prospect batches rather than prematurely
  creating CRM leads.
- Immutable versioned caller scripts with manager approval, guided qualification, required warm
  handoff answers, callbacks, DNC handling, and wrong-number blocking.
- Warm prospect conversion preserving campaign attribution, contact methods, property, internal
  appointment, conversation assignment, owner watchers, and complete attempt history.
- Acquisitions handoff acceptance and correction review plus daily connect, handoff, script-quality,
  DNC, and data-quality scorecards.
- Dedicated Acquisitions Desk for the Lead Manager role, with SLA-controlled handoff acceptance, guided qualification, due
  follow-up, same-day appointments, and neglected-lead exceptions.
- Automatic workload-aware assignment of website inquiries and migration of existing active CRM
  leads into the same Lead Manager queue.
- Worker-driven overdue-handoff escalation with assignee and management alerts, durable due times,
  and append-only audit evidence.
- Immutable, manager-approved Lead Manager qualification versions with required questions,
  structured completion evidence, and mandatory dated next actions.
- Trailing 30-day Lead Manager scorecards for response time, SLA compliance, qualification,
  appointments, no-shows, contracts, and follow-up quality.
- Appointment reschedule, completion, cancellation, no-show, outcome, and recovery workflows.
- Direct-navigation internal Stonegate calendar with month, week, day, and agenda views, plus appointment
  and overdue-task reminders, with no external calendar dependency.
- Dedicated Field Dispatch desk for qualified sellers, closer availability, working hours,
  territory coverage, daily appointment limits, travel buffers, and upcoming appointments.
- Explainable slot evaluation with manager-only conflict overrides, required override reasons,
  immutable candidate snapshots, and audit evidence tied to the actual appointment.
- Full internal month, week, day, and 30-day agenda field calendar with closer filtering, capacity
  context, and meeting launch.
- Versioned seller-meeting briefs, mobile walkthrough evidence and photographs, structured repair
  scope, negotiation outcomes, and approved-ceiling enforcement.
- Reviewed walkthrough transfer creates a new repair estimate and draft underwriting version while
  preserving prior approved underwriting, plus 30-day closer preparation and documentation
  scorecards.
- Conservative duplicate review and merge that archives the secondary lead while preserving
  evidence and a merge snapshot.
- Human-approved SMS and email follow-up drafts; calls and tasks are created directly from plans.
- Lead quality, urgency, qualification gaps, and deterministic next-best-action guidance.
- Notes, appointments, underwriting versions, transactions, and buyer offers on the lead
  workspace.
- Searchable All Leads system of record with saved views, owner and stage filters, compact operating
  status, contextual next actions, and responsive seller previews.
- Complete stage-family Seller Pipeline with local lead inspection, ownership and due context, and
  direct handoffs to conversations, qualification, dispatch, offer preparation, and full records.
- Lead Desk and Field Operations deep links preserve the selected seller through qualification and
  appointment scheduling handoffs.

### Shared Inbox And Team Workflow

- Three-panel shared inbox with Mine, Unassigned, Team, Needs Reply, Appointments, and Unread views.
- Inbox deep links preserve lead or saved-view context, and responsive Inbox, Thread, and Details
  panes retain the complete shared conversation record on mobile.
- One chronological timeline for SMS, email, calls, recordings, transcripts, and internal notes.
- Conversation assignment, watchers, unread state, provider events, and assignment history.
- Restricted VA prospecting role and audited VA-to-acquisitions handoff.
- Owner and acquisition watcher behavior for qualified leads and appointments.

### Communications Implementation

- Twilio SMS adapter, signed inbound and delivery webhooks, idempotency, STOP/START processing,
  suppression, consent checks, number validation, permissions, and contact-hour controls.
- Twilio browser Voice implementation with access tokens, scoped call intents, inbound routing,
  missed-call tasks, call status history, and private recording access.
- Recording disclosure state, audio retention, early deletion audit, OpenAI transcription, speaker
  segments, structured call notes, and required human review.
- Google Workspace email implementation with per-user OAuth, encrypted refresh tokens, Gmail
  threading, signatures, shared templates, incremental synchronization, and attachment proxying.

### Underwriting

- RentCast property-data adapter.
- Recorded-sale comparable search and scoring.
- Subject, market, condition, repair, liquidity, and disposition adjustments.
- ARV range, as-is range, offer scenarios, confidence, and review flags.
- Optional pre-meeting repair and renovation inputs.
- Investor and client PDF reports.
- Comparable inclusion and exclusion explanations retained for review.
- Full selected/rejected comp review workspace with condition classification, include/exclude
  decisions, required reason presets, and bounded evidence weighting.
- Comp review recalculations create immutable underwriting versions and dedicated activity/audit
  events while retaining the original market-data snapshot.
- Canonical address keys normalize common street suffixes, directionals, state, and ZIP5 across
  staff-created and website-created leads.
- RentCast property-record validation retains match status, score, issues, provider address,
  non-owner subject facts, timestamp, and audit history without replacing the CRM address.
- Underwriting uses an explicit canonical subject-fact set with field-level provider/CRM
  provenance; address mismatches reduce confidence and require review without gating outputs.
- Reports remain available even when renovation status is not yet confirmed.
- Lead-level verified outcome entry for expert reviews, appraisals, completed resales, and verified
  market sales, with optional actual rehab, seller contract, and disposition values.
- Immutable calibration snapshots preserve the prediction made at analysis time and report median
  ARV bias, median absolute ARV error, ARV-range coverage, and optional repair/disposition error by
  market.
- The Underwriting workspace shows calibration readiness and verified outcome history. Formula
  review requires at least 50 cases; calibration never adjusts formulas automatically.
- Lead underwriting now includes light, moderate, heavy, and structural repair presets that
  prefill an editable itemized scope with an explicit contingency.
- Contractor bids, walkthrough estimates, and internal scopes can be retained as immutable repair
  evidence and selected for a new analysis without rewriting the source estimate.
- Investor reports identify the selected repair source, contractor, estimate date, reference,
  labor, materials, contingency, and total. Saved underwriting versions can be compared directly
  on the lead page.
- The lead underwriting workspace creates immutable negotiation plans with opening, target,
  stretch, and hard-ceiling values tied to one saved underwriting version.
- Offer approval requests cancel superseded pending plans, reject stale versions, record the
  deciding user and notes, and move an approved lead to `offer_ready` without allowing the ceiling
  to exceed the saved underwriting result.
- The approved opening, target, stretch, and ceiling now govern every field or phone negotiation.
  Sequential concessions require a documented reason and seller exchange; moves through stretch
  are pre-authorized, moves above stretch require manager approval, and moves above ceiling are
  blocked until new underwriting is approved.
- Price discussions, seller counters, objections, presented concessions, and agreements are stored
  in an append-only ledger. Field outcomes link to the exact governing concession, and approval of
  a newer plan cancels prior unused authority without erasing historical offers.

Underwriting is decision support, not an appraisal. It requires continued comparison against real
transactions and human judgment before Stonegate relies on it for offer ceilings.

### Downstream Operations

- Central transaction coordination queue with contract-to-funding status, risk flags, closing
  metrics, milestone dates, and checklist progress.
- Versioned contract packages require human approval before sending. A signed agreement must be
  attached before execution can move the lead to `under_contract`.
- Versioned, state-specific legal-template records, private authenticated document storage, closing
  parties, dependency-aware checklist evidence, and an immutable transaction timeline.
- Funded closing is blocked until an executed package, funding confirmation, and all required
  checklist items are present.
- Dedicated disposition queue with frozen compensation plan/mode, approved deal packages, and
  authenticated investor PDF export.
- Buyer CRM, criteria, expiring proof-of-funds evidence, reliability history, ranked qualification,
  approved campaign simulation, engagement, offers, primary selection, and backup selection.
- Funded-deal reconciliation calculates Adjusted Deal Margin, role-credit commission payouts,
  transaction-coordinator caps, company margin, owner approval, and accounting CSV output.
- Revenue, deductions, compensation rules and calculations, and marketing spend.
- Versioned compensation plans with owner activation, acquisition reserves, company-margin targets,
  role percentages, transaction-coordinator caps, and effective dates.
- Lead-level role-credit proposals and approvals preserve contribution history separately from CRM
  assignment and prevent over-allocation.
- Human-led and two AI-assisted disposition operating modes are versioned with each compensation
  plan; AI modes remain locked behind later evaluation and owner approval.
- Evidence-backed, versioned market launch checklists require all 11 operational controls before
  owner approval.
- Business Setup provides one workspace for operating economics, contribution review, and market
- Source/campaign performance, CPL, contract cost, ROAS, and offline conversion export records.
- AI agent definitions, prompt versions, tool permissions, run logs, tool-call logs, approvals,
  cost telemetry, and call-intelligence quality reporting.

## External Setup In Progress

| Area | Status | Next action |
| --- | --- | --- |
| A2P 10DLC | Submitted and under provider review | Wait for approval, then attach the new dedicated Stonegate SMS number |
| Twilio SMS | Code complete; final provider cutover pending | Configure the new Messaging Service SID and new SMS sender, then run STOP/START/inbound/delivery tests |
| Twilio Voice | Code complete; activation paused | Finish API key, TwiML App, Render variables, outbound test, and inbound webhook on the Voice number |
| Call recording | Implemented but intentionally disabled | Approve disclosure and retention policy, then test before enabling |
| Google Workspace email | Code complete; provider configuration pending | Configure domain/mailboxes, Google OAuth, Render secrets, and per-user mailbox connections |
| Custom domain | Not configured | Choose the domain, connect it to Render, and update Clerk, CORS, Google, and provider URLs |

The dedicated SMS number and the Voice/support number are separate configuration values:

- `TWILIO_SMS_FROM_NUMBER`: the newly purchased, campaign-approved SMS number.
- `TWILIO_VOICE_FROM_NUMBER`: the company Voice number selected for browser and inbound calling.

Do not reuse another company's Messaging Service, A2P Campaign, number, or webhook.

## Known Limits

- Final production messaging, Voice, email, and custom-domain acceptance tests are incomplete.
- Automatic SMS enrollment confirmation must be activated with the approved Messaging Service.
- Field acquisitions uses static travel buffers; live route-duration estimates are intentionally
  deferred until operating data demonstrates that route precision is necessary.
- Contract templates, e-signature, document storage, and checklist completion workflows are not
  complete.
- External buyer campaign delivery is intentionally simulated until email/SMS provider acceptance
  is complete; buyer matching and human approval are operational.
- QuickBooks/Xero synchronization is not implemented.
- Google Ads and Meta conversion delivery adapters are not implemented.
- AI agents do not autonomously send seller messages, change offers, send contracts, or make
  financial or legal decisions.
- Local Node and Python dependency reads intermittently stall on this Mac; Render builds and
  targeted syntax/live checks are currently more reliable than broad local checks.
- A production backup has not yet been restored into an isolated verification database; the
  guarded drill is implemented and remains an operator checkpoint.

## Next Checkpoint

While A2P approval is pending:

1. Run the first isolated database restore drill from `docs/PHASE_1_RELIABILITY.md`.
2. Configure an owner-controlled operations alert webhook and external uptime check for `/ready`.
3. Record the production access-revocation check and close the Phase 1 exit criteria.
4. Run a redacted, end-to-end Phase 8 closing simulation and record operator feedback.
5. Run a redacted Phase 9 contract-to-buyer-to-reconciliation simulation and record operator
   feedback.
6. Populate Phase 10 evaluations with redacted operating examples, approve the datasets, and run
   the first draft-only Lead Management pilot.
7. Resume the parallel integration track after A2P approval without blocking internal development.
