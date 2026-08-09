# Stonegate House-Wholesaling Launch Readiness Audit

- Audit date: August 8, 2026
- Audit target: `TailoredAgents/Wholesale`, local `main` working tree based on commit `5593d1c`
- Decision owner: Stonegate Owner
- Technical owner: Stonegate maintainer
- Audit status: Code review and automated verification; production acceptance remains open

## Verdict

**Stonegate's code is suitable for a tightly controlled first-market acceptance program. It is
not approved for unconditional full live operations.**

That distinction is important:

- A controlled acceptance program may use one Georgia market, one approved Facebook form, low
  lead volume, named staff coverage, manual reconciliation, and human approval at every financial
  or contractual decision.
- A broad launch may not rely on the system until the production deployment, backup restore,
  access revocation, provider delivery, recording, e-signature, buyer-placement, and first-close
  gates in this report have passed with retained evidence.
- Disposition campaign release is currently **simulated**, AI recommendations remain
  **draft-only**, and consequential offer, contract, buyer, and funding decisions remain
  **human-controlled**.

No live SMS, email, call, recording, ad-platform event, property-data request, signature request,
backup restore, or other external acceptance test was performed as part of this audit. Existing
operator anecdotes, screenshots, and prior provider logs are useful context, but this report does
not treat them as current acceptance evidence.

## Decision Summary

| Decision | Status | Meaning |
| --- | --- | --- |
| Merge candidate | Conditional | Final full-tree checks and review must pass first. |
| Deploy to a controlled production acceptance window | Conditional go | Deploy from an identified commit, monitor it, and keep the rollback controls below ready. |
| Turn on low-volume Facebook lead intake | Conditional go | Only after Meta/Zapier ingestion, staff SMS, manual reconciliation, and on-call coverage pass. |
| Record real seller calls | No-go until accepted | Twilio Voice, recording policy, retention, transcription, and note placement must pass together. |
| Send a real purchase agreement | No-go until accepted | Counsel-approved documents, exact offer authority, storage, e-signature, and executed-file evidence must pass. |
| Depend on automated buyer marketing | No-go | The current disposition campaign release records a simulation; it does not send a live buyer blast. |
| Operate at broad volume or without daily supervision | No-go | Restore, revocation, provider, security, and operational gates remain open. |

## Scope And Evidence Standard

### In Scope

- The house-wholesaling path from public/Facebook inquiry through funding handoff.
- FastAPI, PostgreSQL, Alembic, the production worker, Next.js, authentication, and role checks.
- Facebook/Zapier intake, internal lead alerts, property research, call intelligence, calendar,
  underwriting, contract authority, e-signature evidence, buyers, dispositions, and finance
  handoff.
- Retry behavior, queue liveness, provider failure boundaries, dependency advisories, and CI
  coverage.
- Operational recovery: backup/restore, user revocation, rollback, and incident response.

### Out Of Scope

- Legal advice or approval of contracts, outreach, call-recording policy, privacy language, or
  licensing requirements.
- CPA approval of bookkeeping, tax treatment, or the first closed period.
- Provider-account ownership, balances, billing, production credentials, webhook configuration,
  domain records, phone-number registration, or ad-account settings.
- A production backup restore, penetration test, load test, disaster simulation, live provider
  send, or real closing.
- Full land-wholesaling acceptance. Shared platform controls were reviewed, but this verdict is
  specifically for the initial house-wholesaling operation.

### Evidence Rules

An item is considered:

- **Implemented** when the behavior exists in code and has relevant automated coverage.
- **Verified in repository** when the named command passed against the audited working tree.
- **Configured** only when the exact target environment has the required non-secret values and
  secrets.
- **Active** only after a controlled production test proves the real provider path.
- **Accepted** only when the named Stonegate owner records the result, time, identifiers, and any
  exceptions.

A successful HTTP request is not enough by itself. Acceptance evidence must connect the source
event, Stonegate record, worker activity, provider identifier, user-visible result, and audit
history.

## Audited Baseline

| Area | Audited shape |
| --- | --- |
| Repository | Monorepo with `apps/web`, `apps/api`, production worker code in `apps/api/app/worker.py`, scripts, and canonical documentation. |
| Web | Next.js 16 / React 19, Node 20 on Render. |
| API | Python 3.12, FastAPI, SQLAlchemy, Alembic, PostgreSQL. |
| Deployment | Render web, API, worker, PostgreSQL, and Redis-compatible key-value service. |
| Database head in this phase | `0094_esign_send_intents` is the expected single head after applying the audit migrations. |
| Auth | Clerk identity plus local Stonegate user, organization, roles, and permissions. |
| Primary operational truth | PostgreSQL; provider payloads and AI outputs are supporting evidence, not silent replacements. |
| AI boundary | Draft/recommendation by default; call intelligence may populate eligible CRM facts automatically while the transcript-grounded note still requires review. |
| Financial and legal boundary | Offers, concessions, contracts, buyer selection, wires, funding, and posted accounting remain human-controlled. |

## Repository Verification

These results describe code checks only. They do not prove any production provider is configured
or active.

### API

Run from `apps/api`:

```text
uv run ruff check app tests alembic/versions
uv run mypy app tests
uv run pytest -q
uv run pip-audit --strict --desc=off --progress-spinner=off
uv run alembic heads
```

| Check | Final combined-tree result | Release requirement |
| --- | --- | --- |
| Ruff | Passed | Must remain green in CI. |
| MyPy | Passed across 282 source files | Must remain green in CI. |
| Pytest | **535 passed** | No failures remain. |
| Python advisory audit | Passed with no known vulnerabilities after dependency updates | Must pass in CI from the locked dependencies. |
| Alembic heads | Passed with one head: `0094_esign_send_intents` | Must remain a single head. |

### Web

Run from `apps/web`:

```text
npm ci --workspaces=false
npm audit --workspaces=false --audit-level=high
npm run lint
npm run typecheck
npm run audit:ia
npm run audit:underwriting
npm run build
```

| Check | Final combined-tree result | Release requirement |
| --- | --- | --- |
| npm advisory audit | Passed with zero reported vulnerabilities after the `js-yaml` override | Must pass from a clean `npm ci`. |
| ESLint | Passed | Must pass again on the final tree. |
| TypeScript | Passed | Must pass again on the final tree. |
| OS information-architecture contract | Passed, 13 of 13 | Must remain green. |
| Underwriting workspace contract | Passed, 13 of 13 | Must remain green. |
| Production Next build | Passed locally with page-data generation limited to four workers | Must also finish on Render without the prior out-of-memory failure. |

