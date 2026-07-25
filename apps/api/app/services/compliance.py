from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.models.foundation import (
    AuditEvent,
    ComplianceControlRun,
    ComplianceIncident,
    CompliancePolicyVersion,
    ComplianceTrainingRecord,
    DncScreeningSource,
    Prospect,
    ProspectCallingBatch,
    ProspectCallingBatchEntry,
    ProspectSuppressionCheck,
    SuppressionRecord,
    User,
)
from app.schemas.compliance import (
    ComplianceControlCheckRead,
    ComplianceControlRunRead,
    ComplianceIncidentCreate,
    ComplianceIncidentRead,
    ComplianceIncidentResolution,
    ComplianceInstallRead,
    ComplianceOverviewRead,
    CompliancePolicyDecision,
    CompliancePolicyLegalReviewUpdate,
    CompliancePolicyRead,
    ComplianceTrainingAssign,
    ComplianceTrainingDecision,
    ComplianceTrainingRead,
    ComplianceTrainingSubmit,
    ComplianceUserRead,
    DncScreeningRefreshCreate,
    DncScreeningSourceCreate,
    DncScreeningSourceDecision,
    DncScreeningSourceRead,
)

POLICY_SPECS: tuple[tuple[str, str, dict[str, object]], ...] = (
    (
        "national_dnc_screening",
        "National and company Do Not Call screening",
        {
            "maximum_screening_age_days": 31,
            "unknown_or_stale_result": "block",
            "required_checks": ["national_dnc", "company_suppression"],
            "recheck_before_each_call": True,
        },
    ),
    (
        "company_suppression",
        "Suppression, opt-out, complaint, and wrong-number handling",
        {
            "channels": ["phone", "sms", "email", "all"],
            "apply_immediately": True,
            "staff_override_allowed": False,
            "complaints_require_incident": True,
        },
    ),
    (
        "communication_hours_identity",
        "Contact hours, timezone, caller identity, and scripts",
        {
            "seller_timezone_required": True,
            "approved_caller_identity_required": True,
            "approved_scripts_required": True,
        },
    ),
    (
        "consent_and_outreach",
        "SMS, email, and outbound outreach consent",
        {
            "sms_requires_recorded_consent": True,
            "email_requires_recorded_permission": True,
            "opt_out_honored_across_assignments": True,
        },
    ),
    (
        "call_recording_retention",
        "Call recording disclosure, access, retention, and deletion",
        {
            "disclosure_before_recording": True,
            "all_party_consent_workflow": True,
            "objection_disables_recording": True,
            "access_audited": True,
            "deletion_audited": True,
        },
    ),
    (
        "georgia_legal_scope",
        "Georgia outreach, contracting, and seller disclosure review",
        {
            "state": "GA",
            "scope": [
                "calling",
                "sms",
                "email",
                "recording",
                "contracts",
                "seller_disclosures",
            ],
        },
    ),
)


def install_standard_policies(
    db: Session,
    principal: Principal,
) -> ComplianceInstallRead:
    existing = set(
        db.scalars(
            select(CompliancePolicyVersion.policy_key).where(
                CompliancePolicyVersion.organization_id == principal.organization_id
            )
        )
    )
    settings = get_settings()
    created = 0
    for key, name, base_config in POLICY_SPECS:
        if key in existing:
            continue
        config = dict(base_config)
        if key == "communication_hours_identity":
            config.update(
                {
                    "voice_timezone": settings.twilio_voice_timezone,
                    "voice_start_hour": settings.twilio_voice_allowed_start_hour,
                    "voice_end_hour": settings.twilio_voice_allowed_end_hour,
                    "sms_timezone": settings.twilio_sms_timezone,
                    "sms_start_hour": settings.twilio_sms_allowed_start_hour,
                    "sms_end_hour": settings.twilio_sms_allowed_end_hour,
                }
            )
        if key == "call_recording_retention":
            config.update(
                {
                    "disclosure_script": settings.twilio_voice_recording_disclosure,
                    "retention_days": settings.call_recording_retention_days,
                }
            )
        db.add(
            CompliancePolicyVersion(
                organization_id=principal.organization_id,
                policy_key=key,
                name=name,
                scope_state_code="GA",
                version_number=1,
                status="draft",
                policy_config=config,
                legal_review_status="pending",
                created_by_user_id=principal.user_id,
            )
        )
        created += 1
    _audit(
        db,
        principal,
        action="compliance.policies_installed",
        entity_type="organization",
        entity_id=principal.organization_id,
        new={"created_policy_count": created},
        reason="Installed the standard F3 compliance policy set.",
    )
    db.commit()
    return ComplianceInstallRead(
        created_policy_count=created,
        overview=get_compliance_overview(db, principal),
    )


