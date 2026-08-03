import json

import httpx
import pytest

from app.integrations.openai_client import OpenAIClientError, OpenAIResponsesClient

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


def test_structured_response_wraps_malformed_success_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(url: str, **_kwargs: object) -> httpx.Response:
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            content=b"not-json",
        )

    monkeypatch.setattr("app.integrations.openai_client.httpx.post", fake_post)
    client = OpenAIResponsesClient(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        timeout_seconds=30,
    )

    with pytest.raises(OpenAIClientError, match="invalid JSON"):
        client.create_structured_response(
            model="gpt-5.6-sol",
            system_prompt="test",
            user_prompt="{}",
            schema_name="stonegate_test",
            json_schema=STRICT_SCHEMA,
        )


def test_grounded_structured_response_configures_bounded_web_search(
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
                "output": [
                    {
                        "type": "web_search_call",
                        "action": {
                            "type": "search",
                            "sources": [
                                {
                                    "url": "https://assessor.example.gov/property/134",
                                    "title": "County assessor",
                                }
                            ],
                        },
                    },
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps({"summary": "Verified.", "risks": []}),
                                "annotations": [],
                            }
                        ],
                    },
                ],
                "usage": {"input_tokens": 20, "output_tokens": 10},
            },
        )

    monkeypatch.setattr("app.integrations.openai_client.httpx.post", fake_post)
    client = OpenAIResponsesClient(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        timeout_seconds=30,
    )
    result, usage, sources = client.create_grounded_structured_response(
        model="gpt-5.6-sol",
        system_prompt="Use public records.",
        user_prompt="Research the subject.",
        schema_name="stonegate_grounded_test",
        json_schema=STRICT_SCHEMA,
        user_location={
            "country": "US",
            "city": "Canton",
            "region": "GA",
        },
        blocked_domains=["reddit.com"],
        max_tool_calls=2,
        search_context_size="medium",
    )

    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["tools"] == [
        {
            "type": "web_search",
            "search_context_size": "medium",
            "external_web_access": True,
            "user_location": {
                "type": "approximate",
                "country": "US",
                "city": "Canton",
                "region": "GA",
            },
            "filters": {"blocked_domains": ["reddit.com"]},
        }
    ]
    assert payload["tool_choice"] == "required"
    assert payload["max_tool_calls"] == 2
    assert payload["include"] == ["web_search_call.action.sources"]
    assert result == {"summary": "Verified.", "risks": []}
    assert usage["total_tokens"] == 30
    assert sources == [
        {
            "url": "https://assessor.example.gov/property/134",
            "title": "County assessor",
        }
    ]
