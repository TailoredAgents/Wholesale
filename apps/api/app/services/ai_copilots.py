from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    AiAgentDefinition,
    AiCapabilityContract,
    AiCopilotAgentMapping,
    AiCopilotDefinition,
    AiDataGovernancePolicy,
    AiDataQualityRule,
    AiKnowledgeSource,
    AuditEvent,
)
from app.schemas.ai import (
    AiCapabilityContractRead,
    AiCopilotAgentMappingRead,
    AiCopilotFoundationDecision,
    AiCopilotFoundationInstallRead,
    AiCopilotFoundationRead,
    AiCopilotRead,
    AiDataGovernancePolicyRead,
    AiDataQualityRuleRead,
    AiKnowledgeSourceRead,
)

COMMON_PROHIBITED_ACTIONS = [
    "Invent or silently replace seller, property, buyer, consent, contract, or financial facts.",
    "Bypass organization scope, human role permissions, consent, suppression, or contact rules.",
    "Approve or present a binding offer.",
    "Create, alter, send, sign, release, or interpret a contract.",
    "Select a final buyer or change material deal economics.",
    "Move money, approve commissions, or finalize accounting.",
    "Change user access, retention, suppression, or market policy.",
    "Perform an external action without the exact capability approval and deterministic preflight.",
]

COPILOTS: tuple[dict[str, Any], ...] = (
    {
        "key": "prospecting_copilot",
        "name": "Prospecting Copilot",
        "description": (
            "Assists assigned VAs with record context, approved scripts, dispositions, callbacks, "
            "handoff preparation, and call-quality coaching."
        ),
        "owner_role_key": "prospecting_caller",
        "owner_title": "VA caller and prospecting manager",
        "authority": (
            "The human caller conducts cold calls, confirms outcomes, honors stop requests, and "
            "owns the accuracy of every warm handoff."
        ),
        "phase_key": "AI5",
        "agents": (
            ("prospecting_intelligence", "Prioritize eligible records and explain data quality."),
            ("call_intelligence", "Prepare evidence-backed notes and call-quality review."),
            ("compliance", "Flag suppression, consent, script, and calling-policy risks."),
        ),
    },
    {
        "key": "lead_manager_copilot",
        "name": "Lead Manager Copilot",
        "description": (
            "Assists the Lead Manager with inquiry summaries, qualification gaps, follow-up "
            "drafts, appointments, and neglected-lead protection."
        ),
        "owner_role_key": "acquisition_manager",
        "owner_title": "Lead Manager",
        "authority": (
            "The human Lead Manager owns qualification, seller communication, appointment "
            "quality, follow-up judgment, and handoff to Acquisitions."
        ),
        "phase_key": "AI4",
        "agents": (
            ("inbound_lead", "Triage opted-in inquiries and prepare response drafts."),
            ("lead_management", "Detect gaps, stale leads, missed replies, and next actions."),
            ("call_intelligence", "Prepare evidence-backed conversation facts for review."),
            ("compliance", "Preflight consent, suppression, and communication policy."),
        ),
    },
    {
        "key": "acquisitions_copilot",
        "name": "Acquisitions Copilot",
        "description": (
            "Assists the closer with call and appointment preparation, property evidence, "
            "underwriting explanation, negotiation preparation, and follow-up."
        ),
        "owner_role_key": "acquisition_rep",
        "owner_title": "Acquisitions Closer and covering CEO",
        "authority": (
            "The human closer approves comps, repairs, underwriting, offer authority, "
            "concessions, seller communication, and appointment outcomes."
        ),
        "phase_key": "AI6",
        "agents": (
            ("call_intelligence", "Extract reviewed seller facts and commitments."),
            ("appointment_preparation", "Prepare the seller meeting brief."),
            ("underwriting_comp", "Explain valuation evidence and missing inputs."),
            ("negotiation_coach", "Prepare questions and approved-authority warnings."),
            ("compliance", "Flag communication, representation, and evidence risk."),
        ),
    },
    {
        "key": "transaction_copilot",
        "name": "Transaction Copilot",
        "description": (
            "Assists coordination with documents, parties, deadlines, checklist gaps, closing "
            "drafts, and risk escalation."
        ),
        "owner_role_key": "transaction_coordinator",
        "owner_title": "Transaction Coordinator",
        "authority": (
            "The human coordinator confirms contract facts, deadlines, parties, checklist "
            "completion, external requests, and closing status."
        ),
        "phase_key": "AI7",
        "agents": (
            ("transaction_coordinator", "Track transaction milestones and missing work."),
            ("compliance", "Flag document, retention, communication, and authority risk."),
        ),
    },
    {
        "key": "disposition_copilot",
        "name": "Disposition Copilot",
        "description": (
            "Assists the disposition specialist with buyer matching, package preparation, "
            "approved outreach, response comparison, showings, deposits, and backup coverage."
        ),
        "owner_role_key": "disposition_manager",
        "owner_title": "Disposition specialist",
        "authority": (
            "The human disposition specialist approves package facts, recipients, communication, "
            "buyer recommendations, economics, and placement strategy."
        ),
        "phase_key": "AI8",
        "agents": (
            ("disposition", "Match buyers and prepare fact-checked deal packages."),
            ("buyer_relationship", "Maintain buyer preference and reliability proposals."),
            ("compliance", "Preflight claims, recipients, suppression, and communication."),
        ),
    },
    {
        "key": "finance_copilot",
        "name": "Finance Copilot",
        "description": (
            "Assists approved finance staff with funded-deal reconciliation, margin, "
            "commissions, accounting handoff, and exception detection."
        ),
        "owner_role_key": "finance_accounting",
        "owner_title": "Owner and approved finance staff",
        "authority": (
            "Humans approve funded status, reconciliation, commissions, payments, accounting "
            "entries, reserves, and distributions."
        ),
        "phase_key": "AI9",
        "agents": (("finance_commission", "Draft reconciliation and commission calculations."),),
    },
    {
        "key": "marketing_copilot",
        "name": "Marketing Copilot",
        "description": (
            "Assists management with attribution, funnel quality, source economics, and "
            "controlled experiment recommendations."
        ),
        "owner_role_key": "marketing_manager",
        "owner_title": "Owner and marketing staff",
        "authority": (
            "Humans approve budgets, campaigns, creative, audiences, published changes, and "
            "provider delivery."
        ),
        "phase_key": "AI9",
        "agents": (
            ("marketing_intelligence", "Analyze source performance and draft experiments."),
            ("compliance", "Flag attribution, consent, audience, and claim risk."),
        ),
    },
    {
        "key": "executive_copilot",
        "name": "Executive Copilot",
        "description": (
            "Assists the CEO with priorities, bottlenecks, staffing pressure, cash visibility, "
            "risk, and decisions."
        ),
        "owner_role_key": "owner",
        "owner_title": "Owner and CEO",
        "authority": (
            "The CEO owns company strategy, staffing, market launch, budgets, exceptions, and all "
            "changes to AI authority."
        ),
        "phase_key": "AI9",
        "agents": (("executive_operations", "Prepare evidence-backed operating briefs."),),
    },
)


