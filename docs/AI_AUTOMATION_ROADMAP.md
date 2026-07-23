# AI Copilot Build Roadmap

Last updated: July 22, 2026

This is the definitive build plan for completing Stonegate's AI system from its current state.
The product model is:

- Human employees own roles, relationships, and decisions.
- Each role receives one staff-facing copilot.
- Shared specialist engines perform bounded technical work behind the copilots.
- External automation is introduced only after the corresponding copilot has passed evaluation and
  a supervised production pilot.

This roadmap does not replace the main product roadmap. Provider setup may proceed in parallel,
but no phase may bypass deterministic policy, permission, evaluation, approval, or rollback gates.

## End Product

Staff-facing copilots:

| Copilot | Human owner | Primary assistance |
| --- | --- | --- |
| Prospecting Copilot | VA caller and prospecting manager | Record priority, scripts, call preparation, dispositions, callbacks, handoff, and coaching |
| Lead Manager Copilot | Lead Manager | Daily queue, inquiry summary, qualification gaps, follow-up drafts, appointments, and neglected-lead protection |
| Acquisitions Copilot | Acquisitions Closer and covering CEO | Call brief, appointment preparation, property evidence, underwriting explanation, negotiation preparation, and follow-up |
| Transaction Copilot | Transaction Coordinator | Documents, parties, deadlines, checklist gaps, closing drafts, and risk escalation |
| Disposition Copilot | Disposition specialist | Buyer matching, package preparation, approved outreach, response comparison, showing, deposit, and backup coverage |
| Finance Copilot | Owner and approved finance staff | Reconciliation, margin, commissions, accounting handoff, and exception detection |
| Marketing Copilot | Owner and marketing staff | Attribution, funnel quality, source economics, and experiment recommendations |
| Executive Copilot | CEO | Priorities, bottlenecks, staffing pressure, cash visibility, risk, and decisions |

Shared engines:

- Inbound inquiry triage.
- Call transcription, evidence extraction, quality scoring, and coaching.
- Underwriting, comp, repair, and report analysis.
- Compliance preflight and suppression enforcement.
- Buyer matching.
- Document intelligence.
- Approved knowledge and SOP retrieval.
- Data-quality and conflict detection.
- Evaluation, observability, cost, and rollback control.

The shared engines are not separate bots that staff must operate. A copilot selects the correct
engine based on the current record and task.

### Copilot-To-Engine Mapping

| Staff-facing copilot | Backend specialist engines |
| --- | --- |
| Prospecting Copilot | Prospecting Intelligence, Call Intelligence, Compliance, Data Quality |
| Lead Manager Copilot | Inbound Lead, Lead Manager Support, Call Intelligence, Compliance |
| Acquisitions Copilot | Call Intelligence, Appointment Preparation, Underwriting And Comp, Negotiation Coach, Compliance |
| Transaction Copilot | Transaction Coordination, Document Intelligence, Compliance |
| Disposition Copilot | Disposition, Buyer Relationship, Document Intelligence, Compliance |
| Finance Copilot | Finance And Commission, Document Intelligence |
| Marketing Copilot | Marketing Intelligence, Data Quality, Compliance |
| Executive Copilot | Executive Operations plus approved aggregate outputs from every other engine |

## Current Starting Point

Delivered:

- Fourteen backend specialist definitions with versioned prompts.
- Tool permission, approval, run, tool-call, trace, cost, promotion, and rollback records.
- Idempotent orchestrator events, budgets, bounded retries, and dry-run controls.
- Evaluation datasets, cases, runs, results, and deterministic fixture evaluations.
- Lead-intake summaries.
- Recorded-call transcription, speaker segments, evidence-backed notes, and reviewed CRM update
  proposals.
- External execution blocked in the baseline tool policies.

Still required:

- Group the backend specialists into the eight role-facing copilots.
- Approved knowledge sources, redaction rules, and representative evaluation cases.
- Production model execution and strict production tools for every capability.
- Copilot workspace experiences inside each role's existing OS workflow.
- Measured draft-only pilots and capability-specific promotion decisions.
- Provider integrations required for documents, accounting, advertising, and approved external
  communication.

## Definition Of Done

Every copilot is complete only when:

1. Its human owner, scope, triggers, tools, data, and prohibited actions are documented.
2. It works inside the role's existing workspace and preserves one business record.
3. Every output links to its supporting evidence and identifies uncertainty.
4. Permissions and business rules are enforced server-side.
5. Normal, incomplete, conflicting, policy-blocked, and adversarial cases pass evaluation.
6. A supervised pilot measures acceptance, correction, failure, latency, cost, time saved, and
   business outcomes.