def get_compliance_overview(db: Session, principal: Principal) -> ComplianceOverviewRead:
    organization_id = principal.organization_id
    users = _users(db, organization_id)
    user_map = {user.id: user for user in users}
    policies = list(
        db.scalars(
            select(CompliancePolicyVersion)
            .where(CompliancePolicyVersion.organization_id == organization_id)
            .order_by(
                CompliancePolicyVersion.policy_key,
                CompliancePolicyVersion.version_number.desc(),
            )
        )
    )
    sources = list(
        db.scalars(
            select(DncScreeningSource)
            .where(DncScreeningSource.organization_id == organization_id)
            .order_by(DncScreeningSource.created_at.desc())
        )
    )
    training = list(
        db.scalars(
            select(ComplianceTrainingRecord)
            .where(ComplianceTrainingRecord.organization_id == organization_id)
            .order_by(ComplianceTrainingRecord.created_at.desc())
        )
    )
    incidents = list(
        db.scalars(
            select(ComplianceIncident)
            .where(ComplianceIncident.organization_id == organization_id)
            .order_by(ComplianceIncident.occurred_at.desc())
            .limit(100)
        )
    )
    runs = list(
        db.scalars(
            select(ComplianceControlRun)
            .where(ComplianceControlRun.organization_id == organization_id)
            .order_by(ComplianceControlRun.started_at.desc())
            .limit(20)
        )
    )
    checks = _readiness_checks(policies, sources, training)
    return ComplianceOverviewRead(
        users=[
            ComplianceUserRead(
                id=user.id,
                display_name=user.display_name,
                email=user.email,
                is_active=user.is_active,
            )
            for user in users
        ],
        policies=[_policy_read(policy, user_map) for policy in policies],
        dnc_sources=[_source_read(source, user_map) for source in sources],
        training_records=[_training_read(record, user_map) for record in training],
        incidents=[_incident_read(incident, user_map) for incident in incidents],
        control_runs=[_run_read(run, user_map) for run in runs],
        ready_check_count=sum(check.status == "pass" for check in checks),
        total_check_count=len(checks),
    )


def update_policy_legal_review(
    db: Session,
    principal: Principal,
    policy_id: UUID,
    payload: CompliancePolicyLegalReviewUpdate,
) -> CompliancePolicyRead | None:
    policy = _policy(db, principal.organization_id, policy_id)
    if policy is None:
        return None
    if policy.status not in {"draft", "retired"}:
        raise ValueError("Only a draft or retired policy can receive new legal review evidence.")
    if payload.review_due_at <= payload.legal_reviewed_at:
        raise ValueError("The next legal review must be after the completed review.")
    policy.legal_review_status = "approved"
    policy.legal_reviewer_name = payload.legal_reviewer_name.strip()
    policy.legal_reviewer_company = payload.legal_reviewer_company.strip()
    policy.legal_evidence_reference = payload.legal_evidence_reference.strip()
    policy.legal_reviewed_at = payload.legal_reviewed_at
    policy.review_due_at = payload.review_due_at
    policy.notes = _clean(payload.notes)
    _audit(
        db,
        principal,
        action="compliance.policy_legal_review_recorded",
        entity_type="compliance_policy_version",
        entity_id=policy.id,
        new={
            "reviewer": policy.legal_reviewer_name,
            "review_due_at": policy.review_due_at.isoformat(),
        },
        reason="Recorded external legal review evidence.",
    )
    db.commit()
    db.refresh(policy)
    return _policy_read(policy, _user_map(db, principal.organization_id))


def decide_policy(
    db: Session,
    principal: Principal,
    policy_id: UUID,
    payload: CompliancePolicyDecision,
) -> CompliancePolicyRead | None:
    policy = _policy(db, principal.organization_id, policy_id)
    if policy is None:
        return None
    now = datetime.now(UTC)
    if payload.decision == "approve":
        if policy.legal_review_status != "approved" or policy.legal_reviewed_at is None:
            raise ValueError("Legal review evidence is required before owner approval.")
        if policy.review_due_at is None or _as_utc(policy.review_due_at) <= now:
            raise ValueError("Legal review evidence is expired.")
        active = list(
            db.scalars(
                select(CompliancePolicyVersion).where(
                    CompliancePolicyVersion.organization_id == principal.organization_id,
                    CompliancePolicyVersion.policy_key == policy.policy_key,
                    CompliancePolicyVersion.status == "active",
                    CompliancePolicyVersion.id != policy.id,
                )
            )
        )
        for prior in active:
            prior.status = "superseded"
            prior.superseded_at = now
        policy.status = "active"
        policy.approved_by_user_id = principal.user_id
        policy.approved_at = now
        policy.effective_at = now
        policy.superseded_at = None
    else:
        policy.status = "retired"
        policy.superseded_at = now
    _audit(
        db,
        principal,
        action=f"compliance.policy_{payload.decision}d",
        entity_type="compliance_policy_version",
        entity_id=policy.id,
        new={"status": policy.status},
        reason=payload.reason,
    )
    db.commit()
    db.refresh(policy)
    return _policy_read(policy, _user_map(db, principal.organization_id))


