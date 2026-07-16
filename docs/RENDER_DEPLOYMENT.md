# Render Deployment

The Render Blueprint is in `render.yaml`.

Planned staging resources:

- `stonegate-web`: Next.js web service.
- `stonegate-api`: FastAPI web service.
- `stonegate-worker`: background worker.
- `stonegate-postgres`: PostgreSQL database.
- `stonegate-key-value`: Render Key Value instance.

Deployment requirements:

- GitHub repo connected to Render.
- Clerk staging project created.
- All `sync: false` environment variables set in Render.
- API service can run `alembic upgrade head` on startup.
- Owner user bootstrapped in the staging database.
- `OPENAI_API_KEY` set before running production AI agents.

Use `docs/RUNBOOKS/render-staging-checklist.md` before creating staging.
