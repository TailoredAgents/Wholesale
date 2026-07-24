# Stonegate Product Finishing Roadmap

Last updated: July 24, 2026

## Purpose

This is the canonical sequence for taking Stonegate from a feature-complete manual operating
system to a production-proven business platform.

The original product phases remain the record of what was built. This roadmap covers what is
still required: production verification, company configuration, provider activation, real-world
validation, and controlled AI pilots.

`CURRENT_STATE.md` remains the source of truth for what exists today. Do not mark a finishing phase
complete merely because code exists. The exit criteria must be demonstrated in production or a
controlled production-like test.

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
- Object storage, e-signature, buyer delivery, accounting, and advertising integrations.
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

| Phase | Name | Main result |
| --- | --- | --- |
| F1 | Production Safety Closeout | Recoverable, monitored, access-controlled production |
| F2 | Company Configuration And Role Acceptance | Real staff can execute their jobs correctly |
| F3 | Compliance And Operating Policy | Legal, outreach, recording, and retention rules are approved |
| F4 | Documents, Contracts, And Closing | Secure files and e-signature support live transactions |
| F5 | Buyers And Disposition Readiness | Buyer data, packages, offers, and selection are production-ready |
| F6 | Finance And Marketing Connections | Closing economics and attribution reach external ledgers |
| F7 | Underwriting Calibration And Market Proof | Offer guidance is measured against verified outcomes |
| F8 | Resend Operational Email | Two-way email works inside the shared Inbox |
| F9 | Twilio Communications Acceptance | Dedicated SMS and Voice work end to end |
| F10 | AI Production Pilots And Controlled Automation | Copilots are proven before narrow automation |

## Phase F1: Production Safety Closeout

Goal: Make production observable, recoverable, and safe before broad employee use.

Work:

- Rotate every credential that has been exposed outside its intended secret store.
- Require MFA for Owner, Administrator, Finance, and other privileged accounts.
- Configure an external uptime check for `/ready`.
- Configure an owner-controlled failure alert destination.
- Select and connect production error monitoring.
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
- No known exposed credential remains active.

## Phase F2: Company Configuration And Role Acceptance

Goal: Replace demonstration assumptions with Stonegate's real operating data.

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

Goal: Make cold calling, seller communication, and recording operationally defensible.

Work:

- Obtain National DNC access or select an approved screening provider.
- Define recurring DNC refresh and retained evidence procedures.
- Approve company suppression, opt-out, complaint, and wrong-number procedures.
- Obtain legal review for Georgia calling, SMS, email, recording, contracts, and disclosures.
- Approve calling hours, timezone handling, caller identification, and scripts.
- Approve recording disclosure, retention, access, and deletion policy.
- Train VAs and managers; retain training and monitoring records.
- Test that blocked records cannot enter calling batches or external delivery.

Exit criteria:

- A named owner approves every communication policy.
- DNC evidence is current and repeatable.
- Recording is enabled only after disclosure and retention approval.
- Controlled policy-blocked cases fail safely across calls, SMS, and email.

## Phase F4: Documents, Contracts, And Closing

Goal: Run a real contract-to-funding workflow with secure files and provider evidence.

Work:

- Select private S3-compatible object storage.
- Migrate recordings, photographs, reports, proof-of-funds, and contracts behind authenticated
  object access.
- Add malware scanning, retention, checksums, signed downloads, and deletion controls.
- Select and integrate an e-signature provider.
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

## Phase F6: Finance And Marketing Connections

Goal: Move approved business outcomes to the accounting and advertising systems without creating
another source of truth.

Work:

- Prove the existing funded-deal reconciliation with real or redacted closings.
- Add payment-state progression.
- Connect QuickBooks Online through an approval-gated adapter.
- Reconcile exported and provider-posted accounting entries.
- Define consent and attribution rules for downstream advertising events.
- Add Google Ads and Meta conversion delivery with hashing, retries, idempotency, and audit events.
- Keep budgets, campaigns, payments, compensation, and final accounting human-approved.

Exit criteria:

- One approved funded deal reconciles with QuickBooks without duplicate posting.
- Qualified lead, appointment, contract, and funded outcomes can be delivered and audited.
- Provider failures are retryable and do not alter Stonegate's source records.

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
- Activate only communication workflows approved in Phase F3.

Exit criteria:

- Controlled SMS and Voice acceptance suites pass.
- Every communication attaches to the correct conversation.
- Opt-outs and suppression cannot be bypassed.
- Provider failure produces a visible and recoverable task or event.
- Recording remains disabled unless the Phase F3 disclosure and retention policy is approved.

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
- Complete F3 policy work before activating any communication provider.
- F4 must pass before document-dependent Transaction Copilot automation.
- F5 prepares buyer operations; live email delivery waits for F8 and SMS delivery waits for F9.
- F6 requires stable funded-deal reconciliation.
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
6. Underwriting performance is measured against verified outcomes.
7. Copilots have passed supervised pilots before receiving any increased authority.
8. The Owner has a documented daily, weekly, monthly, and emergency operating process.
