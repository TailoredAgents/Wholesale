# Stonegate Operating Model

Last updated: July 22, 2026

## Purpose

This document is the business operating source of truth for Stonegate Home Buyers. It defines how
people, AI agents, software, money, approvals, and records work together from campaign creation
through funded closing.

Implementation status belongs in `CURRENT_STATE.md`. Build order belongs in `ROADMAP.md`.
Technical boundaries belong in `ARCHITECTURE.md` and `AI_AGENTS.md`. The ordered path from the
current control plane to production assistance belongs in `AI_AUTOMATION_ROADMAP.md`.

## Business Objective

Stonegate begins in Georgia and expands market by market into surrounding states. The operating
system must support a local, appointment-led acquisition strategy while allowing centralized lead
management, dispositions, transaction coordination, finance, and AI assistance.

Primary financial policies:

- Target at least 30% company operating profit after commissions, advertising, outreach, and
  ordinary overhead.
- Reserve $2,500 of acquisition and outreach cost per funded seller until trailing results support
  a different policy amount.
- Target an assignment fee of at least $15,000. Smaller deals require an explicit profitability
  review rather than an automatic rejection.
- Pay commissions only from cleared, reconciled closing proceeds.
- Keep role compensation, company profit, and owner distributions separate.

## Organization

### Owner And CEO Management

The CEO owns strategy, advertising, hiring, training, performance management, systems, approvals,
compliance oversight, capital allocation, and market expansion. The CEO can cover any operational
role, but each role contribution remains separately attributed.

### VA Prospecting

Two initial VAs work assigned cold-outreach queues for $7 per hour. Their labor is part of the
acquisition and outreach cost, not the commission pool. They identify interest, record a controlled
disposition, schedule permitted callbacks, and hand warm opportunities to the Lead Manager.

VAs cannot export lists or access unrelated prospects, underwriting, contracts, buyers, finance,
commissions, or unrestricted recordings and transcripts.

### Lead Manager

The Lead Manager owns warm response, qualification, nurture, and appointment setting. This role is
not the Acquisitions Closer. Its principal outcome is a qualified appointment that occurs, not a
high count of weak appointments.

### Acquisitions Closer

The Acquisitions Closer prepares for and attends seller appointments, confirms property condition
and decision-makers, reviews underwriting, negotiates within approved authority, and obtains the
purchase contract. The CEO initially performs this role.

### Transaction Coordinator

The Transaction Coordinator owns the file from executed seller contract through funded closing:
closing-attorney intake, earnest money, title, payoff, due-diligence, document, assignment, and
closing deadlines. The CEO initially covers this role until the workload justifies a dedicated
operator.

### Dispositions

Dispositions owns the buyer outcome after an approved contract: package readiness, buyer matching,
deal distribution, inquiries, showings, offers, proof of funds, buyer selection preparation,
assignment, deposit, backup buyer, and closing support.

### AI Service Identities

AI agents receive narrow service identities and tools. They create evidence-backed work inside the
same Stonegate records as humans. They do not own separate copies of contacts, leads, conversations,
underwriting, deals, buyers, or financial facts.

## Record Lifecycle

### 1. Market And Campaign

The CEO approves the market, counties, list source, targeting, budget, caller assignment, script,
calling number, suppression evidence, and campaign dates. List cost and labor remain attributable
through closing.

### 2. Prospecting

Cold records remain prospects until genuine seller interest exists. VAs work controlled queues and
record standardized outcomes such as no answer, callback, follow-up, interested, not interested,
wrong number, bad data, or do not contact.

### 3. Warm Handoff

An interested prospect becomes a warm lead. The Lead Manager becomes owner, the CEO becomes a
watcher, and the source, calls, transcript, notes, consent, property, and attribution remain on the
same record. A response task and due time are created automatically. The VA becomes read-only after
finalizing the handoff disposition.

### 4. Qualification And Nurture

The Lead Manager confirms ownership, decision-makers, motivation, timeline, condition, occupancy,
price expectations, access, and known mortgage, lien, probate, foreclosure, or title concerns.
Missing noncritical facts do not block nurture, but they remain visible gaps.

### 5. Appointment

Stonegate checks closer availability, territory, and travel capacity before booking. The seller
receives approved confirmations and reminders. Cancellations and no-shows return to an owned
follow-up queue rather than disappearing from the pipeline.

### 6. Acquisition Preparation

Stonegate assembles seller history, qualification, unresolved questions, property data, comparable
evidence, ARV and repair ranges, offer scenarios, approved ceiling, likely objections, and meeting
logistics into one appointment brief.

### 7. Field Acquisition And Offer

The Closer confirms the property and decision-makers, captures photographs and repair details,
updates underwriting, negotiates within authority, and records the outcome. A lead becomes contract,
negotiation follow-up, nurture, disqualified, or lost with a required reason.

### 8. Contract And Transaction

