import json
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import get_settings
from app.integrations.openai_client import OpenAIClientError, OpenAIResponsesClient
from app.models.foundation import (
    ActivityEvent,
    AiAgentDefinition,
    AiPromptVersion,
    AiRunLog,
    AiToolCallLog,
    AiToolPermission,
    ApprovalRequest,
    AuditEvent,
    Contact,
    ContactMethod,
    Lead,
    LeadFormSubmission,
    Property,
)
from app.schemas.ai import (
    AiAgentCreate,
    AiAgentRead,
    AiControlOverview,
    AiControlSummary,
    AiPromptVersionCreate,
    AiPromptVersionRead,
    AiRunCreate,
    AiRunRead,
    AiToolCallRead,
    AiToolPermissionRead,
)

AGENT_STATUSES = {"draft", "active", "paused", "retired"}
RISK_LEVELS = {"low", "medium", "high"}
PROMPT_STATUSES = {"draft", "active", "retired"}
RUN_STATUSES = {"queued", "running", "completed", "failed", "needs_review"}
TOOL_PERMISSION_LEVELS = {"read", "draft", "propose", "write_blocked"}
TOOL_CALL_STATUSES = {"proposed", "completed", "failed", "blocked", "pending_approval"}
LEAD_INTAKE_AGENT_KEY = "lead_intake_summary"
LEAD_INTAKE_PROMPT = """You are Stonegate Home Buyers' lead intake summary agent.

Summarize the seller lead for an acquisitions teammate. Keep the output concise and operational.

Return these sections:
1. Seller situation
2. Urgency and motivation
3. Known property facts
4. Missing questions to ask next
5. Recommended next task

Rules:
- Do not invent facts.
- Use plain language.
- Flag uncertainty clearly.
- Do not send messages or make external tool calls.
- Keep the total response under 220 words."""


def get_ai_overview(db: Session, principal: Principal) -> AiControlOverview:
    agents = db.scalars(
        select(AiAgentDefinition)
        .where(AiAgentDefinition.organization_id == principal.organization_id)
        .order_by(AiAgentDefinition.created_at.desc())
        .limit(100)
    ).all()
    agent_ids = [agent.id for agent in agents]
    tool_permissions_by_agent = get_tool_permissions_by_agent(db, principal, agent_ids)
    prompt_versions = db.scalars(
        select(AiPromptVersion)
        .where(AiPromptVersion.organization_id == principal.organization_id)
        .order_by(AiPromptVersion.created_at.desc())
        .limit(100)
    ).all()
    runs = db.scalars(
        select(AiRunLog)
        .where(AiRunLog.organization_id == principal.organization_id)
        .order_by(AiRunLog.created_at.desc())
        .limit(100)
    ).all()
    tool_calls_by_run = get_tool_calls_by_run(db, principal, [run.id for run in runs])
    return AiControlOverview(
        summary=get_ai_summary(db, principal),
        agents=[
            agent_to_read(agent, tool_permissions_by_agent.get(agent.id, []))
            for agent in agents
        ],
        prompt_versions=[prompt_to_read(prompt) for prompt in prompt_versions],
        runs=[run_to_read(run, tool_calls_by_run.get(run.id, [])) for run in runs],
    )


def create_ai_agent(
    db: Session,
    principal: Principal,
    payload: AiAgentCreate,
) -> AiAgentRead:
    validate_agent_payload(payload)
    existing = db.scalar(
        select(AiAgentDefinition).where(
            AiAgentDefinition.organization_id == principal.organization_id,
            AiAgentDefinition.key == payload.key,
        )
    )
    if existing is not None:
        raise ValueError("AI agent key already exists.")
    agent = AiAgentDefinition(
        organization_id=principal.organization_id,
        key=payload.key,
        name=payload.name,
        description=payload.description,
        status=payload.status,
        model_name=payload.model_name,
        risk_level=payload.risk_level,
        requires_human_approval=payload.requires_human_approval,
    )
    db.add(agent)
    db.flush()
    tool_permissions: list[AiToolPermission] = []
    for tool_payload in payload.tool_permissions:
        validate_tool_permission(tool_payload.permission_level)
        permission = AiToolPermission(
            organization_id=principal.organization_id,
            agent_definition_id=agent.id,
            tool_key=tool_payload.tool_key,
            tool_name=tool_payload.tool_name,
            permission_level=tool_payload.permission_level,
            is_enabled=tool_payload.is_enabled,
            requires_approval=tool_payload.requires_approval,
        )
        db.add(permission)
        tool_permissions.append(permission)
    add_ai_audit(
        db,
        principal,
        "ai.agent_create",
        "ai_agent_definition",
        agent.id,
        {"key": agent.key, "status": agent.status, "risk_level": agent.risk_level},
    )
    db.commit()
    db.refresh(agent)
    for permission in tool_permissions:
        db.refresh(permission)
    return agent_to_read(agent, tool_permissions)


