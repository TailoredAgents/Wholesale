from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.ai import (
    AiAgentCreate,
    AiAgentRead,
    AiControlOverview,
    AiPromptVersionCreate,
    AiPromptVersionRead,
    AiRunCreate,
    AiRunRead,
)
from app.services.ai import (
    create_ai_agent,
    create_ai_prompt_version,
    create_ai_run,
    get_ai_overview,
)

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])
change_ai_dependency = require_permission(PermissionKeys.CHANGE_AI_PROMPTS)


@router.get("")
def read_ai_overview(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiControlOverview:
    return get_ai_overview(db, principal)


@router.post("/agents", status_code=201)
def create_agent(
    payload: AiAgentCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiAgentRead:
    try:
        return create_ai_agent(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post("/agents/{agent_id}/prompts", status_code=201)
def create_prompt_version(
    agent_id: UUID,
    payload: AiPromptVersionCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiPromptVersionRead:
    try:
        prompt = create_ai_prompt_version(db, principal, agent_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if prompt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI agent not found.")
    return prompt


@router.post("/runs", status_code=201)
def create_run_log(
    payload: AiRunCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiRunRead:
    try:
        return create_ai_run(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
