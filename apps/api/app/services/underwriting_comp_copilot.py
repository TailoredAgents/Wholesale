from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings
from app.integrations.openai_client import OpenAIClientError, OpenAIResponsesClient
from app.models.foundation import (
    AuditEvent,
    FieldInspection,
    FieldInspectionPhoto,
    Lead,
    UnderwritingCompCopilotMessage,
    UnderwritingCompCopilotThread,
    UnderwritingMarketAnalysis,
    User,
)
from app.schemas.underwriting_comp_copilot import (
    CompCopilotAnswerRead,
    CompCopilotCitationRead,
    CompCopilotDraft,
    CompCopilotMessageRead,
    CompCopilotSuggestedActionRead,
    CompCopilotThreadRead,
)

MAX_CONTEXT_CHARACTERS = 42_000
MAX_HISTORY_MESSAGES = 8
MAX_SAVED_MESSAGES = 100
PROMPT_CACHE_KEY = "stonegate:underwriting-comp-copilot:v1"
PROHIBITED_AUTHORITY_PATTERN = re.compile(
    r"\b(?:i\s+recommend|you\s+should\s+offer|offer\s+them|set\s+(?:the\s+)?arv|"
    r"change\s+(?:the\s+)?arv|approve\s+(?:the\s+)?offer|maximum\s+offer\s+is)\b",
    re.IGNORECASE,
)
MONEY_PATTERN = re.compile(r"\$\s*\d|\b\d[\d,]*(?:\.\d+)?\s*(?:dollars?|k)\b", re.IGNORECASE)

SYSTEM_PROMPT = """You are Stonegate's Comp Copilot, a draft-only residential comparable-sale
research assistant. Answer only from the supplied immutable analysis evidence and recent thread.
Explain why sales were selected or rejected, confidence, search expansion, adjustment support,
condition uncertainty, micro-market concerns, conflicts, and the safest next review action.

Rules:
- Cite every material factual claim with one or more supplied evidence IDs.
- Never invent a comp, source, property fact, condition, adjustment, or market boundary.
- Do not quote, calculate, suggest, approve, or change any dollar amount, ARV, range, MAO, seller
  ceiling, offer, comp weight, or adjustment. Direct the operator to the saved valuation cards.
- Never say a condition is confirmed. You may identify missing condition evidence and recommend a
  human inspection or listing-photo review.
- Suggested actions are drafts. Only use the allowed action types and supplied comp keys.
- State uncertainty plainly. The deterministic Stonegate V3 engine remains the only valuation
  authority, and every consequential comp or condition change requires human review.
- Keep the answer concise and operational. Return only the strict JSON object requested.
"""

COMP_COPILOT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "string", "minLength": 1, "maxLength": 4000},
        "citations": {
            "type": "array",
            "minItems": 1,
            "maxItems": 12,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"evidence_id": {"type": "string", "minLength": 1}},
                "required": ["evidence_id"],
            },
        },
        "suggested_actions": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "action_type": {
                        "type": "string",
                        "enum": [
                            "open_comp_review",
                            "review_comp",
                            "inspect_condition",
                            "verify_micro_market",
                            "refresh_evidence",
                        ],
                    },
                    "label": {"type": "string", "minLength": 1, "maxLength": 160},
                    "rationale": {"type": "string", "minLength": 1, "maxLength": 500},
                    "comp_key": {"type": ["string", "null"], "maxLength": 500},
                },
                "required": ["action_type", "label", "rationale", "comp_key"],
            },
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "limitations": {
            "type": "array",
            "maxItems": 8,
            "items": {"type": "string", "maxLength": 500},
        },
        "human_review_required": {"type": "boolean", "const": True},
        "valuation_authority": {"type": "string", "const": "deterministic_v3_only"},
    },
    "required": [
        "answer",
        "citations",
        "suggested_actions",
        "confidence",
        "limitations",
        "human_review_required",
        "valuation_authority",
    ],
}

