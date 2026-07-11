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
- API health: http://localhost:8000/health
- API readiness: http://localhost:8000/ready

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
