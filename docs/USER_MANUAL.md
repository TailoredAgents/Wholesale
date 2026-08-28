# Stonegate Operating System User Manual

Last verified against the application: August 28, 2026

## Purpose

This is the canonical non-technical guide for using Stonegate. It explains how employees use the
public seller website and private Operating System from initial outreach through funded closing,
accounting, and management review.

The live web application is:

- Public website: `https://www.stonegatehb.com`
- Private OS: `https://www.stonegatehb.com/os`

The legacy Render URL remains a valid fallback. The `oakwell-*` service names are infrastructure
identifiers for Stonegate, not a second company or workspace.

### How To Use This Manual

- Start with **Roles And Access** and **First Sign-In** when joining Stonegate.
- Use **Recommended Daily Routine** for the shortest job-specific checklist.
- Use the numbered workflow sections when performing a task for the first time.
- Use **Troubleshooting** before creating duplicate records or repeating a provider action.
- Words shown in **bold** are labels visible in the Stonegate interface.
- Text shown in `monospace` is a route, identifier, or technical value that should be entered
  exactly.

This guide describes both available controls and controls waiting on an external provider. A
visible button does not prove the provider is active. Read its status message before using it.

## Current Release Boundary

The complete internal workflow is implemented:

- Public seller intake and consent evidence.
- Campaigns, imports, screening, calling batches, and VA prospecting.
- Warm handoff, Lead Queue, qualification, tasks, Inbox, and appointments.
- Field preparation, inspections, underwriting, reports, offer approval, and negotiation records.
- Contract generation, transaction coordination, SignWell records, and in-person iPad signing.
- Buyers, House disposition packages, governed owned-buyer email/SMS outreach and reply review,
  buyer offers, selection, reconciliation, and accounting export.
- The internal double-entry accounting ledger, vendor bills, bank reconciliation, statements, CPA
  export, marketing measurement, operating policy, AI Copilots, and AI governance.
- Resend email sending, receiving, aliases, mailbox routing, attachments, notifications, and
  response-time tracking.

The following still require external configuration, approval, or production acceptance:

- Controlled Resend production mailbox acceptance.
- Repeat the internal new-lead alert delivery test after the worker credential correction;
  seller-facing SMS production acceptance remains pending.
- Twilio cellphone forwarding and inbound routing acceptance.
- Call recording until the market-specific authorization and retention policy are approved.
- SignWell, private production object storage, and approved legal document acceptance.
- Ongoing RealEstateAPI credit, match-quality, and duplicate-refresh monitoring.
- Controlled production acceptance of governed House buyer-package email/SMS delivery and Google
  conversion delivery; the accepted Meta browser/server path still requires ongoing diagnostics and
  campaign monitoring.
- CPA acceptance of opening balances and the first Stonegate month close.
- Real Georgia underwriting calibration and supervised Copilot pilots.
- Autonomous AI external delivery.
- Production Land-wholesaling activation. House/Land intake, VA handoff, qualification, call
  notes, parcel facts, profile-safe research, and the first dedicated Land valuation workspace are
  implemented, but official diligence sources, site visits, legal templates, offer approval,
  reports, and disposition packaging remain behind the launch boundary.

When a provider is unavailable, Stonegate records and manual workflows still operate. Do not
interpret a provider-disabled message as lost CRM data.

### House And Land Workflow Boundary

Stonegate uses one **Leads** workspace for both business lines. A record is explicitly labeled
**House** or **Land**; use the **Type** filter in Leads to focus the list. Do not create a second
contact, Inbox thread, or deal pipeline solely because the property is Land.

Current Land pilot controls include:

- House/Land selection on manual lead creation, Inbox email conversion, campaigns, imports, and
  approved VA/Lead Manager scripts.
- Land propagation through warm handoff, the Lead Queue, staff new-lead text alerts, call
  intelligence, Activity, and AI context.
- Parcel/APN capture and Land-specific seller facts such as acreage, access/frontage, utilities,
  stated zoning/use, septic/perc, taxes/HOA, and known terrain or environmental concerns.
- A dedicated `land_v1` property-research profile. When enabled, RealEstateAPI collects saved
  property-record facts and optional licensed imagery without running residential comps or ARV.
- Addressed parcels and parcels identified only by APN + county + state use the same Land research
  path. APN matching is county-scoped, and a provider identity mismatch fails closed without
  overwriting the CRM parcel.
- A dedicated **Land Valuation** tab searches arms-length closed Land sales only after a user
  presses the explicit search button. The first analysis makes at most one RealEstateAPI property
  search; reopening the tab and saving a reviewed comparable set reuse saved evidence with zero
  provider calls.
- Land value ranges are calculated deterministically from saved price-per-acre evidence. Provider
  AVMs, residential ARV, building square footage, and repair formulas are excluded.
- The latest Land valuation and selected saved sales are included in the lead's governed AI
  context. AI may summarize that evidence and identify missing research; it does not select,
  calculate, or silently change the deterministic value or offer fields.
- Opening guidance and the seller contract ceiling remain withheld until parcel identity, fresh
  acreage, compatible sale evidence, acceptable dispersion, human-verified legal access, and an
  active owner-approved Land offer policy all pass. A supported research range may still appear
  while those consequential offer fields are withheld.
- Separate House and Land snapshot caches so one workflow cannot reuse the other workflow's
  evidence.
- A hard safety boundary around residential valuation and execution. Land leads cannot create or
  approve House ARV/comps, repair estimates, offer authority, residential field inspections,
  acquisitions-copilot output, valuation PDFs, residential transactions, House contract packages,
  e-signatures, or residential buyer disposition. The CRM shows Land-specific holding screens
  instead. Legacy House versions and execution records remain readable/cancellable audit history,
  but cannot advance as Land work.

`LAND_WORKFLOW_ENABLED` is `false` by default. A disabled Land research message means the lead is
safe in the CRM and the residential valuation path was intentionally skipped. Managers can verify
the feature and RealEstateAPI readiness under **Settings > Integrations**.

To use the current internal Land valuation pilot:

1. Confirm the lead is marked **Land** and review the APN, county, state, acreage, land use, and
   coordinates under **Property**. Refresh research if the saved identity is stale or incomplete.
2. Open **Land Valuation**. Choose a search tier, record the access evidence status and source,
   optionally map the subject to a human-reviewed Land-use group with a cited source, and press
   **Search closed Land sales and save analysis** only when a provider search is intended.
3. Review every selected sale. Uncheck unsuitable evidence and save the reviewed set; that creates
   a new immutable version without another provider search. Rejecting every candidate is allowed
   and produces an insufficient-evidence result.
4. An owner may create the recommended offer-policy draft, inspect its discounts and reserves, and
   activate it explicitly. Activation never changes an older saved analysis; rerun or review the
   analysis to apply the active policy.
5. Treat **Withheld** as a hard stop. Do not copy a supported value range into an offer when the
   workspace lists access, identity, evidence, dispersion, freshness, or policy blockers.

Until the remaining Land stages are released:

1. Do not try to bypass the system's House ARV, repair, room, or living-area guards for Land.
2. Treat provider zoning, flood, utility, access, soil, wetland, and similar results as screening
   evidence, not proof of legal access or buildability.
3. Do not send Stonegate's residential purchase agreement for a Land transaction.
4. Keep valuation, offer, contract, and disposition work under manual management review.

## Core Rules

1. Every person uses an individual Clerk login. Never share credentials.
2. Leads remain in one Stonegate workspace. Reassign ownership instead of copying records.
3. PostgreSQL records are the source of truth. Text messages, calls, documents, and AI outputs must
   attach to the existing record.
4. Complete the current record before creating a replacement. The intake and import processes
   already detect many duplicates.
5. Human-confirmed facts outrank provider facts. Provider facts outrank AI inference.
6. AI output is a draft or recommendation until a person reviews it.
7. Offers, contracts, buyer selection, funding, commissions, and external automation remain
   human-controlled.
8. Honor seller opt-outs, explicit Do Not Contact values, company suppression, and provider
   restrictions.
9. Do not mark work complete merely because a draft was created or a provider request was sent.
10. When responsibility changes, reassign the existing record and create the next dated action.

## Interface Basics

### Page Header

Every workspace begins with:

- the page name
- a short description
- a status badge or summary when relevant
- primary actions such as **Compose**, **Refresh**, a reporting period, or a Copilot launcher

Read warning and unavailable messages before entering data. They normally explain a missing role,
provider, selected record, or prerequisite.

### Lists And Selected Records

Many pages use a list on the left and selected-record details on the right:

1. Select one row or card.
2. Review the context before acting.
3. Use the visible primary action for the next workflow step.
4. Return to the list without creating a second record.

On mobile, the list, record, and details become separate **Inbox**, **Thread**, **Details**, or
similar views. Use the mobile view buttons rather than expecting all panels at once.

### Tabs And Segmented Controls

Tabs change the section of the same workspace. They do not create or save a record. Finish or save
the current form before changing tabs when the page warns about unsaved work.

### Status Messages

- **Ready**, **Current**, or green success text means the current prerequisite passed.
- **Needs review**, **Pending**, or warning text means a person must inspect or decide something.
- **Blocked**, **Unavailable**, or red error text means the action was not completed.
- **Draft** means editable, unapproved work.
- **Approved** means a named person authorized that version.
- **Sent** means a provider request was accepted; it does not necessarily mean delivered, signed,
  replied to, paid, or funded.
- **Closed** means a dead or disqualified seller opportunity whose routine follow-up has stopped.
- **Archived** means a confirmed duplicate or test record retained outside normal active views.
  Administrative archive is not a business disposition for a real seller opportunity.

### Saving And Refreshing

- Wait for **Saved**, **Sent**, **Updated**, or another success message before leaving.
- A disabled button usually means a required field, permission, provider, or prerequisite is
  missing.
- Use **Refresh** after an external callback or another employee updates the same record.
- Never double-click a send, import, contract, payment-state, or provider action.

### Money And Dates

- Dollar fields are displayed as dollars; the system stores exact cents.
- Use the seller's or closing document's exact amount, not a rounded estimate, for contracts,
  offers, reconciliation, and accounting.
- Verify timezone and date before scheduling, closing, or posting.
- A missing due date means the work cannot be managed reliably; add the next dated action.

## Roles And Access

Navigation is generated from both the user's job role and permissions. Hidden pages are normally
intentional.

| Role | Normal starting workspace | Primary responsibilities |
| --- | --- | --- |
| Owner / Founder / CEO | Home | Full company access, approvals, coverage, policy, finance, marketing, and AI control |
| Administrator | Home | User support, records, audit, and acquisition administration |
| Lead Manager | Leads > Lead Queue | Warm response, qualification, nurture, and appointment setting |
| Acquisitions Closer | Calendar | Schedule, meeting preparation, property visit, underwriting review, negotiation, and contract |
| VA Caller | Prospecting | Work assigned screened records, dispositions, callbacks, and warm handoff |
| Dispositions Manager / Rep | Deals | Buyer matching, package and outreach preparation, reply review, offers, buyer outcome, and backup |
| Transaction Coordinator | Deals | Contract-to-close checklist, parties, documents, dates, funding, and closing evidence |
| Finance / Accounting | Finance | Revenue, reconciliation, compensation, payment state, and export |
| Marketing Manager | Marketing | Attribution, funnel, source economics, and conversion exports |
| Read-only Partner / Vendor | Deals | Limited deal records needed for the approved engagement |

The Owner can see all navigation. Restricted users should see only the pages required for their
jobs.

A Disposition representative can prepare and manage supervised outreach but cannot approve or
release it. Outreach approval requires the separate approval permission. Release, resume, and
safe-failure retry require both outreach approval and bulk-send authority; the standard Disposition
manager role has both.

Cold calling is also a separate staff capability. An Owner can enable **Cold calling** for a person
in another role, such as Acquisitions or Dispositions, without changing that person's primary
role. The person then receives the Prospecting navigation and can work only calling records
assigned to them unless their primary role already grants management oversight.

## First Sign-In

1. Open `/os`.
2. Sign in with the Clerk account created for your Stonegate user.
3. Wait for the OS to verify the local role and permissions.
4. Confirm the name and role displayed in the account menu.
5. Confirm the navigation matches the assigned job.

If the screen remains on **Verifying access**, sign out and sign in once. If it persists, the Owner
must confirm that the Clerk email matches an active Stonegate user and that the branded web origin
is present in Clerk authorized parties and API CORS configuration.

## Navigation

The desktop sidebar and mobile navigation drawer use four groups and no more than 11 destinations.
The exact list is reduced by role and permission.

### Work

- **Home:** Today's priorities, exceptions, meetings, pipeline pulse, and Executive Copilot.
- **Inbox:** Seller communication timeline and follow-up.
- **Tasks:** Assigned and overdue actions.
- **Calendar:** Month, week, day, and agenda commitments.

### Operations

- **Prospecting:** Campaign preparation, prospect imports, calling work, and warm handoff.
- **Leads:** Warm-lead qualification, seller records, pipeline, follow-up, and underwriting.
- **Deals:** Contract, approval, closing, and disposition entry point.
- **Buyers:** Buyer CRM, criteria, proof of funds, and reliability.

### Business

- **Finance:** Revenue, deductions, compensation, margin, and export.
- **Marketing:** Funnel, attribution, source economics, and conversion exports.

### Administration

- **Settings:** Personal setup, people and access, communications, company policy, and AI controls.

Use **New** to enter a seller lead or compose a company email when authorized. Use each workspace's
local views for focused work: Campaigns, Analytics, and My Calls in Prospecting;
Lead Queue, Pipeline, and Underwriting in Leads; and transaction, disposition, and finance sections
inside Deals. Analytics is manager-only. Native Dialer Control and Pilot Acceptance are dormant.
**My setup** is always available at the bottom of the sidebar. Global search finds authorized
primary workspaces. Recent destinations return to recently opened OS pages. On mobile, use the
menu button to open the navigation drawer. The floating Help button remains at the bottom-right.

### Route Reference

| Workspace | Route |
| --- | --- |
| Home | `/os` |
| Inbox | `/os/inbox` |
| Tasks | `/os/tasks` |
| Calendar | `/os/calendar` |
| Prospecting | `/os/prospecting` |
| Prospecting: Campaigns | `/os/prospecting?view=campaigns` |
| Prospecting: Analytics | `/os/prospecting?view=analytics` |
| Prospecting: My Calls | `/os/prospecting?view=my-calls` |
| Leads | `/os/leads` |
| Deals | `/os/deals` |
| Buyers | `/os/buyers` |
| Finance | `/os/finance` |
| Marketing | `/os/marketing` |
| Settings | `/os/settings` |
| Settings: Company | `/os/settings/company` |
| Settings: Markets & Territories | `/os/settings/markets` |
| Settings: People & Access | `/os/settings/people` |
| Settings: Communications | `/os/settings/communications` |
| Settings: Integrations | `/os/settings/integrations` |
| Settings: Workflows | `/os/settings/workflows` |
| Settings: Data & Quality | `/os/settings/data-quality` |
| Settings: Finance Policy | `/os/settings/finance-policy` |
| Settings: AI & Automation | `/os/settings/ai` |
| Legacy Campaigns redirect | `/os/campaigns` |
| Legacy Team & Access redirect | `/os/operations?tab=team` |
| Legacy Email Management redirect | `/os/inbox?manage=email` |
| Leads: Lead Queue | `/os/leads?view=queue` |
| Closed Leads | `/os/leads/closed` |
| Archived Leads | `/os/leads/archived` |
| Leads: Pipeline | `/os/leads?display=board` |
| Calendar: Appointment | `/os/calendar?view=appointment` |
| Leads: Underwriting | `/os/leads?view=underwriting` |
| Tasks: Needs Approval | `/os/tasks?view=approvals` |
| Legacy Approvals redirect | `/os/approvals` |
| Deals: Transaction work | `/os/deals?view=closing-exceptions` |
| Deals: Disposition Desk | `/os/deals?view=disposition` |
| Disposition case setup | `/os/dispositions` |
| My Setup | `/os/my-setup` |
| Legacy Company & Policy redirect | `/os/operating-model` |
| Legacy AI Control redirect | `/os/ai` |
| Lead Record | `/os/leads/{lead_id}` |

## Home And Global Controls

### Home

Home is a command center, not a replacement for the detailed workspaces. It summarizes:

- overdue and urgent seller work
- unassigned or neglected records
- today's appointments
- offer and transaction exceptions
- pipeline movement
- role-specific workload
- Executive Copilot analysis for authorized management users

To use it:

1. Read the primary exception and recommended next action.
2. Select the linked seller, task, appointment, approval, or downstream record.
3. Complete the work in its detailed workspace.
4. Return to Home and refresh when reviewing the updated company state.

Home may differ by role. A Dispositions employee should not expect the same seller and
finance information as the Owner.

### Global Search

Use the search control in the OS shell to find an authorized workspace or compatibility tool.

1. Enter a workspace or tool name.
2. Select the exact result.
3. Use the destination's own record search to find a seller, property, buyer, or deal.

### Recent Destinations

Recent destinations are shortcuts to records and workspaces opened during the current work
session. They do not change ownership or mark anything read.

### Notifications

Open the notification button in the OS shell to review:

- new assignments and handoffs
- appointments
- overdue response or task escalation
- approval work
- provider or operating exceptions

Select the notification to open its source record. Marking a notification read only clears the
alert; it does not complete the underlying task.

### Account Menu

Use the account menu to confirm:

- signed-in employee
- active Stonegate role
- current workspace access

Sign out before another person uses a shared computer or iPad. Employees may share company
hardware, but they must not share Stonegate or Clerk credentials.

