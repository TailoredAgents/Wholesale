from uuid import UUID

from sqlalchemy import and_, case, select
from sqlalchemy.orm import Session

from app.models.foundation import CallRecording

AUTHORIZED_RECORDING_CONSENT = frozenset({"disclosed", "one_party_consent"})


def recording_audio_available(recording: CallRecording) -> bool:
    """Return whether retained provider audio may be served to an authorized user."""

    return bool(
        recording.status == "completed"
        and recording.deleted_at is None
        and recording.provider_recording_id
        and recording.consent_status in AUTHORIZED_RECORDING_CONSENT
    )


def select_preferred_call_recording(
    db: Session,
    *,
    organization_id: UUID,
    call_record_id: UUID,
) -> CallRecording | None:
    """Select one call recording deterministically without hiding retained media."""

    retained_rank = case(
        (
            and_(
                CallRecording.deleted_at.is_(None),
                CallRecording.status != "deleted",
            ),
            1,
        ),
        else_=0,
    )
    completed_authorized_rank = case(
        (
            and_(
                CallRecording.status == "completed",
                CallRecording.consent_status.in_(AUTHORIZED_RECORDING_CONSENT),
            ),
            1,
        ),
        else_=0,
    )
    recorded_at_rank = case(
        (CallRecording.recorded_at.is_not(None), 1),
        else_=0,
    )
    return db.scalar(
        select(CallRecording)
        .where(
            CallRecording.organization_id == organization_id,
            CallRecording.call_record_id == call_record_id,
        )
        .order_by(
            retained_rank.desc(),
            completed_authorized_rank.desc(),
            recorded_at_rank.desc(),
            CallRecording.recorded_at.desc(),
            CallRecording.created_at.desc(),
            CallRecording.id.desc(),
        )
        .limit(1)
    )
