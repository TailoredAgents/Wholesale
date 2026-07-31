# Stonegate Home Buyers System Map

Last verified against the repository: July 31, 2026

## 1. Document Authority

This is the canonical as-built map of the Stonegate Home Buyers platform. It describes what the
current repository contains, how the major workflows connect, and which external services still
require production acceptance.

Use `DOCUMENTATION.md` for source priority. Use `FINISHING_ROADMAP.md` for remaining work. Use
`USER_MANUAL.md` for detailed staff instructions.

## 2. Product Definition

Stonegate is one company platform with two intentionally separate product surfaces:

1. A public seller website that explains the direct-sale service and captures property inquiries.
2. A private, authenticated operating system for the Stonegate team.

The platform is designed for a real-estate wholesaling company starting in Georgia and later
expanding by market and territory. It supports the business from prospect acquisition through
seller qualification, field appointments, underwriting, contracting, disposition, closing,
accounting, performance measurement, and AI-assisted work.

The public website is not a staff portal. The private OS does not need a public-site navigation
tab. Staff enter through `/sign-in` or a direct `/os` route and are sent to a role-appropriate
workspace.

## 3. Current Production Shape

### 3.1 Repository And Deployment

- GitHub repository: `TailoredAgents/Wholesale`
- Deployment: Render Blueprint from `main`
- Blueprint file: root `render.yaml`
- Primary web domain: `https://www.stonegatehb.com`
- Primary API domain: `https://api.stonegatehb.com`
- Render web fallback: `https://oakwell-web.onrender.com`

The Render resources retain legacy infrastructure names:

| Resource | Function |
| --- | --- |
| `oakwell-web` | Next.js public site and private OS |
| `oakwell-api` | FastAPI, database migrations, and business API |
| `oakwell-worker` | Background jobs defined by the API application |
| `oakwell-postgres` | Primary PostgreSQL database |
| `oakwell-key-value` | Redis-compatible coordination service |

The `oakwell-*` identifiers do not represent a second company or product. Customer-visible copy
must use Stonegate Home Buyers.

### 3.2 Runtime Status

| Area | Current status |
| --- | --- |
| Public site | Implemented and deployed |
| Private OS | Implemented and deployed |
| Clerk authentication | Implemented and active |
| PostgreSQL data layer | Implemented and active |
| Resend two-way email | Implemented and configured; controlled production acceptance remains |
| Twilio SMS | Implemented; dedicated A2P campaign approval and acceptance remain |
| Twilio Voice | Implemented; dedicated number, credentials, and acceptance remain |
| RentCast property data | Implemented; provider coverage varies by address |
| OpenAI copilots | Implemented in governed draft-only form; production pilots remain |
| SignWell e-signature | Implemented; provider activation and controlled acceptance remain |
| DealMachine buyer discovery | Implemented adapter; subscription/API activation intentionally deferred |
| Internal accounting | Implemented; CPA acceptance and first real close remain |
| Marketing conversion delivery | Implemented; ad-provider credentials and acceptance remain |

“Implemented” does not mean an external provider is active. Provider status is visible separately
so staff are not misled by a control that exists but lacks production credentials.

## 4. Technical Architecture

### 4.1 Monorepo

| Path | Responsibility |
| --- | --- |
| `apps/web` | Next.js 16, React 19, public website, OS interface, Clerk client integration |
| `apps/api` | FastAPI, SQLAlchemy, Alembic, domain services, provider adapters, PDF generation |
| `apps/api/app/worker.py` | Deployed background synchronization, transcription, retention, and escalation work |
| `apps/worker` | Original heartbeat scaffold; not the Render production worker implementation |
| `scripts` | Backup, restore verification, smoke tests, and operations utilities |
| `docs` | Canonical product, operating, setup, and user documentation |
| `render.yaml` | Render service topology and non-secret environment configuration |

### 4.2 Runtime Boundaries

- The browser renders the public site and OS through Next.js.
- Protected browser requests carry a Clerk bearer token to FastAPI.
- FastAPI validates identity, resolves the local Stonegate user, organization, roles, and
  permissions, then executes domain services.
- PostgreSQL is the operational source of truth.
- Redis supports coordination and background-work behavior; it is not the system of record.
- Provider callbacks enter through dedicated signed webhook routes.
- The production worker executes repeatable background jobs and records heartbeat or failure
  evidence.
- External AI and provider outputs never replace source records silently.

### 4.3 Database Evolution

The database has 74 numbered Alembic migrations through `0074_propstream_pipeline`. Migrations are
run automatically when the Render API starts and manually with `npm run db:migrate` locally.

Schema changes must be additive or explicitly migrated. Production data must never depend on
dropping and recreating the database.

### 4.4 API Organization

FastAPI routers are grouped by business capability:

- `public`: seller intake and conversion events
- `me`: current authenticated user and access profile
- `dashboard`: role-aware summary and Executive Copilot
- `operations`: users, teams, markets, territories, campaigns, calling lists, saved views,
  notifications, duplicates, and follow-up plans
- `campaign-management`: list imports, mappings, cohorts, work sessions, campaign costs, and
  calling batches
- `prospecting`: VA workbench, scripts, attempts, handoffs, coaching, and quality review
- `lead-manager`: warm-lead acceptance, qualification, and Lead Manager Copilot
- `leads`: CRM records, appointments, tasks, communications, underwriting, offers, and archival
- `tasks`: speed-to-lead and open work queues
- `inbox`: shared conversations, saved views, unread state, SMS, assignments, and watchers
- `email`: aliases, grants, templates, compose, delivery, attachments, and routing exceptions
- `voice`: browser sessions, lines, call intents, recordings, and transcript review
- `field-operations`: dispatch, briefs, inspections, photos, negotiation, and in-person signing
- `underwriting`: calibration cases and methodology decisions
- `approvals`: centralized human decision queue
- `transactions`: contract packages, e-signature, documents, parties, checklists, and closing
- `buyers`: buyer CRM and provider-backed discovery
- `dispositions`: packages, matching, campaigns, offers, selection, and reconciliation
- `finance`: ledger, banking, vendors, reports, compensation, tax, and Finance Copilot
- `marketing`: performance, offline conversion delivery, and Marketing Copilot
- `operating-model`: seats, counterparties, role acceptance, compensation, and market launches
- `ai`: agents, copilots, runtime, evaluations, traces, promotions, and automation controls
- `webhooks`: Twilio messaging and Voice callbacks
- `resend-webhooks`: signed Resend events
- `esign-webhooks`: SignWell events
- `health`: liveness and dependency readiness

## 5. Identity, Workspace, And Access

### 5.1 Authentication

Clerk proves who signed in. The API validates the token issuer, signing keys, audience when
configured, and authorized party. Production does not trust the local development email header.

