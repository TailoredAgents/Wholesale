# Phase 1 Reliability Runbook

Last updated: July 24, 2026

## Status

Implementation is pushed to `main`. Scheduled external readiness monitoring is active, its
controlled failure reached the repository owner's GitHub notifications, the production backup was
restored into an isolated verification database, and live access revocation passed. The
worker-specific webhook destination and Sentry project/DSN activation are intentionally deferred
by owner direction so F2 can proceed. The implemented integrations remain available for later
activation.

Credential rotation, MFA rollout, and secret-security remediation are excluded from this F1
execution by owner direction. They remain known risks and are not represented as complete.

## Verification Record

| Date | Check | Result | Notes |
| --- | --- | --- | --- |
| July 21, 2026 | Live deployment smoke test | Passed | API `/health`, API `/ready`, website, cash-offer form, privacy policy, and terms returned successfully |
| July 21, 2026 | Live readiness | Passed | Database reported `ready`; worker heartbeat reported `healthy` |
| July 21, 2026 | Automated access-revocation coverage | Passed previously | The unchanged API test suite covers deactivated local and mapped Clerk users; the live non-owner exercise remains pending |
| July 24, 2026 | Live branded deployment smoke test | Passed | API `/health` and `/ready`, branded website, cash-offer form, privacy policy, and terms returned successfully |
| July 24, 2026 | Live Render fallback smoke test | Passed | API `/health` and `/ready` plus all required Render web routes returned successfully |
| July 24, 2026 | Synthetic isolated restore drill | Passed | PostgreSQL custom backup restored into `stonegate_f1_restore_test`; migration marker, organization query, and lead query succeeded |
| July 24, 2026 | Monitoring build verification | Passed | Next.js 16.2.11 production build, ESLint, focused Python Ruff checks, shell syntax, YAML parsing, and controlled alert delivery passed |
| July 24, 2026 | Scheduled production readiness | Passed | Manual run checked live API readiness, worker heartbeat, and required public pages successfully |
| July 24, 2026 | Owner readiness-alert path | Passed | A controlled post-smoke failure created an unread `ci_activity` notification for the repository owner |
| July 24, 2026 | API regression suite | Passed | Strict Ruff and mypy checks passed; all 136 API tests passed |
| July 24, 2026 | Production backup restore | Passed | Production PostgreSQL 18 custom backup restored into isolated local database `stonegate_prod_restore_verify_20260724`; migration `0052`, organization, and lead checks passed |
| July 24, 2026 | Live access revocation | Passed | Disposable `prospecting_caller` received `200` from `/api/v1/me`, then the same valid Clerk session received `401` immediately after Stonegate deactivation |

Owner-deferred items:

- Worker-specific alert delivery requires an owner-controlled webhook destination on
  `oakwell-worker`.
- Sentry reporting requires one web project DSN and one Python project DSN, or one shared project
  DSN if Stonegate prefers combined server reporting.
- Live access revocation requires a disposable non-owner Clerk user and an authenticated test
  session.

## Local Demo Workspace

Set `APP_ENV=local` and `COMMUNICATION_PROVIDER_MODE=simulate`, migrate, then seed:

```bash
npm run db:migrate
npm run seed:demo -- --owner-email owner@example.test --owner-name "Demo Owner"
```

The command is repeatable. It creates only reserved `example.test` addresses, synthetic 555
numbers, demo users, four leads at different stages, an appointment, underwriting, a transaction,
buyers, timeline activity, consent evidence, and a shared simulated mailbox. Re-running it reuses
the records rather than duplicating them.

`COMMUNICATION_PROVIDER_MODE=simulate` writes outbound SMS and email through the real dispatch and
conversation paths but never contacts Twilio or Google. Application startup rejects this mode in
production.

## Worker Health And Failures

The communications worker updates `worker_heartbeats` and isolates transcription, recording
retention, and email synchronization failures so one provider cannot stop every operation.
Repeated failures are grouped in `operational_failures`; a later successful pass resolves the open
group.

Production API readiness requires a fresh worker heartbeat. Use:

```bash
curl --fail https://oakwell-api.onrender.com/ready
```

Set `OPERATIONS_ALERT_WEBHOOK_URL` only on `oakwell-worker`. The worker sends a minimal JSON event
at `OPERATIONS_ALERT_AFTER_FAILURES` and subsequent threshold multiples. Raw exception messages are
not included. Exercise the destination without causing a worker failure:

```bash
OPERATIONS_ALERT_WEBHOOK_URL='https://owner-controlled-endpoint.example' npm run ops:alert-test
```

The scheduled `.github/workflows/production-readiness.yml` workflow checks `/ready` and the public
pages every 15 minutes. GitHub Actions failure notifications must be enabled for the repository
owner. `/health` proves only that the web process is running.

## Error Monitoring

Sentry is the selected production error-monitoring provider. Reporting is disabled when no DSN is
configured. The integration covers:

- Next.js browser, server, edge, request, and global-render errors.
- FastAPI unhandled errors.
- Worker operation exceptions.
- Environment, release, and service tags.

Default PII collection, request-body capture, and Python local-variable capture are disabled.
Configure `SENTRY_DSN` on all three services and `NEXT_PUBLIC_SENTRY_DSN` on `oakwell-web`.
Use `SENTRY_ENVIRONMENT=production` and start with `SENTRY_TRACES_SAMPLE_RATE=0.05`.

## Backup

Run from a trusted workstation with PostgreSQL client tools installed:

```bash
DATABASE_URL='postgresql://...' npm run db:backup
```

Backups use PostgreSQL custom format, omit ownership, receive restrictive local permissions, and
are written under ignored `.backups/` by default. Store production backups in an encrypted,
access-controlled location after creation.

## Restore Drill

Create an empty, isolated PostgreSQL database whose URL includes `test`, `restore`, or `verify`.
Never use the production URL. Then run:

```bash
RESTORE_DATABASE_URL='postgresql://.../stonegate_restore_test' \
ALLOW_RESTORE_TEST=true \
npm run db:restore-verify -- .backups/stonegate-YYYYMMDDTHHMMSSZ.dump
```

The script refuses an identical `DATABASE_URL`, restores with `--clean --if-exists`, and verifies
the migration head plus organization and lead queries. Record the date, backup age, duration,
migration revision, and operator after every drill. Perform the drill before broad team onboarding
and then at least quarterly.

## Deployment Smoke Test

After each Render deployment:

```bash
API_BASE_URL='https://oakwell-api.onrender.com' \
WEB_BASE_URL='https://oakwell-web.onrender.com' \
npm run ops:smoke
```

This read-only check verifies API health/readiness and the homepage, cash-offer form, privacy
policy, and terms pages. It does not submit a lead or send communications. Complete authenticated
CRM, public intake, and provider acceptance checks separately when a release changes those paths.

## Access Revocation

Deactivating a Stonegate `users` record causes both local development authentication and mapped
Clerk authentication to reject that user. Automated coverage verifies the local path. During each
production access review, deactivate a non-owner test user, confirm API access returns `401`, then
reactivate only if the account remains authorized.

## Phase Exit Checklist

- Migration `0024_operational_reliability` is deployed.
- `/ready` reports database and worker as ready.
- GitHub readiness alerts are verified; the optional worker-specific webhook is **owner-deferred**.
- Scheduled external uptime monitoring watches `/ready`, and its owner notification path has been
  exercised.
- A production backup has restored successfully into an isolated verification database.
- Deployment smoke test passes.
- User deactivation has automated coverage and a passing live disposable-user exercise.
- Local demo seed and simulated SMS/email have been exercised.
- Sentry receives controlled web, API, and worker test errors. **Owner-deferred until a Sentry
  project and DSNs are supplied.**

## Residual Dependency Finding

Next.js was updated from 16.2.10 to the stable 16.2.11 patch release. The production dependency
audit still reports upstream `postcss` and `sharp` advisories for which npm provides no stable fix.
Do not force a preview Next.js release into production solely to suppress the report. Recheck the
audit when the next stable Next.js patch is available.