def create_ai_prompt_version(
    db: Session,
    principal: Principal,
    agent_id: UUID,
    payload: AiPromptVersionCreate,
) -> AiPromptVersionRead | None:
    if payload.status not in PROMPT_STATUSES:
        raise ValueError(f"Unsupported prompt status: {payload.status}")
    agent = get_agent(db, principal, agent_id)
    if agent is None:
        return None
    version_number = int(
        db.scalar(
            select(func.coalesce(func.max(AiPromptVersion.version_number), 0)).where(
                AiPromptVersion.organization_id == principal.organization_id,
                AiPromptVersion.agent_definition_id == agent.id,
            )
        )
        or 0
    ) + 1
    prompt = AiPromptVersion(
        organization_id=principal.organization_id,
        agent_definition_id=agent.id,
        version_number=version_number,
        status=payload.status,
        prompt_text=payload.prompt_text,
        change_notes=payload.change_notes,
        created_by_user_id=principal.user_id,
    )
    db.add(prompt)
    db.flush()
    add_ai_audit(
        db,
        principal,
        "ai.prompt_version_create",
        "ai_prompt_version",
        prompt.id,
        {
            "agent_definition_id": str(agent.id),
            "version_number": prompt.version_number,
            "status": prompt.status,
        },
    )
    db.commit()
    db.refresh(prompt)
    return prompt_to_read(prompt)


def create_ai_run(
    db: Session,
    principal: Principal,
    payload: AiRunCreate,
) -> AiRunRead:
    validate_run_payload(payload)
    agent = get_agent(db, principal, payload.agent_definition_id)
    if agent is None:
        raise ValueError("AI agent not found.")
    prompt = None
    if payload.prompt_version_id is not None:
        prompt = get_prompt(db, principal, agent.id, payload.prompt_version_id)
        if prompt is None:
            raise ValueError("Prompt version not found.")
    if payload.lead_id is not None:
        lead = db.scalar(
            select(Lead).where(
                Lead.organization_id == principal.organization_id,
                Lead.id == payload.lead_id,
            )
        )
        if lead is None:
            raise ValueError("Lead not found.")
    tool_permissions = {
        permission.tool_key: permission
        for permission in db.scalars(
            select(AiToolPermission).where(
                AiToolPermission.organization_id == principal.organization_id,
                AiToolPermission.agent_definition_id == agent.id,
            )
        ).all()
    }
    started_at = payload.started_at or datetime.now(UTC)
    run = AiRunLog(
        organization_id=principal.organization_id,
        agent_definition_id=agent.id,
        prompt_version_id=prompt.id if prompt is not None else None,
        lead_id=payload.lead_id,
        status=payload.status,
        model_name=payload.model_name or agent.model_name,
        input_summary=payload.input_summary,
        output_summary=payload.output_summary,
        total_tokens=payload.total_tokens,
        cost_cents=payload.cost_cents,
        latency_ms=payload.latency_ms,
        started_at=started_at,
        completed_at=payload.completed_at or (
            datetime.now(UTC) if payload.status in {"completed", "failed", "needs_review"} else None
        ),
        error_message=payload.error_message,
    )
    db.add(run)
    db.flush()
    tool_calls: list[AiToolCallLog] = []
    for tool_payload in payload.tool_calls:
        permission = tool_permissions.get(tool_payload.tool_key)
        if permission is None or not permission.is_enabled:
            raise ValueError(f"AI tool is not enabled for this agent: {tool_payload.tool_key}")
        if permission.permission_level == "write_blocked":
            raise ValueError(f"AI tool is write-blocked for this agent: {tool_payload.tool_key}")
        needs_approval = tool_payload.requires_approval or permission.requires_approval
        approval = (
            create_tool_approval(db, principal, run, tool_payload.tool_key)
            if needs_approval
            else None
        )
        tool_call = AiToolCallLog(
            organization_id=principal.organization_id,
            ai_run_log_id=run.id,
            approval_request_id=approval.id if approval is not None else None,
            tool_key=tool_payload.tool_key,
            status="pending_approval" if approval is not None else tool_payload.status,
            requires_approval=needs_approval,
            input_payload=tool_payload.input_payload,
            output_payload=tool_payload.output_payload,
            error_message=tool_payload.error_message,
        )
        db.add(tool_call)
        tool_calls.append(tool_call)
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="ai_run",
            entity_id=run.id,
            event_type="ai.run_logged",
            summary=f"AI run logged for {agent.name}.",
        )
    )
    add_ai_audit(
        db,
        principal,
        "ai.run_log_create",
        "ai_run_log",
        run.id,
        {
            "agent_definition_id": str(agent.id),
            "status": run.status,
            "tool_call_count": len(payload.tool_calls),
            "cost_cents": run.cost_cents,
        },
    )
    db.commit()
    db.refresh(run)
    for tool_call in tool_calls:
        db.refresh(tool_call)
    return run_to_read(run, tool_calls)


