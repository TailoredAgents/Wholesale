# Stonegate Public Site Conversion Roadmap

Last updated: August 13, 2026

## Purpose

This roadmap governs the conversion-focused upgrade of the customer-facing Stonegate Home Buyers
website. The objective is to increase qualified seller inquiries and appointments while preserving
the current premium design, honest direct-offer positioning, fast loading, accessibility, and
separate optional SMS consent.

The website should optimize for qualified appointments and contracts, not raw form submissions.
No phase may add invented reviews, unsupported transaction counts, false urgency, guaranteed
offers, guaranteed closing dates, or claims Stonegate cannot consistently fulfill.

## Current Baseline

The public site already provides:

- a Georgia-specific address-first homepage offer
- a two-step selling-options inquiry with optional post-submission property details
- passive phone/email authorization on submission with a separate optional SMS checkbox
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
- Keep the seller's desired timeline in the initial property step, and move condition, occupancy,
  repairs, mortgage, motivation, and comments into an optional
  post-submission enrichment step.
- Issue a random, 24-hour, one-purpose enrichment token whose hash is stored with the intake
  submission; the token can add optional context to that lead but cannot read or edit other data.
- Preserve draft recovery, duplicate handling, validation, attribution, failure recovery, and
  versioned phone/email and optional SMS consent evidence.
- Preserve direct address entry so intake never depends on a third-party address provider.

### Exit Criteria

- A seller can submit a valid inquiry with only the minimum necessary information.
- Optional enrichment remains connected to the same lead.
- Existing phone/email, optional SMS, and conversion evidence remains intact.
- Automated desktop and mobile submission and recovery tests pass.

## Phase PC3: Mobile Conversion Experience

Status: **Implemented**. Branded production verification follows the Render deployment.

### Work

- Add a compact mobile action bar with **Call** and **See My Options** actions.
- Keep actions available while scrolling without covering forms, consent language, errors, legal
  text, or the operating-system Help bubble.
- Improve mobile menu and tap-target behavior.
- Verify phone, tablet, and desktop layouts.
- Record the action, placement, device context, and source route without delaying navigation.
- On the seller-options page, return **See My Options** to the active form instead of restarting the
  seller's work.

### Exit Criteria

- Call and offer actions remain reachable throughout public mobile pages.
- No control overlaps content at supported viewports.
- CTA location and device context are measured.
- The bar is not rendered in `/os`, Clerk authentication, or any other private workspace.

## Phase PC4: Contact And Local Trust Foundation

Status: **Implemented with conservative verified facts**. Branded production verification follows
the Render deployment. Exact staffed hours, county boundaries, and a numeric response-time promise
remain unpublished until the owner confirms them.

### Verified Public Facts

- Current published phone: `(678) 541-7725`.
- Public seller email: `offers@stonegatehb.com`.
- Online property requests are accepted 24 hours a day.
- Initial market language: metro Atlanta and surrounding Georgia communities.
- Property meetings occur at the property by appointment after the next step is confirmed.

### Pending Owner Confirmation

- Confirm whether the currently published phone remains the permanent dedicated Stonegate number
  after the new Twilio setup is approved.
- Confirm genuinely staffed phone hours.
- Confirm the initial county and community boundaries.
- Approve an achievable numeric response-time statement.

Until those facts are confirmed, the site must not publish office hours, a guaranteed response
time, an office address, or a specific county list.

### Work

- Create a Contact and Service Area page.
- Display consistent phone, email, request availability, response expectations, and service areas.
- Explain that Stonegate meets sellers at their properties.
- Update the header, footer, confirmation experience, metadata, and structured data where relevant.
- Record phone and email clicks with their public placement.
- Accept web inquiries at any time while describing human follow-up without an unsupported SLA.

### Exit Criteria

- Every public contact and service-area statement matches the real operation.
- Sellers can understand who will respond, when to expect contact, and whether Stonegate serves
  their location.
- Unconfirmed hours, counties, office location, and response guarantees remain unpublished.

## Phase PC5: Local Search Foundation

Status: **Implemented**. Search Console, Google Business Profile, and branded production
verification remain external acceptance steps.

### Implementation Decisions

- The site publishes one substantive `/service-areas/metro-atlanta` page backed by a reusable
  service-area content model.
- Stonegate uses Organization, WebPage, Service, and BreadcrumbList structured data. It does not
  claim LocalBusiness markup because no staffed customer-facing business address is confirmed.
