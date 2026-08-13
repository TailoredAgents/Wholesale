import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
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
    calling_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    voice_forwarding_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    voice_forwarding_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    lead_alert_sms_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    inbound_message_alert_sms_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )


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
    __table_args__ = (
        CheckConstraint(
            "asset_class IN ('house', 'land')",
            name="ck_campaigns_asset_class",
        ),
        UniqueConstraint("organization_id", "code", name="uq_campaigns_org_code"),
    )

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
    asset_class: Mapped[str] = mapped_column(
        String(40), nullable=False, default="house", server_default="house", index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    starts_on: Mapped[date | None] = mapped_column(nullable=True)
    ends_on: Mapped[date | None] = mapped_column(nullable=True)
    budget_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class Prospect(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prospects"
    __table_args__ = (
        CheckConstraint(
            "asset_class IN ('house', 'land')",
            name="ck_prospects_asset_class",
        ),
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
    asset_class: Mapped[str] = mapped_column(
        String(40), nullable=False, default="house", server_default="house", index=True
    )
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
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prospecting_cohorts.id"), nullable=True, index=True
    )
    default_assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), index=True
    )
    imported_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_profile: Mapped[str] = mapped_column(
        String(40), nullable=False, default="general_csv", server_default="general_csv"
    )
    source_export_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_list_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_list_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_exported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_filters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_existing_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
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
    source_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prospect_source_memberships.id"), nullable=True, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    normalized_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    validation_errors: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    eligibility_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class ProspectSourceMembership(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prospect_source_memberships"
    __table_args__ = (
        UniqueConstraint(
            "prospect_id",
            "source_name",
            "source_list_key",
            name="uq_prospect_source_memberships_prospect_source_list",
        ),
        Index(
            "ix_psm_latest_relationship_state",
            "relationship_state_at_latest_import",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("prospects.id"), index=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("campaigns.id"), index=True)
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prospecting_cohorts.id"), nullable=True, index=True
    )
    first_import_batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("prospect_import_batches.id"), index=True
    )
    latest_import_batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("prospect_import_batches.id"), index=True
    )
    source_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    source_profile: Mapped[str] = mapped_column(String(40), nullable=False)
    source_record_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_list_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_list_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    appearance_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    relationship_state_at_latest_import: Mapped[str] = mapped_column(String(40), nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ProspectContactPoint(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prospect_contact_points"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "prospect_id",
            "contact_type",
            "normalized_value",
            name="uq_prospect_contact_points_prospect_value",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("prospects.id"), index=True)
    source_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prospect_source_memberships.id"), nullable=True, index=True
    )
    contact_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    validation_status: Mapped[str] = mapped_column(String(40), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    contact_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


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


class ProspectingCohort(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prospecting_cohorts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "code",
            name="uq_prospecting_cohorts_org_code",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("campaigns.id"), index=True)
    script_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prospecting_script_versions.id"), nullable=True, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="active", server_default="active", index=True
    )
    source_name: Mapped[str] = mapped_column(String(160), nullable=False)
    list_type: Mapped[str] = mapped_column(String(160), nullable=False)
    market_label: Mapped[str] = mapped_column(String(160), nullable=False)
    dialer_mode: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    call_window_start_hour: Mapped[int] = mapped_column(Integer, nullable=False)
    call_window_end_hour: Mapped[int] = mapped_column(Integer, nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    starts_on: Mapped[date] = mapped_column(nullable=False, index=True)
    ends_on: Mapped[date | None] = mapped_column(nullable=True)
    cohort_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class CampaignCost(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "campaign_costs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("campaigns.id"), index=True)
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prospecting_cohorts.id"), nullable=True, index=True
    )
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


class ProspectingWorkSession(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prospecting_work_sessions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("campaigns.id"), index=True)
    cohort_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("prospecting_cohorts.id"), index=True
    )
    caller_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    campaign_cost_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("campaign_costs.id"), unique=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    work_date: Mapped[date] = mapped_column(nullable=False, index=True)
    paid_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    productive_calling_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    hourly_rate_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    labor_cost_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)


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
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prospecting_cohorts.id"), nullable=True, index=True
    )
    assigned_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    dialer_mode: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="one_line_power",
        server_default="one_line_power",
        index=True,
    )
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
        CheckConstraint(
            "asset_class IN ('house', 'land')",
            name="ck_prospecting_script_versions_asset_class",
        ),
        UniqueConstraint(
            "organization_id",
            "version_number",
            name="uq_prospecting_scripts_org_version",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    asset_class: Mapped[str] = mapped_column(
        String(40), nullable=False, default="house", server_default="house", index=True
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
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prospecting_cohorts.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    outcome: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    contact_made: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    dialer_mode: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="one_line_power",
        server_default="one_line_power",
        index=True,
    )
    answer_classification: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="unknown",
        server_default="unknown",
        index=True,
    )
    party_classification: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="unknown",
        server_default="unknown",
        index=True,
    )
    interest_classification: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="not_assessed",
        server_default="not_assessed",
        index=True,
    )
    follow_up_permission: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="not_recorded",
        server_default="not_recorded",
        index=True,
    )
    classification_source: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="manual_outcome",
        server_default="manual_outcome",
    )
    dial_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    right_party_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    interest_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    measurement_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
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


