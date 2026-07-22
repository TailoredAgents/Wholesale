from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import Any, Literal
from uuid import UUID
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.doctemplate import BaseDocTemplate
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

ReportAudience = Literal["investor", "client"]

BRAND = colors.HexColor("#245F43")
BRAND_DARK = colors.HexColor("#183A2B")
BRAND_SOFT = colors.HexColor("#EAF3ED")
GOLD = colors.HexColor("#B18436")
INK = colors.HexColor("#18201D")
TEXT = colors.HexColor("#37413D")
MUTED = colors.HexColor("#68716D")
LINE = colors.HexColor("#D9D7CF")
SURFACE = colors.HexColor("#F6F4EF")
WHITE = colors.white
WARNING = colors.HexColor("#8A5A16")
WARNING_SOFT = colors.HexColor("#FFF6E4")


@dataclass(frozen=True)
class ReportContext:
    analysis: UnderwritingMarketAnalysis
    lead: Lead
    property_record: Property
    contact: Contact | None
    underwriting_version: UnderwritingVersion | None

    @property
    def address(self) -> str:
        return format_property_address(self.property_record)

    @property
    def seller_name(self) -> str:
        return self.contact.legal_name if self.contact else "Property owner"

    @property
    def seller_first_name(self) -> str:
        preferred = self.contact.preferred_name if self.contact else None
        return preferred or self.seller_name.split()[0]

    @property
    def analysis_reference(self) -> str:
        return str(self.analysis.id).split("-")[0].upper()

    @property
    def version_label(self) -> str:
        if self.underwriting_version is None:
            return "Unlinked"
        return f"Version {self.underwriting_version.version_number}"


def build_market_analysis_pdf(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    analysis_id: UUID,
    *,
    audience: ReportAudience = "investor",
) -> tuple[bytes, str] | None:
    context = load_report_context(db, principal, lead_id, analysis_id)
    if context is None:
        return None

    title = (
        "Stonegate Internal Investment Analysis"
        if audience == "investor"
        else "Stonegate Property Value Review"
    )
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.72 * inch,
        bottomMargin=0.62 * inch,
        title=title,
        author="Stonegate Home Buyers",
        subject=f"{context.address} - saved comp analysis {context.analysis_reference}",
        pageCompression=0,
    )
    styles = report_styles()
    story = (
        build_investor_story(context, styles)
        if audience == "investor"
        else build_client_story(context, styles)
    )
    decorator = page_decorator(context, audience)
    document.build(story, onFirstPage=decorator, onLaterPages=decorator)

    filename = (
        f"stonegate-{audience}-property-report-"
        f"{slugify(context.property_record.street_address)}-{context.analysis_reference.lower()}.pdf"
    )
    return buffer.getvalue(), filename


def load_report_context(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    analysis_id: UUID,
) -> ReportContext | None:
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
    if lead is None or property_record is None:
        return None

    contact = db.get(Contact, lead.contact_id)
    underwriting_version = (
        db.get(UnderwritingVersion, analysis.underwriting_version_id)
        if analysis.underwriting_version_id
        else None
    )
    return ReportContext(
        analysis=analysis,
        lead=lead,
        property_record=property_record,
        contact=contact,
        underwriting_version=underwriting_version,
    )


def report_styles() -> dict[str, ParagraphStyle]:
    samples = getSampleStyleSheet()
    body = ParagraphStyle(
        "ReportBody",
        parent=samples["BodyText"],
        fontName="Helvetica",
        fontSize=9.2,
        leading=13.5,
        textColor=TEXT,
        spaceAfter=6,
    )
    return {
        "body": body,
        "small": ParagraphStyle(
            "ReportSmall",
            parent=body,
            fontSize=7.4,
            leading=10.2,
            textColor=MUTED,
            spaceAfter=3,
        ),
        "eyebrow": ParagraphStyle(
            "ReportEyebrow",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=7.6,
            leading=9,
            textColor=BRAND,
            spaceAfter=5,
        ),
        "hero": ParagraphStyle(
            "ReportHero",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=23,
            leading=26,
            textColor=WHITE,
            spaceAfter=7,
        ),
        "hero_subtitle": ParagraphStyle(
            "ReportHeroSubtitle",
            parent=body,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#DDEBE3"),
            spaceAfter=0,
        ),
        "section": ParagraphStyle(
            "ReportSection",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=INK,
            spaceBefore=4,
            spaceAfter=8,
        ),
        "subsection": ParagraphStyle(
            "ReportSubsection",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=12,
            textColor=INK,
            spaceAfter=4,
        ),
        "metric_label": ParagraphStyle(
            "MetricLabel",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=9,
            textColor=MUTED,
            spaceAfter=4,
        ),
        "metric_value": ParagraphStyle(
            "MetricValue",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=17,
            textColor=BRAND_DARK,
            spaceAfter=0,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=6.6,
            leading=8.2,
            textColor=WHITE,
            alignment=TA_LEFT,
            spaceAfter=0,
        ),
        "table_cell": ParagraphStyle(
            "TableCell",
            parent=body,
            fontSize=7.1,
            leading=9.2,
            textColor=TEXT,
            spaceAfter=0,
        ),
        "table_cell_bold": ParagraphStyle(
            "TableCellBold",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=7.1,
            leading=9.2,
            textColor=INK,
            spaceAfter=0,
        ),
        "center": ParagraphStyle(
            "CenterSmall",
            parent=body,
            fontSize=7.2,
            leading=9.2,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=0,
        ),
        "right": ParagraphStyle(
            "RightSmall",
            parent=body,
            fontSize=7.2,
            leading=9.2,
            textColor=MUTED,
            alignment=TA_RIGHT,
            spaceAfter=0,
        ),
        "disclaimer": ParagraphStyle(
            "Disclaimer",
            parent=body,
            fontSize=7.5,
            leading=10.8,
            textColor=colors.HexColor("#5B513D"),
            spaceAfter=0,
        ),
    }


