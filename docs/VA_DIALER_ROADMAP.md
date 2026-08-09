# Stonegate Phone And VA Dialer Roadmap

Last updated: August 1, 2026

## Decision

Stonegate will use a deliberately split phone model:

- one shared Twilio acquisitions number for warm seller calls and consented seller SMS
- one separate Twilio dispositions number for buyers and investors
- BatchDialer-managed numbers and agent seats for VA cold calling
- Stonegate as the source of truth after a seller becomes interested or an appointment is set

This supersedes the July 30 decision to keep all VA calling one-by-one inside Stonegate. The
existing Stonegate prospecting workflow remains available as a manual fallback until the external
dialer handoff passes production acceptance. It will not become a second CRM or hold a competing
warm-lead history.

## Why This Model

- Sellers keep one recognizable acquisitions number even when responsibility moves between Austin,
  Devon, and a future Lead Manager.
- Buyers do not share the seller negotiation line or seller messaging purpose.
- BatchDialer owns high-volume dialing, number pools, reputation monitoring, call-center controls,
  and VA agent sessions.
- Stonegate owns qualified leads, appointments, conversations, assignments, underwriting,
  contracts, dispositions, accounting, and AI assistance.
- Raw cold-call activity does not overwhelm the CRM. Only warm handoffs and the reporting facts
  needed to measure campaigns cross into Stonegate.

## Existing Foundation To Reuse

Stonegate already has:

1. A unified inbox and seller conversation timeline.
2. Twilio SMS sending, signed inbound and delivery webhooks, idempotency, delivery state, and
   STOP/START handling.
3. Twilio company voice-line records, cellphone forwarding, inbound routing, missed-call handling,
   recordings, transcription, and AI call notes.
4. Individual users, teams, assignments, watchers, and role permissions.
5. Campaigns, PropStream imports, cohorts, VA labor costs, attempts, qualification, appointments,
   and reviewed warm handoffs.
6. Lead Manager and Prospecting Copilots operating in supervised mode.

The upgrade extends these records. It does not create replacement inbox, lead, campaign, or AI
systems.

## Provider Boundaries

### Twilio

Twilio handles warm and established relationships:

- acquisitions Voice and consented seller SMS
- dispositions Voice and buyer SMS only under an accurately registered messaging use case
- inbound and outbound event callbacks
- browser calling for permanent Stonegate staff
- recordings and call lifecycle events when recording is intentionally enabled

### BatchDialer

BatchDialer handles VA prospecting:

- PropStream cold-list delivery
- VA seats and assigned dialer campaigns
- outbound number pools and number reputation
- preview or predictive dialing selected by management
- call dispositions, callbacks, recordings, and VA performance
- one controlled handoff when the result is Interested or Appointment Set

### Stonegate

Stonegate remains authoritative for:

- accepted warm leads and their complete history
- seller ownership and appointments
- acquisitions and dispositions conversations
- tasks, underwriting, offers, contracts, and transactions
- campaign attribution, accepted-warm-lead cost, and employee accountability
- AI summaries, recommendations, and approved CRM changes

## Phased Migration

### PH1. Architecture And Line Ownership

Status: implemented in code; production number assignment remains.

- Designate the approved Twilio number as **Stonegate Acquisitions**.
- Define acquisitions members, primary recipient, fallback recipient, business hours, missed-call
  behavior, and voicemail behavior.
- Reserve a separate **Stonegate Dispositions** number and messaging purpose.
- Keep the current one-by-one Stonegate calling queue available as a fallback during migration.
- Do not provision employee-specific Twilio numbers for Austin or Devon.

Implemented controls now store department, purpose, primary owner, fallback owner, coverage hours,
timezone, inbound ownership preference, missed-call policy, provider, and default-line status on
the existing company line record. Current inbound resolution can use the fallback when the
conversation owner or primary owner is unavailable. PH3 adds shared department membership,
sequential/simultaneous ring behavior, and enforcement of the stored hours and missed-call policy.

Exit criteria: every phone number has one department, purpose, owner, fallback, and system of
record.

### PH2. Acquisitions SMS Activation

Status: line-aware sending and number-aware inbound routing are implemented; Twilio Console,
Render, and live acceptance remain.

- Keep the acquisitions number registered for Stonegate's approved seller-inquiry A2P campaign.
- Configure the signed inbound webhook on the acquisitions number itself. Stonegate supplies the
  delivery callback per outbound message.
