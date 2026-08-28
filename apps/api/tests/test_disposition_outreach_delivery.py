from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import worker
from app.core.auth import principal_for_user
from app.core.config import Settings
from app.integrations.resend_email import ResendEmailError
from app.main import app
from app.models.foundation import (
    Buyer,
    CommunicationDispatch,
    CommunicationParticipant,
    CommunicationRecord,
    ConsentRecord,
    Conversation,
    ConversationContextLink,
    DispositionCampaign,
    DispositionCampaignRecipient,
    DispositionOutreachDelivery,
    DispositionOutreachRevision,
    DispositionPackageVersion,
    DispositionReplyLink,
    EmailSenderAlias,
    SuppressionRecord,
    Task,
    User,
    VoiceLine,
)
from app.schemas.disposition_outreach import DispositionOutreachControlRequest
from app.services import disposition_outreach, disposition_outreach_delivery
from app.services.inbox import ensure_buyer_conversation
from tests.test_disposition_outreach import (
    TEST_OUTREACH_POSTAL_ADDRESS,
    prepare_outreach_case,
)
from tests.test_dispositions import HEADERS, OWNER_EMAIL, setup_case_foundation


@dataclass(frozen=True)
class ApprovedOutreach:
    campaign: DispositionCampaign
    revision_id: UUID
    delivery_id: UUID


@pytest.fixture(autouse=True)
def _configure_test_outreach_postal_address(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        APP_ENV="test",
        DISPOSITION_OUTREACH_PHYSICAL_POSTAL_ADDRESS=TEST_OUTREACH_POSTAL_ADDRESS,
    )
    monkeypatch.setattr(disposition_outreach, "get_settings", lambda: settings)


def _simulation_settings(*, sms: bool = False) -> Settings:
    values: dict[str, object] = {
        "APP_ENV": "test",
        "COMMUNICATION_PROVIDER_MODE": "simulate",
        "DISPOSITION_OUTREACH_PHYSICAL_POSTAL_ADDRESS": TEST_OUTREACH_POSTAL_ADDRESS,
    }
    if sms:
        values.update(
            {
                "TWILIO_SMS_ENABLED": True,
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "test-auth-token",
                "TWILIO_SMS_FROM_NUMBER": "+14705550199",
                "TWILIO_WEBHOOK_BASE_URL": "https://api.example.test",
            }
        )
    return Settings(**values)


def _owner(db: Session) -> User:
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    return owner


def _approve_and_release_email(
    db: Session,
    client: TestClient,
) -> ApprovedOutreach:
    case_id, campaign, alias = prepare_outreach_case(db, client)
    workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/outreach",
        headers=HEADERS,
    )
    assert workspace.status_code == 200, workspace.text
    recipient_id = workspace.json()["prepared_recipients"][0]["id"]
    drafted = client.post(
        f"/api/v1/dispositions/cases/{case_id}/outreach/drafts",
        headers=HEADERS,
        json={
            "campaign_id": str(campaign.id),
            "recipients": [
                {"campaign_recipient_id": recipient_id, "channels": ["email"]}
            ],
            "email_sender_alias_id": str(alias.id),
            "email_subject": "Opportunity at {property_address}",
            "email_body": "Hi {buyer_name}, please review {package_reference}.",
        },
    )
    assert drafted.status_code == 201, drafted.text
    draft = drafted.json()
    approved = client.post(
        f"/api/v1/dispositions/campaigns/{campaign.id}/outreach/{draft['id']}/approve",
        headers=HEADERS,
        json={
            "expected_lock_version": draft["lock_version"],
            "expected_approval_hash": draft["approval_hash"],
            "attestation": True,
            "reason": "Reviewed exact recipient, sender, artifact, and copy.",
        },
    )
    assert approved.status_code == 200, approved.text
    revision_id = UUID(draft["id"])
    principal = principal_for_user(db, _owner(db))
    released = disposition_outreach.release_revision(
        db,
        principal,
        campaign.id,
        revision_id,
        DispositionOutreachControlRequest(
            expected_lock_version=approved.json()["lock_version"],
            reason="Release the approved simulation delivery.",
        ),
        settings=_simulation_settings(),
    )
    assert released is not None
    assert released.status == "queued"
    delivery = db.scalar(
        select(DispositionOutreachDelivery).where(
            DispositionOutreachDelivery.outreach_revision_id == revision_id
        )
    )
    assert delivery is not None and delivery.status == "queued"
    return ApprovedOutreach(campaign, revision_id, UUID(str(delivery.id)))


