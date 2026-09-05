# Stonegate Setup Reference

Last verified against the repository: September 4, 2026

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
| Buyer data | DealMachine | Governed House buyer discovery enabled in the production API manifest; controlled real-deal acceptance remains |
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

`REALESTATEAPI_API_KEY` also enables the public seller form's full-address suggestions through the
provider's free AutoComplete endpoint. The API key remains server-side. If it is absent, rate
limited, or temporarily unavailable, the public endpoint returns no suggestions and the seller can
continue through manual street, city, state, and ZIP entry.

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
19. one controlled House disposition email using an active approved alias, the exact approved
    outreach copy, and its exact frozen investor PDF; confirm the revision retains the package's
    **Preliminary** or approved state, provider state, and the buyer's reply in the same Buyer Inbox
    conversation without a duplicate send

These checks do not complete external mailbox acceptance by themselves. Confirm real sender/reply
behavior and either activate malware scanning or approve a documented limited safe-attachment
procedure before relying on Resend as the only operating mailbox.

Messages reaching spam should be evaluated through SPF, DKIM, DMARC, domain reputation, content,
and recipient engagement. A successful API response alone does not establish inbox placement.

## Twilio SMS

### Department Numbers

- The approved seller-inquiry A2P registration belongs to the shared acquisitions number. A
  Messaging Service is optional when Stonegate sends directly from that number.
- DS6 buyer SMS can select only an active Stonegate line classified as **Dispositions** / **Buyer
  Relations**. Before live use, that number needs accurate buyer/investor messaging registration
  when its use differs from the seller-inquiry campaign; the acquisitions registration must not be
  assumed to cover it.
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
- `TWILIO_MMS_MAX_MEDIA_BYTES` (optional; defaults to `10000000` bytes per photo)
- `TWILIO_MMS_MAX_TOTAL_BYTES` (optional; defaults to `25000000` bytes per message)
- `TWILIO_MMS_MAX_ATTEMPTS` (optional; defaults to `5` worker attempts)
- SMS timezone and contact-hour variables

`TWILIO_MESSAGING_SERVICE_SID` is optional. Stonegate's direct-number setup sends from
`TWILIO_SMS_FROM_NUMBER` and does not require a Messaging Service.

The Account SID, sending credential, direct sender number, and webhook base URL must be present on
both **oakwell-api** and **oakwell-worker**. The API validates callbacks; the worker performs staff
lead-alert sends and retains inbound MMS photos. The worker can download Twilio media with the
existing Account SID and Auth Token, or with the existing Twilio API key SID and secret pair. MMS
does not require another vendor account or a separate media API key.

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

### Inbound Photos And Recovery

The same signed **A message comes in** webhook accepts SMS and MMS. The API saves the message and
Twilio media references immediately; the communications worker then downloads each photo, applies
the configured type and size limits, and writes it to Stonegate's private document storage. Inbox
users receive attachment bytes only through the authenticated Stonegate API. Do not expose or save
the original Twilio media URL in the browser.

Keep the communications worker running with the Twilio credentials listed above and a working
`DOCUMENT_STORAGE_PROVIDER`. Database storage works for the current rollout; use the configured
private S3-compatible storage when production volume warrants it. The existing retention and
malware-scanning settings apply to MMS photos too.

After this feature is deployed, the worker also scans retained Twilio inbound-event payloads that
reported media before MMS storage was available. It automatically recovers those already-received
photos when Twilio still makes the media available. The operation is idempotent, so webhook replays
and worker retries do not create duplicate attachments.

### A2P Evidence

The campaign must reference the current branded public URLs:

- `https://www.stonegatehb.com/get-a-cash-offer`
- `https://www.stonegatehb.com/privacy-policy`
- `https://www.stonegatehb.com/terms`

The campaign consent description must match the actual separate unchecked SMS checkbox, its
`seller-sms-web-v3` wording, and actual message use. Do not claim keyword opt-in unless it is truly
supported, and do not describe purchased-list cold SMS if the campaign is for consented seller
inquiries.

Internal new-lead SMS alerts are a separate staff operational use case. They remain available to
employees who explicitly enable the relevant staff alert preference and do not depend on seller
SMS consent from the public property form.

### Acceptance

After campaign approval and direct-number configuration:

1. Send a controlled outbound SMS.
2. Confirm sent, delivered, and failed states.
3. Reply with one photo, then a photo-only message with two photos; confirm all three appear inline
   in the same Inbox thread and can be opened and downloaded by an authorized user.
4. Replay one MMS callback and restart the worker; confirm the photos are not duplicated. If a real
   pre-deployment MMS exists, confirm its retained photos are recovered automatically.
5. Test STOP, blocked send, START, and HELP behavior.
6. Confirm staff assignments do not break the seller thread and an unauthorized user cannot fetch
   its private attachment URL.
7. With an approved buyer test recipient and the registered Dispositions buyer-relations line, run
   one capped House outreach revision. Confirm permission and suppression preflight, provider state,
   one matching Buyer Inbox reply/review task, one ambiguous-reply review case, and no duplicate
   message after callback replay or worker restart.

### Governed House Buyer Outreach

DS6 adds no separate provider credential. Before any commercial buyer email outreach, set
`DISPOSITION_OUTREACH_PHYSICAL_POSTAL_ADDRESS` to Stonegate's complete, valid business postal
address on both the API service and the communications worker. The two services must use the same
value. This setting is intentionally blank by default and is non-secret because it is recipient-
visible compliance text; do not use a placeholder. A missing value blocks email outreach only.
Governed buyer SMS remains usable without this setting when its existing Twilio, permission, and
suppression requirements pass.

Both API and communications worker must also retain the same existing Resend and Twilio
configuration, and production must use `COMMUNICATION_PROVIDER_MODE=live`. In **Settings >
Communications** configure:

