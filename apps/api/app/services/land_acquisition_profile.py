from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.models.foundation import Lead, Property
from app.schemas.leads import (
    LandAcquisitionEvidenceRead,
    LandAcquisitionFactRead,
    LandAcquisitionProfileRead,
    LandAcquisitionReadinessRead,
    PropertyIntelligenceRead,
)

LAND_ACQUISITION_VERSION = "land_acquisition_v1"
LAND_ACQUISITION_CONTEXT_KEY = LAND_ACQUISITION_VERSION

LAND_FACT_KEYS = (
    "motivation",
    "timeline",
    "asking_price",
    "ownership_decision_makers",
    "parcel_id",
    "county",
    "state",
    "acreage",
    "lot_area_square_feet",
    "road_frontage_feet",
    "legal_description",
    "current_use",
    "zoning_use",
    "access_frontage",
    "utilities",
    "survey_boundaries",
    "septic_perc",
    "taxes_hoa",
    "property_taxes",
    "tax_delinquency",
    "hoa_poa",
    "restrictions",
    "flood_wetlands",
    "terrain_environmental",
    "prior_testing_improvements",
    "known_concerns",
    "title_probate_heirship",
)

LAND_REQUIRED_FACTS = (
    "motivation",
    "timeline",
    "asking_price",
    "ownership_decision_makers",
    "parcel_id",
    "acreage",
    "zoning_use",
    "access_frontage",
    "utilities",
    "survey_boundaries",
    "septic_perc",
    "taxes_hoa",
    "restrictions",
    "flood_wetlands",
    "terrain_environmental",
    "title_probate_heirship",
)

LAND_FIELD_QUESTIONS: dict[str, str] = {
    "motivation": "Why is the seller considering a sale now?",
    "timeline": "When does the seller want to close or decide?",
    "asking_price": "What price or net number is the seller hoping for?",
    "ownership_decision_makers": (
        "Who is on title, and who must approve a sale of this parcel?"
    ),
    "parcel_id": "What is the parcel or assessor parcel number (APN)?",
    "acreage": "How many acres are included, and what is the source of that acreage?",
    "zoning_use": "What zoning, current use, and intended use are known?",
    "access_frontage": (
        "What legal and practical access, road frontage, or easements are known?"
    ),
    "utilities": "Which utilities are at the parcel or nearby?",
    "survey_boundaries": "Is there a survey, and are the boundaries or corners known?",
    "septic_perc": "What is known about sewer, septic, well, or perc testing?",
    "taxes_hoa": "What taxes, delinquency, HOA, or POA obligations are known?",
    "restrictions": "What deed, county, subdivision, or use restrictions are known?",
    "flood_wetlands": "What flood-zone or wetland signals are known?",
    "terrain_environmental": (
        "What terrain, slope, drainage, dumping, or environmental concerns are known?"
    ),
    "title_probate_heirship": (
        "Are there title, lien, probate, heirship, or co-owner issues to resolve?"
    ),
}

LAND_CONTEXT_ALIASES: dict[str, tuple[str, ...]] = {
    "motivation": ("motivation",),
    "timeline": ("timeline", "desired_timeline"),
    "asking_price": ("asking_price",),
    "ownership_decision_makers": (
        "ownership_decision_makers",
        "owner_decision_makers",
        "ownership",
        "decision_makers",
    ),
    "parcel_id": ("parcel_id", "apn"),
    "county": ("county",),
    "state": ("state",),
    "acreage": ("acreage", "acreage_acres", "lot_size_acres"),
    "lot_area_square_feet": ("lot_area_square_feet", "lot_size_square_feet"),
    "road_frontage_feet": ("road_frontage_feet", "lot_size_frontage_feet"),
    "legal_description": ("legal_description",),
    "current_use": ("current_use", "land_use"),
    "zoning_use": ("zoning_use", "zoning_or_use", "zoning"),
    "access_frontage": ("access_frontage", "access_or_frontage"),
    "utilities": ("utilities",),
    "survey_boundaries": ("survey_boundaries", "survey", "boundaries"),
    "septic_perc": ("septic_perc", "septic_or_perc"),
    "taxes_hoa": ("taxes_hoa", "taxes_or_hoa"),
    "property_taxes": ("property_taxes", "annual_property_tax"),
    "tax_delinquency": ("tax_delinquency", "tax_delinquent_year"),
    "hoa_poa": ("hoa_poa", "hoa", "poa"),
    "restrictions": (
        "restrictions",
        "deed_restrictions",
        "county_restrictions",
        "covenants_restrictions",
    ),
    "flood_wetlands": ("flood_wetlands", "flood_or_wetlands"),
    "terrain_environmental": (
        "terrain_environmental",
        "terrain_or_environmental_concerns",
    ),
    "prior_testing_improvements": (
        "prior_testing_improvements",
        "prior_testing",
        "clearing_improvements",
        "improvements",
    ),
    "known_concerns": ("known_concerns", "seller_known_concerns"),
    "title_probate_heirship": (
        "title_probate_heirship",
        "title_issues",
        "title_concerns",
        "probate_heirship",
    ),
}