- Enter the approved number, Account SID, Auth Token, and webhook base URL in Render. A Messaging
  Service SID is optional in Stonegate's direct-number mode.
- Enable Twilio SMS and run controlled outbound, delivered, inbound, STOP, blocked-send, START,
  HELP, reassignment, and duplicate-callback tests.
- Keep purchased-list and unsolicited cold SMS out of this seller-inquiry campaign.

Stonegate now selects the active acquisitions number for seller conversations and preserves the
selected line on dispatch and communication records. Both number-level webhooks may use the same
endpoint because inbound routing reads Twilio's `To` number. PH5 now applies the corresponding
buyer-only rule to the dispositions line.

Exit criteria: Austin and Devon can work one seller SMS thread from Stonegate without duplicate
messages or broken assignment.

### PH3. Shared Acquisitions Voice Routing

Status: implemented in code; Twilio Console, Render, and live acceptance remain in PH4.

- Extend the existing company voice-line records with department membership, primary and fallback
  users, ring strategy, business hours, voicemail destination, and line-use permissions.
- Allow Austin and Devon to place calls from the same acquisitions caller ID.
- Route known callers to the conversation owner first, then the acquisitions fallback group.
- Route new callers to the acquisitions group instead of a single hard-coded employee.
- Use staff cellphone forwarding and Twilio's outbound cellphone bridge instead of browser Voice.

Implemented routing supports an optional department team and up to 10 cellphone destinations.
Simultaneous routing connects the first employee who accepts, announces whether the
call is for acquisitions or dispositions, requires cellphone recipients to press 1, and prevents
personal voicemail from taking the call. It also preserves conversation-owner priority,
primary/fallback deduplication, answer attribution, coverage-hour enforcement, Stonegate voicemail,
and urgent missed-call tasks. Authorized primary, fallback, and team members select the shared line
for outbound calls.

Exit criteria: both authorized users can call from the shared number, inbound calls reach the right
person or fallback, and every call attaches to one conversation.

### PH4. Acquisitions Voice Acceptance

Status: readiness checks and setup controls are implemented; Twilio/Render configuration and live
acceptance remain owner actions.

- Configure the TwiML App, API key, number Voice webhook, and Render Voice variables.
- Test browser registration for Austin and Devon.
- Test outbound caller ID, known-seller routing, unknown-caller routing, busy, no answer, fallback,
  voicemail, and owner coverage.
- Keep recording disabled until the recording disclosure and retention configuration is approved
  for production use.

**Settings > Communications** now reports whether the required Voice environment, active
acquisitions line, matching caller ID, signed webhooks, and owner/fallback coverage are ready. It
also exposes safe copy controls for the number-level inbound webhook and TwiML App outbound URL.

Exit criteria: the acquisitions line can replace personal phones for warm seller work.

### PH5. Dispositions Line

Status: buyer conversations, strict line selection, inbox presentation, permissions, and inbound
routing are implemented; final line ownership and live call/SMS acceptance remain in Twilio and
Render.

- Purchase or designate a separate Twilio Voice/SMS-capable number.
- Add it to Stonegate as **Stonegate Dispositions** with Devon as primary and Austin as fallback.
- Configure the number-level inbound webhook separately. It may share the approved Messaging
  Service only when that campaign's approved message flow covers buyer communications; otherwise,
  use a separate Messaging Service/A2P campaign.
- Add line selection and sender permission so buyer communication cannot accidentally use the
  acquisitions number.
- Route buyer replies into the existing inbox with dispositions visibility and ownership.

Implemented behavior creates one buyer conversation linked to each buyer CRM record, including
existing buyers when their conversation is first opened. **Buyers > Conversation** opens that
thread in the shared inbox. Seller threads can only select the acquisitions line; buyer threads
can only select an active dispositions line assigned to the sender, their fallback assignment, or
their team. Inbound SMS and Voice use the receiving number's purpose before matching a phone
number, so the same phone cannot merge a seller thread with a buyer thread. Unknown callers to the
dispositions number create a minimal buyer record instead of a fake seller lead. Recorded buyer
calls may be transcribed and summarized, but they do not offer seller CRM field updates.

Production acceptance:

1. Confirm **Stonegate Dispositions** is active in Settings > Communications with Devon primary,
   Austin fallback, and `+14708887952` as its number.
2. Keep both number-level Voice and Messaging webhooks on the shared Stonegate endpoints; routing
   uses Twilio's `To` value.
