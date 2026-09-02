# ADR 0003: Task-Centered Operating System Information Architecture

## Status

Accepted; amended September 1, 2026

## Context

The Stonegate Operating System currently exposes 22 owner sidebar links. Several links are separate
pages over the same business records:

- Lead Desk, All Leads, Seller Pipeline, and Underwriting all organize seller leads.
- Transactions and Dispositions both organize active deals.
- Campaigns and Prospecting both organize outbound prospecting.
- Field Operations is appointment execution that begins from Calendar.
- Team & Access, Email Management, Company & Policy, and AI Control are administrative settings.

This makes features discoverable in isolation, but it also forces employees to decide which page
owns a record or task. The navigation reflects the order in which features were built more than the
way Stonegate employees work.

## Decision

Adopt the task-centered information architecture in
`docs/CRM_INFORMATION_ARCHITECTURE_ROADMAP.md`.

The owner navigation contains 12 destinations:

1. Home
2. Inbox
3. Tasks
4. Calendar
5. Prospecting
6. Leads
7. Dispositions
8. Deals
9. Buyers
10. Finance
11. Marketing
12. Settings

The system will preserve separate canonical records for prospects, seller leads, deals, buyers,
campaigns, conversations, tasks, transactions, disposition cases, contracts, and accounting. The
decision consolidates employee navigation and page composition; it does not collapse database
entities or weaken permissions.

The destination was renamed from **Seller Leads** to **Leads** on August 8, 2026. The route and
underlying seller-lead record type did not change.

The decision was amended on September 1, 2026 to make **Dispositions** a first-class, role-focused
navigation destination. It is a query-backed desk over the same canonical Deal, Disposition Case,
Buyer, and Transaction records; it is not a second deal database. The dedicated entry is warranted
because buyer placement is a distinct daily job with its own queues and high-frequency tools, while
the Deal record remains the shared source of truth for acquisition, closing, and finance.

Current routes and query parameters remain compatible until their target workspace has feature
parity, role tests pass, Help content is current, and production smoke tests succeed. Restricted
roles continue to receive a smaller, permission-filtered navigation. My Setup remains directly
addressable for onboarding, and the Design System remains development-only.

## Consequences

Benefits:

- Employees choose the business object or job they are working on instead of choosing among
  overlapping feature pages.
- Prospecting, seller acquisition, buyer placement, and deal execution each have one predictable home.
- Administrative configuration has one Settings entry point.
- Existing data models, API authority, audit history, and deep links remain intact.
- A machine-readable route and role contract can detect accidental omissions during migration.

Tradeoffs:

- Compatibility routes must be maintained while workspaces are consolidated.
- Large workspaces require independent loaders and stable local navigation to avoid becoming
  monolithic pages.
- User manuals and Help retrieval sources must be updated in the same phase as each visible move.
- Navigation visibility tests do not replace direct API permission tests.

## Guardrails

- Do not redirect an existing route before feature parity is documented.
- Do not broaden access because two pages move into one workspace.
- Do not merge prospects, seller leads, buyers, or deals in the database.
- Do not hide a current control unless its replacement location is documented and tested.
- Do not make AI a primary workspace; Copilots remain contextual and AI governance belongs in
  Settings.
- Use `npm --prefix apps/web run audit:ia` as the architecture contract check.
- Use `npm --prefix apps/web run baseline:ia` before and after visible migration phases.
