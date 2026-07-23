# Phase AI10: Controlled External Automation

Last updated: July 23, 2026

## Status

The AI10 control plane is implemented. External delivery is not activated.

Stonegate can install, owner-review, simulate, pause, resume, and audit four candidate action
contracts from the Automation view in `/os/ai`:

1. Consented seller acknowledgement by SMS.
2. Appointment confirmation and reminder by SMS.
3. Consented seller follow-up by SMS.
4. Approved buyer-campaign delivery by email.

## Control Contract

Every policy records:

- Named human owner, governed capability, channel, and provider.
- Eligible audience and suppression requirements.
- Accepted consent sources and prohibition on overriding STOP or unsubscribe.
- Approved template family and prohibition on freeform generation.
- Contact-hour, timezone, and frequency rules.
- Per-run, per-recipient, daily volume, and cost ceilings.
- Evaluation thresholds and minimum reviewed samples.
- Initial canary audience, daily volume, human-review percentage, and observation period.
- Automatic-pause conditions, rollback behavior, and human takeover.
- Actions that remain prohibited regardless of model output.

## Runtime Behavior

AI10 simulations accept only control facts: audience count, estimated cost, and boolean evidence
that consent, template, contact hours, frequency, suppression, and human takeover were verified.
They do not accept seller, buyer, property, message, or contact data.

Every simulation:

- Applies the policy and canary limits deterministically.
- Includes runtime, capability, evaluation, provider, owner-approval, and release-lock checks.
- Is idempotent.
- Stores its checks and blockers in an immutable attempt record.
- Records `external_delivery_attempted=false` and `delivered_count=0`.
- Writes an audit event.

The API has no activation or delivery endpoint in this release.

## Safety Controls

- Global external actions remain disabled in the AI runtime.
- Every policy defaults to `dry_run_only=true`.
- Every policy defaults to `external_delivery_enabled=false`.
- A policy can be paused immediately without affecting its evidence history.
- The existing AI emergency stop disables the provider and all capabilities.
- Resuming a policy restores control simulations only; it does not enable delivery.

Autonomous authority remains prohibited for cold AI voice, binding offers, price concessions,
contracts, signatures, legal interpretations, final buyer selection, material economics,
payments, commissions, budgets, permissions, suppression overrides, and destructive deletion.

## Data Model

Migration `0052_ai10_action_controls` adds:

- `ai_external_action_policies`
- `ai_external_action_attempts`

## Activation Gate

A future activation must be a separate reviewed release. Before one action can enter a live
canary, Stonegate must provide:

1. Approved provider configuration and monitored delivery callbacks.
2. Owner-approved control contract.
3. Approved consent source and suppression behavior.
4. Approved immutable message template.
5. Approved evaluation dataset and a passing model run with zero critical failures.
6. Human takeover and alerting readiness.
7. Named rollback owner and completed shutdown test.
8. Canary review with explicit audience, volume, duration, and success thresholds.
9. Market-specific legal and compliance approval.

Only the selected action may be activated. Passing one action does not authorize another channel,
audience, provider, template, or market.

## Verification

- Full backend suite passes with 134 tests.
- Alembic recognizes `0052_ai10_action_controls` as the single head.
- PostgreSQL offline migration generation passes.
- Frontend lint, TypeScript, and production build pass.
