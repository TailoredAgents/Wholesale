import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.marketing_conversions import (
    ConversionDeliveryError,
    ConversionDeliveryResult,
    MarketingConversionClient,
    build_google_payload,
    build_meta_payload,
)
from app.main import app
from app.models.foundation import (
    Appointment,
    AuditEvent,
    ConversionEvent,
    Deal,
    Lead,
    MarketingSpend,
    OfflineConversionExport,
    RevenueRecord,
    Transaction,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.marketing import process_next_marketing_conversion

OWNER_EMAIL = "owner@example.com"


class FailingConversionClient(MarketingConversionClient):
    def __init__(self) -> None:
        pass

    def deliver(self, export: OfflineConversionExport) -> ConversionDeliveryResult:
        raise ConversionDeliveryError("Provider temporarily unavailable.")


def seed_owner(db_session: Session) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )


def test_marketing_overview_and_offline_export_generation(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    intake_response = client.post(
        "/api/v1/public/seller-leads",
        json={
            "property_address": "123 Peachtree St",
            "property_city": "Atlanta",
            "property_state": "GA",
            "property_postal_code": "30303",
            "name": "Jane Seller",
            "phone": "4045551212",
            "preferred_contact_method": "phone",
            "consent_to_contact": True,
            "attribution": {
                "landing_page": "/get-a-cash-offer",
                "utm_source": "google_ppc",
                "utm_medium": "cpc",
                "utm_campaign": "atlanta-cash-offer",
                "gclid": "test-gclid-123",
            },
        },
    )
    lead_id = intake_response.json()["lead_id"]
    spend_response = client.post(
        "/api/v1/finance/marketing-spend",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "source": "google_ppc",
            "campaign": "atlanta-cash-offer",
            "amount_cents": 500000,
        },
    )
    revenue_response = client.post(
        "/api/v1/finance/revenue",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "lead_id": lead_id,
            "source": "assignment_fee",
            "status": "collected",
            "amount_cents": 2500000,
        },
    )
    for event_type, metadata in (
        ("offer_start", {"entry_point": "homepage_hero"}),
        ("form_start", {"starting_step": 1}),
        ("form_step_complete", {"step_key": "property", "step_number": 1}),
        ("form_validation_error", {"step_key": "contact", "fields": ["phone"]}),
        ("form_submit_attempt", {"completed_steps": 4}),
        ("web_vital", {"metric": "LCP", "value": 2200.0, "rating": "good"}),
        ("web_vital", {"metric": "LCP", "value": 2800.0, "rating": "needs-improvement"}),
    ):
        event_response = client.post(
            "/api/v1/public/conversion-events",
            json={
                "event_type": event_type,
                "session_id": "marketing-session",
                "metadata": metadata,
            },
        )
        assert event_response.status_code == 201

    overview_response = client.get(
        "/api/v1/marketing",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    generate_response = client.post(
        "/api/v1/marketing/offline-conversions/generate",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    duplicate_generate_response = client.post(
        "/api/v1/marketing/offline-conversions/generate",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    updated_overview_response = client.get(
        "/api/v1/marketing",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert intake_response.status_code == 201
    assert spend_response.status_code == 201
    assert revenue_response.status_code == 201
    assert overview_response.status_code == 200
    overview = overview_response.json()
    google_row = next(row for row in overview["campaigns"] if row["source"] == "google_ppc")
    assert google_row["leads_created"] == 1
    assert google_row["form_submits"] == 1
    assert google_row["collected_revenue_cents"] == 2500000
    assert overview["public_funnel"]["offer_starts"] == 1
    assert overview["public_funnel"]["form_starts"] == 1
    assert overview["public_funnel"]["step_completions"] == {"property": 1}
    assert overview["public_funnel"]["validation_errors"] == 1
    assert overview["public_funnel"]["submit_attempts"] == 1
    assert overview["public_funnel"]["form_submits"] == 1
    assert overview["public_funnel"]["start_to_submit_rate_basis_points"] == 10000
    assert overview["web_vitals"] == [
        {
            "metric": "LCP",
            "sample_count": 2,
            "p75_value": 2800.0,
            "good_rate_basis_points": 5000,
        }
    ]

    prior_period_at = datetime.now(UTC) - timedelta(days=45)
    for event in db_session.scalars(select(ConversionEvent)).all():
        event.created_at = prior_period_at
    for lead in db_session.scalars(select(Lead)).all():
        lead.created_at = prior_period_at
    for revenue in db_session.scalars(select(RevenueRecord)).all():
        revenue.received_at = prior_period_at
    for spend in db_session.scalars(select(MarketingSpend)).all():
        spend.spend_month_at = prior_period_at
    db_session.commit()

    period_response = client.get(
        "/api/v1/marketing?period_days=30",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert period_response.status_code == 200
    period = period_response.json()
    assert period["period_days"] == 30
    assert period["summary"]["leads_created"] == 0
    assert period["summary"]["collected_revenue_cents"] == 0
    assert period["previous_summary"]["leads_created"] == 1
    assert period["previous_summary"]["collected_revenue_cents"] == 2500000
    assert period["campaigns"] == []
    assert generate_response.status_code == 201
    assert generate_response.json() == {"created": 1}
    assert duplicate_generate_response.status_code == 201
    assert duplicate_generate_response.json() == {"created": 0}
    assert updated_overview_response.json()["summary"]["pending_offline_exports"] == 1
    assert int(
        db_session.scalar(select(func.count()).select_from(OfflineConversionExport)) or 0
    ) == 1
    export = db_session.scalar(select(OfflineConversionExport))
    assert export is not None
    assert export.platform == "google_ads"
    assert export.click_id == "test-gclid-123"
    assert export.value_cents == 2500000
    assert export.event_name == "funded_deal"
    assert (
        export.payload_snapshot["landing_page"]
        == "https://www.stonegatehb.com/get-a-cash-offer"
    )
    assert export.payload_snapshot["phone_hashes"]
    assert "4045551212" not in str(export.payload_snapshot)
    measurement = updated_overview_response.json()["measurement"]
    assert measurement["mode"] == "disabled"
    assert measurement["event_counts"]["event:funded_deal"] == 1
    assert int(
        db_session.scalar(
            select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action == "marketing.offline_exports_generate"
            )
        )
        or 0
    ) == 1


def test_conversion_queue_covers_each_outcome_and_platform(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    intake = client.post(
        "/api/v1/public/seller-leads",
        json={
            "property_address": "456 Piedmont Ave",
            "property_city": "Atlanta",
            "property_state": "GA",
            "property_postal_code": "30308",
            "name": "Alex Seller",
            "phone": "4045558989",
            "email": "alex.seller@example.com",
            "preferred_contact_method": "phone",
            "consent_to_contact": True,
            "attribution": {
                "landing_page": "/get-a-cash-offer",
                "utm_source": "paid_social",
                "utm_medium": "cpc",
                "utm_campaign": "atlanta-sellers",
                "gclid": "google-click-456",
                "fbclid": "meta-click-456",
            },
        },
    )
    assert intake.status_code == 201
    lead = db_session.get(Lead, UUID(intake.json()["lead_id"]))
    assert lead is not None
    lead.stage_key = "qualified"
    db_session.flush()
    appointment = Appointment(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        property_id=lead.property_id,
        owner_user_id=None,
        appointment_type="seller",
        status="scheduled",
        scheduled_start_at=datetime.now(UTC) + timedelta(days=1),
        scheduled_end_at=None,
        location_type="property",
        location=None,
        notes=None,
        outcome=None,
        external_calendar_id=None,
        appointment_metadata=None,
    )
    db_session.add(appointment)
    deal = Deal(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        property_id=lead.property_id,
        stage_key="under_contract",
        contract_price_cents=15000000,
        assignment_fee_cents=2000000,
    )
    db_session.add(deal)
    db_session.flush()
    transaction = Transaction(
        organization_id=lead.organization_id,
        deal_id=deal.id,
        lead_id=lead.id,
        property_id=lead.property_id,
        contact_id=lead.contact_id,
        owner_user_id=None,
        coordinator_user_id=None,
        status="under_contract",
        contract_type="assignment",
        purchase_price_cents=15000000,
        assignment_fee_cents=2000000,
        earnest_money_cents=10000,
        contract_executed_at=datetime.now(UTC),
    )
    db_session.add(transaction)
    revenue = RevenueRecord(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        deal_id=deal.id,
        transaction_id=None,
        source="assignment_fee",
        status="collected",
        amount_cents=2000000,
        received_at=datetime.now(UTC),
        notes=None,
    )
    db_session.add(revenue)
    db_session.commit()

    response = client.post(
        "/api/v1/marketing/offline-conversions/generate",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    duplicate = client.post(
        "/api/v1/marketing/offline-conversions/generate",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert response.status_code == 201
    assert response.json() == {"created": 8}
    assert duplicate.json() == {"created": 0}
    exports = db_session.scalars(select(OfflineConversionExport)).all()
    assert {(item.event_name, item.platform) for item in exports} == {
        (event_name, platform)
        for event_name in {
            "qualified_lead",
            "appointment_scheduled",
            "contract_signed",
            "funded_deal",
        }
        for platform in {"google_ads", "meta"}
    }
    assert len({item.event_key for item in exports}) == 8
    assert all("alex.seller@example.com" not in str(item.payload_snapshot) for item in exports)
    assert all("4045558989" not in str(item.payload_snapshot) for item in exports)

    processed_id = process_next_marketing_conversion(
        db_session,
        Settings.model_validate({"MARKETING_CONVERSION_MODE": "simulate"}),
    )
    assert processed_id is not None
    processed = db_session.get(OfflineConversionExport, processed_id)
    assert processed is not None
    assert processed.status == "simulated"
    assert processed.attempt_count == 1
    assert processed.provider_response == {
        "simulated": True,
        "external_request_sent": False,
    }

    live_settings = Settings.model_validate(
        {
            "MARKETING_CONVERSION_MODE": "live",
            "GOOGLE_DATA_MANAGER_CLIENT_ID": "google-client",
            "GOOGLE_DATA_MANAGER_CLIENT_SECRET": "google-secret",
            "GOOGLE_DATA_MANAGER_REFRESH_TOKEN": "google-refresh",
            "GOOGLE_DATA_MANAGER_OPERATING_ACCOUNT_ID": "1234567890",
            "GOOGLE_DATA_MANAGER_CONVERSION_ACTIONS_JSON": json.dumps(
                {
                    "qualified_lead": "1001",
                    "appointment_scheduled": "1002",
                    "contract_signed": "1003",
                    "funded_deal": "1004",
                }
            ),
            "META_CONVERSIONS_ACCESS_TOKEN": "meta-token",
            "META_PIXEL_ID": "meta-pixel",
        }
    )
    google_export = next(item for item in exports if item.platform == "google_ads")
    meta_export = next(item for item in exports if item.platform == "meta")
    google_payload = build_google_payload(google_export, live_settings)
    meta_payload = build_meta_payload(meta_export, live_settings)
    assert google_payload["events"][0]["transactionId"] == google_export.event_key
    assert google_payload["events"][0]["adIdentifiers"]["gclid"] == "google-click-456"
    assert meta_payload["data"][0]["event_id"] == meta_export.event_key
    assert meta_payload["data"][0]["user_data"]["fbc"].endswith("meta-click-456")
    assert "alex.seller@example.com" not in json.dumps(google_payload)
    assert "4045558989" not in json.dumps(meta_payload)

    failed_id = process_next_marketing_conversion(
        db_session,
        live_settings,
        FailingConversionClient(),
    )
    assert failed_id is not None
    failed = db_session.get(OfflineConversionExport, failed_id)
    assert failed is not None
    assert failed.status == "retry"
    assert failed.attempt_count == 1
    assert failed.next_attempt_at is not None
