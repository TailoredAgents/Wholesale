import json
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from typing import Any, Literal, cast
from uuid import UUID

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    AuditEvent,
    ContractPackage,
    DispositionCase,
    DispositionPackageVersion,
    FieldInspection,
    FieldInspectionPhoto,
    Lead,
    Property,
    PropertyIntelligenceSnapshot,
    RepairEstimate,
    Transaction,
    TransactionDocument,
    TransactionDocumentFact,
    UnderwritingMarketAnalysis,
    UnderwritingVersion,
)
from app.schemas.dispositions import (
    DispositionEvidenceItemRead,
    DispositionPackageApprovalRequest,
    DispositionPackageReadinessRead,
    DispositionPackageVersionCreate,
    DispositionPackageVersionRead,
    DispositionPackageWorkspaceRead,
)

PACKAGE_POLICY_VERSION = "buyer_safe_v1"
PACKAGE_RENDERER_VERSION = "stonegate_pdf_v2"
ELIGIBLE_TRANSACTION_STATUSES = {"executed", "closing", "funded"}
PUBLIC_PACKAGE_KEYS = {
    "headline",
    "description",
    "highlights",
    "unknowns",
    "disclaimer",
    "package_reference",
    "property",
    "opportunity",
    "pricing",
    "valuation",
    "repairs",
    "inspection",
    "title",
    "due_diligence",
    "evidence_summary",
}
PUBLIC_PACKAGE_SCALAR_KEYS = {
    "headline",
    "description",
    "disclaimer",
    "package_reference",
}
PUBLIC_PACKAGE_LIST_KEYS = {"highlights", "unknowns", "due_diligence"}
PUBLIC_PACKAGE_NESTED_KEYS = {
    "property": {"address", "property_type", "county", "parcel_id"},
    "opportunity": {"strategy"},
    "pricing": {"buyer_asking_price_cents"},
    "valuation": {
        "arv_low_cents",
        "arv_high_cents",
        "estimated_value_cents",
        "source_label",
    },
    "repairs": {"total_cents", "scope_item_count", "source_label"},
    "inspection": {"overall_condition", "photo_count", "areas"},
    "title": {
        "contract_executed",
        "title_opened",
        "title_cleared",
        "title_document_count",
    },
    "evidence_summary": {
        "verified_fact_count",
        "seller_statement_count",
        "provider_signal_count",
        "stonegate_analysis_count",
        "unknown_count",
    },
}


def can_view_private(principal: Principal) -> bool:
    return PermissionKeys.VIEW_DISPOSITION_PRIVATE_ECONOMICS in principal.permission_keys


def can_approve(principal: Principal) -> bool:
    return PermissionKeys.APPROVE_DISPOSITION_PACKAGES in principal.permission_keys


