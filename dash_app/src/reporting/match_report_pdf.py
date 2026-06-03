"""
Match Report PDF — Page 1 (Overview).
Renders the same content as the in-app Page-1 component but as a downloadable
PDF, using ReportLab. Light theme, white background, dashboard palette.

Design notes:
- DejaVuSans embedded for full Latin-Extended coverage (diacritics, Turkish, etc.)
- Pitch drawn natively in ReportLab (no Plotly/kaleido dependency)
- Player dots placed by explicit position-code lookup table, not formation digits
- Substitution rows: #n · Name ▼/▲min' ← #n2 · Replacement
- Event icons drawn as coloured geometric shapes (no emoji / no missing glyphs)
"""

from __future__ import annotations

import io
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from reportlab.lib.colors import HexColor, white, Color
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

from src.components.match_report_cards import (
    MatchMeta, TeamLineup, PlayerRow, PlayerEvents,
    extract_match_report,
)
from src.config import LOGOS_DIR
from src.team_mapping import logo_filename
from src.utils.logging import log


# ── Font registration ─────────────────────────────────────────────────────────

def _find_font(filename: str) -> Optional[Path]:
    import subprocess
    r = subprocess.run(
        ["find", "/Library", "/System/Library", "/usr",
         "-name", filename, "-not", "-path", "*/Volumes/*"],
        capture_output=True, text=True, timeout=10,
    )
    for line in r.stdout.splitlines():
        p = Path(line.strip())
        if p.exists():
            return p
    return None


_FONT_REGULAR = "Helvetica"
_FONT_BOLD    = "Helvetica-Bold"
_FONT_ITALIC  = "Helvetica-Oblique"


def _register_fonts():
    global _FONT_REGULAR, _FONT_BOLD, _FONT_ITALIC
    try:
        reg  = _find_font("DejaVuSans.ttf")
        bold = _find_font("DejaVuSans-Bold.ttf")
        if reg and bold:
            pdfmetrics.registerFont(TTFont("DejaVuSans",      str(reg)))
            pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(bold)))
            _FONT_REGULAR = "DejaVuSans"
            _FONT_BOLD    = "DejaVuSans-Bold"
            _FONT_ITALIC  = "DejaVuSans"
            log.info("PDF: DejaVuSans registered for Unicode coverage")
        else:
            log.warning("PDF: DejaVuSans not found — falling back to Helvetica")
    except Exception as exc:
        log.warning("PDF: Font registration failed (%s) — falling back to Helvetica", exc)


_register_fonts()


# ── Palette ───────────────────────────────────────────────────────────────────
PRIMARY       = HexColor("#8a1f33")
NAVY          = HexColor("#1b2838")
TEXT_PRIMARY  = HexColor("#1a1a2e")
TEXT_SECOND   = HexColor("#4a5568")
TEXT_MUTED    = HexColor("#718096")
BORDER        = HexColor("#e2e6ec")
BG_SOFT       = HexColor("#fafbfc")
GK_AMBER      = HexColor("#f59e0b")
CAPTAIN_GOLD  = HexColor("#ffd23f")
GREEN_ARROW   = HexColor("#16a34a")
RED_ARROW     = HexColor("#dc2626")
YELLOW_C      = HexColor("#eab308")
RED_C         = HexColor("#dc2626")
BLUE_C        = HexColor("#3b82f6")
PITCH_LINE    = Color(0.55, 0.55, 0.55, alpha=0.45)
PITCH_BG      = Color(0.95, 0.97, 0.95, alpha=1.0)


# ═══════════════════════════════════════════════════════════════════════════════
# PITCH COORDINATE ENGINE  (position-code driven)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Coordinate model: X in [0,1] left→right, Y in [0,1] bottom(own goal)→top.
# Every position code maps to a canonical (X, Y).
# When multiple players share the same base code (e.g. three CBs all "CB"),
# they are spread across the horizontal slots for their line.
#
# Lines and their Y anchors:
#   GK   Y=0.06
#   DEF  Y=0.22  (back line)
#   WB   Y=0.42  (wing-backs — wider & higher than full-backs)
#   DM   Y=0.40  (defensive mids — just ahead of backs, narrower than WBs)
#   MID  Y=0.52  (central midfield)
#   AM   Y=0.66  (attacking mid)
#   FWD  Y=0.82  (forwards)
#
# The SPREAD logic: given N players on the same Y-band, distribute them across
# N evenly spaced X slots between left_margin and right_margin, ordered
# left→right by their LR-order priority key.

