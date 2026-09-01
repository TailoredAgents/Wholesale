# InvestorLift Provider Verification

Last reviewed: August 28, 2026

## Purpose

Stonegate remains the system of record for its buyers, deal evidence, approvals, offers, and
disposition history. InvestorLift may extend marketplace reach, but it must not become a hidden
dependency or receive private seller or Stonegate economics merely because a listing is prepared.

This document separates capabilities described in InvestorLift's public documentation from the
direct provider contract Stonegate still needs in writing. It is an operator verification record,
not proof that a live InvestorLift API connection exists.

## Current Stonegate Boundary

- The DS8 provider-neutral/manual workspace can prepare an approved, public-only listing bundle,
  record a manually created InvestorLift property link, stage manually observed inquiry or offer
  signals, show refresh and connection history, disconnect future use, and export Stonegate's
  provider history.
- Live InvestorLift transport remains disabled until InvestorLift supplies a written API contract
  and Stonegate verifies the subscribed account, authorization method, sandbox behavior, limits,
  costs, ownership terms, and event semantics.
- A manual provider signal is evidence for human review. It never creates or activates a canonical
  Buyer, chooses a buyer, accepts an offer, releases outreach, or changes a deal stage by itself.
- Disconnecting a provider stops future use but does not erase the approval, bundle checksum,
  external link, manual event, review, or audit history already stored in Stonegate.
- No provider secret is required for the manual DS8 foundation. Never put credentials in support
  tickets, screenshots, source control, exported files, or this document.

## Public Capability And Gap Matrix

| Capability | Public documentation establishes | Missing verification before direct transport |
| --- | --- | --- |
| CRM integration | InvestorLift documents a Zapier connection requiring an InvestorLift admin login, a CRM login, and a Zapier login. | Direct REST or GraphQL base URL, authentication, credential scope, token lifecycle, sandbox, and account isolation. |
| Zapier triggers | `New Buyer`, `New Offer`, `Offer Accepted`, `Update Lead`, `New Lead`, and `New Inquiry`. | Delivery guarantees, ordering, replay identifiers, retry policy, retention, and whether equivalent direct webhooks or polling endpoints exist. |
| Zapier actions | `Create Buyer` and `Post Lead`. | Direct create/update contracts for listings, buyers, images, documents, pricing, visibility, and status. |
| Offer fields | Public examples include customer ID, property ID, price, buyer company, assignment fee, user ID, property address, and property URL. | Canonical identifiers, currency/precision, revision behavior, accepted-offer semantics, withdrawal/retrade events, and direct event schemas. |
| Listing/lead fields | Public Zapier examples include address, name, email, asking price, square footage, phone, and an InvestorLift lead URL. | The minimum public listing payload; immutable versus mutable fields; photo/document constraints; privacy classification; validation; and error contract. |
| God Mode | Public help describes transaction history, buyer profiles, market analysis, property/financial data, buyer-list building, exports for paid non-Lite plans, and credit-priced skip tracing. | Whether any of that evidence is API-accessible; query contract; license and retention rules; cost telemetry; provenance; and permitted storage in Stonegate. |
| Artemis Mode | Public help describes property and image views, address requests, inquiries, email clicks, favorites, open-house registration, and offer activity. | Whether events are API-accessible; event IDs/timestamps; buyer unlock and identity rules; score meaning; deduplication; cost telemetry; and retention. |
| Buyer access | Public help describes linking or creating buyers and, by plan, unlocking buyers with credits. | Permanent-list ownership, rental or revocation rules, export completeness, contact-use rights, consent evidence, suppression behavior, and cancellation access. |
| Operations | Public help supplies workflow guidance and a support email. | Rate limits, concurrency limits, timeouts, pagination, backoff, service objectives, incident communication, support escalation, and change notices. |
| Data ownership | Public pages reviewed here do not establish Stonegate's complete data-return rights. | Full buyer/deal/history export, export format, deletion schedule, post-cancellation access, backups, subprocessors, and audit evidence. |

## Written Questions For InvestorLift Support

Send these questions to `support@investorlift.com` from an authorized Stonegate business address.
Ask for links or attachments that form part of the subscribed product contract. Do not include an
API key, password, token, webhook secret, or production payload.