def capability(
    copilot_key: str,
    capability_key: str,
    name: str,
    triggers: list[str],
    inputs: list[str],
    outputs: list[str],
    tools: list[str],
    evidence: list[str],
    approval_actions: list[str],
    escalations: list[str],
    prohibited: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "copilot_key": copilot_key,
        "capability_key": capability_key,
        "name": name,
        "triggers": triggers,
        "inputs": inputs,
        "outputs": outputs,
        "tools": tools,
        "evidence": evidence,
        "approval": {
            "initial_level": "draft",
            "human_approval_required_for": approval_actions,
            "external_execution_enabled": False,
        },
        "escalation": {
            "when": escalations,
            "preserve_complete_history": True,
            "stop_on_uncertainty": True,
        },
        "prohibited": [*COMMON_PROHIBITED_ACTIONS, *(prohibited or [])],
    }


CAPABILITY_CONTRACTS = (
    capability(
        "prospecting_copilot",
        "prospecting.prioritize",
        "Prioritize eligible prospects",
        ["prospect.batch_ready", "prospect.callback_due"],
        ["retained screening evidence", "campaign assignment", "property facts", "attempt history"],
        ["ranked assigned records", "priority reasons", "data-quality warnings"],
        ["prospects.read_assigned", "campaigns.read_assigned", "property.read_provider_facts"],
        ["screening reference", "campaign record", "provider fact timestamps"],
        ["change queue eligibility", "change assignment", "create callback"],
        ["missing screening evidence", "conflicting contact identity", "provider facts are stale"],
    ),
    capability(
        "prospecting_copilot",
        "call.quality_coach",
        "Review prospecting call quality",
        ["call.reviewed", "handoff.returned"],
        ["approved script version", "transcript", "disposition", "handoff answers"],
        ["script adherence", "qualification completeness", "coaching draft", "evidence timestamps"],
        ["calls.read_transcript", "scripts.read_approved", "handoffs.read"],
        ["transcript timestamps", "script version", "reviewed disposition"],
        ["publish coaching", "change call outcome", "change handoff facts"],
        ["recording disclosure is missing", "speaker identity is uncertain", "complaint language"],
    ),
    capability(
        "lead_manager_copilot",
        "lead.triage",
        "Triage new seller inquiry",
        ["lead.created", "lead.duplicate_submission"],
        ["seller inquiry", "consent evidence", "property", "source", "current owner"],
        ["factual summary", "urgency indicators", "missing questions", "first-response draft"],
        ["leads.read_assigned", "consent.read", "conversations.read_assigned"],
        ["submission record", "consent version", "source attribution"],
        ["send response", "change owner", "mark qualified", "schedule appointment"],
        ["consent is unclear", "duplicate conflict", "seller requests legal or financial advice"],
    ),
    capability(
        "lead_manager_copilot",
        "lead.next_action",
        "Protect follow-up and qualification",
        ["lead.updated", "message.received", "task.overdue", "lead.sla_at_risk"],
        ["lead stage", "qualification", "conversation", "tasks", "appointments", "SLA"],
        ["qualification gaps", "recommended questions", "next-task proposal", "follow-up draft"],
        ["leads.read_assigned", "tasks.read_assigned", "calendar.read", "messages.draft"],
        ["current lead fields", "conversation timestamps", "task and appointment records"],
        ["create task", "send message", "change stage", "schedule appointment"],
        [
            "conflicting seller facts",
            "missed-reply risk",
            "appointment conflict",
            "policy uncertainty",
        ],
        ["Silently qualify, disqualify, or reassign a seller."],
    ),
    capability(
        "acquisitions_copilot",
        "call.summarize",
        "Prepare reviewed acquisition call facts",
        ["call.recording_ready", "call.transcript_ready"],
        ["recording", "transcript", "speaker segments", "lead context"],
        [
            "structured facts",
            "commitments",
            "objections",
            "missing questions",
            "evidence timestamps",
        ],
        ["calls.read_recording", "calls.read_transcript", "leads.read"],
        ["speaker segments", "transcript timestamps", "provider recording identifier"],
        ["update CRM fact", "create task", "send follow-up"],
        [
            "speaker identity is uncertain",
            "critical fact conflicts",
            "recording policy is incomplete",
        ],
    ),
    capability(
        "acquisitions_copilot",
        "appointment.brief",
        "Prepare seller appointment brief",
        ["appointment.scheduled", "appointment.brief_requested"],
        [
            "seller",
            "property",
            "qualification",
            "conversation",
            "underwriting",
            "tasks",
            "logistics",
        ],
        ["meeting brief", "unresolved questions", "objections", "evidence gaps", "logistics"],
        ["leads.read", "appointments.read", "underwriting.read", "tasks.read"],
        ["CRM record versions", "appointment record", "underwriting version"],
        ["change appointment", "change underwriting", "contact seller"],
        [
            "missing decision maker",
            "unsafe property note",
            "stale underwriting",
            "schedule conflict",
        ],
    ),
    capability(
        "acquisitions_copilot",
        "underwriting.analyze",
        "Explain valuation evidence",
        ["underwriting.saved", "field_evidence.reviewed", "comp_review.requested"],
        ["subject facts", "provider facts", "comp set", "repair evidence", "formula outputs"],
        ["evidence summary", "outliers", "missing inputs", "confidence reasons", "report checks"],
        ["property.read_provider_facts", "underwriting.read", "reports.draft"],
        ["provider timestamps", "comp sources", "repair source", "formula version"],
        ["select comp", "approve ARV", "approve repair amount", "approve offer ceiling"],
        ["weak comp set", "provider disagreement", "material outlier", "missing repair evidence"],
    ),
    capability(
        "acquisitions_copilot",
        "negotiation.coach",
        "Prepare negotiation guidance",
        ["appointment.brief_requested", "seller.counter_received"],
        ["seller context", "objections", "approved negotiation plan", "offer authority"],
        ["questions", "objection preparation", "options within authority", "ceiling warnings"],
        ["leads.read", "negotiation.read_approved", "underwriting.read_approved"],
        ["approved plan version", "authority ledger", "seller conversation evidence"],
        ["present price", "record concession", "change authority", "send offer"],
        ["requested action exceeds authority", "legal representation requested", "plan is stale"],
    ),
    capability(
        "transaction_copilot",
        "transaction.coordinate",
        "Monitor transaction requirements",
        ["contract.executed", "transaction.updated", "deadline.approaching", "document.received"],
        ["executed package", "parties", "checklist", "deadlines", "documents", "communications"],
        ["missing items", "deadline risks", "status summary", "external request draft"],
        ["transactions.read", "documents.read", "checklists.read", "messages.draft"],
        ["document pages", "provider events", "checklist evidence", "timeline"],
        ["mark checklist complete", "send request", "change deadline", "mark funded"],
        [
            "contract terms conflict",
            "signature is missing",
            "deadline is ambiguous",
            "legal question",
        ],
    ),
    capability(
        "disposition_copilot",
        "disposition.match",
        "Match contracted deal to qualified buyers",
        ["disposition.ready", "buyer.updated", "offer.received"],
        ["approved deal facts", "buyer criteria", "proof", "capacity", "activity", "reliability"],
        ["ranked buyers", "fit reasons", "risk flags", "package draft", "offer comparison"],
        ["deals.read_approved", "buyers.read", "documents.read_approved", "messages.draft"],
        ["approved deal version", "buyer criteria version", "proof and reliability records"],
        ["send campaign", "select buyer", "change economics", "publish property claim"],
        ["deal fact is unverified", "proof is stale", "buyer conflict", "recipient suppression"],
    ),
    capability(
        "disposition_copilot",
        "buyer.follow_up",
        "Prepare buyer relationship follow-up",
        ["buyer.reply_received", "buyer.proof_expiring", "buyer.follow_up_due"],
        ["buyer criteria", "communication history", "proof", "deal activity"],
        ["response classification", "preference update proposal", "follow-up draft", "risk alert"],
        ["buyers.read", "conversations.read", "messages.draft"],
        ["buyer message", "current criteria", "proof record"],
        ["update criteria", "send message", "approve proof", "change reliability"],
        ["identity conflict", "opt-out request", "unsupported preference inference"],
    ),
    capability(
        "finance_copilot",
        "finance.reconcile",
        "Draft funded-deal reconciliation",
        ["closing.funded", "closing_statement.received", "commission.review_requested"],
        ["closing statement", "revenue", "deductions", "compensation plan", "role credits"],
        ["reconciliation draft", "margin", "commission draft", "exceptions", "accounting handoff"],
        ["finance.read", "documents.read", "compensation.read_approved"],
        ["funding evidence", "statement pages", "plan version", "role-credit approvals"],
        ["mark funded", "approve commission", "post accounting", "move money"],
        ["material difference", "missing funding evidence", "unapproved role credit"],
    ),
    capability(
        "marketing_copilot",
        "marketing.analyze",
        "Analyze source economics",
        ["campaign.metrics_refreshed", "closing.reconciled", "marketing.review_due"],
        ["attribution", "campaign cost", "lead outcomes", "funded revenue", "margin"],
        ["funnel analysis", "source economics", "data gaps", "experiment recommendation"],
        ["marketing.read", "finance.read_aggregates", "conversions.draft"],
        ["source records", "cost ledger", "outcome records", "attribution version"],
        ["change budget", "publish campaign", "change audience", "send conversion"],
        ["attribution is incomplete", "sample is too small", "consent basis is missing"],
    ),
    capability(
        "executive_copilot",
        "operations.brief",
        "Prepare executive operating brief",
        ["operations.daily_brief", "operations.weekly_brief", "critical_exception.created"],
        [
            "approved aggregate metrics",
            "SLA exceptions",
            "pipeline",
            "cash",
            "staffing",
            "AI health",
        ],
        [
            "priorities",
            "bottlenecks",
            "risks",
            "decision requests",
            "confidence and source periods",
        ],
        ["operations.read_aggregates", "finance.read_aggregates", "ai.read_metrics"],
        ["metric definitions", "reporting period", "source-system timestamps"],
        ["change staffing", "change budget", "approve exception", "change AI authority"],
        ["material data is stale", "financial mismatch", "critical compliance event"],
    ),
)