7. It has alerts, a budget, a named owner, rollback triggers, and a kill switch.
8. Any increased autonomy is approved for one exact capability and tool, not the whole copilot.

## Phase AI1: Copilot Contracts And Data Governance

Goal: Define exactly how humans and AI work together before adding production model behavior.

Build:

- Register the eight staff-facing copilots and map the existing backend specialists to each one.
- Rename Lead Management to Lead Manager Copilot in product language and make the Lead Manager the
  accountable owner.
- Define trigger, input, output, tool, evidence, approval, escalation, and prohibited-action
  contracts for every capability.
- Create a field-level source hierarchy: human-confirmed fact, verified provider fact, unverified
  provider fact, and model inference.
- Define redaction and retention rules for seller, buyer, employee, call, contract, and financial
  data.
- Create the approved-knowledge registry for scripts, SOPs, policies, market playbooks, and
  attorney-approved templates.
- Add shared data-quality rules for duplicates, stale records, missing attribution, and conflicting
  facts.

APIs required: none.

Exit criteria:

- Every copilot has a named human owner and signed-off capability matrix.
- Every sensitive field has a source and overwrite policy.
- Knowledge sources have an owner, version, effective date, and permitted audience.
- No copilot is described as owning a human job or making a permanently reserved decision.

## Phase AI2: Golden Cases And Evaluation Standards

Goal: Create the practice tests Stonegate will use to judge AI quality.

Build:

- Redacted golden datasets for Lead Manager Copilot and Call Intelligence first.
- Normal, incomplete, conflicting, stale, duplicate, policy-blocked, and malicious-input cases.
- Expected structured outputs, allowed uncertainty, required evidence, and prohibited behavior.
- Capability-specific thresholds for factual accuracy, evidence coverage, critical failures,
  latency, and cost.
- Reviewer instructions and disagreement resolution.
- A process for adding corrected production examples without exposing unnecessary personal data.

APIs required: none for dataset creation; OpenAI is optional for early comparison runs.

Exit criteria:

- At least 50 approved operating cases for the first pilot capability.
- At least 25 policy, failure, and adversarial cases.
- No secrets, payment credentials, or unnecessary personal identifiers in evaluation exports.
- The CEO and relevant role owner approve the expected results and promotion thresholds.

## Phase AI3: Production Runtime, Tools, And Monitoring

Goal: Connect models to Stonegate through narrow, observable, recoverable controls.

Build:

- OpenAI Responses API adapter behind the existing Stonegate orchestrator.
- Structured-output schemas and strict server-side tools.
- Model router for high-volume, default, and escalation work.
- Approved-knowledge retrieval with exact source-version evidence.
- Read-only provider tools and idempotent internal-action tools.
- Context, timeout, retry, rate, per-run cost, daily cost, and circuit-breaker limits.
- Trace redaction, error monitoring, alerts, and one-click capability/provider shutdown.
- Replay approved datasets in CI and the AI Control Center.
- Compare prompt and model versions by quality, latency, and cost; block regressions.

APIs required:

- OpenAI.
- Selected production error-monitoring provider.

Exit criteria:

- Every tool enforces organization, role, record, field, and action scope server-side.
- A duplicate event cannot duplicate a task, message, document action, or provider action.
- Model and provider outages fail safely.
- The same dataset can compare two versions and block a regression.
- No external send or high-risk action is available to the model.

## Phase AI4: Lead Manager Copilot

Goal: Give the Lead Manager a daily assistant without transferring responsibility for leads.

Build:

- New-inquiry and conversation summaries.
- Daily work queue prioritization using deterministic SLA and stage rules.
- Qualification gaps and recommended questions.
- Missed-reply, overdue-follow-up, and neglected-lead alerts.
- Human-approved SMS and email drafts.
- Next-task and appointment proposals.
- Handoff preparation for Acquisitions.
- Clear evidence, confidence, and reason for every recommendation.
- Role dashboard for acceptance, correction, response time, appointments, time saved, and cost.

The human Lead Manager:

- Owns qualification, seller judgment, communication, appointment quality, and handoff.
- Approves seller-facing drafts during the pilot.
- Corrects facts before they become authoritative.

APIs required:

- OpenAI.
- Stonegate CRM, inbox, tasks, and internal calendar.
- Twilio and Google Workspace only when their production activation is complete.

Exit criteria:

- The copilot passes AI2 evaluations with no critical authority or compliance failure.
- A four-week draft-only pilot records useful operating volume.
- Staff corrections and seller outcomes are measurable.
- Only reversible internal task creation may be considered for the first autonomy promotion.

## Phase AI5: Prospecting Copilot And Call Quality

