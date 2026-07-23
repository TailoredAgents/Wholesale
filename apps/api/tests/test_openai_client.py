import json

import httpx
import pytest

from app.integrations.openai_client import OpenAIResponsesClient

STRICT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "risks"],
}


def test_structured_response_uses_stateless_strict_responses_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        captured["url"] = url
        captured.update(kwargs)
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "output_text": json.dumps({"summary": "Review needed.", "risks": []}),
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            },
        )

    monkeypatch.setattr("app.integrations.openai_client.httpx.post", fake_post)
    client = OpenAIResponsesClient(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        timeout_seconds=30,
    )
    result, usage = client.create_structured_response(
        model="gpt-5.6-sol",
        system_prompt="Use only supplied facts.",
        user_prompt="{}",
        schema_name="stonegate_test",
        json_schema=STRICT_SCHEMA,
        safety_identifier="a" * 64,
        prompt_cache_key="stonegate:test:v1",
    )

    payload = captured["json"]
    assert isinstance(payload, dict)
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert payload["store"] is False
    assert payload["safety_identifier"] == "a" * 64
    assert payload["prompt_cache_key"] == "stonegate:test:v1"
    assert payload["text"]["format"]["strict"] is True
    assert payload["text"]["format"]["schema"] == STRICT_SCHEMA
    assert result == {"summary": "Review needed.", "risks": []}
    assert usage["total_tokens"] == 15


def test_structured_response_rejects_non_strict_schema_before_network() -> None:
    client = OpenAIResponsesClient(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        timeout_seconds=30,
    )
    with pytest.raises(ValueError, match="additionalProperties"):
        client.create_structured_response(
            model="gpt-5.6-sol",
            system_prompt="test",
            user_prompt="{}",
            schema_name="invalid_schema",
            json_schema={
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        )
