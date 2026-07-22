# UX1 Information Architecture Audit

Last updated: July 22, 2026

Status: Complete. Owner approved the five Phase UX1 decisions on July 22, 2026.

This document is the Phase UX1 decision record for the Stonegate Operating System. It inventories
the current routes, assigns each route a distinct job and audience, defines the proposed navigation,
and identifies the authorization and responsive-shell work required before visual restyling begins.

## Audit Method

The audit covered:

- All 22 current OS routes, including contextual and utility routes.
- Current navigation labels, page headings, route content, and API permission gates.
- Role definitions in the API RBAC policy.
- Desktop screenshots at 1440 pixels and mobile screenshots at 390 pixels for every route.
- Duplicate responsibilities, hidden utilities, inconsistent names, dead ends, and role-access gaps.

All audited routes returned a page and none produced document-level horizontal overflow. The
baseline screenshots were generated locally and intentionally remain untracked because the local
Clerk configuration overlay and mock authentication state are not production evidence.

## Approved Navigation Proposal

Current URLs remain unchanged. Phase UX3 will change labels, grouping, visibility, and shell
behavior without breaking bookmarks or deep links.

| Group | Route | Current label or heading | Target label | Primary job |
| --- | --- | --- | --- | --- |
| Command | `/os` | Dashboard / Acquisition command center | Dashboard | Show the signed-in role's priorities, exceptions, and performance |
| Command | `/os/inbox` | Shared inbox | Inbox | Work seller conversations and communication follow-up |
| Command | `/os/tasks` | Open acquisition tasks | Work Queue | Work assigned actions across records and teams |
| Command | `/os/calendar` | Calendar | Calendar | Manage appointments and time-based commitments |
| Acquisitions | `/os/operations` | Acquisition Ops / Team execution | Operations | Manage acquisition capacity, assignments, and execution |
| Acquisitions | `/os/campaigns` | Campaigns / Outreach control center | Campaigns | Configure and monitor outreach campaigns and lists |
| Acquisitions | `/os/prospecting` | Prospecting / Seller outreach workbench | Prospecting | Execute assigned calls, dispositions, qualification, and handoff |
| Acquisitions | `/os/lead-manager` | Acquisitions Desk | Lead Desk | Work today's warm leads, qualification, and follow-up |
| Acquisitions | `/os/leads` | Leads / Seller lead database | All Leads | Search, filter, review, and administer the complete seller database |
| Acquisitions | `/os/pipeline` | Pipeline / Seller acquisition board | Seller Pipeline | Move seller opportunities through acquisition stages |
| Acquisitions | `/os/field-operations` | Field Ops / Field dispatch | Field Operations | Prepare, dispatch, and document in-person appointments |
| Deal Flow | `/os/underwriting` | Offer preparation and accuracy | Underwriting | Analyze value, repairs, risk, and offer recommendations |
| Deal Flow | `/os/approvals` | Human approval queue | Approvals | Review governed decisions that require a person |
| Deal Flow | `/os/transactions` | Transaction Coordination | Transactions | Move signed seller contracts from execution to closing |
| Deal Flow | `/os/dispositions` | Dispositions | Dispositions | Market assignable deals, manage buyer offers, and secure an exit |
| Deal Flow | `/os/buyers` | Buyer CRM / Disposition workspace | Buyers | Maintain buyer records, criteria, activity, and relationships |
| Business | `/os/finance` | Revenue and compensation | Finance | Reconcile revenue, expenses, commissions, and profitability |
| Business | `/os/marketing` | Campaign intelligence | Marketing | Measure source, campaign, funnel, and acquisition economics |
| Control | `/os/operating-model` | Business Setup / Operating model controls | Operating Model | Govern roles, commission rules, stages, and business policy |
| Control | `/os/ai` | Agent governance | AI Control | Govern AI agents, pilots, approvals, cost, and auditability |
| Contextual | `/os/leads/[leadId]` | Lead record | Lead Record | Provide the complete working record for one seller opportunity |
| Utility | `/os/leads/archived` | Archived leads | Archived Leads | Find and restore archived records from All Leads |

