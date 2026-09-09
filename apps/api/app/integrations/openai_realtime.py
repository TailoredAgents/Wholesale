from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import aiohttp
from openai import InvalidWebhookSignatureError, OpenAI

from app.core.config import Settings


class OpenAIRealtimeError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class OpenAIRealtimeSignatureError(OpenAIRealtimeError):
    pass


def unwrap_openai_webhook(
    body: bytes,
    headers: Mapping[str, str],
    settings: Settings,
) -> dict[str, Any]:
    if not settings.openai_webhook_secret:
        raise OpenAIRealtimeError("OpenAI webhook verification is not configured.")
    try:
        with OpenAI(api_key=settings.openai_api_key or "not-configured") as client:
            event = client.webhooks.unwrap(
                body,
                dict(headers),
                secret=settings.openai_webhook_secret,
            )
    except InvalidWebhookSignatureError as exc:
        raise OpenAIRealtimeSignatureError("Invalid OpenAI webhook signature.") from exc
    payload = event.model_dump(mode="json")
    if not isinstance(payload, dict):
        raise OpenAIRealtimeError("OpenAI webhook payload was not an object.")
    return payload


class OpenAIRealtimeCallClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise OpenAIRealtimeError("OPENAI_API_KEY is required for Realtime calls.")
        self.settings = settings
        self.headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }

    async def accept(self, call_id: str, session: dict[str, Any]) -> None:
        await self._post(f"/realtime/calls/{call_id}/accept", json_body=session)

    async def reject(self, call_id: str, *, status_code: int = 480) -> None:
        await self._post(
            f"/realtime/calls/{call_id}/reject",
            json_body={"status_code": status_code},
        )

    async def refer(self, call_id: str, target_number: str) -> None:
        await self._post(
            f"/realtime/calls/{call_id}/refer",
            json_body={"target_uri": f"tel:{target_number}"},
        )

    async def hangup(self, call_id: str) -> None:
        await self._post(f"/realtime/calls/{call_id}/hangup")

    async def _post(
        self,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> None:
        url = f"{self.settings.openai_base_url.rstrip('/')}{path}"
        timeout = aiohttp.ClientTimeout(total=self.settings.openai_request_timeout_seconds)
        try:
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.post(url, headers=self.headers, json=json_body) as response,
            ):
                if response.status >= 400:
                    detail = (await response.text())[:1000]
                    raise OpenAIRealtimeError(
                        f"OpenAI Realtime returned {response.status}: {detail or 'No detail'}",
                        status_code=response.status,
                    )
        except OpenAIRealtimeError:
            raise
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise OpenAIRealtimeError("OpenAI Realtime request failed.") from exc

    def websocket_url(self, call_id: str) -> str:
        parsed = urlsplit(self.settings.openai_base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        path = f"{parsed.path.rstrip('/')}/realtime"
        return urlunsplit((scheme, parsed.netloc, path, urlencode({"call_id": call_id}), ""))

    @asynccontextmanager
    async def monitor(self, call_id: str) -> AsyncIterator[aiohttp.ClientWebSocketResponse]:
        timeout = aiohttp.ClientTimeout(
            total=self.settings.openai_realtime_max_call_seconds + 30,
            sock_read=self.settings.openai_realtime_max_call_seconds + 30,
        )
        try:
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.ws_connect(
                    self.websocket_url(call_id),
                    headers={"Authorization": self.headers["Authorization"]},
                    heartbeat=20,
                ) as websocket,
            ):
                yield websocket
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise OpenAIRealtimeError("OpenAI Realtime monitoring failed.") from exc


def encode_realtime_event(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
