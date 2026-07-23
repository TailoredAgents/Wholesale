# Stonegate Experience Upgrade Roadmap

Last updated: July 22, 2026

Status: Phases UX1 through UX10 are implementation complete. Production baseline collection and
business-content acceptance remain.

This roadmap governs the next design track for the Stonegate Operating System and public seller
website. It does not replace `ROADMAP.md`, which remains the source of truth for business workflows
and platform capabilities. The purpose of this track is to make those completed capabilities easier
to understand, faster to operate, visually consistent, accessible, and measurable.

## Research Basis

The sequence is based on current patterns from Salesforce Sales Console and Sales Workspace,
HubSpot Sales Workspace, Close CRM, real-estate investor platforms, GOV.UK service design, W3C form
guidance, Google Core Web Vitals, current direct-homebuyer offer flows, Twilio consent requirements,
and FTC advertising guidance.

The core conclusions are:

- Organize the OS around daily work, records, process stages, management, and control.
- Give each role a focused workspace instead of presenting every feature to every user.
- Use split views for rapid queue work and tabs only for related record content.
- Begin the public offer journey with the property address, then ask only necessary questions in a
  progressive form.
- Treat performance, accessibility, consent, truthful claims, and analytics as release criteria.
- Determine actual conversion winners with Stonegate data rather than copying a competitor's
  appearance.

## Target OS Navigation

Routes remain stable during the visual upgrade unless a redirect is explicitly approved.

### Command

- Dashboard: `/os`
- Inbox: `/os/inbox`
- Work Queue: `/os/tasks`
- Calendar: `/os/calendar`

### Acquisitions

- Acquisition Operations: `/os/operations`
- Campaigns: `/os/campaigns`
- Prospecting: `/os/prospecting`
- Lead Desk: `/os/lead-manager`
- All Leads: `/os/leads`
- Seller Pipeline: `/os/pipeline`
- Field Operations: `/os/field-operations`

### Deal Flow

- Underwriting: `/os/underwriting`
- Approvals: `/os/approvals`
- Transactions: `/os/transactions`
- Dispositions: `/os/dispositions`
- Buyers: `/os/buyers`

### Business And Control

- Finance: `/os/finance`
- Marketing: `/os/marketing`
- Operating Model: `/os/operating-model`
- AI Control: `/os/ai`
- Team, integrations, and settings when their dedicated management routes are implemented

Navigation visibility must follow role permissions. Hiding an item is not a substitute for API
authorization; both remain required.

## Shared Acceptance Standard

Every phase must meet these requirements before it is marked complete:

- No business rule, approval gate, audit record, or permission boundary is weakened.
- Existing deep links remain valid or receive an intentional redirect.
- Desktop, laptop, tablet, and mobile layouts have no incoherent overlap or horizontal overflow.
- Controls have stable dimensions and clear loading, empty, success, warning, and error states.
- Forms use visible labels, keyboard access, useful validation, and preserved user input.
- Automated tests, lint, TypeScript, and production builds pass.
- Changed user journeys receive Playwright screenshots at representative desktop and mobile sizes.
- Repeated UI patterns use shared components and tokens instead of page-specific copies.

## Phase UX1: Route, Role, And Information Architecture Audit

Status: Complete. Owner approved the Phase UX1 decision record on July 22, 2026.

Decision record: [`UX1_INFORMATION_ARCHITECTURE_AUDIT.md`](UX1_INFORMATION_ARCHITECTURE_AUDIT.md)

Goal: Establish one clear location, name, audience, and purpose for every OS feature before visual
restyling.

Deliverables:

- Complete route and feature inventory.
- Role-to-navigation matrix for Owner, Lead Manager, Acquisitions Closer, VA Caller, Dispositions,
  and Transaction Coordination.
- Approved navigation groups and labels from this document.
- Explicit definitions for Lead Desk, All Leads, Seller Pipeline, and Field Operations.
- Duplicate entry-point, orphan route, inconsistent-label, and dead-end report.
- Cross-workspace handoff map from campaign through reconciliation.
- Baseline screenshots and usability issue list for every OS route.

Exit criteria:

- Every current route has an approved group, label, role audience, and primary job.
- No two primary navigation items promise the same job.
- Owner approval is recorded before shell implementation begins.

## Phase UX2: Stonegate Design System And Page Contracts

Status: Complete. See [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md).

Goal: Create the shared visual and interaction foundation used by all later phases.

Deliverables:

- Color, typography, spacing, border, shadow, icon, density, focus, and motion tokens.
- Shared buttons, icon buttons, fields, selects, checkboxes, segmented controls, tabs, badges,
  tables, filters, menus, drawers, dialogs, toasts, skeletons, and empty states.