def _approve_and_release_sms(
    db: Session,
    client: TestClient,
) -> ApprovedOutreach:
    case_id, campaign, _alias = prepare_outreach_case(db, client)
    owner = _owner(db)
    recipient = db.scalar(
        select(DispositionCampaignRecipient).where(
            DispositionCampaignRecipient.disposition_campaign_id == campaign.id
        )
    )
    assert recipient is not None
    buyer = db.get(Buyer, recipient.buyer_id)
    assert buyer is not None
    buyer.phone = "+14045550123"
    buyer.normalized_phone = "+14045550123"
    recipient.captured_destination = {
        **(recipient.captured_destination or {}),
        "phone": "+14045550123",
    }
    line = VoiceLine(
        organization_id=owner.organization_id,
        assigned_user_id=owner.id,
        fallback_user_id=None,
        assigned_team_id=None,
        provider="twilio",
        provider_phone_number_id="PN-disposition-test",
        phone_number="+14705550199",
        label="Dispositions test line",
        department_key="dispositions",
        purpose_key="buyer_relations",
        status="active",
        is_default=True,
        inbound_route="conversation_owner",
        ring_strategy="everyone_at_once",
        coverage_timezone="America/New_York",
        coverage_start_hour=0,
        coverage_end_hour=24,
        prospecting_dialer_max_concurrent_legs=1,
        missed_call_action="fallback_then_voicemail",
        line_metadata={"test": True},
    )
    db.add(line)
    db.flush()
    conversation = ensure_buyer_conversation(db, buyer, actor_user_id=owner.id)
    db.add(
        ConsentRecord(
            organization_id=owner.organization_id,
            contact_id=conversation.contact_id,
            channel="sms",
            status="granted",
            source="buyer_written_consent",
            wording_version="test-v1",
            wording="Buyer granted permission to receive this message.",
            normalized_address="+14045550123",
            captured_ip=None,
            user_agent=None,
        )
    )
    db.commit()

    workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/outreach",
        headers=HEADERS,
    )
    assert workspace.status_code == 200, workspace.text
    prepared = workspace.json()["prepared_recipients"][0]
    assert "sms" in prepared["available_channels"]
    drafted = client.post(
        f"/api/v1/dispositions/cases/{case_id}/outreach/drafts",
        headers=HEADERS,
        json={
            "campaign_id": str(campaign.id),
            "recipients": [
                {
                    "campaign_recipient_id": prepared["id"],
                    "channels": ["sms"],
                }
            ],
            "sms_voice_line_id": str(line.id),
            "sms_body": "Hi {buyer_name}, are you interested in {property_address}?",
        },
    )
    assert drafted.status_code == 201, drafted.text
    draft = drafted.json()
    approved = client.post(
        f"/api/v1/dispositions/campaigns/{campaign.id}/outreach/{draft['id']}/approve",
        headers=HEADERS,
        json={
            "expected_lock_version": draft["lock_version"],
            "expected_approval_hash": draft["approval_hash"],
            "attestation": True,
            "reason": "Reviewed exact recipient, sender, artifact, and SMS copy.",
        },
    )
    assert approved.status_code == 200, approved.text
    revision_id = UUID(draft["id"])
    released = disposition_outreach.release_revision(
        db,
        principal_for_user(db, owner),
        campaign.id,
        revision_id,
        DispositionOutreachControlRequest(
            expected_lock_version=approved.json()["lock_version"],
            reason="Release the approved SMS simulation delivery.",
        ),
        settings=_simulation_settings(sms=True),
    )
    assert released is not None
    assert released.status == "queued"
    delivery = db.scalar(
        select(DispositionOutreachDelivery).where(
            DispositionOutreachDelivery.outreach_revision_id == revision_id
        )
    )
    assert delivery is not None and delivery.status == "queued"
    return ApprovedOutreach(campaign, revision_id, UUID(str(delivery.id)))


