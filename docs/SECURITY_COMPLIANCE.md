# Security And Compliance

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
