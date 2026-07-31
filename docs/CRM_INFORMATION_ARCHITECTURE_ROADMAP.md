# Stonegate CRM Information Architecture Roadmap

Last updated: July 30, 2026

## 1. Purpose And Authority

This roadmap defines the planned reorganization of the private Stonegate Operating System. Its
goal is to make the existing platform easier to understand and operate without creating a second
CRM, replacing working domain models, or removing specialist workflows.

Until an information-architecture phase is implemented:

- `SYSTEM_MAP.md` remains authoritative for current routes and behavior.
- `UI_CONTROL_REFERENCE.md` remains authoritative for current controls.
- `USER_MANUAL.md` and the role manuals remain authoritative for current staff procedures.
- This file describes the approved target and implementation order only.

Update the current-state documents in the same commit that changes a route, control, role
experience, or workflow. Do not document a planned destination as live before it exists.

## 2. Decision

Stonegate will keep its existing normalized business records and reorganize the employee
experience around a small number of task-centered workspaces.

Before IA2, the owner saw 22 primary sidebar destinations across five groups. Several destinations
were different views of the same records, administrative controls were mixed with daily work, and
horizontal journey navigation repeated the sidebar. IA2 reduced the live owner experience to 11
primary destinations:

| Group | Destination |
| --- | --- |
| Work | Home |
| Work | Inbox |
| Work | Tasks |
| Work | Calendar |
| Operations | Prospecting |
| Operations | Seller Leads |
| Operations | Deals |
| Operations | Buyers |
| Business | Finance |
| Business | Marketing |
| Bottom utility | Settings |

Each employee sees only the destinations permitted by their combined roles. The architecture is
capability-based: one person covering several seats receives the union of those workspaces through
one account.

## 3. What Is Correct Today

The upgrade must preserve these existing strengths:

- Cold prospects remain separate from interested seller leads.
- A seller lead remains linked to its contact, property, source, communications, qualification,
  appointments, underwriting, offer, and audit evidence.
- Contract preparation creates the existing Deal and Transaction records rather than a duplicate
  replacement record.
- Disposition cases and buyer records remain distinct but associated with the deal.
- Conversations can represent seller, buyer, transaction, or general business communication.
- PostgreSQL remains the source of truth.
- Current role and permission checks remain authoritative.
- Provider adapters, audit records, approval gates, AI traces, and immutable evidence remain in
  place.
- Existing external URLs and bookmarked internal records remain usable through redirects or
  compatibility routes.

This is primarily a frontend composition and navigation program. Some aggregate API responses and
workflow fields may be added where a unified workspace needs them, but existing records must not
be copied into parallel tables merely to support the new interface.

## 4. Problems To Solve

### 4.1 Navigation Mirrors Implementation

The interface currently exposes many internal subsystems as top-level destinations. Staff must
know whether a task belongs to Campaigns, Prospecting, Lead Desk, All Leads, Seller Pipeline,
Field Operations, Underwriting, Approvals, Transactions, or Dispositions before they can act.

### 4.2 Competing Views Of The Same Work

Lead Desk, All Leads, and Seller Pipeline present the same seller opportunities through different
routes. Table, board, queue, and saved-filter presentations should be views of one Seller Leads
workspace, not competing destinations.

### 4.3 Setup Is Scattered

Campaign creation currently lives under Team & Access while campaign import lives under
Campaigns. Email administration is entered through Inbox. Company policy and AI controls are
separate management destinations. Staff cannot predict where setup belongs.

### 4.4 Linear Navigation Misrepresents Parallel Work

The numbered Deal Journey implies that Underwriting, Approvals, Transactions, Dispositions, and
Buyers are one linear sequence. Buyers are a permanent relationship database, approvals occur at
multiple stages, and transaction coordination can run in parallel with disposition.

### 4.5 Record Context Is Lost

Opening separate workspaces for communication, appointments, underwriting, contracts, and buyer
work can force staff to re-establish which seller, property, or deal they are handling. Related
actions should launch from the canonical record and preserve return context.

### 4.6 Administrative Depth Is Visible To Everyone

Owners need comprehensive controls, but ordinary employees should not learn the complete
administrative architecture to perform their jobs. Role restrictions must reduce both access and
visible complexity.

## 5. Design Principles

1. **Navigation is not a sitemap.** Show stable work areas, not every page or data type.
2. **One canonical record per business concept.** Views may differ; records do not duplicate.
3. **One workspace per employee goal.** Configuration, queue work, and record work have different
   page patterns.
4. **One primary next action.** Every active seller lead and deal must clearly identify one
   responsible owner, one primary action, and one due date. Supporting tasks remain available.
5. **Views are not destinations.** Table, board, calendar, and saved filters operate on the same
   underlying records.
6. **Actions stay in context.** Communication, appointments, underwriting, contracting, and buyer
   matching launch from the record they affect.
7. **Progressive disclosure.** Default screens show decisions and next work. Detailed evidence,
   history, configuration, and audit information remain available without dominating the page.
8. **Role-aware, not person-specific.** Navigation is defined by capabilities and operating seats,
   never hard-coded employee names.
9. **Stable deep links.** Every record, saved view, tab, and selected item should have a shareable
   URL.
10. **No giant client page.** Consolidated workspaces use nested routes or independently loaded
    views. Visual consolidation must not require loading every subsystem at once.
11. **AI appears where judgment occurs.** Copilots use contextual drawers and embedded drafts, not
    permanent banners that compete with normal work.
12. **Mobile and iPad are first-class.** Queue panels become drawers on small screens. Seller
    appointments use a focused tablet workflow.

## 6. Canonical Business Records

### 6.1 Prospect

A cold outreach record imported or added for a campaign. It may contain source contact data,
ranked contact methods, suppression evidence, attempts, callbacks, and a handoff. It is not a
seller CRM lead until Stonegate records genuine interest and performs the approved handoff.

### 6.2 Seller Lead

An interested seller opportunity tied to a contact and property. It owns qualification, seller
communications, appointments, valuation, negotiation, follow-up, and pre-contract work.

The employee-facing label is **Seller Lead**. The top-level workspace label is **Seller Leads**.
This distinguishes the record from cold prospects without introducing unfamiliar terminology.

### 6.3 Deal

The employee-facing aggregate for contract preparation through funded closing. The existing Deal,
Transaction, Contract Package, Disposition Case, reconciliation, and related records remain
separate underneath it.

A Deal may first appear in **Contract preparation** before execution. The interface must state
clearly whether Stonegate is:

- preparing a contract
- awaiting signature
- under contract
- marketing to buyers
- closing
- funded
- cancelled

An unsigned package must never be reported as an executed contract.

### 6.4 Buyer

A permanent investor relationship with criteria, markets, activity, proof, capacity, offers,
purchase history, communication, and restrictions. A buyer is associated with many potential or
completed deals and must not be embedded as a disposable contact inside one disposition case.

### 6.5 Campaign

An attributable outreach effort with market, territory, channel, source, owner, dates, budget,
imports, prospects, calling batches, costs, and results.

### 6.6 Conversation

