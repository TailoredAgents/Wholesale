# Land And House CRM Parity Release Plan

Status: Complete

Verification record (September 1, 2026):

- API Ruff passed and all 1,430 API tests passed.
- All 281 frontend contract tests, TypeScript, ESLint, and the production Next.js build passed.
- Changed-module MyPy was exercised. The repository's existing imported-module baseline remains at
  133 errors in 9 historical modules; the new parity paths added no MyPy diagnostics.
- In-app browser acceptance was attempted, but this session had no controllable browser. Automated
  UI contracts and post-deploy production HTTP checks provide the release acceptance instead.
- The final diff passed whitespace, binary-file, and secret-pattern checks.
- The checked release items refer to the commit containing this plan and its corresponding
  `origin/main` Render deployment.

## Objective

Give Land and House leads the same practical CRM catch-up capabilities for work completed by phone,
email, DocuSign, or another outside system. An authorized user must be able to record an outside
offer, select or drag a lead to **Under Contract**, adopt the actual executed PDF, open the
Disposition workflow, and use an externally prepared investor packet for either asset class.

This is one implementation-and-release phase. It ends after the complete change is verified,
committed, pushed to `origin/main`, and the hosted Render services are checked for the released
commit.

## Product Rule

Land and House share one operational lifecycle and the same evidence-backed catch-up actions.
Asset-specific facts and automation remain asset-aware.

- Ordinary stages remain direct CRM updates.
- Offer and Under Contract remain clickable actions backed by the facts that actually occurred.
- A signed external contract is historical evidence; recording it does not authorize Stonegate to
  generate or send an unapproved Land contract.
- An externally prepared investor packet may be the exact approved artifact for either asset.
- Residential-only automation stays unavailable for Land until its legal templates, valuation
  inputs, and providers are intentionally released.

## One-Phase Implementation Checklist

### Shared Lead And Offer Workflow

- [x] Allow House and Land users to record an offer presented outside Stonegate.
- [x] Make Offer and Under Contract actionable from table preview, board drag/drop, Summary, and
      Contract & Deal rather than rendering a disabled Land destination.
- [x] Keep controlled stages evidence-backed and close direct-create or bare-stage-update bypasses.
- [x] Preserve permission-specific entry points for Leads editors and contract coordinators.

### Shared Signed-Contract Catch-Up

- [x] Allow House and Land to import an already executed agreement with the exact immutable PDF and
      real terms.
- [x] Move the lead, deal, and transaction to Under Contract only after import succeeds.
- [x] Use parcel-safe Land identity and persist the asset class in transaction metadata, audits,
      and API responses.
- [x] Keep Stonegate-generated Land agreements, template assembly, and e-sign unavailable.

### Shared Disposition Handoff And Packet

- [x] Create or recover a Disposition case for an executed House or Land transaction.
- [x] Keep setup-blocked transactions visible on the Disposition Desk for both asset classes.
- [x] Allow an exact external Land investor packet to be uploaded, reviewed, approved, downloaded,
      and used as the released packet.
- [x] Make package facts/readiness Land-aware, including parcel identity and Land valuation inputs.
- [x] Keep residential-only outreach, InvestorLift, generated Land packets, and other unreleased
      automation explicitly unavailable instead of blocking the whole Land case.

### UX, Contracts, And Documentation

- [x] Show asset-aware wording and links without presenting House-only actions on Land records.
- [x] Add `asset_class` where frontend/API decisions require it.
- [x] Update workflow documentation and replace tests that codified the obsolete House-only catch-up
      restriction.

## Acceptance Criteria

- [x] A Land lead can choose or be dragged to Offer, record the real outside offer, and reach the
      selected offer stage.
- [x] Under Contract is clickable for Land and opens the same signed-contract evidence flow used by
      House.
- [x] Successful Land import preserves the exact PDF, records a deal and executed transaction, and
      opens Dispositions or a visible Needs setup intake.
- [x] An external Land investor PDF can become the exact approved package artifact.
- [x] Parcel-only Land displays a useful identity throughout the handoff and desk.
- [x] No direct stage mutation can fabricate offer or contract authority.
- [x] Existing House behavior, permissions, tenant isolation, audit history, and file protections
      remain intact.
- [x] Generated/e-signed Land contracts and House-only distribution providers remain blocked.

## Verification

- [x] Run focused API tests for leads, outside offers, executed-contract import, Disposition handoff,
      Desk setup intake, external packages, permissions, storage, and tenant isolation.
- [x] Run the complete API test suite, Ruff, and changed-module MyPy checks.
- [x] Run frontend contract tests, TypeScript, lint, and the production web build.
- [x] Exercise the relevant lead and Disposition paths in the in-app browser when a controllable
      browser and seeded local workspace are available.
- [x] Run `git diff --check` and review the final staged diff for scope and secrets.

## Release

- [x] Mark this plan complete with the actual verification results.
- [x] Commit the coherent change directly to `main`, as requested for the hosted project.
- [x] Push `main` to `origin/main`.
- [x] Wait through the expected Render web deploy and verify the released commit and service health.

## Non-Goals

- Enabling Stonegate-generated or e-signed Land purchase agreements before approved Land templates
  exist.
- Reusing residential repair/ARV assumptions for Land.
- Enabling InvestorLift or residential-only automated outreach for Land.
- Fabricating offer, contract, buyer-selection, outreach, or funding history with a bare stage label.
- Resolving unrelated historical repository debt.