1. At least one active, outbound-enabled Resend sender alias that Stonegate is authorized to use for
   buyer outreach.
2. For SMS, an active Twilio company line with department **Dispositions** and purpose **Buyer
   Relations**, backed by the correct registration for the intended buyer messaging use.
3. The inbound Resend and Twilio webhook routes already documented above so delivery changes,
   opt-outs, and replies can reconcile.

The House Outreach workspace remains available while setup, readiness, package-approval, proof, or
backup checklist items are open. A package-backed revision still binds one exact usable frozen PDF
and records whether that artifact was **Preliminary** or approved; approval is not a prerequisite
for preparing or releasing the revision. The operator explicitly chooses the recipient paths and
sender. Release and delivery continue to enforce organization/role access, destination and sender
availability, STOP/Do Not Contact/suppression state, channel permission, and provider availability.
The implementation hard-caps each revision at 25 recipient-channel deliveries. It does not enable
InvestorLift or Land outreach and it does not place private economics in the message template.

Repository and automated tests do not establish provider acceptance. Before broad use, complete the
controlled email/SMS acceptance above with authorized test recipients, confirm pause and
cancel-unsent behavior, and verify that **Retry failed** is offered only for safely retryable
failures. An SMS in `delivery_unknown` must be investigated rather than retried automatically.

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
keys and a TwiML App are not required for Stonegate's cellphone-forwarding mode, but they are
required for the shared warm-call browser phone used by Inbox, Dispositions, and Quick Dial. This
does not reactivate the dormant native D4 prospecting dialer.
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

1. Select **Enable incoming** in the green OS phone and confirm its ready indicator appears.
2. Outbound call uses the Stonegate number and shows the final completed, busy, no-answer,
   canceled, or failed result rather than a generic browser-audio ending.
3. Inbound call rings the enabled browser and configured staff cellphone under the line's
   first-answer-wins strategy. Confirm Answer and Decline in the OS and press-1 screening on mobile.
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

## Dormant Native VA Dialer Foundation And Historical Browser Softphone

BatchDialer is Stonegate's production VA calling system. The native D0-D10 implementation is
retained for history, analytics, late signed callbacks, and safe cleanup, but its call execution,
softphone, activation controls, and pilot controls are dormant. The repository and Render
Blueprint change are prepared; the live environment is not considered dormant until the company
and campaign switches are off, every session/call is drained, the release is deployed, and the
production no-call check passes.

### Variables

- `PROSPECTING_NATIVE_DIALER_ENABLED=false` in the prepared Render API and worker configuration
- `PROSPECTING_NATIVE_DIALER_MAX_LINES=1`
- `PROSPECTING_NATIVE_DIALER_LEASE_SECONDS=90`
- `PROSPECTING_NATIVE_DIALER_STALE_AFTER_SECONDS=180`
- `PROSPECTING_NATIVE_DIALER_ORPHAN_GRACE_SECONDS=300`
- `PROSPECTING_NATIVE_DIALER_RESERVED_COST_CENTS=5`

The shared Stonegate browser phone uses these existing Twilio variables. The first eight are
readiness gates; the token TTL has a safe application default and is listed for deliberate tuning.
This list intentionally contains names only: credentials belong in the API service environment and
never in source, documentation, screenshots, URLs, browser storage, or frontend environment
variables.

- `TWILIO_VOICE_ENABLED`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_WEBHOOK_BASE_URL`
- `TWILIO_VALIDATE_WEBHOOK_SIGNATURES`
- `TWILIO_API_KEY_SID`
- `TWILIO_API_KEY_SECRET`
- `TWILIO_TWIML_APP_SID`
- `TWILIO_VOICE_TOKEN_TTL_SECONDS`

The application remains fail-closed by default in local and test environments. The prepared
production Blueprint also sets the launch flag to `false`. The schema and historical records keep
their one-to-three-line design, but they do not authorize a live line. A production maximum above
`1` remains rejected during application startup.

Phases D1-D7 install the data foundation, controlled server-side cold-call provider boundary,
durable one-line coordinator, browser softphone, VA workbench, disposition automation, and evidence
continuity. D3 owns the authenticated browser
lease, atomic queue reservation, calling-window and suppression rechecks, cap accounting, wrap-up
lock, company and campaign switches, and stale-session recovery. Call start, call control, and
native disposition completion are bound to the same lease; provider-start checkpoints and
provider-state reconciliation prevent ambiguous retries or missed callbacks from stranding a
session. D4 adds the
client-only Twilio SDK boundary, short-lived outbound-only Voice sessions, browser call controls,
and a strict separation between browser-audio status and seller child-leg status. No implementation
phase by itself authorizes a caller or campaign; runtime manager gates remain authoritative.

A native-dialer phone line must be active, belong to Acquisitions, and use purpose
`prospecting_outbound`. Do not reuse the ordinary `seller_conversations` line for native outbound
prospecting. Stonegate excludes the dedicated prospecting line from normal warm CRM call selection,
and routes inbound callbacks on that line through the D8 cold-prospect callback workflow. An exact
recent same-line dial match opens the assigned prospect context; ambiguous or unknown callers remain
isolated for review and never manufacture a warm seller lead.

Dormant production requires `PROSPECTING_NATIVE_DIALER_ENABLED=false` in both API and worker, the
company and all campaign native switches off, no active caller profile that can extend calling, no
open native pilot, and zero active sessions, legs, or provider calls. Do not turn a database switch
back on or use a historical direct URL as a substitute for owner authorization. BatchDialer remains
the calling system. My Calls remains available for manual qualification, notes, outcomes, and warm
handoffs without a native dialer lease; agreed appointments are entered manually in Stonegate.

### Shared Browser Calling Setup

This setup powers deliberate warm calls from seller records and Inbox, the Dispositions one-to-one
queue, and **New > Quick Dial**. It does not activate the dormant native VA prospecting dialer.

1. Keep `PROSPECTING_NATIVE_DIALER_ENABLED=false` in both API and worker.
2. In Twilio, create or select the TwiML App referenced by `TWILIO_TWIML_APP_SID`. Set its Voice
   Request URL to POST to
   `https://api.stonegatehb.com/api/v1/webhooks/twilio/voice/outbound`.
