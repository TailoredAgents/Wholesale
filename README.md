# Real Estate Wholesaling Operating System

Local-first monorepo for a Georgia real-estate wholesaling operating system.

## Current State

- `apps/web`: Next.js 16 / React 19 / TypeScript dashboard shell.
- `apps/api`: FastAPI / SQLAlchemy / Alembic foundation API.
- `apps/worker`: Python worker scaffold.
- `docs`: Phase 0 product, architecture, data, workflow, AI, security, deployment, and roadmap docs.
- `infra/render.yaml`: draft Render Blueprint with no secrets.

## Prerequisites

- Node.js 20+
- npm 10+
- Python 3.12+
- uv
- PostgreSQL

Docker is not required for the current local setup.

## Local Setup

Create a local database:

```bash
createdb real_estate_wholesale
```

Install backend dependencies:

```bash
cd apps/api
uv sync
uv run alembic upgrade head
```

Copy `.env.example` to `.env` for local defaults. Clerk values can stay blank for local
development; protected API calls will use the development email header until Clerk keys are added.

Bootstrap the first local organization and owner:

```bash
npm run bootstrap:api -- --admin-email richardaustindugger@users.noreply.github.com --admin-name "Richard Austin Dugger"
```

Run the API:

```bash
npm run dev:api
```

Run the web app in a second terminal:

```bash
npm run dev:web
```

Open:

- Web: http://localhost:3000
- Public cash-offer form: http://localhost:3000/get-a-cash-offer
- Lead detail pages: `http://localhost:3000/leads/{lead_id}`
- API health: http://localhost:8000/health
- API readiness: http://localhost:8000/ready
- Protected local API example: http://localhost:8000/api/v1/me
- Lead list API: http://localhost:8000/api/v1/leads
- Lead detail API: `http://localhost:8000/api/v1/leads/{lead_id}`
- Lead stage update API: `PATCH http://localhost:8000/api/v1/leads/{lead_id}/stage`
- Dashboard summary API: http://localhost:8000/api/v1/dashboard/summary
- Public seller intake API: http://localhost:8000/api/v1/public/seller-leads

Public intake performs basic duplicate detection using normalized email, phone, and property address. Duplicate active submissions preserve new consent, form, and attribution evidence while matching the existing lead.

Protected endpoints support Clerk bearer tokens. Local development may use the development-only
email header; production rejects that header and requires Clerk authentication:

```bash
curl -H 'X-Dev-User-Email: richardaustindugger@users.noreply.github.com' \
  http://localhost:8000/api/v1/me
```

Create a local test lead:

```bash
curl -X POST http://localhost:8000/api/v1/public/seller-leads \
  -H 'Content-Type: application/json' \
  -d '{
    "property_address": "123 Peachtree St",
    "property_city": "Atlanta",
    "property_state": "GA",
    "property_postal_code": "30303",
    "name": "Jane Seller",
    "phone": "4045551212",
    "preferred_contact_method": "phone",
    "consent_to_contact": true,
    "attribution": {
      "landing_page": "/get-a-cash-offer",
      "utm_source": "google_ppc",
      "utm_medium": "cpc"
    }
  }'
```

## Checks

```bash
npm run lint:web
npm run build:web
npm run lint:api
npm run typecheck:api
npm run test:api
```

## Deployment Direction

Build and test locally first. Then push to GitHub. Render deployment comes after staging environment variables, database, key-value service, and object storage decisions are confirmed.
