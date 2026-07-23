# Phase AI9: Finance, Marketing, And Executive Copilots

Last updated: July 23, 2026

## Status

The provider-independent foundation is complete in code. `finance.reconcile`,
`marketing.analyze`, and `operations.brief` are enabled in draft-only mode with mandatory human
review. QuickBooks or controlled accounting delivery, Google Ads and Meta delivery, production
model replay, redacted evaluation datasets, and measured pilots remain integration or operator
checkpoints.

## Shared Controls

- All three copilots use the existing AI1-AI3 control plane, model routing, budgets, traces,
  approved knowledge, shutdown controls, and external-action block.
- One immutable management recommendation and review ledger records capability, reporting period,
  evidence snapshot, model trace, original output, correction, reviewer, and estimated time saved.
- Strict output separates confirmed facts, exceptions, analysis, draft internal actions, human
  decision requests, uncertainties, evidence, and confidence.
- Every conclusion and proposed action requires supporting evidence.
- Deterministic health, gaps, exceptions, and metric cards remain available without a model.
- Management prompts use aggregate, period-bounded records and exclude seller identity and contact
  details.
- No copilot can mutate its source records or execute an external action.

## Finance Copilot

Delivered:

- Embedded above the existing Finance ledger and exception workflow.
- Reviews period summary, prior-period summary, pending and unlinked revenue, compensation
  calculations, active rules, and deal reconciliation exceptions.
- Detects negative company net, missing linkage, uncollected revenue, unapproved reconciliations,
  below-target margin, and missing compensation policy evidence.
- Drafts evidence-backed analysis and internal decision requests only.

Blocked authority:

- Funded status, reconciliation approval, compensation changes, reserves, distributions, payments,
  accounting posting, and tax classification.

## Marketing Copilot

Delivered:

- Embedded above the existing Marketing source-economics and funnel workflow.
- Reviews attribution, campaign spend, leads, contracts, collected revenue, cost per lead and
  contract, ROAS, public funnel events, Core Web Vitals, and pending offline conversions.
- Flags spend without dependable outcomes, inadequate samples, form loss, missing performance
  evidence, and pending provider delivery.
- Drafts controlled experiment and data-quality recommendations only.

Blocked authority:

- Budget, campaign, creative, audience, attribution, provider delivery, published experiments, and
  offline-conversion submission.

## Executive Copilot

Delivered:

- Embedded on the owner dashboard and protected by financial-view permission.
- Combines aggregate pipeline, task, assignment, appointment, finance, marketing, reconciliation,
  provider-failure, and governed AI-run signals.
- Produces an evidence-backed operating brief with priorities, bottlenecks, decision requests, data
  gaps, and source timestamps.
- Separates current facts and recommendations through the shared strict output contract.

Blocked authority:

- Staffing, priorities, budgets, permissions, market launches, exception approval, payments,
  offers, buyers, and AI authority.

## Provider Track

1. Keep Stonegate's ledgers and CRM records as the source of truth.
2. Add controlled QuickBooks Online import/export or synchronization only after account mapping,
   duplicate protection, reconciliation, and rollback are approved.
3. Add Google Ads and Meta offline-conversion adapters only after account, event, attribution,
   consent, idempotency, and delivery monitoring are approved.
4. Normalize provider status and errors into Stonegate records; do not let provider objects become
   the copilot's primary data model.
5. Require a human to approve every accounting, compensation, budget, campaign, conversion, and
   management action.

## Pilot Acceptance

- Build redacted normal, incomplete, conflicting, stale, small-sample, negative-margin,
  attribution-gap, provider-failure, and adversarial cases for all three capabilities.
- Finance must identify every material unexplained difference and never invent an accounting fact.
- Marketing must identify sample and attribution limits and never present correlation as confirmed
  causation.
- Executive briefs must identify source periods and never expose seller-level information.
- Measure factual accuracy, evidence coverage, correction rate, critical failures, latency, cost,
  time saved, and downstream management outcomes separately by capability.
- Stop a pilot for unsupported financial claims, missing material exceptions, private-data
  exposure, false execution claims, source mutation, or external action.

## Verification

Tests run all three capabilities through the governed runtime, confirm strict schemas and enabled
draft-only status, verify prompt minimization, exercise idempotent generation and immutable review,
and assert that revenue, spend, task, and external state remain unchanged.
