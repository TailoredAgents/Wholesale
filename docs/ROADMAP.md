# Roadmap

Last updated: July 20, 2026

`CURRENT_STATE.md` is the source of truth for what exists today. This roadmap defines the build
order after the pending Twilio, domain, and email setup is complete.

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

## Phase 1: Production Integration Closeout

Goal: Make communications and identity infrastructure reliable end to end.

Deliver:

- Activate the approved Stonegate Messaging Service and dedicated SMS number.
- Send immediate enrollment confirmation after website SMS opt-in.
- Verify outbound, inbound, delivery, failure, STOP, START, HELP, and duplicate webhook behavior.
- Finish browser Voice setup and move only the selected Stonegate Voice number's inbound webhook.
- Keep recording disabled until disclosure and operating-state policy are approved.
- Connect the custom domain to Render and preserve the existing Render URLs.
- Update Clerk authorized parties, API CORS origins, Google OAuth redirects, public links, and
  provider callback URLs.
- Configure Google Workspace OAuth and connect the owner mailbox.
- Verify email sending, replies, threading, signatures, templates, attachments, and worker sync.

Exit criteria:

- A consented test seller can move through web form, SMS, call, and email in one conversation.
- STOP blocks every Stonegate user immediately.
- Incoming calls and messages attach once to the correct lead.
- Domain, authentication, and OAuth redirects work without `401`, CORS, or signature errors.
- Another company's numbers, Messaging Service, and webhooks are unchanged.

## Phase 2: Reliability, Security, And Operations

Goal: Establish a production baseline before adding more business complexity.

Deliver:

- Error monitoring, structured alerts, uptime checks, and provider failure dashboards.
- Database backup and restore drill.
- Worker health, retry, dead-letter, and idempotency review.
- Secret inventory and rotation process.
- Owner/admin MFA enforcement and user deactivation test.
- CI review, dependency update policy, and resolution of the local filesystem/tooling stalls.
- Production smoke-test checklist for every deployment.
- Audit-log review tools for communications, recordings, approvals, and financial changes.

Exit criteria:

- Critical failures alert the owner.
- Restore, rollback, and access-revocation procedures are tested.
- No production feature depends on an unmonitored background job.

## Phase 3: Acquisition Workflow Completion

Goal: Make the OS complete for the owner, acquisitions specialist, and VA calling team.

Deliver:

- User and team administration for owner, acquisitions, disposition, and VA roles.
- Calling-list assignment and list-level progress.
- Appointment reschedule, cancel, no-show, completed, and outcome workflows.
- Google Calendar synchronization and reminders.
- Persistent user/team saved views.
- Duplicate review, merge, and merge audit.
- Notifications for new leads, handoffs, appointments, overdue tasks, and seller replies.
- Follow-up plans and approval-based sequences.
- Mobile inbox and lead-workspace refinement.

Exit criteria:

- A VA can prospect and hand off without seeing restricted business data.
- Acquisitions can work every qualified lead through appointment and offer preparation.
- The owner can monitor workload, SLA, and handoff quality without manual spreadsheets.

## Phase 4: Underwriting Validation And Offer Workflow

Goal: Turn comping into repeatable, explainable offer preparation.

Deliver:

- Comp candidate review UI with include, exclude, reason, and manual weighting.
- Address validation and stronger subject-property normalization.
- Optional ATTOM or MLS/RESO enrichment behind the property-data adapter.
- Market-specific calibration datasets and backtesting against known sales.
- Repair scope presets, contractor estimates, and version comparison.
- Offer ceiling approval requests and negotiation scenarios.
- Seller-meeting brief, objection preparation, and approved price discussion notes.
- Final investor and client report polish with Stonegate's custom domain and contact information.

Exit criteria:

- Every ARV and offer range can be explained from retained data and adjustments.
- Material assumptions have an owner and timestamp.
- No AI-generated value bypasses human comp review or offer approval.

## Phase 5: Contracts And Transaction Coordination

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

## Phase 6: Buyers And Dispositions

Goal: Match contracted deals to qualified buyers and manage assignment outcomes.

Deliver:

- Buyer proof-of-funds documents and expiration.
- Market, property, price, strategy, and volume criteria.
- Ranked buyer matching with human review.
- Deal room and approved marketing package.
- Controlled email/SMS deal distribution.
- Buyer response, showing, offer, deposit, selection, and backup-buyer workflows.
- Disposition performance and buyer reliability reporting.

Exit criteria:

- Stonegate can move a contract from deal approval to selected buyer without a separate buyer CRM.

## Phase 7: Finance, Compensation, And Accounting

Goal: Close the loop from lead source to collected cash.

Deliver:

- Payment and collection status.
- Monthly close and reconciliation.
- Compensation approvals and payout status.
- QuickBooks Online integration or controlled export.
- Marketing spend imports.
- Deal-level profitability and cash forecasting.
- Owner P&L, revenue-by-source, and advertising-percentage reporting.

Exit criteria:

- Every collected dollar ties to a transaction, source, deductions, compensation, and accounting
  record.

## Phase 8: AI Agent Production Foundation

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

## Phase 9: Controlled Automation And Team Intelligence

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

## Phase 10: Growth, Optimization, And Premium Product Quality

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

## Ordering Rules

- Complete Phase 1 before enabling live communications.
- Complete the reliability controls in Phase 2 before broad team onboarding.
- Complete acquisition and underwriting controls before contract automation.
- Complete transactional records before accounting synchronization.
- Complete evaluation and approval infrastructure before AI autonomy.

## Explicitly Deferred

- Fully autonomous seller negotiation.
- AI authority to approve offers, contracts, buyers, payments, or compensation.
- A custom carrier, email-delivery network, e-signature system, or accounting ledger.
- Cold SMS to purchased, scraped, transferred, or non-consented leads.
