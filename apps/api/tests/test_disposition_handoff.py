from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.foundation import (
    AuditEvent,
    CompensationPlanVersion,
    Contact,
    Deal,
    DispositionCase,
    DispositionOperatingMode,
    DispositionPackageVersion,
    Lead,
    Property,
    Role,
    RoleAssignment,
    StaffLeadAlert,
    Task,
    Team,
    TeamMembership,
    Transaction,
    User,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.disposition_handoff import (
    HANDOFF_SETUP_TASK_TYPE,
    PACKAGE_READY_ALERT_SOURCE_TYPE,
    ensure_disposition_case_for_executed_transaction,
    ensure_house_disposition_case_for_executed_transaction,
    process_next_disposition_handoff_recovery,
    process_next_disposition_package_alert_recovery,
    queue_disposition_package_ready_alert,
)
from app.services.meta_lead_ads import process_next_staff_lead_alert


def setup_executed_house_transaction(
    db: Session,
) -> tuple[Transaction, User, Property]:
    bootstrap = bootstrap_foundation(
        db,
        organization_name="Disposition Handoff Test",
        admin_email="acquisitions@example.com",
        admin_name="Acquisitions Trigger",
    )
    organization = bootstrap.organization
    trigger_user = bootstrap.admin_user
    assert trigger_user is not None
    disposition_owner = User(
        organization_id=organization.id,
        email="alex-dispositions@example.com",
        display_name="Alex Dispositions",
        is_active=True,
        voice_forwarding_number="+16785550123",
        lead_alert_sms_enabled=True,
    )
    db.add(disposition_owner)
    db.flush()
    disposition_role = db.scalar(
        select(Role).where(
            Role.organization_id == organization.id,
            Role.key == "disposition_rep",
        )
    )
    assert disposition_role is not None
    db.add(
        RoleAssignment(
            organization_id=organization.id,
            user_id=disposition_owner.id,
            role_id=disposition_role.id,
        )
    )
    db.add(
        Team(
            organization_id=organization.id,
            name="Dispositions",
            team_type="dispositions",
            manager_user_id=disposition_owner.id,
            is_active=True,
        )
    )
    contact = Contact(
        organization_id=organization.id,
        legal_name="Executed House Seller",
        preferred_name=None,
        contact_type="seller",
        assigned_user_id=trigger_user.id,
    )
    property_record = Property(
        organization_id=organization.id,
        street_address="1806 Babbling Brk NW",
        city="Acworth",
        state="GA",
        postal_code="30102",
        property_type="single_family",
    )
    db.add_all([contact, property_record])
    db.flush()
    lead = Lead(
        organization_id=organization.id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=trigger_user.id,
        source="referral",
        asset_class="house",
        qualification_context={},
        stage_key="under_contract",
    )
    db.add(lead)
    db.flush()
    deal = Deal(
        organization_id=organization.id,
        lead_id=lead.id,
        property_id=property_record.id,
        stage_key="under_contract",
        contract_price_cents=15_000_000,
        assignment_fee_cents=2_000_000,
    )
    db.add(deal)
    db.flush()
    plan = CompensationPlanVersion(
        organization_id=organization.id,
        name="Active disposition plan",
        version_number=1,
        status="active",
        acquisition_reserve_cents=0,
        target_company_margin_basis_points=3000,
        effective_start_at=datetime.now(UTC),
        effective_end_at=None,
        created_by_user_id=trigger_user.id,
        approved_by_user_id=trigger_user.id,
        approved_at=datetime.now(UTC),
        notes=None,
    )
    db.add(plan)
    db.flush()
    mode = DispositionOperatingMode(
        organization_id=organization.id,
        compensation_plan_version_id=plan.id,
        key="human_led",
        name="Human-led",
        status="available",
        human_share_min_basis_points=1500,
        human_share_max_basis_points=1500,
        expected_company_share_min_basis_points=5000,
        expected_company_share_max_basis_points=5000,
        ai_authority_level="human_execution",
        activation_requirements={},
    )
    db.add(mode)
    transaction = Transaction(
        organization_id=organization.id,
        deal_id=deal.id,
        lead_id=lead.id,
        property_id=property_record.id,
        contact_id=contact.id,
        owner_user_id=trigger_user.id,
        coordinator_user_id=None,
        compensation_plan_version_id=None,
        disposition_operating_mode_id=None,
        status="executed",
        contract_type="purchase_agreement",
        purchase_price_cents=15_000_000,
        assignment_fee_cents=2_000_000,
        contract_executed_at=datetime.now(UTC),
        transaction_metadata={"source": "test"},
    )
    db.add(transaction)
    db.commit()
    return transaction, disposition_owner, property_record


def setup_approved_package(
    db: Session,
    *,
    transaction: Transaction,
    disposition_case: DispositionCase,
    disposition_owner: User,
) -> DispositionPackageVersion:
    now = datetime.now(UTC)
    disposition_case.package_status = "approved"
    disposition_case.package_approved_by_user_id = disposition_owner.id
    disposition_case.package_approved_at = now
    package = DispositionPackageVersion(
        organization_id=transaction.organization_id,
        disposition_case_id=disposition_case.id,
        created_by_user_id=disposition_owner.id,
        approved_by_user_id=disposition_owner.id,
        version_number=1,
        lock_version=2,
        status="approved",
        policy_version="test-policy",
        renderer_version="test-renderer",
        public_snapshot={},
        private_economics_snapshot={},
        evidence_manifest=[],
        readiness_snapshot={"blockers": []},
        source_fingerprint="a" * 64,
        email_summary="Approved package",
        sms_summary="Approved package",
        approval_reason="Ready for investor outreach.",
        approved_at=now,
        pdf_file_name="package.pdf",
        pdf_content_type="application/pdf",
        pdf_size=4,
        pdf_sha256="b" * 64,
        pdf_data=b"%PDF",
    )
    db.add(package)
    db.flush()
    return package


def test_executed_house_auto_creates_one_case_for_dispositions_owner(
    db_session: Session,
) -> None:
    transaction, disposition_owner, _ = setup_executed_house_transaction(db_session)

    first = ensure_house_disposition_case_for_executed_transaction(db_session, transaction)
    second = ensure_house_disposition_case_for_executed_transaction(db_session, transaction)
    db_session.commit()

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert first.owner_user_id == disposition_owner.id
    assert first.owner_user_id != transaction.owner_user_id
    assert first.status == "package_prep"
    assert first.package_status == "draft"
    assert first.strategy == "assignment"
    assert first.asking_price_cents == 17_000_000
    assert first.minimum_acceptable_cents == 17_000_000
    assert first.desired_assignment_fee_cents == 2_000_000
    assert transaction.compensation_plan_version_id is not None
    assert transaction.disposition_operating_mode_id is not None
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(DispositionCase)
            .where(DispositionCase.transaction_id == transaction.id)
        )
        == 1
    )
    audits = list(
        db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "disposition.case_auto_create",
                AuditEvent.entity_id == first.id,
            )
        ).all()
    )
    assert len(audits) == 1
    assert audits[0].actor_type == "system"
    assert audits[0].new_value["owner_routing_source"] == "dispositions_team_manager"
    assert audits[0].new_value["private_economics_source"] == "executed_transaction"


