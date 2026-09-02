# Alex Dispositions Outreach Workflow Roadmap

Last updated: September 1, 2026

## Product Decision

The Dispositions experience is built around Alex's real job: take a contracted deal, put the
available deal information in front of likely investors, work those investors one at a time, and
maintain the relationships that make future deals easier to sell.

The default operating path is:

`Under Contract -> Ready in Dispositions -> Start or Continue Outreach -> Pull and rank investors
-> SMS -> Call -> Email -> Record result -> Next investor, follow-up, or pause -> Interested buyer
-> Offer -> Buyer selected`

This sequence is guidance, not a workflow lock. Alex may shop a deal when facts, photos, title,
valuation, inspection, or the final packet are incomplete. He may upload or replace information at
any time, contact any otherwise eligible investor, skip or revisit a channel, work the list out of
order, pause, resume, record an offer, or return to relationship work whenever the situation calls
for it.

Checklists communicate what is complete, missing, uncertain, or worth attention. They do not
prevent work. Hard stops remain limited to permissions, Do Not Contact and channel suppression,
missing usable destinations or providers, and truthful evidence requirements for signature,
assignment, deposit, and funding claims.

This roadmap is the durable implementation contract for the Alex-centered Dispositions user
experience. It supplements the broader governance and platform plan in
[`DISPOSITION_SIDEKICK_ROADMAP.md`](./DISPOSITION_SIDEKICK_ROADMAP.md). Where older navigation or
screen descriptions conflict with this document, this document controls the operator experience;
the older roadmap continues to control evidence, permissions, audit, and provider safeguards.

## The Daily Experience

The Dispositions landing page has two primary working modes:

1. **Deals to Market** — every contracted deal Alex can actively market, led by one dominant
   **Start outreach** or **Continue outreach** action.
2. **Investor Relationships** — follow-ups, replies, notes, preferences, and ongoing relationship
   work that is not limited to one active deal.

Replies, offers, deadlines, performance, bulk campaigns, and external distribution remain
available, but they are secondary queues or tools instead of equal-weight starting points.

Opening a deal provides three primary sections:

1. **Outreach Desk** — the default section and the place Alex works the ranked investor queue.
2. **Deal & Packet** — deal facts, uploads, investor packet, evidence classification, and the
   visible readiness checklist.
3. **Offers & Closing** — interest, offers, primary and backup selection, deposits, deadlines, and
   closing protection.

The deal header stays compact and persistent enough to answer: which property, what price, which
deal, who owns it, and where am I in outreach? Readiness warnings are secondary and expandable;
they are never presented as prerequisites to reaching buyers.

## Current Foundation We Are Reusing

The repository already contains much of the hard backend and governance work:

- an executed/Under Contract transaction can automatically create a Disposition case even when
  owner or setup details are incomplete;
- investor packet upload, evidence classification, exact-artifact approval, and replacement;
- owned Buyer Network matching plus DealMachine House buyer discovery and ranked candidates;
- a one-at-a-time browser calling workspace that can draft and send SMS, start a call, record an
  outcome, and advance to another investor;
- buyer profiles, buy boxes, relationship follow-ups, inbox conversations, engagement history,
  offers, primary and backup selection, deadlines, and closing checkpoints;
- permissions, communication consent and suppression, evidence provenance, and audit history.

The main gap is not a missing collection of features. It is the operator experience: those
capabilities are currently split across too many equally prominent tabs, long pages, and readiness
surfaces, so the simple outreach job is hard to recognize and resume.

## Phase 1 — Make The Job Obvious

**Repository status:** Implemented September 1, 2026. Focused TypeScript, Dispositions desk,
readiness, package, execution, responsive-layout, and information-architecture audits pass.
Operator acceptance with a live deal remains the final confirmation of the screen flow.

Goal: make the existing functionality understandable without changing the underlying workflow or
introducing new operational gates.

- Reduce the landing page to **Deals to Market** and **Investor Relationships** as the two primary
  modes.
- Default Dispositions to **Deals to Market**, not a generic multi-queue Today screen.
- Give every active deal a dominant **Start / continue outreach** action that opens the one-to-one
  outreach desk directly.