Goal: Help VAs work assigned records consistently and hand off better opportunities.

Build:

- Explainable record priority after deterministic eligibility screening.
- Approved-script presentation and required-question tracking.
- Pre-call property and prior-attempt context.
- Suggested disposition, callback, and handoff drafts.
- Call transcription and evidence-backed summaries after recording activation.
- Script adherence, qualification completeness, objection handling, data quality, and handoff
  quality scoring.
- Individual coaching summaries and manager trend reporting.
- Immediate escalation for DNC requests, complaints, unclear identity, or policy uncertainty.

The human VA:

- Conducts initial cold calls.
- Confirms the disposition and handoff facts.
- Remains accountable for following the approved script and honoring stop requests.

APIs required:

- OpenAI.
- Twilio Voice and recording after compliance activation.
- Approved DNC screening process or vendor evidence.
- Current property-data adapter for factual call preparation.

Exit criteria:

- Deterministic screening, company suppression, and calling rules always run before prioritization.
- Call and coaching scores are compared with manager review.
- No autonomous cold AI voice is enabled.
- Handoff quality improves without increasing complaints, unsupported facts, or correction burden.

## Phase AI6: Acquisitions Copilot

Goal: Prepare the closer for seller conversations, appointments, underwriting review, and
negotiation while keeping price authority human.

Build:

- Complete conversation and call brief.
- Appointment brief with motivation, timeline, condition, occupancy, price history, unresolved
  questions, objections, tasks, and logistics.
- Walkthrough evidence organization and missing-evidence detection.
- Comp similarity, outlier, recency, price-per-square-foot, condition, and source explanations.
- Repair-evidence comparison and missing-input questions.
- Investor and client report quality checks.
- Negotiation questions, objection preparation, and approved-ceiling warnings.
- Post-appointment summary and follow-up drafts.
- Call-quality coaching for qualification, discovery, and authority compliance.

The human closer:

- Selects and approves comps, repairs, underwriting, offer authority, concessions, and seller
  communication.
- Conducts the appointment and negotiation.
- Approves the documented outcome.

APIs required:

- OpenAI.
- RentCast.
- Optional licensed MLS/RESO or ATTOM adapter after measured need.
- Twilio recording/transcription and internal calendar.
- Optional route estimates only if operating data justifies them.

Exit criteria:

- Backtesting uses verified outcomes and human-reviewed comp sets.
- ARV error, range coverage, provider disagreement, reviewer overrides, and report corrections are
  measured.
- Meeting briefs are reviewed for accuracy and usefulness.
- AI cannot present, approve, or change a binding offer.

## Phase AI7: Transaction Copilot And Document Intelligence

Goal: Help the Transaction Coordinator move executed contracts to closing without missing
documents, parties, or deadlines.

Prerequisites:

- Private S3-compatible object storage.
- Selected e-signature provider.
- Attorney-approved templates and market playbooks.

Build:

- Document classification, duplicate detection, and proposed field extraction.
- Source-page evidence for dates, parties, property, price, and signatures.
- Contract and checklist comparison.
- Deadline, earnest-money, title, access, inspection, assignment, and funding-risk monitoring.
- Closing-attorney and seller email drafts.
- E-signature envelope and Stonegate record reconciliation.
- Missing-document and conflicting-term escalation.

The human Transaction Coordinator:

- Confirms contract facts, checklist completion, parties, deadlines, and closing status.
- Approves external requests and coordinates with the attorney or title company.

APIs required:

- OpenAI.
- Private object storage.
- E-signature provider.
- Google Workspace.

Exit criteria:

- Required-document and deadline detection are measured on redacted packages.
- Every material extracted fact links to its source.
- AI cannot edit legal language, sign, release, interpret legal rights, or mark a deal funded.

## Phase AI8: Disposition Copilot And Buyer Intelligence

Goal: Help the Disposition specialist place approved contracts quickly and accurately.

Build:

- Explainable buyer matching using market, asset, price, strategy, capacity, proof, activity, and
  reliability.
- Fact-checked deal-package and property-summary drafts.
- Human-approved buyer outreach and response classification.
- Showing, proof-of-funds, deposit, offer, backup-buyer, deadline, and fallout alerts.
- Side-by-side offer and buyer-risk comparison.
- Buyer preference and relationship update proposals.
- Human-led versus AI-assisted disposition performance reporting.

The human Disposition specialist:

- Approves the package, recipients, communication, showing plan, buyer recommendation, economics,
  and backup strategy.
- Owns the buyer relationship and placement outcome.

APIs required:

- OpenAI.
- Buyer CRM and transaction evidence.
- Object storage.
- Approved operational email and messaging providers.