def test_executed_land_transaction_enters_shared_dispositions(db_session: Session) -> None:
    transaction, _, property_record = setup_executed_house_transaction(db_session)
    lead = db_session.get(Lead, transaction.lead_id)
    assert lead is not None
    lead.asset_class = "land"
    property_record.street_address = ""
    property_record.city = ""
    property_record.postal_code = ""
    property_record.county = "Bartow"
    property_record.parcel_id = "LAND-APN-42"
    property_record.property_type = "vacant_land"
    db_session.commit()

    created = ensure_disposition_case_for_executed_transaction(db_session, transaction)
    db_session.commit()
    recovered = process_next_disposition_handoff_recovery(db_session, get_settings())

    assert created is not None
    assert recovered is None
    assert created.package_snapshot["asset_class"] == "land"
    assert created.package_snapshot["property"] == {
        "address": "APN LAND-APN-42, Bartow, GA",
        "property_type": "vacant_land",
        "county": "Bartow",
        "parcel_id": "LAND-APN-42",
    }
    assert db_session.scalar(select(func.count()).select_from(DispositionCase)) == 1


def test_roleless_dispositions_team_manager_is_not_selected(
    db_session: Session,
) -> None:
    transaction, roleless_manager, _ = setup_executed_house_transaction(db_session)
    role_assignment = db_session.scalar(
        select(RoleAssignment).where(RoleAssignment.user_id == roleless_manager.id)
    )
    assert role_assignment is not None
    db_session.delete(role_assignment)
    team = db_session.scalar(
        select(Team).where(
            Team.organization_id == transaction.organization_id,
            Team.team_type == "dispositions",
        )
    )
    assert team is not None
    authorized_member = db_session.get(User, transaction.owner_user_id)
    assert authorized_member is not None
    db_session.add(
        TeamMembership(
            organization_id=transaction.organization_id,
            team_id=team.id,
            user_id=authorized_member.id,
            membership_role="member",
        )
    )
    db_session.commit()

    created = ensure_house_disposition_case_for_executed_transaction(
        db_session,
        transaction,
    )
    db_session.commit()

    assert created is not None
    assert created.owner_user_id == authorized_member.id
    assert created.owner_user_id != roleless_manager.id
    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "disposition.case_auto_create",
            AuditEvent.entity_id == created.id,
        )
    )
    assert audit is not None
    assert audit.new_value["owner_routing_source"] == "dispositions_team_member"


