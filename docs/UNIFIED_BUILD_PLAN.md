# Unified Build Plan

## Objective

Build Oakwell Home Buyers as one operating system with two clean surfaces:

- Public website: converts motivated sellers into consented leads.
- Internal OS: runs acquisition, follow-up, underwriting, transactions, buyers, bookkeeping,
  reporting, and controlled AI automation.

PostgreSQL remains the source of truth. Third-party tools are adapters, not the business brain.

## Research Summary

### Public Site Conversion

The highest-converting seller experience should be simple, local, fast, and focused on one action:
requesting a cash offer.

Patterns to build:

- One primary CTA across public pages: `Get my cash offer`.
- No staff links, OS links, or internal language on public pages.
- Above-the-fold value proposition that names the seller outcome clearly.
- Mobile-first form with minimal required fields and value-driven button copy.
- Phone CTA for sellers who prefer to call.
- Trust signals near the form: local service area, process, proof, consent language, and privacy.
- Situation-specific pages for high-intent sellers:
  - inherited house,
  - house needs repairs,
  - tired landlord,
  - vacant property,
  - behind on payments,
  - relocation,
  - code violations,
  - divorce or life transition, without legal advice.
- Campaign-specific landing pages for PPC and direct mail.
- Conversion analytics for every form view, form start, submit, call click, duplicate match, and
  booked appointment.
- A/B testing backlog for headline, CTA text, form length, trust proof, and page layout.

Research basis:

- Carrot's motivated-seller testing emphasizes a simplified goal, focused content, and short forms;
  it reported a 38.54% lead lift for a tested real-estate investor page pattern.
- Unbounce's CRO guidance emphasizes testing one variable at a time, starting with headlines, CTAs,
  hero images, and forms.
- Opendoor's lead-source guidance emphasizes clear CTAs, conversion tracking, retargeting pixels,
  and local landing pages.

## OS Product Direction

The OS should not be a generic CRM. It should be a wholesaling command center.

Benchmark features from existing systems:

- REsimpli: all-in-one investor CRM, AI seller conversations, follow-up, appointment booking, lead
  movement, drip campaigns, list stacking, skip tracing, driving for dollars, KPI tracking.
- CarrotCRM / InvestorFuse: investor-focused CRM with workflow orientation and lead management
  inside the real estate investor website ecosystem.
- Podio: flexible workspace, custom workflows, automation, collaboration, and visibility.
- Lead Sherpa: specialist SMS, skip tracing, list stacking, and compliance-focused outreach.

Oakwell recommendation:

- Build our own source-of-truth OS for CRM, pipeline, underwriting, transaction, buyers, finance,
  audit, and reporting.
- Buy or integrate specialist infrastructure where speed, compliance, or data quality matter:
  phone/SMS, email, calendar, maps/geocoding, property data, skip tracing, e-signature, bookkeeping
  export, object storage, analytics, and AI model calls.
- Do not make a third-party CRM the operational source of truth.
- Keep every integration behind an adapter with external IDs, raw payload storage, retries,
  idempotency keys, and audit events.

## Operating System Modules

### 1. Public Website And Lead Capture

Scope:

- Public homepage.
- Cash offer form.
- Seller situation pages.
- PPC/direct-mail landing pages.
- Consent and attribution capture.
- Analytics and conversion events.
- Form abandonment events.
- Duplicate detection and evidence preservation.

Next build target:

- Replace placeholder public copy with conversion-focused Oakwell pages and a tighter form flow.
- Add conversion event tracking to the database before paid traffic.

### 2. Acquisition CRM

Scope:

- Lead inbox.
- Daily acquisition workspace.
- Speed-to-lead queue.
- Lead assignment.
- Saved views and filters.
- Follow-up tasks and next action.
- Contact/property timeline.
- Notes, calls, texts, emails, appointments.
- Duplicate review and merge workflow.

Next build target:

- Turn `/os` from a dashboard into an acquisition workspace with a real lead queue, task queue,
  saved filters, assignment, and next-action controls.

### 3. Communications

Scope:

- Twilio or similar phone/SMS adapter.
- Email adapter.
- Call logging.
- Inbound webhook validation.
- Outbound compliance gate.
- Suppression and opt-out enforcement.
- Communication timeline.
- Templates and follow-up sequences.

