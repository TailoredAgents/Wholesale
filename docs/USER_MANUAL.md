# Stonegate Operating System User Manual

Last updated: July 24, 2026

## Purpose

This manual explains how Stonegate staff use the public seller website and private Operating
System from initial outreach through funded closing, reconciliation, and management review.

The live web application is:

- Public website: `https://www.stonegatehb.com`
- Private OS: `https://www.stonegatehb.com/os`

The legacy Render URL remains a valid fallback. The `oakwell-*` service names are infrastructure
identifiers for Stonegate, not a second company or workspace.

## Current Release Boundary

The core manual workflow is available:

- Public seller intake and consent evidence.
- Campaigns, imports, screening, calling batches, and VA prospecting.
- Warm handoff, Lead Desk, qualification, tasks, Inbox, and appointments.
- Field preparation, inspections, underwriting, reports, offer approval, and negotiation records.
- Contract and transaction coordination.
- Buyers, dispositions, buyer offers, selection, reconciliation, and accounting export.
- Finance, marketing, operating policy, AI copilots, and AI governance.

The following depend on final provider acceptance or later integrations:

- Dedicated Stonegate Twilio SMS cutover and production acceptance.
- Twilio browser Voice and inbound routing activation.
- Call recording until disclosure and retention policy are approved.
- Resend operational email migration and production acceptance.
- Live buyer campaign delivery.
- E-signature, private object storage, and the complete internal Stonegate Accounting Ledger.
- Autonomous AI external delivery.

When a provider is unavailable, Stonegate records and manual workflows still operate. Do not
interpret a provider-disabled message as lost CRM data.

## Core Rules

1. Every person uses an individual Clerk login. Never share credentials.
2. Leads remain in one Stonegate workspace. Reassign ownership instead of copying records.
3. PostgreSQL records are the source of truth. Text messages, calls, documents, and AI outputs must
   attach to the existing record.
4. Complete the current record before creating a replacement. The intake and import processes
   already detect many duplicates.
5. Human-confirmed facts outrank provider facts. Provider facts outrank AI inference.
6. AI output is a draft or recommendation until a person reviews it.
7. Offers, contracts, buyer selection, funding, commissions, and external automation remain
   human-controlled.
8. Never bypass consent, suppression, Do Not Contact, recording, or contact-hour controls.

## Roles And Access

Navigation is generated from both the user's job role and permissions. Hidden pages are normally
intentional.

| Role | Normal starting workspace | Primary responsibilities |
| --- | --- | --- |
| Owner / Founder / CEO | Dashboard | Full company access, approvals, coverage, policy, finance, marketing, and AI control |
| Administrator | Dashboard | User support, records, audit, and acquisition administration |
| Lead Manager | Dashboard or Lead Desk | Warm response, qualification, nurture, and appointment setting |
| Acquisitions Closer | Dashboard or Field Operations | Meeting preparation, property visit, underwriting review, negotiation, and contract |
| VA Caller | Prospecting | Work assigned screened records, dispositions, callbacks, and warm handoff |
| Dispositions Manager / Rep | Dispositions | Buyer matching, package release preparation, offers, buyer outcome, and backup |
| Transaction Coordinator | Transactions | Contract-to-close checklist, parties, documents, dates, funding, and closing evidence |
| Finance / Accounting | Finance | Revenue, reconciliation, compensation, payment state, and export |
| Marketing Manager | Marketing | Attribution, funnel, source economics, and conversion exports |
| Read-only Partner / Vendor | Transactions | Limited deal records needed for the approved engagement |

The Owner can see all navigation. Restricted users should see only the pages required for their
jobs.

## First Sign-In

1. Open `/os`.
2. Sign in with the Clerk account created for your Stonegate user.
3. Wait for the OS to verify the local role and permissions.
4. Confirm the name and role displayed in the account menu.
5. Confirm the navigation matches the assigned job.

If the screen remains on **Verifying access**, sign out and sign in once. If it persists, the Owner
must confirm that the Clerk email matches an active Stonegate user and that the branded web origin
is present in Clerk authorized parties and API CORS configuration.

## Navigation

The desktop sidebar and mobile navigation drawer use five groups.

### Command

- **Dashboard:** Today's priorities, exceptions, meetings, pipeline pulse, and Executive Copilot.
- **Inbox:** Seller communication timeline and follow-up.
- **Work Queue:** Assigned and overdue actions.
- **Calendar:** Month, week, day, and agenda commitments.

### Acquisitions

- **Operations:** Team capacity and acquisition administration.
- **Campaigns:** Prospect files, screening, costs, and calling batches.
- **Prospecting:** VA calling workbench and handoff.
- **Lead Desk:** Warm-lead acceptance, qualification, follow-up, and Lead Manager Copilot.
- **All Leads:** Searchable seller system of record.
- **Seller Pipeline:** Stage-based acquisition board.
- **Field Operations:** Dispatch, field calendar, meetings, inspections, and closer capacity.

### Deal Flow

- **Underwriting:** Valuation queue, evidence, accuracy, and verified outcomes.
- **Approvals:** Human decisions for governed actions.
- **Transactions:** Seller contract through funded closing.
- **Dispositions:** Deal package, buyers, offers, and reconciliation.
- **Buyers:** Buyer CRM, criteria, proof of funds, and reliability.

### Business

- **Finance:** Revenue, deductions, compensation, margin, and export.
- **Marketing:** Funnel, attribution, source economics, and conversion exports.

### Control

- **My Setup:** Your role manual, workspace test, and manager approval.
- **Operating Model:** Company setup, compensation policy, role credits, history, and market
  launches.
- **AI Control:** Copilots, runtime, automation contracts, evaluations, traces, and governance.

