# AI Agent System

Last updated: July 22, 2026

Stonegate uses one governed, event-driven AI system with specialized capabilities. It does not use
fourteen independent chatbots with separate memory or authority.

`OPERATING_MODEL.md` defines human roles, commissions, handoffs, and permanent human authority.
This document is the technical source of truth for agent architecture, tools, model routing,
memory, evaluation, and autonomy. Delivery order is defined in `AI_AUTOMATION_ROADMAP.md`.

## End-State Vision

The system should remove repetitive coordination and preparation work from every position while
keeping humans responsible for judgment that can bind the company or materially affect a seller.

Staff interact with eight role-facing copilots: Prospecting, Lead Manager, Acquisitions,
Transaction, Disposition, Finance, Marketing, and Executive. The backend specialists in this
document are technical capabilities selected by those copilots, not separate bots that employees
must manage.

The copilot assists its human role; it does not own that role. In particular, the Lead Manager
Copilot organizes, summarizes, drafts, recommends, and monitors while the human Lead Manager owns
qualification, seller communication, appointment quality, and handoff.

The target operating loop is:

1. A business event is stored in PostgreSQL.
2. Deterministic rules decide whether an AI capability may run.
3. The orchestrator selects one specialist, an approved prompt, a model tier, and narrow tools.
4. The specialist returns a structured proposal with evidence, uncertainty, and the next decision.
5. Policy either stores a low-risk internal result, requests human approval, or blocks the action.
6. Every run, tool call, approval, correction, cost, and final outcome becomes evaluation evidence.

PostgreSQL remains the durable memory and business source of truth. Model conversation state is
temporary execution context, not an independent customer record.

## Architecture

### Event And Policy Layer

- Domain events trigger runs: lead created, reply received, call completed, appointment scheduled,
  underwriting saved, contract executed, deadline approaching, buyer response received, or closing
  funded.
- Deterministic services enforce role scope, consent, suppression, contact hours, offer authority,
  contract gates, buyer-selection gates, payment controls, and data retention.
- Events and outbound actions use stable idempotency keys so retries cannot duplicate work.

### Orchestrator

The Stonegate orchestrator owns:

- Agent, prompt, tool-policy, model, and pricing versions.
- Risk classification and maximum autonomy per capability.
- Per-run and daily cost limits, timeouts, and retry limits.
- Context assembly from organization-scoped records.
- Approval routing, rollback ownership, traces, and outcome linking.
- Model routing based on task difficulty, latency, and measured quality.

The existing control plane remains authoritative. OpenAI's Responses API is the default model
interface. The Agents SDK may be adopted behind the existing service boundary when its typed tools,
handoffs, resumable approvals, and tracing reduce implementation work; it must not replace
Stonegate permissions, audit history, or business policy.

### Specialist Layer

Specialists are bounded capabilities called by the orchestrator. A manager-style orchestrator
should normally call specialists as tools and retain control of the run. Free-form agent-to-agent
handoffs and beta multi-agent behavior are not production dependencies.

Every specialist response must include:

- Structured output matching a versioned schema.
- Facts used and links to Stonegate evidence.
- Missing information and conflicting facts.
- Confidence by material field, not only one overall score.
- Recommended action and required human decision.
- Tool results, provider timestamps, and freshness.

### Tool Gateway

Models never receive arbitrary database, shell, browser, payment, user-administration, or provider
credential access. Each tool is a server-side function with:

- A narrow input and output schema.
- Organization, role, record, and field scope.
- Read, draft, propose, or execute permission.
- Approval and risk requirements.
- Idempotency, timeout, retry, and rate-limit behavior.
- Audit logging and redaction rules.

Tool families include CRM reads, task proposals, scheduling availability, approved communication
drafts, property-data retrieval, underwriting calculations, document classification, buyer
matching, accounting proposals, and approved knowledge retrieval.

### Knowledge And Memory

- CRM records are the durable customer and deal memory.
- Human-confirmed facts outrank provider facts; provider facts outrank model inference.
- An approved knowledge base holds versioned SOPs, scripts, policies, attorney-approved templates,
  and market playbooks.
- File search may retrieve approved knowledge, but the exact source version must be stored with the
  run.
- Web search is allowed only for approved research capabilities and must return citations. It is
  secondary context, never the source of truth for consent, offers, contracts, or comparable sales.
- The system will not scrape consumer real-estate sites or use open-web asking prices as dependable
  closed-sale evidence.

## Model Routing

Model names and prices are configuration, not permanent business rules. Promotions require
evaluation against Stonegate cases.

