# Architecture

Last updated: July 20, 2026

## Stack

- Frontend: Next.js 16 App Router, React 19, TypeScript.
- Backend: FastAPI, Pydantic, SQLAlchemy, Alembic.
- Authentication: Clerk, with local RBAC remaining authoritative for permissions.
- Database: PostgreSQL.
- Worker: `apps/api/app/worker.py` for provider synchronization, transcription, and retention.
- Coordination/cache: Render Key Value-compatible Redis.
- Files later: S3-compatible object storage.
- Hosting: Render Blueprint connected to GitHub `main`.

Official docs checked:

- https://nextjs.org/docs
- https://fastapi.tiangolo.com/tutorial/sql-databases/
- https://render.com/docs/blueprint-spec
- https://openai.github.io/openai-agents-python/

## Monorepo

```text
apps/web
apps/api
apps/worker
docs
```

## Runtime Boundaries

- `apps/web` renders both public pages and authenticated OS routes.
- `apps/api` owns business rules, authorization, provider adapters, and all material writes.
- The Render worker runs `python -m app.worker` from `apps/api`; the original `apps/worker`
  heartbeat scaffold is not the production worker.
- PostgreSQL stores business records, provider identifiers, evidence, and audit history.
- Provider files stay private and are proxied through permission checks until object storage is
  introduced.
- Browser code receives Clerk sessions and short-lived provider tokens only, never raw provider
  secrets.

## Rules

- Major records carry `organization_id`.
- Material writes use transactions and audit events.
- Business rules live in backend domain services.
- Webhooks validate provider signatures and retain provider event identifiers for idempotency.
- AI tools must be narrow, permissioned, structured, and audited.
- Public seller pages and private OS routes remain separate experiences.
- Integration configuration uses the existing `oakwell-*` Render resources even though the
  customer-facing brand is Stonegate.
