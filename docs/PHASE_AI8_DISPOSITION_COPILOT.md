# Phase AI8: Disposition Copilot And Buyer Intelligence

Last updated: July 23, 2026

## Status

The provider-independent foundation is complete in code and `disposition.match` is enabled in
draft-only mode with mandatory human review. Buyer-data provider evaluation, approved campaign
delivery, production model replay, and a measured pilot remain integration or operator
checkpoints.

## Delivered

- Disposition Copilot is embedded in each case in the existing Dispositions workspace.
- Deterministic placement readiness checks package approval, required property facts, buyer
  ranking, qualification, current proof of funds, offer activity, and backup coverage.
- Risk detection identifies expired proof of funds, missing buyer contact details, below-floor
  offers, overdue or approaching deposits, and missing backup buyers without requiring a model.
- The governed runtime receives only the current disposition case, safe package facts, ranked buyer
  evidence, offers, and engagement history. Seller identity, Stonegate's purchase price, and the
  exact internal floor are excluded from model context.
- Strict output includes package gaps and highlights, explainable buyer recommendations,
  side-by-side offer comparisons, internal actions, relationship-update proposals, risks,
  uncertainties, evidence, and a draft buyer message.
- Generated buyer and offer identifiers must exist in the current case. Buyer names must match the
  CRM, and buyer-facing drafts are rejected if they expose seller identity or restricted internal
  economics.
- Every recommendation is idempotent, linked to its disposition case and governed AI trace, and
  preserved with the evidence used at generation time.
- Staff can accept, correct, or reject guidance. The original output and immutable review evidence
  are retained.
- Copilot execution cannot alter buyer records, select an offer, change economics, release a
  campaign, post to a marketplace, or contact a buyer.

## Provider Track

Stonegate's internal buyer CRM remains the source of truth. External platforms should enrich or
distribute approved records through adapters rather than becoming a second operating system.

1. Begin with organic buyer records, proof-of-funds evidence, offers, outcomes, and relationship
   history already stored in Stonegate.
2. Evaluate DealMachine first for API-driven active-buyer discovery and enrichment at startup
   scale.
3. Reassess PropertyRadar when hyperlocal county coverage justifies another provider.
4. Add InvestorLift only when broad marketplace distribution is operationally and financially
   justified.
5. Defer BatchData until volume supports its cost and its incremental data quality is measured
   against Stonegate's own buyer outcomes.
6. Normalize provider records into Stonegate buyers, criteria, evidence, source, and freshness
   fields; do not expose provider-specific objects to the copilot.
7. Require a human to approve imports, merges, package recipients, campaigns, outreach, economics,
   and final buyer selection.

## Pilot Acceptance

- Build redacted ordinary, incomplete, conflicting, expired-proof, below-floor, no-backup, and
  adversarial disposition cases.
- Measure buyer-match precision, unsupported claims, package corrections, offer-comparison
  corrections, time to reviewed draft, latency, cost, and estimated time saved.
- Track downstream response, deposit, closing, fallout, and backup performance separately from
  model quality.
- Stop the pilot for invented buyer capacity, unverified property claims, seller or internal-floor
  disclosure, external execution, buyer mutation, or offer selection.
- Keep external execution and disposition writes blocked throughout the pilot.

## Verification

Tests cover deterministic readiness and risk calculations, runtime context, strict structured
output, idempotent generation, immutable human review, and zero mutation of buyer selection or
campaign state. API lint, focused copilot tests, the full backend suite, web lint, and the production
web build are required before deployment.
