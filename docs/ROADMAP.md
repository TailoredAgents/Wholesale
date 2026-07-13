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

Status: Implemented locally.

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

## Current Phase

Phase 1C: Auth And Pre-GitHub Hardening.

Objective:

Replace development-only auth, harden the repository, then push to GitHub and prepare Render staging.

## Next Milestones

### M8: Clerk Authentication

Goal:

Replace the development-only identity header with real authentication while preserving RBAC.

Scope:

- Clerk app setup.
- Next.js Clerk provider.
- FastAPI token/session verification.
- User mapping from Clerk identity to local `users`.
- MFA requirement documented for privileged users.
- Development header removed from production paths.

Acceptance criteria:

- Signed-in user can access dashboard.
- Signed-out user cannot access protected internal pages.
- API validates Clerk identity.
- Local user permissions still control authorization.
- Production cannot use `X-Dev-User-Email`.
- Tests cover unauthorized and authorized API access.

Test expectations:

- Auth verification tests use mocks or Clerk test tokens.
- Existing RBAC tests remain valid.

Blocking inputs:

- Clerk project credentials.
- Local/staging Clerk URLs.

### M9: Local Pre-GitHub Hardening

Goal:

Prepare the repository for a clean GitHub push.

Scope:

- Remove any generated placeholder docs from app scaffold that conflict with project docs.
- Add CI workflow draft.
- Add secret scanning guidance.
- Confirm `.gitignore`.
- Confirm no local secrets committed.
- Add initial issue/backlog labels in docs.
- Review Render Blueprint for current service commands.

Acceptance criteria:

- Working tree clean.
- Full local verification passes.
- `git log` has clean milestone commits.
- No secrets in repository.
- README can bootstrap from a clean checkout.

### M10: Push To GitHub

Goal:

Create the remote repository and push `main`.

Scope:

- Create GitHub repo.
- Add remote.
- Push current history.
- Confirm branch protection plan.
- Add initial GitHub Actions workflow if not already added.

Acceptance criteria:

- GitHub remote exists.
- `main` is pushed.
- CI runs or is ready to run.
- README instructions are visible in GitHub.

### M11: Render Staging

Goal:

Deploy an early staging environment soon after GitHub push.

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

Blocking inputs:

- Render account/project access.
- Staging domain decision, if any.
- Clerk staging credentials.

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
