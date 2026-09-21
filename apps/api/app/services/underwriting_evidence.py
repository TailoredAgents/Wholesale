import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urldefrag

from app.core.config import Settings
from app.integrations.openai_client import (
    OpenAIClientError,
    OpenAIResponsesClient,
)
from app.integrations.rentcast_client import (
    RentCastClient,
    RentCastClientError,
    RentCastValueEstimate,
)
from app.models.foundation import Property
from app.services.property_validation import (
    address_match_score,
    normalize_street,
    provider_address_components,
)
from app.services.underwriting_comparable_evidence import same_recorded_sale

WEB_EVIDENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {
            "type": "string",
            "enum": ["completed", "insufficient"],
        },
        "summary": {"type": "string"},
        "address_match": {
            "type": "string",
            "enum": ["confirmed", "probable", "conflicting", "not_found"],
        },
        "subject": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "formatted_address": {"type": ["string", "null"]},
                "property_type": {"type": ["string", "null"]},
                "bedrooms": {"type": ["number", "null"]},
                "bathrooms": {"type": ["number", "null"]},
                "square_footage": {"type": ["integer", "null"]},
                "lot_size_square_feet": {"type": ["integer", "null"]},
                "lot_size_acres": {"type": ["number", "null"]},
                "year_built": {"type": ["integer", "null"]},
                "subdivision": {"type": ["string", "null"]},
                "county": {"type": ["string", "null"]},
                "parcel_id": {"type": ["string", "null"]},
                "latitude": {"type": ["number", "null"]},
                "longitude": {"type": ["number", "null"]},
                "last_sale_date": {"type": ["string", "null"]},
                "last_sale_price_dollars": {"type": ["number", "null"]},
                "annual_property_tax_dollars": {"type": ["number", "null"]},
                "assessed_total_value_dollars": {"type": ["number", "null"]},
                "assessed_land_value_dollars": {"type": ["number", "null"]},
                "zoning": {"type": ["string", "null"]},
                "land_use": {"type": ["string", "null"]},
                "legal_description": {"type": ["string", "null"]},
                "water": {"type": ["string", "null"]},
                "sewer": {"type": ["string", "null"]},
                "flood_zone": {"type": ["string", "null"]},
                "source_urls": {"type": "array", "items": {"type": "string"}},
                "source_titles": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "formatted_address", "property_type", "bedrooms", "bathrooms",
                "square_footage", "lot_size_square_feet", "lot_size_acres",
                "year_built", "subdivision", "county", "parcel_id", "latitude",
                "longitude", "last_sale_date", "last_sale_price_dollars",
                "annual_property_tax_dollars", "assessed_total_value_dollars",
                "assessed_land_value_dollars", "zoning", "land_use",
                "legal_description", "water", "sewer", "flood_zone",
                "source_urls", "source_titles"
            ]
        },
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "fact_type": {
                        "type": "string",
                        "enum": [
                            "property_record",
                            "tax_assessment",
                            "sale_history",
                            "listing_history",
                            "permit",
                            "market_context",
                        ],
                    },
                    "value": {"type": "string"},
                    "source_url": {"type": "string"},
                    "source_title": {"type": "string"},
                },
                "required": [
                    "fact_type",
                    "value",
                    "source_url",
                    "source_title",
                ],
            },
        },
        "conflicts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "field": {"type": "string"},
                    "primary_value": {"type": "string"},
                    "web_value": {"type": "string"},
                    "source_url": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": [
                    "field",
                    "primary_value",
                    "web_value",
                    "source_url",
                    "explanation",
                ],
            },
        },
        "comparable_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "formatted_address": {"type": "string"},
                    "address_line1": {"type": "string"},
                    "city": {"type": "string"},
                    "state": {"type": "string"},
                    "postal_code": {"type": "string"},
                    "sale_price_dollars": {"type": ["number", "null"]},
                    "sale_date": {"type": ["string", "null"]},
                    "closed_sale_confirmed": {"type": "boolean"},
                    "transaction_type": {"type": ["string", "null"]},
                    "arms_length_status": {
                        "type": "string",
                        "enum": ["verified", "unverified", "non_market"],
                    },
                    "arms_length_evidence": {"type": ["string", "null"]},
                    "property_type": {"type": ["string", "null"]},
                    "bedrooms": {"type": ["number", "null"]},
                    "bathrooms": {"type": ["number", "null"]},
                    "square_footage": {"type": ["integer", "null"]},
                    "year_built": {"type": ["integer", "null"]},
                    "lot_size": {"type": ["integer", "null"]},
                    "subdivision": {"type": ["string", "null"]},
                    "condition_classification": {
                        "type": "string",
                        "enum": ["unknown", "as_is", "renovated"],
                    },
                    "condition_evidence": {"type": ["string", "null"]},
                    "source_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "source_titles": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "research_summary": {"type": "string"},
                },
                "required": [
                    "formatted_address",
                    "address_line1",
                    "city",
                    "state",
                    "postal_code",
                    "sale_price_dollars",
                    "sale_date",
                    "closed_sale_confirmed",
                    "transaction_type",
                    "arms_length_status",
                    "arms_length_evidence",
                    "property_type",
                    "bedrooms",
                    "bathrooms",
                    "square_footage",
                    "year_built",
                    "lot_size",
                    "subdivision",
                    "condition_classification",
                    "condition_evidence",
                    "source_urls",
                    "source_titles",
                    "research_summary",
                ],
            },
        },
        "limitations": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "status",
        "summary",
        "address_match",
        "subject",
        "facts",
        "conflicts",
        "comparable_candidates",
        "limitations",
    ],
}

