import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
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
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )


class CommunicationRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "communication_records"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
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
    body: Mapped[str] = mapped_column(String(4000), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    external_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    communication_metadata: Mapped[dict[str, Any] | None] = mapped_column(
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


class CompensationRule(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compensation_rules"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
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
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class AiToolCallLog(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_tool_call_logs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), index=True
    )
    ai_run_log_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_run_logs.id"), index=True
    )
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
