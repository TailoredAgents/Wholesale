# Stonegate Product Finishing Roadmap

Last updated: July 26, 2026

## Purpose

This is the canonical sequence for taking Stonegate from a feature-complete manual operating
system to a production-proven business platform.

The original product phases remain the record of what was built. This roadmap covers what is
still required: production verification, company configuration, provider activation, real-world
validation, internal accounting, and controlled AI pilots.

`CURRENT_STATE.md` remains the source of truth for what exists today. Do not mark a finishing phase
complete merely because code exists. The exit criteria must be demonstrated in production or a
controlled production-like test.

## Scope Rules

This roadmap extends the Stonegate platform already in production. It does not authorize parallel
versions of the CRM, Inbox, calendar, buyer database, Finance area, or AI control plane.

- **Acceptance** means proving and configuring existing code for real operations.
- **Extension** means adding records and workflows to an existing Stonegate module.
- **Integration** means connecting a provider through an adapter while Stonegate retains its own
  normalized records, permissions, history, and audit trail.
- **New subsystem** means a genuinely new internal capability, such as the double-entry accounting
  ledger in F6. It must reference existing source records instead of copying or replacing them.
- PostgreSQL remains the platform database. Existing lead, deal, reconciliation, compensation,
  and marketing records remain the operational evidence; posted journal entries become the
  accounting authority for financial statements.
- Every generated or provider-backed record requires source references, organization scope,
  permissions, audit history, and duplicate protection.
- The existing governed AI runtime serves every Copilot. No phase creates a second AI system.
- Every provider decision and runtime credential name must be reflected in
  `PRODUCTION_CREDENTIALS_CHECKLIST.md`. Actual secret values never belong in git.

## Current Boundary

Already built:

- Public seller website and consented intake.
- CRM, campaigns, prospecting, Lead Desk, Inbox, tasks, and calendar.
- Field acquisitions, underwriting, offer governance, reports, and negotiation records.
- Manual contract-to-close, buyer, disposition, reconciliation, finance, and marketing workflows.
- Eight staff-facing copilots and the governed AI control plane.

Still required:

- Production safety and operator verification.
- Real Stonegate users, policies, scripts, templates, territories, and counterparties.
- Resend operational email migration.
- Dedicated Twilio SMS and Voice acceptance.
- Outreach, recording, and market compliance approval.
- Object storage, e-signature, buyer delivery, the internal accounting ledger, and advertising
  integrations.
- Underwriting calibration using verified outcomes.
- Redacted AI model replay and measured supervised pilots.

## Provider Decision

Resend is the approved operational email provider. Google Workspace and Gmail OAuth will not be
activated.

The existing Gmail implementation is disabled legacy code and must be replaced deliberately.
Stonegate will use:

- Company-controlled sender aliases.
- Resend Email API for outbound operational messages.
- Resend Receiving and signed webhooks for inbound replies.
- Stonegate's shared Inbox as the staff mailbox experience.
- PostgreSQL as the communication source of truth.

Cold email remains a separate future system. It must not use the operational seller-email domain,
sender reputation, or consent assumptions.

## Phase Summary

| Phase | Name | Build type | Main result |
| --- | --- | --- | --- |
| F1 | Production Safety Closeout | Acceptance and upgrade | Recoverable, monitored, access-controlled production |
| F2 | Company Configuration And Role Acceptance | Configuration and acceptance | Real staff can execute their jobs correctly |
| F3 | Compliance And Operating Policy | Deferred external policy | No new application-level communication gates |
| F4 | Documents, Contracts, And Closing | Existing workflow extension plus integrations | Secure files and e-signature support live transactions |
| F5 | Buyers And Disposition Readiness | Existing module extension plus buyer-data integration | Buyer data, packages, offers, and selection are production-ready |
| F6 | Stonegate Accounting And Marketing Measurement | New accounting subsystem plus existing-module extensions | Complete internal books and audited advertising attribution |
| F7 | Underwriting Calibration And Market Proof | Existing workflow calibration | Offer guidance is measured against verified outcomes |
| F8 | Resend Operational Email | Existing Inbox provider replacement | Two-way email works inside the shared Inbox |
| F9 | Twilio Communications Acceptance | Existing communications activation | Dedicated SMS and Voice work end to end |
| F10 | AI Production Pilots And Controlled Automation | Existing AI-system validation and promotion | Copilots are proven before narrow automation |

