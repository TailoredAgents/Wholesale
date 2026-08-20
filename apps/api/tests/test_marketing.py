import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
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
    AttributionTouch,
    AuditEvent,
    ConversionEvent,
    Deal,
    Lead,
    MarketingSpend,
    OfflineConversionExport,
    Organization,
    RevenueRecord,
    Transaction,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.marketing import (
    build_meta_match_coverage,
    process_next_marketing_conversion,
)
from app.services.operations import register_worker, safe_meta_runtime_metadata

OWNER_EMAIL = "owner@example.com"


class FailingConversionClient(MarketingConversionClient):
    def __init__(self) -> None:
        pass

    def deliver(self, export: OfflineConversionExport) -> ConversionDeliveryResult:
        raise ConversionDeliveryError("Provider temporarily unavailable.")


def meta_delivery_export() -> OfflineConversionExport:
    occurred_at = datetime(2026, 8, 16, 12, 30, tzinfo=UTC)
    return OfflineConversionExport(
        organization_id=uuid4(),
        platform="meta",
        conversion_event_id=None,
        lead_id=None,
        revenue_record_id=None,
        event_key="meta-delivery-test-event",
        source_record_type="conversion_event",
        source_record_id=uuid4(),
        event_name="ViewContent",
        occurred_at=occurred_at,
        attribution_model="meta_browser_server_deduplicated_v1",
        consent_basis="website_contact_and_measurement_notice_v1",
        click_id="fb.1.1786878000000.click-id",
        click_id_type="meta_browser",
        value_cents=None,
        currency="USD",
        payload_hash="0" * 64,
        payload_snapshot={
            "landing_page": "https://www.stonegatehb.com/get-a-cash-offer",
            "client_ip_address": "203.0.113.10",
            "client_user_agent": "pytest",
            "fbc": "fb.1.1786878000000.click-id",
            "fbp": "fb.1.1786878000000.browser-id",
            "email_hashes": [],
            "external_id_hash": None,
        },
        delivery_mode="live",
        status="pending",
        attempt_count=0,
        exported_at=None,
        last_error=None,
    )


def live_meta_settings(*, access_token: str = "meta-token") -> Settings:
    return Settings.model_validate(
        {
            "MARKETING_CONVERSION_MODE": "live",
            "META_CONVERSIONS_ACCESS_TOKEN": access_token,
            "META_PIXEL_ID": "meta-pixel",
        }
    )


def test_meta_match_coverage_reports_contact_events_separately() -> None:
    contact_export = meta_delivery_export()
    contact_export.event_name = "Contact"

    coverage = build_meta_match_coverage([contact_export])

    contact = next(row for row in coverage if row.event_name == "Contact")
    lead = next(row for row in coverage if row.event_name == "Lead")
    assert contact.total == 1
    assert contact.fbp_basis_points == 10_000
    assert contact.fbc_basis_points == 10_000
    assert lead.total == 0
    assert lead.fbp_basis_points is None


def test_meta_delivery_requires_explicit_single_event_acceptance() -> None:
    observed_request: httpx.Request | None = None

    def accepted_handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_request
        observed_request = request
        return httpx.Response(
            200,
            json={"events_received": 1, "messages": [], "fbtrace_id": "trace-123"},
        )

    transport = httpx.MockTransport(accepted_handler)
    client = MarketingConversionClient(
        live_meta_settings(),
        httpx.Client(transport=transport),
    )

    result = client.deliver(meta_delivery_export())

    assert result.request_id == "trace-123"
    assert result.response["events_received"] == 1
    assert result.response["stonegate_delivery"] == {
        "accepted_count": 1,
        "warning_count": 0,
        "test_mode_enabled": False,
    }
    assert observed_request is not None
    assert "access_token" not in str(observed_request.url)
    assert observed_request.headers["Authorization"] == "Bearer meta-token"


def test_meta_fbc_fallback_uses_only_the_original_click_timestamp() -> None:
    export = meta_delivery_export()
    export.payload_snapshot = {
        **export.payload_snapshot,
        "fbc": None,
        "fbclid": "original-click-id",
        "click_captured_at": "2026-08-01T12:00:00Z",
    }

    payload = build_meta_payload(export, live_meta_settings())

    assert payload["data"][0]["user_data"]["fbc"] == ("fb.1.1785585600000.original-click-id")

    export.payload_snapshot = {**export.payload_snapshot, "click_captured_at": None}
    payload_without_original_time = build_meta_payload(export, live_meta_settings())
    assert "fbc" not in payload_without_original_time["data"][0]["user_data"]


