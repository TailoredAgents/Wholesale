from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

ProviderBatchStatus = Literal["completed", "failed"]

DEFAULT_PROVIDER_PRIORITY = (
    "manual",
    "rentcast",
    "realestateapi",
    "dealmachine",
    "public",
)
CANONICAL_FIELDS = (
    "formatted_address",
    "sale_price",
    "sale_date",
    "property_type",
    "bedrooms",
    "bathrooms",
    "square_footage",
    "year_built",
    "latitude",
    "longitude",
    "lot_size",
    "garage",
    "garage_spaces",
    "pool",
    "basement",
    "subdivision",
    "transaction_type",
    "transaction_eligibility",
    "transaction_review_reason",
    "distance_miles",
    "match_score",
)
CONFLICT_FIELDS = frozenset(
    {
        "sale_price",
        "sale_date",
        "property_type",
        "bedrooms",
        "bathrooms",
        "square_footage",
        "year_built",
        "latitude",
        "longitude",
        "lot_size",
        "garage",
        "garage_spaces",
        "pool",
        "basement",
        "subdivision",
        "transaction_type",
    }
)

_ADDRESS_TOKEN_MAP = {
    "APARTMENT": "APT",
    "AVENUE": "AVE",
    "BOULEVARD": "BLVD",
    "CIRCLE": "CIR",
    "COURT": "CT",
    "DRIVE": "DR",
    "EAST": "E",
    "HIGHWAY": "HWY",
    "LANE": "LN",
    "NORTH": "N",
    "NORTHEAST": "NE",
    "NORTHWEST": "NW",
    "PARKWAY": "PKWY",
    "PLACE": "PL",
    "ROAD": "RD",
    "SAINT": "ST",
    "SOUTH": "S",
    "SOUTHEAST": "SE",
    "SOUTHWEST": "SW",
    "STREET": "ST",
    "SUITE": "STE",
    "TERRACE": "TER",
    "TRAIL": "TRL",
    "WEST": "W",
}
_SEARCH_LEVEL_ORDER = {"preferred": 0, "expanded": 1, "extended": 2, "manual": 3}


@dataclass(frozen=True)
class ProviderCreditMetadata:
    provider: str
    operation: str
    used: int | None = None
    properties: int | None = None
    people: int | None = None
    deduplicated: int | None = None
    estimated: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "operation": self.operation,
            "used": self.used,
            "properties": self.properties,
            "people": self.people,
            "deduplicated": self.deduplicated,
            "estimated": self.estimated,
            "raw": self.raw,
        }


@dataclass(frozen=True)
class ComparableObservation:
    provider: str
    provider_record_id: str | None
    values: dict[str, Any]
    evidence_source: str
    source_reference: str | None = None
    source_url: str | None = None
    search_level: str | None = None

    def provenance_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "provider_record_id": self.provider_record_id,
            "evidence_source": self.evidence_source,
            "source_reference": self.source_reference,
            "source_url": self.source_url,
            "search_level": self.search_level,
        }


@dataclass(frozen=True)
class ComparableProviderResponse:
    records: Sequence[dict[str, Any]]
    credit_metadata: ProviderCreditMetadata | None = None


@dataclass(frozen=True)
class ComparableProviderBatch:
    provider: str
    status: ProviderBatchStatus
    observations: tuple[ComparableObservation, ...]
    raw_count: int
    usable_count: int
    normalized_count: int = 0
    retained_count: int = 0
    dropped_count: int = 0
    duplicate_count: int = 0
    valuation_eligible_count: int = 0
    ineligible_transfer_count: int = 0
    error: str | None = None
    warnings: tuple[str, ...] = ()
    credit_metadata: ProviderCreditMetadata | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "raw_count": self.raw_count,
            "normalized_count": self.normalized_count,
            "retained_count": self.retained_count,
            "usable_count": self.usable_count,
            "dropped_count": self.dropped_count,
            "duplicate_count": self.duplicate_count,
            "valuation_eligible_count": self.valuation_eligible_count,
            "ineligible_transfer_count": self.ineligible_transfer_count,
            "error": self.error,
            "warnings": list(self.warnings),
            "credit_metadata": (
                self.credit_metadata.to_dict() if self.credit_metadata is not None else None
            ),
        }


