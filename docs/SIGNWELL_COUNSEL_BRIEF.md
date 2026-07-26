# Stonegate Contract Counsel Brief

Status: Ready to send to Georgia real-estate counsel.

This brief keeps legal drafting separate from software configuration. Counsel supplies or approves
the legal language; Stonegate then uses the stable signer roles and field IDs below without another
engineering pass.

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

## SignWell Template Standard

Use these exact recipient placeholder names:

| Template | Required placeholders | Optional placeholders |
| --- | --- | --- |
| Purchase agreement | `Seller`, `Stonegate` | `Seller 2`, `Seller 3` |
| Assignment agreement | `Assignee`, `Stonegate` | `Assignee 2` |
| Addendum | Match the original agreement | Additional titled owner if needed |
| Termination and release | Match the original agreement | Additional titled owner if needed |

Do not rename placeholders after production use begins. Stonegate matches recipients by exact
placeholder name and preserves signing order.

Use these exact SignWell field API IDs when the field exists in the legal document:

| API ID | Stonegate value |
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

Only fields actually present in a given document should be placed on that template. Signature,
initial, and signed-date fields should be assigned to the correct recipient placeholder in
SignWell.

## Approval Package

For each final template, Stonegate should retain:

- Counsel name, firm, and approval date.
- State and intended transaction use.
- Editable source and final PDF.
- SignWell template ID and exact recipient placeholders.
- SignWell field API IDs.
- Stonegate template version and approval record.
- One completed test-mode signature packet with the audit page.

Any legal-language change creates a new Stonegate template version and requires approval before use.
