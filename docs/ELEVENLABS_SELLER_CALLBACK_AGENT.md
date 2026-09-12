# ElevenLabs Seller Callback Agent

## Outcome

Caroline answers Stonegate's `+1 (470) 888-7952` seller-callback line through ElevenLabs.
The public human line remains `+1 (678) 541-7725` and is Caroline's only live-transfer
destination. ElevenLabs calls use the same durable CRM records, lead creation rules, team alerts,
and `Inbox -> AI seller calls` review workspace as the prior OpenAI Realtime implementation.

The provider switch is deliberately separate from deployment. Deploy and configure the API first;
move the Twilio number only after both ElevenLabs webhooks and the CRM tools pass their tests.

## Render configuration

Set these variables on the API service. Use generated secrets with at least 32 random characters for
the two secret values.

```text
SELLER_CALLBACK_AGENT_PROVIDER=elevenlabs
ELEVENLABS_AGENT_ENABLED=true
ELEVENLABS_AGENT_ID=agent_0101m2b1nejvfdz8ev4pznm59pwz
ELEVENLABS_WEBHOOK_SECRET=<secret issued for the ElevenLabs post-call webhook>
ELEVENLABS_TOOL_SECRET=<a separate random secret created by Stonegate>
ELEVENLABS_LINE_NUMBER=+14708887952
ELEVENLABS_TRANSFER_NUMBER=+16785417725
ELEVENLABS_WEBHOOK_MAX_BYTES=2000000
```

Do not remove the existing OpenAI variables. They preserve the rollback path.

## ElevenLabs webhooks

### Conversation initiation

In Caroline's agent Security settings, enable fetching conversation initiation data for inbound
Twilio calls.

- URL: `https://api.stonegatehb.com/api/v1/webhooks/elevenlabs/conversation-initiation`
- Method: `POST`
- Header: `X-Stonegate-Agent-Secret`
- Header value: the ElevenLabs workspace secret containing the exact
  `ELEVENLABS_TOOL_SECRET` value
- Do not enable prompt, first-message, language, or voice overrides.

This hook creates the CRM call record before Caroline begins speaking. Its response does not alter
the published agent prompt or voice.

### Post-call transcription

In ElevenLabs workspace Developers -> Webhooks, create or update the post-call webhook.

- URL: `https://api.stonegatehb.com/api/v1/webhooks/elevenlabs/post-call`
- Event: `post_call_transcription`
- Do not enable `post_call_audio`; Stonegate keeps transcript and analysis metadata without copying
  a large base64 audio file into the CRM database.
- Copy the webhook's signing secret into Render as `ELEVENLABS_WEBHOOK_SECRET`.

Stonegate verifies the `ElevenLabs-Signature` HMAC, enforces a timestamp window, caps request size,
and accepts duplicate delivery without creating duplicate calls.

## Shared parameters for every CRM webhook tool

Create a workspace secret whose value is the Render `ELEVENLABS_TOOL_SECRET`. Every tool below is a
`POST` request and uses this header:

```text
X-Stonegate-Agent-Secret: <workspace secret>
```

Add these body parameters to every tool using the indicated system dynamic variable rather than an
LLM-generated value:

| Identifier | Value source | Value |
| --- | --- | --- |
| `conversation_id` | Dynamic variable | `system__conversation_id` |
| `caller_id` | Dynamic variable | `system__caller_id` |
| `called_number` | Dynamic variable | `system__called_number` |
| `call_sid` | Dynamic variable | `system__call_sid` |

Keep tool-response timeout at 10 seconds. The endpoints are idempotent, so a retried identical tool
call returns the prior result instead of repeating the CRM action.

## CRM webhook tools

### `lookup_callback_context`

URL: `https://api.stonegatehb.com/api/v1/webhooks/elevenlabs/tools/lookup_callback_context`

Use only after the caller supplies their name or property address. Never reveal a phone-number match
until this tool reports `verified: true`.