class ProspectingCopilotRecommendation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prospecting_copilot_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_prospecting_copilot_org_idempotency",
        ),
        Index(
            "ix_prospecting_copilot_org_status",
            "organization_id",
            "status",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    batch_entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("prospect_calling_batch_entries.id", ondelete="CASCADE"),
        index=True,
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("prospects.id"), index=True)
    generated_for_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), index=True
    )
    ai_run_log_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_run_logs.id", ondelete="SET NULL"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    priority_score: Mapped[int] = mapped_column(Integer, nullable=False)
    priority_band: Mapped[str] = mapped_column(String(40), nullable=False)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confidence_score: Mapped[int | None] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProspectingCopilotReview(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prospecting_copilot_reviews"
    __table_args__ = (
        UniqueConstraint(
            "recommendation_id",
            name="uq_prospecting_copilot_review_recommendation",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("prospecting_copilot_recommendations.id", ondelete="CASCADE"),
        index=True,
    )
    reviewed_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    decision: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    original_output: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    final_output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(String(2000))
    estimated_time_saved_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProspectingCallQualityReview(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prospecting_call_quality_reviews"
    __table_args__ = (
        UniqueConstraint(
            "attempt_id",
            name="uq_prospecting_call_quality_attempt",
        ),
        Index(
            "ix_prospecting_call_quality_org_status",
            "organization_id",
            "status",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("prospecting_attempts.id", ondelete="CASCADE"), index=True
    )
    caller_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    call_record_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("call_records.id", ondelete="SET NULL"), index=True
    )
    transcript_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("call_transcripts.id", ondelete="SET NULL"), index=True
    )
    ai_run_log_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_run_logs.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    deterministic_scores: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    ai_output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    final_output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    compliance_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    escalation_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    review_notes: Mapped[str | None] = mapped_column(String(2000))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    decision_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    review_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class LeadQualificationScriptVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lead_qualification_script_versions"
    __table_args__ = (
        CheckConstraint(
            "asset_class IN ('house', 'land')",
            name="ck_lead_qualification_script_versions_asset_class",
        ),
        UniqueConstraint(
            "organization_id",
            "version_number",
            name="uq_lead_qualification_scripts_org_version",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    asset_class: Mapped[str] = mapped_column(
        String(40), nullable=False, default="house", server_default="house", index=True
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


class LeadManagerCopilotRecommendation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lead_manager_copilot_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_lead_manager_copilot_org_idempotency",
        ),
        Index(
            "ix_lead_manager_copilot_org_status",
            "organization_id",
            "status",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("lead_management_cases.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    ai_run_log_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_run_logs.id", ondelete="SET NULL"), index=True
    )
    generated_for_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    priority_score: Mapped[int] = mapped_column(Integer, nullable=False)
    priority_band: Mapped[str] = mapped_column(String(40), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(120))
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confidence_score: Mapped[int | None] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LeadManagerCopilotReview(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lead_manager_copilot_reviews"
    __table_args__ = (
        UniqueConstraint(
            "recommendation_id",
            name="uq_lead_manager_copilot_review_recommendation",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("lead_manager_copilot_recommendations.id", ondelete="CASCADE"),
        index=True,
    )
    reviewed_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    decision: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    original_output: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    final_output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(String(2000))
    estimated_time_saved_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
    parcel_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    normalized_parcel_key: Mapped[str | None] = mapped_column(
        String(500), nullable=True, index=True
    )
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
    research_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="not_started", server_default="not_started", index=True
    )
    research_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    research_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    research_last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class PropertyIntelligenceSnapshot(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "property_intelligence_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "property_id",
            "research_profile",
            "version_number",
            name="uq_property_intelligence_property_profile_version",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("properties.id", ondelete="CASCADE"), index=True
    )
    source_lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_market_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("underwriting_market_analyses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    research_profile: Mapped[str] = mapped_column(
        String(80), nullable=False, default="house_v1", server_default="house_v1", index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", index=True
    )
    address_signature: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    completeness_score: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    facts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    valuation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    comparables: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    market_context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    conflicts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    media: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    snapshot_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class PropertyResearchRun(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "property_research_runs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_property_research_org_idempotency",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("properties.id", ondelete="CASCADE"), index=True
    )
    source_lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    research_profile: Mapped[str] = mapped_column(
        String(80), nullable=False, default="house_v1", server_default="house_v1", index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(500), nullable=False)
    trigger_source: Mapped[str] = mapped_column(String(120), nullable=False)
    address_signature: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    force_refresh: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    run_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)


class Lead(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint(
            "asset_class IN ('house', 'land')",
            name="ck_leads_asset_class",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contacts.id"))
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"))
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    asset_class: Mapped[str] = mapped_column(
        String(40), nullable=False, default="house", server_default="house", index=True
    )
    qualification_context: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
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
    close_out_disposition: Mapped[str | None] = mapped_column(String(40), nullable=True)
    close_out_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    closed_out_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    closed_out_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
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
    normalized_address: Mapped[str | None] = mapped_column(String(320), nullable=True)
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
    enrichment_token_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    enrichment_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


class MarketingExperiment(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "marketing_experiments"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "experiment_key",
            name="uq_marketing_experiments_org_key",
        ),
        CheckConstraint(
            "status IN ('draft', 'running', 'paused', 'completed')",
            name="ck_marketing_experiments_status",
        ),
        CheckConstraint(
            "primary_metric IN "
            "('form_submit', 'qualified_lead', 'appointment_scheduled', "
            "'contract_signed', 'funded_deal')",
            name="ck_marketing_experiments_primary_metric",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    experiment_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    hypothesis: Mapped[str] = mapped_column(String(1000), nullable=False)
    surface_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    primary_metric: Mapped[str] = mapped_column(String(80), nullable=False)
    variants: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    minimum_sessions_per_variant: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="50"
    )
    minimum_runtime_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="14")
    decision_rule: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="draft", index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accumulated_runtime_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_notes: Mapped[str | None] = mapped_column(String(2000))


class MarketingExperimentAssignment(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "marketing_experiment_assignments"
    __table_args__ = (
        UniqueConstraint(
            "experiment_id",
            "session_id",
            name="uq_marketing_experiment_assignments_session",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("marketing_experiments.id"), index=True
    )
    session_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    variant_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    device_category: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="unknown"
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


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
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("marketing_experiments.id"), nullable=True, index=True
    )
    experiment_variant: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    device_category: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="unknown", index=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)


class Conversation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("organization_id", "lead_id", name="uq_conversations_org_lead"),
        CheckConstraint(
            "conversation_type IN ('lead', 'transaction', 'buyer', 'general')",
            name="ck_conversations_type",
        ),
        CheckConstraint(
            "conversation_type != 'lead' OR lead_id IS NOT NULL",
            name="ck_conversations_lead_context",
        ),
        CheckConstraint(
            "visibility_scope IN ('standard', 'restricted')",
            name="ck_conversations_visibility_scope",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    conversation_type: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="lead", index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="SET NULL"), index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contacts.id"), index=True)
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), index=True
    )
    assigned_team_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    source_alias_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("email_sender_aliases.id", ondelete="SET NULL"), index=True
    )
    visibility_scope: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="standard", index=True
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
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
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


class ConversationContextLink(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversation_context_links"
    __table_args__ = (
        CheckConstraint(
            "("
            "context_type = 'lead' AND lead_id IS NOT NULL "
            "AND transaction_id IS NULL AND buyer_id IS NULL AND disposition_case_id IS NULL"
            ") OR ("
            "context_type = 'transaction' AND lead_id IS NULL "
            "AND transaction_id IS NOT NULL AND buyer_id IS NULL "
            "AND disposition_case_id IS NULL"
            ") OR ("
            "context_type = 'buyer' AND lead_id IS NULL "
            "AND transaction_id IS NULL AND buyer_id IS NOT NULL "
            "AND disposition_case_id IS NULL"
            ") OR ("
            "context_type = 'disposition' AND lead_id IS NULL "
            "AND transaction_id IS NULL AND buyer_id IS NULL "
            "AND disposition_case_id IS NOT NULL"
            ")",
            name="ck_conversation_context_links_target",
        ),
        UniqueConstraint(
            "conversation_id",
            "lead_id",
            name="uq_conversation_context_links_lead",
        ),
        UniqueConstraint(
            "conversation_id",
            "transaction_id",
            name="uq_conversation_context_links_transaction",
        ),
        UniqueConstraint(
            "conversation_id",
            "buyer_id",
            name="uq_conversation_context_links_buyer",
        ),
        UniqueConstraint(
            "conversation_id",
            "disposition_case_id",
            name="uq_conversation_context_links_disposition",
        ),
        Index(
            "uq_conversation_context_links_primary",
            "conversation_id",
            unique=True,
            postgresql_where=text("is_primary"),
            sqlite_where=text("is_primary = 1"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    context_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    buyer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("buyers.id", ondelete="CASCADE"), index=True
    )
    disposition_case_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("disposition_cases.id", ondelete="CASCADE"), index=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    link_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)


class CommunicationProviderEvent(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "communication_provider_events"
    __table_args__ = (
        Index(
            "ix_provider_events_processing_claim",
            "provider",
            "processing_status",
            "next_attempt_at",
            "processing_started_at",
            "received_at",
        ),
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
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_token: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
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
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
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


class CommunicationParticipant(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "communication_participants"
    __table_args__ = (
        CheckConstraint(
            "participant_role IN ('from', 'to', 'cc', 'bcc', 'reply_to')",
            name="ck_communication_participants_role",
        ),
        UniqueConstraint(
            "communication_record_id",
            "participant_role",
            "normalized_email",
            name="uq_communication_participants_message_role_email",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    communication_record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("communication_records.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    email_sender_alias_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("email_sender_aliases.id", ondelete="SET NULL"), index=True
    )
    participant_role: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    email_address: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    participant_metadata: Mapped[dict[str, Any] | None] = mapped_column(
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
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
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


class EmailSenderAlias(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_sender_aliases"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "email_address",
            name="uq_email_sender_aliases_org_address",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    assigned_team_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_identity_id: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_address: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    alias_type: Mapped[str] = mapped_column(String(40), nullable=False)
    purpose_key: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    inbound_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    outbound_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    signature_text: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    routing_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)


class EmailSenderGrant(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_sender_grants"
    __table_args__ = (
        UniqueConstraint(
            "email_sender_alias_id",
            "user_id",
            name="uq_email_sender_grants_alias_user",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    email_sender_alias_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("email_sender_aliases.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    granted_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    access_level: Mapped[str] = mapped_column(String(40), nullable=False)
    can_send: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    receives_notifications: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )


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
    email_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("email_accounts.id", ondelete="CASCADE"), index=True
    )
    email_sender_alias_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("email_sender_aliases.id", ondelete="SET NULL"), index=True
    )
    provider_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_attachment_id: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    disposition: Mapped[str] = mapped_column(String(40), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    storage_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    malware_scan_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    fallback_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), index=True
    )
    assigned_team_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_phone_number_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    department_key: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="acquisitions"
    )
    purpose_key: Mapped[str] = mapped_column(
        String(80), nullable=False, server_default="seller_conversations"
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    inbound_route: Mapped[str] = mapped_column(String(80), nullable=False)
    ring_strategy: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="sequential"
    )
    coverage_timezone: Mapped[str] = mapped_column(
        String(80), nullable=False, server_default="America/New_York"
    )
    coverage_start_hour: Mapped[int] = mapped_column(Integer, nullable=False, server_default="9")
    coverage_end_hour: Mapped[int] = mapped_column(Integer, nullable=False, server_default="20")
    missed_call_action: Mapped[str] = mapped_column(
        String(80), nullable=False, server_default="fallback_then_voicemail"
    )
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
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id"), index=True, nullable=True
    )
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
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id"), index=True, nullable=True
    )
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


class AcquisitionsCopilotRecommendation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "acquisitions_copilot_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_acquisitions_copilot_org_idempotency",
        ),
        Index(
            "ix_acquisitions_copilot_org_status",
            "organization_id",
            "status",
        ),
        Index("ix_acq_copilot_appointment", "appointment_id"),
        Index("ix_acq_copilot_lead", "lead_id"),
        Index("ix_acq_copilot_type", "recommendation_type"),
        Index("ix_acq_copilot_brief", "field_meeting_brief_id"),
        Index("ix_acq_copilot_inspection", "field_inspection_id"),
        Index("ix_acq_copilot_negotiation", "field_negotiation_session_id"),
        Index("ix_acq_copilot_underwriting", "underwriting_version_id"),
        Index("ix_acq_copilot_offer_plan", "offer_negotiation_plan_id"),
        Index("ix_acq_copilot_assignee", "generated_for_user_id"),
        Index("ix_acq_copilot_run", "ai_run_log_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("appointments.id", ondelete="CASCADE")
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"))
    recommendation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    field_meeting_brief_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("field_meeting_briefs.id", ondelete="SET NULL")
    )
    field_inspection_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("field_inspections.id", ondelete="SET NULL")
    )
    field_negotiation_session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("field_negotiation_sessions.id", ondelete="SET NULL")
    )
    underwriting_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("underwriting_versions.id", ondelete="SET NULL")
    )
    offer_negotiation_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("offer_negotiation_plans.id", ondelete="SET NULL")
    )
    generated_for_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    ai_run_log_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_run_logs.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confidence_score: Mapped[int | None] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AcquisitionsCopilotReview(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "acquisitions_copilot_reviews"
    __table_args__ = (
        UniqueConstraint(
            "recommendation_id",
            name="uq_acquisitions_copilot_review_recommendation",
        ),
        Index("ix_acq_copilot_review_org", "organization_id"),
        Index("ix_acq_copilot_review_recommendation", "recommendation_id"),
        Index("ix_acq_copilot_reviewer", "reviewed_by_user_id"),
        Index("ix_acq_copilot_review_decision", "decision"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("acquisitions_copilot_recommendations.id", ondelete="CASCADE"),
    )
    reviewed_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    original_output: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    final_output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(String(2000))
    estimated_time_saved_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
    image_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    storage_provider: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="database"
    )
    storage_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    malware_scan_status: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="not_configured"
    )
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    governing_concession_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("offer_concessions.id"), nullable=True, index=True
    )
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
    valuation_profile: Mapped[str] = mapped_column(
        String(80), nullable=False, default="house_v3", server_default="house_v3", index=True
    )
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
    valuation_profile: Mapped[str] = mapped_column(
        String(80), nullable=False, default="house_v3", server_default="house_v3", index=True
    )
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


class UnderwritingCompCopilotThread(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "underwriting_comp_copilot_threads"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "market_analysis_id",
            name="uq_underwriting_comp_copilot_analysis",
        ),
        Index(
            "ix_underwriting_comp_copilot_lead",
            "organization_id",
            "lead_id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    market_analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("underwriting_market_analyses.id", ondelete="CASCADE"),
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="active", server_default="active", index=True
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class UnderwritingCompCopilotMessage(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "underwriting_comp_copilot_messages"
    __table_args__ = (
        Index(
            "ix_underwriting_comp_copilot_message_thread",
            "thread_id",
            "created_at",
        ),
        Index(
            "ix_underwriting_comp_copilot_message_org",
            "organization_id",
            "created_at",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("underwriting_comp_copilot_threads.id", ondelete="CASCADE"),
        index=True,
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    suggested_actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    limitations: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    used_ai: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)


class UnderwritingManualComparable(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "underwriting_manual_comparables"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="active", server_default="active", index=True
    )
    street_address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    formatted_address: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_address_key: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    sale_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    sale_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    transaction_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    arms_length_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    arms_length_evidence: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    property_type: Mapped[str] = mapped_column(String(80), nullable=False)
    bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bathrooms_hundredths: Mapped[int | None] = mapped_column(Integer, nullable=True)
    square_footage: Mapped[int] = mapped_column(Integer, nullable=False)
    year_built: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lot_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_hundredths: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subdivision: Mapped[str | None] = mapped_column(String(255), nullable=True)
    condition_classification: Mapped[str] = mapped_column(
        String(40), nullable=False, default="unknown", server_default="unknown"
    )
    condition_evidence: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_reference: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    verification_notes: Mapped[str] = mapped_column(String(2000), nullable=False)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LandValuationAnalysis(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable, Land-only comparable and offer-guidance evidence."""

    __tablename__ = "land_valuation_analyses"
    __table_args__ = (
        CheckConstraint(
            "subject_acres_ten_thousandths > 0",
            name="ck_land_valuation_positive_acres",
        ),
        UniqueConstraint(
            "lead_id",
            "version_number",
            name="uq_land_valuation_lead_version",
        ),
        UniqueConstraint(
            "organization_id",
            "lead_id",
            "analysis_fingerprint",
            name="uq_land_valuation_lead_fingerprint",
        ),
        UniqueConstraint(
            "organization_id",
            "lead_id",
            "request_idempotency_key",
            name="uq_land_valuation_lead_idempotency",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    property_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("property_intelligence_snapshots.id"), index=True
    )
    source_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("land_valuation_analyses.id"), nullable=True, index=True
    )
    policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("land_offer_policy_versions.id"), nullable=True, index=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    valuation_profile: Mapped[str] = mapped_column(
        String(80), nullable=False, default="land_v1", server_default="land_v1", index=True
    )
    methodology_version: Mapped[str] = mapped_column(
        String(80), nullable=False, default="land_v1", server_default="land_v1"
    )
    analysis_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    request_idempotency_key: Mapped[str | None] = mapped_column(
        String(160), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    guidance_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    valuation_basis: Mapped[str] = mapped_column(
        String(40), nullable=False, default="per_acre", server_default="per_acre"
    )
    access_evidence_status: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_acres_ten_thousandths: Mapped[int] = mapped_column(BigInteger, nullable=False)
    subject_lot_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supported_value_low_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    supported_value_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    supported_value_high_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    quick_sale_low_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    quick_sale_high_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    opening_offer_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    seller_contract_ceiling_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    assignment_fee_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    closing_title_reserve_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    curative_reserve_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uncertainty_reserve_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_comp_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_comp_count: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_comps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    rejected_comps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    subject_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    search_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    assumptions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    review_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    guidance_blockers: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    analysis_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )


class LandOfferPolicyVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Owner-approved policy used to turn Land value evidence into offer guidance."""

    __tablename__ = "land_offer_policy_versions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "version_number",
            name="uq_land_offer_policy_org_version",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    quick_sale_discount_low_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    quick_sale_discount_high_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    opening_reserve_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    assignment_fee_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    closing_title_reserve_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    curative_reserve_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uncertainty_reserve_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    maximum_dispersion_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_comparable_count: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    validation_scenarios: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class UnderwritingCalibrationDecision(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "underwriting_calibration_decisions"
    __table_args__ = (
        Index(
            "ix_underwriting_calibration_decisions_org_scope",
            "organization_id",
            "scope_key",
            "created_at",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    proposed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    scope_key: Mapped[str] = mapped_column(String(255), nullable=False)
    decision_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    rationale: Mapped[str] = mapped_column(String(3000), nullable=False)
    current_methodology_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    proposed_methodology_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    proposed_changes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_sample_required: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


class OfferConcession(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offer_concessions"
    __table_args__ = (
        UniqueConstraint(
            "offer_negotiation_plan_id",
            "sequence_number",
            name="uq_offer_concessions_plan_sequence",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    offer_negotiation_plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("offer_negotiation_plans.id"), index=True
    )
    underwriting_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("underwriting_versions.id"), index=True
    )
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("appointments.id"), nullable=True, index=True
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("approval_requests.id"), nullable=True, index=True
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    presented_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    authority_basis: Mapped[str] = mapped_column(String(80), nullable=False)
    previous_offer_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    proposed_offer_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    concession_delta_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    seller_counter_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    seller_exchange: Mapped[str] = mapped_column(String(2000), nullable=False)
    decision_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    presented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class OfferNegotiationEvent(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offer_negotiation_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    offer_negotiation_plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("offer_negotiation_plans.id"), index=True
    )
    concession_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("offer_concessions.id"), nullable=True, index=True
    )
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("appointments.id"), nullable=True, index=True
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    previous_offer_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    seller_counter_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    notes: Mapped[str] = mapped_column(String(2000), nullable=False)
    seller_response: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    objections: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False)


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
    coordinator_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), index=True
    )
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
    earnest_money_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    earnest_money_paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_diligence_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title_cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assignment_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    funded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    item_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, server_default="operations")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    dependency_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transaction_checklist_items.id"), nullable=True
    )
    evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transaction_documents.id"), nullable=True
    )
    evidence_notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class ContractTemplate(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contract_templates"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "document_type",
            "state_code",
            "version_number",
            name="uq_contract_templates_version",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    storage_provider: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="database"
    )
    storage_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    malware_scan_status: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="not_configured"
    )
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    esign_provider_template_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    esign_field_mapping: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(String(1000))


class ContractPackage(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contract_packages"
    __table_args__ = (
        UniqueConstraint("transaction_id", "version_number", name="uq_contract_packages_version"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"))
    template_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contract_templates.id"))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("approval_requests.id")
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    seller_name: Mapped[str] = mapped_column(String(255), nullable=False)
    buyer_entity_name: Mapped[str] = mapped_column(String(255), nullable=False)
    purchase_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    earnest_money_cents: Mapped[int | None] = mapped_column(BigInteger)
    closing_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inspection_period_days: Mapped[int | None] = mapped_column(Integer)
    terms_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TransactionDocument(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transaction_documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.id"), index=True
    )
    contract_package_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("contract_packages.id"), index=True
    )
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    document_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    storage_provider: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="database"
    )
    storage_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    malware_scan_status: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="not_configured"
    )
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000))


