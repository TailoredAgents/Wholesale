# Phase F8: Resend Operational Email

Last updated: July 27, 2026

## Goal

Replace the disabled Gmail/OAuth implementation with company-controlled, two-way operational
email inside Stonegate's existing shared Inbox. Resend is the transport provider; PostgreSQL,
Stonegate permissions, and the unified conversation timeline remain authoritative.

This phase does not create conventional provider mailboxes, a second Inbox, or a cold-email
system.

## Approved Organization And Address Plan

### Named Senders

| Address | Person | Initial purpose |
| --- | --- | --- |
| `austin@stonegatehb.com` | Austin | Owner, CEO Management, Acquisitions Closer, and approved Dispositions field support |
| `devon@stonegatehb.com` | Devon | Initial Lead Manager and Dispositions |
| `conner@stonegatehb.com` | Conner | Transactions, closing coordination, and bookkeeping |
| `michael@stonegatehb.com` | Michael | Reserved; activate only when Michael joins as Lead Manager |

### Department Aliases

| Address | Purpose | Initial routing | Planned routing after Michael joins |
| --- | --- | --- | --- |
| `offers@stonegatehb.com` | Website leads and initial seller replies | Devon primary; Austin watcher | Michael primary; Austin watcher |
| `acquisitions@stonegatehb.com` | Qualified sellers, appointments, negotiation, and offers | Devon and Austin | Michael and Austin |
| `buyers@stonegatehb.com` | Deal packages, investor inquiries, buyer offers, and closing support | Devon and Austin | Devon and Austin |
| `transactions@stonegatehb.com` | Contracts, attorneys, title, deadlines, and closing | Conner primary; Austin watcher | Same |
| `accounting@stonegatehb.com` | Bills, W-9s, commissions, reconciliation, and bookkeeping | Conner primary; Austin watcher | Same |
| `support@stonegatehb.com` | General help and messaging-program support | Devon primary; Austin watcher | Michael primary; Austin watcher |

Department addresses are routed aliases inside Stonegate, not separate Resend users. Named
addresses are available only to the named person and authorized management. Department aliases
are available only to users assigned to the corresponding team or granted explicit management
access.

Two to three initial Upwork VAs receive individual Clerk logins and restricted prospecting access.
They do not receive operational mailboxes by default. If a contractor later needs operational
email, Stonegate creates an individually attributable contractor alias after owner approval. Cold
email never uses `stonegatehb.com`; it requires a separate domain and outreach provider.

## Domain Decision

Use `stonegatehb.com` as both the sending and receiving domain because Stonegate is intended to be
the company mailbox and the domain currently has no competing mail provider. Adding Resend's MX
record makes inbound mail flow to Stonegate through Resend Receiving; it does not replace the
Render website records.

If Stonegate later adopts another mailbox provider, move operational receiving to a dedicated
subdomain or configure deliberate forwarding before changing MX priorities.

## Phase F8.1: Team, Sender, And Routing Decisions

Owner: Codex implementation; Austin approval.

- Record the initial team coverage and 60-day Lead Manager transition.
- Set new human-led compensation-plan drafts to 20% Dispositions.
- Use two 50% Dispositions role credits when Devon and Austin perform the approved split.
- Approve the named addresses, department aliases, ownership, watchers, and role boundaries above.
- Preserve historical compensation versions and require deliberate activation of the replacement
  plan.

Exit:

- The operating model, compensation defaults, email runbook, and F8 plan agree.
- No live plan, user, mailbox, or provider credential is changed implicitly.

## Phase F8.2: Provider-Neutral Email Foundation

Owner: Codex.

Status: **Complete in code on July 27, 2026.**

- Add an email-provider interface without changing communication IDs or conversation history.
- Add organization-scoped alias, sender permission, routing, signature, and provider-event
  records.
- Retire OAuth credential use while retaining migration history.
- Add configuration validation for simulation and Resend modes.

Implemented:

- `EmailDeliveryProvider` separates delivery from the shared Inbox service. Simulation, legacy
  Google delivery, and the F8.3 Resend adapter use the same request/result contract.
