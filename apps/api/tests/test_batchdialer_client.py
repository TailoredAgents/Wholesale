from datetime import date

import httpx
import pytest

from app.core.config import Settings
from app.integrations.batchdialer_client import (
    BatchDialerAuthenticationError,
    BatchDialerClient,
    BatchDialerContractError,
)


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "BATCHDIALER_API_KEY": "test-key-that-is-long-enough",
        "BATCHDIALER_HTTP_MAX_ATTEMPTS": 1,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def test_client_uses_raw_api_key_and_opaque_cursor() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"items": [], "nextPage": "another-cursor"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        page = BatchDialerClient(settings(), client=client).get_cdr_page(
            call_date=date(2026, 8, 18),
            page_length=100,
            next_page="opaque+/=cursor",
        )

    assert page.items == ()
    assert page.next_page == "another-cursor"
    assert requests[0].url.host == "app.batchdialer.com"
    assert requests[0].headers["X-ApiKey"] == "test-key-that-is-long-enough"
    assert requests[0].url.params["next_page"] == "opaque+/=cursor"
    assert requests[0].url.params["callDate"] == "2026-08-18T00:00:00-04:00"
    assert "authorization" not in requests[0].headers


def test_client_rejects_auth_and_redirects_without_leaking_key() -> None:
    for response in (
        httpx.Response(401, json={"message": "secret echoed"}),
        httpx.Response(302, headers={"Location": "https://evil.example/key"}),
    ):
        transport = httpx.MockTransport(lambda _request, current=response: current)
        with httpx.Client(transport=transport) as client:
            provider = BatchDialerClient(settings(), client=client)
            expected = (
                BatchDialerAuthenticationError
                if response.status_code == 401
                else BatchDialerContractError
            )
            with pytest.raises(expected) as error:
                provider.get_campaigns()
            assert "test-key" not in str(error.value)


def test_client_stops_after_bounded_retries_and_honors_retry_after() -> None:
    sleeps: list[float] = []
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200, json=[])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        campaigns = BatchDialerClient(
            settings(BATCHDIALER_HTTP_MAX_ATTEMPTS=2),
            client=client,
            sleeper=sleeps.append,
        ).get_campaigns()

    assert campaigns == ()
    assert sleeps == [3.0]


def test_client_rejects_oversized_and_invalid_shapes() -> None:
    oversized = httpx.Response(
        200,
        headers={"Content-Length": "3000000"},
        content=b"{}",
    )
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _request: oversized)) as client,
        pytest.raises(BatchDialerContractError, match="too large"),
    ):
        BatchDialerClient(settings(), client=client).get_campaigns()

    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json={"items": {}})
            )
        ) as client,
        pytest.raises(BatchDialerContractError, match="invalid shape"),
    ):
        BatchDialerClient(settings(), client=client).get_cdr_page(
            call_date=date(2026, 8, 18)
        )