DATA_POLICIES: tuple[dict[str, Any], ...] = (
    {
        "key": "seller_identity_contact",
        "name": "Seller identity and contact",
        "category": "seller",
        "fields": ["contact.name", "contact.phone", "contact.email", "contact.preferred_channel"],
        "sources": [
            "human_confirmed",
            "seller_submitted",
            "verified_provider",
            "model_inference",
        ],
        "overwrite": (
            "Human-confirmed values cannot be overwritten by provider or model output. "
            "A conflicting value creates a review proposal that preserves both sources."
        ),
        "redaction": (
            "Remove direct identifiers from evaluation exports and operational alerts. "
            "Models receive only the contact fields required by the scoped capability."
        ),
        "retention": (
            "Retain with the lead under the approved CRM retention policy; suppression and consent "
            "evidence outlive ordinary communication content where required."
        ),
        "roles": ["owner", "acquisition_manager", "acquisition_rep", "prospecting_caller"],
    },
    {
        "key": "property_facts",
        "name": "Property facts and condition",
        "category": "property",
        "fields": [
            "property.address",
            "property.type",
            "property.beds",
            "property.baths",
            "property.square_feet",
            "property.year_built",
            "property.condition",
        ],
        "sources": [
            "human_confirmed",
            "field_evidence",
            "verified_provider",
            "unverified_provider",
            "model_inference",
        ],
        "overwrite": (
            "Provider refreshes may update unconfirmed provider fields but cannot replace "
            "human-confirmed or reviewed field evidence. Conflicts create review items."
        ),
        "redaction": "Keep the property address out of redacted evaluation exports.",
        "retention": (
            "Retain source, retrieval time, and version with the property and underwriting."
        ),
        "roles": [
            "owner",
            "acquisition_manager",
            "acquisition_rep",
            "transaction_coordinator",
            "disposition_manager",
        ],
    },
    {
        "key": "consent_suppression",
        "name": "Consent, suppression, and contact policy",
        "category": "compliance",
        "fields": [
            "consent.*",
            "suppression.*",
            "contact_method.validity",
            "communication.policy_result",
        ],
        "sources": ["provider_event", "human_confirmed", "retained_evidence"],
        "overwrite": (
            "AI cannot grant, infer, or override consent or calling eligibility. Revocation and "
            "suppression block communication until a separately retained valid change is reviewed."
        ),
        "redaction": (
            "Preserve policy decisions while removing message content not required for review."
        ),
        "retention": "Retain immutable consent and suppression evidence according to legal policy.",
        "roles": ["owner", "acquisition_manager", "marketing_manager"],
    },
    {
        "key": "underwriting_offer_authority",
        "name": "Underwriting and offer authority",
        "category": "underwriting",
        "fields": ["underwriting.*", "repair_estimate.*", "negotiation_plan.*", "offer_ledger.*"],
        "sources": ["human_approved", "deterministic_calculation", "reviewed_evidence", "provider"],
        "overwrite": (
            "New evidence creates a new version. AI and provider output cannot alter an approved "
            "underwriting version, negotiation plan, concession, or offer ceiling."
        ),
        "redaction": "Remove seller identity from evaluation cases unless identity is material.",
        "retention": "Retain immutable versions, evidence, approvals, and price discussions.",
        "roles": ["owner", "acquisition_manager", "acquisition_rep"],
    },
    {
        "key": "contracts_closing",
        "name": "Contracts and closing records",
        "category": "transaction",
        "fields": ["contract.*", "transaction.*", "document.*", "closing.*"],
        "sources": [
            "executed_document",
            "provider_event",
            "human_confirmed",
            "model_proposal",
        ],
        "overwrite": (
            "Executed documents and provider signature events are immutable evidence. "
            "AI extraction is always a proposal until confirmed."
        ),
        "redaction": "Remove signatures, account details, and direct identifiers from model evals.",
        "retention": "Retain private documents and audit evidence under the approved legal policy.",
        "roles": ["owner", "transaction_coordinator", "acquisition_manager"],
    },
    {
        "key": "financial_compensation",
        "name": "Financial and compensation data",
        "category": "finance",
        "fields": ["revenue.*", "deduction.*", "compensation.*", "accounting.*"],
        "sources": ["funding_evidence", "approved_plan", "human_approved", "model_proposal"],
        "overwrite": (
            "AI can draft calculations and flag differences but cannot finalize funded status, "
            "commissions, payments, accounting entries, or historical plan versions."
        ),
        "redaction": "Remove bank, tax, payment, and personal account details from model context.",
        "retention": "Retain reconciliations and approvals under the accounting retention policy.",
        "roles": ["owner", "finance_accounting"],
    },
    {
        "key": "ai_traces_evaluations",
        "name": "AI traces and evaluation evidence",
        "category": "ai_governance",
        "fields": ["ai_run.*", "ai_trace.*", "ai_evaluation.*", "ai_approval.*"],
        "sources": ["system_recorded", "human_reviewed"],
        "overwrite": (
            "Runs and review decisions are append-only. Corrections create linked evidence rather "
            "than rewriting the original output."
        ),
        "redaction": (
            "Strip secrets and unnecessary personal data before trace or dataset retention."
        ),
        "retention": (
            "Retain enough evidence to reproduce promotion decisions and investigate failures."
        ),
        "roles": ["owner", "ceo", "administrator"],
    },
)

