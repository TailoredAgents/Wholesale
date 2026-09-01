# 0004: Unified House And Land Workflows

Status: Accepted

Date: August 8, 2026

## Context

Stonegate is adding vacant-land wholesaling to the existing house-wholesaling business. Most of
the operating lifecycle is shared, but qualification, property diligence, valuation, site work,
contract evidence, and buyer criteria differ materially. The existing provider `property_type`
values are not stable enough to control consequential workflow behavior, and existing fields named
`strategy` already describe offer or disposition mechanics.

## Decision

Stonegate will keep one CRM and lifecycle. Campaigns, prospects, and leads carry an explicit
`asset_class` of `house` or `land`. `property_type` remains a descriptive physical classification.

Property-research snapshots/runs and underwriting analyses/versions carry explicit versioned
profiles. Cache lookup, invalidation, and idempotency include the applicable profile so evidence
cannot cross asset classes.

The House path retains the current residential valuation and inspection behavior. The Land path
uses dedicated qualification, diligence, comparable-sale math, site observations, contract gates,
and buyer criteria behind a disabled-by-default release flag.

## Consequences

- Leads, Inbox, Calendar, Tasks, Buyers, Deals, communications, and AI records remain shared.
- Existing data backfills to House for compatibility.
- Parcel-first Land records require a durable APN-based identity when no normal situs address is
  available.
- Land automated research is screening evidence and cannot prove buildability.
- Land cannot call the residential ARV/repair engine.
- Stonegate-generated and e-signed Land contract execution remains blocked until an approved
  Land-specific legal template is active. Recording an agreement already executed elsewhere is a
  separate evidence-import path and does not cross that boundary.
- The release flag can stop unfinished Land automation without deleting durable records.