SUGGESTED_QUESTIONS = [
    "Why were these comps selected?",
    "What is lowering confidence?",
    "Which condition evidence is still missing?",
    "Are there micro-market concerns I should verify?",
    "What should I review before the appointment?",
]


class CompCopilotPolicyError(ValueError):
    pass


def get_comp_copilot_thread(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    analysis_id: UUID,
    settings: Settings,
) -> CompCopilotThreadRead | None:
    analysis = _scoped_analysis(db, principal, lead_id, analysis_id)
    if analysis is None:
        return None
    thread = db.scalar(
        select(UnderwritingCompCopilotThread).where(
            UnderwritingCompCopilotThread.organization_id == principal.organization_id,
            UnderwritingCompCopilotThread.market_analysis_id == analysis.id,
        )
    )
    return _thread_read(db, analysis, thread, settings)


def ask_comp_copilot(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    analysis_id: UUID,
    settings: Settings,
    *,
    question: str,
) -> CompCopilotAnswerRead | None:
    analysis = _scoped_analysis(db, principal, lead_id, analysis_id)
    if analysis is None:
        return None

    lead = db.scalar(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.organization_id == principal.organization_id,
        )
    )
    if lead is None:
        return None
    if lead.asset_class not in {None, "house"}:
        raise ValueError("The Comp Copilot currently supports the residential house workflow.")

    thread = db.scalar(
        select(UnderwritingCompCopilotThread)
        .where(
            UnderwritingCompCopilotThread.organization_id == principal.organization_id,
            UnderwritingCompCopilotThread.market_analysis_id == analysis.id,
        )
        .with_for_update()
    )
    if thread is None:
        thread = UnderwritingCompCopilotThread(
            organization_id=principal.organization_id,
            lead_id=lead_id,
            market_analysis_id=analysis.id,
            created_by_user_id=principal.user_id,
            status="active",
        )
        db.add(thread)
        db.flush()

    saved_count = db.scalar(
        select(func.count(UnderwritingCompCopilotMessage.id)).where(
            UnderwritingCompCopilotMessage.thread_id == thread.id
        )
    )
    if (saved_count or 0) >= MAX_SAVED_MESSAGES:
        raise ValueError(
            "This saved analysis has reached its Copilot message limit. Run or open a newer "
            "valuation analysis to continue."
        )

    now = datetime.now(UTC)
    user_message = UnderwritingCompCopilotMessage(
        organization_id=principal.organization_id,
        thread_id=thread.id,
        author_user_id=principal.user_id,
        role="user",
        content=" ".join(question.split()),
        citations=[],
        suggested_actions=[],
        confidence=None,
        limitations=[],
        used_ai=False,
        model=None,
        input_tokens=None,
        output_tokens=None,
    )
    db.add(user_message)
    db.flush()

    evidence, evidence_lookup = _build_evidence(db, analysis)
    history = _recent_history(db, thread.id, exclude_message_id=user_message.id)
    draft, used_ai, model, usage = _answer(
        settings,
        principal=principal,
        analysis=analysis,
        question=user_message.content,
        history=history,
        evidence=evidence,
        evidence_lookup=evidence_lookup,
    )
    citations = _resolve_citations(draft, evidence_lookup)
    actions = _validated_actions(draft, evidence_lookup)
    assistant_message = UnderwritingCompCopilotMessage(
        organization_id=principal.organization_id,
        thread_id=thread.id,
        author_user_id=None,
        role="assistant",
        content=draft.answer,
        citations=[item.model_dump(mode="json") for item in citations],
        suggested_actions=[item.model_dump(mode="json") for item in actions],
        confidence=draft.confidence,
        limitations=draft.limitations,
        used_ai=used_ai,
        model=model,
        input_tokens=_optional_int(usage.get("input_tokens")),
        output_tokens=_optional_int(usage.get("output_tokens")),
    )
    db.add(assistant_message)
    thread.last_message_at = now
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="underwriting.comp_copilot.ask",
            entity_type="underwriting_market_analysis",
            entity_id=analysis.id,
            previous_value=None,
            new_value={
                "thread_id": str(thread.id),
                "question_message_id": str(user_message.id),
                "answer_message_id": str(assistant_message.id),
                "used_ai": used_ai,
                "citation_count": len(citations),
                "suggested_action_count": len(actions),
            },
            reason="Evidence-grounded draft valuation explanation requested by an operator.",
        )
    )
    db.commit()
    db.refresh(assistant_message)
    return CompCopilotAnswerRead(
        thread=_thread_read(db, analysis, thread, settings),
        answer=_message_read(assistant_message, author_name=None),
    )


