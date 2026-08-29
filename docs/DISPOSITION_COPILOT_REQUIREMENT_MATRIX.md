# Disposition Copilot DS9 Requirement And Evidence Matrix

Last updated: August 29, 2026

## Status

DS9 is a governed, **draft-only** Disposition Copilot contract. The repository implementation may
be verified independently from the measured production pilot. The production pilot is **NOT MET**
until the minimum reviewed sample and every quality, evidence, authority, and traceability gate in
this document pass.

No readiness score, favorable model output, accepted draft, global AI setting, or external-action
policy promotes this capability beyond draft-only assistance.

## Permanent Authority Boundary

The Copilot may summarize, classify, compare, draft, and propose. It may not:

- release email, SMS, a buyer campaign, or an InvestorLift handoff;
- contact a buyer or seller;
- create, activate, merge, suppress, or change a Buyer record;
- accept an offer, select or replace a buyer, change deal economics, or change a package;
- execute or release an assignment, contract, deposit, closing, payment, or funded state; or
- treat a recommendation review as approval for a separate governed workflow.

Only an authorized person can perform those actions through their existing deterministic controls.
Every DS9 response and recommendation record must state that its external-action authority is
false. That invariant does not depend on organization-level AI automation settings.

## Requirement-To-Evidence Matrix

| ID | Requirement | Durable implementation evidence | Required verification |
| --- | --- | --- | --- |
| DS9-R1 | Prepare a fact-checked package summary and identify missing evidence | Structured package-summary draft and package-gap fields linked to the current House disposition case, nested public property facts and readiness evidence, and the current evidence fingerprint | Normal, incomplete, conflicting, nested-property, and stale-package tests; package-fact evaluation |
| DS9-R2 | Explain buyer-match strengths, conflicts, and disqualifiers | Structured buyer recommendations identify the saved Buyer and cite current match, criteria, proof, and eligibility evidence | Eligible, expired-proof, suppressed/ineligible, conflict, and out-of-pool tests; match-relevance evaluation |
| DS9-R3 | Draft recipient segments, email, SMS, call briefs, and follow-ups | Typed draft records retain content, purpose, required human review, and current case/package citations; Buyer-scoped drafts also cite the exact saved Buyer | Contract test for all draft types and citation scope; no delivery, campaign, provider, or Inbox mutation regression |
| DS9-R4 | Classify replies, inquiries, passes, offer intent, offers, opt-outs, wrong-person replies, and uncertain replies | Typed classification, confidence, cited saved evidence, and review-required state | Label fixtures, uncertain/adversarial fixtures, citation validation, reply-classification evaluation |
| DS9-R5 | Recommend the next call, proof request, showing, counter, deadline action, backup review, or another bounded next step | Typed next-action proposal with rationale, confidence, citations, and human-action requirement | Useful, unsupported, conflicting, and prohibited-action fixtures; next-action evaluation |
| DS9-R6 | Compare offer differences and execution risk without choosing the buyer | Saved-offer identifiers, buyer identifiers, execution-risk explanation, and citations | Offer comparison tests plus zero selection, offer, economics, and coverage mutation assertions |
| DS9-R7 | Propose buyer preference and reliability updates for human review | Typed buyer-update proposal names the saved Buyer, proposed field/value, reason, citations, and human-approval requirement | Valid/invalid Buyer tests and zero Buyer-profile mutation assertions |
| DS9-R8 | Retain model, prompt, evidence, output, correction, cost, and reviewer trace | Recommendation stores evidence fingerprint and citations; AI trace stores model, prompt version, token use, cost, latency, and timestamps; review stores reviewer and final decision | Persistence/read-contract tests, database migration contract, and 100% trace-attribution pilot gate |
| DS9-R9 | Support accept, correct, reject, and ignore | One immutable review per recommendation records the decision, optional corrected output, quality evaluation, reviewer, and time; a second review is rejected as a conflict | Tests for all four decisions, duplicate-review conflict, and edited-payload revalidation |
| DS9-R10 | Cite saved Stonegate or approved-provider evidence for every material recommendation | Each material draft, match, classification, next action, offer comparison, and Buyer update references scoped structured citations; each citation identifies source type, source ID, saved fact, status, and observation time; reviewed provider evidence is public/redacted and contains no Buyer phone or email | Unsupported, fabricated, foreign-case, wrong-Buyer, missing-citation, and provider-PII rejection tests; zero-unsupported-citation pilot gate |
| DS9-R11 | Preserve organization, role, economics, and asset boundaries | Organization-scoped queries; House-only analysis; private-economics permission for generation/review; redacted overview for users without that permission | Cross-organization 404/withholding, RBAC 403, and Land-block tests |
| DS9-R12 | Make retries safe and stale reviews visible | Idempotency is bound to organization, case, key, and evidence fingerprint; the fingerprint covers material evidence, privacy-safe contact availability, and time-derived proof/deposit freshness without storing raw contact data | Same-request replay, cross-case key collision, changed-evidence key conflict, clock-only proof/deposit staleness, and stale accept/correct rejection tests |
| DS9-R13 | Prevent direct or indirect binding action | Authority fields are constant false; generation and review write only recommendation, review/evaluation, AI trace, and audit evidence | Before/after counts and state assertions for outreach, provider handoff, buyers, offers, selection, package, transaction, and communications |
| DS9-R14 | Measure quality before any future capability decision | Quality evaluation captures hallucination, package correction, match relevance, reply accuracy, next-action usefulness, and reviewer notes | Aggregate-metric tests and minimum-sample/domain-coverage gate |