Use the global search for a seller, property, or record. Recent destinations let you return to
records without searching again. On mobile, use the menu button to open the navigation drawer.

### Route Reference

| Workspace | Route |
| --- | --- |
| Dashboard | `/os` |
| Inbox | `/os/inbox` |
| Work Queue | `/os/tasks` |
| Calendar | `/os/calendar` |
| Operations | `/os/operations` |
| Campaigns | `/os/campaigns` |
| Prospecting | `/os/prospecting` |
| Lead Desk | `/os/lead-manager` |
| All Leads | `/os/leads` |
| Archived Leads | `/os/leads/archived` |
| Seller Pipeline | `/os/pipeline` |
| Field Operations | `/os/field-operations` |
| Underwriting | `/os/underwriting` |
| Approvals | `/os/approvals` |
| Transactions | `/os/transactions` |
| Dispositions | `/os/dispositions` |
| Buyers | `/os/buyers` |
| Finance | `/os/finance` |
| Marketing | `/os/marketing` |
| My Setup | `/os/my-setup` |
| Operating Model | `/os/operating-model` |
| AI Control | `/os/ai` |
| Lead Record | `/os/leads/{lead_id}` |

## Recommended Daily Routine

### Owner

1. Open **Dashboard** and review overdue work, unassigned leads, today's appointments, approvals,
   and the Executive Copilot health summary.
2. Open **Inbox > Needs reply** and confirm no qualified seller is waiting.
3. Open **Work Queue > Overdue** and assign or escalate blocked work.
4. Open **Calendar** and confirm closer capacity and appointment coverage.
5. Open **Approvals** and make only evidence-supported decisions.
6. Review exceptions in **Transactions**, **Dispositions**, and **Finance**.
7. Review **Marketing** source economics at least weekly.

### Lead Manager

1. Open **Lead Desk > Copilot** for priority and neglected-lead signals.
2. Open **Today** and accept new warm handoffs before the SLA expires.
3. Complete **Qualification** using the approved questions.
4. Work **Inbox > Needs reply**.
5. Schedule qualified appointments and create the next dated task for every lead not scheduled.

### Acquisitions Closer

1. Open **Calendar** and **Field Operations > Meetings**.
2. Review the meeting brief, unresolved questions, property facts, and underwriting.
3. Record walkthrough evidence and repairs during the visit.
4. Review the approved offer ceiling before discussing price.
5. Record the meeting and negotiation outcome immediately.

### VA Caller

1. Open **Prospecting > Work queue**.
2. Work one assigned record at a time.
3. Follow the displayed approved script.
4. Record every attempt and outcome.
5. Schedule callbacks only when requested or permitted.
6. Complete all required warm-handoff questions before submitting an interested seller.

### Transaction Coordinator

1. Open **Transactions**.
2. Work overdue and due-next checklist items first.
3. Confirm contract approval, documents, closing parties, earnest money, title, and closing date.
4. Attach evidence before completing required items.
5. Escalate any blocker that threatens closing.

### Dispositions

1. Open **Dispositions** and select the most urgent approved package.
2. Resolve package blockers.
3. Generate and review buyer matches.
4. Verify proof of funds and buyer criteria.
5. Record buyer engagement and offers.
6. Present the primary and backup buyer for human approval.

## End-To-End Operating Workflow

## 1. Public Seller Intake

The seller uses **Get a Cash Offer** on the public site.

The form collects:

- Property address and property type.
- Condition, occupancy, timeline, and seller situation.
- Optional asking price, mortgage, and repair context.
- Name, phone, email, preferred contact method, and permission to contact.
- Separate optional SMS consent.
- Marketing attribution and privacy-safe conversion evidence.

After submission:

1. The API validates the request.
2. Duplicate matching checks contact and property evidence.
3. The system creates or reuses the seller, property, lead, and conversation.
4. Consent and attribution are retained even when the submission matches an existing lead.
5. A speed-to-lead task is created.
6. Staff sees the lead in **All Leads**, **Lead Desk**, **Inbox**, and relevant dashboard queues.

Use the public form to test seller intake with your own controlled information. Do not repeatedly
submit a real seller to diagnose an internal visibility problem.

## 2. Campaign And Prospect Import

Open **Campaigns**. The workspace contains:

- **Performance**
- **Import prospects**
- **Costs**
- **Calling batches**
- **Import history**

### Create And Prepare A Campaign

1. Create or select the campaign.
2. Record the market, list source, channel, budget, dates, and manager.
3. Go to **Import prospects**.
4. Upload the CSV and select or create the vendor-column mapping.
5. Review the preview before saving.
6. Confirm invalid, duplicate, and explicitly suppressed rows are separated from eligible rows.
7. Record list and labor costs in **Costs**.
8. Create a calling batch.
9. Assign the batch or individual entries to VAs.

Blank DNC data does not require review. Explicit Do Not Contact records and seller opt-outs remain
blocked.

## 3. VA Prospecting

Open **Prospecting**. Available views depend on role:

- **Work queue**
- **Call quality**
- **Handoff review** for managers
- **Performance**
- **Caller scripts** for managers

### Work A Record

1. Select the next assigned entry.
2. Review the campaign, seller, property, phone, prior attempts, and compliance state.
3. Start the attempt.
4. Use the exact approved script displayed for the attempt.
5. Record answers as they are provided. Do not invent missing answers.
6. Select the accurate outcome.
7. Save callback timing when applicable.

Typical outcomes include no answer, voicemail, callback requested, follow-up, interested,
appointment set, not interested, wrong number, and Do Not Contact.

### Submit A Warm Handoff

1. Select **Interested** or **Appointment set**.
2. Complete the required ownership, motivation, timeline, condition, occupancy, access, and
   decision-maker questions.
