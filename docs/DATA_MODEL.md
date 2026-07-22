# Data Model

Last updated: July 21, 2026

The schema is managed through Alembic migrations. Migration `0029_offer_negotiation_plans` is the
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
- `activity_events`
- `audit_events`

`properties` retains the staff-entered address as the CRM source of record. It also stores a
canonical duplicate key and separate provider-validation status, provider property ID, formatted
address, validation timestamp, match evidence, issues, and a restricted non-owner fact snapshot.
Editing an address clears the provider confirmation until validation runs again.

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
- `deals`
- `transactions`
- `transaction_checklist_items`
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

## AI Control

- `ai_agent_definitions`
- `ai_prompt_versions`
- `ai_tool_permissions`
- `ai_run_logs`
- `ai_tool_call_logs`

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

- Market, territory, launch-checklist, campaign, prospect, prospect-assignment, and
  prospect-disposition records.
- Comparable candidate records if calibration volume or cross-analysis querying outgrows the
  current immutable analysis payload and audit-event review history.
- Offer versions and negotiation-event records.
- Document, template, signature-envelope, and file-access records.
- Buyer proof-of-funds document records.
- Disposition package, campaign, buyer-response, showing, selection, deposit, and operating-mode
  records.
- Compensation-plan versions, role credits, commission states, payout batches, disputes, and
  reversals.
- Accounting sync, monthly close, reconciliation, cash forecast, and owner-distribution records.
- Notification delivery and preference records.
- AI orchestration event, evaluation dataset, evaluation result, pilot, rollback, and operating-mode
  records.

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