The Clerk account alone does not grant business access. A matching Stonegate `User` must be active
inside the organization and have local role assignments.

### 5.2 Organization Scope

Operational records carry an organization ID. Service methods scope reads and writes to the
authenticated principal's organization. This allows one shared Stonegate workspace without moving
records between separate employee accounts.

### 5.3 Roles

Supported role keys and intended use:

| Role | Intended responsibility |
| --- | --- |
| `owner`, `founder_operator`, `ceo` | Full company authority and cross-role coverage |
| `administrator` | Broad platform administration without automatic owner-only authority |
| `acquisition_manager` | Lead Manager, team coordination, qualification, and acquisitions oversight |
| `acquisition_rep` | Acquisitions closer and seller appointment execution |
| `prospecting_caller` | Restricted VA calling assigned prospect records |
| `disposition_manager` | Buyer and disposition management |
| `disposition_rep` | Assigned disposition execution |
| `transaction_coordinator` | Contracts, closing milestones, documents, and coordination |
| `finance_accounting` | Internal books, evidence, banking, compensation, and reports |
| `marketing_manager` | Campaign and marketing measurement work |
| `read_only_partner` | Restricted transaction visibility |
| `restricted_vendor` | Narrow external-party transaction visibility |
| `ai_service` | Non-human service identity constrained by AI tool policy |

### 5.4 Permission Enforcement

The API uses granular permissions in addition to role-based navigation. Permission groups cover:

- viewing or editing all versus assigned leads
- underwriting edits and ARV approval
- offer approval and contract sending or modification
- buyer viewing, editing, and export
- financial, compensation, accounting-policy, journal, vendor, evidence, and banking access
- SMS, email, calls, recordings, conversations, assignments, and bulk communication
- user, credential, audit, deletion, operating-model, and AI-prompt administration
- acquisition operations and assigned calling-list work

`User.calling_enabled` is a separate capability switch. When enabled, authentication adds only
`calling_lists:work_assigned` to that user's effective permissions. This lets a person keep their
primary Acquisitions, Dispositions, or other staff role while receiving assigned calling batches.
The Prospecting service still scopes non-managers to their own batch entries.

The frontend hides irrelevant navigation, but API permission checks are authoritative. Hiding a tab
is not the security boundary.

### 5.5 User Provisioning

Owners create or activate a Stonegate user in Operations and assign the correct role. Each person
must use an individual Clerk login. Shared employee credentials are not part of the design.

Role-specific default routes include:

- VA Caller: `/os/prospecting`
- Dispositions: `/os/dispositions`
- Transaction Coordinator: `/os/transactions`
- Finance: `/os/finance`
- Marketing: `/os/marketing`
- restricted partners or vendors: `/os/transactions`
- owner and acquisitions roles: `/os`

## 6. Public Seller Website

### 6.1 Public Routes

| Route | Purpose |
| --- | --- |
| `/` | Main address-first direct-offer experience |
| `/get-a-cash-offer` | Two-step seller inquiry, separate SMS opt-in, and optional follow-up details |
| `/how-it-works` | Direct-sale process and expectations |
| `/about` | Stonegate company information |
| `/faqs` | Seller questions and tradeoffs |
| `/contact` | Public phone, email, inquiry availability, service-area confirmation, and property-meeting expectations |
| `/service-areas/metro-atlanta` | Initial market coverage, address confirmation, local review factors, seller situations, and service-area questions |
| `/sell-house-fast` | Fast-sale situation page |
| `/sell-house-needs-repairs` | Repair-heavy property page |
| `/sell-inherited-house` | Inherited-property page |
| `/privacy-policy` | Privacy and messaging data terms |
| `/terms` | Service and SMS terms |
| `/sign-in` and `/sign-up` | Clerk authentication |

### 6.2 Seller Intake

The two required steps collect the property address, seller identity, contact information,
preferred contact method, and consent. The lead is accepted at that point. The confirmation offers
an optional section for timing, condition, occupancy, asking-price, mortgage, and seller context;
a random 24-hour token connects those answers to the same lead without exposing CRM access.

At mobile widths, every public page also provides fixed **Call** and **Get Offer** actions. Their
conversion events include the mobile placement and source route. This bar belongs to the public
footer boundary, so it is never mounted in the operating system or authentication pages.

Public contact facts are centralized in `apps/web/src/app/site-config.ts`. The contact page,
homepage structured data, footer, mobile actions, and offer confirmation use those facts. Exact
staffed hours, county boundaries, an office address, and a numeric response-time promise are not
published until the owner confirms them.

Service-area content is centralized in `apps/web/src/app/service-areas.ts` and rendered through the
dynamic `/service-areas/[slug]` route. The initial Metro Atlanta page is the only published local
page. New entries require a genuinely served market and distinct useful content; the architecture
must not be used to generate repetitive city or county pages.

The homepage publishes Organization and WebSite structured data. The service-area page publishes
WebPage, Service, and BreadcrumbList data linked to the same organization identity. LocalBusiness
markup remains intentionally absent until Stonegate confirms a real staffed address that meets the
provider and search-engine requirements.

Public team identity is centralized in `apps/web/src/app/public-team.ts`. Only complete,
owner-approved active team records belong in that file, and their photographs live in
`apps/web/public/images/team/`. An empty list produces no public team markup. When records exist,
the single featured person appears in the homepage identity section, every approved person appears
on the About page, and matching Person records are linked to the Organization structured data.
Founder identity is a separate explicit field so homepage prominence cannot mislabel a salesperson.
Build-time validation blocks incomplete content, duplicate slugs, multiple featured people,
unsupported image formats, and common placeholder language. The approval and photograph workflow
is documented in `PUBLIC_TEAM_CONTENT.md`.

Submission creates or matches:

- contact and contact methods
- property
- lead
- consent evidence
- form submission evidence
- attribution touches
- conversion events
- speed-to-lead work
- a shared conversation and initial ownership context

Duplicate active submissions are matched using normalized phone, email, and property address.
Stonegate keeps the new form, attribution, and consent evidence while avoiding unnecessary
duplicate active leads.

### 6.3 SMS Consent

SMS consent is a separate unchecked choice. Evidence includes the consent wording version,
timestamp, source, IP address, and user agent. General permission to contact does not silently
become consent for recurring automated SMS.

### 6.4 Conversion Measurement

The public site records privacy-safe events for offer starts, form progress, validation friction,
abandonment, submit attempts, failures, successful submissions, phone clicks, and Core Web Vitals.
Marketing uses these events to evaluate funnel performance. Public event intake does not grant OS
access.

PC7 adds governed `MarketingExperiment` and `MarketingExperimentAssignment` records. A running
homepage CTA experiment is exposed through a read-only public endpoint. The browser makes a stable
anonymous 50/50 assignment and includes the experiment key, variant, session, and desktop/tablet/
mobile category with conversion events and seller intake. The API validates the running
experiment, prevents a session from switching variants, and links the assignment to the created
lead.

