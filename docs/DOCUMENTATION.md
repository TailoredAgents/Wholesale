# Stonegate Documentation Guide

Last verified against the repository: July 30, 2026

## Purpose

This file defines the documentation system for Stonegate Home Buyers. It prevents completed build
notes, old provider plans, and current operating instructions from being treated as equally
authoritative.

The documentation is intended to support three audiences:

1. Stonegate employees who need to perform their jobs.
2. Owners, administrators, and developers who configure or maintain the platform.
3. A future internal help assistant that answers questions from approved Stonegate documentation.

## Source Priority

When sources disagree, use this order:

1. **Application code and database migrations** determine what the software actually does.
2. **`SYSTEM_MAP.md`** describes the current product and its boundaries.
3. **`FINISHING_ROADMAP.md`** describes unfinished work and external acceptance steps.
4. **`CRM_INFORMATION_ARCHITECTURE_ROADMAP.md`** describes the approved private-OS
   reorganization target and migration sequence.
5. **`PUBLIC_SITE_CONVERSION_ROADMAP.md`** describes the active seller-site conversion program.
6. **Domain references** define approved operating policy and specialist methods.
7. **User manuals** explain how staff should perform current workflows.
8. **Git history** preserves completed phase plans and prior decisions for forensic review only.

Never use an old commit, completed phase document, or provider application draft to override the
current code or canonical documentation.

## Canonical Files

| File | Authoritative subject | Intended reader |
| --- | --- | --- |
| `SYSTEM_MAP.md` | Complete as-built product, architecture, modules, lifecycle, data, integrations, and boundaries | Everyone |
| `FINISHING_ROADMAP.md` | Remaining work, acceptance tests, and launch gates | Owner and developers |
| `CRM_INFORMATION_ARCHITECTURE_ROADMAP.md` | Approved target navigation, workspace consolidation, route migration, role experience, and IA phase plan | Owner, managers, and developers |
| `PUBLIC_SITE_CONVERSION_ROADMAP.md` | Public seller-site conversion phases, inputs, and acceptance criteria | Owner, marketing, and developers |
| `VA_DIALER_ROADMAP.md` | One-by-one VA calling workflow, acceptance, handoff, and reporting sequence | Owner, prospecting managers, and developers |
| `OPERATING_MODEL.md` | Roles, handoffs, compensation, service standards, and management cadence | Owner and managers |
| `AI_AGENTS.md` | AI architecture, specialist capabilities, tools, memory, and autonomy rules | Owner, managers, and developers |
| `AI_AUTOMATION_ROADMAP.md` | Remaining path from copilots to measured automation | Owner and developers |
| `UNDERWRITING_COMP_METHOD.md` | Comp selection, ARV, repairs, offer math, confidence, and calibration | Acquisitions and underwriting |
| `SETUP_REFERENCE.md` | Local setup, production services, environment variables, and provider activation | Owner and developers |
| `SETUP_MANUAL.md` | Nontechnical provider, account, staff, launch, and maintenance procedures | Owner and trusted administrators |
| `USER_MANUAL.md` | Full current operating instructions | All staff |
| `UI_CONTROL_REFERENCE.md` | Page-by-page buttons, fields, effects, prerequisites, disabled states, and expected results | All staff and help-assistant maintainers |
| `LEAD_MANAGER_USER_MANUAL.md` | Plain-language Lead Manager daily workflow | Lead Managers |
| `STAFF_ROLE_MANUALS.md` | Role boundaries and job-specific workflows | Staff and managers |
| `SECURITY_COMPLIANCE.md` | Access, communications, records, and operational controls | Owner and managers |
| `DESIGN_SYSTEM.md` | Frontend visual and interaction standards | Developers |
| `GEORGIA_CONTRACT_PACKET.md` | Current Georgia contract packet content and limits | Owner and transaction staff |
| `SIGNWELL_COUNSEL_BRIEF.md` | Questions and evidence for later legal review of e-signature documents | Owner and counsel |
| `DECISIONS/` | Durable architecture decisions, including the accepted task-centered OS information architecture | Developers |

`../apps/web/AGENTS.md` and `../apps/web/CLAUDE.md` are repository tool instructions. They are not
employee help content and must not be ingested into the staff help assistant.

## Document Types

### System Truth

`SYSTEM_MAP.md` answers:

- What is Stonegate OS?
- What pages, services, records, and integrations exist?
- How does a seller move from inquiry to closing?
- Which actions are automatic, draft-only, approval-gated, simulated, or externally pending?
- Where does each capability live in the interface and code?