def _inbound_reply(
    db: Session,
    delivery: DispositionOutreachDelivery,
    *,
    channel: str,
    body: str,
    metadata: dict[str, object] | None = None,
) -> CommunicationRecord:
    assert delivery.conversation_id is not None
    assert delivery.contact_id is not None
    reply = CommunicationRecord(
        organization_id=delivery.organization_id,
        conversation_id=delivery.conversation_id,
        lead_id=None,
        contact_id=delivery.contact_id,
        source_call_record_id=None,
        actor_user_id=None,
        direction="inbound",
        channel=channel,
        status="received",
        provider="test-inbound",
        provider_message_id=f"reply-{uuid4()}",
        subject="Re: property opportunity" if channel == "email" else None,
        body=body,
        occurred_at=datetime.now(UTC) + timedelta(seconds=1),
        external_payload={"test": True},
        communication_metadata=metadata or {},
    )
    db.add(reply)
    db.flush()
    if channel == "email":
        db.add(
            CommunicationParticipant(
                organization_id=delivery.organization_id,
                communication_record_id=reply.id,
                conversation_id=delivery.conversation_id,
                contact_id=delivery.contact_id,
                user_id=None,
                email_sender_alias_id=None,
                participant_role="from",
                email_address=delivery.normalized_destination,
                normalized_email=delivery.normalized_destination,
                display_name=None,
                participant_metadata={"source": "test-inbound"},
            )
        )
    db.commit()
    return reply


def test_worker_registers_disposition_outreach_lanes() -> None:
    assert (
        "disposition_outreach_delivery",
        disposition_outreach_delivery.process_next_disposition_outreach_delivery,
    ) in worker.WORKER_OPERATIONS
    assert (
        "disposition_outreach_reconciliation",
        disposition_outreach_delivery.process_next_disposition_outreach_reconciliation,
    ) in worker.WORKER_OPERATIONS


