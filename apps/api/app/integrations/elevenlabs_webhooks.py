from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any


class ElevenLabsWebhookError(ValueError):
    pass


def verify_elevenlabs_webhook(
    raw_body: bytes,
    signature_header: str | None,
    secret: str | None,
    *,
    now: int | None = None,
    tolerance_seconds: int = 30 * 60,
) -> dict[str, Any]:
    """Verify ElevenLabs' t=<unix>,v0=<hex> HMAC signature and decode the event."""

    if not signature_header:
        raise ElevenLabsWebhookError("Missing ElevenLabs signature header.")
    if not secret or not secret.strip():
        raise ElevenLabsWebhookError("ElevenLabs webhook secret is not configured.")
    timestamp: str | None = None
    supplied_signature: str | None = None
    for part in signature_header.split(","):
        key, separator, value = part.strip().partition("=")
        if not separator:
            continue
        if key == "t":
            timestamp = value
        elif key == "v0":
            supplied_signature = value.lower()
    if not timestamp or not supplied_signature:
        raise ElevenLabsWebhookError("ElevenLabs signature has an unsupported format.")
    try:
        timestamp_value = int(timestamp)
    except ValueError as exc:
        raise ElevenLabsWebhookError("ElevenLabs signature timestamp is invalid.") from exc
    current_time = int(time.time()) if now is None else now
    if timestamp_value < current_time - tolerance_seconds:
        raise ElevenLabsWebhookError("ElevenLabs signature timestamp is too old.")
    if timestamp_value > current_time + 5 * 60:
        raise ElevenLabsWebhookError("ElevenLabs signature timestamp is in the future.")
    signed_payload = timestamp.encode("utf-8") + b"." + raw_body
    expected_signature = hmac.new(
        secret.strip().encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise ElevenLabsWebhookError("ElevenLabs signature is invalid.")
    try:
        event = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ElevenLabsWebhookError("ElevenLabs webhook body is invalid JSON.") from exc
    if not isinstance(event, dict):
        raise ElevenLabsWebhookError("ElevenLabs webhook body must be an object.")
    return event
