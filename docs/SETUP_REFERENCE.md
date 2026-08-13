# Stonegate Setup Reference

Last verified against the repository: August 8, 2026

## Purpose

This is the canonical technical setup inventory for Stonegate Home Buyers. It consolidates local
development, Render, domain, credential, webhook, and provider runbooks without storing any secret
values.

This is the maintainer reference for exact variables, URLs, and commands. Use
`SETUP_MANUAL.md` for the nondeveloper, step-by-step account setup and acceptance guide.

## Status Legend

| Status | Meaning |
| --- | --- |
| Active | Configured and accepted in production |
| Configured | Values or account setup exist; final acceptance remains |
| Pending | Account, approval, credential, or test is still required |
| Deferred | Deliberately postponed until operating volume justifies it |
| Optional | Improves operations but does not block the core workflow |

## Production Inventory

| Component | Provider/resource | Status |
| --- | --- | --- |
| Web application | Render `oakwell-web` | Active |
| API | Render `oakwell-api` | Active |
| Background worker | Render `oakwell-worker` | Active |
| Database | Render `oakwell-postgres` | Active |
| Coordination | Render `oakwell-key-value` | Active |
| Public domain | `www.stonegatehb.com` | Active |
| API domain | `api.stonegatehb.com` | Active |
| Authentication | Clerk | Active |
| AI | OpenAI | Configured; Copilot pilots pending |
| Property data | RentCast + RealEstateAPI | Active; controlled property research passed |
| Operational email | Resend | Configured; controlled acceptance pending |
| SMS | Twilio | Seller-inquiry A2P approved; website and Facebook staff alerts are implemented; repeat internal new-lead alert acceptance after the worker credential correction |
| Voice | Twilio | Implemented and processing calls; complete routing, recording, recovery, retention, and deletion acceptance pending |
| E-signature | SignWell | Configuration and acceptance pending |
| Buyer data | DealMachine | Optional and disabled; safe to remove after subscription cancellation |
| Private object storage | S3-compatible/Cloudflare R2 | Optional/pending |
| Error monitoring | Sentry | Optional/deferred |
| Ad conversion delivery | Google and Meta | Meta Pixel and Conversions API active; Google pending |

## Secret Handling Rule

This repository documents environment variable names only. Actual API keys, auth tokens, webhook
secrets, database URLs, and private account identifiers belong in Render environment variables or
local ignored `.env` files.

If a secret is pasted into chat, a screenshot, source code, or committed file, it should eventually
be rotated even when immediate development continues.

## Local Development

### Prerequisites

- Node.js 20 or newer
- npm 10 or newer
- Python 3.12
- `uv`
- PostgreSQL

### Database

```bash
createdb real_estate_wholesale
cd apps/api
uv sync
uv run alembic upgrade head
```

### Environment

Copy the root `.env.example` to `.env`. Local defaults use:

- web: `http://localhost:3000`
- API: `http://localhost:8000`
- database: local PostgreSQL
- communication mode: `simulate`
- external email, SMS, Voice, e-signature, buyer data, and ad delivery: disabled

Clerk can remain blank for local development, but development-header authentication is an explicit
opt-in. Set `DEV_AUTH_ENABLED=true` only in a local or isolated test environment when using
`X-Dev-User-Email`; the default is `false`, and production rejects the header regardless of this
value. Shared test and production environments should keep the flag false and use Clerk.

### Bootstrap

```bash
npm run bootstrap:api -- \
  --admin-email owner@example.test \
  --admin-name "Stonegate Owner"
```

For a complete synthetic workspace:

```bash
npm run seed:demo -- \
  --owner-email owner@example.test \
  --owner-name "Demo Owner"
```

### Start

API terminal:

```bash
npm run dev:api
```

Web terminal:

```bash
npm run dev:web
```

Open:

- `http://localhost:3000`
- `http://localhost:3000/get-a-cash-offer`
- `http://localhost:3000/os`
- `http://localhost:8000/health`
- `http://localhost:8000/ready`

### Local Simulation

`COMMUNICATION_PROVIDER_MODE=simulate` keeps simulated SMS and email in the normal conversation
timeline without contacting external recipients. Production rejects simulated provider delivery.

## Render Blueprint

`render.yaml` defines the services, build commands, startup commands, non-secret values, and secret
placeholders.

Render resource names still use `oakwell-*`. Do not create duplicate Stonegate-named services just
to change display names. The existing resources contain the operating database and connections.

The API startup command:

1. installs dependencies during build
2. runs Alembic migrations
3. bootstraps configured organization/admin data
4. starts Uvicorn

The worker is deployed from the API application, not the original `apps/worker` heartbeat
scaffold.

Production API startup is fail-closed. `APP_ENV` must be exactly `production`, and startup stops
when the Clerk issuer, explicit or issuer-derived JWKS endpoint, secret key, or at least one
non-local HTTPS authorized party is missing. On the web service, protected production routes return
`503` when the Clerk publishable or secret key is unavailable instead of being passed through
unauthenticated.

## Domain And Cross-Origin Setup

Canonical production values:

```text
Website: https://www.stonegatehb.com
API: https://api.stonegatehb.com
Render web fallback: https://oakwell-web.onrender.com
```

Web environment:

- `API_BASE_URL=https://api.stonegatehb.com`
- `NEXT_PUBLIC_API_BASE_URL=https://api.stonegatehb.com`
- `NEXT_PUBLIC_SITE_URL=https://www.stonegatehb.com`

API environment:

- `API_CORS_ORIGINS` must include the branded apex or `www` origin used by the browser and the
  Render fallback.
- `CLERK_AUTHORIZED_PARTIES` must include every legitimate web origin that can issue a Clerk
  browser token.
- callback base URLs must use `https://api.stonegatehb.com`.

Domain acceptance:

1. Public routes load on the branded domain.
2. `/os` redirects unauthenticated users to sign-in.
3. A signed-in user can load `/api/v1/me` without CORS or authorized-party errors.
4. API `/health` and `/ready` return successfully.
5. Clerk redirect URLs point back to the branded OS.
6. Provider webhooks use the branded API URL.

## Google Search And Local Presence

Canonical public search values:

```text
Search Console property: stonegatehb.com
Sitemap: https://www.stonegatehb.com/sitemap.xml
Initial service-area page: https://www.stonegatehb.com/service-areas/metro-atlanta
Business Profile type: service-area business unless a qualifying staffed storefront is confirmed
```

Acceptance:

1. Verify the Search Console domain property using Google's DNS TXT record.
2. Submit the canonical sitemap and inspect the homepage, service-area, contact, and offer URLs.
3. Create or claim one Stonegate Business Profile using the real business name and permanent
   company contact facts.