def test_non_human_led_mode_does_not_auto_create_disposition_case(
    db_session: Session,
) -> None:
    transaction, _, _ = setup_executed_house_transaction(db_session)
    mode = db_session.scalar(
        select(DispositionOperatingMode).where(
            DispositionOperatingMode.organization_id == transaction.organization_id
        )
    )
    assert mode is not None
    mode.key = "ai_assisted"
    mode.name = "AI assisted"
    db_session.commit()

    created = ensure_house_disposition_case_for_executed_transaction(
        db_session,
        transaction,
    )
    db_session.commit()

    assert created is None
    assert db_session.scalar(select(func.count()).select_from(DispositionCase)) == 0
    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "disposition.case_auto_create_blocked",
            AuditEvent.entity_id == transaction.id,
        )
    )
    assert audit is not None
    assert "No available human-led disposition operating mode." in audit.reason
    setup_task = db_session.scalar(
        select(Task).where(
            Task.deal_id == transaction.deal_id,
            Task.task_type == HANDOFF_SETUP_TASK_TYPE,
        )
    )
    assert setup_task is not None
    assert setup_task.status == "open"
    assert setup_task.priority == "urgent"
    assert setup_task.responsible_user_id is not None


def test_worker_recovers_land_handoff_after_temporary_configuration_block(
    db_session: Session,
) -> None:
    transaction, _, _ = setup_executed_house_transaction(db_session)
    lead = db_session.get(Lead, transaction.lead_id)
    mode = db_session.scalar(
        select(DispositionOperatingMode).where(
            DispositionOperatingMode.organization_id == transaction.organization_id
        )
    )
    assert lead is not None
    assert mode is not None
    lead.asset_class = "land"
    mode.key = "ai_assisted"
    db_session.commit()

    assert ensure_disposition_case_for_executed_transaction(db_session, transaction) is None
    db_session.commit()
    blocked = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "disposition.case_auto_create_blocked",
            AuditEvent.entity_id == transaction.id,
        )
    )
    assert blocked is not None
    setup_task = db_session.scalar(
        select(Task).where(
            Task.deal_id == transaction.deal_id,
            Task.task_type == HANDOFF_SETUP_TASK_TYPE,
        )
    )
    assert setup_task is not None
    assert setup_task.status == "open"

    mode.key = "human_led"
    blocked.created_at = datetime.now(UTC) - timedelta(minutes=6)
    db_session.commit()
    processed_id = process_next_disposition_handoff_recovery(
        db_session,
        get_settings(),
    )

    assert processed_id == transaction.id
    recovered = db_session.scalar(
        select(DispositionCase).where(DispositionCase.transaction_id == transaction.id)
    )
    assert recovered is not None
    assert recovered.package_snapshot["asset_class"] == "land"
    db_session.refresh(setup_task)
    assert setup_task.status == "completed"
    assert setup_task.outcome == "disposition_case_opened"