| Work type | Starting model policy |
| --- | --- |
| High-volume classification, extraction, and routing | Evaluate `gpt-5.6-luna` against the default before promotion |
| Qualification, summaries, briefs, drafts, packages, and operational copilots | `gpt-5.6-sol` with medium reasoning |
| Difficult valuation review, negotiation preparation, policy analysis, and executive decisions | Escalate to `gpt-5.6-sol` only when the default is insufficient |
| Recorded-call transcription with speakers | `gpt-4o-transcribe-diarize` |
| Future consented live voice | OpenAI Realtime behind Twilio, disclosure, transfer, and shutdown controls |

Use the least expensive model that passes the capability's quality, latency, and safety thresholds.
Changing a model or reasoning level creates a new evaluated version. Fine-tuning is considered only
after prompts, tools, schemas, retrieval, and representative evals have plateaued.

## Backend Specialist Portfolio

| Specialist | Primary work | Tools and data | Maximum planned autonomy |
| --- | --- | --- | --- |
| Prospecting Intelligence | Rank records, explain priority, flag data gaps | Campaign records, vendor data, suppression evidence, property facts | Internal recommendation |
| Inbound Lead | Triage seller inquiries, identify urgency, draft first response | CRM, consent, inbox, calendar | Approved external templates after pilot |
| Lead Manager Support | Find qualification gaps, stale leads, and next actions for the human Lead Manager | CRM, tasks, inbox, calendar, approved scripts | Low-risk internal tasks |
| Call Intelligence | Transcribe, separate speakers, extract facts and commitments | Twilio recordings, OpenAI transcription, CRM | Approved structured CRM updates after pilot |
| Appointment Preparation | Produce seller brief, questions, logistics, and risk flags | CRM, qualification, underwriting, internal calendar, optional routes | Internal brief |
| Underwriting And Comp | Prepare evidence, exclusions, ranges, scenarios, and reports | RentCast, later MLS/RESO or ATTOM, deterministic calculators | Recommendation only |
| Negotiation Coach | Prepare questions, objections, options, and ceiling warnings | Approved underwriting, offer authority, seller history | Internal coaching only |
| Transaction Coordinator | Detect missing documents, deadlines, and closing risks | Transaction records, object storage, e-signature, operational email | Low-risk internal tasks |
| Disposition | Match buyers and draft approved deal packages and outreach | Buyer CRM, deal facts, documents, approved channels | Draft campaign; human selects buyer |
| Buyer Relationship | Maintain preferences, reliability, follow-up, and stale POF alerts | Buyer CRM, inbox, proof-of-funds evidence | Low-risk internal tasks |
| Finance And Commission | Reconcile deal economics and draft payouts and exports | Funded records, plan versions, QuickBooks adapter | Draft reconciliation only |
| Marketing Intelligence | Analyze source quality, funnel loss, and budget tests | Attribution, costs, Google/Meta events, outcomes | Internal recommendation |
| Compliance | Preflight consent, suppression, contact, retention, and policy risk | Consent, suppression, provider events, approved policy | Block or escalate; never waive |
| Executive Operations | Summarize bottlenecks, risk, cash, staffing, and decisions | Aggregated organization metrics | Internal brief only |

Knowledge retrieval, document intelligence, evaluation, and observability are shared platform
capabilities rather than additional agents.

## Position Assistance

### VA And Prospecting

AI may clean and prioritize assigned data, present the approved script, detect missing answers,
classify dispositions, schedule compliant callbacks, and prepare a handoff. Deterministic screening
must establish calling eligibility before AI scoring is useful.

Phase AI5 implements priority and preparation as draft-only assistance. The backend, not the model,
enforces assignment, eligibility, suppression, script, transcript, disclosure, and role scope.
Call coaching requires an approved transcript and manager review; compliance flags escalate even
when no transcript or model output exists.

AI-generated cold voice is not an initial Stonegate capability. Federal and state calling,
prerecorded/artificial voice, consent, disclosure, and seller-liability requirements require a
separate legal and operational approval before any pilot.

### Lead Manager Copilot

AI may summarize new inquiries, monitor speed-to-lead and unanswered messages, prepare qualification
questions, draft follow-up, detect neglected leads, and propose appointments. Early pilots remain
draft-only; later approved templates may be sent automatically only to appropriately consented
contacts with escalation and shutdown controls.

The human Lead Manager remains accountable for qualification, seller judgment, communication,
appointments, and acquisition handoff. The copilot cannot silently qualify a seller, replace a
confirmed fact, or take ownership of the relationship.

### Acquisitions Closer

AI may build meeting briefs, organize walkthrough evidence, produce comp and repair questions,
identify uncertainty, prepare negotiation options, and remind the closer of approved authority. It
cannot present or change a binding offer.

### Transaction Coordination

AI may classify documents, extract dates and parties, compare the file against a checklist, draft
closing emails, and escalate missing items. It cannot interpret legal rights, alter contracts,
apply signatures, or declare a closing funded.

