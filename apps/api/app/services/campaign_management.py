import csv
import hashlib
import io
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
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
    ProspectImportBatch,
    ProspectImportMapping,
    ProspectImportRow,
    ProspectSuppressionCheck,
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
    ProspectImportBatchRead,
    ProspectImportMappingCreate,
    ProspectImportMappingRead,
    ProspectImportPreview,
    ProspectImportPreviewRow,
    ProspectImportRequest,
    ProspectImportRowRead,
    ProspectScreeningDecision,
    ProspectScreeningReviewRead,
)
from app.services.acquisition_operations import (
    list_campaigns,
    list_users,
    normalize_prospect_phone,
)
from app.services.property_validation import canonical_address_key

MAX_IMPORT_ROWS = 10_000
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
DNC_CLEAR_VALUES = {"0", "clear", "false", "no", "not listed", "not_listed"}


@dataclass
class PreparedImportRow:
    row_number: int
    raw_data: dict[str, str]
    normalized_data: dict[str, str | None]
    status: str
    validation_errors: list[str]
    eligibility_reasons: list[str]
    duplicate_prospect_id: UUID | None
    company_suppression_status: str
    company_suppression_evidence: dict[str, object]
    dnc_status: str
    dnc_evidence: dict[str, object]


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
        costs=list_campaign_costs(db, principal),
        calling_batches=list_calling_batches(db, principal),
        screening_review=list_screening_review(db, principal),
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
    _, mapping, _ = validate_import_context(db, principal, payload)
    headers, prepared_rows = prepare_import_rows(db, principal, payload, mapping)
    return import_preview(headers, prepared_rows)


