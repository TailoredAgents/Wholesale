# Roadmap

Last updated: July 21, 2026

`CURRENT_STATE.md` is the source of truth for what exists today. This roadmap keeps internal
development moving while Twilio, domain, and email setup are pending.
`OPERATING_MODEL.md` defines the business roles, handoffs, compensation policy, AI portfolio, and
operating standards that these phases implement.

## Current Gate: Integration Closeout

Status: Waiting on external A2P review.

The application code for SMS, Voice, recording/transcription, AI call review, and Google Workspace
email is implemented. Production setup is intentionally paused while Stonegate's dedicated A2P
Campaign is reviewed.

Resume checklist:

- A2P Campaign shows approved or verified.
- New Stonegate SMS number is attached only to the new Stonegate Messaging Service.
- Final SMS sender and Messaging Service SID are entered in Render.
- Voice credentials and TwiML App are configured.
- Custom domain is selected and connected.
- Google Workspace domain and operational mailboxes exist.

## Phase 1: Reliability, Security, And Operations

Status: Implementation complete; production operator checks remain.

Goal: Establish a production baseline before adding more business complexity.

Deliver:

- Durable worker heartbeat, grouped failure tracking, isolated operation retries, and readiness.
- Threshold-based alert webhooks and an external `/ready` monitoring target.
- Guarded database backup and isolated restore-verification scripts.
- Deterministic synthetic demo workspace and provider-safe SMS/email simulators.
- Production smoke-test script and CI shell validation.
- User deactivation coverage and production simulation safeguards.
- Detailed operator procedures in `PHASE_1_RELIABILITY.md`.

Exit criteria:

- Code and automated safeguards are complete.
- The owner configures an alert destination and external uptime monitor.
- The first isolated restore drill and production access-revocation check are recorded.

## Phase 2: Acquisition Workflow Completion (Implemented July 21, 2026)

Goal: Make the OS complete for the owner, Lead Manager, Acquisitions Closer, and VA calling team.

Deliver:

- User and team administration for owner, Lead Manager, Acquisitions Closer, disposition, and VA
  roles.
- Calling-list assignment and list-level progress.
- Appointment reschedule, cancel, no-show, completed, and outcome workflows.
- Internal appointment calendar and reminders.
- Persistent user/team saved views.
- Duplicate review, merge, and merge audit.
- Notifications for new leads, handoffs, appointments, overdue tasks, and seller replies.
- Follow-up plans and approval-based sequences.
- Mobile inbox and lead-workspace refinement.

Exit criteria:

- A VA can prospect and hand off without seeing restricted business data.
- The Lead Manager can qualify and book; the Acquisitions Closer can work every accepted
  appointment through offer preparation and outcome.
- The owner can monitor workload, SLA, and handoff quality without manual spreadsheets.

Implementation note: Stonegate is the calendar system of record. It does not require Google
Calendar or another external calendar provider.

## Phase 3: Underwriting Validation And Offer Workflow

Goal: Turn comping into repeatable, explainable offer preparation.

Deliver:

- [Complete] Comp candidate review UI with include, exclude, documented reason, bounded manual
  weighting, immutable recalculation versions, and audit history.
- [Complete] RentCast address validation, canonical duplicate keys, provider match scoring,
  non-owner property-fact provenance, and explicit subject-fact normalization.
- Optional ATTOM or MLS/RESO enrichment behind the property-data adapter.
- [Complete] Market-specific calibration cases, immutable prediction snapshots, verified outcome
  history, and ARV/repair/disposition backtesting metrics.
- [Complete] Repair scope presets, immutable contractor/walkthrough/internal estimates, and
  underwriting version comparison.
- [Complete] Immutable offer-ceiling approval requests, bounded negotiation ladders, supersession,
  stale-version protection, and accountable decisions.
- Seller-meeting brief, objection preparation, and approved price discussion notes.
- Final investor and client report polish with Stonegate's custom domain and contact information.

Exit criteria:

- Every ARV and offer range can be explained from retained data and adjustments.
- Material assumptions have an owner and timestamp.
- No AI-generated value bypasses human comp review or offer approval.

Implementation note: the first four Phase 3 increments are complete. Reviews use the retained
provider snapshot, require a decision for every displayed sale, constrain reviewer weighting to
50-150% of the engine match weight, and create a new linked underwriting analysis rather than
changing the source version. Address validation preserves the staff-entered address, stores the
provider result separately, invalidates stale confirmation after an address edit, and marks
mismatches for review without blocking calculations or reports. Calibration compares the exact
saved prediction with later expert, appraisal, resale, or verified-sale evidence. It reports
directional bias, median absolute error, range coverage, and optional repair/disposition error by
market. Formula review requires at least 50 cases and never changes formulas automatically.
Repair presets populate an editable itemized scope, while saved estimates preserve contractor,
walkthrough, or internal evidence as immutable records. Analyses snapshot the selected estimate,
and the lead page compares saved ARV, repair, disposition, seller-ceiling, and opening values.
Offer approvals snapshot the exact underwriting version and its economics. Opening, target,
stretch, and walk-away values must remain ordered beneath the calculated seller ceiling. New
requests cancel older pending plans, newer underwriting blocks stale approval, and authorized
decisions update the plan, version, lead stage, activity timeline, and audit history together.

