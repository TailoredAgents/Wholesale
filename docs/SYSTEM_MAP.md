# Stonegate Home Buyers System Map

Last verified against the repository: August 8, 2026

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
| Resend two-way email | Implemented and configured with UUID-fenced leases, route checkpoints, bounded retry, restricted routing, and manager-only dead-letter recovery; controlled mailbox acceptance and malware decision remain |
| Twilio SMS | Implemented; internal new-lead alerts cover website and Facebook intake and have prior delivery evidence, but require repeat acceptance after the worker credential correction; seller-facing SMS acceptance remains |
| Twilio Voice | Implemented and processing recordings/transcripts; full routing, recording, failure-recovery, retention, and deletion acceptance remains |
| RentCast property data | Implemented; provider coverage varies by address |
| RealEstateAPI property intelligence | Implemented and active; controlled property research passed |
| OpenAI copilots | Implemented in governed draft-only form; production pilots remain |
| SignWell e-signature | Implemented; provider activation and controlled acceptance remain |
| DealMachine buyer discovery | Legacy optional adapter; disabled and removable after subscription cancellation |
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
- Provider callbacks enter through dedicated webhook routes. Resend and Twilio callbacks are
  signature validated. SignWell verification binds organization-specific webhook credentials to
  the matching organization's envelope and retains duplicate, stale, or out-of-order events
  without regressing terminal state. The SignWell HMAC covers event type/time rather than the full
  document/signer/body payload, so within-organization provider reconciliation remains an external
  acceptance control. The intentionally secretless Zapier lead route uses the compensating controls
  described in the Marketing section and does not prove Meta provenance cryptographically.
- The production worker executes repeatable background jobs and records independent liveness,
  main-loop progress/current-operation, and failure evidence.
- External AI and provider outputs never replace source records silently.

### 4.3 Database Evolution

The database has 94 numbered Alembic migrations through `0094_esign_send_intents`. Migrations are
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
configured, and authorized party. `APP_ENV` accepts only `local`, `test`, or `production`.
Production API startup fails when the Clerk issuer, explicit or issuer-derived JWKS endpoint,
secret key, or a non-local HTTPS authorized party is missing. The protected web routes return `503`
in production when Clerk keys are unavailable instead of passing the request through.

Development-header authentication is off by default. A local or test environment must explicitly
set `DEV_AUTH_ENABLED=true` before `X-Dev-User-Email` is accepted; production always rejects it.

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

Approval visibility and decisions are checked against the request type in both the approval API and
the Tasks approval feed. Offer ceilings and concessions need offer-approval authority; contract
packages need contract-send authority; AI promotions and tool calls need AI-prompt authority; and
follow-up SMS or email needs acquisition-operations authority. Without `audit:view`, a person sees
only approval types covered by their permissions; `audit:view` is the only blanket organization-
wide read authority and still grants no decision authority. Unknown approval types have no
decision path.

### 5.5 User Provisioning

Owners create or activate a Stonegate user in **Settings > People & Access** and assign the correct role. Each person
must use an individual Clerk login. Shared employee credentials are not part of the design.

Role-specific default routes include:

- VA Caller: `/os/prospecting?view=my-calls`
- Lead Manager: `/os/leads?view=queue`
- Acquisitions Closer: `/os/calendar?view=day`
- Dispositions: `/os/deals?view=ready-for-disposition`
- Transaction Coordinator: `/os/deals?view=closing-exceptions`
- Finance: `/os/finance`
- Marketing: `/os/marketing`
- restricted partners or vendors: `/os/deals`
- owner and administrator roles: `/os`

## 6. Public Seller Website

### 6.1 Public Routes

| Route | Purpose |
| --- | --- |
| `/` | Main address-first direct-offer experience |
| `/get-a-cash-offer` | Focused two-step seller inquiry with address-stage capture, passive phone/email authorization, separate optional SMS opt-in, and an unnumbered optional enrichment section after confirmation |
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

The first visible step requires only a complete property address. Selecting **Continue** captures
that address under a browser-generated `intake_attempt_id` and creates a cold
address-only CRM lead. The record has a placeholder contact, no contact methods or consent, and the
canonical `qualification_context.website_intake_status="address_only"` marker. Staff sees it in
**Leads > Address Only** with **Skip trace needed**.

Address-only capture is evidence and prospect-research work, not a completed seller inquiry. It
queues one internal SMS per eligible employee labeled **Stage 1 filled**, with the address and a
clear contact-details-pending warning. It does not create a conversation, speed-to-lead task,
property-research job, AI lead-preparation job, general staff notification, or seller-contact
automation. Stonegate may research/skip trace the owner, but staff must manually check DNC status
before any cold outreach; the intake path does not perform an automatic DNC check.

The second visible step requires name and phone, accepts optional email, displays passive phone/email
authorization, and offers a separate unchecked recurring automated SMS choice. Submitting it
promotes the same contact, property, lead, and form-submission record to
`website_intake_status="completed"`; it does not create a second lead. Normal conversation,
property-research, AI, speed-to-lead, and notification workflows start only at this point. A second
deduplicated employee SMS labeled **Stage 2 filled** includes the completed seller contact. The
confirmation then offers an unnumbered optional section for desired selling timeline,
condition, occupancy, asking price, mortgage, repairs, and seller context. None of those details is
required. A random 24-hour token adds those answers to the same lead without exposing CRM access.

