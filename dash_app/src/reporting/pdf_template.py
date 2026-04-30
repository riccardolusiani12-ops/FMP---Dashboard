"""
PDF template definitions – fixed layout for report generation.
Uses ReportLab for PDF construction.
"""

from __future__ import annotations

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


# ── Colors ────────────────────────────────────────────────────────────────────
BRAND_DARK = HexColor("#1a1a2e")
BRAND_BLUE = HexColor("#1a3c6e")
BRAND_RED = HexColor("#c8102e")
TEXT_WHITE = HexColor("#ffffff")
TEXT_LIGHT = HexColor("#cccccc")
TEXT_MUTED = HexColor("#888888")
BG_CARD = HexColor("#2c3e50")

# ── Page setup ────────────────────────────────────────────────────────────────
PAGE_SIZE = A4
PAGE_W, PAGE_H = PAGE_SIZE
MARGIN_LEFT = 20 * mm
MARGIN_RIGHT = 20 * mm
MARGIN_TOP = 20 * mm
MARGIN_BOTTOM = 25 * mm
CONTENT_W = PAGE_W - MARGIN_LEFT - MARGIN_RIGHT

# ── Styles ────────────────────────────────────────────────────────────────────

def get_report_styles() -> dict[str, ParagraphStyle]:
    """Return custom paragraph styles for the PDF report."""
    base = getSampleStyleSheet()

    styles = {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontSize=22,
            textColor=TEXT_WHITE,
            alignment=TA_CENTER,
            spaceAfter=6 * mm,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base["Normal"],
            fontSize=12,
            textColor=TEXT_LIGHT,
            alignment=TA_CENTER,
            spaceAfter=4 * mm,
        ),
        "heading": ParagraphStyle(
            "ReportHeading",
            parent=base["Heading2"],
            fontSize=14,
            textColor=BRAND_RED,
            spaceBefore=8 * mm,
            spaceAfter=3 * mm,
        ),
        "subheading": ParagraphStyle(
            "ReportSubheading",
            parent=base["Heading3"],
            fontSize=11,
            textColor=TEXT_LIGHT,
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "ReportBody",
            parent=base["Normal"],
            fontSize=10,
            textColor=TEXT_LIGHT,
            spaceAfter=2 * mm,
            leading=14,
        ),
        "kpi_label": ParagraphStyle(
            "KPILabel",
            parent=base["Normal"],
            fontSize=8,
            textColor=TEXT_MUTED,
            alignment=TA_CENTER,
        ),
        "kpi_value": ParagraphStyle(
            "KPIValue",
            parent=base["Normal"],
            fontSize=18,
            textColor=TEXT_WHITE,
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
        ),
        "footer": ParagraphStyle(
            "ReportFooter",
            parent=base["Normal"],
            fontSize=8,
            textColor=TEXT_MUTED,
            alignment=TA_CENTER,
        ),
        "caption": ParagraphStyle(
            "Caption",
            parent=base["Normal"],
            fontSize=8,
            textColor=TEXT_MUTED,
            alignment=TA_CENTER,
            spaceAfter=3 * mm,
        ),
    }
    return styles