3. Put `TWILIO_API_KEY_SID`, `TWILIO_API_KEY_SECRET`, and `TWILIO_TWIML_APP_SID` in the Render API
   service alongside the existing Twilio Voice settings. Do not put them in the web service, source
   code, or any `NEXT_PUBLIC_*` variable.
4. In **Settings > Communications**, keep each staff member assigned to the active company line(s)
   they are authorized to use. Disposition staff need an active Buyer Relations line; acquisitions
   staff need an active Seller Conversations line. Quick Dial uses an authorized non-prospecting
   company line.
5. Keep the existing Twilio callback base URL on HTTPS and callback-signature validation enabled.
   After deployment, allow microphone access when the OS first asks to prepare the browser headset.
6. Open the green phone, select **Enable incoming**, and leave that signed-in OS tab open. The green
   ready dot means that browser can ring; closing or reloading the tab deliberately turns it off.
7. Call the applicable Stonegate number from a controlled outside phone. Confirm the browser and
   configured cellphone ring, answering either stops the other, Decline leaves other destinations
   available, and no answer reaches the configured voicemail/task plan.

### Historical D4 Twilio Browser Setup

Do not perform this activation procedure while the native dialer is dormant. It is retained only
to explain the implemented architecture and support authorized cleanup or audit work.

1. Confirm the production API and worker both report the native-dialer environment flag on and a
   maximum of one line. Leave company and campaign switches off until the dedicated test setup is
   complete.
2. In Twilio, create or select the TwiML App referenced by `TWILIO_TWIML_APP_SID` and configure its
   Voice Request URL as a POST to
   `https://api.stonegatehb.com/api/v1/webhooks/twilio/voice/outbound`.
3. Add the browser-Voice variable names listed above to the API service using the matching Twilio
   account, API key, and TwiML App. Never copy a secret into the web service or a `NEXT_PUBLIC_*`
   variable.
4. In **Settings > Communications**, assign the test caller an active Twilio line in Acquisitions
   with purpose `prospecting_outbound`. Keep its configured, profile, campaign, company, and
   environment line limits at one.
5. Confirm the Twilio callback base URL is HTTPS and callback-signature validation remains enabled.
6. Deploy with the one-line production feature available. Configuration alone does not authorize a
   caller or campaign; use the manager controls only for the approved isolated rollout.

### Historical D8 Manager Controls And Callback Routing

The normal Dialer Control and native callback panels are hidden in dormant mode. The recovery
behavior described below remains relevant only to an authorized drain, rollback, revocation, or
late-callback investigation; it is not an activation procedure.

Historical procedure — do not execute while dormant:

1. In **Settings > Communications**, create or edit the dedicated Acquisitions number and set
   **Line purpose** to **Prospecting outbound and callbacks**. Configure an approved primary or
   fallback manager for return-call coverage.
2. The former process opened **Prospecting > Dialer control** to configure each approved caller's
   dedicated line, active status, and optional daily dial and spend limits. The effective limit
   remained one live line.
3. Create a calling-hours and approved-script policy, then turn on the company switch and only the
   isolated campaign approved for the pilot. A switch change requires an audit reason.
4. Use **Sessions and recovery** to safely drain a caller after the current call, cancel an
   unanswered call, reconcile provider state, release only an untouched orphan reservation, or
   deliberately mark a terminal session failed. Never use recovery to interrupt a connected seller.
5. In **Prospecting > My Calls**, review **Recent callbacks**. Known callbacks can open the matched
   assigned prospect only after an explicit click. Unknown or ambiguous callbacks remain visible
   without changing the caller's current work. Missed callbacks create one urgent return-call task.
6. Monitor worker health, fresh session heartbeats, active legs, waiting callbacks, missed-call
   tasks, and sanitized operational errors from **Dialer control** before and during a pilot.

### Historical Analytics And Evidence

**Prospecting > Analytics** is visible only to users with acquisition-management authority. It
loads from `GET /api/v1/prospecting/dialer/analytics` with private, no-store response handling and
does not expose browser Voice tokens or provider credentials. Cost, revenue, and profit values are
returned only when that manager also has `financials:view`; otherwise the operating metrics
remain available and financial values are explicitly hidden.

The report defaults to the most recent 30 UTC dates. A manager can select an inclusive UTC start
and end date, up to 366 dates, then optionally filter by source, campaign, cohort, VA/caller, and
dial mode. Use UTC dates when reconciling a shift that crosses midnight in the employee's local
timezone. Source choices normalize native Stonegate, BatchDialer, paid ads, and other
attribution. Campaign, cohort, VA/caller, and dial-mode filters apply only to durable records that
carry those Stonegate operating dimensions. Native activity and attributed BatchDialer work or cost
can carry them; a raw external lead-source record usually does not. Clear those filters before a
cross-source comparison when the external source has no matching operating dimension.

The D9 window selects the originating activity, not the date every later outcome happened. Native
work enters by dial start; paid-ad and other acquisition enters by lead creation; BatchDialer
activity enters on the first durable BatchDialer handoff touch, including a match to an existing
lead, or at lead creation for a BatchDialer-created lead that has no durable handoff touch; costs
enter by incurred date; and paid time enters by work date. A later contract or close
remains attributed to that originating record and is reported as of the timestamp shown on the
dashboard. A paid lead that is later worked through BatchDialer can appear in both source rows.
Those rows are separate attribution views and must not be added together; the all-source summary
de-duplicates the same lead and downstream record.

