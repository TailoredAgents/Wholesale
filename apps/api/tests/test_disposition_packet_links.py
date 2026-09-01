from datetime import UTC, datetime, timedelta
from hashlib import sha256
from urllib.parse import urlparse
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    AuditEvent,
    DispositionCase,
    DispositionPackageShareLink,
    DispositionPackageVersion,
    Transaction,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.disposition_buyer_pool import _project_purchase_evidence
from tests.test_dispositions import (
    HEADERS,
    create_approved_disposition_case,
    setup_case_foundation,
)


def _approved_case(db: Session, client: TestClient) -> tuple[str, DispositionPackageVersion]:
    _, transaction_id, _ = setup_case_foundation(db, client)
    case_id = create_approved_disposition_case(client, transaction_id)
    version = db.scalar(
        select(DispositionPackageVersion).where(
            DispositionPackageVersion.disposition_case_id == UUID(case_id),
            DispositionPackageVersion.status == "approved",
        )
    )
    assert version is not None and version.pdf_data is not None
    return case_id, version


def test_secure_package_link_is_exact_audited_revocable_and_secret_is_not_stored(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, version = _approved_case(db_session, client)

    unauthenticated = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/share-links",
        json={"expires_in_hours": 72},
    )
    assert unauthenticated.status_code == 401

    issued = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/share-links",
        headers=HEADERS,
        json={"expires_in_hours": 72},
    )
    assert issued.status_code == 201, issued.text
    payload = issued.json()
    assert payload["status"] == "active"
    assert payload["package_version_id"] == str(version.id)
    assert payload["artifact_sha256"] == sha256(bytes(version.pdf_data)).hexdigest()
    path = urlparse(payload["share_url"]).path
    token = path.rsplit("/", 1)[-1]
    raw_secret = token.split(".", 1)[1]

    link = db_session.get(DispositionPackageShareLink, UUID(payload["id"]))
    assert link is not None
    assert raw_secret not in link.token_digest
    assert link.token_digest == sha256(raw_secret.encode("utf-8")).hexdigest()

    listed = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package/share-links",
        headers=HEADERS,
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["token_hint"] == payload["token_hint"]
    assert "share_url" not in listed.json()[0]

    downloaded = client.get(path, headers={"User-Agent": "investor-test-browser"})
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == bytes(version.pdf_data)
    assert downloaded.headers["cache-control"] == "private, no-store, max-age=0"
    assert downloaded.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
    assert downloaded.headers["referrer-policy"] == "no-referrer"
    assert downloaded.headers["content-disposition"].startswith("inline;")
    db_session.refresh(link)
    assert link.access_count == 1
    access_audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == link.id,
            AuditEvent.action == "disposition.package_share_link.accessed",
        )
    )
    assert access_audit is not None
    audit_text = str(access_audit.new_value)
    assert "investor-test-browser" not in audit_text
    assert "testclient" not in audit_text
    assert len(str((access_audit.new_value or {})["client_fingerprint"])) == 64

    tampered_path = path[:-1] + ("a" if path[-1] != "a" else "b")
    assert client.get(tampered_path).status_code == 404

    revoked = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/share-links/{link.id}/revoke",
        headers=HEADERS,
        json={
            "expected_version": link.lock_version,
            "reason": "Recipient should no longer have package access.",
        },
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["status"] == "revoked"
    assert client.get(path).status_code == 410


def test_package_link_expires_but_remains_bound_after_a_newer_version(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, version = _approved_case(db_session, client)
    issued = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/share-links",
        headers=HEADERS,
        json={"expires_in_hours": 1},
    )
    assert issued.status_code == 201, issued.text
    path = urlparse(issued.json()["share_url"]).path
    link = db_session.get(DispositionPackageShareLink, UUID(issued.json()["id"]))
    assert link is not None

    link.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    assert client.get(path).status_code == 410

    link.expires_at = datetime.now(UTC) + timedelta(hours=1)
    db_session.commit()
    newer = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=HEADERS,
        json={"expected_latest_version": version.version_number},
    )
    assert newer.status_code == 201, newer.text
    historical = client.get(path)
    assert historical.status_code == 200
    assert historical.content == bytes(version.pdf_data or b"")
    listed = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package/share-links",
        headers=HEADERS,
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["is_current_now"] is False
    assert listed.json()[0]["is_preliminary"] is True
    assert historical.headers["x-stonegate-package-status"] == "preliminary"
    assert "PRELIMINARY-" in historical.headers["content-disposition"]


