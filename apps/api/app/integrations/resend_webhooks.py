from typing import Any

from svix.webhooks import Webhook, WebhookVerificationError


class ResendWebhookVerificationError(ValueError):
    pass


def verify_resend_webhook(
    *,
    payload: bytes,
    event_id: str | None,
    timestamp: str | None,
    signature: str | None,
    webhook_secret: str | None,
) -> dict[str, Any]:
    if not webhook_secret:
        raise ResendWebhookVerificationError(
            "Resend webhook signature validation is not configured."
        )
    if not event_id or not timestamp or not signature:
        raise ResendWebhookVerificationError("Missing Resend webhook signature headers.")
    try:
        verified = Webhook(webhook_secret).verify(
            payload,
            {
                "svix-id": event_id,
                "svix-timestamp": timestamp,
                "svix-signature": signature,
            },
        )
    except (UnicodeDecodeError, WebhookVerificationError, ValueError) as exc:
        raise ResendWebhookVerificationError(
            "Invalid Resend webhook signature."
        ) from exc
    if not isinstance(verified, dict):
        raise ResendWebhookVerificationError("Invalid Resend webhook payload.")
    return verified
