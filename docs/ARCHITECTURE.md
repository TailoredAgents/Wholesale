# Architecture

Last updated: July 22, 2026

## Stack

- Frontend: Next.js 16 App Router, React 19, TypeScript.
- Backend: FastAPI, Pydantic, SQLAlchemy, Alembic.
- Authentication: Clerk, with local RBAC remaining authoritative for permissions.
- Database: PostgreSQL.
- Worker: `apps/api/app/worker.py` for provider synchronization, transcription, and retention.
- Coordination/cache: Render Key Value-compatible Redis.
- Files later: private S3-compatible object storage.
- AI: Stonegate orchestrator and policy control plane with OpenAI Responses API model execution.
- Hosting: Render Blueprint connected to GitHub `main`.

Official docs checked:

- https://nextjs.org/docs
- https://fastapi.tiangolo.com/tutorial/sql-databases/
- https://render.com/docs/blueprint-spec
- https://developers.openai.com/api/docs/guides/latest-model
- https://developers.openai.com/api/docs/guides/agents
- https://developers.openai.com/api/docs/guides/agent-evals

## Monorepo

```text
apps/web
apps/api
apps/worker
docs
```

## Runtime Boundaries

- `apps/web` renders both public pages and authenticated OS routes.
- `apps/api` owns business rules, authorization, provider adapters, and all material writes.
- The Render worker runs `python -m app.worker` from `apps/api`; the original `apps/worker`
  heartbeat scaffold is not the production worker.
- PostgreSQL stores business records, provider identifiers, evidence, and audit history.
- Provider files stay private and are proxied through permission checks until object storage is
  introduced.
- Browser code receives Clerk sessions and short-lived provider tokens only, never raw provider
  secrets.

## AI Runtime

- PostgreSQL stores agent definitions, prompt versions, tool policies, evaluation cases, runs,
  approvals, traces, costs, promotions, and rollbacks.
- Domain events enter the orchestrator after deterministic policy checks. The orchestrator selects
  a specialist capability, approved context, model tier, and narrow tools.
- The Responses API is the default model interface. The OpenAI Agents SDK may be used behind the
  existing orchestrator when typed tools, specialist composition, resumable approvals, or tracing
  reduce implementation work.
- Models return structured proposals with evidence and uncertainty. Backend domain services, not
  model text, perform permitted writes.
- PostgreSQL is durable memory. Temporary model conversation state cannot create an independent
  seller, buyer, deal, consent, or financial record.
- Side-effect tools require stable idempotency keys. External tools additionally require the exact
  approval and compliance policy defined for that capability.
- Model, prompt, schema, tool, or reasoning changes create a version that must pass replayable
  evaluation before promotion.
- See `AI_AGENTS.md` for technical policy and `AI_AUTOMATION_ROADMAP.md` for delivery order.

## Rules

- Major records carry `organization_id`.
- Material writes use transactions and audit events.
- Business rules live in backend domain services.
- Webhooks validate provider signatures and retain provider event identifiers for idempotency.
- AI tools must be narrow, permissioned, structured, and audited.
- Offers, contracts, buyer selection, payments, commissions, permissions, suppression overrides,
  and legal or financial decisions remain human-controlled.
- Public seller pages and private OS routes remain separate experiences.
- Integration configuration uses the existing `oakwell-*` Render resources even though the
  customer-facing brand is Stonegate.
