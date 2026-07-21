import argparse

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.demo_data import seed_demo_workspace


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Seed deterministic local Stonegate demo data.")
    parser.add_argument("--organization-name", default=settings.default_organization_name)
    parser.add_argument("--owner-email", default="demo.owner@example.test")
    parser.add_argument("--owner-name", default="Demo Owner")
    return parser.parse_args()


def main() -> None:
    settings = get_settings()
    if settings.app_env.lower() == "production":
        raise SystemExit("Demo data is forbidden when APP_ENV=production.")
    args = parse_args()
    with SessionLocal() as db:
        result = seed_demo_workspace(
            db,
            organization_name=args.organization_name,
            owner_email=args.owner_email,
            owner_name=args.owner_name,
        )
    print(
        "Seeded Stonegate demo workspace "
        f"organization={result.organization_slug} "
        f"users_created={result.users_created} "
        f"leads_created={result.leads_created} "
        f"leads_reused={result.leads_reused}"
    )


if __name__ == "__main__":
    main()