def create_dnc_source(
    db: Session,
    principal: Principal,
    payload: DncScreeningSourceCreate,
) -> DncScreeningSourceRead:
    source = DncScreeningSource(
        organization_id=principal.organization_id,
        name=payload.name.strip(),
        provider_type=payload.provider_type,
        status="draft",
        account_reference=_clean(payload.account_reference),
        coverage_area_codes=sorted(
            {value.strip() for value in payload.coverage_area_codes if value.strip()}
        ),
        refresh_interval_days=payload.refresh_interval_days,
        notes=_clean(payload.notes),
    )
    db.add(source)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("A DNC source with this name already exists.") from exc
    _audit(
        db,
        principal,
        action="compliance.dnc_source_created",
        entity_type="dnc_screening_source",
        entity_id=source.id,
        new={"name": source.name, "provider_type": source.provider_type},
        reason="Added a DNC screening evidence source.",
    )
    db.commit()
    db.refresh(source)
    return _source_read(source, _user_map(db, principal.organization_id))


def decide_dnc_source(
    db: Session,
    principal: Principal,
    source_id: UUID,
    payload: DncScreeningSourceDecision,
) -> DncScreeningSourceRead | None:
    source = _source(db, principal.organization_id, source_id)
    if source is None:
        return None
    now = datetime.now(UTC)
    if payload.decision == "approve":
        source.status = "active"
        source.approved_by_user_id = principal.user_id
        source.approved_at = now
    else:
        source.status = "inactive"
    _audit(
        db,
        principal,
        action=f"compliance.dnc_source_{payload.decision}d",
        entity_type="dnc_screening_source",
        entity_id=source.id,
        new={"status": source.status},
        reason=payload.reason,
    )
    db.commit()
    db.refresh(source)
    return _source_read(source, _user_map(db, principal.organization_id))


def record_dnc_refresh(
    db: Session,
    principal: Principal,
    source_id: UUID,
    payload: DncScreeningRefreshCreate,
) -> DncScreeningSourceRead | None:
    source = _source(db, principal.organization_id, source_id)
    if source is None:
        return None
    if source.status != "active":
        raise ValueError("Approve the DNC source before recording refresh evidence.")
    if _as_utc(payload.refreshed_at) > datetime.now(UTC) + timedelta(minutes=5):
        raise ValueError("The refresh time cannot be in the future.")
    source.last_refreshed_at = _as_utc(payload.refreshed_at)
    source.next_refresh_due_at = _as_utc(payload.refreshed_at) + timedelta(
        days=min(source.refresh_interval_days, 31)
    )
    source.latest_evidence_reference = payload.evidence_reference.strip()
    if payload.notes:
        source.notes = payload.notes.strip()
    _audit(
        db,
        principal,
        action="compliance.dnc_source_refreshed",
        entity_type="dnc_screening_source",
        entity_id=source.id,
        new={
            "refreshed_at": source.last_refreshed_at.isoformat(),
            "next_due_at": source.next_refresh_due_at.isoformat(),
            "evidence": source.latest_evidence_reference,
        },
        reason="Recorded current DNC synchronization evidence.",
    )
    db.commit()
    db.refresh(source)
    return _source_read(source, _user_map(db, principal.organization_id))


def assign_training(
    db: Session,
    principal: Principal,
    payload: ComplianceTrainingAssign,
) -> ComplianceTrainingRead:
    user = db.scalar(
        select(User).where(
            User.organization_id == principal.organization_id,
            User.id == payload.user_id,
            User.is_active.is_(True),
        )
    )
    if user is None:
        raise ValueError("Training can only be assigned to an active workspace user.")
    record = ComplianceTrainingRecord(
        organization_id=principal.organization_id,
        user_id=user.id,
        training_key=payload.training_key,
        training_version=payload.training_version.strip(),
        status="assigned",
        assigned_by_user_id=principal.user_id,
    )
    db.add(record)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("This training version is already assigned to that user.") from exc
    _audit(
        db,
        principal,
        action="compliance.training_assigned",
        entity_type="compliance_training_record",
        entity_id=record.id,
        new={"user_id": str(user.id), "training_key": record.training_key},
        reason="Assigned required compliance training.",
    )
    db.commit()
    db.refresh(record)
    return _training_read(record, _user_map(db, principal.organization_id))


