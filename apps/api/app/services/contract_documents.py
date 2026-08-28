import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from functools import partial
from html import escape
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.foundation import ContractPackage, ContractTemplate, Property, Transaction
from app.schemas.transactions import EsignRecipientCreate

GREEN = colors.HexColor("#215F41")
INK = colors.HexColor("#18231D")
MUTED = colors.HexColor("#5B675F")
LINE = colors.HexColor("#AEB9B2")
CONTRACT_SOURCE_FILES = {
    "purchase_agreement": "stonegate-ga-investor-purchase-agreement.html",
    "assignment_contract": "stonegate-ga-assignment-agreement.html",
    "addendum": "stonegate-ga-contract-addendum.html",
}
SIGNATURE_HEADINGS = {"signatures", "buyer signature"}
FIELD_KEYS = (
    "seller_name",
    "property_address",
    "buyer_entity_name",
    "purchase_price",
    "earnest_money",
    "deposit_due_at",
    "closing_date",
    "inspection_period_days",
    "special_terms",
    "assignor_name",
    "assignee_name",
    "assignment_fee",
    "end_buyer_price",
)


@dataclass(frozen=True)
class ContractBlock:
    kind: str
    text: str = ""


@dataclass(frozen=True)
class GeneratedContract:
    content: bytes
    file_name: str
    title: str
    document_type: str


class ContractHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[ContractBlock] = []
        self.capture_kind: str | None = None
        self.capture_depth = 0
        self.capture_parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = {key: value or "" for key, value in attrs}
        class_names = set(attributes.get("class", "").split())
        if self.capture_kind is not None:
            if tag == "br":
                self.capture_parts.append("\n")
                return
            self.capture_depth += 1
            return
        if tag == "div" and "page-break" in class_names:
            self.blocks.append(ContractBlock("page_break"))
            return
        kind = None
        if tag in {"h1", "h2", "p", "li", "footer"}:
            kind = tag
        elif tag == "div" and class_names.intersection({"field", "notice", "choice"}):
            kind = next(iter(class_names.intersection({"field", "notice", "choice"})))
        if kind is not None:
            self.capture_kind = kind
            self.capture_depth = 1
            self.capture_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self.capture_kind is None:
            return
        if tag == "b" and self.capture_kind == "field":
            self.capture_parts.append("\n")
        self.capture_depth -= 1
        if self.capture_depth:
            return
        text = _normalize_text("".join(self.capture_parts))
        if text:
            self.blocks.append(ContractBlock(self.capture_kind, text))
        self.capture_kind = None
        self.capture_parts = []

    def handle_data(self, data: str) -> None:
        if self.capture_kind is not None:
            self.capture_parts.append(data)


def generate_contract_pdf(
    transaction: Transaction,
    package: ContractPackage,
    property_record: Property | None,
    template: ContractTemplate | None,
    recipients: list[EsignRecipientCreate],
) -> GeneratedContract:
    document_type = str(
        package.terms_snapshot.get("document_type")
        or (template.document_type if template else "purchase_agreement")
    )
    source_file = CONTRACT_SOURCE_FILES.get(document_type)
    if source_file is None:
        raise ValueError(f"Internal document generation does not support {document_type}.")
    source_path = _contract_source_directory() / source_file
    if not source_path.exists():
        raise ValueError("Stonegate's internal contract source is unavailable.")
    parser = ContractHTMLParser()
    parser.feed(source_path.read_text(encoding="utf-8"))
    context = _contract_context(transaction, package, property_record, recipients)
    title = {
        "purchase_agreement": "Residential Real Estate Purchase Agreement",
        "assignment_contract": "Assignment of Purchase Agreement",
        "addendum": "Amendment and Addendum",
    }[document_type]
    file_stem = {
        "purchase_agreement": "purchase-agreement",
        "assignment_contract": "assignment-agreement",
        "addendum": "contract-addendum",
    }[document_type]
    content = _render_contract(
        parser.blocks,
        context,
        recipients,
        title=title,
        package_id=str(package.id),
        version_number=package.version_number,
    )
    return GeneratedContract(
        content=content,
        file_name=f"{file_stem}-v{package.version_number}.pdf",
        title=f"{title} v{package.version_number}",
        document_type=document_type,
    )


def _contract_source_directory() -> Path:
    repository_root = Path(__file__).resolve().parents[4]
    return repository_root / "docs" / "templates" / "ga-contracts"


