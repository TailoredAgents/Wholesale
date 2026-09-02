# Stonegate UI Control Reference

Last verified against the application: September 1, 2026

## Purpose

This is the canonical button, field, section, state, and permission reference for the Stonegate
public website and Operating System. It is written for employees and the future Stonegate help
assistant.

Use this file to answer:

- Where is a control?
- What does it do?
- What information belongs in a field?
- What record changes after it is used?
- Why is a button disabled, hidden, or unavailable?
- What should happen next?

Use `USER_MANUAL.md` for complete operating workflows, `SYSTEM_MAP.md` for system architecture,
`SETUP_REFERENCE.md` for configuration, and domain references for business policy.

## How To Read The Tables

| Column | Meaning |
| --- | --- |
| **Control or section** | Exact or recognizable label shown in the interface |
| **Purpose and effect** | What it displays, creates, changes, sends, or records |
| **Availability and common blocker** | Role, selected record, status, evidence, or provider needed |

Controls that only filter or navigate do not change business records. Submit, approve, send,
archive, post, and provider controls do change records or contact an outside system.

## Global Status Rules

| State | Meaning |
| --- | --- |
| **Ready / Current / Connected** | The displayed prerequisite passed |
| **Draft** | Editable work that has not been approved |
| **Pending / Needs review** | A person must inspect or decide the record |
| **Approved** | A named user authorized that exact version |
| **Sent** | A provider accepted the request; delivery or completion may still be pending |
| **Blocked / Unavailable** | The action did not run because a prerequisite failed |
| **Archived** | Retained outside normal active views |
| Disabled button | A required field, role, selected record, provider, evidence gate, or prior step is missing |
| Hidden control | The signed-in role does not have the required permission or the control is irrelevant to the current state |

Never repeatedly select a disabled or provider-backed control. Read the nearby status or error,
correct the prerequisite, and retry once.

### Disposition Checklist Exception

In Dispositions, **Needs setup**, launch-readiness, proof, buyer-coverage, and missing-backup states
are informational checklist signals even when older copy calls them blockers. They may change a
badge, warning, explanation, or recommended next action, but they must not disable buyer ranking,
pool selection, calling, follow-up, activity logging, offer entry, or other ordinary desk work.
Operators may shop an incomplete deal and choose the next buyer themselves. The displayed checklist
order is not a prerequisite sequence; no item must be started or completed before another ordinary
authorized action.

A Disposition control may be disabled only for a real platform boundary: wrong organization or
missing role permission; STOP, Do Not Contact, suppression, or channel-permission state; no usable
destination/sender or an unavailable provider for an external action; invalid required form input;
or missing truthful signature, assignment, deposit, or funding evidence for a legal/financial
assertion. Exact package, outreach, provider-handoff, and buyer-selection approvals remain explicit
audited actions. The standard Disposition representative has those narrow approval and bulk-release
permissions, including `dispositions:send_bulk_outreach`, and does not enter a routine manager wait
state. That narrow permission releases governed Dispositions outreach only; it does not grant the
global marketing permission `communications:send_bulk`.

## Page Access Reference

Owners can access every production OS workspace. Other users see a page only when both their role
is relevant and the required permission is present.

| Workspace | Typical authorized roles | Permission signal |
| --- | --- | --- |
| Home | Administrator, Operations Assistant, Lead Manager, Acquisitions, Dispositions, Finance, Marketing | Relevant role permission |
| Inbox | Operations Assistant, Lead Manager, Acquisitions | `communications:view_conversations` |
| Tasks | Administrator, Operations Assistant, Lead Manager, Acquisitions, Dispositions, TC, Finance | Relevant work permission |
| Calendar | Operations Assistant, Lead Manager, Acquisitions | `underwriting:edit` or `operations:manage` |
| Prospecting | Operations Assistant, Lead Manager, VA Caller | `operations:manage` or `calling_lists:work_assigned`; Analytics requires `operations:manage`; native Dialer Control and Pilot Acceptance are dormant |
| Leads | Administrator, Operations Assistant, Lead Manager, Acquisitions | `leads:view` |
| Dispositions | Administrator, Operations Assistant, Dispositions | Both `deals:view` and `buyers:view` |
| Deals | Operations Assistant, Acquisitions, Dispositions, TC, Finance, approved partner/vendor | `deals:view` |
| Buyers | Operations Assistant, Dispositions | `buyers:view` |
| Finance | Finance / Accounting | `financials:view` or `compensation:view` |
| Marketing | Marketing Manager | `financials:view` or `communications:send_bulk` |
| Settings | Owner, Administrator | At least one administration permission |

Campaigns, Analytics, and My Calls are the active local Prospecting views. Analytics is hidden from
caller-only accounts; Dialer Control and Pilot Acceptance are dormant. Lead Queue, Pipeline, and Underwriting are local
Leads views. Approvals are in Tasks; transaction and disposition work is in Deals; administration
is in Settings. My Setup remains available to every signed-in employee.

## Public Website

### Public Header And Footer

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Stonegate logo | Returns to the home page | Always available |
| Open navigation / Close navigation | Opens or closes the mobile navigation menu | Appears on smaller screens |
| How It Works, Selling Situations, FAQs, About | Opens seller education pages | Navigation only |
| Displayed phone number | Starts a phone call and records an anonymous call-click conversion event | Requires a device capable of calling |
| **See My Selling Options** | Opens `/get-a-cash-offer` | Standard public header and footer only; the form page uses a focused logo-and-phone shell |
| Mobile **Call** bar action | Starts a phone call and records the mobile placement and source page | Fixed to the bottom of public pages at 720px wide or below; never appears in the OS |
| Mobile **See My Options** bar action | Opens the seller-options page and records the mobile placement and source page | On the form page, scrolls to the current form instead of clearing it |
| Privacy Policy | Opens current data-use terms | Always available |
| Terms & Conditions | Opens current website and SMS program terms | Always available |

### Contact And Service Area

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Header **Contact** | Opens `/contact` | Available on every public page |
| Published phone | Calls the currently configured Stonegate seller number and records the click placement | Requires a calling-capable device |
| **Email Stonegate** | Opens the device email composer addressed to `offers@stonegatehb.com` and records the click placement | Requires a configured email application |
| Request availability | Explains that the web form accepts property requests at any time | This is not a promise that staff answer calls 24 hours a day |
| Initial service area | Explains the Metro Atlanta starting market and address-based coverage confirmation | Exact counties remain unpublished until owner-approved |
| **See how Metro Atlanta coverage works** | Opens the detailed service-area guide | Available from Contact and related seller-education pages |
| Property meetings | Explains that in-person reviews occur at the property by appointment | Stonegate does not publish an office location that has not been confirmed |
| **Request a Property Review** | Opens the two-step cash-offer form | Always available |

### Metro Atlanta Service Area

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Breadcrumb **Home** | Returns to the public homepage | Always available |
| Address start | Carries the entered address into the full cash-offer form | A property address is required |
| Published phone | Calls Stonegate to ask about coverage | Requires a calling-capable device |
| How coverage works | Explains that Metro Atlanta is an initial focus and coverage is confirmed by exact address | This is not a promise to buy every property in the region |
| Local property review | Lists the location, market, repair, resale, title, and seller factors considered together | Informational only; it does not calculate an offer |
| Inherited property, Major repairs, Flexible timeline | Opens the matching seller-situation guide | Always available |
| **See the complete process** | Opens How It Works | Always available |
| Coverage questions | Expands or collapses answers about location, visits, and offer factors | Always available |

### Home Page Address Start

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Property address** | Carries the street address into the full cash-offer form | Required before starting |
| **Start My Offer** | Clears an older form draft, records an offer-start event, and opens the full form | Disabled by browser validation when address is empty |

### Cash-Offer Form Progress

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Property / Contact steps | Shows the two required form stages | Contact remains disabled until the property information passes validation |
| Completed step button | Returns to an earlier completed step without losing the draft | Only current or completed steps can be opened |
| **Back** | Returns to the prior step | Hidden on the first step |
| **Continue** | Validates the current step, records step completion, and advances; on Property it also creates or reuses the cold address-only CRM record and sends the Meta `Lead` event | Validation errors focus the first invalid field; a deterministic intake-attempt ID keeps retries on one record |
| Error summary links | Move focus to the field needing correction | Appears only after validation fails |
| Saved browser draft | Restores unfinished non-consent answers for up to 24 hours | SMS consent intentionally does not persist or restore |

### Property Step

| Field | Purpose and accepted value | Requirement |
| --- | --- | --- |
| Property address | Suggests matching properties after three characters and fills street, city, state, and ZIP from the selected result; keeps the supporting fields available for browser-saved address autofill | Required; suggestions require RealEstateAPI but never block manual entry |
| **Enter address manually** / **Edit address** | Opens the city, state, and ZIP controls when the seller prefers manual entry or needs to correct a suggestion | Always available; provider outages automatically preserve this path |
| City | Identifies the property city during manual entry | Required |
| State | Preserves the property's actual two-letter state instead of assuming Georgia | Required during manual entry |
| ZIP code | Supports market, duplicate, and property matching during manual entry | Required; five digits or ZIP+4 |

After the complete address passes validation, **Continue** sends the address capture while
the seller advances to Contact. The saved record appears in **Leads > Address Only** as cold and
**Skip trace needed**. It has no contact permission and starts no automated research, conversation,
follow-up, or seller contact. Eligible employees receive one **Stage 1 filled** SMS containing the
address and contact-details-pending status. Staff must check DNC status manually before cold
outreach.

### Contact Step

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Your name | Creates or updates the seller identity | Required |
| Phone | Primary contact number | A complete phone number is required for every website inquiry |
| Email | Additional contact method | Optional; must be valid when entered |
| Contact authorization disclosure | Explains that submitting authorizes phone, email, or a one-to-one text about the property inquiry and possible selling options | Displayed as passive text; there is no checkbox because submitting the form is the authorization action |
| Optional SMS consent | Separately records recurring automated SMS consent and the `seller-sms-web-v3` wording version | Unchecked initially, never required, and never saved in the browser draft |
| **Request My Options Review** | Promotes the same address-only record into a contact-completed seller inquiry, adds direct-contact authorization evidence and optional recurring automated SMS consent evidence, sends the Meta `Contact` event, and queues the separate **Stage 2 filled** employee SMS | Disabled while sending; validation or API errors leave answers on screen |
| **Add property details** | Opens optional post-submission questions without delaying or duplicating the accepted request | Available on confirmation for 24 hours |
| **Call Stonegate** | Calls the displayed Stonegate number after successful submission | Available on confirmation |
| **Submit another property** | Clears confirmation and form storage, then starts a fresh property request | Available on confirmation |

The confirmation reference is the first eight characters of the accepted lead ID. A message that
the request matched an existing record means Stonegate updated one history instead of creating a
duplicate.

This seller-facing SMS choice does not change internal **Text new leads** alerts. Those alerts are
operational messages sent only to employees who separately enabled the staff preference. Form
retries are deduplicated independently for Stage 1 and Stage 2.

### Optional Property Details

The request is already accepted before this section opens. **Save property details** uses a
random, short-lived token to add the answers to the same lead. The token cannot display the lead or
change staff-reviewed information.

| Field or control | Purpose and accepted value | Requirement |
| --- | --- | --- |
| Desired selling timeline | Records when the seller would ideally like to sell | Optional |
| Property type | Single-family, townhouse, condo, multi-family, manufactured, land, or other | Optional |
| Current condition | Move-in ready, minor repairs, major repairs, full renovation, or not sure | Optional |
| Occupancy | Owner occupied, tenant occupied, vacant, inherited/estate, or other | Optional |
| Main reason for considering a sale | Inherited, repairs, relocation, landlord, financial change, vacant, other, or exploring | Optional |
| Price you would like to consider | Seller expectation, not a Stonegate valuation | Optional; numbers only |
| Estimated mortgage balance | Preliminary debt context, not verified payoff | Optional; numbers only |
| Repairs, access, ownership, or timing details | Context that helps prepare the first conversation | Optional; maximum 1,000 characters |
| **Skip for now** | Closes the optional section without changing the accepted request | Always available while the section is open |
| **Save property details** | Adds the entered context to the accepted lead and records an internal audit/conversion event; it does not send a Meta event | At least one optional answer is required |

## OS Global Shell

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Sidebar navigation | Opens workspaces allowed by role and permission | Missing pages usually mean role or access configuration |
| Open navigation / Close navigation | Opens or closes the mobile sidebar | Mobile only |
| **Retry access** | Re-requests the signed-in Stonegate profile | Appears only after access verification fails |
| Search workspaces | Filters workspaces the user is allowed to open | It searches navigation, not sellers or records |
| `/` keyboard key | Focuses workspace search | Does not activate while typing in another field |
| **New** | Opens direct Seller lead and Email actions | Each action appears only with its required permission |
| **Recent destinations** | Shows up to five recently visited OS destinations stored in this browser | Empty until pages have been visited |
| Approvals shortcut | Opens **Tasks > Needs Approval** and shows the pending count | Visible only to authorized reviewers |
| Notifications bell | Opens Calendar, where operational commitments and appointments are reviewed | Visible to users allowed operational notifications |
| Notification count | Shows unread operational notification count, capped visually at 99 | Updates from the user profile |
| Account control | Shows signed-in Clerk identity and sign-out controls | Requires a completed Clerk session |
| Escape key | Closes search, recent menu, or mobile navigation | Browser keyboard control |

## Home

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Inbox** | Opens seller communications | Navigation only |
| **Tasks** | Opens assigned and overdue tasks | Navigation only |
| **Calendar** | Opens the company field calendar | Navigation only |
| Executive Copilot launcher | Opens evidence-backed management analysis | Visible when the Executive Copilot is installed |
| Overdue metric | Opens overdue tasks | Count is scoped to the signed-in user's visibility |
| Qualification metric | Opens Leads > Lead Queue | Shows seller records needing qualification |
| Meetings today metric | Opens Calendar | Includes today's scheduled appointments |
| Offer prep metric | Opens Leads > Underwriting | Includes underwriting and approval work |
| Priority title or arrow | Opens the record or workspace for that item | Navigation only |
| Task completion check | Completes the attached task | Visible only with lead-edit permission; use only after doing the work |
| **Open full queue** | Opens Tasks | Navigation only |
| Needs intervention links | Open unread conversations, unassigned leads, unscheduled tasks, or approvals | Team-wide exceptions are hidden from narrowly scoped roles |
| Pipeline stage | Opens Leads in Board mode filtered to that stage | Navigation only |
| **Open Pipeline** | Opens Leads in Board mode | Navigation only |

An **API fallback view** warning means counts are empty fallback data, not proof that no work exists.

## Tasks

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Primary actions metric | Counts visible open primary next actions | Read-only |
| Overdue metric | Counts visible open work past due | Read-only |
| Needs approval metric | Counts visible pending governed and AI decisions | Permission scoped |
| AI completed metric | Counts visible completed AI reviews | Read-only and role scoped |
| My Tasks | Shows open work assigned to the signed-in user | Requires an assigned user match |
| Do Today | Shows work due today | Filter only |
| Overdue | Shows tasks past their due time | Filter only |
| Upcoming | Shows future dated work | Filter only |
| Unscheduled | Shows tasks missing a due date | Filter only |
| Team | Shows visible team tasks | Authorized managers only |
| Needs Approval | Shows governed decisions and assigned AI briefs in the same queue | Authorized reviewers only |
| AI Completed | Shows accepted or rejected AI work with its recorded outcome | Visibility remains role scoped |
| Exceptions | Shows work with attention flags | Filter only |
| Completed | Shows completed work and recorded outcomes | Visibility remains role scoped |
| Search work | Filters title, seller, property, deal, and task type | Applies to the selected view |
| All owners | Filters all, unassigned, or a named owner | Managers only |
| Work row | Selects an item and preserves it in the URL | Does not change the source |
| **Open source** | Opens the seller, deal, conversation, calendar, or governed review | Navigation only |
| **Mark complete** | Completes a supporting task | Visible only with completion authority |
| **Complete and continue** | Opens the outcome and successor dialog for a primary action | A successor is required while the source is active |
| Outcome | Records what happened on the completed primary action | Required |
| Completion notes | Preserves useful handoff context | Optional but recommended |
| Next action | Names the replacement primary action | Required for an active source |
| Action type / Due / Priority | Classifies and schedules the replacement action | Due is required for an active source |
| Source already closed | Requests completion without a successor | API rejects this unless the source is terminal |
| Approve / Reject | Records a direct governed decision | Only shown when the approval can be safely decided in Tasks; BatchDialer **Approve** is hidden for hard conflicts and requires a written reason for explicitly overridable uncertainty |
| AI result panel | Shows the summary, next step, missing qualification facts, questions, risks, confidence, and evidence | Appears after the governed model run finishes |
| **Accept brief** | Adds the reviewed AI brief as an internal seller note and completes the AI work item | Does not message the seller, overwrite lead facts, or complete the human task |
| AI **Reject** | Records that the draft should not be used | Preserves the run and review evidence without changing the seller |

Approvals that require full source evidence show **Open source** instead of inline decision
buttons. The originating workspace remains authoritative for that decision.

## Calendar

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Schedule status | Shows today's appointments, leads ready to schedule, unassigned meetings, and capacity exceptions | Read-only summary |
| Schedule / Dispatch / Appointment / Availability | Switches Calendar work without changing appointment records | Availability requires management authority |
| **Schedule appointment** | Opens the central seller appointment form from any Calendar view | Requires an accessible active lead |
| Upcoming appointment / **Prepare** | Opens that appointment workspace in one action | Requires an appointment |
| Previous arrow | Moves back one month, week, day, or 30-day agenda period | Filter only |
| **Today** | Returns the cursor to today | Filter only |
| Next arrow | Moves forward one period | Filter only |
| All closers | Filters calendar by closer | Visible to users with management authority |
| Month / Week / Day / Agenda | Changes calendar display without changing appointments | Filter only |
| Appointment color legend | Identifies phone, property, video, office, other, and cancelled blocks | Icons and labels accompany every color |
| Month day number | Opens that date in Day view | Navigation within calendar |
| Empty day **Schedule** | Opens the central appointment form with that date prefilled | Seller and exact time remain editable |
| `+N more` | Opens a crowded month date in Day view | Appears after more than three appointments |
| Week day heading | Opens that date in Day view | Week mode only |
| Appointment event | Blocks the saved start-to-end duration and opens Calendar appointment mode | Color and icon show meeting format; cancelled events are striped |
| **Schedule anyway** | Confirms an intentional owner overlap after the API detects a double booking | Appears only after a conflict warning; the override is audited |

Calendar loading or availability errors do not delete appointments. Refresh after API recovery.

