# Stonegate UI Control Reference

Last verified against the application: July 29, 2026

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

## Page Access Reference

Owners can access every production OS workspace. Other users see a page only when both their role
is relevant and the required permission is present.

| Workspace | Typical authorized roles | Permission signal |
| --- | --- | --- |
| Dashboard | Administrator, Lead Manager, Acquisitions | `leads:view` |
| Inbox | Lead Manager, Acquisitions | `communications:view_conversations` |
| Work Queue | Administrator, Lead Manager, Acquisitions | `leads:view` |
| Calendar | Lead Manager, Acquisitions | `underwriting:edit` or `operations:manage` |
| Operations | Administrator, Lead Manager | `operations:view` |
| Campaigns | Lead Manager | `operations:manage` |
| Prospecting | Lead Manager, VA Caller | `operations:manage` or `calling_lists:work_assigned` |
| Lead Desk | Lead Manager, Acquisitions | `leads:view` |
| All Leads / Pipeline | Administrator, Lead Manager, Acquisitions | `leads:view` |
| Field Operations | Lead Manager, Acquisitions | `underwriting:edit` or `operations:manage` |
| Underwriting | Lead Manager, Acquisitions | `underwriting:edit` |
| Approvals | Lead Manager, Transaction Coordinator | `offers:approve` or `contracts:send` |
| Transactions | Acquisitions, Dispositions, TC, approved partner/vendor | `deals:view` |
| Dispositions | Dispositions, Transaction Coordinator | `deals:view` |
| Buyers | Dispositions | `buyers:view` |
| Finance | Finance / Accounting | `financials:view` or `compensation:view` |
| Marketing | Marketing Manager | `financials:view` or `communications:send_bulk` |
| My Setup | Every signed-in user | Always visible |
| Operating Model | Owner | `operating_model:manage` |
| AI Control | Owner | `ai:change_prompts` |

## Public Website

### Public Header And Footer

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Stonegate logo | Returns to the home page | Always available |
| Open navigation / Close navigation | Opens or closes the mobile navigation menu | Appears on smaller screens |
| How It Works, Selling Situations, FAQs, About | Opens seller education pages | Navigation only |
| Displayed phone number | Starts a phone call and records an anonymous call-click conversion event | Requires a device capable of calling |
| **Get a Cash Offer** | Opens `/get-a-cash-offer` | Always available |
| Mobile **Call** bar action | Starts a phone call and records the mobile placement and source page | Fixed to the bottom of public pages at 720px wide or below; never appears in the OS |
| Mobile **Get Offer** bar action | Opens the cash-offer page and records the mobile placement and source page | On the cash-offer page, scrolls to the current form instead of clearing it |
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
| **Continue** | Validates the current step, records step completion, and advances | Validation errors focus the first invalid field |
| Error summary links | Move focus to the field needing correction | Appears only after validation fails |
| Saved browser draft | Restores unfinished non-consent answers for up to 24 hours | Consent boxes intentionally do not restore |

### Property Step

| Field | Purpose and accepted value | Requirement |
| --- | --- | --- |
| Property street address | Identifies the subject street address | Required; at least three characters |
| City | Identifies the Georgia city | Required |
| ZIP code | Supports market, duplicate, and property matching | Required; five digits or ZIP+4 |

### Contact Step

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Your name | Creates or updates the seller identity | Required |
| Phone | Contact method for phone or SMS | A complete number is required when phone or text is selected |
| Email | Contact method for email | A valid address is required when email is selected |
| Preferred follow-up method | Records phone, email, or SMS preference | SMS also requires the separate SMS checkbox |
| Contact authorization | Authorizes phone or email about this property request | Required to submit |
| Optional SMS consent | Separately records recurring automated SMS consent and wording version | Requires a phone number; remains optional unless SMS is selected |
| **Request My Cash Offer** | Submits one seller inquiry, consent evidence, attribution, and duplicate-match evidence | Disabled while sending; validation or API errors leave answers on screen |
| **Add property details** | Opens optional post-submission questions without delaying or duplicating the accepted request | Available on confirmation for 24 hours |
| **Call Stonegate** | Calls the displayed Stonegate number after successful submission | Available on confirmation |
| **Submit another property** | Clears confirmation and form storage, then starts a fresh property request | Available on confirmation |

The confirmation reference is the first eight characters of the accepted lead ID. A message that
the request matched an existing record means Stonegate updated one history instead of creating a
duplicate.

### Optional Property Details

The request is already accepted before this section opens. **Save property details** uses a
random, short-lived token to add the answers to the same lead. The token cannot display the lead or
change staff-reviewed information.