The API rejects a report that would materialize more than 50,000 origin records. Narrow the UTC
dates or select a campaign, cohort, caller, or source instead of treating that response as an empty
report.
Collected gross revenue comes from collected revenue records. Contribution profit comes separately
from approved reconciliation company-profit evidence rather than an estimated assignment fee. A
closed transaction counts as a closed assignment only when its recorded strategy is assignment.

#### Record Cost And Time Evidence

1. Open **Prospecting > Campaigns**, select the exact campaign, and open **Costs**.
2. Link every cost to the measurement cohort when one is known. Use the actual **Incurred on** date
   so it falls inside the intended UTC analysis window.
3. For VA labor, choose the VA labor category, select the worker, and enter paid hours and hourly
   rate. This produces the labor amount and paid-time evidence used by per-hour metrics.
4. Record the actual list purchase against the matching cohort or import.
5. Record dialer license, phone-number, and voice-usage charges as provider costs. Record
   enrichment, software, or another category only under the category that describes the real
   expense.
6. Add the vendor and a short audit note. Do not enter a Finance payment merely to make a
   prospecting metric appear.
7. Record each expense once. Do not copy the same Twilio usage amount into both call-leg evidence
   and campaign voice usage; D9 prevents known provider-cost overlap, but duplicate manual ledger
   entries are still duplicate business costs.

An empty ledger is not treated as free. Paid time, provider cost, list cost, total cost, unit cost,
and profit-dependent values display **Unavailable** until their required records exist. A collected
revenue record supports gross revenue; a completed deal does not produce contribution profit until
its downstream reconciliation is approved.

#### Read The D9 Readiness Result

The readiness result is one of **Blocked**, **Needs review**, or **Ready for controlled pilot**.
Individual checks report pass, warning, or block for the dedicated prospecting line, browser token
configuration, callback routing, recording policy, current session health, organization-wide
one-line cap, and worker health.

**Ready for controlled pilot** means only that the technical checks passed at the observed time.
It does not activate a campaign, authorize broad calling, verify provider billing, or complete
production acceptance. D10 still requires the owner-controlled numbers, one VA, one small
non-overlapping campaign, call-by-call review, multiple clean shifts, provider-billing review, and
explicit owner acceptance.

#### Troubleshooting And Recovery

- **Analytics unavailable:** keep the prior confirmed snapshot, confirm API health and the signed-in
  manager's `operations:manage` permission, then reload once. Do not infer zero performance from a
  failed request.
- **Unexpected empty report:** confirm the inclusive UTC dates, remove optional filters one at a
  time, and verify the campaign, cohort, caller, dial mode, and source attribution on the original
  records.
- **BatchDialer or paid-ad rows show unavailable attempts or rates:** this is expected when
  Stonegate has attributable leads and outcomes but no raw provider-attempt evidence. Compare the
  common business outcomes rather than inventing dial volume.
- **Costs or paid-hour metrics are unavailable:** record the actual campaign cost and work-session
  evidence with the correct worker, campaign, cohort, and date. Never estimate a value only to
  clear a coverage warning.
- **Appointments, contracts, closes, revenue, or profit are missing:** verify the warm handoff points
  to the correct lead, appointment outcomes are final, the deal and transaction remain linked to
  that lead, assignment strategy is recorded for a closed-assignment count, gross revenue is marked
  collected, and the funded transaction's reconciliation is approved for contribution profit.
- **Historical native readiness is blocked:** do not reactivate Dialer Control. Escalate the named
  old session, line, callback, or worker condition for authorized drain, cancellation,
  reconciliation, or untouched-orphan recovery. Never interrupt a connected seller to clear a
  dashboard.
- **Worker check is stale:** verify the communications worker is live and its heartbeat advances
  before permitting another shift.
- **Rollback:** pause the native campaign, safely end native sessions, and return only the unworked
  non-overlapping cohort to BatchDialer. Keep native evidence read-only and never work the same
  active cohort in both systems.

The former D9/D10 native pilot never became the production calling path. Today, BatchDialer is the
production calling system, its official direct API is the sole CRM integration, and appointments
are entered manually in Stonegate.

### Historical D10 Controlled Pilot And Owner Acceptance

The native pilot screen and activation workflow are dormant. Existing pilot records remain
readable for audit, and rollback/revocation remains available for cleanup, but no new pilot may be
created, advanced, submitted, or accepted. The details below preserve the former acceptance design
and do not authorize its use.

Historical procedure — do not execute while dormant: the former process opened **Prospecting >
Pilot acceptance** only after the D9 technical blockers were clear. The D10
workflow is implemented, but Stonegate has not completed its live production acceptance. Each
record binds the rollout to one VA, campaign, cohort, calling batch, and dedicated line. When D10
acceptance enforcement is enabled, a matching `smoke_testing`, `running`, or owner-accepted scope
is required before a new native dial session can start; a campaign switch by itself is not
acceptance.

Starting a draft requires one to ten unique controlled E.164 numbers from active Stonegate staff
forwarding profiles. Each number must also belong to an eligible test prospect in the selected
calling batch. Start moves the record to `smoke_testing`; in that state, the coordinator can reserve
only those saved test records. Complete an answered controlled seller call with a durable call
record, canonical signed recording, signed seller-child evidence, every root and seller-child
provider call ID, the provider-reported charge for each ID, and provider evidence references;
refresh the workspace and save those exact records under **Smoke test**. Only server-validated smoke
evidence moves the exact pilot to `running` and makes the remaining eligible batch records callable.
The selected records prove at least one answered, recorded controlled seller call; cost evidence
must separately cover every provider-started root or child ID from the entire ended smoke stage,
including root-only failures. Smoke is bounded at 50 reservations / 100 provider IDs, and none of
its staff test calls count toward production-shift volume or time.

The first pilot uses these non-overridable ceilings and evidence minimums:

- one effective line at the runtime, company, VA, campaign, and Voice-line layers;
- a 75-to-250-record pilot batch;
- a daily dial cap between 25 and 50 reservations, plus no more than $10 of reserved provider spend
  per VA local date, so the safety cap still permits the required 25-call clean shift;
- three passing shifts on separate local dates;
- at least 60 minutes of provider-signed right-party conversation time and 25 terminal, signed seller calls
  in each passing shift;
- at least 75 qualifying signed seller calls total and a manager review for every reserved attempt,
  including safe pre-provider releases and root-only provider failures;
- zero lost answers, unintended duplicates, stuck sessions, missing callbacks, complaints, or
  unresolved compliance escalations;
- complete per-call provider-started cost reconciliation, controlled-number testing, kill-switch
  testing, a disjoint BatchDialer comparison, and a completed rollback drill.

The pilot UI never accepts typed aggregate counts as proof. It derives counts and relationships from
the persisted session, leg, attempt, callback, handoff, call-record, transcript, work-session, and
review records. For every provider-started graph in a shift, the manager enters the provider-reported
charge and a source reference for each distinct root and seller-child call ID from the provider
usage export, invoice, or call-detail record. Stonegate checks one-to-one call-ID coverage and
stores the reconciled per-ID values. A provider-documented `$0` charge is valid; a guessed or
unreferenced zero is not. The shift remains blocked while any pilot provider graph on that local
date is ambiguous or lacks reconciled cost evidence. It identifies other external evidence
separately when the direct BatchDialer CDR evidence does not prove it. All pilot reads are
private/no-store, and every
mutation uses an idempotency key plus the expected pilot revision so a stale manager tab cannot
overwrite newer evidence.

Connected seller conversations must have the canonical recording, completed transcript, and
structured notes before their attempt review can pass. A no-answer, voicemail, wrong-party,
canceled, or other non-contact attempt still requires a truthful terminal disposition, manager
review, compliance check, and provider-cost reconciliation, but it does not wait for a transcript
that should never be created.

The kill-switch exercise passes only from server-observed company and campaign off-then-on audit
pairs, stopped or drained pilot sessions, zero live sessions at capture, and an actual reservation
denial recorded after the VA reached the daily dial cap. The later rollback rehearsal must use a
different campaign off-then-on pair, stop or drain a real pilot session, leave zero active sessions
and legs, preserve immutable attempt/shift evidence, and hash the still-unworked batch remainder.
A clean passing shift must occur after that rehearsal. The separate **Rollback native pilot** action
requires **ROLL BACK SINGLE-LINE PILOT** typed exactly. On an unstarted draft it records a
`cancelled` pilot without pretending a live rollback occurred. On a started pilot it records
`rolled_back`, disables the scoped native campaign, safely drains or stops its sessions, preserves
native history, and identifies the unworked remainder. Neither action edits or enables BatchDialer
automatically.

Final approval is owner-only. The Owner or Founder/operator must type **ACCEPT SINGLE-LINE DIALER**
to accept or **REJECT SINGLE-LINE DIALER** to reject, and provide a reason. The API recalculates all hard gates transactionally, freezes the evidence
snapshot and digest, and refuses approval while any required evidence is failed, partial, unknown,
or in flight. Until the real shifts pass and that decision is recorded, the native dialer is not
production-accepted and BatchDialer remains the production calling system.

Acceptance authorizes only that frozen VA, campaign, cohort, batch, dedicated line, caps, and safety
configuration; the organization-wide acceptance gate stays enabled. An authorized owner can stop
the accepted scope from **Pilot acceptance** by entering a reason and typing **REVOKE SINGLE-LINE
DIALER** exactly. Revocation disables the scope, ends or drains its sessions, and preserves all
evidence. Every new seller bridge that has not already been authorized is blocked, while provider
work already authorized or in progress drains safely. It does
not reactivate BatchDialer automatically, and native calling cannot resume from that authorization:
the terminal pilot remains visible for audit. Dormant mode does not permit a replacement pilot.

### Historical D4 Controlled Acceptance Boundary

This checklist records the former controlled-test boundary. Do not execute it as a current setup
step while the native dialer is dormant.

Complete an isolated test-number or approved non-overlapping campaign acceptance before broad
production use:

1. Confirm an unauthorized user, wrong organization, stale tab, wrong browser identity, expired
   lease, and replaced lease cannot obtain a token or control a call.
2. Confirm every session-control response that can contain a lease and the Voice-session response
   includes `Cache-Control: private, no-store`. Confirm the Voice JWT remains memory-only. Confirm
   the dial-session ID, browser-session ID, and lease use only same-tab `sessionStorage` for idle
   reload recovery, never `localStorage`, URLs, DOM attributes, or application logs, and are cleared
   after terminal end or stop.
3. Deny microphone permission once and confirm the UI explains the failure without starting a
   provider call; grant permission and confirm readiness recovers.
4. Place one controlled browser-to-phone call and verify Start Calling, Stop Ringing, Mute, Hang
   Up, Retry, Pause, Resume, and End Shift against the durable Stonegate state.
5. Confirm Retry after a pre-connect SDK or network error reuses the same prepared intent and does
   not create a second Twilio call. Confirm Stop before Twilio supplies a call ID safely cancels the
   local preparation, and confirm an untouched preparation expires and releases after five minutes.
6. Confirm the browser/root SDK connection is labeled as browser audio and never marks the seller
   connected; only the Twilio child `<Number>` call may establish seller ringing or answer state.
7. Open a duplicate tab and confirm it stays passive. Expire a lease and confirm audited recovery
   rotates browser ownership and invalidates the old Voice identity. Repeat the exact recovery
   request to simulate a lost response and confirm it returns the same current lease without a
   second rotation; altered prior tokens or browser identifiers must remain rejected.
