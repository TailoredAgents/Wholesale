# How To Set Up And Maintain Stonegate

Last verified against the repository: July 29, 2026

## Who This Guide Is For

This guide is for the Stonegate owner or the trusted person responsible for company accounts,
domains, staff access, and production services. It explains setup without requiring software
development knowledge.

Use [SETUP_REFERENCE.md](./SETUP_REFERENCE.md) when a developer needs exact environment-variable
names or commands. Use this guide when the question is, “What do I do, where do I do it, and how
do I know it worked?”

## The Two Places Where Setup Happens

Stonegate setup is split between:

1. **Outside provider accounts**, such as Render, Clerk, Resend, Twilio, SignWell, OpenAI,
   RentCast, and RealEstateAPI.
2. **Stonegate OS**, where the owner creates staff users, teams, sender permissions, templates,
   roles, operating policies, and assignments.

An outside provider credential normally goes into the **oakwell-api** or **oakwell-web**
environment variables in Render. It does not belong in a Stonegate note, source file, email,
chat message, or employee manual.

## Current Production Services

Do not create a second set of Render services just because the existing names still say Oakwell.
Those names are infrastructure labels. The live company, domain, and product are Stonegate.

| Purpose | Existing resource |
| --- | --- |
| Public website and OS | `oakwell-web` |
| Stonegate API | `oakwell-api` |
| Background jobs | `oakwell-worker` |
| Main database | `oakwell-postgres` |
| Worker coordination | `oakwell-key-value` |
| Public website | `https://www.stonegatehb.com` |
| API | `https://api.stonegatehb.com` |

Deleting or replacing an Oakwell-named database or service could delete or disconnect Stonegate
data. Rename infrastructure only as a planned migration, never by creating duplicates casually.

## Recommended Setup Order

Follow this order for a new environment or a complete production review:

1. Confirm Render services and branded domains.
2. Confirm Clerk authentication.
3. Confirm the owner account and create staff accounts.
4. Confirm OpenAI and RentCast.
5. Configure and test Resend email.
6. Configure SignWell and contract templates.
7. Activate Twilio SMS only after A2P approval.
8. Configure Twilio Voice.
9. Deploy and test RealEstateAPI property intelligence on the API and worker.
10. Configure bank, vendor, accounting, and compensation policy.
11. Test backups and production health.
12. Train each employee using **My Setup** and the role manuals.

The system can operate while some providers remain pending. A provider should be labeled
configured only after its settings exist, and active only after a real controlled test passes.

## Render: The Main Configuration Location

### Where To Go

1. Sign in to Render.
2. Open the Stonegate workspace.
3. Open the service named **oakwell-api** for API, database-facing, and provider settings.
4. Open **Environment**.
5. Add or update the requested key and value.
6. Save changes.
7. Allow Render to redeploy.
8. Open **Logs** and confirm startup succeeds.

Use **oakwell-web** only for browser-facing settings such as the Clerk publishable key and public
API/site URLs. Most private provider keys belong on **oakwell-api**.

### What A Render Variable Contains

The **Key** is the exact uppercase name documented by Stonegate. The **Value** comes from the
provider account. For example:

| Key | Value comes from |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI API Keys |
| `RENTCAST_API_KEY` | RentCast account |
| `REALESTATEAPI_API_KEY` | RealEstateAPI account |
| `RESEND_API_KEY` | Resend API Keys |
| `TWILIO_ACCOUNT_SID` | Twilio Account Info |
| `TWILIO_AUTH_TOKEN` | Twilio Account Info; it is not the Account SID |
| `ESIGN_API_KEY` | SignWell API settings |
| `DEALMACHINE_API_KEY` | Optional legacy DealMachine buyer discovery only |

Do not put quotation marks around a value unless the documented value itself requires them.
Do not add spaces before or after a key.

### After Every Render Change

