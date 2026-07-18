import json
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class OpenAITextResponse:
    text: str
    total_tokens: int | None


@dataclass(frozen=True)
class OpenAIAudioTranscript:
    text: str
    language: str | None
    segments: list[dict[str, Any]]
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

    def create_structured_response(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, Any],
        reasoning_effort: str = "medium",
        max_output_tokens: int = 1800,
    ) -> tuple[dict[str, Any], int | None]:
        request_payload: dict[str, Any] = {
            "model": model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "reasoning": {"effort": reasoning_effort},
            "max_output_tokens": max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": json_schema,
                }
            },
        }
        payload = self._post_json("/responses", request_payload)
        raw_text = extract_response_text(payload)
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise OpenAIClientError("OpenAI returned invalid structured call notes.") from exc
        if not isinstance(parsed, dict):
            raise OpenAIClientError("OpenAI returned an invalid call-notes object.")
        return parsed, extract_total_tokens(payload)

    def create_audio_transcription(
        self,
        *,
        model: str,
        audio: bytes,
        filename: str = "stonegate-call.mp3",
        media_type: str = "audio/mpeg",
    ) -> OpenAIAudioTranscript:
        try:
            response = httpx.post(
                f"{self.base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                data={
                    "model": model,
                    "response_format": "diarized_json",
                    "chunking_strategy": "auto",
                },
                files={"file": (filename, audio, media_type)},
                timeout=max(self.timeout_seconds, 120),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = parse_openai_error(exc.response)
            raise OpenAIClientError(detail) from exc
        except httpx.HTTPError as exc:
            raise OpenAIClientError("OpenAI transcription request failed.") from exc

        payload = response.json()
        text = payload.get("text")
        raw_segments = payload.get("segments")
        segments = [
            segment
            for segment in raw_segments
            if isinstance(segment, dict)
        ] if isinstance(raw_segments, list) else []
        language = payload.get("language")
        return OpenAIAudioTranscript(
            text=text.strip() if isinstance(text, str) else "",
            language=language if isinstance(language, str) else None,
            segments=segments,
            total_tokens=extract_total_tokens(payload),
        )

    def _post_json(self, path: str, request_payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{self.base_url}{path}",
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
        if not isinstance(payload, dict):
            raise OpenAIClientError("OpenAI returned an invalid response.")
        return payload


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