_CANONICAL_BY_ALIAS = {
    alias: canonical
    for canonical, aliases in LAND_CONTEXT_ALIASES.items()
    for alias in aliases
}
_UNKNOWN_VALUES = {
    "unknown",
    "not known",
    "not sure",
    "not provided",
    "not asked",
    "not yet asked",
    "unavailable",
    "unsure",
    "seller does not know",
    "seller doesn't know",
    "needs research",
    "needs verification",
    "unverified",
    "don't know",
    "do not know",
    "tbd",
}
_CONFLICT_SENSITIVE_FIELDS = {
    "parcel_id",
    "county",
    "state",
    "acreage",
    "lot_area_square_feet",
    "road_frontage_feet",
    "current_use",
    "zoning_use",
    "property_taxes",
    "tax_delinquency",
    "hoa_poa",
}
_IN_PERSON_RISK_TERMS = (
    "landlocked",
    "no legal access",
    "access dispute",
    "boundary dispute",
    "encroach",
    "dump",
    "contamin",
    "wetland",
    "flood",
    "steep",
    "erosion",
    "sinkhole",
)


def canonical_land_key(key: object) -> str | None:
    normalized = str(key or "").strip().lower()
    return _CANONICAL_BY_ALIAS.get(normalized)


def canonical_land_answers(answers: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in answers.items():
        canonical = canonical_land_key(key)
        if canonical is not None and has_land_value(value):
            result[canonical] = value
    return result


def land_context_value(context: Mapping[str, Any] | None, key: str) -> object | None:
    canonical = canonical_land_key(key) or key
    if canonical not in LAND_CONTEXT_ALIASES:
        return None
    source_context = context or {}
    stored = source_context.get(LAND_ACQUISITION_CONTEXT_KEY)
    if isinstance(stored, dict):
        facts = stored.get("facts")
        if isinstance(facts, dict):
            envelope = facts.get(canonical)
            if isinstance(envelope, dict) and has_land_value(envelope.get("value")):
                return envelope["value"]
    for alias in LAND_CONTEXT_ALIASES[canonical]:
        value = source_context.get(alias)
        if has_land_value(value):
            return value
    return None


def record_land_reported_answers(
    context: Mapping[str, Any] | None,
    answers: Mapping[str, object],
    *,
    source_name: str,
    observed_at: datetime,
) -> dict[str, Any]:
    """Merge reported Land answers into the versioned namespace and canonical aliases."""

    result = dict(context or {})
    canonical_answers = {
        key: value
        for key, value in canonical_land_answers(answers).items()
        if key not in {"parcel_id", "county", "state"}
    }
    if not canonical_answers:
        return result
    existing_storage = result.get(LAND_ACQUISITION_CONTEXT_KEY)
    storage = dict(existing_storage) if isinstance(existing_storage, dict) else {}
    existing_facts = storage.get("facts")
    facts = dict(existing_facts) if isinstance(existing_facts, dict) else {}
    observed = as_utc(observed_at).isoformat()
    for key, value in canonical_answers.items():
        result[key] = value
        facts[key] = {
            "value": value,
            "source_type": "seller_reported",
            "source_name": source_name,
            "observed_at": observed,
        }
    storage["schema_version"] = 1
    storage["facts"] = facts
    result[LAND_ACQUISITION_CONTEXT_KEY] = storage
    return result


def merge_land_staff_context(
    existing: Mapping[str, Any] | None,
    incoming: Mapping[str, Any] | None,
    *,
    observed_at: datetime,
) -> dict[str, Any]:
    """Preserve the reserved Land namespace while merging a legacy staff payload."""

    existing_dict = dict(existing or {})
    incoming_dict = dict(incoming or {})
    for identity_key in ("parcel_id", "county", "state"):
        for alias in LAND_CONTEXT_ALIASES[identity_key]:
            incoming_dict.pop(alias, None)
    merged = {**existing_dict, **incoming_dict}
    existing_storage = existing_dict.get(LAND_ACQUISITION_CONTEXT_KEY)
    incoming_storage = incoming_dict.get(LAND_ACQUISITION_CONTEXT_KEY)
    nested_answers: dict[str, object] = {}
    if isinstance(incoming_storage, dict):
        merged_storage = (
            dict(existing_storage) if isinstance(existing_storage, dict) else {}
        )
        merged_storage.update(incoming_storage)
        existing_facts = (
            existing_storage.get("facts") if isinstance(existing_storage, dict) else None
        )
        incoming_facts = incoming_storage.get("facts")
        if isinstance(incoming_facts, dict):
            incoming_facts = {
                key: value
                for key, value in incoming_facts.items()
                if canonical_land_key(key) not in {"parcel_id", "county", "state"}
            }
            merged_facts = dict(existing_facts) if isinstance(existing_facts, dict) else {}
            merged_facts.update(incoming_facts)
            merged_storage["facts"] = merged_facts
            for key, envelope in incoming_facts.items():
                if not isinstance(envelope, dict) or not has_land_value(envelope.get("value")):
                    continue
                prior = existing_facts.get(key) if isinstance(existing_facts, dict) else None
                prior_value = prior.get("value") if isinstance(prior, dict) else None
                if _generic_comparison_value(prior_value) != _generic_comparison_value(
                    envelope["value"]
                ):
                    nested_answers[key] = envelope["value"]
        merged[LAND_ACQUISITION_CONTEXT_KEY] = merged_storage
    reported_answers = {**canonical_land_answers(incoming_dict), **nested_answers}
    return record_land_reported_answers(
        merged,
        reported_answers,
        source_name="staff_qualification_edit",
        observed_at=observed_at,
    )


def build_land_acquisition_profile(
    *,
    lead: Lead,
    property_record: Property,
    property_intelligence: PropertyIntelligenceRead,
) -> LandAcquisitionProfileRead:
    if (
        property_record.organization_id != lead.organization_id
        or property_record.id != lead.property_id
    ):
        raise ValueError("The Land acquisition property does not belong to this lead.")
    evidence: dict[str, list[LandAcquisitionEvidenceRead]] = {
        key: [] for key in LAND_FACT_KEYS
    }
    context = dict(lead.qualification_context or {})
    _add_stored_reported_evidence(evidence, context)
    _add_legacy_context_evidence(evidence, context)
    _add_lead_evidence(evidence, lead)
    _add_property_evidence(evidence, property_record)
    _add_provider_evidence(evidence, property_intelligence.facts)

    facts = {key: _resolve_fact(key, evidence[key]) for key in LAND_FACT_KEYS}
    readiness = _build_readiness(facts)
    return LandAcquisitionProfileRead(
        facts=facts,
        readiness=readiness,
    )


def has_land_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list | tuple | dict | set):
        return bool(value)
    return True