1. Wait for the deployment to show **Live**.
2. Open `https://api.stonegatehb.com/health`.
3. Confirm it responds successfully.
4. Sign in at `https://www.stonegatehb.com/os`.
5. Test the exact feature affected by the change.
6. Check the API logs for a successful request.

A successful deployment proves that the application started. It does not prove that an email,
text, call, signature, or data-provider request works.

## Domains And DNS

### Stonegate Domains

- Public website: `www.stonegatehb.com`
- API: `api.stonegatehb.com`
- Apex domain: `stonegatehb.com`

The DNS owner adds records supplied by Render, Resend, and other approved providers. Copy records
exactly. Do not improvise hostnames, record types, or values.

### Domain Acceptance

Confirm all of these:

1. `https://www.stonegatehb.com` loads the public website.
2. The cash-offer form submits successfully.
3. `/os` sends a signed-out person to Clerk.
4. A signed-in employee sees the correct navigation.
5. `https://api.stonegatehb.com/health` works.
6. API logs do not show CORS or Clerk authorized-party errors.

If the OS says access is being verified and API logs show
`clerk_authorized_party_invalid`, add the exact current website origin to
`CLERK_AUTHORIZED_PARTIES` on **oakwell-api**, save, and redeploy.

## Google Search And Local Presence

### Search Console

Search Console shows whether Google can discover and index Stonegate's public pages. Use a domain
property so the root domain, `www`, and any future public subdomains are covered together.

1. Open Google Search Console and add the domain property `stonegatehb.com`.
2. Copy Google's TXT verification record into the DNS provider for `stonegatehb.com`.
3. Wait for DNS propagation, then select **Verify** in Search Console.
4. Submit `https://www.stonegatehb.com/sitemap.xml` under **Sitemaps**.
5. Use **URL Inspection** for:
   - `https://www.stonegatehb.com/`
   - `https://www.stonegatehb.com/service-areas/metro-atlanta`
   - `https://www.stonegatehb.com/contact`
   - `https://www.stonegatehb.com/get-a-cash-offer`
6. Request indexing only after each URL loads on the canonical branded domain.
7. Review indexing, performance, mobile usability, and enhancement reports monthly.

Google reference:
`https://support.google.com/webmasters/answer/9008080`

### Google Business Profile

Stonegate should use one accurate service-area Business Profile for its current operation.

1. Use the real-world business name **Stonegate Home Buyers**.
2. Choose the closest accurate primary category available for the actual business.
3. Use the permanent dedicated Stonegate phone only after it is confirmed.
4. Set the website to `https://www.stonegatehb.com`.
5. If sellers do not visit a staffed Stonegate office during stated hours, hide the address and
   configure the profile as a service-area business.
6. Add only owner-approved cities, ZIP codes, or named service areas Stonegate can genuinely serve.
7. Keep the overall area operationally realistic; do not add locations merely for ranking.
8. Do not use a virtual office, mailbox, or unstaffed address as a storefront.
9. Publish staffed hours only after they are confirmed.
10. Use real Stonegate photos and request genuine reviews without incentives or fabricated text.

### Public Team Photographs

The website team layouts are already built, but they remain hidden until approved real content is
added. Follow `docs/PUBLIC_TEAM_CONTENT.md` rather than adding a temporary portrait or biography.
For each active person, collect the approved public name, title, biography, portrait, permission,
display order, and homepage-feature decision. Add the optimized portrait to
`apps/web/public/images/team/` and the complete record to
`apps/web/src/app/public-team.ts`.

No environment variable or provider account is required. The build rejects incomplete or
placeholder records. After publication, verify both the homepage and About page on desktop and a
physical phone, then confirm the same real-world identity is used consistently in the Business
Profile.

Do not create separate profiles for Atlanta-area cities unless Stonegate later operates separate,
permanently staffed locations that independently qualify.

For review collection, ask real sellers for an honest review without requiring a positive rating
and without offering payment, discounts, or other benefits. Do not ask employees, family members,
or contractors to appear independent. A review copied to the Stonegate website must also pass the
Marketing public-proof workflow and have documented permission for website use.

