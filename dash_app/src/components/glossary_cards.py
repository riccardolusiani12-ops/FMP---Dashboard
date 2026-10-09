"""
Metric Glossary — layout builders for the /glossary page.

Renders the Metric Registry (src/glossary) read through its lru_cache'd
loader; no text here duplicates registry content. A metric that sits in
several sections is rendered once per section, always from the same entry.

Component ID prefix: ``gl-``. Card-level IDs are pattern-matching dicts whose
``index`` is ``"<section>|<metric id>"`` (unique per rendered card).

Styling: assets/glossary.css, scoped under ``.glossary-page`` and built on the
theme CSS variables, so every element follows the dark/light toggle.
"""

from __future__ import annotations

import re
from functools import lru_cache

import dash_bootstrap_components as dbc
from dash import dcc, html

from src.glossary.loader import get_registry

# ── Section metadata ─────────────────────────────────────────────────────────

SECTION_ORDER = ("team_overview", "match_analysis", "opponent_analysis")
SECTION_LABELS = {
    "team_overview": "Team Overview",
    "match_analysis": "Match Analysis",
    "opponent_analysis": "Opponent Analysis",
}
SECTION_ICONS = {
    "team_overview": "bi-trophy-fill",
    "match_analysis": "bi-bar-chart-line-fill",
    "opponent_analysis": "bi-journal-text",
}

# ── Renderer-side constants (not registry content) ───────────────────────────

# "Do not confuse" callouts shown at layer 1. Keyed by registry id; add an
# entry here to give any other metric a visible layer-1 warning.
DO_NOT_CONFUSE: dict[str, str] = {
    "ppda_team_overview": (
        "Not comparable with the Match/Opponent Analysis PPDA: this version "
        "uses ball recoveries on the denominator side."
    ),
    "ppda_defensive_actions": (
        "Not comparable with the Team Overview PPDA: this version counts "
        "tackles + interceptions + fouls + challenges."
    ),
    "ppda_final_third": (
        "High-zone variant shown in Match Analysis. Not comparable with the "
        "Team Overview PPDA (ball-recovery based) nor with the full-pitch "
        "defensive-actions PPDA."
    ),
}

# Status badges. "ok" shows nothing; "pending_fix" is supported ahead of use.
STATUS_BADGES: dict[str, tuple[str, str, str]] = {
    "needs_review": (
        "under review", "gl-badge--review",
        "This definition is still being checked against the code and docs.",
    ),
    "pending_fix": (
        "definition may change", "gl-badge--pending",
        "A known issue affects this metric; its definition may change.",
    ),
}

READING_LABELS = {
    "higher_better": ("bi-arrow-up", "Higher is better"),
    "lower_better": ("bi-arrow-down", "Lower is better"),
    "contextual": ("bi-arrow-left-right", "Contextual"),
}