@dataclass(frozen=True)
class ComparableFieldConflict:
    field: str
    selected_value: Any
    observations: tuple[dict[str, Any], ...]
    material: bool
    severity: Literal["info", "review", "high"]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "selected_value": self.selected_value,
            "observations": list(self.observations),
            "material": self.material,
            "severity": self.severity,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class MergedComparableEvidence:
    canonical_evidence_id: str
    values: dict[str, Any]
    observations: tuple[ComparableObservation, ...]
    field_conflicts: tuple[ComparableFieldConflict, ...]
    field_provenance: dict[str, tuple[dict[str, Any], ...]]
    primary_observation: ComparableObservation

    @property
    def source_providers(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.provider for item in self.observations))

    @property
    def corroborated(self) -> bool:
        return len(self.source_providers) > 1 and not any(
            conflict.material for conflict in self.field_conflicts
        )

    def to_underwriting_record(self) -> dict[str, Any]:
        values = self.values
        primary = self.primary_observation
        features: dict[str, Any] = {}
        if values.get("garage") is not None:
            features["garage"] = values["garage"]
        if values.get("garage_spaces") is not None:
            features["garageSpaces"] = values["garage_spaces"]
        if values.get("pool") is not None:
            features["pool"] = values["pool"]
        if values.get("basement") is True:
            features["foundationType"] = "Basement"
        if values.get("basement") is not None:
            features["basement"] = values["basement"]

        provider_ids: dict[str, list[str]] = {}
        for observation in self.observations:
            if observation.provider_record_id:
                provider_ids.setdefault(observation.provider, []).append(
                    observation.provider_record_id
                )
        provider_ids = {
            provider: list(dict.fromkeys(ids)) for provider, ids in provider_ids.items()
        }
        conflicts = [item.to_dict() for item in self.field_conflicts]
        provenance = [item.provenance_dict() for item in self.observations]
        field_provenance = {name: list(entries) for name, entries in self.field_provenance.items()}
        search_level = _best_search_level(item.search_level for item in self.observations)
        verification_status = "provider_corroborated" if self.corroborated else "recorded"
        record: dict[str, Any] = {
            "id": primary.provider_record_id or self.canonical_evidence_id,
            "formattedAddress": values.get("formatted_address"),
            "lastSalePrice": values.get("sale_price"),
            "lastSaleDate": values.get("sale_date"),
            "propertyType": values.get("property_type"),
            "bedrooms": values.get("bedrooms"),
            "bathrooms": values.get("bathrooms"),
            "squareFootage": values.get("square_footage"),
            "yearBuilt": values.get("year_built"),
            "latitude": values.get("latitude"),
            "longitude": values.get("longitude"),
            "distance": values.get("distance_miles"),
            "lotSize": values.get("lot_size"),
            "subdivision": values.get("subdivision"),
            "features": features,
            "source_providers": list(self.source_providers),
            "source_overlap_count": len(self.source_providers),
            "field_conflicts": conflicts,
            "corroborated": self.corroborated,
            "evidence_provenance": provenance,
            "transaction_type": values.get("transaction_type"),
            "transaction_eligibility": values.get("transaction_eligibility"),
            "transaction_review_reason": values.get("transaction_review_reason"),
            "_stonegateCanonicalEvidenceId": self.canonical_evidence_id,
            "_stonegateSourceProviders": list(self.source_providers),
            "_stonegateSourceOverlapCount": len(self.source_providers),
            "_stonegateProviderIds": provider_ids,
            "_stonegateProvenance": provenance,
            "_stonegateFieldProvenance": field_provenance,
            "_stonegateFieldConflicts": conflicts,
            "_stonegateCorroborated": self.corroborated,
            "_stonegateEvidenceSource": primary.evidence_source,
            "_stonegateSourceReference": primary.source_reference,
            "_stonegateSourceUrl": primary.source_url,
            "_stonegateVerificationStatus": verification_status,
            "_stonegateSearchLevel": search_level,
            "_stonegateTransactionType": values.get("transaction_type"),
            "_stonegateTransactionEligibility": values.get("transaction_eligibility"),
            "_stonegateTransactionReviewReason": values.get("transaction_review_reason"),
            "_stonegateProviderDistanceMiles": values.get("distance_miles"),
            "_stonegateProviderMatchScore": values.get("match_score"),
        }
        return record


@dataclass(frozen=True)
class ComparableEvidenceSet:
    comparables: tuple[MergedComparableEvidence, ...]
    provider_batches: tuple[ComparableProviderBatch, ...]
    source_observation_count: int
    duplicate_observation_count: int
    field_conflict_count: int

    def to_underwriting_records(self) -> list[dict[str, Any]]:
        return [item.to_underwriting_record() for item in self.comparables]

    def metadata(self) -> dict[str, Any]:
        return {
            "source_observation_count": self.source_observation_count,
            "merged_comparable_count": len(self.comparables),
            "provider_duplicate_count": self.duplicate_observation_count,
            "provider_conflict_count": self.field_conflict_count,
            "providers": [batch.to_dict() for batch in self.provider_batches],
        }


def credit_metadata_from_dealmachine(
    credits: dict[str, Any],
    *,
    operation: str,
    estimated: bool = False,
) -> ProviderCreditMetadata:
    breakdown = credits.get("breakdown")
    values = breakdown if isinstance(breakdown, dict) else credits
    used = _integer(credits.get("used"))
    if used is None:
        used = _integer(credits.get("this_page"))
    deduplicated = _integer(credits.get("deduplicated"))
    if deduplicated is None:
        deduplicated = _integer(values.get("already_accessed"))
    return ProviderCreditMetadata(
        provider="dealmachine",
        operation=operation,
        used=used,
        properties=_integer(values.get("properties")),
        people=_integer(values.get("people")),
        deduplicated=deduplicated,
        estimated=estimated,
        raw=dict(credits),
    )