def get_my_training(db: Session, principal: Principal) -> list[ComplianceTrainingRead]:
    records = list(
        db.scalars(
            select(ComplianceTrainingRecord)
            .where(
                ComplianceTrainingRecord.organization_id == principal.organization_id,
                ComplianceTrainingRecord.user_id == principal.user_id,
            )
            .order_by(ComplianceTrainingRecord.created_at.desc())
        )
    )
    return [_training_read(record, _user_map(db, principal.organization_id)) for record in records]


def submit_training(
    db: Session,
    principal: Principal,
    record_id: UUID,
    payload: ComplianceTrainingSubmit,
) -> ComplianceTrainingRead | None:
    record = db.scalar(
        select(ComplianceTrainingRecord).where(
            ComplianceTrainingRecord.organization_id == principal.organization_id,
            ComplianceTrainingRecord.user_id == principal.user_id,
            ComplianceTrainingRecord.id == record_id,
        )
    )
    if record is None:
        return None
    if record.status not in {"assigned", "needs_changes"}:
        raise ValueError("This training assignment cannot be submitted in its current state.")
    record.completion_evidence = payload.completion_evidence.strip()
    record.employee_attestation = payload.employee_attestation.strip()
    record.completed_at = datetime.now(UTC)
    record.status = "submitted"
    _audit(
        db,
        principal,
        action="compliance.training_submitted",
        entity_type="compliance_training_record",
        entity_id=record.id,
        new={"status": record.status},
        reason="Staff member submitted compliance training evidence.",
    )
    db.commit()
    db.refresh(record)
    return _training_read(record, _user_map(db, principal.organization_id))


def decide_training(
    db: Session,
    principal: Principal,
    record_id: UUID,
    payload: ComplianceTrainingDecision,
) -> ComplianceTrainingRead | None:
    record = db.scalar(
        select(ComplianceTrainingRecord).where(
            ComplianceTrainingRecord.organization_id == principal.organization_id,
            ComplianceTrainingRecord.id == record_id,
        )
    )
    if record is None:
        return None
    if payload.decision == "approve" and record.status != "submitted":
        raise ValueError("Training must be submitted before it can be approved.")
    now = datetime.now(UTC)
    record.status = {
        "approve": "approved",
        "needs_changes": "needs_changes",
        "revoke": "revoked",
    }[payload.decision]
    record.manager_notes = payload.manager_notes.strip()
    record.score_basis_points = payload.score_basis_points
    record.approved_by_user_id = principal.user_id if payload.decision == "approve" else None
    record.approved_at = now if payload.decision == "approve" else None
    _audit(
        db,
        principal,
        action=f"compliance.training_{payload.decision}d",
        entity_type="compliance_training_record",
        entity_id=record.id,
        new={"status": record.status, "score_basis_points": record.score_basis_points},
        reason=record.manager_notes,
    )
    db.commit()
    db.refresh(record)
    return _training_read(record, _user_map(db, principal.organization_id))


def create_incident(
    db: Session,
    principal: Principal,
    payload: ComplianceIncidentCreate,
) -> ComplianceIncidentRead:
    incident = ComplianceIncident(
        organization_id=principal.organization_id,
        contact_id=payload.contact_id,
        lead_id=payload.lead_id,
        prospect_id=payload.prospect_id,
        call_record_id=payload.call_record_id,
        incident_type=payload.incident_type,
        channel=payload.channel,
        severity=payload.severity,
        status="open",
        source="manual",
        summary=payload.summary.strip(),
        details=_clean(payload.details),
        reported_by_user_id=principal.user_id,
        assigned_to_user_id=payload.assigned_to_user_id,
        occurred_at=payload.occurred_at or datetime.now(UTC),
    )
    db.add(incident)
    db.flush()
    _audit(
        db,
        principal,
        action="compliance.incident_created",
        entity_type="compliance_incident",
        entity_id=incident.id,
        new={"type": incident.incident_type, "severity": incident.severity},
        reason=incident.summary,
    )
    db.commit()
    db.refresh(incident)
    return _incident_read(incident, _user_map(db, principal.organization_id))