Review-policy references:
`https://www.ftc.gov/business-guidance/resources/consumer-reviews-testimonials-rule-questions-answers`
and `https://support.google.com/contributionpolicy/answer/7400114`.

Google references:
`https://support.google.com/business/answer/3038177` and
`https://support.google.com/business/answer/9157481`

### Structured Data Acceptance

1. Test the homepage and Metro Atlanta page with Google's Rich Results Test.
2. Test the JSON-LD with Schema.org Validator.
3. Confirm the visible name, phone, email, service area, page description, and structured data all
   agree.
4. Keep Organization markup until a qualifying staffed address exists. Do not add a false address
   just to qualify for LocalBusiness markup.
5. Confirm the production sitemap contains the Metro Atlanta page and no private OS routes.

## Clerk: Employee Sign-In

### What Clerk Does

Clerk proves who signed in. Stonegate separately decides what that person may see and do.
Creating a person in Clerk alone does not create their Stonegate job access.

### Owner Setup

1. Open the Clerk application used by Stonegate.
2. Confirm the production domain and redirect URLs use `stonegatehb.com`.
3. Copy the publishable key to `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` on **oakwell-web**.
4. Copy the secret key to `CLERK_SECRET_KEY` where documented.
5. Copy the Clerk issuer to `CLERK_ISSUER` on **oakwell-api**.
6. Set `CLERK_JWKS_URL` to the issuer followed by `/.well-known/jwks.json`.
7. Add the public website origins to `CLERK_AUTHORIZED_PARTIES`.

The issuer and JWKS URL point to Clerk, not to `api.stonegatehb.com`.

### Adding An Employee

1. In Stonegate, open **Operations > Team**.
2. Select **Create user**.
3. Enter the employee's real work email, name, and role.
4. Save the Stonegate user.
5. Have the employee sign up or accept the Clerk invitation using that same email.
6. Assign the employee to the correct team and operating seat.
7. Open **Operating Model** and assign their role setup.
8. Have the employee open **My Setup**, test their workspace, and submit evidence.
9. Verify they can see only the expected pages.

Never share one Clerk login among employees or VAs.

### Removing An Employee

1. Reassign their leads, conversations, tasks, appointments, and operating seat.
2. Deactivate the Stonegate user in **Operations > Team**.
3. Disable or remove their Clerk access.
4. Remove sender grants and shared-mailbox access.
5. Remove them from teams and coverage.
6. Confirm they can no longer sign in.

Do not delete operational history merely because an employee leaves.

## Stonegate Roles

Use the role matching the actual job:

| Job | Stonegate role |
| --- | --- |
| Owner/CEO | Owner |
| Warm lead qualification | Lead Manager |
| Cold caller | VA Caller |
| Seller appointment and negotiation | Acquisitions Closer |
| Contract-to-close paperwork | Transaction Coordinator |
| Buyer marketing and offers | Dispositions |
| Books, bills, reconciliation, tax preparation | Finance and Accounting |
| Campaign reporting | Marketing |

One person can cover more than one operating seat, but their actions should still show which job
they performed. Do not give every employee Owner access for convenience.

## OpenAI

### What It Powers

OpenAI powers Stonegate Copilots, controlled underwriting research, call transcription and notes,
and the internal documentation help assistant. Copilots remain advisory unless a separately
approved automation explicitly performs an action.

### Setup

1. Open the OpenAI platform account.
2. Create or choose the Stonegate project.
3. Add billing and a reasonable project budget.
4. Create an API key for Stonegate.
5. Put it in `OPENAI_API_KEY` on **oakwell-api**.
6. Confirm `AI_ENABLED=true`.
7. Keep `OPENAI_BASE_URL=https://api.openai.com/v1`.
8. Use the approved model values already defined in `render.yaml`.
9. Redeploy.

### Acceptance