## Recommended Daily Routine

### Owner

1. Open **Home** and review overdue work, unassigned leads, today's appointments, approvals,
   and the Executive Copilot health summary.
2. Open **Inbox > Needs reply** and confirm no qualified seller is waiting.
3. Open **Tasks > Overdue** and assign or escalate blocked work.
4. Open **Calendar** and confirm closer capacity and appointment coverage.
5. Open **Tasks > Needs Approval** and make only evidence-supported decisions.
6. Review exceptions in **Transactions**, **Dispositions**, and **Finance**.
7. Review **Marketing** source economics at least weekly.
8. Review **Prospecting > Analytics** for attributable outcomes, missing evidence, caller quality,
   and retained historical evidence. Never treat an old native readiness label as authorization.

### Lead Manager

1. Open **Leads > Lead Queue** for priority and neglected-lead signals.
2. Open **Today** and accept new warm handoffs before the SLA expires.
3. Complete **Qualification** using the approved questions.
4. Work **Inbox > Needs reply**.
5. Schedule qualified appointments and create the next dated task for every lead not scheduled.

### Acquisitions Closer

1. Open **Calendar > Appointment**.
2. Review the meeting brief, unresolved questions, property facts, and underwriting.
3. Record walkthrough evidence and repairs during the visit.
4. Review the approved offer ceiling before discussing price.
5. Record the meeting and negotiation outcome immediately.

### VA Caller

1. Open **Prospecting > My Calls > Work queue**.
2. Work one assigned record at a time.
3. Follow the displayed approved script.
4. Record every attempt and outcome.
5. Schedule callbacks only when requested or permitted.
6. Complete all required warm-handoff questions before submitting an interested seller.

### Transaction Coordinator

1. Open **Transactions**.
2. Work overdue and due-next checklist items first.
3. Confirm contract approval, documents, closing parties, earnest money, title, and closing date.
4. Attach evidence before completing required items.
5. Escalate any blocker that threatens closing.

### Dispositions

1. Open **Deals**. The Disposition role opens in the **Disposition Desk** by default.
2. Start in **Today** and work the highest-severity owned item first.
3. Use **Active Deals**, **Buyer Follow-ups**, **Replies**, **Offers**, or **Deadlines** when focusing
   on one kind of work.
4. Resolve the displayed blocker through the card's direct action. The action opens the canonical
   Deal, Buyer, Inbox conversation, Task, or disposition control.
5. For a House deal, resolve the Package launch-readiness blockers and review the evidence classes,
   buyer-visible preview, and authorized private economics before building a draft.
6. Approve one exact current package version before ranking buyers or preparing recipients.
7. Verify proof of funds and buyer criteria before recommending placement.
8. In **Outreach**, select only the intended owned-network recipients and eligible channels, review
   the exact rendered message, and create the immutable approval draft. A manager must approve and
   explicitly release that exact revision.
9. Work Buyer Inbox reply-review tasks before recording interest, offers, or follow-up.
10. Present the primary and backup buyer for human approval.

The current package and outreach workflow is House-only. **Prepare recipient pool** records
`prepared_not_sent` recipients but sends no email or SMS. Only the separately approved **Outreach**
revision can queue a message. Do not use this workflow for Land.

### Finance And Accounting

1. Open **Finance** and review pending revenue, reconciliation, journals, bills, and bank
   exceptions.
2. Confirm source evidence before preparing accounting work.
3. Review due vendor and commission obligations.
4. Match imported statement activity only to exact posted cash entries.
5. Work close-readiness blockers before preparing reports.

### Marketing

1. Open **Marketing** and select the reporting period.
2. Review funnel loss, spend without leads, and leads without outcomes.
3. Confirm CRM outcomes before preparing conversion events.
4. Investigate failed or exhausted provider events.
5. Review recommendations without allowing the Copilot to change budgets or campaigns.

## Operations Administration

**Operations** is the acquisition-management workspace. It is normally used by the Owner,
Administrator, or Acquisitions Manager rather than a VA or restricted employee.

Its tabs are:

- **Calendar**
- **Markets & campaigns**
- **Calling lists**
- **Team**
- **Data quality**
- **Follow-up plans**

### Calendar Tab

Use this summary to review upcoming appointments, unread alerts, saved views, calling progress,
and duplicate-review count.

- Select **Open** on an alert to perform the underlying work.
- Select **Mark read** only after understanding the alert.
- Create a saved view for a repeated appointment, calling-list, lead, or Inbox filter.

### Create A Market

1. Open **Settings > Markets & Territories**.
2. Under **Add operating market**, enter a clear service-area name such as `Metro Atlanta`.
3. Confirm the two-letter state and timezone.
4. Select **Add market**. Stonegate creates the internal code automatically.

Do not create a second market just to represent a neighborhood or employee. Use territories and
teams inside the existing market.

### Create A Territory

1. Select the market.
2. Select the assigned team when known.
3. Enter a territory name such as `North Metro`.
4. Enter counties and ZIP codes as comma-separated values.
5. Select **Create territory**. Stonegate creates the internal code automatically.

Territory information supports assignment and closer dispatch. It is not a substitute for
confirming the actual property address.

### Create An Outreach Campaign

1. Open **Prospecting > Campaigns**.
2. Select **New campaign**.
3. Enter the campaign name and stable code.
4. Select the market and optional territory.
5. Select the real channel: cold call, cold email, direct mail, paid search, paid social, organic,
   referral, or other.
6. Select the accountable owner.
7. Enter start date and initial budget.
8. Select **Create campaign**. Stonegate opens the new campaign as the context for imports, costs,
   assignments, history, and reporting.

### Add A Prospect Manually

Use manual prospect entry only when a pre-lead record is not coming from a CSV:

1. Select the campaign.
2. Enter owner name and phone.
3. Add email when known.
4. Select the assigned caller or leave unassigned.
5. Add the source record identifier when one exists.
6. Select **Add prospect**.

A prospect is not a CRM lead. It becomes a lead only through genuine seller interest and the warm
handoff workflow.

### Calling Lists

The Operations calling-list tool supports existing CRM leads. The Campaigns and Prospecting
workflows are preferred for imported cold prospect batches.

1. Create a list and choose its default caller.
2. Select the list.
3. Add a seller and optional different caller.
4. Record the actual disposition and notes after each attempt.
5. Select a handoff owner only when responsibility is genuinely changing.

### Add A User

Adding a Stonegate user does not create the person's Clerk password. It authorizes the matching
individual identity after that person signs in.

1. Open **Team**.
2. Under **Add individual login**, enter the person's real name.
3. Enter the exact email they will use with Clerk.
4. Select the minimum job role needed now.
   Select **Owner / full access** only when the person should have the same company-wide access as
   the primary Owner. Their operational position can still be Dispositions, but their OS access
   role will display as Owner.
5. Select **Create user**.
6. Have the employee sign in with their own Clerk account.
7. Verify navigation and restricted access.

Use **Deactivate** immediately when a person leaves or should lose access. Reassign their work.
Use **Reactivate** only after management confirms the person should return.
For an unused duplicate account, deactivate it and then select **Delete**. Stonegate removes the
account only when it has no operating history. If the person is attached to leads, messages,
contracts, accounting, or other company records, keep the account deactivated so that history
remains accurate.
If the user already exists, change the access-role menu on that person's row instead of creating a
duplicate account.
To correct a staff name, select the pencil beside the displayed name, enter the real name, and save.
This changes Stonegate's staff display name without changing the person's Clerk email or password.

### Create And Staff A Team

1. Enter the team name.
2. Select its function.
3. Select a manager when known.
4. Create the team.
5. Add individual active users as **Member** or **Manager**.

Team membership controls workload, mailbox, and notification behavior in supported workflows. It
does not automatically grant every permission.

### Data Quality

The top valuation ribbons compare two different questions:

- **Underwriting performance** uses later verified outcomes to show ARV error, directional bias,
  range coverage, and tracked markets.
- **Underwriting operating baseline** uses every saved analysis to show run count, median selected
  comps, median comp yield, and median analysis time.

These metrics do not change formulas automatically. Use them to identify thin comp coverage,
operator effort, provider problems, and whether a later methodology actually improves V2.2.

The duplicate section remains a separate workflow. Select **Scan active leads** to prepare possible
duplicate candidates.

1. Compare the two sellers, contacts, and properties.
2. Choose the correct primary record.
3. Merge only when they represent the same seller opportunity.
4. Keep both records when identity is uncertain.

A merge archives the secondary record and preserves evidence. Do not use duplicate merge to hide
bad data or combine unrelated family members.

### Follow-Up Plans

Use a follow-up plan for a repeatable sequence of internal tasks or human-approved message drafts.

1. Create or select the plan.
2. Review each step, delay, channel, and responsible role.
3. Enroll the correct lead.
4. Confirm the enrollment creates the intended work.
5. Stop or correct the plan when the seller's status changes.

Follow-up plans do not authorize messages that the employee or provider is otherwise prohibited
from sending.

## My Setup And Role Acceptance

Open **My Setup** after first sign-in, after a role change, or when a manager assigns a new manual.
This page shows your name, assigned roles, and how many role acceptances are approved.

For each assigned role:

1. Read the displayed role standards.
2. Open the workspaces used in that job.
3. Test normal actions with a training record. Examples include opening an assigned lead, reviewing
   a conversation, creating a follow-up task, or opening a transaction checklist.
4. Confirm restricted workspaces are not visible. A VA, for example, should not see Finance,
   contracts, buyer records, or unrelated seller correspondence.
5. Return to **My Setup**.
6. In **What did you test?**, describe the pages and actions you verified.
7. Add any problem or question under **Notes for your manager**.
8. Select **Submit workspace test**.
9. Wait for manager approval before working live records in that role.

Possible states are:

- **Pending:** The role has been assigned but the workspace test has not been submitted.
- **Submitted:** The employee completed the test and a manager must review it.
- **Approved:** The manager accepted the role setup.
- **Rejected:** Correct the stated problem, repeat the test, and resubmit.

My Setup does not grant access by itself. The Owner controls the actual user role and permissions
from **Team & Access > Team** and assigns role manuals from **Company & Policy > Company setup**.

## Stonegate Help

Select the blue chat bubble at the bottom-right of any OS page when you need instructions.

1. Enter a question about a page, button, setup step, role, or workflow.
2. Select the arrow button or press Enter.
3. Read the formatted plain-language answer. Bold text identifies exact Stonegate controls;
   numbered steps show the order; bullets identify real choices.
4. Ask a short follow-up such as “What if the address does not match?” Help uses the six most
   recent turns in the open panel to understand what “that” or “it” refers to.
5. Select a numbered source inside an answer to open that exact approved source, or select the
   source-count button under the answer.
6. Expand a source to see the exact document, heading, and excerpt.
7. Use the back arrow to return to the conversation.
8. Select **New conversation** when changing subjects or when you do not want the earlier questions
   used as context.
9. Close the panel to continue working on the same page.

Suggested questions change with your role. Help also filters restricted setup, finance,
underwriting, contract, disposition, and administrative topics by your current Stonegate role.
It will direct you to the responsible person instead of explaining a restricted action.

Help summarizes approved manuals when OpenAI is available. If OpenAI is unavailable, it returns
the strongest matching source excerpt. Recent conversation context exists only inside the open
browser panel and is not saved as a CRM or audit record. Earlier messages help interpret a
follow-up but are not treated as documentation. Help cannot read a seller's live record, send
communications, change a stage, approve an offer, post accounting, or perform any other operating
action.

## End-To-End Operating Workflow

The normal deal path and its completion evidence are:

| Stage | Primary workspace | The stage is complete when |
| --- | --- | --- |
| Address-only website capture | Public form, Leads > Address Only | A complete property address exists as a cold record awaiting research and a manual DNC check; this is not yet a contactable seller inquiry |
| Seller inquiry or outreach | Public form, Campaigns, Prospecting | One seller record exists with source, contact evidence, and an owned next action |
| Warm handoff | Prospecting, Lead Queue | The Lead Manager accepted a sufficiently documented handoff |
| Qualification | Lead Queue, Inbox | Required facts are confirmed or marked unknown, and the next appointment or follow-up is dated |
| Appointment | Calendar | The meeting has an owner, time, location, preparation, and recorded outcome |
| Underwriting | Lead record, Underwriting | Comps and repairs were human-reviewed, a version was saved, and warnings were understood |
| Negotiation | Lead record, Approvals | Current offer authority exists and each seller response is recorded |
| Contract | Calendar Appointment, Transactions | The exact approved agreement is fully signed and the completed PDF is retained |
| Closing coordination | Transactions | Checklist, parties, dates, title issues, documents, and funding evidence are complete |
| Buyer placement | Dispositions, Buyers | Package is approved, offers are compared, and primary and backup selections are approved |
| Funded deal | Transactions, Dispositions, Finance | Cleared revenue, deductions, role credits, commissions, and accounting evidence reconcile |

Do not advance a record merely to make the pipeline look current. Advance it when the completion
evidence in this table exists.

## 1. Public Seller Intake

The seller starts from **See My Selling Options** on the public site, then requests a review of the
selling options that may fit the property and situation.

The visible Property step collects only the complete property address:

- One property-address search. Selecting a suggested property fills city, state, and ZIP
  automatically; **Enter address manually** remains available when a suggestion is missing,
  incorrect, or temporarily unavailable. City, state, and ZIP also appear as the seller engages the
  address control so browser-saved addresses can fill the complete address instead of only the
  street.

When the complete address passes validation and the seller selects **Continue**, Stonegate creates
or reuses a cold address-only CRM lead and records Meta `Lead`. It appears under **Leads > Address Only** with
**Skip trace needed**, even if the visitor leaves before supplying contact details. This stage has no
seller name, phone, email, or permission to contact. Each eligible employee receives an internal
**Stage 1 filled** text with the address and a contact-details-pending warning. The record does not
start property research, AI preparation, a conversation, speed-to-lead work, general staff
notifications, or automated seller outreach.

Treat an address-only record as a cold research opportunity, not as a warm inbound seller. Research
or skip trace the owner, then check DNC status manually before any cold call or text. Stonegate does
not perform an automatic DNC check for this record.

The visible Contact step collects:

- Name, required phone number, and optional email. Stonegate follows up by phone by default.
- A passive disclosure explaining that submitting the form authorizes Stonegate to follow up by
  phone or email about the property inquiry and possible selling options.
- A separate optional, unchecked SMS consent box for recurring text messages about the property
  inquiry, appointments, and possible selling options. SMS consent is not saved in browser drafts.
- Marketing attribution and privacy-safe conversion evidence.

When the seller selects **Request My Options Review**:

1. The API validates the request.
2. The system promotes the same address-only record to a completed seller inquiry; it does not make
   a second lead for the same property journey.
3. Duplicate matching checks contact and property evidence from other completed journeys.
4. The system creates or reuses the real seller identity, contact methods, property, lead, and
   conversation.
5. Consent and attribution are retained even when the submission matches an existing lead.
6. Property research, AI preparation, and speed-to-lead work start.
7. Each active staff member with **Text new leads** enabled is queued a separate **Stage 2 filled**
   SMS alert containing the seller contact and property address.
8. Staff sees the completed lead in **All Leads**, **Lead Queue**, **Inbox**, and relevant dashboard
   queues.
9. The browser and server send one deduplicated Meta `Contact` event.

The confirmation offers an unnumbered optional section for desired selling timeline, property type,
condition, occupancy, seller situation, asking price, mortgage balance, repairs, and comments. None
of those details is required. A 24-hour one-purpose token adds those answers to the same lead. This
optional save creates internal evidence but does not send another Meta event.

One intake-attempt ID follows the browser's property journey. Retrying Step 1 returns or updates the
same address-only record; retrying the completed contact submission returns the same completed lead.
If concurrent requests arrive out of order, the completed contact state wins and a late address
capture cannot downgrade it.

Address suggestions use the existing RealEstateAPI configuration and are intentionally fail-open.
Autocomplete failure never disables **Continue** or submission; the seller can enter the complete
address manually, and Stonegate stores the actual state supplied or selected.

The Stage 1 and Stage 2 texts are internal operational messages to employees who separately enabled
that preference. They are unaffected by the website's seller-facing SMS choice and do not create
seller SMS consent. Retrying either form request does not send the corresponding employee text
again.

Use the public form to test seller intake with your own controlled information. Do not repeatedly
submit a real seller to diagnose an internal visibility problem.

## 2. Campaign And Prospect Import

Open **Prospecting > Campaigns**. The selected campaign owns every action in:

- **Overview**
- **Import**
- **Costs**
- **Assignments**
- **History**

### Create And Prepare A Campaign

1. Create or select the campaign at the top of Prospecting.
2. Record the market, list source, channel, budget, dates, and manager.
3. Go to **Import**.
4. For the PropStream contact export containing **First Name**, **Last Name**, **Company Name**,
   **Phone 1-5**, and **Email 1-4**, select **Add contact export preset** once. Use **Add standard
   preset** only for the other PropStream layout containing **Property ID** and
   **Owner 1 First Name**.
5. Choose the measurement cohort. The campaign is already selected.
6. Enter the PropStream export or saved-list identity and the filters used to build the list.
7. Upload the CSV and select the correct vendor-column mapping.
8. Review the preview before saving. It shows contact count, property totals by state, rows outside
   the selected campaign state, and whether each person is untouched, previously contacted, in an
   active conversation, due for callback, or already a CRM lead.
9. Confirm invalid, duplicate, and explicitly suppressed rows are separated from eligible rows.
10. Select **Import reviewed file**. Existing matches receive new source/contact evidence without
    losing prior activity.