def resolve_incident(
    db: Session,
    principal: Principal,
    incident_id: UUID,
    payload: ComplianceIncidentResolution,
) -> ComplianceIncidentRead | None:
    incident = db.scalar(
        select(ComplianceIncident).where(
            ComplianceIncident.organization_id == principal.organization_id,
            ComplianceIncident.id == incident_id,
        )
    )
    if incident is None:
        return None
    incident.status = "resolved"
    incident.resolution = payload.resolution.strip()
    incident.resolved_by_user_id = principal.user_id
    incident.resolved_at = datetime.now(UTC)
    _audit(
        db,
        principal,
        action="compliance.incident_resolved",
        entity_type="compliance_incident",
        entity_id=incident.id,
        new={"status": incident.status},
        reason=incident.resolution,
    )
    db.commit()
    db.refresh(incident)
    return _incident_read(incident, _user_map(db, principal.organization_id))


def run_compliance_controls(
    db: Session,
    principal: Principal,
) -> ComplianceControlRunRead:
    started = datetime.now(UTC)
    max_age = dnc_screening_max_age_days(db, principal.organization_id)
    cutoff = started - timedelta(days=max_age)
    stale_eligible = db.scalar(
        select(func.count())
        .select_from(Prospect)
        .where(
            Prospect.organization_id == principal.organization_id,
            Prospect.call_eligibility == "eligible",
            (
                Prospect.suppression_checked_at.is_(None)
                | (Prospect.suppression_checked_at < cutoff)
            ),
        )
    ) or 0
    unsafe_batch_entries = db.scalar(
        select(func.count())
        .select_from(ProspectCallingBatchEntry)
        .join(
            ProspectCallingBatch,
            ProspectCallingBatch.id
            == ProspectCallingBatchEntry.prospect_calling_batch_id,
        )
        .join(Prospect, Prospect.id == ProspectCallingBatchEntry.prospect_id)
        .where(
            ProspectCallingBatchEntry.organization_id == principal.organization_id,
            ProspectCallingBatch.status.in_(("ready", "in_progress")),
            (
                (Prospect.call_eligibility != "eligible")
                | (Prospect.suppression_status != "clear")
                | (Prospect.suppression_checked_at.is_(None))
                | (Prospect.suppression_checked_at < cutoff)
            ),
        )
    ) or 0
    active_policies = list(
        db.scalars(
            select(CompliancePolicyVersion).where(
                CompliancePolicyVersion.organization_id == principal.organization_id,
                CompliancePolicyVersion.status == "active",
            )
        )
    )
    policy_keys = {policy.policy_key for policy in active_policies}
    current_sources = list(
        db.scalars(
            select(DncScreeningSource).where(
                DncScreeningSource.organization_id == principal.organization_id,
                DncScreeningSource.status == "active",
                DncScreeningSource.next_refresh_due_at.is_not(None),
                DncScreeningSource.next_refresh_due_at >= started,
            )
        )
    )
    open_high_incidents = db.scalar(
        select(func.count())
        .select_from(ComplianceIncident)
        .where(
            ComplianceIncident.organization_id == principal.organization_id,
            ComplianceIncident.status == "open",
            ComplianceIncident.severity.in_(("high", "critical")),
        )
    ) or 0
    settings = get_settings()
    checks = [
        _check(
            "policy_set",
            "Approved policy set",
            len(policy_keys) == len(POLICY_SPECS),
            f"{len(policy_keys)} of {len(POLICY_SPECS)} required policies are active.",
            len(POLICY_SPECS) - len(policy_keys),
        ),
        _check(
            "dnc_source",
            "Current DNC source evidence",
            bool(current_sources),
            "At least one active DNC source has refresh evidence within its due date."
            if current_sources
            else "No active DNC source has current refresh evidence.",
            0 if current_sources else 1,
        ),
        _check(
            "stale_eligible_prospects",
            "Eligible prospects have current screening",
            stale_eligible == 0,
            f"{stale_eligible} eligible prospect(s) have missing or stale screening.",
            stale_eligible,
        ),
        _check(
            "unsafe_calling_batches",
            "Calling batches contain only eligible records",
            unsafe_batch_entries == 0,
            f"{unsafe_batch_entries} queued or active batch record(s) fail the current gate.",
            unsafe_batch_entries,
        ),
        ComplianceControlCheckRead(
            key="recording_gate",
            label="Recording policy gate",
            status=(
                "pass"
                if not settings.twilio_voice_recording_enabled
                or "call_recording_retention" in policy_keys
                else "fail"
            ),
            detail=(
                "Recording is disabled by environment configuration."
                if not settings.twilio_voice_recording_enabled
                else "Recording has an active reviewed policy."
                if "call_recording_retention" in policy_keys
                else "Recording is configured but its reviewed policy is not active."
            ),
            affected_count=(
                1
                if settings.twilio_voice_recording_enabled
                and "call_recording_retention" not in policy_keys
                else 0
            ),
        ),
        ComplianceControlCheckRead(
            key="high_incidents",
            label="High-severity incident queue",
            status="pass" if open_high_incidents == 0 else "attention",
            detail=f"{open_high_incidents} open high or critical incident(s).",
            affected_count=open_high_incidents,
        ),
    ]
    completed = datetime.now(UTC)
    run = ComplianceControlRun(
        organization_id=principal.organization_id,
        run_by_user_id=principal.user_id,
        status="passed" if all(check.status == "pass" for check in checks) else "attention",
        results=[check.model_dump(mode="json") for check in checks],
        started_at=started,
        completed_at=completed,
    )
    db.add(run)
    db.flush()
    _audit(
        db,
        principal,
        action="compliance.controls_run",
        entity_type="compliance_control_run",
        entity_id=run.id,
        new={"status": run.status, "checks": len(checks)},
        reason="Executed the F3 compliance control suite.",
    )
    db.commit()
    db.refresh(run)
    return _run_read(run, _user_map(db, principal.organization_id))