- Standard page contracts for queue, record, pipeline, calendar, and management pages.
- Standard record summary header and sticky action bar.
- Status-color semantics that do not rely on color alone.
- Accessibility and responsive component examples.

Exit criteria:

- Components render correctly at 390, 768, 1280, and 1440 pixel widths.
- No page needs a new local version of an existing core control.
- A reference page demonstrates every component and state.

## Phase UX3: Global OS Shell, Navigation, And Wayfinding

Status: Complete. The role-aware shell and approved navigation were implemented on July 22, 2026.

Goal: Make movement through Stonegate predictable and role-specific.

Deliverables:

- Rebuilt grouped sidebar using the approved information architecture.
- Role-aware item visibility and clear active-route treatment.
- Compact global header with search, notifications, recent records, and user controls.
- Consistent page titles, breadcrumbs where useful, and primary action placement.
- Responsive navigation drawer and a focused mobile pattern for field users.
- Route labels updated without breaking current URLs.

Exit criteria:

- Each role can reach its five most common tasks without scanning unrelated modules.
- Every route clearly communicates its location and purpose.
- Navigation works with keyboard, screen reader, desktop, and mobile input.

Implementation notes:

- The five approved navigation groups now use one centralized route definition with role and
  permission visibility checks.
- The global header provides workspace search, recent destinations, notification state, and compact
  account controls.
- Owner, acquisitions, prospecting, dispositions, transaction coordination, finance, marketing,
  partner, and vendor roles receive focused navigation and appropriate default landing routes.
- Mobile navigation uses an off-canvas drawer; desktop and mobile browser checks confirm no
  horizontal overflow.
- Existing route URLs remain unchanged, while visible route and page labels now use the approved
  information architecture.
- `/api/v1/me` supplies roles, permissions, display identity, and unread notification count to the
  shell for every authenticated workspace role.

## Phase UX4: Command Center And Daily Workspaces

Status: Complete. The daily command workspaces were implemented on July 22, 2026.

Goal: Make the start of every workday immediately actionable.

Scope:

- Dashboard
- Inbox
- Work Queue
- Calendar

Deliverables:

- Role-specific dashboard priorities and exception reporting.
- Refined three-panel Inbox with conversations, unified timeline, and seller context.
- Dense Work Queue with saved filters, bulk-safe actions, ownership, due state, and next action.
- Month, week, day, and agenda calendar views with stable appointment interactions.
- Consistent unread, overdue, blocked, needs-review, and escalation treatment.

Exit criteria:

- A user can identify the next required action within one screen after login.
- Inbox, task, and calendar handoffs retain context and do not duplicate records.
- Daily workflows remain usable at laptop and mobile widths.

Implementation notes:

- The Dashboard is now a role-aware daily command center focused on priority work, exceptions,
  meetings, qualification gaps, offer preparation, and a compact pipeline pulse.
- Work Queue provides saved All, Mine, Overdue, Due Next, and Unscheduled views with seller search,
  owner filtering, explicit due state, contextual next actions, and confirmed bulk completion.
- Inbox keeps one conversation record while supporting deep links to a lead or saved view, unified
  communication history, urgency treatment, and mobile Inbox, Thread, and Details panes.
- Calendar provides month, week, day, and 30-day agenda modes with closer filtering, capacity and
  scheduling summaries, upcoming meetings, and direct links into field dispatch or lead context.
- Dashboard, Work Queue, Inbox, and Calendar were verified with populated local data at 1440 and
  390 pixel widths with no page errors or horizontal overflow.

## Phase UX5: Acquisition Workspaces

Status: Complete. The acquisition workspace upgrade was implemented on July 22, 2026.

Goal: Create one coherent seller-acquisition experience from source record through field meeting.

Scope:

- Acquisition Operations
- Campaigns
- Prospecting
- Lead Desk
- All Leads
- Seller Pipeline
- Field Operations

Deliverables:

- Clear distinctions between daily Lead Desk work, the lead database, and stage management.
- Unified filtering, search, ownership, status, and next-action patterns.
- Faster VA queue and warm-handoff review.
- Compact lead rows and useful preview drawers rather than unnecessary page changes.
- Consistent campaign-to-prospect-to-lead attribution visibility.
- Appointment and field views optimized for preparation and mobile evidence capture.

Exit criteria:

- A warm prospect can be followed from source to appointment without losing ownership or context.
- Users no longer need to guess which lead page contains a specific action.
- VA-only views expose no restricted underwriting, buyer, contract, finance, or export controls.

