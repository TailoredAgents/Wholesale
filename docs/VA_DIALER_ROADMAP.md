# Stonegate Native VA Dialer Historical Implementation Roadmap

Last updated: August 21, 2026

> **Current status: implemented foundation, planned dormant.** D0-D10 document the native
> Stonegate dialer that was built but never production-accepted. The current production strategy
> is BatchDialer with a direct Stonegate integration, defined in
> `BATCHDIALER_DIRECT_INTEGRATION_ROADMAP.md`. This file preserves architecture, tests, and audit
> history; it does not authorize native-dialer activation or the optional D11/D12 pilots. The BD0
> repository and Blueprint changes do not make production dormant until the live switches,
> sessions, calls, and pilot state are drained, the release is deployed, and no-call verification
> passes.

## 1. Purpose And Authority

This is the historical implementation plan and technical record for Stonegate's native VA
prospecting dialer.

It defines:

- the approved product decision
- the VA and manager experience
- the technical architecture
- the safety and compliance boundaries
- the implementation sequence
- the test and production-acceptance gates
- the later path from one-line power dialing to optional two- or three-line dialing

Application code and database migrations remain the truth about what exists today. This roadmap
describes the approved destination and must not be treated as proof that a planned capability is
already live.

## 2. Historical Decision Through D10

The decision below governed implementation through D10. It was superseded on August 21, 2026 by
the direct BatchDialer integration and native-dialer dormancy plan.

Stonegate built a native prospecting dialer inside the existing Prospecting workspace.

The intended first production version was a browser-based, single-line power dialer. Every VA was
expected to use
the same Stonegate application but receive a private, assignment-scoped dashboard containing only
the calling batches and prospects they are authorized to work.

The architecture supports a configurable maximum of one to three simultaneous outbound dial legs
per VA, although production was hard-capped at one line and never accepted. The optional two- and
three-line pilots are no longer on the active implementation path.

BatchDialer remained the production calling system during the native build. It is now the selected
production dialer, its official direct API is the sole Stonegate integration, and Stonegate's
native runtime is retained in a dormant state.

## 3. Desired Business Outcome

One VA should be able to sign in, put on a headset, select an assigned campaign, and complete a
calling shift without switching among a dialer, spreadsheet, calendar, and CRM.

The system should:

1. Select the next eligible assigned prospect.
2. Display the correct person, property, source, prior attempts, script, and qualification needs.
3. Place the call through a dedicated prospecting number.
4. Show queued, dialing, ringing, connected, ended, and failed states in real time.
5. Save qualification answers as the conversation progresses.
6. Make completed questions visibly green and unresolved questions visibly actionable.
7. Require a clear disposition and automatically update the calling cadence.
8. Create a warm Stonegate lead only when the seller is qualified or an appointment is set.
9. Preserve the call recording, transcript, notes, qualification evidence, and attribution.
10. Give managers reliable funnel, quality, cost, and per-VA performance reporting.

The target is not merely more dials. The target is more qualified seller conversations, held
appointments, signed contracts, and contribution profit per paid VA hour without sacrificing
caller reputation or seller experience.

## 4. Product Boundaries

### 4.1 Prospecting Versus Warm CRM

Cold prospects remain in Prospecting until a warm-handoff outcome is recorded.

The native dialer must not create fake Leads, Contacts, or Inbox conversations merely to satisfy
the existing warm-call data model. Raw no-answer, voicemail, wrong-number, and not-interested
activity stays attached to the prospect and prospecting attempt.

When a seller becomes interested or an appointment is set, the existing warm-handoff workflow
creates or updates the real Stonegate lead and moves future seller communication to the
acquisitions workflow.

### 4.2 Phone Number Separation

Prospecting numbers remain separate from:

- the shared Stonegate acquisitions number
- the Stonegate dispositions number
- employee personal numbers

Version one should use one dedicated prospecting number assigned to each active VA or another
manager-approved one-to-one line assignment. Future parallel dialing may use a controlled line
pool, but no number rotation may be designed to evade carrier protections or spam labeling.

### 4.3 Historical BatchDialer Boundary During Native Migration

This boundary governed the former D0-D10 migration. BatchDialer remained the production calling
system while the native system was available only for controlled, non-overlapping test scope
before D10 acceptance. That native activation path is now superseded by dormancy.

During that historical migration:

- one calling list or cohort could not be worked simultaneously in both dialers;
- the then-current qualified-lead and appointment handoff automations remained enabled;
- BatchDialer data remained provider-attributed;
- native Stonegate campaigns wrote directly to Stonegate; and
- management could return a test cohort to BatchDialer if the native dialer was paused.

Current operations use BatchDialer for all VA calling, the official direct API as the sole CRM
integration, and urgent-task-driven manual Stonegate entry for agreed appointments.

## 5. Existing Foundation To Reuse

Stonegate already contains much of the domain and user experience required for this upgrade.

| Existing capability | Current location | Reuse decision |
| --- | --- | --- |
| Campaigns, cohorts, imports, costs, and work sessions | apps/api/app/services/campaign_management.py | Reuse |
| Assigned calling batches and queue entries | ProspectCallingBatch and ProspectCallingBatchEntry | Reuse |
| Approved scripts and qualification questions | ProspectingScriptVersion | Reuse |
| Attempts, outcomes, callbacks, qualification snapshots, and scores | ProspectingAttempt | Extend |
| Warm handoff, lead creation, and appointment creation | apps/api/app/services/prospecting.py | Reuse |
| Per-assignee Prospecting workspace | apps/web/src/app/os/prospecting | Extend |
| Twilio voice lines, access token session, call intents, and callbacks | apps/api/app/services/voice.py and routers/voice.py | Extend |
| Recordings, transcription, structured notes, and quick read | CallRecording, CallTranscript, and call_intelligence.py | Extend |
| DNC and phone suppression | Prospect and SuppressionRecord workflows | Reuse and enforce |
| Prospecting Copilot and call-quality review | prospecting_copilot.py | Reuse |
| RBAC and assigned-calling-list scope | calling_lists:work_assigned and acquisition management permissions | Reuse |

The existing Prospecting page already displays assigned queue records, prospect identity, property
information, approved scripts, previous attempts, qualification inputs, callbacks, appointment
fields, warm handoffs, scorecards, and Copilot guidance. Its current Start prospect action locks a
record but does not place a call. This roadmap turns that workbench into the operational dialer.

## 6. Known Architecture Gaps

The build must solve these gaps explicitly:

1. The web application does not currently include the Twilio Voice JavaScript SDK, even though the
   API can issue a browser Voice session token.
2. Current VoiceCallIntent and CallRecord records require a CRM conversation and contact. Cold
   prospects intentionally do not have those records.
3. ProspectingAttempt currently allows only one in-progress attempt per caller and per queue
   entry. That is correct for single-line operation but cannot represent several future ringing
   legs.
4. Current prospect qualification answers are primarily saved with call completion. The new
   checklist must autosave safely during the call.
5. Existing recording and transcript presentation is conversation-centric. Cold-call evidence
   must be viewable from the prospecting attempt without polluting the Inbox.
6. Current Twilio REST calling primarily supports forwarded staff calls. A browser dialer needs
   initiated, ringing, answered, completed, cancelled, failed, no-answer, and reconnect handling.
