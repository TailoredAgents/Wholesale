# Data Model

Last updated: July 21, 2026

The schema is managed through Alembic migrations. Migration `0025_acquisition_operations` is the
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
- `deals`
- `transactions`
- `transaction_checklist_items`
- `approval_requests`

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
- Comparable candidate records if comp-level review outgrows the retained analysis payload.
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
