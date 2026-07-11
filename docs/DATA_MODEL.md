# Data Model

## Foundation Tables

- `organizations`
- `users`
- `roles`
- `role_assignments`
- `contacts`
- `properties`
- `leads`
- `deals`
- `tasks`
- `activity_events`
- `audit_events`

## Next Tables

- `permissions`
- `role_permissions`
- `contact_methods`
- `consent_records`
- `suppression_records`
- `communications`
- `documents`
- `underwriting_versions`
- `offer_versions`
- `approval_requests`
- `buyers`
- `buyer_offers`

## Rules

- Use UUID primary keys.
- Store timestamps in UTC.
- Store money as integer cents.
- Preserve historical formula, compensation, consent, and prompt versions.
- Keep audit events append-only.