def _contract_context(
    transaction: Transaction,
    package: ContractPackage,
    property_record: Property | None,
    recipients: list[EsignRecipientCreate],
) -> dict[str, str]:
    assignee = next(
        (
            item
            for item in recipients
            if any(role in item.placeholder_name.lower() for role in ("assignee", "end buyer"))
        ),
        None,
    )
    property_address = ""
    if property_record is not None:
        property_address = (
            f"{property_record.street_address}, {property_record.city}, "
            f"{property_record.state} {property_record.postal_code}"
        )
    special_terms = str(package.terms_snapshot.get("special_terms") or "").strip()
    binding = package.terms_snapshot.get("disposition_buyer_binding") or {}
    economics = binding.get("offer_economics_snapshot") if isinstance(binding, dict) else None
    deposit_due_at = economics.get("deposit_due_at") if isinstance(economics, dict) else None
    return {
        "seller_name": package.seller_name,
        "property_address": property_address,
        "buyer_entity_name": package.buyer_entity_name,
        "purchase_price": _money(package.purchase_price_cents),
        "earnest_money": _money(package.earnest_money_cents),
        "deposit_due_at": _date_time(deposit_due_at),
        "closing_date": _date(package.closing_date),
        "inspection_period_days": (
            str(package.inspection_period_days)
            if package.inspection_period_days is not None
            else ""
        ),
        "special_terms": special_terms or "None.",
        "assignor_name": package.buyer_entity_name,
        "assignee_name": assignee.name if assignee else "",
        "assignment_fee": _money(transaction.assignment_fee_cents),
        "end_buyer_price": _money(
            package.purchase_price_cents + transaction.assignment_fee_cents
            if transaction.assignment_fee_cents is not None
            else None
        ),
        "stonegate_transaction_number": str(transaction.id),
        "county": (property_record.county or "") if property_record else "",
        "closing_attorney": transaction.title_company or "",
        "earnest_money_due": _date(transaction.earnest_money_due_at),
    }


def _render_contract(
    blocks: list[ContractBlock],
    context: dict[str, str],
    recipients: list[EsignRecipientCreate],
    *,
    title: str,
    package_id: str,
    version_number: int,
) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=letter,
        leftMargin=0.68 * inch,
        rightMargin=0.68 * inch,
        topMargin=0.62 * inch,
        bottomMargin=0.62 * inch,
        title=title,
        author="Stonegate Home Buyers",
        subject=f"Stonegate contract package {package_id}",
    )
    styles = _styles()
    story: list[Flowable] = []
    signature_section_written = False
    skip_source_signatures = False
    for block in blocks:
        if block.kind == "footer":
            continue
        if block.kind == "page_break":
            if story and not isinstance(story[-1], PageBreak):
                story.append(PageBreak())
            continue
        if skip_source_signatures and block.kind == "h2" and _is_exhibit_heading(block.text):
            skip_source_signatures = False
        if block.kind in {"h1", "h2"} and _is_signature_heading(block.text):
            story.append(Paragraph(escape(block.text), styles["heading"]))
            story.extend(_signature_story(recipients, styles))
            signature_section_written = True
            skip_source_signatures = True
            continue
        if skip_source_signatures:
            continue
        if block.kind == "h1":
            story.append(Paragraph(escape(block.text), styles["title"]))
        elif block.kind == "h2":
            story.append(Paragraph(escape(block.text), styles["heading"]))
        elif block.kind == "p":
            story.append(Paragraph(escape(block.text).replace("\n", "<br/>"), styles["body"]))
        elif block.kind == "li":
            story.append(Paragraph(f"• {escape(block.text)}", styles["list"]))
        elif block.kind == "field":
            story.append(_field_flowable(block.text, context, styles))
        elif block.kind == "notice":
            story.append(_notice_flowable(block.text, styles))
        elif block.kind == "choice":
            story.append(_choice_flowable(block.text, styles))
    if not signature_section_written:
        story.append(PageBreak())
        story.append(Paragraph("Signatures", styles["heading"]))
        story.extend(_signature_story(recipients, styles))
    document.build(
        story,
        onFirstPage=_page_decorator(version_number),
        onLaterPages=_page_decorator(version_number),
        canvasmaker=partial(Canvas, invariant=1, pageCompression=0),
    )
    return output.getvalue()


def _styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ContractTitle",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=23,
            textColor=INK,
            alignment=TA_CENTER,
            spaceAfter=12,
        ),
        "heading": ParagraphStyle(
            "ContractHeading",
            parent=sample["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=14,
            textColor=INK,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "ContractBody",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=9.4,
            leading=12.5,
            textColor=INK,
            spaceAfter=6,
        ),
        "list": ParagraphStyle(
            "ContractList",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=12,
            leftIndent=13,
            firstLineIndent=-9,
            textColor=INK,
            spaceAfter=3,
        ),
        "field_label": ParagraphStyle(
            "ContractFieldLabel",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9,
            textColor=MUTED,
        ),
        "field_value": ParagraphStyle(
            "ContractFieldValue",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=12,
            textColor=INK,
        ),
        "notice": ParagraphStyle(
            "ContractNotice",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            textColor=INK,
            alignment=TA_CENTER,
        ),
        "signature": ParagraphStyle(
            "ContractSignature",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=INK,
        ),
    }


