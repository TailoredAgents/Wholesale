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
    AiCopilotFoundationDecision,
    AiCopilotFoundationInstallRead,
    AiCopilotFoundationRead,
    AiDryRunCreate,
    AiEvaluationDatasetCreate,
    AiEvaluationDatasetRead,
    AiEvaluationDecision,
    AiEvaluationRunCreate,
    AiEvaluationRunRead,
    AiOrchestratorEventCreate,
    AiOrchestratorEventRead,
    AiPortfolioInstallRead,
    AiPromotionCreate,
    AiPromotionRead,
    AiPromptVersionCreate,
    AiPromptVersionRead,
    AiRollbackCreate,
    AiRunCreate,
    AiRunRead,
    AiTraceReview,
    LeadIntakeSummaryRunCreate,
)
from app.services.ai import (
    create_ai_agent,
    create_ai_prompt_version,
    create_ai_run,
    get_ai_overview,
    run_lead_intake_summary,
)
from app.services.ai_copilots import (
    decide_copilot_foundation,
    install_copilot_foundation,
)
from app.services.ai_orchestrator import (
    create_dataset,
    create_dry_run,
    decide_dataset,
    install_portfolio,
    register_event,
    request_promotion,
    retry_run,
    review_trace,
    rollback_promotion,
    run_evaluation,
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


@router.post("/lead-intake-summary", status_code=201)
def create_lead_intake_summary_run(
    payload: LeadIntakeSummaryRunCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiRunRead:
    try:
        return run_lead_intake_summary(db, principal, payload.lead_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post("/orchestrator/portfolio/install", status_code=201)
def install_agent_portfolio(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiPortfolioInstallRead:
    return install_portfolio(db, principal)


@router.post("/copilots/install", status_code=201)
def install_ai_copilot_foundation(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiCopilotFoundationInstallRead:
    try:
        return install_copilot_foundation(db, principal)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/copilots/foundation/decision")
def decide_ai_copilot_foundation(
    payload: AiCopilotFoundationDecision,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiCopilotFoundationRead:
    try:
        return decide_copilot_foundation(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/orchestrator/events", status_code=201)
def create_orchestrator_event(
    payload: AiOrchestratorEventCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiOrchestratorEventRead:
    return register_event(db, principal, payload)


@router.post("/orchestrator/dry-runs", status_code=201)
def create_orchestrator_dry_run(
    payload: AiDryRunCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiRunRead:
    try:
        return create_dry_run(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/orchestrator/runs/{run_id}/retry", status_code=201)
def retry_orchestrator_run(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiRunRead:
    try:
        result = retry_run(db, principal, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="AI run not found.")
    return result


@router.post("/orchestrator/runs/{run_id}/review")
def review_orchestrator_trace(
    run_id: UUID,
    payload: AiTraceReview,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiRunRead:
    result = review_trace(db, principal, run_id, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="AI run not found.")
    return result


@router.post("/orchestrator/evaluation-datasets", status_code=201)
def create_evaluation_dataset(
    payload: AiEvaluationDatasetCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiEvaluationDatasetRead:
    try:
        return create_dataset(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/orchestrator/evaluation-datasets/{dataset_id}/decision")
def decide_evaluation_dataset(
    dataset_id: UUID,
    payload: AiEvaluationDecision,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiEvaluationDatasetRead:
    try:
        result = decide_dataset(db, principal, dataset_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Evaluation dataset not found.")
    return result


@router.post("/orchestrator/evaluations", status_code=201)
def create_evaluation_run(
    payload: AiEvaluationRunCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiEvaluationRunRead:
    try:
        return run_evaluation(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/orchestrator/agents/{agent_id}/promotions", status_code=201)
def create_capability_promotion(
    agent_id: UUID,
    payload: AiPromotionCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiPromotionRead:
    try:
        return request_promotion(db, principal, agent_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/orchestrator/promotions/{promotion_id}/rollback")
def rollback_capability_promotion(
    promotion_id: UUID,
    payload: AiRollbackCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiPromotionRead:
    try:
        result = rollback_promotion(db, principal, promotion_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="AI promotion not found.")
    return result