def build_investor_story(
    context: ReportContext,
    styles: dict[str, ParagraphStyle],
) -> list[Flowable]:
    analysis = context.analysis
    metadata = analysis.analysis_metadata or {}
    pre_meeting_inputs = dict_value(metadata.get("pre_meeting_inputs"))
    report_stage = safe_string(metadata.get("report_stage"))
    is_v2 = is_v2_method(metadata.get("methodology_version"))
    is_v2_1 = metadata.get("methodology_version") == "v2.1"
    assumptions = dict_value(metadata.get("assumptions"))
    arv_value_basis = first_string(assumptions, ("arv_value_basis",))
    arv_verified = arv_value_basis == "verified_renovated_recorded_sales"
    arv_range_label = (
        "Comp-supported ARV range"
        if arv_verified
        else "Preliminary recorded-sale ARV range"
    )
    review_reasons = string_list(metadata.get("review_reasons"))
    data_disagreements = string_list(metadata.get("data_disagreements"))
    decision_control = (
        "Manual review required: " + " ".join(review_reasons + data_disagreements)
        if review_reasons or data_disagreements
        else (
            "Evidence thresholds are met, but this analysis is not approval to make an offer. "
            "Confirm condition, title, buyer demand, and exit assumptions before approval."
        )
    )
    version_status = (
        labelize(context.underwriting_version.status)
        if context.underwriting_version
        else "Unlinked"
    )
    return [
        hero_block(
            f"INTERNAL INVESTMENT ANALYSIS / {report_stage_label(report_stage).upper()}",
            context.address,
            (
                f"Confidential underwriting package | Analysis {context.analysis_reference} | "
                f"{context.version_label}"
            ),
            styles,
        ),
        Spacer(1, 0.18 * inch),
        section_heading("Executive decision screen", styles),
        metric_table(
            [
                (
                    "As-is benchmark",
                    format_money(optional_int(metadata.get("as_is_value_cents"))),
                ),
                (
                    "Conservative ARV" if arv_verified else "Preliminary ARV",
                    format_money(optional_int(metadata.get("conservative_arv_cents"))),
                ),
                (
                    "Total rehab",
                    format_money(optional_int(metadata.get("total_rehab_cents"))),
                ),
                (
                    "Seller ceiling",
                    format_money(
                        optional_int(metadata.get("seller_contract_ceiling_cents"))
                        or analysis.mao_high_cents
                    ),
                ),
                ("Confidence", f"{analysis.confidence_score}%"),
            ],
            styles,
        ),
        Spacer(1, 0.14 * inch),
        two_column_facts(
            [
                ("Seller", context.seller_name),
                ("Property type", labelize(context.property_record.property_type)),
                (
                    "Condition",
                    labelize(
                        first_string(pre_meeting_inputs, ("current_condition",))
                        or context.lead.property_condition
                    ),
                ),
                ("Occupancy", labelize(context.lead.occupancy_status)),
                ("Seller timeline", labelize(context.lead.desired_timeline)),
                ("Current stage", labelize(context.lead.stage_key)),
            ],
            styles,
        ),
        Spacer(1, 0.16 * inch),
        section_heading("Acquisition calculation", styles),
        key_value_table(
            [
                (
                    (
                        arv_range_label
                        if is_v2_1
                        else "Legacy value range (recalculate)"
                    ),
                    format_money_range(
                        analysis.arv_low_cents,
                        analysis.arv_high_cents,
                    ),
                ),
                (
                    "Provider AVM screening range",
                    format_money_range(
                        analysis.estimated_value_low_cents,
                        analysis.estimated_value_high_cents,
                    ),
                ),
                (
                    "Flip buyer maximum",
                    format_money(optional_int(metadata.get("flip_buyer_max_cents"))),
                ),
                (
                    "Rental buyer maximum",
                    format_money(optional_int(metadata.get("rental_buyer_max_cents"))),
                ),
                (
                    "Recommended disposition",
                    format_money(optional_int(metadata.get("recommended_disposition_cents"))),
                ),
                (
                    "Recommended starting offer",
                    format_money(analysis.recommended_offer_cents),
                ),
                ("Assignment fee assumption", format_money(analysis.assignment_fee_cents)),
                (
                    "Transaction reserve",
                    format_money(optional_int(metadata.get("transaction_reserve_cents"))),
                ),
                (
                    "Selected / context comps",
                    f"{analysis.selected_comp_count} / {analysis.rejected_comp_count}",
                ),
                (
                    "Review status",
                    (
                        "Manual review required"
                        if metadata.get("human_review_required", True)
                        else f"{version_status}; evidence threshold met"
                    ),
                ),
            ],
            styles,
        ),
        Spacer(1, 0.14 * inch),
        *repair_input_story(context, styles),
        formula_box(context, styles),
        PageBreak(),
        warning_box(
            "DECISION CONTROL",
            decision_control,
            styles,
        ),
        Spacer(1, 0.16 * inch),
        section_heading("Selected comparable evidence", styles),
        body_paragraph(
            (
                "Selected properties are recorded sales ranked by distance, recency, size, age, "
                "lot, and property-type fit. Renovated and as-is classifications require human "
                "evidence before they support the corresponding value conclusion."
            ),
            styles,
        ),
        Spacer(1, 0.06 * inch),
        investor_comp_table(analysis.selected_comps, styles),
        Spacer(1, 0.2 * inch),
        section_heading("Rejected and market-context evidence", styles),
        body_paragraph(
            (
                "These records were excluded from the primary value range or retained only as "
                "market context. Active listings are not treated as closed-sale evidence."
            ),
            styles,
        ),
        Spacer(1, 0.06 * inch),
        investor_comp_table(analysis.rejected_comps, styles),
        PageBreak(),
        section_heading("Subject property and diligence", styles),
        subject_property_table(context, styles),
        Spacer(1, 0.18 * inch),
        diligence_checklist(styles),
        Spacer(1, 0.18 * inch),
        section_heading("Methodology and audit record", styles),
        key_value_table(
            [
                ("Data provider", analysis.provider.title()),
                ("Requested address", analysis.requested_address),
                ("Analysis reference", context.analysis_reference),
                ("Full analysis ID", str(analysis.id)),
                (
                    "Underwriting version ID",
                    str(analysis.underwriting_version_id or "Not linked"),
                ),
                ("Saved at", format_datetime(analysis.created_at)),
                (
                    "Method",
                    (
                        "Recorded-sale comparison, robust price-per-square-foot screening, "
                        "subject-size indicators, condition classification, repair scope, and "
                        "buyer economics"
                        if arv_verified
                        else "Preliminary recorded-sale comparison using subject-size "
                        "indicators; condition verification remains outstanding"
                        if is_v2
                        else "Sales comparison screening with percentile-based ARV range"
                    ),
                ),
            ],
            styles,
        ),
        Spacer(1, 0.16 * inch),
        disclaimer_box(
            (
                "Internal use only. Provider records and human classifications may be incomplete "
                "or delayed. This document is not an appraisal, "
                "broker price opinion, inspection, title report, or guarantee of resale value. "
                "A qualified human reviewer remains responsible for the acquisition decision."
            ),
            styles,
        ),
    ]


