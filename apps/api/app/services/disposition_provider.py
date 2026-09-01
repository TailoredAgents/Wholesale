import csv
import json
from datetime import UTC, datetime
from hashlib import sha256
from io import StringIO
from typing import Any, Literal, cast
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.integrations.disposition_provider import get_disposition_provider_adapter
from app.models.foundation import (
    AuditEvent,
    DispositionCase,
    DispositionPackageVersion,
    DispositionProviderAccount,
    DispositionProviderEvidence,
    DispositionProviderListing,
    DispositionProviderListingRevision,
    DispositionProviderSourceLink,
    DispositionProviderSyncRun,
    Lead,
)
from app.schemas.disposition_provider import (
    ProviderAccountRead,
    ProviderApprovedPackageRead,
    ProviderAvailablePackageRead,
    ProviderDisconnectRequest,
    ProviderEvidenceRead,
    ProviderListingRead,
    ProviderListingRevisionApproval,
    ProviderListingRevisionCreate,
    ProviderListingRevisionRead,
    ProviderManualEventCreate,
    ProviderManualEventReview,
    ProviderManualLinkCreate,
    ProviderManualRefresh,
    ProviderPermissionRead,
    ProviderSourceLinkRead,
    ProviderSyncRunRead,
    ProviderVerificationGateRead,
    ProviderWorkspaceRead,
)
from app.services import disposition_packages

PROVIDER_KEY = "investorlift"
MAX_METADATA_BYTES = 8_000
MAX_METADATA_KEYS = 50
FORBIDDEN_METADATA_FRAGMENTS = {
    "assignment_fee",
    "contract_price",
    "desired_assignment",
    "internal",
    "margin",
    "minimum_acceptable",
    "private",
    "profit",
    "purchase_price",
    "seller_contact",
    "seller_email",
    "seller_name",
    "seller_phone",
}


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}.")


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def _canonical_hash(payload: Any) -> str:
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _revision_truth_snapshot_matches(
    revision: DispositionProviderListingRevision,
) -> bool:
    if revision.public_payload_sha256 != _canonical_hash(revision.public_payload):
        return False
    if revision.package_was_current_at_prepare is None:
        # Legacy revisions were prepared only from a current approved package.
        return True
    package_snapshot = revision.public_payload.get("package")
    if not isinstance(package_snapshot, dict):
        return False
    expected_status = revision.package_status_at_prepare or "approved"
    expected_preliminary = (
        expected_status != "approved" or not revision.package_was_current_at_prepare
    )
    if "status_at_prepare" in package_snapshot:
        return (
            package_snapshot.get("status_at_prepare") == expected_status
            and package_snapshot.get("was_current_at_prepare")
            is revision.package_was_current_at_prepare
            and package_snapshot.get("preliminary_at_prepare") is expected_preliminary
        )
    # Transitional 0123 payloads used unsuffixed names; retain compatibility.
    return (
        package_snapshot.get("status") == expected_status
        and package_snapshot.get("preliminary") is expected_preliminary
    )


def _as_utc(value: datetime) -> datetime:
    comparable = value if value.tzinfo else value.replace(tzinfo=UTC)
    return comparable.astimezone(UTC)


def _csv_safe(value: object | None) -> str:
    rendered = "" if value is None else str(value)
    if rendered and rendered[0] in "=+-@\t\r\n":
        return "'" + rendered
    return rendered


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _provider_url(value: object) -> str:
    url = str(value).strip()
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        hostname == "investorlift.com" or hostname.endswith(".investorlift.com")
    ):
        raise ValueError("InvestorLift links must use HTTPS on an investorlift.com host.")
    return url


