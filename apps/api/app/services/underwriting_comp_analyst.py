from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast

from pydantic import ValidationError

from app.integrations.openai_client import OpenAIClientError, OpenAIResponsesClient
from app.schemas.leads import MarketAnalysisCompRead
from app.schemas.underwriting_comp_analyst import (
    CompAnalystCitation,
    CompAnalystComparableInput,
    CompAnalystCompRecommendation,
    CompAnalystDraft,
    CompAnalystEvidenceInput,
    CompAnalystRangeContext,
    CompAnalystRequest,
    CompAnalystRunResult,
    CompAnalystSubjectInput,
    CompAnalystUsage,
    SpreadAssessment,
)

COMP_ANALYST_VERSION = "u4.ai-comp-analyst.v1"
COMP_ANALYST_PROMPT_CACHE_KEY = "stonegate:underwriting-comp-analyst:v1"
MAX_CONTEXT_CHARACTERS = 120_000

COMP_ANALYST_OUTPUT_SCHEMA: dict[str, Any] = CompAnalystDraft.model_json_schema()

SYSTEM_PROMPT = """
You are Stonegate's bounded comparable-sale review assistant. Your work is a draft for a
human underwriter, and it is excluded from valuation and offer math.

Use only the supplied subject, comparable records, deterministic range diagnostics, and
evidence records. Do not browse, use prior knowledge, invent a property fact, or resolve a
source conflict. Return exactly one include, exclude, or review recommendation for every
supplied comparable. "Review" is the safe choice when evidence is missing or conflicting.

Condition is always a hypothesis, never a final classification. Cite the comparable's own
record for every recommendation and every affected comparable in a duplicate, conflict,
micro-market concern, missing question, or range explanation. Copy a supplied source URL
exactly when that evidence has one; otherwise return null. Range explanations must also cite
the deterministic range diagnostics record. A source conflict must copy the supplied conflict
field exactly and cite the matching provider_conflict evidence record.

Never calculate, recommend, repeat, or imply ARV, after-repair value, an offer, MAO, a seller
ceiling, a property value conclusion, a comparable weight, or a dollar adjustment. Do not put
currency amounts in narrative text. Do not describe a condition hypothesis as confirmed or
final. The deterministic Stonegate engine owns all arithmetic and a person owns all comp and
condition decisions. Never recommend including a comparable marked as an ineligible transfer.
State a micro-market fact only when a supplied market-context, public-record, or human-note
item supports it; otherwise ask it as a missing question. Return only the strict structured object.
For a completed draft, summary must be exactly: "Draft comparable review completed; all
recommendations require human approval." Return limitations as an empty array; route every
uncertainty through a cited missing question or another cited structured claim.
""".strip()

FORBIDDEN_NARRATIVE_PATTERNS = (
    re.compile(r"\bARV\b", re.IGNORECASE),
    re.compile(r"\bafter[- ]repair value\b", re.IGNORECASE),
    re.compile(r"\bMAO\b", re.IGNORECASE),
    re.compile(
        r"\b(?:seller|contract|purchase|cash|opening|maximum allowable)\s+offer\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bseller(?: contract)? ceiling\b", re.IGNORECASE),
    re.compile(r"\$"),
    re.compile(r"\bUSD\b", re.IGNORECASE),
    re.compile(r"\b\d[\d,]*(?:\.\d+)?\s*(?:dollars?|bucks)\b", re.IGNORECASE),
    re.compile(r"\b\d[\d,]*(?:\.\d+)?\s*cents\b", re.IGNORECASE),
    re.compile(
        r"\b(?:price|value|adjustment|offer)\s+(?:of|is|at)?\s*"
        r"\d[\d,.]*(?:\s*[km])?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b\d[\d,.]*(?:\s*[km])?\s+"
        r"(?:sale price|price|value|adjustment|offer)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:worth|buy|pay|paying|purchase)\b[^.!?\n]{0,40}"
        r"\b(?:\d{5,}|\d+(?:\.\d+)?\s*[km])\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:\d{5,}|\d+(?:\.\d+)?\s*[km])\b[^.!?\n]{0,40}"
        r"\b(?:worth|buy|pay|paying|purchase)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:add|subtract|deduct|increase|decrease|adjust)\b[^.!?\n]{0,40}"
        r"\b(?:\d[\d,.]*(?:\s*[km])?|(?:one|two|three|four|five|six|seven|eight|"
        r"nine|ten|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
        r"(?:[- ]\w+)*[- ]+(?:hundred|thousand|million))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:resell|resale|acquisition target|purchase target|seller ceiling|"
        r"ceiling)\b[^.!?\n]{0,50}\b\d[\d,.]*(?:\s*[km])?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b\d[\d,.]*(?:\s*[km])?\b[^.!?\n]{0,50}"
        r"\b(?:resell|resale|acquisition target|purchase target|seller ceiling|"
        r"ceiling)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bcondition\s+(?:is|=|classified as|should be classified as)\s+"
        r"(?:renovated|as[- ]?is)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:definitely|confirmed|conclusively|finally)\s+"
        r"(?:renovated|as[- ]?is)\b",
        re.IGNORECASE,
    ),
)


class CompAnalystPolicyError(ValueError):
    pass


