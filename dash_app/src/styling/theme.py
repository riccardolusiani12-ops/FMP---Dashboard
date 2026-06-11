"""
dash_app/src/styling/theme.py
==============================
Single source of truth for the Calcio Italiano design system.

All values are derived from the existing palette catalogued in Phase 0:
  - Dark theme: sourced from assets/styles.css :root variables.
  - Light theme: background chosen as #FAF7F0 (warm parchment, not stark white)
    to match the "creamy-white" visual target and to soften the contrast
    between chart backgrounds and card surfaces.  The current light-theme bg
    in styles.css is #f4f6f9 (cool blue-grey); #FAF7F0 is warmer and better
    suits a dark-red primary accent.
  - Font: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    This is already the dashboard's declared font.  It is a system-font stack
    that degrades gracefully without any CDN dependency.  Inter is widely
    available as a system font on modern macOS/Windows; the fallbacks handle
    older systems.

Semantic colours are kept close to existing values; only rationalised for
consistency and colourblind safety where noted inline.
"""

from __future__ import annotations

# ── Font ────────────────────────────────────────────────────────────────────────
# Same stack already declared in body {} inside styles.css.
# Repeated here so Python chart code can reference it without hardcoding strings.
FONT_FAMILY = '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'


# ── Dark Theme ──────────────────────────────────────────────────────────────────
COLORS_DARK: dict[str, str] = {
    # Backgrounds
    "bg":           "#0f1923",              # page background (--bg-dark)
    "surface":      "rgba(27,40,56,0.6)",   # card background (--bg-card)
    "surface_solid": "#1b2838",             # opaque surface for chart backgrounds
    "surface_hover": "rgba(27,40,56,0.85)", # card hover (--bg-card-hover)

    # Borders
    "border":       "rgba(255,255,255,0.06)",    # subtle border (--border-light)
    "border_accent":"rgba(138,31,51,0.2)",       # accent-tinted border (--border-subtle)

    # Text
    "text_primary":  "#f0f0f0",    # --text-primary
    "text_secondary":"#8899aa",    # --text-secondary
    "text_muted":    "#5a6a7a",    # --text-muted

    # Accent
    "accent":        "#8a1f33",    # PRIMARY_COLOR — deep red
    "accent_light":  "#a62842",    # --primary-light
    "accent_dark":   "#6b1828",    # --primary-dark

    # Chart internals
    "gridline":      "rgba(255,255,255,0.07)",
    "zeroline":      "rgba(255,255,255,0.12)",
    "legend_bg":     "rgba(0,0,0,0.30)",
    "legend_border": "rgba(255,255,255,0.12)",
    "hover_bg":      "rgba(15,25,35,0.92)",
    "hover_border":  "rgba(138,31,51,0.5)",
}

# ── Light Theme ─────────────────────────────────────────────────────────────────
# Background: #FAF7F0 — warm parchment (not stark white, not cool blue-grey).
# Rationale: the primary accent is deep red (#8a1f33); a warm off-white base
# creates visual harmony and reduces eye strain compared to #ffffff.
# All chart backgrounds stay transparent (rgba(0,0,0,0)) so they sit cleanly
# inside light-theme cards.
COLORS_LIGHT: dict[str, str] = {
    # Backgrounds
    "bg":           "#FAF7F0",              # warm parchment page background
    "surface":      "rgba(255,255,255,0.92)",
    "surface_solid": "#ffffff",
    "surface_hover": "rgba(255,255,255,1.0)",

    # Borders
    "border":       "rgba(0,0,0,0.08)",
    "border_accent":"rgba(138,31,51,0.25)",

    # Text
    "text_primary":  "#1a1a2e",
    "text_secondary":"#4a5568",
    "text_muted":    "#718096",

    # Accent — same primary red (contrast ratio ≥ 4.5:1 on #FAF7F0, WCAG AA)
    "accent":        "#8a1f33",
    "accent_light":  "#a62842",
    "accent_dark":   "#6b1828",

    # Chart internals
    "gridline":      "rgba(0,0,0,0.07)",
    "zeroline":      "rgba(0,0,0,0.15)",
    "legend_bg":     "rgba(255,255,255,0.85)",
    "legend_border": "rgba(0,0,0,0.12)",
    "hover_bg":      "rgba(250,247,240,0.97)",
    "hover_border":  "rgba(138,31,51,0.4)",
}


