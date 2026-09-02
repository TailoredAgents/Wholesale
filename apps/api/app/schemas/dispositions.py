from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class DispositionCaseCreate(BaseModel):
    transaction_id: UUID
    strategy: Literal["assignment", "double_close", "novation"] = "assignment"
    asking_price_cents: int | None = Field(default=None, ge=1)
    minimum_acceptable_cents: int | None = Field(default=None, ge=1)
    desired_assignment_fee_cents: int | None = Field(default=None, ge=0)
    operating_mode_key: str = Field(default="human_led", max_length=80)
    notes: str | None = Field(default=None, max_length=2000)


class ProofDocumentRead(BaseModel):
    id: UUID
    buyer_id: UUID
    status: str
    institution_name: str | None
    verified_amount_cents: int | None
    expires_at: datetime | None
    file_name: str
    content_type: str
    file_size: int
    storage_provider: str
    malware_scan_status: str
    retention_until: datetime | None
    verified_by_user_id: UUID | None
    verified_at: datetime | None
    verification_source: str | None
    notes: str | None
    content_url: str
    created_at: datetime


class ProofVerificationRequest(BaseModel):
    decision: Literal["verified", "rejected"]
    verification_source: str = Field(min_length=2, max_length=120)
    institution_name: str | None = Field(default=None, max_length=255)
    verified_amount_cents: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None
    notes: str = Field(min_length=2, max_length=1000)

    @field_validator("verification_source", "notes")
    @classmethod
    def require_meaningful_review_evidence(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("Proof review evidence must contain at least 2 characters.")
        return normalized


class MatchRead(BaseModel):
    id: UUID
    buyer_id: UUID
    buyer_name: str
    score_basis_points: int
    score_components: dict[str, int]
    qualification_status: str
    recipient_status: str
    rank: int
    proof_status: str
    proof_expires_at: datetime | None
    latest_proof_document_id: UUID | None


class OfferCreate(BaseModel):
    buyer_id: UUID
    amount_cents: int = Field(ge=1)
    earnest_money_cents: int | None = Field(default=None, ge=0)
    financing_type: str = Field(default="cash", max_length=80)
    proof_document_id: UUID | None = None
    deposit_due_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class OfferRead(BaseModel):
    id: UUID
    buyer_id: UUID
    buyer_name: str
    amount_cents: int
    earnest_money_cents: int | None
    financing_type: str
    status: str
    proof_document_id: UUID | None
    deposit_due_at: datetime | None
    deposit_received_at: datetime | None
    selected_at: datetime | None
    notes: str | None
    received_at: datetime


class EngagementCreate(BaseModel):
    buyer_id: UUID
    engagement_type: Literal["inquiry", "showing", "follow_up", "deposit"]
    status: str = Field(default="logged", max_length=40)
    scheduled_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=1000)


class EngagementRead(BaseModel):
    id: UUID
    buyer_id: UUID
    buyer_name: str
    engagement_type: str
    status: str
    scheduled_at: datetime | None
    occurred_at: datetime
    notes: str | None


class BuyerSelection(BaseModel):
    primary_offer_id: UUID
    backup_offer_id: UUID | None = None
    reason: str = Field(min_length=3, max_length=1000)


class PayoutRead(BaseModel):
    id: UUID
    role_key: str
    user_id: UUID | None
    user_name: str | None
    credit_basis_points: int
    amount_cents: int
    status: str


class ReconciliationRead(BaseModel):
    id: UUID
    status: str
    gross_revenue_cents: int
    acquisition_reserve_cents: int
    deal_deductions_cents: int
    adjusted_deal_margin_cents: int
    total_compensation_cents: int
    company_profit_cents: int
    company_margin_basis_points: int
    target_margin_basis_points: int
    notes: str | None
    payouts: list[PayoutRead]
    created_at: datetime


class ReconciliationDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    notes: str = Field(min_length=3, max_length=2000)
    approve_below_target: bool = False


class DispositionCaseRead(BaseModel):
    id: UUID
    deal_id: UUID
    transaction_id: UUID
    lead_id: UUID
    asset_class: Literal["house", "land"]
    seller_name: str
    property_address: str
    property_type: str | None
    status: str
    strategy: str
    asking_price_cents: int
    minimum_acceptable_cents: int | None
    desired_assignment_fee_cents: int | None
    package_status: str
    package_snapshot: dict[str, object]
    compensation_plan_label: str
    operating_mode_label: str
    selected_buyer_id: UUID | None
    backup_buyer_id: UUID | None
    matches: list[MatchRead]
    offers: list[OfferRead]
    engagements: list[EngagementRead]
    reconciliation: ReconciliationRead | None
    created_at: datetime


