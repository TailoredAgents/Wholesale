from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    AuditEvent,
    EmailSenderAlias,
    EmailSenderGrant,
    Team,
    TeamMembership,
    User,
)
from app.schemas.email import (
    EmailSenderAliasCreate,
    EmailSenderAliasListResponse,
    EmailSenderAliasRead,
    EmailSenderAliasUpdate,
    EmailSenderGrantCreate,
    EmailSenderGrantRead,
)


def list_email_sender_aliases(
    db: Session,
    principal: Principal,
    *,
    settings: Settings | None = None,
) -> EmailSenderAliasListResponse:
    settings = settings or get_settings()
    can_manage = PermissionKeys.MANAGE_EMAIL_ACCOUNTS in principal.permission_keys
    filters = [EmailSenderAlias.organization_id == principal.organization_id]
    if not can_manage:
        team_ids = list(
            db.scalars(
                select(TeamMembership.team_id).where(
                    TeamMembership.organization_id == principal.organization_id,
                    TeamMembership.user_id == principal.user_id,
                )
            )
        )
        granted_alias_ids = select(EmailSenderGrant.email_sender_alias_id).where(
            EmailSenderGrant.organization_id == principal.organization_id,
            EmailSenderGrant.user_id == principal.user_id,
        )
        visibility = [
            EmailSenderAlias.owner_user_id == principal.user_id,
            EmailSenderAlias.id.in_(granted_alias_ids),
        ]
        if team_ids:
            visibility.append(EmailSenderAlias.assigned_team_id.in_(team_ids))
        filters.append(or_(*visibility))
    aliases = db.scalars(
        select(EmailSenderAlias)
        .where(*filters)
        .order_by(
            EmailSenderAlias.is_default.desc(),
            EmailSenderAlias.status.asc(),
            EmailSenderAlias.email_address.asc(),
        )
    ).all()
    return EmailSenderAliasListResponse(
        items=[email_sender_alias_to_read(db, alias, principal) for alias in aliases],
        provider=settings.email_provider,
        provider_configured=(
            settings.communication_simulation_enabled or not settings.email_configuration_blockers
        ),
        configuration_blockers=list(settings.email_configuration_blockers),
    )


def create_email_sender_alias(
    db: Session,
    principal: Principal,
    payload: EmailSenderAliasCreate,
    *,
    settings: Settings | None = None,
) -> EmailSenderAliasRead:
    require_alias_manager(principal)
    settings = settings or get_settings()
    validate_alias_domain(payload.email_address, settings)
    owner = scoped_active_user(db, principal.organization_id, payload.owner_user_id)
    team = scoped_active_team(db, principal.organization_id, payload.assigned_team_id)
    validate_alias_assignment(
        alias_type=payload.alias_type,
        status=payload.status,
        owner_user_id=owner.id if owner else None,
    )
    inbound_enabled, outbound_enabled = normalized_channel_state(
        payload.status,
        payload.inbound_enabled,
        payload.outbound_enabled,
    )
    if payload.is_default and not outbound_enabled:
        raise ValueError("The default sender must be active for outbound email.")
    if payload.is_default:
        clear_default_alias(db, principal.organization_id)
    alias = EmailSenderAlias(
        organization_id=principal.organization_id,
        owner_user_id=owner.id if owner else None,
        assigned_team_id=team.id if team else None,
        created_by_user_id=principal.user_id,
        provider=payload.provider,
        provider_identity_id=None,
        email_address=payload.email_address,
        display_name=payload.display_name.strip(),
        alias_type=payload.alias_type,
        purpose_key=payload.purpose_key,
        status=payload.status,
        inbound_enabled=inbound_enabled,
        outbound_enabled=outbound_enabled,
        is_default=payload.is_default,
        signature_text=clean_optional_text(payload.signature_text),
        routing_metadata=payload.routing_metadata,
    )
    db.add(alias)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("That Stonegate email address already exists.") from exc
    add_alias_audit(
        db,
        principal,
        alias,
        action="email.alias_created",
        previous=None,
        reason="Company-controlled sender alias created",
    )
    db.commit()
    return email_sender_alias_to_read(db, alias, principal)