- Remove the competing “Suggested action,” “Also available now,” and four-button deal launcher
  hierarchy from active-deal cards.
- Keep packet and offer destinations available as quieter secondary links.
- Collapse deal checklist/readiness details and data-health/coverage diagnostics so they remain
  easy to find without controlling the screen.
- Simplify the deal workspace to **Outreach Desk**, **Deal & Packet**, and **Offers & Closing**.
- Make **Outreach Desk** the default deal destination.
- Keep DealMachine discovery, bulk outreach, external distribution, performance, reconciliation,
  and version history available as secondary tools.

Phase 1 is complete when an operator can enter Dispositions, see the deals available to market,
and reach the one-to-one investor queue with one obvious click, while still being able to inspect
or update readiness and packet details without any gate.

## Phase 2 — Redesign The One-To-One Outreach Desk

**Repository status:** Implemented September 1, 2026. The desk now keeps the current investor,
editable channel cadence, result controls, and compact queue in one responsive workbench. Result
selection and queue movement are separate operator decisions. Skip and pause are intentionally
operator-led; Phase 3 now persists them across visits. Phase 4 now completes the editable
one-to-one email step. Operator acceptance with a live deal remains outstanding.

Goal: turn the existing dialer into a focused workbench with three stable areas.

1. **Deal strip** — property, asking price, packet link/status, key disclosures, and quick access to
   deal facts.
2. **Current investor** — name, rank and ranking reasons, contact permission, fit, relationship
   history, prior deal activity, editable SMS, call controls, email, and outcome controls.
3. **Queue** — current position, remaining investors, contacted/interested/skipped counts, and a
   compact preview of who is next.

The default cadence is SMS, then call, then email, but every step can be edited, skipped, repeated,
or completed out of order. Recording a result does not force an immediate advance: Alex chooses
**Save & next**, **Save & stay**, **Schedule follow-up**, **Skip**, or **Pause session**.

## Phase 3 — Durable Sessions And Exact Resume

**Repository status:** Implemented September 1, 2026. Each operator now has one canonical saved
session per deal. The service preserves queue order across ranking refreshes, appends newly found
investors, and restores the current investor, skipped list, pause state, message/result drafts,
channel progress, last outcome, and scheduled follow-up. Session changes are tenant-scoped and
audited. Operator acceptance across logout and a production-equivalent deal remains outstanding.

Goal: let Alex stop and return without reconstructing what happened.

- Persist the current deal, queue/run, investor, queue position, completed channel steps, drafts,
  last outcome, and scheduled follow-up.
- Add explicit **Pause session** and **Resume outreach** actions.
- Resume at the exact investor and unfinished step, even after logout or another task.
- Keep saved drafts until sent, replaced, or intentionally discarded.
- Preserve queue history when buyer ranking is refreshed; do not silently erase completed work.

## Phase 4 — Complete The SMS, Call, Email Cadence

**Repository status:** Implemented September 1, 2026. The outreach desk now loads only authorized
Stonegate senders, restores an editable deal-aware subject and body per investor, optionally inserts
a secure 72-hour preliminary or approved packet link, and sends through the canonical buyer
conversation. Email send state persists with the operator session. The desk surfaces recent buyer
relationship activity—including inbound replies and provider delivery state—from the same timeline
used by Investor Relationships. Drafting remains deterministic and operator-controlled; no AI text
or message is generated or sent automatically. Operator acceptance with a live email provider and
production-equivalent deal remains outstanding.

Goal: add first-class one-to-one email to the existing SMS and calling experience.

- Draft an editable deal-aware SMS for the current investor.
- Call through the browser or use the recorded fallback path.
- Draft an editable one-to-one follow-up email with the approved packet link or attachment.
- Keep AI drafting optional and clearly labeled; Alex owns every message and send.
- Record sends, delivery state, calls, notes, replies, and outcomes in one investor/deal timeline.
- Surface inbound replies in both the active outreach session and Investor Relationships.

## Phase 5 — Pull And Rank Investors In Place