A durable communication thread linked to a seller lead, buyer, deal, or general business context.
Its activity can appear in the global Inbox and the associated record timeline without creating a
second message record.

### 6.7 Task And Primary Next Action

Tasks are supporting work items. The primary next action is the single required decision or
activity that moves an active seller lead or deal forward.

The target contract for primary work is:

- responsible user
- action type
- short action label
- due date and time
- source record
- completion state
- outcome or decision
- next action created after completion when the record remains active

The implementation may extend the current Lead Management next-action fields and Task model. It
must not create unrelated task systems per department.

## 7. Global Navigation And Controls

### 7.1 Sidebar

The sidebar uses the target 11 destinations. Section labels remain short and stable. An item is
hidden when the signed-in user has neither the role nor permission required to use it.

Do not add integration providers, individual employees, saved filters, or pipeline stages to the
primary sidebar.

### 7.2 Global Header

The global header provides:

- categorized search across seller leads, prospects, properties, deals, buyers, campaigns, and
  destinations
- a permission-aware **New** menu for common record creation
- notifications
- approvals count for authorized reviewers
- recent records
- account menu

Suggested **New** menu actions:

- Seller lead
- Task
- Appointment
- Email
- Buyer
- Campaign, only when opened from a prospecting-capable role

Campaign import remains contextual to a selected campaign and is not a global creation action.

### 7.3 Account Menu

Move **My Setup** into the account menu with:

- signed-in identity
- active roles and permissions summary
- role acceptance and workspace test
- personal sender and signature defaults
- notification preferences when implemented
- sign out

### 7.4 Floating Utilities

- The blue Stonegate Help bubble remains globally available.
- A contextual Copilot control may appear beside records or in the page header.
- Help and Copilot remain separate products: Help explains Stonegate; Copilot analyzes authorized
  operational context and prepares drafts.

### 7.5 Context Preservation

List, queue, and board workspaces must preserve:

- selected saved view
- filters
- sort
- display mode
- selected record
- scroll or pagination position where practical

Opening and closing a preview must not reset the employee's queue.

## 8. Target Workspace Specifications

### 8.1 Home

Home replaces the label **Dashboard** while retaining `/os` as the canonical route.

Home is role-aware and answers:

1. What requires my attention now?
2. What is overdue or blocked?
3. What meetings or deadlines occur today?
4. What changed since I last worked?
5. What should I open next?

Home is not a substitute for detailed records. It links into saved views and selected records.

Owner mode includes:

- company exceptions
- unassigned work
- approval queue
- seller and deal movement
- today's appointments
- cash and closing exceptions
- role coverage
- small performance indicators

Specialist modes prioritize the signed-in user's assigned work. An owner may switch between
personal and company views without impersonating another employee.

### 8.2 Inbox

Inbox remains a top-level three-panel workspace.

Left:

- Mine
- Needs Reply
- Unread
- Unassigned
- Team inboxes
- authorized department inboxes
- saved views

Middle:

- one chronological timeline for email, SMS, calls, recordings, transcripts, notes, and system
  delivery events
- composer mode changes channel without hiding the shared history

Right:

- associated seller, buyer, deal, or general-business context
- owner, stage, next action, appointment, and pinned notes
- contextual Copilot summary when authorized

Email Management moves to Settings. The Inbox may link to those settings for authorized users but
must not render provider administration as a normal mailbox view.

### 8.3 Tasks

Tasks replaces the label **Work Queue** and absorbs the global Approvals destination.

Views:

- My Tasks
- Due Today
- Overdue
- Upcoming
- Unscheduled
- Team, for managers
- Approvals, for authorized decision-makers
- Completed

The page distinguishes:

- primary next actions
- supporting tasks
- approval decisions
- automated exception alerts

Completing a primary next action must require an outcome and, when the source record remains
active, a replacement next action or an explicit workflow transition.

Approvals remain their own API records and authority checks. They are aggregated into Tasks for
navigation only and remain visible on the affected Seller Lead, Deal, Finance, or AI record.

### 8.4 Calendar

Calendar remains the canonical schedule and gains appointment execution entry points.

Views:

- Month
- Week
- Day
- Agenda
- Team capacity, for authorized managers

Selecting an ordinary event opens its context. Selecting a seller appointment opens a focused
appointment workspace with:

- Brief
- Walkthrough
- Photos and property evidence
- Seller presentation
- Negotiation
- Outcome
- In-person signing when approved

The old Field Operations route remains a compatibility deep link during migration. Field
Operations is no longer a primary sidebar destination after Calendar reaches feature parity.

On iPad, the meeting workspace uses a full-width guided layout, stable sticky actions, large touch
targets, and no squeezed three-column desktop layout.

### 8.5 Prospecting

Prospecting combines the current Campaigns and Prospecting destinations.

Manager views:

- Overview
- Campaigns
- Imports
- Calling Batches
- Handoffs
- Results

Caller views:

- My Calls
- Callbacks
- Handoffs

Campaign creation lives at:

`Prospecting > Campaigns > New Campaign`

A selected campaign contains:

- Summary
- Prospects
- Imports
- Assignments
- Costs And Results
- Settings

The import flow begins inside a selected campaign so staff never encounter an unexplained
campaign picker. The importer may offer **Create campaign** as an authorized escape hatch without
moving the user to Team & Access.

Market and territory definitions move to Settings. Campaign selection, list import, caller
assignment, and campaign results remain operational Prospecting work.

VAs keep the focused one-by-one calling interface. They do not receive manager campaign,
financial, export, buyer, underwriting, contract, or company settings views.

### 8.6 Seller Leads

Seller Leads combines:

- Lead Desk
- All Leads
- Seller Pipeline
- active Underwriting queue

These become views of one seller dataset rather than separate destinations.

Default saved views:

- Mine
- New
- Needs Qualification
- Needs Follow-Up
- Appointments
- Needs Underwriting
- Offer And Negotiation
- Nurture
- Unassigned
- All
- Archived

Display modes:

- Table
- Board

The board and table use the same filters and records. Changing display mode must not change the
meaning of the selected saved view.

Primary actions:

- New Seller Lead
- Assign
- Schedule
- Contact
- Run Analysis
- Update Stage
- Set Next Action

### Seller Lead Record

Persistent header:

- seller name
- property address
- stage
- owner
- priority or temperature
- primary next action and due date
- next appointment
- call, text, email, schedule, and more actions

Stable record sections:

1. **Summary**
   - qualification
   - missing or conflicting facts
   - seller and property snapshot
   - next action
   - open tasks
   - Copilot draft
2. **Activity**
   - communications
   - calls and transcripts
   - internal notes
   - task and appointment events
   - stage, document, provider, and audit events
3. **Property**
   - canonical facts
   - ownership
   - condition
   - repairs
   - photographs
   - field evidence
4. **Valuation And Offer**
   - subject match
   - comps and evidence
   - repair assumptions
   - ARV and as-is ranges
   - buyer-demand evidence
   - reports
   - offer authority
   - negotiation ledger
5. **Appointments**
   - scheduled and historical meetings
   - preparation
   - outcomes
