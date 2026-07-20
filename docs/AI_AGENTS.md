# AI Agents

Use specialized agents with narrow tools and human approval boundaries.

## Current Foundation

- Agent definitions, prompt versions, tool policies, runs, tool-call logs, approvals, and cost
  telemetry are implemented.
- Lead intake summary execution is available.
- Call transcription and evidence-backed note extraction are implemented.
- Call-derived CRM updates and tasks require human review.
- External autonomy remains disabled.

## Planned Agent Order

1. Seller intake and qualification-gap agent.
2. Speed-to-lead and missed-reply monitor.
3. Follow-up drafting agent.
4. Acquisition copilot.
5. Underwriting research assistant.
6. Compliance preflight agent.
7. Disposition package assistant.
8. Finance reconciliation checker.
9. Contract assistant after document and approval infrastructure exists.

## Rules

- AI cannot make binding offers.
- AI cannot send contracts without approval.
- AI cannot give legal, tax, foreclosure, probate, bankruptcy, title, or closing advice.
- AI cannot receive arbitrary SQL, shell access, payment access, user administration, or raw provider credentials.
- Conflicts with human-confirmed facts create review items.
- AI cannot bypass deterministic consent, suppression, offer, contract, buyer, or finance approval.

## Call Intelligence

The call-intelligence agent transcribes recorded calls, separates speakers, extracts structured
seller facts, recommends the next action, and links extracted facts to transcript timestamps.
Every result requires human review before it can update lead fields or create a follow-up task.

Review telemetry compares the original AI draft with the reviewer-approved notes. Stonegate tracks:

- Model confidence.
- Field agreement after human edits.
- Evidence coverage.
- Approvals, rejections, pending reviews, and failures.
- High-correction calls.
- Input/output usage and sub-cent estimated OpenAI cost.

The control center keeps human approval required until at least 50 calls have been reviewed,
average field agreement and evidence coverage are both at least 90%, reviewer rejection is no more
than 5%, and processing failure is no more than 2%. Passing these checks only marks the agent as
eligible for a controlled low-risk pilot. It does not enable autonomous CRM updates, seller
messages, offers, contracts, or legal/financial actions.

Pricing estimates are versioned and stored with each run. `OPENAI_PRICING_OVERRIDES_JSON` can
replace a model's per-million-token input/output rates without a code release.
