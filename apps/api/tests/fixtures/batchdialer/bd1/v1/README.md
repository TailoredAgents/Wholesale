# BatchDialer BD1 Evidence Fixtures

This directory contains sanitized evidence used to prove the official BatchDialer API contract.
It must never contain real seller data, production credentials, raw HTTP cassettes, or screenshots.

## Files

- `manifest.json`: required evidence scenarios and capture status.
- `field_matrix.json`: desired BatchDialer capabilities and current evidence state.
- `captured/20260822T164713Z-83ec9c25/`: reviewed, sanitized response bodies from the initial
  controlled read-only capture.

## Capture Rules

1. Obtain explicit owner permission before accessing an API credential.
2. Use a controlled campaign containing fictional records only.
3. Sanitize in memory before writing any file.
4. Preserve documented JSON keys, nesting, value types, nullability, ordering, and relationships.
   Quarantine undocumented property names and values; retain only a one-way 12-character
   fingerprint as schema-drift evidence.
5. Replace related provider IDs consistently across fixtures.
6. Use only `example.com` email addresses.
7. Use only North American fictional numbers in the reserved `202-555-0100` through
   `202-555-0199` range.
8. Use obviously fictional names and street addresses.
9. Retain only allowlisted response headers from the manifest contract test.
10. Remove authorization headers, cookies, tokens, keys, secrets, signed URLs, and raw account IDs.
11. Add a SHA-256 hash of each sanitized file to `manifest.json`.
12. Label simulated failures `synthetic_resilience`; never present them as provider observations.

## Evidence Status

Use `not_captured` until a fixture is safely available. Use `captured` only for a sanitized,
controlled-account observation. Use `synthetic` only for deliberately generated resilience input.

An undocumented field stays ambiguous even when observed. Do not use fixture discovery as
permission to call an undocumented endpoint in production.

The August 22 capture is partial evidence, not BD1 acceptance. The manifest registers all seven
reviewed observations and one first-page cursor scenario. It intentionally leaves BD2 blocked
until the remaining controlled outcomes, stable disposition identity, cursor termination,
incremental boundary, and rate/retry contract are proven.