def test_blank_postal_address_blocks_email_draft_but_not_sms(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blank_settings = Settings(
        APP_ENV="test",
        COMMUNICATION_PROVIDER_MODE="simulate",
        DISPOSITION_OUTREACH_PHYSICAL_POSTAL_ADDRESS="",
    )
    monkeypatch.setattr(disposition_outreach, "get_settings", lambda: blank_settings)
    client = TestClient(app)

    sms_context = _approve_and_release_sms(db_session, client)
    sms_delivery = db_session.get(
        DispositionOutreachDelivery,
        sms_context.delivery_id,
    )
    alias = db_session.scalar(select(EmailSenderAlias))
    assert sms_delivery is not None and alias is not None

    email_draft = client.post(
        f"/api/v1/dispositions/cases/{sms_delivery.disposition_case_id}/outreach/drafts",
        headers=HEADERS,
        json={
            "campaign_id": str(sms_context.campaign.id),
            "recipients": [
                {
                    "campaign_recipient_id": str(
                        sms_delivery.disposition_campaign_recipient_id
                    ),
                    "channels": ["email"],
                }
            ],
            "email_sender_alias_id": str(alias.id),
            "email_subject": "Stonegate property opportunity",
            "email_body": "Hi {buyer_name}, please review this opportunity.",
        },
    )
    assert email_draft.status_code == 422
    assert "DISPOSITION_OUTREACH_PHYSICAL_POSTAL_ADDRESS" in email_draft.text


def test_approved_email_delivery_sends_once_and_binds_buyer_inbox_context(
    db_session: Session,
    api_db_override: None,
) -> None:
    context = _approve_and_release_email(db_session, TestClient(app))

    processed = disposition_outreach_delivery.process_next_disposition_outreach_delivery(
        db_session,
        _simulation_settings(),
    )
    assert processed == context.delivery_id
    assert (
        disposition_outreach_delivery.process_next_disposition_outreach_delivery(
            db_session,
            _simulation_settings(),
        )
        is None
    )

    delivery = db_session.get(DispositionOutreachDelivery, context.delivery_id)
    assert delivery is not None
    assert delivery.status == "sent"
    assert delivery.attempt_count == 1
    assert delivery.provider == "simulated"
    assert delivery.communication_record_id is not None
    assert delivery.communication_dispatch_id is not None
    assert db_session.scalar(select(func.count(CommunicationRecord.id))) == 1
    assert db_session.scalar(select(func.count(CommunicationDispatch.id))) == 1

    conversation = db_session.get(Conversation, delivery.conversation_id)
    communication = db_session.get(CommunicationRecord, delivery.communication_record_id)
    assert conversation is not None and conversation.conversation_type == "buyer"
    assert conversation.queue_key == "dispositions"
    assert communication is not None
    assert communication.communication_metadata is not None
    assert communication.communication_metadata["outreach_delivery_id"] == str(delivery.id)
    links = list(
        db_session.scalars(
            select(ConversationContextLink).where(
                ConversationContextLink.conversation_id == conversation.id
            )
        ).all()
    )
    assert {link.context_type for link in links} == {"buyer", "disposition"}
    disposition_link = next(link for link in links if link.context_type == "disposition")
    assert disposition_link.disposition_case_id == delivery.disposition_case_id
    assert disposition_link.is_primary is False

    communication.status = "delivered"
    dispatch = db_session.get(CommunicationDispatch, delivery.communication_dispatch_id)
    assert dispatch is not None
    dispatch.status = "delivered"
    delivery.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    assert (
        disposition_outreach_delivery.process_next_disposition_outreach_reconciliation(
            db_session,
            _simulation_settings(),
        )
        == delivery.id
    )
    revision = db_session.get(DispositionOutreachRevision, context.revision_id)
    assert delivery.status == "delivered"
    assert revision is not None and revision.status == "completed"


def test_sms_provider_uncertainty_is_committed_and_never_automatically_retried(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _approve_and_release_sms(db_session, TestClient(app))
    state_seen_at_provider_boundary: dict[str, str] = {}

    def crash_after_submission_started(
        db: Session,
        _settings: Settings,
        delivery: DispositionOutreachDelivery,
        _revision: DispositionOutreachRevision,
        _conversation: Conversation,
        _contact: object,
        dispatch: CommunicationDispatch,
    ) -> None:
        persisted_delivery = db.get(DispositionOutreachDelivery, delivery.id)
        persisted_dispatch = db.get(CommunicationDispatch, dispatch.id)
        assert persisted_delivery is not None and persisted_dispatch is not None
        state_seen_at_provider_boundary["delivery"] = persisted_delivery.status
        state_seen_at_provider_boundary["dispatch"] = persisted_dispatch.status
        raise RuntimeError("simulated worker loss after the provider boundary")

    monkeypatch.setattr(
        disposition_outreach_delivery,
        "_send_sms",
        crash_after_submission_started,
    )
    assert (
        disposition_outreach_delivery.process_next_disposition_outreach_delivery(
            db_session,
            _simulation_settings(sms=True),
        )
        == context.delivery_id
    )

    delivery = db_session.get(DispositionOutreachDelivery, context.delivery_id)
    revision = db_session.get(DispositionOutreachRevision, context.revision_id)
    assert state_seen_at_provider_boundary == {
        "delivery": "delivery_unknown",
        "dispatch": "delivery_unknown",
    }
    assert delivery is not None and delivery.status == "delivery_unknown"
    assert delivery.attempt_count == 1
    assert delivery.communication_record_id is None
    assert revision is not None and revision.status == "completed_with_failures"
    assert (
        disposition_outreach_delivery.process_next_disposition_outreach_delivery(
            db_session,
            _simulation_settings(sms=True),
        )
        is None
    )
    assert delivery.attempt_count == 1


def test_retryable_failure_completes_with_failures_until_explicit_retry(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _approve_and_release_email(db_session, TestClient(app))
    attempts = 0

    def reject_email(*_args: object, **_kwargs: object) -> None:
        nonlocal attempts
        attempts += 1
        raise ResendEmailError(
            "temporary provider rate limit",
            status_code=429,
            retry_safe=True,
        )

    monkeypatch.setattr(disposition_outreach_delivery, "_send_email", reject_email)
    assert (
        disposition_outreach_delivery.process_next_disposition_outreach_delivery(
            db_session,
            _simulation_settings(),
        )
        == context.delivery_id
    )
    delivery = db_session.get(DispositionOutreachDelivery, context.delivery_id)
    revision = db_session.get(DispositionOutreachRevision, context.revision_id)
    assert delivery is not None and delivery.status == "failed_retryable"
    assert delivery.attempt_count == 1
    assert delivery.next_attempt_at is None
    assert revision is not None and revision.status == "completed_with_failures"

    assert (
        disposition_outreach_delivery.process_next_disposition_outreach_delivery(
            db_session,
            _simulation_settings(),
        )
        is None
    )
    assert attempts == 1
    retried = disposition_outreach.retry_failed(
        db_session,
        principal_for_user(db_session, _owner(db_session)),
        context.campaign.id,
        context.revision_id,
        DispositionOutreachControlRequest(
            expected_lock_version=revision.lock_version,
            reason="Operator explicitly approved retry after provider recovery.",
        ),
        settings=_simulation_settings(),
    )
    assert retried is not None and retried.status == "queued"
    assert delivery.status == "queued"
    assert delivery.next_attempt_at is not None


@pytest.mark.parametrize(
    ("control", "expected_delivery_status"),
    (("pause", "queued"), ("cancel", "cancelled")),
)
def test_operator_control_before_provider_boundary_prevents_email_submission(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
    control: str,
    expected_delivery_status: str,
) -> None:
    context = _approve_and_release_email(db_session, TestClient(app))
    original_boundary = disposition_outreach_delivery._provider_boundary_context
    provider_calls = 0
    control_applied = False

    def apply_control_then_fence(
        db: Session,
        settings: Settings,
        delivery_id: UUID,
        **kwargs: object,
    ) -> object:
        nonlocal control_applied
        if not control_applied:
            control_applied = True
            revision = db.get(DispositionOutreachRevision, context.revision_id)
            assert revision is not None
            request = DispositionOutreachControlRequest(
                expected_lock_version=revision.lock_version,
                reason=f"Regression test {control} before provider submission.",
            )
            principal = principal_for_user(db, _owner(db))
            if control == "pause":
                disposition_outreach.pause_revision(
                    db,
                    principal,
                    context.campaign.id,
                    context.revision_id,
                    request,
                )
            else:
                disposition_outreach.cancel_unsent(
                    db,
                    principal,
                    context.campaign.id,
                    context.revision_id,
                    request,
                )
        return original_boundary(db, settings, delivery_id, **kwargs)

    def record_provider_call(*_args: object, **_kwargs: object) -> None:
        nonlocal provider_calls
        provider_calls += 1

    monkeypatch.setattr(
        disposition_outreach_delivery,
        "_provider_boundary_context",
        apply_control_then_fence,
    )
    monkeypatch.setattr(disposition_outreach_delivery, "_send_email", record_provider_call)

    assert (
        disposition_outreach_delivery.process_next_disposition_outreach_delivery(
            db_session,
            _simulation_settings(),
        )
        == context.delivery_id
    )

    delivery = db_session.get(DispositionOutreachDelivery, context.delivery_id)
    revision = db_session.get(DispositionOutreachRevision, context.revision_id)
    dispatch = db_session.get(
        CommunicationDispatch,
        delivery.communication_dispatch_id if delivery is not None else None,
    )
    assert provider_calls == 0
    assert delivery is not None and delivery.status == expected_delivery_status
    assert revision is not None and revision.status == (
        "paused" if control == "pause" else "cancelled"
    )
    assert dispatch is not None and dispatch.communication_record_id is None
    assert dispatch.status == ("pending" if control == "pause" else "cancelled")


@pytest.mark.parametrize(
    "tamper",
    ("body", "subject", "destination", "sender", "attachment"),
)
def test_approved_email_request_tampering_is_blocked_before_provider_submission(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    context = _approve_and_release_email(db_session, TestClient(app))
    original_boundary = disposition_outreach_delivery._provider_boundary_context
    provider_calls = 0
    tamper_applied = False

    def tamper_then_fence(
        db: Session,
        settings: Settings,
        delivery_id: UUID,
        **kwargs: object,
    ) -> object:
        nonlocal tamper_applied
        if not tamper_applied:
            tamper_applied = True
            delivery = db.get(DispositionOutreachDelivery, delivery_id)
            revision = db.get(DispositionOutreachRevision, context.revision_id)
            assert delivery is not None and revision is not None
            if tamper == "body":
                delivery.body = f"{delivery.body} Unapproved change."
            elif tamper == "subject":
                delivery.subject = "Unapproved subject"
            elif tamper == "destination":
                delivery.normalized_destination = "other-buyer@example.test"
            elif tamper == "sender":
                alias = db.get(EmailSenderAlias, revision.email_sender_alias_id)
                assert alias is not None
                alias.display_name = "Unapproved sender"
            else:
                package = db.get(DispositionPackageVersion, delivery.package_version_id)
                assert package is not None
                package.pdf_data = b"unapproved attachment bytes"
            db.commit()
        return original_boundary(db, settings, delivery_id, **kwargs)

    def record_provider_call(*_args: object, **_kwargs: object) -> None:
        nonlocal provider_calls
        provider_calls += 1

    monkeypatch.setattr(
        disposition_outreach_delivery,
        "_provider_boundary_context",
        tamper_then_fence,
    )
    monkeypatch.setattr(disposition_outreach_delivery, "_send_email", record_provider_call)

    assert (
        disposition_outreach_delivery.process_next_disposition_outreach_delivery(
            db_session,
            _simulation_settings(),
        )
        == context.delivery_id
    )

    delivery = db_session.get(DispositionOutreachDelivery, context.delivery_id)
    assert provider_calls == 0
    assert delivery is not None and delivery.status in {"ineligible", "failed_retryable"}
    assert delivery.error_code == "preflight_blocked"


@pytest.mark.parametrize(
    ("provider_error", "expected_status"),
    (
        (
            ResendEmailError(
                "provider acceptance is unknown",
                status_code=500,
                acceptance_unknown=True,
            ),
            "delivery_unknown",
        ),
        (
            ResendEmailError(
                "provider rejected the request",
                status_code=400,
            ),
            "failed_terminal",
        ),
    ),
)
def test_resend_failure_classification_never_automatically_retries(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
    provider_error: ResendEmailError,
    expected_status: str,
) -> None:
    context = _approve_and_release_email(db_session, TestClient(app))
    attempts = 0

    def reject_email(*_args: object, **_kwargs: object) -> None:
        nonlocal attempts
        attempts += 1
        raise provider_error

    monkeypatch.setattr(disposition_outreach_delivery, "_send_email", reject_email)
    assert (
        disposition_outreach_delivery.process_next_disposition_outreach_delivery(
            db_session,
            _simulation_settings(),
        )
        == context.delivery_id
    )
    delivery = db_session.get(DispositionOutreachDelivery, context.delivery_id)
    assert delivery is not None and delivery.status == expected_status
    delivery.next_attempt_at = datetime.now(UTC) - timedelta(days=2)
    db_session.commit()

    assert (
        disposition_outreach_delivery.process_next_disposition_outreach_delivery(
            db_session,
            _simulation_settings(),
        )
        is None
    )
    assert attempts == 1


def test_exact_email_reply_is_reconciled_before_delivery_status_and_creates_task(
    db_session: Session,
    api_db_override: None,
) -> None:
    context = _approve_and_release_email(db_session, TestClient(app))
    disposition_outreach_delivery.process_next_disposition_outreach_delivery(
        db_session,
        _simulation_settings(),
    )
    delivery = db_session.get(DispositionOutreachDelivery, context.delivery_id)
    assert delivery is not None and delivery.communication_record_id is not None
    outbound = db_session.get(CommunicationRecord, delivery.communication_record_id)
    dispatch = db_session.get(CommunicationDispatch, delivery.communication_dispatch_id)
    assert outbound is not None and dispatch is not None
    assert outbound.communication_metadata is not None
    outbound.status = "sent"
    dispatch.status = "sent"
    delivery.status = "sent"
    delivery.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    reply = _inbound_reply(
        db_session,
        delivery,
        channel="email",
        body="I am interested. Please send more info.",
        metadata={"in_reply_to": outbound.communication_metadata["rfc_message_id"]},
    )

    processed = disposition_outreach_delivery.process_next_disposition_outreach_reconciliation(
        db_session,
        _simulation_settings(),
    )
    assert processed == reply.id
    link = db_session.scalar(
        select(DispositionReplyLink).where(
            DispositionReplyLink.communication_record_id == reply.id
        )
    )
    assert link is not None
    assert link.routing_status == "matched"
    assert link.routing_confidence == 100
    assert link.outreach_delivery_id == delivery.id
    assert link.disposition_case_id == delivery.disposition_case_id
    assert link.task_id is not None
    task = db_session.get(Task, link.task_id)
    assert task is not None and task.task_type == "buyer_reply_review"
    assert task.deal_id is not None
    assert delivery.status == "replied"


def test_matched_email_unsubscribe_creates_suppression_and_blocks_later_draft(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    context = _approve_and_release_email(db_session, client)
    disposition_outreach_delivery.process_next_disposition_outreach_delivery(
        db_session,
        _simulation_settings(),
    )
    delivery = db_session.get(DispositionOutreachDelivery, context.delivery_id)
    assert delivery is not None and delivery.communication_record_id is not None
    outbound = db_session.get(CommunicationRecord, delivery.communication_record_id)
    assert outbound is not None and outbound.communication_metadata is not None
    reply = _inbound_reply(
        db_session,
        delivery,
        channel="email",
        body="Please unsubscribe and remove me from your list.",
        metadata={"in_reply_to": outbound.communication_metadata["rfc_message_id"]},
    )

    processed = disposition_outreach_delivery.process_next_disposition_outreach_reconciliation(
        db_session,
        _simulation_settings(),
    )
    assert processed == reply.id
    link = db_session.scalar(
        select(DispositionReplyLink).where(
            DispositionReplyLink.communication_record_id == reply.id
        )
    )
    suppression = db_session.scalar(
        select(SuppressionRecord).where(
            SuppressionRecord.organization_id == delivery.organization_id,
            SuppressionRecord.channel == "email",
            SuppressionRecord.normalized_address == delivery.normalized_destination,
        )
    )
    assert link is not None and link.reply_classification == "opt_out"
    assert delivery.status == "opted_out"
    assert suppression is not None
    assert suppression.status == "active"
    assert suppression.source == "disposition_outreach_reply"
    assert suppression.contact_id == reply.contact_id
    assert suppression.suppression_metadata is not None
    assert suppression.suppression_metadata["communication_record_id"] == str(reply.id)
    assert suppression.suppression_metadata["outreach_delivery_id"] == str(delivery.id)

    alias = db_session.scalar(select(EmailSenderAlias))
    assert alias is not None
    later_draft = client.post(
        f"/api/v1/dispositions/cases/{delivery.disposition_case_id}/outreach/drafts",
        headers=HEADERS,
        json={
            "campaign_id": str(context.campaign.id),
            "recipients": [
                {
                    "campaign_recipient_id": str(
                        delivery.disposition_campaign_recipient_id
                    ),
                    "channels": ["email"],
                }
            ],
            "email_sender_alias_id": str(alias.id),
            "email_subject": "Another property opportunity",
            "email_body": "Hi {buyer_name}, this should remain suppressed.",
        },
    )
    assert later_draft.status_code == 201, later_draft.text
    later_delivery = later_draft.json()["deliveries"][0]
    assert later_delivery["status"] == "ineligible"
    assert any(
        "actively suppressed" in blocker
        for blocker in later_delivery["eligibility_snapshot"]["draft"][
            "permanent_blockers"
        ]
    )


def test_unthreaded_email_unsubscribe_suppresses_sender_before_manual_matching(
    db_session: Session,
    api_db_override: None,
) -> None:
    context = _approve_and_release_email(db_session, TestClient(app))
    disposition_outreach_delivery.process_next_disposition_outreach_delivery(
        db_session,
        _simulation_settings(),
    )
    delivery = db_session.get(DispositionOutreachDelivery, context.delivery_id)
    assert delivery is not None and delivery.status == "sent"
    reply = _inbound_reply(
        db_session,
        delivery,
        channel="email",
        body="Please unsubscribe me from these emails.",
        metadata={"in_reply_to": "<unrelated-message@example.test>"},
    )

    processed = disposition_outreach_delivery.process_next_disposition_outreach_reconciliation(
        db_session,
        _simulation_settings(),
    )
    assert processed == reply.id
    link = db_session.scalar(
        select(DispositionReplyLink).where(
            DispositionReplyLink.communication_record_id == reply.id
        )
    )
    suppression = db_session.scalar(
        select(SuppressionRecord).where(
            SuppressionRecord.organization_id == delivery.organization_id,
            SuppressionRecord.channel == "email",
            SuppressionRecord.normalized_address == delivery.normalized_destination,
        )
    )
    assert link is not None and link.routing_status == "ambiguous"
    assert link.outreach_delivery_id is None
    assert link.reply_classification == "opt_out"
    assert suppression is not None and suppression.status == "active"
    assert suppression.suppression_metadata is not None
    assert suppression.suppression_metadata["source"] == (
        "unmatched_disposition_outreach_reply"
    )
    assert "outreach_delivery_id" not in suppression.suppression_metadata
    assert delivery.status == "sent"


@pytest.mark.parametrize(
    "body",
    (
        "Please unsubscribe.",
        "Remove me from this list",
        "Please do not text me again",
    ),
)
def test_clear_email_and_sms_opt_out_phrases_are_classified_before_pass(
    body: str,
) -> None:
    assert disposition_outreach_delivery._classify_reply(body) == "opt_out"


def test_single_candidate_sms_reply_links_to_delivery_and_creates_task(
    db_session: Session,
    api_db_override: None,
) -> None:
    context = _approve_and_release_sms(db_session, TestClient(app))
    disposition_outreach_delivery.process_next_disposition_outreach_delivery(
        db_session,
        _simulation_settings(sms=True),
    )
    delivery = db_session.get(DispositionOutreachDelivery, context.delivery_id)
    assert delivery is not None and delivery.status == "sent"
    reply = _inbound_reply(
        db_session,
        delivery,
        channel="sms",
        body="Interested, please send the address.",
    )

    processed = disposition_outreach_delivery.process_next_disposition_outreach_reconciliation(
        db_session,
        _simulation_settings(sms=True),
    )
    assert processed == reply.id
    link = db_session.scalar(
        select(DispositionReplyLink).where(
            DispositionReplyLink.communication_record_id == reply.id
        )
    )
    assert link is not None and link.routing_status == "matched"
    assert link.routing_confidence == 90
    assert link.outreach_delivery_id == delivery.id
    assert link.task_id is not None
    assert db_session.get(Task, link.task_id).task_type == "buyer_reply_review"  # type: ignore[union-attr]
    assert delivery.status == "replied"


def test_ambiguous_email_reply_stays_review_only_without_mutating_delivery(
    db_session: Session,
    api_db_override: None,
) -> None:
    context = _approve_and_release_email(db_session, TestClient(app))
    disposition_outreach_delivery.process_next_disposition_outreach_delivery(
        db_session,
        _simulation_settings(),
    )
    delivery = db_session.get(DispositionOutreachDelivery, context.delivery_id)
    assert delivery is not None and delivery.status == "sent"
    reply = _inbound_reply(
        db_session,
        delivery,
        channel="email",
        body="Can someone call me?",
        metadata={"in_reply_to": "<unrelated-message@example.test>"},
    )

    disposition_outreach_delivery.process_next_disposition_outreach_reconciliation(
        db_session,
        _simulation_settings(),
    )
    link = db_session.scalar(
        select(DispositionReplyLink).where(
            DispositionReplyLink.communication_record_id == reply.id
        )
    )
    assert link is not None and link.routing_status == "ambiguous"
    assert link.outreach_delivery_id is None
    assert link.outreach_revision_id is None
    assert link.disposition_campaign_id is None
    assert link.disposition_case_id is None
    assert link.task_id is not None
    task = db_session.get(Task, link.task_id)
    assert task is not None and task.task_type == "buyer_reply_reconciliation"
    assert task.deal_id is None
    assert delivery.status == "sent"
    assert delivery.replied_at is None


def test_buyer_reply_without_prior_disposition_outreach_is_ignored(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _lead_id, _transaction_id, buyer_id = setup_case_foundation(db_session, client)
    buyer = db_session.get(Buyer, UUID(buyer_id))
    assert buyer is not None
    conversation = ensure_buyer_conversation(
        db_session,
        buyer,
        actor_user_id=_owner(db_session).id,
    )
    reply = CommunicationRecord(
        organization_id=buyer.organization_id,
        conversation_id=conversation.id,
        lead_id=None,
        contact_id=conversation.contact_id,
        source_call_record_id=None,
        actor_user_id=None,
        direction="inbound",
        channel="email",
        status="received",
        provider="test-inbound",
        provider_message_id=f"old-reply-{uuid4()}",
        subject="Old buyer email",
        body="This predates governed disposition outreach.",
        occurred_at=datetime.now(UTC),
        external_payload={"test": True},
        communication_metadata={"in_reply_to": "<legacy@example.test>"},
    )
    db_session.add(reply)
    db_session.commit()

    assert (
        disposition_outreach_delivery.process_next_disposition_outreach_reconciliation(
            db_session,
            _simulation_settings(),
        )
        is None
    )
    assert (
        db_session.scalar(
            select(DispositionReplyLink).where(
                DispositionReplyLink.communication_record_id == reply.id
            )
        )
        is None
    )
    assert (
        db_session.scalar(
            select(Task).where(Task.task_type == "buyer_reply_reconciliation")
        )
        is None
    )
