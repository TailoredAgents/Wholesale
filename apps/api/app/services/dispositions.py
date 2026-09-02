import csv
from datetime import UTC, datetime
from hashlib import sha256
from io import StringIO
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.assets import normalize_asset_class, property_identity_label, require_house_workflow
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    AuditEvent,
    Buyer,
    BuyerBuyBoxVersion,
    BuyerEngagement,
    BuyerOffer,
    BuyerProofDocument,
    CompensationPlanRole,
    CompensationPlanVersion,
    Contact,
    DealDeduction,
    DealPayout,
    DealReconciliation,
    DispositionBuyerPoolCandidate,
    DispositionCampaign,
    DispositionCampaignRecipient,
    DispositionCase,
    DispositionMatch,
    DispositionOperatingMode,
    DispositionPackageVersion,
    Lead,
    Property,
    RevenueRecord,
    RoleCredit,
    SuppressionRecord,
    Transaction,
    User,
)
from app.schemas.dispositions import (
    BuyerSelection,
    DispositionCaseCreate,
    DispositionCaseRead,
    DispositionMetrics,
    DispositionOverview,
    DispositionPackageApprovalRequest,
    EligibleTransactionRead,
    EngagementCreate,
    EngagementRead,
    MatchRead,
    OfferCreate,
    OfferRead,
    PayoutRead,
    ProofDocumentRead,
    ProofVerificationRequest,
    ReconciliationDecision,
    ReconciliationRead,
)
from app.services.buyers import get_current_buy_box_version
from app.services.disposition_handoff import derive_initial_disposition_economics
from app.services.disposition_state import (
    ACTIVE_DISPOSITION_CASE_STATUSES,
    advance_disposition_milestone,
)
from app.services.document_storage import read_content, store_content
from app.services.lead_lifecycle import (
    INACTIVE_LEAD_STAGES,
    lock_organization_lead,
    require_lead_not_closed_out,
)

MAX_FILE_BYTES = 15 * 1024 * 1024
REVIEWABLE_PROOF_SCAN_STATUSES = {"clean", "not_configured"}


def can_view_private_economics(principal: Principal) -> bool:
    return PermissionKeys.VIEW_DISPOSITION_PRIVATE_ECONOMICS in principal.permission_keys


def require_private_economics_access(principal: Principal) -> None:
    if not can_view_private_economics(principal):
        raise PermissionError(
            f"Missing permission: {PermissionKeys.VIEW_DISPOSITION_PRIVATE_ECONOMICS}"
        )


def require_private_economics_write(principal: Principal) -> None:
    require_private_economics_access(principal)


def scoped_case(db: Session, principal: Principal, case_id: UUID) -> DispositionCase | None:
    return db.scalar(
        select(DispositionCase).where(
            DispositionCase.id == case_id,
            DispositionCase.organization_id == principal.organization_id,
        )
    )