| Field or control | Purpose and accepted value | Requirement |
| --- | --- | --- |
| Property type | Single-family, townhouse, condo, multi-family, manufactured, land, or other | Optional |
| Current condition | Move-in ready, minor repairs, major repairs, full renovation, or not sure | Optional |
| Occupancy | Owner occupied, tenant occupied, vacant, inherited/estate, or other | Optional |
| Main reason for considering a sale | Inherited, repairs, relocation, landlord, financial change, vacant, other, or exploring | Optional |
| Preferred timeline | ASAP, 30 days, 60-90 days, flexible, or exploring | Optional |
| Price you would like to consider | Seller expectation, not a Stonegate valuation | Optional; numbers only |
| Estimated mortgage balance | Preliminary debt context, not verified payoff | Optional; numbers only |
| Repairs, access, ownership, or timing details | Context that helps prepare the first conversation | Optional; maximum 1,000 characters |
| **Skip for now** | Closes the optional section without changing the accepted request | Always available while the section is open |
| **Save property details** | Adds the entered context to the accepted lead and records an audit/conversion event | At least one optional answer is required |

## OS Global Shell

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Sidebar navigation | Opens workspaces allowed by role and permission | Missing pages usually mean role or access configuration |
| Open navigation / Close navigation | Opens or closes the mobile sidebar | Mobile only |
| **Retry access** | Re-requests the signed-in Stonegate profile | Appears only after access verification fails |
| Search workspaces | Filters workspaces the user is allowed to open | It searches navigation, not sellers or records |
| `/` keyboard key | Focuses workspace search | Does not activate while typing in another field |
| **Recent destinations** | Shows up to five recently visited OS destinations stored in this browser | Empty until pages have been visited |
| Notifications bell | Opens Operations notification work | Visible to users allowed into Operations |
| Notification count | Shows unread operational notification count, capped visually at 99 | Updates from the user profile |
| Account control | Shows signed-in Clerk identity and sign-out controls | Requires a completed Clerk session |
| Escape key | Closes search, recent menu, or mobile navigation | Browser keyboard control |

## Dashboard

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Inbox** | Opens seller communications | Navigation only |
| **Work Queue** | Opens assigned and overdue tasks | Navigation only |
| **Calendar** | Opens the company field calendar | Navigation only |
| Executive Copilot launcher | Opens evidence-backed management analysis | Visible when the Executive Copilot is installed |
| Overdue metric | Opens overdue tasks | Count is scoped to the signed-in user's visibility |
| Qualification metric | Opens Lead Desk | Shows seller records needing qualification |
| Meetings today metric | Opens Calendar | Includes today's scheduled appointments |
| Offer prep metric | Opens Underwriting | Includes underwriting and approval work |
| Priority title or arrow | Opens the record or workspace for that item | Navigation only |
| Task completion check | Completes the attached task | Visible only with lead-edit permission; use only after doing the work |
| **Open full queue** | Opens Work Queue | Navigation only |
| Needs intervention links | Open unread conversations, unassigned leads, unscheduled tasks, or approvals | Team-wide exceptions are hidden from narrowly scoped roles |
| Pipeline stage | Opens Seller Pipeline filtered to that stage | Navigation only |
| **Open Seller Pipeline** | Opens the unfiltered pipeline | Navigation only |

An **API fallback view** warning means counts are empty fallback data, not proof that no work exists.

## Work Queue

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| All work | Shows every visible open task | Visibility remains role-scoped |
| My work | Shows tasks assigned to the signed-in user | Requires an assigned user match |
| Overdue | Shows tasks past their due time | Filter only |
| Due next | Shows tasks currently due | Filter only |
| Unscheduled | Shows tasks missing a due date | Filter only |
| Search open tasks | Filters title, seller, property, and task type | Does not search completed tasks |
| Owner | Filters all, unassigned, or a named owner | Filter only |
| Row checkbox | Selects a task for bulk completion | Visible only when the user can complete tasks |
| Select all visible tasks | Selects the currently filtered rows | Does not select hidden rows |
| **Complete selected** | Confirms and completes selected tasks | Disabled while saving or when nothing is selected |
| Row completion icon | Completes one task | Disabled while another completion request is saving |
| Open conversation | Opens communication work for communication tasks | Navigation only |
| Open calendar | Opens Calendar for appointment tasks | Navigation only |
| Open lead | Opens the full lead for other task types | Navigation only |

If a bulk request partially fails, completed tasks disappear and failed tasks remain selected.

