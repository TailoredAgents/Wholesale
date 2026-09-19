# Stonegate Employee Guide

Last verified: September 19, 2026

This is the short, current guide Ask Stonegate should prefer when an employee needs to know where work belongs or what to do next. The application and API remain the final authority when a screen and this guide disagree.

## The operating model

Stonegate is organized around four kinds of work:

- **Work** keeps up with today: Home, Conversations, Tasks, and Calendar.
- **CRM** holds durable records: Leads, Deals, and Buyers.
- **Outreach** handles acquisition prospecting and disposition outreach: Prospecting and Dispositions.
- **Business and Administration** contain restricted Finance, Marketing, and Settings work.

Most employees should begin at **Home** or **Conversations**, not hunt through every page. A record's stage describes where it is in the pipeline. A reminder or task describes a real action a person deliberately scheduled. Those are separate things.

## Navigation and access

The left navigation only shows work the signed-in employee can access. Owners can see company-wide work without being a member of every team. Finance, Marketing, and Settings remain permission-controlled. Do not work around a missing menu with another employee's login; ask an owner to review the role or team membership.

Use the green **Phone** bubble at the bottom-right for business calls from the browser. Use the
**Ask Stonegate** sparkle in the top workspace header for questions about the CRM, a role, or a
company process.

Ask Stonegate is read-only. It explains and points to the right place; it does not silently edit records or grant access.

## Home

Home is the daily operating view. It emphasizes manually due work, appointments, offer work, exceptions, and the active pipeline. "Needs review" is not the same as overdue. Only an actual task or reminder with a past due time should be treated as overdue.

Use **Open full queue** or the relevant section when the summary shows work that needs attention. Mark a task done only after the action is actually complete.

## Conversations

Conversations is the shared communications workspace for SMS, email, calls, and notes. Use the assignment and ownership controls when another employee should take over. An unread message is not automatically an overdue task. A reply becomes due only when a person deliberately creates or schedules that follow-up.

Deliberate one-to-one calls and texts do not require a separate permission record. Use normal business
judgment, and never contact a person who has asked Stonegate to stop. Carrier STOP, Do Not Contact,
suppression, an invalid destination, or an unavailable provider still blocks the affected channel.
Attachments and inbound MMS photos appear with the conversation when the provider delivered them
successfully.

## Tasks, reminders, and Calendar

Tasks and reminders are intentional commitments:

1. Set a date and time when the seller or situation actually calls for future action.
2. Add a short reason that will make sense later.
3. Assign the right employee.
4. Mark it **Done** when completed, or reschedule it when the timing changes.

Stonegate should not create recurring overdue pressure merely because a lead exists or a message is unread. A six-month callback is valid: schedule it for the agreed date instead of leaving an artificial near-term follow-up.

Calendar is the time-based view for appointments and scheduled work. Tasks is the list view for deliberate work items.

## Leads

Leads has four focused views:

- **Today** shows the work that is actually relevant now.
- **All Leads** is the searchable, bounded company list and uses pagination as the database grows.
- **Pipeline** groups active seller opportunities by stage.
- **Underwriting** contains property and offer analysis work.

Pipeline stages describe deal progress: New, Contacting, Contacted, Qualifying, Qualified, Appointment, Underwriting, Offer, Nurture, and Under Contract. Their colored badges are stage indicators, not task urgency.

Use **Move to stage** for ordinary progress. **Offer** and **Under Contract** can open the workflows needed to capture the facts behind those stages. If a purchase agreement was signed outside Stonegate, use **Record an already-signed contract**, upload the executed PDF, enter the real terms, and open Dispositions.

Use **New Lead** even when the relationship is still being built. Only a seller name and either a
phone number or email are required; the property type, address, motivation, and other facts can be
completed later. Use **Not a lead** for spam, a wrong number, an unrelated solicitation, a duplicate,
or another non-seller contact. That action removes the record from active seller work without erasing
its call or message history, and the confirmation offers **Undo** immediately.

