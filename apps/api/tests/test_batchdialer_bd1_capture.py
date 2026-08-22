import hashlib
import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from scripts.capture_batchdialer_bd1 import (
    MAX_REQUESTS,
    AliasBook,
    CaptureConfig,
    CaptureError,
    CaptureSession,
    Operation,
    load_local_capture_environment,
    project_json,
    strict_json_loads,
)

API_KEY = "bd1-test-api-key-that-must-never-leak"
CAMPAIGN_ID = "campaign-raw-controlled"
CONTACT_ID = "contact-raw-controlled"
VENDOR_CONTACT_ID = "vendor-contact-raw-991177"
CDR_ID = 88_112_233


def capture_config(**overrides: object) -> CaptureConfig:
    values: dict[str, object] = {
        "api_key": API_KEY,
        "campaign_id": CAMPAIGN_ID,
        "contact_id": CONTACT_ID,
        "call_date": "2026-08-18T00:00:00-04:00",
        "controlled_campaign_confirmed": True,
    }
    values.update(overrides)
    return CaptureConfig(
        **values,
    )


def test_direct_sync_configuration_is_worker_safe_and_active_when_key_is_present() -> None:
    missing_key = Settings.model_validate({})
    configured = Settings.model_validate(
        {
            "BATCHDIALER_API_BASE_URL": "https://app.batchdialer.com/api/",
            "BATCHDIALER_API_KEY": API_KEY,
        }
    )

    assert missing_key.batchdialer_configured is False
    assert missing_key.batchdialer_configuration_blockers == ("BATCHDIALER_API_KEY",)
    assert configured.batchdialer_configured is True
    assert configured.batchdialer_configuration_blockers == ()
    assert configured.batchdialer_api_base_url == "https://app.batchdialer.com/api"
    assert configured.batchdialer_account_timezone == "America/Chicago"
    assert API_KEY not in repr(configured)

    with pytest.raises(ValidationError, match="official"):
        Settings.model_validate(
            {
                "BATCHDIALER_API_BASE_URL": "https://attacker.invalid/api",
            }
        )
    with pytest.raises(ValidationError, match="valid IANA timezone"):
        Settings.model_validate({"BATCHDIALER_ACCOUNT_TIMEZONE": "not/a-timezone"})


def test_local_capture_environment_accepts_only_fixed_keys(tmp_path: Path) -> None:
    safe_file = tmp_path / ".env.bd1"
    safe_file.write_text(
        "BATCHDIALER_BD1_API_KEY=not-a-real-test-key\n"
        "BATCHDIALER_BD1_CAMPAIGN_ID=controlled-campaign\n",
        encoding="utf-8",
    )
    assert load_local_capture_environment(safe_file) == {
        "BATCHDIALER_BD1_API_KEY": "not-a-real-test-key",
        "BATCHDIALER_BD1_CAMPAIGN_ID": "controlled-campaign",
    }

    unsafe_file = tmp_path / ".env.unsafe"
    unsafe_file.write_text("UNRELATED_SECRET=must-not-be-read\n", encoding="utf-8")
    with pytest.raises(CaptureError, match="forbidden key"):
        load_local_capture_environment(unsafe_file)


def test_sanitizer_preserves_blank_missingness_and_approved_dash_variant() -> None:
    assert project_json(
        {
            "vendorcontactid": "",
            "disposition": "Qualified Seller \u2013 Follow Up",
            "did": "+16785417725",
        },
        AliasBook(),
        allowed_keys={"vendorcontactid", "disposition", "did"},
        mask_operational_values=True,
    ) == {
        "vendorcontactid": "",
        "disposition": "Qualified Seller \u2013 Follow Up",
        "did": "+12025550100",
    }