## Calendar

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Schedule status | Shows today's appointments, leads ready to schedule, unassigned meetings, and capacity exceptions | Read-only summary |
| **Dispatch** | Opens Field Operations dispatch | Navigation only |
| Upcoming appointment / **Prepare** | Opens that appointment's meeting workspace | Requires an appointment |
| Previous arrow | Moves back one month, week, day, or 30-day agenda period | Filter only |
| **Today** | Returns the cursor to today | Filter only |
| Next arrow | Moves forward one period | Filter only |
| All closers | Filters calendar by closer | Visible to users with management authority |
| Month / Week / Day / Agenda | Changes calendar display without changing appointments | Filter only |
| Month day number | Opens that date in Day view | Navigation within calendar |
| `+N more` | Opens a crowded month date in Day view | Appears after more than three appointments |
| Week day heading | Opens that date in Day view | Week mode only |
| Appointment event | Opens Field Operations meeting preparation | Requires a selected appointment |

Calendar loading or availability errors do not delete appointments. Refresh after API recovery.

## All Leads

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Summary metrics | Shows New, Qualified+, Unassigned, No follow-up, and Paid leads | Read-only |
| Saved lead views | Filters by predefined operating state and updates the URL | Filter only |
| Search active leads | Searches seller, property, source, and owner | Active records only |
| Owner filter | Shows all, unassigned, or one owner | Filter only |
| Stage filter | Shows one normalized pipeline stage | Filter only |
| Seller row | Selects the local seller preview | Does not edit the lead |
| Primary next-action link | Opens Lead Desk, Inbox, Dispatch, Underwriting, Negotiation, or full record based on status | Navigation only |
| **Conversation** | Opens Inbox on this seller | Requires conversation access |
| **Full record** | Opens the five-tab lead record | Requires lead access |
| **Calendar** | Opens Calendar | Appears when appointment status exists |
| Close seller preview | Closes the mobile preview drawer | Mobile only |
| Archived Leads link | Opens archived seller records | Requires lifecycle visibility |

## Archived Leads

| Control | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Back to active leads** | Returns to All Leads | Navigation only |
| **Restore** | Returns an archived lead to active lists | Disabled while saving |
| **Permanently delete** | Opens irreversible deletion confirmation | Intended only for confirmed test records |
| Type `DELETE` | Satisfies permanent-deletion confirmation | Exact uppercase value required |
| Final **Permanently delete** | Deletes the seller and operational history | Disabled until `DELETE` is entered; may still be blocked by related evidence or role |
| **Archive lead** | Removes an active lead from normal queues while retaining history | Confirmation required |
| **Cancel** | Closes an archive or deletion dialog without changing the record | Dialog only |

## Seller Pipeline

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Search seller pipeline | Filters by seller, property, or source | Filter only |
| Owner filter | Shows all, unassigned, or one owner | Filter only |
| Stage filter | Shows all pipeline columns or one stage | Updates the URL; does not move leads |
| Pipeline card | Selects seller context | Does not change stage |
| Card action | Opens the recommended workspace for current operating status | Navigation only |
| Conversation | Opens Inbox for the lead | Requires conversation access |
| Full record | Opens the complete lead record | Requires lead access |
| Close pipeline context | Closes the mobile detail drawer | Mobile only |

The pipeline board deliberately does not drag records between stages. Stage changes require the
lead record's audited stage control.

## Operations

Operations contains six tabs: **Calendar**, **Markets & campaigns**, **Calling lists**, **Team**,
**Data quality**, and **Follow-up plans**.

### Calendar Tab

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Internal calendar | Shows acquisition appointments and operating commitments | Read-only here; use Calendar or Field Operations for appointment work |
| Needs attention | Lists operational notifications | Read-only until a notification is selected |
| **Mark read** | Records the notification as read | Hidden after it has been read |
| Saved view name | Names a reusable Operations view | Required to save |
| View | Selects Appointments, Calling lists, Leads, or Inbox as the destination | Required |
| **Save view** | Creates the reusable view | Requires a name and view |

