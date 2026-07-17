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
    EXPORT_BUYERS = "buyers:export"
    SEND_BULK_COMMUNICATIONS = "communications:send_bulk"
    ACCESS_RECORDINGS = "communications:access_recordings"
    VIEW_CONVERSATIONS = "communications:view_conversations"
    VIEW_ASSIGNED_CONVERSATIONS = "communications:view_assigned_conversations"
    MANAGE_CONVERSATION_ASSIGNMENTS = "communications:manage_assignments"
    HANDOFF_ASSIGNED_CONVERSATIONS = "communications:handoff_assigned"
    LOG_ASSIGNED_COMMUNICATIONS = "communications:log_assigned"
    SCHEDULE_ASSIGNED_APPOINTMENTS = "appointments:schedule_assigned"
    CHANGE_AI_PROMPTS = "ai:change_prompts"
    CHANGE_COMPENSATION_RULES = "compensation:change_rules"
    DELETE_OR_ARCHIVE_RECORDS = "records:delete_or_archive"
    MANAGE_USERS = "users:manage"
    VIEW_AUDIT_LOGS = "audit:view"
    MANAGE_API_CREDENTIALS = "integrations:manage_credentials"
    VIEW_BUYERS = "buyers:view"
    EDIT_BUYERS = "buyers:edit"
    VIEW_DEALS = "deals:view"
    EDIT_DEALS = "deals:edit"


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
    PermissionDefinition(PermissionKeys.EXPORT_BUYERS, "Export buyers", "Export buyer data."),
    PermissionDefinition(
        PermissionKeys.SEND_BULK_COMMUNICATIONS,
        "Send bulk communications",
        "Send approved bulk campaigns.",
    ),
    PermissionDefinition(
        PermissionKeys.ACCESS_RECORDINGS,
        "Access recordings",
        "Access call recordings and related transcripts.",
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
    PermissionDefinition(PermissionKeys.VIEW_BUYERS, "View buyers", "View buyer records."),
    PermissionDefinition(PermissionKeys.EDIT_BUYERS, "Edit buyers", "Create and update buyers."),
    PermissionDefinition(PermissionKeys.VIEW_DEALS, "View deals", "View deal records."),
    PermissionDefinition(PermissionKeys.EDIT_DEALS, "Edit deals", "Create and update deals."),
)

ALL_PERMISSION_KEYS = tuple(permission.key for permission in PERMISSIONS)

ACQUISITION_KEYS = (
    PermissionKeys.VIEW_LEADS,
    PermissionKeys.EDIT_LEADS,
    PermissionKeys.EDIT_UNDERWRITING,
    PermissionKeys.VIEW_DEALS,
    PermissionKeys.VIEW_CONVERSATIONS,
)

DISPOSITION_KEYS = (
    PermissionKeys.VIEW_DEALS,
    PermissionKeys.EDIT_DEALS,
    PermissionKeys.VIEW_BUYERS,
    PermissionKeys.EDIT_BUYERS,
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
        ),
    ),
    RoleDefinition(
        "acquisition_manager",
        "Acquisition manager",
        (
            *ACQUISITION_KEYS,
            PermissionKeys.APPROVE_ARV,
            PermissionKeys.APPROVE_OFFERS,
            PermissionKeys.MANAGE_CONVERSATION_ASSIGNMENTS,
        ),
    ),
    RoleDefinition("acquisition_rep", "Acquisition representative", ACQUISITION_KEYS),
    RoleDefinition(
        "prospecting_caller",
        "Prospecting caller",
        (
            PermissionKeys.VIEW_ASSIGNED_LEADS,
            PermissionKeys.VIEW_ASSIGNED_CONVERSATIONS,
            PermissionKeys.HANDOFF_ASSIGNED_CONVERSATIONS,
            PermissionKeys.LOG_ASSIGNED_COMMUNICATIONS,
            PermissionKeys.SCHEDULE_ASSIGNED_APPOINTMENTS,
        ),
    ),
    RoleDefinition(
        "disposition_manager",
        "Disposition manager",
        (*DISPOSITION_KEYS, PermissionKeys.EXPORT_BUYERS),
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
        ),
    ),
    RoleDefinition(
        "marketing_manager",
        "Marketing manager",
        (PermissionKeys.VIEW_LEADS, PermissionKeys.SEND_BULK_COMMUNICATIONS),
    ),
    RoleDefinition(
        "finance_accounting",
        "Finance/accounting",
        (
            PermissionKeys.VIEW_FINANCIALS,
            PermissionKeys.VIEW_COMPENSATION,
            PermissionKeys.CHANGE_COMPENSATION_RULES,
        ),
    ),
    RoleDefinition("read_only_partner", "Read-only partner", (PermissionKeys.VIEW_DEALS,)),
    RoleDefinition("restricted_vendor", "Restricted attorney/vendor", (PermissionKeys.VIEW_DEALS,)),
    RoleDefinition("ai_service", "AI service identity", (PermissionKeys.VIEW_LEADS,)),
)