Implementation notes:

- Operations, Campaigns, Prospecting, Lead Desk, All Leads, Seller Pipeline, and Field Operations
  now use the standard workspace header and one role-filtered acquisition route sequence.
- All Leads is the searchable active seller system of record with saved views, owner and stage
  filters, compact rows, operating status, explicit next actions, and a responsive context drawer.
- Seller Pipeline groups every supported acquisition stage, including contact-due, appointment
  scheduling, approval, negotiation, nurture, and under-contract states, without dropping records.
- Pipeline cards expose owner, status, due context, and the next workspace action. Seller details
  open in a local inspector instead of forcing a full record-page change.
- Lead Desk and Field Operations accept lead deep links so qualification and appointment handoffs
  open with the matching seller highlighted or selected.
- Under-contract and closed-out leads no longer receive misleading qualification statuses, and
  appointment queues recognize scheduling-stage aliases used by the operational API.
- The secondary acquisition route strip uses the same role and permission contract as the global
  sidebar; restricted VA callers retain only their authorized Prospecting route and API scope.
- All seven workspaces and the lead/pipeline drawers were verified at 1440 and 390 pixel widths
  with no runtime errors or page-level horizontal overflow.

## Phase UX6: Deal Execution Workspaces

Status: Complete. The deal execution workspace upgrade was implemented on July 22, 2026.

Goal: Make high-risk deal work compact, evidence-led, and difficult to perform out of sequence.

Scope:

- Underwriting
- Approvals
- Transactions
- Dispositions
- Buyers

Deliverables:

- Shared deal summary and status progression across workspaces.
- Evidence, authority, risk, owner, deadline, and next action visible without long-page scanning.
- Comparison-oriented underwriting and buyer-selection layouts.
- Approval inbox with direct review context and clear consequences.
- Transaction and disposition checklists organized by exceptions and deadlines.
- Secondary forms moved into drawers, dialogs, or local tabs when appropriate.

Exit criteria:

- Users can identify blocking evidence and the authorized next step from each workspace header.
- No visual control implies authority the current user does not have.
- Contract, offer, buyer-selection, funding, and reconciliation gates remain server-enforced.

Implementation notes:

- Underwriting, Approvals, Transactions, Dispositions, and Buyers now share one role-filtered Deal
  Flow sequence while preserving every existing route and API permission boundary.
- A shared execution control strip exposes evidence, authority, the next deadline, the primary
  blocker, and the authorized next step without requiring long-page scanning.
- Underwriting separates the active analysis queue from selected seller evidence and makes sample
  size, error, bias, range coverage, and verified outcomes directly comparable.
- Approvals behaves as a consequence-led decision queue with source-record links, affected entity
  context, deadline risk, metadata evidence, view-only treatment, and audited human decisions.
- Transactions preserves its checklist, contract version, document, party, timeline, and funding
  gates while surfacing required open items, evidence count, approval authority, and the next
  operational deadline above the record tabs.
- Dispositions preserves package approval, buyer qualification, offer selection, proof-of-funds,
  and reconciliation gates while showing the current sequence blocker and buyer evidence before
  any release or payout action.
- Buyers is a searchable comparison workspace with proof-of-funds status, expiration, reliability,
  purchasing criteria, capacity, active deal inventory, and an authorized add-buyer drawer. Users
  without `buyers:edit` never receive an edit control.
- Secondary transaction and disposition forms remain inside their relevant local tabs; buyer entry
  moved out of the primary comparison surface into a responsive drawer.

## Phase UX7: Business, Reporting, And AI Control

Status: Complete. The management and control workspace upgrade was implemented on July 22, 2026.

Goal: Give ownership and management a coherent view of economics, performance, configuration, and
automation risk.

Scope:

- Finance
- Marketing
- Operating Model
- AI Control
- Cross-workspace reporting

Deliverables:

- Consistent metric definitions, comparison periods, filters, and drill-down behavior.
- Finance organized around reconciliation exceptions, margin, commissions, and export state.
- Marketing organized around source economics and attributable outcomes.
- Operating Model separated into active policy, historical versions, and pending decisions.
- AI Control organized around portfolio, evaluations, traces, approvals, cost, and rollback.
- Clear separation between operational controls and explanatory documentation.

Exit criteria:

- The owner can identify financial, marketing, policy, and AI exceptions without opening raw logs.
- Metrics link back to the records that produced them.
- AI autonomy and external-action restrictions remain unmistakable.

Implementation notes:

- Finance, Marketing, Operating Model, and AI Control now share one role-filtered Business and
  Control sequence plus a consistent management summary for reporting basis, comparison state,
  primary exception, authority, and next action.
- Finance and Marketing support real 30-day, 90-day, and all-time periods. Fixed periods include
  the immediately preceding equal-length period for comparisons, with API-tested timestamp
  boundaries and source-record filtering.
- Finance is organized around retained margin, pending revenue, deal reconciliation exceptions,
  commission calculations, and linked ledger evidence. Manual entry controls are separated from
  management reporting.
- Marketing is organized around attributable source economics, spend without leads, leads without
  contracts, sub-1.0 return on ad spend, source-to-lead drilldowns, and the offline conversion queue.
- Operating Model separates the active compensation authority, pending role-credit decisions,
  historical policy versions, and evidence-based market launch records without weakening audited
  activation or approval controls.
- AI Control surfaces portfolio coverage, evaluations, trace review, approvals, usage cost,
  promotion state, and rollback controls. External execution remains visibly blocked and human
  approval remains required for promotion.
- All four routes were verified with populated data at 1440 and 390 pixel widths with no runtime
  errors or page-level horizontal overflow. The complete API suite, frontend lint, TypeScript, and
  production build pass.

## Phase UX8: OS Responsive, Accessibility, And Regression Pass

Status: Complete. The whole-OS quality pass was implemented on July 22, 2026. See
[`UX8_OS_QUALITY_AUDIT.md`](UX8_OS_QUALITY_AUDIT.md).

Goal: Validate the upgraded OS as one complete product rather than a collection of improved pages.

Deliverables:

- Full desktop and mobile route audit.
- Keyboard, focus, labels, errors, contrast, reduced-motion, and screen-reader checks.
- Layout-shift, overflow, truncation, loading, empty-state, and long-content tests.
- Visual regression screenshots for critical role workflows.
- Performance review of large tables, tabs, images, and client-side bundles.
- Final consistency cleanup with no unrelated business-logic refactors.

Exit criteria:

- Critical workflows pass at 390, 768, 1280, and 1440 pixel widths.
- No unresolved high-severity accessibility, overlap, navigation, or data-loss defect remains.
- Owner completes a representative workflow for every internal role.

Implementation notes:

- The authenticated OS now has one main landmark and one page heading on every route, plus a
  keyboard-accessible skip link and consistent visible focus treatment.
- The mobile navigation drawer transfers focus on open, contains keyboard focus while active,
  closes with Escape, restores focus to its trigger, and prevents background scrolling.
- Buyer entry and lead archive/delete confirmation use the shared native dialog foundation for
  focus containment, Escape handling, and focus restoration.
- Reduced-motion preferences suppress nonessential animation and smooth scrolling throughout the
  OS without changing business behavior.
- A permanent `npm run audit:os` release check now covers every production OS route at 390, 768,
  1280, and 1440 pixels. It checks overflow, document landmarks, control names, duplicate IDs,
  image alternatives, reduced motion, keyboard navigation, key contrast pairs, browser errors,
  and serious or critical axe-core WCAG findings.
- The populated audit completed 88 route and viewport checks, including an active lead record,
  with no unresolved high-severity accessibility, overlap, navigation, or data-loss defect.
- Representative desktop and mobile screenshots were reviewed for Dashboard, Inbox, All Leads,
  lead detail, Underwriting, and Dispositions. The complete lint, TypeScript, production build,
  and API test suite pass.
- Owner role acceptance remains a deployment checkpoint whenever permissions or representative
  workflows change; the automated matrix does not replace that human verification.

## Phase UX9: Public Website Architecture, Brand, And Trust

Status: Complete. See [`UX9_PUBLIC_WEBSITE_ARCHITECTURE.md`](UX9_PUBLIC_WEBSITE_ARCHITECTURE.md).

Goal: Establish a credible, local, differentiated Stonegate seller experience before rebuilding the
offer journey.

Deliverables:

- Final public sitemap and content hierarchy.
- Minimal primary navigation: How It Works, Selling Situations, About, FAQs, and Get a Cash Offer.
- Stonegate visual direction, typography, photography rules, icon treatment, and responsive system.
- First-viewport brand and literal seller offer with property-address entry.
- Verifiable reviews, local service-area signals, team identity, process, and contact information.
- Legal and claims review that rejects unsupported price, savings, speed, or comparison claims.
- SEO situation-page template that does not overcrowd primary navigation.

Exit criteria:

- Every public page has one primary seller action and a clear next step.
- Claims are supportable and do not imply an appraisal, guaranteed price, or superior net proceeds.
- Real or approved high-quality property and team imagery is ready before final visual acceptance.