Archived Leads remains a child action of All Leads and does not become primary navigation. Lead
Record remains contextual and is reached from a queue, search result, pipeline card, appointment,
or conversation.

## Distinct Workspace Definitions

These related pages must remain separate because they support different operating modes:

- **Lead Desk:** a focused queue for today's warm leads, qualification, and seller follow-up.
- **All Leads:** the searchable system of record for every seller lead, including administrative
  and recovery work.
- **Seller Pipeline:** a stage-based board for opportunity movement, bottlenecks, and ownership.
- **Work Queue:** assigned actions spanning leads, communications, appointments, approvals, and
  deals.
- **Calendar:** scheduled commitments organized by time rather than record stage.
- **Field Operations:** appointment preparation, dispatch, property evidence, and visit outcomes.
- **Campaigns:** campaign and list administration, routing, pacing, and management.
- **Prospecting:** the caller's execution workspace for assigned outreach.
- **Marketing:** source and campaign measurement, funnel performance, and acquisition economics.
- **Transactions:** seller contract-to-close coordination.
- **Dispositions:** buyer placement and contract-exit execution.
- **Buyers:** the buyer relationship database and criteria system.

## Role Navigation Matrix

`Primary` means part of the role's normal navigation. `Support` means visible when needed but not a
default landing destination. `Context` means reached from an assigned record or handoff. A blank
cell means hidden from normal navigation even if an unusually broad permission could technically
allow the route.

| Destination | Owner | Lead Manager | Closer | VA Caller | Dispositions | Transaction Coordinator |
| --- | --- | --- | --- | --- | --- | --- |
| Dashboard | Primary | Primary | Primary |  | Primary | Primary |
| Inbox | Primary | Primary | Primary |  |  |  |
| Work Queue | Primary | Primary | Primary |  | Primary | Primary |
| Calendar | Primary | Primary | Primary |  |  | Support |
| Operations | Primary | Primary |  |  |  |  |
| Campaigns | Primary | Support |  |  |  |  |
| Prospecting | Support | Support |  | Primary |  |  |
| Lead Desk | Support | Primary | Support |  |  |  |
| All Leads | Primary | Primary | Support |  |  |  |
| Seller Pipeline | Primary | Primary | Support |  |  |  |
| Field Operations | Support | Support | Primary |  |  |  |
| Underwriting | Primary | Support | Primary |  |  |  |
| Approvals | Primary | Support | Context |  | Support | Support |
| Transactions | Primary | Support | Support |  | Support | Primary |
| Dispositions | Primary |  |  |  | Primary | Support |
| Buyers | Primary |  |  |  | Primary |  |
| Finance | Primary |  |  |  |  |  |
| Marketing | Primary |  |  |  |  |  |
| Operating Model | Primary |  |  |  |  |  |
| AI Control | Primary |  |  |  |  |  |

Role notes:

- The VA Caller lands on Prospecting and works only assigned records. Qualification and appointment
  handoff remove normal edit access to the lead.
- Dispositions and Transaction Coordination need role-specific dashboard and Work Queue summaries;
  the current dashboard and task APIs are acquisition-permission dependent.
- A future Marketing Manager workspace should expose Marketing and appropriate campaign reporting.
- A Finance/Accounting role should expose Finance without requiring unrelated lead access.
- Navigation visibility must require both API authorization and job relevance. Permissions alone
  are too broad to produce a focused workspace.
- Owner access remains comprehensive, but the owner can collapse Business and Control groups to
  keep daily work prominent.

## Handoff Map

