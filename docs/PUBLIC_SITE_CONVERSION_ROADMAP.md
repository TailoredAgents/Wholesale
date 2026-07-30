# Stonegate Public Site Conversion Roadmap

Last updated: July 29, 2026

## Purpose

This roadmap governs the conversion-focused upgrade of the customer-facing Stonegate Home Buyers
website. The objective is to increase qualified seller inquiries and appointments while preserving
the current premium design, honest direct-offer positioning, fast loading, accessibility, and
separate SMS consent.

The website should optimize for qualified appointments and contracts, not raw form submissions.
No phase may add invented reviews, unsupported transaction counts, false urgency, guaranteed
offers, guaranteed closing dates, or claims Stonegate cannot consistently fulfill.

## Current Baseline

The public site already provides:

- a Georgia-specific address-first homepage offer
- a two-step cash-offer form with optional post-submission property details
- separate contact and SMS consent
- draft recovery, duplicate handling, and submission recovery
- phone-click, page-view, offer-start, form-step, abandonment, and submission measurement
- real-user LCP, INP, and CLS reporting
- direct-offer versus traditional-listing education
- seller-situation, process, FAQ, company, privacy, and terms pages
- responsive desktop and mobile layouts
- canonical metadata, Open Graph metadata, a sitemap, and Organization structured data

The July 29, 2026 audit found that the largest remaining conversion weakness is proof of the real
local people and operation behind Stonegate. The final team-photography phase is intentionally
last so that the preceding conversion infrastructure can be completed without placeholder assets.

## Status Rules

- **Planned** means implementation has not started.
- **Implemented** means the code and automated coverage exist.
- **Production verified** means the branded production site passed the phase checks.
- **Measured** means enough real traffic exists to evaluate a conversion decision.

Research establishes a defensible baseline, but Stonegate's own qualified-lead, appointment,
contract, and funded-deal outcomes determine which variation performs best.

## Phase PC1: Technical Conversion Baseline

Status: **Production verified** on `https://www.stonegatehb.com`.

### Work

- Correct public logo contrast without redesigning the brand.
- Prevent private OS and authentication routes from being indexed.
- Correct robots and sitemap behavior.
- Validate titles, descriptions, canonicals, Organization data, public route availability,
  accessibility, responsive overflow, and the complete offer journey.
- Preserve the current public layout, copy, and conversion flow.

### Exit Criteria

- The public audit passes at desktop and mobile viewports.
- No serious or critical accessibility finding remains.
- `/os`, `/sign-in`, and `/sign-up` are excluded from indexing.
- The sitemap contains public routes only and does not publish misleading modification dates.
- Public production routes remain available after deployment.

## Phase PC2: Lead Form Simplification

Status: **Implemented**. Branded production verification follows the Render deployment.

### Work

- Reduce the initial journey to Property, Contact, and Confirmation.
- Create the lead as soon as the minimum valid property and contact information is submitted.
- Move condition, occupancy, repairs, mortgage, motivation, timing, and comments into an optional
  post-submission enrichment step.
- Issue a random, 24-hour, one-purpose enrichment token whose hash is stored with the intake
  submission; the token can add optional context to that lead but cannot read or edit other data.
- Preserve draft recovery, duplicate handling, validation, attribution, failure recovery, and
  separate SMS consent.
- Preserve direct address entry so intake never depends on a third-party address provider.

### Exit Criteria

- A seller can submit a valid inquiry with only the minimum necessary information.
- Optional enrichment remains connected to the same lead.
- Existing consent and conversion evidence remains intact.
- Automated desktop and mobile submission and recovery tests pass.

## Phase PC3: Mobile Conversion Experience

Status: **Planned**

### Work

- Add a compact mobile action bar with Call and Get Offer actions.
- Keep actions available while scrolling without covering forms, consent language, errors, legal
  text, or the operating-system Help bubble.
- Improve mobile menu and tap-target behavior.
- Verify phone, tablet, and desktop layouts.

### Exit Criteria

- Call and offer actions remain reachable throughout public mobile pages.
- No control overlaps content at supported viewports.
- CTA location and device context are measured.

## Phase PC4: Contact And Local Trust Foundation

Status: **Planned**

### Owner Inputs

- Confirm the dedicated public Stonegate phone number.
- Confirm the public email address.
- Confirm genuinely staffed contact hours.
- Confirm the initial counties and communities Stonegate can serve.
- Approve an achievable response-time statement.

### Work

- Create a Contact and Service Area page.
- Display consistent phone, email, hours, response expectations, and service areas.
- Explain that Stonegate meets sellers at their properties.
- Update the header, footer, confirmation experience, metadata, and structured data where relevant.

### Exit Criteria

- Every public contact and service-area statement matches the real operation.
- Sellers can understand who will respond, when to expect contact, and whether Stonegate serves
  their location.

## Phase PC5: Local Search Foundation

Status: **Planned**

### Work

- Expand accurate Organization or LocalBusiness structured data using only public company facts.
- Create a useful Metro Atlanta service-area page.
- Build reusable local-page architecture without publishing thin or repetitive doorway pages.
- Strengthen internal links among situations, service areas, FAQs, and the offer form.
- Document Google Business Profile and Search Console setup.

### Exit Criteria

- Search engines can understand Stonegate's identity, service area, and public contact details.
- Only genuinely served markets are published.
- Structured data passes validation and matches visible page content.

## Phase PC6: Trust And Proof System

Status: **Planned**

### Work

- Build controlled sections for verified reviews, completed purchases, seller stories, and
  transaction statistics.
- Keep every proof section hidden until genuine approved evidence exists.
- Store source links, usage permission, publication status, and relevant disclosures.
- Never display placeholder ratings, fabricated testimonials, or unsupported totals.

### Exit Criteria

- Real proof can be published without a redesign.
- Every visible claim has a recorded source and approval.
- Empty proof sections never appear to sellers.

## Phase PC7: Conversion Measurement And Testing

Status: **Planned**

### Work

- Measure CTA placement, initial submission, optional enrichment, phone clicks, qualification,
  appointments, contracts, and funded outcomes.
- Add controlled experiment assignment and variant attribution.
- Report results by device, source, campaign, and qualified business outcome.
- Establish a production baseline before changing major headlines or offers.

### Exit Criteria

- A variation can be tied to downstream CRM outcomes without exposing seller details.
- Decisions are based on qualified appointments, contracts, cost per contract, and funded margin.
- Experiments do not run without enough traffic or a named decision rule.

## Phase PC8: Team Identity And Photography

Status: **Planned**

### Owner Inputs

- Austin's approved founder and closer photograph and biography.
- Approved photographs, names, and public titles for active team members.
- Optional natural group, office, or property-visit photographs.
- Written confirmation of who should appear publicly.

### Work

- Add a polished founder section to the homepage.
- Rebuild the About page around the real Stonegate team and company story.
- Optimize, crop, and responsively size every photograph.
- Add accurate alt text and update public company data.
- Perform the final visual, accessibility, speed, and conversion audit.

### Exit Criteria

- The site clearly identifies the real people behind Stonegate.
- No placeholder or inactive team member appears publicly.
- Photographs remain sharp and fast on mobile and desktop.
- The complete production public-site audit passes.

## Recommended Order

Complete PC1 through PC7 in order. Collect real company facts, proof, reviews, and transaction
evidence while those phases are underway. Complete PC8 only when the approved team photographs and
public biographies are ready.
