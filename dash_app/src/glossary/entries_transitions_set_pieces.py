"""
Glossary entries for transitions (offensive and defensive) and set pieces
(corner kicks, free kicks). Match Analysis per match, Opponent Analysis per
season.
"""

from __future__ import annotations

from src.glossary._common import (
    CORRIDORS, D_CORNERS, D_DEF_TRANS, D_FREE_KICKS, D_OA_CORNERS,
    D_OA_DEF_TRANS, D_OA_OFF_TRANS, D_OFF_TRANS, GRID_18, MODAL_PER_MATCH,
    MODAL_RATE, PER_MATCH, SEASON_MEAN_DEVIATION, SEASON_RATIO, md, metric,
)

MA = "match_analysis"
OA = "opponent_analysis"
MA_OFF = "Transitions — Offensive Transition"
OA_OFF = "Transitions — Offensive Transitions"
MA_DEF = "Transitions — Defensive Transition"
OA_DEF = "Transitions — Defensive Transitions"
MA_CORNERS = "Set Pieces — Corner Kicks"
OA_CORNERS = "Set Pieces — Corner Kicks"
MA_FK = "Set Pieces — Free Kicks"

_OFF_DETECT = (
    "**Detection (offensive_transitions.py):** every event of the match is "
    "scanned. Triggers: the team's Ball Recovery (49), Interception (8) or won "
    "Tackle (7, outcome 1); or the opponent's Dispossessed (50), Error (51) or "
    "failed Ball Touch (61, outcome 0). Origin = the trigger location (team "
    "triggers) or the team's next play event (opponent triggers). A trigger is "
    "skipped when the team's next possession starts from a set piece, when the "
    "origin event is an aerial, challenge or shot, when the team committed a "
    "foul in the previous 3 s, or when it comes less than 8 s after the "
    "previous trigger (deduplication)."
)
_OFF_TIERS = (
    "**Outcome (25 s window, best tier reached):** P3 = a team shot or a "
    "penalty-area foul in the team's favour; P2 = a corner won in the final "
    "third, a cross with its end point at x ≥ 83.33, or a foul won in the "
    "final third; P1 = a team event at x ≥ 66.67, or any team event 15 s or "
    "more after the trigger. No flag = not qualified. Events count anywhere in "
    "the window, even if possession changed in between."
)
_DEF_DETECT = (
    "**Detection (defensive_structure.compute_defensive_transitions):** every "
    "event of the match is scanned. Triggers: the opponent's Ball Recovery "
    "(49), Interception (8) or won Tackle (7, outcome 1); or the team's "
    "Dispossessed (50), Error (51) or failed Ball Touch (61, outcome 0). Origin "
    "= the trigger location (team triggers) or the team's last play event "
    "before it (opponent triggers). The loss must be at x ≥ 50 (the team's "
    "attacking half). A trigger is skipped when the opponent's next possession "
    "starts from a set piece, when the origin event is an out, aerial, "
    "challenge, keeper pick-up or shot, when the opponent committed a foul in "
    "the previous 3 s, or when it comes less than 30 s after the previous "
    "accepted trigger."
)
_DEF_TIERS = (
    "**Outcome (25 s window, worst tier reached):** N3 = an opponent shot, or "
    "a foul by the team in its own box (or with the `Penalty` qualifier); "
    "N2 = an opponent corner in the final third, an opponent cross with its "
    "end point at x ≥ 83.33, or a foul by the team in its defensive third; "
    "N1 = an opponent event at x ≥ 66.67 (their frame), or any opponent event "
    "15 s or more after the trigger. No flag = not qualified."
)
_CORNER = (
    "A corner is a team Pass (type_id 1) with the `Corner taken` qualifier."
)
_CORNER_OUTCOME = (
    "**Outcome (corner_kicks._corner_outcome, next 49 events):** 'Cleared' at "
    "once if within 10 s the ball goes out, a new corner is awarded or the "
    "attacking team commits a foul. Otherwise the first opponent clearance, "
    "interception or goalkeeper claim within 25 s is a cut-off. Before the "
    "cut-off and within 25 s, the best `From corner`-tagged shot sets the "
    "outcome (Goal / Own Goal > Shot on Target > Shot off Target). If none is "
    "tagged, the first team shot (or opponent own goal) within 10 s is used. "
    "Otherwise the corner is 'Cleared', promoted to 'Second Phase Attack' when "
    "the corner carries `Leading to attempt` or the delivery was Short. "
    "Goals include opponent own goals."
)
_FK_DELIVERY = (
    "A free-kick delivery is any team Pass with the `Free kick taken` "
    "qualifier, penalties excluded — whatever its destination."
)
_FK_OUTCOME = (
    "**Delivery outcome (12 s window):** an opponent foul → Foul Won; ball out "
    "or an opponent shot/pass/carry → Cleared / No Shot; an opponent clearance, "
    "interception, claim, blocked pass, pick-up or won aerial → Cleared; a team "
    "shot → Goal / Shot on Target / Shot off Target / Hit Post. If the window "
    "expires, Second Phase when a teammate touched the ball, otherwise "
    "Cleared / No Shot."
)
_FK_SHOT = (
    "A direct free-kick shot is a team shot (type_id 13–16) with the "
    "`Free kick` qualifier, penalties excluded. Outcome by type: 16 Goal, "
    "15 Shot on Target, 14 Hit Post, 13 Shot off Target."
)


