# AI Comp Agent Research

## Recommendation

Use OpenAI as the reasoning layer, not the source of truth for comps.

Default model:

- `gpt-5.6-terra`
- `reasoning.effort=medium`

Why:

- OpenAI currently recommends `gpt-5.6-terra` as the balanced intelligence/cost model.
- The Responses API is the correct API surface for reasoning, tool-calling, and multi-turn agent workflows.
- Structured Outputs should be used for comp decisions so the OS receives predictable fields instead of free-form valuation prose.

## Data Sources Required

The comp agent needs current property data APIs before it can produce useful ARV support.

Primary provider:

- ATTOM Property Data API.
- Use for property facts, parcel/tax data, owner data, sale history, AVM, equity signals, and nearby sales.

Secondary/fallback provider:

- RentCast.
- Use for fast property records, AVM, rent estimates, active listings, sale history, and market trends.

MLS/listing provider:

- RESO Web API through Bridge Interactive or another MLS-approved feed.
- Use for active, pending, expired, and sold listing data where we have licensed access.

Web search:

- Useful for public context and source checking.
- Not sufficient as the primary comp source because public web data can be stale, missing sale terms, duplicated, or unavailable.

## Comp Agent Workflow

1. Normalize and validate the subject property address.
2. Pull property facts from the property data provider.
3. Pull sold comps within configurable radius and lookback windows.
4. Filter comps by distance, sale recency, property type, beds/baths, square footage, year built, lot size, condition notes, and outlier price per square foot.
5. Ask OpenAI to reason over the normalized comp packet using structured output.
6. Store selected comps, rejected comps with reasons, ARV range, confidence, missing data, and recommended next task.
7. Require human approval before using the result for an offer ceiling.

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
- `OPENAI_DEFAULT_MODEL=gpt-5.6-terra`
- `OPENAI_REASONING_EFFORT=medium`
- `OPENAI_WEB_SEARCH_ENABLED=false`

Property data:

- `PROPERTY_DATA_PROVIDER=attom`
- `ATTOM_API_KEY`
- `RENTCAST_API_KEY`
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