def _scoped_analysis(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    analysis_id: UUID,
) -> UnderwritingMarketAnalysis | None:
    return db.scalar(
        select(UnderwritingMarketAnalysis).where(
            UnderwritingMarketAnalysis.id == analysis_id,
            UnderwritingMarketAnalysis.lead_id == lead_id,
            UnderwritingMarketAnalysis.organization_id == principal.organization_id,
            UnderwritingMarketAnalysis.valuation_profile == "house_v3",
        )
    )


def _thread_read(
    db: Session,
    analysis: UnderwritingMarketAnalysis,
    thread: UnderwritingCompCopilotThread | None,
    settings: Settings,
) -> CompCopilotThreadRead:
    if thread is None:
        messages: list[CompCopilotMessageRead] = []
    else:
        records = list(
            db.scalars(
                select(UnderwritingCompCopilotMessage)
                .where(
                    UnderwritingCompCopilotMessage.organization_id == analysis.organization_id,
                    UnderwritingCompCopilotMessage.thread_id == thread.id,
                )
                .order_by(
                    UnderwritingCompCopilotMessage.created_at.asc(),
                    UnderwritingCompCopilotMessage.id.asc(),
                )
            ).all()
        )
        user_ids = {item.author_user_id for item in records if item.author_user_id is not None}
        names = (
            {
                user.id: user.display_name
                for user in db.scalars(select(User).where(User.id.in_(user_ids))).all()
            }
            if user_ids
            else {}
        )
        messages = [
            _message_read(
                item,
                author_name=(names.get(item.author_user_id) if item.author_user_id else None),
            )
            for item in records
        ]
    return CompCopilotThreadRead(
        thread_id=thread.id if thread else None,
        analysis_id=analysis.id,
        analysis_created_at=analysis.created_at,
        messages=messages,
        suggested_questions=SUGGESTED_QUESTIONS,
        ai_available=_ai_available(settings),
    )


def _message_read(
    message: UnderwritingCompCopilotMessage,
    *,
    author_name: str | None,
) -> CompCopilotMessageRead:
    return CompCopilotMessageRead.model_validate(
        {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "author_user_id": message.author_user_id,
            "author_name": author_name,
            "citations": message.citations,
            "suggested_actions": message.suggested_actions,
            "confidence": message.confidence,
            "limitations": message.limitations,
            "used_ai": message.used_ai,
            "model": message.model,
            "created_at": message.created_at,
        }
    )


def _ai_available(settings: Settings) -> bool:
    return bool(
        settings.underwriting_ai_comp_analyst_mode == "draft"
        and settings.ai_enabled
        and settings.openai_api_key
    )


def _recent_history(
    db: Session,
    thread_id: UUID,
    *,
    exclude_message_id: UUID,
) -> list[dict[str, str]]:
    records = list(
        db.scalars(
            select(UnderwritingCompCopilotMessage)
            .where(
                UnderwritingCompCopilotMessage.thread_id == thread_id,
                UnderwritingCompCopilotMessage.id != exclude_message_id,
            )
            .order_by(UnderwritingCompCopilotMessage.created_at.desc())
            .limit(MAX_HISTORY_MESSAGES)
        ).all()
    )
    records.reverse()
    return [{"role": item.role, "content": item.content[:2000]} for item in records]