KNOWLEDGE_SOURCES: tuple[dict[str, Any], ...] = (
    {
        "key": "operating_model",
        "title": "Stonegate Operating Model",
        "category": "operations",
        "source_type": "versioned_document",
        "reference": "docs/OPERATING_MODEL.md",
        "owner": "owner",
        "audience": ["owner", "acquisition_manager", "acquisition_rep", "disposition_manager"],
        "authoritative": True,
        "status": "draft",
    },
    {
        "key": "ai_agent_policy",
        "title": "AI Agent System Policy",
        "category": "ai_governance",
        "source_type": "versioned_document",
        "reference": "docs/AI_AGENTS.md",
        "owner": "owner",
        "audience": ["owner", "ceo", "administrator"],
        "authoritative": True,
        "status": "draft",
    },
    {
        "key": "underwriting_method",
        "title": "Underwriting Comparable Method",
        "category": "underwriting",
        "source_type": "versioned_document",
        "reference": "docs/UNDERWRITING_COMP_METHOD.md",
        "owner": "acquisition_manager",
        "audience": ["owner", "acquisition_manager", "acquisition_rep"],
        "authoritative": True,
        "status": "draft",
    },
    {
        "key": "prospecting_scripts",
        "title": "Approved Prospecting Scripts",
        "category": "prospecting",
        "source_type": "database_registry",
        "reference": "prospecting_script_versions:approved",
        "owner": "acquisition_manager",
        "audience": ["owner", "acquisition_manager", "prospecting_caller"],
        "authoritative": True,
        "status": "draft",
    },
    {
        "key": "lead_manager_qualification",
        "title": "Approved Lead Manager Qualification Standard",
        "category": "lead_management",
        "source_type": "database_registry",
        "reference": "lead_manager_qualification_scripts:approved",
        "owner": "acquisition_manager",
        "audience": ["owner", "acquisition_manager"],
        "authoritative": True,
        "status": "draft",
    },
    {
        "key": "legal_templates",
        "title": "Attorney-Approved Market Templates",
        "category": "legal",
        "source_type": "document_registry",
        "reference": "legal_template_versions:approved",
        "owner": "owner",
        "audience": ["owner", "acquisition_manager", "transaction_coordinator"],
        "authoritative": False,
        "status": "pending_external_review",
    },
)