def _add_stored_reported_evidence(
    evidence: dict[str, list[LandAcquisitionEvidenceRead]],
    context: Mapping[str, Any],
) -> None:
    storage = context.get(LAND_ACQUISITION_CONTEXT_KEY)
    if not isinstance(storage, dict):
        return
    stored_facts = storage.get("facts")
    if not isinstance(stored_facts, dict):
        return
    for raw_key, raw_envelope in stored_facts.items():
        canonical = canonical_land_key(raw_key)
        if canonical is None or not isinstance(raw_envelope, dict):
            continue
        value = raw_envelope.get("value")
        if not has_land_value(value):
            continue
        source_name = str(raw_envelope.get("source_name") or "land_qualification")
        evidence[canonical].append(
            LandAcquisitionEvidenceRead(
                value=value,
                source_type="seller_reported",
                source_name=source_name,
                observed_at=parse_datetime(raw_envelope.get("observed_at")),
            )
        )


def _add_legacy_context_evidence(
    evidence: dict[str, list[LandAcquisitionEvidenceRead]],
    context: Mapping[str, Any],
) -> None:
    for canonical, aliases in LAND_CONTEXT_ALIASES.items():
        stored_values = {
            _comparison_value(canonical, item.value)
            for item in evidence[canonical]
            if item.source_type == "seller_reported"
        }
        for alias in aliases:
            value = context.get(alias)
            if not has_land_value(value):
                continue
            if _comparison_value(canonical, value) in stored_values:
                continue
            evidence[canonical].append(
                LandAcquisitionEvidenceRead(
                    value=value,
                    source_type="seller_reported",
                    source_name=(
                        "legacy_call_intelligence"
                        if alias in {
                            "access_or_frontage",
                            "zoning_or_use",
                            "septic_or_perc",
                            "taxes_or_hoa",
                            "terrain_or_environmental_concerns",
                        }
                        else "legacy_qualification_context"
                    ),
                    observed_at=None,
                )
            )
            stored_values.add(_comparison_value(canonical, value))


