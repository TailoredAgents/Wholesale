# Task And Follow-Up Policy

## Decision

Stonegate Tasks represents work a person has actually agreed or is required to do. AI processing,
AI suggestions, and background preparation are not human deadlines and must not become overdue
work merely because time passed.

## Human Tasks

A human task is appropriate when there is a concrete obligation, including:

- a new inbound lead that requires a speed-to-lead response;
- a missed inbound call or other reply that requires attention;
- a callback, appointment, deadline, or follow-up a staff member explicitly schedules; or
- a governed acquisition, contract, disposition, or closing step that has a real due date.

Creating a seller lead manually does not create a task unless `next_follow_up_at` is supplied. If a
date is supplied, Stonegate creates the lead's primary next action using that exact date.

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

Migration `0127_retire_legacy_automatic_tasks.py` retires the overdue generic primary actions that
match the former five-minute automatic-creation fingerprint. It marks them cancelled with the
`automation_retired` outcome, stores an audit event, and clears the matching artificial lead
follow-up date. It does not delete task history.

The cleanup does not touch speed-to-lead work, explicitly titled tasks, future work, or generic
tasks whose due date does not match the former automation fingerprint. Remaining human primary
actions can be completed with an outcome and no successor.

## Protections That Remain

Speed-to-lead tasks, inbound-response work, explicit callbacks, appointments, approvals,
operational exceptions, and transaction deadlines retain their existing permissions and audit
history. This policy changes task noise and successor defaults; it does not authorize AI to contact
people or perform governed business actions.