def sanitize_public_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Return an explicit, recursively buyer-safe projection of any package snapshot."""
    source = snapshot if isinstance(snapshot, dict) else {}
    sanitized: dict[str, Any] = {}
    for key in PUBLIC_PACKAGE_SCALAR_KEYS:
        value = source.get(key)
        if key in source and (value is None or isinstance(value, (str, int, float, bool))):
            sanitized[key] = value
    for key in PUBLIC_PACKAGE_LIST_KEYS:
        value = source.get(key)
        if isinstance(value, list):
            sanitized[key] = [item for item in value if isinstance(item, str)]
    for key, allowed_keys in PUBLIC_PACKAGE_NESTED_KEYS.items():
        value = source.get(key)
        if not isinstance(value, dict):
            continue
        nested: dict[str, Any] = {}
        for nested_key in allowed_keys:
            nested_value = value.get(nested_key)
            if nested_value is None or isinstance(nested_value, (str, int, float, bool)):
                if nested_key in value:
                    nested[nested_key] = nested_value
            elif isinstance(nested_value, list):
                nested[nested_key] = [
                    item
                    for item in nested_value
                    if item is None or isinstance(item, (str, int, float, bool))
                ]
        sanitized[key] = nested
    if sanitized:
        return sanitized
    # Legacy snapshots predate the whitelist and can contain seller/private economics.
    return sanitize_public_snapshot(
        {
            "property": {
                "address": source.get("property_address") or "Address unavailable",
                "property_type": source.get("property_type"),
            },
            "opportunity": {"strategy": source.get("strategy") or "assignment"},
            "pricing": {"buyer_asking_price_cents": source.get("asking_price_cents")},
            "due_diligence": [
                "Buyer must independently verify property facts, access, title, "
                "and closing capacity."
            ],
        }
    )


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}.")


def _canonical_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


def _dict_section(payload: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = payload.get(key)
    return dict(value) if isinstance(value, dict) else None


def _address(property_record: Property | None) -> str:
    if property_record is None:
        return "Address unavailable"
    parts = [
        property_record.street_address.strip(),
        property_record.city.strip(),
        property_record.state.strip(),
        property_record.postal_code.strip(),
    ]
    return ", ".join(part for part in parts if part)


def _freshness(expires_at: datetime | None) -> str:
    if expires_at is None:
        return "unknown"
    comparable = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
    return "current" if comparable >= datetime.now(UTC) else "stale"


def _evidence(
    *,
    key: str,
    label: str,
    classification: str,
    value: Any,
    entity_type: str,
    entity_id: UUID | None,
    captured_at: datetime | None,
    expires_at: datetime | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "classification": classification,
        "value": value,
        "provenance": {
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id else None,
            "provider": provider,
        },
        "captured_at": captured_at.isoformat() if captured_at else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "freshness": _freshness(expires_at),
    }


def _check(
    key: str,
    label: str,
    status: str,
    detail: str,
    source_label: str,
    captured_at: datetime | None = None,
    remediation: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "detail": detail,
        "source_label": source_label,
        "captured_at": captured_at.isoformat() if captured_at else None,
        "remediation": remediation,
    }


def _readiness(
    *,
    blockers: list[str],
    warnings: list[str],
    unknowns: list[str],
    checks: list[dict[str, Any]],
    stale: bool = False,
) -> dict[str, Any]:
    status = "stale" if stale else "blocked" if blockers else "warnings" if warnings else "ready"
    return {
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "unknowns": unknowns,
        "checks": checks,
        "ready_count": sum(item["status"] == "ready" for item in checks),
        "warning_count": sum(item["status"] == "warning" for item in checks),
        "blocked_count": sum(item["status"] == "blocked" for item in checks),
        "unknown_count": len(unknowns),
    }


def assemble_package(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    *,
    asking_price_cents: int | None = None,
    minimum_acceptable_cents: int | None = None,
    desired_assignment_fee_cents: int | None = None,
) -> dict[str, Any]:
    """Assemble from saved Stonegate evidence only; this function never calls providers."""
    if case.organization_id != principal.organization_id:
        raise ValueError("Disposition case does not belong to this organization.")
    transaction = db.scalar(
        select(Transaction).where(
            Transaction.id == case.transaction_id,
            Transaction.organization_id == principal.organization_id,
        )
    )
    lead = db.scalar(
        select(Lead).where(
            Lead.id == case.lead_id,
            Lead.organization_id == principal.organization_id,
        )
    )
    property_record = db.scalar(
        select(Property).where(
            Property.id == case.property_id,
            Property.organization_id == principal.organization_id,
        )
    )
    if transaction is None or lead is None or property_record is None:
        raise ValueError("Disposition case references unavailable transaction or property records.")
    if (
        transaction.lead_id != case.lead_id
        or transaction.property_id != case.property_id
        or transaction.deal_id != case.deal_id
    ):
        raise ValueError("Disposition case transaction identity is inconsistent.")

    ask = asking_price_cents if asking_price_cents is not None else case.asking_price_cents
    floor = (
        minimum_acceptable_cents
        if minimum_acceptable_cents is not None
        else case.minimum_acceptable_cents
    )
    desired = (
        desired_assignment_fee_cents
        if desired_assignment_fee_cents is not None
        else case.desired_assignment_fee_cents
    )
    if desired is None:
        desired = transaction.assignment_fee_cents
    if desired is None:
        desired = max(ask - transaction.purchase_price_cents, 0)

    intelligence = db.scalar(
        select(PropertyIntelligenceSnapshot)
        .where(
            PropertyIntelligenceSnapshot.organization_id == principal.organization_id,
            PropertyIntelligenceSnapshot.property_id == case.property_id,
            PropertyIntelligenceSnapshot.is_current.is_(True),
        )
        .order_by(PropertyIntelligenceSnapshot.version_number.desc())
    )
    underwriting = db.scalar(
        select(UnderwritingVersion)
        .where(
            UnderwritingVersion.organization_id == principal.organization_id,
            UnderwritingVersion.lead_id == case.lead_id,
            UnderwritingVersion.property_id == case.property_id,
            UnderwritingVersion.status == "approved",
        )
        .order_by(UnderwritingVersion.version_number.desc())
    )
    market_analysis = db.scalar(
        select(UnderwritingMarketAnalysis)
        .where(
            UnderwritingMarketAnalysis.organization_id == principal.organization_id,
            UnderwritingMarketAnalysis.lead_id == case.lead_id,
            UnderwritingMarketAnalysis.property_id == case.property_id,
        )
        .order_by(UnderwritingMarketAnalysis.created_at.desc())
    )
    repair = db.scalar(
        select(RepairEstimate)
        .where(
            RepairEstimate.organization_id == principal.organization_id,
            RepairEstimate.lead_id == case.lead_id,
            RepairEstimate.property_id == case.property_id,
        )
        .order_by(RepairEstimate.created_at.desc())
    )
    inspection = db.scalar(
        select(FieldInspection)
        .where(
            FieldInspection.organization_id == principal.organization_id,
            FieldInspection.lead_id == case.lead_id,
            FieldInspection.property_id == case.property_id,
            FieldInspection.status.in_(("submitted", "reviewed")),
        )
        .order_by(FieldInspection.created_at.desc())
    )
    photos = (
        list(
            db.scalars(
                select(FieldInspectionPhoto)
                .where(
                    FieldInspectionPhoto.organization_id == principal.organization_id,
                    FieldInspectionPhoto.inspection_id == inspection.id,
                )
                .order_by(FieldInspectionPhoto.created_at)
            ).all()
        )
        if inspection
        else []
    )
    documents = list(
        db.scalars(
            select(TransactionDocument)
            .where(
                TransactionDocument.organization_id == principal.organization_id,
                TransactionDocument.transaction_id == transaction.id,
                TransactionDocument.deleted_at.is_(None),
            )
            .order_by(TransactionDocument.occurred_at)
        ).all()
    )
    document_ids = [item.id for item in documents]
    facts = (
        list(
            db.scalars(
                select(TransactionDocumentFact).where(
                    TransactionDocumentFact.organization_id == principal.organization_id,
                    TransactionDocumentFact.transaction_id == transaction.id,
                    TransactionDocumentFact.document_id.in_(document_ids),
                    TransactionDocumentFact.status.in_(("confirmed", "approved")),
                )
            ).all()
        )
        if document_ids
        else []
    )
    executed_contract = db.scalar(
        select(ContractPackage)
        .where(
            ContractPackage.organization_id == principal.organization_id,
            ContractPackage.transaction_id == transaction.id,
            ContractPackage.status == "executed",
        )
        .order_by(ContractPackage.version_number.desc())
    )

    blockers: list[str] = []
    warnings: list[str] = []
    unknowns: list[str] = []
    checks: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    transaction_ready = transaction.status in ELIGIBLE_TRANSACTION_STATUSES
    if not transaction_ready:
        blockers.append("The transaction is not in an executed disposition-eligible state.")
    checks.append(
        _check(
            "transaction_state",
            "Executed transaction",
            "ready" if transaction_ready else "blocked",
            f"Transaction status is {transaction.status}.",
            "Stonegate transaction",
            transaction.updated_at,
            None
            if transaction_ready
            else {
                "label": "Open transaction",
                "href": f"/os/deals?deal={transaction.deal_id}&tab=contract",
            },
        )
    )
    evidence.append(
        _evidence(
            key="transaction_state",
            label="Transaction status",
            classification="verified_fact",
            value=transaction.status,
            entity_type="transaction",
            entity_id=transaction.id,
            captured_at=transaction.updated_at,
        )
    )

    address_values = (
        property_record.street_address,
        property_record.city,
        property_record.state,
        property_record.postal_code,
    )
    address_ready = all(
        value and value.strip().lower() not in {"unknown", "n/a", "none"}
        for value in address_values
    )
    if not address_ready:
        blockers.append("The property address is incomplete or unusable.")
    elif property_record.address_validation_status not in {
        "validated",
        "provider_confirmed",
        "confirmed",
        "verified",
    }:
        warnings.append("The address has not been provider-confirmed.")
    checks.append(
        _check(
            "property_identity",
            "Property identity",
            "blocked" if not address_ready else "ready" if not warnings else "warning",
            _address(property_record),
            "Stonegate property record",
            property_record.address_validated_at or property_record.updated_at,
            None
            if address_ready
            else {"label": "Review property", "href": f"/os/leads/{case.lead_id}?tab=property"},
        )
    )
    evidence.append(
        _evidence(
            key="property_address",
            label="Property address",
            classification=(
                "verified_fact"
                if property_record.address_validation_status
                in {"validated", "provider_confirmed", "confirmed", "verified"}
                else "seller_statement"
            ),
            value=_address(property_record),
            entity_type="property",
            entity_id=property_record.id,
            captured_at=property_record.address_validated_at or property_record.updated_at,
            provider=property_record.address_validation_provider,
        )
    )

    assignment_floor_below_basis = (
        case.strategy == "assignment" and floor < transaction.purchase_price_cents
    )
    economics_valid = ask > 0 and floor > 0 and floor <= ask and desired >= 0
    if transaction.purchase_price_cents <= 0:
        economics_valid = False
    if case.strategy == "assignment":
        if assignment_floor_below_basis:
            economics_valid = False
        if transaction.purchase_price_cents + desired > ask:
            economics_valid = False
    if not economics_valid:
        blockers.append(
            "Minimum acceptable price cannot be below the contract purchase price "
            "for an assignment."
            if assignment_floor_below_basis
            else "Disposition pricing or internal economics are inconsistent."
        )
    checks.append(
        _check(
            "economics",
            "Disposition economics",
            "ready" if economics_valid else "blocked",
            "Buyer ask and internal release economics passed validation."
            if economics_valid
            else "Review ask, contract basis, floor, and desired assignment fee.",
            "Stonegate disposition case",
            case.updated_at,
            None
            if economics_valid
            else {
                "label": "Review package economics",
                "href": (f"/os/deals?deal={case.deal_id}&tab=disposition&dispositionTab=package"),
            },
        )
    )

    critical_conflicts = []
    if intelligence:
        for conflict in intelligence.conflicts or []:
            if not isinstance(conflict, dict):
                continue
            severity = str(conflict.get("severity") or "").lower()
            field = str(conflict.get("field") or conflict.get("key") or "").lower()
            if severity == "critical" or field in {
                "address",
                "property_identity",
                "parcel_identity",
            }:
                critical_conflicts.append(conflict)
        evidence.append(
            _evidence(
                key="property_intelligence",
                label="Saved property intelligence",
                classification="provider_signal",
                value={
                    "status": intelligence.status,
                    "confidence_score": intelligence.confidence_score,
                    "comparable_count": len(intelligence.comparables or []),
                },
                entity_type="property_intelligence_snapshot",
                entity_id=intelligence.id,
                captured_at=intelligence.captured_at,
                expires_at=intelligence.expires_at,
            )
        )
        if _freshness(intelligence.expires_at) == "stale":
            warnings.append("Saved property intelligence is stale.")
        if critical_conflicts:
            blockers.append("Property intelligence contains a critical identity conflict.")
        checks.append(
            _check(
                "property_intelligence",
                "Property intelligence",
                "blocked"
                if critical_conflicts
                else "warning"
                if _freshness(intelligence.expires_at) == "stale"
                else "ready",
                (
                    f"Saved snapshot v{intelligence.version_number}; "
                    f"{len(intelligence.comparables or [])} comparable records."
                ),
                "Saved property intelligence",
                intelligence.captured_at,
                {
                    "label": "Review property research",
                    "href": f"/os/leads/{case.lead_id}?tab=property",
                },
            )
        )
    else:
        warning = "Property intelligence has not been saved."
        warnings.append(warning)
        unknowns.append("Property intelligence")
        checks.append(
            _check(
                "property_intelligence",
                "Property intelligence",
                "warning",
                warning,
                "Stonegate property research",
                remediation={
                    "label": "Research property",
                    "href": f"/os/leads/{case.lead_id}?tab=property",
                },
            )
        )
        evidence.append(
            _evidence(
                key="property_intelligence",
                label="Saved property intelligence",
                classification="unknown",
                value=None,
                entity_type="property",
                entity_id=case.property_id,
                captured_at=None,
            )
        )

    valuation_values = None
    if underwriting:
        valuation_values = {
            "arv_low_cents": underwriting.arv_low_cents,
            "arv_high_cents": underwriting.arv_high_cents,
            "source_label": "Stonegate approved underwriting",
        }
        evidence.append(
            _evidence(
                key="valuation",
                label="Stonegate valuation",
                classification="stonegate_analysis",
                value=valuation_values,
                entity_type="underwriting_version",
                entity_id=underwriting.id,
                captured_at=underwriting.updated_at,
            )
        )
        checks.append(
            _check(
                "valuation",
                "Valuation evidence",
                "ready",
                f"Approved underwriting v{underwriting.version_number} is saved.",
                "Stonegate underwriting",
                underwriting.updated_at,
                {"label": "Open valuation", "href": f"/os/leads/{case.lead_id}?tab=valuation"},
            )
        )
    elif market_analysis:
        valuation_values = {
            "arv_low_cents": market_analysis.arv_low_cents,
            "arv_high_cents": market_analysis.arv_high_cents,
            "estimated_value_cents": market_analysis.estimated_value_cents,
            "source_label": "Stonegate analysis of provider evidence",
        }
        warnings.append("Valuation evidence has not been approved by underwriting.")
        evidence.append(
            _evidence(
                key="valuation",
                label="Valuation signal",
                classification="stonegate_analysis",
                value=valuation_values,
                entity_type="underwriting_market_analysis",
                entity_id=market_analysis.id,
                captured_at=market_analysis.created_at,
                provider=market_analysis.provider,
            )
        )
        checks.append(
            _check(
                "valuation",
                "Valuation evidence",
                "warning",
                "A saved analysis exists but is not approved underwriting.",
                "Stonegate underwriting",
                market_analysis.created_at,
                {"label": "Review valuation", "href": f"/os/leads/{case.lead_id}?tab=valuation"},
            )
        )
    else:
        warnings.append("Valuation evidence is not available.")
        unknowns.append("Valuation")
        evidence.append(
            _evidence(
                key="valuation",
                label="Valuation evidence",
                classification="unknown",
                value=None,
                entity_type="property",
                entity_id=case.property_id,
                captured_at=None,
            )
        )
        checks.append(
            _check(
                "valuation",
                "Valuation evidence",
                "warning",
                "No saved valuation evidence is available.",
                "Stonegate underwriting",
                remediation={
                    "label": "Run valuation",
                    "href": f"/os/leads/{case.lead_id}?tab=valuation",
                },
            )
        )

    repair_values = None
    if repair:
        repair_values = {
            "total_cents": repair.total_cents,
            "scope_item_count": len(repair.scope_items or []),
            "source_label": "Stonegate repair estimate",
        }
        evidence.append(
            _evidence(
                key="repairs",
                label="Repair estimate",
                classification="stonegate_analysis",
                value=repair_values,
                entity_type="repair_estimate",
                entity_id=repair.id,
                captured_at=repair.estimate_date,
            )
        )
        checks.append(
            _check(
                "repairs",
                "Repair evidence",
                "ready",
                f"Saved repair estimate with {len(repair.scope_items or [])} scope items.",
                "Stonegate repair estimate",
                repair.estimate_date,
            )
        )
    else:
        warnings.append("Repair evidence is not available.")
        unknowns.append("Repairs")
        evidence.append(
            _evidence(
                key="repairs",
                label="Repair evidence",
                classification="unknown",
                value=None,
                entity_type="property",
                entity_id=case.property_id,
                captured_at=None,
            )
        )
        checks.append(
            _check(
                "repairs",
                "Repair evidence",
                "warning",
                "No saved repair estimate is available.",
                "Stonegate repair estimate",
                remediation={
                    "label": "Review repairs",
                    "href": f"/os/leads/{case.lead_id}?tab=valuation",
                },
            )
        )

    inspection_values = None
    if inspection:
        inspection_values = {
            "overall_condition": inspection.overall_condition,
            "photo_count": len(photos),
            "areas": sorted({photo.area for photo in photos}),
        }
        inspection_reviewed = inspection.status == "reviewed" and inspection.reviewed_at is not None
        inspection_review_label = (
            " and human review" if inspection_reviewed else "; human review is pending"
        )
        evidence.append(
            _evidence(
                key="inspection",
                label="Field inspection",
                classification="verified_fact" if inspection_reviewed else "stonegate_analysis",
                value=inspection_values,
                entity_type="field_inspection",
                entity_id=inspection.id,
                captured_at=inspection.reviewed_at or inspection.submitted_at,
            )
        )
        checks.append(
            _check(
                "inspection",
                "Inspection and photos",
                "ready" if inspection_reviewed and photos else "warning",
                (f"Inspection saved with {len(photos)} photo(s){inspection_review_label}."),
                "Stonegate field inspection",
                inspection.reviewed_at or inspection.submitted_at,
            )
        )
        if not inspection_reviewed:
            warnings.append("The field inspection has not completed human review.")
        if not photos:
            warnings.append("The field inspection has no saved photos.")
            unknowns.append("Property photos")
    else:
        warnings.append("Inspection and property photos are not available.")
        unknowns.extend(["Field inspection", "Property photos"])
        evidence.append(
            _evidence(
                key="inspection",
                label="Field inspection",
                classification="unknown",
                value=None,
                entity_type="property",
                entity_id=case.property_id,
                captured_at=None,
            )
        )
        checks.append(
            _check(
                "inspection",
                "Inspection and photos",
                "warning",
                "No completed field inspection is saved.",
                "Stonegate field inspection",
                remediation={
                    "label": "Open appointments",
                    "href": f"/os/leads/{case.lead_id}?tab=appointments",
                },
            )
        )

    title_documents = [item for item in documents if "title" in item.document_type.lower()]
    contract_ready = bool(transaction.contract_executed_at or executed_contract)
    title_values = {
        "contract_executed": contract_ready,
        "title_opened": transaction.title_opened_at is not None,
        "title_cleared": transaction.title_cleared_at is not None,
        "title_document_count": len(title_documents),
    }
    if not contract_ready:
        warnings.append("An executed contract document has not been confirmed in saved evidence.")
        unknowns.append("Executed contract document")
    if not title_documents and transaction.title_cleared_at is None:
        warnings.append("Title evidence is not available.")
        unknowns.append("Title status")
    evidence.append(
        _evidence(
            key="title",
            label="Contract and title status",
            classification="verified_fact" if contract_ready else "unknown",
            value=title_values,
            entity_type="transaction",
            entity_id=transaction.id,
            captured_at=transaction.updated_at,
        )
    )
    checks.append(
        _check(
            "title",
            "Contract and title evidence",
            "ready"
            if contract_ready and (title_documents or transaction.title_cleared_at)
            else "warning",
            (
                f"Executed contract: {'yes' if contract_ready else 'unconfirmed'}; "
                f"title documents: {len(title_documents)}."
            ),
            "Stonegate transaction documents",
            transaction.updated_at,
            {
                "label": "Review transaction files",
                "href": f"/os/deals?deal={transaction.deal_id}&tab=documents",
            },
        )
    )

    private_economics = {
        "contract_purchase_price_cents": transaction.purchase_price_cents,
        "minimum_acceptable_cents": floor,
        "desired_assignment_fee_cents": desired,
        "buyer_asking_price_cents": ask,
        "gross_spread_at_ask_cents": ask - transaction.purchase_price_cents,
    }
    unknowns = list(dict.fromkeys(unknowns))
    highlights = [
        item
        for item in (
            f"{property_record.property_type} property" if property_record.property_type else None,
            f"Buyer asking price ${ask / 100:,.0f}",
            "Stonegate valuation evidence saved" if valuation_values else None,
            f"{len(photos)} inspection photo(s) saved" if photos else None,
        )
        if item
    ]
    public_snapshot = {
        "headline": f"Investment opportunity at {_address(property_record)}",
        "description": (
            "A Stonegate evidence-backed property opportunity prepared for qualified buyers."
        ),
        "highlights": highlights,
        "unknowns": unknowns,
        "disclaimer": (
            "Buyer must independently verify every property, title, repair, financing, "
            "access, and closing fact before relying on this summary."
        ),
        "package_reference": str(case.id),
        "property": {
            "address": _address(property_record),
            "property_type": property_record.property_type,
            "county": property_record.county,
            "parcel_id": property_record.parcel_id,
        },
        "opportunity": {"strategy": case.strategy},
        "pricing": {"buyer_asking_price_cents": ask},
        "valuation": valuation_values,
        "repairs": repair_values,
        "inspection": inspection_values,
        "title": title_values,
        "due_diligence": [
            "Buyer must independently verify property facts, access, title, financing, "
            "and closing capacity.",
            "Provider data and Stonegate analysis are research signals, not warranties.",
        ],
        "evidence_summary": {
            "verified_fact_count": sum(
                item["classification"] == "verified_fact" for item in evidence
            ),
            "seller_statement_count": sum(
                item["classification"] == "seller_statement" for item in evidence
            ),
            "provider_signal_count": sum(
                item["classification"] == "provider_signal" for item in evidence
            ),
            "stonegate_analysis_count": sum(
                item["classification"] == "stonegate_analysis" for item in evidence
            ),
            "unknown_count": sum(item["classification"] == "unknown" for item in evidence),
        },
    }
    readiness = _readiness(blockers=blockers, warnings=warnings, unknowns=unknowns, checks=checks)
    property_label = _address(property_record)
    email_summary = (
        f"Investment opportunity: {property_label}. Buyer asking price: ${ask / 100:,.0f}. "
        "Review the attached evidence-backed package and independently verify all facts."
    )
    sms_summary = (
        f"Stonegate opportunity: {property_label} at ${ask / 100:,.0f}. "
        "Reply for the evidence-backed package. Buyer due diligence required."
    )[:1000]
    material_sources = {
        "case": {"id": case.id, "strategy": case.strategy},
        "transaction": {
            "id": transaction.id,
            "status": transaction.status,
            "contract_type": transaction.contract_type,
            "purchase_price_cents": transaction.purchase_price_cents,
            "assignment_fee_cents": transaction.assignment_fee_cents,
            "closing_date": transaction.closing_date,
            "contract_executed_at": transaction.contract_executed_at,
            "title_opened_at": transaction.title_opened_at,
            "title_cleared_at": transaction.title_cleared_at,
        },
        "property": {
            "id": property_record.id,
            "street_address": property_record.street_address,
            "city": property_record.city,
            "state": property_record.state,
            "postal_code": property_record.postal_code,
            "county": property_record.county,
            "property_type": property_record.property_type,
            "parcel_id": property_record.parcel_id,
            "address_validation_status": property_record.address_validation_status,
            "address_validation_provider": property_record.address_validation_provider,
            "address_validated_at": property_record.address_validated_at,
        },
        "economics": private_economics,
        "intelligence": {
            "id": intelligence.id if intelligence else None,
            "version": intelligence.version_number if intelligence else None,
            "captured_at": intelligence.captured_at if intelligence else None,
            "expires_at": intelligence.expires_at if intelligence else None,
            "facts": intelligence.facts if intelligence else None,
            "valuation": intelligence.valuation if intelligence else None,
            "comparables": intelligence.comparables if intelligence else None,
            "conflicts": intelligence.conflicts if intelligence else None,
            "media": intelligence.media if intelligence else None,
        },
        "underwriting": {
            "id": underwriting.id if underwriting else None,
            "version": underwriting.version_number if underwriting else None,
            "status": underwriting.status if underwriting else None,
            "arv_low": underwriting.arv_low_cents if underwriting else None,
            "arv_high": underwriting.arv_high_cents if underwriting else None,
        },
        "market_analysis": (
            {
                "id": market_analysis.id,
                "created_at": market_analysis.created_at,
                "provider": market_analysis.provider,
                "estimated_value_cents": market_analysis.estimated_value_cents,
                "arv_low_cents": market_analysis.arv_low_cents,
                "arv_high_cents": market_analysis.arv_high_cents,
                "selected_comps": market_analysis.selected_comps,
            }
            if market_analysis and underwriting is None
            else None
        ),
        "repair": {
            "id": repair.id,
            "total": repair.total_cents,
            "scope": repair.scope_items,
            "estimate_date": repair.estimate_date,
        }
        if repair
        else None,
        "inspection": {
            "id": inspection.id,
            "status": inspection.status,
            "overall_condition": inspection.overall_condition,
            "submitted_at": inspection.submitted_at,
            "reviewed_at": inspection.reviewed_at,
            "photos": [
                {
                    "id": item.id,
                    "sha256": item.sha256,
                    "area": item.area,
                    "caption": item.caption,
                    "captured_at": item.captured_at,
                }
                for item in photos
            ],
        }
        if inspection
        else None,
        "documents": [
            {
                "id": item.id,
                "type": item.document_type,
                "status": item.status,
                "sha256": item.sha256,
                "occurred_at": item.occurred_at,
            }
            for item in documents
        ],
        "document_facts": [
            {
                "id": item.id,
                "field": item.field_key,
                "value": item.value_text,
                "status": item.status,
                "reviewed_at": item.reviewed_at,
            }
            for item in facts
        ],
        "executed_contract": (
            {
                "id": executed_contract.id,
                "version": executed_contract.version_number,
                "status": executed_contract.status,
                "executed_at": executed_contract.executed_at,
            }
            if executed_contract
            else None
        ),
    }
    return {
        "public_snapshot": sanitize_public_snapshot(public_snapshot),
        "private_economics": private_economics,
        "evidence_manifest": evidence,
        "readiness": readiness,
        "source_fingerprint": _canonical_hash(material_sources),
        "email_summary": email_summary,
        "sms_summary": sms_summary,
    }


def _latest_versions(
    db: Session, principal: Principal, case_id: UUID
) -> list[DispositionPackageVersion]:
    return list(
        db.scalars(
            select(DispositionPackageVersion)
            .where(
                DispositionPackageVersion.organization_id == principal.organization_id,
                DispositionPackageVersion.disposition_case_id == case_id,
            )
            .order_by(DispositionPackageVersion.version_number.desc())
        ).all()
    )


def _version_matches_current_sources(
    version: DispositionPackageVersion,
    *,
    current_fingerprint: str,
) -> bool:
    return (
        version.source_fingerprint == current_fingerprint
        and version.policy_version == PACKAGE_POLICY_VERSION
        and version.renderer_version == PACKAGE_RENDERER_VERSION
    )


def _version_read(
    principal: Principal,
    version: DispositionPackageVersion,
    *,
    current_fingerprint: str,
    latest_version_id: UUID | None,
) -> DispositionPackageVersionRead:
    return DispositionPackageVersionRead(
        id=version.id,
        disposition_case_id=version.disposition_case_id,
        version_number=version.version_number,
        lock_version=version.lock_version,
        status=cast(
            Literal["draft", "approved", "superseded", "rejected"],
            version.status,
        ),
        policy_version=version.policy_version,
        renderer_version=version.renderer_version,
        public_snapshot=sanitize_public_snapshot(version.public_snapshot),
        private_economics_snapshot=(
            version.private_economics_snapshot if can_view_private(principal) else None
        ),
        evidence_manifest=[
            DispositionEvidenceItemRead.model_validate(item) for item in version.evidence_manifest
        ],
        readiness=DispositionPackageReadinessRead.model_validate(version.readiness_snapshot),
        source_fingerprint=version.source_fingerprint,
        email_summary=version.email_summary,
        sms_summary=version.sms_summary,
        pdf_file_name=version.pdf_file_name,
        pdf_size=version.pdf_size,
        pdf_sha256=version.pdf_sha256,
        created_by_user_id=version.created_by_user_id,
        approved_by_user_id=version.approved_by_user_id,
        approval_reason=version.approval_reason if can_view_private(principal) else None,
        approved_at=version.approved_at,
        created_at=version.created_at,
        is_current=(
            version.id == latest_version_id
            and _version_matches_current_sources(
                version,
                current_fingerprint=current_fingerprint,
            )
        ),
    )


def read_workspace(
    db: Session, principal: Principal, case_id: UUID
) -> DispositionPackageWorkspaceRead | None:
    case = db.scalar(
        select(DispositionCase).where(
            DispositionCase.id == case_id,
            DispositionCase.organization_id == principal.organization_id,
        )
    )
    if case is None:
        return None
    current = assemble_package(db, principal, case)
    versions = _latest_versions(db, principal, case.id)
    latest = versions[0] if versions else None
    approved = next((item for item in versions if item.status == "approved"), None)
    approved_is_current = bool(
        approved
        and latest
        and approved.id == latest.id
        and case.package_status == "approved"
        and _version_matches_current_sources(
            approved,
            current_fingerprint=current["source_fingerprint"],
        )
    )
    current_readiness = current["readiness"]
    if approved is not None and not approved_is_current:
        stale_warning = (
            "The approved buyer package is stale because a newer draft, material evidence, "
            "or the package policy/renderer changed."
        )
        current_readiness = _readiness(
            blockers=list(current_readiness.get("blockers") or []),
            warnings=list(
                dict.fromkeys([*(current_readiness.get("warnings") or []), stale_warning])
            ),
            unknowns=list(current_readiness.get("unknowns") or []),
            checks=[
                *(current_readiness.get("checks") or []),
                _check(
                    "approved_package_freshness",
                    "Approved package freshness",
                    "warning",
                    stale_warning,
                    "Stonegate immutable package",
                    approved.approved_at,
                    {
                        "label": "Build a current package",
                        "href": (
                            f"/os/deals?deal={case.deal_id}&tab=disposition&dispositionTab=package"
                        ),
                    },
                ),
            ],
            stale=True,
        )
    reads = [
        _version_read(
            principal,
            item,
            current_fingerprint=current["source_fingerprint"],
            latest_version_id=latest.id if latest else None,
        )
        for item in versions
    ]
    return DispositionPackageWorkspaceRead(
        case_id=case.id,
        can_view_internal_economics=can_view_private(principal),
        can_approve=can_approve(principal),
        current_source_fingerprint=current["source_fingerprint"],
        current_readiness=current_readiness,
        public_preview=current["public_snapshot"],
        private_economics=current["private_economics"] if can_view_private(principal) else None,
        evidence_manifest=current["evidence_manifest"],
        email_summary=current["email_summary"],
        sms_summary=current["sms_summary"],
        latest_version=reads[0] if reads else None,
        approved_version=(
            _version_read(
                principal,
                approved,
                current_fingerprint=current["source_fingerprint"],
                latest_version_id=latest.id if latest else None,
            )
            if approved
            else None
        ),
        approved_package_is_current=approved_is_current,
        versions=reads,
    )


def read_versions(
    db: Session, principal: Principal, case_id: UUID
) -> list[DispositionPackageVersionRead] | None:
    workspace = read_workspace(db, principal, case_id)
    return workspace.versions if workspace else None


def build_version(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: DispositionPackageVersionCreate,
    *,
    commit: bool = True,
) -> DispositionPackageVersionRead | None:
    from app.services.dispositions import scoped_case_for_mutation

    case = scoped_case_for_mutation(
        db,
        principal,
        case_id,
        allowed_statuses={"package_prep", "buyer_matching", "marketed"},
    )
    if case is None:
        return None
    has_economics_override = any(
        value is not None
        for value in (
            payload.asking_price_cents,
            payload.minimum_acceptable_cents,
            payload.desired_assignment_fee_cents,
        )
    )
    if has_economics_override and not can_view_private(principal):
        raise ValueError(
            "Private disposition economics permission is required to change package pricing."
        )
    latest_number = (
        db.scalar(
            select(func.max(DispositionPackageVersion.version_number)).where(
                DispositionPackageVersion.organization_id == principal.organization_id,
                DispositionPackageVersion.disposition_case_id == case.id,
            )
        )
        or 0
    )
    if latest_number != payload.expected_latest_version:
        raise ValueError(
            f"Package version changed. Expected latest version "
            f"{payload.expected_latest_version}; current latest is {latest_number}."
        )
    assembled = assemble_package(
        db,
        principal,
        case,
        asking_price_cents=payload.asking_price_cents,
        minimum_acceptable_cents=payload.minimum_acceptable_cents,
        desired_assignment_fee_cents=payload.desired_assignment_fee_cents,
    )
    if case.strategy == "assignment" and int(
        assembled["private_economics"]["minimum_acceptable_cents"]
    ) < int(assembled["private_economics"]["contract_purchase_price_cents"]):
        raise ValueError(
            "Minimum acceptable price cannot be below the contract purchase price "
            "for an assignment."
        )
    for prior_draft in db.scalars(
        select(DispositionPackageVersion).where(
            DispositionPackageVersion.organization_id == principal.organization_id,
            DispositionPackageVersion.disposition_case_id == case.id,
            DispositionPackageVersion.status == "draft",
        )
    ).all():
        prior_draft.status = "superseded"
        prior_draft.lock_version += 1
    version = DispositionPackageVersion(
        organization_id=principal.organization_id,
        disposition_case_id=case.id,
        created_by_user_id=principal.user_id,
        approved_by_user_id=None,
        version_number=latest_number + 1,
        lock_version=1,
        status="draft",
        policy_version=PACKAGE_POLICY_VERSION,
        renderer_version=PACKAGE_RENDERER_VERSION,
        public_snapshot=assembled["public_snapshot"],
        private_economics_snapshot=assembled["private_economics"],
        evidence_manifest=assembled["evidence_manifest"],
        readiness_snapshot=assembled["readiness"],
        source_fingerprint=assembled["source_fingerprint"],
        email_summary=assembled["email_summary"],
        sms_summary=assembled["sms_summary"],
        approval_reason=None,
        approved_at=None,
        pdf_file_name=None,
        pdf_content_type=None,
        pdf_size=None,
        pdf_sha256=None,
        pdf_data=None,
    )
    db.add(version)
    case.asking_price_cents = int(assembled["private_economics"]["buyer_asking_price_cents"])
    case.minimum_acceptable_cents = int(assembled["private_economics"]["minimum_acceptable_cents"])
    case.desired_assignment_fee_cents = int(
        assembled["private_economics"]["desired_assignment_fee_cents"]
    )
    case.package_status = "draft"
    case.package_snapshot = sanitize_public_snapshot(assembled["public_snapshot"])
    # DS5 replaces the mutable legacy package state with immutable versions.
    # A legacy case may already be marked marketed even though it has no current
    # package artifact; rebuilding it must reopen buyer matching so the approved
    # version can be matched and prepared through the current workflow.
    if case.status in {"package_prep", "marketed"}:
        case.status = "buyer_matching"
    db.flush()
    _audit(
        db,
        principal,
        "disposition.package_version_create",
        version.id,
        {"case_id": str(case.id), "version_number": version.version_number},
        "Immutable disposition package draft created",
    )
    if commit:
        db.commit()
        db.refresh(version)
    return _version_read(
        principal,
        version,
        current_fingerprint=assembled["source_fingerprint"],
        latest_version_id=version.id,
    )


def _render_pdf(snapshot: dict[str, Any], approved_at: datetime, case_id: UUID) -> bytes:
    safe = sanitize_public_snapshot(snapshot)
    prop = _dict_section(safe, "property") or {}
    pricing = _dict_section(safe, "pricing") or {}
    opportunity = _dict_section(safe, "opportunity") or {}
    valuation = _dict_section(safe, "valuation")
    repairs = _dict_section(safe, "repairs")
    title = _dict_section(safe, "title") or {}
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=letter)
    pdf.setTitle("Stonegate Investor Deal Package")
    green = (0.15, 0.37, 0.26)
    ink = (0.09, 0.11, 0.12)
    muted = (0.40, 0.44, 0.45)
    pdf.setFillColorRGB(*green)
    pdf.rect(0, 680, letter[0], 112, fill=1, stroke=0)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(48, 752, "STONEGATE HOME BUYERS")
    pdf.setFont("Helvetica-Bold", 23)
    pdf.drawString(48, 716, "Investor Deal Package")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(48, 696, f"Approved {approved_at:%B %d, %Y}")
    pdf.setFillColorRGB(*ink)
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(48, 640, str(prop.get("address") or "Address unavailable")[:78])
    pdf.setFillColorRGB(*muted)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(48, 620, "Evidence-backed opportunity summary for qualified buyers")
    ask = pricing.get("buyer_asking_price_cents")
    rows = [
        ("PROPERTY TYPE", prop.get("property_type") or "Not provided"),
        ("TRANSACTION", str(opportunity.get("strategy") or "assignment").replace("_", " ").title()),
        ("INVESTOR ASKING PRICE", f"${ask / 100:,.0f}" if isinstance(ask, int) else "Not provided"),
        (
            "STONEGATE VALUATION",
            f"${valuation.get('arv_low_cents', 0) / 100:,.0f} - "
            f"${valuation.get('arv_high_cents', 0) / 100:,.0f}"
            if valuation
            and valuation.get("arv_low_cents") is not None
            and valuation.get("arv_high_cents") is not None
            else "Not established",
        ),
        (
            "REPAIR ESTIMATE",
            f"${repairs.get('total_cents', 0) / 100:,.0f}"
            if repairs and repairs.get("total_cents") is not None
            else "Not established",
        ),
        ("TITLE CLEARED", "Yes" if title.get("title_cleared") else "Not confirmed"),
    ]
    y = 575
    for label, value in rows:
        pdf.setFillColorRGB(*muted)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(48, y, label)
        pdf.setFillColorRGB(*ink)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(238, y - 1, str(value)[:55])
        pdf.setStrokeColorRGB(0.93, 0.91, 0.87)
        pdf.line(48, y - 17, 564, y - 17)
        y -= 48
    pdf.setFillColorRGB(0.96, 0.97, 0.95)
    pdf.roundRect(48, 190, 516, 78, 4, fill=1, stroke=0)
    pdf.setFillColorRGB(*green)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(64, 242, "BUYER DUE DILIGENCE")
    pdf.setFillColorRGB(*ink)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(
        64,
        220,
        "Independently verify property facts, access, title, financing, and closing capacity.",
    )
    pdf.drawString(
        64, 204, "Provider data and Stonegate analysis are research signals, not warranties."
    )
    pdf.setFillColorRGB(*muted)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(48, 72, "CONFIDENTIAL - FOR QUALIFIED REAL ESTATE INVESTORS")
    pdf.drawRightString(564, 72, f"Case {str(case_id)[:8].upper()}")
    pdf.save()
    return stream.getvalue()


def approve_version(
    db: Session,
    principal: Principal,
    case_id: UUID,
    version_id: UUID,
    payload: DispositionPackageApprovalRequest,
) -> DispositionPackageVersionRead | None:
    if not can_approve(principal):
        raise ValueError("Disposition package approval permission is required.")
    from app.services.dispositions import scoped_case_for_mutation

    case = scoped_case_for_mutation(
        db, principal, case_id, allowed_statuses={"package_prep", "buyer_matching", "marketed"}
    )
    if case is None:
        return None
    version = db.scalar(
        select(DispositionPackageVersion)
        .where(
            DispositionPackageVersion.id == version_id,
            DispositionPackageVersion.organization_id == principal.organization_id,
            DispositionPackageVersion.disposition_case_id == case.id,
        )
        .with_for_update()
    )
    if version is None:
        return None
    latest = db.scalar(
        select(DispositionPackageVersion)
        .where(
            DispositionPackageVersion.organization_id == principal.organization_id,
            DispositionPackageVersion.disposition_case_id == case.id,
        )
        .order_by(DispositionPackageVersion.version_number.desc())
        .limit(1)
        .with_for_update()
    )
    if latest is None or latest.id != version.id:
        raise ValueError("Only the latest package version can be approved.")
    if version.status != "draft":
        raise ValueError("Only a draft package version can be approved.")
    if (
        version.policy_version != PACKAGE_POLICY_VERSION
        or version.renderer_version != PACKAGE_RENDERER_VERSION
    ):
        raise ValueError(
            "The package policy or renderer changed. Build a new package version before approval."
        )
    if version.lock_version != payload.expected_version:
        raise ValueError(
            f"Package changed. Expected lock version {payload.expected_version}; "
            f"current version is {version.lock_version}."
        )
    economics = version.private_economics_snapshot
    current = assemble_package(
        db,
        principal,
        case,
        asking_price_cents=int(economics["buyer_asking_price_cents"]),
        minimum_acceptable_cents=int(economics["minimum_acceptable_cents"]),
        desired_assignment_fee_cents=int(economics["desired_assignment_fee_cents"]),
    )
    if current["source_fingerprint"] != version.source_fingerprint:
        raise ValueError(
            "The package draft is stale because material deal evidence changed. "
            "Build a new package version."
        )
    blockers = list(current["readiness"].get("blockers") or [])
    if blockers:
        raise ValueError("Package approval is blocked: " + "; ".join(blockers))
    now = datetime.now(UTC)
    pdf_data = _render_pdf(version.public_snapshot, now, case.id)
    for prior in db.scalars(
        select(DispositionPackageVersion).where(
            DispositionPackageVersion.organization_id == principal.organization_id,
            DispositionPackageVersion.disposition_case_id == case.id,
            DispositionPackageVersion.status == "approved",
            DispositionPackageVersion.id != version.id,
        )
    ).all():
        prior.status = "superseded"
        prior.lock_version += 1
    version.status = "approved"
    version.approved_by_user_id = principal.user_id
    version.approved_at = now
    version.approval_reason = payload.reason
    version.pdf_file_name = f"stonegate-deal-package-{case.id}-v{version.version_number}.pdf"
    version.pdf_content_type = "application/pdf"
    version.pdf_size = len(pdf_data)
    version.pdf_sha256 = sha256(pdf_data).hexdigest()
    version.pdf_data = pdf_data
    version.lock_version += 1
    case.asking_price_cents = int(economics["buyer_asking_price_cents"])
    case.minimum_acceptable_cents = int(economics["minimum_acceptable_cents"])
    case.desired_assignment_fee_cents = int(economics["desired_assignment_fee_cents"])
    case.package_status = "approved"
    case.package_snapshot = sanitize_public_snapshot(version.public_snapshot)
    case.package_approved_by_user_id = principal.user_id
    case.package_approved_at = now
    if case.status in {"package_prep", "marketed"}:
        case.status = "buyer_matching"
    _audit(
        db,
        principal,
        "disposition.package_version_approve",
        version.id,
        {
            "case_id": str(case.id),
            "version_number": version.version_number,
            "source_fingerprint": version.source_fingerprint,
        },
        payload.reason,
    )
    from app.services.disposition_handoff import queue_disposition_package_ready_alert

    queue_disposition_package_ready_alert(
        db,
        disposition_case=case,
        package_version=version,
    )
    db.commit()
    return _version_read(
        principal,
        version,
        current_fingerprint=current["source_fingerprint"],
        latest_version_id=version.id,
    )


def require_current_approved_version(
    db: Session,
    principal: Principal,
    case: DispositionCase,
    *,
    action: str,
) -> DispositionPackageVersion:
    if case.organization_id != principal.organization_id:
        raise ValueError("Disposition case does not belong to this organization.")
    version = db.scalar(
        select(DispositionPackageVersion)
        .where(
            DispositionPackageVersion.organization_id == principal.organization_id,
            DispositionPackageVersion.disposition_case_id == case.id,
        )
        .order_by(DispositionPackageVersion.version_number.desc())
    )
    if (
        version is None
        or version.status != "approved"
        or case.package_status != "approved"
        or version.pdf_data is None
        or version.pdf_sha256 is None
    ):
        raise ValueError(f"An approved immutable disposition package is required before {action}.")
    current = assemble_package(db, principal, case)
    if not _version_matches_current_sources(
        version,
        current_fingerprint=current["source_fingerprint"],
    ):
        raise ValueError(
            "The approved disposition package is stale because material deal evidence, "
            "the package policy, or the renderer changed. Build and approve a new package "
            f"version before {action}."
        )
    if current["readiness"].get("blockers"):
        raise ValueError(
            f"The approved disposition package is no longer release-ready before {action}: "
            + "; ".join(current["readiness"]["blockers"])
        )
    return version


def exact_version_pdf(
    db: Session,
    principal: Principal,
    case_id: UUID,
    version_id: UUID,
) -> tuple[bytes, str] | None:
    version = db.scalar(
        select(DispositionPackageVersion).where(
            DispositionPackageVersion.id == version_id,
            DispositionPackageVersion.organization_id == principal.organization_id,
            DispositionPackageVersion.disposition_case_id == case_id,
        )
    )
    if version is None or version.pdf_data is None or version.pdf_file_name is None:
        return None
    return bytes(version.pdf_data), version.pdf_file_name


def compatibility_pdf(db: Session, principal: Principal, case_id: UUID) -> tuple[bytes, str] | None:
    case = db.scalar(
        select(DispositionCase).where(
            DispositionCase.id == case_id,
            DispositionCase.organization_id == principal.organization_id,
        )
    )
    if case is None:
        return None
    version = require_current_approved_version(
        db, principal, case, action="downloading the current package"
    )
    return bytes(version.pdf_data or b""), str(version.pdf_file_name)


def _audit(
    db: Session,
    principal: Principal,
    action: str,
    entity_id: UUID,
    new_value: dict[str, object],
    reason: str,
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type="disposition_package_version",
            entity_id=entity_id,
            previous_value=None,
            new_value=new_value,
            reason=reason,
        )
    )