11. Record list, VA labor, BatchDialer license, phone-number, and usage costs in **Costs**, linked
    to the cohort when applicable.
12. Export the approved callable list to its matching BatchDialer campaign. Use **Assignments** to
    create a Stonegate calling batch only when the one-by-one contingency workflow is needed.
13. Give each VA an individual BatchDialer Agent login and only the campaigns they should work.

The contact-export preset uses **Company Name** for trusts and companies, then falls back to
**First Name + Last Name** for individuals. It retains up to five ranked phone numbers and four
ranked email addresses, including each phone's Cell or Landline type. A source-marked DNC phone
remains attached as evidence but is not selected for calling; Stonegate uses the first remaining
callable number. One DNC phone does not block the other clear numbers on the same owner record.

Mixed-state files are allowed, but the preview displays a warning. Use separate state-specific
campaigns whenever practical so assignments, performance, scripts, and expansion reporting stay
accurate.

PropStream refreshes are expected to show matched existing rows. This is not a failed import. It
means Stonegate recognized the person or property and preserved the existing history. **Import
history** shows new versus matched counts, relationship state, contact count, source list, and
cohort. The exact same file cannot be imported twice.

Blank DNC data does not require review. Explicit Do Not Contact records and seller opt-outs remain
blocked.

## 3. Prospecting

### BatchDialer VA Prospecting

BatchDialer is the normal workspace for high-volume VA cold calling. Stonegate becomes the source
of truth when the owner is genuinely interested and the warm handoff begins. BatchDialer remains
the authority for raw calling cadence, cold-call DNC, phone-number operations, and ordinary call
results. Do not copy every dial, voicemail, or no-answer into Stonegate.

### Work A BatchDialer Campaign

1. Sign in with your own BatchDialer Agent login. Never share an Owner, Admin, or another VA's
   account.
2. Open only the campaign assigned by the manager and read its current script and lead sheet.
3. Confirm the property and right party before recording seller facts.
4. Select the truthful call result after every call:
   - **Qualified Seller - Follow Up**: use only when the seller is interested and agrees Stonegate
     may follow up. Use the exact approved label and stop redialing the contact.
   - **Appointment Set**: use when an actual time is agreed. Use the exact approved label and stop
     redialing the contact.
   - **Callback**: schedule the callback in BatchDialer. Do not mark it as a Stonegate lead unless
     the seller is also qualified and has agreed to follow-up.
   - **Not Interested**: stop redialing the contact.
   - **Do Not Call**: apply DNC immediately.
   - **Wrong Number**: stop redialing that number.
   - **No Answer** or **Voicemail**: leave it in the BatchDialer cadence.
5. For a qualified seller, complete owner verification, property address, motivation, timeline,
   condition, occupancy, asking price, mortgage or lien context, best callback time, appointment,
   and clear notes before saving the result.
6. Allow the direct sync its normal polling interval, then confirm the qualified seller appears once
   in **Stonegate > Leads** and the staff lead alert is sent. Do not submit the same seller again or
   create a second Lead while the direct worker is processing.
7. If the result is **Appointment Set**, open the urgent **Enter/verify Stonegate appointment** task,
   create the appointment with the real owner, time, type, and location, and confirm the task clears.

Appointments are created and managed in Stonegate. BatchDialer call recordings remain in
BatchDialer until the official API exposes and Stonegate verifies stable recording access; do not
assume that its recording or transcript is available to Stonegate AI.

### Review A Direct BatchDialer Handoff

Stonegate's native browser dialer, softphone, Dialer Control, and Pilot Acceptance are dormant.
They are not another calling path when BatchDialer is unavailable. The direct worker creates the
warm Lead from the eligible provider result; staff must not recreate that handoff manually.

1. Open the new Lead from **Leads**, the staff notification, or the urgent task.
2. Confirm seller identity, phone, campaign, VA, raw result, provider call time, and available notes
   match the BatchDialer record.
3. Correct missing property or qualification facts only from a real source. Do not invent an address,
   consent, motivation, timeline, condition, or occupancy answer.
4. If the property is incomplete, finish the visible data-quality task before running research.
5. If the provider agent did not map cleanly, leave the preserved provider attribution intact and
   escalate the mapping warning; do not discard the seller.
6. For **Appointment Set**, open **Enter/verify Stonegate appointment**, create the real Appointment,
   and confirm the task and warning clear.
7. Continue follow-up, Inbox communication, qualification, underwriting, and pipeline work in
   Stonegate after the handoff.

**Prospecting > My Calls** remains available for separately assigned manual CRM records and
historical native evidence. It does not receive a native dialing lease, and it must not be used to
create a second Lead for a direct BatchDialer handoff.

### Review Prospecting Analytics

Managers use **Prospecting > Analytics** to compare BatchDialer handoffs, paid acquisition,
historical native evidence, operating quality, and attributable business outcomes. The report is
read-only and does not activate the dormant native dialer. Callers do not receive this company-wide
reporting view. Managers without Finance-view (`financials:view`) permission can review operating
evidence, but cost, revenue, and profit values remain hidden.

1. Select the start and end dates. Both dates are included and interpreted in UTC.
2. Optionally narrow the report by source, campaign, cohort, VA/caller, or dial mode, then select
   **Apply filters**. Operating filters apply only where the durable record carries that dimension;
   clear them when comparing an external lead source without it. Use **Reset** to return to the
   original 30-date window and all sources.
3. Review the funnel from entered leads and attempts through human conversations, right-party
   contacts, qualified sellers, appointments, accepted handoffs, signed contracts, and closed
   assignment-strategy transactions.
4. Review **Cost and profit** and **Calling productivity**. A value labeled **Unavailable** means
   required evidence is missing; it does not mean zero.
5. Compare **Native Stonegate**, **BatchDialer**, and **Paid ads** using outcomes all included
   sources can support. **Other** attribution stays separate. BatchDialer, paid-ad, and other raw
   attempt rates can remain unavailable even when their accepted handoffs, contracts, closes, and
   attributed economics are measurable. A paid acquisition later worked in BatchDialer can appear
   in both source rows, so source rows are attribution views and must not be added together.
6. Change **Break down by** to review VA, campaign, cohort, list, or dial-mode scorecards.
7. Review quality, reputation, daily movement, and **Metric coverage**. Coverage identifies whether
   raw attempts, paid hours, provider costs, appointment outcomes, profit attribution, and number
   reputation have supporting records.
8. Open **How these metrics are calculated** before comparing an unfamiliar metric. It states the
   source records, attribution timestamp, and condition that makes the value unavailable.
9. Treat native-readiness blockers as historical evidence or cleanup signals. Escalate an old live
   session, callback, recording, or worker issue through an authorized recovery path; do not reopen
   Dialer Control merely to clear the display.

The same page includes **BatchDialer VA performance** for managers:

- The selected dates define the outbound-call cohort. Appointments, signed contracts, and closed
  transactions show the current outcomes of that cohort as of the report snapshot; they may occur
  after the selected calling period. Recent and older cohorts are not maturity-normalized.

1. Select **Today**, **Last 7 days**, or **Last 30 days**, then optionally select one observed
   BatchDialer agent.
2. Review completed calls, unique contacts, provider-recorded call duration, human-contact rate,
   provider candidates, evidence-verified handoffs, false positives, appointments, contracts, and
   closed transactions. **Candidate** means the VA selected a qualifying result; **Evidence
   accepted** means Stonegate's gate accepted that candidate; **Verified handoff** means the
   accepted call also created a new lead. Later accepted calls on that same lead remain accepted
   but do not inflate the new-handoff total. Duration and unique-contact coverage identify provider
   records that omitted those source values instead of presenting guessed totals.
   For 7- or 30-day views, also read the archive evidence boundary. Dates before the earliest
   archived call may be incomplete rather than true zero-activity dates because the provider sync
   scans a rolling window.
3. Use the hourly and daily views to see when calls occurred. The first/last call and observed span
   are not proof of login time, paid hours, breaks, or continuous work.
4. Under **Identity mapping**, connect each BatchDialer agent to the correct active Stonegate user
   and select **Save mapping**. Never choose a user merely because a name looks similar.
5. Select one agent and choose **Prepare coaching draft** to generate an evidence-cited manager
   review for that exact date range. Review its strengths, concerns, suggested next-shift actions,
   calls to inspect, caveats, and confidence before using any recommendation.
6. Treat the coach as advisory only. It cannot change calls, leads, assignments, campaigns, pay,
   discipline, or employment status. Compare VAs only after considering campaign/list difficulty,
   shift coverage, and sample size.

Any historical **Ready for controlled pilot** status is retained technical evidence only. It does
not make the native dialer Active or Accepted and does not override dormant mode. BatchDialer is
the production calling system.
The selected period identifies when the originating activity entered the cohort: native dial start,
paid/other lead creation, the first durable BatchDialer handoff touch, or BatchDialer lead creation
when no durable handoff exists. A contract or close
completed later remains attributed to that originating work and is shown as of the dashboard
timestamp; it is not silently moved out of its original acquisition cohort. The all-source summary
de-duplicates overlapping source rows. Collected gross revenue and approved-reconciliation company
profit are separate evidence and should not be treated as the same number.

### Historical D10 Single-Line Pilot — Dormant, Do Not Run

The instructions below preserve the former D10 acceptance design for audit and engineering
history. Dialer Control and Pilot Acceptance are hidden in dormant production, and the server must
reject new native sessions, activation, pilot creation/advancement, and acceptance. Do not follow
these steps as an operating procedure. Existing records may be read, rolled back, revoked, or
cleaned up through authorized recovery paths; late signed callbacks remain processable.

The former D10 process used **Prospecting > Pilot acceptance** after D9 was technically ready. It
was an evidence workflow, not an extra dialer on/off switch. The retained description below is
historical only and cannot authorize production calling.

1. Create one pilot by selecting exactly one VA, enabled native campaign, non-overlapping cohort,
   75-to-250-record calling batch, and dedicated prospecting line. Keep the company, campaign, VA,
   line, and release limits at one live line. Set the pilot daily dial cap between 25 and 50
   reservations so a qualifying shift remains possible; reserved provider spend cannot exceed $10
   per VA local date.
2. Add one to ten unique controlled E.164 numbers from active Stonegate staff forwarding profiles.
   Each number must also exist as an eligible test record in this selected calling batch. Attest
   that the external
   BatchDialer list is separate. The direct integration archives supported completed-call records,
   but it does not prove the complete original list membership. The external export/list digest
   therefore remains a named human attestation.
3. Select **Begin controlled-number smoke test** only after the screen shows no starting blocker.
   The pilot enters `smoke_testing`, where the coordinator can reserve only the saved test records.
   Complete answered controlled seller calls with durable call records, canonical recordings, and
   signed seller-child evidence. Refresh the page, select those exact records under **Smoke test**,
   and enter the provider-reported charge and evidence reference for every displayed root and
   seller-child call ID. Valid evidence moves the exact scope to `running`;
   it does not grant other VAs, campaigns, batches, lines, caps, or configurations permission.
   The cost list covers the entire ended smoke stage, including root-only failures, while the
   selected records prove at least one answered, recorded seller call. If smoke exceeds 50
   reservations / 100 provider IDs, roll it back and begin a new controlled pilot. Smoke calls do
   not count toward production-shift volume or time.
4. After every call, open its D10 review. Verify the disposition and any applicable recording,
   transcript, compact notes, callback, DNC action, handoff, and provider-cost evidence. Failed,
   canceled, no-answer, and voicemail attempts must be reviewed too. Only applicable connected
   seller conversations require a recording, completed transcript, and structured notes;
   non-contact outcomes still require an accurate disposition, review, compliance, and cost
   evidence but do not wait for a transcript.
5. After the shift ends, submit the shift review. For every exact root and seller-child provider
   call ID shown, enter the provider-reported charge and the matching usage-export, invoice, or
   call-detail reference. Stonegate rejects missing, duplicate, extra, cross-linked, or ambiguous
   call IDs. A provider-documented `$0` charge is valid; a guessed or unreferenced zero is not. A
   passing shift requires at least 60 minutes of provider-signed right-party conversation time, 25 terminal
   signed seller calls, 100% passed reviews for every reserved attempt, and no lost answer,
   unintended duplicate, stuck session, missing callback, complaint, or unresolved compliance issue.
6. Complete at least three passing shifts on three distinct local dates and at least 75 qualifying
   signed seller calls total. Review every reservation, including safe pre-provider releases and
   root-only provider failures.
7. Name the comparable, disjoint BatchDialer cohort or list, attest that overlap is zero, and record
   an honest comparison summary. The direct API can support only the CDR and campaign evidence it
   actually retrieved; it does not prove list cost or every attempted contact. Leave unsupported
   rates or economics unavailable. It is acceptable for the comparison to be inconclusive; it is
   not acceptable to invent a rate or claim superiority.
8. Exercise the company and campaign switches on a real controlled pilot session, then reach the
   configured daily dial limit, which must be between 25 and 50, and attempt one more reservation.
   The gate passes only when the
   server records the off-then-on switch cycles, stopped/drained sessions, zero live sessions, and
   the actual daily-cap denial. Typed confirmation is not proof.
9. Complete a separate, later rollback rehearsal: pause and re-enable the native campaign with a
   new switch cycle, safely end or drain a real pilot session, verify no live sessions or legs
   remain, preserve immutable attempt/shift reviews, and identify the hashed unworked remainder.
   Then complete a later clean shift. Use **Rollback native pilot** only when intentionally closing
   the pilot and type **ROLL BACK SINGLE-LINE PILOT** exactly. Closing an unstarted draft records
   `cancelled`; closing a started pilot records `rolled_back`, disables its scope, and preserves its
   evidence. This terminal action does not change BatchDialer automatically.
10. Submit for owner review. Only an Owner or Founder/operator can type **ACCEPT SINGLE-LINE
    DIALER** to accept or **REJECT SINGLE-LINE DIALER** to reject, exactly as shown, and provide the
    reason. The server recomputes all evidence before freezing the decision; managers cannot
    override a failed or unknown hard gate.

Leave every historical pilot and attempt in Stonegate. Do not delete evidence. An Owner or
Founder/operator may still use the authorized rollback/revocation path to drain and close an old
scope, but no new D10 pilot may be created or resumed while dormant. BatchDialer is the production
calling system.

An assigned-only caller cannot open another caller's prospect. Enabling **Cold calling** adds the
Prospecting work permission; it does not grant unrelated tabs or override the permissions from the
person's main role. A restricted VA still cannot access underwriting, contracts, transactions,
buyers, Finance, global email recipients, or email administration. Contact an Owner or manager if
the assignment itself is wrong; do not share logins.

## 4. Lead Manager Qualification

Open **Leads > Lead Queue**. Its views are:

- **Copilot**
- **Today**
- **Qualification**
- **Performance**
- **Standards**

### Accept New Work

1. Open **Today**.
2. Select an unaccepted warm lead.
3. Review handoff evidence and due time.
4. Accept the case.
5. If information is materially wrong, return the handoff from the prospecting review flow with a
   specific correction reason.
6. If the person or property is not a valid warm lead, select a rejection type and record the
   specific reason instead of returning it for more VA work.

### Complete Qualification

1. Open **Qualification**.
2. Select the seller.
3. Confirm the lead's **House** or **Land** label before asking qualification questions.
4. For a **House**, ask the approved questions for ownership, decision-makers, motivation,
   timeline, condition, occupancy, price expectation, mortgage or liens, and access.
5. For **Land**, use the Land acquisition profile and ask the displayed open questions for
   ownership and decision-makers, motivation, timeline, price, APN and acreage, access/frontage,
   utilities, survey/boundaries, septic/perc, taxes/HOA, restrictions, flood/wetlands,
   terrain/environmental concerns, prior work, and title/probate/heirs. Do not require House
   condition, room, repair, occupancy, mortgage, or walkthrough fields.
6. Save only seller-supported answers. Seller-reported answers remain separate from provider
   screening evidence, and a source conflict remains open for review.
7. Treat **Ready for valuation review** as qualification readiness only. It is not offer approval.
8. For Land, use phone or video review by default. Schedule an in-person visit only when access,
   terrain, drainage, dumping, boundaries, improvements, seller interaction, or offer risk
   justifies one.
9. Leave unknown facts unknown rather than guessing.
10. Set the next action and due date.
11. Schedule an appointment when the applicable House or Land workflow calls for one.

See `LAND_ACQUISITION_OPERATIONS_PLAYBOOK.md` for the complete Land procedure and evidence rules.

### Use The Lead Manager Copilot

1. Open **Copilot**.
2. Select a work item.
3. Generate the draft recommendation.
4. Review evidence, risks, missing facts, next-action proposal, and message draft.
5. Accept, correct, or reject the recommendation.
6. Perform any seller communication yourself through the approved channel.

Copilot review does not automatically change lead fields or send the draft.

## 5. Inbox And Communications

Open **Inbox**. The three-panel layout is:

- Left: conversation and mailbox views.
- Middle: one chronological timeline and the channel composer.
- Right: contact or mailbox context, property, qualification, next action, owner, watchers, and
  handoff.

Conversation views:

- **Mine**
- **Unassigned**
- **Team**
- **Needs reply**
- **Appointments**
- **Unread**
- **Archived**

Email mailbox groups appear below the general views when the employee can access them:

- **My addresses:** named addresses owned by or granted to the employee.
- **Team inboxes:** department or team addresses the employee may use.
- **Restricted:** private addresses such as accounting that require exact access.

Composer modes:

- **SMS**
- **Email**
- **Call**
- **Note**