DispositionEvidenceClassification = Literal[
    "verified_fact",
    "seller_statement",
    "provider_signal",
    "stonegate_analysis",
    "unknown",
]


class DispositionEvidenceItemRead(BaseModel):
    key: str
    label: str
    classification: DispositionEvidenceClassification
    value: Any = None
    provenance: dict[str, Any]
    captured_at: datetime | None = None
    expires_at: datetime | None = None
    freshness: Literal["current", "stale", "unknown"] = "unknown"


class DispositionPackageRemediationRead(BaseModel):
    label: str
    href: str


class DispositionPackageReadinessCheckRead(BaseModel):
    key: str
    label: str
    status: Literal["ready", "warning", "blocked"]
    detail: str
    source_label: str
    captured_at: datetime | None = None
    remediation: DispositionPackageRemediationRead | None = None


class DispositionPackageReadinessRead(BaseModel):
    status: Literal["ready", "warnings", "blocked", "stale"]
    blockers: list[str]
    warnings: list[str]
    unknowns: list[str]
    checks: list[DispositionPackageReadinessCheckRead]
    ready_count: int
    warning_count: int
    blocked_count: int
    unknown_count: int


class DispositionPackageVersionCreate(BaseModel):
    expected_latest_version: int = Field(ge=0)
    asking_price_cents: int | None = Field(default=None, ge=1)
    minimum_acceptable_cents: int | None = Field(default=None, ge=1)
    desired_assignment_fee_cents: int | None = Field(default=None, ge=0)


