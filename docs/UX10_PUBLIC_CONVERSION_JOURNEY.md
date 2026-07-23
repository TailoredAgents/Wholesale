# UX10 Public Conversion Journey, Performance, And Measurement

Last updated: July 22, 2026

Status: Implementation complete. Production traffic baselines remain.

## Purpose

UX10 turns the address-first entry created in UX9 into a complete seller request that is easy to
finish, truthful about what is optional, resilient to network failure, compliant with separate SMS
consent, and measurable without placing seller-provided values in analytics metadata.

## Research Decisions

- Break the request into logical, named steps with visible progress and back navigation. W3C's
  [multi-page form guidance](https://www.w3.org/WAI/tutorials/forms/multi-page/) recommends smaller
  logical groups, clear progress, and preserving entered data.
- Keep SMS consent separate, optional, unambiguous, and unchecked. Stonegate records the approved
  wording version with the request and follows
  [Twilio's messaging policy](https://www.twilio.com/en-us/legal/messaging-policy) and
  [A2P consent guidance](https://www.twilio.com/docs/api/errors/30830).
- Evaluate real-user performance at the 75th percentile using LCP, INP, and CLS. The current good
  thresholds are LCP at or below 2.5 seconds, INP at or below 200 milliseconds, and CLS at or below
  0.1, as defined by [web.dev](https://web.dev/articles/defining-core-web-vitals-thresholds).
- Use page experience as one input to seller usability and search quality, not as a substitute for
  useful content or evidence. See
  [Google Search Central page experience guidance](https://developers.google.com/search/docs/appearance/page-experience).

## Seller Journey

1. **Property:** Street address, city, and ZIP are required. Property type is optional.
2. **Situation:** Condition, occupancy, reason, and timeline are optional.
3. **Details:** Asking price, mortgage balance, and free-form context are optional.
4. **Contact:** Name and a usable phone or email are required. The selected channel must have its
   corresponding value. Text preference requires the separate SMS checkbox.

The browser retains non-consent answers for 24 hours within the current tab. Contact and SMS
checkboxes are always restored as unchecked. Starting a new request from a public address form
clears the old draft and confirmation.

On a temporary API error, every answer remains visible and the seller can retry. On success, the
tab stores a confirmation reference for 24 hours; refreshing shows that confirmation without
posting another request. Public duplicate matching remains authoritative on the API.

## CRM Contract

The public intake now accepts property type, property condition, occupancy status, mortgage
balance, and an anonymous conversion session ID. New records receive the submitted context. A
duplicate request may fill a missing CRM value but cannot overwrite a value already reviewed or
entered by staff.

The successful backend `form_submit` event uses the same anonymous session ID as the browser funnel,
allowing aggregate start-to-submit analysis without sending seller answers in event metadata.

## Measurement Contract

Recorded funnel events:

| Event | Safe metadata |
| --- | --- |
| `offer_start` | Public entry point |
| `form_start` and `form_restore` | Form name and step number |
| `form_step_complete` and `form_step_back` | Step key and number |
| `form_validation_error` | Invalid field names, never field values |
| `form_submit_attempt`, `form_submit_error`, `form_submit` | Status category and anonymous session |
| `form_abandon` | Active step and completed-step count |
| `web_vital` | Metric, rounded value, rating, navigation type, and public route |

Attribution persists only for the current browser tab. Referrers are reduced to origin and path;
queries and fragments are discarded. Anonymous IDs are not stored in long-lived local storage.

The Marketing workspace reports page views, offer starts, form starts, each completed step,
validation errors, attempts, successful submissions, failures, abandonment, start-to-submit rate,
and LCP/INP/CLS sample count, p75 value, and good-rate.

## First Optimization Test

**Hypothesis:** Explicitly labeling situation and details as optional while showing four-step
progress will increase completed requests because sellers can continue without knowing repair,
mortgage, or price details.

**Primary metric:** Unique `form_submit` sessions divided by unique `form_start` sessions.

**Guardrails:** Validation-error sessions per form start, submit-error rate, duplicate-match rate,
qualified-lead rate, and appointment-set rate must not materially worsen.

**Minimum observation rule:** First collect the unchanged production baseline. Do not decide an
A/B result before each experience has at least 200 unique form starts and has run for two complete
business weeks. Compare source mix and downstream lead quality before adopting a winner. If traffic
is too low, continue collecting data rather than declaring a result from noise.

## Verification

- `npm run lint -- --max-warnings=0`: pass.
- `npx tsc --noEmit`: pass.
- `npm run build`: pass.
- `npm run audit:public`: desktop 1440x1000 and mobile 390x844 journeys pass.
- Automated journey covers validation, back navigation, answer preservation, separate SMS consent,
  failed-submit retry, payload integrity, durable confirmation, no duplicate repost, serious and
  critical axe findings, duplicate IDs, and horizontal overflow.
- `uv run ruff check app tests`: pass.
- `uv run pytest -q`: 114 tests pass.
- Mobile Lighthouse offer route: performance 98, accessibility 100, best practices 96, SEO 100,
  LCP 2.4 seconds, CLS 0, TBT 50 milliseconds.
- Mobile Lighthouse homepage: performance 93-95, accessibility 100, best practices 96, SEO 100,
  LCP 2.9-3.3 seconds, CLS 0, TBT 10-20 milliseconds.

The homepage lab LCP is still above the 2.5-second target in these throttled local runs. Image
priority and compression are improved, and field telemetry is enabled. UX10 must collect production
p75 data before another performance change is justified or the target is considered met.

## Production Checkpoint

1. Confirm `offer_start`, `form_start`, step, validation, submit, and Web Vitals events appear in
   Marketing after deployment.
2. Confirm successful website leads contain the optional structured context in the OS.
3. Confirm a failed request can retry and a success can refresh without reposting in production.
4. Collect at least 28 days of baseline traffic, segmented by source and device.
5. Review homepage field LCP before changing media, layout, or hosting configuration.
6. Launch only one documented optimization test at a time.
