# BatchDialer Direct Integration And Native Dialer Dormancy Roadmap

Last updated: August 22, 2026

Status: direct-only architecture approved; native dialer dormancy prepared; direct runtime
implementation and production acceptance in progress

## 1. Purpose And Authority

This is the canonical implementation plan for Stonegate's outbound-calling architecture.

BatchDialer is the production dialer. Stonegate receives supported BatchDialer data through the
official API and becomes the business system of record when a seller is qualified. Stonegate's
native D0-D10 dialer remains dormant and preserved for historical evidence; it is not an alternate
calling path.

The final architecture has one BatchDialer transport: the direct API integration. It has no
third-party automation bridge, parallel observation transport, or alternate intake path. Appointments
are never imported from BatchDialer. An **Appointment Set** result creates an urgent Stonegate task,
and the VA enters the actual appointment manually in Stonegate.

Application code, migrations, and production configuration remain the truth about what is live. A
roadmap phase is not production evidence by itself.

## 2. Final Product Decision

1. **BatchDialer is the calling system.** VAs place calls, work calling cadences, use provider
   numbers, and select truthful call results there.
2. **Stonegate is the CRM and operating system.** Qualified sellers, property records, notes,
   follow-up, appointments, acquisitions work, contracts, and downstream deal history belong in
   Stonegate.
3. **The official BatchDialer API is the sole integration.** A Stonegate worker retrieves bounded
   provider data, stores durable evidence, and processes eligible handoffs exactly once.
4. **Appointments are manual in Stonegate.** **Appointment Set** creates one urgent
   **Enter/verify Stonegate appointment** task and visible warning. It never creates an Appointment
   from provider calendar data.
5. **BatchDialer owns cold-calling cadence and DNC.** Stonegate does not write provider DNC or
   campaign state. Stonegate's own suppression controls continue to govern communication sent from
   Stonegate after handoff.
6. **The native Stonegate dialer remains dormant.** Its execution, softphone, activation, and pilot
   controls stay unavailable. Historical records, recordings, transcripts, analytics, migrations,
   and late signed callback cleanup remain intact.

## 3. System-Of-Record Boundaries

| Responsibility | Authority | Stonegate behavior |
| --- | --- | --- |
| Dialing, pacing, caller numbers, cadence, and cold DNC | BatchDialer | Do not control in version one |
| Campaign and agent identity | BatchDialer | Discover and preserve provider attribution |
| Raw completed-call evidence | BatchDialer | Retrieve through the official API and archive safely |
| No-answer, voicemail, wrong number, not interested, and ordinary callback | BatchDialer | Preserve evidence; do not manufacture a warm Lead |
| Qualified seller and appointment-set handoff | Stonegate after eligible result | Create or update one warm Lead |
| Seller, property, qualification, source, and notes | Stonegate after handoff | Normalize, conflict-check, enrich, and preserve provenance |
| Staff alert, speed-to-lead, AI preparation, and research | Stonegate | Trigger once per genuine warm handoff; research only a usable property |
| Calendar appointment | Stonegate | VA enters and manages it manually |
| Seller communication after handoff | Stonegate Inbox and company lines | Preserve one communication timeline |
| Contract, deal, buyer, and finance history | Stonegate | BatchDialer has no authority |

## 4. Version-One Direct API Scope

Stonegate uses only the provider operations listed in
[`BATCHDIALER_API_CONTRACT.md`](./BATCHDIALER_API_CONTRACT.md):

- `GET /campaigns` for provider campaign discovery;
- `GET /v2/cdrs` with a bounded date, page length, and cursor for completed calls;
- `GET /contact/{contactID}` to enrich an eligible warm handoff;
- optional `POST /cdrs/by-lead-id` only when a nonblank provider vendor-contact ID exists; and
- optional `GET /cdrs/{cdrID}/transcription` after the handoff, without making the transcript a
  prerequisite for lead creation.

Version one does not:

- use the stateful `/v2/cdrs/last` endpoint;
- poll or import BatchDialer calendar events;
- automatically create, reschedule, or cancel a Stonegate Appointment;
- write DNC, cadence, campaign, contact, or result state back to BatchDialer;
- place calls from Stonegate or reactivate the native browser softphone;
- scrape the BatchDialer interface or use undocumented private endpoints;
- infer contact permission from a phone number or disposition;
- discard a qualified seller solely because permission or property data is incomplete;
- overwrite staff-reviewed Stonegate facts silently;
- merge conflicting identities automatically; or
- expose, rotate, delete, or otherwise modify credentials.

## 5. Call-Result Rules

Only exact manager-reviewed provider labels are eligible for automatic lead creation. Version one
uses the exact punctuation observed in the controlled account. A renamed, unknown, or conflicting
label is quarantined for review and never silently creates a Lead.

| BatchDialer result | Stonegate effect |
| --- | --- |
| Qualified Seller - Follow Up | Create or update one warm Lead, preserve provider facts and notes, start normal lead work, and send one staff alert |
| Appointment Set | Perform the qualified handoff, mark appointment entry pending, and create one urgent manual-entry task; do not create an Appointment |
| Callback | Preserve provider evidence and callback context; do not manufacture a warm Lead solely from a cold callback |
| No Answer or Voicemail | Preserve provider evidence only; keep outside Leads |
| Not Interested | Preserve provider evidence only; do not create or reopen a Lead |
| Wrong Number | Preserve provider evidence only; BatchDialer controls redial behavior |
| Do Not Call | Preserve provider evidence only; BatchDialer remains the cold-calling DNC authority |
| Unknown or renamed result | Quarantine as `needs_review`; do not create a Lead |

Missing permission evidence must not make a qualified seller disappear. Stonegate records the
permission state as unknown and never manufactures SMS consent. Staff can record permission later
from a real conversation or another valid source.

An unknown provider agent or a VA email that differs from a Stonegate login must not block the
handoff. Stonegate preserves provider identity, assigns the configured acquisitions owner, and
surfaces the mapping issue for review.

## 6. Direct Technical Architecture

    Official BatchDialer API
        -> fixed-host authenticated client
        -> bounded date-partitioned worker poll
        -> durable raw CDR observation
        -> checkpoint advances only after archive commit
        -> exact disposition classifier
        -> idempotent direct business processor
        -> lead/contact/property conflict checks
        -> Lead + attribution + activity + staff alert
        -> CommunicationRecord + CallRecord timeline evidence
        -> optional transcript enrichment
        -> urgent manual-appointment task when applicable
        -> persisted health, lag, failure, and quarantine evidence

### 6.1 Client Safety

The direct client must:

- use the fixed official host `https://app.batchdialer.com/api`;
- authenticate with the raw key in `X-ApiKey`;
- reject redirects;
- use bounded timeouts, response bytes, pages, and retries;
- distinguish authentication, temporary, permanent, and contract failures;
- honor bounded `Retry-After` guidance when present; and
- never log the API key or an unsafe recording URL.

### 6.2 Polling And Recovery

The worker scans a bounded rolling date window and starts each date from the first page because a
safe stateful provider watermark and deterministic tie-breaker have not been proven. Durable raw
identity and semantic business idempotency make overlapping scans safe.

Rules:

- archive every new provider revision before recording scan success;
- an empty item list ends that bounded date scan even if the provider returns another cursor, while
  recording the cursor anomaly;
- a repeated cursor or maximum-page boundary fails the scan visibly;
- authentication failures stop provider work and surface a readiness blocker;
- temporary failures retry within configured bounds and retain the checkpoint for catch-up;
- ordinary service restarts resume from durable database state; and
- a provider outage never switches Stonegate to another intake transport.

### 6.3 Idempotency

The system maintains two boundaries:

- raw observation identity from the provider CDR identity plus a revision/content fingerprint; and
- business-action identity from the provider campaign, contact, call, result, and relevant revision.

Together they must guarantee one Lead, staff alert, attribution trail, research workflow, call
timeline, and manual-appointment task across overlapping polls, retries, revisions, and restarts.