The authenticated OS browser audit was not accepted as evidence in this phase because its harness
did not have a correctly seeded authenticated server and reached sign-in. Rerun it only with the
documented authenticated test fixture; do not count a sign-in redirect as a pass or product
failure.

### CI Improvements In This Phase

The CI workflow now checks Python dependency advisories, web dependency advisories, web lint,
TypeScript, the information-architecture contract, the underwriting contract, and the production
web build in addition to the existing API checks. This closes the previous gap where a Render
build or TypeScript issue could survive local API verification.

## P0 And P1 Findings Addressed In This Phase

For this report, **P0** means a launch-blocking path that could lose or strand business data,
authorize the wrong legal commitment, or expose a public ingress without a reasonable operating
boundary. **P1** means a serious reliability, authorization, or integrity problem that must be
fixed before scale and may be accepted only under explicit controlled-launch supervision.

All items below are changes in the current working tree. They are not deployed merely because the
code exists.

### P0: Resend Events Could Remain Stuck Or Exhaust Worker Memory

Status: **Remediated in code; migration and production acceptance pending.**

- Provider events now carry an attempt count, next-attempt time, processing lease timestamp,
  unique claim token, and bounded terminal dead-letter status.
- Retries use bounded exponential delay; expired processing leases can be reclaimed after a
  worker crash, while UUID claim-token fencing prevents a stale worker from overwriting the new
  owner.
- Recovery distinguishes a genuinely active lease from a stale or dead-lettered event.
- Validated inbound routing is checkpointed before attachment work, and early lifecycle events
  retry within the same bounded budget when they arrive before the outbound CRM record exists.
- Restricted aliases cannot auto-route or be manually assigned into standard-visibility
  conversations.
- Email managers can see failed events in Inbox > Email administration and perform an audited,
  reason-required requeue after correcting the cause.
- Attachment downloads validate the HTTPS Resend CDN host, honor declared size, stream in bounded
  chunks, and reject content that crosses the configured size limit instead of buffering an
  unbounded response.
- Manually resolved routing exceptions reset retry/lease state before reprocessing.

Evidence:

- `apps/api/alembic/versions/0093_resend_event_reliability.py`
- `apps/api/app/services/resend_email_events.py`
- `apps/api/app/services/email_admin.py`
- `apps/api/app/integrations/resend_email.py`
- `apps/web/src/app/os/inbox/email-admin-panel.tsx`
- `apps/api/tests/test_resend_inbound.py`

Residual boundary: dead-letter recovery remains an intentional operator action. Controlled
external mailbox acceptance is not complete, and malware scanning must be configured or separately
controlled before staff trust inbound files.

### P0: A Purchase Agreement Was Not Tied To Current Offer Authority

Status: **Remediated in code; counsel and production e-sign acceptance pending.**

- A house purchase agreement now requires a current approved offer plan and approved underwriting
  version before the package is created.
- Its exact purchase price is tied to the current transaction or latest seller-agreed amount.
- Prices above opening/ceiling authority require the exact authorized or manager-approved
  concession.
- The package stores an authority snapshot and revalidates it before approval, send, provider
  execution, and manual execution. A changed source version or price forces a new package.
- Manual execution requires the exact package document, an executed status, an acceptable scan
  state, an explicit attestation reason, checksum evidence, and an audit event.
- SignWell completion stores the completed document as executed evidence and records its provider
  envelope and scan state.
- SignWell webhook credentials are organization-bound, stale/out-of-order events cannot regress
  state, and completed-document mutations use a savepoint so a failed PDF retrieval leaves no
  false completion state; an identical failed event can then be replayed safely.
- Signature delivery is two-phase: Stonegate durably reserves one active send per package, creates
  an unsent SignWell draft, stores its provider ID, and only then sends that known document.
  Ambiguous create/send outcomes never create another document automatically. Reconciliation can
  repair local package state, and staff can resume a reconciled saved draft from the transaction.
- If the provider-create response is lost before its ID is saved, an authorized operator can attach
  only an unsent SignWell draft whose metadata and recipients match the exact Stonegate transaction
  and package. If the provider account is checked and no document exists, a stale intent can be
  abandoned after a five-minute safety interval with an explicit attestation and audit record.
- Envelope, recipient, package, and transaction transitions are monotonic when an API response
  races a webhook. A shared locked finalizer records provider delivery exactly once, while a
  transaction-row mutex prevents agreements, plans, concessions, or price presentations from racing
  an in-flight or still-signable contract. A manually sent package remains frozen until it is
  executed or staff attests that it was withdrawn from every recipient; terminal provider failures
  release their reservation once without altering a later delivery.
- Forward completion events remain valid even when provider timestamps predate a manual reconcile;
  signer-scoped out-of-order events update the correct recipient without regressing envelope state.
  The public SignWell webhook rejects oversized bodies before JSON parsing.

Evidence:

- `apps/api/app/services/contract_authority.py`
- `apps/api/app/services/contract_authority_locks.py`
- `apps/api/app/services/transactions.py`
- `apps/api/app/services/esign.py`
- `apps/api/alembic/versions/0094_esign_send_intents.py`
- `apps/api/tests/test_transactions.py`
- `apps/api/tests/test_esign_webhook_security.py`

Residual boundary: this is software authority and evidence control, not legal approval of the
agreement or proof that SignWell is active.

### P0: Secretless Zapier Ingress Had Insufficient Abuse Controls

Status: **Risk reduced with compensating controls; provenance risk remains explicitly accepted or
must be resolved before broad volume.**

The Owner intentionally chose a secretless Zapier webhook. The audit did not reverse that product
decision. The endpoint now has:

- an exact configured Facebook Page ID requirement;
- a production-required allowlist of approved Facebook Form IDs;
- a strict request-body size limit;
- a short-window per-client burst limit applied only after schema, Page, and Form validation;
- a database-backed rolling daily accepted-event circuit breaker; and
- provider lead ID duplicate handling before the daily cap is consumed.

Evidence:

- `apps/api/app/routers/zapier_webhooks.py`
- `apps/api/app/services/meta_lead_ads.py`
- `apps/api/app/services/request_rate_limit.py`
- `apps/api/tests/test_zapier_facebook_leads.py`

Residual boundary: Page/Form identifiers are not secrets and do not prove Meta or Zapier created a
request. Before broad ad spend, Stonegate must either record management acceptance of that residual
spoofing risk with strict allowlists/caps/monitoring, or introduce cryptographic provenance or an
authoritative Meta lookup.

### P1: Authentication Could Fail Open Under Environment Drift

Status: **Remediated in code; deployment configuration test pending.**