7. Queue locking must remain correct across multiple VAs, tabs, retries, webhook replays, and
   service restarts.
8. Existing documentation describes BatchDialer as the end-state. System maps and staff manuals
   must be updated only as the native behavior becomes Implemented and Active.

Migration 0076 retired the historical multi-line-parallel mode. The new design must not revive
that old value or reverse that migration. Future concurrency will use explicit dial-session and
dial-leg records with feature-gated line limits.

## 7. Target VA Dialer Dashboard

### 7.1 One Workspace Per VA

There will be one reusable Dialer Dashboard, automatically scoped to the signed-in VA.

The VA sees:

- assigned campaigns and batches
- due callbacks
- records needing correction
- the current prospect
- personal shift statistics
- their assigned prospecting line
- their approved maximum line count

The VA does not see unrelated employee queues, unrestricted seller CRM records, company finance,
or global recordings.

Managers use the same Prospecting area with broader controls for assignments, scripts, line
configuration, session health, call quality, and reporting.

### 7.2 Desktop Layout

The primary desktop layout will contain four functional areas.

| Area | Contents |
| --- | --- |
| Top command bar | Campaign, batch, headset status, line status, Start Calling, Pause, Resume, End Shift, and live shift metrics |
| Prospect panel | Owner name, ranked phone number, property address, list source, property facts, prior attempts, callbacks, and warning flags |
| Conversation panel | Approved opening script, live call state, timer, mute, hang up, retry, and qualification checklist |
| Evidence and outcome panel | Notes, prior call history, transcript or AI summary when available, disposition, callback, handoff owner, and appointment fields |

On smaller screens, the active call and qualification checklist take priority. Manager analytics
and long history can collapse behind tabs. Version one is desktop-first because reliable headset
calling and simultaneous data entry are the core VA use case.

### 7.3 Dashboard State Flow

The dashboard has a visible state at all times:

| State | VA experience |
| --- | --- |
| Not ready | Microphone, Twilio session, line assignment, campaign, or calling window blocker is shown |
| Ready | Next eligible prospect is reserved and visible; no call is active |
| Dialing | Provider accepted the request; stop control is available |
| Ringing | The selected number is ringing; prospect details and script remain visible |
| Connected | Call timer runs; qualification answers and call controls are active |
| Wrap-up | Dialing is paused until disposition and required fields are saved |
| Paused | No new call starts; current saved work remains visible |
| Reconnecting | Browser or provider state is being reconciled; no duplicate call may start |
| Stopped | Session is closed and all outstanding legs are terminal |

Refreshing the page must restore the durable server state. Closing the tab or losing the network
must not silently start another call.

### 7.4 Qualification Checklist

The approved script defines the questions for the selected asset class. A typical house checklist
includes:

- decision-maker or ownership confirmation
- reason or motivation for considering a sale
- desired timeline
- property condition and major repairs
- occupancy
- asking price or expected net
- estimated mortgage or payoff
- preferred follow-up timing
- appointment readiness

Land scripts may instead include parcel identity, acreage, access, utilities, zoning or use,
septic or perc status, taxes or HOA, and terrain or environmental concerns.

Question states:

| Color | Meaning |
| --- | --- |
| Gray | Not covered or no response saved |
| Green | A usable answer was saved |
| Yellow | Asked but unknown, refused, deferred, or follow-up is needed |
| Red | Conflicting information, identity uncertainty, policy concern, or manager review needed |

Green means an answer was captured, not merely that the VA read the question. This prevents a
misleading complete score.

Each response will store:

- script version and question key
- state
- answer value
- source, such as VA entry or evidence-backed AI
- actor
- capture and update time
- optional transcript evidence

Answers autosave individually. The interface shows progress such as 6 of 9 answered. A connection
failure or browser refresh must not erase already saved answers.

Version one uses dependable VA entry during the call. Post-call AI may fill an unanswered
descriptive field when transcript evidence is strong, but it must not silently overwrite a human
answer. A disagreement becomes a red conflict for review. Streaming AI that attempts to recognize
questions in real time is deferred until the core dialer is stable.

### 7.5 Disposition And Wrap-Up

Every terminal call enters wrap-up. The existing Stonegate outcomes remain authoritative:

- No Answer
- Left Voicemail
- Callback Requested
- Follow Up
- Interested
- Appointment Set
- Not Interested
- Wrong Number
- Do Not Call

Outcome behavior:

| Outcome | Automatic result |
| --- | --- |
| No Answer | Return to cadence using the campaign retry rule |
| Left Voicemail | Return to cadence using the voicemail delay |
| Callback Requested or Follow Up | Require a future date and prioritize it when due |
| Interested | Require warm-handoff questions and create one reviewable Stonegate lead |
| Appointment Set | Require qualification, owner, date, time, and location; create one lead and one appointment |
| Not Interested | Complete the queue entry and stop routine dialing |
| Wrong Number | Block that exact invalid number and use another ranked number only if eligible |
| Do Not Call | Immediately suppress the exact number and stop future dialing |
| Technical Failure | Preserve the attempt evidence without treating the seller as rejecting contact |

The next call cannot start until wrap-up is valid and saved. This protects attribution, cadence,
and seller history.

## 8. Target Technical Architecture

### 8.1 End-To-End Flow

    Assigned batch
        -> atomic eligibility and suppression check
        -> durable dial session
        -> one reserved prospect
        -> one Twilio dial leg in version one
        -> browser headset connection
        -> live state callbacks and autosaved qualification
        -> disposition and attempt completion
        -> recording, transcript, and AI notes when applicable
        -> cadence, warm lead, or appointment
        -> manager measurement

### 8.2 New Dialer Records

Exact names may be adjusted during implementation, but the responsibilities must remain separate.

#### Prospecting Dialer Profile

One configuration record per VA:

- status
- assigned prospecting voice line or pool
- default line count
- maximum approved line count from one to three
- recording policy
- permitted campaigns or market restrictions when needed
- daily dial and cost caps
- manager and audit metadata

The effective line count is the lowest approved value among company, VA, campaign, and current
feature-flag limits.

#### Prospecting Dial Session

One durable calling shift or active browser session:

- VA, campaign, cohort, and batch
- state
- requested and effective line count
- started, paused, resumed, heartbeat, and ended times
- browser or provider session identity
- current prospect or wrap-up lock
- stop reason and recovery metadata

Only one active session is allowed per VA. A lease and heartbeat permit safe recovery after a
crashed tab without immediately releasing live calls.

#### Prospecting Dial Leg

One record for every provider call:

- session, prospect, batch entry, and logical attempt
- selected contact point and voice line
- provider and call identifier
- idempotency key
- queued, dialing, ringing, answered, connected, cancelled, failed, and completed times
- answer and party classification
- terminal provider result and error
- cancellation reason
- recording link

Future two- or three-line dialing creates several ringing legs in one session. Only one
human-connected leg may become the VA's active conversation. Remaining ringing legs must be
cancelled or handled by a separately approved compliant fallback.

#### Prospecting Qualification Response

One current, auditable response per attempt and script question. The completed attempt retains a
snapshot for compatibility and reporting.

#### Prospecting Dial Event

An append-only provider event record stores signed callback identity, bounded raw evidence,
processing state, and replay protection. Out-of-order callbacks may advance a leg but may never
regress a terminal state.

