# Integrations

Last updated: July 27, 2026

All external providers are adapters. PostgreSQL remains the platform database. The internal
Stonegate Accounting Ledger is a native subsystem, not a provider integration.
`PRODUCTION_CREDENTIALS_CHECKLIST.md` is the canonical account and environment-variable inventory.

## Status

| Provider | Purpose | Code | External setup |
| --- | --- | --- | --- |
| Clerk | Staff authentication | Live | Verify MFA for every privileged user and retain both branded and Render fallback origins |
| Render | Web, API, worker, PostgreSQL, Key Value | Live | Branded web domain is active; final production operator checks remain |
| RentCast | Property facts, valuation estimates, and sale-listing-based comps | Live | Continue validation; do not label provider estimates as appraisals or verified closed sales |
| OpenAI | Transcription, structured call notes, future agents | Implemented | Recording activation and agent evaluations pending |
| Twilio Messaging | Seller SMS | Implemented | Dedicated A2P Campaign under review; final sender cutover pending |
| Twilio Voice | Browser and inbound calls | Implemented | API key, TwiML App, Render activation, and webhook tests pending |
| Resend | Operational seller email | F8.2-F8.3 provider-neutral foundation, aliases, grants, owner APIs, and tested outbound adapter implemented | Build inbound webhooks/recovery and Inbox administration, verify DNS, register signed webhooks, and run acceptance tests |
| Stonegate internal calendar | Appointments and reminders | Implemented | System of record; no external provider required |
| National DNC API | None planned | Not used | Application-level DNC evidence integration was removed at Owner direction |
| Smartlead or equivalent | Future cold email | Not implemented | Separate compliance and infrastructure decision required |
| Cloudflare R2 | Private uploaded files | Adapter implemented; database fallback active | Create private bucket/token, configure Render, then run upload/download/delete acceptance |
| SignWell | Contract execution and event evidence | Adapter, owner connection, webhook registration, and test simulation implemented | Add API key, connect in Transactions, load attorney templates, then run controlled test-mode acceptance |
| Stonegate Accounting Ledger | Internal bookkeeping and financial statements | Deal-finance foundation only | Build the double-entry ledger, bank reconciliation, close, reporting, and CPA acceptance in F6 |
| Google Ads / Meta | Offline conversion delivery | Foundation records only | Consent, hashing, provider adapters, and retries remain |
| Address and routes | Address quality and field dispatch | Not selected | Optional when operating data justifies the cost |
| Sentry | Web, API, and worker error reporting and traces | Implemented; disabled without DSNs | Create projects, configure Render DSNs, send controlled test errors, and approve alert routing |

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

## Production Monitoring

Sentry is the selected error-monitoring provider. The web, API, and worker integrations are
disabled when their DSNs are absent. Default PII, request-body capture, and Python local-variable
capture are disabled. Start with a 5% trace sample and route production alerts to an
owner-controlled destination.

The scheduled GitHub Actions production-readiness workflow checks API health, database and worker
readiness, and required public pages every 15 minutes. It supplements Sentry and worker failure
alerts; it does not replace either one.

## Do-Not-Contact Data

Stonegate can read an optional do-not-call flag supplied in a vendor list and separately checks its
internal Voice suppression records. Blank or unknown vendor values do not block imports or calling
batches. Explicit do-not-call values, seller opt-outs, and active company suppression still block
outbound contact.

No live national DNC provider is connected.

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

## Resend

Resend is the approved operational email provider. The existing Gmail/OAuth implementation is
disabled legacy code and will not be activated.

Stonegate will send from approved company aliases through the Resend API and receive replies
through Resend Receiving and signed webhooks. The shared Inbox remains the staff mailbox, and
PostgreSQL remains the communication source of truth. Staff will not connect individual OAuth
mailboxes.

The adapter must preserve provider IDs and email thread headers, retrieve inbound bodies and
attachments, deduplicate at-least-once webhook delivery, tolerate out-of-order events, recover
missed inbound events, and record sent, delivered, delayed, bounced, complained, failed,
suppressed, and received states.

Stonegate has approved `stonegatehb.com` for root-domain sending and receiving because the OS is
the intended company mailbox and the domain has no competing mailbox provider. Resend receives
mail for every address on the configured receiving domain, so any future mailbox-provider change
requires deliberate MX or forwarding design.

Cold outreach is excluded. Future cold email must use separate domains, sender reputation,
compliance rules, and a dedicated outreach adapter. See `RUNBOOKS/resend-email.md`.

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

- Cloudflare R2 is selected for private persistent uploads. The storage adapter covers photographs,
  buyer proof of funds, legal templates, transaction evidence, and provider-completed agreements.
  Existing database files remain readable, and new files switch to R2 after production
  configuration. Stonegate stores object keys rather than public URLs.
- Twilio remains the recording-media provider behind Stonegate's authenticated recording
  endpoint. Valuation PDFs remain generated authenticated responses rather than persistent files.
- SignWell is selected for e-signature. The adapter retains envelope, recipient, document, test
  mode, reconciliation, and deduplicated webhook-event identifiers. Provider completion retrieves
  the final PDF but cannot bypass Stonegate's package approval, checklist, or funding gates.
