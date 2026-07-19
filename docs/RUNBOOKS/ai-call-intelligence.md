# AI Call Intelligence Operations

## Default State

Call intelligence is an assistant, not an autonomous operator. It may transcribe, extract facts,
draft notes, and recommend a task. A person must review the recording and draft before Stonegate
updates CRM fields or creates the task.

## Review Workflow

1. Open **OS > Inbox** and select a call marked **Needs review**.
2. Play the recording and inspect the speaker-separated transcript.
3. Correct any unsupported or inaccurate fields.
4. Select only CRM fields that should be filled when the current lead field is empty.
5. Approve or reject the notes and record a decision reason.

Stonegate retains the original draft, final reviewed values, changed field names, reviewer,
decision, confidence, evidence coverage, and audit event.

## Quality Gate

The AI control center reports:

| Measure | Pilot threshold |
| --- | --- |
| Reviewed calls | At least 50 |
| Average field agreement | At least 90% |
| Average evidence coverage | At least 90% |
| Reviewer rejection rate | No more than 5% |
| Processing failure rate | No more than 2% |

Meeting every threshold changes the dashboard status to **Eligible for low-risk pilot**. It does
not change agent permissions or bypass approvals.

## Cost Tracking

Each call-intelligence run combines transcription and structured-note usage. Stonegate stores
input tokens, output tokens, pricing components, pricing version, and estimated cost in
micro-dollars so calls costing less than one cent are not rounded away.

Use this optional API and worker variable to override pricing:

```text
OPENAI_PRICING_OVERRIDES_JSON={"model-id":{"input_usd_per_million":2.5,"output_usd_per_million":15}}
```

The application estimate is for operations and trend monitoring. Reconcile actual charges against
the OpenAI billing dashboard.

## Actions That Remain Approval-Gated

- CRM field changes.
- Follow-up tasks.
- Seller SMS or email.
- Offer recommendations or price communication.
- Contracts and transaction commitments.
- Compliance, legal, title, tax, or financial decisions.