The header shows the number of conversations needing replies, overdue, and unread. **Compose**
starts a new company email. **Email ready** opens sender settings or owner administration.
**Refresh** reloads conversations and provider state.

### Work A Conversation

1. Select the conversation.
2. Read the complete timeline before responding.
3. Confirm the people, receiving mailbox, assigned owner, stage, consent, suppression, and next
   task.
4. Select the correct composer.
5. Write or review the message.
6. Send only when the eligibility indicator allows it.
7. Add internal information as a **Note**, not as a seller message.
8. Reassign the conversation when responsibility changes.
9. Create a dated follow-up before leaving the thread.

The timeline keeps SMS, email, calls, recordings, transcripts, internal notes, and provider events
together. Switching composer modes does not hide prior channels.

When a seller texts photos, the inbound item is labeled **MMS** and the photos appear inline in that
same conversation. Select a photo to open the full image, or use its download control to save a
copy. A message that contains only photos still appears in the timeline; it does not need a text
caption. Non-browser photo formats appear as a secure downloadable attachment instead of a broken
preview.

MMS photos remain private to users who can open that Inbox conversation. Stonegate stores its own
copy rather than making the seller's Twilio media link public. After MMS support is deployed, the
communications worker also attempts to restore photos from already-received Twilio MMS events when
Twilio still retains the media, so the seller does not normally need to resend recent photos.

After a live SMS is sent, the open thread quietly refreshes its delivery state for about 30 seconds
so **Queued** normally advances to **Sent**, **Delivered**, **Failed**, or **Undelivered** without a
page reload. If a carrier reports later than that window, select **Refresh** to retrieve the latest
provider state.

### Record SMS Permission Obtained Elsewhere

The Inbox right sidebar and the seller record's Contact panel show **SMS permission: Permissioned**
or **Not permissioned**. If the seller granted or withdrew permission outside the website form, an
authorized employee can document it without creating a second lead:

1. Open the seller in **Inbox** or open the full seller record.
2. In the Contact panel, expand **Edit SMS permission**.
3. Choose **Permissioned** or **Not permissioned**.
4. Choose where the decision came from: phone call, in person, Facebook, seller text, written form,
   or another documented source.
5. Enter a specific evidence note, including when and how the seller communicated the decision.
6. Select **Save SMS permission**.

Stonegate appends the change rather than replacing prior evidence. The source, evidence note,
employee, timestamp, activity event, and audit history remain available for review. Never mark a
seller permissioned based only on possession of a phone number. A carrier-level **STOP** cannot be
manually overridden; the seller must text **START** from that number before SMS can resume.
The saved permission is tied to the phone number shown in the editor; if the primary number changes,
record permission for the new number before texting it.

### Understand Response State

- **Needs reply** means the newest external communication has not received an appropriate company
  response.
- **Due soon** means the configured response target is approaching.
- **Overdue** means the response target passed.
- **Waiting on contact** means Stonegate sent the latest message and no team response is currently
  required.
- **Unread** is personal notification state; another teammate reading the thread does not
  necessarily clear it for you.

Assignment, watchers, team membership, and mailbox grants determine who receives notifications.
When an unanswered thread reaches the owner-escalation threshold, the Owner receives an alert.
Replying or otherwise resolving the wait state clears the associated response alert.

### Handle An Incoming Text

An incoming seller or buyer text is saved in Inbox immediately and marks the thread unread and
needing a reply. When the responsible employee has **Settings > Communications > Text inbound
messages** enabled, Stonegate also texts that employee a minimal alert with an Inbox link. Open the
link and reply from Stonegate; do not reply to the personal-phone alert.

If Stonegate does not recognize the sender, an Acquisitions text creates a reviewable seller lead
with **Address pending**, while a Dispositions text creates a reviewable buyer thread. Rename the
contact and complete the missing information after confirming who sent it. Compliance keywords and
texts from configured employee cellphones are ignored so they cannot create fake leads or alert
loops.

### Send An Email In An Existing Thread

1. Select the conversation.
2. Select **Email**.
3. Choose the appropriate authorized **Stonegate sender**.
4. Confirm the recipient shown by the readiness message.
5. Enter the subject.
6. Select an approved template when useful.
7. Write and verify the body.
8. Open email settings to add CC, BCC, confirm the signature, or save the current subject and body
   as a reusable template.
9. Attach up to the allowed number and size of files.
10. Select **Send email** once.
11. Confirm the timeline shows the outgoing message and provider status.

The system shows only From addresses authorized for the signed-in employee. Selecting an alias
applies its approved signature. A provider **sent** state does not prove delivery; review delayed,
delivered, bounced, complained, failed, or suppressed state when shown.

### Compose A New Company Email

Use **Compose** when Stonegate needs to email a closing contact, buyer, vendor, contractor, or
other person without an existing conversation. Do not create a fake property lead.

1. Select **Compose** in the Inbox header.
2. Select the correct **From** address.
3. Enter one or more **To** addresses separated by commas or semicolons.
4. After entering at least two characters, select a known Stonegate contact suggestion when it
   matches.
5. Enter **Contact name** when useful for a new general correspondent.
6. Add CC or BCC only when the recipients should receive the same business correspondence.
7. Enter a specific subject.
8. Apply a template when appropriate.
9. Write and verify the message.
10. Add attachments.
11. Select **Send** once.

Stonegate creates a general company conversation and opens it in Inbox. Future replies should
return to that thread through the selected receiving alias. General conversations support email
only until they are deliberately connected to another business context.

### Handle An Incoming General Email

An email from a sender who is not already matched to a seller becomes a general company
conversation rather than a fake lead. Open the conversation and use **Handle this email** in the
right panel:

- **Convert to seller lead:** enter the property address. Stonegate reuses the sender contact,
  keeps the complete email thread on the new lead, creates the first follow-up task, and queues AI
  preparation and property research.
- **Link to existing lead:** select the seller already in Stonegate. The messages, attachments,
  and sender email are merged into that seller's canonical Inbox thread.
- **Mark non-lead and archive:** classify vendor, administrative, spam, or other handled mail and
  remove it from active Inbox views without deleting it.

Use **Archived** to review retained mail. Select **Restore to inbox** when a general conversation
was classified incorrectly. Do not convert receipts, account notices, vendors, or unsolicited
mail into seller leads.

### Use Templates And Signatures

- A template supplies reusable subject and body text.
- A signature belongs to the selected Stonegate sender.
- Review every template before sending; placeholders are not proof that the current recipient or
  record is correct.
- Saving a current draft as a template does not send the draft.
- Changing a template or signature does not rewrite messages already sent.

### Add An Internal Note

1. Select **Note**.
2. Write information intended only for authorized Stonegate users.
3. Select **Log note**.

Do not place secrets, full bank information, tax identifiers, or unrelated private data in an
internal note. Use the restricted document workflow for sensitive evidence.

### Log An External Call Or SMS

When an approved employee uses a staff cellphone:

1. Select **Call** or **SMS**.
2. Select **Log call** or the correct inbound/outbound direction.
3. Enter what happened, not a planned script.
4. Save the communication.
5. Create the next task.

Logging a communication does not send a message or place a call.

### Configure Company Phone-Line Ownership

Owners manage department phone-line responsibility in **Settings > Communications**.

1. Find the company-owned number or select **Add line**.
2. Set the department to **Acquisitions**, **Dispositions**, or **Company general**.
3. Select the primary owner and a different fallback owner.
4. Optionally select the department team so future active team members join the line automatically.
5. Choose whether known callers prefer their conversation owner or the line's primary owner.
6. Choose **In order** to ring the owner, primary, team, and fallback sequentially, or **Everyone at
   once** when the first available employee should answer.
7. Under **Staff ring settings**, enter each answering employee's cellphone and enable **Ring
   cellphone**.
8. Confirm **24/7 staff ringing** and choose the missed-call policy.
9. Mark the acquisitions line as the default company line.
10. Select **Save** and confirm the line shows **Ownership ready**.

Stonegate accepts inbound calls and rings the configured staff cellphones at every hour. It removes
inactive users and duplicate targets before ringing up to 10 staff cellphones. With **Everyone at
once**, the first employee to
accept gets the call and all other devices stop ringing. Cellphone recipients hear the department
and press 1 to accept, preventing personal voicemail from taking the business call. Stonegate
records the employee who answers. After an unanswered ring sequence, or when no configured staff
member is available, the selected missed-call policy sends the caller to Stonegate voicemail or
creates an urgent return-call task.

### Place A Call From Inbox

When the seller has a callable number:

1. Open the seller conversation.
2. Select **Call > My cellphone**.
3. Confirm the number and select **Call seller**.
4. Stonegate calls your saved cellphone. Answer and press 1.
5. Twilio connects the seller and shows the Stonegate company number as caller ID.
6. Return to Stonegate, record any additional notes, and create the next action.

Inbound calls to a Stonegate company number are different: Twilio forwards them to the enabled
staff cellphones. The employee presses 1 to accept the business call.

### Review A Call Recording And AI Notes

When recording and transcription are active:

1. Open the call in the timeline.
2. Select **Play recording**. Stonegate securely loads the audio and starts it. The compact player
   supports play/pause, 10-second rewind and skip, scrubbing, elapsed and total time, playback speed,
   mute and volume, and audio download. Starting another call pauses the current one.
   Stonegate remembers the call position and speed for the current browser session only, without
   automatically restarting playback. If loading fails, use **Retry** on the player.
3. Read the automatic call summary. Use **Quick read** at the bottom for the seller's main reason,
   timing, stated numbers, and next step. Stonegate adds the full note to the Inbox conversation,
   seller record, communication history, and recent activity as soon as processing succeeds; no
   approval is required.
4. Open **Full transcript** directly beneath the AI notes to read the complete speaker-separated
   call. Select a transcript timestamp to jump the recording to that moment. Select
   **Download transcript (.txt)** to save a timestamped copy.
5. Review motivation, timeline, condition, occupancy, asking price, commitments, and follow-up
   context when those facts matter to the next action.
6. Call Intelligence immediately fills eligible empty CRM fields supported by the transcript.
   Existing staff-entered values are never overwritten.
7. Correct an inaccurate CRM value in the seller record or add a clarifying internal note. The
   original transcript-grounded summary remains linked to the call for audit.
8. An exhausted job exposes **Retry call intelligence** on the same call after the provider is
   healthy. A suggested next action does not create a task automatically.

Early audio deletion requires a reason. Deleting audio does not erase the call, transcript,
or audit evidence.

### Change Ownership Or Add Watchers

The right panel shows the current owner and queue.

To hand off a seller conversation:

1. Select the new owner.
2. Select the correct queue: VA Prospecting, Qualified, Appointment Set, or Acquisitions
   Follow-Up.
3. Enter a clear reason.
4. Select **Update ownership**.
5. Confirm the thread remains visible to the correct team.

Watchers receive visibility and notifications but do not become responsible for the next outcome.

### Email Administration For Owners

Authorized owners select **Email ready** and open **Email administration**.

**Senders** controls:

- company address and display name
- named, department, or contractor type
- purpose
- active, reserved, or disabled status
- owner and assigned team
- inbound and outbound enablement
- default sender
- signature
- direct sender or watcher grants

Use **sender** access when the person may send from the address. Use **watcher** access when the
person should receive notifications and visibility without sending authority.

**Routing** contains inbound messages Stonegate could not match safely:

1. Review sender, recipients, subject, time, reason, and candidate threads.
2. Search existing records separately when needed.
3. Select the exact conversation only when identity is clear.
4. Resolve the exception.
5. The worker places the message into the selected thread.

Never guess. Leave ambiguous correspondence in review until the correct person or business record
is confirmed. Mail received through a restricted alias can be assigned only to a restricted-
visibility conversation; both automatic matching and manual assignment enforce that boundary.

**Failed events** is a manager-only recovery tab for Resend events that exhausted automatic retry:

1. Read the event, attempt count, and final error.
2. Correct the provider, routing, or data problem first.
3. Enter a specific reason explaining why retry is now safe.
4. Select **Requeue**. Stonegate resets that one event for the worker and records the action in the
   audit log.

Do not repeatedly requeue an unresolved event. Production mailbox behavior and the approved safe-
attachment or malware-scanning procedure must still pass acceptance before email is relied on as
the only channel.

If SMS, Voice, or email reports that it is not configured, use the approved manual contact process
and log the communication. Do not put another company's credentials, campaign, domain, or numbers
into Stonegate.

## 6. Tasks

Open **Tasks**. Saved views are:

- **My Tasks**
- **Do Today**
- **Overdue**
- **Upcoming**
- **Unscheduled**
- **Team** for authorized managers
- **Needs Approval** for authorized reviewers
- **AI Completed** for reviewed AI preparation
- **Exceptions**
- **Completed**

Use search and the owner filter to narrow the queue. Select a row to see its source, owner,
deadline, work type, warnings, and permitted action. **Open source** takes you to the seller,
deal, conversation, calendar, or governed review that created the work.

Supporting tasks can be marked complete after the work is done. For a **Primary action**, select
**Complete and continue**, record what happened, then name and schedule the next action. Stonegate
will not close a primary action without a successor while the seller lead or deal is active. Use
the terminal checkbox only when the source is already closed; the API verifies that state.

Every active seller lead and deal must have one owner, one primary action, and one due date. Team,
Needs Approval and some decision controls appear only when the signed-in role has authority.

New seller leads can also create an assigned AI brief. Open it in **Needs Approval** to review the
summary, recommended next step, missing qualification facts, questions, risks, confidence, and
evidence. **Accept brief** adds a labeled internal note to the seller timeline; **Reject** records
that the draft should not be used. This review never messages the seller, overwrites lead facts,
or replaces the employee's primary next action. Call summaries post automatically in Inbox and the
seller record; they do not create approval work or replace the employee's next action.

## 7. Calendar And Scheduling

The internal Stonegate calendar is the appointment source of truth. No Google Calendar connection
is required.

Use:

- Month view for capacity and coverage.
- Week view for team planning.
- Day view for execution.
- Agenda view for upcoming commitments.

To schedule:

1. Open **Calendar** and select **Schedule appointment**. The same scheduler opens from a seller
   record, the Inbox contact panel, or an empty Calendar day with the seller or date preselected.
2. Choose the seller, meeting format, purpose, start and end time, and assigned team member.
3. Confirm the automatically suggested phone number or property address, add preparation notes,
   and select **Schedule appointment**.
4. If the assigned team member is already booked, change the time or deliberately select
   **Schedule anyway**. The override is retained in the appointment audit history.
5. Confirm the appointment opens in **Calendar > Appointment** and appears in Schedule view.

Calendar blocks cover the saved start-to-end duration. Phone meetings are blue, property visits
green, video meetings purple, office meetings orange, and other meetings gray. Cancelled meetings
remain visible with a faded striped treatment. Each block also includes an icon and text label, so
the calendar never relies on color alone.

Use **Calendar > Dispatch** instead when closer capacity, territory, overlap, travel buffers, or a
manager conflict override must be evaluated before assignment.

Manager override is allowed only for authorized roles and requires a reason.

## 8. Calendar Appointment Execution

Open **Calendar**. Its local views are:

- **Schedule**
- **Dispatch**
- **Appointment**
- **Availability** for authorized managers

### Prepare A Meeting

1. Open **Appointment** and select the meeting.
2. Appointments opened from Calendar or a lead enter **Appointment mode** automatically.
3. Review **Prepare** for seller goals, history, property, unresolved questions, and logistics.
4. Refresh the meeting brief after changing underwriting or comparable sales.
5. Review underwriting and approved authority privately.
6. Generate and review Acquisitions Copilot preparation when useful.

The progress rail shows **Prepare**, **Walkthrough**, **Present**, and **Finish**. Use **Exit focus**
to return to the team meeting queue.

### Record The Walkthrough

1. Open **Walkthrough** on the iPad, phone, or laptop.
2. Confirm occupancy, access, decision-makers, and material property facts.
3. Tap the common property areas, then record condition and notes.
4. Tap a common repair category. Choose **Not sure**, **No**, **Yes, repair**, **Yes, replace**, or
   **Specialist review**, then confirm extent and quantity. Enter an exact amount only when you
   have a better supported number than the system range.
5. Capture photographs by area and add what you observed. Use **Dictate** to append a spoken note
   when the browser supports it.
6. Watch the walkthrough status for **Saving**, **Saved**, or the offline recovery message. The
   iPad retains an unsynced draft locally; reconnect before submitting or uploading more photos.
7. Open **Acquisitions Copilot** and select **Suggest repair scope** when useful. Review the draft
   with **Accept**, **Save correction**, or **Reject**. Accepted suggestions are added as
   unconfirmed rows and must still be checked during the walkthrough.
8. Select **Save now** for an immediate sync, then **Submit walkthrough** when complete. Submission
   first sends the latest on-screen draft and will not proceed while offline.
9. Select **Review and transfer**. Stonegate carries the same verified rows and low/expected/high
   range into one new underwriting draft; it does not overwrite prior approved work.

Submitted inspections and evidence are retained. Correct material errors with a new record rather
than silently rewriting historical evidence.

### Present Market Evidence

1. Open **Seller view**.
2. Confirm the address, recorded-sale count, renovated-value range, and evidence confidence.
3. Review the comparable sales with the seller.
4. Select **Present full screen** before handing over or rotating the iPad.
5. Download the **Client PDF** when a printed or retained copy is useful.
6. Exit the presentation before returning to Stonegate's private offer controls.

Seller view does not display Stonegate's repair budget, offer ceiling, opening position,
assignment fee, buyer profit, or concession history.

### Record Negotiation And Outcome

