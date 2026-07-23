# ADR 0002: Auth Provider And Deployment Sequence

## Status

Accepted

## Context

The project is being built locally before pushing to GitHub and deploying to Render. The application needs real authentication before staging can be treated as a protected internal tool, but the local lead workflow should advance far enough to validate the product shape before remote setup.

## Decision

Use Clerk as the initial authentication provider for speed.

Continue local development through:

1. Staff lead editing.
2. Speed-to-lead workflow.

Then:

1. Prepare the repository for GitHub.
2. Push `main` to GitHub.
3. Set up Render staging early.

Use `Stonegate Home Buyers` as the business-facing company name.

## Consequences

Benefits:

- Clerk should reduce time spent building auth primitives.
- Local development can continue without blocking on branding.
- GitHub push happens before the codebase grows too large.
- Early Render staging will surface deployment issues before advanced product modules are added.

Tradeoffs:

- Clerk introduces a third-party auth dependency.
- User/role mapping must be designed carefully so Clerk identity does not replace internal RBAC.
- Public-facing copy uses Stonegate Home Buyers; Render domains remain deployment fallbacks.

## Follow-Up

- Completed: Clerk project and Render variables.
- Completed: first Clerk user mapped to the local owner.
- Completed: development header auth rejected in production.
- Completed: branded web domain added to Clerk origins and authorized parties.
- Remaining: verify and enforce MFA for every privileged user.