def update_email_sender_alias(
    db: Session,
    principal: Principal,
    alias_id: UUID,
    payload: EmailSenderAliasUpdate,
) -> EmailSenderAliasRead | None:
    require_alias_manager(principal)
    alias = scoped_alias(db, principal.organization_id, alias_id)
    if alias is None:
        return None
    previous = alias_snapshot(alias)
    values = payload.model_dump(exclude_unset=True)
    for required_key in ("display_name", "purpose_key", "status"):
        if required_key in values and values[required_key] is None:
            raise ValueError(f"{required_key.replace('_', ' ').title()} cannot be blank.")
    if "owner_user_id" in values:
        owner = scoped_active_user(db, principal.organization_id, values["owner_user_id"])
        alias.owner_user_id = owner.id if owner else None
    if "assigned_team_id" in values:
        team = scoped_active_team(db, principal.organization_id, values["assigned_team_id"])
        alias.assigned_team_id = team.id if team else None
    for key in (
        "display_name",
        "purpose_key",
        "status",
        "inbound_enabled",
        "outbound_enabled",
        "is_default",
        "signature_text",
        "routing_metadata",
    ):
        if key not in values:
            continue
        value = values[key]
        if key in {"display_name", "signature_text"} and isinstance(value, str):
            value = clean_optional_text(value)
        setattr(alias, key, value)
    validate_alias_assignment(
        alias_type=alias.alias_type,
        status=alias.status,
        owner_user_id=alias.owner_user_id,
    )
    alias.inbound_enabled, alias.outbound_enabled = normalized_channel_state(
        alias.status,
        alias.inbound_enabled,
        alias.outbound_enabled,
    )
    if alias.is_default and not alias.outbound_enabled:
        raise ValueError("The default sender must be active for outbound email.")
    if alias.is_default:
        clear_default_alias(db, principal.organization_id, except_alias_id=alias.id)
    add_alias_audit(
        db,
        principal,
        alias,
        action="email.alias_updated",
        previous=previous,
        reason="Company-controlled sender alias updated",
    )
    db.commit()
    return email_sender_alias_to_read(db, alias, principal)


def grant_email_sender_access(
    db: Session,
    principal: Principal,
    alias_id: UUID,
    payload: EmailSenderGrantCreate,
) -> EmailSenderAliasRead | None:
    require_alias_manager(principal)
    alias = scoped_alias(db, principal.organization_id, alias_id)
    if alias is None:
        return None
    user = scoped_active_user(db, principal.organization_id, payload.user_id)
    if user is None:
        raise ValueError("Select an active Stonegate user.")
    grant = db.scalar(
        select(EmailSenderGrant).where(
            EmailSenderGrant.email_sender_alias_id == alias.id,
            EmailSenderGrant.user_id == user.id,
        )
    )
    previous = None
    if grant is None:
        grant = EmailSenderGrant(
            organization_id=principal.organization_id,
            email_sender_alias_id=alias.id,
            user_id=user.id,
            granted_by_user_id=principal.user_id,
            access_level=payload.access_level,
            can_send=payload.can_send,
            receives_notifications=payload.receives_notifications,
        )
        db.add(grant)
    else:
        previous = grant_snapshot(grant)
        grant.granted_by_user_id = principal.user_id
        grant.access_level = payload.access_level
        grant.can_send = payload.can_send
        grant.receives_notifications = payload.receives_notifications
    if grant.access_level == "watcher":
        grant.can_send = False
    db.flush()
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="email.alias_grant_updated",
            entity_type="email_sender_grant",
            entity_id=grant.id,
            previous_value=previous,
            new_value=grant_snapshot(grant),
            reason="Email alias access assigned",
        )
    )
    db.commit()
    return email_sender_alias_to_read(db, alias, principal)


