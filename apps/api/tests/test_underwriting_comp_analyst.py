from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.integrations.openai_client import OpenAIClientError, validate_strict_json_schema
from app.schemas.leads import MarketAnalysisCompRead
from app.schemas.underwriting_comp_analyst import CompAnalystEvidenceInput
from app.services.underwriting_comp_analyst import (
    COMP_ANALYST_OUTPUT_SCHEMA,
    analyze_comparable_set,
    build_comp_analyst_request,
    build_saved_comp_context_evidence,
    run_comp_analyst,
    unavailable_comp_analyst,
)
from app.services.underwriting_v2 import score_recorded_sale


def comp(
    key: str,
    *,
    selected: bool,
    score: int = 90,
    source_url: str | None = None,
) -> MarketAnalysisCompRead:
    return MarketAnalysisCompRead(
        provider_id=key,
        formatted_address=f"{key} Main St, Atlanta, GA 30303",
        status="Recorded sale",
        listing_type="Property record",
        property_type="Single Family",
        price_cents=30_000_000 + score * 100,
        bedrooms=3,
        bathrooms=2,
        square_footage=1_800,
        year_built=1980,
        distance_miles=0.3,
        days_old=90,
        correlation=None,
        listed_date=None,
        removed_date=None,
        last_seen_date=None,
        sale_date="2026-01-01",
        price_source="recorded_sale",
        verification_status="recorded",
        condition_classification="unknown",
        condition_evidence="No listing photos were supplied.",
        lot_size=8_000,
        garage=True,
        pool=False,
        basement=False,
        adjusted_value_cents=None,
        price_per_square_foot_cents=None,
        weight=None,
        subdivision="PEACHTREE",
        subdivision_match=True,
        search_level="preferred",
        comp_grade="A",
        search_warnings=[],
        evidence_source="rentcast_property_record",
        source_url=source_url,
        selection_status="selected" if selected else "rejected",
        selection_reason="Local recorded sale" if selected else "Ranked below selected sales",
        score=score,
    )


def subject() -> dict[str, Any]:
    return {
        "formattedAddress": "100 Subject Ave, Atlanta, GA 30303",
        "propertyType": "Single Family",
        "bedrooms": 3,
        "bathrooms": 2,
        "squareFootage": 1_850,
        "lotSize": 8_500,
        "yearBuilt": 1982,
        "subdivision": "PEACHTREE",
        "features": {"garage": True, "pool": False, "foundationType": "Slab"},
    }


def request_and_payload() -> tuple[Any, dict[str, Any]]:
    request = build_comp_analyst_request(
        subject=subject(),
        selected_comps=[
            comp(
                "selected-1",
                selected=True,
                source_url="https://records.example/sale/1#history",
            )
        ],
        rejected_comps=[comp("rejected-1", selected=False, score=70)],
        market_adjustment={
            "conclusion": {
                "arv_low_cents": 28_000_000,
                "arv_point_cents": 32_000_000,
                "arv_high_cents": 36_000_000,
            },
            "rate_evidence": [
                {"key": "living_area", "status": "supported"},
                {"key": "condition_quality", "status": "unsupported"},
            ],
            "comp_adjustments": [{"comp_key": "selected-1", "requires_review": True}],
        },
    )
    selected_evidence = next(
        item.evidence_id for item in request.comparables if item.comp_key == "selected-1"
    )
    rejected_evidence = next(
        item.evidence_id for item in request.comparables if item.comp_key == "rejected-1"
    )
    payload: dict[str, Any] = {
        "status": "completed",
        "summary": (
            "Draft comparable review completed; all recommendations require human approval."
        ),
        "analysis_role": "draft_comp_review_support",
        "human_review_required": True,
        "valuation_use": "excluded_from_arv_and_offer_math",
        "comp_recommendations": [
            {
                "comp_key": "selected-1",
                "recommendation": "include",
                "reason": "The recorded sale is nearby and physically similar.",
                "condition_hypothesis": "unknown",
                "condition_reason": "No condition evidence was supplied.",
                "micro_market_concerns": [],
                "confidence": 81,
                "citations": [
                    {
                        "evidence_id": selected_evidence,
                        "source_url": "https://records.example/sale/1",
                    }
                ],
                "requires_human_approval": True,
            },
            {
                "comp_key": "rejected-1",
                "recommendation": "review",
                "reason": "The sale ranked below the selected evidence.",
                "condition_hypothesis": "unknown",
                "condition_reason": "No condition evidence was supplied.",
                "micro_market_concerns": [],
                "confidence": 65,
                "citations": [{"evidence_id": rejected_evidence, "source_url": None}],
                "requires_human_approval": True,
            },
        ],
        "duplicate_candidates": [],
        "conflicts": [],
        "micro_market_concerns": [],
        "missing_questions": [
            {
                "question": "Are dated interior photos available for the subject?",
                "why_it_matters": "Condition evidence is missing.",
                "related_comp_keys": [],
                "citations": [{"evidence_id": "subject_record", "source_url": None}],
            }
        ],
        "range_explanations": [
            {
                "driver": "Condition support is withheld.",
                "affected_comp_keys": ["selected-1"],
                "explanation": "Unknown condition leaves a material similarity question.",
                "resolution_question": "Can a person compare dated listing photos?",
                "citations": [
                    {
                        "evidence_id": "deterministic_range_diagnostics",
                        "source_url": None,
                    },
                    {
                        "evidence_id": selected_evidence,
                        "source_url": "https://records.example/sale/1",
                    },
                ],
            }
        ],
        "limitations": [],
    }
    return request, payload


class FakeClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.kwargs: dict[str, Any] = {}

    def create_structured_response(self, **kwargs: Any) -> tuple[dict[str, Any], dict[str, int]]:
        self.kwargs = kwargs
        return self.payload, {
            "input_tokens": 500,
            "output_tokens": 200,
            "total_tokens": 700,
        }


def test_comp_analyst_schema_is_strict_and_run_is_bounded() -> None:
    validate_strict_json_schema(COMP_ANALYST_OUTPUT_SCHEMA)
    request, payload = request_and_payload()
    client = FakeClient(payload)

    result = run_comp_analyst(
        request,
        client=client,  # type: ignore[arg-type]
        model="gpt-test",
        safety_identifier="underwriting-test",
    )

    assert result.status == "completed"
    assert result.mode == "draft"
    assert result.valuation_use == "excluded_from_arv_and_offer_math"
    assert result.human_review_required is True
    assert result.comp_recommendations[0].recommendation == "include"
    assert result.range_explanations[0].affected_comp_keys == ["selected-1"]
    assert result.usage is not None and result.usage.total_tokens == 700
    assert client.kwargs["json_schema"] == COMP_ANALYST_OUTPUT_SCHEMA
    assert client.kwargs["prompt_cache_key"].endswith(":v1")
    assert "tools" not in client.kwargs
    assert "arv_point_cents" not in str(client.kwargs["user_prompt"])


def test_comp_analyst_rejects_unknown_evidence_and_hides_entire_draft() -> None:
    request, payload = request_and_payload()
    payload["comp_recommendations"][0]["citations"][0]["evidence_id"] = "invented"

    result = run_comp_analyst(
        request,
        client=FakeClient(payload),  # type: ignore[arg-type]
        model="gpt-test",
    )

    assert result.status == "rejected"
    assert result.comp_recommendations == []
    assert result.range_explanations == []
    assert result.usage is not None and result.usage.total_tokens == 700
    assert "not supplied" in (result.error or "")


def test_comp_analyst_rejects_changed_source_url() -> None:
    request, payload = request_and_payload()
    payload["comp_recommendations"][0]["citations"][0]["source_url"] = (
        "https://invented.example/sale/1"
    )

    result = run_comp_analyst(
        request,
        client=FakeClient(payload),  # type: ignore[arg-type]
        model="gpt-test",
    )

    assert result.status == "rejected"
    assert "source URL" in (result.error or "")