### 8.3 Existing Record Extensions

ProspectingAttempt remains the logical business attempt and authoritative disposition record.

VoiceCallIntent and CallRecord must support one of two explicit contexts:

1. warm CRM context using conversation and contact
2. cold prospecting context using prospect and prospecting attempt

The migration should make CRM context nullable only when a valid prospecting context exists and
enforce that invariant. It must not weaken organization scoping or allow an unbound call record.

ProspectingAttempt keeps its one-in-progress-call-per-caller protection for single-line operation.
Future parallel ringing is represented by DialLeg records. The unique active-attempt rule should
continue to guarantee that the VA is connected to only one seller conversation at a time.

### 8.4 Browser Voice

The web application will use Twilio's supported Voice JavaScript SDK as a softphone.

The browser flow:

1. Request a short-lived, user-scoped token from the existing Voice session endpoint.
2. Initialize one Twilio Device.
3. Verify microphone permission and audio readiness.
4. Ask the API coordinator to start an authorized dial leg.
5. Receive state through the SDK plus signed server callbacks.
6. Reconcile browser state with the durable server session.
7. Hang up or cancel through an idempotent server action.
8. Refresh the token before expiration without dropping an active call.

Twilio remains the provider, but provider operations sit behind a Stonegate adapter so business
queue and qualification logic do not become SDK-specific.

### 8.5 Queue Coordinator

The server, not the browser, decides which prospect is dialed.

Eligibility includes:

- assigned VA and active batch
- active campaign and cohort
- due callback or eligible cadence position
- valid ranked phone number
- no applicable Stonegate suppression
- call eligibility is allowed
- local calling window is open
- attempt and daily caps are not exceeded
- no active reservation by another VA or session

Priority order:

1. Due callbacks
2. Returned handoff corrections
3. Due retries
4. New assigned prospects

Selection and reservation must be atomic. API retries, double-clicks, provider replays, and two VAs
must never dial the same prospect simultaneously.

### 8.6 Recording, Transcript, And AI Notes

When recording is enabled by the approved company policy:

- recording attaches to the cold prospecting attempt and dial leg
- transcription is queued once
- full transcript, recording playback, download controls, and quick summary appear in Prospecting
- AI creates compact notes and evidence-backed qualification suggestions automatically
- human-entered answers are never silently replaced
- accepted warm handoff copies or links the relevant evidence into the seller timeline
- evidence is not transcribed twice after handoff
- no-answer and failed calls do not create meaningless transcription work
- retention and deletion rules reuse the existing call-intelligence controls

The completed seller call should therefore remain understandable from the prospect, the warm lead,
and the later seller timeline without duplicating incompatible histories.

### 8.7 Inbound Callbacks

Calls returning to a prospecting number should:

1. Match the receiving prospecting line.
2. Search recent attempts and ranked prospect phone numbers.
3. Route to the assigned VA when available.
4. Use a manager-approved fallback or voicemail when unavailable.
5. Open the matching prospect in the VA dashboard.
6. Record the callback as an inbound prospecting call.
7. Create an urgent callback task when missed.

An inbound callback alone does not create a warm lead. Qualification or a manager-approved warm
handoff still controls CRM entry.

### 8.8 Access And Audit

VAs may:

- work only assigned batches
- see only the prospect data required for calling
- use only assigned prospecting lines
- access their own live calls and permitted call evidence
- create dispositions, callbacks, qualifications, and warm handoffs

Managers may:

- create and assign batches
- approve scripts
- configure VA dialer profiles and line limits
- monitor sessions and stop a campaign
- review recordings, quality, conflicts, and performance

Every session, call, reservation, qualification update, disposition, suppression, handoff, manager
override, and configuration change must have organization scope, actor, time, and audit evidence.

## 9. Safety, Reliability, And Compliance Gates

### 9.1 Hard Controls In Every Version

- entity-specific DNC and exact-number suppression
- local-time calling windows
- valid company caller ID
- assigned-line enforcement
- one active session per VA
- one connected seller per VA
- atomic prospect reservation
- idempotent start, cancel, hang-up, and completion
- signed provider callbacks
- durable callback replay protection
- daily dial and spend caps
- company, campaign, VA, and line kill switches
- stale-session and orphaned-leg recovery
- no automatic cold SMS
- no dialing from acquisitions or dispositions lines

Software controls support but do not replace legal review, provider policy review, written calling
procedures, staff training, or campaign-specific advice.

### 9.2 Multi-Line Activation Gate

Two- or three-line calling creates a risk that more than one person answers before a VA is
available. It therefore remains disabled until Stonegate has:

- a stable single-line baseline
- counsel-approved calling and abandonment procedures
- live-answer connection and abandonment measurement
- minimum ring-time enforcement
- a compliant no-agent-available treatment
- manager-visible per-campaign records
- real-time cancellation of outstanding legs
- call reputation monitoring
- a tested emergency stop

The system must compute abandonment and connection metrics from durable provider evidence. It may
not rely on a VA's manual disposition alone.

## 10. Manager Controls And Measurement

### 10.1 Configuration

Managers need controls for:

- active VAs
- campaigns, cohorts, and calling batches
- script version by asset class
- dedicated number or line pool
- local calling window and timezone
- retry cadence and maximum attempts
- callback priority
- daily dial and cost caps
- recording policy
- default and maximum line count
- single-line, two-line pilot, or three-line pilot eligibility
- campaign and company stop controls

### 10.2 Operational Health

Managers should see:

- VAs ready, calling, connected, in wrap-up, paused, reconnecting, or offline
- stale sessions
- queued and ringing legs
- callback backlog
- provider errors
- line or number failures
- recording and transcription failures
- suppression or compliance blockers

### 10.3 Business Metrics

Measure by VA, campaign, cohort, list, date, and line mode:

- attempts per paid hour
- human conversations per paid hour
- conversations longer than 60 seconds
- right-party contact rate
- qualified sellers per 100 right-party conversations
- appointments set and held
- accepted warm handoffs
- signed contracts
- closed assignments
- gross and contribution profit
- dialer and labor cost per qualified seller
- cost per contract
- profit per paid VA hour

### 10.4 Quality And Reputation Metrics

- short calls
- silent or dead-air calls
- blocked or failed calls
- no-answer and voicemail rate
- duplicate-call incidents
- seller complaints
- DNC requests
- abandonment and connection time for future multi-line pilots
- number reputation and answer-rate trend

Line count should be increased only when profit and quality improve together. Raw dial count is
not a scale decision.

## 11. Start-To-Finish Implementation Roadmap

The phase table is the progress ledger. Update the status in this file as work ships.

| Phase | Deliverable | Status |
| --- | --- | --- |
| D0 | Canonical architecture, scope, acceptance gates, and roadmap | Implemented |
| D1 | Additive dialer schema and feature flags | Implemented |
| D2 | Prospect-aware Voice context and Twilio provider adapter | Implemented |
| D3 | Dial-session coordinator, queue reservation, and recovery | Implemented |
| D4 | Browser softphone and single-line call controls | Implemented; globally available under manager gates |
| D5 | Per-VA dashboard and live qualification checklist | Implemented; available to approved native campaigns |
| D6 | Dispositions, cadence, handoff, and appointment automation | Implemented; available to approved native campaigns |
| D7 | Recording, transcript, AI notes, and evidence continuity | Implemented; available to approved native campaigns |
| D8 | Inbound callbacks, manager controls, and operational health | Implemented; available under manager gates |
| D9 | Analytics, quality, cost, and launch readiness | Implemented; technical controlled-pilot readiness only |
| D10 | Controlled single-line production acceptance | Workflow implemented; live pilot evidence and owner acceptance still required |
| D11 | Optional two-line pilot | Planned |
| D12 | Optional three-line or adaptive pacing pilot | Planned |