| Stage | Primary workspace | Responsible role | Required handoff output |
| --- | --- | --- | --- |
| Campaign preparation | Campaigns | Owner or Lead Manager | Approved list, campaign, caller assignment, and consent/suppression state |
| Cold outreach | Prospecting | VA Caller | Disposition, qualification evidence, communication history, and next action |
| Warm-lead qualification | Lead Desk and Inbox | Lead Manager | Confirmed motivation, condition, timeline, decision makers, and appointment readiness |
| Appointment preparation and visit | Calendar and Field Operations | Closer | Visit plan, property evidence, seller concerns, and appointment outcome |
| Valuation and offer | Underwriting and Approvals | Closer with Owner oversight | Supported ARV, repair assumptions, offer range, risks, and approved decision |
| Seller contract to close | Transactions | Transaction Coordinator | Executed documents, title/closing milestones, blockers, and expected close |
| Buyer placement | Dispositions and Buyers | Dispositions | Buyer outreach, proof of funds, offers, selected exit, and assignment status |
| Reconciliation | Finance and Marketing | Owner or Finance | Closed revenue, commissions, expenses, source attribution, and campaign economics |

Every handoff retains the original record, ownership history, communications, evidence, approvals,
and audit trail. Records change responsibility; they are not copied between user accounts.

## Findings And Implementation Register

| ID | Severity | Finding | Required correction | Planned phase |
| --- | --- | --- | --- | --- |
| UX1-01 | High | The static sidebar exposes every primary destination to every signed-in role. | Render role-relevant groups and items while preserving API authorization. | UX3 |
| UX1-02 | High | Dashboard APIs require lead-view permission, preventing useful role homes for downstream teams. | Add permission-aware dashboard summaries for Dispositions, Transactions, and Finance roles. | UX4 |
| UX1-03 | High | Work Queue APIs depend on lead-view permission, preventing one shared action system for downstream roles. | Authorize task access by assignment and task domain, then provide role-scoped filters. | UX4 |
| UX1-04 | High | Marketing APIs require financial-view permission while the Marketing Manager role lacks that permission. | Introduce the narrow reporting permission or revise the endpoint gate and tests. | UX6 |
| UX1-05 | High | Mobile navigation is a clipped horizontal strip and account controls dominate the first viewport. | Replace it with a responsive navigation drawer and compact account menu. | UX3 |
| UX1-06 | Medium | The Command group currently contains 11 destinations and mixes daily work with acquisition administration. | Adopt the five proposed navigation groups. | UX3 |
| UX1-07 | Medium | Dashboard repeats a substantial seller pipeline and lead database already available in dedicated workspaces. | Keep dashboard content exception-focused and link to full workspaces. | UX4 |
| UX1-08 | Medium | Buyer CRM uses the heading `Disposition workspace` and includes deal-room work that overlaps Dispositions. | Rename the heading to Buyers and focus the page on buyer records, criteria, and relationships. | UX7 |
| UX1-09 | Medium | Navigation labels and page headings frequently differ. | Apply the target labels consistently to navigation, titles, breadcrumbs, and metadata. | UX3-UX8 |
| UX1-10 | Medium | Finance, Buyers, Operating Model, AI Control, and Lead Record are very long on mobile. | Move secondary workflows into tabs, drawers, or contextual details using shared page contracts. | UX7-UX9 |
| UX1-11 | Medium | Approvals presents multiple approval concepts without one clear filtered queue model. | Consolidate governed decisions into a shared queue with decision-type filters. | UX7 |
| UX1-12 | Low | Archived Leads is reachable but not explained as a child utility. | Add a clear archive action and return path within All Leads. | UX5 |

## Phase Decision

The audit recommends approval of the following decisions:

1. Use Command, Acquisitions, Deal Flow, Business, and Control as the primary navigation groups.
2. Use the target route labels in the inventory table while retaining every current URL.
3. Use the role navigation matrix as the shell visibility contract.
4. Make Prospecting the VA Caller landing workspace.
5. Redesign Dashboard and Work Queue authorization so downstream roles receive relevant work
   without receiving unrelated seller access.

The owner approved all five decisions on July 22, 2026. The route inventory, labels, role matrix,
VA landing workspace, and downstream authorization direction are now the product contract for
Phases UX2 through UX8.