## Leads

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **New Lead** | Opens internal entry for warm calls, referrals, networking, and staff-entered sellers | Requires `leads:edit` |
| Seller name / preferred name | Creates the seller identity | Seller name required |
| Phone / Email | Creates usable contact methods | At least one is required by the form |
| Property address fields | Creates the property record | Street, city, state, and ZIP required |
| Source / Assigned owner | Preserves attribution and responsibility | Active owner required |
| Temperature / Next follow-up | Sets urgency and the first dated commitment | Optional but recommended |
| Seller context / Initial note | Preserves known motivation, timeline, condition, occupancy, price, mortgage, and intake notes | Optional; missing facts remain unconfirmed |
| **Create lead** | Creates the lead, contact methods, property, conversation, attribution context, assignment, and note | Opens the new full lead record after success |
| Summary metrics | Shows New, Qualified+, Unassigned, No follow-up, and Paid prospects; address-only records are excluded from operational counts but remain included in paid-prospect acquisition totals | Read-only |
| Lead Queue / All Leads / Pipeline / Underwriting | Switches local Leads work without changing records | Underwriting requires underwriting access; address-only records do not enter operational queues |
| Saved lead views | Filters by predefined operating state and updates the URL | **Address Only** shows incomplete website records; other operational views exclude them |
| Search active leads | Searches seller, property, source, and owner | Active records only |
| Owner filter | Shows all, unassigned, or one owner | Filter only |
| Stage filter | Shows one normalized pipeline stage in Table mode | Pipeline mode clears this filter so every valid drop destination remains visible |
| Sort | Orders the visible leads by Newest, Oldest, or Highest priority | All Leads and Address Only default to Newest; saved operational queues default to Highest priority |
| Table / Board | Changes display while preserving saved view, search, owner, and selected seller | Board mode clears a single-stage filter so the complete pipeline can accept moves |
| Received | Shows when the lead entered Stonegate in the table and board card | Read-only; displayed in the user's local timezone |
| Seller row | Selects the local seller preview | Does not edit the lead |
| Primary next-action link | Opens Lead Queue, Inbox, Calendar dispatch, Underwriting, Negotiation, or the full record based on status | Navigation only |
| **Conversation** | Opens Inbox on this seller | Requires conversation access; absent for an address-only record until contact details are completed |
| **Full record** | Opens the seven-section seller record and preserves the current list or board return context | Requires lead access |
| **Calendar** | Opens Calendar | Appears when appointment status exists |
| Close seller preview | Closes the mobile preview drawer | Mobile only |
| **Close out lead** | Opens the business close-out dialog | Active leads only; requires `leads:edit` |
| Dead / Disqualified | Records why routine seller work should end | One disposition is required |
| Close-out reason | Preserves the business reason in activity and audit history | At least 10 characters required |
| Final **Close out lead** | Atomically stops active tasks, appointments, automated follow-up, calling and handoff work; cancels every pending approval tied to the lead; retires pending or approved offer plans and unused offer concessions; closes the Lead Queue case and Inbox conversation; clears routine warnings; and moves the record to Closed Leads | Blocked while an active deal, contract, or disposition case exists; a funded deal is a completed success and can never be relabeled dead or disqualified |
| Closed Leads link | Opens dead and disqualified seller opportunities | Requires lead visibility |
| Archived Leads link | Opens confirmed duplicate and test records | Requires lifecycle visibility; Administrative archive is not a business disposition |

## Closed Leads

| Control | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Seller / property | Opens retained contact and property facts, calls and internal notes, recent activity, appointments, valuations, transactions, and buyer offers | Full history is display-only until the lead is reopened |
| Disposition / reason / closed time / closed by | Shows the auditable close-out decision | Read-only |
| **Reopen lead** | Opens the controlled reactivation dialog | Requires `leads:edit` |
| Reason for reopening | Records why seller work should resume | At least 10 characters required |
| Next action / Next action due | Creates one new primary follow-up task and returns the seller to active Leads | A future due date and clear title are required |
| Inbound seller email, SMS, or call | Automatically reopens a closed lead, restores the Inbox route, and creates urgent response work | Genuine inbound contact only; SMS opt-out keywords do not reopen the lead |

## Archived Leads

| Control | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Back to active leads** | Returns to All Leads | Navigation only |
| Seller / property | Opens the retained duplicate or test record | Full history is display-only until restored |
| **Restore** | Returns an archived lead to active lists | Disabled while saving |
| **Permanently delete** | Opens irreversible deletion confirmation | Intended only for confirmed test records |
| Type `DELETE` | Satisfies permanent-deletion confirmation | Exact uppercase value required |
| Final **Permanently delete** | Deletes the seller and operational history | Disabled until `DELETE` is entered; may still be blocked by related evidence or role |
| **Administrative archive** | Removes a confirmed duplicate or test record from normal queues while retaining read-only history | Confirmation required; never use for a real seller opportunity, including dead or disqualified leads |
| **Cancel** | Closes an archive or deletion dialog without changing the record | Dialog only |

### Pipeline Display

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Search seller pipeline | Filters by seller, property, or source | Filter only |
| Owner filter | Shows all, unassigned, or one owner | Filter only |
| Pipeline columns | Group active sellers by normalized operating stage | Every column remains visible while Board mode is active |
| Pipeline card | Selects seller context | Selecting the card does not change stage |
| Card drag grip | Moves the seller to an ordinary destination and saves that stage; dropping on Offer or Under Contract opens its evidence-backed action instead | Ordinary stages and Offer require `leads:edit`; Under Contract requires `contracts:record_executed` or legacy-compatible `contracts:modify`; mouse and press-and-hold touch dragging are supported |
| Move to stage | Provides the keyboard/mobile alternative in the selected seller preview | Ordinary stages save directly; Offer opens workflow choices; Under Contract opens the signed-agreement form; the same permission, validation, stale-state protection, and rollback rules apply |
| **Offer - choose workflow** | Opens the asset-aware Stonegate valuation workspace or **Record an outside offer** without changing the saved stage first | Requires `leads:edit`; outside-offer catch-up supports House and Land, while Stonegate-generated Land offer authority remains unavailable |
| **Record an outside offer** | Saves an offer already presented outside Stonegate with amount, occurred date/time, method, outcome, optional seller response, and optional internal notes | Requires `leads:edit`; the time cannot be in the future; Countered/Negotiating enters Negotiating, every other outcome enters Offer Presented unless the lead is already Negotiating; verbal acceptance does not mean Under Contract |
| **Under Contract - record signed agreement** | Opens the exact executed-contract upload instead of applying a label-only stage mutation | House and Land; requires `contracts:record_executed` or legacy-compatible `contracts:modify`, no conflicting executed workflow, and the evidence described under Contract Tab |
| Saving / result notice | Shows the in-progress move and its success or failure | A rejected or stale move restores the prior column and refreshes current server state |
| Card action | Opens the recommended workspace for current operating status | Navigation only |
| Conversation | Opens Inbox for the lead | Requires conversation access |
| Full record | Opens the complete lead record | Requires lead access |
| Close pipeline context | Closes the mobile detail drawer | Mobile only |

Dropping a card inside its existing grouped column is a no-op, which preserves more-specific stages
such as Appointment Scheduled or Offer Presented. Ordinary destinations are direct CRM updates.
**Offer** and **Under Contract** are board destinations, but they act as shortcuts into the factual
workflow rather than writing those milestones without evidence. Under-contract cards cannot be
dragged out of sync with their deal. Every completed move or action uses the same audited services
as the full lead record; dragging never bypasses stage, permission, concurrency, or asset-class
rules.

The full lead record's **Change pipeline stage** control follows the same boundary. It does not
offer Offer Pending Approval, Offer Ready, Offer Presented, Negotiating, or Under Contract as bare
manual stages. It offers **Offer - choose workflow** and, for an eligible authorized House or Land user,
**Under Contract - record signed agreement**. Offer stages can retreat to a normal pipeline stage
with a required audit reason. An Under Contract lead remains locked to **Contract & Deal** so the
signed agreement and transaction stay aligned. Pipeline **Continue negotiation** and **Negotiate**
links open `?tab=valuation#negotiation-governance` in **Valuation & Offer**, never the Contract tab.

## Operations

The former Operations page is now a compatibility redirect. Its controls retain the behavior
documented below, but their live owners are: Calendar in **Calendar**; campaigns, prospects, and
calling lists in **Prospecting**; markets in **Settings > Markets & Territories**; team controls
in **Settings > People & Access**; duplicate review in **Settings > Data & Quality**; and follow-up
plans in **Settings > Workflows**.

### Calendar Tab

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Internal calendar | Shows acquisition appointments and operating commitments | Use Calendar > Appointment for meeting work |
| Needs attention | Lists operational notifications | Read-only until a notification is selected |
| **Mark read** | Records the notification as read | Hidden after it has been read |
| Saved view name | Names a reusable Operations view | Required to save |
| View | Selects Appointments, Calling lists, Leads, or Inbox as the destination | Required |
| **Save view** | Creates the reusable view | Requires a name and view |

### Markets And Campaigns Tab

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Market Name | Human-readable market name | Required |
| State | Two-letter state code | Required |
| Timezone | Eastern or Central operating timezone | Required for scheduling controls |
| **Add market** | Creates the geographic market record and its internal lowercase code | Disabled by browser validation when required values are missing |
| Territory Market | Parent market | Required |
| Assigned team | Team responsible for the territory | Optional |
| Territory Name | Human-readable territory label; the internal code is automatic | Required |
| Counties | Comma-separated county names | Optional but important for assignment |
| ZIP codes | Comma-separated postal codes | Optional but important for territory matching |
| **Create territory** | Creates routing geography under a market | Requires market and name |
| Campaign Name / Code | Human label and stable campaign key | Required |
| Campaign Market / Territory | Geographic scope | Market required; territory optional |
| Channel | Cold call, cold email, direct mail, paid search, paid social, organic, referral, or other | Required |
| Owner | Responsible company user | Optional but recommended |
| Start date | Campaign operating start | Optional |
| Initial budget | Planned dollars, not actual spend | Optional |
| **Create campaign** | Creates the outreach campaign record | Does not import prospects or record actual cost |
| Prospect Campaign | Campaign receiving a manually added prospect | Required |
| Owner name | Seller or owner name from the source record | Required |
| Phone / Email | Contact evidence | At least one usable contact method is needed operationally |
| Assigned caller | Initial caller | Optional |
| Source record | Vendor or source identifier | Recommended for duplicate control |
| **Add prospect** | Adds one prospect to the selected campaign | Does not create a CRM lead until qualified handoff |

### Calling Lists Tab

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| List selector | Chooses the list being edited or worked | Required before adding sellers |
| List Name | Names a reusable internal calling list | Required |
| Default caller | Default assignee for new entries | Optional |
| Description | Explains the list's purpose | Optional |
| **Create list** | Creates the list | Requires a name |
| Lead | Selects an existing active seller | Required |
| Caller | Overrides the list's default caller | Optional |
| **Add to list** | Adds the seller to the selected list | Disabled until a list is selected |
| Outcome | No answer, callback, follow-up, interested, appointment set, not interested, wrong number, or Do not call | Required when recording an attempt |
| Handoff | Selects the acquisitions recipient when applicable | Available for warm outcomes |
| Attempt notes | Records what occurred and the next action | Recommended |
| **Record** | Saves the calling-list attempt and selected outcome | Requires the entry and valid outcome data |

### Team Tab

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Pencil beside staff name | Edits the Stonegate display name and records an audit event | Does not change Clerk email, password, role, or permissions |
| **Deactivate / Reactivate** | Removes or restores OS access without deleting history | Owner or authorized administrator only |
| **Delete** | Permanently removes an unused duplicate employee and its access-only setup | Appears only after deactivation; blocked when the employee has operating history |
| Existing user's access-role menu | Changes an existing person's OS role without recreating the login | Selecting Owner / full access grants company-wide access |
| **Cold calling** | Allows this user to receive calling batches and opens their assigned Prospecting queue | Does not change the user's main role or grant unrelated pages |
| Name / Email | Creates the Stonegate-side user identity | Must match the person's Clerk sign-in email |
| Access role | Operations Assistant, VA, Acquisitions rep/manager, Dispositions rep, Transaction Coordinator, or Owner / full access | Operations Assistant covers routine CRM work but excludes Finance, Marketing, Settings, approvals, contracts, exports, and deletion; choose Owner only for company-wide access equal to the primary Owner |
| Allow assigned cold calling | Enables Prospecting when the new person may also cold call | Operations Assistant and VA Caller accounts are enabled automatically; an administrator can turn it off later |
| **Create user** | Creates the individual Stonegate user | Does not create or share a password |
| Add member | Chooses an active user for a team | Requires a team |
| Membership role | Member or Manager | Manager role carries team responsibility |
| **Add** | Adds the selected user to the team | Requires a user |
| Team Name / Function / Manager | Defines team identity and responsibility | Name required; manager optional |
| **Create team** | Creates a Prospecting, Acquisitions, Dispositions, or Operations team | Requires a name and function |

### Data Quality Tab

| Control | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Underwriting performance ribbon | Shows verified ARV error, bias, range coverage, and tracked markets | Read-only; requires calibration outcomes for accuracy metrics |
| Underwriting operating baseline ribbon | Shows analysis count, median selected comps, comp yield, and run time | Read-only; older analyses without execution timing still count where their stored comp totals permit |
| Difficult-scenario coverage | Counts verified cohort tags for dense, suburban, rural, unique, low-comp, recovery, and repair-risk cases | Tags are entered on the lead's verified outcome and do not change valuation math |
| Provider and methodology scorecard | Breaks verified errors, range coverage, overrides, and adequacy down by market/provider | Read-only; small samples remain insufficient evidence |
| Methodology decision controls | Records evidence-backed formula or provider proposals and human approval/rejection | Does not change formulas automatically |
| **Scan active leads** | Runs duplicate detection across active seller records | Does not merge automatically |
| **Keep separate** | Marks the candidate pair as two legitimate records | Requires a pending duplicate candidate |
| **Merge records** | Combines the supported records while retaining history | Requires management authority and a pending candidate |

### Follow-Up Plans Tab

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Seller selector | Chooses an active lead for a plan | Required |
| **Enroll** | Creates the plan's internal tasks and approval-ready drafts for the seller | Requires a selected seller |
| Plan name / Description | Identifies the cadence | Name required |
| Day 3 SMS draft | Defines the reusable proposed SMS text | Required; it does not send when the plan is created |
| **Create plan** | Creates the Day 1 call, Day 3 SMS approval, and Day 7 review cadence | Does not contact a seller |

## Campaigns

Open **Prospecting > Campaigns**. Managers see **Overview**, **Import**, **Costs**,
**Assignments**, and **History**. Caller-only accounts open **My Calls** instead.

### Campaign Context

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Switch campaign | Makes one campaign the context for every local section | Requires at least one campaign |
| **New campaign** | Opens campaign creation without leaving Prospecting | Requires `operations:manage` |
| Name / Short code | Identifies the campaign and its stable internal code | Both required; code uses lowercase letters, numbers, underscores, or hyphens |
| Market / Territory | Places the campaign in the active service area | Market required; territory optional |
| Channel / Owner / Dates / Budget | Sets ownership, source channel, operating dates, and planned spend | Channel required; other fields may be added as known |
| **Create campaign** | Creates the campaign and opens it as selected context | Requires a valid market and unique code |

### Performance

| Section | Purpose | Availability |
| --- | --- | --- |
| Performance by campaign | Compares imported records, attempts, warm leads, appointments, costs, and conversion | Read-only |
| Selected campaign rows | Show campaign quality and economics | Based on recorded campaign activity |

### Import Prospects

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Mapping name | Names a reusable vendor-column mapping | Required |
| Source or vendor | Identifies the file source | Required |
| **Add contact export preset** | Adds or reuses the PropStream layout with First/Last/Company Name, Phone 1-5, and Email 1-4 | Use for Stonegate's current downloaded contact export |
| **Add standard preset** | Adds or reuses the alternate PropStream layout with Property ID and Owner 1 fields | Use only when those exact headings exist |
| Owner/company, first/last name, Phone 1-5 with type, Email 1-4, Source ID, Street, City, State, ZIP columns | Maps vendor headings and preserves ranked contact methods plus Cell/Landline evidence | Enter headings exactly as they appear in the CSV |
| Phone-specific DNC columns | Retains each source-marked number but excludes only that number from calling | A clear alternate number remains callable |
| Record-wide do-not-call column | Maps a single explicit source flag when the vendor provides one | Optional; do not use it for phone-specific flags |
| **Save mapping** | Saves the reusable column mapping | Required headings must be valid |
| Selected campaign context | Receives every imported record automatically | Choose the campaign at the top of Prospecting before importing |
| Saved mapping | Selects the vendor mapping | Required |
| Source format | Identifies a PropStream export or a general CSV | PropStream requires an export ID, saved-list ID, or saved-list name |
| Measurement cohort | Attributes list performance and determines its dialing mode | Recommended for every controlled VA comparison |
| Default assignee | Applies a caller when the row has no separate assignment | Optional |
| Export ID / Saved list ID / Saved list name / Exported at | Preserves exact vendor lineage | At least one identity is required for PropStream |
| Market / County / Distress / Equity / Ownership / Occupancy / Property type | Preserves the filters used to produce the list | Enter the actual export criteria |
| CSV file | Uploads the prospect file for validation | CSV required |
| Property states and campaign-state warning | Shows state totals and identifies rows outside the selected campaign market | Warning only; does not block import |
| **Validate file** | Previews valid, invalid, duplicate, suppressed, review, eligible, prior-contact, callback, active-conversation, and existing-lead states | Does not commit records |
| **Import reviewed file** | Commits new records and attaches refreshed source/contact evidence to existing matches | Disabled when no row can be imported or matched |
| Add one prospect manually | Opens individual cold-prospect entry inside the selected campaign | Use for one pre-lead record that is not in a CSV |
| Owner / Phone / Email / Address / Caller / Source ID | Creates one traceable prospect with optional assignment | Phone or email required; enter either the complete address or no address |
| **Add prospect** | Saves the record as a prospect without creating a seller lead | Requires the selected campaign and valid contact details |

### Costs

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Selected campaign / Cohort / Category | Links cost to list purchase, VA labor, enrichment, phone, voice, mail, ads, software, or other | Campaign context and category required |
| Related import | Links cost to one imported file | Optional |
| Incurred on | Cost date | Required |
| Worker / Hours / Hourly rate | Calculates VA labor cost | Used for VA labor |
| Amount | Direct cost amount | Used for non-labor or adjusted cost |
| Vendor / Notes | Adds source and explanation | Recommended |
| **Record cost** | Adds an actual campaign cost ledger entry | Does not create a Finance payment |

### Calling Batches

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Existing batch row | Selects the batch whose records appear below | Requires a batch |
| Batch name / selected campaign | Names and scopes the batch | Campaign is inherited from the page context |
| Cohort | Restricts records to the selected source cohort and applies its dialing mode | Recommended for controlled comparisons |
| Import batch | Limits records to one import or any unbatched campaign records | Optional |
| Assigned caller | Gives the batch to a specific active caller | Required; the person must have **Cold calling** enabled in Operations > Team |
| Maximum records | Caps records added, between 1 and 1,000 | Required |
| Due by | Sets the batch deadline | Optional but recommended |
| Notes | Adds manager instructions | Optional |
| **Create callable batch** | Creates the batch from eligible unbatched records | Requires eligible records and caller |
| Batch records | Shows each assigned record and status | Read-only from Campaigns |

### Import History

| Section or control | Purpose and effect | Availability |
| --- | --- | --- |
| Committed file row | Selects an import and shows source/list plus new and matched counts | Requires prior import |
| Row-level results | Shows exactly why each row imported, matched, failed, or was excluded plus relationship state and contact count | Read-only evidence |

## Prospecting Analytics

Open **Prospecting > Analytics**. This manager-only view compares attributable business outcomes,
cost, quality, evidence coverage, and retained historical dialer evidence. Financial values also
require `financials:view`. An unavailable or permission-hidden value is not zero. A historical
**Ready for controlled pilot** label does not activate or authorize the dormant native dialer.

### Filters And Scorecards

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Start date / End date | Selects an inclusive UTC reporting window | Both required; end cannot precede start and the range cannot exceed 366 dates |
| Source | Limits evidence to native Stonegate, BatchDialer, paid ads, or other attribution | The four canonical choices remain available even when one has no records in the period |
| Campaign / Cohort | Limits the report to durable records carrying the selected operating campaign or measurement cohort | Clear to compare an external source whose raw lead records do not carry that dimension |
| VA / caller | Limits work and linked cost evidence to one current or historical caller | Clear to compare an external source whose raw lead records do not carry that caller |
| Dial mode | Limits records carrying a stored cohort, batch, work, cost, or attempt dial mode | Clear to compare a source without that operating evidence |
| **Reset** | Restores the initial 30-date window and clears optional filters | Manager only |
| **Apply filters** | Reloads the private, no-store analytics result | Disabled while loading; invalid dates show an error |
| Funnel cards | Show attempts, human conversations, right-party contacts, qualified sellers, appointments set and held, accepted handoffs, contracts, and closed assignment-strategy transactions | Missing raw source evidence displays **Unavailable** |
| Cost and profit | Shows labor, provider, list, other/marketing, total cost, collected gross revenue, approved-reconciliation contribution profit, and unit economics | Requires `financials:view` plus linked cost, time, collected revenue, transaction, and approved reconciliation evidence as applicable |
| Calling productivity | Shows paid and productive time, per-hour output, and contact/conversion rates | Per-hour values require paid-time evidence |
| Source comparison | Compares native Stonegate, BatchDialer, paid ads, and separate other-attribution rows on attributable outcomes | Rows can overlap when paid acquisition later receives a BatchDialer handoff and must not be added together; raw dial metrics remain unavailable without attempt evidence |
| Break down by | Changes operating scorecards among VA/caller, campaign, cohort, list, and dial mode | Read-only selection |
| Quality and reputation | Shows duration, failed/no-answer/voicemail, duplicate, complaint, DNC, abandonment, connection-time, reputation, and trend indicators | Each item remains unavailable until its source evidence exists |
| Metric coverage | Shows evidence completeness for raw attempts, paid hours, provider cost, appointment outcomes, profit attribution, and number reputation | Warnings identify missing evidence; they do not synthesize values |
| Daily movement | Shows daily UTC attempt, contact, handoff, answer-rate, and failure evidence | Empty when the period has no attributable daily records |

