from dataclasses import dataclass


class PermissionKeys:
    VIEW_LEADS = "leads:view"
    VIEW_ASSIGNED_LEADS = "leads:view_assigned"
    EDIT_LEADS = "leads:edit"
    VIEW_FINANCIALS = "financials:view"
    VIEW_COMPENSATION = "compensation:view"
    EDIT_UNDERWRITING = "underwriting:edit"
    APPROVE_ARV = "underwriting:approve_arv"
    APPROVE_OFFERS = "offers:approve"
    SEND_CONTRACTS = "contracts:send"
    MODIFY_CONTRACTS = "contracts:modify"
    RECORD_EXECUTED_CONTRACTS = "contracts:record_executed"
    EXPORT_BUYERS = "buyers:export"
    SEND_BULK_COMMUNICATIONS = "communications:send_bulk"
    ACCESS_RECORDINGS = "communications:access_recordings"
    MANAGE_RECORDINGS = "communications:manage_recordings"
    SEND_SMS = "communications:send_sms"
    SEND_ASSIGNED_SMS = "communications:send_assigned_sms"
    SEND_EMAIL = "communications:send_email"
    SEND_ASSIGNED_EMAIL = "communications:send_assigned_email"
    MANAGE_EMAIL_ACCOUNTS = "communications:manage_email_accounts"
    PLACE_CALLS = "communications:place_calls"
    PLACE_ASSIGNED_CALLS = "communications:place_assigned_calls"
    MANAGE_VOICE_LINES = "communications:manage_voice_lines"
    VIEW_CONVERSATIONS = "communications:view_conversations"
    VIEW_ASSIGNED_CONVERSATIONS = "communications:view_assigned_conversations"
    MANAGE_CONVERSATION_ASSIGNMENTS = "communications:manage_assignments"
    HANDOFF_ASSIGNED_CONVERSATIONS = "communications:handoff_assigned"
    LOG_ASSIGNED_COMMUNICATIONS = "communications:log_assigned"
    SCHEDULE_ASSIGNED_APPOINTMENTS = "appointments:schedule_assigned"
    CHANGE_AI_PROMPTS = "ai:change_prompts"
    CHANGE_COMPENSATION_RULES = "compensation:change_rules"
    MANAGE_ACCOUNTING_POLICY = "accounting:manage_policy"
    PREPARE_JOURNALS = "accounting:prepare_journals"
    APPROVE_JOURNALS = "accounting:approve_journals"
    POST_JOURNALS = "accounting:post_journals"
    MANAGE_ACCOUNTING_PERIODS = "accounting:manage_periods"
    MANAGE_VENDORS = "accounting:manage_vendors"
    MANAGE_FINANCE_EVIDENCE = "accounting:manage_evidence"
    MANAGE_BANKING = "accounting:manage_banking"
    DELETE_OR_ARCHIVE_RECORDS = "records:delete_or_archive"
    MANAGE_USERS = "users:manage"
    VIEW_AUDIT_LOGS = "audit:view"
    MANAGE_API_CREDENTIALS = "integrations:manage_credentials"
    MANAGE_PUBLIC_PROOF = "marketing:manage_public_proof"
    MANAGE_MARKETING_EXPERIMENTS = "marketing:manage_experiments"
    VIEW_BUYERS = "buyers:view"
    EDIT_BUYERS = "buyers:edit"
    VIEW_BUYER_PROOF = "buyers:view_proof"
    MANAGE_BUYER_PROOF = "buyers:manage_proof"
    VIEW_DEALS = "deals:view"
    EDIT_DEALS = "deals:edit"
    VIEW_DISPOSITION_PRIVATE_ECONOMICS = "dispositions:view_private_economics"
    APPROVE_DISPOSITION_PACKAGES = "dispositions:approve_packages"
    MANAGE_DISPOSITION_OUTREACH = "dispositions:manage_outreach"
    APPROVE_DISPOSITION_OUTREACH = "dispositions:approve_outreach"
    APPROVE_DISPOSITION_BUYER_SELECTION = "dispositions:approve_buyer_selection"
    SEND_DISPOSITION_BULK_OUTREACH = "dispositions:send_bulk_outreach"
    VIEW_ACQUISITION_OPERATIONS = "operations:view"
    MANAGE_ACQUISITION_OPERATIONS = "operations:manage"
    MANAGE_OPERATING_MODEL = "operating_model:manage"
    WORK_ASSIGNED_CALLING_LISTS = "calling_lists:work_assigned"


@dataclass(frozen=True)
class PermissionDefinition:
    key: str
    name: str
    description: str