def _field_flowable(
    source_text: str,
    context: dict[str, str],
    styles: dict[str, ParagraphStyle],
) -> Flowable:
    label, _, source_value = source_text.partition("\n")
    key = next((candidate for candidate in FIELD_KEYS if candidate in label.lower()), None)
    value = ""
    if key:
        label = re.sub(rf"\s*-\s*{re.escape(key)}", "", label, flags=re.IGNORECASE)
        value = context.get(key, "")
        suffix = source_value.strip("$ ").strip()
        if value and suffix:
            value = f"{value} {suffix}"
    else:
        normalized = label.lower()
        if normalized.startswith("stonegate transaction number"):
            value = context["stonegate_transaction_number"]
        elif normalized.startswith("county and parcel"):
            value = context["county"]
        elif normalized.startswith("closing attorney / firm"):
            value = context["closing_attorney"]
        elif normalized.startswith("earnest money due"):
            value = context["earnest_money_due"]
        else:
            value = source_value.strip()
    label = label.rstrip("$ ").strip()
    value = value or " "
    table = Table(
        [
            [Paragraph(escape(label.upper()), styles["field_label"])],
            [Paragraph(escape(value).replace("\n", "<br/>"), styles["field_value"])],
        ],
        colWidths=[7.1 * inch],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LINEBELOW", (0, -1), (-1, -1), 0.5, LINE),
            ]
        )
    )
    return KeepTogether([table])


def _notice_flowable(text: str, styles: dict[str, ParagraphStyle]) -> Table:
    table = Table([[Paragraph(escape(text), styles["notice"])]], colWidths=[7.1 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1.2, INK),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _choice_flowable(text: str, styles: dict[str, ParagraphStyle]) -> Table:
    table = Table(
        [[Paragraph(escape(text).replace("\n", "<br/>"), styles["body"])]],
        colWidths=[7.1 * inch],
    )
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _signature_story(
    recipients: list[EsignRecipientCreate],
    styles: dict[str, ParagraphStyle],
) -> list[Flowable]:
    story: list[Flowable] = []
    for index, recipient in enumerate(recipients, start=1):
        signature_tag = f"{{{{signature:{index}:y::::180:35}}}}"
        date_tag = f"{{{{autofill_date_signed:{index}:y::::90:30}}}}"
        signature = Paragraph(
            f'<font color="#FFFFFF">{escape(signature_tag)}</font>',
            styles["signature"],
        )
        signed_date = Paragraph(
            f'<font color="#FFFFFF">{escape(date_tag)}</font>',
            styles["signature"],
        )
        lines = Table(
            [[signature, signed_date]],
            colWidths=[5.1 * inch, 2 * inch],
            rowHeights=[0.42 * inch],
        )
        lines.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.8, INK),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        labels = Table(
            [
                [
                    Paragraph(
                        f"{escape(recipient.placeholder_name)} signature — "
                        f"{escape(recipient.name)}",
                        styles["signature"],
                    ),
                    Paragraph("Date signed", styles["signature"]),
                ]
            ],
            colWidths=[5.1 * inch, 2 * inch],
        )
        labels.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        story.append(KeepTogether([Spacer(1, 10), lines, labels, Spacer(1, 12)]))
    return story


def _page_decorator(
    version_number: int,
) -> Callable[[Canvas, SimpleDocTemplate], None]:
    def decorate(canvas: Canvas, document: SimpleDocTemplate) -> None:
        canvas.saveState()
        width, _ = letter
        canvas.setStrokeColor(GREEN)
        canvas.setLineWidth(1.2)
        canvas.line(document.leftMargin, 0.46 * inch, width - document.rightMargin, 0.46 * inch)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7.2)
        canvas.drawString(
            document.leftMargin,
            0.3 * inch,
            f"Stonegate Home Buyers | Contract package v{version_number}",
        )
        canvas.drawRightString(
            width - document.rightMargin,
            0.3 * inch,
            f"Page {canvas.getPageNumber()}",
        )
        canvas.restoreState()

    return decorate


def _is_signature_heading(text: str) -> bool:
    normalized = re.sub(r"^\d+\.\s*", "", text.strip().lower())
    return normalized in SIGNATURE_HEADINGS


def _is_exhibit_heading(text: str) -> bool:
    normalized = re.sub(r"^\d+\.\s*", "", text.strip().lower())
    return normalized.startswith("exhibit")


def _normalize_text(value: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def _money(value: int | None) -> str:
    return f"${value / 100:,.2f}" if value is not None else ""


def _date(value: date | datetime | None) -> str:
    if value is None:
        return ""
    normalized = value.date() if isinstance(value, datetime) else value
    return f"{normalized.strftime('%B')} {normalized.day}, {normalized.year}"


def _date_time(value: str | datetime | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            normalized = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    else:
        normalized = value
    hour = normalized.strftime("%I").lstrip("0") or "12"
    timezone_name = normalized.tzname() or ""
    return (
        f"{normalized.strftime('%B')} {normalized.day}, {normalized.year} at "
        f"{hour}:{normalized.strftime('%M %p')} {timezone_name}"
    ).strip()