8. Refresh while idle and confirm the same valid lease and reserved prospect restore. Refresh
   during a live call and confirm the durable server state restores with a server-side hang-up
   option, while the UI clearly states that browser audio did not reattach. A full reload cannot
   resume the live JavaScript audio stream. During a live call, cancel one internal navigation and
   one browser Back attempt and confirm the page and audio remain in place; approve each once and
   confirm browser audio disconnects before navigation continues.
9. Confirm no cold call creates a fake warm Contact, Lead, Inbox conversation, or communication
   record, and confirm the existing cellphone-forwarding Voice and BatchDialer handoff workflows
   remain unchanged.
10. Return all native-dialer gates to off after the controlled test. D0-D9 are implemented, but
    production acceptance remains incomplete until the D10 controlled shifts pass and the owner
    explicitly approves activation.

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

- `BUYER_DATA_PROVIDER=dealmachine` on the API service
- `DEALMACHINE_API_KEY`
- `DEALMACHINE_BASE_URL=https://api.v2.dealmachine.com/v1`
- `DEALMACHINE_REQUEST_TIMEOUT_SECONDS=30`
- `BUYER_DISCOVERY_MAX_RESULTS=40`

The production Blueprint enables DealMachine only for governed, deal-specific House buyer
discovery on the API service. The worker does not need `BUYER_DATA_PROVIDER`. Keep
`UNDERWRITING_DEALMACHINE_COMPS_MODE=disabled` on both services; buyer discovery does not reactivate
DealMachine comp evidence.

The Buyer workspace readiness check must show the expected paid plan and available credits before
Alex spends a credit. Stonegate ranks the owned Buyer Network first. Paid discovery then uses three
sequential, net-new tiers: up to 10 candidates with a 30-credit ceiling, up to 20 additional
candidates with a 60-credit ceiling, and up to 40 additional candidates with a 120-credit ceiling.
The server also enforces a 250-credit per-deal cap, a 2,000-credit monthly organization cap, current
approved-package authority, current provider-estimate confirmation, binding tier ceilings,
recent-result reuse, and duplicate-request protection. The displayed dollar equivalent uses
Stonegate's current planning rate of $0.0075 per
credit ($150 per 20,000 credits); DealMachine's provider ledger remains authoritative.

Every tier begins with DealMachine's zero-credit estimate mode. The operator reviews the exact
scope, estimated credits, dollar equivalent, deal usage, and monthly usage before confirming the
paid request. That confirmation is bound to the exact preview fingerprint and requires both buyer
and deal editing authority. The tier ceiling remains the binding maximum because live owner-contact credits can
exceed the provider preview. An interrupted or incompletely reported paid attempt is durably saved
and blocks another paid search for that deal pending reconciliation. Results remain staged: they
cannot become active buyers, gain call or SMS permission,
or receive outreach without a separate human decision. DS12 acceptance must compare estimated and
actual credits and test provider result quality, field mapping, DNC-safe contact suggestion,
scoring, candidate review, duplicate handling, and cost on a controlled real deal before routine
dependence.

## BatchDialer Direct API Integration

BatchDialer is the VA cold-calling workspace; Stonegate is the system of record after a seller is
qualified. The official direct API is the sole BatchDialer-to-Stonegate integration. A bounded
worker poll retrieves provider campaigns, completed-call records, eligible contacts, and optional
transcript evidence. There is no public BatchDialer intake webhook or external automation step.

### Variables

The integration becomes active when its required API key is present. Add the values requested by
the Render Blueprint to the API and worker services:

- `BATCHDIALER_API_BASE_URL=https://app.batchdialer.com/api`
- `BATCHDIALER_API_KEY` (secret)
- `BATCHDIALER_POLL_SECONDS=120`
- `BATCHDIALER_SCAN_DAYS=2`
- `BATCHDIALER_ACCOUNT_TIMEZONE=America/Chicago`
- `BATCHDIALER_PAGE_LENGTH=100`
- `BATCHDIALER_MAX_PAGES_PER_DAY=50`
- `BATCHDIALER_HTTP_TIMEOUT_SECONDS=15`
- `BATCHDIALER_HTTP_MAX_ATTEMPTS=3`
- `BATCHDIALER_EVENT_MAX_ATTEMPTS=8`
- `BATCHDIALER_EVENT_RETRY_BASE_SECONDS=30`
- `BATCHDIALER_CAMPAIGN_REFRESH_SECONDS=3600`
- `BATCHDIALER_CHECKPOINT_LEASE_SECONDS=90`
- `BATCHDIALER_TRANSCRIPT_SYNC_ENABLED=true`

Use the Blueprint defaults unless a measured provider limit or production incident requires an
approved change. Keep `PROSPECTING_NATIVE_DIALER_ENABLED=false` in both API and worker.

Do not paste the BatchDialer key into chat, source code, documentation, logs, URLs, commands, or
screenshots. Do not inspect, rotate, delete, or replace it as part of ordinary integration work. The
owner enters it manually in the requested Render secret fields.

The API key is sent as the raw `X-ApiKey` value to the fixed official host. Do not prefix it with
`Bearer`. Stonegate rejects redirects and bounds response bytes, timeouts, pages, and retries.

### BatchDialer Configuration

1. In BatchDialer, open **Settings > Integrations > Integration Keys**, add a key named
   **Stonegate Direct API**, and place it only in the authorized Render secret fields.
2. Give each VA an individual **Agent** login and only the campaign access needed for their work.
3. Build one required lead sheet with owner verification, full property address, motivation,
   timeline, condition, occupancy, asking price, mortgage or lien context, best callback time,
   authorized follow-up channels, appointment, and notes.
4. Configure these call results:
   - **Qualified Seller - Follow Up**: use this exact label and **Do Not Redial Contact**.
   - **Appointment Set**: use this exact label and **Do Not Redial Contact**.
   - **Callback**: schedule the callback; use a qualified label only when the seller is genuinely
     qualified.
   - **Not Interested**: stop redialing the contact.
   - **Do Not Call**: add DNC.
   - **Wrong Number**: stop redialing that number.
   - **No Answer/Voicemail**: remain inside the BatchDialer cadence.

