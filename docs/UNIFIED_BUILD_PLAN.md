# Unified Build Plan

Last updated: July 21, 2026

## Objective

Build Stonegate Home Buyers as a premium, unified operating system for the full wholesaling
business:

- A high-converting public seller website.
- CRM and team workflows.
- SMS, Voice, email, appointments, and follow-up.
- Underwriting, comps, offer preparation, and reports.
- Contracts, transactions, buyers, and dispositions.
- Bookkeeping, compensation, marketing attribution, and executive reporting.
- Controlled AI agents that automate work without bypassing human authority.

The detailed delivered state is in `CURRENT_STATE.md`. Ordered execution is in `ROADMAP.md`.
The authoritative human, AI, workflow, and compensation policy is in `OPERATING_MODEL.md`.

## Product Surfaces

### Public Website

Audience: Georgia property owners considering a direct sale.

The public site must be fast, local, trustworthy, mobile-first, and focused on one primary action:
requesting a cash offer. It must never expose internal OS navigation or staff language.

Required capabilities:

- Clear service and seller-situation pages.
- Short property inquiry flow.
- Phone option.
- Separate communication consent.
- Privacy, terms, attribution, and conversion measurement.
- Campaign landing pages and controlled experiments.

### Internal Operating System

Audience: owner, acquisitions, disposition, VAs, transaction coordination, and approved service
identities.

The OS must be a quiet, efficient wholesaling command center rather than a generic CRM. Each role
should see the minimum data and actions required for its work.

Required modules:

- Dashboard and work queues.
- Leads, pipeline, tasks, and appointments.
- Shared inbox and communications.
- Underwriting and approvals.
- Contracts and transactions.
- Buyers and dispositions.
- Finance and compensation.
- Marketing intelligence.
- AI control center.
- User, role, integration, and compliance administration.

## Current Capability Map

| Area | Foundation | Production status |
| --- | --- | --- |
| Public conversion | Built and live | A2P wording deployed; custom domain pending |
| Clerk and RBAC | Built and live | MFA and access-revocation drill remain |
| Acquisition CRM | Broad foundation built | Team administration, calendar, merge, notifications, and sequences remain |
| Shared inbox | Built | Final SMS, Voice, and email provider activation pending |
| Underwriting V2.1 | Built | Real-deal validation, comp review controls, and offer approvals remain |
| Transactions | Manual workflow built | Live closing validation and e-signature adapter remain |
| Buyers/dispositions | Manual workflow built | Live simulation and provider campaign delivery remain |
| Finance | Deal reconciliation built | Payment lifecycle, accounting sync, and forecasting remain |
| Marketing | Foundation built | Provider delivery, retry, and paid-channel optimization remain |
| AI control | Foundation built | Evaluations, production runner, pilots, and measured automation remain |

## Product Principles

- PostgreSQL is the source of truth.
- Third-party providers are replaceable adapters.
- Every material action has an actor, timestamp, reason, and audit record.
- Consent and suppression are deterministic gates, not AI judgments.
- Human-confirmed facts outrank provider data and model output.
- Underwriting stores assumptions, evidence, adjustments, and versions.
- Provider callbacks are validated and idempotent.
- Secrets stay server-side and outside git.
- AI permissions are narrower than the human role sponsoring the run.
- Public and internal experiences remain visibly and structurally separate.

## Role Model

### Owner/CEO

Full operational visibility, management, approvals, finance, settings, and the ability to cover an
operational role with separately attributed role credit.

### Lead Manager

Warm response, qualification, nurture, appointment setting, and seller follow-up. The Lead Manager
does not own field closing.

### Acquisitions Closer

Seller appointments, property inspection, negotiation, underwriting review, approved offers, and
purchase contracts. The CEO initially fills this role.

### VA Prospecting

Assigned records and calling lists only. May qualify and schedule, then hand off. No access to
underwriting, buyers, contracts, accounting, exports, unrelated leads, recordings, or transcripts.

### Dispositions

Approved contracts, buyers, marketing packages, showings, offers, and buyer selection preparation.

### Transaction Coordinator

Executed contracts, closing-attorney intake, title, earnest money, due diligence, documents,
assignment, deadlines, and funded closing.

### AI Service

May read explicitly scoped context and create drafts or proposals. It cannot send, approve,
contract, pay, change permissions, or bypass compliance without an approved pilot and narrow tool.

## Build Versus Integrate

Build and own:

- Seller website and forms.
- CRM, pipeline, tasks, appointments, and team workflow.
- Consent, attribution, suppression, audit, and approvals.
- Underwriting, offer policy, transaction, buyer, and finance records.
- Marketing intelligence and AI governance.

Integrate:

- Clerk for authentication.
- Render for hosting.
- Twilio for SMS and Voice.
- Google Workspace for operational email and calendar.
- Smartlead or a comparable dedicated platform for future cold email.
- RentCast now, with ATTOM or MLS/RESO as optional property-data enrichment.
- OpenAI for model and transcription calls.
- An e-signature provider.
- S3-compatible object storage.
- QuickBooks Online or controlled accounting export.
- Google Ads and Meta conversion APIs.
- Error monitoring and uptime monitoring.

## Underwriting Standard

The comp engine must:

- Prefer recorded sales over asking-price evidence.
- Compare property type, location, size, age, condition, recency, and liquidity.
- Exclude or down-weight materially different properties with visible reasons.
- Produce a range and confidence, not false precision.
- Keep human-selected comps and manual assumptions versioned.
- Calculate offer scenarios from ARV, repairs, transaction costs, disposition strategy, assignment
  fee, and policy percentages.
- Produce a seller-safe client report and a detailed internal investor report.

The system supports judgment. It is not an appraisal and cannot make a binding offer.

## AI Autonomy Ladder

1. Observe: summarize and identify missing information.
2. Draft: prepare notes, messages, questions, and tasks for approval.
3. Recommend: propose structured CRM updates with evidence.
4. Execute low-risk internal actions after approval.
5. Execute narrow external actions only after evaluation, monitoring, rollback, and explicit owner
   authorization.

Offers, contracts, buyer selection, payments, compensation, permissions, and legal or financial
decisions remain human-controlled.

## Quality Bar

Public website:

- Fast initial load and stable layout.
- Mobile-first forms with no hidden consent.
- Clear brand, local relevance, and one primary CTA.
- No broken links, internal navigation, or placeholder content.
- Measured conversion changes.

Operating system:

- Real routed pages with purposeful content.
- Dense but readable information.
- Predictable assignment, task, inbox, and approval behavior.
- Responsive workflows without overlapping or clipped controls.
- Complete loading, empty, error, retry, permission, and audit states.

Backend:

- Migrations, tests, authorization, validation, idempotency, structured logs, and provider retry
  behavior proportional to risk.

## Metrics

Public funnel:

- Visitors, form starts, completions, call clicks, completion rate, duplicate rate, CPL,
  lead-to-appointment rate.

Acquisition:

- Median speed-to-lead, contact rate, attempts per lead, appointment rate, offer rate, contract
  rate, follow-up SLA.

Transactions and dispositions:

- Days to contract, days to close, assignment spread, buyer response rate, buyer fallout rate.

Finance and marketing:

- Collected revenue, net deal revenue, compensation, ad spend percentage, source profitability,
  cost per contract, ROAS.

AI:

- Draft acceptance, field agreement, evidence coverage, reviewer rejection, failure rate, latency,
  cost, guardrail blocks, and estimated time saved.

## Execution

Work proceeds in the order defined in `ROADMAP.md`. A later phase may be researched in advance, but
it must not create a production dependency that bypasses an earlier phase's controls.