def _answer(
    settings: Settings,
    *,
    principal: Principal,
    analysis: UnderwritingMarketAnalysis,
    question: str,
    history: list[dict[str, str]],
    evidence: list[dict[str, Any]],
    evidence_lookup: dict[str, dict[str, Any]],
) -> tuple[CompCopilotDraft, bool, str | None, dict[str, Any]]:
    if not _ai_available(settings):
        return _fallback_draft(question, analysis, evidence_lookup), False, None, {}

    user_prompt = json.dumps(
        {
            "task": question,
            "recent_thread": history,
            "immutable_analysis_evidence": evidence,
            "allowed_comp_keys": sorted(_allowed_comp_keys(evidence_lookup)),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(user_prompt) > MAX_CONTEXT_CHARACTERS:
        return _fallback_draft(question, analysis, evidence_lookup), False, None, {}

    client = OpenAIResponsesClient(
        api_key=settings.openai_api_key or "",
        base_url=settings.openai_base_url,
        timeout_seconds=settings.openai_request_timeout_seconds,
    )
    try:
        parsed, usage = client.create_structured_response(
            model=settings.openai_default_model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            schema_name="stonegate_underwriting_comp_copilot",
            json_schema=COMP_COPILOT_OUTPUT_SCHEMA,
            reasoning_effort=settings.openai_reasoning_effort,
            max_output_tokens=2200,
            safety_identifier=f"comp-copilot-{principal.organization_id}",
            prompt_cache_key=PROMPT_CACHE_KEY,
        )
        draft = CompCopilotDraft.model_validate(parsed)
        _validate_draft(draft, evidence_lookup)
        return draft, True, settings.openai_default_model, usage
    except (OpenAIClientError, ValidationError, CompCopilotPolicyError, ValueError):
        return _fallback_draft(question, analysis, evidence_lookup), False, None, {}


def _validate_draft(
    draft: CompCopilotDraft,
    evidence_lookup: Mapping[str, Mapping[str, Any]],
) -> None:
    authority_text = " ".join(
        [
            draft.answer,
            *draft.limitations,
            *(action.label for action in draft.suggested_actions),
            *(action.rationale for action in draft.suggested_actions),
        ]
    )
    if PROHIBITED_AUTHORITY_PATTERN.search(authority_text) or MONEY_PATTERN.search(authority_text):
        raise CompCopilotPolicyError(
            "The Comp Copilot draft crossed its pricing authority boundary."
        )
    known_ids = set(evidence_lookup)
    if any(citation.evidence_id not in known_ids for citation in draft.citations):
        raise CompCopilotPolicyError("The Comp Copilot cited evidence that was not supplied.")
    allowed_keys = _allowed_comp_keys(evidence_lookup)
    for action in draft.suggested_actions:
        if action.comp_key is not None and action.comp_key not in allowed_keys:
            raise CompCopilotPolicyError("The Comp Copilot proposed an unknown comparable.")
        if action.action_type in {"review_comp", "inspect_condition"} and not action.comp_key:
            raise CompCopilotPolicyError("The Comp Copilot omitted the comparable for its action.")


def _resolve_citations(
    draft: CompCopilotDraft,
    evidence_lookup: Mapping[str, Mapping[str, Any]],
) -> list[CompCopilotCitationRead]:
    resolved: list[CompCopilotCitationRead] = []
    seen: set[str] = set()
    for citation in draft.citations:
        if citation.evidence_id in seen:
            continue
        item = evidence_lookup.get(citation.evidence_id)
        if item is None:
            continue
        seen.add(citation.evidence_id)
        resolved.append(
            CompCopilotCitationRead.model_validate(
                {
                    "evidence_id": citation.evidence_id,
                    "label": str(item.get("label") or citation.evidence_id),
                    "kind": str(item.get("kind") or "analysis"),
                    "comp_key": _text(item.get("comp_key")),
                    "source_url": _safe_url(item.get("source_url")),
                }
            )
        )
    return resolved


def _validated_actions(
    draft: CompCopilotDraft,
    evidence_lookup: Mapping[str, Mapping[str, Any]],
) -> list[CompCopilotSuggestedActionRead]:
    allowed_keys = _allowed_comp_keys(evidence_lookup)
    return [
        CompCopilotSuggestedActionRead.model_validate(action.model_dump())
        for action in draft.suggested_actions
        if action.comp_key is None or action.comp_key in allowed_keys
    ]


def _build_evidence(
    db: Session,
    analysis: UnderwritingMarketAnalysis,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    metadata = analysis.analysis_metadata or {}
    subject = analysis.subject_property or {}
    evidence: list[dict[str, Any]] = [
        {
            "evidence_id": "analysis:summary",
            "kind": "analysis",
            "label": "Saved valuation analysis",
            "facts": {
                "requested_address": analysis.requested_address,
                "created_at": analysis.created_at.isoformat(),
                "methodology_version": metadata.get("methodology_version"),
                "confidence_score": analysis.confidence_score,
                "confidence_tier": metadata.get("confidence_tier"),
                "selected_comp_count": analysis.selected_comp_count,
                "rejected_comp_count": analysis.rejected_comp_count,
                "manual_review_required": metadata.get("human_review_required", True),
                "report_stage": metadata.get("report_stage"),
            },
        },
        {
            "evidence_id": "subject:record",
            "kind": "subject",
            "label": analysis.requested_address,
            "facts": _without_money(subject),
        },
        {
            "evidence_id": "analysis:confidence",
            "kind": "analysis",
            "label": "Confidence factors and review reasons",
            "facts": {
                "confidence_factors": _bounded_value(metadata.get("confidence_factors")),
                "review_reasons": _bounded_value(metadata.get("review_reasons")),
                "search_summary": _bounded_value(metadata.get("comp_search_summary")),
            },
        },
        {
            "evidence_id": "analysis:adjustments",
            "kind": "analysis",
            "label": "Supported and withheld adjustment evidence",
            "facts": _without_money(_mapping(metadata.get("market_adjustment"))),
        },
    ]
    inspections = list(
        db.scalars(
            select(FieldInspection)
            .where(
                FieldInspection.organization_id == analysis.organization_id,
                FieldInspection.lead_id == analysis.lead_id,
            )
            .order_by(FieldInspection.created_at.desc())
            .limit(3)
        ).all()
    )
    inspection_ids = [item.id for item in inspections]
    photos = (
        list(
            db.scalars(
                select(FieldInspectionPhoto)
                .where(
                    FieldInspectionPhoto.organization_id == analysis.organization_id,
                    FieldInspectionPhoto.inspection_id.in_(inspection_ids),
                )
                .order_by(FieldInspectionPhoto.created_at.desc())
                .limit(40)
            ).all()
        )
        if inspection_ids
        else []
    )
    evidence.append(
        {
            "evidence_id": "subject:inspection",
            "kind": "subject",
            "label": "Field inspection and appointment photo evidence",
            "facts": {
                "inspection_count": len(inspections),
                "photo_count": len(photos),
                "inspections": [
                    {
                        "status": item.status,
                        "overall_condition": item.overall_condition,
                        "submitted_at": item.submitted_at.isoformat()
                        if item.submitted_at
                        else None,
                        "room_observations": _without_money(item.room_observations),
                        "repair_items": _without_money(item.repair_items),
                        "inspector_notes": item.inspector_notes,
                    }
                    for item in inspections
                ],
                "photo_index": [
                    {
                        "area": item.area,
                        "caption": item.caption,
                        "captured_at": item.captured_at.isoformat() if item.captured_at else None,
                    }
                    for item in photos
                ],
                "image_content_not_supplied_to_copilot": True,
            },
        }
    )

    for selected, records in ((True, analysis.selected_comps), (False, analysis.rejected_comps)):
        for index, raw in enumerate(records[:30]):
            comp = dict(raw) if isinstance(raw, dict) else {}
            key = _comp_key(comp, index, selected=selected)
            evidence.append(
                {
                    "evidence_id": f"comp:{key}",
                    "kind": "comparable",
                    "label": _text(comp.get("formatted_address")) or f"Comparable {index + 1}",
                    "comp_key": key,
                    "source_url": _safe_url(comp.get("source_url")),
                    "facts": {
                        "selected": selected,
                        **_without_money(comp),
                    },
                }
            )

    secondary = _mapping(metadata.get("secondary_evidence"))
    for index, raw_source in enumerate(_list_of_mappings(secondary.get("sources"))[:12]):
        url = _safe_url(raw_source.get("url") or raw_source.get("source_url"))
        if not url:
            continue
        evidence.append(
            {
                "evidence_id": f"source:{index + 1}",
                "kind": "source",
                "label": _text(raw_source.get("title")) or url,
                "source_url": url,
                "facts": _without_money(raw_source),
            }
        )

    bounded = [_bounded_evidence(item) for item in evidence]
    lookup = {str(item["evidence_id"]): item for item in bounded}
    return bounded, lookup


def _fallback_draft(
    question: str,
    analysis: UnderwritingMarketAnalysis,
    evidence_lookup: Mapping[str, Mapping[str, Any]],
) -> CompCopilotDraft:
    normalized = question.lower()
    selected = _comp_evidence(evidence_lookup, selected=True)
    rejected = _comp_evidence(evidence_lookup, selected=False)
    citations = [{"evidence_id": "analysis:summary"}]
    actions: list[dict[str, Any]] = []
    limitations = [
        "This explanation uses saved deterministic evidence; no valuation inputs were changed."
    ]

    if any(term in normalized for term in ("confidence", "weak", "uncertain")):
        answer = (
            f"This analysis has {analysis.confidence_score}% saved confidence. The confidence "
            "record identifies evidence depth, comp quality, source agreement, condition support, "
            "search expansion, and withheld adjustments as the controlling review areas. Open the "
            "review reasons and resolve the highest-severity missing evidence first."
        )
        citations.append({"evidence_id": "analysis:confidence"})
        actions.append(_open_review_action("Review the confidence blockers"))
    elif any(term in normalized for term in ("reject", "exclude", "left out")) and rejected:
        examples = ", ".join(str(item.get("label")) for item in rejected[:3])
        answer = (
            f"The saved engine excluded {len(rejected)} sale(s). Examples include {examples}. "
            "Each record retains its fit grade, search level, transfer eligibility and selection "
            "reason so a person can challenge the exclusion without losing the original evidence."
        )
        citations.extend({"evidence_id": str(item["evidence_id"])} for item in rejected[:3])
        actions.append(_open_review_action("Review excluded sales"))
    elif any(term in normalized for term in ("condition", "renovat", "photo", "repair")):
        unknown = [
            item
            for item in selected
            if _mapping(item.get("facts")).get("condition_classification") in {None, "unknown"}
        ]
        answer = (
            f"{len(unknown)} selected sale(s) still lack confirmed condition evidence. Stonegate "
            "does not infer renovation quality from price. Compare dated listing evidence or "
            "inspection photos, then confirm renovated, as-is, or unknown in Comparable review."
        )
        citations.extend({"evidence_id": str(item["evidence_id"])} for item in unknown[:3])
        citations.append({"evidence_id": "subject:inspection"})
        for item in unknown[:2]:
            actions.append(
                {
                    "action_type": "inspect_condition",
                    "label": f"Inspect condition: {item.get('label')}",
                    "rationale": "The saved sale does not have human-confirmed condition evidence.",
                    "comp_key": item.get("comp_key"),
                }
            )
    elif any(term in normalized for term in ("market", "neighborhood", "subdivision", "boundary")):
        answer = (
            "The engine measures distance and subdivision agreement, but it does not treat a "
            "radius as a definitive market boundary. Review the comp map for school-district, "
            "flood, road, design, subdivision, or other location differences before confirming "
            "the set."
        )
        citations.extend({"evidence_id": str(item["evidence_id"])} for item in selected[:3])
        actions.append(
            {
                "action_type": "verify_micro_market",
                "label": "Verify the micro-market on the map",
                "rationale": "Distance alone does not prove that two properties compete.",
                "comp_key": None,
            }
        )
    elif any(term in normalized for term in ("range", "spread", "wide")):
        answer = (
            "The saved range comes from the middle distribution of adjusted closed-sale "
            "indications. Its width is affected by comp disagreement, unknown condition, expanded "
            "search evidence, source conflicts, and adjustments that lacked adequate local support."
        )
        citations.extend(
            [{"evidence_id": "analysis:adjustments"}, {"evidence_id": "analysis:confidence"}]
        )
        actions.append(_open_review_action("Review the range drivers"))
    else:
        examples = ", ".join(str(item.get("label")) for item in selected[:3])
        answer = (
            f"Stonegate selected {len(selected)} recorded sale(s) using property fit, distance, "
            f"recency, size, age, subdivision and transfer eligibility. The leading saved evidence "
            f"includes {examples or 'no currently selected sales'}. Review condition and location "
            "before treating the set as appointment-ready."
        )
        citations.extend({"evidence_id": str(item["evidence_id"])} for item in selected[:3])
        actions.append(_open_review_action("Open Comparable review"))

    return CompCopilotDraft.model_validate(
        {
            "answer": answer,
            "citations": citations,
            "suggested_actions": actions,
            "confidence": "medium" if selected else "low",
            "limitations": limitations,
            "human_review_required": True,
            "valuation_authority": "deterministic_v3_only",
        }
    )


def _open_review_action(label: str) -> dict[str, Any]:
    return {
        "action_type": "open_comp_review",
        "label": label,
        "rationale": "A person must confirm consequential comp and condition decisions.",
        "comp_key": None,
    }


def _comp_evidence(
    evidence_lookup: Mapping[str, Mapping[str, Any]],
    *,
    selected: bool,
) -> list[Mapping[str, Any]]:
    return [
        item
        for item in evidence_lookup.values()
        if item.get("kind") == "comparable"
        and _mapping(item.get("facts")).get("selected") is selected
    ]


def _allowed_comp_keys(evidence_lookup: Mapping[str, Mapping[str, Any]]) -> set[str]:
    return {
        str(item["comp_key"])
        for item in evidence_lookup.values()
        if item.get("kind") == "comparable" and item.get("comp_key")
    }


def _comp_key(comp: Mapping[str, Any], index: int, *, selected: bool) -> str:
    return (
        _text(comp.get("provider_id"))
        or _text(comp.get("formatted_address"))
        or f"{'selected' if selected else 'rejected'}-{index + 1}"
    )


def _without_money(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _without_money(item)
            for key, item in value.items()
            if not any(
                marker in str(key).lower()
                for marker in ("price", "cents", "value", "arv", "offer", "mao", "cost")
            )
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_without_money(item) for item in list(value)[:30]]
    if isinstance(value, str):
        return value[:1000]
    return value


def _bounded_evidence(item: Mapping[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(item, default=str, separators=(",", ":"))
    if len(encoded) <= 12_000:
        return dict(item)
    return {
        "evidence_id": item.get("evidence_id"),
        "kind": item.get("kind"),
        "label": item.get("label"),
        "comp_key": item.get("comp_key"),
        "source_url": item.get("source_url"),
        "facts": {"note": "Evidence was truncated to the safe context boundary."},
    }


def _bounded_value(value: Any) -> Any:
    return _without_money(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _safe_url(value: Any) -> str | None:
    url = _text(value)
    if url is None:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url[:1000]


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