def scoped_case_for_mutation(
    db: Session,
    principal: Principal,
    case_id: UUID,
    *,
    allowed_statuses: set[str],
) -> DispositionCase | None:
    """Lock the lead before its disposition case and enforce the workflow transition."""
    existing = scoped_case(db, principal, case_id)
    if existing is None:
        return None
    lead = lock_organization_lead(
        db,
        organization_id=principal.organization_id,
        lead_id=existing.lead_id,
    )
    if lead is None:
        raise ValueError("The disposition lead is no longer available.")
    require_lead_not_closed_out(lead)
    case = db.scalar(
        select(DispositionCase)
        .where(
            DispositionCase.id == case_id,
            DispositionCase.organization_id == principal.organization_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if case is None:
        return None
    if case.status not in allowed_statuses:
        expected = ", ".join(sorted(value.replace("_", " ") for value in allowed_statuses))
        raise ValueError(
            f"This disposition action requires case status {expected}; "
            f"the case is {case.status.replace('_', ' ')}."
        )
    return case


def require_house_case_workflow(db: Session, case: DispositionCase) -> None:
    lead = db.get(Lead, case.lead_id)
    if lead is None:
        raise ValueError("The disposition lead is no longer available.")
    require_house_workflow(lead.asset_class, workflow="Residential buyer disposition")


def audit(
    db: Session,
    principal: Principal,
    action: str,
    entity_type: str,
    entity_id: UUID,
    new: dict[str, object],
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
            new_value=new,
            reason=reason,
        )
    )


def overview(db: Session, principal: Principal) -> DispositionOverview:
    may_view_private = can_view_private_economics(principal)
    cases = db.scalars(
        select(DispositionCase)
        .where(DispositionCase.organization_id == principal.organization_id)
        .order_by(DispositionCase.created_at.desc())
    ).all()
    used = {item.transaction_id for item in cases}
    transactions = db.scalars(
        select(Transaction)
        .join(Lead, Lead.id == Transaction.lead_id)
        .where(
            Transaction.organization_id == principal.organization_id,
            Transaction.status.in_(("executed", "closing", "funded")),
            Lead.asset_class.in_(("house", "land")),
            Lead.archived_at.is_(None),
            Lead.stage_key.not_in(INACTIVE_LEAD_STAGES),
        )
        .order_by(Transaction.created_at.desc())
    ).all()
    eligible = []
    for transaction in transactions:
        if transaction.id in used:
            continue
        contact = db.get(Contact, transaction.contact_id)
        property_record = db.get(Property, transaction.property_id)
        lead = db.get(Lead, transaction.lead_id)
        eligible.append(
            EligibleTransactionRead(
                id=transaction.id,
                asset_class=normalize_asset_class(lead.asset_class if lead else None),
                seller_name=contact.legal_name if contact else "Unknown seller",
                property_address=address(property_record),
                purchase_price_cents=(
                    transaction.purchase_price_cents if may_view_private else None
                ),
                assignment_fee_cents=(
                    transaction.assignment_fee_cents if may_view_private else None
                ),
            )
        )
    reads = [case_read(db, item, principal) for item in cases]
    return DispositionOverview(
        can_view_private_economics=may_view_private,
        metrics=DispositionMetrics(
            active_cases=sum(item.status not in {"closed", "cancelled"} for item in cases),
            packages_pending=sum(item.package_status != "approved" for item in cases),
            buyer_selected=sum(item.selected_buyer_id is not None for item in cases),
            reconciliation_pending=sum(
                item.reconciliation is not None and item.reconciliation.status == "draft"
                for item in reads
            ),
            below_margin_target=sum(
                item.reconciliation is not None
                and item.reconciliation.company_margin_basis_points
                < item.reconciliation.target_margin_basis_points
                for item in reads
            ),
        ),
        eligible_transactions=eligible,
        cases=reads,
    )


def create_case(
    db: Session, principal: Principal, payload: DispositionCaseCreate
) -> DispositionCaseRead:
    if PermissionKeys.EDIT_DEALS not in principal.permission_keys:
        raise PermissionError(f"Missing permission: {PermissionKeys.EDIT_DEALS}")
    has_private_economics_override = any(
        value is not None
        for value in (
            payload.asking_price_cents,
            payload.minimum_acceptable_cents,
            payload.desired_assignment_fee_cents,
        )
    )
    if has_private_economics_override:
        require_private_economics_write(principal)
    transaction = db.scalar(
        select(Transaction).where(
            Transaction.id == payload.transaction_id,
            Transaction.organization_id == principal.organization_id,
        )
    )
    if transaction is None or transaction.status not in {"executed", "closing", "funded"}:
        raise ValueError("An executed transaction is required.")
    lead = lock_organization_lead(
        db,
        organization_id=principal.organization_id,
        lead_id=transaction.lead_id,
    )
    if lead is None:
        raise ValueError("The transaction lead is no longer available.")
    require_lead_not_closed_out(lead)
    transaction = db.scalar(
        select(Transaction)
        .where(
            Transaction.id == payload.transaction_id,
            Transaction.organization_id == principal.organization_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if transaction is None or transaction.status not in {"executed", "closing", "funded"}:
        raise ValueError("An executed transaction is required.")
    initial_economics = derive_initial_disposition_economics(db, transaction)
    asking_price_cents = (
        payload.asking_price_cents
        if payload.asking_price_cents is not None
        else initial_economics.asking_price_cents
    )
    minimum_acceptable_cents = (
        payload.minimum_acceptable_cents
        if payload.minimum_acceptable_cents is not None
        else initial_economics.minimum_acceptable_cents
    )
    desired_assignment_fee_cents = (
        payload.desired_assignment_fee_cents
        if payload.desired_assignment_fee_cents is not None
        else initial_economics.desired_assignment_fee_cents
    )
    if minimum_acceptable_cents > asking_price_cents:
        raise ValueError("Minimum acceptable price cannot exceed asking price.")
    if db.scalar(
        select(DispositionCase.id).where(DispositionCase.transaction_id == transaction.id)
    ):
        raise ValueError("A disposition case already exists for this transaction.")
    plan = db.scalar(
        select(CompensationPlanVersion).where(
            CompensationPlanVersion.organization_id == principal.organization_id,
            CompensationPlanVersion.status == "active",
        )
    )
    mode = (
        db.scalar(
            select(DispositionOperatingMode).where(
                DispositionOperatingMode.compensation_plan_version_id == plan.id,
                DispositionOperatingMode.key == payload.operating_mode_key,
                DispositionOperatingMode.status == "available",
            )
        )
        if plan is not None
        else None
    )
    property_record = db.get(Property, transaction.property_id)
    case = DispositionCase(
        organization_id=principal.organization_id,
        transaction_id=transaction.id,
        deal_id=transaction.deal_id,
        lead_id=transaction.lead_id,
        property_id=transaction.property_id,
        owner_user_id=principal.user_id,
        compensation_plan_version_id=plan.id if plan else None,
        disposition_operating_mode_id=mode.id if mode else None,
        status="package_prep",
        strategy=payload.strategy,
        asking_price_cents=asking_price_cents,
        minimum_acceptable_cents=minimum_acceptable_cents,
        desired_assignment_fee_cents=desired_assignment_fee_cents,
        package_status="draft",
        package_snapshot={
            "package_reference": "pending",
            "asset_class": normalize_asset_class(lead.asset_class),
            "property": {
                "address": address(property_record),
                "asset_class": normalize_asset_class(lead.asset_class),
                "property_type": property_record.property_type if property_record else None,
            },
            "opportunity": {"strategy": payload.strategy},
            "pricing": {"buyer_asking_price_cents": asking_price_cents},
            "due_diligence": [
                "Buyer must independently verify property facts, access, title, and "
                "closing capacity."
            ],
        },
        package_approved_by_user_id=None,
        package_approved_at=None,
        selected_buyer_id=None,
        backup_buyer_id=None,
        selection_approved_by_user_id=None,
        selection_approved_at=None,
        notes=payload.notes,
    )
    db.add(case)
    if plan is not None:
        transaction.compensation_plan_version_id = plan.id
    if mode is not None:
        transaction.disposition_operating_mode_id = mode.id
    db.flush()
    audit(
        db,
        principal,
        "disposition.case_create",
        "disposition_case",
        case.id,
        {
            "transaction_id": str(transaction.id),
            "asset_class": normalize_asset_class(lead.asset_class),
            "plan_id": str(plan.id) if plan else None,
            "mode_id": str(mode.id) if mode else None,
            "private_economics_source": (
                "operator_override"
                if has_private_economics_override
                else initial_economics.source
            ),
            "setup_warnings": [
                *([] if plan else ["No active compensation plan."]),
                *([] if mode else ["No available disposition operating mode."]),
            ],
        },
        "Disposition case opened",
    )
    db.commit()
    return case_read(db, case, principal)


def approve_package(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: DispositionPackageApprovalRequest,
) -> DispositionCaseRead | None:
    case = scoped_case(db, principal, case_id)
    if case is None:
        return None
    latest_draft = db.scalar(
        select(DispositionPackageVersion)
        .where(
            DispositionPackageVersion.organization_id == principal.organization_id,
            DispositionPackageVersion.disposition_case_id == case.id,
            DispositionPackageVersion.status == "draft",
        )
        .order_by(DispositionPackageVersion.version_number.desc())
    )
    if latest_draft is None:
        raise ValueError("Create a package draft before approving it.")
    from app.services.disposition_packages import approve_version

    approved = approve_version(db, principal, case.id, latest_draft.id, payload)
    if approved is None:
        return None
    db.refresh(case)
    return case_read(db, case, principal)


def generate_matches(
    db: Session, principal: Principal, case_id: UUID
) -> DispositionCaseRead | None:
    case = scoped_case_for_mutation(
        db,
        principal,
        case_id,
        allowed_statuses=set(ACTIVE_DISPOSITION_CASE_STATUSES),
    )
    if case is None:
        return None
    require_house_case_workflow(db, case)
    property_record = db.get(Property, case.property_id)
    db.execute(delete(DispositionMatch).where(DispositionMatch.disposition_case_id == case.id))
    scored: list[
        tuple[
            Buyer,
            int,
            dict[str, int],
            str,
            BuyerBuyBoxVersion | None,
            dict[str, object] | None,
        ]
    ] = []
    now = datetime.now(UTC)
    buyers = db.scalars(
        select(Buyer).where(
            Buyer.organization_id == principal.organization_id,
            Buyer.status == "active",
            Buyer.relationship_status != "do_not_contact",
            Buyer.archived_at.is_(None),
        )
    ).all()
    for buyer in buyers:
        buy_box_result = get_current_buy_box_version(
            db,
            principal,
            buyer.id,
            "house",
            require_verified=True,
        )
        buy_box_version = buy_box_result[1] if buy_box_result else None
        criteria = dict(buy_box_version.criteria_payload) if buy_box_version else None
        price_ok = _structured_price_match(criteria, case.asking_price_cents)
        market_ok = _structured_market_match(criteria, property_record)
        type_ok = _structured_house_type_match(criteria, property_record)
        strategy_ok = _structured_strategy_match(criteria, case.strategy)
        proof = next(
            (
                item
                for item in db.scalars(
                    select(BuyerProofDocument)
                    .where(
                        BuyerProofDocument.buyer_id == buyer.id,
                        BuyerProofDocument.organization_id == principal.organization_id,
                        BuyerProofDocument.status == "verified",
                        BuyerProofDocument.deleted_at.is_(None),
                    )
                    .order_by(
                        BuyerProofDocument.verified_at.desc(),
                        BuyerProofDocument.created_at.desc(),
                    )
                ).all()
                if _proof_is_current_verified(item, now=now)
            ),
            None,
        )
        pof_ok = proof is not None
        if pof_ok and proof and proof.verified_amount_cents is not None:
            pof_ok = proof.verified_amount_cents >= case.asking_price_cents
        components = {
            "proof": 3000 if pof_ok else 0,
            "price": 2500 if price_ok else 0,
            "market": 2000 if market_ok else 0,
            "reliability": (
                round(buyer.reliability_score_basis_points * 0.15)
                if buyer.completed_deals + buyer.failed_deals > 0
                else 0
            ),
            "property_type": 1000 if type_ok else 0,
        }
        score = sum(components.values())
        qualified = bool(
            buy_box_version and price_ok and market_ok and type_ok and strategy_ok and pof_ok
        )
        scored.append(
            (
                buyer,
                score,
                components,
                "qualified" if qualified else "review_required",
                buy_box_version,
                criteria,
            )
        )
    scored.sort(key=lambda value: value[1], reverse=True)
    for rank, (
        buyer,
        score,
        components,
        qualification,
        buy_box_version,
        criteria,
    ) in enumerate(scored, 1):
        db.add(
            DispositionMatch(
                organization_id=principal.organization_id,
                disposition_case_id=case.id,
                buyer_id=buyer.id,
                score_basis_points=score,
                score_components=components,
                qualification_status=qualification,
                recipient_status="proposed" if qualification == "qualified" else "excluded",
                rank=rank,
                buy_box_version_id=buy_box_version.id if buy_box_version else None,
                matcher_version="house_buy_box_v1",
                criteria_snapshot=(
                    {
                        "asset_class": "house",
                        "verification_status": buy_box_version.verification_status,
                        "version_number": buy_box_version.version_number,
                        "criteria": criteria,
                    }
                    if buy_box_version
                    else {
                        "asset_class": "house",
                        "verification_status": "missing",
                        "criteria": None,
                        "legacy_criteria_excluded": True,
                    }
                ),
            )
        )
    # DS4 records a parallel, append-only evaluation run. The legacy match rows
    # remain the compatibility projection used by offers and existing releases.
    from app.services.disposition_buyer_pool import generate_buyer_pool_run

    generate_buyer_pool_run(
        db,
        principal,
        case.id,
        locked_case=case,
        commit=False,
    )
    db.commit()
    return case_read(db, case, principal)


def release_campaign(
    db: Session,
    principal: Principal,
    case_id: UUID,
    package_version_id: UUID | None = None,
) -> DispositionCaseRead | None:
    case = scoped_case_for_mutation(
        db,
        principal,
        case_id,
        allowed_statuses=set(ACTIVE_DISPOSITION_CASE_STATUSES),
    )
    if case is None:
        return None
    from app.services.disposition_packages import require_package_artifact

    package_version = require_package_artifact(
        db,
        principal,
        case,
        action="preparing campaign recipients",
        package_version_id=package_version_id,
    )
    matches = list(
        db.scalars(
            select(DispositionMatch)
            .where(
                DispositionMatch.organization_id == principal.organization_id,
                DispositionMatch.disposition_case_id == case.id,
            )
            .with_for_update()
        ).all()
    )
    case_candidates = list(
        db.scalars(
            select(DispositionBuyerPoolCandidate).where(
                DispositionBuyerPoolCandidate.organization_id
                == principal.organization_id,
                DispositionBuyerPoolCandidate.disposition_case_id == case.id,
                DispositionBuyerPoolCandidate.buyer_id.is_not(None),
            )
        ).all()
    )
    passed_buyer_ids = {
        candidate.buyer_id
        for candidate in case_candidates
        if candidate.buyer_id is not None
        and (
            candidate.decision_status == "passed"
            or candidate.lifecycle_stage == "pass"
        )
    }
    buyers = {
        buyer.id: buyer
        for buyer in db.scalars(
            select(Buyer)
            .where(
                Buyer.organization_id == principal.organization_id,
                Buyer.archived_at.is_(None),
                Buyer.status != "archived",
            )
            .with_for_update()
        ).all()
    }
    buyer_ids = set(buyers) - passed_buyer_ids
    suppressed_destinations = {
        (suppression.channel, suppression.normalized_address)
        for suppression in db.scalars(
            select(SuppressionRecord).where(
                SuppressionRecord.organization_id == principal.organization_id,
                SuppressionRecord.status == "active",
            )
        ).all()
    }
    matches_by_buyer_id = {match.buyer_id: match for match in matches}
    for existing_match in matches:
        if existing_match.buyer_id not in buyers:
            existing_match.qualification_status = "ineligible"
            existing_match.recipient_status = "excluded"
        elif existing_match.buyer_id in passed_buyer_ids:
            existing_match.recipient_status = "excluded"
    eligible_buyer_ids: set[UUID] = set()
    destinations_by_buyer_id: dict[UUID, dict[str, str]] = {}
    for buyer_id in buyer_ids:
        buyer = buyers.get(buyer_id)
        matched_record = matches_by_buyer_id.get(buyer_id)
        if (
            buyer is None
            or buyer.status == "do_not_contact"
            or buyer.relationship_status == "do_not_contact"
            or buyer.archived_at is not None
        ):
            if matched_record is not None:
                matched_record.qualification_status = "ineligible"
                matched_record.recipient_status = "excluded"
            continue
        destinations = _campaign_destinations(buyer, suppressed_destinations)
        if not destinations:
            if matched_record is not None:
                matched_record.qualification_status = "ineligible"
                matched_record.recipient_status = "excluded"
            continue
        eligible_buyer_ids.add(buyer_id)
        destinations_by_buyer_id[buyer_id] = destinations
    if not eligible_buyer_ids:
        # Persist lifecycle invalidation so the stale match cannot be reused on a retry.
        db.commit()
        raise ValueError(
            "No non-suppressed buyers with a usable email address or phone number are "
            "available."
        )
    existing_campaigns = list(
        db.scalars(
            select(DispositionCampaign)
            .where(
                DispositionCampaign.organization_id == principal.organization_id,
                DispositionCampaign.disposition_case_id == case.id,
                DispositionCampaign.package_version_id == package_version.id,
                DispositionCampaign.status == "prepared_not_sent",
            )
            .order_by(DispositionCampaign.created_at.desc())
            .with_for_update()
        ).all()
    )
    for existing_campaign in existing_campaigns:
        existing_recipients = list(
            db.scalars(
                select(DispositionCampaignRecipient).where(
                    DispositionCampaignRecipient.organization_id == principal.organization_id,
                    DispositionCampaignRecipient.disposition_campaign_id == existing_campaign.id,
                    DispositionCampaignRecipient.package_version_id == package_version.id,
                    DispositionCampaignRecipient.status == "prepared_not_sent",
                )
            ).all()
        )
        existing_buyer_ids = {
            recipient.buyer_id
            for recipient in existing_recipients
            if recipient.buyer_id is not None
        }
        if existing_buyer_ids == eligible_buyer_ids and len(existing_recipients) == len(
            eligible_buyer_ids
        ):
            for match in matches:
                if match.buyer_id in eligible_buyer_ids:
                    match.recipient_status = "prepared_not_sent"
            db.commit()
            return case_read(db, case, principal)
    for match in matches:
        if match.buyer_id in eligible_buyer_ids:
            match.recipient_status = "prepared_not_sent"
    campaign = DispositionCampaign(
        organization_id=principal.organization_id,
        disposition_case_id=case.id,
        package_version_id=package_version.id,
        created_by_user_id=principal.user_id,
        status="prepared_not_sent",
        name=f"{address(db.get(Property, case.property_id))} buyer release",
        channel="email_sms_preparation",
        recipient_count=len(eligible_buyer_ids),
        released_at=None,
    )
    db.add(campaign)
    db.flush()
    prepared_at = datetime.now(UTC)
    recipient_set_fingerprint = sha256(
        ":".join(sorted(str(buyer_id) for buyer_id in eligible_buyer_ids)).encode()
    ).hexdigest()
    for buyer_id in sorted(eligible_buyer_ids, key=str):
        buyer = buyers[buyer_id]
        destinations = destinations_by_buyer_id[buyer_id]
        idempotency_key = sha256(
            (
                f"{principal.organization_id}:{case.id}:{package_version.id}:"
                f"{recipient_set_fingerprint}:{buyer.id}"
            ).encode()
        ).hexdigest()
        db.add(
            DispositionCampaignRecipient(
                organization_id=principal.organization_id,
                disposition_campaign_id=campaign.id,
                disposition_case_id=case.id,
                package_version_id=package_version.id,
                buyer_id=buyer.id,
                prepared_by_user_id=principal.user_id,
                status="prepared_not_sent",
                captured_identity={
                    "buyer_name": buyer.name,
                    "company_name": buyer.company_name,
                },
                captured_destination=destinations,
                idempotency_key=idempotency_key,
                artifact_sha256=str(package_version.pdf_sha256),
                prepared_at=prepared_at,
            )
        )
    db.commit()
    return case_read(db, case, principal)


def _campaign_destinations(
    buyer: Buyer,
    suppressed_destinations: set[tuple[str, str]],
) -> dict[str, str]:
    destinations: dict[str, str] = {}
    normalized_email = buyer.normalized_email
    if (
        buyer.email
        and normalized_email
        and ("email", normalized_email) not in suppressed_destinations
        and ("all", normalized_email) not in suppressed_destinations
    ):
        destinations["email"] = buyer.email
    normalized_phone = buyer.normalized_phone
    if (
        buyer.phone
        and normalized_phone
        and ("sms", normalized_phone) not in suppressed_destinations
        and ("phone", normalized_phone) not in suppressed_destinations
        and ("all", normalized_phone) not in suppressed_destinations
    ):
        destinations["phone"] = buyer.phone
    return destinations


def upload_proof(
    db: Session,
    principal: Principal,
    buyer_id: UUID,
    *,
    content: bytes,
    file_name: str,
    content_type: str,
    institution_name: str | None,
    verified_amount_cents: int | None,
    expires_at: datetime | None,
) -> ProofDocumentRead:
    buyer = db.scalar(
        select(Buyer)
        .where(Buyer.id == buyer_id, Buyer.organization_id == principal.organization_id)
        .with_for_update()
    )
    if buyer is None:
        raise ValueError("Buyer not found.")
    if not content or len(content) > MAX_FILE_BYTES:
        raise ValueError("Proof document must be between 1 byte and 15 MB.")
    file_name = file_name.strip()
    if not file_name or "\r" in file_name or "\n" in file_name:
        raise ValueError("Proof document file name is invalid.")
    document_id = uuid4()
    stored = store_content(
        organization_id=principal.organization_id,
        namespace=f"buyers/{buyer.id}/proof-of-funds",
        record_id=document_id,
        file_name=file_name,
        content_type=content_type,
        content=content,
    )
    document = BuyerProofDocument(
        id=document_id,
        organization_id=principal.organization_id,
        buyer_id=buyer.id,
        uploaded_by_user_id=principal.user_id,
        status="received",
        verified_by_user_id=None,
        verified_at=None,
        verification_source=None,
        institution_name=institution_name,
        verified_amount_cents=verified_amount_cents,
        expires_at=expires_at,
        file_name=file_name,
        content_type=content_type,
        file_size=len(content),
        sha256=sha256(content).hexdigest(),
        file_data=stored.database_bytes,
        storage_provider=stored.provider,
        storage_key=stored.key,
        malware_scan_status=stored.malware_scan_status,
        retention_until=stored.retention_until,
        deleted_at=None,
        notes=None,
    )
    db.add(document)
    # A renewal upload must not downgrade a still-current verified document.
    # This aggregate is always projected from the underlying evidence records.
    _refresh_buyer_proof_summary(db, buyer)
    audit(
        db,
        principal,
        "buyer.proof_received",
        "buyer_proof_document",
        document.id,
        {
            "buyer_id": str(buyer.id),
            "status": "received",
            "sha256": document.sha256,
            "malware_scan_status": document.malware_scan_status,
        },
        "Proof-of-funds evidence received for human review",
    )
    db.commit()
    db.refresh(document)
    return proof_read(document)


def list_proof(
    db: Session,
    principal: Principal,
    buyer_id: UUID,
) -> list[ProofDocumentRead] | None:
    buyer = db.scalar(
        select(Buyer.id).where(
            Buyer.id == buyer_id,
            Buyer.organization_id == principal.organization_id,
        )
    )
    if buyer is None:
        return None
    return [
        proof_read(document)
        for document in db.scalars(
            select(BuyerProofDocument)
            .where(
                BuyerProofDocument.organization_id == principal.organization_id,
                BuyerProofDocument.buyer_id == buyer_id,
                BuyerProofDocument.deleted_at.is_(None),
            )
            .order_by(BuyerProofDocument.created_at.desc())
        ).all()
    ]


def review_proof(
    db: Session,
    principal: Principal,
    document_id: UUID,
    payload: ProofVerificationRequest,
) -> ProofDocumentRead | None:
    document = db.scalar(
        select(BuyerProofDocument)
        .where(
            BuyerProofDocument.id == document_id,
            BuyerProofDocument.organization_id == principal.organization_id,
            BuyerProofDocument.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if document is None:
        return None
    buyer = db.scalar(
        select(Buyer)
        .where(
            Buyer.id == document.buyer_id,
            Buyer.organization_id == principal.organization_id,
        )
        .with_for_update()
    )
    if buyer is None:
        return None
    previous_status = document.status
    now = datetime.now(UTC)
    if payload.decision == "verified":
        if document.malware_scan_status not in REVIEWABLE_PROOF_SCAN_STATUSES:
            raise ValueError("Proof of funds cannot be verified until its safety review passes.")
        verified_amount = payload.verified_amount_cents or document.verified_amount_cents
        expires_at = payload.expires_at or document.expires_at
        if verified_amount is None or verified_amount <= 0:
            raise ValueError("Enter the amount confirmed by the proof-of-funds review.")
        if expires_at is None or aware(expires_at) <= now:
            raise ValueError("Verified proof of funds requires a future expiration date.")
        document.status = "verified"
        document.verified_amount_cents = verified_amount
        document.expires_at = expires_at
        document.institution_name = payload.institution_name or document.institution_name
        document.verified_by_user_id = principal.user_id
        document.verified_at = now
        document.verification_source = payload.verification_source.strip()
        document.notes = payload.notes.strip()
    else:
        document.status = "rejected"
        document.verified_by_user_id = principal.user_id
        document.verified_at = now
        document.verification_source = payload.verification_source.strip()
        document.notes = payload.notes.strip()
    _refresh_buyer_proof_summary(db, buyer, now=now)
    audit(
        db,
        principal,
        f"buyer.proof_{payload.decision}",
        "buyer_proof_document",
        document.id,
        {
            "buyer_id": str(buyer.id),
            "previous_status": previous_status,
            "status": document.status,
            "verified_amount_cents": document.verified_amount_cents,
            "expires_at": document.expires_at.isoformat() if document.expires_at else None,
            "verification_source": document.verification_source,
        },
        payload.notes.strip(),
    )
    db.commit()
    db.refresh(document)
    return proof_read(document)


def get_proof_content(
    db: Session,
    principal: Principal,
    document_id: UUID,
) -> tuple[BuyerProofDocument, bytes] | None:
    document = db.scalar(
        select(BuyerProofDocument).where(
            BuyerProofDocument.id == document_id,
            BuyerProofDocument.organization_id == principal.organization_id,
            BuyerProofDocument.deleted_at.is_(None),
        )
    )
    if document is None:
        return None
    if document.malware_scan_status not in REVIEWABLE_PROOF_SCAN_STATUSES:
        return None
    content = read_content(
        provider=document.storage_provider,
        key=document.storage_key,
        database_bytes=document.file_data,
    )
    audit(
        db,
        principal,
        "buyer.proof_download",
        "buyer_proof_document",
        document.id,
        {
            "buyer_id": str(document.buyer_id),
            "file_name": document.file_name,
            "sha256": document.sha256,
        },
        "Restricted proof-of-funds evidence accessed",
    )
    db.commit()
    return document, content


def _proof_is_current_verified(document: BuyerProofDocument, *, now: datetime) -> bool:
    return bool(
        document.deleted_at is None
        and document.status == "verified"
        and document.verified_by_user_id is not None
        and document.verified_at is not None
        and document.verified_amount_cents is not None
        and document.verified_amount_cents > 0
        and document.expires_at is not None
        and aware(document.expires_at) > now
        and document.malware_scan_status in REVIEWABLE_PROOF_SCAN_STATUSES
    )


def _refresh_buyer_proof_summary(
    db: Session,
    buyer: Buyer,
    *,
    now: datetime | None = None,
) -> None:
    checked_at = now or datetime.now(UTC)
    documents = list(
        db.scalars(
            select(BuyerProofDocument)
            .where(
                BuyerProofDocument.organization_id == buyer.organization_id,
                BuyerProofDocument.buyer_id == buyer.id,
                BuyerProofDocument.deleted_at.is_(None),
            )
            .order_by(BuyerProofDocument.created_at.desc())
        ).all()
    )
    current = next(
        (item for item in documents if _proof_is_current_verified(item, now=checked_at)),
        None,
    )
    if current is not None:
        buyer.proof_of_funds_status = "verified"
        buyer.proof_of_funds_expires_at = current.expires_at
    elif any(item.status == "received" for item in documents):
        buyer.proof_of_funds_status = "received"
        buyer.proof_of_funds_expires_at = None
    elif any(
        item.status == "verified"
        and item.expires_at is not None
        and aware(item.expires_at) <= checked_at
        for item in documents
    ):
        buyer.proof_of_funds_status = "expired"
        buyer.proof_of_funds_expires_at = None
    elif any(item.status == "rejected" for item in documents):
        buyer.proof_of_funds_status = "rejected"
        buyer.proof_of_funds_expires_at = None
    else:
        buyer.proof_of_funds_status = "unknown"
        buyer.proof_of_funds_expires_at = None


def create_offer(
    db: Session, principal: Principal, case_id: UUID, payload: OfferCreate
) -> DispositionCaseRead | None:
    case = scoped_case_for_mutation(
        db,
        principal,
        case_id,
        allowed_statuses=set(ACTIVE_DISPOSITION_CASE_STATUSES),
    )
    if case is None:
        return None
    buyer = db.scalar(
        select(Buyer).where(
            Buyer.id == payload.buyer_id, Buyer.organization_id == principal.organization_id
        )
    )
    if buyer is None:
        raise ValueError("Buyer not found.")
    proof = (
        db.scalar(
            select(BuyerProofDocument).where(
                BuyerProofDocument.id == payload.proof_document_id,
                BuyerProofDocument.organization_id == principal.organization_id,
                BuyerProofDocument.buyer_id == buyer.id,
                BuyerProofDocument.deleted_at.is_(None),
            )
        )
        if payload.proof_document_id
        else None
    )
    if payload.proof_document_id is not None and proof is None:
        raise ValueError("The selected proof-of-funds document is unavailable for this buyer.")
    offer = BuyerOffer(
        organization_id=principal.organization_id,
        lead_id=case.lead_id,
        deal_id=case.deal_id,
        buyer_id=buyer.id,
        disposition_case_id=case.id,
        proof_document_id=proof.id if proof else None,
        amount_cents=payload.amount_cents,
        earnest_money_cents=payload.earnest_money_cents,
        financing_type=payload.financing_type,
        status="received",
        proof_of_funds_received=proof is not None,
        notes=payload.notes,
        received_at=datetime.now(UTC),
        deposit_due_at=payload.deposit_due_at,
        deposit_received_at=None,
        selected_at=None,
    )
    db.add(offer)
    advance_disposition_milestone(case, "offers_received")
    db.commit()
    return case_read(db, case, principal)


def add_engagement(
    db: Session, principal: Principal, case_id: UUID, payload: EngagementCreate
) -> DispositionCaseRead | None:
    case = scoped_case_for_mutation(
        db,
        principal,
        case_id,
        allowed_statuses=set(ACTIVE_DISPOSITION_CASE_STATUSES),
    )
    if case is None:
        return None
    buyer = db.scalar(
        select(Buyer).where(
            Buyer.id == payload.buyer_id,
            Buyer.organization_id == principal.organization_id,
        )
    )
    if buyer is None:
        raise ValueError("Buyer not found.")
    db.add(
        BuyerEngagement(
            organization_id=principal.organization_id,
            disposition_case_id=case.id,
            buyer_id=payload.buyer_id,
            actor_user_id=principal.user_id,
            engagement_type=payload.engagement_type,
            status=payload.status,
            scheduled_at=payload.scheduled_at,
            occurred_at=datetime.now(UTC),
            notes=payload.notes,
        )
    )
    db.commit()
    return case_read(db, case, principal)


def select_buyer(
    db: Session, principal: Principal, case_id: UUID, payload: BuyerSelection
) -> DispositionCaseRead | None:
    require_private_economics_access(principal)
    case = scoped_case_for_mutation(
        db,
        principal,
        case_id,
        allowed_statuses=set(ACTIVE_DISPOSITION_CASE_STATUSES),
    )
    if case is None:
        return None
    primary = db.scalar(
        select(BuyerOffer).where(
            BuyerOffer.id == payload.primary_offer_id,
            BuyerOffer.organization_id == principal.organization_id,
            BuyerOffer.disposition_case_id == case.id,
        )
    )
    backup = (
        db.scalar(
            select(BuyerOffer).where(
                BuyerOffer.id == payload.backup_offer_id,
                BuyerOffer.organization_id == principal.organization_id,
                BuyerOffer.disposition_case_id == case.id,
            )
        )
        if payload.backup_offer_id
        else None
    )
    if primary is None:
        raise ValueError("Primary offer not found for this disposition case.")
    if backup and backup.id == primary.id:
        raise ValueError("Primary and backup offers must be different.")
    proof = (
        db.scalar(
            select(BuyerProofDocument).where(
                BuyerProofDocument.id == primary.proof_document_id,
                BuyerProofDocument.organization_id == principal.organization_id,
                BuyerProofDocument.buyer_id == primary.buyer_id,
                BuyerProofDocument.deleted_at.is_(None),
            )
        )
        if primary.proof_document_id
        else None
    )
    selection_warnings: list[str] = []
    if primary.amount_cents < case.minimum_acceptable_cents:
        selection_warnings.append("Primary offer is below the current minimum.")
    if (
        proof is None
        or not _proof_is_current_verified(proof, now=datetime.now(UTC))
        or proof.verified_amount_cents is None
        or proof.verified_amount_cents < primary.amount_cents
    ):
        selection_warnings.append("Current verified proof does not cover the primary offer.")
    now = datetime.now(UTC)
    primary.status = "selected"
    primary.selected_at = now
    if backup:
        backup.status = "backup"
    for other in db.scalars(
        select(BuyerOffer).where(
            BuyerOffer.disposition_case_id == case.id,
            BuyerOffer.organization_id == principal.organization_id,
            BuyerOffer.status.in_(("selected", "backup")),
            BuyerOffer.id.notin_(
                [value for value in (primary.id, backup.id if backup else None) if value]
            ),
        )
    ).all():
        other.status = "received"
    case.selected_buyer_id = primary.buyer_id
    case.backup_buyer_id = backup.buyer_id if backup else None
    case.selection_approved_by_user_id = principal.user_id
    case.selection_approved_at = now
    advance_disposition_milestone(case, "buyer_selected")
    audit(
        db,
        principal,
        "disposition.buyer_select",
        "disposition_case",
        case.id,
        {
            "primary_buyer_id": str(primary.buyer_id),
            "backup_buyer_id": str(backup.buyer_id) if backup else None,
            "backup_coverage_state": "covered" if backup else "missing",
            "advisory_warnings": [
                *selection_warnings,
                *([] if backup else ["No backup buyer is selected."]),
            ],
        },
        payload.reason,
    )
    db.commit()
    return case_read(db, case, principal)


def build_reconciliation(
    db: Session, principal: Principal, case_id: UUID
) -> DispositionCaseRead | None:
    require_private_economics_access(principal)
    case = scoped_case_for_mutation(db, principal, case_id, allowed_statuses={"buyer_selected"})
    if case is None:
        return None
    _require_house_reconciliation_case(db, principal, case)
    transaction = db.scalar(
        select(Transaction).where(
            Transaction.id == case.transaction_id,
            Transaction.organization_id == principal.organization_id,
        )
    )
    if transaction is None or transaction.status != "funded" or case.selected_buyer_id is None:
        raise ValueError("Funded transaction and approved buyer selection are required.")
    gross = int(
        db.scalar(
            select(func.coalesce(func.sum(RevenueRecord.amount_cents), 0)).where(
                RevenueRecord.transaction_id == transaction.id, RevenueRecord.status == "collected"
            )
        )
        or 0
    )
    if gross <= 0:
        raise ValueError("Record collected deal revenue before reconciliation.")
    deductions = int(
        db.scalar(
            select(func.coalesce(func.sum(DealDeduction.amount_cents), 0)).where(
                DealDeduction.transaction_id == transaction.id
            )
        )
        or 0
    )
    if case.compensation_plan_version_id is None:
        raise ValueError(
            "Attach a frozen compensation plan before financial reconciliation."
        )
    plan = db.scalar(
        select(CompensationPlanVersion).where(
            CompensationPlanVersion.id == case.compensation_plan_version_id,
            CompensationPlanVersion.organization_id == principal.organization_id,
        )
    )
    if plan is None:
        raise ValueError("The frozen compensation plan is unavailable in this organization.")
    if case.disposition_operating_mode_id is None:
        raise ValueError(
            "Attach an operating mode before financial reconciliation. Deal work may continue."
        )
    operating_mode = db.scalar(
        select(DispositionOperatingMode).where(
            DispositionOperatingMode.id == case.disposition_operating_mode_id,
            DispositionOperatingMode.organization_id == principal.organization_id,
            DispositionOperatingMode.compensation_plan_version_id == plan.id,
        )
    )
    if operating_mode is None:
        raise ValueError(
            "The operating mode is unavailable or does not belong to the frozen compensation "
            "plan."
        )
    margin = max(gross - plan.acquisition_reserve_cents - deductions, 0)
    reconciliation = db.scalar(
        select(DealReconciliation).where(
            DealReconciliation.organization_id == principal.organization_id,
            DealReconciliation.transaction_id == transaction.id,
        )
    )
    if reconciliation and reconciliation.status == "approved":
        raise ValueError("Approved reconciliation cannot be recalculated.")
    if reconciliation is None:
        reconciliation = DealReconciliation(
            organization_id=principal.organization_id,
            transaction_id=transaction.id,
            disposition_case_id=case.id,
            compensation_plan_version_id=plan.id,
            disposition_operating_mode_id=operating_mode.id,
            created_by_user_id=principal.user_id,
            approved_by_user_id=None,
            status="draft",
            gross_revenue_cents=0,
            acquisition_reserve_cents=0,
            deal_deductions_cents=0,
            adjusted_deal_margin_cents=0,
            total_compensation_cents=0,
            company_profit_cents=0,
            company_margin_basis_points=0,
            target_margin_basis_points=plan.target_company_margin_basis_points,
            snapshot={},
            approved_at=None,
            notes=None,
        )
        db.add(reconciliation)
        db.flush()
    db.execute(delete(DealPayout).where(DealPayout.deal_reconciliation_id == reconciliation.id))
    roles = db.scalars(
        select(CompensationPlanRole).where(
            CompensationPlanRole.compensation_plan_version_id == plan.id
        )
    ).all()
    payouts_total = 0
    for role in roles:
        role_amount = round(margin * role.basis_points / 10000)
        if role.cap_cents is not None:
            role_amount = min(role_amount, role.cap_cents)
        credits = db.scalars(
            select(RoleCredit).where(
                RoleCredit.lead_id == case.lead_id,
                RoleCredit.role_key == role.role_key,
                RoleCredit.status.in_(("approved", "earned", "payable")),
            )
        ).all()
        if credits:
            allocated_basis_points = 0
            for credit in credits:
                amount = round(role_amount * credit.credit_basis_points / 10000)
                allocated_basis_points += credit.credit_basis_points
                payouts_total += amount
                db.add(
                    DealPayout(
                        organization_id=principal.organization_id,
                        deal_reconciliation_id=reconciliation.id,
                        role_credit_id=credit.id,
                        user_id=credit.user_id,
                        role_key=role.role_key,
                        credit_basis_points=credit.credit_basis_points,
                        amount_cents=amount,
                        status="calculated",
                        approved_at=None,
                        paid_at=None,
                    )
                )
            unassigned_basis_points = max(10000 - allocated_basis_points, 0)
            if unassigned_basis_points:
                amount = round(role_amount * unassigned_basis_points / 10000)
                payouts_total += amount
                db.add(
                    DealPayout(
                        organization_id=principal.organization_id,
                        deal_reconciliation_id=reconciliation.id,
                        role_credit_id=None,
                        user_id=None,
                        role_key=role.role_key,
                        credit_basis_points=unassigned_basis_points,
                        amount_cents=amount,
                        status="unassigned",
                        approved_at=None,
                        paid_at=None,
                    )
                )
        else:
            payouts_total += role_amount
            db.add(
                DealPayout(
                    organization_id=principal.organization_id,
                    deal_reconciliation_id=reconciliation.id,
                    role_credit_id=None,
                    user_id=None,
                    role_key=role.role_key,
                    credit_basis_points=10000,
                    amount_cents=role_amount,
                    status="unassigned",
                    approved_at=None,
                    paid_at=None,
                )
            )
    company = margin - payouts_total
    reconciliation.status = "draft"
    reconciliation.gross_revenue_cents = gross
    reconciliation.acquisition_reserve_cents = plan.acquisition_reserve_cents
    reconciliation.deal_deductions_cents = deductions
    reconciliation.adjusted_deal_margin_cents = margin
    reconciliation.total_compensation_cents = payouts_total
    reconciliation.company_profit_cents = company
    reconciliation.company_margin_basis_points = round(company * 10000 / margin) if margin else 0
    reconciliation.snapshot = {
        "plan_name": plan.name,
        "plan_version": plan.version_number,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    db.commit()
    return case_read(db, case, principal)


def decide_reconciliation(
    db: Session, principal: Principal, case_id: UUID, payload: ReconciliationDecision
) -> DispositionCaseRead | None:
    require_private_economics_access(principal)
    case = scoped_case_for_mutation(db, principal, case_id, allowed_statuses={"buyer_selected"})
    if case is None:
        return None
    _require_house_reconciliation_case(db, principal, case)
    reconciliation = db.scalar(
        select(DealReconciliation).where(
            DealReconciliation.organization_id == principal.organization_id,
            DealReconciliation.disposition_case_id == case.id,
        )
    )
    if reconciliation is None or reconciliation.status != "draft":
        raise ValueError("A draft reconciliation is required.")
    if (
        payload.decision == "approved"
        and reconciliation.company_margin_basis_points < reconciliation.target_margin_basis_points
        and not payload.approve_below_target
    ):
        raise ValueError(
            "Company margin is below target. Record an explicit owner override to approve."
        )
    unassigned_payout = db.scalar(
        select(DealPayout.id).where(
            DealPayout.deal_reconciliation_id == reconciliation.id,
            DealPayout.user_id.is_(None),
            DealPayout.amount_cents > 0,
        )
    )
    if payload.decision == "approved" and unassigned_payout is not None:
        raise ValueError("Approve role credits for every commission role before reconciliation.")
    now = datetime.now(UTC)
    reconciliation.status = payload.decision
    reconciliation.notes = payload.notes
    reconciliation.approved_by_user_id = principal.user_id
    reconciliation.approved_at = now
    for payout in db.scalars(
        select(DealPayout).where(DealPayout.deal_reconciliation_id == reconciliation.id)
    ).all():
        payout.status = (
            "approved" if payload.decision == "approved" and payout.user_id else payout.status
        )
        payout.approved_at = now if payout.status == "approved" else None
    if payload.decision == "approved":
        case.status = "reconciled"
    audit(
        db,
        principal,
        "finance.reconciliation_decide",
        "deal_reconciliation",
        reconciliation.id,
        {
            "status": reconciliation.status,
            "company_margin_basis_points": reconciliation.company_margin_basis_points,
        },
        payload.notes,
    )
    db.commit()
    return case_read(db, case, principal)


def package_pdf(db: Session, principal: Principal, case_id: UUID) -> tuple[bytes, str] | None:
    from app.services.disposition_packages import compatibility_pdf

    return compatibility_pdf(db, principal, case_id)


def accounting_csv(db: Session, principal: Principal, case_id: UUID) -> str | None:
    require_private_economics_access(principal)
    case = scoped_case(db, principal, case_id)
    if case is None:
        return None
    _require_house_reconciliation_case(db, principal, case)
    reconciliation = db.scalar(
        select(DealReconciliation).where(
            DealReconciliation.organization_id == principal.organization_id,
            DealReconciliation.disposition_case_id == case.id,
            DealReconciliation.status == "approved",
        )
    )
    if reconciliation is None:
        return None
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("type", "role", "user", "amount_cents", "status"))
    writer.writerow(
        ("company_profit", "company", "", reconciliation.company_profit_cents, "approved")
    )
    users = {
        item.id: item.display_name
        for item in db.scalars(
            select(User).where(User.organization_id == principal.organization_id)
        ).all()
    }
    for payout in db.scalars(
        select(DealPayout).where(DealPayout.deal_reconciliation_id == reconciliation.id)
    ).all():
        user_name = users.get(payout.user_id, "") if payout.user_id is not None else ""
        writer.writerow(("payout", payout.role_key, user_name, payout.amount_cents, payout.status))
    return output.getvalue()


def _require_house_reconciliation_case(
    db: Session,
    principal: Principal,
    case: DispositionCase,
) -> None:
    lead = db.scalar(
        select(Lead).where(
            Lead.id == case.lead_id,
            Lead.organization_id == principal.organization_id,
        )
    )
    if lead is None or normalize_asset_class(lead.asset_class) != "house":
        raise ValueError("Financial reconciliation is currently available for House deals only.")


def case_read(
    db: Session,
    case: DispositionCase,
    principal: Principal | None = None,
) -> DispositionCaseRead:
    from app.services.disposition_packages import sanitize_public_snapshot

    may_view_private = bool(principal and can_view_private_economics(principal))
    contact = db.scalar(
        select(Contact).join(Lead, Lead.contact_id == Contact.id).where(Lead.id == case.lead_id)
    )
    property_record = db.get(Property, case.property_id)
    lead = db.get(Lead, case.lead_id)
    plan = (
        db.get(CompensationPlanVersion, case.compensation_plan_version_id)
        if case.compensation_plan_version_id is not None
        else None
    )
    mode = (
        db.get(DispositionOperatingMode, case.disposition_operating_mode_id)
        if case.disposition_operating_mode_id is not None
        else None
    )
    buyers = {
        item.id: item
        for item in db.scalars(
            select(Buyer).where(Buyer.organization_id == case.organization_id)
        ).all()
    }
    latest_proof_by_buyer: dict[UUID, BuyerProofDocument] = {}
    current_verified_proof_by_buyer: dict[UUID, BuyerProofDocument] = {}
    proof_checked_at = datetime.now(UTC)
    for proof in db.scalars(
        select(BuyerProofDocument)
        .where(
            BuyerProofDocument.organization_id == case.organization_id,
            BuyerProofDocument.deleted_at.is_(None),
        )
        .order_by(BuyerProofDocument.created_at.desc())
    ).all():
        latest_proof_by_buyer.setdefault(proof.buyer_id, proof)
        if proof.buyer_id not in current_verified_proof_by_buyer and _proof_is_current_verified(
            proof, now=proof_checked_at
        ):
            current_verified_proof_by_buyer[proof.buyer_id] = proof
    matches = db.scalars(
        select(DispositionMatch)
        .where(DispositionMatch.disposition_case_id == case.id)
        .order_by(DispositionMatch.rank)
    ).all()
    offers = db.scalars(
        select(BuyerOffer)
        .where(BuyerOffer.disposition_case_id == case.id)
        .order_by(BuyerOffer.received_at.desc())
    ).all()
    engagements = db.scalars(
        select(BuyerEngagement)
        .where(BuyerEngagement.disposition_case_id == case.id)
        .order_by(BuyerEngagement.occurred_at.desc())
    ).all()
    reconciliation = db.scalar(
        select(DealReconciliation).where(DealReconciliation.disposition_case_id == case.id)
    )
    return DispositionCaseRead(
        id=case.id,
        deal_id=case.deal_id,
        transaction_id=case.transaction_id,
        lead_id=case.lead_id,
        asset_class=normalize_asset_class(lead.asset_class if lead else None),
        seller_name=contact.legal_name if contact else "Unknown seller",
        property_address=address(property_record),
        property_type=property_record.property_type if property_record else None,
        status=case.status,
        strategy=case.strategy,
        asking_price_cents=case.asking_price_cents,
        minimum_acceptable_cents=(case.minimum_acceptable_cents if may_view_private else None),
        desired_assignment_fee_cents=(
            case.desired_assignment_fee_cents if may_view_private else None
        ),
        package_status=case.package_status,
        package_snapshot=sanitize_public_snapshot(case.package_snapshot),
        compensation_plan_label=f"{plan.name} v{plan.version_number}" if plan else "Unavailable",
        operating_mode_label=mode.name if mode else "Unavailable",
        selected_buyer_id=case.selected_buyer_id,
        backup_buyer_id=case.backup_buyer_id,
        matches=[
            MatchRead(
                id=item.id,
                buyer_id=item.buyer_id,
                buyer_name=buyers[item.buyer_id].name,
                score_basis_points=item.score_basis_points,
                score_components=item.score_components,
                qualification_status=item.qualification_status,
                recipient_status=item.recipient_status,
                rank=item.rank,
                proof_status=(
                    "verified"
                    if item.buyer_id in current_verified_proof_by_buyer
                    else latest_proof_by_buyer[item.buyer_id].status
                    if item.buyer_id in latest_proof_by_buyer
                    else "unknown"
                ),
                proof_expires_at=(
                    current_verified_proof_by_buyer[item.buyer_id].expires_at
                    if item.buyer_id in current_verified_proof_by_buyer
                    else None
                ),
                latest_proof_document_id=(
                    current_verified_proof_by_buyer[item.buyer_id].id
                    if item.buyer_id in current_verified_proof_by_buyer
                    else latest_proof_by_buyer[item.buyer_id].id
                    if item.buyer_id in latest_proof_by_buyer
                    else None
                ),
            )
            for item in matches
        ],
        offers=[offer_read(item, buyers[item.buyer_id]) for item in offers],
        engagements=[
            EngagementRead(
                id=item.id,
                buyer_id=item.buyer_id,
                buyer_name=buyers[item.buyer_id].name,
                engagement_type=item.engagement_type,
                status=item.status,
                scheduled_at=item.scheduled_at,
                occurred_at=item.occurred_at,
                notes=item.notes,
            )
            for item in engagements
        ],
        reconciliation=(
            reconciliation_read(db, reconciliation)
            if reconciliation is not None and may_view_private
            else None
        ),
        created_at=case.created_at,
    )


def reconciliation_read(db: Session, item: DealReconciliation) -> ReconciliationRead:
    users = {
        user.id: user.display_name
        for user in db.scalars(
            select(User).where(User.organization_id == item.organization_id)
        ).all()
    }
    payouts = db.scalars(
        select(DealPayout).where(DealPayout.deal_reconciliation_id == item.id)
    ).all()
    return ReconciliationRead(
        id=item.id,
        status=item.status,
        gross_revenue_cents=item.gross_revenue_cents,
        acquisition_reserve_cents=item.acquisition_reserve_cents,
        deal_deductions_cents=item.deal_deductions_cents,
        adjusted_deal_margin_cents=item.adjusted_deal_margin_cents,
        total_compensation_cents=item.total_compensation_cents,
        company_profit_cents=item.company_profit_cents,
        company_margin_basis_points=item.company_margin_basis_points,
        target_margin_basis_points=item.target_margin_basis_points,
        notes=item.notes,
        payouts=[
            PayoutRead(
                id=value.id,
                role_key=value.role_key,
                user_id=value.user_id,
                user_name=users.get(value.user_id) if value.user_id else None,
                credit_basis_points=value.credit_basis_points,
                amount_cents=value.amount_cents,
                status=value.status,
            )
            for value in payouts
        ],
        created_at=item.created_at,
    )


def offer_read(item: BuyerOffer, buyer: Buyer) -> OfferRead:
    return OfferRead(
        id=item.id,
        buyer_id=item.buyer_id,
        buyer_name=buyer.name,
        amount_cents=item.amount_cents,
        earnest_money_cents=item.earnest_money_cents,
        financing_type=item.financing_type,
        status=item.status,
        proof_document_id=item.proof_document_id,
        deposit_due_at=item.deposit_due_at,
        deposit_received_at=item.deposit_received_at,
        selected_at=item.selected_at,
        notes=item.notes,
        received_at=item.received_at,
    )


def proof_read(item: BuyerProofDocument) -> ProofDocumentRead:
    return ProofDocumentRead(
        id=item.id,
        buyer_id=item.buyer_id,
        status=item.status,
        institution_name=item.institution_name,
        verified_amount_cents=item.verified_amount_cents,
        expires_at=item.expires_at,
        file_name=item.file_name,
        content_type=item.content_type,
        file_size=item.file_size,
        storage_provider=item.storage_provider,
        malware_scan_status=item.malware_scan_status,
        retention_until=item.retention_until,
        verified_by_user_id=item.verified_by_user_id,
        verified_at=item.verified_at,
        verification_source=item.verification_source,
        notes=item.notes,
        content_url=f"/api/v1/dispositions/proof-documents/{item.id}/content",
        created_at=item.created_at,
    )


def address(item: Property | None) -> str:
    if item is None:
        return "Unknown property"
    return property_identity_label(
        street_address=item.street_address,
        city=item.city,
        state=item.state,
        postal_code=item.postal_code,
        parcel_id=item.parcel_id,
        county=item.county,
    ) or "Unknown property"


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _criteria_integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _structured_price_match(criteria: dict[str, object] | None, asking_price_cents: int) -> bool:
    if criteria is None:
        return False
    minimum = _criteria_integer(criteria.get("min_price_cents"))
    maximum = _criteria_integer(criteria.get("max_price_cents"))
    if minimum is None and maximum is None:
        return False
    return bool(
        (minimum is None or asking_price_cents >= minimum)
        and (maximum is None or asking_price_cents <= maximum)
    )


def _structured_market_match(
    criteria: dict[str, object] | None,
    property_record: Property | None,
) -> bool:
    if criteria is None or property_record is None:
        return False
    included = criteria.get("geographies")
    excluded = criteria.get("excluded_geographies")
    if not isinstance(included, list) or not included:
        return False
    if isinstance(excluded, list):
        for entry in excluded:
            if not isinstance(entry, dict):
                return False
            if entry.get("jurisdiction") == "radius":
                # Property coordinates are not canonical on the current House disposition record.
                # Unknown exclusion evidence must force review instead of silently passing.
                return False
            if _geography_matches_property(entry, property_record):
                return False
    return any(
        _geography_matches_property(entry, property_record)
        for entry in included
        if isinstance(entry, dict)
    )


def _geography_matches_property(entry: dict[object, object], property_record: Property) -> bool:
    jurisdiction = str(entry.get("jurisdiction") or "").strip().lower()
    value = _normalized_match_text(entry.get("value"))
    state = _normalized_match_text(entry.get("state"))
    property_state = _normalized_match_text(property_record.state)
    if jurisdiction == "state":
        return bool(value and value == property_state)
    if jurisdiction == "county":
        if not state or state != property_state:
            return False
        return _normalized_county(value) == _normalized_county(property_record.county)
    if jurisdiction == "city":
        return bool(
            state
            and state == property_state
            and value == _normalized_match_text(property_record.city)
        )
    if jurisdiction == "postal_code":
        requested_zip = "".join(character for character in value if character.isdigit())[:5]
        property_zip = "".join(
            character for character in (property_record.postal_code or "") if character.isdigit()
        )[:5]
        return bool(requested_zip and requested_zip == property_zip)
    # Radius entries remain review-required until canonical subject coordinates are available.
    return False


def _structured_house_type_match(
    criteria: dict[str, object] | None,
    property_record: Property | None,
) -> bool:
    if criteria is None or property_record is None:
        return False
    requested = criteria.get("property_types")
    if not isinstance(requested, list) or not requested:
        return False
    subject_type = _normalized_key(property_record.property_type)
    return bool(subject_type and subject_type in {_normalized_key(value) for value in requested})


def _structured_strategy_match(criteria: dict[str, object] | None, strategy: str) -> bool:
    if criteria is None:
        return False
    strategies = criteria.get("strategies")
    if not isinstance(strategies, list) or not strategies:
        return True
    normalized_strategy = {
        "assignment": "wholesale_assignment",
        "double_close": "double_close",
        "novation": "novation",
    }.get(_normalized_key(strategy), _normalized_key(strategy))
    return normalized_strategy in {_normalized_key(value) for value in strategies}


def _normalized_key(value: object) -> str:
    return "_".join(str(value or "").strip().lower().replace("-", " ").split())


def _normalized_match_text(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _normalized_county(value: object) -> str:
    normalized = _normalized_match_text(value)
    return normalized.removesuffix(" county").strip()
