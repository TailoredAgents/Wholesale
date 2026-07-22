from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.foundation import (
    Buyer,
    Deal,
    Lead,
    LeadManagementCase,
    LeadQualificationScriptVersion,
    Organization,
    User,
)
from app.services.demo_data import seed_demo_workspace


def test_demo_seed_is_repeatable(db_session: Session) -> None:
    first = seed_demo_workspace(
        db_session,
        organization_name="Stonegate Demo",
        owner_email="owner@example.test",
        owner_name="Demo Owner",
    )
    second = seed_demo_workspace(
        db_session,
        organization_name="Stonegate Demo",
        owner_email="owner@example.test",
        owner_name="Demo Owner",
    )

    organization = db_session.scalar(
        select(Organization).where(Organization.slug == "stonegate-demo")
    )
    assert organization is not None
    assert first.users_created == 5
    assert first.leads_created == 4
    assert second.users_created == 0
    assert second.leads_created == 0
    assert second.leads_reused == 4
    assert db_session.scalar(
        select(func.count()).select_from(User).where(User.organization_id == organization.id)
    ) == 6
    assert db_session.scalar(
        select(func.count()).select_from(Lead).where(Lead.organization_id == organization.id)
    ) == 4
    assert db_session.scalar(
        select(func.count())
        .select_from(LeadManagementCase)
        .where(LeadManagementCase.organization_id == organization.id)
    ) == 4
    assert db_session.scalar(
        select(func.count())
        .select_from(LeadQualificationScriptVersion)
        .where(LeadQualificationScriptVersion.organization_id == organization.id)
    ) == 1
    assert db_session.scalar(
        select(func.count()).select_from(Deal).where(Deal.organization_id == organization.id)
    ) == 1
    assert db_session.scalar(
        select(func.count()).select_from(Buyer).where(Buyer.organization_id == organization.id)
    ) == 2
