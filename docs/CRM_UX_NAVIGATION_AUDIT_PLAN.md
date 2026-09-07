# CRM UX and Navigation Redesign Plan

Status: Active

Revised: September 7, 2026

Objective: Give Stonegate one coherent mental model before changing more screens, then bring each important workspace to confident daily-use quality without requiring employees to design or formally test the system.

## Correction to the original plan

The original version moved from a current-state audit directly into structured employee task testing. That was too early and placed design work on Austin and the team.

The corrected sequence is:

1. Codex understands the current system.
2. Codex defines how the system should work.
3. Codex defines where each function belongs and how each page should be laid out.
4. Codex identifies the smallest safe implementation sequence.
5. Codex implements, verifies, commits, and pushes each slice.
6. Normal team usage and screenshots provide optional feedback after coherent designs exist.

Austin, Devon, Alex, and the VAs are not required to conduct formal usability tests, complete evidence forms, or help design the information architecture. Their ordinary questions and screenshots remain useful evidence when they naturally occur.

## Evidence Codex will use

- Current routes, components, controls, data dependencies, and permissions.
- Existing screenshots and issue reports already provided in conversation.
- Business intent stated by Austin, including operational visibility, house and land parity, investor relationship management, and the ability to record real-world work after it happens.
- Established interaction and accessibility principles.
- Automated tests, local rendering, browser inspection, and production behavior after deployment.

Current code remains authoritative when older documentation differs from the product.

## Non-negotiable product principles

- The system should follow the business lifecycle, not expose its database architecture.
- Employees should know where to begin without memorizing which module owns a hidden event.
- A record has one canonical home even when it is visible from several workspaces.
- The same action uses the same name and interaction pattern everywhere.
- Contextual shortcuts may appear anywhere, but they must open the canonical record or shared action.
- Routine operating data is visible across the company so employees can help one another.
- Finance, Marketing, Settings, private economics, destructive actions, and policy changes remain appropriately restricted.
- House and land share the same operating capabilities unless a genuine asset-specific requirement justifies a difference.
- Real-world progress can be recorded after the fact, with accurate evidence and audit history.
- The CRM supports free relationship work; it does not force a rigid sequence when the business does not require one.
- Critical communication and document actions show what was sent, to whom, and whether it succeeded.
- Every page should have one obvious purpose and one obvious primary action.

## Phase 1 - Current-system inventory

Owner: Codex

Status: Complete

Codex inventoried:

- Primary and secondary navigation.
- Routes, redirects, tabs, drawers, modals, and global controls.
- Major functions and record types.
- Role and permission differences.
- Cross-page workflow handoffs.
- High-complexity workspaces.

Deliverable: `docs/CRM_UX_NAVIGATION_AUDIT.md`

## Phase 2 - Current-state diagnosis

Owner: Codex

Status: Complete

Codex identified:

- Overlapping workspace ownership.
- Role-to-navigation mismatches.
- Terminology and hierarchy problems.
- Known reliability and confidence problems.
- Preliminary page scores and priority areas.

Deliverable: `docs/CRM_UX_NAVIGATION_AUDIT.md`

## Phase 3 - Target mental model

Owner: Codex

Status: Complete for the initial architecture

Codex defines:

- The business lifecycle employees should understand.
- The canonical home of every important record and action.
- The target sidebar and role behavior.
- How Today, Inbox, Calendar, Prospecting, Leads, Deals, Dispositions, and Investors relate.
- Where packet, contract, communication, task, and notification functions belong.
- The target anatomy shared by all operating pages.

Deliverable: `docs/CRM_TARGET_MENTAL_MODEL.md`

## Phase 4 - Page blueprints

Owner: Codex

Status: Pending

Before modifying a major page, Codex will define its target blueprint:

- The job the page owns.
- What belongs on the first screen.
- Local navigation and views.
- Primary, secondary, and destructive actions.
- Selected-record behavior.
- Empty, loading, error, success, and restricted states.
- Desktop and mobile layout.
- Links to adjacent canonical workspaces.
- What should be removed, merged, renamed, or moved.

Blueprint order:

