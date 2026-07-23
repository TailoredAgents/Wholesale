# Data Model

Last updated: July 23, 2026

The schema is managed through Alembic migrations. Migration `0051_management_copilots` is the
current head.

## Identity And Access

- `organizations`
- `users`
- `roles`
- `permissions`
- `role_permissions`
- `role_assignments`

## CRM And Evidence

- `contacts`
- `contact_methods`
- `properties`
- `leads`
- `consent_records`
- `suppression_records`
- `lead_form_submissions`
- `attribution_touches`
- `conversion_events`
- `tasks`
- `appointments`
- `calendar_events`
- `lead_qualification_script_versions`
- `lead_management_cases`
- `lead_qualification_sessions`
- `closer_dispatch_profiles`
- `closer_territory_coverages`
- `closer_availability_blocks`
- `appointment_dispatch_records`
- `field_meeting_briefs`
- `acquisitions_copilot_recommendations`
- `acquisitions_copilot_reviews`
- `field_inspections`
- `field_inspection_photos`
- `field_negotiation_sessions`
- `field_underwriting_transfers`
- `activity_events`
- `audit_events`

`properties` retains the staff-entered address as the CRM source of record. It also stores a
canonical duplicate key and separate provider-validation status, provider property ID, formatted
address, validation timestamp, match evidence, issues, and a restricted non-owner fact snapshot.
Editing an address clears the provider confirmation until validation runs again.

Field meeting briefs are versioned evidence snapshots. Submitted inspections and photographs are
immutable, and each underwriting transfer links the exact inspection, repair estimate, prior
underwriting version, and newly created draft version. Photo bytes are privately stored in
PostgreSQL for controlled launch volume with strict size/count limits; object storage is the planned
scaling boundary without changing the authorization or evidence metadata contract.

## Communications

- `conversations`
- `conversation_watchers`
- `conversation_assignment_events`
- `communication_records`
- `communication_dispatches`
- `communication_provider_events`
- `email_accounts`
- `email_templates`
- `email_attachments`
- `voice_lines`
- `voice_call_intents`
- `call_records`
- `call_recordings`
- `call_transcripts`

## Underwriting And Transactions

- `underwriting_versions`
- `underwriting_market_analyses`
- `underwriting_calibration_cases`
- `repair_estimates`
- `offer_negotiation_plans`
- `offer_concessions`
- `offer_negotiation_events`
- `deals`
- `transactions`
- `transaction_checklist_items`
- `contract_templates`
- `contract_packages`
- `transaction_documents`
- `transaction_document_facts`
- `transaction_parties`
- `transaction_events`
- `transaction_copilot_recommendations`
- `transaction_copilot_reviews`
- `approval_requests`

`underwriting_calibration_cases` stores one verified outcome per immutable market analysis. It
retains the predicted ARV range and point, repair budget, seller ceiling, and disposition value as
they existed when evidence was recorded, alongside later human or market benchmarks. This supports
market-level error analysis without rewriting historical analyses or automatically changing offer
formulas.

`repair_estimates` stores immutable contractor bids, walkthrough estimates, and internal scopes.
Each record retains its itemized work, optional labor/material split, subtotal, contingency,
evidence reference, and total. A market analysis snapshots the selected estimate identity and
supporting metadata so later calculations and reports remain reproducible.

`offer_negotiation_plans` snapshots the selected underwriting version, market analysis, ARV,
repair budget, disposition value, seller asking price, and an ordered opening/target/stretch/
walk-away ladder. The plan links to a human `approval_request`; decisions retain the deciding user,
notes, timestamp, and audit events. A later request preserves but cancels the former pending plan.

`offer_concessions` is the sequential authority ledger beneath an approved plan. Each row retains
the prior and proposed amount, seller counter, required reason, seller exchange, authority basis,
manager decision, presentation evidence, and immutable source snapshot. `offer_negotiation_events`
stores the chronological price discussion, channel, seller response, objections, amount, actor,
appointment, and governing concession. A field negotiation may reference the exact concession that
authorized its presented or agreed price.

`transaction_document_facts` stores human-confirmed or future proposed facts with the source
document, page, excerpt, extraction method, confidence, status, and reviewer. Raw document bytes
are excluded from AI context. `transaction_copilot_recommendations` stores idempotent draft
coordination guidance and its evidence snapshot; `transaction_copilot_reviews` preserves the
original output and immutable human acceptance, correction, or rejection.

## Buyers, Finance, And Marketing

- `buyers`
- `buyer_criteria`
- `buyer_offers`
- `revenue_records`
- `deal_deductions`
- `compensation_rules`
- `compensation_calculations`
- `marketing_spend`
- `offline_conversion_exports`

## Operating Model

- `markets`
- `territories`
- `campaigns`
- `prospects`
- `prospect_import_mappings`
- `prospect_import_batches`
- `prospect_import_rows`
- `prospect_suppression_checks`
- `campaign_costs`
- `prospect_calling_batches`
- `prospect_calling_batch_entries`
- `prospecting_script_versions`
- `prospecting_attempts`
- `prospecting_copilot_recommendations`
- `prospecting_copilot_reviews`
- `prospecting_call_quality_reviews`
- `prospect_handoffs`
- `compensation_plan_versions`
- `compensation_plan_roles`
- `disposition_operating_modes`
- `role_credits`
- `market_launch_checklists`
- `market_launch_checklist_items`
- `buyer_proof_documents`
- `disposition_cases`
- `disposition_matches`
- `disposition_campaigns`
- `buyer_engagements`
- `disposition_copilot_recommendations`
- `disposition_copilot_reviews`
- `deal_reconciliations`
- `deal_payouts`