def capture_provider_batch(
    *,
    provider: str,
    fetch: Callable[[], ComparableProviderResponse],
    normalizer: Callable[[dict[str, Any]], ComparableObservation | None],
) -> ComparableProviderBatch:
    """Run one optional provider without allowing its failure to abort other providers."""
    try:
        response = fetch()
    except Exception as exc:  # noqa: BLE001 - isolation is the purpose of this boundary.
        message = str(exc).strip() or exc.__class__.__name__
        return ComparableProviderBatch(
            provider=provider,
            status="failed",
            observations=(),
            raw_count=0,
            usable_count=0,
            error=message[:1000],
        )
    return provider_batch_from_response(
        provider=provider,
        response=response,
        normalizer=normalizer,
    )


def provider_batch_from_response(
    *,
    provider: str,
    response: ComparableProviderResponse,
    normalizer: Callable[[dict[str, Any]], ComparableObservation | None],
) -> ComparableProviderBatch:
    observations: list[ComparableObservation] = []
    warnings: list[str] = []
    for index, record in enumerate(response.records):
        try:
            observation = normalizer(record)
        except (TypeError, ValueError) as exc:
            warnings.append(f"Record {index + 1} was ignored: {str(exc)[:300]}")
            continue
        if observation is None:
            warnings.append(
                f"Record {index + 1} was ignored because it did not normalize to a "
                "usable closed sale."
            )
            continue
        if observation.provider != provider:
            raise ValueError(
                f"Comparable normalizer returned provider {observation.provider!r}; "
                f"expected {provider!r}."
            )
        observations.append(observation)
    normalized_count = len(observations)
    observations = _deduplicate_provider_observations(observations)
    retained_count = len(observations)
    ineligible_transfer_count = sum(
        item.values.get("transaction_eligibility") == "ineligible" for item in observations
    )
    valuation_eligible_count = retained_count - ineligible_transfer_count
    return ComparableProviderBatch(
        provider=provider,
        status="completed",
        observations=tuple(observations),
        raw_count=len(response.records),
        usable_count=valuation_eligible_count,
        normalized_count=normalized_count,
        retained_count=retained_count,
        dropped_count=len(response.records) - normalized_count,
        duplicate_count=normalized_count - retained_count,
        valuation_eligible_count=valuation_eligible_count,
        ineligible_transfer_count=ineligible_transfer_count,
        warnings=tuple(warnings),
        credit_metadata=response.credit_metadata,
    )


def normalize_rentcast_comparable(
    record: dict[str, Any],
    *,
    search_level: str | None = None,
) -> ComparableObservation | None:
    features = record.get("features")
    feature_values = features if isinstance(features, dict) else {}
    foundation_type = _string(feature_values.get("foundationType"))
    transaction_type = _string(record.get("lastSaleDocumentType"))
    transaction_eligibility, transaction_review_reason = _transaction_evidence(
        record,
        transaction_type=transaction_type,
        sale_price=_integer(record.get("lastSalePrice")),
    )
    values = {
        "formatted_address": _string(record.get("formattedAddress")),
        "sale_price": _integer(record.get("lastSalePrice")),
        "sale_date": _date_string(record.get("lastSaleDate")),
        "property_type": _property_type(record.get("propertyType")),
        "bedrooms": _number(record.get("bedrooms")),
        "bathrooms": _number(record.get("bathrooms")),
        "square_footage": _integer(record.get("squareFootage")),
        "year_built": _integer(record.get("yearBuilt")),
        "latitude": _number(record.get("latitude")),
        "longitude": _number(record.get("longitude")),
        "lot_size": _integer(record.get("lotSize")),
        "garage": _boolean(feature_values.get("garage")),
        "garage_spaces": _number(feature_values.get("garageSpaces")),
        "pool": _boolean(feature_values.get("pool")),
        "basement": (
            "basement" in foundation_type.lower() if foundation_type is not None else None
        ),
        "subdivision": _string(record.get("subdivision")),
        "transaction_type": transaction_type,
        "transaction_eligibility": transaction_eligibility,
        "transaction_review_reason": transaction_review_reason,
        "distance_miles": _number(record.get("distance")),
        "match_score": None,
    }
    if not values["formatted_address"]:
        return None
    provider_id = _string(record.get("id"))
    return ComparableObservation(
        provider="rentcast",
        provider_record_id=provider_id,
        values=values,
        evidence_source=(
            _string(record.get("_stonegateEvidenceSource")) or "rentcast_property_record"
        ),
        source_reference=(_string(record.get("_stonegateSourceReference")) or provider_id),
        source_url=_string(record.get("_stonegateSourceUrl")),
        search_level=(
            _normalize_search_level(record.get("_stonegateSearchLevel"))
            or _normalize_search_level(search_level)
        ),
    )