class EsignEnvelope(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "esign_envelopes"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "provider_document_id",
            name="uq_esign_envelope_provider_document",
        ),
        Index(
            "uq_esign_envelope_active_package",
            "contract_package_id",
            unique=True,
            postgresql_where=text(
                "status NOT IN ('completed', 'declined', 'expired', 'cancelled', 'error')"
            ),
            sqlite_where=text(
                "status NOT IN ('completed', 'declined', 'expired', 'cancelled', 'error')"
            ),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.id"), index=True
    )
    contract_package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("contract_packages.id"), index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    completed_document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transaction_documents.id"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_document_id: Mapped[str] = mapped_column(String(255), nullable=False)
    delivery_mode: Mapped[str] = mapped_column(String(40), nullable=False, server_default="email")
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str | None] = mapped_column(String(2000))
    test_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    provider_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_provider_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EsignRecipient(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "esign_recipients"
    __table_args__ = (
        UniqueConstraint(
            "esign_envelope_id",
            "email",
            name="uq_esign_recipient_envelope_email",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    esign_envelope_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("esign_envelopes.id", ondelete="CASCADE"), index=True
    )
    provider_recipient_id: Mapped[str | None] = mapped_column(String(255))
    embedded_signing_url: Mapped[str | None] = mapped_column(String(1000))
    placeholder_name: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    signing_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EsignProviderEvent(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "esign_provider_events"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "provider_event_id",
            name="uq_esign_provider_event",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    esign_envelope_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("esign_envelopes.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_error: Mapped[str | None] = mapped_column(String(2000))


class EsignProviderConfiguration(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "esign_provider_configurations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            name="uq_esign_provider_configuration",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    configured_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    webhook_id: Mapped[str] = mapped_column(String(255), nullable=False)
    callback_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    account_email: Mapped[str | None] = mapped_column(String(320))
    account_name: Mapped[str | None] = mapped_column(String(255))
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class TransactionDocumentFact(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transaction_document_facts"
    __table_args__ = (
        Index("ix_transaction_document_facts_transaction", "transaction_id"),
        Index("ix_transaction_document_facts_document", "document_id"),
        Index("ix_transaction_document_facts_field", "field_key"),
        Index("ix_transaction_document_facts_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="CASCADE")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transaction_documents.id", ondelete="CASCADE")
    )
    field_key: Mapped[str] = mapped_column(String(120), nullable=False)
    value_text: Mapped[str] = mapped_column(String(2000), nullable=False)
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_excerpt: Mapped[str | None] = mapped_column(String(1000))
    extraction_method: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence_score: Mapped[int | None] = mapped_column(Integer)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TransactionParty(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transaction_parties"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.id"), index=True
    )
    party_type: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(80))
    address: Mapped[str | None] = mapped_column(String(500))
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    notes: Mapped[str | None] = mapped_column(String(1000))


class TransactionEvent(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transaction_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TransactionCopilotRecommendation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transaction_copilot_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_transaction_copilot_org_idempotency",
        ),
        Index("ix_transaction_copilot_transaction", "transaction_id"),
        Index("ix_transaction_copilot_lead", "lead_id"),
        Index("ix_transaction_copilot_run", "ai_run_log_id"),
        Index("ix_transaction_copilot_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="CASCADE")
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"))
    generated_for_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    ai_run_log_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_run_logs.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confidence_score: Mapped[int | None] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TransactionCopilotReview(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transaction_copilot_reviews"
    __table_args__ = (
        UniqueConstraint(
            "recommendation_id",
            name="uq_transaction_copilot_review_recommendation",
        ),
        Index("ix_transaction_copilot_review_org", "organization_id"),
        Index("ix_transaction_copilot_review_recommendation", "recommendation_id"),
        Index("ix_transaction_copilot_reviewer", "reviewed_by_user_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("transaction_copilot_recommendations.id", ondelete="CASCADE"),
    )
    reviewed_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    original_output: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    final_output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(String(2000))
    estimated_time_saved_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
    reliability_score_basis_points: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="5000"
    )
    completed_deals: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failed_deals: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    proof_of_funds_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class BuyerDiscoveryRun(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "buyer_discovery_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    disposition_case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("disposition_cases.id", ondelete="CASCADE"), index=True
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    search_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    provider_request: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    credit_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(String(2000))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BuyerDiscoveryCandidate(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "buyer_discovery_candidates"
    __table_args__ = (
        UniqueConstraint(
            "discovery_run_id",
            "external_key",
            name="uq_buyer_discovery_run_external_key",
        ),
        Index(
            "ix_buyer_discovery_candidate_provider_key",
            "organization_id",
            "provider",
            "external_key",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    discovery_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("buyer_discovery_runs.id", ondelete="CASCADE"), index=True
    )
    buyer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("buyers.id"))
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    external_key: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(80))
    market: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    property_types: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    observed_purchase_count: Mapped[int] = mapped_column(Integer, nullable=False)
    no_mortgage_count: Mapped[int] = mapped_column(Integer, nullable=False)
    last_purchase_date: Mapped[date | None] = mapped_column(Date)
    min_purchase_price_cents: Mapped[int | None] = mapped_column(BigInteger)
    max_purchase_price_cents: Mapped[int | None] = mapped_column(BigInteger)
    score_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    score_components: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    provider_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BuyerProofDocument(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "buyer_proof_documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    buyer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("buyers.id"), index=True)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    institution_name: Mapped[str | None] = mapped_column(String(255))
    verified_amount_cents: Mapped[int | None] = mapped_column(BigInteger)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    storage_provider: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="database"
    )
    storage_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    malware_scan_status: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="not_configured"
    )
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    notes: Mapped[str | None] = mapped_column(String(1000))


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
    criteria_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class BuyerOffer(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "buyer_offers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("deals.id"), index=True)
    buyer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("buyers.id"), index=True)
    disposition_case_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("disposition_cases.id")
    )
    proof_document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("buyer_proof_documents.id")
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    earnest_money_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    financing_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    proof_of_funds_received: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deposit_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deposit_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DispositionCase(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "disposition_cases"
    __table_args__ = (UniqueConstraint("transaction_id", name="uq_disposition_cases_transaction"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.id"), index=True
    )
    deal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("deals.id"))
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"))
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    compensation_plan_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("compensation_plan_versions.id")
    )
    disposition_operating_mode_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("disposition_operating_modes.id")
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    strategy: Mapped[str] = mapped_column(String(40), nullable=False)
    asking_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    minimum_acceptable_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    package_status: Mapped[str] = mapped_column(String(40), nullable=False)
    package_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    package_approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id")
    )
    package_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    selected_buyer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("buyers.id"))
    backup_buyer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("buyers.id"))
    selection_approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id")
    )
    selection_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(String(2000))


class DispositionMatch(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "disposition_matches"
    __table_args__ = (
        UniqueConstraint(
            "disposition_case_id", "buyer_id", name="uq_disposition_matches_case_buyer"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    disposition_case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("disposition_cases.id", ondelete="CASCADE"), index=True
    )
    buyer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("buyers.id"))
    score_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    score_components: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    qualification_status: Mapped[str] = mapped_column(String(40), nullable=False)
    recipient_status: Mapped[str] = mapped_column(String(40), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)


class DispositionCampaign(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "disposition_campaigns"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    disposition_case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("disposition_cases.id", ondelete="CASCADE")
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BuyerEngagement(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "buyer_engagements"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    disposition_case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("disposition_cases.id", ondelete="CASCADE")
    )
    buyer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("buyers.id"))
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    engagement_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000))


