# Production Credentials Checklist

Last updated: July 27, 2026

## Purpose

This is the canonical inventory of external accounts, credentials, provider identifiers, and
runtime configuration Stonegate needs to operate as designed.

This file records names and status only. Never enter an API key, password, token, private database
URL, or webhook secret in this repository. Actual values belong in the provider dashboard and the
appropriate Render service environment.

## Status Legend

| Status | Meaning |
| --- | --- |
| Live | Required now and reported configured; retain periodic acceptance evidence |
| Render-managed | Render creates and injects the value |
| Built, activation pending | Stonegate code exists; provider account or acceptance remains |
| Selected, build pending | Provider decision is made; adapter is scheduled in a later phase |
| Provider selection pending | Capability is planned, but no provider or variable contract exists |
| Optional / deferred | The system runs without it |
| Not used | Deliberately excluded from the Stonegate architecture |

## Master Register

| Phase | Provider or account | Purpose | Status | Render services |
| --- | --- | --- | --- | --- |
| Core | GitHub | Source repository and CI | Live | Render account connection, not an environment variable |
| Core | Render | Web, API, worker, PostgreSQL, and Key Value hosting | Live | All |
| Core | Domain and DNS account | `stonegatehomebuyer.com` and provider records | Live | Provider dashboard only |
| Core | Clerk | Staff sign-in and session tokens | Live | Web and API |
| Core | Render PostgreSQL | Operational database | Render-managed | API and worker |
| Core | Render Key Value | Worker coordination and queues | Render-managed | API and worker |
| Underwriting | RentCast | Property facts, valuation, and comparable inputs | Live | API |
| AI | OpenAI | Copilots, transcription, summaries, and future governed tools | Live | API and worker |
| F4 | Cloudflare R2 | Private uploaded-file storage | Built, activation pending | API |
| F4 | SignWell | Electronic signatures and completed contract PDFs | Built, activation pending | API |
| F4 | ClamAV | Uploaded-file malware scanning | Optional / deferred | API/private service |
| F5 | DealMachine | Buyer discovery and enrichment | Built, activation pending | API |
| F8 | Resend | Operational outbound and inbound email | Selected, build pending | API and worker |
| F9 | Twilio Messaging | Seller and buyer SMS | Built, activation pending | API |
| F9 | Twilio Voice | Browser calling, inbound calls, and recordings | Built, activation pending | API and worker |
| Operations | Sentry | Error and trace monitoring | Optional / deferred | Web, API, and worker |
| Operations | Owner alert destination | Worker/readiness failure notifications | Optional / deferred | Worker |
| Future | ATTOM or licensed MLS/RESO | Secondary property and verified market data | Optional / deferred | API |
| Future | Google Ads and Meta | Offline conversion delivery | Provider selection pending | API or worker |
| Future | Cold-email platform | Separate cold-outreach infrastructure | Provider selection pending | Future adapter only |

## Core Runtime

### Clerk

Provider account owner: Stonegate owner-controlled company account.

| Variable | Secret | Render service | Source or value |
| --- | --- | --- | --- |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | No | `oakwell-web` | Clerk API Keys |
| `CLERK_SECRET_KEY` | Yes | `oakwell-web`, `oakwell-api` | Clerk API Keys |
| `CLERK_ISSUER` | No | `oakwell-api` | Clerk instance issuer URL |
| `CLERK_JWKS_URL` | No | `oakwell-api` | `<issuer>/.well-known/jwks.json` |
| `CLERK_AUDIENCE` | No | `oakwell-api` | Blank unless explicitly configured in Clerk |
| `CLERK_AUTHORIZED_PARTIES` | No | `oakwell-api` | Branded apex, `www`, and Render fallback web origins |

Acceptance:

- Sign in through `https://www.stonegatehomebuyer.com`.
- Confirm `/api/v1/me` returns the Stonegate user and local permissions.
- Confirm branded and Render fallback origins both work.

### Render Database And Key Value

These are generated bindings, not credentials the owner manually copies.

| Variable | Secret | Render service | Source |
| --- | --- | --- | --- |
| `DATABASE_URL` | Yes | `oakwell-api`, `oakwell-worker` | `oakwell-postgres` connection binding |
| `REDIS_URL` | Yes | `oakwell-api`, `oakwell-worker` | `oakwell-key-value` connection binding |

Acceptance:

- `/ready` reports database and worker readiness.
- API migrations complete during deployment.
- Worker heartbeat remains current.

### OpenAI

| Variable | Secret | Render service | Source or value |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | Yes | `oakwell-api`, `oakwell-worker` | OpenAI project API key |
| `OPENAI_BASE_URL` | No | API and worker | `https://api.openai.com/v1` |
| `OPENAI_DEFAULT_MODEL` | No | API and worker | Approved evaluated default |
| `OPENAI_HIGH_VOLUME_MODEL` | No | API and worker | Optional evaluated lower-cost model |
| `OPENAI_ESCALATION_MODEL` | No | API and worker | Optional evaluated escalation model |
| `OPENAI_TRANSCRIPTION_MODEL` | No | API and worker | Approved transcription model |