At mobile widths, every public page also provides fixed **Call** and **See My Options** actions. Their
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

The address stage creates or reuses:

- property
- cold address-only lead and placeholder contact
- incomplete form-submission evidence
- attribution touches
- the first-party `address_capture` event and Meta `Lead`
- one durable `website_form_stage_1` internal employee SMS per eligible recipient

The contact stage promotes that same record and adds or starts:

- real seller identity and contact methods
- phone/email and optional SMS consent evidence
- completed form-submission evidence
- the first-party `contact_complete` event and Meta `Contact`
- one durable `website_form` Stage 2 employee SMS per eligible recipient
- speed-to-lead, AI preparation, and property research
- a shared conversation and initial ownership context

The intake attempt ID, row locking, and an organization-scoped unique constraint make address-stage
retries deterministic and serialize concurrent Step 1/Step 2 requests. A repeated Step 1 request
updates or returns the same address-only record. Step 2 promotes that record once. If Step 2 is
processed first, a later Step 1 request records missing address-stage conversion evidence but never
downgrades the completed lead. A repeated completed submission returns the same lead. Separate
completed journeys still use normalized phone, email, and property evidence to match active CRM
records while preserving new form, attribution, and consent evidence.

### 6.3 Contact Authorization And SMS Consent

Step 1 grants no permission to contact. The public property form displays the versioned phone/email
disclosure next to the Step 2 final action and submits `consent_to_contact=true` only when the seller
sends that completed inquiry. Recurring automated SMS consent is a separate unchecked choice. When
checked, evidence includes the `seller-sms-web-v3` wording version, timestamp, source, IP address,
and user agent. The checkbox is never required, selected by default, persisted in a browser draft,
or inferred from general permission to contact.

Internal new-lead SMS alerts are a separate operational use case sent only to employees who enabled
the staff alert preference; the seller-facing checkbox does not control those alerts. The address
stage and completed-contact stage use separate durable identities, so each recipient gets at most
one Stage 1 text and one Stage 2 text even when the browser or worker retries.

The seller record Contact panel and Inbox right sidebar show the latest SMS state as
**Permissioned** or **Not permissioned**. Authorized staff can append a grant or revocation when
the seller communicates the decision through a phone call, in person, Facebook, an inbound seller
text, a written form, or another documented source. Every staff entry requires an evidence note
and preserves source, actor, timestamp, activity, and audit history. It does not rewrite earlier
consent evidence. An active Twilio **STOP** suppression cannot be manually overridden; the seller
must send **START** from the same number before SMS permission can be restored.
New SMS permission records are also bound to the normalized phone number that was permissioned, so
replacing a seller's primary number does not silently transfer prior permission to the new number.

### 6.4 Conversion Measurement

The public site records privacy-safe events for offer starts, form progress, validation friction,
address capture, abandonment, submit attempts, failures, successful contact submissions, phone
clicks, and Core Web Vitals. Marketing reports address leads, contact-completed leads, the
address-to-contact rate, and separate cost figures so a raw address capture is never confused with
a contactable seller. Public event intake does not grant OS access.

Meta uses `Lead` for the valid complete-address stage and `Contact` for the completed name,
required-phone, optional-email, and consent stage. Each browser/server pair shares a deterministic
event ID for deduplication. The post-confirmation optional enrichment section has no Meta event.

PC7 adds governed `MarketingExperiment` and `MarketingExperimentAssignment` records. A running
homepage CTA experiment is exposed through a read-only public endpoint. The browser makes a stable
anonymous 50/50 assignment and includes the experiment key, variant, session, and desktop/tablet/
mobile category with conversion events and seller intake. The API validates the running
experiment, prevents a session from switching variants, and links the assignment to the created
lead.

Marketing reports each version through assigned sessions, form starts, address leads,
contact-completed leads, qualified leads, appointments, executed contracts, funded deals, and
collected revenue. Runtime and per-version traffic thresholds control when the result becomes ready
for human review; the system does not choose a winner or change the public site autonomously.

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

The live OS sidebar uses four stable groups and 11 owner destinations. Focused queues and controls
are local views inside those workspaces. Legacy URLs remain as context-preserving redirects but are
not presented as competing navigation.

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
- The seller context in the right pane shows the current SMS permission state and lets authorized
  staff append a sourced, evidenced grant or revocation without leaving the conversation.

**Tasks (`/os/tasks`)**

- Unified daily work center for primary next actions, supporting tasks, governed approvals, and
  operational exceptions, plus assigned AI preparation and review.
- Saved views include My Tasks, Do Today, Overdue, Upcoming, Unscheduled, Team, Needs Approval,
  AI Completed, Exceptions, and Completed, with role-aware visibility.
- Completing a primary action requires an outcome and a successor when its seller lead or deal
  remains active.
- Home, Leads, seller records, and Tasks read the same primary next-action record.
- Lead briefs created from new seller events are reviewed inline. Transcript-grounded call notes
  immediately fill empty qualification fields, while the narrative review opens in Inbox so staff
  can hear the source evidence and correct any AI-populated value.

