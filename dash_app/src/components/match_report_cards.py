"""
Match Report — UI Components
============================
Page 1: Match Overview.

Renders metadata, score, formations with pitch, starting XI and bench
for both teams. Visual language matches the rest of the dashboard
(white background, modern cards, subtle borders).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from src.team_mapping import canonical_name, logo_url


# ═══════════════════════════════════════════════════════════════════════════════
# DATA EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

# Opta Player Position codes (from the "Player Position" qualifier)
#   1 = Goalkeeper  2 = Defender  3 = Midfielder  4 = Forward  5 = Substitute
_POSITION_GROUP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD", 5: "SUB"}

# Opta detailed position → pitch Y-line key.
# Wing-backs (LWB/RWB) operate in the midfield band, not the defensive line.
_DETAIL_TO_YKEY = {
    "GK":  "GK",
    "CB":  "DEF",
    "LB":  "DEF",
    "RB":  "DEF",
    "SW":  "DEF",
    "LWB": "DM",
    "RWB": "DM",
    "DM":  "DM",
    "DMC": "DM",
    "MC":  "MID",
    "ML":  "MID",
    "MR":  "MID",
    "CAM": "AM",
    "SS":  "AM",
    "LW":  "FWD",
    "RW":  "FWD",
    "CF":  "FWD",
    "ST":  "FWD",
    "FW":  "FWD",
}


@dataclass
class PlayerEvents:
    """Match events attributed to a player."""
    goals: int = 0
    own_goals: int = 0
    assists: int = 0
    yellow_cards: int = 0
    red_cards: int = 0   # includes second yellow


@dataclass
class SubInfo:
    """Substitution details."""
    minute: Optional[int] = None
    partner_id: Optional[str] = None    # who came on / went off in exchange
    partner_name: Optional[str] = None


@dataclass
class PlayerRow:
    player_id: str
    name: str
    shirt: Optional[int]
    position_group: str         # GK / DEF / MID / FWD / SUB
    formation_slot: int         # 1..11 starter, 0 bench
    detailed_position: str      # e.g. CB, CAM
    is_captain: bool
    events: PlayerEvents = field(default_factory=PlayerEvents)
    subbed_off: Optional[SubInfo] = None
    subbed_on: Optional[SubInfo] = None


@dataclass
class TeamLineup:
    team_name: str
    team_raw: str
    formation_code: str
    starters: list[PlayerRow]
    bench: list[PlayerRow]
    coach: Optional[str]


@dataclass
class MatchMeta:
    match_id: str
    week: Optional[int]
    date: Optional[str]
    time: Optional[str]
    venue: Optional[str]
    competition: Optional[str]
    home_team: str
    away_team: str
    home_raw: str
    away_raw: str
    home_score: Optional[int]
    away_score: Optional[int]


# ─── Qualifier helpers ────────────────────────────────────────────────────────

def _parse_qualifier_list(rq: str, key: str) -> list[str]:
    m = re.search(rf"{re.escape(key)}\s*:\s*([^;]+)", rq)
    if not m:
        return []
    return [x.strip() for x in m.group(1).split(",")]


def _parse_qualifier_value(rq: str, key: str) -> Optional[str]:
    m = re.search(rf"{re.escape(key)}\s*:\s*([^;]+)", rq)
    if not m:
        return None
    val = m.group(1).strip()
    return val.split(",")[0].strip() if "," in val else val


def _format_formation_code(code) -> str:
    """Turn 433 / '433' into '4-3-3'."""
    if code is None or pd.isna(code):
        return "—"
    s = str(int(code)) if isinstance(code, (int, float)) else str(code).strip()
    if not s.isdigit():
        return s
    return "-".join(s)


# ─── Event extraction ─────────────────────────────────────────────────────────

def _extract_player_events(events: pd.DataFrame) -> dict[str, PlayerEvents]:
    result: dict[str, PlayerEvents] = {}

    def _get(pid: str) -> PlayerEvents:
        if pid not in result:
            result[pid] = PlayerEvents()
        return result[pid]

    for _, row in events.iterrows():
        pid = str(row.get("player_id", "") or "")
        if not pid or pid == "nan":
            continue
        tid = row.get("type_id")
        rq  = str(row.get("represented_qualifiers", "") or "")

        if tid == 16:   # Goal
            if str(row.get("own goal", "") or "").strip().lower() == "si":
                _get(pid).own_goals += 1
            else:
                _get(pid).goals += 1
                # Find the assist pass via Related event ID
                rel_m = re.search(r"Related event ID\s*:\s*(\d+)", rq)
                if rel_m:
                    rel_id = int(rel_m.group(1))
                    for _, ar in events[events["event_id"] == rel_id].iterrows():
                        ar_rq = str(ar.get("represented_qualifiers", "") or "")
                        if re.search(r"\bAssist\s*:", ar_rq):
                            ap = str(ar.get("player_id", "") or "")
                            if ap and ap != "nan":
                                _get(ap).assists += 1
                            break

        elif tid == 17:   # Card
            if re.search(r"Red Card\s*:\s*Si", rq, re.I):
                _get(pid).red_cards += 1
            elif re.search(r"Second yellow\s*:\s*Si", rq, re.I):
                _get(pid).red_cards += 1
            elif re.search(r"Yellow Card\s*:\s*Si", rq, re.I):
                _get(pid).yellow_cards += 1

    return result


def _extract_substitutions(
    events: pd.DataFrame,
) -> tuple[dict[str, SubInfo], dict[str, SubInfo]]:
    """
    Returns (subbed_off_map, subbed_on_map) keyed by player_id.
    type 18 = Player Off, type 19 = Player On.
    Pairs are linked via 'Related event ID' in the on-event's qualifiers.
    """
    off_events = events[events["type_id"] == 18]
    on_events  = events[events["type_id"] == 19]

    off_by_eid: dict[int, tuple[str, int]] = {}
    for _, row in off_events.iterrows():
        eid = row.get("event_id")
        pid = str(row.get("player_id", "") or "")
        min_ = int(row.get("time_min", 0) or 0)
        if eid is not None and pid and pid != "nan":
            off_by_eid[int(eid)] = (pid, min_)

    subbed_off: dict[str, SubInfo] = {}
    subbed_on:  dict[str, SubInfo] = {}

    for _, row in on_events.iterrows():
        on_pid = str(row.get("player_id", "") or "")
        if not on_pid or on_pid == "nan":
            continue
        minute = int(row.get("time_min", 0) or 0)
        rq = str(row.get("represented_qualifiers", "") or "")
        rel_m = re.search(r"Related event ID\s*:\s*(\d+)", rq)
        if rel_m:
            rel_id = int(rel_m.group(1))
            if rel_id in off_by_eid:
                off_pid, _ = off_by_eid[rel_id]
                subbed_on[on_pid]   = SubInfo(minute=minute, partner_id=off_pid)
                subbed_off[off_pid] = SubInfo(minute=minute, partner_id=on_pid)

    return subbed_off, subbed_on


# ─── Lineup builder ───────────────────────────────────────────────────────────

def _build_team_lineup(
    events: pd.DataFrame,
    team_raw: str,
    player_events: dict[str, PlayerEvents],
    subbed_off_map: dict[str, SubInfo],
    subbed_on_map: dict[str, SubInfo],
) -> TeamLineup:
    pdir = (
        events[events["team_name"] == team_raw]
        .dropna(subset=["player_id"])
        .drop_duplicates(subset=["player_id"], keep="first")
        .set_index("player_id")
    )

    def _name(pid: str) -> str:
        if pid in pdir.index:
            v = pdir.at[pid, "player_name"]
            return str(v) if pd.notna(v) else ""
        return ""

    def _detailed_pos(pid: str) -> str:
        if pid in pdir.index and "position" in pdir.columns:
            v = pdir.at[pid, "position"]
            return str(v) if pd.notna(v) else ""
        return ""

    lineup_rows = events[(events["type_id"] == 34) & (events["team_name"] == team_raw)]
    if lineup_rows.empty:
        return TeamLineup(canonical_name(team_raw), team_raw, "—", [], [], None)

    row = lineup_rows.iloc[0]
    rq  = str(row.get("represented_qualifiers", "") or "")

    involved   = _parse_qualifier_list(rq, "Involved")
    positions  = _parse_qualifier_list(rq, "Player Position")
    jerseys    = _parse_qualifier_list(rq, "Jersey Number")
    slots      = _parse_qualifier_list(rq, "Team Player Formation")
    captain_id = _parse_qualifier_value(rq, "Captain")

    formation_code = _format_formation_code(row.get("formation"))

    starters: list[PlayerRow] = []
    bench:    list[PlayerRow] = []

    for i, pid in enumerate(involved):
        try:
            pos_code = int(positions[i]) if i < len(positions) else 5
        except (ValueError, TypeError):
            pos_code = 5
        try:
            slot = int(slots[i]) if i < len(slots) else 0
        except (ValueError, TypeError):
            slot = 0
        try:
            shirt = int(jerseys[i]) if i < len(jerseys) and jerseys[i] else None
        except (ValueError, TypeError):
            shirt = None

        name = _name(pid)
        pr = PlayerRow(
            player_id=pid,
            name=name,
            shirt=shirt,
            position_group=_POSITION_GROUP.get(pos_code, "SUB"),
            formation_slot=slot,
            detailed_position=_detailed_pos(pid),
            is_captain=(pid == captain_id),
            events=player_events.get(pid, PlayerEvents()),
            subbed_off=subbed_off_map.get(pid),
            subbed_on=subbed_on_map.get(pid),
        )
        if slot and slot >= 1:
            starters.append(pr)
        else:
            # Only keep bench players whose name we can resolve
            if name:
                bench.append(pr)

    starters.sort(key=lambda p: p.formation_slot)

    # Resolve partner names after all PlayerRows exist
    all_by_id = {p.player_id: p for p in starters + bench}
    for pr in starters + bench:
        if pr.subbed_off and pr.subbed_off.partner_id:
            partner = all_by_id.get(pr.subbed_off.partner_id)
            pr.subbed_off.partner_name = partner.name if partner else _name(pr.subbed_off.partner_id)
        if pr.subbed_on and pr.subbed_on.partner_id:
            partner = all_by_id.get(pr.subbed_on.partner_id)
            pr.subbed_on.partner_name = partner.name if partner else _name(pr.subbed_on.partner_id)

    return TeamLineup(
        team_name=canonical_name(team_raw),
        team_raw=team_raw,
        formation_code=formation_code,
        starters=starters,
        bench=bench,
        coach=None,
    )


def _read_score_from_metadata(match_csv: Path, season: str) -> tuple[Optional[int], Optional[int]]:
    try:
        from src.analytics.data_loader import load_season_matches_cached
        df = load_season_matches_cached(season)
        if df is None or df.empty or "File" not in df.columns:
            return None, None
        hit = df[df["File"].astype(str) == match_csv.name]
        if hit.empty:
            return None, None
        r = hit.iloc[0]
        return int(r.get("HG", 0)), int(r.get("AG", 0))
    except Exception:
        return None, None


def extract_match_report(match_csv: Path, season: str) -> tuple[MatchMeta, TeamLineup, TeamLineup]:
    """Load an Opta events CSV and return structured match-report data."""
    events = pd.read_csv(match_csv, low_memory=False)

    stem_parts = match_csv.stem.split("_")
    home_hint = stem_parts[1] if len(stem_parts) >= 3 else None
    match_id  = "_".join(stem_parts[3:]) if len(stem_parts) >= 4 else match_csv.stem

    teams_raw = [t for t in events["team_name"].dropna().unique().tolist() if t]
    home_raw = next(
        (t for t in teams_raw if home_hint and canonical_name(t).lower() == canonical_name(home_hint).lower()),
        teams_raw[0] if teams_raw else "?",
    )
    away_raw = next(
        (t for t in teams_raw if t != home_raw),
        teams_raw[1] if len(teams_raw) > 1 else "?",
    )

    home_score, away_score = _read_score_from_metadata(match_csv, season)

    def _first(col: str) -> Optional[str]:
        if col not in events.columns:
            return None
        s = events[col].dropna()
        return str(s.iloc[0]) if not s.empty else None

    week_val = _first("week")
    try:
        week_int = int(float(week_val)) if week_val is not None else None
    except (ValueError, TypeError):
        week_int = None

    competition = (
        _first("competition_sponsor_name")
        or _first("competition_known_name")
        or _first("competition_name")
    )

    meta = MatchMeta(
        match_id=match_id,
        week=week_int,
        date=_first("local_date"),
        time=(_first("local_time") or "")[:5] or None,
        venue=_first("venue_long_name"),
        competition=competition,
        home_team=canonical_name(home_raw),
        away_team=canonical_name(away_raw),
        home_raw=home_raw,
        away_raw=away_raw,
        home_score=home_score,
        away_score=away_score,
    )

    player_events               = _extract_player_events(events)
    subbed_off_map, subbed_on_map = _extract_substitutions(events)

    home_lu = _build_team_lineup(events, home_raw, player_events, subbed_off_map, subbed_on_map)
    away_lu = _build_team_lineup(events, away_raw, player_events, subbed_off_map, subbed_on_map)
    return meta, home_lu, away_lu


# ═══════════════════════════════════════════════════════════════════════════════
# PITCH FORMATION VISUALISATION
# ═══════════════════════════════════════════════════════════════════════════════

# ── Formation-driven pitch coordinate engine ──────────────────────────────────
#
# Formation strings are parsed into a list of line counts from DEF→FWD.
# GK is always an implicit extra line at the very bottom (Y ≈ 6%).
# Outfield lines are spaced evenly between Y=20 and Y=88.
# Within each line, N players are spread evenly across X with a horizontal
# margin so even a 5-man line doesn't crowd the edges.
#
# Left→right ordering within each line uses the player's detailed_position
# code; only falls back to slot/list order when no code is present.

# Known formation strings → line counts (DEF→FWD, GK implicit).
_FORMATION_LINES: dict[str, list[int]] = {
    "4-4-2":   [4, 4, 2],
    "4-3-3":   [4, 3, 3],
    "4-5-1":   [4, 5, 1],
    "3-4-3":   [3, 4, 3],
    "3-5-2":   [3, 5, 2],
    "3-1-5-1": [3, 1, 5, 1],
    "5-3-2":   [5, 3, 2],
    "5-4-1":   [5, 4, 1],
    "4-2-2-2": [4, 2, 2, 2],
    "4-2-3-1": [4, 2, 3, 1],
    "2-4-4":   [2, 4, 4],
    "2-5-3":   [2, 5, 3],
    # Common aliases
    "4-1-4-1": [4, 1, 4, 1],
    "4-1-2-3": [4, 1, 2, 3],
    "3-4-1-2": [3, 4, 1, 2],
    "3-4-2-1": [3, 4, 2, 1],
    "4-3-2-1": [4, 3, 2, 1],
    "4-4-1-1": [4, 4, 1, 1],
}

# Left-to-right sort priority for a given detailed_position code.
# Lower value = further left. Used to order players within each Y-line.
_POS_LR: dict[str, int] = {
    # Defensive / back line
    "LB": 0, "LWB": 0,
    "LCB": 1,
    "CB": 2, "SW": 2,
    "RCB": 3,
    "RB": 4, "RWB": 4,
    # Midfield / DM line
    "DM": 0, "DMC": 0,
    "CDM": 1,
    "LM": 0, "ML": 0,
    "MC": 2, "CM": 2,
    "RM": 4, "MR": 4,
    # Attacking mid
    "CAM": 2, "AM": 2, "SS": 2,
    # Forwards
    "LW": 0, "LF": 1,
    "CF": 2, "ST": 2, "FW": 2,
    "RF": 3,
    "RW": 4,
    # GK always centred
    "GK": 2,
}


def _parse_formation(code: str) -> list[int] | None:
    """
    Return a list of outfield line counts for this formation string.
    Tries the known dict first; falls back to parsing the digit sequence.
    Returns None if the string can't be parsed or doesn't sum to 10.
    """
    if not code or code == "—":
        return None
    norm = code.strip()
    if norm in _FORMATION_LINES:
        return _FORMATION_LINES[norm]
    # Try to parse digits separated by hyphens
    parts = norm.split("-")
    try:
        counts = [int(p) for p in parts if p]
    except ValueError:
        return None
    if sum(counts) != 10:
        return None
    return counts


def _row_xs(n: int, margin: float = 12.0) -> list[float]:
    """Evenly spaced X positions for n players across [margin, 100-margin]."""
    if n == 1:
        return [50.0]
    step = (100.0 - 2 * margin) / (n - 1)
    return [margin + step * i for i in range(n)]


def _formation_positions(code: str, starters: list[PlayerRow]) -> list[tuple[float, float]]:
    """
    Return (x, y) pitch coordinates for each starter (same index as starters).

    Strategy:
    1.  Parse the formation string into a list of line counts.
    2.  GK sits at Y=6; outfield lines are distributed evenly from Y=22 to Y=88.
    3.  Within each line, sort players left→right by their position code.
    4.  Fall back to a position-code-based Y-line grouping when the formation
        string is unavailable or the player count doesn't match.
    """
    s11 = starters[:11]
    n   = len(s11)
    if n == 0:
        return []

    line_counts = _parse_formation(code)

    # ── Formation-driven path ─────────────────────────────────────────────────
    if line_counts and sum(line_counts) + 1 == n:  # 10 outfield + 1 GK
        n_outfield_lines = len(line_counts)
        y_gk  = 6.0
        y_top = 88.0
        y_bot = 22.0
        if n_outfield_lines == 1:
            y_lines = [y_top]
        else:
            step = (y_top - y_bot) / (n_outfield_lines - 1)
            y_lines = [y_bot + step * i for i in range(n_outfield_lines)]

        # Separate GK from outfield players (GK = position_group "GK")
        gk_indices  = [i for i, p in enumerate(s11) if p.position_group == "GK"]
        out_indices = [i for i, p in enumerate(s11) if p.position_group != "GK"]

        # If exactly one GK is missing from the outfield count, use first GK
        gk_idx = gk_indices[0] if gk_indices else None

        coords: list[tuple[float, float]] = [(50.0, 50.0)] * n

        # Place GK
        if gk_idx is not None:
            coords[gk_idx] = (50.0, y_gk)

        # Assign outfield players to lines in formation order
        line_ptr = 0
        player_ptr = 0
        for line_idx, count in enumerate(line_counts):
            y = y_lines[line_idx]
            # Take `count` outfield players (in their current list order)
            batch_indices = out_indices[player_ptr: player_ptr + count]
            player_ptr += count

            # Sort batch left→right by position code
            def _lr(idx: int) -> tuple[int, int]:
                dp = (s11[idx].detailed_position or "").upper()
                return (_POS_LR.get(dp, 2), s11[idx].formation_slot)

            batch_sorted = sorted(batch_indices, key=_lr)
            xs = _row_xs(len(batch_sorted))
            for rank, idx in enumerate(batch_sorted):
                coords[idx] = (xs[rank], y)

            line_ptr += 1

        return coords

    # ── Fallback: group by broad position band ────────────────────────────────
    # Used when formation string is missing or player count is wrong.
    _YBAND = {"GK": 6.0, "DEF": 22.0, "DM": 36.0, "MID": 50.0, "AM": 64.0, "FWD": 80.0}

    def _yband(pr: PlayerRow) -> str:
        dp = (pr.detailed_position or "").upper()
        return _DETAIL_TO_YKEY.get(dp, "MID")

    groups: dict[str, list[int]] = defaultdict(list)
    for i, pr in enumerate(s11):
        groups[_yband(pr)].append(i)

    coords_fb: list[tuple[float, float]] = [(50.0, 50.0)] * n
    for band, indices in groups.items():
        y = _YBAND[band]
        # Sort within band by LR order
        indices_sorted = sorted(indices, key=lambda i: (_POS_LR.get(
            (s11[i].detailed_position or "").upper(), 2), s11[i].formation_slot))
        xs = _row_xs(len(indices_sorted))
        for rank, idx in enumerate(indices_sorted):
            coords_fb[idx] = (xs[rank], y)

    return coords_fb


def _pitch_figure(lineup: TeamLineup, color: str) -> go.Figure:
    """Render a clean vertical pitch with the 11 starters. Jersey numbers only — no name labels."""
    fig = go.Figure()

    pitch_line = dict(color="rgba(160,160,160,0.5)", width=1.2)
    box_line   = dict(color="rgba(160,160,160,0.45)", width=1.0)

    # Pitch outline
    fig.add_shape(type="rect", x0=0, y0=0, x1=100, y1=100,
                  line=pitch_line, fillcolor="rgba(0,0,0,0)", layer="below")
    # Halfway line
    fig.add_shape(type="line", x0=0, y0=50, x1=100, y1=50,
                  line=pitch_line, layer="below")
    # Centre circle
    fig.add_shape(type="circle", x0=40, y0=40, x1=60, y1=60,
                  line=pitch_line, layer="below")
    # Centre spot
    fig.add_shape(type="circle", x0=49.2, y0=49.2, x1=50.8, y1=50.8,
                  fillcolor="rgba(160,160,160,0.5)",
                  line=dict(color="rgba(0,0,0,0)", width=0), layer="below")
    # Penalty boxes
    fig.add_shape(type="rect", x0=22, y0=0, x1=78, y1=17,
                  line=box_line, layer="below")
    fig.add_shape(type="rect", x0=22, y0=83, x1=78, y1=100,
                  line=box_line, layer="below")
    # 6-yard boxes
    fig.add_shape(type="rect", x0=36, y0=0, x1=64, y1=6,
                  line=box_line, layer="below")
    fig.add_shape(type="rect", x0=36, y0=94, x1=64, y1=100,
                  line=box_line, layer="below")
    # Penalty spots
    for py in [12, 88]:
        fig.add_shape(type="circle", x0=49.2, y0=py - 0.8, x1=50.8, y1=py + 0.8,
                      fillcolor="rgba(160,160,160,0.5)",
                      line=dict(color="rgba(0,0,0,0)", width=0), layer="below")
    # Corner arcs
    for cx, cy in [(0, 0), (100, 0), (0, 100), (100, 100)]:
        fig.add_shape(type="circle", x0=cx - 3, y0=cy - 3, x1=cx + 3, y1=cy + 3,
                      line=box_line, fillcolor="rgba(0,0,0,0)", layer="below")

    coords = _formation_positions(lineup.formation_code, lineup.starters)

    xs, ys, texts, hovers = [], [], [], []
    marker_colors = []
    for pr, (x, y) in zip(lineup.starters, coords):
        xs.append(x)
        ys.append(y)
        texts.append(str(pr.shirt) if pr.shirt is not None else "·")
        cap = " (C)" if pr.is_captain else ""
        hovers.append(
            f"<b>{pr.name}</b>{cap}<br>"
            f"#{pr.shirt or '—'} · {pr.detailed_position or pr.position_group}"
        )
        marker_colors.append("#f59e0b" if pr.position_group == "GK" else color)

    # Jersey numbers only — no separate name label trace
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers+text",
        marker=dict(size=28, color=marker_colors, line=dict(color="white", width=2)),
        text=texts,
        textfont=dict(color="white", size=11, family="Inter, sans-serif"),
        textposition="middle center",
        hovertext=hovers, hoverinfo="text",
        showlegend=False,
    ))

    fig.update_layout(
        xaxis=dict(visible=False, range=[-5, 105], fixedrange=True),
        yaxis=dict(visible=False, range=[-8, 108], scaleanchor="x", scaleratio=1.5, fixedrange=True),
        margin=dict(l=8, r=8, t=8, b=8),
        height=420,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(34, 139, 70, 0.06)",
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# LAYOUT BUILDERS
# ═══════════════════════════════════════════════════════════════════════════════

def _scoreboard(meta: MatchMeta) -> html.Div:
    score_text = (
        f"{meta.home_score} – {meta.away_score}"
        if meta.home_score is not None and meta.away_score is not None
        else "vs"
    )
    date_str = ""
    if meta.date:
        try:
            date_str = pd.to_datetime(meta.date).strftime("%d/%m/%Y")
        except Exception:
            date_str = meta.date

    meta_line  = " · ".join(x for x in [f"Matchday {meta.week}" if meta.week else None, meta.competition] if x)
    venue_line = " · ".join(x for x in [meta.venue, date_str, meta.time] if x)

    return html.Div([
        html.Div(meta_line, className="mr-eyebrow"),
        html.Div([
            html.Div([
                html.Img(src=logo_url(meta.home_team), className="mr-score-logo", alt=meta.home_team),
                html.Div(meta.home_team, className="mr-score-team"),
            ], className="mr-score-team-block"),
            html.Div(score_text, className="mr-score-value"),
            html.Div([
                html.Img(src=logo_url(meta.away_team), className="mr-score-logo", alt=meta.away_team),
                html.Div(meta.away_team, className="mr-score-team"),
            ], className="mr-score-team-block"),
        ], className="mr-score-row"),
        html.Div(venue_line, className="mr-venue-line") if venue_line else None,
    ], className="mr-scoreboard")


def _meta_strip(meta: MatchMeta) -> html.Div:
    items = []
    if meta.week is not None:
        items.append(("bi-trophy", "Matchday", str(meta.week)))
    if meta.date:
        try:
            d = pd.to_datetime(meta.date).strftime("%d %b %Y")
        except Exception:
            d = meta.date
        items.append(("bi-calendar-event", "Date", d))
    if meta.time:
        items.append(("bi-clock", "Kick-off", meta.time))
    if meta.venue:
        items.append(("bi-geo-alt", "Stadium", meta.venue))

    return html.Div([
        html.Div([
            html.I(className=f"bi {icon} mr-meta-icon"),
            html.Div([
                html.Div(label, className="mr-meta-label"),
                html.Div(value, className="mr-meta-value"),
            ], className="mr-meta-text"),
        ], className="mr-meta-item")
        for icon, label, value in items
    ], className="mr-meta-strip")


def _event_badges(pr: PlayerRow) -> list:
    """Inline event/sub badges for the web player-row component."""
    badges = []
    ev = pr.events
    for _ in range(ev.goals):
        badges.append(html.Span("⚽", className="mr-event-badge mr-event-goal", title="Goal"))
    for _ in range(ev.own_goals):
        badges.append(html.Span("⚽", className="mr-event-badge mr-event-og", title="Own goal"))
    for _ in range(ev.assists):
        badges.append(html.Span("👟", className="mr-event-badge mr-event-assist", title="Assist"))
    for _ in range(ev.yellow_cards):
        badges.append(html.Span("🟨", className="mr-event-badge mr-event-yellow", title="Yellow card"))
    for _ in range(ev.red_cards):
        badges.append(html.Span("🟥", className="mr-event-badge mr-event-red", title="Red card"))
    if pr.subbed_off:
        min_str = f" {pr.subbed_off.minute}'" if pr.subbed_off.minute else ""
        tip = f"Subbed off{min_str}" + (f" → {pr.subbed_off.partner_name}" if pr.subbed_off.partner_name else "")
        badges.append(html.Span(f"▼{min_str}", className="mr-event-badge mr-event-suboff", title=tip))
    if pr.subbed_on:
        min_str = f" {pr.subbed_on.minute}'" if pr.subbed_on.minute else ""
        tip = f"Subbed on{min_str}" + (f" ← {pr.subbed_on.partner_name}" if pr.subbed_on.partner_name else "")
        badges.append(html.Span(f"▲{min_str}", className="mr-event-badge mr-event-subon", title=tip))
    return badges


def _player_row(pr: PlayerRow) -> html.Div:
    shirt = str(pr.shirt) if pr.shirt is not None else "·"
    badge_cls = "mr-shirt" + (" mr-shirt-gk" if pr.position_group == "GK" else "")
    return html.Div([
        html.Span(shirt, className=badge_cls),
        html.Span(pr.name or "—", className="mr-player-name"),
        html.Span(pr.detailed_position or pr.position_group, className="mr-player-pos"),
        html.Span("C", className="mr-captain-badge") if pr.is_captain else None,
        *_event_badges(pr),
    ], className="mr-player-row")


def _lineup_panel(lineup: TeamLineup, color: str, align_right: bool = False) -> html.Div:
    cls = "mr-lineup-panel" + (" mr-lineup-right" if align_right else "")
    return html.Div([
        html.Div([
            html.Img(src=logo_url(lineup.team_name), className="mr-lineup-logo", alt=lineup.team_name),
            html.Div([
                html.Div(lineup.team_name, className="mr-lineup-team"),
                html.Div(lineup.formation_code, className="mr-formation-pill",
                         style={"backgroundColor": color}),
            ], className="mr-lineup-head-text"),
        ], className="mr-lineup-head"),

        dcc.Graph(
            figure=_pitch_figure(lineup, color),
            config={"displayModeBar": False, "staticPlot": False},
            className="mr-pitch",
        ),

        html.Div([
            html.Div("Starting XI", className="mr-list-title"),
            html.Div([_player_row(pr) for pr in lineup.starters], className="mr-player-list"),
        ], className="mr-list-block"),

        html.Div([
            html.Div("Bench", className="mr-list-title"),
            html.Div(
                [_player_row(pr) for pr in lineup.bench] or [html.Div("—", className="mr-empty")],
                className="mr-player-list mr-bench-list",
            ),
        ], className="mr-list-block"),
    ], className=cls)


def match_report_page1(match_csv: Path, season: str) -> html.Div:
    """Top-level builder for Page 1 of the Match Report (overview)."""
    meta, home_lu, away_lu = extract_match_report(match_csv, season)
    home_color = "#8a1f33"
    away_color = "#1b2838"

    return html.Div([
        html.Div([
            html.Div("Match Report", className="mr-page-eyebrow"),
            html.Div("Page 1 · Overview", className="mr-page-sub"),
        ], className="mr-page-header"),
        _scoreboard(meta),
        _meta_strip(meta),
        html.Div([
            _lineup_panel(home_lu, home_color),
            _lineup_panel(away_lu, away_color, align_right=True),
        ], className="mr-lineups-grid"),
        html.Div("Data: Opta · Generated by FMP Serie A Dashboard", className="mr-footnote"),
    ], className="mr-report")