@dataclass(frozen=True)
class RoleDefinition:
    key: str
    name: str
    permission_keys: tuple[str, ...]


PERMISSIONS: tuple[PermissionDefinition, ...] = (
    PermissionDefinition(PermissionKeys.VIEW_LEADS, "View leads", "View seller leads."),
    PermissionDefinition(
        PermissionKeys.VIEW_ASSIGNED_LEADS,
        "View assigned leads",
        "View only seller leads assigned to the current user.",
    ),
    PermissionDefinition(PermissionKeys.EDIT_LEADS, "Edit leads", "Create and update leads."),
    PermissionDefinition(
        PermissionKeys.VIEW_FINANCIALS, "View financials", "View revenue and expense data."
    ),
    PermissionDefinition(
        PermissionKeys.VIEW_COMPENSATION,
        "View compensation",
        "View compensation calculations and payment status.",
    ),
    PermissionDefinition(
        PermissionKeys.EDIT_UNDERWRITING,
        "Edit underwriting",
        "Create and update underwriting drafts.",
    ),
    PermissionDefinition(PermissionKeys.APPROVE_ARV, "Approve ARV", "Approve ARV values."),
    PermissionDefinition(
        PermissionKeys.APPROVE_OFFERS, "Approve offers", "Approve seller offer ranges."
    ),
    PermissionDefinition(
        PermissionKeys.SEND_CONTRACTS, "Send contracts", "Send approved contract envelopes."
    ),
    PermissionDefinition(
        PermissionKeys.MODIFY_CONTRACTS, "Modify contracts", "Modify contract records."
    ),
    PermissionDefinition(
        PermissionKeys.RECORD_EXECUTED_CONTRACTS,
        "Record executed contracts",
        "Adopt a fully executed agreement completed outside Stonegate.",
    ),
    PermissionDefinition(PermissionKeys.EXPORT_BUYERS, "Export buyers", "Export buyer data."),
    PermissionDefinition(
        PermissionKeys.SEND_BULK_COMMUNICATIONS,
        "Send bulk communications",
        "Send approved bulk campaigns.",
    ),
    PermissionDefinition(
        PermissionKeys.SEND_DISPOSITION_BULK_OUTREACH,
        "Send Dispositions bulk outreach",
        "Release approved buyer outreach from the Dispositions workbench.",
    ),
    PermissionDefinition(
        PermissionKeys.ACCESS_RECORDINGS,
        "Access recordings",
        "Access call recordings and related transcripts.",
    ),
    PermissionDefinition(
        PermissionKeys.MANAGE_RECORDINGS,
        "Manage recordings",
        "Delete call audio before its retention deadline and audit the reason.",
    ),
    PermissionDefinition(
        PermissionKeys.SEND_SMS,
        "Send SMS",
        "Send compliant one-to-one seller text messages.",
    ),
    PermissionDefinition(
        PermissionKeys.SEND_ASSIGNED_SMS,
        "Send assigned SMS",
        "Send compliant text messages only for assigned seller conversations.",
    ),
    PermissionDefinition(
        PermissionKeys.SEND_EMAIL,
        "Send email",
        "Send one-to-one seller email from a connected company mailbox.",
    ),
    PermissionDefinition(
        PermissionKeys.SEND_ASSIGNED_EMAIL,
        "Send assigned email",
        "Send seller email only for assigned conversations.",
    ),
    PermissionDefinition(
        PermissionKeys.MANAGE_EMAIL_ACCOUNTS,
        "Manage email accounts",
        "Manage connected company mailboxes, signatures, and shared email templates.",
    ),
    PermissionDefinition(
        PermissionKeys.PLACE_CALLS,
        "Place calls",
        "Place one-to-one seller calls from the browser softphone.",
    ),
    PermissionDefinition(
        PermissionKeys.PLACE_ASSIGNED_CALLS,
        "Place assigned calls",
        "Place seller calls only for assigned conversations.",
    ),
    PermissionDefinition(
        PermissionKeys.MANAGE_VOICE_LINES,
        "Manage voice lines",
        "Create and assign company-owned voice lines.",
    ),
    PermissionDefinition(
        PermissionKeys.VIEW_CONVERSATIONS,
        "View conversations",
        "View the shared company conversation inbox.",
    ),
    PermissionDefinition(
        PermissionKeys.VIEW_ASSIGNED_CONVERSATIONS,
        "View assigned conversations",
        "View only conversations assigned to the current user.",
    ),
    PermissionDefinition(
        PermissionKeys.MANAGE_CONVERSATION_ASSIGNMENTS,
        "Manage conversation assignments",
        "Assign and reassign conversations across the team.",
    ),
    PermissionDefinition(
        PermissionKeys.HANDOFF_ASSIGNED_CONVERSATIONS,
        "Handoff assigned conversations",
        "Handoff a currently assigned conversation to an eligible acquisition user.",
    ),
    PermissionDefinition(
        PermissionKeys.LOG_ASSIGNED_COMMUNICATIONS,
        "Log assigned communications",
        "Log calls, texts, and emails for assigned seller leads.",
    ),
    PermissionDefinition(
        PermissionKeys.SCHEDULE_ASSIGNED_APPOINTMENTS,
        "Schedule assigned appointments",
        "Schedule seller appointments for assigned leads.",
    ),
    PermissionDefinition(
        PermissionKeys.CHANGE_AI_PROMPTS,
        "Change AI prompts",
        "Create and promote AI prompt versions.",
    ),
    PermissionDefinition(
        PermissionKeys.CHANGE_COMPENSATION_RULES,
        "Change compensation rules",
        "Manage effective-dated compensation rules.",
    ),
    PermissionDefinition(
        PermissionKeys.MANAGE_ACCOUNTING_POLICY,
        "Manage accounting policy",
        "Manage the accounting profile and versioned chart of accounts.",
    ),
    PermissionDefinition(
        PermissionKeys.PREPARE_JOURNALS,
        "Prepare journals",
        "Prepare balanced accounting journals and linked reversals.",
    ),
    PermissionDefinition(
        PermissionKeys.APPROVE_JOURNALS,
        "Approve journals",
        "Approve balanced accounting journals for posting.",
    ),
    PermissionDefinition(
        PermissionKeys.POST_JOURNALS,
        "Post journals",
        "Post approved journals into an open accounting period.",
    ),
    PermissionDefinition(
        PermissionKeys.MANAGE_ACCOUNTING_PERIODS,
        "Manage accounting periods",
        "Open, review, close, lock, and reopen accounting periods.",
    ),
    PermissionDefinition(
        PermissionKeys.MANAGE_VENDORS,
        "Manage vendors and bills",
        "Manage vendor profiles, bills, bill approvals, and payment-state records.",
    ),
    PermissionDefinition(
        PermissionKeys.MANAGE_FINANCE_EVIDENCE,
        "Manage finance evidence",
        "Upload, access, and retire private accounting evidence including W-9 documents.",
    ),
    PermissionDefinition(
        PermissionKeys.MANAGE_BANKING,
        "Manage bank reconciliation",
        "Import statements, match bank transactions, and prepare reconciliations.",
    ),
    PermissionDefinition(
        PermissionKeys.DELETE_OR_ARCHIVE_RECORDS,
        "Delete or archive records",
        "Archive or delete records where allowed.",
    ),
    PermissionDefinition(PermissionKeys.MANAGE_USERS, "Manage users", "Manage user access."),
    PermissionDefinition(PermissionKeys.VIEW_AUDIT_LOGS, "View audit logs", "View audit events."),
    PermissionDefinition(
        PermissionKeys.MANAGE_API_CREDENTIALS,
        "Manage API credentials",
        "Manage integration credentials and health.",
    ),
    PermissionDefinition(
        PermissionKeys.MANAGE_PUBLIC_PROOF,
        "Manage public proof",
        "Prepare, review, publish, and retire evidence-backed public trust content.",
    ),
    PermissionDefinition(
        PermissionKeys.MANAGE_MARKETING_EXPERIMENTS,
        "Manage marketing experiments",
        "Prepare, launch, pause, and conclude controlled public-site experiments.",
    ),
    PermissionDefinition(PermissionKeys.VIEW_BUYERS, "View buyers", "View buyer records."),
    PermissionDefinition(PermissionKeys.EDIT_BUYERS, "Edit buyers", "Create and update buyers."),
    PermissionDefinition(
        PermissionKeys.VIEW_BUYER_PROOF,
        "View buyer proof of funds",
        "View and download restricted buyer proof-of-funds evidence.",
    ),
    PermissionDefinition(
        PermissionKeys.MANAGE_BUYER_PROOF,
        "Manage buyer proof of funds",
        "Upload, verify, reject, and maintain buyer proof-of-funds evidence.",
    ),
    PermissionDefinition(PermissionKeys.VIEW_DEALS, "View deals", "View deal records."),
    PermissionDefinition(PermissionKeys.EDIT_DEALS, "Edit deals", "Create and update deals."),
    PermissionDefinition(
        PermissionKeys.VIEW_DISPOSITION_PRIVATE_ECONOMICS,
        "View disposition private economics",
        "View purchase basis, release floors, and internal disposition economics.",
    ),
    PermissionDefinition(
        PermissionKeys.APPROVE_DISPOSITION_PACKAGES,
        "Approve disposition packages",
        "Attest to and approve immutable buyer-facing disposition packages.",
    ),
    PermissionDefinition(
        PermissionKeys.MANAGE_DISPOSITION_OUTREACH,
        "Manage disposition outreach",
        "Prepare and manage supervised buyer outreach without approving its release.",
    ),
    PermissionDefinition(
        PermissionKeys.APPROVE_DISPOSITION_OUTREACH,
        "Approve disposition outreach",
        "Approve immutable recipient and message revisions for supervised buyer outreach.",
    ),
    PermissionDefinition(
        PermissionKeys.APPROVE_DISPOSITION_BUYER_SELECTION,
        "Approve disposition buyer selection",
        "Approve primary buyers, ranked backups, and governed buyer replacements.",
    ),
    PermissionDefinition(
        PermissionKeys.VIEW_ACQUISITION_OPERATIONS,
        "View acquisition operations",
        "View team capacity, calling lists, notifications, and acquisition workflow controls.",
    ),
    PermissionDefinition(
        PermissionKeys.MANAGE_ACQUISITION_OPERATIONS,
        "Manage acquisition operations",
        "Manage teams, calling lists, duplicate review, saved views, and follow-up plans.",
    ),
    PermissionDefinition(
        PermissionKeys.MANAGE_OPERATING_MODEL,
        "Manage operating model",
        "Manage compensation policy, role credits, disposition modes, and market launch approval.",
    ),
    PermissionDefinition(
        PermissionKeys.WORK_ASSIGNED_CALLING_LISTS,
        "Work assigned calling lists",
        "View and update calling-list records assigned to the current user.",
    ),
)

