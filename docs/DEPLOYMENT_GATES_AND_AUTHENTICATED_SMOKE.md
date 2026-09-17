# Deployment gates and authenticated smoke checks

## What is enforced in the repository

- GitHub Actions runs the API and web CI jobs for every push to `main` and for pull requests.
- Required CI validates `render.yaml` locally for supported top-level, service, database, and
  environment-variable structure. This catches misspelled keys, malformed references, and duplicate
  names without making deploy eligibility depend on Render's schema endpoint or network availability.
- CI also compares `render.yaml` with Render's live published schema as a non-blocking advisory check.
  A failure there should be investigated, but an upstream outage or schema change cannot strand an
  otherwise valid release. CI runs every web contract test, not only the navigation and underwriting
  subsets.
- The API typecheck is a regression gate over the full `app` and `tests` trees. The repository has
  pre-existing strict-mypy debt recorded in `apps/api/mypy-baseline.json`; any new error fingerprint
  or increase in an existing fingerprint count fails CI. A retired fingerprint or reduced count also
  requires the baseline to be reduced in that same reviewed change, so stale allowance cannot hide a
  later regression. Unrecognized output from a failing mypy run fails closed rather than being treated
  as an empty result.
- The three Git-backed Render services declare `autoDeployTrigger: checksPass` in `render.yaml`.
  After the Blueprint is synced, a commit deploy waits for the repository checks to pass.
- `.github/workflows/production-readiness.yml` checks API health/readiness and public pages every
  15 minutes. Health endpoints must return HTTP 200 with valid JSON and the expected top-level status;
  public pages must return HTTP 200 without redirecting. A failure creates or refreshes one durable
  GitHub issue and recovery closes it. The monitor itself remains a successful/neutral commit check,
  so an unhealthy old deployment cannot prevent Render from deploying its repair.
- `.github/workflows/authenticated-production-smoke.yml` can check real Clerk-authenticated identity,
  leads, conversation, and company disposition data plus the corresponding protected CRM pages every
  hour. It uses its own durable GitHub issue for failures and closes that issue after recovery; like
  the public production monitor, it never fails a deploy-eligible commit check.

The authenticated check is a post-deploy monitor, not a pre-deploy CI test. CI cannot exercise a
commit on the production URLs before Render has deployed it. Its open GitHub issue is a rollback or
repair signal for the already-live release, while the monitor workflow remains non-blocking so the
repair can deploy.

## API typecheck debt policy

Do not update `apps/api/mypy-baseline.json` simply to make CI green. New errors must be fixed. When a
cleanup change removes known errors or reduces a repeated fingerprint count, regenerate the baseline
from `apps/api` and review the baseline reduction in that same change:

```bash
uv run python ../../scripts/check-mypy-baseline.py --baseline mypy-baseline.json --write-baseline
```

The required CI command runs full mypy and compares normalized path, error code, and message counts:

```bash
uv run python ../../scripts/check-mypy-baseline.py --baseline mypy-baseline.json
```

This is an exact debt snapshot and ratchet, not a claim that the API is fully type-clean. CI rejects
both new debt and stale retired allowance. The baseline must trend down to zero.

## One-time GitHub setup

Create a dedicated, active Clerk user that is also mapped to an ordinary Stonegate workspace user.
Give it permission to view leads, conversations, and the company/team disposition desk, but do not
give it owner-only Finance, Marketing, or Settings access merely for this test.

Create a GitHub Actions Environment named `production-smoke`. Restrict its deployment branches to
`main`; do not allow arbitrary branches or tags. Store these as **environment secrets**, not
repository secrets:

| Name | Value |
| --- | --- |
| `PRODUCTION_SMOKE_CLERK_SECRET_KEY` | The production Clerk instance secret key |
| `PRODUCTION_SMOKE_CLERK_USER_ID` | The dedicated smoke user's Clerk ID (`user_...`) |

Then add the environment variable `AUTHENTICATED_SMOKE_ENABLED` with the value `true`. Until that
variable is enabled, the hourly workflow exits successfully without touching production. The
workflow intentionally has no manual-dispatch trigger: GitHub schedules it from the protected
default branch, preventing code from a manually selected ref from receiving the production Clerk
secret. Use the local one-off command below when an immediate check is needed.

The workflow does not store a password or a session token. It uses Clerk's Backend API to create a
short-lived session, creates a fresh token for each check, and revokes the session in a `finally`
block. Secrets and tokens are never printed.

## What the authenticated smoke proves

1. `/api/v1/me` accepts a real production Clerk bearer token and returns a complete mapped workspace
   identity.
2. `/api/v1/leads?limit=1&offset=0` returns the protected lead-list contract.
3. `/api/v1/inbox/conversations` returns the protected conversation-list contract.
4. `/api/v1/dispositions/desk?scope=team` returns the company team scope and the desk's core sections.
5. `/os`, `/os/leads`, `/os/inbox?view=team`, and
   `/os/deals?view=disposition&scope=team` render through Clerk middleware and include a
   page-specific workspace marker, not merely the shared Stonegate OS shell.

With the repeatable Clerk credentials, the harness mints a fresh short-lived token for every API and
page check. Empty production lists are valid; malformed envelopes, malformed first records, a
downgraded disposition scope, or missing core desk sections fail the run.

The smoke identity must also expose the lead, conversation, and Dispositions permissions needed by
those checks. Redirects, authentication outage pages, shell-only fallbacks, non-HTML CRM responses,
incomplete identity payloads, and request timeouts fail the workflow.

## Local or one-off execution

A current Clerk session token can be used for a one-off run without supplying the Clerk secret:

```powershell
$env:API_BASE_URL = "https://api.stonegatehb.com"
$env:WEB_BASE_URL = "https://www.stonegatehb.com"
$env:SMOKE_CLERK_SESSION_TOKEN = "<short-lived-token>"
node scripts/authenticated-smoke.mjs
```

For repeatable automation, use `CLERK_SECRET_KEY` and `SMOKE_CLERK_USER_ID` instead. Never put any of
those values in a tracked file or command example.

The harness itself is covered without network access or real credentials:

```bash
node --test scripts/authenticated-smoke.test.mjs
```

The deployment-gate scripts have local regression coverage for exact HTTP/JSON behavior and mypy
baseline fail-closed behavior:

```bash
python -m unittest discover -s scripts/tests -p "test_*.py"
```

## Render operational caveats

Run the deterministic deployment gate locally from `apps/api` with:

```bash
uv run --with pyyaml python ../../scripts/validate-render-blueprint.py ../../render.yaml
```

To additionally compare against Render's current published schema, opt into the network-dependent
advisory check:

```bash
uv run --with pyyaml --with jsonschema python ../../scripts/validate-render-blueprint.py ../../render.yaml --official
```

- Sync the Blueprint after merging the `render.yaml` change and confirm each web/API/worker service
  shows **After CI Checks Pass** under **Settings > Auto-Deploy**. A repository declaration does not
  prove that an existing dashboard service has already applied it.
- Manual deploys and Blueprint configuration syncs are operator actions; they are not made safe by a
  passing commit check. Use the same CI and smoke acceptance evidence before those actions.
- Render treats successful, neutral, and skipped GitHub checks as passing. Keep the API and Web jobs
  required in GitHub branch protection so a skipped or renamed job cannot silently weaken review.
- Post-deploy monitors must report through their durable issue without failing a commit check. A
  scheduled or manually simulated production failure must never strand the next repair behind
  `checksPass`.
- The scheduled smoke workflows detect a bad release but do not automatically roll it back.
