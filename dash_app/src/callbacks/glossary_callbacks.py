"""
Glossary page callbacks (/glossary).

Registered with the global ``dash.callback`` / ``dash.clientside_callback`` at
import time (src.pages.glossary imports this module, and the router imports
the page at startup), so app.py needs no change. All use prevent_initial_call.

1. Clientside controller — search, section chips, index navigation and URL-hash
   anchors. Filtering toggles a CSS class on the already-rendered cards, so no
   card is re-rendered per keystroke; only accordion open states, chip classes,
   the no-results banner and the filter state go through Dash.
2. Layer-2 toggle (pattern-matching MATCH) — opens/closes a card's "Full
   methodology" panel and renders its content on first open.
"""

from __future__ import annotations

from dash import ALL, MATCH, Input, Output, State, callback, clientside_callback, ctx, html, no_update

from src.components.glossary_cards import build_detail
from src.glossary.loader import get_metric

clientside_callback(
    """
    function(query, chipClicks, navClicks, boot, hashData, activeItems, state) {
        const dc = window.dash_clientside;
        const cbx = dc.callback_context;
        const accIds = cbx.outputs_list[0].map(function(o) { return o.id.index; });
        const chipIds = cbx.outputs_list[1].map(function(o) { return o.id.index; });
        state = Object.assign({section: "all"}, state || {});
        let q = (query || "").trim().toLowerCase();
        let searchOut = dc.no_update;
        let target = null;

        const trig = (cbx.triggered && cbx.triggered.length) ? cbx.triggered[0].prop_id : "";
        if (trig.charAt(0) === "{") {
            const idObj = JSON.parse(trig.slice(0, trig.lastIndexOf(".")));
            if (idObj.type === "gl-chip") { state.section = idObj.index; }
            if (idObj.type === "gl-nav") { target = idObj.index.split("|")[1]; }
        } else if (trig.indexOf("gl-boot") === 0 || trig.indexOf("gl-hash") === 0) {
            target = decodeURIComponent((window.location.hash || "").replace(/^#/, "")) || null;
        }
        // In-page hash changes (edited URL, later contextual links) re-run this
        // callback through the gl-hash store; the listener is installed once.
        if (!window.__glHashListener) {
            window.__glHashListener = true;
            window.addEventListener("hashchange", function() {
                // dcc.Store has no DOM node: guard on the page container.
                if (document.querySelector(".glossary-page")) {
                    dc.set_props("gl-hash", {data: window.location.hash});
                }
            });
        }
        if (target) {
            state.section = "all";
            if (q) { q = ""; searchOut = ""; }
        }

        // Filter the rendered cards in place (no re-render).
        const root = document.querySelector(".glossary-page");
        const modVisible = {};
        let total = 0;
        if (root) {
            root.querySelectorAll(".gl-section").forEach(function(sec) {
                const secOn = state.section === "all" || state.section === sec.dataset.section;
                let secCount = 0;
                sec.querySelectorAll(".gl-module").forEach(function(mod) {
                    let n = 0;
                    mod.querySelectorAll(".gl-card").forEach(function(card) {
                        const hit = !q || card.dataset.search.indexOf(q) !== -1;
                        card.classList.toggle("gl-hidden", !hit);
                        if (hit) { n += 1; }
                    });
                    const cnt = mod.querySelector(".gl-mod-count");
                    if (cnt) { cnt.textContent = n; }
                    mod.classList.toggle("gl-hidden", n === 0 || !secOn);
                    modVisible[mod.dataset.module] = secOn ? n : 0;
                    if (secOn) { secCount += n; }
                });
                const sc = sec.querySelector(".gl-sec-count");
                if (sc) { sc.textContent = secCount; }
                sec.classList.toggle("gl-hidden", secCount === 0);
                total += secCount;
            });
            root.querySelectorAll(".gl-index-mod, .gl-index-sec").forEach(function(btn) {
                const slug = btn.id ? JSON.parse(btn.id).index.split("|")[1] : "";
                const visible = slug.indexOf("--") === -1
                    ? Object.keys(modVisible).some(function(k) { return k.indexOf(slug + "--") === 0 && modVisible[k] > 0; })
                    : (modVisible[slug] || 0) > 0;
                btn.classList.toggle("gl-index-dim", !visible);
            });
        }

        // Accordion open states.
        let open = (activeItems || []).map(function(a) { return !!a; });
        if (target) {
            accIds.forEach(function(slug, i) {
                if (slug === target || slug.indexOf(target + "--") === 0) { open[i] = true; }
            });
            setTimeout(function() {
                const el = document.getElementById("gl-anchor-" + target);
                if (el) { el.scrollIntoView({behavior: "smooth", block: "start"}); }
            }, 350);
        } else if (q) {
            open = accIds.map(function(slug) { return (modVisible[slug] || 0) > 0; });
        } else if (trig.indexOf("gl-search") === 0) {
            open = accIds.map(function() { return false; });
        }

        return [
            open.map(function(o) { return o ? "item" : null; }),
            chipIds.map(function(id) { return "gl-chip" + (id === state.section ? " gl-chip--active" : ""); }),
            {display: total === 0 ? "flex" : "none"},
            state,
            searchOut
        ];
    }
    """,
    Output({"type": "gl-acc", "index": ALL}, "active_item"),
    Output({"type": "gl-chip", "index": ALL}, "className"),
    Output("gl-no-results", "style"),
    Output("gl-state", "data"),
    Output("gl-search", "value"),
    Input("gl-search", "value"),
    Input({"type": "gl-chip", "index": ALL}, "n_clicks"),
    Input({"type": "gl-nav", "index": ALL}, "n_clicks"),
    Input("gl-boot", "n_intervals"),
    Input("gl-hash", "data"),
    State({"type": "gl-acc", "index": ALL}, "active_item"),
    State("gl-state", "data"),
    prevent_initial_call=True,
)


@callback(
    Output({"type": "gl-collapse", "index": MATCH}, "is_open"),
    Output({"type": "gl-detail", "index": MATCH}, "children"),
    Output({"type": "gl-more", "index": MATCH}, "children"),
    Input({"type": "gl-more", "index": MATCH}, "n_clicks"),
    State({"type": "gl-collapse", "index": MATCH}, "is_open"),
    State({"type": "gl-detail", "index": MATCH}, "children"),
    prevent_initial_call=True,
)
def toggle_methodology(n_clicks, is_open, detail):
    """Open/close a card's layer 2; build its content on first open."""
    opening = not is_open
    body = no_update
    if opening and not detail:
        metric_id = ctx.triggered_id["index"].split("|", 1)[1]
        entry = get_metric(metric_id)
        body = build_detail(entry) if entry else html.P("Definition not found.")
    label = [
        html.I(className=f"bi bi-chevron-{'up' if opening else 'down'}"),
        html.Span("Hide methodology" if opening else "Full methodology"),
    ]
    return opening, body, label
