# Architecture and Performance Audit - Phase 2

Status: audit complete; no production behavior, database schema, provider configuration, or deployment
configuration was changed in this phase.

## Decision

Stonegate does **not** need a rewrite, a microservice conversion, or a new system that someone has to
manually supervise. The application is structurally recoverable and has strong automated tests around
many business workflows.

The performance problem is concentrated in a small number of shared paths:

1. every authenticated API request recreates the Clerk JWKS client and can perform an external key
   lookup;
2. Leads and Inbox list endpoints fetch rows once and then perform several database reads per row;
3. broad "workspace" endpoints return much more data than the visible page needs;
4. several collections are silently capped in the API and then treated by the browser as complete;
5. the Inbox repeatedly reloads complete list and detail payloads;
6. the worker records far more database telemetry than an idle worker needs; and
7. Dispositions loads organization-wide buyer/package data in several different paths.

Those are bounded, incremental problems. Fixing them is safer and more valuable than reorganizing the
entire repository.

## Non-negotiable operating constraint

The owner and staff should not become system operators. The implementation that follows this audit
must measure and protect itself automatically:

- CI should prevent query-count and contract regressions.
- Runtime telemetry should identify slow routes and old queues automatically.
- A failure should create one actionable alert, not a dashboard that needs daily watching.
- Normal use should not require cache clearing, queue maintenance, manual retries, or performance
  checklists.
- Each change must preserve the live workflow and have a bounded rollback path.

## Scope and evidence

This phase inspected the complete tracked repository, the current production-mode web build artifact,
API query construction, list serializers, client loading behavior, background processing, deployment
configuration, and the Phase 1 observability implementation.

Repository baseline at commit `c24dfb1`:

| Area | Current size |
| --- | ---: |
| Tracked files | 1,048 |
| API files | 566 |
| Web files | 387 |
| API application Python | 249 files / 200,789 lines |
| Web `src/app` TypeScript/TSX | 234 files / 82,789 lines |
| API routes | 519 across 34 routers |
| API service modules | 128 |
| Database migrations | 134 |
| API tests | 162 files / 1,348 test functions |
| Web contract scripts | 40 scripts / 341 contracts |

Large files and frequent-change hotspots are maintenance evidence, not proof of runtime slowness. The
most important examples are `models/foundation.py` (10,200 lines), `web/src/app/lib/api.ts` (more than
8,000 lines), `services/leads.py` (6,667 lines), and `inbox-workspace.tsx` (more than 3,400 lines).
They should be split only while fixing a proven hot path, not as a standalone cleanup project.

This audit did **not** have access to production row counts, PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)`,
table/TOAST sizes, Render CPU/memory graphs, or a statistically complete route trace. Ordinary successful
request logs are sampled one in twenty, while slow/high-query/failing requests are retained. Therefore:

- code-path fan-out, caps, ordering bugs, and repeated database calls are confirmed;
- exact production latency contribution and capacity limits are not claimed without measurements; and
- the Phase 1 sampled log stream must not be used to calculate a naive production p95.

## Current architecture

```text
Browser / Next.js server components
        |
        | authenticated JSON reads and mutations
        v
FastAPI routers -> domain services -> SQLAlchemy -> PostgreSQL
        |                                  |
        |                                  +-- documents currently stored in DB
        |
        +-- Twilio, Clerk, OpenAI, ElevenLabs, Resend,
            BatchDialer, DealMachine, and other provider adapters

One background worker process
        |
        +-- 27 queue/provider/maintenance operations, sequentially checked
        +-- PostgreSQL coordination and durable failure state
        +-- Redis-backed capabilities where configured