### Operating Policy

`OPERATING_MODEL.md`, `SECURITY_COMPLIANCE.md`, and `UNDERWRITING_COMP_METHOD.md` answer:

- Who owns the work?
- What is the approved business process?
- What calculations and decision rules apply?
- What must remain under human authority?

### Instructions

The manuals answer:

- What should I click?
- What information should I enter?
- What happens next?
- What should I do if something fails?

`USER_MANUAL.md` was regenerated and verified against the application on July 29, 2026.
`UI_CONTROL_REFERENCE.md` is the detailed interface dictionary and should be used for questions
about a specific page, section, button, field, disabled state, or immediate result. The
role-specific manuals remain shorter job aids and should defer to the main manual and control
reference when they omit a workflow or interface detail. `SETUP_MANUAL.md` provides the
nontechnical owner procedure while `SETUP_REFERENCE.md` remains the exact maintainer inventory.

### Future Work

`FINISHING_ROADMAP.md`, `CRM_INFORMATION_ARCHITECTURE_ROADMAP.md`,
`PUBLIC_SITE_CONVERSION_ROADMAP.md`, `VA_DIALER_ROADMAP.md`, and
`AI_AUTOMATION_ROADMAP.md` answer:

- What is incomplete?
- What requires credentials, provider approval, production evidence, or human acceptance?
- What sequence should be followed?

A roadmap item is not proof that a capability is absent. Always check its implementation status
and `SYSTEM_MAP.md`.

## Status Vocabulary

Use only these terms in canonical documentation:

| Status | Meaning |
| --- | --- |
| **Implemented** | The workflow exists in code and has automated coverage. |
| **Configured** | Required external settings or credentials are present in the target environment. |
| **Active** | The provider-backed production workflow has passed an end-to-end acceptance test. |
| **Simulated** | The workflow can be exercised without sending data to an external provider. |
| **Draft-only** | The system may recommend or prepare work but a human must approve or perform the consequential action. |
| **Approval-gated** | The system enforces a named human decision before progression. |
| **Externally pending** | Code exists, but an outside account, credential, provider approval, or professional review is incomplete. |
| **Planned** | The capability is not yet implemented. |

Avoid the word “complete” without specifying whether it means implementation, configuration, or
production acceptance.

## Maintenance Rules

Update the documentation in the same change when any of these occur:

- A page, API route, role, permission, integration, or core workflow is added or removed.
- A provider changes from disabled or simulated to active.
- A business rule, commission rule, underwriting formula, or approval boundary changes.
- A new migration adds a major data domain.
- A known launch blocker is resolved or discovered.

For each update:

1. Change `SYSTEM_MAP.md` when current behavior changes.
2. Change the relevant domain reference when policy or methodology changes.
3. Change `FINISHING_ROADMAP.md` when remaining work changes.
4. Change the affected manual when staff steps change.
5. Change `UI_CONTROL_REFERENCE.md` when a page, tab, button, field, prerequisite, or disabled
   state changes.
6. Update the “Last verified” date only after checking the implementation.

Do not create a new phase Markdown file for routine implementation. Use Git commits and pull
requests for build history. Create a new durable document only when it has a distinct long-term
owner and subject.

## Stonegate Help

The authenticated **Help** workspace retrieves only approved canonical files. Each answer should:

- State whether it concerns current behavior, setup, policy, or future work.
- Cite the document heading used.
- Respect the requesting employee's role.
- Never expose secrets, private seller data, restricted correspondence, accounting evidence, or
  legal documents the employee cannot access in Stonegate OS.
- Say when a feature is externally pending instead of inventing setup success.
- Route policy, tax, legal, offer-approval, and compliance decisions to the authorized human.

Recommended ingestion metadata:

- `document`
- `heading_path`
- `audience`
- `role_scope`
- `topic`
- `status`
- `last_verified`
- `source_priority`

The assistant should answer “what does this button or field do?” from
`UI_CONTROL_REFERENCE.md`, “how do I complete this workflow?” from the manuals, “how does this
work?” from `SYSTEM_MAP.md`, “what are the rules?” from domain references, and “what remains?”
from roadmaps.

The current implementation chunks Markdown by heading, filters documents and sensitive topic
areas by the signed-in user's role, retrieves the strongest matching sections, and returns the
document title, heading path, and excerpt. OpenAI may summarize those sources when configured.
A deterministic source excerpt remains available when OpenAI is unavailable. Help has no tools
for reading or changing live Stonegate records.