### 6.4 Durable Records

| Record | Responsibility |
| --- | --- |
| `ProspectingProviderEvent` | Raw/revision evidence, provider IDs, processing state, retries, and errors |
| `BatchDialerSyncCheckpoint` | Lease, next poll, last attempt/success, scan health, counters, and failure detail |
| `BatchDialerCampaign` | Latest provider campaign snapshot and direct-sync counters |
| Lead qualification context | Provider campaign/contact/call/result identity, permission state, source facts, and appointment-entry warning |
| `CommunicationRecord` and `CallRecord` | Inbox and seller-timeline representation of the provider call |
| `Task` with type `batchdialer_manual_appointment` | Idempotent urgent manual Stonegate appointment work |

## 7. Manual Appointment Workflow

1. The direct worker sees exact **Appointment Set** on a completed provider call.
2. Stonegate creates or updates the warm Lead exactly once.
3. Stonegate sets the Lead's appointment state to **Needs scheduling**, records the provider source,
   creates one urgent **Enter/verify Stonegate appointment** task, and shows a pending warning.
4. The task links to `/os/leads/{lead_id}?tab=appointments`.
5. The VA opens the Lead, enters the real date, time, type, owner, and location, and saves the
   Stonegate Appointment.
6. Stonegate automatically resolves the task and warning when an active Appointment exists.
7. The missing-appointment task remains visible and escalates while the Appointment is genuinely
   absent.

No provider calendar event is accepted as the Stonegate calendar of record.

## 8. Credentials And Configuration

The direct integration is active whenever its required API key is configured. It does not have a
second transport mode.

Configuration responsibilities:

- `BATCHDIALER_API_BASE_URL=https://app.batchdialer.com/api`
- `BATCHDIALER_API_KEY`
- `BATCHDIALER_POLL_SECONDS`
- `BATCHDIALER_SCAN_DAYS`
- `BATCHDIALER_ACCOUNT_TIMEZONE`
- `BATCHDIALER_PAGE_LENGTH`
- `BATCHDIALER_MAX_PAGES_PER_DAY`
- `BATCHDIALER_HTTP_TIMEOUT_SECONDS`
- `BATCHDIALER_HTTP_MAX_ATTEMPTS`
- `BATCHDIALER_EVENT_MAX_ATTEMPTS`
- `BATCHDIALER_EVENT_RETRY_BASE_SECONDS`
- `BATCHDIALER_CAMPAIGN_REFRESH_SECONDS`
- `BATCHDIALER_CHECKPOINT_LEASE_SECONDS`
- `BATCHDIALER_TRANSCRIPT_SYNC_ENABLED`
- `PROSPECTING_NATIVE_DIALER_ENABLED=false`

No documentation or code task authorizes inspection, disclosure, rotation, deletion, or replacement
of the owner's credential. The owner places the key in the requested Render secret fields. Logs and
status surfaces show only safe presence/readiness information.

## 9. Implementation Phases

### BD0. Preserve And Dormant The Native Dialer

- keep historical tables, migrations, recordings, transcripts, analytics, and cleanup paths;
- force native call execution off in API and worker configuration;
- hide normal activation, softphone, Dialer Control, and Pilot Acceptance paths;
- preserve manual Prospecting qualification and records without a native lease; and
- verify zero active native sessions, legs, provider calls, or pilots in production.

Exit gate: native calling cannot start, while historical evidence and ordinary CRM work remain
readable.

### BD1. Record The Constrained Official API Contract

- retain the sanitized controlled evidence package and `ready_for_bd2=false` historical marker;
- document the owner's decision to defer additional live scenarios;
- implement only official, observed endpoints under conservative compatibility rules;
- require exact result labels and quarantine every unknown or renamed result;
- use bounded date scans rather than the unproven stateful latest-CDR operation; and
- keep recording/history/transcript enrichment optional.

Exit gate: tests enforce every constrained assumption; the evidence record is never presented as a
fully proven provider contract.

