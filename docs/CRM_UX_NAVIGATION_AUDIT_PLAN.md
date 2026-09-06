# CRM UX and Navigation Audit Plan

Status: Active

Started: September 6, 2026

Objective: Make Stonegate understandable, predictable, and efficient for the people who use it every day.

## Why this audit exists

Stonegate has grown quickly across acquisitions, communications, underwriting, contracts, dispositions, buyers, and closing. Individual capabilities can work correctly while the overall product still feels difficult to learn or navigate. This audit will evaluate the complete operating experience instead of polishing isolated screens without understanding how work moves between them.

The audit uses three kinds of evidence:

1. Repository evidence: routes, components, permissions, data dependencies, actions, and workflow transitions.
2. Rendered evidence: screenshots or recordings showing real data, visual hierarchy, density, loading, overflow, and responsive behavior.
3. User evidence: task completion, hesitation, incorrect first clicks, backtracking, errors, and questions from Austin, Devon, Alex, and the VA.

## Ground rules

- Map the system before reorganizing it.
- Evaluate complete jobs as well as individual pages.
- Prefer the language employees naturally use over internal database terminology.
- Give one familiar action one consistent name and location.
- Keep sensitive areas such as Finance, Marketing, and Settings appropriately permissioned while making normal operating work visible to the company.
- Separate usability problems from performance, authorization, and reliability problems, while recording all four.
- Implement one coherent workflow improvement at a time.
- Test, commit, push, deploy, and validate each implementation slice before expanding its scope.
- Preserve unrelated user work and avoid speculative large rewrites.

## Phase 1 — Codebase inventory

Owner: Codex

Codex will inventory:

- Primary and secondary navigation.
- Routes, pages, tabs, drawers, modals, and global controls.
- Important page states: loading, empty, selected, error, success, and restricted.
- Functions and actions available from each workspace.
- Role and permission differences.
- Cross-page links and workflow handoffs.
- Duplicated, hidden, or inconsistently named capabilities.

Deliverables:

- `docs/CRM_UX_NAVIGATION_AUDIT.md`
- A current system/navigation diagram.
- A page and function inventory.
- A role-access matrix.

Phase exit condition: Every major workspace and primary action has an identified location and purpose.

## Phase 2 — Preliminary usability audit

Owner: Codex

Codex will use repository evidence and existing screenshots to:

- Establish baseline page and workflow scores.
- Identify obvious hierarchy, naming, discoverability, and consistency problems.
- Separate global design-system problems from page-specific problems.
- Identify pages that require screenshots or real-user observation before a recommendation is safe.
- Produce a prioritized evidence queue based on business impact and usage frequency.

Initial workflow priority:

1. Inbox and daily communication.
2. Leads and pipeline.
3. Offer and Under Contract.
4. Dispositions and investor outreach.
5. Deals, packets, documents, and closing.
6. Buyers and investor relationship management.
7. Home, Tasks, and Calendar.
8. Finance, Marketing, and Settings.

Phase exit condition: The team has a defensible order for reviewing workflows and knows what evidence is still missing.

## Phase 3 — Real-user evidence

Owners: Austin, the VA, Devon, and Alex

The team will test one workflow at a time without coaching. A useful evidence packet contains:

- The user and their role.
- The specific result they were trying to achieve.
- A short screen recording, when practical, or two to five full-window screenshots.
- The first control they expected to use.
- Where they hesitated, backtracked, or asked for help.
- Whether they completed the task and approximately how long it took.
- Any unexpected loading, failure, missing data, or permission behavior.

Representative tasks:

- Find a seller and continue the correct conversation.
- Move a lead through qualification and underwriting.
- Record an existing signed contract and open Dispositions.
- Find a deal to market and contact a chosen investor.
- Send or retrieve an investor packet during a conversation.
- Find an investor reply and set the next action.
- Find a contract or previously sent attachment.

Phase exit condition: The selected workflow has enough evidence to explain the user’s difficulty rather than merely confirm that difficulty exists.

## Phase 4 — Focused redesign and implementation

Owner: Codex

For the selected workflow, Codex will:

- Compare repository, rendered, and user evidence.
- Identify the underlying problem rather than only the visible symptom.
- Recommend simplification, unification, renaming, relocation, or removal as appropriate.
- Update the audit and proposed score.
- Implement one limited, coherent improvement.
- Verify the affected behavior and regression risk.
- Commit and push the completed slice.

Phase exit condition: The improved workflow is deployed and ready for the same real-world task to be repeated.

## Phase 5 — Production validation

Owners: Austin and the employee who originally tested the workflow

After deployment, the same user repeats the same task without coaching and reports:

- Whether the first action was obvious.
- Whether they completed the task.
- Remaining hesitation or wrong turns.
- Anything that disappeared, broke, or became slower.
- A screenshot of the deployed result when visual evidence is useful.

Phase exit condition: The workflow is either accepted or has a short, evidence-backed correction list.

## Phase 6 — Workflow correction and closure

Owner: Codex

Codex will address the production findings, verify relevant screen sizes and roles, update the audit, commit and push the correction, and mark the workflow complete. Phases 3 through 6 then repeat for the next workflow.

## Phase 7 — System-wide unification

Owner: Codex

After the major workflows are complete, Codex will perform a cross-system pass for:

- Navigation terminology and ordering.
- Page titles, breadcrumbs, and orientation cues.
- Button hierarchy and repeated action labels.
- Search, filters, tables, boards, drawers, and modals.
- Loading, empty, error, success, and permission states.
- Responsive behavior and keyboard navigation.
- Obsolete, duplicated, or misleading controls.

Phase exit condition: Shared patterns are consistent across the operating system.

## Phase 8 — Final acceptance

Owners: Stonegate team, then Codex

The Stonegate team completes a short daily-work acceptance script. Codex resolves remaining findings and publishes:

- The final system and workflow map.
- Final page and workflow scores.
- A concise employee navigation guide.
- A future-improvement backlog separated from launch-critical work.

## Scoring model

Each major page and workflow receives a 0–100 score.

| Category | Weight | What it measures |
| --- | ---: | --- |
| Task completion | 30 | Whether the intended result can be completed correctly |
| Findability and navigation | 20 | Whether users know where to begin and where to go next |
| Language and clarity | 15 | Whether labels and instructions match employee vocabulary |
| Cross-page consistency | 15 | Whether learned patterns remain predictable elsewhere |
| Speed and efficiency | 10 | Clicks, waiting, re-entry, and unnecessary context switching |
| Error prevention and recovery | 10 | Protection from mistakes and clarity when something fails |

Score interpretation:

- 90–100: Confident daily-use quality.
- 80–89: Strong, with identifiable friction.
- 70–79: Usable but requires training or workarounds.
- 60–69: Confusing or inefficient in important situations.
- Below 60: High risk of abandonment, mistakes, or dependence on another employee.

Scores are baselines for prioritization, not substitutes for observed task performance.

## Repeatable working cadence

For each workflow:

1. Codex maps and audits.
2. Stonegate supplies real-user evidence.
3. Codex recommends and implements a focused improvement.
4. Stonegate validates the deployed behavior.
5. Codex corrects and closes the workflow.

The audit document is the source of truth throughout this process so the work can resume accurately after context compaction, a device change, or a delay between sessions.