**Calendar (`/os/calendar`)**

- Internal month, week, day, and agenda views.
- Combines appointments, field scheduling, and due work without requiring Google Calendar.
- Owns one central appointment composer opened from Calendar, empty schedule days, seller records,
  and Inbox; phone and property meetings reuse the lead's saved contact and address context.
- Renders duration-aware blocks by meeting format, preserves cancelled blocks as history, and
  requires an explicit second action before saving an assigned-user scheduling conflict.
- Keeps Dispatch as the advanced closer-capacity, territory, overlap, and travel-buffer workflow.

### 7.2 Operations And Acquisition Tools

The primary Operations destinations are Prospecting, Leads, Deals, and Buyers. Campaign
management is a local Prospecting view. Lead Queue, Pipeline, and active Underwriting are local
Leads views. Schedule, Dispatch, Appointment, and Availability are local Calendar views.

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

**Leads (`/os/leads`)**

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
- The header **Edit lead** action opens one canonical editor in the Property section. Authorized
  staff can manage every seller phone and email, choose the primary method for each type, correct
  seller/property/qualification facts, and reassign ownership without creating a duplicate lead.
- Property Intelligence renders an interactive road map from the latitude and longitude already
  saved in the reusable property profile. MapLibre loads OpenFreeMap tiles in the browser, so map
  use does not trigger geocoding, RealEstateAPI, RentCast, or another property-data credit. Staff
  can pan, zoom, recenter on the property, or open external directions. Records without confirmed
  coordinates show a pending state; Street View and satellite imagery are intentionally excluded.
- Ownership reassignment synchronizes the lead, contact, conversation, watcher, open task, and
  upcoming appointment records and creates assignment and audit history. Stage changes remain a
  separate control because responsibility and pipeline state are different business facts.
- Seller and transaction histories use the same chronological activity pattern for event title,
  supporting context, actor, and timestamp.
- Underwriting shows the active valuation queue; detailed comp work remains on the seller record.
- Dead and disqualified opportunities are closed through one atomic workflow. Close-out records a
  disposition, reason, actor, and time; cancels active tasks, appointments, automated follow-up,
  calling and handoff work, and every pending approval tied to the lead; retires pending or
  approved offer plans and unused offer concessions; closes Lead Queue and Inbox work; and removes
  routine overdue warnings. Closed records live at `/os/leads/closed`, retain their complete saved
  contact, property, communication, appointment, valuation, transaction, and buyer-offer history
  as read-only, and require a reason plus a future next action to reopen. Genuine inbound seller
  contact automatically reactivates them for urgent follow-up. Active deal, transaction, or
  disposition work must be cancelled or resolved first; a funded deal remains a completed success
  and cannot be relabeled dead or disqualified.
- Administrative archive is reserved for confirmed duplicate and test records at
  `/os/leads/archived`; it is not a general business disposition.
- `/os/lead-manager`, `/os/pipeline`, and `/os/underwriting` preserve old links by redirecting to
  the corresponding Leads view.

**Calendar (`/os/calendar`)**

- Internal month, week, day, and agenda schedule.
- Dispatch with closer capacity, working-hours, territory, travel-buffer, and conflict checks.
- Appointment execution with preparation, guided repair walkthrough, photographs, local/API
  autosave, note dictation, supervised AI scope suggestions, seller-safe presentation,
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

**Needs Approval (`/os/tasks?view=approvals`)**

- Permission-filtered Tasks view for human decisions such as offer ceilings and contract release.
- Approval records keep their domain-specific authority, evidence, decision, and audit rules.
- `/os/approvals` is a compatibility redirect to this Tasks view.

**Transaction work (`/os/deals`)**

- Contract-to-closing work is performed in the selected Deal's Contract, Closing, Documents,
  Parties, and Timeline sections.
- The legacy `/os/transactions` URL resolves its transaction ID and tab to the same canonical Deal.

**Disposition work (`/os/deals`)**

- Existing cases are worked from the Disposition and Finance sections of the selected Deal.
- `/os/dispositions` is setup-only when an executed transaction needs its first disposition case.
  A legacy `case` bookmark resolves to the same canonical Deal.
- Deal packages, matches, engagement, offers, proof, buyer selection, reconciliation, and
  Disposition Copilot drafts remain server governed.

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
- Staff enter human-readable names; stable lowercase market and territory codes are generated
  automatically and normalized again by the API.
- Campaign and prospect creation remain in Prospecting.

**Communications (`/os/settings/communications`)**

- Embeds the authenticated email administration workspace for senders, routing, signatures,
  mailbox grants, unresolved inbound assignments, and manager-only failed-event recovery.
- Its **Failed events** tab shows terminal Resend failures. Requeue requires a reason and creates an
  audit event after an authorized manager corrects the cause.
- Restricted-alias messages can auto-route or be manually assigned only to restricted-visibility
  conversations; they cannot fall into a standard-visibility thread.
- Voice-line administrators can add company-owned numbers and update line labels, status, default
  routing, and inbound behavior without receiving email-administration access.

**Workflows And Data Quality**