def active_policy(
    db: Session,
    organization_id: UUID,
    policy_key: str,
    *,
    now: datetime | None = None,
) -> CompliancePolicyVersion | None:
    current = now or datetime.now(UTC)
    return db.scalar(
        select(CompliancePolicyVersion)
        .where(
            CompliancePolicyVersion.organization_id == organization_id,
            CompliancePolicyVersion.policy_key == policy_key,
            CompliancePolicyVersion.status == "active",
            CompliancePolicyVersion.legal_review_status == "approved",
            CompliancePolicyVersion.review_due_at.is_not(None),
            CompliancePolicyVersion.review_due_at > current,
        )
        .order_by(CompliancePolicyVersion.version_number.desc())
    )


def recording_enabled_for_organization(
    db: Session,
    organization_id: UUID,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> bool:
    settings = settings or get_settings()
    return bool(
        settings.twilio_voice_recording_configured
        and active_policy(
            db,
            organization_id,
            "call_recording_retention",
            now=now,
        )
    )


def dnc_screening_max_age_days(db: Session, organization_id: UUID) -> int:
    policy = active_policy(db, organization_id, "national_dnc_screening")
    if policy is None:
        return 31
    raw = policy.policy_config.get("maximum_screening_age_days", 31)
    try:
        return max(1, min(int(raw), 31))
    except (TypeError, ValueError):
        return 31


def approved_contact_hours(
    db: Session,
    organization_id: UUID,
    channel: str,
    *,
    settings: Settings | None = None,
) -> tuple[str, int, int]:
    settings = settings or get_settings()
    prefix = "sms" if channel == "sms" else "voice"
    fallback = (
        (
            settings.twilio_sms_timezone,
            settings.twilio_sms_allowed_start_hour,
            settings.twilio_sms_allowed_end_hour,
        )
        if prefix == "sms"
        else (
            settings.twilio_voice_timezone,
            settings.twilio_voice_allowed_start_hour,
            settings.twilio_voice_allowed_end_hour,
        )
    )
    policy = active_policy(db, organization_id, "communication_hours_identity")
    if policy is None:
        return fallback
    try:
        timezone = str(policy.policy_config[f"{prefix}_timezone"])
        start_hour = int(policy.policy_config[f"{prefix}_start_hour"])
        end_hour = int(policy.policy_config[f"{prefix}_end_hour"])
    except (KeyError, TypeError, ValueError):
        return fallback
    if not timezone or not 0 <= start_hour <= 23 or not 1 <= end_hour <= 24:
        return fallback
    return timezone, start_hour, end_hour


def prospect_call_blockers(
    db: Session,
    prospect: Prospect,
    *,
    now: datetime | None = None,
) -> tuple[str, ...]:
    current = now or datetime.now(UTC)
    blockers: list[str] = []
    if not prospect.normalized_phone:
        blockers.append("A valid prospect phone number is required.")
    if prospect.call_eligibility != "eligible":
        blockers.append("The prospect is not approved for calling.")
    if prospect.suppression_status != "clear":
        blockers.append("The prospect has a suppression or review hold.")
    if prospect.normalized_phone:
        values = _phone_values(prospect.normalized_phone)
        suppressed = db.scalar(
            select(SuppressionRecord).where(
                SuppressionRecord.organization_id == prospect.organization_id,
                SuppressionRecord.channel.in_(("phone", "all")),
                SuppressionRecord.normalized_address.in_(values),
                SuppressionRecord.status == "active",
            )
        )
        if suppressed is not None:
            blockers.append("The phone number is on Stonegate's suppression list.")
    cutoff = current - timedelta(
        days=dnc_screening_max_age_days(db, prospect.organization_id)
    )
    latest_dnc = db.scalar(
        select(ProspectSuppressionCheck)
        .where(
            ProspectSuppressionCheck.organization_id == prospect.organization_id,
            ProspectSuppressionCheck.prospect_id == prospect.id,
            ProspectSuppressionCheck.check_type == "national_dnc",
        )
        .order_by(ProspectSuppressionCheck.checked_at.desc())
    )
    if latest_dnc is None:
        blockers.append("A National Do Not Call screening result is required.")
    elif latest_dnc.status != "clear":
        blockers.append("The latest National Do Not Call screening is not clear.")
    elif _as_utc(latest_dnc.checked_at) < cutoff:
        blockers.append("The National Do Not Call screening is more than 31 days old.")
    return tuple(dict.fromkeys(blockers))


def _readiness_checks(
    policies: list[CompliancePolicyVersion],
    sources: list[DncScreeningSource],
    training: list[ComplianceTrainingRecord],
) -> list[ComplianceControlCheckRead]:
    now = datetime.now(UTC)
    active_keys = {
        policy.policy_key
        for policy in policies
        if policy.status == "active"
        and policy.legal_review_status == "approved"
        and policy.review_due_at is not None
        and _as_utc(policy.review_due_at) > now
    }
    return [
        _check(
            "policy_set",
            "Policy approval",
            len(active_keys) == len(POLICY_SPECS),
            f"{len(active_keys)} of {len(POLICY_SPECS)} policies are active.",
            len(POLICY_SPECS) - len(active_keys),
        ),
        _check(
            "dnc_source",
            "DNC evidence",
            any(
                source.status == "active"
                and source.next_refresh_due_at is not None
                and _as_utc(source.next_refresh_due_at) >= now
                for source in sources
            ),
            "Current DNC refresh evidence is required.",
            0
            if any(
                source.status == "active"
                and source.next_refresh_due_at is not None
                and _as_utc(source.next_refresh_due_at) >= now
                for source in sources
            )
            else 1,
        ),
        ComplianceControlCheckRead(
            key="training",
            label="Staff training",
            status=(
                "pass"
                if training and all(record.status == "approved" for record in training)
                else "attention"
            ),
            detail=(
                "All assigned training is approved."
                if training and all(record.status == "approved" for record in training)
                else "Assign and approve role-appropriate training before outbound work."
            ),
            affected_count=sum(record.status != "approved" for record in training),
        ),
    ]


def _check(
    key: str,
    label: str,
    passed: bool,
    detail: str,
    affected_count: int,
) -> ComplianceControlCheckRead:
    return ComplianceControlCheckRead(
        key=key,
        label=label,
        status="pass" if passed else "fail",
        detail=detail,
        affected_count=max(0, affected_count),
    )


def _policy(
    db: Session, organization_id: UUID, policy_id: UUID
) -> CompliancePolicyVersion | None:
    return db.scalar(
        select(CompliancePolicyVersion).where(
            CompliancePolicyVersion.organization_id == organization_id,
            CompliancePolicyVersion.id == policy_id,
        )
    )


def _source(
    db: Session, organization_id: UUID, source_id: UUID
) -> DncScreeningSource | None:
    return db.scalar(
        select(DncScreeningSource).where(
            DncScreeningSource.organization_id == organization_id,
            DncScreeningSource.id == source_id,
        )
    )


def _users(db: Session, organization_id: UUID) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(User.organization_id == organization_id)
            .order_by(User.is_active.desc(), User.display_name)
        )
    )