**Repository status:** Implemented September 1, 2026. The Outreach Desk now contains a compact,
collapsible **Build this investor queue** workspace. Alex can rerank the owned network, preview the
exact scope and estimated DealMachine credits before a House search, reuse saved searches, review
staged external candidates, approve or link them into the canonical Buyer Network, reject them,
manually add a relationship, and pin any canonical investor without leaving the active outreach
session. Reranking adopts the latest explainable order while preserving the pinned investor,
per-investor drafts, channel progress, outcomes, skips, and follow-ups. DealMachine results preserve
their external provenance and never trigger outreach automatically. Land uses the asset-aware owned
network matcher and manual additions; the residential DealMachine search remains visibly unavailable
for Land so House assumptions cannot leak into that workflow. Production acceptance with a connected
DealMachine account and production-equivalent House and Land deals remains outstanding.

Goal: make the external-to-owned buyer pool feel like one part of the outreach job.

- Run DealMachine discovery from the Outreach Desk without leaving the deal.
- Show cost/reuse status and discovery scope before running it.
- Combine authorized owned-network buyers and reviewed external candidates into one explainable
  ranked list while preserving source and provenance.
- Let Alex review, approve, rerank, skip, pin, or manually add a buyer.
- Expand asset-aware validation before enabling Land outreach so residential logic is never
  applied to Land.

## Phase 6 — Make Relationship Knowledge Useful During Outreach

Goal: support the second half of Alex's job—knowing investors and staying in touch.

- Show relationship owner, preferred markets/assets, communication style, last touch, reliability,
  proof status, prior offers, purchases, fallout, notes, and promised follow-ups beside the current
  investor.
- Give Investor Relationships a daily queue for replies, due follow-ups, stale relationships,
  missing preferences, and recent activity.
- Allow quick notes, preference updates, next-follow-up scheduling, and buyer-profile access without
  losing the current outreach session.
- Keep one canonical relationship timeline across deals and channels.

## Phase 7 — Carry Interest Through Buyer Selection

Goal: connect outreach to the commercial outcome without forcing Alex into another mental model.

- Convert an outreach result into interested, showing, offer expected, offer received, not now, or
  not a fit.
- Compare offers on price, timing, proof, deposit, certainty, reliability, and execution risk.
- Select primary and backup buyers, preserve backups, and reopen the queue after fallout.
- Track deposit, assignment/double-close evidence, buyer deadlines, and closing checkpoints.
- Finish asset-appropriate offer and closing parity before treating Land as a complete outreach
  lane.

## Later — Buyer-Facing Deal Page

After the internal workflow is proven, provide an approved, expiring buyer-facing deal page that
can show the exact public packet, photos, disclosures, price, access/request-interest controls, and
tracked responses. It must use the same approved evidence and never expose private economics or
internal notes.

## End-To-End Acceptance Checklist

The Alex-centered workflow is complete when all of the following can be demonstrated on a real or
production-equivalent deal:

1. A newly Under Contract deal appears in **Deals to Market** without manual case creation.
2. Alex can start outreach even when readiness items remain incomplete.
3. Alex can upload, replace, or inspect the investor packet without leaving the deal workspace.
4. Alex can pull authorized DealMachine candidates from the deal.
5. The system presents one explainable most-likely-to-least-likely investor queue.
6. Alex can review, edit, and send the drafted SMS to an eligible investor.
7. Alex can call that investor from the same workspace.
8. Alex can record the call result without being forced away from the investor.
9. Alex can review, edit, and send the follow-up email.
10. Alex can advance to the next investor and repeat the cadence.
11. Alex can pause and later resume at the exact investor and unfinished step.
12. Replies, prior conversations, notes, preferences, and follow-ups remain visible in the
    relationship history.
13. Alex can record interest, showing activity, and an offer from the outreach context.
14. Alex can select a primary/backup buyer and reopen outreach cleanly if that buyer falls out.

## Implementation Discipline

- Build these phases in order unless a discovered technical dependency requires a documented
  adjustment.
- Update this file when a phase changes scope or is completed.
- Do not describe a planned phase as live before its focused tests and operator acceptance pass.
- Prefer reusing the existing canonical records and services over parallel task, campaign, or
  relationship stores.
- Preserve the operator-led, no-workflow-gates decision in every phase.