Acceptance:

- A governed Copilot draft completes and records model, tokens, latency, and estimated cost.
- A controlled recording transcribes after Twilio recording is activated.
- No OpenAI credential is exposed through a browser variable.

### RentCast

| Variable | Secret | Render service | Source or value |
| --- | --- | --- | --- |
| `PROPERTY_DATA_PROVIDER` | No | `oakwell-api` | `rentcast` |
| `RENTCAST_API_KEY` | Yes | `oakwell-api` | RentCast API Keys |
| `RENTCAST_BASE_URL` | No | `oakwell-api` | `https://api.rentcast.io/v1` |

Acceptance:

- Run a controlled market analysis on a known property.
- Confirm provider facts and comps are retained separately from staff-confirmed facts.
- Record the provider quota and billing review date in the owner account register.

## F4 Documents And E-Signature

### Cloudflare R2

| Variable | Secret | Render service | Source or value |
| --- | --- | --- | --- |
| `DOCUMENT_STORAGE_PROVIDER` | No | `oakwell-api` | Change from `database` to `s3` after acceptance |
| `DOCUMENT_STORAGE_ENDPOINT_URL` | No | `oakwell-api` | R2 S3 endpoint for the Stonegate account |
| `DOCUMENT_STORAGE_BUCKET` | No | `oakwell-api` | Private Stonegate bucket name |
| `DOCUMENT_STORAGE_ACCESS_KEY_ID` | Yes | `oakwell-api` | Bucket-scoped R2 API token |
| `DOCUMENT_STORAGE_SECRET_ACCESS_KEY` | Yes | `oakwell-api` | Bucket-scoped R2 API token secret |
| `DOCUMENT_STORAGE_REGION` | No | `oakwell-api` | `auto` |

Non-environment requirements:

- Private R2 bucket.
- Bucket-scoped API token with only the access Stonegate needs.
- Owner-controlled Cloudflare billing and recovery access.

Acceptance:

- Upload, authenticate, download, and delete a controlled file.
- Confirm an old database-backed file remains readable.
- Run `npm run documents:migrate` before applying the historical-file migration.

### SignWell

| Variable | Secret | Render service | Source or value |
| --- | --- | --- | --- |
| `ESIGN_PROVIDER` | No | `oakwell-api` | Change from `disabled` to `signwell` |
| `ESIGN_API_KEY` | Yes | `oakwell-api` | SignWell API settings |
| `ESIGN_BASE_URL` | No | `oakwell-api` | `https://www.signwell.com/api/v1` |
| `ESIGN_WEBHOOK_CALLBACK_URL` | No | `oakwell-api` | `https://oakwell-api.onrender.com/api/v1/webhooks/esign/signwell` |
| `ESIGN_SIGNWELL_WEBHOOK_ID` | Legacy fallback | `oakwell-api` | Leave blank when using Stonegate's connection action |
| `ESIGN_TEST_MODE` | No | `oakwell-api` | `true` until controlled acceptance passes |

Non-environment requirements:

- Attorney-approved Georgia purchase and assignment templates.
- Controlled test recipients for purchase and assignment signing acceptance.
- Owner selects **Connect SignWell** after deployment; Stonegate registers or reuses the webhook
  and stores its verification ID.

Acceptance:

- Send a test-mode package to controlled addresses.
- Verify ordered recipients, HMAC event verification, duplicate-event handling, reconciliation,
  and completed-PDF retention.
- Set `ESIGN_TEST_MODE=false` only after internal-document and provider acceptance.

Detailed procedure: `SIGNWELL_LAUNCH_RUNBOOK.md`.

### ClamAV

ClamAV is optional. Do not require scanning until a private scanner is reachable.

| Variable | Secret | Render service | Source or value |
| --- | --- | --- | --- |
| `DOCUMENT_MALWARE_SCANNER` | No | `oakwell-api` | `disabled` or `clamav` |
| `DOCUMENT_MALWARE_SCAN_REQUIRED` | No | `oakwell-api` | Keep `false` until acceptance |
| `CLAMAV_HOST` | No | `oakwell-api` | Private scanner hostname |
| `CLAMAV_PORT` | No | `oakwell-api` | `3310` |

## F5 Buyer Data

DealMachine is the selected startup provider. Stonegate stores the discovery run, scored candidate
evidence, selected imports, deduplication result, and later internal outcomes. DealMachine does not
replace the Stonegate buyer CRM or the Dispositions Copilot.