- `/os/settings/workflows` owns approved follow-up plans.
- `/os/settings/data-quality` owns duplicate review plus underwriting operating baselines,
  verified-outcome scorecards, market/provider quality, and methodology decisions.
- Every newly created Stonegate Valuation stores its methodology control, run duration, provider
  and candidate counts, comp yield, cache reuse, review requirement, and operator override count in
  the existing immutable analysis metadata.
- V3 is the single live runner. Its locally supported adjustments produce the saved ARV and all
  dependent economics. Unsupported evidence clears the recommendation and requires review; V2.2
  remains a hidden engineering rollback and historical read path.

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
5. Website inquiries enter the same Lead Manager queue through a separate consented intake path and
   queue the same opted-in staff SMS alerts used by Facebook intake.
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
7. A dead or disqualified lead is closed with a structured disposition and reason. Stonegate
   atomically ends routine work, cancels all lead-related pending approvals, retires unused offer
   authority, and preserves the complete record as read-only history. Active deal, contract, or
   disposition work blocks close-out, and funded deals remain successful closed business rather
   than dead or disqualified leads.

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
3. The walkthrough records condition, guided repair decisions, quantities, optional exact prices,
   notes, and photographs. Drafts autosave to the API and retain an iPad recovery copy while
   disconnected.
4. Acquisitions Copilot can propose missing repair categories from cited text evidence and photo
   metadata. A person must review the draft, apply it, and confirm each observation; the Copilot
   cannot set repair prices or silently mark a suggestion verified.
5. The seller presentation exposes selected market evidence but hides Stonegate's internal offer
   authority, assignment fee, buyer profit, and negotiation history.
6. Reviewed field evidence evaluates the same catalog items into a low/expected/high repair
   scenario, creates the existing repair estimate and draft underwriting version, and does not
   overwrite an approved analysis.

### 8.7 Underwriting And Offer

1. Stonegate validates the subject address and canonical property facts.
2. RentCast supplies the subject record and recorded-sale candidates when available.
3. Fresh recorded-sale discovery starts with a preferred 0.5-mile / 180-day search, expands to 1
   mile / 365 days, and reaches 3 miles / 730 days only when the prior level remains insufficient.
4. Wider-query duplicates are removed, and every unique sale retains its earliest search level,
   fit grade, subdivision relationship, score, and screening reason.
5. Safe address variants may be retried when the provider misses the original string.
6. Authorized staff can add a known closed sale with its verification source, reference, condition
   evidence, and notes. Subject, duplicate, future-dated, voided, and provider-duplicate records are
   rejected or suppressed; accepted records pass through the existing comp scorer.
7. RentCast active sale listings and ZIP-level listing statistics are saved as supporting context.
   They are explicitly excluded from ARV and offer math.
8. Bounded OpenAI web research collects cited subject evidence and can propose nearby closed-sale
   candidates. Stonegate admits only candidates with exact address, closed price/date, living area,
   and consulted citations; deterministic scoring and human review still control valuation use.
9. Comparable candidates are screened for geography, recency, property type, size, bed/bath,
   condition, and material price or price-per-square-foot outliers.
10. Selected and rejected comps retain scores and reasons. A thin result remains visible with an
   exact shortage and manual-evidence next action; unsuitable properties are not substituted.
11. For guided scopes, Stonegate applies the versioned Georgia component catalog to user-selected
   repair, replace, unknown, no-work, or specialist-review decisions. It preserves quantities,
   evidence, confirmations, manual override reasons, and low/expected/high scenarios on the
   existing repair and analysis records. Unknown work creates an allowance and warning rather than
   becoming zero; legacy totals and contractor bids remain valid.
12. Stonegate Valuation V3 produces the live ARV range, as-is range, expected repair result, buyer
   economics, offer scenarios, confidence tier, and review flags.
13. V3 adjusts the selected closed-sale set using locally supported evidence.
   Time, marginal living area, lot, garage, pool, and basement adjustments require local pair
   support; collinear, unstable, missing, or extrapolated evidence is withheld or limited and every
   dollar remains reproducible. Three usable indications are preferred. Two can produce clearly
   labeled working guidance with confidence capped at 49 and mandatory review; fewer than two
   leave ARV and offer fields unavailable.
14. Investor and client PDFs use the same immutable analysis with different disclosure boundaries.
   Investor reports include guided repair decisions, ranges, evidence, catalog version, and items
   to verify; PDFs remain available when repairs are not walkthrough-confirmed.
   The same immutable analysis owns a persistent Comp Copilot thread. Its answers cite sanitized
   saved evidence and can navigate the operator to comp, condition, micro-market, or refresh work,
   but cannot change evidence, state a price, or exercise valuation or approval authority. The
   interactive Location view plots the subject plus selected and excluded sales from saved
   coordinates without another provider lookup.
15. A human creates a negotiation plan tied to one saved underwriting version.
16. Approval establishes opening, target, stretch, and hard-ceiling authority.
17. Concessions and price discussions are appended to the negotiation ledger.
18. The seller's Valuation & Offer section presents Quick Comp, Desk Review, Walkthrough, and Offer
    Decision as progressive stages over these same records. It does not create a separate comp or
    repair workflow.