@pytest.mark.parametrize(
    "response_body",
    [
        {},
        {"events_received": 0},
        {"events_received": "1"},
        {"events_received": True},
        {"events_received": 2},
    ],
)
def test_meta_delivery_rejects_missing_zero_malformed_or_multiple_acceptance(
    response_body: dict[str, object],
) -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=response_body))
    client = MarketingConversionClient(
        live_meta_settings(),
        httpx.Client(transport=transport),
    )

    with pytest.raises(ConversionDeliveryError) as exc_info:
        client.deliver(meta_delivery_export())

    assert "exactly one event" in str(exc_info.value)
    assert exc_info.value.response is not None


def test_meta_delivery_error_never_serializes_access_token() -> None:
    sentinel_token = "SENTINEL-META-TOKEN-MUST-NOT-LEAK"
    observed_url = ""

    def rejected_handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_url
        observed_url = str(request.url)
        return httpx.Response(503, text="provider unavailable")

    client = MarketingConversionClient(
        live_meta_settings(access_token=sentinel_token),
        httpx.Client(transport=httpx.MockTransport(rejected_handler)),
    )

    with pytest.raises(ConversionDeliveryError) as exc_info:
        client.deliver(meta_delivery_export())

    serialized = json.dumps(exc_info.value.response, sort_keys=True)
    assert sentinel_token not in observed_url
    assert sentinel_token not in str(exc_info.value)
    assert sentinel_token not in serialized