### Markets And Campaigns Tab

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Market Name | Human-readable market name | Required |
| Market Code | Stable lowercase system key | Must match lowercase letters, numbers, underscore, or hyphen rules |
| State | Two-letter state code | Required |
| Timezone | Eastern or Central operating timezone | Required for scheduling controls |
| **Create market** | Creates the geographic market record | Disabled by browser validation when required values are missing |
| Territory Market | Parent market | Required |
| Assigned team | Team responsible for the territory | Optional |
| Territory Name / Code | Human label and stable system key | Required |
| Counties | Comma-separated county names | Optional but important for assignment |
| ZIP codes | Comma-separated postal codes | Optional but important for territory matching |
| **Create territory** | Creates routing geography under a market | Requires market, name, and code |
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
| **Deactivate / Reactivate** | Removes or restores OS access without deleting history | Owner or authorized administrator only |
| **Cold calling** | Allows this user to receive calling batches and opens their assigned Prospecting queue | Does not change the user's main role or grant unrelated pages |
| Name / Email | Creates the Stonegate-side user identity | Must match the person's Clerk sign-in email |
| Role | VA, Acquisitions rep/manager, Dispositions rep, or Transaction Coordinator | Choose minimum job access |
| Allow assigned cold calling | Enables Prospecting when the new person may also cold call | VA Caller accounts are enabled automatically |
| **Create user** | Creates the individual Stonegate user | Does not create or share a password |
| Add member | Chooses an active user for a team | Requires a team |
| Membership role | Member or Manager | Manager role carries team responsibility |
| **Add** | Adds the selected user to the team | Requires a user |
| Team Name / Function / Manager | Defines team identity and responsibility | Name required; manager optional |
| **Create team** | Creates a Prospecting, Acquisitions, Dispositions, or Operations team | Requires a name and function |

### Data Quality Tab

| Control | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
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

Campaigns contains **Performance**, **Import prospects**, **Costs**, **Calling batches**, and
**Import history**.

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
| **Add PropStream preset** | Adds or reuses Stonegate's standard PropStream export mapping | Use once before the first standard PropStream import |
| Owner, Phone 1-3, Email 1-3, Source ID, Street, City, State, ZIP columns | Maps vendor headings to Stonegate fields and preserves ranked contact methods | Enter the headings exactly as they appear in the CSV |
| Do-not-call flag column | Maps an explicit source flag when present | Optional; blank source data is not treated as an opt-out |
| **Save mapping** | Saves the reusable column mapping | Required headings must be valid |
| Campaign | Selects the campaign receiving imported records | Required |
| Saved mapping | Selects the vendor mapping | Required |
| Source format | Identifies a PropStream export or a general CSV | PropStream requires an export ID, saved-list ID, or saved-list name |
| Measurement cohort | Attributes list performance and determines its dialing mode | Recommended for every controlled VA comparison |
| Default assignee | Applies a caller when the row has no separate assignment | Optional |
| Export ID / Saved list ID / Saved list name / Exported at | Preserves exact vendor lineage | At least one identity is required for PropStream |
| Market / County / Distress / Equity / Ownership / Occupancy / Property type | Preserves the filters used to produce the list | Enter the actual export criteria |
| CSV file | Uploads the prospect file for validation | CSV required |
| **Validate file** | Previews valid, invalid, duplicate, suppressed, review, eligible, prior-contact, callback, active-conversation, and existing-lead states | Does not commit records |
| **Import reviewed file** | Commits new records and attaches refreshed source/contact evidence to existing matches | Disabled when no row can be imported or matched |

### Costs

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Campaign / Cohort / Category | Links cost to list purchase, VA labor, enrichment, phone, voice, mail, ads, software, or other | Campaign and category required |
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
| Batch name / Campaign | Names and scopes the batch | Required |
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

## Prospecting

Prospecting views are **Work queue**, **Call quality**, **Handoff review** for managers,
**Performance**, and **Caller scripts** for managers.

### Work Queue And Attempt

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Due now / Callbacks / Corrections / Scheduled / Waiting / All assigned | Filters the caller's complete assigned shift without changing ownership | Caller sees only assigned records; managers can review the broader operation |
| Campaign and batch strip | Shows ready, callback, correction, active, and waiting workload plus dialing connection state | Read-only |
| Assigned seller row | Loads that seller into the three-panel calling context | Disabled for another row while the caller has an active attempt |
| One-by-one calling | Confirms the caller contacts one assigned owner at a time | External multi-line dialing is intentionally retired |
| Ranked phone and email methods | Shows all validated imported contact methods in source rank order | Based on imported contact evidence |
| Prior attempt details | Expands notes, callback commitment, and structured qualification answers | Read-only history |
| Assigned priority row | Selects the current assigned prospect | Caller sees assigned work only |
| **Generate brief / Refresh brief** | Creates or refreshes a read-only Prospecting Copilot preparation draft | Disabled while saving or when no record is selected |
| Evidence and risks | Expands source facts, warnings, required questions, and limits | Appears after a brief exists |
| **Accept brief** | Records that the draft was useful | Does not alter seller data |
| **Correct** | Opens correction editing | Requires a generated recommendation |
| **Save correction** | Saves corrected summary and review evidence | Available while correcting |
| **Reject** | Records that the draft should not be used | Requires a generated recommendation |
| **Start prospect** | Locks the assigned record to the caller and starts an attempt | Requires an approved active caller script |
| Qualification questions | Records motivation, timeline, condition, occupancy, price, and mortgage answers | Required questions depend on approved script |
| Disposition buttons | Records the truthful call outcome without using a long menu | Required |
| Callback date and time | Schedules callback work | Required for callback or follow-up outcomes |
| In 1 hour / Tomorrow / In 3 days | Sets a common callback time quickly | Caller can still enter an exact date and time |
| Acquisitions owner | Chooses warm handoff recipient | Required for interested or appointment-set outcomes |
| Appointment date and time | Creates seller appointment | Required for Appointment set |
| Meeting type / location | Defines property, phone, video, or office appointment | Used for Appointment set |
| Call notes | Records objections, commitments, and next action | Strongly recommended |
| Compliance flags | Records seller complaint, unclear identity, policy uncertainty, or recording issue | Select only when observed |
| **Save outcome** | Completes the attempt and creates follow-up, handoff, appointment, or suppression effects | Required fields vary by disposition |

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