def run_lead_intake_summary(
    db: Session,
    principal: Principal,
    lead_id: UUID,
) -> AiRunRead:
    settings = get_settings()
    lead_context = build_lead_context(db, principal, lead_id)
    if lead_context is None:
        raise ValueError("Lead not found.")

    agent = ensure_lead_intake_agent(db, principal, settings.openai_default_model)
    prompt = ensure_lead_intake_prompt(db, principal, agent)
    input_summary = summarize_lead_context_for_log(lead_context)
    started_at = datetime.now(UTC)
    started_monotonic = time.perf_counter()

    if not settings.ai_enabled:
        return create_ai_run(
            db,
            principal,
            AiRunCreate(
                agent_definition_id=agent.id,
                prompt_version_id=prompt.id,
                lead_id=lead_id,
                status="failed",
                model_name=agent.model_name,
                input_summary=input_summary,
                error_message="AI is disabled by AI_ENABLED.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                latency_ms=0,
            ),
        )

    if not settings.openai_api_key:
        return create_ai_run(
            db,
            principal,
            AiRunCreate(
                agent_definition_id=agent.id,
                prompt_version_id=prompt.id,
                lead_id=lead_id,
                status="failed",
                model_name=agent.model_name,
                input_summary=input_summary,
                error_message="OPENAI_API_KEY is not configured.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                latency_ms=0,
            ),
        )

    client = OpenAIResponsesClient(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout_seconds=settings.openai_request_timeout_seconds,
    )
    try:
        response = client.create_text_response(
            model=agent.model_name,
            system_prompt=prompt.prompt_text,
            user_prompt=json.dumps(lead_context, indent=2, sort_keys=True),
        )
        output_summary = truncate_text(
            response.text or "OpenAI returned an empty response.",
            4000,
        )
        status = "needs_review"
        error_message = None
    except OpenAIClientError as exc:
        response = None
        output_summary = None
        status = "failed"
        error_message = str(exc)

    latency_ms = round((time.perf_counter() - started_monotonic) * 1000)
    return create_ai_run(
        db,
        principal,
        AiRunCreate(
            agent_definition_id=agent.id,
            prompt_version_id=prompt.id,
            lead_id=lead_id,
            status=status,
            model_name=agent.model_name,
            input_summary=input_summary,
            output_summary=output_summary,
            total_tokens=response.total_tokens if response is not None else None,
            latency_ms=latency_ms,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            error_message=error_message,
        ),
    )


def ensure_lead_intake_agent(
    db: Session,
    principal: Principal,
    model_name: str,
) -> AiAgentDefinition:
    agent = db.scalar(
        select(AiAgentDefinition).where(
            AiAgentDefinition.organization_id == principal.organization_id,
            AiAgentDefinition.key == LEAD_INTAKE_AGENT_KEY,
        )
    )
    if agent is not None:
        if agent.model_name != model_name:
            agent.model_name = model_name
            db.commit()
            db.refresh(agent)
        return agent

    agent = AiAgentDefinition(
        organization_id=principal.organization_id,
        key=LEAD_INTAKE_AGENT_KEY,
        name="Lead intake summary",
        description="Summarizes seller intake context for acquisitions follow-up.",
        status="active",
        model_name=model_name,
        risk_level="low",
        requires_human_approval=False,
    )
    db.add(agent)
    db.flush()
    db.add(
        AiToolPermission(
            organization_id=principal.organization_id,
            agent_definition_id=agent.id,
            tool_key="leads.read_context",
            tool_name="Read lead context",
            permission_level="read",
            is_enabled=True,
            requires_approval=False,
        )
    )
    add_ai_audit(
        db,
        principal,
        "ai.agent_create",
        "ai_agent_definition",
        agent.id,
        {"key": agent.key, "status": agent.status, "risk_level": agent.risk_level},
    )
    db.commit()
    db.refresh(agent)
    return agent