Stonegate recognizes only the exact reviewed **Qualified Seller - Follow Up** and **Appointment
Set** labels as candidate warm handoffs. A label alone cannot create a Lead. Transcript evidence
must prove a live two-way conversation with two distinct speakers and no clear disqualifier. Strong
evidence of seller interest is accepted automatically. When the live conversation is valid but
seller interest, classifier confidence, or the AI decision remains ambiguous, Stonegate imports the
Lead with a visible **Qualified seller needs review** task instead of losing the handoff.
**Appointment Set** without supported appointment agreement follows that review path but does not
create appointment-entry work. A changed or unknown label, unavailable classifier, invalid
citation, one-sided call, voicemail, no answer, wrong party, do-not-call request, or not-interested
result remains outside Leads. Do not broaden the mapping from a similar-looking label.
BatchDialer's optional **Mark As Lead** rule may organize records inside BatchDialer, but Stonegate
does not use it as an integration transport or eligibility substitute.

Current operating boundary:

- VAs place calls, work cadence, manage cold-call DNC, and choose results in BatchDialer.
- The direct worker retrieves candidate completed-call records, retries delayed transcripts, and
  creates or updates the Stonegate warm handoff after either strict evidence acceptance or the
  bounded live-two-way **needs review** path.
- A valid two-speaker conversation with only allowed uncertainty creates one Lead, provider call
  timeline, and high-priority review task. The task identifies that staff must confirm the handoff;
  it is not proof that the seller or an appointment was fully qualified.
- Unavailable AI, invalid citations, missing two-way proof, contradictory hard-conflict evidence,
  and unknown labels route to visible approval review in Tasks without creating a Lead, staff
  alert, property research, or seller call timeline first.
- Tasks shows **Approve** only for explicitly overridable uncertainty. Approval requires a written
  reason and applies only to the exact evidence fingerprint. Voicemail, wrong-party, DNC,
  not-interested, missing/invalid evidence, and unrecognized reasons are reject-or-correct only.
- Out-of-market properties remain eligible after evidence acceptance. Permission remains unknown
  unless a separate valid source proves it.
- Stonegate My Calls/lead records retain manual qualification, notes, outcome review, follow-up,
  and acquisitions handoff without a native dialer lease.
- When **Appointment Set** and the appointment agreement are supported, the VA creates the actual
  appointment manually in Stonegate from the urgent **Enter/verify Stonegate appointment** task.
  If only the live conversation is supported, the Lead receives qualification review but no
  appointment task. BatchDialer calendar data is not imported.
- BatchDialer remains authoritative for its cold-calling suppression. Stonegate still enforces
  opt-outs for communications sent from Stonegate.

### Supported Direct Operations

Version one uses only:

| Provider operation | Stonegate use |
| --- | --- |
| `GET /campaigns` | Refresh active provider campaign identity and status |
| `GET /v2/cdrs` | Retrieve completed calls by bounded date and cursor |
| `GET /contact/{contactID}` | Enrich a candidate warm result with seller/contact facts |
| `POST /cdrs/by-lead-id` | Optional call history when a nonblank vendor-contact ID exists |
| `GET /cdrs/{cdrID}/transcription` | Pre-lead evidence for candidate qualified and appointment-set results, with bounded readiness retries |

Do not use `/v2/cdrs/last`, calendar endpoints, provider write operations, or interface scraping.
Appointments and cold-call DNC remain in their authoritative systems: appointments in Stonegate,
cold-call DNC in BatchDialer.

### Polling, Evidence, And Replay Safety

The worker scans the configured rolling date window from page one. Overlap is intentional because
the provider's stateful latest-CDR watermark and deterministic tie-breaking are not accepted for
version one.

- Each CDR revision is archived before the checkpoint records success.
- An empty item list ends the bounded date scan even if another cursor is present; Stonegate records
  the anomaly.
- A repeated cursor or page-cap boundary makes the scan visibly failed or incomplete.
- Provider replay, overlapping scans, and service restarts must not duplicate a Lead, alert,
  attribution touch, research run, call record, or appointment task.
- A 401/403 surfaces an authentication blocker without exposing the key.
- A 429 or temporary provider failure uses bounded retry and durable catch-up.
- Unknown or renamed result labels are quarantined instead of guessed.

The raw CDR, contact, campaign, and transcript shapes remain provider evidence. Stonegate's normal
models are the business records. A provider phone number never proves SMS permission, and an
incomplete property must not be sent to research until staff supply a usable identity.

### Direct Acceptance

Run one controlled qualified call and one controlled appointment-set call, then confirm:

- direct health shows configured, a current worker heartbeat, and a successful poll;
- active provider campaigns appear in the discovered campaign evidence;
- **Qualified Seller - Follow Up** creates or updates one Lead with BatchDialer source, VA/campaign
  attribution, provider call evidence, normal Lead Manager work, and one staff alert;
- a transcript-backed two-way call with unclear interest or low classifier confidence creates one
  Lead plus one open **Qualified seller needs review** task, while invalid/one-sided evidence creates
  no Lead;
- a qualified seller with unknown permission is preserved without creating an SMS consent record;
- a qualified seller with an incomplete property receives visible data-quality work and does not
  trigger research against a placeholder;
- evidence-supported **Appointment Set** creates one Lead plus one urgent **Enter/verify Stonegate
  appointment** task and no Appointment; a two-way call without supported appointment agreement
  creates the Lead for qualification review but no appointment task;
- the VA creates the real appointment in Stonegate and the task/warning clears;
- rescanning the same provider call creates no duplicate business action;
- an altered result label is held for review;
- no-answer, voicemail, wrong-number, not-interested, and ordinary callback activity does not enter
  Leads;