Marketing reports each version through assigned sessions, form starts, submissions, qualified
leads, appointments, executed contracts, funded deals, and collected revenue. Runtime and
per-version traffic thresholds control when the result becomes ready for human review; the system
does not choose a winner or change the public site autonomously.

### 6.5 Public Trust Proof

Marketing manages `PublicProofRecord` entries for reviews, seller stories, completed purchases,
and statistics. Each record stores the public content separately from its source URL or internal
evidence reference, usage-permission status and notes, material connection, visible disclosure,
calculation method, dates, sort order, and publication decision.

The lifecycle is `draft -> in_review -> published -> retired`. Editing a reviewed or published
record first returns it to draft, which immediately removes it from the public feed. Publishing
requires source evidence, permission review, and type-specific fields. Reviews and seller stories
require affirmative permission; named purchase proof also requires permission; statistics require
an as-of date and calculation method.

`GET /api/v1/public/trust-proofs` returns only published records with granted or documented
not-required permission. It omits internal references, permission evidence, staff identities, and
audit history. The homepage caches the sanitized feed for five minutes and returns no trust-proof
markup when the feed is empty. No self-serving Review or AggregateRating schema is generated.

## 7. Private OS Navigation

The live OS sidebar uses four stable groups and 11 owner destinations. Authorized legacy
workspaces remain available through the global **Tools** menu until their consolidation phase
reaches feature parity.

### 7.1 Work

**Home (`/os`)**

- Role-aware daily command center.
- Shows seller work, intervention counts, meetings, offers, and pipeline health.
- Hosts the owner-facing Executive Copilot.

**Inbox (`/os/inbox`)**

- Shared three-panel communication workspace.
- Views include Mine, Unassigned, Team, Needs Reply, Unread, Appointments, My Addresses, team
  inboxes, and authorized restricted inboxes.
- Supports lead, buyer, transaction, and general email contexts.

**Tasks (`/os/tasks`)**

- Unified daily work center for primary next actions, supporting tasks, governed approvals, and
  operational exceptions.
- Saved views include My Tasks, Due Today, Overdue, Upcoming, Unscheduled, Team, Approvals,
  Exceptions, and Completed, with role-aware visibility.
- Completing a primary action requires an outcome and a successor when its seller lead or deal
  remains active.
- Home, Seller Leads, seller records, and Tasks read the same primary next-action record.

**Calendar (`/os/calendar`)**

- Internal month, week, day, and agenda views.
- Combines appointments, field scheduling, and due work without requiring Google Calendar.

### 7.2 Operations And Acquisition Tools

The primary Operations destinations are Prospecting, Seller Leads, Deals, and Buyers. Campaign
management is a local Prospecting view. Lead Queue, Pipeline, and active Underwriting are local
Seller Leads views. Schedule, Dispatch, Appointment, and Availability are local Calendar views.

**Prospecting > Campaigns (`/os/prospecting?view=campaigns`)**

- Creates a campaign and keeps the selected campaign as the context for every downstream action.
- CSV prospect import, reusable mappings, validation previews, costs, batches, and campaign
  performance.
- Includes standard and contact-export PropStream presets, trust/company-to-person name fallback,
  five ranked phones with Cell/Landline evidence, four ranked emails, phone-specific DNC evidence,
  source export/list evidence, saved filter evidence, mixed-state preview warnings, and source-list
  appearance history.
- Refreshes match existing people, contact methods, properties, and source IDs without resetting
  prior outreach, callbacks, opt-outs, handoffs, or CRM leads.
- Prospecting cohorts preserve source, list type, market, script, date range, and call window for
  one-by-one calling.
- Work sessions preserve paid time, productive calling time, VA labor, and cohort attribution.
- Cold prospect records remain separate from CRM leads until a valid handoff.
- The selected campaign, local section, and deep-link context are preserved with `campaign`,
  `campaignView`, and `view` query parameters.
- Campaign management and My Calls load independently; opening one does not eagerly load the
  other subsystem.
- The former `/os/campaigns` route redirects to this view.

**Prospecting > My Calls (`/os/prospecting?view=my-calls`)**

- Assigned-caller workbench for VAs and any other staff explicitly enabled for cold calling.
- Caller-only accounts open directly to My Calls and cannot load campaign management.
- Shows the complete assigned shift through due, callback, correction, scheduled, waiting, and
  all-assigned queue views while one selected prospect remains the active calling context.
- Shows campaign/batch workload, ranked contact methods, approved script, prior attempts and
  commitments, structured disposition, callback, qualification, handoff, and Prospecting Copilot
  guidance.
- All VA prospecting is labeled **One-by-one calling**.
- Current prospect calls open through the device `tel:` handler and the VA records the result in
  Stonegate. External multi-line and predictive dialing are intentionally retired.

**Seller Leads (`/os/leads`)**

- Canonical seller workspace with Lead Queue, All Leads, Pipeline, and Underwriting local views.
- Lead Queue supports acceptance, guided qualification, dated next actions, appointments,
  exceptions, scorecards, and Lead Manager Copilot drafts.
- Authorized staff can create an internal lead for a warm call, referral, networking source, or
  other genuine opportunity. One submission creates contact methods, property, ownership,
  source, qualification context, follow-up, conversation, and initial note.
- All Leads supports owner, stage, search, saved views, seller preview, and direct next actions.
- Table and board modes operate on the same filtered records and preserve URL state.
- Opening a full seller record preserves the originating list, board, filter, and selected-seller
  context so **Back** returns to the same working view.
- Seller and transaction histories use the same chronological activity pattern for event title,
  supporting context, actor, and timestamp.
- Underwriting shows the active valuation queue; detailed comp work remains on the seller record.
- Archived records live at `/os/leads/archived`.
- `/os/lead-manager`, `/os/pipeline`, and `/os/underwriting` preserve old links by redirecting to
  the corresponding Seller Leads view.

**Calendar (`/os/calendar`)**

- Internal month, week, day, and agenda schedule.
- Dispatch with closer capacity, working-hours, territory, travel-buffer, and conflict checks.
- Appointment execution with preparation, walkthrough, photographs, seller-safe presentation,
  negotiation, outcome, and approved iPad signing.
- Manager Availability view for closer profiles and unavailable blocks.
- The former `/os/field-operations` route redirects while preserving appointment and lead context.

### 7.3 Deals And Deal Tools

**Deals (`/os/deals`)**

- Canonical employee workspace for contract preparation through funded closing.
- Reads the existing Deal, Transaction, Contract Package, Disposition Case, Buyer Offer,
  reconciliation, task, document, and checklist records without duplicating them.
