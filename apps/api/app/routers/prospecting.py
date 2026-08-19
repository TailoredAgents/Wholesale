from typing import Annotated, Literal, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.integrations.voice_call_provider import VoiceCallProviderError
from app.schemas.prospecting import (
    DialerContextRead,
    ProspectHandoffDecision,
    ProspectHandoffRead,
    ProspectingAttemptComplete,
    ProspectingBrowserVoiceSessionRead,
    ProspectingCallEvidenceRead,
    ProspectingCallQualityAnalyzeRead,
    ProspectingCallQualityRead,
    ProspectingCallQualityReviewRequest,
    ProspectingCopilotAnalyzeRead,
    ProspectingCopilotAnalyzeRequest,
    ProspectingCopilotReviewRead,
    ProspectingCopilotReviewRequest,
    ProspectingDialerOperationsRead,
    ProspectingDialerProfileRead,
    ProspectingDialerProfileUpsert,
    ProspectingDialerSwitchRead,
    ProspectingDialerSwitchUpdate,
    ProspectingDialSessionControlRead,
    ProspectingDialSessionEndCommand,
    ProspectingDialSessionLeaseCommand,
    ProspectingDialSessionOperationRead,
    ProspectingDialSessionRecoveryCommand,
    ProspectingDialSessionSnapshotRead,
    ProspectingDialSessionStart,
    ProspectingEntryRead,
    ProspectingInboundCallbackListRead,
    ProspectingManagerSessionRecoveryCommand,
    ProspectingManagerSessionStopCommand,
    ProspectingQualificationAutosaveRequest,
    ProspectingQualificationChecklistItemRead,
    ProspectingQualificationChecklistRead,
    ProspectingScriptCreate,
    ProspectingScriptRead,
    ProspectingTechnicalFailureComplete,
    ProspectingVoiceCallControl,
    ProspectingVoiceCallCreate,
    ProspectingVoiceCallRead,
    ProspectingWorkbenchOverview,
)
from app.services.lead_lifecycle import LeadLifecycleConflictError
from app.services.prospecting import (
    ProspectingCompletionConflictError,
    ProspectingQualificationConflictError,
    approve_script,
    autosave_attempt_qualification,
    complete_attempt,
    complete_technical_failure,
    create_script,
    decide_handoff,
    get_attempt_qualification,
    get_prospecting_overview,
    start_attempt,
)
from app.services.prospecting_callbacks import (
    get_prospecting_callback_prospect,
    list_prospecting_inbound_callbacks,
)
from app.services.prospecting_copilot import (
    analyze_call_quality,
    analyze_entry,
    review_call_quality,
    review_recommendation,
)
from app.services.prospecting_dialer import (
    ProspectingDialerConfigurationError,
    ProspectingDialerConflictError,
    end_dial_session,
    get_dialer_context,
    heartbeat_dial_session,
    list_dialer_profiles,
    pause_dial_session,
    read_dial_session,
    recover_dial_session,
    reserve_next_dial_record,
    resume_dial_session,
    start_dial_session,
    update_campaign_dialer_switch,
    update_company_dialer_switch,
    upsert_dialer_profile,
)
from app.services.prospecting_dialer_operations import (
    ProspectingDialerOperationsConflictError,
    get_prospecting_dialer_operations,
    manager_recover_dial_session,
    manager_stop_dial_session,
)
from app.services.prospecting_evidence import get_prospecting_call_evidence
from app.services.prospecting_voice import (
    ProspectingVoiceConfigurationError,
    ProspectingVoiceConflictError,
    control_prospecting_voice_call,
    create_prospecting_browser_voice_session,
    fetch_prospecting_voice_call,
    prepare_browser_prospecting_voice_call,
    start_prospecting_voice_call,
)

router = APIRouter(prefix="/api/v1/prospecting", tags=["prospecting"])
work_dependency = require_any_permission(
    PermissionKeys.WORK_ASSIGNED_CALLING_LISTS,
    PermissionKeys.MANAGE_ACQUISITION_OPERATIONS,
)
manage_dependency = require_permission(PermissionKeys.MANAGE_ACQUISITION_OPERATIONS)
recording_dependency = require_permission(PermissionKeys.ACCESS_RECORDINGS)


def _mark_sensitive_response_no_store(response: Response) -> None:
    """Prevent browser/proxy storage of responses containing leases or Voice JWTs."""

    response.headers["Cache-Control"] = "private, no-store"