## Phase 4: Contracts And Transaction Coordination

Goal: Run an accepted offer through closing without outside checklists.

Deliver:

- Contract and addendum template records.
- Offer and contract approval workflow.
- E-signature provider adapter.
- Secure object storage and document permissions.
- Checklist completion, ownership, due dates, dependencies, and escalation.
- Earnest money, inspection, title, payoff, closing, and assignment deadline tracking.
- Closing attorney/title communication timeline.

Exit criteria:

- An approved offer can become a signed contract and completed transaction with a complete audit
  trail.

## Phase 5: Buyers And Dispositions

Goal: Match contracted deals to qualified buyers and manage assignment outcomes.

Deliver:

- Buyer proof-of-funds documents and expiration.
- Market, property, price, strategy, and volume criteria.
- Ranked buyer matching with human review.
- Deal room and approved marketing package.
- Controlled email/SMS deal distribution.
- Buyer response, showing, offer, deposit, selection, and backup-buyer workflows.
- Disposition performance and buyer reliability reporting.
- Versioned human-led, AI-operated/human-managed, and human-oversight disposition modes without
  retroactive compensation changes.

Exit criteria:

- Stonegate can move a contract from deal approval to selected buyer without a separate buyer CRM.

## Phase 6: Finance, Compensation, And Accounting

Goal: Close the loop from lead source to collected cash.

Deliver:

- Payment and collection status.
- Monthly close and reconciliation.
- Compensation approvals and payout status.
- Adjusted Deal Margin, CEO Management, role credit, plan version, and 30% company-margin controls
  defined by the operating model.
- QuickBooks Online integration or controlled export.
- Marketing spend imports.
- Deal-level profitability and cash forecasting.
- Owner P&L, revenue-by-source, and advertising-percentage reporting.

Exit criteria:

- Every collected dollar ties to a transaction, source, deductions, compensation, and accounting
  record.

## Phase 7: AI Agent Production Foundation

Goal: Move from AI-capable records to evaluated, permissioned agents.

Deliver:

- Versioned evaluation datasets for intake, follow-up, calls, underwriting, and compliance.
- Agent runner with dry-run mode, retries, budgets, and trace review.
- Intake summarizer and qualification-gap agent.
- Follow-up draft agent with human approval.
- Speed-to-lead and missed-reply monitor.
- Underwriting research assistant that cannot set approved values.
- Compliance preflight agent that cannot override deterministic rules.

Exit criteria:

- Every agent action is attributable to a prompt, model, tool permission, evidence, cost, and human
  decision.
- No external action is enabled without an explicit pilot decision.

## Phase 8: Controlled Automation And Team Intelligence

Goal: Automate repetitive low-risk work after measured accuracy.

Deliver:

- Approval-based follow-up sequences.
- Call coaching and missed-opportunity detection.
- AI-proposed CRM field updates with evidence.
- Appointment reminders and unanswered-message escalation.
- VA and acquisitions quality dashboards.
- Low-risk automation pilots only after documented evaluation thresholds are met.
- Separate Smartlead-style cold email integration if Stonegate approves that channel and its
  compliance process.

Exit criteria:

- Automation saves measurable staff time without increasing complaints, corrections, missed
  follow-up, or compliance failures.

## Phase 9: Growth, Optimization, And Premium Product Quality

Goal: Improve conversion, operating efficiency, and polish after core workflows are dependable.

Deliver:

- Additional seller-situation and campaign landing pages.
- Branded photography, local proof, testimonials, and trust assets as they become available.
- Google Ads offline conversion delivery and Meta Conversions API.
- A/B testing with one controlled variable at a time.
- Page-speed, accessibility, mobile, and Core Web Vitals passes.
- OS information-density, keyboard flow, empty-state, and responsive refinement.
- Executive reporting for funnel, team, deal, finance, marketing, and AI performance.

Exit criteria:

- Public conversion and internal workflow changes are driven by measured outcomes.
- The platform meets Stonegate's premium quality bar on desktop and mobile.

## Phase 10: Multi-Market Expansion And Operating Maturity

Goal: Expand beyond the first Georgia market without losing financial or operating control.

Deliver:

- Versioned market profiles for pricing rules, disclosures, attorneys, vendors, and service areas.
- Territory launch checklist, staffing capacity, and campaign budget controls.
- Market-level conversion, margin, cycle-time, and compliance reporting.
- Permissioned regional management and workload routing.
- Disaster recovery review, quarterly restore drills, access reviews, and automation revalidation.

Exit criteria:

- A new market can be launched from an approved checklist without changing global code or silently
  inheriting Georgia-specific assumptions.
- Company and market-level profitability remain separately explainable.

## Ordering Rules

- Complete Phase 1 operator checks before broad team onboarding.
- Resume the external integration gate when providers are ready; it does not block Phase 2.
- Complete acquisition and underwriting controls before contract automation.
- Complete transactional records before accounting synchronization.
- Complete evaluation and approval infrastructure before AI autonomy.

## Explicitly Deferred

- Fully autonomous seller negotiation.
- AI authority to approve offers, contracts, buyers, payments, or compensation.
- A custom carrier, email-delivery network, e-signature system, or accounting ledger.
- Cold SMS to purchased, scraped, transferred, or non-consented leads.