1. Open **Outcome** after leaving the seller presentation.
2. Confirm the current approved offer authority.
3. Record objections, seller counters, Stonegate discussions, and outcome.
4. Request approval before exceeding the current ceiling.
5. Save the appointment outcome and next action.

The Copilot may prepare questions and follow-up drafts. It cannot present or change a binding
offer.

### Sign An Accepted Agreement On The iPad

The signing panel appears after the outcome is saved as **Accepted**.

1. Confirm every owner is listed as a decision maker and the agreed price is exact.
2. If the panel says the agreement is not ready, open **Prepare exact agreement**. Create, preview,
   and approve the purchase agreement for the same accepted price.
3. Return to the appointment and select **Review PDF**.
4. Enter a separate legal name and email for every owner.
5. Select **Start on this iPad** and hand the device to the person named on the handoff screen.
6. Each seller completes their assigned fields. The Stonegate representative signs last.
7. After completion, take the iPad back and select **Return to Stonegate**.
8. Confirm the signed PDF and audit page appear in the transaction.

Use **Resume signing** if the session was interrupted. Do not create another package or signature
request for the same approved agreement. The seller handoff screen hides the Stonegate workspace
until the device is returned.

## 9. Leads And Seller Record

### Leads

Use **Leads** to work from one seller database. Its local views include **Lead Queue**, **All
Leads**, **Address Only**, **Pipeline**, and **Underwriting**.

1. Select **New Lead** for a warm call, referral, networking contact, or other staff-entered seller.
2. Enter the seller name and at least one phone number or email.
3. Enter the complete property address.
4. Choose the real source, assigned owner, temperature, and next follow-up.
5. Add known motivation, timeline, condition, occupancy, price context, and an initial note.
6. Select **Create lead**. Stonegate opens the complete seller record.
7. Search by seller, property, phone, email, or source.
8. Filter by owner, stage, or saved view.
9. Review status and next action in the local detail drawer.
10. Open the full seller record when deeper work is required.
11. Select **Close out lead** when a real opportunity is dead or disqualified. Choose the
    disposition and record a specific reason.
12. Use **Administrative archive** only for a confirmed duplicate or test record. Never use it to
    remove a real seller opportunity from the pipeline.

When you open **Full record** from a filtered list or Pipeline view, Stonegate remembers that exact
view. Select **Back** in the seller record to return to the same filters and selected seller.

Use **New Lead** only for a genuine CRM opportunity. Cold list records normally belong in Campaigns
and Prospecting as prospects until the seller expresses interest. **Address Only** is the deliberate
exception for valid Property steps abandoned before the website Contact step. Those records are
cold, show **Skip trace needed**, have no Inbox conversation, and are excluded from qualification,
no-follow-up, urgency, and other operational queues until the visitor completes Contact.

For an address-only record, review the property and source evidence, research or skip trace the
owner, and manually check DNC status before outreach. Do not assume the website visitor was the owner
or granted permission to contact. If the visitor later completes the same form journey, Stonegate
promotes that record automatically and normal seller workflows begin.

Closing a lead cancels its open tasks, scheduled appointments, automated follow-up, calling and
handoff work, every pending approval tied to the lead, and unused offer authority. It closes the
Lead Queue case and active Inbox route so routine overdue warnings stop. Active deal, contract, or
disposition work must be cancelled or resolved first. A funded deal is already a completed success
and cannot be closed as dead or disqualified.

The record remains under **Closed** with its saved seller and property facts, calls and internal
notes, recent activity, appointments, valuation versions, transactions, and buyer offers available
as read-only history. To resume work, select **Reopen lead**, explain why, and schedule a future
next action. A genuine inbound seller email, text, or call automatically reopens a closed lead and
creates urgent follow-up work.

Use **Archived** from Leads only to inspect, restore, or permanently remove confirmed duplicate and
test records.

### Pipeline

Select **Pipeline** to switch the same active records to a stage board. Search, owner, selected
seller, and display mode stay in the URL. Pipeline mode clears a single-stage filter so every valid
drop destination remains visible. Use the recommended next action to open Inbox, Lead Queue,
Calendar, Valuation & Offer, Contract & Deal, or the complete record.

If you have lead-edit access, drag the grip on a lead card into another column to change its saved
pipeline stage. On a touch device, press and hold the grip briefly before moving it. The card moves
immediately while Stonegate saves, then displays confirmation. If the save is rejected, the card
returns to its original column and the board refreshes. Select the card and use **Move to stage** in
the seller preview when dragging is inconvenient. Dropping inside the card's existing grouped
column does not rewrite a more-specific stage such as Appointment Scheduled or Offer Presented.

**Offer** and **Under Contract** are workflow-controlled destinations: prepare the offer in
**Valuation & Offer** and complete the signed contract in **Contract & Deal** instead of dragging a
card there. An under-contract card is locked on the board so an active deal cannot be moved out of
sync. Staff without `leads:edit` can view and select pipeline cards but cannot move them.

Move a stage only when the corresponding real-world event occurred. Stage movement does not
replace qualification, approvals, or evidence.

### Lead Record

The full lead record has seven sections:

- **Summary:** Primary next action, tasks, qualification, recent activity, contact, and controls.
- **Activity:** Unified communication, appointment, consent, attribution, and workflow history.
- **Property:** Address validation, seller/property facts, and qualification editing.
- **Valuation & Offer:** Comps, repairs, versions, PDFs, offer authority, and negotiation.
- **Appointments:** Appointment history, scheduling, outcomes, and related tasks.
- **Contract & Deal:** Transactions, contracts, and buyer offers.
- **Files:** Links to generated valuation reports and transaction document workspaces.

Use the lead record when you need the complete evidence chain. Use focused workspaces for daily
queue execution.

The Contact panel also shows the latest **SMS permission** state. Authorized staff may append a
grant or revocation with its real source and a required evidence note; the Activity and audit
history preserve each change. A seller's **STOP** remains blocked until that seller sends
**START**.

In **Property > Property Intelligence**, use the property map to confirm the general location,
pan or zoom around the neighborhood, and select **Recenter** to return to the saved property pin.
Select **Open directions** to start a route in Google Maps. The embedded map uses coordinates
already saved by property research, so viewing it does not spend another RealEstateAPI or RentCast
credit. If **Map location pending** appears, validate the address and then use **Refresh research**;
Stonegate does not guess coordinates or substitute Street View or satellite imagery.

### Edit A Lead

1. Open the seller's full lead record.
2. Select **Edit lead** in the record header. Stonegate opens the canonical editor in the
   **Property** section.
3. Update the seller name, property, source, qualification, price context, follow-up preference,
   or lead owner as needed.
4. Under **Phone numbers and email addresses**, edit an existing contact method or select **Add
   phone** or **Add email**. Use **Primary** to choose the number and email Stonegate should use
   first. Use the trash button to remove an incorrect method.
5. Select **Save lead**.

At least one phone number or email address must remain on the lead. Add the replacement before
removing the only contact method. Changing the lead owner also reassigns its conversation, open
tasks, and upcoming appointments and records the handoff in assignment history. Change the sales
stage separately under **Summary > Record controls** so ownership and pipeline progress remain
independent decisions.

## 10. Underwriting And Comp Analysis

Open **Leads > Underwriting** to choose an active valuation case. Detailed analysis is
completed in the seller record's **Valuation & Offer** section. Calibration and provider-quality
controls are in **Settings > Data & Quality**.

### Before Analysis

Confirm:

- Correct subject address.
- Property type, bedrooms, bathrooms, square footage, and year built when known.
- Occupancy and current condition.
- Known repairs and renovation assumptions.
- Seller asking price and mortgage context when available.

### Run Market Analysis

1. Open the seller record's **Valuation & Offer** section.
2. Read the four-stage bar: **Quick Comp**, **Desk Review**, **Walkthrough**, and **Offer
   Decision**. The highlighted stage is the next stage supported by the saved evidence. Select a
   stage to jump to its existing analysis, appointment, or approval workspace.
3. If **Highest-value missing facts** appears, correct those facts before relying on the result.
   Stonegate limits this strip to the three most useful missing facts so it does not become another
   questionnaire.
4. Confirm the property panel contains the correct complete address and known subject facts.
5. Open **Comp setup**.
6. Choose **Repair scope**: Light cosmetic, Moderate renovation, Heavy renovation, or Structural /
   full rebuild.
7. Choose a remodel estimate method:
   - **System:** Use Stonegate's size and scope estimate.
   - **Total:** Enter one expected base remodel amount.
   - **Itemized:** Use the guided Georgia scope. Select **Apply preset** for a starting point or
     assess only the categories you know. For each category choose Unknown, No work, Repair,
     Replace, or Specialist review. Stonegate estimates a low, expected, and high cost from the
     saved quantity and catalog version.
8. Adjust quantity or scope when the property facts justify it. Open **Evidence and override** to
   record who observed the issue, confirmation status, notes, or a known manual amount. A manual
   amount requires a reason and does not erase the original system range.
9. Leave an uncertain item as **Unknown** instead of No work. Unknown items add a visible allowance
   and widen the repair range; they do not block the analysis or PDFs.
10. When using Total or Itemized, set the contingency reserve and explain the estimate source under
   **Repair details and source notes**.
11. Save the current guided scope as Internal scope or Walkthrough scope when it should become
   reusable evidence. Select Contractor bid only when written contractor pricing has been entered.
   Applying any saved estimate uses that immutable evidence in the next analysis.
12. Open **Verified manual sales** only when you know a legitimate closing that RentCast missed.
   Enter the complete address, closed date and price, property type, square footage, verification
   source and reference, and clear verification notes. Add condition evidence before calling a sale
   As-is or Renovated. Save the record and leave its checkbox selected when it should enter the next
   analysis.
13. Select **Run Stonegate valuation** for the first result. Afterward, the same button reads
   **Update Stonegate valuation** and recalculates from the saved same-address market evidence with
   zero paid provider calls. Select **Refresh market evidence (may use credits)** only when you
   intentionally need a newer snapshot or provider retry; review the capture time and source-cost
   audit first.
14. Review **Repair range**, **Unconfirmed work**, and each item to
   verify before discussing an offer. The expected scenario drives current offer math; low/high
   scenarios explain repair uncertainty.

The right-side **Current decision** panel stays visible on desktop and stacks on smaller screens.
Use it to keep ARV, repair range, buyer target, opening recommendation, and seller ceiling distinct.
Its links open the existing reports, appointment or scheduling flow, offer approval, and Contract &
Deal signing flow. Open **Advanced records** only when comparing versions or preserving a manual
scenario.

Stonegate first requests the exact address from RentCast. If that lookup fails or returns the wrong
property, Stonegate tries normalized address variations and a matching property record. If the
provider has a matching subject but no AVM, the system can still use its recorded-sale evidence.
The **Subject match** status and resolved address show which property was used. Stop and correct the
record if that address is not the subject property.

When the owner has enabled RealEstateAPI underwriting in **shadow** mode, Stonegate retrieves an
exact-match Property Detail profile and standard comp set, records estimated credits, and compares
it with RentCast without changing ARV. In **candidate** mode, unique RealEstateAPI closed sales may
enter the same screen as other provider sales. A transfer returned by both providers appears once
with both source badges;
material price, date, or property-fact conflicts remain visible and require review. Small
recording-date, coordinate, or rounding differences remain visible as minor provider variances but
do not reduce confidence or force review. A different RealEstateAPI subject address is rejected.

Ordinary valuation updates reuse the saved RealEstateAPI result even when it is old, failed, or had no
match; they do not retry a paid call in the background. The provider panel shows zero current-run
credits on reuse while retaining the original source credits and latency. A failed call whose final
billing response was unavailable is labeled with a conservative estimated credit count. Use the
explicit refresh control when a retry is worth the potential cost.

Foreclosures, quitclaim/gift/family transfers, sheriff/tax sales, corrective transfers, and nominal
consideration are shown only for audit and cannot be included in value math. A sale whose
arm's-length status is unavailable is labeled unverified and should be checked against deed/MLS or
closing evidence before approval.

Stonegate searches closed sales in controlled levels:

1. **Preferred:** Tight physical match within 0.5 mile and 180 days.
2. **Expanded:** Up to 1 mile and 365 days using the normal V2.2 physical limits.
3. **Extended:** Up to 3 miles and 730 days with bounded additional size and age tolerance.
4. **Manual / researched:** The provider search ended without enough market-area support, so
   verified operator-entered sales or cited AI research supplemented it. Stonegate states exactly
   what was added; it does not insert a listing or AVM as a fake closed comp.

The search stops when at least three screened sales meet the available market-area check. When the
subject subdivision and comparable subdivision data are available, Stonegate also seeks at least
two selected sales from the same subdivision. Wider-query duplicates are removed automatically.

Stonegate also uses bounded internet research to corroborate the exact address, property facts,
prior sales, permits, visible condition clues, and likely nearby closed sales.
This research:

- Shows its sources and conflicts in **Secondary public evidence**.
- Can add a sale to the working comp set only when address, closed price/date, living area, and a
  consulted source are present. One-source sales receive less weight than corroborated sales.
- Cannot provide ARV, repair cost, offer amount, owner identity, or private contact information.
- Does not replace deterministic screening or human comp review.
- May be unavailable without preventing the primary analysis from running.

Stonegate also saves nearby active asking prices and ZIP listing statistics under **Supporting
listings and ZIP market context**. Use them to understand current competition and seller questions,
not as proof of a closed value. They never enter ARV, buyer-maximum, or offer calculations.

### Review The Result

Review the result from top to bottom:

1. Confirm **Subject match** and the resolved address.
2. Confirm **Core valuation evidence** contains usable recorded sales.
3. Open **Closed-sale search**. Confirm where the search stopped, which levels ran, how many unique
   sales remained, and whether subdivision or market-area warnings exist.
4. When the final level is **Manual**, read the manual verified count, evidence shortage, and next
   action. Open each manual comp's source link/reference and verify the closing and condition.
5. Review **Stonegate valuation adjustments**. The displayed ARV is the live result from these
   adjusted closed-sale indications. **Supported** means the local pair threshold passed;
   **Withheld** means Stonegate applied zero dollars rather than guessing. If the evidence is too
   weak, Stonegate stops for manual review instead of substituting another method.
6. Review **What is driving this range**. Stonegate uses the weighted middle distribution of the
   adjusted closed-sale indications without adding a generic provider or confidence envelope.
   Resolve unknown condition, wide adjusted-sale dispersion, expanded-market comps, withheld
   adjustments, large extrapolations, and provider conflicts when shown.
7. Open **External benchmarks** only when comparison context is useful. RentCast and RealEstateAPI
   estimates in this section are excluded from ARV and offer math. Older saved analyses may retain
   a clearly labeled legacy DealMachine benchmark.
8. Use **Comp Copilot** to ask what is lowering confidence, which comp needs attention, what
   condition evidence is missing, or why the supported range is wide. Its thread is saved only to
   the currently displayed immutable analysis. Open each citation before acting. Suggested-action
   buttons take you to the applicable comp review, condition review, micro-market view, or refresh
   control; they do not change data. When the separate **AI Comp Analyst draft** is present, review
   its structured include/exclude/review suggestions the same way. Neither feature can change the
   comp set, set a weight, confirm condition, calculate a price, or approve an offer.
9. Open **Why this confidence score** and read every factor.
10. Open **Secondary public evidence** and investigate any conflict.
   Review every **AI-discovered closed sale** link before using a material number with a seller.
11. Open **Supporting listings and ZIP market context**. Confirm these records are labeled as asking
   prices and supporting-only evidence.
12. Review the comp-supported as-is indication (or **Not comp-supported**), ARV status and range,
   total rehab, buyer maximum, seller contract
   ceiling, and opening recommendation.
   **Working guidance** means only two usable sales were available; confidence is capped and another
   sale should be verified before final offer approval.
13. Read every item under **Resolve before approval**.
14. Review each comparable:
   - Keep the **Subject property** band visible as the comparison baseline. Correct the lead or run
     a new analysis if its physical facts are wrong.
   - Use **All**, **Included**, **Excluded**, grade, search-level, address/subdivision, and sort
     filters to focus the list. Filters never remove a sale from the saved review decision set.
   - Confirm it is a real recorded sale.
   - Compare property type, location, distance, sale date, size, bedrooms, bathrooms, and price per
     square foot.
   - Read its A-D grade and Preferred, Expanded, Extended, or Manual search label. A grade describes
     fit, not whether the property was renovated. Manual sales cannot receive an A or B grade.
   - For a Manual sale, open the source and read the reference, verification notes, and condition
     evidence. Source verification proves the closing record, not that it is a suitable comp.
   - Investigate subdivision and extended-search warnings instead of ignoring them.
   - **System pick** and **System excluded** show the engine's original recommendation. **Reviewer
     changed** means the draft inclusion choice differs from that recommendation.
   - Mark **Condition at sale** as As-is, Renovated, or Unknown based on evidence.
   - Include or exclude it and choose the truthful **Decision reason**.
   - Adjust **Evidence weight** only when the record deserves more or less influence.
   - Open **Evidence and rationale** for the engine reason, condition support, warnings,
     verification notes, and source link.
   - Use **Location** to open the road map, recenter on all plotted evidence, select a numbered pin,
     and compare the subject with selected and excluded sales. The side list remains synchronized
     with the pins. A green ring means Renovated, an amber ring means As-is, and a gray ring means
     condition is Unknown. The map uses already-saved coordinates, does not spend a provider
     credit, and is not a parcel, school-boundary, or neighborhood-boundary map.
   - Use **Restore system set** only to return inclusion choices and weights to the engine's saved
     recommendation; it does not erase condition classifications.
