# AI Automation Roadmap

Last updated: July 22, 2026

This is the ordered delivery plan for turning Stonegate's implemented AI control plane into a
measured production assistant system. It does not replace the main product roadmap. Provider setup
may proceed in parallel, but autonomy cannot skip evaluation, policy, or approval gates.

## Current Position

Implemented:

- Fourteen agent definitions and versioned prompt records.
- Tool permission records, approval requests, run logs, tool-call logs, traces, cost limits, and
  rollback ownership.
- Evaluation datasets, cases, runs, results, trace review, capability promotion, and rollback
  records.
- Lead-intake summaries.
- Recorded-call transcription, evidence-backed notes, and human-reviewed CRM update proposals.

Not yet proven:

- Representative redacted evaluation datasets.
- Production model execution for every portfolio capability.
- Measured draft-only pilots outside call intelligence.
- Any approved external autonomy.

## Phase AI1: Data Governance And Golden Cases

Build:

- A redaction standard for seller, buyer, employee, contract, and financial data.
- Versioned knowledge sources and source ownership.
- Golden datasets for Lead Management and Call Intelligence.
- Normal, edge, conflict, incomplete, policy-block, and malicious-input cases.
- Outcome labels and reviewer instructions.

Exit criteria:

- At least 50 approved cases for the first capability and 25 policy/adversarial cases.
- No live secret, payment credential, or unnecessary personal identifier in an eval export.
- A named business owner approves expected outputs and promotion thresholds.

## Phase AI2: Runtime And Tool Gateway Hardening

Build:

- Responses API adapter behind the existing orchestrator.
- Structured-output schemas and strict tool definitions.
- Model router for high-volume, default, and escalation tiers.
- Idempotent internal action tools and read-only provider tools.
- Context-size, timeout, retry, daily-cost, and circuit-breaker controls.
- Trace redaction and production error monitoring.

Exit criteria:

- Every tool enforces organization, role, record, and field scope server-side.
- Duplicate events cannot duplicate a task, message, or provider action.
- A provider or model outage fails safely and can be disabled without a deployment.

## Phase AI3: Evaluation Factory

Build:

- Dataset replay in CI and the AI Control Center.
- Deterministic checks, model graders, trace graders, and human review sampling.
- Model and prompt comparison with quality, latency, and cost reporting.
- Regression gates for prompt, model, schema, or tool changes.

Exit criteria:

- The same approved dataset can be replayed against two versions.
- A regression blocks promotion.
- Results link to exact prompts, models, tool policies, and expected outcomes.

## Phase AI4: Lead Operations Pilot

Capabilities:

- Inbound Lead.
- Lead Management.
- Compliance preflight.

Start with:

- New-inquiry summary.
- Qualification gaps.
- Speed-to-lead and missed-reply alerts.
- Next-task proposals.
- Human-approved SMS and email drafts.

Exit criteria:

- Draft acceptance, corrections, response time, cost, and time saved are measured for four weeks.
- No contact is attempted without deterministic consent and suppression checks.
- Only reversible internal task creation may be considered for promotion.

## Phase AI5: Call, Appointment, And Acquisition Copilot

Capabilities:

- Call Intelligence.
- Appointment Preparation.
- Negotiation Coach.

Build:

- Automatic recording-ready processing after compliance activation.
- Speaker-separated transcript, evidence timestamps, and structured seller facts.
- Appointment brief, missing questions, objections, repair questions, and logistics.
- Approved-ceiling and unsupported-claim warnings during preparation.

Exit criteria:

- Call Intelligence satisfies its documented minimum sample and quality thresholds.
- Brief accuracy and closer usefulness are measured.
- No capability presents or changes a binding offer.

## Phase AI6: Underwriting And Negotiation Support

Capabilities:

- Underwriting And Comp.
- Negotiation Coach.

Build:

- Provider-fact reconciliation and stale-data warnings.
- Comp outlier, similarity, price-per-square-foot, condition, and recency explanations.
- Repair-evidence comparison and missing-input questions.
- Investor and client report quality checks.
- Optional second property-data source behind the existing adapter.

Exit criteria:

- Backtesting uses verified transactions and human-reviewed comps.
- Range coverage, ARV error, offer correction, provider disagreement, and reviewer overrides are
  measured.
- Formulas remain deterministic and humans approve underwriting and offer authority.

## Phase AI7: Transaction And Document Intelligence

Capabilities:

- Transaction Coordinator.
- Compliance.

Prerequisites:

- Private S3-compatible object storage.
- Selected e-signature provider.
- Attorney-approved templates and market playbooks.

Build:

- Document classification and field extraction.
- Checklist comparison, deadline monitoring, and missing-document escalation.
- Closing-email drafts and status summaries.
- Contract-version and signature-event reconciliation.

Exit criteria:

- Required-document recall is measured on redacted packages.
- Dates and parties always link to source pages or provider events.
- AI cannot edit legal language, sign, release, or mark a closing funded.

## Phase AI8: Disposition And Buyer Automation

Capabilities:

- Disposition.
- Buyer Relationship.

Build:

- Buyer fit scoring with explainable criteria.
- Fact-checked deal-package drafts.
- Human-approved outreach sequence and response classification.
- Showing, proof-of-funds, offer, backup-buyer, and fallout alerts.

Exit criteria:

- Matching quality, package corrections, buyer response, time-to-buyer, and fallout are measured.
- The selected buyer and economics always require human approval.
- AI-operated disposition mode stays locked until compensation and quality rules are approved.

## Phase AI9: Finance, Marketing, And Executive Intelligence

Capabilities:

- Finance And Commission.
- Marketing Intelligence.
- Executive Operations.

Prerequisites:

- QuickBooks Online adapter or controlled accounting import/export.
- Google Ads and Meta offline conversion adapters.

Build:

- Funded-deal reconciliation and commission draft review.
- Provider-versus-ledger mismatch detection.
- Source quality, cost per qualified lead, cost per contract, and margin reporting.
- Daily and weekly executive briefs with bottlenecks, cash, staffing, and decision requests.

Exit criteria:

- Finance drafts reconcile against closed examples with zero unexplained material difference.
- Marketing recommendations cite retained costs and outcomes.
- Payments, commissions, budgets, and ad changes remain human-approved.

## Phase AI10: Controlled External Automation

Consider only capabilities that passed prior phases:

- Consented seller acknowledgements and appointment reminders from approved templates.
- Low-risk follow-up inside exact frequency, contact-hour, and escalation limits.
- Approved buyer campaign delivery.
- Future consented inbound voice assistance with immediate human transfer.

Do not include:

- Autonomous cold AI voice.
- Binding offer or contract activity.
- Final buyer selection.
- Payment, commission, budget, permission, suppression, or legal decisions.

Exit criteria:

- Each external capability has an owner, approved audience, exact templates or bounds, evaluation
  threshold, volume ramp, monitoring, rollback trigger, and kill switch.
- A small canary runs before broader activation.
- Monthly quality, policy, cost, and business-outcome review remains mandatory.

## Recommended Immediate Sequence

1. Complete AI1 for Lead Management and Call Intelligence.
2. Complete the Phase 1 production restore, alert, and access-revocation checks.
3. Activate error monitoring before model pilots.
4. Implement AI2 and AI3.
5. Run AI4 draft-only while Twilio and Google Workspace setup finishes.
6. Resume recording and AI5 only after disclosure and retention approval.

The first useful production goal is not a fully autonomous company. It is a Lead Operations copilot
that reliably prepares work, catches neglected sellers, creates high-quality drafts, and proves its
value through corrections, outcomes, time saved, and cost.
