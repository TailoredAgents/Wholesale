from typing import Literal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    CallRecord,
    CallRecording,
    CallTranscript,
    ProspectingAttempt,
    ProspectingDialLeg,
    ProspectingQualificationResponse,
)
from app.schemas.prospecting import (
    ProspectingCallEvidenceCapabilities,
    ProspectingCallEvidenceRead,
    ProspectingQualificationSuggestionRead,
)
from app.services.call_intelligence import (
    prospecting_transcript_eligibility,
    transcript_to_read,
)
from app.services.call_recording_evidence import (
    recording_audio_available,
    select_preferred_call_recording,
)
from app.services.voice import recording_to_read


def get_prospecting_call_evidence(
    db: Session,
    principal: Principal,
    attempt_id: UUID,
) -> ProspectingCallEvidenceRead | None:
    if PermissionKeys.ACCESS_RECORDINGS not in principal.permission_keys:
        return None
    attempt = db.scalar(
        select(ProspectingAttempt).where(
            ProspectingAttempt.id == attempt_id,
            ProspectingAttempt.organization_id == principal.organization_id,
        )
    )
    if attempt is None:
        return None
    can_manage = PermissionKeys.MANAGE_ACQUISITION_OPERATIONS in principal.permission_keys
    if not can_manage and attempt.caller_user_id != principal.user_id:
        return None
    call = db.get(CallRecord, attempt.call_record_id) if attempt.call_record_id else None
    leg = (
        db.scalar(
            select(ProspectingDialLeg).where(
                ProspectingDialLeg.organization_id == principal.organization_id,
                ProspectingDialLeg.attempt_id == attempt.id,
            )
        )
        if call is not None
        else None
    )
    graph_valid = bool(
        call is not None
        and leg is not None
        and call.organization_id == principal.organization_id
        and call.prospecting_attempt_id == attempt.id
        and call.prospecting_dial_leg_id == leg.id
        and call.prospect_id == attempt.prospect_id == leg.prospect_id
        and attempt.call_record_id == call.id == leg.call_record_id
    )
    recording = (
        select_preferred_call_recording(
            db,
            organization_id=principal.organization_id,
            call_record_id=call.id,
        )
        if graph_valid and call is not None
        else None
    )
    transcript = (
        db.scalar(
            select(CallTranscript).where(
                CallTranscript.organization_id == principal.organization_id,
                CallTranscript.recording_id == recording.id,
            )
        )
        if recording is not None
        else None
    )
    suggestions = read_prospecting_suggestions(db, attempt, transcript)
    audio_ready = bool(recording is not None and recording_audio_available(recording))
    permanent_failure = bool(
        transcript is not None and (transcript.transcript_metadata or {}).get("permanent_failure")
    )
    retry_source_available = bool(
        recording is not None and prospecting_transcript_eligibility(db, recording).eligible
    )
    evidence_status = prospecting_evidence_status(recording, transcript)
    return ProspectingCallEvidenceRead(
        attempt_id=attempt.id,
        call_record_id=call.id if graph_valid and call is not None else None,
        dial_leg_id=leg.id if graph_valid and leg is not None else None,
        recording=recording_to_read(recording) if recording is not None else None,
        transcript=transcript_to_read(db, transcript) if transcript is not None else None,
        suggestions=suggestions,
        capabilities=ProspectingCallEvidenceCapabilities(
            can_play=audio_ready,
            can_download_audio=audio_ready,
            can_download_transcript=bool(
                transcript is not None and (transcript.transcript_text or "").strip()
            ),
            can_retry=bool(
                transcript is not None
                and transcript.status in {"failed", "exhausted"}
                and not permanent_failure
                and retry_source_available
            ),
            can_delete=bool(
                recording is not None
                and recording.deleted_at is None
                and recording.status != "deleted"
                and PermissionKeys.MANAGE_RECORDINGS in principal.permission_keys
            ),
        ),
        evidence_status=evidence_status,
    )


def read_prospecting_suggestions(
    db: Session,
    attempt: ProspectingAttempt,
    transcript: CallTranscript | None,
) -> list[ProspectingQualificationSuggestionRead]:
    if transcript is None:
        return []
    raw_items = (transcript.transcript_metadata or {}).get("prospecting_suggestions") or []
    responses = {
        item.question_key: item
        for item in db.scalars(
            select(ProspectingQualificationResponse).where(
                ProspectingQualificationResponse.attempt_id == attempt.id
            )
        ).all()
    }
    output: list[ProspectingQualificationSuggestionRead] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        response = responses.get(str(raw.get("question_key") or ""))
        candidate = {
            **raw,
            "current_value": response.answer_value if response is not None else None,
        }
        try:
            output.append(ProspectingQualificationSuggestionRead.model_validate(candidate))
        except ValidationError:
            continue
    return output


def prospecting_evidence_status(
    recording: CallRecording | None,
    transcript: CallTranscript | None,
) -> Literal[
    "unavailable",
    "recording_ready",
    "processing",
    "ready",
    "failed",
    "exhausted",
]:
    if transcript is not None and transcript.status in {"completed", "approved"}:
        return "ready"
    if recording is None:
        return "unavailable"
    recording_is_recoverable = bool(
        recording.deleted_at is None
        and recording.status != "deleted"
        and recording.consent_status in {"disclosed", "one_party_consent"}
        and (
            recording.status in {"in-progress", "processing", "queued"}
            or recording_audio_available(recording)
        )
    )
    if not recording_is_recoverable:
        return "unavailable"
    if transcript is None:
        return "recording_ready" if recording_audio_available(recording) else "processing"
    if transcript.status in {"queued", "processing", "needs_review"}:
        return "processing"
    if transcript.status == "failed":
        return "failed"
    if transcript.status in {"exhausted", "rejected"}:
        return "exhausted"
    return "recording_ready"
