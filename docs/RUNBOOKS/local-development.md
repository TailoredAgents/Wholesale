# Local Development Runbook

## Database

```bash
createdb real_estate_wholesale
cd apps/api
uv sync
uv run alembic upgrade head
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