1. Open **AI Control** as Owner.
2. Confirm runtime/provider health.
3. Open a normal role page with a Copilot.
4. Generate a draft.
5. Confirm it cites Stonegate evidence and can be accepted, corrected, or rejected.
6. Open **Help** and ask what a visible button does.
7. Confirm the answer cites an approved manual section.

Do not enable autonomous external actions merely because draft generation works.

## RentCast Property Data

### Setup

1. Open RentCast.
2. Copy the API key.
3. Set `PROPERTY_DATA_PROVIDER=rentcast`.
4. Add the key to `RENTCAST_API_KEY` on **oakwell-api**.
5. Keep `RENTCAST_BASE_URL=https://api.rentcast.io/v1`.
6. Redeploy.

### Acceptance

1. Create or open a test Georgia lead with a complete address.
2. Validate the property address.
3. Run **Analyze comps**.
4. Confirm the subject property is correct.
5. Review included and excluded comparables.
6. Download both Investor and Client PDFs.

If RentCast returns no property, verify the address and use the controlled evidence workflow.
A provider 404 does not mean Stonegate is down.

## Resend Email

### What Resend Does

Resend sends and receives company email. Stonegate owns sender permissions, shared mailboxes,
templates, signatures, threading, assignments, and response tracking.

### Outside Stonegate

1. Open Resend and verify `stonegatehb.com`.
2. Add the exact SPF and DKIM records Resend provides.
3. Configure receiving/MX records when Resend Receiving is used.
4. Add a DMARC record and begin with a monitoring policy.
5. Create a Stonegate API key.
6. Create a webhook pointing to:
   `https://api.stonegatehb.com/api/v1/webhooks/resend`
7. Subscribe to inbound and supported outbound lifecycle events.
8. Copy the webhook signing secret.

### In Render

Confirm:

- `EMAIL_ENABLED=true`
- `EMAIL_PROVIDER=resend`
- `EMAIL_SYNC_ENABLED=true`
- `RESEND_API_KEY` contains the Resend key
- `RESEND_WEBHOOK_SECRET` contains the webhook signing secret
- sending and receiving domains are `stonegatehb.com`
- the webhook base URL is `https://api.stonegatehb.com`

### Inside Stonegate

As Owner:

1. Open **Inbox**.
2. Open email administration.
3. Create approved addresses such as:
   - `austin@stonegatehb.com`
   - `offers@stonegatehb.com`
   - `buyers@stonegatehb.com`
   - `accounting@stonegatehb.com`
4. Choose whether each address is personal, team, general, or restricted.
5. Grant only the people who may send from that address.
6. Grant watchers who need to see replies.
7. Add the correct signature.
8. Create approved templates.

### Email Acceptance

For every sender:

1. Send a new message to a controlled outside address.
2. Test subject, signature, CC, BCC, and attachment.
3. Reply from the outside mailbox.
4. Confirm the reply enters the same Stonegate thread.
5. Confirm the correct person or team receives it.
6. Confirm **Unread** and **Needs Reply** work.
7. Confirm a user without a sender grant cannot use that address.
8. Test a bad recipient and confirm failure is visible.

If mail lands in spam, review SPF, DKIM, DMARC, domain reputation, message content, and recipient
engagement. Repeated test messages to disengaged recipients can make deliverability worse.

## SignWell E-Signature

### What Must Exist

SignWell hosts the signature ceremony. Stonegate creates the agreement data, approval history,
signer mapping, transaction record, and completed-document link.

### Outside Stonegate

1. Open SignWell.
2. Upload the current purchase-agreement template.
3. Add placeholder recipients named **Seller** and **Document Sender**.
4. Place every required text, initial, date, and signature field.
5. Save the template.
6. Obtain the template ID.
7. Create the Stonegate API key.
8. Create the webhook using:
   `https://api.stonegatehb.com/api/v1/webhooks/esign/signwell`

### In Render

1. Set `ESIGN_PROVIDER=signwell`.
2. Enter `ESIGN_API_KEY`.
3. Enter the webhook/provider values documented in [SETUP_REFERENCE.md](./SETUP_REFERENCE.md).
4. Keep test mode on during acceptance.
5. Redeploy.

