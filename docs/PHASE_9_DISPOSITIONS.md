# Phase 9: Buyers, Dispositions, And Reconciliation

Status: Complete for the provider-neutral manual workflow.

## Operating Path

1. An executed transaction is opened in Dispositions.
2. Stonegate freezes the active compensation plan and human-led operating mode on that case.
3. Staff reviews and approves the investor package before matching or export.
4. Matching scores proof of funds, price capacity, market, buyer reliability, and property type.
5. Staff approves a simulated recipient release. Phase 9 does not send buyer messages.
6. Inquiries, showings, follow-ups, offers, and deposit terms remain attached to the case.
7. A human selects the primary and optional backup offer. Selection requires an acceptable price
   and current verified proof-of-funds evidence.
8. After funding, collected revenue and deal-specific costs produce an Adjusted Deal Margin.
9. The frozen plan allocates approved role credits, applies caps, and calculates company profit.
10. An owner approves the statement and downloads the accounting CSV.

## Deterministic Buyer Score

| Evidence | Weight |
| --- | ---: |
| Current verified proof of funds | 30% |
| Capacity at or above the approved minimum | 25% |
| Market fit | 20% |
| Historical reliability | 15% |
| Property-type fit | 10% |

A high numeric score does not override qualification. Missing proof, insufficient capacity, market
mismatch, or property-type mismatch produces `review_required` and excludes that buyer from the
approved campaign pool.

## Financial Controls

```text
Adjusted Deal Margin =
  collected deal revenue
  - frozen acquisition/outreach reserve
  - deal-specific deductions
```

The transaction-coordinator cap returns unused commission capacity to the company. Reconciliation
approval is blocked while any paid role lacks approved role credit. A result below the compensation
plan's company-margin target requires a separate, explicit owner override.

## Deferred Adapters

- Buyer email/SMS delivery after provider activation and compliance acceptance testing.
- QuickBooks Online after the approved CSV workflow is proven on funded deals.
- Object storage after evidence volume warrants moving binary files out of PostgreSQL.
- AI disposition modes only after Phase 10 evaluations demonstrate safe, profitable performance.