def normalize_dealmachine_comparable(
    record: dict[str, Any],
    *,
    search_level: str | None = None,
) -> ComparableObservation | None:
    comp_type = (_string(record.get("type")) or "sale").lower()
    if comp_type not in {"sale", "closed_sale", "sold"}:
        return None
    sale_price = _integer(_first(record, "sale_price", "last_sale_price", "sold_price"))
    sale_date = _date_string(
        _first(record, "sale_date", "last_sale_date", "sold_date", "recording_date")
    )
    if sale_price is None or sale_price <= 0 or sale_date is None:
        return None
    lot_size = _integer(_first(record, "lot_size_sqft", "lot_size", "lot_sqft"))
    if lot_size is None:
        acres = _number(record.get("lot_size_acres"))
        lot_size = round(acres * 43_560) if acres is not None and acres >= 0 else None
    match_score = record.get("match_score")
    if isinstance(match_score, dict):
        match_score = match_score.get("overall")
    transaction_type = _property_type(
        _first(record, "sale_doc_type", "last_sale_doc_type", "transaction_type")
    )
    transaction_eligibility, transaction_review_reason = _transaction_evidence(
        record,
        transaction_type=transaction_type,
        sale_price=sale_price,
    )
    values = {
        "formatted_address": _dealmachine_address(record),
        "sale_price": sale_price,
        "sale_date": sale_date,
        "property_type": _property_type(_first(record, "property_type", "propertyType")),
        "bedrooms": _number(_first(record, "bedrooms", "num_bedrooms")),
        "bathrooms": _number(_first(record, "bathrooms", "num_bathrooms")),
        "square_footage": _integer(_first(record, "sqft", "living_area_sqft", "square_footage")),
        "year_built": _integer(_first(record, "year_built", "yearBuilt")),
        "latitude": _number(_first(record, "latitude", "lat")),
        "longitude": _number(_first(record, "longitude", "lng", "lon")),
        "lot_size": lot_size,
        "garage": _feature_present(_first(record, "garage", "garage_type")),
        "garage_spaces": _number(_first(record, "garage_spaces", "garage_count")),
        "pool": _feature_present(record.get("pool")),
        "basement": _feature_present(record.get("basement")),
        "subdivision": _string(_first(record, "subdivision_name", "subdivision")),
        "transaction_type": transaction_type,
        "transaction_eligibility": transaction_eligibility,
        "transaction_review_reason": transaction_review_reason,
        "distance_miles": _number(_first(record, "distance", "distance_miles")),
        "match_score": _number(match_score),
    }
    if not values["formatted_address"]:
        return None
    provider_id = _string(_first(record, "dm_property_id", "property_id", "id"))
    return ComparableObservation(
        provider="dealmachine",
        provider_record_id=provider_id,
        values=values,
        evidence_source="dealmachine_comps_closed_sale",
        source_reference=provider_id,
        source_url=_string(_first(record, "source_url", "url")),
        search_level=_normalize_search_level(search_level),
    )


def normalize_realestateapi_comparable(
    record: dict[str, Any],
    *,
    search_level: str | None = None,
) -> ComparableObservation | None:
    sale_price = _integer(
        _first(record, "lastSaleAmount", "lastSalePrice", "saleAmount", "salePrice")
    )
    sale_date = _date_string(_first(record, "lastSaleDate", "saleDate", "recordingDate"))
    if sale_price is None or sale_price <= 0 or sale_date is None:
        return None
    address = record.get("address")
    address_values = address if isinstance(address, dict) else {}
    formatted_address = _realestateapi_address(record, address_values)
    if not formatted_address:
        return None
    transaction_type = _string(
        _first(record, "lastSaleDocumentType", "documentType", "transactionType")
    )
    transaction_eligibility, transaction_review_reason = _transaction_evidence(
        record,
        transaction_type=transaction_type,
        sale_price=sale_price,
    )
    lot_size = _integer(_first(record, "lotSquareFeet", "lotSize", "lotSqft"))
    values = {
        "formatted_address": formatted_address,
        "sale_price": sale_price,
        "sale_date": sale_date,
        "property_type": _property_type(_first(record, "propertyType", "landUse")),
        "bedrooms": _number(record.get("bedrooms")),
        "bathrooms": _number(record.get("bathrooms")),
        "square_footage": _integer(_first(record, "squareFeet", "livingSquareFeet", "livingArea")),
        "year_built": _integer(record.get("yearBuilt")),
        "latitude": _number(record.get("latitude") or address_values.get("latitude")),
        "longitude": _number(record.get("longitude") or address_values.get("longitude")),
        "lot_size": lot_size,
        "garage": _feature_present(record.get("garage")),
        "garage_spaces": _number(record.get("garageSpaces")),
        "pool": _feature_present(record.get("pool")),
        "basement": _feature_present(record.get("basement")),
        "subdivision": _string(record.get("subdivision")),
        "transaction_type": transaction_type,
        "transaction_eligibility": transaction_eligibility,
        "transaction_review_reason": transaction_review_reason,
        "distance_miles": _number(record.get("distance")),
        "match_score": _number(record.get("similarity") or record.get("score")),
    }
    provider_id = _string(_first(record, "propertyId", "id", "priorId"))
    return ComparableObservation(
        provider="realestateapi",
        provider_record_id=provider_id,
        values=values,
        evidence_source="realestateapi_public_record_closed_sale",
        source_reference=provider_id,
        source_url=None,
        search_level=_normalize_search_level(search_level),
    )