Application code and migrations remain the truth about whether each evidence field exists. This
matrix defines the acceptance contract; it does not by itself prove an implementation or pilot.

## Review Semantics

- **Accept:** the reviewer confirms the cited draft is useful as written. It does not apply or send
  anything.
- **Correct:** the reviewer saves a replacement structured draft that passes the same citation and
  authority validation. It does not apply or send anything.
- **Reject:** the reviewer records that the draft is wrong, unsupported, unsafe, or not useful.
- **Ignore:** the reviewer deliberately closes the recommendation without judging its quality or
  applying it. Ignored recommendations are reported separately and do not count toward the
  measured quality sample.

One recommendation may have only one immutable review; a second submission returns a conflict
instead of silently replaying or replacing the first decision. A later change to the saved evidence makes
acceptance or correction of the earlier draft stale; staff must generate a current recommendation.
Reject and ignore remain available so the historical draft can be closed honestly.

## Measured Pilot Gates

The pilot uses the cumulative retained DS9 review history; the 30-day operating metrics do not reset
its evidence. It is measured only after at least **50 decisive human reviews** across at least **10
distinct House disposition cases**. A decisive review is accepted, corrected, or rejected; ignored
drafts are tracked but do not satisfy the sample. The set must include normal, incomplete,
conflicting, policy-blocked, stale, and adversarial examples. Each applicable scored quality domain
must also contain at least **10 decisive evaluations** so a high aggregate score cannot conceal an
untested package, Buyer-match, reply-classification, or next-action capability.

| Gate | Passing threshold |
| --- | --- |
| Critical authority or binding-action violations | Exactly 0 |
| Unsupported, fabricated, missing, or foreign-case citations | Exactly 0 |
| Package-fact correctness | At least 90% |
| Buyer-match relevance | At least 80% |
| Reply-classification accuracy | At least 90% |
| Next-action useful or correctable | At least 80% |
| Reviewer accept-or-correct rate | At least 80% |
| Model, prompt, evidence, output, cost, and reviewer attribution | 100% |
| Domain coverage | All required normal, incomplete, conflicting, blocked, stale, and adversarial groups represented |
| Per-quality-domain sample | At least 10 applicable decisive evaluations for package facts, Buyer matching, reply classification, and next actions |

Correction rate, ignore rate, reject rate, latency, token use, cost, and time saved must be reported.
They are diagnostic metrics, not targets that may be improved by hiding difficult cases. P95
latency and average cost receive an owner-approved budget only after a real baseline exists; they
must still be captured for every measured run.

An accept-or-correct rate cannot override a failed authority, citation, traceability, sample-size,
or domain-coverage gate. Passing DS9 does not authorize autonomous outreach, Buyer mutation, buyer
selection, offer acceptance, economics changes, contract release, or funding.

## Verification Evidence

Repository acceptance must include:

1. Backend governance and regression tests for DS9-R1 through DS9-R14.
2. A migration contract proving full structured output and quality evaluation are retained without
   the former summary-length cap.
3. A frontend contract test proving all four review choices, citations, stale state, pilot status,
   and draft-only authority are visible and that no Copilot control is labeled as a send, apply,
   select, accept-offer, release, or publish action.
4. Existing Disposition package, matching, outreach, InvestorLift manual handoff, Offer Room,
   buyer-selection, transaction, and permission suites.
5. Type checking, linting, production build, migration-head validation, documentation link checks,
   and whitespace validation.
6. A later owner-approved production evaluation export demonstrating the minimum sample and every
   measured-pilot gate above. Until that evidence exists, the UI and documentation must continue to
   say **Pilot not met**.
