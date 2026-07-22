# Phase 5: Lead Manager Operating System

Status: Complete as of July 22, 2026.

## Daily Operating Order

1. Accept new warm handoffs before their SLA deadline.
2. Complete guided qualification using the current approved standard.
3. Work overdue seller follow-ups.
4. Prepare for today's appointments.
5. Clear every neglected-lead exception before ending the shift.

The Lead Manager desk is available at `/os/lead-manager`. Individual Lead Managers see their own
cases. Acquisition managers and owners see the full team queue and scorecards.

## Workflow Controls

- A VA warm handoff creates one CRM lead and one Lead Manager case. It does not duplicate or move
  the seller between accounts.
- A public website inquiry routes to the least-loaded active acquisitions user at the highest
  available role priority and enters the same acceptance queue. Existing active leads are
  backfilled during the Phase 5 migration.
- The acceptance deadline defaults to 60 minutes and is configured with
  `LEAD_MANAGER_HANDOFF_SLA_MINUTES`.
- The worker escalates overdue acceptance to the assignee and acquisition-management users, while
  retaining the original due time and an audit event.
- Qualification cannot finish until every required question in the approved script is answered.
- Every active qualification requires a future dated action. Stonegate creates or updates the
  assigned task and lead follow-up time automatically.
- An appointment next action creates the internal calendar appointment and advances the lead.
- Disqualification closes the case and records the lead stage without creating a follow-up.

## Management Standards

Qualification scripts are immutable after approval. Approving a new version retires the previous
version for new sessions, while completed sessions retain their original version and answers.

The trailing 30-day scorecard reports:

- Handoffs received and accepted.
- Acceptance within SLA and average response minutes.
- Qualifications completed.
- Appointments set, held, and marked no-show.
- Contracts created.
- Percentage of active leads protected by a future dated next action.

## Verification

Automated coverage exercises the complete VA-to-Lead-Manager flow, required qualification fields,
future next-action enforcement, scorecard updates, worker escalation, permissions, and audit
creation. The API suite, Ruff, Mypy, TypeScript, ESLint, Next production build, and PostgreSQL
migration cycle are the release gates for this phase.