def _realestateapi_address(
    record: Mapping[str, Any],
    address: Mapping[str, Any],
) -> str | None:
    direct = _string(
        _first_mapping(record, "formattedAddress", "fullAddress")
        or _first_mapping(address, "formattedAddress", "fullAddress")
    )
    if direct:
        return direct
    street = _string(
        _first_mapping(address, "address", "addressLine1", "streetAddress")
        or _first_mapping(record, "addressLine1", "streetAddress")
    )
    if not street:
        house = _string(address.get("house"))
        street_name = _string(address.get("street"))
        street = " ".join(value for value in (house, street_name) if value) or None
    city = _string(address.get("city") or record.get("city"))
    state = _string(address.get("state") or record.get("state"))
    postal_code = _string(
        _first_mapping(address, "zip", "zipCode", "postalCode")
        or _first_mapping(record, "zip", "zipCode", "postalCode")
    )
    if not street:
        return None
    locality = ", ".join(value for value in (city, state) if value)
    return ", ".join(value for value in (street, locality) if value) + (
        f" {postal_code}" if postal_code else ""
    )


def merge_comparable_batches(
    batches: Sequence[ComparableProviderBatch],
    *,
    provider_priority: Sequence[str] = DEFAULT_PROVIDER_PRIORITY,
) -> ComparableEvidenceSet:
    observations = [
        observation
        for batch in batches
        if batch.status == "completed"
        for observation in batch.observations
    ]
    groups = _group_same_sale_observations(observations, provider_priority)
    comparables = tuple(_merge_observation_group(group, provider_priority) for group in groups)
    comparables = tuple(
        sorted(
            comparables,
            key=lambda item: (
                item.values.get("sale_date") or "",
                item.values.get("formatted_address") or "",
                item.canonical_evidence_id,
            ),
            reverse=True,
        )
    )
    conflicts = sum(conflict.material for item in comparables for conflict in item.field_conflicts)
    return ComparableEvidenceSet(
        comparables=comparables,
        provider_batches=tuple(batches),
        source_observation_count=len(observations),
        duplicate_observation_count=max(0, len(observations) - len(comparables)),
        field_conflict_count=conflicts,
    )


def normalize_address_key(value: str | None) -> str:
    if not value:
        return ""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    ascii_value = re.sub(r"\b(\d{5})-\d{4}\b", r"\1", ascii_value)
    tokens = re.findall(r"[A-Z0-9]+", ascii_value.upper())
    normalized: list[str] = []
    for token in tokens:
        normalized.append(_ADDRESS_TOKEN_MAP.get(token, token))
    return " ".join(normalized)


