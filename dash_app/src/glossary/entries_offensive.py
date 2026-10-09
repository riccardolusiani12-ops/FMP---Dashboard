"""
Glossary entries for the offensive phase: goal-kick build-up, build-up to the
final third and chance creation (Match Analysis per match, Opponent Analysis
per season).
"""

from __future__ import annotations

from src.glossary._common import (
    COORDS, CORRIDORS, D_CC, D_FT, D_GK, D_OA_CC, D_OA_FT, D_OA_GK, D_ORIGIN,
    D_TIERS, FINAL_THIRD, GRID_18, MODAL_PER_MATCH, MODAL_RATE,
    OWN_GOAL_ROWS, PENALTY_BOX, PENALTY_XG_TEXT, PER_MATCH, ROW_XG_NOTE,
    SEASON_MEAN_DEVIATION, SEASON_RATIO, md, metric,
)

MA = "match_analysis"
OA = "opponent_analysis"
MA_GK = "Offensive Phase — Build-up from Goal Kicks"
OA_GK = "Offensive Phase — GK Build-up"
MA_FT = "Offensive Phase — Build-up to Final Third"
OA_FT = "Offensive Phase — Build-up to Final Third"
MA_CC = "Offensive Phase — Chance Creation"
OA_CC = "Offensive Phase — Chance Creation"

_GOAL_KICK = (
    "A goal kick is a team Pass event (type_id 1) carrying the Opta `Goal Kick` "
    "qualifier; detection uses that flag only, whoever takes the kick."
)
_FIRST_RECEIVER = (
    "The first receiver is the first team play event after the goal kick (within "
    "the next 20 events) before any opponent touch. Short = first receiver in "
    "zones Z1–Z6 (the team's defensive third, x < 33.33); Long = Z7–Z18. If an "
    "opponent touches first, the zone of the pass end point is used; if that is "
    "missing too, a goal kick with Length > 32 is Long, otherwise Short."
)
_GK_CHAIN = (
    "Outcome chain: from the first receiver the team's events are followed. A "
    "team shot ends it as positive (P3). A team event 15 s or more after the "
    "first reception ends it as positive: P2 if the team reached " + FINAL_THIRD
    + " at any point, otherwise P1. An opponent foul is positive (P1/P2). After "
    "any other opponent event the next events are looked ahead to decide who "
    "really has the ball (contested duels, outs and corners whose restart goes "
    "to the team do not end the chain). A genuine loss before 15 s is negative; "
    "the opponent's possession is then followed: N3 if it produces a shot, N2 if "
    "it reaches x ≥ 83.33, otherwise N1. If no teammate receives the goal kick it "
    "is negative."
)
_FT_ENTRY = (
    "An entry is the moment a possession moves the ball from x < 66.67 to "
    "x ≥ 66.67: a pass whose end point is in the final third (or, if the end "
    "point is missing, whose next event is), a through ball whose next event is "
    "in the final third, or a carry (ball touch / take-on by the same player) "
    "crossing the line. Possessions whose first play event is already in the "
    "final third are skipped, except open-play possessions that start there with "
    "a ball recovery, interception or won tackle, which count as one "
    "'high regain' entry. Possessions of every origin (open play and set pieces) "
    "are scanned; a possession can produce more than one entry."
)
_QUALIFYING = "Qualifying possessions are team possessions lasting at least 10 s (MIN_POSS_SEC)."