## Phase F1: Production Safety Closeout

Goal: Make production observable, recoverable, and safe before broad employee use.

Owner-directed scope exception:

- Credential rotation, MFA rollout, and secret-security remediation are intentionally excluded
  from the current F1 execution. They remain known risks and are not implied complete when F1
  reliability acceptance is complete.

Work:

- Activate the scheduled GitHub production-readiness check for `/ready` and required public pages.
- Configure an owner-controlled failure alert destination.
- Connect the implemented Sentry error monitoring for the web, API, and worker.
- Run and record an isolated database restore drill.
- Run and record employee access-revocation and record-reassignment checks.
- Verify worker heartbeat, retries, and failure visibility.
- Run deployment smoke tests against the branded domain and Render fallbacks.
- Record the production environment inventory without storing secret values in git.

Exit criteria:

- A backup has been restored into an isolated database successfully.
- An owner receives a controlled readiness or worker alert.
- A deactivated employee immediately loses access.
- The branded website, OS, API, worker, database, and Key Value service pass the production
  checklist.
- Web, API, and worker errors reach the approved Sentry projects without default PII collection.

## Phase F2: Company Configuration And Role Acceptance

Goal: Replace demonstration assumptions with Stonegate's real operating data.

Implementation checkpoint, July 24, 2026:

- The existing Operating Model now includes standard operating seats, named primary and backup
  coverage, partner verification, readiness checks, staff manual assignments, employee workspace
  test evidence, manager approval, and complete audit events.
- Every user has a restricted **My Setup** workspace. Owners manage the process from
  **Operating Model > Company setup**.
- This is the configuration and acceptance layer for existing users, roles, markets, scripts,
  compensation, closer capacity, and buyers. It does not duplicate those systems.
- Operational acceptance remains ongoing as real staff and Georgia counterparties are hired and
  approved.

Work:

- Create individual users for the Owner, Lead Manager, closers, VAs, dispositions, transaction
  coordination, finance, and marketing as those people are hired.
- Configure teams, ownership rules, watchers, and workload routing.
- Activate the approved compensation plan and role-credit rules.
- Configure Georgia markets, territories, closer capacity, work hours, and unavailable time.
- Approve VA and Lead Manager scripts.
- Load attorney-reviewed templates and approved operating knowledge.
- Add closing attorneys, title companies, and other standard counterparties.
- Seed the initial verified buyer list and proof-of-funds review process.
- Complete role-based acceptance testing using restricted accounts.
- Write staff manuals for Owner, VA, Closer, Transaction Coordinator, Dispositions, and Finance.

Exit criteria:

- Every active employee has an individual login and only the access required for the job.
- A controlled lead can move through every staff handoff without Owner-only workarounds.
- Compensation, territory, script, capacity, and assignment policies are approved and active.
- Each role owner signs off on their daily workspace and manual.

## Phase F3: Compliance And Operating Policy

Status: Application-level F3 restrictions were removed at the Owner's direction on July 24, 2026.

Current product boundary:

- No DNC evidence, policy approval, training acknowledgment, email permission, or recording-policy
  approval is required by the application.
- Blank imported DNC values do not block imports or calling batches.
- The temporary Compliance workspace and its approval APIs are not part of the product.
- Existing seller opt-outs, explicit do-not-contact values, company suppression, invalid contact
  data, provider configuration, and provider delivery failures still behave normally.

Any future policy tooling must be requested explicitly and should default to advisory reporting
rather than silently blocking operations.

## Phase F4: Documents, Contracts, And Closing

Goal: Run a real contract-to-funding workflow with secure files and provider evidence.

Implementation checkpoint, July 24, 2026:

- The private storage adapter now covers legal templates, transaction documents, completed signed
  agreements, inspection photographs, and buyer proof-of-funds documents. Existing database files
  remain readable; Cloudflare R2 is the selected production object store.
- SignWell is the selected e-signature provider. Envelope, recipient, webhook, reconciliation,
  completed-PDF, test-mode, and provider evidence are implemented inside the existing transaction
  workflow.