- Provides Active, Closing Exceptions, Ready for Disposition, Buyer Needed, Finance Review, and
  Completed saved views with queue, table, and board displays.
- Preserves the selected view, display, deal, and record tab in the URL.
- Shows Contract, Closing, Disposition, and Finance as independent parallel states.
- Provides Summary, Contract, Closing, Documents, Parties, Disposition, Finance, and Timeline
  record sections. The specialist sections embed the existing server-governed controls.
- Loads transaction or disposition data only when its corresponding record section is active.
- Transaction and Disposition Copilots open as contextual drawers inside the Deal record and retain
  their existing draft, evidence, and human-review rules.
- Hides assignment fee, company profit, and company margin unless the user has financial or
  compensation visibility. Operational contract price remains visible to deal roles.

**Valuation Quality (`/os/settings/data-quality`)**

- Calibration scorecards, verified outcomes, provider adequacy, and methodology decisions.
- Restricted to users with data-quality or underwriting authority.

**Approvals (`/os/tasks?view=approvals`)**

- Permission-filtered Tasks view for human decisions such as offer ceilings and contract release.
- Approval records keep their domain-specific authority, evidence, decision, and audit rules.
- `/os/approvals` is a compatibility redirect to this Tasks view.

**Transactions (`/os/transactions`)**

- Compatibility and specialist setup route for contract-to-closing coordination. Normal daily
  work begins in Deals.
- Manages contract templates, packages, approvals, signatures, documents, parties, milestones,
  checklists, closing, and Transaction Copilot drafts.

**Dispositions (`/os/dispositions`)**

- Compatibility and specialist setup route for opening a new disposition case. Existing cases
  are worked from the Disposition and Finance sections of Deals.
- Manages deal packages, matches, campaigns, engagement, offers, proof, selection, reconciliation,
  and Disposition Copilot drafts.

**Buyers (`/os/buyers`)**

- Investor CRM with criteria, capacity, markets, proof-of-funds status, and provider discovery.
- Buyer selection and Summary, Criteria & Markets, Active Deals, and Proof & Capacity sections are
  URL-addressable. Buyer details open as a drawer on phone layouts, and related seller links return
  to the same buyer section.

### 7.4 Business

**Finance (`/os/finance`)**

- Revenue, deductions, compensation, double-entry books, vendors, bills, private evidence,
  statement import, bank reconciliation, financial reports, close workflow, CPA exports, Finance
  Copilot, and Tax Copilot.

**Marketing (`/os/marketing`)**

- Spend, public funnel performance, unit economics, offline conversion queue, and Marketing
  Copilot.
- Controlled homepage CTA experiments, stable variant assignment, device mix, downstream business
  outcomes, stopping thresholds, and recorded human decisions.

### 7.5 Administration And Management Tools

**Settings (`/os/settings`)**

- Primary administration entry point.
- Redirects to the first authorized administration section.
- Uses a stable permission-filtered local navigation for Company, Markets & Territories, People &
  Access, Communications, Integrations, Workflows, Data & Quality, Finance Policy, and AI &
  Automation.
- Direct access to a restricted section is rejected by the server-rendered page.
- Integrations reports provider readiness and missing environment-variable names without exposing
  credential values.

**My Setup (`/os/my-setup`)**

- Every staff member can review and accept assigned role expectations.

**People & Access (`/os/settings/people`)**

- Owner and manager administration for users, access roles, cold-calling eligibility, and teams.
- This is where staff records are created before the matching person signs in with Clerk.
- Cold-calling eligibility is controlled independently of the main access role.

**Markets & Territories (`/os/settings/markets`)**

- Market and territory setup plus market-launch evidence.
- Campaign and prospect creation remain in Prospecting.

**Communications (`/os/settings/communications`)**

- Embeds the authenticated email administration workspace for senders, routing, signatures,
  mailbox grants, and unresolved inbound assignments.
- Voice-line administrators can add company-owned numbers and update line labels, status, default
  routing, and inbound behavior without receiving email-administration access.

**Workflows And Data Quality**

- `/os/settings/workflows` owns approved follow-up plans.
- `/os/settings/data-quality` owns duplicate review.

**Floating Help**

- A blue chat button remains available at the bottom-right of every signed-in OS workspace.
- Selecting it opens a compact Help conversation without leaving the current work.
- Retrieves approved Markdown sections through the authenticated API.
- Filters owner and specialist topics by the employee's current role.
- Returns document, heading, and source excerpts with every supported answer.
- Has no access to live seller records and cannot perform operational actions.

**Company (`/os/settings/company`) And Finance Policy (`/os/settings/finance-policy`)**

- Company owns seats, counterparties, and role acceptance.
- Finance Policy owns compensation plans, role credits, and policy history.

**AI & Automation (`/os/settings/ai`)**

- Owner-controlled agent portfolio, copilots, capability contracts, model runtime, evaluation
  library, traces, budgets, shutdown controls, promotions, and external automation policy.

Legacy `/os/operations`, `/os/inbox?manage=email`, `/os/operating-model`, and `/os/ai` links
redirect to their new owners.

## 8. End-To-End Operating Lifecycle

### 8.1 Market And Campaign Setup

1. An owner or manager defines a market and territory.
2. A campaign records channel, source, dates, budget, and ownership.
3. Campaign expenses record lists, enrichment, software, ads, mail, and VA labor.
4. A comparison cohort records source, list type, market, script, calling window, date range, and
   one-by-one calling method.
5. A CSV is validated with a saved mapping before import.
6. Exact file replay, invalid rows, duplicate prospects, and imported suppression flags are
   retained as explicit outcomes.
7. Valid prospects enter a cohort-linked calling batch and are assigned to an active staff member
   with cold calling enabled.

### 8.2 Prospecting

1. A non-manager caller sees only assigned callable prospect records.
2. The approved script and qualification fields guide the call.
3. Every attempt records outcome, notes, callback, script evidence, cohort, calling method, answer
   class, right-party evidence, interest, permission, and governing timestamps.
4. Wrong numbers and explicit opt-outs stop inappropriate follow-up.
5. An interested seller creates a structured handoff.
6. The Prospecting Copilot can prepare a brief and coaching; it does not place autonomous calls.

### 8.3 Warm Handoff And Lead Creation

1. A submitted handoff converts the prospect into a CRM lead without losing campaign attribution.
2. Contact, property, conversation, qualification answers, attempts, and appointment context are
   preserved.
3. The lead is assigned to acquisitions; owners can become watchers.
4. The original caller loses prospect editing access after handoff but the original activity
   remains attributable.
5. Website inquiries enter the same Lead Manager queue through a separate consented intake path.
6. The Lead Manager accepts, returns for correction, or terminally rejects the handoff with a
   structured decision code.
7. A handoff counts as an accepted warm lead only after accepted status, right-party contact,
   interest, follow-up permission, and every required qualification answer are all recorded.