15. Select **Apply review and recalculate**. This creates a new analysis and preserves the original.
16. Repeat until the included set and assumptions reflect the evidence.
17. Create a manual underwriting version only when an authorized person must preserve a separate
    judgment or scenario.
18. Open **Advanced records** and compare saved versions before requesting offer approval. The
    comparison shows headline dollar changes plus comps added or removed, repair categories that
    changed, search reach, catalog version, and adjustment support.

To correct a saved manual sale, select **Remove** and create a new verified record. Removal voids it
for future analyses; it does not alter an analysis or PDF that was already saved.

The range is decision support, not an appraisal or guaranteed offer. A result remains visible when
renovation status is unconfirmed, but confidence and warnings should affect judgment.

**Preliminary ARV** means the available recorded sales have not been verified as renovated
comparables. **Conservative ARV** means renovated recorded-sale evidence supports the range. The
provider AVM is shown only as an external benchmark and never replaces insufficient closed-sale
support or enters offer math.

### Use The Result In A Seller Meeting

On the iPad, open **Calendar > Appointment** and select the appointment. Use the market
evidence view to discuss the property and the reasons behind the range. Keep these numbers
distinct:

- **ARV:** Supported resale value after the assumed renovation.
- **Repairs:** The expected renovation budget plus contingency.
- **Buyer maximum:** What the best modeled investor strategy may support.
- **Seller contract ceiling:** Stonegate's maximum under the current evidence and economics.
- **Opening recommendation:** A negotiation starting point, not permission to exceed the approved
  ceiling.

Record new condition facts from the walkthrough, refresh the analysis when they materially change
repairs or comp selection, and obtain new approval when the governing underwriting version changes.

### Reports

After a completed analysis:

- Use **Investor PDF** for internal review, agents, lenders, buyers, and detailed value debate.
- Use **Client PDF** for a cleaner seller discussion with appropriate explanations and
  disclosures.

The Investor PDF contains Stonegate's acquisition math, seller ceiling, complete repair evidence,
and market-supported adjustment evidence. The Client PDF contains seller-safe value evidence, preparation
assumptions, comp fit, search reach, unresolved work, and source context; it intentionally excludes
buyer economics, assignment assumptions, negotiation recommendations, and internal ceilings.

Review every report before printing or sharing. Confirm seller, property, comparable, repair, and
offer information is current.

The PDF buttons are available even when renovation status is not confirmed. Warnings and
preliminary labels remain in the report so the reviewer can see what still needs verification.

### Calibration

After verified evidence becomes available, record the actual benchmark in Underwriting, including
actual rehab when known. Mark every validation scenario the case represents: dense market,
suburban, rural, unique property, low comp count, wrong-address recovery, provider-failure
recovery, or high-risk repairs. These labels measure cohort coverage; they do not change the saved
valuation. Open **Settings > Data & Quality** to review range coverage, point error, market bias,
comp yield, operator overrides, AI repair-scope corrections, and catalog repair error.

The segment table groups verified cases by property type, search level, comp grade, repair category,
verification stage, and repair catalog. One case may appear in multiple grade or repair-category
rows because one analysis can use several comp grades and repair categories. Small samples identify
questions to investigate; they do not justify changing formulas. Do not increase dependence on the
comp engine until real-deal calibration and the governed human decision are acceptable.

Stonegate presents one live valuation method. Verified outcomes measure its real-world accuracy by
market and evidence type. V2.2 exists only as an engineering rollback and is not a staff choice;
offer and contract authority remains human-controlled.

## 11. Offer Approval And Negotiation

1. Save the underwriting version used for the decision.
2. Create the offer plan with opening, target, stretch, and seller ceiling amounts.
3. Provide the rationale and seller context.
4. Submit for approval.
5. The authorized reviewer opens **Tasks > Needs Approval** or the lead's Underwriting tab.
6. The reviewer confirms the version is current and evidence supports the ceiling.
7. Approve or reject with decision notes.
8. Record every price discussion and seller counter.
9. Request a concession approval before raising the offer beyond current authority.
10. Record what was actually presented and how the seller responded.

A newer underwriting version makes older authority stale. Generate a new offer plan instead of
reusing stale approval.

## 12. Reviews And Approvals In Tasks

Open **Tasks > Needs Approval** for governed and AI decisions visible to your role. Without
`audit:view`, the feed shows only approval types covered by your permissions; `audit:view` is the
only blanket approval-read authority and still does not let you decide a request. The old
`/os/approvals` address redirects here.

1. Select the request.
2. Read the title, summary, due state, source record, and consequences.
3. Select **Open source** to inspect required evidence.
4. Approve, reject, or cancel only if your role has authority.
5. Add specific decision notes.

Typical requests include offer ceilings, concessions, contract sends, and AI capability
promotions. Call summaries are not approval requests; they post automatically with their
transcript and audit link. Some requests can be decided directly in Tasks. When complete source
evidence is required, Tasks intentionally sends you to the originating workspace for the decision.

An approval does not prove the underlying real-world event happened. For example, funding still
requires funding evidence.

## 13. Contracts And Transactions

When a seller is ready for an agreement, open **Deals** and select the property. Deals is the
normal employee workspace from contract preparation through funding.

Use the saved views to find the correct work: **Active**, **Closing Exceptions**, **Ready for
Disposition**, **Buyer Needed**, **Finance Review**, or **Completed**. Use the queue for daily
work, the table for comparison, and the board for a milestone overview. Selecting a deal opens one
record with separate Contract, Closing, Disposition, and Finance status so parallel work does not
overwrite another department's progress.

The record's **Summary** section shows the one primary next action, its owner and due date, all
active blockers, closing evidence counts, buyer status, and only the economics your role may see.
Use the remaining record sections for the actual work. The old Transactions route remains an
authorized compatibility tool, not a second record system.

The Transactions workspace has:

- **Closing**
- **Contract**
- **Documents**
- **Parties**
- **Timeline**

### Contract

1. Confirm the transaction has a current approved offer plan, approved underwriting version, and
   seller-agreed/current purchase price, then select or create the contract package.
2. Select Purchase Agreement, Assignment Agreement, or Contract Addendum and confirm the seller,
   property, price, dates, and terms.
3. Select **Preview PDF** and review the exact agreement before approval.
4. Submit the package for human approval.
5. Confirm SignWell shows Account and Webhook as connected. Owners can select **Connect SignWell**
   or **Verify connection** in this area.
6. Confirm SignWell is connected. Stonegate generates the signing PDF internally.
7. Enter the seller or assignee name and email. Add a second seller when needed. Stonegate adds the
   signed-in company user automatically.
8. Select **Send for signature** only after the exact package version is approved. If the source
   offer, underwriting version, price, seller agreement, or governing concession changed, create a
   new package instead of bypassing the stale-authority warning.
9. Track recipients under **Signature requests**. Use **Refresh status** if a provider update is
   delayed.
10. Confirm the completed provider PDF appears in Documents before continuing closing work.

For an accepted in-person appointment, use the signing panel in **Calendar > Appointment >
Outcome** instead of the email form. Both methods use the same approved package, signer records,
provider status, completed PDF, and audit trail.

Until production SignWell acceptance is complete, use the controlled manual execution workflow.
Upload the exact package as a **Fully executed signed copy**, link it to that package, verify every
required signature, and use **Attest executed** with the required explanation. Never mark a
contract executed merely because a draft was approved or an email was sent.
See `SETUP_REFERENCE.md` for SignWell account setup and production acceptance.

### Closing

1. Assign the Transaction Coordinator.
2. Set closing, due-diligence, earnest-money, and other dates.
3. Work required checklist items in dependency order.
4. Attach evidence before marking an item complete.
5. Track title, payoff, probate, liens, access, assignment, buyer deposit, and attorney items.
6. Confirm funding evidence before marking funded.

### Documents

Upload the appropriate file, classify it, and confirm extracted facts against the actual source
page. The file room shows the storage and malware-scan state for each document. Raw documents
remain private and are not automatically trusted by AI.

### Parties And Timeline

Maintain the closing attorney, seller, buyer, coordinator, and other approved parties. Use the
timeline for immutable transaction events and escalation history.

### Transaction Copilot

Generate a draft to identify missing documents, deadline risk, party gaps, and proposed
coordination messages. Accept, correct, or reject it. Review does not send email, alter deadlines,
complete checklist items, or mark closing funded.

In the canonical Deal record, open the Transaction Copilot from Contract, Closing, Documents,
Parties, or Timeline. It opens in a drawer so the source evidence remains available after you close
the assistant.

## 14. Buyers And Dispositions

### Disposition Desk

Open **Deals**, then select **Disposition desk**. The URL is `/os/deals?view=disposition`.

The desk has six views:

- **Today**: overdue or due-today work, buyer replies, new offers, imminent deadlines, and weak
  buyer coverage.
- **Active Deals**: every active disposition case in scope, including package and coverage blockers.
- **Buyer Follow-ups**: scheduled deal-specific buyer follow-up records.
- **Replies**: buyer Inbox conversations that have unread messages or need a response.
- **Offers**: received offers awaiting human review.
- **Deadlines**: contract, closing, checklist, buyer POF, and offer-deposit dates that still require
  attention.

**Mine** is the default scope. If **Team** appears, use it only when reviewing the active
Dispositions team's workload; it does not change ownership or assignment. Owner-level users may see
the organization scope. Each card states the owner, due time, reason, blocker, and next action.
Select that action to complete the work in its source record rather than re-entering it on the desk.
When a queue contains more than 100 items, use **Previous** and **Next** in the queue notice; the
total remains the full scoped count rather than the number shown on the current page.

The buyer-network health strip summarizes active and review-needed relationships, missing or
expiring proof, missing criteria, and unassigned buyers. Deal coverage warnings explain when a
package is not ready, a deal lacks enough matched buyers or offers, or a selected buyer lacks backup
coverage. An external-provider warning does not mean the owned Buyer Network is unavailable.

Use **Add buyer** for a new relationship. Use **Open deal** for package, matching, follow-up, offer,
or deadline work. Use **Open reply** for the actual buyer conversation. Refresh the page if the
desk reports stale data; cached owned records remain usable when an outside provider is unavailable.
The route shows a loading state during navigation. If Stonegate cannot verify your access profile,
the standard Deal queue stays readable where possible but editing and disposition navigation are
visibly disabled until the profile reloads.

### Buyer CRM

Open **Buyers**.

The Buyer Network list is searched and filtered on the server. Search by the buyer identity or
contact information; use the **Status**, **Relationship owner**, and **Source** filters to narrow the
list. Use the pagination controls to continue through the full database. Clearing a filter restores
the broader result set; it does not delete or change buyers.

Select a buyer, then use **Summary**, **Criteria & Markets**, **Active Deals**, or **Proof &
Capacity**. The selected buyer and section stay in the page URL. On a phone, selecting a buyer
opens the record as a full-height drawer; use the close button to return to the buyer list.

For each buyer, maintain:

- Contact and company information.
- Lifecycle status and why the buyer is or is not currently usable.
- Relationship owner, source, and last verified date.
- Markets, counties, property types, price range, and strategy.
- Cash or financing capacity.
- Proof-of-funds status and expiration.
- Reliability and prior activity.
- Notes and relationship history.
- The latest call and SMS permission decision and its factual source.

Expired or missing proof of funds should reduce selection confidence.

#### Add A Buyer

1. Search the Buyer Network first. Do not assume a spelling difference or a different company name
   means the person is new.
2. Select **Add buyer**.
3. Enter the buyer's name and at least one usable phone number or email address. A name alone is not
   enough to create the record.
4. Enter the company, relationship owner, source, source reference when available, and facts that
   have already been verified.
5. Save the criteria that the buyer actually stated. Do not infer markets, price capacity, or
   strategy from one inquiry.
6. Review the duplicate check. If a matching phone or email belongs to an existing buyer, select
   **Use existing** and update that profile.
7. Select **Create separate** only when the contacts truly represent different buyer records, then
   enter a specific reason. Stonegate records the override. It never silently merges the records.
8. Review the new **Needs Review** profile before changing its lifecycle status.

Stonegate does not currently provide a buyer-merge action. If two records represent the same
buyer, use the existing record and pause or archive the unnecessary duplicate according to the
record's history. Never create a separate record merely to avoid correcting the existing one.

#### Buyer Lifecycle

| Status | Use it when | Matching behavior |
| --- | --- | --- |
| **Needs Review** | The record is new, incomplete, imported, or awaiting contact/criteria verification | Excluded |
| **Active** | Identity, contact path, relationship state, and usable buying criteria have been reviewed | Eligible for future matching |
| **Paused** | The buyer relationship is retained but should not receive current opportunities | Excluded |
| **Do Not Contact** | The buyer opted out or Stonegate has another documented contact restriction | Excluded |
| **Archived** | The record should leave normal working views while its history is retained | Excluded |

Only **Active** buyers are eligible for future matching. Status is not a quality score: do not mark
a buyer Active solely to make a disposition match appear.

#### Edit And Verify A Buyer

1. Open the buyer and select **Edit buyer**.
2. Correct identity and contact details, company, relationship owner, source, and last verified
   date from factual evidence.
3. Update criteria when the buyer gives new guidance. Each criteria save creates another version;
   it does not erase the prior criteria record.
4. Record call or SMS permission only from evidence. Include the source and any available note;
   later permission changes remain in history.
5. Save the profile. Stonegate synchronizes the canonical buyer contact and linked Inbox
   conversation so staff do not have to create another thread.
6. Confirm the status still represents the relationship. Move the buyer to **Active** only after
   the review is complete.

Changing a phone number or email does not transfer permission from a different contact method.
Document the permission that applies to the contact path being used.

#### Archive Or Restore A Buyer

Use **Archive buyer** to remove a buyer from normal working views without deleting relationship,
criteria, permission, Inbox, offer, or deal history. Use **Restore buyer** when the record should
return to review, then verify the displayed lifecycle status before making the buyer Active.

Imported and provider-created buyers display their available provenance. Treat that data as a lead
for review, not as verified buyer criteria or permission. InvestorLift synchronization and outreach
are not active. Maintaining a buyer, changing status, or preparing a recipient does not send
anything; only a separately approved and released House **Outreach** revision can contact selected
buyers through Stonegate's Resend or Twilio configuration.

### Disposition Case

Open the property in **Deals**, then select **Disposition** after the seller contract is executed.
For an existing case, the embedded tabs are:

- **Package**
- **Buyers**
- **Outreach**
- **Offer Room**
- **Reconciliation**

If the record says disposition has not started, use **Open disposition setup**. This opens the
specialist setup route where an authorized user creates the first case. Return to Deals afterward;
the new case will appear in the same Deal record.

### Package

The current Package workspace is for contracted **House** deals only:

1. Confirm the frozen compensation plan and disposition operating mode.
2. Review **Launch readiness**. Resolve every blocker; review warnings, unknowns, freshness,
   conflicts, and the provided remediation link before continuing.
3. Review **Classified evidence**. Stonegate separates **Verified fact**, **Seller statement**,
   **Provider signal**, **Stonegate analysis**, and **Unknown** so an unsupported claim is not
   presented as fact.
4. Compare the buyer-visible preview with the permission-gated private economics. Purchase basis,
   minimum acceptable amount, desired assignment fee, approval authority, and private notes must
   never be copied into the public preview, summaries, or investor PDF.
5. Select **Build draft**. If a prior version exists or saved material evidence changed, select
   **Rebuild draft**. Each draft is a separate immutable version tied to its source fingerprint.
6. An authorized approver selects **Approve vN**, records why the version is ready, checks the
   evidence attestation, and selects **Approve exact version**. A stale version cannot be reused;
   rebuild and reapprove it.
7. Use **Download approved vN PDF** or the version-history **PDF** action. Stonegate serves the exact
   PDF saved at approval, not a new document generated from later changes.
8. **Refresh buyer ranking** and **Prepare recipient pool** require the current evidence to match
   the approved version.

Preparation binds each recipient to that exact version and stored artifact hash. Its status is
`prepared_not_sent`: **Prepare recipient pool** sends no email or SMS. The separate **Outreach** tab
uses this reviewed pool for governed House delivery. Land package readiness and outreach remain
blocked.

### Buyers

Use Stonegate's existing Buyer CRM first:

1. Select **Refresh buyer ranking** after the package is approved.
2. Review market, property, capacity, reliability, proof-of-funds, and evidence.
3. Exclude ineligible or unsupported buyers.
4. Upload and verify proof of funds when required.
5. Record inquiries, showings, follow-up, and deposit activity.

When DealMachine is configured, **External buyer intelligence** adds deal-specific candidates:

1. Confirm the expected paid plan, billing-cycle reset, and available credits are visible.
2. Select **Preview search cost**. The preview validates the request without consuming credits.
3. Review the matching-property count and maximum property/contact credit estimate.
4. Select **Run buyer search** only when the estimate is acceptable.
5. Compare the actual credit summary with the preview, then review the ranked candidates, observed
   purchase count, no-mortgage signal, last purchase date, market, property type, and available
   contact information.
6. Check only the candidates worth keeping.
7. Select **Import selected**.
8. Review the imported buyer in the Buyer CRM and complete missing criteria or proof information.
9. Refresh the case's buyer ranking.

The search does not send outreach and does not automatically add every result. Candidates remain
outside the Buyer CRM until a person approves their import. DealMachine is disabled and is not part
of the current launch plan; maintain buyers manually unless the Owner deliberately reactivates the
legacy adapter and completes a new provider-quality, billing, permission, and production acceptance
test.

### Outreach

Use **Outreach** only after the current House package is approved and **Prepare recipient pool** has
created the reviewed owned-buyer pool:

1. Read every readiness blocker. Do not work around a stale package, missing prepared campaign, or
   missing recipient pool.
2. Select the exact buyer recipients. Choose email, SMS, or both only when that contact path is
   available and appropriate. The hard limit is 25 recipient-channel deliveries per revision; email
   plus SMS to one buyer counts as two.
3. Choose an active Resend sender for email and an active Dispositions buyer-relations Twilio line
   for SMS. A normal buyer profile change or Inbox message is not a substitute for this sender
   selection.
4. Enter or review the exact email subject/body and SMS body. The bounded merge fields may use the
   buyer name, company name, public property address, and package reference. Never paste purchase
   basis, minimum acceptable economics, desired assignment fee, approval authority, seller notes,
   or unsupported claims into buyer-visible copy.
5. Create the immutable review revision, then inspect every recipient, destination, channel,
   rendered message, exclusion reason, package/PDF identity, and delivery count.
6. An authorized approver refreshes if anything changed, records a meaningful reason, affirms the
   attestation, and approves the exact hash-bound revision. Approval alone does not send it.
7. The authorized releaser records a reason and explicitly releases the revision. Release checks
   buyer status, destination, suppression, SMS permission, sender, package currency, and provider
   readiness again before queueing.
8. Watch the per-recipient delivery states. Use **Pause** to stop unsent work, **Resume** only after
   resolving a temporary blocker, **Cancel unsent** to abandon remaining work, and **Retry failed**
   only when the manager control says the failure is safely retryable. Never retry a
   `delivery_unknown` SMS manually just to make its status move.
9. Open the linked Buyer Inbox conversation when a reply arrives and complete the reply-review task.
   Stonegate does not automatically accept an offer, select a buyer, or treat an ambiguous reply as
   interest.

This workflow reaches only owned Buyer Network records in the current House disposition case.
InvestorLift and Land outreach remain disabled. Repository implementation does not establish real
Resend/Twilio acceptance; the owner must complete a controlled, capped production test before broad
use.

### Offer Room

The Offer Room is available for a contracted **House** disposition case. Open the Deal, select
**Disposition**, then select **Offer Room**.

1. Select **Record offer** and save the buyer's amount, earnest money, deposit deadline,
   due-diligence period, contingencies, proposed closing, funding method and confidence, proof of
   funds, special terms, and notes. Use factual terms from the buyer; do not infer missing terms.
2. Use **Revise offer** when a material term changes. Enter why it changed. Stonegate creates a new
   immutable revision instead of replacing the prior evidence.
3. Record counters, retrades, buyer messages, and internal negotiation events in **Negotiation
   history**. This history does not itself change or accept the offer.
4. Compare the offer cards. Review price, proof coverage and expiration, deposit strength, closing
   compatibility, contingencies, funding confidence, buyer reliability, risk flags, strengths, and
   execution score. The highest offer is not automatically the strongest executable offer.
5. A user with buyer-selection approval chooses one primary and at least one backup from a different
   buyer, records a decision reason, and approves the selection. Other disposition staff can record
   and compare offers but cannot activate the choice. The system and Copilot never select a buyer.
   Any later revision to a selected offer makes that reviewed slot stale; compare the current terms
   and approve a new coverage version before promotion, assignment delivery, or funding.
6. Review **Closing protection** after selection. Transaction closing and relevant title, access,
   and closing-checklist dates are canonical and must be changed in the Deal's Transaction sections.
   The selected buyer's deposit deadline remains tied to the offer. Add buyer-response, agreement,
   signature, or other deal-specific milestones in the Offer Room when needed.
   Deposit completion requires substantive evidence. Only a manager may record a documented deposit
   waiver, and a waiver does not silently change the buyer's approved offer terms.
7. When an alert appears, review the actual source evidence. Acknowledge it to record that someone
   owns the response; acknowledgement does not complete or erase the missed deadline. Complete the
   milestone, change the canonical source, or use the governed replacement control as appropriate.
8. If the primary buyer cannot perform, an authorized manager chooses an eligible ranked backup and
   records the prior buyer's outcome, cause, reason, details, and evidence. The original selection,
   checkpoints, and offer remain in history.
9. Use **Record outcome** for a pass, withdrawal, fallout, or retrade. Choose the factual cause.
   Seller, title, property, Stonegate, and external causes do not reduce the buyer's reliability.
   Buyer-responsible failures and retrades do. Do not use a buyer cause merely because the deal did
   not close.
10. Record the funded close in the Transaction workspace. Funding records the completed buyer close
    automatically and exactly once. For an assignment, Stonegate requires the current approved
    buyer selection, an assignment bound to the selected buyer and reviewed offer economics, the
    matching assignee signer identity, executed assignment evidence, and buyer-deposit evidence or
    a documented manager waiver before funding. If the primary buyer or terms change, create and
    execute a new assignment version; the old agreement cannot move through later contract gates.

The Offer Room preserves viable unselected offers for replacement review. After a backup is
promoted, qualify and approve new backup coverage if none remains. Land Offer Room, Land outreach,
and InvestorLift synchronization are not active.

### Disposition Copilot

Generate draft package guidance, buyer ranking explanation, outreach copy, and offer comparison.
Review restricted economics carefully. Accept, correct, or reject the draft. The Copilot does not
send campaigns, select the buyer, or change deal economics.

For an existing case, open the Copilot from the Deal record's **Disposition** or **Finance**
section. It uses the same reviewed recommendation record as the specialist compatibility route.

**Prepare recipient pool** records which approved recipients may receive the exact approved package,
including the observed identity and destination, as `prepared_not_sent`. It sends no messages.
Governed delivery occurs only through a separately reviewed, approved, and released House
**Outreach** revision. Land package release and outreach remain blocked.

### Reconciliation

After funds clear:

1. Record collected revenue.
2. Record deal-specific deductions.
3. Confirm role credits.
4. Calculate Adjusted Deal Margin and compensation under the frozen plan.
5. Resolve missing credits or below-target company margin.
6. Obtain owner approval.
7. Export the approved accounting statement.

## 15. Finance

Use 30-day, 90-day, or all-time reporting periods.

Review:

- Collected and pending revenue.
- Deal deductions and acquisition reserve. The reserve is operating-margin math, not a ledger
  expense unless Stonegate incurred a real cost.
- Adjusted Deal Margin.
- Compensation calculations and payment state.
- Company net and margin.
- Reconciliation exceptions.
- Accounting export readiness.
- Finance Copilot analysis.
- Books and Tax Setup, including legal entity, federal tax classification, accounting method,
  books start date, owner-compensation treatment, and the active chart of accounts.
- Tax and Deductions Copilot drafts, missing business-purpose notes, and unresolved evidence.
- Accounting Ledger balances, open-period state, draft journals, approved journals, posted
  journals, reversals, and exact source evidence.
- Posting and Payment Control, including versioned rules, source readiness, evidence exceptions,
  payables, reimbursements, distributions, and source-linked journal drafts.
- Vendors, Bills, and Private Evidence, including contractor W-9 status, itemized invoices,
  approved payables, receipts, and year-to-date vendor payments.
- Financial Statements, including Profit and Loss, Balance Sheet, Cash Flow, Trial Balance,
  General Ledger, receivables, payables, payment history, deal profitability, close readiness, and
  the CPA export package.

Only funded, reconciled proceeds should create earned commissions. Keep projected, earned,
approved, payable, paid, reversed, and disputed states distinct.

The Finance Copilot has two financial review capabilities. **Finance and Accounting Review**
reviews funded-deal economics, commissions, the posted ledger, statements, posting candidates,
possible bank matches, variances, and close blockers. **Tax and Deductions Review** reviews
recorded costs, proposes classifications, and identifies missing evidence for the owner or tax
professional. Neither capability can approve commissions, alter records, promise that an item is
deductible, approve or post journals, match bank lines, close periods, move money, file returns,
make final tax classifications, or change compensation policy.

### Finance Copilot Review

1. Select the reporting period in Finance and run the current financial reports.
2. Open the Finance Copilot and select the financial review capability needed.
3. Generate a draft. The deterministic review runs even when the model provider is unavailable.
4. Check every material statement against its source-record, journal-line, bank-transaction,
   statement, or close-check citation.
5. Treat a posting item as a candidate only. Prepare the real draft through **Posting and Payment
   Control**, then use the normal journal approval and posting workflow.
6. Treat a bank match as a candidate only. Stonegate proposes one only when exactly one unused
   posted journal has the matching cash amount; a person still decides the match.
7. Do not accept an explanation for a variance unless the cause is supported by recorded evidence.
8. Accept, correct, or reject the Copilot draft. The decision is retained without changing any
   accounting record.

The performance strip reports the last 30 days of generated and reviewed drafts, correction and
rejection rates, blocked outputs, model latency, model cost, and estimated review time saved.

### Accounting Ledger

Use **Prepare manual journal** only after the underlying revenue, expense, owner activity, or deal
event has been recorded and supporting evidence is available.

1. Select the entry date and source type.
2. Add the source record or document reference.
3. Enter a clear memo and evidence references.
4. Add at least two lines using the approved chart of accounts.
5. Confirm total debits equal total credits.
6. Prepare the journal.
7. A user with approval authority reviews the accounts, amounts, source, and evidence.
8. A user with posting authority posts the approved journal while the period is open.

Draft and approved journals are unfinished accounting work. Posted journals are permanent. To
correct a posted journal, select **Prepare reversal**, document the reason, then approve and post
the reversing journal through the same workflow. Never create an unrelated offset merely to hide
an error.

### Accounting Periods

- **Open:** Journals can be prepared, approved, and posted.
- **Review:** Posting pauses while the month is reviewed; unresolved journals remain visible.
- **Closed:** The month is complete. Reopening requires a recorded reason.
- **Locked:** The period is permanently protected from reopening in the operating workflow.

A period cannot close while draft or approved journals remain. Closing and locking do not replace
bank reconciliation, month-end evidence, or CPA review.

### Posting And Payment Control

Use this workspace for normal accounting work created from Stonegate records. It is preferred over
manual journal entry because it keeps the journal tied to the exact operational source.

1. The owner reviews each draft posting rule and selects **Approve rule**.
2. Stonegate lists collected revenue, deal costs, marketing spend, approved commissions, and
   approved obligations in the source queue.
3. A funded-deal item becomes ready after the transaction is funded, reconciliation is approved,
   and both the closing statement and funding confirmation are uploaded.
4. Select **Prepare draft**. Stonegate chooses the approved accounts, balances debit and credit,
   links the source, and prevents a second draft for the same accounting event.
5. Review the resulting journal in **Accounting Ledger**, then approve and post it under the normal
   journal workflow.

For a bill, contractor payment, reimbursement, or owner distribution, expand **Add payable,
reimbursement, or owner distribution**. Enter the payee, amount, account, due date, business
purpose, and evidence reference. Move an approved obligation to **Payable** when it is authorized.
After the real payment occurs outside Stonegate, select **Record paid** and enter the bank, check,
or transfer reference plus evidence. Stonegate records the state and prepares the settlement item;
it never sends the payment.

Commission payouts follow the same approach: approved, payable, then paid. Commission accrual and
commission payment are separate accounting events, so the commission expense is not recorded
twice. Owner distributions use the equity account and are never treated as ordinary expenses.

If an amount, status, or evidence set changes after a draft is prepared, Stonegate shows an
exception. Review and correct the linked journal rather than creating an unrelated duplicate.

### Vendors, Bills, And Private Evidence

Use this workspace when Stonegate receives an invoice or needs to keep a contractor, receipt,
W-9, or proof of payment.

1. Expand **Add vendor** and record the contractor or service provider. Select
   **Tax-reportable contractor or vendor** when W-9 tracking is needed.
2. Expand **Upload private evidence**, select the vendor, choose **W-9**, and upload the file.
   The vendor changes to **W-9 received**. After a permitted person reviews it, select
   **Verify W-9**.
3. Expand **Enter bill**. Add one line for each real cost category rather than combining unlike
   expenses. For example, contractor labor and calling software should use separate lines.
4. Upload the invoice and link it to the draft bill.
5. Review the vendor, dates, line coding, amount, and evidence. Select **Approve** only when they
   agree. Stonegate creates one payable in Posting and Payment Control.
6. Prepare and review the itemized accrual journal through the normal posting workflow.
7. Pay the vendor outside Stonegate. Upload the receipt or payment confirmation, then record the
   payment reference through Posting and Payment Control.

Stonegate records and audits the payable; it does not send money. Never place a Social Security
number, employer identification number, bank number, or other tax identifier in vendor notes.
Keep that information only in the restricted W-9 document.

### Bank Statements And Reconciliation

1. Add the company checking account or card using its label and last four digits. Do not enter
   credentials or a full account number.
2. Export a CSV statement from the bank. In **Preview CSV statement**, map the exact date,
   description, and signed amount headers. Balance and transaction-ID columns are optional.
3. Review the preview. Stonegate shows valid, duplicate, and invalid rows before it stores the
   private statement.
4. For each cleared operating line, select the posted journal with the exact same operating-cash
   movement. Use **Ignore** only for a non-operating line and provide a clear reason.
5. Prepare the reconciliation with the statement dates and opening/closing balances. Approval is
   available only when the difference is zero and every included line is resolved.

Stonegate does not connect to the bank, initiate payments, or decide matches automatically.

### Financial Statements And Month Close

1. In **Statements, close, and CPA handoff**, select the first and last date for the period.
2. Select **Run reports**. Only posted journals affect the statements. Draft or approved journals
   remain unfinished work and appear in the close checklist.
3. Review Profit and Loss and Balance Sheet first. Balance Sheet and Trial Balance must both show
   **Balanced**.
4. Expand **Trial balance** to compare total debits and credits.
5. Expand **General ledger** to inspect the exact journal, account, memo, source, and evidence count
   behind the report.
6. Expand **Receivables, payables, and payments** to review pending proceeds, approved vendor and
   commission obligations, completed payment records, and deal-coded profitability.
7. Resolve every close blocker: unfinished journals, missing bank reconciliation, unmatched bank
   transactions, or an open accounting period. Missing evidence is a warning that should be fixed
   before CPA review.
8. Use the Accounting Ledger period control to move the month to **Review**, finish adjustments,
   then **Close** it. Lock only after the final outside review is complete.
9. Select **Download CPA package**. The ZIP contains the manifest, financial statements, trial
   balance, general ledger, receivables, payables, payments, and deal-profitability files.

Opening balances and CPA adjustments are entered as manual balanced journals with a clear source
type, date, explanation, and evidence. They follow the same prepare, approve, and post workflow as
every other journal. The report screen never edits ledger data.

## 16. Marketing

Use 30-day, 90-day, or all-time reporting periods.

Review:

- Page views, offer starts, form starts, Step 1 address leads, Step 2 contact-completed leads,
  address-to-contact rate, errors, and abandonment.
- Leads, contracts, and collected revenue by source and campaign.
- Marketing spend, cost per address lead, cost per contact-completed lead, cost per contract, and
  return on ad spend.
- Spend without leads.
- Leads without contracts.
- Advertising measurement mode and Google/Meta readiness.
- Prepared qualified lead, appointment, signed contract, and funded-deal outcomes.
- Queued, retried, delivered, blocked, or exhausted conversion events.
- Marketing Copilot analysis.
- Public reviews, seller stories, completed purchases, and statistics awaiting review.

Select **Prepare conversion events** after CRM outcomes have been updated. Stonegate creates only
new records tied to a captured Google or Meta click; selecting it again does not duplicate the same
outcome. **Process next event** appears only when simulation or live delivery is enabled. Normally
the worker processes due events automatically.

Open the attributed lead when a record needs review. `Credentials pending` means the internal
queue is working but Stonegate has not activated that provider. `Blocked` means configuration is
missing, `Retry` means another attempt is scheduled, and `Exhausted` requires an owner to review
the provider error before retrying operationally.

For Meta website measurement, `Lead` is the valid complete-address capture and `Contact` is the
completed name/required-phone/optional-email submission. The two events have separate deterministic
IDs, with browser and server copies deduplicated inside each event. Optional post-confirmation
details do not create another Meta event.

Drill into source records before changing spend. The Marketing Copilot may recommend tests but
cannot change budgets, audiences, ads, or campaigns. Preparing or delivering outcomes never edits
the lead, transaction, revenue, accounting, ad budget, campaign, or creative.

### Run A Controlled Homepage Test

Use this workflow only when Stonegate has enough live website traffic to compare one CTA wording
change. It does not require another provider account.

1. Open **Marketing > Conversion experiments**.
2. Select **New test**.
3. Enter a stable lowercase experiment key, a plain-language name, and one testable hypothesis.
4. Choose the primary outcome. **Qualified lead** is the normal starting point because it filters
   out low-quality submissions without waiting as long as a funded deal.
5. Leave the current CTA as Control and enter one Test CTA. Do not change other homepage content
   during the test unless the same change applies to both versions.
6. Set the minimum sessions per version, minimum runtime, and decision rule. The system enforces a
   minimum of 20 sessions per version and seven active days.
7. Select **Create draft**, reopen the draft, verify every field, and select **Start test**.
8. While it runs, review assigned sessions, device mix, submissions, qualified leads,
   appointments, contracts, funded deals, and collected revenue.
9. Select **Pause** if a version is misleading, broken, or creating a seller-experience problem.
   Existing evidence remains intact.
10. When the report says **Ready for human review**, apply the written rule. Select **Complete
    test** and record what Stonegate decided and why.

Assignment is anonymous until the Property step creates an address lead. At that capture, the
experiment follows the same record through Contact completion and the rest of the CRM. The system
prevents one browser session from changing versions and never automatically declares or publishes a
winner.