| Variable | Secret | Render service | Source or value |
| --- | --- | --- | --- |
| `BUYER_DATA_PROVIDER` | No | `oakwell-api` | `dealmachine` after the acceptance search |
| `DEALMACHINE_API_KEY` | Yes | `oakwell-api` | DealMachine Settings > Developer |
| `DEALMACHINE_BASE_URL` | No | `oakwell-api` | `https://api.v2.dealmachine.com/v1` |
| `DEALMACHINE_REQUEST_TIMEOUT_SECONDS` | No | `oakwell-api` | `30` |
| `BUYER_DISCOVERY_MAX_RESULTS` | No | `oakwell-api` | `100` initially |

Entitlements to confirm in the owner-controlled DealMachine account:

- Property search, owner contacts, selected record use, and API access are active.
- The plan credit allowance and current billing-cycle usage are visible.
- Default API limits are sufficient for Stonegate's capped, user-triggered searches.
- Stonegate's intended internal storage and retention comply with the current provider terms.

Acceptance:

1. Keep `BUYER_DATA_PROVIDER=disabled` during pre-revenue development. Subscribe when a seller
   opportunity is likely to become a signed contract within one to two weeks.
2. Change it to `dealmachine`, deploy the API, and open an approved Georgia disposition case.
3. In Dispositions > Buyers, run **Find investors** and confirm candidate names, purchase
   evidence, contact details, credit usage, and ranking are plausible.
4. Import two test candidates and repeat the same search. Confirm Stonegate links duplicates
   instead of creating second buyer records.
5. Confirm imported records remain unverified for buying criteria and proof of funds.
6. Confirm no messages, campaigns, or buyer selections occur from discovery or import.

Twilio and Resend remain the later communication providers for buyer outreach. A buyer-data API
does not replace the Stonegate buyer CRM.

## F8 Resend Operational Email

Resend is selected, but these values are planned and should not be added until the F8 adapter is
implemented.

| Planned variable | Secret | Planned Render service |
| --- | --- | --- |
| `EMAIL_PROVIDER` | No | API and worker |
| `RESEND_API_KEY` | Yes | API and worker |
| `RESEND_WEBHOOK_SECRET` | Yes | API and worker |
| `RESEND_SENDING_DOMAIN` | No | API and worker |
| `RESEND_RECEIVING_DOMAIN` | No | API and worker |
| `RESEND_DEFAULT_FROM_EMAIL` | No | API and worker |
| `RESEND_WEBHOOK_BASE_URL` | No | API and worker |

Non-environment requirements:

- Sending-domain DNS records.
- Deliberately approved receiving-domain MX records.
- Company aliases, signatures, reply routing, and retention policy.
- Signed webhook registration.

Detailed procedure: `RUNBOOKS/resend-email.md`.

## F9 Twilio Messaging And Voice

One Stonegate Twilio account can supply both SMS and Voice credentials, but the dedicated
Messaging Service, A2P Campaign, SMS sender, Voice number, and TwiML App are separate provider
objects.

| Variable | Secret | Render service | Purpose |
| --- | --- | --- | --- |
| `TWILIO_ACCOUNT_SID` | Sensitive identifier | API and worker | Account identity |
| `TWILIO_AUTH_TOKEN` | Yes | API and worker | Webhook validation and provider access |
| `TWILIO_API_KEY_SID` | Sensitive identifier | API | Browser Voice token signing identity |
| `TWILIO_API_KEY_SECRET` | Yes | API | Browser Voice token signing secret |
| `TWILIO_MESSAGING_SERVICE_SID` | Sensitive identifier | API | Dedicated Stonegate messaging service |
| `TWILIO_SMS_FROM_NUMBER` | No | API | Campaign-approved SMS sender |
| `TWILIO_VOICE_FROM_NUMBER` | No | API | Company Voice number |
| `TWILIO_TWIML_APP_SID` | Sensitive identifier | API | Browser Voice TwiML application |
| `TWILIO_WEBHOOK_BASE_URL` | No | API | `https://oakwell-api.onrender.com` |

Activation switches remain `false` until their individual acceptance tests pass:

- `TWILIO_SMS_ENABLED`
- `TWILIO_VOICE_ENABLED`
- `TWILIO_VOICE_RECORDING_ENABLED`

Non-environment requirements:

- Approved Stonegate A2P Brand and Campaign.
- Dedicated Stonegate Messaging Service and attached SMS number.
- TwiML App and Voice number webhooks.
- Recording disclosure text before recording is enabled.

Detailed procedures:

- `RUNBOOKS/twilio-a2p-campaign.md`
- `RUNBOOKS/twilio-sms-setup.md`
- `RUNBOOKS/twilio-voice-setup.md`

## Optional Operations Providers

### Sentry

| Variable | Secret | Render service |
| --- | --- | --- |
| `SENTRY_DSN` | Sensitive identifier | Web, API, and worker |
| `NEXT_PUBLIC_SENTRY_DSN` | Browser-visible | Web |

