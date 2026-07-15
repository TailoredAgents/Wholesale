# Roadmap

## Current Strategy

Build locally first, keep the system testable at each milestone, then push to GitHub after the local staff lead workflow and speed-to-lead queue are in place. After GitHub is set up, create a Render staging deployment early so deployment issues are discovered before the product surface becomes large.

Current assumptions:

- Authentication provider: Clerk.
- GitHub push timing: after staff lead editing and speed-to-lead workflow.
- Render staging timing: soon after GitHub push.
- Business-facing company name: `Oakwell Home Buyers`.
- Current local organization: `Oakwell Home Buyers`.

## Completed Local Milestones

### M0: Local Monorepo Foundation

Status: Done.

Delivered:

- Root git repository.
- Next.js web app.
- FastAPI API app.
- Python worker scaffold.
- PostgreSQL local development database.
- Alembic migrations.
- Render Blueprint draft.
- Local README and runbook.

Acceptance met:

- Web app builds.
- API health/readiness works.
- Worker starts.
- Local database migrates.
- Baseline committed.

### M1: RBAC And Bootstrap Foundation

Status: Done.

Delivered:

- Organization seed.
- Owner bootstrap command.
- 14 default roles.
- 22 default permissions.
- Role-permission mappings.
- Development-only protected route pattern.
- `/api/v1/me`.

Acceptance met:

- Bootstrap is idempotent.
- Protected route returns 401 without dev identity.
- Seeded owner resolves with permissions.
- Tests cover bootstrap and principal resolution.

### M2: Lead API And Live Dashboard

Status: Done.

Delivered:

- Protected lead create/list API.
- Dashboard summary API.
- Dashboard connected to live Postgres counts.
- Lead create writes activity and audit events.

Acceptance met:

- Leads can be created through API.
- Dashboard reads live lead and pipeline counts.
- Tests cover lead creation, listing, dashboard counts, and auth requirement.

### M3: Public Seller Intake

Status: Done.

Delivered:

- Public cash-offer form at `/get-a-cash-offer`.
- Public seller lead intake API.
- Consent records.
- Raw form submissions.
- Attribution touches.
- UTM, GCLID, FBCLID, landing page, referrer, IP, and user-agent capture.

Acceptance met:

- Public form/API creates contact, property, lead, consent, form submission, attribution, activity, and audit records.
- Consent is required.
- Tests cover consent and record creation.

### M4: Duplicate Detection

Status: Started and functional locally.

Delivered:

- Contact methods for normalized email/phone.
- Normalized property address key.
- Public intake duplicate matching.
- Duplicate submissions reuse existing active lead when contact and property match.
- Duplicate submissions still preserve consent, form, attribution, activity, and audit evidence.

Acceptance met:

- Repeat email/phone/address returns `matched_existing_lead`.
- Repeat submission does not create another active lead.
- Tests cover duplicate matching.

Remaining hardening:

- More robust address normalization.
- Fuzzy duplicate review queue.
- Manual merge workflow.
- Duplicate confidence/explanation fields.

### M5: Lead Detail And Stage Workflow

Status: Done.

Delivered:

- Protected lead detail API.
- Protected stage update API.
- Internal lead detail page.
- Dashboard lead links.
- Stage update control.
- Lead detail shows contact methods, consent, attribution, and recent activity.
- Stage updates write activity and audit events.

Acceptance met:

- Lead detail API returns complete context.
- Stage update changes the pipeline stage.
- Stage update is audited.
- Web detail route renders.
- Tests cover detail, stage update, invalid stage rejection.

### M6: Staff Lead Editing

Status: Done.

Delivered:

- Protected staff lead edit API.
- Seller legal/preferred name editing.
- Email and phone contact method add/update.
- Property address, county, and property type editing.
- Lead source and temperature editing.
- Structured property fields returned by lead APIs for edit prefill.
- Lead detail edit form.
- Audit events with previous and new values for material edits.
- Activity timeline entry for material edits.
- Tests added for successful edit/audit behavior and auth requirement.

Verification completed:

- API lint.
- API typecheck.
- Python compile check.
- Full API test suite.

Verification blocked:

- Broad web lint, Next build, TypeScript compiler, and Next dev server hung before producing diagnostics in this local shell.

### M7: Speed-To-Lead Queue

Status: Done.

Delivered:

- Lead-linked task metadata and Alembic migration.
- Configurable speed-to-lead due threshold through `SPEED_TO_LEAD_DUE_MINUTES`.
- Idempotent speed-to-lead task creation for public seller submissions.
- Protected speed-to-lead queue API.
- Protected task completion API.
- Dashboard queue panel backed by real open tasks.
- Due/overdue/unscheduled queue state labels.
- Dashboard task completion action.
- Activity event when a speed-to-lead task is created.
- Audit and activity events when a task is completed.
- Tests for task creation, duplicate suppression, queue retrieval, completion, audit, and activity.

Acceptance met:

- Public lead submission creates an acquisition follow-up task.
- Duplicate public submissions do not create duplicate open speed-to-lead tasks.
- Dashboard fetches and displays the live speed-to-lead queue.
- Queue distinguishes due and overdue tasks.
- Staff can mark a speed-to-lead task complete.
- Completion is audited and recorded as activity.
- Tests cover task creation and queue behavior.

Verification completed:

- Alembic migration applied locally.
- API lint.
- API typecheck.
- Python compile check.
- Targeted M7 API tests.
- Full API test suite.

Verification blocked:

- Broad web lint, Next build, and TypeScript compiler hung before producing diagnostics in this local shell.

### M8: Clerk Authentication

Status: Implemented locally; Clerk project credentials still required for live sign-in.

Delivered:

- Clerk dependency installed in the Next.js app.
- `ClerkProvider` added at the app root.
- Clerk middleware added for internal dashboard and lead routes.
- Clerk sign-in and sign-up routes.
- Server-rendered API requests send Clerk bearer tokens when available.
- Client-side staff actions send Clerk bearer tokens when available.
- FastAPI verifies Clerk JWTs through JWKS.
- Clerk subject maps to local `users.external_auth_id`.
- Existing local user can be linked by email after token verification.
- Production rejects development header auth.
- Local development can still use `X-Dev-User-Email` when no Clerk token is present.
- Clerk environment variables documented in `.env.example`.

Acceptance met:

- Signed-in Clerk users can be mapped to local RBAC users.
- API validates Clerk identity before resolving local permissions.
- Local user permissions remain the authorization source.
- Production cannot use `X-Dev-User-Email`.
- Tests cover production rejection of dev auth and mapped Clerk principal access.

Verification completed:

- API lint.
- API typecheck.
- Full API test suite.
- Web production build using `next build --webpack`.

Verification blocked:

- Broad web lint still hangs before producing diagnostics in this local shell.

Remaining setup:

- Create Clerk project.
- Add local and Render Clerk environment variables.
- Map the first Clerk user to the existing owner user.
- Require MFA for owner/admin users in Clerk.

## Current Phase

Phase 2A: Staging Stabilization And Public Conversion Foundation.

Objective:

Use the live staging deployment to harden the public seller conversion flow and the internal OS
workspace. The unified product direction is documented in `docs/UNIFIED_BUILD_PLAN.md`.

## Next Milestones

### M9: Local Pre-Render Hardening

Status: Done.

Goal:

Prepare the repository for CI and Render staging.

Delivered:

- Removed generated create-next-app README copy that conflicted with project docs.
- Removed unused create-next-app SVG assets.
- Added GitHub Actions CI for API lint/typecheck/tests and web production build.
- Added secret scanning guidance.
- Confirmed `.gitignore` covers env files, dependency installs, build output, caches, and local conflict artifacts.
- Added GitHub branch protection and issue-label plan.
- Added Render staging checklist.
- Reviewed and updated Render Blueprint for current service commands, Oakwell service names, migrations, and Clerk env vars.

Acceptance met:

- Local verification passes for API and web build.
- No tracked local secrets found by pattern scan.
- README can bootstrap from a clean checkout.
- GitHub CI is ready to run.