DATA_QUALITY_RULES: tuple[dict[str, Any], ...] = (
    {
        "key": "duplicate_contact",
        "name": "Duplicate contact identity",
        "record_type": "lead",
        "fields": ["contact.phone", "contact.email"],
        "rule_type": "duplicate",
        "severity": "high",
        "deterministic": True,
        "configuration": {"normalization": "canonical", "match": "exact"},
        "action": "Create a duplicate review item; never merge records automatically.",
    },
    {
        "key": "duplicate_property",
        "name": "Duplicate canonical property",
        "record_type": "property",
        "fields": ["property.canonical_address_key"],
        "rule_type": "duplicate",
        "severity": "high",
        "deterministic": True,
        "configuration": {"match": "exact", "scope": "organization"},
        "action": "Create a duplicate review item and preserve every submission.",
    },
    {
        "key": "stale_active_lead",
        "name": "Stale active lead action",
        "record_type": "lead",
        "fields": ["lead.stage", "lead.next_action_at", "lead.last_contact_at"],
        "rule_type": "freshness",
        "severity": "medium",
        "deterministic": True,
        "configuration": {"requires_dated_next_action": True},
        "action": "Flag the record and propose an owned follow-up task.",
    },
    {
        "key": "missing_attribution",
        "name": "Missing acquisition attribution",
        "record_type": "lead",
        "fields": ["lead.source", "lead.campaign_id", "lead.first_touch"],
        "rule_type": "completeness",
        "severity": "medium",
        "deterministic": True,
        "configuration": {"required_for_reporting": True},
        "action": "Flag reporting as incomplete; never invent a campaign or source.",
    },
    {
        "key": "property_fact_conflict",
        "name": "Conflicting property fact",
        "record_type": "property",
        "fields": [
            "property.beds",
            "property.baths",
            "property.square_feet",
            "property.year_built",
        ],
        "rule_type": "conflict",
        "severity": "high",
        "deterministic": True,
        "configuration": {"source_precedence_policy": "property_facts"},
        "action": "Preserve both sources and require review before authoritative use.",
    },
    {
        "key": "unverified_model_fact",
        "name": "Unverified model-derived fact",
        "record_type": "all",
        "fields": ["*"],
        "rule_type": "provenance",
        "severity": "high",
        "deterministic": True,
        "configuration": {"model_output_is_authoritative": False},
        "action": "Store as a proposal with evidence and reviewer status.",
    },
)