### Inside Stonegate

1. Open a test transaction.
2. Map the SignWell template ID to the matching Stonegate contract template.
3. Create an agreement version.
4. Review every merged fact.
5. Request and obtain internal approval.
6. Send the signature request.

### Acceptance

Complete one remote test and one iPad test:

1. Verify signer names and emails.
2. Review the exact PDF before sending.
3. Complete signatures.
4. Confirm Stonegate shows provider events.
5. Confirm the completed PDF is stored with the transaction.
6. Confirm an unauthorized user cannot send or download the agreement.

The temporary template is operational draft content until professional review occurs. Stonegate
must not describe it as attorney-approved when it has not been reviewed.

## Twilio SMS

### Stonegate Line Model

- **Acquisitions:** shared warm-seller Voice and consented seller-inquiry SMS for Austin, Devon,
  and future acquisitions staff.
- **Dispositions:** separate buyer/investor Voice and SMS. Do not use the seller-inquiry A2P
  campaign for buyer marketing unless the approved campaign accurately covers that traffic.
- **VA cold calling:** BatchDialer numbers and agent seats. Warm handoffs move into Stonegate and
  continue from the acquisitions number.

### Do Not Activate Before Approval

Stonegate SMS should use its own A2P campaign, Messaging Service, and phone number. Do not attach
another company's number or campaign.

### After A2P Approval

1. Open Twilio Messaging Services and attach both approved Stonegate 10DLC numbers to the sender
   pool only when the approved campaign accurately covers both messaging purposes.
2. Under **Integration**, select **Defer to sender's webhook**.
3. Open each Stonegate number under **Phone Numbers > Manage > Active numbers**.
4. Under that number's Messaging configuration, set **A message comes in** to Webhook, `POST`:
   `https://api.stonegatehb.com/api/v1/webhooks/twilio/messaging/incoming`
5. Repeat the same number-level webhook for the acquisitions and dispositions numbers. Twilio's
   `To` value lets Stonegate identify the department line.
6. Do not add a separate Console delivery callback. Stonegate includes this callback on every
   outbound API request:
   `https://api.stonegatehb.com/api/v1/webhooks/twilio/messaging/status`
7. Copy the Account SID, separate Auth Token, Messaging Service SID, and both numbers in `+1...`
   format.

If the approved campaign only describes seller inquiries, attach only the acquisitions number.
Using one Low Volume Mixed campaign for both numbers is appropriate only when its submitted and
approved message flow, consent methods, and samples cover both seller and buyer communications.

### In Render

Enter the Twilio values on **oakwell-api**, keep webhook validation enabled, set the branded API
base URL, and set `TWILIO_SMS_ENABLED=true` only after the approved number is attached.
Use the acquisitions number for `TWILIO_SMS_FROM_NUMBER` as a deployment fallback. Add and manage
both real department numbers in **Settings > Communications**; active seller conversations select
the acquisitions line and buyer conversations select the dispositions line.

### Acceptance

1. Send one SMS to a controlled phone.
2. Confirm sent and delivered states.
3. Reply and confirm the same seller thread.
4. Send STOP and confirm Stonegate blocks another outbound message.
5. Send START and confirm provider/state recovery.
6. Send HELP and confirm the expected reply.
7. Confirm duplicate callbacks do not create duplicate messages.

Do not use the consented seller-inquiry campaign for purchased-list cold text messages.

## Twilio Voice

Stonegate uses cellphone forwarding for Voice. The company-owned Twilio number receives the call,
Stonegate chooses the responsible staff members, and Twilio rings their saved cellphones. Browser
Voice, microphone access, API keys, and a TwiML App are not required.

### Setup Order

1. Open the acquisitions number under **Phone Numbers > Manage > Active numbers**. Under Voice,
   set **A call comes in** to Webhook, `POST`:
   `https://api.stonegatehb.com/api/v1/webhooks/twilio/voice/incoming`