### 8.4 Lead Management

1. The Lead Manager accepts the work within the configured SLA.
2. The current approved qualification script captures motivation, condition, timeline, occupancy,
   price context, title or mortgage issues, and next action.
3. Missing or conflicting information remains visible instead of being guessed.
4. The Lead Manager schedules a call, follow-up, or closer appointment.
5. Overdue handoffs and neglected leads produce tasks or notifications.
6. The Lead Manager Copilot drafts summaries, questions, replies, and next steps for human review.

### 8.5 Appointment And Dispatch

1. The internal calendar evaluates closer availability, territory, working hours, travel buffer,
   capacity, and conflicts.
2. An explainable candidate snapshot is stored when scheduling.
3. A manager can override a conflict only with a reason.
4. The closer receives the appointment, seller context, qualification, task state, and meeting
   preparation needs.

### 8.6 Field Appointment

1. The closer opens the appointment workspace on a phone or iPad.
2. A meeting brief combines seller facts, property context, qualification, and approved analysis.
3. The walkthrough records condition, repair scope, notes, and photographs.
4. The seller presentation exposes selected market evidence but hides Stonegate's internal offer
   authority, assignment fee, buyer profit, and negotiation history.
5. Reviewed field evidence creates a new repair estimate and draft underwriting version; it does
   not overwrite an approved analysis.

### 8.7 Underwriting And Offer

1. Stonegate validates the subject address and canonical property facts.
2. RentCast supplies the subject record and recorded-sale candidates when available.
3. Safe address variants may be retried when the provider misses the original string.
4. Optional bounded OpenAI web research can collect cited public-record evidence; it cannot set
   ARV or offer values.
5. Comparable candidates are screened for geography, recency, property type, size, bed/bath,
   condition, and material price or price-per-square-foot outliers.
6. Selected and rejected comps retain scores and reasons.
7. The engine produces an ARV range, as-is range, repair result, buyer economics, offer scenarios,
   confidence tier, and review flags.
8. Investor and client PDFs use the same immutable analysis with different disclosure boundaries.
9. A human creates a negotiation plan tied to one saved underwriting version.
10. Approval establishes opening, target, stretch, and hard-ceiling authority.
11. Concessions and price discussions are appended to the negotiation ledger.

### 8.8 Contract And E-Signature

1. An approved, versioned contract template provides the base document.
2. Stonegate creates a contract package from CRM, property, offer, and party facts.
3. Missing or conflicting required facts block release rather than being invented.
4. An authorized person requests approval and then sends through the configured e-sign provider.
5. SignWell hosts the signing ceremony; Stonegate stores envelope, recipient, event, and completed
   document evidence.
6. The same provider flow can be launched on an iPad for an in-person seller signature.
7. Manual sent and executed states remain available for controlled fallback evidence.

### 8.9 Transaction Coordination

1. The executed acquisition agreement opens the controlled transaction workflow.
2. Parties, title/closing information, earnest money, inspection or due-diligence dates, closing
   date, assignment strategy, and documents remain attached to the transaction.
3. Checklist items and events make blockers and ownership visible.
4. The Transaction Copilot may identify missing facts and draft coordination work.
5. It cannot change legal terms, send a contract, or represent legal review.

### 8.10 Buyer And Disposition

1. The disposition case is opened from the contracted transaction.
2. Staff approve the property package before marketing.
3. Buyers are matched against markets, property criteria, price, capacity, activity, and proof.
4. DealMachine can provide external buyer candidates when its adapter is activated.
5. Candidates are reviewed before import; external data does not overwrite trusted buyer records.
6. Staff record outreach, engagement, offers, deposits, and proof.
7. Buyer selection is a human approval.
8. The Disposition Copilot can rank and explain candidates or draft outreach in review-only mode.

### 8.11 Closing, Reconciliation, And Compensation

1. Closing evidence records the funded transaction.
2. Reconciliation starts with actual assignment revenue and approved deal deductions.
3. The active compensation plan and role credits calculate proposed payouts.
4. Disposition can use the human-led or AI-assisted operating mode defined by the approved plan.
5. Payout approval and payment status remain human controlled.
6. Reconciliation feeds source-linked accounting entries and profitability reporting.

### 8.12 Accounting And Management

1. Operational source records create draft accounting work through approved posting rules.
2. Journal entries must balance before approval or posting.
3. Posted entries are immutable; corrections use reversals.
4. Vendors, bills, evidence, bank statements, transaction matches, and reconciliations remain
   auditable.
5. Financial reports use posted journals only.
6. Period close and CPA export expose unresolved blockers.
7. Finance, Tax, Marketing, and Executive Copilots prepare evidence-linked review drafts without
   posting, paying, filing, or changing policy.

## 9. CRM And Work Management

### 9.1 Lead Record

The lead record is the complete seller workspace. It combines:

- seller and property facts
- source and attribution
- stage, owner, status, and next action
- qualification and missing questions
- notes and follow-ups
- appointments
- underwriting versions and reports
- offer authority and negotiation ledger
- transaction and buyer offers
- communications and consent
- recent activity and audit evidence

The canonical internal detail route is `/os/leads/{lead_id}`. The legacy `/leads/{leadId}` route
exists in the web tree but should not be presented as the primary OS workflow.

### 9.2 Lead Stages

Stages represent business state, not employee ownership. Assignment can change without creating a
new lead. Pipeline progression is controlled by the actual workflow and may include new, contact,
qualified, appointment, analysis, offer, contract, transaction, disposition, closed, lost, or
archived families.

### 9.3 Tasks And Notifications

Tasks carry ownership, due date, completion, lead and optional deal context. `work_kind`
distinguishes the single primary next action from supporting work and operational exceptions.
Primary completion records an outcome and completion notes and links the replacement action; an
active source cannot be silently left without a successor. Notifications communicate events such
as handoffs, appointments, communication assignment, overdue response, owner escalation, and
approval needs.

Workers can create escalation evidence, but staff remain responsible for resolving the underlying
work. Approvals are aggregated into Tasks for discovery but remain separate governed records.

### 9.4 Duplicate Handling

Duplicate scanning is conservative. A reviewed merge preserves evidence, records a merge snapshot,
and archives the secondary record. Permanent deletion is a separate permission-controlled action.

## 10. Shared Communications

### 10.1 Conversation Model

A conversation is a durable thread, not merely a contact card. It can be linked to a lead,
transaction, buyer, or general business context. It records:

- channel-neutral timeline
- structured participants
- assignment and team
- source and receiving alias
- watchers
- unread state
- response status and deadlines
- communication records and dispatch attempts
- provider events
- attachments
- calls, recordings, and transcripts
- internal notes

### 10.2 Inbox Layout