- `APP_ENV` is normalized and restricted to `local`, `test`, or `production`.
- development-header authentication is off by default and allowed only in local/test when
  explicitly enabled.
- production requires a Clerk issuer, an explicit or issuer-derived JWKS endpoint, a secret key,
  and at least one non-local HTTPS authorized party.
- the Next.js proxy returns a non-cacheable 503 for protected production routes when Clerk is not
  configured instead of passing the route through.

Evidence:

- `apps/api/app/core/config.py`
- `apps/api/app/core/auth.py`
- `apps/api/tests/test_auth_config.py`
- `apps/web/src/proxy.ts`

### P1: Approval Visibility Could Be Mistaken For Decision Authority

Status: **Remediated in code.**

Both `GET /api/v1/approvals` and the Tasks approval feed scope results to request types covered by
the principal's permissions. `audit:view` is the only blanket organization-wide read authority.
Decision authority remains separate and maps fail-closed to the permission required by the request
type: audit visibility alone cannot approve an offer, send a contract, promote an AI capability or
tool call, or authorize managed acquisition follow-up. Unsupported request types cannot be read or
decided through a generic administrator fallback; only explicit `audit:view` may expose them as
read-only audit evidence.

Evidence:

- `apps/api/app/services/approvals.py`
- `apps/api/app/services/tasks.py`
- `apps/api/app/routers/approvals.py`
- `apps/api/tests/test_approval_authorization.py`

### P1: Busy Queues Could Starve Later Operations Or Misreport Worker Readiness

Status: **Remediated in code.**

- Each operation now gets one turn per cycle instead of the first busy queue restarting the cycle.
- A dedicated heartbeat keeps readiness fresh while a long provider operation is running.
- Main-loop progress and the current operation are tracked separately, so a fresh liveness
  heartbeat cannot hide a permanently hung queue.
- The 600-second production stall threshold is separate from the 120-second heartbeat window, so
  a legitimate sequence of bounded provider calls does not create a false alarm.
- The heartbeat preserves degraded state instead of hiding a provider failure.
- Focused tests prove a busy first queue does not block the second queue.

Evidence:

- `apps/api/app/worker.py`
- `apps/api/app/services/operations.py`
- `apps/api/tests/test_worker.py`
- `apps/api/tests/test_operations.py`

### P1: Failed Call Intelligence Could Retry Too Aggressively Or Become Invisible

Status: **Remediated in code; live OpenAI/recording acceptance pending.**

- Failed jobs now wait with bounded exponential backoff.
- Jobs become explicitly exhausted at the configured attempt limit instead of silently blocking
  the queue.
- A successful paid transcription is checkpointed before note generation. If note generation
  fails, the retry reuses the saved transcript instead of downloading and transcribing the call
  again.
- Each automatic/manual retry has an attempt-specific idempotency key enforced by the same unique
  index in PostgreSQL and the test schema.
- An authorized user can requeue an exhausted transcript from the Inbox, and the manual action is
  audited.
- The Inbox distinguishes queued, processing, temporary failure, and exhausted status instead of
  promising an automatic retry forever.

Evidence:

- `apps/api/app/services/call_intelligence.py`
- `apps/api/app/routers/voice.py`
- `apps/web/src/app/os/inbox/inbox-workspace.tsx`
- `apps/api/tests/test_call_intelligence.py`

### P1: Public Write Routes Had Uneven Throttling

Status: **Partially remediated; distributed edge protection remains a scale gate.**

Seller creation, enrichment, and conversion-event routes now use route-specific throttles instead
of leaving enrichment/conversion writes outside the intake boundary; Zapier has its own burst
budget. Production key derivation uses the edge-owned Cloudflare client address and ignores caller
`X-Forwarded-For`, and each limiter hard-bounds its tracked keys at 2,048. The limiter is still
process-local, and the origin must preserve edge ownership of that header, so this is a controlled-
launch guard rather than a complete high-volume WAF or distributed rate-limit system.

### P1: Restricted Inbound Email Could Fall Back To An Unrelated Conversation

Status: **Remediated in code; production mailbox acceptance pending.**

Restricted aliases now constrain exact reply, provider-thread, contact, and fallback matching to
conversations visible through the receiving alias. An inbound message to a restricted address no
longer gains a generic cross-alias fallback merely because the external sender matches.

Evidence: `apps/api/app/services/resend_email_events.py` and
`apps/api/tests/test_resend_inbound.py`.

### P1: SignWell Webhook Scope Needed Tenant And Event-Order Hardening

Status: **Cross-tenant and status-regression risk remediated in code; within-organization payload
reconciliation and production acceptance remain.**

- An organization-specific webhook credential can update only that organization's envelope.
- Ambiguous credentials fail closed, and the legacy global credential fails closed once provider
  envelopes span organizations.
- Duplicate, stale, and out-of-order events remain auditable without moving an envelope backward
  from a later or terminal state.

Residual boundary: the SignWell HMAC contract implemented here covers event type and event time,
not the document ID, signer, or complete event body. Organization binding prevents cross-tenant
mutation, but production reconciliation must still verify the document, intended recipients,
status, and completed PDF against the SignWell API before treating it as execution evidence.

Evidence: `apps/api/app/services/esign.py`, `apps/api/app/routers/esign_webhooks.py`, and
`apps/api/tests/test_esign_webhook_security.py`.

### P1: Dependency And Frontend Verification Gaps

Status: **Remediated in the lockfiles and CI definition.**

- `aiohttp` and `cryptography` were moved to versions that cover the advisories found during the
  audit.
- `js-yaml` is overridden to a patched line.
- `pip-audit`, full npm advisory audit, web lint, web typecheck, and web contract checks are now CI
  requirements.

Evidence:

- `apps/api/pyproject.toml` and `apps/api/uv.lock`
- `apps/web/package.json` and `apps/web/package-lock.json`
- `.github/workflows/ci.yml`

## Current Live, Simulated, And Draft-Only Boundaries

Environment variables can disable an implemented path; therefore this table describes code
capability, not current Render configuration.