def install_copilot_foundation(
    db: Session,
    principal: Principal,
) -> AiCopilotFoundationInstallRead:
    from app.services.ai_orchestrator import install_portfolio

    install_portfolio(db, principal)
    agents = {
        item.key: item
        for item in db.scalars(
            select(AiAgentDefinition).where(
                AiAgentDefinition.organization_id == principal.organization_id
            )
        ).all()
    }
    existing_copilots = {
        item.key: item
        for item in db.scalars(
            select(AiCopilotDefinition).where(
                AiCopilotDefinition.organization_id == principal.organization_id
            )
        ).all()
    }
    created_copilots = 0
    for spec in COPILOTS:
        copilot = existing_copilots.get(spec["key"])
        if copilot is None:
            copilot = AiCopilotDefinition(
                organization_id=principal.organization_id,
                key=spec["key"],
                name=spec["name"],
                description=spec["description"],
                human_owner_role_key=spec["owner_role_key"],
                human_owner_title=spec["owner_title"],
                human_authority_summary=spec["authority"],
                status="draft",
                phase_key=spec["phase_key"],
                created_by_user_id=principal.user_id,
            )
            db.add(copilot)
            db.flush()
            existing_copilots[copilot.key] = copilot
            created_copilots += 1
        else:
            copilot.name = spec["name"]
            copilot.description = spec["description"]
            copilot.human_owner_role_key = spec["owner_role_key"]
            copilot.human_owner_title = spec["owner_title"]
            copilot.human_authority_summary = spec["authority"]
            copilot.phase_key = spec["phase_key"]

    existing_mappings = {
        (item.copilot_definition_id, item.agent_definition_id)
        for item in db.scalars(
            select(AiCopilotAgentMapping).where(
                AiCopilotAgentMapping.organization_id == principal.organization_id
            )
        ).all()
    }
    created_mappings = 0
    for spec in COPILOTS:
        copilot = existing_copilots[spec["key"]]
        for order, (agent_key, purpose) in enumerate(spec["agents"], start=1):
            agent = agents.get(agent_key)
            if agent is None:
                raise ValueError(f"Required AI specialist is missing: {agent_key}.")
            mapping_key = (copilot.id, agent.id)
            if mapping_key in existing_mappings:
                continue
            db.add(
                AiCopilotAgentMapping(
                    organization_id=principal.organization_id,
                    copilot_definition_id=copilot.id,
                    agent_definition_id=agent.id,
                    purpose=purpose,
                    display_order=order,
                )
            )
            existing_mappings.add(mapping_key)
            created_mappings += 1

    existing_contracts = {
        (item.copilot_definition_id, item.capability_key, item.version_number)
        for item in db.scalars(
            select(AiCapabilityContract).where(
                AiCapabilityContract.organization_id == principal.organization_id
            )
        ).all()
    }
    created_contracts = 0
    owner_roles = {item["key"]: item["owner_role_key"] for item in COPILOTS}
    for spec in CAPABILITY_CONTRACTS:
        copilot = existing_copilots[spec["copilot_key"]]
        contract_key = (copilot.id, spec["capability_key"], 1)
        if contract_key in existing_contracts:
            continue
        db.add(
            AiCapabilityContract(
                organization_id=principal.organization_id,
                copilot_definition_id=copilot.id,
                capability_key=spec["capability_key"],
                name=spec["name"],
                version_number=1,
                status="draft",
                owner_role_key=owner_roles[spec["copilot_key"]],
                trigger_events=spec["triggers"],
                input_requirements=spec["inputs"],
                output_requirements=spec["outputs"],
                allowed_tool_scopes=spec["tools"],
                evidence_requirements=spec["evidence"],
                approval_policy=spec["approval"],
                escalation_policy=spec["escalation"],
                prohibited_actions=spec["prohibited"],
                created_by_user_id=principal.user_id,
            )
        )
        existing_contracts.add(contract_key)
        created_contracts += 1

    created_policies = _install_policies(db, principal)
    created_knowledge = _install_knowledge(db, principal)
    created_rules = _install_quality_rules(db, principal)
    _audit(
        db,
        principal,
        "ai.copilot_foundation_installed",
        {
            "copilots": created_copilots,
            "mappings": created_mappings,
            "contracts": created_contracts,
            "policies": created_policies,
            "knowledge_sources": created_knowledge,
            "data_quality_rules": created_rules,
        },
    )
    db.commit()
    return AiCopilotFoundationInstallRead(
        created_copilot_count=created_copilots,
        created_mapping_count=created_mappings,
        created_contract_count=created_contracts,
        created_policy_count=created_policies,
        created_knowledge_source_count=created_knowledge,
        created_data_quality_rule_count=created_rules,
        foundation=get_copilot_foundation(db, principal),
    )


def decide_copilot_foundation(
    db: Session,
    principal: Principal,
    payload: AiCopilotFoundationDecision,
) -> AiCopilotFoundationRead:
    copilots = _copilots(db, principal)
    if not copilots:
        raise ValueError("Install the AI1 copilot foundation before deciding it.")
    now = datetime.now(UTC)
    approve = payload.decision == "approve"
    for copilot in copilots:
        _set_approval(copilot, principal, now, approve, active_status="active")
    for contract in _contracts(db, principal):
        _set_approval(contract, principal, now, approve)
    for policy in _policies(db, principal):
        _set_approval(policy, principal, now, approve)
    for quality_rule in _quality_rules(db, principal):
        _set_approval(quality_rule, principal, now, approve)
    for knowledge_source in _knowledge(db, principal):
        if knowledge_source.status == "pending_external_review":
            continue
        _set_approval(knowledge_source, principal, now, approve)
    _audit(
        db,
        principal,
        f"ai.copilot_foundation_{'approved' if approve else 'returned'}",
        {"notes": payload.notes},
    )
    db.commit()
    return get_copilot_foundation(db, principal)