class DispositionCopilotRecommendation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "disposition_copilot_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_disposition_copilot_org_idempotency",
        ),
        Index("ix_disposition_copilot_case", "disposition_case_id"),
        Index("ix_disposition_copilot_transaction", "transaction_id"),
        Index("ix_disposition_copilot_run", "ai_run_log_id"),
        Index("ix_disposition_copilot_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    disposition_case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("disposition_cases.id", ondelete="CASCADE")
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("transactions.id"))
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"))
    generated_for_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    ai_run_log_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_run_logs.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confidence_score: Mapped[int | None] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DispositionCopilotReview(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "disposition_copilot_reviews"
    __table_args__ = (
        UniqueConstraint(
            "recommendation_id",
            name="uq_disposition_copilot_review_recommendation",
        ),
        Index("ix_disposition_copilot_review_org", "organization_id"),
        Index(
            "ix_disposition_copilot_review_recommendation",
            "recommendation_id",
        ),
        Index("ix_disposition_copilot_reviewer", "reviewed_by_user_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("disposition_copilot_recommendations.id", ondelete="CASCADE"),
    )
    reviewed_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    original_output: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    final_output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(String(2000))
    estimated_time_saved_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ManagementCopilotRecommendation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "management_copilot_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_management_copilot_org_idempotency",
        ),
        Index(
            "ix_management_copilot_org_capability_status",
            "organization_id",
            "capability_key",
            "status",
        ),
        Index("ix_management_copilot_run", "ai_run_log_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    capability_key: Mapped[str] = mapped_column(String(120), nullable=False)
    reporting_period_days: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_for_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    ai_run_log_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_run_logs.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confidence_score: Mapped[int | None] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ManagementCopilotReview(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "management_copilot_reviews"
    __table_args__ = (
        UniqueConstraint(
            "recommendation_id",
            name="uq_management_copilot_review_recommendation",
        ),
        Index("ix_management_copilot_review_org", "organization_id"),
        Index("ix_management_copilot_reviewer", "reviewed_by_user_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("management_copilot_recommendations.id", ondelete="CASCADE"),
    )
    reviewed_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    original_output: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    final_output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(String(2000))
    estimated_time_saved_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DealReconciliation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deal_reconciliations"
    __table_args__ = (
        UniqueConstraint("transaction_id", name="uq_deal_reconciliations_transaction"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    transaction_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("transactions.id"))
    disposition_case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("disposition_cases.id"))
    compensation_plan_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("compensation_plan_versions.id")
    )
    disposition_operating_mode_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("disposition_operating_modes.id")
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    gross_revenue_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    acquisition_reserve_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deal_deductions_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    adjusted_deal_margin_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_compensation_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    company_profit_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    company_margin_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    target_margin_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(String(2000))


class DealPayout(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deal_payouts"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    deal_reconciliation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("deal_reconciliations.id", ondelete="CASCADE")
    )
    role_credit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("role_credits.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    role_key: Mapped[str] = mapped_column(String(120), nullable=False)
    credit_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_reference: Mapped[str | None] = mapped_column(String(255))
    evidence_references: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, server_default="[]"
    )


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


class OperatingSeat(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "operating_seats"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "seat_key",
            name="uq_operating_seats_org_key",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    seat_key: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    role_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    primary_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    backup_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))


class BusinessCounterparty(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "business_counterparties"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    market_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("markets.id"), index=True)
    counterparty_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class StaffRoleAcceptance(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "staff_role_acceptances"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            "role_key",
            "manual_key",
            "manual_version",
            name="uq_staff_role_acceptance_assignment",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    role_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    manual_key: Mapped[str] = mapped_column(String(160), nullable=False)
    manual_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    assigned_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    workspace_test_evidence: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    employee_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    manager_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CompliancePolicyVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compliance_policy_versions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "policy_key",
            "version_number",
            name="uq_compliance_policy_version",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    policy_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_state_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    policy_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    legal_review_status: Mapped[str] = mapped_column(String(40), nullable=False)
    legal_reviewer_name: Mapped[str | None] = mapped_column(String(255))
    legal_reviewer_company: Mapped[str | None] = mapped_column(String(255))
    legal_evidence_reference: Mapped[str | None] = mapped_column(String(1000))
    legal_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(String(2000))


class DncScreeningSource(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dnc_screening_sources"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "name",
            name="uq_dnc_screening_sources_org_name",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    account_reference: Mapped[str | None] = mapped_column(String(255))
    coverage_area_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    refresh_interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    next_refresh_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    latest_evidence_reference: Mapped[str | None] = mapped_column(String(1000))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(String(2000))


class ComplianceTrainingRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compliance_training_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            "training_key",
            "training_version",
            name="uq_compliance_training_assignment",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    training_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    training_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    assigned_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score_basis_points: Mapped[int | None] = mapped_column(Integer)
    completion_evidence: Mapped[str | None] = mapped_column(String(2000))
    employee_attestation: Mapped[str | None] = mapped_column(String(2000))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manager_notes: Mapped[str | None] = mapped_column(String(2000))


class ComplianceIncident(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compliance_incidents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("contacts.id"), index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    prospect_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prospects.id"), index=True
    )
    call_record_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("call_records.id"), index=True
    )
    incident_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[str | None] = mapped_column(String(4000))
    reported_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(String(2000))


class ComplianceControlRun(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compliance_control_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    run_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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


class PublicProofRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "public_proof_records"
    __table_args__ = (
        CheckConstraint(
            "proof_type IN ('review', 'seller_story', 'completed_purchase', 'statistic')",
            name="ck_public_proof_records_type",
        ),
        CheckConstraint(
            "permission_status IN ('pending', 'granted', 'not_required', 'revoked')",
            name="ck_public_proof_records_permission",
        ),
        CheckConstraint(
            "publication_status IN ('draft', 'in_review', 'published', 'retired')",
            name="ck_public_proof_records_publication",
        ),
        CheckConstraint(
            "rating IS NULL OR (rating >= 1 AND rating <= 5)",
            name="ck_public_proof_records_rating",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    proof_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    attribution_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    attribution_detail: Mapped[str | None] = mapped_column(String(180), nullable=True)
    location_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metric_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metric_value: Mapped[str | None] = mapped_column(String(80), nullable=True)
    methodology: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_type: Mapped[str] = mapped_column(String(60), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    show_source_link: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    permission_status: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="pending"
    )
    permission_evidence_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    material_connection: Mapped[str | None] = mapped_column(String(500), nullable=True)
    disclosure: Mapped[str | None] = mapped_column(String(500), nullable=True)
    publication_status: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="draft", index=True
    )
    featured: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AccountingProfile(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "accounting_profiles"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            name="uq_accounting_profiles_organization",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    legal_entity_name: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    federal_tax_classification: Mapped[str] = mapped_column(String(80), nullable=False)
    accounting_method: Mapped[str] = mapped_column(String(40), nullable=False)
    tax_year_end_month: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_year_end_day: Mapped[int] = mapped_column(Integer, nullable=False)
    books_start_date: Mapped[date | None] = mapped_column(Date)
    home_state: Mapped[str] = mapped_column(String(2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    owner_compensation_treatment: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_rule_year: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000))
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))


class AccountingAccount(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "accounting_accounts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "policy_version",
            "code",
            name="uq_accounting_accounts_org_version_code",
        ),
        UniqueConstraint(
            "organization_id",
            "policy_version",
            "system_key",
            name="uq_accounting_accounts_org_version_key",
        ),
        Index(
            "ix_accounting_accounts_org_type",
            "organization_id",
            "account_type",
            "is_active",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    accounting_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("accounting_profiles.id", ondelete="CASCADE"), index=True
    )
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    system_key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(String(40), nullable=False)
    subtype: Mapped[str] = mapped_column(String(80), nullable=False)
    normal_balance: Mapped[str] = mapped_column(String(10), nullable=False)
    tax_category: Mapped[str] = mapped_column(String(120), nullable=False)
    deal_tracking: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)


class AccountingPeriod(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "accounting_periods"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "period_key",
            name="uq_accounting_periods_org_key",
        ),
        CheckConstraint(
            "period_end_at >= period_start_at",
            name="ck_accounting_period_date_order",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    accounting_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("accounting_profiles.id", ondelete="CASCADE"), index=True
    )
    period_key: Mapped[str] = mapped_column(String(7), nullable=False)
    period_start_at: Mapped[date] = mapped_column(Date, nullable=False)
    period_end_at: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    review_started_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id")
    )
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopened_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopen_reason: Mapped[str | None] = mapped_column(String(2000))


class JournalEntry(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "entry_number",
            name="uq_journal_entries_org_number",
        ),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_journal_entries_org_idempotency",
        ),
        UniqueConstraint(
            "reverses_entry_id",
            name="uq_journal_entries_reverses_entry",
        ),
        CheckConstraint(
            "total_debits_cents = total_credits_cents",
            name="ck_journal_entries_balanced_totals",
        ),
        CheckConstraint(
            "total_debits_cents > 0",
            name="ck_journal_entries_positive_total",
        ),
        Index(
            "ix_journal_entries_org_status_date",
            "organization_id",
            "status",
            "entry_date",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    accounting_period_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("accounting_periods.id"), index=True
    )
    entry_number: Mapped[str] = mapped_column(String(40), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    memo: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_type: Mapped[str] = mapped_column(String(120), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(255))
    posting_rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_references: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total_debits_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_credits_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prepared_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    posted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    reversed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    reverses_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("journal_entries.id"), index=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(String(2000))


class JournalLine(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        UniqueConstraint(
            "journal_entry_id",
            "line_number",
            name="uq_journal_lines_entry_number",
        ),
        CheckConstraint(
            "debit_cents >= 0 AND credit_cents >= 0",
            name="ck_journal_lines_nonnegative",
        ),
        CheckConstraint(
            "(debit_cents > 0 AND credit_cents = 0) OR (credit_cents > 0 AND debit_cents = 0)",
            name="ck_journal_lines_single_side",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("journal_entries.id", ondelete="CASCADE"), index=True
    )
    accounting_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("accounting_accounts.id"), index=True
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    debit_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    credit_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    memo: Mapped[str | None] = mapped_column(String(1000))
    deal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("deals.id"), index=True)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transactions.id"), index=True
    )


class AccountingPostingRule(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "accounting_posting_rules"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "rule_key",
            "version_number",
            name="uq_accounting_posting_rules_org_key_version",
        ),
        Index(
            "ix_accounting_posting_rules_org_status",
            "organization_id",
            "status",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    rule_key: Mapped[str] = mapped_column(String(120), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(120), nullable=False)
    trigger_status: Mapped[str] = mapped_column(String(80), nullable=False)
    strategy_key: Mapped[str] = mapped_column(String(120), nullable=False)
    debit_account_key: Mapped[str] = mapped_column(String(120), nullable=False)
    credit_account_key: Mapped[str] = mapped_column(String(120), nullable=False)
    evidence_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccountingSourceLink(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "accounting_source_links"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_type",
            "source_id",
            "posting_purpose",
            name="uq_accounting_source_links_source_purpose",
        ),
        Index(
            "ix_accounting_source_links_org_status",
            "organization_id",
            "status",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    posting_rule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("accounting_posting_rules.id"), index=True
    )
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("journal_entries.id"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(120), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    posting_purpose: Mapped[str] = mapped_column(String(120), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    exception_detail: Mapped[str | None] = mapped_column(String(2000))
    generated_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FinancialObligation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "financial_obligations"
    __table_args__ = (
        CheckConstraint(
            "amount_cents > 0",
            name="ck_financial_obligations_positive_amount",
        ),
        Index(
            "ix_financial_obligations_org_status",
            "organization_id",
            "status",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    obligation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    counterparty_name: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    expense_account_key: Mapped[str | None] = mapped_column(String(120))
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_type: Mapped[str | None] = mapped_column(String(120))
    source_id: Mapped[str | None] = mapped_column(String(255))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_reference: Mapped[str | None] = mapped_column(String(255))
    evidence_references: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000))


class VendorProfile(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vendor_profiles"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "counterparty_id",
            name="uq_vendor_profiles_org_counterparty",
        ),
        Index(
            "ix_vendor_profiles_org_status",
            "organization_id",
            "status",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    counterparty_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("business_counterparties.id"), index=True
    )
    vendor_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    default_expense_account_key: Mapped[str | None] = mapped_column(String(120))
    payment_terms_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tax_reportable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    w9_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    w9_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    w9_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    w9_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    w9_verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    remittance_address: Mapped[str | None] = mapped_column(String(1000))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(String(2000))


class VendorBill(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vendor_bills"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "vendor_profile_id",
            "bill_number",
            name="uq_vendor_bills_org_vendor_number",
        ),
        CheckConstraint(
            "amount_cents > 0",
            name="ck_vendor_bills_positive_amount",
        ),
        Index(
            "ix_vendor_bills_org_status_due",
            "organization_id",
            "status",
            "due_at",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    vendor_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("vendor_profiles.id"), index=True
    )
    financial_obligation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("financial_obligations.id"), index=True
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("deals.id"), index=True)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transactions.id"), index=True
    )
    bill_number: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    issue_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_reference: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(String(2000))


class VendorBillLine(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vendor_bill_lines"
    __table_args__ = (
        UniqueConstraint(
            "vendor_bill_id",
            "line_number",
            name="uq_vendor_bill_lines_bill_number",
        ),
        CheckConstraint(
            "amount_cents > 0",
            name="ck_vendor_bill_lines_positive_amount",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    vendor_bill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("vendor_bills.id", ondelete="CASCADE"), index=True
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expense_account_key: Mapped[str] = mapped_column(String(120), nullable=False)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("deals.id"), index=True)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transactions.id"), index=True
    )


class FinanceDocument(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "finance_documents"
    __table_args__ = (
        Index(
            "ix_finance_documents_org_type",
            "organization_id",
            "document_type",
            "status",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    vendor_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("vendor_profiles.id"), index=True
    )
    vendor_bill_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("vendor_bills.id"), index=True
    )
    financial_obligation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("financial_obligations.id"), index=True
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transactions.id"), index=True
    )
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    document_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_data: Mapped[bytes | None] = mapped_column(LargeBinary)
    storage_provider: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="database"
    )
    storage_key: Mapped[str | None] = mapped_column(String(1000))
    malware_scan_status: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="not_configured"
    )
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000))