## Lead Desk

Lead Desk views are **Copilot**, **Today**, **Qualification**, **Performance**, and **Standards**.

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
| Acquisitions scorecard | Shows handoff SLA, qualifications, appointments, contracts, and follow-up quality | Read-only |
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
| **Compose** | Opens the global email composer without requiring a property lead | Requires outbound email permission and an active sender |
| **Enable calling** | Initializes the browser phone | Requires configured Twilio Voice and microphone access |
| **Refresh** | Reloads conversation and provider status | Available while Inbox is open |
| Mobile **Inbox / Thread / Details** | Changes the active pane on narrow screens | Mobile layout only |

### Unified Timeline

| Control or item | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| SMS event | Shows inbound or outbound text, delivery state, and timestamp | Read-only after provider submission |
| Email event | Shows sender, recipients, subject, body, attachments, and delivery state | Read-only after send |
| Call event | Shows direction, outcome, duration, recording, and transcript status | Depends on voice integration |
| Internal note | Shares staff-only context in the timeline | Never sent to the seller |
| Transcript | Opens speaker-separated call text | Requires a completed recording and transcription |
| Recording player | Plays the secured call recording | Requires recording access for the user's role |
| **Delete recording** | Removes retained audio after a reason is entered | Authorized roles only; transcript and audit history are handled separately |
| Mark unread/read | Changes the user's unread state for the conversation | Does not change another user's unread state |
| Lead/property link | Opens the related seller record | Requires lead access |

### Message Composer

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **SMS** | Selects text-message composition | Requires SMS consent, a routable phone number, and configured Twilio SMS |
| **Email** | Selects email composition | Requires an active Resend sender and recipient email |
| **Call** | Opens browser or external call options | Requires a seller phone number |
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
| **Send** | Sends the selected external message | Disabled when provider, consent, sender, recipient, or content requirements fail |
| **Save note / Log communication** | Adds an internal or manually logged event | Does not contact the seller |

### Browser Calling

| Control | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Call in browser** | Starts an outbound call in Stonegate | Requires an enabled voice token, microphone permission, and configured number |
| **Call externally** | Opens the device's phone handler | The resulting call must be logged or matched by provider event |
| **Answer** | Accepts an inbound browser call | Appears only while ringing |
| **Decline** | Rejects the inbound call | Appears only while ringing |
| **Mute / Unmute** | Changes local microphone state | Active browser call only |
| **End call** | Ends the current call | Active call only |
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
| **Generate AI notes** | Produces a transcript-grounded draft | Requires a completed transcript and enabled Call Intelligence capability |
| Summary | Drafts the overall call result | Human review required |
| Motivation / Timeline / Condition / Occupancy | Extracts seller qualification details | Human review required |
| Asking price | Extracts stated seller pricing | Never treated as an approved offer |
| Mortgage and title | Extracts possible debt or ownership concerns | Must be verified by staff |
| Repairs / Objections / Commitments | Structures operational follow-up context | Human review required |
| Next action / Follow-up date | Proposes the next task | Does not create a task unless selected |
| Supporting timestamps | Opens the transcript evidence behind an extracted item | Requires diarized transcript evidence |
| Fill empty lead fields | Allows approved notes to populate only blank CRM fields | Existing values remain unchanged |
| Create follow-up task | Creates the reviewed proposed task | Optional approval choice |
| **Approve** | Saves the reviewed notes and selected low-risk updates | Requires review permission |
| **Reject** | Records that the AI draft should not be used | Does not alter CRM fields |

### Email Administration

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Senders** | Manages approved outbound identities | Owner or communication administrator |
| **Routing** | Manages inbound address and department routing | Owner or communication administrator |
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
| **Save / Update** | Persists sender or routing changes | Administrator only |

