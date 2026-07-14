# Render Deployment

The Render Blueprint is in `render.yaml`.

Planned staging resources:

- `oakwell-web`: Next.js web service.
- `oakwell-api`: FastAPI web service.
- `oakwell-worker`: background worker.
- `oakwell-postgres`: PostgreSQL database.
- `oakwell-key-value`: Render Key Value instance.

Deployment requirements:

- GitHub repo connected to Render.
- Clerk staging project created.
- All `sync: false` environment variables set in Render.
- API service can run `alembic upgrade head` on startup.
- Owner user bootstrapped in the staging database.

Use `docs/RUNBOOKS/render-staging-checklist.md` before creating staging.