class BankAccount(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bank_accounts"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_bank_accounts_org_name"),
        Index("ix_bank_accounts_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    institution_name: Mapped[str | None] = mapped_column(String(160))
    account_type: Mapped[str] = mapped_column(String(40), nullable=False)
    last_four: Mapped[str | None] = mapped_column(String(4))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(String(1000))


class BankStatementImport(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bank_statement_imports"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "bank_account_id",
            "file_sha256",
            name="uq_bank_statement_imports_account_file",
        ),
        Index("ix_bank_statement_imports_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    bank_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("bank_accounts.id"), index=True
    )
    imported_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_format: Mapped[str] = mapped_column(String(40), nullable=False)
    field_mapping: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    invalid_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicate_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    statement_start_on: Mapped[date | None] = mapped_column(Date)
    statement_end_on: Mapped[date | None] = mapped_column(Date)
    opening_balance_cents: Mapped[int | None] = mapped_column(BigInteger)
    closing_balance_cents: Mapped[int | None] = mapped_column(BigInteger)
    file_data: Mapped[bytes | None] = mapped_column(LargeBinary)
    storage_provider: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="database"
    )
    storage_key: Mapped[str | None] = mapped_column(String(1000))
    malware_scan_status: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="not_configured"
    )
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BankTransaction(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bank_transactions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "bank_account_id",
            "fingerprint",
            name="uq_bank_transactions_account_fingerprint",
        ),
        CheckConstraint("amount_cents <> 0", name="ck_bank_transactions_nonzero_amount"),
        Index("ix_bank_transactions_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    bank_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("bank_accounts.id"), index=True
    )
    statement_import_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("bank_statement_imports.id"), index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255))
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    posted_on: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_cents: Mapped[int | None] = mapped_column(BigInteger)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(String(1000))