def test_completed_handoff_does_not_create_setup_work_or_retry(
    db_session: Session,
) -> None:
    transaction, _, _ = setup_executed_house_transaction(db_session)
    disposition_case = ensure_house_disposition_case_for_executed_transaction(
        db_session,
        transaction,
    )
    assert disposition_case is not None
    transaction.status = "funded"
    disposition_case.status = "reconciled"
    db_session.commit()

    existing = ensure_house_disposition_case_for_executed_transaction(
        db_session,
        transaction,
    )
    db_session.commit()
    recovered = process_next_disposition_handoff_recovery(db_session, get_settings())

    assert existing is not None
    assert existing.id == disposition_case.id
    assert recovered is None
    assert (
        db_session.scalar(
            select(Task.id).where(
                Task.deal_id == transaction.deal_id,
                Task.task_type == HANDOFF_SETUP_TASK_TYPE,
            )
        )
        is None
    )
    assert (
        db_session.scalar(
            select(AuditEvent.id).where(
                AuditEvent.entity_id == transaction.id,
                AuditEvent.action == "disposition.case_auto_create_blocked",
            )
        )
        is None
    )


def test_package_ready_sms_targets_only_case_owner_and_is_idempotent(
    db_session: Session,
) -> None:
    transaction, disposition_owner, _ = setup_executed_house_transaction(db_session)
    disposition_case = ensure_house_disposition_case_for_executed_transaction(
        db_session,
        transaction,
    )
    assert disposition_case is not None
    package = setup_approved_package(
        db_session,
        transaction=transaction,
        disposition_case=disposition_case,
        disposition_owner=disposition_owner,
    )

    first = queue_disposition_package_ready_alert(
        db_session,
        disposition_case=disposition_case,
        package_version=package,
    )
    second = queue_disposition_package_ready_alert(
        db_session,
        disposition_case=disposition_case,
        package_version=package,
    )
    db_session.commit()

    assert first == 1
    assert second == 0
    alerts = list(
        db_session.scalars(
            select(StaffLeadAlert).where(
                StaffLeadAlert.source_type == PACKAGE_READY_ALERT_SOURCE_TYPE,
                StaffLeadAlert.source_event_id == package.id,
            )
        ).all()
    )
    assert len(alerts) == 1
    assert alerts[0].recipient_user_id == disposition_owner.id
    assert alerts[0].recipient_phone == "+16785550123"
    assert "1806 Babbling Brk NW" in alerts[0].message_body
    assert "package v1 is approved" in alerts[0].message_body
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action == "disposition.package_ready_sms_queued",
                AuditEvent.entity_id == package.id,
            )
        )
        == 1
    )
    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "disposition.package_ready_sms_queued",
            AuditEvent.entity_id == package.id,
        )
    )
    assert audit is not None
    assert audit.new_value["owner_disposition_authorized"] is True
    assert audit.new_value["owner_sms_opted_in"] is True


def test_package_ready_sms_is_not_queued_for_opted_out_owner(
    db_session: Session,
) -> None:
    transaction, disposition_owner, _ = setup_executed_house_transaction(db_session)
    disposition_owner.lead_alert_sms_enabled = False
    disposition_case = ensure_house_disposition_case_for_executed_transaction(
        db_session,
        transaction,
    )
    assert disposition_case is not None
    package = setup_approved_package(
        db_session,
        transaction=transaction,
        disposition_case=disposition_case,
        disposition_owner=disposition_owner,
    )

    created = queue_disposition_package_ready_alert(
        db_session,
        disposition_case=disposition_case,
        package_version=package,
    )
    db_session.commit()

    assert created == 0
    assert db_session.scalar(select(func.count()).select_from(StaffLeadAlert)) == 0
    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "disposition.package_ready_sms_not_queued",
            AuditEvent.entity_id == package.id,
        )
    )
    assert audit is not None
    assert audit.new_value["owner_active"] is True
    assert audit.new_value["owner_disposition_authorized"] is True
    assert audit.new_value["owner_sms_opted_in"] is False
    assert "has not opted in" in audit.reason


