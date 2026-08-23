# Acquisitions Performance Scorecard

## Purpose

The scorecard gives Stonegate managers a private, side-by-side, evidence-backed coaching view for
Austin and Devon while they continue splitting acquisitions work. It does not change lead
ownership, routing, permissions, or deal-credit rules.

Version 1 runs in **shadow mode**. It is meant to reveal coaching opportunities and data gaps—not
to automate compensation, employment, discipline, lead assignment, or declare a winner.

## Score policy

| Dimension | Weight | What counts |
| --- | ---: | --- |
| Speed to lead | 20% | Time from lead receipt to the first real outbound call, SMS, or email by that user |
| Follow-up discipline | 20% | Due primary next-action follow-up work completed on time |
| Conversation quality | 20% | Transcript-backed listening, discovery, objection handling, next-step clarity, professionalism, and compliance |
| Qualification and discovery | 15% | Completed acquisition qualification evidence and usable seller/property discovery |
| CRM hygiene | 10% | Timely, attributable outcomes and clean next-action documentation |
| Appointment execution | 5% | Mature appointment outcome documentation attributable to the user |
| Mature sales outcomes | 10% | Mature role-credit evidence for jointly or individually worked deals |

Weights are stored as basis points in the API so the total is exactly 10,000.

## Fairness rules

1. **Actual work beats assignment.** Lead ownership alone does not earn behavioral credit. Where
   possible, the score uses the user who made the call, sent the message, completed the session, or
   performed the outcome.
2. **Accepting a case is not speed to lead.** The timer stops on the first real outbound seller
   contact attempt recorded in Stonegate.
3. **Missing data is N/A, not zero.** A dimension without usable attributable evidence is
   unavailable and does not silently lower the overall result.
4. **Minimum samples apply.** Each dimension exposes its sample count and minimum. Below the
   minimum, the dimension is marked **Building**: its raw evidence remains auditable, but its numeric
   score and bar are withheld and it does not enter the overall result. A single call or appointment
   cannot create a published comparison.
5. **Coverage is explicit.** The overall score is withheld until at least 60% of the weighted policy
   has ready evidence. Coverage from 60% through 79% is provisional; 80% or more can become
   reliable when its dimension samples are sufficient.
6. **Shared outcomes receive fractional credit.** Mature deal outcomes use role-credit basis points
   instead of awarding the entire result to whichever user happens to own the lead today.
7. **Extra touches cannot game persistence.** Repeated activity by itself does not improve the
   follow-up score; the system looks for required work completed on time and a protected next step.
8. **External work is disclosed.** Calls, texts, appointments, or follow-up performed outside
   Stonegate cannot be measured and are surfaced as a scorecard warning.

## Conversation-quality guardrails

New recorded seller calls may receive a second transcript-grounded coaching analysis. The analysis
scores only observable words and conversation behavior:

- active listening;
- seller and property discovery;
- objection handling;
- next-step clarity;
- respectful, clear, non-manipulative language; and
- avoidance of unsupported promises, pressure, or binding claims.

The analysis must not infer or score vocal pitch, accent, dialect, personality, emotion,
enthusiasm, age, gender, disability, race, ethnicity, national origin, or any other protected or
identity-related characteristic. Grammar, speech patterns, and communication differences are not
scoring factors.

A call remains unscored when it is voicemail/no-answer, contains too little two-way conversation,
cannot reliably identify the Stonegate speaker, has less than 60% evaluation confidence, or lacks a
transcript citation for every category. A coaching-provider failure never blocks the normal call
summary or CRM field updates.

Historical calls are not automatically reprocessed. This avoids an unapproved AI-cost backfill and
allows comparable evidence to accumulate naturally after launch.

## Score interpretation

- **Building overall:** less than 60% weighted ready-evidence coverage; no overall score is
  published.
- **Building dimension:** some usable observations exist, but the minimum sample is not met; its
  numeric score is withheld and its policy weight is excluded from the overall result.
- **Provisional:** at least 60% coverage, but the evidence is still incomplete or sample minimums
  are not fully mature.
- **Reliable:** at least 80% coverage with sufficient supporting samples.
- **N/A dimension:** the OS has no usable attributable evidence for that behavior.

The 30-day view is the primary coaching window. The 90-day view reduces short-term noise and is
useful for trend context. Neither period should be interpreted without the visible sample sizes,
coverage, and warnings.

## Operational location

Managers with **Manage acquisition operations** access open **Leads → Lead Queue → Performance**
and choose the 30- or 90-day period. The tab is hidden from users without that permission. The view
shows each acquisition user side by side, followed by dimension evidence, strengths, focus areas,
sample sizes, and policy warnings. It deliberately does not show a rank or winner.

Every confirmed report shows its generation timestamp. Refresh covers both session-token retrieval
and the report request with one 12-second limit. If a refresh times out, the UI says whether a
confirmed snapshot for the selected period remains visible; it never claims that an absent or
different-period snapshot is current.

## Future review

After at least 30 days in shadow mode:

1. audit a sample of attributed calls, communications, tasks, sessions, appointments, and deal
   credits;
2. compare scorecard evidence with manager review;
3. look for differences caused by lead source, property type, market, or assignment mix;
4. revise thresholds only through a versioned policy change; and
5. keep all consequential decisions human-reviewed even if the score proves useful.