def _user_map(db: Session, organization_id: UUID) -> dict[UUID, User]:
    return {user.id: user for user in _users(db, organization_id)}


def _policy_read(
    policy: CompliancePolicyVersion, users: dict[UUID, User]
) -> CompliancePolicyRead:
    approver = users.get(policy.approved_by_user_id) if policy.approved_by_user_id else None
    return CompliancePolicyRead(
        id=policy.id,
        policy_key=policy.policy_key,
        name=policy.name,
        scope_state_code=policy.scope_state_code,
        version_number=policy.version_number,
        status=policy.status,
        policy_config=policy.policy_config,
        legal_review_status=policy.legal_review_status,
        legal_reviewer_name=policy.legal_reviewer_name,
        legal_reviewer_company=policy.legal_reviewer_company,
        legal_evidence_reference=policy.legal_evidence_reference,
        legal_reviewed_at=policy.legal_reviewed_at,
        approved_by_user_id=policy.approved_by_user_id,
        approved_by_name=approver.display_name if approver else None,
        approved_at=policy.approved_at,
        effective_at=policy.effective_at,
        review_due_at=policy.review_due_at,
        superseded_at=policy.superseded_at,
        notes=policy.notes,
    )


def _source_read(
    source: DncScreeningSource, users: dict[UUID, User]
) -> DncScreeningSourceRead:
    approver = users.get(source.approved_by_user_id) if source.approved_by_user_id else None
    now = datetime.now(UTC)
    return DncScreeningSourceRead(
        id=source.id,
        name=source.name,
        provider_type=source.provider_type,
        status=source.status,
        account_reference=source.account_reference,
        coverage_area_codes=source.coverage_area_codes,
        refresh_interval_days=source.refresh_interval_days,
        last_refreshed_at=source.last_refreshed_at,
        next_refresh_due_at=source.next_refresh_due_at,
        latest_evidence_reference=source.latest_evidence_reference,
        approved_by_user_id=source.approved_by_user_id,
        approved_by_name=approver.display_name if approver else None,
        approved_at=source.approved_at,
        notes=source.notes,
        is_current=bool(
            source.status == "active"
            and source.next_refresh_due_at
            and _as_utc(source.next_refresh_due_at) >= now
        ),
    )