4. Hide the business address if customers are not served at a staffed Stonegate location.
5. Add only approved service areas Stonegate can genuinely serve; do not use a virtual office.
6. Validate homepage Organization data and service-area WebPage, Service, and BreadcrumbList data.
7. Do not add LocalBusiness structured data until a qualifying public address is confirmed.
8. Do not generate repetitive city or county pages.

Official references:

- `https://support.google.com/webmasters/answer/9008080`
- `https://support.google.com/business/answer/3038177`
- `https://support.google.com/business/answer/9157481`
- `https://developers.google.com/search/docs/appearance/structured-data/organization`
- `https://developers.google.com/search/docs/appearance/structured-data/local-business`
- `https://developers.google.com/search/docs/essentials/spam-policies`

## Core Runtime Variables

### Application And Data

- `APP_ENV`
- `DEV_AUTH_ENABLED` for deliberate local/test header authentication only; keep false in production
- `LOG_LEVEL`
- `DATABASE_URL`
- `REDIS_URL`
- `DEFAULT_ORGANIZATION_NAME`
- `BOOTSTRAP_ADMIN_EMAIL`
- `BOOTSTRAP_ADMIN_NAME`
- `API_CORS_ORIGINS`
- `WORKER_READINESS_REQUIRED`
- `WORKER_HEARTBEAT_INTERVAL_SECONDS`
- `WORKER_STALE_AFTER_SECONDS`
- `WORKER_OPERATION_STALL_SECONDS=600` in production
- worker retry and failure-alert variables

The worker's background heartbeat records process liveness independently from main-loop progress
and the current operation. `/ready` treats a missing or stale heartbeat as a liveness failure, but
does not call an active loop `stalled` until main-loop progress exceeds
`WORKER_OPERATION_STALL_SECONDS`. Keep the production value at 600 seconds unless a measured
provider-operation envelope justifies a reviewed change; this catches a live-but-hung worker
without false alarms during normal multi-provider calls.

### Clerk

- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` on web
- `CLERK_SECRET_KEY` where Clerk server operations are used
- `CLERK_ISSUER`
- `CLERK_JWKS_URL`
- `CLERK_AUDIENCE` when required by the Clerk token configuration
- `CLERK_AUTHORIZED_PARTIES`
- Clerk sign-in, sign-up, and fallback redirect variables on web

The Clerk issuer and JWKS URL belong to Clerk. They must never point at the Stonegate API. In
production the issuer is required, the JWKS URL must be explicit or derivable from that issuer,
`CLERK_SECRET_KEY` must be present, and `CLERK_AUTHORIZED_PARTIES` must contain at least one
non-local HTTPS origin. `CLERK_AUDIENCE` remains optional when the token configuration does not use
an audience.

Public-write controls on the API:

- `PUBLIC_INTAKE_RATE_LIMIT_ENABLED`
- `PUBLIC_INTAKE_RATE_LIMIT_REQUESTS`
- `PUBLIC_INTAKE_RATE_LIMIT_WINDOW_SECONDS`
- `PUBLIC_CONVERSION_EVENT_RATE_LIMIT_REQUESTS`
- `PUBLIC_CONVERSION_EVENT_RATE_LIMIT_WINDOW_SECONDS`

Seller creation and enrichment use separate route keys with the tighter intake budget. Public
conversion events use their own higher budget. In production, the application keys these limits
from the edge-owned `CF-Connecting-IP` value and ignores caller-supplied `X-Forwarded-For`; without a
valid Cloudflare address it falls back to the socket peer. Each in-process limiter hard-bounds its
tracked key set at 2,048 entries so attacker-controlled key cardinality cannot grow memory without
limit. These remain per-process safeguards: ensure the production origin accepts the client-IP
header only from the trusted edge, and add distributed edge/WAF limiting before scaled traffic or
multiple API instances.

### Monitoring

- `SENTRY_DSN`
- `NEXT_PUBLIC_SENTRY_DSN`
- `SENTRY_ENVIRONMENT`
- `NEXT_PUBLIC_SENTRY_ENVIRONMENT`
- trace sample-rate variables
- `OPERATIONS_ALERT_WEBHOOK_URL`
- `OPERATIONS_ALERT_AFTER_FAILURES`

Sentry and a separate worker alert webhook are optional operational improvements. They are not
required for the CRM, email, underwriting, or transaction workflows to function.

## OpenAI

Purpose:

- governed Copilot generation
- bounded underwriting public-record research
- call transcription and structured notes
- evaluation and production model routing

Variables:

- `AI_ENABLED`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_DEFAULT_MODEL`
- `OPENAI_HIGH_VOLUME_MODEL`
- `OPENAI_ESCALATION_MODEL`
- `OPENAI_REASONING_EFFORT`
- `OPENAI_WEB_SEARCH_ENABLED`
- `OPENAI_REQUEST_TIMEOUT_SECONDS`
- `OPENAI_PRICING_OVERRIDES_JSON`
- `OPENAI_TRANSCRIPTION_MODEL`

Activation checks:

1. AI overview reports the expected model route.
2. A draft Copilot run succeeds.
3. The run retains model, prompt, evidence, usage, cost, and review state.
4. Web search, when enabled, remains bounded and cited.
5. No Copilot receives autonomous consequential authority.

## RentCast, RealEstateAPI, And Property Data

Variables:

- `PROPERTY_DATA_PROVIDER=rentcast`
- `RENTCAST_API_KEY`
- `RENTCAST_BASE_URL=https://api.rentcast.io/v1`
- `PROPERTY_INTELLIGENCE_AUTO_RESEARCH_ENABLED=true`
- `PROPERTY_INTELLIGENCE_FRESH_DAYS=30`
- `PROPERTY_INTELLIGENCE_MAX_ATTEMPTS=3`
- `PROPERTY_INTELLIGENCE_RETRY_BASE_SECONDS=60`
- `REALESTATEAPI_API_KEY`
- `REALESTATEAPI_BASE_URL=https://api.realestateapi.com`
- `REALESTATEAPI_REQUEST_TIMEOUT_SECONDS=30`
- `UNDERWRITING_ACTIVE_METHODOLOGY_VERSION=v3`
- `UNDERWRITING_V3_SHADOW_ENABLED=false`
- `UNDERWRITING_REALESTATEAPI_COMPS_MODE=candidate`
- `UNDERWRITING_DEALMACHINE_COMPS_MODE=disabled`
- `UNDERWRITING_AI_COMP_ANALYST_MODE=draft`
- optional `ATTOM_API_KEY` placeholder