- BatchDialer retains expected cold-call DNC/redial behavior; and
- delayed transcript evidence retries before any Lead is created; exhausted, unavailable, or
  structurally invalid evidence remains visibly reviewable outside Leads rather than silently
  passing the evidence gate.

After activation, reconcile provider CDR identities and eligible results against Stonegate for at
least 24 hours. Acceptance requires zero eligible misses, duplicate actions, or wrong-contact merges.

The worker also normalizes archived direct CDR observations into bounded call-fact batches for
**Prospecting > Analytics > BatchDialer VA performance**. This backfill requires no additional
provider credential. It drains immediately while history remains, then uses a durable checkpoint
to audit for missed or stale facts every ten minutes rather than rescanning every worker loop.
Managers must explicitly map observed provider agents to active Stonegate
users; no name or email match is inferred. The VA Performance Coach reuses the existing governed
OpenAI configuration and creates draft-only reports, so it adds no new environment variable.
An AI administrator must select **Install runtime** in **AI & Automation** after this release to
register the coach capability for an existing workspace. Generating a coaching draft never creates,
enables, or changes that capability and respects an administrator disabling it.

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

Implemented events are `PageView` from the Pixel; deduplicated browser/server `ViewContent`,
`Lead`, and `Contact`; and server-side `QualifiedLead` and `Schedule` from later CRM outcomes. In
the public seller funnel, `Lead` means the visitor completed the valid complete-address step.
`Contact` means the visitor then supplied a name and required phone number and submitted the contact
step. The unnumbered optional property-details section after confirmation does not send another Meta
event.

Browser and server copies use the same event name and deterministic event ID for each intake
attempt: the address stage uses `stonegate-lead-{intake_attempt_id}` and the completed contact stage
uses `stonegate-contact-{intake_attempt_id}`. Server delivery includes the source URL, user agent,
IP, `fbc`, and `fbp` when available. The address-stage `Lead` has no seller email or phone because
those fields have not been collected. The contact-stage `Contact` also includes hashed email when
provided and the CRM external ID. The phone hash is deliberately withheld from Meta because the
current mobile privacy promise excludes sharing mobile information for third-party marketing.

Acceptance sequence:

1. Generate the Conversions API access token in Meta Events Manager and store it in Render.
2. Add the Pixel ID to the web, API, and worker variables described above.
3. Add Meta's Test Events code to the API and worker, switch delivery to `live`, and redeploy.
4. Visit a public page and complete the property step of one controlled seller inquiry.
5. In Test Events, confirm browser and server `ViewContent` and address-stage `Lead` arrive and
   deduplicate.
6. Complete the contact step and confirm browser and server `Contact` arrive and deduplicate under a
   different event ID for the same intake attempt.
7. Confirm `Contact` Event Match Quality includes the expected non-phone match keys. Do not expect
   email coverage on the earlier address-only `Lead`.
8. Add optional post-submit details and confirm no additional Meta event is created.
9. Remove the test event code, redeploy, and monitor deduplication, freshness, coverage, and match
   quality during the first campaigns.

Meta rejects events older than seven days; the worker expires those instead of retrying an invalid
request. Delivery remains one event per request so one invalid event cannot reject unrelated
events.

## Website And Zapier Lead Intake Staff Alerts

The public **See My Selling Options** form has two visible stages and one unnumbered optional stage:

- Completing a valid property address and selecting **Continue** sends
  `POST /api/v1/public/seller-leads/address-capture`. It creates a cold address-only CRM lead, an
  address-stage conversion record, and a deduplicated Meta `Lead`. RealEstateAPI autocomplete may
  fill street, city, state, and ZIP, but manual entry remains available and provider-independent.
- The address-only record has no seller contact channel or contact authorization. It appears in
  **Leads > Address Only** as **Skip trace needed** and queues an internal employee SMS labeled
  **Stage 1 filled**. It does not start AI preparation, property research, a conversation,
  speed-to-lead work, or seller contact automation. Staff must research/skip trace the owner and
  check DNC status manually before any cold outreach; the system does not perform that DNC check
  automatically.
- Submitting the visible Contact step with name, required phone, optional email, and the displayed
  consent choices promotes the same CRM record to a completed seller inquiry. It sends the
  deduplicated Meta `Contact` event and a separate employee SMS labeled **Stage 2 filled**, then
  starts normal property research, AI work, conversation, speed-to-lead, and notification workflows.
- The optional property-details section shown after confirmation writes desired timeline, condition,
  occupancy, motivation, price, mortgage, repairs, and comments to the same lead. None of those
  details is required. It is not a numbered funnel step and does not send a Meta event.

One browser-generated `intake_attempt_id` identifies the property journey. Database locking and the
organization-scoped unique attempt constraint make Step 1 retries idempotent, make Step 2 promote
the same record, and prevent concurrent requests from creating two records. If the completed contact
request wins the race, a later Step 1 request can add the missing address-stage evidence but cannot
downgrade the completed lead. Retrying an already completed attempt returns the same lead.

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
Website address capture, website contact completion, and completed Facebook intake create
source-tagged alerts for every active user who has a valid cellphone and **Text new leads** enabled.
Website messages say **Stage 1 filled** and **Stage 2 filled** respectively. Their separate durable
source identities prevent duplicates, and Stage 1 uses the stable Address Only queue link because a
temporary placeholder can later merge into an existing lead. Within the recovery window, the
worker backfills a missing recipient in Stage 1-then-Stage 2 order without sending duplicates.
Stage 2 also waits while the same recipient's Stage 1 delivery is retrying.

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
| Controlled production acceptance of governed House owned-buyer email/SMS outreach and reply reconciliation | Owner/dispositions/developer | Before broad buyer outreach for the first contracted deal |
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