Implementation notes:

- The public site now uses one responsive header and footer with minimal navigation, visible phone
  contact, legal links, and a consistent direct-offer disclosure.
- The homepage is an address-first, full-bleed Georgia property experience with no unsupported
  speed claim, fabricated review, or implied guarantee of retail value.
- New How It Works, About, and FAQs pages explain offer inputs, company boundaries, assignment,
  timing, costs, privacy, and the direct-offer versus retail-listing tradeoff.
- Inherited-property, repair, and timeline pages use the same seller journey and local visual
  system rather than remote stock-image dependencies.
- Organization and WebSite structured data, canonical metadata, social metadata, sitemap, and
  robots rules cover the new public architecture while excluding authenticated OS routes.
- Three project-bound property images were generated for the public site. Real team photography,
  verified reviews, and quantified proof remain intentionally unpublished until Stonegate supplies
  approved evidence.
- All ten public routes return `200` at desktop and mobile widths with no page overflow. Lint,
  TypeScript, production build, and desktop/mobile axe-core WCAG A/AA checks pass.

## Phase UX10: Public Conversion Journey, Performance, And Measurement

Status: Implementation complete. See
[`UX10_PUBLIC_CONVERSION_JOURNEY.md`](UX10_PUBLIC_CONVERSION_JOURNEY.md). Production field baselines
remain.

Goal: Ship a fast, accessible, compliant offer experience and establish the data needed to improve
conversion honestly.

Deliverables:

- Address-first offer entry point on the homepage and relevant situation pages.
- Progressive property, condition, situation, timeline, contact, and optional-SMS-consent steps.
- Progress, back navigation, answer preservation, field-level errors, and recovery from API failure.
- Optional, unbundled SMS consent with retained disclosure/version/timestamp evidence.
- Conversion events for offer starts, step completion, form errors, submissions, calls, and source
  attribution without collecting unnecessary sensitive data.
- Core Web Vitals targets at the 75th percentile: LCP at or below 2.5 seconds, INP at or below 200
  milliseconds, and CLS at or below 0.1.
- Pre-launch accessibility, SEO, structured-data, analytics, consent, and performance checks.
- Baseline reporting and a controlled testing backlog based on Stonegate traffic.

Exit criteria:

- A seller can complete the offer request with keyboard or mobile input and receives a durable
  confirmation without duplicate leads.
- Consent evidence and conversion attribution reach the OS correctly.
- Performance targets pass in lab testing and field measurement is enabled.
- The first optimization test has a written hypothesis, primary metric, guardrail metric, and
  minimum observation rule before launch.

Implementation notes:

- The offer request is now a four-step property, situation, optional-details, and contact journey
  with clear required/optional boundaries, progress, back navigation, field-level errors, and
  answer preservation.
- A failed API request preserves all answers and can be retried. A successful request stores a
  tab-scoped confirmation and reference so a refresh does not repost the lead.
- Property type, condition, occupancy, mortgage context, and the anonymous conversion session now
  reach the CRM. Duplicate intake fills only missing fields and never overwrites staff-reviewed
  values.
- SMS consent remains separate, optional, unchecked, versioned, and excluded from draft storage.
- Privacy-safe funnel and Core Web Vitals events feed a new public-experience baseline in Marketing.
- Desktop and mobile Playwright journeys, serious/critical axe checks, overflow checks, ESLint,
  TypeScript, production build, Ruff, and all 114 API tests pass.
- Mobile Lighthouse lab results were 98 performance for the offer route and 93-95 for the homepage,
  with 100 accessibility and SEO and zero measured CLS. The offer route LCP was 2.4 seconds; the
  homepage hero LCP varied from 2.9 to 3.3 seconds. Field p75 collection is enabled and remains the
  release evidence for the shared Core Web Vitals target.

## Implementation Order Rules

- Do not begin broad page restyling before UX1 navigation and naming approval.
- Do not create page-local components when UX2 should own the pattern.
- Complete UX3 before upgrading individual workspaces.
- Complete OS workflow phases before applying final public-site polish, but public content and image
  preparation may run in parallel.
- Do not use appearance as evidence of conversion performance; instrument and test it.
- Do not add external communication, AI authority, legal claims, or provider activation merely as
  part of a visual phase.

## Recommended Next Checkpoint

Deploy UX10, verify conversion and Web Vitals events in the production Marketing workspace, and
collect an unmodified baseline before launching the first controlled optimization test. Complete
the real-team, verified-review, final-domain, Twilio, and email checkpoints only when the required
business evidence and provider approvals are available.
