# Product Requirements

Last updated: July 23, 2026

## Product

Stonegate Home Buyers is a unified website and operating system for a Georgia real-estate
wholesaling company. It connects seller acquisition, team communication, underwriting, offers,
contracts, transactions, buyers, dispositions, finance, marketing attribution, and controlled AI
automation.

## Users

- Motivated property seller.
- Owner/CEO.
- Lead Manager.
- Acquisitions Closer.
- Restricted VA prospecting caller.
- Disposition specialist.
- Transaction coordinator.
- Approved AI and provider service identities.

## Core Outcomes

1. Convert a public visitor into a consented, attributed seller lead.
2. Contact and qualify that lead quickly without losing history.
3. Hand a qualified lead from a VA to acquisitions without copying or moving records between
   accounts, with the Lead Manager owning qualification and the Acquisitions Closer owning the
   seller contract.
4. Prepare an explainable comp analysis, ARV range, repair range, and offer scenarios.
5. Require human approval for price, contract, buyer, financial, and sensitive communication
   decisions.
6. Coordinate contract, title, buyer, closing, revenue, compensation, and marketing attribution.
7. Use AI to reduce repetitive work while preserving evidence, permissions, and review.

## Functional Requirements

### Public

- Public pages must remain separate from the internal OS.
- Seller forms must capture property context, attribution, contact permission, and optional SMS
  consent.
- Consent evidence must retain wording, version, source, timestamp, IP, and user agent.
- Duplicate submissions must preserve new evidence while avoiding duplicate active leads.

### CRM

- Every lead links seller, property, tasks, appointments, communications, underwriting,
  transaction, buyer, source, activity, and audit history.
- Assignment changes ownership without losing history.
- Restricted roles can access only assigned records and permitted actions.

### Communications

- SMS, email, calls, recordings, transcripts, and notes share one chronological conversation.
- Provider events are signed, idempotent, and retained.
- Outbound communication requires permission, valid destination, consent, suppression, contact
  rules, and configured provider.
- STOP revokes SMS eligibility across the organization.

### Underwriting

- Comparable selection and exclusion must be explainable.
- ARV and offer outputs must be ranges with versioned assumptions.
- Reports must support internal review and seller-facing discussion.
- Unconfirmed renovation status may reduce confidence but must not hide results or reports.

### AI

- Every model run records model, prompt, tools, evidence, status, cost, and review outcome.
- AI capabilities use the Stonegate orchestrator, narrow server-side tools, versioned schemas,
  deterministic policy gates, and capability-specific evaluation datasets.
- PostgreSQL and human-confirmed facts remain authoritative; model state is not a second CRM.
- Autonomy is promoted per capability and tool after offline evaluation, a draft-only pilot,
  monitored outcomes, rollback controls, and explicit owner approval.
- AI cannot independently make offers, send contracts, select buyers, change payments, administer
  users, override compliance, or provide legal or financial advice.

## Non-Functional Requirements

- Organization-scoped authorization.
- UTC timestamps and integer-cent money.
- Append-only audit history for material actions.
- Secure secret storage and private provider media.
- Responsive public and OS interfaces.
- Idempotent webhooks and outbound dispatch.
- Observable workers and recoverable provider failures.
- Backups and tested restoration before broad production use.

## Current Release State

The broad product foundation and branded web domain are implemented and deployed. Final dedicated
SMS, Voice, and Google Workspace activation is pending external/provider setup. See
`CURRENT_STATE.md`.

## Launch Gates

- Dedicated A2P Campaign and Stonegate SMS sender approved.
- SMS, Voice, email, Clerk, and CORS acceptance tests pass for every activated provider origin.
- Recording remains disabled until disclosure policy is approved.
- Backups, alerts, access revocation, and smoke tests are verified.
- Underwriting is compared against real deals before it is treated as dependable offer support.
- AI external autonomy remains disabled until an evaluation-backed pilot is approved.

## Success Measures

- Seller form completion.
- Median speed-to-lead.
- Contact, appointment, offer, and contract conversion.
- Follow-up SLA.
- Underwriting review accuracy and correction rate.
- Days from contract to disposition and close.
- Net revenue and source profitability.
- AI acceptance, correction, failure, cost, and time saved.

## Resolved Decisions

- Business-facing brand: Stonegate Home Buyers.
- Repository: `TailoredAgents/Wholesale`.
- Hosting: Render.
- Authentication: Clerk with local RBAC.
- Database: PostgreSQL.
- AI provider: OpenAI.
- Current property data: RentCast.
- SMS and Voice: Twilio, with a dedicated Stonegate Messaging Service and SMS number.
- Operational email: Google Workspace.
- Cold email, if approved later: separate outreach infrastructure rather than operational Gmail.

## Open Decisions

- Google Workspace mailbox names.
- Recording disclosure and state coverage.
- Object storage provider.
- E-signature provider.
- Accounting integration.
- Error monitoring provider.
- Secondary property-data provider.
- Production AI pilot order and capability-specific thresholds after the first redacted datasets.
