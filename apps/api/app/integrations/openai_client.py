from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class OpenAITextResponse:
    text: str
    total_tokens: int | None


class OpenAIClientError(RuntimeError):
    pass


class OpenAIResponsesClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def create_text_response(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        reasoning_effort: str = "medium",
        enable_web_search: bool = False,
        max_output_tokens: int = 900,
    ) -> OpenAITextResponse:
        request_payload: dict[str, Any] = {
            "model": model,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": system_prompt,
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": user_prompt,
                        }
                    ],
                },
            ],
            "reasoning": {"effort": reasoning_effort},
            "max_output_tokens": max_output_tokens,
        }
        if enable_web_search:
            request_payload["tools"] = [{"type": "web_search"}]

        try:
            response = httpx.post(
                f"{self.base_url}/responses",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=request_payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = parse_openai_error(exc.response)
            raise OpenAIClientError(detail) from exc
        except httpx.HTTPError as exc:
            raise OpenAIClientError("OpenAI request failed.") from exc

        payload = response.json()
        return OpenAITextResponse(
            text=extract_response_text(payload),
            total_tokens=extract_total_tokens(payload),
        )


def parse_openai_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"OpenAI returned HTTP {response.status_code}."
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message:
            return message[:2000]
    return f"OpenAI returned HTTP {response.status_code}."


def extract_total_tokens(payload: dict[str, Any]) -> int | None:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None
    total = usage.get("total_tokens")
    return int(total) if isinstance(total, int | float) else None


def extract_response_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    text_parts: list[str] = []
    output = payload.get("output")
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())
    return "\n\n".join(text_parts)
