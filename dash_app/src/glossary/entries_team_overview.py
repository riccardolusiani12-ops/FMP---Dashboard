"""Glossary entries rendered in Team Overview (/serie-a/team/<slug>)."""

from __future__ import annotations

from src.glossary._common import (
    D_CCON, D_FORMATION, D_GOAL_DIST, D_PLAYER, D_PPDA_TO, D_WHEEL, D_XG_SUMMARY,
    MODAL_TOTALS, PENALTY_XG_TEXT, SEASON_MEAN_DEVIATION, SEASON_RATIO,
    md, metric,
)

TO = "team_overview"
KPI_ROW = "KPI Row"
POINTS = "Points Progression"
FORMATIONS = "Most-Used Formations"
PERFORMANCE = "Offensive Production and Defensive Efficiency"
WHEEL = "Playing Style Wheel · Style Evolution"
PRESSING = "Pressing Intensity"

_STANDINGS = (
    "Source: the season standings table (standings_{season}.parquet), built by "
    "multi_season_standings.compute_standings() from final scorelines: "
    "3 points for a win, 1 for a draw, 0 for a defeat."
)

_WHEEL_PCT = (
    "**Wheel value:** the within-season percentile of the raw value against "
    "every Serie A team of the same season — scipy `percentileofscore(kind='rank')`, "
    "clipped to 0–99 and rounded to 1 dp; a missing raw value stays empty. "
    "KPIs where a lower raw value is better (D1, D2, A2) are inverted "
    "(100 − percentile), so a longer spoke always means more of the named trait. "
    "Style Evolution plots the same percentile for every available season. "
    "Raw values are shown, with units, in the reference grid and the "
    "league-comparison modal (percentiles)."
)

_TWO_PPDA = (
    "**Two PPDA definitions (intentional, never merge):** Team Overview PPDA "
    "divides by the pressing team's *ball recoveries*; Match Analysis and "
    "Opponent Analysis PPDA divide by *tackles + interceptions + fouls committed "
    "+ challenges*. The two numbers are not comparable."
)

_FRAME_ISSUE = (
    "**Coordinate frame (code reference):** ppda.load_season_events() flips x "
    "to `x_from_own_goal` using home/away and period, assuming absolute "
    "coordinates. The raw Opta files are already team-relative (verified in the "
    "Phase 0 audit), so for the away team in the first half and the home team "
    "in the second half the frame is inverted. Reported in "
    "docs/glossary_review.md; not changed."
)