def test_package_link_tightens_to_preliminary_after_source_facts_change(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, version = _approved_case(db_session, client)
    issued = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/share-links",
        headers=HEADERS,
        json={"expires_in_hours": 1},
    )
    assert issued.status_code == 201, issued.text
    assert issued.json()["was_current_at_issue"] is True
    assert issued.json()["is_preliminary"] is False
    original = bytes(version.pdf_data or b"")
    disposition_case = db_session.get(DispositionCase, UUID(case_id))
    assert disposition_case is not None
    transaction = db_session.get(Transaction, disposition_case.transaction_id)
    assert transaction is not None
    transaction.purchase_price_cents += 1
    db_session.commit()

    listed = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package/share-links",
        headers=HEADERS,
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["was_current_at_issue"] is True
    assert listed.json()[0]["is_current_now"] is False
    assert listed.json()[0]["is_preliminary"] is True
    downloaded = client.get(urlparse(issued.json()["share_url"]).path)
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == original
    assert downloaded.headers["x-stonegate-package-status"] == "preliminary"
    assert "PRELIMINARY-" in downloaded.headers["content-disposition"]


def test_package_link_listing_fails_closed_on_cross_tenant_version_reference(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, version = _approved_case(db_session, client)
    issued = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/share-links",
        headers=HEADERS,
        json={"expires_in_hours": 1},
    )
    assert issued.status_code == 201, issued.text
    other = bootstrap_foundation(
        db_session,
        organization_name="Other Packet Organization",
        admin_email="other-packet-owner@example.com",
        admin_name="Other Packet Owner",
    )
    version.organization_id = other.organization.id
    db_session.commit()

    listed = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package/share-links",
        headers=HEADERS,
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["status"] == "artifact_unavailable"
    assert listed.json()[0]["package_version_number"] == 0
    assert client.get(urlparse(issued.json()["share_url"]).path).status_code == 410


def test_package_link_requires_a_complete_artifact_and_reports_later_damage(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, version = _approved_case(db_session, client)
    original_file_name = version.pdf_file_name
    version.pdf_file_name = None
    db_session.commit()

    rejected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/share-links",
        headers=HEADERS,
        json={"expires_in_hours": 72},
    )
    assert rejected.status_code == 422, rejected.text
    assert "integrity check" in rejected.json()["detail"]

    version.pdf_file_name = original_file_name
    db_session.commit()
    issued = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/share-links",
        headers=HEADERS,
        json={"expires_in_hours": 72},
    )
    assert issued.status_code == 201, issued.text
    path = urlparse(issued.json()["share_url"]).path

    version.pdf_file_name = None
    db_session.commit()
    listed = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package/share-links",
        headers=HEADERS,
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["status"] == "artifact_unavailable"
    assert client.get(path).status_code == 410


def test_saved_purchase_evidence_projects_only_verified_record_fields() -> None:
    projected = _project_purchase_evidence(
        {
            "dm_property_id": "dm-property-42",
            "address": "101 First St",
            "city": "Atlanta",
            "state": "GA",
            "zip": "30303",
            "last_sale_date": "2026-07-01",
            "last_sale_price": 185000,
            "property_type": ["Single Family"],
            "latitude": 33.7503,
            "longitude": -84.3891,
            "contacts": [{"phone": "private"}],
            "num_mortgages": 0,
            "inferred_strategy": "flip",
            "connected_portfolio": ["private"],
        },
        (33.7490, -84.3880),
    )
    assert projected is not None
    assert projected == {
        "provider_property_id": "dm-property-42",
        "address": "101 First St, Atlanta, GA 30303",
        "purchase_date": datetime(2026, 7, 1).date(),
        "purchase_price_cents": 18500000,
        "property_types": ["Single Family"],
        "distance_miles": projected["distance_miles"],
        "distance_basis": "saved_provider_coordinates",
    }
    assert isinstance(projected["distance_miles"], float)
    assert set(projected) == {
        "provider_property_id",
        "address",
        "purchase_date",
        "purchase_price_cents",
        "property_types",
        "distance_miles",
        "distance_basis",
    }

    without_provider_coordinates = _project_purchase_evidence(
        {"address": "202 Second St", "city": "Atlanta", "state": "GA"},
        (33.7490, -84.3880),
    )
    assert without_provider_coordinates is not None
    assert without_provider_coordinates["distance_miles"] is None
    assert without_provider_coordinates["distance_basis"] is None