def _training_read(
    record: ComplianceTrainingRecord, users: dict[UUID, User]
) -> ComplianceTrainingRead:
    user = users.get(record.user_id)
    assigner = users.get(record.assigned_by_user_id)
    approver = users.get(record.approved_by_user_id) if record.approved_by_user_id else None
    return ComplianceTrainingRead(
        id=record.id,
        user_id=record.user_id,
        user_name=user.display_name if user else "Unknown user",
        user_email=user.email if user else "",
        training_key=record.training_key,
        training_version=record.training_version,
        status=record.status,
        assigned_by_user_id=record.assigned_by_user_id,
        assigned_by_name=assigner.display_name if assigner else "Unknown user",
        completed_at=record.completed_at,
        score_basis_points=record.score_basis_points,
        completion_evidence=record.completion_evidence,
        employee_attestation=record.employee_attestation,
        approved_by_user_id=record.approved_by_user_id,
        approved_by_name=approver.display_name if approver else None,
        approved_at=record.approved_at,
        manager_notes=record.manager_notes,
    )


def _incident_read(
    incident: ComplianceIncident, users: dict[UUID, User]
) -> ComplianceIncidentRead:
    reporter = users.get(incident.reported_by_user_id) if incident.reported_by_user_id else None
    assignee = users.get(incident.assigned_to_user_id) if incident.assigned_to_user_id else None
    resolver = users.get(incident.resolved_by_user_id) if incident.resolved_by_user_id else None
    return ComplianceIncidentRead(
        id=incident.id,
        contact_id=incident.contact_id,
        lead_id=incident.lead_id,
        prospect_id=incident.prospect_id,
        call_record_id=incident.call_record_id,
        incident_type=incident.incident_type,
        channel=incident.channel,
        severity=incident.severity,
        status=incident.status,
        source=incident.source,
        summary=incident.summary,
        details=incident.details,
        reported_by_user_id=incident.reported_by_user_id,
        reported_by_name=reporter.display_name if reporter else None,
        assigned_to_user_id=incident.assigned_to_user_id,
        assigned_to_name=assignee.display_name if assignee else None,
        occurred_at=incident.occurred_at,
        resolved_by_user_id=incident.resolved_by_user_id,
        resolved_by_name=resolver.display_name if resolver else None,
        resolved_at=incident.resolved_at,
        resolution=incident.resolution,
    )


def _run_read(
    run: ComplianceControlRun, users: dict[UUID, User]
) -> ComplianceControlRunRead:
    actor = users.get(run.run_by_user_id)
    return ComplianceControlRunRead(
        id=run.id,
        status=run.status,
        results=[ComplianceControlCheckRead.model_validate(item) for item in run.results],
        run_by_user_id=run.run_by_user_id,
        run_by_name=actor.display_name if actor else "Unknown user",
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def _phone_values(value: str) -> tuple[str, ...]:
    digits = "".join(character for character in value if character.isdigit())
    values = {value, digits}
    if len(digits) == 10:
        values.add(f"+1{digits}")
    elif len(digits) == 11 and digits.startswith("1"):
        values.update((digits[1:], f"+{digits}"))
    return tuple(item for item in values if item)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _audit(
    db: Session,
    principal: Principal,
    *,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    new: dict[str, Any] | None,
    reason: str,
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            previous_value=None,
            new_value=new,
            reason=reason[:500],
        )
    )