### BD2. Build The Fixed-Host Direct Client

- implement campaign, CDR, contact, optional history, and optional transcript retrieval;
- enforce authentication, redirect, timeout, response-size, retry, and error boundaries; and
- verify secrets never appear in logs or exceptions.

Exit gate: contract and failure tests pass against sanitized fixtures.

### BD3. Add Durable Sync State

- add checkpoint and provider campaign records through an additive migration;
- lease one poller per organization/stream;
- archive raw observations before advancing success state; and
- preserve cumulative health and provider campaign evidence.

Exit gate: restart, overlap, crash-boundary, cursor-loop, empty-page, and page-cap tests pass.

### BD4. Implement Live Direct Polling

- refresh active campaigns on a bounded interval;
- rescan the configured date window from page one;
- archive new and changed CDR revisions idempotently; and
- surface authentication, contract, pagination, and lag failures.

Exit gate: a bounded controlled provider scan completes, archives evidence, and catches up after a
temporary failure without another transport.

### BD5. Implement Warm Handoffs And Call Evidence

- classify only exact approved qualified results;
- create or update one Lead even when permission or address facts are incomplete;
- preserve source, VA, campaign, CDR, notes, and qualification context;
- use a visible placeholder/data-quality path rather than discarding an incomplete seller;
- skip property research until a usable property identity exists;
- create one staff alert, attribution trail, activity, and call timeline; and
- keep callback and non-lead results as evidence only.

Exit gate: controlled provider records create the correct CRM result exactly once and never invent
consent.

### BD6. Enforce Manual Stonegate Appointment Entry

- never poll or accept provider calendar events;
- create one urgent manual-entry task for **Appointment Set**;
- deep-link the VA to the Lead's appointment tab;
- resolve the task only when an active Stonegate Appointment exists; and
- escalate while the appointment remains missing.

Exit gate: one provider result creates one Lead and one task, not an Appointment; manual entry clears
the task and warning.

### BD7. Add Direct Health And Operational Visibility

- show credential readiness, worker heartbeat, poll attempt/success, lag, counts, oldest pending
  event, authentication failure, and quarantined dispositions without exposing secrets;
- keep failures durable and retryable; and
- document daily health and provider-outage recovery.

Exit gate: every eligible handoff is processed once or visibly explained with a recovery path.

### BD8. Production Acceptance And Reconciliation

- configure the direct key and deploy API/worker changes;
- verify active campaigns and exact result labels;
- run one controlled qualified result and one controlled Appointment Set result;
- verify replay/overlap produces no duplicate Lead, alert, research, call, or task;
- reconcile provider CDR identities against Stonegate for at least 24 hours; and
- verify provider outage catch-up and unknown-label quarantine.

Exit gate: zero eligible misses, duplicate actions, or wrong-contact merges; appointment results
produce manual tasks only; direct lag remains within the approved threshold.

### BD9. Direct-Only Cleanup And Routine Operations

- remove every obsolete BatchDialer third-party transport route, schema, service, variable, test,
  and operating instruction while preserving raw historical evidence;
- keep Facebook lead-form automation separate and unchanged;
- update the system map, setup references, user/staff manuals, and UI control reference;
- publish daily health, exception review, new-campaign discovery, manual appointment, provider
  outage, and reconciliation procedures; and
- preserve the native-dialer dormant regression suite.

Exit gate: a new BatchDialer campaign appears through official discovery without creating an
external automation, changing a campaign environment allowlist, or redeploying Stonegate.

## 10. Progress Ledger