1. Global shell, Today, notifications, and universal search.
2. Inbox and shared communication.
3. Prospecting and the VA daily flow.
4. Leads, Pipeline, Offer, and Under Contract.
5. Deals and the post-contract record.
6. Dispositions, Deal & Packet, and investor outreach.
7. Investors and long-term relationship management.
8. Calendar and scheduling.
9. Finance, Marketing, and Settings.

Phase exit condition: The selected page has a coherent target state before implementation begins.

## Phase 5 - Implementation roadmap

Owner: Codex

Status: Pending

Codex will turn the target architecture and blueprints into small, dependency-aware slices. Each slice must:

- Improve a complete job or remove a clear inconsistency.
- Avoid speculative backend rewrites when existing records can support the design.
- State affected roles and records.
- Include a rollback-safe boundary.
- Define automated and visual verification.
- Fit into one commit whenever practical.

Highest-value structural candidates currently are:

1. Correct notification ownership and add a real activity destination.
2. Make ordinary operational navigation consistent across staff roles.
3. Separate the meaning of Deals from Dispositions while preserving fast handoffs.
4. Rename Buyers to Investors in employee-facing language and make it the canonical relationship network.
5. Unify house and land operating capabilities.
6. Consolidate Lead modes around one database with predictable views.
7. Make packet and attachment identity unmistakable across Deals, Dispositions, and Inbox.

These are candidates until Phase 4 determines exact scope.

## Phase 6 - Focused implementation

Owner: Codex

Status: Pending

For each approved slice, Codex will:

1. Record the intended change in the audit documents.
2. Implement the smallest coherent solution.
3. Run focused tests and appropriate broader checks.
4. Inspect the rendered result when visual behavior changes.
5. Commit and push the completed slice.
6. Allow Render to finish deployment before treating production as verified.

The team does not need to run a formal test script after each slice.

## Phase 7 - Codex verification

Owner: Codex

Status: Pending

Verification will use, as appropriate:

- Unit and contract tests.
- TypeScript and lint checks.
- Production builds.
- Local browser inspection at relevant widths.
- Role and permission inspection.
- API and web logs supplied when a production-only issue occurs.
- Production checks when access and deployment state permit them.

## Phase 8 - Optional production feedback

Owners: Stonegate team during normal work

Status: Optional and ongoing

No scheduled usability exercise is required. If Austin or an employee encounters confusion during normal work, a screenshot, recording, or plain-language description can be added to the audit. Codex will use it to correct the target design or implementation.

## Phase 9 - System-wide finish

Owner: Codex

Status: Pending

After major workflows are structurally sound, Codex will complete a global pass for:

- Page titles, breadcrumbs, and orientation.
- Repeated action names and hierarchy.
- Search, filters, tables, boards, drawers, and dialogs.
- Loading, empty, error, success, reconnecting, and restricted states.
- Responsive behavior and keyboard access.
- Visual density, typography, spacing, borders, and button treatment.
- Removal of obsolete or misleading controls.
- Final page and workflow scores.

## Scoring model

Each page and workflow receives a 0-100 score.

| Category | Weight | What it measures |
| --- | ---: | --- |
| Task completion | 30 | Whether the design supports the complete intended result |
| Findability and navigation | 20 | Whether the correct starting point and next step are evident |
| Language and clarity | 15 | Whether labels match ordinary employee vocabulary |
| Cross-page consistency | 15 | Whether learned patterns remain predictable elsewhere |
| Speed and efficiency | 10 | Clicks, waiting, duplicate entry, and context switching |
| Error prevention and recovery | 10 | Mistake prevention, status confidence, and recovery behavior |

Score interpretation:

- 90-100: Confident daily-use quality.
- 80-89: Strong, with identifiable friction.
- 70-79: Usable but requires learning or workarounds.
- 60-69: Confusing or inefficient in important situations.
- Below 60: High risk of mistakes, abandonment, or dependence on another employee.

Codex can assign a design score before team use by tracing every supported job against the code and target mental model. Organic production feedback may later adjust the score, but is not required to begin improvement.

## Working cadence

For each area:

1. Codex creates the target blueprint.
2. Codex compares the blueprint with current code.
3. Codex recommends a limited implementation slice.
4. Codex implements, verifies, commits, and pushes when authorized.
5. Codex updates the audit so work survives context compaction or a device change.

The plan, audit, and target mental model together are the source of truth for this redesign.