> Stonegate Home Buyers is evaluating a direct, server-to-server InvestorLift integration while
> keeping Stonegate OS as our system of record. Please answer the following in writing and provide
> the current technical documentation for our subscription:
>
> 1. Does our subscription include a supported direct API? If so, what tier or additional fee is
>    required, and can you provide the production and sandbox base URLs plus the current API docs?
> 2. What authentication method and scopes are supported? How are credentials created, rotated,
>    revoked, restricted by account, and tested without production data?
> 3. Which endpoints can create and update a property/listing, photos, documents, pricing,
>    visibility, and listing status? Which fields are required, public, immutable, or size-limited?
> 4. Are inquiries, property views, image views, address requests, favorites, offers, accepted
>    offers, withdrawals, and status changes available by webhook or polling? Please provide exact
>    event schemas, stable event IDs, ordering, replay, retry, signature, and retention behavior.
> 5. Are God Mode transaction/buyer results and Artemis engagement signals available through the
>    supported API? If yes, what plans, credit charges, licenses, storage limits, and attribution
>    requirements apply?
> 6. What are the rules for importing, exporting, unlocking, renting, retaining, contacting, and
>    permanently owning buyer records? What happens to unlocked or linked buyers after downgrade or
>    cancellation?
> 7. What are the per-endpoint rate limits, pagination limits, concurrency limits, timeouts,
>    idempotency guarantees, retry guidance, request IDs, cost fields, service objectives, and
>    support-escalation path?
> 8. Can Stonegate export all of its listings, buyers, inquiries, offers, activity, notes, and source
>    identifiers in a documented machine-readable format? What is retained or deleted after
>    disconnection or cancellation, and on what schedule?
> 9. Can you provide a non-production account or sandbox and written permission for a bounded
>    acceptance test before live activation?
> 10. Who will notify Stonegate of breaking changes, deprecations, pricing changes, and incidents,
>     and how much notice is provided?

## Verification Evidence Required

An Owner or disposition manager should attach the following evidence to the integration decision;
do not paste credentials into the evidence:

1. The provider's written answers and versioned API documentation.
2. The subscribed plan and any API, Artemis, God Mode, buyer-unlock, storage, or usage fees.
3. The data-ownership, export, retention, deletion, and cancellation terms.
4. The permitted-use and contact rules for provider-discovered buyers.
5. Sandbox evidence for authentication failure, idempotent retry, pagination, rate limiting,
   malformed payloads, duplicate events, out-of-order events, disconnect, and full export.
6. A field-by-field privacy review proving the publish payload contains only approved public facts.
7. A go-live approval naming the tested provider contract version and accepted operational limits.

## Activation Gate

Live transport may be implemented and enabled only after the written evidence above is reviewed and
the provider-specific adapter passes bounded acceptance tests. Until then, use the guided manual
handoff: choose one exact usable Stonegate package, retain **Preliminary** visibly when it is not
approved/current, approve the exact public-only handoff revision, copy or export its bundle, publish
it in InvestorLift manually, save the resulting property ID and HTTPS URL in Stonegate, and
reconcile provider activity as review-required manual signals.

## Official References

- [Zapier Integration Essentials: triggers, actions, and fields](https://intercom.help/investorlift/en/articles/15119320-zapier-integration-essentials-supported-triggers-actions-and-fields-in-investorlift)
- [Connect a CRM to InvestorLift through Zapier](https://intercom.help/investorlift/en/articles/15119650-step-by-step-connect-your-crm-to-investorlift-via-zapier)
- [God Mode FAQ](https://intercom.help/investorlift/en/articles/15138862-god-mode-faq)
- [Artemis Mode FAQ](https://intercom.help/investorlift/en/articles/15138857-artemis-mode-faq)
- [Find hot leads with Artemis Mode](https://intercom.help/investorlift/en/articles/15164832-find-hot-leads-with-artemis-mode)
- [Track and manage disposition leads](https://intercom.help/investorlift/en/articles/15164885-how-to-track-and-manage-disposition-leads-with-investorlift)
