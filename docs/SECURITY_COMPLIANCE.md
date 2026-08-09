# Security And Compliance

Last updated: August 8, 2026

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
- Scope the approval API and Tasks approval feed by request-type permission. Only `audit:view`
  grants blanket organization-wide approval visibility; it does not grant decision authority.
  Governed decisions still require the permission for that exact request type, and unknown request
  types fail closed.

## Current Auth Pattern

Clerk is the selected authentication provider. FastAPI verifies Clerk session JWTs and maps Clerk
subjects to local RBAC users. `APP_ENV` accepts only `local`, `test`, or `production`. Production API
startup stops when the Clerk issuer, explicit or issuer-derived JWKS endpoint, secret key, or a
non-local HTTPS authorized party is missing. Protected web routes return `503` in production when
Clerk keys are unavailable instead of passing through unauthenticated.

`X-Dev-User-Email` is disabled by default and is accepted only in local or test environments that
explicitly set `DEV_AUTH_ENABLED=true`. Production rejects that header regardless of the flag.

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

## Webhooks And Public Write Surfaces

- Resend and Twilio callbacks use provider signature validation plus idempotency records. SignWell
  webhook verification binds an organization-specific webhook credential to that organization's
  envelope; duplicate, stale, and out-of-order events are retained without regressing terminal
  state. The legacy global SignWell credential fails closed once envelopes span organizations.
- The implemented SignWell HMAC covers event type and event time, not the document ID, signer, or
  complete payload body. Organization binding prevents cross-tenant mutation but does not by itself
  prove every within-organization field. Production acceptance must reconcile the document,
  recipients, status, and completed PDF against the SignWell API before Stonegate treats the event
  as execution evidence.
- The Facebook Lead Ads route used by Zapier is an intentional Owner-approved exception: it is
  secretless and publicly reachable. It checks the configured Page ID, required production form-ID
  allowlist, schema and request size, an in-process burst limit, a database-backed rolling daily
  acceptance cap, and organization-scoped provider-lead deduplication.
- Page and form IDs are asserted by the caller. Those controls reduce abuse and provider-cost risk
  but do not cryptographically prove Meta or Zapier provenance. Monitor Zap History, form IDs,
  accepted-event volume, daily-circuit responses, and unexpected CRM records during live campaigns.
- Seller creation, seller enrichment, public conversion events, and Zapier intake use route-keyed
  process-local limits whose key stores are hard-bounded. Production key derivation uses the
  edge-owned Cloudflare client address and ignores caller-supplied `X-Forwarded-For`; the origin must
  be configured so only the trusted edge can supply that header. Before scaled traffic or multiple
  API instances, pair these guards with distributed edge/WAF controls.
- Resend retry leases use a UUID claim fence, and validated inbound routing is checkpointed before
  later provider or attachment work. Restricted aliases cannot auto-route or be manually assigned
  to standard-visibility conversations. Terminal events are visible only to email managers and
  require a reason-bearing audited requeue.

## Communication Compliance

Store consent source, wording, version, timestamp, channel, revocation, suppression, quiet hours, recording disclosure, template approval, and complaint history.

Deterministic code must check eligibility before every outbound communication.

Stonegate's dedicated A2P Campaign covers opted-in seller follow-up only. It does not authorize cold
SMS or transferred consent. Internal new-lead alerts are a separate staff operational use case.

The Owner-selected Georgia-only one-party operating mode may leave the spoken recording disclosure
blank while recording the `one_party_consent` authorization state and applying the selected
retention and access controls. The operational/legal policy still requires documented production
acceptance. That decision does not automatically apply to calls involving another state; Stonegate
must review the applicable recording policy before expanding beyond the selected mode.

Cold-call batches do not require imported DNC evidence. A blank or unknown imported DNC value does
not block a prospect. An explicit do-not-call value, a seller opt-out, or active Stonegate company
suppression still blocks outbound contact.

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
- Complete controlled Resend retry, dead-letter, attachment-limit, routing, bounce, and restricted-
  mailbox acceptance.
- Complete production acceptance of SignWell organization binding, duplicate/stale/out-of-order
  webhook handling, remote signature, iPad signature, authority staleness, completed-document
  retrieval, and failure recovery before a live seller contract.
- Decide whether optional malware scanning will be activated before broad document and attachment
  intake. The current configuration can preserve a `not_configured` scan state; it is not malware
  detection.
- Maintain Python and Node dependency audits as release gates and investigate every high-severity
  result before deployment.
- Retain an explicit risk decision and monitoring procedure for the secretless Zapier route and
  process-local public throttles; keep origin/header trust restricted and add distributed edge
  controls before scale.
- Do not represent a disposition campaign as delivered while the current release action records
  simulation evidence only. Use an accepted controlled manual procedure or implement live delivery.
- Review recording, calling, email outreach, DNC, and state-specific requirements with qualified
  counsel before broad production campaigns.
