# Stonegate VA Dialer Roadmap

Last updated: July 30, 2026

## Purpose

This roadmap defines the phased path for making Stonegate's VA cold-calling operation production
ready. It extends the existing Prospecting, CRM, Inbox, calendar, communications, assignment, and
reporting systems. It does not create a second CRM or replace Stonegate as the operational source
of truth.

The intended production model is hybrid:

- a multi-line dialer handles first-pass calling on untouched cold PropStream records
- Stonegate's one-line power dialer handles callbacks, prior contacts, scheduled follow-up, and
  interested sellers
- Stonegate stores the durable prospect, lead, assignment, communication, handoff, cost, and
  outcome history
- only Lead Manager-accepted handoffs count as warm leads for performance and cost reporting

## Current Decision

- PropStream Pro is the initial prospect-list source.
- BatchDialer Starter is the initial multi-line provider candidate.
- Two or three individually authenticated Upwork VAs are expected at launch.
- Each VA is budgeted at $8 per paid hour.
- A provider trial and measured comparison must occur before an annual dialer commitment.
- Stonegate remains the permanent workspace even when a provider temporarily handles live
  dialing.

## Current Product Baseline

Stonegate already implements:

- campaign and calling-list records
- CSV prospect import, reusable mappings, validation preview, and duplicate handling
- prospect records that remain separate from CRM leads until handoff
- restricted VA Caller accounts and the `/os/prospecting` workbench
- assigned calling batches, scripts, qualification questions, attempts, dispositions, callbacks,
  notes, and appointments
- qualified handoff into the CRM without losing attribution or activity history
- Lead Manager ownership, owner watching, notifications, and post-handoff VA restrictions
- a one-line browser calling foundation, communications timeline, recordings, transcripts, and
  supervised AI call intelligence
- campaign expense and operating-performance foundations
- comparison cohorts with source, list type, market, script, call window, date range, and dialer mode
- paid-time and productive-calling work sessions with automatically attributed VA labor cost
- outcome evidence classifications and structured Lead Manager decision codes
- strict accepted-warm-lead and cost-per-accepted-warm-lead calculations

Before implementing each phase, verify this baseline against the current code and migrations.
Extend existing records and services rather than duplicating them.

## VD1 Audit Result

VD1 was completed on July 30, 2026 by tracing the current models, migrations, API services, routes,
web workspaces, role permissions, and focused tests.

### Reuse, Extend, And Add Matrix

| Domain | Reuse without replacement | Extend or add |
| --- | --- | --- |
| Campaign identity | `Campaign`, market, territory, owner, channel, dates, budget, and explicit comparison cohorts | Add PropStream export and source-membership detail in VD3 |
| Imports | Saved mappings, CSV preview, row validation, exact-file replay protection, raw rows, normalized rows, and audit events | Add a PropStream mapping preset, export identifiers, filter snapshots, list dates, and normalized multiple phone/email values |
| Prospect identity | One organization-scoped `Prospect` record with normalized phone, email, and property identity | Add source/list memberships so repeated source appearances are retained without creating duplicate people or properties |
| Eligibility | Existing company suppression, imported flags, validation states, and call eligibility | Preserve history when refreshed data changes; do not reset prior seller outcomes or callbacks |
| Assignment | `ProspectCallingBatch`, ordered entries, individual VA assignment, due time, cohort, dialer mode, and active-attempt locking | Add provider campaign/contact identifiers, sync state, and routing reason |
| VA workflow | `/os/prospecting`, approved scripts, required questions, attempts, outcomes, callbacks, appointments, notes, and Copilot drafts | Add provider state and launch/resume controls while keeping Stonegate as the primary workbench |
| Calls | `CommunicationProviderEvent`, `CommunicationRecord`, `CallRecord`, recording, transcript, retention, and AI call-quality records | Extend the existing call domain to support prospect-linked calls before a CRM lead exists; add BatchDialer adapter, webhooks, reconciliation, replay, and provider failures |
| Handoffs | Pending review, accepted handoff, correction request, terminal rejection, structured decision codes, CRM conversion, Lead Manager case, SLA, notifications, owner watchers, and audit history | Add faster review controls and coaching detail in VD7 |
| Hybrid routing | Callback scheduling and one-at-a-time queue locking already exist | Add explicit cold multi-line, warm one-line, provider-paused, and completed routing states with cross-system collision prevention |
| Cost records | Campaign costs support cohort attribution, list, enrichment, dialer seat, number, voice usage, software, VA labor, and other attributable costs; work sessions separate paid and productive minutes | Add provider billing reconciliation and shared billing-period allocation |
| Reporting | Campaign quality includes submitted, rejected, and strictly accepted warm handoffs plus cost per accepted warm lead; source records retain dialer mode and cohort | Add full filtered cohort, VA, appointment, contract, and closed-deal scorecards in VD8 |
| Permissions | Restricted `prospecting_caller` role, assigned-record scoping, manager controls, and server-side permission checks | Add provider-sync management to owner/manager permissions without exposing credentials or exports to VAs |

