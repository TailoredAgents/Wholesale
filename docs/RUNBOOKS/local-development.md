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
curl -X POST http://localhost:8000/api/v1/leads \
  -H 'Content-Type: application/json' \
  -H 'X-Dev-User-Email: richardaustindugger@users.noreply.github.com' \
  -d '{"contact":{"legal_name":"Jane Seller"},"property":{"street_address":"123 Peachtree St","city":"Atlanta","state":"GA","postal_code":"30303"},"source":"google_ppc","stage_key":"new"}'
```
