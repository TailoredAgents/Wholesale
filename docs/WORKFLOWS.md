# Workflows

Last updated: July 20, 2026

## Seller Intake

1. Seller visits a public page and starts the cash-offer form.
2. The site records attribution and conversion events.
3. Seller submits property and contact details with required call/email permission and optional
   SMS permission.
4. API validates and normalizes the data.
5. Duplicate matching checks normalized contact and property evidence.
6. API creates or reuses contact, property, lead, and conversation records.
7. API preserves consent, form, attribution, activity, and audit evidence.
8. API creates an urgent speed-to-lead task.
9. Staff works the lead from the private OS.

## VA Qualification And Handoff

1. Manager assigns a list or conversation to a VA.
2. VA sees only assigned seller context and permitted call/disposition actions.
3. VA records qualification answers, call outcome, notes, and appointment.
4. Interested lead changes to Qualified or Appointment Set.
5. Handoff reassigns the lead, conversation, open tasks, and appointment to acquisitions.
6. Owner and acquisitions become watchers.
7. VA loses broad editing access after handoff.
8. Assignment and activity history remain attached to the same record.

## Shared Communications

1. Staff opens the seller conversation.
2. OS calculates SMS and Voice eligibility from role, assignment, number, consent, suppression,
   hours, and provider state.
3. Outbound provider call uses an idempotency key or scoped intent.
4. Provider callback signature is validated.
5. Provider events update the same conversation without duplication.
6. STOP creates organization-wide SMS suppression.
7. Calls, messages, emails, recordings, transcripts, and notes remain chronological.

## Call Intelligence

1. A disclosed, approved call is recorded.
2. Twilio sends a signed completed-recording callback.
3. Worker retrieves private media and requests speaker-separated transcription.
4. OpenAI drafts structured notes and links claims to transcript evidence.
5. Human reviewer corrects and approves or rejects the draft.
6. Only selected approved fields and tasks update the CRM.
7. Quality and cost telemetry record the result.
8. Provider audio expires or is deleted according to policy while the transcript and audit remain.

## Underwriting

1. Staff confirms subject facts and optional repair/renovation context.
2. Service retrieves property and recorded-sale evidence through the provider adapter.
3. Candidate sales are normalized, filtered, scored, and retained with reasons.
4. Engine calculates adjusted value evidence, ARV and as-is ranges, confidence, and review flags.
5. Staff reviews comp evidence and assumptions.
6. Engine calculates repair, transaction, assignment, and offer scenarios.
7. Human approves the working value and offer ceiling.
8. Staff exports the investor or client report for internal review or seller discussion.

## Contract And Transaction

1. Approved offer becomes a proposed contract.
2. Approval verifies price, terms, authority, and required documents.
3. E-signature sends the approved template after that integration exists.
4. Signed agreement opens or updates the transaction checklist.
5. Owners track earnest money, title, payoff, due diligence, buyer, assignment, and closing dates.
6. Closing records revenue, deductions, and compensation inputs.

## Buyers And Dispositions

1. Contracted deal enters the disposition queue.
2. Staff confirms approved deal facts and marketing package.
3. System ranks matching qualified buyers after matching is implemented.
4. Staff approves recipients and sends the campaign.
5. Buyer responses, showings, offers, proof of funds, and deposit status attach to the deal.
6. Human approves the selected buyer and backup.

## Finance And Compensation

1. Record collected revenue.
2. Apply deal-specific deductions.
3. Calculate net commissionable revenue.
4. Apply effective-dated compensation rules.
5. Review and approve acquisition, disposition, founder, and company amounts.
6. Reconcile against accounting and payment status.
7. Report revenue, spend, source profitability, and advertising percentage.

## AI Tool Action

1. Agent run receives a narrow goal and scoped records.
2. Model proposes a structured tool call.
3. Deterministic authorization and compliance evaluate the proposal.
4. Approval-required actions enter the approval queue.
5. Human approves, edits, or rejects.
6. Tool executes idempotently within the approved scope.
7. Run, evidence, tool arguments, result, cost, and audit are retained.
