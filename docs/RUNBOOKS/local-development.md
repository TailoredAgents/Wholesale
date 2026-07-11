# Local Development Runbook

## Database

```bash
createdb real_estate_wholesale
cd apps/api
uv sync
uv run alembic upgrade head
```

## Bootstrap

```bash
npm run bootstrap:api -- --admin-email richardaustindugger@users.noreply.github.com --admin-name "Richard Austin Dugger"
```

## Services

```bash
npm run dev:api
npm run dev:web
npm run worker
```

## Checks

```bash
npm run lint:web
npm run build:web
npm run lint:api
npm run typecheck:api
npm run test:api
```

## Local Protected Endpoints

Development-only auth uses the seeded email header. This is disabled in production until the real auth provider is selected.

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