19. **Run Stonegate valuation** creates the first provider snapshot; the same control becomes
    **Update Stonegate valuation** afterward and recalculates from that saved same-address snapshot
    with zero paid provider calls. **Refresh market evidence (may use credits)** is a separate,
    explicit action that replaces the snapshot and retries providers when newer evidence is needed.
20. A persistent decision summary shows the current ARV, repairs, buyer target, opening, and seller
    ceiling and links to reports, the appointment/field workflow, approval, and contract signing.
    Version comparison and manual scenarios remain available under expandable advanced records.
21. Version comparison reads the linked immutable analysis for each underwriting version and shows
    added or removed comps, search reach, changed repair categories, catalog version, adjustment
    support, ARV/repair/disposition/opening changes, and seller-ceiling changes.
22. The investor PDF includes internal economics and reproducible market-adjustment evidence. The
    client PDF uses the same analysis but exposes only seller-safe evidence strength, preparation
    assumptions, unresolved work, comparable evidence, and public-source context.
23. Verified outcomes feed calibration segments for market, provider, property type, search level,
    selected comp grades, active repair categories, report stage, and repair catalog. A case can
    appear in more than one comp-grade or repair-category segment because those dimensions describe
    evidence present in the same analysis.
24. Data & Quality shows comp yield, operator comp overrides, supervised AI repair-scope corrections,
    and repair-catalog total-budget error. These measurements inform a human methodology decision;
    they do not modify formulas automatically.
25. Verified outcomes measure V3 accuracy, range coverage, market bias, provider performance, and
    operator correction burden without changing formulas automatically.
26. Method changes remain evidence-backed human decisions. Historical analyses stay immutable and
    V2.2 remains available only as an engineering rollback.

### 8.8 Contract And E-Signature

1. An approved, versioned contract template provides the base document.
2. Stonegate creates a contract package from CRM, property, offer, and party facts.
3. Missing or conflicting required facts block release rather than being invented.
4. A purchase agreement also captures the exact approved offer plan, underwriting version,
   seller-agreed or current transaction price, and any governing concession as an authority
   snapshot. A stale or changed source blocks approval, sending, signing, or execution and requires
   a new package.
5. An authorized person requests approval and then sends through the configured e-sign provider.
   Stonegate reserves one active envelope, creates an unsent provider draft, saves its ID, and only
   then sends it. Lost create responses require verified draft attachment or an audited empty-intent
   abandonment; no automatic retry creates a second provider document.
6. SignWell hosts the signing ceremony; Stonegate stores envelope, recipient, event, and completed
   document evidence. Organization-bound webhook verification prevents one tenant's credential from
   updating another tenant's envelope, while stale and out-of-order events remain audit evidence
   without moving the envelope backward. Because the provider HMAC does not bind every body field,
   production reconciliation must still confirm the document, recipients, status, and completed PDF
   against SignWell.
7. Offer plans, concessions, price presentations, and seller agreements cannot change while a
   purchase package is being delivered or remains signable. Provider terminal failures release that
   reservation once. A manually sent agreement requires audited withdrawal from every recipient
   before newer authority can be recorded.
8. The same provider flow can be launched on an iPad for an in-person seller signature.
9. Manual execution requires the exact executed document type, an explicit executed evidence
   status, an acceptable scan state, and an audited human attestation. Provider completion records
   the completed envelope and executed document evidence.

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
4. The optional DealMachine adapter can provide external buyer candidates only if it is deliberately reactivated and
   accepted.
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

Business close-out is distinct from Administrative archive, which is only for confirmed duplicate
or test records. A closed lead has no active primary action, pending approval or unused offer
authority, and no routine follow-up warnings. Its complete saved contact, property, communication,
appointment, valuation, transaction, and buyer-offer history remains viewable but read-only.
Manual reactivation creates exactly one new primary next action; inbound seller email, SMS, or
voice reactivation creates urgent response work. Historical close-out metadata remains attached to
the lead for audit and reporting.

Workers can create escalation evidence, but staff remain responsible for resolving the underlying
work. Approvals are aggregated into Tasks for discovery but remain separate governed records.
New lead events also enter the AI Operations queue. The worker prepares a Lead Manager brief, then
routes it to the assigned employee for acceptance or rejection. Acceptance logs an internal note;
it does not contact the seller, change lead facts, or complete the human's primary action.

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
- inbound MMS photo capture with authenticated inline Inbox previews and downloads
- private document retention instead of browser-visible Twilio media URLs
- worker retry and automatic recovery of retained pre-deployment MMS events when provider media is
  still available
- STOP and START processing
- suppression and consent controls
- an editable **Permissioned / Not permissioned** seller-context control for authorized staff, with
  required source and evidence-note capture plus append-only activity and audit history
- number normalization
- organization and permission scope

Stonegate's dedicated seller-inquiry A2P campaign must show approved in Twilio before production
SMS acceptance. Do not use another
company's Messaging Service, campaign, number, or consent description.

Manual staff documentation never bypasses an active carrier STOP. Only the seller's inbound START
message removes that suppression and restores SMS eligibility.

### 10.5 Voice

