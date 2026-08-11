# Stonegate Public Site Performance Audit

- Audit date: August 11, 2026
- Baseline: production site at commit `252ac6b`
- Scope: public loading performance only; no visual, copy, form-flow, or tracking changes
- Target pages: `/` and `/get-a-cash-offer`

## Result

The public site had one high-impact, low-risk performance defect: every public visitor loaded the
staff authentication provider and ran its middleware. On the production mobile homepage trace,
that caused a Clerk development-browser handshake and 12 authentication requests totaling about
373 KB transferred before the visitor had any need to sign in.

The fix keeps authentication on the CRM, legacy lead, sign-in, and sign-up routes while removing it
from public marketing pages. The cash-offer route is also pre-rendered, and public images now expose
better-sized candidates. The page design, content, behavior, Meta Pixel events, web-vitals reporting,
and lead submission path are unchanged.

## Production Baseline

Lighthouse 13 mobile emulation was captured against the live site before implementation.

| Page | Performance | FCP | LCP | TBT | CLS | Transfer | Requests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Homepage | 70 | 2.68 s | 7.82 s | 144 ms | 0 | 1.12 MB | 48 |
| Cash offer | 96 | 1.70 s | 2.60 s | 105 ms | 0 | 0.91 MB | 49 |

These are laboratory measurements, not guaranteed field results. Real-user Core Web Vitals remain
the source of truth after deployment and representative ad traffic.

## Safe Changes Implemented

1. Scoped `ClerkProvider` and Clerk middleware to authenticated and authentication routes.
2. Converted `/get-a-cash-offer` from request-time rendering to static pre-rendering while keeping
   homepage address prefill in the browser.
3. Added an accurate `sizes` hint to the 44-pixel brand mark so mobile browsers do not request an
   unnecessarily large image candidate.
4. Added 1440- and 1600-pixel responsive candidates for large public images and a 512-pixel fixed
   image candidate.
5. Added a performance contract test to prevent the public authentication payload, dynamic offer
   route, and image-sizing regressions from returning.
6. Updated the IA audit so middleware matcher patterns are not misclassified as clickable links.

## Verification

The optimized local production build produced these Lighthouse checks:

| Page | Performance | FCP | LCP | TBT | CLS |
| --- | ---: | ---: | ---: | ---: | ---: |
| Homepage | 94 | 1.06 s | 3.15 s | 45 ms | 0 |
| Cash offer | 100 | 1.06 s | 1.88 s | 57 ms | 0 |

Local scores are confirmation of the optimized application path, not a direct before-and-after
production comparison because production advertising and monitoring providers are intentionally
absent from the local environment.

The following also passed:

- optimized Next.js production build
- public desktop, tablet, and mobile lead-journey audit
- TypeScript type checking
- ESLint
- information-architecture contract suite
- underwriting workspace contract suite
- public performance contract suite

The production build manifest confirms both public target pages are pre-rendered.

## Deliberately Preserved

- Meta Pixel and conversion events remain enabled for advertising attribution.
- Sentry and real-user web-vitals measurement remain enabled for production visibility.
- The hero artwork was not recompressed or visually altered.
- No page sections, styles, text, forms, or user-facing interactions changed.

## Post-Deployment Acceptance

After Render deploys this commit:

1. Confirm public page traces contain no Clerk handshake or Clerk browser bundle.
2. Repeat the production mobile Lighthouse captures for both target pages.
3. Confirm the cash-offer route is cacheable and homepage address prefill still works.
4. Confirm Meta PageView, ViewContent, form-start, and lead events still appear in Events Manager.
5. Review production LCP, INP, and CLS after enough real traffic exists; use those field metrics for
   any further optimization decision.