3. Choose the acquisitions owner.
4. Confirm any scheduled appointment.
5. Submit the handoff.

The system creates one CRM lead and retains the campaign, attempt, qualification, conversation,
appointment, and attribution history. The Lead Manager can accept the handoff or return it with a
correction reason.

## 4. Lead Manager Qualification

Open **Lead Desk**. Its views are:

- **Copilot**
- **Today**
- **Qualification**
- **Performance**
- **Standards**

### Accept New Work

1. Open **Today**.
2. Select an unaccepted warm lead.
3. Review handoff evidence and due time.
4. Accept the case.
5. If information is materially wrong, return the handoff from the prospecting review flow with a
   specific correction reason.

### Complete Qualification

1. Open **Qualification**.
2. Select the seller.
3. Ask the approved questions for ownership, decision-makers, motivation, timeline, condition,
   occupancy, price expectation, mortgage or liens, and access.
4. Save confirmed answers.
5. Leave unknown facts unknown rather than guessing.
6. Set the next action and due date.
7. Schedule an appointment when the lead is ready.

### Use The Lead Manager Copilot

1. Open **Copilot**.
2. Select a work item.
3. Generate the draft recommendation.
4. Review evidence, risks, missing facts, next-action proposal, and message draft.
5. Accept, correct, or reject the recommendation.
6. Perform any seller communication yourself through the approved channel.

Copilot review does not automatically change lead fields or send the draft.

## 5. Inbox And Communications

Open **Inbox**. The three-panel layout is:

- Left: conversation views and seller threads.
- Middle: one chronological timeline and channel composer.
- Right: seller, property, assignment, qualification, tasks, notes, and AI summary.

Conversation views:

- **Mine**
- **Unassigned**
- **Team**
- **Needs reply**
- **Appointments**
- **Unread**

Composer modes:

- **SMS**
- **Email**
- **Call**
- **Note**

### Work A Conversation

1. Select the conversation.
2. Read the complete timeline before responding.
3. Confirm the assigned owner, stage, consent, suppression, and next task.
4. Select the correct composer.
5. Write or review the message.
6. Send only when the eligibility indicator allows it.
7. Add internal information as a **Note**, not as a seller message.
8. Reassign the conversation when responsibility changes.
9. Create a dated follow-up before leaving the thread.

The timeline keeps SMS, email, calls, recordings, transcripts, internal notes, and provider events
together. Switching composer modes does not hide prior channels.

For email, select only the Stonegate From address appropriate to the conversation. The system
shows only addresses authorized for your account and applies that address's approved signature.
Delivery status and any retained provider failure appear on the timeline message.

Owners can click the email status control to open **Email administration**:

- **Senders** controls company addresses, owners, teams, signatures, defaults, and direct sender
  or watcher access.
- **Routing** lists inbound email that could not be matched safely. Review the sender and subject,
  select the correct seller conversation, and assign it. Never guess when the correct lead is not
  clear.

If SMS, Voice, or email reports that it is not configured, use the approved manual contact process
and log the communication. Do not put another company's credentials or numbers into Stonegate.

## 6. Work Queue

Open **Work Queue**. Saved views are:

- **All work**
- **My work**
- **Overdue**
- **Due next**
- **Unscheduled**

Use owner and seller filters to narrow the queue. Open the contextual action to go directly to the
conversation, calendar, or lead. Complete a task only after the work is actually done. Bulk
completion requires confirmation and should be used only for a genuinely completed set.

Every active lead should have an owner and a next dated action.

## 7. Calendar And Scheduling

The internal Stonegate calendar is the appointment source of truth. No Google Calendar connection
is required.

Use:

- Month view for capacity and coverage.
- Week view for team planning.
- Day view for execution.
- Agenda view for upcoming commitments.

To schedule:

1. Open the lead in **Lead Desk**, **Inbox**, or **Field Operations > Dispatch**.
2. Select the requested start and end time.
3. Evaluate closer availability, territory, overlap, and travel buffers.
4. Select an eligible closer.
5. Save the appointment.
6. Confirm it appears in Calendar and Field Operations.

Manager override is allowed only for authorized roles and requires a reason.

## 8. Field Operations

Open **Field Operations**. Views are:

- **Dispatch**
- **Calendar**
- **Meetings**
- **Capacity**

### Prepare A Meeting

1. Open **Meetings** and select the appointment.
2. Appointments opened from Calendar or a lead enter **Appointment mode** automatically.
3. Review **Prepare** for seller goals, history, property, unresolved questions, and logistics.
4. Refresh the meeting brief after changing underwriting or comparable sales.
5. Review underwriting and approved authority privately.
6. Generate and review Acquisitions Copilot preparation when useful.

The progress rail shows **Prepare**, **Walkthrough**, **Present**, and **Finish**. Use **Exit focus**
to return to the team meeting queue.

### Record The Walkthrough

1. Open **Walkthrough** on the iPad, phone, or laptop.
2. Confirm occupancy, access, decision-makers, and material property facts.
3. Tap the common property areas, then record condition and notes.
4. Tap common repair categories, enter estimated costs and scope, and capture photographs.
5. Save the draft while walking the property.
6. Submit the inspection when the walkthrough is complete.
7. Transfer confirmed field evidence into a new underwriting draft.

Submitted inspections and evidence are retained. Correct material errors with a new record rather
than silently rewriting historical evidence.

### Present Market Evidence

1. Open **Seller view**.
2. Confirm the address, recorded-sale count, renovated-value range, and evidence confidence.
3. Review the comparable sales with the seller.
4. Select **Present full screen** before handing over or rotating the iPad.
5. Download the **Client PDF** when a printed or retained copy is useful.
6. Exit the presentation before returning to Stonegate's private offer controls.

