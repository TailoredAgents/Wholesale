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
    AiCapabilityRuntimeUpdate,
    AiControlOverview,
    AiCopilotFoundationDecision,
    AiCopilotFoundationInstallRead,
    AiCopilotFoundationRead,
    AiCorrectedEvaluationCaseCreate,
    AiDryRunCreate,
    AiEvaluationComparisonCreate,
    AiEvaluationComparisonRead,
    AiEvaluationDatasetCreate,
    AiEvaluationDatasetRead,
    AiEvaluationDecision,
    AiEvaluationReviewCreate,
    AiEvaluationRunCreate,
    AiEvaluationRunRead,
    AiGoldenLibraryInstallRead,
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
    AiRuntimeExecuteCreate,
    AiRuntimeInstallRead,
    AiRuntimeOverview,
    AiRuntimePolicyUpdate,
    AiRuntimeShutdownCreate,
    AiTraceReview,
    LeadIntakeSummaryRunCreate,
)
from app.schemas.ai_automation import (
    AiExternalActionAttemptRead,
    AiExternalActionPauseCreate,
    AiExternalActionPolicyDecision,
    AiExternalActionPolicyInstallRead,
    AiExternalActionPolicyRead,
    AiExternalActionSimulationCreate,
    AiExternalAutomationOverview,
)
from app.services.ai import (
    create_ai_agent,
    create_ai_prompt_version,
    create_ai_run,
    get_ai_overview,
    run_lead_intake_summary,
)
from app.services.ai_automation import (
    decide_external_action_policy,
    get_external_automation_overview,
    install_external_action_policies,
    pause_external_action_policy,
    resume_external_action_control,
    simulate_external_action,
)
from app.services.ai_copilots import (
    decide_copilot_foundation,
    install_copilot_foundation,
)
from app.services.ai_evaluation_library import install_golden_library
from app.services.ai_orchestrator import (
    add_corrected_case_version,
    create_dataset,
    create_dry_run,
    decide_dataset,
    install_portfolio,
    register_event,
    request_promotion,
    retry_run,
    review_dataset,
    review_trace,
    rollback_promotion,
    run_evaluation,
)
from app.services.ai_runtime import (
    compare_evaluations,
    emergency_shutdown,
    execute_runtime,
    install_runtime,
    update_capability_runtime,
    update_runtime_policy,
)

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])
change_ai_dependency = require_permission(PermissionKeys.CHANGE_AI_PROMPTS)


@router.get("")
def read_ai_overview(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiControlOverview:
    return get_ai_overview(db, principal)


@router.get("/automation")
def read_external_automation(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiExternalAutomationOverview:
    return get_external_automation_overview(db, principal)


@router.post("/automation/install", status_code=201)
def install_external_automation_controls(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiExternalActionPolicyInstallRead:
    return install_external_action_policies(db, principal)


@router.post("/automation/policies/{policy_id}/decision")
def decide_external_automation_control(
    policy_id: UUID,
    payload: AiExternalActionPolicyDecision,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiExternalActionPolicyRead:
    result = decide_external_action_policy(db, principal, policy_id, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="External-action policy not found.")
    return result


@router.post("/automation/policies/{policy_id}/simulations", status_code=201)
def simulate_external_automation_control(
    policy_id: UUID,
    payload: AiExternalActionSimulationCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiExternalActionAttemptRead:
    try:
        result = simulate_external_action(db, principal, policy_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="External-action policy not found.")
    return result


@router.post("/automation/policies/{policy_id}/pause")
def pause_external_automation_control(
    policy_id: UUID,
    payload: AiExternalActionPauseCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiExternalActionPolicyRead:
    result = pause_external_action_policy(db, principal, policy_id, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="External-action policy not found.")
    return result


@router.post("/automation/policies/{policy_id}/resume-control")
def resume_external_automation_simulations(
    policy_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiExternalActionPolicyRead:
    try:
        result = resume_external_action_control(db, principal, policy_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="External-action policy not found.")
    return result


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


@router.post("/runtime/install", status_code=201)
def install_ai_runtime(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiRuntimeInstallRead:
    try:
        return install_runtime(db, principal)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/runtime/policy")
def patch_ai_runtime_policy(
    payload: AiRuntimePolicyUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiRuntimeOverview:
    try:
        return update_runtime_policy(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/runtime/capabilities/{capability_key:path}")
def patch_ai_capability_runtime(
    capability_key: str,
    payload: AiCapabilityRuntimeUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiRuntimeOverview:
    try:
        return update_capability_runtime(db, principal, capability_key, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/runtime/shutdown")
def stop_ai_runtime(
    payload: AiRuntimeShutdownCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiRuntimeOverview:
    try:
        return emergency_shutdown(db, principal, payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/runtime/execute", status_code=201)
def execute_ai_runtime(
    payload: AiRuntimeExecuteCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiRunRead:
    try:
        return execute_runtime(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/runtime/evaluation-comparisons", status_code=201)
def compare_ai_evaluation_runs(
    payload: AiEvaluationComparisonCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiEvaluationComparisonRead:
    try:
        return compare_evaluations(db, principal, payload)
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


@router.post("/evaluation-library/install", status_code=201)
def install_ai2_golden_library(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiGoldenLibraryInstallRead:
    try:
        return install_golden_library(db, principal)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/orchestrator/evaluation-datasets/{dataset_id}/reviews")
def review_evaluation_dataset(
    dataset_id: UUID,
    payload: AiEvaluationReviewCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiEvaluationDatasetRead:
    try:
        result = review_dataset(db, principal, dataset_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Evaluation dataset not found.")
    return result


@router.post(
    "/orchestrator/evaluation-datasets/{dataset_id}/corrected-cases",
    status_code=201,
)
def create_corrected_evaluation_case_version(
    dataset_id: UUID,
    payload: AiCorrectedEvaluationCaseCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(change_ai_dependency)],
) -> AiEvaluationDatasetRead:
    try:
        result = add_corrected_case_version(db, principal, dataset_id, payload)
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