V3 is the single live Stonegate Valuation method. V2.2 is retained only for historical reads and an
engineering rollback; staff do not choose between versions. Keep shadow mode disabled in normal
operation.

Fresh analysis may use these RentCast endpoints:

- `/properties` and `/avm/value` for subject identity, recorded sales, and the benchmark AVM
- `/avm/rent/long-term` for rental exit support
- `/listings/sale` for active asking-price context only
- `/markets` for ZIP-level sale-listing context only

The active-listing and market-statistics calls consume provider requests and are cached with the
analysis. **Update Stonegate valuation**, repair changes, and comp review reuse that same-address
snapshot without a paid retry. **Refresh market evidence (may use credits)** explicitly replaces
the snapshot. Neither endpoint supplies closed-sale evidence to ARV or offer math.

### Automatic Property Intelligence

When a lead has a usable street address and city, the worker automatically runs the same V3
research pipeline used by Stonegate Valuation and saves an immutable, property-level snapshot. The
snapshot centralizes normalized property facts, screened comparable sales, calculated valuation
evidence, provider provenance, conflicts, market context, confidence, and freshness. Leads that
resolve to the same normalized property reuse the current snapshot and its cached market analysis
instead of buying the same provider evidence again. A normal snapshot remains fresh for the
configured number of days; **Refresh research** intentionally requests current evidence and may
use provider credits.

The API and worker must receive the same RentCast, RealEstateAPI, and intelligence variables. A
fresh analysis makes one exact-address RealEstateAPI Property Detail request with standard comps
included, then reuses that response for the property profile, secondary comp evidence, provider
benchmark, and any licensed listing image. The complete sanitized property record is saved inside
the immutable snapshot so the UI and AI runtime do not re-buy it.

The image order is the latest Stonegate field-inspection photo, a RealEstateAPI listing image when
the response directly includes an approved `imagecdn.realty.dev` URL, then a clear no-photo
placeholder. Stonegate does not use Street View, satellite, aerial, or scraped images. The browser
retrieves provider media through Stonegate's authenticated API and never receives the API key.

Existing saved market analyses are lazily backfilled into property snapshots by the worker without
a provider call. Automatic research does not move the seller into Underwriting, approve a value,
or make an offer. It prepares evidence for staff and AI; consequential valuation and offer controls
remain human-operated.

Set `OPENAI_WEB_SEARCH_ENABLED=true` to allow the underwriting research agent to supplement thin
RentCast results. It uses medium-context live search with a five-call ceiling, stores consulted
citations, and never lets the model set ARV or an offer directly. Use
`OPENAI_REQUEST_TIMEOUT_SECONDS=75` so the bounded multi-search request has time to finish.

Stonegate's configured RealEstateAPI mode is `candidate`: unique closed sales may enter the
candidate pool, but every sale still passes the same deterministic screen, confidence rules, and
human review as RentCast evidence. `shadow` remains available for diagnostics and records overlap,
conflicts, benchmark, estimated credits, and latency without affecting ARV. Exact address matching
is fail-closed. The provider audit distinguishes returned, usable, overlapping, net-new, duplicate,
ineligible, dropped, and conflicting sales. Reused snapshots show zero current-run credits while
preserving original source cost and latency. RealEstateAPI and RentCast estimates remain external
benchmarks; Stonegate's screened comp math remains the valuation conclusion.

Production enables `UNDERWRITING_AI_COMP_ANALYST_MODE=draft`. With `AI_ENABLED=true` and a valid
OpenAI key, the draft analyst and persistent Comp Copilot can organize comp review work and explain
deterministic evidence. Without those prerequisites, Comp Copilot remains available with bounded
deterministic guidance. The strict contract excludes ARV, offers, value ranges, weights, dollar
adjustments, and approval authority.

Each Copilot thread belongs to one immutable market-analysis ID. It stores messages, citations,
suggested navigation actions, model use, and token counts. It uses saved analysis and structured
inspection metadata and does not make a RentCast or RealEstateAPI request. Apply migration `0096`
before deploying the web application that exposes this workspace.

Acceptance:

1. Analyze several known Georgia addresses.
2. Confirm subject identity before relying on returned records.
3. Review selected and excluded comparables.
4. Confirm active listings and ZIP statistics appear only under supporting context.
5. Add one source-verified manual closed sale, rerun, then confirm its source remains visible.
6. Confirm investor and client PDFs.
7. Record provider failures and verified outcomes.

A RentCast 404 is a data-coverage result, not proof that the Stonegate API is down. The
underwriting workflow can continue from verified subject facts and recorded sales when permitted
by the method.

## Resend Operational Email

### Architecture

- Send with the Resend API.
- Receive through Resend Receiving.
- Use the `stonegatehb.com` domain.
- Keep aliases, grants, templates, signatures, routing, permissions, and conversation history in
  Stonegate.

### Variables

- `EMAIL_ENABLED=true`
- `EMAIL_PROVIDER=resend`
- `EMAIL_SYNC_ENABLED=true`
- `EMAIL_SYNC_POLL_SECONDS`
- `EMAIL_MAX_ATTACHMENT_BYTES`
- `EMAIL_WEB_APP_BASE_URL=https://www.stonegatehb.com`
- `RESEND_API_KEY`
- `RESEND_WEBHOOK_SECRET`
- `RESEND_SENDING_DOMAIN=stonegatehb.com`
- `RESEND_RECEIVING_DOMAIN=stonegatehb.com`
- `RESEND_DEFAULT_FROM_EMAIL`
- `RESEND_WEBHOOK_BASE_URL=https://api.stonegatehb.com`
- `RESEND_EVENT_MAX_ATTEMPTS`
- `RESEND_EVENT_RETRY_BASE_SECONDS`
- `RESEND_EVENT_RETRY_MAX_SECONDS`
- `RESEND_EVENT_PROCESSING_LEASE_SECONDS`

Google OAuth variables are superseded and should remain unused.

Resend webhook and recovery records are claimed under a processing lease. Temporary failures use
capped exponential retry. Every claim has a UUID fence, so an expired lease can be reclaimed without
allowing the stale worker to overwrite the new attempt. For inbound mail, the validated route is
committed before later attachment or provider work; a retry reuses that exact destination. Outbound
lifecycle webhooks that arrive before the matching CRM send record exists retry within the same
bounded budget. Once `RESEND_EVENT_MAX_ATTEMPTS` is reached, the event becomes `dead_letter` and
requires manager review instead of being automatically resurrected. The attachment byte limit is
enforced against provider metadata, HTTP content length, and streamed content so an oversized
response is not fully buffered in memory.