| Phase | Status | Required evidence |
| --- | --- | --- |
| BD0 Native-dialer dormancy | Repository prepared; production verification pending | Production drain, deploy, and no-call verification |
| BD1 Constrained API contract | Owner-approved constrained implementation; historical evidence remains partial | Contract tests enforce exact labels, bounded pagination, and unresolved-field quarantine |
| BD2 Direct client | Implemented and repository-verified | Secure official client and failure tests |
| BD3 Durable sync state | Implemented and repository-verified | Migration, lease, checkpoint, campaign, restart, and pagination tests |
| BD4 Live direct polling | Implemented and repository-verified | Controlled provider retrieval and catch-up evidence |
| BD5 Warm handoff and call evidence | Implemented and repository-verified | One correct CRM action per eligible provider call |
| BD6 Manual calendar workflow | Implemented and repository-verified | One task, no automatic Appointment, manual resolution and escalation |
| BD7 Health and visibility | Implemented and repository-verified | Persisted direct health, lag, failures, and quarantine evidence |
| BD8 Production acceptance | Pending owner/provider action | Controlled direct results plus 24-hour reconciliation |
| BD9 Direct-only cleanup | Implemented and repository-verified | No obsolete BatchDialer third-party transport surface; current documentation |

## 11. Cross-Phase Acceptance Matrix

Tests must cover:

- missing and valid direct API credential behavior without disclosure;
- fixed host, no redirects, timeout, response-size, 401/403, 429, 5xx, and retry limits;
- campaign discovery and refresh;
- empty-page cursor anomaly, cursor cycle, maximum pages, overlap, late order, restart, and crash
  boundaries;
- one raw observation per revision and one business action across rescans;
- exact Qualified Seller and Appointment Set results;
- unknown and renamed result quarantine;
- callback and non-lead evidence without Lead pollution;
- incomplete property and unknown permission without silent loss or fabricated consent;
- provider agent mismatch without blocking a handoff;
- one Lead, alert, attribution trail, and call timeline per warm handoff;
- property research only after a usable property identity exists;
- one urgent manual-appointment task and no automatic Appointment;
- task resolution after a Stonegate Appointment is entered;
- optional transcript absence without handoff failure;
- no native call execution in dormant mode; and
- historical evidence and manual Prospecting readability.

## 12. Production Acceptance Checklist

Before the direct integration is considered accepted, verify:

1. The native dialer is dormant in API and worker, with no active native call state.
2. The BatchDialer key is present only in authorized secret configuration and absent from logs.
3. Direct authentication succeeds against the fixed official host.
4. Active provider campaigns are discovered and visible.
5. Exact qualifying and appointment result labels are recognized; an unknown label quarantines.
6. Qualified and appointment-set results create or update exactly one Lead.
7. Staff receive one correctly labeled BatchDialer alert.
8. Source, owner, property state, notes, attribution, and call evidence are correct.
9. Appointment Set creates one urgent task and no automatic Appointment.
10. A VA can enter the real Appointment in Stonegate and clear the task.
11. Overlapping scans and provider replay create no duplicate side effects.
12. A temporary provider outage catches up from durable state.
13. A 24-hour reconciliation finds no eligible miss, duplicate action, or wrong identity merge.

## 13. Version-One Definition Of Done

Version one is done only when:

- BatchDialer is the only active VA calling runtime;
- the official direct API is the only BatchDialer-to-Stonegate integration;
- the native Stonegate dialer is dormant and cannot place a call;
- Stonegate retrieves supported provider data through bounded, durable polling;
- qualified and appointment-set results create or update one Lead exactly once;
- notes, attribution, available call evidence, and data-quality gaps are preserved;
- non-lead results do not pollute Leads or mutate Stonegate suppression;
- Appointment Set creates a visible urgent manual-entry task, never an automatic Appointment;
- VAs create and manage appointments directly in Stonegate;
- health, lag, failures, and quarantined results are visible;
- provider outages recover from durable checkpoint state; and
- controlled direct acceptance and 24-hour reconciliation pass.

## 14. Official Provider References

- [BatchDialer developer documentation](https://developer.batchdialer.com/docs/batchdialer/f4e6fa31af431-getting-started)
- [BatchDialer API index](https://developer.batchdialer.com/)
- [BatchDialer pricing and API description](https://batchdialer.com/pricing)

Provider documentation, plan availability, rate limits, and endpoint behavior must continue to be
checked conservatively. An unobserved or undocumented field remains optional and quarantined until
reviewed.