- Left pane: conversation views, search, filters, and threads.
- Middle pane: chronological timeline and channel composer.
- Right pane: context, seller or business summary, assignment, notes, and follow-up state.
- Mobile: the panes become navigable views instead of being compressed together.

### 10.3 Email

The current provider is Resend. Stonegate supports:

- approved company aliases such as named, offers, buyers, and accounting addresses
- user and team sender grants
- restricted mailbox visibility
- new general email without a fake property lead
- To, CC, BCC, subject, text, HTML, templates, signatures, and attachments
- outbound idempotency and visible provider status
- signed inbound webhooks and retrieval
- `Message-ID`, `In-Reply-To`, and `References` threading
- exact reply, provider-thread, participant, alias, and bounded fallback routing
- owner review of ambiguous routing
- first-response and next-response deadlines
- assignee, watcher, team, and owner-escalation notifications

The old Google OAuth implementation remains only as superseded code compatibility. It is not the
selected operating model and should not be configured.

### 10.4 SMS

The Twilio SMS implementation supports:

- approved Messaging Service or sender number
- outbound from the shared conversation
- signed inbound and delivery callbacks
- provider event idempotency
- delivery, failure, and inbound state
- STOP and START processing
- suppression and consent controls
- number normalization
- organization and permission scope

Stonegate's dedicated A2P campaign remains externally pending. Do not use another company's
Messaging Service, campaign, number, or consent description.

### 10.5 Voice

The Twilio Voice implementation supports:

- company voice lines
- scoped browser access tokens
- call intents tied to a conversation
- outbound and inbound routing
- call status and dial result callbacks
- missed-call tasks
- private recordings
- disclosure state
- transcript review

Voice requires the Account SID, Auth Token for webhooks, API key SID and secret for browser tokens,
TwiML App SID, company number, and callback configuration. A single inbound webhook alone does not
provide secure browser calling.

### 10.6 Call Intelligence

When recording is deliberately enabled:

1. Twilio reports the completed recording.
2. The worker retrieves eligible audio.
3. OpenAI transcription produces speaker-aware transcript evidence.
4. structured notes identify motivation, condition, timeline, occupancy, price, objections,
   commitments, and next action.
5. a human reviews the transcript and notes before critical CRM fields change.
6. retention and early deletion are tracked.

## 11. Underwriting System

### 11.1 Evidence Hierarchy

Stonegate separates:

- CRM-entered subject facts
- provider-returned subject facts
- recorded-sale comparables
- operator condition and repair evidence
- cited secondary public evidence
- verified outcomes such as appraisals, expert reviews, resales, and closed values

Every important fact should retain its source and timestamp. Disagreement lowers confidence or
requires review; it should not be silently averaged away.

### 11.2 Complete Analysis

The one complete-analysis workflow performs:

1. address normalization and identity validation
2. provider-safe address retries
3. subject fact reconciliation
4. recorded-sale search
5. candidate screening and scoring
6. optional bounded public-record research
7. comparable weighting
8. ARV and as-is range calculation
9. repair and contingency math
10. buyer economics and Stonegate offer scenarios
11. confidence factors and review flags
12. immutable analysis storage

### 11.3 Offer Math

The configured baseline uses a low and high percentage of ARV, normally 65% and 70%, then accounts
for repairs, assignment fee, transaction reserve, and configured buyer costs. The result is a
scenario and authority range, not a guaranteed appraisal or mandatory seller offer.

The exact method and controls live in `UNDERWRITING_COMP_METHOD.md`.

### 11.4 Report Types

- **Investor PDF:** full comparable evidence, adjustments, repair source and detail, buyer
  economics, offer framework, confidence, limitations, and audit identifiers.
- **Client PDF:** seller-appropriate market evidence and explanation without Stonegate's internal
  assignment fee, buyer profit, hard ceiling, or negotiation strategy.

Reports remain available when renovation status is unconfirmed. Uncertainty must be disclosed
rather than used to hide the result.

### 11.5 Calibration

Verified outcomes compare prediction with reality by market. Scorecards track ARV bias, absolute
error, range coverage, repair variance, contract variance, disposition variance, operator
overrides, and provider failure patterns.

No formula self-adjusts from these results. Method or provider changes require a versioned
decision, frozen evidence, human notes, and the configured minimum case count.

## 12. Contracts, Documents, And E-Signature

### 12.1 Document Model

Stonegate maintains versioned contract templates, transaction documents, extracted facts,
packages, recipients, provider events, and immutable completion evidence.

Document storage can use the database or S3-compatible private object storage. Downloads are
permission checked and can use short-lived links. Retention and malware-scan state are explicit.

### 12.2 Contract Templates

The current Georgia investor purchase agreement is an internal working template pending later
professional review. Template content must be approved in Stonegate and configured with the
matching SignWell template ID before automated sending.

AI may populate approved fields and identify missing information. AI must not invent legal terms,
change approved language, select legal strategy, or send without authority.

### 12.3 In-Person Signing

The closer can start the same SignWell signing ceremony from the field appointment on an iPad.
The seller signs in the hosted provider flow; Stonegate records the envelope and completed
document. This does not create a separate contract or signature system.

## 13. Buyers And Dispositions

### 13.1 Buyer CRM

Buyer records can retain:

- identity and contact information
- active or inactive status
- preferred markets and property types
- minimum and maximum price
- rehab tolerance and strategy
- proof-of-funds evidence and expiration
- capacity and recent activity
- engagement and offer history

### 13.2 Buyer Discovery

DealMachine is the selected first external buyer-data adapter. The workflow:

1. Runs discovery for an active disposition case.
2. Stores the provider query and raw candidate evidence.
3. Normalizes, scores, and explains candidates.
4. Requires a human to review before import.
5. Links imported records to the existing buyer CRM.

The subscription can remain off until Stonegate is close to having a contract to disposition.
Provider activation should not require rebuilding the buyer workflow.

### 13.3 Disposition Authority

AI can organize evidence, rank buyers, and draft communication. Humans approve the package,
campaign release, buyer selection, contract terms, and reconciliation.

## 14. Finance And Accounting

### 14.1 Source Of Truth

Stonegate contains its own double-entry accounting ledger. QuickBooks is not required as the
operational source of truth. External CPA exports remain available.

### 14.2 Ledger Controls

- Chart of accounts and accounting profile
- Open, review, close, reopen, and year-end period states
- Balanced journal preparation
- Separate approval and posting authority
- Immutable posted journals
- Reversal entries instead of edits
- Source links to deals, revenue, bills, payouts, or evidence
- Approved posting rules for operational events

### 14.3 Vendors And Evidence

Finance supports vendors and counterparties, coded bills, W-9 status, invoices, receipts, payment
evidence, closing statements, private documents, and financial obligations. Sensitive data should
use restricted evidence storage rather than ordinary notes.

### 14.4 Banking

Current banking is import-based:

