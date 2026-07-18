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
Flip Buyer Maximum = Conservative ARV - Rehab - Purchase Costs - Holding - Resale - Profit
Seller Contract Ceiling = Best Supported Buyer Maximum - Assignment Fee - Transaction Reserve
Opening Recommendation = Seller Contract Ceiling - Negotiation Reserve
```

The 65-70% rule is retained as a comparison, not the controlling calculation.

Detailed implementation method:

- `docs/UNDERWRITING_COMP_METHOD.md`
