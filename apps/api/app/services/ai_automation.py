from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import get_settings
from app.models.foundation import (
    AiCapabilityRuntimePolicy,
    AiEvaluationDataset,
    AiEvaluationRun,
    AiExternalActionAttempt,
    AiExternalActionPolicy,
    AiRuntimePolicy,
    AuditEvent,
)
from app.schemas.ai_automation import (
    AiExternalActionAttemptRead,
    AiExternalActionPauseCreate,
    AiExternalActionPolicyDecision,
    AiExternalActionPolicyInstallRead,
    AiExternalActionPolicyRead,
    AiExternalActionSimulationCreate,
    AiExternalAutomationMetrics,
    AiExternalAutomationOverview,
)

PROHIBITED_EXTERNAL_ACTIONS = [
    "Cold AI voice outreach",
    "Binding seller offers or price concessions",
    "Contract changes, signatures, releases, or legal interpretations",
    "Final buyer selection or material deal economics",
    "Payments, commissions, budgets, permissions, or suppression overrides",
    "Destructive deletion",
]

POLICY_BLUEPRINTS: tuple[dict[str, Any], ...] = (
    {
        "action_key": "seller_acknowledgement.sms",
        "name": "Consented seller acknowledgement",
        "description": (
            "Acknowledge a seller-initiated request using an approved transactional template."
        ),
        "capability_key": "lead.next_action",
        "channel": "sms",
        "provider_key": "twilio_messaging",
        "owner_role_key": "lead_manager",
        "audience_policy": {
            "required_relationship": "seller_inquiry",
            "allowed_lead_stages": ["new", "contacted", "qualified"],
            "exclude_suppressed": True,
        },
        "consent_policy": {
            "required": True,
            "accepted_sources": ["web_form_sms_consent", "inbound_sms"],
            "stop_override_prohibited": True,
        },
        "template_policy": {
            "approval_required": True,
            "template_family": "seller_request_acknowledgement",
            "freeform_generation_allowed": False,
        },
        "schedule_policy": {
            "contact_hours_required": True,
            "recipient_timezone_required": True,
        },
        "volume_policy": {
            "max_recipients_per_run": 1,
            "max_actions_per_day": 10,
            "max_actions_per_recipient_per_day": 1,
        },
        "cost_policy": {"max_cost_microusd_per_run": 20_000, "max_daily_cost_microusd": 200_000},
        "quality_policy": {
            "minimum_pass_rate_basis_points": 9_800,
            "minimum_reviewed_samples": 50,
            "maximum_critical_failures": 0,
        },
        "canary_policy": {
            "initial_recipient_limit": 1,
            "initial_daily_limit": 5,
            "human_review_percentage": 100,
            "minimum_observation_days": 7,
        },
    },
    {
        "action_key": "appointment_reminder.sms",
        "name": "Appointment confirmation and reminder",
        "description": (
            "Send an approved confirmation or reminder only for a scheduled seller appointment."
        ),
        "capability_key": "appointment.brief",
        "channel": "sms",
        "provider_key": "twilio_messaging",
        "owner_role_key": "acquisitions",
        "audience_policy": {
            "required_relationship": "scheduled_seller_appointment",
            "allowed_appointment_statuses": ["scheduled", "confirmed"],
            "exclude_suppressed": True,
        },
        "consent_policy": {
            "required": True,
            "accepted_sources": ["web_form_sms_consent", "inbound_sms", "staff_documented_consent"],
            "stop_override_prohibited": True,
        },
        "template_policy": {
            "approval_required": True,
            "template_family": "seller_appointment",
            "freeform_generation_allowed": False,
        },
        "schedule_policy": {
            "contact_hours_required": True,
            "recipient_timezone_required": True,
            "maximum_hours_before_appointment": 48,
        },
        "volume_policy": {
            "max_recipients_per_run": 1,
            "max_actions_per_day": 25,
            "max_actions_per_appointment": 2,
        },
        "cost_policy": {"max_cost_microusd_per_run": 20_000, "max_daily_cost_microusd": 500_000},
        "quality_policy": {
            "minimum_pass_rate_basis_points": 9_800,
            "minimum_reviewed_samples": 50,
            "maximum_critical_failures": 0,
        },
        "canary_policy": {
            "initial_recipient_limit": 1,
            "initial_daily_limit": 5,
            "human_review_percentage": 100,
            "minimum_observation_days": 7,
        },
    },
    {
        "action_key": "seller_follow_up.sms",
        "name": "Consented seller follow-up",
        "description": (
            "Send a bounded follow-up from an approved template when the next action is overdue."
        ),
        "capability_key": "lead.next_action",
        "channel": "sms",
        "provider_key": "twilio_messaging",
        "owner_role_key": "lead_manager",
        "audience_policy": {
            "required_relationship": "active_seller_lead",
            "allowed_lead_stages": ["contacted", "qualified", "appointment_set", "follow_up"],
            "exclude_suppressed": True,
        },
        "consent_policy": {
            "required": True,
            "accepted_sources": ["web_form_sms_consent", "inbound_sms", "staff_documented_consent"],
            "stop_override_prohibited": True,
        },
        "template_policy": {
            "approval_required": True,
            "template_family": "seller_follow_up",
            "freeform_generation_allowed": False,
        },
        "schedule_policy": {
            "contact_hours_required": True,
            "recipient_timezone_required": True,
            "minimum_hours_since_last_outbound": 24,
        },
        "volume_policy": {
            "max_recipients_per_run": 5,
            "max_actions_per_day": 25,
            "max_actions_per_recipient_per_week": 3,
        },
        "cost_policy": {"max_cost_microusd_per_run": 100_000, "max_daily_cost_microusd": 500_000},
        "quality_policy": {
            "minimum_pass_rate_basis_points": 9_800,
            "minimum_reviewed_samples": 100,
            "maximum_critical_failures": 0,
        },
        "canary_policy": {
            "initial_recipient_limit": 1,
            "initial_daily_limit": 5,
            "human_review_percentage": 100,
            "minimum_observation_days": 14,
        },
    },
    {
        "action_key": "buyer_campaign.email",
        "name": "Approved buyer campaign delivery",
        "description": (
            "Deliver an owner-approved deal package to a policy-matched buyer audience."
        ),
        "capability_key": "disposition.match",
        "channel": "email",
        "provider_key": "google_workspace",
        "owner_role_key": "dispositions",
        "audience_policy": {
            "required_relationship": "active_buyer",
            "minimum_match_tier": "review",
            "exclude_suppressed": True,
            "owner_approved_audience_required": True,
        },
        "consent_policy": {
            "required": True,
            "accepted_sources": ["buyer_registration", "documented_business_relationship"],
            "unsubscribe_override_prohibited": True,
        },
        "template_policy": {
            "approval_required": True,
            "template_family": "buyer_deal_campaign",
            "freeform_generation_allowed": False,
            "approved_deal_package_required": True,
        },
        "schedule_policy": {
            "contact_hours_required": False,
            "recipient_timezone_required": False,
        },
        "volume_policy": {
            "max_recipients_per_run": 10,
            "max_actions_per_day": 50,
            "max_actions_per_buyer_per_week": 3,
        },
        "cost_policy": {"max_cost_microusd_per_run": 100_000, "max_daily_cost_microusd": 500_000},
        "quality_policy": {
            "minimum_pass_rate_basis_points": 9_800,
            "minimum_reviewed_samples": 50,
            "maximum_critical_failures": 0,
        },
        "canary_policy": {
            "initial_recipient_limit": 5,
            "initial_daily_limit": 10,
            "human_review_percentage": 100,
            "minimum_observation_days": 14,
        },
    },
)