### DNS

Resend supplies the exact SPF, DKIM, receiving/MX, and optional verification records. The DNS owner
must add the records exactly and wait for Resend to show the domain as verified. Add a DMARC record
and monitor deliverability before tightening policy.

### Webhook

Endpoint:

```text
https://api.stonegatehb.com/api/v1/webhooks/resend
```

Subscribe to received and outbound lifecycle events supported by the Resend account. Copy the
matching signing secret to `RESEND_WEBHOOK_SECRET`.

### Stonegate Setup

In Inbox owner administration:

1. Create approved aliases such as `austin@`, `offers@`, `buyers@`, and `accounting@`.
2. Choose personal, team, general, or restricted visibility.
3. Grant authorized senders.
4. Add signatures and templates.
5. Resolve or assign unmatched inbound routing exceptions. A restricted alias can be assigned only
   to a restricted-visibility conversation; automatic and manual routing both enforce this rule.
6. Use **Failed events** only after correcting a terminal failure. This tab is manager-only, requires
   a reason to requeue, and writes an audit event.

### Acceptance

Test each approved alias:

1. New outbound email
2. CC and BCC
3. text and attachment delivery
4. recipient reply into the same thread
5. correct personal or team routing
6. unread and Needs Reply state
7. first-response and next-response timer
8. bounce or failure visibility
9. duplicate webhook handling
10. unauthorized sender and restricted mailbox denial
11. one temporary provider-processing failure that retries after its delay
12. one abandoned processing claim that becomes eligible after the lease expires while the stale
    claim can no longer finalize or overwrite it
13. declared-size and streamed oversize attachments that fail safely
14. one poison event that reaches `dead_letter` without blocking later valid mail and remains
    available in manager-only **Failed events**
15. one reason-required requeue after the underlying cause is corrected, including its audit event
16. one early lifecycle webhook that retries until its outbound CRM record exists
17. one inbound message whose validated route survives a later attachment/provider failure
18. automatic and manual denial of a standard-visibility destination for a restricted alias

These checks do not complete external mailbox acceptance by themselves. Confirm real sender/reply
behavior and either activate malware scanning or approve a documented limited safe-attachment
procedure before relying on Resend as the only operating mailbox.

Messages reaching spam should be evaluated through SPF, DKIM, DMARC, domain reputation, content,
and recipient engagement. A successful API response alone does not establish inbox placement.

## Twilio SMS

### Department Numbers

- The approved seller-inquiry A2P registration belongs to the shared acquisitions number. A
  Messaging Service is optional when Stonegate sends directly from that number.
- A future dispositions number needs its own accurate buyer/investor messaging registration when
  its use differs from the seller-inquiry campaign.
- BatchDialer owns VA cold-call numbers; those numbers are not added to Stonegate's Twilio
  Messaging Service.

### Separation Rule

Stonegate must use its own:

- A2P brand and campaign
- Messaging Service, when used
- 10DLC number
- campaign description and samples
- public consent evidence
- webhook destinations

Do not share another business's campaign or number.

### Variables

- `TWILIO_SMS_ENABLED`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_SMS_FROM_NUMBER` (acquisitions/default rollout fallback; department lines are stored in
  **Settings > Communications**)
- `TWILIO_WEBHOOK_BASE_URL=https://api.stonegatehb.com`
- `TWILIO_VALIDATE_WEBHOOK_SIGNATURES=true`
- SMS timezone and contact-hour variables

`TWILIO_MESSAGING_SERVICE_SID` is optional. Stonegate's direct-number setup sends from
`TWILIO_SMS_FROM_NUMBER` and does not require a Messaging Service.

The Account SID, sending credential, direct sender number, and webhook base URL must be present on
both **oakwell-api** and **oakwell-worker**. The API validates callbacks; the worker performs staff
lead-alert sends.

The Auth Token is not the Account SID. Twilio displays them as separate values in the account
console.

### Webhooks

Each phone number's **A message comes in** webhook:

```text
POST https://api.stonegatehb.com/api/v1/webhooks/twilio/messaging/incoming
```

Delivery status callback supplied automatically by Stonegate on each outbound message:

```text
POST https://api.stonegatehb.com/api/v1/webhooks/twilio/messaging/status
```

### A2P Evidence

The campaign must reference the current branded public URLs:

- `https://www.stonegatehb.com/get-a-cash-offer`
- `https://www.stonegatehb.com/privacy-policy`
- `https://www.stonegatehb.com/terms`

The consent description must match the actual separate unchecked checkbox and actual message use.
Do not claim keyword opt-in unless it is truly supported. Do not describe purchased-list cold SMS
if the campaign is for consented seller inquiries.

### Acceptance

After campaign approval and direct-number configuration:

1. Send a controlled outbound SMS.
2. Confirm sent, delivered, and failed states.
3. Reply and confirm the same conversation.
4. Test STOP, blocked send, START, and HELP behavior.
5. Replay callbacks and confirm no duplicate timeline records.
6. Confirm staff assignments do not break the seller thread.

## Twilio Voice

### Variables

- `TWILIO_VOICE_ENABLED`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_WEBHOOK_BASE_URL`
- token TTL, ring timeout, timezone, and calling-hour variables
- `TWILIO_VOICE_RECORDING_ENABLED`
- `TWILIO_VOICE_RECORDING_DISCLOSURE`
- `CALL_RECORDING_RETENTION_DAYS`
- `CALL_TRANSCRIPTION_ENABLED`
- `OPENAI_TRANSCRIPTION_MODEL`
- `CALL_TRANSCRIPTION_POLL_SECONDS`
- `CALL_TRANSCRIPTION_MAX_ATTEMPTS`
- `AI_ENABLED` and `OPENAI_API_KEY`

The Account SID identifies the Twilio account. The Auth Token validates provider requests. API
keys and a TwiML App are not required for Stonegate's cellphone-forwarding mode.
`TWILIO_VOICE_FROM_NUMBER` is optional and only supports initial line bootstrap; the active line
records under **Settings > Communications** control caller ID.
The disclosure is optional. Stonegate's Owner-selected Georgia-only one-party mode leaves it unset
and records `one_party_consent` without playing an announcement. The operating/legal policy still
requires documented production acceptance. Set the variable when Stonegate chooses or is required
to announce recording. Recording-consent rules can differ outside Georgia, so review the operating
policy before calling into other states.

### Webhooks

- inbound Voice instructions: `/api/v1/webhooks/twilio/voice/incoming`
- call status: `/api/v1/webhooks/twilio/voice/status`
- dial result: `/api/v1/webhooks/twilio/voice/dial-result`
- recording callback: `/api/v1/webhooks/twilio/voice/recording`
- disclosure route: `/api/v1/webhooks/twilio/voice/disclosure`

All paths use `https://api.stonegatehb.com` as the base.