- The Transaction workspace supports owner-driven account verification and webhook registration,
  internal purchase, assignment, and addendum generation, ordered signers, approved-package sending,
  signature status, provider reconciliation, and storage/scan visibility.
- Local simulation and automated provider-connection, webhook, purchase, and assignment tests are
  implemented. R2 credentials, the SignWell API key, attorney-approved templates, and controlled
  production acceptance remain external completion steps.
- See `SIGNWELL_LAUNCH_RUNBOOK.md` for setup and acceptance and
  `SIGNWELL_COUNSEL_BRIEF.md` for the production document specification.

Work:

- Select private S3-compatible object storage. **Selected: Cloudflare R2.**
- Route persistent uploaded photographs, proof-of-funds, legal templates, and contracts behind
  authenticated object access. Keep provider-hosted recordings and generated reports behind their
  existing authenticated endpoints.
- Add malware scanning, retention, checksums, short-lived downloads, and deletion controls.
- Select and integrate an e-signature provider. **Selected: SignWell.**
- Load attorney-approved Georgia purchase and assignment templates.
- Reconcile envelopes, recipients, signatures, final documents, and webhook events.
- Prepare closing-party templates and provider-neutral delivery records; activate delivery in
  Phase F8.
- Run a redacted contract-to-funding simulation.

Exit criteria:

- A contract package is approved, sent, signed, reconciled, and retained without manual status
  fabrication.
- Every material document and signature event has provider evidence.
- Funding remains blocked until the existing checklist and evidence gates pass.

## Phase F5: Buyers And Disposition Readiness

Goal: Turn the internal buyer CRM into an operational deal-placement system.

Status as of July 26, 2026:

- DealMachine is selected and the provider adapter, deal-specific search, scored candidate
  evidence, selective import, contact extraction, cross-run deduplication, and audit history are
  implemented.
- Imported candidates flow into the existing buyer CRM, deterministic match ranking, and
  Dispositions Copilot. No parallel buyer database or second AI system was created.
- Live Georgia API acceptance, initial buyer verification, controlled audience simulation, and a
  funded reconciliation simulation remain before F5 is operationally complete.

Work:

- Select the first buyer acquisition source or API based on cost and coverage.
- Import and deduplicate the initial buyer list.
- Verify criteria, market, capacity, contact permission, and proof of funds.
- Prepare approved buyer-package audiences and provider-neutral delivery records.
- Process manually logged inquiries, showing interest, offers, deposit terms, and opt-outs in one
  case until communication providers activate.
- Test primary and backup buyer selection.
- Run a contract-to-buyer-to-reconciliation simulation.
- Compare human-led and AI-assisted disposition work only after the manual process has volume.

Exit criteria:

- An approved deal package is ready for a controlled buyer audience without bypassing release
  approval.
- Manually logged replies and offers attach to the correct disposition case.
- Proof of funds and selection gates cannot be bypassed.
- A funded simulation reconciles buyer outcome, revenue, deductions, commissions, and company
  margin.

## Phase F6: Stonegate Accounting And Marketing Measurement

Goal: Extend the existing Finance area into Stonegate's internal bookkeeping system and connect
approved funnel outcomes to advertising providers without duplicating operational records.

Starting point:

- Stonegate already records revenue, deal deductions, marketing spend, compensation rules,
  compensation calculations, role credits, deal payouts, funded-deal reconciliation, company
  margin, owner approvals, audit events, and accounting CSV output.
- The existing Finance records are operational deal economics. They are not yet a complete
  accounting ledger because there is no chart of accounts, balanced journal, accounting-period
  close, bank reconciliation, vendor ledger, or complete financial-statement package.
- The existing Finance Copilot already analyzes finance exceptions in draft-only mode. F6 extends
  that same Copilot; it does not add another agent framework.

### F6A: Accounting Policy And Account Structure

- **Implementation status:** Core product work is complete. `/os/finance` now installs one
  organization-scoped accounting profile and versioned wholesaling chart of accounts, exposes the
  unresolved entity and owner-compensation decisions, and preserves an audit history. CPA
  confirmation remains an external acceptance step.
- Have Stonegate's CPA approve the legal entity, tax year, cash or accrual method, opening-balance
  date, retention policy, and treatment of assignment fees, double closes, earnest money, closing
  costs, commissions, contractor labor, software, advertising, owner contributions, and
  distributions.