6. **Contract And Deal**
   - contract preparation
   - approval
   - signature
   - associated Deal after creation
7. **Files**
   - seller and property documents
   - generated reports
   - signed records appropriate to the user's role

The current Communications and History tabs are consolidated into Activity. Sensitive internal
economics remain hidden from seller presentation mode.

### Seller Acquisition Stage Families

Use understandable stage families while retaining detailed internal statuses:

- New
- Contacting
- Qualifying
- Qualified
- Appointment
- Underwriting
- Offer And Negotiation
- Nurture
- Contract Preparation
- Converted To Deal
- Lost

Stage, owner, task, and next action are separate concepts. Reassigning a record must not move its
stage.

### 8.7 Deals

Deals combines the employee experience currently split between Transactions and Dispositions.
The underlying Deal, Transaction, Disposition Case, Buyer Offer, Contract Package, document,
checklist, accounting, and reconciliation records remain separate.

Default saved views:

- My Deals
- Contract Preparation
- Awaiting Signature
- Contracted
- Closing Exceptions
- Ready For Disposition
- Marketing To Buyers
- Buyer Selected
- Closing Scheduled
- Funded
- Cancelled

Display modes:

- Table
- Board based on the next critical milestone

Because closing and disposition can run in parallel, the Deal record shows independent status:

- Contract
- Transaction and title
- Disposition
- Financial reconciliation

The board must not claim these parallel processes form a perfect linear sequence.

### Deal Record

Persistent header:

- property
- seller
- contract status
- purchase price
- expected or actual assignment revenue
- closing date
- transaction coordinator
- disposition owner
- primary next action
- blockers

Stable sections:

1. **Summary**
2. **Contract**
3. **Closing**
4. **Disposition**
5. **Financials**
6. **Activity**
7. **Files**

Disposition includes package readiness, buyer matches, marketing, engagement, offers, proof,
deposits, primary buyer, and backup buyer. Buyer matching may be previewed during Seller Lead
underwriting, but outbound buyer marketing remains gated by the approved deal workflow.

Transactions and Dispositions may retain nested compatibility routes during development. They
must not remain competing top-level sidebar destinations after the Deal workspace passes role
acceptance.

### 8.8 Buyers

Buyers remains a top-level long-lived relationship database.

Saved views:

- Active
- Needs Verification
- By Market
- Recently Engaged
- Proof Expiring
- Restricted Or Opted Out
- All

Buyer record sections:

- Summary
- Criteria And Markets
- Activity
- Offers And Purchases
- Proof And Capacity
- Files

Deal-specific matching and outreach occur from the Deal record and link back to the same Buyer.
Provider candidates remain reviewable before import and never overwrite trusted evidence.

### 8.9 Finance

Finance remains a separate permission-protected business workspace because its users, evidence,
and authority differ materially from seller acquisition work.

Its local navigation may be reorganized, but the IA program must preserve:

- operational source records
- posting and payment control
- double-entry ledger
- vendors and bills
- bank statements and reconciliation
- compensation
- reports and close
- CPA export
- Finance and Tax Copilots

Deal financial summaries link to Finance source records without exposing restricted company books
to acquisitions or disposition roles.

### 8.10 Marketing

Marketing remains a separate owner or marketing workspace for:

- funnel performance
- source and campaign economics
- website conversion
- controlled experiments
- public trust proof
- offline conversion delivery
- marketing recommendations

Campaign execution and list operations live in Prospecting. Marketing reads the same Campaign,
cost, lead, contract, and funded-outcome records for performance analysis.

### 8.11 Settings

Settings replaces the current collection of Team & Access, Email Management, Company & Policy,
and AI Control destinations.

Use a stable left-side settings navigation with these sections:

1. **Company**
   - legal and display identity
   - brand and public contact defaults
   - service standards
2. **Markets And Territories**
   - markets
   - territories
   - team coverage
   - launch readiness
3. **People And Access**
   - users
   - roles
   - teams
   - operating seats
   - activation and deactivation
4. **Communications**
   - Resend senders and routing
   - signatures and templates
   - mailbox grants
   - Twilio numbers and routing
   - channel availability and consent settings
5. **Integrations**
   - provider connection status
   - required configuration names
   - webhook readiness
   - acceptance status
   - no displayed secret values
6. **Workflows**
   - stage definitions
   - qualification scripts
   - follow-up plans
   - appointment policies
   - assignment rules
7. **Data And Quality**
   - duplicates
   - merge review
   - import mappings
   - archives
   - audit and retention controls
8. **Finance Policy**
   - operating plan
   - compensation
   - contribution credits
   - disposition mode
9. **AI And Automation**
   - copilots
   - models
   - capability contracts
   - evaluations
   - traces
   - budgets
   - autonomy and shutdown controls

Settings sections remain permission-filtered. Consolidating navigation does not broaden access.

## 9. Role Experiences

| Role or seat | Default destination | Normal visible workspaces |
| --- | --- | --- |
| Owner and CEO | Home, company view | All target destinations |
| Lead Manager | Seller Leads, New or Needs Qualification | Home, Inbox, Tasks, Calendar, Seller Leads |
| Acquisitions Closer | Calendar, today's appointments | Home, Inbox, Tasks, Calendar, Seller Leads, Deals when assigned |
| VA Caller | Prospecting, My Calls | Prospecting and account setup only |
| Transaction Coordinator | Deals, Closing Exceptions | Home, Inbox, Tasks, Calendar, Deals |
| Dispositions | Deals, Ready For Disposition | Home, Inbox, Tasks, Calendar, Deals, Buyers |
| Finance and bookkeeping | Finance | Home, Inbox when granted, Tasks, Calendar when needed, Deals summary, Finance |
| Marketing | Marketing | Home, Prospecting summary when granted, Marketing |

When one person covers multiple seats, Stonegate combines the authorized destinations and saved
views. It does not create multiple accounts or force a workspace switch for each title.

## 10. Copilot And Help Placement

### 10.1 Contextual Copilots

Replace large permanent Copilot areas with:

- a named Copilot button in the relevant header
- a right-side drawer containing summary, evidence, recommendation, and draft actions
- embedded recommendation cards beside the record or decision they concern
- explicit review, accept, correct, and reject controls

Copilot context follows the selected record. Opening a Copilot must not navigate away or hide the
source evidence.

### 10.2 AI Control

The current AI Control capability moves to `Settings > AI And Automation`. It remains visible only
to authorized owners. Runtime governance is configuration, not daily employee navigation.

### 10.3 Stonegate Help

The Help bubble remains a non-operational documentation assistant. It must be updated after each
phase so it answers using the current interface, not the final planned roadmap.

## 11. Route And Compatibility Plan