The Twilio Voice implementation supports:

- company voice lines separated by department and purpose
- primary, fallback, and optional department-team membership
- conversation-owner-first routing with sequential or simultaneous ringing
- private-cellphone forwarding groups with first-answer-wins behavior
- department call announcements and press-1 cellphone screening
- active-user filtering, duplicate removal, and answer attribution
- 24/7 staff ringing, voicemail fallback, and missed-call tasks
- outbound cellphone bridging with Stonegate caller ID and automatic conversation history
- company-number-aware inbound routing
- call status and dial result callbacks
- missed-call tasks
- private recordings
- recording-authorization state
- transcript review

Voice forwarding requires the Account SID, Auth Token, company number, inbound callback, active
Stonegate line, and enabled staff cellphone destinations. Browser access tokens and a TwiML App
are not required for this operating mode.

### 10.6 Call Intelligence

When recording is deliberately enabled:

1. Twilio reports the completed recording.
2. The worker retrieves eligible audio.
3. OpenAI transcription produces speaker-aware transcript evidence.
4. structured notes identify motivation, condition, timeline, occupancy, price, objections,
   commitments, and next action.
5. transcript-grounded values immediately fill only empty CRM qualification fields and create an
   audit/activity record; existing staff-entered values are not overwritten.
6. the transcript-grounded narrative posts automatically as an internal conversation note and
   appears in Inbox, the seller record, communication history, and recent activity. No approval
   request is created.
7. staff can correct an inaccurate CRM value or add a clarifying internal note. A proposed next
   action remains context only and does not create a task automatically.
8. successful transcription is checkpointed before structured note generation, so a later note
   failure can reuse the saved transcript without paying to transcribe the same call again.
9. temporary failures retry with exponential delay. Repeated failures become `exhausted`, and an
   authorized user can queue an audited manual retry from Inbox.
10. the AI run and orchestrator event close automatically after the note is saved, and retention or
   early deletion remains tracked. Legacy notes left in `needs_review` are automatically posted by
   the worker and their obsolete approval requests are cancelled.

The integration is not launch-ready unless Voice, the approved recording-authorization policy,
transcription, OpenAI, failure visibility, retention, deletion, and automatic note placement have passed
together. A spoken disclosure is optional in the Owner-selected Georgia-only one-party mode, whose
operating policy still requires documented production acceptance.

## 11. Underwriting System

### 11.1 Evidence Hierarchy

Stonegate separates:

- CRM-entered subject facts
- provider-returned subject facts
- provider-neutral recorded-sale observations with field-level provenance and conflicts
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
4. adaptive preferred, expanded, and extended RentCast recorded-sale search
5. exact-match RealEstateAPI Property Detail and candidate or shadow comp retrieval
6. cross-provider normalization, transfer deduplication, conflict retention, subdivision
   comparison, A-D grading, screening, and scoring
7. subject-versus-candidate review data, engine recommendation, and location direction
8. optional bounded public-record research and draft-only AI Comp Analyst review
9. locally supported adjustments and comparable weighting
10. interpolated weighted adjusted-sale Q25/Q50/Q75 ARV conclusion and range diagnostics
11. repair and contingency math
12. buyer economics and Stonegate offer scenarios
13. confidence factors and review flags
14. immutable analysis storage

The search stops when at least three screened closed sales satisfy available market-area evidence.
If the complete provider search remains thin, the result is labeled `manual`, records the exact
shortage and next action, and preserves every suitable sale found. Ordinary updates, repair-only
reruns, and comp reviews reuse this immutable provider snapshot—even after a provider failure or no
match—and make no paid retry unless the operator explicitly refreshes market data.

The Comparable Review workbench consumes the saved subject snapshot and complete candidate set.
Filters and sorting affect only the display. Every apply request still carries one include/exclude
decision, reason, and weight for every candidate in the source analysis. The engine's original
recommendation remains attached to each sale so a later reviewer decision cannot rewrite what the
system originally suggested. Applying creates another immutable analysis and audit event.

### 11.3 Offer Math

V3 begins with the conservative point from locally adjusted closed-sale evidence, then subtracts
repair, purchase, financing/holding, resale, buyer-profit, assignment-fee, and transaction-reserve
requirements. The historical 65-70% calculation remains comparison context and does not control
the seller ceiling. The result is a scenario and authority range, not a guaranteed appraisal or
mandatory seller offer.

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

The DealMachine buyer-data adapter is retained only as an optional legacy workflow and is disabled
when `BUYER_DATA_PROVIDER=disabled`. If it is deliberately reactivated, the workflow:

1. Verifies the configured account and displays the paid plan, billing-cycle reset, and available
   credits without exposing the API key.
2. Previews the matching-result count and maximum property/contact credit use without consuming
   credits.
3. Requires a second explicit action before running discovery for an active disposition case.
4. Stores the provider query, actual credit summary, and raw candidate evidence.
5. Normalizes current multi-select property fields, excludes provider-DNC phone numbers from the
   imported contact suggestion, scores candidates, and explains the evidence.
6. Requires a human to review before import.
7. Links imported records to the existing buyer CRM without sending outreach.