- Add a versioned chart of accounts with asset, liability, equity, revenue, cost, and expense
  account types.
- Add organization-scoped accounting permissions for preparation, approval, posting, period close,
  reporting, and CPA read-only access.

### F6B: Double-Entry Ledger And Posting Controls

- **Implementation status:** Core product work is complete. Finance now provides monthly
  accounting periods, balanced journal entries and lines, source and evidence references,
  idempotency, dedicated preparation/approval/posting/period permissions, linked reversing
  journals, and auditable period review, close, reopen, and lock transitions. Production opening
  balances and CPA acceptance remain F6E work.
- Add journal entries and journal lines that require total debits to equal total credits.
- Use `draft`, `approved`, `posted`, and `reversed` states. Posted entries are immutable and can
  only be corrected through linked reversing and replacement entries.
- Add source type, source ID, posting-rule version, evidence references, preparer, approver,
  timestamps, and idempotency keys to prevent duplicate posting.
- Add accounting periods with open, review, closed, and locked states. Reopening a closed period
  requires explicit Owner or Finance authority and an audit reason.
- Store money in integer cents and require currency consistency for every journal.

### F6C: Operational Posting Rules

- **Implementation status:** Core product work is complete. Finance now installs ten
  owner-approved, versioned posting rules; exposes a deterministic source work queue; proves
  funded revenue and commissions against approved reconciliation, closing statement, and funding
  confirmation; and creates one source-linked balanced draft per accounting event. Vendor
  payables, contractor payables, reimbursements, owner distributions, and commission payouts use
  explicit payment states and evidence. Generated entries remain drafts until separate journal
  approval and posting. Production funded-deal acceptance and CPA rule approval remain external
  acceptance steps.
- Prove the existing funded-deal reconciliation with real or redacted closing statements before
  allowing it to draft accounting entries.
- Draft balanced entries from approved funded-deal reconciliations without copying the lead,
  transaction, payout, or compensation record.
- Draft entries for collected assignment revenue, double-close economics, deal deductions,
  approved commissions, marketing spend, software, contractor labor, owner activity, and other
  approved business expenses.
- Add payment-state progression for receivables, payables, commissions, reimbursements, and
  distributions.
- Require human review of every new posting rule and every material exception.

Implemented posting coverage:

- Collected assignment revenue, double-close proceeds, and other operating revenue.
- Paid deal deductions with category-aware account mapping.
- Advertising, lead data, software, hosting, subscription, VA, contractor, and other marketing
  spend with source-aware account mapping.
- Approved commission accrual and separate commission settlement.
- Vendor, contractor, and reimbursement accrual and settlement.
- Owner distributions recorded as equity activity rather than operating expense.
- Source fingerprints and unique source-purpose links that surface changed records as exceptions
  instead of preparing a second journal.

### F6D: Banking, Vendors, And Evidence

- **Implementation status:** Core F6D product work is complete. Finance uses the shared
  business-counterparty identity for organization-scoped vendor profiles, itemized bills,
  tax-reportable and W-9 lifecycle status, private source documents, year-to-date vendor payments,
  and bill approval. It also provides provider-free CSV statement preview and import, private
  statement retention, duplicate prevention, manual posted-journal matching, and balance-controlled
  bank reconciliation. An approved bill creates the existing financial obligation and flows
  through F6C posting and payment control; it does not create a parallel payable ledger. W-9 files
  are sensitive private documents with audited access, and tax identifiers are never copied into
  ordinary fields.
- Add bank and credit-card accounts, statement imports, normalized transactions, matching,
  reconciliation sessions, statement balances, and unexplained-difference tracking.
- Start with secure CSV/OFX statement import. Add a read-only bank-feed adapter later only if
  operating volume justifies its cost and support burden.
- Add vendors and contractors, bills, receipts, closing statements, payment evidence, W-9
  collection status, and reportable-payment tracking.
- Store sensitive tax documents in the private object-storage system from F4 with restricted
  access; do not place tax identifiers in ordinary notes or logs.
- Do not initiate bank transfers, payroll, tax payments, or card payments in the initial ledger
  release.

F6D1 implemented workflow:

- Add a vendor, contractor, closing service, funding partner, or other service provider without
  duplicating an existing business counterparty.