DEFAULT_PAUSE_POLICY = {
    "provider_failure_count": 3,
    "delivery_failure_rate_basis_points": 500,
    "complaint_count": 1,
    "opt_out_rate_basis_points": 200,
    "policy_violation_count": 1,
    "unexpected_cost_overrun_basis_points": 1000,
}
DEFAULT_ROLLBACK_POLICY = {
    "immediate_pause": True,
    "preserve_attempt_history": True,
    "cancel_queued_actions": True,
    "require_owner_review_to_resume": True,
    "human_takeover_required": True,
}


def install_external_action_policies(
    db: Session,
    principal: Principal,
) -> AiExternalActionPolicyInstallRead:
    existing = {
        item.action_key: item
        for item in db.scalars(
            select(AiExternalActionPolicy).where(
                AiExternalActionPolicy.organization_id == principal.organization_id
            )
        ).all()
    }
    created = 0
    for blueprint in POLICY_BLUEPRINTS:
        item = existing.get(blueprint["action_key"])
        if item is None:
            item = AiExternalActionPolicy(
                organization_id=principal.organization_id,
                status="control_only",
                pause_policy=DEFAULT_PAUSE_POLICY,
                rollback_policy=DEFAULT_ROLLBACK_POLICY,
                prohibited_actions=PROHIBITED_EXTERNAL_ACTIONS,
                dry_run_only=True,
                external_delivery_enabled=False,
                updated_by_user_id=principal.user_id,
                **blueprint,
            )
            db.add(item)
            created += 1
            continue
        for key, value in blueprint.items():
            setattr(item, key, value)
        item.pause_policy = DEFAULT_PAUSE_POLICY
        item.rollback_policy = DEFAULT_ROLLBACK_POLICY
        item.prohibited_actions = PROHIBITED_EXTERNAL_ACTIONS
        item.dry_run_only = True
        item.external_delivery_enabled = False
        item.updated_by_user_id = principal.user_id

    _audit(
        db,
        principal,
        action="ai.external_action_controls.install",
        entity_type="ai_external_action_policy",
        entity_id=None,
        new_value={
            "created_policy_count": created,
            "external_delivery_enabled": False,
            "dry_run_only": True,
        },
        reason="Install AI10 external-action controls without activating delivery",
    )
    db.commit()
    return AiExternalActionPolicyInstallRead(
        created_policy_count=created,
        existing_policy_count=len(existing),
        overview=get_external_automation_overview(db, principal),
    )