The adapter is not required for Stonegate's current launch and should not be treated as an active
buyer source unless the Owner deliberately reactivates and accepts it later.

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
- address-only website leads and contact-completed website leads as separate funnel outcomes
- qualified leads
- appointments
- signed contracts
- funded deals
- cost per result and deal profitability

Offline conversion adapters exist for Google Data Manager and Meta Conversions API. Meta `Lead`
represents valid Step 1 address capture, while Meta `Contact` represents completed Step 2 contact
submission; optional enrichment does not emit a Meta event. Contact identifiers are normalized and
hashed where the privacy policy permits, deterministic event keys support browser/server
deduplication, and retries are audited. Meta Pixel and Conversions API delivery passed controlled
acceptance; Google delivery remains behind its account credentials and acceptance tests.

Meta Lead Ads intake uses one Zapier action to send a Page-bound payload to Stonegate. At the
Owner's direction the route is intentionally secretless and publicly reachable. It enforces the
configured Page ID, a production-required form-ID allowlist, request schema and size limits, an
in-process burst limit, a database-backed rolling 24-hour acceptance cap, and organization-scoped
Facebook lead-ID deduplication. It durably stores the original and normalized payloads before the
worker runs normal seller intake, campaign/ad attribution, property research, and internal SMS
alert queuing. CRM intake and alert delivery retry with backoff.

Production burst keys use the edge-owned Cloudflare client address and ignore caller
`X-Forwarded-For`; the in-process limiter hard-bounds tracked keys. This is a controlled-launch
memory and burst guard, not distributed protection across instances, so the trusted origin path and
edge/WAF limiting remain scale requirements.

These controls constrain abuse and cost but do not prove that the caller obtained the Page and form
values from Meta. Stonegate therefore monitors Zapier history, provider-event volume, form IDs, and
the daily circuit during live campaigns. Stonegate does not use a Meta developer app, Graph token,
or direct Meta webhook for this workflow. The system records requested phone/email contact basis
but never infers seller SMS consent from a Meta phone field.

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
| Lead Manager | Leads > Lead Queue | Priority, seller brief, missing facts, reply and task proposals |
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

Each sweep gives every operation one opportunity to process work before the next sweep, so a busy
high-priority queue cannot indefinitely starve call, email, or other later queues. A separate
heartbeat thread refreshes liveness during long provider calls without clearing an already
degraded state. Main-loop progress and the current operation are recorded independently. `/ready`
therefore catches a live-but-hung loop after `WORKER_OPERATION_STALL_SECONDS` (600 seconds in
production) without classifying a normal multi-provider operation as stalled merely because it
lasts longer than the heartbeat freshness window.

Resend provider events use a UUID-fenced processing lease, bounded exponential retry, stale-claim
recovery, and a terminal dead-letter state. A reclaimed event cannot be overwritten by its stale
worker. The exact validated inbound route is checkpointed before later provider or attachment work,
so a retry cannot silently choose a different destination; lifecycle webhooks that arrive before
their outbound CRM record retry within the same bounded budget. Attachment downloads enforce the
configured limit from declared size, response length, and streamed bytes instead of buffering an
unbounded response. Dead-letter events require manager review and a reason-required audited requeue;
they are not automatically resurrected into a poison loop.

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
- signed Resend, Twilio, and organization-bound SignWell webhooks, plus a documented secretless
  Zapier exception with bounded ingress and acceptance controls
- production client-IP rate-limit keys derived from the edge-owned Cloudflare address while caller
  `X-Forwarded-For` is ignored, with a hard bound on process-local limiter keys
- event and dispatch idempotency
- consent and suppression evidence
- permission-gated downloads
- secret values stored in environment configuration, not documentation
- human approval for consequential financial, contractual, offer, buyer, and AI actions
- request-type-specific approval read and decision enforcement, with `audit:view` as the only
  blanket approval-read authority and unknown types having no decision path
- dependency audits in CI for Python and Node packages

The platform contains controls, but software does not replace legal, tax, accounting, employment,
telemarketing, recording, or real-estate advice.

## 20. External Integrations

