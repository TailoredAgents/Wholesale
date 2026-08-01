from __future__ import annotations

from datetime import date
from typing import Any

CATALOG_VERSION = "ga-2026.07-v1"
MARKET_KEY = "ga_atlanta"
MARKET_LABEL = "Georgia / Metro Atlanta"
EFFECTIVE_DATE = date(2026, 7, 31)
CATALOG_SOURCE_NOTE = (
    "Stonegate internal Georgia planning allowances. These are versioned acquisition-screening "
    "ranges, not contractor quotes. Calibrate them with walkthroughs, written bids, and completed "
    "project outcomes before expanding market coverage."
)


def _rate(low: int, expected: int, high: int) -> dict[str, int]:
    return {
        "low_cents": low * 100,
        "expected_cents": expected * 100,
        "high_cents": high * 100,
    }


CATALOG: dict[str, dict[str, Any]] = {
    "roof": {
        "label": "Roof",
        "unit": "roof_square",
        "quantity_basis": "subject living area x 1.15 / 100; verify roof geometry",
        "repair": _rate(175, 325, 500),
        "replace": _rate(450, 625, 850),
        "minimum_cents": 1_500_00,
        "specialist_recommended": False,
    },
    "hvac": {
        "label": "HVAC",
        "unit": "system",
        "quantity_basis": "one system unless field evidence confirms more",
        "repair": _rate(750, 1_750, 3_500),
        "replace": _rate(6_000, 8_500, 12_500),
        "minimum_cents": 750_00,
        "specialist_recommended": False,
    },
    "plumbing": {
        "label": "Plumbing",
        "unit": "project",
        "quantity_basis": "one project allowance",
        "repair": _rate(1_500, 4_000, 8_000),
        "replace": _rate(8_000, 15_000, 28_000),
        "minimum_cents": 1_000_00,
        "specialist_recommended": True,
    },
    "electrical": {
        "label": "Electrical",
        "unit": "project",
        "quantity_basis": "one project allowance",
        "repair": _rate(1_500, 4_000, 8_000),
        "replace": _rate(10_000, 18_000, 30_000),
        "minimum_cents": 1_000_00,
        "specialist_recommended": True,
    },
    "foundation": {
        "label": "Foundation",
        "unit": "project",
        "quantity_basis": "one project allowance; specialist scope required",
        "repair": _rate(3_000, 10_000, 25_000),
        "replace": _rate(20_000, 45_000, 85_000),
        "minimum_cents": 2_500_00,
        "specialist_recommended": True,
    },
    "kitchen": {
        "label": "Kitchen",
        "unit": "kitchen",
        "quantity_basis": "one kitchen unless field evidence confirms more",
        "repair": _rate(7_500, 14_000, 22_000),
        "replace": _rate(22_000, 35_000, 55_000),
        "minimum_cents": 5_000_00,
        "specialist_recommended": False,
    },
    "bathrooms": {
        "label": "Bathrooms",
        "unit": "bathroom",
        "quantity_basis": "subject bathroom count; verify partial baths and scope",
        "repair": _rate(2_500, 5_000, 8_500),
        "replace": _rate(8_000, 13_000, 20_000),
        "minimum_cents": 2_000_00,
        "specialist_recommended": False,
    },
    "flooring": {
        "label": "Flooring",
        "unit": "square_foot",
        "quantity_basis": "subject living area; reduce for unaffected rooms",
        "repair": _rate(1, 2, 4),
        "replace": _rate(4, 6, 10),
        "minimum_cents": 1_500_00,
        "specialist_recommended": False,
    },
    "paint_drywall": {
        "label": "Paint / drywall",
        "unit": "living_square_foot",
        "quantity_basis": "subject living area",
        "repair": _rate(1, 2, 4),
        "replace": _rate(3, 5, 8),
        "minimum_cents": 1_500_00,
        "specialist_recommended": False,
    },
    "windows_doors": {
        "label": "Windows / doors",
        "unit": "opening",
        "quantity_basis": "estimated from living area; verify exact opening count",
        "repair": _rate(200, 450, 800),
        "replace": _rate(700, 1_100, 1_800),
        "minimum_cents": 750_00,
        "specialist_recommended": False,
    },
    "exterior": {
        "label": "Exterior",
        "unit": "project",
        "quantity_basis": "one project allowance",
        "repair": _rate(2_500, 6_000, 12_000),
        "replace": _rate(10_000, 20_000, 40_000),
        "minimum_cents": 1_500_00,
        "specialist_recommended": False,
    },
    "landscaping": {
        "label": "Landscaping",
        "unit": "project",
        "quantity_basis": "one project allowance",
        "repair": _rate(750, 2_000, 4_500),
        "replace": _rate(3_500, 7_000, 14_000),
        "minimum_cents": 500_00,
        "specialist_recommended": False,
    },
    "permits": {
        "label": "Permits",
        "unit": "project",
        "quantity_basis": "one project allowance; verify jurisdiction and scope",
        "repair": _rate(500, 1_500, 3_500),
        "replace": _rate(1_500, 3_500, 8_000),
        "minimum_cents": 500_00,
        "specialist_recommended": False,
    },
    "cleanup": {
        "label": "Cleanup",
        "unit": "project",
        "quantity_basis": "one project allowance",
        "repair": _rate(750, 1_750, 3_500),
        "replace": _rate(2_500, 5_000, 10_000),
        "minimum_cents": 500_00,
        "specialist_recommended": False,
    },
    "other": {
        "label": "Other",
        "unit": "project",
        "quantity_basis": "manual scope and price required",
        "repair": _rate(0, 0, 0),
        "replace": _rate(0, 0, 0),
        "minimum_cents": 0,
        "specialist_recommended": False,
    },
}

