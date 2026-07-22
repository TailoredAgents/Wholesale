# Stonegate Experience Upgrade Roadmap

Last updated: July 22, 2026

Status: Implementation in progress. Phases UX1 through UX3 are complete.

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

Status: Not started.

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

## Phase UX5: Acquisition Workspaces

Status: Not started.

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

## Phase UX6: Deal Execution Workspaces

Status: Not started.

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

## Phase UX7: Business, Reporting, And AI Control

Status: Not started.

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

## Phase UX8: OS Responsive, Accessibility, And Regression Pass

Status: Not started.

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

## Phase UX9: Public Website Architecture, Brand, And Trust

Status: Not started.

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

## Phase UX10: Public Conversion Journey, Performance, And Measurement

Status: Not started.

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

## Implementation Order Rules

- Do not begin broad page restyling before UX1 navigation and naming approval.
- Do not create page-local components when UX2 should own the pattern.
- Complete UX3 before upgrading individual workspaces.
- Complete OS workflow phases before applying final public-site polish, but public content and image
  preparation may run in parallel.
- Do not use appearance as evidence of conversion performance; instrument and test it.
- Do not add external communication, AI authority, legal claims, or provider activation merely as
  part of a visual phase.

## Recommended First Checkpoint

Start UX1 by producing the route inventory, role-navigation matrix, duplicate-page assessment, and
approved label map. The first implementation commit should not change visual styling; it should
document and test the information architecture that the visual system will support.
