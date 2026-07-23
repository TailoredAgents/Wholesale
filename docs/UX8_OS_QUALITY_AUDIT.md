# UX8 OS Quality Audit

Date completed: July 22, 2026

## Outcome

Phase UX8 validates the upgraded Stonegate Operating System as one product. The populated audit
completed 88 route and viewport combinations with no unresolved serious or critical accessibility
finding, horizontal overflow, broken landmark structure, unnamed control, duplicate identifier,
missing image alternative, browser error, or reduced-motion failure.

This result covers automated and visual regression checks. A human owner walkthrough remains part
of deployment acceptance whenever a role's permissions or representative workflow changes.

## Route Matrix

The audit covers Dashboard, Inbox, Work Queue, Calendar, Acquisition Operations, Campaigns,
Prospecting, Lead Desk, All Leads, Seller Pipeline, Field Operations, Underwriting, Approvals,
Transactions, Dispositions, Buyers, Finance, Marketing, Operating Model, AI Control, Archived Leads,
and a populated lead record.

Every route is checked at these widths:

- 390 pixels for mobile
- 768 pixels for tablet
- 1280 pixels for laptop
- 1440 pixels for desktop

The development-only design-system route is intentionally excluded from the production matrix
because it returns `404` in a production build.

## Automated Gate

Run the audit against a production-mode web instance backed by a populated API:

```bash
cd apps/web
OS_AUDIT_BASE_URL=http://127.0.0.1:3000 \
OS_AUDIT_LEAD_ID=<populated-lead-id> \
npm run audit:os
```

Set `OS_AUDIT_SCREENSHOT_DIR` to write full-page screenshots for Dashboard, Inbox, All Leads,
lead detail, Underwriting, and Dispositions. Set `CHROME_EXECUTABLE_PATH` only when Chrome is not in
its normal macOS location.

The gate checks:

- HTTP and browser console failures
- Page-level horizontal overflow
- Exactly one main landmark and one page-level heading
- Accessible names for links, buttons, form controls, and disclosure controls
- Duplicate IDs and missing image alternatives
- Serious and critical axe-core WCAG 2.0 A/AA, 2.1 AA, and 2.2 AA findings
- Skip-link keyboard behavior and visible focus
- Mobile navigation focus transfer, containment, Escape close, and trigger restoration
- Native drawer Escape close and trigger restoration
- Key text-to-surface contrast pairs
- Reduced-motion animation, transition, and scroll behavior

## Product Corrections

- The shell owns the single main landmark; workspace layouts use labeled sections inside it.
- The Stonegate product name is no longer incorrectly exposed as every page's primary heading.
- Inbox and Archived Leads now provide explicit page-level headings.
- A skip link lets keyboard users bypass persistent navigation and focus the workspace directly.
- Global focus-visible styling no longer depends on each page implementing its own outline.
- Mobile navigation behaves as a modal drawer and restores the user's keyboard position on close.
- Buyer creation and destructive lead actions use the shared native dialog components.
- Reduced-motion preferences apply even to page-local transitions and animations.

## Visual And Performance Review

Representative screenshots were reviewed at mobile, tablet, laptop, and desktop widths. Dense deal
workspaces retain readable queue/detail relationships at wider sizes and convert to focused stacked
or pane-based workflows on smaller screens. Long lead records remain vertically scrollable without
forcing horizontal scrolling, and empty queue states preserve their surrounding layout.

The review found no image-heavy OS route or new blocking client dependency. The accessibility audit
adds development-only packages and does not increase the production browser bundle. Large lists
remain bounded by API limits or compact queue surfaces; future record growth should be handled with
server pagination or virtualization instead of rendering an unbounded client list.

## Release Checklist

- `npm run lint`
- `npx tsc --noEmit`
- `npm run build`
- `npm run audit:os` against populated production-mode services
- Complete API pytest suite
- Owner walkthrough for roles or permissions changed by the release

UX9 can begin after this gate is green. UX9 covers public website architecture, Stonegate brand and
trust presentation, content claims, imagery, and seller-facing wayfinding.