2. If the number provides a call-status callback field, set it to `POST`:
   `https://api.stonegatehb.com/api/v1/webhooks/twilio/voice/status`
3. Repeat those number-level settings for the dispositions number.
4. On **oakwell-api** in Render, enter:
   - `TWILIO_VOICE_ENABLED=true`
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `TWILIO_WEBHOOK_BASE_URL=https://api.stonegatehb.com`
   - `TWILIO_VALIDATE_WEBHOOK_SIGNATURES=true`
   `TWILIO_VOICE_FROM_NUMBER` is optional legacy bootstrap configuration; active company lines in
   Stonegate are the source of truth for caller ID.
5. In **Settings > Communications**, select Austin and Devon as the primary and fallback staff,
   choose **Everyone at once**, set the coverage window and **Fallback, then voicemail**, and save
   both company lines.
6. Under **Staff ring settings**, enter Austin's and Devon's cellphones in `+1...` format, enable
   **Ring cellphone**, and save each person.
7. Keep `TWILIO_VOICE_RECORDING_ENABLED=false` for the first routing test. Voicemail uses its own
   caller-initiated recording path.
8. Redeploy the API, then open **Settings > Communications**. The Voice panel must show **Ready for
   forwarded-call testing** before acceptance begins.

Call recording and AI notes are a launch requirement. For Stonegate's approved Georgia-only
one-party operating mode, set `TWILIO_VOICE_RECORDING_ENABLED=true` and leave
`TWILIO_VOICE_RECORDING_DISCLOSURE` unset; Stonegate records the authorization state without
playing an announcement. The disclosure variable remains available when Stonegate chooses or is
required to announce recording. Configure the same recording, transcription, OpenAI, and retention
values on the API and worker, and review the operating policy before calling into other states.

### Acceptance

1. Call each Stonegate number and confirm both Austin and Devon ring simultaneously.
2. Answer one test on a cellphone, confirm the department announcement, and press 1. Verify all
   other devices stop ringing and the personal number is not exposed.
3. Test no answer, missed call, voicemail, and call outcome.
4. Confirm the inbound call appears on the correct seller or buyer conversation.
5. From Inbox, select **Call > My cellphone**, answer the staff cellphone, press 1, and confirm the
   seller sees the Stonegate company number.
6. Enable recording and place a controlled call. Confirm the configured Georgia authorization is
   recorded, no announcement plays when the disclosure is blank, the recording stays private, a
   speaker-aware transcript is produced, and the AI draft extracts motivation, timeline,
   condition, occupancy, asking price, mortgage/title issues, objections, commitments, and the next
   action.
7. Review the draft, correct it if needed, apply it, and confirm Stonegate fills only empty
   motivation, timeline, condition, occupancy, asking-price, and mortgage/payoff fields; saves the
   complete summary under **Internal seller notes** and Activity; and creates the intended follow-up
   task and next-follow-up date.
8. Test rejection, a failed transcription, retry visibility, retention date, and early deletion.
9. Open **Settings > Integrations** and confirm **Call recording and AI notes** is configured before
   launch.

## RealEstateAPI Property Intelligence And Optional DealMachine Buyers

RealEstateAPI now supplies the reusable property profile and secondary comp evidence. DealMachine
is disabled and is optional only for legacy buyer discovery if that subscription is retained.

For RealEstateAPI activation:

1. Add `REALESTATEAPI_API_KEY` to both the Render API and worker services. Never paste the key into
   chat, documentation, source code, or browser settings.
2. Set `REALESTATEAPI_BASE_URL=https://api.realestateapi.com` and
   `REALESTATEAPI_REQUEST_TIMEOUT_SECONDS=30` on both services.
