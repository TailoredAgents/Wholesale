import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

import httpx
import jwt
import structlog
from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWKClient, PyJWTError
from jwt.exceptions import PyJWKClientError
from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.foundation import Permission, RoleAssignment, RolePermission, User

logger = structlog.get_logger()


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    permission_keys: frozenset[str]


class ClerkClaims:
    def __init__(self, *, subject: str, email: str | None) -> None:
        self.subject = subject
        self.email = email


def get_current_principal(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_dev_user_email: Annotated[str | None, Header(alias="X-Dev-User-Email")] = None,
) -> Principal:
    settings = get_settings()
    if authorization:
        claims = verify_clerk_authorization_header(authorization)
        user = resolve_clerk_user(db, claims)
        return principal_for_user(db, user)

    if settings.app_env == "production":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )

    if not x_dev_user_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing development user header.",
        )

    dev_user = db.scalar(select(User).where(User.email == x_dev_user_email.lower().strip()))
    if dev_user is None or not dev_user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user.")

    return principal_for_user(db, dev_user)


def principal_for_user(db: Session, user: User) -> Principal:
    permission_keys = frozenset(
        db.scalars(
            select(distinct(Permission.key))
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(RoleAssignment, RoleAssignment.role_id == RolePermission.role_id)
            .where(
                RoleAssignment.organization_id == user.organization_id,
                RoleAssignment.user_id == user.id,
            )
        )
    )
    return Principal(
        user_id=user.id,
        organization_id=user.organization_id,
        email=user.email,
        permission_keys=permission_keys,
    )


def verify_clerk_authorization_header(authorization: str) -> ClerkClaims:
    token = extract_bearer_token(authorization)
    settings = get_settings()
    jwks_url = settings.clerk_jwks_url or (
        f"{settings.clerk_issuer.rstrip('/')}/.well-known/jwks.json"
        if settings.clerk_issuer
        else None
    )
    if not settings.clerk_issuer or not jwks_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Clerk authentication is not configured.",
        )

    try:
        signing_key = PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
        decode_options: dict[str, Any] = {"algorithms": ["RS256"], "issuer": settings.clerk_issuer}
        if settings.clerk_audience:
            decode_options["audience"] = settings.clerk_audience
        else:
            decode_options["options"] = {"verify_aud": False}
        claims = jwt.decode(token, signing_key.key, **decode_options)
    except PyJWKClientError as exc:
        logger.warning(
            "clerk_jwks_fetch_failed",
            clerk_issuer=settings.clerk_issuer,
            clerk_jwks_url=jwks_url,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not fetch Clerk signing keys. Check CLERK_ISSUER and CLERK_JWKS_URL.",
        ) from exc
    except PyJWTError as exc:
        logger.warning("clerk_token_invalid", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Clerk session token.",
        ) from exc

    authorized_party = claims.get("azp")
    if authorized_party and authorized_party not in settings.clerk_authorized_parties:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Clerk authorized party.",
        )
    if claims.get("sts") == "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Clerk user registration is pending.",
        )

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clerk token is missing a subject.",
        )
    email = claims.get("email") or claims.get("email_address")
    return ClerkClaims(subject=subject, email=email if isinstance(email, str) else None)


def extract_bearer_token(authorization: str) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be a bearer token.",
        )
    return token.strip()


def resolve_clerk_user(db: Session, claims: ClerkClaims) -> User:
    user = db.scalar(select(User).where(User.external_auth_id == claims.subject))
    if user is not None and user.is_active:
        return user

    email = claims.email or fetch_clerk_user_email(claims.subject)
    if email:
        user = db.scalar(select(User).where(User.email == email.lower().strip()))
        if user is not None and user.is_active:
            user.external_auth_id = claims.subject
            db.commit()
            db.refresh(user)
            return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Clerk user is not mapped to an active local user.",
    )


def fetch_clerk_user_email(clerk_user_id: str) -> str | None:
    settings = get_settings()
    if not settings.clerk_secret_key:
        return None
    try:
        response = httpx.get(
            f"https://api.clerk.com/v1/users/{clerk_user_id}",
            headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
            timeout=5,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return None

    payload = response.json()
    primary_email_id = payload.get("primary_email_address_id")
    email_addresses = payload.get("email_addresses")
    if not isinstance(email_addresses, list):
        return None
    for email_address in email_addresses:
        if not isinstance(email_address, dict):
            continue
        if email_address.get("id") == primary_email_id:
            email = email_address.get("email_address")
            return email if isinstance(email, str) else None
    return None


def require_permission(permission_key: str) -> Callable[[Principal], Principal]:
    def dependency(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if permission_key not in principal.permission_keys:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission_key}",
            )
        return principal

    return dependency