def same_recorded_sale(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """Match probable representations of one transfer across evidence sources."""
    left_address = normalize_address_key(_sale_record_address(left))
    right_address = normalize_address_key(_sale_record_address(right))
    if not left_address or left_address != right_address:
        return False
    left_date = _parse_date(_first_mapping(left, "lastSaleDate", "sale_date"))
    right_date = _parse_date(_first_mapping(right, "lastSaleDate", "sale_date"))
    left_price = _number(_first_mapping(left, "lastSalePrice", "sale_price_dollars"))
    right_price = _number(_first_mapping(right, "lastSalePrice", "sale_price_dollars"))
    return _probable_same_transfer(left_date, right_date, left_price, right_price)


def _sale_record_address(record: Mapping[str, Any]) -> str | None:
    direct = _first_mapping(
        record,
        "formattedAddress",
        "formatted_address",
        "full_address",
    )
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    street = _first_mapping(record, "addressLine1", "address_line1", "street_address")
    city = _first_mapping(record, "city")
    state = _first_mapping(record, "state")
    postal_code = _first_mapping(record, "zipCode", "postal_code", "zip")
    parts = [
        value.strip() for value in (street, city, state, postal_code) if isinstance(value, str)
    ]
    return ", ".join(parts) if parts else None


def _first_mapping(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if record.get(key) is not None:
            return record[key]
    return None


def _group_same_sale_observations(
    observations: Sequence[ComparableObservation],
    provider_priority: Sequence[str],
) -> list[list[ComparableObservation]]:
    priority = {provider: index for index, provider in enumerate(provider_priority)}
    ordered = sorted(
        observations,
        key=lambda item: (
            normalize_address_key(_string(item.values.get("formatted_address"))),
            _string(item.values.get("sale_date")) or "",
            _integer(item.values.get("sale_price")) or 0,
            priority.get(item.provider, len(priority)),
            item.provider_record_id or "",
        ),
    )
    groups: list[list[ComparableObservation]] = []
    for observation in ordered:
        matching = [
            index
            for index, group in enumerate(groups)
            if any(_same_sale(observation, existing) for existing in group)
        ]
        if not matching:
            groups.append([observation])
            continue
        target = matching[0]
        groups[target].append(observation)
        for extra_index in reversed(matching[1:]):
            groups[target].extend(groups.pop(extra_index))
    return groups


def _same_sale(left: ComparableObservation, right: ComparableObservation) -> bool:
    left_address = normalize_address_key(_string(left.values.get("formatted_address")))
    right_address = normalize_address_key(_string(right.values.get("formatted_address")))
    if not left_address or left_address != right_address:
        return False
    left_date = _parse_date(left.values.get("sale_date"))
    right_date = _parse_date(right.values.get("sale_date"))
    left_price = _integer(left.values.get("sale_price"))
    right_price = _integer(right.values.get("sale_price"))
    return _probable_same_transfer(left_date, right_date, left_price, right_price)


def _probable_same_transfer(
    left_date: date | None,
    right_date: date | None,
    left_price: float | int | None,
    right_price: float | int | None,
) -> bool:
    """Use a review band wider than conflict tolerances to prevent double weighting."""
    if left_date is not None and right_date is not None:
        date_difference = abs((left_date - right_date).days)
        if date_difference == 0:
            return True
        if date_difference > 31:
            return False
        if left_price is None or right_price is None:
            return True
        largest_price = max(abs(float(left_price)), abs(float(right_price)))
        if largest_price == 0:
            return True
        return abs(float(left_price) - float(right_price)) / largest_price <= 0.20
    if left_price is None or right_price is None:
        return False
    tolerance = max(1_000.0, max(abs(float(left_price)), abs(float(right_price))) * 0.01)
    return abs(float(left_price) - float(right_price)) <= tolerance


def _merge_observation_group(
    observations: Sequence[ComparableObservation],
    provider_priority: Sequence[str],
) -> MergedComparableEvidence:
    priority = {provider: index for index, provider in enumerate(provider_priority)}
    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (
                priority.get(item.provider, len(priority)),
                item.provider_record_id or "",
            ),
        )
    )
    values: dict[str, Any] = {}
    conflicts: list[ComparableFieldConflict] = []
    provenance: dict[str, tuple[dict[str, Any], ...]] = {}
    for field_name in CANONICAL_FIELDS:
        available = [
            (item, item.values.get(field_name))
            for item in ordered
            if item.values.get(field_name) is not None
        ]
        if not available:
            values[field_name] = None
            continue
        selected, groups = _select_consensus_value(
            field_name,
            available,
            priority,
        )
        values[field_name] = selected
        provenance[field_name] = tuple(
            {
                "provider": item.provider,
                "provider_record_id": item.provider_record_id,
                "value": value,
            }
            for item, value in available
        )
        if field_name in CONFLICT_FIELDS and len(groups) > 1:
            material, severity, summary = _conflict_materiality(
                field_name,
                [value for _observation, value in available],
            )
            conflicts.append(
                ComparableFieldConflict(
                    field=field_name,
                    selected_value=selected,
                    observations=provenance[field_name],
                    material=material,
                    severity=severity,
                    summary=summary,
                )
            )
    if values.get("transaction_eligibility") == "ineligible":
        ineligible_reason = next(
            (
                item.values.get("transaction_review_reason")
                for item in ordered
                if item.values.get("transaction_eligibility") == "ineligible"
                and item.values.get("transaction_review_reason")
            ),
            values.get("transaction_review_reason"),
        )
        values["transaction_review_reason"] = ineligible_reason
    identity = "|".join(
        (
            normalize_address_key(_string(values.get("formatted_address"))),
            _string(values.get("sale_date")) or "",
            str(_integer(values.get("sale_price")) or ""),
        )
    )
    if not identity.strip("|"):
        identity = "|".join(f"{item.provider}:{item.provider_record_id or ''}" for item in ordered)
    canonical_id = f"sale_{hashlib.sha256(identity.encode()).hexdigest()[:20]}"
    return MergedComparableEvidence(
        canonical_evidence_id=canonical_id,
        values=values,
        observations=ordered,
        field_conflicts=tuple(conflicts),
        field_provenance=provenance,
        primary_observation=ordered[0],
    )