def test_comp_analyst_requires_matching_evidence_for_source_conflicts() -> None:
    request, payload = request_and_payload()
    selected_evidence = payload["comp_recommendations"][0]["citations"][0]
    payload["conflicts"] = [
        {
            "field": "sale_date",
            "comp_keys": ["selected-1"],
            "description": "Providers report different closed-sale dates.",
            "requires_human_resolution": True,
            "citations": [selected_evidence],
        }
    ]
    unsupported = run_comp_analyst(
        request,
        client=FakeClient(payload),  # type: ignore[arg-type]
        model="gpt-test",
    )
    assert unsupported.status == "rejected"
    assert "conflict evidence" in (unsupported.error or "")

    selected = comp(
        "selected-1",
        selected=True,
        source_url="https://records.example/sale/1",
    ).model_copy(
        update={
            "source_conflicts": [
                {
                    "field": "sale_date",
                    "selected_value": "2026-01-01",
                    "observations": [
                        {"provider": "rentcast", "value": "2026-01-01"},
                        {"provider": "dealmachine", "value": "2025-12-30"},
                    ],
                }
            ]
        }
    )
    supported_request = build_comp_analyst_request(
        subject=subject(),
        selected_comps=[selected],
        rejected_comps=[comp("rejected-1", selected=False, score=70)],
    )
    conflict_evidence = next(
        item for item in supported_request.evidence if item.evidence_type == "provider_conflict"
    )
    payload["conflicts"][0]["citations"].append(
        {"evidence_id": conflict_evidence.evidence_id, "source_url": None}
    )
    supported = run_comp_analyst(
        supported_request,
        client=FakeClient(payload),  # type: ignore[arg-type]
        model="gpt-test",
    )
    assert supported.status == "completed"
    assert supported.conflicts[0].field == "sale_date"


def test_comp_analyst_rejects_price_authority_fields_and_narrative() -> None:
    request, payload = request_and_payload()
    payload["arv_cents"] = 40_000_000
    result = run_comp_analyst(
        request,
        client=FakeClient(payload),  # type: ignore[arg-type]
        model="gpt-test",
    )
    assert result.status == "rejected"
    assert "structured contract" in result.summary

    _request, narrative_payload = request_and_payload()
    narrative_payload["summary"] = "Apply a $25,000 adjustment to the first sale."
    narrative_result = run_comp_analyst(
        request,
        client=FakeClient(narrative_payload),  # type: ignore[arg-type]
        model="gpt-test",
    )
    assert narrative_result.status == "rejected"
    assert "authority boundary" in narrative_result.summary


def test_comp_analyst_rejects_implied_value_and_purchase_authority() -> None:
    for narrative in (
        "This property is worth 300k.",
        "Stonegate should buy around 225k.",
        "Recommend paying 250000.",
        "The subject would resell for 300k after renovation.",
        "Use 225k as the acquisition target.",
        "Set the ceiling at 225k.",
        "Add twenty-five thousand to this comparable.",
    ):
        request, payload = request_and_payload()
        payload["summary"] = narrative

        result = run_comp_analyst(
            request,
            client=FakeClient(payload),  # type: ignore[arg-type]
            model="gpt-test",
        )

        assert result.status == "rejected"
        assert "authority boundary" in result.summary


def test_comp_analyst_allows_non_price_year_size_and_zip_facts() -> None:
    request, payload = request_and_payload()
    payload["comp_recommendations"][0]["reason"] = (
        "The record says it was built in 1980, has 1800 square feet, and is in ZIP 30303."
    )

    result = run_comp_analyst(
        request,
        client=FakeClient(payload),  # type: ignore[arg-type]
        model="gpt-test",
    )

    assert result.status == "completed"


def test_comp_analyst_rejects_factual_claims_hidden_in_uncited_summary() -> None:
    for narrative in (
        "The first sale is across Highway 85 in an inferior school district.",
        "Providers disagree about the first sale date.",
    ):
        request, payload = request_and_payload()
        payload["summary"] = narrative

        result = run_comp_analyst(
            request,
            client=FakeClient(payload),  # type: ignore[arg-type]
            model="gpt-test",
        )

        assert result.status == "rejected"