class BankTransactionMatch(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bank_transaction_matches"
    __table_args__ = (
        UniqueConstraint("bank_transaction_id", name="uq_bank_transaction_matches_transaction"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    bank_transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("bank_transactions.id", ondelete="CASCADE"), index=True
    )
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("journal_entries.id"), index=True
    )
    match_type: Mapped[str] = mapped_column(String(40), nullable=False)
    matched_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(String(1000))
    matched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BankReconciliation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bank_reconciliations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "bank_account_id",
            "statement_end_on",
            name="uq_bank_reconciliations_account_end",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    bank_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("bank_accounts.id"), index=True
    )
    statement_import_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("bank_statement_imports.id"), index=True
    )
    statement_start_on: Mapped[date] = mapped_column(Date, nullable=False)
    statement_end_on: Mapped[date] = mapped_column(Date, nullable=False)
    opening_balance_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    closing_balance_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    calculated_closing_balance_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    difference_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    prepared_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(String(1000))


class OfflineConversionExport(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offline_conversion_exports"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "platform",
            "revenue_record_id",
            name="uq_offline_exports_org_platform_revenue",
        ),
        UniqueConstraint(
            "organization_id",
            "platform",
            "event_key",
            name="uq_offline_exports_org_platform_event",
        ),
        Index(
            "ix_offline_exports_org_status_due",
            "organization_id",
            "status",
            "next_attempt_at",
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
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_record_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_record_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    event_name: Mapped[str] = mapped_column(String(120), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attribution_model: Mapped[str] = mapped_column(String(120), nullable=False)
    consent_basis: Mapped[str] = mapped_column(String(160), nullable=False)
    click_id: Mapped[str] = mapped_column(String(255), nullable=False)
    click_id_type: Mapped[str] = mapped_column(String(80), nullable=False)
    value_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    delivery_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(255))
    provider_response: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class MetaLeadEvent(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "meta_lead_events"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider_lead_id",
            name="uq_meta_lead_events_org_provider_lead",
        ),
        Index(
            "ix_meta_lead_events_org_status_due",
            "organization_id",
            "status",
            "next_attempt_at",
        ),
        Index(
            "ix_meta_lead_events_address_enrichment_due",
            "address_enrichment_status",
            "address_enrichment_next_attempt_at",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    provider_lead_id: Mapped[str] = mapped_column(String(255), nullable=False)
    ingestion_method: Mapped[str] = mapped_column(
        String(80), nullable=False, server_default="zapier", index=True
    )
    page_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    form_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    ad_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    campaign_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lead_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    webhook_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    lead_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    address_enrichment_status: Mapped[str] = mapped_column(
        String(80), nullable=False, server_default="pending", index=True
    )
    address_enrichment_attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    address_enrichment_last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    address_enrichment_next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    address_enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    address_enrichment_last_error: Mapped[str | None] = mapped_column(String(2000))


class StaffLeadAlert(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "staff_lead_alerts"
    __table_args__ = (
        UniqueConstraint(
            "meta_lead_event_id",
            "recipient_user_id",
            name="uq_staff_lead_alerts_event_recipient",
        ),
        UniqueConstraint(
            "organization_id",
            "source_type",
            "source_event_id",
            "recipient_user_id",
            name="uq_staff_lead_alerts_source_recipient",
        ),
        Index(
            "ix_staff_lead_alerts_org_status_due",
            "organization_id",
            "status",
            "next_attempt_at",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    meta_lead_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("meta_lead_events.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    source_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_event_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("leads.id"),
        index=True,
        nullable=True,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    recipient_phone: Mapped[str] = mapped_column(String(40), nullable=False)
    message_body: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    provider_response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)


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
    autonomy_level: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="observe"
    )
    max_cost_microusd_per_run: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="100000"
    )
    max_daily_cost_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="1000000"
    )
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="2")
    rollback_owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))


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