- `email_sender_aliases` stores company-controlled named, department, contractor, active, reserved,
  disabled, inbound, outbound, default, owner, team, signature, purpose, and routing state.
- `email_sender_grants` stores individually attributable sender or watcher access.
- Owner-managed alias and grant APIs enforce organization scope, approved domains, active-user and
  team references, one default sender, and audit history.
- Provider-specific configuration supports `disabled`, `simulate`, legacy `google`, and planned
  `resend` modes. Resend credentials are declared but production remains disabled.
- Gmail synchronization is now explicitly legacy-only and cannot run when another provider is
  selected.
- Existing simulated and Gmail test behavior remains intact.

Exit:

- Existing simulated email still works.
- Resend can be selected without Gmail credentials or a second Inbox.

## Phase F8.3: Outbound Resend Delivery

Owner: Codex.

Status: **Complete in code on July 27, 2026. Production delivery remains disabled.**

- Send approved text, HTML, recipients, CC, BCC, reply headers, and attachments through Resend.
- Use an idempotency key for every dispatch.
- Store provider IDs and normalized sent, delivered, delayed, bounced, complained, failed, and
  suppressed states.
- Keep Copilot output as a human-approved draft.

Implemented:

- `ResendEmailDeliveryProvider` sends through the current Resend Email API using server-side
  credentials and an `Idempotency-Key` header.
- Shared Inbox dispatches can select an active company alias. Organization, conversation, role,
  owner, team, and direct-grant permissions are enforced before provider delivery.
- Text, optional HTML, CC, BCC, attachments, signatures, `In-Reply-To`, and `References` are
  carried through the provider-neutral delivery contract.
- Resend's provider email ID and retrieved RFC `Message-ID` are retained with the existing
  communication and dispatch records. Subsequent messages use that evidence to preserve the email
  thread.
- Stonegate's database-level dispatch key and Resend's provider-level idempotency key protect the
  same request from duplicate delivery.
- Provider rejection records a failed dispatch and returns a controlled gateway error. A sent
  email remains sent if Resend's follow-up metadata lookup is temporarily unavailable.
- Legacy Google and local simulation paths remain compatible during migration.
- Focused tests cover authorized delivery, unauthorized alias use, HTML, CC/BCC, attachments,
  threading, provider failures, and duplicate retries.

Exit:

- Controlled tests send once from an authorized alias and retain complete provider evidence.

F8.4 now reconciles delivery lifecycle updates beyond the initial `sent` or `failed` result
through signed Resend webhooks.

## Phase F8.4: Inbound Receiving And Recovery

Owner: Codex.

Status: **Complete in code on July 27, 2026. Production receiving remains disabled.**

- Add a signed Resend webhook endpoint and durable provider-event intake.
- Retrieve received bodies, headers, and attachments.
- Thread exact replies using provider and RFC message headers.
- Route by recipient alias and conversation evidence.
- Send ambiguous matches to an owner review queue instead of guessing.
- Add a worker recovery job for missed received-email events.

Implemented:

- `POST /api/v1/webhooks/resend` verifies the raw body with Resend's Svix signature headers,
  rejects stale or invalid signatures, and durably records the event before returning.
- Provider event IDs are organization-scoped and unique. Webhook retries and manual replays return
  the existing event instead of duplicating work.
- The worker retrieves full received-email content because Resend webhooks contain metadata only.
- Exact `In-Reply-To` and `References` evidence is preferred. A single seller-email match is the
  bounded fallback. Multiple or missing matches remain `ambiguous` or `unmatched` provider events
  for the owner review interface in F8.5.
- Inbound messages preserve Resend IDs, RFC headers, sender and recipient aliases, text, HTML
  availability, chronological conversation history, unread state, and activity history.
- Received attachments are downloaded before Resend's temporary URL expires, checked against
  Stonegate size, file, malware-scan, and retention rules, and retained in private database or
  object storage. Legacy Google attachments remain readable during migration.