Next build target:

- Add communication records and provider adapter interfaces before sending real messages.

### 4. Underwriting

Scope:

- Underwriting versions.
- Property facts.
- Provider data import.
- Comparable sale candidates.
- Human comp review.
- ARV range.
- Repair estimate.
- Offer scenarios.
- Manager approval for offer ceiling.

Next build target:

- Build underwriting version records and manual ARV/repair/offer controls before automating comps.

### 5. Contracts And Transaction Coordination

Scope:

- Contract templates.
- Approval requests.
- E-signature adapter.
- Transaction checklist.
- Closing attorney/title status.
- Deadline tracking.
- Document storage.

Next build target:

- Create transaction/checklist records after offer approval, before e-signature automation.

### 6. Buyers And Dispositions

Scope:

- Buyer CRM.
- Buyer criteria.
- Proof-of-funds records.
- Buyer tags and markets.
- Deal room.
- Offer collection.
- Buyer selection approval.
- Disposition campaign performance.

Next build target:

- Build buyer records and criteria before blast/campaign automation.

### 7. Bookkeeping, Revenue, And Compensation

Scope:

- Revenue records.
- Assignment fee or closing income.
- Direct deal deductions.
- Advertising spend.
- Effective-dated compensation rules.
- Acquisition/disposition/founder/company split.
- Monthly P&L-style reporting.
- Export to accounting system.

Next build target:

- Build finance tables and manual revenue entry before QuickBooks/Xero integration.

### 8. Marketing Intelligence

Scope:

- Source/campaign/click attribution.
- Google Ads conversion uploads.
- Meta conversion API.
- Direct mail campaign attribution.
- Lead quality reporting.
- Cost-per-lead and cost-per-contract reporting.
- Revenue by source.

Next build target:

- Add conversion events and attribution reporting before paid scaling.

### 9. AI Control Center

Scope:

- Agent definitions.
- Prompt versions.
- Tool permissions.
- Run logs and traces.
- Human approval queue.
- Evaluation datasets.
- Cost and latency tracking.
- Safety/compliance guardrails.

Next build target:

- Build AI run logging and approval queue before agents can take external actions.

## AI Agent Roadmap

Use agents where they reduce repetitive work, not where they make binding business decisions.

Initial agents:

- Intake summarizer: turns form/call notes into a structured seller brief.
- Speed-to-lead monitor: watches new leads and escalates overdue contact tasks.
- Follow-up drafter: drafts SMS/email/call scripts for human approval.
- Acquisition copilot: identifies missing fields and suggests next questions.
- Underwriting assistant: drafts comp notes and flags inconsistent property facts.
- Disposition copy assistant: drafts buyer-facing deal summaries after approval.
- Finance checker: flags missing revenue, deductions, or compensation inputs.
- Compliance monitor: checks consent, suppression, outbound eligibility, and missing approvals.

Hard boundaries:

- AI cannot make binding offers.
- AI cannot send contracts.
- AI cannot bypass consent/suppression.
- AI cannot give legal, tax, probate, foreclosure, bankruptcy, title, or closing advice.
- AI cannot change payments, compensation rules, roles, permissions, or secrets.
- Human approvals are required for offers, contracts, buyer selection, seller-facing sensitive
  messaging, and financial entries.

Implementation direction:

- Use OpenAI's agent/tooling stack for agent workflows after the OS has explicit tool APIs,
  permissions, logs, and approvals.
- Start with one narrow summarization/routing agent.
- Add tool-using agents only after every tool writes audit events and supports dry-run mode.

## Build-Versus-Buy Decisions

Build now:

- Public seller website and forms.
- Lead/contact/property CRM.
- Consent, attribution, duplicate detection, and audit.
- Acquisition workspace.
- Underwriting workflow.
- Transaction workflow.
- Buyer CRM.
- Revenue and compensation logic.
- AI approval/logging layer.

Integrate instead of building from scratch:

- Clerk for auth.
- Render for hosting.
- Twilio or equivalent for phone/SMS.
- Email provider for outbound email.
- Google/Meta conversion APIs.
- Address validation and geocoding.
- Property data/comps provider.
- Skip tracing provider.
- E-signature provider.
- Object storage.
- Accounting export provider.
- OpenAI for AI agents.
- Error monitoring.

