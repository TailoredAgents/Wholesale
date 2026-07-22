# Testing

Last updated: July 22, 2026

## Required Checks

```bash
npm run build:web
npm run lint:api
npm run typecheck:api
npm run test:api
```

Also run:

- Worker import/start smoke test.
- `git diff --check`.
- Tracked-file secret scan.
- Alembic upgrade from the previous production revision.
- Live `/health` and `/ready` checks after deployment.

## Coverage Areas

- Authentication, permission, and organization scope.
- Bootstrap and migration idempotency.
- Public intake, duplicate matching, consent, and attribution.
- CSV dialect parsing, reusable mappings, row validation, prospect normalization, duplicate
  detection, DNC/company suppression evidence, import replay protection, costs, and callable-only
  prospect batches.
- Approved caller-script versioning, one-active-prospect enforcement, immutable attempts, guided
  outcome validation, callbacks, DNC suppression, warm lead conversion, handoff correction and
  acceptance, VA scope, attribution, appointments, and scorecards.
- Lead, task, appointment, underwriting, transaction, buyer, finance, and approval writes.
- Shared inbox assignment, watchers, VA handoff, and unread state.
- SMS consent, suppression, STOP/START, signatures, and provider idempotency.
- Voice intents, routing, statuses, signatures, recordings, retention, and deletion.
- Call transcription review, evidence, quality telemetry, and approval gates.
- Gmail OAuth state, encryption, threading, synchronization, attachments, and role scope.
- Underwriting calculations, comp filtering, confidence, report access, and nullable recommendations.
- AI tool permissions, run logs, approval behavior, and cost calculations.

## Provider Acceptance Tests

Never run live provider tests against an uncontrolled seller.

Use company-controlled accounts and numbers to test:

- SMS outbound, delivery, inbound, STOP, START, HELP, failure, and duplicate callbacks.
- Voice browser registration, outbound, inbound, no-answer, missed-call task, and webhook signature.
- Recording disclosure, playback permissions, transcript, review, retention, and deletion.
- Gmail send, reply, thread, sync, signature, template, and attachment.
- Custom-domain Clerk login, CORS, OAuth redirect, and public legal links.

## Current Local Tooling Issue

On this Mac, broad Node and Python commands intermittently stall while reading installed
dependencies before diagnostics appear. Do not interpret a dependency-load stall as a passing or
failing test.

Current fallback:

- Bound or stop stalled commands.
- Run focused syntax and targeted tests when possible.
- Rely on Render's successful production compile for deployed web changes.
- Verify changed public content over HTTPS.
- Record any unrun checks in the completion note.

Resolving the local filesystem/toolchain issue is part of Roadmap Phase 2.