def successful_transport(seen_requests: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        provided_key = request.headers.get("X-ApiKey")
        if provided_key == "bd1-intentionally-invalid-token":
            return httpx.Response(
                401,
                headers={"X-Request-ID": "raw-provider-request-id"},
                json={"error": f"Invalid API key {provided_key}", "api_key": provided_key},
            )
        assert provided_key == API_KEY

        if request.url.path.endswith("/campaigns") and request.method == "GET":
            return httpx.Response(
                200,
                headers={"X-Request-ID": "raw-campaign-request-id"},
                json=[
                    {
                        "id": CAMPAIGN_ID,
                        "parentid": None,
                        "name": "Controlled Distressed Homeowners",
                        "mode": "predictive",
                        "recyclecount": 0,
                        "level": 1,
                        "externalid": None,
                        "number_of_contacts": 1,
                        "date_added": "2026-08-18T10:00:00Z",
                        "status": "active",
                    }
                ],
            )
        if request.url.path.endswith("/campaigns/search"):
            body = json.loads(request.content)
            return httpx.Response(
                200,
                json=[
                    {
                        "id": f"raw-search-campaign-{body['page']}",
                        "name": f"Private Campaign {body['page']}",
                        "mode": "predictive",
                        "contacts": 25,
                        "status": "active",
                        "dateadded": "2026-08-18T10:00:00Z",
                        "externalid": f"raw-search-external-id-{body['page']}",
                    }
                ],
            )
        if f"/contact/{CONTACT_ID}" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "id": CONTACT_ID,
                    "vendorcontactid": VENDOR_CONTACT_ID,
                    "firstname": "Real",
                    "lastname": "Person",
                    "address": "123 Private Street",
                    "city": "Private City",
                    "state": "GA",
                    "postalcode": "30101",
                    "dateofbirth": "1982-04-07",
                    "email": "real.person@private.invalid",
                    "securityphrase": "provider-secret-phrase",
                    "comments": "Private seller notes 678-525-8427",
                    "lastcallid": 99_999_999,
                    "phonenumber1": "6785258427",
                    "phonenumbers": [
                        {
                            "id": "raw-phone-row-id",
                            "contactid": CONTACT_ID,
                            "phonenumber": "6785258427",
                            "numbertype": "mobile",
                            "dnc": False,
                        }
                    ],
                    "status": "active",
                    "disposition": "Qualified Seller - Follow Up",
                    "dateadded": "2026-08-18T13:50:00-05:00",
                    "datemodified": "2026-08-18T13:51:07-05:00",
                },
            )
        if request.url.path.endswith("/v2/cdrs"):
            if request.url.params.get("next_page"):
                return httpx.Response(200, json={"items": [], "nextPage": None})
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": CDR_ID,
                            "direction": "outbound",
                            "callStartTime": "2026-08-18T13:50:00-05:00",
                            "callEndTime": "2026-08-18T13:51:07-05:00",
                            "did": "+16785417725",
                            "customerNumber": "+16785258427",
                            "disposition": "Qualified Seller - Follow Up",
                            "duration": 67,
                            "status": "completed",
                            "agent": {
                                "id": "raw-agent-id",
                                "firstname": "Richard",
                                "lastname": "Dugger",
                            },
                            "contact": {
                                "id": CONTACT_ID,
                                "firstname": "Real",
                                "lastname": "Person",
                                "address": "123 Private Street",
                                "city": "Private City",
                                "state": "GA",
                                "zip": "30101",
                                "email": "real.person@private.invalid",
                            },
                            "campaign": {
                                "id": CAMPAIGN_ID,
                                "name": "Controlled Distressed Homeowners",
                            },
                            "client": {"id": "raw-client-id", "name": "Private Account"},
                            "callid": "raw-call-provider-id",
                            "recordingenabled": True,
                            "callRecordUrl": "https://private.invalid/signed-recording?token=raw",
                            "comments": ["Private call note"],
                        },
                        {
                            "id": "unrelated-call-id",
                            "contact": {
                                "id": "unrelated-contact-id",
                                "firstname": "Unrelated",
                                "lastname": "Seller",
                            },
                            "campaign": {
                                "id": CAMPAIGN_ID,
                                "name": "Controlled Distressed Homeowners",
                            },
                        },
                    ],
                    "nextPage": "raw-provider-cursor-token",
                },
            )
        if request.url.path.endswith("/cdrs/by-lead-id"):
            assert json.loads(request.content)["vendor_contact_id"] == VENDOR_CONTACT_ID
            return httpx.Response(
                200,
                json=[
                    {
                        "call_type": "outbound",
                        "date_time": "2026-08-18T13:50:00-05:00",
                        "phone_no": "6785258427",
                        "call_result": "Qualified Seller - Follow Up",
                        "agent": "Richard Dugger",
                        "campaign": "Controlled Distressed Homeowners",
                        "duration": 67,
                        "notes": "Private seller call notes",
                        "attachments": ["https://private.invalid/private-photo.jpg"],
                        "note_only": False,
                    }
                ],
            )
        if request.url.path.endswith(f"/cdrs/{CDR_ID}/transcription"):
            return httpx.Response(
                200,
                json=[
                    {
                        "time": 1_784_999_400_000,
                        "role": "agent",
                        "text": "My private address is 123 Private Street.",
                    }
                ],
            )
        raise AssertionError(f"Unexpected test request: {request.method} {request.url.path}")

    return httpx.MockTransport(handler)


