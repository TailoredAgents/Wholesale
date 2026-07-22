# Phase 7: Underwriting And Offer Governance

Last updated: July 22, 2026

Status: Complete

## Purpose

Phase 7 makes Stonegate's valuation and seller-price decisions explainable from source evidence to
the final conversation. It separates a valuation recommendation from approved negotiation
authority and separates approved authority from what staff actually present to a seller.

## Operating Workflow

1. Staff reviews property facts, comparable evidence, repairs, ARV, disposition value, and risks.
2. A saved underwriting version produces an opening, target, stretch, and hard seller ceiling.
3. A permitted manager approves that immutable plan. A newer underwriting version makes the plan
   stale until a new plan is approved.
4. The opening offer may be presented directly. Every increase requires a sequential concession
   with a reason and an explicit seller exchange.
5. Concessions through stretch are authorized by the approved ladder. Above-stretch concessions
   require manager approval. Anything above the ceiling is blocked.
6. Price discussions, seller counters, objections, concessions, and agreements are appended to the
   negotiation ledger. Agreements must match the latest governed amount actually presented.
7. Field meeting outcomes reference the exact concession used. A newly approved plan cancels old
   unused authority but preserves all historical evidence.

## User Surfaces

- The lead Underwriting tab contains valuation evidence, immutable versions, offer-plan approval,
  active authority, concession controls, manager decisions, and price-discussion history.
- The mobile Field Acquisitions workspace shows the active ladder, allows a closer to request a
  concession, exposes only usable authorized steps, and blocks ungoverned outcomes.
- Above-stretch requests enter the central Approvals queue and deep-link to the lead's negotiation
  governance section.

## Data And Audit

- `offer_negotiation_plans` preserves approved valuation and authority snapshots.
- `offer_concessions` preserves sequential movement, rationale, seller exchange, status, approval,
  and presentation evidence.
- `offer_negotiation_events` is the append-only conversation and price history.
- `field_negotiation_sessions.governing_concession_id` links the seller-meeting outcome to its
  authority.
- Activity and audit events identify the user, action, amount, source plan, and decision.

## Safety Rules

- AI cannot approve ARV, change offer authority, present a price, or accept an agreement.
- A concession cannot skip the current governed amount or exceed the ceiling.
- Rejected or pending manager exceptions cannot be presented.
- An agreement cannot differ from the latest presented governed amount.
- New evidence creates a new underwriting version; it never silently rewrites approved economics.

## Verification

- Alembic upgrades PostgreSQL from revision `0036` to `0037`.
- API tests cover undocumented offers, automatic ladder authority, pending manager exceptions,
  approval, presentation, agreement, ceiling blocking, event history, and field linkage.
- Python lint, type checks, all API tests, frontend lint, TypeScript checks, and the production web
  build pass.

Optional ATTOM or MLS/RESO enrichment remains behind the property-data adapter until its accuracy
benefit justifies the expense. Final PDF contact and domain branding remains tied to the later
custom-domain decision; neither item weakens the completed governance workflow.
