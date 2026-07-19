# Roadmap

## Current Strategy

Build locally first, keep the system testable at each milestone, then push to GitHub after the local staff lead workflow and speed-to-lead queue are in place. After GitHub is set up, create a Render staging deployment early so deployment issues are discovered before the product surface becomes large.

Current assumptions:

- Authentication provider: Clerk.
- GitHub push timing: after staff lead editing and speed-to-lead workflow.
- Render staging timing: soon after GitHub push.
- Business-facing company name: `Stonegate Home Buyers`.
- Current local organization: `Stonegate Home Buyers`.
- AI model default: `gpt-5.6-terra`.
- Comp automation requires property data APIs before AI can draft ARV support.

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
- Reviewed and updated Render Blueprint for current service commands, Stonegate service names, migrations, and Clerk env vars.

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

Make the front-facing Stonegate site ready for real seller traffic and paid lead generation.

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
- Added the shared inbox foundation with one unified conversation per lead, conversation queues,
  assignments, watchers, assignment history, unread/activity tracking, and provider-event storage.
- Added the routed three-panel shared inbox with Mine, Unassigned, Team, Needs Reply,
  Appointments, and Unread views; a unified communication, appointment, and assignment timeline;
  manual SMS, email, call, and internal-note logging; seller/property context; responsive pane
  navigation; read-state controls; and manager/VA handoff controls.
- Added a restricted prospecting-caller role that can only view assigned leads and conversations,
  log assigned communications, schedule assigned appointments, and hand qualified conversations
  to eligible acquisition users.
- Added an audited VA-to-acquisitions handoff that reassigns the lead, seller, open tasks, and
  scheduled appointments while automatically adding owner and acquisition watchers.
- Added call, recording, and transcript records with provider identifiers, recording-consent
  status, speaker segments, approval fields, and secure provider media references.
- Existing leads and communication records are backfilled into unified conversations during the
  Phase 1 database migration.
- Added appointment records with scheduled windows, type, status, location, notes, audit trail,
  and activity timeline entries.
- Added protected appointment scheduling API and lead workspace appointment panel.
- Scheduling an appointment now updates lead appointment status, next follow-up, and appointment
  pipeline stage when appropriate.
- Added underwriting version records for manual ARV range, repair range, max offer, recommended
  offer, strategy, notes, and review status.
- Added protected underwriting API and lead workspace underwriting panel.
- Creating underwriting versions now writes audit/activity events and moves leads into underwriting
  or offer-ready stages when appropriate.
- Added transaction records connected to deals, leads, properties, sellers, title/closing details,
  contract terms, and deadline metadata.
- Added default transaction checklist items for contract approval, signature, earnest money, title,
  disclosure/payoff collection, due diligence, closing, and assignment planning.
- Added protected transaction opening API and lead workspace contract/transaction panel.

Remaining:

- Persist user-specific saved view definitions after team/user preferences exist.
- Add appointment status update/reschedule outcomes and calendar sync after provider selection.
- Add comp candidate records, provider import adapters, and approval request records.
- Add contract template records, e-signature adapter, checklist completion actions, and explicit
  approval request workflow.
- Connect the AI-ready summary to model-backed agents after communications and underwriting data
  are available.
- Add approval gates for future AI-authored seller messages before enabling autonomous sending.
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

Delivered in the SMS foundation:

- Twilio Messaging Service adapter with idempotent outbound dispatch records.
- Signed inbound-message and delivery-status webhooks with retained provider events.
- Inbound and outbound SMS records in the unified communication timeline.
- Role-aware sending from the shared inbox.
- Consent, suppression, valid-number, contact-hour, and provider-configuration checks before send.
- STOP and START processing with consent history and an organization-wide suppression record.
- Delivery, failure, and undeliverable status updates on sent messages.
- Render configuration that remains disabled until Twilio credentials are supplied.

Delivered in Communications Phase 5, Twilio Browser Calling:

- Twilio browser Voice SDK with short-lived, user-specific access tokens.
- One-time, conversation-scoped outbound call intents that prevent arbitrary browser dialing.
- Company voice-line records with explicit sender selection, assignment, and inbound routing.
- Signed outbound, inbound, status, dial-result, disclosure, and recording webhooks.
- Known-caller routing to the conversation owner and retained lead creation for unknown callers.
- Idempotent call lifecycle records protected from duplicate and out-of-order callbacks.
- Missed inbound call tasks due within five minutes.
- Unified inbox call cards with duration, status, and permission-gated private recording playback.
- Role-aware calling for owners, acquisitions staff, and assigned prospecting callers.
- Contact permission, suppression, valid-number, contact-hour, and provider readiness checks.
- Render configuration that keeps Voice and recording independently disabled until activation.
- A migration-tested Voice schema and an operator setup runbook.

Delivered in Communications Phase 6, Recording and Transcription:

- Per-call recording disclosure tracking for inbound and outbound calls.
- Signed, idempotent Twilio recording callbacks and private role-gated audio playback.
- OpenAI transcription with speaker-separated segments in the unified inbox timeline.
- Structured call-note extraction with evidence timestamps and required human review.
- Configurable audio retention deadlines and automatic provider deletion by the worker.
- Owner-only early audio deletion with a required reason and complete audit history.
- Persistent transcripts and reviewed CRM notes after provider audio expires or is deleted.
- Deployment defaults that keep recording disabled until disclosure and Voice configuration are
  explicitly approved and enabled.

Delivered in Communications Phase 7, AI Call Intelligence:

- Evidence-backed structured call notes for motivation, condition, timeline, occupancy, asking
  price, objections, commitments, and next actions.
- Human approval before lead-field updates or follow-up task creation.
- Reviewer correction tracking with per-field agreement measurements.
- Confidence, evidence coverage, approval, rejection, failure, and high-correction reporting.
- Per-model input/output usage and sub-cent OpenAI cost estimates with pricing provenance.
- AI control-center quality reporting with conservative low-risk pilot thresholds.
- Autonomy remains disabled; passing quality thresholds only identifies pilot eligibility.

Remaining in the communications sequence:

- Communication-triggered follow-up tasks and notifications.
- Email provider integration.

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

Delivered foundation:

- Buyer CRM records.
- Buyer criteria.
- Proof-of-funds status.
- Deal room queue for contracted leads.
- Buyer offer collection tied to lead workspaces.

Remaining expansion:

- Buyer proof-of-funds document records.
- Buyer selection approval workflow.
- Deal blast campaigns and response automation.

### Phase 8: Finance And Compensation

Delivered foundation:

- Revenue records.
- Direct deal deductions.
- Effective-dated compensation rules.
- Automatic compensation calculations.
- Manual marketing spend records.
- OS finance page for ledger entry and reporting.

Remaining expansion:

- Payment status workflow.
- Monthly close process.
- Advertising percentage reporting.
- QuickBooks/Xero export or sync.

### Phase 9: Marketing Intelligence

Delivered foundation:

- Campaign/click performance reporting.
- Spend, lead, contract, and revenue attribution by source/campaign.
- Cost-per-lead and cost-per-contract reporting.
- ROAS reporting.
- Offline conversion export queue for Google/Meta click IDs.

Remaining expansion:

- Google Ads upload adapter.
- Meta conversions API adapter.
- Export retry and failure workflow.

### Phase 10: AI Control Center

Delivered foundation:

- Agent definitions.
- Prompt versions.
- Tool permission policy.
- Run and tool-call logs.
- Approval queue integration for proposed AI tool actions.
- Cost and latency tracking.
- OS AI Control page.

Remaining expansion:

- Evaluation datasets.
- Model-backed agent execution.
- OpenAI agent/tool integration.
- Automated approval workflow routing.

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