### Acceptance

1. Browser device registers.
2. Outbound call uses the Stonegate number.
3. Inbound call routes to the intended staff identity.
4. No-answer and missed-call task behavior work.
5. Status callbacks attach to the correct conversation.
6. Confirm and document acceptance of the Owner-selected recording-authorization and retention
   mode. In the Georgia-only one-party mode, the spoken disclosure may intentionally remain blank
   while the authorization state is still recorded.
7. When recording is enabled, confirm the authorization state, private recording, speaker-aware
   transcript, structured AI draft, automatic empty-field CRM population, correction, rejection,
   internal seller note/activity entry, follow-up task and date, audit history, failure visibility,
   retention date, and early deletion.
8. **Settings > Integrations** shows **Call recording and AI notes** as configured. A missing Voice,
   recording, transcription, AI, or OpenAI setting is a launch blocker; an intentionally blank
   disclosure is not.
9. Force one temporary transcription or note-generation failure. Confirm the worker waits for the
   exponential retry delay rather than immediately repeating the provider charge.
10. In a controlled test, exhaust `CALL_TRANSCRIPTION_MAX_ATTEMPTS`, confirm Inbox displays the
    stopped state, then select **Retry call intelligence** and verify the audited retry succeeds on
    the same call record.

## SignWell

### Variables

- `ESIGN_PROVIDER=signwell` when active
- `ESIGN_API_KEY`
- `ESIGN_BASE_URL=https://www.signwell.com/api/v1`
- `ESIGN_SIGNWELL_WEBHOOK_ID`
- `ESIGN_WEBHOOK_CALLBACK_URL=https://api.stonegatehb.com/api/v1/webhooks/esign/signwell`
- `ESIGN_TEST_MODE`
- `ESIGN_REQUEST_TIMEOUT_SECONDS`

### Provider Setup

1. Finish SignWell account onboarding.
2. Upload and configure the approved purchase-agreement template.
3. Use placeholder recipients `Seller` and `Document Sender`.
4. Place seller and company fields carefully.
5. Store the SignWell template ID on the matching Stonegate contract template.
6. Create the Stonegate webhook in SignWell.
7. Enter the API key and webhook information in Render.

### Acceptance

1. Connect SignWell from Stonegate integration status.
2. Create a contract package from a test transaction.
3. Verify all populated facts and unresolved gaps.
4. Send in SignWell test mode.
5. Complete remote signing.
6. Confirm event reconciliation and completed-document storage.
7. Repeat from the field appointment on an iPad.
8. Confirm unauthorized roles cannot send or download restricted documents.
9. Configure two isolated Stonegate organizations in a controlled test and confirm an
   organization-specific webhook credential cannot update another organization's envelope.
10. Replay duplicate, stale, and out-of-order events and confirm they remain auditable without
    regressing a later or terminal envelope state. If a legacy global webhook credential remains,
    confirm it fails closed once provider envelopes span organizations.
11. Confirm production reconciliation compares the document ID, intended recipients/signers,
    status, and completed PDF with the SignWell API. The webhook HMAC used by this integration signs
    event type/time, not the full document/signer/body payload, so organization binding alone is not
    sufficient within one organization.
12. Confirm Stonegate creates an unsent provider draft first, persists the SignWell document ID,
    and then sends that exact draft. Simulate a timeout at both phases and verify no second provider
    document is created automatically.
13. Confirm a saved `draft` envelope shows **Resume saved draft** in the transaction workspace,
    while `sending` or `send_uncertain` requires provider reconciliation before any retry.
14. Simulate a crash after SignWell creates an unsent draft but before Stonegate saves its ID. In
    **Signature requests**, use **Attach verified draft** and confirm Stonegate accepts only the exact
    draft whose metadata, test mode, and recipients match the transaction/package reservation.
15. Simulate a create timeout where the SignWell account contains no matching document. After at
    least five minutes and an account search, use **Abandon empty intent**, enter a meaningful audit
    reason, and confirm the package returns to `approved` without deleting the failed envelope.
16. Confirm a decline, expiration, cancellation, or provider error releases its package exactly once.
    Re-send the package, replay/reconcile the old terminal event, and confirm it cannot reset the new
    delivery.
17. Confirm offer-plan, concession, price-presentation, and seller-agreement changes are blocked while
    an approved purchase agreement is being sent or remains signable. For a manually delivered
    agreement, notify every recipient that it is withdrawn, then use **Withdraw sent package** with a
    meaningful reason before recording new authority.
18. Reconcile `sent`, then deliver an older-timestamp `completed` event and confirm completion still
    advances. With two signers, deliver signed/viewed events out of timestamp order and confirm each
    recipient progresses while envelope state and timestamps never regress.

Use `GEORGIA_CONTRACT_PACKET.md` and `SIGNWELL_COUNSEL_BRIEF.md` for document-content boundaries.

## Document Storage

Variables:

- `DOCUMENT_STORAGE_PROVIDER=database` or `s3`
- endpoint, bucket, access-key, secret-key, and region values
- download-link TTL
- retention days
- malware scanner settings

Database storage supports the product now. S3-compatible private storage is recommended before
large-scale production evidence. Cloudflare R2 is a compatible low-cost option.

If malware scanning is required, configure ClamAV and set the required flag only after a controlled
upload test passes.

## DealMachine Buyer Data

Variables:

- `BUYER_DATA_PROVIDER=dealmachine` when activated
- `DEALMACHINE_API_KEY`
- `DEALMACHINE_BASE_URL`
- request timeout
- maximum discovery results

This legacy integration is optional and should remain `BUYER_DATA_PROVIDER=disabled` after the
subscription is cancelled. If Stonegate deliberately reactivates it, create the API key from the
DealMachine developer settings, store it only in Render, set the provider to `dealmachine`, and
redeploy. The Buyer
workspace readiness check must show the expected paid plan and available credits. Every search
first uses DealMachine's zero-credit estimate mode and requires explicit confirmation of the
current maximum credit use. Acceptance must compare estimated and actual credits and test provider
result quality, multi-select field mapping, DNC-safe contact suggestion, scoring, candidate review,
import, duplicates, and cost before recurring dependence.

## Marketing Conversion Delivery

Variables include:

- `MARKETING_CONVERSION_MODE`
- conversion window, retry, and website values
- Google Data Manager client, refresh token, account, and conversion action values
- Meta access token, pixel ID, API version, and optional test event code

The direct Meta integration combines the browser Pixel with server-side Conversions API events:

- The web service uses `NEXT_PUBLIC_META_PIXEL_ID`; this ID is public by design.
- The API and worker use the same value in `META_PIXEL_ID`.
- Only the API and worker receive `META_CONVERSIONS_ACCESS_TOKEN`; never expose it as a
  `NEXT_PUBLIC_` variable.
- `META_TEST_EVENT_CODE` is temporary and should be removed after Events Manager acceptance.
- `MARKETING_CONVERSION_MODE=disabled` stores events without delivery. Use `live` only after the
  Pixel ID and access token are present on both the API and worker services.

Implemented events are `PageView` from the Pixel, deduplicated browser/server `ViewContent` and
`Lead`, and server-side `QualifiedLead` and `Schedule` from later CRM outcomes. Browser and server
copies of `ViewContent` and `Lead` use the same event name and event ID. Server delivery includes
the source URL and user agent; Lead also uses hashed email and external ID plus IP, `fbc`, and `fbp`
when available. The phone hash is deliberately withheld from Meta because the current mobile
privacy promise excludes sharing mobile information for third-party marketing.

Acceptance sequence:

1. Generate the Conversions API access token in Meta Events Manager and store it in Render.
2. Add the Pixel ID to the web, API, and worker variables described above.
3. Add Meta's Test Events code to the API and worker, switch delivery to `live`, and redeploy.
4. Visit a public page and submit one controlled seller test lead.
5. In Test Events, confirm browser and server `ViewContent` and `Lead` arrive and deduplicate.
6. Confirm Event Match Quality includes the expected non-phone match keys.
7. Remove the test event code, redeploy, and monitor deduplication, freshness, coverage, and match
   quality during the first campaigns.

Meta rejects events older than seven days; the worker expires those instead of retrying an invalid
request. Delivery remains one event per request so one invalid event cannot reject unrelated
events.

## Website And Zapier Lead Intake Staff Alerts

The public **Get a Cash Offer** form creates a Stonegate lead directly. It requires the property
street, city, state, seller timeline, and contact information before submission. Its browser
`Lead` event and matching server conversion use the same event ID for Meta deduplication.

Facebook instant forms are separate from the Pixel and Conversions API. The Pixel reports activity
back to Meta; Zapier moves each submitted Facebook instant form into Stonegate as a real CRM lead.
Stonegate does not use a Meta developer app, Graph access token, or direct Meta webhook for lead
intake.

Processing variables needed on both **oakwell-api** and **oakwell-worker**:

- `ZAPIER_FACEBOOK_LEADS_ENABLED`
- `ZAPIER_FACEBOOK_PAGE_ID`
- `ZAPIER_FACEBOOK_LEADS_MAX_PAYLOAD_BYTES`
- `FACEBOOK_LEAD_INTAKE_MAX_ATTEMPTS`
- `FACEBOOK_LEAD_INTAKE_RETRY_BASE_SECONDS`
- `FACEBOOK_ADDRESS_ENRICHMENT_MAX_ATTEMPTS`
- `FACEBOOK_ADDRESS_ENRICHMENT_RETRY_BASE_SECONDS`
- `STAFF_LEAD_ALERT_SMS_MODE` plus its retry values

Ingress safety variables needed on **oakwell-api**:

- `ZAPIER_FACEBOOK_ALLOWED_FORM_IDS`, as a comma-separated list of production form IDs
- `ZAPIER_FACEBOOK_LEADS_BURST_LIMIT`
- `ZAPIER_FACEBOOK_LEADS_BURST_WINDOW_SECONDS`
- `ZAPIER_FACEBOOK_LEADS_DAILY_ACCEPT_LIMIT`

The burst circuit is an in-process limit. The rolling 24-hour accepted-lead limit is counted from
durable database events. A duplicate provider lead ID is recognized before the daily circuit so a
legitimate Zap replay does not consume another accepted-lead slot.

The worker also needs `PROPERTY_DATA_PROVIDER=rentcast` and `RENTCAST_API_KEY` for automatic
address enrichment. It needs the complete Twilio SMS configuration when staff alerts are live.
Website and Facebook intake both create source-tagged alerts for every active user who has a valid
cellphone and **Text new leads** enabled. The worker also recovers a recent website submission when
a recipient was not alert-ready at intake, without sending duplicates.

The endpoint is:

```text
https://api.stonegatehb.com/api/v1/webhooks/zapier/facebook-leads
```

### Zapier Connection And Trigger

1. In Meta Page settings or Business Settings, grant Zapier CRM/Leads Access to the Stonegate Page.
2. In Zapier, add the **Facebook Lead Ads** connection using the Facebook account that controls the
   Page. The integration requires a paid Zapier plan.
3. Create one Zap with **Facebook Lead Ads > New Lead** as the instant trigger.
4. Select the Stonegate Page and the production instant form. Use a separate Zap for another form
   unless its output fields are identical and intentionally mapped.
5. Generate a Facebook test lead and confirm Zapier loads all required trigger fields.

### One Stonegate Action

Add **Webhooks by Zapier > Custom Request** as the Zap's only action:

- Method: `POST`
- URL: `https://api.stonegatehb.com/api/v1/webhooks/zapier/facebook-leads`
- Data Pass-Through: `false`
- Unflatten: `false`
- Header `Content-Type`: `application/json`

Use a JSON body with Zapier field tokens in place of the example labels:

```json
{
  "provider_lead_id": "{{Lead ID}}",
  "page_id": "{{Page ID or the configured Stonegate Page ID}}",
  "form_id": "{{Form ID}}",
  "form_name": "{{Form Name}}",
  "created_time": "{{Created Time}}",
  "ad_id": "{{Ad ID}}",
  "ad_name": "{{Ad Name}}",
  "adset_id": "{{Ad Set ID}}",
  "adset_name": "{{Ad Set Name}}",
  "campaign_id": "{{Campaign ID}}",
  "campaign_name": "{{Campaign Name}}",
  "platform": "{{Platform}}",
  "is_organic": false,
  "full_name": "{{Full Name}}",
  "email": "{{Email}}",
  "phone_number": "{{Phone Number}}",
  "property_address": "{{Property Address answer}}",
  "property_city": "{{Property City answer}}",
  "property_state": "{{Property State answer}}",
  "property_zip_code": "{{Property ZIP answer}}",
  "property_type": "{{Property Type answer}}",
  "reason_for_selling": "{{Reason for Selling answer}}",
  "desired_timeline": "{{Selling Timeline answer}}",
  "property_condition": "{{Property Condition answer}}",
  "occupancy_status": "{{Occupancy answer}}",
  "asking_price": "{{Asking Price answer}}",
  "mortgage_balance": "{{Mortgage Balance answer}}",
  "comments": "{{Comments answer}}"
}
```

