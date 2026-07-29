# Phase F8.7A: Internal Mailbox And Routing Upgrade

Last updated: July 28, 2026

## Decision

Keep Stonegate's shared Inbox and Resend transport. Do not create a second email system or
traditional provider mailboxes.

Generalize the existing `Conversation` model so one durable communication thread can be:

- Linked to a seller lead.
- Linked to a transaction or closing.
- Linked to a buyer or disposition case.
- Retained as general company correspondence.

Named addresses and department addresses remain `EmailSenderAlias` records. A staff member's
"mailbox" is a permission-scoped view of shared conversations, not a separate copy of messages.
This preserves continuity when assignments change and still gives each person a focused work view.

## Current Baseline

Already implemented:

- Resend outbound delivery and signed inbound webhooks.
- Provider event deduplication, lifecycle reconciliation, and missed-event recovery.
- Approved sender aliases, owners, teams, direct grants, signatures, and default sender selection.
- One unified SMS, email, call, transcript, and note timeline.
- Conversation assignment, watchers, unread state, and audit history.
- Mine, Unassigned, Team, Needs Reply, Appointments, and Unread views.
- Exact email reply matching through RFC `Message-ID`, `In-Reply-To`, and `References`.
- Manual routing review for unmatched and ambiguous inbound email.

Current limitation:

- Every `Conversation`, `CommunicationRecord`, and outbound dispatch assumes a seller lead and
  contact.
- A brand-new email that is not already associated with a seller can only wait for manual
  assignment to an existing seller conversation.
- Named addresses do not yet provide a dedicated personal work view.
- Department aliases do not yet create true team queues.
- Sensitive accounting correspondence cannot yet override broad conversation-view permissions.

## Target Experience

### Staff

- `My Inbox` shows conversations assigned directly to the signed-in user.
- `My Addresses` filters conversations received by or sent from the user's authorized named
  aliases.
- `Team Inboxes` shows only teams the user belongs to.
- Department views include Offers, Acquisitions, Buyers, Transactions, Accounting, and Support.
- The owner can view every business conversation and routing exception.
- A global Compose action can start an email without first creating a seller lead.

### Inbound Routing

- An exact reply always returns to its existing conversation.
- A new message to a named address defaults to that alias owner.
- A new message to a department address defaults to its assigned team.
- A known sender is linked to the best unambiguous contact and business context.
- An unknown sender creates a pending contact and general conversation instead of being lost.
- Ambiguous context is retained in the correct mailbox and flagged for human linking.
- System traffic such as DMARC reports is isolated from seller work queues.

### Business Context

From the right panel, an authorized user can:

- Link a general conversation to an existing lead.
- Create a new lead from the sender and then link the conversation.
- Link the conversation to a transaction, buyer, or disposition case.
- Change the assignee or team without moving or duplicating messages.
- Keep general correspondence unlinked when no CRM record is appropriate.

## Phase F8.7A.1: Data Model Generalization

Goal: Evolve the existing conversation records without replacing them.

Status: Complete in code on July 28, 2026.

Work:

- Add a conversation context classification: `lead`, `transaction`, `buyer`, or `general`.
- Make lead references nullable where communication records currently require a lead.
- Preserve contact references whenever a real external correspondent is known.
- Add structured context links for transactions, buyers, and disposition cases.
- Add `assigned_team_id`, `source_alias_id`, and a restricted-visibility policy to conversations.
- Allow assignment events and dispatch records to exist without a seller lead.
- Add participant records for To, CC, and BCC membership instead of relying only on message JSON.
- Backfill every existing conversation as `lead` with no ID changes or history rewrites.
- Add database constraints so each context type has valid references.

Exit:

- Existing seller conversations behave identically.
- A general conversation can be created and can retain inbound or outbound email.
- Migration rollback and production-backup restore are tested.

Delivered:

- Migration `0068_f8_mailbox_context` generalizes the existing records in place and backfills
  every seller conversation with a primary lead-context link.
- Conversations now support nullable lead context, type, team assignment, source alias, and
  standard or restricted visibility.