- Track payment terms, default account coding, tax-reportable status, and requested, received,
  verified, or not-required W-9 state.
- Upload invoices, receipts, W-9s, payment evidence, closing statements, contracts, and related
  private evidence with checksum, malware-scan state, retention, and access auditing.
- Enter one or more coded bill lines. Approval creates one source-linked payable; settlement is
  recorded only after payment occurs outside Stonegate.
- Draft itemized accrual journals from bill lines and preserve document evidence through accrual
  and settlement.

F6D2 implemented workflow:

- Add company bank and credit-card accounts using a label and optional last four digits only.
- Preview a CSV statement with explicit date, description, amount, balance, and transaction-ID
  column mappings before importing it. The original CSV is retained as private evidence.
- Block an exact duplicate statement file and row-level duplicate transactions.
- Match cleared bank lines manually to exactly one existing posted operating-cash journal, or mark a
  non-operating line ignored with an audit reason.
- Prepare and approve a reconciliation only after every included line is resolved and the statement
  closing balance equals opening balance plus imported activity. No provider credentials, bank
  login, payment initiation, or automatic match decisions are included.

### F6E: Reports, Close, And CPA Handoff

- **Implementation status:** Core product work is complete. `/os/finance` now produces
  date-controlled Profit and Loss, Balance Sheet, Cash Flow, Trial Balance, and General Ledger
  reports exclusively from posted journals. It also provides receivable, payable, commission,
  payment-history, and deal-profitability schedules; a close-readiness checklist; and an
  authenticated CPA ZIP package containing the supporting report files. Existing period controls
  handle review, close, reopen, and year-end lock. Opening balances and adjusting entries use the
  same reviewed manual-journal lifecycle instead of a separate balance store. A real month close,
  opening-balance acceptance, and report-package approval by Stonegate's CPA remain external
  acceptance steps.
- Add Profit And Loss, Balance Sheet, Cash Flow, Trial Balance, General Ledger, accounts
  receivable, accounts payable, commission payable, vendor-payment, and deal-profitability reports.
- Make every report drillable to journal lines, source records, approvals, and supporting
  documents.
- Add opening balances, month-end checklist, reconciliation signoff, adjusting entries, period
  close, year-end lock, and a complete CPA export package.
- Keep optional generic exports so Stonegate can work with tax preparation or outside accounting
  tools without making QuickBooks, Xero, or another ledger the source of truth.

F6E implemented workflow:

- Select a statement start and end date. Reports include posted journal activity only; drafts and
  approvals remain visible as close blockers.
- Drill from statements into account totals and the chronological journal-line ledger with source
  IDs and evidence counts.
- Review pending revenue as receivables, approved obligations and commissions as payables,
  completed settlements as payment history, and deal-coded journals as deal profitability.
- Resolve unfinished journals, unmatched statement lines, missing reconciliations, and period
  status before close. Missing evidence remains a visible warning.
- Download one CPA archive containing a manifest, statements, trial balance, general ledger,
  receivables, payables, payments, and deal-profitability schedules.

### F6F: Finance And Accounting Copilot

- **Implementation status:** Core product work is complete. The existing Finance Copilot now reads
  the Stonegate ledger, financial statements, posting queue, bank-statement workspace, close
  checklist, and tax-review sources. It produces evidence-linked, review-only classification,
  journal, bank-match, variance, and close-readiness guidance. A 60-case Finance evaluation
  dataset and 30-day quality, latency, cost, blocked-output, correction, and rejection metrics are
  included. Production model replay, supervised use on real periods, and CPA review remain
  acceptance steps.
- Extend the existing Finance Copilot to suggest account classifications, draft balanced journal
  entries, propose transaction matches, identify duplicate or missing records, explain variances,
  and prepare month-end and CPA review checklists.
- Keep the Copilot embedded in the existing `/os/finance` workspace and powered by the existing AI
  control plane, model runner, review records, budgets, and shutdown controls.
- Require citations to the exact source records, journal lines, statements, and evidence used.
- Measure classification accuracy, reconciliation accuracy, unsupported claims, correction rate,
  latency, cost, and time saved through the existing AI evaluation and review system.
