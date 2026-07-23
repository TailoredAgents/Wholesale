# Phase AI6: Acquisitions Copilot

Last updated: July 23, 2026

## Status

Implementation is complete in code. Production model replay, capability activation, and the
measured draft-only pilot remain operator checkpoints.

## Delivered

- The copilot is embedded in the existing Field Operations seller-meeting workspace rather than
  separated into another AI destination.
- An upcoming appointment can be opened directly from its lead record or the operating calendar.
  Field Operations remains the team-level meeting queue.
- The readiness panel remains visible before a meeting brief exists and tells the user exactly
  what must be generated or enabled before AI preparation can run.
- Appointment preparation uses the current versioned meeting brief, seller qualification,
  underwriting, comp evidence, field inspection, and approved offer authority.
- Post-meeting coaching requires a human-recorded meeting outcome.
- Deterministic readiness identifies missing qualification, underwriting, market, inspection, and
  offer-authority evidence before model execution.
- Only a fully approved offer plan exposes its opening, target, stretch, and seller ceiling to the
  model. Otherwise, the model receives an explicit no-price instruction.
- Outputs use strict, capability-specific schemas for appointment preparation and follow-up.
- Every generated recommendation is a draft linked to its appointment, lead, evidence versions,
  governed AI run, intended closer, confidence, and idempotency key.
- Staff can accept, correct, or reject a draft. The original output and immutable review are both
  retained.
- The workspace reports readiness, evidence, authority, runtime state, capability state, pilot
  metrics, and reviewed recommendation history.
- Copilot execution cannot send seller communications, change CRM facts, schedule work, calculate
  offers, change underwriting, or exceed approved authority.

## Operator Activation

1. Approve and replay acquisitions golden cases in the AI Control Center.
2. Enable the OpenAI provider runtime.
3. Enable `appointment.brief` for pre-meeting guidance.
4. Enable `negotiation.coach` for post-meeting guidance.
5. Review every draft during the pilot and correct unsupported or incomplete guidance.
6. Measure acceptance, correction, rejection, evidence coverage, latency, cost, and time saved.
7. Stop either capability immediately for unsupported price guidance, invented facts, authority
   violations, privacy failures, or unacceptable correction burden.

## Human Authority

The closer selects comps, verifies repairs, conducts the appointment, decides what to say, records
the outcome, and stays within approved offer authority. Managers approve underwriting, offer
plans, exceptions, and any future autonomy promotion. AI6 does not grant the model offer,
contract, communication, or CRM-write authority.

## Verification

Focused API tests cover disabled-runtime blocking, appointment scoping, approved-ceiling exposure,
strict structured outputs, idempotent generation, immutable correction review, post-outcome
gating, and zero copilot mutation of leads, tasks, or communications.
