from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.foundation import (
    Appointment,
    Buyer,
    BuyerCriteria,
    CommunicationRecord,
    ConsentRecord,
    Contact,
    ContactMethod,
    Deal,
    EmailAccount,
    Lead,
    LeadManagementCase,
    LeadQualificationScriptVersion,
    Organization,
    Property,
    Role,
    RoleAssignment,
    Transaction,
    TransactionChecklistItem,
    UnderwritingVersion,
    User,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.inbox import ensure_primary_conversation


@dataclass(frozen=True)
class DemoScenario:
    key: str
    seller_name: str
    email: str
    phone: str
    address: str
    city: str
    postal_code: str
    stage_key: str
    role_owner: str
    motivation: str
    timeline: str
    condition: str
    occupancy: str
    asking_price: str


@dataclass(frozen=True)
class DemoSeedResult:
    organization_slug: str
    users_created: int
    leads_created: int
    leads_reused: int


TEAM_USERS = (
    ("lead.manager@example.test", "Demo Lead Manager", "acquisition_manager"),
    ("closer@example.test", "Demo Acquisitions Closer", "acquisition_rep"),
    ("va.caller@example.test", "Demo VA Caller", "prospecting_caller"),
    ("dispositions@example.test", "Demo Dispositions", "disposition_manager"),
    ("transactions@example.test", "Demo Transaction Coordinator", "transaction_coordinator"),
)

SCENARIOS = (
    DemoScenario(
        key="new-inbound",
        seller_name="Jordan Ellis",
        email="jordan.ellis@example.test",
        phone="+14045550101",
        address="100 Demo Oak Lane",
        city="Atlanta",
        postal_code="30310",
        stage_key="new",
        role_owner="acquisition_manager",
        motivation="Inherited property and wants to understand available options.",
        timeline="Within 90 days",
        condition="Needs cosmetic updates",
        occupancy="Vacant",
        asking_price="$245,000",
    ),
    DemoScenario(
        key="qualification",
        seller_name="Maria Thompson",
        email="maria.thompson@example.test",
        phone="+16785550102",
        address="200 Sample Creek Drive",
        city="Decatur",
        postal_code="30032",
        stage_key="qualification_in_progress",
        role_owner="acquisition_manager",
        motivation="Relocating for work and does not want to complete repairs.",
        timeline="Within 30 days",
        condition="Kitchen and roof need review",
        occupancy="Owner occupied",
        asking_price="$210,000",
    ),
    DemoScenario(
        key="appointment",
        seller_name="Samuel Reed",
        email="samuel.reed@example.test",
        phone="+17705550103",
        address="300 Fictional Mill Road",
        city="Marietta",
        postal_code="30060",
        stage_key="appointment_scheduled",
        role_owner="acquisition_rep",
        motivation="Managing a rental from out of state and wants a simple sale.",
        timeline="Within 45 days",
        condition="Moderate renovation",
        occupancy="Tenant occupied",
        asking_price="$275,000",
    ),
    DemoScenario(
        key="under-contract",
        seller_name="Denise Walker",
        email="denise.walker@example.test",
        phone="+14705550104",
        address="400 Training House Court",
        city="Stone Mountain",
        postal_code="30083",
        stage_key="under_contract",
        role_owner="acquisition_rep",
        motivation="Downsizing after retirement.",
        timeline="Contract executed",
        condition="Major systems serviceable; interior renovation needed",
        occupancy="Owner occupied",
        asking_price="$185,000",
    ),
)


def seed_demo_workspace(
    db: Session,
    *,
    organization_name: str,
    owner_email: str,
    owner_name: str,
) -> DemoSeedResult:
    foundation = bootstrap_foundation(
        db,
        organization_name=organization_name,
        admin_email=owner_email,
        admin_name=owner_name,
    )
    organization = foundation.organization
    users_by_role: dict[str, User] = {}
    users_created = 0
    for email, display_name, role_key in TEAM_USERS:
        user, created = ensure_demo_user(db, organization, email, display_name, role_key)
        users_by_role[role_key] = user
        users_created += int(created)

    leads_created = 0
    leads_reused = 0
    qualification_script = ensure_demo_qualification_script(
        db,
        organization,
        foundation.admin_user or users_by_role["acquisition_manager"],
    )
    for scenario in SCENARIOS:
        lead, created = ensure_demo_lead(
            db,
            organization,
            scenario,
            assigned_user=users_by_role[scenario.role_owner],
        )
        leads_created += int(created)
        leads_reused += int(not created)
        ensure_demo_timeline(db, lead, scenario)
        ensure_demo_lead_manager_case(
            db,
            lead,
            scenario,
            users_by_role["acquisition_manager"],
            qualification_script,
        )
        if scenario.key == "appointment":
            ensure_demo_appointment(db, lead, users_by_role["acquisition_rep"])
            ensure_demo_underwriting(db, lead, users_by_role["acquisition_rep"])
        if scenario.key == "under-contract":
            ensure_demo_transaction(db, lead, users_by_role["transaction_coordinator"])
    ensure_demo_buyers(db, organization)
    ensure_demo_email_account(db, organization, users_by_role["acquisition_manager"])
    db.commit()
    return DemoSeedResult(
        organization_slug=organization.slug,
        users_created=users_created,
        leads_created=leads_created,
        leads_reused=leads_reused,
    )


def ensure_demo_qualification_script(
    db: Session,
    organization: Organization,
    approver: User,
) -> LeadQualificationScriptVersion:
    existing = db.scalar(
        select(LeadQualificationScriptVersion).where(
            LeadQualificationScriptVersion.organization_id == organization.id,
            LeadQualificationScriptVersion.status == "approved",
        )
    )
    if existing is not None:
        return existing
    now = datetime.now(UTC)
    questions = [
        {
            "key": key,
            "label": label,
            "prompt": prompt,
            "answer_type": "text",
            "choices": [],
            "required": required,
        }
        for key, label, prompt, required in (
            ("ownership", "Ownership", "Who owns the property and how is title held?", True),
            ("decision_makers", "Decision makers", "Who must approve a sale?", True),
            ("motivation", "Motivation", "What is driving the possible sale?", True),
            ("timeline", "Timeline", "When would the seller ideally close?", True),
            ("property_condition", "Condition", "What repairs or updates are needed?", True),
            ("occupancy", "Occupancy", "Who occupies the property?", True),
            ("asking_price", "Price expectation", "Does the seller have a price in mind?", False),
        )
    ]
    script = LeadQualificationScriptVersion(
        organization_id=organization.id,
        version_number=1,
        title="Stonegate Demo Seller Qualification",
        status="approved",
        introduction="Confirm the seller's situation before recommending the next action.",
        questions=questions,
        completion_rules={
            "require_all_required_questions": True,
            "require_dated_next_action": True,
        },
        created_by_user_id=approver.id,
        approved_by_user_id=approver.id,
        approved_at=now,
    )
    db.add(script)
    db.flush()
    return script


def ensure_demo_lead_manager_case(
    db: Session,
    lead: Lead,
    scenario: DemoScenario,
    lead_manager: User,
    script: LeadQualificationScriptVersion,
) -> None:
    existing = db.scalar(select(LeadManagementCase).where(LeadManagementCase.lead_id == lead.id))
    if existing is not None:
        return
    now = datetime.now(UTC)
    accepted_at = None if scenario.key == "new-inbound" else now - timedelta(minutes=18)
    qualification_completed_at = (
        now - timedelta(minutes=8)
        if scenario.key in {"appointment", "under-contract"}
        else None
    )
    next_action_due_at = (
        now + timedelta(days=1) if scenario.key == "appointment" else None
    )
    status = {
        "new-inbound": "awaiting_acceptance",
        "qualification": "active",
        "appointment": "appointment_set",
        "under-contract": "closed",
    }[scenario.key]
    db.add(
        LeadManagementCase(
            organization_id=lead.organization_id,
            lead_id=lead.id,
            handoff_id=None,
            assigned_user_id=lead_manager.id,
            status=status,
            acceptance_due_at=now + timedelta(minutes=20),
            accepted_at=accepted_at,
            accepted_by_user_id=lead_manager.id if accepted_at else None,
            escalated_at=None,
            qualification_script_version_id=(
                script.id if qualification_completed_at is not None else None
            ),
            qualification_started_at=accepted_at,
            qualification_completed_at=qualification_completed_at,
            qualification_quality_basis_points=(10000 if qualification_completed_at else None),
            next_action_type="appointment" if scenario.key == "appointment" else None,
            next_action_due_at=next_action_due_at,
            last_contact_at=now - timedelta(hours=2),
            closed_at=now if status == "closed" else None,
        )
    )


def ensure_demo_email_account(
    db: Session,
    organization: Organization,
    user: User,
) -> None:
    email_address = "inbox@stonegate.example.test"
    existing = db.scalar(
        select(EmailAccount).where(
            EmailAccount.organization_id == organization.id,
            EmailAccount.provider == "simulated",
            EmailAccount.email_address == email_address,
        )
    )
    if existing is not None:
        return
    db.add(
        EmailAccount(
            organization_id=organization.id,
            user_id=user.id,
            connected_by_user_id=user.id,
            provider="simulated",
            provider_account_id="stonegate-demo-mailbox",
            email_address=email_address,
            display_name="Stonegate Demo Inbox",
            status="active",
            is_shared=True,
            sync_enabled=False,
            encrypted_access_token=None,
            encrypted_refresh_token="simulation-only",
            access_token_expires_at=None,
            history_cursor=None,
            last_synced_at=None,
            last_error=None,
            signature_text="Stonegate Home Buyers\nSynthetic demonstration mailbox",
            account_metadata={"synthetic": True},
        )
    )


def ensure_demo_user(
    db: Session,
    organization: Organization,
    email: str,
    display_name: str,
    role_key: str,
) -> tuple[User, bool]:
    user = db.scalar(
        select(User).where(User.organization_id == organization.id, User.email == email)
    )
    created = user is None
    if user is None:
        user = User(
            organization_id=organization.id,
            email=email,
            display_name=display_name,
            external_auth_id=None,
            is_active=True,
        )
        db.add(user)
        db.flush()
    role = db.scalar(
        select(Role).where(Role.organization_id == organization.id, Role.key == role_key)
    )
    if role is None:
        raise RuntimeError(f"Demo role {role_key} is unavailable.")
    assignment = db.scalar(
        select(RoleAssignment).where(
            RoleAssignment.organization_id == organization.id,
            RoleAssignment.user_id == user.id,
            RoleAssignment.role_id == role.id,
        )
    )
    if assignment is None:
        db.add(
            RoleAssignment(
                organization_id=organization.id,
                user_id=user.id,
                role_id=role.id,
            )
        )
    return user, created


def ensure_demo_lead(
    db: Session,
    organization: Organization,
    scenario: DemoScenario,
    *,
    assigned_user: User,
) -> tuple[Lead, bool]:
    contact_method = db.scalar(
        select(ContactMethod).where(
            ContactMethod.organization_id == organization.id,
            ContactMethod.method_type == "email",
            ContactMethod.normalized_value == scenario.email,
        )
    )
    if contact_method is not None:
        existing = db.scalar(
            select(Lead).where(
                Lead.organization_id == organization.id,
                Lead.contact_id == contact_method.contact_id,
                Lead.source == "demo_seed",
            )
        )
        if existing is not None:
            return existing, False

    contact = Contact(
        organization_id=organization.id,
        legal_name=scenario.seller_name,
        preferred_name=scenario.seller_name.split()[0],
        contact_type="seller",
        assigned_user_id=assigned_user.id,
    )
    db.add(contact)
    db.flush()
    db.add_all(
        [
            ContactMethod(
                organization_id=organization.id,
                contact_id=contact.id,
                method_type="email",
                value=scenario.email,
                normalized_value=scenario.email,
                is_primary=False,
            ),
            ContactMethod(
                organization_id=organization.id,
                contact_id=contact.id,
                method_type="phone",
                value=scenario.phone,
                normalized_value="".join(
                    character for character in scenario.phone if character.isdigit()
                ),
                is_primary=True,
            ),
        ]
    )
    for channel in ("phone", "email", "sms"):
        db.add(
            ConsentRecord(
                organization_id=organization.id,
                contact_id=contact.id,
                channel=channel,
                status="granted",
                source="demo_seed",
                wording_version="synthetic-demo-v1",
                wording="Synthetic local demonstration record. No external contact is permitted.",
                captured_ip=None,
                user_agent="stonegate-demo-seed",
            )
        )
    property_record = Property(
        organization_id=organization.id,
        street_address=scenario.address,
        city=scenario.city,
        state="GA",
        postal_code=scenario.postal_code,
        county=None,
        property_type="single_family",
        normalized_address_key=f"{scenario.address}|{scenario.city}|GA|{scenario.postal_code}".lower(),
    )
    db.add(property_record)
    db.flush()
    lead = Lead(
        organization_id=organization.id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=assigned_user.id,
        source="demo_seed",
        stage_key=scenario.stage_key,
        lead_temperature="hot" if scenario.stage_key != "new" else "warm",
        motivation=scenario.motivation,
        desired_timeline=scenario.timeline,
        property_condition=scenario.condition,
        occupancy_status=scenario.occupancy,
        asking_price=scenario.asking_price,
        mortgage_balance="Unknown",
        appointment_status="scheduled" if scenario.key == "appointment" else None,
        next_follow_up_at=datetime.now(UTC) + timedelta(days=1),
        archived_at=None,
    )
    db.add(lead)
    db.flush()
    conversation = ensure_primary_conversation(db, lead)
    conversation.queue_key = {
        "new": "unassigned",
        "qualification_in_progress": "acquisitions_follow_up",
        "appointment_scheduled": "appointment_set",
        "under_contract": "acquisitions_follow_up",
    }[scenario.stage_key]
    return lead, True


def ensure_demo_timeline(db: Session, lead: Lead, scenario: DemoScenario) -> None:
    conversation = ensure_primary_conversation(db, lead)
    provider_message_id = f"demo:{scenario.key}:seller-note"
    existing = db.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.organization_id == lead.organization_id,
            CommunicationRecord.provider == "simulated",
            CommunicationRecord.provider_message_id == provider_message_id,
        )
    )
    if existing is not None:
        return
    occurred_at = datetime.now(UTC) - timedelta(hours=2)
    db.add(
        CommunicationRecord(
            organization_id=lead.organization_id,
            conversation_id=conversation.id,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            actor_user_id=None,
            direction="inbound",
            channel="call",
            status="completed",
            provider="simulated",
            provider_message_id=provider_message_id,
            subject=None,
            body=f"Synthetic seller conversation: {scenario.motivation}",
            occurred_at=occurred_at,
            external_payload={"simulated": True},
            communication_metadata={"source": "demo_seed", "synthetic": True},
        )
    )
    conversation.last_activity_at = occurred_at
    conversation.last_inbound_at = occurred_at
    conversation.unread_count = 1


