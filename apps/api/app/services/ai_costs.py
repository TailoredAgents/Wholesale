import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.core.config import Settings

PRICING_VERSION = "openai-2026-07-18"
DEFAULT_PRICING_USD_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-5.6": (Decimal("5"), Decimal("30")),
    "gpt-5.6-sol": (Decimal("5"), Decimal("30")),
    "gpt-5.6-terra": (Decimal("2.5"), Decimal("15")),
    "gpt-5.6-luna": (Decimal("1"), Decimal("6")),
    "gpt-5.5": (Decimal("5"), Decimal("30")),
    "gpt-5.4": (Decimal("2.5"), Decimal("15")),
    "gpt-5.4-mini": (Decimal("0.75"), Decimal("4.5")),
    "gpt-5.4-nano": (Decimal("0.2"), Decimal("1.25")),
    "gpt-4o-transcribe": (Decimal("2.5"), Decimal("10")),
    "gpt-4o-transcribe-diarize": (Decimal("2.5"), Decimal("10")),
}


@dataclass(frozen=True)
class AiCostEstimate:
    model: str
    input_tokens: int | None
    output_tokens: int | None
    cost_microusd: int | None
    pricing_status: str
    input_usd_per_million: str | None
    output_usd_per_million: str | None

    def to_metadata(self) -> dict[str, object]:
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_microusd": self.cost_microusd,
            "pricing_status": self.pricing_status,
            "input_usd_per_million": self.input_usd_per_million,
            "output_usd_per_million": self.output_usd_per_million,
            "pricing_version": PRICING_VERSION,
        }


def estimate_openai_cost(
    settings: Settings,
    *,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> AiCostEstimate:
    pricing = pricing_for_model(settings, model)
    if pricing is None:
        return AiCostEstimate(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_microusd=None,
            pricing_status="unpriced_model",
            input_usd_per_million=None,
            output_usd_per_million=None,
        )
    input_rate, output_rate = pricing
    if input_tokens is None or output_tokens is None:
        return AiCostEstimate(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_microusd=None,
            pricing_status="usage_unavailable",
            input_usd_per_million=str(input_rate),
            output_usd_per_million=str(output_rate),
        )
    cost = (
        Decimal(input_tokens) * input_rate + Decimal(output_tokens) * output_rate
    ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return AiCostEstimate(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_microusd=int(cost),
        pricing_status="priced",
        input_usd_per_million=str(input_rate),
        output_usd_per_million=str(output_rate),
    )


def pricing_for_model(
    settings: Settings,
    model: str,
) -> tuple[Decimal, Decimal] | None:
    pricing = dict(DEFAULT_PRICING_USD_PER_MILLION)
    if settings.openai_pricing_overrides_raw.strip():
        try:
            overrides = json.loads(settings.openai_pricing_overrides_raw)
        except json.JSONDecodeError:
            overrides = {}
        if isinstance(overrides, dict):
            for key, value in overrides.items():
                if not isinstance(key, str) or not isinstance(value, dict):
                    continue
                input_rate = value.get("input_usd_per_million")
                output_rate = value.get("output_usd_per_million")
                if isinstance(input_rate, int | float | str) and isinstance(
                    output_rate, int | float | str
                ):
                    pricing[key] = (Decimal(str(input_rate)), Decimal(str(output_rate)))
    return pricing.get(model)


def cents_from_microusd(cost_microusd: int | None) -> int | None:
    if cost_microusd is None:
        return None
    return int(
        (Decimal(cost_microusd) / Decimal(10_000)).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )
