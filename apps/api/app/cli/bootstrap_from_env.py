import structlog

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.bootstrap import bootstrap_foundation

logger = structlog.get_logger()


def main() -> None:
    settings = get_settings()
    if not settings.bootstrap_admin_email:
        logger.info("bootstrap_from_env_skipped", reason="missing_bootstrap_admin_email")
        return

    with SessionLocal() as db:
        result = bootstrap_foundation(
            db,
            organization_name=settings.default_organization_name,
            admin_email=settings.bootstrap_admin_email,
            admin_name=settings.bootstrap_admin_name,
        )
        organization_slug = result.organization.slug
        admin_email = result.admin_user.email if result.admin_user else None
        permissions_count = result.permissions_count
        roles_count = result.roles_count

    logger.info(
        "bootstrap_from_env_completed",
        organization=organization_slug,
        admin=admin_email,
        permissions=permissions_count,
        roles=roles_count,
    )


if __name__ == "__main__":
    main()
