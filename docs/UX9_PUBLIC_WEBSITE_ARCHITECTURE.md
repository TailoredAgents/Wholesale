# UX9 Public Website Architecture, Brand, And Trust

Last updated: July 22, 2026

Status: Implementation complete. Owner content acceptance and production domain verification remain.

## Purpose

UX9 rebuilds the seller-facing website around a credible direct-offer decision rather than a generic
lead form. It intentionally does not claim that Stonegate produces the highest price, closes within
an unsupported period, or has reviews, transaction volume, team members, or local offices that have
not been verified.

## Research Conclusions

The implementation applies these current public-site patterns:

- Begin with the property address and one literal seller outcome.
- Explain the direct-offer process before asking a seller to trust the company.
- Make the retail-price versus convenience tradeoff explicit.
- Use visible company identity, phone contact, service area, legal disclosures, and plain answers to
  common objections.
- Keep situation content out of crowded primary navigation while maintaining crawlable pages.
- Use people-first content and descriptive headings instead of repetitive search-keyword copy.
- Publish only advertising claims that Stonegate can substantiate.
- Do not fabricate reviews, team photography, office locations, transaction counts, savings, or
  response-time guarantees.

Primary guidance reviewed:

- Google Search Central organization and website structured-data guidance.
- Google Search Central people-first content guidance.
- FTC advertising, endorsement, and testimonial guidance.
- W3C WCAG form purpose, focus, contrast, keyboard, and responsive requirements.
- Public direct-homebuyer experiences from Opendoor, Sundae, and HomeVestors were reviewed for
  process and objection patterns, not copied for appearance or unsupported claims.

## Public Sitemap

| Route | Primary job | Primary action |
| --- | --- | --- |
| `/` | Explain the offer and tradeoff | Enter property address |
| `/how-it-works` | Explain review, pricing, and contract sequence | Start offer |
| `/about` | Establish company identity and boundaries | Request offer |
| `/faqs` | Resolve seller questions and objections | Call Stonegate |
| `/get-a-cash-offer` | Capture the current seller inquiry | Submit request |
| `/sell-inherited-house` | Address inherited-property concerns | Enter property address |
| `/sell-house-needs-repairs` | Address condition and repair concerns | Enter property address |
| `/sell-house-fast` | Address timeline concerns without guarantees | Enter property address |
| `/privacy-policy` | Explain data handling and messaging privacy | Contact Stonegate |
| `/terms` | Explain website, offer, and SMS terms | Contact Stonegate |

The primary navigation is limited to How It Works, Selling Situations, About, FAQs, phone contact,
and Get a Cash Offer. Situation pages remain discoverable from the homepage and sitemap.

## Visual Direction

- Dark evergreen communicates stability without turning the full site into a single-color theme.
- White and cool neutral surfaces keep long seller content easy to scan.
- Restrained brass marks actions and section labels; it is not used as decorative gradient color.
- Georgia-style property photography shows the real object being discussed.
- Georgia serif headings provide a grounded editorial voice; system sans-serif text keeps controls
  fast and legible without external font requests.
- Lucide icons communicate familiar actions and assurances.
- Cards are limited to repeated situation and principle items. Sections remain unframed bands.

Local generated assets:

- `apps/web/public/images/stonegate-georgia-home-hero.jpg`
- `apps/web/public/images/stonegate-inherited-home.jpg`
- `apps/web/public/images/stonegate-repair-kitchen.jpg`

The assets are project-bound and may not be reused as verified transaction properties. They are
representative visual content, not customer testimonials or evidence of a Stonegate purchase.

## Claims And Trust Rules

The public website now says that Stonegate is a real estate investment company, not a brokerage or
appraisal service. It explains that a direct offer may be below potential retail market value and
that any purchase depends on written contract terms, title review, and property verification.

The implementation removes the unsupported `24 hr` review claim. It does not promise a closing
period, price, savings, commission comparison beyond Stonegate's own direct process, or guaranteed
purchase. It also discloses that contractual purchase rights may be assigned when permitted by the
written agreement.

## Search And Technical Structure

- Shared title templates, descriptions, canonical URLs, Open Graph data, and local social image.
- Organization and WebSite JSON-LD with only name, website, phone, and Georgia service area.
- Generated `/sitemap.xml` for public routes.
- Generated `/robots.txt` that excludes authenticated OS and authentication routes.
- Local Next Image assets with responsive sizing and descriptive alternative text.
- One first-level heading and one primary seller action on every public route.

## Verification

- ESLint: pass.
- TypeScript: pass.
- Next.js production build: pass.
- Ten public routes checked at 1440 by 1000 and 390 by 844: all return `200`.
- No document-level horizontal overflow at either viewport.
- Axe-core WCAG A and AA scan on the homepage: no violations at either viewport.
- Desktop and mobile screenshots reviewed for homepage and mobile offer form.
- Address entered on the homepage is preserved in the existing offer form.

Local conversion-event CORS errors are expected when the temporary browser origin uses port 3023;
production uses the configured allowed web origin. The Clerk development configuration prompt shown
in local screenshots is also not part of the deployed production experience.

## Required Business Evidence Before Final Launch

Stonegate should supply these when they are real and approved:

- Legal entity and business mailing address if they should appear publicly.
- Real team names, roles, biographies, and professional photographs.
- Verifiable customer reviews with permission, source, date, and any required disclosure.
- Verified service territories as operations expand.
- Supportable response, offer, close-time, savings, or transaction-volume statistics before making
  any quantified claim.

These omissions are intentional. UX10 can measure the current truthful baseline before Stonegate
adds verified proof or begins controlled conversion tests.

The branded domain is active and is the production value for `NEXT_PUBLIC_SITE_URL`.
