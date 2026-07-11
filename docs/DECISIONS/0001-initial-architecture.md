# ADR 0001: Initial Architecture

## Status

Accepted

## Decision

Use a local-first monorepo with Next.js for the web app, FastAPI for the API, Python for workers, PostgreSQL as the source of truth, Alembic for migrations, and Render as the later hosting target.

## Consequences

- Clear separation between UI, API, and async work.
- OpenAPI can drive typed frontend clients later.
- PostgreSQL remains authoritative.
- Two language ecosystems require disciplined scripts and CI.