def _select_consensus_value(
    field_name: str,
    available: Sequence[tuple[ComparableObservation, Any]],
    provider_priority: dict[str, int],
) -> tuple[Any, dict[str, list[tuple[ComparableObservation, Any]]]]:
    groups: dict[str, list[tuple[ComparableObservation, Any]]] = {}
    for observation, value in available:
        groups.setdefault(_semantic_value_key(field_name, value), []).append((observation, value))

    if field_name == "transaction_eligibility" and "ineligible" in groups:
        return "ineligible", groups

    def group_rank(
        item: tuple[str, list[tuple[ComparableObservation, Any]]],
    ) -> tuple[int, int, str]:
        key, members = item
        distinct_providers = len({observation.provider for observation, _value in members})
        best_priority = min(
            provider_priority.get(observation.provider, len(provider_priority))
            for observation, _value in members
        )
        return (-distinct_providers, best_priority, key)

    _selected_key, selected_members = min(groups.items(), key=group_rank)
    selected_observation, selected_value = min(
        selected_members,
        key=lambda item: (
            provider_priority.get(item[0].provider, len(provider_priority)),
            item[0].provider_record_id or "",
        ),
    )
    del selected_observation
    return selected_value, groups


def _semantic_value_key(field_name: str, value: Any) -> str:
    if field_name == "formatted_address":
        return normalize_address_key(_string(value))
    if field_name == "sale_date":
        return _date_string(value) or ""
    if isinstance(value, float):
        return f"{value:.6f}"
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip().casefold()
    return json.dumps(value, sort_keys=True, default=str)


def _conflict_materiality(
    field_name: str,
    values: Sequence[Any],
) -> tuple[bool, Literal["info", "review", "high"], str]:
    """Classify a preserved cross-provider difference by underwriting impact."""
    if field_name == "sale_date":
        parsed = [parsed_date for value in values if (parsed_date := _parse_date(value))]
        if len(parsed) == len(values) and parsed:
            span_days = (max(parsed) - min(parsed)).days
            if span_days <= 7:
                return (
                    False,
                    "review",
                    (
                        f"Provider recording dates differ by {span_days} day(s), "
                        "within policy tolerance."
                    ),
                )
            return (
                True,
                "high",
                f"Provider sale dates differ by {span_days} days.",
            )
        return True, "high", "Provider sale dates could not be reconciled."

    numeric_values = [
        numeric_value for value in values if (numeric_value := _number(value)) is not None
    ]
    if len(numeric_values) == len(values) and numeric_values:
        span = max(numeric_values) - min(numeric_values)
        maximum = max(abs(item) for item in numeric_values)
        if field_name == "sale_price":
            tolerance = max(1_000.0, maximum * 0.01)
            if span <= tolerance:
                return (
                    False,
                    "review",
                    "Provider sale prices differ only within the $1,000 / 1% policy tolerance.",
                )
            return True, "high", f"Provider sale prices differ by ${span:,.0f}."
        if field_name == "square_footage":
            tolerance = max(50.0, maximum * 0.02)
            if span < tolerance:
                return (
                    False,
                    "info",
                    "Provider living-area figures differ only within the 50 sq ft / 2% tolerance.",
                )
            return True, "high", f"Provider living-area figures differ by {span:,.0f} sq ft."
        if field_name == "lot_size":
            tolerance = max(500.0, maximum * 0.05)
            if span < tolerance:
                return (
                    False,
                    "info",
                    "Provider lot-size figures differ only within the 500 sq ft / 5% tolerance.",
                )
            return True, "review", f"Provider lot-size figures differ by {span:,.0f} sq ft."
        if field_name in {"latitude", "longitude"}:
            if span < 0.001:
                return (
                    False,
                    "info",
                    "Provider coordinates differ only within the 0.001-degree tolerance.",
                )
            return True, "review", "Provider coordinates identify materially different points."
        if field_name in {"bedrooms", "bathrooms"}:
            if span < 0.5:
                return False, "info", "Provider room counts differ only by rounding."
            return True, "high", f"Provider {field_name.replace('_', ' ')} counts differ."
        if field_name == "year_built":
            if span <= 2:
                return False, "info", "Provider year-built figures are within two years."
            return True, "review", f"Provider year-built figures differ by {span:,.0f} years."
        if field_name == "garage_spaces":
            if span < 1:
                return False, "info", "Provider garage-space counts differ only by rounding."
            return True, "review", "Provider garage-space counts differ by at least one space."

    if field_name == "transaction_type":
        return (
            False,
            "review",
            "Provider document labels differ; transfer eligibility is evaluated separately.",
        )
    if field_name == "subdivision":
        return True, "review", "Providers assign the sale to different subdivisions."
    if field_name in {"property_type", "garage", "pool", "basement"}:
        return True, "high", f"Providers disagree on {field_name.replace('_', ' ')}."
    return True, "high", f"Providers report different {field_name.replace('_', ' ')} values."