def test_worker_recovers_package_alert_after_owner_opts_in(
    db_session: Session,
) -> None:
    transaction, disposition_owner, _ = setup_executed_house_transaction(db_session)
    disposition_owner.lead_alert_sms_enabled = False
    disposition_case = ensure_house_disposition_case_for_executed_transaction(
        db_session,
        transaction,
    )
    assert disposition_case is not None
    package = setup_approved_package(
        db_session,
        transaction=transaction,
        disposition_case=disposition_case,
        disposition_owner=disposition_owner,
    )
    assert (
        queue_disposition_package_ready_alert(
            db_session,
            disposition_case=disposition_case,
            package_version=package,
        )
        == 0
    )
    db_session.commit()
    prior_attempt = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "disposition.package_ready_sms_not_queued",
            AuditEvent.entity_id == package.id,
        )
    )
    assert prior_attempt is not None

    disposition_owner.lead_alert_sms_enabled = True
    prior_attempt.created_at = datetime.now(UTC) - timedelta(minutes=6)
    db_session.commit()
    processed_id = process_next_disposition_package_alert_recovery(
        db_session,
        get_settings(),
    )

    assert processed_id == package.id
    alert = db_session.scalar(
        select(StaffLeadAlert).where(
            StaffLeadAlert.source_type == PACKAGE_READY_ALERT_SOURCE_TYPE,
            StaffLeadAlert.source_event_id == package.id,
        )
    )
    assert alert is not None
    assert alert.recipient_user_id == disposition_owner.id


def test_queued_land_package_alert_rechecks_owner_opt_in_before_delivery(
    db_session: Session,
) -> None:
    transaction, disposition_owner, _ = setup_executed_house_transaction(db_session)
    lead = db_session.get(Lead, transaction.lead_id)
    assert lead is not None
    lead.asset_class = "land"
    disposition_case = ensure_disposition_case_for_executed_transaction(
        db_session,
        transaction,
    )
    assert disposition_case is not None
    package = setup_approved_package(
        db_session,
        transaction=transaction,
        disposition_case=disposition_case,
        disposition_owner=disposition_owner,
    )
    assert (
        queue_disposition_package_ready_alert(
            db_session,
            disposition_case=disposition_case,
            package_version=package,
        )
        == 1
    )
    db_session.commit()
    alert = db_session.scalar(
        select(StaffLeadAlert).where(
            StaffLeadAlert.source_type == PACKAGE_READY_ALERT_SOURCE_TYPE,
            StaffLeadAlert.source_event_id == package.id,
        )
    )
    assert alert is not None

    disposition_owner.lead_alert_sms_enabled = False
    db_session.commit()
    settings = get_settings().model_copy(update={"staff_lead_alert_sms_mode": "simulate"})
    assert process_next_staff_lead_alert(db_session, settings) == alert.id

    db_session.refresh(alert)
    assert alert.status == "blocked"
    assert alert.attempt_count == 0
    assert alert.provider_message_id is None
    assert "no longer opted in" in (alert.last_error or "")

    disposition_owner.lead_alert_sms_enabled = True
    alert.next_attempt_at = None
    db_session.commit()
    assert process_next_staff_lead_alert(db_session, settings) == alert.id
    db_session.refresh(alert)
    assert alert.status == "simulated"
    assert alert.provider_message_id is not None


def test_queued_package_alert_rechecks_rbac_and_current_cellphone(
    db_session: Session,
) -> None:
    transaction, disposition_owner, _ = setup_executed_house_transaction(db_session)
    disposition_case = ensure_house_disposition_case_for_executed_transaction(
        db_session,
        transaction,
    )
    assert disposition_case is not None
    package = setup_approved_package(
        db_session,
        transaction=transaction,
        disposition_case=disposition_case,
        disposition_owner=disposition_owner,
    )
    assert (
        queue_disposition_package_ready_alert(
            db_session,
            disposition_case=disposition_case,
            package_version=package,
        )
        == 1
    )
    db_session.commit()
    alert = db_session.scalar(
        select(StaffLeadAlert).where(
            StaffLeadAlert.source_type == PACKAGE_READY_ALERT_SOURCE_TYPE,
            StaffLeadAlert.source_event_id == package.id,
        )
    )
    assignment = db_session.scalar(
        select(RoleAssignment)
        .join(Role, Role.id == RoleAssignment.role_id)
        .where(
            RoleAssignment.user_id == disposition_owner.id,
            Role.key == "disposition_rep",
        )
    )
    assert alert is not None and assignment is not None
    disposition_owner.is_active = False
    db_session.commit()

    settings = get_settings().model_copy(update={"staff_lead_alert_sms_mode": "simulate"})
    assert process_next_staff_lead_alert(db_session, settings) == alert.id
    db_session.refresh(alert)
    assert alert.status == "blocked"
    assert alert.provider_message_id is None
    assert "no longer active" in (alert.last_error or "")

    disposition_owner.is_active = True
    alert.next_attempt_at = None
    db_session.delete(assignment)
    db_session.commit()
    assert process_next_staff_lead_alert(db_session, settings) == alert.id
    db_session.refresh(alert)
    assert alert.status == "blocked"
    assert alert.provider_message_id is None
    assert "permissions" in (alert.last_error or "")

    disposition_role = db_session.scalar(
        select(Role).where(
            Role.organization_id == transaction.organization_id,
            Role.key == "disposition_rep",
        )
    )
    assert disposition_role is not None
    db_session.add(
        RoleAssignment(
            organization_id=transaction.organization_id,
            user_id=disposition_owner.id,
            role_id=disposition_role.id,
        )
    )
    disposition_owner.voice_forwarding_number = "+16785550999"
    alert.next_attempt_at = None
    db_session.commit()
    assert process_next_staff_lead_alert(db_session, settings) == alert.id
    db_session.refresh(alert)
    assert alert.status == "simulated"
    assert alert.recipient_phone == "+16785550999"
    assert alert.provider_response is not None
    assert alert.provider_response["recipient"] == "+16785550999"