### Technical Readiness And Definitions

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Historical controlled-pilot readiness | Preserves the prior **Blocked**, **Needs review**, or **Ready for controlled pilot** technical result | Read-only historical evidence; never authorizes native calling |
| Blocking issues / historical review | Lists the conditions captured by the former native readiness model | Use for audit or cleanup; do not reactivate controls to make the display green |
| Readiness check cards | Preserve dedicated-line, browser-token, callback, recording, session, one-line-cap, and worker evidence | Investigate old live work through an authorized cleanup path; Dialer Control is dormant |
| **How these metrics are calculated** | Expands deterministic definitions, source records, attribution timestamp, and unavailable conditions | Use before comparing unlike sources or periods |
| Prior confirmed snapshot notice | Retains the last successful values after a transient network or server failure | A 401 or 403 clears the prior snapshot, including financial values, because access expired or was removed |

### BatchDialer VA Performance

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Today / Last 7 days / Last 30 days | Reloads normalized direct BatchDialer call facts in the provider account timezone | Manager only; the migration and worker fact backfill must be deployed |
| Archive evidence boundary | Shows the earliest call currently archived and the provider rolling scan window | Earlier dates may be incomplete rather than zero; this observation does not prove continuous historical coverage |
| Agent | Shows one provider agent or the all-agent summary | Agents remain visible under provider identity until explicitly mapped |
| Calls / human contacts / recorded duration | Shows completed CDR volume, detected-person calls, and the provider's generic duration field | Duration is not asserted to be talk-only time; missing duration is excluded and shown through coverage |
| Unique contacts / contact-ID coverage | Counts distinct provider contact IDs and shows the share of calls that supplied one | Calls without a provider contact ID are excluded rather than guessed to be different people |
| Candidate / evidence-accepted / verified-handoff / false-positive metrics | Separates provider-selected qualifying results, evidence-gate acceptance, new-lead Stonegate handoffs, and failed evidence gates | Acceptance rate uses all evidence-accepted candidates; repeated accepted calls on an existing lead do not inflate new handoffs; unresolved candidates are excluded from accepted and false-positive totals |
| Appointment / contract / closed outcomes | Attributes later Stonegate outcomes to the original evidence-accepted lead-creating call | Appointment-entry rate counts handoffs with at least one appointment, so multiple appointments cannot push it above 100%; a provider appointment result creates an urgent manual-entry task, not an automatic Appointment |
| First observed / last observed / observed span | Describes clusters of completed-call activity with long idle gaps removed | Call-derived only; never paid hours, login time, break time, or a timeclock |
| Hourly activity / Daily activity | Shows when completed records occurred | Uses the configured BatchDialer account timezone |
| Campaign performance | Compares direct provider campaigns | Agent filtering does not alter campaign-wide rows |
| Stonegate user / **Save mapping** | Explicitly links an observed provider agent identity to an active Stonegate user | A mapping is never guessed and one Stonegate user cannot be actively mapped to multiple provider identities |
| **Prepare coaching draft** | Generates or reuses an evidence-cited AI manager review for the selected agent and exact period | Requires AI configuration and call evidence; output is draft-only and may be retried after a provider failure |
| Coaching evidence references | Shows the metric keys and provider-event IDs supporting each statement | Manager must inspect the source evidence before acting |

The VA Performance Coach may recommend call review or next-shift coaching. It cannot change CRM or
BatchDialer state and cannot make discipline, pay, or employment decisions.

## Historical Prospecting Pilot Acceptance — Dormant

Pilot Acceptance and Dialer Control are hidden from normal production navigation in dormant mode.
Direct URLs must not permit a manager to create, start, advance, submit, or accept a native pilot.
The table below preserves the historical control contract for audit and cleanup only. Existing
evidence remains readable; authorized rollback/revocation, safe session cleanup, and late signed
provider callbacks remain available. Do not use these controls to reactivate calling.

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Pilot scope | Binds one VA, campaign, cohort, calling batch, and dedicated line | Batch must contain 75-250 unique records; every line cap must be one; daily dial cap must be 25-50 reservations and daily spend cannot exceed $10 |
| Controlled numbers | Saves one to ten active Stonegate staff forwarding numbers for the first calls | Every E.164 number must belong to an active staff profile and already be an eligible test record in the selected calling batch |
| **Begin controlled-number smoke test** | Moves the draft to `smoke_testing`; only the saved test records can be reserved | Requires current D9/runtime readiness, valid immutable scope, controlled checks, and no other active pilot |
| Smoke test | Selects durable answered call records and reconciles their controlled recipients, canonical recordings, provider call IDs, actual costs, and provider references | Passing evidence moves the exact pilot from `smoke_testing` to `running`; ordinary batch records stay blocked before then |
| Attempt review queue | Requires review of every terminal pilot attempt, including failed/no-answer/voicemail | Recording, transcript, and structured notes are required only for applicable connected seller conversations; non-contact outcomes still require truthful disposition, review, compliance, and cost evidence |
| Shift review | Recomputes provider-signed right-party conversation time, reservation coverage, incidents, and billing across every production-stage pilot session on one local date | Reconcile every root and child provider call ID to a provider-reported charge and reference, including documented $0 records. Passing requires 60 right-party conversation minutes, 25 terminal signed seller calls, 100% passed reservation reviews, and no hard incident; ringing, machines, wrong parties, and smoke-stage calls do not add productive minutes |
| Pilot progress | Shows passing shifts, reviewed attempts, required attempts, and hard gates | Three distinct passing local dates and 75 total attempts are required |
| BatchDialer comparison | Stores the named separate cohort/list reference, zero-overlap attestation, and comparison summary | Direct CDR evidence supports only the calls actually retrieved; original list membership, provider cost, and any missing attempt class remain unavailable unless separately evidenced. An honest inconclusive comparison is valid |
| Kill-switch and daily-cap drill | Verifies server-observed company/campaign off-then-on cycles, stopped or drained sessions, and one real reservation denial at the enforced daily cap | Typed confirmation alone cannot pass this gate |
| Rollback rehearsal | Verifies a later, separate campaign switch cycle, stopped/drained session, zero live calls, immutable evidence, and the hashed unworked remainder | Must be followed by a clean shift; evidence capture does not transfer or enable a BatchDialer list |
| **Rollback native pilot** | Closes a draft as `cancelled`, or disables a started pilot scope, stops/drains sessions, preserves evidence, and records `rolled_back` | Requires **ROLL BACK SINGLE-LINE PILOT** typed exactly; it does not automatically edit BatchDialer or allow cohort overlap |
| **Submit for owner review** | Freezes the manager-complete review state for final recomputation | Disabled while any hard evidence is missing, failed, unknown, or in flight |
| Owner decision | Accepts or rejects after a fresh server-side gate calculation | Owner or Founder/operator only; accept requires **ACCEPT SINGLE-LINE DIALER**, all hard gates passing, reason, and current revision; reject requires **REJECT SINGLE-LINE DIALER**, reason, and current revision |
| **Revoke native dialer authorization** | Blocks every new seller bridge that has not already been authorized for the accepted exact scope, safely drains provider work already authorized or in progress, and preserves its evidence | Owner-only cleanup path; the terminal history remains visible, but dormant native calling cannot resume through a new pilot |

This historical workflow was implemented but never production-accepted. BatchDialer is the
production calling system. Restoring a route or changing a stored switch does not authorize native
calling.

## Prospecting

Prospecting has **Campaigns** and **Analytics** for authorized managers plus **My Calls** for
assigned callers. Dialer Control and Pilot Acceptance are dormant. Within My Calls, views are **Work queue**, **Call quality**,
**Handoff review** for managers, **Performance**, and **Caller scripts** for managers.

The direct BatchDialer worker creates evidence-accepted warm Leads automatically. A qualifying
disposition alone is only a candidate: transcript evidence must show a live two-way conversation and
explicit seller interest, plus explicit appointment agreement for **Appointment Set**. Delayed or
unclear evidence retries and then appears as an approval item in Tasks without first creating a
Lead. My Calls remains for separately assigned manual CRM records, corrections, and historical
evidence. Starting or saving a My Calls record must not recreate a Lead that already arrived from
the same provider CDR.

### Work Queue And Attempt

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Due now / Callbacks / Corrections / Scheduled / Waiting / All assigned | Filters the caller's complete assigned shift without changing ownership | Caller sees only assigned records; managers can review the broader operation |
| Campaign and batch strip | Shows ready, callback, correction, active, and waiting CRM workload | Read-only |
| Assigned seller row | Loads that seller into the three-panel calling context | Disabled for another row while the caller has an active attempt |
| Manual CRM work | Confirms Stonegate is tracking one separately assigned prospect or correction at a time | Place the actual call in BatchDialer; My Calls does not load the native softphone, require a native lease, or duplicate a direct handoff |
| Ranked phone and email methods | Shows all validated imported contact methods in source rank order | Based on imported contact evidence |
| Prior attempt details | Expands notes, callback commitment, and structured qualification answers | Read-only history |
| Assigned priority row | Selects the current assigned prospect | Caller sees assigned work only |
| **Generate brief / Refresh brief** | Creates or refreshes a read-only Prospecting Copilot preparation draft | Disabled while saving or when no record is selected |
| Evidence and risks | Expands source facts, warnings, required questions, and limits | Appears after a brief exists |
| **Accept brief** | Records that the draft was useful | Does not alter seller data |
| **Correct** | Opens correction editing | Requires a generated recommendation |
| **Save correction** | Saves corrected summary and review evidence | Available while correcting |
| **Reject** | Records that the draft should not be used | Requires a generated recommendation |
| **Start prospect** | Locks a separately assigned record for manual qualification, notes, outcome, and correction work | Requires an approved active caller script; it does not dial the seller and must not be used to recreate a direct provider handoff |
| Qualification questions | Records motivation, timeline, condition, occupancy, price, and mortgage answers | Required questions depend on approved script |
| Disposition buttons | Records the truthful call outcome without using a long menu | Required |
| Callback date and time | Schedules callback work | Required for callback or follow-up outcomes |
| In 1 hour / Tomorrow / In 3 days | Sets a common callback time quickly | Caller can still enter an exact date and time |
| Acquisitions owner | Chooses warm handoff recipient | Required for interested or appointment-set outcomes |
| Appointment date and time | Records an agreed time on a manual record | For a direct Appointment Set result, use the urgent task to create and verify the authoritative appointment in Stonegate |
| Meeting type / location | Defines property, phone, video, or office context | Enter the agreed details in the manual Stonegate Appointment |
| Call notes | Records objections, commitments, and next action | Strongly recommended |
| Compliance flags | Records seller complaint, unclear identity, policy uncertainty, or recording issue | Select only when observed |
| **Save outcome** | Completes a separately assigned manual CRM attempt and applicable follow-up | Required fields vary by disposition; it must not duplicate a direct BatchDialer Lead. Appointments remain manual in Stonegate and cold-call DNC remains in BatchDialer |

### Handoff Review

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Warm seller handoff | Shows source attempt and qualification answers | Manager view only |
| Acceptance note | Optional manager context | Optional |
| **Accept handoff** | Accepts responsibility into acquisition workflow | Requires sufficient evidence |
| Correction type | Classifies the missing evidence for reporting and coaching | Required when returning |
| Required correction | States exactly what the caller must fix | Required when returning |
| **Return for correction** | Preserves the same handoff and creates correction work | Requires a correction reason |
| Rejection type | Classifies why the submission is not a warm lead | Required for terminal rejection |
| Rejection reason | Records specific manager evidence for the rejection | Required for terminal rejection |
| **Reject handoff** | Closes the prospecting entry, disqualifies the generated lead, and excludes the handoff from accepted-warm-lead metrics | Manager view only |

### Call Quality

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Analyze call** | Generates transcript-backed call coaching | Requires an available transcript |
| Manager summary / Suggested disposition | Reviews or corrects AI interpretation | Manager review state |
| Confidence and score fields | Scores script adherence, qualification, objections, data, and handoff quality | Values are 0-100 |
| Coaching points | One coaching point per line | Review field |
| **Approve coaching** | Accepts reviewed quality output | Manager only |
| **Correct / Save correction** | Edits and saves corrected coaching | Manager only |
| **Reject coaching** | Rejects unsupported output | Manager only |
| **Cancel correction** | Discards unsaved coaching edits | Correction mode only |

### Caller Scripts And Performance

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Caller performance | Shows attempts, contacts, handoffs, appointments, and quality | Read-only |
| Version title / Opening | Defines a new script version | Manager only |
| Standard question prompt fields | Adjust the wording for required qualification questions | Manager only |
| **Create draft version** | Saves a new inactive script version | Does not replace active script |
| **Approve** | Makes that draft the approved caller script | Manager only |
| Caller script history | Shows version, status, and question count | Read-only |

## Leads: Lead Queue

Lead Queue views are **Copilot**, **Today**, **Qualification**, **Performance**, and **Standards**.

### Copilot

| Control | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Work item row | Selects a seller case | Requires visible acquisition work |
| **Generate brief / Refresh brief** | Produces seller summary, gaps, questions, risks, reply, and next-step proposal | Disabled while saving |
| Evidence and risks | Expands the support and warnings behind the draft | Requires a generated brief |
| **Accept brief** | Records acceptance of the recommendation | Does not contact seller or update CRM |
| **Correct / Save correction** | Corrects the primary guidance and records edited review | Requires a draft |
| **Reject** | Records rejection | Requires a draft |

### Today

| Control or section | Purpose and effect | Availability |
| --- | --- | --- |
| Needs attention | Opens urgent acquisition cases | Read-only navigation |
| **Accept** under Accept warm handoffs | Assigns and accepts the handoff into Lead Manager work | Requires an unaccepted handoff |
| Seller follow-up | Shows due seller work | Read-only queue |
| Today's appointments | Shows meetings scheduled today | Read-only queue |
| Neglected leads | Shows active records lacking timely work | Read-only queue |
| Open lead icon | Opens the full seller record | Requires lead access |

### Qualification

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Seller queue row | Selects a case requiring qualification | Requires an approved qualification standard |
| Ownership | Confirms owner and title context | Required by standard |
| Decision makers | Confirms everyone required to sell | Required |
| Reason for selling | Records motivation | Required |
| Timeline | Records desired completion timing | Required |
| Property condition | Records known repair context | Required |
| Occupancy | Records who occupies the property | Required |
| Price expectation | Records seller expectation | Optional |
| Mortgage or liens | Records known debt/title context | Optional |
| Property access | Records how and when Stonegate can inspect | Required |
| Next action | Call, Text, Email, Seller appointment, Nurture, or Disqualify | Required |
| Due date and time | Creates the dated next action | Required for every choice except Disqualify |
| **Complete qualification** | Saves answers, updates qualification work, and creates the next action | Disabled while saving; blocked without approved standard |

### Performance And Standards

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Acquisitions scorecard | Compares weighted speed-to-lead, follow-up, conversation, qualification, CRM, appointment, and mature-outcome evidence without ranking specialists | Manager only; read-only shadow coaching view |
| 30 days / 90 days | Selects the evidence window and requests a fresh report | Manager only; the selected request includes a 12-second session-token and report timeout |
| **Refresh** | Requests a new uncached snapshot and announces completion; the report shows its generation time | Disabled while loading; a timeout says whether a confirmed same-period snapshot remains visible |
| Raw scoring evidence | Shows dimension-specific operands, sample counts, minimums, and evidence status | Manager only; Building dimensions expose raw inputs but withhold the numeric score and bar |
| Methodology and weights | Explains the versioned policy, coverage, and coaching-only guardrails | Read-only |
| Version name / Opening guidance | Defines a new qualification standard version | Manager only |
| **Create draft** | Saves a standard containing the nine standardized questions | Does not activate it |
| Qualification standards | Shows version history and current status | Read-only |
| **Approve** | Activates a draft standard | Manager only |

## Inbox

The Inbox is the communications workspace. It combines SMS, email, calls, recordings,
transcripts, internal notes, assignment, and AI call notes without splitting the seller
history into separate channel threads.

### Inbox Navigation And Filters

| Control | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Mine** | Shows conversations assigned to or watched by the signed-in user | Requires conversation access |
| **Unassigned** | Shows conversations without an owner | Visibility depends on role and team |
| **Team** | Shows conversations available to the user's teams | Requires team membership |
| **Needs reply** | Shows seller messages awaiting a staff response | Read-only filter |
| **Appointments** | Shows conversations linked to scheduled appointments | Read-only filter |
| **Unread** | Shows conversations with unread activity | Read-only filter |
| Mailbox group: **My addresses** | Filters email conversations sent to an address assigned to the user | Requires an active sender assignment |
| Mailbox group: **Team inboxes** | Filters email routed to a shared team address | Requires team mailbox access |
| Mailbox group: **Restricted** | Shows restricted correspondence only to authorized roles | Hidden without permission |
| Search | Finds a conversation by seller, property, phone, email, or message context | Searches visible records only |
| Conversation row | Opens the unified timeline and seller detail panel | Requires conversation access |
| Right-panel **SMS permission** | Shows **Permissioned** or **Not permissioned** for the selected seller | Read-only status is visible with the seller context; editing requires lead-edit or SMS-send authority |
| **Compose** | Opens the global email composer without requiring a property lead | Requires outbound email permission and an active sender |
| **Refresh** | Reloads conversation and provider status | Available while Inbox is open |
| Mobile **Inbox / Thread / Details** | Changes the active pane on narrow screens | Mobile layout only |

### Unified Timeline

| Control or item | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| SMS / MMS event | Shows inbound or outbound text, delivery state, timestamp, and any inbound photos; a newly sent live Twilio message refreshes quietly for about 30 seconds while delivery is pending | An SMS with photos is labeled **MMS**; a photo-only message remains visible even without body text |
| Inline photo | Opens the full-size privately stored image; the adjacent download control saves a copy | Requires access to the conversation; common browser image formats preview inline and other supported formats use a secure file control |
| Email event | Shows sender, recipients, subject, body, attachments, and delivery state | Read-only after send |
| Call event | Shows direction, outcome, duration, recording, and transcript status | Depends on voice integration |
| Internal note | Shares staff-only context in the timeline | Never sent to the seller |
| Full transcript | Opens the complete speaker-separated call text, jumps playback from a selected timestamp, and downloads a timestamped `.txt` copy | Requires a completed transcription and recording access for the user's role |
| Call recording player | Securely loads retained call audio with play/pause, 10-second rewind and skip, scrubbing, elapsed/total time, speed, mute/volume, and download controls | Requires recording access; only one call plays at a time, and position and speed resume for the current browser session only |
| **Retry** | Loads the recording again after a network or media error | Appears when recording playback fails; loading and buffering status appear in the player |
| **Delete recording** | Removes retained audio after a reason is entered | Authorized roles only; transcript and audit history are handled separately |
| Mark unread/read | Changes the user's unread state for the conversation | Does not change another user's unread state |
| Lead/property link | Opens the related seller record | Requires lead access |