## Field Operations

Field Operations has **Dispatch**, **Calendar**, **Meetings**, and **Capacity** views.

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
| Acquisitions Copilot | Generates meeting questions, gaps, risks, and next-step guidance | Draft-only; requires enabled capability |
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
| Repair estimate | Records an estimated cost for an observed item | Estimate, not a contractor bid |
| Photo upload | Attaches property evidence | Requires supported image and network access |
| Delete photo | Removes an uploaded photo | Requires field edit access |
| **Save draft** | Preserves incomplete walkthrough work | Does not mark inspection complete |
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

The seller record uses **Overview**, **Communications**, **Underwriting**, **Deal**, and
**History** tabs. Every tab acts on the same lead; changing ownership or stage does not
create a second record.

### Header And Overview

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Back to leads** | Returns to the lead workspace | Always available |
| Current stage | Shows the seller's current pipeline stage | Read-only in header |
| Owner | Shows the person responsible for the record | Read-only in header; editable with permission |
| Contact action | Opens the relevant communication workflow | Requires phone/email and channel access |
| First name / Last name | Edits the primary contact | Required fields depend on lead source |
| Phone / Email | Edits seller contact methods | Format validation applies |
| Property address / City / State / ZIP | Edits the subject property | Address required for market analysis |
| Source / Campaign | Records acquisition attribution | Options come from configured operations data |
| Motivation / Timeline / Condition / Occupancy | Saves qualification facts | Unknown is valid until confirmed |
| Asking price / Mortgage balance | Saves seller-stated figures | Must not be treated as independently verified |
| Preferred contact method/time | Guides follow-up | Does not itself create a task |
| **Save details** | Persists edited lead and qualification fields | Disabled while saving |
| Stage / Stage reason | Changes pipeline status and records why | Reason may be required by target stage |
| **Update stage** | Applies the stage change | Permission and transition rules apply |
| Archive | Removes the lead from active queues without deleting history | Requires archive permission |

### Property Validation

| Control or result | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Validate property** | Checks and normalizes the subject address before market analysis | Requires a sufficiently complete address |
| Candidate address | Shows a provider-normalized match | Staff must confirm the correct property |
| Match quality | Explains exact, normalized, partial, or unresolved address status | Read-only |
| **Use this address** | Replaces the working address with the confirmed normalized value | Requires lead edit access |
| Manual correction | Lets staff fix the address when no provider match is reliable | Staff remains responsible for correctness |

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

### Communications Tab

| Control or item | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Open in Inbox** | Opens the seller's full unified conversation | Requires Inbox access |
| Channel / Direction | Classifies a manually logged message or call | Required |
| Subject / Body / Outcome | Records what happened | Body or outcome required by channel |
| **Log communication** | Adds the event to the seller timeline | Does not send an external message |
| Timeline row | Shows calls, messages, emails, notes, transcripts, and provider status | Read-only |

### History Tab

| Section | Purpose | Availability |
| --- | --- | --- |
| Recent activity | Shows material lead and workflow events | Read-only |
| Assignment history | Shows former and current owners/queues | Read-only |
| Stage history | Shows pipeline changes and reasons | Read-only |
| Consent and attribution | Shows source, consent, and campaign evidence | Read-only to normal staff |
| Audit events | Shows who changed important fields and when | Visibility depends on role |

## Underwriting Workspace

The lead's Underwriting tab is the working valuation area. The separate Underwriting
page is the management queue and calibration area. A market analysis is decision support,
not an appraisal or permission to promise a seller a price.

### Repair Inputs

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Repair method | Chooses system estimate, manual total, or itemized repair estimate | Affects offer math and report explanation |
| Manual repair total | Supplies a known working budget | Used only when the selected method allows it |
| Contingency | Adds repair uncertainty allowance | Must be a valid percentage or amount |
| Itemized repair row | Records category, description, quantity, unit cost, and total | Repeatable |
| Repair notes | Captures assumptions and exclusions | Included in internal evidence |
| Evidence/source | Links photos, walkthrough facts, contractor input, or staff observation | Improves reviewability |
| **Save repair estimate** | Saves the current version used by underwriting | Disabled while saving |

### Market Analysis