def create_prospect_import(
    db: Session,
    principal: Principal,
    payload: ProspectImportRequest,
) -> ProspectImportBatchRead:
    campaign, mapping, assignee = validate_import_context(db, principal, payload)
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
        default_assignee_user_id=assignee.id if assignee else None,
        imported_by_user_id=principal.user_id,
        file_name=payload.file_name.strip(),
        file_sha256=file_sha256,
        status="processing",
        total_rows=counts["total_rows"],
        valid_rows=counts["valid_rows"],
        imported_rows=0,
        invalid_rows=counts["invalid_rows"],
        duplicate_rows=counts["duplicate_rows"],
        suppressed_rows=counts["suppressed_rows"],
        review_required_rows=counts["review_required_rows"],
        completed_at=None,
    )
    db.add(batch)
    db.flush()

    imported_rows = 0
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
        import_row = ProspectImportRow(
            organization_id=principal.organization_id,
            import_batch_id=batch.id,
            prospect_id=prospect.id if prospect else None,
            duplicate_prospect_id=prepared.duplicate_prospect_id,
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
            add_suppression_checks(db, principal, import_row, prospect, prepared, now)

    batch.status = "complete"
    batch.imported_rows = imported_rows
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
            "invalid_rows": batch.invalid_rows,
            "duplicate_rows": batch.duplicate_rows,
            "suppressed_rows": batch.suppressed_rows,
            "review_required_rows": batch.review_required_rows,
        },
        reason="Prospect CSV imported with row-level screening evidence",
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
) -> tuple[Campaign, ProspectImportMapping, User | None]:
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
    assignee = None
    if payload.default_assignee_user_id:
        assignee = active_user(db, principal.organization_id, payload.default_assignee_user_id)
        if assignee is None:
            raise ValueError("The default assignee must be an active workspace user.")
    return campaign, mapping, assignee


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
) -> PreparedImportRow:
    values = {
        field: clean_text(raw.get(column)) or clean_text(mapping.default_values.get(field))
        for field, column in mapping.field_mapping.items()
    }
    for field, default in mapping.default_values.items():
        values.setdefault(field, clean_text(default))
    errors: list[str] = []
    reasons: list[str] = []
    legal_name = values.get("legal_name")
    if not legal_name:
        errors.append("Seller or owner name is required.")
    elif len(legal_name) > 255:
        errors.append("Seller or owner name exceeds 255 characters.")

    phone = values.get("phone")
    normalized_phone = None
    if phone:
        if len(phone) > 80:
            errors.append("Phone number exceeds 80 characters.")
        try:
            normalized_phone = normalize_prospect_phone(phone)
        except ValueError:
            errors.append("Phone number is invalid.")
    email = values.get("email")
    normalized_email = email.lower() if email else None
    if normalized_email and len(normalized_email) > 320:
        errors.append("Email address exceeds 320 characters.")
        normalized_email = None
    elif normalized_email and ("@" not in normalized_email or normalized_email.startswith("@")):
        errors.append("Email address is invalid.")
        normalized_email = None
    if not normalized_phone and not normalized_email:
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

    normalized: dict[str, str | None] = {
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
    }

    duplicate_id = find_duplicate(
        normalized,
        phone_matches,
        email_matches,
        address_matches,
        source_matches,
    )
    identity_keys = {
        value
        for value in (
            f"phone:{normalized_phone}" if normalized_phone else None,
            f"email:{normalized_email}" if normalized_email else None,
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
    if dnc_raw in DNC_BLOCKED_VALUES:
        dnc_status = "blocked"
    elif dnc_raw in DNC_CLEAR_VALUES:
        dnc_status = "clear"
    else:
        dnc_status = "review_required"
    dnc_evidence: dict[str, object] = {
        "raw_value": values.get("dnc_status"),
        "mapping_source": mapping.source_name,
    }

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
    elif dnc_status != "clear":
        status = "review_required"
        reasons.append("Verified Do Not Call screening evidence was not supplied.")
    else:
        status = "valid"

    return PreparedImportRow(
        row_number=row_number,
        raw_data=raw,
        normalized_data=normalized,
        status=status,
        validation_errors=errors,
        eligibility_reasons=reasons,
        duplicate_prospect_id=duplicate_id,
        company_suppression_status=company_status,
        company_suppression_evidence=company_evidence,
        dnc_status=dnc_status,
        dnc_evidence=dnc_evidence,
    )


def find_duplicate(
    normalized: dict[str, str | None],
    phone_matches: dict[str, UUID],
    email_matches: dict[str, UUID],
    address_matches: dict[str, UUID],
    source_matches: dict[str, UUID],
) -> UUID | None:
    candidates = (
        (normalized.get("source_record_key"), source_matches),
        (normalized.get("normalized_phone"), phone_matches),
        (normalized.get("normalized_email"), email_matches),
        (normalized.get("normalized_address_key"), address_matches),
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


def add_suppression_checks(
    db: Session,
    principal: Principal,
    import_row: ProspectImportRow,
    prospect: Prospect,
    prepared: PreparedImportRow,
    checked_at: datetime,
) -> None:
    for check_type, status, source, evidence in (
        (
            "company_suppression",
            prepared.company_suppression_status,
            "stonegate_suppression_records",
            prepared.company_suppression_evidence,
        ),
        (
            "national_dnc",
            prepared.dnc_status,
            "imported_vendor_field",
            prepared.dnc_evidence,
        ),
    ):
        db.add(
            ProspectSuppressionCheck(
                organization_id=principal.organization_id,
                import_row_id=import_row.id,
                prospect_id=prospect.id,
                check_type=check_type,
                channel="voice",
                normalized_value=prospect.normalized_phone,
                status=status,
                source=source,
                evidence=evidence,
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
        and any(row.status in {"valid", "suppressed", "review_required"} for row in rows),
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
        mapping_id=batch.mapping_id,
        mapping_name=mapping.name if mapping else "Unknown mapping",
        default_assignee_user_id=batch.default_assignee_user_id,
        default_assignee_name=assignee.display_name if assignee else None,
        imported_by_user_id=batch.imported_by_user_id,
        imported_by_name=importer.display_name if importer else "Unknown user",
        file_name=batch.file_name,
        file_sha256=batch.file_sha256,
        status=batch.status,
        total_rows=batch.total_rows,
        valid_rows=batch.valid_rows,
        imported_rows=batch.imported_rows,
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
    return ProspectImportRowRead(
        id=row.id,
        row_number=row.row_number,
        status=row.status,
        prospect_id=row.prospect_id,
        duplicate_prospect_id=row.duplicate_prospect_id,
        legal_name=string_value(data.get("legal_name")),
        phone=string_value(data.get("phone")),
        property_address=property_address(data),
        validation_errors=row.validation_errors,
        eligibility_reasons=row.eligibility_reasons,
    )


def create_campaign_cost(
    db: Session,
    principal: Principal,
    payload: CampaignCostCreate,
) -> CampaignCostRead:
    campaign = scoped_campaign(db, principal.organization_id, payload.campaign_id)
    if campaign is None:
        raise ValueError("Select a Stonegate campaign.")
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
    worker = None
    if payload.worker_user_id:
        worker = active_user(db, principal.organization_id, payload.worker_user_id)
        if worker is None:
            raise ValueError("Labor must reference an active workspace user.")
    cost = CampaignCost(
        organization_id=principal.organization_id,
        campaign_id=campaign.id,
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
    worker = db.get(User, cost.worker_user_id) if cost.worker_user_id else None
    return CampaignCostRead(
        id=cost.id,
        campaign_id=cost.campaign_id,
        campaign_name=campaign.name if campaign else "Unknown campaign",
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
    assignee = active_user(db, principal.organization_id, payload.assigned_user_id)
    if assignee is None:
        raise ValueError("Calling batch requires an active workspace user.")
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
        prospect_statement = prospect_statement.where(Prospect.import_batch_id == import_batch.id)
    prospects = db.scalars(prospect_statement).all()
    if not prospects:
        raise ValueError("No unbatched, callable prospects match this selection.")

    batch = ProspectCallingBatch(
        organization_id=principal.organization_id,
        campaign_id=campaign.id,
        import_batch_id=import_batch.id if import_batch else None,
        assigned_user_id=assignee.id,
        created_by_user_id=principal.user_id,
        name=payload.name.strip(),
        status="ready",
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


def list_screening_review(
    db: Session,
    principal: Principal,
) -> list[ProspectScreeningReviewRead]:
    prospects = db.scalars(
        select(Prospect)
        .where(
            Prospect.organization_id == principal.organization_id,
            Prospect.call_eligibility == "review_required",
            Prospect.converted_lead_id.is_(None),
        )
        .order_by(Prospect.created_at)
        .limit(500)
    ).all()
    return [screening_review_read(db, prospect) for prospect in prospects]


def screening_review_read(db: Session, prospect: Prospect) -> ProspectScreeningReviewRead:
    campaign = db.get(Campaign, prospect.campaign_id)
    data: dict[str, object] = {
        "street_address": prospect.street_address,
        "city": prospect.city,
        "state_code": prospect.state_code,
        "postal_code": prospect.postal_code,
    }
    return ProspectScreeningReviewRead(
        id=prospect.id,
        campaign_id=prospect.campaign_id,
        campaign_name=campaign.name if campaign else "Unknown campaign",
        legal_name=prospect.legal_name,
        phone=prospect.phone,
        property_address=property_address(data),
        call_eligibility=prospect.call_eligibility,
        suppression_status=prospect.suppression_status,
        suppression_checked_at=prospect.suppression_checked_at,
    )


def record_screening_decision(
    db: Session,
    principal: Principal,
    prospect_id: UUID,
    payload: ProspectScreeningDecision,
) -> ProspectScreeningReviewRead | None:
    prospect = db.scalar(
        select(Prospect).where(
            Prospect.organization_id == principal.organization_id,
            Prospect.id == prospect_id,
        )
    )
    if prospect is None:
        return None
    if prospect.call_eligibility != "review_required":
        raise ValueError("Only prospects awaiting screening can receive this decision.")
    if not prospect.normalized_phone:
        raise ValueError("A prospect requires a valid phone before DNC review can be cleared.")
    company_record = active_company_suppressions(db, principal.organization_id).get(
        prospect.normalized_phone
    )
    now = datetime.now(UTC)
    final_status = "blocked" if company_record or payload.dnc_status == "blocked" else "eligible"
    previous: dict[str, object] = {
        "call_eligibility": prospect.call_eligibility,
        "suppression_status": prospect.suppression_status,
    }
    prospect.call_eligibility = final_status
    prospect.suppression_status = "suppressed" if final_status == "blocked" else "clear"
    prospect.suppression_checked_at = now
    company_evidence: dict[str, object] = {
        "matched": bool(company_record),
        "suppression_record_id": str(company_record.id) if company_record else None,
        "reason": company_record.reason if company_record else None,
    }
    dnc_evidence: dict[str, object] = {
        "evidence_reference": payload.evidence_reference.strip(),
        "notes": clean_text(payload.notes),
        "reviewed_by_user_id": str(principal.user_id),
    }
    for check_type, status_value, source, evidence in (
        (
            "company_suppression",
            "blocked" if company_record else "clear",
            "stonegate_suppression_records",
            company_evidence,
        ),
        ("national_dnc", payload.dnc_status, payload.source.strip(), dnc_evidence),
    ):
        db.add(
            ProspectSuppressionCheck(
                organization_id=principal.organization_id,
                import_row_id=None,
                prospect_id=prospect.id,
                check_type=check_type,
                channel="voice",
                normalized_value=prospect.normalized_phone,
                status=status_value,
                source=source,
                evidence=evidence,
                checked_at=now,
            )
        )
    add_audit(
        db,
        principal,
        action="campaign_management.screening_decision",
        entity_type="prospect",
        entity_id=prospect.id,
        previous=previous,
        new={
            "call_eligibility": prospect.call_eligibility,
            "suppression_status": prospect.suppression_status,
            "dnc_status": payload.dnc_status,
            "source": payload.source.strip(),
            "evidence_reference": payload.evidence_reference.strip(),
        },
        reason="Prospect DNC screening evidence reviewed",
    )
    db.commit()
    return screening_review_read(db, prospect)


def calling_batch_read(db: Session, batch: ProspectCallingBatch) -> ProspectCallingBatchRead:
    campaign = db.get(Campaign, batch.campaign_id)
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
    actual_cost = int(
        db.scalar(
            select(func.coalesce(func.sum(CampaignCost.amount_cents), 0)).where(
                CampaignCost.campaign_id == campaign.id
            )
        )
        or 0
    )
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
