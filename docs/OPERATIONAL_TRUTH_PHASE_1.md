# Operational Truth - Phase 1

Status: implemented in the repository; production acceptance follows the deployment checklist below.

## Outcome

Phase 1 makes Stonegate's runtime behavior measurable before any broad refactor. It separates four
questions that the old health path mixed together:

1. Is the API process alive?
2. Can the API and its database accept CRM traffic?
3. Is the background worker making progress?
4. Are optional providers configured and operating without an open failure?

A provider or worker problem must be visible without unnecessarily removing an otherwise usable CRM
API from service. This phase adds the evidence needed to decide where Phase 2 performance work will
actually produce value.

## Health contracts

| Endpoint | Purpose | Healthy response | Failure behavior |
| --- | --- | --- | --- |
| Web `/health` | Proves the deployed Next.js application can execute a route handler | HTTP 200, `status: ok` | Non-200 lets Render stop routing to the web instance |
| API `/health` | Process liveness only; no database or provider calls | HTTP 200, `status: ok` | Process/server failure only |
| API `/ready` | Required API traffic dependency: database | HTTP 200, `status: ready` | HTTP 503 with the same top-level shape and `status: not_ready` |
| API `/health/operations` | Database, worker progress, open failures, retry state, and optional-provider configuration | HTTP 200, `status: healthy` | HTTP 503 with a stable top-level `status`, `database`, `worker`, `providers`, and `operations` shape |
| API `/health/database-observability` | Safe database/pool instrumentation diagnostic | HTTP 200 with dialect, query-statistics status, and pool counters | Request failure is visible in request telemetry |

Render probes the web `/health` route and API `/ready` route. It does not use optional provider or
worker state to admit normal API traffic. The scheduled operational smoke test separately requires
`/health/operations` to be healthy and prints the full bounded response when it is not.

Detailed health responses use `Cache-Control: no-store`. They expose operation names and
configuration-key names, but no credential values, provider payloads, contacts, or customer data.

Provider status `configured` means required configuration is present and no tracked failure is open.
It deliberately does not claim that a live provider request was just completed. `degraded` means a
configuration blocker or durable open failure is present.

## Request and SQL measurements

Every request receives an in-memory request metrics object. SQLAlchemy process hooks add query count,
total SQL time, and maximum single-query time to that request without recording SQL text or bind
parameters. The final structured `api_request_completed` event contains only:

- HTTP method, matched route template, response status, and client-visible duration;
- declared/read request bytes and response bytes;
- SQL count, total SQL milliseconds, and maximum SQL milliseconds;
- safe pool class/capacity counters;
- bounded performance flags and the exception class, when one escaped.

The route template is logged instead of the raw URL, so record IDs and query strings do not enter
the event. Headers, bodies, SQL, parameters, email addresses, phone numbers, and provider responses
are never logged by this instrumentation. Telemetry failures are swallowed and cannot alter the API
response.

The client-visible timer stops when the final response body is sent. SQL from dependency cleanup or
detached background tasks is ignored after that point, even though Python context can be inherited
by a task.

To bound monitoring overhead:

- every failed request is logged;
- every request with a performance flag is logged;
- healthy `/health` polling is suppressed;
- ordinary successful traffic is sampled at one event per 20 requests.

Current performance flags are:

| Flag | Threshold |
| --- | --- |
| `slow_request` | at least 1,000 ms |
| `high_query_count` | at least 50 SQL statements |
| `high_sql_time` | at least 500 ms total SQL time |
| `large_request` | at least 1 MB |
| `large_response` | at least 1 MB |

These are diagnostic thresholds, not user-experience targets. Phase 2 should use the observed route
distribution and traces to set route-specific budgets.

## Database observability

Migration `0134_pg_stat_statements` enables PostgreSQL's `pg_stat_statements` extension when the
dialect is PostgreSQL. It is idempotent, does nothing for SQLite tests, and intentionally does not
drop the shared extension on downgrade.

The database diagnostic reports `available` only after both the extension catalog check and a safe
zero-row view query succeed. It never reads or returns statement text. Pool state is captured before
the diagnostic query checks out its own connection so the endpoint does not inflate its own
`checked_out` count.

## Worker and retry measurements