def test_comp_analyst_rejects_condition_hypothesis_without_supporting_evidence() -> None:
    request, payload = request_and_payload()
    recommendation = payload["comp_recommendations"][0]
    recommendation["condition_hypothesis"] = "renovated"
    recommendation["condition_reason"] = "Fresh interior photographs show a complete renovation."

    result = run_comp_analyst(
        request,
        client=FakeClient(payload),  # type: ignore[arg-type]
        model="gpt-test",
    )

    assert result.status == "rejected"
    assert "condition evidence" in (result.error or "")


def test_comp_analyst_rejects_unsupported_micro_market_claim() -> None:
    request, payload = request_and_payload()
    selected_citation = payload["comp_recommendations"][0]["citations"][0]
    payload["micro_market_concerns"] = [
        {
            "comp_keys": ["selected-1"],
            "concern": "The sale is across Highway 85 in an inferior school district.",
            "why_it_matters": "The claimed boundary may affect buyer demand.",
            "citations": [selected_citation],
        }
    ]

    result = run_comp_analyst(
        request,
        client=FakeClient(payload),  # type: ignore[arg-type]
        model="gpt-test",
    )

    assert result.status == "rejected"
    assert "micro-market claim" in (result.error or "")


def test_comp_analyst_routes_context_claims_in_every_narrative_field() -> None:
    cases = (
        ("recommendation", "The comp is on the different side of I-85."),
        (
            "recommendation",
            "RentCast and DealMachine report inconsistent closing figures.",
        ),
        ("range", "Traffic from the nearby interstate may explain the spread."),
        ("question", "Is this sale across a neighborhood boundary?"),
    )
    for field, narrative in cases:
        request, payload = request_and_payload()
        if field == "recommendation":
            payload["comp_recommendations"][0]["reason"] = narrative
        elif field == "range":
            payload["range_explanations"][0]["explanation"] = narrative
        else:
            question = payload["missing_questions"][0]
            question["question"] = narrative
            question["related_comp_keys"] = ["selected-1"]
            question["citations"] = [payload["comp_recommendations"][0]["citations"][0]]

        result = run_comp_analyst(
            request,
            client=FakeClient(payload),  # type: ignore[arg-type]
            model="gpt-test",
        )

        assert result.status == "rejected"
        assert "claim lacked" in (result.error or "")


def test_comp_analyst_accepts_micro_market_claim_only_with_semantic_context() -> None:
    request, payload = request_and_payload()
    context = CompAnalystEvidenceInput(
        evidence_id="market_context:selected-1",
        evidence_type="market_context",
        related_comp_keys=["selected-1"],
        field="roadway_boundary",
        value="I-85 and its highway traffic separate this sale from the subject market area.",
        source_title="Local planning map",
        source_url="https://planning.example/i-85",
    )
    request.evidence.append(context)
    recommendation = payload["comp_recommendations"][0]
    recommendation["reason"] = "The comp is on the different side of I-85."
    recommendation["citations"].append(
        {"evidence_id": context.evidence_id, "source_url": context.source_url}
    )

    result = run_comp_analyst(
        request,
        client=FakeClient(payload),  # type: ignore[arg-type]
        model="gpt-test",
    )

    assert result.status == "completed"


def test_saved_cited_market_facts_are_wired_as_bounded_context_evidence() -> None:
    selected = comp(
        "selected-1",
        selected=True,
        source_url="https://records.example/sale/1",
    )
    evidence = build_saved_comp_context_evidence(
        selected_comps=[selected],
        rejected_comps=[],
        secondary_evidence={
            "facts": [
                {
                    "fact_type": "market_context",
                    "value": "The neighborhood boundary follows I-85.",
                    "source_title": "City planning map",
                    "source_url": "https://planning.example/map",
                }
            ]
        },
    )

    assert len(evidence) == 1
    assert evidence[0].evidence_type == "market_context"
    assert evidence[0].related_comp_keys == ["selected-1"]
    assert evidence[0].source_url == "https://planning.example/map"