| Current route | Target canonical destination | Compatibility behavior |
| --- | --- | --- |
| `/os` | `/os` Home | Keep |
| `/os/inbox` | `/os/inbox` | Keep |
| `/os/tasks` | `/os/tasks` Tasks | Keep and rename display label |
| `/os/calendar` | `/os/calendar` | Keep |
| `/os/campaigns` | `/os/prospecting?view=campaigns` | Redirect implemented |
| `/os/prospecting` | `/os/prospecting` | Keep as workspace root |
| `/os/lead-manager` | `/os/leads?view=needs-qualification` | Redirect after parity |
| `/os/leads` | `/os/leads` Seller Leads | Keep |
| `/os/pipeline` | `/os/leads?display=board` | Redirect after parity |
| `/os/field-operations` | `/os/calendar` or selected appointment | Preserve deep links, then redirect list view |
| `/os/underwriting` | `/os/leads?view=needs-underwriting` | Redirect queue; move calibration to Settings |
| `/os/approvals` | `/os/tasks?view=approvals` | Redirect after parity |
| `/os/transactions` | `/os/deals?view=closing` | Preserve selected transaction during redirect |
| `/os/dispositions` | `/os/deals?view=disposition` | Preserve selected disposition case during redirect |
| `/os/buyers` | `/os/buyers` | Keep |
| `/os/finance` | `/os/finance` | Keep |
| `/os/marketing` | `/os/marketing` | Keep |
| `/os/my-setup` | account menu setup panel | Preserve direct route for onboarding links |
| `/os/operations` | `/os/settings/...` | Redirect each tab to its new owner |
| `/os/inbox?manage=email` | `/os/settings/communications/email` | Redirect after parity |
| `/os/operating-model` | `/os/settings/finance-policy` | Redirect after parity |
| `/os/ai` | `/os/settings/ai` | Redirect after parity |
| `/os/leads/{lead_id}` | `/os/leads/{lead_id}` | Keep |

Do not replace working routes with redirects until:

1. the target has feature parity
2. role and permission tests pass
3. documentation is updated
4. deep-link parameters are preserved
5. production smoke tests pass

## 12. Shared Page Patterns

### 12.1 Queue Pattern

Use for Prospecting, Seller Leads, Tasks, and Deals:

- local saved views and counts
- search, filters, sort, and display controls
- stable list or board
- selected-record preview
- contextual actions
- optional right context rail on wide screens

### 12.2 Record Pattern

Use for Seller Lead, Deal, Buyer, and Campaign:

- breadcrumb
- persistent record header
- key status and next action
- short, stable local navigation
- read-first summary
- edit controls only where needed
- one chronological activity timeline
- related records and files
- contextual Copilot drawer

### 12.3 Guided Process Pattern

Use for:

- CSV import
- one-by-one calling
- seller qualification
- field appointment
- contract release
- reconciliation

A guided process shows progress and required decisions. It does not become a permanent top-level
destination merely because it is complex.

### 12.4 Settings Pattern

Use a fixed settings subnavigation and independently loaded sections. Settings forms should not be
nested inside operational cards or Inbox panels.

## 13. Implementation Phases

## IA1. Architecture Contract And Baseline

Status: **Implemented**

Scope:

- approve this roadmap as the target
- create a durable architecture decision record
- inventory every current route, link, permission, query parameter, and help reference
- define analytics or test evidence for navigation usage
- capture desktop, tablet, and mobile baseline screenshots
- define canonical vocabulary and route ownership

Exit criteria:

- every current destination maps to one target workspace or an intentional retained route
- no current control is unaccounted for
- role visibility matrix is executable as tests
- old and new terminology is documented

## IA2. Shell, Navigation, And Global Controls

Status: **Implemented**

Scope:

- implement the target sidebar
- rename Dashboard to Home and Work Queue to Tasks
- create placeholders or compatibility links for consolidated destinations
- remove duplicated horizontal journey navigation only where local replacement navigation exists
- standardize global search, New menu, notifications, approvals count, recent records, and account
  menu placement
- preserve current URLs during transition

Exit criteria:

- owner sees no more than 11 primary destinations
- each role sees only authorized destinations
- every existing page remains reachable
- active-route highlighting works for nested and compatibility routes
- desktop and mobile navigation pass visual checks

## IA3. Settings Consolidation

Status: **Implemented July 30, 2026**

Scope:

- create the Settings shell and permission-filtered subnavigation
- move users, teams, seats, markets, territories, email administration, operating policy, and AI
  controls into their target sections
- move duplicate review, follow-up configuration, and import mappings to Data And Quality or
  Workflows
- keep campaign creation out of Settings
- add provider status without displaying secrets

Exit criteria:

- administrative configuration has one predictable entry point
- each current Operations tab has one documented new owner
- Email, Company Policy, and AI retain feature parity
- unauthorized roles cannot load restricted sections directly
- old management links route to the correct settings section

## IA4. Prospecting Consolidation

Status: **Implemented July 30, 2026**

Scope:

- place campaign list and creation inside Prospecting
- make selected campaigns own imports, assignments, costs, and results
- retain the specialized caller workbench
- add manager and caller local views
- make the PropStream importer begin with selected campaign context
- preserve one-by-one calling, callbacks, handoffs, attribution, and caller restrictions

Exit criteria:

- an authorized owner can create a campaign in two navigation decisions or fewer
- a file can be imported without leaving Prospecting
- a caller opens directly to assigned calling work
- imported prospects remain separate from seller leads
- campaign costs and outcomes remain attributable
- `/os/campaigns` compatibility works

## IA5. Seller Leads Consolidation

Status: **Implemented July 30, 2026**

Scope:

- unify Lead Desk, lead list, and pipeline as views of Seller Leads
- add table and board display switching
- standardize saved views
- incorporate the active underwriting queue
- refactor the seller record to the target stable sections
- merge Communications and History into Activity
- retain manual lead creation, archive, lifecycle, qualification, communication, underwriting,
  reports, appointments, negotiation, and contract preparation

Exit criteria:

- staff never choose between Lead Desk, All Leads, and Seller Pipeline to find the same seller
- filters and selected records survive table or board switching
- Lead Manager workflow remains SLA-aware
- a seller record exposes one owner, one primary next action, and one due date
- all current lead controls have an accounted-for target
- existing lead deep links remain valid

## IA6. Calendar And Appointment Execution

Status: **Implemented July 30, 2026**

Scope:

- launch field meeting execution from Calendar
- combine appointment preparation, walkthrough, photos, presentation, negotiation, outcome, and
  approved in-person signing
- move capacity and availability management into Calendar or Settings as appropriate
- optimize appointment mode for iPad
- preserve existing appointment deep links

Exit criteria:

- a closer reaches today's meeting workspace from Calendar in one selection
- appointment context does not require a separate sidebar destination
- seller presentation still hides internal economics
- iPad viewport passes screenshot, touch-target, and overflow checks
- existing Field Operations capabilities retain parity

## IA7. Tasks, Approvals, And Primary Next Actions

Status: **Implemented July 30, 2026**

Scope:

- aggregate tasks, approvals, and operational exceptions in Tasks
- formalize one primary next action for active seller leads and deals
- require outcome and successor action or terminal transition
- add manager team views
- retain permission-specific approval decisions and source evidence

Exit criteria:

- every active seller lead and deal can answer who, what, and when
- overdue and unassigned work is visible without inspecting every pipeline
- approvals remain permission-protected and auditable
- completing a task does not silently strand an active record
- Home and record headers use the same next-action truth

