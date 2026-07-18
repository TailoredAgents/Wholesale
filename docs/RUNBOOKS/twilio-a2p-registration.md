# Stonegate A2P 10DLC Registration

This runbook prepares a separate Stonegate Home Buyers Brand, Campaign, Messaging Service, and
sender without changing another company's campaign. Submit the registration only after the public
website changes in this runbook are deployed.

Twilio's current guidance says campaign review can take 10-15 days or two to three weeks during
high-volume periods. Do not plan around a two-day approval.

## Recommended Structure

- The Twilio account may remain the same. Account SID and Auth Token are account-level credentials.
- Create a separate Customer Profile and Brand for Stonegate if it is a separate legal entity.
- Create a new Campaign named `Stonegate Seller Property Inquiries`.
- Create a new Messaging Service named `Stonegate Home Buyers`.
- Associate only Stonegate's `+1 678-541-7725` number with that Messaging Service.
- Do not move or modify the `+1 404-777-2631` number or the other company's Messaging Service.

A Messaging Service can be linked to only one A2P Campaign. Keeping Stonegate separate prevents
configuration and registration changes from interrupting the other software.

## Before Starting

Gather:

- Exact legal business name from the IRS CP 575 or 147C letter if Stonegate has an EIN.
- EIN, entity type, formation state, legal address, and business contact information.
- Authorized representative's name, title, email, and mobile number.
- Stonegate's live website URL.

Use a **Low-Volume Standard Brand** when the US business has an EIN and expects fewer than roughly
6,000 message segments per day. Use **Sole Proprietor** only when the US or Canadian sole
proprietorship does not have an EIN or Canadian Business Number. The legal profile must match
government records exactly; `Stonegate Home Buyers` can be the public brand while the profile uses
the registered legal entity name.

## Public Evidence

After deployment, verify these pages without signing in:

- Opt-in form: `https://oakwell-web.onrender.com/get-a-cash-offer`
- Privacy Policy: `https://oakwell-web.onrender.com/privacy-policy`
- Terms & Conditions: `https://oakwell-web.onrender.com/terms`

The form's SMS checkbox must be visible, optional, unchecked by default, and separate from general
phone/email contact permission. The API stores the SMS wording version, exact wording, source,
timestamp, IP address, and browser user agent. Selecting `Text` as the preferred contact method
requires the seller to check the SMS box.

Replace the Render URLs with Stonegate's custom domain before submitting if that domain is already
live. Do not submit URLs that redirect to a login, return an error, or show a different business.

## Console Registration

1. Open **Messaging > Regulatory Compliance > Onboarding** in Twilio.
2. Create or select Stonegate's Customer Profile.
3. Register Stonegate as the correct Brand type.
4. Complete the Brand contact email verification.
5. Create a new Messaging Service named `Stonegate Home Buyers`.
6. Add `+1 678-541-7725` to its Sender Pool.
7. Register a new A2P Campaign against that Messaging Service.
8. Enable Advanced Opt-Out with the standard STOP, START, and HELP behavior.
9. Submit the Campaign and wait for both Campaign and phone-number registration to show approved.
10. Put the new Messaging Service SID in `TWILIO_MESSAGING_SERVICE_SID` on `oakwell-api`, then
    redeploy and test STOP, START, HELP, inbound SMS, and outbound delivery.

## Campaign Answers

### Use case

Choose **Low Volume Mixed** when available. The messages combine customer-care follow-up,
appointment information, and related marketing follow-up for property owners who explicitly ask
Stonegate to contact them. If Twilio offers only a single-purpose choice for the selected Brand,
choose the option Twilio identifies for mixed customer care and marketing rather than mislabeling
the traffic.

### Campaign description

```text
Stonegate Home Buyers sends one-to-one and automated SMS to property owners who explicitly opt in
on our public cash-offer request form. Messages concern the property inquiry they submitted,
qualification questions, requested follow-up, appointment scheduling and reminders, cash-offer
updates, and related seller follow-up. Message frequency varies by the seller's inquiry and
responses. Stonegate does not use purchased consent or send messages on behalf of third parties.
Recipients can reply STOP to opt out and HELP for help.
```