Seller view does not display Stonegate's repair budget, offer ceiling, opening position,
assignment fee, buyer profit, or concession history.

### Record Negotiation And Outcome

1. Open **Outcome** after leaving the seller presentation.
2. Confirm the current approved offer authority.
3. Record objections, seller counters, Stonegate discussions, and outcome.
4. Request approval before exceeding the current ceiling.
5. Save the appointment outcome and next action.

The Copilot may prepare questions and follow-up drafts. It cannot present or change a binding
offer.

## 9. All Leads, Pipeline, And Lead Record

### All Leads

Use **All Leads** to search and administer the seller database.

1. Search by seller, property, phone, email, or source.
2. Filter by owner, stage, or saved view.
3. Review status and next action in the local detail drawer.
4. Open the full seller record when deeper work is required.
5. Archive a dead or duplicate record only with the required authority and reason.

Use **Archived Leads** from All Leads to locate and restore archived records.

### Seller Pipeline

Use **Seller Pipeline** to view stage distribution and bottlenecks. Select a card to inspect seller
context. Use the recommended next action to open Inbox, Lead Desk, Field Operations, Underwriting,
Negotiation, or the complete record.

Move a stage only when the corresponding real-world event occurred. Stage movement does not
replace qualification, approvals, or evidence.

### Lead Record

The full lead record has five tabs:

- **Overview:** Tasks, qualification, recent activity, contact, property, and record controls.
- **Communications:** Unified timeline, appointments, notes, and manual logs.
- **Underwriting:** Property validation, comp analysis, repairs, versions, reports, and offer
  authority.
- **Deal:** Contracts, transactions, and buyer offers.
- **History:** Consent evidence, attribution, and retained history.

Use the lead record when you need the complete evidence chain. Use focused workspaces for daily
queue execution.

## 10. Underwriting And Comp Analysis

Open **Underwriting** to choose a lead, review valuation accuracy, or inspect calibration. Detailed
analysis is completed in the lead's **Underwriting** tab.

### Before Analysis

Confirm:

- Correct subject address.
- Property type, bedrooms, bathrooms, square footage, and year built when known.
- Occupancy and current condition.
- Known repairs and renovation assumptions.
- Seller asking price and mortgage context when available.

### Run Market Analysis

1. Open the lead's **Underwriting** tab.
2. Validate the property address.
3. Open the comp analysis control.
4. Enter optional repair and renovation details that improve the estimate.
5. Run the market analysis.
6. Review included and excluded comparables.
7. Check distance, recency, property similarity, condition, price-per-square-foot support, and
   outlier reasons.
8. Review ARV, as-is value, repair range, offer scenarios, confidence, and warnings.
9. Save a new underwriting version when assumptions change.
10. Compare versions before requesting approval.

The range is decision support, not an appraisal or guaranteed offer. A result remains visible when
renovation status is unconfirmed, but confidence and warnings should affect judgment.

### Reports

After a completed analysis:

- Use **Investor PDF** for internal review, agents, lenders, buyers, and detailed value debate.
- Use **Client PDF** for a cleaner seller discussion with appropriate explanations and
  disclosures.

Review every report before printing or sharing. Confirm seller, property, comparable, repair, and
offer information is current.

### Calibration

After verified evidence becomes available, record the actual benchmark in Underwriting. Track
range coverage, point error, and market bias. Do not increase dependence on the comp engine until
real-deal calibration is acceptable.

## 11. Offer Approval And Negotiation

1. Save the underwriting version used for the decision.
2. Create the offer plan with opening, target, stretch, and seller ceiling amounts.
3. Provide the rationale and seller context.
4. Submit for approval.
5. The authorized reviewer opens **Approvals** or the lead's Underwriting tab.
6. The reviewer confirms the version is current and evidence supports the ceiling.
7. Approve or reject with decision notes.
8. Record every price discussion and seller counter.
9. Request a concession approval before raising the offer beyond current authority.
10. Record what was actually presented and how the seller responded.

A newer underwriting version makes older authority stale. Generate a new offer plan instead of
reusing stale approval.

## 12. Approvals

Open **Approvals** for pending and completed governed decisions.

1. Select the request.
2. Read the title, summary, due state, source record, and consequences.
3. Follow the review link to inspect evidence.
4. Approve, reject, or cancel only if your role has authority.
5. Add specific decision notes.

Typical requests include offer ceilings, concessions, contract sends, call-note reviews, and AI
capability promotions. Call-note review is completed with the recording and transcript in Inbox.

An approval does not prove the underlying real-world event happened. For example, funding still
requires funding evidence.

## 13. Contracts And Transactions

When an approved seller agreement exists, open or update the transaction.

The Transactions workspace has:

- **Closing**
- **Contract**
- **Documents**
- **Parties**
- **Timeline**

### Contract

1. Select or create the contract package.
2. Select Purchase Agreement, Assignment Agreement, or Contract Addendum and confirm the seller,
   property, price, dates, and terms.
3. Select **Preview PDF** and review the exact agreement before approval.
4. Submit the package for human approval.
5. Confirm SignWell shows Account and Webhook as connected. Owners can select **Connect SignWell**
   or **Verify connection** in this area.
6. Confirm SignWell is connected. Stonegate generates the signing PDF internally.
7. Enter the seller or assignee name and email. Add a second seller when needed. Stonegate adds the
   signed-in company user automatically.
8. Select **Send for signature** only after the exact package version is approved.
9. Track recipients under **Signature requests**. Use **Refresh status** if a provider update is
   delayed.
10. Confirm the completed provider PDF appears in Documents before continuing closing work.

