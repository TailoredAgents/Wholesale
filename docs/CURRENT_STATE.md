# Current State

Last updated: July 21, 2026

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
- Lead quality, urgency, qualification gaps, and deterministic next-best-action guidance.
- Notes, appointments, underwriting versions, transactions, and buyer offers on the lead
  workspace.

### Shared Inbox And Team Workflow

- Three-panel shared inbox with Mine, Unassigned, Team, Needs Reply, Appointments, and Unread views.
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
- Reports remain available even when renovation status is not yet confirmed.

Underwriting is decision support, not an appraisal. It requires continued comparison against real
transactions and human judgment before Stonegate relies on it for offer ceilings.

### Downstream Operations

- Transaction records and default closing checklist.
- Buyer CRM, buyer criteria, proof-of-funds status, deal queue, and buyer offers.
- Revenue, deductions, compensation rules and calculations, and marketing spend.
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
- Calendar synchronization is not implemented.
- Duplicate review and manual merge are not implemented.
- Contract templates, e-signature, document storage, and checklist completion workflows are not
  complete.
- Buyer matching and deal-distribution automation are not complete.
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
3. Continue with Phase 2 acquisition workflow completion in `docs/ROADMAP.md`.
4. Resume the external integration gate after A2P approval without blocking internal development.