| Provider | Purpose | Code status | External status |
| --- | --- | --- | --- |
| Clerk | Authentication | Implemented | Active |
| Render | Hosting, Postgres, key value | Implemented | Active |
| OpenAI | Copilots, bounded research, transcription | Implemented | API configured; production pilots remain |
| RentCast | Independent recorded-sale, rent, and market evidence | Implemented | Configured; address coverage varies |
| RealEstateAPI | Canonical property profile, secondary comps, financial/property signals, and licensed listing image when returned | Implemented with exact-match enforcement, deduplication, saved full record, safe image proxy, and candidate/shadow modes | Active; controlled property research passed |
| Resend | Outbound and inbound operational email | Implemented with signed events, UUID-fenced leases, durable route checkpointing, bounded retry, manager-only audited dead-letter recovery, restricted-mailbox isolation, and bounded attachment downloads | DNS and webhook configured; controlled mailbox acceptance and malware-scanning decision remain |
| Twilio | SMS, Voice, recordings, and Call Intelligence | Implemented with transcript backoff, exhaustion visibility, and audited manual retry | Staff alerts have prior delivery evidence but require repeat acceptance; seller SMS and Voice/recording/transcription/AI-note acceptance remain |
| SignWell | Hosted e-signature | Implemented | Activation and acceptance pending |
| DealMachine | Legacy optional buyer discovery and underwriting adapter | Retained for rollback only | Disabled; removable after subscription cancellation |
| S3-compatible storage / R2 | Private document storage | Implemented option | Activation optional/pending |
| ClamAV | Document malware scanning | Implemented option | Disabled |
| Sentry | Error monitoring | Implemented option | Deferred |
| Google Data Manager | Offline ad conversions | Implemented adapter | Credentials and acceptance pending |
| Meta Pixel and Conversions API | Browser/server ad conversions | Implemented | Active; controlled browser/server acceptance passed |
| Zapier + Meta Lead Ads | Facebook instant-form CRM intake | Implemented intentionally secretless endpoint with Page/form restrictions, burst and daily circuits, payload limits, deduplication, attribution, audit payloads, and retries | Controlled ingestion passed; residual caller-provenance risk is monitored |
| Twilio staff lead alerts | Internal new-lead notification | Implemented with per-employee opt-in and delivery callbacks | Prior controlled delivery exists; repeat acceptance is pending after the worker credential correction |
| Twilio inbound-message staff alerts | Assigned-owner/fallback cellphone notification with Inbox link; unknown seller/buyer sender capture and loop protection | Implemented with independent per-employee opt-in, durable deduplication, retries, and delivery callbacks | Controlled production acceptance pending |

## 21. Data Domain Map

The primary SQLAlchemy model file contains 198 operational model classes. They group into:

### Identity And Organization

`Organization`, `User`, `Role`, `Permission`, `RolePermission`, `RoleAssignment`, `Team`,
`TeamMembership`.

### Markets, Campaigns, And Prospecting

`Market`, `Territory`, `Campaign`, `Prospect`, import mapping/batch/row records, suppression checks,
prospecting cohorts, paid/productive work sessions, cohort-attributed campaign costs, calling
batches and entries, script versions, evidence-classified attempts, structured handoffs, Copilot
recommendations, reviews, and call quality.

### CRM And Seller Evidence

`Contact`, `ContactMethod`, `Property`, `PropertyIntelligenceSnapshot`, `PropertyResearchRun`,
`Lead`, `ConsentRecord`, `SuppressionRecord`,
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

`UnderwritingVersion`, `UnderwritingMarketAnalysis`, `UnderwritingManualComparable`, calibration
cases and decisions, `RepairEstimate`, `OfferNegotiationPlan`, `OfferConcession`, and
`OfferNegotiationEvent`.

`UnderwritingMarketAnalysis.metadata` remains the additive compatibility boundary for methodology
control, execution metrics, comparable-search summaries, selected manual-sale IDs, and normalized
supporting market evidence. Provider closed sales remain separate in the raw snapshot. This avoids
a duplicate analysis table and keeps older V2.2 records readable when newer optional fields are
absent.

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
- 90 API test modules
- Ruff linting
- MyPy type checking
- Python and Node dependency vulnerability audits
- Next.js lint, explicit TypeScript checking, and production build commands
- OS information-architecture and underwriting-workspace contract checks
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
npm run typecheck:web
npm run audit:ia
npm run audit:underwriting
npm run build:web

(cd apps/api && uv run pip-audit --strict --desc=off --progress-spinner=off)
(cd apps/web && npm audit --workspaces=false --audit-level=high)
```

Provider-backed workflows also require controlled acceptance. Passing unit tests does not prove
DNS, webhook, carrier, mailbox, signing, data-provider, or advertising account configuration.

## 23. Known Boundaries And Remaining Proof

The major product workflows are implemented. The remaining risk is primarily production
acceptance and evidence:

- Twilio seller SMS plus dedicated Voice, recording, transcription, AI-note
  review/apply, automatic retry, exhaustion/manual recovery, retention, and deletion acceptance
- Resend controlled sender, reply, restricted routing, attachment-size/malware procedure,
  retry/dead-letter/requeue, bounce, and escalation tests
- SignWell template, webhook, remote signature, and iPad signature acceptance
- real Georgia underwriting outcomes and operator calibration
- first CPA-reviewed opening balances, bank reconciliation, month close, and report package
- ad-provider credential setup and offline conversion acceptance
- role acceptance with actual staff accounts
- supervised Copilot pilots using redacted Stonegate cases
- PropStream production export acceptance using Stonegate's implemented source membership,
  ranked-contact, refresh-safe, and deterministic cohort workflow
- real-VA acceptance of the BatchDialer calling and idempotent Stonegate warm-handoff workflow;
  Stonegate one-by-one calling remains the migration fallback
- real backup restoration and optional monitoring-provider configuration
- one real Facebook-form-to-CRM-to-property-research-to-staff-alert acceptance run using the
  production form allowlist, plus continued monitoring of the secretless-ingress residual risk
- a controlled manual buyer-outreach procedure or a separately implemented live disposition
  delivery channel; the current campaign release records simulation evidence only
- an explicit production decision on malware scanning and distributed edge throttling before scale;
  process-local key storage is bounded but is not a shared multi-instance control

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
