# Disposition Management Intelligence DS10 Requirement And Evidence Matrix

Last updated: August 29, 2026

## Status

DS10 is a read-only, organization-scoped management dashboard derived from Stonegate's canonical
House disposition records. It explains the retained operational evidence; it does not create a
second source of truth, infer a funded assignment from activity alone, or change any deal, buyer,
offer, selection, transaction, reconciliation, or financial record.

Repository implementation is separate from production acceptance. Metrics with no qualifying
records remain unavailable or zero with their denominator visible. A small sample is descriptive,
not proof that an agent, source, provider, or AI workflow caused an outcome.

## Canonical Evidence Boundary

The dashboard may derive observations from saved Stonegate records for:

- executed House contracts and their disposition cases;
- approved package versions;
- owned-network outreach delivery and linked replies;
- reviewed provider inquiries or offers that have been converted into the applicable canonical
  workflow;
- canonical buyer offers, approved primary or backup selections, deposit evidence, buyer outcomes,
  and funded transactions; and
- approved deal reconciliation when a completed assignment's economic result is shown.

Provider activity, a delivered message, a reply, an inquiry, a nominal offer, a selected buyer, or
a scheduled close is not a completed assignment. Mutable Buyer source labels and current deal
ownership are context, not sufficient historical attribution by themselves.

## Implemented Repository Scope

The current DS10 dashboard is deliberately narrower than the full roadmap vision:

- It derives operational funnel and milestone observations from existing canonical disposition
  records and exposes the underlying sample size.
- It keeps activity measures separate from selected, deposited, and completed outcomes.
- It can describe current buyer reliability from documented buyer outcome records rather than a
  subjective label alone.
- It preserves unknown or incomplete evidence instead of silently assigning a source, agent, or
  economic result.
- It accepts deal, Buyer, agent, source, market, asset-class, and inclusive date-window filters;
  available filter choices are derived from the authorized organization scope.
- It reports existing package-revision, match-override, AI-correction, and backup-save observations
  as derived counts; those counts are not an append-only DS10 correction workflow.
- It is read-only and tenant-scoped.

The current implementation does **not** provide an attributable disposition campaign-cost ledger,
cost-per-outcome reporting, a frozen winning-source attribution decision, append-only management
metric corrections, full split-credit agent attribution, or causal human-versus-AI performance
claims. Those remain follow-up work and must not be inferred from this dashboard.

## Requirement-To-Evidence Matrix

| ID | Requirement | Canonical evidence | Required verification |
| --- | --- | --- | --- |
| DS10-R1 | Show milestone timing without inventing missing events | Executed contract, approved package, sent outreach, linked reply or reviewed inquiry, canonical offer, approved selection, deposit evidence, funded transaction timestamps | Complete, partial, missing, duplicated, future, and out-of-order timeline fixtures |
| DS10-R2 | Separate activity from economic outcomes | Delivery/reply/inquiry/offer counts remain distinct from selected, deposited, and completed assignment counts | A high-message/no-close case cannot increase completed assignment metrics |
| DS10-R3 | Recognize a completed assignment only from canonical completion evidence | Completed buyer outcome and funded transaction, with approved reconciliation required for displayed assignment economics | Missing or conflicting outcome, funding, and reconciliation fixtures remain incomplete and never double count |
| DS10-R4 | Explain every rate with a numerator, denominator, and sample size | Derived funnel counts from the same organization-scoped evidence set | Empty, one-record, mixed-status, and zero-denominator cases return an honest unavailable state |
| DS10-R5 | Keep source reporting evidence-backed | Saved outreach/provider route and the canonical winning buyer/offer path where available | Mutable Buyer source alone does not claim a winning source; ambiguous or missing evidence is reported as unknown |
| DS10-R6 | Derive buyer reliability from documented behavior | Immutable completed-close, fallout, retrade, deposit, and cause evidence already retained by the Offer Room workflow | Non-buyer-caused fallout does not become an unsupported buyer penalty; archived buyers remain historically visible |
| DS10-R7 | Keep agent reporting explainable | Saved actors and approved role credit where present | Current ownership does not rewrite historical work; missing or conflicting attribution remains unassigned or ambiguous |
| DS10-R8 | Describe AI-assisted work without claiming causality | Frozen operating mode and retained DS9 recommendation/review evidence where applicable | Small samples and post-outcome drafts cannot be described as causal lift |
| DS10-R9 | Preserve tenant, role, asset, and economics boundaries | Organization-scoped House disposition queries and existing disposition/financial permissions | Cross-organization records are withheld; unauthorized private economics are absent; Land is not silently analyzed as House |
| DS10-R10 | Remain derived and read-only | Dashboard query and presentation paths only | Before/after assertions prove no mutation to buyers, packages, campaigns, provider evidence, offers, selections, outcomes, transactions, reconciliation, communications, or finance |
| DS10-R11 | Reconcile totals across views | One canonical definition per milestone and outcome | Summary, source, buyer, agent, and deal totals reconcile for the same evidence window and filters |
| DS10-R12 | Make incomplete evidence visible | Explicit gaps, unknown buckets, and denominator/sample metadata | Provider-only offers, missing packages, missing outreach, stale selection, backup promotion, and unfunded closes remain explainable |