### D0. Canonical Architecture And Roadmap

Deliverables:

- record the native-dialer decision
- preserve BatchDialer as the production calling baseline during the historical native build
- define the VA dashboard and qualification behavior
- identify current data-model constraints
- define implementation and activation gates

Exit criteria:

- one canonical roadmap exists
- no second roadmap competes for the same subject
- future implementation can be checked against explicit acceptance criteria

### D1. Additive Dialer Schema And Feature Flags

Implementation:

- add dialer profile, session, leg, and qualification response records, and extend the existing
  provider-event archive with dialer correlation and ordering evidence
- add organization, VA, campaign, and line-level concurrency limits
- add unique active-session and provider-call constraints
- preserve existing ProspectingAttempt behavior
- add migrations with safe defaults and rollback-aware data handling
- add serializers, validation, audit actions, and RBAC scope
- hard-cap production concurrency at one

Tests:

- migration structure plus PostgreSQL upgrade and downgrade SQL generation from revision 0102
- one active session per VA
- one active reservation per prospect
- provider event replay and out-of-order handling
- organization isolation
- line-count cap cannot be bypassed by request payload

Exit criteria:

- schema supports one to three legs without enabling multi-line production
- existing BatchDialer and manual Prospecting tests remain green

Implementation record (2026-08-19):

- migration `0103_native_prospecting_dialer` adds the D1 tables, concurrency columns, integrity
  checks, partial unique indexes, and downgrade path
- feature controls are present in application settings and deployment templates; unconfigured
  environments remain fail-closed, the production API and worker explicitly enable controlled
  native calling, and the effective production cap is one line across the organization
- managers can configure and list organization-scoped VA dialer profiles, while an assigned caller
  can read only their own dialer context
- request payloads can record future one-to-three-line preferences but cannot override the
  server-computed one-line effective limit
- verified provider callback state reduction locks each dial leg before applying an update and
  ignores replayed, stale, regressive, incompatible-terminal, and post-terminal updates
- the phase adds no call-placement, session-control, browser softphone, or activation endpoint;
  those remain gated behind D2 through D4
- focused migration, configuration, RBAC, service-boundary organization-isolation,
  active-session, connected-state, qualification, and provider-replay tests pass alongside the
  existing BatchDialer, Twilio Voice, and manual Prospecting regression suites

### D2. Prospect-Aware Voice Context And Provider Adapter

Implementation:

- extend Voice call intent and call record context safely for cold prospects
- add prospecting Voice endpoints
- add a provider-neutral call adapter
- request initiated, ringing, answered, and completed callbacks
- support cancel, hang up, fetch state, and recording callbacks
- validate every callback and correlate it to one dial leg
- configure dedicated prospecting-line purpose and permissions

Tests:

- warm CRM calls remain unchanged
- cold calls never require a fake contact or conversation
- provider failures reach a terminal recoverable state
- cancellation and duplicate callback paths are idempotent
- wrong organization, user, line, or prospect is rejected

Exit criteria:

- a controlled API test can create and reconcile one cold prospect call
- no browser UI is required yet

Implementation record (2026-08-19):

- migration `0104_prospecting_voice_context` extends the existing Voice intent and call records
  with a strict cold-prospect context; a call is either a normal CRM conversation call or a
  prospecting call linked directly to one prospect, attempt, and dial leg, never both
- the provider-neutral `VoiceCallProvider` boundary now supports create, fetch, cancel, and hang-up
  operations, with Twilio implemented behind that boundary and the existing warm-call behavior
  preserved
- controlled prospecting APIs can create one cold call for a pre-reserved D1 dial leg, reconcile
  its provider state, cancel a ringing call, or hang up a live call
- signed root-call, child-call, dial-result, recording, and disclosure callbacks are correlated to
  the exact organization, intent, call record, line, prospect, attempt, and dial leg; duplicate,
  stale, mismatched, and out-of-order events are rejected or ignored safely
- provider failures remain visible and recoverable, failed call-control requests can be retried,
  and durable prepared and dispatching checkpoints are committed before provider placement so an
  immediate callback cannot outrun its Stonegate record or an ambiguous retry duplicate a call
- dedicated cold-calling lines use purpose `prospecting_outbound`; they are excluded from ordinary
  warm seller-call selection, and at the D2 boundary inbound calls on those lines were deliberately
  blocked rather than creating a fake seller lead; D8 now supplies the isolated callback workflow
- cold-call recordings can be attached to their prospecting call evidence, but D2 intentionally
  does not send them into the warm CRM transcript or AI-note pipeline; that continuity belongs to
  D7
- D2 does not add the D3 session coordinator, change session/current-record pointers, add a browser
  softphone, or authorize live calling by itself; the completed system remains capped at one line
- focused cold-call, provider-adapter, migration, model, callback, retry, authorization, and
  no-fake-CRM-record tests pass alongside the existing warm Twilio Voice and D1 dialer suites

### D3. Dial-Session Coordinator, Queue Reservation, And Recovery

Implementation:

- start, pause, resume, end, and heartbeat session APIs
- atomic next-record selection and lease
- callback, correction, retry, and new-record priority
- calling-window, suppression, eligibility, and cap enforcement
- durable wrap-up lock
- stale browser, stale session, orphaned call, and worker-restart recovery
- campaign and company kill switches

Tests:

- two VAs cannot reserve the same prospect
- one VA cannot start two sessions
- double clicks and HTTP retries do not duplicate calls
- refresh restores the same active state
- overdue callback wins over a new record
- paused, stopped, blocked, and after-hours sessions cannot dial

Exit criteria:

- simulated calls can progress through the entire server state machine reliably

Implementation record (2026-08-19):

- authenticated start, read, heartbeat, pause, resume, stop, recovery, and reserve-next APIs now
  operate one durable browser lease per assigned caller and reject stale lease ownership
- call start, cancel, hang-up, and native disposition completion require that same exact browser
  lease; an expired or replaced tab cannot control or advance the session, while a manager-entered
  disposition pauses the VA session instead of reserving work in another person's browser
- the server atomically selects and reserves the next eligible record in callback, returned
  correction, retry, then new-record order; PostgreSQL candidate locks and a workspace capacity
  lock prevent duplicate-prospect and line-cap races
- company, campaign, caller, profile, cohort, batch, market, territory, dedicated-line, calling
  window, daily dial, daily spend, phone validity, and suppression rules are rechecked before both
  reservation and provider placement
- company and campaign switches default off, require acquisition-management authority, release
  calls that have not started, and safely drain calls that may already have reached the provider
- provider events drive the durable session through dialing, ringing, connected, and wrap-up;
  disposition completion is row-locked, cannot advance until the call leg is terminal, renews the
  authenticated caller lease before exposing the next record, and never exposes work during
  wrap-up
