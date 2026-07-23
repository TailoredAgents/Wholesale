# Phase AI7: Transaction Copilot And Document Intelligence

Last updated: July 23, 2026

## Status

The provider-independent foundation is complete in code. Private object storage, automated
document extraction, e-signature reconciliation, email delivery, attorney-approved production
templates, production model replay, and a measured draft-only pilot remain operator or integration
checkpoints.

## Delivered

- Transaction Copilot is embedded in the existing Transactions closing workspace.
- Deterministic readiness checks coordinator assignment, closing date, closing attorney or title
  contact, executed contract evidence, required checklist work, private documents, confirmed
  document facts, and deadline risk.
- Earnest-money, due-diligence, assignment, closing, and checklist deadlines are classified as
  informational, warning, or critical without requiring a model.
- Identical files within a transaction are rejected using their SHA-256 checksum.
- Staff can record human-confirmed document facts with the source document, source page, and short
  supporting excerpt.
- The governed runtime receives transaction fields, contract-package metadata, document metadata,
  confirmed facts, parties, checklist status, and timeline evidence. Raw private file bytes are not
  included in model prompts.
- Strict Transaction Copilot output includes status, missing work, deadline risks, document
  findings, party gaps, internal actions, closing-attorney and seller drafts, legal escalations,
  evidence, and confidence.
- Every recommendation is idempotent, draft-only, linked to the transaction and AI trace, and
  preserved with its evidence snapshot.
- Staff can accept, correct, or reject guidance. Original output and immutable review evidence are
  retained.
- Copilot execution cannot edit or interpret legal documents, complete checklist work, change
  deadlines, contact parties, or mark a transaction funded, closed, or cancelled.

## Provider Track

Before production document intelligence is complete:

1. Move private file bodies from PostgreSQL to owner-controlled S3-compatible object storage.
2. Add malware scanning, encryption-key policy, signed download URLs, and retention controls.
3. Select an e-signature provider and reconcile envelopes, recipients, signatures, and final files.
4. Connect Google Workspace after the operational mailbox is approved.
5. Load attorney-approved Georgia templates and closing playbooks.
6. Add page-preserving PDF and image extraction that creates proposed, never auto-confirmed, facts.
7. Require a human to confirm every material extracted fact before it can control a checklist,
   deadline, external draft, or closing decision.

## Pilot Acceptance

- Build redacted ordinary, incomplete, conflicting, duplicate, unsigned, deadline-risk, and
  adversarial transaction packages.
- Measure required-document detection, deadline detection, source-page accuracy, unsupported
  claims, corrections, latency, cost, and estimated time saved.
- Stop the pilot for invented terms, missing source references, legal interpretation, signature
  claims without evidence, external execution, or transaction mutation.
- Keep `transaction.coordinate` disabled until the AI3 production runtime and AI7 dataset replay
  pass.

## Verification

Tests cover duplicate-file rejection, page-linked confirmed facts, disabled-runtime blocking,
transaction-scoped model context, exclusion of raw file bytes, idempotent generation, immutable
human correction, strict structured output, and zero mutation of transaction status, deadlines,
checklist items, or timeline events.
