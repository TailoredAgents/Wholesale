import base64
import hmac
import re
import zlib
from hashlib import sha256
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}


def pdf_page_streams(content: bytes) -> bytes:
    decoded = []
    for encoded in re.findall(rb"stream\r?\n(.*?)endstream", content, re.DOTALL):
        try:
            compressed = base64.a85decode(
                b"<~" + encoded.strip(),
                adobe=True,
            )
            decoded.append(zlib.decompress(compressed))
        except (ValueError, zlib.error):
            continue
    return b"\n".join(decoded)


def setup_transaction(db: Session, client: TestClient) -> tuple[str, str]:
    bootstrap_foundation(
        db, organization_name="Stonegate Home Buyers", admin_email=OWNER_EMAIL, admin_name="Owner"
    )
    lead = client.post(
        "/api/v1/leads",
        headers=HEADERS,
        json={
            "contact": {"legal_name": "Jane Seller", "contact_type": "seller"},
            "property": {
                "street_address": "123 Peachtree St",
                "city": "Atlanta",
                "state": "GA",
                "postal_code": "30303",
                "property_type": "single_family",
            },
            "source": "referral",
            "stage_key": "offer_ready",
        },
    )
    transaction_response = client.post(
        f"/api/v1/leads/{lead.json()['id']}/transactions",
        headers=HEADERS,
        json={
            "purchase_price_cents": 17000000,
            "earnest_money_cents": 100000,
            "closing_date": "2026-08-14T21:00:00Z",
            "inspection_period_days": 7,
        },
    )
    return lead.json()["id"], transaction_response.json()["transactions"][0]["id"]


def test_contract_approval_execution_and_funding_gates(
    db_session: Session, api_db_override: None
) -> None:
    client = TestClient(app)
    lead_id, transaction_id = setup_transaction(db_session, client)
    overview = client.get("/api/v1/transactions", headers=HEADERS)
    assert overview.status_code == 200
    assert overview.json()["metrics"]["active"] == 1

    package_response = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages",
        headers=HEADERS,
        json={
            "seller_name": "Jane Seller",
            "buyer_entity_name": "Stonegate Acquisitions LLC",
            "purchase_price_cents": 17000000,
            "earnest_money_cents": 100000,
            "closing_date": "2026-08-14T21:00:00Z",
            "inspection_period_days": 7,
        },
    )
    assert package_response.status_code == 201
    package_id = package_response.json()["id"]
    pending = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/request-approval",
        headers=HEADERS,
    )
    approval_id = pending.json()["approval_request_id"]
    approved = client.patch(
        f"/api/v1/approvals/{approval_id}/decision",
        headers=HEADERS,
        json={"status": "approved", "decision_notes": "Terms verified."},
    )
    assert approved.status_code == 200
    assert (
        client.post(
            f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/mark-sent",
            headers=HEADERS,
        ).status_code
        == 200
    )

    missing_document = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/mark-executed?document_id=00000000-0000-0000-0000-000000000001",
        headers=HEADERS,
    )
    assert missing_document.status_code == 422
    signed = client.post(
        f"/api/v1/transactions/{transaction_id}/documents?file_name=signed.pdf&document_type=signed_purchase_agreement&title=Signed%20purchase%20agreement&document_status=executed&package_id={package_id}",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=b"%PDF signed purchase agreement",
    )
    assert signed.status_code == 201
    executed = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/mark-executed?document_id={signed.json()['id']}",
        headers=HEADERS,
    )
    assert executed.status_code == 200
    assert (
        client.get(f"/api/v1/leads/{lead_id}", headers=HEADERS).json()["stage_key"]
        == "under_contract"
    )

    blocked = client.post(
        f"/api/v1/transactions/{transaction_id}/close",
        headers=HEADERS,
        json={"outcome": "funded", "notes": "Closing confirmed."},
    )
    assert blocked.status_code == 422
    detail = client.get(f"/api/v1/transactions/{transaction_id}", headers=HEADERS).json()
    for item in detail["checklist"]:
        response = client.patch(
            f"/api/v1/transactions/{transaction_id}/checklist/{item['id']}",
            headers=HEADERS,
            json={"status": "complete"},
        )
        assert response.status_code == 200
    funding = client.post(
        f"/api/v1/transactions/{transaction_id}/documents?file_name=funding.pdf&document_type=funding_confirmation&title=Funding%20confirmation&document_status=evidence",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=b"%PDF funding confirmation",
    )
    closed = client.post(
        f"/api/v1/transactions/{transaction_id}/close",
        headers=HEADERS,
        json={"outcome": "funded", "notes": "Funds received by closing attorney."},
    )
    assert funding.status_code == 201
    assert closed.status_code == 200
    assert closed.json()["status"] == "funded"