- store company account labels and optional last four digits
- preview CSV mapping
- retain original statement evidence
- prevent duplicate files and transactions
- manually match to posted operating-cash journals
- document ignored non-operating lines
- reconcile only when all included lines are resolved and balances agree

Stonegate does not initiate payments or bank transfers.

### 14.5 Reports

Posted journals power:

- Profit and Loss
- Balance Sheet
- Cash Flow
- Trial Balance
- General Ledger
- receivable and payable schedules
- commission payable and payment history
- deal profitability
- close-readiness checklist
- CPA ZIP export

### 14.6 Finance And Tax Copilots

The Finance Copilot can suggest classifications, balanced draft entries, transaction matches,
variance explanations, and close work. The Tax Copilot can identify potential categories,
missing evidence, and CPA-review questions.

Neither Copilot can post entries, close periods, pay vendors, promise deductibility, file returns,
or make final tax determinations.

## 15. Marketing Measurement

Marketing combines:

- campaign costs
- prospect and handoff outcomes
- public conversion events
- qualified leads
- appointments
- signed contracts
- funded deals
- cost per result and deal profitability

Offline conversion adapters exist for Google Data Manager and Meta Conversions API. Contact
identifiers are normalized and hashed, event keys are stable, and retries are audited. External
delivery remains disabled until Stonegate configures approved ad accounts, conversion actions,
credentials, and acceptance tests.

Marketing also owns the public trust-proof library. `marketing:manage_public_proof` allows Owner
and Marketing Manager roles to prepare, review, publish, unpublish, and retire proof. Other
marketing viewers can inspect status but cannot change public content. Every state transition is
written to the audit log.

`marketing:manage_experiments` allows Owner and Marketing Manager roles to prepare, start, pause,
resume, and complete controlled public-site tests. Only one running test may use the same surface.
Every lifecycle decision is written to the audit ledger.

## 16. AI Copilot System

### 16.1 Copilot Versus Agent

A **Copilot** is the staff-facing assistant embedded in the workspace where the person already
works. It presents a brief, draft, recommendation, warning, or proposed next action.

An **agent** is a backend specialist capability that can analyze information or use an allowed
tool. Several backend agents can support one staff-facing Copilot.

Employees generally interact with copilots, not a collection of separate chat rooms.

### 16.2 Current Copilots

| Copilot | Location | Current role |
| --- | --- | --- |
| Prospecting | Prospecting | Pre-call brief, script guidance, disposition quality, coaching |
| Lead Manager | Lead Desk | Priority, seller brief, missing facts, reply and task proposals |
| Acquisitions | Calendar Appointment | Meeting preparation, evidence gaps, negotiation support |
| Transaction | Transactions | Checklist, document facts, blockers, coordination drafts |
| Disposition | Dispositions | Package gaps, buyer ranking, outreach and offer review |
| Finance | Finance | Classification, journal, match, variance, and close guidance |
| Tax | Finance | Evidence and classification questions for professional review |
| Marketing | Marketing | Funnel, spend, attribution, and campaign recommendations |
| Executive | Dashboard | Cross-functional exceptions, priorities, and management review |

### 16.3 Control Plane

The AI system records:

- agent and Copilot definitions
- prompt versions
- capability contracts
- data-governance policies
- knowledge sources and quality rules
- tool permissions
- model and capability runtime policies
- run, tool-call, knowledge-use, and cost logs
- golden evaluation datasets and cases
- reviews, comparisons, promotions, and rollbacks
- external-action policies and attempts
- orchestrator events and failure evidence

### 16.4 Autonomy

Copilots are enabled but not autonomous. Their normal state is draft-only or approval-gated.
Consequential actions remain with authorized humans, including:

- offers and ARV approval
- contract language and sending
- buyer selection
- payments and journal posting
- compensation changes
- tax or legal conclusions
- suppression and consent overrides
- user permissions

Future autonomy is capability-specific. One reversible action may be promoted only after its own
evaluation, supervised pilot, monitoring, budget, canary, and rollback requirements pass.

## 17. Background Processing And Reliability

The deployed API worker handles recurring operational jobs such as:

- worker heartbeat
- email synchronization, webhook recovery, and response escalation
- call recording processing and transcription
- recording retention
- overdue handoff and workflow escalation
- provider retry work where implemented

Background failures are stored as durable operational records. Repeated failures can notify an
owner-controlled webhook. API readiness can require a fresh worker heartbeat.

Optional Sentry integration exists for web, API, and worker error reporting. It is not required for
core application behavior.

Database backup, guarded restore verification, deployment smoke tests, and scheduled production
readiness checks exist as operational tools. A real restore drill remains an owner acceptance
task.

## 18. Audit, Evidence, And Corrections

Stonegate favors append-only evidence for material decisions:

- activity events describe operational history
- audit events identify actor, action, target, and before/after context
- provider events preserve external callbacks
- assignment events preserve ownership changes
- AI reviews preserve acceptance, rejection, and correction
- underwriting versions preserve prior calculations
- negotiation ledgers preserve price movement
- posted accounting entries use reversals
- completed documents retain checksums and provider evidence

Routine corrections should create a new version, review, reversal, event, or status transition
instead of erasing the old decision.

## 19. Security And Compliance Boundaries

Core boundaries include:

- Clerk authentication plus Stonegate-local RBAC
- organization-scoped reads and writes
- individual employee accounts
- restricted VA, vendor, partner, finance, recording, and mailbox access
- signed provider webhooks
- event and dispatch idempotency
- consent and suppression evidence
- permission-gated downloads
- secret values stored in environment configuration, not documentation
- human approval for consequential financial, contractual, offer, buyer, and AI actions

The platform contains controls, but software does not replace legal, tax, accounting, employment,
telemarketing, recording, or real-estate advice.

## 20. External Integrations

| Provider | Purpose | Code status | External status |
| --- | --- | --- | --- |
| Clerk | Authentication | Implemented | Active |
| Render | Hosting, Postgres, key value | Implemented | Active |
| OpenAI | Copilots, bounded research, transcription | Implemented | API configured; production pilots remain |
| RentCast | Subject and recorded-sale data | Implemented | Configured; address coverage varies |
| Resend | Outbound and inbound operational email | Implemented | DNS and webhook configured; acceptance remains |
| Twilio | SMS, Voice, recordings | Implemented | Dedicated A2P/number acceptance pending |
| SignWell | Hosted e-signature | Implemented | Activation and acceptance pending |
| DealMachine | Buyer discovery | Implemented adapter | Subscription/API intentionally deferred |
| S3-compatible storage / R2 | Private document storage | Implemented option | Activation optional/pending |
| ClamAV | Document malware scanning | Implemented option | Disabled |
| Sentry | Error monitoring | Implemented option | Deferred |
| Google Data Manager | Offline ad conversions | Implemented adapter | Credentials and acceptance pending |
| Meta Conversions API | Offline ad conversions | Implemented adapter | Credentials and acceptance pending |

