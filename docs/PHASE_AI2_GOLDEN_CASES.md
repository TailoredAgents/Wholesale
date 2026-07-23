# Phase AI2: Golden Cases And Evaluation Standards

Status: Complete in code on July 23, 2026. Production reviewer signatures remain pending.

## Delivered

- An idempotent AI2 library installer in `/os/ai`.
- A 75-case Lead Manager Copilot dataset:
  - 50 operating cases across ordinary follow-up, missing qualification, conflicts, stale records,
    duplicates, appointments, missed replies, callbacks, and handoffs.
  - 25 policy, failure, and adversarial cases.
- A 60-case Call Intelligence dataset:
  - 35 operating cases covering qualification, missing facts, speaker uncertainty, conflicting
    timelines, condition, commitments, and objections.
  - 25 policy, failure, and adversarial cases.
- Explicit expected outputs, uncertainty, evidence, prohibited behavior, and critical-case status.
- Capability thresholds for pass rate, factual accuracy, evidence coverage, critical failures,
  latency, and cost.
- Separate executive and operating-role review records.
- Deterministic redaction validation for direct identifiers, credentials, and payment data.
- A corrected-production-case endpoint that always creates a new draft dataset version.
- Evaluation output metrics for factual accuracy and evidence coverage.

## Approval Flow

1. Open `/os/ai` and select **Evaluations**.
2. Select **Install AI2 golden cases**.
3. Review the case mix, expected-answer standard, thresholds, and disagreement policy.
4. Sign the executive review.
5. Sign the role-owner review. An owner or founder may sign while covering the vacant role.
6. Approve the dataset.
7. Run the deterministic fixture evaluation.

The two review scopes are separate audit records even when the same owner is temporarily covering
both responsibilities.

## Redaction Standard

Evaluation payloads use opaque `seller_ref`, `property_ref`, and `case_ref` values. Direct names,
email addresses, phone numbers, street addresses, government identifiers, payment credentials,
authentication tokens, passwords, and secrets are prohibited.

A corrected production example must:

- use an opaque source reference;
- remove unnecessary personal data;
- pass deterministic redaction validation;
- document the human correction;
- create a new draft dataset version;
- repeat executive and role-owner review before approval.

## API

- `POST /api/v1/ai/evaluation-library/install`
- `POST /api/v1/ai/orchestrator/evaluation-datasets/{dataset_id}/reviews`
- `POST /api/v1/ai/orchestrator/evaluation-datasets/{dataset_id}/corrected-cases`
- Existing dataset approval and evaluation endpoints enforce the new review and quality thresholds.

## Persistence

Migration `0042_ai_evaluation_standards` extends evaluation datasets, cases, runs, and results and
adds `ai_evaluation_dataset_reviews`.

## Remaining Operator Checkpoint

Install and inspect the production library, then record both required signatures. Code completion
does not substitute for the CEO and relevant operating-role owner accepting the expected answers.

## Next Phase

AI3 connects production model execution, strict tools, approved-knowledge retrieval, redacted
traces, replay, monitoring, budgets, and provider shutdown controls behind the existing
orchestrator.