def ensure_lead_intake_prompt(
    db: Session,
    principal: Principal,
    agent: AiAgentDefinition,
) -> AiPromptVersion:
    prompt = db.scalar(
        select(AiPromptVersion)
        .where(
            AiPromptVersion.organization_id == principal.organization_id,
            AiPromptVersion.agent_definition_id == agent.id,
            AiPromptVersion.status == "active",
        )
        .order_by(AiPromptVersion.version_number.desc())
    )
    if prompt is not None:
        return prompt

    version_number = int(
        db.scalar(
            select(func.coalesce(func.max(AiPromptVersion.version_number), 0)).where(
                AiPromptVersion.organization_id == principal.organization_id,
                AiPromptVersion.agent_definition_id == agent.id,
            )
        )
        or 0
    ) + 1
    prompt = AiPromptVersion(
        organization_id=principal.organization_id,
        agent_definition_id=agent.id,
        version_number=version_number,
        status="active",
        prompt_text=LEAD_INTAKE_PROMPT,
        change_notes="Default lead intake summary prompt.",
        created_by_user_id=principal.user_id,
    )
    db.add(prompt)
    db.flush()
    add_ai_audit(
        db,
        principal,
        "ai.prompt_version_create",
        "ai_prompt_version",
        prompt.id,
        {
            "agent_definition_id": str(agent.id),
            "version_number": prompt.version_number,
            "status": prompt.status,
        },
    )
    db.commit()
    db.refresh(prompt)
    return prompt


def build_lead_context(
    db: Session,
    principal: Principal,
    lead_id: UUID,
) -> dict[str, object] | None:
    lead = db.scalar(
        select(Lead).where(
            Lead.organization_id == principal.organization_id,
            Lead.id == lead_id,
        )
    )
    if lead is None:
        return None
    contact = db.get(Contact, lead.contact_id)
    property_record = db.get(Property, lead.property_id)
    contact_methods = db.scalars(
        select(ContactMethod)
        .where(
            ContactMethod.organization_id == principal.organization_id,
            ContactMethod.contact_id == lead.contact_id,
        )
        .order_by(ContactMethod.is_primary.desc(), ContactMethod.method_type)
    ).all()
    submission = db.scalar(
        select(LeadFormSubmission)
        .where(
            LeadFormSubmission.organization_id == principal.organization_id,
            LeadFormSubmission.lead_id == lead.id,
        )
        .order_by(LeadFormSubmission.created_at.desc())
    )
    return {
        "lead": {
            "id": str(lead.id),
            "source": lead.source,
            "stage": lead.stage_key,
            "temperature": lead.lead_temperature,
            "motivation": lead.motivation,
            "desired_timeline": lead.desired_timeline,
            "property_condition": lead.property_condition,
            "occupancy_status": lead.occupancy_status,
            "asking_price": lead.asking_price,
            "mortgage_balance": lead.mortgage_balance,
            "appointment_status": lead.appointment_status,
            "next_follow_up_at": lead.next_follow_up_at.isoformat()
            if lead.next_follow_up_at
            else None,
            "created_at": lead.created_at.isoformat(),
        },
        "seller": {
            "name": contact.legal_name if contact is not None else None,
            "preferred_name": contact.preferred_name if contact is not None else None,
            "contact_methods": [
                {
                    "type": method.method_type,
                    "value": method.value,
                    "is_primary": method.is_primary,
                }
                for method in contact_methods
            ],
        },
        "property": {
            "street_address": property_record.street_address if property_record else None,
            "city": property_record.city if property_record else None,
            "state": property_record.state if property_record else None,
            "postal_code": property_record.postal_code if property_record else None,
            "county": property_record.county if property_record else None,
            "property_type": property_record.property_type if property_record else None,
        },
        "latest_form_submission": submission.raw_payload if submission is not None else None,
    }