## IA8. Unified Deals

Status: **Implemented July 31, 2026**

Scope:

- create the Deal queue, table, board, saved views, and record shell
- compose Transaction and Disposition data through one Deal record
- show independent contract, closing, disposition, and finance status
- place buyer matches and offers inside Disposition
- preserve role-specific access to economics, documents, proof, and accounting
- redirect existing transaction and disposition list routes only after parity

Exit criteria:

- one contracted property has one employee-facing Deal record
- transaction and disposition staff can work simultaneously without overwriting status
- contract, title, buyer, closing, and financial blockers remain independently visible
- current transaction and disposition controls have target locations
- role tests confirm no restricted economics leak

Implementation note: `/os/transactions` and `/os/dispositions` remain authorized compatibility
routes. The unified record has parity for established transaction and disposition cases, while a
new disposition case is still opened through the specialist setup route. Redirecting that route
before setup parity would remove a working control, so final redirects remain an IA10 decision.

## IA9. Record Standards, Contextual AI, And Responsive Quality

Status: **Implemented July 31, 2026**

Scope:

- standardize Seller Lead, Deal, Buyer, and Campaign headers and local navigation
- standardize activity timelines and related-record links
- replace permanent Copilot areas with contextual launchers, drawers, and embedded drafts
- preserve the Help bubble as a separate utility
- implement list preview and return-context behavior
- verify desktop, mobile, and iPad layouts
- load only the active nested view and required record data

Exit criteria:

- comparable record types behave consistently
- Copilot never hides source evidence or changes records without the existing review flow
- no horizontal journey duplicates the sidebar
- mobile panels become usable drawers
- target pages do not load every subsystem eagerly

Implementation note: Seller Lead, Deal, Buyer, and Campaign records now preserve selected-record
and local-tab context in their URLs. Seller and Buyer related-record links preserve the originating
list view. Buyer detail becomes a drawer on phone layouts. Canonical Deals loads Transaction or
Disposition data only for the active section and exposes their existing review-gated Copilots in
context. Seller records load the buyer dataset only for Contract & Deal, and Prospecting loads only
Campaigns or My Calls data for the selected view. Duplicate acquisition and deal journey strips
were removed from the canonical Prospecting and Buyers pages; the separate Help bubble remains
unchanged.

## IA10. Compatibility, Documentation, And Role Acceptance

Status: **Implemented July 31, 2026**

Scope:

- add final compatibility redirects
- remove obsolete navigation components and unreachable duplicate UI
- update System Map, User Manual, UI Control Reference, role manuals, setup manuals, screenshots,
  and Help ingestion
- run automated route, permission, API, lint, type, and build checks
- run role acceptance with Owner, Lead Manager, Closer, VA, Transaction, Disposition, and Finance
  accounts
- run controlled production smoke tests

Exit criteria:

- no obsolete documentation instructs staff to use retired navigation
- old bookmarks reach the correct target with record and selected-view context
- each role completes its daily routine without owner-level navigation knowledge
- no required feature or record history is lost
- production passes desktop, mobile, and iPad acceptance

Implementation note: the global Tools menu and duplicate journey strips were removed after their
controls reached canonical parity. My Setup remains at the bottom of every signed-in user's
sidebar. `/os/transactions` now resolves the selected transaction and tab into the matching Deal.
`/os/dispositions?case=...` resolves the selected case into the matching Deal, while the route
without a case retains only the first-case setup form. The embedded transaction and disposition
tools no longer render their own queues, record headers, or local tab bars inside Deals.

The System Map, User Manual, UI Control Reference, Staff Role Manuals, Lead Manager Manual, AI
documentation, and Help sources now use the canonical workspace language. Automated acceptance
checks cover route ownership, static deep links, role visibility, role defaults, permission
inventory synchronization, retired navigation removal, canonical Help sources, and retained
record context. Production employee-seat smoke checks remain an operational deployment task when
each real staff account is activated; they do not require additional information architecture.

## 14. Cross-Phase Acceptance Standards

### 14.1 Findability

An authorized user can:

- create a campaign from Prospecting in two navigation decisions or fewer
- import prospects from the selected campaign
- create a manual seller lead from Seller Leads or the global New menu
- find a seller from global search
- open today's appointment from Calendar
- run valuation from the Seller Lead
- find an executed contract from the Seller Lead or Deal
- open buyer matching from the Deal
- add an employee from Settings
- find provider configuration from Settings

### 14.2 Role Simplicity

- Owner: no more than 11 primary destinations
- VA: Prospecting plus personal account setup only
- Lead Manager: normal work does not require Settings, Deals, Buyers, Finance, or AI Control
- Closer: normal appointment work begins in Calendar
- Transaction Coordinator: normal closing work begins in Deals
- Dispositions: normal buyer placement work begins in Deals
- Finance: company books remain isolated from acquisition roles

### 14.3 Record Integrity

- no duplicate prospect, seller lead, deal, buyer, message, or accounting system is introduced
- route consolidation never changes organization scoping
- stage changes, assignments, approvals, and audit events remain attributable
- imported source and consent evidence remain intact
- unsigned contracts remain visibly unsigned
- posted journals remain immutable

### 14.4 Interaction Quality

- lists retain filters and selected context
- table and board modes represent the same record set
- empty states name the next permitted action
- disabled controls explain the prerequisite
- page and tab labels use employee language
- settings use forms; operational pages prioritize reading and action
- record headers do not shift when status or buttons change
- no text, controls, or panels overlap at supported viewports

### 14.5 Performance

- consolidated navigation does not create monolithic data requests
- nested views fetch only their required data
- large tables paginate or virtualize when volume requires it
- activity timelines paginate
- images and documents load on demand
- role navigation does not repeatedly fetch the same profile within one request when avoidable

## 15. Non-Goals

This roadmap does not authorize:

- rebuilding the API or database from scratch
- combining prospects and seller leads
- combining buyers and sellers
- replacing the internal accounting system
- changing approved underwriting formulas
- weakening role permissions or approval gates
- activating provider credentials
- granting AI new autonomy
- redesigning the public seller website
- organizing navigation around current employee names
- deleting current routes before compatibility is proven

## 16. Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| A consolidated page becomes too large | Use nested routes, independent loaders, and stable local navigation |
| Controls disappear during relocation | Maintain a route-to-control inventory and parity checklist |
| Old bookmarks break | Preserve compatibility routes and query parameters until IA10 |
| Role access broadens accidentally | Test both visible navigation and direct API/URL access for every role |
| Staff relearn the system repeatedly | Release complete workspace slices and update Help in the same deployment |
| Pipeline stages are confused with task ownership | Display stage, owner, and primary next action as separate fields |
| Deal work is forced into a false linear flow | Show independent contract, closing, disposition, and financial status |
| AI becomes more visually prominent than work | Use contextual drawers and embedded drafts only |
| Navigation consolidation hurts performance | Load active views independently and enforce performance checks |

## 17. Research Basis

The target incorporates these product and design patterns:

