# Georgia Contract Packet

Status: Operational version 1 used by Stonegate's internal document generator.

## What This Packet Is

This is an original Stonegate contract packet for initial Georgia wholesale transactions. It gives
the company usable internal document sources without copying licensed Georgia Association of
Realtors forms.

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

## Internal Document Generation

Stonegate currently generates the Purchase Agreement, Assignment Agreement, and Contract Addendum
from the matching HTML source. It fills approved package terms, creates a locked PDF signing copy,
adds the ordered signature and date fields, and sends the PDF through SignWell. No agreement
template is maintained in SignWell.

Exhibit A, federal lead disclosures, termination notices, and other supporting documents remain
separate files and should be attached or delivered when applicable.

## Stonegate Installation

1. Confirm the HTML source contains the intended agreement language.
2. Create each document type from a controlled Stonegate transaction.
3. Inspect the generated PDF, populated data, signer names, and signature locations.
4. Keep `ESIGN_TEST_MODE=true` and complete the acceptance steps in
   `docs/SIGNWELL_LAUNCH_RUNBOOK.md`.
5. Record the exact contract package version used on every transaction.

Never rewrite a package after approval or signing. Create a new package version.

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
2. Create a reviewed Stonegate source revision.
3. Run a test-mode signature packet and verify the completed PDF and audit page.
4. Retire version 1 from future use without deleting historical signed records.
5. Mark the reviewed replacement as the active version.