Compensation plans preserve the exact approved economics in effect for a deal. Role credits record
who performed each compensated function and require an auditable approval before later payment.
Disposition operating modes define human and expected company shares without retroactively changing
historical plans. Market checklists retain evidence and final approval for every launch version.

Disposition cases freeze the governing plan and operating mode, retain the approved package and
buyer-selection evidence, and connect one contracted transaction to its ranked buyer pool.
Disposition Copilot recommendations retain idempotent buyer and offer guidance with its governed
trace and evidence snapshot. Reviews preserve the original output and immutable human acceptance,
correction, or rejection without changing buyers, campaigns, economics, or selection.
Reconciliations use collected revenue and deal-specific deductions to produce auditable payout and
company-profit records. Approval cannot silently allocate an unassigned commission.

Prospect import batches preserve the source file checksum, reusable mapping, every source row,
normalization result, duplicate match, and call-eligibility decision. Suppression checks retain
separate company and imported vendor DNC evidence. Calling batches reference only prospects with
clear screening evidence; records that are blocked or require review remain outside caller queues.

Prospecting scripts are immutable versions that require manager approval before queue use. Each
started record creates a separate attempt tied to the exact script version, caller, batch entry,
answers, outcome, callback, and quality evidence. Warm outcomes create a CRM lead and a reviewable
handoff; correction and acceptance decisions preserve both the original and replacement attempts.

Prospecting Copilot recommendations preserve deterministic priority, the exact governed model
output, evidence snapshot, model trace, intended caller, and immutable human review. Call-quality
reviews remain tied to the human attempt and optionally to a disclosed recording, approved
transcript, and governed AI run. Missing evidence produces nullable scores rather than invented
certainty. Compliance flags and escalation state do not depend on transcript or model availability.

## AI Control

- `ai_agent_definitions`
- `ai_prompt_versions`
- `ai_tool_permissions`
- `ai_run_logs`
- `ai_tool_call_logs`
- `ai_orchestrator_events`
- `ai_evaluation_datasets`
- `ai_evaluation_cases`
- `ai_evaluation_dataset_reviews`
- `ai_evaluation_runs`
- `ai_evaluation_results`
- `ai_capability_promotions`
- `ai_copilot_definitions`
- `ai_copilot_agent_mappings`
- `ai_capability_contracts`
- `ai_data_governance_policies`
- `ai_knowledge_sources`
- `ai_data_quality_rules`
- `management_copilot_recommendations`
- `management_copilot_reviews`

Role copilots are the staff-facing layer. Each copilot has one named human owner and maps to
bounded specialist engines. Versioned capability contracts define triggers, inputs, outputs,
permitted tools, evidence, approvals, escalation, and prohibited actions. Governance policies
preserve field-level source precedence, overwrite behavior, redaction, retention, and audience.

Evaluation datasets retain capability-specific accuracy, evidence, safety, latency, and cost
thresholds. Cases identify operating, policy, failure, and adversarial scenarios with explicit
redaction state, uncertainty, required evidence, and prohibited behavior. Dataset reviews preserve
separate executive and operating-role decisions. Human-corrected production examples always create
a new draft dataset version.

Management Copilot recommendations share one capability-scoped, period-bounded ledger for Finance,
Marketing, and Executive drafts. The evidence snapshot and governed AI trace remain attached to
the original output; one immutable review preserves acceptance, correction, or rejection without
mutating financial, marketing, staffing, permission, or external systems.

## Platform Operations

- `worker_heartbeats`
- `operational_failures`

## Acquisition Operations

- `teams`
- `team_memberships`
- `calling_lists`
- `calling_list_entries`
- `calendar_events`
- `saved_views`
- `notifications`
- `duplicate_candidates`
- `lead_merge_events`
- `follow_up_plans`
- `follow_up_enrollments`

## Planned Additions

- Comparable candidate records if calibration volume or cross-analysis querying outgrows the
  current immutable analysis payload and audit-event review history.
- Offer versions and negotiation-event records.
- Signature-envelope, private object-storage, file-scan, and signed-access records.
- Buyer proof-of-funds document records.
- Disposition package, campaign, buyer-response, showing, selection, deposit, and deal-level
  operating-mode assignment records.
- Commission states, payout batches, disputes, and reversals.
- Accounting sync, monthly close, reconciliation, cash forecast, and owner-distribution records.
- Notification delivery and preference records.
- Dedicated pilot cohort records if promotion and rollback history no longer provides enough
  reporting detail after the first measured pilots.

## Rules

- Use UUID primary keys.
- Store timestamps in UTC.
- Store money as integer cents.
- Scope business records by `organization_id`.
- Preserve historical formula, compensation, consent, underwriting, and prompt versions.
- Keep provider IDs separate from internal IDs.
- Give call audio an explicit retention deadline and preserve deletion evidence after media removal.
- Keep material audit events append-only.
- Use structured columns for operational queries and retained provider metadata for evidence, not
  as the only source of business state.