- Sent, delivered, delayed, bounced, complained, failed, and suppressed events reconcile the
  communication and dispatch records without allowing late, lower-priority events to regress the
  current state.
- The worker scans Resend Receiving with cursor pagination and creates synthetic durable events
  for received emails whose webhooks were missed.
- Migration `0067_f8_resend_inbound` makes email attachments provider-neutral and adds durable
  content, checksum, storage, malware-scan, and retention evidence.
- Focused tests cover valid and invalid signatures, replay deduplication, exact reply threading,
  durable attachment retrieval, authorized download, out-of-order lifecycle events, unmatched
  review routing, and missed-webhook recovery.

Exit:

- A reply appears once in the originating Stonegate conversation, including after replay.

## Phase F8.5: Inbox And Administration

Owner: Codex.

Status: **Complete in code on July 27, 2026. Production email remains disabled.**

- Replace Google connection controls with owner-managed alias controls.
- Add authorized From selection, signatures, routing owners, watchers, status, and failure detail.
- Support the initial team map and the later Devon-to-Michael routing change without rewriting
  history.
- Keep VAs limited to their assigned role and conversations.

Implemented:

- The Shared Inbox now loads authorized Stonegate aliases instead of legacy Google accounts and
  sends with `email_sender_alias_id`.
- Each user sees only active aliases available through ownership, team membership, direct sender
  grants, or email-administrator authority. VA callers remain outside the email APIs.
- The owner administration dialog creates and updates named, department, and contractor aliases;
  controls status, inbound/outbound use, defaults, owners, teams, signatures, and direct sender or
  watcher grants; and shows current Resend readiness without exposing secrets.
- Unmatched and ambiguous Resend email appears in an owner-only routing queue. Manual assignment
  records an audit event and returns the durable provider event to the worker for normal import.
- Inbox messages show provider lifecycle status and retained dispatch failure detail.
- Alias reassignment updates the current route while preserving prior audit and communication
  history, including the planned Devon-to-Michael transition.
- Focused tests cover owner-only administration, active-user options, VA denial, manual exception
  routing, normal import after resolution, and the existing sender authorization boundaries.

Exit:

- Each role sees only the appropriate senders and conversations.
- Austin can administer all aliases and unresolved routing exceptions.

## Phase F8.6: Deployment And Provider Setup

Status: Complete July 28, 2026. The branded API domain is live; Resend sending and receiving DNS,
the production API key, the signed webhook secret, and subscribed webhook endpoint are configured.

Owners: Codex for deployment configuration; Austin for provider and DNS actions.

Codex:

- Add final Render variable declarations.
- Run automated tests, commit, push, deploy, and provide the exact webhook URL.

Austin:

- Add and verify `stonegatehb.com` in Resend.
- Add the supplied SPF, DKIM, DMARC, and receiving MX records in DNS.
- Create the production API key.
- Enter the provided values in the API and worker Render services.
- Register the deployed webhook and select the required email events.

Exit:

- Resend reports the sending and receiving domain as verified.
- API and worker readiness identify Resend as configured without exposing secrets.

## Phase F8.7: Acceptance

Status: In progress. Production transport is enabled for controlled company-address testing only.

Owners: Austin and Codex.

- Send from a named address and each department class.
- Reply from a company-controlled external address.
- Test exact threading, alias routing, attachments, delivery, bounce, suppression, duplicate
  replay, out-of-order events, and provider-disabled behavior.
- Verify Devon, Conner, Austin, future Michael, and VA permission boundaries with controlled users.

Exit:

- Every F8 acceptance test passes before a real seller, buyer, attorney, or title party is used.

## Phase F8.8: Production Launch

Owners: Austin approval; Codex closeout.

- Approve sender names, signatures, team routing, and activation.
- Enable Resend delivery.
- Record the production configuration without secret values.
- Update current state, credentials, integrations, staff manuals, and recovery procedures.
- Monitor the first controlled conversations and correct any routing exception.

Exit:

- Operational email is live inside the Stonegate Inbox.
- Gmail/OAuth is not required.
- Cold outreach remains isolated from the operational domain.