`provider_lead_id` and `page_id` are required and must be the numeric Facebook values. At least
one of `email` or `phone_number` is required for usable CRM intake. Remove optional JSON properties
that are not present on the form rather than inserting descriptive placeholder text. Custom
question keys may also be sent as flat scalar fields using letters, numbers, spaces, periods,
underscores, or hyphens; Stonegate preserves them even when they are not part of CRM qualification.

For Georgia-only forms, map the seller's street answer to `property_address`, city to
`property_city`, and enter `GA` as the fixed `property_state`. Omit `property_zip_code` when the
form does not ask for it. After the CRM record and staff alert are queued, the worker uses RentCast
property-record data to fill a missing ZIP and county only when the street, city, and state match
confidently. Ambiguous results remain unchanged and are marked for review. This lookup does not use
RentCast's AVM value range in comp or offer math.

### Activation And Acceptance

1. Store the numeric Page ID on both Render services. On the API, store the exact production form
   IDs in `ZAPIER_FACEBOOK_ALLOWED_FORM_IDS`. Leave
   `ZAPIER_FACEBOOK_LEADS_ENABLED=false` until the Zap is completely mapped.
2. Set `ZAPIER_FACEBOOK_LEADS_ENABLED=true` on the API and worker, redeploy, and immediately run the
   Zapier action test.
3. Confirm the action returns `received: true` and `accepted: 1`.
4. Confirm exactly one CRM lead, seller conversation, five-minute speed-to-lead task, inbound case,
   notification, and AI intake job appear.
5. Re-test the same Zapier sample. It must return `accepted: 0` and create no duplicate records.
6. Confirm source is `facebook_lead_ads`, campaign/ad attribution is present, ingestion method is
   `zapier`, and the original payload is auditable. A submission without email and phone stops in
   `needs_review` instead of creating an unusable lead.
7. For a street-and-city submission without ZIP, confirm the property gains a five-digit ZIP,
   county, normalized address, provider provenance, and `provider_confirmed` status. An ambiguous
   provider response must retain the seller's original values and require review.
8. Publish the Zap only after the controlled test passes. Monitor Zap History and Stonegate
   Marketing readiness during the first campaign.

Production startup and `/ready` fail closed when Zapier intake is enabled without at least one
configured form ID. Populate `ZAPIER_FACEBOOK_ALLOWED_FORM_IDS` before the enabling deploy.

The endpoint is intentionally secretless, publicly reachable, and does not authenticate requests.
It rejects the wrong Page or an unapproved configured form, limits request size and bursts, stops at
the rolling daily acceptance circuit, and returns quickly after durable storage. The Page and form
values are supplied by the caller, so these controls constrain abuse and cost but do not
cryptographically prove that a request came from Meta or Zapier. Monitor Zap History, accepted form
IDs, provider-event volume, and daily-circuit responses during every live campaign.

The Zapier burst limiter follows the same production address rule as other public writes: it uses
the edge-owned `CF-Connecting-IP`, ignores caller `X-Forwarded-For`, and hard-bounds process-local
keys. Keep the Render origin behind the trusted Cloudflare path and add distributed edge limiting
before higher volume or multiple API instances.

The worker performs CRM intake and retries temporary internal failures with backoff. Facebook lead
IDs are unique per organization, so Zapier replays are safe. If a Zap fails, correct the mapping and
replay the original run; do not manually invent another provider lead ID.

Facebook form submission authorizes Stonegate to respond by the channels stated on that form. It
does **not** create seller SMS marketing consent. Stonegate records phone and email contact basis
from the instant form while leaving `sms_consent=false`; any seller texting workflow still requires
its own approved consent evidence.

Staff alerts are an internal operational message, not a text to the seller. For each employee who
should receive them:

1. Open **Settings > Communications > Staff ring settings**.
2. Enter the employee's personal cellphone in `+1...` format.
3. Select **Text new leads** and save.
4. Leave `STAFF_LEAD_ALERT_SMS_MODE=disabled` until Stonegate confirms its Twilio registration and
   direct sender/campaign or optional Messaging Service covers this internal notification use case,
   and each employee has agreed to receive the alerts.
5. Run a non-production `simulate` test, then set the API and worker to `live`, redeploy, and submit
   one controlled Zapier test lead.
6. Confirm each opted-in employee receives one minimal alert and the delivery callback becomes
   `delivered`. The alert contains the seller name, market, and a Stonegate lead link, but excludes
   the seller's phone number and street address.

**Text inbound messages** is a separate employee preference that uses the same live Twilio staff
alert delivery mode. For each seller or buyer text, Stonegate sends one internal alert to the first
eligible responsible employee: the conversation owner, the company line's primary/team owner, the
line fallback, then an organization owner. The alert identifies the contact and links to Inbox but
does not copy the customer's message onto a personal phone. A previously unknown number creates a
reviewable seller lead on Acquisitions or buyer thread on Dispositions; STOP, START, HELP, and
messages from configured staff cellphones do not create records or notification loops.

Production forbids staff-alert `simulate` mode. Disabling alerts never disables Meta lead
ingestion. When the use case is approved and the controlled delivery test is ready,
`STAFF_LEAD_ALERT_SMS_MODE=live` must be present on both the API and worker.

At worker startup, inspect `worker_started` and `staff_lead_alert_readiness_failed`. They report the
delivery mode, missing Twilio configuration, active opted-in employees, valid recipients, missing
cellphones, and invalid cellphones without exposing full phone numbers. For each processed Meta
lead, `staff_lead_alert_queue_evaluated` records whether alerts were created, already existed, or
could not be queued. A zero-recipient result is also written to the lead activity timeline, the
audit log, and an in-app notification for the assigned owner, so the failure is not silent.

The worker checks the previous 24 hours for processed Meta leads that have no staff-alert rows. If
an active opted-in employee now has a valid cellphone, it creates the missing alert exactly once
and logs `staff_lead_alert_missing_rows_recovered`. Delivery acceptance, retry, exhaustion,
configuration blocking, and Twilio callback status each have their own structured log event. An
administrator with `communications:manage_voice_lines` can also use the audited recovery endpoint
`POST /api/v1/voice/staff-lead-alerts/{meta_lead_event_id}/requeue` after correcting the cause. A
meaningful reason is required, current employee opt-in is rechecked, and queued, sent, or delivered
alerts cannot be resent through that endpoint.