def build_client_story(
    context: ReportContext,
    styles: dict[str, ParagraphStyle],
) -> list[Flowable]:
    analysis = context.analysis
    metadata = analysis.analysis_metadata or {}
    is_v2_1 = metadata.get("methodology_version") == "v2.1"
    assumptions = dict_value(metadata.get("assumptions"))
    arv_verified = (
        first_string(assumptions, ("arv_value_basis",))
        == "verified_renovated_recorded_sales"
    )
    pre_meeting_inputs = dict_value(metadata.get("pre_meeting_inputs"))
    report_stage = safe_string(metadata.get("report_stage"))
    current_condition = labelize(
        first_string(pre_meeting_inputs, ("current_condition",))
        or context.lead.property_condition
    ).lower()
    return [
        hero_block(
            f"PROPERTY VALUE & SALE OPTIONS REVIEW / {report_stage_label(report_stage).upper()}",
            context.address,
            (
                f"Prepared for {context.seller_first_name} | "
                f"Market review {context.analysis_reference}"
            ),
            styles,
        ),
        Spacer(1, 0.2 * inch),
        section_heading("A clear look at the property and local market", styles),
        body_paragraph(
            (
                f"Stonegate Home Buyers prepared this review for {context.seller_first_name} "
                "using recent nearby property evidence and the information currently available "
                "about the home. It is designed to support a practical conversation about value "
                "and the tradeoffs between a renovated retail sale and a direct as-is sale."
            ),
            styles,
        ),
        Spacer(1, 0.12 * inch),
        metric_table(
            [
                (
                    "Current as-is benchmark",
                    format_money_range(
                        optional_int(metadata.get("as_is_value_low_cents")),
                        optional_int(metadata.get("as_is_value_high_cents")),
                    ),
                ),
                (
                    (
                        (
                            "Comp-supported renovated value"
                            if arv_verified
                            else "Preliminary renovated value"
                        )
                        if is_v2_1
                        else "Legacy renovated value"
                    ),
                    format_money_range(analysis.arv_low_cents, analysis.arv_high_cents),
                ),
                (
                    "Provider market screen",
                    format_money_range(
                        analysis.estimated_value_low_cents,
                        analysis.estimated_value_high_cents,
                    ),
                ),
                ("Comparable properties", str(analysis.selected_comp_count)),
                ("Market evidence", confidence_label(analysis.confidence_score)),
            ],
            styles,
        ),
        Spacer(1, 0.18 * inch),
        section_heading("Property snapshot", styles),
        subject_property_table(context, styles, include_internal=False),
        Spacer(1, 0.16 * inch),
        disclaimer_box(
            (
                f"This {report_stage_label(report_stage).lower()} market review is informational "
                "and is not a formal appraisal, "
                "broker price opinion, inspection, tax assessment, or guarantee of sale price. "
                "Values can change as property facts, condition, and market information are "
                "verified."
            ),
            styles,
        ),
        PageBreak(),
        section_heading("What the value range represents", styles),
        two_column_callouts(
            [
                (
                    "Renovated market position",
                    (
                        "The value range reflects how comparable properties support the home's "
                        "potential market position after appropriate repairs and preparation."
                    ),
                ),
                (
                    "Current condition",
                    (
                        f"The property is currently described as "
                        f"{current_condition}. A walkthrough is needed before finalizing "
                        "the scope of work."
                    ),
                ),
                (
                    "Direct as-is sale",
                    (
                        "A direct purchase can reduce preparation, showings, financing delays, "
                        "and uncertainty, but the economics differ from a renovated retail sale."
                    ),
                ),
                (
                    "Final decision",
                    (
                        "Any cash offer is finalized separately after property, title, timeline, "
                        "and closing-cost details are confirmed."
                    ),
                ),
            ],
            styles,
        ),
        Spacer(1, 0.2 * inch),
        section_heading("Comparable property evidence", styles),
        body_paragraph(
            (
                "The properties below were selected because their available location, recency, "
                "property type, size, and pricing data provide useful context for the subject "
                "property. Differences in condition, updates, lot, layout, and micro-location "
                "can materially affect value."
            ),
            styles,
        ),
        Spacer(1, 0.08 * inch),
        client_comp_table(analysis.selected_comps, styles),
        PageBreak(),
        section_heading("How to use this review", styles),
        numbered_steps(
            [
                (
                    "Verify the property",
                    "Confirm size, layout, major systems, repairs, occupancy, and title details.",
                ),
                (
                    "Compare sale paths",
                    (
                        "Consider preparation cost, commissions, carrying time, financing risk, "
                        "closing timeline, and certainty alongside the headline sale price."
                    ),
                ),
                (
                    "Confirm next steps",
                    (
                        "Stonegate can review the property in person and provide a separate "
                        "written cash offer when the required facts are verified."
                    ),
                ),
            ],
            styles,
        ),
        Spacer(1, 0.2 * inch),
        section_heading("Source and preparation record", styles),
        key_value_table(
            [
                ("Prepared by", "Stonegate Home Buyers"),
                ("Property", context.address),
                ("Market data source", analysis.provider.title()),
                ("Review status", report_stage_label(report_stage)),
                ("Analysis reference", context.analysis_reference),
                ("Market data saved", format_datetime(analysis.created_at)),
            ],
            styles,
        ),
        Spacer(1, 0.16 * inch),
        closing_box(context, styles),
    ]


