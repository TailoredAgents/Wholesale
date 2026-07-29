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
   RentCast, and DealMachine.
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
9. Activate DealMachine when the first contracted deal is close.
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
| `RESEND_API_KEY` | Resend API Keys |
| `TWILIO_ACCOUNT_SID` | Twilio Account Info |
| `TWILIO_AUTH_TOKEN` | Twilio Account Info; it is not the Account SID |
| `ESIGN_API_KEY` | SignWell API settings |
| `DEALMACHINE_API_KEY` | DealMachine API access |

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

### Do Not Activate Before Approval

Stonegate SMS should use its own A2P campaign, Messaging Service, and phone number. Do not attach
another company's number or campaign.

### After A2P Approval

1. Open Twilio Messaging Services.
2. Open Stonegate's approved Messaging Service.
3. Attach the approved Stonegate 10DLC number.
4. Set incoming messages to:
   `POST https://api.stonegatehb.com/api/v1/webhooks/twilio/messaging/incoming`
5. Set the delivery callback to:
   `POST https://api.stonegatehb.com/api/v1/webhooks/twilio/messaging/status`
6. Copy the Account SID.
7. Reveal and copy the separate Auth Token.
8. Copy the Messaging Service SID.
9. Copy the Stonegate number in `+1...` format.

### In Render

Enter the Twilio values on **oakwell-api**, keep webhook validation enabled, set the branded API
base URL, and set `TWILIO_SMS_ENABLED=true` only after the approved number is attached.

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

Twilio Voice needs more than a webhook because browser calling requires a short-lived device token.
The Account SID and Auth Token identify and validate the account. The API Key SID and secret mint
the browser token. The TwiML App tells Twilio where to request call instructions.

### Setup Order

1. Choose the Stonegate-owned voice number.
2. Create a Twilio API key and securely record its SID and secret.
3. Create a TwiML App for Stonegate browser calling.
4. Configure inbound and outbound Voice webhooks from [SETUP_REFERENCE.md](./SETUP_REFERENCE.md).
5. Enter Voice variables on **oakwell-api**.
6. Keep recording disabled until disclosure and retention rules are approved.
7. Enable Voice and redeploy.

### Acceptance

1. Confirm the browser phone registers.
2. Place an outbound call to a controlled phone.
3. Confirm the Stonegate number appears.
4. Call Stonegate back and confirm intended staff routing.
5. Test no answer, missed call, voicemail, and call outcome.
6. Confirm the call appears on the correct conversation.
7. Enable recording later and test disclosure, access, transcription, AI notes, and deletion.

## DealMachine Buyer Data

Do not purchase DealMachine solely to finish a settings screen. Activate it when Stonegate is near
its first contracted deal and has time to test buyer quality before marketing that deal.

When ready:

1. Buy the package that includes the required API access.
2. Create a DealMachine API key.
3. Add it to `DEALMACHINE_API_KEY`.
4. Set `BUYER_DATA_PROVIDER=dealmachine`.
5. Redeploy.
6. Open the test disposition case.
7. Select **Find buyers with DealMachine**.
8. Review candidates before importing them.
9. Check duplicates, contact quality, market fit, and provider cost.

Stonegate's Disposition Copilot ranks reviewed internal and provider candidates. It should not
silently import or contact every result.

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
- [ ] Owner and staff can sign in with individual accounts.
- [ ] Each role sees only the correct workspaces.
- [ ] OpenAI Copilots and Help work in advisory mode.
- [ ] RentCast and underwriting reports pass controlled tests.
- [ ] Resend sending, reply routing, attachments, and restricted aliases pass.
- [ ] SignWell remote and iPad signing pass before using e-signature with a seller.
- [ ] Compensation policy and role credits match current Stonegate policy.
- [ ] Finance opening setup and first bank-reconciliation process are reviewed.
- [ ] A database backup has been restored into a separate test database.

### Activate When Ready

- [ ] Twilio SMS after A2P approval.
- [ ] Twilio Voice after browser and inbound routing tests.
- [ ] Recording after disclosure and retention approval.
- [ ] DealMachine near the first contracted deal.
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
