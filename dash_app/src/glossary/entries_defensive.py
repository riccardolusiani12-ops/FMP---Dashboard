"""
Glossary entries for the defensive phase: pressing, defensive castle and
chances conceded (Match Analysis per match, Opponent Analysis per season).
"""

from __future__ import annotations

from src.glossary._common import (
    COORDS, CORRIDORS, D_CASTLE, D_CCON, D_OA_CCON, D_OA_PRESS,
    D_ORIGIN, D_PRESS, D_STRUCT, D_TIERS, GRID_18, MODAL_PER_MATCH, MODAL_RATE,
    MODAL_TOTALS, PENALTY_XG_TEXT, PER_MATCH, ROW_XG_NOTE, SEASON_RATIO, THIRDS,
    md, metric,
)

MA = "match_analysis"
OA = "opponent_analysis"
MA_PRESS = "Defensive Phase — Pressure"
OA_PRESS = "Defensive Phase — Defensive Pressing"
MA_CASTLE = "Defensive Phase — Defensive Castle"
OA_CASTLE = "Defensive Phase — Defensive Castle"
MA_CCON = "Defensive Phase — Chances Conceded"
OA_CCON = "Defensive Phase — Chances Conceded"

_WIDE_SET = (
    "Defensive actions (wide set): Foul (type_id 4, committed side only, "
    "outcome 0), Tackle (7), Interception (8), Clearance (12), Aerial (44, "
    "excluding aerials at x ≥ 83.33, which are attacking headers in the "
    "opponent box), Challenge (45), Ball Recovery (49) and Blocked Pass (74), "
    "made by the team."
)
_NARROW_PPDA = (
    "**PPDA (Match / Opponent Analysis definition):** opponent passes ÷ the "
    "team's tackles + interceptions + fouls committed + challenges "
    "(type_id 7, 8, 4 with outcome 0, 45) in the same zone. Opponent passes are "
    "type_id 1 (Pass, any outcome), 2 (Offside Pass), 74 and type_id 1 throw-ins. "
    "Opponent x is mirrored into the pressing frame (x_att = 100 − x), so 'the "
    "opponent's own 60%' is x_att ≤ 60 and the matching team actions are at "
    "x ≥ 40. Clearances, aerials, ball recoveries and blocked passes are "
    "excluded from the denominator. A zero denominator gives no value."
)
_TWO_PPDA = (
    "**Two PPDA definitions (intentional, never merge):** this PPDA divides by "
    "tackles + interceptions + fouls committed + challenges; the Team Overview "
    "PPDA divides by ball recoveries. The two numbers are not comparable."
)
_PRESS_SUCCESS = (
    "For each wide-set action, the events in the next 10 s (same period, "
    "PRESS_SUCCESS_SEC) are scanned. Fouls committed and challenges always "
    "count as unsuccessful. Otherwise the press is successful if the last play "
    "event in the window belongs to the team, if the window contains no play "
    "event, or if the opponent's last event is a foul; it is unsuccessful if "
    "the opponent has the last play event."
)
_CASTLE_SET = (
    "Castle actions: the wide defensive set (fouls committed, tackles, "
    "interceptions, clearances, aerials except at x ≥ 83.33, challenges, ball "
    "recoveries, blocked passes) made in the team's defensive third (x < 33.33)."
)
_CASTLE_ZONES = (
    "Sub-zones: In Own Box = x ≤ 16.5 and 21 ≤ y ≤ 79; Wide Flanks = x ≤ 16.67 "
    "outside that box rectangle; Def. Third Edge = 16.67 < x < 33.33."
)
_CONCEDED = (
    "Conceded chances are produced by running the full Chance Creation "
    "analysis for the opponent (same xG model, origins and tiers), then "
    "mirroring shot coordinates into the defending team's frame "
    "(x → 100 − x, y → 100 − y). Own goals scored by the analysed team are "
    "included as 'Own Goal' rows (xG 0, counted as goals and shots)."
)


