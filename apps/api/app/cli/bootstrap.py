import argparse

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.bootstrap import bootstrap_foundation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap local foundation data.")
    parser.add_argument("--organization-name", default=get_settings().default_organization_name)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-name", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with SessionLocal() as db:
        result = bootstrap_foundation(
            db,
            organization_name=args.organization_name,
            admin_email=args.admin_email,
            admin_name=args.admin_name,
        )
        print(
            "Bootstrapped "
            f"organization={result.organization.slug} "
            f"admin={result.admin_user.email if result.admin_user else 'none'} "
            f"permissions={result.permissions_count} "
            f"roles={result.roles_count}"
        )


if __name__ == "__main__":
    main()
