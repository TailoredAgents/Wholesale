# Stonegate Home Buyers Operating System

Local-first monorepo and Render deployment for Stonegate Home Buyers.

## Current State

- `apps/web`: Next.js 16 / React 19 public seller site and private operating system.
- `apps/api`: FastAPI / SQLAlchemy / Alembic business API with 93 migrations.
- `apps/api/app/worker.py`: deployed email synchronization, call transcription, and
  recording-retention worker, plus lead intake, property research, AI preparation, alerts, and
  provider retries. Fair sweeps give every queue a turn. An independent liveness heartbeat remains
  fresh during long provider work, while a separate main-loop progress/current-operation marker
  lets `/ready` report a genuinely hung operation only after the production 600-second stall
  threshold without treating a normal multi-provider call as stalled.
- `apps/worker`: original standalone heartbeat scaffold, retained for local history but not used by
  the Render worker service.
- `render.yaml`: deployed Render Blueprint with legacy `oakwell-*` resource names and no secrets.
- Clerk authentication and organization-scoped RBAC are live. Production API and protected web
  routes fail closed when Clerk is incomplete, development-header auth is explicit opt-in, and
  approval decisions require the permission for their exact request type. The approval API and
  Tasks approval feed show only request types covered by the viewer's permissions; `audit:view` is
  the only blanket organization-wide approval-read authority.
- CRM, shared inbox, Stonegate Valuation V3.1 with default-safe comp intelligence, reports,
  transactions, buyers, finance, marketing, and AI control foundations are implemented.
- Complete lead addresses automatically create a reusable Property Intelligence snapshot with
  normalized RealEstateAPI property facts, screened RentCast and RealEstateAPI comparable evidence,
  Stonegate-owned valuation math, provenance, conflicts, freshness, and an authorized listing
  image when the provider returns one. Inspection photos remain preferred; no Street View,
  satellite, or scraped imagery is used.
- The branded web domain is live. Stonegate's seller-inquiry A2P Campaign is approved. Internal
  Facebook lead alerts have prior delivery evidence but require one repeat acceptance after the
  worker credential correction; seller-facing SMS and final Twilio Voice acceptance remain.
- Resend sending, receiving, aliases, shared mailboxes, routing, attachments, notifications, and
  response management are implemented and configured. Provider events use UUID-fenced processing
  leases, durable validated-route checkpoints, bounded retry for early lifecycle events,
  manager-only audited dead-letter requeue, and bounded attachment downloads. Restricted aliases
  cannot auto-route or be manually assigned to standard-visibility conversations. Controlled
  production mailbox acceptance and the malware-scanning decision remain.
- Call Intelligence automatically fills only empty CRM fields, keeps narrative review beside the
  recording, retries temporary failures, exposes terminal exhaustion, and supports an audited
  manual retry from Inbox.
- Purchase agreements capture approved offer/underwriting/concession authority and revalidate it
  through approval, sending, e-signature, and execution. Manual execution requires exact signed
  evidence and an attestation.
- Zapier Facebook intake is intentionally secretless and uses Page/form restrictions, payload,
  burst, daily-volume, and deduplication controls. Those controls do not cryptographically prove
  Meta provenance, so monitoring remains required. Production in-process rate-limit keys use the
  edge-owned Cloudflare client address and ignore caller-supplied `X-Forwarded-For`; limiter key
  storage is hard-bounded, but distributed edge protection remains required before scale.

Start with:

- `docs/DOCUMENTATION.md`: documentation authority, status vocabulary, and maintenance rules.
- `docs/SYSTEM_MAP.md`: detailed as-built map of every major product surface, workflow, data domain,
  integration, and remaining production boundary.
- `docs/UI_CONTROL_REFERENCE.md`: page-by-page reference for buttons, fields, effects,
  prerequisites, disabled states, and expected results.
- `docs/USER_MANUAL.md`: detailed role-based instructions for using the public site and private OS.
- `docs/SETUP_MANUAL.md`: nontechnical account, provider, staff, launch, and maintenance guide.
- `docs/LEAD_MANAGER_USER_MANUAL.md`: plain-language daily guide for Stonegate Lead Managers.
- `docs/SETUP_REFERENCE.md`: consolidated local, Render, domain, credential, webhook, and provider
  setup reference without secret values.
- `docs/FINISHING_ROADMAP.md`: canonical remaining production acceptance and launch sequence.
- `docs/DISPOSITION_SIDEKICK_ROADMAP.md`: Buyer Network, House disposition, Offer Room, DS8
  manual InvestorLift handoff, and remaining disposition phases.
- `docs/INVESTORLIFT_PROVIDER_VERIFICATION.md`: official public provider evidence, unresolved live
  transport contract, support questions, and activation gate; it contains no credentials.
- `docs/CRM_INFORMATION_ARCHITECTURE_ROADMAP.md`: approved private-OS navigation, workspace,
  record-layout, compatibility, and role-acceptance upgrade plan; IA1 provides the executable
  contract, IA2 provides the live 11-destination shell, and IA3 provides the permission-filtered
  Settings workspace and legacy management redirects.
- `docs/VA_DIALER_ROADMAP.md`: one-by-one staff calling workflow, assignment, acceptance, and
  launch sequence.
- `docs/OPERATING_MODEL.md`: authoritative roles, workflow, compensation, AI, controls, and metrics.
- `docs/DESIGN_SYSTEM.md`: shared OS tokens, components, states, and responsive page contracts.
- `docs/AI_AGENTS.md`: agent architecture, portfolio, model routing, tools, memory, and autonomy policy.
- `docs/AI_AUTOMATION_ROADMAP.md`: ordered path from the current control plane to measured production automation.

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
development, but protected API calls use the development email header only after you deliberately
set `DEV_AUTH_ENABLED=true`. Keep that flag false in shared and production environments.

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
npm run lint:web
npm run typecheck:web
npm run audit:ia
npm run audit:underwriting

(cd apps/api && uv run pip-audit --strict --desc=off --progress-spinner=off)
(cd apps/web && npm audit --workspaces=false --audit-level=high)
```

Production operations:

```bash
# Populate DATABASE_URL and BACKUP_DIR through an approved secret-injection method first.
npm run db:backup
# Populate RESTORE_DATABASE_URL and ALLOW_RESTORE_TEST without entering a secret in shell history.
npm run db:restore-verify -- .backups/stonegate-YYYYMMDDTHHMMSSZ.dump
API_BASE_URL='https://api.stonegatehb.com' \
WEB_BASE_URL='https://oakwell-web.onrender.com' npm run ops:smoke
```

See `docs/SETUP_REFERENCE.md` before running a restore drill or configuring failure alerts.

GitHub Actions runs API lint, dependency audit, typecheck, and tests plus web dependency audit,
lint, explicit TypeScript checking, information-architecture and underwriting contract checks, and
the production build. The Next.js build still skips its embedded TypeScript validation because that
dependency graph can stall in this environment; the separate `tsc --noEmit` CI step is the hard
type gate.

## GitHub

The repository is pushed to:

```text
https://github.com/TailoredAgents/Wholesale.git
```

CI is defined in `.github/workflows/ci.yml`.

## Deployment

`main` deploys through the Render Blueprint. Public staging is currently available at:

- Website: https://oakwell-web.onrender.com
- API health: https://api.stonegatehb.com/health

The `oakwell-*` names are existing infrastructure identifiers, not a second product. Keep customer
copy branded as Stonegate Home Buyers. Use `docs/SETUP_REFERENCE.md` before changing environment
variables, DNS, or callback URLs.