def test_unconfirmed_meta_acceptance_retries_and_dashboard_stays_safe(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    response = TestClient(app).post(
        "/api/v1/public/conversion-events",
        json={
            "event_type": "page_view",
            "attribution": {"landing_page": "/get-a-cash-offer"},
            "meta_browser_event": {
                "event_id": "unconfirmed-meta-event",
                "event_source_url": "https://www.stonegatehb.com/get-a-cash-offer",
                "fbp": "fb.1.1786878000000.browser-id",
            },
        },
    )
    assert response.status_code == 201
    sentinel_token = "SENTINEL-RETRY-TOKEN-MUST-NOT-LEAK"
    settings = live_meta_settings(access_token=sentinel_token)
    register_worker(
        db_session,
        runtime_metadata=safe_meta_runtime_metadata(settings),
    )
    provider_client = MarketingConversionClient(
        settings,
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    json={
                        "events_received": 0,
                        "messages": [{"code": 100, "message": "No event accepted."}],
                        "fbtrace_id": "trace-unconfirmed",
                    },
                )
            )
        ),
    )

    processed_id = process_next_marketing_conversion(
        db_session,
        settings,
        provider_client,
    )

    assert processed_id is not None
    export = db_session.get(OfflineConversionExport, processed_id)
    assert export is not None
    assert export.status == "retry"
    assert export.provider_response is not None
    assert export.provider_response["events_received"] == 0
    assert export.provider_request_id == "trace-unconfirmed"
    assert export.last_error is not None
    audit = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.entity_id == export.id)
        .order_by(AuditEvent.created_at.desc())
    )
    assert audit is not None
    dashboard = TestClient(app).get(
        "/api/v1/marketing",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert dashboard.status_code == 200
    payload = dashboard.json()
    exported = next(item for item in payload["offline_exports"] if item["id"] == str(export.id))
    assert exported["provider_accepted_count"] == 0
    assert exported["provider_warnings"] == ["100: No event accepted."]
    measurement = payload["measurement"]
    assert measurement["worker"]["marketing_conversion_mode"] == "live"
    assert measurement["worker"]["meta_access_token_present"] is True
    assert measurement["worker"]["meta_pixel_id_fingerprint"]
    assert measurement["meta_match_coverage_window_days"] == 30
    overall_coverage = next(
        row for row in measurement["meta_match_coverage"] if row["event_name"] == "all"
    )
    contact_coverage = next(
        row for row in measurement["meta_match_coverage"] if row["event_name"] == "Contact"
    )
    assert overall_coverage["total"] == 1
    assert overall_coverage["fbp_basis_points"] == 10000
    assert overall_coverage["fbc_basis_points"] == 0
    assert overall_coverage["client_ip_basis_points"] == 0
    assert contact_coverage["total"] == 0
    assert contact_coverage["fbp_basis_points"] is None
    assert measurement["oldest_meta_pending_at"] is not None
    serialized = json.dumps(
        {
            "error": export.last_error,
            "response": export.provider_response,
            "audit": audit.new_value,
            "dashboard": payload,
        },
        sort_keys=True,
        default=str,
    )
    assert sentinel_token not in serialized

    # A later network failure has no provider request ID. Keep the last known trace
    # instead of erasing the evidence captured on the prior provider response.
    export.next_attempt_at = None
    db_session.commit()
    retried_id = process_next_marketing_conversion(
        db_session,
        settings,
        FailingConversionClient(),
    )
    assert retried_id == export.id
    db_session.refresh(export)
    assert export.provider_request_id == "trace-unconfirmed"


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
    lead = db_session.get(Lead, UUID(lead_id))
    assert lead is not None
    original_touch_created_at = db_session.scalar(
        select(AttributionTouch.created_at)
        .where(
            AttributionTouch.lead_id == lead.id,
            AttributionTouch.touch_type == "lead_creation",
        )
        .order_by(AttributionTouch.created_at.asc(), AttributionTouch.id.asc())
        .limit(1)
    )
    assert original_touch_created_at is not None
    db_session.add(
        AttributionTouch(
            organization_id=lead.organization_id,
            lead_id=lead.id,
            touch_type="lead_creation",
            source="duplicate_source",
            medium="duplicate_medium",
            campaign="duplicate_campaign",
            landing_page="/duplicate",
            created_at=original_touch_created_at + timedelta(seconds=1),
        )
    )
    db_session.commit()
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
    assert google_row["address_leads"] == 0
    assert google_row["contact_completed_leads"] == 0
    assert google_row["address_to_contact_rate_basis_points"] is None
    assert google_row["cost_per_address_lead_cents"] is None
    assert google_row["cost_per_contact_completed_lead_cents"] is None
    assert google_row["collected_revenue_cents"] == 2500000
    assert sum(row["leads_created"] for row in overview["campaigns"]) == 1
    assert sum(row["collected_revenue_cents"] for row in overview["campaigns"]) == 2500000
    assert overview["public_funnel"]["offer_starts"] == 1
    assert overview["public_funnel"]["form_starts"] == 1
    assert overview["public_funnel"]["step_completions"] == {"property": 1}
    assert overview["public_funnel"]["validation_errors"] == 1
    assert overview["public_funnel"]["submit_attempts"] == 1
    assert overview["public_funnel"]["form_submits"] == 1
    assert overview["public_funnel"]["address_leads"] == 0
    assert overview["public_funnel"]["contact_completed_leads"] == 0
    assert overview["public_funnel"]["address_to_contact_rate_basis_points"] is None
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
    assert (
        int(db_session.scalar(select(func.count()).select_from(OfflineConversionExport)) or 0) == 1
    )
    export = db_session.scalar(select(OfflineConversionExport))
    assert export is not None
    assert export.platform == "google_ads"
    assert export.click_id == "test-gclid-123"
    assert export.value_cents == 2500000
    assert export.event_name == "funded_deal"
    assert export.payload_snapshot["landing_page"] == "https://www.stonegatehb.com/get-a-cash-offer"
    assert export.payload_snapshot["phone_hashes"]
    assert "4045551212" not in str(export.payload_snapshot)
    measurement = updated_overview_response.json()["measurement"]
    assert measurement["mode"] == "disabled"
    assert measurement["event_counts"]["event:funded_deal"] == 1
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "marketing.offline_exports_generate")
            )
            or 0
        )
        == 1
    )