The worker records bounded latest-operation evidence on its existing heartbeat row:

- operation name;
- `processed`, `idle`, `backing_off`, or `failed` outcome;
- last duration and finish time;
- current operation and independent main-loop progress time.

Open failures remain durable records with attempt count, error class, oldest age, and next retry.
Waiting for an existing BatchDialer retry deadline is recorded as `backing_off`; it no longer creates
a new failure or falsely increments the worker's consecutive failure count. The original incident
remains visible until a later successful operation resolves it.

Long BatchDialer catch-up scans refresh main-loop progress after every archived provider page, so a
large but advancing import does not look stalled merely because it exceeds the ordinary operation
window. Worker startup also resolves open failure rows belonging to retired operation names while
leaving every active operation failure open; a renamed job can no longer poison health forever.

This is deliberately bounded latest-state instrumentation, not a time-series system. If the first
measurements show a need for percentiles or long-term worker trends, add a metrics backend in a later
phase rather than growing the heartbeat JSON indefinitely.

Processor-owned retry, review, and dead-letter columns remain separate from `OperationalFailure`.
When a processor durably records one of those outcomes and returns normally, this endpoint currently
shows the operation as processed rather than aggregating every domain queue. In particular,
Disposition outreach status `failed_retryable` is terminal in the current implementation despite its
name. Phase 2 should add bounded, read-only lane aggregates with age thresholds before using those
domain statuses as a global 503 gate; historical terminal rows must not make health permanently red.

## Deployment gates and production smoke

- API and web GitHub Actions jobs must pass before the three Git-backed Render services auto-deploy.
- Required Blueprint validation is deterministic and offline. A live comparison with Render's
  published schema remains advisory, so an external documentation/schema outage cannot block a
  release.
- All web contract tests run in CI.
- Full strict mypy currently contains 399 accepted legacy errors. CI runs full mypy through a
  committed regression ratchet: new fingerprints or increased counts fail. This is visible debt,
  not a claim that typing is clean.
- An hourly authenticated smoke harness can use a dedicated Clerk employee to validate real
  identity, Leads, Conversations, company Dispositions data, and their protected pages. It mints a
  fresh token per automated check and revokes the session when finished.

The one-time GitHub credentials and permission setup for the authenticated monitor are documented in
`docs/DEPLOYMENT_GATES_AND_AUTHENTICATED_SMOKE.md`. Until that setup is completed and
`AUTHENTICATED_SMOKE_ENABLED=true`, the scheduled authenticated run is intentionally inactive.

## Operator acceptance after deployment

1. Confirm Render applied **After CI Checks Pass** to web, API, and worker after the Blueprint sync.
2. Confirm web `/health`, API `/health`, and API `/ready` return HTTP 200.
3. Confirm `/health/operations` returns HTTP 200 after the worker has started; inspect the returned
   worker/provider/failure fields instead of repeatedly restarting the API if it does not.
4. Confirm `/health/database-observability` reports PostgreSQL and an operable
   `pg_stat_statements` view.
5. Run the public production smoke workflow.
6. Configure and manually run the authenticated production smoke workflow, then enable its schedule.
7. Let representative normal traffic accumulate before using the measurements to prioritize Phase 2.

## Verification commands

```bash
cd apps/api
uv run ruff check .
uv run python ../../scripts/check-mypy-baseline.py --baseline mypy-baseline.json
uv run pytest
uv run pip-audit --strict --desc=off --progress-spinner=off
uv run alembic heads
uv run --with pyyaml python ../../scripts/validate-render-blueprint.py ../../render.yaml

cd ../web
npm run lint
npm run typecheck
npm run audit:contracts
npm run build
npm audit --workspaces=false --audit-level=high

cd ../..
node --test scripts/authenticated-smoke.test.mjs
```

## Deferred to later phases

Phase 1 intentionally does not redesign pages, change CRM workflows, split the worker into multiple
services, batch known Leads/Inbox/Dispositions queries, move document bytes out of PostgreSQL, or
reorganize the large backend domain modules. It also does not yet aggregate every processor-owned
retry/review/dead-letter lane into `/health/operations`. Those are candidate Phase 2 and Phase 3
changes, chosen from production measurements rather than code size alone.