def test_contract_template_requires_explicit_approval(
    db_session: Session, api_db_override: None
) -> None:
    client = TestClient(app)
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    created = client.post(
        "/api/v1/transactions/templates?file_name=ga-purchase.pdf&document_type=purchase_agreement&state_code=GA&name=Georgia%20Purchase%20Agreement",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=b"%PDF attorney reviewed template",
    )
    assert created.status_code == 201
    assert created.json()["status"] == "draft"
    approved = client.post(
        f"/api/v1/transactions/templates/{created.json()['id']}/approve", headers=HEADERS
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


def test_signwell_connection_registers_and_persists_verified_webhook(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "signwell")
    monkeypatch.setenv("ESIGN_API_KEY", "test-signwell-api-key")
    monkeypatch.setenv(
        "ESIGN_WEBHOOK_CALLBACK_URL",
        "https://api.example.com/api/v1/webhooks/esign/signwell",
    )
    monkeypatch.delenv("ESIGN_SIGNWELL_WEBHOOK_ID", raising=False)
    get_settings.cache_clear()
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        del kwargs
        request = httpx.Request("GET", url)
        if url.endswith("/me"):
            return httpx.Response(
                200,
                request=request,
                json={"id": "account-1", "name": "Stonegate", "email": OWNER_EMAIL},
            )
        if url.endswith("/hooks"):
            return httpx.Response(200, request=request, json=[])
        raise AssertionError(f"Unexpected SignWell GET {url}")

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        assert url.endswith("/hooks")
        assert kwargs["json"] == {
            "callback_url": "https://api.example.com/api/v1/webhooks/esign/signwell"
        }
        return httpx.Response(
            201,
            request=httpx.Request("POST", url),
            json={
                "id": "stonegate-webhook-id",
                "callback_url": "https://api.example.com/api/v1/webhooks/esign/signwell",
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    client = TestClient(app)
    connected = client.post(
        "/api/v1/transactions/integrations/signwell/connect",
        headers=HEADERS,
    )
    assert connected.status_code == 200, connected.text
    assert connected.json()["account_email"] == OWNER_EMAIL
    assert connected.json()["webhook_created"] is True

    status_response = client.get("/api/v1/transactions/integrations/f4", headers=HEADERS)
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["esign_configured"] is True
    assert status_payload["esign_webhook_connected"] is True
    assert status_payload["esign_account_email"] == OWNER_EMAIL

    event_type = "document_sent"
    event_time = 1786698000
    event = {
        "event": {
            "hash": hmac.new(
                b"stonegate-webhook-id",
                f"{event_type}@{event_time}".encode(),
                sha256,
            ).hexdigest(),
            "time": event_time,
            "type": event_type,
        },
        "data": {"object": {"id": str(uuid4()), "status": "sent"}},
    }
    webhook = client.post("/api/v1/webhooks/esign/signwell", json=event)
    assert webhook.status_code == 200, webhook.text
    assert webhook.json() == {"received": True, "matched": False}
    get_settings.cache_clear()


def test_transaction_document_facts_preserve_page_evidence_and_reject_duplicates(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id = setup_transaction(db_session, client)
    path = (
        f"/api/v1/transactions/{transaction_id}/documents"
        "?file_name=contract.pdf"
        "&document_type=signed_purchase_agreement"
        "&title=Executed%20agreement"
        "&document_status=executed"
    )
    content = b"%PDF unique executed agreement"
    uploaded = client.post(
        path,
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=content,
    )
    assert uploaded.status_code == 201, uploaded.text
    duplicate = client.post(
        path,
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=content,
    )
    assert duplicate.status_code == 422
    assert "already stored" in duplicate.json()["detail"]

    fact = client.post(
        (f"/api/v1/transactions/{transaction_id}/documents/{uploaded.json()['id']}/facts"),
        headers=HEADERS,
        json={
            "field_key": "Closing Date",
            "value_text": "August 14, 2026",
            "source_page": 4,
            "source_excerpt": "Closing shall occur on August 14, 2026.",
        },
    )
    assert fact.status_code == 201, fact.text
    assert fact.json()["field_key"] == "closing_date"
    assert fact.json()["status"] == "confirmed"
    assert fact.json()["source_page"] == 4

    detail = client.get(
        f"/api/v1/transactions/{transaction_id}",
        headers=HEADERS,
    )
    stored_document = next(
        item for item in detail.json()["documents"] if item["id"] == uploaded.json()["id"]
    )
    assert stored_document["facts"][0]["value_text"] == "August 14, 2026"
    assert stored_document["facts"][0]["reviewed_by_name"] == "Owner"


def test_f4_simulated_esign_completion_stores_provider_pdf_and_executes_package(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "simulate")
    monkeypatch.setenv("ESIGN_SIGNWELL_WEBHOOK_ID", "test-signwell-webhook-id")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    client = TestClient(app)
    lead_id, transaction_id = setup_transaction(db_session, client)

    package = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages",
        headers=HEADERS,
        json={
            "document_type": "purchase_agreement",
            "seller_name": "Jane Seller",
            "buyer_entity_name": "Stonegate Acquisitions LLC",
            "purchase_price_cents": 17000000,
            "earnest_money_cents": 100000,
            "closing_date": "2026-08-14T21:00:00Z",
            "inspection_period_days": 7,
        },
    )
    package_id = package.json()["id"]
    preview = client.get(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/preview",
        headers=HEADERS,
    )
    assert preview.status_code == 200, preview.text
    assert preview.headers["content-type"] == "application/pdf"
    assert b"{{signature:1:y::::180:35}}" in pdf_page_streams(preview.content)
    pending = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/request-approval",
        headers=HEADERS,
    )
    client.patch(
        f"/api/v1/approvals/{pending.json()['approval_request_id']}/decision",
        headers=HEADERS,
        json={"status": "approved", "decision_notes": "Terms verified."},
    )
    sent = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/esign",
        headers=HEADERS,
        json={
            "subject": "Stonegate purchase agreement",
            "message": "Please review and sign the approved agreement.",
            "recipients": [
                {
                    "placeholder_name": "Seller",
                    "name": "Jane Seller",
                    "email": "jane@example.com",
                    "signing_order": 1,
                }
            ],
        },
    )
    assert sent.status_code == 201, sent.text
    envelope = sent.json()
    assert envelope["status"] == "sent"
    assert envelope["delivery_mode"] == "email"
    assert envelope["embedded_signers"] == []
    assert envelope["test_mode"] is True
    generated_detail = client.get(
        f"/api/v1/transactions/{transaction_id}",
        headers=HEADERS,
    ).json()
    signing_copy = next(
        item
        for item in generated_detail["documents"]
        if item["document_type"] == "purchase_agreement_for_signature"
    )
    signing_pdf = client.get(signing_copy["download_url"], headers=HEADERS)
    assert signing_pdf.content.startswith(b"%PDF")
    signing_text = pdf_page_streams(signing_pdf.content)
    assert b"{{signature:1:y::::180:35}}" in signing_text
    assert b"{{signature:2:y::::180:35}}" in signing_text
    assert b"{{autofill_date_signed:1:y::::90:30}}" in signing_text
    wrong_transaction = client.post(
        f"/api/v1/transactions/{uuid4()}/esign/{envelope['id']}/reconcile",
        headers=HEADERS,
    )
    assert wrong_transaction.status_code == 404
    completed_pdf = b"%PDF SignWell completed agreement with audit page"
    event_type = "document_completed"
    event_time = 1786698000
    event = {
        "event": {
            "hash": hmac.new(
                b"test-signwell-webhook-id",
                f"{event_type}@{event_time}".encode(),
                sha256,
            ).hexdigest(),
            "time": event_time,
            "type": event_type,
        },
        "data": {
            "object": {
                "id": envelope["provider_document_id"],
                "status": "completed",
                "completed_pdf_base64": base64.b64encode(completed_pdf).decode(),
            }
        },
    }
    completed = client.post(
        "/api/v1/webhooks/esign/signwell",
        json=event,
    )
    duplicate = client.post(
        "/api/v1/webhooks/esign/signwell",
        json=event,
    )
    assert completed.status_code == 200, completed.text
    assert duplicate.status_code == 200
    detail = client.get(
        f"/api/v1/transactions/{transaction_id}",
        headers=HEADERS,
    ).json()
    assert detail["contract_packages"][0]["status"] == "executed"
    assert detail["esign_envelopes"][0]["status"] == "completed"
    signed_document = next(
        item for item in detail["documents"] if item["document_type"] == "signed_purchase_agreement"
    )
    assert signed_document["storage_provider"] == "database"
    assert signed_document["malware_scan_status"] == "not_configured"
    download = client.get(
        signed_document["download_url"],
        headers=HEADERS,
    )
    assert download.content == completed_pdf
    assert client.get(f"/api/v1/leads/{lead_id}", headers=HEADERS).json()["stage_key"] == (
        "under_contract"
    )

    assignment_package = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages",
        headers=HEADERS,
        json={
            "document_type": "assignment_contract",
            "seller_name": "Jane Seller",
            "buyer_entity_name": "Stonegate Acquisitions LLC",
            "purchase_price_cents": 17000000,
            "earnest_money_cents": 100000,
            "closing_date": "2026-08-14T21:00:00Z",
            "inspection_period_days": 7,
        },
    )
    assignment_package_id = assignment_package.json()["id"]
    assignment_pending = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{assignment_package_id}/request-approval",
        headers=HEADERS,
    )
    client.patch(
        f"/api/v1/approvals/{assignment_pending.json()['approval_request_id']}/decision",
        headers=HEADERS,
        json={"status": "approved", "decision_notes": "Assignment terms verified."},
    )
    assignment_sent = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{assignment_package_id}/esign",
        headers=HEADERS,
        json={
            "subject": "Stonegate assignment agreement",
            "recipients": [
                {
                    "placeholder_name": "Assignee",
                    "name": "Ready Cash Buyer LLC",
                    "email": "buyer@example.com",
                    "signing_order": 1,
                }
            ],
        },
    )
    assert assignment_sent.status_code == 201, assignment_sent.text
    assignment_event_time = event_time + 1
    assignment_event = {
        "event": {
            "hash": hmac.new(
                b"test-signwell-webhook-id",
                f"{event_type}@{assignment_event_time}".encode(),
                sha256,
            ).hexdigest(),
            "time": assignment_event_time,
            "type": event_type,
        },
        "data": {
            "object": {
                "id": assignment_sent.json()["provider_document_id"],
                "status": "completed",
                "completed_pdf_base64": base64.b64encode(
                    b"%PDF SignWell completed assignment agreement"
                ).decode(),
            }
        },
    }
    assert client.post("/api/v1/webhooks/esign/signwell", json=assignment_event).status_code == 200
    assignment_detail = client.get(
        f"/api/v1/transactions/{transaction_id}",
        headers=HEADERS,
    ).json()
    stored_assignment = next(
        item
        for item in assignment_detail["documents"]
        if item["contract_package_id"] == assignment_package_id
    )
    assert stored_assignment["document_type"] == "assignment_contract"
    assert "assignment agreement" in stored_assignment["title"].lower()
    get_settings.cache_clear()
