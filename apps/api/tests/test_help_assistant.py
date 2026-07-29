from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.openai_client import OpenAITextResponse
from app.main import app
from app.models.foundation import Organization, Role, RoleAssignment, User
from app.services.bootstrap import bootstrap_foundation
from app.services.help_assistant import load_chunks
from app.services import help_assistant as help_module

OWNER_HEADERS = {"X-Dev-User-Email": "owner@example.com"}


def create_role_user(
    db: Session,
    organization: Organization,
    *,
    email: str,
    display_name: str,
    role_key: str,
) -> User:
    role = db.scalar(
        select(Role).where(
            Role.organization_id == organization.id,
            Role.key == role_key,
        )
    )
    assert role is not None
    user = User(
        organization_id=organization.id,
        email=email,
        display_name=display_name,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        RoleAssignment(
            organization_id=organization.id,
            user_id=user.id,
            role_id=role.id,
        )
    )
    db.commit()
    return user


def disable_ai(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    load_chunks.cache_clear()


def test_owner_help_returns_role_scoped_sources(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    disable_ai(monkeypatch)
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email="owner@example.com",
        admin_name="Owner",
    )
    client = TestClient(app)

    try:
        overview = client.get("/api/v1/help", headers=OWNER_HEADERS)
        answer = client.post(
            "/api/v1/help/ask",
            headers=OWNER_HEADERS,
            json={"question": "How do I add and train a new employee?"},
        )
    finally:
        get_settings.cache_clear()
        load_chunks.cache_clear()

    assert overview.status_code == 200
    assert "SETUP_MANUAL.md" in overview.json()["available_documents"]
    assert "owner" in overview.json()["role_keys"]
    assert answer.status_code == 200
    payload = answer.json()
    assert payload["used_ai"] is False
    assert payload["citations"]
    assert any(
        citation["document"] in {"SETUP_MANUAL.md", "STAFF_ROLE_MANUALS.md"}
        for citation in payload["citations"]
    )


def test_va_help_blocks_finance_instructions(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    disable_ai(monkeypatch)
    foundation = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email="owner@example.com",
        admin_name="Owner",
    )
    va = create_role_user(
        db_session,
        foundation.organization,
        email="va@example.com",
        display_name="VA Caller",
        role_key="prospecting_caller",
    )
    client = TestClient(app)

    try:
        overview = client.get(
            "/api/v1/help",
            headers={"X-Dev-User-Email": va.email},
        )
        answer = client.post(
            "/api/v1/help/ask",
            headers={"X-Dev-User-Email": va.email},
            json={"question": "How do I post an accounting journal?"},
        )
    finally:
        get_settings.cache_clear()
        load_chunks.cache_clear()

    assert overview.status_code == 200
    assert "SETUP_MANUAL.md" not in overview.json()["available_documents"]
    assert answer.status_code == 200
    payload = answer.json()
    assert "outside your current Stonegate role" in payload["answer"]
    assert payload["used_ai"] is False


def test_help_rejects_empty_question(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email="owner@example.com",
        admin_name="Owner",
    )

    response = TestClient(app).post(
        "/api/v1/help/ask",
        headers=OWNER_HEADERS,
        json={"question": " "},
    )

    assert response.status_code == 422


def test_help_uses_openai_only_to_summarize_retrieved_sources(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email="owner@example.com",
        admin_name="Owner",
    )
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-help-key")
    get_settings.cache_clear()
    load_chunks.cache_clear()

    class FakeOpenAIResponsesClient:
        def __init__(self, **_: object) -> None:
            pass

        def create_text_response(self, **kwargs: object) -> OpenAITextResponse:
            system_prompt = kwargs["system_prompt"]
            user_prompt = kwargs["user_prompt"]
            assert isinstance(system_prompt, str)
            assert isinstance(user_prompt, str)
            assert "Answer only from the provided approved Stonegate sources" in system_prompt
            assert "SOURCE [1]" in user_prompt
            assert kwargs["enable_web_search"] is False
            return OpenAITextResponse(
                text="Open **Operations > Team**, then create the employee record. [1]",
                total_tokens=100,
            )

    monkeypatch.setattr(
        help_module,
        "OpenAIResponsesClient",
        FakeOpenAIResponsesClient,
    )

    try:
        response = TestClient(app).post(
            "/api/v1/help/ask",
            headers=OWNER_HEADERS,
            json={"question": "How do I add and train a new employee?"},
        )
    finally:
        get_settings.cache_clear()
        load_chunks.cache_clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["used_ai"] is True
    assert payload["citations"]
    assert "[1]" in payload["answer"]