def test_marketing_funnel_separates_address_and_contact_cpl_without_duplicating_spend(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    organization = db_session.scalar(select(Organization))
    assert organization is not None
    common = {
        "organization_id": organization.id,
        "landing_page": "/get-a-cash-offer",
        "source": "meta_ads",
        "campaign": "georgia-sellers",
        "device_category": "mobile",
    }
    db_session.add_all(
        [
            ConversionEvent(
                **common,
                medium="paid_social",
                event_type="address_capture",
                session_id="address-session-1",
            ),
            ConversionEvent(
                **common,
                medium="paid_social",
                event_type="address_capture",
                session_id="address-session-2",
            ),
            ConversionEvent(
                **common,
                medium="paid_social",
                event_type="contact_complete",
                session_id="address-session-1",
            ),
            ConversionEvent(
                **common,
                medium="social",
                event_type="page_view",
                session_id="page-session",
            ),
            MarketingSpend(
                organization_id=organization.id,
                source="meta_ads",
                campaign="georgia-sellers",
                amount_cents=10_000,
                spend_month_at=datetime.now(UTC),
            ),
        ]
    )
    db_session.commit()

    response = TestClient(app).get(
        "/api/v1/marketing",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert response.status_code == 200
    overview = response.json()
    matching_rows = [
        row
        for row in overview["campaigns"]
        if row["source"] == "meta_ads" and row["campaign"] == "georgia-sellers"
    ]
    assert len(matching_rows) == 1
    campaign = matching_rows[0]
    assert campaign["medium"] == "mixed"
    assert campaign["page_views"] == 1
    assert campaign["address_leads"] == 2
    assert campaign["contact_completed_leads"] == 1
    assert campaign["form_submits"] == 1
    assert campaign["marketing_spend_cents"] == 10_000
    assert campaign["cost_per_address_lead_cents"] == 5_000
    assert campaign["cost_per_contact_completed_lead_cents"] == 10_000
    assert campaign["address_to_contact_rate_basis_points"] == 5_000
    assert overview["summary"]["total_spend_cents"] == 10_000
    assert overview["summary"]["address_leads"] == 2
    assert overview["summary"]["contact_completed_leads"] == 1
    assert overview["summary"]["cost_per_address_lead_cents"] == 5_000
    assert overview["summary"]["cost_per_contact_completed_lead_cents"] == 10_000
    assert overview["summary"]["address_to_contact_rate_basis_points"] == 5_000
    assert overview["public_funnel"]["address_leads"] == 2
    assert overview["public_funnel"]["contact_completed_leads"] == 1
    assert overview["public_funnel"]["address_to_contact_rate_basis_points"] == 5_000


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
                "fbclid_captured_at": "2026-08-01T12:00:00Z",
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
    meta_export = next(
        item for item in exports if item.platform == "meta" and item.event_name == "qualified_lead"
    )
    google_payload = build_google_payload(google_export, live_settings)
    meta_payload = build_meta_payload(meta_export, live_settings)
    assert google_payload["events"][0]["transactionId"] == google_export.event_key
    assert google_payload["events"][0]["adIdentifiers"]["gclid"] == "google-click-456"
    assert meta_payload["data"][0]["event_id"] == meta_export.event_key
    assert meta_payload["data"][0]["event_name"] == "QualifiedLead"
    assert meta_payload["data"][0]["user_data"]["fbc"].endswith("meta-click-456")
    assert meta_payload["data"][0]["user_data"]["client_user_agent"]
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


def test_scheduling_a_lead_automatically_queues_meta_schedule(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    intake = client.post(
        "/api/v1/public/seller-leads",
        json={
            "property_address": "789 Edgewood Ave",
            "property_city": "Atlanta",
            "property_state": "GA",
            "property_postal_code": "30307",
            "name": "Taylor Seller",
            "phone": "4045550188",
            "email": "taylor@example.com",
            "preferred_contact_method": "email",
            "consent_to_contact": True,
            "attribution": {
                "landing_page": "/get-a-cash-offer",
                "utm_source": "meta_ads",
                "utm_medium": "paid_social",
                "fbclid": "schedule-click-789",
            },
        },
    )
    assert intake.status_code == 201

    response = client.post(
        f"/api/v1/leads/{intake.json()['lead_id']}/appointments",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "appointment_type": "walkthrough",
            "status": "scheduled",
            "scheduled_start_at": "2026-08-10T15:00:00Z",
            "scheduled_end_at": "2026-08-10T16:00:00Z",
            "location_type": "property",
        },
    )

    assert response.status_code == 201
    export = db_session.scalar(select(OfflineConversionExport))
    assert export is not None
    assert export.platform == "meta"
    assert export.event_name == "appointment_scheduled"
    assert export.click_id == "schedule-click-789"
    assert export.status == "pending"
    meta_payload = build_meta_payload(export, Settings())
    assert meta_payload["data"][0]["event_name"] == "Schedule"
    assert meta_payload["data"][0]["user_data"]["client_user_agent"]
