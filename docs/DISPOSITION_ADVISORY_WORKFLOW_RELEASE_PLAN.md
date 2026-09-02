# Disposition Advisory Workflow Release Plan

Last updated: September 1, 2026

## Release Contract

Dispositions is an operator-led desk. Setup, package-readiness, proof, coverage, and backup items are
an informational checklist and never workflow locks. Authorized staff may shop an incomplete deal,
review the full buyer pool, choose any buyer, and rank, call, follow up, log activity, or record an
offer in the order the situation requires. Checklist numbering, severity, status, and suggested
actions never create a required first step or completion sequence.

Hard stops are limited to:

- organization isolation and narrow RBAC;
- STOP, Do Not Contact, and active suppression rules;
- a usable destination/sender and available provider for the chosen external action;
- explicit paid-provider preview, credit/budget, tier-sequencing, idempotency, and interrupted-spend
  reconciliation controls for a new DealMachine search; and
- truthful selected-buyer, signature, assignment, deposit/waiver, and funding evidence when the
  system records a legal or financial result.

Paid-search spend governance limits only the new provider request. It never blocks the owned Buyer
Network, manual shopping, a saved-result review, or another ordinary disposition action.

Exact package, outreach, manual provider-handoff, and buyer-selection approvals stay versioned and
audited. The standard Disposition representative has those narrow disposition permissions,
including `dispositions:send_bulk_outreach` for governed Dispositions release, without the global
marketing permission `communications:send_bulk`, user administration, operating-policy, Finance,
or unrelated approval authority. No manager wait is part of the normal desk workflow.

The role desk is first-class in the left navigation but remains backed by canonical Deal and
Disposition Case records. Active Deal cards provide direct **Packet**, **Find buyers**, **Reach
out**, and **Offers** actions. The checklist is visible but collapsed by default. Buyer ranking is
performed in **Find buyers**, exact recipient preparation in **Bulk outreach**, one-at-a-time work
in **One-to-one**, manual InvestorLift handoff under **More > External distribution**, and finance
reconciliation through Deal Finance.

## Phased Release And Acceptance

### 1. Access And Data Foundation

- Migration `0123_disposition_advisory` makes case owner, compensation-plan version, and operating
  mode nullable and adds advisory/version provenance fields without deleting or rewriting existing
  case setup or provenance values.
- Every executed supported House or Land transaction creates or reuses exactly one case, including
  when setup is incomplete. Later configuration hydrates the same case.
- Existing cases preserve their IDs, status history, package versions, offers, and selections.
- The standard `disposition_rep` receives only the package, outreach,
  `dispositions:send_bulk_outreach`, provider-handoff, and buyer-selection permissions needed for
  the full desk. It does not receive global `communications:send_bulk` marketing authority.

Acceptance: duplicate/retry handoffs return the same case; legacy complete cases are unchanged;
incomplete cases remain visible and mutable; null setup causes no serializer, notification, desk, or
worker exception; cross-tenant and under-permission requests still fail.

### 2. Advisory Desk And Internal Work

- Case status becomes a reporting milestone, not authorization for the next ordinary task.
- The package checklist and desk severity guide attention but do not disable matching, pool access,
  calling, engagement, follow-up, or offer entry.
- Buyer ranking is available from current case facts without an approved package.
- The Buyer pool exposes the full ranked set for work on any appropriate buyer. The separate
  execution queue may present one ranked buyer at a time as a focus view, but it never locks the
  full pool or another disposition action.
- **Pass for this deal** is a durable, reasoned deal-specific decision that keeps the buyer out of
  the current prepared outreach pool. It is reversible through **Undo pass** or a new shortlist
  decision with another reason; it is not a permanent communication restriction or a change to the
  Buyer Network lifecycle.
- A primary buyer can be approved without backup coverage. Proof, minimum-price, qualified-match,
  timing, and backup gaps are saved as advisory evidence.
- On primary fallout, the representative may activate any other viable recorded same-case offer,
  whether or not it was previously a backup, or record **No replacement now**. The latter
  supersedes the active selection, clears active buyer coverage, and reopens ordinary shopping
  without deleting the old selection or outcome.
- Manual closing-protection milestones may be created and worked at any active case stage. A
  whole-deal milestone remains independent of buyer coverage; an optional recorded-offer milestone
  is buyer-specific, while selection-bound and canonical checkpoints continue to follow and protect
  the current approved coverage.

Acceptance: API and UI tests exercise all ordinary actions from `package_prep`, `buyer_matching`,
`marketed`, `offers_received`, and `buyer_selected`; primary-only selection succeeds; an operator
can work a non-first buyer from the full pool without completing the call-queue candidate; a pass
can be reversed without erasing its audit history; fallout can use a non-backup viable offer or no
replacement; warnings remain visible and auditable after action.