| Capability | Boundary now | Required operator behavior |
| --- | --- | --- |
| Facebook lead webhook | Can create live CRM records when enabled; secretless by Owner decision | Restrict Page/Form IDs, cap volume, reconcile Meta/Zapier to CRM every day, and disable intake on anomalies. |
| Staff new-lead SMS | Can send live Twilio SMS; production forbids simulation | Keep at least one manual Inbox/lead-queue fallback and confirm provider delivery, not just worker processing. |
| Property research | Can make paid RentCast/RealEstateAPI requests | Confirm exact subject match and source freshness; never treat an address mismatch or AVM as offer authority. |
| Twilio Voice and recordings | Provider-backed and consequential | Keep disabled until number, routing, recording policy, webhook, retention, and failure paths pass together. |
| AI call notes | Transcript-grounded notes require review; eligible CRM facts may auto-populate with evidence metadata | Compare the note with the recording, correct errors, and approve/reject the note. Never treat AI inference as seller confirmation. |
| AI copilots | Draft-only by default | A human owns every offer, follow-up, contract, buyer, finance, and external action. |
| Underwriting | Saved comp evidence and versioned calculations are implemented | A human verifies the subject, selects defensible closed comps, reviews repairs, and approves the offer plan. Provider AVMs are benchmarks only. |
| Contract package | Approval-gated and tied to current approved offer authority | Do not bypass price/version gates. Use only counsel-approved sources and retain executed evidence. |
| SignWell | Provider adapter implemented | Treat as externally pending until remote and in-person acceptance, completed-document retrieval, replay/failure tests, and within-organization provider reconciliation pass. |
| Resend email | Two-way provider path implemented; queue reliability improved | Keep restricted aliases restricted, monitor retry/dead-letter records, and treat unscanned attachments as unsafe. |
| Disposition campaign | **Simulated release only** | Contact buyers manually and log each interaction. Never tell staff a recorded simulation sent a buyer blast. |
| Buyer selection and POF | Human-controlled; buyer data can record a POF status | Independently inspect current POF evidence. Do not rely on a status field by itself. |
| Finance and funding | Internal records and workflow exist; the OS does not independently validate a wire | Closing attorney, authorized owner, and finance staff verify instructions, settlement statement, receipt, and ledger reconciliation. |
| Marketing conversion delivery | Adapter/mode controlled | Do not claim ad attribution is active until Meta/Google receives and matches a controlled event. |

## Remaining Full-Live Blockers

### Gate 1: Final Build, Migration, And Deployment Proof

- Final API and web verification in this report must pass on the combined tree.
- Alembic must report one head and migrate an isolated production-like database through `0094`.
- Before `0094`, confirm no package already has multiple nonterminal e-sign envelopes; the new
  uniqueness guard intentionally refuses to hide that conflict.
- Render must build without the prior web out-of-memory failure.
- API and worker must start from the same release and compatible environment.
- `/health`, `/ready`, worker liveness plus main-loop progress/current-operation, public pages,
  Clerk sign-in, `/api/v1/me`, and the changed workflows must pass after deployment. Readiness must
  stay healthy during a normal long provider call and report `stalled` only after the configured
  600-second production progress threshold.
- The deployed commit SHA, service deploy IDs, migration result, and timestamps must be retained.

### Gate 2: Backup Restore And Access Revocation

- Restore one real production backup into an isolated database using the runbook below.
- Deactivate one disposable staff account, revoke Clerk access/session, remove grants, reassign its
  work, and prove the old account is denied while history remains attributable.

### Gate 3: Real Lead Intake And Notification

- Prove one Meta test lead travels through Zapier into exactly one Stonegate lead.
- Prove replay of the same provider lead ID does not create a duplicate.
- Prove the configured lead manager receives the sanitized SMS and that Twilio records delivery.
- Prove the lead still appears in the CRM/task queue when SMS is unavailable.
- Reconcile Meta Leads Center, Zap History, Stonegate, worker logs, and Twilio using saved IDs.

### Gate 4: Voice, Recording, Transcription, And Notes

- Management must document the recording/disclosure/retention policy approved for actual
  operations. This audit makes no legal determination.
- Prove inbound and outbound routing, missed-call handling, webhook signatures, recording linkage,
  retention/deletion, transcription, note placement, auto-populated CRM evidence, human review,
  exhausted retry, and provider outage behavior.

### Gate 5: Property And Underwriting Acceptance

- Prove RentCast and RealEstateAPI against a small, known Georgia address set, including a mismatch,
  missing-data case, duplicate refresh, and provider outage.
- Record provider credits/cost, source freshness, subject match, comp selection, ARV, correction,
  and offer-plan approval.
- Confirm a paid-provider failure cannot silently create a second charge without operator evidence;
  keep conservative refresh/cost caps until this is observed in production.

### Gate 6: Contracts, Files, And SignWell

- Counsel must approve the exact house purchase, assignment, and addendum sources used.
- Complete remote-sign and in-person-sign tests with the actual SignWell account and webhook.
- Verify webhook signature, provider document ownership, organization/package binding, duplicate and
  stale event behavior, completed PDF retrieval, checksum, permissions, and audit history.
- Test draft-create and send crash windows, verified draft attachment, empty-intent abandonment,
  one-time terminal failure release, delayed completion, manual-package withdrawal, and authority
  mutation attempts while a package remains signable.
- Reconcile document ID, intended recipients/signers, status, and completed PDF with the provider;
  the webhook HMAC does not bind those body fields within an already authorized organization.
- Configure malware scanning, or have management formally accept and document a limited manual
  handling process. The code can accept `not_configured` for some execution evidence; that state is
  not proof a file is safe.

### Gate 7: Buyers And Dispositions

- Build and validate an initial buyer list with current contact permission, criteria, and independently
  reviewed proof of funds.
- Do not rely on the current simulated campaign as delivery. Use controlled one-to-one outreach and
  log every contact until a real reviewed distribution adapter exists.
- Require human approval of the package, recipients, buyer offer, selected buyer, assignment amount,
  and reconciliation.

### Gate 8: Closing, Funding, And Finance

- Configure the real closing attorney/title contact and independently verify wire instructions.
- Reconcile executed contracts, assignment, settlement statement, cash receipt, fees, commissions,
  and posted journal entries for the first closing.
- Obtain CPA acceptance before relying on the first closed period or tax reporting.

### Gate 9: Residual Security And Scale Controls

- Record the Owner's explicit decision on secretless Zapier provenance, allowed form IDs, daily cap,
  alerting, and disable procedure.
- Confirm the origin accepts `CF-Connecting-IP` only through the trusted Cloudflare path; caller
  `X-Forwarded-For` must remain ignored.
- Add distributed edge/WAF throttling before broad public volume or multiple API instances; the
  hard-bounded in-process limiter is not a shared scale control.
- Run production acceptance for the hardened SignWell tenant binding, replay handling, completed
  document retrieval, and failure recovery.
- Prevent staff from treating inbound files or POF status as verified evidence without a scan or
  authorized human review.
- Test a real least-privilege user for every initial role and all prohibited workspaces.

## Controlled First-Market Operating Envelope

Stonegate may conduct controlled acceptance only within all of these limits:

1. Use one Georgia market and one explicitly allowlisted Facebook form.
2. Start with a low daily lead cap appropriate for staff coverage; do not default to the maximum
   technical limit merely because it exists.
3. Name a primary and backup lead manager for every active ad window.
4. Reconcile Meta/Zapier leads to Stonegate at least daily and immediately while testing.
5. Keep CRM/Inbox checks as the backup notification path; SMS is an alert, not the record of truth.
6. Monitor `/ready`, worker failures, Resend dead letters, transcript exhaustion, provider errors,
   and paid-data usage each operating day.
7. Review every AI note, property match, comp, repair estimate, offer plan, and seller agreement.
8. Do not allow AI autonomy promotion during acceptance. Recommendations remain drafts.
9. Use manual, one-to-one buyer outreach and record it in the disposition case.
10. Independently verify buyer identity, contact permission, POF, title/closing contacts, and wire
    instructions.
11. Do not open or circulate unscanned inbound attachments outside the documented restricted
    process.
12. Stop new ads/intake immediately if leads are missing, duplicated, misrouted, or not assigned.

This envelope permits learning with real operations while keeping every irreversible decision under
named human control. It does not permit unattended or broad-volume operation.

## Provider Acceptance Matrix

Every row below is **not run by this audit**. Record a date, operator, test record, provider ID,
result, screenshots/log links, and cleanup action when each test is performed.

| ID | Provider or boundary | Code status | Controlled acceptance evidence | Full-live requirement | Audit result |
| --- | --- | --- | --- | --- | --- |
| PA-01 | Render web/API/worker | Implemented | Same commit deployed; build/start logs; one migration run; `/health` and `/ready`; fresh worker heartbeat | Stable deploy plus rollback rehearsal | Not run |
| PA-02 | PostgreSQL/Redis | Implemented | DB connectivity, migration head, queue coordination, isolated restore counts | Real restore drill and monitored capacity | Not run |
| PA-03 | Clerk | Implemented; fail-closed hardening in tree | Sign-in, sign-out, expired session, unauthorized party, inactive local user, role denial | Disposable-user revocation test retained | Not run |
| PA-04 | Meta Pixel / Conversions API | Implemented/configurable boundary | One consented controlled browser/server event with shared event ID and expected match/deduplication | Diagnostics clean enough for the approved campaign | Not run |
| PA-05 | Facebook Lead Ads via Zapier | Implemented; secretless with compensating controls | Allowed form accepted, disallowed form rejected, replay deduplicated, cap/429 observed in a safe test | Management risk acceptance or cryptographic provenance; daily reconciliation | Not run |
| PA-06 | Twilio staff lead SMS | Implemented | Worker item, Twilio SID, `Delivered`, correct opted-in recipient, sanitized body, working CRM link | Primary and backup recipients plus failure escalation | Not run |
| PA-07 | Twilio seller SMS | Implemented | Inbound/outbound thread, signature validation, STOP/START, failure and quiet-hours behavior | A2P/number configuration matches actual use | Not run |
| PA-08 | Twilio Voice/recording | Implemented | Inbound/outbound, forwarding, voicemail/missed call, recording SID, linked conversation, deletion | Approved recording/retention policy and failure test | Not run |
| PA-09 | OpenAI transcription/call notes | Implemented | Transcript, structured note, Inbox right rail, lead activity, CRM field evidence, review/reject, exhausted retry | Accuracy sample accepted by Owner; cost and retention monitored | Not run |
| PA-10 | RentCast | Implemented | Exact subject match, closed comp evidence, AVM benchmark, mismatch and missing-data behavior | Accuracy/cost sample and provider failure monitoring | Not run |
| PA-11 | RealEstateAPI | Implemented | Record enrichment, coordinates/media when available, candidate evidence, missing-photo behavior, credit use | Accuracy/cost sample and duplicate-refresh controls | Not run |
| PA-12 | Resend | Implemented; reliability hardened in tree | Outbound/reply, restricted auto/manual routing denial, attachment limit, signature failure, early lifecycle retry, route-checkpoint survival, UUID lease fencing, dead letter, manager reason/audit requeue | Production mailbox/domain plus malware scanner or accepted safe-attachment procedure | Not run |
| PA-13 | SignWell | Implemented; externally pending | Remote and iPad sign, signature validation, duplicates/stale events, completed PDF/checksum and audit | Counsel approval, tenant/document binding, and within-organization API reconciliation accepted | Not run |
| PA-14 | Document storage/scanning | Database/S3 adapters implemented | Private download authorization, deletion/retention, rejected oversize, malware state | Scanner configured or formal limited-risk process | Not run |
| PA-15 | Buyer discovery | No accepted live source established; DealMachine is legacy/disabled | Manually create known buyers and verify contact/criteria/POF evidence | Reliable buyer acquisition process with consent and evidence | Not run |
| PA-16 | Disposition delivery | **Simulated only** | Simulation clearly labeled; no external message; manual outreach logged | Reviewed live delivery adapter before calling it a blast | Not run |
| PA-17 | Marketing offline conversion | Implemented/configurable boundary | One accepted provider event tied to a Stonegate lifecycle event and deduplicated | Attribution diagnostics and privacy policy accepted | Not run |
| PA-18 | Closing/finance | Internal workflow implemented | One controlled transaction reconciles contract, buyer, settlement, receipt, fees, and ledger | Closing attorney and CPA acceptance | Not run |

## Real Facebook Lead Golden-Path Acceptance Checklist

Use one owner-controlled, consented test lead. Do not use arbitrary personal data, do not submit
the same test repeatedly except for the explicit deduplication step, and do not advance into a real
legal or financial commitment merely to complete this checklist.

Create one evidence folder or ticket for the run. Record UTC timestamps and IDs at each step.

### 0. Preflight

- [ ] Record the deployed commit SHA and Render deploy IDs for web, API, and worker.
- [ ] Confirm Alembic has exactly one current head: `0094_esign_send_intents`.
- [ ] Confirm `/health` is `ok`, `/ready` is `ready`, and the worker heartbeat is fresh.
- [ ] Confirm the named Lead Manager and backup are signed in and each has an individual account.
- [ ] Confirm `ZAPIER_FACEBOOK_PAGE_ID` and the exact Form ID allowlist are correct.
- [ ] Set a low controlled daily intake cap and document who may disable intake.
- [ ] Confirm staff SMS recipients have saved E.164 cell numbers and opted in to lead alerts.
- [ ] Open Meta Leads Center, Zap History, Stonegate Leads/Inbox, worker logs, and Twilio logs.

Stop if any preflight item fails.

### 1. Facebook Lead To Stonegate Lead