SEASON_AGGREGATION_LABELS = {
    "sum": "Season total (sum of match values)",
    "total_per_match": "Season total ÷ matches played",
    "ratio_of_sums": "Ratio of season sums (Σ numerator ÷ Σ denominator)",
    "mean_of_match_values": "Mean of per-match values",
    "median_of_match_values": "Median of per-match values",
    "season_events": "Computed once over the pooled season events",
    "rank_percentile": "Within-season rank / percentile",
    "shrinkage_adjusted": "Per-90 with empirical-Bayes shrinkage toward the role mean",
    "external": "External source value",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def section_slug(section: str) -> str:
    return slugify(SECTION_LABELS[section])


def module_slug(section: str, module: str) -> str:
    return f"{section_slug(section)}--{slugify(module)}"


def card_key(section: str, metric_id: str) -> str:
    return f"{section}|{metric_id}"


def markdown_safe(text: str) -> str:
    """Escape identifier underscores (e.g. compute_ppda, ppda_{season}) outside
    backtick code spans, so dcc.Markdown does not render them as italics.
    Display-only transform; the registry text is unchanged."""
    parts = text.split("`")
    for i in range(0, len(parts), 2):          # even parts are outside code spans
        parts[i] = re.sub(r"(?<=\w)_", r"\\_", parts[i])
    return "`".join(parts)


def grouped_registry() -> dict[str, dict[str, list[dict]]]:
    """{section: {module: [entries]}} in registry order (module order = first appearance)."""
    groups: dict[str, dict[str, list[dict]]] = {s: {} for s in SECTION_ORDER}
    for entry in get_registry():
        for section in entry["sections"]:
            groups[section].setdefault(entry["module"][section], []).append(entry)
    return groups


def _chip(children, class_name: str, title: str | None = None) -> html.Span:
    return html.Span(children, className=f"gl-chip-meta {class_name}", title=title)


# ── Layer 1 / layer 2 ────────────────────────────────────────────────────────

def _section_badges(entry: dict, current: str) -> list:
    return [
        html.Span(
            SECTION_LABELS[s],
            className="gl-badge gl-badge--section"
            + (" gl-badge--current" if s == current else ""),
        )
        for s in SECTION_ORDER if s in entry["sections"]
    ]


def _status_badge(entry: dict):
    meta = STATUS_BADGES.get(entry["status"])
    if meta is None:
        return None
    label, cls, title = meta
    return html.Span(label, className=f"gl-badge {cls}", title=title)


def _variants(entry: dict, current: str):
    if not entry["variants"]:
        return None
    return html.Div(
        [
            html.Div(
                [
                    html.Span(SECTION_LABELS[v["section"]],
                              className="gl-badge gl-badge--section"
                              + (" gl-badge--current" if v["section"] == current else "")),
                    html.Span(v["definition"], className="gl-variant-text"),
                ],
                className="gl-variant",
            )
            for v in entry["variants"]
        ],
        className="gl-variants",
    )


def _meta_row(entry: dict) -> html.Div:
    icon, label = READING_LABELS[entry["reading"]]
    chips = []
    if entry["formula"]:
        chips.append(_chip([html.I(className="bi bi-calculator"), html.Code(entry["formula"])],
                           "gl-chip-formula", "Formula"))
    chips.append(_chip([html.I(className="bi bi-rulers"), entry["unit"]], "gl-chip-unit", "Unit"))
    chips.append(_chip([html.I(className=f"bi {icon}"), label],
                       f"gl-chip-reading gl-reading--{entry['reading']}", entry["reading_note"]))
    return html.Div(chips, className="gl-meta")


def build_detail(entry: dict) -> list:
    """Layer 2 content (rendered lazily when the card is first expanded)."""
    parts: list = [dcc.Markdown(markdown_safe(entry["methodology"]), className="gl-markdown")]
    if entry["notes"]:
        parts.append(html.Div(
            [html.Span("Notes", className="gl-detail-label"),
             dcc.Markdown(markdown_safe(entry["notes"]), className="gl-markdown")],
            className="gl-detail-row",
        ))
    if entry["season_aggregation"] is not None:
        key = entry["season_aggregation"]
        parts.append(html.Div(
            [html.Span("Season aggregation", className="gl-detail-label"),
             html.Span(SEASON_AGGREGATION_LABELS.get(key, key)),
             html.Code(key, className="gl-detail-key")],
            className="gl-detail-row",
        ))
    if entry["source_doc"] is not None:
        parts.append(html.Div(
            [html.Span("Source", className="gl-detail-label"),
             html.Code(entry["source_doc"])],
            className="gl-detail-row",
        ))
    return parts


def build_card(entry: dict, section: str) -> html.Div:
    key = card_key(section, entry["id"])
    badges = _section_badges(entry, section)
    status = _status_badge(entry)
    if status is not None:
        badges.append(status)

    children = [
        html.Div(
            [html.H6(entry["name"], className="gl-card-name"),
             html.Div(badges, className="gl-badges")],
            className="gl-card-head",
        ),
    ]
    if entry["id"] in DO_NOT_CONFUSE:
        children.append(html.Div(
            [html.I(className="bi bi-exclamation-triangle-fill"),
             html.Span([html.Strong("Do not confuse: "), DO_NOT_CONFUSE[entry["id"]]])],
            className="gl-callout",
        ))
    children.append(html.P(entry["short_definition"], className="gl-def"))
    variants = _variants(entry, section)
    if variants is not None:
        children.append(variants)
    children += [
        _meta_row(entry),
        html.P(entry["reading_note"], className="gl-reading-note"),
        html.Button(
            [html.I(className="bi bi-chevron-down"), html.Span("Full methodology")],
            id={"type": "gl-more", "index": key},
            className="gl-more-btn",
            n_clicks=0,
        ),
        dbc.Collapse(
            html.Div(id={"type": "gl-detail", "index": key}, className="gl-detail"),
            id={"type": "gl-collapse", "index": key},
            is_open=False,
        ),
    ]
    return html.Div(
        children,
        className="gl-card",
        **{"data-search": f"{entry['name']} {entry['short_definition']}".lower(),
           "data-metric": entry["id"]},
    )


# ── Module / section / index ─────────────────────────────────────────────────

def build_module(section: str, module: str, entries: list[dict]) -> html.Div:
    slug = module_slug(section, module)
    title = html.Span(
        [html.Span(module, className="gl-mod-title"),
         html.Span(str(len(entries)), className="gl-mod-count")],
        className="gl-mod-head",
    )
    return html.Div(
        dbc.Accordion(
            dbc.AccordionItem(
                [build_card(e, section) for e in entries],
                title=title,
                item_id="item",
            ),
            id={"type": "gl-acc", "index": slug},
            start_collapsed=True,
            active_item=None,
        ),
        id=f"gl-anchor-{slug}",
        className="gl-module",
        **{"data-module": slug, "data-section": section},
    )


def build_section(section: str, modules: dict[str, list[dict]]) -> html.Section:
    n_cards = sum(len(v) for v in modules.values())
    return html.Section(
        [
            html.Div(
                [html.I(className=f"bi {SECTION_ICONS[section]}"),
                 html.H3(SECTION_LABELS[section], className="gl-sec-title"),
                 html.Span(str(n_cards), className="gl-sec-count")],
                className="gl-sec-head",
            ),
            *[build_module(section, m, entries) for m, entries in modules.items()],
        ],
        id=f"gl-anchor-{section_slug(section)}",
        className="gl-section chart-section",
        **{"data-section": section},
    )


def build_index(groups: dict[str, dict[str, list[dict]]]) -> tuple[html.Nav, dbc.DropdownMenu]:
    """Sticky sidebar index (wide screens) and a dropdown (narrow screens)."""
    desk, mobile = [], []
    for section in SECTION_ORDER:
        sslug = section_slug(section)
        desk.append(html.Button(SECTION_LABELS[section],
                                id={"type": "gl-nav", "index": f"d|{sslug}"},
                                className="gl-index-sec", n_clicks=0))
        mobile.append(dbc.DropdownMenuItem(SECTION_LABELS[section],
                                           id={"type": "gl-nav", "index": f"m|{sslug}"},
                                           class_name="gl-index-sec", n_clicks=0))
        for module in groups[section]:
            mslug = module_slug(section, module)
            desk.append(html.Button(module, id={"type": "gl-nav", "index": f"d|{mslug}"},
                                    className="gl-index-mod", n_clicks=0))
            mobile.append(dbc.DropdownMenuItem(module, id={"type": "gl-nav", "index": f"m|{mslug}"},
                                               class_name="gl-index-mod", n_clicks=0))
    nav = html.Nav([html.Div("Contents", className="gl-index-title"), *desk], className="gl-index")
    drop = dbc.DropdownMenu(mobile, label="Jump to section", class_name="gl-index-mobile",
                            toggle_class_name="gl-jump-btn")
    return nav, drop


@lru_cache(maxsize=1)
def build_glossary_body() -> tuple:
    """Search bar, chips, index and the three section blocks (built once)."""
    groups = grouped_registry()
    nav, drop = build_index(groups)
    chips = [html.Button("All", id={"type": "gl-chip", "index": "all"},
                         className="gl-chip gl-chip--active", n_clicks=0)]
    chips += [html.Button(SECTION_LABELS[s], id={"type": "gl-chip", "index": s},
                          className="gl-chip", n_clicks=0) for s in SECTION_ORDER]
    toolbar = html.Div(
        [
            html.Div(
                [html.I(className="bi bi-search"),
                 dcc.Input(id="gl-search", type="search", value="", debounce=False,
                           placeholder="Search metrics by name or definition…",
                           autoComplete="off", className="gl-search-input")],
                className="gl-search",
            ),
            html.Div(chips, className="gl-chips"),
            drop,
        ],
        className="gl-toolbar",
    )
    content = html.Div(
        [
            html.Div(
                [html.I(className="bi bi-search"),
                 html.Span("No metric matches your search.")],
                id="gl-no-results", className="gl-no-results", style={"display": "none"},
            ),
            *[build_section(s, groups[s]) for s in SECTION_ORDER],
        ],
        className="gl-content",
    )
    return toolbar, html.Div([nav, content], className="gl-layout")
