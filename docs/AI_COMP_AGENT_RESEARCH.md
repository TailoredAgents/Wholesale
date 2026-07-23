# AI Comp Agent Research

Last updated: July 23, 2026

## Recommendation

Use OpenAI as the reasoning layer, not the source of truth for comps.

Default model:

- `gpt-5.6-sol`
- `reasoning.effort=medium`

Why:

- `gpt-5.6-sol` is Stonegate's current deployment target; AI2/AI3 evaluation comparisons determine
  whether a lower-cost route can replace it for any exact capability.
- The Responses API is the correct API surface for reasoning, tool-calling, and multi-turn agent workflows.
- Structured Outputs should be used for comp decisions so the OS receives predictable fields instead of free-form valuation prose.

## Data Sources Required

The comp agent needs current property data APIs before it can produce useful ARV support.

Primary provider for the current build:

- RentCast.
- Use first because the account/API key is available now and it gives value estimates, comparable
  sale-listing candidates, property records, listings, rent estimates, and market trends at a low
  starting cost. Provider candidates require source/status review before Stonegate describes them
  as verified closed sales.

Later enterprise provider:

- ATTOM Property Data API.
- Use for property facts, parcel/tax data, owner data, sale history, AVM, equity signals, and nearby sales.

Secondary/fallback provider:

- ATTOM, if upgraded later, or MLS/RESO where licensed.

MLS/listing provider:

- RESO Web API through Bridge Interactive or another MLS-approved feed.
- Use for active, pending, expired, and sold listing data where we have licensed access.

Web search:

- Useful for public context and source checking.
- Not sufficient as the primary comp source because public web data can be stale, missing sale terms, duplicated, or unavailable.

## Comp Agent Workflow

1. Normalize and validate the subject property address.
2. Pull property facts from the property data provider.
3. Pull comparable candidates within configurable radius and lookback windows and retain their
   source and sale/listing status.
4. Filter comps by distance, sale recency, property type, beds/baths, square footage, year built, lot size, condition notes, and outlier price per square foot.
5. Run deterministic scoring, condition review, repair, and buyer-economics calculations.
6. Optionally ask OpenAI to summarize the normalized evidence and propose review tasks using
   structured output. AI must not change comp facts or calculation results.
7. Store selected comps, rejected comps with reasons, value ranges, confidence, missing data,
   buyer economics, and the recommended next task.
8. Require human approval before using the result for an offer ceiling.

The detailed recorded-sale, ARV, repair, and buyer-economics method lives in
`docs/UNDERWRITING_COMP_METHOD.md`.

## Structured Output Shape

The comp agent should return a strict JSON object with:

- `subject_summary`
- `selected_comps[]`
- `rejected_comps[]`
- `arv_low_cents`
- `arv_high_cents`
- `confidence`
- `confidence_reasons[]`
- `missing_data[]`
- `risk_flags[]`
- `recommended_next_action`

## Guardrails

- AI cannot make binding offers.
- AI cannot approve ARV.
- AI cannot send offers or contracts.
- AI must cite the provider/source for each comp.
- AI must flag weak comp sets instead of forcing a valuation.
- AI output must be stored as a draft underwriting version or proposed comp review.

## Environment Variables

OpenAI:

- `OPENAI_API_KEY`
- `OPENAI_DEFAULT_MODEL=gpt-5.6-sol`
- `OPENAI_REASONING_EFFORT=medium`
- `OPENAI_WEB_SEARCH_ENABLED=false`

Property data:

- `PROPERTY_DATA_PROVIDER=rentcast`
- `RENTCAST_API_KEY`
- `RENTCAST_BASE_URL=https://api.rentcast.io/v1`
- `ATTOM_API_KEY`
- `BRIDGE_API_BASE_URL`
- `BRIDGE_API_KEY`

## Research Sources

- OpenAI latest model guide: https://developers.openai.com/api/docs/guides/latest-model
- OpenAI web search tool guide: https://developers.openai.com/api/docs/guides/tools-web-search
- OpenAI Structured Outputs guide: https://developers.openai.com/api/docs/guides/structured-outputs
- ATTOM Property Data API: https://www.attomdata.com/solutions/delivery/property-data-api/
- ATTOM developer docs: https://api.developer.attomdata.com/docs
- RentCast API: https://www.rentcast.io/api
- Bridge Interactive data access: https://www.bridgeinteractive.com/developers/data-access/
- RESO Web API: https://www.reso.org/reso-web-api/