# Canonical single-slot positions (X, Y)
_POS_XY: dict[str, tuple[float, float]] = {
    # Goalkeeper
    "GK":   (0.50, 0.06),
    # Back line — five distinct slots
    "LB":   (0.15, 0.22),
    "LCB":  (0.32, 0.22),
    "CB":   (0.50, 0.22),
    "RCB":  (0.68, 0.22),
    "RB":   (0.85, 0.22),
    "SW":   (0.50, 0.22),
    # Wing-backs (higher and wider)
    "LWB":  (0.10, 0.42),
    "RWB":  (0.90, 0.42),
    # Defensive mid
    "CDM":  (0.50, 0.40),
    "DM":   (0.50, 0.40),
    "DMC":  (0.50, 0.40),
    # Central midfield
    "MC":   (0.50, 0.52),
    "CM":   (0.50, 0.52),
    "LCM":  (0.35, 0.52),
    "RCM":  (0.65, 0.52),
    # Wide midfield
    "LM":   (0.15, 0.52),
    "ML":   (0.15, 0.52),
    "RM":   (0.85, 0.52),
    "MR":   (0.85, 0.52),
    # Attacking mid
    "CAM":  (0.50, 0.66),
    "AM":   (0.50, 0.66),
    "SS":   (0.50, 0.66),
    # Forwards
    "LW":   (0.18, 0.82),
    "RW":   (0.82, 0.82),
    "CF":   (0.50, 0.82),
    "ST":   (0.50, 0.82),
    "FW":   (0.50, 0.82),
}

# Left-to-right priority within a band (lower = further left).
# Used to sort duplicate-code players before spreading.
_POS_LR: dict[str, int] = {
    "LB": 0, "LWB": 0, "LM": 0, "ML": 0, "LW": 0,
    "LCB": 1, "LCM": 1,
    "CB": 2, "SW": 2, "CDM": 2, "DM": 2, "DMC": 2,
    "MC": 2, "CM": 2, "CAM": 2, "AM": 2, "SS": 2,
    "CF": 2, "ST": 2, "FW": 2,
    "RCB": 3, "RCM": 3,
    "RB": 4, "RWB": 4, "RM": 4, "MR": 4, "RW": 4,
    "GK": 2,
}

# Band each position belongs to (for grouping duplicate codes)
_POS_BAND: dict[str, str] = {
    "GK":  "GK",
    "LB": "DEF", "LCB": "DEF", "CB": "DEF", "RCB": "DEF", "RB": "DEF", "SW": "DEF",
    "LWB": "WB",  "RWB": "WB",
    "CDM": "DM",  "DM": "DM",  "DMC": "DM",
    "MC":  "MID", "CM": "MID", "LCM": "MID", "RCM": "MID",
    "LM":  "MID", "ML": "MID", "RM":  "MID", "MR":  "MID",
    "CAM": "AM",  "AM": "AM",  "SS":  "AM",
    "LW":  "FWD", "RW": "FWD", "CF":  "FWD", "ST":  "FWD", "FW":  "FWD",
}

# Horizontal spread anchors for each band — up to 5 slots, left→right.
# Indexed by (band, n_players) → list of X values.
# When a band needs N evenly spread slots we generate them symmetrically.
_BAND_Y: dict[str, float] = {
    "GK":  0.06,
    "DEF": 0.22,
    "WB":  0.42,
    "DM":  0.40,
    "MID": 0.52,
    "AM":  0.66,
    "FWD": 0.82,
}

# X margins for each band when spreading N players
_BAND_MARGIN: dict[str, float] = {
    "GK":  0.0,
    "DEF": 0.12,
    "WB":  0.10,   # LWB at X=0.10, RWB at X=0.90 for a 2-player spread
    "DM":  0.18,
    "MID": 0.14,
    "AM":  0.20,
    "FWD": 0.15,
}