def revoke_email_sender_access(
    db: Session,
    principal: Principal,
    alias_id: UUID,
    user_id: UUID,
) -> EmailSenderAliasRead | None:
    require_alias_manager(principal)
    alias = scoped_alias(db, principal.organization_id, alias_id)
    if alias is None:
        return None
    grant = db.scalar(
        select(EmailSenderGrant).where(
            EmailSenderGrant.organization_id == principal.organization_id,
            EmailSenderGrant.email_sender_alias_id == alias.id,
            EmailSenderGrant.user_id == user_id,
        )
    )
    if grant is not None:
        grant_id = grant.id
        previous = grant_snapshot(grant)
        db.delete(grant)
        db.add(
            AuditEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                actor_type="user",
                action="email.alias_grant_revoked",
                entity_type="email_sender_grant",
                entity_id=grant_id,
                previous_value=previous,
                new_value=None,
                reason="Email alias access revoked",
            )
        )
        db.commit()
    return email_sender_alias_to_read(db, alias, principal)


def email_sender_alias_to_read(
    db: Session,
    alias: EmailSenderAlias,
    principal: Principal,
) -> EmailSenderAliasRead:
    owner = db.get(User, alias.owner_user_id) if alias.owner_user_id else None
    team = db.get(Team, alias.assigned_team_id) if alias.assigned_team_id else None
    grant_rows = db.execute(
        select(EmailSenderGrant, User)
        .join(User, User.id == EmailSenderGrant.user_id)
        .where(
            EmailSenderGrant.organization_id == alias.organization_id,
            EmailSenderGrant.email_sender_alias_id == alias.id,
        )
        .order_by(User.display_name.asc())
    ).all()
    can_manage = PermissionKeys.MANAGE_EMAIL_ACCOUNTS in principal.permission_keys
    team_member = False
    if alias.assigned_team_id:
        team_member = (
            db.scalar(
                select(TeamMembership.id).where(
                    TeamMembership.team_id == alias.assigned_team_id,
                    TeamMembership.user_id == principal.user_id,
                )
            )
            is not None
        )
    direct_grant = next(
        (grant for grant, _user in grant_rows if grant.user_id == principal.user_id),
        None,
    )
    authorized = (
        can_manage
        or alias.owner_user_id == principal.user_id
        or team_member
        or bool(direct_grant and direct_grant.can_send)
    )
    return EmailSenderAliasRead(
        id=alias.id,
        provider=alias.provider,
        email_address=alias.email_address,
        display_name=alias.display_name,
        alias_type=alias.alias_type,
        purpose_key=alias.purpose_key,
        status=alias.status,
        owner_user_id=alias.owner_user_id,
        owner_user_name=owner.display_name if owner else None,
        assigned_team_id=alias.assigned_team_id,
        assigned_team_name=team.name if team else None,
        inbound_enabled=alias.inbound_enabled,
        outbound_enabled=alias.outbound_enabled,
        is_default=alias.is_default,
        signature_text=alias.signature_text,
        routing_metadata=alias.routing_metadata or {},
        can_send=authorized and alias.status == "active" and alias.outbound_enabled,
        can_manage=can_manage,
        grants=[
            EmailSenderGrantRead(
                id=grant.id,
                user_id=grant.user_id,
                user_name=user.display_name,
                access_level=grant.access_level,
                can_send=grant.can_send,
                receives_notifications=grant.receives_notifications,
            )
            for grant, user in grant_rows
        ],
    )


def scoped_alias(
    db: Session,
    organization_id: UUID,
    alias_id: UUID,
) -> EmailSenderAlias | None:
    return db.scalar(
        select(EmailSenderAlias).where(
            EmailSenderAlias.organization_id == organization_id,
            EmailSenderAlias.id == alias_id,
        )
    )


def get_authorized_email_sender_alias(
    db: Session,
    principal: Principal,
    alias_id: UUID,
) -> EmailSenderAlias | None:
    alias = scoped_alias(db, principal.organization_id, alias_id)
    if alias is None:
        return None
    if PermissionKeys.MANAGE_EMAIL_ACCOUNTS in principal.permission_keys:
        return alias
    if alias.owner_user_id == principal.user_id:
        return alias
    if alias.assigned_team_id is not None:
        team_membership = db.scalar(
            select(TeamMembership.id).where(
                TeamMembership.organization_id == principal.organization_id,
                TeamMembership.team_id == alias.assigned_team_id,
                TeamMembership.user_id == principal.user_id,
            )
        )
        if team_membership is not None:
            return alias
    direct_grant = db.scalar(
        select(EmailSenderGrant.id).where(
            EmailSenderGrant.organization_id == principal.organization_id,
            EmailSenderGrant.email_sender_alias_id == alias.id,
            EmailSenderGrant.user_id == principal.user_id,
            EmailSenderGrant.can_send.is_(True),
        )
    )
    if direct_grant is not None:
        return alias
    raise PermissionError("You are not authorized to send from this email address.")