def hero_block(
    eyebrow: str,
    title: str,
    subtitle: str,
    styles: dict[str, ParagraphStyle],
) -> Table:
    content = [
        Paragraph(escape(eyebrow), styles["eyebrow"]),
        Paragraph(escape(title), styles["hero"]),
        Paragraph(escape(subtitle), styles["hero_subtitle"]),
    ]
    table = Table([[content]], colWidths=[7.4 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BRAND_DARK),
                ("BOX", (0, 0), (-1, -1), 0.8, BRAND_DARK),
                ("LEFTPADDING", (0, 0), (-1, -1), 20),
                ("RIGHTPADDING", (0, 0), (-1, -1), 20),
                ("TOPPADDING", (0, 0), (-1, -1), 18),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
            ]
        )
    )
    return table


def section_heading(title: str, styles: dict[str, ParagraphStyle]) -> KeepTogether:
    return KeepTogether(
        [
            Paragraph(escape(title), styles["section"]),
            HRFlowable(width="100%", thickness=0.6, color=LINE, spaceAfter=8),
        ]
    )


def body_paragraph(text: str, styles: dict[str, ParagraphStyle]) -> Paragraph:
    return Paragraph(escape(text), styles["body"])


def metric_table(
    metrics: list[tuple[str, str]],
    styles: dict[str, ParagraphStyle],
) -> Table:
    width = 7.4 * inch / len(metrics)
    cells = [
        [
            Paragraph(escape(label.upper()), styles["metric_label"]),
            Paragraph(escape(value), styles["metric_value"]),
        ]
        for label, value in metrics
    ]
    table = Table([cells], colWidths=[width] * len(cells))
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BRAND_SOFT),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#C8DCCF")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#C8DCCF")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 11),
                ("RIGHTPADDING", (0, 0), (-1, -1), 11),
                ("TOPPADDING", (0, 0), (-1, -1), 11),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
            ]
        )
    )
    return table