def summarize_lead_context_for_log(lead_context: dict[str, object]) -> str:
    lead = lead_context.get("lead") if isinstance(lead_context.get("lead"), dict) else {}
    seller = lead_context.get("seller") if isinstance(lead_context.get("seller"), dict) else {}
    property_record = (
        lead_context.get("property") if isinstance(lead_context.get("property"), dict) else {}
    )
    address = ", ".join(
        str(value)
        for value in [
            property_record.get("street_address"),
            property_record.get("city"),
            property_record.get("state"),
            property_record.get("postal_code"),
        ]
        if value
    )
    return truncate_text(
        "Lead intake summary request for "
        f"{seller.get('name') or 'unknown seller'} at {address or 'unknown property'}. "
        f"Stage: {lead.get('stage') or 'unknown'}. "
        f"Motivation: {lead.get('motivation') or 'not captured'}. "
        f"Timeline: {lead.get('desired_timeline') or 'not captured'}.",
        4000,
    )


def truncate_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return f"{value[: max_length - 3]}..."


def create_tool_approval(
    db: Session,
    principal: Principal,
    run: AiRunLog,
    tool_key: str,
) -> ApprovalRequest:
    approval = ApprovalRequest(
        organization_id=principal.organization_id,
        requested_by_user_id=principal.user_id,
        assigned_to_user_id=None,
        request_type="ai_tool_call",
        entity_type="ai_run",
        entity_id=run.id,
        status="pending",
        title=f"Approve AI tool call: {tool_key}",
        summary=f"AI requested permission to use {tool_key}. Review before execution.",
        decision_notes=None,
        due_at=None,
        decided_at=None,
        approval_metadata={"tool_key": tool_key, "ai_run_log_id": str(run.id)},
    )
    db.add(approval)
    db.flush()
    return approval


def get_ai_summary(db: Session, principal: Principal) -> AiControlSummary:
    agent_count = count_scalar(
        db,
        select(func.count(AiAgentDefinition.id)).where(
            AiAgentDefinition.organization_id == principal.organization_id
        ),
    )
    active_agent_count = count_scalar(
        db,
        select(func.count(AiAgentDefinition.id)).where(
            AiAgentDefinition.organization_id == principal.organization_id,
            AiAgentDefinition.status == "active",
        ),
    )
    prompt_version_count = count_scalar(
        db,
        select(func.count(AiPromptVersion.id)).where(
            AiPromptVersion.organization_id == principal.organization_id
        ),
    )
    run_count = count_scalar(
        db,
        select(func.count(AiRunLog.id)).where(
            AiRunLog.organization_id == principal.organization_id
        ),
    )
    pending_approval_count = count_scalar(
        db,
        select(func.count(ApprovalRequest.id)).where(
            ApprovalRequest.organization_id == principal.organization_id,
            ApprovalRequest.status == "pending",
        ),
    )
    total_cost_cents = count_scalar(
        db,
        select(func.coalesce(func.sum(AiRunLog.cost_cents), 0)).where(
            AiRunLog.organization_id == principal.organization_id
        ),
    )
    average_latency = db.scalar(
        select(func.avg(AiRunLog.latency_ms)).where(
            AiRunLog.organization_id == principal.organization_id,
            AiRunLog.latency_ms.is_not(None),
        )
    )
    return AiControlSummary(
        agent_count=agent_count,
        active_agent_count=active_agent_count,
        prompt_version_count=prompt_version_count,
        run_count=run_count,
        pending_approval_count=pending_approval_count,
        total_cost_cents=total_cost_cents,
        average_latency_ms=round(float(average_latency)) if average_latency is not None else None,
    )


def get_tool_permissions_by_agent(
    db: Session,
    principal: Principal,
    agent_ids: list[UUID],
) -> dict[UUID, list[AiToolPermission]]:
    if not agent_ids:
        return {}
    permissions = db.scalars(
        select(AiToolPermission).where(
            AiToolPermission.organization_id == principal.organization_id,
            AiToolPermission.agent_definition_id.in_(agent_ids),
        )
    ).all()
    result: dict[UUID, list[AiToolPermission]] = {}
    for permission in permissions:
        result.setdefault(permission.agent_definition_id, []).append(permission)
    return result


def get_tool_calls_by_run(
    db: Session,
    principal: Principal,
    run_ids: list[UUID],
) -> dict[UUID, list[AiToolCallLog]]:
    if not run_ids:
        return {}
    tool_calls = db.scalars(
        select(AiToolCallLog).where(
            AiToolCallLog.organization_id == principal.organization_id,
            AiToolCallLog.ai_run_log_id.in_(run_ids),
        )
    ).all()
    result: dict[UUID, list[AiToolCallLog]] = {}
    for tool_call in tool_calls:
        result.setdefault(tool_call.ai_run_log_id, []).append(tool_call)
    return result