def unavailable_comp_analyst(
    reason: str,
    *,
    model: str | None = None,
    latency_ms: int = 0,
) -> CompAnalystRunResult:
    """Return the stable no-advice envelope for disabled or unavailable AI review."""
    return _empty_result(
        status="unavailable",
        summary="AI comp review was not added to this analysis.",
        error=(_text(reason) or "The AI Comp Analyst is unavailable.")[:500],
        model=model,
        latency_ms=max(0, latency_ms),
    )


def analyze_comparable_set(
    *,
    subject: Mapping[str, Any],
    selected_comps: Sequence[MarketAnalysisCompRead],
    rejected_comps: Sequence[MarketAnalysisCompRead],
    market_adjustment: Mapping[str, Any] | None,
    additional_evidence: Sequence[CompAnalystEvidenceInput] = (),
    client: OpenAIResponsesClient | None,
    model: str | None,
    reasoning_effort: str = "low",
    safety_identifier: str | None = None,
) -> CompAnalystRunResult:
    """Build the bounded request and return draft-only comparable review support."""
    started = time.perf_counter()
    try:
        request = build_comp_analyst_request(
            subject=subject,
            selected_comps=selected_comps,
            rejected_comps=rejected_comps,
            market_adjustment=market_adjustment,
            additional_evidence=additional_evidence,
        )
    except (ValidationError, ValueError):
        return _empty_result(
            status="rejected",
            summary="The comp analyst request did not pass its bounded input contract.",
            error="Invalid or unsupported comp analyst input was rejected.",
            model=model,
            latency_ms=_elapsed_ms(started),
        )
    return run_comp_analyst(
        request,
        client=client,
        model=model,
        reasoning_effort=reasoning_effort,
        safety_identifier=safety_identifier,
        started=started,
    )


def build_comp_analyst_request(
    *,
    subject: Mapping[str, Any],
    selected_comps: Sequence[MarketAnalysisCompRead],
    rejected_comps: Sequence[MarketAnalysisCompRead],
    market_adjustment: Mapping[str, Any] | None = None,
    additional_evidence: Sequence[CompAnalystEvidenceInput] = (),
) -> CompAnalystRequest:
    bounded_selected = list(selected_comps)[:20]
    remaining_slots = max(0, 20 - len(bounded_selected))
    bounded_rejected = sorted(
        rejected_comps,
        key=lambda comp: (
            -comp.score,
            comp.provider_id or "",
            comp.formatted_address or "",
        ),
    )[:remaining_slots]
    comparables = [
        _comparable_input(comp, selection_status="selected", index=index)
        for index, comp in enumerate(bounded_selected)
    ]
    comparables.extend(
        _comparable_input(
            comp,
            selection_status="rejected",
            index=len(comparables) + index,
        )
        for index, comp in enumerate(bounded_rejected)
    )
    additional = list(additional_evidence)
    auto_evidence = _provider_evidence(
        comparables,
        [*bounded_selected, *bounded_rejected],
    )[: max(0, 80 - len(additional))]
    range_context = build_comp_analyst_range_context(
        market_adjustment or {},
        selected_comps=bounded_selected,
        all_comps=[*bounded_selected, *bounded_rejected],
    )
    return CompAnalystRequest(
        subject=_subject_input(subject),
        comparables=comparables,
        evidence=[*auto_evidence, *additional],
        range_context=range_context,
    )


def build_saved_comp_context_evidence(
    *,
    selected_comps: Sequence[MarketAnalysisCompRead],
    rejected_comps: Sequence[MarketAnalysisCompRead],
    secondary_evidence: Mapping[str, Any],
) -> list[CompAnalystEvidenceInput]:
    """Convert already-saved cited research facts into bounded analyst evidence."""
    all_comps = [*selected_comps, *rejected_comps][:20]
    comp_keys = [_comp_key(comp, index) for index, comp in enumerate(all_comps)]
    source_keys: dict[str, list[str]] = {}
    for index, comp in enumerate(all_comps):
        source_url = _safe_url(comp.source_url)
        if source_url:
            source_keys.setdefault(source_url, []).append(_comp_key(comp, index))

    evidence: list[CompAnalystEvidenceInput] = []
    facts = secondary_evidence.get("facts")
    if not isinstance(facts, list):
        return evidence
    for index, raw_fact in enumerate(facts[:20]):
        if not isinstance(raw_fact, Mapping):
            continue
        value = _text(raw_fact.get("value"))
        field = _text(raw_fact.get("fact_type"))
        if value is None or field is None:
            continue
        source_url = _safe_url(raw_fact.get("source_url"))
        related_keys = source_keys.get(source_url or "", [])
        evidence_type = (
            "market_context"
            if field == "market_context"
            else "listing_history"
            if field == "listing_history"
            else "public_record"
        )
        if evidence_type == "market_context" and not related_keys:
            related_keys = comp_keys
        evidence.append(
            CompAnalystEvidenceInput(
                evidence_id=_evidence_id(
                    "saved_research",
                    f"{index}:{field}:{source_url or value}",
                ),
                evidence_type=evidence_type,
                related_comp_keys=related_keys,
                field=field,
                value=value[:2000],
                source_title=_text(raw_fact.get("source_title")),
                source_url=source_url,
            )
        )
    return evidence