def _spread_xs(n: int, band: str) -> list[float]:
    """Return n evenly-spaced X positions for the given band."""
    if n == 1:
        return [0.50]
    margin = _BAND_MARGIN.get(band, 0.12)
    step   = (1.0 - 2 * margin) / (n - 1)
    return [margin + step * i for i in range(n)]


def _pos_code(pr: PlayerRow) -> str:
    return (pr.detailed_position or "").upper().strip()


def _player_band(pr: PlayerRow) -> str:
    code = _pos_code(pr)
    if code in _POS_BAND:
        return _POS_BAND[code]
    # Fallback via position_group
    pg = (pr.position_group or "").upper()
    return {"GK": "GK", "DEF": "DEF", "MID": "MID", "FWD": "FWD"}.get(pg, "MID")


def _lr_key(pr: PlayerRow) -> int:
    code = _pos_code(pr)
    return _POS_LR.get(code, 2)


def formation_coords(starters: list[PlayerRow]) -> list[tuple[float, float]]:
    """
    Return (X, Y) in [0,1]×[0,1] for each starter at the same index.

    Algorithm:
    1. Group players by their position band (GK/DEF/WB/DM/MID/AM/FWD).
    2. Within each band, sort players left→right by their LR-priority key
       (position code determines left/right half; formation slot breaks ties).
    3. Spread N players evenly across the band's horizontal range.
    4. Assign Y from the band's anchor.
    """
    s11 = starters[:11]
    n   = len(s11)
    if n == 0:
        return []

    # Group indices by band
    bands: dict[str, list[int]] = defaultdict(list)
    for i, pr in enumerate(s11):
        bands[_player_band(pr)].append(i)

    coords: list[tuple[float, float]] = [(0.50, 0.50)] * n

    for band, indices in bands.items():
        y = _BAND_Y.get(band, 0.50)

        # Sort within band: LR-priority first, formation slot as tiebreak
        indices_sorted = sorted(
            indices,
            key=lambda i: (_lr_key(s11[i]), s11[i].formation_slot),
        )

        xs = _spread_xs(len(indices_sorted), band)
        for rank, idx in enumerate(indices_sorted):
            coords[idx] = (xs[rank], y)

    return coords


# ═══════════════════════════════════════════════════════════════════════════════
# NATIVE REPORTLAB PITCH DRAWING
# ═══════════════════════════════════════════════════════════════════════════════

def _rl_line(c, x0: float, y0: float, x1: float, y1: float):
    c.setStrokeColor(PITCH_LINE)
    c.setLineWidth(0.6)
    c.line(x0, y0, x1, y1)