LAND_WEB_EVIDENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {"type": "string", "enum": ["completed", "insufficient"]},
        "summary": {"type": "string"},
        "address_match": {
            "type": "string",
            "enum": ["confirmed", "probable", "conflicting", "not_found"],
        },
        "subject": WEB_EVIDENCE_SCHEMA["properties"]["subject"],
        "comparable_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "formatted_address": {"type": ["string", "null"]},
                    "parcel_id": {"type": ["string", "null"]},
                    "county": {"type": ["string", "null"]},
                    "state": {"type": ["string", "null"]},
                    "sale_price_dollars": {"type": ["number", "null"]},
                    "sale_date": {"type": ["string", "null"]},
                    "closed_sale_confirmed": {"type": "boolean"},
                    "arms_length_status": {
                        "type": "string",
                        "enum": ["verified", "unverified", "non_market"],
                    },
                    "arms_length_evidence": {"type": ["string", "null"]},
                    "acres": {"type": ["number", "null"]},
                    "lot_size_square_feet": {"type": ["integer", "null"]},
                    "lot_count": {"type": ["integer", "null"]},
                    "land_use": {"type": ["string", "null"]},
                    "zoning": {"type": ["string", "null"]},
                    "latitude": {"type": ["number", "null"]},
                    "longitude": {"type": ["number", "null"]},
                    "source_urls": {"type": "array", "items": {"type": "string"}},
                    "source_titles": {"type": "array", "items": {"type": "string"}},
                    "research_summary": {"type": "string"},
                },
                "required": [
                    "formatted_address", "parcel_id", "county", "state",
                    "sale_price_dollars", "sale_date", "closed_sale_confirmed",
                    "arms_length_status", "arms_length_evidence", "acres",
                    "lot_size_square_feet", "lot_count", "land_use", "zoning",
                    "latitude", "longitude", "source_urls", "source_titles",
                    "research_summary"
                ],
            },
        },
        "limitations": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "status", "summary", "address_match", "subject",
        "comparable_candidates", "limitations"
    ],
}


@dataclass(frozen=True)
class RentCastSubjectResolution:
    estimate: RentCastValueEstimate
    subject_record: dict[str, Any]
    resolved_address: str
    address_evidence: dict[str, Any]
    avm_error: str | None = None
    property_record_error: str | None = None


