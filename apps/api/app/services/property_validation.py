import re
import unicodedata
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any

from app.models.foundation import Property

STREET_SUFFIXES = {
    "avenue": "ave",
    "boulevard": "blvd",
    "circle": "cir",
    "court": "ct",
    "drive": "dr",
    "highway": "hwy",
    "lane": "ln",
    "parkway": "pkwy",
    "place": "pl",
    "road": "rd",
    "street": "st",
    "terrace": "ter",
    "trail": "trl",
}
DIRECTIONS = {
    "north": "n",
    "south": "s",
    "east": "e",
    "west": "w",
    "northeast": "ne",
    "northwest": "nw",
    "southeast": "se",
    "southwest": "sw",
}
UNIT_MARKERS = {"apartment": "unit", "apt": "unit", "suite": "unit", "ste": "unit", "#": "unit"}
SUBJECT_FACT_FIELDS = (
    "propertyType",
    "bedrooms",
    "bathrooms",
    "squareFootage",
    "lotSize",
    "yearBuilt",
    "lastSaleDate",
    "lastSalePrice",
    "latitude",
    "longitude",
    "county",
    "countyFips",
    "stateFips",
)


def canonical_address_key(
    street_address: str,
    city: str,
    state: str,
    postal_code: str,
) -> str:
    return "|".join(
        (
            normalize_street(street_address),
            normalize_words(city),
            normalize_words(state).upper(),
            normalize_postal_code(postal_code),
        )
    )


def validate_provider_record(
    property_record: Property,
    provider_record: dict[str, Any],
    *,
    provider: str = "rentcast",
) -> dict[str, Any]:
    requested = {
        "street_address": property_record.street_address.strip(),
        "city": property_record.city.strip(),
        "state": property_record.state.strip().upper(),
        "postal_code": normalize_postal_code(property_record.postal_code),
    }
    provider_components = provider_address_components(provider_record)
    validated_at = datetime.now(UTC)
    if not provider_components["street_address"]:
        metadata = {
            "requested": requested,
            "provider": provider_components,
            "match_score": 0,
            "issues": ["No property record was returned for the entered address."],
            "facts": {},
        }
        set_validation_fields(
            property_record,
            status="not_found",
            provider=provider,
            provider_property_id=None,
            formatted_address=None,
            validated_at=validated_at,
            metadata=metadata,
        )
        return metadata

    score, issues = address_match_score(requested, provider_components)
    status = "provider_confirmed" if score >= 90 and not issues else "needs_review"
    facts = {
        key: provider_record[key]
        for key in SUBJECT_FACT_FIELDS
        if provider_record.get(key) is not None
    }
    metadata = {
        "requested": requested,
        "provider": provider_components,
        "match_score": score,
        "issues": issues,
        "facts": facts,
    }
    set_validation_fields(
        property_record,
        status=status,
        provider=provider,
        provider_property_id=string_value(provider_record.get("id")),
        formatted_address=string_value(provider_record.get("formattedAddress")),
        validated_at=validated_at,
        metadata=metadata,
    )
    return metadata


def reset_property_validation(property_record: Property) -> None:
    property_record.address_validation_status = "unverified"
    property_record.address_validation_provider = None
    property_record.provider_property_id = None
    property_record.validated_formatted_address = None
    property_record.address_validated_at = None
    property_record.address_validation_metadata = None


def provider_address_components(record: dict[str, Any]) -> dict[str, str]:
    address_line_1 = string_value(record.get("addressLine1")) or ""
    address_line_2 = string_value(record.get("addressLine2"))
    street_address = " ".join(value for value in (address_line_1, address_line_2) if value)
    formatted_address = string_value(record.get("formattedAddress")) or ""
    fallback = parse_formatted_address(formatted_address)
    return {
        "street_address": street_address or fallback["street_address"],
        "city": string_value(record.get("city")) or fallback["city"],
        "state": (string_value(record.get("state")) or fallback["state"]).upper(),
        "postal_code": normalize_postal_code(
            string_value(record.get("zipCode")) or fallback["postal_code"]
        ),
        "formatted_address": formatted_address,
    }


def parse_formatted_address(value: str) -> dict[str, str]:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if len(parts) < 3:
        return {"street_address": "", "city": "", "state": "", "postal_code": ""}
    state_and_zip = parts[-1].split()
    return {
        "street_address": ", ".join(parts[:-2]),
        "city": parts[-2],
        "state": state_and_zip[0] if state_and_zip else "",
        "postal_code": state_and_zip[1] if len(state_and_zip) > 1 else "",
    }


def address_match_score(
    requested: dict[str, str],
    provider: dict[str, str],
) -> tuple[int, list[str]]:
    requested_street = normalize_street(requested["street_address"])
    provider_street = normalize_street(provider["street_address"])
    requested_number = first_street_number(requested_street)
    provider_number = first_street_number(provider_street)
    street_similarity = SequenceMatcher(None, requested_street, provider_street).ratio()
    score = round(street_similarity * 35)
    issues: list[str] = []

    if requested_number and provider_number and requested_number == provider_number:
        score += 35
    else:
        issues.append("Street number does not match the provider record.")
    if normalize_words(requested["city"]) == normalize_words(provider["city"]):
        score += 10
    else:
        issues.append("City differs from the provider record.")
    if requested["state"].upper() == provider["state"].upper():
        score += 10
    else:
        issues.append("State differs from the provider record.")
    if normalize_postal_code(requested["postal_code"]) == normalize_postal_code(
        provider["postal_code"]
    ):
        score += 10
    else:
        issues.append("ZIP code differs from the provider record.")
    if street_similarity < 0.75:
        issues.append("Street name or unit differs materially from the provider record.")
    return max(0, min(100, score)), issues


def normalize_street(value: str) -> str:
    tokens = normalize_words(value).split()
    return " ".join(
        STREET_SUFFIXES.get(token, DIRECTIONS.get(token, UNIT_MARKERS.get(token, token)))
        for token in tokens
    )


def normalize_words(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    cleaned = re.sub(r"[^a-zA-Z0-9#]+", " ", ascii_value.lower())
    return " ".join(cleaned.split())


def normalize_postal_code(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    return digits[:5]


def first_street_number(value: str) -> str | None:
    match = re.match(r"^(\d+[a-z]?)\b", value)
    return match.group(1) if match else None


def string_value(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def set_validation_fields(
    property_record: Property,
    *,
    status: str,
    provider: str,
    provider_property_id: str | None,
    formatted_address: str | None,
    validated_at: datetime,
    metadata: dict[str, Any],
) -> None:
    property_record.address_validation_status = status
    property_record.address_validation_provider = provider
    property_record.provider_property_id = provider_property_id
    property_record.validated_formatted_address = formatted_address
    property_record.address_validated_at = validated_at
    property_record.address_validation_metadata = metadata