Defer:

- Custom dialer.
- Custom SMS carrier/compliance stack.
- Custom e-signature.
- Custom accounting ledger replacement.
- Fully autonomous seller conversations.

## Next 90-Day Execution Plan

### Phase A: Staging Stabilization And Public Conversion Foundation

Goal:

Make staging useful, separate public and internal experiences, and collect reliable conversion data.

Deliver:

- Confirm Render services and Clerk login.
- Bootstrap staging owner.
- Replace placeholder homepage with conversion-focused public site.
- Improve cash offer form UX and reduce friction.
- Add seller situation pages.
- Add analytics/conversion event tables.
- Add form abandonment and call-click tracking.
- Add basic source/campaign reporting in `/os`.

Acceptance:

- `/` and `/get-a-cash-offer` are public.
- `/os` and `/leads` require login.
- Form submissions create leads and conversion events.
- Owner can see leads, source, consent, and speed-to-lead queue.

### Phase B: Acquisition Workspace

Goal:

Make `/os` the daily workspace for seller lead handling.

Deliver:

- Lead inbox with saved filters.
- Task queue with SLA status.
- Lead assignment.
- Lead notes.
- Follow-up plans.
- Appointment records.
- Duplicate review queue.
- Activity timeline improvements.

Acceptance:

- A user can work a lead from new to contacted/underwriting without leaving the OS.
- Every material action writes audit/activity records.

### Phase C: Communications Foundation

Goal:

Prepare compliant real seller communication.

Deliver:

- Communication tables.
- Provider adapter interface.
- Twilio/SMS prototype in test mode.
- Email prototype in test mode.
- Suppression and opt-out enforcement.
- Template library.
- Manual send with approval/check gate.

Acceptance:

- No message can send without consent and suppression checks.
- All inbound/outbound events are stored.

### Phase D: AI Agent Foundation

Goal:

Add useful AI without unsafe autonomy.

Deliver:

- Agent run records.
- Prompt version records.
- Tool permission registry.
- Approval queue.
- Intake summary agent.
- Follow-up draft agent.
- Compliance monitor draft checks.

Acceptance:

- Agents can summarize and draft.
- Agents cannot externally send, approve offers, or change financial/legal records.

### Phase E: Underwriting And Offer Workflow

Goal:

Move from lead management to deal decision support.

Deliver:

- Underwriting versions.
- Property facts.
- Manual comps.
- ARV range.
- Repair estimate.
- Offer scenarios.
- Offer approval queue.

Acceptance:

- A human can approve an offer ceiling based on stored assumptions and comps.

## Metrics To Track

Public site:

- Unique visitors.
- Form starts.
- Form completions.
- Call clicks.
- Completion rate.
- Duplicate rate.
- Cost per lead by source.
- Lead-to-appointment rate.

Acquisition:

- Median speed-to-lead.
- Percent contacted under 5 minutes.
- Contact attempts per lead.
- Contact rate.
- Appointment set rate.
- Offer made rate.
- Contract rate.

Finance:

- Revenue by source.
- Ad spend as percent of collected revenue.
- Net revenue after deal deductions.
- Compensation by role.
- Cost per contract.

AI:

- Draft acceptance rate.
- Human edit distance.
- Time saved estimate.
- Cost per agent run.
- Guardrail blocks.
- Approval queue latency.

## Research References

- Carrot motivated seller landing page test:
  https://carrot.com/blog/real-estate-lead-generation-landing-page/
- Unbounce CRO best practices:
  https://unbounce.com/conversion-rate-optimization/cro-best-practices/
- Opendoor real estate lead source and conversion guidance:
  https://www.opendoor.com/articles/proven-real-estate-lead-sources-that-convert
- Harvard Business Review lead response research:
  https://hbr.org/2011/03/the-short-life-of-online-sales-leads
- REsimpli benchmark:
  https://resimpli.com/
- InvestorFuse / CarrotCRM benchmark:
  https://www.investorfuse.com/
- Podio benchmark:
  https://www.podio.com/
- Lead Sherpa benchmark:
  https://leadsherpa.com/
- OpenAI Agents SDK:
  https://developers.openai.com/api/docs/guides/agents
- OpenAI tools guide:
  https://developers.openai.com/api/docs/guides/tools