3. Set `UNDERWRITING_REALESTATEAPI_COMPS_MODE=candidate` on both services.
4. Set `UNDERWRITING_DEALMACHINE_COMPS_MODE=disabled` and `BUYER_DATA_PROVIDER=disabled`.
5. Redeploy API and worker, then use **Refresh research** on a known Georgia property.
6. Confirm Sources shows RentCast and RealEstateAPI, duplicate transfers appear once, and the
   Stonegate ARV is based on screened comp math rather than either provider estimate.
7. Confirm physical, tax, sale, equity, mortgage, lien, ownership, listing, and hazard signals are
   saved when returned. Unknown fields must remain unknown.
8. If the response contains licensed listing media, confirm it loads through Stonegate. If not,
   confirm the UI shows **No property photo available** with no Street View or scraped fallback.
9. Repeat **Update Stonegate valuation** without refreshing and confirm no new RealEstateAPI call is
   made. Only explicit evidence refreshes may spend another provider credit.

If DealMachine is retained solely for buyer discovery, use the legacy controlled workflow below.
Otherwise remove its key after disabling both DealMachine modes.

When ready:

1. Sign in to the paid Stonegate DealMachine account as the account owner.
2. Open the developer/API settings and create an API key.
3. Add it to `DEALMACHINE_API_KEY` in the Render API service. Never paste it into chat,
   documentation, source code, or browser settings.
4. Set `BUYER_DATA_PROVIDER=dealmachine`.
5. Keep `DEALMACHINE_BASE_URL=https://api.v2.dealmachine.com/v1` and redeploy.
6. Open a test disposition case and the Buyers section.
7. Confirm Stonegate shows the expected paid plan, billing-cycle reset, and available credits.
8. Select **Preview search cost**. This validates the same request without consuming credits.
9. Review the match count and maximum property/contact credit estimate, then select **Run buyer
   search** only when the amount is acceptable.
10. Compare the actual credit summary with the estimate.
11. Review candidates before importing them.
12. Check duplicates, contact quality, DNC handling, market fit, purchase evidence, and provider
    cost.

Stonegate's Disposition Copilot ranks reviewed internal and provider candidates. It should not
silently import or contact every result.

## Facebook Lead Forms And Staff Text Alerts

Facebook lead forms use a different connection from the website Pixel. The Pixel measures site
activity; Zapier delivers each instant-form submission to Stonegate, and the worker performs the
normal CRM intake. No Meta developer app or Graph API token is required.