### Message Composer

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **SMS** | Selects text-message composition | Manual one-to-one texting requires a routable phone number, configured Twilio SMS, and no active STOP/DNC suppression; the recorded permission label remains visible but is advisory |
| **Email** | Selects email composition | Requires an active Resend sender and recipient email |
| **Call** | Opens device calling or manual call logging | Requires a seller phone number |
| **Note** | Creates an internal timeline note | Requires conversation edit access |
| Inbound / Outbound | Records direction when manually logging a communication | Manual logging only |
| Sender address | Chooses an authorized personal or shared email address | Only granted addresses appear |
| To | Sets primary email recipients | Required for email |
| CC / BCC | Adds copied or hidden recipients | Email only |
| Subject | Sets the email subject and reply-thread context | Email only |
| Template | Inserts an approved message template | Does not send automatically |
| Signature | Appends the sender's configured signature | Email only |
| Attachment | Uploads files to the outbound email | Subject to file and provider limits |
| Message body | Contains the SMS, email, call note, or internal note | Required before send/save |
| **Send** | Sends the selected external message | Disabled when provider, sender, recipient, suppression, contact-hour, or content requirements fail |
| **Save note / Log communication** | Adds an internal or manually logged event | Does not contact the seller |

### SMS Permission

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **SMS permission: Permissioned / Not permissioned** | Shows the latest recorded seller SMS decision in the Inbox right sidebar and seller-record Contact panel | A missing or revoked record remains **Not permissioned** |
| **Edit SMS permission** | Opens the staff documentation form | Available to authorized lead-edit or SMS-send staff while the lead is open |
| Status | Records a new permission grant or revocation | Appends a new record; it does not rewrite prior evidence |
| Where was this decision confirmed? | Identifies phone call, in person, Facebook, seller text, written form, or another documented source | Required for every staff-recorded change |
| Automatic audit evidence | Preserves the selected source, employee, timestamp, displayed phone number, activity, and audit history | No typed note is required |
| **Save SMS permission** | Appends the permission record for the displayed phone number and writes activity and audit history | A grant requires a valid seller phone number; a not-permissioned decision can still be recorded without one |

A seller's carrier-level **STOP** is an absolute suppression. Staff cannot manually replace it with
a permission grant; the seller must send **START** from that phone number before SMS can resume.
Permission recorded for one number does not transfer when the primary phone number changes.
For deliberate staff-initiated CRM calls and one-to-one texts, this permission state is an
informational label rather than a send/call blocker. Automated and bulk outreach retain their
separate eligibility controls.

### Cellphone Calling

| Control | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **My cellphone** | Selects Stonegate's Twilio cellphone bridge | Requires the employee's enabled forwarding number |
| **Call seller** | Calls the employee first; pressing 1 connects the seller with Stonegate caller ID | Requires configured Twilio Voice and an active department line |
| **Log call** | Opens the manual inbound/outbound call record form | Logging does not itself place a call |
| Call outcome | Records answered, voicemail, missed, no answer, or other disposition | Required by the active workflow when shown |

### Assignment And Handoff

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Conversation owner | Assigns the person responsible for the next response | Requires assignment permission |
| Queue | Places the conversation in **VA Prospecting**, **Qualified**, **Appointment Set**, or **Acquisitions Follow-Up** | Options depend on workflow state |
| Watcher | Adds a staff member who should continue seeing updates | Requires workspace membership |
| Handoff reason | Explains why ownership or queue is changing | Required for managed handoffs |
| **Complete handoff** | Reassigns the same record while preserving its full history | Blocked if required owner, queue, or reason is missing |
| Pinned note | Keeps important staff context visible in the right panel | Internal only |

### AI Call Notes

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Call Intelligence status | Shows queued, processing, temporary failure, stopped/exhausted, or automatically posted state | Processing starts from the completed recording; no separate generation or approval button is required |
| **Retry call intelligence** | Resets an exhausted transcript's attempt counter and queues the same call for another audited run | Visible only after repeated failures stop automatic retry and requires recording access |
| Summary | Adds the transcript-grounded call result to Inbox and the seller record | Internal only and posted automatically |
| **Quick read** | Shows a compact reason, stated numbers, timing, and next-step summary at the bottom of a completed call note | Derived from the saved structured note and never replaces the full transcript or evidence |
| Motivation / Timeline / Condition / Occupancy | Extracts seller qualification details and immediately fills empty CRM fields | Never overwrites an existing value; staff can correct the CRM record |
| Asking price | Extracts stated seller pricing | Never treated as an approved offer |
| Mortgage and title | Extracts possible debt or ownership concerns | Must be verified by staff |
| Repairs / Objections / Commitments | Structures operational follow-up context | Saved in the automatic internal summary |
| Next action / Follow-up date | Preserves suggested next-step context | Does not create a task automatically |
| Supporting timestamps | Opens the transcript evidence behind an extracted item | Requires diarized transcript evidence |
| Correct CRM fact | Changes an inaccurate transcript-populated value from the seller record | Existing staff-entered values remain unchanged unless a person edits them |
| Automatic call summary | Adds the narrative as an internal note in the conversation timeline, seller history, and recent activity | Never sent to the seller; remains linked to the transcript and AI audit |

### Email Administration

Email administration is embedded at `/os/settings/communications`. The legacy
`/os/inbox?manage=email` link redirects there.

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Senders** | Manages approved outbound identities | Owner or communication administrator |
| **Routing** | Manages inbound address and department routing | Owner or communication administrator |
| **Failed events** | Lists Resend events that exhausted bounded retry | Email manager only; external mailbox acceptance still must pass |
| Address / Display name | Defines the sender identity | Domain must be verified in Resend |
| Sender type | Identifies personal, shared, accounting, offers, or buyer mailbox behavior | Administrator only |
| Status | Enables or disables an address | Disabled addresses cannot send |
| Owner / Team | Controls who can use and receive the address | Requires an existing user or team |
| Inbound / Outbound | Enables each direction independently | Provider configuration must support the selected direction |
| Default sender | Makes the address the user's or team's first choice | Only one applicable default is used |
| Signature | Defines the default outbound signature | Can be adjusted in the composer |
| Sender grant | Gives a user permission to send from an address | Does not grant access to restricted mailbox history by itself |
| Watcher grant | Gives a user visibility into routed replies | Used for shared coverage |
| Unresolved inbound assignment | Routes an unmatched reply to a person or team | Requires an unresolved inbound event |
| Restricted routing destination | Preserves restricted-mailbox visibility during automatic or manual assignment | A restricted alias can target only a restricted-visibility conversation |
| Requeue reason | Explains why a failed provider event is safe to try again | Required, audited, and available only after the cause is corrected |
| **Requeue** | Resets one dead-lettered event into the worker's retry queue | Email manager only; does not bypass attachment or routing safeguards |
| **Save / Update** | Persists sender or routing changes | Administrator only |

### Voice Line Administration

Voice-line administration is shown below Email Administration at `/os/settings/communications`
only to owners and users with `communications:manage_voice_lines`.

The Voice readiness panel above the line editor checks Render variables, webhook validation, the
active acquisitions number, number matching, and primary/fallback cellphone coverage. Its copy
button provides the number-level inbound webhook without exposing credentials.

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Staff cellphone | Stores an employee's private forwarding destination | Enter in `+1...` format; never shown to sellers or buyers |
| Ring cellphone | Adds that cellphone to the company line's forwarding group | Requires a valid cellphone; answering requires pressing 1 |
| Text new leads | Opts that employee into internal SMS alerts for new seller leads from the website, Facebook forms, and supported future intake sources | Requires a saved personal cellphone and live staff-alert provider readiness |
| Text inbound messages | Opts that employee into internal SMS alerts when a seller or buyer texts a Stonegate line | Requires a saved personal cellphone; alerts route to the conversation owner first, then the company line's primary and fallback owners |
| Phone number | Registers a company-owned Twilio number in Stonegate | Must already belong to the company Twilio account |
| Department | Identifies the line as Acquisitions, Dispositions, or Company general | Automatically sets the matching seller, buyer, or general purpose |
| Primary owner | Sets the first responsible employee for an unowned or directly routed call | Must be an active Stonegate user |
| Fallback owner | Records the second responsible employee when the owner or primary is unavailable | Must differ from the primary owner |
| Department team | Adds active team members to the shared ring group and grants them use of the line | Optional; manage membership under People & Access |
| Ring strategy | Rings staff cellphones in owner-first order or all simultaneously | Twilio supports up to 10 total destinations per call |
| 24/7 staff ringing | Confirms enabled staff phones ring at every hour | Fixed for active lines; the missed-call plan runs only after no answer or unavailable targets |
| Missed-call plan | Chooses voicemail or urgent-task behavior after no answer or unavailable targets | Fallback targets are included in the ring sequence before voicemail |
| Ownership ready | Confirms primary and fallback staff both have forwarding enabled | Does not mean Twilio provider acceptance has passed |
| Label | Names the line by purpose or seat | Required |
| Status | Activates or deactivates routing through the line | Deactivation preserves call history |
| Inbound route | Starts routing with the conversation owner or the line's primary owner | Then includes active team members and fallback without duplicates |
| Default company line | Marks the preferred line for company calling | Use one operational default |
| **Add line** | Creates the Stonegate voice-line record | Requires voice-line management permission |
| **Save** | Updates ownership, coverage policy, label, status, default, and route | Requires voice-line management permission |

## Calendar Dispatch And Availability

Calendar has **Schedule**, **Dispatch**, **Appointment**, and **Availability** views.

### Dispatch

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Lead / appointment source | Selects the seller record to schedule | Requires lead access |
| Closer | Assigns the field closer | Only active eligible users appear |
| Appointment type | Identifies inspection, seller meeting, follow-up, or other visit | Required |
| Start and end time | Sets the proposed appointment window | Required |
| Location | Sets the property or meeting address | Required for field work |
| Internal note | Adds dispatch context | Staff only |
| Capacity check | Shows work hours, overlap, travel buffer, territory, and daily load conflicts | Advisory unless enforcement is enabled |
| Override conflict | Allows an authorized dispatcher to proceed despite a warning | Requires an override reason |
| Override reason | Records why a capacity warning was accepted | Required when overriding |
| **Dispatch appointment** | Creates or updates the appointment and assigns the closer | Blocked by enforced conflicts or missing required fields |

### Capacity

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Timezone | Defines the closer's scheduling timezone | Required |
| Home ZIP | Provides a travel-planning origin | Optional but improves dispatch checks |
| Day start / Day end | Defines normal working hours | Required for capacity enforcement |
| Daily appointment count | Limits planned appointment volume | Positive number required |
| Default meeting length | Supplies an expected duration | Used when an appointment lacks one |
| Travel buffer | Reserves time between field appointments | Used by conflict checks |
| Working days | Defines the closer's normal available weekdays | At least one day recommended |
| Territories | Restricts or prioritizes service areas | Used by dispatch checks |
| Enforce limits | Turns capacity warnings into dispatch blockers | Owner/operations setting |
| Active | Includes the closer in dispatch selection | Inactive closers cannot receive new work |
| **Save capacity** | Persists the closer's scheduling rules | Requires capacity-management access |
| Unavailable start/end/reason | Defines a one-time blocked period | Start must precede end |
| **Add unavailable block** | Removes that window from availability | Requires a valid window |
| **Remove** | Deletes an availability block | Does not cancel an existing appointment automatically |

### Calendar And Meetings

| Control or item | Purpose and effect | Availability |
| --- | --- | --- |
| Field calendar view | Shows closer appointments and availability | Calendar access |
| Central appointment form | Creates phone, property, video, office, or other seller meetings and can assign an eligible team member | Phone and property locations prefill from the lead |
| Closer filter | Limits visible events to a closer | Manager sees team; closer sees permitted records |
| Meeting row | Opens the appointment workspace | Requires appointment and lead access |
| Status and outcome | Shows scheduled, completed, canceled, or no-show state | Read-only until updated in meeting workflow |

## Appointment Workspace

The tablet-ready appointment workspace has **Prepare**, **Walkthrough**, **Seller view**,
and **Outcome**. Focus mode reduces navigation distractions during a seller meeting.

### Prepare

| Control or section | Purpose and effect | Availability |
| --- | --- | --- |
| Focus mode | Expands the meeting workspace for an iPad or laptop | Appointment workspace only |
| Seller/property brief | Shows contact, property, qualification, appointment, and risk context | Read-only |
| Acquisitions Copilot | Generates meeting questions, repair-scope suggestions, gaps, risks, and next-step guidance | Draft-only; requires the corresponding enabled capability |
| Supporting evidence | Shows why the Copilot made a recommendation | Available after generation |
| **Accept / Correct / Reject** | Records human review of Copilot guidance | Does not contact seller or approve an offer |

### Walkthrough

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Start walkthrough** | Starts the field inspection state | Appointment must be active |
| Condition | Records overall observed condition | Staff observation |
| Occupancy | Confirms occupied, vacant, tenant, or other state | Staff observation |
| Utilities | Records utility status | Staff observation |
| Access | Records access constraints | Staff observation |
| Title concern | Records a possible ownership or title issue | Requires later verification |
| Safety concern | Warns the team about unsafe conditions | Does not replace professional inspection |
| Area/room items | Adds location-specific repair observations | Repeatable |
| Repair work decision | Records not sure, no work, repair, replace, or specialist review | A closer's selection marks the item walkthrough verified; AI suggestions remain unconfirmed |
| Extent and quantity | Applies the versioned Georgia catalog range to the observed scope | Planning allowance, not a contractor bid |
| Exact amount | Replaces the expected system amount while preserving its original range | Optional; use only with stronger price evidence |
| Repair range | Shows low and high totals including contingency | Uses the same scenario transferred to underwriting |
| **Suggest repair scope** | Generates cited categories and scope candidates from existing appointment evidence | Draft only; cannot price or confirm work |
| **Add unconfirmed suggestions** | Adds reviewed AI categories that are not already in the walkthrough | Requires Accept or Save correction; rows remain unconfirmed |
| Photo upload | Attaches property evidence | Requires supported image and network access |
| Delete photo | Removes an uploaded photo | Requires field edit access |
| **Dictate** | Converts supported browser speech into inspector-note text | Audio is not retained by Stonegate |
| Saving / Saved / offline status | Shows API autosave or local iPad recovery state | Reconnect before final submission |
| **Save now** | Immediately syncs the incomplete walkthrough | Does not mark inspection complete |
| **Submit walkthrough** | Finalizes the current field report | Blocked if required inspection details are missing |
| **Review and transfer** | Moves verified field facts into underwriting inputs | Requires a submitted walkthrough |

### Seller View And In-Person Signing

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Client PDF | Opens the seller-safe valuation presentation | Requires a generated client report |
| Fullscreen | Presents the report without operating controls | Useful on an iPad |
| **Resume / Review PDF** | Returns to an existing in-person signature session or opens the exact agreement | Requires a prepared SignWell request |
| Seller signer name/email | Identifies the signer | Must match the person signing |
| Stonegate signer name/email | Identifies the company signer when required | Depends on template roles |
| **Start session** | Opens the in-person signing ceremony | Requires configured SignWell, agreement, and signer details |
| **End session** | Closes local access to the signing session | Does not erase provider records |
| **Begin signing** | Opens the provider signing page on the device | Seller should review the complete document |
| **Return to Stonegate** | Leaves provider signing and returns to the appointment workspace | Available after session launch |

### Outcome And Negotiation

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Request offer step | Requests or selects an approved negotiation step | Requires current underwriting and approval state |
| Decision makers confirmed | Confirms required sellers participated | Required before relying on agreement |
| Decision-maker names | Records confirmed participants | Required when confirmation is selected |
| Asking price | Records the seller's stated request | Does not change Stonegate's approved range |
| Presented offer | Records what Stonegate presented | Must remain within authority |
| Seller counter | Records seller response | Optional |
| Agreed amount | Records a tentative agreement | Does not replace an executed contract |
| Objections | Records seller concerns | Internal negotiation history |
| Commitments | Records promises and next steps | Internal negotiation history |
| Outcome | Sets meeting result such as follow-up, no agreement, or agreement reached | Required to complete the meeting |
| Follow-up date | Schedules the next action | Required when outcome needs follow-up |
| **Save outcome** | Persists negotiation facts and next work | Blocked when required outcome fields are missing |

## Seller Record

The seller record uses **Summary**, **Activity**, **Property**, **Valuation & Offer**,
**Appointments**, **Contract & Deal**, and **Files** sections. Every section acts on the same lead;
changing ownership or stage does not create a second record.

### Header And Summary

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Back to leads** | Returns to the lead workspace | Always available |
| **Edit lead** | Opens the single complete lead editor in the Property section | Requires lead edit access |
| Current stage | Shows the seller's current pipeline stage | Read-only in header |
| Owner | Shows and reassigns the person responsible for the record | Reassignment also updates the conversation, open tasks, upcoming appointments, watchers, and assignment history |
| Contact action | Opens the relevant communication workflow | Requires phone/email and channel access |
| First name / Last name | Edits the primary contact | Required fields depend on lead source |
| **Add phone** / **Add email** | Adds another contact method without replacing the existing methods | At least one phone or email must remain on the lead |
| Contact type / value | Edits any seller phone number or email address | Phone and email format validation applies |
| Primary | Chooses the preferred phone and preferred email used first by Stonegate | One primary is maintained per contact type |
| Remove contact method | Deletes an incorrect or obsolete phone number or email address | Cannot leave the lead without any phone or email |
| **SMS permission: Permissioned / Not permissioned** | Shows and edits the latest documented seller SMS decision from the Contact panel | Authorized staff may append a sourced grant or revocation without typing a note; carrier **STOP** requires seller **START** |
| Property address / City / State / ZIP | Edits the subject property | Address required for market analysis |
| Source / Campaign | Records acquisition attribution | Options come from configured operations data |
| Motivation / Timeline / Condition / Occupancy | Saves qualification facts | Unknown is valid until confirmed |
| Asking price / Mortgage balance | Saves seller-stated figures | Must not be treated as independently verified |
| Preferred contact method/time | Guides follow-up | Does not itself create a task |
| **Save lead** | Atomically persists ownership, contact methods, seller, property, and qualification changes | Disabled while saving; validation errors are shown in the editor |
| Stage / Stage reason | Selects an ordinary stage or an available Offer/Under Contract action; records why an offer stage is moved backward | Ordinary stages save directly; an offer retreat requires a substantive reason |
| **Offer - choose workflow** | Opens the asset-aware Stonegate valuation path or the factual **Record an outside offer** form | Requires `leads:edit`; external catch-up supports House and Land and does not fabricate offer approval |
| **Under Contract - record signed agreement** | Opens the executed-agreement importer from the stage control | Eligible House or Land lead; requires `contracts:record_executed` or `contracts:modify` and does not update the stage until the upload succeeds |
| **Update stage** | Applies an ordinary stage change | Permission, transition, and current-stage concurrency rules apply; action destinations use their own submit control |
| Administrative archive | Removes a confirmed duplicate or test record from active queues without deleting history | Requires archive permission; real opportunities must use business close-out |

### Property Validation

| Control or result | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Validate property** | Checks and normalizes the subject address before market analysis | Requires a sufficiently complete address |
| Candidate address | Shows a provider-normalized match | Staff must confirm the correct property |
| Match quality | Explains exact, normalized, partial, or unresolved address status | Read-only |
| **Use this address** | Replaces the working address with the confirmed normalized value | Requires lead edit access |
| Manual correction | Lets staff fix the address when no provider match is reliable | Staff remains responsible for correctness |

### Property Intelligence

The top of the **Property** section is the reusable research profile for the physical property.
It is shared by leads that resolve to the same normalized address and does not replace the seller's
contact, qualification, or activity history.

