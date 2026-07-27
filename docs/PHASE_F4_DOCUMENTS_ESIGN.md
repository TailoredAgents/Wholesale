# Phase F4: Documents, Contracts, And Closing

Last updated: July 24, 2026

## Result

F4 extends the existing Transactions, Field Operations, and Dispositions workflows. It does not
create a second contract or file system.

Implemented:

- One private storage adapter for transaction documents, legal templates, signed agreements,
  inspection photographs, and buyer proof-of-funds documents.
- Database storage remains the zero-configuration fallback. Cloudflare R2 is the selected
  production object store through its S3-compatible API.
- File-type and PDF-header validation, SHA-256 checksums, configurable ClamAV scanning, retention
  dates, authenticated downloads, short-lived R2 download links, and controlled deletion.
- Versioned contract packages still require existing Stonegate approval before sending.
- SignWell is the selected e-signature adapter. Stonegate retains envelope, recipient, provider
  event, status, completed-document, and test-mode evidence.
- Signed webhook events are deduplicated. A completed provider PDF is retrieved and stored
  privately before Stonegate marks the package executed.
- Provider reconciliation can recover a missed webhook.
- Completed contracts advance the existing transaction, lead, and deal; they do not bypass the
  existing checklist or funding gates.
- The Transaction workspace shows storage readiness, e-signature readiness, internally generated
  packages, signature requests, recipient status, reconciliation, and document scan state.

Call recordings remain in Twilio and are accessed through Stonegate's authenticated recording
endpoint. Valuation PDFs are generated on demand and are not persistent uploads. Both retain their
existing permission boundaries.

## Provider Decisions

Cloudflare R2 was selected because it provides a private S3-compatible API, presigned downloads,
and no egress charge. SignWell was selected for its direct document API, webhooks, completed-PDF retrieval,
test mode, and low-volume API pricing.

- [Cloudflare R2 S3 and presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/)
- [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/)
- [SignWell API](https://www.signwell.com/api/)
- [SignWell API pricing](https://www.signwell.com/api-pricing/)
- [SignWell create document API](https://developers.signwell.com/reference/createdocument)
- [SignWell webhook events](https://developers.signwell.com/reference/events)
- [SignWell event hash verification](https://developers.signwell.com/reference/event-hash-verification)

## Production Setup

Keep these values server-side on `oakwell-api`.

### Cloudflare R2

1. Create one private R2 bucket for Stonegate production documents.
2. Create an R2 API token limited to that bucket.
3. Set:

```text
DOCUMENT_STORAGE_PROVIDER=s3
DOCUMENT_STORAGE_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
DOCUMENT_STORAGE_BUCKET=<private-bucket-name>
DOCUMENT_STORAGE_ACCESS_KEY_ID=<r2-access-key>
DOCUMENT_STORAGE_SECRET_ACCESS_KEY=<r2-secret-key>
DOCUMENT_STORAGE_REGION=auto
DOCUMENT_STORAGE_DOWNLOAD_TTL_SECONDS=300
DOCUMENT_RETENTION_DAYS=2555
```

Existing database-backed files remain readable. New uploads use R2 after the provider is changed.
Changing the setting does not silently move old bytes. After R2 acceptance, inspect and run the
idempotent copy command:

```bash
npm run documents:migrate
npm run documents:migrate -- --apply
```

The first command only counts eligible database files. The second copies each object, updates its
Stonegate storage reference, and clears the copied database bytes.

### Malware Scanning

The scanner adapter is implemented but optional. Database and R2 storage both report
`not_configured` until a private ClamAV service is available.

```text
DOCUMENT_MALWARE_SCANNER=clamav
DOCUMENT_MALWARE_SCAN_REQUIRED=true
CLAMAV_HOST=<private-clamav-host>
CLAMAV_PORT=3310
CLAMAV_TIMEOUT_SECONDS=15
```

Do not set scanning to required until the scanner is reachable from the API service.

### SignWell

1. Create the SignWell API account and API key.
2. Set:

```text
ESIGN_PROVIDER=signwell
ESIGN_API_KEY=<signwell-api-key>
ESIGN_BASE_URL=https://www.signwell.com/api/v1
ESIGN_WEBHOOK_CALLBACK_URL=https://oakwell-api.onrender.com/api/v1/webhooks/esign/signwell
ESIGN_TEST_MODE=true
ESIGN_REQUEST_TIMEOUT_SECONDS=30
```

3. Deploy, then select **Connect SignWell** in **Transactions > Contract**. Stonegate verifies the
   account, registers or reuses the callback URL, and retains the webhook ID used for SignWell's
   documented HMAC-SHA256 event verification. `ESIGN_SIGNWELL_WEBHOOK_ID` remains available only
   as a legacy environment fallback.
4. Run the acceptance case in test mode with company-controlled email addresses.
5. Set `ESIGN_TEST_MODE=false` only after the internal source, populated values, recipient order,
   signature placement, final PDF, webhook, and reconciliation results have been approved.

`ESIGN_PROVIDER=simulate` is limited to local and automated testing and is rejected in production.
The complete owner procedure is in `SIGNWELL_LAUNCH_RUNBOOK.md`; the legal-template specification
is in `SIGNWELL_COUNSEL_BRIEF.md`.

## Acceptance Case

1. Confirm the Stonegate agreement source and expected signer roles.
2. Create a contract package from an approved underwriting and offer decision.
3. Submit and approve the exact package version.
4. Send it to controlled seller and company test addresses.
5. Confirm sent, viewed, and signed recipient states.
6. Confirm webhook replay does not create duplicate events or files.
7. Use **Refresh status** to prove provider reconciliation.
8. Download the final signed PDF and compare it with the provider copy.
9. Complete required closing checklist evidence and funding confirmation.
10. Confirm funding remains blocked until every existing funding gate passes.

## Completion Boundary

The F4 application implementation is complete. Production acceptance remains open until:

- R2 is configured and a file is uploaded, downloaded, and deleted successfully.
- The Georgia purchase and assignment PDFs pass controlled generation and signing tests.
- SignWell completes the controlled test above and the final provider PDF is retained.
- A redacted contract-to-funding simulation passes the existing closing and funding gates.