ENTRIES: list[dict] = [
    # ── Goal-kick build-up ───────────────────────────────────────────────────
    metric(
        id="matches_analysed",
        name="Matches",
        sections=[OA],
        module={OA: OA_GK + " · " + OA_CC},
        short_definition="Number of season matches included in the aggregate.",
        formula="matches_played from offensive_summary_{season}.parquet",
        unit="count",
        reading="contextual",
        reading_note="Context for every per-match value in the section.",
        methodology=md(
            "Matches played are counted from the season's match files (home and "
            "away appearances). If the summary parquet is missing, the number of "
            "distinct gameweeks with data is used.",
        ),
        source_doc=D_OA_GK,
        season_aggregation="sum",
    ),
    metric(
        id="gk_possessions",
        name="GK Possessions",
        sections=[MA, OA],
        module={MA: MA_GK, OA: OA_GK},
        short_definition="Number of goal kicks the team took.",
        formula="count of team passes with the Goal Kick qualifier",
        unit="count",
        reading="contextual",
        reading_note="Volume depends on how often the opponent puts the ball out; not a quality measure.",
        methodology=md(
            _GOAL_KICK,
            "Match Analysis shows the match count as 'Total' (distributions). "
            "Opponent Analysis shows the season total with the per-match "
            "average underneath. " + PER_MATCH,
        ),
        notes="Labelled 'GK Possessions' but it counts goal kicks only, not every goalkeeper distribution.",
        source_doc=D_GK,
        season_aggregation="total_per_match",
    ),
    metric(
        id="gk_short_pct",
        name="Short Pass %",
        sections=[MA, OA],
        module={MA: MA_GK, OA: OA_GK},
        short_definition="Share of goal kicks first received inside the team's own defensive third.",
        formula="short goal kicks ÷ goal kicks × 100",
        unit="%",
        reading="contextual",
        reading_note="A build-up choice: high means the team plays out from the back.",
        methodology=md(_GOAL_KICK, _FIRST_RECEIVER, GRID_18, SEASON_RATIO),
        source_doc=D_GK,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="gk_long_pct",
        name="Long Ball %",
        sections=[MA, OA],
        module={MA: MA_GK, OA: OA_GK},
        short_definition="Share of goal kicks first received beyond the team's own defensive third.",
        formula="long goal kicks ÷ goal kicks × 100",
        unit="%",
        reading="contextual",
        reading_note="A build-up choice: high means the team goes long from goal kicks.",
        methodology=md(_GOAL_KICK, _FIRST_RECEIVER, SEASON_RATIO),
        source_doc=D_GK,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="gk_short_success_rate",
        name="GK Short-Pass Success Rate",
        sections=[OA],
        module={OA: OA_GK},
        short_definition="Share of short goal kicks that ended with a positive outcome.",
        formula="positive short goal kicks ÷ short goal kicks × 100",
        unit="%",
        reading="higher_better",
        reading_note="Higher means short build-up survives the press more often.",
        methodology=md(
            "Shown as '% success' under Short Pass % and in the league bar "
            "'GK Short-Pass Success Rate — All Teams'. Positive/negative as in "
            "'Outcome Classification'.",
            _GK_CHAIN,
            SEASON_RATIO,
            MODAL_RATE,
        ),
        source_doc=D_OA_GK,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="gk_long_success_rate",
        name="GK Long-Ball Success Rate",
        sections=[OA],
        module={OA: OA_GK},
        short_definition="Share of long goal kicks that ended with a positive outcome.",
        formula="positive long goal kicks ÷ long goal kicks × 100",
        unit="%",
        reading="higher_better",
        reading_note="Higher means long goal kicks are won and kept more often.",
        methodology=md(
            "Shown as '% success' under Long Ball % and in the league bar "
            "'GK Long-Ball Success Rate — All Teams'.",
            _GK_CHAIN,
            SEASON_RATIO,
            MODAL_RATE,
        ),
        source_doc=D_OA_GK,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="gk_outcome",
        name="Outcome Classification",
        sections=[MA, OA],
        module={MA: MA_GK, OA: OA_GK},
        short_definition="Whether each goal kick kept possession for 15 s (positive) or lost it (negative), with three grades each.",
        formula="positive if possession kept ≥ 15 s from first reception or a shot; negative otherwise",
        unit="distribution",
        reading="contextual",
        reading_note="More positive (and higher P grades) is better.",
        methodology=md(
            _GK_CHAIN,
            "Opponent Analysis shows the same split in the 'Outcome Breakdown' "
            "modals and the 'Positive Rate' of each build-up type; season counts "
            "are summed before shares are computed.",
            SEASON_RATIO,
        ),
        notes="The audit brief's short/medium/long/mixed taxonomy does not exist in code.",
        source_doc=D_GK,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="gk_p1_established_possession",
        name="Established Possession",
        sections=[MA, OA],
        module={MA: MA_GK, OA: OA_GK},
        short_definition="P1: the team kept the goal kick for at least 15 s without reaching the final third.",
        formula="positive, no final-third event, no shot",
        unit="count",
        reading="higher_better",
        reading_note="A retained goal kick; better than any negative outcome.",
        methodology=md(_GK_CHAIN),
        notes="The UI description says 'without leaving own half'; the code condition is 'without reaching the final third (x ≥ 66.67)'.",
        source_doc=D_GK,
        season_aggregation="sum",
    ),
    metric(
        id="gk_p2_reached_final_third",
        name="Reached Final Third",
        sections=[MA, OA],
        module={MA: MA_GK, OA: OA_GK},
        short_definition="P2: the team kept the goal kick for at least 15 s and reached the final third.",
        formula="positive and any team event at x ≥ 66.67 in the chain",
        unit="count",
        reading="higher_better",
        reading_note="A retained goal kick that progressed into attacking territory.",
        methodology=md(_GK_CHAIN),
        source_doc=D_GK,
        season_aggregation="sum",
    ),
    metric(
        id="gk_p3_created_shot",
        name="Created a Shot",
        sections=[MA, OA],
        module={MA: MA_GK, OA: OA_GK},
        short_definition="P3: the possession that started from the goal kick produced a team shot.",
        formula="team shot event in the retained chain",
        unit="count",
        reading="higher_better",
        reading_note="The best goal-kick outcome.",
        methodology=md(_GK_CHAIN),
        source_doc=D_GK,
        season_aggregation="sum",
    ),
    metric(
        id="gk_n1_possession_lost",
        name="Possession Lost",
        sections=[MA, OA],
        module={MA: MA_GK, OA: OA_GK},
        short_definition="N1: the team lost the ball within 15 s, without the opponent entering the box or shooting.",
        formula="negative; opponent possession reaches neither x ≥ 83.33 nor a shot",
        unit="count",
        reading="lower_better",
        reading_note="The mildest negative outcome.",
        methodology=md(_GK_CHAIN),
        source_doc=D_GK,
        season_aggregation="sum",
    ),
    metric(
        id="gk_n2_box_entry_conceded",
        name="Box Entry Conceded",
        sections=[MA, OA],
        module={MA: MA_GK, OA: OA_GK},
        short_definition="N2: after winning the ball, the opponent reached the team's penalty area without shooting.",
        formula="negative; opponent event at x ≥ 83.33 (their frame), no shot",
        unit="count",
        reading="lower_better",
        reading_note="A costly loss.",
        methodology=md(_GK_CHAIN, "The box test uses x only (no y band)."),
        source_doc=D_GK,
        season_aggregation="sum",
    ),
    metric(
        id="gk_n3_shot_conceded",
        name="Shot Conceded",
        sections=[MA, OA],
        module={MA: MA_GK, OA: OA_GK},
        short_definition="N3: after winning the ball, the opponent produced a shot.",
        formula="negative; opponent shot during their possession",
        unit="count",
        reading="lower_better",
        reading_note="The most costly goal-kick outcome.",
        methodology=md(_GK_CHAIN),
        source_doc=D_GK,
        season_aggregation="sum",
    ),
    metric(
        id="gk_first_receiver_zones",
        name="First Receiver Zone Distribution",
        sections=[MA, OA],
        module={MA: MA_GK, OA: OA_GK},
        short_definition="Where goal kicks are first received, on the 18-zone pitch grid.",
        formula="count of goal kicks per first-receiver zone",
        unit="distribution",
        reading="contextual",
        reading_note="Shows the target areas of the build-up.",
        methodology=md(
            _FIRST_RECEIVER, GRID_18,
            "Match Analysis also shows the outcome split per zone ('Goal Kick — "
            "First Receiver Zones'). Opponent Analysis shows the season map as "
            "'GK Distribution End-Points' with counts summed across matches.",
        ),
        source_doc=D_GK,
        season_aggregation="sum",
    ),
    # ── Build-up to Final Third ──────────────────────────────────────────────
    metric(
        id="possession_pct",
        name="Possession %",
        sections=[MA, OA],
        module={MA: MA_FT, OA: OA_FT},
        short_definition="The team's share of total possession time in the match.",
        formula="Σ team possession durations ÷ Σ all possession durations × 100",
        unit="%",
        reading="contextual",
        reading_note="A style indicator: more of the ball is not automatically better.",
        methodology=md(
            "Possessions come from general_buildup.build_possessions(). Each "
            "possession's duration is the time between its first and last play "
            "event (non-play events excluded, floored at 0). Possession % = team "
            "duration ÷ total duration of all possessions × 100.",
            "Opponent Analysis shows the season value ('avg ball possession per "
            "match').",
            SEASON_MEAN_DEVIATION,
        ),
        notes="Time between events, not a ball-in-play clock; stoppages inside a possession count.",
        source_doc=D_FT,
        season_aggregation="mean_of_match_values",
        status="pending_fix",
    ),
    metric(
        id="possession_by_time_period",
        name="POSSESSION BY TIME PERIOD",
        sections=[MA],
        module={MA: MA_FT},
        short_definition="Possession share for each 15-minute band of the match.",
        formula="team possession time overlapping the band ÷ all possession time in the band × 100",
        unit="%",
        reading="contextual",
        reading_note="Shows which phases of the match the team controlled.",
        methodology=md(
            "Shown in the Possession % modal. Bands are 15 minutes of match "
            "clock (minute × 60 + second, where the second half starts at 45:00); "
            "each possession contributes the part of its duration that overlaps "
            "the band. An 'Overall' row repeats Possession %.",
        ),
        notes=(
            "Band labels in code: 15', 30', 45', 60', 75', 90', \"45+'\", \"90+'\" "
            "for 0–15 … 75–90, 90–105, 105–120 minutes of match clock; first-half "
            "stoppage time therefore falls in the 45–60 band and the 90–105 band "
            "is labelled 45+'."
        ),
        source_doc=D_FT,
        season_aggregation=None,
    ),
    metric(
        id="possession_by_pitch_area",
        name="POSSESSION BY PITCH AREA",
        sections=[MA],
        module={MA: MA_FT},
        short_definition="How the team's possession time splits between possessions held mainly in its own half and in the opponent's half.",
        formula="duration of possessions with mean x < 50 (own half) vs ≥ 50 ÷ team possession time × 100",
        unit="%",
        reading="contextual",
        reading_note="More opponent-half time suggests territorial control.",
        methodology=md(
            "Shown in the Possession % modal. Each team possession is assigned "
            "whole to the own half or opponent half by the mean x of its play "
            "events.",
            COORDS,
        ),
        source_doc=D_FT,
        season_aggregation=None,
    ),
    metric(
        id="qualifying_possessions",
        name="Qualifying Poss.",
        sections=[MA],
        module={MA: MA_FT},
        short_definition="Team possessions that lasted at least 10 seconds.",
        formula="count of team possessions with duration ≥ 10 s",
        unit="count",
        reading="contextual",
        reading_note="Volume of sustained possessions; the base for entry rates and tempo.",
        methodology=md(_QUALIFYING, "Duration as defined for Possession %."),
        source_doc=D_FT,
        season_aggregation=None,
    ),
    metric(
        id="ft_entries_total",
        name="Total FT Entries",
        sections=[MA],
        module={MA: MA_FT},
        short_definition="Every time the team moved the ball into the final third, in any possession.",
        formula="count of entries across all team possessions",
        unit="count",
        reading="higher_better",
        reading_note="More entries means more access to attacking areas.",
        methodology=md(_FT_ENTRY, COORDS),
        notes="The doc says only open-play possessions are scanned; the code scans all origins.",
        source_doc=D_FT,
        season_aggregation=None,
    ),
    metric(
        id="ft_entries_qualifying",
        name="Qual. FT Entries",
        sections=[MA],
        module={MA: MA_FT},
        short_definition="Final-third entries made in possessions of at least 10 seconds; the base for every entry breakdown.",
        formula="count of entries in qualifying possessions; subtitle = possessions with ≥ 1 entry ÷ qualifying possessions × 100",
        unit="count",
        reading="higher_better",
        reading_note="More sustained-possession entries means more controlled access to the final third.",
        methodology=md(
            _FT_ENTRY, _QUALIFYING,
            "All corridor, method, zone and outcome breakdowns, and the Opponent "
            "Analysis season entries (ft_entries_{season}.parquet), use these "
            "qualifying entries.",
        ),
        source_doc=D_FT,
        season_aggregation="sum",
    ),
    metric(
        id="opp_box_touches",
        name="Opp. Box Touches",
        sections=[MA, OA],
        module={MA: MA_FT, OA: OA_FT},
        short_definition="Team on-ball events inside the opponent's penalty area.",
        formula="count of team events with x ≥ 83.33 and 21 ≤ y ≤ 79, excluding duels, fouls and non-play events",
        unit="count",
        reading="higher_better",
        reading_note="More box touches means more presence in the most dangerous area.",
        methodology=md(
            "Counted on the team's own rows during its possessions. Excluded "
            "event types: aerial, tackle, foul, card, offside provoked, shield "
            "ball, out, corner awarded, offside and administrative events. Each "
            "action counts separately.",
            "Opponent Analysis shows the season value per match and ranks all "
            "teams in 'Opp. Box Touches / Match — League Ranking'. "
            + MODAL_PER_MATCH,
            "The season value is the mean of per-match counts, which equals the "
            "season total ÷ matches analysed.",
        ),
        notes="The box y-band here is 21–79; Chance Creation uses 21.1–78.9.",
        source_doc=D_FT,
        season_aggregation="total_per_match",
    ),
    metric(
        id="tempo",
        name="Tempo",
        sections=[MA, OA],
        module={MA: MA_FT, OA: OA_FT},
        short_definition="Passes per minute the team plays in its sustained (≥ 10 s) possessions.",
        formula="passes in qualifying possessions ÷ minutes between the first and last such pass",
        unit="passes per minute",
        reading="contextual",
        reading_note="Higher is a quicker passing rhythm; a style trait.",
        methodology=md(
            _QUALIFYING,
            "Passes (event 'pass') in qualifying possessions are counted and "
            "divided by the time span from the first to the last of those passes "
            "in the match. The modal 'Tempo — 15-Minute Windows' repeats the "
            "calculation in consecutive 15-minute windows starting at the first "
            "qualifying pass.",
            "Opponent Analysis shows the season value ('avg passes/min').",
            SEASON_MEAN_DEVIATION,
        ),
        notes="The time span is the whole match window between those passes, not the possessions' own duration.",
        source_doc=D_FT,
        season_aggregation="mean_of_match_values",
        status="pending_fix",
    ),
    metric(
        id="ft_entry_corridor",
        name="Entry by Corridor",
        sections=[MA, OA],
        module={MA: MA_FT, OA: OA_FT},
        short_definition="Share of final-third entries through the left, central and right corridors.",
        formula="entries per corridor ÷ qualifying entries × 100",
        unit="%",
        reading="contextual",
        reading_note="Shows the preferred attacking side; not a quality measure.",
        methodology=md(
            "Each qualifying entry is assigned by its entry-point y. " + CORRIDORS,
            "Opponent Analysis shows the season split as the 'Left Corridor', "
            "'Central' and 'Right Corridor' cards.",
            SEASON_RATIO,
        ),
        source_doc=D_FT,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="ft_entry_method",
        name="How — Entry Method",
        sections=[MA, OA],
        module={MA: MA_FT, OA: OA_FT},
        short_definition="How each entry into the final third was made, in eight priority-ordered categories.",
        formula="first matching rule: transition → through ball → switch → set piece → cross → long ball → carry → short pass",
        unit="distribution",
        reading="contextual",
        reading_note="Describes the team's progression style.",
        methodology=md(
            "final_third._classify_ft_method(), first match wins:",
            "1. Transition / Recovery — the possession started with a ball "
            "recovery, interception or tackle at x ≤ 50 and the entry came within 15 s.\n"
            "2. Through Ball — `Through ball` qualifier on the entry event or any of "
            "the last 3 passes.\n"
            "3. Switch of Play — `Switch of play` qualifier on the entry event or "
            "any of the last 3 passes.\n"
            "4. Set-Piece — the possession started from a set-piece restart and "
            "the restart itself crossed the line (no passes before the entry).\n"
            "5. Cross Delivery — `Cross` qualifier on the entry event or the last pass.\n"
            "6. Long Ball — `Long ball` qualifier or Length ≥ 32 on the entry or the last pass.\n"
            "7. Individual Carry — a carry by one player across the line.\n"
            "8. Short Pass — everything else (default).",
            "Shares = method count ÷ qualifying entries × 100. Opponent Analysis "
            "shows the season breakdown ('Entry Method Breakdown') with counts "
            "summed across matches.",
            SEASON_RATIO,
        ),
        notes=(
            "The doc lists 7 methods (it merges cross and long ball as 5a/5b); "
            "the season data stores 8 keys. UI hover text for Short Pass says "
            "'Patient build-up with ≥ 5 passes'; no pass-count rule exists in code. "
            "High-regain entries usually fall through to Short Pass."
        ),
        source_doc=D_FT,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="ft_top_method",
        name="Top Method",
        sections=[OA],
        module={OA: OA_FT},
        short_definition="The most frequent final-third entry method of the season and its share of entries.",
        formula="modal method; value = its count ÷ entries × 100",
        unit="%",
        reading="contextual",
        reading_note="Identifies the dominant progression route.",
        methodology=md(
            "Mode of the season's qualifying entries by method (Short Pass "
            "included); the dropdown lists every method's share.",
            SEASON_RATIO,
        ),
        notes=(
            "Code reference: the unused field top_method_excl_short returns the "
            "second-ranked non-short method (index [1]) rather than the first."
        ),
        source_doc=D_OA_FT,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="ft_zone14",
        name="Zone 14",
        sections=[MA],
        module={MA: MA_FT},
        short_definition="Share of final-third entries whose entry point is in Zone 14, the central area just outside the box.",
        formula="entries with entry point in Z14 ÷ qualifying entries × 100",
        unit="%",
        reading="higher_better",
        reading_note="Central entries close to the box are the most dangerous.",
        methodology=md(
            "Zone 14 = x 66.67–83.33, y 33.33–66.67 (Z14 of the 18-zone grid). "
            "The test uses the entry point itself.",
            GRID_18,
        ),
        notes=(
            "UI says 'Entries reaching the central danger zone'; the KPI counts "
            "entries that start in Z14. Separate post-entry reach flags (10 s window) "
            "are computed but not shown."
        ),
        source_doc=D_FT,
        season_aggregation=None,
    ),
    metric(
        id="ft_flanks",
        name="Flanks",
        sections=[MA],
        module={MA: MA_FT},
        short_definition="Share of final-third entries whose entry point is in a wide channel of the final third.",
        formula="entries with entry point in Z13, Z15, Z16 or Z18 ÷ qualifying entries × 100",
        unit="%",
        reading="contextual",
        reading_note="Shows how much the team enters through wide areas.",
        methodology=md("Wide final-third zones Z13, Z15, Z16, Z18 of the 18-zone grid.", GRID_18),
        source_doc=D_FT,
        season_aggregation=None,
    ),
    metric(
        id="ft_entry_outcome",
        name="Entry Outcomes (Positive / Negative)",
        sections=[MA],
        module={MA: MA_FT},
        short_definition="Whether each final-third entry led to a constructive outcome (positive) or an early loss (negative).",
        formula="positive if shot, corner, opponent foul, penalty or ball kept ≥ 5 s; otherwise negative",
        unit="distribution",
        reading="higher_better",
        reading_note="A higher positive share means entries are converted into sustained attacks.",
        methodology=md(
            "final_third._classify_outcome() scans forward from the entry over "
            "the whole match. Positive (checked first): a team shot; any 'corner "
            "awarded' event; a foul committed by the defending team; a team event "
            "with the `Penalty` qualifier; or the team still has the ball 5 s or "
            "more after the entry. Negative: the attacking team commits a foul, or "
            "a genuine loss (confirmed by look-ahead) before 5 s. Also shown split "
            "'by Corridor' and 'by Method'.",
        ),
        notes=(
            "UI says 'Lost within ≤ 3 s'; the code threshold is 5 s and "
            "OUTCOME_NEGATIVE_SEC = 3 is unused."
        ),
        source_doc=D_FT,
        season_aggregation=None,
    ),
    metric(
        id="ft_success_rate",
        name="Success Rate",
        sections=[OA],
        module={OA: OA_FT},
        short_definition="Share of the season's final-third entries with a positive outcome.",
        formula="positive entries ÷ entries × 100",
        unit="%",
        reading="higher_better",
        reading_note="Higher means entries more often turn into sustained attacks.",
        methodology=md(
            "Positive as in 'Entry Outcomes (Positive / Negative)'. Also shown "
            "per method in 'Success Rate by Entry Method'.",
            SEASON_RATIO,
        ),
        source_doc=D_OA_FT,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="ft_entry_timing",
        name="Entry Timing — 15-min Bands",
        sections=[OA],
        module={OA: OA_FT},
        short_definition="Season final-third entries per 15-minute band of the match, with each band's success rate.",
        formula="entries per band; success % = positive ÷ entries in band × 100",
        unit="distribution",
        reading="contextual",
        reading_note="Shows when in the match the team gets into the final third.",
        methodology=md(
            "Six bands by entry minute: 0–15, 15–30, 30–45, 45–60, 60–75, 75–90+ "
            "(later minutes go in the last band).",
            SEASON_RATIO,
        ),
        source_doc=D_OA_FT,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="ft_build_depth",
        name="Build-up Depth — Avg Passes Before Entry",
        sections=[OA],
        module={OA: OA_FT},
        short_definition="Average number of passes in the possession before the final-third entry, per entry method.",
        formula="Σ passes before entry ÷ entries, per method",
        unit="passes",
        reading="contextual",
        reading_note="Lower means more direct routes; higher means more patient build-up.",
        methodology=md(
            "passes_before = passes (and offside passes) in the possession before "
            "the entry event.",
            SEASON_RATIO,
        ),
        source_doc=D_OA_FT,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="ft_entry_map",
        name="FT Entry Zones & Outcomes",
        sections=[MA, OA],
        module={MA: MA_FT, OA: OA_FT},
        short_definition="Pitch maps of where entries into the final third happened, coloured by method or outcome.",
        formula=None,
        unit="map",
        reading="contextual",
        reading_note="Visual summary of entry locations.",
        methodology=md(
            "Match Analysis: 'Entry Points — Method View' and 'FT Entry Zones & "
            "Outcomes' (Z14 highlighted purple, flanks cyan). Opponent Analysis: "
            "'FT Entry Points by Zone' and 'Entry Points by Method — Season', "
            "18-zone counts summed across matches.",
            GRID_18,
        ),
        source_doc=D_FT,
        season_aggregation="sum",
    ),
    # ── Chance Creation ──────────────────────────────────────────────────────
    metric(
        id="total_shots",
        name="Total Shots",
        sections=[MA, OA],
        module={MA: MA_CC, OA: OA_CC},
        short_definition="All attempts at goal by the team, including penalties.",
        formula="count of team events with type_id 13–16 (+ opponent own goals)",
        unit="count",
        reading="higher_better",
        reading_note="More shots means more attempts, regardless of quality.",
        methodology=md(
            "Shots are Opta Miss (13), Post (14), Attempt Saved (15) and Goal (16) "
            "events by the team. " + OWN_GOAL_ROWS,
            "Match Analysis subtitle: shots ÷ team possessions × 100 ('% of "
            "possessions', all possessions of the team). Opponent Analysis labels "
            "the season total 'Total Chances' with shots per match underneath. "
            + PER_MATCH,
        ),
        source_doc=D_CC,
        season_aggregation="total_per_match",
    ),
    metric(
        id="shots_in_box",
        name="In-Box",
        sections=[MA],
        module={MA: MA_CC},
        short_definition="Shots taken from inside the opponent's penalty box.",
        formula="count of shots with x ≥ 83.33 and 21.1 ≤ y ≤ 78.9; subtitle = ÷ shots × 100",
        unit="count",
        reading="higher_better",
        reading_note="Box shots are usually higher-quality chances.",
        methodology=md("A shot is in the box if its location is in " + PENALTY_BOX + ".", OWN_GOAL_ROWS),
        source_doc=D_CC,
        season_aggregation=None,
    ),
    metric(
        id="shots_out_box",
        name="Out-Box",
        sections=[MA],
        module={MA: MA_CC},
        short_definition="Shots taken from outside the opponent's penalty box.",
        formula="shots − In-Box shots; subtitle = ÷ shots × 100",
        unit="count",
        reading="contextual",
        reading_note="Long-range shooting is usually lower quality.",
        methodology=md("Complement of In-Box: every shot not located in " + PENALTY_BOX + "."),
        source_doc=D_CC,
        season_aggregation=None,
    ),
    metric(
        id="sot_pct",
        name="SoT %",
        sections=[MA, OA],
        module={MA: MA_CC, OA: OA_CC},
        short_definition="Share of the team's shots that were on target.",
        formula="shots with type_id 15 or 16 ÷ shots × 100",
        unit="%",
        reading="higher_better",
        reading_note="Higher means more shots test the goalkeeper.",
        methodology=md(
            "On target = Attempt Saved (15) or Goal (16). " + OWN_GOAL_ROWS,
            "Opponent Analysis shows it under Goals ('SoT: n (x%)').",
            SEASON_RATIO,
        ),
        notes=(
            "Opta type_id 15 also covers shots blocked by an outfield player "
            "(`Blocked` qualifier), so blocked shots count as on target here."
        ),
        source_doc=D_CC,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="xg_total",
        name="xG Total",
        sections=[MA, OA],
        module={MA: MA_CC, OA: OA_CC},
        short_definition="Summed expected goals of the team's shots in the match (Match Analysis) or season (Opponent Analysis).",
        formula="Σ per-shot xG",
        unit="xG",
        reading="higher_better",
        reading_note="Higher means more and better chances created.",
        methodology=md(
            "Per-shot xG from the shared logistic-regression xG model (distance, "
            "angle, qualifier features). " + PENALTY_XG_TEXT,
            ROW_XG_NOTE,
            "Match Analysis subtitle: xG per shot (xG ÷ shots). Opponent Analysis "
            "subtitle: xG per match; the card opens 'xG per Match — All Teams'. "
            + MODAL_PER_MATCH,
        ),
        source_doc=D_CC,
        season_aggregation="total_per_match",
    ),
    metric(
        id="xg_per_shot",
        name="xG/Shot",
        sections=[MA],
        module={MA: MA_CC},
        short_definition="Average xG of the team's shots in the match.",
        formula="xG Total ÷ Total Shots",
        unit="xG",
        reading="higher_better",
        reading_note="Higher means better average shooting positions.",
        methodology=md("Shown as the subtitle of xG Total.", OWN_GOAL_ROWS),
        source_doc=D_CC,
        season_aggregation=None,
    ),
    metric(
        id="team_goals",
        name="Goals",
        sections=[MA, OA],
        module={MA: MA_CC, OA: OA_CC},
        short_definition="Goals the team scored, including opponent own goals.",
        formula="count of team Goal events (type_id 16) + opponent own goals",
        unit="count",
        reading="higher_better",
        reading_note="More goals is better.",
        methodology=md(
            OWN_GOAL_ROWS,
            "Match Analysis subtitle: SoT% and the number of own goals included.",
        ),
        source_doc=D_CC,
        season_aggregation="sum",
    ),
    metric(
        id="chain_to_goal_matrix",
        name="Chain-to-Goal Matrix",
        sections=[MA],
        module={MA: MA_CC},
        short_definition="A table of the team's shots by attack origin, showing count, xG, SoT% and goals for each origin.",
        formula="per origin: N = shots, xG = Σ xG, SoT% = on target ÷ N × 100, GS = goals",
        unit="table",
        reading="contextual",
        reading_note="Shows which creation patterns produce volume, quality and goals.",
        methodology=md(
            "Columns: Set Piece, High Regain, Cross, Through Ball, Cut Back, "
            "Individual Play, Combination, plus TOTAL. Origins as in 'Attack "
            "Origin Breakdown'. " + OWN_GOAL_ROWS,
        ),
        source_doc=D_CC,
        season_aggregation=None,
    ),
    metric(
        id="attack_origin",
        name="Attack Origin Breakdown",
        sections=[MA, OA],
        module={MA: MA_CC, OA: OA_CC},
        short_definition="How each of the team's shots was created, in seven priority-ordered origins.",
        formula="classify_attack_origin(): first match of Through Ball → Set Piece → Individual Play → High Regain → Cut Back → Cross → Combination",
        unit="distribution",
        reading="contextual",
        reading_note="Describes the team's chance-creation style.",
        methodology=md(
            "Protected classifier `classify_attack_origin()`, first match wins:",
            "1. Through Ball — the assisting pass has the `Through ball` qualifier.\n"
            "2. Set Piece — a team restart (corner, free kick, throw-in, goal kick, "
            "penalty …) within 15 s and at most 5 passes before the shot, or a "
            "direct set-piece qualifier on the shot; restarts by the opponent do "
            "not count. Penalties always land here.\n"
            "3. Individual Play — `Individual Play` qualifier on the shot.\n"
            "4. High Regain — ball won in " + FINAL_THIRD + " and the shot within 8 s "
            "(also when the opponent's error/dispossession is itself the regain).\n"
            "5. Cut Back — a `Pull Back` pass (qualifier 195) within 12 s.\n"
            "6. Cross — a cross from a wide final-third area.\n"
            "7. Combination — every other shot (default).",
            "Set Piece, High Regain and direct-score checks also look back into "
            "previous possessions. The Set Piece card excludes penalties, which "
            "get their own Penalty card. Opponent Analysis shows season counts, "
            "per-match values, goals and conversion per origin.",
        ),
        notes=(
            "The Match Analysis caption lists 'Set Piece → High Regain → Counter → "
            "Cross → Through Ball → Combination'; that is not the code priority and "
            "there is no 'Counter' origin. The Opponent Analysis caption matches the code."
        ),
        source_doc=D_ORIGIN,
        season_aggregation="sum",
    ),
    metric(
        id="penalty_card",
        name="Penalty",
        sections=[MA, OA],
        module={MA: MA_CC, OA: OA_CC},
        short_definition="Penalties scored, with penalty kicks taken and conversion rate.",
        formula="value = penalties scored; subtitle = kicks taken and scored ÷ taken × 100",
        unit="count",
        reading="higher_better",
        reading_note="More penalties scored is better; conversion shows reliability from the spot.",
        methodology=md(
            "A penalty is a shot (type_id 13–16) with the `Penalty` qualifier; "
            "Opta type_id 84 rows are excluded. 'Awarded' = penalty shots taken; "
            "'scored' = those that are goals; conversion = scored ÷ awarded × 100 "
            "(— when none). Season values sum the `is_penalty` rows of "
            "shots_{season}.parquet.",
            SEASON_RATIO,
        ),
        notes="'Awarded' counts penalty kicks taken (each attempt), not penalties given by the referee.",
        source_doc=D_ORIGIN,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="shot_quality_tiers",
        name="Shot Quality Tiers",
        sections=[MA],
        module={MA: MA_CC},
        short_definition="The team's shots split into Converted, Big Chance and Speculative.",
        formula="goal → Converted; else Big Chance qualifier → Big Chance; else Speculative",
        unit="distribution",
        reading="contextual",
        reading_note="More Big Chance and Converted shots means better chance quality.",
        methodology=md(
            "classify_shot_quality(): Converted (tier 3) = the shot was a goal; "
            "Big Chance (tier 2) = Opta `Big Chance` qualifier and not scored; "
            "Speculative (tier 0) = everything else. xG is not used. There is no "
            "tier 1; on-target is a separate measure (SoT %). " + OWN_GOAL_ROWS,
        ),
        source_doc=D_TIERS,
        season_aggregation=None,
    ),
    metric(
        id="xg_by_origin",
        name="xG by Attack Origin",
        sections=[MA],
        module={MA: MA_CC},
        short_definition="The team's xG split by attack origin.",
        formula="Σ xG of shots per origin",
        unit="xG",
        reading="contextual",
        reading_note="Shows which patterns generate the most expected goals.",
        methodology=md("Origins as in 'Attack Origin Breakdown'; xG as in 'xG Total'. Own-goal rows are excluded."),
        source_doc=D_CC,
        season_aggregation=None,
    ),
    metric(
        id="attack_origin_zones",
        name="Attack Origin Zones",
        sections=[MA, OA],
        module={MA: MA_CC, OA: OA_CC},
        short_definition="Pitch map of where the team's shots were taken, coloured by attack origin.",
        formula=None,
        unit="map",
        reading="contextual",
        reading_note="Visual summary of shot locations by creation pattern.",
        methodology=md(
            "Each shot plotted at its location; filled markers = on target or "
            "goal, open markers = missed or blocked. Opponent Analysis shows the "
            "season's shots.",
            COORDS,
        ),
        source_doc=D_CC,
        season_aggregation="sum",
    ),
    metric(
        id="top_origin",
        name="Top Origin",
        sections=[OA],
        module={OA: OA_CC},
        short_definition="The attack origin that produced most of the team's shots this season.",
        formula="mode of the shot origin column",
        unit="category",
        reading="contextual",
        reading_note="Identifies the dominant chance-creation pattern.",
        methodology=md(
            "Mode over shots_{season}.parquet origins (Combination if no shots). "
            "The card opens 'Goal Types — Season'.",
        ),
        source_doc=D_OA_CC,
        season_aggregation="sum",
    ),
    metric(
        id="origin_conversion_pct",
        name="Conv %",
        sections=[OA],
        module={OA: OA_CC},
        short_definition="For each attack origin, the share of its shots that became goals this season.",
        formula="goals from origin ÷ shots from origin × 100",
        unit="%",
        reading="higher_better",
        reading_note="Higher means the pattern is finished efficiently; unstable on small samples.",
        methodology=md(
            "Shown in the origin table with Total and '/ Match' (shots of the "
            "origin ÷ matches played). Empty when the origin has no shots.",
            SEASON_RATIO,
        ),
        source_doc=D_OA_CC,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="goals_by_origin",
        name="Goal Types — Season",
        sections=[OA],
        module={OA: OA_CC},
        short_definition="The team's season goals split by attack origin.",
        formula="count of goals per origin",
        unit="count",
        reading="contextual",
        reading_note="Shows which patterns actually produce goals.",
        methodology=md(
            "Goals from shots_{season}.parquet grouped by origin, with each "
            "origin's share of the season's goals. Penalty goals are counted under "
            "Set Piece here; opponent own goals appear as 'Own Goal'.",
        ),
        source_doc=D_OA_CC,
        season_aggregation="sum",
    ),
]