### Publishing Public Proof

The public-proof library is below the website funnel section. Published proof can appear on the
homepage; drafts and review records never do.

1. Select **New proof**.
2. Choose Review, Seller story, Completed purchase, or Statistic.
3. Enter the exact approved public wording. For a review or story, use only the name, initials,
   location, and details the seller allowed Stonegate to publish.
4. Add the original public source URL or an internal evidence reference such as the signed release,
   transaction record, funded statement, or dated report.
5. Set the permission status and explain where permission is recorded. Reviews and stories require
   **Granted** permission.
6. If the person has any employee, family, contractor, incentive, or other material connection,
   record the connection and write the disclosure that sellers will see.
7. For a statistic, enter the public label, value, as-of date, and a reproducible calculation
   method.
8. Select **Create draft** or **Save draft**.
9. Select **Submit for review**. Stonegate checks for source evidence and blocks sample or
   placeholder proof.
10. Verify every public word against the source, then select **Publish**. The homepage can take up
    to five minutes to refresh.

Select **Unpublish and edit** before correcting live proof. Select **Retire** when permission is
withdrawn, a statistic becomes stale, or Stonegate should no longer use the record. Both actions
remove it from the public feed while preserving evidence and audit history.

Never invent a review, ask AI to write a seller's testimonial, condition a benefit on positive
sentiment, or publish a company total without a dated calculation.

## 17. Company & Policy

The Owner uses **Company & Policy**. Tabs are:

- **Company setup**
- **Active policy**
- **Pending decisions**
- **Policy history**
- **Market launches**

Use it to:

1. Install and maintain operating seats, coverage, and backups.
2. Add and verify closing and operating partners.
3. Assign role manuals and decide employee workspace tests.
4. Review the active compensation plan and company-margin target.
5. Resolve role-credit decisions.
6. Review historical policy versions.
7. Configure human-led or AI-assisted disposition modes.
8. Complete market-specific launch evidence.
9. Approve a launch only after every required item is supported.

Policy changes are effective-dated. They do not rewrite historical deal economics.

## 18. AI Copilots

Copilots live inside the human workspace they assist:

| Copilot | Location | Current authority |
| --- | --- | --- |
| Lead Manager | Lead Queue | Draft and recommend |
| Prospecting | Prospecting | Priority, preparation, and reviewed coaching |
| Acquisitions | Calendar Appointment | Meeting and follow-up drafts |
| Transaction | Deal > Contract or Closing | Coordination drafts |
| Disposition | Deal > Disposition | Buyer and package guidance |
| Finance | Finance | Aggregate analysis and recommendations |
| Marketing | Marketing | Aggregate analysis and recommendations |
| Executive | Home | Operating brief and decisions |

### Standard Copilot Review

1. Select the relevant real work item.
2. Generate the recommendation.
3. Verify each material statement against linked evidence.
4. Review uncertainty and risks.
5. Edit incorrect or incomplete content.
6. Accept, correct, or reject.
7. Perform the approved human action in its normal workspace.

Do not paste secrets, unrelated seller data, or unsupported facts into an AI request.

## 19. AI Control

Only authorized owners use **AI Control**. Views are:

- **Copilots**
- **Runtime**
- **Automation**
- **Portfolio**
- **Evaluations**
- **Traces**
- **Governance**

### Copilots

Install and review the role-facing copilot contracts. Confirm each has a named human owner,
retained human authority, approved capabilities, evidence rules, escalation, and prohibited
actions.

### Runtime

Install the governed runtime, inspect model routes, budgets, read-only tools, knowledge scopes,
provider state, and circuit breaker. Use **Emergency stop** when provider, policy, privacy, or
quality risk requires immediate shutdown.

### Automation

Select **Install controls** once after AI10 deployment. Four simulation-only policies appear:

- Consented seller acknowledgement.
- Appointment reminder.
- Consented seller follow-up.
- Approved buyer campaign.

For each policy:

1. Review the named owner, provider, capability, audience, consent, template, contact, frequency,
   volume, cost, quality, canary, pause, and rollback rules.
2. Select **Approve control contract** only when the contract itself is correct.
3. Select **Run readiness simulation** to record current blockers.
4. Use **Pause policy** for any concern.
5. Use **Resume controls** only after reviewing the pause reason.

Approval and simulation do not activate sending. The current release has no delivery endpoint.

### Portfolio And Evaluations

Use Portfolio to inspect specialist engines, prompts, tools, risk, and autonomy. Use Evaluations to
approve redacted datasets, run model replay, compare results, and enforce quality thresholds.

### Traces And Governance

Review model runs, evidence, tool calls, cost, failures, and human decisions. Flag unsafe or
unsupported traces. Governance contains source precedence, approved knowledge, data-quality rules,
promotion history, and rollback.

Never promote a capability using another capability's results.

## 20. Records, Audit, And Corrections

Material actions create activity or audit evidence. Preserve history:

- Correct a lead through an authorized edit.
- Create a new underwriting version when assumptions change.
- Create a new offer plan when authority becomes stale.
- Create a correction attempt for a returned VA handoff.
- Add a transaction event instead of rewriting history.
- Reverse or dispute a financial record instead of deleting a paid state.

Archive is preferred over deletion when a record has operating history.

## 21. Notifications And Ownership

Ownership identifies the person responsible for the next outcome. Watchers receive visibility
without becoming the owner.

Reassign when responsibility changes:

- VA to Lead Manager after warm handoff.
- Lead Manager to Closer for field execution when appropriate.
- Acquisitions to Transaction Coordination after executed contract.
- Transaction and Dispositions remain separate responsibilities on the same deal.

Always create the next task during a handoff. A stage without an owner and dated next action is an
operating exception.

## 22. Troubleshooting

### Navigation Is Missing

- Confirm sign-in completed and the account is not stuck on **Verifying access**.
- Sign out and sign in again.
- Confirm the Stonegate user is active and has the intended role.
- Hidden pages may be correct for the role.
- The Owner should inspect `/api/v1/me` logs only when role verification fails.

### API Or Workspace Shows Unavailable

- Check whether the API health endpoint is returning `200`.
- Wait for a Render deployment or migration to finish.
- Refresh after the API is healthy.
- Do not resubmit seller forms repeatedly to fix an OS authorization problem.

### Seller Form Returns A Validation Error

- Review required fields and field-level messages.
- Use a valid phone and complete property address.
- The phone/email authorization is passive text on the Contact step; there is no required contact
  permission checkbox. The separate SMS choice is optional.
- Retry after correcting the highlighted field.
- A `201 Created` API log means the lead was accepted even if the browser later showed a UI error.

### Lead Was Submitted But Is Not Visible

- Search **All Leads** by phone, email, seller, and property. If only Property was completed, open
  **Address Only** and search by property address; there will be no seller name, phone, or email yet.
- Check whether duplicate matching reused an existing active lead.
- Confirm your role can view the lead.
- If OS requests return `401`, fix Clerk authorization before submitting another lead.

### SMS Is Blocked

Possible reasons include:

- Twilio is not configured or enabled.
- No approved Stonegate sender is attached.
- SMS consent is missing.
- The number is invalid.
- STOP or company suppression exists.
- Contact-hour or frequency policy blocks the action.
- The user lacks permission or assignment.

If permission was obtained by phone, in person, Facebook, seller text, or a written record, use
**Edit SMS permission** in the Inbox right sidebar or seller Contact panel and save the source plus
a specific evidence note. Do not override a seller's **STOP** or company suppression, and do not
use another business's Messaging Service. Only a new **START** from the seller can restore a
carrier-level STOP.

### Voice, Recording, Or Email Is Unavailable

Read the provider status in Settings first.

- **Email ready** means Resend sending and inbound routing are available.
- **Email unavailable** or a setup message means an owner must inspect the Resend connection,
  domain, sender alias, webhook, or recipient route.
- Voice forwarding remains unavailable until its Twilio provider settings, active company line,
  and staff cellphone destinations pass acceptance.

Log approved communication manually in Inbox when a provider is unavailable. Recording must remain
off until market authorization, access, retention, and deletion settings are approved.

### An Email Went To Spam

- Confirm the sender uses the verified `stonegatehb.com` domain.
- Confirm SPF and DKIM remain verified in Resend and DMARC is published for the domain.
- Use a real display name, clear subject, normal text, and a complete signature.
- Avoid test-like content, excessive links, all caps, and repeated identical messages.
- Ask the recipient to mark a legitimate message as not spam.
- Review Resend delivery events. Stonegate cannot force a recipient's mailbox provider to place a
  message in the inbox.

### An Email Reply Is Missing Or In The Wrong Inbox

- Open **Inbox** and check **My addresses**, **Team inboxes**, **Restricted**, **Unread**, and
  **Needs Reply**.
- Search by sender address, subject, or contact name.
- Confirm the recipient replied to the same Stonegate address that sent the message.
- Owners should open **Senders** and confirm that address has inbound enabled and the intended
  owner or team.
- Open **Routing** and verify the inbound rule.
- Check Resend webhook delivery and API logs before creating another conversation.

### Compose Email Is Unavailable

- Confirm email status is ready.
- Confirm your role has global email compose permission.
- Confirm at least one active outbound sender is granted to you or your team.
- Ask the Owner to inspect **Inbox > Senders** rather than creating a fake property lead.

### Underwriting Analysis Fails

- Confirm the lead has a complete address.
- Confirm the subject facts and property record are correct.
- Read **Subject match** and any address attempts when a partial result exists.
- Correct a misspelled street, city, state, or ZIP before retrying.
- Check RentCast configuration and quota.
- A missing saved analysis appears as `404` when the page first loads and is normal.
- A failed provider request may appear as `502`; read the structured warning to distinguish an
  address-not-found response from quota, credentials, timeout, or provider outage.
- Do not keep generating analyses for the same incorrect address.

### SignWell Or Contract Controls Are Unavailable

- Confirm an approved contract package exists for the selected transaction.
- Confirm the exact package version has not been replaced by a newer draft.
- In **Transactions > Contract**, inspect Account and Webhook status.
- Owners can use **Connect SignWell** or **Verify connection**.
- Confirm every recipient has a valid email and the assigned signer role is correct.
- Use the controlled manual process until provider acceptance is complete. Do not mark a draft as
  executed.

### DealMachine Buyer Search Is Unavailable

- The subscription is purchased; this message now means the API key, provider setting, account
  credit balance, or production redeploy still needs attention.
- Continue using the internal Buyer CRM and manually maintained criteria.
- When configured, confirm the provider panel says live search is enabled before previewing cost.
- Provider candidates are not buyers in Stonegate until a person selects and imports them.

### A Buyer Cannot Be Saved Or Does Not Appear In Matching

- A new buyer requires a name plus at least one usable phone number or email address.
- Resolve the duplicate review. Choose the existing buyer, or use **Create separate** and enter a
  factual reason when the identities are truly different.
- Confirm the buyer is **Active**. Needs Review, Paused, Do Not Contact, and Archived buyers are
  intentionally excluded from future automated matching.
- Review the current criteria version, market, property type, price capacity, funding, proof, and
  other case requirements. Do not loosen verified criteria merely to create a match.
- Clear Buyer Network filters or move to another result page before assuming the record is absent.
- InvestorLift synchronization and outreach are disabled. A saved or matched buyer is not proof that
  any campaign ran; check the House **Outreach** revision and delivery states for Stonegate-owned
  recipient activity.

### RealEstateAPI Property Intelligence Is Unavailable

- Confirm `REALESTATEAPI_API_KEY` and the account credit balance.
- Confirm `UNDERWRITING_REALESTATEAPI_COMPS_MODE` is `shadow` or `candidate` and production was
  redeployed.
- Read the provider summary for the exact-address match, quota, timeout, or response error.
- A RealEstateAPI failure does not invalidate an otherwise complete RentCast analysis. Continue the
  review and retry only when its evidence is needed.
- Never promote RealEstateAPI from shadow to candidate merely because it returned more records;
  review overlap, conflicts, comp quality, operator time, cost, and verified outcomes first.

### PDF Buttons Are Missing

Complete and save a market analysis first. Open the lead's **Underwriting** tab and review the
report area. Role authorization and API health must also be valid.

### AI Recommendation Is Disabled Or Blocked

- Confirm the runtime and capability are installed and enabled.
- Confirm the OpenAI provider is configured.
- Confirm the source record satisfies the capability's evidence gate.
- For the Comp Analyst, confirm `UNDERWRITING_AI_COMP_ANALYST_MODE=draft`. A rejected result means
  the structured output crossed an evidence or price-authority boundary and was intentionally not
  shown as advice.
- Review the visible blocker.
- External-action simulations are expected to remain blocked by the AI10 release lock.

### A Record Cannot Be Deleted

Deletion may be prohibited by role, related evidence, financial history, or audit requirements.
Archive the record or correct it through the approved workflow.

## 23. Owner Administration Checklist

### Daily

- Review Home exceptions.
- Review overdue seller responses and tasks.
- Review today's appointments.
- Review pending approvals.
- Review provider or worker failures.

### Weekly

- Review VA and Lead Manager performance.
- Review pipeline aging and neglected leads.
- Review underwriting calibration and corrections.
- Review transaction deadlines and disposition coverage.
- Review source economics and spend exceptions.
- Review AI acceptance, edits, rejections, cost, and failures.

### Monthly

- Reconcile funded revenue and compensation.
- Review company margin against target.
- Review user access and deactivate departed users immediately.
- Review consent, suppression, recording, and communication exceptions.
- Review backups, alerts, worker health, and provider failure history.
- Review AI quality, privacy, cost, and business outcomes.

### Quarterly

- Review role permissions and operating policy.
- Review market launch requirements.
- Review AI models, prompts, tools, knowledge, evaluations, and autonomy.
- Test emergency shutdown and rollback procedures.
- Review provider contracts, costs, limits, and security.

## 24. New Employee Onboarding

1. Owner creates the Stonegate user and assigns the minimum required role.
2. Employee creates an individual Clerk login.
3. Owner verifies the local user and Clerk identity are linked.
4. Employee signs in and confirms role-specific navigation.
5. Employee completes training using synthetic records.
6. Manager verifies the employee can perform normal work and cannot open restricted pages.
7. Manager reviews consent, suppression, recording, privacy, and escalation rules.
8. Owner assigns the correct manual in **Company & Policy > Company setup**.
9. Employee opens **My Setup**, reviews the role standards, and submits workspace-test evidence.
10. Owner approves the submission only after confirming normal access and role restrictions.
11. Live work is assigned only after role acceptance is approved.

When a person leaves, deactivate the Stonegate user immediately. Reassign owned conversations,
tasks, appointments, leads, transactions, and disposition cases. Do not delete the user or their
history.

## 25. Plain-Language Glossary

| Term | Meaning |
| --- | --- |
| Active lead | A seller opportunity that still requires work |
| ARV | Expected resale value after the assumed renovation |
| As-is value | Supported value in the property's present condition |
| Assignment fee | Revenue Stonegate earns by assigning its contract rights to a buyer |
| Attribution | Evidence showing which source, campaign, or advertisement produced a lead |
| Buyer maximum | Highest modeled purchase amount a buyer strategy may support |
| Campaign | A tracked outreach or advertising effort |
| Closing evidence | Documents or provider records proving the deal actually funded |
| Comp | A comparable recorded property sale used as market evidence |
| Conversation owner | Person responsible for the next response or outcome |
| Copilot | AI assistance that drafts or recommends work for a person to review |
| Disposition | Selling or assigning the contracted deal to an investor buyer |
| Evidence weight | How much influence an included comp receives in the calculation |
| Handoff | Transfer of responsibility while preserving the same record and history |
| Lead owner | Person accountable for the seller's next outcome |
| MAO | Maximum allowable offer under the selected underwriting assumptions |
| Needs Reply | A conversation where Stonegate owes the next external response |
| Next action | Specific work that must happen next, with an owner and due time |
| Proof of funds | Evidence that a buyer can fund the proposed purchase |
| Recorded sale | A completed property transfer used as primary valuation evidence |
| Seller contract ceiling | Maximum acquisition price supported by current approved economics |
| Suppression | A company record that blocks prohibited contact |
| Transaction | The coordinated contract-to-close record |
| Underwriting version | A saved set of valuation, repair, and offer assumptions |
| Watcher | Person who follows a conversation without becoming its owner |

## 26. Related Documentation

- `LEAD_MANAGER_USER_MANUAL.md`: plain-language daily guide for the Lead Manager role.
- `STAFF_ROLE_MANUALS.md`: plain-language standards for every operating role.
- `DOCUMENTATION.md`: documentation authority and source priority.
- `SYSTEM_MAP.md`: complete as-built product, workflow, data, and integration map.
- `UI_CONTROL_REFERENCE.md`: every production page's meaningful buttons, fields, effects,
  prerequisites, disabled states, and expected results.
- `OPERATING_MODEL.md`: roles, handoffs, compensation, and operating policy.
- `FINISHING_ROADMAP.md`: canonical sequence for production completion and provider activation.
- `SETUP_REFERENCE.md`: local, production, domain, credential, webhook, and provider setup.
- `SETUP_MANUAL.md`: nontechnical owner guide for accounts, providers, staff, acceptance, and
  maintenance.
- `UNDERWRITING_COMP_METHOD.md`: valuation and offer methodology.
- `AI_AGENTS.md`: AI architecture and authority.
- `AI_AUTOMATION_ROADMAP.md`: AI production acceptance sequence.
- `SECURITY_COMPLIANCE.md`: security, consent, communications, and retention controls.