### Confirmed End-To-End Flow

1. A manager creates a campaign and reusable CSV mapping.
2. Stonegate previews and imports valid rows while retaining invalid, duplicate, and other explicit
   row outcomes.
3. Raw provider columns remain in the prospect source payload.
4. Eligible prospects are assigned to one VA in ordered calling batches.
5. Starting an attempt locks the prospect to that VA and prevents another simultaneous active
   attempt.
6. The VA records the approved script version, answers, outcome, notes, callback, and optional
   appointment.
7. Interested and appointment-set outcomes create a pending handoff, CRM lead, unified
   conversation, Lead Manager case, SLA, notification, and attribution.
8. The manager accepts the handoff or requests a correction; accepted handoffs complete the
   prospecting entry and corrections return it to the VA queue.
9. Existing scorecards count submitted and accepted handoffs separately.

### Material Gaps Confirmed

- The Prospecting page currently opens the phone through a `tel:` link and records the outcome
  manually. It is not connected to a multi-line provider.
- Existing Twilio browser calls require a CRM lead conversation. A cold prospect cannot yet own a
  provider call, recording, or transcript.
- `CallRecord` currently requires lead, contact, and conversation identifiers. It must be extended,
  not duplicated, for pre-lead prospect calls.
- Provider events already have organization/provider/external-event idempotency, but they do not
  yet link directly to a prospect or prospecting attempt.
- A prospect currently belongs to one campaign. Duplicate rows from later lists are retained as
  import evidence but do not create a reusable source-membership or cohort record.
- The normalized prospect record currently exposes one phone and one email even when a source may
  supply multiple ranked contact values.
- Calling batches store cohort and dialer mode but not provider campaign/contact identifiers, sync
  status, or routing reason.
- Lead Manager decisions now have structured accepted, correction, and rejection codes; the
  dedicated review interface will be streamlined in VD7.
- Campaign reports calculate strict accepted-warm-lead economics, but full date, cohort, VA, list,
  script, and dialer-mode filtering belongs to VD8.
- VA scorecards still use a fixed seven-day window; source records now support reproducible
  comparisons after the VD8 reporting interface is added.

### Implementation Boundaries

- `app.models.foundation` remains the shared data model; new migrations extend these records.
- `services.campaign_management` remains responsible for import, list membership, campaign costs,
  cohort creation, and batch preparation.
- `services.prospecting` remains responsible for VA attempts, callbacks, outcomes, and handoffs.
- The existing communications and Voice services remain responsible for normalized calls,
  recordings, transcripts, and timeline events.
- A new provider adapter may translate BatchDialer APIs and events, but it may not become a second
  CRM or business-rules engine.
- Provider routes must call domain services; webhook handlers may not implement independent lead,
  handoff, or routing logic.
- `/os/campaigns`, `/os/prospecting`, and `/os/lead-manager` remain the manager, VA, and warm-lead
  workspaces.
- VD2 owns the shared measurement contract; later phases must use it instead of redefining provider
  outcomes or warm-lead counts.

## Status Rules

- **Implemented** means the workflow exists in Stonegate code with focused automated coverage.
- **Configured** means the required provider account, campaign, mappings, and credentials exist.
- **Active** means a controlled production test passed with real provider events.
- **Accepted** means the Owner approved the measured workflow and operating result.

A phase is not finished from code alone when its exit criteria require provider or production
evidence.

## Success Definition

A **Lead Manager-accepted warm lead** is a prospect for whom:

1. the VA reached the owner or an authorized decision-maker
2. the correct property was confirmed
3. the seller expressed genuine openness to selling or receiving an offer
4. the seller permitted Stonegate follow-up
5. the VA recorded the required qualification and callback context
6. the Lead Manager reviewed and accepted the handoff

Wrong numbers, already-sold properties, agents seeking listings, unsupported guesses, vague
"maybe someday" responses, duplicates, and rejected handoffs do not count as warm leads.

The primary economic metric is:

```text
cost per accepted warm lead =
  allocated VA wages
  + allocated PropStream cost
  + allocated dialer and phone-number cost
  + allocated calling usage
  ------------------------------------------------
  Lead Manager-accepted warm leads
```

Secondary metrics include contacts per paid hour, accepted handoffs per paid hour, rejection rate,
appointments per accepted handoff, cost per appointment, and eventual cost per contract.

## Research Baseline

These values are planning assumptions, not guaranteed results:

- PropStream Pro is currently listed at $199 per month and includes 50,000 monthly saves and
  exports, free skip tracing through PropStream Connect, and in-app dialing.
- BatchDialer Starter is currently listed at $119 per agent monthly or about $95 per agent monthly
  with annual billing. It includes three simultaneous lines, ten phone numbers, reputation
  monitoring, recordings, and unlimited inbound and outbound calling.
- Current published dialing benchmarks commonly place one-line power dialing around 40-65
  attempts per hour and multi-line or predictive dialing around 60-120 or more attempts per hour.
- Wholesaling-focused vendor benchmarks commonly report a 6-10% live-contact rate and a 2-4%
  interested-lead rate from live contacts. Actual Georgia results may differ materially.

Initial planning range for two VAs working 30 productive calling hours each per week:

| Mode | Expected accepted warm leads per month | Planning cost per accepted warm lead |
| --- | ---: | ---: |
| One-line power dialer | 18-30 | $75-$125 |
| Three-line multi-call dialer | 35-55 | $45-$70 |

The initial central forecast is approximately $90-$100 per accepted warm lead with one-line power
dialing and $50-$55 with three-line dialing. Stonegate must replace these assumptions with its own
measured cohort results.

Research references:

