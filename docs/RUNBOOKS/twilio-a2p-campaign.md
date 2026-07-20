# Twilio A2P Campaign Registration

Use this runbook for Stonegate Home Buyers' separate seller-communications campaign. This campaign
is limited to people who explicitly consent through Stonegate's public cash-offer form. It does not
cover purchased lists, third-party lead consent, or unsolicited cold SMS.

## Campaign And Messaging Service

- Use case: `Low Volume Mixed`
- Messaging Service: create a new service with the campaign
- Suggested service name: `Stonegate Seller Communications`
- Do not reuse another company's Messaging Service
- Add the new Stonegate 10DLC number as a sender only after the campaign is approved

## Campaign Description

```text
This campaign sends recurring, low-volume SMS messages from Stonegate Home Buyers to Georgia
property owners who explicitly opt in through the Stonegate cash-offer request form. Messages
respond to a property inquiry and may include qualification questions, appointment scheduling and
reminders, cash-offer status updates, and related one-to-one follow-up. Stonegate does not use this
campaign for purchased lists or unsolicited cold messaging.
```

## Sample Messages

```text
Stonegate Home Buyers: Thanks for opting in to texts about your property inquiry. Message frequency
varies. Msg & data rates may apply. Help: 678-541-7725. Reply STOP to unsubscribe.
```

```text
Stonegate Home Buyers: Hi [first name], we received your property inquiry. Is [preferred time] a
good time to discuss the home? Reply STOP to unsubscribe.
```

```text
Stonegate Home Buyers: Your property appointment is scheduled for [date] at [time]. Reply HELP for
help or STOP to unsubscribe.
```

```text
Stonegate Home Buyers: We have an update about your cash-offer request. Are you available at [time]
for a quick call? Reply STOP to unsubscribe.
```

```text
Stonegate Home Buyers: Just checking whether you still want to discuss options for your property.
Reply YES to continue or STOP to unsubscribe.
```

## Message Contents

- Embedded links: `No`
- Phone numbers: `Yes`
- Direct lending or loan arrangements: `No`
- Age-gated content: `No`

The support phone number is disclosed in the first sample. Do not send embedded links under this
campaign unless the campaign registration and samples are updated to disclose them.

## Consent Flow

```text
End users opt in only through the publicly accessible Stonegate Home Buyers cash-offer form at
https://oakwell-web.onrender.com/get-a-cash-offer. They enter their own mobile number and
voluntarily check a separate, unchecked SMS consent box stating that they agree to recurring
automated texts about their property inquiry, appointments, and cash-offer updates; message
frequency varies; message and data rates may apply; reply STOP to opt out or HELP for help; and
consent is not a condition of purchase. The form links directly to
https://oakwell-web.onrender.com/terms and https://oakwell-web.onrender.com/privacy-policy.
Stonegate stores the consent timestamp, source, wording version, IP address, and user agent.
Stonegate does not use purchased, rented, or third-party lead consent and does not send unsolicited
cold SMS.
```

## Policy URLs

- Privacy Policy: `https://oakwell-web.onrender.com/privacy-policy`
- Terms and Conditions: `https://oakwell-web.onrender.com/terms`

Replace these URLs with Stonegate's branded custom domain before submitting if that domain is
already live. Do not submit URLs that redirect to an unrelated brand or are not publicly accessible.

## Keyword Opt-In

Stonegate's initial opt-in method is the website checkbox only:

- Opt-in keywords: leave blank
- Opt-in message: leave blank

Do not claim keyword opt-in until the new number is configured to recognize the disclosed keywords
and send the disclosed confirmation. Use Twilio's default or Advanced Opt-Out handling for STOP,
START, and HELP after the Messaging Service exists.

## Operational Rules

- Send an enrollment confirmation immediately after a website SMS opt-in once the approved
  Messaging Service is connected.
- Identify Stonegate Home Buyers in every initial or automated message.
- Include `Reply STOP to unsubscribe` in the initial message.
- Honor STOP immediately and preserve the suppression record.
- Send only the message subjects covered by the checkbox and campaign description.
- Retain the consent wording, version, timestamp, source, IP address, and user agent.
