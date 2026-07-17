# Integrations

Wrap all third-party services behind adapters.

## Initial Interfaces

- OpenAI.
- Twilio.
- Property data provider.
- Address validation/geocoding.
- Mapping.
- E-signature provider.
- Google advertising.
- Meta conversions.
- Email provider.
- Calendar provider.
- Object storage.
- Error monitoring.

## Controls

- Validate webhooks.
- Store raw events.
- Store external IDs.
- Use idempotency keys.
- Handle rate limits and retries.
- Track sync state.
- Provide test mode.

## Twilio Messaging

Phase 3 implements SMS through a Twilio Messaging Service. The adapter sends from the API only;
browser code never receives Twilio credentials. Incoming-message and delivery-status endpoints
validate Twilio signatures, preserve provider event identifiers for idempotency, and update the
shared conversation timeline.

Outbound sends must pass the communication compliance service. It checks the recipient number,
consent history, active suppression records, configured contact hours, sender permissions, and
provider readiness before calling Twilio. STOP and START events update both the suppression record
and append-only consent history.

The integration remains disabled in deployment configuration until credentials are entered and
the activation checklist is complete. See
[Twilio SMS Setup](./RUNBOOKS/twilio-sms-setup.md).
