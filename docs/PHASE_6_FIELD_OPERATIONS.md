# Phase 6: Field Operations

Status: Complete.

## Delivered

The `/os/field-operations` workspace now covers the complete seller-appointment lifecycle:

- explainable appointment dispatch with territory, working-hours, capacity, unavailable-time, and
  travel-buffer checks;
- manager-only conflict overrides with reasons and immutable candidate evidence;
- an internal month, week, and day calendar, with closer filtering and direct meeting launch;
- a versioned seller-meeting brief generated from current seller, property, qualification,
  underwriting, approved offer, tasks, unresolved questions, and likely objections;
- a mobile field walkthrough for room observations, repair scope, access, title, safety, utilities,
  occupancy, notes, and captured photographs;
- structured decision-maker, seller price, offer, counter, objection, commitment, outcome, and
  follow-up capture;
- a hard server-side block against presenting or accepting a price above the currently approved
  seller ceiling;
- a reviewed transfer that creates a new repair estimate and draft underwriting version without
  changing prior approved underwriting or silently creating a revised offer; and
- trailing 30-day preparation and outcome-documentation scorecards for each closer.

The internal `appointments` record remains the source of truth. External calendar integration is
not required for operations.

## Access And Evidence Controls

Acquisition managers can see the team calendar and all field appointments. Acquisition users see
only their assigned leads and appointments. Prospecting callers cannot access Field Operations,
underwriting, negotiation evidence, or inspection photographs.

Submitted walkthroughs and their photographs are immutable. Field evidence must be reviewed before
transfer, and the transfer always creates a new draft underwriting version with its offer values
cleared for recalculation and approval.

Inspection images currently use private, authenticated database storage with a 5 MB per-image and
30-image per-inspection limit. This is appropriate for controlled launch volume. Before sustained
high-volume operations, move image bytes to encrypted object storage while preserving the existing
database metadata, checksums, authorization rules, and audit history.

## Deferred Optimization

Travel protection uses a configurable static buffer. Live route-duration estimates should only be
added after operating data shows that static buffers are materially inadequate; this is an
optimization, not an incomplete Phase 6 workflow.

## Verification

- API regression coverage exercises calendar retrieval, versioned meeting briefs, walkthrough
  drafts, authenticated photographs, immutable submission, approved-ceiling enforcement,
  negotiation outcomes, underwriting transfer, and prospecting-caller denial.
- Python formatting, linting, and static typing pass.
- TypeScript and ESLint pass for the new Field Operations interface.
- Alembic upgrades through `0036_phase6_field_workflow`, downgrades one revision, and upgrades again
  on PostgreSQL.
- The complete API suite and production Next.js build pass.