def ensure_demo_appointment(db: Session, lead: Lead, closer: User) -> None:
    existing = db.scalar(select(Appointment).where(Appointment.lead_id == lead.id))
    if existing is not None:
        return
    start = (datetime.now(UTC) + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    property_record = db.get(Property, lead.property_id)
    db.add(
        Appointment(
            organization_id=lead.organization_id,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            property_id=lead.property_id,
            owner_user_id=closer.id,
            appointment_type="property_visit",
            status="scheduled",
            scheduled_start_at=start,
            scheduled_end_at=start + timedelta(hours=1),
            location_type="property",
            location=(
                f"{property_record.street_address}, {property_record.city}, GA "
                f"{property_record.postal_code}"
                if property_record
                else None
            ),
            notes="Synthetic appointment for local workflow testing.",
            outcome=None,
            external_calendar_id=None,
            appointment_metadata={"source": "demo_seed", "synthetic": True},
        )
    )


def ensure_demo_underwriting(db: Session, lead: Lead, closer: User) -> None:
    existing = db.scalar(select(UnderwritingVersion).where(UnderwritingVersion.lead_id == lead.id))
    if existing is not None:
        return
    db.add(
        UnderwritingVersion(
            organization_id=lead.organization_id,
            lead_id=lead.id,
            property_id=lead.property_id,
            created_by_user_id=closer.id,
            version_number=1,
            status="draft",
            arv_low_cents=31_000_000,
            arv_high_cents=33_000_000,
            repair_low_cents=5_000_000,
            repair_high_cents=7_000_000,
            max_offer_cents=17_500_000,
            recommended_offer_cents=16_500_000,
            offer_strategy="assignment",
            notes="Synthetic underwriting used for local demonstrations only.",
            source="demo_seed",
            underwriting_metadata={"synthetic": True},
        )
    )


def ensure_demo_transaction(db: Session, lead: Lead, coordinator: User) -> None:
    deal = db.scalar(select(Deal).where(Deal.lead_id == lead.id))
    if deal is None:
        deal = Deal(
            organization_id=lead.organization_id,
            lead_id=lead.id,
            property_id=lead.property_id,
            stage_key="under_contract",
            contract_price_cents=15_000_000,
            assignment_fee_cents=2_000_000,
        )
        db.add(deal)
        db.flush()
    transaction = db.scalar(select(Transaction).where(Transaction.deal_id == deal.id))
    if transaction is not None:
        return
    now = datetime.now(UTC)
    transaction = Transaction(
        organization_id=lead.organization_id,
        deal_id=deal.id,
        lead_id=lead.id,
        property_id=lead.property_id,
        contact_id=lead.contact_id,
        owner_user_id=coordinator.id,
        status="open",
        contract_type="assignment",
        purchase_price_cents=15_000_000,
        assignment_fee_cents=2_000_000,
        earnest_money_cents=100_000,
        title_company="Synthetic Georgia Closing Attorney",
        closing_date=now + timedelta(days=21),
        inspection_period_days=10,
        contract_sent_at=now - timedelta(days=1),
        contract_executed_at=now - timedelta(hours=12),
        notes="Synthetic transaction for local workflow testing.",
        transaction_metadata={"source": "demo_seed", "synthetic": True},
    )
    db.add(transaction)
    db.flush()
    for index, title in enumerate(
        ("Send file to closing attorney", "Confirm earnest money", "Review title status"),
        start=1,
    ):
        db.add(
            TransactionChecklistItem(
                organization_id=lead.organization_id,
                transaction_id=transaction.id,
                responsible_user_id=coordinator.id,
                title=title,
                status="open",
                due_at=now + timedelta(days=index),
                completed_at=None,
                sort_order=index,
            )
        )


def ensure_demo_buyers(db: Session, organization: Organization) -> None:
    for name, email, markets, max_price in (
        ("Demo Renovation Partners", "buyers.one@example.test", "Atlanta, Decatur", 25_000_000),
        ("Sample Rental Group", "buyers.two@example.test", "Marietta, Stone Mountain", 30_000_000),
    ):
        buyer = db.scalar(
            select(Buyer).where(Buyer.organization_id == organization.id, Buyer.email == email)
        )
        if buyer is not None:
            continue
        buyer = Buyer(
            organization_id=organization.id,
            name=name,
            company_name=name,
            email=email,
            phone=None,
            buyer_type="cash_investor",
            status="active",
            proof_of_funds_status="verified",
            max_purchase_price_cents=max_price,
            notes="Synthetic buyer for local workflow testing.",
        )
        db.add(buyer)
        db.flush()
        db.add(
            BuyerCriteria(
                organization_id=organization.id,
                buyer_id=buyer.id,
                markets=markets,
                property_types="single_family",
                min_price_cents=5_000_000,
                max_price_cents=max_price,
                rehab_levels="cosmetic, moderate, heavy",
                notes="Synthetic criteria.",
            )
        )
