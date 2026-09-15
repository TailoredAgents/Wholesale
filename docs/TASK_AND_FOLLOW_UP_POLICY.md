# Task And Follow-Up Policy

## Decision

Stonegate Tasks represents work a person has actually agreed or is required to do. AI processing,
AI suggestions, and background preparation are not human deadlines and must not become overdue
work merely because time passed.

## Human Tasks

A human task is appropriate when there is a concrete obligation, including:

- a missed inbound call or other reply that a person deliberately turns into a task;
- a callback, appointment, deadline, or follow-up a staff member explicitly schedules; or
- a governed acquisition, contract, disposition, or closing step that has a real due date.

Creating or importing a seller lead does not create a reminder. New website and BatchDialer leads
remain visible through their stage, qualification state, inbox activity, and new-lead alerts until
a team member deliberately chooses **Set reminder**. A reminder can be set for any exact date and
time, rescheduled, or marked done directly from Leads. **Text the assigned user when due** is an
optional per-reminder choice and stays off by default. When selected, Stonegate sends one internal
SMS to that user's saved cellphone in addition to the normal in-app notification.

Completing a primary next action requires an outcome so the history remains useful. Creating the
next action is optional and must be selected deliberately. An active record may therefore have no
open task when no follow-up is currently warranted.

## AI Activity

AI work remains durable and reviewable but is separated from human task urgency:

- queued or processing work does not appear in My Tasks or any due-date view;
- suggestions that are ready for a person appear under **AI Suggestions**;
- completed AI work remains under **AI Completed**;
- failed or blocked AI work remains under **Exceptions**; and
- AI items do not increase the human open-task or overdue counts.

AI-generated call notes do not preselect **Create follow-up task**. The reviewer may opt in when the
conversation produced a real next step.

## Existing Records

Migration `0127_retire_legacy_automatic_tasks.py` retired the overdue generic primary actions that
matched the former five-minute automatic-creation fingerprint. Migration
`0130_retire_automatic_lead_reminders.py` finishes the cutover by retiring every remaining open
generated speed-to-lead or generic five-minute action, including future ones. Both migrations keep
the history, record an audit event, and clear only the matching artificial follow-up date.

The cleanup does not touch reminders explicitly scheduled by people. Remaining human primary
actions can be completed with an outcome and no successor.

## Protections That Remain

New-lead and inbound-message alerts, unread conversations, inbound-response work for reactivated
closed leads, explicit callbacks, appointments, approvals, operational exceptions, and transaction
deadlines retain their existing permissions and audit history. This policy changes task noise and
successor defaults; it does not authorize AI to contact people or perform governed business actions.
