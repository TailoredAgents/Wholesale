# Render Deployment

Last updated: July 20, 2026

## Current Deployment

The Render Blueprint at `render.yaml` is deployed from GitHub repository
`TailoredAgents/Wholesale`, branch `main`.

Existing resources:

- `oakwell-web`: Next.js website and OS.
- `oakwell-api`: FastAPI API.
- `oakwell-worker`: background worker.
- `oakwell-postgres`: PostgreSQL.
- `oakwell-key-value`: Redis-compatible Key Value.

These names are legacy infrastructure identifiers. They all belong to the Stonegate application.
Do not create duplicate `stonegate-*` resources or delete `oakwell-*` resources based only on the
name.

## Deployment Behavior

- Web builds from `apps/web`.
- API runs Alembic migrations and environment bootstrap before Uvicorn starts.
- Worker runs `python -m app.worker` from `apps/api`.
- `sync: false` variables are managed in the Render dashboard.
- Secrets must not be placed in `render.yaml`.
- A push to `main` can trigger Blueprint service deployments.

## Current URLs

- Web: `https://oakwell-web.onrender.com`
- API: `https://oakwell-api.onrender.com`
- Health: `https://oakwell-api.onrender.com/health`
- Readiness: `https://oakwell-api.onrender.com/ready`

## Pending Deployment Work

- Connect Stonegate's custom domain.
- Update `API_CORS_ORIGINS`.
- Update `CLERK_AUTHORIZED_PARTIES`.
- Update email web origin and OAuth redirect if API/web custom subdomains are used.
- Update Twilio callback base URL only if the API host changes.
- Verify worker health after enabling Gmail sync, transcription, or retention jobs.
- Run the production acceptance checks in `TESTING.md`.

## Safety

- Preserve existing database and Key Value bindings.
- Review Blueprint diffs before syncing.
- Keep provider activation switches dashboard-managed.
- Do not change both a provider webhook and API environment configuration without an ordered
  rollback plan.
- Back up the database before destructive migrations or service consolidation.

Use `RUNBOOKS/render-staging-checklist.md` for environment-variable inventory and
`RUNBOOKS/domain-cutover.md` for the future custom-domain change.