| Control or result | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Property image | Shows the latest field-inspection photo first; otherwise uses a licensed RealEstateAPI listing image or a no-photo placeholder | No Street View, aerial, satellite, or scraped fallback is used |
| Research status | Shows queued, processing, ready, partial, stale, needs address, needs review, or failed | Worker and a usable address are required for automatic completion |
| Profile complete / Valuation confidence / Selected comps / Snapshot | Summarizes evidence coverage, confidence, retained comp count, and immutable snapshot version | Read-only; missing evidence remains visible instead of being guessed |
| **Refresh research** | Queues a new property snapshot and explicitly refreshes market evidence | Requires lead edit access; may use RentCast and RealEstateAPI credits |
| Property map | Shows an interactive road map and property pin from coordinates already saved in Property Intelligence | Does not run another provider query or use a property-data credit; shows **Map location pending** until usable coordinates exist |
| **Recenter** | Returns the map to the saved property coordinates and default zoom | Available after the map loads; does not change the property record |
| **Open directions** | Opens the property destination in Google Maps in a new browser tab | Uses an external directions link, not an embedded Google Maps API or Stonegate API key |
| Verified property facts | Shows normalized physical and sale-history facts with retained source metadata | Unknown remains unknown when providers do not support a fact; provider estimates are labeled research signals |
| Additional property intelligence | Expands RealEstateAPI assessor, tax, equity, loan, listing, parcel, lien, construction, amenity, ownership, and hazard facts when returned | Full sanitized provider record is saved once and reused by the UI and AI |
| Saved value evidence | Shows Stonegate ARV support and external benchmark values already on file | Provider estimates remain benchmarks and do not become Stonegate's comp conclusion |
| Comparable evidence already on file | Previews retained screened sales without re-querying a provider | **Open full valuation** moves to the complete Valuation & Offer analysis |
| Sources, conflicts and freshness | Expands provenance, disagreements, and evidence age | Read-only audit context |

### Notes, Tasks, And Appointments

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Note body | Adds internal seller or property context | Required to save |
| **Save note** | Creates an internal note and audit event | Never sent externally |
| Task title / Owner / Due date / Priority | Defines follow-up work | Title and owner required |
| **Create follow-up** | Adds a task linked to this lead | Blocked without required task fields |
| Complete task | Marks the selected task complete | Requires task edit access |
| Appointment type / Start / End / Location / Owner | Defines a seller appointment | Start, end, owner, and type required |
| **Schedule appointment** | Creates a calendar and field-operations event | Capacity conflicts may warn or block |
| Appointment outcome | Records completed, canceled, no-show, or rescheduled result | Existing appointment required |
| **Save outcome** | Persists appointment outcome and notes | Does not automatically close the lead |

### Activity

| Control or item | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Open in Inbox** | Opens the seller's full unified conversation | Requires Inbox access |
| Channel / Direction | Classifies a manually logged message or call | Required |
| Subject / Body / Outcome | Records what happened | Body or outcome required by channel |
| **Log communication** | Adds the event to the seller timeline | Does not send an external message |
| Timeline row | Shows calls, messages, emails, notes, transcripts, and provider status | Read-only |

The Activity section also includes:

| Section | Purpose | Availability |
| --- | --- | --- |
| Recent activity | Shows material lead and workflow events | Read-only |
| Assignment history | Shows former and current owners/queues | Read-only |
| Stage history | Shows pipeline changes and reasons | Read-only |
| Consent and attribution | Shows source, consent, and campaign evidence | Read-only to normal staff |
| Audit events | Shows who changed important fields and when | Visibility depends on role |

## Valuation And Offer

The seller record's Valuation & Offer section is the working valuation area. **Leads >
Underwriting** is the active queue, while **Settings > Data & Quality** owns calibration,
provider scorecards, and methodology decisions. A market analysis is decision support, not an
appraisal or permission to promise a seller a price.

### Repair Inputs

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Repair method | Chooses system estimate, manual total, or guided itemized repair estimate | Affects offer math and report explanation |
| Manual repair total | Supplies a known working budget | Used only when the selected method allows it |
| Contingency | Adds repair uncertainty allowance | Must be a valid percentage or amount |
| **Apply repair preset** | Prepares a starting set of category decisions for the selected light, moderate, heavy, or structural scope | Starting point only; review every selected category |
| Work state | Sets a category to Not assessed, Unknown, No work, Repair, Replace, or Specialist review | Unknown adds an allowance; Not assessed is omitted; No work saves zero |
| Scope | Sets Minor, Standard, or Extensive work intensity | Changes catalog range for Repair and Replace decisions |
| Quantity | Sets systems, rooms, openings, roof squares, square feet, or project count | Starts from known subject facts where available; staff must verify |
| Expected range | Shows catalog low/high and expected amount for the category | Read-only until status, scope, quantity, or catalog version changes |
| Evidence and override | Opens evidence source, confirmation, manual amount, reason, and notes | Manual amount requires a reason and retains system comparison |
| Repair scenario strip | Shows low, expected, high totals and unknown-work allowance | Includes the selected contingency in low/expected/high totals |
| Repair notes | Captures assumptions and exclusions | Included in internal evidence |
| Evidence/source | Links photos, walkthrough facts, contractor input, or staff observation | Improves reviewability |
| **Save repair estimate** | Saves the current version used by underwriting | Disabled while saving |

### Verified Manual Sales

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Verified manual sales** | Opens the saved manual closed-sale records for this seller lead | Requires full lead visibility; caller-only roles do not see underwriting |
| Include checkbox | Chooses whether the saved manual sale enters the next analysis | Selection affects only the next saved analysis |
| Street / City / State / ZIP | Identifies the closed property and supports subject/duplicate checks | Complete address required; subject property rejected |
| Closed date / Closed price | Records the verified transaction fact | Future date and invalid amount rejected |
| Property type / Square feet | Supplies the minimum physical facts needed for screening | Required; the scorer may still reject a poor match |
| Bedrooms / Bathrooms / Year / Lot / Distance / Subdivision | Supplies optional physical and location evidence | Missing facts reduce reviewability; they are never invented |
| Condition at sale | Classifies Unknown, As-is, or Renovated | As-is or Renovated requires condition evidence |
| Verification source | Identifies county record, MLS record, closing document, broker confirmation, or another verified source | Required |
| Source reference / Source link | Preserves the exact record, identifier, or page used | Reference required; link optional and must use HTTP/HTTPS |
| Verification notes | Explains how closing price/date and relevant facts were confirmed | At least 10 characters required |
| **Save verified sale** | Creates an audited immutable evidence record and selects it for the next run | Duplicate manual/provider sale, subject, future date, or missing evidence rejected |
| **Remove** | Voids the record for future analyses | Prior analyses remain unchanged; create a corrected record instead of editing history |

### Market Analysis

| Control or result | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Quick Comp / Desk Review / Walkthrough / Offer Decision | Shows the progressive status of the existing valuation, field evidence, and offer authority | Status is derived from saved records; selecting a stage opens its existing workspace |
| Highest-value missing facts | Shows at most three lead facts most useful to the next valuation | Links to Property; absence does not mean every optional fact is known |
| **Run Stonegate valuation / Update Stonegate valuation** | Run performs the first provider retrieval; Update applies current repair and review inputs to the saved same-address market snapshot and saves a new reviewable result | Update makes zero paid provider calls, including when the saved provider attempt failed or returned no match |
| **Refresh market evidence (may use credits)** | Explicitly replaces the provider snapshot, retries configured providers, and then recalculates | Available after an analysis exists; review the capture time and credit warning before selecting it |
| Current decision | Keeps ARV, repairs, buyer target, opening, and seller ceiling visible and links to reports, appointment, approval, and signing | Values come from the latest saved underwriting version |
| Advanced records | Expands version comparison, prior versions, and manual underwriting creation | Collapsed by default; normal comp review remains in the main analysis |
| Subject facts | Shows bedrooms, bathrooms, size, year, lot, and property type used | Staff should correct material mismatches |
| Stonegate ARV / Supported range | Shows the weighted adjusted-sale point and Q25-Q75 range before repair or offer math | Primary valuation result; provider AVMs do not control it |
| Confidence | Summarizes evidence quality and unresolved gaps | Does not gate PDF generation |
| Offer range | Shows policy-based low/high offer guidance after repairs and assignment fee | Staff must use current authority and approval rules |
| Repair range / Unconfirmed work | Shows saved low, expected, and high repair totals, catalog version, unknown allowance, and specialist warnings | Expected amount drives the current analysis; range is decision support and does not block PDFs |
| Provider evidence | Shows RentCast/RealEstateAPI status, returned and usable counts, net-new and overlapping transfers, drops, internal duplicates, ineligible transfers, conflicts, current-run credits/latency, and original source credits/latency for reused evidence | Read-only; RealEstateAPI shadow evidence cannot affect valuation and failed calls may show conservative estimated credits; older analyses can retain labeled legacy DealMachine evidence |
| Closed-sale search summary | Shows the final Preferred, Expanded, Extended, or Manual evidence level, unique and duplicate counts, subdivision support, shortage, and next action | Read-only; Manual means the controlled provider search remained insufficient, not that the analysis disappeared |
| Search-attempt row | Shows each radius/date level, provider results, newly added sales, usable count, and reason for widening | Read-only; provider errors remain visible |
| Supporting market context summary | Shows supporting evidence status, active listing count, and ZIP | Read-only; never contributes to ARV or offer math |
| Supporting listings and ZIP market context | Shows active asking prices, size, days on market, ZIP median asking price, asking price per square foot, inventory, and market timing | Supporting-only; asking prices are not closed comps |
| Stonegate valuation adjustments | Shows the adjusted closed sales that drive the saved ARV and dependent offer math | Two sales produce labeled working guidance with confidence capped at 49; three are preferred; fewer than two produce no recommendation |
| Supported local adjustments | Shows only time, living-area, lot, garage, pool, or basement rates that passed local evidence and double-count controls | A missing feature rate is withheld, not assumed to be zero market value |
| Review rate support and withheld adjustments | Shows sample/pair counts and the exact reason each rate was supported or withheld | Read-only evidence |
| Review comparable adjustment math | Shows recorded price, every sourced dollar component, extrapolation limit, total adjustment, and adjusted indication | Read-only; review flags require operator judgment |
| What is driving this range | Shows adjusted-sale dispersion, condition uncertainty, withheld adjustments, expanded-market sales, provider conflicts, and magnitude review | Uses deterministic diagnostics; no generic percentage envelope is added |
| External benchmarks | Expands RentCast or RealEstateAPI provider value estimates | Collapsed secondary context; explicitly excluded from ARV and offer math; older analyses may retain a labeled legacy DealMachine benchmark |
| AI Comp Analyst draft | Shows evidence-cited include/exclude/review suggestions, condition hypotheses, micro-market concerns, missing questions, and range explanations | Draft-only; cannot mutate comps, set weights or prices, or confirm condition |
| Public evidence | Shows controlled subject research, AI-discovered closed sales, source grade, and source links | Must be verified before relying on a material fact; one-source sales receive reduced weight |
| Warnings | Identifies address, comp, price-per-square-foot, renovation, or data-quality concerns | Staff review required |
| **Investor PDF** | Downloads the detailed internal/agent-facing valuation report | Requires a saved analysis |
| **Client PDF** | Downloads the seller-safe presentation without internal negotiation details | Requires a saved analysis |
| Update analysis | Creates a new analysis version from current inputs and the saved provider snapshot | Earlier versions remain auditable; use the explicit refresh control only when new market evidence is needed |
| Version comparison | Compares ARV, repairs, disposition target, opening, seller ceiling, comp membership, repair categories, and adjustment evidence between two immutable versions | Requires at least two saved versions |
| Comparable changes | Lists selected sales added to or removed from the newer version | Uses provider ID, source reference, or saved address identity |
| Repair-scope changes | Lists categories whose decision, expected cost, or confirmation changed | Uses the saved repair snapshot and catalog version |
| Adjustment change | Shows supported/withheld rate counts and the adjusted ARV movement between saved versions | Read-only comparison; approval authority remains separate |

### Comparable Review

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Subject property band | Anchors the saved address, type/subdivision, beds, baths, living area, year, and lot used by the analysis | Read-only snapshot; correct source facts and create a new analysis when wrong |
| Compare / Location | Switches between side-by-side candidate review and relative coordinate position | Location is not a parcel or neighborhood-boundary map; unavailable coordinates are listed but not plotted |
| Included / Excluded / Draft changes | Keeps the complete draft decision count visible | Draft changes include inclusion, weight, or condition changes from the loaded analysis |
| **Restore system set** | Restores the engine's original included/excluded recommendation and 100% reviewer weights | Does not erase condition classifications or change the source analysis |
| Search / decision / grade / level filters | Narrows the visible workbench without dropping hidden candidates from the review payload | Display-only filters |
| Sort | Orders by best fit, nearest, most recent, or highest adjusted indication | Display-only; does not alter weight |
| Comparable candidate | Shows raw closed price, adjusted indication, price per square foot, sale date, distance/direction, physical comparison, source, A-D grade, search level, and subdivision | Read-only source facts |
| System pick / System excluded | Preserves the engine's original recommendation | Remains visible after human overrides |
| Reviewer changed | Shows that the draft include/exclude choice differs from the engine recommendation | Reviewer retains authority and must supply a reason |
| Comp grade | Summarizes physical, location, recency, and market-area fit; Extended-only records cannot receive A or B | A grade does not prove renovated condition |
| Search-level label | Shows whether the sale first appeared in the Preferred, Expanded, Extended, or Manual evidence step | Wider-query duplicates retain their earliest level; Manual identifies operator-entered evidence |
| Evidence source / **Open source** | Shows provider or manual verification origin and opens a retained source link | Manual reference is always retained; link appears when supplied |
| Source badges / Cross-sourced / Corroborated / Conflict | Shows RentCast, RealEstateAPI, manual, or public provenance; older evidence may retain a legacy DealMachine badge. Cross-sourced means more than one source reported the transfer; Corroborated requires explicit agreement; Conflict identifies material disagreement | Duplicate transfers count once; cross-sourcing alone is not corroboration and conflicts require review |
| AI draft badge | Shows the Comp Analyst's recommendation for the same comp | Advisory only; the reviewer still controls inclusion, reason, condition, and weight |
| Include | Allows a comparable to contribute to the estimate | Staff judgment; exclusion reason recommended when changed |
| Condition | Marks renovated, average, distressed, unknown, or other supported state | Unconfirmed renovation reduces confidence but does not block results |
| Exclusion reason | Explains why a comp should not be used | Required by review workflow when excluded |
| Weight | Adjusts a comp's influence within allowed bounds | Should reflect similarity and evidence, not desired outcome |
| Evidence and rationale | Opens engine rationale, condition evidence, warnings, verification notes, and retained source | Advanced evidence is collapsed by default |
| **Apply review and recalculate** | Rebuilds the analysis from every reviewed comp choice and creates a new immutable version | At least one included sale; every candidate receives one decision |
| Outlier result | Shows whether distance, price range, size, property type, or price-per-square-foot rules reduced or removed a comp | Read-only explanation |

### Offer Plan And Approval

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Strategy | Selects the intended offer approach | Requires saved underwriting |
| ARV / Repair / Assignment fee | Shows or adjusts governed offer assumptions | Edit permission and policy limits apply |
| Offer floor / Target / Ceiling | Defines negotiation authority | Ceiling is not automatically seller-facing |
| Notes and assumptions | Explains the plan | Internal only |
| **Save offer plan** | Creates a versioned offer plan | Does not authorize presentation by itself |
| **Request approval** | Sends the offer plan to the approval queue | Requires complete current plan |
| Approval status | Shows pending, approved, rejected, or superseded | Read-only |
| Approved amount/range | Defines the authority staff may use | Required before governed negotiation steps |
| **Request next negotiation step** | Proposes the next amount/action using current authority and ledger | Blocked without approved authority |
| Negotiation entry | Records asking, presented, counter, agreed, objection, and commitment context | Creates an auditable ledger |
| **Continue negotiation** / **Negotiate** | Opens the seller's full negotiation ledger in **Valuation & Offer** | Links to `?tab=valuation#negotiation-governance`; it does not open Contract & Deal |
| **Record an outside offer** | Records the amount and time actually presented outside Stonegate without inventing a governed offer plan | House and Land; requires `leads:edit`, a positive amount, a non-future occurred time, delivery method, seller outcome, and current-stage match |
| How it was presented | Classifies Phone, In person, Text / SMS, Email, Video meeting, or Other | Required for outside-offer catch-up |
| Seller outcome | Classifies Presented, Considering, Countered, Negotiating, Verbally accepted, Declined, No response, or Other | Countered/Negotiating enters Negotiating; all other results enter Offer Presented unless already Negotiating; none enters Under Contract |
| Seller response / Internal notes | Preserves the seller's actual response and staff-only context with the outside-offer evidence | Optional; each is limited to 2,000 characters |

### Underwriting Management Page

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Underwriting queue | Opens leads needing analysis or review | Requires underwriting permission |
| **Analyze comps** | Runs the same evidence workflow from the queue | Requires usable subject data |
| Calibration performance ribbon | Shows ARV error, bias, range coverage, and tracked markets | Requires verified outcomes |
| Operating baseline ribbon | Shows analysis volume, comp yield, run time, and selected-comp count | Uses every instrumented saved analysis |
| Evidence-quality ribbon | Shows comp overrides, AI repair-scope corrections, catalog error, and catalog outcome count | Empty samples display as unavailable, not zero accuracy |
| Provider and methodology scorecard | Compares verified outcomes by market and provider | Read-only; sample threshold still applies |
| Evidence segment scorecards | Attributes outcomes by property type, search level, comp grade, repair category, verification stage, and catalog | Grade/category rows overlap when one case contains several values |
| Validation scenario checkboxes | Classifies a verified outcome for U3.10 cohort coverage | Select only scenarios actually represented; tags do not alter the analysis |
| Stonegate valuation quality | Shows measured accuracy, range coverage, market bias, provider performance, and operator corrections | Uses verified outcomes; does not alter formulas automatically |
| Decision review | Shows approvals, overrides, confidence, and result history | Manager access |
| Verified sale/outcome input | Records known closing evidence for calibration | Must come from reliable evidence |
| Analysis version history | Opens prior valuation snapshots | Read-only |

## Approvals In Tasks

| Control or item | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Tasks > Needs Approval view | Limits the unified work queue to governed requests and AI review | Without `audit:view`, it lists only request types covered by the viewer's permissions; `audit:view` is the sole blanket read authority and does not grant decision authority |
| Approval row | Shows source, deadline, owner, status, and warnings | Requires read scope for that approval type; call summaries no longer enter this queue |
| Source link | Opens the underlying lead, transaction, finance record, or AI review | Used when the decision needs full context |
| Decision note | Records reasoning for approval or rejection | Required by some approval types |
| **Approve** | Authorizes the requested governed action | Server checks the request type: offer authority, contract sending, AI changes, or acquisition follow-up each requires its own permission |
| **Reject** | Rejects the request and records the reason | Same request-type permission check applies; unknown approval types fail closed |
| Review-at-source state | Directs the approver to decide in the originating workspace | Used when inline approval would omit required context |
| Legacy `/os/approvals` route | Redirects to Tasks > Needs Approval and preserves a selected approval | Compatibility only |

## Deals

Deals is the normal contract-to-funding workspace. It presents existing transaction,
disposition, buyer, task, document, and reconciliation records through one employee-facing deal.

### Deal Index

| Control or item | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Active | Shows non-funded, non-cancelled deals | Default saved view |
| Closing Exceptions | Shows active deals with an overdue closing item or unassigned coordinator | Requires a closing blocker |
| Ready for Disposition | Shows an exceptional executed transaction whose case still needs recovery | Normal House and Land execution creates or reuses the case immediately even with incomplete setup; this view preserves visibility if a legacy or failed handoff needs repair |
| Buyer Needed | Shows active disposition cases without an approved selected buyer | Requires an open disposition case |
| Finance Review | Shows deals ready for or requiring reconciliation | Detailed economics still require financial access |
| Completed | Shows funded or cancelled deals | Historical operational view |
| Queue icon | Shows compact status and next-action rows | Default display |
| Table icon | Shows a dense comparison table | Horizontally scrolls on narrow screens |
| Board icon | Groups deals by the next critical work area | Parallel statuses remain visible inside the record |
| Deal row/card | Opens the selected Deal record | Preserves view, display, deal, and tab in the URL |

