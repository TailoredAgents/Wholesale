from __future__ import annotations

from typing import Literal, Self
from urllib.parse import urldefrag, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EvidenceType = Literal[
    "subject_record",
    "closed_sale_record",
    "listing_history",
    "condition_review",
    "public_record",
    "provider_conflict",
    "human_note",
    "market_context",
    "other",
]
CompRecommendation = Literal["include", "exclude", "review"]
ConditionHypothesis = Literal["renovated", "as_is", "mixed", "unknown"]
SpreadAssessment = Literal["unknown", "compact", "moderate", "wide"]

EVIDENCE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$"


def normalize_source_url(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Source URLs must be strings or null.")
    candidate, _fragment = urldefrag(value.strip())
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Source URLs must use HTTP or HTTPS.")
    path = parsed.path
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            parsed.query,
            "",
        )
    )


class CompAnalystSubjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(
        default="subject_record",
        min_length=1,
        max_length=160,
        pattern=EVIDENCE_ID_PATTERN,
    )
    formatted_address: str = Field(min_length=3, max_length=500)
    property_type: str | None = Field(default=None, max_length=80)
    bedrooms: float | None = Field(default=None, ge=0, le=100)
    bathrooms: float | None = Field(default=None, ge=0, le=100)
    square_footage: int | None = Field(default=None, ge=1, le=1_000_000)
    lot_size: int | None = Field(default=None, ge=0, le=1_000_000_000)
    year_built: int | None = Field(default=None, ge=1600, le=2300)
    subdivision: str | None = Field(default=None, max_length=255)
    garage: bool | None = None
    pool: bool | None = None
    basement: bool | None = None
    source_url: str | None = Field(default=None, max_length=2000)

    _normalize_url = field_validator("source_url", mode="before")(normalize_source_url)


class CompAnalystComparableInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(
        min_length=1,
        max_length=160,
        pattern=EVIDENCE_ID_PATTERN,
    )
    comp_key: str = Field(min_length=1, max_length=500)
    formatted_address: str | None = Field(max_length=500)
    selection_status: Literal["selected", "rejected"]
    selection_reason: str = Field(min_length=1, max_length=1000)
    property_type: str | None = Field(max_length=80)
    sale_date: str | None = Field(max_length=40)
    sale_price_cents: int | None = Field(ge=0, le=100_000_000_000)
    bedrooms: float | None = Field(ge=0, le=100)
    bathrooms: float | None = Field(ge=0, le=100)
    square_footage: int | None = Field(ge=1, le=1_000_000)
    lot_size: int | None = Field(ge=0, le=1_000_000_000)
    year_built: int | None = Field(ge=1600, le=2300)
    distance_miles: float | None = Field(ge=0, le=1000)
    subdivision: str | None = Field(max_length=255)
    subdivision_match: bool | None
    garage: bool | None
    pool: bool | None
    basement: bool | None
    condition_classification: Literal["renovated", "as_is", "unknown"]
    condition_evidence: str | None = Field(max_length=1000)
    comp_grade: Literal["A", "B", "C", "D"] | None
    search_level: Literal["preferred", "expanded", "extended", "manual"] | None
    score: int = Field(ge=0, le=100)
    search_warnings: list[str] = Field(max_length=12)
    evidence_source: str | None = Field(max_length=120)
    source_url: str | None = Field(max_length=2000)
    transaction_type: str | None = Field(max_length=160)
    transaction_eligibility: Literal["not_flagged", "unverified", "ineligible"] | None
    transaction_review_reason: str | None = Field(max_length=1000)

    _normalize_url = field_validator("source_url", mode="before")(normalize_source_url)

    @field_validator("search_warnings")
    @classmethod
    def validate_search_warnings(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 500 for item in value):
            raise ValueError("Search warnings must be non-empty and no longer than 500 characters.")
        return list(dict.fromkeys(item.strip() for item in value))


class CompAnalystEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(
        min_length=1,
        max_length=160,
        pattern=EVIDENCE_ID_PATTERN,
    )
    evidence_type: EvidenceType
    related_comp_keys: list[str] = Field(default_factory=list, max_length=20)
    field: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=2000)
    source_title: str | None = Field(default=None, max_length=500)
    source_url: str | None = Field(default=None, max_length=2000)

    _normalize_url = field_validator("source_url", mode="before")(normalize_source_url)

    @field_validator("field")
    @classmethod
    def exclude_price_authority_fields(cls, value: str) -> str:
        normalized = "_".join(value.lower().replace("-", " ").split())
        forbidden = {
            "arv",
            "after_repair_value",
            "adjusted_value",
            "dollar_adjustment",
            "mao",
            "maximum_allowable_offer",
            "offer",
            "recommended_offer",
            "seller_ceiling",
            "seller_contract_ceiling",
            "value_estimate",
        }
        if normalized in forbidden:
            raise ValueError("AI comp evidence cannot contain a price-authority conclusion.")
        return value.strip()

    @field_validator("related_comp_keys")
    @classmethod
    def validate_related_comp_keys(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item or len(item) > 500 for item in cleaned):
            raise ValueError("Related comp keys must be between 1 and 500 characters.")
        return list(dict.fromkeys(cleaned))


class CompAnalystRangeContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(
        default="deterministic_range_diagnostics",
        min_length=1,
        max_length=160,
        pattern=EVIDENCE_ID_PATTERN,
    )
    spread_assessment: SpreadAssessment = "unknown"
    selected_comp_count: int = Field(default=0, ge=0, le=20)
    supported_adjustment_keys: list[str] = Field(default_factory=list, max_length=20)
    withheld_adjustment_keys: list[str] = Field(default_factory=list, max_length=20)
    review_comp_keys: list[str] = Field(default_factory=list, max_length=20)
    expanded_search_comp_keys: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("supported_adjustment_keys", "withheld_adjustment_keys")
    @classmethod
    def validate_adjustment_keys(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item or len(item) > 120 for item in cleaned):
            raise ValueError("Adjustment keys must be between 1 and 120 characters.")
        return list(dict.fromkeys(cleaned))

    @field_validator("review_comp_keys", "expanded_search_comp_keys")
    @classmethod
    def validate_comp_keys(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item or len(item) > 500 for item in cleaned):
            raise ValueError("Comp keys must be between 1 and 500 characters.")
        return list(dict.fromkeys(cleaned))


class CompAnalystRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: CompAnalystSubjectInput
    comparables: list[CompAnalystComparableInput] = Field(max_length=20)
    evidence: list[CompAnalystEvidenceInput] = Field(default_factory=list, max_length=80)
    range_context: CompAnalystRangeContext = Field(default_factory=CompAnalystRangeContext)

    @model_validator(mode="after")
    def validate_identifiers(self) -> Self:
        comp_keys = [comp.comp_key for comp in self.comparables]
        if len(set(comp_keys)) != len(comp_keys):
            raise ValueError("Comparable keys must be unique.")
        known_comp_keys = set(comp_keys)
        evidence_ids = [
            self.subject.evidence_id,
            self.range_context.evidence_id,
            *(comp.evidence_id for comp in self.comparables),
            *(item.evidence_id for item in self.evidence),
        ]
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("Evidence IDs must be unique.")
        for item in self.evidence:
            if not set(item.related_comp_keys).issubset(known_comp_keys):
                raise ValueError("Evidence cannot reference an unknown comparable.")
        diagnostics_keys = {
            *self.range_context.review_comp_keys,
            *self.range_context.expanded_search_comp_keys,
        }
        if not diagnostics_keys.issubset(known_comp_keys):
            raise ValueError("Range diagnostics cannot reference an unknown comparable.")
        if self.range_context.selected_comp_count != sum(
            comp.selection_status == "selected" for comp in self.comparables
        ):
            raise ValueError("The selected comp count must match the comparable records.")
        return self


class CompAnalystCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(
        min_length=1,
        max_length=160,
        pattern=EVIDENCE_ID_PATTERN,
    )
    source_url: str | None = Field(max_length=2000)

    _normalize_url = field_validator("source_url", mode="before")(normalize_source_url)


class CompAnalystCompRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comp_key: str = Field(min_length=1, max_length=500)
    recommendation: CompRecommendation
    reason: str = Field(min_length=1, max_length=1200)
    condition_hypothesis: ConditionHypothesis
    condition_reason: str = Field(min_length=1, max_length=1000)
    micro_market_concerns: list[str] = Field(max_length=8)
    confidence: int = Field(ge=0, le=100)
    citations: list[CompAnalystCitation] = Field(min_length=1, max_length=12)
    requires_human_approval: Literal[True]


class CompAnalystDuplicateCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comp_keys: list[str] = Field(min_length=2, max_length=8)
    reason: str = Field(min_length=1, max_length=1000)
    confidence: int = Field(ge=0, le=100)
    citations: list[CompAnalystCitation] = Field(min_length=1, max_length=12)


class CompAnalystConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=120)
    comp_keys: list[str] = Field(min_length=1, max_length=20)
    description: str = Field(min_length=1, max_length=1000)
    requires_human_resolution: Literal[True]
    citations: list[CompAnalystCitation] = Field(min_length=1, max_length=12)


class CompAnalystMicroMarketConcern(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comp_keys: list[str] = Field(min_length=1, max_length=20)
    concern: str = Field(min_length=1, max_length=500)
    why_it_matters: str = Field(min_length=1, max_length=1000)
    citations: list[CompAnalystCitation] = Field(min_length=1, max_length=12)


class CompAnalystMissingQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=500)
    why_it_matters: str = Field(min_length=1, max_length=1000)
    related_comp_keys: list[str] = Field(max_length=20)
    citations: list[CompAnalystCitation] = Field(min_length=1, max_length=12)


class CompAnalystRangeExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    driver: str = Field(min_length=1, max_length=500)
    affected_comp_keys: list[str] = Field(min_length=1, max_length=20)
    explanation: str = Field(min_length=1, max_length=1000)
    resolution_question: str | None = Field(max_length=500)
    citations: list[CompAnalystCitation] = Field(min_length=1, max_length=12)


class CompAnalystDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "insufficient"]
    summary: str = Field(min_length=1, max_length=2000)
    analysis_role: Literal["draft_comp_review_support"]
    human_review_required: Literal[True]
    valuation_use: Literal["excluded_from_arv_and_offer_math"]
    comp_recommendations: list[CompAnalystCompRecommendation] = Field(max_length=20)
    duplicate_candidates: list[CompAnalystDuplicateCandidate] = Field(max_length=20)
    conflicts: list[CompAnalystConflict] = Field(max_length=20)
    micro_market_concerns: list[CompAnalystMicroMarketConcern] = Field(max_length=20)
    missing_questions: list[CompAnalystMissingQuestion] = Field(max_length=20)
    range_explanations: list[CompAnalystRangeExplanation] = Field(max_length=20)
    limitations: list[str] = Field(max_length=12)


class CompAnalystUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class CompAnalystRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    status: Literal["completed", "insufficient", "unavailable", "rejected"]
    mode: Literal["draft"]
    valuation_use: Literal["excluded_from_arv_and_offer_math"]
    human_review_required: Literal[True]
    summary: str
    comp_recommendations: list[CompAnalystCompRecommendation]
    duplicate_candidates: list[CompAnalystDuplicateCandidate]
    conflicts: list[CompAnalystConflict]
    micro_market_concerns: list[CompAnalystMicroMarketConcern]
    missing_questions: list[CompAnalystMissingQuestion]
    range_explanations: list[CompAnalystRangeExplanation]
    limitations: list[str]
    model: str | None
    usage: CompAnalystUsage | None
    latency_ms: int | None = Field(ge=0)
    error: str | None

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        draft_fields_have_content = any(
            (
                self.comp_recommendations,
                self.duplicate_candidates,
                self.conflicts,
                self.micro_market_concerns,
                self.missing_questions,
                self.range_explanations,
            )
        )
        if self.status in {"unavailable", "rejected"} and draft_fields_have_content:
            raise ValueError("Unavailable and rejected results cannot expose draft advice.")
        if self.status in {"completed", "insufficient"} and self.error is not None:
            raise ValueError("Completed and insufficient results cannot contain an error.")
        if self.status in {"unavailable", "rejected"} and not self.error:
            raise ValueError("Unavailable and rejected results require an error.")
        return self