def resolve_rentcast_subject(
    client: RentCastClient,
    property_record: Property,
    *,
    requested_address: str,
) -> RentCastSubjectResolution:
    attempts: list[dict[str, Any]] = []
    initial_error: RentCastClientError | None = None
    try:
        estimate = client.get_value_estimate(
            address=requested_address,
            property_type=property_record.property_type,
        )
    except RentCastClientError as exc:
        initial_error = exc
        attempts.append(failed_attempt("avm", requested_address, exc))
    else:
        attempts.append(successful_attempt("avm", requested_address))
        subject_record, property_error = fetch_subject_record(
            client,
            estimate=estimate,
            address=requested_address,
            attempts=attempts,
        )
        subject_evidence = subject_record or estimate.subject_property
        score, issues = provider_match(property_record, subject_evidence)
        if is_acceptable_match(score, issues):
            return RentCastSubjectResolution(
                estimate=estimate,
                subject_record=subject_record,
                resolved_address=provider_formatted_address(subject_evidence) or requested_address,
                address_evidence=build_address_evidence(
                    requested_address=requested_address,
                    resolved_address=provider_formatted_address(subject_evidence)
                    or requested_address,
                    method="exact_avm",
                    score=score,
                    issues=issues,
                    attempts=attempts,
                ),
                property_record_error=property_error,
            )
        attempts.append(
            {
                "operation": "subject_match",
                "address": requested_address,
                "status": "rejected",
                "match_score": score,
                "issues": issues,
            }
        )
        initial_error = RentCastClientError(
            "RentCast returned a subject property that does not match the requested address.",
            operation="value estimate",
        )

    best_record: dict[str, Any] = {}
    best_record_address = requested_address
    best_record_score = 0
    best_record_issues: list[str] = []
    for candidate in address_candidates(property_record, requested_address):
        try:
            record = client.get_property_record(address=candidate)
        except RentCastClientError as exc:
            attempts.append(failed_attempt("property_record", candidate, exc))
            continue
        if not record:
            attempts.append(
                {
                    "operation": "property_record",
                    "address": candidate,
                    "status": "not_found",
                }
            )
            continue
        score, issues = provider_match(property_record, record)
        attempts.append(
            {
                "operation": "property_record",
                "address": candidate,
                "status": "matched" if is_acceptable_match(score, issues) else "rejected",
                "match_score": score,
                "issues": issues,
            }
        )
        if score > best_record_score:
            best_record = record
            best_record_address = provider_formatted_address(record) or candidate
            best_record_score = score
            best_record_issues = issues
        if not is_acceptable_match(score, issues):
            continue
        resolved_address = provider_formatted_address(record) or candidate
        try:
            estimate = client.get_value_estimate(
                address=resolved_address,
                property_type=(
                    string_value(record.get("propertyType")) or property_record.property_type
                ),
            )
        except RentCastClientError as exc:
            attempts.append(failed_attempt("avm", resolved_address, exc))
            continue
        attempts.append(successful_attempt("avm", resolved_address))
        return RentCastSubjectResolution(
            estimate=estimate,
            subject_record=record,
            resolved_address=resolved_address,
            address_evidence=build_address_evidence(
                requested_address=requested_address,
                resolved_address=resolved_address,
                method="property_record_retry",
                score=score,
                issues=issues,
                attempts=attempts,
            ),
            avm_error=str(initial_error) if initial_error else None,
        )

    if best_record and is_acceptable_match(best_record_score, best_record_issues):
        return RentCastSubjectResolution(
            estimate=empty_value_estimate(best_record, initial_error),
            subject_record=best_record,
            resolved_address=best_record_address,
            address_evidence=build_address_evidence(
                requested_address=requested_address,
                resolved_address=best_record_address,
                method="recorded_sales_fallback",
                score=best_record_score,
                issues=best_record_issues,
                attempts=attempts,
            ),
            avm_error=str(initial_error) if initial_error else None,
        )

    assert initial_error is not None
    raise initial_error


def fetch_subject_record(
    client: RentCastClient,
    *,
    estimate: RentCastValueEstimate,
    address: str,
    attempts: list[dict[str, Any]],
) -> tuple[dict[str, Any], str | None]:
    property_id = string_value(estimate.subject_property.get("id"))
    try:
        record = client.get_property_record(address=address, property_id=property_id)
    except RentCastClientError as exc:
        attempts.append(failed_attempt("property_record", address, exc))
        return {}, str(exc)
    attempts.append(
        {
            "operation": "property_record",
            "address": address,
            "status": "found" if record else "not_found",
        }
    )
    return (
        (record, None)
        if record
        else ({}, "RentCast did not return a separate public property record.")
    )


def address_candidates(
    property_record: Property,
    requested_address: str,
) -> list[str]:
    candidates = [
        property_record.validated_formatted_address,
        requested_address,
        (
            f"{property_record.street_address}, {property_record.city}, "
            f"{property_record.state}, {property_record.postal_code}"
        ),
        (
            f"{normalize_street(property_record.street_address)}, "
            f"{property_record.city}, {property_record.state}, "
            f"{property_record.postal_code}"
        ),
    ]
    unique: list[str] = []
    seen: set[str] = set()
    for value in candidates:
        if not isinstance(value, str) or not value.strip():
            continue
        normalized = " ".join(value.lower().split())
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(value.strip())
    return unique


def provider_match(
    property_record: Property,
    provider_record: dict[str, Any],
) -> tuple[int, list[str]]:
    if not provider_record:
        return 0, ["No provider subject property was returned."]
    requested = {
        "street_address": property_record.street_address.strip(),
        "city": property_record.city.strip(),
        "state": property_record.state.strip().upper(),
        "postal_code": property_record.postal_code.strip(),
    }
    return address_match_score(
        requested,
        provider_address_components(provider_record),
    )


def is_acceptable_match(score: int, issues: list[str]) -> bool:
    blocking_issues = {
        "Street number does not match the provider record.",
        "City differs from the provider record.",
        "State differs from the provider record.",
        "ZIP code differs from the provider record.",
    }
    return score >= 80 and not any(issue in blocking_issues for issue in issues)


def build_address_evidence(
    *,
    requested_address: str,
    resolved_address: str,
    method: str,
    score: int,
    issues: list[str],
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "requested_address": requested_address,
        "resolved_address": resolved_address,
        "resolution_method": method,
        "match_score": score,
        "status": (
            "confirmed"
            if score >= 90 and not issues
            else "probable"
            if is_acceptable_match(score, issues)
            else "needs_review"
        ),
        "issues": issues,
        "attempts": attempts,
    }


def collect_secondary_market_evidence(
    settings: Settings,
    property_record: Property,
    *,
    requested_address: str,
    subject_facts: dict[str, Any],
) -> dict[str, Any]:
    if not settings.ai_enabled:
        return unavailable_secondary_evidence("AI is disabled.")
    if not settings.openai_web_search_enabled:
        return unavailable_secondary_evidence(
            "Controlled web research is disabled by OPENAI_WEB_SEARCH_ENABLED."
        )
    if not settings.openai_api_key:
        return unavailable_secondary_evidence("OPENAI_API_KEY is not configured.")

    client = OpenAIResponsesClient(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout_seconds=settings.openai_request_timeout_seconds,
    )
    public_facts = {
        key: subject_facts.get(key)
        for key in (
            "formattedAddress",
            "propertyType",
            "bedrooms",
            "bathrooms",
            "squareFootage",
            "lotSize",
            "yearBuilt",
            "lastSaleDate",
            "lastSalePrice",
            "county",
        )
        if subject_facts.get(key) is not None
    }
    try:
        parsed, usage, sources = client.create_grounded_structured_response(
            model=settings.openai_default_model,
            system_prompt=(
                "You are a real-estate underwriting research agent. Search public sources for "
                "property facts about the exact subject and nearby closed-sale comparables. "
                "Prioritize "
                "county or municipal records, tax assessor records, permit records, and "
                "dated sold-listing pages from identifiable brokerages and major property "
                "portals. A comparable candidate must have an exact street address, a closed "
                "sale price, a closed sale date, living area, and cited source URLs. Never "
                "represent a list price, estimate, pending price, or tax assessment as a sale. "
                "Only mark arms_length_status verified when a cited deed, MLS closed-sale "
                "record, closing record, or other consulted source affirmatively supports an "
                "ordinary arm's-length market transfer; explain that support in "
                "arms_length_evidence. Mark foreclosures, sheriff/tax sales, quitclaims, gifts, "
                "family transfers, deeds in lieu, and corrective deeds non_market. If transfer "
                "status is not supported, mark it unverified. "
                "Search within roughly three miles and two years, preferring the same property "
                "type, subdivision, size, age, and renovated condition. Do not identify owners, "
                "occupants, tenants, phone numbers, emails, or other personal information. "
                "Do not estimate value, ARV, repairs, an offer, or a price range. Automated "
                "home-value estimates are not sale evidence. Report conflicts rather than "
                "resolving them. Every subject field, fact, conflict, and comparable must cite "
                "URLs actually consulted during this search. Fill the structured subject object "
                "only from cited public sources. Return incomplete fields as null; do not infer "
                "or fabricate them."
            ),
            user_prompt=json.dumps(
                {
                    "task": (
                        "Verify the address and collect primary public evidence for property "
                        "facts, prior recorded sales, listing history/condition clues, permits, "
                        "local market context, and up to eight likely nearby closed-sale "
                        "comparables. Stonegate validates this cited evidence before it can "
                        "affect valuation math."
                    ),
                    "subject_address": requested_address,
                    "known_crm_facts": public_facts,
                },
                sort_keys=True,
            ),
            schema_name="stonegate_underwriting_web_evidence",
            json_schema=WEB_EVIDENCE_SCHEMA,
            reasoning_effort="low",
            max_output_tokens=4200,
            safety_identifier=f"underwriting-{property_record.id}",
            prompt_cache_key="stonegate:underwriting-evidence:v2",
            user_location={
                "country": "US",
                "city": property_record.city,
                "region": property_record.state,
                "timezone": "America/New_York",
            },
            blocked_domains=[
                "facebook.com",
                "instagram.com",
                "reddit.com",
                "tiktok.com",
                "x.com",
            ],
            max_tool_calls=5,
            search_context_size="medium",
        )
    except OpenAIClientError as exc:
        return unavailable_secondary_evidence(str(exc))

    evidence = sanitize_grounded_evidence(parsed, sources)
    evidence["model"] = settings.openai_default_model
    evidence["usage"] = usage
    return evidence


def sanitize_grounded_evidence(
    parsed: dict[str, Any],
    sources: list[dict[str, str]],
) -> dict[str, Any]:
    consulted = {
        normalize_url(source.get("url")): source
        for source in sources
        if normalize_url(source.get("url"))
    }
    facts = [
        fact
        for fact in list_of_dicts(parsed.get("facts"))
        if normalize_url(fact.get("source_url")) in consulted
    ][:8]
    conflicts = [
        conflict
        for conflict in list_of_dicts(parsed.get("conflicts"))
        if normalize_url(conflict.get("source_url")) in consulted
    ][:6]
    comparable_candidates = sanitize_comparable_candidates(
        parsed.get("comparable_candidates"),
        consulted,
    )
    subject = sanitize_subject(parsed.get("subject"), consulted)
    status = string_value(parsed.get("status")) or "insufficient"
    if not facts and not conflicts and not comparable_candidates:
        status = "insufficient"
    return {
        "research_version": "ai_comp_discovery_v1",
        "status": status,
        "summary": string_value(parsed.get("summary"))
        or "No corroborating public property evidence was found.",
        "address_match": string_value(parsed.get("address_match")) or "not_found",
        "subject": subject,
        "facts": facts,
        "conflicts": conflicts,
        "comparable_candidates": comparable_candidates,
        "valuation_candidate_count": sum(
            candidate.get("valuation_eligible") is True for candidate in comparable_candidates
        ),
        "limitations": [
            item for item in parsed.get("limitations", []) if isinstance(item, str) and item.strip()
        ][:6],
        "sources": list(consulted.values())[:24],
    }


def sanitize_subject(
    raw_subject: Any,
    consulted: dict[str, dict[str, str]],
) -> dict[str, Any]:
    if not isinstance(raw_subject, dict):
        return {}
    urls = list(
        dict.fromkeys(
            normalized
            for value in raw_subject.get("source_urls", [])
            if (normalized := normalize_url(value)) in consulted
        )
    )
    if not urls:
        return {}
    return {
        **raw_subject,
        "source_urls": urls,
        "source_titles": [
            string_value(consulted[url].get("title")) or url for url in urls
        ],
    }


def collect_land_market_evidence(
    settings: Settings,
    property_record: Property,
    *,
    requested_identity: str,
) -> dict[str, Any]:
    if not settings.ai_enabled:
        return unavailable_secondary_evidence("AI is disabled.")
    if not settings.openai_web_search_enabled:
        return unavailable_secondary_evidence(
            "Controlled web research is disabled by OPENAI_WEB_SEARCH_ENABLED."
        )
    if not settings.openai_api_key:
        return unavailable_secondary_evidence("OPENAI_API_KEY is not configured.")
    client = OpenAIResponsesClient(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout_seconds=settings.openai_request_timeout_seconds,
    )
    try:
        parsed, usage, sources = client.create_grounded_structured_response(
            model=settings.openai_default_model,
            system_prompt=(
                "You research vacant-land property records and closed land sales for real-estate "
                "underwriting. Use county assessor, recorder, GIS, planning/zoning, FEMA, and "
                "dated sold-listing sources. Match the exact address or parcel before returning "
                "subject facts. Find up to twelve nearby closed vacant-land sales, preferring "
                "similar acreage and use. A candidate needs cited sale price, sale date, acreage "
                "or lot square feet, and exact address or parcel identity. Never treat asking "
                "prices, estimates, assessments, quitclaims, gifts, tax sales, or foreclosures as "
                "ordinary market sales. Mark arms-length verified only with affirmative cited "
                "evidence. Do not identify owners or other people. Do not estimate value or an "
                "offer. Use null for facts you cannot support, and cite every returned record."
            ),
            user_prompt=json.dumps(
                {
                    "task": "Verify this land parcel and collect cited closed land sales.",
                    "subject_identity": requested_identity,
                    "crm": {
                        "address": property_lookup_identity(property_record),
                        "parcel_id": property_record.parcel_id,
                        "county": property_record.county,
                        "state": property_record.state,
                        "property_type": property_record.property_type,
                    },
                },
                sort_keys=True,
            ),
            schema_name="stonegate_land_public_evidence",
            json_schema=LAND_WEB_EVIDENCE_SCHEMA,
            reasoning_effort="low",
            max_output_tokens=5000,
            safety_identifier=f"land-research-{property_record.id}",
            prompt_cache_key="stonegate:land-public-evidence:v1",
            user_location={
                "country": "US",
                "city": property_record.city,
                "region": property_record.state,
                "timezone": "America/New_York",
            },
            blocked_domains=[
                "facebook.com", "instagram.com", "reddit.com", "tiktok.com", "x.com"
            ],
            max_tool_calls=7,
            search_context_size="medium",
        )
    except OpenAIClientError as exc:
        return unavailable_secondary_evidence(str(exc))
    consulted = {
        normalize_url(source.get("url")): source
        for source in sources
        if normalize_url(source.get("url"))
    }
    candidates: list[dict[str, Any]] = []
    for raw in list_of_dicts(parsed.get("comparable_candidates"))[:16]:
        urls = list(
            dict.fromkeys(
                normalized
                for value in raw.get("source_urls", [])
                if (normalized := normalize_url(value)) in consulted
            )
        )
        price = positive_number(raw.get("sale_price_dollars"))
        sold_on = iso_date_value(raw.get("sale_date"))
        acres = positive_number(raw.get("acres"))
        lot_square_feet = positive_integer(raw.get("lot_size_square_feet"))
        if acres is None and lot_square_feet is not None:
            acres = lot_square_feet / 43_560
        if lot_square_feet is None and acres is not None:
            lot_square_feet = round(acres * 43_560)
        rejection = public_transfer_rejection_reason(
            transaction_type="land sale",
            arms_length_status=string_value(raw.get("arms_length_status")),
            arms_length_evidence=string_value(raw.get("arms_length_evidence")),
            sale_price=price or 0,
        )
        if (
            not urls
            or price is None
            or sold_on is None
            or acres is None
            or raw.get("closed_sale_confirmed") is not True
            or rejection is not None
        ):
            continue
        candidates.append(
            {
                **raw,
                "sale_price_dollars": price,
                "sale_date": sold_on,
                "acres": acres,
                "lot_size_square_feet": lot_square_feet,
                "source_urls": urls,
                "source_titles": [
                    string_value(consulted[url].get("title")) or url for url in urls
                ],
                "source": "ai_web_research",
            }
        )
    status = string_value(parsed.get("status")) or "insufficient"
    evidence = {
        "research_version": "land_public_research_v1",
        "status": status,
        "summary": string_value(parsed.get("summary")) or "No land evidence was found.",
        "address_match": string_value(parsed.get("address_match")) or "not_found",
        "subject": sanitize_subject(parsed.get("subject"), consulted),
        "comparable_candidates": candidates[:12],
        "valuation_candidate_count": len(candidates[:12]),
        "limitations": [
            item for item in parsed.get("limitations", [])
            if isinstance(item, str) and item.strip()
        ][:8],
        "sources": list(consulted.values())[:30],
        "model": settings.openai_default_model,
        "usage": usage,
    }
    if not evidence["subject"] and not evidence["comparable_candidates"]:
        evidence["status"] = "insufficient"
    return evidence


def property_lookup_identity(property_record: Property) -> str:
    return ", ".join(
        value.strip()
        for value in (
            property_record.street_address,
            property_record.city,
            property_record.state,
            property_record.postal_code,
        )
        if isinstance(value, str) and value.strip()
    )


def research_subject_record(
    evidence: dict[str, Any],
    property_record: Property,
    *,
    requested_address: str,
) -> dict[str, Any]:
    """Translate cited public research into Stonegate's canonical subject shape."""
    raw_subject = evidence.get("subject")
    values = raw_subject if isinstance(raw_subject, dict) else {}
    lot_square_feet = positive_integer(values.get("lot_size_square_feet"))
    lot_acres = positive_number(values.get("lot_size_acres"))
    if lot_square_feet is None and lot_acres is not None:
        lot_square_feet = round(lot_acres * 43_560)
    parcel_id = string_value(values.get("parcel_id")) or property_record.parcel_id
    return {
        "formattedAddress": string_value(values.get("formatted_address")) or requested_address,
        "addressLine1": property_record.street_address,
        "city": property_record.city,
        "state": property_record.state,
        "zipCode": property_record.postal_code,
        "propertyType": string_value(values.get("property_type"))
        or property_record.property_type,
        "bedrooms": positive_number(values.get("bedrooms")),
        "bathrooms": positive_number(values.get("bathrooms")),
        "squareFootage": positive_integer(values.get("square_footage")),
        "lotSize": lot_square_feet,
        "lotAcres": lot_acres,
        "yearBuilt": positive_integer(values.get("year_built")),
        "subdivision": string_value(values.get("subdivision")),
        "county": string_value(values.get("county")) or property_record.county,
        "id": parcel_id,
        "parcelId": parcel_id,
        "latitude": values.get("latitude"),
        "longitude": values.get("longitude"),
        "lastSaleDate": iso_date_value(values.get("last_sale_date")),
        "lastSalePrice": positive_number(values.get("last_sale_price_dollars")),
        "propertyTaxes": positive_number(values.get("annual_property_tax_dollars")),
        "assessedValue": positive_number(values.get("assessed_total_value_dollars")),
        "assessedLandValue": positive_number(values.get("assessed_land_value_dollars")),
        "zoning": string_value(values.get("zoning")),
        "landUse": string_value(values.get("land_use")),
        "legalDescription": string_value(values.get("legal_description")),
        "water": string_value(values.get("water")),
        "sewer": string_value(values.get("sewer")),
        "floodZone": string_value(values.get("flood_zone")),
        "_stonegateEvidenceSource": "ai_web_research",
        "_stonegateSourceUrls": list(values.get("source_urls", [])),
        "_stonegateSourceTitles": list(values.get("source_titles", [])),
    }


def sanitize_comparable_candidates(
    raw_candidates: Any,
    consulted: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in list_of_dicts(raw_candidates)[:12]:
        urls = list(
            dict.fromkeys(
                normalized
                for value in raw.get("source_urls", [])
                if (normalized := normalize_url(value)) in consulted
            )
        )
        sale_price = positive_number(raw.get("sale_price_dollars"))
        sale_date = iso_date_value(raw.get("sale_date"))
        square_footage = positive_integer(raw.get("square_footage"))
        address = string_value(raw.get("formatted_address"))
        address_line1 = string_value(raw.get("address_line1"))
        city = string_value(raw.get("city"))
        state = string_value(raw.get("state"))
        postal_code = string_value(raw.get("postal_code"))
        property_type = string_value(raw.get("property_type"))
        transaction_type = string_value(raw.get("transaction_type"))
        arms_length_status = string_value(raw.get("arms_length_status"))
        arms_length_evidence = string_value(raw.get("arms_length_evidence"))
        if (
            not address
            or not address_line1
            or not city
            or not state
            or not postal_code
            or not property_type
            or not urls
            or sale_price is None
            or sale_date is None
            or square_footage is None
            or raw.get("closed_sale_confirmed") is not True
        ):
            continue
        identity = (compact_text(address), sale_date)
        if identity in seen:
            continue
        seen.add(identity)
        source_grade = "corroborated" if len(urls) >= 2 else "cited_single_source"
        transfer_rejection = public_transfer_rejection_reason(
            transaction_type=transaction_type,
            arms_length_status=arms_length_status,
            arms_length_evidence=arms_length_evidence,
            sale_price=sale_price,
        )
        candidates.append(
            {
                **raw,
                "sale_price_dollars": sale_price,
                "sale_date": sale_date,
                "square_footage": square_footage,
                "source_urls": urls,
                "source_titles": [string_value(consulted[url].get("title")) or url for url in urls],
                "source_grade": source_grade,
                "transaction_type": transaction_type,
                "arms_length_status": arms_length_status or "unverified",
                "arms_length_evidence": arms_length_evidence,
                "transfer_review_reason": transfer_rejection,
                "valuation_eligible": transfer_rejection is None,
            }
        )
    return candidates[:8]


def research_comparable_sale_records(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, candidate in enumerate(list_of_dicts(evidence.get("comparable_candidates"))):
        if candidate.get("valuation_eligible") is not True:
            continue
        source_urls = [url for url in candidate.get("source_urls", []) if isinstance(url, str)]
        source_grade = string_value(candidate.get("source_grade")) or "cited_single_source"
        records.append(
            {
                "id": f"web-research:{index}:{compact_text(candidate.get('formatted_address'))}",
                "formattedAddress": candidate.get("formatted_address"),
                "addressLine1": candidate.get("address_line1"),
                "city": candidate.get("city"),
                "state": candidate.get("state"),
                "zipCode": candidate.get("postal_code"),
                "propertyType": candidate.get("property_type"),
                "lastSalePrice": candidate.get("sale_price_dollars"),
                "lastSaleDate": candidate.get("sale_date"),
                "transaction_type": candidate.get("transaction_type"),
                "transaction_eligibility": "not_flagged",
                "transaction_review_reason": None,
                "bedrooms": candidate.get("bedrooms"),
                "bathrooms": candidate.get("bathrooms"),
                "squareFootage": candidate.get("square_footage"),
                "yearBuilt": candidate.get("year_built"),
                "lotSize": candidate.get("lot_size"),
                "subdivision": candidate.get("subdivision"),
                "_stonegateSearchLevel": "manual",
                "_stonegateVerificationStatus": (
                    "public_corroborated"
                    if source_grade == "corroborated"
                    else "public_cited_single_source"
                ),
                "_stonegateEvidenceSource": "ai_web_research",
                "_stonegateSourceReference": "; ".join(
                    string_value(title) or "Public source"
                    for title in candidate.get("source_titles", [])
                ),
                "_stonegateSourceUrl": source_urls[0] if source_urls else None,
                "_stonegateSourceUrls": source_urls,
                "_stonegateVerificationNotes": " ".join(
                    value
                    for value in (
                        string_value(candidate.get("research_summary")),
                        (
                            "AI condition clue: "
                            + (string_value(candidate.get("condition_classification")) or "unknown")
                            + "."
                        ),
                    )
                    if value
                ),
                "_stonegateConditionClassification": "unknown",
                "_stonegateConditionEvidence": candidate.get("condition_evidence"),
                "_stonegateTransactionType": candidate.get("transaction_type"),
                "_stonegateTransactionEligibility": "not_flagged",
                "_stonegateTransactionReviewReason": None,
                "_stonegateArmsLengthEvidence": candidate.get("arms_length_evidence"),
            }
        )
    return records


def public_transfer_rejection_reason(
    *,
    transaction_type: str | None,
    arms_length_status: str | None,
    arms_length_evidence: str | None,
    sale_price: float,
) -> str | None:
    """Require affirmative, cited arm's-length support for AI-discovered sales."""
    if sale_price < 10_000:
        return "Recorded consideration is nominal, not an ordinary market sale."
    normalized_type = compact_text(transaction_type)
    blocked_terms = (
        "quit claim",
        "quitclaim",
        "gift deed",
        "family transfer",
        "intra family",
        "foreclosure",
        "sheriff deed",
        "tax deed",
        "tax sale",
        "deed in lieu",
        "corrective deed",
        "correction deed",
    )
    if arms_length_status == "non_market" or any(
        compact_text(term) in normalized_type for term in blocked_terms
    ):
        return "Public evidence indicates a non-market transfer."
    if arms_length_status != "verified" or not arms_length_evidence:
        return "Public evidence does not affirmatively verify an arm's-length transfer."
    return None


def merge_research_comparable_sales(
    provider_records: list[dict[str, Any]],
    research_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    merged = list(provider_records)
    duplicate_count = 0
    for record in research_records:
        if any(same_recorded_sale(record, existing) for existing in merged):
            duplicate_count += 1
            continue
        merged.append(record)
    return merged, duplicate_count


def secondary_conflict_warnings(evidence: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if evidence.get("address_match") == "conflicting":
        warnings.append("Secondary public sources conflict with the subject property address.")
    for conflict in list_of_dicts(evidence.get("conflicts"))[:4]:
        field = string_value(conflict.get("field")) or "property fact"
        explanation = string_value(conflict.get("explanation"))
        warnings.append(
            f"Secondary evidence conflicts on {field}: {explanation or 'review the cited source.'}"
        )
    return warnings


def unavailable_secondary_evidence(reason: str) -> dict[str, Any]:
    return {
        "research_version": "ai_comp_discovery_v1",
        "status": "unavailable",
        "summary": "Secondary public-record research was not added to this analysis.",
        "address_match": "not_checked",
        "subject": {},
        "facts": [],
        "conflicts": [],
        "comparable_candidates": [],
        "valuation_candidate_count": 0,
        "limitations": [reason],
        "sources": [],
    }


def empty_value_estimate(
    subject_record: dict[str, Any],
    error: RentCastClientError | None,
) -> RentCastValueEstimate:
    payload: dict[str, Any] = {
        "price": None,
        "priceRangeLow": None,
        "priceRangeHigh": None,
        "subjectProperty": subject_record,
        "comparables": [],
        "fallbackReason": str(error) if error else "AVM unavailable.",
    }
    return RentCastValueEstimate(
        price=None,
        price_range_low=None,
        price_range_high=None,
        subject_property=subject_record,
        comparables=[],
        raw_response=payload,
    )


def failed_attempt(
    operation: str,
    address: str,
    error: RentCastClientError,
) -> dict[str, Any]:
    return {
        "operation": operation,
        "address": address,
        "status": "failed",
        "provider_status_code": error.status_code,
        "provider_error_code": error.error_code,
        "message": str(error),
    }


def successful_attempt(operation: str, address: str) -> dict[str, Any]:
    return {
        "operation": operation,
        "address": address,
        "status": "succeeded",
    }


def provider_formatted_address(record: dict[str, Any]) -> str | None:
    return string_value(record.get("formattedAddress"))


def normalize_url(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith(("https://", "http://")):
        return ""
    clean, _fragment = urldefrag(value.strip())
    return clean.rstrip("/")


def list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_value(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def positive_number(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return value


def positive_integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def iso_date_value(value: Any) -> str | None:
    text = string_value(value)
    if text is None or len(text) < 10:
        return None
    candidate = text[:10]
    parts = candidate.split("-")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        return None
    try:
        parsed = date.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed > date.today() or (date.today() - parsed).days > 1095:
        return None
    return candidate


def compact_text(value: Any) -> str:
    text = string_value(value) or ""
    return "".join(character for character in text.lower() if character.isalnum())
