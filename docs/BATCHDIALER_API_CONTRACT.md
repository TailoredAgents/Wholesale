# BatchDialer BD1 API Contract Evidence

Last updated: August 22, 2026

Status: initial bounded controlled capture completed and reviewed; the owner approved a
constrained direct-only version-one implementation while additional live scenarios remain deferred

## Purpose

This document is the evidence gate for Stonegate's direct BatchDialer integration. It prevents the
application from being built around guessed endpoints, undocumented response fields, or a single
example from the BatchDialer UI.

This evidence record does not claim that every provider behavior is proven. It defines the exact
official and controlled evidence Stonegate may use, the unresolved behaviors it must not guess,
and the conservative compatibility rules that make a bounded direct implementation safe.

## What The Official Public Sources Prove

As of August 21, 2026, BatchDialer's official Version 1 documentation establishes the following:

- Base URL: `https://app.batchdialer.com/api`.
- Authentication uses the raw API token in `X-ApiKey`, without a `Bearer` prefix.
- API keys are exposed through **Settings -> Integrations -> Custom Integration**.
- Campaigns can be listed and searched with status, search, paging, and sorting controls.
- Contacts can be listed and retrieved; bulk retrieval documents paging and date filters.
- CDR data includes call identity, direction, dates, phone, disposition label, duration, agent,
  contact, campaign, comments, and recording metadata.
- Cursor-paginated CDR retrieval and a stateful `GET /v2/cdrs/last` operation are documented.
- Contact call history exposes notes and attachments.
- JSON and HTML transcript retrieval by numeric CDR ID are documented.

This proves that a direct integration is technically viable for campaign discovery and completed
call ingestion. It does not yet prove that every documented response matches Stonegate's account or
that the stateful watermark is safe to consume without coordination.

Official sources:

- [BatchDialer developer portal](https://developer.batchdialer.com/)
- [BatchDialer API getting started](https://developer.batchdialer.com/docs/batchdialer/f4e6fa31af431-getting-started)
- [Campaign search](https://developer.batchdialer.com/docs/batchdialer/rw0nq2fp5bu7a-search)
- [Contact retrieval](https://developer.batchdialer.com/docs/batchdialer/u4lhivm8hts8x-get-contacts)
- [Cursor-paginated CDRs](https://developer.batchdialer.com/docs/batchdialer/kjto0ggvaavor-get-recent-contacts-v2)
- [Latest CDRs since last poll](https://developer.batchdialer.com/docs/batchdialer/l30xoc2l3ziml-get-latest-cd-rs-since-last-poll)
- [Call history by vendor contact](https://developer.batchdialer.com/docs/batchdialer/j8znbe36cqcm6-get-recent-calls-by-vendor-contact-id)
- [JSON transcript retrieval](https://developer.batchdialer.com/docs/batchdialer/1ipr1j1l9zkyn-get-transcription-json)
- [BatchDialer pricing and API availability](https://batchdialer.com/pricing)
- [BatchDialer API-key integration example](https://help.getbatch.co/en/articles/9792924-how-to-sync-batchleads-and-batchdialer-and-push-lists)

## What The Controlled Capture Proved

On August 22, 2026, the owner supplied a dedicated local-only API key and the bounded read-only
capture completed against the fixed official API host. Seven sanitized observations were reviewed
and registered in the evidence manifest. No raw credential, configured provider ID, real email,
real phone number, address, person name, or recording URL was retained.

The account observation confirms:

- active-campaign retrieval and two bounded campaign-search requests succeed;
- a controlled contact can be retrieved by its stable provider contact ID;
- the contact exposes name, phone, email, timestamps, and explicit blank optional fields;
- the selected CDR preserves stable call, contact, campaign, and agent relationships;
- the controlled qualification label is returned with its exact punctuation;
- a cursor can be passed from the first CDR page to a second request; and
- a four-segment JSON transcript can be retrieved for the selected numeric CDR ID.

Production reconciliation on August 22, 2026 also showed that the account's completed-call date
queries return records under `America/Chicago`; the same bounded date returned no records under
`America/New_York` or `UTC`. Stonegate therefore configures the BatchDialer account timezone as
`America/Chicago` while leaving other company timezone settings unchanged.

These are partial observations, not permission to enable production polling. The manifest marks
only the first-page cursor scenario captured and leaves `ready_for_bd2` false.

## What Remains Unproven

The following details remain ambiguous or unsupported until BatchDialer support clarifies them and
a sanitized observation is captured from Stonegate's controlled test campaign:

- token scope, account/workspace binding, and credential-specific permissions;
- a stable call-result/disposition ID; the documented CDR contract exposes labels only;
- custom result renaming behavior and the exact raw labels returned by the account;
- lead-sheet answers, callbacks, and a standalone agent directory;
- calendar-event behavior, which is intentionally outside Stonegate's integration because every
  appointment is entered manually in Stonegate;
- deterministic ordering and tie-breaking across every retrieval operation;
- rate-limit headers, approved polling frequency, `Retry-After`, request IDs, and retry guidance;
- the scope and advancement rules of the stateful `/v2/cdrs/last` watermark;
- whether separate API keys receive separate latest-CDR watermarks;
- recording URL authentication, expiration, and download behavior;
- transcript readiness, delay, retention, and incomplete-transcript behavior; and
- inconsistent documented examples for direction, disposition, comments, and attachments;
- `externalid` appearing in campaign-search responses despite being documented there only as a
  request filter; it is an exact reviewed compatibility exception because the active-campaign
  response formally documents the same field;
- two additional undocumented campaign-search properties, fourteen undocumented contact
  properties, and one undocumented transcript property observed and quarantined by fingerprint;
- an empty second CDR page that still returned another cursor, leaving termination behavior
  unproven; and
- call-history notes and attachments for this controlled contact, because BatchDialer returned a
  blank vendor-contact ID and the bounded tool correctly skipped that optional endpoint.

Stonegate must preserve raw provider values and use exact reviewed disposition labels. It must not
encode assumptions for any unresolved item. A missing, renamed, or unknown label is quarantined and
never silently creates a Lead.

## Availability And Evidence Rules

The machine-readable field matrix is stored at
`apps/api/tests/fixtures/batchdialer/bd1/v1/field_matrix.json`.

It uses three availability values:

- `supported`: a current official source explicitly supports the stated capability;
- `unsupported`: current official evidence explicitly says the capability is unavailable; and
- `ambiguous`: the public contract is silent, incomplete, or too broad for production use.

An observed but undocumented field remains `ambiguous`. Critical fields may be marked ready only
when both official support and a controlled-account observation exist. Synthetic resilience data
can test Stonegate's behavior, but it is never proof of BatchDialer's behavior.

Allowed provenance classes are:

- `official_documentation`;
- `controlled_account_observation`; and
- `synthetic_resilience`.

## Evidence Package

The evidence package lives under `apps/api/tests/fixtures/batchdialer/bd1/v1/`:

- `manifest.json` records every required scenario and its capture status;
- `field_matrix.json` maps desired provider evidence to Stonegate's use;
- `README.md` defines the capture and sanitization procedure; and
- `apps/api/scripts/capture_batchdialer_bd1.py` performs only the fixed, documented, read-only
  proof sequence and writes sanitized observations for review; and
- captured JSON responses will be stored in scenario subdirectories only after sanitization.

The test suite rejects incomplete manifests, missing fixture hashes, unsafe provenance, sensitive
headers, credentials, non-example email addresses, and non-fictional phone numbers.

## Controlled Capture Runbook

The owner authorized controlled credential use on August 21, 2026. This workspace has no existing
BatchDialer API key, Render CLI session, Render connector, or connected signed-in browser, so the
tool cannot obtain the key automatically. The key must be entered locally once without placing it
in chat, source control, a screenshot, or a command-line argument.

Local capture procedure:

1. In BatchDialer, open **Settings -> Integrations -> Custom Integration** and create or copy the
   dedicated Stonegate direct-integration key. This is the only BatchDialer-to-Stonegate transport
   credential.
2. Open `%USERPROFILE%\.stonegate\batchdialer_bd1.env` and paste the key only after
   `BATCHDIALER_BD1_API_KEY=`. This fixed local file is outside the OneDrive repository. The
   controlled campaign, contact, and date are already staged there.
3. From `apps/api`, run `uv run python -m scripts.capture_batchdialer_bd1 --execute`.
4. The tool uses a fixed official host, requires confirmation that the target is controlled,
   refuses arbitrary paths, forbids `/v2/cdrs/last`, follows no redirects, performs no retries,
   caps requests and response bytes, and never accepts the key on the command line.
5. It retrieves active campaigns, two one-record campaign-search pages, the controlled contact,
   at most two small CDR pages for the controlled date, and supported call history and transcript
   data. Authentication, rate-limit, and temporary-failure resilience use synthetic fixtures; the
   evidence tool does not deliberately send a bad key to the live provider.
6. Raw responses exist only in memory. The tool writes new sanitized JSON trees under
   `apps/api/tests/fixtures/batchdialer/bd1/v1/captured/` and prints only operation, HTTP status,
   sanitized hash, and fixture path.
7. Every output remains `pending_review`; the tool cannot mark BD1 ready or alter the manifest.
8. The initial August 22 run has been reviewed, hashed, and registered. The owner deferred the
   remaining live rename/update/result scenarios. Synthetic resilience fixtures and future
   sanitized observations may strengthen the evidence package, but they do not change the
   constrained production rules automatically.

Never paste the API key into chat, screenshots, fixtures, logs, documentation, or Git. Never rotate,
delete, or change it as part of this phase.

## Deferred Evidence Scenarios

The manifest continues to track evidence for:

1. Qualified Seller - Follow Up;
2. Appointment Set;
3. Callback;
4. No Answer or Voicemail;
5. an unknown result;
6. a result before and after renaming;
7. at least two pages of results;
8. one provider record before and after an update;
9. an incomplete provider record;
10. a 401 or 403 authentication failure;
11. a 429 rate-limit response with relevant headers; and
12. a temporary 5xx failure.

The failure scenarios may be deliberately simulated for resilience tests, but they must be labeled
`synthetic_resilience` and cannot prove provider error or retry behavior. These incomplete scenarios
remain visible evidence gaps; they are not permission to broaden version-one behavior.

## Constrained Version-One Contract Gate

The owner-authorized direct implementation may proceed only while all of these constraints remain
enforced:

- use only `GET /campaigns`, bounded date-partitioned `GET /v2/cdrs`, eligible
  `GET /contact/{contactID}`, and optional history/transcript operations documented above;
- never use the stateful `/v2/cdrs/last` endpoint;
- begin each bounded date scan at page one and rely on durable raw and semantic idempotency for the
  overlap;
- stop a bounded scan on an empty item list even when another cursor is returned, and record that
  provider anomaly;
- fail a scan visibly on a repeated cursor or maximum-page boundary;
- match only the exact reviewed **Qualified Seller - Follow Up** and **Appointment Set** labels;
- quarantine every unknown, renamed, incomplete, or conflicting result instead of guessing;
- treat those labels as candidates rather than proof: transcript evidence must show a live two-way
  conversation and explicit seller interest, and **Appointment Set** must also show explicit
  appointment agreement;
- retry a delayed transcript within a bounded window, then create a visible Tasks approval review
  for unavailable, contradictory, or inconclusive evidence without creating a Lead;
- allow approval only for explicitly enumerated uncertainty reasons, require a written decision
  reason, bind it to the exact evidence fingerprint, and fail closed for hard conflicts or any new
  unrecognized reason code;
- preserve an evidence-accepted handoff even when property or permission facts are incomplete or
  the property is outside the current market, without manufacturing consent or running research
  against a placeholder property;
- run Lead creation, staff alerts, property research, attribution, and seller call-timeline work
  only after evidence acceptance; and
- never poll provider calendar data or create an Appointment automatically.

The historical manifest remains `ready_for_bd2=false` because it records provider-proof
completeness, not the owner's constrained implementation decision. Do not rewrite that evidence
flag merely to make the roadmap look complete.

## Current Decision

The sanitized account capture confirms that the official API can retrieve the core campaign,
contact, CDR, relationship, and transcript shapes, while also exposing material contract gaps. The
owner chose to proceed with a conservative direct-only implementation instead of waiting for every
live scenario.

The official API is the sole BatchDialer integration. Stonegate uses bounded overlapping date scans,
exact result labels, durable evidence, idempotent business actions, and visible quarantine for every
unproven variation. Candidate qualifying dispositions pass a transcript-backed evidence gate before
they can create a Lead; delayed or unclear evidence retries and then routes to visible Tasks approval
review. Consent remains unknown unless separately proven, and out-of-market property is not a
rejection rule. It does not consume the stateful latest-CDR watermark, provider calendar data, or
undocumented private operations. Appointments remain manual in Stonegate. Production credential
entry and controlled acceptance remain explicit owner actions; this document never authorizes code
to inspect, reveal, rotate, or replace a credential.