class AiCopilotDefinition(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_copilot_definitions"
    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="uq_ai_copilots_org_key"),
        Index("ix_ai_copilots_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(1200), nullable=False)
    human_owner_role_key: Mapped[str] = mapped_column(String(120), nullable=False)
    human_owner_title: Mapped[str] = mapped_column(String(255), nullable=False)
    human_authority_summary: Mapped[str] = mapped_column(String(1200), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    phase_key: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiCopilotAgentMapping(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_copilot_agent_mappings"
    __table_args__ = (
        UniqueConstraint(
            "copilot_definition_id",
            "agent_definition_id",
            name="uq_ai_copilot_agent_mapping",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    copilot_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_copilot_definitions.id", ondelete="CASCADE"), index=True
    )
    agent_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_agent_definitions.id"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(800), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)


class AiCapabilityContract(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_capability_contracts"
    __table_args__ = (
        UniqueConstraint(
            "copilot_definition_id",
            "capability_key",
            "version_number",
            name="uq_ai_capability_contract_version",
        ),
        Index("ix_ai_capability_contracts_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    copilot_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_copilot_definitions.id", ondelete="CASCADE"), index=True
    )
    capability_key: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    owner_role_key: Mapped[str] = mapped_column(String(120), nullable=False)
    trigger_events: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    input_requirements: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    output_requirements: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    allowed_tool_scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_requirements: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    approval_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    escalation_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    prohibited_actions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiDataGovernancePolicy(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_data_governance_policies"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "key",
            "version_number",
            name="uq_ai_data_governance_policy_version",
        ),
        Index("ix_ai_data_governance_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    key: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_category: Mapped[str] = mapped_column(String(120), nullable=False)
    field_scope: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    source_precedence: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    overwrite_policy: Mapped[str] = mapped_column(String(1600), nullable=False)
    redaction_rule: Mapped[str] = mapped_column(String(1600), nullable=False)
    retention_rule: Mapped[str] = mapped_column(String(1600), nullable=False)
    permitted_role_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiKnowledgeSource(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_knowledge_sources"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "key",
            "version_number",
            name="uq_ai_knowledge_source_version",
        ),
        Index("ix_ai_knowledge_sources_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    key: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    content_reference: Mapped[str] = mapped_column(String(1000), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    owner_role_key: Mapped[str] = mapped_column(String(120), nullable=False)
    audience_role_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    is_authoritative: Mapped[bool] = mapped_column(Boolean, nullable=False)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_checksum: Mapped[str | None] = mapped_column(String(128))
    content_snapshot: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiDataQualityRule(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_data_quality_rules"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "key",
            "version_number",
            name="uq_ai_data_quality_rule_version",
        ),
        Index("ix_ai_data_quality_rules_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    key: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    record_type: Mapped[str] = mapped_column(String(120), nullable=False)
    field_scope: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    rule_type: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    is_deterministic: Mapped[bool] = mapped_column(Boolean, nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    resolution_action: Mapped[str] = mapped_column(String(1000), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiRuntimePolicy(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_runtime_policies"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_ai_runtime_policy_org"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    provider_status: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="disabled"
    )
    emergency_stop: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    emergency_stop_reason: Mapped[str | None] = mapped_column(String(1000))
    high_volume_model: Mapped[str] = mapped_column(String(120), nullable=False)
    default_model: Mapped[str] = mapped_column(String(120), nullable=False)
    escalation_model: Mapped[str] = mapped_column(String(120), nullable=False)
    max_context_characters: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="24000"
    )
    max_requests_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="30"
    )
    max_daily_cost_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="10000000"
    )
    circuit_failure_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="3"
    )
    circuit_cooldown_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="300"
    )
    consecutive_failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    circuit_open_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trace_redaction_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    external_actions_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))


class AiCapabilityRuntimePolicy(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_capability_runtime_policies"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "capability_key",
            name="uq_ai_capability_runtime_org_key",
        ),
        Index(
            "ix_ai_capability_runtime_org_status",
            "organization_id",
            "status",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    agent_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_agent_definitions.id"), index=True
    )
    capability_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="disabled")
    model_route: Mapped[str] = mapped_column(String(40), nullable=False, server_default="default")
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    allowed_tool_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    allowed_knowledge_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1200")
    max_cost_microusd_per_run: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="100000"
    )
    requires_human_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))


