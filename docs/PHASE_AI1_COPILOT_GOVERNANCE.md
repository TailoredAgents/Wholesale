# Phase AI1: Copilot Contracts And Data Governance

Status: Complete in code on July 22, 2026.

## Delivered

- Eight staff-facing copilots: Prospecting, Lead Manager, Acquisitions, Transaction, Disposition,
  Finance, Marketing, and Executive.
- A named human owner and explicit retained human authority for every copilot.
- Mappings from each copilot to the existing bounded specialist engines.
- Fourteen versioned capability contracts covering triggers, required inputs, outputs, tool scopes,
  evidence, approvals, escalation, and prohibited actions.
- Seven data-governance policies for source precedence, overwrite controls, redaction, retention,
  and role access.
- Six versioned knowledge-source registrations with owner, audience, effective date, review date,
  and authority state.
- Six deterministic quality rules for duplicates, stale leads, missing attribution, conflicting
  property facts, and unverified model output.
- Idempotent installation, owner approval, return-to-draft, audit events, and OS visibility.

## Product Behavior

The `/os/ai` Copilots view is the staff-facing governance control. It shows who owns each job, which
specialist engines assist them, and what each capability may produce. The Governance view shows
source authority, overwrite policy, retained knowledge, and deterministic quality rules.

Installation creates draft records and does not grant external authority. Owner approval activates
the governance foundation but does not enable messaging, calling, offers, contracts, buyer
selection, payments, commissions, legal decisions, or any other external action. Those actions
remain blocked by capability contracts and specialist tool permissions.

Attorney-approved market templates remain `pending_external_review` and non-authoritative until
real reviewed templates are registered.

## API

- `POST /api/v1/ai/copilots/install`
- `POST /api/v1/ai/copilots/foundation/decision`
- `GET /api/v1/ai` includes the complete foundation and copilot metrics.

All endpoints require `ai:change_prompts`.

## Persistence

Migration `0041_ai_copilot_governance` adds:

- `ai_copilot_definitions`
- `ai_copilot_agent_mappings`
- `ai_capability_contracts`
- `ai_data_governance_policies`
- `ai_knowledge_sources`
- `ai_data_quality_rules`

## Verification

Focused backend tests verify complete installation, idempotency, the Lead Manager authority
boundary, source precedence, legal-template review status, owner approval, overview metrics, and
return-to-draft behavior.

## Next Phase

AI2 creates redacted golden cases and quality thresholds for Lead Manager Copilot and Call
Intelligence before production model behavior is allowed.