- Communication records, dispatches, and assignment events can exist without a seller lead.
- Structured context links support leads, transactions, buyers, and disposition cases.
- Structured email participants retain From, To, CC, BCC, contact, user, and sender-alias
  relationships.
- General conversations can persist inbound and outbound email without creating a fake lead.
- The full API suite, application type check, and isolated PostgreSQL upgrade/downgrade/re-upgrade
  cycle pass.

## Phase F8.7A.2: Deterministic Routing Engine

Goal: Route new email predictably while retaining human control over uncertain matches.

Status: Complete in code on July 28, 2026.

Routing precedence:

1. Exact RFC reply headers.
2. Retained Resend provider thread evidence.
3. Existing unique conversation for the sender and recipient alias.
4. Known contact with one active business context.
5. Alias owner or alias team as a new general conversation.
6. Organization routing review when required configuration is missing.

Work:

- Separate mailbox routing from CRM-context matching.
- Always place a valid inbound message into an authorized personal or team mailbox first.
- Attach business context only when evidence is unique.
- Create a pending contact for a previously unknown external sender.
- Record the routing rule, confidence, candidates, and decision in the audit trail.
- Add loop protection for Stonegate aliases and staff identities.
- Add system-message rules for DMARC reports, bounces, automated replies, and provider notices.
- Keep routing idempotent across duplicate and out-of-order webhook deliveries.

Exit:

- Valid messages no longer require an existing seller lead to appear in the Inbox.
- Uncertain messages remain visible and actionable without being attached to the wrong record.

Delivered:

- Exact RFC replies and retained provider-thread evidence have the highest routing priority.
- A unique sender and receiving-alias context routes before broader contact matching.
- A sender is attached to an existing CRM conversation only when one active context is
  unambiguous.
- New external correspondents create a pending business contact and general conversation under
  the configured alias owner or team.
- Internal Stonegate loops are ignored, automated mail is categorized, and aliases without an
  owner or team remain in the owner routing queue.
- Every decision records the routing rule, confidence, candidates, and result in the provider
  event. Duplicate and out-of-order webhook protections remain intact.

## Phase F8.7A.3: Access And Mailbox Policies

Goal: Give each role a focused mailbox while preserving owner oversight.

Status: Core authorization complete in code on July 28, 2026.

Policies:

- Austin can view and administer all conversations.
- A named alias owner can view conversations routed to that alias.
- Team members can view conversations assigned to their team.
- Direct sender grants allow sending; watcher grants allow visibility and notifications.
- VA users can access only assigned prospecting conversations and approved contractor aliases.
- Accounting conversations are restricted to Austin, Conner, and explicit grants.
- Transaction conversations are restricted to assigned transaction staff, approved watchers, and
  the owner.
- Removing a user or grant immediately removes future access without changing historical authors.

Work:

- Apply alias, team, assignment, watcher, and restricted-visibility rules in one authorization
  service.
- Enforce the same scope in lists, detail views, search, attachments, exports, and notifications.
- Add explicit owner override and auditable break-glass access if needed later.
- Add tests proving broad role permissions cannot bypass restricted accounting conversations.

Exit:

- API tests prove every role can access only the intended conversations and attachments.

Delivered:

- Austin's Owner role retains organization-wide mailbox oversight.
- Named-alias owners, assigned users, team members, watchers, and explicit alias grantees can
  access their conversations.
- Broad seller-Inbox permission continues to expose standard lead conversations but does not
  expose general or restricted correspondence.
- Accounting, transaction, closing, and legal aliases default to restricted visibility unless
  their routing configuration explicitly chooses another scope.
- Dispositions, transaction coordination, finance, and assigned VAs receive the email permissions
  needed for their authorized mailbox work without gaining unrelated conversation access.
- The same scoped-conversation service protects list, detail, attachment, and send operations.

## Phase F8.7A.4: Inbox Views And General Compose

Goal: Make the model understandable and efficient for nontechnical staff.

Status: Next.

Left panel:

- My Inbox.
- Unassigned.
- Needs Reply.
- Unread.
- My Addresses.
- Team Inboxes.
- Restricted inboxes shown only when authorized.

