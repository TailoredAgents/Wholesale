# Stonegate Home Buyers Operating System

Local-first monorepo and Render deployment for Stonegate Home Buyers.

## Current State

- `apps/web`: Next.js 16 / React 19 public seller site and private operating system.
- `apps/api`: FastAPI / SQLAlchemy / Alembic business API with 24 migrations.
- `apps/api/app/worker.py`: deployed email synchronization, call transcription, and
  recording-retention worker.
- `apps/worker`: original standalone heartbeat scaffold, retained for local history but not used by
  the Render worker service.
- `render.yaml`: deployed Render Blueprint with legacy `oakwell-*` resource names and no secrets.
- Clerk authentication and organization-scoped RBAC are live.
- CRM, shared inbox, underwriting V2.1, reports, transactions, buyers, finance, marketing, and AI
  control foundations are implemented.
- Final dedicated Twilio SMS, Voice, custom-domain, and Google Workspace setup is pending.

Start with:

- `docs/OPERATING_MODEL.md`: authoritative roles, workflow, compensation, AI, controls, and metrics.
- `docs/CURRENT_STATE.md`: delivered capabilities, live environment, pending setup, and limits.
- `docs/ROADMAP.md`: ordered development phases after provider setup.
- `docs/UNIFIED_BUILD_PLAN.md`: long-term product scope and quality standard.
- `docs/INTEGRATIONS.md`: provider status and system boundaries.

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

Seed a repeatable, entirely synthetic workspace for local workflow testing:

```bash
npm run seed:demo -- --owner-email owner@example.test --owner-name "Demo Owner"
```

Local `.env` defaults communications to `simulate`. Simulated SMS and email are retained in the
normal conversation timeline but never leave the computer. Simulation is rejected when
`APP_ENV=production`.

Run the API:

```bash
npm run dev:api
```

Run the web app in a second terminal:

```bash
npm run dev:web
```

Open:

- Public website: http://localhost:3000
- Public cash-offer form: http://localhost:3000/get-a-cash-offer
- Internal operating system: http://localhost:3000/os
- Lead detail pages: `http://localhost:3000/os/leads/{lead_id}`
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
npm run build:web
npm run lint:api
npm run typecheck:api
npm run test:api
```

Production operations:

```bash
DATABASE_URL='...' npm run db:backup
RESTORE_DATABASE_URL='...stonegate_restore_test' ALLOW_RESTORE_TEST=true \
  npm run db:restore-verify -- .backups/stonegate-YYYYMMDDTHHMMSSZ.dump
API_BASE_URL='https://oakwell-api.onrender.com' \
WEB_BASE_URL='https://oakwell-web.onrender.com' npm run ops:smoke
```

See `docs/PHASE_1_RELIABILITY.md` before running a restore drill or configuring failure alerts.

`npm run lint:web` is not currently part of CI because ESLint hangs locally before diagnostics.
Next.js web builds currently skip build-time TypeScript validation because Clerk dependency type
checking stalls locally; API lint, API typecheck, API tests, and the web production compile remain
the required gates.

## GitHub

The repository is pushed to:

```text
https://github.com/TailoredAgents/Wholesale.git
```

CI is defined in `.github/workflows/ci.yml`. Branch protection and labels are documented in
`docs/GITHUB_SETUP.md`.

## Deployment

`main` deploys through the Render Blueprint. Public staging is currently available at:

- Website: https://oakwell-web.onrender.com
- API health: https://oakwell-api.onrender.com/health

The `oakwell-*` names are existing infrastructure identifiers, not a second product. Keep customer
copy branded as Stonegate Home Buyers. Use `docs/RENDER_DEPLOYMENT.md` and the provider runbooks
before changing environment variables or callback URLs.