- provider placement uses recoverable prepared and dispatching checkpoints, immediate callbacks
  can finalize the pending provider identity, and provider fetch repairs a missed terminal callback
  into the call, leg, and session records without creating another outbound call
- the communications worker recovers stale leases and queued-only orphans without ever initiating
  or ending a provider call; possible live calls are preserved without endlessly renewing browser
  ownership, while exact-token browser recovery rotates the lease and resumes the same durable
  state
- reservation cost holds and actual-cost fields make daily spend enforcement possible without
  treating an unstarted released call as provider spend
- focused coordinator tests cover switch gates, replay and duplicate prevention, priority order,
  pause/resume/stop, terminal-to-wrap-up advancement, stale-tab and expired-lease rejection,
  manager-safe completion, provider-start recovery, missed-callback reconciliation, stale-provider
  preservation, and queued orphan release alongside the D1 and D2 regression suites
- D3's coordinator is production-available through the completed browser workbench, while company,
  campaign, caller-profile, and dedicated-line gates remain fail-closed until a manager approves an
  isolated rollout. Effective organization-wide concurrency remained one, and BatchDialer stayed
  the production calling system through D10 acceptance

### D4. Browser Softphone And Single-Line Call Controls

Implementation:

- add the supported Twilio Voice JavaScript SDK
- create a client-only softphone boundary
- initialize and refresh short-lived Voice tokens
- add microphone and device readiness
- show provider state in the dashboard
- add Start Calling, Pause, Resume, Stop Ringing, Mute, Hang Up, Retry, and End Shift
- recover from token expiry, temporary network loss, and browser refresh
- keep effective line count fixed at one

Tests:

- component state transitions
- denied microphone permission
- token refresh
- disconnect and reconnect
- browser back, refresh, duplicate tab, and stale session
- accessibility and keyboard controls

Exit criteria:

- controlled test numbers can complete browser-to-phone calls with correct live state

Implementation record (2026-08-19):

- the supported Twilio Voice JavaScript SDK now sits behind a client-only softphone boundary;
  microphone readiness is explicit, denied or unsupported devices fail closed, and short-lived
  outbound-only Voice tokens are refreshed before expiry without exposing the signing secret to
  the browser
- the API issues a Voice token only for the authenticated caller's exact current browser lease,
  active dial session, and dedicated Acquisitions `prospecting_outbound` line; the resulting Voice
  identity is bound to the caller, dial session, browser owner, and current lease fingerprint
- browser call preparation creates one durable, idempotent intent and call record before
  `Device.connect`; retries reuse that pending intent and never silently place a second call
- Twilio's browser/root call is treated only as browser-audio state. Stonegate does not mark the
  seller ringing or connected until the child `<Number>` leg supplies that evidence, and Stop
  Ringing targets the seller child when known or safely terminates the browser root while the child
  is still unknown
- if microphone, SDK, or network setup fails before Twilio produces any root or child call ID, the
  browser-only pending call can be cancelled locally and idempotently. An untouched preparation
  that expires after its five-minute authorization window is terminalized on refresh, its queue
  reservation is safely released, and End Shift can then finish instead of draining forever
- all API responses carrying a dialer lease or Voice JWT use `Cache-Control: private, no-store`.
  The Voice JWT remains memory-only. The dial-session ID, browser-session ID, and lease may use
  same-tab `sessionStorage` solely to restore an idle page; they never enter `localStorage`, URLs,
  DOM attributes, or logs, and terminal end or stop clears the stored lease
- the operator contract includes Start Calling, Pause, Resume, Stop Ringing, Mute, Hang Up, Retry,
  and End Shift. Durable server session and child-leg state remains the seller-call truth, while
  browser SDK/audio status is shown separately so a connected headset is never presented as a
  connected seller
- duplicate tabs use leader election so only one tab operates the dialer, while the server lease
  remains authoritative. A same-tab page reconstruction may restore the same still-valid lease
  from `sessionStorage`; an expired lease uses the audited recovery path, rotates ownership, and
  invalidates the prior Voice identity
- session start and expired-lease recovery retain their exact idempotency and browser identifiers
  in same-tab storage until the server response is known. If a successful response is lost, the
  browser replays the same request and the server returns the already-rotated lease without a
  second ownership change; only a keyed digest of the prior recovery credential is retained
- heartbeat authority and read-only status synchronization have separate warning channels, so a
  successful poll cannot hide an expired or lost browser lease. Active calls install a same-page
  history sentinel and explicit leave confirmation instead of attempting to undo browser Back
  after navigation has already occurred
- a full browser reload cannot reattach JavaScript audio to a call already in progress. After such
  a reload the UI restores durable server state and offers a server-side hang-up; it must never
  claim that live browser audio resumed
- the production feature was globally available, its effective concurrency remained exactly one
  line across the organization, company and campaign activation switches remained independent
  fail-closed gates, and BatchDialer remained the production calling system through controlled D10
  acceptance
- focused backend coverage exercises lease-bound token issuance, no-cache controls, idempotent
  preparation, stale lease and duplicate-browser rejection, root-versus-child status truth,
  exact lost-response recovery replay, pre-provider retry/cancel/expiry, provider cancel/hang-up,
  and warm-Voice isolation; frontend coverage exercises the softphone state boundary, token
  refresh, microphone failure, reconnect behavior, control-state policy, navigation protection,
  lease recovery identity, and browser-audio lifecycle independently from seller call state

### D5. Per-VA Dashboard And Live Qualification Checklist

Implementation:

- convert the existing Prospecting workspace into the operational dialer layout
- display current owner, ranked phone, property, source, history, and warnings
- display approved script and asset-specific questions
- autosave each qualification response
- implement gray, green, yellow, and red states
- show progress count and missing warm-handoff requirements
- preserve answers across refresh and reconnect
- provide manager monitoring without exposing unrelated data to VAs

Tests:

- VA assignment scope
- house and land scripts
- every question state
- autosave, retry, and concurrent edit behavior
- no blank answer appears green
- AI suggestion never overwrites a human answer
- mobile fallback and desktop headset layout

Exit criteria:

- a VA can run a complete controlled conversation from one screen

Implementation record (2026-08-19):

- the workbench resolves the exact pinned House or Land script for each entry and presents the
  current owner, ranked phone numbers, property, source, attempt history, and bounded warnings
- the current attempt owns its server-side checklist; prior-attempt answers are history only, and
  gray, green, yellow, and red are explicit labeled states rather than color-only signals
- each question autosaves independently with assigned-caller and native-lease authorization,
  optimistic revision checks, idempotent retries, and visible conflict or retry handling
- qualification rows are authoritative during completion, so a stale final form cannot overwrite
  newer saved evidence; progress and missing warm-handoff requirements derive from those rows
- saved answers survive refresh and reconnect; managers receive organization-wide read-only
  monitoring while VAs remain limited to assigned work
- human answers are never replaced by AI suggestions, and a new attempt is never prefilled from
  historical responses; D5 adds no disposition, cadence, handoff, appointment, transcript, or AI
  side effects reserved for D6 and D7
- responsive and accessible workbench behavior plus focused backend and frontend tests cover the
  pinned scripts, four states, authorization, autosave/retry/conflict behavior, refresh recovery,
  assignment scope, and stale-form protection
- the native dialer was available only to manager-approved one-line campaigns pending D10
  acceptance; BatchDialer remained the production calling system