Until production SignWell acceptance is complete, use the controlled manual execution workflow.
Never mark a contract executed merely because a draft was approved or an email was sent.
See `SIGNWELL_LAUNCH_RUNBOOK.md` for account setup and production acceptance.

### Closing

1. Assign the Transaction Coordinator.
2. Set closing, due-diligence, earnest-money, and other dates.
3. Work required checklist items in dependency order.
4. Attach evidence before marking an item complete.
5. Track title, payoff, probate, liens, access, assignment, buyer deposit, and attorney items.
6. Confirm funding evidence before marking funded.

### Documents

Upload the appropriate file, classify it, and confirm extracted facts against the actual source
page. The file room shows the storage and malware-scan state for each document. Raw documents
remain private and are not automatically trusted by AI.

### Parties And Timeline

Maintain the closing attorney, seller, buyer, coordinator, and other approved parties. Use the
timeline for immutable transaction events and escalation history.

### Transaction Copilot

Generate a draft to identify missing documents, deadline risk, party gaps, and proposed
coordination messages. Accept, correct, or reject it. Review does not send email, alter deadlines,
complete checklist items, or mark closing funded.

## 14. Buyers And Dispositions

### Buyer CRM

Open **Buyers**.

For each buyer, maintain:

- Contact and company information.
- Active status.
- Markets, counties, property types, price range, and strategy.
- Cash or financing capacity.
- Proof-of-funds status and expiration.
- Reliability and prior activity.
- Notes and relationship history.

Expired or missing proof of funds should reduce selection confidence.

### Disposition Case

Open **Dispositions** after the seller contract is executed. Tabs are:

- **Package**
- **Buyers**
- **Offers**
- **Reconciliation**

### Package

1. Confirm the frozen compensation plan and disposition operating mode.
2. Complete approved deal facts and marketing package.
3. Set the minimum acceptable amount.
4. Approve the package before buyer release.

### Buyers

1. Generate ranked matches.
2. Review market, property, capacity, reliability, proof-of-funds, and evidence.
3. Exclude ineligible or unsupported buyers.
4. Record engagement and access activity.

### Offers

1. Record each buyer offer, terms, proof, deposit readiness, and expiration.
2. Compare net economics and execution risk.
3. Select the primary and backup buyer only through human approval.

### Disposition Copilot

Generate draft package guidance, buyer ranking explanation, outreach copy, and offer comparison.
Review restricted economics carefully. Accept, correct, or reject the draft. The Copilot does not
send campaigns, select the buyer, or change deal economics.

Live campaign delivery remains blocked until the approved provider adapter is activated.

### Reconciliation

After funds clear:

1. Record collected revenue.
2. Record deal-specific deductions.
3. Confirm role credits.
4. Calculate Adjusted Deal Margin and compensation under the frozen plan.
5. Resolve missing credits or below-target company margin.
6. Obtain owner approval.
7. Export the approved accounting statement.

## 15. Finance

Use 30-day, 90-day, or all-time reporting periods.

Review:

- Collected and pending revenue.
- Deal deductions and acquisition reserve. The reserve is operating-margin math, not a ledger
  expense unless Stonegate incurred a real cost.
- Adjusted Deal Margin.
- Compensation calculations and payment state.
- Company net and margin.
- Reconciliation exceptions.
- Accounting export readiness.
- Finance Copilot analysis.
- Books and Tax Setup, including legal entity, federal tax classification, accounting method,
  books start date, owner-compensation treatment, and the active chart of accounts.
- Tax and Deductions Copilot drafts, missing business-purpose notes, and unresolved evidence.
- Accounting Ledger balances, open-period state, draft journals, approved journals, posted
  journals, reversals, and exact source evidence.
- Posting and Payment Control, including versioned rules, source readiness, evidence exceptions,
  payables, reimbursements, distributions, and source-linked journal drafts.
- Vendors, Bills, and Private Evidence, including contractor W-9 status, itemized invoices,
  approved payables, receipts, and year-to-date vendor payments.
- Financial Statements, including Profit and Loss, Balance Sheet, Cash Flow, Trial Balance,
  General Ledger, receivables, payables, payment history, deal profitability, close readiness, and
  the CPA export package.

Only funded, reconciled proceeds should create earned commissions. Keep projected, earned,
approved, payable, paid, reversed, and disputed states distinct.

The Finance Copilot has two financial review capabilities. **Finance and Accounting Review**
reviews funded-deal economics, commissions, the posted ledger, statements, posting candidates,
possible bank matches, variances, and close blockers. **Tax and Deductions Review** reviews
recorded costs, proposes classifications, and identifies missing evidence for the owner or tax
professional. Neither capability can approve commissions, alter records, promise that an item is
deductible, approve or post journals, match bank lines, close periods, move money, file returns,
make final tax classifications, or change compensation policy.

### Finance Copilot Review

1. Select the reporting period in Finance and run the current financial reports.
2. Open the Finance Copilot and select the financial review capability needed.
3. Generate a draft. The deterministic review runs even when the model provider is unavailable.
4. Check every material statement against its source-record, journal-line, bank-transaction,
   statement, or close-check citation.
5. Treat a posting item as a candidate only. Prepare the real draft through **Posting and Payment
   Control**, then use the normal journal approval and posting workflow.
6. Treat a bank match as a candidate only. Stonegate proposes one only when exactly one unused
   posted journal has the matching cash amount; a person still decides the match.
7. Do not accept an explanation for a variance unless the cause is supported by recorded evidence.
8. Accept, correct, or reject the Copilot draft. The decision is retained without changing any
   accounting record.

The performance strip reports the last 30 days of generated and reviewed drafts, correction and
rejection rates, blocked outputs, model latency, model cost, and estimated review time saved.

### Accounting Ledger

Use **Prepare manual journal** only after the underlying revenue, expense, owner activity, or deal
event has been recorded and supporting evidence is available.