Verification completed:

- API lint.
- API typecheck.
- Full API test suite.
- Web production compile with Next build-time TypeScript validation temporarily skipped.
- `git diff --check`.

Remaining caveat:

- Web lint still hangs before diagnostics and is excluded from CI for now.
- Clerk dependency type checking currently stalls local Next/TypeScript validation; re-enable
  build-time validation after the toolchain issue is resolved.

### M10: Push To GitHub

Status: Done.

Goal:

Create the remote repository and push `main`.

Delivered:

- GitHub remote added: `https://github.com/TailoredAgents/Wholesale.git`.
- `main` pushed and tracking `origin/main`.
- CI workflow added.
- Branch protection plan documented.

Acceptance met:

- GitHub remote exists.
- `main` is pushed.
- CI is ready to run.
- README instructions are visible in GitHub.

### M11: Render Staging

Status: Done.

Goal:

Deploy an early staging environment.

Scope:

- Render PostgreSQL staging database.
- Render API service.
- Render web service.
- Render worker service.
- Render Key Value staging resource.
- Staging environment variables.
- Run migrations in staging.
- Bootstrap staging owner.

Acceptance criteria:

- Staging web URL loads.
- Staging API `/health` and `/ready` pass.
- Staging database migrations apply.
- Staging login path works after Clerk is configured.
- No secrets are committed.

Delivered:

- Render Blueprint deployment.
- Public website at `/`.
- Public cash-offer form at `/get-a-cash-offer`.
- Protected internal OS route at `/os`.
- API health and readiness endpoints live.
- Clerk redirects configured to return staff users to `/os`.

### M12: Public Conversion Foundation

Status: In progress.

Goal:

Make the front-facing Oakwell site ready for real seller traffic and paid lead generation.

Scope:

- Conversion-focused homepage copy.
- Seller situation pages.
- Trust and process sections.
- Cash-offer form UX tightening.
- Conversion event model.
- Form start, abandonment, submit, duplicate, and call-click tracking.
- Source/campaign reporting in the OS.

Acceptance criteria:

- Public pages have one seller CTA and no internal OS links.
- Conversion events are stored in PostgreSQL.
- OS shows source/campaign performance and speed-to-lead by source.
- Paid traffic can be launched without losing attribution or consent evidence.

Delivered so far:

- Added PostgreSQL conversion event model and migration.
- Added public conversion event API for page views, form starts, and call clicks.
- Added definitive cash-offer form submit events tied to leads.
- Preserved UTM, click ID, landing page, referrer, session, IP, and user-agent context.
- Added OS source performance reporting for views, starts, submits, calls, and created leads.
- Instrumented the public homepage and cash-offer form without adding internal OS links.
- Added seller situation pages for inherited houses, repairs-needed houses, and fast-sale timelines.
- Expanded the homepage with public trust cues, process content, visual property media, and stronger seller CTAs.
- Removed internal operating-system wording from the public cash-offer page.
- Improved the cash-offer form with clearer sections, helper text, and a stronger confirmation state.
- Added honeypot spam protection for public seller intake.
- Added form abandonment tracking and OS reporting.

Remaining:

- Add deeper trust/proof/process sections.
- Add stronger spam protection after traffic volume justifies it.

### M13: Acquisition Lead Workspace

Status: In progress.

Goal:

Turn each seller lead into a usable acquisition workspace for qualification, follow-up,
appointments, and next actions.

Research basis:

- Modern investor CRMs emphasize qualification fields for motivation, timeline, condition,
  appointment setting, follow-up, and pipeline accountability.
- Strong real estate CRMs centralize source context, contact details, notes, tasks, and timeline
  history so the rep can work from one screen.

Delivered so far:

- Added acquisition fields to leads: motivation, timeline, condition, occupancy, asking price,
  mortgage balance, appointment status, and next follow-up.