def get_agent(db: Session, principal: Principal, agent_id: UUID) -> AiAgentDefinition | None:
    return db.scalar(
        select(AiAgentDefinition).where(
            AiAgentDefinition.organization_id == principal.organization_id,
            AiAgentDefinition.id == agent_id,
        )
    )


def get_prompt(
    db: Session,
    principal: Principal,
    agent_id: UUID,
    prompt_id: UUID,
) -> AiPromptVersion | None:
    return db.scalar(
        select(AiPromptVersion).where(
            AiPromptVersion.organization_id == principal.organization_id,
            AiPromptVersion.agent_definition_id == agent_id,
            AiPromptVersion.id == prompt_id,
        )
    )


def validate_agent_payload(payload: AiAgentCreate) -> None:
    if payload.status not in AGENT_STATUSES:
        raise ValueError(f"Unsupported AI agent status: {payload.status}")
    if payload.risk_level not in RISK_LEVELS:
        raise ValueError(f"Unsupported AI risk level: {payload.risk_level}")
    for tool_permission in payload.tool_permissions:
        validate_tool_permission(tool_permission.permission_level)


def validate_tool_permission(permission_level: str) -> None:
    if permission_level not in TOOL_PERMISSION_LEVELS:
        raise ValueError(f"Unsupported AI tool permission level: {permission_level}")


def validate_run_payload(payload: AiRunCreate) -> None:
    if payload.status not in RUN_STATUSES:
        raise ValueError(f"Unsupported AI run status: {payload.status}")
    for tool_call in payload.tool_calls:
        if tool_call.status not in TOOL_CALL_STATUSES:
            raise ValueError(f"Unsupported AI tool call status: {tool_call.status}")


def add_ai_audit(
    db: Session,
    principal: Principal,
    action: str,
    entity_type: str,
    entity_id: UUID,
    new_value: dict[str, object],
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
            new_value=new_value,
            reason="Manual AI control center entry",
        )
    )


def agent_to_read(
    agent: AiAgentDefinition,
    tool_permissions: list[AiToolPermission],
) -> AiAgentRead:
    return AiAgentRead(
        id=agent.id,
        key=agent.key,
        name=agent.name,
        description=agent.description,
        status=agent.status,
        model_name=agent.model_name,
        risk_level=agent.risk_level,
        requires_human_approval=agent.requires_human_approval,
        tool_permissions=[tool_permission_to_read(permission) for permission in tool_permissions],
        created_at=agent.created_at,
    )


def tool_permission_to_read(permission: AiToolPermission) -> AiToolPermissionRead:
    return AiToolPermissionRead(
        id=permission.id,
        tool_key=permission.tool_key,
        tool_name=permission.tool_name,
        permission_level=permission.permission_level,
        is_enabled=permission.is_enabled,
        requires_approval=permission.requires_approval,
        created_at=permission.created_at,
    )


def prompt_to_read(prompt: AiPromptVersion) -> AiPromptVersionRead:
    return AiPromptVersionRead(
        id=prompt.id,
        agent_definition_id=prompt.agent_definition_id,
        version_number=prompt.version_number,
        status=prompt.status,
        prompt_text=prompt.prompt_text,
        change_notes=prompt.change_notes,
        created_at=prompt.created_at,
    )


def run_to_read(run: AiRunLog, tool_calls: list[AiToolCallLog]) -> AiRunRead:
    return AiRunRead(
        id=run.id,
        agent_definition_id=run.agent_definition_id,
        prompt_version_id=run.prompt_version_id,
        lead_id=run.lead_id,
        status=run.status,
        model_name=run.model_name,
        input_summary=run.input_summary,
        output_summary=run.output_summary,
        total_tokens=run.total_tokens,
        cost_cents=run.cost_cents,
        latency_ms=run.latency_ms,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error_message=run.error_message,
        tool_calls=[tool_call_to_read(tool_call) for tool_call in tool_calls],
        created_at=run.created_at,
    )


def tool_call_to_read(tool_call: AiToolCallLog) -> AiToolCallRead:
    return AiToolCallRead(
        id=tool_call.id,
        ai_run_log_id=tool_call.ai_run_log_id,
        approval_request_id=tool_call.approval_request_id,
        tool_key=tool_call.tool_key,
        status=tool_call.status,
        requires_approval=tool_call.requires_approval,
        input_payload=tool_call.input_payload,
        output_payload=tool_call.output_payload,
        error_message=tool_call.error_message,
        created_at=tool_call.created_at,
    )


def count_scalar(db: Session, statement: Any) -> int:
    return int(db.scalar(statement) or 0)