- The Copilot cannot approve or post journals, change accounting policy, close or reopen periods,
  approve compensation, classify taxes finally, move money, file returns, or submit regulatory
  forms.
- Keep Tax and Deductions as a specialist capability inside the existing Finance Copilot. It may
  review source records, propose expense, inventory, capitalized-cost, and owner-activity
  classifications, identify missing business purpose or evidence, and prepare a professional
  review package. It remains draft-only and cannot promise deductibility, file returns, submit
  elections, alter source records, or post ledger entries.

### F6G: Marketing Measurement

- **Implemented:** Stonegate uses a versioned first-party measurement policy and last eligible
  platform click within a 90-day window. Google and Meta are evaluated independently.
- **Implemented:** Qualified lead, appointment scheduled, contract signed, and funded deal events
  are prepared from existing CRM records. Stable event keys prevent duplicate provider outcomes.
- **Implemented:** Google Data Manager and Meta Conversions API adapters use normalized SHA-256
  contact identifiers, provider-specific click IDs, retries, terminal failure states, and an audit
  record for every attempt.
- **Implemented:** The Marketing workspace shows provider readiness, credential blockers, policy,
  queue health, event history, and manual prepare/process controls.
- External delivery remains intentionally disabled until Stonegate configures the ad accounts,
  conversion actions, credentials, and completes controlled provider acceptance.
- Keep budgets, campaigns, payments, compensation, accounting finalization, and published
  advertising changes human-approved.

Exit criteria:

- The CPA has approved the accounting policy, opening balances, chart of accounts, posting rules,
  month-end process, and report package.
- Every posted journal is balanced, source-linked, auditable, and immutable.
- One approved funded deal produces exactly one reviewed accounting result without duplicate
  revenue, deduction, commission, or payout posting.
- One bank statement reconciles to zero unexplained difference, with exceptions visibly retained.
- Profit And Loss, Balance Sheet, Cash Flow, Trial Balance, and General Ledger agree for the same
  closed period.
- The Finance and Accounting Copilot passes its evaluation set and remains unable to post, close,
  pay, or file.
- Qualified lead, appointment, contract, and funded outcomes can be delivered to approved
  advertising providers and audited.
- Provider failures are retryable and do not alter Stonegate's operational or accounting source
  records.

## Phase F7: Underwriting Calibration And Market Proof

Goal: Measure whether Stonegate's comps, ARV, repairs, and offer guidance are reliable enough for
real acquisition decisions.

Work:

- Record verified expert reviews, appraisals, resales, and closed outcomes.
- Compare predicted ARV, range coverage, repairs, seller contract, and disposition results.
- Review selected and excluded comps with experienced operators.
- Establish minimum case counts before changing formulas.
- Determine whether RentCast is adequate by Georgia market.
- Add MLS/RESO, ATTOM, or another provider only if measured error or operator time justifies it.
- Finalize investor and seller-report branding and approved language.

Exit criteria:

- Calibration reports contain enough verified cases for the approved review threshold.
- Material bias and failure patterns are documented.
- Formula or provider changes require versioned evidence and human approval.

## Phase F8: Resend Operational Email

Goal: Replace the disabled Gmail/OAuth integration with two-way operational email in Stonegate.

Architecture:

- Use the Resend API for sending.
- Use Resend Receiving for inbound email.
- Verify every webhook signature and deduplicate by event ID.
- Retrieve inbound body, headers, and attachments after the `email.received` event.
- Preserve `Message-ID`, `In-Reply-To`, and `References` evidence for threading.
- Map approved sender and receiving aliases to Stonegate users and conversations.
- Keep signatures and templates in Stonegate.
- Record sent, delivered, delayed, bounced, complained, failed, suppressed, and received events.
- Suppress unsafe recipients after hard bounce, complaint, unsubscribe, or policy block.

Work:

- Decide whether operational mail uses the root domain or a dedicated subdomain.
- Verify SPF and DKIM; add DMARC policy and monitoring.
- Build the Resend adapter and provider-neutral email interface.
- Replace Google OAuth connection screens with owner-managed Stonegate aliases.
- Add signed outbound and inbound webhook routes.
- Add inbound recovery using the Resend received-email list API.
- Add attachments, reply threading, idempotency, retry, and out-of-order event handling.
- Migrate existing email-account records without retaining unused Google credentials.
- Replace Gmail tests, Render variables, UI labels, worker jobs, and runbooks.
- Activate the prepared closing-party and buyer-package email workflows.
- Test using company-controlled addresses before seller or buyer use.