def _add_lead_evidence(
    evidence: dict[str, list[LandAcquisitionEvidenceRead]], lead: Lead
) -> None:
    for key, value in (
        ("motivation", lead.motivation),
        ("timeline", lead.desired_timeline),
        ("asking_price", lead.asking_price),
    ):
        _append_evidence(
            evidence[key],
            value=value,
            source_type="seller_reported",
            source_name="lead_record",
            observed_at=lead.updated_at,
        )


def _add_property_evidence(
    evidence: dict[str, list[LandAcquisitionEvidenceRead]], property_record: Property
) -> None:
    for key, value in (
        ("parcel_id", property_record.parcel_id),
        ("county", property_record.county),
        ("state", property_record.state),
    ):
        _append_evidence(
            evidence[key],
            value=value,
            source_type="crm_record",
            source_name="property_record",
            observed_at=property_record.updated_at,
        )


def _add_provider_evidence(
    evidence: dict[str, list[LandAcquisitionEvidenceRead]], facts: Mapping[str, Any]
) -> None:
    direct_mappings: dict[str, tuple[str, ...]] = {
        "parcel_id": ("parcel_id",),
        "county": ("county",),
        "state": ("state",),
        "acreage": ("lot_size_acres",),
        "lot_area_square_feet": ("lot_size",),
        "road_frontage_feet": ("lot_size_frontage_feet",),
        "legal_description": ("legal_description",),
        "current_use": ("land_use", "property_use"),
        "zoning_use": ("zoning",),
        "property_taxes": ("annual_property_tax", "property_taxes"),
        "tax_delinquency": ("tax_delinquent_year",),
        "hoa_poa": ("hoa_1_fee_amount",),
    }
    for target, source_keys in direct_mappings.items():
        for source_key in source_keys:
            if _append_provider_fact(evidence[target], facts.get(source_key), source_key):
                break

    utility_values: dict[str, object] = {}
    utility_sources: list[dict[str, Any]] = []
    for source_key in ("water", "sewer"):
        fact = facts.get(source_key)
        if not isinstance(fact, dict) or not has_land_value(fact.get("value")):
            continue
        utility_values[source_key] = fact["value"]
        utility_sources.append(fact)
    if utility_values:
        _append_evidence(
            evidence["utilities"],
            value=utility_values,
            source_type=_property_fact_source_type(utility_sources[0]),
            source_name=_provider_source_name(utility_sources[0], "utility_screen"),
            observed_at=parse_datetime(utility_sources[0].get("observed_at")),
        )

    flood_values: dict[str, object] = {}
    flood_sources: list[dict[str, Any]] = []
    for source_key in ("flood_zone", "flood_zone_description", "wetlands"):
        fact = facts.get(source_key)
        if not isinstance(fact, dict) or not has_land_value(fact.get("value")):
            continue
        flood_values[source_key] = fact["value"]
        flood_sources.append(fact)
    if flood_values:
        _append_evidence(
            evidence["flood_wetlands"],
            value=flood_values,
            source_type=_property_fact_source_type(flood_sources[0]),
            source_name=_provider_source_name(flood_sources[0], "hazard_screen"),
            observed_at=parse_datetime(flood_sources[0].get("observed_at")),
        )

    owner_values: list[object] = []
    owner_sources: list[dict[str, Any]] = []
    for source_key in ("recorded_owner", "recorded_co_owner", "owner_company"):
        fact = facts.get(source_key)
        if not isinstance(fact, dict) or not has_land_value(fact.get("value")):
            continue
        owner_values.append(fact["value"])
        owner_sources.append(fact)
    if owner_values:
        _append_evidence(
            evidence["ownership_decision_makers"],
            value=owner_values,
            source_type=_property_fact_source_type(owner_sources[0]),
            source_name=_provider_source_name(owner_sources[0], "ownership_screen"),
            observed_at=parse_datetime(owner_sources[0].get("observed_at")),
        )


