# SignWell Launch Runbook

## Current State

Stonegate's SignWell integration is implemented for:

- Owner-controlled account verification.
- Automatic webhook registration or reuse.
- HMAC-SHA256 event verification.
- Duplicate-event handling.
- Purchase, assignment, addendum, and generic executed-document classification.
- Up to four ordered signers.
- Reconciliation when a provider event is delayed.
- Completed PDF and SignWell audit-page retrieval.
- Private transaction-document retention and download.
- Test mode before binding use.

The production launch dependency that software cannot create is attorney-approved contract
language. Stonegate's original Georgia version 1 contracts and their operating instructions are in
`docs/GEORGIA_CONTRACT_PACKET.md`; they remain visibly marked as unreviewed until replaced through
the versioning process in that guide.

## Finish SignWell Account Onboarding Now

On SignWell's **Upload A Template** screen:

1. Upload `docs/templates/stonegate-signwell-technical-test.docx`.
2. Name it `Stonegate - NON-BINDING Technical Test`.
3. Add one placeholder named exactly `Seller`.
4. Place one signature field and one signed-date field for `Seller`.
5. Finish the template.

This template completes provider onboarding and can be used only for non-binding test-mode checks.
It must not be represented as a purchase or assignment agreement.

Then open **Settings > API** in SignWell and create an API key.

## Render Configuration

Set these values on the `oakwell-api` service:

```text
ESIGN_PROVIDER=signwell
ESIGN_API_KEY=<SignWell API key>
ESIGN_BASE_URL=https://www.signwell.com/api/v1
ESIGN_WEBHOOK_CALLBACK_URL=https://oakwell-api.onrender.com/api/v1/webhooks/esign/signwell
ESIGN_TEST_MODE=true
ESIGN_REQUEST_TIMEOUT_SECONDS=30
```

`ESIGN_SIGNWELL_WEBHOOK_ID` may remain blank. Stonegate now registers or reuses the webhook and
retains its verification ID after the owner connects the account.

Deploy the API after saving the variables.

## Connect From Stonegate

1. Open **OS > Transactions**.
2. Open a transaction and select **Contract**.
3. In **SignWell**, select **Connect SignWell**.
4. Confirm Account and Webhook show `Connected`.

The same action becomes **Verify connection** after setup and can be used after provider changes.

## Install Production Templates

For each attorney-approved document:

1. Upload the final file to SignWell and create the signer placeholders from
   `SIGNWELL_COUNSEL_BRIEF.md`.
2. Add only the applicable fields and use the exact API IDs in the counsel brief.
3. Finish the SignWell template and copy its template ID from its SignWell URL.
4. In **OS > Transactions > Contract > Legal template**, upload the same approved file.
5. Select the correct document type and `GA`, then add it as a draft.
6. Approve the Stonegate template only after confirming it is the attorney-approved final.
7. Under **Connect template**, select it and enter the SignWell template ID. Stonegate applies the
   standard field IDs automatically; use override inputs only if counsel's template differs.
8. Select **Verify connection** and confirm the template count shows ready.

## Controlled Acceptance

Keep `ESIGN_TEST_MODE=true` and use controlled email addresses.

1. Create a contract package from the approved purchase template.
2. Request and approve the exact package version.
3. Send it to the test signer with placeholder `Seller`.
4. Open and sign it.
5. Confirm Stonegate shows sent, viewed/in progress, and completed.
6. Confirm the completed PDF downloads from transaction Documents and contains SignWell's audit
   page.
7. Repeat with the assignment template using `Assignee` and `Stonegate` placeholders.
8. Send one additional test and use **Reconcile** to confirm recovery works.
9. Confirm a repeated provider event does not create a duplicate file or timeline event.

After counsel approval and both controlled tests pass, set:

```text
ESIGN_TEST_MODE=false
```

Deploy once more. Production signature requests are then binding provider documents rather than
SignWell test documents.

## Operating Rule

Never edit a production legal template in place. Create a new version in SignWell and Stonegate,
test it, approve it, and retire the prior version from future use. Existing signed packets and their
audit history remain attached to the transaction.