### D6. Dispositions, Cadence, Handoff, And Appointment Automation

Implementation:

- connect terminal provider states to the existing attempt completion service
- retain existing outcome validation and measurement
- distinguish technical failure from seller disposition
- automatically advance no-answer and voicemail cadence
- require callback date when appropriate
- suppress wrong numbers and DNC outcomes correctly
- create exactly one warm lead for Interested
- create exactly one lead and appointment for Appointment Set
- pause new calls until wrap-up is valid

Tests:

- every disposition
- required qualification enforcement
- callback scheduling and priority
- duplicate handoff and appointment replay
- wrong-number fallback to another eligible ranked number
- exact-number DNC suppression

Exit criteria:

- the native dialer was required to produce the same or stronger CRM handoff guarantees as the
  then-current BatchDialer workflow

Implementation record (2026-08-19):

- terminal provider evidence now gates seller dispositions; failed or cancelled provider calls use
  a separate technical-failure action and do not consume seller-facing cadence or manufacture a
  contact result
- every native wrap-up uses a stable idempotency key, semantic request digest, caller lease receipt,
  and row-locked transaction so an identical lost-response replay returns the prior result while a
  conflicting replay is rejected
- no-answer and voicemail outcomes use the pinned script's bounded retry delays and maximum seller
  attempts; technical retries and seller-requested callbacks remain separate queue classes and
  callback commitments require a future date and time
- wrong-number handling invalidates and suppresses only the exact dialed number, then immediately
  reserves the next eligible ranked number when one exists; DNC suppresses the exact E.164 number
  across the organization and blocks the source prospect
- Interested creates or reuses one warm CRM lead and one reviewable handoff; Appointment Set also
  creates one attempt-linked appointment, with the seller-property address persisted as the default
  location and explicit locations required for phone, video, and office meetings
- the connected ranked phone becomes the CRM contact's primary phone while the original valid phone
  remains available as a secondary method
- the VA wrap-up screen groups seller outcomes, blocks invalid or in-flight wrap-up, gives technical
  failures their own action, confirms only server-returned automation, preserves exact-payload retry,
  and keeps manager monitoring read-only
- focused D6 contracts plus the complete prospecting coordinator, workbench, Voice lifecycle,
  migration, and provider-handoff regressions cover replay, cadence exhaustion, callbacks,
  qualification enforcement, appointment uniqueness, ranked fallback, and exact-number suppression
- the native dialer was available only to manager-approved one-line campaigns pending D10
  acceptance; BatchDialer remained the production calling system

### D7. Recording, Transcript, AI Notes, And Evidence Continuity

Implementation:

- attach recordings to prospect attempts
- expose secure playback, pause, resume, seeking, and download
- queue one transcript per eligible recording
- create full transcript and compact quick-read notes automatically
- extract evidence-backed qualification suggestions
- flag conflicts without overwriting human answers
- link accepted call evidence into the warm seller timeline
- reuse retention, deletion, retry, and exhaustion controls

Tests:

- long recordings
- unavailable media and provider retry
- transcript failure and manual retry
- no double transcription after handoff
- no recording or transcript leakage across roles or organizations
- automatic notes appear in Prospecting and the accepted seller timeline

Exit criteria:

- every accepted recorded test call is auditable from cold prospect through warm lead

D7 implementation record:

- completed, connected seller conversations now enqueue exactly one transcript after both the
  signed recording callback and caller wrap-up are present, regardless of which arrives first;
  no-answer, voicemail, wrong-party, incomplete, unsigned, deleted, and mismatched call graphs are
  excluded
- transcript processing reuses the existing provider-private recording controls, retention and
  deletion policy, bounded automatic retries, exhaustion state, and authorized manual retry; paid
  transcription text is checkpointed so a later notes failure does not purchase the transcript a
  second time
- the completed-attempt history lazily loads secure recording playback with pause, resume, seek,
  playback speed, timestamp jumps, and separately authorized audio and transcript downloads
- AI creates a compact quick read and full structured notes automatically, supports both house and
  land scripts, records transcript evidence by timestamp, and stores qualification output only as
  suggested, corroborated, or conflicting evidence without replacing caller-entered answers
- accepted handoffs create one source-call-linked seller-timeline note in either transcript-first or
  handoff-first order; the original call time is preserved, the assigned acquisitions user can
  access the retained evidence, and unrelated callers, roles, and organizations cannot
- call-quality analysis can use automatically completed prospecting transcripts without adding an
  approval step; native calling remains limited to manager-approved one-line campaigns pending
  controlled D10 acceptance
- focused D7 contracts cover long calls, unavailable provider media, retry/exhaustion/recovery,
  exactly-once enqueue and timeline linkage, more-than-one-page fallback discovery, house/land
  evidence conflicts, role and organization isolation, and prior D4-D6 browser regressions

### D8. Inbound Callbacks, Manager Controls, And Operational Health

Implementation:

- match inbound calls to prospecting line and recent prospect
- route to assigned VA or approved fallback
- open the matched prospect
- create a missed-callback task when unanswered
- add dialer profile, line, cap, hours, script, and line-count controls
- add live session and error monitoring
- add manager stop controls and safe recovery actions

Tests:

- known and unknown callback
- VA available, unavailable, and offline
- voicemail and missed-call task
- manager line-count and campaign controls
- stop control cancels or safely drains calls

Exit criteria:

- a seller callback can be handled without manually searching BatchDialer or a spreadsheet

Implementation record (2026-08-19):

- production makes the native dialer globally available in both API and worker services while the
  company, campaign, caller-profile, dedicated-line, calling-window, and suppression gates remain
  independently fail-closed; the effective organization-wide cap is enforced at one line
- dedicated `prospecting_outbound` lines now accept inbound callbacks without creating a fake warm
  lead, contact, or conversation; exact caller-number evidence must match a recent outbound attempt
  placed from that same line, and ambiguous or unknown callers remain isolated for review
- callback routing prefers the matched assigned VA when that VA has a fresh eligible session on the
  receiving line, then uses only configured fallbacks with authority to access the matched work;
  terminal provider replays do not re-ring staff
- callback state is durable and monotonic across parent and child provider events, multi-target
  ringing cannot be closed by one failed child leg, and voicemail or a fully missed callback creates
  exactly one urgent return-call task even when provider callbacks race or replay
- **Prospecting > My Calls** polls callback cards independently and opens a matched prospect only
  after an explicit user action, so a new callback never steals the caller's current workspace
- **Prospecting > Dialer control** gives managers audited company and campaign switches, caller and
  dedicated-line setup, daily caps, calling-hours and approved-script policy creation, live session
  and callback health, sanitized recent errors, safe-drain and unanswered-call stop controls, and
  guarded provider reconciliation or orphan recovery
- **Settings > Communications** preserves an explicit **Prospecting outbound and callbacks** line
  purpose instead of silently converting an Acquisitions prospecting line back to seller calls
- focused migration, model, callback matching and routing, provider replay, access isolation,
  voicemail and missed-task, manager control, stop and recovery, warm Voice regression, frontend
  contract, type, lint, and production-build coverage protect the D8 operating boundary
- BatchDialer remained the production calling system during this historical phase; D9 analytics
  was implemented, but D10 controlled single-line acceptance was still required before broad
  rollout

