# Stonegate OS Design System

Last updated: July 22, 2026

Status: Phase UX2 foundation complete.

This document defines the visual and interaction foundation for the Stonegate Operating System.
It applies to internal OS workspaces. The public seller website receives its own conversion-focused
application of the brand during Phases UX9 and UX10.

## Source Files

- Semantic theme tokens: `apps/web/src/app/os/os-theme.module.css`
- Core controls and system states: `apps/web/src/app/os/_components/design-system.tsx`
- Core control styles: `apps/web/src/app/os/_components/design-system.module.css`
- Page contracts: `apps/web/src/app/os/_components/page-contracts.tsx`
- Page contract styles: `apps/web/src/app/os/_components/page-contracts.module.css`
- Development reference: `/os/design-system`

The reference route is available only in development. Production returns a not-found response so
the component catalog does not become an employee workspace or primary navigation destination.

## Token Rules

- Use `--sg-color-*` tokens for all new OS color decisions.
- Use semantic status colors only for meaning: success, warning, danger, info, or neutral.
- Pair status color with an icon and plain-language text.
- Use `--sg-space-*`, `--sg-radius-*`, and `--sg-control-height-*` instead of new local values.
- Keep cards and panels at an 8-pixel radius or less.
- Use `--sg-focus-ring` for keyboard focus and preserve reduced-motion behavior.
- Compatibility aliases such as `--brand` and `--surface` remain only while existing pages migrate.

## Component Rules

- Use `Button` for commands and `IconButton` for familiar icon-only tools.
- Every `IconButton` requires a descriptive `label`, which supplies its accessible name and tooltip.
- Use `FormField` with `TextInput`, `Select`, or `TextArea` so labels, help, and validation remain
  consistent.
- Use `Checkbox` for binary choices and `SegmentedControl` for a small set of mutually exclusive
  modes.
- Use `Tabs` only for related content inside one record or workspace. Tabs must not replace primary
  navigation.
- Use `StatusBadge`, `Alert`, `EmptyState`, `Skeleton`, `Toast`, `Dialog`, `Drawer`, and `Menu`
  instead of page-specific state treatments.
- Use `TableShell` around wide tables so keyboard users can reach and horizontally scroll the table.
- Do not put a `SectionPanel` inside another `SectionPanel`.

## Page Contracts

### Queue

Use `QueuePageContract` for repeated triage work such as Inbox, Work Queue, and Lead Desk. The queue
is the first column, active work is the center, and supporting context is the third column. On small
screens, context becomes a drawer and the queue stacks above active work.

### Record

Use `RecordSummaryHeader` and `RecordPageContract` for lead, buyer, transaction, and other record
pages. Primary record work stays in the main column. Tasks, pinned notes, audit context, or supporting
facts belong in the side column. Use `StickyActionBar` when users must save or approve after editing
a long record.

### Pipeline

Use `PipelinePageContract` for stage-based opportunity work. Columns have stable widths and scroll
inside the contract rather than widening the document.

### Calendar

Use `CalendarPageContract` for month, week, day, and agenda views. People, market, and event filters
occupy the side region on wide screens and become a drawer on small screens.

### Management

Use `ManagementPageContract` for Operating Model, Finance configuration, AI Control, Team,
Integrations, and Settings. The local section navigation is separate from the global OS navigation.

## Page Composition

1. Wrap the route in `WorkspacePage`.
2. Add one `PageHeader` with the literal workspace name, concise operating context, and primary
   action.
3. Use the page contract that matches the job being performed.
4. Use `SectionPanel` only for genuinely framed tools or groups that require a shared header.
5. Put secondary forms in tabs, drawers, or dialogs instead of extending the default page
   indefinitely.
6. Preserve loading, empty, success, warning, error, disabled, and permission-denied states.

## Responsive And Accessibility Standard

- Validate changed routes at 390, 768, 1280, and 1440 pixels.
- Keep document width equal to viewport width; tables, pipelines, tabs, and segmented controls may
  scroll only within their own bounded region.
- Keep labels visible and associate help or error text with its control.
- Preserve keyboard focus, native dialog cancellation, escape behavior, and readable tab order.
- Never communicate status using color alone.
- Respect reduced-motion preferences and avoid motion that changes layout dimensions.

## Migration Boundary

Phase UX2 establishes the system but does not restyle every production page. Phases UX3 through UX8
will migrate the shell and workspaces in operating priority order. New OS UI created before those
migrations must use these tokens, components, and page contracts.