ENTRIES: list[dict] = [
    # ── Pressing ─────────────────────────────────────────────────────────────
    metric(
        id="total_defensive_actions",
        name="Total Defensive Actions",
        sections=[MA, OA],
        module={MA: MA_PRESS, OA: OA_PRESS},
        short_definition="All defensive actions the team made anywhere on the pitch.",
        formula="count of wide-set defensive actions",
        unit="count",
        reading="contextual",
        reading_note="Volume depends on how much the opponent has the ball; read with PPDA.",
        methodology=md(
            _WIDE_SET,
            "Opponent Analysis shows the season value as 'Actions / Match'. "
            + PER_MATCH + " " + MODAL_PER_MATCH,
        ),
        notes=(
            "The card subtitle lists tackles, interceptions, clearances, aerials and "
            "recoveries; fouls committed, challenges and blocked passes are also counted."
        ),
        source_doc=D_PRESS,
        season_aggregation="total_per_match",
    ),
    metric(
        id="ppda_final_third",
        name="PPDA (Final Third)",
        sections=[MA],
        module={MA: MA_PRESS},
        short_definition="Opponent passes in their own third for each tackle, interception, foul or challenge the team makes there.",
        formula="opp passes with x_att ≤ 33.33 ÷ team (tackles + interceptions + fouls + challenges) with x ≥ 66.67",
        unit="ratio",
        reading="lower_better",
        reading_note="Fewer passes allowed per action means a more intense high press.",
        methodology=md(
            _TWO_PPDA,
            _NARROW_PPDA,
            "This card shows the high-press zone variant (`ppda_high`): only "
            "opponent passes in their own defensive third and team actions in "
            "the team's attacking third. Colour: green ≤ 6, orange ≤ 10, red above.",
        ),
        notes=(
            "Match Analysis shows the final-third variant; Opponent Analysis "
            "shows the overall (60%) variant labelled 'PPDA'."
        ),
        source_doc=D_PRESS,
        season_aggregation=None,
    ),
    metric(
        id="ppda_defensive_actions",
        name="PPDA",
        sections=[OA],
        module={OA: OA_PRESS},
        short_definition="Opponent passes in their own 60% of the pitch for each tackle, interception, foul or challenge the team makes there, over the season.",
        formula="Σ opp passes with x_att ≤ 60 ÷ Σ team (tackles + interceptions + fouls + challenges) with x ≥ 40",
        unit="ratio",
        reading="lower_better",
        reading_note="Fewer passes allowed per action means more intense pressing.",
        methodology=md(
            _TWO_PPDA,
            _NARROW_PPDA,
            "This is the overall zone (`ppda_overall`). The subtitle shows the "
            "summed numerator and denominator.",
            SEASON_RATIO,
            "League comparison modal: ranks all 20 teams on the season PPDA.",
        ),
        notes="Same quantity as the raw value of the wheel's Defensive Intensity (D2).",
        source_doc=D_OA_PRESS,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="press_success_rate",
        name="Press Success Rate",
        sections=[MA, OA],
        module={MA: MA_PRESS, OA: OA_PRESS},
        short_definition="Share of the team's defensive actions after which it had the ball at the end of the next 10 seconds.",
        formula="successful defensive actions ÷ defensive actions × 100",
        unit="%",
        reading="higher_better",
        reading_note="Higher means defensive actions more often win the ball back.",
        methodology=md(
            _WIDE_SET,
            _PRESS_SUCCESS,
            "Labelled 'Press Success' in Match Analysis, with successful / total underneath.",
            SEASON_RATIO,
            MODAL_RATE,
        ),
        notes=(
            "Code comments describe a 5-second window; the constant used is 10 s. "
            "Success means the team has the last event in the window, not that it "
            "kept the ball for 10 s."
        ),
        source_doc=D_PRESS,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="offsides_provoked",
        name="Offsides Provoked",
        sections=[MA],
        module={MA: MA_PRESS},
        short_definition="Number of times the team caught an opponent offside.",
        formula="count of team Offside Provoked events (type_id 55)",
        unit="count",
        reading="contextual",
        reading_note="Reflects an active, high defensive line; a style trait.",
        methodology=md(
            "Opta logs Offside Provoked (type_id 55) on the last defender of the "
            "defending team. Computed in defensive_structure.py and shown in the "
            "Pressure card.",
        ),
        source_doc=D_STRUCT,
        season_aggregation=None,
    ),
    metric(
        id="offside_line_median",
        name="Offside Line (median)",
        sections=[MA],
        module={MA: MA_PRESS},
        short_definition="Median x-position at which the team's defensive line caught opponents offside.",
        formula="median x of team Offside Provoked events",
        unit="x (0–100)",
        reading="contextual",
        reading_note="Higher means the line steps up higher up the pitch.",
        methodology=md(
            "Median x of type_id 55 events (the last defender's position). Shown "
            "as 'N/A' when no offside was provoked, and drawn as a purple dotted "
            "line on the pitch maps.",
            COORDS,
        ),
        notes="Only sampled when an offside is provoked; small samples are noisy.",
        source_doc=D_STRUCT,
        season_aggregation=None,
    ),
    metric(
        id="pressing_line_median",
        name="Pressing Line (median)",
        sections=[MA, OA],
        module={MA: MA_PRESS, OA: OA_PRESS},
        short_definition="Median x-position of the team's defensive actions — how high up the pitch it defends.",
        formula="median x of wide-set defensive actions",
        unit="x (0–100)",
        reading="contextual",
        reading_note="Higher means the team defends further up the pitch.",
        methodology=md(
            _WIDE_SET,
            "Match Analysis draws it as the white dotted line on the pitch maps. "
            "Opponent Analysis shows the season value, which is the median of the "
            "per-match medians; the modal ranks all teams on that value.",
            COORDS,
        ),
        source_doc=D_PRESS,
        season_aggregation="median_of_match_values",
    ),
    metric(
        id="defensive_actions_by_third",
        name="Defensive Actions",
        sections=[MA, OA],
        module={MA: MA_PRESS, OA: OA_PRESS},
        short_definition="How the team's defensive actions split between its own, middle and final thirds.",
        formula="actions per third ÷ all defensive actions × 100",
        unit="%",
        reading="contextual",
        reading_note="More final-third actions means a higher press.",
        methodology=md(
            _WIDE_SET,
            THIRDS + " Final third = High Press, middle = Mid Press, own = Low Block.",
            "Opponent Analysis shows this as 'Actions by Zone' with season "
            "counts summed; the three modals rank all teams on each third's share.",
            SEASON_RATIO,
        ),
        source_doc=D_PRESS,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="pressing_direction",
        name="Pressing Direction",
        sections=[MA, OA],
        module={MA: MA_PRESS, OA: OA_PRESS},
        short_definition="How the team's defensive actions split between the left, central and right corridors.",
        formula="actions per corridor ÷ defensive actions × 100",
        unit="%",
        reading="contextual",
        reading_note="Shows which side the team presses or is pressed into.",
        methodology=md(_WIDE_SET, CORRIDORS, SEASON_RATIO),
        source_doc=D_PRESS,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="press_success_by_zone",
        name="Pressing Success by Zone",
        sections=[MA, OA],
        module={MA: MA_PRESS, OA: OA_PRESS},
        short_definition="Press success rate separately for high, mid and low defensive actions.",
        formula="successful ÷ actions × 100 within each third",
        unit="%",
        reading="higher_better",
        reading_note="Shows where on the pitch the team's defending wins the ball back.",
        methodology=md(
            _PRESS_SUCCESS,
            THIRDS,
            "Labelled 'Press Success by Zone' in Opponent Analysis.",
            SEASON_RATIO,
        ),
        source_doc=D_PRESS,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="defensive_action_density",
        name="Action Density + Press Outcomes",
        sections=[MA, OA],
        module={MA: MA_PRESS, OA: OA_PRESS},
        short_definition="Pitch map of where the team's defensive actions happened and whether each press succeeded.",
        formula="count of wide-set actions per 18-zone cell; markers = successful / unsuccessful presses",
        unit="map",
        reading="contextual",
        reading_note="Darker zones mean more defensive activity.",
        methodology=md(
            _WIDE_SET, GRID_18,
            "Zone fill = action count; filled/green markers = successful presses, "
            "open/red = unsuccessful (see Press Success Rate). Season maps sum the "
            "zone counts and press outcomes across matches.",
        ),
        source_doc=D_PRESS,
        season_aggregation="sum",
    ),
    metric(
        id="defensive_actions_by_type",
        name="Defensive Actions by Type",
        sections=[MA],
        module={MA: MA_PRESS},
        short_definition="The team's defensive actions split by event type.",
        formula="count per type: Tackle, Interception, Foul, Ball Recovery, Clearance, Aerial, Challenge, Blocked Pass",
        unit="count",
        reading="contextual",
        reading_note="Describes how the team defends.",
        methodology=md(_WIDE_SET),
        source_doc=D_PRESS,
        season_aggregation=None,
    ),
    # ── Defensive Castle ─────────────────────────────────────────────────────
    metric(
        id="castle_actions",
        name="Def. Actions in 1st Third",
        sections=[MA, OA],
        module={MA: MA_CASTLE, OA: OA_CASTLE},
        short_definition="Defensive actions the team made in its own defensive third.",
        formula="count of castle actions with x < 33.33",
        unit="count",
        reading="contextual",
        reading_note="High values mean the team spends a lot of time defending deep.",
        methodology=md(
            _CASTLE_SET,
            "Opponent Analysis shows the per-match value with the season total "
            "underneath. " + PER_MATCH + " " + MODAL_PER_MATCH,
        ),
        source_doc=D_CASTLE,
        season_aggregation="total_per_match",
    ),
    metric(
        id="castle_in_own_box",
        name="In Own Box",
        sections=[MA, OA],
        module={MA: MA_CASTLE, OA: OA_CASTLE},
        short_definition="Defensive-third actions made inside the team's own penalty area.",
        formula="castle actions with x ≤ 16.5 and 21 ≤ y ≤ 79",
        unit="count",
        reading="contextual",
        reading_note="High values mean opponents often get into the box.",
        methodology=md(
            _CASTLE_SET, _CASTLE_ZONES,
            "Match Analysis shows the share of castle actions; Opponent Analysis "
            "the per-match value. " + MODAL_PER_MATCH,
        ),
        source_doc=D_CASTLE,
        season_aggregation="total_per_match",
    ),
    metric(
        id="castle_wide_flanks",
        name="Wide Flanks",
        sections=[MA, OA],
        module={MA: MA_CASTLE, OA: OA_CASTLE},
        short_definition="Defensive-third actions in the deep wide areas beside the box.",
        formula="castle actions with x ≤ 16.67 outside the box rectangle",
        unit="count",
        reading="contextual",
        reading_note="High values mean the team is often forced to defend deep wide areas.",
        methodology=md(
            _CASTLE_SET, _CASTLE_ZONES,
            "Match Analysis shows the share of castle actions; Opponent Analysis "
            "the per-match value. " + MODAL_PER_MATCH,
        ),
        source_doc=D_CASTLE,
        season_aggregation="total_per_match",
    ),
    metric(
        id="castle_def_third_edge",
        name="Def. Third Edge",
        sections=[MA, OA],
        module={MA: MA_CASTLE, OA: OA_CASTLE},
        short_definition="Defensive-third actions in the band between the box and the edge of the defensive third.",
        formula="castle actions with 16.67 < x < 33.33",
        unit="count",
        reading="contextual",
        reading_note="High values mean the team screens in front of its box.",
        methodology=md(
            _CASTLE_SET, _CASTLE_ZONES,
            "Match Analysis shows the share of castle actions; Opponent Analysis "
            "the per-match value. " + MODAL_PER_MATCH,
        ),
        notes="The UI subtitle '17–33 m line' quotes Opta units (≈ 17.5–35 m).",
        source_doc=D_CASTLE,
        season_aggregation="total_per_match",
    ),
    metric(
        id="castle_actions_by_type",
        name="Actions by Type",
        sections=[MA, OA],
        module={MA: MA_CASTLE, OA: OA_CASTLE},
        short_definition="The team's defensive-third actions split by event type.",
        formula="count per type of castle actions",
        unit="count",
        reading="contextual",
        reading_note="Shows reliance on clearances versus tackles and interceptions.",
        methodology=md(_CASTLE_SET, "Season counts are summed across matches; the top action is highlighted."),
        source_doc=D_CASTLE,
        season_aggregation="sum",
    ),
    metric(
        id="castle_corridor",
        name="Defensive Corridor",
        sections=[MA, OA],
        module={MA: MA_CASTLE, OA: OA_CASTLE},
        short_definition="How the team's defensive-third actions split between the left, central and right corridors.",
        formula="castle actions per corridor ÷ castle actions × 100",
        unit="%",
        reading="contextual",
        reading_note="Shows which side opponents attack the team's low block.",
        methodology=md(_CASTLE_SET, CORRIDORS, "Labelled 'Defensive Corridors' in Opponent Analysis.", SEASON_RATIO),
        source_doc=D_CASTLE,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="castle_zone_density",
        name="Zone Action Density — Defensive Third",
        sections=[MA, OA],
        module={MA: MA_CASTLE, OA: OA_CASTLE},
        short_definition="Pitch map of defensive-third actions per zone.",
        formula="castle actions per zone Z1–Z6",
        unit="map",
        reading="contextual",
        reading_note="Darker zones mean more deep defending there.",
        methodology=md(_CASTLE_SET, GRID_18, "Season maps sum the zone counts across matches."),
        source_doc=D_CASTLE,
        season_aggregation="sum",
    ),
    # ── Chances Conceded ─────────────────────────────────────────────────────
    metric(
        id="shots_faced",
        name="Total Shots Faced",
        sections=[MA, OA],
        module={MA: MA_CCON, OA: OA_CCON},
        short_definition="All attempts at goal the opponent made against the team, including penalties.",
        formula="count of opponent shots (type_id 13–16) + own goals by the team",
        unit="count",
        reading="lower_better",
        reading_note="Fewer shots faced means the opponent got fewer attempts.",
        methodology=md(
            _CONCEDED,
            "Opponent Analysis shows the season value as 'Shots / Match'. "
            + PER_MATCH + " " + MODAL_PER_MATCH,
        ),
        source_doc=D_CCON,
        season_aggregation="total_per_match",
    ),
    metric(
        id="shots_faced_in_box",
        name="In-Box",
        sections=[MA],
        module={MA: MA_CCON},
        short_definition="Opponent shots taken from inside the team's penalty box.",
        formula="conceded shots inside the box; subtitle = ÷ shots faced × 100",
        unit="count",
        reading="lower_better",
        reading_note="Fewer box shots conceded means the team keeps opponents away from goal.",
        methodology=md(
            _CONCEDED,
            "In the box = the shot location (opponent's attacking frame) is in "
            "x ≥ 83.33 and 21.1 ≤ y ≤ 78.9.",
        ),
        source_doc=D_CCON,
        season_aggregation=None,
    ),
    metric(
        id="shots_faced_out_box",
        name="Out-Box",
        sections=[MA],
        module={MA: MA_CCON},
        short_definition="Opponent shots taken from outside the team's penalty box.",
        formula="shots faced − In-Box shots faced; subtitle = ÷ shots faced × 100",
        unit="count",
        reading="contextual",
        reading_note="A high share means opponents are kept to long-range attempts.",
        methodology=md(_CONCEDED, "Complement of In-Box (Chances Conceded)."),
        source_doc=D_CCON,
        season_aggregation=None,
    ),
    metric(
        id="sot_faced_pct",
        name="SoT Faced %",
        sections=[MA],
        module={MA: MA_CCON},
        short_definition="Share of the opponent's shots that were on target.",
        formula="opponent shots with type_id 15 or 16 ÷ shots faced × 100",
        unit="%",
        reading="lower_better",
        reading_note="Lower means fewer opponent shots tested the goalkeeper.",
        methodology=md(_CONCEDED, "On target as in 'SoT %' (Chance Creation)."),
        source_doc=D_CCON,
        season_aggregation=None,
    ),
    metric(
        id="on_target_conceded_per_match",
        name="On Target / Match",
        sections=[OA],
        module={OA: OA_CCON},
        short_definition="Opponent shots on target per match over the season.",
        formula="Σ conceded shots on target (or goals) ÷ matches played",
        unit="per match",
        reading="lower_better",
        reading_note="Fewer shots on target conceded is better.",
        methodology=md(_CONCEDED, PER_MATCH, MODAL_PER_MATCH),
        source_doc=D_OA_CCON,
        season_aggregation="total_per_match",
    ),
    metric(
        id="xg_conceded",
        name="xG Against",
        sections=[MA, OA],
        module={MA: MA_CCON, OA: OA_CCON},
        short_definition="Summed expected goals of the shots the opponent took against the team.",
        formula="Σ xG of conceded shots",
        unit="xG",
        reading="lower_better",
        reading_note="Lower means the team allowed fewer and worse chances.",
        methodology=md(
            _CONCEDED,
            PENALTY_XG_TEXT,
            ROW_XG_NOTE,
            "Match Analysis subtitle: xG per shot faced. Opponent Analysis shows "
            "the season value as 'xG Conceded / Match'. " + PER_MATCH + " "
            + MODAL_PER_MATCH,
        ),
        notes="Includes penalty xG; this per-match value is also the raw input of the wheel's Chance Prevention (D1).",
        source_doc=D_CCON,
        season_aggregation="total_per_match",
    ),
    metric(
        id="big_chances_conceded",
        name="Big chances",
        sections=[MA, OA],
        module={MA: MA_CCON, OA: OA_CCON},
        short_definition="Opponent shots flagged by Opta as big chances that were not scored.",
        formula="count of conceded shots in quality tier 2",
        unit="count",
        reading="lower_better",
        reading_note="Fewer big chances conceded is better.",
        methodology=md(
            _CONCEDED,
            "Tier 2 = Opta `Big Chance` qualifier and not a goal (a scored big "
            "chance is tier 3). Match Analysis shows it under Goals Conceded; "
            "Opponent Analysis as 'Big Chances / Match'. " + PER_MATCH + " "
            + MODAL_PER_MATCH,
        ),
        source_doc=D_CCON,
        season_aggregation="total_per_match",
    ),
    metric(
        id="chain_to_concede_matrix",
        name="Chain-to-Concede Matrix",
        sections=[MA],
        module={MA: MA_CCON},
        short_definition="A table of the opponent's shots by attack origin, showing count, xG, SoT% and goals conceded for each origin.",
        formula="per origin: N, xG, SoT%, GC (goals conceded)",
        unit="table",
        reading="contextual",
        reading_note="Shows which opponent patterns hurt the team.",
        methodology=md(
            _CONCEDED,
            "Identical to the Chain-to-Goal Matrix of the opponent, with the GS row "
            "renamed GC.",
        ),
        source_doc=D_CCON,
        season_aggregation=None,
    ),
    metric(
        id="attack_origin_conceded",
        name="Attack Origin Breakdown",
        sections=[MA, OA],
        module={MA: MA_CCON, OA: OA_CCON},
        short_definition="How each shot the team conceded was created, in the seven attack-origin categories.",
        formula="classify_attack_origin() applied to the opponent's shots",
        unit="distribution",
        reading="contextual",
        reading_note="Shows the patterns the team is most vulnerable to.",
        methodology=md(
            _CONCEDED,
            "Origins and priority as in Chance Creation's 'Attack Origin "
            "Breakdown' (Through Ball → Set Piece → Individual Play → High Regain "
            "→ Cut Back → Cross → Combination), with conceded penalties on their "
            "own Penalty card. Opponent Analysis shows the season counts as "
            "'Origin of Chances Conceded' with goals conceded and conversion.",
        ),
        notes=(
            "Both captions list the priority as 'Set Piece → High Regain → Cross → "
            "Through Ball → Cut Back → Combination', which is not the code order."
        ),
        source_doc=D_ORIGIN,
        season_aggregation="sum",
    ),
    metric(
        id="xg_against_by_origin",
        name="xG Against by Attack Origin",
        sections=[MA],
        module={MA: MA_CCON},
        short_definition="The xG the team conceded, split by the opponent's attack origin.",
        formula="Σ xG of conceded shots per origin",
        unit="xG",
        reading="lower_better",
        reading_note="Lower xG conceded from a pattern means it is well defended.",
        methodology=md(_CONCEDED),
        source_doc=D_CCON,
        season_aggregation=None,
    ),
    metric(
        id="shot_origin_zones_defensive",
        name="Shot Origin Zones — Defensive Frame",
        sections=[MA, OA],
        module={MA: MA_CCON, OA: OA_CCON},
        short_definition="Pitch map of where the opponent's shots against the team were taken.",
        formula="conceded shots per 18-zone cell (defending frame)",
        unit="map",
        reading="contextual",
        reading_note="Shows the areas opponents shoot from.",
        methodology=md(_CONCEDED, GRID_18, "Season maps sum the zone counts across matches."),
        source_doc=D_CCON,
        season_aggregation="sum",
    ),
    metric(
        id="shot_quality_tiers_conceded",
        name="Shot Quality Tiers Conceded",
        sections=[MA, OA],
        module={MA: MA_CCON, OA: OA_CCON},
        short_definition="The opponent's shots split into Converted, Big Chance and Speculative.",
        formula="tiers as in Shot Quality Tiers, applied to conceded shots",
        unit="distribution",
        reading="contextual",
        reading_note="Fewer Converted and Big Chance shots conceded is better.",
        methodology=md(_CONCEDED, "Tier rules as in Chance Creation's 'Shot Quality Tiers'.", SEASON_RATIO),
        source_doc=D_TIERS,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="clean_sheets",
        name="Clean Sheets",
        sections=[OA],
        module={OA: OA_CCON},
        short_definition="League matches in which the team conceded no goals.",
        formula="matches with 0 goals against on the scoreline; subtitle = ÷ matches played × 100",
        unit="count",
        reading="higher_better",
        reading_note="More clean sheets is better.",
        methodology=md(
            "Read from the season match results: a home match with away goals = 0 "
            "or an away match with home goals = 0. Scoreline goals, so own goals "
            "count against the team. The subtitle shows clean sheets / matches "
            "played and the percentage.",
            MODAL_TOTALS + " Ties are ordered alphabetically.",
        ),
        source_doc=D_OA_CCON,
        season_aggregation="sum",
    ),
]
