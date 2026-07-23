# Integrations

Last updated: July 23, 2026

All providers are adapters. PostgreSQL remains the business source of truth.

## Status

| Provider | Purpose | Code | External setup |
| --- | --- | --- | --- |
| Clerk | Staff authentication | Live | Verify MFA for every privileged user and retain both branded and Render fallback origins |
| Render | Web, API, worker, PostgreSQL, Key Value | Live | Branded web domain is active; final production operator checks remain |
| RentCast | Property facts, valuation estimates, and sale-listing-based comps | Live | Continue validation; do not label provider estimates as appraisals or verified closed sales |
| OpenAI | Transcription, structured call notes, future agents | Implemented | Recording activation and agent evaluations pending |
| Twilio Messaging | Seller SMS | Implemented | Dedicated A2P Campaign under review; final sender cutover pending |
| Twilio Voice | Browser and inbound calls | Implemented | API key, TwiML App, Render activation, and webhook tests pending |
| Google Workspace | Operational seller email | Implemented | Domain, OAuth project, secrets, and mailbox connections pending |
| Stonegate internal calendar | Appointments and reminders | Implemented | System of record; no external provider required |
| FTC National DNC data and screening process | Cold-call eligibility evidence | Evidence intake implemented | Secure registry access, recurring refresh, and legal review still required |
| Smartlead or equivalent | Future cold email | Not implemented | Separate compliance and infrastructure decision required |
| Object storage | Recordings, photos, contracts, and persistent files | Not selected | Required before AI document automation |
| E-signature | Contract execution and event evidence | Not selected | Required before AI transaction automation |
| QuickBooks Online | Accounting reconciliation | Not implemented | Planned for finance intelligence; final entries stay human-approved |
| Google Ads / Meta | Offline conversion delivery | Foundation records only | Consent, hashing, provider adapters, and retries remain |
| Address and routes | Address quality and field dispatch | Not selected | Optional when operating data justifies the cost |
| Error monitoring | Errors, traces, and production alerts | Not selected | Select before production AI pilots; Sentry is the current recommendation |

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

No live national DNC provider is currently connected. The FTC registry is accessed through its
secure telemarketer portal and downloaded data, not the public DNC complaint-report API. Stonegate
needs an approved access account, subscription/area-code plan, retained screening evidence, and a
recurring process that keeps data within the required refresh window. A screening vendor may
perform this work, but its result must write through the existing evidence model and does not
remove Stonegate's responsibility for company suppression, written procedures, training, or
monitoring.

## OpenAI

OpenAI transcription and model calls are server-side. Runs record the model, prompt version,
latency, token usage, pricing version, estimated cost, status, evidence, and human-review outcome.

Call intelligence is implemented but cannot update CRM facts or create tasks without review. Future
agents must use the permission, approval, trace, and evaluation controls described in
`AI_AGENTS.md`. `AI_AUTOMATION_ROADMAP.md` defines the promotion order.

The recommended model interface is the Responses API behind Stonegate's existing orchestrator.
`gpt-5.6-sol` with medium reasoning is the deployment default until Stonegate evaluations
show a cheaper or stronger tier is better for a specific capability. Use
`gpt-4o-transcribe-diarize` for recorded calls that need speaker separation. Web search is
restricted to approved research workflows with citations and is not a comparable-sales source.

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

RentCast is the current low-cost provider for property facts, valuation estimates, and comparable
sale-listing data. Its valuation endpoint allows subject attributes, search radius, age, and comp
count to influence results. Those estimates are useful inputs, but they are not an appraisal and
must not be described as verified closed-sale records without separate evidence.

ATTOM or licensed MLS/RESO data may be added later behind the same adapter boundary. Provider data
must not silently overwrite human-confirmed facts. Before expansion or material offer volume,
Stonegate should compare RentCast outputs with human-reviewed comps and verified outcomes. Add a
licensed MLS/RESO feed or ATTOM only when measured error, coverage, or operator time justifies the
cost.

## Accounting, Documents, And E-Signature

- Use private S3-compatible object storage for recordings, photographs, reports, and contract
  files. Store metadata and access policy in Stonegate; store provider object keys rather than
  public URLs.
- Add e-signature through an adapter that retains envelope, recipient, document, and webhook-event
  identifiers. Provider completion cannot bypass Stonegate's contract and funding gates.
- Connect QuickBooks Online through OAuth after internal reconciliation is stable. Stonegate
  prepares reviewed entries and retains provider IDs; QuickBooks remains the accounting ledger.
- AI may classify files, extract proposed fields, and identify mismatches. It cannot sign, alter
  approved legal language, release agreements, mark funding complete, or post final accounting
  changes without human authority.

## Marketing Measurement

Send down-funnel outcomes only after attribution and consent rules are defined:

- Google enhanced conversions for leads can match offline outcomes using click identifiers and
  normalized, hashed first-party data. For a new integration after June 15, 2026, evaluate Google's
  Data Manager API because new offline-upload developer tokens have additional restrictions.
- Meta's Conversions API may receive qualified-lead, appointment, contract, and funded outcomes
  through a separate adapter.
- Every delivery needs an idempotency key, consent basis, provider response, retry state, and audit
  record.
- AI may recommend experiments. Humans approve budgets, campaigns, creative, audiences, and
  published changes.

## Email And Cold Outreach

Gmail push notifications use Google Cloud Pub/Sub and must be renewed. The worker also needs
incremental history synchronization and a periodic recovery path because provider notifications
can be delayed or missed.

Operational seller email and future cold email remain separate. A future outreach platform must
enforce approved domains, volume ramps, suppression, opt-out handling, sender identity, and
CAN-SPAM controls. It may create interested prospects for human qualification; it must not mix cold
mailbox reputation with day-to-day seller and closing mail.

## Recommended API Sequence

1. Finish dedicated Twilio SMS, Twilio Voice, recording policy, and Google Workspace.
2. Select error monitoring and private object storage.
3. Complete OpenAI evaluation datasets, model routing, and the governed tool gateway.
4. Add e-signature before transaction-document automation.
5. Add QuickBooks after funded-deal reconciliation is verified.
6. Add Google and Meta offline conversion delivery after attribution review.
7. Add a second property-data source, address validation, or live routes only when operating
   evidence shows the current solution is insufficient.

## Official References

- [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model)
- [OpenAI Agents SDK](https://developers.openai.com/api/docs/guides/agents)
- [OpenAI agent evaluations](https://developers.openai.com/api/docs/guides/agent-evals)
- [RentCast property valuation](https://developers.rentcast.io/reference/property-valuation)
- [Twilio Voice JavaScript SDK](https://www.twilio.com/docs/voice/sdks/javascript)
- [Gmail push notifications](https://developers.google.com/workspace/gmail/api/guides/push)
- [QuickBooks Online webhooks](https://developer.intuit.com/app/developer/qbo/docs/develop/webhooks)
- [Docusign Connect webhooks](https://developers.docusign.com/platform/webhooks/connect/)
- [Google Ads offline conversions](https://developers.google.com/google-ads/api/docs/conversions/upload-offline)
- [FTC Telemarketing Sales Rule guidance](https://www.ftc.gov/business-guidance/resources/complying-telemarketing-sales-rule)
- [FTC CAN-SPAM compliance guidance](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business)
