# Phase 1 Start

Status: Historical and completed.

This file preserves the original foundation build order. Use `../CURRENT_STATE.md` for the current
baseline and `../ROADMAP.md` for active development.

## Build Order

1. Initialize monorepo.
2. Scaffold web, API, and worker.
3. Add local database and migrations.
4. Add bootstrap seed data.
5. Add RBAC.
6. Add auth provider.
7. Add lead CRUD.
8. Connect dashboard to API data.

## Do Not Start Live Operations Until

- Legal consent text is approved.
- Communication compliance gates are tested.
- Auth and RBAC tests pass.
- Secrets are outside the repository.

The foundation requirements above were implemented. Provider-specific production launch gates
remain documented in the current roadmap and integration runbooks.