def _raise_prospecting_voice_error(exc: Exception) -> NoReturn:
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if isinstance(exc, ProspectingVoiceConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, ProspectingVoiceConfigurationError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if isinstance(exc, VoiceCallProviderError):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    raise exc


def _raise_prospecting_dialer_error(exc: Exception) -> NoReturn:
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if isinstance(
        exc,
        (
            ProspectingDialerConflictError,
            ProspectingQualificationConflictError,
            ProspectingCompletionConflictError,
        ),
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, ProspectingDialerConfigurationError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    raise exc


def _raise_prospecting_operations_error(exc: Exception) -> NoReturn:
    if isinstance(exc, ProspectingDialerOperationsConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, VoiceCallProviderError):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    raise exc


@router.get("/dialer/context")
def read_native_dialer_context(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> DialerContextRead:
    return get_dialer_context(db, principal)


@router.get("/dialer/profiles")
def read_native_dialer_profiles(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> list[ProspectingDialerProfileRead]:
    return list_dialer_profiles(db, principal)


@router.get("/dialer/operations")
def read_native_dialer_operations(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> ProspectingDialerOperationsRead:
    _mark_sensitive_response_no_store(response)
    return get_prospecting_dialer_operations(db, principal)


@router.get("/dialer/callbacks")
def read_native_dialer_callbacks(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
    limit: int = 50,
) -> ProspectingInboundCallbackListRead:
    _mark_sensitive_response_no_store(response)
    return list_prospecting_inbound_callbacks(db, principal, limit=limit)


@router.get("/dialer/callbacks/{callback_id}/prospect")
def read_native_dialer_callback_prospect(
    callback_id: UUID,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingEntryRead:
    _mark_sensitive_response_no_store(response)
    entry = get_prospecting_callback_prospect(db, principal, callback_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Prospecting callback context not found.")
    return entry


@router.post("/dialer/operations/sessions/{session_id}/stop")
def stop_native_dial_session_as_manager(
    session_id: UUID,
    payload: ProspectingManagerSessionStopCommand,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> ProspectingDialSessionOperationRead:
    try:
        result = manager_stop_dial_session(db, principal, session_id, payload)
    except (ProspectingDialerOperationsConflictError, VoiceCallProviderError, ValueError) as exc:
        _raise_prospecting_operations_error(exc)
    if result is None:
        raise HTTPException(status_code=404, detail="Prospecting dial session not found.")
    return result


@router.post("/dialer/operations/sessions/{session_id}/recover")
def recover_native_dial_session_as_manager(
    session_id: UUID,
    payload: ProspectingManagerSessionRecoveryCommand,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> ProspectingDialSessionOperationRead:
    try:
        result = manager_recover_dial_session(db, principal, session_id, payload)
    except (ProspectingDialerOperationsConflictError, VoiceCallProviderError, ValueError) as exc:
        _raise_prospecting_operations_error(exc)
    if result is None:
        raise HTTPException(status_code=404, detail="Prospecting dial session not found.")
    return result


@router.put("/dialer/profiles/{user_id}")
def configure_native_dialer_profile(
    user_id: UUID,
    payload: ProspectingDialerProfileUpsert,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> ProspectingDialerProfileRead:
    try:
        profile = upsert_dialer_profile(db, principal, user_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if profile is None:
        raise HTTPException(status_code=404, detail="Cold-calling user not found.")
    return profile


@router.post("/dialer/sessions", status_code=201)
def create_native_dial_session(
    payload: ProspectingDialSessionStart,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingDialSessionControlRead:
    _mark_sensitive_response_no_store(response)
    try:
        result = start_dial_session(db, principal, payload)
    except (
        PermissionError,
        ProspectingDialerConflictError,
        ProspectingDialerConfigurationError,
        ValueError,
    ) as exc:
        _raise_prospecting_dialer_error(exc)
    if result is None:
        raise HTTPException(status_code=404, detail="Prospecting dialer setup not found.")
    return result


@router.get("/dialer/sessions/{session_id}")
def get_native_dial_session(
    session_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingDialSessionSnapshotRead:
    try:
        result = read_dial_session(db, principal, session_id)
    except (
        PermissionError,
        ProspectingDialerConflictError,
        ProspectingDialerConfigurationError,
        ValueError,
    ) as exc:
        _raise_prospecting_dialer_error(exc)
    if result is None:
        raise HTTPException(status_code=404, detail="Prospecting dial session not found.")
    return result


@router.post("/dialer/sessions/{session_id}/heartbeat")
def heartbeat_native_dial_session(
    session_id: UUID,
    payload: ProspectingDialSessionLeaseCommand,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingDialSessionControlRead:
    _mark_sensitive_response_no_store(response)
    try:
        result = heartbeat_dial_session(db, principal, session_id, payload)
    except (
        PermissionError,
        ProspectingDialerConflictError,
        ProspectingDialerConfigurationError,
        ValueError,
    ) as exc:
        _raise_prospecting_dialer_error(exc)
    if result is None:
        raise HTTPException(status_code=404, detail="Prospecting dial session not found.")
    return result


@router.post("/dialer/sessions/{session_id}/pause")
def pause_native_dial_session(
    session_id: UUID,
    payload: ProspectingDialSessionLeaseCommand,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingDialSessionControlRead:
    _mark_sensitive_response_no_store(response)
    try:
        result = pause_dial_session(db, principal, session_id, payload)
    except (
        PermissionError,
        ProspectingDialerConflictError,
        ProspectingDialerConfigurationError,
        ValueError,
    ) as exc:
        _raise_prospecting_dialer_error(exc)
    if result is None:
        raise HTTPException(status_code=404, detail="Prospecting dial session not found.")
    return result


@router.post("/dialer/sessions/{session_id}/resume")
def resume_native_dial_session(
    session_id: UUID,
    payload: ProspectingDialSessionLeaseCommand,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingDialSessionControlRead:
    _mark_sensitive_response_no_store(response)
    try:
        result = resume_dial_session(db, principal, session_id, payload)
    except (
        PermissionError,
        ProspectingDialerConflictError,
        ProspectingDialerConfigurationError,
        ValueError,
    ) as exc:
        _raise_prospecting_dialer_error(exc)
    if result is None:
        raise HTTPException(status_code=404, detail="Prospecting dial session not found.")
    return result


@router.post("/dialer/sessions/{session_id}/end")
def end_native_dial_session(
    session_id: UUID,
    payload: ProspectingDialSessionEndCommand,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingDialSessionControlRead:
    _mark_sensitive_response_no_store(response)
    try:
        result = end_dial_session(db, principal, session_id, payload)
    except (
        PermissionError,
        ProspectingDialerConflictError,
        ProspectingDialerConfigurationError,
        ValueError,
    ) as exc:
        _raise_prospecting_dialer_error(exc)
    if result is None:
        raise HTTPException(status_code=404, detail="Prospecting dial session not found.")
    return result


@router.post("/dialer/sessions/{session_id}/recover")
def recover_native_dial_session(
    session_id: UUID,
    payload: ProspectingDialSessionRecoveryCommand,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingDialSessionControlRead:
    _mark_sensitive_response_no_store(response)
    try:
        result = recover_dial_session(db, principal, session_id, payload)
    except (
        PermissionError,
        ProspectingDialerConflictError,
        ProspectingDialerConfigurationError,
        ValueError,
    ) as exc:
        _raise_prospecting_dialer_error(exc)
    if result is None:
        raise HTTPException(status_code=404, detail="Prospecting dial session not found.")
    return result


@router.post("/dialer/sessions/{session_id}/reserve-next")
def reserve_next_native_dial_record(
    session_id: UUID,
    payload: ProspectingDialSessionLeaseCommand,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingDialSessionControlRead:
    _mark_sensitive_response_no_store(response)
    try:
        result = reserve_next_dial_record(db, principal, session_id, payload)
    except (
        PermissionError,
        ProspectingDialerConflictError,
        ProspectingDialerConfigurationError,
        ValueError,
    ) as exc:
        _raise_prospecting_dialer_error(exc)
    if result is None:
        raise HTTPException(status_code=404, detail="Prospecting dial session not found.")
    return result


@router.post("/dialer/sessions/{session_id}/voice-session")
def create_native_browser_voice_session(
    session_id: UUID,
    payload: ProspectingDialSessionLeaseCommand,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingBrowserVoiceSessionRead:
    _mark_sensitive_response_no_store(response)
    try:
        result = create_prospecting_browser_voice_session(db, principal, session_id, payload)
    except (
        PermissionError,
        ProspectingVoiceConflictError,
        ProspectingVoiceConfigurationError,
        ValueError,
    ) as exc:
        _raise_prospecting_voice_error(exc)
    if result is None:
        raise HTTPException(status_code=404, detail="Prospecting dial session not found.")
    return result


@router.put("/dialer/switches/company")
def configure_company_native_dialer_switch(
    payload: ProspectingDialerSwitchUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> ProspectingDialerSwitchRead:
    try:
        result = update_company_dialer_switch(db, principal, payload)
    except (
        PermissionError,
        ProspectingDialerConflictError,
        ProspectingDialerConfigurationError,
        ValueError,
    ) as exc:
        _raise_prospecting_dialer_error(exc)
    if result is None:
        raise HTTPException(status_code=404, detail="Organization not found.")
    return result


@router.put("/dialer/switches/campaigns/{campaign_id}")
def configure_campaign_native_dialer_switch(
    campaign_id: UUID,
    payload: ProspectingDialerSwitchUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> ProspectingDialerSwitchRead:
    try:
        result = update_campaign_dialer_switch(db, principal, campaign_id, payload)
    except (
        PermissionError,
        ProspectingDialerConflictError,
        ProspectingDialerConfigurationError,
        ValueError,
    ) as exc:
        _raise_prospecting_dialer_error(exc)
    if result is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return result


@router.post("/dialer/legs/{dial_leg_id}/call", status_code=201)
def create_native_prospecting_call(
    dial_leg_id: UUID,
    payload: ProspectingVoiceCallCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingVoiceCallRead:
    try:
        call = start_prospecting_voice_call(db, principal, dial_leg_id, payload)
    except (
        PermissionError,
        ProspectingVoiceConflictError,
        ProspectingVoiceConfigurationError,
        VoiceCallProviderError,
        ValueError,
    ) as exc:
        _raise_prospecting_voice_error(exc)
    if call is None:
        raise HTTPException(status_code=404, detail="Prospecting dial leg not found.")
    return call


@router.post("/dialer/legs/{dial_leg_id}/browser-call", status_code=201)
def prepare_native_browser_prospecting_call(
    dial_leg_id: UUID,
    payload: ProspectingVoiceCallCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingVoiceCallRead:
    try:
        call = prepare_browser_prospecting_voice_call(db, principal, dial_leg_id, payload)
    except (
        PermissionError,
        ProspectingVoiceConflictError,
        ProspectingVoiceConfigurationError,
        VoiceCallProviderError,
        ValueError,
    ) as exc:
        _raise_prospecting_voice_error(exc)
    if call is None:
        raise HTTPException(status_code=404, detail="Prospecting dial leg not found.")
    return call


@router.get("/dialer/legs/{dial_leg_id}/call")
def read_native_prospecting_call(
    dial_leg_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingVoiceCallRead:
    try:
        call = fetch_prospecting_voice_call(db, principal, dial_leg_id)
    except (
        PermissionError,
        ProspectingVoiceConflictError,
        ProspectingVoiceConfigurationError,
        VoiceCallProviderError,
        ValueError,
    ) as exc:
        _raise_prospecting_voice_error(exc)
    if call is None:
        raise HTTPException(status_code=404, detail="Prospecting dial leg not found.")
    return call


@router.post("/dialer/legs/{dial_leg_id}/call/cancel")
def cancel_native_prospecting_call(
    dial_leg_id: UUID,
    payload: ProspectingVoiceCallControl,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingVoiceCallRead:
    return _control_native_prospecting_call(db, principal, dial_leg_id, payload, "cancel")


@router.post("/dialer/legs/{dial_leg_id}/call/hangup")
def hangup_native_prospecting_call(
    dial_leg_id: UUID,
    payload: ProspectingVoiceCallControl,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingVoiceCallRead:
    return _control_native_prospecting_call(db, principal, dial_leg_id, payload, "hangup")


def _control_native_prospecting_call(
    db: Session,
    principal: Principal,
    dial_leg_id: UUID,
    payload: ProspectingVoiceCallControl,
    action: Literal["cancel", "hangup"],
) -> ProspectingVoiceCallRead:
    try:
        call = control_prospecting_voice_call(
            db,
            principal,
            dial_leg_id,
            action=action,
            payload=payload,
        )
    except (
        PermissionError,
        ProspectingVoiceConflictError,
        ProspectingVoiceConfigurationError,
        VoiceCallProviderError,
        ValueError,
    ) as exc:
        _raise_prospecting_voice_error(exc)
    if call is None:
        raise HTTPException(status_code=404, detail="Prospecting dial leg not found.")
    return call


@router.get("")
def read_prospecting_workbench(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingWorkbenchOverview:
    return get_prospecting_overview(db, principal)


@router.post("/scripts", status_code=201)
def create_prospecting_script(
    payload: ProspectingScriptCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> ProspectingScriptRead:
    try:
        return create_script(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.post("/scripts/{script_id}/approve")
def approve_prospecting_script(
    script_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> ProspectingScriptRead:
    try:
        script = approve_script(db, principal, script_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if script is None:
        raise HTTPException(status_code=404, detail="Caller script not found.")
    return script


@router.post("/entries/{entry_id}/start")
def start_prospecting_attempt(
    entry_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingEntryRead:
    try:
        entry = start_attempt(db, principal, entry_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if entry is None:
        raise HTTPException(status_code=404, detail="Assigned prospect not found.")
    return entry


@router.post("/attempts/{attempt_id}/complete")
def complete_prospecting_attempt(
    attempt_id: UUID,
    payload: ProspectingAttemptComplete,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingEntryRead:
    try:
        entry = complete_attempt(db, principal, attempt_id, payload)
    except (
        PermissionError,
        ProspectingCompletionConflictError,
        ProspectingDialerConflictError,
        ProspectingDialerConfigurationError,
        ValueError,
    ) as exc:
        _raise_prospecting_dialer_error(exc)
    if entry is None:
        raise HTTPException(status_code=404, detail="Prospecting attempt not found.")
    return entry


@router.post("/attempts/{attempt_id}/technical-failure")
def complete_prospecting_technical_failure(
    attempt_id: UUID,
    payload: ProspectingTechnicalFailureComplete,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingEntryRead:
    _mark_sensitive_response_no_store(response)
    try:
        entry = complete_technical_failure(db, principal, attempt_id, payload)
    except (
        PermissionError,
        ProspectingCompletionConflictError,
        ProspectingDialerConflictError,
        ProspectingDialerConfigurationError,
        ValueError,
    ) as exc:
        _raise_prospecting_dialer_error(exc)
    if entry is None:
        raise HTTPException(status_code=404, detail="Prospecting attempt not found.")
    return entry


@router.get("/attempts/{attempt_id}/qualification")
def read_prospecting_attempt_qualification(
    attempt_id: UUID,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingQualificationChecklistRead:
    _mark_sensitive_response_no_store(response)
    try:
        checklist = get_attempt_qualification(db, principal, attempt_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if checklist is None:
        raise HTTPException(status_code=404, detail="Prospecting attempt not found.")
    return checklist


@router.get(
    "/attempts/{attempt_id}/evidence",
    dependencies=[Depends(recording_dependency)],
)
def read_prospecting_attempt_evidence(
    attempt_id: UUID,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingCallEvidenceRead:
    _mark_sensitive_response_no_store(response)
    evidence = get_prospecting_call_evidence(db, principal, attempt_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="Prospecting attempt not found.")
    return evidence


@router.put("/attempts/{attempt_id}/qualification/{question_key}")
def autosave_prospecting_attempt_qualification(
    attempt_id: UUID,
    question_key: str,
    payload: ProspectingQualificationAutosaveRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingQualificationChecklistItemRead:
    _mark_sensitive_response_no_store(response)
    try:
        item = autosave_attempt_qualification(db, principal, attempt_id, question_key, payload)
    except (
        PermissionError,
        ProspectingDialerConflictError,
        ProspectingDialerConfigurationError,
        ProspectingQualificationConflictError,
        ValueError,
    ) as exc:
        _raise_prospecting_dialer_error(exc)
    if item is None:
        raise HTTPException(status_code=404, detail="Prospecting attempt not found.")
    return item


@router.post("/handoffs/{handoff_id}/decision")
def review_prospect_handoff(
    handoff_id: UUID,
    payload: ProspectHandoffDecision,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> ProspectHandoffRead:
    try:
        handoff = decide_handoff(db, principal, handoff_id, payload)
    except LeadLifecycleConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if handoff is None:
        raise HTTPException(status_code=404, detail="Warm handoff not found.")
    return handoff


@router.post("/entries/{entry_id}/copilot/analyze")
def analyze_prospecting_entry(
    entry_id: UUID,
    payload: ProspectingCopilotAnalyzeRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingCopilotAnalyzeRead:
    try:
        result = analyze_entry(db, principal, entry_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Assigned prospect not found.")
    return result


@router.post("/copilot/recommendations/{recommendation_id}/review")
def review_prospecting_copilot_recommendation(
    recommendation_id: UUID,
    payload: ProspectingCopilotReviewRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingCopilotReviewRead:
    try:
        review = review_recommendation(db, principal, recommendation_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if review is None:
        raise HTTPException(status_code=404, detail="Copilot recommendation not found.")
    return review


@router.post("/attempts/{attempt_id}/quality/analyze")
def analyze_prospecting_call_quality(
    attempt_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> ProspectingCallQualityAnalyzeRead:
    try:
        result = analyze_call_quality(db, principal, attempt_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Prospecting attempt not found.")
    return result


@router.post("/attempts/{attempt_id}/quality/review")
def review_prospecting_call_quality_result(
    attempt_id: UUID,
    payload: ProspectingCallQualityReviewRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> ProspectingCallQualityRead:
    try:
        result = review_call_quality(db, principal, attempt_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Call-quality review not found.")
    return result
