# Stonegate VA Calling Roadmap

Last updated: July 30, 2026

## Decision

Stonegate will not use BatchDialer, predictive dialing, or multi-line dialing. VAs and any other
staff members explicitly enabled for cold calling will call one property owner at a time from
their assigned Stonegate queues.

This file keeps its original name so existing documentation links do not break. It now governs the
one-by-one VA calling workflow.

## Operating Model

- PropStream remains the initial source for prospect lists.
- Every caller has an individual Stonegate login and sees only assigned records unless their main
  management role already grants broader operational oversight.
- Cold calling is an explicit per-user capability. Enabling it does not change the person's main
  role or expose unrelated workspaces.
- Each call is made one at a time.
- The VA records the outcome, notes, callback, qualification, and appointment in Stonegate.
- Interested sellers move through the existing reviewed handoff to the Lead Manager.
- Stonegate remains the source of truth for ownership, history, appointments, costs, and results.
- Twilio may later provide company-owned one-to-one numbers and browser calling, but it will not
  create predictive or simultaneous dialing.

## Retired Scope

The following work is intentionally retired:

- BatchDialer accounts, API credentials, campaign synchronization, and webhooks
- simultaneous or predictive outbound calls
- provider campaign/contact reconciliation
- power-versus-multi-line comparison pilots
- annual external dialer subscriptions

Migration `0075_dialer_provider` remains in the repository only because a published database
revision cannot safely be deleted after a deployment may have applied it. The provider code and
controls are removed. Its unused database structures are inert and do not send or receive data.

## Current Foundation

Implemented capabilities retained from the prior phases:

1. PropStream CSV imports, reusable mappings, validation, duplicate handling, source evidence,
   list refresh, and ranked contact methods.
2. Campaign cohorts, work sessions, VA labor cost, and accepted-warm-lead measurement.
3. Restricted VA Caller accounts plus per-user cold-calling eligibility for staff in other roles.
4. A focused Prospecting workspace with due calls, callbacks, corrections, scheduled work, and
   complete assigned queues.
5. Approved scripts, qualification prompts, attempts, outcomes, notes, appointments, and
   individual caller attribution.
6. Reviewed handoffs into the Lead Manager and CRM without duplicating the prospect.
7. Cost and performance foundations based on Lead Manager-accepted warm leads.

## Remaining Phases

### VC1. One-By-One Calling Acceptance

Build status: implemented and covered by synthetic role, assignment, scoping, and attribution
tests. A real staff shift is still required for operational acceptance.

- In **Operations > Team**, enable **Cold calling** for each person who may receive a batch.
- In **Campaigns > Calling batches**, assign the batch to any active enabled caller.
- Test a complete caller shift using assigned Stonegate records.
- Confirm the VA can move quickly between attempts without losing notes or callbacks.
- Confirm every outcome is attributed to the correct caller, campaign, and cohort.
- Confirm restricted pages remain inaccessible.

### VC2. One-To-One Phone Connection

- Finish dedicated Twilio numbers after Stonegate's phone and messaging setup is approved.
- Add company-owned one-to-one browser calling when ready.
- Keep manual phone calling available as the fallback.
- Attach recordings and transcripts only when recording is intentionally enabled.

### VC3. Lead Manager Handoff Acceptance

- Test interested, appointment, correction, and rejected handoffs with actual staff accounts.
- Confirm the Lead Manager receives enough context for immediate follow-up.
- Confirm rejected handoffs do not count as accepted warm leads.

### VC4. Reporting And Optimization

- Report calls, contacts, accepted warm leads, appointments, contracts, and cost by VA and list.
- Record paid hours and actual list/phone costs.
- Improve lists, scripts, schedules, and coaching from Stonegate's measured results.

## Next Action

Run VC1 with a small controlled list and one enabled staff account. Improve the one-by-one
workspace only where the real shift reveals unnecessary steps or missing information.
