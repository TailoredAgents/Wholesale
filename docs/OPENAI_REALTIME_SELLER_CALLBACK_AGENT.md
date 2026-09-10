# OpenAI Realtime Seller Callback Agent

## Outcome

Stonegate's `+1 (470) 888-7952` line becomes the AI seller-callback line. Calls are answered by Marin using OpenAI Realtime. The publicly marketed `+1 (678) 541-7725` line remains the company human line and the only transfer destination. `+1 (404) 777-2631` is not a Stonegate number and must never be configured or dialed by this feature.

The caller is treated as a possible homeowner returning a cold call, but Marin does not assume that the caller knows why Stonegate called and never reveals a stored property address before the caller has identified themself.

## Call flow

1. Twilio sends calls for the 470 line through a secure SIP trunk to OpenAI.
2. OpenAI sends Stonegate a signed `realtime.call.incoming` webhook.
3. Stonegate verifies the signature, confirms the called number is the configured AI line, creates one durable callback/call record, and accepts the call with `gpt-realtime-2.1` and the `marin` voice.
4. A server-side WebSocket observes the call and handles narrowly scoped CRM tools.
5. Marin opens neutrally: "Thank you for calling Stonegate Home Buyers. This is Marin. How can I help you?"
6. Marin learns whether the caller is returning a call, verifies identity using information the caller supplies, and gathers seller/property details naturally, one question at a time.
7. Stonegate saves meaningful information as the conversation progresses. A lead is created or updated only after seller interest and property ownership are established.
8. If requested or appropriate, the call is transferred to the 678 company line. If live help is unavailable, Marin records an agreed callback time.

## CRM behavior

- A call by itself creates a callback/call record, not a seller lead.
- A verified owner who is open to discussing a sale creates or updates one lead.
- Known contacts and leads are matched by normalized caller phone, then verified using caller-provided identity/property information.
- A caller who is not interested is recorded without creating an artificial follow-up task.
- An agreed future callback creates exactly one dated follow-up.
- Do-not-contact requests use Stonegate's existing suppression controls.
- Wrong numbers and unrelated calls are closed cleanly without entering the seller pipeline.
- Partial structured notes survive an interrupted call.

## Call review and quality control

- `Inbox -> Marin calls` is the company operational review workspace for the AI line.
- The dashboard distinguishes total calls from unique callers and shows today, 7-day, and 30-day activity.
- Every row includes the caller, time, duration, outcome, transcript availability, and linked seller context when Marin verified it.
- Opening a call loads the caller/Marin transcript separately so the normal Inbox and the call list remain lightweight.
- Staff can mark a call reviewed, flag a specific problem, add notes, and resolve the finding after the agent is corrected.
- Failed, timed-out, incomplete, missing-transcript, and uncertain-transfer calls automatically enter the needs-review queue.
- Completed transcript turns are checkpointed while the call is active. A later connection failure therefore retains the conversation collected before the failure.
- Review records retain the reviewer, review time, issue categories, notes, model, voice, and prompt version.
- Realtime caller transcription is a review aid rather than a guaranteed verbatim record. Audio recording remains disabled unless Stonegate separately enables its recording-consent and retention workflow.

## Agent tools

- `lookup_callback_context`: Match caller-supplied identity or property details against Stonegate records.
- `save_seller_details`: Persist verified seller/property facts and create or update a lead when qualified.
- `schedule_human_callback`: Store an explicitly agreed callback time and a single follow-up.
- `transfer_to_acquisitions`: Transfer the live call to the 678 company line.
- `record_call_outcome`: Store interested, not interested, wrong number, unrelated, or do-not-contact outcomes.
- `wait_for_user`: Keep the call open through brief silence without inventing a response.
- `finish_call`: Finish the interaction with a concise disposition.

All mutating tools are idempotent for a call. High-impact actions such as transfer and do-not-contact require the caller's clear request or confirmation.

## Safety and reliability

- The feature defaults off and is enabled only when all required OpenAI settings are present.
- OpenAI webhook signatures are verified before any call is accepted.
- Duplicate webhooks resolve to the same provider callback record and never start duplicate CRM work.
- The WebSocket worker uses its own short-lived database sessions; it never holds a request database session for the length of a call.
- The system gives OpenAI only the minimum context needed for the current tool response.
- A transfer is server-controlled and can target only the configured human line.
- If the agent is disabled or unavailable, Twilio's SIP trunk fallback must route the call to the 678 company line.
- Existing recording consent and retention policy remains authoritative; this feature does not silently enable recording.

## Runtime configuration

```text
OPENAI_REALTIME_VOICE_ENABLED=false
OPENAI_REALTIME_MODEL=gpt-realtime-2.1
OPENAI_REALTIME_VOICE=marin
OPENAI_REALTIME_LINE_NUMBER=+14708887952
OPENAI_REALTIME_TRANSFER_NUMBER=+16785417725
OPENAI_WEBHOOK_SECRET=
OPENAI_PROJECT_ID=
OPENAI_REALTIME_MAX_CALL_SECONDS=900
```

## Deployment sequence

1. Deploy the code with the feature disabled.
2. Create the OpenAI webhook for Stonegate's public incoming-call endpoint and save its signing secret in Render.
3. Save the OpenAI project ID and enable the feature in Render.
4. Associate only the 470 number with the Twilio trunk and configure its Origination SIP URI as `sip:<OPENAI_PROJECT_ID>@sip.api.openai.com;transport=tls`.
5. Configure Twilio trunk fallback/failure routing to the 678 company line.
6. Place controlled test calls for returning seller, unknown caller, interested seller, not interested, callback scheduling, transfer, silence, hang-up, duplicate webhook, and agent/API failure.
7. Confirm the 678 company line's existing routing was not changed.

## Acceptance checks

- The 470 line is the only number eligible for Marin.
- The 678 line remains human-operated and marketed publicly.
- The unrelated 404 number is absent from the configuration.
- The greeting is neutral and natural.
- No stored address is disclosed before verification.
- Switching between lookup, note capture, scheduling, and transfer does not produce duplicate records.
- A dropped call leaves a useful callback record and summary.
- No automatic overdue task is created unless a callback time was agreed.
- Operators can see agent readiness and the configured line in Communications settings.
- Operational staff can see company-wide Marin call counts and inspect individual transcripts from Inbox.
- A failed session keeps its partial transcript and is automatically marked for review.
- Review flags and reviewer notes remain attached to the call after refresh.
