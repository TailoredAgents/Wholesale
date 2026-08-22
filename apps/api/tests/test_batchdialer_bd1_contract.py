import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "batchdialer" / "bd1" / "v1"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
FIELD_MATRIX_PATH = FIXTURE_ROOT / "field_matrix.json"

REQUIRED_SCENARIOS = {
    "qualified_seller_follow_up",
    "appointment_set",
    "callback",
    "ordinary_non_lead_result",
    "unknown_result",
    "result_before_rename",
    "result_after_rename",
    "pagination_page_one",
    "pagination_page_two",
    "record_before_update",
    "record_after_update",
    "incomplete_record",
    "authentication_failure",
    "rate_limit",
    "temporary_provider_failure",
}
CONTROLLED_REQUIRED_SCENARIOS = {
    "qualified_seller_follow_up",
    "appointment_set",
    "ordinary_non_lead_result",
    "unknown_result",
    "result_before_rename",
    "result_after_rename",
    "pagination_page_one",
    "pagination_page_two",
    "record_before_update",
    "record_after_update",
    "incomplete_record",
}
SYNTHETIC_ALLOWED_SCENARIOS = {
    "authentication_failure",
    "rate_limit",
    "temporary_provider_failure",
}
REQUIRED_FIELD_KEYS = {
    "authentication.api_key_available",
    "authentication.request_header_format",
    "authentication.scope_and_account_identifier",
    "transport.base_url",
    "campaign.resource",
    "campaign.stable_id",
    "contact.resource",
    "contact.stable_id",
    "contact.name_phone_and_email",
    "contact.property_address_fields",
    "contact.created_at_updated_at_or_revision",
    "call.resource",
    "call.stable_id",
    "call.status_timestamps_duration_and_numbers",
    "call.contact_campaign_agent_and_result_links",
    "call.created_at_updated_at_or_revision",
    "call_result.stable_id",
    "call_result.label_and_rename_behavior",
    "note.resource_and_revision",
    "agent.stable_id_name_and_email",
    "callback.due_time_and_identity",
    "recording.reference_and_access_contract",
    "transcript.text_segments_and_access_contract",
    "pagination.mode_page_size_and_termination",
    "pagination.sort_and_tie_breaker",
    "filter.updated_since_or_cursor",
    "rate_limit.headers_retry_after_and_frequency",
    "error.request_id_and_retry_guidance",
    "consent.follow_up_permission_evidence",
}
ALLOWED_EVIDENCE_STATUSES = {"not_captured", "captured", "synthetic"}
CONTROLLED_REFERENCE_KEYS = {
    "fixture_sha256",
    "json_path",
    "reviewed_at",
    "reviewer",
    "scenario_id",
}
ALLOWED_PROVENANCE = {
    "account_schema_observation",
    "official_documentation",
    "controlled_account_observation",
    "synthetic_resilience",
}
ALLOWED_AVAILABILITY = {"supported", "unsupported", "ambiguous"}
ALLOWED_CRITICALITY = {"required", "optional"}
ALLOWED_RESPONSE_HEADERS = {
    "content-type",
    "date",
    "retry-after",
    "x-request-id",
    "x-correlation-id",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "ratelimit-limit",
    "ratelimit-remaining",
    "ratelimit-reset",
}
FORBIDDEN_KEY_PARTS = {
    "authorization",
    "cookie",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "secret",
    "signed_url",
}
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b", re.IGNORECASE)
REVIEWED_OBSERVATION_KEYS = {
    "captured_at",
    "endpoint_documentation_url",
    "fixture_path",
    "http_status",
    "id",
    "operation",
    "provenance",
    "response_headers",
    "review_status",
    "schema_drift_fingerprints",
    "sha256",
}


def load_json(path: Path) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, child in pairs:
            assert key not in value, f"Duplicate JSON key {key!r} in {path}."
            value[key] = child
        return value

    loaded = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
    )
    assert isinstance(loaded, dict)
    return loaded


