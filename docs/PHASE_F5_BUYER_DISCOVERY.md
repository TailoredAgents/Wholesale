# Phase F5: Buyer Discovery And Disposition Readiness

Last updated: July 26, 2026

## Decision

DealMachine is Stonegate's first buyer-data provider. RentCast remains the underwriting and
comparable-sale provider. Stonegate remains the source of truth for buyer identity, verified buy
boxes, proof of funds, engagement history, offers, reliability, and closing outcomes.

## Delivered

- Deal-specific buyer discovery from the Dispositions > Buyers workspace.
- ZIP, property-type, price-band, and recent-sale provider query built from the disposition case.
- Capped provider pulls to control credit use.
- Candidate aggregation by normalized current-owner identity.
- Deterministic scoring for purchase recency, price fit, property-type fit, sampled activity,
  no-recorded-mortgage signal, and entity signal.
- Clear evidence language: no recorded mortgage is a lead signal, not proof of a cash purchase.
- Provider contacts retained when returned with property results.
- Human-selected import; the top candidates are preselected for review but never imported
  automatically.
- Deduplication against previous provider imports and existing normalized buyer identities.
- Imported records enter the existing Stonegate buyer CRM with inferred criteria and unknown proof
  of funds.
- Automatic internal match refresh after approved-package imports.
- Audit records for searches, imports, duplicates, and confirmation that no outreach was sent.
- Provider configuration and status are server-side; the API key is never exposed to the browser.

## How Staff Use It

1. Open **Dispositions** and select a contracted property.
2. Open the **Buyers** tab.
3. Select **Find investors**.
4. Review the ranked candidates and their observed purchase evidence.
5. Uncheck weak candidates and select **Import selected**.
6. Verify each imported buyer's contact details, actual buy box, closing capacity, and proof of
   funds.
7. Refresh or review the internal match list.
8. Generate Dispositions Copilot guidance only after the internal evidence is current.

Discovery and import do not send messages, release campaigns, approve recipients, select offers,
or mark proof of funds as verified.

## Runtime Configuration

Configure only on the Render API service:

```text
BUYER_DATA_PROVIDER=dealmachine
DEALMACHINE_API_KEY=<owner-controlled API key>
DEALMACHINE_BASE_URL=https://api.v2.dealmachine.com/v1
DEALMACHINE_REQUEST_TIMEOUT_SECONDS=30
BUYER_DISCOVERY_MAX_RESULTS=100
```

Keep `BUYER_DATA_PROVIDER=disabled` until the key is present and a controlled Georgia search is
ready.

## Activation Timing

Stonegate will not subscribe to DealMachine during pre-revenue development. Activate it when a
seller opportunity is likely to become a signed contract within one to two weeks, rather than
waiting until after the contract is signed. This allows time to enter the API key, deploy the
configuration, validate Georgia results, import an initial buyer cohort, and correct provider or
matching issues before the disposition deadline begins.

Until then:

- Keep `BUYER_DATA_PROVIDER=disabled`.
- Do not treat the missing `DEALMACHINE_API_KEY` as a deployment failure.
- Add known investors manually to the Stonegate buyer CRM.
- Continue developing and testing provider-independent disposition workflows.

## Scoring Boundary

The provider score prioritizes which records deserve human review. It is not a claim that a
candidate has cash, is currently buying, will close, or fits the final deal.

The existing Stonegate match score then evaluates imported buyer criteria, price capacity,
property type, market, reliability, and verified proof of funds. The Dispositions Copilot explains
that internal evidence and prepares review drafts; it does not invent or certify missing facts.

## Remaining Acceptance

- Run known Atlanta-area searches and compare provider results with county records and known local
  investors.
- Record actual credits consumed per search.
- Verify contacts and buy boxes for the initial buyer cohort.
- Upload current proof of funds only after human verification.
- Run primary and backup buyer selection simulations.
- Run one funded or redacted contract-to-buyer-to-reconciliation simulation.
- Measure response, offer, deposit, closing, and fallout outcomes before changing provider weights
  or granting any external automation.