class DispositionPackageApprovalRequest(BaseModel):
    expected_version: int = Field(ge=1)
    attestation: bool
    reason: str = Field(min_length=3, max_length=2000)

    @field_validator("attestation")
    @classmethod
    def require_human_attestation(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Package approval requires an affirmative human attestation.")
        return value

    @field_validator("reason")
    @classmethod
    def normalize_approval_reason(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 3:
            raise ValueError("Approval reason must contain at least 3 characters.")
        return normalized


class DispositionPackageArtifactMetadataRead(BaseModel):
    source: Literal["external_upload"]
    original_file_name: str
    content_type: Literal["application/pdf"]
    size_bytes: int = Field(ge=1)
    sha256: str = Field(min_length=64, max_length=64)
    uploaded_at: datetime
    uploaded_by_user_id: UUID
    malware_scan_status: str
    source_note: str | None = None


class DispositionPackageVersionRead(BaseModel):
    id: UUID
    disposition_case_id: UUID
    version_number: int
    lock_version: int
    status: Literal["draft", "approved", "superseded", "rejected"]
    policy_version: str
    renderer_version: str
    public_snapshot: dict[str, Any]
    private_economics_snapshot: dict[str, Any] | None
    evidence_manifest: list[DispositionEvidenceItemRead]
    readiness: DispositionPackageReadinessRead
    source_fingerprint: str
    email_summary: str
    sms_summary: str
    pdf_file_name: str | None
    pdf_size: int | None
    pdf_sha256: str | None
    artifact_source: Literal["stonegate_generated", "external_upload"]
    artifact_metadata: DispositionPackageArtifactMetadataRead | None
    created_by_user_id: UUID
    approved_by_user_id: UUID | None
    approval_reason: str | None
    approved_at: datetime | None
    created_at: datetime
    is_current: bool


class DispositionPackageWorkspaceRead(BaseModel):
    case_id: UUID
    can_view_internal_economics: bool
    can_approve: bool
    current_source_fingerprint: str
    current_readiness: DispositionPackageReadinessRead
    public_preview: dict[str, Any]
    private_economics: dict[str, Any] | None
    evidence_manifest: list[DispositionEvidenceItemRead]
    email_summary: str
    sms_summary: str
    latest_version: DispositionPackageVersionRead | None
    approved_version: DispositionPackageVersionRead | None
    approved_package_is_current: bool
    versions: list[DispositionPackageVersionRead]


class DispositionPackageShareLinkCreate(BaseModel):
    expires_in_hours: int = Field(default=72, ge=1, le=168)


class DispositionPackageShareLinkRevoke(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 3:
            raise ValueError("Revocation reason must contain at least 3 characters.")
        return normalized


class DispositionPackageShareLinkRead(BaseModel):
    id: UUID
    disposition_case_id: UUID
    package_version_id: UUID
    package_version_number: int
    token_hint: str
    artifact_sha256: str
    package_status_at_issue: str
    was_current_at_issue: bool
    is_preliminary: bool
    is_current_now: bool
    lock_version: int
    status: Literal["active", "expired", "revoked", "artifact_unavailable"]
    expires_at: datetime
    revoked_at: datetime | None
    revocation_reason: str | None
    access_count: int
    first_accessed_at: datetime | None
    last_accessed_at: datetime | None
    created_by_user_id: UUID
    created_at: datetime


class DispositionPackageShareLinkIssuedRead(DispositionPackageShareLinkRead):
    share_url: str


BuyerPoolSourceFilter = Literal["all", "mine", "network", "external"]
BuyerPoolDecision = Literal["undecided", "shortlisted", "passed"]
BuyerPoolLifecycleStage = Literal[
    "discovered",
    "needs_review",
    "shortlisted",
    "contacted",
    "interested",
    "showing",
    "offer",
    "pass",
    "selected",
    "backup",
    "fallout",
]


class BuyerPoolRunRead(BaseModel):
    id: UUID
    version_number: int
    asset_class: str
    matcher_version: str
    score_policy_version: str
    status: str
    source_counts: dict[str, int]
    generated_at: datetime


class BuyerPurchaseEvidenceRead(BaseModel):
    provider_property_id: str | None
    address: str
    purchase_date: date | None
    purchase_price_cents: int | None
    property_types: list[str]
    distance_miles: float | None
    distance_basis: Literal["saved_provider_coordinates"] | None


class BuyerPoolEntryRead(BaseModel):
    id: UUID
    candidate_id: UUID
    buyer_id: UUID | None
    discovery_candidate_id: UUID | None
    source_type: Literal["mine", "network", "external"]
    origin_type: Literal["internal", "external"]
    provider: str | None
    external_key: str | None
    name: str
    company_name: str | None
    email: str | None
    phone: str | None
    decision_status: BuyerPoolDecision
    lifecycle_stage: BuyerPoolLifecycleStage
    decision_reason: str | None
    lock_version: int
    overlap_status: str
    possible_buyer_id: UUID | None
    possible_buyer_name: str | None
    possible_buyer_company_name: str | None
    overlap_evidence: dict[str, object]
    score_basis_points: int
    rank: int
    eligibility_status: str
    score_components: dict[str, int]
    score_explanation: list[str]
    supporting_evidence: list[dict[str, object]]
    conflicting_evidence: list[dict[str, object]]
    disqualifying_reasons: list[str]
    buy_box_version_id: UUID | None
    proof_status: str
    proof_expires_at: datetime | None
    relationship_status: str | None
    tier: str | None
    temperature: str | None
    purchase_evidence: list[BuyerPurchaseEvidenceRead] = Field(default_factory=list)


class BuyerPoolRead(BaseModel):
    case_id: UUID
    run: BuyerPoolRunRead | None
    total: int
    page: int
    page_size: int
    entries: list[BuyerPoolEntryRead]


class BuyerPoolDecisionUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    decision_status: BuyerPoolDecision
    lifecycle_stage: BuyerPoolLifecycleStage | None = None
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason")
    @classmethod
    def normalize_optional_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class BuyerPoolConversionRequest(BaseModel):
    expected_version: int = Field(ge=1)
    decision: Literal["create_new", "link_existing", "reject"]
    existing_buyer_id: UUID | None = None
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def normalize_conversion_reason(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 3:
            raise ValueError("A conversion decision requires a meaningful reason.")
        return normalized


class EligibleTransactionRead(BaseModel):
    id: UUID
    asset_class: Literal["house", "land"]
    seller_name: str
    property_address: str
    purchase_price_cents: int | None
    assignment_fee_cents: int | None


class DispositionMetrics(BaseModel):
    active_cases: int
    packages_pending: int
    buyer_selected: int
    reconciliation_pending: int
    below_margin_target: int


class DispositionOverview(BaseModel):
    can_view_private_economics: bool
    metrics: DispositionMetrics
    eligible_transactions: list[EligibleTransactionRead]
    cases: list[DispositionCaseRead]


class DispositionBuyerRecommendation(BaseModel):
    buyer_id: UUID
    buyer_name: str
    recommendation: Literal["priority", "backup", "hold", "exclude"]
    rationale: list[str]
    risks: list[str]
    evidence: list[str]
    citation_ids: list[str] = Field(default_factory=list)


class DispositionOfferComparison(BaseModel):
    offer_id: UUID
    buyer_id: UUID | None = None
    buyer_name: str
    strength: Literal["strong", "acceptable", "weak", "ineligible"]
    execution_risk: Literal["low", "moderate", "high", "unknown"] = "unknown"
    rationale: list[str]
    risks: list[str]
    citation_ids: list[str] = Field(default_factory=list)


class DispositionCopilotDraft(BaseModel):
    draft_type: Literal[
        "package_summary",
        "recipient_segment",
        "email",
        "sms",
        "call_brief",
        "follow_up",
    ]
    buyer_id: UUID | None = None
    title: str
    body: str
    citation_ids: list[str] = Field(min_length=1)
    requires_human_approval: Literal[True] = True


class DispositionReplyClassification(BaseModel):
    source_type: Literal["outreach_reply", "provider_evidence"]
    source_id: UUID
    classification: Literal[
        "interested",
        "inquiry",
        "pass",
        "offer_intent",
        "offer",
        "opt_out",
        "wrong_person",
        "needs_review",
    ]
    confidence: int = Field(ge=0, le=100)
    rationale: str
    citation_ids: list[str] = Field(min_length=1)
    requires_human_review: Literal[True] = True


class DispositionCopilotNextAction(BaseModel):
    action_type: Literal[
        "call",
        "proof_request",
        "showing",
        "counter",
        "deadline_action",
        "backup_activation",
        "follow_up",
        "package_correction",
        "reply_review",
    ]
    buyer_id: UUID | None = None
    offer_id: UUID | None = None
    action: str
    rationale: str
    confidence: int = Field(ge=0, le=100)
    priority: Literal["low", "normal", "high", "urgent"]
    citation_ids: list[str] = Field(min_length=1)
    requires_human_approval: Literal[True] = True


class DispositionBuyerUpdateProposal(BaseModel):
    buyer_id: UUID
    field_name: Literal[
        "relationship_status",
        "tier",
        "temperature",
        "preferred_markets",
        "preferred_property_types",
        "proof_of_funds_status",
        "reliability_note",
    ]
    proposed_value: str
    rationale: str
    confidence: int = Field(ge=0, le=100)
    citation_ids: list[str] = Field(min_length=1)
    requires_human_approval: Literal[True] = True


class DispositionEvidenceCitation(BaseModel):
    citation_id: str
    source_type: Literal[
        "case_snapshot",
        "package_version",
        "buyer_pool_entry",
        "buyer_match",
        "buyer_contact_status",
        "buyer_proof",
        "buyer_offer",
        "offer_revision",
        "buyer_engagement",
        "outreach_reply",
        "provider_evidence",
    ]
    source_id: str
    label: str
    fact: str
    status: str
    observed_at: datetime | None = None


class DispositionCopilotAiTrace(BaseModel):
    model_name: str
    prompt_version_id: UUID | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cost_microusd: int | None
    latency_ms: int | None
    started_at: datetime
    completed_at: datetime | None


class DispositionCopilotAuthority(BaseModel):
    can_send_outreach: Literal[False] = False
    can_select_buyer: Literal[False] = False
    can_bind_stonegate: Literal[False] = False
    can_update_buyer: Literal[False] = False


class DispositionCoordinationOutput(BaseModel):
    status_summary: str
    package_gaps: list[str]
    package_highlights: list[str]
    recommended_buyers: list[DispositionBuyerRecommendation]
    offer_comparison: list[DispositionOfferComparison]
    buyer_outreach_subject: str
    buyer_outreach_body: str
    recommended_internal_actions: list[str]
    relationship_update_proposals: list[str]
    risk_alerts: list[str]
    uncertainties: list[str]
    evidence: list[str]
    drafts: list[DispositionCopilotDraft] = Field(default_factory=list)
    reply_classifications: list[DispositionReplyClassification] = Field(default_factory=list)
    next_actions: list[DispositionCopilotNextAction] = Field(default_factory=list)
    buyer_update_proposals: list[DispositionBuyerUpdateProposal] = Field(default_factory=list)
    can_send_outreach: Literal[False] = False
    can_select_buyer: Literal[False] = False
    can_bind_stonegate: Literal[False] = False
    can_update_buyer: Literal[False] = False
    confidence: int = Field(ge=0, le=100)


class DispositionCopilotAnalyzeRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)


class DispositionCopilotRecommendationRead(BaseModel):
    id: UUID
    disposition_case_id: UUID
    transaction_id: UUID
    lead_id: UUID
    ai_run_log_id: UUID | None
    status: str
    output_payload: DispositionCoordinationOutput
    evidence_fingerprint: str
    evidence_citations: list[DispositionEvidenceCitation]
    evidence_status: Literal["current", "stale", "unknown"]
    stale_reason: str | None = None
    permitted_review_decisions: list[
        Literal["accepted", "edited", "rejected", "ignored"]
    ]
    ai_trace: DispositionCopilotAiTrace | None
    authority: DispositionCopilotAuthority = Field(
        default_factory=DispositionCopilotAuthority
    )
    confidence_score: int | None
    generated_at: datetime
    reviewed_at: datetime | None


class DispositionCopilotAnalyzeRead(BaseModel):
    run_id: UUID
    run_status: str
    message: str
    recommendation: DispositionCopilotRecommendationRead | None


class DispositionCopilotQualityEvaluation(BaseModel):
    scenario_group: Literal[
        "normal",
        "incomplete",
        "conflicting",
        "policy_blocked",
        "stale",
        "adversarial",
    ]
    critical_authority_violation: bool = False
    unsupported_or_hallucinated_citation: bool = False
    package_fact_correctness: Literal[
        "correct", "partially_correct", "incorrect", "not_applicable"
    ]
    buyer_match_relevance: Literal[
        "relevant", "partially_relevant", "not_relevant", "not_applicable"
    ]
    reply_classification_accuracy: Literal[
        "correct", "partially_correct", "incorrect", "not_applicable"
    ]
    next_action_usefulness: Literal[
        "useful", "correctable", "not_useful", "not_applicable"
    ]
    notes: str | None = Field(default=None, max_length=2000)


class DispositionCopilotReviewRequest(BaseModel):
    decision: Literal["accepted", "edited", "rejected", "ignored"]
    final_output: dict[str, object] | None = None
    notes: str | None = Field(default=None, max_length=2000)
    estimated_time_saved_seconds: int = Field(default=0, ge=0, le=86_400)
    quality_evaluation: DispositionCopilotQualityEvaluation | None = None

    def model_post_init(self, __context: object) -> None:
        if self.decision == "edited" and self.final_output is None:
            raise ValueError("Edited guidance requires the corrected output.")
        if self.decision != "edited" and self.final_output is not None:
            raise ValueError("Corrected output is only accepted with an edited decision.")


class DispositionCopilotReviewRead(BaseModel):
    id: UUID
    recommendation_id: UUID
    decision: str
    final_output: DispositionCoordinationOutput | None
    notes: str | None
    estimated_time_saved_seconds: int
    quality_evaluation: DispositionCopilotQualityEvaluation | None
    reviewed_at: datetime


class DispositionCopilotMetrics(BaseModel):
    generated: int
    reviewed: int
    accepted: int
    corrected: int
    rejected: int
    ignored: int
    accepted_or_corrected_rate_basis_points: int
    correction_rate_basis_points: int
    rejection_rate_basis_points: int
    ignore_rate_basis_points: int
    estimated_time_saved_minutes: int
    average_latency_ms: int | None
    p95_latency_ms: int | None
    average_input_tokens: int | None
    average_output_tokens: int | None
    average_cost_microusd: int | None
    total_cost_microusd: int
    pilot_evaluation: "DispositionCopilotPilotEvaluation"


class DispositionCopilotPilotEvaluation(BaseModel):
    minimum_evaluated_recommendations: int = 50
    minimum_distinct_cases: int = 10
    minimum_domain_sample_size: int = 10
    evaluated_recommendations: int
    distinct_cases: int
    observed_scenario_groups: list[
        Literal[
            "normal",
            "incomplete",
            "conflicting",
            "policy_blocked",
            "stale",
            "adversarial",
        ]
    ]
    missing_scenario_groups: list[
        Literal[
            "normal",
            "incomplete",
            "conflicting",
            "policy_blocked",
            "stale",
            "adversarial",
        ]
    ]
    critical_authority_violations: int
    unsupported_or_hallucinated_citations: int
    package_fact_correctness_basis_points: int
    package_fact_sample_size: int
    buyer_match_relevance_basis_points: int
    buyer_match_sample_size: int
    reply_classification_accuracy_basis_points: int
    reply_classification_sample_size: int
    next_action_useful_or_correctable_basis_points: int
    next_action_sample_size: int
    accept_or_correct_basis_points: int
    trace_attribution_basis_points: int
    pilot_ready: bool
    blockers: list[str]


class DispositionRiskAlert(BaseModel):
    severity: Literal["info", "warning", "critical"]
    item: str
    reason: str
    evidence: list[str]


class DispositionCopilotOverview(BaseModel):
    pilot_mode: Literal["draft_only"]
    runtime_status: str
    capability_status: str
    external_actions_blocked: bool
    readiness_score: int = Field(ge=0, le=100)
    readiness_band: Literal["ready", "needs_review", "blocked"]
    readiness_gaps: list[str]
    risk_alerts: list[DispositionRiskAlert]
    qualified_buyer_count: int
    verified_buyer_count: int
    offer_count: int
    backup_coverage: bool
    recommendations: list[DispositionCopilotRecommendationRead]
    metrics: DispositionCopilotMetrics
