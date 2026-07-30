import csv
import hashlib
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    AuditEvent,
    Campaign,
    CampaignCost,
    Prospect,
    ProspectCallingBatch,
    ProspectCallingBatchEntry,
    ProspectContactPoint,
    ProspectHandoff,
    ProspectImportBatch,
    ProspectImportMapping,
    ProspectImportRow,
    ProspectSourceMembership,
    ProspectSuppressionCheck,
    ProspectingAttempt,
    ProspectingCohort,
    ProspectingScriptVersion,
    ProspectingWorkSession,
    SuppressionRecord,
    User,
)
from app.schemas.campaign_management import (
    CampaignCostCreate,
    CampaignCostRead,
    CampaignManagementOverview,
    CampaignQualityRead,
    ProspectCallingBatchCreate,
    ProspectCallingBatchEntryRead,
    ProspectCallingBatchRead,
    ProspectContactPointRead,
    ProspectImportBatchRead,
    ProspectImportMappingCreate,
    ProspectImportMappingRead,
    ProspectImportPreview,
    ProspectImportPreviewRow,
    ProspectImportRequest,
    ProspectImportRowRead,
    ProspectSourceMembershipRead,
    ProspectingCohortCreate,
    ProspectingCohortRead,
    ProspectingWorkSessionCreate,
    ProspectingWorkSessionRead,
)
from app.services.acquisition_operations import (
    list_campaigns,
    list_users,
    normalize_prospect_phone,
)
from app.services.property_validation import canonical_address_key
from app.services.prospecting_measurement import (
    ProspectingCostBreakdown,
    cost_per_accepted_warm_lead_cents,
    is_accepted_warm_lead,
    labor_cost_cents,
)

MAX_IMPORT_ROWS = 10_000
PROPSTREAM_PRESET_NAME = "PropStream Standard Export"
PROPSTREAM_FIELD_MAPPING = {
    "source_record_key": "Property ID",
    "legal_first_name": "Owner 1 First Name",
    "legal_last_name": "Owner 1 Last Name",
    "phone": "Phone 1",
    "phone_2": "Phone 2",
    "phone_3": "Phone 3",
    "email": "Email 1",
    "email_2": "Email 2",
    "email_3": "Email 3",
    "street_address": "Property Address",
    "city": "Property City",
    "state_code": "Property State",
    "postal_code": "Property Zip",
}
DNC_BLOCKED_VALUES = {
    "1",
    "blocked",
    "dnc",
    "do not call",
    "do_not_call",
    "listed",
    "registered",
    "true",
    "yes",
}


@dataclass
class PreparedContactPoint:
    contact_type: str
    value: str
    normalized_value: str
    rank: int
    source_field: str


@dataclass
class PreparedImportRow:
    row_number: int
    raw_data: dict[str, str]
    normalized_data: dict[str, Any]
    contact_points: list[PreparedContactPoint]
    relationship_state: str
    status: str
    validation_errors: list[str]
    eligibility_reasons: list[str]
    duplicate_prospect_id: UUID | None
    company_suppression_status: str
    company_suppression_evidence: dict[str, object]
    dnc_status: str


def get_campaign_management_overview(
    db: Session,
    principal: Principal,
) -> CampaignManagementOverview:
    campaigns = list_campaigns(db, principal)
    return CampaignManagementOverview(
        users=list_users(db, principal, manageable=True),
        campaigns=campaigns,
        mappings=list_import_mappings(db, principal),
        import_batches=list_import_batches(db, principal),
        source_memberships=list_source_memberships(db, principal),
        contact_points=list_prospect_contact_points(db, principal),
        cohorts=list_prospecting_cohorts(db, principal),
        work_sessions=list_prospecting_work_sessions(db, principal),
        costs=list_campaign_costs(db, principal),
        calling_batches=list_calling_batches(db, principal),
        quality=[campaign_quality_read(db, campaign.id) for campaign in campaigns],
    )


def create_import_mapping(
    db: Session,
    principal: Principal,
    payload: ProspectImportMappingCreate,
) -> ProspectImportMappingRead:
    mapping = ProspectImportMapping(
        organization_id=principal.organization_id,
        name=payload.name.strip(),
        source_name=clean_text(payload.source_name),
        field_mapping={key: value.strip() for key, value in payload.field_mapping.items()},
        default_values={key: value.strip() for key, value in payload.default_values.items()},
        created_by_user_id=principal.user_id,
        is_active=True,
    )
    db.add(mapping)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("An import mapping with this name already exists.") from exc
    add_audit(
        db,
        principal,
        action="campaign_management.import_mapping_create",
        entity_type="prospect_import_mapping",
        entity_id=mapping.id,
        new={"name": mapping.name, "field_mapping": mapping.field_mapping},
        reason="Reusable prospect import mapping created",
    )
    db.commit()
    return import_mapping_read(db, mapping)


def create_propstream_import_preset(
    db: Session,
    principal: Principal,
) -> ProspectImportMappingRead:
    existing = db.scalar(
        select(ProspectImportMapping).where(
            ProspectImportMapping.organization_id == principal.organization_id,
            ProspectImportMapping.name == PROPSTREAM_PRESET_NAME,
            ProspectImportMapping.is_active.is_(True),
        )
    )
    if existing is not None:
        return import_mapping_read(db, existing)
    return create_import_mapping(
        db,
        principal,
        ProspectImportMappingCreate(
            name=PROPSTREAM_PRESET_NAME,
            source_name="PropStream",
            field_mapping=PROPSTREAM_FIELD_MAPPING,
            default_values={},
        ),
    )


def list_import_mappings(
    db: Session,
    principal: Principal,
) -> list[ProspectImportMappingRead]:
    mappings = db.scalars(
        select(ProspectImportMapping)
        .where(
            ProspectImportMapping.organization_id == principal.organization_id,
            ProspectImportMapping.is_active.is_(True),
        )
        .order_by(ProspectImportMapping.name)
    ).all()
    return [import_mapping_read(db, mapping) for mapping in mappings]


def import_mapping_read(db: Session, mapping: ProspectImportMapping) -> ProspectImportMappingRead:
    creator = db.get(User, mapping.created_by_user_id)
    return ProspectImportMappingRead(
        id=mapping.id,
        name=mapping.name,
        source_name=mapping.source_name,
        field_mapping=mapping.field_mapping,
        default_values=mapping.default_values,
        created_by_user_id=mapping.created_by_user_id,
        created_by_name=creator.display_name if creator else "Unknown user",
        is_active=mapping.is_active,
        created_at=mapping.created_at,
    )


def validate_prospect_import(
    db: Session,
    principal: Principal,
    payload: ProspectImportRequest,
) -> ProspectImportPreview:
    _, mapping, _, _ = validate_import_context(db, principal, payload)
    headers, prepared_rows = prepare_import_rows(db, principal, payload, mapping)
    return import_preview(headers, prepared_rows)


