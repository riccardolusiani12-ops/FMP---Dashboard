# Redesign Tracker

Status legend: ⬜ not started · 🟨 in progress · ✅ done

---

## Phase 0 — Design System Scaffolding (this phase)

- ✅ `dash_app/src/styling/theme.py` — colour palette, font, semantic colours
- ✅ `dash_app/src/styling/plotly_template.py` — `apply_chart_theme()`, `kpi_strip_style()`
- ✅ `dash_app/src/styling/pitch_utils.py` — canonical `draw_pitch()` primitive
- ✅ `dash_app/assets/styles.css` — additive: warm-parchment light bg `#FAF7F0`, `.redesign-card`
- ✅ `REDESIGN_TRACKER.md` — this file

---

## Phase 1 — Team Overview (Team Detail page) — ✅ COMPLETE (league table N/A)

> Shared Phase 1 infrastructure: page root got the `team-overview` scope class;
> house-style headers via `_ds_header()` in `pages/team_detail.py`; scoped CSS
> block "PHASE 1 — TEAM OVERVIEW REDESIGN" in `assets/styles.css` (card accent
> top strip, ds-header, KPI cards, season pills — all additive).
> Additive theme.py additions: `SEASON_MUTED_PALETTE`, `GLOW_ACCENT`,
> `SEMANTIC_COLORS["goals_scored"/"goals_conceded"/"gk_marker"]`.
> Additive pitch_utils.py additions: `draw_pitch(style="formation", width=…)`
> + `_draw_formation_markings()`.

> NOTE (Phase 1 file-reading): the live Team Overview tab is
> `dash_app/src/pages/team_detail.py` + `dash_app/src/callbacks/team_detail_callbacks.py`
> (routed via `src/callbacks/navigation.py`). The older `dash_app/src/tabs/team_season.py`
> is not part of this page. File paths below corrected accordingly.

- ✅ Points Progression chart
  - `dash_app/src/analytics/multi_season_standings.py` :: `build_standings_figure()`
  - Done: `apply_chart_theme(fig, theme)` applied last; non-selected seasons use
    new `SEASON_MUTED_PALETTE` (theme.py, additive) at 1.6px/0.75 opacity; selected
    season accent-coloured with a glow under-trace (hover-skipped); benchmark lines
    softened (1.2px dash, 0.55 opacity, compact badges); end-of-line position badge
    via new optional `final_position` param (official Rank from `load_standings`).
    In-chart title removed — the card header now carries it (house style).
  - Season pills added in the card (`season-pills-row` + 2 new callbacks); pills
    set the existing `team-season-selector` dropdown value, so all season-driven
    behaviour is unchanged. Hover tooltips byte-identical to before.
  - (`multi_season_standings_v1.py` is an untracked variant, not imported — skip)
- N/A League table / standings table
  - **Not present in the Team Overview tab.** No standings table is rendered on
    `team_detail.py` (standings data only feeds the KPI cards). The Phase 0 entry
    came from graph communities ("League Summary Precompute"), which is a data
    pipeline, not a UI table. Revisit only if a standings table is added later.
- ✅ KPI strip (Position, Last 5, Goal Diff, PPG, Mean Age + PPDA / Goals-xG rows)
  - `dash_app/src/callbacks/team_detail_callbacks.py` :: `_kpi_card()`, `_form_card()`, `_stat_card()`
  - Done via scoped CSS (`.team-overview .kpi-card` etc. in `assets/styles.css`);
    page root got the `team-overview` scope class. `kpi_strip_style()` values were
    mirrored into CSS (rather than inline styles) so the client-side theme toggle
    keeps working without re-rendering KPI children. No Python value changes.