def _append_provider_fact(
    target: list[LandAcquisitionEvidenceRead], raw_fact: object, fallback_source: str
) -> bool:
    if not isinstance(raw_fact, dict) or not has_land_value(raw_fact.get("value")):
        return False
    _append_evidence(
        target,
        value=raw_fact["value"],
        source_type=_property_fact_source_type(raw_fact),
        source_name=_provider_source_name(raw_fact, fallback_source),
        observed_at=parse_datetime(raw_fact.get("observed_at")),
    )
    return True


def _provider_source_name(fact: Mapping[str, Any], fallback: str) -> str:
    return str(fact.get("source") or fallback)


def _property_fact_source_type(fact: Mapping[str, Any]) -> str:
    source = str(fact.get("source") or "").strip().lower()
    return "crm_record" if source == "stonegate_crm" else "provider_sourced"


def _append_evidence(
    target: list[LandAcquisitionEvidenceRead],
    *,
    value: object,
    source_type: str,
    source_name: str,
    observed_at: datetime | None,
) -> None:
    if not has_land_value(value):
        return
    candidate = LandAcquisitionEvidenceRead(
        value=value,
        source_type=source_type,
        source_name=source_name,
        observed_at=observed_at,
    )
    signature = (
        _generic_comparison_value(candidate.value),
        candidate.source_type,
        candidate.source_name,
    )
    if any(
        (
            _generic_comparison_value(item.value),
            item.source_type,
            item.source_name,
        )
        == signature
        for item in target
    ):
        return
    target.append(candidate)


def _resolve_fact(
    key: str, evidence: list[LandAcquisitionEvidenceRead]
) -> LandAcquisitionFactRead:
    ordered = sorted(
        evidence,
        key=lambda item: (
            {"seller_reported": 0, "crm_record": 1, "provider_sourced": 2}[
                item.source_type
            ],
            -(item.observed_at.timestamp() if item.observed_at is not None else 0),
        ),
    )
    selected = next((item for item in ordered if not _is_unknown_value(item.value)), None)
    if selected is None:
        selected = ordered[0] if ordered else None
    non_unknown_values = {
        _comparison_value(key, item.value)
        for item in ordered
        if not _is_unknown_value(item.value)
    }
    conflict = key in _CONFLICT_SENSITIVE_FIELDS and len(non_unknown_values) > 1
    status = (
        "conflict"
        if conflict
        else "known"
        if selected is not None and not _is_unknown_value(selected.value)
        else "unknown"
    )
    return LandAcquisitionFactRead(
        status=status,
        value=selected.value if selected is not None else None,
        source_type=selected.source_type if selected is not None else "unknown",
        source_name=selected.source_name if selected is not None else None,
        observed_at=selected.observed_at if selected is not None else None,
        requires_verification=(
            selected is None
            or selected.source_type != "crm_record"
            or key not in {"parcel_id", "county", "state"}
        ),
        evidence=ordered,
    )


