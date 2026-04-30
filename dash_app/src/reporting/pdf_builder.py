"""
PDF report builder – generates a formatted PDF from precomputed artifacts.
Uses ReportLab. Embeds PNG images of charts (from saved PNGs or converted via kaleido).
Works fully offline.
"""

from __future__ import annotations

import io
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image as RLImage,
    Table as RLTable,
    TableStyle,
    PageBreak,
)
from reportlab.lib.colors import HexColor

from src.registry.registry import ArtifactRegistry
from src.registry.manifest_schema import ArtifactEntry
from src.reporting.pdf_template import (
    BRAND_DARK,
    BRAND_BLUE,
    BRAND_RED,
    TEXT_WHITE,
    TEXT_LIGHT,
    TEXT_MUTED,
    BG_CARD,
    PAGE_SIZE,
    MARGIN_LEFT,
    MARGIN_RIGHT,
    MARGIN_TOP,
    MARGIN_BOTTOM,
    CONTENT_W,
    get_report_styles,
)
from src.utils.logging import log


def _convert_plotly_to_png(json_path: Path) -> Optional[bytes]:
    """
    Convert a Plotly JSON figure to PNG bytes using kaleido.
    Returns None if conversion fails.
    """
    try:
        import plotly.io as pio

        fig = pio.from_json(json_path.read_text(encoding="utf-8"))
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#1a1a2e",
            plot_bgcolor="#1a1a2e",
            width=800,
            height=450,
        )
        return fig.to_image(format="png", scale=2, engine="kaleido")
    except ImportError:
        log.warning("kaleido not installed – cannot convert Plotly figures to PNG for PDF")
        return None
    except Exception as exc:
        log.error("Plotly→PNG conversion failed for %s: %s", json_path, exc)
        return None


def _load_image_for_pdf(entry: ArtifactEntry) -> Optional[bytes]:
    """Load an image (PNG/JPG) or convert Plotly JSON to PNG bytes."""
    registry = ArtifactRegistry.instance()
    resolved = registry.resolve_path(entry)

    if not resolved.exists():
        return None

    if entry.format in ("png", "jpg"):
        return resolved.read_bytes()
    elif entry.format == "plotly_json":
        return _convert_plotly_to_png(resolved)
    return None


def _draw_page_background(canvas, doc):
    """Draw dark background and footer on every page."""
    canvas.saveState()
    # Dark background
    canvas.setFillColor(BRAND_DARK)
    canvas.rect(0, 0, PAGE_SIZE[0], PAGE_SIZE[1], fill=1)

    # Header stripe
    canvas.setFillColor(BRAND_RED)
    canvas.rect(0, PAGE_SIZE[1] - 5 * mm, PAGE_SIZE[0], 5 * mm, fill=1)

    # Footer
    canvas.setFillColor(HexColor("#666666"))
    canvas.setFont("Helvetica", 7)
    canvas.drawCentredString(
        PAGE_SIZE[0] / 2,
        10 * mm,
        f"Serie A Game Analysis Dashboard  •  Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}  •  Page {doc.page}",
    )
    canvas.restoreState()


def build_pdf_report(
    season: str,
    team: str,
    match_id: Optional[str] = None,
    analyses: Optional[list[str]] = None,
    active_tab: str = "tab-home",
) -> bytes:
    """
    Build a PDF report and return it as bytes.

    Parameters
    ----------
    season : str
        Season identifier (e.g. "2024_2025").
    team : str
        Team name.
    match_id : str, optional
        Match ID for match-specific reports.
    analyses : list[str], optional
        List of analysis types to include.
    active_tab : str
        Currently active tab name (for report title).

    Returns
    -------
    bytes
        The generated PDF as bytes.
    """
    buffer = io.BytesIO()
    styles = get_report_styles()
    registry = ArtifactRegistry.instance()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=PAGE_SIZE,
        leftMargin=MARGIN_LEFT,
        rightMargin=MARGIN_RIGHT,
        topMargin=MARGIN_TOP + 5 * mm,  # account for header stripe
        bottomMargin=MARGIN_BOTTOM,
    )

    story: list = []

    # ── Title page ────────────────────────────────────────────────────────
    story.append(Spacer(1, 30 * mm))
    story.append(Paragraph("Serie A – Game Analysis", styles["title"]))

    tab_titles = {
        "tab-home": "Season Overview",
        "tab-match-report": "Match Report",
        "tab-team-season": "Team Season Performance",
        "tab-player": "Player Analysis",
    }
    subtitle = tab_titles.get(active_tab, "Report")
    story.append(Paragraph(subtitle, styles["subtitle"]))
    story.append(Spacer(1, 10 * mm))

    # Meta info table
    meta_data = [
        ["Competition", "Serie A"],
        ["Season", season.replace("_", "/")],
        ["Team", team],
    ]
    if match_id:
        meta_data.append(["Match", match_id[:20]])

    meta_data.append(["Generated", datetime.now().strftime("%Y-%m-%d %H:%M")])

    meta_table = RLTable(meta_data, colWidths=[40 * mm, 80 * mm])
    meta_table.setStyle(
        TableStyle(
            [
                ("TEXTCOLOR", (0, 0), (0, -1), HexColor("#888888")),
                ("TEXTCOLOR", (1, 0), (1, -1), TEXT_WHITE),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                ("ALIGN", (1, 0), (1, -1), "LEFT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(meta_table)
    story.append(PageBreak())

    # ── Content pages ─────────────────────────────────────────────────────
    analyses = analyses or ["high_regains"]

    for analysis in analyses:
        entries = registry.query(season=season, team=team, analysis=analysis, match_id=match_id)

        if not entries:
            continue

        # Section heading
        heading = analysis.replace("_", " ").title()
        story.append(Paragraph(heading, styles["heading"]))

        for entry in entries:
            story.append(Paragraph(entry.title, styles["subheading"]))

            if entry.description:
                story.append(Paragraph(entry.description, styles["body"]))

            # Try to embed image
            img_bytes = _load_image_for_pdf(entry)
            if img_bytes:
                # Write to temp file for ReportLab
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp.write(img_bytes)
                tmp.close()

                # Calculate image dimensions to fit content width
                img = RLImage(tmp.name)
                aspect = img.imageHeight / img.imageWidth if img.imageWidth else 1
                img_w = min(CONTENT_W, 170 * mm)
                img_h = img_w * aspect

                # Cap height
                if img_h > 120 * mm:
                    img_h = 120 * mm
                    img_w = img_h / aspect

                img = RLImage(tmp.name, width=img_w, height=img_h)
                story.append(img)
                story.append(Paragraph(entry.title, styles["caption"]))
            else:
                story.append(
                    Paragraph(
                        f"[Chart: {entry.file} – format: {entry.format}]",
                        styles["body"],
                    )
                )

            story.append(Spacer(1, 5 * mm))

        story.append(PageBreak())

    # If no content at all, add a message
    if len(story) <= 5:
        story.append(Spacer(1, 20 * mm))
        story.append(
            Paragraph(
                "No artifacts found for the selected filters. "
                "Generate outputs from notebooks and update the manifest.",
                styles["body"],
            )
        )

    doc.build(story, onFirstPage=_draw_page_background, onLaterPages=_draw_page_background)
    return buffer.getvalue()