def scoped_active_user(
    db: Session,
    organization_id: UUID,
    user_id: UUID | None,
) -> User | None:
    if user_id is None:
        return None
    user = db.scalar(
        select(User).where(
            User.organization_id == organization_id,
            User.id == user_id,
            User.is_active.is_(True),
        )
    )
    if user is None:
        raise ValueError("Select an active Stonegate user.")
    return user


def scoped_active_team(
    db: Session,
    organization_id: UUID,
    team_id: UUID | None,
) -> Team | None:
    if team_id is None:
        return None
    team = db.scalar(
        select(Team).where(
            Team.organization_id == organization_id,
            Team.id == team_id,
            Team.is_active.is_(True),
        )
    )
    if team is None:
        raise ValueError("Select an active Stonegate team.")
    return team


def validate_alias_domain(email_address: str, settings: Settings) -> None:
    domain = email_address.rsplit("@", 1)[-1].lower()
    allowed_domains = {
        settings.resend_sending_domain.strip().lower(),
        settings.resend_receiving_domain.strip().lower(),
    }
    if domain not in allowed_domains:
        raise ValueError("Email aliases must use an approved Stonegate email domain.")


def validate_alias_assignment(
    *,
    alias_type: str,
    status: str,
    owner_user_id: UUID | None,
) -> None:
    if alias_type in {"named", "contractor"} and status == "active" and owner_user_id is None:
        raise ValueError("An active named or contractor address requires an assigned user.")


def normalized_channel_state(
    status: str,
    inbound_enabled: bool,
    outbound_enabled: bool,
) -> tuple[bool, bool]:
    if status != "active":
        return False, False
    return inbound_enabled, outbound_enabled


def clear_default_alias(
    db: Session,
    organization_id: UUID,
    *,
    except_alias_id: UUID | None = None,
) -> None:
    filters = [
        EmailSenderAlias.organization_id == organization_id,
        EmailSenderAlias.is_default.is_(True),
    ]
    if except_alias_id is not None:
        filters.append(EmailSenderAlias.id != except_alias_id)
    db.execute(update(EmailSenderAlias).where(*filters).values(is_default=False))


def require_alias_manager(principal: Principal) -> None:
    if PermissionKeys.MANAGE_EMAIL_ACCOUNTS not in principal.permission_keys:
        raise PermissionError("Email alias administration requires owner or manager access.")


def clean_optional_text(value: str | None) -> str | None:
    normalized = value.strip() if value else ""
    return normalized or None


def alias_snapshot(alias: EmailSenderAlias) -> dict[str, object]:
    return {
        "email_address": alias.email_address,
        "display_name": alias.display_name,
        "alias_type": alias.alias_type,
        "purpose_key": alias.purpose_key,
        "status": alias.status,
        "owner_user_id": str(alias.owner_user_id) if alias.owner_user_id else None,
        "assigned_team_id": str(alias.assigned_team_id) if alias.assigned_team_id else None,
        "inbound_enabled": alias.inbound_enabled,
        "outbound_enabled": alias.outbound_enabled,
        "is_default": alias.is_default,
    }


def grant_snapshot(grant: EmailSenderGrant) -> dict[str, object]:
    return {
        "alias_id": str(grant.email_sender_alias_id),
        "user_id": str(grant.user_id),
        "access_level": grant.access_level,
        "can_send": grant.can_send,
        "receives_notifications": grant.receives_notifications,
    }


def add_alias_audit(
    db: Session,
    principal: Principal,
    alias: EmailSenderAlias,
    *,
    action: str,
    previous: dict[str, object] | None,
    reason: str,
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type="email_sender_alias",
            entity_id=alias.id,
            previous_value=previous,
            new_value=alias_snapshot(alias),
            reason=reason,
        )
    )
