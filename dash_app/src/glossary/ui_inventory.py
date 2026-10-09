"""
UI metric inventory (Phase 0.2 of the glossary audit).

Every metric label rendered in Team Overview, Match Analysis and Opponent
Analysis, with the registry id that defines it. The same label can appear in
several modules and map to different ids (e.g. "Goals"), so rows carry the
module. Visual elements that are not metrics are listed in ``UNMAPPED`` with
the reason, so the validation test can prove nothing was silently skipped.

Row format: (label as shown, section, module, file rendering it, registry id)
"""

from __future__ import annotations

TO, MA, OA = "team_overview", "match_analysis", "opponent_analysis"
_C = "dash_app/src/components/"
_CB = "dash_app/src/callbacks/"

# Files
TD = _CB + "team_detail_callbacks.py"
TD_PAGE = "dash_app/src/pages/team_detail.py"
STANDINGS = "dash_app/src/analytics/multi_season_standings.py"
PPDA_FIG = "dash_app/src/analytics/ppda.py"
PS = _C + "playing_style_cards.py"
PSE = _C + "playing_style_evolution_cards.py"
GK = _C + "buildup_cards.py"
FT = _C + "final_third_cards.py"
CC = _C + "chance_creation_cards.py"
PRESS = _C + "defensive_pressing_cards.py"
CASTLE = _C + "defensive_castle_cards.py"
CCON = _C + "chance_conceded_cards.py"
OFF_T = _C + "offensive_transition_cards.py"
DEF_T = _C + "defensive_structure_cards.py"
SP = _C + "set_piece_cards.py"
PLAYER = _C + "player_analysis_cards.py"
OA_OFF = _C + "opponent_offensive_phase.py"
OA_PRESS = _C + "opp_season_pressing_cards.py"
OA_CASTLE = _C + "opp_season_castle_cards.py"
OA_CCON = _C + "opp_season_chances_conceded_cards.py"
OA_TRANS = _C + "opp_season_transitions_cards.py"
OA_CORNERS = _C + "opp_season_corner_kicks_cards.py"
OA_PLAYER = _C + "opp_season_player_cards.py"

# Module names (as used in the registry)
TO_KPI = "KPI Row"
TO_POINTS = "Points Progression"
TO_FORM = "Most-Used Formations"
TO_PERF = "Offensive Production and Defensive Efficiency"
TO_WHEEL = "Playing Style Wheel · Style Evolution"
TO_PRESS = "Pressing Intensity"
MA_GK = "Offensive Phase — Build-up from Goal Kicks"
MA_FT = "Offensive Phase — Build-up to Final Third"
MA_CC = "Offensive Phase — Chance Creation"
MA_PRESS = "Defensive Phase — Pressure"
MA_CASTLE = "Defensive Phase — Defensive Castle"
MA_CCON = "Defensive Phase — Chances Conceded"
MA_OFF_T = "Transitions — Offensive Transition"
MA_DEF_T = "Transitions — Defensive Transition"
MA_CORNERS = "Set Pieces — Corner Kicks"
MA_FK = "Set Pieces — Free Kicks"
PA = "Player Analysis"
OA_GK = "Offensive Phase — GK Build-up"
OA_FT = "Offensive Phase — Build-up to Final Third"
OA_CC = "Offensive Phase — Chance Creation"
OA_PRESS_M = "Defensive Phase — Defensive Pressing"
OA_CASTLE_M = "Defensive Phase — Defensive Castle"
OA_CCON_M = "Defensive Phase — Chances Conceded"
OA_OFF_T = "Transitions — Offensive Transitions"
OA_DEF_T = "Transitions — Defensive Transitions"
OA_CORNERS_M = "Set Pieces — Corner Kicks"


def _rows(section: str, module: str, file: str, pairs: list[tuple[str, str]]) -> list[tuple]:
    return [(label, section, module, file, mid) for label, mid in pairs]


_WHEEL_FULL = [
    ("Chance Prevention", "ps_chance_prevention"),
    ("Defensive Intensity", "ps_defensive_intensity"),
    ("High Line", "ps_high_line"),
    ("Deep Build-up", "ps_deep_buildup"),
    ("Press Resistance", "ps_press_resistance"),
    ("Possession", "ps_possession"),
    ("Central Progression", "ps_central_progression"),
    ("Circulate", "ps_circulate"),
    ("Field Tilt", "ps_field_tilt"),
    ("Chance Creation", "ps_chance_creation"),
    ("Patient Attack", "ps_patient_attack"),
    ("Shot Quality", "ps_shot_quality"),
]