### D9. Analytics, Quality, Cost, And Launch Readiness

Implementation record (2026-08-19):

- add the manager-only **Prospecting > Analytics** workspace and a private, no-store analytics API;
  cost, revenue, and profit values remain hidden without `financials:view`
- filter by an inclusive UTC start and end date plus optional source, campaign, cohort, VA/caller,
  and dial mode; the default window is the most recent 30 UTC dates and a request cannot exceed
  366 dates
- use a versioned activity-cohort attribution model: native work enters at dial start, paid-ad and
  other acquisition enters at lead creation, and BatchDialer activity enters at the first durable
  BatchDialer handoff touch even when it matched an existing CRM lead, with lead creation used as a
  secondary attribution timestamp when no durable handoff touch exists; cost enters at incurred
  date and work time at work date; later downstream outcomes remain attributed to that originating
  work and are reported as of the response timestamp
- preserve paid/other acquisition attribution when that lead later receives a BatchDialer handoff.
  Source scorecards can therefore overlap and are explicitly non-additive, while the all-source
  summary de-duplicates the same lead and downstream record
- build scorecards by VA, campaign, cohort, imported list, dial mode, and source, with daily UTC
  trend evidence
- compare native Stonegate, BatchDialer, and paid-ad sources on attributable business outcomes,
  with other attribution kept in its own bucket; raw dial rates remain unavailable for a source
  that does not provide raw attempt evidence
- connect recorded VA work sessions and campaign-cost records to paid time, VA labor, list,
  provider, other, and total cost; preserve unavailable values when the underlying evidence is
  absent instead of displaying an invented zero
- trace qualified native prospecting work through submitted and accepted handoff, appointment set
  and held, signed seller contract, closed assignment-strategy transaction, collected gross revenue,
  and contribution profit; gross comes from collected revenue records, while the versioned
  contribution-profit formula uses approved reconciliation company-profit evidence
- report calling efficiency, contact and conversion rates, short calls, blocked or failed calls,
  no-answer and voicemail outcomes, duplicate-call incidents, seller complaints, DNC requests,
  abandoned calls, connection time, number reputation, and answer-rate trend when their supporting
  evidence exists
- expose explicit coverage for raw attempts, paid hours, provider cost, appointment outcomes,
  profit attribution, and number reputation; every nullable metric renders as **Unavailable** when
  the required source record is missing
- publish the deterministic definition, source records, attribution timestamp, and unavailable
  rule for each material metric in **How these metrics are calculated**
- reject analytics windows that would materialize more than 50,000 origin records and require the
  manager to narrow the date or operating filters
- add pass, warning, or block checks for the dedicated line, browser token configuration, callback
  routing, recording policy, session health, organization-wide one-line cap, and worker health
- label the best possible D9 result **Ready for controlled pilot**. This is a technical status only;
  it never marks the native dialer Active or Accepted and always retains the D10 requirement
- document cost entry, troubleshooting, safe recovery, and the historical non-overlapping
  cohort-return procedure in the setup and operating references

Tests:

- deterministic metric definitions and nullable coverage behavior
- inclusive UTC cohort and date boundaries plus scoped filter validation
- no-answer, human contact, qualified seller, handoff, appointment, contract, close, and reconciled
  profit attribution
- provider-cost de-duplication and labor-cost linkage
- readiness blocker accuracy, including stale sessions, line/token/callback/recording configuration,
  the hard one-line cap, and worker health
- manager-only API and navigation access plus frontend contract, type, lint, and build coverage

Exit criteria:

- management can compare native Stonegate, BatchDialer, and paid-ad cohorts on attributable business
  outcomes without mistaking missing evidence for zero
- a manager can identify technical blockers and the exact missing measurement coverage before a
  controlled pilot
- D10 remains mandatory and is not production-accepted; its workflow is implemented, but D9 output
  and an empty D10 record cannot authorize general production use

### D10. Controlled Single-Line Production Acceptance

Implementation record (2026-08-19):

- Stonegate stores one versioned pilot scope containing exactly one VA, campaign, cohort, calling
  batch, and dedicated Voice line. A current `smoke_testing`, `running`, or owner-accepted scope is
  required before a new native dial session may start; smoke sessions remain limited to the saved
  test records.
- Technical D9 readiness remains separate from D10 acceptance. A green D9 result can permit the
  controlled pilot to begin, but it cannot mark the dialer accepted.
- Starting a draft stores one to ten controlled E.164 numbers from active Stonegate staff
  forwarding profiles and moves the pilot to `smoke_testing`. Every controlled number must also be
  an eligible test record in the selected calling batch. While this state is active, the
  coordinator can reserve only those saved records; durable answered seller-call records with
  canonical recordings, signed seller-child evidence, every distinct root and child provider call
  ID, provider-reported charges, and provider references must pass the smoke-test check before the
  pilot moves to `running` and the rest of the exact batch becomes callable.
  Selected records prove answered, recorded controlled seller calls, while cost evidence covers
  every provider-started ID in the entire ended smoke stage, including root-only failures. The
  smoke stage is bounded at 50 reservations / 100 provider IDs and is excluded from production
  shift volume and timing.
- Every pilot attempt receives its own manager acceptance review, including no-answer, voicemail,
  canceled, failed, and connected outcomes. AI call-quality evidence can support that review but
  cannot replace it. Canonical recording, transcript, and structured-note evidence is required for
  applicable connected seller conversations, not for non-contact outcomes that should have no
  transcript.
- Each submitted shift is recomputed from linked session, leg, attempt, callback, handoff,
  recording, transcript, cost, and review evidence. Every reservation counts toward the dial-cap
  proof; every provider-started root/child graph counts toward billing; only signed seller-child
  calls count toward volume, productive timing, outcomes, and duplicate checks. The manager must
  reconcile every distinct provider call ID to its provider-reported charge and a provider
  usage-export, invoice, or call-detail reference; a typed aggregate total never satisfies the
  billing gate, while a referenced provider-reported `$0` remains valid.
- Controlled-number checks, provider-billing reconciliation, a separate BatchDialer comparison,
  and two server-observed safety drills remain explicit evidence sections. The kill-switch drill
  requires audited company/campaign switch cycles, stopped sessions, and a real daily-cap
  reservation denial. The later rollback drill requires a distinct campaign switch cycle, zero
  live calls, immutable evidence, a hashed unworked remainder, and a subsequent clean shift.
  Evidence that Stonegate cannot observe directly is labeled as a human attestation rather than
  presented as an automated fact.
- Final acceptance is an explicit Owner or Founder/operator decision. The server recomputes every
  hard gate, requires **ACCEPT SINGLE-LINE DIALER** to accept or **REJECT SINGLE-LINE DIALER** to
  reject plus a reason, freezes an evidence snapshot and digest, and does not permit a hard-gate
  override.
- A material scope or safety-configuration change makes the prior decision unusable for new
  sessions. Rollback preserves all native evidence and never reactivates the same cohort in
  BatchDialer automatically.
- The terminal close control requires **ROLL BACK SINGLE-LINE PILOT** typed exactly. It records an
  unstarted draft as `cancelled`; only a started pilot is recorded as `rolled_back` with its scope
  disabled and evidence preserved.