- ✅ Goal Distribution chart (15-min interval tiles)
  - `dash_app/src/callbacks/team_detail_callbacks.py` :: `_build_goal_distribution_card()`
  - Done: tile/summary/icon colours now sourced from `SEMANTIC_COLORS["goals_scored"/
    "goals_conceded"]` (new additive aliases of the outcome pair; #00CC96→#22c55e,
    #EF553B→#ef4444 — hue harmonisation only). Bins, values, intensity formula and
    hover tooltips unchanged. Card got the house header (eyebrow "TIMING") and
    rounded-tile polish via scoped CSS. No Plotly figure in this component.
- ✅ Formation pitch figure — FIRST `draw_pitch()` ADOPTER
  - `dash_app/src/analytics/formations.py` :: `build_formation_pitch_figure()`
  - Done: inline pitch drawing + layout replaced by
    `pitch_utils.draw_pitch(fig, theme="dark", style="formation", height=300, width=300)`.
    `draw_pitch()` was extended additively with `style="formation"` + `width` params
    and a `_draw_formation_markings()` helper (geometry/colours replicate the old
    private drawing exactly; light-theme equivalents included for future use).
    Verified structurally identical: 12 shapes, 13 traces, seamless `#1b2838`
    square, all 11 dot positions/colours/hover text unchanged. Dot colours now
    bound to `COLORS_DARK["accent"]` / new `SEMANTIC_COLORS["gk_marker"]`.
    Pitch intentionally stays dark in both themes (`.formation-pitch` skipped by
    the theme observer — existing convention).
- ✅ PPDA section (bar ranking + field-tilt logo scatter + PPDA KPI row)
  - `dash_app/src/analytics/ppda.py` :: `build_ppda_bar_figure()`, `build_ppda_scatter_figure()`
  - Done: both builders now end with `apply_chart_theme(fig, "dark")` + chart
    specifics on top; `template="plotly_dark"`/hardcoded backgrounds removed.
    Colour constants bound to `SEMANTIC_COLORS` (team/opponent; quadrant labels
    harmonised #00CC96→#22c55e, #EF553B→#ef4444). Values, sort order, logos,
    quadrant placement and hover text unchanged. Figures still built dark and
    re-patched by the client-side theme observer on light toggle (behaviour
    identical to before). Card header → eyebrow "PRESSING". PPDA KPI row covered
    by the scoped KPI strip restyle.
- ✅ Goals & xG block (stat cards + grouped bar chart) — ADDED in Phase 1 file-reading
  - `dash_app/src/callbacks/team_detail_callbacks.py` :: `update_goals_xg()`, `_build_goals_xg_bar_chart()`
  - Done: `apply_chart_theme(fig, "dark")` + chart specifics; hardcoded `#1b2838`
    backgrounds and `template="plotly_dark"` removed. Page-wide good/bad pair
    harmonised via module constants `_GREEN`/`_RED` (= `SEMANTIC_COLORS`
    goals_scored/goals_conceded) — also applied to PPG/GD/age KPI colours and
    W/L form badges (hue change only: #00CC96→#22c55e, #EF553B→#ef4444).
    GF/GA/xG/xGC values verified unchanged through the real callback.
    Card header → eyebrow "PERFORMANCE".

---

## Phase 2 — Match Analysis — ✅ COMPLETE (2a + 2b + 2c)

> All 11 Match Analysis cards redesigned (Defensive Structure/Pressing/Castle,
> Offensive Transitions, Final Third, Chance Creation/Conceded, Build-up Chain,
> General Build-up, Corner Kicks, Free Kicks). Documented exceptions:
> (1) GK goalmouth figure — geometrically distinct view, themed in place;
> (2) portrait corner/FK maps — zone furniture is the analysis, themed in place;
> (3) Chance Creation/Conceded landscape shot maps — NOT migrated to the new
>     `draw_pitch(detailed_boxes=True)` (their framing/aspect differs: x [49,103],
>     no 0.68 scaleratio); candidates for a later cleanup pass;
> (4) Player Events UI — is the PDF report builder, out of scope (see row below).
> Phase 2c geometry correction: `draw_pitch()` boxes now at Opta/zone-aligned
> 83.33 / 16.67 / 21.1–78.9 (was 83.5/16.5/21/79 — sub-pixel shift, all prior
> phases regression-checked); new additive `detailed_boxes` param (six-yard
> boxes, penalty spots, D-arcs, centre circle, goal mouths).

> Root file: `dash_app/src/components/analysis_cards.py` (phase renderers; the
> page entry is `pages/match_analysis.py` — `pages/player_analysis.py` does not
> exist). Phase 2a (Defensive Structure / Pressing / Castle, Offensive
> Transitions) is ✅ COMPLETE.
> Phase 2a shared infrastructure: new `src/styling/ui_components.py ::
> ds_header()` (shared house header — use this, not team_detail's private copy);
> CSS block "PHASE 2a — MATCH ANALYSIS CARDS" scoped under `.ma-card` (card
> accent strip, ds-header, mini-KPI restyle); additive `SEMANTIC_COLORS` keys
> (`corridor_left/centre/right`, `transition_n1-n3`, `transition_p1-p3`,
> `press_high/mid/low`, `action_foul`, `offside_line`, `method_high_regain`);
> additive `draw_pitch(emphasize_own_box=...)` param.

### Final Third
- ✅ Final Third card (entry scatter + zone heatmap + KPI/bar sections)
  - `dash_app/src/components/final_third_pitch.py`, `final_third_cards.py`
  - Done (Phase 2b): `_draw_pitch_base()`/`_base_layout()` deleted; entry scatter
    adopts `draw_pitch(draw_zones=True, highlight_final_third=True)`; the zone
    heatmap keeps its bespoke zone canvas (the zones ARE the data) with themed
    layout inline (geometry unchanged). METHOD/CORRIDOR/OUTCOME/zone palettes
    bound to `SEMANTIC_COLORS` (values unchanged). 6 bar/possession figures get
    `apply_chart_theme()` before their specific layouts. Shell: `ds_header()`
    ("OFFENSIVE PHASE — FINAL THIRD") + `.ma-card` scope (reused from 2a).
    31 entry positions + hover verified identical on real match data.
    `analytics/final_third.py` untouched.

### Chance Creation
- ✅ Chance Creation card (overview KPIs, origin breakdown, xG bars, origin grid,
  shot map, quality donut, chain-to-goal matrix)
  - `dash_app/src/components/chance_creation_cards.py`
  - Done (Phase 2b): ORIGIN_COLORS bound to `SEMANTIC_COLORS["origin_*"]` (the
    7-category attack-origin taxonomy Phase 0 already encoded; values unchanged).
    TAXONOMY DECISION: origins are NOT unified with `method_*` — they are a
    genuinely different taxonomy (shot origins vs FT entry methods); same-named
    categories (Set Piece, Through Ball, Cross) intentionally keep different
    colours per taxonomy. TIER_META bound to `tier_*`. `apply_chart_theme()` on
    all 5 figures. SHOT MAP DEFERRAL: `_draw_half_pitch()` kept — its detailed
    markings (six-yard box, penalty spot, D-arc, centre arc, goal mouth) use
    geometry that conflicts with `draw_pitch()`'s box coords (83.33 vs 83.5);
    restyled in place, `draw_pitch(half="attacking")` adoption deferred (revisit
    with Phase 2c set-piece half-pitches, which share this need). Shell:
    `ds_header()` ("OFFENSIVE PHASE — CHANCE CREATION") + `.ma-card`.
    11 shot positions verified identical on real match data.

### Defensive Structure
- ✅ Defensive structure card (transition KPIs, outcome bars, loss-origins pitch)
  - `dash_app/src/components/defensive_structure_cards.py`
  - Done (Phase 2a): private `_draw_full_pitch()`/`_pitch_layout()` deleted, replaced
    by `pitch_utils.draw_pitch(draw_zones=True)`; `apply_chart_theme()` on every
    figure (pitch + 6 bar charts); palette bound to `SEMANTIC_COLORS` (values
    unchanged except structural-mirror METHOD_PALETTE, now bound to the shared
    `method_*` taxonomy so methods match the Final Third card's colours).
    Card shell: `ds_header()` (eyebrow "DEFENSIVE PHASE — STRUCTURE") + `ma-card`
    scope class. Marker positions/hover verified identical on real match data.

### Defensive Pressing
- ✅ Pressing card (PPDA KPIs, height/direction/success bars, 2 pitch maps)
  - `dash_app/src/components/defensive_pressing_cards.py`
  - Done (Phase 2a): private `_draw_full_pitch()`/`_pitch_layout()` deleted →
    `draw_pitch(draw_zones=True)`; `apply_chart_theme()` on every figure;
    ACTION_COLORS/corridors/press tiers bound to `SEMANTIC_COLORS` (values
    unchanged); OFFSIDE_COLOR harmonised #a855f7→#8b5cf6 (`offside_line`).
    Zone-density ramp documented as the unified `heatmap_colorscale` (formula
    unchanged). Shell: `ds_header()` ("DEFENSIVE PHASE — PRESSING") + `ma-card`.
    161 marker positions + hover verified identical on real match data.
  - SHARED-FUNCTION FINDING: this card does NOT use `analytics/ppda.py`'s
    `build_ppda_bar_figure()`/`build_ppda_scatter_figure()` (those are Team
    Overview-only, themed in Phase 1). It uses `analytics/defensive_pressing.py`
    (computation only — untouched).

### Defensive Castle
- ✅ Castle card (sub-zone KPIs, type/corridor bars, scatter + zone heatmap)
  - `dash_app/src/components/defensive_castle_cards.py`
  - Done (Phase 2a): private pitch helpers deleted → `draw_pitch(draw_zones=True,
    highlight_defensive_third=True, emphasize_own_box=True)`. The
    `emphasize_own_box` param was ADDED to `draw_pitch()` (additive) to
    reproduce this card's stronger own-box line + dimmed attacking box.
    `apply_chart_theme()` on all figures; ACTION/CORRIDOR/SUBZONE colours bound
    to `SEMANTIC_COLORS` (values unchanged). Shell: `ds_header()` ("DEFENSIVE
    PHASE — CASTLE") + `ma-card`. 68 marker positions + zone fills verified
    identical on real match data.

### Set Pieces
- ✅ Corner Kicks card (volume/outcome KPIs, delivery-type bars, delivery maps)
  - `dash_app/src/components/set_piece_cards.py`
  - Done (Phase 2c): DELIVERY/OUTCOME palettes bound to new `SEMANTIC_COLORS`
    families `delivery_*`/`sp_*` (values unchanged); `apply_chart_theme()` on all
    figures. DRAW_PITCH DEFERRAL: the corner maps are PORTRAIT-oriented
    (figure x = Opta y, goal at top) with GA/CA zone furniture that IS the
    analysis — adopting landscape `draw_pitch(half="attacking")` would rotate
    the chart 90°; intentionally deferred and documented in-module. Shell:
    `ds_header()` ("SET PIECES — CORNERS") + `.ma-card`. Corner trace data
    verified intact on real match data.
- ✅ Direct FK shot map + FK delivery maps (Free Kicks card)
  - Done (Phase 2c): FK_TYPE/FK_OUTCOME palettes bound to new `fk_*`/`sp_*`
    keys (values unchanged); themed via `apply_chart_theme()`. Same portrait-
    orientation deferral as corners. Origin marker positions + hover verified
    identical (Bologna–Lecce direct FK). Shell: `ds_header()` ("SET PIECES —
    FREE KICKS") + `.ma-card`.
- ✅ GK save map / goalmouth figure (`_build_goalmouth_figure` + `_apply_gm_layout`)
  - Done (Phase 2c): themed in place (`apply_chart_theme()` before
    `_apply_gm_layout`); goalmouth (y/z) framing is geometrically distinct from
    any pitch view — `draw_pitch()` adoption NOT pursued (documented exception;
    the only Match Analysis pitch-style chart not on `draw_pitch()` along with
    the portrait set-piece maps and the 2b shot maps).

### Offensive Transitions
- ✅ Offensive transition card (overview KPIs, P1–P3 bars, origins pitch)
  - `dash_app/src/components/offensive_transition_cards.py`
  - Done (Phase 2a): private pitch helpers deleted → `draw_pitch(draw_zones=True)`;
    `apply_chart_theme()` on every figure; P1/P2/P3 greens, corridors and accent
    bound to `SEMANTIC_COLORS` (new `transition_p1/p2/p3` keys, values unchanged).
    Green own-half shade and threshold annotation preserved. Shell: `ds_header()`
    ("TRANSITIONS — OFFENSIVE") + `ma-card`. 32 marker positions verified
    identical on real match data. `analytics/offensive_transitions.py` untouched
    (computation only).

### Chance Conceded
- ✅ Chances Conceded card (overview, origin breakdown, xGA bars, origin grid,
  quality donut, defensive-half shot map, chain-to-concede matrix)
  - `dash_app/src/components/chance_conceded_cards.py`
  - Done (Phase 2b): mirrors Chance Creation's decisions — ORIGIN_COLORS bound to
    `SEMANTIC_COLORS["origin_*"]` (values unchanged); `apply_chart_theme()` on
    all 5 figures. SHOT MAP DEFERRAL: `_draw_defensive_half()` kept (detailed
    left-half markings, same geometry-conflict reason as Chance Creation);
    restyled in place. Intro paragraph folded into the `ds_header()` subtitle
    (copy preserved, incl. opponent name). Shell: "DEFENSIVE PHASE — CHANCE
    CONCEDED" + `.ma-card`. 14 shot positions verified identical.
    `analytics/chance_creation.py` (shared engine) untouched.

### Build-up Chain
- ✅ Build-up from Goal Kicks card (type summary, zone heatmap, outcomes, chains)
  - `dash_app/src/components/buildup_cards.py`, `pitch_zones.py`
  - Done (Phase 2b): `apply_chart_theme()` on both bar figures and on
    `pitch_zone_figure()` (specific layout overrides preserved — zone fills,
    counts and geometry byte-identical). HEATMAP FINDING: `pitch_zone_figure()`'s
    navy→primary-red interpolation IS the unified sequential ramp from Phase 2a
    (`SEMANTIC_COLORS["heatmap_colorscale"]`) — formula kept, documented inline.
    `pitch_zones.OUTCOME_COLORS` bound to the semantic outcome pair (values
    unchanged). `draw_pitch()` adoption deferred for `pitch_zone_figure()` —
    bespoke zone canvas (the zones are the data), same rationale as the FT zone
    heatmap. The P/N shade families and short/long colours in buildup_cards.py
    already equal semantic values; literals left in place (shade variants like
    #16a34a/#dc2626 have no semantic key — note for a future palette pass).
    Shell: `ds_header()` ("BUILD-UP — GOAL KICKS") + `.ma-card`. Verified on
    real match data (6 goal kicks). NOTE: `pitch_zone_figure` is only called by
    buildup_cards; Phase 3's opponent GK heatmap re-implements its own copy
    (`opp-season-gk-*`) — handle there in Phase 3.

### General Build-up
- ✅ General Build-up (Open Play) card (frequency KPIs, origin/progression bars,
  after-Z3 sections)
  - `dash_app/src/components/general_buildup_cards.py`
  - Done (Phase 2b): PROG_COLORS bound to `SEMANTIC_COLORS["method_*"]` — the
    progression categories' values were ALREADY identical to the FT entry-method
    taxonomy, so this is a pure binding (new additive key `method_other` for the
    grey "Other" bucket). `apply_chart_theme()` on both figures. Shell:
    `ds_header()` ("BUILD-UP — GENERAL") + `.ma-card`. No pitch in this card.
    Verified on real match data (37 Z3 entries / 287 possessions).

### Player Events UI
- N/A (Phase 2c finding) — NOT a live Dash UI component.
  - `dash_app/src/components/match_report_cards.py` is imported ONLY by the
    ReportLab PDF builder (`src/reporting/match_report_pdf.py`); the "Match
    Report" module card on the Match Analysis page is a PDF DOWNLOAD trigger
    (`analysis_callbacks._download_match_report`). `pages/match_report.py` does
    not exist; `tabs/match_report.py` belongs to the legacy un-routed tabs
    system. Per Phase 2c scope rules, PDF-builder styling was NOT attempted —
    flag for a separate prompt if a styled PDF report is wanted.

---

## Phase 3 — Opponent Analysis (Season-aggregate view) — ✅ COMPLETE

> Root: `dash_app/src/components/opponent_offensive_phase.py`,
> `dash_app/src/callbacks/analysis_callbacks.py`  
> All component IDs use the `opp-season-` prefix.
> REGRESSION FIXED in this phase: the module imported `_draw_pitch_base`/
> `_base_layout` (deleted in Phase 2b) — the Opponent page failed to load via
> its lazy callbacks. Fixed by migrating `_build_ft_entry_scatter()` to
> `draw_pitch()`.
> CSS scope decision: `.ma-card` REUSED (rules are generic); the three lazy
> sections got `buildup-card ma-card` shells; KPI strips styled via the scope.
> All figures themed via `apply_chart_theme()` (13 sites; `template=
> "plotly_dark"` removed throughout — explicit theming instead). Section
> headers delegate to the shared `ds_header()` (additive `_section_header`
> params).

- ✅ Opponent GK distribution zone heatmap (`opp-season-gk-*`)
  - `_build_gk_zone_pitch()` — RAMP FINDING: NOT the unified navy→red
    `heatmap_colorscale`; it is a deliberate red-only gradient
    (rgba(120→220, 40→30, 40→30)) per its docstring ("with a red colorscale").
    Binding to the unified ramp would be a visible change → formula kept
    byte-identical, documented. Zone fills/counts/outcome dots verified
    unchanged. `draw_pitch()` deferred (bespoke zone canvas, 2b precedent).
    Radar + GK benchmark bars themed. Eyebrow "OPPONENT — GK DISTRIBUTION".
- ✅ Opponent Final Third entry benchmarks (`opp-season-ft-*`)
  - `_build_benchmark_bar()` — highlight bound to `COLORS_DARK["accent"]`,
    neutral to new additive `SEMANTIC_COLORS["benchmark_neutral"]` ("#4a6274",
    value unchanged; readable on both themes — no light variant needed).
    Sort order/values/colours verified exact. FT zone pitch + entry scatter
    + success/timing/depth charts themed; entry scatter migrated to
    `draw_pitch(draw_zones=True, highlight_final_third=True)` (the regression
    fix). Eyebrow "OPPONENT — FINAL THIRD".
- ✅ Opponent Chance Creation origin + xG (`opp-season-cc-*`)
  - xG modal figure (`_build_cc_xg_bar` → shared `_build_benchmark_bar`) and
    Goal Types chart themed. ORIGIN COLOURS: imports `ORIGIN_COLORS` directly
    from `chance_creation_cards` — already bound to `origin_*` in Phase 2b
    (same variable, no copy → nothing to unify). Attack Origin Zones pitch
    map: bespoke zone canvas (accent-tinted fills ARE the data) → themed in
    place, `draw_pitch()` NOT adopted (consistent with the 2b zone-heatmap
    precedent). Modal open/close behaviour untouched. 20-team benchmark
    verified through the real modal builder. Eyebrow "OPPONENT — CHANCE
    CREATION".
- N/A Opponent Defensive Pressing benchmarks
  - **Does not exist.** `opponent_offensive_phase.py` is offensive-phase only —
    no PPDA/pressing benchmark is implemented (the Phase 0 row was an
    assumption). The shared `_build_benchmark_bar()` helper (used by GK/FT/CC
    benchmarks) is themed once, so a future pressing benchmark inherits the
    style for free.
- ✅ Opponent season overview KPI strip
  - `_mini_kpi()`/`_clickable_kpi()` use `.kpi-card`, now styled by the
    `.ma-card` scope on the section shells (Phase 1/2 pattern — scoped CSS,
    not inline). Overview page header → `ds_header()` ("OPPONENT ANALYSIS —
    SEASON VIEW").

---

## Phase 4 — Light-mode Integration Audit — ✅ COMPLETE

- ✅ Fix 1 — Light background unified on `#FAF7F0`.
  - AUDIT FINDING: the original `#f4f6f9` body rules appear LATER in styles.css
    than the Phase 0 override at equal specificity+!important, so the cool-blue
    was still winning on `<body>` (only `.app-root` showed parchment). Fixed at
    the source: `.light-theme { --bg-dark }`, both body rules, and the light
    scrollbar track now use `#FAF7F0`. (In-card light surfaces like
    `.match-officials-card` keep `#f4f6f9` intentionally — they are surfaces,
    not the page background.)
- ✅ Fix 2 — Skip-list corrected.
  - `.pitch-zone-container` / `.final-third-pitch-container` were DEAD selectors
    (no component uses them) — removed. Convention: every dark-by-design chart
    is wrapped in `.pitch-dark-container` (or `.formation-pitch`). AUDIT FIX:
    the opponent GK zone pitch, FT zone pitch and FT entry scatter were dark
    pitches WITHOUT the wrapper (would have been stripped to white-on-white in
    light mode) — now wrapped. Full dark-by-design inventory, all covered:
    formation pitch, all defensive/transition pitch maps, FT scatter+heatmap,
    shot maps, GK zone heatmap (build-up), set-piece portrait maps, GK
    goalmouth, opponent GK/FT/AOZ pitches.
- ✅ Fix 3 — Observer relayout completeness.
  - `apply_chart_theme()` dark contract vs observer: fonts/axes/grid/legend/
    title/trace-textfont all patched (incl. the `#c8d0d8` benchmark outside-
    text — handled via the `textfont.color` patch, no change needed). NOT
    patched: hoverlabel (dark tooltip on light page — readable, left as-is)
    and ANNOTATIONS — fixed the one real casualty: benchmark-bar "Avg" line/
    label now `#748b9c` slate (readable on both themes; was white-on-dark
    only). Last stray `template="plotly_dark"` removed from the opponent
    empty-benchmark fallback. Remaining `plotly_dark` uses are out of scope:
    legacy un-routed `registry/loaders.py`, un-imported
    `multi_season_standings_v1.py`, PDF builder. GK red ramp contrast in
    light mode: resolved by the `.pitch-dark-container` wrap (ramp itself
    untouched, per Phase 3 decision).
- ✅ Fix 4 — Lazily-mounted figures: VERIFIED covered. The clientside callback
  fires on theme-store init (not just toggle) and installs a persistent
  `MutationObserver` that re-patches any newly mounted `.js-plotly-plot`
  (covers the 3 lazy opponent sections, the CC xG / goal-types modals, and
  `dcc.Loading` swaps), honouring the skip-list via `closest()`.
- ✅ Fix 5 — Font: Inter loads from Google Fonts CDN (`display=swap` in
  `app.py` external_stylesheets) and `FONT_FAMILY` carries the full system
  fallback stack — graceful degradation confirmed; no new dependency added.

### Phase 4b — optional visual confirmation checklist (low-risk leftovers)
- ⬜ PPDA scatter (Team Overview): quadrant median dash lines are
  `rgba(255,255,255,0.18)` — near-invisible in light mode (pre-existing;
  labels remain readable).
- ⬜ Inside-bar white text on stacked bars gets repainted dark by the observer
  in light mode (pre-existing behaviour) — confirm legibility on saturated
  segments by eye.
- ⬜ GK outcome radar (opponent): pie slice labels repainted dark on light —
  confirm contrast on the dark-green/dark-red slices by eye.
- ⬜ buildup_cards P/N shade literals (#16a34a/#dc2626 etc.) — future palette
  pass (noted since Phase 2b).

# ═══════════════════════════════════════════════════════════════════════════
# REDESIGN — ALL PHASES COMPLETE (0–4)
# ═══════════════════════════════════════════════════════════════════════════
# Phase 0: design system (theme.py, plotly_template.py, pitch_utils.py) ✅
# Phase 1: Team Overview ✅ (league table N/A — never existed on the tab)
# Phase 2: Match Analysis, 11 cards ✅ — documented exceptions: GK goalmouth +
#   portrait set-piece maps + 2b shot maps themed in place (not on draw_pitch);
#   Player Events = PDF builder (separate prompt if wanted)
# Phase 3: Opponent Analysis ✅ (pressing benchmarks N/A — never implemented;
#   GK red ramp deliberately distinct from the unified heatmap_colorscale;
#   fixed the 2b import regression that broke the page)
# Phase 4: light-mode audit ✅ (4b visual-confirmation checklist above)
# Geometry: draw_pitch boxes corrected to Opta/zone-aligned 83.33/16.67/
#   21.1–78.9 in Phase 2c (sub-pixel; all phases regression-checked).
# ═══════════════════════════════════════════════════════════════════════════