# ── Semantic Colours ────────────────────────────────────────────────────────────
# These are chart-internal semantic palettes shared across multiple components.
# Kept close to existing values; adjusted where noted for colourblind safety.
SEMANTIC_COLORS: dict[str, object] = {

    # Team vs. Opponent (bar charts, line charts, distribution splits)
    # Source: opponent_offensive_phase.py (_HIGHLIGHT / _NEUTRAL), config.PRIMARY_COLOR
    "team":     "#8a1f33",   # primary red — the analysed team
    "opponent": "#4a6274",   # muted teal-grey — opponent / other teams

    # Attack origin taxonomy (7 categories from classify_attack_origin())
    # Source: chance_creation_cards.py ORIGIN_COLORS
    "origin_set_piece":       "#22c55e",   # green
    "origin_high_regain":     "#ef4444",   # red — aggressive press recovery
    "origin_cross":           "#06b6d4",   # cyan
    "origin_through_ball":    "#8b5cf6",   # purple
    "origin_cut_back":        "#f97316",   # orange
    "origin_individual_play": "#eab308",   # amber (replaces yellow for better CB safety)
    "origin_combination":     "#3b82f6",   # blue — patient build-up

    # xG / chance tiers (3 levels from chance_creation_cards.py TIER_META)
    "tier_converted":  "#22c55e",   # green — goal scored
    "tier_big_chance": "#f97316",   # orange — Opta Big Chance qualifier
    "tier_speculative":"#6b7280",   # grey — no big-chance qualifier

    # Possession outcome (positive / negative — pitch_zones.py, final_third_pitch.py)
    "outcome_positive": "#22c55e",   # green — possession retained ≥ 15s
    "outcome_negative": "#ef4444",   # red — possession lost quickly

    # Goals scored vs conceded (Phase 1 addition — goal distribution tiles,
    # goals-vs-xG bars). Aliases of the outcome pair so "good/bad" greens and
    # reds are identical across the dashboard (previously #00CC96 / #EF553B).
    "goals_scored":   "#22c55e",
    "goals_conceded": "#ef4444",

    # Pitch zone fills (final third sub-zones — final_third_pitch.py)
    "zone_flank":  "#06b6d4",   # cyan — Z13, Z15, Z16, Z18
    "zone14":      "#8b5cf6",   # purple — Zone 14 central danger
    "zone_box":    None,         # Z17 penalty box — no tint, transparent

    # Final third entry methods (final_third_pitch.py METHOD_COLORS)
    "method_transition_recovery": "#22c55e",
    "method_through_ball":        "#f43f5e",
    "method_switch_of_play":      "#14b8a6",
    "method_set_piece":           "#6366f1",
    "method_long_ball":           "#f97316",
    "method_cross_delivery":      "#ec4899",
    "method_individual_carry":    "#eab308",
    "method_short_pass":          "#3b82f6",

    # Defensive action types (defensive_pressing_cards.py ACTION_COLORS)
    "action_tackle":       "#3b82f6",   # blue
    "action_interception": "#22c55e",   # green
    "action_recovery":     "#8b5cf6",   # purple
    "action_clearance":    "#f59e0b",   # amber
    "action_aerial":       "#06b6d4",   # cyan
    "action_challenge":    "#ec4899",   # pink
    "action_blocked_pass": "#84cc16",   # lime

    # Pressure / PPDA colour coding (defensive_pressing_cards.py _ppda_color())
    "ppda_good":    "#22c55e",   # ≤ 6 — aggressive press
    "ppda_medium":  "#f97316",   # 6–10
    "ppda_poor":    "#ef4444",   # > 10

    # Heatmap colorscale — sequential, used for zone intensity / xT / pressing maps
    # "Reds" is the existing convention in opponent_offensive_phase.py (red gradient);
    # the PV model uses matplotlib "RdYlGn" (offline).  For Plotly interactive heatmaps
    # the canonical scale is a custom navy→red ramp that follows the dashboard palette.
    "heatmap_colorscale": [
        [0.0,  "rgba(15,25,35,0.1)"],
        [0.25, "rgba(59,82,120,0.4)"],
        [0.5,  "rgba(100,30,60,0.55)"],
        [0.75, "rgba(150,30,50,0.75)"],
        [1.0,  "rgba(220,40,40,0.92)"],
    ],

    # Benchmark line colours (standings chart — multi_season_standings.py)
    "ucl_line":       "#0E1E5B",
    "uel_line":       "#F47E01",
    "uecl_line":      "#00CC44",
    "relegation_line":"#FF1A1A",

    # GK keeper shirt colour (match_report — mr-shirt-gk)
    "gk_shirt":  "#f59e0b",
    # GK marker on formation pitches / lineup position badges (Phase 1 addition)
    "gk_marker": "#3cb371",

    # ── Phase 2a additions (Match Analysis defensive/transition cards) ──
    # Pitch corridors (L/C/R) — used by pressing direction, offside trap,
    # transition corridor splits (values unchanged from card-local palettes)
    "corridor_left":   "#3b82f6",
    "corridor_centre": "#8b5cf6",
    "corridor_right":  "#06b6d4",
    # Defensive transition outcome tiers (N1 mild → N3 dangerous)
    "transition_n1": "#f97316",
    "transition_n2": "#ef4444",
    "transition_n3": "#7f1d1d",
    # Offensive transition outcome tiers (P1 mild → P3 dangerous, green family)
    "transition_p1": "#86efac",
    "transition_p2": "#22c55e",
    "transition_p3": "#15803d",
    # Pressing height bands (high press / mid press / low block)
    "press_high": "#ef4444",
    "press_mid":  "#f97316",
    "press_low":  "#6b7280",
    # Additional defensive action type (castle card)
    "action_foul": "#f97316",
    # Offside line overlay on pitch maps (harmonises pressing card's #a855f7
    # KPI purple with the #8b5cf6 line colour already used on the pitches)
    "offside_line": "#8b5cf6",
    # FT entry method present in opponent-mirror data but not in the
    # final-third taxonomy above
    "method_high_regain": "#84cc16",

    # ── Phase 2b addition ──
    # "Other" bucket for progression/method splits (General Build-up card)
    "method_other": "#6b7280",

    # ── Phase 2c additions (set-piece cards; values unchanged from
    #    set_piece_cards.py's local palettes) ──
    # Corner delivery types
    "delivery_inswinger":  "#3b82f6",
    "delivery_outswinger": "#f97316",
    "delivery_straight":   "#8b5cf6",
    "delivery_short":      "#22c55e",
    "delivery_unknown":    "#6b7280",
    # Set-piece outcomes (corners + free kicks)
    "sp_goal":            "#22c55e",
    "sp_shot_on_target":  "#3b82f6",
    "sp_shot_off_target": "#f97316",
    "sp_cleared":         "#6b7280",
    "sp_second_phase":    "#8b5cf6",
    "sp_played_on":       "#06b6d4",
    "sp_hit_post":        "#eab308",
    "sp_blocked":         "#ef4444",
    "sp_foul_won":        "#06b6d4",
    # Free-kick delivery types
    "fk_direct_shot": "#ef4444",
    "fk_crossed":     "#3b82f6",
    "fk_chipped":     "#8b5cf6",
    "fk_long_ball":   "#f97316",
    "fk_short":       "#22c55e",
    "fk_launch":      "#eab308",

    # ── Phase 3 addition ──
    # Non-highlighted teams in league benchmark bar charts (ppda.py NEUTRAL_COLOR
    # / opponent_offensive_phase _NEUTRAL — muted slate, readable on both themes)
    "benchmark_neutral": "#4a6274",
    # Captain badge
    "captain_badge": "#ffd23f",
}


# ── Phase 1 additions (additive) ────────────────────────────────────────────────

# Desaturated line palette for NON-highlighted series in multi-season charts
# (Points Progression). Distinct hues, low saturation, so the accent-coloured
# highlighted season stands out. Readable on both dark and parchment backgrounds.
SEASON_MUTED_PALETTE: list[str] = [
    "#6c8ebf",   # muted blue
    "#6fa8a0",   # muted teal
    "#9183b8",   # muted purple
    "#b08968",   # muted tan
    "#7f9c6c",   # muted olive
    "#a0788a",   # muted mauve
]

# Soft glow behind highlighted data points (semi-transparent accent)
GLOW_ACCENT: str = "rgba(166, 40, 66, 0.25)"   # accent_light @ 25%


# ── Helper ──────────────────────────────────────────────────────────────────────

def get_colors(theme: str = "dark") -> dict[str, str]:
    """Return the palette dict for *theme* ('dark' or 'light')."""
    return COLORS_LIGHT if theme == "light" else COLORS_DARK