ALL_PERMISSION_KEYS = tuple(permission.key for permission in PERMISSIONS)

ACQUISITION_KEYS = (
    PermissionKeys.VIEW_LEADS,
    PermissionKeys.EDIT_LEADS,
    PermissionKeys.EDIT_UNDERWRITING,
    PermissionKeys.VIEW_DEALS,
    PermissionKeys.VIEW_CONVERSATIONS,
    PermissionKeys.SEND_SMS,
    PermissionKeys.SEND_EMAIL,
    PermissionKeys.PLACE_CALLS,
    PermissionKeys.ACCESS_RECORDINGS,
)

DISPOSITION_KEYS = (
    PermissionKeys.VIEW_DEALS,
    PermissionKeys.EDIT_DEALS,
    PermissionKeys.VIEW_DISPOSITION_PRIVATE_ECONOMICS,
    PermissionKeys.VIEW_BUYERS,
    PermissionKeys.EDIT_BUYERS,
    PermissionKeys.VIEW_BUYER_PROOF,
    PermissionKeys.MANAGE_BUYER_PROOF,
    PermissionKeys.VIEW_CONVERSATIONS,
    PermissionKeys.SEND_SMS,
    PermissionKeys.SEND_EMAIL,
    PermissionKeys.PLACE_CALLS,
    PermissionKeys.ACCESS_RECORDINGS,
    PermissionKeys.MANAGE_DISPOSITION_OUTREACH,
    PermissionKeys.APPROVE_DISPOSITION_PACKAGES,
    PermissionKeys.APPROVE_DISPOSITION_OUTREACH,
    PermissionKeys.APPROVE_DISPOSITION_BUYER_SELECTION,
    PermissionKeys.SEND_DISPOSITION_BULK_OUTREACH,
)