def test_stale_queued_owner_is_canceled_and_recovery_targets_current_owner(
    db_session: Session,
) -> None:
    transaction, disposition_owner, _ = setup_executed_house_transaction(db_session)
    disposition_case = ensure_house_disposition_case_for_executed_transaction(
        db_session,
        transaction,
    )
    assert disposition_case is not None
    package = setup_approved_package(
        db_session,
        transaction=transaction,
        disposition_case=disposition_case,
        disposition_owner=disposition_owner,
    )
    assert (
        queue_disposition_package_ready_alert(
            db_session,
            disposition_case=disposition_case,
            package_version=package,
        )
        == 1
    )
    replacement = User(
        organization_id=transaction.organization_id,
        email="replacement-dispositions@example.com",
        display_name="Replacement Dispositions",
        is_active=True,
        voice_forwarding_number="+16785550777",
        lead_alert_sms_enabled=True,
    )
    db_session.add(replacement)
    db_session.flush()
    disposition_role = db_session.scalar(
        select(Role).where(
            Role.organization_id == transaction.organization_id,
            Role.key == "disposition_rep",
        )
    )
    assert disposition_role is not None
    db_session.add(
        RoleAssignment(
            organization_id=transaction.organization_id,
            user_id=replacement.id,
            role_id=disposition_role.id,
        )
    )
    disposition_case.owner_user_id = replacement.id
    db_session.commit()
    stale_alert = db_session.scalar(
        select(StaffLeadAlert).where(
            StaffLeadAlert.source_type == PACKAGE_READY_ALERT_SOURCE_TYPE,
            StaffLeadAlert.source_event_id == package.id,
            StaffLeadAlert.recipient_user_id == disposition_owner.id,
        )
    )
    assert stale_alert is not None

    settings = get_settings().model_copy(update={"staff_lead_alert_sms_mode": "simulate"})
    assert process_next_staff_lead_alert(db_session, settings) == stale_alert.id
    db_session.refresh(stale_alert)
    assert stale_alert.status == "canceled"
    assert stale_alert.provider_message_id is None

    attempts = list(
        db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_id == package.id,
                AuditEvent.action.in_(
                    (
                        "disposition.package_ready_sms_queued",
                        "disposition.package_ready_sms_not_queued",
                    )
                ),
            )
        ).all()
    )
    latest_not_queued = next(
        item for item in attempts if item.action == "disposition.package_ready_sms_not_queued"
    )
    for item in attempts:
        item.created_at = datetime.now(UTC) - timedelta(
            minutes=6 if item.id == latest_not_queued.id else 7
        )
    db_session.commit()

    assert (
        process_next_disposition_package_alert_recovery(
            db_session,
            get_settings(),
        )
        == package.id
    )
    current_alert = db_session.scalar(
        select(StaffLeadAlert).where(
            StaffLeadAlert.source_type == PACKAGE_READY_ALERT_SOURCE_TYPE,
            StaffLeadAlert.source_event_id == package.id,
            StaffLeadAlert.recipient_user_id == replacement.id,
        )
    )
    assert current_alert is not None
    assert current_alert.recipient_phone == "+16785550777"