def test_capture_is_bounded_relational_and_contains_no_raw_secrets_or_pii(
    tmp_path: Path,
) -> None:
    seen_requests: list[httpx.Request] = []
    with CaptureSession(
        capture_config(),
        transport=successful_transport(seen_requests),
        fixture_root=tmp_path,
    ) as session:
        results = session.run()

    assert len(seen_requests) == MAX_REQUESTS
    assert len(results) == MAX_REQUESTS
    assert all("/v2/cdrs/last" not in request.url.path for request in seen_requests)
    assert all(request.url.host == "app.batchdialer.com" for request in seen_requests)

    artifact_text = "\n".join(result.fixture_path.read_text() for result in results)
    for forbidden in (
        API_KEY,
        CAMPAIGN_ID,
        CONTACT_ID,
        VENDOR_CONTACT_ID,
        str(CDR_ID),
        "raw-provider-cursor-token",
        "raw-provider-request-id",
        "raw-search-external-id",
        "Real",
        "Richard",
        "Dugger",
        "123 Private Street",
        "Private City",
        "real.person@private.invalid",
        "provider-secret-phrase",
        "6785258427",
        "16785417725",
        "Private seller",
        "private.invalid",
    ):
        assert forbidden not in artifact_text

    fixtures = [json.loads(result.fixture_path.read_text()) for result in results]
    assert all(fixture["review_status"] == "pending_review" for fixture in fixtures)
    assert {
        fixture["provenance"] for fixture in fixtures
    } == {"controlled_account_observation", "account_schema_observation"}
    assert all("X-ApiKey" not in json.dumps(fixture) for fixture in fixtures)

    contact_fixture = next(
        fixture for fixture in fixtures if fixture["operation"] == "target_contact"
    )
    contact_body = contact_fixture["response"]["body"]
    assert contact_body["id"].startswith("id-")
    assert contact_body["phonenumber1"].startswith("+120255501")
    assert contact_body["email"].endswith("@example.com")
    assert contact_body["dateofbirth"] == "1970-01-01"
    assert "securityphrase" not in contact_body

    cdr_fixture = next(
        fixture for fixture in fixtures if fixture["operation"] == "cdr_cursor_page_one"
    )
    assert len(cdr_fixture["response"]["body"]["items"]) == 1
    cdr_contact_id = cdr_fixture["response"]["body"]["items"][0]["contact"]["id"]
    assert cdr_contact_id == contact_body["id"]


def test_capture_does_not_follow_redirect_or_leave_fixture(tmp_path: Path) -> None:
    seen_requests: list[httpx.Request] = []

    def redirect_handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(302, headers={"Location": "https://example.com/credential-sink"})

    with (
        CaptureSession(
            capture_config(),
            transport=httpx.MockTransport(redirect_handler),
            fixture_root=tmp_path,
        ) as session,
        pytest.raises(CaptureError, match="forbidden redirect"),
    ):
        session.run()

    assert len(seen_requests) == 1
    assert not list(tmp_path.rglob("*.json"))
    assert API_KEY not in repr(capture_config())


def test_capture_rejects_noncontract_endpoint_stateful_endpoint_and_duplicate_json() -> None:
    with pytest.raises(CaptureError, match="fixed contract"):
        Operation(
            "campaigns_active",
            "POST",
            "/contacts",
            "/contacts",
            "list",
            body={"status": "active"},
        )
    with pytest.raises(CaptureError, match="fixed contract|forbidden"):
        Operation(
            "cdr_cursor_page_one",
            "GET",
            "/v2/cdrs/last",
            "/v2/cdrs",
            "dict",
            params={"pagelength": 1, "callDate": "2026-08-18T00:00:00Z"},
        )
    with pytest.raises(CaptureError, match="duplicate"):
        strict_json_loads(b'{"id": 1, "id": 2}')


def test_capture_rejects_oversized_or_invalid_success_without_writing(tmp_path: Path) -> None:
    for body in (b"x" * 1_000_001, b"not-json"):
        transport = httpx.MockTransport(
            lambda _request, response_body=body: httpx.Response(200, content=response_body)
        )
        with (
            CaptureSession(
                capture_config(),
                transport=transport,
                fixture_root=tmp_path,
            ) as session,
            pytest.raises(CaptureError),
        ):
            session.run()
        assert not list(tmp_path.rglob("*.json"))