def build_comp_analyst_range_context(
    market_adjustment: Mapping[str, Any],
    *,
    selected_comps: Sequence[MarketAnalysisCompRead],
    all_comps: Sequence[MarketAnalysisCompRead],
) -> CompAnalystRangeContext:
    conclusion = _mapping(market_adjustment.get("conclusion"))
    low = _integer(conclusion.get("arv_low_cents"))
    point = _integer(conclusion.get("arv_point_cents"))
    high = _integer(conclusion.get("arv_high_cents"))
    spread_assessment: SpreadAssessment = "unknown"
    if low is not None and point and point > 0 and high is not None and high >= low:
        spread_ratio = (high - low) / point
        if spread_ratio >= 0.15:
            spread_assessment = "wide"
        elif spread_ratio >= 0.08:
            spread_assessment = "moderate"
        else:
            spread_assessment = "compact"

    rate_evidence = [
        item for item in market_adjustment.get("rate_evidence", []) if isinstance(item, Mapping)
    ]
    supported = [
        key
        for item in rate_evidence
        if item.get("status") == "supported" and (key := _text(item.get("key")))
    ]
    withheld = [
        key
        for item in rate_evidence
        if item.get("status") != "supported" and (key := _text(item.get("key")))
    ]
    known_keys = {_comp_key(comp, index) for index, comp in enumerate(all_comps)}
    review_keys = [
        key
        for item in market_adjustment.get("comp_adjustments", [])
        if isinstance(item, Mapping)
        and item.get("requires_review") is True
        and (key := _text(item.get("comp_key"))) in known_keys
    ]
    expanded_keys = [
        key
        for index, comp in enumerate(all_comps)
        if comp.search_level in {"expanded", "extended", "manual"}
        and (key := _comp_key(comp, index))
    ]
    return CompAnalystRangeContext(
        spread_assessment=spread_assessment,
        selected_comp_count=len(selected_comps),
        supported_adjustment_keys=list(dict.fromkeys(supported)),
        withheld_adjustment_keys=list(dict.fromkeys(withheld)),
        review_comp_keys=list(dict.fromkeys(review_keys)),
        expanded_search_comp_keys=list(dict.fromkeys(expanded_keys)),
    )