### Deal Record

| Control or item | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Seller Lead | Opens the source seller record | Requires seller-lead access |
| Contract, Closing, Disposition, Finance strip | Shows independent status for each workstream | Read-only aggregate state |
| Summary | Shows the primary next action, blockers, evidence counts, selected buyer, and authorized economics | Default record section |
| Contract | Embeds agreement packages, SignWell, signatures, version controls, and the outside-signed catch-up entry point | Uses existing contract permissions and server gates |
| **Record an already-signed contract** in Deals > Contract | Opens the same House/Land executed-agreement importer by source lead | Available to `contracts:record_executed` or `contracts:modify`; gives a Transaction Coordinator an entry point without general Leads access; hidden once the contract is executed or closing is funded/cancelled |
| Closing | Embeds checklist, dates, title, funding, and closing controls | Current executable closing controls are House-only; Land retains pre-close evidence without exposing unsupported closing/funding actions |
| Documents | Embeds the transaction file room and evidence controls | Document access remains role controlled |
| Parties | Embeds closing-party records | Uses transaction edit permission |
| Disposition | Embeds the asset-appropriate case workspace | House shows the complete residential toolset; Land shows Package, the asset-aware Buyer pool, and supported engagement work while call queue, Outreach, Offer Room, buyer selection/funding, Reconciliation, and InvestorLift stay hidden |
| Finance | Opens the House disposition reconciliation view in deal context | House-only; economics are redacted from the aggregate unless authorized, and Land reconciliation remains unavailable |
| Timeline | Embeds immutable transaction history and notes | Read access follows the deal role |
| Transaction / Disposition Copilot | Opens the active domain assistant in a drawer | Draft and review only; does not hide or replace source evidence |

The legacy Transactions route redirects its selected transaction and tab into Deals. The
Dispositions route is setup-only for opening the first case and redirects existing case bookmarks
into Deals. Employees begin ordinary active-deal work in Deals.

## Transactions

The transaction record uses **Closing**, **Contract**, **Documents**, **Parties**, and
**Timeline** tabs. It begins after a seller record is moved into transaction execution.

### Transaction Header And Closing

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Transaction selector/row | Opens the selected contract-to-close record | Requires transaction access |
| Purchase price | Stores the seller contract amount | Must match executed agreement |
| Assignment fee / Expected revenue | Stores projected transaction economics | Projection until closing is funded |
| Closing date | Sets expected closing | Used for tasks and readiness warnings |
| Title/closing company | Records the closing partner | Optional until selected |
| Status | Tracks opened, under contract, title, marketing, assigned, closing, completed, or canceled state | Transition permission applies |
| Checklist item | Marks required execution work complete or incomplete | Does not replace source documents |
| **Mark funded** | Records confirmed closing funding | Requires authorized finance/transaction role and supporting facts |
| Milestone date/status | Updates key title, inspection, assignment, and closing milestones | Requires transaction edit access |
| **Save** | Persists transaction and closing changes | Disabled while saving |

### Contract Tab

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Template | Chooses an approved contract template | Requires configured template record |
| Seller/property/purchase fields | Supplies agreement merge data | For a purchase agreement, price must match the current seller-agreed/current transaction price and approved offer authority |
| Closing terms / Special terms | Supplies transaction-specific agreement terms | Must be reviewed before sending |
| **Create agreement version** | Generates a frozen agreement version and captures its approved plan, underwriting, price, and concession authority | Does not send it; blocked without current purchase authority |
| Agreement PDF | Opens the exact generated version for review | Requires generated agreement |
| **Request approval** | Sends the agreement version for internal approval | Revalidates the captured authority; stale source records require a new package |
| **Mark sent manually** | Records that staff delivered the exact agreement outside SignWell | Revalidates authority and creates a transaction event; the package stays authority-frozen until execution or audited withdrawal |
| **Withdraw sent package** | Voids an outstanding manually delivered agreement after staff confirms every recipient can no longer sign it | Requires an explicit confirmation and meaningful audit reason; active SignWell requests must be cancelled and reconciled instead |
| **Attest executed** | Records a completed externally signed agreement after a human explains how every required party's signature was verified | Requires the exact package document, `executed` evidence status, acceptable scan state, confirmation, and at least 10 characters of reason |
| **Record an already-signed contract** | Imports an agreement fully executed outside Stonegate, records its actual terms and immutable signed evidence, marks the House or Land transaction/deal/lead Under Contract/Executed, and attempts the canonical Dispositions handoff | Requires `contracts:record_executed` or legacy-compatible `contracts:modify`; intended standard roles are Acquisition Manager, Acquisition Representative, and Transaction Coordinator, while Owner, Founder/Operator, and CEO retain full authority; this permission grants no unrelated approval, send, lead, or Dispositions action |
| Executed agreement upload | Sends the exact PDF and contract facts together as `multipart/form-data` | `.pdf` file name, PDF content/header, acceptable scan state, and 1-byte-to-15-MB size required; the request does not expose facts in the URL or rebuild the document |
| Required import facts | Records seller name, buyer entity, purchase price, execution date/time, signature source, full-execution confirmation, and verification note | Names cannot be blank; price must be positive; time cannot be in the future; source is DocuSign, SignWell, PandaDoc, Adobe Acrobat Sign, manual signature, or Other; verification note is 10-500 characters |
| Optional import facts | Records assignment fee, earnest money, title/closing company, closing date, inspection period, earnest-money due time, due-diligence deadline, external reference, and contract notes | Optional amounts must be non-negative; inspection period is 0-120 days; external reference is limited to 255 and notes to 2,000 characters |
| Import entry points | Opens the one canonical form from the Pipeline Under Contract action, seller **Change pipeline stage**, seller **Contract & Deal**, or selected **Deals > Contract** | House and Land use the same importer; Pipeline movement uses the contract-recording permission, and Deals remains the Transaction Coordinator entry point when Leads editing is unavailable |
| Dispositions handoff result | Creates or safely reuses the case after the contract is recorded and reports whether setup is complete | The case opens immediately. Missing owner, plan, or mode appears as advisory **Needs setup** evidence with corrective links, not a blocking task; later configuration hydrates the same case rather than authorizing its creation |
| SignWell connection status | Shows whether API configuration is usable | Read-only |
| **Verify SignWell** | Tests the configured provider connection/template | Requires SignWell credentials and template ID |
| Seller signer / Company signer | Maps actual people to template placeholder roles | Required by template |
| **Send signature request** | Reserves the approved package, creates and saves an unsent SignWell draft, then sends that exact provider document | Requires valid signers, working provider, and authority that is still identical to the approved package snapshot; uncertain outcomes do not auto-create another document |
| **Resume saved draft** | Sends an already persisted, reconciled provider draft without creating a replacement document | Appears only for a `draft` envelope; configuration and current authority are rechecked |
| **Attach verified draft** | Recovers a provider draft created during the narrow response/persistence crash window | Requires the exact unsent SignWell document ID; provider metadata, mode, and signer emails must match the reserved transaction/package |
| **Abandon empty intent** | Releases a stale creation intent only after staff verifies no matching provider document exists | Available only for placeholder intents after a five-minute safety interval; requires confirmation and a meaningful audit reason |
| **Reconcile signature status** | Pulls the latest provider status and completed files | Requires an existing signature request |
| Signature status | Shows prepared, sent, viewed, completed, declined, or failed | Provider-derived |

### Documents

| Control or item | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Document type | Classifies contract, amendment, title, closing, assignment, photo, or other file | Required |
| File upload | Attaches a document to the transaction | File limits apply |
| Evidence status | Marks the upload as **Final / reference copy** or **Fully executed signed copy** | Use executed only after every required party signed the exact package document |
| Contract package | Links the upload to the frozen agreement version it supports | Required before that document can support manual execution |
| **Upload privately** | Stores the file, checksum, retention facts, scan state, and audit metadata | An upload alone does not mark a contract executed |
| Download | Opens the permission-checked stored document | Requires document access and a retained file |
| Fact confirmation | Confirms a material value or fact supported by the document | Requires reviewer permission |
| Private evidence marker | Restricts sensitive financial or identity documents | Visibility depends on role |

### Parties

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Party type | Identifies seller, buyer, title company, attorney, agent, lender, or other participant | Required |
| Name / Company | Identifies the party | Name or company required |
| Phone / Email | Stores communication details | Format validation applies |
| Notes | Records role-specific context | Internal |
| **Add party** | Links the party to the transaction | Requires transaction edit access |
| Edit/remove | Updates or unlinks the party | Does not erase historical documents or communications |

### Timeline

| Item | Purpose | Availability |
| --- | --- | --- |
| Status event | Shows transaction stage changes | Read-only |
| Contract event | Shows generation, approval, send, view, and execution | Read-only |
| Document event | Shows uploads and evidence confirmation | Read-only |
| Closing event | Shows milestone and funding activity | Read-only |
| Transaction Copilot output | Shows reviewed coordination risks and next actions | Draft-only recommendation |

## Buyers

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Search | Finds buyers through the server-backed Buyer Network search | Searches the complete organization-scoped result set, not only the currently loaded page |
| Status filter | Limits the list to Needs Review, Active, Paused, Do Not Contact, or Archived | Filter only; it does not change buyer status |
| Relationship owner filter | Limits the list to the employee responsible for the investor relationship | Available owners are organization scoped |
| Source filter | Limits the list by manual, import, or provider provenance | A missing provider reference does not make outside data staff-verified |
| Result total / pagination | Shows the matching count and loads the previous or next server result page | Changing search or filters returns to the beginning of that result set |
| Buyer row | Opens the buyer profile | Requires buyer access |
| Summary / Criteria & Markets / Active Deals / Proof & Capacity | Changes the selected buyer section and updates the URL | Navigation only |
| Close buyer details | Returns to the buyer list | Phone layout only |
| **Add buyer** | Opens the new-buyer drawer | Requires buyer edit permission |
| Name / Company | Identifies the investor or organization | Name is required; company is optional |
| Phone / Email | Stores canonical contact methods | At least one usable phone number or email address is required |
| Relationship owner | Identifies the staff member responsible for verification and follow-up | Must be an eligible user in the same organization |
| Source / source reference | Records whether the buyer was entered manually, imported, or supplied by a provider | Preserve the external reference when available; provenance is not verification |
| Last verified | Records when staff most recently confirmed the buyer profile | Enter a factual verification date, not the import date unless verification occurred then |
| Duplicate review | Shows likely normalized phone or email matches before creation | Resolve every shown match before saving |
| **Use existing** | Opens the matching buyer instead of creating another record | Preferred when the identity belongs to the same investor |
| **Create separate** / reason | Allows a genuinely distinct buyer record despite a likely match | Requires an explicit factual reason and is audited; no silent merge occurs |
| **Edit buyer** | Opens the selected profile for authorized changes | Requires buyer edit permission |
| Markets | Records geographic buying areas | Used for matching |
| Property types | Records asset preferences | Used for matching |
| Price minimum/maximum | Records acquisition budget | Used for matching |
| Strategy | Records flip, rental, wholesale, development, or other focus | Used for matching |
| Funding type | Records cash, hard money, private, conventional, or other source | Used for readiness |
| Proof of funds status | Shows missing, submitted, verified, rejected, or expired | Verification requires evidence |
| Criteria version | Preserves each saved criteria revision | New criteria replace the current working version without deleting prior versions |
| Status: **Needs Review** | Holds new, incomplete, or unverified buyer records | Excluded from future automated matching |
| Status: **Active** | Marks a reviewed buyer as available for current opportunities | The only lifecycle status eligible for future automated matching |
| Status: **Paused** | Retains a relationship that should not receive current opportunities | Excluded from matching |
| Status: **Do Not Contact** | Records an opt-out or other documented contact restriction | Excluded from matching; do not use as a temporary pause |
| Status: **Archived** | Retains an out-of-workflow buyer outside normal active results | Excluded from matching |
| Call/SMS permission state and evidence | Shows the latest decision and its supporting history for the applicable contact path | Append evidence; never infer permission from the presence of a phone or email |
| Inbox conversation | Opens or creates the canonical buyer communication thread | Profile contact edits synchronize the linked contact and conversation identity |
| Reliability/status | Records performance and relationship state | Staff-managed; lifecycle status is separate from reliability |
| Notes | Captures buyer-specific context | Internal |
| **Save buyer** | Creates or updates the buyer profile and current criteria version | Disabled while saving or when validation/duplicate review is unresolved |
| **Archive buyer** | Removes the buyer from normal working views and future matching | Preserves profile, criteria versions, provenance, permission, Inbox, offer, and deal history |
| **Restore buyer** | Returns an archived buyer to a reviewable lifecycle | Review identity, criteria, permission, and status before making the buyer Active |

The Buyer Network does not include a merge control. Use the existing record when a duplicate match
represents the same investor; use **Create separate** only for a truly distinct record and document
why. Live InvestorLift synchronization and automated outreach remain disabled, so no Buyer Network
control sends an InvestorLift campaign. Buyer profile maintenance also does not trigger Stonegate's
governed House Outreach workflow. The separate **InvestorLift** disposition view supports only the
manual exact-artifact handoff and reviewable evidence workflow described below.

## Dispositions

Select **Dispositions** in the left menu to open the buyer-placement desk. Active Deal cards expose
direct **Packet**, **Find buyers**, **Reach out**, and **Offers** navigation. House uses the primary
**Packet**, **Find buyers**, **One-to-one**, **Bulk outreach**, and **Offers & closing** workbenches.
Use **More > External distribution** for the manual InvestorLift handoff and **Deal Finance** for
reconciliation. Land uses **Packet**, the asset-aware **Find buyers** pool, and supported pre-close
engagement controls only.

### Case And Package

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Case row | Opens a disposition case | Requires disposition access |
| **Open disposition case** | Creates or recovers the buyer-placement workspace from saved contract facts | Requires `deals:edit` and a qualifying executed House or Land transaction. Asking price and internal minimum are optional; supplying private-economics overrides requires private-economics access, while users without it can still open the advisory shell without seeing those values |
| **Needs setup** case | Keeps an executed House or Land case visible when owner, compensation-plan, or operating-mode setup is incomplete | The case is created immediately; **Resolve setup** opens the setup route and **Open deal** opens the source record. Missing setup is advisory and does not disable otherwise authorized case work |
| Launch readiness | Shows ready, warning, incomplete, and stale status plus source freshness, conflicts, unknowns, and remediation links | Informational checklist only; never disables buyer, engagement, offer, or other disposition work |
| **Build with Stonegate** / **Use existing PDF** | Chooses whether Stonegate generates the draft PDF or preserves a completed external investor packet as the draft artifact | House supports both paths; Land supports the exact existing-PDF path until the dedicated generated Land packet is released. An unapproved artifact may be shopped only with its visible **Preliminary** state preserved |
| Classified evidence | Groups claims as Verified fact, Seller statement, Provider signal, Stonegate analysis, or Unknown | Classification and provenance are read-only package evidence |
| Investor-visible preview | Shows the facts and pricing that may appear in buyer summaries and the PDF | Must not contain private floors, seller notes, or unsupported claims |
| Private economics | Shows purchase basis, buyer asking price, minimum acceptable amount, desired assignment fee, and approval authority | Visible only with the private-economics permission; never recipient-visible |
| Deterministic buyer summaries | Previews email and SMS wording from the same saved public facts | Preview only; no message is sent |
| **Build draft** / **Rebuild draft** | Creates a new immutable package version and generated PDF from the current saved evidence and source fingerprint | House-only **Build with Stonegate** path; requires `deals:edit`; private overrides require private-economics access |
| **Upload external packet draft** | Stores the **Use existing PDF** upload byte-for-byte as the immutable artifact for a new package version, plus its hash, source note, and scan state | House and Land; requires `deals:edit`, a valid PDF no larger than 15 MB, and current version concurrency; it supersedes an older draft but never replaces CRM readiness, matching, private economics, or deterministic summaries |
| Draft external PDF review / version **PDF** | Opens the exact uploaded artifact before approval | Requires `deals:edit` or `dispositions:approve_packages`; blocked unless scan state is `clean` or `not_configured`; ordinary deal-view permission alone is insufficient while it is unapproved |
| **Approve vN** | Opens approval for the exact latest generated or uploaded draft | Requires `dispositions:approve_packages`, an acceptable scan state, current-version concurrency, and recorded source-fingerprint provenance; readiness findings remain visible but advisory |
| Approval reason and attestation | Records what the approver reviewed and confirms no private or unverified claim is presented as fact | Both are required before **Approve exact version** |
| **Download approved vN PDF** / version **PDF** | Downloads the exact PDF bytes stored for that version | Approval does not regenerate the artifact. Unapproved use retains the Preliminary label and narrower draft access; if source facts later drift, the current download also labels the unchanged bytes Preliminary |
| Version history | Shows immutable version number, status, evidence currency, fingerprint, approver, reason, and artifact | A material source change marks the prior approval non-current for buyer-facing artifact use; it does not lock unrelated buyer work |

Secure links use the exact saved artifact. Currentness is recomputed on every access: a link issued
from a Preliminary package stays Preliminary, and an approved/current link downgrades visibly to
Preliminary if its package or source facts later drift. The label can change without rewriting the
hash-bound bytes. Stonegate's saved CRM facts continue to supply readiness, buyer matching, private
economics, and email/SMS summaries.
For Land, this enables the shared package and buyer-pool workflow without enabling residential-only
outreach, Offer Room, buyer selection/funding, Reconciliation/closing, InvestorLift, or
Stonegate-generated Land packet controls.

### Buyer Matching

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Internal match list | Ranks stored buyers against market, property, price, strategy, funding, and performance | Shows the full available pool; readiness and proof gaps are warnings, and the operator may choose any appropriate buyer |
| Match explanation | Shows why a buyer ranked highly or poorly | Read-only |
| **Refresh buyer ranking** | Refreshes the buyer recommendation using current case facts | Located in **Find buyers**; available while setup or package checklist items are incomplete; output is advisory |
| DealMachine plan and credits | Shows live connection, paid plan, reset date, available credits, saved tier results, deal usage, and monthly usage | Discovery is House-only and independent from disabled DealMachine underwriting comps |
| Best-Fit 10 / Expand Nearby 20 / Search Regional Investors 40 | Progressively widens a deal-specific search for up to 10, 20, or 40 additional net-new candidates | Each tier unlocks only after the prior tier completes; 30/60/120 tier caps, 250 per deal, and 2,000 per month are enforced by the server |
| **Preview search estimate** | Validates the exact tier request and shows DealMachine's current estimate without consuming credits | Requires buyer-edit and deal-edit permissions, a connected paid plan, and enough authority for the displayed 30/60/120 binding tier ceiling; package/readiness state is shown but is not a gate |
| **Search up to...** / **Reuse saved results** | Confirms the displayed estimate and exact request fingerprint, stages recent purchaser candidates, records actual provider credit use, or reuses the current saved run for zero new credits | Disabled until a current preview succeeds; stale or changed requests or estimates, insufficient credits, and duplicate concurrent requests are rejected |
| Credit reconciliation required | Stops another paid request when a prior run was interrupted or returned incomplete credit telemetry | The owned Buyer Network remains usable; reconcile the provider attempt before searching again |
| Candidate result | Shows provider evidence and match context before a conversion decision; DNC-tagged phone numbers are excluded | Not yet a Stonegate buyer record |
| **Shortlist** / **Pass for this deal** | Records the candidate's durable fit decision for this disposition case | A pass requires a reason, keeps the buyer out of the current prepared outreach pool, sends nothing, and does not change the Buyer Network lifecycle or create a permanent contact restriction |
| **Undo pass** / change to **Shortlisted** | Reverses the current deal-specific pass while retaining its audit history | Requires a reason for the changed decision; the buyer can immediately return to ordinary deal work, subject only to live communication controls |
| **Approve into network** / **Link reviewed match** / **Reject result** | Creates a new Needs Review relationship, links evidence to a reviewed existing buyer, or rejects unusable provider evidence | Requires a meaningful human review reason; never activates or contacts a buyer automatically |
| Proof of funds upload | Attaches funding evidence with staff-entered institution, amount, and expiry | The current submitter attests to those values; there is no separate second-review step in this flow |
| **Verify POF** | Uploads the evidence and records the supplied verification facts | Authorized staff only; controlled launch acceptance must verify the operating review procedure |
| Buyer activity | Logs contact, interest, showing, pass reason, and follow-up | Requires a selected buyer, not a completed package or prior rank-order step |
| **Log activity** | Saves the buyer touchpoint | Does not send communication unless explicitly using a channel action |