### 3. External Actions And Truth Boundaries

- One-to-one SMS/voice and governed outreach recheck organization/role scope, STOP/DNC/suppression,
  destination/sender, line authorization, and provider availability at queue and delivery time.
  Recorded permission labels remain visible but advisory for deliberate human one-to-one buyer
  contact under the existing manual-contact policy; governed bulk and automated delivery continue
  to enforce their applicable permission and release controls.
- DealMachine rechecks the exact paid-search preview, sequential tier, available credits and
  budgets, and unresolved prior spend before incurring a new provider charge; a denial leaves the
  owned Buyer Network and manual work available.
- A shared packet, outreach revision/delivery, provider bundle, or current package download is
  bound to exact bytes and hash and visibly says **Preliminary** when the source package was not
  approved/current. Currentness is recomputed at access, delivery, or download, so source-fact
  drift after preparation downgrades the visible label without rewriting the frozen artifact.
- Approval/release remains explicit and attributable, but the same authorized Disposition
  representative may complete it.
- Assignment and funding validation uses selected-buyer identity, current economics, executed
  signer evidence, deposit evidence or an authorized waiver, and canonical funded evidence. POF,
  match score, floor, timing, and backup findings do not become surrogate funding gates.

Acceptance: every STOP/DNC/suppression and missing-destination/provider scenario fails closed;
deliberate one-to-one contact preserves the recorded-permission advisory label, governed bulk keeps
its release controls, and eligible recipients can be contacted with open checklist items;
preliminary artifacts cannot be mistaken for approved/current ones before or after later source
drift; forged, mismatched, or missing signature/funding evidence is rejected; every approval and
release records actor, reason, exact version/hash, and time.

### 4. Asset And Legacy Acceptance

- House retains generated/external packages, governed outreach, the buyer execution workspace,
  Offer Room, and manual InvestorLift handoff.
- Land retains the exact external-PDF package, asset-aware pool, and supported pre-close engagement
  work. Residential generated packages, automated outreach, execution queue, Offer Room,
  buyer-selection/funding and reconciliation/closing controls, InvestorLift, and Disposition
  Copilot remain unavailable until separately designed and accepted.
- Legacy House and Land cases receive the advisory behavior without cloning cases or backfilling
  invented owners, plans, modes, approvals, proof, or backups.

Acceptance: asset-boundary tests prevent residential, selection, funding, and reconciliation tools
from appearing or running for Land; legacy cases with every historic status can rank/log/record in
the supported surface; existing approved artifacts and links remain byte-identical and traceable.

### 5. Controlled Rollout

Deploy the migration and API before or atomically with the web update. No new product feature flag
is required for checklist semantics; provider-specific enablement and production-acceptance flags
remain unchanged. If rollback is necessary, roll back application behavior first. Do not downgrade
nullable columns until every advisory case has valid setup references, or the database downgrade
would fail and could encourage fabricated backfill.

Run automated tenant, RBAC, workflow-order, communication-compliance, artifact-integrity, and
funding-truth tests, then use one supervised House case and one existing/legacy case. Land receives a
separate smoke pass limited to its supported controls.

## Success Measures

- 100% of eligible executed-contract retries resolve to one visible case, even with incomplete
  owner/plan/mode setup.
- Zero readiness-, package-, backup-, proof-, floor-, rank-, or case-stage validation failures for
  ordinary matching, supported House buyer selection, activity, follow-up, or offer work.
- Zero cross-tenant access, unauthorized disposition approval, suppressed delivery, or false funded
  close in the acceptance suite and controlled rollout.
- 100% of external sends have a current compliance decision, usable destination/sender, provider
  result, actor, and immutable request/revision identity.
- Operators can begin a buyer action on the same day as contract execution while unresolved
  checklist items remain visible.
- Backup coverage and package/proof gaps remain measurable warnings rather than disappearing after
  the operator continues.

## Principal Risks

- Old status checks can silently recreate the sequence even after the UI becomes advisory.
- Nullable setup references can break desk reads, staff alerts, reconciliation, or serializers that
  still assume a user/plan/mode exists.
- Reusing one `readiness_blockers` collection for both warnings and funding truth can over-block
  valid operator decisions or under-protect a funded close; keep those decisions separate.
- A preliminary artifact can be mistaken for final outside Stonegate; label its PDF/link/revision
  state at each current access/send/download, preserve exact hash provenance, and never silently
  upgrade it after source facts drift.
- A deal-specific pass can become an accidental permanent exclusion if only the old decision is
  retained; preserve the decision history while exposing a reasoned **Undo pass**/shortlist path.
- Granting broad manager or admin roles to solve approvals would expand authority beyond the desk;
  grant only the named disposition permissions.
- Analytics that equate package approval with the start of disposition will undercount early buyer
  work; measure actual engagement and offer timestamps.