_GK_TIERS = [
    ("Established Possession", "gk_p1_established_possession"),
    ("Reached Final Third", "gk_p2_reached_final_third"),
    ("Created a Shot", "gk_p3_created_shot"),
    ("Possession Lost", "gk_n1_possession_lost"),
    ("Box Entry Conceded", "gk_n2_box_entry_conceded"),
    ("Shot Conceded", "gk_n3_shot_conceded"),
]

_ORIGINS = [
    "Set Piece", "High Regain", "Cross", "Through Ball", "Cut Back",
    "Individual Play", "Combination",
]

_PLAYER_KPIS = [
    ("Passes Completed", "passes_completed"),
    ("Pass Completion %", "pass_completion_pct"),
    ("Ball Progressions", "ball_progressions"),
    ("Line Breaks", "line_breaks"),
    ("Switches of Play", "switches_of_play"),
    ("Crosses Completed", "crosses_completed"),
    ("Take-Ons", "take_ons"),
    ("Attempts at Goal", "attempts_at_goal"),
    ("Goals", "player_goals"),
    ("Tackles Won", "tackles_won"),
    ("Tackles Made", "tackles_made"),
    ("Interceptions", "interceptions"),
    ("Blocks", "blocks"),
    ("Clearances", "clearances"),
    ("Aerial Duels Won", "aerial_duels_won"),
    ("Possession Regains", "possession_regains"),
]