### One-To-One Buyer Execution

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Current queue buyer | Presents one ranked canonical buyer for deliberate call execution | This focus view does not lock the separate full Buyer pool or another disposition task; use the Buyer pool when a different buyer should be worked next |
| Readiness and fit findings | Shows missing package facts, proof, conflicts, strengths, and suggested next work | Informational only; does not disable buyer selection, calling, follow-up, activity, or offer entry |
| **Call** / one-to-one SMS | Starts the selected company-channel action for the chosen buyer | Requires role access, a usable destination/sender and provider, and no STOP, Do Not Contact, suppression, or channel-permission restriction |
| **Text package** | Creates a time-limited link for the exact artifact and texts it to the chosen buyer | Requires an exact shareable artifact plus the same communication-integrity checks; incomplete/unapproved artifacts say Preliminary, and the link dynamically downgrades to Preliminary if source facts later drift. If unavailable, the operator can continue other buyer work |
| Outcome / follow-up controls | Records contact outcome, pass, interest, callback, showing, or next action | Requires truthful structured input and any applicable future date; independent of package/checklist completion |
| **Record offer** | Opens the canonical Offer Room entry for the chosen buyer | Available without completing earlier checklist or rank-order steps; saved terms must reflect the buyer's actual offer |

### Disposition Copilot

Open **Disposition Copilot** from the current Deal's **Disposition** or **Finance** context. The
drawer is House-only and draft-only. Viewing readiness requires deal visibility; generation and
review require deal editing plus private-economics access.

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Draft only** / external actions blocked | States the invariant authority boundary | Always true for DS9, regardless of broader AI policy |
| Pilot status | Shows cumulative sample coverage and quality/safety gates | Remains **NOT MET** until 50 decisive reviews across 10 cases, 10 applicable evaluations in each scored quality domain, and every gate passes; ignored drafts are excluded |
| Readiness and evidence gaps | Shows deterministic case blockers before generation | Read-only; resolve the source record rather than editing a model claim |
| **Generate recommendation** | Creates one structured, evidence-fingerprinted recommendation | Current House case, installed/enabled capability, deal edit, and private-economics access required |
| Recommendation selector | Opens a preserved historical draft | Historical drafts remain visible; stale evidence cannot be accepted or corrected |
| Saved citations | Identifies source type, source record, fact, status, and observation time for each material item | Every item requires scoped evidence; all drafts cite the current case/package, Buyer-scoped items cite that Buyer, and provider evidence is public/redacted |
| Package summary and gaps | Presents cited public-package guidance and missing evidence | Draft only; does not rebuild or approve a package |
| Buyer-match explanation | Shows cited strengths, conflicts, and disqualifiers for the current pool | Does not add, edit, suppress, qualify, or select a Buyer |
| Recipient, email, SMS, call-brief, and follow-up drafts | Prepares cited copy for human review | Does not create an Outreach revision, queue a provider operation, or send a message |
| Reply classification | Shows a cited label and confidence for interested, inquiry, pass, offer intent, offer, opt-out, wrong-person, or needs-review evidence | Does not change Buyer interest, suppression, offer, or communication state |
| Next-action proposal | Suggests a cited call, proof request, showing, counter, deadline, backup review, or bounded next step | Human-required; does not create or complete the operational action |
| Offer comparison | Explains cited execution risk across saved offers | Never selects or replaces a buyer, accepts an offer, or changes economics |
| Buyer-update proposal | Shows a cited preference or reliability change for review | Never mutates the Buyer record |
| Model and evidence trace | Shows evidence fingerprint, model, prompt, tokens, cost, latency, and timestamps | Read-only audit evidence |
| Quality evaluation | Records hallucination, package correction, match relevance, reply accuracy, next-action usefulness, and reviewer notes | Complete truthfully; evaluation never applies the draft |
| **Accept** | Records that the cited draft is useful as written | One review only; blocked when evidence is stale; a duplicate review returns a conflict; applies nothing |
| **Correct** | Saves a replacement structured output under the same citation and authority rules | One review only; blocked when stale or invalid; applies nothing |
| **Reject** | Records that the draft is wrong, unsupported, unsafe, or not useful | Available for stale drafts; preserves the original output |
| **Ignore** | Closes a draft without a quality judgment | Available for stale drafts; tracked separately and excluded from the measured quality sample |

No Copilot control sends, publishes, releases, applies, selects, accepts an offer, updates a Buyer,
changes economics, releases a contract, or marks funding. Perform an authorized action separately
through the package, Outreach, InvestorLift, Offer Room, Transaction, or Finance workflow.

### Disposition Performance

Open **Deals > Disposition > Performance** for the read-only DS10 House disposition report.

| Control | Effect | Boundary |
| --- | --- | --- |
| **Start date** / **End date** | Limits the evidence window | Dates filter retained evidence; they do not alter record timestamps |
| **Deals**, **Buyers**, **Agents**, **Sources**, **Markets**, **Asset classes** | Narrows the report to a selected saved dimension | Missing or ambiguous attribution remains unknown |
| **Apply filters** | Reloads the report with the selected filter intersection | Read-only; no workflow record changes |
| **Clear filters** | Returns to the full authorized report scope | Does not clear or delete saved evidence |
| Metric definition / provenance disclosure | Shows the canonical sources and definition supporting a metric | Use the source workflow to correct data; the report has no edit control |

**Known**, **Partial**, and **Unavailable** are evidence states. Unavailable is not zero. Activity
counts remain separate from selected, deposited, funded, and approved reconciled outcomes. Private
economics show **Restricted** without the applicable financial permission, and campaign-cost
measures stay unavailable without attributable cost evidence. The report cannot send outreach,
select a Buyer, record an outcome, fund a transaction, post finance, or rewrite historical
attribution.

### Bulk Outreach

The **Bulk outreach** workbench is available only for the current House disposition workflow and buyers in
Stonegate's owned Buyer Network. Its repository implementation uses existing Resend and Twilio
configuration; a visible ready state is not evidence that real provider acceptance has passed.

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Prepare recipient pool** | Records selected recipients against the exact package version, its approved/Preliminary state, and artifact hash as `prepared_not_sent` | Located at the top of **Bulk outreach**; sends no email or SMS and remains available while checklist work continues |
| Readiness | Shows package, artifact, recipient, evidence, and setup findings for the planned revision | Informational; incomplete/stale items do not lock the desk. If a package will be attached or linked, choose an exact usable artifact and preserve its Preliminary state when applicable |
| Recipient and channel selection | Selects the exact owned-network buyers and email and/or SMS paths included in the revision | The operator chooses the intended buyers; email plus SMS to one buyer counts as two deliveries |
| Delivery cap | Shows the number of recipient-channel deliveries in the current selection | Hard maximum of 25 per immutable revision |
| Email sender | Selects the active Stonegate Resend alias captured in the revision | Required when any email path is selected; inactive, non-Resend, or outbound-disabled aliases are unavailable |
| SMS sender | Selects the active Stonegate Dispositions buyer-relations Twilio line captured in the revision | Required when any SMS path is selected; acquisitions or inactive lines are not eligible |
| Email subject/body and SMS body | Defines the exact copy rendered and hashed for each selected delivery | Merge fields are limited to buyer name, company name, public property address, and package reference; no private economics are inserted automatically |
| Create review revision | Freezes recipient identity, destination, channel, sender, exact rendered copy, package fingerprint, PDF hash, and manifest for approval | Requires outreach-management permission and one to 25 structurally valid recipient-channel selections; it sends nothing |
| Revision preview and delivery rows | Displays the immutable content, destination, eligibility/exclusion reason, package state at preparation, package currentness now, status, attempt count, and Buyer Inbox link | Refresh before approval when the lock version or hash changed; later package/source drift marks the revision Preliminary without rewriting its frozen manifest or artifact |
| Approval reason and attestation | Records why the exact package, when included, and recipient/channel/message revision is approved | Requires outreach-approval permission, an affirmative attestation, current lock version, and matching approval hash; the standard Disposition representative has this narrow permission |
| Approve exact outreach | Approves the immutable revision | Approval does not send; at least one structurally eligible delivery is required |
| Release | Rechecks tenant/role scope, STOP/Do Not Contact/suppression, channel permission, destination, sender, and provider state, then queues eligible work | Requires outreach approval plus `dispositions:send_bulk_outreach` (or legacy/global bulk authority) and a meaningful reason; the standard Disposition representative has the narrow Dispositions permission, not global marketing bulk authority. Checklist completion and backup coverage are not release gates |
| Pause | Prevents remaining unsent deliveries from being claimed while preserving history | Available for queued, sending, or provider-degraded revisions; requires outreach-management permission and a reason |
| Resume | Rechecks the approved revision and current delivery eligibility before queueing remaining work | Available only for paused or provider-degraded revisions; the standard Disposition representative may resume with a reason |
| Cancel unsent | Permanently cancels remaining prepared, approved, queued, or safely retryable work without erasing sent history | Requires outreach-management permission and a reason; it cannot recall provider-accepted messages |
| Retry failed | Requeues only failures Stonegate has classified as safely retryable after a fresh preflight | Available to the authorized Disposition representative; never use it for `delivery_unknown` SMS |
| Buyer Inbox link | Opens the canonical buyer conversation for a delivery or safely matched reply | Appears after the delivery has a conversation; ambiguous replies create reconciliation work instead of an automatic buyer-state change |

Delivery and reply status updates are asynchronous. Stonegate may show prepared, approved, queued,
claimed, provider-accepted, sent, delivered, failed, delivery-unknown, suppressed, opted-out,
replied, or cancelled outcomes. No Outreach control accepts an offer, selects a buyer, changes deal
economics, sends through InvestorLift, or enables Land outreach.

Package currentness is recomputed before provider delivery. If source facts drift after the exact
revision was prepared or approved, the recipient-visible attachment/current state is
**Preliminary** while the message, recipients, hash, and PDF bytes remain the approved immutable
revision.

### External Distribution: InvestorLift Manual Handoff

The **More > External distribution** view is available for a House disposition case. It is a guided manual handoff,
not a live integration: no control calls InvestorLift, publishes a campaign, imports a buyer, or
claims that God Mode or Artemis data is synchronized.

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Manual-only / No live sync | States the verified provider boundary and remaining contract blockers | Informational; no credential is required for this manual foundation |
| Five-step handoff guide | Shows Prepare, Approve exact handoff, Download, Publish manually, and Record and review | Progress is based on Stonegate records, not a provider API response |
| **Prepare latest package** | Creates an immutable public-only provider revision and checksum from the exact usable House package selected for publication | Requires deal-edit plus disposition-management access and an exact artifact; an incomplete/unapproved source remains Preliminary. A new revision supersedes every earlier draft or approved provider release |
| **Reload Stonegate state** | Reloads only Stonegate's saved package, revision, link, event, and operation state | Does not query InvestorLift |
| **Review** / **Approve exact handoff** | Opens the exact payload and records a separate release approval, attestation, and reason | Requires disposition outreach-approval access, which the standard Disposition representative has; only the latest draft can be approved |
| Revision **Download** | Downloads the exact approved JSON bundle | Only the latest approved revision is downloadable; currentness is recomputed at download, so source drift adds the Preliminary filename/manifest state without changing the frozen payload. Private Stonegate economics and seller contact data are excluded |
| **Record manual publication** | Saves the property ID, HTTPS InvestorLift URL, status, and note after staff publish the bundle outside Stonegate | Requires the latest approved revision and the current listing lock version; exact retries are idempotent |
| **Stage provider evidence** | Saves an inquiry, engagement, or offer as checksummed review-required evidence | Available only after the current revision's manual publication is recorded; an offer requires an amount |
| **Save review** | Marks staged evidence reviewed or dismissed with an optional note | Never creates or activates a Buyer, selects a buyer, accepts an offer, sends a response, or changes the deal |
| **Record manual status check** | Saves the provider status and optional staff-observed ID, URL, or note | Manual observation only; no provider request is made |
| **Export history** / **JSON** / **CSV** | Downloads the preserved public revision, link, event, review, and operation history | Requires deal-view access; exports exclude private Stonegate economics |
| **Disconnect manual handoff** | Stops additional handoff activity while preserving all Stonegate history | Requires deal-edit plus disposition-management access, attestation, and reason; a disconnected listing cannot be silently reactivated |

An older InvestorLift link may remain visible after a newer revision is prepared, but it is reference
history only. Staff must publish and record the current approved revision before adding new provider
activity or status observations.

### Offers And Closing

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Offer comparison cards | Compares price, EMD, due diligence, contingencies, close date, funding, proof, reliability, risk, and execution evidence | House cases only; evidence and ranking are advisory |
| Proof coverage and risk flags | Explains expired or insufficient proof, weak deposit, incompatible timing, contingencies, or buyer-history risk | Read-only evidence; a flag never rejects or selects an offer automatically |
| **Record offer** | Saves normalized terms and creates immutable revision 1 | Requires deal editing, an available buyer, amount, funding context, and a unique request key |
| **Revise offer** | Saves a new immutable terms/risk revision | Requires the current offer lock version, a viable offer, and a change reason |
| **Record negotiation** | Appends an inbound, outbound, or internal negotiation event | Does not change buyer selection by itself |
| Primary and backup selectors | Defines one primary and any available different-buyer backups | A primary may be selected without backup coverage; missing backups, proof, and other readiness findings stay visible as advisory risk |
| **Approve buyer selection** | Creates a versioned human-approved selection and freezes reviewed evidence per slot | Requires `dispositions:approve_buyer_selection`; the standard Disposition representative has this permission. AI cannot approve it |
| Current coverage | Shows primary, ranked backups, their reviewed offer amount, and ready/provisional evidence | Read-only; provisional backup findings remain visible and advisory |
| Closing checkpoint row | Shows response, agreement, signature, deposit, access, title, closing, or other deadlines and labels its scope as **Whole deal** or the related buyer | House cases; manual rows may exist before buyer selection |
| **Add milestone** | Creates an Offer Room-specific deadline with owner, notes, evidence, and either whole-deal or recorded-offer scope | Available throughout an active House disposition case; a current primary/backup scope follows that selection, while whole-deal and other recorded-offer rows are independent. Use Transaction for canonical closing/title/access checklist dates |
| **Complete** / **Waive** | Completes an Offer Room milestone or documents a supported buyer-deposit waiver | Canonical Transaction/checklist rows are read-only here; deposit completion requires evidence and an authorized waiver requires a substantive note |
| **Update in Deal / Transaction** | Opens the canonical source for a Transaction or checklist-controlled milestone | Prevents divergent closing records |
| Deadline alert | Shows one versioned alert for a missed checkpoint | Created by the worker; acknowledgement records review but does not complete the milestone |
| **Acknowledge** | Records who accepted responsibility for the alert and why | Open alerts only; the original due date and missed evidence remain |
| Next buyer (optional) | Shows every other viable recorded offer on the case with execution/risk evidence, including offers that were never approved backups | Proof, price, match, timing, and missing-backup findings remain visible warnings; select any structurally viable offer or leave the choice empty |
| **No replacement now - record outcome and reopen shopping** | Records the primary outcome without choosing another buyer | Supersedes the active selection, clears active buyer coverage, returns the case to offer shopping, and preserves the old selection/checkpoint/outcome history |
| **Replace primary** | Activates the chosen viable recorded offer and records the prior buyer outcome/cause/evidence | Requires buyer-selection approval, current selection and replacement-offer lock versions, a different same-case viable offer, and no unresolved live assignment obligation; prior backup status is not required |
| **Record outcome** | Records pass, withdrawal, fallout, or retrade without erasing evidence | Buyer history changes only for buyer-responsible failure/retrade; completed close is funding-driven |
| Negotiation / selection / outcome history | Shows immutable human and buyer decision history | Read-only |
| Funded close gate | Atomically records the selected buyer's completed close and history | This hard truth boundary requires the selected buyer, an agreement bound to the same buyer and offer economics, matching assignee identity, executed evidence, and deposit evidence or a documented authorized waiver |

### Deal Finance Reconciliation

Open reconciliation through **Deal Finance** from the Dispositions context. The context bar keeps a
direct return to the active Dispositions case; reconciliation is not a primary Dispositions tab.

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Actual assignment revenue | Records funded gross revenue | Must match closing evidence |
| Transaction deductions | Records approved deal-specific costs | Evidence and category rules apply |
| Role credits | Records who earned acquisition, closer, disposition, management, or other credit | Must match operating-model rules |
| Payout preview | Calculates commission and company allocation from current facts | Preview only |
| **Approve reconciliation** | Freezes the reviewed close economics | Authorized role only |
| **Post payout** | Creates finance obligations/ledger effects | Requires approved reconciliation and funded closing |
| Export | Downloads approved reconciliation detail | Requires export permission |

## Finance

Finance combines operational revenue and commissions with Stonegate's internal double-entry
books. Sensitive vendor, banking, tax, and accounting controls are permission-gated.

### Reporting And Operational Ledger

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Reporting period | Switches between all time, recent 30 days, and recent 90 days | Refreshes the page totals |
| Finance Copilot | Drafts cash, margin, exception, and control observations | Advisory; does not post entries or pay anyone |
| Revenue exception link | Opens the source lead or disposition reconciliation | Requires access to the source record |
| Revenue source / Amount / Date / Status / Lead | Creates an operational revenue record | Required values must be valid |
| **Record revenue** | Saves expected or collected revenue evidence | Does not automatically equal a posted bank transaction |
| Deduction category / Amount / Date / Lead | Records a deal-specific deduction | Evidence recommended |
| **Record deduction** | Saves the deduction used in economics | Requires finance input access |
| Compensation rule name / Role / Basis / Rate / Dates | Defines a versioned commission rule | Requires compensation policy permission |
| **Create compensation rule** | Saves a rule version | Does not alter already approved historical payouts |
| Marketing source / Campaign / Amount / Month | Records campaign spend | Requires finance input access |
| **Record marketing spend** | Saves spend for performance reporting | Does not replace bank reconciliation |
| **Ledger entry controls** | Expands manual operational forms | Authorized users only |

### Accounting Setup

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Company legal/name settings | Defines the entity represented by the books | Accounting policy manager only |
| Fiscal year and accounting basis | Defines reporting policy | Policy change affects future reporting behavior |
| Default accounts | Maps revenue, cash, receivable, payable, expense, commission, and equity behavior | Requires installed chart of accounts |
| Tax settings | Records accounting/tax configuration used by reporting | Staff must confirm with the company's tax professional |
| Books start date / opening settings | Defines when internal books become authoritative | Should match migration evidence |
| **Save accounting setup** | Persists accounting policy | Requires `accounting:manage_policy` |
| Install/default setup action | Creates Stonegate's initial chart and mappings | Available only when setup is incomplete |

### Vendor Accounting

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Add vendor** | Creates a contractor, vendor, closing service, funding partner, or other payee | Requires vendor-management permission |
| Name / Company / Type | Identifies the vendor | Name required |
| Email / Phone / Remittance address | Stores payment/contact details | Sensitive fields are role-restricted |
| Default expense account | Supplies the normal bookkeeping category | Can be changed per bill |
| Payment terms | Calculates normal due timing | Nonnegative days |
| W-9 status and private evidence | Stores tax-document readiness without exposing it broadly | Requires evidence permission |
| Vendor status | Activates or deactivates future use | Historical bills remain |
| Bill vendor / Number / Dates / Description | Defines a vendor bill | Vendor and description required |
| **Add line** | Adds another expense allocation to the bill | Each valid line needs amount and account |
| Remove line | Removes an unsaved bill line | At least one valid line required |
| **Save draft bill** | Creates a reviewable payable draft | Does not approve or pay it |
| **Submit / Approve / Reject bill** | Advances or decides the bill workflow | Approval permission required for decisions |
| Document type / File / Related bill | Attaches invoice, receipt, W-9, payment evidence, closing statement, contract, or other evidence | Requires supported file |
| **Upload evidence** | Stores the protected vendor document | Evidence permission required |