3. Confirm the approved A2P campaign covers one-to-one investor/buyer messaging before enabling
   buyer SMS traffic.
4. Test one outbound and inbound call, one outbound and inbound SMS, caller ID, assignment,
   unanswered-call handling, and seller/buyer isolation with controlled contacts.

Exit criteria: seller and buyer communication are operationally and visibly separated while still
using Stonegate's unified timeline architecture.

### PH6. BatchDialer Provider Connection

- Obtain BatchDialer seats for active VAs only.
- Confirm the account's available API, webhook, Zapier, recording, and disposition capabilities
  before implementing a deep connector.
- Add a Stonegate provider connection with health status and encrypted credentials only for the
  capabilities actually available.
- Map Stonegate campaigns, cohorts, employees, and external BatchDialer identifiers.
- Start with webhook or Zapier handoff if the account does not expose stable public API endpoints.

Exit criteria: Stonegate can identify the originating BatchDialer campaign and VA without copying
all cold-call records into the CRM.

### PH7. PropStream And VA Calling Workflow

- Create the campaign shell and cost assumptions in Stonegate.
- Push or import the PropStream list into BatchDialer.
- Assign each VA an individual BatchDialer login and campaign access.
- Configure scripts and final dispositions, including Interested and Appointment Set.
- Keep raw cold prospects, no answers, and routine retries in BatchDialer.
- Define how inbound callbacks to dialer numbers return to the assigned VA queue.

Exit criteria: a VA can complete a full shift without using the Stonegate warm-lead inbox or seeing
restricted company data.

### PH8. Idempotent Warm Handoff

- Receive only Interested and Appointment Set results from BatchDialer.
- Match or create the Stonegate prospect using external record ID, normalized phone, and property
  address.
- Preserve seller/property facts, VA identity, campaign, disposition, qualification, notes,
  recording reference, and appointment.
- Create exactly one lead and conversation, assign the Lead Manager, follow the Owner, and notify
  both.
- Switch all future seller communication to the Twilio acquisitions number.
- Reject or queue incomplete and duplicate handoffs for review.

Exit criteria: replaying the same provider event cannot create duplicate leads, appointments, or
conversations.

### PH9. Recording, AI, And Reporting

- Retrieve or link BatchDialer recordings for accepted warm leads when provider access permits.
- Transcribe accepted calls and run the existing Prospecting and Lead Manager Copilots.
- Auto-populate only empty qualification fields from transcript evidence with an audit trail;
  require human approval for narrative notes, appointments, tasks, and consequential CRM actions.
- Report calls, contacts, interested sellers, accepted warm leads, appointments, contracts, and
  cost by VA, list, campaign, and cohort.
- Reconcile BatchDialer seats, numbers, list costs, and VA hours against Stonegate campaign costs.

Exit criteria: management can calculate cost per accepted warm lead and audit the evidence behind
every handoff.

### PH10. Controlled Cutover

- Pilot one VA, one campaign, and a small controlled list.
- Run end-to-end callback, handoff, acquisitions follow-up, recording, and reporting tests.
- Add the second and third VA only after the first workflow is stable.
- Make BatchDialer the default VA workspace after acceptance.
- Retain Stonegate's manual calling queue as a contingency tool, not a competing daily workflow.
- Update the setup manual, user manuals, system map, and help-chat knowledge after final acceptance.

Exit criteria: staff know exactly which system to use at every stage, and no seller is worked from
two competing communication histories.

## Immediate Order

1. In **Settings > Communications**, configure the approved number as Acquisitions, select Austin
   and Devon as primary/fallback in the intended order, and save the coverage policy.
2. Complete the Twilio acquisitions SMS steps because the A2P campaign is already approved.
3. Complete PH4 acquisitions Voice configuration and acceptance for Austin and Devon.
4. Confirm the shared line's ring strategy, after-hours voicemail, and answer attribution live.
5. Add the dispositions line and its correct messaging registration.
6. Open BatchDialer and run PH6-PH8 with one VA before adding more seats.

## External References

- [Twilio Messaging Services](https://www.twilio.com/docs/messaging/services)
- [Twilio Voice webhooks](https://www.twilio.com/docs/usage/webhooks/voice-webhooks)
- [Twilio A2P multiple-use-case guidance](https://help.twilio.com/articles/4403014741403-I-have-multiple-messaging-use-cases-How-should-I-register-my-use-cases-for-A2P-10DLC)
- [BatchDialer current plans and integration claims](https://batchdialer.com/pricing)
