# Phase 6: Field Operations

Status: Partial. Appointment dispatch and capacity controls are complete; seller-meeting and
mobile field workflows remain.

## Delivered

The Field Dispatch desk is available at `/os/field-operations` for users with acquisition
operations access. It uses Stonegate's internal `appointments` and `calendar_events` records as the
calendar source of truth.

Managers can configure each closer's:

- timezone, working days, and working hours;
- daily appointment limit and normal appointment duration;
- static travel buffer and home ZIP;
- active territories and whether territory matching is mandatory;
- scheduled unavailable periods.

The slot evaluator checks working hours, territory coverage, daily capacity, unavailable periods,
and appointment-plus-travel overlap separately. It returns every closer with an explicit list of
violations so dispatch decisions are reviewable rather than opaque.

An eligible dispatch creates the appointment, internal calendar event, closer notification, lead
assignment and stage update, activity entry, and dispatch record in one transaction. Managers may
override conflicts only by supplying a reason. The record preserves the violations and the full
candidate snapshot as decision evidence.

When a Lead Manager selects an appointment as the next action and no appointment already exists,
the seller moves to `appointment_scheduling` and appears in Field Dispatch. The system no longer
silently assigns that field visit to the Lead Manager. Existing appointments remain intact.

## Current Boundary

Travel protection currently uses a configurable buffer around each appointment. Stonegate does not
yet call a mapping API for live drive time. That avoids a new paid dependency while the company has
low appointment volume; a route provider can be added later without changing the dispatch record or
calendar contract.

## Remaining Phase 6 Work

1. Generate the seller-meeting brief from qualification, property, underwriting, approved offer,
   unresolved questions, likely objections, and logistics.
2. Add a mobile property walkthrough for photographs, room-by-room condition, repair evidence, and
   access notes.
3. Capture decision makers, objections, negotiation movement, commitments, and appointment outcome.
4. Transfer reviewed field observations into a new underwriting version without overwriting prior
   evidence.
5. Add appointment preparation and outcome scorecards after real meeting data exists.

## Verification

- Focused dispatch tests cover normal scheduling, daily-capacity rejection, manager override audit,
  and unavailable-time blocking.
- The complete API suite passes with the new tables and routes.
- Alembic upgrades from the foundation through `0035_field_dispatch`, downgrades to
  `0034_lead_manager_os`, and upgrades again on PostgreSQL.
- TypeScript, ESLint, and the production Next.js build include `/os/field-operations`.