### Dispositions

AI may score buyer fit, assemble a fact-checked package, personalize drafts from approved facts,
track responses, and recommend follow-up. It cannot choose the winning buyer, misrepresent the
property, release a contract, or change economics.

### Finance, Marketing, And Management

AI may draft reconciliations, identify mismatches, explain funnel performance, detect operational
bottlenecks, and recommend controlled experiments. It cannot move money, finalize commissions,
change budgets, or publish ads without approval.

## Autonomy Policy

Autonomy is promoted per capability and tool, never for an entire agent.

| Level | Meaning |
| --- | --- |
| Observe | Read scoped facts and produce a private summary |
| Draft | Prepare content or a proposed record for human review |
| Recommend | Compare options and explain a recommended decision |
| Execute internal | Perform a reversible, low-risk internal action within exact limits |
| Execute external | Perform one approved external action within exact template, audience, and policy limits |

Good first autonomous actions:

- Refresh internal summaries after new evidence.
- Create or reschedule internal follow-up tasks within policy.
- Classify documents and communications without overwriting confirmed facts.
- Flag SLA, consent, suppression, missing-document, and provider failures.
- Refresh dashboards and draft packages.

Human approval always remains required for:

- Offer ceilings, price changes, concessions outside approved authority, and binding offers.
- Contract language, contract sending, signatures, releases, and legal interpretations.
- Final buyer selection and material deal-term changes.
- Payments, funded status, commission approval, accounting finalization, and budget changes.
- User permissions, data export, broad deletion, suppression override, or retention override.
- Cold AI voice, new outreach programs, or any unapproved communication policy.

## Evaluation And Promotion

Every capability needs an approved, redacted dataset containing normal cases, edge cases, failures,
and adversarial cases. Production examples join a dataset only after sensitive fields are removed
or replaced and a human approves the expected outcome.

Evaluation covers:

- Structured-field accuracy and evidence coverage.
- False facts, missed conflicts, and unsupported certainty.
- Correct tool choice, arguments, ordering, and blocked-tool behavior.
- Approval routing and deterministic-policy compliance.
- Draft acceptance, reviewer edits, rejection, and business outcome.
- Failure, retry, latency, token use, and cost.

Promotion requires:

1. Passing offline replay against fixed thresholds.
2. A draft-only production pilot with a named owner.
3. No critical policy, privacy, or authority violation.
4. Measured time savings without unacceptable correction burden.
5. A documented rollback trigger and kill switch.
6. Explicit owner approval for the exact next autonomy level.

Call intelligence keeps human approval until at least 50 calls have been reviewed, field agreement
and evidence coverage are at least 90%, reviewer rejection is no more than 5%, and processing
failure is no more than 2%. Passing makes it eligible for a narrow pilot; it does not authorize
seller messages, offers, contracts, or financial actions.

## Observability, Security, And Cost

- Record model, reasoning level, prompt, schema, tools, evidence, latency, usage, pricing version,
  status, approval, correction, and linked business outcome.
- Redact secrets and unnecessary seller data from prompts, traces, alerts, and evaluation exports.
- Encrypt OAuth and provider tokens and keep all raw credentials server-side.
- Apply per-run, per-agent, and organization daily budgets with hard stops.
- Alert on failure spikes, tool denials, unexpected cost, repeated retries, low confidence, and
  policy blocks.
- Keep one-click disablement by capability and provider.
- Retain enough source evidence to reproduce a decision without retaining unnecessary raw model
  context indefinitely.

`OPENAI_PRICING_OVERRIDES_JSON` may update estimated token rates without a release. Pricing
estimates never replace provider billing reconciliation.

## Research Basis

- [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model)
- [OpenAI Agents SDK](https://developers.openai.com/api/docs/guides/agents)
- [OpenAI agent evaluations](https://developers.openai.com/api/docs/guides/agent-evals)
- [OpenAI tools](https://developers.openai.com/api/docs/guides/tools)
- [OpenAI speech-to-text and diarization](https://developers.openai.com/api/docs/guides/speech-to-text#speaker-diarization)
- [OpenAI practical guide to building agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/)
- [NIST AI Risk Management Framework](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/)
- [HubSpot Sales Hub](https://www.hubspot.com/products/sales)
- [Salesforce human-representative handoff](https://help.salesforce.com/s/articleView?id=mktg.um_channel_email_human_rep_experience.htm&language=en_US&type=5)
- [REsimpli real-estate investor CRM feature coverage](https://resimpli.com/)
- [FTC Telemarketing Sales Rule guidance](https://www.ftc.gov/business-guidance/resources/complying-telemarketing-sales-rule)
- [FTC CAN-SPAM compliance guidance](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business)
