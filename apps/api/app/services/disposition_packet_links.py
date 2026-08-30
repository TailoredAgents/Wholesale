from __future__ import annotations

import hmac
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    AuditEvent,
    DispositionCase,
    DispositionPackageShareLink,
    DispositionPackageVersion,
)
from app.schemas.dispositions import (
    DispositionPackageShareLinkCreate,
    DispositionPackageShareLinkIssuedRead,
    DispositionPackageShareLinkRead,
    DispositionPackageShareLinkRevoke,
)
from app.services.disposition_packages import require_current_approved_version


class SharedPackageUnavailable(ValueError):
    def __init__(self, detail: str, *, gone: bool = False) -> None:
        super().__init__(detail)
        self.gone = gone


def list_share_links(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> list[DispositionPackageShareLinkRead] | None:
    case = _case_for_principal(db, principal, case_id)
    if case is None:
        return None
    links = list(
        db.scalars(
            select(DispositionPackageShareLink)
            .where(
                DispositionPackageShareLink.organization_id == principal.organization_id,
                DispositionPackageShareLink.disposition_case_id == case.id,
            )
            .order_by(DispositionPackageShareLink.created_at.desc())
        ).all()
    )
    versions = _versions_by_id(db, {link.package_version_id for link in links})
    latest_id = _latest_version_id(db, case)
    return [
        _link_read(link, versions.get(link.package_version_id), case, latest_id=latest_id)
        for link in links
    ]


def issue_share_link(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: DispositionPackageShareLinkCreate,
    *,
    share_url_builder,
) -> DispositionPackageShareLinkIssuedRead | None:
    case = _case_for_principal(db, principal, case_id)
    if case is None:
        return None
    version = require_current_approved_version(
        db,
        principal,
        case,
        action="creating an investor package link",
    )
    if not _artifact_is_available(version):
        raise ValueError("The approved investor package artifact failed its integrity check.")
    pdf = bytes(version.pdf_data or b"")
    artifact_sha256 = sha256(pdf).hexdigest()

    secret = secrets.token_urlsafe(32)
    link = DispositionPackageShareLink(
        organization_id=principal.organization_id,
        disposition_case_id=case.id,
        package_version_id=version.id,
        created_by_user_id=principal.user_id,
        token_digest=sha256(secret.encode("utf-8")).hexdigest(),
        token_hint=secret[-8:],
        artifact_sha256=artifact_sha256,
        lock_version=1,
        expires_at=datetime.now(UTC) + timedelta(hours=payload.expires_in_hours),
        access_count=0,
    )
    db.add(link)
    db.flush()
    _audit(
        db,
        link,
        actor_user_id=principal.user_id,
        actor_type="user",
        action="disposition.package_share_link.created",
        new_value={
            "case_id": str(case.id),
            "package_version_id": str(version.id),
            "package_version_number": version.version_number,
            "artifact_sha256": artifact_sha256,
            "expires_at": link.expires_at.isoformat(),
            "token_hint": link.token_hint,
        },
        reason="Created a time-limited investor-safe package link.",
    )
    db.commit()
    db.refresh(link)
    read = _link_read(link, version, case, latest_id=version.id)
    token = f"{link.id}.{secret}"
    return DispositionPackageShareLinkIssuedRead(
        **read.model_dump(),
        share_url=share_url_builder(token),
    )


def revoke_share_link(
    db: Session,
    principal: Principal,
    case_id: UUID,
    link_id: UUID,
    payload: DispositionPackageShareLinkRevoke,
) -> DispositionPackageShareLinkRead | None:
    case = _case_for_principal(db, principal, case_id)
    if case is None:
        return None
    link = db.scalar(
        select(DispositionPackageShareLink)
        .where(
            DispositionPackageShareLink.id == link_id,
            DispositionPackageShareLink.organization_id == principal.organization_id,
            DispositionPackageShareLink.disposition_case_id == case.id,
        )
        .with_for_update()
    )
    if link is None:
        return None
    if link.lock_version != payload.expected_version:
        raise ValueError("The package link changed. Refresh before revoking it.")
    if link.revoked_at is None:
        link.revoked_at = datetime.now(UTC)
        link.revoked_by_user_id = principal.user_id
        link.revocation_reason = payload.reason
        link.lock_version += 1
        _audit(
            db,
            link,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="disposition.package_share_link.revoked",
            new_value={
                "revoked_at": link.revoked_at.isoformat(),
                "token_hint": link.token_hint,
                "lock_version": link.lock_version,
            },
            reason=payload.reason,
        )
        db.commit()
        db.refresh(link)
    version = db.get(DispositionPackageVersion, link.package_version_id)
    return _link_read(link, version, case, latest_id=_latest_version_id(db, case))


def read_shared_package(
    db: Session,
    token: str,
    *,
    client_address: str | None,
    user_agent: str | None,
) -> tuple[bytes, str]:
    link_id, secret = _parse_token(token)
    link = db.scalar(
        select(DispositionPackageShareLink)
        .where(DispositionPackageShareLink.id == link_id)
        .with_for_update()
    )
    if link is None or not hmac.compare_digest(
        link.token_digest,
        sha256(secret.encode("utf-8")).hexdigest(),
    ):
        raise SharedPackageUnavailable("Investor package link not found.")

    now = datetime.now(UTC)
    if link.revoked_at is not None:
        raise SharedPackageUnavailable("This investor package link was revoked.", gone=True)
    if _as_utc(link.expires_at) <= now:
        raise SharedPackageUnavailable("This investor package link expired.", gone=True)

    case = db.get(DispositionCase, link.disposition_case_id)
    version = db.get(DispositionPackageVersion, link.package_version_id)
    latest_id = _latest_version_id(db, case) if case is not None else None
    if (
        case is None
        or version is None
        or version.organization_id != link.organization_id
        or version.status != "approved"
        or case.package_status != "approved"
        or latest_id != version.id
        or not _artifact_is_available(version)
    ):
        raise SharedPackageUnavailable(
            "This investor package link is no longer current.",
            gone=True,
        )
    content = bytes(version.pdf_data)
    if (
        version.pdf_sha256 != link.artifact_sha256
        or sha256(content).hexdigest() != link.artifact_sha256
    ):
        raise SharedPackageUnavailable(
            "This investor package artifact is no longer available.",
            gone=True,
        )

    link.access_count += 1
    link.first_accessed_at = link.first_accessed_at or now
    link.last_accessed_at = now
    _audit(
        db,
        link,
        actor_user_id=None,
        actor_type="external_package_recipient",
        action="disposition.package_share_link.accessed",
        new_value={
            "access_count": link.access_count,
            "accessed_at": now.isoformat(),
            "client_fingerprint": _client_fingerprint(client_address, user_agent),
            "token_hint": link.token_hint,
        },
        reason="Authenticated investor package link opened.",
    )
    db.commit()
    return content, version.pdf_file_name


def _case_for_principal(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> DispositionCase | None:
    return db.scalar(
        select(DispositionCase).where(
            DispositionCase.id == case_id,
            DispositionCase.organization_id == principal.organization_id,
        )
    )


def _versions_by_id(
    db: Session,
    version_ids: set[UUID],
) -> dict[UUID, DispositionPackageVersion]:
    if not version_ids:
        return {}
    return {
        version.id: version
        for version in db.scalars(
            select(DispositionPackageVersion).where(
                DispositionPackageVersion.id.in_(version_ids)
            )
        ).all()
    }


def _latest_version_id(db: Session, case: DispositionCase | None) -> UUID | None:
    if case is None:
        return None
    return db.scalar(
        select(DispositionPackageVersion.id)
        .where(
            DispositionPackageVersion.organization_id == case.organization_id,
            DispositionPackageVersion.disposition_case_id == case.id,
        )
        .order_by(
            DispositionPackageVersion.version_number.desc(),
            DispositionPackageVersion.created_at.desc(),
        )
        .limit(1)
    )


def _link_read(
    link: DispositionPackageShareLink,
    version: DispositionPackageVersion | None,
    case: DispositionCase,
    *,
    latest_id: UUID | None,
) -> DispositionPackageShareLinkRead:
    now = datetime.now(UTC)
    if link.revoked_at is not None:
        status = "revoked"
    elif _as_utc(link.expires_at) <= now:
        status = "expired"
    elif (
        version is None
        or version.status != "approved"
        or case.package_status != "approved"
        or latest_id != version.id
        or version.pdf_sha256 != link.artifact_sha256
        or not _artifact_is_available(version)
    ):
        status = "artifact_unavailable"
    else:
        status = "active"
    return DispositionPackageShareLinkRead(
        id=link.id,
        disposition_case_id=link.disposition_case_id,
        package_version_id=link.package_version_id,
        package_version_number=version.version_number if version else 0,
        token_hint=link.token_hint,
        artifact_sha256=link.artifact_sha256,
        lock_version=link.lock_version,
        status=status,
        expires_at=link.expires_at,
        revoked_at=link.revoked_at,
        revocation_reason=link.revocation_reason,
        access_count=link.access_count,
        first_accessed_at=link.first_accessed_at,
        last_accessed_at=link.last_accessed_at,
        created_by_user_id=link.created_by_user_id,
        created_at=link.created_at,
    )


def _artifact_is_available(version: DispositionPackageVersion | None) -> bool:
    if (
        version is None
        or not version.pdf_data
        or not version.pdf_file_name
        or not version.pdf_sha256
    ):
        return False
    return hmac.compare_digest(
        sha256(bytes(version.pdf_data)).hexdigest(),
        version.pdf_sha256,
    )


def _parse_token(token: str) -> tuple[UUID, str]:
    try:
        raw_id, secret = token.split(".", 1)
        link_id = UUID(raw_id)
    except (ValueError, AttributeError) as exc:
        raise SharedPackageUnavailable("Investor package link not found.") from exc
    if len(secret) < 32:
        raise SharedPackageUnavailable("Investor package link not found.")
    return link_id, secret


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _client_fingerprint(client_address: str | None, user_agent: str | None) -> str:
    material = f"{client_address or 'unknown'}|{user_agent or 'unknown'}"
    return sha256(material.encode("utf-8")).hexdigest()


def _audit(
    db: Session,
    link: DispositionPackageShareLink,
    *,
    actor_user_id: UUID | None,
    actor_type: str,
    action: str,
    new_value: dict[str, object],
    reason: str,
) -> None:
    db.add(
        AuditEvent(
            organization_id=link.organization_id,
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            action=action,
            entity_type="disposition_package_share_link",
            entity_id=link.id,
            previous_value=None,
            new_value=new_value,
            reason=reason,
        )
    )