Middle panel:

- Keep the existing chronological cross-channel timeline.
- Show sender alias, delivery state, participants, and business-context label.
- Keep SMS and email as composer modes rather than separate histories.

Right panel:

- Assignee, team, sender alias, participants, and next action.
- Current seller, property, transaction, buyer, or general context.
- Link, create, or change context actions.
- Pinned notes and AI summary where permitted.

Compose:

- Add a global Compose button.
- Require an authorized From alias.
- Support To, CC, BCC, subject, body, signature, templates, and attachments.
- Search existing contacts and buyers before creating a pending contact.
- Let the sender choose a business context or leave the conversation general.

Exit:

- Staff can send and receive legitimate company email without creating a fake property lead.
- Existing lead conversations retain their current workflow and layout.

## Phase F8.7A.5: Notifications And Work Management

Goal: Ensure replies are owned and acted on.

Work:

- Notify the direct assignee for personal conversations.
- Notify the assigned team for unassigned department conversations.
- Respect watcher notification levels and mute state.
- Add first-response and next-response timers without blocking communication.
- Add owner escalation for aging unassigned or unanswered conversations.
- Deduplicate notifications when a user is both owner, team member, and watcher.
- Add mailbox counts and response-time reporting by alias, team, and assignee.

Exit:

- Every inbound message has a visible owner or team and a measurable response state.

## Phase F8.7A.6: Controlled Migration And Acceptance

Setup:

- Configure named aliases for Austin, Devon, and Conner.
- Reserve Michael's alias until activation.
- Configure Offers, Acquisitions, Buyers, Transactions, Accounting, and Support aliases.
- Assign owners, teams, sender grants, watcher grants, signatures, and defaults.
- Route DMARC aggregate reports to a system category or Resend's DMARC analyzer.

Required acceptance cases:

- A reply to an Austin-sent lead email returns to the same lead conversation.
- A new email to `austin@stonegatehb.com` creates an Austin-owned general conversation.
- A new email to `offers@stonegatehb.com` enters the Lead Management team inbox.
- A new email to `transactions@stonegatehb.com` enters Conner's transaction queue.
- An accounting email is visible to Austin and Conner but not Devon or a VA.
- A general conversation can be linked to an existing lead without duplicating messages.
- A general conversation can create a new contact and lead.
- An email with ambiguous context stays visible and can be resolved manually.
- A duplicate webhook does not duplicate the thread or message.
- Out-of-order delivery events do not regress final delivery status.
- Deactivating a test staff user immediately removes mailbox access.
- Existing SMS, calls, notes, seller conversations, and handoff behavior remain unchanged.

Exit:

- Controlled cases pass in production using company-owned test addresses.
- No real seller, buyer, attorney, or title party is used until acceptance is recorded.

## Rollout Order

1. Data model and migration.
2. Routing engine.
3. authorization and restricted inboxes.
4. Inbox views and general Compose.
5. Notifications and response reporting.
6. Alias configuration and controlled acceptance.
7. F8.8 production launch approval.

## Non-Goals

- Do not recreate Gmail or provide IMAP/POP access.
- Do not create a separate message store for each employee.
- Do not copy one inbound message into multiple conversations.
- Do not use the operational domain for cold-email campaigns.
- Do not allow AI to send new external email autonomously during this upgrade.
- Do not weaken existing attachment, audit, sender-grant, or conversation access controls.

## Research Basis

- Intercom's current Inbox guidance uses permission-scoped views, team inboxes, explicit
  assignment, and routing rules while retaining one conversation history:
  `https://www.intercom.com/help/en/articles/10223008-setting-up-the-inbox`.
- Intercom documents role-based limits for all, assigned, team, and restricted conversation access:
  `https://www.intercom.com/help/en/articles/4707721-limit-teammates-access-to-conversations`.
- Resend Receiving uses domain MX records, signed `email.received` webhooks, and API retrieval for
  complete bodies and attachments:
  `https://resend.com/docs/dashboard/receiving/custom-domains`.
