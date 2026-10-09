"""
Smoke tests for the /glossary page: the layout builds from the registry,
every entry is rendered exactly once per section it belongs to, layer-1
details (callouts, badges, variants, optional chips) are present, and every
glossary callback uses prevent_initial_call.
"""

from collections import Counter

import dash
import pytest
from dash.development.base_component import Component

from src.components import glossary_cards as gc
from src.glossary.registry import METRICS
from src.pages import glossary as page


def _walk(node):
    """Yield every component in a layout tree."""
    if isinstance(node, Component):
        yield node
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            for c in children:
                yield from _walk(c)
        else:
            yield from _walk(children)
        title = getattr(node, "title", None)
        if isinstance(title, Component):
            yield from _walk(title)
    elif isinstance(node, (list, tuple)):
        for c in node:
            yield from _walk(c)


@pytest.fixture(scope="module")
def tree():
    return list(_walk(page.layout()))


def _cards(tree):
    return [c for c in tree if "gl-card" == getattr(c, "className", None)]


def _text(node) -> str:
    return " ".join(
        str(c) for c in _walk_text(node)
    )


def _walk_text(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, Component):
        yield from _walk_text(getattr(node, "children", None))
    elif isinstance(node, (list, tuple)):
        for c in node:
            yield from _walk_text(c)


def test_every_entry_rendered_once_per_section(tree):
    rendered = Counter()
    for acc in (c for c in tree if isinstance(getattr(c, "id", None), dict)
                and c.id.get("type") == "gl-more"):
        section, metric_id = acc.id["index"].split("|", 1)
        rendered[(section, metric_id)] += 1
    expected = Counter((s, m["id"]) for m in METRICS for s in m["sections"])
    assert rendered == expected
    assert len(_cards(tree)) == sum(len(m["sections"]) for m in METRICS)


def test_card_counts_per_section_match_registry():
    groups = gc.grouped_registry()
    for section in gc.SECTION_ORDER:
        n = sum(len(v) for v in groups[section].values())
        assert n == sum(1 for m in METRICS if section in m["sections"])


def test_module_and_section_anchors_are_unique(tree):
    anchors = [c.id for c in tree if isinstance(getattr(c, "id", None), str)
               and c.id.startswith("gl-anchor-")]
    assert len(anchors) == len(set(anchors))
    for slug in ("team-overview", "match-analysis", "opponent-analysis"):
        assert f"gl-anchor-{slug}" in anchors


def test_ppda_callouts_at_layer_one():
    by_id = {m["id"]: m for m in METRICS}
    for metric_id, text in gc.DO_NOT_CONFUSE.items():
        entry = by_id[metric_id]
        for section in entry["sections"]:
            card = gc.build_card(entry, section)
            callouts = [c for c in _walk(card) if getattr(c, "className", None) == "gl-callout"]
            assert len(callouts) == 1
            assert text in _text(callouts[0])
    assert set(gc.DO_NOT_CONFUSE) == {"ppda_team_overview", "ppda_defensive_actions", "ppda_final_third"}


def test_status_badges_and_pending_fix_support():
    for m in METRICS:
        for section in m["sections"]:
            assert "under review" not in _text(gc.build_card(m, section)), m["id"]
    pending = next(m for m in METRICS if m["status"] == "pending_fix")
    assert "definition may change" in _text(gc.build_card(pending, pending["sections"][0]))
    ok = next(m for m in METRICS if m["status"] == "ok")
    assert "definition may change" not in _text(gc.build_card(ok, ok["sections"][0]))
    review = dict(ok, status="needs_review")          # renderer readiness only
    assert "under review" in _text(gc.build_card(review, ok["sections"][0]))


def test_variants_render_labelled_by_section():
    starts = next(m for m in METRICS if m["id"] == "starts")
    card = gc.build_card(starts, "team_overview")
    variants = [c for c in _walk(card) if getattr(c, "className", None) == "gl-variant"]
    assert len(variants) == len(starts["variants"])
    for v, comp in zip(starts["variants"], variants):
        assert gc.SECTION_LABELS[v["section"]] in _text(comp)
        assert v["definition"] in _text(comp)


def test_optional_fields_leave_no_empty_chips():
    no_formula = next(m for m in METRICS if m["formula"] is None)
    card = gc.build_card(no_formula, no_formula["sections"][0])
    assert not [c for c in _walk(card) if "gl-chip-formula" in str(getattr(c, "className", ""))]
    def labels(entry):
        return [_text(c) for c in _walk(gc.build_detail(entry))
                if getattr(c, "className", None) == "gl-detail-label"]

    no_source = next(m for m in METRICS if m["source_doc"] is None)
    assert "Source" not in labels(no_source)
    with_source = next(m for m in METRICS if m["source_doc"] is not None)
    assert "Source" in labels(with_source)
    assert with_source["source_doc"] in _text(gc.build_detail(with_source))
    no_agg = next(m for m in METRICS if m["season_aggregation"] is None)
    assert "Season aggregation" not in labels(no_agg)
    no_notes = next(m for m in METRICS if m["notes"] is None)
    assert "Notes" not in labels(no_notes)


def test_markdown_safe_escapes_identifiers_outside_code_only():
    src = "ppda.compute_ppda() reads ppda_{season} and `pressing_summary`."
    out = gc.markdown_safe(src)
    assert "compute\\_ppda" in out and "ppda\\_{season}" in out
    assert "`pressing_summary`" in out          # code spans untouched
    assert "**bold**" in gc.markdown_safe("**bold**")


def test_search_index_covers_name_and_definition(tree):
    for card in _cards(tree)[:20]:
        attr = getattr(card, "data-search")
        metric = next(m for m in METRICS if m["id"] == getattr(card, "data-metric"))
        assert metric["name"].lower() in attr
        assert metric["short_definition"].lower() in attr


def test_glossary_callbacks_prevent_initial_call():
    from dash import _callback

    def _outputs(cb):
        return str(cb.get("output", ""))

    glossary_cbs = [cb for cb in _callback.GLOBAL_CALLBACK_LIST if "gl-" in _outputs(cb)]
    assert len(glossary_cbs) == 2, [_outputs(cb) for cb in glossary_cbs]
    assert all(cb.get("prevent_initial_call") is True for cb in glossary_cbs)


def test_router_serves_glossary():
    from src.callbacks import navigation
    app = dash.Dash(__name__, suppress_callback_exceptions=True)
    navigation.register_navigation_callbacks(app)
    key = next(k for k in app.callback_map if k.startswith("page-content"))
    func = app.callback_map[key]["callback"].__wrapped__
    out = func("/glossary", "")
    assert "glossary-page" in out.className
