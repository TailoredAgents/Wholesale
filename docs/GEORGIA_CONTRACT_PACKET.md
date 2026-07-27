# Georgia Contract Packet

Status: Operational version 1 prepared for SignWell setup.

## What This Packet Is

This is an original Stonegate contract packet for initial Georgia wholesale transactions. It gives the
company usable documents and stable SignWell fields now, without copying licensed Georgia
Association of Realtors forms.

These documents are not a substitute for transaction-specific legal advice. Replace them with a
Georgia real-estate attorney's approved versions before Stonegate treats the packet as final
production language. The CFO may administer templates and transaction facts, but should not invent
or materially revise legal clauses for a live transaction.

## Included Files

Editable Word files are in `docs/templates/ga-contracts/`:

| Document | Intended use |
| --- | --- |
| `stonegate-ga-investor-purchase-agreement.docx` | Stonegate contracts to buy from a seller |
| `stonegate-ga-assignment-agreement.docx` | Stonegate assigns its buyer rights to an end buyer |
| `stonegate-ga-contract-addendum.docx` | All required parties change written contract terms |
| `stonegate-ga-buyer-termination-notice.docx` | Stonegate exercises an express termination right |
| `stonegate-ga-mutual-termination-release.docx` | Buyer and seller mutually terminate and release |
| `stonegate-ga-legal-description-exhibit-A.docx` | Verified deed legal description attached to purchase contract |
| `epa-seller-lead-based-paint-disclosure.pdf` | Official federal seller disclosure for applicable pre-1978 housing |
| `epa-protect-your-family-from-lead-2026.pdf` | Official EPA pamphlet provided for applicable pre-1978 housing |

The matching HTML files are editable source files used to generate the Word documents.

## Decisions To Fill In Before First Use

Confirm these operating facts once and use the same values consistently:

1. Stonegate's exact purchasing entity legal name and state of formation.
2. Authorized Stonegate signer name and title.
3. Default Georgia closing attorney or firm and contact information.
4. Default earnest-money amount and delivery deadline.
5. Default due-diligence period.
6. Default closing-cost allocation and closing timeline.
7. Stonegate notice email, mailing address, and phone number.

Do not send a contract with an entity nickname, missing owner, incomplete legal description,
unresolved blank, or unapproved special term.

## SignWell Setup

Create a separate SignWell template for each document that will be signed. Keep Exhibit A and the
federal lead disclosure as attachments when applicable.

### Purchase Agreement

- Template name: `Stonegate GA Purchase Agreement v1`
- Required placeholders: `Seller`, `Stonegate`
- Optional placeholders: `Seller 2`, `Seller 3`
- Fields: `seller_name`, `property_address`, `buyer_entity_name`, `purchase_price`,
  `earnest_money`, `closing_date`, `inspection_period_days`, `special_terms`
- Add signature and signed-date fields for every required signer.

### Assignment Agreement

- Template name: `Stonegate GA Assignment Agreement v1`
- Required placeholders: `Assignee`, `Stonegate`
- Optional placeholder: `Assignee 2`
- Fields: `property_address`, `assignor_name`, `assignee_name`, `assignment_fee`,
  `end_buyer_price`, `closing_date`, `special_terms`
- Add signature and signed-date fields for every required signer.

### Addendum and Mutual Release

- Use the same seller and Stonegate placeholders as the original purchase agreement.
- Place only fields that appear in the document.
- Every party whose rights are changed or released should be included as a signer.

### Buyer Termination Notice

- Stonegate is the only signer.
- Delivery evidence matters. Send the completed notice to every notice address required by the
  purchase agreement and retain proof of delivery in the transaction.
- A notice does not itself authorize an escrow holder to release disputed earnest money.

## Stonegate Installation

1. Finish each SignWell template and copy its template ID.
2. In **OS > Transactions > Contract > Legal template**, upload the matching Word file.
3. Select the matching document type and `GA`.
4. Include the version number in the Stonegate template name.
5. Connect the Stonegate template to its SignWell template ID.
6. Keep `ESIGN_TEST_MODE=true` and complete the acceptance steps in
   `docs/SIGNWELL_LAUNCH_RUNBOOK.md`.
7. Record the exact version used on every transaction.

Do not mix fields or SignWell IDs between versions. Never edit a template after it has been used for
signing; create a new version.

## Transaction Controls

Escalate a transaction for closing-attorney or counsel review before signature when it involves:

- probate, an estate, a trust, guardianship, or power of attorney;
- a corporation, partnership, or LLC seller;
- divorce, bankruptcy, foreclosure, tax sale, or pending litigation;
- tenants, occupants who are not owners, liens, judgments, or disputed ownership;
- seller financing, subject-to financing, novation, double closing, or unusual consideration;
- missing owners, uncertain authority, or an unclear legal description;
- a seller who does not understand the transaction or requests legal advice; or
- a special term that materially changes risk, remedies, access, possession, title, or payment.

Georgia closings should be coordinated through the selected Georgia closing attorney. For
residential property built before 1978, use the federal lead disclosure process and provide the
required EPA pamphlet before the buyer is obligated, subject to applicable exemptions.

The included federal files were downloaded from the official EPA pages:

- https://www.epa.gov/lead/sellers-disclosure-information-lead-based-paint-andor-lead-based-paint-hazards
- https://www.epa.gov/lead/protect-your-family-lead-your-home-real-estate-disclosure

## Later Attorney Approval

Send `docs/SIGNWELL_COUNSEL_BRIEF.md` and this full packet to Georgia real-estate counsel. For every
approved replacement:

1. Retain the counsel name, firm, approval date, state, and intended use.
2. Create a new SignWell template and new Stonegate template version.
3. Run a test-mode signature packet and verify the completed PDF and audit page.
4. Retire version 1 from future use without deleting historical signed records.
5. Mark the reviewed replacement as the active version.