def test_package_alert_recovery_requires_explicit_failure_and_active_supported_deal(
    db_session: Session,
) -> None:
    transaction, disposition_owner, _ = setup_executed_house_transaction(db_session)
    disposition_case = ensure_house_disposition_case_for_executed_transaction(
        db_session,
        transaction,
    )
    assert disposition_case is not None
    package = setup_approved_package(
        db_session,
        transaction=transaction,
        disposition_case=disposition_case,
        disposition_owner=disposition_owner,
    )
    db_session.commit()

    assert (
        process_next_disposition_package_alert_recovery(
            db_session,
            get_settings(),
        )
        is None
    )
    assert db_session.scalar(select(func.count()).select_from(StaffLeadAlert)) == 0

    disposition_owner.lead_alert_sms_enabled = False
    assert (
        queue_disposition_package_ready_alert(
            db_session,
            disposition_case=disposition_case,
            package_version=package,
        )
        == 0
    )
    failure = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "disposition.package_ready_sms_not_queued",
            AuditEvent.entity_id == package.id,
        )
    )
    lead = db_session.get(Lead, transaction.lead_id)
    deal = db_session.get(Deal, transaction.deal_id)
    assert failure is not None and lead is not None and deal is not None
    disposition_owner.lead_alert_sms_enabled = True
    failure.created_at = datetime.now(UTC) - timedelta(hours=25)
    db_session.commit()
    assert (
        process_next_disposition_package_alert_recovery(
            db_session,
            get_settings(),
        )
        is None
    )

    failure.created_at = datetime.now(UTC) - timedelta(minutes=6)
    deal.stage_key = "closed"
    db_session.commit()
    assert (
        process_next_disposition_package_alert_recovery(
            db_session,
            get_settings(),
        )
        is None
    )

    deal.stage_key = "under_contract"
    lead.asset_class = "land"
    db_session.commit()
    assert (
        process_next_disposition_package_alert_recovery(
            db_session,
            get_settings(),
        )
        == package.id
    )


def test_superseded_package_version_does_not_queue_ready_sms(db_session: Session) -> None:
    transaction, disposition_owner, _ = setup_executed_house_transaction(db_session)
    disposition_case = ensure_house_disposition_case_for_executed_transaction(
        db_session,
        transaction,
    )
    assert disposition_case is not None
    now = datetime.now(UTC)
    disposition_case.package_status = "approved"
    disposition_case.package_approved_by_user_id = disposition_owner.id
    disposition_case.package_approved_at = now
    old_package = DispositionPackageVersion(
        organization_id=transaction.organization_id,
        disposition_case_id=disposition_case.id,
        created_by_user_id=disposition_owner.id,
        approved_by_user_id=disposition_owner.id,
        version_number=1,
        lock_version=2,
        status="approved",
        policy_version="test-policy",
        renderer_version="test-renderer",
        public_snapshot={},
        private_economics_snapshot={},
        evidence_manifest=[],
        readiness_snapshot={"blockers": []},
        source_fingerprint="a" * 64,
        email_summary="Old package",
        sms_summary="Old package",
        approval_reason="Previously approved.",
        approved_at=now,
    )
    newer_draft = DispositionPackageVersion(
        organization_id=transaction.organization_id,
        disposition_case_id=disposition_case.id,
        created_by_user_id=disposition_owner.id,
        approved_by_user_id=None,
        version_number=2,
        lock_version=1,
        status="draft",
        policy_version="test-policy",
        renderer_version="test-renderer",
        public_snapshot={},
        private_economics_snapshot={},
        evidence_manifest=[],
        readiness_snapshot={"blockers": []},
        source_fingerprint="c" * 64,
        email_summary="New package",
        sms_summary="New package",
        approval_reason=None,
        approved_at=None,
    )
    db_session.add_all([old_package, newer_draft])
    db_session.flush()

    created = queue_disposition_package_ready_alert(
        db_session,
        disposition_case=disposition_case,
        package_version=old_package,
    )
    db_session.commit()

    assert created == 0
    assert db_session.scalar(select(func.count()).select_from(StaffLeadAlert)) == 0
