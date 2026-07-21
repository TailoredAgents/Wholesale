# Phase 1 Reliability Runbook

Last updated: July 21, 2026

## Status

Implementation complete. The first production backup/restore drill and external uptime/alert
destinations remain operator setup tasks because they require separate infrastructure credentials.

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
not included. Point an external uptime monitor at `/ready`; `/health` proves only that the web
process is running.

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
- Failure alert webhook has been exercised with a controlled test endpoint.
- External uptime monitoring watches `/ready`.
- An isolated restore drill has succeeded and been recorded.
- Deployment smoke test passes.
- User deactivation has been verified.
- Local demo seed and simulated SMS/email have been exercised.