- Metro Atlanta is described as the initial focus, while coverage is confirmed from the actual
  property address.
- Thin city and county variants are prohibited. A future local page must represent a genuinely
  served market and contain distinct, useful operational information.
- The service-area page is linked from the public header, homepage, contact page, seller-situation
  pages, FAQ page, How It Works page, footer, and sitemap.

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
- The owner verifies the `stonegatehb.com` Search Console domain property, submits the sitemap, and
  configures one accurate service-area Business Profile.

## Phase PC6: Trust And Proof System

Status: **Implemented**. The public section remains hidden until Stonegate records and publishes
genuine proof. Real review collection and first-record production acceptance remain operational
steps.

### Implementation Decisions

- Public proof is managed inside **Marketing**, not in source code.
- Supported records are reviews, seller stories, completed purchases, and statistics.
- Every record moves through draft, review, published, and retired states.
- Publication requires a source URL or internal evidence reference, documented usage permission or
  a reason permission is not required, and a visible disclosure for any material connection.
- Reviews and seller stories require affirmative permission. Statistics require a date and
  documented calculation method.
- Placeholder, sample, and fabricated proof is blocked before review.
- The public API strips internal evidence notes and references. The homepage refreshes published
  proof every five minutes and renders no heading, empty state, or placeholder when none exists.
- Stonegate does not add self-serving Review or AggregateRating structured data.

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
- Unauthorized staff cannot manage public proof, and all decisions create audit records.

## Phase PC7: Conversion Measurement And Testing

Status: **Implemented**. Production baseline collection and the first deliberately approved test
remain operational steps.

### Implementation Decisions

- PC7 extends Stonegate's existing first-party conversion and CRM attribution system rather than
  adding another analytics product.
- Marketing can run one experiment at a time on the homepage offer CTA. The first supported test
  changes CTA wording only, which keeps the causal question understandable.
- A persistent anonymous browser identifier assigns a visitor deterministically to a 50/50
  control or treatment. The assignment cannot change within the seller journey.
- Conversion events record device category without storing seller field values. When a seller
  submits, the assignment links to the resulting lead and follows qualification, appointments,
  signed contracts, collected revenue, source, and campaign.
- Every experiment requires a hypothesis, primary business outcome, at least 20 sessions per
  version, at least seven active runtime days, and a written decision rule before launch.
- Thresholds produce **Ready for human review**, never an automatic winner. Marketing records the
  final decision and supporting business evidence.
- Only one running experiment may affect a public surface. Pausing stops new assignments while
  preserving all existing records and accumulated active runtime.

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
- Stable assignment, downstream lead linkage, permission controls, and experiment decisions are
  covered by automated acceptance tests.

## Phase PC8: Team Identity And Photography

Status: **Implemented and awaiting owner content**. The company-story upgrade, publication-gated
team model, responsive homepage and About-page layouts, structured data, and automated audits are
complete. Final publication and production verification require the approved people, photographs,
titles, and biographies listed below.

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

### Implementation Decisions

- Team content is centralized in `apps/web/src/app/public-team.ts`; approved photographs live in
  `apps/web/public/images/team/`.
- Homepage and About-page team sections return no markup when the approved list is empty.
- A complete approved person record automatically appears on the About page. The single featured
  person appears on the homepage; only the separately confirmed founder appears in Organization
  founder data.
- Duplicate slugs, incomplete content, multiple featured people, unsupported image formats, and
  placeholder language fail the build.
- The current About page explains the actual direct-purchase model, seller accountability
  sequence, Georgia starting market, and operating principles without inventing a company history.
- `docs/PUBLIC_TEAM_CONTENT.md` defines the approval packet, photography standard, file preparation,
  publication behavior, and final acceptance procedure.
- The public browser audit checks the homepage and About page for placeholder language, missing or
  broken photographs, inadequate image dimensions, missing alt text, layout overflow, and serious
  accessibility findings.

### Exit Criteria

- The site clearly identifies the real people behind Stonegate.
- No placeholder or inactive team member appears publicly.
- Photographs remain sharp and fast on mobile and desktop.
- The complete production public-site audit passes.

## Recommended Order

PC1 through PC7 are implemented. PC8's publication path is implemented but intentionally remains
visually gated until approved real team photographs and biographies are added. Follow
`docs/PUBLIC_TEAM_CONTENT.md` to complete the owner-content handoff and production acceptance.