- See `PHASE_F4_DOCUMENTS_ESIGN.md` for environment values and production acceptance.
- Extend Stonegate's existing Finance records into the internal Stonegate Accounting Ledger. Add a
  versioned chart of accounts, balanced and immutable posted journals, accounting periods, bank
  reconciliation, vendors, supporting evidence, financial statements, and CPA exports.
- Existing lead, transaction, reconciliation, compensation, payout, and marketing records remain
  operational source evidence. The ledger references those records and must never duplicate their
  business workflow.
- A read-only bank-data provider may be added later behind an adapter. The initial accounting
  release imports statements and does not move money, run payroll, file taxes, or submit payments.
- AI may classify files, extract proposed fields, and identify mismatches. It cannot sign, alter
  approved legal language, release agreements, mark funding complete, post journals, close
  periods, move money, or make final tax classifications.

## Marketing Measurement

Stonegate's existing attribution records now feed one governed conversion queue:

- Outcomes: `qualified_lead`, `appointment_scheduled`, `contract_signed`, and `funded_deal`.
- Rule: last eligible click for each platform within 90 days and before the outcome. A Google click
  never substitutes for a Meta click, or vice versa.
- Matching: platform click ID plus normalized SHA-256 email and phone identifiers when available.
  Raw email and phone values are not retained in the provider payload snapshot.
- Deduplication: one stable versioned event key per source record, outcome, and platform.
- Delivery: `pending`, `retry`, `delivered`, `simulated`, `blocked`, or `exhausted`, with
  exponential retry timing, sanitized provider responses, and an audit event for every attempt.
- Google uses the Data Manager API `events:ingest` route and maps each Stonegate outcome to a
  separate Google Ads conversion action.
- Meta uses the Conversions API server-event route and maps events to Lead, Schedule,
  ContractSigned, and Purchase.
- `MARKETING_CONVERSION_MODE=disabled` prepares and audits the queue without external delivery.
  Production simulation is prohibited. Use provider test tools before enabling `live`.

The public privacy notice is the recorded basis for first-party advertising measurement. The
adapters do not assert Google advertising consent fields that Stonegate has not separately
captured.

- AI may recommend experiments. Humans approve budgets, campaigns, creative, audiences, and
  published changes.

## Email And Cold Outreach

Resend webhooks provide at-least-once delivery and may arrive out of order. Stonegate must verify
signatures, deduplicate event IDs, order state using provider timestamps, and run a periodic
received-email recovery job.

Operational seller email and future cold email remain separate. A future outreach platform must
enforce approved domains, volume ramps, suppression, opt-out handling, sender identity, and
CAN-SPAM controls. It may create interested prospects for human qualification; it must not mix cold
mailbox reputation with day-to-day seller and closing mail.

## Recommended API Sequence

1. Finish dedicated Twilio SMS, Twilio Voice, recording policy, and the Resend migration.
2. Complete Sentry provider acceptance and select private object storage.
3. Complete OpenAI evaluation datasets, model routing, and the governed tool gateway.
4. Add e-signature before transaction-document automation.
5. Build the internal Stonegate Accounting Ledger after funded-deal reconciliation is verified and
   have a CPA approve its policies, opening balances, reports, and month-end process.
6. Complete Google and Meta provider acceptance, then enable the implemented conversion delivery.
7. Add a second property-data source, address validation, or live routes only when operating
   evidence shows the current solution is insufficient.

## Official References

- [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model)
- [OpenAI Agents SDK](https://developers.openai.com/api/docs/guides/agents)
- [OpenAI agent evaluations](https://developers.openai.com/api/docs/guides/agent-evals)
- [RentCast property valuation](https://developers.rentcast.io/reference/property-valuation)
- [Twilio Voice JavaScript SDK](https://www.twilio.com/docs/voice/sdks/javascript)
- [Resend sending API](https://resend.com/docs/api-reference/emails/send-email)
- [Resend Receiving](https://resend.com/docs/dashboard/receiving/introduction)
- [Resend webhook behavior](https://resend.com/docs/webhooks/introduction)
- [IRS business recordkeeping](https://www.irs.gov/businesses/small-businesses-self-employed/recordkeeping)
- [IRS Publication 583](https://www.irs.gov/publications/p583)
- [Sentry Python SDK](https://getsentry.github.io/sentry-python/)
- [Sentry Next.js SDK](https://docs.sentry.io/platforms/javascript/guides/nextjs/)
- [Docusign Connect webhooks](https://developers.docusign.com/platform/webhooks/connect/)
- [Google Data Manager event ingestion](https://developers.google.com/data-manager/api/reference/rest/v1/events/ingest)
- [Google Data Manager send-events guide](https://developers.google.com/data-manager/api/devguides/events/send-events)
- [Meta Conversions API](https://www.facebook.com/business/help/AboutConversionsAPI)
- [FTC Telemarketing Sales Rule guidance](https://www.ftc.gov/business-guidance/resources/complying-telemarketing-sales-rule)
- [FTC CAN-SPAM compliance guidance](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business)