def _build_readiness(
    facts: Mapping[str, LandAcquisitionFactRead],
) -> LandAcquisitionReadinessRead:
    def interview_answered(key: str) -> bool:
        fact = facts[key]
        if key == "parcel_id":
            return any(
                item.source_type in {"crm_record", "seller_reported"}
                for item in fact.evidence
            )
        return any(item.source_type == "seller_reported" for item in fact.evidence)

    completed = [key for key in LAND_REQUIRED_FACTS if interview_answered(key)]
    unanswered = [key for key in LAND_REQUIRED_FACTS if not interview_answered(key)]

    def unresolved_unknown(key: str) -> bool:
        fact = facts[key]
        if fact.status == "unknown":
            return True
        if key == "parcel_id":
            return False
        seller_evidence = [
            item for item in fact.evidence if item.source_type == "seller_reported"
        ]
        return bool(seller_evidence) and all(
            _is_unknown_value(item.value) for item in seller_evidence
        )

    unknown = [key for key in LAND_REQUIRED_FACTS if unresolved_unknown(key)]
    conflicts = [key for key in LAND_REQUIRED_FACTS if facts[key].status == "conflict"]
    seller_reported = [
        key
        for key, fact in facts.items()
        if any(item.source_type == "seller_reported" for item in fact.evidence)
    ]
    provider_sourced = [
        key
        for key, fact in facts.items()
        if any(item.source_type == "provider_sourced" for item in fact.evidence)
    ]
    score = round(100 * len(completed) / len(LAND_REQUIRED_FACTS))
    if unanswered:
        status = "needs_seller_information"
    elif unknown or conflicts:
        status = "needs_due_diligence_review"
    else:
        status = "ready_for_valuation_review"
    open_questions = [LAND_FIELD_QUESTIONS[key] for key in unanswered]
    open_questions.extend(
        f"Research or verify {key.replace('_', ' ')}; the seller reported it as unknown."
        for key in unknown
        if key not in unanswered
    )
    open_questions.extend(
        f"Resolve conflicting evidence for {key.replace('_', ' ')}." for key in conflicts
    )
    risk_values = " ".join(
        str(facts[key].value or "").lower()
        for key in (
            "access_frontage",
            "survey_boundaries",
            "flood_wetlands",
            "terrain_environmental",
            "known_concerns",
        )
    )
    in_person_recommended = any(
        term in risk_values for term in _IN_PERSON_RISK_TERMS
    ) or any(
        key in conflicts
        for key in {
            "access_frontage",
            "survey_boundaries",
            "flood_wetlands",
            "terrain_environmental",
        }
    )
    return LandAcquisitionReadinessRead(
        status=status,
        completion_score=score,
        required_fields=list(LAND_REQUIRED_FACTS),
        completed_fields=completed,
        unanswered_fields=unanswered,
        unknown_fields=unknown,
        conflict_fields=conflicts,
        seller_reported_fields=seller_reported,
        provider_sourced_fields=provider_sourced,
        open_questions=open_questions,
        remote_review_ready=not unanswered,
        in_person_review_recommended=in_person_recommended,
    )


def _is_unknown_value(value: object) -> bool:
    return isinstance(value, str) and " ".join(value.lower().split()) in _UNKNOWN_VALUES


def _comparison_value(key: str, value: object) -> str:
    if key in {"acreage", "lot_area_square_feet", "road_frontage_feet", "property_taxes"}:
        number = _first_number(value)
        if number is not None:
            return f"number:{number:g}"
    if key == "parcel_id":
        return re.sub(r"[^A-Z0-9]", "", str(value).upper())
    return _generic_comparison_value(value)


def _generic_comparison_value(value: object) -> str:
    if isinstance(value, dict):
        return "|".join(
            f"{key}:{_generic_comparison_value(item)}"
            for key, item in sorted(value.items())
        )
    if isinstance(value, list | tuple | set):
        return "|".join(sorted(_generic_comparison_value(item) for item in value))
    return " ".join(str(value).strip().lower().split())


def _first_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    match = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(value))
    if match is None:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return as_utc(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return as_utc(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
    except ValueError:
        return None


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