def get_copilot_foundation(db: Session, principal: Principal) -> AiCopilotFoundationRead:
    copilots = _copilots(db, principal)
    agents = {
        item.id: item
        for item in db.scalars(
            select(AiAgentDefinition).where(
                AiAgentDefinition.organization_id == principal.organization_id
            )
        ).all()
    }
    mappings = db.scalars(
        select(AiCopilotAgentMapping)
        .where(AiCopilotAgentMapping.organization_id == principal.organization_id)
        .order_by(AiCopilotAgentMapping.display_order)
    ).all()
    contracts = _contracts(db, principal)
    mappings_by_copilot: dict[Any, list[AiCopilotAgentMapping]] = {}
    contracts_by_copilot: dict[Any, list[AiCapabilityContract]] = {}
    for mapping in mappings:
        mappings_by_copilot.setdefault(mapping.copilot_definition_id, []).append(mapping)
    for contract in contracts:
        contracts_by_copilot.setdefault(contract.copilot_definition_id, []).append(contract)

    policies = _policies(db, principal)
    knowledge = _knowledge(db, principal)
    quality_rules = _quality_rules(db, principal)
    approved = bool(copilots) and all(item.status == "active" for item in copilots)
    approved = approved and all(item.status == "approved" for item in contracts)
    approved = approved and all(item.status == "approved" for item in policies)
    approved = approved and all(item.status == "approved" for item in quality_rules)
    approved = approved and all(
        item.status == "approved" for item in knowledge if item.is_authoritative
    )
    status = "approved" if approved else ("draft" if copilots else "not_installed")
    return AiCopilotFoundationRead(
        status=status,
        copilots=[
            _copilot_read(
                item,
                mappings_by_copilot.get(item.id, []),
                contracts_by_copilot.get(item.id, []),
                agents,
            )
            for item in copilots
        ],
        data_governance_policies=[_policy_read(item) for item in policies],
        knowledge_sources=[_knowledge_read(item) for item in knowledge],
        data_quality_rules=[_quality_rule_read(item) for item in quality_rules],
    )


def _install_policies(db: Session, principal: Principal) -> int:
    existing = {
        (item.key, item.version_number)
        for item in db.scalars(
            select(AiDataGovernancePolicy).where(
                AiDataGovernancePolicy.organization_id == principal.organization_id
            )
        ).all()
    }
    created = 0
    for spec in DATA_POLICIES:
        if (spec["key"], 1) in existing:
            continue
        db.add(
            AiDataGovernancePolicy(
                organization_id=principal.organization_id,
                key=spec["key"],
                name=spec["name"],
                data_category=spec["category"],
                field_scope=spec["fields"],
                version_number=1,
                status="draft",
                source_precedence=spec["sources"],
                overwrite_policy=spec["overwrite"],
                redaction_rule=spec["redaction"],
                retention_rule=spec["retention"],
                permitted_role_keys=spec["roles"],
                created_by_user_id=principal.user_id,
            )
        )
        existing.add((spec["key"], 1))
        created += 1
    return created


def _install_knowledge(db: Session, principal: Principal) -> int:
    existing = {
        (item.key, item.version_number)
        for item in db.scalars(
            select(AiKnowledgeSource).where(
                AiKnowledgeSource.organization_id == principal.organization_id
            )
        ).all()
    }
    created = 0
    review_due = datetime.now(UTC) + timedelta(days=90)
    for spec in KNOWLEDGE_SOURCES:
        if (spec["key"], 1) in existing:
            continue
        db.add(
            AiKnowledgeSource(
                organization_id=principal.organization_id,
                key=spec["key"],
                title=spec["title"],
                category=spec["category"],
                source_type=spec["source_type"],
                content_reference=spec["reference"],
                version_number=1,
                status=spec["status"],
                owner_role_key=spec["owner"],
                audience_role_keys=spec["audience"],
                is_authoritative=spec["authoritative"],
                effective_at=datetime.now(UTC),
                review_due_at=review_due,
                created_by_user_id=principal.user_id,
            )
        )
        existing.add((spec["key"], 1))
        created += 1
    return created


def _install_quality_rules(db: Session, principal: Principal) -> int:
    existing = {
        (item.key, item.version_number)
        for item in db.scalars(
            select(AiDataQualityRule).where(
                AiDataQualityRule.organization_id == principal.organization_id
            )
        ).all()
    }
    created = 0
    for spec in DATA_QUALITY_RULES:
        if (spec["key"], 1) in existing:
            continue
        db.add(
            AiDataQualityRule(
                organization_id=principal.organization_id,
                key=spec["key"],
                name=spec["name"],
                record_type=spec["record_type"],
                field_scope=spec["fields"],
                rule_type=spec["rule_type"],
                severity=spec["severity"],
                is_deterministic=spec["deterministic"],
                configuration=spec["configuration"],
                resolution_action=spec["action"],
                version_number=1,
                status="draft",
                created_by_user_id=principal.user_id,
            )
        )
        existing.add((spec["key"], 1))
        created += 1
    return created


def _set_approval(
    item: Any,
    principal: Principal,
    now: datetime,
    approve: bool,
    *,
    active_status: str = "approved",
) -> None:
    item.status = active_status if approve else "draft"
    item.approved_by_user_id = principal.user_id if approve else None
    item.approved_at = now if approve else None


def _copilots(db: Session, principal: Principal) -> list[AiCopilotDefinition]:
    return list(
        db.scalars(
            select(AiCopilotDefinition)
            .where(AiCopilotDefinition.organization_id == principal.organization_id)
            .order_by(AiCopilotDefinition.name)
        ).all()
    )


