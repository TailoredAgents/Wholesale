from unittest.mock import Mock
from uuid import uuid4

from sqlalchemy.orm import Session

from app.integrations.openai_client import validate_strict_json_schema
from app.models.foundation import CallRecord, CallRecording, CallTranscript, Lead, Property
from app.schemas.voice import CallNoteEvidence, LandStructuredCallNotes, StructuredCallNotes
from app.services.call_intelligence import (
    LAND_QUALIFICATION_FIELDS,
    auto_populate_call_note_fields,
    call_notes_model_for_asset,
    call_notes_system_prompt,
    format_approved_notes,
    resolve_transcript_asset_class,
)


def land_notes(*, parcel_evidence: str = "The APN is 12-345-678-901.") -> LandStructuredCallNotes:
    land_values = {
        "parcel_id": "12-345-678-901",
        "acreage": "5.2 acres",
        "legal_description": "Seller referred to tract 4 in the recorded plat.",
        "access_or_frontage": "Seller reports 240 feet of frontage on County Road 8.",
        "utilities": "Seller says power is at the road; water availability is unknown.",
        "zoning_or_use": "Seller believes it is agricultural and wants it sold as homesite land.",
        "septic_or_perc": "Seller says no perc test has been completed.",
        "taxes_or_hoa": "$640 annual tax; seller reports no HOA.",
        "terrain_or_environmental_concerns": (
            "Seller reports a creek at the rear and does not know the flood status."
        ),
    }
    evidence_text = {
        **{field: f"Seller explicitly discussed {value}" for field, value in land_values.items()},
        "parcel_id": parcel_evidence,
    }
    return LandStructuredCallNotes(
        summary="Seller discussed selling a vacant 5.2-acre tract.",
        motivation="No longer plans to keep the land",
        timeline="Within 60 days",
        property_condition=None,
        occupancy_status="Vacant land",
        asking_price="$75,000",
        mortgage_balance=None,
        mortgage_or_title=None,
        repairs=[],
        objections=[],
        commitments=[],
        next_action="Verify parcel records and call the seller",
        follow_up_at=None,
        appointment_details=None,
        confidence=86,
        evidence=[
            CallNoteEvidence(
                field=field,
                segment_index=index,
                start_seconds=float(index),
                supporting_text=evidence_text[field],
            )
            for index, field in enumerate(LAND_QUALIFICATION_FIELDS)
        ],
        **land_values,
    )


def test_house_schema_and_prompt_remain_unchanged_while_land_schema_is_strict() -> None:
    house_schema = StructuredCallNotes.model_json_schema()
    land_schema = LandStructuredCallNotes.model_json_schema()

    validate_strict_json_schema(house_schema)
    validate_strict_json_schema(land_schema)
    assert set(house_schema["properties"]) == set(house_schema["required"])
    assert set(land_schema["properties"]) == set(land_schema["required"])
    assert not (set(LAND_QUALIFICATION_FIELDS) & set(house_schema["properties"]))
    assert set(LAND_QUALIFICATION_FIELDS) <= set(land_schema["properties"])
    assert call_notes_model_for_asset("house") is StructuredCallNotes
    assert call_notes_model_for_asset("land") is LandStructuredCallNotes
    house_prompt = call_notes_system_prompt("house prompt", "house")
    assert house_prompt.startswith("house prompt")
    assert "clear English using Latin-script" in house_prompt
    land_prompt = call_notes_system_prompt("house prompt", "land")
    assert "Never conclude or" in land_prompt
    assert "buildability" in land_prompt
    assert "unverified seller statements" in land_prompt


def test_land_call_notes_fill_only_empty_evidence_backed_crm_fields() -> None:
    lead = Lead(
        organization_id=uuid4(),
        contact_id=uuid4(),
        property_id=uuid4(),
        assigned_user_id=None,
        source="inbound_call",
        asset_class="land",
        qualification_context={"utilities": "County utility map verified water at road"},
        stage_key="contacted",
        lead_temperature=None,
        motivation="Existing motivation",
        desired_timeline=None,
        property_condition=None,
        occupancy_status=None,
        asking_price=None,
        mortgage_balance=None,
        appointment_status=None,
        next_follow_up_at=None,
        archived_at=None,
    )
    property_record = Property(
        organization_id=lead.organization_id,
        street_address="0 County Road 8",
        city="Macon",
        state="GA",
        postal_code="31201",
        county="Bibb",
        property_type="land",
        parcel_id=None,
        normalized_address_key=None,
    )

    populated = auto_populate_call_note_fields(
        lead,
        land_notes(),
        property_record=property_record,
    )

    assert lead.motivation == "Existing motivation"
    assert lead.desired_timeline == "Within 60 days"
    assert lead.occupancy_status == "Vacant land"
    assert lead.asking_price == "$75,000"
    assert lead.qualification_context["acreage"] == "5.2 acres"
    assert lead.qualification_context["utilities"] == ("County utility map verified water at road")
    assert lead.qualification_context["parcel_id"] == "12-345-678-901"
    assert property_record.parcel_id == "12-345-678-901"
    assert "qualification_context.acreage" in populated
    assert "qualification_context.utilities" not in populated
    assert populated["property.parcel_id"] == "12-345-678-901"
    approved_note = format_approved_notes(land_notes())
    assert "Parcel/APN (seller stated): 12-345-678-901" in approved_note
    assert "Zoning/intended use (unverified):" in approved_note


def test_land_parcel_is_not_filled_without_matching_explicit_evidence() -> None:
    lead = Lead(
        organization_id=uuid4(),
        contact_id=uuid4(),
        property_id=uuid4(),
        assigned_user_id=None,
        source="inbound_call",
        asset_class="land",
        qualification_context={},
        stage_key="contacted",
        lead_temperature=None,
        motivation=None,
        desired_timeline=None,
        property_condition=None,
        occupancy_status=None,
        asking_price=None,
        mortgage_balance=None,
        appointment_status=None,
        next_follow_up_at=None,
        archived_at=None,
    )
    property_record = Property(
        organization_id=lead.organization_id,
        street_address="0 Unknown Road",
        city="Macon",
        state="GA",
        postal_code="31201",
        county="Bibb",
        property_type="land",
        parcel_id=None,
        normalized_address_key=None,
    )

    populated = auto_populate_call_note_fields(
        lead,
        land_notes(parcel_evidence="Seller said the parcel number is 99-999."),
        property_record=property_record,
    )

    assert property_record.parcel_id is None
    assert "parcel_id" not in lead.qualification_context
    assert "property.parcel_id" not in populated


def test_transcript_asset_resolution_uses_the_linked_lead() -> None:
    recording = CallRecording(id=uuid4(), call_record_id=uuid4())
    call = CallRecord(id=recording.call_record_id, lead_id=uuid4())
    lead = Lead(id=call.lead_id, asset_class="land")
    transcript = CallTranscript(
        id=uuid4(),
        recording_id=recording.id,
        transcript_metadata={"asset_class": "house"},
    )
    db = Mock(spec=Session)
    records = {
        (CallRecording, transcript.recording_id): recording,
        (CallRecord, recording.call_record_id): call,
        (Lead, call.lead_id): lead,
    }
    db.get.side_effect = lambda model, record_id: records.get((model, record_id))

    assert resolve_transcript_asset_class(db, transcript) == "land"
