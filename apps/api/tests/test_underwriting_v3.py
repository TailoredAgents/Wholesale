from app.services.underwriting_v2 import UnderwritingV2Result
from app.services.underwriting_v3 import unsupported_result


def baseline_result() -> UnderwritingV2Result:
    return UnderwritingV2Result(
        selected_comps=[],
        rejected_comps=[],
        as_is_low_cents=20_000_000,
        as_is_value_cents=21_000_000,
        as_is_high_cents=22_000_000,
        arv_low_cents=28_000_000,
        arv_point_cents=30_000_000,
        arv_high_cents=32_000_000,
        conservative_arv_cents=28_500_000,
        repair_low_cents=4_000_000,
        repair_high_cents=6_000_000,
        base_rehab_cents=5_000_000,
        rehab_contingency_percentage=15,
        total_rehab_cents=5_750_000,
        flip_buyer_max_cents=14_000_000,
        rental_buyer_max_cents=13_000_000,
        recommended_disposition_cents=14_000_000,
        seller_contract_ceiling_cents=12_250_000,
        recommended_opening_offer_cents=11_250_000,
        legacy_rule_cents=13_000_000,
        monthly_rent_cents=220_000,
        confidence_score=72,
        confidence_tier="review",
        confidence_factors=[],
        manual_review_required=False,
        review_reasons=[],
        data_disagreements=[],
        assumptions={"canonical_subject_facts": {"squareFootage": 1800}},
    )


def test_unsupported_v3_never_silently_uses_the_rollback_value() -> None:
    result = unsupported_result(
        baseline_result(),
        {
            "version": "v3",
            "status": "unsupported",
            "conclusion": {"confidence_score": 40},
            "warnings": ["Only two usable closed sales were available."],
            "confidence_factors": [],
        },
    )

    assert result.arv_point_cents is None
    assert result.recommended_disposition_cents is None
    assert result.seller_contract_ceiling_cents is None
    assert result.recommended_opening_offer_cents is None
    assert result.manual_review_required is True
    assert result.assumptions["rollback_arv_point_cents"] == 30_000_000
    assert any("at least three usable" in reason for reason in result.review_reasons)