| Control or result | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| **Analyze comps** | Validates the address, gathers property/comparable evidence, filters outliers, estimates ARV, applies repair and assignment assumptions, and creates a reviewable analysis | Requires valid address; external provider failures may fall back to controlled evidence collection |
| Subject facts | Shows bedrooms, bathrooms, size, year, lot, and property type used | Staff should correct material mismatches |
| ARV range | Shows conservative low, central, and high after-repair value | Range width reflects evidence uncertainty |
| Confidence | Summarizes evidence quality and unresolved gaps | Does not gate PDF generation |
| Offer range | Shows policy-based low/high offer guidance after repairs and assignment fee | Staff must use current authority and approval rules |
| Provider evidence | Shows market-data source, retrieval result, and matching details | Read-only |
| Public evidence | Shows controlled secondary evidence and source links when used | Must be verified before relying on a material fact |
| Warnings | Identifies address, comp, price-per-square-foot, renovation, or data-quality concerns | Staff review required |
| **Investor PDF** | Downloads the detailed internal/agent-facing valuation report | Requires a saved analysis |
| **Client PDF** | Downloads the seller-safe presentation without internal negotiation details | Requires a saved analysis |
| Re-run analysis | Creates a new analysis version using current inputs | Earlier versions remain auditable |

### Comparable Review

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Comparable row | Shows address, sale date, distance, size, beds/baths, price, price per square foot, and evidence source | Read-only source facts |
| Include | Allows a comparable to contribute to the estimate | Staff judgment; exclusion reason recommended when changed |
| Condition | Marks renovated, average, distressed, unknown, or other supported state | Unconfirmed renovation reduces confidence but does not block results |
| Exclusion reason | Explains why a comp should not be used | Required by review workflow when excluded |
| Weight | Adjusts a comp's influence within allowed bounds | Should reflect similarity and evidence, not desired outcome |
| **Recalculate** | Rebuilds the analysis from reviewed comp choices | Requires at least enough usable evidence for a range |
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

### Underwriting Management Page

| Control or section | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Underwriting queue | Opens leads needing analysis or review | Requires underwriting permission |
| **Analyze comps** | Runs the same evidence workflow from the queue | Requires usable subject data |
| Calibration scorecard | Compares prior valuation predictions with verified outcomes | Read-only |
| Decision review | Shows approvals, overrides, confidence, and result history | Manager access |
| Verified sale/outcome input | Records known closing evidence for calibration | Must come from reliable evidence |
| Analysis version history | Opens prior valuation snapshots | Read-only |

## Approval Center

| Control or item | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Approval type filter | Limits the queue by offer, contract, disposition, finance, AI, or other governed request | Visible types depend on role |
| Approval row | Shows requester, source, amount/action, evidence, and status | Requires approval permission for that domain |
| Source link | Opens the underlying lead, transaction, finance record, or AI review | Used when the decision needs full context |
| Evidence summary | Shows the facts and warnings attached to the request | Read-only |
| Decision note | Records reasoning for approval or rejection | Required by some approval types |
| **Approve** | Authorizes the requested governed action | Only authorized approvers; may be blocked if source review is required |
| **Reject** | Rejects the request and records the reason | Only authorized approvers |
| Review-at-source state | Directs the approver to decide in the originating workspace | Used when inline approval would omit required context |

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
| Seller/property/purchase fields | Supplies agreement merge data | Required fields depend on template |
| Closing terms / Special terms | Supplies transaction-specific agreement terms | Must be reviewed before sending |
| **Create agreement version** | Generates a frozen agreement version from current data | Does not send it |
| Agreement PDF | Opens the exact generated version for review | Requires generated agreement |
| **Request approval** | Sends the agreement version for internal approval | Required by contract authority rules |
| **Mark sent manually** | Records that staff delivered the exact agreement outside SignWell | Requires delivery details |
| **Mark executed manually** | Records a completed externally signed agreement and evidence | Requires execution evidence |
| SignWell connection status | Shows whether API configuration is usable | Read-only |
| **Verify SignWell** | Tests the configured provider connection/template | Requires SignWell credentials and template ID |
| Seller signer / Company signer | Maps actual people to template placeholder roles | Required by template |
| **Send signature request** | Creates and sends the approved agreement through SignWell | Requires approved agreement, valid signers, and working provider |
| **Reconcile signature status** | Pulls the latest provider status and completed files | Requires an existing signature request |
| Signature status | Shows prepared, sent, viewed, completed, declined, or failed | Provider-derived |

### Documents

