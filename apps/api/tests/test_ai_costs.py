from app.core.config import Settings
from app.services.ai_costs import estimate_openai_cost


def test_openai_cost_estimate_supports_versioned_defaults_and_overrides() -> None:
    settings = Settings.model_validate({"DATABASE_URL": "sqlite+pysqlite:///:memory:"})
    terra = estimate_openai_cost(
        settings,
        model="gpt-5.6-terra",
        input_tokens=2000,
        output_tokens=500,
    )

    assert terra.cost_microusd == 12_500
    assert terra.pricing_status == "priced"

    overridden = Settings.model_validate(
        {
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "OPENAI_PRICING_OVERRIDES_JSON": (
                '{"custom-model":{"input_usd_per_million":1.5,'
                '"output_usd_per_million":7}}'
            ),
        }
    )
    custom = estimate_openai_cost(
        overridden,
        model="custom-model",
        input_tokens=1000,
        output_tokens=100,
    )

    assert custom.cost_microusd == 2200
    assert custom.pricing_status == "priced"


def test_openai_cost_estimate_marks_missing_usage_and_unknown_models() -> None:
    settings = Settings.model_validate({"DATABASE_URL": "sqlite+pysqlite:///:memory:"})

    missing_usage = estimate_openai_cost(
        settings,
        model="gpt-5.6-terra",
        input_tokens=None,
        output_tokens=None,
    )
    unknown = estimate_openai_cost(
        settings,
        model="future-model",
        input_tokens=100,
        output_tokens=20,
    )

    assert missing_usage.cost_microusd is None
    assert missing_usage.pricing_status == "usage_unavailable"
    assert unknown.cost_microusd is None
    assert unknown.pricing_status == "unpriced_model"
