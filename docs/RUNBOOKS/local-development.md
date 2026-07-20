# Local Development Runbook

## Database

```bash
createdb real_estate_wholesale
cd apps/api
uv sync
uv run alembic upgrade head
```

Copy the local environment template:

```bash
cp .env.example .env
```

Clerk values may stay blank for local-only development. Add them when testing real sign-in.

## Bootstrap

```bash
npm run bootstrap:api -- --admin-email richardaustindugger@users.noreply.github.com --admin-name "Richard Austin Dugger"
```

## Services

Run the web and API in separate terminals:

```bash
npm run dev:api
npm run dev:web
```

Run the same communications worker used by Render in a third terminal:

```bash
cd apps/api
uv run python -m app.worker
```

The root `npm run worker` command starts the original heartbeat scaffold and does not process
transcription, recording retention, or Gmail synchronization.

## Checks

```bash
npm run lint:web
npm run build:web
npm run lint:api
npm run typecheck:api
npm run test:api
```

## Local Protected Endpoints

Clerk bearer tokens are supported for protected endpoints. Local-only development can still use
the seeded email header. Production rejects the development header and requires Clerk auth.

```bash
curl -H 'X-Dev-User-Email: richardaustindugger@users.noreply.github.com' \
  http://localhost:8000/api/v1/me
```

Create a local lead:

```bash
curl -X POST http://localhost:8000/api/v1/public/seller-leads \
  -H 'Content-Type: application/json' \
  -d '{"property_address":"123 Peachtree St","property_city":"Atlanta","property_state":"GA","property_postal_code":"30303","name":"Jane Seller","phone":"4045551212","preferred_contact_method":"phone","consent_to_contact":true,"attribution":{"landing_page":"/get-a-cash-offer","utm_source":"google_ppc","utm_medium":"cpc"}}'
```

Submitting the same email/phone/address again should return `duplicate_status: "matched_existing_lead"` and reuse the existing active lead.

Open the internal operating system at:

```text
http://localhost:3000/os
```

Open a lead detail page from the OS dashboard or directly at:

```text
http://localhost:3000/os/leads/{lead_id}
```

The staff controls send a Clerk bearer token when available, otherwise they use the local
development email header. Stage updates and task completions write activity plus audit records.