## 21. Data Domain Map

The primary SQLAlchemy model file contains 189 operational model classes. They group into:

### Identity And Organization

`Organization`, `User`, `Role`, `Permission`, `RolePermission`, `RoleAssignment`, `Team`,
`TeamMembership`.

### Markets, Campaigns, And Prospecting

`Market`, `Territory`, `Campaign`, `Prospect`, import mapping/batch/row records, suppression checks,
prospecting cohorts, paid/productive work sessions, cohort-attributed campaign costs, calling
batches and entries, script versions, evidence-classified attempts, structured handoffs, Copilot
recommendations, reviews, and call quality.

### CRM And Seller Evidence

`Contact`, `ContactMethod`, `Property`, `Lead`, `ConsentRecord`, `SuppressionRecord`,
`LeadFormSubmission`, `AttributionTouch`, `ConversionEvent`, qualification scripts, cases, and
sessions.

### Communications

`Conversation`, watchers, assignments, context links, provider events, communication records,
participants, dispatches, email accounts, aliases, grants, templates, attachments, voice lines,
call intents, calls, recordings, and transcripts.

### Appointments And Field Acquisitions

`Appointment`, `CalendarEvent`, closer profiles, territory coverage, availability blocks, dispatch
records, meeting briefs, inspections, photos, negotiation sessions, underwriting transfers, and
Acquisitions Copilot records.

### Underwriting And Offer Governance

`UnderwritingVersion`, `UnderwritingMarketAnalysis`, calibration cases and decisions,
`RepairEstimate`, `OfferNegotiationPlan`, `OfferConcession`, and `OfferNegotiationEvent`.

### Contracts And Transactions

`Deal`, `Transaction`, checklist items, contract templates and packages, transaction documents and
facts, e-sign envelopes, recipients and events, provider configuration, parties, events, and
Transaction Copilot records.

### Buyers And Dispositions

`Buyer`, criteria, proof documents, discovery runs and candidates, offers, disposition cases,
matches, campaigns, engagements, Copilot records, reconciliation, payouts, revenue, deductions,
operating mode, and role credits.

### Company Operations

Compensation plans and roles, market launch checklists, operating seats, counterparties, staff role
acceptance, compliance policies and records, compensation calculations, and marketing spend.

### Accounting

Accounting profile, accounts, periods, journals, lines, posting rules, source links, obligations,
vendors, bills, bill lines, finance documents, bank accounts, imports, transactions, matches,
reconciliations, and offline conversion exports.

### AI Governance

Agent, prompt, tool-permission, Copilot, mapping, capability, governance, knowledge, quality,
runtime, external-action, orchestrator, run, tool, evaluation, comparison, and promotion records.

### Shared Platform Operations

`ApprovalRequest`, `Task`, `CallingList`, `CallingListEntry`, `SavedView`, `Notification`,
`DuplicateCandidate`, `LeadMergeEvent`, follow-up plans and enrollments, `ActivityEvent`,
`AuditEvent`, `WorkerHeartbeat`, and `OperationalFailure`.

## 22. Testing And Quality Gates

Current repository verification includes:

- API unit and integration tests under `apps/api/tests`
- 52 API test modules
- Ruff linting
- MyPy type checking
- Next.js lint and production build commands
- Alembic migration execution
- local synthetic demo seed
- simulated email and SMS
- backup and restore verification scripts
- production smoke checks
- GitHub Actions CI

Standard commands:

```bash
npm run lint:api
npm run typecheck:api
npm run test:api
npm run lint:web
npm run build:web
```

Provider-backed workflows also require controlled acceptance. Passing unit tests does not prove
DNS, webhook, carrier, mailbox, signing, data-provider, or advertising account configuration.

## 23. Known Boundaries And Remaining Proof

The major product workflows are implemented. The remaining risk is primarily production
acceptance and evidence:

- Twilio A2P approval and dedicated SMS/Voice end-to-end tests
- Resend controlled sender, reply, routing, attachment, bounce, and escalation tests
- SignWell template, webhook, remote signature, and iPad signature acceptance
- DealMachine subscription and buyer-data acceptance when deal volume justifies it
- real Georgia underwriting outcomes and operator calibration
- first CPA-reviewed opening balances, bank reconciliation, month close, and report package
- ad-provider credential setup and offline conversion acceptance
- role acceptance with actual staff accounts
- supervised Copilot pilots using redacted Stonegate cases
- PropStream production export acceptance using Stonegate's implemented source membership,
  ranked-contact, refresh-safe, and deterministic cohort workflow
- real-VA acceptance of the one-by-one calling, callback, and warm-handoff workflow
- real backup restoration and optional monitoring-provider configuration

These are tracked in `FINISHING_ROADMAP.md`.

## 24. Documentation And Help System

`USER_MANUAL.md` is the current **How To Use Stonegate OS** guide. It covers each operating
workspace, role handoff, provider state, ordinary procedure, and common failure path in
nontechnical language.

`UI_CONTROL_REFERENCE.md` is the current interface dictionary. It documents the public website
and every production OS workspace by section, including the purpose and effect of meaningful
buttons and fields, prerequisites, permission or workflow blockers, disabled states, and the
result a user should expect. It also defines the answer contract for precise help-assistant
questions.

`SETUP_MANUAL.md` is **How To Set Up And Maintain Stonegate**. It gives the owner nontechnical
provider, account, staff, Render, DNS, webhook, acceptance, backup, and maintenance instructions.
`SETUP_REFERENCE.md` remains the exact technical variable and command inventory.

The floating Help panel is mounted in the authenticated OS shell. The API:

1. reads canonical Markdown from the deployed repository
2. splits sources by heading
3. applies document and section role scopes
4. retrieves the strongest lexical matches
5. optionally asks the configured OpenAI model to summarize only those sources
6. falls back to a deterministic source excerpt when OpenAI is unavailable
7. returns structured document, heading, and excerpt citations
8. accepts at most six recent local conversation turns for natural follow-up context

Recent Help turns are supplied by the open browser panel and are not stored as business records.
The API treats them as untrusted context, reapplies the current employee's role boundary across the
recent topic, and never accepts earlier answer text as an approved factual source. Approved
role-visible documentation remains the only answer source.

The Help interface safely renders a limited answer format using React elements: paragraphs,
headings, numbered steps, bullets, bold labels, inline code, and numbered source controls. It does
not render model-provided HTML. Selecting an inline source number opens the matching approved
document excerpt.

Help does not query live seller, buyer, transaction, communication, or accounting records. It has
no action tools and is not a substitute for operational Copilots. Future optimization may add
answer-gap analytics and semantic retrieval after real staff questions justify it.