def run_comp_analyst(
    request: CompAnalystRequest | Mapping[str, Any],
    *,
    client: OpenAIResponsesClient | None,
    model: str | None,
    reasoning_effort: str = "low",
    safety_identifier: str | None = None,
    started: float | None = None,
) -> CompAnalystRunResult:
    """Run a stateless structured draft and reject any output outside supplied evidence."""
    started_at = started if started is not None else time.perf_counter()
    try:
        bounded_request = CompAnalystRequest.model_validate(request)
    except ValidationError:
        return _empty_result(
            status="rejected",
            summary="The comp analyst request did not pass its bounded input contract.",
            error="Invalid or unsupported comp analyst input was rejected.",
            model=model,
            latency_ms=_elapsed_ms(started_at),
        )

    if not bounded_request.comparables:
        draft = _insufficient_draft()
        return _result_from_draft(
            draft,
            model=None,
            usage=None,
            latency_ms=_elapsed_ms(started_at),
        )
    model_name = _text(model)
    if client is None or model_name is None:
        return unavailable_comp_analyst(
            "The AI Comp Analyst is disabled or its provider is not configured.",
            model=model_name,
            latency_ms=_elapsed_ms(started_at),
        )

    user_prompt = json.dumps(
        {
            "task": (
                "Review every supplied comparable as draft decision support, identify possible "
                "duplicates and source conflicts, surface condition and micro-market uncertainty, "
                "ask the most useful missing questions, and explain the supplied range category."
            ),
            "input": bounded_request.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(user_prompt) > MAX_CONTEXT_CHARACTERS:
        return _empty_result(
            status="rejected",
            summary="The comp analyst request exceeded its bounded context limit.",
            error="Oversized comp analyst input was rejected.",
            model=model_name,
            latency_ms=_elapsed_ms(started_at),
        )

    try:
        parsed, raw_usage = client.create_structured_response(
            model=model_name,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            schema_name="stonegate_underwriting_comp_analyst",
            json_schema=COMP_ANALYST_OUTPUT_SCHEMA,
            reasoning_effort=reasoning_effort,
            max_output_tokens=5000,
            safety_identifier=safety_identifier,
            prompt_cache_key=COMP_ANALYST_PROMPT_CACHE_KEY,
        )
    except OpenAIClientError as exc:
        return unavailable_comp_analyst(
            _safe_provider_error(exc),
            model=model_name,
            latency_ms=_elapsed_ms(started_at),
        )
    except Exception:  # noqa: BLE001 - optional AI must never abort deterministic underwriting.
        return unavailable_comp_analyst(
            "The AI Comp Analyst failed safely before its draft could be accepted.",
            model=model_name,
            latency_ms=_elapsed_ms(started_at),
        )

    usage: CompAnalystUsage | None = None
    try:
        usage = _usage(raw_usage)
        draft = CompAnalystDraft.model_validate(parsed)
        validate_comp_analyst_draft(draft, bounded_request)
        result = _result_from_draft(
            draft,
            model=model_name,
            usage=usage,
            latency_ms=_elapsed_ms(started_at),
        )
    except ValidationError:
        return _empty_result(
            status="rejected",
            summary="The AI comp draft failed its strict structured contract.",
            error="The provider output was rejected before it could reach underwriting.",
            model=model_name,
            latency_ms=_elapsed_ms(started_at),
            usage=usage,
        )
    except CompAnalystPolicyError as exc:
        return _empty_result(
            status="rejected",
            summary="The AI comp draft failed its evidence or authority boundary.",
            error=str(exc),
            model=model_name,
            latency_ms=_elapsed_ms(started_at),
            usage=usage,
        )
    except Exception:  # noqa: BLE001 - malformed optional output must fail closed.
        return _empty_result(
            status="rejected",
            summary="The AI comp draft failed its strict structured contract.",
            error="The provider output was rejected before it could reach underwriting.",
            model=model_name,
            latency_ms=_elapsed_ms(started_at),
            usage=usage,
        )

    return result


def validate_comp_analyst_draft(
    draft: CompAnalystDraft,
    request: CompAnalystRequest,
) -> None:
    """Enforce evidence, comparable, URL, and price-authority boundaries."""
    comparables = {comp.comp_key: comp for comp in request.comparables}
    expected_keys = set(comparables)
    recommendation_keys = [item.comp_key for item in draft.comp_recommendations]
    if len(set(recommendation_keys)) != len(recommendation_keys):
        raise CompAnalystPolicyError("Duplicate comparable recommendations were rejected.")
    if set(recommendation_keys) != expected_keys:
        raise CompAnalystPolicyError(
            "The draft did not return exactly one recommendation for every supplied comparable."
        )

    evidence_urls: dict[str, str | None] = {
        request.subject.evidence_id: request.subject.source_url,
        request.range_context.evidence_id: None,
        **{comp.evidence_id: comp.source_url for comp in request.comparables},
        **{item.evidence_id: item.source_url for item in request.evidence},
    }
    supplied_evidence = {item.evidence_id: item for item in request.evidence}
    comp_evidence_ids = {comp.comp_key: comp.evidence_id for comp in request.comparables}

    if draft.summary != (
        "Draft comparable review completed; all recommendations require human approval."
    ):
        raise CompAnalystPolicyError(
            "The draft summary must use Stonegate's non-factual review template."
        )
    if draft.limitations:
        raise CompAnalystPolicyError(
            "Uncited limitations must be routed through cited missing questions."
        )

    for recommendation in draft.comp_recommendations:
        _validate_comp_keys([recommendation.comp_key], expected_keys)
        if (
            recommendation.recommendation == "include"
            and comparables[recommendation.comp_key].transaction_eligibility == "ineligible"
        ):
            raise CompAnalystPolicyError(
                "The draft attempted to include a deterministic non-market transfer."
            )
        _validate_citations(recommendation.citations, evidence_urls)
        _require_comp_record_citations(
            recommendation.citations,
            [recommendation.comp_key],
            comp_evidence_ids,
        )
        _validate_contextual_claims(
            [
                recommendation.reason,
                recommendation.condition_reason,
                *recommendation.micro_market_concerns,
            ],
            citations=recommendation.citations,
            comp_keys=[recommendation.comp_key],
            supplied_evidence=supplied_evidence,
        )
        if recommendation.micro_market_concerns:
            _require_market_context_citation(
                recommendation.citations,
                [recommendation.comp_key],
                supplied_evidence,
                claims=recommendation.micro_market_concerns,
            )
        if _contains_micro_market_claim(recommendation.reason):
            _require_market_context_citation(
                recommendation.citations,
                [recommendation.comp_key],
                supplied_evidence,
                claims=[recommendation.reason],
            )
        if _contains_conflict_claim(recommendation.reason):
            _require_matching_conflict_citation(
                recommendation.citations,
                [recommendation.comp_key],
                supplied_evidence,
            )
        if recommendation.condition_hypothesis != "unknown":
            _require_condition_support(
                recommendation,
                comparable=comparables[recommendation.comp_key],
                supplied_evidence=supplied_evidence,
            )
    for duplicate in draft.duplicate_candidates:
        keys = _unique_comp_keys(duplicate.comp_keys, expected_keys)
        _validate_citations(duplicate.citations, evidence_urls)
        _require_comp_record_citations(duplicate.citations, keys, comp_evidence_ids)
        _validate_contextual_claims(
            [duplicate.reason],
            citations=duplicate.citations,
            comp_keys=keys,
            supplied_evidence=supplied_evidence,
        )
    for conflict in draft.conflicts:
        keys = _unique_comp_keys(conflict.comp_keys, expected_keys)
        _validate_citations(conflict.citations, evidence_urls)
        _require_comp_record_citations(conflict.citations, keys, comp_evidence_ids)
        cited_conflicts = [
            supplied_evidence[citation.evidence_id]
            for citation in conflict.citations
            if citation.evidence_id in supplied_evidence
            and supplied_evidence[citation.evidence_id].evidence_type == "provider_conflict"
        ]
        if not any(
            _field_key(item.field) == _field_key(conflict.field)
            and bool(set(item.related_comp_keys).intersection(keys))
            for item in cited_conflicts
        ):
            raise CompAnalystPolicyError(
                "A source-conflict claim lacked matching supplied conflict evidence."
            )
    for concern in draft.micro_market_concerns:
        keys = _unique_comp_keys(concern.comp_keys, expected_keys)
        _validate_citations(concern.citations, evidence_urls)
        _require_comp_record_citations(concern.citations, keys, comp_evidence_ids)
        _require_market_context_citation(
            concern.citations,
            keys,
            supplied_evidence,
            claims=[concern.concern, concern.why_it_matters],
        )
    for question in draft.missing_questions:
        keys = _unique_comp_keys(question.related_comp_keys, expected_keys)
        _validate_citations(question.citations, evidence_urls)
        if keys:
            _require_comp_record_citations(question.citations, keys, comp_evidence_ids)
        elif request.subject.evidence_id not in {
            citation.evidence_id for citation in question.citations
        }:
            raise CompAnalystPolicyError(
                "A subject-level missing question lacked subject evidence."
            )
        _validate_contextual_claims(
            [question.question, question.why_it_matters],
            citations=question.citations,
            comp_keys=keys,
            supplied_evidence=supplied_evidence,
        )
    for explanation in draft.range_explanations:
        keys = _unique_comp_keys(explanation.affected_comp_keys, expected_keys)
        _validate_citations(explanation.citations, evidence_urls)
        _require_comp_record_citations(explanation.citations, keys, comp_evidence_ids)
        if request.range_context.evidence_id not in {
            citation.evidence_id for citation in explanation.citations
        }:
            raise CompAnalystPolicyError(
                "A range explanation lacked deterministic range diagnostics."
            )
        _validate_contextual_claims(
            [
                explanation.driver,
                explanation.explanation,
                explanation.resolution_question or "",
            ],
            citations=explanation.citations,
            comp_keys=keys,
            supplied_evidence=supplied_evidence,
        )

    for narrative in _draft_narratives(draft):
        if any(pattern.search(narrative) for pattern in FORBIDDEN_NARRATIVE_PATTERNS):
            raise CompAnalystPolicyError(
                "The draft attempted to cross Stonegate's price or decision-authority boundary."
            )


def _subject_input(subject: Mapping[str, Any]) -> CompAnalystSubjectInput:
    features = _mapping(subject.get("features"))
    formatted_address = (
        _text(subject.get("formattedAddress"))
        or _text(subject.get("validated_formatted_address"))
        or _formatted_address(subject)
        or "Subject property"
    )
    return CompAnalystSubjectInput(
        formatted_address=formatted_address,
        property_type=_text(subject.get("propertyType")),
        bedrooms=_number(subject.get("bedrooms")),
        bathrooms=_number(subject.get("bathrooms")),
        square_footage=_integer(subject.get("squareFootage")),
        lot_size=_integer(subject.get("lotSize")),
        year_built=_integer(subject.get("yearBuilt")),
        subdivision=_text(subject.get("subdivision")),
        garage=_boolean(features.get("garage")),
        pool=_boolean(features.get("pool")),
        basement=_basement(features),
        source_url=_safe_url(subject.get("_stonegateSourceUrl")),
    )


def _comparable_input(
    comp: MarketAnalysisCompRead,
    *,
    selection_status: Literal["selected", "rejected"],
    index: int,
) -> CompAnalystComparableInput:
    key = _comp_key(comp, index)
    condition: Literal["renovated", "as_is", "unknown"] = "unknown"
    if comp.condition_classification == "renovated":
        condition = "renovated"
    elif comp.condition_classification == "as_is":
        condition = "as_is"
    return CompAnalystComparableInput(
        evidence_id=_evidence_id("comp_record", key),
        comp_key=key,
        formatted_address=comp.formatted_address,
        selection_status=selection_status,
        selection_reason=comp.selection_reason or "No engine selection reason was recorded.",
        property_type=comp.property_type,
        sale_date=comp.sale_date,
        sale_price_cents=comp.price_cents,
        bedrooms=comp.bedrooms,
        bathrooms=comp.bathrooms,
        square_footage=comp.square_footage,
        lot_size=comp.lot_size,
        year_built=comp.year_built,
        distance_miles=comp.distance_miles,
        subdivision=comp.subdivision,
        subdivision_match=comp.subdivision_match,
        garage=comp.garage,
        pool=comp.pool,
        basement=comp.basement,
        condition_classification=condition,
        condition_evidence=comp.condition_evidence,
        comp_grade=comp.comp_grade,
        search_level=comp.search_level,
        score=max(0, min(100, comp.score)),
        search_warnings=[warning[:500] for warning in comp.search_warnings[:12]],
        evidence_source=comp.evidence_source,
        source_url=_safe_url(comp.source_url),
        transaction_type=comp.transaction_type,
        transaction_eligibility=(
            cast(
                Literal["not_flagged", "unverified", "ineligible"],
                comp.transaction_eligibility,
            )
            if comp.transaction_eligibility in {"not_flagged", "unverified", "ineligible"}
            else None
        ),
        transaction_review_reason=comp.transaction_review_reason,
    )


def _provider_evidence(
    comparable_inputs: Sequence[CompAnalystComparableInput],
    comps: Sequence[MarketAnalysisCompRead],
) -> list[CompAnalystEvidenceInput]:
    evidence: list[CompAnalystEvidenceInput] = []
    for comparable, comp in zip(comparable_inputs, comps, strict=True):
        verification_notes = _text(comp.verification_notes)
        if verification_notes:
            evidence.append(
                CompAnalystEvidenceInput(
                    evidence_id=_evidence_id(
                        "comp_context",
                        f"{comparable.comp_key}:{verification_notes}",
                    ),
                    evidence_type=(
                        "public_record"
                        if comp.evidence_source == "ai_web_research"
                        else "human_note"
                        if comp.search_level == "manual"
                        else "condition_review"
                    ),
                    related_comp_keys=[comparable.comp_key],
                    field="verification_notes",
                    value=verification_notes[:2000],
                    source_title=_text(comp.source_reference),
                    source_url=_safe_url(comp.source_url),
                )
            )
        observations = _object_sequence(comp, "source_observations")
        if not observations:
            observations = _object_sequence(comp, "evidence_provenance")
        for index, observation in enumerate(observations[:8]):
            record = _record_mapping(observation)
            evidence.append(
                CompAnalystEvidenceInput(
                    evidence_id=_evidence_id(
                        "source_observation",
                        f"{comparable.comp_key}:{index}:{_bounded_evidence_json(record)}",
                    ),
                    evidence_type="closed_sale_record",
                    related_comp_keys=[comparable.comp_key],
                    field=_text(record.get("field")) or "source_observation",
                    value=_bounded_evidence_json(record),
                    source_title=(
                        _text(record.get("provider"))
                        or _text(record.get("source"))
                        or _text(record.get("source_title"))
                    ),
                    source_url=_safe_url(record.get("source_url") or record.get("url")),
                )
            )

        conflicts = _object_sequence(comp, "source_conflicts")
        if not conflicts:
            conflicts = _object_sequence(comp, "field_conflicts")
        for index, conflict in enumerate(conflicts[:8]):
            record = _record_mapping(conflict)
            field = _text(record.get("field")) or "provider_field_conflict"
            evidence.append(
                CompAnalystEvidenceInput(
                    evidence_id=_evidence_id(
                        "provider_conflict",
                        f"{comparable.comp_key}:{field}:{index}",
                    ),
                    evidence_type="provider_conflict",
                    related_comp_keys=[comparable.comp_key],
                    field=field,
                    value=_bounded_evidence_json(record),
                    source_title="Cross-provider field conflict",
                    source_url=_safe_url(record.get("source_url") or record.get("url")),
                )
            )
    return evidence


def _insufficient_draft() -> CompAnalystDraft:
    return CompAnalystDraft(
        status="insufficient",
        summary="No comparable records were supplied for draft AI review.",
        analysis_role="draft_comp_review_support",
        human_review_required=True,
        valuation_use="excluded_from_arv_and_offer_math",
        comp_recommendations=[],
        duplicate_candidates=[],
        conflicts=[],
        micro_market_concerns=[],
        missing_questions=[],
        range_explanations=[],
        limitations=["Comparable evidence is required before the analyst can assist."],
    )


def _result_from_draft(
    draft: CompAnalystDraft,
    *,
    model: str | None,
    usage: CompAnalystUsage | None,
    latency_ms: int,
) -> CompAnalystRunResult:
    return CompAnalystRunResult(
        version=COMP_ANALYST_VERSION,
        status=draft.status,
        mode="draft",
        valuation_use="excluded_from_arv_and_offer_math",
        human_review_required=True,
        summary=draft.summary,
        comp_recommendations=draft.comp_recommendations,
        duplicate_candidates=draft.duplicate_candidates,
        conflicts=draft.conflicts,
        micro_market_concerns=draft.micro_market_concerns,
        missing_questions=draft.missing_questions,
        range_explanations=draft.range_explanations,
        limitations=draft.limitations,
        model=model,
        usage=usage,
        latency_ms=latency_ms,
        error=None,
    )


def _empty_result(
    *,
    status: Literal["unavailable", "rejected"],
    summary: str,
    error: str,
    model: str | None,
    latency_ms: int,
    usage: CompAnalystUsage | None = None,
) -> CompAnalystRunResult:
    return CompAnalystRunResult(
        version=COMP_ANALYST_VERSION,
        status=status,
        mode="draft",
        valuation_use="excluded_from_arv_and_offer_math",
        human_review_required=True,
        summary=summary,
        comp_recommendations=[],
        duplicate_candidates=[],
        conflicts=[],
        micro_market_concerns=[],
        missing_questions=[],
        range_explanations=[],
        limitations=[],
        model=_text(model),
        usage=usage,
        latency_ms=latency_ms,
        error=error,
    )


def _validate_citations(
    citations: Sequence[CompAnalystCitation],
    evidence_urls: Mapping[str, str | None],
) -> None:
    seen: set[str] = set()
    for citation in citations:
        if citation.evidence_id in seen:
            raise CompAnalystPolicyError("Duplicate evidence citations were rejected.")
        seen.add(citation.evidence_id)
        if citation.evidence_id not in evidence_urls:
            raise CompAnalystPolicyError(
                "The draft cited evidence that was not supplied to the analyst."
            )
        if citation.source_url != evidence_urls[citation.evidence_id]:
            raise CompAnalystPolicyError(
                "The draft changed or invented a source URL for cited evidence."
            )


def _require_comp_record_citations(
    citations: Sequence[CompAnalystCitation],
    comp_keys: Sequence[str],
    comp_evidence_ids: Mapping[str, str],
) -> None:
    cited = {citation.evidence_id for citation in citations}
    required = {comp_evidence_ids[key] for key in comp_keys}
    if not required.issubset(cited):
        raise CompAnalystPolicyError(
            "The draft made a comparable claim without citing each affected comp record."
        )


def _require_market_context_citation(
    citations: Sequence[CompAnalystCitation],
    comp_keys: Sequence[str],
    supplied_evidence: Mapping[str, CompAnalystEvidenceInput],
    *,
    claims: Sequence[str] = (),
) -> None:
    keys = set(comp_keys)
    supported_types = {"market_context", "public_record", "human_note"}
    relevant = [
        evidence
        for citation in citations
        if (evidence := supplied_evidence.get(citation.evidence_id)) is not None
        and evidence.evidence_type in supported_types
        and (not keys or bool(keys.intersection(evidence.related_comp_keys)))
    ]
    concepts = {concept for claim in claims for concept in _micro_market_concepts(claim)}
    if relevant and (
        not concepts
        or any(
            concepts.intersection(
                _micro_market_concepts(
                    " ".join(
                        value
                        for value in (
                            evidence.field,
                            evidence.value,
                            evidence.source_title or "",
                        )
                        if value
                    )
                )
            )
            for evidence in relevant
        )
    ):
        return
    raise CompAnalystPolicyError(
        "A micro-market claim lacked supplied market-context, public-record, or human-note "
        "evidence."
    )


def _require_matching_conflict_citation(
    citations: Sequence[CompAnalystCitation],
    comp_keys: Sequence[str],
    supplied_evidence: Mapping[str, CompAnalystEvidenceInput],
) -> None:
    keys = set(comp_keys)
    if any(
        (evidence := supplied_evidence.get(citation.evidence_id)) is not None
        and evidence.evidence_type == "provider_conflict"
        and bool(keys.intersection(evidence.related_comp_keys))
        for citation in citations
    ):
        return
    raise CompAnalystPolicyError(
        "A source-conflict claim lacked matching supplied conflict evidence."
    )


def _require_condition_support(
    recommendation: CompAnalystCompRecommendation,
    *,
    comparable: CompAnalystComparableInput,
    supplied_evidence: Mapping[str, CompAnalystEvidenceInput],
) -> None:
    if comparable.condition_classification == recommendation.condition_hypothesis:
        return
    supported_types = {"condition_review", "listing_history", "public_record", "human_note"}
    cited_ids = {citation.evidence_id for citation in recommendation.citations}
    relevant = [
        evidence
        for evidence_id, evidence in supplied_evidence.items()
        if evidence_id in cited_ids
        and evidence.evidence_type in supported_types
        and recommendation.comp_key in evidence.related_comp_keys
    ]
    keyword_sets = {
        "renovated": (
            "renovat",
            "remodel",
            "updated",
            "new kitchen",
            "new bath",
            "rehab",
        ),
        "as_is": ("as-is", "as is", "dated", "deferred", "repair", "fixer", "original"),
        "mixed": ("mixed", "partial", "some updates", "dated", "renovat", "remodel"),
    }
    keywords = keyword_sets.get(recommendation.condition_hypothesis, ())
    if any(
        any(keyword in evidence.value.casefold() for keyword in keywords) for evidence in relevant
    ):
        return
    raise CompAnalystPolicyError(
        "A non-unknown condition hypothesis lacked supporting supplied condition evidence."
    )


def _contains_micro_market_claim(value: str) -> bool:
    return bool(_micro_market_concepts(value))


def _micro_market_concepts(value: str) -> set[str]:
    normalized = value.casefold()
    concepts: set[str] = set()
    if "school" in normalized:
        concepts.add("school")
    if re.search(r"\bi[- ]?\d{1,3}\b", normalized) or any(
        term in normalized
        for term in (
            "highway",
            "interstate",
            "freeway",
            "across the road",
            "different side",
            "other side",
            "traffic",
            "busy road",
        )
    ):
        concepts.add("roadway")
    if "boundary" in normalized or "neighborhood" in normalized:
        concepts.add("boundary")
    if "flood" in normalized:
        concepts.add("flood")
    if "railroad" in normalized:
        concepts.add("railroad")
    if "airport" in normalized:
        concepts.add("airport")
    if "commercial corridor" in normalized:
        concepts.add("commercial")
    return concepts


def _contains_conflict_claim(value: str) -> bool:
    normalized = value.casefold()
    direct_match = any(
        term in normalized
        for term in (
            "providers disagree",
            "provider disagreement",
            "source conflict",
            "sources conflict",
            "conflicting provider",
            "different sale date",
            "different sale price",
            "different closing",
        )
    )
    source_terms = r"(?:provider|source|record|rentcast|dealmachine)"
    conflict_terms = r"(?:disagree|disagreement|inconsisten|conflict|discrepanc|mismatch|differ)"
    contextual_match = re.search(
        rf"(?:{source_terms}.{{0,80}}{conflict_terms}|"
        rf"{conflict_terms}.{{0,80}}{source_terms})",
        normalized,
    )
    return direct_match or contextual_match is not None


def _validate_contextual_claims(
    narratives: Sequence[str],
    *,
    citations: Sequence[CompAnalystCitation],
    comp_keys: Sequence[str],
    supplied_evidence: Mapping[str, CompAnalystEvidenceInput],
) -> None:
    if any(_contains_micro_market_claim(value) for value in narratives):
        _require_market_context_citation(
            citations,
            comp_keys,
            supplied_evidence,
            claims=narratives,
        )
    if any(_contains_conflict_claim(value) for value in narratives):
        _require_matching_conflict_citation(citations, comp_keys, supplied_evidence)


def _unique_comp_keys(values: Sequence[str], known: set[str]) -> list[str]:
    if len(set(values)) != len(values):
        raise CompAnalystPolicyError("Duplicate comparable references were rejected.")
    _validate_comp_keys(values, known)
    return list(values)


def _validate_comp_keys(values: Sequence[str], known: set[str]) -> None:
    if not set(values).issubset(known):
        raise CompAnalystPolicyError(
            "The draft referenced a comparable that was not supplied to the analyst."
        )


def _draft_narratives(draft: CompAnalystDraft) -> list[str]:
    narratives = [draft.summary, *draft.limitations]
    for recommendation_item in draft.comp_recommendations:
        narratives.extend(
            [
                recommendation_item.reason,
                recommendation_item.condition_reason,
                *recommendation_item.micro_market_concerns,
            ]
        )
    narratives.extend(item.reason for item in draft.duplicate_candidates)
    narratives.extend(item.description for item in draft.conflicts)
    for concern_item in draft.micro_market_concerns:
        narratives.extend([concern_item.concern, concern_item.why_it_matters])
    for question_item in draft.missing_questions:
        narratives.extend([question_item.question, question_item.why_it_matters])
    for explanation_item in draft.range_explanations:
        narratives.extend(
            value
            for value in (
                explanation_item.driver,
                explanation_item.explanation,
                explanation_item.resolution_question,
            )
            if value is not None
        )
    return narratives


def _comp_key(comp: MarketAnalysisCompRead, index: int) -> str:
    return comp.provider_id or comp.formatted_address or f"comp-{index + 1}"


def _evidence_id(prefix: str, identity: str) -> str:
    compact = re.sub(r"[^A-Za-z0-9:._-]+", "-", identity).strip("-:._")
    candidate = f"{prefix}:{compact}" if compact else prefix
    if len(candidate) <= 160:
        return candidate
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}:{digest}"


def _field_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _formatted_address(subject: Mapping[str, Any]) -> str | None:
    pieces = [
        _text(subject.get("addressLine1")) or _text(subject.get("streetAddress")),
        _text(subject.get("city")),
        _text(subject.get("state")),
        _text(subject.get("zipCode")) or _text(subject.get("postalCode")),
    ]
    return ", ".join(piece for piece in pieces if piece) or None


def _basement(features: Mapping[str, Any]) -> bool | None:
    explicit = _boolean(features.get("basement"))
    if explicit is not None:
        return explicit
    foundation = _text(features.get("foundationType"))
    return "basement" in foundation.lower() if foundation else None


def _safe_url(value: object) -> str | None:
    candidate = _text(value)
    if candidate is None:
        return None
    try:
        return CompAnalystCitation(
            evidence_id="url_validation",
            source_url=candidate,
        ).source_url
    except ValidationError:
        return None


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _record_mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json")
        return dumped if isinstance(dumped, Mapping) else {}
    return {}


def _object_sequence(value: object, field: str) -> list[object]:
    candidate = getattr(value, field, None)
    if not isinstance(candidate, list):
        return []
    return candidate


def _bounded_evidence_json(value: Mapping[str, Any]) -> str:
    redacted = _redact_evidence(value)
    serialized = json.dumps(redacted, sort_keys=True, default=str, separators=(",", ":"))
    return serialized if len(serialized) <= 2000 else f"{serialized[:1997]}..."


def _redact_evidence(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _redact_evidence(item)
            for key, item in value.items()
            if not any(
                token in str(key).lower()
                for token in ("owner", "occupant", "tenant", "phone", "email", "contact")
            )
        }
    if isinstance(value, list):
        return [_redact_evidence(item) for item in value[:20]]
    return value


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _nonnegative_integer(value: object) -> int | None:
    parsed = _integer(value)
    return parsed if parsed is not None and parsed >= 0 else None


def _usage(raw_usage: Mapping[str, object]) -> CompAnalystUsage:
    return CompAnalystUsage(
        input_tokens=_nonnegative_integer(raw_usage.get("input_tokens")),
        output_tokens=_nonnegative_integer(raw_usage.get("output_tokens")),
        total_tokens=_nonnegative_integer(raw_usage.get("total_tokens")),
    )


def _boolean(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _safe_provider_error(exc: OpenAIClientError) -> str:
    message = _text(str(exc)) or "OpenAI request failed."
    return message[:500]