Application code and migrations remain the truth about which dimensions and evidence fields exist.
This matrix prevents the dashboard or documentation from claiming unsupported attribution,
economics, costs, corrections, or causality.

## Metric Semantics

### Activity measures

Sent, delivered, replied, inquiry, showing, and offer measures describe activity. They do not prove
buyer selection, deposit, funding, profit, or a completed assignment.

### Outcome measures

- **Selected:** an authorized primary-buyer selection exists.
- **Deposit documented:** the governed Offer Room has retained qualifying deposit evidence or an
  authorized waiver under its existing policy.
- **Completed assignment:** canonical completed-close evidence agrees with the funded transaction.
- **Economic result:** the completed assignment also has the applicable approved reconciliation.

If the supporting records disagree, the dashboard must surface the conflict rather than choose the
most favorable interpretation.

### Rates and timing

Every rate must retain its numerator and denominator. Every duration must identify both retained
endpoints and exclude records that lack either endpoint. Median or average timing without a sample
count is not acceptable.

### Source, buyer, and agent context

Source, Buyer, and agent groupings are descriptive views of saved evidence. Until Stonegate adds a
frozen, correction-capable attribution decision, the dashboard must label ambiguous or missing
winning-source evidence as unknown. Current owner and mutable Buyer source fields cannot rewrite
history.

## Not Yet Implemented

The following DS10 roadmap items remain explicitly pending:

1. A disposition-specific campaign cost ledger and cost per offer, selected buyer, or completed
   assignment.
2. A frozen winning-source record tied to the selected Buyer, offer, outcome, and completed
   assignment.
3. Append-only manager corrections for attribution and derived-metric disputes.
4. Full split-credit agent attribution across acquisition, disposition, coordination, and closing.
5. A frozen market dimension for historical reporting.
6. Canonical showing definitions across owned-network and provider workflows.
7. Production sample thresholds for comparing human-led and AI-assisted outcomes.
8. Land disposition intelligence, which remains blocked until the Land disposition workflow is
   implemented and accepted.

## Repository Acceptance

Repository acceptance requires:

1. Backend tests for canonical timeline derivation, funnel separation, completed-assignment
   reconciliation, unknown evidence, organization isolation, permission boundaries, and zero
   mutation.
2. Frontend contract coverage for loading, empty, partial, conflict, and populated states, with
   activity and economic outcomes visibly separated.
3. Regression coverage for House package, Outreach, InvestorLift evidence, Offer Room, buyer
   selection, buyer outcome, transaction, and reconciliation workflows.
4. Type checking, targeted linting, documentation link checks, and whitespace validation.
5. Later production reconciliation against a manager-reviewed sample of completed and incomplete
   assignments before the dashboard is used for compensation, provider scaling, or causal claims.

Passing repository tests does not prove that a source, agent, provider, or AI workflow improves
completed assignments. It proves only that the retained evidence is summarized consistently and
within the stated authority boundary.