- [ ] Submit one Meta test lead through the exact live form and record Lead ID, Page ID, Form ID,
  campaign/ad identifiers, and submission time.
- [ ] Confirm Zapier POST succeeds and record its Zap run ID and response.
- [ ] Confirm exactly one Stonegate Lead is created with source `Facebook Lead Ads` and the same
  provider lead ID.
- [ ] Confirm name, phone, email, street, city, state, and seller timeline map to the intended
  fields; mark missing data as missing rather than invented.
- [ ] Confirm a speed-to-lead task, owner, due time, activity entry, and conversation are attached
  to the same record.
- [ ] Replay the same provider lead ID once and confirm no duplicate lead, contact, property,
  conversation, task, or staff alert is created.

Stop and disable Zapier intake if the lead is missing, duplicated, assigned to the wrong
organization/person, or contains data from another submission.

### 2. Address And Property Research

- [ ] Confirm the normalized address represents the seller's actual subject before using paid data.
- [ ] Confirm property research attaches to the existing Property/Lead rather than creating a
  second profile.
- [ ] Record RealEstateAPI and RentCast provider outcomes, timestamps, source IDs, credit/cost
  evidence, and any mismatch warning.
- [ ] Confirm property facts, coordinates/map pin, market signals, available media, value benchmark,
  and candidate comps show their sources and freshness.
- [ ] Confirm a missing photo, parcel fact, AVM, or provider mismatch remains visibly missing or
  blocked rather than being fabricated.
- [ ] Refresh once only when needed and confirm the UI does not silently double-charge or replace
  stronger verified evidence.

Stop underwriting until a human confirms the subject match.

### 3. Staff SMS And Speed To Lead

- [ ] Confirm the worker processes the staff-alert item once.
- [ ] Confirm Twilio creates a Message SID to every intended opted-in staff recipient.
- [ ] Confirm provider status becomes `Delivered`, the body identifies the lead without unnecessary
  sensitive data, and the Stonegate link opens the correct record for the authorized user.
- [ ] Record submission-to-CRM and submission-to-delivered-SMS latency.
- [ ] Confirm the Lead remains visible in the Lead Queue/Inbox and has an urgent task even if the
  SMS test is intentionally failed for the backup-path check.

Stop ads if neither the SMS nor the supervised CRM fallback is reliable.

### 4. Call, Recording, And Conversation History

- [ ] Place or receive the call using the configured Stonegate acquisitions number and record the
  Twilio Call SID.
- [ ] Confirm direction, participants, owner, timestamps, duration, and result appear on the same
  Inbox thread and Lead timeline.
- [ ] Confirm the approved recording policy is followed and the recording SID/file links to this
  call only.
- [ ] Test missed/no-answer handling separately; confirm no duplicate call intent or task.
- [ ] Confirm an unauthorized user cannot access the recording or transcript.

Stop recording if policy, routing, signature validation, access, or retention behavior is unclear.

### 5. Transcript, Notes, And CRM Fields

- [ ] Confirm call intelligence moves through queued, processing, and `needs_review`/completed
  without remaining stuck.
- [ ] Confirm the transcript is grounded in the correct recording and speaker/time segments are
  usable.
- [ ] Confirm the structured summary and qualification notes appear in the Inbox right-side call
  panel and the Lead's recent activity/timeline.
- [ ] Confirm eligible CRM fields auto-populated from the call carry evidence metadata and do not
  overwrite stronger human-confirmed facts without a visible conflict.
- [ ] Compare motivation, timeline, condition, occupancy, asking price, mortgage, next action, and
  appointment details to the actual call.
- [ ] Correct any error, approve or reject the note, and confirm the decision/audit history remains.
- [ ] Exercise one safe failed/exhausted job and confirm the authorized **Retry call intelligence**
  action requeues it once provider health is restored.

Do not let any AI summary become the sole basis for an offer or contract.

### 6. Appointment And Walkthrough

- [ ] Create the correct appointment type from the Lead/Calendar with owner, location or phone,
  timezone, start/end, travel buffer, and notes.
- [ ] Confirm its type has the expected color and the calendar blocks the correct time.
- [ ] Create a controlled overlapping appointment and confirm the conflict warning appears; do not
  override it without a documented reason and authorized decision.
- [ ] Confirm the appointment appears on the Lead, assignee calendar, dispatch/appointment view,
  and recent activity.
- [ ] During the walkthrough, capture seller-confirmed occupancy/condition, room/area repair scope,
  access/title/safety concerns, photos, and outcome on the existing Lead/Property.

### 7. Underwriting And Offer Authority

- [ ] Create a versioned underwriting snapshot only after the subject is confirmed.
- [ ] Review closed-sale comps for distance, recency, property type, living area, beds/baths, year,
  condition, and transfer eligibility; reject ineligible or misleading transfers.
- [ ] Confirm Stonegate ARV/support range comes from saved selected comp evidence. Treat RentCast or
  another AVM only as a benchmark.
- [ ] Review repairs from the actual walkthrough; replace system ranges with stronger bids/evidence
  when available.
- [ ] Confirm assignment fee, holding/closing costs, target margin, and MAO/offer calculations.
- [ ] Approve the exact underwriting version and offer plan with opening, target, stretch, and
  seller-ceiling authority.
- [ ] If price moves above authorized limits, record the exact concession and manager approval.

Stop before contract drafting if the subject, comps, repair scope, approved version, or exact seller
agreement is missing.

### 8. Contract And Execution Evidence

- [ ] Confirm the transaction purchase price equals the latest seller-agreed/current approved
  amount.
- [ ] Create a purchase package and confirm it captures the exact offer-authority snapshot.
- [ ] Change a source price/version in a controlled non-production case and confirm the stale package
  cannot be approved, sent, or executed.
- [ ] Use only the counsel-approved current template and obtain the required human approval.
- [ ] For SignWell acceptance, confirm the exact approved package is sent to the intended recipients
  and duplicate send is blocked.
- [ ] Simulate a lost draft-create response. Confirm staff can attach only the matching unsent draft,
  or abandon the intent only after verifying no provider document exists and waiting five minutes.
- [ ] Confirm new seller authority is blocked while either a SignWell or manually delivered purchase
  agreement remains signable. For a manual delivery, test the audited **Withdraw sent package** flow.
- [ ] Confirm completed provider execution retrieves the exact PDF, stores checksum/provider
  envelope evidence, and marks the correct package/document executed.
- [ ] For a manual execution path, require the exact executed document and a meaningful human
  attestation; verify the audit event.
- [ ] Confirm the Lead/Deal becomes under contract only after valid execution evidence.

### 9. Buyer Placement And Disposition