- Public cash-offer submissions now populate motivation, timeline, and asking price.
- Added lead notes that appear in the lead activity timeline.
- Added manual follow-up task creation from the lead page.
- Added open task visibility and completion from the lead page.
- Expanded the lead detail page into an acquisition workspace with a qualification snapshot.
- Added a generic open task queue API for all acquisition task types.
- Added OS daily work queues for overdue follow-up, qualification gaps, appointments, and offers.
- Added a seller acquisition board grouped by pipeline stage with task and follow-up context.
- Split the OS into real routed pages for dashboard, tasks, pipeline, leads, underwriting,
  approvals, and buyers.
- Added deterministic lead intelligence with quality score, urgency score, priority label,
  missing-field prompts, next best action, and AI-ready summary support.
- Added an AI-ready intelligence panel to the lead workspace.
- Added saved OS lead views for urgent leads, qualification gaps, missing follow-up,
  appointments, offer prep, paid sources, and nurture.
- Added operating status labels and seven-field qualification progress to the OS lead database.
- Added `/os/leads/{leadId}` lead detail routing and updated OS links to stay inside the
  operating-system surface.
- Added communication records for manual call, SMS, email, voicemail, and internal-note logging.
- Added protected lead communication logging API with audit and activity events.
- Added a communications panel to the lead workspace.
- Added a communication provider adapter contract for future Twilio/Gmail-style integrations.

Remaining:

- Persist user-specific saved view definitions after team/user preferences exist.
- Add appointment records instead of only appointment status.
- Connect the AI-ready summary to model-backed agents after communications and underwriting data
  are available.
- Add inbound provider webhooks, suppression checks, and send approval gates before live
  seller-facing automation.
- Decide whether to keep or redirect the legacy `/leads/{leadId}` route after staff bookmarks
  have moved to `/os/leads/{leadId}`.

## Later Product Phases

### Phase 2B: Lead Generation Hardening

- Address validation/autocomplete provider.
- Spam protection.
- Content pages for seller situations.
- PPC landing page templates.
- Form abandonment events.
- Consent wording management.
- Suppression records and opt-out enforcement.

### Phase 3: Communications And Intake

- Twilio adapter.
- Webhook signature validation.
- Inbound SMS/call records.
- Outbound communication compliance gate.
- Unified communication timeline.
- Initial AI intake summary/extraction.
- Call/lead follow-up tasks.

### Phase 4: Acquisition Workspace

- Acquisition daily workspace.
- Saved filters.
- Lead assignment.
- Appointments.
- Follow-up plans.
- Call notes and activity timeline.
- Missing-field prompts.

### Phase 5: Underwriting Foundation

- Property data provider abstraction.
- Underwriting versions.
- Comparable sale candidate records.
- Human comp review.
- ARV range.
- Repair estimate.
- Offer scenarios.
- ARV/offer approval queue.

### Phase 6: Contracts And Transactions

- Template records.
- Contract approval request.
- E-signature adapter.
- Transaction checklist.
- Closing attorney/status fields.
- Deadline tracking.

### Phase 7: Buyers And Dispositions

- Buyer CRM.
- Buyer criteria.
- Proof-of-funds records.
- Deal room.
- Buyer offer collection.
- Buyer selection approval.

### Phase 8: Finance And Compensation

- Revenue records.
- Direct deal deductions.
- Effective-dated compensation rules.
- Compensation calculation.
- Monthly advertising spend.
- Advertising percentage reporting.

### Phase 9: Marketing Intelligence

- Google conversion event upload adapter.
- Meta conversions adapter.
- Campaign/click performance reporting.
- Offline conversion export/retry tracking.

### Phase 10: AI Control Center

- Agent definitions.
- Prompt versions.
- Tool-call logs.
- Approval queue integration.
- Evaluation datasets.
- Cost and latency tracking.

## Open Decisions

- Business-facing company name.
- Object storage provider.
- Address validation/geocoding provider.
- Initial property data provider.
- E-signature provider.
- Queue library.
- Error monitoring provider.

## Non-Negotiables

- PostgreSQL remains the source of truth.
- Material actions are audited.
- AI does not make binding offers, send contracts, or bypass approvals.
- Consent/suppression checks are deterministic.
- No real seller communications from automated tests.
- No secrets in git.
