from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.field_operations import (
    AcquisitionsCopilotAnalyzeRead,
    AcquisitionsCopilotAnalyzeRequest,
    AcquisitionsCopilotReviewRead,
    AcquisitionsCopilotReviewRequest,
    AppointmentDispatchCreate,
    AppointmentDispatchRead,
    CloserAvailabilityBlockCreate,
    CloserAvailabilityBlockRead,
    CloserProfileRead,
    CloserProfileUpsert,
    DispatchSlotEvaluation,
    DispatchSlotRequest,
    FieldAppointmentWorkspaceRead,
    FieldCalendarRead,
    FieldInspectionPhotoRead,
    FieldInspectionRead,
    FieldInspectionUpdate,
    FieldMeetingBriefRead,
    FieldNegotiationRead,
    FieldNegotiationUpdate,
    FieldOperationsOverview,
    FieldUnderwritingTransferRead,
)
from app.services.acquisitions_copilot import (
    analyze_appointment,
    review_recommendation,
)
from app.services.field_operations import (
    add_availability_block,
    delete_availability_block,
    dispatch_appointment,
    evaluate_slot,
    get_overview,
    upsert_profile,
)
from app.services.field_workflows import (
    add_photo,
    appointment_workspace,
    calendar_appointments,
    delete_photo,
    generate_meeting_brief,
    get_photo_content,
    save_negotiation,
    start_inspection,
    submit_inspection,
    transfer_to_underwriting,
    update_inspection,
)

router = APIRouter(prefix="/api/v1/field-operations", tags=["field-operations"])
work_dependency = require_any_permission(
    PermissionKeys.EDIT_UNDERWRITING,
    PermissionKeys.MANAGE_ACQUISITION_OPERATIONS,
)
manage_dependency = require_permission(PermissionKeys.MANAGE_ACQUISITION_OPERATIONS)


@router.get("")
def read_field_operations(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> FieldOperationsOverview:
    return get_overview(db, principal)


@router.get("/calendar")
def read_field_calendar(
    starts_at: datetime,
    ends_at: datetime,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
    owner_user_id: UUID | None = None,
) -> FieldCalendarRead:
    try:
        return calendar_appointments(db, principal, starts_at, ends_at, owner_user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get("/appointments/{appointment_id}/workspace")
def read_appointment_workspace(
    appointment_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> FieldAppointmentWorkspaceRead:
    try:
        result = appointment_workspace(db, principal, appointment_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    return result


@router.post("/appointments/{appointment_id}/brief")
def create_meeting_brief(
    appointment_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> FieldMeetingBriefRead:
    try:
        result = generate_meeting_brief(db, principal, appointment_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    return result


@router.post("/appointments/{appointment_id}/copilot/analyze")
def create_acquisitions_copilot_draft(
    appointment_id: UUID,
    payload: AcquisitionsCopilotAnalyzeRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> AcquisitionsCopilotAnalyzeRead:
    try:
        result = analyze_appointment(db, principal, appointment_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    return result


@router.post("/copilot/recommendations/{recommendation_id}/review")
def review_acquisitions_copilot_draft(
    recommendation_id: UUID,
    payload: AcquisitionsCopilotReviewRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> AcquisitionsCopilotReviewRead:
    try:
        result = review_recommendation(db, principal, recommendation_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Recommendation not found.")
    return result


@router.post("/appointments/{appointment_id}/inspection", status_code=201)
def create_field_inspection(
    appointment_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> FieldInspectionRead:
    try:
        result = start_inspection(db, principal, appointment_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    return result


@router.patch("/inspections/{inspection_id}")
def save_field_inspection(
    inspection_id: UUID,
    payload: FieldInspectionUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> FieldInspectionRead:
    try:
        result = update_inspection(db, principal, inspection_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    return result


@router.post("/inspections/{inspection_id}/submit")
def complete_field_inspection(
    inspection_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> FieldInspectionRead:
    try:
        result = submit_inspection(db, principal, inspection_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    return result


@router.post("/inspections/{inspection_id}/photos", status_code=201)
async def upload_inspection_photo(
    inspection_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
    area: Annotated[str, Query(min_length=1, max_length=120)],
    file_name: Annotated[str, Query(min_length=1, max_length=255)],
    caption: Annotated[str | None, Query(max_length=500)] = None,
    captured_at: datetime | None = None,
) -> FieldInspectionPhotoRead:
    try:
        result = add_photo(
            db,
            principal,
            inspection_id,
            image_data=await request.body(),
            content_type=request.headers.get("content-type", ""),
            file_name=file_name,
            area=area,
            caption=caption,
            captured_at=captured_at,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    return result


@router.get("/photos/{photo_id}/content")
def read_inspection_photo(
    photo_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> Response:
    try:
        result = get_photo_content(db, principal, photo_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Photo not found.")
    photo, content = result
    return Response(
        content=content,
        media_type=photo.content_type,
        headers={
            "Cache-Control": "private, max-age=300",
            "Content-Disposition": f'inline; filename="{photo.file_name}"',
        },
    )


@router.delete("/photos/{photo_id}", status_code=204)
def remove_inspection_photo(
    photo_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> Response:
    try:
        removed = delete_photo(db, principal, photo_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="Photo not found.")
    return Response(status_code=204)


@router.put("/appointments/{appointment_id}/negotiation")
def record_field_negotiation(
    appointment_id: UUID,
    payload: FieldNegotiationUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> FieldNegotiationRead:
    try:
        result = save_negotiation(db, principal, appointment_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    return result


@router.post("/inspections/{inspection_id}/underwriting-transfer")
def review_field_evidence(
    inspection_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> FieldUnderwritingTransferRead:
    try:
        result = transfer_to_underwriting(db, principal, inspection_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    return result


@router.put("/profiles/{user_id}")
def configure_closer(
    user_id: UUID,
    payload: CloserProfileUpsert,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> CloserProfileRead:
    try:
        profile = upsert_profile(db, principal, user_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if profile is None:
        raise HTTPException(status_code=404, detail="Closer user not found.")
    return profile


@router.post("/profiles/{profile_id}/blocks", status_code=201)
def block_closer_time(
    profile_id: UUID,
    payload: CloserAvailabilityBlockCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> CloserAvailabilityBlockRead:
    block = add_availability_block(db, principal, profile_id, payload)
    if block is None:
        raise HTTPException(status_code=404, detail="Closer profile not found.")
    return block


@router.delete("/blocks/{block_id}", status_code=204)
def remove_closer_block(
    block_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_dependency)],
) -> Response:
    if not delete_availability_block(db, principal, block_id):
        raise HTTPException(status_code=404, detail="Availability block not found.")
    return Response(status_code=204)


@router.post("/evaluate")
def evaluate_dispatch_slot(
    payload: DispatchSlotRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> DispatchSlotEvaluation:
    try:
        result = evaluate_slot(db, principal, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return result


@router.post("/dispatch", status_code=201)
def schedule_dispatched_appointment(
    payload: AppointmentDispatchCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(work_dependency)],
) -> AppointmentDispatchRead:
    try:
        result = dispatch_appointment(db, principal, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return result
