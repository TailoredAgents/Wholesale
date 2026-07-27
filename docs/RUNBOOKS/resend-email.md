# Resend Operational Email

Last updated: July 27, 2026

## Status

Resend is selected as Stonegate's operational email provider. F8.2-F8.3 have implemented the
provider-neutral delivery boundary, company alias and sender-grant records, owner APIs,
provider-specific configuration, database migration, and tested outbound Resend adapter. Live
sending, Receiving webhooks, recovery, and Inbox administration remain disabled until F8.4
through F8.7 are complete and accepted.

The existing Google Workspace/Gmail OAuth implementation remains disabled and is superseded. Do
not configure Google OAuth or enable Gmail synchronization.

Implementation is Phase F8 of `../FINISHING_ROADMAP.md`.

## Product Model

Stonegate's shared Inbox is the employee mailbox experience.

- Staff send from approved company aliases.
- Resend sends the message.
- Resend Receiving posts inbound email events to Stonegate.
- Stonegate retrieves the body, headers, and attachments.
- Stonegate attaches the email to the correct seller or deal conversation.
- PostgreSQL remains the communication source of truth.

Employees do not connect personal email accounts and do not share provider credentials.

## Domain Decision

The approved sending and receiving domain is `stonegatehb.com`. Do not configure the retired
domain in Resend.

Stonegate intentionally uses root-domain receiving because the OS will be the company mailbox and
the domain has no competing mailbox provider. Resend receives mail for the domain after its MX
record is configured. The Render website records remain separate from email MX records.

If another mailbox provider is added later, use a dedicated receiving subdomain or deliberate
forwarding before changing MX priorities.

Use a sending subdomain when useful for reputation isolation. Configure SPF and DKIM and add DMARC
monitoring before production delivery.

## Approved Aliases

Named senders:

- `austin@stonegatehb.com`
- `devon@stonegatehb.com`
- `conner@stonegatehb.com`
- `michael@stonegatehb.com`, reserved and inactive until Michael joins

Department aliases:

- `offers@stonegatehb.com`: seller intake and initial follow-up
- `acquisitions@stonegatehb.com`: qualified sellers, appointments, and negotiation
- `transactions@stonegatehb.com`: seller, attorney, title, and closing correspondence
- `buyers@stonegatehb.com`: approved disposition packages and buyer replies
- `accounting@stonegatehb.com`: bills, tax documents, commissions, and bookkeeping
- `support@stonegatehb.com`: operational help and messaging-program support

Each alias needs:

- Display name.
- Purpose and permitted roles.
- Assigned user or team.
- Reply routing rule.
- Signature.
- Retention policy.
- Allowed templates.

The complete initial and post-Michael routing matrix is in `../PHASE_F8_RESEND_EMAIL.md`.

## Defined Environment Variables

These variables are declared in application configuration and Render. Keep `EMAIL_ENABLED=false`
and `EMAIL_PROVIDER=disabled` until the outbound and inbound acceptance phases are ready:

- `EMAIL_ENABLED`
- `EMAIL_PROVIDER=resend`
- `RESEND_API_KEY`
- `RESEND_WEBHOOK_SECRET`
- `RESEND_SENDING_DOMAIN`
- `RESEND_RECEIVING_DOMAIN`
- `RESEND_DEFAULT_FROM_EMAIL`
- `RESEND_WEBHOOK_BASE_URL`

Secrets belong in Render. Only non-secret public configuration may be exposed to the browser.

## Outbound Implementation

The adapter now:

- Send through the Resend Email API.
- Require an approved Stonegate sender alias.
- Enforces role, conversation, owner, team, and direct-grant sender permissions.
- Use an idempotency key for each dispatch.
- Preserve reply and thread headers.
- Support approved attachments within Stonegate limits.
- Stores provider email ID, RFC `Message-ID`, recipient, sender, subject, timestamps, and dispatch
  status.
- Never expose the API key to the browser.

Delivery, delay, bounce, complaint, and suppression transitions remain part of F8.4 signed webhook
processing. Live outbound stays disabled until inbound recovery and acceptance are ready.

## Inbound Requirements

The webhook must:

- Accept `email.received`.
- Verify the Resend/Svix signature before processing.
- Deduplicate using the webhook event ID.
- Return a successful response after durable event intake.
- Retrieve full message content through the Receiving API.
- Retrieve authorized attachments before temporary URLs expire.
- Route using recipient alias, sender, reply headers, and retained provider IDs.
- Create a review exception instead of guessing when conversation matching is ambiguous.
- Preserve the original provider event and normalized communication record separately.

The worker needs a recovery job that lists received emails and imports any event missed during an
outage.

## Delivery Events

Store and display:

- `email.sent`
- `email.delivered`
- `email.delivery_delayed`
- `email.bounced`
- `email.complained`
- `email.failed`
- `email.suppressed`
- `email.received`

Webhook delivery is at least once and event order is not guaranteed. Processing must be idempotent
and use provider timestamps instead of assuming arrival order.

Hard bounces, complaints, unsubscribes, and provider suppression must prevent unsafe repeat
delivery until an authorized resolution is recorded.

## Threading

Threading must retain:

- Provider email ID.
- RFC `Message-ID`.
- `In-Reply-To`.
- `References`.
- Subject.
- Sender and recipient aliases.
- Stonegate conversation ID.

When exact header matching is unavailable, Stonegate may use bounded contact and subject evidence
to propose a conversation. A person must resolve ambiguous matches.

## Attachments

- Validate type and size before sending or retaining.
- Store permanent files in Stonegate's selected private object storage.
- Store provider attachment IDs and checksums.
- Use authenticated downloads and role checks.
- Scan documents before staff access when the object-storage phase is implemented.
- Do not treat temporary Resend download URLs as permanent storage.

## Migration From Gmail

The implementation phase must:

1. Add a provider-neutral email adapter.
2. Add the Resend adapter, signed webhooks, and recovery worker.
3. Replace OAuth mailbox connection with owner-managed aliases.
4. Remove Google wording and controls from Inbox.
5. Migrate or retire legacy `EmailAccount` credential fields safely.
6. Replace Gmail-specific Render variables and worker jobs.
7. Replace provider-specific tests without reducing threading, attachment, role, or audit coverage.
8. Keep communication record IDs and conversation history stable.

Do not delete the legacy migration files. Database history must remain reproducible.

## Acceptance Test

Use company-controlled addresses:

1. Verify the sending and receiving domain.
2. Send from an approved Stonegate alias inside Inbox.
3. Confirm `sent` and `delivered` events attach to the message.
4. Reply from the external test address.
5. Confirm the reply appears once in the same conversation.
6. Repeat with an attachment.
7. Trigger a controlled invalid-recipient bounce.
8. Replay a webhook and confirm no duplicate record is created.
9. Deliver events out of order and confirm the final state remains correct.
10. Disable the provider and confirm Stonegate fails safely without losing queued work.

Do not use a real seller until all checks pass.

## Official References

- [Resend sending API](https://resend.com/docs/api-reference/emails/send-email)
- [Resend Receiving](https://resend.com/docs/dashboard/receiving/introduction)
- [Retrieve a received email](https://resend.com/docs/api-reference/emails/retrieve-received-email)
- [Retrieve an inbound attachment](https://resend.com/docs/api-reference/emails/retrieve-received-email-attachment)
- [Resend webhook events](https://resend.com/docs/webhooks/event-types)
- [Resend webhook behavior](https://resend.com/docs/webhooks/introduction)
- [Resend domains](https://resend.com/docs/dashboard/domains/introduction)