### Message flow / how users opt in

```text
Property owners opt in at https://oakwell-web.onrender.com/get-a-cash-offer. The user enters a
mobile number and separately checks an optional, unchecked SMS consent box. The disclosure names
Stonegate Home Buyers, identifies the message topics, states that messages may be recurring and
automated, states that message frequency varies and message/data rates may apply, explains STOP and
HELP, states that consent is not a condition of purchase, and links to the public Terms &
Conditions and Privacy Policy. The user then submits the form. The system records the disclosure
version, exact wording, timestamp, source, IP address, and user agent. Users who do not check the
SMS box may still submit a property inquiry but are not eligible for outbound SMS.
```

Select **Website form** as the opt-in method. Do not select QR code, paper form, verbal consent, or
keyword opt-in unless Stonegate actually launches and documents those workflows.

### Opt-in keywords

Leave this field blank when the registration uses only the website form. Twilio's standard START
handling may still restore messaging after a prior STOP.

### Opt-in confirmation

```text
Stonegate Home Buyers: You are subscribed to texts about your property inquiry, appointments, and
cash-offer updates. Message frequency varies. Msg & data rates may apply. Reply HELP for help or
STOP to opt out.
```

Use this as the immediate confirmation or as the opening disclosure in the first message before
sending ongoing campaign messages.

### Sample message 1

```text
Stonegate Home Buyers: Hi [First Name], thanks for requesting a cash-offer review for [Property
Address]. May I ask a few questions about the property? Reply STOP to opt out.
```

### Sample message 2

```text
Stonegate Home Buyers: Your property call is scheduled for [Date] at [Time]. Reply HELP for help or
STOP to opt out.
```

### Sample message 3

```text
Stonegate Home Buyers: Hi [First Name], we have an update about the cash-offer review for [Property
Address]. Is this a good time to discuss it? Reply STOP to opt out.
```

### HELP response

```text
Stonegate Home Buyers: Help with your property inquiry is available at (678) 541-7725 or
https://oakwell-web.onrender.com. Msg & data rates may apply. Reply STOP to opt out.
```

### STOP response

Use Twilio's standard Advanced Opt-Out confirmation:

```text
Stonegate Home Buyers: You have opted out and will receive no further messages. Reply START to
subscribe again.
```

### Other campaign questions

- Subscriber opt-in: **Yes**
- Subscriber opt-out: **Yes**
- Subscriber help: **Yes**
- Number pooling: **No**
- Direct lending or loan arrangement: **No**
- Embedded links: **No**, unless the actual campaign will send the website links shown in samples
- Embedded phone numbers: **No**, unless the actual samples include the Stonegate support number
- Age-gated content: **No**
- Affiliate marketing: **No**

Keep the answers consistent with the submitted samples. If the Console asks whether messages
contain a phone number because the HELP sample includes one, answer **Yes** and use the same
Stonegate number in the sample.

## Production Rules

- Send only to contacts with an active `sms` consent record.
- Identify Stonegate Home Buyers in the initial message and include STOP instructions.
- Honor STOP immediately across the whole Stonegate workspace.
- Do not treat permission to call as permission to text.
- Do not upload purchased lists as consented contacts.
- Keep consent evidence at least until consent is withdrawn and as long as legally required.
- Do not send from the Stonegate Campaign for another company or use another company's Campaign for
  Stonegate.

## Twilio References

- A2P overview: https://www.twilio.com/docs/messaging/compliance/a2p-10dlc
- Registration quickstart: https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/quickstart
- Required business information:
  https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/collect-business-info
- Standard and low-volume onboarding:
  https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/direct-standard-onboarding
- Messaging Policy: https://www.twilio.com/en-us/legal/messaging-policy