Exit criteria:

- Buyer-match quality, package corrections, responses, time-to-buyer, deposits, and fallout are
  measured.
- No unverified property claim reaches a buyer.
- Final buyer selection and deal economics always require human approval.
- AI-assisted compensation mode remains locked until measured and explicitly activated.

## Phase AI9: Finance, Marketing, And Executive Copilots

Goal: Give management dependable financial, growth, and operating intelligence.

Finance Copilot:

- Draft funded-deal reconciliation, margin, commission, reserve, and accounting entries.
- Compare closing statements, transaction records, compensation plans, and provider ledger entries.
- Flag unexplained differences and missing evidence.

Marketing Copilot:

- Explain lead quality, cost per qualified lead, appointment, contract, funded deal, and margin by
  source.
- Detect funnel loss and recommend controlled tests.
- Prepare approved offline-conversion events.

Executive Copilot:

- Produce daily priorities and weekly operating briefs.
- Surface SLA failure, staffing pressure, pipeline risk, cash obligations, margin risk, provider
  failure, and decisions.
- Track whether copilots save time and improve business outcomes.

APIs required:

- OpenAI.
- QuickBooks Online or a controlled accounting import/export.
- Google Ads and Meta conversion adapters.
- Stonegate finance, marketing, and operating records.

Exit criteria:

- Finance drafts reconcile against funded examples with zero unexplained material difference.
- Marketing conclusions cite retained costs, attribution, and outcomes.
- Executive briefs distinguish facts, estimates, and recommendations.
- Payments, commissions, budgets, accounting finalization, and published ad changes remain
  human-approved.

## Phase AI10: Controlled External Automation And Optimization

Goal: Permit only proven, bounded external actions and operate the AI system as a measured business
capability.

Eligible only after earlier pilots:

- Consented seller acknowledgements.
- Appointment confirmations and reminders from approved templates.
- Low-risk follow-up inside exact frequency, contact-hour, content, and escalation limits.
- Approved buyer-campaign delivery.
- Future consented inbound voice assistance with clear disclosure and immediate human transfer.

Build:

- Per-capability audience, template, frequency, volume, and cost bounds.
- Canary rollout, live monitoring, automatic pause conditions, rollback, and kill switch.
- Human takeover with the complete conversation and decision history.
- Monthly quality, policy, privacy, cost, and business-outcome review.
- Quarterly model, prompt, tool, knowledge, provider, and autonomy review.
- Market-specific policy packs before geographic expansion.

Always prohibited from autonomous authority:

- Cold AI voice without a separately approved legal, consent, disclosure, and monitoring design.
- Binding offers, contract changes, signatures, releases, or legal interpretations.
- Final buyer selection or material economics.
- Payments, commissions, budgets, permissions, suppression overrides, or destructive deletion.

APIs required:

- Approved Twilio Messaging and Voice configuration.
- Google Workspace.
- OpenAI Realtime only for a separately approved inbound voice use case.

Exit criteria:

- Every external capability has a named owner, approved audience, tested template or bounds,
  evaluation threshold, volume ramp, alerts, rollback trigger, and kill switch.
- Canary performance is reviewed before broader activation.
- The system can stop safely when a provider, model, policy, or data dependency fails.
- No market launches with copied policy; each market receives reviewed operating and compliance
  configuration.

## Build Order

The required order is:

1. AI1: Copilot contracts and data governance.
2. AI2: Golden cases and evaluation standards.
3. AI3: Production runtime, tools, and monitoring.
4. AI4: Lead Manager Copilot.
5. AI5: Prospecting Copilot and call quality.
6. AI6: Acquisitions Copilot.
7. AI7: Transaction Copilot.
8. AI8: Disposition Copilot.
9. AI9: Finance, Marketing, and Executive Copilots.
10. AI10: Controlled external automation and optimization.

Provider work continues in parallel. Lead Manager Copilot can run with simulated communications
before Twilio and Google Workspace are live. Recording-dependent work waits for approved disclosure
and retention policy. Transaction, finance, and advertising automation waits for its provider
adapter rather than inventing a second source of truth.

## Immediate Next Build

Start AI1. The first implementation package should contain:

1. The eight copilot definitions and backend-specialist mapping.
2. The Lead Manager Copilot capability and prohibited-action contract.
3. The field-level source and overwrite policy.
4. The approved-knowledge registry.
5. Redaction and evaluation-data rules.
6. The first Lead Manager and Call Intelligence case templates for AI2.

The first production milestone is a Lead Manager Copilot that reliably organizes work, identifies
gaps, drafts follow-up, and protects response SLAs while the human Lead Manager remains accountable
for every seller relationship and decision.
