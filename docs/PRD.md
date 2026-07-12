# PRD

Build a local-first operating system for a Georgia real-estate wholesaling company. The product connects seller lead capture, CRM, communications, underwriting, offer approval, contracts, transaction coordination, buyer disposition, compensation, attribution, reporting, and controlled AI automation.

## Current State

- The repository now contains a local monorepo foundation.
- No legacy application code existed before this scaffold.
- PostgreSQL is the source of truth.
- AI, transcripts, provider payloads, and vector search are supporting records only.

## MVP

1. Capture seller leads with consent and attribution.
2. Create contact, property, and lead records.
3. Work seller leads through a pipeline.
4. Record communications and follow-up tasks.
5. Underwrite property with comps, ARV, repairs, and offer scenarios.
6. Require human approval for material decisions.
7. Track buyers, transactions, closing revenue, and compensation.
8. Report advertising spend as a percentage of collected revenue.

## Blocking Decisions

- Initial company/organization name.
- Object storage provider.
- Render staging resource configuration.

Resolved:

- Authentication provider: Clerk.
- GitHub timing: after staff lead editing and speed-to-lead workflow.
- Render staging timing: soon after GitHub push.