class AiExternalActionPolicy(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_external_action_policies"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "action_key",
            name="uq_ai_external_action_policy_org_key",
        ),
        Index(
            "ix_ai_external_action_policy_org_status",
            "organization_id",
            "status",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    action_key: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(1200), nullable=False)
    capability_key: Mapped[str] = mapped_column(String(160), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_role_key: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="control_only")
    audience_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    consent_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    template_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    schedule_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    volume_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    cost_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    quality_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    canary_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    pause_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    rollback_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    prohibited_actions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    dry_run_only: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    external_delivery_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_pause_reason: Mapped[str | None] = mapped_column(String(1000))
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))


class AiExternalActionAttempt(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_external_action_attempts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_ai_external_action_attempt_org_idempotency",
        ),
        Index(
            "ix_ai_external_action_attempt_policy_created",
            "policy_id",
            "created_at",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_external_action_policies.id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    execution_mode: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="simulation"
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    audience_count: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    policy_checks: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    block_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    external_delivery_attempted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    delivered_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))


class AiOrchestratorEvent(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_orchestrator_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "event_key", name="uq_ai_events_org_key"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(120))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(2000))


class AiRunLog(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_run_logs"
    __table_args__ = (
        Index(
            "ix_ai_runs_org_idempotency",
            "organization_id",
            "idempotency_key",
            unique=True,
        ),
    )

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
    orchestrator_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_orchestrator_events.id")
    )
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("ai_run_logs.id"))
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    execution_mode: Mapped[str] = mapped_column(String(40), nullable=False, server_default="manual")
    capability_key: Mapped[str] = mapped_column(
        String(160), nullable=False, server_default="manual"
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    budget_limit_microusd: Mapped[int | None] = mapped_column(BigInteger)
    budget_status: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="within_budget"
    )
    trace_status: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="unreviewed"
    )
    trace_reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id")
    )
    trace_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trace_review_notes: Mapped[str | None] = mapped_column(String(2000))
    rollback_status: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="not_required"
    )


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


class AiKnowledgeUseLog(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_knowledge_use_logs"
    __table_args__ = (
        UniqueConstraint(
            "ai_run_log_id",
            "knowledge_source_id",
            name="uq_ai_knowledge_use_run_source",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    ai_run_log_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_run_logs.id", ondelete="CASCADE"), index=True
    )
    knowledge_source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_knowledge_sources.id"), index=True
    )
    source_key: Mapped[str] = mapped_column(String(160), nullable=False)
    source_version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    content_reference: Mapped[str] = mapped_column(String(1000), nullable=False)


class AiEvaluationDataset(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_evaluation_datasets"
    __table_args__ = (
        UniqueConstraint(
            "agent_definition_id",
            "capability_key",
            "version_number",
            name="uq_ai_eval_dataset_version",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    agent_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_agent_definitions.id"), index=True
    )
    capability_key: Mapped[str] = mapped_column(String(160), nullable=False)
    dataset_key: Mapped[str] = mapped_column(String(160), nullable=False, server_default="manual")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    minimum_case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_pass_rate_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_factual_accuracy_basis_points: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="9000"
    )
    minimum_evidence_coverage_basis_points: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="9000"
    )
    maximum_critical_failures: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum_average_latency_ms: Mapped[int | None] = mapped_column(Integer)
    maximum_average_cost_microusd: Mapped[int | None] = mapped_column(BigInteger)
    owner_role_key: Mapped[str] = mapped_column(String(120), nullable=False, server_default="owner")
    case_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    reviewer_instructions: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    disagreement_policy: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    redaction_policy: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, server_default="{}"
    )
    required_review_scopes: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, server_default="[]"
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiEvaluationCase(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_evaluation_cases"
    __table_args__ = (UniqueConstraint("dataset_id", "case_key", name="uq_ai_eval_case_key"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_evaluation_datasets.id", ondelete="CASCADE"), index=True
    )
    case_key: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    expected_output: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    candidate_output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    deterministic_checks: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    risk_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False)
    case_type: Mapped[str] = mapped_column(String(40), nullable=False, server_default="operating")
    scenario_family: Mapped[str] = mapped_column(
        String(120), nullable=False, server_default="manual"
    )
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, server_default="synthetic")
    source_reference: Mapped[str | None] = mapped_column(String(255))
    redaction_status: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="verified"
    )
    expected_uncertainty: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, server_default="[]"
    )
    required_evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False, server_default="[]")
    prohibited_behaviors: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, server_default="[]"
    )
    reviewer_notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")


class AiEvaluationDatasetReview(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_evaluation_dataset_reviews"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "review_scope",
            name="uq_ai_evaluation_dataset_review_scope",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_evaluation_datasets.id", ondelete="CASCADE"), index=True
    )
    review_scope: Mapped[str] = mapped_column(String(40), nullable=False)
    reviewer_role_key: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    notes: Mapped[str] = mapped_column(String(2000), nullable=False)
    reviewed_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AiEvaluationRun(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_evaluation_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_evaluation_datasets.id"))
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_prompt_versions.id"))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    passed_case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    pass_rate_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    factual_accuracy_basis_points: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    evidence_coverage_basis_points: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    critical_failure_count: Mapped[int] = mapped_column(Integer, nullable=False)
    average_latency_ms: Mapped[int | None] = mapped_column(Integer)
    average_cost_microusd: Mapped[int | None] = mapped_column(BigInteger)
    total_cost_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    thresholds_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiEvaluationResult(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_evaluation_results"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_run_id",
            "evaluation_case_id",
            name="uq_ai_eval_result_case",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    evaluation_case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_evaluation_cases.id")
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    score_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    factual_accuracy_basis_points: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    evidence_coverage_basis_points: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    critical_failure: Mapped[bool] = mapped_column(Boolean, nullable=False)
    actual_output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    check_results: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_microusd: Mapped[int | None] = mapped_column(BigInteger)
    error_message: Mapped[str | None] = mapped_column(String(2000))


class AiEvaluationComparison(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_evaluation_comparisons"
    __table_args__ = (
        UniqueConstraint(
            "baseline_evaluation_run_id",
            "challenger_evaluation_run_id",
            name="uq_ai_evaluation_comparison_runs",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_evaluation_datasets.id"), index=True
    )
    baseline_evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_evaluation_runs.id"), index=True
    )
    challenger_evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_evaluation_runs.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    regression_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quality_delta_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_delta_ms: Mapped[int | None] = mapped_column(Integer)
    cost_delta_microusd: Mapped[int | None] = mapped_column(BigInteger)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))


class AiCapabilityPromotion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_capability_promotions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    agent_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_agent_definitions.id")
    )
    capability_key: Mapped[str] = mapped_column(String(160), nullable=False)
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_evaluation_runs.id"))
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("approval_requests.id")
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    from_level: Mapped[str] = mapped_column(String(40), nullable=False)
    to_level: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    decision_notes: Mapped[str | None] = mapped_column(String(2000))
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rollback_reason: Mapped[str | None] = mapped_column(String(2000))


class Task(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index(
            "uq_tasks_active_primary_lead",
            "organization_id",
            "lead_id",
            unique=True,
            postgresql_where=text(
                "work_kind = 'primary_next_action' "
                "AND status IN ('open', 'in_progress') "
                "AND lead_id IS NOT NULL"
            ),
            sqlite_where=text(
                "work_kind = 'primary_next_action' "
                "AND status IN ('open', 'in_progress') "
                "AND lead_id IS NOT NULL"
            ),
        ),
        Index(
            "uq_tasks_active_primary_deal",
            "organization_id",
            "deal_id",
            unique=True,
            postgresql_where=text(
                "work_kind = 'primary_next_action' "
                "AND status IN ('open', 'in_progress') "
                "AND deal_id IS NOT NULL"
            ),
            sqlite_where=text(
                "work_kind = 'primary_next_action' "
                "AND status IN ('open', 'in_progress') "
                "AND deal_id IS NOT NULL"
            ),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("leads.id"), index=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("deals.id"), index=True)
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    task_type: Mapped[str] = mapped_column(String(120), nullable=False)
    work_kind: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="supporting",
        server_default="supporting",
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    priority: Mapped[str] = mapped_column(String(80), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    outcome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    completion_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    successor_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id"), nullable=True
    )


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
