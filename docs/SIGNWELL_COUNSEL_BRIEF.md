# Stonegate Contract Counsel Brief

Status: Ready to send to Georgia real-estate counsel.

This brief keeps legal drafting separate from software configuration. Counsel supplies or approves
the legal language; Stonegate incorporates it into the internal document source and sends the
resulting PDF through SignWell.

## Business Context

Stonegate Home Buyers initially operates in Georgia as a principal real-estate buyer. Stonegate
expects to contract to purchase seller property and, when appropriate, assign its contractual
interest to an end buyer. Stonegate is not asking its software or e-signature provider to determine
whether a transaction is legal, suitable, assignable, or properly disclosed.

Counsel should confirm the purchasing entity's exact legal name before the templates are approved.

## Launch Document Set

Counsel should deliver editable originals and final PDFs for:

1. Georgia purchase and sale agreement used when Stonegate is the buyer.
2. Georgia assignment of purchase agreement used between Stonegate and an end buyer.
3. Purchase agreement amendment or addendum.
4. Mutual termination and release.
5. Any Georgia-specific principal-buyer, equitable-interest, assignment, marketing, or solicitation
   disclosure counsel determines is required or prudent.

Counsel should also identify which templates require Stonegate's signature, whether every titled
owner must sign, how trusts/entities/estates should sign, and whether initials are required on
specific clauses.

## Legal Review Questions

Counsel should answer these in writing:

- May Stonegate assign the purchase agreement without additional seller consent?
- What disclosure should explain that Stonegate is a principal buyer and may make a profit?
- What language is required when Stonegate markets or assigns its contractual interest?
- Which inspection, due-diligence, access, title, closing-attorney, earnest-money, default, and
  termination terms should be used?
- What changes are required for inherited property, probate, trusts, entities, divorce, bankruptcy,
  foreclosure, liens, tenants, or multiple owners?
- Which notices are required for unsolicited Georgia offers and written seller solicitations?
- What retention period should Stonegate apply to signed documents and audit records?
- Which neighboring-state templates must be separately drafted before expansion?

Georgia's Attorney General states that certain unsolicited written real-estate inquiries and offers
require conspicuous notices, including fair-market-value language when a monetary offer is included.
Counsel must decide where those rules apply in Stonegate's acquisition process.

## Stonegate Document Standard

Use these exact recipient placeholder names:

| Template | Required placeholders | Optional placeholders |
| --- | --- | --- |
| Purchase agreement | `Seller`, `Stonegate` | `Seller 2`, `Seller 3` |
| Assignment agreement | `Assignee`, `Stonegate` | `Assignee 2` |
| Addendum | Match the original agreement | Additional titled owner if needed |
| Termination and release | Match the original agreement | Additional titled owner if needed |

Stonegate preserves the signer role and signing order in its own package and provider records.

Stonegate fills these internal data fields when they exist in the legal document:

| Field | Stonegate value |
| --- | --- |
| `seller_name` | Seller name on the approved package |
| `property_address` | Subject property address |
| `buyer_entity_name` | Stonegate purchasing entity |
| `purchase_price` | Seller contract price |
| `earnest_money` | Earnest-money amount |
| `closing_date` | Contract closing date |
| `inspection_period_days` | Inspection or due-diligence period |
| `special_terms` | Approved special terms |
| `assignor_name` | Stonegate assigning entity |
| `assignee_name` | Selected end buyer |
| `assignment_fee` | Approved assignment fee |
| `end_buyer_price` | Original purchase price plus assignment fee |

Only fields actually present in a given document should be included. Stonegate adds signature and
signed-date fields programmatically to the generated PDF.

## Approval Package

For each final template, Stonegate should retain:

- Counsel name, firm, and approval date.
- State and intended transaction use.
- Editable source and final PDF.
- Stonegate source revision and signer roles.
- Stonegate package version and approval record.
- One completed test-mode signature packet with the audit page.

Any legal-language change creates a reviewed Stonegate source revision and requires PDF acceptance
before use.