1. Select the entry date and source type.
2. Add the source record or document reference.
3. Enter a clear memo and evidence references.
4. Add at least two lines using the approved chart of accounts.
5. Confirm total debits equal total credits.
6. Prepare the journal.
7. A user with approval authority reviews the accounts, amounts, source, and evidence.
8. A user with posting authority posts the approved journal while the period is open.

Draft and approved journals are unfinished accounting work. Posted journals are permanent. To
correct a posted journal, select **Prepare reversal**, document the reason, then approve and post
the reversing journal through the same workflow. Never create an unrelated offset merely to hide
an error.

### Accounting Periods

- **Open:** Journals can be prepared, approved, and posted.
- **Review:** Posting pauses while the month is reviewed; unresolved journals remain visible.
- **Closed:** The month is complete. Reopening requires a recorded reason.
- **Locked:** The period is permanently protected from reopening in the operating workflow.

A period cannot close while draft or approved journals remain. Closing and locking do not replace
bank reconciliation, month-end evidence, or CPA review.

### Posting And Payment Control

Use this workspace for normal accounting work created from Stonegate records. It is preferred over
manual journal entry because it keeps the journal tied to the exact operational source.

1. The owner reviews each draft posting rule and selects **Approve rule**.
2. Stonegate lists collected revenue, deal costs, marketing spend, approved commissions, and
   approved obligations in the source queue.
3. A funded-deal item becomes ready after the transaction is funded, reconciliation is approved,
   and both the closing statement and funding confirmation are uploaded.
4. Select **Prepare draft**. Stonegate chooses the approved accounts, balances debit and credit,
   links the source, and prevents a second draft for the same accounting event.
5. Review the resulting journal in **Accounting Ledger**, then approve and post it under the normal
   journal workflow.

For a bill, contractor payment, reimbursement, or owner distribution, expand **Add payable,
reimbursement, or owner distribution**. Enter the payee, amount, account, due date, business
purpose, and evidence reference. Move an approved obligation to **Payable** when it is authorized.
After the real payment occurs outside Stonegate, select **Record paid** and enter the bank, check,
or transfer reference plus evidence. Stonegate records the state and prepares the settlement item;
it never sends the payment.

Commission payouts follow the same approach: approved, payable, then paid. Commission accrual and
commission payment are separate accounting events, so the commission expense is not recorded
twice. Owner distributions use the equity account and are never treated as ordinary expenses.

If an amount, status, or evidence set changes after a draft is prepared, Stonegate shows an
exception. Review and correct the linked journal rather than creating an unrelated duplicate.

### Vendors, Bills, And Private Evidence

Use this workspace when Stonegate receives an invoice or needs to keep a contractor, receipt,
W-9, or proof of payment.

1. Expand **Add vendor** and record the contractor or service provider. Select
   **Tax-reportable contractor or vendor** when W-9 tracking is needed.
2. Expand **Upload private evidence**, select the vendor, choose **W-9**, and upload the file.
   The vendor changes to **W-9 received**. After a permitted person reviews it, select
   **Verify W-9**.
3. Expand **Enter bill**. Add one line for each real cost category rather than combining unlike
   expenses. For example, contractor labor and calling software should use separate lines.
4. Upload the invoice and link it to the draft bill.
5. Review the vendor, dates, line coding, amount, and evidence. Select **Approve** only when they
   agree. Stonegate creates one payable in Posting and Payment Control.
6. Prepare and review the itemized accrual journal through the normal posting workflow.
7. Pay the vendor outside Stonegate. Upload the receipt or payment confirmation, then record the
   payment reference through Posting and Payment Control.

Stonegate records and audits the payable; it does not send money. Never place a Social Security
number, employer identification number, bank number, or other tax identifier in vendor notes.
Keep that information only in the restricted W-9 document.

### Bank Statements And Reconciliation

1. Add the company checking account or card using its label and last four digits. Do not enter
   credentials or a full account number.
2. Export a CSV statement from the bank. In **Preview CSV statement**, map the exact date,
   description, and signed amount headers. Balance and transaction-ID columns are optional.
3. Review the preview. Stonegate shows valid, duplicate, and invalid rows before it stores the
   private statement.
4. For each cleared operating line, select the posted journal with the exact same operating-cash
   movement. Use **Ignore** only for a non-operating line and provide a clear reason.
5. Prepare the reconciliation with the statement dates and opening/closing balances. Approval is
   available only when the difference is zero and every included line is resolved.

Stonegate does not connect to the bank, initiate payments, or decide matches automatically.

### Financial Statements And Month Close

1. In **Statements, close, and CPA handoff**, select the first and last date for the period.
2. Select **Run reports**. Only posted journals affect the statements. Draft or approved journals
   remain unfinished work and appear in the close checklist.
3. Review Profit and Loss and Balance Sheet first. Balance Sheet and Trial Balance must both show
   **Balanced**.
4. Expand **Trial balance** to compare total debits and credits.
5. Expand **General ledger** to inspect the exact journal, account, memo, source, and evidence count
   behind the report.
6. Expand **Receivables, payables, and payments** to review pending proceeds, approved vendor and
   commission obligations, completed payment records, and deal-coded profitability.
7. Resolve every close blocker: unfinished journals, missing bank reconciliation, unmatched bank
   transactions, or an open accounting period. Missing evidence is a warning that should be fixed
   before CPA review.
8. Use the Accounting Ledger period control to move the month to **Review**, finish adjustments,
   then **Close** it. Lock only after the final outside review is complete.
9. Select **Download CPA package**. The ZIP contains the manifest, financial statements, trial
   balance, general ledger, receivables, payables, payments, and deal-profitability files.