def decide_external_action_policy(
    db: Session,
    principal: Principal,
    policy_id: UUID,
    payload: AiExternalActionPolicyDecision,
) -> AiExternalActionPolicyRead | None:
    item = _policy(db, principal, policy_id)
    if item is None:
        return None
    previous = {
        "status": item.status,
        "approved_by_user_id": str(item.approved_by_user_id)
        if item.approved_by_user_id
        else None,
    }
    if payload.decision == "approve_control":
        item.status = "paused" if item.status == "paused" else "control_approved"
        item.approved_by_user_id = principal.user_id
        item.approved_at = datetime.now(UTC)
    else:
        item.status = "paused" if item.status == "paused" else "control_only"
        item.approved_by_user_id = None
        item.approved_at = None
    item.external_delivery_enabled = False
    item.dry_run_only = True
    item.updated_by_user_id = principal.user_id
    _audit(
        db,
        principal,
        action="ai.external_action_policy.decide",
        entity_type="ai_external_action_policy",
        entity_id=item.id,
        previous_value=previous,
        new_value={
            "status": item.status,
            "decision": payload.decision,
            "external_delivery_enabled": False,
        },
        reason=payload.notes,
    )
    db.commit()
    db.refresh(item)
    return _policy_read(db, principal, item)


def simulate_external_action(
    db: Session,
    principal: Principal,
    policy_id: UUID,
    payload: AiExternalActionSimulationCreate,
) -> AiExternalActionAttemptRead | None:
    item = _policy(db, principal, policy_id)
    if item is None:
        return None
    existing = db.scalar(
        select(AiExternalActionAttempt).where(
            AiExternalActionAttempt.organization_id == principal.organization_id,
            AiExternalActionAttempt.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        if existing.policy_id != item.id:
            raise ValueError("The idempotency key belongs to another external-action policy.")
        return _attempt_read(existing)

    readiness_blockers = _readiness_blockers(db, principal, item)
    volume_limit = int(item.canary_policy.get("initial_recipient_limit", 1))
    cost_limit = int(item.cost_policy.get("max_cost_microusd_per_run", 0))
    checks: dict[str, bool] = {
        "consent_verified": payload.consent_verified,
        "template_approved": payload.template_approved,
        "within_contact_hours": (
            payload.within_contact_hours
            or not bool(item.schedule_policy.get("contact_hours_required", True))
        ),
        "frequency_allowed": payload.frequency_allowed,
        "suppression_checked": payload.suppression_checked,
        "human_takeover_ready": payload.human_takeover_ready,
        "within_canary_audience_limit": payload.audience_count <= volume_limit,
        "within_cost_limit": payload.estimated_cost_microusd <= cost_limit,
        "external_delivery_locked": item.dry_run_only and not item.external_delivery_enabled,
    }
    block_reasons = list(readiness_blockers)
    check_labels = {
        "consent_verified": "Recipient consent is not verified.",
        "template_approved": "The message template is not approved.",
        "within_contact_hours": "The proposed action is outside approved contact hours.",
        "frequency_allowed": "The recipient frequency limit is not satisfied.",
        "suppression_checked": "Suppression and opt-out checks are incomplete.",
        "human_takeover_ready": "Human takeover is not ready.",
        "within_canary_audience_limit": (
            f"Audience exceeds the {volume_limit}-recipient initial canary limit."
        ),
        "within_cost_limit": "Estimated cost exceeds the per-run policy limit.",
    }
    for key, label in check_labels.items():
        if not checks[key]:
            block_reasons.append(label)
    block_reasons = list(dict.fromkeys(block_reasons))
    status = "simulation_passed" if not block_reasons else "blocked"
    attempt = AiExternalActionAttempt(
        organization_id=principal.organization_id,
        policy_id=item.id,
        idempotency_key=payload.idempotency_key,
        execution_mode="simulation",
        status=status,
        audience_count=payload.audience_count,
        estimated_cost_microusd=payload.estimated_cost_microusd,
        policy_checks=checks,
        block_reasons=block_reasons,
        external_delivery_attempted=False,
        delivered_count=0,
        requested_by_user_id=principal.user_id,
    )
    db.add(attempt)
    db.flush()
    _audit(
        db,
        principal,
        action="ai.external_action.simulate",
        entity_type="ai_external_action_attempt",
        entity_id=attempt.id,
        new_value={
            "policy_id": str(item.id),
            "status": status,
            "audience_count": payload.audience_count,
            "block_reason_count": len(block_reasons),
            "external_delivery_attempted": False,
            "delivered_count": 0,
        },
        reason="AI10 deterministic control simulation",
    )
    db.commit()
    db.refresh(attempt)
    return _attempt_read(attempt)


def pause_external_action_policy(
    db: Session,
    principal: Principal,
    policy_id: UUID,
    payload: AiExternalActionPauseCreate,
) -> AiExternalActionPolicyRead | None:
    item = _policy(db, principal, policy_id)
    if item is None:
        return None
    previous_status = item.status
    item.status = "paused"
    item.last_pause_reason = payload.reason
    item.paused_at = datetime.now(UTC)
    item.external_delivery_enabled = False
    item.dry_run_only = True
    item.updated_by_user_id = principal.user_id
    _audit(
        db,
        principal,
        action="ai.external_action_policy.pause",
        entity_type="ai_external_action_policy",
        entity_id=item.id,
        previous_value={"status": previous_status},
        new_value={"status": "paused", "external_delivery_enabled": False},
        reason=payload.reason,
    )
    db.commit()
    db.refresh(item)
    return _policy_read(db, principal, item)


def resume_external_action_control(
    db: Session,
    principal: Principal,
    policy_id: UUID,
) -> AiExternalActionPolicyRead | None:
    item = _policy(db, principal, policy_id)
    if item is None:
        return None
    if item.status != "paused":
        raise ValueError("Only a paused external-action policy can resume control simulations.")
    item.status = "control_approved" if item.approved_at else "control_only"
    item.last_pause_reason = None
    item.paused_at = None
    item.external_delivery_enabled = False
    item.dry_run_only = True
    item.updated_by_user_id = principal.user_id
    _audit(
        db,
        principal,
        action="ai.external_action_policy.resume_control",
        entity_type="ai_external_action_policy",
        entity_id=item.id,
        previous_value={"status": "paused"},
        new_value={"status": item.status, "external_delivery_enabled": False},
        reason="Resume AI10 control simulations; external delivery remains locked",
    )
    db.commit()
    db.refresh(item)
    return _policy_read(db, principal, item)


def get_external_automation_overview(
    db: Session,
    principal: Principal,
) -> AiExternalAutomationOverview:
    policies = db.scalars(
        select(AiExternalActionPolicy)
        .where(AiExternalActionPolicy.organization_id == principal.organization_id)
        .order_by(AiExternalActionPolicy.action_key)
    ).all()
    runtime = db.scalar(
        select(AiRuntimePolicy).where(
            AiRuntimePolicy.organization_id == principal.organization_id
        )
    )

    def count(model: Any, *conditions: Any) -> int:
        return int(
            db.scalar(
                select(func.count(model.id)).where(
                    model.organization_id == principal.organization_id,
                    *conditions,
                )
            )
            or 0
        )

    policy_reads = [_policy_read(db, principal, item) for item in policies]
    canary_ready_count = sum(
        1 for item in policy_reads if item.readiness_status == "ready_for_activation_review"
    )
    external_delivery_globally_enabled = bool(
        runtime
        and runtime.external_actions_enabled
        and not runtime.emergency_stop
    )
    return AiExternalAutomationOverview(
        phase_status="control_plane_only",
        external_delivery_globally_enabled=external_delivery_globally_enabled,
        emergency_stop=bool(runtime and runtime.emergency_stop),
        metrics=AiExternalAutomationMetrics(
            policy_count=len(policies),
            control_only_count=sum(
                1 for item in policies if item.status in {"control_only", "control_approved"}
            ),
            paused_count=sum(1 for item in policies if item.status == "paused"),
            canary_ready_count=canary_ready_count,
            external_delivery_enabled_count=sum(
                1 for item in policies if item.external_delivery_enabled
            ),
            simulation_count=count(AiExternalActionAttempt),
            blocked_simulation_count=count(
                AiExternalActionAttempt,
                AiExternalActionAttempt.status == "blocked",
            ),
            external_delivery_attempt_count=count(
                AiExternalActionAttempt,
                AiExternalActionAttempt.external_delivery_attempted.is_(True),
            ),
            delivered_message_count=int(
                db.scalar(
                    select(
                        func.coalesce(func.sum(AiExternalActionAttempt.delivered_count), 0)
                    ).where(
                        AiExternalActionAttempt.organization_id
                        == principal.organization_id
                    )
                )
                or 0
            ),
        ),
        policies=policy_reads,
    )


def _readiness_blockers(
    db: Session,
    principal: Principal,
    item: AiExternalActionPolicy,
) -> list[str]:
    blockers: list[str] = []
    runtime = db.scalar(
        select(AiRuntimePolicy).where(
            AiRuntimePolicy.organization_id == principal.organization_id
        )
    )
    capability = db.scalar(
        select(AiCapabilityRuntimePolicy).where(
            AiCapabilityRuntimePolicy.organization_id == principal.organization_id,
            AiCapabilityRuntimePolicy.capability_key == item.capability_key,
        )
    )
    approved_dataset = db.scalar(
        select(AiEvaluationDataset.id).where(
            AiEvaluationDataset.organization_id == principal.organization_id,
            AiEvaluationDataset.capability_key == item.capability_key,
            AiEvaluationDataset.status == "approved",
        )
    )
    quality_policy = item.quality_policy
    passing_evaluation = db.scalar(
        select(AiEvaluationRun.id)
        .join(
            AiEvaluationDataset,
            AiEvaluationDataset.id == AiEvaluationRun.dataset_id,
        )
        .where(
            AiEvaluationRun.organization_id == principal.organization_id,
            AiEvaluationDataset.capability_key == item.capability_key,
            AiEvaluationRun.thresholds_passed.is_(True),
            AiEvaluationRun.case_count
            >= int(quality_policy.get("minimum_reviewed_samples", 0)),
            AiEvaluationRun.pass_rate_basis_points
            >= int(quality_policy.get("minimum_pass_rate_basis_points", 0)),
            AiEvaluationRun.critical_failure_count
            <= int(quality_policy.get("maximum_critical_failures", 0)),
        )
    )
    if item.status == "paused":
        blockers.append("This action policy is paused.")
    if item.approved_at is None:
        blockers.append("The action control contract has not been owner-approved.")
    if runtime is None:
        blockers.append("The governed AI runtime is not installed.")
    else:
        if runtime.emergency_stop:
            blockers.append("The AI emergency stop is active.")
        if not runtime.external_actions_enabled:
            blockers.append("Global external actions are disabled.")
    if capability is None or capability.status != "enabled":
        blockers.append(f"The {item.capability_key} capability is not enabled.")
    if approved_dataset is None:
        blockers.append("No owner-approved evaluation dataset covers this capability.")
    if passing_evaluation is None:
        blockers.append(
            "No evaluation run satisfies this action's sample, quality, and safety thresholds."
        )
    settings = get_settings()
    if item.provider_key == "twilio_messaging":
        if not settings.twilio_sms_configured:
            blockers.append("The approved Twilio Messaging configuration is incomplete.")
    elif item.provider_key == "google_workspace":
        if settings.email_configuration_blockers:
            blockers.append("The approved Google Workspace email configuration is incomplete.")
    else:
        blockers.append(f"The {item.provider_key} provider has no approved adapter.")
    if item.dry_run_only or not item.external_delivery_enabled:
        blockers.append("External delivery is locked by the AI10 control-plane release.")
    return blockers


def _policy(
    db: Session,
    principal: Principal,
    policy_id: UUID,
) -> AiExternalActionPolicy | None:
    return db.scalar(
        select(AiExternalActionPolicy).where(
            AiExternalActionPolicy.organization_id == principal.organization_id,
            AiExternalActionPolicy.id == policy_id,
        )
    )


def _policy_read(
    db: Session,
    principal: Principal,
    item: AiExternalActionPolicy,
) -> AiExternalActionPolicyRead:
    attempts = db.scalars(
        select(AiExternalActionAttempt)
        .where(
            AiExternalActionAttempt.organization_id == principal.organization_id,
            AiExternalActionAttempt.policy_id == item.id,
        )
        .order_by(AiExternalActionAttempt.created_at.desc())
        .limit(10)
    ).all()
    blockers = _readiness_blockers(db, principal, item)
    only_release_lock = blockers == [
        "External delivery is locked by the AI10 control-plane release."
    ]
    return AiExternalActionPolicyRead(
        id=item.id,
        action_key=item.action_key,
        name=item.name,
        description=item.description,
        capability_key=item.capability_key,
        channel=item.channel,
        provider_key=item.provider_key,
        owner_role_key=item.owner_role_key,
        status=item.status,
        audience_policy=item.audience_policy,
        consent_policy=item.consent_policy,
        template_policy=item.template_policy,
        schedule_policy=item.schedule_policy,
        volume_policy=item.volume_policy,
        cost_policy=item.cost_policy,
        quality_policy=item.quality_policy,
        canary_policy=item.canary_policy,
        pause_policy=item.pause_policy,
        rollback_policy=item.rollback_policy,
        prohibited_actions=item.prohibited_actions,
        dry_run_only=item.dry_run_only,
        external_delivery_enabled=item.external_delivery_enabled,
        approved_by_user_id=item.approved_by_user_id,
        approved_at=item.approved_at,
        last_pause_reason=item.last_pause_reason,
        paused_at=item.paused_at,
        readiness_status=(
            "ready_for_activation_review" if only_release_lock else "blocked"
        ),
        readiness_blockers=blockers,
        attempts=[_attempt_read(attempt) for attempt in attempts],
        updated_at=item.updated_at,
    )


def _attempt_read(item: AiExternalActionAttempt) -> AiExternalActionAttemptRead:
    return AiExternalActionAttemptRead(
        id=item.id,
        policy_id=item.policy_id,
        idempotency_key=item.idempotency_key,
        execution_mode=item.execution_mode,
        status=item.status,
        audience_count=item.audience_count,
        estimated_cost_microusd=item.estimated_cost_microusd,
        policy_checks=item.policy_checks,
        block_reasons=item.block_reasons,
        external_delivery_attempted=item.external_delivery_attempted,
        delivered_count=item.delivered_count,
        requested_by_user_id=item.requested_by_user_id,
        created_at=item.created_at,
    )


def _audit(
    db: Session,
    principal: Principal,
    *,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    new_value: dict[str, object],
    reason: str,
    previous_value: dict[str, object] | None = None,
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            previous_value=previous_value,
            new_value=new_value,
            reason=reason,
        )
    )
