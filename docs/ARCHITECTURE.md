# Architecture

## Stack

- Frontend: Next.js App Router, React, TypeScript.
- Backend: FastAPI, Pydantic, SQLAlchemy, Alembic.
- Database: PostgreSQL.
- Worker: Python background worker.
- Queue/cache later: Render Key Value-compatible Redis.
- Files later: S3-compatible object storage.

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
infra
packages
scripts
```

## Rules

- Major records carry `organization_id`.
- Material writes use transactions and audit events.
- Business rules live in backend domain services.
- Webhooks are stored before async processing.
- AI tools must be narrow, permissioned, structured, and audited.
