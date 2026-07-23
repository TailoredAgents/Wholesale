# Phase AI5: Prospecting Copilot And Call Quality

Last updated: July 23, 2026

Status: **Implementation complete. Production activation and measured pilots remain.**

## Purpose

The Prospecting Copilot assists human VAs and prospecting managers inside `/os/prospecting`. It
prioritizes only eligible assigned records, prepares evidence-based call briefs, and evaluates
completed calls when approved transcript evidence exists. It does not call sellers, select final
dispositions, alter eligibility, or submit handoffs.

This extends Stonegate's existing AI control plane and VA workbench. It is not a second AI system.

## Delivered

- Deterministic eligibility-first work ranking for corrections, due callbacks, active attempts,
  first attempts, and repeat outreach.
- Explainable score, priority band, recommended action, screening evidence, and data warnings.
- Governed `prospecting.prioritize` output for pre-call context, opening guidance, required
  questions, disposition guidance, compliance reminders, evidence, and confidence.
- Accept, correct, and reject review with immutable original and final output.
- Idempotent generation tied to the current prospect, queue entry, screening state, and priority.
- One chronological quality queue for every completed prospecting attempt.
- Deterministic qualification, data-quality, and handoff scores that remain nullable when evidence
  is unavailable.
- Governed `call.quality_coach` analysis using only an approved transcript from a disclosed,
  non-deleted recording.
- Manager approval, correction, or rejection of generated coaching without changing the caller's
  recorded outcome or notes.
- Immediate compliance flags for DNC requests, seller complaints, unclear identity, policy
  uncertainty, and recording-disclosure issues.
- Deduplicated manager notifications and append-only audit evidence for compliance escalation.
- Trailing 30-day brief, review, correction, time-saved, quality, transcript, escalation, and
  coaching metrics.
- Organization, role, assignment, field, and read-tool scope enforced by backend services.

## Enforced Limits

- Pilot mode is always `draft_only`.
- The copilot cannot place a call, send a message, change assignment, override suppression, change
  eligibility, choose a disposition, or submit a handoff.
- The human caller records qualification facts, disposition, callback, and handoff.
- The human manager decides whether coaching is useful and correct.
- Transcript-derived scores are unavailable until disclosure, recording, transcription, and human
  transcript approval are all present.
- No autonomous cold AI voice is enabled.
- Runtime budgets, circuit breakers, redaction, evaluation, audit, and emergency shutdown remain
  authoritative.

## Production Activation

1. Add and approve redacted Prospecting Copilot and call-quality cases in the AI evaluation system.
2. Complete AI3 provider monitoring and staging shutdown checks.
3. Confirm the approved caller script, suppression process, contact-hour policy, and escalation
   owner are current.
4. In `/os/ai`, enable the provider runtime.
5. Enable only `prospecting.prioritize`.
6. Generate controlled briefs in `/os/prospecting` and verify evidence, redaction, and zero record
   mutation.
7. Run a two-week draft-only pre-call pilot and review every rejection or correction.
8. After Voice compliance activation, confirm recording disclosure and retention controls.
9. Enable only `call.quality_coach`.
10. Run a separate two-week coaching pilot with manager comparison against approved transcripts.

## Pilot Measures

- Briefs generated, accepted, corrected, rejected, and left unreviewed.
- Critical factual, authority, privacy, and compliance failures.
- Cost, latency, provider failures, and estimated preparation time saved.
- Handoff acceptance and correction rates.
- Script and qualification quality based on available evidence.
- Complaints, stop requests, policy uncertainty, and escalation response time.
- Coaching acceptance, correction, and caller improvement over time.

Stop either pilot for unauthorized action, unscoped data, invented critical facts presented as
verified, missed compliance escalation, uncontrolled cost, or repeated unusable output.

## Exit Criteria

- Approved evaluation thresholds pass with no critical authority or compliance failure.
- Useful pilot volume is reviewed by the owner and prospecting manager.
- Brief and coaching correction rates, costs, failures, time saved, and handoff outcomes are
  measurable.
- Compliance escalation is tested without depending on AI or transcript availability.
- Any later autonomy proposal is evaluated as one reversible internal capability. Calling,
  messaging, eligibility, suppression, disposition, and handoff authority remain human.

## Next Phase

Proceed to AI6 Acquisitions Copilot while AI4 and AI5 remain supervised pilots. AI6 should build
appointment preparation, underwriting explanation, repair and evidence gaps, negotiation
preparation, and post-appointment drafts inside existing field and acquisitions workflows.
