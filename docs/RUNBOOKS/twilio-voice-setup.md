# Twilio Voice Setup

Last updated: July 20, 2026

Current status: code and public webhook endpoints are deployed; provider activation is paused until
Stonegate resumes the Twilio/domain/email integration closeout.

Communications Phase 5 adds browser calling, inbound call routing, call lifecycle history,
missed-call tasks, and
private recording access to the Stonegate shared inbox. Voice is disabled by default. Do not
change either phone number's Voice webhook until the new API deployment and environment values are
ready.

## Stonegate Number

Stonegate uses `+16785417725` for this integration. Do not change `+14047772631`; that number
belongs to another application.

The `+16785417725` Voice webhook currently routes to `myadvisormiles.com`. Changing it will move
incoming Voice calls away from that application and into Stonegate. Make that change only when
Stonegate is ready to receive the calls.

## 1. Create Voice Credentials

In the Twilio Console:

1. Keep the existing Account SID and Auth Token. The Auth Token validates Twilio webhooks and
   authorizes private recording retrieval.
2. Open **Account > API keys and tokens** and create a **Standard** or **Main** API key.
3. Save the API Key SID, which starts with `SK`, and its secret. Twilio displays the secret once.
4. Open **Voice > Manage > TwiML Apps** and create a TwiML App named `Stonegate OS`.
5. Set its Voice Request URL to the following HTTP `POST` endpoint:

```text
https://YOUR-API-HOST/api/v1/webhooks/twilio/voice/outbound
```

6. Save the TwiML App SID, which starts with `AP`.

The API key mints short-lived browser tokens. The Account SID identifies the Twilio account. The
TwiML App tells Twilio where Stonegate's authorized outbound browser calls should be routed. These
values have different jobs and are all required.

## 2. Configure `oakwell-api` In Render

The Render service retains its existing infrastructure name even though the product is Stonegate.
Add these variables only to `oakwell-api`:

| Key | Value |
| --- | --- |
| `TWILIO_ACCOUNT_SID` | Existing Account SID starting with `AC` |
| `TWILIO_AUTH_TOKEN` | Existing Auth Token |
| `TWILIO_API_KEY_SID` | New API Key SID starting with `SK` |
| `TWILIO_API_KEY_SECRET` | New API key secret |
| `TWILIO_TWIML_APP_SID` | Stonegate TwiML App SID starting with `AP` |
| `TWILIO_VOICE_FROM_NUMBER` | `+16785417725` |
| `TWILIO_WEBHOOK_BASE_URL` | Public API origin, such as `https://oakwell-api.onrender.com` |
| `TWILIO_VALIDATE_WEBHOOK_SIGNATURES` | `true` |
| `TWILIO_VOICE_ENABLED` | Keep `false` until the activation steps are complete |
| `TWILIO_VOICE_TOKEN_TTL_SECONDS` | `3600` |
| `TWILIO_VOICE_RING_TIMEOUT_SECONDS` | `25` |
| `TWILIO_VOICE_TIMEZONE` | `America/New_York` |
| `TWILIO_VOICE_ALLOWED_START_HOUR` | `9` |
| `TWILIO_VOICE_ALLOWED_END_HOUR` | `20` |
| `TWILIO_VOICE_RECORDING_ENABLED` | Keep `false` initially |
| `TWILIO_VOICE_RECORDING_DISCLOSURE` | Leave blank while recording is disabled |
| `CALL_RECORDING_RETENTION_DAYS` | `180` until Stonegate approves a different policy |

Voice has its own contact window and remains limited to 9:00 AM–8:00 PM Eastern even though
Stonegate permits staff SMS at any hour.

Never add Twilio secrets to `oakwell-web`, GitHub, or a `NEXT_PUBLIC_` variable. The browser only
receives a short-lived, user-specific Voice token from the authenticated Stonegate API.

## 3. Deploy Before Moving Incoming Voice

1. Confirm the latest `main` deployment is healthy.
2. Confirm the API migration reaches `0020_twilio_voice`.
3. Confirm `https://YOUR-API-HOST/health` returns `200`.
4. Set `TWILIO_VOICE_ENABLED=true` on `oakwell-api` and redeploy.
5. Sign in to Stonegate and open **OS > Inbox**.
6. Select **Enable calling** and allow microphone access.
7. Confirm the status changes to **Ready on +16785417725**.
8. Place an outbound test call to a phone you control from a consented test lead.

Outbound calling is ready at this point. The browser cannot supply an arbitrary destination; it
can only consume a short-lived call intent created for the selected Stonegate conversation.

## 4. Move The Inbound Voice Webhook

After outbound testing passes, open Twilio **Phone Numbers > Manage > Active numbers** and select
`+16785417725`. Under **Voice configuration**, set **A call comes in** to **Webhook**, HTTP `POST`:

```text
https://YOUR-API-HOST/api/v1/webhooks/twilio/voice/incoming
```

Save the number, enable calling in the Stonegate inbox, and call `+16785417725` from a phone you
control. Known callers route to the conversation owner. Unknown callers create a new lead with an
`Address pending` property so the call is retained. An unanswered inbound call creates a
high-priority return-call task due in five minutes.

## 5. Recording Activation

Recording remains off until Stonegate has approved recording disclosure and retention rules for
its operating states. The application will not treat recording as configured unless Voice,
recording, and a non-empty disclosure are all enabled.

When approved:

1. Set `TWILIO_VOICE_RECORDING_DISCLOSURE` to the approved spoken disclosure.
2. Set `TWILIO_VOICE_RECORDING_ENABLED=true`.
3. Redeploy `oakwell-api`.
4. Test inbound and outbound disclosure with a phone you control.
5. Confirm the completed recording appears once in the inbox call timeline.
6. Confirm the call shows a disclosure status, a transcript is queued, and the audio displays its
   retention deadline.

Stonegate stores only the Twilio recording identifier and private provider reference. Audio is
retrieved through an authenticated API endpoint and is never exposed as a public Twilio URL.
The worker transcribes completed calls with speaker identification and places AI notes into human
review. Audio is deleted from Twilio after `CALL_RECORDING_RETENTION_DAYS`; the transcript and
reviewed CRM notes remain as historical records.

Owners and CEOs can delete audio before the retention deadline from the inbox. Early deletion
requires a written reason, removes the provider audio, preserves the transcript, and creates an
audit event. Acquisition representatives can play recordings but cannot delete them. Prospecting
callers cannot access recordings or transcripts.

## Safety Behavior

- Every Twilio webhook validates `X-Twilio-Signature`.
- Browser calls require a user-scoped token and a one-time, conversation-scoped call intent.
- Call intents expire after five minutes and cannot be reused for another call.
- Outbound calls require a valid number, contact permission, allowed hours, no active suppression,
  an authorized role, and a configured Stonegate line.
- Duplicate and out-of-order Twilio callbacks do not duplicate or regress call history.
- Phone numbers stay company-owned when staff or contractors leave.
