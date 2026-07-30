# Stonegate Setup Reference

Last verified against the repository: July 29, 2026

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
| Property data | RentCast | Active |
| Operational email | Resend | Configured; controlled acceptance pending |
| SMS | Twilio | A2P resubmission/approval pending |
| Voice | Twilio | Configuration and acceptance pending |
| E-signature | SignWell | Configuration and acceptance pending |
| Buyer data | DealMachine | Deferred until an active deal is near contract |
| Private object storage | S3-compatible/Cloudflare R2 | Optional/pending |
| Error monitoring | Sentry | Optional/deferred |
| Ad conversion delivery | Google and Meta | Pending |

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

Clerk can remain blank for local development. The API permits the configured development email
header only when `APP_ENV` is not production.

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
- `LOG_LEVEL`
- `DATABASE_URL`
- `REDIS_URL`
- `DEFAULT_ORGANIZATION_NAME`
- `BOOTSTRAP_ADMIN_EMAIL`
- `BOOTSTRAP_ADMIN_NAME`
- `API_CORS_ORIGINS`
- `WORKER_READINESS_REQUIRED`
- worker heartbeat, retry, and failure-alert variables

### Clerk

- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` on web
- `CLERK_SECRET_KEY` where Clerk server operations are used
- `CLERK_ISSUER`
- `CLERK_JWKS_URL`
- `CLERK_AUDIENCE` when required by the Clerk token configuration
- `CLERK_AUTHORIZED_PARTIES`
- Clerk sign-in, sign-up, and fallback redirect variables on web

The Clerk issuer and JWKS URL belong to Clerk. They must never point at the Stonegate API.

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

## RentCast And Property Data

Variables:

- `PROPERTY_DATA_PROVIDER=rentcast`
- `RENTCAST_API_KEY`
- `RENTCAST_BASE_URL=https://api.rentcast.io/v1`
- optional `ATTOM_API_KEY` placeholder

Acceptance:

1. Analyze several known Georgia addresses.
2. Confirm subject identity before relying on returned records.
3. Review selected and excluded comparables.
4. Confirm investor and client PDFs.
5. Record provider failures and verified outcomes.

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

Google OAuth variables are superseded and should remain unused.

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
5. Resolve or assign unmatched inbound routing exceptions.

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

Messages reaching spam should be evaluated through SPF, DKIM, DMARC, domain reputation, content,
and recipient engagement. A successful API response alone does not establish inbox placement.

## Twilio SMS

### Separation Rule

Stonegate must use its own:

- A2P brand and campaign
- Messaging Service
- 10DLC number
- campaign description and samples
- public consent evidence
- webhook destinations

Do not share another business's campaign or number.

### Variables

- `TWILIO_SMS_ENABLED`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_MESSAGING_SERVICE_SID`
- `TWILIO_SMS_FROM_NUMBER`
- `TWILIO_WEBHOOK_BASE_URL=https://api.stonegatehb.com`
- `TWILIO_VALIDATE_WEBHOOK_SIGNATURES=true`
- SMS timezone and contact-hour variables

The Auth Token is not the Account SID. Twilio displays them as separate values in the account
console.

### Webhooks

Messaging Service incoming request:

```text
POST https://api.stonegatehb.com/api/v1/webhooks/twilio/messaging/incoming
```

Delivery status callback:

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

After campaign approval and number attachment:

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
- `TWILIO_API_KEY_SID`
- `TWILIO_API_KEY_SECRET`
- `TWILIO_TWIML_APP_SID`
- `TWILIO_VOICE_FROM_NUMBER`
- `TWILIO_WEBHOOK_BASE_URL`
- token TTL, ring timeout, timezone, and calling-hour variables
- `TWILIO_VOICE_RECORDING_ENABLED`
- `TWILIO_VOICE_RECORDING_DISCLOSURE`
- `CALL_RECORDING_RETENTION_DAYS`

The Account SID identifies the Twilio account. The Auth Token validates provider requests. The API
key SID and secret mint limited browser Voice tokens. The TwiML App tells Twilio where outbound
browser calls should request call instructions.

### Webhooks

- outbound Voice instructions: `/api/v1/webhooks/twilio/voice/outbound`
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
6. Recording remains off until disclosure and retention policy are approved.
7. When recording is enabled, media access, transcription, review, and deletion are tested.

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

Current decision: keep the adapter ready, but purchase API access when Stonegate is close to a
contracted deal. Acceptance must test provider result quality, field mapping, scoring, candidate
review, import, duplicates, and cost before recurring dependence.

## Marketing Conversion Delivery

Variables include:

- `MARKETING_CONVERSION_MODE`
- conversion window, retry, and website values
- Google Data Manager client, refresh token, account, and conversion action values
- Meta access token, pixel ID, API version, and optional test event code

Keep delivery disabled until ad accounts and conversion actions are approved. Test with provider
test modes, verify hashed contact data, confirm event deduplication, and reconcile accepted events
to CRM outcomes.

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
npm run build:web
```

### Backup

```bash
DATABASE_URL='...' npm run db:backup
```

### Restore Verification

```bash
RESTORE_DATABASE_URL='...stonegate_restore_test' \
ALLOW_RESTORE_TEST=true \
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
3. `/health` and `/ready` pass.
4. public homepage, cash-offer form, privacy, and terms load.
5. Clerk sign-in reaches the correct OS navigation.
6. one protected API request succeeds.
7. worker heartbeat is fresh.
8. the changed workflow receives a focused end-to-end test.

## Setup Work Still Required

| Work | Owner | Trigger |
| --- | --- | --- |
| Resend controlled production acceptance | Stonegate owner/partner | Now |
| Search Console and service-area Business Profile acceptance | Stonegate owner/marketing | Before local search launch |
| First genuine public proof acceptance | Stonegate owner/marketing | After a documented review or outcome exists |
| First controlled homepage experiment acceptance | Stonegate owner/marketing | After a stable production baseline exists |
| Approved public team content and photography | Stonegate owner/marketing | Before PC8 production acceptance |
| Twilio A2P resubmission and approval | Stonegate owner | Provider application |
| Dedicated Twilio SMS and Voice acceptance | Owner and developer | After A2P approval |
| SignWell activation and end-to-end signing | Owner and transaction staff | Before live contracts |
| DealMachine subscription and acceptance | Owner and dispositions | Near first contracted deal |
| CPA accounting acceptance | Owner, finance, CPA | Before relying on first closed period |
| Underwriting calibration | Owner/acquisitions | As real outcomes accumulate |
| Google/Meta conversion activation | Owner/marketing | When ad accounts are ready |
| Production restore drill | Owner/developer | Before broad launch |
| Sentry and alert webhook | Owner/developer | Optional |

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