def _deduplicate_provider_observations(
    observations: Sequence[ComparableObservation],
) -> list[ComparableObservation]:
    unique: dict[str, ComparableObservation] = {}
    for observation in observations:
        identity = (
            f"id:{observation.provider_record_id}"
            if observation.provider_record_id
            else "|".join(
                (
                    normalize_address_key(_string(observation.values.get("formatted_address"))),
                    _string(observation.values.get("sale_date")) or "",
                    str(_integer(observation.values.get("sale_price")) or ""),
                )
            )
        )
        current = unique.get(identity)
        if current is None or _search_level_rank(observation.search_level) < _search_level_rank(
            current.search_level
        ):
            unique[identity] = observation
    return list(unique.values())


def _best_search_level(values: Iterable[str | None]) -> str | None:
    present = [value for value in values if value]
    return min(present, key=_search_level_rank) if present else None


def _search_level_rank(value: str | None) -> int:
    return _SEARCH_LEVEL_ORDER.get(value or "", len(_SEARCH_LEVEL_ORDER))


def _normalize_search_level(value: object) -> str | None:
    normalized = (_string(value) or "").lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in _SEARCH_LEVEL_ORDER else None


def _dealmachine_address(record: dict[str, Any]) -> str | None:
    for key in ("full_address", "formatted_address"):
        value = _string(record.get(key))
        if value:
            return value
    raw_address = record.get("address")
    if isinstance(raw_address, dict):
        nested = _dealmachine_address(raw_address)
        if nested:
            return nested
        raw_address = raw_address.get("street")
    street = _string(record.get("display_line_1")) or _string(raw_address)
    city = _string(record.get("city"))
    state = _string(record.get("state"))
    postal_code = _string(_first(record, "zip", "postal_code"))
    locality = ", ".join(item for item in (city, state) if item)
    if postal_code:
        locality = f"{locality} {postal_code}".strip()
    if street and locality:
        return f"{street}, {locality}"
    return street or locality or None


def _feature_present(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (list, tuple, set)):
        normalized = [_feature_present(item) for item in value]
        known = [item for item in normalized if item is not None]
        return any(known) if known else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value > 0
    text = _string(value)
    if not text:
        return None
    normalized_text = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    if normalized_text in {
        "unknown",
        "n a",
        "na",
        "not available",
        "unspecified",
        "not reported",
        "not provided",
        "tbd",
    }:
        return None
    if normalized_text in {"no", "none", "false", "n", "0", "not present", "absent"}:
        return False
    if re.match(r"^(?:no|without|zero)\b", normalized_text):
        return False
    if re.match(r"^0\b", normalized_text):
        return False
    return "does not have" not in normalized_text


def _property_type(value: Any) -> str | None:
    if isinstance(value, (list, tuple)):
        value = next((item for item in value if _string(item)), None)
    return _string(value)


def _transaction_evidence(
    record: Mapping[str, Any],
    *,
    transaction_type: str | None,
    sale_price: int | None,
) -> tuple[str, str | None]:
    explicit_foreclosure = any(
        record.get(key) is True
        for key in (
            "foreclosure",
            "is_foreclosure",
            "sale_is_foreclosure",
            "foreclosure_sale",
        )
    )
    explicit_non_arms_length = any(
        record.get(key) is True
        for key in ("non_arms_length", "is_non_arms_length", "family_transfer")
    ) or any(
        record.get(key) is False
        for key in ("arms_length", "is_arms_length", "arm_length")
        if key in record
    )
    normalized_type = re.sub(
        r"[^a-z0-9]+",
        " ",
        (transaction_type or "").casefold(),
    ).strip()
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
    if explicit_foreclosure:
        return "ineligible", "Provider marked the transfer as a foreclosure."
    if explicit_non_arms_length:
        return "ineligible", "Provider marked the transfer as non-arm's-length."
    if any(term in normalized_type for term in blocked_terms):
        return (
            "ineligible",
            f"Recorded document type {transaction_type} indicates a non-market transfer.",
        )
    if sale_price is not None and 0 < sale_price < 10_000:
        return (
            "ineligible",
            "Recorded consideration is nominal and is not treated as an ordinary market sale.",
        )
    if transaction_type:
        return "not_flagged", None
    return (
        "unverified",
        "Arm's-length status is not available from the structured provider record.",
    )


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None:
            return value
    return None


def _string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _integer(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value)
    if isinstance(value, str):
        normalized = value.strip().replace(",", "").replace("$", "")
        try:
            return round(float(normalized))
        except ValueError:
            return None
    return None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.strip().replace(",", "").replace("$", "")
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return _feature_present(value)


def _date_string(value: Any) -> str | None:
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed is not None else None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    try:
        return date.fromisoformat(normalized[:10])
    except ValueError:
        return None
