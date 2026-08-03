from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from typing import Any, cast

from reportlab.lib.pagesizes import letter
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table

from app.services.underwriting_reports import (
    ReportContext,
    comp_analyst_story,
    comp_intelligence_story,
    format_market_capture,
    format_primary_as_is_value,
    market_provider_label,
    report_styles,
)


def flowable_text(value: object) -> str:
    if isinstance(value, Paragraph):
        return value.getPlainText()
    if isinstance(value, Table):
        return " ".join(flowable_text(item) for item in cast(Any, value)._cellvalues)
    if isinstance(value, list | tuple):
        return " ".join(flowable_text(item) for item in value)
    content = getattr(value, "_content", None)
    return flowable_text(content) if content is not None else ""


def test_comp_intelligence_story_renders_internal_provider_audit() -> None:
    context = cast(
        ReportContext,
        cast(
            Any,
            SimpleNamespace(
                analysis=SimpleNamespace(
                    analysis_metadata={
                        "comp_intelligence": {
                            "mode": "shadow",
                            "corroborated_sale_count": 2,
                            "duplicate_count": 3,
                            "conflict_count": 1,
                            "evidence_reused": True,
                            "providers": [
                                {
                                    "provider": "rentcast",
                                    "status": "completed",
                                    "valuation_use": "primary_evidence",
                                    "returned_count": 8,
                                    "usable_count": 7,
                                    "net_new_count": 7,
                                    "overlap_count": 0,
                                    "dropped_count": 0,
                                    "ineligible_transfer_count": 0,
                                    "duplicate_count": 1,
                                    "conflict_count": 1,
                                    "credits_used": 0,
                                    "latency_ms": 240,
                                },
                                {
                                    "provider": "dealmachine",
                                    "status": "completed",
                                    "valuation_use": "shadow_only",
                                    "returned_count": 6,
                                    "usable_count": 4,
                                    "net_new_count": 2,
                                    "overlap_count": 2,
                                    "dropped_count": 1,
                                    "ineligible_transfer_count": 1,
                                    "duplicate_count": 2,
                                    "conflict_count": 1,
                                    "credits_used": 0,
                                    "credits_estimated": False,
                                    "latency_ms": 0,
                                    "evidence_reused": True,
                                    "source_credits_used": 2,
                                    "source_credits_estimated": True,
                                    "source_latency_ms": 510,
                                },
                            ],
                            "source_conflicts": [
                                {
                                    "formatted_address": "10 Main St, Atlanta, GA 30303",
                                    "field": "sale_price",
                                    "selected_value": 300000,
                                    "observations": [
                                        {"provider": "rentcast", "value": 300000},
                                        {"provider": "dealmachine", "value": 305000},
                                    ],
                                }
                            ],
                            "external_benchmarks": [
                                {
                                    "provider": "rentcast",
                                    "point_cents": 31_000_000,
                                    "low_cents": 28_000_000,
                                    "high_cents": 35_000_000,
                                    "valuation_use": "excluded_from_arv_and_offer_math",
                                }
                            ],
                            "warnings": ["Review the recorded-sale price conflict."],
                        }
                    }
                )
            ),
        ),
    )
    story = comp_intelligence_story(context, report_styles())
    plain_text = flowable_text(story)
    buffer = BytesIO()
    SimpleDocTemplate(buffer, pagesize=letter, pageCompression=0).build(story)

    pdf = buffer.getvalue()
    assert pdf.startswith(b"%PDF")
    assert "Comparable-source audit" in plain_text
    assert "INTERNAL PROVIDER AUDIT" in plain_text
    assert "DealMachine" in plain_text
    assert "Returned / usable / new / overlap" in plain_text
    assert "source 2 est. / 510 ms" in plain_text
    assert "excluded from Stonegate ARV" in plain_text
    assert "Review the recorded-sale price conflict" in plain_text


