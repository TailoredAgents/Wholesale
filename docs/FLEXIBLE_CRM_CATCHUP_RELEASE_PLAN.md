# Flexible CRM Catch-Up And Disposition Release Plan

Follow-up: `LAND_HOUSE_CRM_PARITY_RELEASE_PLAN.md` extends the evidence-backed outside-offer,
signed-contract import, Disposition handoff, and exact external-packet path to Land. The House-only
boundary below describes this earlier release, not the current product boundary.

Later follow-up: `DISPOSITION_ADVISORY_WORKFLOW_RELEASE_PLAN.md` supersedes this release's
setup-blocked handoff semantics. Current House and Land execution creates or reuses the case
immediately; missing owner, plan, or mode remains visible advisory setup on that same workable case.
The checklist below is retained as the historical acceptance record for the earlier release.

Status: Complete — verified and released to `origin/main`

Release note: All automated gates passed. Manual authenticated browser acceptance was attempted but
could not run because no controllable in-app or extension browser was available in this workspace;
the production web, API health, and API readiness endpoints are checked after the push.

## Objective

Make Stonegate flexible about where real-world work happens while preserving reliable contract,
offer, disposition, document, permission, and audit records. Staff must be able to catch Stonegate
up after phone, DocuSign, email, or externally prepared work without recreating fictional internal
steps.

This is one implementation-and-release phase. It ends only after the coherent change is verified,
committed, and pushed to `origin/main` for the currently hosted Render project.

## Product Rule

Stonegate is flexible about how truth enters the CRM and strict about what consequential truth
authorizes.

- Ordinary pipeline stages may move directly.
- Offer and contract milestones remain backed by their real facts and evidence.
- Selecting or dragging to a controlled milestone opens its action instead of showing a disabled
  or mysterious destination.
- Catch-up actions record what actually happened outside Stonegate; they never manufacture a prior
  approval or provider event.

## Implementation Checklist

### Preserve And Complete The Existing Work

- [x] Preserve the current signed-contract import, exact external investor packet, tests, styles,
      and documentation changes already present in the worktree.
- [x] Treat the existing worktree as one coherent feature; do not discard or overwrite it.

### Pipeline Actions

- [x] Keep ordinary stage changes fast and direct.
- [x] Make board drag/drop, seller-preview **Move to stage**, seller Summary, and **Contract & Deal**
      open the same signed-contract catch-up action for **Under Contract**.
- [x] Move the card only after the signed contract is recorded successfully.
- [x] Add a governed path for an offer presented outside Stonegate so **Offer Presented** and
      **Negotiating** are reachable without a bare label mutation.
- [x] Keep internal Stonegate offer preparation and approval available as the other Offer path.

### Signed Contract Catch-Up

- [x] Require the executed PDF, real purchase price, execution time, buyer entity, and confirmation
      of complete signatures; prefill known facts and keep secondary closing facts optional.
- [x] Turn omitted secondary terms into visible transaction follow-up rather than blocking the
      contract record.
- [x] Keep the exact signed agreement immutable with size, type, scan, hash, retention, tenant,
      and rollback protections.
- [x] Prevent reuse or resurrection of terminal/dead deals.
- [x] Reject names that become empty after trimming.
- [x] Avoid exposing seller, contract, or attestation facts in request URLs.

### Permissions And Entry Points

- [x] Add a narrow permission for recording an already executed agreement.
- [x] Grant it to the intended Owner, Acquisitions, and Transaction Coordinator roles without
      broadening unrelated contract authority.
- [x] Keep the Leads shortcuts permission-aware.
- [x] Add the equivalent catch-up entry point in Deals/Transactions for Transaction Coordinators
      who do not have general Leads editing access.

### Disposition Handoff

- [x] Open the normal House Disposition case when the owner, compensation plan, and human-led mode
      are ready.
- [x] If setup is incomplete, keep the executed transaction visible on the Disposition Desk as
      **Needs setup**, record exact blockers, create corrective work, and retain automatic retry.
- [x] Never claim the Disposition case opened when the handoff response says it did not.
- [x] Do not let compensation or staffing configuration make an executed deal disappear from
      operational view.

### Existing Investor Packet

- [x] Present **Build with Stonegate** and **Use existing PDF** as first-class Package choices.
- [x] Preserve an uploaded investor packet as the exact immutable artifact through approval,
      download, secure links, and email attachment.
- [x] Explain that CRM facts still govern readiness, private economics, matching, and outreach
      summaries.
- [x] Keep draft review and approved public release permissions distinct.

### Corrections And Documentation

- [x] Fix unreachable offer stages, incorrect negotiation links, contract-import typing, validation,
      and terminal-deal defects found during review.
- [x] Update `SYSTEM_MAP.md`, `USER_MANUAL.md`, `UI_CONTROL_REFERENCE.md`, and affected setup or
      README facts so code and staff guidance agree.
- [x] Keep House/Land boundaries explicit; this phase does not activate Land contract execution or
      Land disposition.

## Acceptance Criteria

- [x] An authorized user can drag or select a House lead into **Under Contract**, record the real
      agreement, and see the card move only after success.
- [x] An authorized user can record an outside offer and truthfully reach **Offer Presented** or
      **Negotiating**.
- [x] Owners and Acquisitions can use the Leads entry points; Transaction Coordinators can use the
      Deals/Transactions entry point.
- [x] Every executed House transaction is visible to Dispositions as an active case or an explicit
      setup-blocked intake.
- [x] An existing investor PDF can become the exact approved artifact without regeneration.
- [x] No bare stage patch can create false contract, offer, outreach, buyer-selection, or funded
      authority.
- [x] Tenant isolation, permissions, audit history, file cleanup, and immutable evidence remain
      covered.

## Verification

- [x] Run focused lead-stage, outside-offer, transaction-import, disposition-handoff, external
      packet, document-storage, permission, and tenant-isolation API tests.
- [x] Run the complete API test suite.
- [x] Run Ruff and ensure changed Python modules introduce no MyPy errors.
- [x] Run lead-pipeline and disposition-package frontend contract suites.
- [x] Run TypeScript, frontend lint, and the production web build.
- [ ] Exercise the drag/drop, stage-selector, Transaction Coordinator, setup-blocked Disposition,
      and exact external-PDF flows in a seeded local workspace when the local environment permits.
      Not run: no controllable in-app or extension browser was available.
- [x] Run `git diff --check` and inspect the final staged diff for scope and secrets.

## Release

- [x] Update this plan status and checklist to reflect the completed result.
- [x] Commit the coherent change to `main` with the message
      `Make CRM catch-up workflows flexible`.
- [x] Push `main` to `origin/main` so Render receives the release.
- [x] Confirm the remote commit and report any Render production acceptance that remains external.

## Non-Goals

- Live InvestorLift transport.
- Land contract execution or Land disposition release.
- Autonomous offer approval, buyer selection, outreach release, legal decisions, or funding.
- Rewriting unrelated historical type-check debt as part of this operational workflow fix.