Opening balances and CPA adjustments are entered as manual balanced journals with a clear source
type, date, explanation, and evidence. They follow the same prepare, approve, and post workflow as
every other journal. The report screen never edits ledger data.

## 16. Marketing

Use 30-day, 90-day, or all-time reporting periods.

Review:

- Page views, offer starts, form starts, submits, errors, and abandonment.
- Leads, contracts, and collected revenue by source and campaign.
- Marketing spend, cost per lead, cost per contract, and return on ad spend.
- Spend without leads.
- Leads without contracts.
- Advertising measurement mode and Google/Meta readiness.
- Prepared qualified lead, appointment, signed contract, and funded-deal outcomes.
- Queued, retried, delivered, blocked, or exhausted conversion events.
- Marketing Copilot analysis.

Select **Prepare conversion events** after CRM outcomes have been updated. Stonegate creates only
new records tied to a captured Google or Meta click; selecting it again does not duplicate the same
outcome. **Process next event** appears only when simulation or live delivery is enabled. Normally
the worker processes due events automatically.

Open the attributed lead when a record needs review. `Credentials pending` means the internal
queue is working but Stonegate has not activated that provider. `Blocked` means configuration is
missing, `Retry` means another attempt is scheduled, and `Exhausted` requires an owner to review
the provider error before retrying operationally.

Drill into source records before changing spend. The Marketing Copilot may recommend tests but
cannot change budgets, audiences, ads, or campaigns. Preparing or delivering outcomes never edits
the lead, transaction, revenue, accounting, ad budget, campaign, or creative.

## 17. Operating Model

The Owner uses **Operating Model**. Tabs are:

- **Company setup**
- **Active policy**
- **Pending decisions**
- **Policy history**
- **Market launches**

Use it to:

1. Install and maintain operating seats, coverage, and backups.
2. Add and verify closing and operating partners.
3. Assign role manuals and decide employee workspace tests.
4. Review the active compensation plan and company-margin target.
5. Resolve role-credit decisions.
6. Review historical policy versions.
7. Configure human-led or AI-assisted disposition modes.
8. Complete market-specific launch evidence.
9. Approve a launch only after every required item is supported.

Policy changes are effective-dated. They do not rewrite historical deal economics.

## 18. AI Copilots

Copilots live inside the human workspace they assist:

| Copilot | Location | Current authority |
| --- | --- | --- |
| Lead Manager | Lead Desk | Draft and recommend |
| Prospecting | Prospecting | Priority, preparation, and reviewed coaching |
| Acquisitions | Field Operations | Meeting and follow-up drafts |
| Transaction | Transactions | Coordination drafts |
| Disposition | Dispositions | Buyer and package guidance |
| Finance | Finance | Aggregate analysis and recommendations |
| Marketing | Marketing | Aggregate analysis and recommendations |
| Executive | Dashboard | Operating brief and decisions |

### Standard Copilot Review

1. Select the relevant real work item.
2. Generate the recommendation.
3. Verify each material statement against linked evidence.
4. Review uncertainty and risks.
5. Edit incorrect or incomplete content.
6. Accept, correct, or reject.
7. Perform the approved human action in its normal workspace.

Do not paste secrets, unrelated seller data, or unsupported facts into an AI request.

## 19. AI Control

Only authorized owners use **AI Control**. Views are:

- **Copilots**
- **Runtime**
- **Automation**
- **Portfolio**
- **Evaluations**
- **Traces**
- **Governance**

### Copilots

Install and review the role-facing copilot contracts. Confirm each has a named human owner,
retained human authority, approved capabilities, evidence rules, escalation, and prohibited
actions.

### Runtime

Install the governed runtime, inspect model routes, budgets, read-only tools, knowledge scopes,
provider state, and circuit breaker. Use **Emergency stop** when provider, policy, privacy, or
quality risk requires immediate shutdown.

### Automation

Select **Install controls** once after AI10 deployment. Four simulation-only policies appear:

- Consented seller acknowledgement.
- Appointment reminder.
- Consented seller follow-up.
- Approved buyer campaign.

For each policy:

1. Review the named owner, provider, capability, audience, consent, template, contact, frequency,
   volume, cost, quality, canary, pause, and rollback rules.
2. Select **Approve control contract** only when the contract itself is correct.
3. Select **Run readiness simulation** to record current blockers.
4. Use **Pause policy** for any concern.
5. Use **Resume controls** only after reviewing the pause reason.

Approval and simulation do not activate sending. The current release has no delivery endpoint.

### Portfolio And Evaluations

Use Portfolio to inspect specialist engines, prompts, tools, risk, and autonomy. Use Evaluations to
approve redacted datasets, run model replay, compare results, and enforce quality thresholds.

### Traces And Governance

Review model runs, evidence, tool calls, cost, failures, and human decisions. Flag unsafe or
unsupported traces. Governance contains source precedence, approved knowledge, data-quality rules,
promotion history, and rollback.

Never promote a capability using another capability's results.

## 20. Records, Audit, And Corrections

Material actions create activity or audit evidence. Preserve history:

- Correct a lead through an authorized edit.
- Create a new underwriting version when assumptions change.
- Create a new offer plan when authority becomes stale.
- Create a correction attempt for a returned VA handoff.
- Add a transaction event instead of rewriting history.
- Reverse or dispute a financial record instead of deleting a paid state.

Archive is preferred over deletion when a record has operating history.

## 21. Notifications And Ownership

Ownership identifies the person responsible for the next outcome. Watchers receive visibility
without becoming the owner.

Reassign when responsibility changes:

- VA to Lead Manager after warm handoff.
- Lead Manager to Closer for field execution when appropriate.
- Acquisitions to Transaction Coordination after executed contract.
- Transaction and Dispositions remain separate responsibilities on the same deal.

