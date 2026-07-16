# Render Deployment

The Render Blueprint is in `render.yaml`.

Planned staging resources:

- `oakwell-web`: Next.js web service.
- `oakwell-api`: FastAPI web service.
- `oakwell-worker`: background worker.
- `oakwell-postgres`: PostgreSQL database.
- `oakwell-key-value`: Render Key Value instance.

These Render resource names are legacy infrastructure IDs. The customer-facing brand inside the
application is `Stonegate Home Buyers`.

Deployment requirements:

- GitHub repo connected to Render.
- Clerk staging project created.
- All `sync: false` environment variables set in Render.
- API service can run `alembic upgrade head` on startup.
- Owner user bootstrapped in the staging database.
- `OPENAI_API_KEY` set before running production AI agents.
- `RENTCAST_API_KEY` set before enabling comp automation.

Use `docs/RUNBOOKS/render-staging-checklist.md` before creating staging.