def test_comp_analyst_story_preserves_evidence_checks_and_citations() -> None:
    context = cast(
        ReportContext,
        cast(
            Any,
            SimpleNamespace(
                analysis=SimpleNamespace(
                    analysis_metadata={
                        "ai_comp_analyst": {
                            "status": "completed",
                            "model": "gpt-test",
                            "summary": "Draft comparable review completed.",
                            "comp_recommendations": [],
                            "duplicate_candidates": [
                                {
                                    "comp_keys": ["comp-1", "comp-2"],
                                    "reason": "Possible duplicate transfer.",
                                    "citations": [{"evidence_id": "comp_record:comp-1"}],
                                }
                            ],
                            "conflicts": [
                                {
                                    "field": "sale_price",
                                    "comp_keys": ["comp-1"],
                                    "description": "Provider prices differ.",
                                    "citations": [{"evidence_id": "provider_conflict:comp-1"}],
                                }
                            ],
                            "micro_market_concerns": [
                                {
                                    "comp_keys": ["comp-2"],
                                    "concern": "Possible market boundary.",
                                    "why_it_matters": "Confirm buyer reaction.",
                                    "citations": [{"evidence_id": "market_context:comp-2"}],
                                }
                            ],
                            "missing_questions": [
                                {
                                    "question": "Are listing photos available?",
                                    "why_it_matters": "Condition is unknown.",
                                    "related_comp_keys": ["comp-1"],
                                    "citations": [{"evidence_id": "comp_record:comp-1"}],
                                }
                            ],
                            "range_explanations": [
                                {
                                    "driver": "Condition uncertainty",
                                    "affected_comp_keys": ["comp-1"],
                                    "explanation": "Condition remains unverified.",
                                    "resolution_question": "Can staff review photos?",
                                    "citations": [
                                        {"evidence_id": ("deterministic_range_diagnostics")}
                                    ],
                                }
                            ],
                        }
                    }
                )
            ),
        ),
    )

    plain_text = flowable_text(comp_analyst_story(context, report_styles()))

    assert "Possible duplicate transfer" in plain_text
    assert "Provider prices differ" in plain_text
    assert "Possible market boundary" in plain_text
    assert "comp_record:comp-1" in plain_text
    assert "deterministic_range_diagnostics" in plain_text
    assert "Resolve: Can staff review photos?" in plain_text


def test_market_capture_time_keeps_its_timezone_and_provider_label_is_multisource() -> None:
    metadata = {
        "market_data_captured_at": "2026-08-03T16:00:00+00:00",
        "comp_intelligence": {
            "providers": [
                {
                    "provider": "rentcast",
                    "status": "completed",
                    "usable_count": 4,
                },
                {
                    "provider": "dealmachine",
                    "status": "completed",
                    "usable_count": 2,
                },
            ]
        },
    }

    assert format_market_capture(metadata, datetime(2026, 8, 3, tzinfo=UTC)).endswith("UTC")
    assert market_provider_label(metadata, "rentcast") == "RentCast + DealMachine"


def test_primary_as_is_value_never_promotes_provider_avm() -> None:
    metadata = {
        "as_is_value_cents": 30_000_000,
        "as_is_value_low_cents": 28_000_000,
        "as_is_value_high_cents": 32_000_000,
    }

    for value_basis in ("provider_avm_benchmark", "unsupported", None):
        assumptions = {"as_is_value_basis": value_basis}
        assert (
            format_primary_as_is_value(metadata, assumptions, as_range=False)
            == "Not comp-supported"
        )
        assert (
            format_primary_as_is_value(metadata, assumptions, as_range=True) == "Not comp-supported"
        )


def test_primary_as_is_value_shows_verified_closed_sale_support() -> None:
    metadata = {
        "as_is_value_cents": 30_000_000,
        "as_is_value_low_cents": 28_000_000,
        "as_is_value_high_cents": 32_000_000,
    }
    assumptions = {"as_is_value_basis": "verified_as_is_recorded_sales"}

    assert format_primary_as_is_value(metadata, assumptions, as_range=False) == "$300,000"
    assert format_primary_as_is_value(metadata, assumptions, as_range=True) == "$280,000 - $320,000"
