import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class Organization(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class User(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("organization_id", "email", name="uq_users_org_email"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    external_auth_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class Role(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("organization_id", "key", name="uq_roles_org_key"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class Permission(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "permissions"

    key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)


class RolePermission(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_permission"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("roles.id"))
    permission_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("permissions.id"))


class RoleAssignment(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "role_assignments"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_role_assignments_user_role"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("roles.id"))


class Team(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_teams_org_name"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    team_type: Mapped[str] = mapped_column(String(80), nullable=False)
    manager_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class TeamMembership(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "team_memberships"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_memberships_team_user"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    team_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("teams.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    membership_role: Mapped[str] = mapped_column(String(80), nullable=False)


class Market(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "markets"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_markets_org_code"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class Territory(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "territories"
    __table_args__ = (UniqueConstraint("market_id", "code", name="uq_territories_market_code"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    market_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("markets.id"), index=True)
    assigned_team_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("teams.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    county_names: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    postal_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class Campaign(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "campaigns"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_campaigns_org_code"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    market_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("markets.id"), index=True)
    territory_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("territories.id"), index=True
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    channel: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    starts_on: Mapped[date | None] = mapped_column(nullable=True)
    ends_on: Mapped[date | None] = mapped_column(nullable=True)
    budget_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class Prospect(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prospects"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "source_record_key",
            name="uq_prospects_campaign_source_record",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("campaigns.id"), index=True)
    territory_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("territories.id"), index=True
    )
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), index=True
    )
    converted_lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id"), index=True
    )
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prospect_import_batches.id"), index=True
    )
    source_record_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    normalized_phone: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    normalized_email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    street_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    normalized_address_key: Mapped[str | None] = mapped_column(
        String(500), nullable=True, index=True
    )
    suppression_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    suppression_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    phone_validation_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="unverified", server_default="unverified", index=True
    )
    address_validation_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="unverified", server_default="unverified", index=True
    )
    call_eligibility: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="review_required",
        server_default="review_required",
        index=True,
    )
    last_contacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ProspectImportMapping(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prospect_import_mappings"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_prospect_import_mappings_org_name"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    field_mapping: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    default_values: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class ProspectImportBatch(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prospect_import_batches"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("campaigns.id"), index=True)
    mapping_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("prospect_import_mappings.id"), index=True
    )
    default_assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), index=True
    )
    imported_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    invalid_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicate_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    suppressed_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    review_required_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProspectImportRow(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prospect_import_rows"
    __table_args__ = (
        UniqueConstraint("import_batch_id", "row_number", name="uq_prospect_import_rows_batch_row"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    import_batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("prospect_import_batches.id", ondelete="CASCADE"), index=True
    )
    prospect_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prospects.id"), index=True
    )
    duplicate_prospect_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prospects.id"), index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    normalized_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    validation_errors: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    eligibility_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class ProspectSuppressionCheck(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prospect_suppression_checks"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    import_row_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prospect_import_rows.id", ondelete="CASCADE"), index=True
    )
    prospect_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prospects.id"), index=True
    )
    check_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(String(320), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CampaignCost(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "campaign_costs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("campaigns.id"), index=True)
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prospect_import_batches.id"), index=True
    )
    worker_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), index=True
    )
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    vendor_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    labor_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hourly_rate_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    incurred_on: Mapped[date] = mapped_column(nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))