def test_comp_analyst_rejects_include_recommendation_for_ineligible_transfer() -> None:
    request, payload = request_and_payload()
    rejected = next(item for item in request.comparables if item.comp_key == "rejected-1")
    rejected.transaction_type = "Quit Claim Deed"
    rejected.transaction_eligibility = "ineligible"
    rejected.transaction_review_reason = "Recorded document is a non-market transfer."
    payload["comp_recommendations"][1]["recommendation"] = "include"

    result = run_comp_analyst(
        request,
        client=FakeClient(payload),  # type: ignore[arg-type]
        model="gpt-test",
    )

    assert result.status == "rejected"
    assert "non-market transfer" in (result.error or "")


def test_comp_analyst_degrades_safely_when_disabled_or_provider_fails() -> None:
    request, _payload = request_and_payload()
    disabled = run_comp_analyst(request, client=None, model=None)
    assert disabled.status == "unavailable"
    assert disabled.comp_recommendations == []
    assert disabled.error

    explicit = unavailable_comp_analyst("Draft review is disabled.")
    assert explicit.status == "unavailable"
    assert explicit.error == "Draft review is disabled."

    class FailingClient:
        def create_structured_response(self, **_kwargs: Any) -> Any:
            raise OpenAIClientError("Provider temporarily unavailable.")

    failed = run_comp_analyst(
        request,
        client=FailingClient(),  # type: ignore[arg-type]
        model="gpt-test",
    )
    assert failed.status == "unavailable"
    assert failed.error == "Provider temporarily unavailable."

    class MalformedSuccessClient:
        def create_structured_response(self, **_kwargs: Any) -> Any:
            raise ValueError("malformed provider success")

    malformed = run_comp_analyst(
        request,
        client=MalformedSuccessClient(),  # type: ignore[arg-type]
        model="gpt-test",
    )
    assert malformed.status == "unavailable"
    assert malformed.comp_recommendations == []
    assert "failed safely" in (malformed.error or "")

    wrong_url_request, wrong_url_payload = request_and_payload()
    wrong_url_payload["comp_recommendations"][0]["citations"][0]["source_url"] = 123
    wrong_url = run_comp_analyst(
        wrong_url_request,
        client=FakeClient(wrong_url_payload),  # type: ignore[arg-type]
        model="gpt-test",
    )
    assert wrong_url.status == "rejected"
    assert wrong_url.comp_recommendations == []


def test_comp_analyst_returns_insufficient_without_calling_model_for_no_comps() -> None:
    request = build_comp_analyst_request(
        subject=subject(),
        selected_comps=[],
        rejected_comps=[],
    )

    result = run_comp_analyst(request, client=None, model="gpt-test")

    assert result.status == "insufficient"
    assert result.model is None
    assert result.error is None


def test_request_builder_caps_and_ranks_rejected_comps_deterministically() -> None:
    selected = [comp(f"selected-{index}", selected=True) for index in range(3)]
    rejected = [comp(f"rejected-{index}", selected=False, score=index) for index in range(40)]

    request = build_comp_analyst_request(
        subject=subject(),
        selected_comps=selected,
        rejected_comps=rejected,
    )

    assert len(request.comparables) == 20
    assert [item.comp_key for item in request.comparables[:3]] == [
        "selected-0",
        "selected-1",
        "selected-2",
    ]
    assert [item.comp_key for item in request.comparables[3:6]] == [
        "rejected-39",
        "rejected-38",
        "rejected-37",
    ]
    assert request.range_context.selected_comp_count == 3


