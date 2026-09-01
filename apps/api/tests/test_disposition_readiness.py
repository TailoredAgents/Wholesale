from copy import deepcopy
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    DispositionCase,
    DispositionPackageVersion,
    Lead,
    Transaction,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.disposition_state import ACTIVE_DISPOSITION_CASE_STATUSES
from tests.test_dispositions import (
    HEADERS,
    create_approved_disposition_case,
    setup_case_foundation,
)


def _ready_case(db: Session, client: TestClient) -> tuple[str, DispositionCase]:
    _, transaction_id, _ = setup_case_foundation(db, client)
    case_id = create_approved_disposition_case(client, transaction_id)
    case = db.get(DispositionCase, UUID(case_id))
    assert case is not None
    return case_id, case


def test_readiness_is_advisory_for_every_active_case_status(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, case = _ready_case(db_session, client)

    for case_status in ACTIVE_DISPOSITION_CASE_STATUSES:
        case.status = case_status
        db_session.commit()
        response = client.get(
            f"/api/v1/dispositions/cases/{case_id}/readiness",
            headers=HEADERS,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_advisory"] is True
        assert all(action["state"] != "blocked" for action in body["actions"])
        assert all(
            check["blocker_class"] in {None, "warning"}
            for action in body["actions"]
            for check in action["checks"]
        )
        assert body["best_action_key"] not in body["parallel_action_keys"]


def test_land_readiness_excludes_house_only_release_actions_from_progress(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, case = _ready_case(db_session, client)
    lead = db_session.scalar(
        select(Lead).where(
            Lead.id == case.lead_id,
            Lead.organization_id == case.organization_id,
        )
    )
    assert lead is not None
    lead.asset_class = "land"
    db_session.commit()

    response = client.get(
        f"/api/v1/dispositions/cases/{case_id}/readiness",
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    actions = {item["key"]: item for item in body["actions"]}
    for key in ("prepare_assignment", "record_funding", "reconcile"):
        assert actions[key]["state"] == "not_applicable"
    applicable = [item for item in body["actions"] if item["state"] != "not_applicable"]
    assert body["total_count"] == len(applicable)
    assert body["completed_count"] == sum(
        item["state"] == "complete" for item in applicable
    )


def test_readiness_warns_on_corrupt_artifact_and_remains_tenant_scoped(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, case = _ready_case(db_session, client)
    version = db_session.scalar(
        select(DispositionPackageVersion)
        .where(
            DispositionPackageVersion.organization_id == case.organization_id,
            DispositionPackageVersion.disposition_case_id == case.id,
        )
        .order_by(DispositionPackageVersion.version_number.desc())
    )
    assert version is not None and version.pdf_sha256 is not None
    version.pdf_sha256 = "0" * 64
    db_session.commit()

    response = client.get(
        f"/api/v1/dispositions/cases/{case_id}/readiness",
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    package_action = next(
        item for item in response.json()["actions"] if item["key"] == "build_package"
    )
    artifact = next(
        item for item in package_action["checks"] if item["key"] == "package.artifact"
    )
    assert package_action["state"] in {"available", "ready"}
    assert artifact["status"] == "warning"
    assert artifact["blocker_class"] == "warning"
    assert "hash" in artifact["detail"].lower()

    other = bootstrap_foundation(
        db_session,
        organization_name="Other Readiness Organization",
        admin_email="other-readiness-owner@example.com",
        admin_name="Other Readiness Owner",
    )
    hidden = client.get(
        f"/api/v1/dispositions/cases/{case_id}/readiness",
        headers={"X-Dev-User-Email": other.admin_user.email},
    )
    assert hidden.status_code == 404


def test_stale_exact_package_approval_preserves_snapshot_and_artifact_bytes(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, _ = setup_case_foundation(db_session, client)
    created = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": transaction_id,
            "strategy": "assignment",
            "asking_price_cents": 19_000_000,
            "minimum_acceptable_cents": 18_000_000,
            "operating_mode_key": "human_led",
        },
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    first = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=HEADERS,
        json={"expected_latest_version": 0},
    )
    second = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=HEADERS,
        json={"expected_latest_version": 1},
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    stale_version = db_session.get(DispositionPackageVersion, UUID(first.json()["id"]))
    latest_version = db_session.get(DispositionPackageVersion, UUID(second.json()["id"]))
    transaction = db_session.get(Transaction, UUID(transaction_id))
    assert stale_version is not None and latest_version is not None and transaction is not None
    original_snapshot = deepcopy(stale_version.readiness_snapshot)
    original_pdf = bytes(stale_version.pdf_data or b"")
    original_hash = stale_version.pdf_sha256
    transaction.purchase_price_cents += 1
    db_session.commit()

    approved = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{stale_version.id}/approval",
        headers=HEADERS,
        json={
            "expected_version": stale_version.lock_version,
            "attestation": True,
            "reason": "Reviewed this exact historical snapshot for intentional use.",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["is_current"] is False
    db_session.refresh(stale_version)
    assert stale_version.readiness_snapshot == original_snapshot
    assert bytes(stale_version.pdf_data or b"") == original_pdf
    assert stale_version.pdf_sha256 == original_hash

    latest_version.pdf_sha256 = "0" * 64
    db_session.commit()
    corrupt = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{latest_version.id}/approval",
        headers=HEADERS,
        json={
            "expected_version": latest_version.lock_version,
            "attestation": True,
            "reason": "A corrupt reviewed artifact must be rebuilt instead of re-rendered.",
        },
    )
    assert corrupt.status_code == 422, corrupt.text
    assert "immutable integrity" in corrupt.json()["detail"].lower()
