from typing import cast

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import AuditEvent, PublicProofRecord, Role, RoleAssignment, User
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"


def seed_owner(db: Session) -> None:
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )


def headers(email: str = OWNER_EMAIL) -> dict[str, str]:
    return {"X-Dev-User-Email": email}


def review_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "proof_type": "review",
        "title": "A straightforward property sale",
        "content": "The team explained the process and followed through on the written timeline.",
        "attribution_name": "J. S.",
        "attribution_detail": "Georgia property seller",
        "location_label": "Canton, Georgia",
        "rating": 5,
        "source_type": "signed_release",
        "source_url": "https://example.com/evidence/review-1",
        "source_reference": "Signed seller release SG-2026-001",
        "show_source_link": False,
        "permission_status": "granted",
        "permission_evidence_notes": "Signed release SG-2026-001 permits website publication.",
        "featured": True,
        "sort_order": 10,
    }
    payload.update(overrides)
    return payload


def decide(
    client: TestClient,
    record_id: str,
    decision: str,
    reason: str = "Reviewed evidence.",
) -> Response:
    return cast(
        Response,
        client.post(
            f"/api/v1/marketing/trust-proofs/{record_id}/decision",
            headers=headers(),
            json={"decision": decision, "reason": reason},
        ),
    )


def test_public_proof_requires_review_and_publishes_only_approved_fields(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)

    empty_public = client.get("/api/v1/public/trust-proofs")
    created = client.post(
        "/api/v1/marketing/trust-proofs",
        headers=headers(),
        json=review_payload(show_source_link=True),
    )
    record_id = created.json()["id"]
    draft_public = client.get("/api/v1/public/trust-proofs")
    submitted = decide(client, record_id, "submit_review")
    review_public = client.get("/api/v1/public/trust-proofs")
    published = decide(client, record_id, "publish", "Source and seller release verified.")
    live_public = client.get("/api/v1/public/trust-proofs")

    assert empty_public.status_code == 200
    assert empty_public.json() == {"records": []}
    assert created.status_code == 201
    assert created.json()["publication_status"] == "draft"
    assert draft_public.json() == {"records": []}
    assert submitted.status_code == 200
    assert submitted.json()["publication_status"] == "in_review"
    assert review_public.json() == {"records": []}
    assert published.status_code == 200
    assert published.json()["publication_status"] == "published"
    records = live_public.json()["records"]
    assert len(records) == 1
    assert records[0]["title"] == "A straightforward property sale"
    assert records[0]["source_url"] == "https://example.com/evidence/review-1"
    assert "permission_evidence_notes" not in records[0]
    assert "source_reference" not in records[0]
    assert live_public.headers["cache-control"] == (
        "public, max-age=60, stale-while-revalidate=300"
    )

    retired = decide(client, record_id, "retire", "Seller requested retirement.")
    assert retired.status_code == 200
    assert client.get("/api/v1/public/trust-proofs").json() == {"records": []}
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_type == "public_proof_record")
        )
        == 4
    )


def test_public_proof_blocks_missing_evidence_permission_and_disclosure(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)

    missing_source = client.post(
        "/api/v1/marketing/trust-proofs",
        headers=headers(),
        json=review_payload(source_url=None, source_reference=None),
    )
    missing_source_id = missing_source.json()["id"]
    assert decide(client, missing_source_id, "submit_review").status_code == 422
    invalid_required_field = client.patch(
        f"/api/v1/marketing/trust-proofs/{missing_source_id}",
        headers=headers(),
        json={"title": None},
    )
    assert invalid_required_field.status_code == 422
    assert invalid_required_field.json()["detail"] == "Public title cannot be empty."

    pending_permission = client.post(
        "/api/v1/marketing/trust-proofs",
        headers=headers(),
        json=review_payload(permission_status="pending"),
    )
    pending_id = pending_permission.json()["id"]
    assert decide(client, pending_id, "submit_review").status_code == 200
    publish_pending = decide(client, pending_id, "publish")
    assert publish_pending.status_code == 422
    assert "Usage permission" in publish_pending.json()["detail"]

    undisclosed_connection = client.post(
        "/api/v1/marketing/trust-proofs",
        headers=headers(),
        json=review_payload(material_connection="Reviewer is an employee.", disclosure=None),
    )
    connection_id = undisclosed_connection.json()["id"]
    assert decide(client, connection_id, "submit_review").status_code == 200
    publish_connection = decide(client, connection_id, "publish")
    assert publish_connection.status_code == 422
    assert "visible disclosure" in publish_connection.json()["detail"]

    placeholder = client.post(
        "/api/v1/marketing/trust-proofs",
        headers=headers(),
        json=review_payload(content="Sample testimonial for layout."),
    )
    assert decide(client, placeholder.json()["id"], "submit_review").status_code == 422
    assert client.get("/api/v1/public/trust-proofs").json() == {"records": []}


def test_statistic_requires_method_and_non_marketing_role_cannot_manage(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    acquisition_role = db_session.scalar(
        select(Role).where(
            Role.organization_id == owner.organization_id,
            Role.key == "acquisition_rep",
        )
    )
    assert acquisition_role is not None
    acquisition_user = User(
        organization_id=owner.organization_id,
        email="acquisition@example.com",
        display_name="Acquisition",
        is_active=True,
    )
    db_session.add(acquisition_user)
    db_session.flush()
    db_session.add(
        RoleAssignment(
            organization_id=owner.organization_id,
            user_id=acquisition_user.id,
            role_id=acquisition_role.id,
        )
    )
    db_session.commit()

    forbidden = client.post(
        "/api/v1/marketing/trust-proofs",
        headers=headers(acquisition_user.email),
        json=review_payload(),
    )
    assert forbidden.status_code == 403

    statistic = client.post(
        "/api/v1/marketing/trust-proofs",
        headers=headers(),
        json={
            "proof_type": "statistic",
            "title": "Verified completed purchases",
            "metric_label": "Completed Stonegate purchases",
            "metric_value": "3",
            "as_of_date": "2026-07-29",
            "source_type": "transaction_record",
            "source_reference": "Funded transaction report dated 2026-07-29",
            "permission_status": "not_required",
            "permission_evidence_notes": (
                "Aggregate company count contains no seller-identifying information."
            ),
        },
    )
    statistic_id = statistic.json()["id"]
    assert decide(client, statistic_id, "submit_review").status_code == 200
    missing_method = decide(client, statistic_id, "publish")
    assert missing_method.status_code == 422
    assert "calculation method" in missing_method.json()["detail"]

    assert db_session.scalar(select(func.count()).select_from(PublicProofRecord)) == 1