| Parameter | Type | Required | Meaning |
| --- | --- | --- | --- |
| `caller_name` | string | no | Name stated by the caller |
| `property_address` | string | no | Address stated by the caller |

### `capture_seller_interest`

URL: `https://api.stonegatehb.com/api/v1/webhooks/elevenlabs/tools/capture_seller_interest`

Call immediately after the owner expresses affirmative or conditional interest, before continuing
the detailed intake. This preserves a useful lead even if the call drops.

| Parameter | Type | Required | Meaning |
| --- | --- | --- | --- |
| `interest_level` | string | yes | Exactly `open_to_offer`, `maybe`, or `depends_on_numbers` |
| `interest_basis` | string | yes | What the caller actually said that showed interest |
| `seller_name` | string | no | Caller-supplied name |
| `property_type` | string | no | Caller-supplied property type |
| `city` | string | no | Property city |
| `state` | string | no | Two-letter property state |
| `owner_confirmed` | boolean | yes | Whether the caller confirmed ownership |

### `save_seller_details`

URL: `https://api.stonegatehb.com/api/v1/webhooks/elevenlabs/tools/save_seller_details`

Use once the required facts have been stated by the caller. Ask one question at a time; do not delay
the early `capture_seller_interest` call while trying to complete this larger payload.

Required parameters: `seller_name`, `street_address`, `city`, `state`, `owner_confirmed`, and
`seller_interested`. Optional string parameters: `postal_code`, `property_type`, `occupancy_status`,
`property_condition`, `desired_timeline`, `motivation`, `asking_price`, and `notes`.

### `schedule_human_callback`

URL: `https://api.stonegatehb.com/api/v1/webhooks/elevenlabs/tools/schedule_human_callback`

| Parameter | Type | Required | Meaning |
| --- | --- | --- | --- |
| `callback_at` | string | yes | Caller-confirmed future time in ISO 8601 with timezone |
| `caller_confirmed` | boolean | yes | Must be true only after the caller agrees |
| `reason` | string | no | Short caller-supplied reason or context |

This creates one internal calendar appointment and one dated follow-up. It will not create vague or
automatic overdue work.

### `record_call_outcome`

URL: `https://api.stonegatehb.com/api/v1/webhooks/elevenlabs/tools/record_call_outcome`

| Parameter | Type | Required | Meaning |
| --- | --- | --- | --- |
| `outcome` | string | yes | Exactly `interested`, `callback_scheduled`, `transferred`, `not_interested`, `wrong_number`, `unrelated`, or `do_not_contact` |
| `notes` | string | yes | Concise factual outcome notes |
| `do_not_contact_confirmed` | boolean | no | Must be true for `do_not_contact` |

## ElevenLabs system tools

Add these as ElevenLabs system tools, not Stonegate webhook tools:

- End call: allow Caroline to end a naturally completed call.
- Transfer to number: destination `+16785417725`. Prefer conference transfer if the plan supports
  it; otherwise use blind transfer. The prompt must get clear caller consent before transferring.
- Language detection: enable if Caroline should continue Spanish conversations.

Never configure any other transfer destination.

## Cutover and rollback

1. Deploy the API and web changes without changing the Twilio number.
2. Set the Render variables and wait for the API deployment to become healthy.
3. Configure and test the initiation webhook, post-call webhook, and five CRM tools in ElevenLabs.
4. Confirm Communications settings reports Caroline ready.
5. Import or attach only `+1 (470) 888-7952` to Caroline using ElevenLabs' native Twilio
   integration. If the number is still attached to the OpenAI SIP trunk, detach it from that trunk
   immediately before the ElevenLabs import.
6. Place controlled calls covering hang-up during greeting, interested seller, complete intake,
   callback booking, do-not-contact, Spanish, and human transfer.
7. Confirm each call appears in the review workspace and that qualified calls create only one lead.

To roll back, return the Twilio number to the existing OpenAI SIP trunk and set
`SELLER_CALLBACK_AGENT_PROVIDER=openai_realtime`. Leave the ElevenLabs webhook history in place.
