"""
Theme toggle callback — switches between dark and light mode.
"""

from __future__ import annotations

from dash import Input, Output, State, clientside_callback, html


def register_theme_callbacks(app):
    """Register the theme toggle callbacks."""

    # Toggle the stored theme value on button click
    @app.callback(
        Output("theme-store", "data"),
        Input("theme-toggle-btn", "n_clicks"),
        State("theme-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_theme(n_clicks, current_theme):
        return "light" if current_theme == "dark" else "dark"

    # Apply the theme class to the app root div + document.body via clientside
    # Also patch all Plotly charts so axes, fonts and backgrounds adapt
    clientside_callback(
        """
        function(theme) {
            var isLight = theme === "light";

            // Toggle class on body for full-page background
            if (isLight) {
                document.body.classList.add("light-theme");
            } else {
                document.body.classList.remove("light-theme");
            }

            var fontColor   = isLight ? "#1a1a2e"              : "#f0f0f0";
            var gridColor   = isLight ? "rgba(0,0,0,0.07)"     : "rgba(255,255,255,0.07)";
            var lineColor   = isLight ? "rgba(0,0,0,0.15)"     : "rgba(255,255,255,0.12)";
            var legendBg    = isLight ? "rgba(255,255,255,0.85)" : "rgba(0,0,0,0.3)";

            function patchPlots() {
                document.querySelectorAll(".js-plotly-plot").forEach(function(plot) {
                    // Leave static pitch-field charts alone (formations, buildup pitch)
                    if (plot.closest(".formation-pitch") ||
                        plot.closest(".pitch-zone-container") ||
                        plot.closest(".final-third-pitch-container") ||
                        plot.closest(".pitch-dark-container")) return;

                    try {
                        Plotly.relayout(plot, {
                            "paper_bgcolor": "rgba(0,0,0,0)",
                            "plot_bgcolor":  "rgba(0,0,0,0)",
                            "font.color":    fontColor,
                            "title.font.color": fontColor,
                            "xaxis.color":              fontColor,
                            "xaxis.tickfont.color":     fontColor,
                            "xaxis.title.font.color":   fontColor,
                            "xaxis.gridcolor":          gridColor,
                            "xaxis.linecolor":          lineColor,
                            "xaxis.zerolinecolor":      lineColor,
                            "yaxis.color":              fontColor,
                            "yaxis.tickfont.color":     fontColor,
                            "yaxis.title.font.color":   fontColor,
                            "yaxis.gridcolor":          gridColor,
                            "yaxis.linecolor":          lineColor,
                            "yaxis.zerolinecolor":      lineColor,
                            "xaxis2.color":             fontColor,
                            "xaxis2.tickfont.color":    fontColor,
                            "xaxis2.gridcolor":         gridColor,
                            "yaxis2.color":             fontColor,
                            "yaxis2.tickfont.color":    fontColor,
                            "yaxis2.gridcolor":         gridColor,
                            "legend.font.color":        fontColor,
                            "legend.bgcolor":           legendBg,
                            "legend.bordercolor":       lineColor
                        });
                        // Also patch bar/scatter text labels colour
                        var gd = plot;
                        if (gd.data) {
                            var traceUpdates = {};
                            gd.data.forEach(function(trace, i) {
                                if (trace.textfont) {
                                    traceUpdates["data[" + i + "].textfont.color"] = fontColor;
                                }
                            });
                            if (Object.keys(traceUpdates).length) {
                                Plotly.relayout(plot, traceUpdates);
                            }
                        }
                    } catch(e) {}
                });
            }

            // Patch immediately and after loading spinners resolve
            patchPlots();
            setTimeout(patchPlots, 400);
            setTimeout(patchPlots, 1200);

            // Watch DOM for new charts being mounted (dcc.Loading)
            if (window._themeObserver) window._themeObserver.disconnect();
            var observer = new MutationObserver(function(mutations) {
                var hasNew = mutations.some(function(m) {
                    return Array.from(m.addedNodes).some(function(n) {
                        return n.nodeType === 1 && (
                            (n.classList && n.classList.contains("js-plotly-plot")) ||
                            (n.querySelector && n.querySelector(".js-plotly-plot"))
                        );
                    });
                });
                if (hasNew) setTimeout(patchPlots, 150);
            });
            observer.observe(document.body, { childList: true, subtree: true });
            window._themeObserver = observer;

            return isLight ? "app-root light-theme" : "app-root";
        }
        """,
        Output("app-root", "className"),
        Input("theme-store", "data"),
    )

    # Update the toggle button icon
    @app.callback(
        Output("theme-toggle-btn", "children"),
        Input("theme-store", "data"),
    )
    def update_toggle_icon(theme):
        if theme == "light":
            return html.I(className="bi bi-moon-fill", style={"fontSize": "0.95rem"})
        return html.I(className="bi bi-sun-fill", style={"fontSize": "0.95rem"})
