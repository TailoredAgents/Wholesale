# Data Model

## Foundation Tables

- `organizations`
- `users`
- `roles`
- `permissions`
- `role_permissions`
- `role_assignments`
- `contact_methods`
- `consent_records`
- `lead_form_submissions`
- `attribution_touches`
- `contacts`
- `properties`
- `leads`
- `conversations`
- `conversation_watchers`
- `conversation_assignment_events`
- `communication_records`
- `communication_provider_events`
- `call_records`
- `call_recordings`
- `call_transcripts`
- `deals`
- `tasks`
- `activity_events`
- `audit_events`

## Next Tables

- `suppression_records`
- `documents`
- `underwriting_versions`
- `offer_versions`
- `approval_requests`
- `buyers`
- `buyer_offers`
- `revenue_records`
- `deal_deductions`
- `compensation_rules`
- `compensation_calculations`
- `marketing_spend`
- `offline_conversion_exports`
- `approval_requests`
- `ai_agent_definitions`
- `ai_prompt_versions`
- `ai_tool_permissions`
- `ai_run_logs`
- `ai_tool_call_logs`

## Rules

- Use UUID primary keys.
- Store timestamps in UTC.
- Store money as integer cents.
- Preserve historical formula, compensation, consent, and prompt versions.
- Give call audio an explicit retention deadline; preserve deletion actor, reason, timestamp, and
  audit history after provider media is removed.
- Keep audit events append-only.