ROLES: tuple[RoleDefinition, ...] = (
    RoleDefinition("owner", "Owner", ALL_PERMISSION_KEYS),
    RoleDefinition("founder_operator", "Founder/operator", ALL_PERMISSION_KEYS),
    RoleDefinition(
        "ceo",
        "CEO",
        tuple(key for key in ALL_PERMISSION_KEYS if key != PermissionKeys.MANAGE_API_CREDENTIALS),
    ),
    RoleDefinition(
        "administrator",
        "Administrator",
        (
            PermissionKeys.VIEW_LEADS,
            PermissionKeys.EDIT_LEADS,
            PermissionKeys.MANAGE_USERS,
            PermissionKeys.VIEW_AUDIT_LOGS,
            PermissionKeys.DELETE_OR_ARCHIVE_RECORDS,
            PermissionKeys.VIEW_ACQUISITION_OPERATIONS,
            PermissionKeys.MANAGE_ACQUISITION_OPERATIONS,
        ),
    ),
    RoleDefinition(
        "acquisition_manager",
        "Acquisition manager",
        (
            *ACQUISITION_KEYS,
            PermissionKeys.APPROVE_ARV,
            PermissionKeys.APPROVE_OFFERS,
            PermissionKeys.RECORD_EXECUTED_CONTRACTS,
            PermissionKeys.MANAGE_CONVERSATION_ASSIGNMENTS,
            PermissionKeys.MANAGE_EMAIL_ACCOUNTS,
            PermissionKeys.VIEW_ACQUISITION_OPERATIONS,
            PermissionKeys.MANAGE_ACQUISITION_OPERATIONS,
        ),
    ),
    RoleDefinition(
        "acquisition_rep",
        "Acquisition representative",
        (
            *ACQUISITION_KEYS,
            PermissionKeys.RECORD_EXECUTED_CONTRACTS,
            PermissionKeys.VIEW_ACQUISITION_OPERATIONS,
        ),
    ),
    RoleDefinition(
        "operations_assistant",
        "Operations assistant",
        (
            *ACQUISITION_KEYS,
            PermissionKeys.EDIT_DEALS,
            PermissionKeys.VIEW_BUYERS,
            PermissionKeys.EDIT_BUYERS,
            PermissionKeys.VIEW_ACQUISITION_OPERATIONS,
        ),
    ),
    RoleDefinition(
        "prospecting_caller",
        "Prospecting caller",
        (
            PermissionKeys.VIEW_ASSIGNED_LEADS,
            PermissionKeys.VIEW_ASSIGNED_CONVERSATIONS,
            PermissionKeys.HANDOFF_ASSIGNED_CONVERSATIONS,
            PermissionKeys.LOG_ASSIGNED_COMMUNICATIONS,
            PermissionKeys.SEND_ASSIGNED_SMS,
            PermissionKeys.SEND_ASSIGNED_EMAIL,
            PermissionKeys.PLACE_ASSIGNED_CALLS,
            PermissionKeys.SCHEDULE_ASSIGNED_APPOINTMENTS,
            PermissionKeys.ACCESS_RECORDINGS,
            PermissionKeys.VIEW_ACQUISITION_OPERATIONS,
            PermissionKeys.WORK_ASSIGNED_CALLING_LISTS,
        ),
    ),
    RoleDefinition(
        "disposition_manager",
        "Disposition manager",
        (
            *DISPOSITION_KEYS,
            PermissionKeys.EXPORT_BUYERS,
        ),
    ),
    RoleDefinition("disposition_rep", "Disposition representative", DISPOSITION_KEYS),
    RoleDefinition(
        "transaction_coordinator",
        "Transaction coordinator",
        (
            PermissionKeys.VIEW_DEALS,
            PermissionKeys.EDIT_DEALS,
            PermissionKeys.SEND_CONTRACTS,
            PermissionKeys.MODIFY_CONTRACTS,
            PermissionKeys.RECORD_EXECUTED_CONTRACTS,
            PermissionKeys.VIEW_CONVERSATIONS,
            PermissionKeys.SEND_EMAIL,
        ),
    ),
    RoleDefinition(
        "marketing_manager",
        "Marketing manager",
        (
            PermissionKeys.VIEW_LEADS,
            PermissionKeys.SEND_BULK_COMMUNICATIONS,
            PermissionKeys.MANAGE_PUBLIC_PROOF,
            PermissionKeys.MANAGE_MARKETING_EXPERIMENTS,
        ),
    ),
    RoleDefinition(
        "finance_accounting",
        "Finance/accounting",
        (
            PermissionKeys.VIEW_FINANCIALS,
            PermissionKeys.VIEW_COMPENSATION,
            PermissionKeys.CHANGE_COMPENSATION_RULES,
            PermissionKeys.MANAGE_ACCOUNTING_POLICY,
            PermissionKeys.PREPARE_JOURNALS,
            PermissionKeys.APPROVE_JOURNALS,
            PermissionKeys.POST_JOURNALS,
            PermissionKeys.MANAGE_ACCOUNTING_PERIODS,
            PermissionKeys.MANAGE_VENDORS,
            PermissionKeys.MANAGE_FINANCE_EVIDENCE,
            PermissionKeys.MANAGE_BANKING,
            PermissionKeys.VIEW_CONVERSATIONS,
            PermissionKeys.SEND_EMAIL,
        ),
    ),
    RoleDefinition("read_only_partner", "Read-only partner", (PermissionKeys.VIEW_DEALS,)),
    RoleDefinition("restricted_vendor", "Restricted attorney/vendor", (PermissionKeys.VIEW_DEALS,)),
    RoleDefinition("ai_service", "AI service identity", (PermissionKeys.VIEW_LEADS,)),
)