- [PropStream pricing](https://www.propstream.com/pricing)
- [BatchDialer pricing](https://batchdialer.com/pricing)
- [FTC Telemarketing Sales Rule guidance](https://www.ftc.gov/business-guidance/resources/complying-telemarketing-sales-rule)

## Phase Summary

| Phase | Name | Current state |
| --- | --- | --- |
| VD1 | Existing-system audit | Implemented July 30, 2026 |
| VD2 | Definitions and measurement contract | Implemented July 30, 2026 |
| VD3 | PropStream list pipeline | Next |
| VD4 | VA calling workspace | Planned upgrade |
| VD5 | Multi-line provider connection | Planned |
| VD6 | Hybrid dialing and routing | Planned |
| VD7 | Accepted handoff workflow | Planned upgrade |
| VD8 | Cost and performance reporting | Planned upgrade |
| VD9 | Controlled comparison pilot | Externally pending |
| VD10 | Production launch and optimization | Externally pending |

## VD1. Existing-System Audit

### Completed Work

1. Inventoried current prospecting models, migrations, services, routes, permissions, and UI.
2. Traced list import through assignment, attempt logging, callback, handoff, and Lead Manager
   review.
3. Inventoried existing Twilio and browser-calling records that can normalize BatchDialer events.
4. Identified existing campaign expense and performance fields.
5. Produced the reuse, extend, and add matrix above before changing the schema.
6. Recorded the implementation boundaries and material gaps.

### Exit Criteria

- **Passed:** Every planned capability is classified as existing, needing extension, or new.
- **Passed:** No second prospect, lead, conversation, call, appointment, or user system is
  proposed.
- **Passed:** The implementation sequence names the exact existing ownership boundaries it will
  extend.

## VD2. Definitions And Measurement Contract

### Completed Work

1. Added `ProspectingCohort` with campaign, source, list type, market label, script, date range,
   calling window, timezone, and `one_line_power` or `multi_line_parallel` mode.
2. Added `ProspectingWorkSession` so paid minutes, productive calling minutes, caller, cohort,
   hourly rate, labor cost, and provider-session evidence remain reproducible.
3. Added cohort attribution and explicit `dialer_license`, `phone_number`, and `voice_usage`
   campaign-cost categories.
4. Added attempt evidence fields for dial start, answer, live person, right party, interest,
   follow-up permission, evidence timestamps, classification source, cohort, and dialer mode.
5. Added deterministic outcome classification shared by both dialer modes.
6. Added structured accepted, correction, and terminal rejection decisions for Lead Manager
   handoffs.
7. Made accepted-warm-lead counting require accepted status, an accepted decision code, a live
   right-party contact, confirmed interest, follow-up permission, and every required answer.
8. Added strict campaign counts for submitted, rejected, and accepted warm handoffs plus cost per
   accepted warm lead.
9. Added migration `0073_va_dialer_metrics`, historical-attempt backfills, API coverage, and focused
   tests for evidence classification, acceptance gating, cohort records, work time, labor cost,
   cost allocation, and campaign economics.

### Measurement Contract

| Metric | Required source evidence | Governing timestamp |
| --- | --- | --- |
| Dial attempt | Attempt with `dial_started_at` | Dial start |
| Machine answer | `answer_classification=machine` and `answered_at` | Answer time |
| Live contact | `answer_classification=live_person` and `answered_at` | Answer time |
| Right-party contact | Live contact, `party_classification=right_party`, confirmation time | Right-party confirmation |
| Interested seller | Right party, interested classification, follow-up permission granted | Interest confirmation |
| Submitted handoff | Durable handoff row | Submission time |
| Accepted warm lead | Accepted decision plus all right-party, interest, permission, and required-answer evidence | Lead Manager review time |
| Rejected handoff | Terminal rejected decision and structured rejected code | Lead Manager review time |
| Callback | Callback/follow-up outcome and future callback time | Callback due time |
| Appointment | Durable appointment row and status | Scheduled start |
| Contract | Durable transaction with signed date | Contract signed time |

Paid time is the compensated work-session duration. Productive calling time is the portion spent in
active dialing or connected-call work. Total attributable cost is VA labor plus allocated list,
dialer-license, phone-number, voice-usage, and other campaign costs. Cost per accepted warm lead is
that total divided only by handoffs satisfying the strict accepted-warm-lead contract.

### Exit Criteria

- A cheap or vague VA handoff cannot be counted as an accepted warm lead.
- Every dashboard metric can be reproduced from stored source records.
- Power and multi-line cohorts can be compared without changing definitions.

## VD3. PropStream List Pipeline

**Status:** Implemented July 30, 2026. Production export acceptance remains.

### Work

1. Preserve the existing CSV preview, mapping, validation, duplicate, and replay behavior.
2. Add or verify PropStream-specific source metadata and export identifiers.
3. Preserve list filters such as market, county, distress signal, equity, ownership duration,
   occupancy, and property type.
4. Normalize multiple ranked phone numbers and emails without duplicating the prospect.
5. Add source/list memberships so later list appearances remain attributable to the same prospect.
6. Detect duplicate people, properties, phone numbers, and prior Stonegate contact.
7. Separate untouched cold prospects from callbacks, active conversations, and existing leads.
8. Prevent a fresh import from resetting prior outcomes, opt-outs, or callback commitments.
9. Support deterministic assignment into comparable campaign cohorts.

### Implemented

1. Added a reusable PropStream standard-export preset while preserving custom CSV mappings.
2. Added source profile, export ID, saved-list ID/name, export time, filter evidence, and cohort
   attribution to every import batch.
3. Added durable source-list memberships so repeat appearances update lineage instead of creating
   another outreach record.
4. Added up to three ranked phones and three ranked emails per export row without replacing the
   prospect's established communication history.
5. Added matching across source IDs, all known phones, all known emails, and normalized property
   addresses.
6. Added explicit untouched, prior-contact, callback, active-conversation, and existing-lead
   relationship states in preview and import history.
7. Made refresh imports preserve prior outcomes and attach new contact/source evidence to the
   existing record.
8. Made calling batches select through import-row and cohort lineage, including records matched
   during a refreshed export.
9. Added a PostgreSQL migration and repeatable acceptance coverage for import, refresh,
   preservation, replay rejection, contact ranking, source appearances, and cohort batching.

### Exit Criteria

- A PropStream export imports through a reviewed preview without duplicate outreach records.
- Every imported prospect can be traced to the exact campaign and source cohort.
- Existing seller history survives list refreshes and repeated imports.

## VD4. VA Calling Workspace

**Status:** Implemented July 30, 2026. Real-VA desktop acceptance remains.

### Work

1. Keep `/os/prospecting` as the VA's primary Stonegate workspace.
2. Show assigned campaigns, current prospect context, approved script, qualification prompts,
   prior attempts, callback commitments, and required disposition fields.
3. Make callback, not interested, wrong party, invalid number, do not contact, interested, and
   appointment outcomes fast to record.
4. Add clear provider-sync state without forcing VAs to work in two CRMs.
5. Preserve individual attribution for every action and provider event.
6. Verify that VAs cannot access unrelated prospects, underwriting, contracts, buyers, finance,
   exports, or restricted mail.
7. Verify usable desktop behavior for Upwork VAs and responsive manager review.

### Implemented

1. Kept `/os/prospecting` as the single VA shift workspace and extended the existing attempt,
   handoff, quality, and Copilot records.
2. Added a complete assigned queue with Due now, Callbacks, Corrections, Scheduled, Waiting, and
   All assigned views.
3. Added batch and campaign summaries with ready, callback, correction, active, and handoff counts.
4. Prioritized active work, returned corrections, and due callbacks ahead of untouched records.
5. Added ranked phone/email display, callback commitments, assigned caller, prior notes,
   qualification answers, cohort, dialing mode, and detailed attempt history.
6. Replaced the long disposition menu with a compact outcome control and added one-hour,
   next-day, and three-day callback shortcuts.
7. Kept structured qualification visible only for outcomes where a real seller conversation needs
   to be retained; warm outcomes still require every approved handoff question.
8. Added truthful provider state: one-line work shows Stonegate direct, while multi-line work shows
   Provider not connected until VD5 is completed.
9. Added API acceptance proving a VA cannot open another VA's prospect or access underwriting,
   transactions, buyers, finance, global email recipients, or email administration.
10. Preserved individual caller attribution on every attempt, outcome, handoff, and audit event.

### Exit Criteria

- A VA can complete a normal shift from one focused queue.
- Required qualification and outcome data are captured without free-form reconstruction.
- Restricted areas remain inaccessible from both the UI and API.

## VD5. Multi-Line Provider Connection

### Work

1. Use an adapter boundary so BatchDialer can be replaced without changing Stonegate's domain
   records.
2. Add environment-variable and setup documentation without storing secrets in Git.
3. Send only approved, assigned cold prospects and required fields to the provider.
4. Store provider campaign, contact, call, recording, and event identifiers.
5. Ingest attempts, dispositions, timing, agent identity, recordings, and provider errors.
6. Normalize provider calls into Stonegate's existing communications and prospect history.
7. Add signature or authentication validation, idempotency, retries, and reconciliation.
8. Provide simulation fixtures so the integration can be tested before paid production calling.

### Exit Criteria

- A simulated provider campaign completes end to end.
- Replayed or duplicate provider events do not create duplicate attempts or leads.
- Provider failures are visible and retryable.
- Stonegate retains a complete normalized history independent of the provider dashboard.

## VD6. Hybrid Dialing And Routing

### Work

1. Route untouched, eligible cold prospects to the multi-line campaign.
2. Route callbacks, prior contacts, scheduled follow-up, interested sellers, and active leads to
   Stonegate's one-line workflow.
3. Stop multi-line attempts immediately after interest, callback commitment, appointment,
   handoff, invalid contact, or opt-out.
4. Preserve one chronological seller history when the assigned person or dialing mode changes.
5. Add owner-visible routing reasons and correction controls.
6. Prevent simultaneous calling of the same person by multiple VAs or dialer modes.

### Exit Criteria

- Cold volume benefits from multi-line dialing without sending warm conversations back into it.
- A prospect cannot be actively dialed by both systems at the same time.
- Managers can explain why each record is in its current queue.

## VD7. Accepted Handoff Workflow

### Work

1. Extend the existing handoff workflow with submitted, accepted, rejected, and correction states.
2. Require the correct seller, property, interest, permission, context, and next action.
3. Attach the originating call, recording, transcript, answers, disposition, campaign, and VA.
4. Notify the Lead Manager and create the response task and due time.
5. Allow rejection with structured reasons such as no clear interest, wrong person, duplicate,
   insufficient context, unsupported property, or no permission to follow up.
6. Return coaching feedback to the originating VA without exposing restricted lead details.
7. Keep the VA read-only after accepted handoff except for an audited correction request.

### Exit Criteria

- Accepted warm leads arrive in the Lead Manager queue with enough context for immediate action.
- Rejected handoffs do not inflate VA performance.
- Every acceptance, rejection, reassignment, and correction remains attributable.

## VD8. Cost And Performance Reporting

### Work

1. Add campaign-level wages, PropStream allocation, provider licenses, phone numbers, and variable
   calling costs.
2. Calculate cost per contact, submitted handoff, accepted warm lead, appointment, contract, and
   closed deal.
3. Report dials per paid hour, contacts per paid hour, handoff acceptance rate, appointments per
   accepted handoff, and follow-up response time.
4. Filter by VA, manager, market, list type, cohort, script, call window, date, and dialer mode.
5. Keep raw counts beside rates so small samples are not presented as reliable trends.
6. Add exportable owner summaries and provider reconciliation.
7. Add data-quality warnings for missing hours, costs, outcomes, or provider events.

### Exit Criteria

- Stonegate can reproduce the monthly cost per accepted warm lead from source records.
- The Owner can compare power and multi-line results by equivalent cohort.
- Managers can distinguish list, connection, VA, handoff, and Lead Manager problems.

## VD9. Controlled Comparison Pilot

### External Preparation

1. Start with a monthly BatchDialer trial or subscription rather than an annual commitment.
2. Use two trained VAs, the same approved script, and comparable calling schedules.
3. Split comparable PropStream records randomly by market and list type.
4. Have VAs switch dialer modes during the pilot so VA skill is not confused with dialer
   performance.

### Pilot

1. Run each mode for enough paid hours and records to avoid judging a very small sample.
2. Review accepted warm leads, rejection rate, appointments, complaints, abandoned calls,
   provider errors, and number reputation.
3. Listen to a sample of successful, rejected, and ordinary calls from each mode.
4. Calculate costs using actual wages, subscriptions, hours, and accepted outcomes.
5. Document the Owner's go, adjust, or stop decision.

### Decision Rule

Adopt multi-line dialing for cold first passes when:

- its cost per accepted warm lead is no more than 70% of the power-dialer result
- Lead Manager acceptance and appointment quality remain acceptable
- dropped-call, complaint, and number-reputation results remain within the approved operating
  standard
- provider syncing and reconciliation are reliable

### Exit Criteria

- The comparison uses equivalent cohorts and Stonegate's accepted-warm-lead definition.
- The Owner has approved a measured production configuration.
- Annual purchasing remains deferred until the trial proves the expected economics.

## VD10. Production Launch And Optimization

### Work

1. Activate the approved provider plan, campaign configuration, numbers, and VA seats.
2. Train each VA and Lead Manager on the final Stonegate workflow.
3. Publish daily and weekly scorecards.
4. Review calls and rejection reasons weekly during the first 90 days.
5. Monitor list exhaustion, repeat attempts, contact rate, number reputation, provider failures,
   and appointment quality.
6. Calibrate campaign filters, scripts, calling windows, and routing from measured results.
7. Keep warm follow-up in the one-line workflow even when multi-line wins cold prospecting.
8. Reassess provider, seat count, and annual billing only after stable operating evidence.

### Exit Criteria

- Real VAs can work complete shifts with reliable provider synchronization.
- Lead Managers receive useful, attributable handoffs without duplicate records.
- Cost per accepted warm lead and downstream appointment quality are reviewed weekly.
- Stonegate, not the dialer provider, remains the authoritative operating record.

## External Responsibilities

The Owner or trusted administrator is responsible for:

- maintaining PropStream Pro
- creating and funding the BatchDialer account
- entering provider credentials in the production environment
- approving scripts, list criteria, VA schedules, and performance standards
- hiring, training, and managing individual VAs
- approving the production pilot result and any annual purchase
- obtaining any professional review Stonegate chooses for its calling practices

## Development Responsibilities

Codex implementation work includes:

- auditing and extending the current prospecting domain
- PropStream import and campaign cohort improvements
- provider adapter, synchronization, reconciliation, and simulation
- VA workspace and hybrid queue routing
- accepted handoff review and coaching feedback
- cost and performance reporting
- permissions, audit history, automated tests, and documentation

## Provider And Operating Notes

- Provider credentials and exact setup values belong in `SETUP_REFERENCE.md`.
- Staff instructions belong in `STAFF_ROLE_MANUALS.md`, `USER_MANUAL.md`, and
  `UI_CONTROL_REFERENCE.md` after the workflow is implemented.
- Current product behavior belongs in `SYSTEM_MAP.md`.
- Remaining launch acceptance belongs in `FINISHING_ROADMAP.md`.
- The dialer must retain records needed to evaluate call connection and abandonment behavior.
- The FTC describes a predictive-dialer safe harbor that includes a maximum three-percent
  abandoned-call rate, live-agent connection timing, minimum ringing behavior, required fallback
  identification, and recordkeeping. Stonegate's final operating configuration must reflect the
  rules applicable to its actual campaigns and jurisdictions.

## Next Action

Begin VD3 by extending the existing import pipeline with a PropStream preset, export and filter
metadata, multiple ranked contact methods, reusable source memberships, and refresh-safe duplicate
handling. Keep CSV import as the supported launch path unless PropStream grants Stonegate a private
partner API.