Exit criteria:

- A staff user sends from an approved Stonegate alias inside Inbox.
- The recipient reply returns to the same Stonegate conversation.
- Attachments are available only to authorized users.
- Delivery, delay, bounce, complaint, failure, and suppression states are visible.
- Duplicate and out-of-order webhooks do not duplicate or regress communication state.
- Approved closing-party and buyer-package email attach to the correct business records.
- No Google OAuth secret or Gmail synchronization job is required.

See `RUNBOOKS/resend-email.md`.

## Phase F9: Twilio Communications Acceptance

Goal: Activate Stonegate's dedicated SMS and Voice resources without sharing another business's
campaign, number, or webhook.

Work:

- Complete A2P approval and attach the dedicated SMS number.
- Configure the dedicated Messaging Service, sender, and signed webhook URLs.
- Test outbound, delivered, failed, inbound, `STOP`, `START`, `HELP`, and duplicate callbacks.
- Configure the Voice API key, TwiML App, dedicated Voice number, and browser identity.
- Test browser registration, outbound, inbound, no-answer, missed-call task, and routing.
- Confirm company ownership and reassignment of numbers when staff changes.
- Activate the dedicated communication workflows after provider acceptance testing.

Exit criteria:

- Controlled SMS and Voice acceptance suites pass.
- Every communication attaches to the correct conversation.
- Opt-outs and suppression cannot be bypassed.
- Provider failure produces a visible and recoverable task or event.
- Recording activation is an explicit Owner and provider-configuration decision.

## Phase F10: AI Production Pilots And Controlled Automation

Goal: Prove each Copilot with Stonegate work before granting any internal or external authority.

Work:

- Redact real Lead Manager, call, acquisition, transaction, disposition, finance, marketing, and
  executive examples.
- Complete AI2 executive and role-owner signoff.
- Replay approved cases through the production model route.
- Complete AI3 monitoring, budget, circuit-breaker, and shutdown acceptance.
- Run separate draft-only pilots for each Copilot.
- Measure accuracy, evidence coverage, corrections, critical failures, latency, cost, time saved,
  and business outcomes.
- Promote only narrow, reversible internal actions after explicit approval.
- Keep external actions locked until the exact provider, consent, template, canary, monitoring,
  and rollback gates pass.

Exit criteria:

- Every promoted capability passes its own dataset and supervised pilot.
- Staff can correct, reject, pause, and audit every output.
- No Copilot can approve offers, contracts, buyers, payments, compensation, legal conclusions, or
  suppression overrides.
- AI10 live delivery, if pursued, is implemented as a separately reviewed release for one exact
  action at a time.

## Ordering Rules

- Complete F1 before broad staff onboarding or live AI pilots.
- F2 can run while A2P approval and provider accounts are pending.
- F3 does not block later provider integrations.
- F4 must pass before document-dependent Transaction Copilot automation.
- F5 prepares buyer operations; live email delivery waits for F8 and SMS delivery waits for F9.
- F6 requires stable funded-deal reconciliation and F4 private document storage before retaining
  sensitive accounting evidence. F6A-F6C can begin before live bank or advertising providers.
- F7 begins as soon as verified outcomes exist and continues permanently.
- F8 and F9 intentionally follow the internal operating, compliance, document, buyer, finance, and
  underwriting work.
- F10 uses the completed deterministic workflows; it does not replace them.

## Definition Of Finished

Stonegate is operationally finished for the first Georgia market when:

1. Production can be monitored, restored, and secured.
2. Every active role can complete its workflow with a restricted account.
3. SMS, Voice, and Resend email pass controlled production acceptance.
4. Outreach and recording policies are approved and enforced.
5. Contracts, documents, signatures, buyers, funding, and reconciliation have passed end-to-end
   simulations.
6. Stonegate's internal books have passed a CPA-reviewed month close and bank reconciliation.
7. Underwriting performance is measured against verified outcomes.
8. Copilots have passed supervised pilots before receiving any increased authority.
9. The Owner has a documented daily, weekly, monthly, and emergency operating process.