- GOV.UK service-navigation guidance: primary navigation should expose the most important
  top-level sections and should not serve as a complete sitemap.
  - https://design-system.service.gov.uk/patterns/navigate-a-service/
- HubSpot Sales Workspace: records, tasks, suggested actions, and schedule remain accessible from a
  unified work context.
  - https://knowledge.hubspot.com/sales-workspace/manage-sales-activities-in-the-updated-sales-workspace
- Salesforce console: split list and record views reduce context switching while preserving access
  to related records.
  - https://trailhead.salesforce.com/content/learn/modules/lightning-experience-for-salesforce-classic-users/work-with-your-data
- InvestorFuse: one primary action per opportunity gives a real-estate acquisitions team a clear
  daily queue while allowing supporting tasks.
  - https://www.investorfuse.com/features/core/action-based-system
- REsimpli: seller details, communication history, notes, tasks, and appointments are organized
  around the lead profile.
  - https://help.resimpli.com/en/articles/11046029-what-is-lead-details-first-tab-lead-profile
- Left Main REI: valuation, market evidence, and buyer intelligence are most useful in the
  opportunity and transaction context.
  - https://docs.leftmainrei.co/docs/disposignals-frequently-asked-questions

These sources provide pattern evidence, not proof that any vendor's complete product should be
copied. Stonegate's operating model, roles, record boundaries, and actual usability acceptance
remain authoritative.

## 18. Documentation Update Matrix

Every implementation phase updates:

| Change | Required documentation |
| --- | --- |
| Current navigation or route changes | `SYSTEM_MAP.md`, `USER_MANUAL.md`, `UI_CONTROL_REFERENCE.md` |
| Role default or visible destination changes | `STAFF_ROLE_MANUALS.md`, `LEAD_MANAGER_USER_MANUAL.md` when applicable |
| Setup control moves | `SETUP_MANUAL.md`, `SETUP_REFERENCE.md` when provider instructions change |
| Data or workflow contract changes | `SYSTEM_MAP.md`, relevant domain reference, migration notes |
| AI placement or authority changes | `AI_AGENTS.md`, `AI_AUTOMATION_ROADMAP.md`, `SECURITY_COMPLIANCE.md` |
| Remaining phase status changes | this roadmap and `FINISHING_ROADMAP.md` |
| Help-visible workflow changes | approved Help source documents and retrieval verification |

Mark a phase **Implemented** only after its code, automated checks, role acceptance, compatibility,
and current-state documentation are all updated.

## 19. IA1 Architecture Baseline

IA1 was implemented on July 30, 2026. It establishes the migration contract without changing the
current employee interface.

### 19.1 Accepted Decision

`DECISIONS/0003-task-centered-os-information-architecture.md` accepts the 11-destination target,
preserves the existing business-record boundaries, and requires compatibility until each target
workspace reaches parity.

### 19.2 Executable Inventory

`../apps/web/scripts/os-ia-contract.mjs` records:

- all 24 current `/os` App Router pages, including the dynamic Seller Record and development-only
  Design System
- all 22 current primary navigation items and their target workspace
- current consumed query parameters and two known emitted-but-unhandled parameters
- all 52 API permission keys and all 15 role keys
- the target role experience for every current role
- old-to-new employee vocabulary
- every level-two section in `UI_CONTROL_REFERENCE.md` and its future owner
- the canonical Help source set and visual evidence commands

The two known query issues are preserved as explicit migration work instead of being lost:

- Marketing emits `/os/leads?q=...`, but the current All Leads page does not consume `q`.
- the header notification control emits `/os/operations?view=notifications`, but Operations does
  not consume `view`.

### 19.3 Automated Contract

Run:

```bash
npm --prefix apps/web run audit:ia
```

The check fails when:

- an `/os` page is added or removed without a migration owner
- a current sidebar item is omitted from the contract
- a static internal OS link or query key has no route owner
- an API role or permission changes without an IA review
- a Help control-reference section is added or removed without a future owner
- the target exceeds 11 destinations or violates the explicit VA and AI-service boundaries

CI runs this contract before the web production build.

### 19.4 Visual Baseline

Run against a working local web server:

```bash
npm --prefix apps/web run baseline:ia
```

The runner captures each current non-dynamic OS destination at:

- mobile: 390 by 844
- tablet: 1024 by 1366
- desktop: 1440 by 900

Screenshots and `manifest.json` are written to `.artifacts/os-ia-baseline/`. The artifacts are local
verification evidence and are intentionally excluded from Git. A capture fails when the route
returns an error, redirects to sign-in, raises a browser exception, renders the application error
boundary, logs an unexpected browser error, lacks an H1, or renders materially blank. The runner
records but ignores the expected keyless-Clerk 401 produced by an unsigned local screenshot
session; role visibility is enforced separately by the executable role contract.

The July 30, 2026 baseline contains 66 captures across 22 routes and three viewports. It completed
with zero failed captures, error boundaries, fatal browser errors, or document-level horizontal
overflow against the current web/API code and local database migration `0077`.

### 19.5 IA2 Handoff

IA2 was the next phase after this baseline. Section 20 records its implementation and verification.

## 20. IA2 Shell And Navigation

IA2 was implemented on July 30, 2026.

### 20.1 Live Navigation

The owner sidebar now contains exactly 11 destinations:

- Work: Home, Inbox, Tasks, Calendar
- Operations: Prospecting, Seller Leads, Deals, Buyers
- Business: Finance, Marketing
- Administration: Settings

Non-owner navigation is filtered by both operating role and API permission. AI service users
receive no employee navigation. The focused VA Caller experience retains only Prospecting.

### 20.2 Compatibility

No previous workspace was removed. The global **Tools** menu exposes authorized Campaigns, Lead
Desk, Seller Pipeline, Field Operations, Underwriting, Approvals, Transactions, Dispositions, My
Setup, Team & Access, Email Management, Company & Policy, and AI Control routes while later
consolidation phases are completed.

The new Deals and Settings routes are working compatibility hubs over existing records and
workspaces. They do not create parallel business data.

Legacy routes activate the correct primary destination:

- Campaigns activates Prospecting.
- Lead Desk, Seller Pipeline, Underwriting, and Seller records activate Seller Leads.
- Field Operations activates Calendar.
- Approvals activates Tasks.
- Transactions and Dispositions activate Deals.
- My Setup, Operations, Company & Policy, and AI Control activate Settings.

### 20.3 Global Controls

- **New** opens direct actions for a seller lead and company email when permitted.
- Search covers both primary destinations and authorized compatibility tools.
- Recent destinations remain in a fixed header location.
- Approvals have a fixed header shortcut and pending count for authorized reviewers.
- Notifications now open the consumed Operations `today` tab instead of emitting an unsupported
  query parameter.
- Clerk account controls remain the rightmost header action.

The direct New links consume `/os/leads?new=lead` and `/os/inbox?compose=email`.

### 20.4 Verification

- IA contract: 10 tests passed.
- TypeScript: passed after production route generation.
- ESLint: passed.
- Next.js production build: passed with `/os/deals` and `/os/settings`.
- Visual baseline: 72 captures across mobile, tablet, and desktop; zero failed routes, error
  boundaries, fatal browser errors, or document-level horizontal overflow.
