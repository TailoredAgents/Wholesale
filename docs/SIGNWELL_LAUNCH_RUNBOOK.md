# SignWell Launch Runbook

## Current State

Stonegate's SignWell integration is implemented for:

- Owner-controlled account verification.
- Automatic webhook registration or reuse.
- HMAC-SHA256 event verification.
- Duplicate-event handling.
- Internal Stonegate generation of purchase, assignment, and addendum PDFs.
- Automatic signature and signed-date placement using SignWell text tags.
- Purchase, assignment, addendum, and generic executed-document classification.
- Ordered seller, end-buyer, and company signers.
- Reconciliation when a provider event is delayed.
- Completed PDF and SignWell audit-page retrieval.
- Private transaction-document retention and download.
- Test mode before binding use.

Stonegate's original Georgia version 1 contracts and their operating instructions are in
`docs/GEORGIA_CONTRACT_PACKET.md`. Later legal revisions should be installed through the versioning
process in that guide.

## Finish SignWell Account Onboarding

Open **Settings > API** in SignWell and create an API key. Stonegate uses SignWell's direct document
API, so no SignWell template, placeholder, field-ID mapping, or provider template maintenance is
required.

## Render Configuration

Set these values on the `oakwell-api` service:

```text
ESIGN_PROVIDER=signwell
ESIGN_API_KEY=<SignWell API key>
ESIGN_BASE_URL=https://www.signwell.com/api/v1
ESIGN_WEBHOOK_CALLBACK_URL=https://api.stonegatehb.com/api/v1/webhooks/esign/signwell
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

## Document Source

Stonegate owns the production document source in `docs/templates/ga-contracts/`. The transaction
workspace selects Purchase Agreement, Assignment Agreement, or Contract Addendum and creates the
completed PDF from the approved package data. SignWell receives that PDF plus programmatic signature
fields and returns the completed PDF and audit page.

When document language changes, update the matching Stonegate source as a reviewed software change,
run the contract-generation tests, inspect all affected PDFs, and deploy a new application version.
Do not recreate the agreement in SignWell.

## Controlled Acceptance

Keep `ESIGN_TEST_MODE=true` and use controlled email addresses.

1. Create a purchase-agreement package in Stonegate.
2. Select **Preview PDF** and inspect every populated term and signature line.
3. Request and approve the exact package version.
4. Send it to a controlled seller address. Stonegate adds the company signer automatically.
5. Open and sign it.
6. Confirm Stonegate shows sent, viewed/in progress, and completed.
7. Confirm the completed PDF downloads from transaction Documents and contains SignWell's audit
   page.
8. Repeat with an assignment package and a controlled assignee address.
9. Send one additional test and use **Reconcile** to confirm recovery works.
10. Confirm a repeated provider event does not create a duplicate file or timeline event.

After counsel approval and both controlled tests pass, set:

```text
ESIGN_TEST_MODE=false
```

Deploy once more. Production signature requests are then binding provider documents rather than
SignWell test documents.

## Operating Rule

Never change production agreement language without version review and PDF acceptance testing.
Existing packages, signing copies, completed PDFs, and audit history remain attached to their
transactions.
