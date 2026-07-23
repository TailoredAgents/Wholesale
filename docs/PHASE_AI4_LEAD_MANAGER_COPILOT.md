# Phase AI4: Lead Manager Copilot

Last updated: July 23, 2026

Status: **Implementation complete. Production activation and the measured draft-only pilot remain.**

## Purpose

The Lead Manager Copilot assists the human Lead Manager inside `/os/lead-manager`. It ranks work,
summarizes the current seller record, identifies missing qualification facts, and prepares drafts.
It does not own leads or make seller decisions.

This extends the existing AI control plane and Lead Desk. It is not a second AI system.

## Delivered

- Deterministic work ranking based on handoff SLA, missed replies, overdue follow-up,
  qualification state, neglected leads, and same-day appointments.
- Explainable priority score, band, alerts, recommended action, and supporting CRM evidence.
- Governed `lead.next_action` model output with a strict Lead Manager response contract.
- Seller summary, priority explanation, qualification gaps, recommended questions, unsent
  SMS/email draft, task proposal, appointment proposal, Acquisitions handoff brief, risks,
  evidence, and confidence.
- Idempotent generation tied to the material case, conversation, script, and priority state.
- Immutable recommendation and review records preserving original and human-corrected output.
- Accept, correct, and reject controls inside the Lead Desk.
- Trailing 30-day generation, review, acceptance, correction, time-saved, cost, response-time, and
  appointment metrics.
- Organization, role, and assignment scoping plus append-only audit events.

## Enforced Limits

- Pilot mode is always `draft_only`.
- No SMS or email is sent.
- No task or appointment is created.
- No CRM fact, stage, ownership, or qualification answer is changed.
- No lead is transferred to another employee.
- Reviewing a brief records feedback only.
- Twilio and email-provider activation are not required for the pilot.
- Runtime policy, capability policy, budgets, rate limits, circuit breaker, redaction, and
  emergency shutdown remain authoritative.

## Production Activation

1. Approve the production AI2 Lead Manager golden dataset in `/os/ai`.
2. Run the intended production model and prompt against the approved dataset.
3. Compare the result with the accepted baseline and confirm every promotion threshold passes.
4. Complete the AI3 provider-monitoring and staging shutdown checks.
5. Confirm `OPENAI_API_KEY` is configured only in Render and is not stored in source control.
6. In `/os/ai`, enable the provider runtime.
7. Enable only the `lead.next_action` capability.
8. Open `/os/lead-manager`, select Copilot, and generate one controlled test brief.
9. Confirm the trace is redacted, evidence is relevant, and no external or CRM action occurred.
10. Begin the supervised pilot with a named owner and daily failure review.

## Four-Week Pilot

Record:

- Number of briefs generated and reviewed.
- Accepted, corrected, and rejected recommendations.
- Critical factual, authority, privacy, or compliance failures.
- Response latency, provider failures, and circuit-breaker events.
- Cost per brief and total cost.
- Estimated staff time saved.
- Handoff response time, appointment volume, and appointment quality.

Stop the pilot immediately for any external action, unauthorized record access, invented critical
fact presented as verified, repeated unusable output, or uncontrolled cost. Use the AI emergency
shutdown in `/os/ai`, preserve the trace, and add a redacted corrected case to the AI2 dataset.

## Exit Criteria

- AI2 thresholds pass with no critical authority or compliance failure.
- Four weeks of useful operating volume are reviewed.
- Corrections, failure rate, latency, cost, time saved, and seller outcomes are measurable.
- The owner and Lead Manager approve or reject continued use.
- Any proposed autonomy is evaluated as one separate reversible internal capability. External
  communication, appointments, ownership, offers, and contractual actions remain out of scope.

## Next Phase

Proceed to AI5 Prospecting Copilot and Call Quality while AI4 remains in its supervised pilot.
Recording-dependent features remain disabled until Twilio disclosure, consent, and retention
controls are approved.