def _draw_pitch_rl(
    c,
    lineup: TeamLineup,
    dot_color: Color,
    px: float,    # left edge of pitch box (points)
    py: float,    # bottom edge of pitch box (points)
    pw: float,    # pitch box width (points)
    ph: float,    # pitch box height (points)
):
    """
    Draw a vertical football pitch with player dots, natively in ReportLab.

    px, py = bottom-left corner of the pitch bounding box (ReportLab coords).
    pw, ph = width and height of the pitch bounding box.
    """

    def _px(x_frac: float) -> float:
        return px + x_frac * pw

    def _py(y_frac: float) -> float:
        return py + y_frac * ph

    # ── Pitch background ─────────────────────────────────────────────────────
    c.setFillColor(PITCH_BG)
    c.rect(px, py, pw, ph, fill=1, stroke=0)

    # ── Pitch markings ───────────────────────────────────────────────────────
    lw_thin = 0.5
    c.setStrokeColor(PITCH_LINE)
    c.setLineWidth(lw_thin)

    # Outline
    c.rect(px, py, pw, ph, fill=0, stroke=1)

    # Halfway line
    c.line(_px(0), _py(0.50), _px(1), _py(0.50))

    # Centre circle (radius ≈ 9.15m on a 68m wide pitch → ~13% of width)
    r_cc = pw * 0.13
    c.circle(_px(0.50), _py(0.50), r_cc, fill=0, stroke=1)

    # Centre spot
    c.setFillColor(PITCH_LINE)
    c.circle(_px(0.50), _py(0.50), 1.2, fill=1, stroke=0)

    # Penalty boxes (own half — bottom)
    box_x0 = _px(0.22)
    box_x1 = _px(0.78)
    c.rect(box_x0, _py(0.0), box_x1 - box_x0, _py(0.17) - _py(0.0), fill=0, stroke=1)
    # Penalty box (opponent half — top)
    c.rect(box_x0, _py(0.83), box_x1 - box_x0, _py(1.0) - _py(0.83), fill=0, stroke=1)

    # 6-yard boxes
    sy_x0 = _px(0.36)
    sy_x1 = _px(0.64)
    c.rect(sy_x0, _py(0.0),  sy_x1 - sy_x0, _py(0.06) - _py(0.0),  fill=0, stroke=1)
    c.rect(sy_x0, _py(0.94), sy_x1 - sy_x0, _py(1.0)  - _py(0.94), fill=0, stroke=1)

    # Penalty spots
    c.setFillColor(PITCH_LINE)
    c.circle(_px(0.50), _py(0.12), 1.2, fill=1, stroke=0)
    c.circle(_px(0.50), _py(0.88), 1.2, fill=1, stroke=0)

    # Corner arcs (small quarter-circles at each corner)
    arc_r = pw * 0.025
    for corner_x, corner_y in [(0, 0), (1, 0), (0, 1), (1, 1)]:
        cx_ = _px(corner_x)
        cy_ = _py(corner_y)
        # Draw a small filled arc by clipping a circle to the pitch area
        c.setStrokeColor(PITCH_LINE)
        c.setLineWidth(lw_thin)
        c.circle(cx_, cy_, arc_r, fill=0, stroke=1)

    # ── Player dots ──────────────────────────────────────────────────────────
    coords = formation_coords(lineup.starters)
    dot_r  = min(pw, ph) * 0.042   # radius — large enough for 2-digit numbers

    for pr, (xf, yf) in zip(lineup.starters, coords):
        cx_ = _px(xf)
        cy_ = _py(yf)
        is_gk = pr.position_group == "GK"

        fill = GK_AMBER if is_gk else dot_color
        c.setFillColor(fill)
        c.setStrokeColor(white)
        c.setLineWidth(1.0)
        c.circle(cx_, cy_, dot_r, fill=1, stroke=1)

        # Jersey number centred inside dot
        shirt_str = str(pr.shirt) if pr.shirt is not None else "·"
        font_size = 6.5 if len(shirt_str) > 1 else 7.5
        c.setFillColor(white)
        c.setFont(_FONT_BOLD, font_size)
        c.drawCentredString(cx_, cy_ - font_size * 0.35, shirt_str)


# ── Logo / image helpers ──────────────────────────────────────────────────────

def _logo_path(team: str) -> Optional[Path]:
    p = LOGOS_DIR / logo_filename(team)
    return p if p.exists() else None


def _draw_logo(c, team: str, x: float, y: float, size: float):
    lp = _logo_path(team)
    if not lp:
        return
    try:
        from reportlab.lib.utils import ImageReader
        c.drawImage(ImageReader(str(lp)), x - size / 2, y - size / 2,
                    width=size, height=size, preserveAspectRatio=True, mask="auto")
    except Exception as exc:
        log.warning("Logo embed failed (%s): %s", team, exc)


# ── Text helpers ──────────────────────────────────────────────────────────────

def _wrap(c, text: str, font: str, size: float, max_w: float) -> str:
    if c.stringWidth(text, font, size) <= max_w:
        return text
    while text and c.stringWidth(text + "…", font, size) > max_w:
        text = text[:-1]
    return text + "…"


def _sw(c, text: str, size: float, bold: bool = False) -> float:
    f = _FONT_BOLD if bold else _FONT_REGULAR
    return c.stringWidth(text, f, size)


# ── Shirt badge ───────────────────────────────────────────────────────────────