```

The repository is a modular monolith. That is the right deployment shape for the current company. Its
main weakness is not the monolith itself; it is that some read models cross too many domain boundaries
and some serializers perform database access one record at a time.

## Ranked findings

Confidence labels:

- **Confirmed**: directly established by the current code or build artifact.
- **Strong candidate**: the expensive behavior is confirmed, but live impact needs production metrics.
- **Future risk**: safe at today's apparent volume but will become incorrect or expensive as data grows.

### P0 - Fix first

#### 1. Authentication can perform a Clerk JWKS lookup for every API request

**Confidence:** Confirmed behavior; production latency contribution is a strong candidate.

`get_current_principal` verifies every bearer request in `apps/api/app/core/auth.py:37-46`.
`verify_clerk_authorization_header` creates a new `PyJWKClient` inline at
`apps/api/app/core/auth.py:91-108`. The key cache belongs to that client instance, so recreating the
client prevents reuse across requests.

This puts a third-party network call in the critical path of nearly every API request. A single page can
make several authenticated reads, so network delay or a short Clerk/JWKS interruption can fan out into
slow pages or 5xx responses. This is a credible contributor to earlier concurrency-sensitive behavior,
but this audit cannot retrospectively prove it caused a specific incident.

**Safe correction:** keep one process-lifetime JWKS client per configured endpoint, retain normal cache
expiry and unknown-key refresh, and preserve all current issuer, audience, authorized-party, and
signature checks. Add a test proving repeated token verification fetches the key set once rather than
once per request.

#### 2. Leads performs database work per row and then silently stops at 100 records

**Confidence:** Confirmed.

The route defaults to 100 and returns only `items`, with no total or continuation metadata
(`apps/api/app/routers/leads.py:168-190`). `list_leads` fetches the Lead rows once and calls
`lead_to_read` for every result (`apps/api/app/services/leads.py:679-758`). Each serialization can then
load Contact, Property, assigned user, closed-by user, and a primary task
(`apps/api/app/services/leads.py:6615-6659`; `apps/api/app/services/tasks.py:935-956`).

For 100 mostly unique leads, the conservative shape is one list query plus roughly three queries per
lead before optional user lookups. That is hundreds of statements for one list response and is well over
the current 50-query diagnostic threshold.

The web compounds the correctness problem. `getDashboardData` requests `/api/v1/leads` without a
cursor (`apps/web/src/app/lib/api.ts:6596-6626`), and the Leads page paginates only the already truncated
browser array (`apps/web/src/app/os/leads/leads-workspace.tsx:494`). Once active leads exceed the API
cap, older active records disappear from All Leads, pipeline columns, owner/facet calculations, and any
other feature using that shared dataset.

**Safe correction:** batch-load contacts, properties, users, and open primary tasks into maps; keep the
existing item schema and order. Add a constant-query regression test at 1, 25, and 100 rows. Then add
backward-compatible `total`, `has_more`, and cursor/page metadata and move table and pipeline columns to
real server pagination.

#### 3. Inbox list hydration is a severe N+1 path and the timeline can hide the newest messages

**Confidence:** Confirmed.

The Inbox route exposes queue and assignment filters but no pagination contract
(`apps/api/app/routers/inbox.py:74-93`). The service silently limits the list to 100 and calls a rich
serializer for each conversation (`apps/api/app/services/inbox.py:1308-1336`). Per conversation, that
serializer can load the contact, assignee, lead, property, watchers, assignment history, latest inbound
channel, buyer context, and a general-contact email (`apps/api/app/services/inbox.py:2516-2576`). At a
full page this is several hundred SQL statements.

The detail query has a separate correctness bug. It orders communications oldest-first and then applies
`LIMIT 200` (`apps/api/app/services/inbox.py:1507-1515`). A conversation with more than 200 records can
therefore omit the latest messages—the exact opposite of what an active inbox needs.

The browser then reloads the entire capped list and the entire selected detail every 15 seconds while the
tab is visible (`apps/web/src/app/os/inbox/inbox-workspace.tsx:1333-1349`). That is approximately eight
API calls per minute per open user before pending-SMS delivery polling, and each list request traverses
the expensive serializer again.

**Safe correction:** build a bounded list projection with bulk loaders; select the newest 200 timeline
records and present them oldest-to-newest; add an older-message cursor; add cursor pagination to the
conversation list; and replace full polling with a lightweight version/attention read followed by
conditional delta/detail refresh.

### P1 - High-value structural relief

#### 4. The worker creates heavy database churn even while idle

**Confidence:** Confirmed workload; production resource share is a strong candidate.

The single worker checks 27 operations sequentially (`apps/api/app/worker.py:81-115,232-253`). For each
operation it opens separate sessions to record start, check retry state/run work, resolve failures, and
record finish (`apps/api/app/worker.py:235-310`). Start and finish each select and update the shared
heartbeat row (`apps/api/app/services/operations.py:170-227`); retry eligibility and failure resolution
each perform another select (`apps/api/app/services/operations.py:350-392`).

At the configured 10-second idle poll (`render.yaml:561-564`), start/finish telemetry alone is about 108
SQL statements per sweep, including 54 heartbeat updates. Retry/failure checks add roughly 54 more
selects before the 27 operations perform their own queue probes. That means hundreds of unnecessary
writes per minute on the current `basic-256mb` PostgreSQL plan even when little is happening.

The sequential design is also a latency risk: one slow provider operation delays every later lane.
However, splitting the worker now would add operational complexity without proving starvation.

**Safe correction:** record one cycle heartbeat, persist per-operation state only when the outcome
changes, work is processed, an error occurs, or a coarse reporting interval expires, and schedule the
next due operation instead of probing every lane every ten seconds. Add automatic queue depth and
oldest-ready-age metrics. Split interactive communications from long AI/backfill work only if those
metrics show real contention.

#### 5. Dispositions overview and desk build full organization-scale datasets

**Confidence:** Confirmed behavior; current-volume impact varies by organization size.

The overview selects all organization cases and calls the full `case_read` model for each
(`apps/api/app/services/dispositions.py:171-232`). `case_read` loads organization-wide buyers and proof
documents for each case, plus matches, offers, engagements, and reconciliation
(`apps/api/app/services/dispositions.py:1561-1623`). The overview schema embeds those detailed
collections rather than a compact queue projection.

The Disposition Desk supports a 100-item section response, but default loading first materializes the
active cases and section datasets and slices them near the end
(`apps/api/app/services/disposition_desk.py:469-519,1494-1562`). On the default all-sections request it
also calls `_desk_checklist` for each active deal (`apps/api/app/services/disposition_desk.py:995-1035`).
Each checklist invokes a full readiness read with its own plan, mode, package, pool, offer, campaign,
selection, and reconciliation work (`apps/api/app/services/disposition_readiness.py:130-332`).

The deal workspace adds browser cost. Its parent statically imports the tab workspaces, and the current
production-mode build artifact assigns the disposition case approximately 226 KiB of gzip-compressed
JavaScript versus 176 KiB for Leads and 170 KiB for Inbox. The execution read also loads every active
buyer and serializes every candidate (`apps/api/app/services/disposition_execution.py:91-287`).

**Safe correction:** introduce a lightweight, paged case-summary DTO; compute section counts with SQL
aggregates; query each requested desk section with SQL-level limits; store or bulk-derive readiness
summaries; return only current/next plus a cursor page of execution candidates; and dynamically load an
inactive tab only when opened. Shadow-compare new summary results with the old response before cutover.

#### 6. The acquisition operations endpoint is a broad workspace endpoint used by narrower pages

**Confidence:** Confirmed.

One `/api/v1/operations` request assembles users, teams, calling lists, notifications, saved views,
duplicate candidates, follow-up plans, appointments, markets, territories, campaigns, and prospects
(`apps/api/app/services/acquisition_operations.py:142-174`). Several sub-builders do per-row lookups:
users at `:711-752`, teams at `:1012-1048`, calling-list entries at `:1212-1257`, markets at `:177-205`,
campaigns at `:372-418`, and appointments at `:2064-2108`.

The Leads page loads this entire object on every visit even though its main needs are users,
appointments, and notifications (`apps/web/src/app/os/leads/page.tsx:45-52`). Settings pages reuse it for
other subsets.

**Safe correction:** add page-specific reads—such as lead operations, people/team settings, market
settings, and data-quality summaries—while retaining the broad endpoint as a compatibility facade until
all consumers move.

#### 7. `getDashboardData` spreads expensive Lead hydration across unrelated pages

**Confidence:** Confirmed.

`getDashboardData` always requests dashboard summary, Leads, speed-to-lead tasks, and open tasks in
parallel (`apps/web/src/app/lib/api.ts:6596-6626`). It is used by Home, Leads, Buyers, Finance, AI
control, and six Settings pages. Several consumers only need a small subset, but all pay for the full
Lead list and task queues.

Home additionally requests profile, field operations, executive copilot, and inbox attention and then
renders only a small priority subset. Because Home counts are derived partly from the silently capped
Lead array, those counts can become inaccurate above 100 records.

**Safe correction:** replace the generic helper with explicit summary, lead-selector, and task accessors.
Give Home one role-scoped read model containing counts, today's meetings, inbox attention, and only the
top actionable rows. Load executive copilot only when opened.

#### 8. Metadata reads can load large binary documents unnecessarily

**Confidence:** Confirmed code behavior; production byte cost needs table/TOAST measurements.

Production uses database document storage (`render.yaml:221-222`). Large binary columns exist for email
attachments, photos, transaction documents, buyer proofs, disposition PDFs, finance documents, and bank
imports. Several metadata/list paths select complete ORM rows without deferring binary attributes,
including transaction detail (`apps/api/app/services/transactions.py:377-389`), buyer proof summaries
(`apps/api/app/services/buyers.py:113-130`), disposition proof reads
(`apps/api/app/services/dispositions.py:1590-1600`), desk proof reads
(`apps/api/app/services/disposition_desk.py:772-787`), banking (`apps/api/app/services/banking.py:59-81`),
and vendor accounting (`apps/api/app/services/vendor_accounting.py:96-105`).

**Safe correction:** use `defer`/`load_only` for every metadata and list path and add tests proving the
binary attributes remain unloaded. Do not migrate all bytes to object storage until table and TOAST
sizes demonstrate that a migration is worth its operational risk.

### P2 - Correct after the shared hot paths

#### 9. Deals and Finance use unbounded or high-fan-out reads

**Confidence:** Confirmed behavior; live impact depends on usage and row counts.

Deal overview reads every Deal/Transaction without paging
(`apps/api/app/services/deals.py:612-644`), and the browser filters and renders the received collection.
Transaction tabs then load selected detail, copilot, and e-sign/F4 data after hydration, including data
that inactive tabs do not need.

Finance starts six reads in its first wave and, when accounting is configured, another six in a second
wave (`apps/web/src/app/os/finance/page.tsx:68-99`). The OS layout adds profile and approval reads. Any
slow subsystem delays the whole page.

**Safe correction:** page active and completed deals separately; load the selected transaction directly;
lazy-load copilot and e-sign data by tab; split Finance into a fast summary shell and lazy accounting
sections.

#### 10. The global shell performs hidden work

**Confidence:** Confirmed.

Every OS navigation waits for the workspace profile and a full approval-request response
(`apps/web/src/app/os/layout.tsx:23-27`) although the shell needs only profile basics and a pending count.
The closed Help workspace is mounted globally and makes a browser request before the employee opens it.

**Safe correction:** use a count-only approval endpoint and mount/fetch Help on first open. Preserve the
existing Web Phone behavior; its Twilio SDK already loads dynamically only when the phone is initialized
(`apps/web/src/app/os/_components/web-phone-runtime.ts:106`).

#### 11. Common tenant-filtered scans lack matching composite indexes

**Confidence:** Future risk; indexes are candidates, not yet prescribed.

Lead list filters organization/archive and orders created/id; Conversation list filters organization,
access/queue and orders last-activity/created; Disposition cases commonly filter organization/status.
Models currently provide mostly separate indexes. Composite indexes may materially help after N+1 work
is removed, but speculative indexes also increase write cost.

**Safe correction:** capture production `EXPLAIN (ANALYZE, BUFFERS)` and query frequency after the list
refactors, then add only indexes that match a demonstrated hot query.

#### 12. Complexity is concentrated in a service dependency knot

**Confidence:** Confirmed maintainability debt, not direct speed proof.

A static dependency scan found 352 service-to-service imports and one strongly connected group containing
32 service modules. Leads alone imports 25 service modules. The web also has at least 21 local request
wrappers and 54 OS files that reference the public API base URL.

**Safe correction:** while fixing a hot endpoint, extract its read model/query module and move the web
consumer to one shared browser request primitive. Do not launch a repository-wide file-splitting project.

## Symptom-to-cause map

| User-visible symptom | Most credible code-level cause |
| --- | --- |
| Many pages feel a little slow | Per-request JWKS client, layout reads, and generic dashboard fan-out |
| Leads becomes taller/heavier as records grow | Rich per-row serializer, client-only pagination, full refresh after mutations |
| Inbox feels laggy with multiple users | Several-hundred-query list hydration plus complete 15-second polling |
| An old/long conversation looks incomplete | Oldest-first `LIMIT 200` hides newer communications |
| Dispositions takes longer than ordinary pages | Full case read models, organization-wide buyers/proofs, all-tab client graph |
| Disposition Desk paging does not reduce initial cost | Full section construction occurs before slicing |
| Background work can feel unpredictable | 27 serial lanes plus constant idle database churn |
| Home counts eventually disagree with Leads | Both derive from a silently capped 100-lead response |

## Healthy patterns to preserve

The audit also found several good boundaries:

- Deal overview already has a useful bulk-hydration/map pattern in
  `apps/api/app/services/deals.py:414-609`; copy that pattern for Leads and Inbox.
- Inbox detail explicitly defers email attachment bytes at
  `apps/api/app/services/inbox.py:1517-1520`.
- Disposition execution batches contact eligibility rather than querying each contact independently.
- Prospecting has a constant-query regression test at 1 versus 25 entries in
  `apps/api/tests/test_prospecting_workbench.py:678-880`; use the same test style.
- The worker isolates operation failures, uses durable retry state, records bounded errors, and keeps a
  separate heartbeat.
- AI work claiming uses `FOR UPDATE SKIP LOCKED` and commits before long execution.
- Inbox polling pauses in hidden tabs and prevents overlapping refreshes.
- Several secondary disposition tools already defer their data until opened.
- The Twilio browser SDK is dynamically imported rather than included in every initial page load.
- The current production-readiness workflows are non-blocking monitors; the authenticated workflow is
  bound to the `production-smoke` environment and is not manually dispatchable from an arbitrary ref.
- The native in-CRM prospecting dialer is disabled in both API and worker configuration. Its remaining
  code is maintenance surface, not a current runtime load source.

## Recommended implementation sequence

This sequence is ordered by user impact, confidence, safety, and reversibility. It is not an operator
checklist; it is the developer execution order.

### Slice 1 - Remove global request drag

1. Reuse a process-lifetime Clerk JWKS client.
2. Preserve every current verification check.
3. Add unit coverage for caching, unknown-key refresh, invalid signature, issuer, audience, and authorized
   party.

This is the smallest change with the broadest possible benefit and no database or UI contract change.

### Slice 2 - Make Leads a constant-query read

1. Add a query-count regression fixture before changing behavior.
2. Batch contacts, properties, users, and primary actions.
3. Keep the existing response item exactly compatible.
4. Compare 1, 25, and 100 lead responses for content and ordering.

### Slice 3 - Make Inbox list and timeline correct

1. Add a constant-query list test and a 201-message timeline regression test.
2. Batch the Inbox list projection.
3. Return the newest timeline window in chronological display order.
4. Add an older-message cursor without removing existing fields.

### Slice 4 - Bound collection growth

1. Add `total`/`has_more`/cursor metadata to Leads and Inbox responses.
2. Move Leads table and pipeline columns to server paging/lazy columns.
3. Move Inbox to a first page plus incremental older/list pages.
4. Paginate active and historical Deals independently.

### Slice 5 - Stop repeat full refreshes

1. Add a lightweight Inbox change/version endpoint or conditional ETag contract.
2. Refresh list/detail only when their version changes.
3. Keep temporary polling as a fallback during rollout.
4. Avoid a full server page refresh after successful optimistic Lead stage changes.

### Slice 6 - Reduce broad workspace reads

1. Split acquisition operations by page need.
2. Replace `getDashboardData` with explicit accessors.
3. Add a small Home read model rather than downloading whole queues.
4. Use a count-only approvals read and lazy Help mount.

### Slice 7 - Lighten Dispositions

1. Add a lightweight active-case overview and explicitly paged history.
2. Move desk section pagination into SQL and aggregate counts separately.
3. Bulk or persist readiness summaries rather than rebuilding a full workspace per case.
4. Page buyer execution candidates and use server search.
5. Dynamically import inactive workspace tabs.

### Slice 8 - Reduce worker and binary I/O pressure

1. Coalesce idle worker telemetry and schedule next-due lanes.
2. Expose bounded queue depth and oldest-ready age automatically.
3. Defer all binary columns on metadata paths.
4. Use measured queue age and PostgreSQL statistics before changing deployment topology or storage.

### Slice 9 - Evidence-led capacity work

1. Evaluate composite indexes with production `EXPLAIN` after the N+1 fixes.
2. Split worker lanes only if oldest-ready age shows starvation.
3. Move document bodies only if table/TOAST size and read I/O justify it.
4. Extract module boundaries only around code being changed for a user-facing reason.

## Automated acceptance targets

These checks belong in CI or runtime instrumentation; they are not manual tasks for staff.

| Area | Acceptance target |
| --- | --- |
| Authentication | Repeated valid token checks reuse JWKS; unknown key still triggers safe refresh |
| Leads list | Query count remains effectively constant from 1 to 100 rows |
| Inbox list | Query count remains effectively constant from 1 to 100 rows |
| Inbox detail | A 201+ message thread always includes the newest message and can load older history |
| Pagination | No active record silently disappears at 100 items; response declares continuation |
| Inbox refresh | Unchanged state returns a tiny response and does not rehydrate all rows |
| Worker idle loop | Per-minute heartbeat/telemetry writes fall by at least 90% without losing failure evidence |
| Disposition desk | Page size changes database work, not only response slicing |
| Disposition case | Initial execution payload is bounded independently of total buyer count |
| Metadata reads | Binary document attributes remain unloaded until a download/content endpoint needs them |

## Release-safety method

Every implementation slice should follow the same automated pattern:

1. add a failing regression or query-count test;
2. make one bounded, response-compatible change;
3. run the affected unit, integration, and web contract suites;
4. keep a compatibility endpoint or fallback during contract migrations;
5. deploy one slice at a time so Phase 1 route/query telemetry identifies regressions;
6. automatically alert only on a durable failure or exceeded budget; and
7. remove the fallback only after the new path is proven.

No phase requires the owner to inspect dashboards, rebalance queues, or decide when the system is under
load.

## Explicitly deferred

Do not do the following before the measured hot paths are fixed:

- rewrite the CRM;
- split the modular monolith into microservices;
- split the worker merely because it has many operations;
- migrate every document out of PostgreSQL;
- add speculative indexes without plans and frequency data;
- delete legacy dialer code during performance work;
- split large files solely to reduce line counts; or
- increase Render plans as a substitute for fixing repeated work.

## Final assessment

Stonegate's current weight comes primarily from **repeated work**, not from an inherently wrong product
architecture. The highest-return path is surgical: cache the shared authentication key client, make Leads
and Inbox constant-query and genuinely paged, correct the Inbox timeline window, coalesce worker
telemetry, and replace broad Dispositions/workspace reads with bounded summaries.

That sequence improves speed, correctness, and resilience while leaving the daily CRM workflow intact.