def _contracts(db: Session, principal: Principal) -> list[AiCapabilityContract]:
    return list(
        db.scalars(
            select(AiCapabilityContract)
            .where(AiCapabilityContract.organization_id == principal.organization_id)
            .order_by(AiCapabilityContract.name)
        ).all()
    )


def _policies(db: Session, principal: Principal) -> list[AiDataGovernancePolicy]:
    return list(
        db.scalars(
            select(AiDataGovernancePolicy)
            .where(AiDataGovernancePolicy.organization_id == principal.organization_id)
            .order_by(AiDataGovernancePolicy.name)
        ).all()
    )


def _knowledge(db: Session, principal: Principal) -> list[AiKnowledgeSource]:
    return list(
        db.scalars(
            select(AiKnowledgeSource)
            .where(AiKnowledgeSource.organization_id == principal.organization_id)
            .order_by(AiKnowledgeSource.title)
        ).all()
    )


def _quality_rules(db: Session, principal: Principal) -> list[AiDataQualityRule]:
    return list(
        db.scalars(
            select(AiDataQualityRule)
            .where(AiDataQualityRule.organization_id == principal.organization_id)
            .order_by(AiDataQualityRule.name)
        ).all()
    )


def _copilot_read(
    item: AiCopilotDefinition,
    mappings: list[AiCopilotAgentMapping],
    contracts: list[AiCapabilityContract],
    agents: dict[Any, AiAgentDefinition],
) -> AiCopilotRead:
    return AiCopilotRead(
        id=item.id,
        key=item.key,
        name=item.name,
        description=item.description,
        human_owner_role_key=item.human_owner_role_key,
        human_owner_title=item.human_owner_title,
        human_authority_summary=item.human_authority_summary,
        status=item.status,
        phase_key=item.phase_key,
        approved_by_user_id=item.approved_by_user_id,
        approved_at=item.approved_at,
        specialist_mappings=[
            AiCopilotAgentMappingRead(
                id=mapping.id,
                agent_definition_id=mapping.agent_definition_id,
                agent_key=agents[mapping.agent_definition_id].key,
                agent_name=agents[mapping.agent_definition_id].name,
                purpose=mapping.purpose,
                display_order=mapping.display_order,
            )
            for mapping in mappings
            if mapping.agent_definition_id in agents
        ],
        capability_contracts=[_contract_read(contract) for contract in contracts],
        created_at=item.created_at,
    )


def _contract_read(item: AiCapabilityContract) -> AiCapabilityContractRead:
    return AiCapabilityContractRead(
        id=item.id,
        copilot_definition_id=item.copilot_definition_id,
        capability_key=item.capability_key,
        name=item.name,
        version_number=item.version_number,
        status=item.status,
        owner_role_key=item.owner_role_key,
        trigger_events=item.trigger_events,
        input_requirements=item.input_requirements,
        output_requirements=item.output_requirements,
        allowed_tool_scopes=item.allowed_tool_scopes,
        evidence_requirements=item.evidence_requirements,
        approval_policy=item.approval_policy,
        escalation_policy=item.escalation_policy,
        prohibited_actions=item.prohibited_actions,
        approved_by_user_id=item.approved_by_user_id,
        approved_at=item.approved_at,
        created_at=item.created_at,
    )


def _policy_read(item: AiDataGovernancePolicy) -> AiDataGovernancePolicyRead:
    return AiDataGovernancePolicyRead(
        id=item.id,
        key=item.key,
        name=item.name,
        data_category=item.data_category,
        field_scope=item.field_scope,
        version_number=item.version_number,
        status=item.status,
        source_precedence=item.source_precedence,
        overwrite_policy=item.overwrite_policy,
        redaction_rule=item.redaction_rule,
        retention_rule=item.retention_rule,
        permitted_role_keys=item.permitted_role_keys,
        approved_by_user_id=item.approved_by_user_id,
        approved_at=item.approved_at,
        created_at=item.created_at,
    )


def _knowledge_read(item: AiKnowledgeSource) -> AiKnowledgeSourceRead:
    return AiKnowledgeSourceRead(
        id=item.id,
        key=item.key,
        title=item.title,
        category=item.category,
        source_type=item.source_type,
        content_reference=item.content_reference,
        version_number=item.version_number,
        status=item.status,
        owner_role_key=item.owner_role_key,
        audience_role_keys=item.audience_role_keys,
        is_authoritative=item.is_authoritative,
        effective_at=item.effective_at,
        review_due_at=item.review_due_at,
        content_checksum=item.content_checksum,
        approved_by_user_id=item.approved_by_user_id,
        approved_at=item.approved_at,
        created_at=item.created_at,
    )


def _quality_rule_read(item: AiDataQualityRule) -> AiDataQualityRuleRead:
    return AiDataQualityRuleRead(
        id=item.id,
        key=item.key,
        name=item.name,
        record_type=item.record_type,
        field_scope=item.field_scope,
        rule_type=item.rule_type,
        severity=item.severity,
        is_deterministic=item.is_deterministic,
        configuration=item.configuration,
        resolution_action=item.resolution_action,
        version_number=item.version_number,
        status=item.status,
        approved_by_user_id=item.approved_by_user_id,
        approved_at=item.approved_at,
        created_at=item.created_at,
    )


def _audit(
    db: Session,
    principal: Principal,
    action: str,
    new_value: dict[str, object],
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type="organization",
            entity_id=principal.organization_id,
            previous_value=None,
            new_value=new_value,
            reason="AI1 copilot and data-governance control",
        )
    )