def _tier(id, name, sections, module, short, formula, reading, note, method, doc):
    return metric(
        id=id, name=name, sections=sections, module=module,
        short_definition=short, formula=formula, unit="count",
        reading=reading, reading_note=note, methodology=method,
        source_doc=doc, season_aggregation="sum",
    )


ENTRIES: list[dict] = [
    # ── Offensive transitions ────────────────────────────────────────────────
    metric(
        id="off_total_transitions",
        name="Total Transitions",
        sections=[MA, OA],
        module={MA: MA_OFF, OA: OA_OFF},
        short_definition="The team's ball recoveries anywhere on the pitch — the pool of possible counter-attacks.",
        formula="count of team Ball Recovery events (type_id 49)",
        unit="count",
        reading="contextual",
        reading_note="Context for the transition rate rather than a target.",
        methodology=md(
            "Raw count of the team's Ball Recovery events, any zone, any outcome. "
            "Opponent Analysis shows 'Transitions / Match'. " + PER_MATCH + " "
            + MODAL_PER_MATCH,
        ),
        source_doc=D_OFF_TRANS,
        season_aggregation="total_per_match",
    ),
    metric(
        id="off_qualified_transitions",
        name="Qualified Transitions",
        sections=[MA, OA],
        module={MA: MA_OFF, OA: OA_OFF},
        short_definition="Ball wins that turned into an attack reaching at least the P1 tier within 25 seconds.",
        formula="count of transitions with a P1, P2 or P3 outcome",
        unit="count",
        reading="higher_better",
        reading_note="More qualified transitions means more dangerous counter-attacks.",
        methodology=md(
            _OFF_DETECT, _OFF_TIERS,
            "Opponent Analysis shows 'Qualifying / Match'. " + PER_MATCH + " "
            + MODAL_PER_MATCH,
        ),
        source_doc=D_OFF_TRANS,
        season_aggregation="total_per_match",
    ),
    metric(
        id="off_transition_rate",
        name="Transition Rate",
        sections=[MA, OA],
        module={MA: MA_OFF, OA: OA_OFF},
        short_definition="Qualified offensive transitions as a share of the team's ball recoveries.",
        formula="Qualified Transitions ÷ Total Transitions × 100",
        unit="%",
        reading="higher_better",
        reading_note="Higher means ball wins more often become dangerous attacks.",
        methodology=md(
            _OFF_DETECT, _OFF_TIERS,
            "The numerator includes every trigger type, the denominator only "
            "Ball Recoveries, so the rate can exceed 100% in principle. "
            "Opponent Analysis labels it 'Qualifying Rate'.",
            SEASON_RATIO,
            MODAL_RATE,
        ),
        notes=(
            "The Match Analysis subtitle says 'per total team possessions'; the "
            "code divides by the team's ball recoveries."
        ),
        source_doc=D_OFF_TRANS,
        season_aggregation="ratio_of_sums",
    ),
    _tier("off_p1_sustained", "P1 — Sustained", [MA, OA], {MA: MA_OFF, OA: OA_OFF},
          "Offensive transition whose best outcome was reaching the final third or keeping the ball 15 s or more.",
          "best tier = P1", "contextual", "The mildest qualifying counter-attack outcome.",
          md(_OFF_DETECT, _OFF_TIERS), D_OFF_TRANS),
    _tier("off_p2_threatening", "P2 — Threatening", [MA, OA], {MA: MA_OFF, OA: OA_OFF},
          "Offensive transition that won a corner or a final-third free kick, or delivered a cross into the box, without a shot.",
          "best tier = P2", "higher_better", "A threatening counter-attack.",
          md(_OFF_DETECT, _OFF_TIERS,
             "The UI describes P2 as 'corner / free kick / cross in final third'; "
             "the cross must end at x ≥ 83.33."), D_OFF_TRANS),
    _tier("off_p3_dangerous", "P3 — Dangerous", [MA, OA], {MA: MA_OFF, OA: OA_OFF},
          "Offensive transition that produced a shot or a penalty-area foul in the team's favour.",
          "best tier = P3", "higher_better", "The most dangerous counter-attack outcome.",
          md(_OFF_DETECT, _OFF_TIERS,
             "Code reference: a foul *committed by the team* (its own row, "
             "outcome 0) inside the opponent box also sets the P3 penalty flag."), D_OFF_TRANS),
    metric(
        id="off_outcomes_by_zone",
        name="Outcomes by Zone",
        sections=[MA, OA],
        module={MA: MA_OFF, OA: OA_OFF},
        short_definition="P1/P2/P3 split of qualified offensive transitions by where the ball was won.",
        formula="tier counts per origin zone: Own Box x ≤ 16.67, Def. Third 16.67 < x ≤ 33.33, Mid x > 33.33",
        unit="distribution",
        reading="contextual",
        reading_note="Shows where the most dangerous counters start.",
        methodology=md(_OFF_DETECT, _OFF_TIERS, "Season counts are summed across matches."),
        source_doc=D_OFF_TRANS,
        season_aggregation="sum",
    ),
    metric(
        id="off_outcomes_by_corridor",
        name="Outcomes by Corridor",
        sections=[MA, OA],
        module={MA: MA_OFF, OA: OA_OFF},
        short_definition="P1/P2/P3 split of qualified offensive transitions by the corridor where the ball was won.",
        formula="tier counts per origin corridor",
        unit="distribution",
        reading="contextual",
        reading_note="Shows which side counter-attacks start from.",
        methodology=md(_OFF_DETECT, _OFF_TIERS, CORRIDORS, "Season counts are summed across matches."),
        source_doc=D_OFF_TRANS,
        season_aggregation="sum",
    ),
    metric(
        id="off_transition_origins",
        name="Offensive Transition Origins (Qualified · Own Half)",
        sections=[MA, OA],
        module={MA: MA_OFF, OA: OA_OFF},
        short_definition="Pitch map of where qualified counter-attacks started, for ball wins in the team's own half.",
        formula="qualified transitions with origin x ≤ 50",
        unit="map",
        reading="contextual",
        reading_note="Visual summary of counter-attack starting points.",
        methodology=md(
            "Match Analysis plots each qualified transition with origin x ≤ 50, "
            "coloured by tier (hover shows time to outcome). Opponent Analysis "
            "shows 'Pitch Map — Transition Origins Density' (green): per "
            "18-zone cell, the season count of such origins that reached P2 or P3.",
            GRID_18,
        ),
        source_doc=D_OA_OFF_TRANS,
        season_aggregation="sum",
    ),
    # ── Defensive transitions ────────────────────────────────────────────────
    metric(
        id="def_total_transitions",
        name="Total Transitions",
        sections=[MA, OA],
        module={MA: MA_DEF, OA: OA_DEF},
        short_definition="The opponent's ball recoveries anywhere on the pitch — the pool of possible counter-attacks against the team.",
        formula="count of opponent Ball Recovery events (type_id 49)",
        unit="count",
        reading="contextual",
        reading_note="Context for the transition rate rather than a target.",
        methodology=md(
            "Raw count of the opponent's Ball Recovery events, any zone, any "
            "outcome. Opponent Analysis shows 'Transitions / Match'. "
            + PER_MATCH + " " + MODAL_PER_MATCH,
        ),
        source_doc=D_DEF_TRANS,
        season_aggregation="total_per_match",
    ),
    metric(
        id="def_qualified_transitions",
        name="Qualified Transitions",
        sections=[MA, OA],
        module={MA: MA_DEF, OA: OA_DEF},
        short_definition="Ball losses in the attacking half after which the opponent's attack reached at least the N1 tier within 25 seconds.",
        formula="count of transitions with an N1, N2 or N3 outcome",
        unit="count",
        reading="lower_better",
        reading_note="Fewer means the team is less exposed after losing the ball.",
        methodology=md(
            _DEF_DETECT, _DEF_TIERS,
            "Opponent Analysis shows 'Qualifying / Match'. " + PER_MATCH + " "
            + MODAL_PER_MATCH,
        ),
        source_doc=D_DEF_TRANS,
        season_aggregation="total_per_match",
    ),
    metric(
        id="def_transition_rate",
        name="Transition Rate",
        sections=[MA, OA],
        module={MA: MA_DEF, OA: OA_DEF},
        short_definition="Qualified defensive transitions as a share of the opponent's ball recoveries.",
        formula="Qualified Transitions ÷ opponent Ball Recoveries × 100",
        unit="%",
        reading="lower_better",
        reading_note="Lower means opponent ball wins rarely become dangerous counters.",
        methodology=md(
            _DEF_DETECT, _DEF_TIERS,
            "Opponent Analysis labels it 'Qualifying Rate'.",
            SEASON_RATIO,
            MODAL_RATE,
        ),
        notes=(
            "The Match Analysis subtitle says 'per total team possessions' and "
            "the doc says '÷ possession losses in the attacking half'; the code "
            "divides by the opponent's ball recoveries (any zone)."
        ),
        source_doc=D_DEF_TRANS,
        season_aggregation="ratio_of_sums",
    ),
    _tier("def_n1_sustained", "N1 — Sustained", [MA, OA], {MA: MA_DEF, OA: OA_DEF},
          "Defensive transition whose worst outcome was the opponent reaching the final third or keeping the ball 15 s or more.",
          "worst tier = N1", "lower_better", "The mildest qualifying counter conceded.",
          md(_DEF_DETECT, _DEF_TIERS), D_DEF_TRANS),
    _tier("def_n2_threatening", "N2 — Threatening", [MA, OA], {MA: MA_DEF, OA: OA_DEF},
          "Defensive transition in which the opponent won a corner, crossed into the box or drew a foul in the team's defensive third, without a shot.",
          "worst tier = N2", "lower_better", "A threatening counter conceded.",
          md(_DEF_DETECT, _DEF_TIERS), D_DEF_TRANS),
    _tier("def_n3_dangerous", "N3 — Dangerous", [MA, OA], {MA: MA_DEF, OA: OA_DEF},
          "Defensive transition in which the opponent shot or the team conceded a foul in its own box.",
          "worst tier = N3", "lower_better", "The most dangerous counter conceded.",
          md(_DEF_DETECT, _DEF_TIERS), D_DEF_TRANS),
    metric(
        id="immediate_press_rate",
        name="Immediate Press ≤5s",
        sections=[MA, OA],
        module={MA: MA_DEF, OA: OA_DEF},
        short_definition="Share of the team's ball losses after which it made a defensive action within 5 seconds.",
        formula="transitions with first counter-press action ≤ 5 s ÷ recorded transitions × 100",
        unit="%",
        reading="contextual",
        reading_note="High means the team counter-presses straight away; a style choice.",
        methodology=md(
            _DEF_DETECT,
            "Counter-press actions: the team's Foul (4), Tackle (7), Interception "
            "(8), Aerial (44), Challenge (45) or Ball Recovery (49) in the 25 s "
            "window. The denominator is every recorded transition, qualified or "
            "not. Opponent Analysis labels it 'Immediate Press'.",
            SEASON_MEAN_DEVIATION,
            MODAL_RATE,
        ),
        source_doc=D_DEF_TRANS,
        season_aggregation="mean_of_match_values",
        status="pending_fix",
        notes="Not described in the defensive-transitions methodology docs.",
    ),
    metric(
        id="organised_drop_rate",
        name="Organised Drop >10s",
        sections=[MA, OA],
        module={MA: MA_DEF, OA: OA_DEF},
        short_definition="Share of the team's ball losses after which it made no defensive action for more than 10 seconds.",
        formula="transitions with no counter-press action or first action > 10 s ÷ recorded transitions × 100",
        unit="%",
        reading="contextual",
        reading_note="High means the team drops into shape instead of pressing; a style choice.",
        methodology=md(
            _DEF_DETECT,
            "Counter-press actions as for Immediate Press. Losses with a first "
            "action between 5 and 10 s count in neither rate. Opponent Analysis "
            "labels it 'Organised Drop'.",
            SEASON_MEAN_DEVIATION,
            MODAL_RATE,
        ),
        source_doc=D_DEF_TRANS,
        season_aggregation="mean_of_match_values",
        status="pending_fix",
        notes="Not described in the defensive-transitions methodology docs.",
    ),
    metric(
        id="def_outcomes_by_zone",
        name="Outcomes by Zone",
        sections=[MA, OA],
        module={MA: MA_DEF, OA: OA_DEF},
        short_definition="N1/N2/N3 split of qualified defensive transitions by where the ball was lost.",
        formula="tier counts per origin zone (High x ≥ 66.67, Mid 33.33–66.67, Low < 33.33)",
        unit="distribution",
        reading="contextual",
        reading_note="Shows where losses are most costly.",
        methodology=md(_DEF_DETECT, _DEF_TIERS, "Season counts are summed across matches."),
        source_doc=D_DEF_TRANS,
        season_aggregation="sum",
    ),
    metric(
        id="def_outcomes_by_corridor",
        name="Outcomes by Corridor",
        sections=[MA, OA],
        module={MA: MA_DEF, OA: OA_DEF},
        short_definition="N1/N2/N3 split of qualified defensive transitions by the corridor where the ball was lost.",
        formula="tier counts per origin corridor",
        unit="distribution",
        reading="contextual",
        reading_note="Shows which side losses lead to counters.",
        methodology=md(_DEF_DETECT, _DEF_TIERS, CORRIDORS, "Season counts are summed across matches."),
        source_doc=D_DEF_TRANS,
        season_aggregation="sum",
    ),
    metric(
        id="def_transition_origins",
        name="Transition Loss Origins (Qualified · Middle + Attacking Third)",
        sections=[MA, OA],
        module={MA: MA_DEF, OA: OA_DEF},
        short_definition="Pitch map of where the ball was lost before qualified counter-attacks against the team.",
        formula="qualified defensive transitions with origin x ≥ 33.33",
        unit="map",
        reading="contextual",
        reading_note="Shows the team's most vulnerable loss areas.",
        methodology=md(
            "Match Analysis plots each qualified transition (all origins are at "
            "x ≥ 50 by construction), coloured by tier, with the offside line "
            "overlaid. Opponent Analysis shows 'Pitch Map — Transition Origins "
            "Density' (red): per 18-zone cell, the season count of origins that "
            "reached N2 or N3.",
            GRID_18,
        ),
        source_doc=D_OA_DEF_TRANS,
        season_aggregation="sum",
    ),
    # ── Corner kicks ─────────────────────────────────────────────────────────
    metric(
        id="corners_total",
        name="Total Corners",
        sections=[MA, OA],
        module={MA: MA_CORNERS, OA: OA_CORNERS},
        short_definition="Corner kicks the team took.",
        formula="count of team passes with the Corner taken qualifier",
        unit="count",
        reading="contextual",
        reading_note="Volume reflects territorial pressure; not a quality measure.",
        methodology=md(
            _CORNER,
            "Opponent Analysis shows 'Corners / Match' with the season total and "
            "conversion rate underneath. " + PER_MATCH + " " + MODAL_PER_MATCH,
        ),
        source_doc=D_CORNERS,
        season_aggregation="total_per_match",
    ),
    metric(
        id="corner_goals",
        name="Goals",
        sections=[MA, OA],
        module={MA: MA_CORNERS, OA: OA_CORNERS},
        short_definition="Corners whose outcome was a goal, including opponent own goals.",
        formula="corners with outcome Goal or Own Goal",
        unit="count",
        reading="higher_better",
        reading_note="More corner goals is better.",
        methodology=md(
            _CORNER, _CORNER_OUTCOME,
            "Match Analysis subtitle: share of corners. Opponent Analysis shows "
            "'Goals / Match' (" + PER_MATCH + ") " + MODAL_PER_MATCH,
        ),
        notes=(
            "opp-season-corner-kicks.md says own goals are excluded from the "
            "headline Goals KPI; the code includes them."
        ),
        source_doc=D_CORNERS,
        season_aggregation="total_per_match",
    ),
    metric(
        id="corner_conversion_rate",
        name="% conv.",
        sections=[OA],
        module={OA: OA_CORNERS},
        short_definition="Share of the season's corners that produced a goal.",
        formula="corner goals (incl. own goals) ÷ corners × 100",
        unit="%",
        reading="higher_better",
        reading_note="Higher means corners are converted more often.",
        methodology=md(_CORNER_OUTCOME, SEASON_RATIO),
        source_doc=D_OA_CORNERS,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="corner_shots_on_target",
        name="Shots on Target",
        sections=[MA, OA],
        module={MA: MA_CORNERS, OA: OA_CORNERS},
        short_definition="Corners whose best outcome was a shot on target that was not scored.",
        formula="corners with outcome Shot on Target",
        unit="count",
        reading="higher_better",
        reading_note="More on-target attempts from corners is better.",
        methodology=md(
            _CORNER_OUTCOME,
            "Opponent Analysis shows 'Shots on Target / Match'. " + MODAL_PER_MATCH,
        ),
        source_doc=D_CORNERS,
        season_aggregation="total_per_match",
    ),
    metric(
        id="corner_shots_off_target",
        name="Shots off Target",
        sections=[MA, OA],
        module={MA: MA_CORNERS, OA: OA_CORNERS},
        short_definition="Corners whose best outcome was a shot off target or hitting the post.",
        formula="corners with outcome Shot off Target",
        unit="count",
        reading="contextual",
        reading_note="An attempt, but not a dangerous one.",
        methodology=md(
            _CORNER_OUTCOME,
            "Opponent Analysis shows 'Shots off Target / Match'. " + MODAL_PER_MATCH,
        ),
        source_doc=D_CORNERS,
        season_aggregation="total_per_match",
    ),
    metric(
        id="corner_cleared",
        name="Cleared",
        sections=[MA, OA],
        module={MA: MA_CORNERS, OA: OA_CORNERS},
        short_definition="Corners that produced no shot and no second-phase attack.",
        formula="corners with outcome Cleared",
        unit="count",
        reading="lower_better",
        reading_note="Fewer cleared corners means more productive routines.",
        methodology=md(
            _CORNER_OUTCOME,
            "Opponent Analysis shows 'Cleared / Match'. " + MODAL_PER_MATCH,
        ),
        source_doc=D_CORNERS,
        season_aggregation="total_per_match",
    ),
    metric(
        id="corner_second_phase",
        name="2nd Phase",
        sections=[MA, OA],
        module={MA: MA_CORNERS, OA: OA_CORNERS},
        short_definition="Corners with no direct shot that still led to a further attack (Opta 'leading to attempt') or were played short.",
        formula="corners with outcome Second Phase Attack",
        unit="count",
        reading="contextual",
        reading_note="Keeps the attack alive, but less direct than a shot.",
        methodology=md(
            _CORNER_OUTCOME,
            "Opponent Analysis shows '2nd Phase / Match'. " + MODAL_PER_MATCH,
        ),
        notes="Every Short corner without a direct shot is counted as 2nd Phase, regardless of what follows.",
        source_doc=D_CORNERS,
        season_aggregation="total_per_match",
    ),
    metric(
        id="corner_delivery_type",
        name="Delivery Type",
        sections=[MA, OA],
        module={MA: MA_CORNERS, OA: OA_CORNERS},
        short_definition="How each corner was delivered (inswinger, outswinger, straight, short) and what it produced.",
        formula="Opta swing qualifier; else end-point rules; outcome counts per type",
        unit="table",
        reading="contextual",
        reading_note="Describes the team's corner routines.",
        methodology=md(
            "Opta qualifiers first: `Inswinger` → `Outswinger` → `Straight`. "
            "When none is present and the pass has no `Cross` qualifier: end x ≥ 93 "
            "→ Short; end x ≥ 83.33 outside the box width (y < 21.1 or > 78.9) → "
            "Short; end x < 83.33 → Straight; otherwise Unknown.",
            "The table shows, per type, the count and each outcome's share of "
            "that type's corners (Own Goal kept as its own column). Season "
            "tables sum counts across matches.",
            SEASON_RATIO,
        ),
        source_doc=D_CORNERS,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="corner_delivery_zones",
        name="Delivery Maps",
        sections=[MA, OA],
        module={MA: MA_CORNERS, OA: OA_CORNERS},
        short_definition="Where corners landed, on a nine-zone goalmouth map, separately for left- and right-side corners.",
        formula="count of corners per landing zone",
        unit="map",
        reading="contextual",
        reading_note="Shows the target areas of corner routines.",
        methodology=md(
            "Landing zone from `Pass End X/Y`, near/far post relative to the "
            "corner side (left corner = start y ≥ 50): GA1/GA2/GA3 = six-yard box "
            "(end x ≥ 94.8) near/centre/far; CA1/CA2/CA3 = rest of the box "
            "(end x ≥ 83.33, 21.1 ≤ y ≤ 78.9); Edge = 79 ≤ end x < 83.33 inside "
            "the box width; Front / Back = near-post / far-post strips outside the "
            "box width. Each corner is drawn from the flag to its landing point, "
            "coloured by outcome.",
        ),
        source_doc=D_CORNERS,
        season_aggregation="sum",
    ),
    # ── Free kicks ───────────────────────────────────────────────────────────
    metric(
        id="fk_total_deliveries",
        name="Total Deliveries",
        sections=[MA],
        module={MA: MA_FK},
        short_definition="Free kicks the team played as a pass (crosses and passes), rather than a shot.",
        formula="count of team passes with the Free kick taken qualifier, penalties excluded",
        unit="count",
        reading="contextual",
        reading_note="Volume depends on fouls won; not a quality measure.",
        methodology=md(_FK_DELIVERY),
        notes="The doc says deliveries 'into the box'; the code counts every free-kick pass.",
        source_doc=D_FREE_KICKS,
        season_aggregation=None,
    ),
    metric(
        id="fk_delivery_outcomes",
        name="FK Deliveries — Volume & Outcomes",
        sections=[MA],
        module={MA: MA_FK},
        short_definition="What the team's free-kick deliveries produced: goals, shots, second phases or clearances.",
        formula="count of deliveries per outcome; each card also shows ÷ deliveries × 100",
        unit="count",
        reading="contextual",
        reading_note="More goals and shots per delivery means more productive routines.",
        methodology=md(
            _FK_DELIVERY, _FK_OUTCOME,
            "Cards: Goals, Shots on Target, Shots off Target, Hit Post, "
            "'2nd Phase / Foul' (Second Phase + Foul Won + Assist) and "
            "'Cleared / No Shot' (Cleared + Cleared / No Shot).",
        ),
        source_doc=D_FREE_KICKS,
        season_aggregation=None,
    ),
    metric(
        id="fk_delivery_type",
        name="Delivery Type",
        sections=[MA],
        module={MA: MA_FK},
        short_definition="How each free-kick delivery was played (crossed, chipped, long ball, launch or short).",
        formula="first match: Cross → Chipped → Long ball → Launch → Short",
        unit="table",
        reading="contextual",
        reading_note="Describes the team's free-kick routines.",
        methodology=md(
            _FK_DELIVERY,
            "Opta qualifiers in priority order: `Cross` → Crossed into Box; "
            "`Chipped` → Chipped / Lofted; `Long ball` → Long Ball; `Launch` → "
            "Launch; otherwise Short. Shown with the outcome split per type and "
            "the landing zone.",
        ),
        source_doc=D_FREE_KICKS,
        season_aggregation=None,
    ),
    metric(
        id="fk_total_shots",
        name="Total FK Shots",
        sections=[MA],
        module={MA: MA_FK},
        short_definition="Free kicks the team shot directly at goal.",
        formula="count of team shots with the Free kick qualifier, penalties excluded",
        unit="count",
        reading="contextual",
        reading_note="Volume of direct attempts; not a quality measure.",
        methodology=md(_FK_SHOT),
        source_doc=D_FREE_KICKS,
        season_aggregation=None,
    ),
    metric(
        id="fk_direct_shot_outcomes",
        name="Direct FK Shots — Volume & Outcomes",
        sections=[MA],
        module={MA: MA_FK},
        short_definition="What the team's direct free-kick shots produced: goals, shots on and off target, posts, blocks.",
        formula="count of direct shots per outcome; each card also shows ÷ shots × 100",
        unit="count",
        reading="contextual",
        reading_note="More goals and on-frame shots is better.",
        methodology=md(
            _FK_SHOT,
            "Cards: Goals, Shots on Target, Shots off Target, Hit Post, Blocked "
            "(shots with the `Blocked` qualifier, also counted in their type "
            "outcome) and On Frame (= Goals + Shots on Target + Hit Post).",
            "Shown with the 'Goalmouth zone (GK perspective)' map of where each "
            "shot ended, from the Opta goal-mouth qualifiers.",
        ),
        notes="Blocked shots are usually Opta type 15 and therefore also count as on target and on frame.",
        source_doc=D_FREE_KICKS,
        season_aggregation=None,
    ),
]