def key_value_table(
    rows: list[tuple[str, str]],
    styles: dict[str, ParagraphStyle],
) -> Table:
    content = [
        [
            Paragraph(escape(label), styles["table_cell_bold"]),
            Paragraph(escape(value), styles["table_cell"]),
        ]
        for label, value in rows
    ]
    table = Table(content, colWidths=[1.85 * inch, 5.55 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), SURFACE),
                ("BOX", (0, 0), (-1, -1), 0.45, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def two_column_facts(
    facts: list[tuple[str, str]],
    styles: dict[str, ParagraphStyle],
) -> Table:
    pairs: list[list[list[Paragraph]]] = []
    for index in range(0, len(facts), 2):
        row: list[list[Paragraph]] = []
        for label, value in facts[index : index + 2]:
            row.append(
                [
                    Paragraph(escape(label.upper()), styles["metric_label"]),
                    Paragraph(escape(value), styles["table_cell_bold"]),
                ]
            )
        while len(row) < 2:
            row.append([])
        pairs.append(row)
    table = Table(pairs, colWidths=[3.7 * inch, 3.7 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.45, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def repair_input_story(
    context: ReportContext,
    styles: dict[str, ParagraphStyle],
) -> list[Flowable]:
    metadata = context.analysis.analysis_metadata or {}
    assumptions = dict_value(metadata.get("assumptions"))
    inputs = dict_value(metadata.get("pre_meeting_inputs"))
    repair_items_value = inputs.get("repair_items")
    repair_items = (
        [item for item in repair_items_value if isinstance(item, dict)]
        if isinstance(repair_items_value, list)
        else []
    )
    holding_months = optional_int(inputs.get("holding_period_months")) or optional_int(
        assumptions.get("holding_period_months")
    )
    repair_rows = [
        (
            "Report stage",
            report_stage_label(safe_string(metadata.get("report_stage"))),
        ),
        (
            "Current condition",
            labelize(
                first_string(inputs, ("current_condition",))
                or context.lead.property_condition
            ),
        ),
        (
            "Target finish",
            labelize(
                first_string(inputs, ("target_condition",))
                or first_string(assumptions, ("target_condition",))
            ),
        ),
        (
            "Repair estimate source",
            labelize(
                first_string(inputs, ("repair_estimate_source",))
                or first_string(assumptions, ("repair_estimate_source",))
            ),
        ),
    ]
    contractor_name = first_string(inputs, ("repair_estimate_contractor_name",))
    estimate_date = first_string(inputs, ("repair_estimate_date",))
    estimate_reference = first_string(inputs, ("repair_estimate_reference",))
    if contractor_name:
        repair_rows.append(("Contractor", contractor_name))
    if estimate_date:
        repair_rows.append(("Estimate date", format_sale_date(estimate_date)))
    if estimate_reference:
        repair_rows.append(("Evidence reference", estimate_reference))
    repair_rows.extend(
        [
            (
                "Base remodel estimate",
                format_money(optional_int(metadata.get("base_rehab_cents"))),
            ),
            (
                "Contingency",
                f"{optional_int(metadata.get('rehab_contingency_percentage')) or 0}%",
            ),
            (
                "Total remodel estimate",
                format_money(optional_int(metadata.get("total_rehab_cents"))),
            ),
            ("Holding period", f"{holding_months or 6} months"),
            (
                "Repair notes",
                first_string(inputs, ("repair_notes",))
                or "No additional notes recorded.",
            ),
        ]
    )
    story: list[Flowable] = [
        section_heading("Repair scope and input record", styles),
        key_value_table(repair_rows, styles),
    ]
    if repair_items:
        story.extend(
            [
                Spacer(1, 0.12 * inch),
                repair_item_table(repair_items, styles),
            ]
        )
    story.append(Spacer(1, 0.14 * inch))
    return story


def repair_item_table(
    items: list[dict[str, Any]],
    styles: dict[str, ParagraphStyle],
) -> LongTable:
    rows: list[list[Paragraph]] = [
        [
            Paragraph("Work item", styles["table_header"]),
            Paragraph("Labor", styles["table_header"]),
            Paragraph("Materials", styles["table_header"]),
            Paragraph("Total", styles["table_header"]),
            Paragraph("Details", styles["table_header"]),
        ]
    ]
    for item in items:
        rows.append(
            [
                Paragraph(
                    escape(labelize(first_string(item, ("category",)))),
                    styles["table_cell_bold"],
                ),
                Paragraph(
                    escape(format_money(optional_int(item.get("labor_cost_cents")))),
                    styles["table_cell"],
                ),
                Paragraph(
                    escape(format_money(optional_int(item.get("material_cost_cents")))),
                    styles["table_cell"],
                ),
                Paragraph(
                    escape(format_money(optional_int(item.get("estimated_cost_cents")))),
                    styles["table_cell"],
                ),
                Paragraph(
                    escape(first_string(item, ("details",)) or "No item note."),
                    styles["table_cell"],
                ),
            ]
        )
    table = LongTable(
        rows,
        colWidths=[1.25 * inch, 0.9 * inch, 0.9 * inch, 1.0 * inch, 3.35 * inch],
        repeatRows=1,
    )
    apply_comp_table_style(table)
    return table


def formula_box(
    context: ReportContext,
    styles: dict[str, ParagraphStyle],
) -> Table:
    analysis = context.analysis
    metadata = analysis.analysis_metadata or {}
    if is_v2_method(metadata.get("methodology_version")):
        assumptions = dict_value(metadata.get("assumptions"))
        if analysis.arv_low_cents is None or analysis.arv_high_cents is None:
            low_formula = (
                "Offer recommendation unavailable: no usable recorded-sale value evidence "
                "was available for a preliminary ARV."
            )
            high_formula = (
                "The provider AVM remains market-screening context and does not control the "
                "seller ceiling."
            )
        else:
            low_formula = (
                "Buyer maximum = conservative ARV - total rehab - purchase costs - "
                "financing/holding - resale costs - required buyer profit"
            )
            high_formula = (
                "Seller ceiling = "
                f"{format_money(optional_int(metadata.get('recommended_disposition_cents')))} "
                f"disposition - {format_money(analysis.assignment_fee_cents)} assignment - "
                f"{format_money(optional_int(metadata.get('transaction_reserve_cents')))} "
                f"reserve. Opening recommendation includes a "
                f"{format_percentage(assumptions.get('negotiation_reserve_percentage'))} "
                "negotiation reserve."
            )
    else:
        low_formula = (
            f"Low ceiling = {format_money(analysis.arv_low_cents)} x "
            f"{analysis.offer_low_percentage}% - {format_money(analysis.repair_high_cents)} "
            f"repairs - {format_money(analysis.assignment_fee_cents)} assignment fee"
        )
        high_formula = (
            f"High ceiling = {format_money(analysis.arv_high_cents)} x "
            f"{analysis.offer_high_percentage}% - {format_money(analysis.repair_low_cents)} "
            f"repairs - {format_money(analysis.assignment_fee_cents)} assignment fee"
        )
    table = Table(
        [
            [
                [
                    Paragraph("FORMULA USED", styles["metric_label"]),
                    Paragraph(escape(low_formula), styles["body"]),
                    Paragraph(escape(high_formula), styles["body"]),
                ]
            ]
        ],
        colWidths=[7.4 * inch],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def warning_box(
    label: str,
    text: str,
    styles: dict[str, ParagraphStyle],
) -> Table:
    label_style = ParagraphStyle(
        "WarningLabel",
        parent=styles["metric_label"],
        textColor=WARNING,
    )
    table = Table(
        [
            [
                [
                    Paragraph(escape(label), label_style),
                    Paragraph(escape(text), styles["disclaimer"]),
                ]
            ]
        ],
        colWidths=[7.4 * inch],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), WARNING_SOFT),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#E4C88C")),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def disclaimer_box(text: str, styles: dict[str, ParagraphStyle]) -> Table:
    table = Table(
        [[Paragraph(escape(text), styles["disclaimer"])]],
        colWidths=[7.4 * inch],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def investor_comp_table(
    comps: list[dict[str, Any]],
    styles: dict[str, ParagraphStyle],
) -> LongTable:
    headings = [
        "Address",
        "Sale date",
        "Price / sqft",
        "Sqft",
        "Subject-size indicator",
        "Dist.",
        "Condition",
        "Rationale",
    ]
    rows: list[list[Paragraph]] = [
        [Paragraph(heading, styles["table_header"]) for heading in headings]
    ]
    for comp in comps[:12]:
        price_per_square_foot = format_ppsf_cents(
            optional_int(comp.get("price_per_square_foot_cents"))
        )
        rows.append(
            [
                Paragraph(
                    escape(safe_string(comp.get("formatted_address"))),
                    styles["table_cell_bold"],
                ),
                Paragraph(
                    escape(format_sale_date(comp.get("sale_date"))),
                    styles["table_cell"],
                ),
                Paragraph(
                    (
                        f"{escape(format_money(optional_int(comp.get('price_cents'))))}"
                        f"<br/><font color='#657269'>"
                        f"{escape(price_per_square_foot)}"
                        "</font>"
                    ),
                    styles["table_cell"],
                ),
                Paragraph(
                    escape(format_number(optional_int(comp.get("square_footage")))),
                    styles["table_cell"],
                ),
                Paragraph(
                    escape(format_money(optional_int(comp.get("adjusted_value_cents")))),
                    styles["table_cell"],
                ),
                Paragraph(
                    escape(format_distance(comp.get("distance_miles"))),
                    styles["table_cell"],
                ),
                Paragraph(
                    escape(labelize(safe_string(comp.get("condition_classification")))),
                    styles["table_cell"],
                ),
                Paragraph(
                    escape(safe_string(comp.get("selection_reason"))),
                    styles["table_cell"],
                ),
            ]
        )
    if len(rows) == 1:
        rows.append(
            [Paragraph("No comparable records saved.", styles["table_cell"])]
            + [Paragraph("", styles["table_cell"]) for _ in range(len(headings) - 1)]
        )
    table = LongTable(
        rows,
        colWidths=[
            1.4 * inch,
            0.72 * inch,
            0.82 * inch,
            0.45 * inch,
            0.82 * inch,
            0.42 * inch,
            0.68 * inch,
            2.09 * inch,
        ],
        repeatRows=1,
    )
    apply_comp_table_style(table)
    return table


def client_comp_table(
    comps: list[dict[str, Any]],
    styles: dict[str, ParagraphStyle],
) -> LongTable:
    headings = [
        "Comparable property",
        "Sale date",
        "Price",
        "Beds / baths",
        "Sqft",
        "Distance",
        "Condition",
    ]
    rows: list[list[Paragraph]] = [
        [Paragraph(heading, styles["table_header"]) for heading in headings]
    ]
    for comp in comps[:8]:
        bedrooms = format_decimal(optional_float(comp.get("bedrooms")))
        bathrooms = format_decimal(optional_float(comp.get("bathrooms")))
        rows.append(
            [
                Paragraph(
                    escape(safe_string(comp.get("formatted_address"))),
                    styles["table_cell_bold"],
                ),
                Paragraph(
                    escape(format_sale_date(comp.get("sale_date"))),
                    styles["table_cell"],
                ),
                Paragraph(
                    escape(format_money(optional_int(comp.get("price_cents")))),
                    styles["table_cell"],
                ),
                Paragraph(f"{escape(bedrooms)} / {escape(bathrooms)}", styles["table_cell"]),
                Paragraph(
                    escape(format_number(optional_int(comp.get("square_footage")))),
                    styles["table_cell"],
                ),
                Paragraph(
                    escape(format_distance(comp.get("distance_miles"))),
                    styles["table_cell"],
                ),
                Paragraph(
                    escape(labelize(safe_string(comp.get("condition_classification")))),
                    styles["table_cell"],
                ),
            ]
        )
    if len(rows) == 1:
        rows.append(
            [Paragraph("No comparable records were available.", styles["table_cell"])]
            + [Paragraph("", styles["table_cell"]) for _ in range(len(headings) - 1)]
        )
    table = LongTable(
        rows,
        colWidths=[
            2.1 * inch,
            0.82 * inch,
            0.82 * inch,
            0.78 * inch,
            0.58 * inch,
            0.62 * inch,
            1.02 * inch,
        ],
        repeatRows=1,
    )
    apply_comp_table_style(table)
    return table


def apply_comp_table_style(table: Table) -> None:
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SURFACE]),
                ("BOX", (0, 0), (-1, -1), 0.45, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )


def subject_property_table(
    context: ReportContext,
    styles: dict[str, ParagraphStyle],
    *,
    include_internal: bool = True,
) -> Table:
    subject = context.analysis.subject_property
    rows = [
        ("Address", context.address),
        (
            "Property type",
            labelize(
                first_string(subject, ("propertyType", "property_type"))
                or context.property_record.property_type
            ),
        ),
        ("Living area", format_subject_number(subject, ("squareFootage", "livingArea"))),
        ("Bedrooms", format_subject_number(subject, ("bedrooms", "bedroomCount"))),
        ("Bathrooms", format_subject_number(subject, ("bathrooms", "bathroomCount"))),
        ("Year built", format_subject_number(subject, ("yearBuilt", "year_built"))),
        ("County", context.property_record.county or "Not recorded"),
        ("Occupancy", labelize(context.lead.occupancy_status)),
    ]
    if include_internal:
        rows.extend(
            [
                ("Seller motivation", context.lead.motivation or "Not recorded"),
                ("Asking price", context.lead.asking_price or "Not recorded"),
            ]
        )
    return key_value_table(rows, styles)


def diligence_checklist(styles: dict[str, ParagraphStyle]) -> Table:
    items = [
        "Verify gross living area, bed/bath count, lot, additions, and property type.",
        "Walk the property and replace the condition-based repair allowance with a scoped budget.",
        "Confirm comp sale status, sale date, concessions, renovation level, and neighborhood fit.",
        "Review title, liens, taxes, probate, occupancy, access, and seller authority.",
        "Validate buyer demand, assignment spread, holding exposure, and closing assumptions.",
        "Document manual changes and obtain human approval before presenting an offer.",
    ]
    cells = [
        [
            Paragraph(
                f"<b>{index}.</b>&nbsp;&nbsp;{escape(item)}",
                styles["body"],
            )
        ]
        for index, item in enumerate(items, start=1)
    ]
    table = Table(cells, colWidths=[7.4 * inch])
    table.setStyle(
        TableStyle(
            [
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, SURFACE]),
                ("BOX", (0, 0), (-1, -1), 0.45, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def two_column_callouts(
    callouts: list[tuple[str, str]],
    styles: dict[str, ParagraphStyle],
) -> Table:
    rows: list[list[list[Paragraph]]] = []
    for index in range(0, len(callouts), 2):
        row = [
            [
                Paragraph(escape(title), styles["subsection"]),
                Paragraph(escape(text), styles["body"]),
            ]
            for title, text in callouts[index : index + 2]
        ]
        while len(row) < 2:
            row.append([])
        rows.append(row)
    table = Table(rows, colWidths=[3.62 * inch, 3.62 * inch], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
                ("BOX", (0, 0), (-1, -1), 0.45, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 11),
                ("RIGHTPADDING", (0, 0), (-1, -1), 11),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def numbered_steps(
    steps: list[tuple[str, str]],
    styles: dict[str, ParagraphStyle],
) -> Table:
    rows: list[list[object]] = []
    for index, (title, text) in enumerate(steps, start=1):
        number_style = ParagraphStyle(
            f"StepNumber{index}",
            parent=styles["metric_value"],
            textColor=WHITE,
            alignment=TA_CENTER,
            fontSize=11,
        )
        rows.append(
            [
                Paragraph(str(index), number_style),
                [
                    Paragraph(escape(title), styles["subsection"]),
                    Paragraph(escape(text), styles["body"]),
                ],
            ]
        )
    table = Table(rows, colWidths=[0.42 * inch, 6.98 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), BRAND),
                ("ROWBACKGROUNDS", (1, 0), (1, -1), [WHITE, SURFACE]),
                ("BOX", (0, 0), (-1, -1), 0.45, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, -1), 6),
                ("RIGHTPADDING", (0, 0), (0, -1), 6),
                ("LEFTPADDING", (1, 0), (1, -1), 10),
                ("RIGHTPADDING", (1, 0), (1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def closing_box(
    context: ReportContext,
    styles: dict[str, ParagraphStyle],
) -> Table:
    content = [
        Paragraph("STONEGATE HOME BUYERS", styles["metric_label"]),
        Paragraph("A practical next step, without pressure.", styles["subsection"]),
        Paragraph(
            escape(
                "We can review the property, answer questions about the comparable evidence, "
                "and explain the timing and terms of a direct as-is purchase."
            ),
            styles["body"],
        ),
        Paragraph(
            escape(f"Reference this review as {context.analysis_reference}."),
            styles["small"],
        ),
    ]
    table = Table([[content]], colWidths=[7.4 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BRAND_SOFT),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#C8DCCF")),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return table


def page_decorator(
    context: ReportContext,
    audience: ReportAudience,
) -> Callable[[Canvas, BaseDocTemplate], None]:
    report_label = "INTERNAL INVESTMENT ANALYSIS" if audience == "investor" else "PROPERTY REVIEW"
    confidentiality = (
        "CONFIDENTIAL - INTERNAL USE"
        if audience == "investor"
        else "PREPARED FOR PROPERTY OWNER"
    )

    def decorate(canvas: Canvas, document: BaseDocTemplate) -> None:
        canvas.saveState()
        width, height = letter
        canvas.setFillColor(BRAND_DARK)
        canvas.rect(0, height - 0.18 * inch, width, 0.18 * inch, fill=1, stroke=0)
        canvas.setFillColor(BRAND)
        canvas.roundRect(
            0.55 * inch,
            height - 0.55 * inch,
            0.24 * inch,
            0.24 * inch,
            2,
            fill=1,
            stroke=0,
        )
        canvas.setFillColor(INK)
        canvas.setFont("Helvetica-Bold", 8.5)
        canvas.drawString(0.88 * inch, height - 0.45 * inch, "STONEGATE HOME BUYERS")
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.8)
        canvas.drawRightString(width - 0.55 * inch, height - 0.45 * inch, report_label)
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.4)
        canvas.line(0.55 * inch, 0.47 * inch, width - 0.55 * inch, 0.47 * inch)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.5)
        canvas.drawString(0.55 * inch, 0.28 * inch, confidentiality)
        canvas.drawCentredString(
            width / 2,
            0.28 * inch,
            f"Analysis {context.analysis_reference}",
        )
        canvas.drawRightString(
            width - 0.55 * inch,
            0.28 * inch,
            f"Page {document.page}",
        )
        canvas.restoreState()

    return decorate


def confidence_label(score: int) -> str:
    if score >= 80:
        return "Strong"
    if score >= 60:
        return "Moderate"
    return "Limited"


def report_stage_label(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized == "walkthrough_verified":
        return "Walkthrough verified"
    if normalized == "pre_meeting_reviewed":
        return "Pre-meeting reviewed"
    return "Preliminary"


def format_property_address(property_record: Property) -> str:
    return (
        f"{property_record.street_address}, {property_record.city}, "
        f"{property_record.state} {property_record.postal_code}"
    )


def format_money(cents: int | None) -> str:
    if cents is None:
        return "Not available"
    return f"${cents / 100:,.0f}"


def format_money_range(low_cents: int | None, high_cents: int | None) -> str:
    if low_cents is None and high_cents is None:
        return "Not supported"
    return f"{format_money(low_cents)} - {format_money(high_cents)}"


def format_ppsf_cents(cents: int | None) -> str:
    if cents is None:
        return "N/A"
    return f"${cents / 100:,.0f}/sqft"


def format_number(value: int | None) -> str:
    return "Not available" if value is None else f"{value:,}"


def format_decimal(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:g}"


def format_distance(value: object) -> str:
    number = optional_float(value)
    return "N/A" if number is None else f"{number:.1f} mi"


def format_days(value: object) -> str:
    number = optional_int(value)
    return "N/A" if number is None else f"{number} days"


def format_sale_date(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return "N/A"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.strftime("%b %d, %Y").replace(" 0", " ")


def format_percentage(value: object) -> str:
    number = optional_float(value)
    return "N/A" if number is None else f"{number * 100:.0f}%"


def format_ppsf(comp: dict[str, Any]) -> str:
    price = optional_int(comp.get("price_cents"))
    square_feet = optional_int(comp.get("square_footage"))
    if price is None or square_feet is None or square_feet <= 0:
        return "N/A"
    return f"${(price / 100) / square_feet:,.0f}"


def format_datetime(value: datetime) -> str:
    rendered = value.strftime("%b %d, %Y at %I:%M %p")
    return rendered.replace(" 0", " ")


def format_subject_number(subject: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = subject.get(key)
        number = optional_float(value)
        if number is not None:
            return format_decimal(number)
    return "Not available"


def first_string(subject: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = subject.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def labelize(value: str | None) -> str:
    if not value:
        return "Not recorded"
    return " ".join(word.capitalize() for word in value.replace("-", "_").split("_"))


def slugify(value: str) -> str:
    slug = "".join(character.lower() if character.isalnum() else "-" for character in value)
    return "-".join(part for part in slug.split("-") if part)[:60] or "property"


def safe_string(value: object) -> str:
    if value is None:
        return "Not available"
    return str(value)


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def is_v2_method(value: object) -> bool:
    return isinstance(value, str) and value.startswith("v2")


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