def _draw_shirt(c, x: float, y: float, shirt: Optional[int], is_gk: bool,
                size: float = 5.5 * mm):
    c.setFillColor(GK_AMBER if is_gk else PRIMARY)
    c.circle(x, y, size / 2, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(_FONT_BOLD, 7)
    c.drawCentredString(x, y - 2.3, str(shirt) if shirt is not None else "·")


# ── Event icon drawing ────────────────────────────────────────────────────────

def _draw_event_icons(c, ev: PlayerEvents, x: float, y_center: float) -> float:
    gap      = 0.8 * mm
    icon_h   = 3.5 * mm
    icon_w   = 2.4 * mm
    circle_r = 1.7 * mm
    cx = x

    for _ in range(ev.goals):
        c.setFillColor(TEXT_PRIMARY)
        c.circle(cx + circle_r, y_center, circle_r, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont(_FONT_BOLD, 5)
        c.drawCentredString(cx + circle_r, y_center - 1.7, "G")
        cx += circle_r * 2 + gap

    for _ in range(ev.own_goals):
        c.setFillColor(RED_C)
        c.circle(cx + circle_r, y_center, circle_r, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont(_FONT_BOLD, 4)
        c.drawCentredString(cx + circle_r, y_center - 1.4, "OG")
        cx += circle_r * 2 + gap

    for _ in range(ev.assists):
        c.setFillColor(BLUE_C)
        c.circle(cx + circle_r, y_center, circle_r, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont(_FONT_BOLD, 5)
        c.drawCentredString(cx + circle_r, y_center - 1.7, "A")
        cx += circle_r * 2 + gap

    for _ in range(ev.yellow_cards):
        c.setFillColor(YELLOW_C)
        c.roundRect(cx, y_center - icon_h / 2, icon_w, icon_h, 0.5, fill=1, stroke=0)
        cx += icon_w + gap

    for _ in range(ev.red_cards):
        c.setFillColor(RED_C)
        c.roundRect(cx, y_center - icon_h / 2, icon_w, icon_h, 0.5, fill=1, stroke=0)
        cx += icon_w + gap

    return cx


def _icons_width(ev: PlayerEvents) -> float:
    gap      = 0.8 * mm
    circle_r = 1.7 * mm
    icon_w   = 2.4 * mm
    w = 0.0
    w += ev.goals        * (circle_r * 2 + gap)
    w += ev.own_goals    * (circle_r * 2 + gap)
    w += ev.assists      * (circle_r * 2 + gap)
    w += ev.yellow_cards * (icon_w + gap)
    w += ev.red_cards    * (icon_w + gap)
    return w


# ── Player list ───────────────────────────────────────────────────────────────

def _draw_player_list(c, players: list[PlayerRow], all_players: dict[str, PlayerRow],
                      x: float, y_top: float, width: float,
                      title: str, is_bench: bool = False,
                      row_h: float = 5.2 * mm, y_floor: float = 14 * mm) -> float:
    c.setFillColor(PRIMARY)
    c.setFont(_FONT_BOLD, 8)
    c.drawString(x, y_top, title.upper())
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.5)
    c.line(x, y_top - 1.5, x + width, y_top - 1.5)

    y = y_top - row_h
    drawn = 0
    truncated = 0

    for pr in players:
        if y - row_h < y_floor:
            truncated = len(players) - drawn
            break
        drawn += 1
        row_mid_y = y + row_h / 2
        is_gk = pr.position_group == "GK"

        shirt_cx = x + 3.0 * mm
        _draw_shirt(c, shirt_cx, row_mid_y, pr.shirt, is_gk, size=4.5 * mm)

        pos_label = (pr.detailed_position or pr.position_group or "").upper()
        pos_w = 0.0
        if pos_label:
            c.setFont(_FONT_BOLD, 6)
            pos_w = c.stringWidth(pos_label, _FONT_BOLD, 6) + 2.4 * mm
            pos_x = x + width - pos_w
            c.setFillColor(HexColor("#eef0f4"))
            c.roundRect(pos_x, row_mid_y - 1.8 * mm, pos_w, 3.6 * mm, 1.2, fill=1, stroke=0)
            c.setFillColor(TEXT_SECOND)
            c.drawCentredString(pos_x + pos_w / 2, row_mid_y - 1.0 * mm, pos_label)

        sub_text  = ""
        sub_color = TEXT_PRIMARY
        partner_shirt_val: Optional[int] = None
        partner_name_val: str = ""

        if not is_bench and pr.subbed_off:
            sub_text  = f"▼{pr.subbed_off.minute}'" if pr.subbed_off.minute else "▼"
            sub_color = RED_ARROW
            if pr.subbed_off.partner_id:
                partner = all_players.get(pr.subbed_off.partner_id)
                if partner:
                    partner_shirt_val = partner.shirt
                    partner_name_val  = partner.name

        elif is_bench and pr.subbed_on:
            sub_text  = f"▲{pr.subbed_on.minute}'" if pr.subbed_on.minute else "▲"
            sub_color = GREEN_ARROW
            if pr.subbed_on.partner_id:
                partner = all_players.get(pr.subbed_on.partner_id)
                if partner:
                    partner_shirt_val = partner.shirt
                    partner_name_val  = partner.name

        icon_w = _icons_width(pr.events)
        cap_w  = 3.5 * mm if pr.is_captain else 0.0

        arrow_w = 0.0
        if sub_text:
            c.setFont(_FONT_BOLD, 7.5)
            arrow_w = c.stringWidth(sub_text, _FONT_BOLD, 7.5) + 1.0 * mm

        partner_block_w = 0.0
        if partner_name_val:
            c.setFont(_FONT_REGULAR, 7)
            pname_str = (f"← #{partner_shirt_val} {partner_name_val}"
                         if partner_shirt_val else f"← {partner_name_val}")
            partner_block_w = c.stringWidth(pname_str, _FONT_REGULAR, 7) + 1.5 * mm

        name_x     = x + 7.0 * mm
        name_avail = width - 7.0 * mm - icon_w - cap_w - arrow_w - partner_block_w - pos_w - 1.5 * mm
        if name_avail < 8 * mm:
            name_avail      = 8 * mm
            partner_block_w = 0.0

        c.setFillColor(TEXT_PRIMARY)
        c.setFont(_FONT_REGULAR, 8.5)
        display_name = _wrap(c, pr.name or "—", _FONT_REGULAR, 8.5, name_avail)
        c.drawString(name_x, row_mid_y - 1.4 * mm, display_name)
        cur_x = name_x + c.stringWidth(display_name, _FONT_REGULAR, 8.5) + 1.0 * mm

        if pr.is_captain:
            c.setFillColor(CAPTAIN_GOLD)
            c.circle(cur_x + 1.4 * mm, row_mid_y, 1.5 * mm, fill=1, stroke=0)
            c.setFillColor(TEXT_PRIMARY)
            c.setFont(_FONT_BOLD, 5.5)
            c.drawCentredString(cur_x + 1.4 * mm, row_mid_y - 1.8, "C")
            cur_x += 3.2 * mm

        if icon_w > 0:
            cur_x = _draw_event_icons(c, pr.events, cur_x, row_mid_y)
            cur_x += 0.5 * mm

        if sub_text:
            c.setFillColor(sub_color)
            c.setFont(_FONT_BOLD, 7.5)
            c.drawString(cur_x, row_mid_y - 1.4 * mm, sub_text)
            cur_x += c.stringWidth(sub_text, _FONT_BOLD, 7.5) + 1.0 * mm

        if partner_name_val and partner_block_w > 0:
            pname_str = (f"← #{partner_shirt_val} {partner_name_val}"
                         if partner_shirt_val else f"← {partner_name_val}")
            c.setFillColor(TEXT_MUTED)
            c.setFont(_FONT_REGULAR, 7)
            c.drawString(cur_x, row_mid_y - 1.2 * mm,
                         _wrap(c, pname_str, _FONT_REGULAR, 7,
                               x + width - pos_w - 1 * mm - cur_x))

        y -= row_h

    if truncated:
        c.setFillColor(TEXT_MUTED)
        c.setFont(_FONT_ITALIC, 7)
        c.drawString(x, y + 1 * mm, f"+ {truncated} more")
        y -= row_h

    return y


# ── Lineup panel ──────────────────────────────────────────────────────────────

def _draw_lineup_panel(c, lineup: TeamLineup, pill_color: Color,
                       x: float, y_top: float,
                       width: float, pitch_h: float = 70 * mm) -> float:
    # Header band
    head_h = 13 * mm
    c.setFillColor(BG_SOFT)
    c.roundRect(x, y_top - head_h, width, head_h, 2, fill=1, stroke=0)
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.4)
    c.roundRect(x, y_top - head_h, width, head_h, 2, fill=0, stroke=1)

    _draw_logo(c, lineup.team_name, x + 6.5 * mm, y_top - head_h / 2, size=9 * mm)

    c.setFillColor(TEXT_PRIMARY)
    c.setFont(_FONT_BOLD, 11)
    team_label = _wrap(c, lineup.team_name.upper(), _FONT_BOLD, 11, width - 38 * mm)
    c.drawString(x + 14 * mm, y_top - head_h / 2 + 0.6 * mm, team_label)

    pill = lineup.formation_code or "—"
    c.setFont(_FONT_BOLD, 8)
    pill_w = c.stringWidth(pill, _FONT_BOLD, 8) + 5 * mm
    pill_x = x + width - pill_w - 3 * mm
    pill_y = y_top - head_h / 2 - 2.3 * mm
    c.setFillColor(pill_color)
    c.roundRect(pill_x, pill_y, pill_w, 4.6 * mm, 2.3, fill=1, stroke=0)
    c.setFillColor(white)
    c.drawCentredString(pill_x + pill_w / 2, pill_y + 1.2 * mm, pill)

    y = y_top - head_h - 2 * mm

    # Native ReportLab pitch
    pitch_x = x + 2 * mm
    pitch_y = y - pitch_h        # bottom-left of pitch in ReportLab coords
    pitch_w = width - 4 * mm

    _draw_pitch_rl(c, lineup, pill_color,
                   px=pitch_x, py=pitch_y, pw=pitch_w, ph=pitch_h)

    y -= pitch_h + 3 * mm

    all_players = {p.player_id: p for p in lineup.starters + lineup.bench}

    y = _draw_player_list(c, lineup.starters, all_players,
                          x + 2 * mm, y, width - 4 * mm,
                          "Starting XI", is_bench=False)
    y -= 2.5 * mm

    if lineup.bench:
        y = _draw_player_list(c, lineup.bench, all_players,
                              x + 2 * mm, y, width - 4 * mm,
                              "Bench", is_bench=True)
    return y


# ── Page chrome ───────────────────────────────────────────────────────────────

def _draw_page_chrome(c, pw: float, ph: float):
    c.setFillColor(white)
    c.rect(0, 0, pw, ph, fill=1, stroke=0)
    c.setFillColor(PRIMARY)
    c.rect(0, ph - 3 * mm, pw, 3 * mm, fill=1, stroke=0)
    c.setFillColor(TEXT_MUTED)
    c.setFont(_FONT_REGULAR, 7)
    c.drawCentredString(pw / 2, 6 * mm,
        f"Data: Opta · Generated {datetime.now().strftime('%d/%m/%Y %H:%M')} · FMP Serie A Dashboard")


def _draw_header(c, meta: MatchMeta, pw: float, top_y: float) -> float:
    c.setFillColor(PRIMARY)
    c.setFont(_FONT_BOLD, 13)
    c.drawString(15 * mm, top_y, "MATCH REPORT")
    c.setFillColor(TEXT_SECOND)
    c.setFont(_FONT_REGULAR, 8.5)
    c.drawRightString(pw - 15 * mm, top_y, "Page 1 · Overview")
    c.setStrokeColor(PRIMARY)
    c.setLineWidth(1.2)
    c.line(15 * mm, top_y - 2 * mm, pw - 15 * mm, top_y - 2 * mm)
    return top_y - 7 * mm


def _draw_scoreboard(c, meta: MatchMeta, pw: float, y_top: float) -> float:
    cx = pw / 2

    eyebrow = " · ".join(x for x in [
        f"Matchday {meta.week}" if meta.week else None, meta.competition] if x)
    if eyebrow:
        c.setFillColor(TEXT_SECOND)
        c.setFont(_FONT_BOLD, 8)
        c.drawCentredString(cx, y_top, eyebrow.upper())

    score_y   = y_top - 21 * mm
    logo_size = 20 * mm

    _draw_logo(c, meta.home_team, cx - 48 * mm, score_y, logo_size)
    c.setFillColor(TEXT_PRIMARY)
    c.setFont(_FONT_BOLD, 10)
    c.drawCentredString(cx - 48 * mm, score_y - 14 * mm, meta.home_team.upper())

    _draw_logo(c, meta.away_team, cx + 48 * mm, score_y, logo_size)
    c.drawCentredString(cx + 48 * mm, score_y - 14 * mm, meta.away_team.upper())

    score_text = (
        f"{meta.home_score} – {meta.away_score}"
        if meta.home_score is not None and meta.away_score is not None else "vs"
    )
    c.setFillColor(PRIMARY)
    c.setFont(_FONT_BOLD, 26)
    c.drawCentredString(cx, score_y - 4 * mm, score_text)

    date_str = ""
    if meta.date:
        try:
            date_str = pd.to_datetime(meta.date).strftime("%d/%m/%Y")
        except Exception:
            date_str = meta.date
    line = " · ".join(x for x in [meta.venue, date_str, meta.time] if x)
    if line:
        c.setFillColor(TEXT_SECOND)
        c.setFont(_FONT_REGULAR, 8.5)
        c.drawCentredString(cx, score_y - 20 * mm, line)

    return score_y - 25 * mm


def _draw_meta_strip(c, meta: MatchMeta, pw: float, y_top: float) -> float:
    items = []
    if meta.week is not None:
        items.append(("MATCHDAY", str(meta.week)))
    if meta.date:
        try:
            d = pd.to_datetime(meta.date).strftime("%d %b %Y")
        except Exception:
            d = meta.date
        items.append(("DATE", d))
    if meta.time:
        items.append(("KICK-OFF", meta.time))
    if meta.venue:
        items.append(("STADIUM", meta.venue))
    if not items:
        return y_top

    strip_h = 12 * mm
    strip_w = pw - 30 * mm
    x0      = 15 * mm

    c.setFillColor(BG_SOFT)
    c.roundRect(x0, y_top - strip_h, strip_w, strip_h, 2, fill=1, stroke=0)
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.4)
    c.roundRect(x0, y_top - strip_h, strip_w, strip_h, 2, fill=0, stroke=1)

    n      = len(items)
    cell_w = strip_w / n
    for i, (label, value) in enumerate(items):
        ccx = x0 + cell_w * i + cell_w / 2
        c.setFillColor(TEXT_SECOND)
        c.setFont(_FONT_BOLD, 6.5)
        c.drawCentredString(ccx, y_top - 4.2 * mm, label)
        c.setFillColor(TEXT_PRIMARY)
        c.setFont(_FONT_BOLD, 9.5)
        c.drawCentredString(ccx, y_top - 8.8 * mm,
                            _wrap(c, value, _FONT_BOLD, 9.5, cell_w - 4 * mm))
        if i > 0:
            c.setStrokeColor(BORDER)
            c.setLineWidth(0.4)
            c.line(x0 + cell_w * i, y_top - strip_h + 2 * mm,
                   x0 + cell_w * i, y_top - 2 * mm)

    return y_top - strip_h - 3 * mm


# ── Main entry point ──────────────────────────────────────────────────────────

def build_match_report_pdf(match_csv: Path, season: str) -> bytes:
    """Build Page 1 of the Match Report and return raw PDF bytes."""
    meta, home_lu, away_lu = extract_match_report(match_csv, season)

    buf = io.BytesIO()
    pw, ph = A4
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Match Report – {meta.home_team} vs {meta.away_team}")
    c.setAuthor("FMP Serie A Dashboard")

    _draw_page_chrome(c, pw, ph)

    y = ph - 11 * mm
    y = _draw_header(c, meta, pw, y)
    y = _draw_scoreboard(c, meta, pw, y - 2 * mm)
    y = _draw_meta_strip(c, meta, pw, y)

    panel_w = (pw - 30 * mm - 5 * mm) / 2
    left_x  = 15 * mm
    right_x = left_x + panel_w + 5 * mm

    available = y - 18 * mm
    pitch_h   = max(42 * mm, min(65 * mm, available - 145 * mm))

    _draw_lineup_panel(c, home_lu, PRIMARY, left_x,  y, panel_w, pitch_h=pitch_h)
    _draw_lineup_panel(c, away_lu, NAVY,    right_x, y, panel_w, pitch_h=pitch_h)

    c.showPage()
    c.save()
    return buf.getvalue()