An executed contract creates the transaction and closing checklist. The closing attorney receives
the approved file, and every material deadline has an owner, state, due time, evidence, and
escalation path.

### 9. Disposition

An approved, complete deal package enters the disposition queue. Stonegate matches qualified
buyers, distributes approved facts, tracks engagement, schedules access, receives offers, verifies
proof and deposit readiness, and presents a primary and backup buyer for human approval.

### 10. Closing And Reconciliation

After funds clear, Stonegate reconciles revenue, deductions, attribution, role credits,
commissions, payment state, and accounting. No projected commission becomes earned before funding.

## Compensation Model

### Adjusted Deal Margin

```text
Adjusted Deal Margin =
  collected deal revenue
  - $2,500 acquisition and outreach reserve
  - JV or partner payments
  - buyer credits and refunds
  - transactional funding
  - extraordinary deal-specific closing expenses
```

Ordinary software, administration, insurance, accounting, and general overhead are paid from the
company share. The $2,500 reserve is reviewed against trailing funded-deal data and changed only by
an effective-dated policy decision.

### Full Human Disposition

| Role | Adjusted Deal Margin |
| --- | ---: |
| Lead Manager | 10% |
| Acquisitions Closer | 10% |
| CEO Management | 10% |
| Dispositions | 15% |
| Transaction Coordinator | 5%, capped at $1,000 |
| Company before ordinary overhead | Approximately 50% |

When the CEO also closes the seller, the CEO earns 10% for management and 10% for acquisition
closing. When a dedicated Closer is assigned, that person earns the Closer share while the CEO
retains management compensation for performing the management role.

Any unused Transaction Coordinator amount above its cap returns to the company. Owner
distributions occur only after commissions, taxes, operating reserves, and the company profit
target are protected.

### AI-Assisted Disposition

| Operating mode | Human disposition share | Expected company share before overhead |
| --- | ---: | ---: |
| Human-led | 15% | Approximately 50% |
| AI-operated, human-managed | 10% | Approximately 55% |
| AI-led, human exception oversight | 5% to 7.5% | Approximately 57.5% to 60% |

The disposition mode and compensation-plan version are assigned before work begins. Stonegate does
not decide after closing that AI performed "most" of a specific deal. A lower human share is enabled
only after measured AI performance preserves assignment spread, response time, closing rate, buyer
quality, and compliance.

### Credit And Payment Rules

- The Lead Manager keeps qualification credit when another user provides temporary coverage.
- Closer credit belongs to the person who negotiated and obtained the seller contract.
- Disposition credit belongs to the assigned person who owns the buyer outcome under the selected
  operating mode.
- Coverage splits require approval before closing.
- Canceled or unfunded transactions do not earn commission.
- Earned, approved, payable, paid, reversed, and disputed are separate states.
- Historical plan versions and calculations never change when future rates change.

## AI Operating System

### Stonegate Orchestrator

The Orchestrator reacts to business events, selects an approved agent and prompt version, grants
only the required records and tools, enforces budget and policy, and records the complete run. It
does not replace deterministic workflow, permissions, suppression, pricing, or financial rules.

### Agent Portfolio

| Agent | Primary contribution | Initial authority |
| --- | --- | --- |
| Prospecting Intelligence | Prioritize records, prepare context, assist scripts, detect data and call-quality problems | Recommend |
| Inbound Lead | Respond to opted-in inquiries, collect basic facts, schedule Lead Manager contact | Draft; controlled sending pilot later |
| Lead Management | Find qualification gaps, draft follow-up, monitor nurture and neglected leads | Draft and recommend |
| Call Intelligence | Transcribe, separate speakers, extract facts, cite timestamps, score calls | Recommend CRM updates |
| Appointment Preparation | Produce the Closer's meeting brief and unresolved-question list | Internal execution |
| Underwriting And Comp | Gather evidence, score comps, explain ranges, calculate scenarios, produce reports | Recommend; no offer approval |
| Negotiation Coach | Prepare objections, questions, concessions, and approved-price warnings | Internal recommendation |
| Disposition | Build packages, match buyers, run approved campaigns, track responses, compare offers and deposits | Phased external automation |
| Buyer Relationship | Maintain criteria, proof status, activity, reliability, and re-engagement | Draft and recommend |
| Transaction Coordinator | Extract deadlines, maintain checklists, request routine items, escalate risks | Internal execution; external drafts |
| Compliance | Preflight outreach, consent, suppression, hours, recording, state, and document rules | Block or escalate; never override policy |
| Finance And Commission | Reconcile proceeds, calculate margin and compensation, detect exceptions | Draft calculations for approval |
| Marketing Intelligence | Attribute spend and recommend campaign-budget changes | Recommend |
| Executive Operations | Surface priorities, bottlenecks, forecasts, hiring pressure, and margin risk | Recommend |

### Autonomy Levels