def parse_aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None and parsed.utcoffset() is not None
    return parsed


def iter_values(value: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    items: list[tuple[tuple[str, ...], Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, str(key))
            items.append((child_path, child))
            items.extend(iter_values(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = (*path, str(index))
            items.append((child_path, child))
            items.extend(iter_values(child, child_path))
    return items


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def assert_controlled_reference(
    reference: Any,
    *,
    scenarios: dict[str, dict[str, Any]],
) -> None:
    assert isinstance(reference, dict)
    assert set(reference) == CONTROLLED_REFERENCE_KEYS
    scenario = scenarios[reference["scenario_id"]]
    assert scenario["evidence_status"] == "captured"
    assert scenario["provenance"] == "controlled_account_observation"
    assert reference["fixture_sha256"] == scenario["sha256"]
    assert re.fullmatch(r"[0-9a-f]{64}", reference["fixture_sha256"])
    assert isinstance(reference["json_path"], str)
    assert reference["json_path"].startswith("$.")
    assert isinstance(reference["reviewer"], str) and reference["reviewer"].strip()
    datetime.fromisoformat(reference["reviewed_at"].replace("Z", "+00:00"))


def assert_fixture_is_sanitized(fixture: dict[str, Any], fixture_path: Path) -> None:
    raw_text = fixture_path.read_text(encoding="utf-8")
    assert "Bearer " not in raw_text
    assert "Basic " not in raw_text

    for path, value in iter_values(fixture):
        key = normalize_key(path[-1])
        assert not any(part in key for part in FORBIDDEN_KEY_PARTS), (
            f"Sensitive key {'.'.join(path)} must not be stored in BD1 fixtures."
        )
        if not isinstance(value, str):
            continue

        for match in EMAIL_PATTERN.finditer(value):
            assert match.group(1).lower() == "example.com", (
                f"Non-example email found at {'.'.join(path)}."
            )

        if "phone" in key or "mobile" in key:
            digits = re.sub(r"\D", "", value)
            if digits:
                national = digits[-10:]
                assert len(national) == 10 and national.startswith("20255501"), (
                    f"Non-fictional phone found at {'.'.join(path)}."
                )


def test_bd1_manifest_is_complete_and_pending_controlled_capture() -> None:
    manifest = load_json(MANIFEST_PATH)

    assert manifest["schema_version"] == "batchdialer_bd1_evidence_v1"
    assert manifest["status"] == "controlled_capture_pending"
    assert manifest["ready_for_bd2"] is False
    assert manifest["acceptance_blockers"]
    parse_aware_datetime(manifest["updated_at"])

    sources = manifest["official_sources"]
    source_ids = {source["id"] for source in sources}
    assert len(source_ids) == len(sources)
    assert {
        "developer_portal",
        "getting_started",
        "campaign_search",
        "contact_retrieval",
        "cdr_pagination",
        "cdr_latest_poll",
        "vendor_contact_call_history",
        "transcript_json",
    }.issubset(source_ids)
    for source in sources:
        parsed_url = urlparse(source["url"])
        assert parsed_url.scheme == "https"
        assert parsed_url.hostname in {
            "batchdialer.com",
            "developer.batchdialer.com",
            "help.getbatch.co",
        }
        assert source["provenance"] == "official_documentation"
        assert source["proves"]

    scenarios = manifest["required_scenarios"]
    assert {scenario["id"] for scenario in scenarios} == REQUIRED_SCENARIOS
    assert len({scenario["id"] for scenario in scenarios}) == len(scenarios)
    for scenario in scenarios:
        assert scenario["evidence_status"] in ALLOWED_EVIDENCE_STATUSES
        if scenario["id"] in CONTROLLED_REQUIRED_SCENARIOS:
            assert scenario["evidence_status"] != "synthetic"
        if scenario["evidence_status"] == "synthetic":
            assert scenario["id"] in SYNTHETIC_ALLOWED_SCENARIOS
        if scenario["evidence_status"] == "not_captured":
            assert scenario["provenance"] is None
            assert scenario["fixture_path"] is None
            assert scenario["sha256"] is None
            assert scenario["captured_at"] is None
            assert scenario["http_status"] is None
            assert scenario["response_headers"] == {}


def test_bd1_ready_gate_requires_complete_controlled_evidence() -> None:
    manifest = load_json(MANIFEST_PATH)
    matrix = load_json(FIELD_MATRIX_PATH)
    if not manifest["ready_for_bd2"]:
        assert manifest["status"] != "ready_for_bd2"
        assert manifest["acceptance_blockers"]
        return

    assert manifest["status"] == "ready_for_bd2"
    assert manifest["acceptance_blockers"] == []
    scenarios = {scenario["id"]: scenario for scenario in manifest["required_scenarios"]}
    for scenario_id in CONTROLLED_REQUIRED_SCENARIOS:
        assert scenarios[scenario_id]["evidence_status"] == "captured"
        assert scenarios[scenario_id]["provenance"] == "controlled_account_observation"

    controlled_evidence = matrix["controlled_evidence"]
    for field in matrix["fields"]:
        if field["criticality"] != "required":
            continue
        assert field["availability"] == "supported"
        assert field["evidence_source_ids"]
        assert_controlled_reference(
            controlled_evidence.get(field["key"]),
            scenarios=scenarios,
        )


def test_bd1_reviewed_observations_are_registered_hashed_and_sanitized() -> None:
    manifest = load_json(MANIFEST_PATH)
    observations = manifest["reviewed_observations"]

    assert {observation["operation"] for observation in observations} == {
        "campaigns_active",
        "campaign_search_page_one",
        "campaign_search_page_two",
        "target_contact",
        "cdr_cursor_page_one",
        "cdr_cursor_page_two",
        "target_transcript",
    }
    assert len({observation["id"] for observation in observations}) == len(observations)
    fixture_paths: set[Path] = set()
    fixture_hashes: set[str] = set()

    for observation in observations:
        assert set(observation) == REVIEWED_OBSERVATION_KEYS
        assert observation["review_status"] == "reviewed"
        assert observation["provenance"] in {
            "account_schema_observation",
            "controlled_account_observation",
        }
        assert observation["http_status"] == 200
        parse_aware_datetime(observation["captured_at"])
        assert all(
            re.fullmatch(r"[0-9a-f]{12}", fingerprint)
            for fingerprint in observation["schema_drift_fingerprints"]
        )
        assert set(map(str.lower, observation["response_headers"])) <= ALLOWED_RESPONSE_HEADERS

        documentation_url = urlparse(observation["endpoint_documentation_url"])
        assert documentation_url.scheme == "https"
        assert documentation_url.hostname == "developer.batchdialer.com"

        fixture_path = (FIXTURE_ROOT / observation["fixture_path"]).resolve()
        assert fixture_path.is_relative_to(FIXTURE_ROOT.resolve())
        assert fixture_path.is_file()
        assert fixture_path not in fixture_paths
        fixture_paths.add(fixture_path)

        raw_bytes = fixture_path.read_bytes()
        fixture_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        assert fixture_sha256 == observation["sha256"]
        assert fixture_sha256 not in fixture_hashes
        fixture_hashes.add(fixture_sha256)

        fixture = load_json(fixture_path)
        assert fixture["operation"] == observation["operation"]
        assert fixture["review_status"] == "reviewed"
        assert fixture["reviewed_at"] == "2026-08-22T16:48:07Z"
        assert fixture["reviewer"] == "Codex"
        assert fixture["provenance"] == observation["provenance"]
        assert fixture["captured_at"] == observation["captured_at"]
        assert fixture["response"]["status"] == observation["http_status"]
        assert fixture["response"]["headers"] == observation["response_headers"]
        assert (
            fixture["response"]["schema_drift"][
                "undocumented_property_fingerprints"
            ]
            == observation["schema_drift_fingerprints"]
        )
        assert_fixture_is_sanitized(fixture, fixture_path)


def test_bd1_field_matrix_covers_every_cutover_critical_contract_area() -> None:
    manifest = load_json(MANIFEST_PATH)
    source_ids = {source["id"] for source in manifest["official_sources"]}
    matrix = load_json(FIELD_MATRIX_PATH)

    assert matrix["schema_version"] == "batchdialer_bd1_field_matrix_v1"
    assert matrix["status"] == "controlled_capture_pending"
    assert isinstance(matrix["controlled_evidence"], dict)
    assert set(matrix["availability_values"]) == ALLOWED_AVAILABILITY

    fields = matrix["fields"]
    scenarios = {
        scenario["id"]: scenario for scenario in manifest["required_scenarios"]
    }
    for field_key, reference in matrix["controlled_evidence"].items():
        assert field_key in REQUIRED_FIELD_KEYS
        assert_controlled_reference(reference, scenarios=scenarios)
    field_keys = {field["key"] for field in fields}
    assert REQUIRED_FIELD_KEYS.issubset(field_keys)
    assert len(field_keys) == len(fields)
    for field in fields:
        assert field["availability"] in ALLOWED_AVAILABILITY
        assert field["criticality"] in ALLOWED_CRITICALITY
        assert field["stonegate_use"].strip()
        assert set(field["evidence_source_ids"]).issubset(source_ids)
        assert isinstance(field["controlled_observation_required"], bool)
        if field["availability"] == "supported":
            assert field["evidence_source_ids"], (
                f"Supported field {field['key']} must cite official evidence."
            )


def test_captured_bd1_fixtures_are_hashed_bounded_and_sanitized() -> None:
    manifest = load_json(MANIFEST_PATH)
    fixture_paths: set[Path] = set()
    fixture_hashes: set[str] = set()

    for scenario in manifest["required_scenarios"]:
        if scenario["evidence_status"] == "not_captured":
            continue

        expected_provenance = (
            "controlled_account_observation"
            if scenario["evidence_status"] == "captured"
            else "synthetic_resilience"
        )
        assert scenario["provenance"] == expected_provenance
        assert scenario["provenance"] in ALLOWED_PROVENANCE
        assert scenario["fixture_path"]
        fixture_path = (FIXTURE_ROOT / scenario["fixture_path"]).resolve()
        assert fixture_path.is_relative_to(FIXTURE_ROOT.resolve())
        assert fixture_path.is_file()
        assert fixture_path.suffix == ".json"
        assert fixture_path not in fixture_paths
        fixture_paths.add(fixture_path)

        raw_bytes = fixture_path.read_bytes()
        assert len(raw_bytes) <= 1_000_000
        assert hashlib.sha256(raw_bytes).hexdigest() == scenario["sha256"]
        assert scenario["sha256"] not in fixture_hashes
        fixture_hashes.add(scenario["sha256"])
        assert scenario["http_status"] in range(100, 600)
        if scenario["id"] == "authentication_failure":
            assert scenario["http_status"] in {401, 403}
        elif scenario["id"] == "rate_limit":
            assert scenario["http_status"] == 429
        elif scenario["id"] == "temporary_provider_failure":
            assert scenario["http_status"] in range(500, 600)
        parse_aware_datetime(scenario["captured_at"])

        documentation_url = urlparse(scenario["endpoint_documentation_url"])
        assert documentation_url.scheme == "https"
        assert documentation_url.hostname == "developer.batchdialer.com"
        assert set(map(str.lower, scenario["response_headers"])) <= ALLOWED_RESPONSE_HEADERS

        assert_fixture_is_sanitized(load_json(fixture_path), fixture_path)