def _safe_metadata_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        raise ValueError("Manual provider metadata is nested too deeply.")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:1000]
    if isinstance(value, list):
        if len(value) > 50:
            raise ValueError("Manual provider metadata lists cannot exceed 50 items.")
        return [_safe_metadata_value(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > MAX_METADATA_KEYS:
            raise ValueError("Manual provider metadata cannot exceed 50 keys per object.")
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key).strip()[:120]
            normalized_key = key.lower().replace("-", "_").replace(" ", "_")
            if not key:
                raise ValueError("Manual provider metadata keys cannot be blank.")
            if any(fragment in normalized_key for fragment in FORBIDDEN_METADATA_FRAGMENTS):
                raise ValueError(
                    f"Manual provider metadata cannot contain private field '{key}'."
                )
            result[key] = _safe_metadata_value(item, depth=depth + 1)
        return result
    raise ValueError(
        "Manual provider metadata may contain only JSON objects, lists, strings, numbers, "
        "booleans, and null."
    )


def _safe_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = cast(dict[str, Any], _safe_metadata_value(payload))
    if len(_canonical_json(sanitized).encode("utf-8")) > MAX_METADATA_BYTES:
        raise ValueError("Manual provider metadata cannot exceed 8,000 bytes.")
    return sanitized


def _case(
    db: Session,
    principal: Principal,
    case_id: UUID,
    *,
    for_update: bool = False,
) -> DispositionCase | None:
    statement = select(DispositionCase).where(
        DispositionCase.id == case_id,
        DispositionCase.organization_id == principal.organization_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return db.scalar(statement)


def _require_house(db: Session, principal: Principal, case: DispositionCase) -> Lead:
    lead = db.scalar(
        select(Lead).where(
            Lead.id == case.lead_id,
            Lead.organization_id == principal.organization_id,
        )
    )
    if lead is None:
        raise ValueError("The disposition case does not have a tenant-scoped lead.")
    if lead.asset_class != "house":
        raise ValueError(
            "InvestorLift manual handoff is House-only. Land provider handoff remains "
            "disabled until its asset-safe disposition workflow is implemented."
        )
    return lead


def _account(
    db: Session,
    principal: Principal,
    *,
    create: bool,
) -> DispositionProviderAccount | None:
    account = db.scalar(
        select(DispositionProviderAccount).where(
            DispositionProviderAccount.organization_id == principal.organization_id,
            DispositionProviderAccount.provider_key == PROVIDER_KEY,
        )
    )
    if account is not None or not create:
        return account
    adapter = get_disposition_provider_adapter(PROVIDER_KEY)
    now = datetime.now(UTC)
    account = DispositionProviderAccount(
        organization_id=principal.organization_id,
        provider_key=PROVIDER_KEY,
        provider_label=adapter.capabilities.provider_label,
        connection_mode="manual",
        status="manual_ready",
        capability_snapshot=adapter.capabilities.snapshot(),
        created_by_user_id=principal.user_id,
        connected_at=now,
    )
    db.add(account)
    db.flush()
    return account


def _listing(
    db: Session,
    principal: Principal,
    case_id: UUID,
    account_id: UUID | None = None,
    *,
    for_update: bool = False,
) -> DispositionProviderListing | None:
    conditions = [
        DispositionProviderListing.organization_id == principal.organization_id,
        DispositionProviderListing.disposition_case_id == case_id,
    ]
    if account_id is not None:
        conditions.append(DispositionProviderListing.provider_account_id == account_id)
    statement = select(DispositionProviderListing).where(*conditions)
    if for_update:
        statement = statement.with_for_update()
    return db.scalar(statement)


def _revisions(
    db: Session,
    principal: Principal,
    listing_id: UUID,
) -> list[DispositionProviderListingRevision]:
    return list(
        db.scalars(
            select(DispositionProviderListingRevision)
            .where(
                DispositionProviderListingRevision.organization_id
                == principal.organization_id,
                DispositionProviderListingRevision.listing_id == listing_id,
            )
            .order_by(DispositionProviderListingRevision.revision_number.desc())
        ).all()
    )


def _source_links(
    db: Session,
    principal: Principal,
    listing_id: UUID,
) -> list[DispositionProviderSourceLink]:
    return list(
        db.scalars(
            select(DispositionProviderSourceLink)
            .where(
                DispositionProviderSourceLink.organization_id == principal.organization_id,
                DispositionProviderSourceLink.listing_id == listing_id,
            )
            .order_by(DispositionProviderSourceLink.observed_at.desc())
        ).all()
    )


def _provider_evidence(
    db: Session,
    principal: Principal,
    listing_id: UUID,
) -> list[DispositionProviderEvidence]:
    return list(
        db.scalars(
            select(DispositionProviderEvidence)
            .where(
                DispositionProviderEvidence.organization_id == principal.organization_id,
                DispositionProviderEvidence.listing_id == listing_id,
            )
            .order_by(DispositionProviderEvidence.occurred_at.desc())
        ).all()
    )


def _runs(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> list[DispositionProviderSyncRun]:
    return list(
        db.scalars(
            select(DispositionProviderSyncRun)
            .where(
                DispositionProviderSyncRun.organization_id == principal.organization_id,
                DispositionProviderSyncRun.disposition_case_id == case_id,
            )
            .order_by(DispositionProviderSyncRun.started_at.desc())
            .limit(25)
        ).all()
    )


def _account_read(account: DispositionProviderAccount) -> ProviderAccountRead:
    return ProviderAccountRead(
        id=account.id,
        provider_key="investorlift",
        provider_label=account.provider_label,
        mode="manual",
        status="manual_ready",
        capability_snapshot=account.capability_snapshot,
        connected_at=account.connected_at,
    )


def _revision_read(
    revision: DispositionProviderListingRevision,
    *,
    latest_id: UUID | None,
    package_is_current_now: bool,
) -> ProviderListingRevisionRead:
    package_status = revision.package_status_at_prepare or "approved"
    package_was_current = (
        revision.package_was_current_at_prepare
        if revision.package_was_current_at_prepare is not None
        else True
    )
    return ProviderListingRevisionRead(
        id=revision.id,
        listing_id=revision.listing_id,
        package_version_id=revision.package_version_id,
        revision_number=revision.revision_number,
        lock_version=revision.lock_version,
        status=cast(Literal["draft", "approved", "superseded"], revision.status),
        public_payload=revision.public_payload,
        public_payload_sha256=revision.public_payload_sha256,
        package_source_fingerprint=revision.package_source_fingerprint,
        package_status=package_status,
        package_was_current_at_prepare=package_was_current,
        package_is_current_now=package_is_current_now,
        package_is_preliminary=(
            package_status != "approved"
            or not package_was_current
            or not package_is_current_now
        ),
        created_by_user_id=revision.created_by_user_id,
        approved_by_user_id=revision.approved_by_user_id,
        approval_reason=revision.approval_reason,
        approved_at=revision.approved_at,
        created_at=revision.created_at,
        is_current=bool(
            revision.id == latest_id
            and revision.status in {"draft", "approved"}
        ),
    )


def _revision_package_is_current_now(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    revision: DispositionProviderListingRevision,
) -> bool:
    package = db.scalar(
        select(DispositionPackageVersion).where(
            DispositionPackageVersion.id == revision.package_version_id,
            DispositionPackageVersion.organization_id == principal.organization_id,
            DispositionPackageVersion.disposition_case_id == case.id,
        )
    )
    return bool(
        package is not None
        and disposition_packages.package_version_currentness(
            db, principal, case, package
        )
    )


def _listing_read(
    listing: DispositionProviderListing,
    revisions: list[DispositionProviderListingRevision],
) -> ProviderListingRead:
    latest = revisions[0] if revisions else None
    approved = next((item for item in revisions if item.status == "approved"), None)
    return ProviderListingRead(
        id=listing.id,
        provider_account_id=listing.provider_account_id,
        disposition_case_id=listing.disposition_case_id,
        status=cast(
            Literal["draft", "release_approved", "manual_published", "disconnected"],
            listing.status,
        ),
        lock_version=listing.lock_version,
        package_version_id=listing.package_version_id,
        latest_revision_id=latest.id if latest else None,
        approved_revision_id=approved.id if approved else None,
        external_property_id=listing.external_property_id,
        external_url=listing.external_url,
        provider_status=cast(Any, listing.provider_status),
        public_payload_sha256=listing.public_payload_sha256,
        package_source_fingerprint=listing.package_source_fingerprint,
        manual_published_at=listing.manual_published_at,
        last_refreshed_at=listing.last_refreshed_at,
        disconnected_at=listing.disconnected_at,
        disconnect_reason=listing.disconnect_reason,
        created_at=listing.created_at,
        updated_at=listing.updated_at,
    )


def _source_link_read(link: DispositionProviderSourceLink) -> ProviderSourceLinkRead:
    return ProviderSourceLinkRead(
        id=link.id,
        listing_id=link.listing_id,
        listing_revision_id=link.listing_revision_id,
        external_property_id=link.external_property_id,
        external_url=link.external_url,
        provider_status=cast(Any, link.provider_status),
        source_snapshot_sha256=link.source_snapshot_sha256,
        observed_at=link.observed_at,
        note=link.note,
        created_by_user_id=link.created_by_user_id,
        created_at=link.created_at,
    )


def _evidence_read(evidence: DispositionProviderEvidence) -> ProviderEvidenceRead:
    return ProviderEvidenceRead(
        id=evidence.id,
        listing_id=evidence.listing_id,
        event_type=cast(Any, evidence.event_type),
        external_event_id=evidence.external_event_id,
        review_status=cast(Any, evidence.review_status),
        lock_version=evidence.lock_version,
        occurred_at=evidence.occurred_at,
        buyer_name=evidence.buyer_name,
        buyer_email=evidence.buyer_email,
        buyer_phone=evidence.buyer_phone,
        offer_amount_cents=evidence.offer_amount_cents,
        message=evidence.message,
        metadata=evidence.public_metadata,
        evidence_sha256=evidence.evidence_sha256,
        review_note=evidence.review_note,
        reviewed_by_user_id=evidence.reviewed_by_user_id,
        reviewed_at=evidence.reviewed_at,
        created_at=evidence.created_at,
        selection_eligible=False,
    )


def _run_read(run: DispositionProviderSyncRun) -> ProviderSyncRunRead:
    return ProviderSyncRunRead(
        id=run.id,
        listing_id=run.listing_id,
        operation=run.operation,
        status=cast(Literal["completed", "failed"], run.status),
        mode="manual",
        request_sha256=run.request_sha256,
        result_summary=run.result_summary,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def _record_run(
    db: Session,
    principal: Principal,
    *,
    account: DispositionProviderAccount,
    listing: DispositionProviderListing | None,
    case_id: UUID,
    operation: str,
    request_payload: dict[str, Any],
    result_summary: dict[str, Any],
) -> DispositionProviderSyncRun:
    now = datetime.now(UTC)
    run = DispositionProviderSyncRun(
        organization_id=principal.organization_id,
        provider_account_id=account.id,
        listing_id=listing.id if listing else None,
        disposition_case_id=case_id,
        requested_by_user_id=principal.user_id,
        operation=operation,
        status="completed",
        mode="manual",
        request_sha256=_canonical_hash(request_payload),
        result_summary=result_summary,
        error_message=None,
        started_at=now,
        completed_at=now,
    )
    db.add(run)
    return run


def _audit(
    db: Session,
    principal: Principal,
    *,
    action: str,
    entity_type: str,
    entity_id: UUID,
    new_value: dict[str, Any],
    reason: str,
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            previous_value=None,
            new_value=new_value,
            reason=reason,
        )
    )


def read_workspace(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> ProviderWorkspaceRead | None:
    case = _case(db, principal, case_id)
    if case is None:
        return None
    lead = db.scalar(
        select(Lead).where(
            Lead.id == case.lead_id,
            Lead.organization_id == principal.organization_id,
        )
    )
    eligible = bool(lead and lead.asset_class == "house")
    eligibility_blockers = [] if eligible else ["InvestorLift manual handoff is House-only."]
    adapter = get_disposition_provider_adapter(PROVIDER_KEY)
    account = _account(db, principal, create=False)
    listing = _listing(db, principal, case.id, account.id if account else None)
    revisions = _revisions(db, principal, listing.id) if listing else []
    source_links = _source_links(db, principal, listing.id) if listing else []
    staged = _provider_evidence(db, principal, listing.id) if listing else []
    latest_package = db.scalar(
        select(DispositionPackageVersion)
        .where(
            DispositionPackageVersion.organization_id == principal.organization_id,
            DispositionPackageVersion.disposition_case_id == case.id,
        )
        .order_by(
            DispositionPackageVersion.version_number.desc(),
            DispositionPackageVersion.created_at.desc(),
        )
        .limit(1)
    )
    try:
        available_package = disposition_packages.require_package_artifact(
            db,
            principal,
            case,
            action="preparing a provider handoff",
        )
    except ValueError:
        available_package = None
    approved_package = db.scalar(
        select(DispositionPackageVersion)
        .where(
            DispositionPackageVersion.organization_id == principal.organization_id,
            DispositionPackageVersion.disposition_case_id == case.id,
            DispositionPackageVersion.status == "approved",
            DispositionPackageVersion.pdf_data.is_not(None),
        )
        .order_by(
            DispositionPackageVersion.version_number.desc(),
            DispositionPackageVersion.created_at.desc(),
        )
        .limit(1)
    )
    package_is_current = bool(
        approved_package
        and latest_package
        and approved_package.id == latest_package.id
        and disposition_packages.package_version_currentness(
            db,
            principal,
            case,
            approved_package,
        )
    )
    available_package_is_current = bool(
        available_package
        and latest_package
        and available_package.id == latest_package.id
        and disposition_packages.package_version_currentness(
            db,
            principal,
            case,
            available_package,
        )
    )
    latest_id = revisions[0].id if revisions else None
    warnings: list[str] = []
    if available_package is None:
        warnings.append(
            "No usable package artifact is available to attach to a provider handoff yet."
        )
    if listing and listing.status == "disconnected":
        warnings.append(
            "This listing is disconnected. Stonegate history remains available and no provider "
            "network operation will run."
        )
    if (
        listing
        and listing.package_source_fingerprint
        and available_package
        and (
            listing.package_source_fingerprint != available_package.source_fingerprint
            or not available_package_is_current
        )
    ):
        warnings.append(
            "The provider handoff uses a different package snapshot than the latest usable "
            "artifact. That is allowed; verify the intended exact version before publishing."
        )
    permissions = principal.permission_keys
    can_edit = (
        PermissionKeys.EDIT_DEALS in permissions
        and PermissionKeys.MANAGE_DISPOSITION_OUTREACH in permissions
    )
    can_view = PermissionKeys.VIEW_DEALS in permissions
    can_approve = PermissionKeys.APPROVE_DISPOSITION_OUTREACH in permissions
    caps = adapter.capabilities
    return ProviderWorkspaceRead(
        case_id=case.id,
        provider_key="investorlift",
        provider_label=caps.provider_label,
        house_only=True,
        eligible=eligible,
        eligibility_blockers=eligibility_blockers,
        permissions=ProviderPermissionRead(
            can_prepare=can_edit and eligible,
            can_approve=can_approve and eligible,
            can_record_manual=can_edit and eligible,
            can_disconnect=can_edit and bool(listing and listing.status != "disconnected"),
            can_export=can_view,
        ),
        verification_gate=ProviderVerificationGateRead(
            provider_key="investorlift",
            mode="manual",
            api_contract_verified=caps.api_contract_verified,
            live_transport_enabled=caps.live_transport_enabled,
            credential_required=caps.credential_required,
            house_only=True,
            blockers=list(caps.blockers),
            supported_manual_capabilities=list(caps.supported_manual_capabilities),
            unverified_capabilities=list(caps.unverified_capabilities),
        ),
        account=_account_read(account) if account else None,
        available_package=(
            ProviderAvailablePackageRead(
                package_version_id=available_package.id,
                version_number=available_package.version_number,
                source_fingerprint=available_package.source_fingerprint,
                status=available_package.status,
                is_current=available_package_is_current,
            )
            if available_package
            else None
        ),
        approved_package=(
            ProviderApprovedPackageRead(
                package_version_id=approved_package.id,
                version_number=approved_package.version_number,
                source_fingerprint=approved_package.source_fingerprint,
                approved_at=_as_utc(approved_package.approved_at),
                is_current=package_is_current,
            )
            if approved_package and approved_package.approved_at
            else None
        ),
        listing=_listing_read(listing, revisions) if listing else None,
        revisions=[
            _revision_read(
                item,
                latest_id=latest_id,
                package_is_current_now=_revision_package_is_current_now(
                    db, principal, case, item
                ),
            )
            for item in revisions
        ],
        source_links=[_source_link_read(item) for item in source_links],
        staged_events=[_evidence_read(item) for item in staged],
        recent_runs=[_run_read(item) for item in _runs(db, principal, case.id)],
        warnings=warnings,
    )


def create_listing_revision(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: ProviderListingRevisionCreate,
) -> ProviderWorkspaceRead | None:
    # The case lock serializes first-time listing creation, while the listing lock below
    # serializes revision numbering once the provider row exists. The optimistic expected
    # revision guard remains the user-facing stale-write check.
    case = _case(db, principal, case_id, for_update=True)
    if case is None:
        return None
    _require_house(db, principal, case)
    package = disposition_packages.require_package_artifact(
        db,
        principal,
        case,
        action="preparing an InvestorLift handoff",
        package_version_id=payload.package_version_id,
    )
    account = cast(DispositionProviderAccount, _account(db, principal, create=True))
    listing = _listing(db, principal, case.id, account.id, for_update=True)
    if listing is not None and listing.status == "disconnected":
        raise ValueError(
            "This provider listing is disconnected. A separately governed reconnect action is "
            "required before preparing another revision."
        )
    if listing is None:
        listing = DispositionProviderListing(
            organization_id=principal.organization_id,
            provider_account_id=account.id,
            disposition_case_id=case.id,
            property_id=case.property_id,
            created_by_user_id=principal.user_id,
            status="draft",
            lock_version=1,
        )
        db.add(listing)
        db.flush()
    latest_number = (
        db.scalar(
            select(func.max(DispositionProviderListingRevision.revision_number)).where(
                DispositionProviderListingRevision.organization_id
                == principal.organization_id,
                DispositionProviderListingRevision.listing_id == listing.id,
            )
        )
        or 0
    )
    if latest_number != payload.expected_latest_revision:
        raise ValueError(
            "Provider listing revision changed. Expected latest revision "
            f"{payload.expected_latest_revision}; current latest is {latest_number}."
        )
    safe_snapshot = disposition_packages.sanitize_public_snapshot(package.public_snapshot)
    package_was_current = disposition_packages.package_version_currentness(
        db,
        principal,
        case,
        package,
    )
    adapter = get_disposition_provider_adapter(PROVIDER_KEY)
    public_payload = adapter.build_public_listing_payload(
        package_version=package.version_number,
        package_status=package.status,
        package_was_current_at_prepare=package_was_current,
        package_preliminary=package.status != "approved" or not package_was_current,
        package_snapshot_at=_as_utc(
            package.approved_at or package.created_at
        ).isoformat(),
        package_snapshot=safe_snapshot,
    )
    public_hash = _canonical_hash(public_payload)
    for prior in db.scalars(
        select(DispositionProviderListingRevision).where(
            DispositionProviderListingRevision.organization_id == principal.organization_id,
            DispositionProviderListingRevision.listing_id == listing.id,
            DispositionProviderListingRevision.status.in_(("draft", "approved")),
        )
    ).all():
        prior.status = "superseded"
        prior.lock_version += 1
    revision = DispositionProviderListingRevision(
        organization_id=principal.organization_id,
        listing_id=listing.id,
        disposition_case_id=case.id,
        package_version_id=package.id,
        created_by_user_id=principal.user_id,
        approved_by_user_id=None,
        revision_number=latest_number + 1,
        lock_version=1,
        status="draft",
        public_payload=public_payload,
        public_payload_sha256=public_hash,
        package_source_fingerprint=package.source_fingerprint,
        package_status_at_prepare=package.status,
        package_was_current_at_prepare=package_was_current,
        approval_reason=None,
        approved_at=None,
    )
    db.add(revision)
    listing.status = "draft"
    listing.package_version_id = package.id
    listing.public_payload_sha256 = public_hash
    listing.package_source_fingerprint = package.source_fingerprint
    listing.lock_version += 1
    db.flush()
    _audit(
        db,
        principal,
        action="disposition.provider_revision_create",
        entity_type="disposition_provider_listing_revision",
        entity_id=revision.id,
        new_value={
            "case_id": str(case.id),
            "revision_number": revision.revision_number,
            "public_payload_sha256": public_hash,
            "package_version_id": str(package.id),
        },
        reason="Buyer-safe manual provider handoff revision prepared",
    )
    _record_run(
        db,
        principal,
        account=account,
        listing=listing,
        case_id=case.id,
        operation="prepare_revision",
        request_payload={
            "package_version_id": str(package.id),
            "expected_latest_revision": payload.expected_latest_revision,
            "public_payload_sha256": public_hash,
        },
        result_summary={
            "listing_revision_id": str(revision.id),
            "revision_number": revision.revision_number,
            "status": "draft",
        },
    )
    db.commit()
    return read_workspace(db, principal, case.id)


def approve_listing_revision(
    db: Session,
    principal: Principal,
    case_id: UUID,
    revision_id: UUID,
    payload: ProviderListingRevisionApproval,
) -> ProviderWorkspaceRead | None:
    case = _case(db, principal, case_id)
    if case is None:
        return None
    _require_house(db, principal, case)
    revision = db.scalar(
        select(DispositionProviderListingRevision)
        .where(
            DispositionProviderListingRevision.id == revision_id,
            DispositionProviderListingRevision.organization_id == principal.organization_id,
            DispositionProviderListingRevision.disposition_case_id == case.id,
        )
        .with_for_update()
    )
    if revision is None:
        return None
    package = disposition_packages.require_package_artifact(
        db,
        principal,
        case,
        action="approving an InvestorLift release",
        package_version_id=revision.package_version_id,
    )
    listing = db.scalar(
        select(DispositionProviderListing)
        .where(
            DispositionProviderListing.id == revision.listing_id,
            DispositionProviderListing.organization_id == principal.organization_id,
        )
        .with_for_update()
    )
    if listing is None:
        return None
    latest = db.scalar(
        select(DispositionProviderListingRevision)
        .where(
            DispositionProviderListingRevision.organization_id == principal.organization_id,
            DispositionProviderListingRevision.listing_id == listing.id,
        )
        .order_by(DispositionProviderListingRevision.revision_number.desc())
        .limit(1)
        .with_for_update()
    )
    if latest is None or latest.id != revision.id:
        raise ValueError("Only the latest provider listing revision can be approved.")
    if revision.status != "draft":
        raise ValueError("Only a draft provider listing revision can be approved.")
    if revision.lock_version != payload.expected_lock_version:
        raise ValueError(
            f"Provider revision changed. Expected lock version {payload.expected_lock_version}; "
            f"current version is {revision.lock_version}."
        )
    if (
        revision.package_version_id != package.id
        or revision.package_source_fingerprint != package.source_fingerprint
        or not _revision_truth_snapshot_matches(revision)
    ):
        raise ValueError(
            "The provider handoff package fingerprint or payload hash does not match the "
            "prepared exact snapshot."
        )
    now = datetime.now(UTC)
    for prior in db.scalars(
        select(DispositionProviderListingRevision).where(
            DispositionProviderListingRevision.organization_id == principal.organization_id,
            DispositionProviderListingRevision.listing_id == listing.id,
            DispositionProviderListingRevision.status == "approved",
            DispositionProviderListingRevision.id != revision.id,
        )
    ).all():
        prior.status = "superseded"
        prior.lock_version += 1
    revision.status = "approved"
    revision.approved_by_user_id = principal.user_id
    revision.approved_at = now
    revision.approval_reason = payload.reason
    revision.lock_version += 1
    listing.status = "release_approved"
    listing.package_version_id = package.id
    listing.public_payload_sha256 = revision.public_payload_sha256
    listing.package_source_fingerprint = revision.package_source_fingerprint
    listing.lock_version += 1
    account = cast(DispositionProviderAccount, _account(db, principal, create=False))
    _audit(
        db,
        principal,
        action="disposition.provider_revision_approve",
        entity_type="disposition_provider_listing_revision",
        entity_id=revision.id,
        new_value={
            "case_id": str(case.id),
            "revision_number": revision.revision_number,
            "public_payload_sha256": revision.public_payload_sha256,
            "exact_release_approval": True,
        },
        reason=payload.reason,
    )
    _record_run(
        db,
        principal,
        account=account,
        listing=listing,
        case_id=case.id,
        operation="approve_revision",
        request_payload={
            "listing_revision_id": str(revision.id),
            "expected_lock_version": payload.expected_lock_version,
            "public_payload_sha256": revision.public_payload_sha256,
        },
        result_summary={
            "listing_revision_id": str(revision.id),
            "status": "approved",
            "exact_release_approval": True,
        },
    )
    db.commit()
    return read_workspace(db, principal, case.id)


def listing_bundle(
    db: Session,
    principal: Principal,
    case_id: UUID,
    revision_id: UUID,
) -> tuple[bytes, str] | None:
    case = _case(db, principal, case_id)
    if case is None:
        return None
    _require_house(db, principal, case)
    revision = db.scalar(
        select(DispositionProviderListingRevision).where(
            DispositionProviderListingRevision.id == revision_id,
            DispositionProviderListingRevision.organization_id == principal.organization_id,
            DispositionProviderListingRevision.disposition_case_id == case.id,
        )
    )
    if revision is None:
        return None
    package = disposition_packages.require_package_artifact(
        db,
        principal,
        case,
        action="downloading an InvestorLift handoff bundle",
        package_version_id=revision.package_version_id,
    )
    if revision.approved_at is None or revision.approved_by_user_id is None:
        raise ValueError("Exact release approval is required before downloading this bundle.")
    if (
        revision.package_version_id != package.id
        or revision.package_source_fingerprint != package.source_fingerprint
        or not _revision_truth_snapshot_matches(revision)
    ):
        raise ValueError(
            "This provider bundle no longer matches its exact package fingerprint or payload "
            "hash."
        )
    package_is_current_now = disposition_packages.package_version_currentness(
        db, principal, case, package
    )
    package_is_preliminary = (
        (revision.package_status_at_prepare or "approved") != "approved"
        or revision.package_was_current_at_prepare is False
        or not package_is_current_now
    )
    bundle = {
        "manifest": {
            "provider": PROVIDER_KEY,
            "mode": "manual",
            "listing_revision_id": str(revision.id),
            "listing_revision_number": revision.revision_number,
            "package_version_id": str(package.id),
            "package_status_at_prepare": revision.package_status_at_prepare or "approved",
            "package_was_current_at_prepare": (
                revision.package_was_current_at_prepare
                if revision.package_was_current_at_prepare is not None
                else True
            ),
            "package_is_current_now": package_is_current_now,
            "package_is_preliminary": package_is_preliminary,
            "package_source_fingerprint": revision.package_source_fingerprint,
            "public_payload_sha256": revision.public_payload_sha256,
            "release_approved_at": _as_utc(revision.approved_at).isoformat(),
        },
        "public_payload": revision.public_payload,
    }
    data = json.dumps(bundle, indent=2, sort_keys=True, default=_json_default).encode("utf-8")
    prefix = "PRELIMINARY-" if package_is_preliminary else ""
    return (
        data,
        f"{prefix}stonegate-investorlift-handoff-{case.id}-r{revision.revision_number}.json",
    )


def _source_link_idempotency_key(
    *,
    listing_id: UUID,
    revision_id: UUID,
    operation: str,
    external_property_id: str,
    external_url: str,
    provider_status: str,
    note: str | None,
) -> str:
    return _canonical_hash(
        {
            "provider": PROVIDER_KEY,
            "listing_id": str(listing_id),
            "listing_revision_id": str(revision_id),
            "operation": operation,
            "external_property_id": external_property_id,
            "external_url": external_url,
            "provider_status": provider_status,
            "note": _normalize_optional(note),
        }
    )


def _record_source_link(
    db: Session,
    principal: Principal,
    *,
    listing: DispositionProviderListing,
    revision: DispositionProviderListingRevision,
    external_property_id: str,
    external_url: str,
    provider_status: str,
    note: str | None,
    operation: str,
) -> DispositionProviderSourceLink:
    now = datetime.now(UTC)
    case = db.scalar(
        select(DispositionCase).where(
            DispositionCase.id == revision.disposition_case_id,
            DispositionCase.organization_id == principal.organization_id,
        )
    )
    package = db.scalar(
        select(DispositionPackageVersion).where(
            DispositionPackageVersion.id == revision.package_version_id,
            DispositionPackageVersion.organization_id == principal.organization_id,
            DispositionPackageVersion.disposition_case_id == revision.disposition_case_id,
        )
    )
    package_is_current_now = bool(
        case is not None
        and package is not None
        and disposition_packages.package_version_currentness(
            db, principal, case, package
        )
    )
    package_is_preliminary = (
        (revision.package_status_at_prepare or "approved") != "approved"
        or revision.package_was_current_at_prepare is False
        or not package_is_current_now
    )
    source_snapshot = {
        "provider": PROVIDER_KEY,
        "external_property_id": external_property_id,
        "external_url": external_url,
        "provider_status": provider_status,
        "listing_revision_id": str(revision.id),
        "public_payload_sha256": revision.public_payload_sha256,
        "package_is_current_now": package_is_current_now,
        "package_is_preliminary": package_is_preliminary,
        "observed_at": now.isoformat(),
    }
    source_hash = _canonical_hash(source_snapshot)
    idempotency_key = _source_link_idempotency_key(
        listing_id=listing.id,
        revision_id=revision.id,
        operation=operation,
        external_property_id=external_property_id,
        external_url=external_url,
        provider_status=provider_status,
        note=note,
    )
    existing = db.scalar(
        select(DispositionProviderSourceLink).where(
            DispositionProviderSourceLink.organization_id == principal.organization_id,
            DispositionProviderSourceLink.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return existing
    link = DispositionProviderSourceLink(
        organization_id=principal.organization_id,
        listing_id=listing.id,
        listing_revision_id=revision.id,
        created_by_user_id=principal.user_id,
        provider_key=PROVIDER_KEY,
        external_property_id=external_property_id,
        external_url=external_url,
        provider_status=provider_status,
        source_snapshot=source_snapshot,
        source_snapshot_sha256=source_hash,
        idempotency_key=idempotency_key,
        observed_at=now,
        note=_normalize_optional(note),
    )
    db.add(link)
    db.flush()
    return link


def record_manual_link(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: ProviderManualLinkCreate,
) -> ProviderWorkspaceRead | None:
    case = _case(db, principal, case_id)
    if case is None:
        return None
    _require_house(db, principal, case)
    account = cast(DispositionProviderAccount, _account(db, principal, create=True))
    listing = _listing(db, principal, case.id, account.id, for_update=True)
    if listing is None:
        raise ValueError("Prepare and approve a provider listing revision first.")
    if listing.status == "disconnected":
        raise ValueError(
            "This provider listing is disconnected. Manual publication cannot resume without "
            "a separately governed reconnect action."
        )
    revision = db.scalar(
        select(DispositionProviderListingRevision).where(
            DispositionProviderListingRevision.id == payload.revision_id,
            DispositionProviderListingRevision.organization_id == principal.organization_id,
            DispositionProviderListingRevision.listing_id == listing.id,
        )
    )
    if (
        revision is None
        or revision.approved_at is None
        or revision.approved_by_user_id is None
    ):
        raise ValueError("An exact approved provider listing revision is required.")
    package = disposition_packages.require_package_artifact(
        db,
        principal,
        case,
        action="recording an InvestorLift publication",
        package_version_id=revision.package_version_id,
    )
    external_url = _provider_url(payload.external_url)
    stable_idempotency_key = _source_link_idempotency_key(
        listing_id=listing.id,
        revision_id=revision.id,
        operation="manual_link",
        external_property_id=payload.external_property_id,
        external_url=external_url,
        provider_status=payload.provider_status,
        note=payload.note,
    )
    replay = db.scalar(
        select(DispositionProviderSourceLink).where(
            DispositionProviderSourceLink.organization_id == principal.organization_id,
            DispositionProviderSourceLink.idempotency_key == stable_idempotency_key,
        )
    )
    if replay is not None:
        return read_workspace(db, principal, case.id)
    if listing.lock_version != payload.expected_listing_version:
        raise ValueError(
            f"Provider listing changed. Expected version {payload.expected_listing_version}; "
            f"current version is {listing.lock_version}."
        )
    if (
        revision.package_version_id != package.id
        or revision.package_source_fingerprint != package.source_fingerprint
        or not _revision_truth_snapshot_matches(revision)
    ):
        raise ValueError(
            "The approved provider listing no longer matches its exact prepared package or "
            "payload hash."
        )
    link = _record_source_link(
        db,
        principal,
        listing=listing,
        revision=revision,
        external_property_id=payload.external_property_id,
        external_url=external_url,
        provider_status=payload.provider_status,
        note=payload.note,
        operation="manual_link",
    )
    now = datetime.now(UTC)
    listing.status = "manual_published"
    listing.external_property_id = payload.external_property_id
    listing.external_url = external_url
    listing.provider_status = payload.provider_status
    listing.manual_published_at = listing.manual_published_at or now
    listing.last_refreshed_at = now
    listing.lock_version += 1
    _record_run(
        db,
        principal,
        account=account,
        listing=listing,
        case_id=case.id,
        operation="manual_link",
        request_payload=link.source_snapshot,
        result_summary={"source_link_id": str(link.id), "provider_status": payload.provider_status},
    )
    _audit(
        db,
        principal,
        action="disposition.provider_manual_link",
        entity_type="disposition_provider_listing",
        entity_id=listing.id,
        new_value={
            "source_link_id": str(link.id),
            "external_property_id": payload.external_property_id,
            "provider_status": payload.provider_status,
        },
        reason=payload.note or "Manual InvestorLift publication recorded",
    )
    db.commit()
    return read_workspace(db, principal, case.id)


def record_manual_event(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: ProviderManualEventCreate,
) -> ProviderWorkspaceRead | None:
    case = _case(db, principal, case_id)
    if case is None:
        return None
    _require_house(db, principal, case)
    account = _account(db, principal, create=False)
    listing = _listing(db, principal, case.id, account.id if account else None)
    if account is None or listing is None or listing.status != "manual_published":
        raise ValueError(
            "Record the manual provider listing link before staging provider evidence."
        )
    source_link = db.scalar(
        select(DispositionProviderSourceLink)
        .where(
            DispositionProviderSourceLink.organization_id == principal.organization_id,
            DispositionProviderSourceLink.listing_id == listing.id,
        )
        .order_by(DispositionProviderSourceLink.observed_at.desc())
    )
    metadata = _safe_metadata(payload.metadata)
    evidence_payload = {
        "listing_id": str(listing.id),
        "event_type": payload.event_type,
        "external_event_id": _normalize_optional(payload.external_event_id),
        "occurred_at": payload.occurred_at.astimezone(UTC).isoformat(),
        "buyer_name": _normalize_optional(payload.buyer_name),
        "buyer_email": _normalize_optional(payload.buyer_email),
        "buyer_phone": _normalize_optional(payload.buyer_phone),
        "offer_amount_cents": payload.offer_amount_cents,
        "message": _normalize_optional(payload.message),
        "metadata": metadata,
    }
    evidence_hash = _canonical_hash(evidence_payload)
    external_event_id = evidence_payload["external_event_id"]
    idempotency_key = _canonical_hash(
        {
            "provider": PROVIDER_KEY,
            "listing_id": listing.id,
            "event_type": payload.event_type,
            "external_event_id": external_event_id,
        }
        if external_event_id
        else {"provider": PROVIDER_KEY, "evidence_sha256": evidence_hash}
    )
    existing = db.scalar(
        select(DispositionProviderEvidence).where(
            DispositionProviderEvidence.organization_id == principal.organization_id,
            DispositionProviderEvidence.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.evidence_sha256 != evidence_hash:
            raise ValueError(
                "This provider event ID was already recorded with different evidence. "
                "Review the existing staged event instead of overwriting it."
            )
        return read_workspace(db, principal, case.id)
    event = DispositionProviderEvidence(
        organization_id=principal.organization_id,
        listing_id=listing.id,
        disposition_case_id=case.id,
        source_link_id=source_link.id if source_link else None,
        recorded_by_user_id=principal.user_id,
        reviewed_by_user_id=None,
        event_type=payload.event_type,
        external_event_id=cast(str | None, external_event_id),
        idempotency_key=idempotency_key,
        review_status="staged",
        lock_version=1,
        occurred_at=payload.occurred_at,
        buyer_name=cast(str | None, evidence_payload["buyer_name"]),
        buyer_email=cast(str | None, evidence_payload["buyer_email"]),
        buyer_phone=cast(str | None, evidence_payload["buyer_phone"]),
        offer_amount_cents=payload.offer_amount_cents,
        message=cast(str | None, evidence_payload["message"]),
        public_metadata=metadata,
        evidence_sha256=evidence_hash,
        review_note=None,
        reviewed_at=None,
    )
    db.add(event)
    db.flush()
    _record_run(
        db,
        principal,
        account=account,
        listing=listing,
        case_id=case.id,
        operation="manual_event",
        request_payload=evidence_payload,
        result_summary={
            "evidence_id": str(event.id),
            "event_type": event.event_type,
            "review_status": "staged",
            "selection_eligible": False,
        },
    )
    _audit(
        db,
        principal,
        action="disposition.provider_evidence_stage",
        entity_type="disposition_provider_evidence",
        entity_id=event.id,
        new_value={
            "event_type": event.event_type,
            "evidence_sha256": evidence_hash,
            "review_status": "staged",
            "selection_eligible": False,
        },
        reason="Manual provider evidence staged for human review",
    )
    db.commit()
    return read_workspace(db, principal, case.id)


def review_manual_event(
    db: Session,
    principal: Principal,
    case_id: UUID,
    event_id: UUID,
    payload: ProviderManualEventReview,
) -> ProviderWorkspaceRead | None:
    case = _case(db, principal, case_id)
    if case is None:
        return None
    _require_house(db, principal, case)
    event = db.scalar(
        select(DispositionProviderEvidence)
        .where(
            DispositionProviderEvidence.id == event_id,
            DispositionProviderEvidence.organization_id == principal.organization_id,
            DispositionProviderEvidence.disposition_case_id == case.id,
        )
        .with_for_update()
    )
    if event is None:
        return None
    if event.review_status != "staged":
        raise ValueError("Only staged provider evidence can be reviewed.")
    if event.lock_version != payload.expected_lock_version:
        raise ValueError(
            f"Provider evidence changed. Expected version {payload.expected_lock_version}; "
            f"current version is {event.lock_version}."
        )
    event.review_status = payload.review_status
    event.review_note = _normalize_optional(payload.review_note)
    event.reviewed_by_user_id = principal.user_id
    event.reviewed_at = datetime.now(UTC)
    event.lock_version += 1
    account = cast(DispositionProviderAccount, _account(db, principal, create=False))
    listing = cast(
        DispositionProviderListing,
        _listing(db, principal, case.id, account.id),
    )
    _audit(
        db,
        principal,
        action="disposition.provider_evidence_review",
        entity_type="disposition_provider_evidence",
        entity_id=event.id,
        new_value={
            "review_status": event.review_status,
            "selection_eligible": False,
            "buyer_or_offer_created": False,
        },
        reason=event.review_note or f"Provider evidence marked {event.review_status}",
    )
    _record_run(
        db,
        principal,
        account=account,
        listing=listing,
        case_id=case.id,
        operation="review_event",
        request_payload={
            "evidence_id": str(event.id),
            "expected_lock_version": payload.expected_lock_version,
            "review_status": payload.review_status,
        },
        result_summary={
            "evidence_id": str(event.id),
            "review_status": event.review_status,
            "selection_eligible": False,
        },
    )
    db.commit()
    return read_workspace(db, principal, case.id)


def manual_refresh(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: ProviderManualRefresh,
) -> ProviderWorkspaceRead | None:
    case = _case(db, principal, case_id)
    if case is None:
        return None
    _require_house(db, principal, case)
    account = _account(db, principal, create=False)
    listing = _listing(
        db,
        principal,
        case.id,
        account.id if account else None,
        for_update=True,
    )
    if account is None or listing is None:
        raise ValueError("No manual provider listing exists for this case.")
    if listing.status == "disconnected":
        raise ValueError("This provider listing is disconnected.")
    revisions = _revisions(db, principal, listing.id)
    revision = next((item for item in revisions if item.status == "approved"), None)
    if revision is None:
        raise ValueError("An approved provider listing revision is required.")
    external_property_id = _normalize_optional(payload.external_property_id) or (
        listing.external_property_id
    )
    external_url = (
        _provider_url(payload.external_url) if payload.external_url else listing.external_url
    )
    if not external_property_id or not external_url:
        raise ValueError("External property ID and InvestorLift URL are required for refresh.")
    refresh_key = _source_link_idempotency_key(
        listing_id=listing.id,
        revision_id=revision.id,
        operation="manual_refresh",
        external_property_id=external_property_id,
        external_url=external_url,
        provider_status=payload.provider_status,
        note=payload.note,
    )
    replay = db.scalar(
        select(DispositionProviderSourceLink).where(
            DispositionProviderSourceLink.organization_id == principal.organization_id,
            DispositionProviderSourceLink.idempotency_key == refresh_key,
        )
    )
    if replay is not None:
        return read_workspace(db, principal, case.id)
    link = _record_source_link(
        db,
        principal,
        listing=listing,
        revision=revision,
        external_property_id=external_property_id,
        external_url=external_url,
        provider_status=payload.provider_status,
        note=payload.note,
        operation="manual_refresh",
    )
    now = datetime.now(UTC)
    listing.external_property_id = external_property_id
    listing.external_url = external_url
    listing.provider_status = payload.provider_status
    listing.last_refreshed_at = now
    listing.lock_version += 1
    _record_run(
        db,
        principal,
        account=account,
        listing=listing,
        case_id=case.id,
        operation="manual_refresh",
        request_payload=link.source_snapshot,
        result_summary={"source_link_id": str(link.id), "provider_status": payload.provider_status},
    )
    db.commit()
    return read_workspace(db, principal, case.id)


def disconnect(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: ProviderDisconnectRequest,
) -> ProviderWorkspaceRead | None:
    case = _case(db, principal, case_id)
    if case is None:
        return None
    _require_house(db, principal, case)
    account = _account(db, principal, create=False)
    listing = _listing(
        db,
        principal,
        case.id,
        account.id if account else None,
        for_update=True,
    )
    if account is None or listing is None:
        raise ValueError("No provider listing exists for this case.")
    if listing.status == "disconnected":
        return read_workspace(db, principal, case.id)
    now = datetime.now(UTC)
    listing.status = "disconnected"
    listing.disconnected_at = now
    listing.disconnected_by_user_id = principal.user_id
    listing.disconnect_reason = payload.reason
    listing.lock_version += 1
    _record_run(
        db,
        principal,
        account=account,
        listing=listing,
        case_id=case.id,
        operation="disconnect",
        request_payload={"listing_id": str(listing.id), "reason": payload.reason},
        result_summary={"history_preserved": True, "network_operations_stopped": True},
    )
    _audit(
        db,
        principal,
        action="disposition.provider_disconnect",
        entity_type="disposition_provider_listing",
        entity_id=listing.id,
        new_value={"status": "disconnected", "history_preserved": True},
        reason=payload.reason,
    )
    db.commit()
    return read_workspace(db, principal, case.id)


def export_case(
    db: Session,
    principal: Principal,
    case_id: UUID,
    *,
    export_format: Literal["json", "csv"],
) -> tuple[bytes, str, str] | None:
    case = _case(db, principal, case_id)
    if case is None:
        return None
    account = _account(db, principal, create=False)
    listing = _listing(db, principal, case.id, account.id if account else None)
    revisions = _revisions(db, principal, listing.id) if listing else []
    links = _source_links(db, principal, listing.id) if listing else []
    evidence = (
        list(
            db.scalars(
                select(DispositionProviderEvidence)
                .where(
                    DispositionProviderEvidence.organization_id == principal.organization_id,
                    DispositionProviderEvidence.disposition_case_id == case.id,
                )
                .order_by(DispositionProviderEvidence.occurred_at.desc())
            ).all()
        )
        if listing
        else []
    )
    runs = _runs(db, principal, case.id)
    export_payload = {
        "schema_version": "stonegate.disposition_provider_export.v1",
        "exported_at": datetime.now(UTC).isoformat(),
        "provider": PROVIDER_KEY,
        "mode": "manual",
        "case_id": str(case.id),
        "account": _account_read(account).model_dump(mode="json") if account else None,
        "listing": (
            _listing_read(listing, revisions).model_dump(mode="json") if listing else None
        ),
        "revisions": [
            _revision_read(
                item,
                latest_id=revisions[0].id if revisions else None,
                package_is_current_now=_revision_package_is_current_now(
                    db, principal, case, item
                ),
            ).model_dump(mode="json")
            for item in revisions
        ],
        "source_links": [_source_link_read(item).model_dump(mode="json") for item in links],
        "evidence": [_evidence_read(item).model_dump(mode="json") for item in evidence],
        "runs": [_run_read(item).model_dump(mode="json") for item in runs],
        "history_preserved": True,
        "contains_private_stonegate_economics": False,
    }
    if export_format == "json":
        data = json.dumps(export_payload, indent=2, sort_keys=True).encode("utf-8")
        return data, f"stonegate-provider-export-{case.id}.json", "application/json"
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "record_type",
            "record_id",
            "occurred_at",
            "status",
            "external_id",
            "external_url",
            "sha256",
            "data_json",
        ],
    )
    writer.writeheader()
    for revision in revisions:
        writer.writerow(
            {
                "record_type": "listing_revision",
                "record_id": _csv_safe(revision.id),
                "occurred_at": _csv_safe(revision.created_at.isoformat()),
                "status": _csv_safe(revision.status),
                "sha256": revision.public_payload_sha256,
                "data_json": _canonical_json(revision.public_payload),
            }
        )
    for link in links:
        writer.writerow(
            {
                "record_type": "source_link",
                "record_id": _csv_safe(link.id),
                "occurred_at": _csv_safe(link.observed_at.isoformat()),
                "status": _csv_safe(link.provider_status),
                "external_id": _csv_safe(link.external_property_id),
                "external_url": _csv_safe(link.external_url),
                "sha256": link.source_snapshot_sha256,
                "data_json": _canonical_json(link.source_snapshot),
            }
        )
    for item in evidence:
        writer.writerow(
            {
                "record_type": f"evidence_{item.event_type}",
                "record_id": _csv_safe(item.id),
                "occurred_at": _csv_safe(item.occurred_at.isoformat()),
                "status": _csv_safe(item.review_status),
                "external_id": _csv_safe(item.external_event_id),
                "sha256": item.evidence_sha256,
                "data_json": _canonical_json(_evidence_read(item).model_dump(mode="json")),
            }
        )
    return (
        output.getvalue().encode("utf-8"),
        f"stonegate-provider-export-{case.id}.csv",
        "text/csv; charset=utf-8",
    )
