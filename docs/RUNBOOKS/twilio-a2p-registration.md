# Stonegate A2P 10DLC Registration

Last updated: July 20, 2026

## Current Status

Stonegate's separate Low Volume Mixed Campaign has been submitted and is under provider review.
Approval timing is controlled by Twilio and carrier review; resume this runbook when the Campaign
shows approved or verified.

Submitted public evidence:

- Opt-in form: `https://oakwell-web.onrender.com/get-a-cash-offer`
- Privacy Policy: `https://oakwell-web.onrender.com/privacy-policy`
- Terms: `https://oakwell-web.onrender.com/terms`

The public pages were verified live before submission. The form uses a separate, optional,
unchecked SMS checkbox and the API stores versioned consent evidence.

The canonical submitted campaign description, samples, consent flow, and message-content answers
are in `twilio-a2p-campaign.md`.

## Separation Rules

- The Twilio account may be shared because Account SID and Auth Token are account-level.
- Stonegate must use its own Brand/Campaign relationship, Messaging Service, and newly purchased
  SMS number.
- Do not attach another company's phone number or Messaging Service.
- Do not point another company's webhook at Stonegate.
- Do not assume the Voice/support number is the new SMS sender.

Configuration values after approval:

```text
TWILIO_MESSAGING_SERVICE_SID=<NEW_STONEGATE_MESSAGING_SERVICE_SID>
TWILIO_SMS_FROM_NUMBER=<NEW_CAMPAIGN_APPROVED_SMS_NUMBER_IN_E164>
```

The Voice line remains independently configured through `TWILIO_VOICE_FROM_NUMBER`.

## While Review Is Pending

- Do not change the application answers unless Twilio requests a correction.
- Keep the submitted opt-in, privacy, and terms URLs publicly available.
- Do not remove or materially weaken the submitted consent wording.
- Do not send production application-to-person traffic from the new number.
- Record any reviewer request and the exact response in this file before resubmitting.

## Post-Approval Checklist

1. Confirm Campaign status is approved or verified.
2. Open the new Stonegate Messaging Service.
3. Add only the newly purchased Stonegate SMS number to its Sender Pool.
4. Confirm the number shows registered with the approved Campaign.
5. Enable Twilio's standard or Advanced Opt-Out behavior for STOP, START, and HELP.
6. Configure incoming messages as HTTP `POST` to:

   `https://oakwell-api.onrender.com/api/v1/webhooks/twilio/messaging/incoming`

7. Enter the new Messaging Service SID and new SMS number on `oakwell-api`.
8. Confirm `TWILIO_AUTH_TOKEN` is the actual Auth Token, not the Account SID.
9. Set `TWILIO_SMS_ENABLED=true` and redeploy the API.
10. Activate immediate enrollment confirmation for new website SMS opt-ins.
11. Test with a company-controlled phone:
    - outbound,
    - delivered status,
    - inbound reply,
    - STOP suppression,
    - blocked send after STOP,
    - START restoration,
    - HELP response,
    - duplicate callback behavior.
12. Verify all events appear once in the correct Stonegate conversation.

## Production Rules

- Send only to contacts with active SMS consent or a valid inbound conversational context.
- Do not treat call permission as text permission.
- Identify Stonegate Home Buyers in the initial message.
- Include STOP instructions in the initial message.
- Honor suppression across the whole Stonegate workspace.
- Do not use purchased, rented, scraped, or transferred consent.
- Do not use this Campaign for cold SMS.
- Retain consent evidence until withdrawal and as long as required by policy or law.

## References

- A2P overview: https://www.twilio.com/docs/messaging/compliance/a2p-10dlc
- Registration quickstart:
  https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/quickstart
- Messaging Policy: https://www.twilio.com/en-us/legal/messaging-policy
