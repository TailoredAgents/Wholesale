# GitHub Setup

Repository: `TailoredAgents/Wholesale`

## Branch Protection

Protect `main` before additional collaborators start pushing.

Recommended rules:

- Require pull requests before merging.
- Require status checks to pass before merging.
- Require the `API` and `Web` CI jobs.
- Require conversation resolution before merging.
- Block force pushes.
- Block branch deletion.
- Require linear history once the team is comfortable with squash/rebase merges.

## Initial Labels

Create these issue labels:

- `area:api`
- `area:web`
- `area:worker`
- `area:auth`
- `area:crm`
- `area:bookkeeping`
- `area:ai-agents`
- `area:deployment`
- `type:bug`
- `type:feature`
- `type:hardening`
- `type:docs`
- `priority:p0`
- `priority:p1`
- `priority:p2`
- `blocked`

## CI

The current GitHub Actions workflow runs:

- API lint.
- API typecheck.
- API test suite.
- Web production build.

Web lint is intentionally not required yet because local `eslint` hangs before diagnostics.
