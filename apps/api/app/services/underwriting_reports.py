from io import BytesIO
from uuid import UUID

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    Contact,
    Lead,
    Property,
    UnderwritingMarketAnalysis,
    UnderwritingVersion,
)


def build_market_analysis_pdf(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    analysis_id: UUID,
) -> tuple[bytes, str] | None:
    analysis = db.scalar(
        select(UnderwritingMarketAnalysis).where(
            UnderwritingMarketAnalysis.organization_id == principal.organization_id,
            UnderwritingMarketAnalysis.lead_id == lead_id,
            UnderwritingMarketAnalysis.id == analysis_id,
        )
    )
    if analysis is None:
        return None

    lead = db.get(Lead, analysis.lead_id)
    property_record = db.get(Property, analysis.property_id)
    contact = db.get(Contact, lead.contact_id) if lead else None
    underwriting_version = (
        db.get(UnderwritingVersion, analysis.underwriting_version_id)
        if analysis.underwriting_version_id
        else None
    )
    if lead is None or property_record is None:
        return None

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.45 * inch,
        leftMargin=0.45 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
        title="Underwriting Comp Report",
    )
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    heading_style = styles["Heading2"]
    body_style = styles["BodyText"]
    small_style = ParagraphStyle(
        "Small",
        parent=body_style,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#4f5658"),
    )

    story: list[object] = [
        Paragraph("Underwriting Comp Report", title_style),
        Paragraph("Stonegate Home Buyers", small_style),
        Spacer(1, 0.15 * inch),
        Paragraph("Deal Summary", heading_style),
        key_value_table(
            [
                ("Seller", contact.legal_name if contact else "Unknown"),
                ("Property", format_property_address(property_record)),
                ("Provider", analysis.provider),
                ("Report created", analysis.created_at.strftime("%b %-d, %Y %I:%M %p")),
                (
                    "Draft underwriting version",
                    str(underwriting_version.version_number) if underwriting_version else "None",
                ),
                ("Human review required", "Yes"),
            ]
        ),
        Spacer(1, 0.12 * inch),
        Paragraph("Valuation And Offer Screen", heading_style),
        key_value_table(
            [
                ("Provider value", format_money(analysis.estimated_value_cents)),
                (
                    "Provider value range",
                    f"{format_money(analysis.estimated_value_low_cents)} to "
                    f"{format_money(analysis.estimated_value_high_cents)}",
                ),
                (
                    "Draft ARV range",
                    format_money_range(analysis.arv_low_cents, analysis.arv_high_cents),
                ),
                (
                    "Repair range",
                    f"{format_money(analysis.repair_low_cents)} to "
                    f"{format_money(analysis.repair_high_cents)}",
                ),
                (
                    "Offer ceiling range",
                    format_money_range(analysis.mao_low_cents, analysis.mao_high_cents),
                ),
                ("Recommended starting offer", format_money(analysis.recommended_offer_cents)),
                ("Assignment fee assumption", format_money(analysis.assignment_fee_cents)),
                ("Confidence", f"{analysis.confidence_score}%"),
            ]
        ),
        Spacer(1, 0.12 * inch),
        Paragraph("Formula Used", heading_style),
        Paragraph(
            "Low offer ceiling = ARV low x "
            f"{analysis.offer_low_percentage}% - repair high - assignment fee.",
            body_style,
        ),
        Paragraph(
            "High offer ceiling = ARV high x "
            f"{analysis.offer_high_percentage}% - repair low - assignment fee.",
            body_style,
        ),
        Paragraph(
            "This is a screening method only. Review condition, neighborhood, title, buyer demand, "
            "and seller context before approving ARV or making an offer.",
            small_style,
        ),
        Spacer(1, 0.12 * inch),
        Paragraph("Selected Comps", heading_style),
        comp_table(analysis.selected_comps),
        Spacer(1, 0.12 * inch),
        Paragraph("Rejected / Context Comps", heading_style),
        comp_table(analysis.rejected_comps),
        Spacer(1, 0.12 * inch),
        Paragraph("Review Checklist", heading_style),
        Paragraph(
            "Confirm property condition, square footage, bedroom/bath count, neighborhood "
            "boundary, sale dates, seller timeline, repair budget, and buyer appetite "
            "before approving.",
            body_style,
        ),
    ]

    document.build(story)
    filename = f"underwriting-comp-report-{analysis.id}.pdf"
    return buffer.getvalue(), filename


def key_value_table(rows: list[tuple[str, str]]) -> Table:
    table = Table(rows, colWidths=[1.9 * inch, 4.6 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f2f0ea")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#202426")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d8d2c7")),
                ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, colors.HexColor("#fbfaf7")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def comp_table(comps: list[dict[str, object]]) -> Table:
    rows: list[list[str]] = [["Address", "Price", "Sqft", "Dist", "Age", "Score", "Reason"]]
    for comp in comps[:10]:
        rows.append(
            [
                safe_string(comp.get("formatted_address")),
                format_money(optional_int(comp.get("price_cents"))),
                safe_string(comp.get("square_footage")),
                format_distance(comp.get("distance_miles")),
                format_days(comp.get("days_old")),
                safe_string(comp.get("score")),
                safe_string(comp.get("selection_reason")),
            ]
        )
    if len(rows) == 1:
        rows.append(["No comps saved.", "", "", "", "", "", ""])

    table = Table(
        rows,
        colWidths=[
            1.55 * inch,
            0.78 * inch,
            0.55 * inch,
            0.48 * inch,
            0.5 * inch,
            0.5 * inch,
            2.15 * inch,
        ],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#263238")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d8d2c7")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fbfaf7")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def format_property_address(property_record: Property) -> str:
    return (
        f"{property_record.street_address}, {property_record.city}, "
        f"{property_record.state} {property_record.postal_code}"
    )


def format_money(cents: int | None) -> str:
    if cents is None:
        return "Unknown"
    return f"${cents / 100:,.0f}"


def format_money_range(low_cents: int | None, high_cents: int | None) -> str:
    return f"{format_money(low_cents)} to {format_money(high_cents)}"


def format_distance(value: object) -> str:
    number = optional_float(value)
    return "Unknown" if number is None else f"{number:.1f} mi"


def format_days(value: object) -> str:
    number = optional_int(value)
    return "Unknown" if number is None else f"{number} days"


def safe_string(value: object) -> str:
    if value is None:
        return "Unknown"
    return str(value)


def optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value)
    if isinstance(value, str):
        try:
            return round(float(value))
        except ValueError:
            return None
    return None


def optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
