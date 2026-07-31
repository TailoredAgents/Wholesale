from typing import Any

from app.integrations.rentcast_client import RentCastClientError
from app.services.underwriting_comp_search import search_adaptive_closed_sales
from app.services.underwriting_v2 import analyze_recorded_sales


def subject(*, subdivision: str | None = "OAK RIDGE") -> dict[str, Any]:
    return {
        "id": "subject-1",
        "formattedAddress": "100 Main St, Canton, GA 30114",
        "propertyType": "Single Family",
        "bedrooms": 3,
        "bathrooms": 2,
        "squareFootage": 1800,
        "yearBuilt": 1990,
        "latitude": 34.2368,
        "longitude": -84.4908,
        "subdivision": subdivision,
    }


def sale(
    identifier: str,
    *,
    subdivision: str | None = "OAK RIDGE",
    distance: float = 0.2,
    square_footage: int = 1800,
    year_built: int = 1990,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "formattedAddress": f"{identifier} Main St, Canton, GA 30114",
        "propertyType": "Single Family",
        "bedrooms": 3,
        "bathrooms": 2,
        "squareFootage": square_footage,
        "yearBuilt": year_built,
        "lastSalePrice": 300000 + int(identifier.split("-")[-1]) * 1000,
        "lastSaleDate": "2026-06-15T00:00:00Z",
        "distance": distance,
        "subdivision": subdivision,
    }


class ProfileClient:
    def __init__(self, responses: dict[float, list[dict[str, Any]]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def get_recent_sales(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(kwargs)
        return self.responses.get(float(kwargs["radius"]), [])


def run_search(client: ProfileClient) -> Any:
    return search_adaptive_closed_sales(
        client,
        address="100 Main St, Canton, GA 30114",
        subject_facts=subject(),
        local_property_type="single_family",
        condition_overrides={},
    )


def test_preferred_search_stops_when_closed_sale_threshold_is_met() -> None:
    client = ProfileClient({0.5: [sale("comp-1"), sale("comp-2"), sale("comp-3")]})

    result = run_search(client)

    assert [call["radius"] for call in client.calls] == [0.5]
    assert result.provider_returned_count == 3
    assert result.summary["strategy_version"] == "adaptive_v1"
    assert result.summary["final_level"] == "preferred"
    assert result.summary["sufficient_closed_sales"] is True
    assert result.summary["same_subdivision_count"] == 3
    assert result.summary["duplicate_count"] == 0
    assert result.warnings == []
    assert {record["_stonegateSearchLevel"] for record in result.records} == {"preferred"}


def test_expanded_search_deduplicates_prior_results_and_preserves_first_level() -> None:
    first = sale("comp-1")
    client = ProfileClient(
        {
            0.5: [first],
            1.0: [first, sale("comp-2"), sale("comp-3")],
        }
    )

    result = run_search(client)

    assert [call["radius"] for call in client.calls] == [0.5, 1]
    assert result.provider_returned_count == 4
    assert result.summary["final_level"] == "expanded"
    assert result.summary["total_unique_sales"] == 3
    assert result.summary["duplicate_count"] == 1
    assert result.summary["attempts"][1]["unique_added_count"] == 2
    assert result.summary["attempts"][1]["duplicate_count"] == 1
    by_id = {record["id"]: record for record in result.records}
    assert by_id["comp-1"]["_stonegateSearchLevel"] == "preferred"
    assert by_id["comp-2"]["_stonegateSearchLevel"] == "expanded"
    assert "required the expanded search" in result.warnings[0]


def test_full_search_returns_precise_manual_evidence_shortage() -> None:
    one_sale = sale("comp-1")
    client = ProfileClient(
        {
            0.5: [one_sale],
            1.0: [one_sale],
            3.0: [one_sale],
        }
    )

    result = run_search(client)

    assert [call["radius"] for call in client.calls] == [0.5, 1, 3]
    assert result.provider_returned_count == 3
    assert result.summary["final_level"] == "manual"
    assert result.summary["sufficient_closed_sales"] is False
    assert result.summary["total_unique_sales"] == 1
    assert result.summary["duplicate_count"] == 2
    assert result.summary["attempts"][-1]["level"] == "manual"
    assert "found 1 usable closed sale" in result.summary["evidence_shortage_reason"]
    assert "obtain a known closed sale" in result.summary["next_action"]


def test_subdivision_evidence_forces_controlled_expansion() -> None:
    outside = [
        sale("comp-1", subdivision="OTHER"),
        sale("comp-2", subdivision="OTHER"),
        sale("comp-3", subdivision="OTHER"),
    ]
    client = ProfileClient(
        {
            0.5: outside,
            1.0: outside,
            3.0: [
                *outside,
                sale("comp-4", subdivision="OAK RIDGE", distance=1.2),
                sale("comp-5", subdivision="OAK RIDGE", distance=1.4),
            ],
        }
    )

    result = run_search(client)

    assert result.summary["final_level"] == "extended"
    assert result.summary["sufficient_closed_sales"] is True
    assert result.summary["same_subdivision_count"] == 2
    assert "outside the recorded subject subdivision" in result.summary["market_area_warning"]
    assert result.summary["attempts"][1]["expansion_reason"].startswith(
        "Fewer than two selected sales"
    )
    selected, _ = analyze_recorded_sales(
        subject(),
        result.records,
        condition_overrides={},
    )
    extended = [comp for comp in selected if comp.search_level == "extended"]
    assert len(extended) == 2
    assert all(comp.comp_grade == "C" for comp in extended)
    assert all(comp.subdivision_match is True for comp in extended)
    assert any(comp.subdivision_match is False for comp in selected)


def test_selected_sale_preserves_engine_recommendation_and_compass_direction() -> None:
    north_sale = sale("comp-1")
    north_sale.update(
        {
            "latitude": 34.2468,
            "longitude": -84.4908,
        }
    )

    selected, rejected = analyze_recorded_sales(
        subject(),
        [north_sale],
        condition_overrides={},
    )

    assert rejected == []
    assert selected[0].latitude == 34.2468
    assert selected[0].longitude == -84.4908
    assert selected[0].direction_from_subject == "N"
    assert selected[0].engine_selection_status == "selected"
    assert selected[0].engine_selection_reason == selected[0].selection_reason


def test_later_provider_failure_keeps_earlier_evidence_and_explains_gap() -> None:
    class FailingExpandedClient(ProfileClient):
        def get_recent_sales(self, **kwargs: Any) -> list[dict[str, Any]]:
            self.calls.append(kwargs)
            if kwargs["radius"] == 1:
                raise RentCastClientError(
                    "RentCast recent sales failed (HTTP 503): unavailable.",
                    operation="recent sales",
                    status_code=503,
                )
            return [sale("comp-1")]

    client = FailingExpandedClient({})

    result = run_search(client)

    assert [call["radius"] for call in client.calls] == [0.5, 1]
    assert len(result.records) == 1
    assert result.summary["final_level"] == "manual"
    assert "stopped responding" in result.summary["evidence_shortage_reason"]
    assert result.summary["attempts"][1]["provider_error"].endswith("unavailable.")
