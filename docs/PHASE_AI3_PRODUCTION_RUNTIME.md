# Phase AI3: Production Runtime, Tools, And Monitoring

Status: implemented in code on July 23, 2026. Production activation and provider acceptance remain
operator checkpoints.

## Purpose

AI3 extends Stonegate's existing AI orchestrator. It does not create a second AI system. The same
agent definitions, prompt versions, capability contracts, tool permissions, run logs, AI2
datasets, approvals, budgets, traces, promotions, and rollback records remain authoritative.

## Delivered

- OpenAI Responses API structured-output execution behind the existing orchestrator.
- Stateless requests with strict JSON schemas, a hashed safety identifier, prompt cache keys,
  bounded output, timeouts, and at most two attempts.
- Organization-level provider controls and separate per-capability runtime controls.
- High-volume, default, and escalation model routes with environment-controlled model names.
- Disabled-by-default provider and capabilities.
- Read-only, organization-scoped tool execution checked against the agent's existing permission
  registry. No external send or high-risk write tool is exposed.
- Approved and authoritative knowledge retrieval only, using immutable content snapshots.
- A knowledge-use ledger recording source key, exact version, checksum, and reference for each run.
- Context, per-minute rate, per-run spend, daily spend, and circuit-breaker limits.
- Redacted production traces that remove direct contact details and common secret fields.
- Idempotent production runs using the existing run idempotency key.
- One-click provider and all-capability emergency shutdown in the AI Control Center.
- Same-dataset baseline and challenger comparisons with automatic regression blocking.
- Runtime health, source-use, failure, blocked-run, and regression metrics in `/os/ai`.

Migration `0043_ai_production_runtime` adds runtime policies, capability runtime policies,
knowledge-use evidence, evaluation comparisons, and versioned knowledge snapshots.

## Runtime Sequence

1. Authenticate the user and enforce `CHANGE_AI_PROMPTS` for AI control operations.
2. Resolve the organization-scoped agent, active prompt, and capability runtime policy.
3. Reject duplicate idempotency keys by returning the original run.
4. Check provider state, capability state, emergency stop, rate, spend, context, and circuit limits.
5. Execute only the capability's registered read tool within the organization and optional record
   scope.
6. Retrieve only the latest approved authoritative version of each allowed knowledge source.
7. Route the request to the configured model and require the strict Stonegate output schema.
8. Redact the stored input and output trace, record usage and cost, and attach tool and knowledge
   evidence.
9. Return the result as `needs_review`. Human review remains mandatory.

Provider failure records a failed run, increments the circuit breaker, and performs no external
action. Three consecutive failures open the circuit for five minutes by default.

## API Controls

- `POST /api/v1/ai/runtime/install`
- `PATCH /api/v1/ai/runtime/policy`
- `PATCH /api/v1/ai/runtime/capabilities/{capability_key}`
- `POST /api/v1/ai/runtime/execute`
- `POST /api/v1/ai/runtime/shutdown`
- `POST /api/v1/ai/runtime/evaluation-comparisons`

## Production Activation

Keep the provider and every capability disabled until these steps are complete:

1. Deploy migration `0043_ai_production_runtime`.
2. Install the portfolio, AI1 foundation, AI2 library, and AI3 runtime from `/os/ai`.
3. Complete executive and role-owner review of the production AI2 datasets.
4. Confirm `OPENAI_API_KEY`, model-route values, pricing, timeout, daily budget, and alert routing.
5. Run the approved evaluation dataset against the intended prompt and model configuration.
6. Compare it with the accepted baseline and confirm no regression is blocked.
7. Enable the OpenAI provider.
8. Enable only the first approved draft-only capability.
9. Review every trace during the pilot and use emergency stop for unexpected behavior.

The first production capability should be `lead.next_action` in draft-only mode. Seller
communication, offers, contracts, buyer selection, payments, commissions, and legal
representations remain human-controlled.

## Remaining Acceptance Work

- Select and configure a production error-monitoring provider and alert destination.
- Run real OpenAI replay against the approved, redacted AI2 datasets after dataset signoff.
- Record latency, cost, correction, and failure baselines from the first controlled pilot.
- Verify emergency shutdown and circuit recovery in the Render staging environment.

Implementation follows the official OpenAI Responses API, structured outputs, and function-tool
guidance:

- https://developers.openai.com/api/reference/resources/responses/methods/create
- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/docs/guides/function-calling