### Banking

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Add bank or card account** | Creates an internal account record for checking, savings, credit card, or other source | Requires banking-management permission |
| Name / Institution / Type / Last four | Identifies the account without storing online-banking credentials | Name required; last four must be four digits |
| **Preview CSV statement** | Parses a statement using selected column names without committing it | Requires CSV and account |
| Date / Description / Amount / Balance / Transaction ID columns | Maps the uploaded CSV format | Required mappings must match headers |
| Opening / Closing balance | Adds statement control totals | Optional during preview; needed for reliable reconciliation |
| Preview results | Shows valid, duplicate, and invalid rows | Review before import |
| **Import reviewed statement** | Creates bank transaction records from accepted rows | Disabled when preview reports blocking errors |
| Posted journal selector | Chooses a same-amount posted journal candidate | Unmatched bank row only |
| **Match journal** | Links cleared cash to the selected journal | Requires a selected compatible journal |
| **Ignore** | Marks a non-bookkeeping bank line as intentionally ignored | Requires banking permission |
| Statement/date range / balances | Defines a bank reconciliation | Required |
| **Prepare reconciliation** | Calculates matched, unresolved, and balance differences | Requires imported bank activity |
| **Approve** | Finalizes a balanced reconciliation | Available only in review state; unresolved difference blocks approval |

### Posting Rules, Drafts, And Obligations

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Posting rule | Maps operational events to accounting treatment | Accounting policy manager |
| Enable/disable rule | Controls whether future eligible events generate drafts | Does not erase prior journals |
| **Generate draft** | Creates a proposed journal from a supported source event | Requires a configured rule and source |
| Draft review | Shows source, accounts, debits, credits, and evidence | Prepare permission |
| **Approve draft** | Approves the generated accounting treatment | Approver must be authorized |
| **Post draft** | Creates the posted journal | Requires approval and an open period |
| Obligation type / Counterparty / Amount / Account / Due date | Creates a commission, vendor, tax, reimbursement, or other payable | Required values vary by type |
| **Create obligation** | Saves the payable for approval/payment tracking | Prepare permission |
| **Approve payment** | Authorizes an obligation for payment | Approval permission |
| **Mark paid** | Records payment facts and accounting source | Requires payment evidence/authorized role |

### General Ledger

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Accounting period | Selects the month/period being managed | Read-only unless period manager |
| **Send to review** | Changes an open period to review | Requires period-management permission |
| **Reopen** | Returns an eligible period to open | Requires period-management permission |
| **Close** | Prevents ordinary new posting to the period | Review requirements must be satisfied |
| **Lock** | Finalizes the closed period against normal changes | Highest-control state |
| Entry date / Source / Source reference / Memo | Defines a manual journal | Date and memo required |
| Evidence notes | Explains why the manual journal is justified | Recommended and audited |
| Account / Debit / Credit / Line memo | Defines each journal line | Entry must balance and use valid accounts |
| Add journal line | Adds another debit/credit row | Repeatable |
| Remove journal line | Removes an unsaved row | At least two valid lines normally required |
| **Save draft journal** | Creates a reviewable, unposted journal | Requires prepare permission and balanced lines |
| **Approve** | Approves a draft journal | Requires approve permission and separation rules |
| **Post** | Posts an approved journal into an open period | Requires post permission |
| **Reverse** | Creates a linked reversing entry instead of deleting history | Requires authorized reason and eligible posted entry |

### Reports And Tax Copilot

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Report start / end | Defines the reporting window | Start must not follow end |
| **Run reports** | Refreshes profit and loss, balance sheet, cash flow, and supporting schedules | Accounting setup required |
| **Export CPA package** | Downloads review materials and supporting evidence references | Requires report access |
| Tax Copilot | Flags possible categories, missing evidence, tax readiness, and questions for a tax professional | Advisory only; does not file taxes or make final tax determinations |
| Copilot evidence | Opens the books or documents supporting an observation | Requires source access |
| **Accept / Correct / Reject** | Records human review of Tax Copilot guidance | Does not post a journal by itself |

## Marketing

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Reporting period | Changes the performance comparison window | Refreshes metrics |
| Marketing Copilot | Drafts channel performance, conversion, and budget observations | Advisory only |
| Source/campaign row | Opens the underlying campaign or lead cohort | Requires related access |
| Funnel metrics | Separates valid Step 1 address leads, Step 2 contact-completed leads, address-to-contact rate, appointments, contracts, and revenue | Read-only; optional enrichment is not another Meta outcome |
| Cost metrics | Separates cost per address lead from cost per contact-completed lead, then shows acquisition cost and return | Depends on linked spend and revenue |
| Web performance | Shows Core Web Vitals and public-site health | Read-only monitoring |
| Experiment ledger | Lists draft, running, paused, and completed homepage CTA tests | Visible to Marketing reporting roles |
| **New test** | Opens a controlled two-version CTA experiment draft | Owner or Marketing Manager |
| Experiment key / Name / Hypothesis | Identifies the test and states why the change should affect the selected outcome | Required before creation |
| Primary business outcome | Selects submitted lead, qualified lead, appointment, signed contract, or funded deal as the planned decision metric | Select before launch; qualified lead is the default |
| Current CTA / Test CTA | Defines the only public difference in the first experiment surface | Both versions receive 50% stable assignment |
| Sessions per version / Minimum runtime | Defines when the report can become ready for human review | At least 20 sessions per version and seven active days |
| Decision rule | States in advance how downstream evidence will be weighed | Required before launch |
| **Create draft / Save draft** | Saves the experiment without affecting the public site | Draft only |
| **Start test** | Opens the test to new homepage assignments | Blocked when another test is running on the same surface |
| **Pause / Resume** | Stops or restarts new assignments while preserving active runtime and evidence | Running or paused test |
| **Complete test** | Stops the test and records the owner's final evidence-based decision | Does not automatically rewrite the permanent CTA |
| Variant report | Compares device mix, sessions, leads, qualification, appointments, contracts, funded deals, revenue, and primary rate | Read-only; never auto-declares a winner |
| Public proof library | Lists reviews, seller stories, completed purchases, and statistics with publication and permission status | Visible in Marketing; editing requires public-proof management permission |
| **New proof** | Opens a clean evidence-backed draft | Owner or Marketing Manager |
| Public content fields | Define the approved title, text, attribution, location, rating, or metric visible to sellers | Only editable while the record is a draft |
| Source URL / Internal evidence reference | Records where the claim can be verified | At least one is required before review |
| Permission status / Permission evidence | Records usage consent or why consent is not required | Reviews and seller stories require Granted |
| Material connection / Visible disclosure | Records and discloses employee, family, incentive, or other relevant relationships | Disclosure blocks publication when the connection is not blank |
| **Save draft** | Saves corrections without publishing | Draft only |
| **Submit for review** | Locks the draft and validates basic source evidence | Does not publish |
| **Publish** | Performs final evidence checks and adds the sanitized record to the public feed | In-review records only; refresh can take five minutes |
| **Unpublish and edit** | Immediately returns published proof to draft before correction | Removes it from the public feed |
| **Retire** | Preserves evidence and history while removing proof from public use | Published or in-review records |
| **Prepare conversion events** | Creates pending attribution processing work | Requires marketing operations permission |
| **Process next** | Processes the next pending event | Appears only when server-side processing is enabled |
| Offline export | Downloads conversion data for supported ad-platform workflows | Requires marketing export permission |
| **Accept / Correct / Reject** on Copilot | Records review of marketing recommendations | Does not change budgets automatically |

## Company & Policy

These controls are split by ownership: **Settings > Company** contains setup, seats,
counterparties, and role acknowledgement; **Settings > Finance Policy** contains Active, Pending,
and History; **Settings > Markets & Territories** contains Launches. The legacy Company & Policy
route redirects to Finance Policy.

### Setup And Team Seats

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Install standard setup** | Creates Stonegate's baseline seats, roles, compensation structure, and checklist definitions | Owner only; intended for an uninitialized workspace |
| Seat status | Marks a position planned, recruiting, active, covered, or inactive | Owner/operations manager |
| Primary user | Assigns the person normally responsible for the seat | Requires an active user |
| Backup user | Assigns coverage | Cannot provide permissions the backup user does not have |
| Coverage notes | Explains temporary or shared coverage | Internal |
| **Save** | Persists seat coverage | Management only |

### Counterparties And Role Acceptance

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Counterparty type | Selects closing attorney, title company, funding partner, inspector, or other partner | Required |
| Market | Limits the partner to a market or company-wide use | Optional |
| Contact/company/email/phone | Identifies the external partner | Contact name required |
| Verification notes | Records how the partner was checked | Required for meaningful verification |
| **Add for verification** | Creates a pending counterparty | Does not mark it verified |
| **Verify** | Approves the partner for operational use | Authorized manager |
| **Deactivate** | Removes the partner from future selection | Preserves history |
| Team member / Assigned role / Manual version | Creates a role-manual acceptance request | Required |
| **Assign role setup** | Gives the user a setup checklist for that role | Does not complete acceptance |
| **Return** | Sends submitted acknowledgement back for changes | Manager |
| **Approve** | Accepts the submitted role setup evidence | Manager |
| **Revoke** | Removes a previously approved acknowledgement | Manager |

### Compensation And Work Credit

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Plan name | Names a new policy version | Required |
| Acquisition reserve | Sets the planned per-deal acquisition/marketing reserve | Used in policy economics |
| Target company margin | Sets the target retained company share | Management policy |
| Lead manager / Acquisitions closer / CEO management | Sets role percentages | Draft policy values |
| Human dispositions | Sets the human-led disposition share | Draft policy value |
| Transaction coordinator / cap | Sets TC share and maximum | Draft policy value |
| AI-managed dispositions / oversight min/max | Sets policy for reduced human disposition workload | Does not let AI approve payouts |
| Policy notes | Explains assumptions and exceptions | Audited |
| **Create draft version** | Saves a new compensation policy without activating it | Owner/compensation permission |
| **Activate** | Makes the selected draft the current policy | Does not rewrite historical approved calculations |
| Lead / Team member / Role / Credit share | Defines who performed the work for a deal | Required |
| Contribution evidence | Explains the contribution | Required |
| **Submit for approval** | Creates proposed role credit | Does not create a payout |
| **Approve / Reject** | Decides proposed work credit | Authorized manager |

### Market Launches

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Market | Selects the territory being prepared | Requires configured market |
| Accountable owner | Assigns launch responsibility | Active user required |
| Launch notes | Adds market-specific context | Optional |
| **Create launch checklist** | Creates the standard readiness list | Management only |
| Checklist selector | Opens a market checklist version | Read-only navigation |
| Item status | Sets pending, in progress, blocked, or complete | Locked after launch approval |
| Responsible user | Assigns the checklist item | Active user |
| Evidence notes | Records proof, link, or decision | Required by important readiness items |
| **Save** | Persists a checklist item | Disabled after approval |
| **Approve launch** | Freezes a ready checklist as management-approved | Available only when required items are complete |

## My Setup

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Assigned role manual | Shows the plain-language responsibilities and allowed work for the signed-in user | Every active user |
| Setup item | Shows required reading, practice, access check, or evidence | Based on assigned role |
| Evidence | Records what the employee completed or tested | Required by some items |
| Employee notes | Adds context or questions | Optional |
| **Submit for review** | Sends the role acknowledgement to management | Blocked until required setup items are addressed |
| Acceptance status | Shows assigned, in progress, submitted, approved, returned, or revoked | Read-only |

## Help

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Blue chat bubble | Opens Stonegate Help over the current OS page | Bottom-right of every signed-in OS workspace |
| Close | Closes the panel without changing the current OS page | Open panel |
| Suggested question | Places a role-relevant example in the composer | Available before or after a conversation |
| Question | Accepts a software, setup, role, or workflow question | Three to 500 characters |
| Ask arrow / Enter | Sends the question to authenticated documentation retrieval | Disabled while loading, answering, or when too short |
| Shift+Enter | Adds a line without submitting | Composer only |
| Answer | Safely formats paragraphs, numbered steps, bullets, bold control names, inline code, and source numbers | AI summary when available; manual fallback otherwise; model-provided HTML is never rendered |
| Answer row | Selects which answer's citations appear | Existing conversation only |
| Inline source number | Opens the matching approved document section used for that statement | Appears when the answer cites a valid returned source number |
| Source count | Shows how many approved sections support the answer and opens source view | Supported answer |
| Source summary | Opens the document title and heading path | Available for supported answers |
| Source disclosure | Expands the exact excerpt used | Citation panel |
| Back arrow | Returns from citations to the conversation | Source view |
| Follow-up question | Uses up to six recent turns to understand references such as “that,” “it,” or “the previous step” | Role boundaries are reapplied to the recent topic; conversation text is context, not an approved source |
| **New conversation** | Clears local question, answer, and follow-up context | Does not delete or change business records |

Help filters documents and sensitive topics by the signed-in role. It cannot read live operating
records or perform actions. Conversation context remains in the open browser session and is not
stored as a business record.

## AI Control

AI Control now lives at **Settings > AI & Automation**. The legacy `/os/ai` route redirects there.
It is the owner/administrator workspace for the existing Stonegate Copilot system.
It does not create a second AI system. Its views are **Copilots**, **Runtime**,
**Automation**, **Portfolio**, **Evaluations**, **Traces**, and **Governance**.

### Foundation And Copilots

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Install foundation** | Creates the governed Copilot contracts and baseline configuration | Owner/AI administrator |
| Copilot selector | Opens a role-specific Copilot definition | Administrator |
| Contract | Shows allowed inputs, outputs, tools, prohibitions, and approval rules | Read-only after promotion |
| **Approve foundation/contract** | Approves a reviewed Copilot contract version | Required before production use |
| **Run dry run** | Executes a non-operational test against a selected case | Requires installed foundation and selected Copilot |
| Status | Shows draft, review, approved, enabled, disabled, or blocked state | Read-only |

### Runtime

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Install runtime** | Creates provider, model, policy, and tool-runner configuration | AI administrator |
| Provider enable/disable | Allows or blocks model calls through that provider | Requires configured credentials |
| Model and reasoning settings | Selects the approved production model behavior | Administrator; bounded by environment/configuration |
| Capability enable/disable | Turns a specific Copilot capability on or off | Does not grant autonomy |
| Emergency stop | Blocks AI runs across the workspace | Owner/AI administrator |
| Runtime health | Shows provider, queue, model, and error state | Read-only |

### Automation

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Automation policy | Defines the event, allowed action, approval mode, limits, and rollback behavior | Administrator |
| Contract/version | Selects the governed automation definition | Approved versions only |
| **Simulate** | Tests what the automation would do without performing the external action | Preferred before activation |
| **Resume / Enable** | Allows the policy to run within its approved bounds | Requires approved contract and passing controls |
| **Pause** | Stops future executions of that policy | Existing audit history remains |
| Execution history | Shows proposed, blocked, approved, completed, or failed runs | Read-only |
| Human approval | Authorizes an approval-required automation instance | Does not broaden the policy |

### Portfolio

| Section | Purpose | Availability |
| --- | --- | --- |
| Copilot inventory | Shows each Copilot, owner, mode, model, version, and health | Read-only |
| Cost/usage | Shows model calls, token/cost estimates, and failures | Read-only |
| Quality status | Shows current evaluation and production-review state | Read-only |
| Autonomy status | Shows draft-only, approval-required, or controlled automatic mode | Read-only |

### Evaluations

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Install golden library** | Creates baseline ordinary, incomplete, conflicting, compliance-blocked, and adversarial test cases | AI administrator |
| Dataset selector | Opens a golden-case collection | Requires installed library |
| **Executive review** | Records business-owner review of expected answers | Required for promotion policy |
| **Role owner review** | Records workflow-expert review | Required for promotion policy |
| **Approve dataset** | Freezes the reviewed expected behavior | Requires required reviews |
| **Create baseline** | Runs the selected approved set against the current production baseline | Requires selected dataset |
| Run evaluation | Tests a model/contract version against golden cases | Requires runtime |
| Compare | Compares candidate results with baseline quality, safety, latency, and cost | Requires completed runs |
| **Promote** | Makes a passing candidate the approved production version | Blocked below quality thresholds, without required reviews, or without `ai:change_prompts` authority |

### Traces And Governance

| Control or item | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Trace row | Opens model input references, tool calls, output, review state, latency, and cost | Sensitive data is access-controlled |
| **Mark reviewed** | Records that an administrator inspected the run | Does not change its output |
| **Flag** | Marks the run for investigation | Creates governance attention |
| Incident/risk register | Shows quality, provider, privacy, policy, and automation concerns | Read-only until managed |
| Promotion history | Shows which model/contract versions entered production | Read-only |
| **Roll back** | Restores the prior approved production version | Available for an approved promotion |
| Governance evidence | Shows reviews, evaluations, approvals, and rollback links | Read-only |

## Shared Copilot Controls

Role-specific Copilots normally appear near the top of the page where their advice is
used: Leads, Prospecting, Underwriting/Acquisitions, Deals, Finance, Tax, Marketing, and
Executive management.

| Control or concept | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Generate/Refresh | Produces a current draft from visible source records | Capability must be enabled and source data available |
| Evidence | Shows the records, transcript timestamps, or metrics supporting the draft | Available after generation |
| Risks/gaps | Shows uncertainty, conflicts, or missing facts | Read-only |
| Proposed action | Explains what a staff member could do next | It is not performed merely because it appears |
| **Accept** | Records that the recommendation was useful/correct | Only performs a separate action if the UI explicitly says it will |
| **Correct** | Lets staff replace incorrect guidance and captures evaluation feedback | Requires an existing draft |
| **Reject** | Records that the recommendation should not be used | Leaves operating records unchanged |
| Disabled capability | Indicates the Copilot cannot currently run | Check AI Control capability, runtime/provider health, permissions, and required source data |

## Design System Reference

`/os/design-system` is an internal UI reference for developers and product review. Its
sample buttons, dialogs, drawers, toasts, tables, empty states, and controls demonstrate
appearance and interaction patterns; they do not create operational Stonegate records.

## Common Reasons A Control Is Missing Or Disabled

1. The signed-in role does not have the required permission.
2. The record is not in the workflow state required by the action.
3. A required field, approval, evidence item, or source record is missing.
4. The external integration is disabled, unconfigured, pending approval, or unhealthy.
5. The action is already running and the interface is preventing duplicate submission.
6. A financial period, agreement version, launch checklist, or other governed record is locked.
7. The selected user, sender, number, team, template, buyer, vendor, or account is inactive.
8. The server rejected current data; read the inline error before retrying.

Do not work around a missing permission by sharing another person's login. Ask the owner to
correct the user's role, team, sender grant, or record assignment.

## Chatbot Answer Contract

When this document is used as help-assistant source material, answers about a control should
include:

1. The page and section where the control appears.
2. What the control does in plain language.
3. What record or external action it changes.
4. What is required before it works.
5. Why it may be missing or disabled.
6. What the user should expect immediately afterward.
7. Any approval, compliance, financial, contractual, or AI limitation that matters.

Use [USER_MANUAL.md](./USER_MANUAL.md) for complete workflows,
[STAFF_ROLE_MANUALS.md](./STAFF_ROLE_MANUALS.md) for job-specific instructions,
[SETUP_MANUAL.md](./SETUP_MANUAL.md) for nontechnical setup,
[SETUP_REFERENCE.md](./SETUP_REFERENCE.md) for exact configuration, and
[SYSTEM_MAP.md](./SYSTEM_MAP.md) for architecture and system ownership.
