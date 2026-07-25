# Phase F3 Compliance And Operating Policy

Last updated: July 24, 2026

## Purpose

F3 adds a versioned operating-policy and evidence layer to Stonegate's existing consent,
suppression, prospecting, communications, recording, and audit controls. It does not replace those
systems and does not claim that Stonegate has completed external legal or provider acceptance.

## Implemented

- Owner-only `/os/compliance` workspace.
- Six standard Georgia policy drafts covering DNC screening, company suppression, contact hours
  and identity, consent and outreach, recording and retention, and Georgia legal scope.
- External legal-review evidence and review-due dates before owner activation.
- Versioned policy status with prior active versions superseded rather than overwritten.
- DNC screening sources with owner approval, covered area codes, maximum 31-day refresh interval,
  refresh dates, next due dates, and retained evidence references.
- Staff training assignments, employee attestations, manager decisions, scores, and audit history.
- Compliance incident register for complaints, wrong numbers, Do Not Contact requests, recording
  objections, policy exceptions, and provider failures.
- Repeatable control runs for policy readiness, DNC freshness, stale eligible prospects, unsafe
  calling batches, recording policy, and high-severity incidents.
- Prospect call eligibility rechecked when a batch is created and when a caller starts an attempt.
- Email delivery blocked without recorded email permission or when email/all suppression is active.
- Recording enabled only when provider configuration is complete and a current, legally reviewed
  recording policy is active.
- Staff compliance assignments and submission controls in `/os/my-setup`.

## External Acceptance Still Required

The following cannot be completed by application code:

1. Stonegate must obtain National Do Not Call Registry access or approve a qualified screening
   provider and record the source in `/os/compliance`.
2. The source must be synchronized on the approved schedule, never longer than 31 days, with an
   evidence reference retained for each refresh.
3. Qualified counsel must review Stonegate's actual Georgia calling, SMS, email, recording,
   contract, and disclosure practices. The owner records the reviewer and evidence, then activates
   each policy.
4. Each outbound employee or contractor must complete assigned training and receive manager
   approval.
5. Stonegate must run controlled blocked-case tests before broad outreach or recording activation.

Policy records are operational evidence, not legal advice. Enter real review evidence only after
the review has occurred.

## Recommended Acceptance Sequence

1. Install the standard policy set in **Compliance > Policies**.
2. Select and approve the DNC source.
3. Record current DNC refresh evidence.
4. Complete external legal review and record it on each policy.
5. Activate each reviewed policy as Owner.
6. Assign role-appropriate training and approve staff submissions.
7. Run the control suite.
8. Test a DNC match, stale DNC result, company suppression, SMS opt-out, email suppression, and
   recording-disabled call.
9. Record and resolve any exception in the incident register.

## Primary References

- FTC, *Complying with the Telemarketing Sales Rule*:
  https://www.ftc.gov/business-guidance/resources/complying-telemarketing-sales-rule
- Twilio, *Recording API and legal considerations*:
  https://www.twilio.com/docs/voice/api/recording
- Twilio, *Legal considerations with recording voice and video communications*:
  https://help.twilio.com/articles/360011522553-Legal-Considerations-with-Recording-Voice-and-Video-Communications
- Twilio, *Voice and SIP country-specific terms*:
  https://www.twilio.com/en-us/legal/service-country-specific-terms/voice-sip