- [ ] Create or select buyers with current criteria, contact permission, relationship notes, and
  independently reviewed, unexpired POF evidence.
- [ ] Confirm the disposition package uses the executed contract, current property/valuation/repair
  facts, assignment terms, access instructions, and approved photos.
- [ ] Have a human approve the package and recipient list.
- [ ] Record that the built-in campaign release is simulated; perform controlled manual one-to-one
  outreach and log each contact, response, and opt-out.
- [ ] Record every buyer offer, deposit/earnest terms, proof, contingencies, and reliability notes.
- [ ] Have an authorized human select the buyer and document why; do not let rank or AI decide.
- [ ] Prepare/execute the assignment using the same document, signature, checksum, and audit
  standards as the purchase agreement.

### 10. Closing, Funding, And Reconciliation

- [ ] Confirm closing attorney/title contact and wire instructions through an independently known
  channel; never rely on an inbound email change alone.
- [ ] Confirm purchase contract, assignment, title/closing checklist, settlement statement, buyer
  funds, earnest/deposit, and scheduled closing refer to the same property and parties.
- [ ] Record actual purchase/assignment amounts, fees, commissions, and expected net.
- [ ] Do not mark funded from a promise, screenshot, or provider draft; retain authoritative receipt
  or closing evidence.
- [ ] Reconcile the transaction and posted journal entries to the final settlement statement and
  received funds.
- [ ] Have transaction staff/Owner sign off; include CPA review for the first real close.

### 11. End-To-End Reconciliation

- [ ] The Meta Lead ID, Zap run, Stonegate Lead/Property/Conversation, Twilio Message/Call SID,
  recording/transcript, appointment, underwriting version, approval IDs, contract package/envelope,
  buyer/disposition case, transaction, and finance entries form one traceable chain.
- [ ] No duplicate lead, property, task, conversation, contract, buyer offer, or provider send exists.
- [ ] All corrections and human decisions remain in activity/audit history.
- [ ] Provider usage/cost, processing latency, failures, and manual workarounds are recorded.
- [ ] The Owner records pass/fail and either authorizes the next controlled run or opens remediation.

## Backup And Restore Drill Runbook

- Owner: Stonegate Owner plus technical maintainer
- Frequency: before controlled broad launch, after material schema changes, and on the approved
  recurring schedule
- Rule: never restore a drill into production

### Prepare

1. Choose a maintenance window and record the production release SHA and current Alembic head.
2. Populate `DATABASE_URL` in the process environment through the approved secret-injection
   mechanism. Do not paste it into chat, tickets, screenshots, shell history, or this repository.
3. Create or identify an encrypted, access-controlled backup destination outside the repository
   and normal OneDrive working folder.
4. Provision a fresh isolated PostgreSQL database whose URL/name contains `test`, `restore`, or
   `verify`. It must not be reachable by production services.
5. Confirm PostgreSQL client tools are the same major version or compatible with production.

### Create And Protect The Backup

From the repository root in a Bash-capable environment where `DATABASE_URL` and `BACKUP_DIR` have
already been populated without echoing them or entering them in shell history:

```bash
npm run db:backup
sha256sum "$BACKUP_DIR"/stonegate-*.dump
```

Record the UTC time, file name, byte size, SHA-256, source database identity, Alembic head, operator,
and secure storage location. Restrict permissions and remove any unencrypted working copy after the
verified encrypted copy is retained.

### Restore Into The Isolated Database

Populate `RESTORE_DATABASE_URL` through the same history-safe mechanism and set the non-secret
confirmation `ALLOW_RESTORE_TEST=true`. Then run:

```bash
npm run db:restore-verify -- /absolute/path/to/stonegate-YYYYMMDDTHHMMSSZ.dump
```

The guard refuses the production URL and requires an isolated-looking target. The script restores
with `pg_restore` and checks the migration version plus organization and lead counts.

### Verify

- [ ] The restore command completes without ignored errors.
- [ ] The restored Alembic version equals the source version.
- [ ] Organization, user, lead, conversation, transaction, buyer, document, and audit-event counts
  are plausible compared with the source snapshot.
- [ ] Select a small list of pre-recorded non-secret IDs and confirm their relationships open in an
  isolated application instance.
- [ ] Confirm protected documents remain private and checksums/metadata are present.
- [ ] Confirm the restored database was never connected to live webhooks, workers, SMS, email,
  e-signature, or property providers.
- [ ] Record duration, result, discrepancies, operator, reviewer, and evidence location.

Destroy the isolated database only after evidence is reviewed. Destruction must follow the
provider's approved recoverable process and exact target verification.

### Restore Drill Pass Criteria

- A real backup restores without modifying production.
- Core counts and sampled relationships are correct.
- The documented recovery time is acceptable to the Owner.
- The encrypted backup and restore evidence can be found by someone other than the person who ran
  the drill.

## Access Revocation Drill Runbook

Use a disposable staff account with realistic least-privilege assignments. Never use the only
Owner account.

### Prepare

1. Record the test user's Clerk ID/email, Stonegate user ID, role, teams, mailbox grants, sender
   aliases, operating seat, active session, owned leads/conversations/tasks, and appointments.
2. Assign at least one disposable lead, conversation, task, and appointment so reassignment can be
   proven.
3. Sign in as the test user in a separate browser and confirm the expected allowed and denied areas.

### Revoke

1. Reassign leads, conversations, open tasks, appointments, watchers, approvals, and operating-seat
   coverage to the named backup.
2. In **Settings > People & Access**, deactivate the Stonegate user. Preserve the account and
   history rather than deleting a user with operational records.
3. Revoke/disable the person's Clerk account and active sessions.
4. Remove sender grants, shared/restricted mailbox access, team membership, coverage, calling-line
   access, and external provider access.
5. Rotate any shared secret the person actually knew. The preferred design is that no staff member
   knows production service secrets.

### Prove

- [ ] Refresh the existing user session and confirm protected OS access is denied.
- [ ] Confirm a direct protected API request is denied with 401/403 and cannot use the development
  identity header.
- [ ] Confirm a new sign-in cannot regain Stonegate access.
- [ ] Confirm reassigned work appears for the backup and no active item remains silently ownerless.
- [ ] Confirm restricted mail, recordings, contracts, buyer records, exports, finance, and AI
  controls are no longer accessible.
- [ ] Confirm past activity still attributes actions to the deactivated user.
- [ ] Record revocation start/end time, operator, reviewer, test account, result, and exceptions.

### Revocation Pass Criteria

Access is denied immediately enough for Stonegate's approved policy, all open work has a named
owner, external access/grants are removed, and historical attribution remains intact.