New seller leads route through the configured acquisitions team. Team membership and routing are managed in Settings by authorized users. Ownership means who is responsible for moving the record forward; it does not make the record invisible to an owner.

## Deals and contract changes

Deals is the durable deal record after acquisition work becomes substantive. Keep contract evidence, documents, closing facts, and disposition readiness attached to the deal.

When a signed contract is renegotiated, do not overwrite the original agreement as if it never existed. Record an **executed contract amendment**, upload the signed amendment, enter the revised terms, and preserve both the original and amended history. The current deal economics should then reflect the executed amendment.

## Prospecting

BatchDialer is the production cold-calling system. Stonegate is the system of record for the resulting
seller or investor relationship. Campaign mappings and BatchDialer handoff configuration live in
**Prospecting > BatchDialer campaign routes**:

- **Seller acquisition** routes qualified results into seller Leads in the selected House or Land lane.
- **Investor disposition** routes interested investors to one selected contracted deal, creates or
  updates an Active Buyer Prospect, and connects that person to the deal's Dispositions work. It must
  never create a seller lead.

Results from an unmapped campaign are held for review until an authorized person selects the campaign
purpose and required destination. Stonegate is not intended to replace BatchDialer's multiline cold
dialer.

## Dispositions

Dispositions is company-visible to operational staff who need to collaborate on contracted deals. Use it to build and rank the investor queue, review the investor relationship, communicate one-to-one, record outcomes, and continue to the next investor.

The deal packet should be available from the outreach workspace. Use **Open packet**, **Copy link**, **Text packet**, or **Email packet** while speaking with an investor. An externally prepared investor packet can be uploaded and approved as the official packet when the built-in packet is not ready or is not the desired version.

Investor conversations belong to the canonical buyer relationship so another employee can understand prior texts, emails, calls, interests, and objections.

## Buyers

Buyers separates investor work into three understandable views:

- **Active Buyer Prospects** are investors currently being worked for a specific property. BatchDialer
  investor-disposition results belong here and display the connected property.
- **Buyer Network** contains reusable investor relationships Stonegate wants to contact about future
  deals. Add an active prospect to the network only when the relationship should be retained beyond
  the current property.
- **Past Buyers** contains investors who completed a purchase.

Keep markets, strategies, price range, proof-of-funds status, notes, performance, and the next
meaningful follow-up current. A prospect may be contacted for the connected deal while the reusable
relationship profile is still being enriched.

## Caroline seller callbacks

The `470-888-7952` line is answered by **Caroline**, the ElevenLabs seller-callback agent. It is for
people returning BatchDialer seller calls. Caroline can capture a potential seller, record a do-not-
contact request, schedule a callback, and transfer an interested caller to the human acquisitions
line. Review **Conversations > AI seller calls** for the recording, transcript, result, and captured
CRM work. OpenAI Realtime remains a configured rollback provider; employees should not change the
active provider.

## Browser phone

Use the green Phone bubble at the bottom-right to call a valid business number, including a number that is not attached to an active lead. Add a name, company, and reason when useful so the resulting conversation is understandable. Archived or closed CRM status alone should not block a legitimate business call.

If browser audio fails, check microphone permission and the phone status shown in the panel before redialing. Do not repeatedly click Call while a request is already connecting.

## Ask Stonegate

Ask Stonegate can answer questions such as:

- "What can I do on this page?"
- "Where should I record a six-month callback?"
- "How do I move an outside-signed contract to Under Contract?"
- "Where do I send an investor the packet?"
- "Why can I not see Finance or Settings?"

It uses the employee's signed-in role, current page, and approved Stonegate documentation. It should say when the documents do not establish an answer. It must never invent a policy, promise that an external delivery succeeded, reveal restricted business information, or claim it changed a record.

## When to ask a person

Escalate to an owner or the responsible manager when:

- the requested action changes legal, financial, contract, or company policy;
- access appears wrong after confirming the employee's role and team;
- a provider reports delivery or telephony errors that Stonegate cannot resolve;
- the documentation and the visible screen materially disagree;
- a seller, attorney, buyer, or partner needs a decision rather than an explanation.