Always create the next task during a handoff. A stage without an owner and dated next action is an
operating exception.

## 22. Troubleshooting

### Navigation Is Missing

- Confirm sign-in completed and the account is not stuck on **Verifying access**.
- Sign out and sign in again.
- Confirm the Stonegate user is active and has the intended role.
- Hidden pages may be correct for the role.
- The Owner should inspect `/api/v1/me` logs only when role verification fails.

### API Or Workspace Shows Unavailable

- Check whether the API health endpoint is returning `200`.
- Wait for a Render deployment or migration to finish.
- Refresh after the API is healthy.
- Do not resubmit seller forms repeatedly to fix an OS authorization problem.

### Seller Form Returns A Validation Error

- Review required fields and field-level messages.
- Confirm contact permission is checked.
- Use a valid phone and complete property address.
- Retry after correcting the highlighted field.
- A `201 Created` API log means the lead was accepted even if the browser later showed a UI error.

### Lead Was Submitted But Is Not Visible

- Search **All Leads** by phone, email, seller, and property.
- Check whether duplicate matching reused an existing active lead.
- Confirm your role can view the lead.
- If OS requests return `401`, fix Clerk authorization before submitting another lead.

### SMS Is Blocked

Possible reasons include:

- Twilio is not configured or enabled.
- No approved Stonegate sender is attached.
- SMS consent is missing.
- The number is invalid.
- STOP or company suppression exists.
- Contact-hour or frequency policy blocks the action.
- The user lacks permission or assignment.

Do not override suppression or use another business's Messaging Service.

### Voice, Recording, Or Email Is Unavailable

These providers require final activation. Log approved manual communication in Inbox until the
provider passes acceptance. Recording must remain off until disclosure and retention policy are
approved.

### Underwriting Analysis Fails

- Confirm the lead has a complete address.
- Validate the property.
- Confirm required subject facts.
- Check RentCast configuration and quota.
- Review the exact API error before creating another analysis.

### PDF Buttons Are Missing

Complete and save a market analysis first. Open the lead's **Underwriting** tab and review the
report area. Role authorization and API health must also be valid.

### AI Recommendation Is Disabled Or Blocked

- Confirm the runtime and capability are installed and enabled.
- Confirm the OpenAI provider is configured.
- Confirm the source record satisfies the capability's evidence gate.
- Review the visible blocker.
- External-action simulations are expected to remain blocked by the AI10 release lock.

### A Record Cannot Be Deleted

Deletion may be prohibited by role, related evidence, financial history, or audit requirements.
Archive the record or correct it through the approved workflow.

## 23. Owner Administration Checklist

### Daily

- Review Dashboard exceptions.
- Review overdue seller responses and tasks.
- Review today's appointments.
- Review pending approvals.
- Review provider or worker failures.

### Weekly

- Review VA and Lead Manager performance.
- Review pipeline aging and neglected leads.
- Review underwriting calibration and corrections.
- Review transaction deadlines and disposition coverage.
- Review source economics and spend exceptions.
- Review AI acceptance, edits, rejections, cost, and failures.

### Monthly

- Reconcile funded revenue and compensation.
- Review company margin against target.
- Review user access and deactivate departed users immediately.
- Review consent, suppression, recording, and communication exceptions.
- Review backups, alerts, worker health, and provider failure history.
- Review AI quality, privacy, cost, and business outcomes.

### Quarterly

- Review role permissions and operating policy.
- Review market launch requirements.
- Review AI models, prompts, tools, knowledge, evaluations, and autonomy.
- Test emergency shutdown and rollback procedures.
- Review provider contracts, costs, limits, and security.

## 24. New Employee Onboarding

1. Owner creates the Stonegate user and assigns the minimum required role.
2. Employee creates an individual Clerk login.
3. Owner verifies the local user and Clerk identity are linked.
4. Employee signs in and confirms role-specific navigation.
5. Employee completes training using synthetic records.
6. Manager verifies the employee can perform normal work and cannot open restricted pages.
7. Manager reviews consent, suppression, recording, privacy, and escalation rules.
8. Owner assigns the correct manual in **Operating Model > Company setup**.
9. Employee opens **My Setup**, reviews the role standards, and submits workspace-test evidence.
10. Owner approves the submission only after confirming normal access and role restrictions.
11. Live work is assigned only after role acceptance is approved.

When a person leaves, deactivate the Stonegate user immediately. Reassign owned conversations,
tasks, appointments, leads, transactions, and disposition cases. Do not delete the user or their
history.

## 25. Related Documentation

- `LEAD_MANAGER_USER_MANUAL.md`: plain-language daily guide for the Lead Manager role.
- `STAFF_ROLE_MANUALS.md`: plain-language standards for every operating role.
- `PHASE_F2_COMPANY_SETUP.md`: company setup and role-acceptance workflow.
- `OPERATING_MODEL.md`: roles, handoffs, compensation, and operating policy.
- `WORKFLOWS.md`: concise system workflow sequence.
- `CURRENT_STATE.md`: delivered functionality and known limits.
- `ROADMAP.md`: completed phases and remaining production checkpoints.
- `FINISHING_ROADMAP.md`: canonical sequence for production completion and provider activation.
- `UNDERWRITING.md` and `UNDERWRITING_COMP_METHOD.md`: valuation and offer methodology.
- `AI_AGENTS.md`: AI architecture and authority.
- `AI_AUTOMATION_ROADMAP.md`: AI production acceptance sequence.
- `INTEGRATIONS.md`: provider status and boundaries.
- `SECURITY_COMPLIANCE.md`: security, consent, communications, and retention controls.
- `TESTING.md`: release and provider acceptance checks.