- Manual review covered Home, Deals, Settings, and the mobile global header.

### 20.5 Handoff

IA3 followed this baseline. Section 21 records its implementation and verification.

## 21. IA3 Settings Consolidation

IA3 was implemented on July 30, 2026.

### 21.1 Live Settings Structure

`/os/settings` now redirects to the first section the signed-in employee may access. A stable,
responsive local navigation exposes only authorized sections:

| Section | Live route | Primary permission owner |
| --- | --- | --- |
| Company | `/os/settings/company` | `operating_model:manage` |
| Markets & Territories | `/os/settings/markets` | Operations or operating-model management |
| People & Access | `/os/settings/people` | User or operations management |
| Communications | `/os/settings/communications` | Email or voice administration |
| Integrations | `/os/settings/integrations` | Integration credential management |
| Workflows | `/os/settings/workflows` | Operations management |
| Data & Quality | `/os/settings/data-quality` | Operations, archive, or audit management |
| Finance Policy | `/os/settings/finance-policy` | Operating-model or compensation management |
| AI & Automation | `/os/settings/ai` | AI prompt/control management |

Direct section requests run the same server-side permission check used to build the local
navigation. Unauthorized sections return no page content.

### 21.2 Existing Features Moved, Not Duplicated

- Company reuses the operating-seat, counterparty, and role-acceptance controls.
- Markets reuses market and territory controls plus market-launch evidence.
- People reuses user, access-role, cold-calling eligibility, and team controls.
- Communications embeds the existing sender, grant, signature, and inbound-routing administrator.
- Workflows and Data & Quality reuse the existing follow-up and duplicate-review controls.
- Finance Policy reuses active policy, work-credit, and policy-history controls.
- AI & Automation reuses the existing Stonegate Copilot control plane.
- Campaign and prospect creation remain under Prospecting and Campaigns, not Settings.

### 21.3 Former Operations Tab Ownership

| Former tab | New owner |
| --- | --- |
| Calendar | `/os/calendar` |
| Markets & campaigns | Markets under Settings; campaigns and prospects under Prospecting |
| Calling lists | `/os/prospecting` |
| Team | `/os/settings/people` |
| Data quality | `/os/settings/data-quality` |
| Follow-up plans | `/os/settings/workflows` |

### 21.4 Compatibility And Provider Status

- `/os/operations` redirects by its `tab` query to the correct owner.
- `/os/inbox?manage=email` redirects to Communications settings.
- `/os/operating-model` redirects to Finance Policy.
- `/os/ai` redirects to AI & Automation.
- The Integrations page reports enabled/configured state and missing environment-variable names
  for OpenAI, property data, Resend, Twilio, SignWell, DealMachine, document storage, and Sentry.
  Credential values are never returned to the browser.

### 21.5 Verification

- IA contract: 10 tests passed with every new App Router page inventoried.
- ESLint and TypeScript: passed.
- Next.js production build: passed with all nine nested Settings routes.
- Settings visual baseline: 30 captures across mobile, tablet, and desktop; zero failed routes,
  fatal browser errors, or document-level horizontal overflow.
- Targeted API regression suite: 22 tests passed across operations, company setup, operating
  model, email administration, AI controls, voice lines, and integration status.
- Six legacy management URL cases were verified to reach their intended new owner.

### 21.6 Next Phase

IA4 followed this phase. Section 22 records its implementation and verification.

## 22. IA4 Prospecting Consolidation

IA4 was implemented on July 30, 2026.

### 22.1 One Prospecting Destination

`/os/prospecting` now owns two permission-aware local views:

- **Campaigns** for authorized managers to create campaigns, select campaign context, import
  prospect lists, attribute costs, assign calling batches, and inspect results
- **My Calls** for callers to open their assigned one-by-one calling queue directly

Manager accounts default to Campaigns. Caller-only accounts default to My Calls and do not receive
campaign-management data or controls.

### 22.2 Selected Campaign Context

The campaign selector is now the context owner for Overview, Import, Costs, Assignments, and
History. Each control automatically writes to the selected campaign, removing repeated campaign
selectors and reducing cross-campaign attribution mistakes. The selected campaign and local view
are preserved through `view`, `campaign`, and `campaignView` query parameters.

Campaign creation now lives at the top of Prospecting and uses the existing market, territory,
owner, channel, date, and budget records. This moves the existing feature; it does not create a
second campaign model.

### 22.3 Preserved Record Boundaries

- Imported cold prospects remain prospect records until a valid warm handoff creates a seller lead.
- Existing PropStream mapping, validation, duplicate matching, source history, and contact evidence
  remain unchanged.
- Existing one-by-one call attempts, callbacks, qualification, appointment handoff, cost
  attribution, and caller permissions remain unchanged.
- `/os/campaigns` redirects to `/os/prospecting?view=campaigns`.

### 22.4 Verification

- IA contract: 10 tests passed.
- ESLint, TypeScript, and the Next.js production build passed.
- Fifteen targeted campaign, acquisition-operations, and prospecting API tests passed.
- The Campaigns workspace and legacy redirect passed six formal browser captures across mobile,
  tablet, and desktop with no failed routes, fatal browser errors, or horizontal overflow.
- My Calls passed three additional responsive captures with no horizontal overflow; its only
  browser error was the expected unauthorized Help request in the credential-free local browser.

### 22.5 Next Phase

IA5 is complete. IA6 moves field meeting execution into Calendar while preserving appointment
deep links and the iPad workflow.

## 23. IA5 Seller Leads Consolidation Implementation

### 23.1 One Seller Workspace

`/os/leads` is the canonical seller workspace. Its local views are:

- **Lead Queue** for SLA-aware warm handoffs, qualification, follow-up, performance, standards,
  and Lead Manager Copilot work.
- **All Leads** for saved views, search, ownership, stage filters, manual creation, archive access,
  and seller preview.
- **Pipeline** for the same filtered seller set displayed as a board.
- **Underwriting** for the active valuation and offer-preparation queue.

Table/board choice, saved view, search, owner, stage, and selected seller are represented in URL
state so context survives display changes and links can be shared.

### 23.2 Seller Record

The seller record now has stable **Summary**, **Activity**, **Property**, **Valuation & Offer**,
**Appointments**, **Contract & Deal**, and **Files** sections. Activity combines communication,
appointment, consent, attribution, and material workflow history without deleting source evidence.
Old `overview`, `communications`, `history`, `underwriting`, and `deal` tab links are normalized to
their new sections.

### 23.3 Configuration Boundary

The active underwriting queue remains in Seller Leads. Provider scorecards, formula-governance
decisions, verified outcome history, and calibration metrics now live in **Settings > Data &
Quality**, where authorized managers configure and audit valuation quality.

### 23.4 Compatibility

- `/os/lead-manager?lead=...` redirects to `/os/leads?view=queue&lead=...`.
- `/os/pipeline?stage=...` redirects to `/os/leads?display=board&stage=...`.
- `/os/underwriting?lead=...` redirects to `/os/leads?view=underwriting&lead=...`.
- Existing `/os/leads/[leadId]` links remain valid.