1. Finish the Zapier connection, one-action mapping, and Render Page-ID steps in
   [SETUP_REFERENCE.md](./SETUP_REFERENCE.md#zapier-facebook-lead-ads-intake-and-staff-alerts).
2. Use this Stonegate action URL:
   `https://api.stonegatehb.com/api/v1/webhooks/zapier/facebook-leads`.
3. Submit one Facebook test lead containing name, phone or email, property street address, city,
   fixed state, motivation, and timeline. ZIP may be omitted when automatic enrichment is enabled.
4. Confirm the lead appears once in Stonegate with source **Facebook Lead Ads**, attribution,
   speed-to-lead work, normal intake notifications, and a provider-confirmed ZIP/county when the
   address matched confidently.
5. Under **Settings > Communications**, save each alert recipient's cellphone and enable
   **Text new Facebook leads**.
6. Activate staff texts only after the Twilio campaign/use case is approved. Confirm one delivered
   alert per enabled employee using a controlled test lead.

Stonegate never treats a Facebook lead-form phone field as seller SMS consent. The form may permit
a requested phone call, but automated or marketing texts to that seller need separate consent.

## Accounting And Banking

### Initial Setup

1. Sign in as Owner or Finance.
2. Open **Finance**.
3. Install or review the accounting setup.
4. Confirm legal/company information, fiscal year, accounting basis, chart of accounts, and
   opening date.
5. Add bank and card account records using names and last four digits only.
6. Add vendors and payment terms.
7. Upload restricted W-9 and invoice evidence where appropriate.
8. Create the active compensation policy in **Operating Model**.

Stonegate records bookkeeping and payment evidence. It does not log into the bank or move money.

### Monthly Routine

1. Record or generate source-linked revenue, costs, commissions, and bills.
2. Review accounting drafts.
3. Approve and post balanced journals.
4. Import the bank CSV.
5. Match cleared transactions to posted journals.
6. Resolve or explain unmatched lines.
7. Prepare and approve the bank reconciliation.
8. Run financial statements.
9. Close and lock the period only after review.
10. Export the CPA package when needed.

The Tax Copilot suggests classifications and missing evidence. The Finance/CPA reviewer remains
responsible for tax treatment and filing.

## Backups And Recovery

The database contains the company operating record. A backup is useful only if it can be restored.

At minimum:

1. Confirm Render's database backup/retention option.
2. Create an owner-controlled backup outside the production database.
3. Restore it into a separate test database.
4. Confirm migrations and basic record counts.
5. Never run restore verification against production.
6. Record the date and result.

The exact commands are in [SETUP_REFERENCE.md](./SETUP_REFERENCE.md). A developer or experienced
administrator should run restoration because a wrong database URL can be destructive.

## Monitoring And Health

Use:

- `/health` to confirm the API process responds.
- `/ready` to confirm dependencies and required worker readiness.
- Render deployment and service logs for errors.
- Stonegate provider status and operational-failure records for workflow failures.

Sentry and a separate alert webhook are useful but currently optional. They do not block seller,
email, underwriting, transaction, or accounting workflows.

## Safe Change Procedure

For any provider or production setting:

1. State the exact feature being changed.
2. Record the current non-secret setting.
3. Change one provider or configuration area at a time.
4. Redeploy.
5. Run the narrow acceptance test.
6. Check UI status and API logs.
7. Restore the previous setting if the test fails.
8. Update canonical documentation when behavior or status changes.

Do not change several unrelated URLs, credentials, webhooks, and provider modes at once. That
makes failures difficult to identify.

## Launch Readiness Checklist

### Required For Initial Operations

- [ ] Public website and cash-offer form work on `stonegatehb.com`.
- [ ] Search Console domain verification and sitemap submission are complete.
- [ ] One accurate service-area Google Business Profile is verified or in review.
- [ ] Approved active team photographs and biographies pass the PC8 public-site audit.
- [ ] Owner and staff can sign in with individual accounts.
- [ ] Each role sees only the correct workspaces.
- [ ] OpenAI Copilots and Help work in advisory mode.
- [ ] RentCast and underwriting reports pass controlled tests.
- [ ] Resend sending, reply routing, attachments, and restricted aliases pass.
- [ ] Twilio calls record under the approved disclosure and retention policy; transcript, AI-note
      review/apply, failure visibility, and deletion pass end to end.
- [ ] SignWell remote and iPad signing pass before using e-signature with a seller.
- [ ] Compensation policy and role credits match current Stonegate policy.
- [ ] Finance opening setup and first bank-reconciliation process are reviewed.
- [ ] A database backup has been restored into a separate test database.

### Activate When Ready

- [ ] Twilio SMS after A2P approval.
- [ ] Twilio Voice after browser and inbound routing tests.
- [ ] RealEstateAPI key and controlled property-research acceptance.
- [ ] Google/Meta conversion delivery after ad-account setup.
- [ ] S3-compatible private storage as document volume grows.
- [ ] Sentry and separate worker alerts when the owner wants external monitoring.

## Where To Get More Help

- [UI_CONTROL_REFERENCE.md](./UI_CONTROL_REFERENCE.md): what a button or field does.
- [USER_MANUAL.md](./USER_MANUAL.md): how to complete an operating workflow.
- [STAFF_ROLE_MANUALS.md](./STAFF_ROLE_MANUALS.md): what each job owns.
- [SYSTEM_MAP.md](./SYSTEM_MAP.md): how the software is structured.
- [FINISHING_ROADMAP.md](./FINISHING_ROADMAP.md): what still needs external acceptance.
- [SECURITY_COMPLIANCE.md](./SECURITY_COMPLIANCE.md): access and communications rules.