- Owner acceptance authorizes only the frozen exact scope while the organization acceptance gate
  remains enabled. An Owner or Founder/operator can type **REVOKE SINGLE-LINE DIALER** with a reason
  to block every new seller bridge that has not already been authorized for that accepted scope,
  safely drain provider work already authorized or in progress, and preserve its evidence; the
  terminal history remains visible. Under the current dormant plan, that history cannot be used to
  create or resume a replacement D10 pilot.

Rollout:

1. Add controlled owner and staff test records to the selected batch, start `smoke_testing`, and
   prove an answered recorded call before broadening the exact pilot to `running`.
2. One VA and one small non-overlapping campaign.
3. Review every call, disposition, recording, callback, and handoff.
4. Reconcile every distinct root and seller-child provider call ID to its provider-reported charge
   and provider evidence reference; confirm reservation-based daily caps and the audited kill
   switches.
5. Keep the saved daily dial cap between 25 and 50 reservations so the safety cap can still permit
   a qualifying shift, then pass three fully reviewed shifts on separate local dates, each with at least 25 terminal signed
   seller calls and 60 minutes of provider-signed right-party conversation time, without duplicate calls,
   lost answers, stuck sessions, or missing callbacks. At least 75 signed seller calls must qualify
   in total, and every reserved attempt must have a manager review.
6. Compare against a separate BatchDialer cohort.
7. Mark single-line Active only after owner acceptance.

Rollback:

- pause the native campaign
- end all native sessions
- identify the unworked remainder for a separate, controlled return to BatchDialer
- keep native call evidence read-only
- never place the same active cohort in both systems

Exit criteria:

- the native single-line dialer is Active for approved campaigns
- BatchDialer remains available until management makes a later cancellation decision

Shipping the acceptance workflow is not the exit criterion. D10 remains open until the real pilot
has accumulated the required linked evidence and an authorized owner has accepted it.

### D11. Optional Two-Line Pilot

This phase begins only by explicit owner decision.

Implementation:

- enable two ringing legs for one approved VA and campaign
- keep only one connected seller
- cancel outstanding legs immediately after a human connection
- measure connection time, collisions, abandonment, dead air, short calls, complaints, and answer
  rate
- automatically reduce to one line when risk or capacity thresholds are crossed

Exit criteria:

- counsel and owner approve the operating procedure
- quality and contribution profit outperform the single-line control
- per-campaign evidence supports continued activation

If these criteria are not met, Stonegate remains a single-line dialer by design.

### D12. Optional Three-Line Or Adaptive Pacing Pilot

This phase also requires explicit owner decision.

Implementation:

- extend the proven two-line coordinator to three lines
- use measured answer probability and wrap-up capacity rather than a fixed aggressive pace
- preserve the one-connected-seller invariant
- enforce campaign-specific risk and abandonment controls
- automatically fall back to two or one line

Exit criteria:

- the three-line pilot improves profit per paid VA hour
- held appointments, accepted handoffs, seller experience, and number reputation do not decline
- production evidence and manager review support continued use

Three-line operation is optional. The final business answer may legitimately be that single-line
quality produces the best return.

## 12. Version-One Definition Of Done

The native single-line dialer is not done until all of the following are true:

- each VA has an assignment-scoped dashboard
- a manager can assign a campaign, batch, script, and dedicated line
- headset and microphone readiness is visible
- Start Calling selects and reserves the correct next prospect
- one click places exactly one call
- call state is visible from request through completion
- the correct person and property remain on screen when connected
- qualification answers autosave and use the approved color states
- dispositions automatically control cadence, callbacks, suppression, and warm handoff
- recordings, transcripts, and compact notes attach to the attempt
- qualified sellers and appointments enter the existing CRM exactly once
- inbound callbacks return to the correct prospect workflow
- managers can pause calling and see session health
- metrics connect dials to conversations, appointments, contracts, cost, and profit
- automated tests cover security, concurrency, recovery, and provider replay
- a controlled production pilot has passed
- BatchDialer remains the production calling system; the native runtime is dormant

## 13. Explicitly Deferred From Version One

- live two- or three-line production dialing
- predictive or adaptive pacing
- AI voice agents
- prerecorded sales messages
- automatic voicemail drops
- unsolicited cold SMS
- real-time AI speech recognition for checklist completion
- automatic skip tracing
- automated number rotation intended to bypass spam detection
- removing the BatchDialer integration

These are deferred to keep the first release focused, measurable, and dependable.

## 14. Implementation Working Rules

For every phase:

1. Inspect the current main branch before editing.
2. Use additive migrations and preserve production data.
3. Keep BatchDialer and warm Voice behavior working.
4. Add backend and frontend tests proportional to the risk.
5. Run targeted tests first, then broader affected quality gates.
6. Update this progress ledger when implementation status changes.
7. Update SYSTEM_MAP.md, FINISHING_ROADMAP.md, USER_MANUAL.md, UI_CONTROL_REFERENCE.md,
   OPERATING_MODEL.md, and SETUP_REFERENCE.md when the corresponding behavior actually changes.
8. Treat Implemented, Configured, and Active as separate states.
9. Commit and push each coherent phase to main when the owner requests execution.
10. Stop for external configuration or production acceptance when owner action is required; never
    alter credentials without direct permission.

## 15. Primary Repository Work Areas

Expected backend areas:

- apps/api/app/models/foundation.py
- apps/api/alembic/versions
- apps/api/app/schemas/prospecting.py
- apps/api/app/routers/prospecting.py
- apps/api/app/services/prospecting.py
- a dedicated prospecting dialer coordinator service
- apps/api/app/services/voice.py
- apps/api/app/integrations/twilio_voice.py
- apps/api/app/integrations/twilio_voice_calls.py
- apps/api/app/services/call_intelligence.py
- apps/api/app/services/prospecting_copilot.py
- apps/api/app/domain/rbac.py

Expected frontend areas:

- apps/web/src/app/os/prospecting/page.tsx
- apps/web/src/app/os/prospecting/prospecting-workspace.tsx
- apps/web/src/app/os/prospecting/prospecting.module.css
- apps/web/src/app/lib/api.ts
- a client-only Twilio softphone component
- reusable recording, transcript, and quick-read controls

Expected test areas:

- apps/api/tests/test_prospecting_workbench.py
- apps/api/tests/test_prospecting_measurement.py
- apps/api/tests/test_asset_prospecting.py
- apps/api/tests/test_campaign_management.py
- apps/api/tests/test_twilio_voice.py
- apps/api/tests/test_twilio_recordings.py
- apps/api/tests/test_call_intelligence.py
- new dial-session, dial-leg, provider-event, callback, and concurrency tests
- frontend component and information-architecture contract tests

## 16. External References

- Twilio Voice JavaScript SDK:
  https://www.twilio.com/docs/voice/sdks/javascript
- Twilio Voice Call resource and status callbacks:
  https://www.twilio.com/docs/voice/api/call-resource
- Twilio answering-machine detection:
  https://www.twilio.com/docs/voice/answering-machine-detection
- Twilio SHAKEN/STIR:
  https://www.twilio.com/docs/voice/trusted-calling-with-shakenstir
- FTC Telemarketing Sales Rule compliance guide:
  https://www.ftc.gov/business-guidance/resources/complying-telemarketing-sales-rule

Official requirements and provider behavior must be rechecked before any multi-line production
activation.
