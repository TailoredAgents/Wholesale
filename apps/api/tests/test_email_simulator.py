from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import principal_for_user
from app.core.config import Settings
from app.models.foundation import CommunicationRecord, Conversation, EmailAccount, User
from app.schemas.email import EmailSendRequest
from app.services.demo_data import seed_demo_workspace
from app.services.email import send_conversation_email


def test_demo_email_uses_simulator_without_google_credentials(db_session: Session) -> None:
    seed_demo_workspace(
        db_session,
        organization_name="Stonegate Demo",
        owner_email="owner@example.test",
        owner_name="Demo Owner",
    )
    owner = db_session.scalar(select(User).where(User.email == "owner@example.test"))
    account = db_session.scalar(
        select(EmailAccount).where(EmailAccount.provider == "simulated")
    )
    conversation = db_session.scalar(select(Conversation).order_by(Conversation.created_at))
    assert owner is not None
    assert account is not None
    assert conversation is not None

    result = send_conversation_email(
        db_session,
        principal_for_user(db_session, owner),
        conversation.id,
        EmailSendRequest(
            email_account_id=account.id,
            subject="Synthetic follow-up",
            body="This stays inside the local demonstration workspace.",
            idempotency_key="demo-email-simulation-1",
        ),
        settings=Settings.model_validate(
            {"APP_ENV": "local", "COMMUNICATION_PROVIDER_MODE": "simulate"}
        ),
    )

    assert result is not None
    assert result.provider_message_id.startswith("sim-email-")
    communication = db_session.get(CommunicationRecord, result.communication_id)
    assert communication is not None
    assert communication.provider == "simulated"
    assert communication.external_payload == {
        "simulated": True,
        "dry_run": True,
        "channel": "email",
        "recipient": result.recipient,
        "metadata": {"attachment_count": "0"},
    }
