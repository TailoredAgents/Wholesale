# Security And Compliance

Last updated: July 24, 2026

## Highest Risks

- Contacting opted-out sellers.
- Losing consent evidence.
- Unauthorized financial, compensation, document, or recording access.
- AI implying binding offers or legal advice.
- Webhook spoofing.
- Insecure file access.
- Unlicensed data use.
- Sensitive logs.

## Access Control

- Use least privilege.
- Scope data by organization.
- Use roles plus granular permissions.
- Use service identities for AI and integrations.
- Audit material reads/writes.

## Current Auth Pattern

Clerk is the selected authentication provider. FastAPI verifies Clerk session JWTs and maps Clerk subjects to local RBAC users. Local development can still use `X-Dev-User-Email`; production rejects that header and requires a Clerk bearer token.

Each staff member and contractor requires an individual Clerk login. Credentials must never be
shared. Restricted VA permissions are enforced by the API, not only by hidden navigation.

## Secret Handling

- Do not commit `.env` files or real credentials.
- Keep Render and Clerk secrets in their hosted dashboards.
- Use `.env.example` for variable names only.
- Before pushing deployment changes, run a tracked-file secret scan such as:

```bash
git grep -n -E "(sk_live|pk_live|CLERK_SECRET_KEY=.+|DATABASE_URL=.*:.*@|password=|secret=)" -- ':!*.lock'
```

- Treat any positive match as a blocker unless it is an intentionally blank template variable or documentation example.

## Communication Compliance

Store consent source, wording, version, timestamp, channel, revocation, suppression, quiet hours, recording disclosure, template approval, and complaint history.

Deterministic code must check eligibility before every outbound communication.

Stonegate's dedicated A2P Campaign covers opted-in seller follow-up only. It does not authorize cold
SMS or transferred consent. Recording remains disabled until the spoken disclosure and retention
policy are approved for the operating states.

Cold-call batches require a valid normalized phone, retained clear DNC evidence, and no active
Stonegate Voice suppression. A blank or unknown imported DNC result is review-only. The current
system retains vendor or manager-review evidence but is not itself a live national DNC provider.

F3 adds a versioned owner policy and evidence workspace at `/os/compliance`. National DNC evidence
must be clear and no more than 31 days old when the record enters a batch and again when a caller
starts it. DNC source records retain provider type, area-code coverage, approval, last refresh,
next due date, and an external evidence reference.

Seller email requires a recorded `email` consent record and no active `email` or `all` suppression.
SMS and Voice retain their channel-specific consent, suppression, provider, and contact-hour
checks. Staff cannot override these gates from the UI.

Recording configuration no longer activates recording by itself. Stonegate also requires an
active `call_recording_retention` policy with current external legal-review evidence. The reviewed
policy and employee training are operational prerequisites; they do not replace legal advice or
provider acceptance.

Compliance incidents, training assignments, employee attestations, manager decisions, and control
runs retain organization scope and append-only audit events. Detailed external acceptance steps
and official FTC/Twilio references are in `PHASE_F3_COMPLIANCE_POLICY.md`.

The VA workbench queries only batch entries assigned to the current caller. It never exposes raw
import files, unrelated prospects, underwriting, buyers, contracts, finance, or exports. Only an
approved script can start an attempt, one caller can hold only one active record, and every outcome
is audited. Warm handoffs require acquisitions review; prior attempts remain immutable when a
handoff is returned for correction.

## Production Hardening Still Required

- Verify privileged-user MFA.
- Complete a secret inventory and rotation process.
- Test user deactivation and access revocation.
- Test database restore.
- Add error monitoring and operational alerts.
- Review recording, calling, email outreach, DNC, and state-specific requirements with qualified
  counsel before broad production campaigns.