## Deployment And Smoke Runbook

1. Identify the exact release commit and confirm the working tree used to create it passed every
   final check in this report.
2. Back up production before the migration window.
3. Before applying `0094`, run this read-only preflight and stop if it returns any row:

   ```sql
   SELECT contract_package_id, COUNT(*) AS active_envelopes
   FROM esign_envelopes
   WHERE status NOT IN ('completed', 'declined', 'expired', 'cancelled', 'error')
   GROUP BY contract_package_id
   HAVING COUNT(*) > 1;
   ```

4. Deploy API/migration first according to the Render Blueprint, then worker and web from the same
   release. Watch for more than one migration runner.
5. Confirm migrations through `0094_esign_send_intents` apply once and no second Alembic head exists.
6. Run from a controlled environment:

```bash
export API_BASE_URL='https://api.stonegatehb.com'
export WEB_BASE_URL='https://www.stonegatehb.com'
npm run ops:smoke
```

7. Confirm Clerk sign-in and one protected `/api/v1/me` request using an authorized account.
8. Confirm worker logs show a fresh heartbeat and `/ready` remains ready during a longer safe job.
9. Exercise only the changed non-consequential paths first. Run provider acceptance one row at a
   time, not in parallel.
10. Record the deployment, smoke result, and go/rollback decision.

## Incident And Rollback Guidance

### Treat As A Launch-Blocking Incident

- A Facebook lead is missing, duplicated, routed to the wrong organization/user, or contains
  another seller's data.
- A staff alert claims success without a Stonegate Lead, or sends sensitive data to the wrong
  person.
- A provider job repeats paid work or an external send unexpectedly.
- A recording, email, document, POF file, or financial record is visible to an unauthorized user.
- A contract price/package differs from the approved offer authority or seller agreement.
- A SignWell event completes the wrong package or a disposition action is represented as sent when
  it was only simulated.
- A backup cannot be restored, a departing user retains access, `/ready` is degraded, or the worker
  is not processing critical queues.

### First 15 Minutes

1. Stop new ad spend or form delivery when intake integrity is in question.
2. Disable the smallest affected provider path using explicit controls; examples include
   `ZAPIER_FACEBOOK_LEADS_ENABLED=false`, `STAFF_LEAD_ALERT_SMS_MODE=disabled`,
   `TWILIO_SMS_ENABLED=false`, `TWILIO_VOICE_ENABLED=false`,
   `TWILIO_VOICE_RECORDING_ENABLED=false`, `CALL_TRANSCRIPTION_ENABLED=false`,
   `EMAIL_ENABLED=false`, `EMAIL_SYNC_ENABLED=false`, `ESIGN_PROVIDER=disabled`,
   `PROPERTY_INTELLIGENCE_AUTO_RESEARCH_ENABLED=false`, or
   `MARKETING_CONVERSION_MODE=disabled`.
3. If a runaway worker is causing harm, pause the worker service. Do not delete queue rows or clear
   evidence.
4. Preserve the release SHA, Render deploy IDs, UTC timeline, request/provider IDs, sanitized logs,
   affected record IDs, actor, and screenshots. Never copy secrets into the incident record.
5. Name an incident owner and a business owner. Protect sellers first, then restore operation.

Production intentionally rejects several `simulate` modes. Do not try to turn a live production
provider into simulation during an incident; disable the affected path.

### Diagnose And Contain

- Reconcile the external provider event to the normalized Stonegate record before replaying
  anything.
- Use provider IDs and idempotency keys to determine whether the outside action occurred.
- Quarantine or restrict affected files/data. Revoke compromised accounts or tokens through the
  provider and rotate only the exact exposed credentials.
- Tell staff which channel is authoritative during the incident and assign manual lead coverage.
- If seller/buyer communication was wrong, have an authorized person approve the correction.

### Rollback Decision

- Prefer a tested forward fix when database changes are additive and data has already been written.
- A Render application rollback may use the last known-good commit only after confirming it is
  compatible with the current database schema and provider payloads.
- Migrations `0093` and `0094` are additive, but that is not permission to run an unreviewed production
  downgrade. Do not run `alembic downgrade`, restore over production, or drop columns during the
  incident without a specific reviewed recovery plan and verified backup.
- Never roll back a contract, signature, SMS, email, or provider-side event by deleting the local
  record. Preserve the event and add a corrective/audit record.

### Recover

1. Deploy the reviewed fix or known-compatible release.
2. Confirm health, readiness, auth, and worker liveness.
3. Re-enable one provider boundary at a time.
4. Replay only verified idempotent events. Manually requeue an exhausted transcript or resolve an
   email routing exception only after confirming the provider is healthy and the target is exact.
5. Reconcile every event that occurred during the incident and notify affected parties when
   required by management/professional advice.
6. Record root cause, affected records, financial/provider cost, correction, prevention, owner, and
   follow-up due dates.

## Launch Sign-Off Record

Do not change the verdict by editing prose alone. Complete this table and link the retained
evidence.

| Gate | Owner | Evidence | Result/date |
| --- | --- | --- | --- |
| Final API/web/CI/build | Technical maintainer |  | Open |
| Migration and Render smoke | Technical maintainer |  | Open |
| Production backup restore | Owner + maintainer |  | Open |
| Staff access revocation | Owner + maintainer |  | Open |
| Facebook/Zapier lead and dedupe | Marketing + Lead Manager |  | Open |
| Staff SMS and fallback | Lead Manager |  | Open |
| Voice/recording/call notes | Acquisitions + Owner |  | Open |
| Property/underwriting sample | Acquisitions + Owner |  | Open |
| Counsel-approved contract/SignWell | Owner + counsel + transaction staff |  | Open |
| Buyer/POF/manual disposition | Dispositions + Owner |  | Open |
| First close/finance reconciliation | Owner + transaction staff + CPA |  | Open |
| Residual security risk acceptance | Owner + maintainer |  | Open |

## Final Go/No-Go Decision

**Current decision: conditional GO for controlled acceptance; NO-GO for unconditional full live
operations.**

The working tree materially improves queue durability, worker fairness, authentication fail-closed
behavior, permissioned approvals, call-intelligence recovery, public ingress controls, restricted
mail routing, dependency hygiene, contract price authority, and execution evidence. Those are
meaningful launch-readiness improvements.

The remaining gates are not paperwork. They prove that the real provider accounts, production
deployment, staff roles, legal documents, phone/recording path, property evidence, buyer process,
backups, revocation, and funding controls work together. Stonegate should begin with the controlled
envelope above, keep every consequential decision under named human authority, and expand only as
each gate is passed and documented.