ENTRIES: list[dict] = [
    # ── KPI row ──────────────────────────────────────────────────────────────
    metric(
        id="league_position",
        name="Position",
        sections=[TO],
        module={TO: KPI_ROW},
        short_definition="The team's current place in the Serie A table for the selected season.",
        formula="rank by Points, then Goal Difference, then Goals For",
        unit="rank",
        reading="lower_better",
        reading_note="1st is the top of the table.",
        methodology=md(
            _STANDINGS,
            "Teams are ordered by Points, then Goal Difference, then Goals For "
            "(descending). Head-to-head records, which the official Serie A "
            "tie-break uses, are not applied, so tied teams can be ordered "
            "differently from the official table.",
        ),
        notes="No current methodology document covers the standings KPIs.",
        source_doc=None,
        status="needs_review",
        season_aggregation="sum",
    ),
    metric(
        id="season_record",
        name="Season Record",
        sections=[TO],
        module={TO: KPI_ROW},
        short_definition="Matches won, drawn and lost so far this season (W · D · L).",
        formula="W · D · L counts from final scorelines",
        unit="count",
        reading="contextual",
        reading_note="More wins is better, but the split only makes sense alongside matches played.",
        methodology=md(
            _STANDINGS,
            "W, D and L are the counts of wins, draws and defeats. The card icon "
            "is green when W > L, red when L > W, grey otherwise.",
        ),
        notes="No current methodology document covers the standings KPIs.",
        source_doc=None,
        status="needs_review",
        season_aggregation="sum",
    ),
    metric(
        id="last_5_form",
        name="Last 5",
        sections=[TO],
        module={TO: KPI_ROW},
        short_definition="Results of the team's five most recent league matches, oldest to newest.",
        formula="last five Result values ordered by matchday",
        unit="category",
        reading="contextual",
        reading_note="A recent-form indicator; five matches is a small sample.",
        methodology=md(
            "Source: points_progression_{season}.parquet "
            "(multi_season_standings.compute_points_progression()). The team's "
            "rows are sorted by Matchday and the last five `Result` letters "
            "(W/D/L) are shown as coloured badges.",
        ),
        notes="No current methodology document covers the standings KPIs.",
        source_doc=None,
        status="needs_review",
        season_aggregation="sum",
    ),
    metric(
        id="goal_difference",
        name="Goal Diff.",
        sections=[TO],
        module={TO: KPI_ROW},
        short_definition="Goals scored minus goals conceded in the league this season.",
        formula="GF − GA",
        unit="count",
        reading="higher_better",
        reading_note="A positive value means the team has scored more than it has conceded.",
        methodology=md(
            _STANDINGS,
            "GF and GA are scoreline goals, so own goals count for the team "
            "that benefits. Shown with a sign; green if positive, red if negative.",
        ),
        notes="No current methodology document covers the standings KPIs.",
        source_doc=None,
        status="needs_review",
        season_aggregation="sum",
    ),
    metric(
        id="points_per_game",
        name="PPG",
        sections=[TO],
        module={TO: KPI_ROW},
        short_definition="Average league points earned per match played this season.",
        formula="Points ÷ matches played",
        unit="points per match",
        reading="higher_better",
        reading_note="3.00 is the maximum (all wins).",
        methodology=md(
            _STANDINGS,
            "PPG = Points ÷ MP, shown to 2 dp. Colour: green ≥ 2.00, orange ≥ 1.30, "
            "red below.",
            SEASON_RATIO,
        ),
        notes="No current methodology document covers the standings KPIs.",
        source_doc=None,
        status="needs_review",
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="mean_age",
        name="Mean Age",
        sections=[TO],
        module={TO: KPI_ROW},
        short_definition="Average age of the squad as published by Transfermarkt for the season.",
        formula=None,
        unit="years",
        reading="contextual",
        reading_note="Describes squad profile, not quality.",
        methodology=md(
            "External value: scraped from Transfermarkt's 'Età media' table "
            "(scripts/scrape_avg_age.py) into data/external/avg_age_serie_a.csv "
            "and read by data_loader.load_team_average_age(). Per the scraper's "
            "notes, Transfermarkt weights player ages by minutes played; the "
            "dashboard does not recompute it.",
            "Colour: green below 26, orange 26–28, red above 28.",
        ),
        notes=(
            "The only description is the LEGACY doc _archive/MEAN_AGE_KPI_IMPLEMENTATION.md, "
            "so no source_doc is set. The minutes-weighting claim is Transfermarkt's, "
            "not verified here."
        ),
        source_doc=None,
        status="needs_review",
        season_aggregation="external",
    ),
    # ── Points progression ───────────────────────────────────────────────────
    metric(
        id="points_progression",
        name="Points Progression",
        sections=[TO],
        module={TO: POINTS},
        short_definition="Cumulative league points after each matchday, with the selected season highlighted.",
        formula="cumulative sum of match points (3/1/0) by matchday",
        unit="points",
        reading="higher_better",
        reading_note="A steeper line means points are being collected faster.",
        methodology=md(
            "Source: points_progression_{season}.parquet. Each match gives "
            "3/1/0 points; `CumulativePoints` is the running sum ordered by "
            "matchday. All seasons are drawn and the selected season is "
            "highlighted; the legend marks the Champions League, Europa/Conference "
            "League and relegation zones.",
        ),
        source_doc=D_PPDA_TO,
        season_aggregation="sum",
    ),
    # ── Formations ───────────────────────────────────────────────────────────
    metric(
        id="formation_times_used",
        name="Times Used",
        sections=[TO],
        module={TO: FORMATIONS},
        short_definition="How many times the team lined up in this formation during the season.",
        formula="count of formation records for the formation string",
        unit="count",
        reading="contextual",
        reading_note="Describes the tactical repertoire; not better or worse.",
        methodology=md(
            "Formation records come from Opta Team set-up events (type_id 34, the "
            "starting formation) and Formation change events (type_id 40, in-match "
            "changes) via formations.extract_team_formations(). Each record counts "
            "once, so one match contributes its starting formation plus every "
            "in-match change.",
            "Only formations used at least 3 times are shown (top 3 by count); "
            "the cards are labelled 'Most Used', '2nd Most Used', '3rd Most Used'. "
            "The pitch diagram is the formation template filled with the most-used "
            "players (Hungarian assignment), not measured positions.",
        ),
        notes=(
            "The section subtitle says 'Starting shapes used three or more times', "
            "but the count also includes in-match formation changes."
        ),
        source_doc=D_FORMATION,
        season_aggregation="sum",
    ),
    metric(
        id="formation_share",
        name="Share",
        sections=[TO],
        module={TO: FORMATIONS},
        short_definition="This formation's share of the team's formation records for the season.",
        formula="Times Used ÷ total formation records × 100",
        unit="%",
        reading="contextual",
        reading_note="A high share means a settled shape; a low one means rotation.",
        methodology=md(
            "Share = formation count ÷ total formation records × 100 (records as "
            "defined for Times Used). With the precomputed formations_{season}.parquet "
            "the denominator is every formation record of the season, including "
            "formations used fewer than 3 times.",
            SEASON_RATIO,
        ),
        notes=(
            "Code reference: when the parquet is missing, the fallback "
            "compute_formation_counts() divides by the qualifying (≥ 3 uses) "
            "formations only, so the share can differ between the two paths."
        ),
        source_doc=D_FORMATION,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="starts",
        name="Starts",
        sections=[TO, "opponent_analysis"],
        module={TO: FORMATIONS, "opponent_analysis": "Player Analysis"},
        short_definition="Number of matches a player started.",
        formula="count of matches started",
        unit="count",
        reading="contextual",
        reading_note="Shows who the coach relies on; not a performance measure.",
        methodology=md(
            "Team Overview: in the formation squad panel ('View Squad'), Starts is "
            "the number of matches the player started in that formation's slot "
            "(slots 1–11), from formation_lineups_{season}.parquet; the player "
            "with most starts per slot is highlighted.",
            "Opponent Analysis: in the Squad Overview table, Starts is the number "
            "of season matches the player started (starting XI = first 11 "
            "distinct players of the team to record an on-ball event before any "
            "substitution).",
        ),
        variants=[
            {"section": TO, "name": "Starts",
             "definition": "Starts in the selected formation's slot."},
            {"section": "opponent_analysis", "name": "Starts",
             "definition": "Starts across the whole season, any formation."},
        ],
        notes=(
            "The formation-panel variant is only described in the LEGACY "
            "match-report.md (§3.3)."
        ),
        source_doc=D_PLAYER,
        status="needs_review",
        season_aggregation="sum",
    ),
    metric(
        id="lineup_minutes",
        name="Minutes",
        sections=[TO],
        module={TO: FORMATIONS},
        short_definition="Total minutes the player played in matches started in this formation.",
        formula="Σ minutes over starts in the formation",
        unit="minutes",
        reading="contextual",
        reading_note="Shows reliance on the player within this shape.",
        methodology=md(
            "From formation_lineups_{season}.parquet (precompute_formation_lineups): "
            "for every match the team started in the formation, the minutes of each "
            "starter are summed per player and slot.",
        ),
        notes="Only described in the LEGACY match-report.md (§3.3).",
        source_doc=None,
        status="needs_review",
        season_aggregation="sum",
    ),
    metric(
        id="lineup_avg_minutes",
        name="Avg Min",
        sections=[TO],
        module={TO: FORMATIONS},
        short_definition="Average minutes per start for the player in this formation.",
        formula="Minutes ÷ Starts",
        unit="minutes",
        reading="contextual",
        reading_note="Values near 90 mean the player usually completes the match.",
        methodology=md(
            "Avg Min = total minutes ÷ starts in the formation slot, from "
            "formation_lineups_{season}.parquet.",
            SEASON_RATIO,
        ),
        notes="Only described in the LEGACY match-report.md (§3.3).",
        source_doc=None,
        status="needs_review",
        season_aggregation="ratio_of_sums",
    ),
    # ── Goals & xG ───────────────────────────────────────────────────────────
    metric(
        id="goals_scored",
        name="Goals Scored",
        sections=[TO],
        module={TO: PERFORMANCE},
        short_definition="League goals scored this season, including opponent own goals.",
        formula="GF from the standings table",
        unit="count",
        reading="higher_better",
        reading_note="More goals scored is better.",
        methodology=md(
            _STANDINGS,
            "The card shows GF (scoreline goals, so opponent own goals count) "
            "with the season xG underneath. The comparison bar chart plots "
            "Goals Scored against xG.",
            "The '15-minute intervals' button opens the goal distribution for "
            "goals scored (see 'Goals Scored — 15-Minute Intervals').",
            MODAL_TOTALS + " Sorted descending.",
        ),
        notes=(
            "goal-distribution.md §9 says the modal ranks goals per match with each "
            "team's share of league goals; the code ranks season totals and shows no share."
        ),
        source_doc=D_GOAL_DIST,
        season_aggregation="sum",
    ),
    metric(
        id="goals_conceded",
        name="Goals Conceded",
        sections=[TO, "match_analysis", "opponent_analysis"],
        module={
            TO: PERFORMANCE,
            "match_analysis": "Defensive Phase — Chances Conceded",
            "opponent_analysis": "Defensive Phase — Chances Conceded",
        },
        short_definition="Goals the team let in, including own goals it scored against itself.",
        formula="count of goals conceded",
        unit="count",
        reading="lower_better",
        reading_note="Fewer goals conceded is better.",
        methodology=md(
            "Team Overview: GA from the standings table (scoreline goals). The "
            "card shows the season xGC underneath. " + MODAL_TOTALS + " Sorted "
            "ascending (fewest first).",
            "Match Analysis: the number of conceded shots that were goals. "
            "Conceded shots come from running Chance Creation for the opponent, "
            "so own goals by the analysed team are included as 'Own Goal' rows. "
            "The subtitle shows big chances conceded.",
            "Opponent Analysis ('Goals Conceded / Match'): season total of "
            "conceded goals ÷ matches played (chances_conceded_summary_{season}.parquet). "
            "Its league modal ranks the per-match value.",
        ),
        source_doc=D_CCON,
        season_aggregation="total_per_match",
    ),
    metric(
        id="xg_for",
        name="xG",
        sections=[TO],
        module={TO: PERFORMANCE},
        short_definition="Expected goals: the summed scoring probability of every shot the team took this season.",
        formula="Σ per-shot xG of the team's shots",
        unit="xG",
        reading="higher_better",
        reading_note="More xG means the team created more and better chances.",
        methodology=md(
            "Source: xg_{season}.parquet from xg.compute_team_xg_summary(), which "
            "uses load_season_shots() and the batch xG API (rebound and assist-type "
            "features included). Shots are Opta type_id 13–16. " + PENALTY_XG_TEXT,
            "The subtitle compares with actual goals: ↑/↓ |GF − xG| 'vs actual' "
            "(green when GF ≥ xG, i.e. finishing above expectation).",
            MODAL_TOTALS + " Sorted descending, 2 dp.",
        ),
        notes=(
            "xg-summary.md §9 says the modal ranks xG per match with a league share; "
            "the code ranks season totals without a share. Includes penalty xG."
        ),
        source_doc=D_XG_SUMMARY,
        season_aggregation="sum",
    ),
    metric(
        id="xg_against",
        name="xGC",
        sections=[TO],
        module={TO: PERFORMANCE},
        short_definition="Expected goals conceded: the summed xG of every shot opponents took against the team this season.",
        formula="Σ per-shot xG of opponent shots against the team",
        unit="xG",
        reading="lower_better",
        reading_note="Less xG conceded means the team allowed fewer and worse chances.",
        methodology=md(
            "Same source and model as xG: each season shot is credited against "
            "the opposing team resolved from the canonical home/away names. "
            + PENALTY_XG_TEXT,
            "Subtitle: ↑/↓ |GA − xGC| 'vs actual' (green when GA ≤ xGC).",
            MODAL_TOTALS + " Sorted ascending (lowest first), 2 dp.",
        ),
        notes=(
            "xg-summary.md §9 says the modal ranks xGC per match with a league "
            "share; the code ranks season totals without a share."
        ),
        source_doc=D_XG_SUMMARY,
        season_aggregation="sum",
    ),
    metric(
        id="goals_scored_by_interval",
        name="Goals Scored — 15-Minute Intervals",
        sections=[TO],
        module={TO: PERFORMANCE},
        short_definition="When in the match the team scores its goals, in six 15-minute windows.",
        formula="count of goals per window: 0–15, 15–30, 30–45, 45–60, 60–75, 75–90",
        unit="count",
        reading="contextual",
        reading_note="Shows timing patterns (fast starts, late goals), not quality.",
        methodology=md(
            "Source: goal_distribution.compute_goal_distribution(). Goal events "
            "(type_id 16) are credited to the scoring side; own goals (`own goal` "
            "qualifier) are credited to the team that benefits.",
            "Bins are half-open [lo, hi): 0–15, 15–30, 30–45, 45–60, 60–75, and "
            "75–90 with no upper bound. First-half stoppage time (period 1, minute "
            "≥ 45) is capped at 44 so it falls in 30–45; second-half stoppage stays "
            "in 75–90. Always six windows.",
            "Each tile shows the count and its share of the season total "
            "(count ÷ total × 100).",
        ),
        source_doc=D_GOAL_DIST,
        season_aggregation="sum",
    ),
    metric(
        id="goals_conceded_by_interval",
        name="Goals Conceded — 15-Minute Intervals",
        sections=[TO],
        module={TO: PERFORMANCE},
        short_definition="When in the match the team concedes its goals, in six 15-minute windows.",
        formula="count of goals conceded per window: 0–15, 15–30, 30–45, 45–60, 60–75, 75–90",
        unit="count",
        reading="contextual",
        reading_note="Shows when the team is vulnerable; read alongside the total.",
        methodology=md(
            "Same windows and stoppage-time rules as 'Goals Scored — 15-Minute "
            "Intervals', applied to goals conceded (own goals by the team count "
            "as conceded). Each tile shows count and share of the season total.",
        ),
        source_doc=D_GOAL_DIST,
        season_aggregation="sum",
    ),
    # ── Playing Style Wheel (12 KPIs) ────────────────────────────────────────
    metric(
        id="ps_chance_prevention",
        name="Chance Prevention",
        sections=[TO],
        module={TO: WHEEL},
        short_definition="How little expected-goal threat the team concedes, as a league percentile (D1).",
        formula="raw = xG conceded ÷ matches played; wheel = 100 − percentile",
        unit="percentile",
        reading="higher_better",
        reading_note="Percentile is inverted: higher means fewer xG conceded.",
        methodology=md(
            "Raw (D1): `xg_conceded_per_match` from chances_conceded_summary_{season}.parquet "
            "= Σ xG of every opponent shot against the team ÷ matches played. "
            + PENALTY_XG_TEXT,
            _WHEEL_PCT,
        ),
        notes=(
            "Doc and info modal describe 'non-penalty xGA per 90'. The code uses "
            "all xG conceded, penalties included, per match (not per 90); the "
            "comment claiming penalties are already excluded is incorrect."
        ),
        source_doc=D_WHEEL,
        season_aggregation="rank_percentile",
    ),
    metric(
        id="ps_defensive_intensity",
        name="Defensive Intensity",
        sections=[TO],
        module={TO: WHEEL},
        short_definition="How few passes opponents are allowed before the team makes a defensive action (D2, based on PPDA).",
        formula="raw = Σ opp passes (own 60%) ÷ Σ (tackles + interceptions + fouls + challenges) at x ≥ 40; wheel = 100 − percentile",
        unit="percentile",
        reading="higher_better",
        reading_note="Percentile is inverted: higher means a lower PPDA, i.e. more intense defending.",
        methodology=md(
            "Raw (D2) = ppda_num_overall ÷ ppda_den_overall from "
            "pressing_summary_{season}.parquet, i.e. the narrow-definition PPDA of "
            "the Opponent Analysis pressing view (see 'PPDA' in Opponent Analysis): "
            "opponent passes (type_id 1, 2, 74 and throw-ins) made in their own 60% "
            "of the pitch ÷ the team's tackles, interceptions, fouls committed and "
            "challenges at x ≥ 40.",
            SEASON_RATIO,
            _WHEEL_PCT,
            "The wheel spoke and Style Evolution label it 'Intensity'.",
        ),
        notes=(
            "Uses the narrow PPDA denominator, not the Team Overview PPDA KPI "
            "(ball recoveries). The info modal says 'opposition touches'; the "
            "code counts opposition passes."
        ),
        source_doc=D_WHEEL,
        season_aggregation="rank_percentile",
    ),
    metric(
        id="ps_high_line",
        name="High Line",
        sections=[TO],
        module={TO: WHEEL},
        short_definition="How often the team's defensive line produces offside calls and deep interventions, per 100 opponent final-third passes (D3).",
        formula="raw = (offsides provoked + through balls conceded + deep tackles/interceptions/clearances) ÷ opp final-third passes × 100",
        unit="percentile",
        reading="contextual",
        reading_note="Higher means a more aggressive, higher-risk line; it is a style trait, not a quality.",
        methodology=md(
            "Season counters from playing_style._raw_counters_for_match(), summed "
            "over the season: offsides provoked (type_id 55 by the team) + "
            "through balls conceded (opponent passes with the `Through ball` "
            "qualifier) + 'GK sweeper' actions; divided by opponent passes "
            "starting in their final third (x ≥ 66.67 in their frame), × 100.",
            "'GK sweeper' actions are the team's tackles, interceptions and "
            "clearances (type_id 7, 8, 12) at x ≤ 16.67, by any player.",
            SEASON_RATIO,
            _WHEEL_PCT,
        ),
        notes=(
            "Docs call the third component 'GK-sweeper actions'; the code counts "
            "deep tackles, interceptions and clearances by any player, which "
            "rewards deep defending as well."
        ),
        source_doc=D_WHEEL,
        season_aggregation="rank_percentile",
    ),
    metric(
        id="ps_deep_buildup",
        name="Deep Build-up",
        sections=[TO],
        module={TO: WHEEL},
        short_definition="How often the team's goal kicks are played short to a receiver in its own defensive third (P1).",
        formula="raw = 1 − long goal kicks ÷ goal kicks",
        unit="percentile",
        reading="contextual",
        reading_note="Higher means more short build-up from goal kicks; a style choice.",
        methodology=md(
            "Raw (P1) = 1 − gk_long_pct ÷ 100 from offensive_summary_{season}.parquet. "
            "gk_long_pct is the share of the team's goal kicks (Opta `Goal Kick` "
            "qualifier) whose first receiver is in zones Z7–Z18 of the 18-zone grid, "
            "i.e. beyond the team's defensive third (see 'Long Ball %').",
            SEASON_RATIO,
            _WHEEL_PCT,
        ),
        notes=(
            "The info modal says 'share of GK passes that are short (not long balls "
            "≥ 40 yards)'; the code uses goal kicks only, classified by the first "
            "receiver's zone."
        ),
        source_doc=D_WHEEL,
        season_aggregation="rank_percentile",
    ),
    metric(
        id="ps_press_resistance",
        name="Press Resistance",
        sections=[TO],
        module={TO: WHEEL},
        short_definition="How many touches the team has in its own two-thirds for every tackle or interception the opponent makes there (P2).",
        formula="raw = own-two-thirds events ÷ opp tackles + interceptions in that zone",
        unit="percentile",
        reading="higher_better",
        reading_note="Higher means the team keeps the ball under pressure more often.",
        methodology=md(
            "Numerator: every team event with x ≤ 66.67 (any event type with "
            "coordinates). Denominator: opponent tackles and interceptions "
            "(type_id 7, 8) at x ≥ 33.33 in the opponent's frame, i.e. inside the "
            "team's own two-thirds. Counters are summed over the season.",
            SEASON_RATIO,
            _WHEEL_PCT,
        ),
        source_doc=D_WHEEL,
        season_aggregation="rank_percentile",
    ),
    metric(
        id="ps_possession",
        name="Possession",
        sections=[TO],
        module={TO: WHEEL},
        short_definition="The team's average share of possession time per match (P3).",
        formula="raw = mean over matches of Possession %",
        unit="percentile",
        reading="contextual",
        reading_note="Higher means more of the ball; a style trait.",
        methodology=md(
            "Raw (P3) = ft_possession_pct from offensive_summary_{season}.parquet, "
            "the mean of the per-match 'Possession %' values from the Build-up to "
            "Final Third module (time-based possession share; see 'Possession %').",
            SEASON_MEAN_DEVIATION,
            _WHEEL_PCT,
        ),
        notes=(
            "Doc crosswalk and info modal describe 'share of total open-play "
            "passes'; the code uses time-based possession share."
        ),
        source_doc=D_WHEEL,
        season_aggregation="rank_percentile",
    ),
    metric(
        id="ps_central_progression",
        name="Central Progression",
        sections=[TO],
        module={TO: WHEEL},
        short_definition="How rarely the team crosses, relative to its passing volume (G1).",
        formula="raw = 1 − (crosses ÷ passes × 100)",
        unit="percentile",
        reading="contextual",
        reading_note="Higher means fewer crosses per 100 passes, i.e. more central build-up.",
        methodology=md(
            "Crosses are team passes (type_id 1) with the `Cross` qualifier; "
            "passes are all team passes. Raw = 1 − crosses per 100 passes, so the "
            "raw value is usually negative (e.g. 1 − 3.2 = −2.2); the reference "
            "grid shows crosses per 100 passes instead. The transformation does not "
            "change the percentile ranking.",
            SEASON_RATIO,
            _WHEEL_PCT,
            "Shortened to 'Central Progr.' on the wheel spoke.",
        ),
        source_doc=D_WHEEL,
        season_aggregation="rank_percentile",
    ),
    metric(
        id="ps_circulate",
        name="Circulate",
        sections=[TO],
        module={TO: WHEEL},
        short_definition="How much the team recycles the ball instead of passing straight forward (G2).",
        formula="raw = 1 − Σ forward x-distance of passes ÷ Σ pass length",
        unit="percentile",
        reading="contextual",
        reading_note="Higher means more lateral/back circulation; lower means more direct play.",
        methodology=md(
            "For every team pass with start and end coordinates: forward distance "
            "= max(end x − start x, 0); pass length = √(Δx² + Δy²) in Opta units. "
            "Directness = Σ forward distance ÷ Σ length over the season; raw = 1 − "
            "directness. Carries are not included.",
            SEASON_RATIO,
            _WHEEL_PCT,
        ),
        notes="The info modal mentions passing/carrying distance; only passes are used.",
        source_doc=D_WHEEL,
        season_aggregation="rank_percentile",
    ),
    metric(
        id="ps_field_tilt",
        name="Field Tilt",
        sections=[TO],
        module={TO: WHEEL},
        short_definition="The team's share of all final-third passes in its matches (G3).",
        formula="raw = team final-third passes ÷ (team + opponent final-third passes) × 100",
        unit="percentile",
        reading="contextual",
        reading_note="Higher means the team plays more of the game in the opponent's third.",
        methodology=md(
            "Final-third passes are passes starting at x ≥ 66.67 in each team's own "
            "attacking frame. Counts for both sides are summed over the season "
            "before dividing.",
            SEASON_RATIO,
            _WHEEL_PCT,
        ),
        notes=(
            "Different from the 'Field Tilt %' KPI in Pressing Intensity, which is "
            "a mean of per-match tilts computed in a different coordinate frame."
        ),
        source_doc=D_WHEEL,
        season_aggregation="rank_percentile",
    ),
    metric(
        id="ps_chance_creation",
        name="Chance Creation",
        sections=[TO],
        module={TO: WHEEL},
        short_definition="Non-penalty expected goals the team generates per match (A1).",
        formula="raw = Σ non-penalty xG ÷ matches played",
        unit="percentile",
        reading="higher_better",
        reading_note="Higher means more open-play and set-piece threat.",
        methodology=md(
            "From shots_{season}.parquet: the team's shots excluding penalties "
            "(`is_penalty`), xG summed, divided by matches played. Own-goal rows "
            "carry xG 0. Per match, not per 90.",
            _WHEEL_PCT,
        ),
        notes=(
            "Doc and info modal say 'per 90'; the code divides by matches. In "
            "Style Evolution this KPI is labelled 'Patient Attack' (A1–A3 labels "
            "are rotated there)."
        ),
        source_doc=D_WHEEL,
        season_aggregation="rank_percentile",
    ),
    metric(
        id="ps_patient_attack",
        name="Patient Attack",
        sections=[TO],
        module={TO: WHEEL},
        short_definition="How few shots the team takes per 100 touches in the final third (A2).",
        formula="raw = non-penalty shots ÷ final-third touches × 100; wheel = 100 − percentile",
        unit="percentile",
        reading="contextual",
        reading_note="Percentile is inverted: higher means fewer shots per final-third touch (more patient).",
        methodology=md(
            "Non-penalty shots from shots_{season}.parquet ÷ team events at "
            "x ≥ 66.67 (any event type), × 100, season totals.",
            SEASON_RATIO,
            _WHEEL_PCT,
        ),
        notes=(
            "Own-goal rows in the shots parquet are counted as shots. In Style "
            "Evolution the A2 chart is labelled 'Shot Quality'."
        ),
        source_doc=D_WHEEL,
        season_aggregation="rank_percentile",
    ),
    metric(
        id="ps_shot_quality",
        name="Shot Quality",
        sections=[TO],
        module={TO: WHEEL},
        short_definition="Average non-penalty xG per shot the team takes (A3).",
        formula="raw = Σ non-penalty xG ÷ non-penalty shots",
        unit="percentile",
        reading="higher_better",
        reading_note="Higher means the team shoots from better positions on average.",
        methodology=md(
            "Non-penalty xG ÷ non-penalty shots, season totals, from "
            "shots_{season}.parquet.",
            SEASON_RATIO,
            _WHEEL_PCT,
        ),
        notes=(
            "Own-goal rows (xG 0) are counted as shots and slightly lower the value. "
            "In Style Evolution the A3 chart is labelled 'Chance Creation'."
        ),
        source_doc=D_WHEEL,
        season_aggregation="rank_percentile",
    ),
    # ── Pressing Intensity ───────────────────────────────────────────────────
    metric(
        id="ppda_team_overview",
        name="PPDA",
        sections=[TO],
        module={TO: PRESSING},
        short_definition="Passes the opponent completes in its own 60% of the pitch for every ball recovery the team makes there, over the season.",
        formula="opponent passes with x_from_own_goal ≤ 60 ÷ team ball recoveries with x_from_own_goal ≥ 40",
        unit="ratio",
        reading="lower_better",
        reading_note="Fewer opponent passes per recovery means more intense pressing.",
        methodology=md(
            _TWO_PPDA,
            "Computed by ppda.compute_ppda() over the season's pooled event table "
            "(ppda_{season}.parquet). Numerator: every opponent `pass` event (any "
            "outcome) made within 60 units of the opponent's own goal. "
            "Denominator: the pressing team's `ball recovery` events at ≥ 40 units "
            "from its own goal, i.e. in the same area. PPDA = passes ÷ recoveries, "
            "2 dp; teams without recoveries are omitted.",
            SEASON_RATIO,
            "Shown as the PPDA KPI (green below the league median, red above), "
            "the 'PPDA Ranking — Pressing Intensity' bar chart and the y-axis of "
            "'PPDA vs Field Tilt' (quadrants split at the league medians).",
            _FRAME_ISSUE,
        ),
        notes=(
            "Not comparable with Match/Opponent Analysis PPDA (different "
            "denominator) or with the wheel's Defensive Intensity."
        ),
        source_doc=D_PPDA_TO,
        season_aggregation="season_events",
    ),
    metric(
        id="ppda_rank",
        name="PPDA Rank",
        sections=[TO],
        module={TO: PRESSING},
        short_definition="The team's league position when all teams are ordered from lowest to highest Team Overview PPDA.",
        formula="rank of PPDA ascending (1 = lowest PPDA)",
        unit="rank",
        reading="lower_better",
        reading_note="1st means the most intense pressing in the league.",
        methodology=md(
            "ppda.build_ppda_table() sorts teams by PPDA ascending and numbers "
            "them 1…N. Colour: green in the top third, orange in the middle "
            "third, red in the bottom third.",
            _TWO_PPDA,
        ),
        source_doc=D_PPDA_TO,
        season_aggregation="rank_percentile",
    ),
    metric(
        id="field_tilt_pct",
        name="Field Tilt %",
        sections=[TO],
        module={TO: PRESSING},
        short_definition="The team's average share of the final-third passes played in its matches.",
        formula="mean over matches of team final-third passes ÷ both teams' final-third passes × 100",
        unit="%",
        reading="contextual",
        reading_note="Above 50% means the team plays more in the opponent's third than it concedes in its own.",
        methodology=md(
            "Per match: team passes with x_from_own_goal > 66.67 ÷ all such passes "
            "by both teams × 100 (ppda.compute_field_tilt()). The season value is "
            "the mean of these per-match tilts.",
            SEASON_MEAN_DEVIATION,
            "Shown as a KPI (green above the league median) and as the x-axis of "
            "'PPDA vs Field Tilt'.",
            _FRAME_ISSUE,
        ),
        notes=(
            "Not the same number as the wheel's 'Field Tilt' (G3), which is a "
            "ratio of season sums in the team-relative frame."
        ),
        source_doc=D_PPDA_TO,
        season_aggregation="mean_of_match_values",
    ),
    metric(
        id="pressing_tier",
        name="Pressing Tier",
        sections=[TO],
        module={TO: PRESSING},
        short_definition="A five-level label (Elite to Passive) from the team's PPDA rank.",
        formula="pct = (1 − (rank − 1) ÷ (N − 1)) × 100; ≥80 Elite, ≥60 High, ≥40 Medium, ≥20 Low, else Passive",
        unit="category",
        reading="contextual",
        reading_note="Elite = most intense pressing by Team Overview PPDA.",
        methodology=md(
            "Derived only from PPDA Rank: rank is converted to a 0–100 percentile "
            "(1st = 100) and bucketed into Elite / High / Medium / Low / Passive at "
            "80 / 60 / 40 / 20.",
            _TWO_PPDA,
        ),
        notes="No methodology document describes the tier thresholds.",
        source_doc=None,
        status="needs_review",
        season_aggregation="rank_percentile",
    ),
]