SEVERITY_FACTORS = {"minor": 0.75, "standard": 1.0, "extensive": 1.35}


def prepare_new_scope_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Discard client-supplied system prices before calculating a new catalog scope."""
    prepared: list[dict[str, Any]] = []
    for item in items:
        clean = dict(item)
        if clean.get("pricing_method") == "catalog":
            for key in (
                "system_low_cents",
                "system_expected_cents",
                "system_high_cents",
                "catalog_version",
            ):
                clean[key] = None
        prepared.append(clean)
    return prepared


def repair_catalog_payload(subject: dict[str, Any] | None = None) -> dict[str, Any]:
    defaults = subject_defaults(subject or {})
    items = []
    for category, entry in CATALOG.items():
        items.append(
            {
                "category": category,
                "label": entry["label"],
                "unit": entry["unit"],
                "default_quantity": default_quantity(category, defaults),
                "quantity_basis": entry["quantity_basis"],
                "repair": entry["repair"],
                "replace": entry["replace"],
                "minimum_cents": entry["minimum_cents"],
                "specialist_recommended": entry["specialist_recommended"],
                "source_note": CATALOG_SOURCE_NOTE,
            }
        )
    return {
        "version": CATALOG_VERSION,
        "market_key": MARKET_KEY,
        "market_label": MARKET_LABEL,
        "effective_date": EFFECTIVE_DATE,
        "currency": "USD",
        "status": "internal_planning_allowance",
        "source_note": CATALOG_SOURCE_NOTE,
        "subject_defaults": defaults,
        "items": items,
    }


def evaluate_repair_scope(
    items: list[dict[str, Any]],
    *,
    contingency_percentage: int,
    subject: dict[str, Any] | None = None,
) -> dict[str, Any]:
    defaults = subject_defaults(subject or {})
    normalized_items: list[dict[str, Any]] = []
    warnings: list[str] = []
    for raw_item in items:
        normalized, item_warnings = evaluate_repair_item(raw_item, defaults=defaults)
        normalized_items.append(normalized)
        warnings.extend(item_warnings)

    saved_versions = {
        str(item["catalog_version"])
        for item in normalized_items
        if item.get("catalog_version")
    }
    scenario_version = (
        next(iter(saved_versions)) if len(saved_versions) == 1 else CATALOG_VERSION
    )
    if len(saved_versions) > 1:
        warnings.append(
            "Repair items contain multiple catalog versions; review the combined scope."
        )

    subtotal_low = sum(int(item["system_low_cents"]) for item in normalized_items)
    subtotal_expected = sum(
        int(item["estimated_cost_cents"]) for item in normalized_items
    )
    subtotal_high = sum(int(item["system_high_cents"]) for item in normalized_items)
    unknown_reserve = sum(
        int(item["estimated_cost_cents"])
        for item in normalized_items
        if item["scope_status"] in {"unknown", "specialist_review"}
    )
    factor = 1 + contingency_percentage / 100
    return {
        "version": scenario_version,
        "market_key": MARKET_KEY,
        "source_note": CATALOG_SOURCE_NOTE,
        "subtotal_low_cents": subtotal_low,
        "subtotal_expected_cents": subtotal_expected,
        "subtotal_high_cents": subtotal_high,
        "contingency_percentage": contingency_percentage,
        "total_low_cents": round(subtotal_low * factor),
        "total_expected_cents": round(subtotal_expected * factor),
        "total_high_cents": round(subtotal_high * factor),
        "unknown_reserve_cents": unknown_reserve,
        "unknown_item_count": sum(
            item["scope_status"] == "unknown" for item in normalized_items
        ),
        "specialist_item_count": sum(
            item["scope_status"] == "specialist_review"
            for item in normalized_items
        ),
        "items": normalized_items,
        "warnings": list(dict.fromkeys(warnings)),
    }


def evaluate_repair_item(
    raw_item: dict[str, Any],
    *,
    defaults: dict[str, float | int | None],
) -> tuple[dict[str, Any], list[str]]:
    category = str(raw_item.get("category") or "other")
    entry = CATALOG.get(category, CATALOG["other"])
    status = str(raw_item.get("scope_status") or "repair")
    pricing_method = str(raw_item.get("pricing_method") or "manual")
    severity = str(raw_item.get("severity") or "standard")
    quantity = number(raw_item.get("quantity")) or default_quantity(category, defaults)
    quantity = max(quantity, 0.01)
    warnings: list[str] = []

    stored_catalog_range = (
        pricing_method == "catalog"
        and raw_item.get("catalog_version")
        and money(raw_item.get("system_low_cents")) is not None
        and money(raw_item.get("system_expected_cents")) is not None
        and money(raw_item.get("system_high_cents")) is not None
        and money(raw_item.get("estimated_cost_cents")) is not None
    )
    if stored_catalog_range:
        system_low = money(raw_item.get("system_low_cents")) or 0
        system_expected = money(raw_item.get("system_expected_cents")) or 0
        system_high = money(raw_item.get("system_high_cents")) or 0
        expected = money(raw_item.get("estimated_cost_cents")) or 0
        low = min(system_low, expected)
        high = max(system_high, expected)
        catalog_version = raw_item.get("catalog_version")
        if status == "no_work":
            low = expected = high = 0
    elif pricing_method != "catalog":
        amount = money(raw_item.get("manual_override_cents"))
        if amount is None:
            amount = money(raw_item.get("estimated_cost_cents")) or 0
        if status == "no_work":
            amount = 0
        stored_low = money(raw_item.get("system_low_cents"))
        stored_expected = money(raw_item.get("system_expected_cents"))
        stored_high = money(raw_item.get("system_high_cents"))
        low = min(stored_low, amount) if stored_low is not None else amount
        expected = amount
        high = max(stored_high, amount) if stored_high is not None else amount
        system_low = stored_low if stored_low is not None else amount
        system_expected = stored_expected if stored_expected is not None else amount
        system_high = stored_high if stored_high is not None else amount
        catalog_version = raw_item.get("catalog_version")
    else:
        system_low, system_expected, system_high = catalog_amounts(
            entry,
            status=status,
            severity=severity,
            quantity=quantity,
        )
        low, expected, high = system_low, system_expected, system_high
        catalog_version = CATALOG_VERSION
        override = money(raw_item.get("manual_override_cents"))
        if override is not None:
            reason = text(raw_item.get("override_reason"))
            if not reason:
                raise ValueError(
                    f"{entry['label']} needs a reason for the manual price override."
                )
            expected = override
            low = min(low, override)
            high = max(high, override)
            pricing_method = "manual"
        if category == "other" and expected == 0 and status != "no_work":
            warnings.append("Other work needs a manual amount and scope note.")

    if status == "unknown":
        warnings.append(
            f"{entry['label']} is unknown; the expected scenario includes an uncertainty reserve."
        )
    if status == "specialist_review" or (
        status == "unknown" and bool(entry["specialist_recommended"])
    ):
        warnings.append(f"{entry['label']} needs specialist review before offer approval.")

    uncertainty_note = text(raw_item.get("uncertainty_note"))
    if not uncertainty_note and status == "unknown":
        uncertainty_note = (
            "Condition is unconfirmed; reserve is based on catalog replacement range."
        )
    if not uncertainty_note and status == "specialist_review":
        uncertainty_note = "Specialist scope and written pricing are not yet available."

    normalized = {
        **raw_item,
        "category": category,
        "scope_status": status,
        "severity": severity,
        "quantity": round(quantity, 2),
        "unit": entry["unit"],
        "pricing_method": pricing_method,
        "estimated_cost_cents": expected,
        "system_low_cents": low,
        "system_expected_cents": system_expected,
        "system_high_cents": high,
        "catalog_version": catalog_version,
        "uncertainty_note": uncertainty_note,
    }
    return normalized, warnings


def catalog_amounts(
    entry: dict[str, Any],
    *,
    status: str,
    severity: str,
    quantity: float,
) -> tuple[int, int, int]:
    if status == "no_work":
        return 0, 0, 0
    repair = entry["repair"]
    replace = entry["replace"]
    factor = SEVERITY_FACTORS.get(severity, 1.0)
    minimum = int(entry["minimum_cents"])

    if status == "unknown":
        reserve_fraction = 0.40 if entry["specialist_recommended"] else 0.25
        return (
            0,
            round(int(replace["expected_cents"]) * quantity * reserve_fraction),
            max(minimum, round(int(replace["high_cents"]) * quantity)),
        )
    if status == "specialist_review":
        return (
            max(minimum, round(int(repair["low_cents"]) * quantity)),
            max(minimum, round(int(replace["expected_cents"]) * quantity)),
            max(minimum, round(int(replace["high_cents"]) * quantity * 1.25)),
        )

    rate = replace if status == "replace" else repair
    values = [
        max(minimum, round(int(rate[key]) * quantity * factor))
        for key in ("low_cents", "expected_cents", "high_cents")
    ]
    return values[0], values[1], values[2]


def subject_defaults(subject: dict[str, Any]) -> dict[str, float | int | None]:
    square_feet = first_number(subject, "squareFootage", "square_footage")
    bathrooms = first_number(subject, "bathrooms")
    return {
        "square_footage": round(square_feet) if square_feet else None,
        "bathrooms": bathrooms,
        "estimated_roof_squares": (
            round(square_feet * 1.15 / 100, 1) if square_feet else 20
        ),
        "estimated_openings": (
            max(8, round(square_feet / 150)) if square_feet else 12
        ),
    }


def default_quantity(
    category: str,
    defaults: dict[str, float | int | None],
) -> float:
    if category == "roof":
        return float(defaults.get("estimated_roof_squares") or 20)
    if category == "bathrooms":
        return float(defaults.get("bathrooms") or 2)
    if category in {"flooring", "paint_drywall"}:
        return float(defaults.get("square_footage") or 1_800)
    if category == "windows_doors":
        return float(defaults.get("estimated_openings") or 12)
    return 1.0


def first_number(source: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = number(source.get(key))
        if value is not None:
            return value
    return None


def number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def money(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value)
    return None


def text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