def create_prospect_import(
    db: Session,
    principal: Principal,
    payload: ProspectImportRequest,
) -> ProspectImportBatchRead:
    campaign, mapping, assignee, cohort = validate_import_context(db, principal, payload)
    file_sha256 = hashlib.sha256(payload.csv_content.encode("utf-8")).hexdigest()
    previous_batch = db.scalar(
        select(ProspectImportBatch).where(
            ProspectImportBatch.organization_id == principal.organization_id,
            ProspectImportBatch.campaign_id == campaign.id,
            ProspectImportBatch.file_sha256 == file_sha256,
            ProspectImportBatch.status == "complete",
        )
    )
    if previous_batch is not None:
        raise ValueError("This exact file has already been imported into the campaign.")
    _, prepared_rows = prepare_import_rows(db, principal, payload, mapping)
    counts = import_counts(prepared_rows)
    if not prepared_rows:
        raise ValueError("The CSV does not contain any data rows.")

    now = datetime.now(UTC)
    batch = ProspectImportBatch(
        organization_id=principal.organization_id,
        campaign_id=campaign.id,
        mapping_id=mapping.id,
        cohort_id=cohort.id if cohort else None,
        default_assignee_user_id=assignee.id if assignee else None,
        imported_by_user_id=principal.user_id,
        file_name=payload.file_name.strip(),
        file_sha256=file_sha256,
        source_name=clean_text(mapping.source_name) or "CSV import",
        source_profile=payload.source_profile,
        source_export_id=clean_text(payload.source_export_id),
        source_list_id=clean_text(payload.source_list_id),
        source_list_name=clean_text(payload.source_list_name),
        source_exported_at=payload.source_exported_at,
        source_filters=payload.source_filters,
        status="processing",
        total_rows=counts["total_rows"],
        valid_rows=counts["valid_rows"],
        imported_rows=0,
        matched_existing_rows=0,
        invalid_rows=counts["invalid_rows"],
        duplicate_rows=counts["duplicate_rows"],
        suppressed_rows=counts["suppressed_rows"],
        review_required_rows=counts["review_required_rows"],
        completed_at=None,
    )
    db.add(batch)
    db.flush()

    imported_rows = 0
    matched_existing_rows = 0
    for prepared in prepared_rows:
        row_status = prepared.status
        prospect = None
        if prepared.status in {"valid", "suppressed", "review_required"}:
            prospect = prospect_from_import(
                principal,
                campaign,
                batch,
                assignee,
                prepared,
                file_sha256,
            )
            db.add(prospect)
            db.flush()
            imported_rows += 1
            row_status = f"imported_{prepared.status}"
        elif prepared.status == "duplicate" and prepared.duplicate_prospect_id:
            prospect = db.get(Prospect, prepared.duplicate_prospect_id)
            if prospect is not None:
                matched_existing_rows += 1
                row_status = "matched_existing"
                refresh_untouched_prospect(prospect, prepared)
        import_row = ProspectImportRow(
            organization_id=principal.organization_id,
            import_batch_id=batch.id,
            prospect_id=prospect.id if prospect else None,
            duplicate_prospect_id=prepared.duplicate_prospect_id,
            source_membership_id=None,
            row_number=prepared.row_number,
            status=row_status,
            raw_data=prepared.raw_data,
            normalized_data=prepared.normalized_data,
            validation_errors=prepared.validation_errors,
            eligibility_reasons=prepared.eligibility_reasons,
        )
        db.add(import_row)
        db.flush()
        if prospect is not None:
            membership = upsert_source_membership(
                db,
                principal,
                campaign,
                cohort,
                batch,
                prospect,
                prepared,
                now,
            )
            import_row.source_membership_id = membership.id
            upsert_prospect_contact_points(
                db,
                principal,
                prospect,
                membership,
                prepared,
                now,
            )
            add_suppression_checks(db, principal, import_row, prospect, prepared, now)

    batch.status = "complete"
    batch.imported_rows = imported_rows
    batch.matched_existing_rows = matched_existing_rows
    batch.completed_at = now
    add_audit(
        db,
        principal,
        action="campaign_management.prospect_import_complete",
        entity_type="prospect_import_batch",
        entity_id=batch.id,
        new={
            "campaign_id": str(campaign.id),
            "file_name": batch.file_name,
            "total_rows": batch.total_rows,
            "imported_rows": batch.imported_rows,
            "matched_existing_rows": batch.matched_existing_rows,
            "cohort_id": str(batch.cohort_id) if batch.cohort_id else None,
            "source_name": batch.source_name,
            "source_export_id": batch.source_export_id,
            "source_list_id": batch.source_list_id,
            "invalid_rows": batch.invalid_rows,
            "duplicate_rows": batch.duplicate_rows,
            "suppressed_rows": batch.suppressed_rows,
            "review_required_rows": batch.review_required_rows,
        },
        reason="Prospect CSV imported with row-level validation",
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("The import conflicted with an existing prospect record.") from exc
    return import_batch_read(db, batch)


def validate_import_context(
    db: Session,
    principal: Principal,
    payload: ProspectImportRequest,
) -> tuple[Campaign, ProspectImportMapping, User | None, ProspectingCohort | None]:
    campaign = db.scalar(
        select(Campaign).where(
            Campaign.organization_id == principal.organization_id,
            Campaign.id == payload.campaign_id,
        )
    )
    if campaign is None:
        raise ValueError("Select a Stonegate campaign.")
    mapping = db.scalar(
        select(ProspectImportMapping).where(
            ProspectImportMapping.organization_id == principal.organization_id,
            ProspectImportMapping.id == payload.mapping_id,
            ProspectImportMapping.is_active.is_(True),
        )
    )
    if mapping is None:
        raise ValueError("Select an active import mapping.")
    cohort = None
    if payload.cohort_id:
        cohort = db.scalar(
            select(ProspectingCohort).where(
                ProspectingCohort.organization_id == principal.organization_id,
                ProspectingCohort.id == payload.cohort_id,
                ProspectingCohort.campaign_id == campaign.id,
            )
        )
        if cohort is None:
            raise ValueError("Import cohort must belong to the selected campaign.")
    assignee = None
    if payload.default_assignee_user_id:
        assignee = active_user(db, principal.organization_id, payload.default_assignee_user_id)
        if assignee is None:
            raise ValueError("The default assignee must be an active workspace user.")
    return campaign, mapping, assignee, cohort


def prepare_import_rows(
    db: Session,
    principal: Principal,
    payload: ProspectImportRequest,
    mapping: ProspectImportMapping,
) -> tuple[list[str], list[PreparedImportRow]]:
    headers, rows = parse_csv(payload.csv_content)
    missing_headers = sorted(set(mapping.field_mapping.values()) - set(headers))
    if missing_headers:
        raise ValueError(f"CSV is missing mapped columns: {', '.join(missing_headers)}.")

    existing_prospects = db.scalars(
        select(Prospect).where(Prospect.organization_id == principal.organization_id)
    ).all()
    phone_matches = {
        prospect.normalized_phone: prospect.id
        for prospect in existing_prospects
        if prospect.normalized_phone
    }
    email_matches = {
        prospect.normalized_email: prospect.id
        for prospect in existing_prospects
        if prospect.normalized_email
    }
    contact_points = db.scalars(
        select(ProspectContactPoint).where(
            ProspectContactPoint.organization_id == principal.organization_id
        )
    ).all()
    for contact_point in contact_points:
        target = phone_matches if contact_point.contact_type == "phone" else email_matches
        target.setdefault(contact_point.normalized_value, contact_point.prospect_id)
    address_matches = {
        prospect.normalized_address_key: prospect.id
        for prospect in existing_prospects
        if prospect.normalized_address_key
    }
    source_matches = {
        prospect.source_record_key: prospect.id
        for prospect in existing_prospects
        if prospect.campaign_id == payload.campaign_id and prospect.source_record_key
    }
    source_name = clean_text(mapping.source_name) or "CSV import"
    memberships = db.scalars(
        select(ProspectSourceMembership).where(
            ProspectSourceMembership.organization_id == principal.organization_id,
            ProspectSourceMembership.source_name == source_name,
            ProspectSourceMembership.source_record_key.is_not(None),
        )
    ).all()
    for membership in memberships:
        if membership.source_record_key:
            source_matches.setdefault(membership.source_record_key, membership.prospect_id)
    relationship_states = prospect_relationship_states(db, existing_prospects)
    active_voice_suppressions = active_company_suppressions(db, principal.organization_id)
    seen_identities: set[str] = set()
    prepared_rows: list[PreparedImportRow] = []
    for row_number, raw in enumerate(rows, start=2):
        prepared = prepare_row(
            raw,
            row_number,
            mapping,
            phone_matches,
            email_matches,
            address_matches,
            source_matches,
            active_voice_suppressions,
            seen_identities,
            relationship_states,
        )
        prepared_rows.append(prepared)
    return headers, prepared_rows


def parse_csv(content: str) -> tuple[list[str], list[dict[str, str]]]:
    cleaned = content.lstrip("\ufeff")
    try:
        dialect = csv.Sniffer().sniff(cleaned[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(cleaned, newline=""), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("The CSV requires a header row.")
    headers = [header.strip() for header in reader.fieldnames if header is not None]
    if len(headers) != len(set(headers)):
        raise ValueError("CSV column names must be unique.")
    parsed: list[dict[str, str]] = []
    for source_row in reader:
        row = {
            str(key).strip(): str(value or "").strip()
            for key, value in source_row.items()
            if key is not None
        }
        if not any(row.values()):
            continue
        parsed.append(row)
        if len(parsed) > MAX_IMPORT_ROWS:
            raise ValueError(f"Imports are limited to {MAX_IMPORT_ROWS:,} data rows.")
    return headers, parsed


def prepare_row(
    raw: dict[str, str],
    row_number: int,
    mapping: ProspectImportMapping,
    phone_matches: dict[str, UUID],
    email_matches: dict[str, UUID],
    address_matches: dict[str, UUID],
    source_matches: dict[str, UUID],
    active_voice_suppressions: dict[str, SuppressionRecord],
    seen_identities: set[str],
    relationship_states: dict[UUID, str],
) -> PreparedImportRow:
    values = {
        field: clean_text(raw.get(column)) or clean_text(mapping.default_values.get(field))
        for field, column in mapping.field_mapping.items()
    }
    for field, default in mapping.default_values.items():
        values.setdefault(field, clean_text(default))
    errors: list[str] = []
    reasons: list[str] = []
    legal_name = values.get("legal_name") or " ".join(
        part
        for part in (
            values.get("legal_first_name"),
            values.get("legal_last_name"),
        )
        if part
    ).strip()
    if not legal_name:
        errors.append("Seller or owner name is required.")
    elif len(legal_name) > 255:
        errors.append("Seller or owner name exceeds 255 characters.")

    contact_points: list[PreparedContactPoint] = []
    for rank, field in enumerate(("phone", "phone_2", "phone_3"), start=1):
        phone_value = values.get(field)
        if not phone_value:
            continue
        if len(phone_value) > 80:
            reasons.append(f"Phone {rank} exceeds 80 characters and was skipped.")
            continue
        try:
            normalized_contact = normalize_prospect_phone(phone_value)
        except ValueError:
            reasons.append(f"Phone {rank} is invalid and was skipped.")
            continue
        if normalized_contact and all(
            point.normalized_value != normalized_contact
            for point in contact_points
            if point.contact_type == "phone"
        ):
            contact_points.append(
                PreparedContactPoint(
                    "phone",
                    phone_value,
                    normalized_contact,
                    rank,
                    field,
                )
            )
    for rank, field in enumerate(("email", "email_2", "email_3"), start=1):
        email_value = values.get(field)
        if not email_value:
            continue
        normalized_contact = email_value.lower()
        if (
            len(normalized_contact) > 320
            or "@" not in normalized_contact
            or normalized_contact.startswith("@")
        ):
            reasons.append(f"Email {rank} is invalid and was skipped.")
            continue
        if all(
            point.normalized_value != normalized_contact
            for point in contact_points
            if point.contact_type == "email"
        ):
            contact_points.append(
                PreparedContactPoint(
                    "email",
                    email_value,
                    normalized_contact,
                    rank,
                    field,
                )
            )
    primary_phone = next(
        (point for point in contact_points if point.contact_type == "phone"),
        None,
    )
    primary_email = next(
        (point for point in contact_points if point.contact_type == "email"),
        None,
    )
    phone = primary_phone.value if primary_phone else None
    normalized_phone = primary_phone.normalized_value if primary_phone else None
    email = primary_email.value if primary_email else None
    normalized_email = primary_email.normalized_value if primary_email else None
    if not contact_points:
        errors.append("A valid phone or email is required.")

    street = values.get("street_address")
    city = values.get("city")
    state = values.get("state_code")
    postal = values.get("postal_code")
    address_values = (street, city, state, postal)
    normalized_address = None
    address_status = "missing"
    if any(address_values) and not all(address_values):
        errors.append("Property address is incomplete.")
        address_status = "invalid"
    elif all(address_values):
        if len(street or "") > 255 or len(city or "") > 120 or len(postal or "") > 20:
            errors.append("Property address contains an overlong value.")
            address_status = "invalid"
        elif len(state or "") != 2:
            errors.append("Property state must use a two-letter code.")
            address_status = "invalid"
        else:
            normalized_address = canonical_address_key(
                street or "", city or "", state or "", postal or ""
            )
            address_status = "normalized"
    if values.get("source_record_key") and len(values.get("source_record_key") or "") > 255:
        errors.append("Source record key exceeds 255 characters.")

    normalized: dict[str, Any] = {
        "source_record_key": values.get("source_record_key"),
        "legal_name": legal_name,
        "phone": phone,
        "normalized_phone": normalized_phone,
        "email": email,
        "normalized_email": normalized_email,
        "street_address": street,
        "city": city,
        "state_code": state.upper() if state else None,
        "postal_code": postal,
        "normalized_address_key": normalized_address,
        "address_validation_status": address_status,
        "dnc_status": values.get("dnc_status"),
        "contact_points": [
            {
                "contact_type": point.contact_type,
                "value": point.value,
                "normalized_value": point.normalized_value,
                "rank": point.rank,
                "source_field": point.source_field,
            }
            for point in contact_points
        ],
    }

    duplicate_id = find_duplicate(
        normalized,
        contact_points,
        phone_matches,
        email_matches,
        address_matches,
        source_matches,
    )
    identity_keys = {
        value
        for value in (
            *(
                f"{point.contact_type}:{point.normalized_value}"
                for point in contact_points
            ),
            f"address:{normalized_address}" if normalized_address else None,
            (
                f"source:{values.get('source_record_key')}"
                if values.get("source_record_key")
                else None
            ),
        )
        if value
    }
    within_file_duplicate = not errors and bool(identity_keys.intersection(seen_identities))
    if not errors:
        seen_identities.update(identity_keys)

    company_record = active_voice_suppressions.get(normalized_phone or "")
    company_status = "blocked" if company_record else "clear"
    company_evidence: dict[str, object] = {
        "matched": bool(company_record),
        "suppression_record_id": str(company_record.id) if company_record else None,
        "reason": company_record.reason if company_record else None,
    }
    dnc_raw = (values.get("dnc_status") or "").strip().casefold()
    dnc_status = "blocked" if dnc_raw in DNC_BLOCKED_VALUES else "clear"

    if errors:
        status = "invalid"
    elif duplicate_id or within_file_duplicate:
        status = "duplicate"
        reasons.append(
            "Exact phone, email, property, or source identifier matches another prospect."
        )
    elif company_status == "blocked" or dnc_status == "blocked":
        status = "suppressed"
        if company_status == "blocked":
            reasons.append("Phone matches Stonegate's active company suppression list.")
        if dnc_status == "blocked":
            reasons.append("Imported source identifies the phone as Do Not Call.")
    elif not normalized_phone:
        status = "review_required"
        reasons.append("No valid phone is available for calling.")
    else:
        status = "valid"

    relationship_state = (
        relationship_states.get(duplicate_id, "prior_contact")
        if duplicate_id
        else "duplicate_in_file"
        if within_file_duplicate
        else "untouched"
    )
    normalized["relationship_state"] = relationship_state
    return PreparedImportRow(
        row_number=row_number,
        raw_data=raw,
        normalized_data=normalized,
        contact_points=contact_points,
        relationship_state=relationship_state,
        status=status,
        validation_errors=errors,
        eligibility_reasons=reasons,
        duplicate_prospect_id=duplicate_id,
        company_suppression_status=company_status,
        company_suppression_evidence=company_evidence,
        dnc_status=dnc_status,
    )


def find_duplicate(
    normalized: dict[str, Any],
    contact_points: list[PreparedContactPoint],
    phone_matches: dict[str, UUID],
    email_matches: dict[str, UUID],
    address_matches: dict[str, UUID],
    source_matches: dict[str, UUID],
) -> UUID | None:
    candidates: list[tuple[str | None, dict[str, UUID]]] = [
        (string_value(normalized.get("source_record_key")), source_matches),
    ]
    candidates.extend(
        (
            point.normalized_value,
            phone_matches if point.contact_type == "phone" else email_matches,
        )
        for point in contact_points
    )
    candidates.append(
        (string_value(normalized.get("normalized_address_key")), address_matches)
    )
    for value, matches in candidates:
        if value and value in matches:
            return matches[value]
    return None


def prospect_from_import(
    principal: Principal,
    campaign: Campaign,
    batch: ProspectImportBatch,
    assignee: User | None,
    prepared: PreparedImportRow,
    file_sha256: str,
) -> Prospect:
    data = prepared.normalized_data
    source_key = data.get("source_record_key") or f"{file_sha256[:16]}:{prepared.row_number}"
    call_eligibility = {
        "valid": "eligible",
        "suppressed": "blocked",
        "review_required": "review_required",
    }[prepared.status]
    return Prospect(
        organization_id=principal.organization_id,
        campaign_id=campaign.id,
        territory_id=campaign.territory_id,
        assigned_user_id=assignee.id if assignee else None,
        converted_lead_id=None,
        import_batch_id=batch.id,
        source_record_key=source_key,
        status="new",
        legal_name=data.get("legal_name") or "Unknown owner",
        phone=data.get("phone"),
        normalized_phone=data.get("normalized_phone"),
        email=data.get("email"),
        normalized_email=data.get("normalized_email"),
        street_address=data.get("street_address"),
        city=data.get("city"),
        state_code=data.get("state_code"),
        postal_code=data.get("postal_code"),
        normalized_address_key=data.get("normalized_address_key"),
        suppression_status=(
            "suppressed"
            if call_eligibility == "blocked"
            else "clear"
            if call_eligibility == "eligible"
            else "review_required"
        ),
        suppression_checked_at=datetime.now(UTC),
        phone_validation_status="valid" if data.get("normalized_phone") else "missing",
        address_validation_status=data.get("address_validation_status") or "missing",
        call_eligibility=call_eligibility,
        last_contacted_at=None,
        source_payload=prepared.raw_data,
    )


def prospect_relationship_states(
    db: Session,
    prospects: Sequence[Prospect],
) -> dict[UUID, str]:
    prospect_ids = [prospect.id for prospect in prospects]
    entry_rows = (
        db.execute(
            select(
                ProspectCallingBatchEntry.prospect_id,
                ProspectCallingBatchEntry.status,
                ProspectCallingBatchEntry.next_attempt_at,
            ).where(ProspectCallingBatchEntry.prospect_id.in_(prospect_ids))
        ).all()
        if prospect_ids
        else []
    )
    entries_by_prospect: dict[UUID, list[tuple[str, datetime | None]]] = {}
    for prospect_id, status, next_attempt_at in entry_rows:
        entries_by_prospect.setdefault(prospect_id, []).append((status, next_attempt_at))
    states: dict[UUID, str] = {}
    for prospect in prospects:
        entries = entries_by_prospect.get(prospect.id, [])
        if prospect.converted_lead_id:
            state = "existing_lead"
        elif any(next_attempt_at is not None for _, next_attempt_at in entries):
            state = "callback_due"
        elif any(
            status in {"in_progress", "handoff_pending", "needs_correction"}
            for status, _ in entries
        ) or prospect.status in {"warm_handoff", "handoff_correction"}:
            state = "active_conversation"
        elif prospect.last_contacted_at is not None or entries:
            state = "prior_contact"
        else:
            state = "untouched"
        states[prospect.id] = state
    return states


def refresh_untouched_prospect(
    prospect: Prospect,
    prepared: PreparedImportRow,
) -> None:
    if prepared.relationship_state != "untouched":
        return
    data = prepared.normalized_data
    if not prospect.phone and data.get("normalized_phone"):
        prospect.phone = string_value(data.get("phone"))
        prospect.normalized_phone = string_value(data.get("normalized_phone"))
        prospect.phone_validation_status = "valid"
        if prospect.call_eligibility == "review_required":
            prospect.call_eligibility = "eligible"
    if not prospect.email and data.get("normalized_email"):
        prospect.email = string_value(data.get("email"))
        prospect.normalized_email = string_value(data.get("normalized_email"))
    for field in ("street_address", "city", "state_code", "postal_code"):
        if not getattr(prospect, field):
            setattr(prospect, field, string_value(data.get(field)))
    if not prospect.normalized_address_key:
        prospect.normalized_address_key = string_value(data.get("normalized_address_key"))
        prospect.address_validation_status = (
            string_value(data.get("address_validation_status")) or "missing"
        )


def upsert_source_membership(
    db: Session,
    principal: Principal,
    campaign: Campaign,
    cohort: ProspectingCohort | None,
    batch: ProspectImportBatch,
    prospect: Prospect,
    prepared: PreparedImportRow,
    seen_at: datetime,
) -> ProspectSourceMembership:
    source_list_key = (
        batch.source_list_id
        or normalized_source_list_key(batch.source_list_name)
        or batch.source_export_id
        or f"campaign:{campaign.id}"
    )
    membership = db.scalar(
        select(ProspectSourceMembership).where(
            ProspectSourceMembership.prospect_id == prospect.id,
            ProspectSourceMembership.source_name == batch.source_name,
            ProspectSourceMembership.source_list_key == source_list_key,
        )
    )
    source_metadata = {
        "source_export_id": batch.source_export_id,
        "source_list_id": batch.source_list_id,
        "source_list_name": batch.source_list_name,
        "source_exported_at": (
            batch.source_exported_at.isoformat() if batch.source_exported_at else None
        ),
        "source_filters": batch.source_filters,
        "latest_file_name": batch.file_name,
        "latest_row_number": prepared.row_number,
    }
    if membership is None:
        membership = ProspectSourceMembership(
            organization_id=principal.organization_id,
            prospect_id=prospect.id,
            campaign_id=campaign.id,
            cohort_id=cohort.id if cohort else None,
            first_import_batch_id=batch.id,
            latest_import_batch_id=batch.id,
            source_name=batch.source_name,
            source_profile=batch.source_profile,
            source_record_key=string_value(
                prepared.normalized_data.get("source_record_key")
            ),
            source_list_key=source_list_key,
            source_list_name=batch.source_list_name,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
            appearance_count=1,
            relationship_state_at_latest_import=prepared.relationship_state,
            source_metadata=source_metadata,
        )
        db.add(membership)
    else:
        membership.latest_import_batch_id = batch.id
        membership.campaign_id = campaign.id
        membership.cohort_id = cohort.id if cohort else membership.cohort_id
        membership.source_profile = batch.source_profile
        membership.source_record_key = (
            string_value(prepared.normalized_data.get("source_record_key"))
            or membership.source_record_key
        )
        membership.source_list_name = batch.source_list_name or membership.source_list_name
        membership.last_seen_at = seen_at
        membership.appearance_count += 1
        membership.relationship_state_at_latest_import = prepared.relationship_state
        membership.source_metadata = source_metadata
    db.flush()
    return membership


def upsert_prospect_contact_points(
    db: Session,
    principal: Principal,
    prospect: Prospect,
    membership: ProspectSourceMembership,
    prepared: PreparedImportRow,
    seen_at: datetime,
) -> None:
    existing = {
        (contact.contact_type, contact.normalized_value): contact
        for contact in db.scalars(
            select(ProspectContactPoint).where(
                ProspectContactPoint.organization_id == principal.organization_id,
                ProspectContactPoint.prospect_id == prospect.id,
            )
        ).all()
    }
    for point in prepared.contact_points:
        key = (point.contact_type, point.normalized_value)
        is_primary = (
            prospect.normalized_phone == point.normalized_value
            if point.contact_type == "phone"
            else prospect.normalized_email == point.normalized_value
        )
        contact = existing.get(key)
        metadata = {
            "source_field": point.source_field,
            "source_name": membership.source_name,
            "source_list_key": membership.source_list_key,
        }
        if contact is None:
            db.add(
                ProspectContactPoint(
                    organization_id=principal.organization_id,
                    prospect_id=prospect.id,
                    source_membership_id=membership.id,
                    contact_type=point.contact_type,
                    value=point.value,
                    normalized_value=point.normalized_value,
                    rank=point.rank,
                    is_primary=is_primary,
                    validation_status="valid",
                    first_seen_at=seen_at,
                    last_seen_at=seen_at,
                    contact_metadata=metadata,
                )
            )
        else:
            contact.source_membership_id = membership.id
            contact.value = point.value
            contact.rank = min(contact.rank, point.rank)
            contact.is_primary = contact.is_primary or is_primary
            contact.validation_status = "valid"
            contact.last_seen_at = seen_at
            contact.contact_metadata = metadata


def normalized_source_list_key(value: str | None) -> str | None:
    cleaned = clean_text(value)
    if not cleaned:
        return None
    return "-".join(cleaned.casefold().split())[:255]


def add_suppression_checks(
    db: Session,
    principal: Principal,
    import_row: ProspectImportRow,
    prospect: Prospect,
    prepared: PreparedImportRow,
    checked_at: datetime,
) -> None:
    db.add(
        ProspectSuppressionCheck(
            organization_id=principal.organization_id,
            import_row_id=import_row.id,
            prospect_id=prospect.id,
            check_type="company_suppression",
            channel="voice",
            normalized_value=prospect.normalized_phone,
            status=prepared.company_suppression_status,
            source="stonegate_suppression_records",
            evidence=prepared.company_suppression_evidence,
            checked_at=checked_at,
        )
    )


def import_preview(
    headers: list[str],
    rows: list[PreparedImportRow],
) -> ProspectImportPreview:
    counts = import_counts(rows)
    return ProspectImportPreview(
        headers=headers,
        **counts,
        eligible_rows=sum(row.status == "valid" for row in rows),
        can_import=bool(rows)
        and any(
            row.status in {"valid", "suppressed", "review_required"}
            or (row.status == "duplicate" and row.duplicate_prospect_id is not None)
            for row in rows
        ),
        rows=[prepared_row_preview(row) for row in rows[:200]],
    )


def import_counts(rows: list[PreparedImportRow]) -> dict[str, int]:
    return {
        "total_rows": len(rows),
        "valid_rows": sum(row.status in {"valid", "suppressed", "review_required"} for row in rows),
        "invalid_rows": sum(row.status == "invalid" for row in rows),
        "duplicate_rows": sum(row.status == "duplicate" for row in rows),
        "suppressed_rows": sum(row.status == "suppressed" for row in rows),
        "review_required_rows": sum(row.status == "review_required" for row in rows),
    }


def prepared_row_preview(row: PreparedImportRow) -> ProspectImportPreviewRow:
    data = row.normalized_data
    return ProspectImportPreviewRow(
        row_number=row.row_number,
        status=row.status,
        legal_name=data.get("legal_name"),
        phone=data.get("phone"),
        property_address=property_address(data),
        validation_errors=row.validation_errors,
        eligibility_reasons=row.eligibility_reasons,
        duplicate_prospect_id=row.duplicate_prospect_id,
        relationship_state=row.relationship_state,
        contact_point_count=len(row.contact_points),
    )


def list_import_batches(
    db: Session,
    principal: Principal,
) -> list[ProspectImportBatchRead]:
    batches = db.scalars(
        select(ProspectImportBatch)
        .where(ProspectImportBatch.organization_id == principal.organization_id)
        .order_by(ProspectImportBatch.created_at.desc())
        .limit(50)
    ).all()
    return [import_batch_read(db, batch) for batch in batches]


def import_batch_read(db: Session, batch: ProspectImportBatch) -> ProspectImportBatchRead:
    campaign = db.get(Campaign, batch.campaign_id)
    cohort = db.get(ProspectingCohort, batch.cohort_id) if batch.cohort_id else None
    mapping = db.get(ProspectImportMapping, batch.mapping_id)
    assignee = (
        db.get(User, batch.default_assignee_user_id) if batch.default_assignee_user_id else None
    )
    importer = db.get(User, batch.imported_by_user_id)
    rows = db.scalars(
        select(ProspectImportRow)
        .where(ProspectImportRow.import_batch_id == batch.id)
        .order_by(ProspectImportRow.row_number)
        .limit(200)
    ).all()
    return ProspectImportBatchRead(
        id=batch.id,
        campaign_id=batch.campaign_id,
        campaign_name=campaign.name if campaign else "Unknown campaign",
        cohort_id=batch.cohort_id,
        cohort_name=cohort.name if cohort else None,
        mapping_id=batch.mapping_id,
        mapping_name=mapping.name if mapping else "Unknown mapping",
        default_assignee_user_id=batch.default_assignee_user_id,
        default_assignee_name=assignee.display_name if assignee else None,
        imported_by_user_id=batch.imported_by_user_id,
        imported_by_name=importer.display_name if importer else "Unknown user",
        file_name=batch.file_name,
        file_sha256=batch.file_sha256,
        source_name=batch.source_name,
        source_profile=batch.source_profile,
        source_export_id=batch.source_export_id,
        source_list_id=batch.source_list_id,
        source_list_name=batch.source_list_name,
        source_exported_at=batch.source_exported_at,
        source_filters=batch.source_filters,
        status=batch.status,
        total_rows=batch.total_rows,
        valid_rows=batch.valid_rows,
        imported_rows=batch.imported_rows,
        matched_existing_rows=batch.matched_existing_rows,
        invalid_rows=batch.invalid_rows,
        duplicate_rows=batch.duplicate_rows,
        suppressed_rows=batch.suppressed_rows,
        review_required_rows=batch.review_required_rows,
        completed_at=batch.completed_at,
        created_at=batch.created_at,
        rows=[import_row_read(row) for row in rows],
    )


def import_row_read(row: ProspectImportRow) -> ProspectImportRowRead:
    data = row.normalized_data
    contact_points = data.get("contact_points")
    return ProspectImportRowRead(
        id=row.id,
        row_number=row.row_number,
        status=row.status,
        prospect_id=row.prospect_id,
        duplicate_prospect_id=row.duplicate_prospect_id,
        source_membership_id=row.source_membership_id,
        relationship_state=string_value(data.get("relationship_state")) or "unknown",
        contact_point_count=len(contact_points) if isinstance(contact_points, list) else 0,
        legal_name=string_value(data.get("legal_name")),
        phone=string_value(data.get("phone")),
        property_address=property_address(data),
        validation_errors=row.validation_errors,
        eligibility_reasons=row.eligibility_reasons,
    )


def list_source_memberships(
    db: Session,
    principal: Principal,
) -> list[ProspectSourceMembershipRead]:
    memberships = db.scalars(
        select(ProspectSourceMembership)
        .where(ProspectSourceMembership.organization_id == principal.organization_id)
        .order_by(ProspectSourceMembership.last_seen_at.desc())
        .limit(500)
    ).all()
    return [source_membership_read(db, membership) for membership in memberships]


def source_membership_read(
    db: Session,
    membership: ProspectSourceMembership,
) -> ProspectSourceMembershipRead:
    prospect = db.get(Prospect, membership.prospect_id)
    campaign = db.get(Campaign, membership.campaign_id)
    cohort = db.get(ProspectingCohort, membership.cohort_id) if membership.cohort_id else None
    return ProspectSourceMembershipRead(
        id=membership.id,
        prospect_id=membership.prospect_id,
        legal_name=prospect.legal_name if prospect else "Unknown prospect",
        campaign_id=membership.campaign_id,
        campaign_name=campaign.name if campaign else "Unknown campaign",
        cohort_id=membership.cohort_id,
        cohort_name=cohort.name if cohort else None,
        source_name=membership.source_name,
        source_profile=membership.source_profile,
        source_record_key=membership.source_record_key,
        source_list_key=membership.source_list_key,
        source_list_name=membership.source_list_name,
        first_import_batch_id=membership.first_import_batch_id,
        latest_import_batch_id=membership.latest_import_batch_id,
        first_seen_at=membership.first_seen_at,
        last_seen_at=membership.last_seen_at,
        appearance_count=membership.appearance_count,
        relationship_state_at_latest_import=membership.relationship_state_at_latest_import,
        source_metadata=membership.source_metadata,
    )


def list_prospect_contact_points(
    db: Session,
    principal: Principal,
) -> list[ProspectContactPointRead]:
    contact_points = db.scalars(
        select(ProspectContactPoint)
        .where(ProspectContactPoint.organization_id == principal.organization_id)
        .order_by(
            ProspectContactPoint.prospect_id,
            ProspectContactPoint.contact_type,
            ProspectContactPoint.rank,
        )
        .limit(1000)
    ).all()
    return [prospect_contact_point_read(db, contact_point) for contact_point in contact_points]


def prospect_contact_point_read(
    db: Session,
    contact_point: ProspectContactPoint,
) -> ProspectContactPointRead:
    prospect = db.get(Prospect, contact_point.prospect_id)
    return ProspectContactPointRead(
        id=contact_point.id,
        prospect_id=contact_point.prospect_id,
        legal_name=prospect.legal_name if prospect else "Unknown prospect",
        source_membership_id=contact_point.source_membership_id,
        contact_type=contact_point.contact_type,
        value=contact_point.value,
        normalized_value=contact_point.normalized_value,
        rank=contact_point.rank,
        is_primary=contact_point.is_primary,
        validation_status=contact_point.validation_status,
        first_seen_at=contact_point.first_seen_at,
        last_seen_at=contact_point.last_seen_at,
    )


def create_prospecting_cohort(
    db: Session,
    principal: Principal,
    payload: ProspectingCohortCreate,
) -> ProspectingCohortRead:
    campaign = scoped_campaign(db, principal.organization_id, payload.campaign_id)
    if campaign is None:
        raise ValueError("Select a Stonegate campaign.")
    script = None
    if payload.script_version_id:
        script = db.scalar(
            select(ProspectingScriptVersion).where(
                ProspectingScriptVersion.organization_id == principal.organization_id,
                ProspectingScriptVersion.id == payload.script_version_id,
            )
        )
        if script is None:
            raise ValueError("Selected caller script does not belong to this workspace.")
    cohort = ProspectingCohort(
        organization_id=principal.organization_id,
        campaign_id=campaign.id,
        script_version_id=script.id if script else None,
        created_by_user_id=principal.user_id,
        name=payload.name.strip(),
        code=payload.code.strip().lower(),
        status="active",
        source_name=payload.source_name.strip(),
        list_type=payload.list_type.strip(),
        market_label=payload.market_label.strip(),
        dialer_mode=payload.dialer_mode,
        call_window_start_hour=payload.call_window_start_hour,
        call_window_end_hour=payload.call_window_end_hour,
        timezone=payload.timezone.strip(),
        starts_on=payload.starts_on,
        ends_on=payload.ends_on,
        cohort_metadata=payload.cohort_metadata,
    )
    db.add(cohort)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("A prospecting cohort with this code already exists.") from exc
    add_audit(
        db,
        principal,
        action="campaign_management.prospecting_cohort_create",
        entity_type="prospecting_cohort",
        entity_id=cohort.id,
        new={
            "campaign_id": str(campaign.id),
            "code": cohort.code,
            "dialer_mode": cohort.dialer_mode,
            "source_name": cohort.source_name,
            "list_type": cohort.list_type,
        },
        reason="Comparable prospecting cohort defined",
    )
    db.commit()
    return prospecting_cohort_read(db, cohort)


def list_prospecting_cohorts(
    db: Session,
    principal: Principal,
) -> list[ProspectingCohortRead]:
    cohorts = db.scalars(
        select(ProspectingCohort)
        .where(ProspectingCohort.organization_id == principal.organization_id)
        .order_by(ProspectingCohort.starts_on.desc(), ProspectingCohort.created_at.desc())
    ).all()
    return [prospecting_cohort_read(db, cohort) for cohort in cohorts]


def prospecting_cohort_read(
    db: Session,
    cohort: ProspectingCohort,
) -> ProspectingCohortRead:
    campaign = db.get(Campaign, cohort.campaign_id)
    creator = db.get(User, cohort.created_by_user_id)
    return ProspectingCohortRead(
        id=cohort.id,
        campaign_id=cohort.campaign_id,
        campaign_name=campaign.name if campaign else "Unknown campaign",
        script_version_id=cohort.script_version_id,
        created_by_user_id=cohort.created_by_user_id,
        created_by_name=creator.display_name if creator else "Unknown user",
        name=cohort.name,
        code=cohort.code,
        status=cohort.status,
        source_name=cohort.source_name,
        list_type=cohort.list_type,
        market_label=cohort.market_label,
        dialer_mode=cohort.dialer_mode,
        call_window_start_hour=cohort.call_window_start_hour,
        call_window_end_hour=cohort.call_window_end_hour,
        timezone=cohort.timezone,
        starts_on=cohort.starts_on,
        ends_on=cohort.ends_on,
        cohort_metadata=cohort.cohort_metadata,
        created_at=cohort.created_at,
    )


def create_prospecting_work_session(
    db: Session,
    principal: Principal,
    payload: ProspectingWorkSessionCreate,
) -> ProspectingWorkSessionRead:
    campaign = scoped_campaign(db, principal.organization_id, payload.campaign_id)
    if campaign is None:
        raise ValueError("Select a Stonegate campaign.")
    cohort = db.scalar(
        select(ProspectingCohort).where(
            ProspectingCohort.organization_id == principal.organization_id,
            ProspectingCohort.id == payload.cohort_id,
            ProspectingCohort.campaign_id == campaign.id,
        )
    )
    if cohort is None:
        raise ValueError("Work session cohort must belong to the selected campaign.")
    caller = active_user(db, principal.organization_id, payload.caller_user_id)
    if caller is None:
        raise ValueError("Work session requires an active workspace user.")
    labor_cost = labor_cost_cents(payload.paid_minutes, payload.hourly_rate_cents)
    cost = CampaignCost(
        organization_id=principal.organization_id,
        campaign_id=campaign.id,
        cohort_id=cohort.id,
        import_batch_id=None,
        worker_user_id=caller.id,
        category="va_labor",
        vendor_name=None,
        amount_cents=labor_cost,
        labor_minutes=payload.paid_minutes,
        hourly_rate_cents=payload.hourly_rate_cents,
        incurred_on=payload.work_date,
        notes=clean_text(payload.notes),
        created_by_user_id=principal.user_id,
    )
    db.add(cost)
    db.flush()
    work_session = ProspectingWorkSession(
        organization_id=principal.organization_id,
        campaign_id=campaign.id,
        cohort_id=cohort.id,
        caller_user_id=caller.id,
        campaign_cost_id=cost.id,
        created_by_user_id=principal.user_id,
        work_date=payload.work_date,
        paid_minutes=payload.paid_minutes,
        productive_calling_minutes=payload.productive_calling_minutes,
        hourly_rate_cents=payload.hourly_rate_cents,
        labor_cost_cents=labor_cost,
        source=payload.source,
        provider_session_id=clean_text(payload.provider_session_id),
        notes=clean_text(payload.notes),
    )
    db.add(work_session)
    db.flush()
    add_audit(
        db,
        principal,
        action="campaign_management.prospecting_work_session_create",
        entity_type="prospecting_work_session",
        entity_id=work_session.id,
        new={
            "campaign_id": str(campaign.id),
            "cohort_id": str(cohort.id),
            "caller_user_id": str(caller.id),
            "paid_minutes": work_session.paid_minutes,
            "productive_calling_minutes": work_session.productive_calling_minutes,
            "labor_cost_cents": labor_cost,
        },
        reason="Prospecting paid time and productive time recorded",
    )
    db.commit()
    return prospecting_work_session_read(db, work_session)


def list_prospecting_work_sessions(
    db: Session,
    principal: Principal,
) -> list[ProspectingWorkSessionRead]:
    sessions = db.scalars(
        select(ProspectingWorkSession)
        .where(ProspectingWorkSession.organization_id == principal.organization_id)
        .order_by(
            ProspectingWorkSession.work_date.desc(),
            ProspectingWorkSession.created_at.desc(),
        )
        .limit(500)
    ).all()
    return [prospecting_work_session_read(db, session) for session in sessions]


def prospecting_work_session_read(
    db: Session,
    session: ProspectingWorkSession,
) -> ProspectingWorkSessionRead:
    campaign = db.get(Campaign, session.campaign_id)
    cohort = db.get(ProspectingCohort, session.cohort_id)
    caller = db.get(User, session.caller_user_id)
    return ProspectingWorkSessionRead(
        id=session.id,
        campaign_id=session.campaign_id,
        campaign_name=campaign.name if campaign else "Unknown campaign",
        cohort_id=session.cohort_id,
        cohort_name=cohort.name if cohort else "Unknown cohort",
        caller_user_id=session.caller_user_id,
        caller_name=caller.display_name if caller else "Unknown user",
        campaign_cost_id=session.campaign_cost_id,
        work_date=session.work_date,
        paid_minutes=session.paid_minutes,
        productive_calling_minutes=session.productive_calling_minutes,
        utilization_rate_basis_points=rate_basis_points(
            session.productive_calling_minutes,
            session.paid_minutes,
        ),
        hourly_rate_cents=session.hourly_rate_cents,
        labor_cost_cents=session.labor_cost_cents,
        source=session.source,
        provider_session_id=session.provider_session_id,
        notes=session.notes,
        created_at=session.created_at,
    )


def create_campaign_cost(
    db: Session,
    principal: Principal,
    payload: CampaignCostCreate,
) -> CampaignCostRead:
    campaign = scoped_campaign(db, principal.organization_id, payload.campaign_id)
    if campaign is None:
        raise ValueError("Select a Stonegate campaign.")
    cohort = None
    if payload.cohort_id:
        cohort = db.scalar(
            select(ProspectingCohort).where(
                ProspectingCohort.organization_id == principal.organization_id,
                ProspectingCohort.id == payload.cohort_id,
                ProspectingCohort.campaign_id == campaign.id,
            )
        )
        if cohort is None:
            raise ValueError("Cost cohort must belong to the selected campaign.")
    import_batch = None
    if payload.import_batch_id:
        import_batch = db.scalar(
            select(ProspectImportBatch).where(
                ProspectImportBatch.organization_id == principal.organization_id,
                ProspectImportBatch.id == payload.import_batch_id,
                ProspectImportBatch.campaign_id == campaign.id,
            )
        )
        if import_batch is None:
            raise ValueError("Import batch must belong to the selected campaign.")
        if import_batch.cohort_id:
            import_cohort = db.get(ProspectingCohort, import_batch.cohort_id)
            if cohort and cohort.id != import_batch.cohort_id:
                raise ValueError("Import batch and cost cohort must match.")
            cohort = cohort or import_cohort
    worker = None
    if payload.worker_user_id:
        worker = active_user(db, principal.organization_id, payload.worker_user_id)
        if worker is None:
            raise ValueError("Labor must reference an active workspace user.")
    cost = CampaignCost(
        organization_id=principal.organization_id,
        campaign_id=campaign.id,
        cohort_id=cohort.id if cohort else None,
        import_batch_id=import_batch.id if import_batch else None,
        worker_user_id=worker.id if worker else None,
        category=payload.category,
        vendor_name=clean_text(payload.vendor_name),
        amount_cents=payload.amount_cents,
        labor_minutes=payload.labor_minutes,
        hourly_rate_cents=payload.hourly_rate_cents,
        incurred_on=payload.incurred_on,
        notes=clean_text(payload.notes),
        created_by_user_id=principal.user_id,
    )
    db.add(cost)
    db.flush()
    add_audit(
        db,
        principal,
        action="campaign_management.cost_create",
        entity_type="campaign_cost",
        entity_id=cost.id,
        new={
            "campaign_id": str(campaign.id),
            "cohort_id": str(cohort.id) if cohort else None,
            "category": cost.category,
            "amount_cents": cost.amount_cents,
            "worker_user_id": str(worker.id) if worker else None,
        },
        reason="Campaign cost attributed",
    )
    db.commit()
    return campaign_cost_read(db, cost)


def list_campaign_costs(db: Session, principal: Principal) -> list[CampaignCostRead]:
    costs = db.scalars(
        select(CampaignCost)
        .where(CampaignCost.organization_id == principal.organization_id)
        .order_by(CampaignCost.incurred_on.desc(), CampaignCost.created_at.desc())
        .limit(300)
    ).all()
    return [campaign_cost_read(db, cost) for cost in costs]


def campaign_cost_read(db: Session, cost: CampaignCost) -> CampaignCostRead:
    campaign = db.get(Campaign, cost.campaign_id)
    cohort = db.get(ProspectingCohort, cost.cohort_id) if cost.cohort_id else None
    worker = db.get(User, cost.worker_user_id) if cost.worker_user_id else None
    return CampaignCostRead(
        id=cost.id,
        campaign_id=cost.campaign_id,
        campaign_name=campaign.name if campaign else "Unknown campaign",
        cohort_id=cost.cohort_id,
        cohort_name=cohort.name if cohort else None,
        import_batch_id=cost.import_batch_id,
        worker_user_id=cost.worker_user_id,
        worker_name=worker.display_name if worker else None,
        category=cost.category,
        vendor_name=cost.vendor_name,
        amount_cents=cost.amount_cents,
        labor_minutes=cost.labor_minutes,
        hourly_rate_cents=cost.hourly_rate_cents,
        incurred_on=cost.incurred_on,
        notes=cost.notes,
        created_at=cost.created_at,
    )


def create_calling_batch(
    db: Session,
    principal: Principal,
    payload: ProspectCallingBatchCreate,
) -> ProspectCallingBatchRead:
    campaign = scoped_campaign(db, principal.organization_id, payload.campaign_id)
    if campaign is None:
        raise ValueError("Select a Stonegate campaign.")
    cohort = None
    if payload.cohort_id:
        cohort = db.scalar(
            select(ProspectingCohort).where(
                ProspectingCohort.organization_id == principal.organization_id,
                ProspectingCohort.id == payload.cohort_id,
                ProspectingCohort.campaign_id == campaign.id,
            )
        )
        if cohort is None:
            raise ValueError("Calling-batch cohort must belong to the selected campaign.")
        if cohort.dialer_mode != payload.dialer_mode:
            raise ValueError("Calling-batch method must match its cohort.")
    assignee = active_user(db, principal.organization_id, payload.assigned_user_id)
    if assignee is None:
        raise ValueError("Calling batch requires an active workspace user.")
    if not assignee.calling_enabled:
        raise ValueError(
            "Enable cold calling for this workspace user before assigning a calling batch."
        )
    import_batch = None
    if payload.import_batch_id:
        import_batch = db.scalar(
            select(ProspectImportBatch).where(
                ProspectImportBatch.organization_id == principal.organization_id,
                ProspectImportBatch.id == payload.import_batch_id,
                ProspectImportBatch.campaign_id == campaign.id,
            )
        )
        if import_batch is None:
            raise ValueError("Import batch must belong to the selected campaign.")
        if import_batch.cohort_id:
            import_cohort = db.get(ProspectingCohort, import_batch.cohort_id)
            if cohort and cohort.id != import_batch.cohort_id:
                raise ValueError("Import batch and calling-batch cohort must match.")
            cohort = cohort or import_cohort
            if cohort and cohort.dialer_mode != payload.dialer_mode:
                raise ValueError("Calling-batch method must match its cohort.")

    already_batched = select(ProspectCallingBatchEntry.prospect_id)
    prospect_statement = (
        select(Prospect)
        .where(
            Prospect.organization_id == principal.organization_id,
            Prospect.campaign_id == campaign.id,
            Prospect.call_eligibility == "eligible",
            Prospect.converted_lead_id.is_(None),
            Prospect.id.not_in(already_batched),
        )
        .order_by(Prospect.created_at)
        .limit(payload.maximum_records)
    )
    if import_batch:
        import_prospect_ids = select(ProspectImportRow.prospect_id).where(
            ProspectImportRow.import_batch_id == import_batch.id,
            ProspectImportRow.prospect_id.is_not(None),
        )
        prospect_statement = prospect_statement.where(Prospect.id.in_(import_prospect_ids))
    if cohort:
        cohort_prospect_ids = select(ProspectSourceMembership.prospect_id).where(
            ProspectSourceMembership.organization_id == principal.organization_id,
            ProspectSourceMembership.cohort_id == cohort.id,
        )
        prospect_statement = prospect_statement.where(Prospect.id.in_(cohort_prospect_ids))
    prospects = db.scalars(prospect_statement).all()
    if not prospects:
        raise ValueError("No unbatched, callable prospects match this selection.")

    batch = ProspectCallingBatch(
        organization_id=principal.organization_id,
        campaign_id=campaign.id,
        import_batch_id=import_batch.id if import_batch else None,
        cohort_id=cohort.id if cohort else None,
        assigned_user_id=assignee.id,
        created_by_user_id=principal.user_id,
        name=payload.name.strip(),
        status="ready",
        dialer_mode=payload.dialer_mode,
        due_at=payload.due_at,
        notes=clean_text(payload.notes),
    )
    db.add(batch)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("A prospect calling batch with this name already exists.") from exc
    for sequence_number, prospect in enumerate(prospects, start=1):
        prospect.assigned_user_id = assignee.id
        db.add(
            ProspectCallingBatchEntry(
                organization_id=principal.organization_id,
                prospect_calling_batch_id=batch.id,
                prospect_id=prospect.id,
                assigned_user_id=assignee.id,
                sequence_number=sequence_number,
                status="queued",
                attempt_count=0,
                disposition=None,
                last_attempt_at=None,
            )
        )
    add_audit(
        db,
        principal,
        action="campaign_management.calling_batch_create",
        entity_type="prospect_calling_batch",
        entity_id=batch.id,
        new={
            "campaign_id": str(campaign.id),
            "assigned_user_id": str(assignee.id),
            "cohort_id": str(cohort.id) if cohort else None,
            "dialer_mode": batch.dialer_mode,
            "record_count": len(prospects),
        },
        reason="Callable prospects assigned as a controlled batch",
    )
    db.commit()
    return calling_batch_read(db, batch)


def list_calling_batches(
    db: Session,
    principal: Principal,
) -> list[ProspectCallingBatchRead]:
    batches = db.scalars(
        select(ProspectCallingBatch)
        .where(ProspectCallingBatch.organization_id == principal.organization_id)
        .order_by(ProspectCallingBatch.created_at.desc())
        .limit(100)
    ).all()
    return [calling_batch_read(db, batch) for batch in batches]


def calling_batch_read(db: Session, batch: ProspectCallingBatch) -> ProspectCallingBatchRead:
    campaign = db.get(Campaign, batch.campaign_id)
    cohort = db.get(ProspectingCohort, batch.cohort_id) if batch.cohort_id else None
    assignee = db.get(User, batch.assigned_user_id)
    entries = db.scalars(
        select(ProspectCallingBatchEntry)
        .where(ProspectCallingBatchEntry.prospect_calling_batch_id == batch.id)
        .order_by(ProspectCallingBatchEntry.sequence_number)
    ).all()
    return ProspectCallingBatchRead(
        id=batch.id,
        campaign_id=batch.campaign_id,
        campaign_name=campaign.name if campaign else "Unknown campaign",
        import_batch_id=batch.import_batch_id,
        cohort_id=batch.cohort_id,
        cohort_name=cohort.name if cohort else None,
        dialer_mode=batch.dialer_mode,
        assigned_user_id=batch.assigned_user_id,
        assigned_user_name=assignee.display_name if assignee else "Unknown user",
        name=batch.name,
        status=batch.status,
        due_at=batch.due_at,
        notes=batch.notes,
        total_entries=len(entries),
        completed_entries=sum(entry.status == "completed" for entry in entries),
        entries=[calling_batch_entry_read(db, entry) for entry in entries],
        created_at=batch.created_at,
    )


def calling_batch_entry_read(
    db: Session,
    entry: ProspectCallingBatchEntry,
) -> ProspectCallingBatchEntryRead:
    prospect = db.get(Prospect, entry.prospect_id)
    data = {
        "street_address": prospect.street_address if prospect else None,
        "city": prospect.city if prospect else None,
        "state_code": prospect.state_code if prospect else None,
        "postal_code": prospect.postal_code if prospect else None,
    }
    return ProspectCallingBatchEntryRead(
        id=entry.id,
        prospect_id=entry.prospect_id,
        legal_name=prospect.legal_name if prospect else "Unknown prospect",
        phone=prospect.phone if prospect else None,
        property_address=property_address(data),
        sequence_number=entry.sequence_number,
        status=entry.status,
        attempt_count=entry.attempt_count,
        disposition=entry.disposition,
        call_eligibility=prospect.call_eligibility if prospect else "blocked",
    )


def campaign_quality_read(db: Session, campaign_id: UUID) -> CampaignQualityRead:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise RuntimeError("Campaign disappeared while building quality metrics.")
    import_totals = db.execute(
        select(
            func.coalesce(func.sum(ProspectImportBatch.total_rows), 0),
            func.coalesce(func.sum(ProspectImportBatch.invalid_rows), 0),
            func.coalesce(func.sum(ProspectImportBatch.duplicate_rows), 0),
            func.coalesce(func.sum(ProspectImportBatch.suppressed_rows), 0),
        ).where(ProspectImportBatch.campaign_id == campaign.id)
    ).one()
    total_rows, invalid_rows, duplicate_rows, suppressed_rows = (
        int(value or 0) for value in import_totals
    )
    imported = count_prospects(db, campaign.id)
    callable_count = count_prospects(db, campaign.id, eligibility="eligible")
    review_count = count_prospects(db, campaign.id, eligibility="review_required")
    blocked_count = count_prospects(db, campaign.id, eligibility="blocked")
    converted = int(
        db.scalar(
            select(func.count())
            .select_from(Prospect)
            .where(
                Prospect.campaign_id == campaign.id,
                Prospect.converted_lead_id.is_not(None),
            )
        )
        or 0
    )
    cost_rows = list(
        db.scalars(select(CampaignCost).where(CampaignCost.campaign_id == campaign.id)).all()
    )
    actual_cost = sum(cost.amount_cents for cost in cost_rows)
    categorized_costs = {
        category: sum(cost.amount_cents for cost in cost_rows if cost.category == category)
        for category in {
            "va_labor",
            "list_purchase",
            "dialer_license",
            "phone_number",
            "voice_usage",
        }
    }
    known_cost = sum(categorized_costs.values())
    cost_breakdown = ProspectingCostBreakdown(
        labor_cents=categorized_costs["va_labor"],
        list_cents=categorized_costs["list_purchase"],
        dialer_license_cents=categorized_costs["dialer_license"],
        phone_number_cents=categorized_costs["phone_number"],
        voice_usage_cents=categorized_costs["voice_usage"],
        other_attributable_cents=actual_cost - known_cost,
    )
    handoff_rows = db.execute(
        select(ProspectHandoff, ProspectingAttempt)
        .join(ProspectingAttempt, ProspectingAttempt.id == ProspectHandoff.attempt_id)
        .join(
            ProspectCallingBatchEntry,
            ProspectCallingBatchEntry.id == ProspectingAttempt.batch_entry_id,
        )
        .join(
            ProspectCallingBatch,
            ProspectCallingBatch.id == ProspectCallingBatchEntry.prospect_calling_batch_id,
        )
        .where(ProspectCallingBatch.campaign_id == campaign.id)
    ).all()
    accepted_warm_leads = sum(
        is_accepted_warm_lead(attempt, handoff) for handoff, attempt in handoff_rows
    )
    rejected_handoffs = sum(handoff.status == "rejected" for handoff, _ in handoff_rows)
    calling_total = int(
        db.scalar(
            select(func.count())
            .select_from(ProspectCallingBatchEntry)
            .join(
                ProspectCallingBatch,
                ProspectCallingBatch.id == ProspectCallingBatchEntry.prospect_calling_batch_id,
            )
            .where(ProspectCallingBatch.campaign_id == campaign.id)
        )
        or 0
    )
    calling_completed = int(
        db.scalar(
            select(func.count())
            .select_from(ProspectCallingBatchEntry)
            .join(
                ProspectCallingBatch,
                ProspectCallingBatch.id == ProspectCallingBatchEntry.prospect_calling_batch_id,
            )
            .where(
                ProspectCallingBatch.campaign_id == campaign.id,
                ProspectCallingBatchEntry.status == "completed",
            )
        )
        or 0
    )
    return CampaignQualityRead(
        campaign_id=campaign.id,
        campaign_name=campaign.name,
        budget_cents=campaign.budget_cents,
        actual_cost_cents=actual_cost,
        remaining_budget_cents=(
            campaign.budget_cents - actual_cost if campaign.budget_cents is not None else None
        ),
        total_import_rows=total_rows,
        imported_prospects=imported,
        callable_prospects=callable_count,
        review_required_prospects=review_count,
        blocked_prospects=blocked_count,
        converted_prospects=converted,
        submitted_handoffs=len(handoff_rows),
        accepted_warm_leads=accepted_warm_leads,
        rejected_handoffs=rejected_handoffs,
        invalid_rows=invalid_rows,
        duplicate_rows=duplicate_rows,
        suppressed_rows=suppressed_rows,
        bad_data_rate_basis_points=rate_basis_points(invalid_rows, total_rows),
        duplicate_rate_basis_points=rate_basis_points(duplicate_rows, total_rows),
        conversion_rate_basis_points=rate_basis_points(converted, imported),
        cost_per_imported_prospect_cents=(round(actual_cost / imported) if imported else None),
        cost_per_callable_prospect_cents=(
            round(actual_cost / callable_count) if callable_count else None
        ),
        cost_per_accepted_warm_lead_cents=cost_per_accepted_warm_lead_cents(
            cost_breakdown,
            accepted_warm_leads,
        ),
        calling_batch_entries=calling_total,
        calling_batch_completed=calling_completed,
    )


def count_prospects(db: Session, campaign_id: UUID, eligibility: str | None = None) -> int:
    statement = (
        select(func.count()).select_from(Prospect).where(Prospect.campaign_id == campaign_id)
    )
    if eligibility:
        statement = statement.where(Prospect.call_eligibility == eligibility)
    return int(db.scalar(statement) or 0)


def scoped_campaign(db: Session, organization_id: UUID, campaign_id: UUID) -> Campaign | None:
    return db.scalar(
        select(Campaign).where(
            Campaign.organization_id == organization_id,
            Campaign.id == campaign_id,
        )
    )


def active_company_suppressions(
    db: Session,
    organization_id: UUID,
) -> dict[str, SuppressionRecord]:
    records = db.scalars(
        select(SuppressionRecord).where(
            SuppressionRecord.organization_id == organization_id,
            SuppressionRecord.channel.in_(("phone", "voice", "all")),
            SuppressionRecord.status.in_(("active", "suppressed")),
            SuppressionRecord.lifted_at.is_(None),
        )
    ).all()
    result: dict[str, SuppressionRecord] = {}
    for record in records:
        try:
            normalized = normalize_prospect_phone(record.normalized_address)
        except ValueError:
            continue
        if normalized:
            result[normalized] = record
    return result


def active_user(db: Session, organization_id: UUID, user_id: UUID) -> User | None:
    return db.scalar(
        select(User).where(
            User.organization_id == organization_id,
            User.id == user_id,
            User.is_active.is_(True),
        )
    )


def property_address(data: Mapping[str, object]) -> str | None:
    parts = [
        string_value(data.get("street_address")),
        string_value(data.get("city")),
        string_value(data.get("state_code")),
        string_value(data.get("postal_code")),
    ]
    return ", ".join(part for part in parts if part) or None


def string_value(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def rate_basis_points(numerator: int, denominator: int) -> int:
    return round(numerator / denominator * 10000) if denominator else 0


def clean_text(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def add_audit(
    db: Session,
    principal: Principal,
    *,
    action: str,
    entity_type: str,
    entity_id: UUID,
    previous: dict[str, object] | None = None,
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
            previous_value=previous,
            new_value=new,
            reason=reason,
        )
    )
