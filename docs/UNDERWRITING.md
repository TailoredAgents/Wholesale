# Underwriting

## Provider Abstraction

Use adapters for property facts, ownership, sales history, comparable sales, listings, tax data, mortgage indicators, AVMs, and market statistics.

## Comps

Start with conservative criteria: same property type, nearby location, recent sale, similar size, similar beds/baths, similar age, similar construction, similar basement/garage/lot, and comparable renovation state.

Expansion order:

1. Sale age.
2. Distance.
3. Square-footage tolerance.
4. Nearby neighborhood boundaries.
5. Adjusted property differences.

## Offer Formula

```text
Expected Buyer Price = ARV * Buyer Percentage - Repairs - Buyer-Specific Adjustments
Maximum Seller Offer = Expected Buyer Price - Target Assignment Fee - Direct Wholesale Costs - Risk Buffer
```

Calculate 65%, 67.5%, and 70% scenarios.

Detailed implementation method:

- `docs/UNDERWRITING_COMP_METHOD.md`