UI_METRICS: list[tuple] = [
    # ══ TEAM OVERVIEW ════════════════════════════════════════════════════════
    *_rows(TO, TO_KPI, TD, [
        ("Position", "league_position"),
        ("Season Record", "season_record"),
        ("Last 5", "last_5_form"),
        ("Goal Diff.", "goal_difference"),
        ("PPG", "points_per_game"),
        ("Mean Age", "mean_age"),
    ]),
    *_rows(TO, TO_POINTS, TD_PAGE, [("Points Progression", "points_progression")]),
    *_rows(TO, TO_POINTS, STANDINGS, [("Cumulative Points", "points_progression")]),
    *_rows(TO, TO_FORM, TD, [
        ("Times Used", "formation_times_used"),
        ("Share", "formation_share"),
        ("Starts", "starts"),
        ("Minutes", "lineup_minutes"),
        ("Avg Min", "lineup_avg_minutes"),
    ]),
    *_rows(TO, TO_PERF, TD, [
        ("Goals Scored", "goals_scored"),
        ("Goals Conceded", "goals_conceded"),
        ("xG", "xg_for"),
        ("xGC", "xg_against"),
        ("Expected (xG)", "xg_for"),
    ]),
    *_rows(TO, TO_PERF, TD_PAGE, [
        ("Goals Scored — League Comparison", "goals_scored"),
        ("Goals Conceded — League Comparison", "goals_conceded"),
        ("xG For — League Comparison", "xg_for"),
        ("xGC Against — League Comparison", "xg_against"),
        ("Goals Scored — 15-Minute Intervals", "goals_scored_by_interval"),
        ("Goals Conceded — 15-Minute Intervals", "goals_conceded_by_interval"),
    ]),
    *_rows(TO, TO_WHEEL, PS, _WHEEL_FULL + [
        ("Intensity", "ps_defensive_intensity"),
        ("Central Progr.", "ps_central_progression"),
    ]),
    *_rows(TO, TO_WHEEL, PSE, [
        (label, mid) for label, mid in _WHEEL_FULL if label != "Defensive Intensity"
    ] + [("Intensity", "ps_defensive_intensity")]),
    *_rows(TO, TO_PRESS, TD, [
        ("PPDA Rank", "ppda_rank"),
        ("PPDA", "ppda_team_overview"),
        ("Field Tilt %", "field_tilt_pct"),
        ("Pressing Tier", "pressing_tier"),
    ]),
    *_rows(TO, TO_PRESS, PPDA_FIG, [
        ("PPDA Ranking — Pressing Intensity", "ppda_team_overview"),
        ("PPDA vs Field Tilt", "ppda_team_overview"),
        ("Field Tilt % (higher = more attacking territory control)", "field_tilt_pct"),
    ]),

    # ══ MATCH ANALYSIS ═══════════════════════════════════════════════════════
    *_rows(MA, MA_GK, GK, [
        ("Total", "gk_possessions"),
        ("Short", "gk_short_pct"),
        ("Long", "gk_long_pct"),
        ("First Receiver Zone Distribution", "gk_first_receiver_zones"),
        ("Goal Kick — First Receiver Zones", "gk_first_receiver_zones"),
        ("Outcome Classification", "gk_outcome"),
        ("Positive", "gk_outcome"),
        ("Negative", "gk_outcome"),
    ] + _GK_TIERS),
    *_rows(MA, MA_FT, FT, [
        ("Possession %", "possession_pct"),
        ("POSSESSION BY TIME PERIOD", "possession_by_time_period"),
        ("POSSESSION BY PITCH AREA", "possession_by_pitch_area"),
        ("Qualifying Poss.", "qualifying_possessions"),
        ("Total FT Entries", "ft_entries_total"),
        ("Qual. FT Entries", "ft_entries_qualifying"),
        ("Opp. Box Touches", "opp_box_touches"),
        ("Tempo", "tempo"),
        ("Tempo — 15-Minute Windows", "tempo"),
        ("Entry by Corridor", "ft_entry_corridor"),
        ("How — Entry Method", "ft_entry_method"),
        ("Zone 14", "ft_zone14"),
        ("Flanks", "ft_flanks"),
        ("Entry Outcomes (Positive / Negative)", "ft_entry_outcome"),
        ("Outcomes by Corridor", "ft_entry_outcome"),
        ("Outcomes by Method", "ft_entry_outcome"),
        ("Entry Points — Method View", "ft_entry_map"),
        ("FT Entry Zones & Outcomes", "ft_entry_map"),
    ]),
    *_rows(MA, MA_CC, CC, [
        ("Total Shots", "total_shots"),
        ("In-Box", "shots_in_box"),
        ("Out-Box", "shots_out_box"),
        ("SoT %", "sot_pct"),
        ("xG Total", "xg_total"),
        ("xG/Shot", "xg_per_shot"),
        ("Goals", "team_goals"),
        ("Chain-to-Goal Matrix", "chain_to_goal_matrix"),
        ("Attack Origin Breakdown", "attack_origin"),
        *[(o, "attack_origin") for o in _ORIGINS],
        ("Penalty", "penalty_card"),
        ("Shot Quality Tiers", "shot_quality_tiers"),
        ("Converted", "shot_quality_tiers"),
        ("Big Chance", "shot_quality_tiers"),
        ("Speculative", "shot_quality_tiers"),
        ("xG by Attack Origin", "xg_by_origin"),
        ("Attack Origin Zones", "attack_origin_zones"),
    ]),
    *_rows(MA, MA_PRESS, PRESS, [
        ("Total Defensive Actions", "total_defensive_actions"),
        ("PPDA (Final Third)", "ppda_final_third"),
        ("Press Success", "press_success_rate"),
        ("Offsides Provoked", "offsides_provoked"),
        ("Offside Line (median)", "offside_line_median"),
        ("Pressing line", "pressing_line_median"),
        ("Defensive Actions", "defensive_actions_by_third"),
        ("Final Third", "defensive_actions_by_third"),
        ("Middle Third", "defensive_actions_by_third"),
        ("Own Third", "defensive_actions_by_third"),
        ("High Press", "defensive_actions_by_third"),
        ("Mid Press", "defensive_actions_by_third"),
        ("Low Block", "defensive_actions_by_third"),
        ("Pressing Direction", "pressing_direction"),
        ("Pressing Success by Zone", "press_success_by_zone"),
        ("Action Density + Press Outcomes", "defensive_action_density"),
        ("Defensive Actions by Type", "defensive_actions_by_type"),
    ]),
    *_rows(MA, MA_CASTLE, CASTLE, [
        ("Def. Actions in 1st Third", "castle_actions"),
        ("In Own Box", "castle_in_own_box"),
        ("Wide Flanks", "castle_wide_flanks"),
        ("Def. Third Edge", "castle_def_third_edge"),
        ("Actions by Type", "castle_actions_by_type"),
        ("Defensive Corridor", "castle_corridor"),
        ("Zone Action Density — Defensive Third", "castle_zone_density"),
    ]),
    *_rows(MA, MA_CCON, CCON, [
        ("Total Shots Faced", "shots_faced"),
        ("In-Box", "shots_faced_in_box"),
        ("Out-Box", "shots_faced_out_box"),
        ("SoT Faced %", "sot_faced_pct"),
        ("xG Against", "xg_conceded"),
        ("Goals Conceded", "goals_conceded"),
        ("Big chances", "big_chances_conceded"),
        ("Chain-to-Concede Matrix", "chain_to_concede_matrix"),
        ("Attack Origin Breakdown", "attack_origin_conceded"),
        ("Penalty", "attack_origin_conceded"),
        ("xG Against by Attack Origin", "xg_against_by_origin"),
        ("Shot Origin Zones — Defensive Frame", "shot_origin_zones_defensive"),
        ("Shot Quality Tiers Conceded", "shot_quality_tiers_conceded"),
    ]),
    *_rows(MA, MA_OFF_T, OFF_T, [
        ("Total Transitions", "off_total_transitions"),
        ("Qualified Transitions", "off_qualified_transitions"),
        ("Transition Rate", "off_transition_rate"),
        ("P1 — Sustained", "off_p1_sustained"),
        ("P2 — Threatening", "off_p2_threatening"),
        ("P3 — Dangerous", "off_p3_dangerous"),
        ("Outcomes by Zone", "off_outcomes_by_zone"),
        ("Outcomes by Corridor", "off_outcomes_by_corridor"),
        ("Offensive Transition Origins (Qualified · Own Half)", "off_transition_origins"),
    ]),
    *_rows(MA, MA_DEF_T, DEF_T, [
        ("Total Transitions", "def_total_transitions"),
        ("Qualified Transitions", "def_qualified_transitions"),
        ("Transition Rate", "def_transition_rate"),
        ("Immediate Press ≤5s", "immediate_press_rate"),
        ("Organised Drop >10s", "organised_drop_rate"),
        ("N1 — Sustained", "def_n1_sustained"),
        ("N2 — Threatening", "def_n2_threatening"),
        ("N3 — Dangerous", "def_n3_dangerous"),
        ("Outcomes by Zone", "def_outcomes_by_zone"),
        ("Outcomes by Corridor", "def_outcomes_by_corridor"),
        ("Transition Loss Origins (Qualified · Middle + Attacking Third)", "def_transition_origins"),
    ]),
    *_rows(MA, MA_CORNERS, SP, [
        ("Total Corners", "corners_total"),
        ("Goals", "corner_goals"),
        ("Shots on Target", "corner_shots_on_target"),
        ("Shots off Target", "corner_shots_off_target"),
        ("Cleared", "corner_cleared"),
        ("2nd Phase", "corner_second_phase"),
        ("Delivery Type", "corner_delivery_type"),
        ("Inswinger", "corner_delivery_type"),
        ("Outswinger", "corner_delivery_type"),
        ("Straight", "corner_delivery_type"),
        ("Delivery Maps", "corner_delivery_zones"),
        ("GA1", "corner_delivery_zones"),
        ("CA1", "corner_delivery_zones"),
        ("Edge", "corner_delivery_zones"),
        ("Front Zone", "corner_delivery_zones"),
        ("Back Zone", "corner_delivery_zones"),
    ]),
    *_rows(MA, MA_FK, SP, [
        ("Total Deliveries", "fk_total_deliveries"),
        ("FK Deliveries — Volume & Outcomes", "fk_delivery_outcomes"),
        # Same labels appear in both FK blocks (deliveries / direct shots).
        ("Goals", "fk_delivery_outcomes"),
        ("Shots on Target", "fk_delivery_outcomes"),
        ("Shots off Target", "fk_delivery_outcomes"),
        ("Hit Post", "fk_delivery_outcomes"),
        ("Goals", "fk_direct_shot_outcomes"),
        ("Shots on Target", "fk_direct_shot_outcomes"),
        ("Shots off Target", "fk_direct_shot_outcomes"),
        ("2nd Phase / Foul", "fk_delivery_outcomes"),
        ("Cleared / No Shot", "fk_delivery_outcomes"),
        ("Delivery Type", "fk_delivery_type"),
        ("Crossed into Box", "fk_delivery_type"),
        ("Chipped / Lofted", "fk_delivery_type"),
        ("Launch", "fk_delivery_type"),
        ("Landing Zone", "fk_delivery_type"),
        ("Total FK Shots", "fk_total_shots"),
        ("Direct FK Shots — Volume & Outcomes", "fk_direct_shot_outcomes"),
        ("Hit Post", "fk_direct_shot_outcomes"),
        ("Blocked", "fk_direct_shot_outcomes"),
        ("On Frame", "fk_direct_shot_outcomes"),
        ("Goalmouth zone (GK perspective)", "fk_direct_shot_outcomes"),
    ]),
    *_rows(MA, PA, PLAYER, _PLAYER_KPIS + [
        ("Offensive PVA", "offensive_pva"),
        ("Defensive PVA", "defensive_pva"),
        ("Total PVA", "total_pva"),
        ("PVA per 90", "total_pva"),
        ("Event Map — Possession Value Added", "offensive_pva"),
        ("Cumulative Possession Value", "cumulative_possession_value"),
        ("Value added", "cumulative_possession_value"),
        ("Value lost", "cumulative_possession_value"),
        ("Top Passer", "passes_completed"),
        ("Top Progressor", "ball_progressions"),
        ("Top Crosser", "crosses_completed"),
        ("Most Shots", "attempts_at_goal"),
        ("Top Tackler", "tackles_won"),
        ("Top Interceptor", "interceptions"),
        ("Top in Air", "aerial_duels_won"),
        ("Top Regains", "possession_regains"),
        ("Att", "passes_completed"),
        ("Cmp", "passes_completed"),
        ("LB Att", "line_breaks"),
        ("LB Cmp", "line_breaks"),
        ("LB %", "line_breaks"),
        ("Cross Att", "crosses_completed"),
        ("Cross Cmp", "crosses_completed"),
        ("Made", "tackles_made"),
        ("Contested", "aerial_duels_won"),
        ("Min", "season_minutes"),
    ]),

    # ══ OPPONENT ANALYSIS ════════════════════════════════════════════════════
    *_rows(OA, OA_GK, OA_OFF, [
        ("Matches", "matches_analysed"),
        ("GK Possessions", "gk_possessions"),
        ("Short Pass %", "gk_short_pct"),
        ("Long Ball %", "gk_long_pct"),
        ("% success (Short Pass)", "gk_short_success_rate"),
        ("% success (Long Ball)", "gk_long_success_rate"),
        ("GK Short-Pass Success Rate — All Teams", "gk_short_success_rate"),
        ("GK Long-Ball Success Rate — All Teams", "gk_long_success_rate"),
        ("Outcome Breakdown — Short Pass", "gk_outcome"),
        ("Outcome Breakdown — Long Ball", "gk_outcome"),
        ("Positive Rate", "gk_outcome"),
        ("GK Distribution End-Points", "gk_first_receiver_zones"),
    ] + _GK_TIERS),
    *_rows(OA, OA_FT, OA_OFF, [
        ("Possession %", "possession_pct"),
        ("Success Rate", "ft_success_rate"),
        ("Left Corridor", "ft_entry_corridor"),
        ("Central", "ft_entry_corridor"),
        ("Right Corridor", "ft_entry_corridor"),
        ("Opp. Box Touches", "opp_box_touches"),
        ("Opp. Box Touches / Match — League Ranking", "opp_box_touches"),
        ("Tempo", "tempo"),
        ("Top Method", "ft_top_method"),
        ("Entry Method Breakdown", "ft_entry_method"),
        ("Success Rate by Entry Method", "ft_success_rate"),
        ("Entry Timing — 15-min Bands", "ft_entry_timing"),
        ("Build-up Depth — Avg Passes Before Entry", "ft_build_depth"),
        ("FT Entry Points by Zone", "ft_entry_map"),
        ("Entry Points by Method — Season", "ft_entry_map"),
    ]),
    *_rows(OA, OA_CC, OA_OFF, [
        ("Total Chances", "total_shots"),
        ("Goals", "team_goals"),
        ("SoT:", "sot_pct"),
        ("xG Total", "xg_total"),
        ("xG per Match — All Teams", "xg_total"),
        ("Top Origin", "top_origin"),
        ("Matches", "matches_analysed"),
        ("Chances Created by Attack Origin", "attack_origin"),
        ("ATTACK ORIGIN BREAKDOWN", "attack_origin"),
        *[(o, "attack_origin") for o in _ORIGINS],
        ("Conv %", "origin_conversion_pct"),
        ("Penalty", "penalty_card"),
        ("Goal Types — Season", "goals_by_origin"),
        ("Attack Origin Zones", "attack_origin_zones"),
    ]),
    *_rows(OA, OA_PRESS_M, OA_PRESS, [
        ("Actions / Match", "total_defensive_actions"),
        ("Defensive Actions / Match — League Comparison", "total_defensive_actions"),
        ("PPDA", "ppda_defensive_actions"),
        ("PPDA — League Comparison", "ppda_defensive_actions"),
        ("Press Success Rate", "press_success_rate"),
        ("Press Success Rate — League Comparison", "press_success_rate"),
        ("Pressing Line (median)", "pressing_line_median"),
        ("Pressing Line (Median) — League Comparison", "pressing_line_median"),
        ("Actions by Zone", "defensive_actions_by_third"),
        ("High Press", "defensive_actions_by_third"),
        ("Mid Press", "defensive_actions_by_third"),
        ("Low Block", "defensive_actions_by_third"),
        ("Own Third — League Comparison", "defensive_actions_by_third"),
        ("Middle Third — League Comparison", "defensive_actions_by_third"),
        ("Final Third — League Comparison", "defensive_actions_by_third"),
        ("Pressing Direction", "pressing_direction"),
        ("Press Success by Zone", "press_success_by_zone"),
        ("Pitch Map — Action Density & Press Outcomes", "defensive_action_density"),
    ]),
    *_rows(OA, OA_CASTLE_M, OA_CASTLE, [
        ("Def. Actions in 1st Third", "castle_actions"),
        ("In Own Box", "castle_in_own_box"),
        ("Wide Flanks", "castle_wide_flanks"),
        ("Def. Third Edge", "castle_def_third_edge"),
        ("Def. Actions / Match — League Comparison", "castle_actions"),
        ("In Own Box / Match — League Comparison", "castle_in_own_box"),
        ("Wide Flanks / Match — League Comparison", "castle_wide_flanks"),
        ("Def. Third Edge / Match — League Comparison", "castle_def_third_edge"),
        ("Actions by Type", "castle_actions_by_type"),
        ("Defensive Corridors", "castle_corridor"),
        ("Pitch Map — Zone Action Density", "castle_zone_density"),
    ]),
    *_rows(OA, OA_CCON_M, OA_CCON, [
        ("Clean Sheets", "clean_sheets"),
        ("Clean Sheets — League Comparison", "clean_sheets"),
        ("Shots / Match", "shots_faced"),
        ("On Target / Match", "on_target_conceded_per_match"),
        ("Goals Conceded / Match", "goals_conceded"),
        ("Big Chances / Match", "big_chances_conceded"),
        ("xG Conceded / Match", "xg_conceded"),
        ("Shots / Match — League Comparison", "shots_faced"),
        ("On Target / Match — League Comparison", "on_target_conceded_per_match"),
        ("Goals Conceded / Match — League Comparison", "goals_conceded"),
        ("Big Chances / Match — League Comparison", "big_chances_conceded"),
        ("xG Conceded / Match — League Comparison", "xg_conceded"),
        ("Origin of Chances Conceded", "attack_origin_conceded"),
        ("ATTACK ORIGIN BREAKDOWN", "attack_origin_conceded"),
        ("Penalty", "attack_origin_conceded"),
        ("SHOT ORIGIN ZONES — DEFENSIVE FRAME", "shot_origin_zones_defensive"),
        ("SHOT QUALITY TIERS CONCEDED", "shot_quality_tiers_conceded"),
    ]),
    *_rows(OA, OA_OFF_T, OA_TRANS, [
        ("Transitions / Match", "off_total_transitions"),
        ("Qualifying / Match", "off_qualified_transitions"),
        ("Qualifying Rate", "off_transition_rate"),
        ("Transitions / Match — League Comparison", "off_total_transitions"),
        ("Qualifying Transitions / Match — League Comparison", "off_qualified_transitions"),
        ("Qualifying Rate — League Comparison", "off_transition_rate"),
        ("Outcome Distribution", "off_qualified_transitions"),
        ("P1 — Sustained", "off_p1_sustained"),
        ("P2 — Threatening", "off_p2_threatening"),
        ("P3 — Dangerous", "off_p3_dangerous"),
        ("Outcomes by Zone", "off_outcomes_by_zone"),
        ("Outcomes by Corridor", "off_outcomes_by_corridor"),
        ("Qualifying Transitions by Corridor", "off_outcomes_by_corridor"),
        ("Pitch Map — Transition Origins Density", "off_transition_origins"),
    ]),
    *_rows(OA, OA_DEF_T, OA_TRANS, [
        ("Transitions / Match", "def_total_transitions"),
        ("Qualifying / Match", "def_qualified_transitions"),
        ("Qualifying Rate", "def_transition_rate"),
        ("Transitions / Match — League Comparison", "def_total_transitions"),
        ("Qualifying Transitions / Match — League Comparison", "def_qualified_transitions"),
        ("Qualifying Rate — League Comparison", "def_transition_rate"),
        ("Immediate Press", "immediate_press_rate"),
        ("Organised Drop", "organised_drop_rate"),
        ("Immediate Press Rate — League Comparison", "immediate_press_rate"),
        ("Organised Drop Rate — League Comparison", "organised_drop_rate"),
        ("Outcome Distribution", "def_qualified_transitions"),
        ("N1 — Sustained", "def_n1_sustained"),
        ("N2 — Threatening", "def_n2_threatening"),
        ("N3 — Dangerous", "def_n3_dangerous"),
        ("Outcomes by Zone", "def_outcomes_by_zone"),
        ("Outcomes by Corridor", "def_outcomes_by_corridor"),
        ("Qualifying Transitions by Corridor", "def_outcomes_by_corridor"),
        ("Pitch Map — Transition Origins Density", "def_transition_origins"),
    ]),
    *_rows(OA, OA_CORNERS_M, OA_CORNERS, [
        ("Corners / Match", "corners_total"),
        ("Goals / Match", "corner_goals"),
        ("% conv.", "corner_conversion_rate"),
        ("Shots on Target / Match", "corner_shots_on_target"),
        ("Shots off Target / Match", "corner_shots_off_target"),
        ("Cleared / Match", "corner_cleared"),
        ("2nd Phase / Match", "corner_second_phase"),
        ("Corners / Match — League Comparison", "corners_total"),
        ("Corner Goals / Match — League Comparison", "corner_goals"),
        ("Shots on Target / Match — League Comparison", "corner_shots_on_target"),
        ("Shots off Target / Match — League Comparison", "corner_shots_off_target"),
        ("Cleared / Match — League Comparison", "corner_cleared"),
        ("2nd Phase / Match — League Comparison", "corner_second_phase"),
        ("Delivery Type", "corner_delivery_type"),
        ("Delivery Maps", "corner_delivery_zones"),
        ("Left-Side Corners", "corner_delivery_zones"),
        ("Right-Side Corners", "corner_delivery_zones"),
    ]),
    *_rows(OA, PA, OA_PLAYER, _PLAYER_KPIS + [
        ("Offensive PVA", "offensive_pva"),
        ("Defensive PVA", "defensive_pva"),
        ("Total PVA", "total_pva"),
        ("PVA per 90", "total_pva"),
        ("Adj PVA/90", "total_pva"),
        ("Role", "role_group"),
        ("Apps", "appearances"),
        ("partial", "appearances"),
        ("Starts", "starts"),
        ("Min", "season_minutes"),
        ("low min", "season_minutes"),
        ("Min%", "minutes_share"),
        ("σ PVA", "pva_consistency"),
        ("Adj /90", "adjusted_per90"),
        ("Raw /90", "raw_per90"),
        ("Season %", "season_pct"),
        ("Role %ile", "role_percentile"),
    ]),
]

# Rendered elements deliberately not mapped to a metric entry.
# (label, section, module, file, reason)
UNMAPPED: list[tuple] = [
    ("Shot Map", MA, MA_CC, CC,
     "Visual of individual shots (origin colour, goal markers); no own metric — "
     "covered by Total Shots, xG Total and Attack Origin Breakdown."),
    ("Shot Map — Defensive Half", MA, MA_CCON, CCON,
     "Visual of individual conceded shots; covered by Total Shots Faced and xG Against."),
    ("Distribution Chains", MA, MA_GK, GK,
     "Event-chain viewer for each goal kick; illustrates Outcome Classification."),
    ("Delivery Chains", MA, MA_FK, SP,
     "Event-chain viewer for free-kick deliveries; illustrates FK delivery outcomes."),
    ("Possession Sequence Viewer", MA, PA, PLAYER,
     "Container for the Cumulative Possession Value chart (mapped)."),
    ("Playing Style — League Comparison (percentiles)", TO, TO_WHEEL, TD_PAGE,
     "Modal table of the 12 wheel percentiles; each column is a mapped KPI."),
]