class ProspectCallingBatch(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prospect_calling_batches"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_prospect_calling_batches_org_name"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("campaigns.id"), index=True)
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prospect_import_batches.id"), index=True
    )
    assigned_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class ProspectCallingBatchEntry(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prospect_calling_batch_entries"
    __table_args__ = (
        UniqueConstraint(
            "prospect_calling_batch_id",
            "prospect_id",
            name="uq_prospect_calling_batch_entries_batch_prospect",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    prospect_calling_batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("prospect_calling_batches.id", ondelete="CASCADE"), index=True
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("prospects.id"), index=True)
    assigned_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    disposition: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProspectingScriptVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prospecting_script_versions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "version_number",
            name="uq_prospecting_scripts_org_version",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    opening_script: Mapped[str] = mapped_column(Text, nullable=False)
    qualification_questions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    disposition_rules: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProspectingAttempt(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prospecting_attempts"
    __table_args__ = (
        Index(
            "uq_prospecting_attempts_active_caller",
            "organization_id",
            "caller_user_id",
            unique=True,
            postgresql_where=text("status = 'in_progress'"),
            sqlite_where=text("status = 'in_progress'"),
        ),
        Index(
            "uq_prospecting_attempts_active_entry",
            "batch_entry_id",
            unique=True,
            postgresql_where=text("status = 'in_progress'"),
            sqlite_where=text("status = 'in_progress'"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    batch_entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("prospect_calling_batch_entries.id", ondelete="CASCADE"), index=True
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("prospects.id"), index=True)
    caller_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    script_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("prospecting_script_versions.id"), index=True
    )
    call_record_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("call_records.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    outcome: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    contact_made: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    qualification_answers: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    callback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    required_answer_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    answered_required_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    quality_score_basis_points: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ProspectHandoff(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prospect_handoffs"
    __table_args__ = (UniqueConstraint("attempt_id", name="uq_prospect_handoffs_attempt"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("prospects.id"), index=True)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("prospecting_attempts.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    assigned_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    submitted_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), index=True
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class LeadQualificationScriptVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lead_qualification_script_versions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "version_number",
            name="uq_lead_qualification_scripts_org_version",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    introduction: Mapped[str] = mapped_column(Text, nullable=False)
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    completion_rules: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LeadManagementCase(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lead_management_cases"
    __table_args__ = (UniqueConstraint("lead_id", name="uq_lead_management_cases_lead"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    handoff_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prospect_handoffs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    acceptance_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    qualification_script_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("lead_qualification_script_versions.id"), nullable=True, index=True
    )
    qualification_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    qualification_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    qualification_quality_basis_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_action_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    next_action_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LeadQualificationSession(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lead_qualification_sessions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("lead_management_cases.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    script_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("lead_qualification_script_versions.id"), index=True
    )
    completed_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    answers: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    missing_required_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    quality_score_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    next_action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    next_action_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Contact(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contacts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    preferred_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_type: Mapped[str] = mapped_column(String(80), nullable=False)
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))


class ContactMethod(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contact_methods"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contacts.id"), index=True)
    method_type: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(320), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class Property(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "properties"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    street_address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    county: Mapped[str | None] = mapped_column(String(120), nullable=True)
    property_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    normalized_address_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    address_validation_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="unverified", server_default="unverified"
    )
    address_validation_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provider_property_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    validated_formatted_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    address_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    address_validation_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class Lead(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leads"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contacts.id"))
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"))
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    stage_key: Mapped[str] = mapped_column(String(120), nullable=False)
    lead_temperature: Mapped[str | None] = mapped_column(String(80), nullable=True)
    motivation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    desired_timeline: Mapped[str | None] = mapped_column(String(120), nullable=True)
    property_condition: Mapped[str | None] = mapped_column(String(120), nullable=True)
    occupancy_status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    asking_price: Mapped[str | None] = mapped_column(String(120), nullable=True)
    mortgage_balance: Mapped[str | None] = mapped_column(String(120), nullable=True)
    appointment_status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class ConsentRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "consent_records"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contacts.id"), index=True)
    channel: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    wording_version: Mapped[str] = mapped_column(String(80), nullable=False)
    wording: Mapped[str] = mapped_column(String(1000), nullable=False)
    captured_ip: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)


class SuppressionRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "suppression_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "channel",
            "normalized_address",
            name="uq_suppression_records_org_channel_address",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    normalized_address: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    suppressed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lifted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suppression_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )


class LeadFormSubmission(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lead_form_submissions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"))
    landing_page: Mapped[str | None] = mapped_column(String(255), nullable=True)
    referrer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class AttributionTouch(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "attribution_touches"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    touch_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    medium: Mapped[str | None] = mapped_column(String(120), nullable=True)
    campaign: Mapped[str | None] = mapped_column(String(255), nullable=True)
    term: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gclid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fbclid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    landing_page: Mapped[str | None] = mapped_column(String(255), nullable=True)
    referrer: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ConversionEvent(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversion_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    landing_page: Mapped[str | None] = mapped_column(String(255), nullable=True)
    referrer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    medium: Mapped[str | None] = mapped_column(String(120), nullable=True)
    campaign: Mapped[str | None] = mapped_column(String(255), nullable=True)
    term: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gclid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fbclid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)


class Conversation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("organization_id", "lead_id", name="uq_conversations_org_lead"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contacts.id"), index=True)
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    queue_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(80), nullable=False)
    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_outbound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    conversation_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )


class ConversationWatcher(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversation_watchers"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "user_id",
            name="uq_conversation_watchers_conversation_user",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    notification_level: Mapped[str] = mapped_column(String(80), nullable=False)
    is_muted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class ConversationAssignmentEvent(UuidPrimaryKeyMixin, Base):
    __tablename__ = "conversation_assignment_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    previous_assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id")
    )
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    previous_queue_key: Mapped[str] = mapped_column(String(120), nullable=False)
    queue_key: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CommunicationProviderEvent(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "communication_provider_events"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "external_event_id",
            name="uq_provider_events_org_provider_external",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class CommunicationRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "communication_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "provider_message_id",
            name="uq_communication_records_org_provider_message",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contacts.id"), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    direction: Mapped[str] = mapped_column(String(40), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    external_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    communication_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )


class CommunicationDispatch(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "communication_dispatches"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_communication_dispatches_org_idempotency",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contacts.id"), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    communication_record_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("communication_records.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    request_body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatch_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )


class EmailAccount(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_accounts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "email_address",
            name="uq_email_accounts_org_provider_address",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    connected_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_account_id: Mapped[str] = mapped_column(String(320), nullable=False)
    email_address: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    sync_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    encrypted_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    history_cursor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    signature_text: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    account_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)


class EmailTemplate(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_templates"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "name",
            name="uq_email_templates_org_name",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    subject_template: Mapped[str] = mapped_column(String(255), nullable=False)
    body_template: Mapped[str] = mapped_column(String(4000), nullable=False)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class EmailAttachment(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_attachments"
    __table_args__ = (
        UniqueConstraint(
            "communication_record_id",
            "provider_attachment_id",
            name="uq_email_attachments_communication_provider_id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    communication_record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("communication_records.id", ondelete="CASCADE"), index=True
    )
    email_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("email_accounts.id", ondelete="CASCADE"), index=True
    )
    provider_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_attachment_id: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    disposition: Mapped[str] = mapped_column(String(40), nullable=False)
    attachment_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )


class VoiceLine(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "voice_lines"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "phone_number",
            name="uq_voice_lines_org_phone_number",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), index=True
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_phone_number_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    inbound_route: Mapped[str] = mapped_column(String(80), nullable=False)
    line_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)


class VoiceCallIntent(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "voice_call_intents"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_voice_call_intents_org_idempotency",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contacts.id"), index=True)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    voice_line_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("voice_lines.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    recipient: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    recording_consent_status: Mapped[str] = mapped_column(String(80), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    intent_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)


class CallRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "call_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "provider_call_id",
            name="uq_call_records_org_provider_call",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contacts.id"), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    communication_record_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("communication_records.id", ondelete="SET NULL")
    )
    voice_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("voice_lines.id", ondelete="SET NULL"), index=True
    )
    call_intent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("voice_call_intents.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    child_provider_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    direction: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    from_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    to_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disposition: Mapped[str | None] = mapped_column(String(120), nullable=True)
    recording_consent_status: Mapped[str] = mapped_column(
        String(80), nullable=False, server_default="not_requested"
    )
    call_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)


class CallRecording(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "call_recordings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "provider_recording_id",
            name="uq_call_recordings_org_provider_recording",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    call_record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("call_records.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_recording_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    media_reference: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consent_status: Mapped[str] = mapped_column(String(80), nullable=False)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retention_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    deletion_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    recording_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )


class CallTranscript(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "call_transcripts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    recording_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("call_recordings.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    language: Mapped[str | None] = mapped_column(String(40), nullable=True)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    speaker_segments: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    confidence_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    transcript_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )


class Appointment(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "appointments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contacts.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    appointment_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    scheduled_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    location_type: Mapped[str] = mapped_column(String(80), nullable=False)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    external_calendar_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    appointment_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )


class CalendarEvent(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "calendar_events"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "appointment_id",
            "provider",
            name="uq_calendar_events_org_appointment_provider",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("appointments.id", ondelete="CASCADE"), index=True
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    event_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CloserDispatchProfile(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "closer_dispatch_profiles"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_closer_dispatch_profiles_org_user",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    working_days: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    workday_start_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    workday_end_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    default_appointment_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    travel_buffer_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    home_base_postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    territory_enforcement_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class CloserTerritoryCoverage(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "closer_territory_coverages"
    __table_args__ = (
        UniqueConstraint(
            "dispatch_profile_id",
            "territory_id",
            name="uq_closer_territory_coverages_profile_territory",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    dispatch_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("closer_dispatch_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    territory_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("territories.id", ondelete="CASCADE"), index=True
    )


class CloserAvailabilityBlock(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "closer_availability_blocks"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    dispatch_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("closer_dispatch_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    block_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))


class AppointmentDispatchRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "appointment_dispatch_records"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("appointments.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    closer_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    territory_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("territories.id", ondelete="SET NULL"), index=True
    )
    decided_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    decision_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    scheduled_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    daily_booked_count: Mapped[int] = mapped_column(Integer, nullable=False)
    travel_buffer_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    territory_match: Mapped[bool] = mapped_column(Boolean, nullable=False)
    violations: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    candidate_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    decision_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class FieldMeetingBrief(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "field_meeting_briefs"
    __table_args__ = (
        UniqueConstraint(
            "appointment_id", "version_number", name="uq_field_meeting_briefs_appointment_version"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("appointments.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    generated_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    brief_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class FieldInspection(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "field_inspections"
    __table_args__ = (UniqueConstraint("appointment_id", name="uq_field_inspections_appointment"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("appointments.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    inspector_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    overall_condition: Mapped[str | None] = mapped_column(String(80), nullable=True)
    occupancy_observed: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utilities_status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    access_notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    title_concerns: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    safety_concerns: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    room_observations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    repair_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    inspector_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class FieldInspectionPhoto(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "field_inspection_photos"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("field_inspections.id", ondelete="CASCADE"), index=True
    )
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    area: Mapped[str] = mapped_column(String(120), nullable=False)
    caption: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    image_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class FieldNegotiationSession(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "field_negotiation_sessions"
    __table_args__ = (
        UniqueConstraint("appointment_id", name="uq_field_negotiation_sessions_appointment"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("appointments.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    recorded_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    decision_makers_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    decision_makers: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    seller_asking_price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    offer_presented_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    seller_counter_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    agreed_price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    approved_ceiling_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    objections: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    commitments: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    outcome: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class FieldUnderwritingTransfer(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "field_underwriting_transfers"
    __table_args__ = (
        UniqueConstraint("inspection_id", name="uq_field_underwriting_transfers_inspection"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("field_inspections.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    reviewed_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    source_underwriting_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("underwriting_versions.id"), nullable=True
    )
    repair_estimate_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("repair_estimates.id"), nullable=True
    )
    created_underwriting_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("underwriting_versions.id"), index=True
    )
    transfer_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class UnderwritingVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "underwriting_versions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    arv_low_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    arv_high_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    repair_low_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    repair_high_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    max_offer_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    recommended_offer_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    offer_strategy: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    underwriting_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )


class UnderwritingMarketAnalysis(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "underwriting_market_analyses"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    underwriting_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("underwriting_versions.id"), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    requested_address: Mapped[str] = mapped_column(String(500), nullable=False)
    estimated_value_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    estimated_value_low_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    estimated_value_high_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    arv_low_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    arv_high_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    repair_low_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    repair_high_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mao_low_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mao_high_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    recommended_offer_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    assignment_fee_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    offer_low_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    offer_high_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_comp_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_comp_count: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_comps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    rejected_comps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    subject_property: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    raw_response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    analysis_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )


class UnderwritingCalibrationCase(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "underwriting_calibration_cases"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "analysis_id",
            name="uq_underwriting_calibration_org_analysis",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("underwriting_market_analyses.id"), index=True
    )
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    market_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    benchmark_type: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    benchmark_arv_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_rehab_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actual_seller_contract_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actual_disposition_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    predicted_arv_low_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    predicted_arv_point_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    predicted_arv_high_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    predicted_rehab_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    predicted_seller_ceiling_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    predicted_disposition_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    evidence_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class RepairEstimate(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "repair_estimates"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    source_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    contractor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estimate_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scope_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    subtotal_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    contingency_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    contingency_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    evidence_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class OfferNegotiationPlan(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offer_negotiation_plans"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    underwriting_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("underwriting_versions.id"), index=True
    )
    market_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("underwriting_market_analyses.id"), nullable=True, index=True
    )
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("approval_requests.id"), nullable=True, index=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    seller_asking_price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    arv_low_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    arv_point_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    arv_high_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_rehab_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    disposition_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    opening_offer_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_contract_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stretch_contract_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    seller_ceiling_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    seller_context: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    rationale: Mapped[str] = mapped_column(String(2000), nullable=False)
    source_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class Deal(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deals"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"))
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"))
    stage_key: Mapped[str] = mapped_column(String(120), nullable=False)
    contract_price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    assignment_fee_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class Transaction(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transactions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    deal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("deals.id"), index=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contacts.id"), index=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    compensation_plan_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("compensation_plan_versions.id"), index=True
    )
    disposition_operating_mode_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("disposition_operating_modes.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    contract_type: Mapped[str] = mapped_column(String(120), nullable=False)
    purchase_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    assignment_fee_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    earnest_money_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    title_company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    closing_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    inspection_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contract_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    contract_executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    transaction_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )


class TransactionChecklistItem(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transaction_checklist_items"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.id"), index=True
    )
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class Buyer(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "buyers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    buyer_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    proof_of_funds_status: Mapped[str] = mapped_column(String(80), nullable=False)
    max_purchase_price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class BuyerCriteria(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "buyer_criteria"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    buyer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("buyers.id"), index=True)
    markets: Mapped[str | None] = mapped_column(String(500), nullable=True)
    property_types: Mapped[str | None] = mapped_column(String(500), nullable=True)
    min_price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    max_price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    rehab_levels: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class BuyerOffer(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "buyer_offers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("deals.id"), index=True)
    buyer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("buyers.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    earnest_money_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    financing_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    proof_of_funds_received: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RevenueRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "revenue_records"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("deals.id"), index=True)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transactions.id"), index=True
    )
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class DealDeduction(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deal_deductions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("deals.id"), index=True)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transactions.id"), index=True
    )
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    incurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class CompensationPlanVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compensation_plan_versions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "name",
            "version_number",
            name="uq_compensation_plan_versions_org_name_version",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    acquisition_reserve_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_company_margin_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    effective_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class CompensationPlanRole(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compensation_plan_roles"
    __table_args__ = (
        UniqueConstraint(
            "compensation_plan_version_id",
            "role_key",
            name="uq_compensation_plan_roles_plan_role",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    compensation_plan_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("compensation_plan_versions.id", ondelete="CASCADE"), index=True
    )
    role_key: Mapped[str] = mapped_column(String(120), nullable=False)
    basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    cap_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class DispositionOperatingMode(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "disposition_operating_modes"
    __table_args__ = (
        UniqueConstraint(
            "compensation_plan_version_id",
            "key",
            name="uq_disposition_operating_modes_plan_key",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    compensation_plan_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("compensation_plan_versions.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    human_share_min_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    human_share_max_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_company_share_min_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_company_share_max_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_authority_level: Mapped[str] = mapped_column(String(80), nullable=False)
    activation_requirements: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class RoleCredit(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "role_credits"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    compensation_plan_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("compensation_plan_versions.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("deals.id"), index=True)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transactions.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    role_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    credit_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    assigned_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class MarketLaunchChecklist(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "market_launch_checklists"
    __table_args__ = (
        UniqueConstraint(
            "market_id",
            "version_number",
            name="uq_market_launch_checklists_market_version",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    market_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("markets.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class MarketLaunchChecklistItem(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "market_launch_checklist_items"
    __table_args__ = (
        UniqueConstraint(
            "market_launch_checklist_id",
            "item_key",
            name="uq_market_launch_checklist_items_checklist_key",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    market_launch_checklist_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("market_launch_checklists.id", ondelete="CASCADE"), index=True
    )
    item_key: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    evidence_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class CompensationRule(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compensation_rules"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    compensation_plan_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("compensation_plan_versions.id"), index=True
    )
    compensation_plan_role_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("compensation_plan_roles.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_key: Mapped[str] = mapped_column(String(120), nullable=False)
    basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    applies_to: Mapped[str] = mapped_column(String(120), nullable=False)
    effective_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class CompensationCalculation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compensation_calculations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    revenue_record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("revenue_records.id"), index=True
    )
    compensation_rule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("compensation_rules.id"), index=True
    )
    role_key: Mapped[str] = mapped_column(String(120), nullable=False)
    basis_amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    calculated_amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class MarketingSpend(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "marketing_spend"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    campaign: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    spend_month_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class OfflineConversionExport(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offline_conversion_exports"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "platform",
            "revenue_record_id",
            name="uq_offline_exports_org_platform_revenue",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    platform: Mapped[str] = mapped_column(String(80), nullable=False)
    conversion_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversion_events.id"), index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    revenue_record_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("revenue_records.id"), index=True
    )
    event_name: Mapped[str] = mapped_column(String(120), nullable=False)
    click_id: Mapped[str] = mapped_column(String(255), nullable=False)
    click_id_type: Mapped[str] = mapped_column(String(80), nullable=False)
    value_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class ApprovalRequest(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "approval_requests"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    request_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(String(2000), nullable=False)
    decision_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )


class AiAgentDefinition(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_agent_definitions"
    __table_args__ = (UniqueConstraint("organization_id", "key", name="uq_ai_agents_org_key"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(80), nullable=False)
    requires_human_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )


class AiPromptVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_prompt_versions"
    __table_args__ = (
        UniqueConstraint(
            "agent_definition_id",
            "version_number",
            name="uq_ai_prompt_versions_agent_version",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    agent_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_agent_definitions.id"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_text: Mapped[str] = mapped_column(String(8000), nullable=False)
    change_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))


class AiToolPermission(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_tool_permissions"
    __table_args__ = (
        UniqueConstraint(
            "agent_definition_id",
            "tool_key",
            name="uq_ai_tool_permissions_agent_tool",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    agent_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_agent_definitions.id"), index=True
    )
    tool_key: Mapped[str] = mapped_column(String(160), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    permission_level: Mapped[str] = mapped_column(String(80), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class AiRunLog(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_run_logs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    agent_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_agent_definitions.id"), index=True
    )
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_prompt_versions.id"), index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    input_summary: Mapped[str] = mapped_column(String(4000), nullable=False)
    output_summary: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cost_microusd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    run_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)


class AiToolCallLog(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_tool_call_logs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    ai_run_log_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_run_logs.id"), index=True)
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("approval_requests.id"), index=True
    )
    tool_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False)
    input_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class Task(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    task_type: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    priority: Mapped[str] = mapped_column(String(80), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CallingList(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "calling_lists"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_calling_lists_org_name"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    default_assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))


class CallingListEntry(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "calling_list_entries"
    __table_args__ = (
        UniqueConstraint("calling_list_id", "lead_id", name="uq_calling_list_entries_list_lead"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    calling_list_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("calling_lists.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    disposition: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SavedView(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "saved_views"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "owner_user_id",
            "resource_type",
            "name",
            name="uq_saved_views_owner_resource_name",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    team_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("teams.id"), index=True)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class Notification(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "recipient_user_id",
            "dedupe_key",
            name="uq_notifications_recipient_dedupe",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    notification_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(String(1000), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    action_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DuplicateCandidate(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "duplicate_candidates"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "primary_lead_id",
            "duplicate_lead_id",
            name="uq_duplicate_candidates_lead_pair",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    primary_lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    duplicate_lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    match_score: Mapped[int] = mapped_column(Integer, nullable=False)
    match_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class LeadMergeEvent(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lead_merge_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    primary_lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    duplicate_lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    merged_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    merge_strategy: Mapped[str] = mapped_column(String(80), nullable=False)
    merge_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class FollowUpPlan(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "follow_up_plans"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_follow_up_plans_org_name"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)


class FollowUpEnrollment(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "follow_up_enrollments"
    __table_args__ = (
        UniqueConstraint(
            "follow_up_plan_id",
            "lead_id",
            "status",
            name="uq_follow_up_enrollments_plan_lead_status",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    follow_up_plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("follow_up_plans.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    enrolled_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class ActivityEvent(UuidPrimaryKeyMixin, Base):
    __tablename__ = "activity_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditEvent(UuidPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    actor_type: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    previous_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkerHeartbeat(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "worker_heartbeats"

    service_name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    worker_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)


class OperationalFailure(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "operational_failures"

    service_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    operation_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    error_type: Mapped[str] = mapped_column(String(255), nullable=False)
    error_message: Mapped[str] = mapped_column(String(2000), nullable=False)
    first_occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_retry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