| Control or item | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Document type | Classifies contract, amendment, title, closing, assignment, photo, or other file | Required |
| File upload | Attaches a document to the transaction | File limits apply |
| Description | Explains what the document contains | Recommended |
| **Upload** | Stores the file and audit metadata | Requires document permission |
| Download | Opens the stored document | Requires document access |
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
| Search | Finds buyers by name, company, market, contact, or criteria | Searches visible buyer records |
| Buyer row | Opens the buyer profile | Requires buyer access |
| **Add buyer** | Opens the new-buyer drawer | Requires buyer edit permission |
| Name / Company | Identifies the investor or organization | Name required |
| Phone / Email | Stores contact methods | At least one useful method recommended |
| Markets | Records geographic buying areas | Used for matching |
| Property types | Records asset preferences | Used for matching |
| Price minimum/maximum | Records acquisition budget | Used for matching |
| Strategy | Records flip, rental, wholesale, development, or other focus | Used for matching |
| Funding type | Records cash, hard money, private, conventional, or other source | Used for readiness |
| Proof of funds status | Shows missing, submitted, verified, rejected, or expired | Verification requires evidence |
| Reliability/status | Records activity and relationship state | Staff-managed |
| Notes | Captures buyer-specific context | Internal |
| **Save buyer** | Creates or updates the buyer profile | Disabled while saving |
| Archive/deactivate | Removes buyer from active matching | Preserves history |

## Dispositions

The Dispositions workspace opens a case for a contracted property and uses **Package**,
**Buyers**, **Offers**, and **Reconciliation** views.

### Case And Package

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Case row | Opens a disposition case | Requires disposition access |
| **Open disposition case** | Creates the marketing and buyer-offer workspace from a transaction | Requires a qualifying transaction |
| Package details | Defines property summary, access, terms, closing, and marketing facts | Must be supported by transaction/underwriting evidence |
| Photo/document selection | Chooses seller-safe media for the buyer package | Private or restricted evidence cannot be released |
| **Generate package PDF** | Produces the current investor marketing package | Requires sufficient package data |
| **Request package approval** | Sends the release package for review | Required before governed release |
| **Approve package** | Authorizes the current version for marketing | Authorized approver only |
| Release status | Shows draft, pending, approved, released, or withdrawn | Read-only |
| **Simulate release** | Shows intended recipients and content without contacting buyers | Available before live release |
| **Release package** | Sends or records the approved package release | Requires approved current package and enabled channel |

### Buyer Matching

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Internal match list | Ranks stored buyers against market, property, price, strategy, funding, and performance | Requires buyer profiles |
| Match explanation | Shows why a buyer ranked highly or poorly | Read-only |
| **Rank buyers** | Refreshes the buyer recommendation using current case facts | AI output remains reviewable |
| **Find buyers with DealMachine** | Requests external buyer candidates for the subject market | Requires enabled DealMachine API credentials |
| Candidate result | Shows provider data and match context before import | Not yet a Stonegate buyer record |
| **Import buyer** | Creates or updates an internal buyer from a reviewed candidate | Staff approval required |
| Proof of funds upload | Attaches funding evidence | Requires supported document |
| **Verify / Reject proof of funds** | Records staff review of funding evidence | Authorized role only |
| Buyer activity | Logs contact, interest, showing, pass reason, and follow-up | Requires selected buyer |
| **Log activity** | Saves the buyer touchpoint | Does not send communication unless explicitly using a channel action |

### Offers

| Control or field | Purpose and effect | Availability and common blocker |
| --- | --- | --- |
| Buyer | Selects the submitting buyer | Required |
| Offer amount | Records gross buyer offer | Required |
| Earnest money | Records proposed deposit | Optional until offered |
| Closing date | Records proposed timing | Required for comparison |
| Inspection/contingencies | Records buyer conditions | Used in offer quality |
| Financing | Records cash/funding context | Used in readiness |
| Notes | Records additional terms | Internal |
| **Record buyer offer** | Saves a versioned buyer offer | Requires selected case and buyer |
| **Select primary** | Marks the preferred offer | Requires disposition authority/approval rules |
| **Select backup** | Marks a backup offer | Cannot duplicate the active primary selection |
| Offer score | Compares price, speed, contingencies, funding, and buyer reliability | Decision support, not automatic acceptance |

### Reconciliation

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
| Funnel metrics | Shows visits, starts, submissions, leads, appointments, contracts, and revenue | Read-only |
| Cost metrics | Shows spend, cost per lead, acquisition cost, and return | Depends on linked spend and revenue |
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

## Operating Model

The Operating Model workspace uses **Setup**, **Active**, **Pending**, **History**, and
**Launches** to manage seats, role acknowledgement, compensation policy, work credit,
counterparties, and market readiness.

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

AI Control is the owner/administrator workspace for the existing Stonegate Copilot system.
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
| **Promote** | Makes a passing candidate the approved production version | Blocked below quality thresholds or without approvals |

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
used: Lead Desk, Prospecting, Underwriting/Acquisitions, Transactions, Dispositions,
Finance, Tax, Marketing, and Executive management.

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