## 24. IA6 Calendar And Appointment Execution Implementation

### 24.1 One Appointment Destination

`/os/calendar` is the canonical appointment workspace. Its permission-aware local views are:

- **Schedule** for month, week, day, and agenda calendars.
- **Dispatch** for qualified-seller scheduling, territory matching, closer capacity, and travel
  conflict review.
- **Appointment** for meeting preparation, walkthrough evidence, photos, seller presentation,
  negotiation, outcome, and approved in-person signing.
- **Availability** for authorized managers to configure closer hours, territories, capacity,
  travel buffers, and unavailable blocks.

Selecting a Calendar appointment opens Appointment mode in one action. Dispatching a new meeting
opens that appointment immediately.

### 24.2 iPad Appointment Mode

Direct appointment links enter focus mode automatically. The existing responsive appointment
workspace retains larger tablet controls, seller-safe presentation, camera capture, structured
walkthroughs, negotiation authority, and SignWell in-person signing. Seller presentation never
renders internal margins, ceilings, assignment economics, or staff-only notes.

### 24.3 URL And Compatibility Contract

Calendar preserves `view`, `appointment`, and `lead` context. The public local-view names are
`schedule`, `dispatch`, `appointment`, and `availability`. Existing
`/os/field-operations?view=...` links redirect to the equivalent Calendar URL while preserving the
selected appointment or lead.

### 24.4 Preserved Capabilities

No appointment, closer profile, availability block, brief, inspection, photo, negotiation,
underwriting transfer, signature envelope, or outcome model was duplicated. IA6 recomposes the
existing field workflow under Calendar and keeps the same permission and API boundaries.

## 25. IA7 Tasks, Approvals, And Primary Next Actions Implementation

### 25.1 One Work Center

`/os/tasks` now aggregates ordinary tasks, primary next actions, governed approvals, and
operational exceptions without copying their source records. Its permission-aware saved views are:

- **My Tasks**
- **Due Today**
- **Overdue**
- **Upcoming**
- **Unscheduled**
- **Team** for authorized managers
- **Approvals** for authorized decision-makers
- **Exceptions**
- **Completed**

Search, owner filtering, selected work, and source links operate inside the same work center.
`/os/approvals` remains a compatibility route and redirects to `/os/tasks?view=approvals`.

### 25.2 Primary Next-Action Contract

The Task record now distinguishes `primary_next_action`, `supporting`, `approval`, and
`operational_exception` work. It can retain lead and deal context, completion outcome and notes,
the completing user, and the successor task.

Every active seller lead or deal has one visible primary action with:

- one responsible owner
- one specific action
- one due date

Completing a primary action requires an outcome. If its seller lead or deal is still active, the
same operation must create the successor primary action. The API rejects completion without a
successor unless it verifies that the source record is terminal. New seller leads, qualified
handoffs, appointment-recovery paths, follow-ups, and newly opened deals all create or replace the
primary action through the shared task service.

### 25.3 Shared Truth

Home, Seller Leads, the seller record, and Tasks read the same primary action. Deal-linked primary
work supersedes the pre-contract seller action while retaining both record references. Supporting
tasks can still be completed directly and do not replace the primary action.

Approvals remain their existing governed records with their existing permission and audit checks.
Tasks only aggregates them for discovery. Requests that require source evidence send the reviewer
to the originating workspace before a decision is recorded.

### 25.4 Verification

- Alembic migration `0078_tasks_primary_actions.py` applied to local PostgreSQL.
- Existing active seller leads received a primary action during migration when one was missing.
- Task lifecycle, successor enforcement, lead-detail synchronization, and approval aggregation
  have API coverage.
- Adjacent lead, public intake, acquisition, field operations, transaction, and prospecting tests
  pass.
- TypeScript and ESLint pass.
- Mobile, iPad, and desktop checks show no document-level horizontal overflow.

## 26. IA8 Unified Deals Implementation

### 26.1 One Deal Index

`/os/deals` is now the canonical contract-to-funding workspace. It reads the existing Deal and
related domain records through a purpose-built aggregate API. Its saved views are **Active**,
**Closing Exceptions**, **Ready for Disposition**, **Buyer Needed**, **Finance Review**, and
**Completed**. Queue, table, and board displays operate on the same records and preserve view,
display, selected deal, and selected tab in the URL.

### 26.2 One Deal Record

The Deal record has **Summary**, **Contract**, **Closing**, **Documents**, **Parties**,
**Disposition**, **Finance**, and **Timeline** sections. Transaction and Disposition controls are
embedded in the canonical Deal record and use their existing APIs, permissions,
approval rules, documents, checklists, buyer matching, offers, and reconciliation controls rather
than reproducing them.

Contract, Closing, Disposition, and Finance remain independent statuses. The aggregate read model
also exposes domain-specific blockers, the shared primary next action, evidence counts, closing
deadline, buyer outcome, and stable related-record IDs.

### 26.3 Access And Compatibility

The Deal API requires `deals:view`. Assignment fee, company profit, and company margin are only
returned when the principal has financial or compensation visibility. Contract price remains an
operational term available to deal roles, matching the existing transaction workflow.

`/os/transactions` remains a compatibility route for specialist setup and bookmarks.
`/os/dispositions` remains the setup route for creating the first disposition case. Existing cases
are worked inside Deals. Final redirects are deferred until new-case setup has canonical parity.

### 26.4 Verification

- Unified overview and organization-scoped detail endpoints have API coverage.
- Existing transaction and disposition suites pass against the new router and embedded modes.
- Next.js production build passes with the canonical Deals workspace.
- Desktop and 390px mobile captures confirm the queue and record remain readable without
  document-level horizontal overflow.

## 27. IA9 Record Standards And Contextual Tools Implementation

Seller Lead, Deal, Buyer, and Campaign records now preserve selected record, local section, and
return context in the URL. Related-record links return staff to the originating list or record.
Buyer detail becomes a drawer on phone layouts, and specialist data loads only when its local view
is selected.

Transaction and Disposition Copilots remain review-gated inside the canonical Deal. The Help
bubble remains a separate global utility. Canonical pages no longer repeat acquisition, deal, or
management journey strips above their actual record controls.

## 28. IA10 Compatibility And Role Acceptance Implementation

The OS exposes only the approved 11 primary destinations, reduced by role and permission. Focused
queues are local views inside Prospecting, Seller Leads, Tasks, Calendar, Deals, and Settings.
My Setup remains permanently available from the signed-in role block.

Legacy links preserve context without advertising duplicate workspaces:

- transaction ID and selected transaction tab resolve to the matching Deal
- disposition case ID resolves to the matching Deal's Disposition section
- first-case disposition setup remains available for eligible executed transactions
- campaign, pipeline, underwriting, approval, team, policy, and AI links keep their earlier
  context-preserving redirects

The architecture contract verifies current routes, query parameters, static links, canonical
navigation, role visibility, default workspace, permission inventory, Help source ownership, and
retired navigation removal. Current manuals teach only the canonical employee workflow.