def test_capture_does_not_write_partial_run_when_later_request_fails(tmp_path: Path) -> None:
    seen_requests: list[httpx.Request] = []
    successful = successful_transport(seen_requests)

    def late_failure(request: httpx.Request) -> httpx.Response:
        response = successful.handle_request(request)
        if len(seen_requests) == 2:
            return httpx.Response(200, content=b"not-json", request=request)
        return response

    with (
        CaptureSession(
            capture_config(),
            transport=httpx.MockTransport(late_failure),
            fixture_root=tmp_path,
        ) as session,
        pytest.raises(CaptureError, match="invalid JSON"),
    ):
        session.run()

    assert len(seen_requests) == 2
    assert not list(tmp_path.rglob("*.json"))


def test_capture_quarantines_undocumented_provider_property_without_persisting_it(
    tmp_path: Path,
) -> None:
    seen_requests: list[httpx.Request] = []
    successful = successful_transport(seen_requests)

    def schema_drift(request: httpx.Request) -> httpx.Response:
        response = successful.handle_request(request)
        if len(seen_requests) == 1:
            body = response.json()
            body[0]["John_Smith"] = "private value"
            return httpx.Response(200, json=body, request=request)
        return response

    with CaptureSession(
        capture_config(),
        transport=httpx.MockTransport(schema_drift),
        fixture_root=tmp_path,
    ) as session:
        results = session.run()

    assert len(seen_requests) == MAX_REQUESTS
    fixture = next(
        json.loads(result.fixture_path.read_text())
        for result in results
        if result.operation_id == "campaigns_active"
    )
    expected_fingerprint = hashlib.sha256(b"johnsmith").hexdigest()[:12]
    assert fixture["response"]["schema_drift"] == {
        "undocumented_property_fingerprints": [expected_fingerprint]
    }
    fixture_text = json.dumps(fixture)
    assert "John_Smith" not in fixture_text
    assert "private value" not in fixture_text


def test_capture_rejects_unsafe_provider_property_name_without_writing(tmp_path: Path) -> None:
    seen_requests: list[httpx.Request] = []
    successful = successful_transport(seen_requests)

    def unsafe_schema(request: httpx.Request) -> httpx.Response:
        response = successful.handle_request(request)
        if len(seen_requests) == 1:
            body = response.json()
            body[0]["unsafe property?"] = "private value"
            return httpx.Response(200, json=body, request=request)
        return response

    with (
        CaptureSession(
            capture_config(),
            transport=httpx.MockTransport(unsafe_schema),
            fixture_root=tmp_path,
        ) as session,
        pytest.raises(CaptureError, match="unsafe JSON property name"),
    ):
        session.run()

    assert len(seen_requests) == 1
    assert not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize(
    ("config_overrides", "message"),
    [
        (
            {"vendor_contact_id": "different-vendor-contact"},
            "vendor-contact ID does not match",
        ),
        ({"cdr_id": "123456"}, "CDR ID does not match"),
    ],
)
def test_capture_rejects_mismatched_controlled_id_overrides(
    tmp_path: Path,
    config_overrides: dict[str, object],
    message: str,
) -> None:
    seen_requests: list[httpx.Request] = []
    with (
        CaptureSession(
            capture_config(**config_overrides),
            transport=successful_transport(seen_requests),
            fixture_root=tmp_path,
        ) as session,
        pytest.raises(CaptureError, match=message),
    ):
        session.run()

    assert len(seen_requests) == 6
    assert not list(tmp_path.rglob("*.json"))


def test_capture_requires_exact_campaign_on_controlled_cdr(tmp_path: Path) -> None:
    seen_requests: list[httpx.Request] = []
    successful = successful_transport(seen_requests)

    def missing_campaign(request: httpx.Request) -> httpx.Response:
        response = successful.handle_request(request)
        if request.url.path.endswith("/v2/cdrs") and not request.url.params.get("next_page"):
            body = response.json()
            body["items"][0].pop("campaign")
            return httpx.Response(200, json=body, request=request)
        return response

    with (
        CaptureSession(
            capture_config(),
            transport=httpx.MockTransport(missing_campaign),
            fixture_root=tmp_path,
        ) as session,
        pytest.raises(CaptureError, match="controlled BatchDialer contact was not found"),
    ):
        session.run()

    assert len(seen_requests) == 5
    assert not list(tmp_path.rglob("*.json"))
