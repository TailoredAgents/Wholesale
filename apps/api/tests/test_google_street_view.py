import httpx
import pytest

from app.integrations.google_street_view import (
    GoogleStreetViewClient,
    GoogleStreetViewError,
)


def test_street_view_metadata_and_image_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[tuple[str, dict[str, object]]] = []

    def fake_get(
        url: str,
        *,
        params: dict[str, object],
        timeout: float,
    ) -> httpx.Response:
        requests.append((url, params))
        assert timeout == 20
        request = httpx.Request("GET", url)
        if url.endswith("/metadata"):
            return httpx.Response(
                200,
                request=request,
                json={
                    "status": "OK",
                    "pano_id": "test-panorama",
                    "date": "2026-06",
                    "location": {"lat": 33.75, "lng": -84.39},
                    "copyright": "Google",
                },
            )
        return httpx.Response(
            200,
            request=request,
            content=b"jpeg-bytes",
            headers={"Content-Type": "image/jpeg; charset=binary"},
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    client = GoogleStreetViewClient(api_key="private-test-key")

    metadata = client.get_metadata(location="123 Peachtree Street, Atlanta, GA")
    image, content_type = client.get_image(panorama_id=metadata.panorama_id or "")

    assert metadata.available is True
    assert metadata.panorama_id == "test-panorama"
    assert metadata.latitude == 33.75
    assert image == b"jpeg-bytes"
    assert content_type == "image/jpeg"
    assert requests[0][1]["location"] == "123 Peachtree Street, Atlanta, GA"
    assert requests[1][1]["pano"] == "test-panorama"
    assert requests[1][1]["return_error_code"] == "true"


def test_street_view_zero_results_and_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    response_payload = {"status": "ZERO_RESULTS"}

    def fake_get(
        url: str,
        *,
        params: dict[str, object],
        timeout: float,
    ) -> httpx.Response:
        del params, timeout
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json=response_payload,
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    client = GoogleStreetViewClient(api_key="private-test-key")

    assert client.get_metadata(location="missing").available is False
    response_payload = {"status": "REQUEST_DENIED", "error_message": "API disabled"}
    with pytest.raises(GoogleStreetViewError, match="API disabled"):
        client.get_metadata(location="blocked")