Acceptance requires one controlled web error, API error, and worker error reaching the approved
projects without raw request bodies or default PII collection.

### Owner Alert Destination

| Variable | Secret | Render service |
| --- | --- | --- |
| `OPERATIONS_ALERT_WEBHOOK_URL` | Yes | Worker |

This can target an owner-controlled alert channel. It is not required for normal business
workflow execution.

## Advertising Conversion Delivery

The Google Data Manager and Meta Conversions API adapters are implemented. Keep
`MARKETING_CONVERSION_MODE=disabled` until controlled provider acceptance is complete.

| Variable | Secret | Render service |
| --- | --- | --- |
| `MARKETING_CONVERSION_MODE` | No | API and worker |
| `MARKETING_CONVERSION_WINDOW_DAYS` | No | API and worker |
| `MARKETING_CONVERSION_MAX_ATTEMPTS` | No | API and worker |
| `MARKETING_CONVERSION_RETRY_BASE_SECONDS` | No | API and worker |
| `MARKETING_WEBSITE_BASE_URL` | No | API and worker |
| `GOOGLE_DATA_MANAGER_CLIENT_ID` | No | API and worker |
| `GOOGLE_DATA_MANAGER_CLIENT_SECRET` | Yes | API and worker |
| `GOOGLE_DATA_MANAGER_REFRESH_TOKEN` | Yes | API and worker |
| `GOOGLE_DATA_MANAGER_LOGIN_ACCOUNT_ID` | No | API and worker |
| `GOOGLE_DATA_MANAGER_OPERATING_ACCOUNT_ID` | No | API and worker |
| `GOOGLE_DATA_MANAGER_CONVERSION_ACTIONS_JSON` | No | API and worker |
| `META_CONVERSIONS_ACCESS_TOKEN` | Yes | API and worker |
| `META_PIXEL_ID` | No | API and worker |
| `META_CONVERSIONS_API_VERSION` | No | API and worker |
| `META_TEST_EVENT_CODE` | No | API and worker; remove after acceptance |

The Google conversion-action value is a JSON object with all four outcome keys, for example:

```json
{
  "qualified_lead": "123",
  "appointment_scheduled": "456",
  "contract_signed": "789",
  "funded_deal": "101112"
}
```

Acceptance:

1. Create four distinct Google Ads conversion actions and confirm the Google account IDs.
2. Enable the Data Manager API and obtain OAuth credentials with the Data Manager scope.
3. Use Meta Events Manager test events with Stonegate's Pixel/Dataset and temporary test code.
4. Prepare one controlled conversion for each outcome and inspect the masked queue record.
5. Confirm Google and Meta each receive one event and repeated preparation creates no duplicate.
6. Remove the Meta test code, set mode to `live` in both services, deploy, and monitor retries.

## Future Provider Placeholders

These capabilities remain planned:

- Address validation and live route-duration data.
- Separate cold-email platform and sending domains.
- Optional bank-data feed after the internal accounting ledger is proven.

F6D1 vendor profiles, bills, W-9 status, and evidence require no new provider credential. Files
use the existing private object-storage configuration. A future read-only bank feed remains
optional; F6D2 starts with authenticated CSV/OFX import so Stonegate is not blocked by a provider.

Optional secondary property-data variables already reserved:

- `ATTOM_API_KEY`
- `BRIDGE_API_BASE_URL`
- `BRIDGE_API_KEY`

Do not configure all three merely because fields exist. Activate a secondary source only after
underwriting calibration demonstrates the need and its data license is approved.

## Deliberately Not Used

| Provider or system | Decision |
| --- | --- |
| Gmail / Google Workspace OAuth | Replaced by the planned Resend operational-email adapter |
| Google Calendar / Outlook Calendar | Stonegate's internal calendar is the system of record |
| QuickBooks API | Stonegate will build its internal accounting ledger in F6 |
| Separate CRM | Stonegate's CRM remains the source of truth |
| National DNC API | No application-level DNC evidence integration is planned |
| Another AI platform | All copilots use the existing governed OpenAI runtime |

## Update Procedure

Update this file whenever a phase:

1. Selects or changes an external provider.
2. Adds, renames, or removes a provider environment variable.
3. Changes which Render service needs a credential.
4. Completes or fails provider acceptance.
5. Adds a recurring billing, quota, domain, number, certificate, or webhook dependency.

For each activation:

1. Create the provider account under an owner-controlled company identity.
2. Enter actual values only in the provider and Render dashboards.
3. Deploy the affected service.
4. Run the documented controlled acceptance case.
5. Update the status and `Last updated` date here.
6. Record billing ownership and renewal reminders in the owner's private account register.

This checklist records what Stonegate needs. Render and the provider dashboards remain the
authority for whether a real value is currently configured.
