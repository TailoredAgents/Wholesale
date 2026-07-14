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

Use `Oakwell Home Buyers` as the business-facing company name.

## Consequences

Benefits:

- Clerk should reduce time spent building auth primitives.
- Local development can continue without blocking on branding.
- GitHub push happens before the codebase grows too large.
- Early Render staging will surface deployment issues before advanced product modules are added.

Tradeoffs:

- Clerk introduces a third-party auth dependency.
- User/role mapping must be designed carefully so Clerk identity does not replace internal RBAC.
- Public-facing copy should use Oakwell Home Buyers; domains remain temporary until selected.

## Follow-Up

- Create Clerk project and collect local/staging environment variables.
- Add Clerk environment variables locally and on Render.
- Map the first Clerk user to the local owner user.
- Require MFA for privileged users in Clerk.
- Keep development header auth disabled in production.