def test_request_builder_converts_provider_observations_and_conflicts_to_evidence() -> None:
    comparable = comp("corroborated-1", selected=True).model_copy(
        update={
            "source_observations": [
                {
                    "provider": "dealmachine",
                    "provider_record_id": "dm-1",
                    "field": "closed_sale_record",
                    "source_url": "https://evidence.example/record/1#sale",
                    "owner_name": "Must not enter AI context",
                }
            ],
            "source_conflicts": [
                {
                    "field": "sale_date",
                    "selected_value": "2026-01-01",
                    "observations": [
                        {"provider": "rentcast", "value": "2026-01-01"},
                        {"provider": "dealmachine", "value": "2025-12-30"},
                    ],
                }
            ],
        }
    )

    request = build_comp_analyst_request(
        subject=subject(),
        selected_comps=[comparable],
        rejected_comps=[],
    )

    observation = next(
        item for item in request.evidence if item.evidence_type == "closed_sale_record"
    )
    conflict = next(item for item in request.evidence if item.evidence_type == "provider_conflict")
    assert observation.related_comp_keys == ["corroborated-1"]
    assert observation.source_url == "https://evidence.example/record/1"
    assert "owner" not in observation.value.lower()
    assert conflict.field == "sale_date"
    assert "dealmachine" in conflict.value


def test_scored_comps_preserve_provider_provenance_and_conflict_aliases() -> None:
    provenance = [
        {"provider": "rentcast", "provider_record_id": "rc-1"},
        {"provider": "dealmachine", "provider_record_id": "dm-1"},
    ]
    conflicts = [
        {
            "field": "square_footage",
            "selected_value": 1_800,
            "material": False,
            "severity": "info",
            "summary": "Living area differs only within tolerance.",
            "observations": [
                {"provider": "rentcast", "value": 1_800},
                {"provider": "dealmachine", "value": 1_760},
            ],
        }
    ]
    scored = score_recorded_sale(
        subject(),
        {
            "id": "rc-1",
            "formattedAddress": "1 Main St, Atlanta, GA 30303",
            "lastSalePrice": 300_000,
            "lastSaleDate": "2026-01-01",
            "propertyType": "Single Family",
            "bedrooms": 3,
            "bathrooms": 2,
            "squareFootage": 1_800,
            "yearBuilt": 1980,
            "lotSize": 8_000,
            "subdivision": "PEACHTREE",
            "source_providers": ["rentcast", "dealmachine"],
            "evidence_provenance": provenance,
            "field_conflicts": conflicts,
            "corroborated": True,
        },
        condition_overrides={},
    )

    assert scored.evidence_sources == ["rentcast", "dealmachine"]
    assert scored.source_providers == scored.evidence_sources
    assert scored.source_observations == provenance
    assert scored.evidence_provenance == provenance
    assert scored.source_conflicts == conflicts
    assert scored.field_conflicts == conflicts
    assert scored.corroboration_count == 2
    assert scored.source_overlap_count == 2
    assert scored.corroborated is True


def test_analyze_comparable_set_rejects_invalid_additional_evidence() -> None:
    invalid = CompAnalystEvidenceInput.model_construct(
        evidence_id="unsupported",
        evidence_type="provider_conflict",
        related_comp_keys=["not-a-known-comp"],
        field="sale_date",
        value="Sources disagree.",
        source_title=None,
        source_url=None,
    )

    result = analyze_comparable_set(
        subject=subject(),
        selected_comps=[comp("selected-1", selected=True)],
        rejected_comps=[],
        market_adjustment=None,
        additional_evidence=[invalid],
        client=None,
        model=None,
    )

    assert result.status == "rejected"
    assert result.comp_recommendations == []


def test_comp_analyst_rejects_unknown_comp_and_missing_range_diagnostics() -> None:
    request, payload = request_and_payload()
    unknown_comp = deepcopy(payload)
    unknown_comp["comp_recommendations"][0]["comp_key"] = "unknown-comp"
    result = run_comp_analyst(
        request,
        client=FakeClient(unknown_comp),  # type: ignore[arg-type]
        model="gpt-test",
    )
    assert result.status == "rejected"

    missing_diagnostics = deepcopy(payload)
    missing_diagnostics["range_explanations"][0]["citations"] = [
        missing_diagnostics["range_explanations"][0]["citations"][1]
    ]
    result = run_comp_analyst(
        request,
        client=FakeClient(missing_diagnostics),  # type: ignore[arg-type]
        model="gpt-test",
    )
    assert result.status == "rejected"
    assert "range diagnostics" in (result.error or "")