Inbound-message readiness is reported independently as
`staff_inbound_message_alert_readiness_failed`; queue decisions are logged as
`staff_inbound_sms_alert_queue_evaluated`. Correct the **Text inbound messages** preference or
cellphone when that route has no eligible recipient.

If a worker log contains `meta_lead_ads` for a lead but no `staff_lead_alerts`, first find the
matching `staff_lead_alert_queue_evaluated` event. If `ready_recipients=0`, correct the employee's
cellphone or **Text new leads** preference. If an alert exists but delivery is blocked,
correct the listed worker configuration. A Twilio Console message appears only after
`staff_lead_alert_delivery_accepted`; its absence before that event is expected.

## Public Trust Proof Acceptance

The trust-and-proof system is internal and does not require another provider account or secret.
Authorized Marketing users manage it under **OS > Marketing > Public Trust Governance**.

For the first real production record:

1. Create a draft from a genuine review, seller story, completed purchase, or measured statistic.
2. Add the public wording, source URL or internal evidence reference, permission evidence, and any
   required relationship disclosure.
3. Submit the record for review and publish it only after the evidence and wording are confirmed.
4. Open the public homepage and confirm the record appears within five minutes with the correct
   attribution, source link, disclosure, and outcome caveat.
5. Unpublish the record and confirm it disappears within five minutes, then republish it if the
   acceptance check passed.
6. Keep source evidence and permission records available for later correction or retirement.

Never enter sample testimonials or production-looking placeholders for acceptance. Stonegate
does not publish self-serving Review or AggregateRating structured data.

## Conversion Experiment Acceptance

The PC7 experiment system is first-party and requires no external account or credential.
Authorized users operate it under **OS > Marketing > Conversion experiments**.

Before the first live test:

1. Record the existing homepage funnel baseline for at least one normal reporting period.
2. Create a draft using the current CTA as Control and one wording-only Test CTA.
3. Choose a primary business outcome and write the stopping and decision rule before launch.
4. Start the experiment and open the public homepage in a private browser.
5. Confirm one approved CTA appears, the complete cash-offer journey succeeds, and the submitted
   lead is created normally.
6. Confirm Marketing shows the assigned session under exactly one version with the correct device
   category and linked lead.
7. Pause and resume once to verify active runtime stops while paused and no evidence is deleted.
8. Leave the test running only after this acceptance passes.

Do not use production seller submissions as synthetic acceptance records. Do not run overlapping
homepage CTA tests or change only one version through an unrelated deployment.

## Operations And Recovery

### Checks

```bash
npm run lint:api
npm run typecheck:api
npm run test:api
npm run lint:web
npm run typecheck:web
npm run audit:ia
npm run audit:underwriting
npm run build:web

(cd apps/api && uv run pip-audit --strict --desc=off --progress-spinner=off)
(cd apps/web && npm audit --workspaces=false --audit-level=high)
```

### Backup

Populate `DATABASE_URL` and `BACKUP_DIR` through the approved secret-injection mechanism without
typing the database URL into shell history. Then run:

```bash
npm run db:backup
```

### Restore Verification

Populate `RESTORE_DATABASE_URL` through the same history-safe mechanism and set
`ALLOW_RESTORE_TEST=true`. Then run:

```bash
npm run db:restore-verify -- .backups/stonegate-TIMESTAMP.dump
```

Never point restore verification at the production database.

### Smoke Test

```bash
API_BASE_URL='https://api.stonegatehb.com' \
WEB_BASE_URL='https://www.stonegatehb.com' \
npm run ops:smoke
```

### Deployment Acceptance

After a production deployment:

1. Render build and startup succeed.
2. migrations finish once without error.
3. `/health` and `/ready` pass. Confirm `/ready` remains ready through one normal longer provider
   operation, reports its current operation, and would become `stalled` only after the configured
   600-second production progress threshold.
4. public homepage, cash-offer form, privacy, and terms load.
5. Clerk sign-in reaches the correct OS navigation.
6. one protected API request succeeds.
7. worker heartbeat is fresh.
8. the changed workflow receives a focused end-to-end test.

## Setup Work Still Required

| Work | Owner | Trigger |
| --- | --- | --- |
| Resend controlled production acceptance, including Failed events recovery | Stonegate owner/partner | Now |
| Search Console and service-area Business Profile acceptance | Stonegate owner/marketing | Before local search launch |
| First genuine public proof acceptance | Stonegate owner/marketing | After a documented review or outcome exists |
| First controlled homepage experiment acceptance | Stonegate owner/marketing | After a stable production baseline exists |
| Approved public team content and photography | Stonegate owner/marketing | Before PC8 production acceptance |
| Confirm direct acquisitions sender and signed Twilio callbacks | Stonegate owner | Twilio Console |
| Dedicated Twilio SMS, Voice, recording, transcription, and AI-note acceptance | Owner and developer | Before launch |
| SignWell activation and end-to-end signing | Owner and transaction staff | Before live contracts |
| RealEstateAPI production connection and acceptance | Owner and acquisitions | Passed; monitor credits and evidence quality |
| CPA accounting acceptance | Owner, finance, CPA | Before relying on first closed period |
| Underwriting calibration | Owner/acquisitions | As real outcomes accumulate |
| Google offline conversion activation; ongoing Meta monitoring | Owner/marketing | When the Google ad account is ready |
| Production restore drill | Owner/developer | Before broad launch |
| Sentry and alert webhook | Owner/developer | Optional |
| Real production Facebook form through CRM, research, and staff-alert acceptance | Owner/developer | Before paid Meta traffic scales |
| Secretless Zapier allowlist, circuits, Zap History, and volume-monitoring review | Owner/developer | Every live Meta campaign |
| Controlled manual buyer outreach or implemented live disposition delivery | Owner/dispositions | Before marketing the first contracted deal |
| Malware-scanning and distributed edge-rate-limit decision; restrict origin/header trust | Owner/developer | Before broad scale |

## Change Procedure

When adding or changing a provider:

1. Update code and `.env.example`.
2. Update `render.yaml` without putting secrets in Git.
3. Update this reference.
4. Update `SYSTEM_MAP.md` status.
5. Update `FINISHING_ROADMAP.md`.
6. Add or update automated tests.
7. Deploy with the provider disabled where possible.
8. Enter secrets in Render.
9. Perform controlled acceptance.
10. Change status from configured to active only after evidence exists.