1. Observe: summarize facts and detect gaps.
2. Draft: prepare messages, notes, tasks, documents, and calculations.
3. Recommend: propose structured actions with evidence and confidence.
4. Execute internal: perform narrow, reversible CRM actions after evaluation.
5. Execute external: perform an explicitly approved communication or provider action with
   monitoring, idempotency, and rollback or suppression handling.

Agents advance by capability, not as a group. A successful call-note agent does not authorize an
offer, buyer selection, payment, or unrelated communication agent.

### Permanent Human Authority

Humans approve offer ceilings, seller contracts, material concessions, final buyer selection,
payments, commission exceptions, user permissions, market launch, and legal or financial
representations. AI cannot bypass deterministic consent, suppression, recording, contact-hour,
price, document, or role controls.

Autonomous AI cold voice calls to unconsented consumers are not part of the operating model. Human
VAs may use AI assistance; AI voice begins only with an approved consent, disclosure, compliance,
and monitoring design.

## Service Standards

- Public inbound leads receive a speed-to-lead task with a five-minute target during staffed hours.
- Warm VA handoffs are accepted during the same shift and cannot remain without an owner.
- Every appointment has confirmation, reminder, outcome, and next-action states.
- Executed contracts are sent to the approved closing attorney the same business day.
- Complete contracted deals enter disposition promptly; missing package requirements are visible
  blockers with owners.
- Active buyer inquiries receive an owned response task.
- Closing reconciliation and commission approval occur only after funds and statements agree.

Every active business record must have one accountable owner, one current stage, one next action,
one due time, a last-contact timestamp, and a complete activity history.

## Performance System

### Marketing And Prospecting

- List and campaign cost.
- Attempts, contacts, meaningful conversations, and interested-seller rate.
- DNC, complaint, bad-data, and duplicate rate.
- Cost per warm lead, held appointment, contract, and funded deal.

### Lead Management

- Warm-response time.
- Contact and qualification rate.
- Qualified appointments set and held.
- No-show, nurture, and neglected-lead rate.
- Held-appointment-to-contract conversion by source.

### Acquisitions

- Appointments held, offers made, and contracts signed.
- Offer-to-contract and held-appointment-to-contract conversion.
- Contract cancellation, approved-ceiling exception, and follow-up conversion.
- Average assignment fee and Adjusted Deal Margin.

### Transactions And Dispositions

- Contract-to-package, package-to-buyer, and contract-to-close time.
- Buyer responses, showings, offers, proof, deposits, and backup coverage.
- Assignment spread, buyer fallout, title delay, and contract cancellation.
- Human-led versus AI-assisted performance and cost.

### Finance And Executive

- Collected revenue, acquisition cost, commissions, ordinary overhead, and company profit.
- Net margin against the 30% target.
- Cash forecast, taxes, reserves, distributions, and unpaid obligations.
- Profit and conversion by campaign, source, market, role, and operating mode.

### AI

- Acceptance, correction, rejection, evidence coverage, and failure rates.
- Latency, cost, time saved, compliance blocks, and escalations.
- Business outcome compared with an appropriate human or pre-automation baseline.
- Rollback trigger and owner for every external-action pilot.

## Management Cadence

- Daily: urgent leads, appointments, contracts, buyer activity, deadlines, and blocked work.
- Weekly: funnel scorecard, call quality, lead aging, acquisition outcomes, disposition pipeline,
  cash forecast, and AI exceptions.
- Monthly: close the books, approve commissions, reconcile campaign costs, review margin, update
  forecasts, and decide controlled experiments.
- Quarterly: review compensation economics, hiring capacity, agent autonomy, vendor performance,
  market readiness, and legal/compliance policy.

## Expansion Standard

A new state or market is a configured operating unit, not a pipeline toggle. Before launch it needs
approved counties and buy box, economics, contract and disclosure templates, legal review, contact
and recording rules, closing partners, buyer coverage, assigned staff, numbers and messaging
configuration, campaign attribution, and an owner-approved launch checklist.

The CEO should add a dedicated Closer, Transaction Coordinator, or Disposition Manager when role
coverage repeatedly causes missed service standards, constrains funded-deal capacity, or consumes
time required for management and expansion. AI reduces a role's compensation only after the new
operating mode is measured and formally activated.

## Implementation Priority

1. Finish dedicated communications, domain, email, reliability, and access controls.
2. Complete campaign/list prospecting, Lead Manager handoff, appointments, and notifications.
3. Validate underwriting and offer approval against real deals.
4. Complete contracts, documents, transaction coordination, and closing evidence.
5. Complete buyer matching and human-led dispositions.
6. Complete reconciliation, compensation, accounting, and the 30% margin dashboard.
7. Productionize Call Intelligence, Lead Management, and Appointment Preparation agents.
8. Introduce the Disposition Agent in measured human-led, AI-operated, and oversight modes.
9. Add Transaction, Finance, Marketing, and Executive agents with narrow approvals.
10. Expand geography only through the market launch standard.
