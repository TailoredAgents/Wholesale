# Integrations

Last updated: July 21, 2026

All providers are adapters. PostgreSQL remains the business source of truth.

## Status

| Provider | Purpose | Code | External setup |
| --- | --- | --- | --- |
| Clerk | Staff authentication | Live | Verify MFA and final custom-domain origins |
| Render | Web, API, worker, PostgreSQL, Key Value | Live | Custom domain and final production checks pending |
| RentCast | Property facts and recorded-sale comps | Live | Continue usage and accuracy monitoring |
| OpenAI | Transcription, structured call notes, future agents | Implemented | Recording activation and agent evaluations pending |
| Twilio Messaging | Seller SMS | Implemented | Dedicated A2P Campaign under review; final sender cutover pending |
| Twilio Voice | Browser and inbound calls | Implemented | API key, TwiML App, Render activation, and webhook tests pending |
| Google Workspace | Operational seller email | Implemented | Domain, OAuth project, secrets, and mailbox connections pending |
| Stonegate internal calendar | Appointments and reminders | Implemented | System of record; no external provider required |
| DNC screening vendor | Cold-call eligibility evidence | Evidence intake implemented | Live provider not selected; import or review a retained vendor result |
| Smartlead or equivalent | Future cold email | Not implemented | Separate compliance and infrastructure decision required |
| Object storage | Contracts and persistent files | Not selected | Planned before transaction document automation |
| E-signature | Contracts | Not selected | Planned in transaction phase |
| QuickBooks Online | Accounting | Not implemented | Planned after finance workflow completion |
| Google Ads / Meta | Offline conversion delivery | Foundation records only | Provider adapters and retries remain |
| Error monitoring | Production alerts | Not selected | Roadmap Phase 2 |

## Shared Controls

- Keep secrets in Render or provider dashboards, never browser variables or git.
- Validate signed webhooks.
- Retain external IDs and provider-event IDs.
- Use idempotency keys for outbound work.
- Store normalized business records separately from raw provider metadata.
- Enforce organization and role scope.
- Handle retries, stale cursors, rate limits, and provider outages.
- Provide a disabled or test state before production activation.
- Write audit events for material provider-backed actions.

## DNC Screening

Stonegate can retain DNC results supplied in a vendor list and can record a later manager-reviewed
result with its provider or report reference. The system separately checks Stonegate's internal
Voice suppression records. A prospect without clear retained DNC evidence remains review-only and
cannot enter a calling batch.

No live national DNC provider is currently connected. Selecting one remains an external vendor and
legal-process decision; the integration must write through the existing evidence model rather than
bypassing it.

## OpenAI

OpenAI transcription and model calls are server-side. Runs record the model, prompt version,
latency, token usage, pricing version, estimated cost, status, evidence, and human-review outcome.

Call intelligence is implemented but cannot update CRM facts or create tasks without review. Future
agents must use the permission, approval, trace, and evaluation controls described in
`AI_AGENTS.md`.

## Twilio Messaging

The API supports:

- Messaging Service dispatch.
- Signed inbound and delivery webhooks.
- Idempotent provider events.
- Shared-inbox timeline updates.
- Consent, suppression, valid-number, role, provider, and contact-hour gates.
- STOP and START consent history.

Current status: Stonegate submitted a separate Low Volume Mixed A2P Campaign using the live public
opt-in and legal pages. The campaign, new Messaging Service, and newly purchased SMS number must
remain separate from every other business.

After approval, configure:

- `TWILIO_MESSAGING_SERVICE_SID`: new Stonegate Messaging Service.
- `TWILIO_SMS_FROM_NUMBER`: newly purchased and campaign-approved SMS number.

Do not substitute the Voice/support number unless Stonegate explicitly decides to register that
number as an SMS sender. See `RUNBOOKS/twilio-a2p-campaign.md` and
`RUNBOOKS/twilio-sms-setup.md`.

## Twilio Voice

The Voice implementation uses short-lived browser tokens and one-time conversation-scoped call
intents. Inbound calls route to the conversation owner or line assignee. Unknown callers create a
retained lead, and missed calls create urgent return-call tasks.

Recording, speaker-separated transcription, AI note extraction, retention, and audited deletion
are implemented but recording remains disabled until the spoken disclosure and retention policy
are approved.

Voice setup is paused until Stonegate resumes provider configuration. See
`RUNBOOKS/twilio-voice-setup.md`.

## Google Workspace

Operational mailboxes connect individually through server-side OAuth. Tokens are encrypted.
Messages preserve Gmail threads and share the seller conversation timeline with SMS, calls,
transcripts, and notes.

Cold outreach is excluded. Future cold email must use separate domains/mailboxes and a dedicated
outreach adapter. See `RUNBOOKS/google-workspace-email.md`.

## Property Data

RentCast is the current low-cost provider for property facts and recorded sales. The underwriting
service retains normalized comparable evidence and exclusion reasons.

ATTOM or licensed MLS/RESO data may be added later behind the same adapter boundary. Provider data
must not silently overwrite human-confirmed facts.
