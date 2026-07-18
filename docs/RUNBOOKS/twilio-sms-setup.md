# Twilio SMS Setup

Phase 3 uses a Twilio Messaging Service so Stonegate owns the phone numbers, routing, opt-out
controls, and delivery callbacks in one place. SMS is disabled by default and will not send until
the API service is configured and `TWILIO_SMS_ENABLED` is set to `true`.

## 1. Prepare Twilio

1. In the Twilio Console, open **Messaging > Services** and create or select Stonegate's Messaging
   Service.
2. Add the company-owned Twilio phone number under **Sender Pool**. Stonegate explicitly sends
   from this number, even if the approved Messaging Service contains other senders.
3. Review and enable **Advanced Opt-Out** for the service. Keep the standard STOP, START, and HELP
   keywords unless legal counsel directs otherwise.
4. Copy the Account SID and Messaging Service SID. The Account SID starts with `AC`; the Messaging
   Service SID starts with `MG`.
5. Copy the Auth Token. Stonegate uses it to verify Twilio webhook signatures.

Twilio trial accounts can send only to verified recipient numbers. Production messaging may also
require A2P 10DLC registration for US application-to-person traffic.

## 2. Configure `oakwell-api` In Render

The Render service retains its existing infrastructure name even though the product is Stonegate.
Add these environment variables only to the API service:

| Key | Value |
| --- | --- |
| `TWILIO_ACCOUNT_SID` | Account SID from Twilio |
| `TWILIO_AUTH_TOKEN` | Auth Token from Twilio |
| `TWILIO_MESSAGING_SERVICE_SID` | Messaging Service SID from Twilio |
| `TWILIO_SMS_FROM_NUMBER` | Stonegate sender in E.164 format: `+16785417725` |
| `TWILIO_WEBHOOK_BASE_URL` | Public API origin, such as `https://oakwell-api.onrender.com` |
| `TWILIO_VALIDATE_WEBHOOK_SIGNATURES` | `true` |
| `TWILIO_SMS_ENABLED` | `true` after the remaining steps are complete |
| `TWILIO_SMS_TIMEZONE` | `America/New_York` |
| `TWILIO_SMS_ALLOWED_START_HOUR` | `0` |
| `TWILIO_SMS_ALLOWED_END_HOUR` | `24` |

Do not add Twilio secrets to `oakwell-web`, GitHub, or any `NEXT_PUBLIC_` variable.

The optional `TWILIO_API_KEY_SID` and `TWILIO_API_KEY_SECRET` values can be used together for
outbound API authentication. Keep both the Account SID and Auth Token configured because Twilio
signs webhooks with the account's Auth Token.

## 3. Configure The Twilio Webhook

If the Messaging Service contains numbers used by multiple applications, keep its incoming-message
handling set to **Defer to sender's webhook**. Open the Stonegate phone number and configure its
incoming-message webhook as an HTTP `POST` to:

```text
https://YOUR-API-HOST/api/v1/webhooks/twilio/messaging/incoming
```

Stonegate supplies a status callback for every outbound message automatically:

```text
https://YOUR-API-HOST/api/v1/webhooks/twilio/messaging/status
```

`TWILIO_WEBHOOK_BASE_URL` must exactly match the public scheme and host Twilio uses. Signature
validation uses the complete callback URL, so a different host or an extra trailing slash will
cause a rejected webhook.

Do not set a shared service-level incoming webhook when the service contains another application's
number. That would route inbound messages for every sender in the service into Stonegate.

## 4. Activate And Test

1. Redeploy `oakwell-api` after the environment variables are saved.
2. Confirm `/health` returns `200`.
3. Set `TWILIO_SMS_ENABLED` to `true` and redeploy the API.
4. Open **OS > Inbox** and select a lead with a valid E.164 phone number and SMS consent.
5. Send a short test message to a phone you control.
6. Confirm the timeline changes from `queued` or `sent` to `delivered`.
7. Reply from the phone and confirm the inbound message appears once in the same conversation.
8. Send `STOP`; confirm the inbox shows the number as suppressed and prevents another outbound
   message.
9. Send `START`; confirm the suppression is lifted before sending again.

If the test fails, inspect the `oakwell-api` logs for the outbound request or webhook response and
check the Twilio Messaging logs for the provider error code.

## Safety Behavior

- Every outbound attempt requires an idempotency key, preventing double sends from repeated clicks.
- Messages are blocked without a valid phone number, consent, permitted contact hours, and a fully
  configured provider.
- Stonegate's configured SMS window is `0–24`, so staff can send at any hour. Consent and
  suppression checks still apply.
- Active STOP suppression blocks every Stonegate user, not only the person who received the reply.
- Inbound and status callbacks validate `X-Twilio-Signature` and retain provider event identifiers.
- Disabling `TWILIO_SMS_ENABLED` stops new outbound messages without removing communication history.
