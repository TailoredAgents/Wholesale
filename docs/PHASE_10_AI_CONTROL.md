# Phase 10 AI Control Plane

Last updated: July 23, 2026

Status: AI1-AI10 control planes are implemented in code. Production signoff, provider adapters,
redacted model replay, measured pilots, and any future action-specific activation remain.

`AI_AGENTS.md` defines the complete technical architecture. Production acceptance order is in
`AI_AUTOMATION_ROADMAP.md`.

## Delivered

Stonegate now has a governed AI lifecycle instead of disconnected agent prompts:

1. Install the 14-agent operating portfolio from `/os/ai`.
2. Inspect each agent's autonomy, budget, retry limit, and tool permissions.
3. Register idempotent business events and run policy-only dry runs without model spend.
4. Review or flag traces, including simulated and blocked tool calls.
5. Version and approve evaluation datasets with explicit pass and critical-failure thresholds.
6. Run deterministic fixture evaluations before spending money on model replay.
7. Request capability promotion only from a passing evaluation.
8. Require a separate human approval before promotion becomes effective.
9. Roll back an approved capability immediately; rollback pauses the agent for owner review.

## Safety Boundary

- Baseline autonomy is `observe`.
- Baseline agents can read and draft; execute tools are `write_blocked`.
- `execute_external` is not an accepted promotion level.
- Offers, contracts, buyer selection, payments, compensation, access, and legal or financial
  decisions remain human-controlled.
- Idempotency keys prevent duplicate governed runs.
- Per-run and daily budgets are checked before a run.
- Retry attempts are bounded by the agent definition.

## Promotion Standard

A capability can move from observe to draft, recommend, and narrow internal execution only when:

- its approved dataset has enough representative cases;
- the latest evaluation meets pass-rate, critical-failure, latency, and cost thresholds;
- the owner reviews the trace and evaluation evidence;
- a separate approval request is approved;
- monitoring and a named rollback owner are active.

The included fixture harness proves the control flow. It does not prove model quality. Before a
real pilot, replace fixture examples with redacted Stonegate calls, leads, appointments,
underwriting cases, transactions, and corrections, then run model replay against that set.

## Next Acceptance Work

Complete AI3 production monitoring and AI2 role-owner signoff, then measure each active draft-only
copilot separately. Review AI10 control contracts and blocked readiness simulations while
dedicated Twilio and Google Workspace setup is completed. Do not activate external delivery based
on generic datasets or another capability's pilot.
