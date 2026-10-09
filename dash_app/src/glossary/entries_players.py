"""
Glossary entries for Player Analysis (Match Analysis per match, Opponent
Analysis per season).
"""

from __future__ import annotations

from src.glossary._common import D_PLAYER, D_PV, OPEN_PLAY, SEASON_RATIO, md, metric

MA = "match_analysis"
OA = "opponent_analysis"
PLAYER = "Player Analysis"
BOTH = {MA: PLAYER, OA: PLAYER}

_MATCH = (
    "**Match Analysis:** per-player values for the selected team in the match "
    "(player_analysis.analyse_player_analysis); each card is a player ranking and "
    "opens a breakdown modal. Minutes per player come from substitutions, "
    "dismissals and the last 'End' event of the match."
)
_SEASON = (
    "**Opponent Analysis:** season total ÷ season minutes × 90 ('Raw /90'). "
    "Players are ranked on the shrinkage-adjusted per-90 ('Adj /90'): "
    "w = minutes ÷ (minutes + K), adj = w × raw per-90 + (1 − w) × role-group "
    "mean, with K (minutes) estimated per metric and role group by split-half "
    "reliability (heuristic fallback, clamped to 200–3000). 'Role %ile' is the "
    "within-role percentile of the adjusted value (pandas rank, pct) among "
    "Serie A players of the same role with at least 450 minutes. Players under "
    "450 minutes are kept but dimmed; unclassified players are not shrunk."
)
_SEASON_PCT = (
    "**Opponent Analysis:** the season percentage ('Season %') is recomputed "
    "from summed counts and ranked as is (no shrinkage); 'Role %ile' as for "
    "the other KPIs."
)
_PVA = (
    "Possession value comes from the ML model in utils/pv_model.py "
    "(pv_model_serie_a.pkl), which predicts P(goal) for an event from its "
    "location and context."
)


def _kpi(id, name, short, formula, reading, note, rule, extra=None, pct=False, notes=None):
    return metric(
        id=id, name=name, sections=[MA, OA], module=BOTH,
        short_definition=short, formula=formula,
        unit="%" if pct else "per 90",
        reading=reading, reading_note=note,
        methodology=md(rule, extra or "", _MATCH, _SEASON_PCT if pct else _SEASON,
                       SEASON_RATIO if pct else ""),
        notes=notes, source_doc=D_PLAYER,
        season_aggregation="ratio_of_sums" if pct else "shrinkage_adjusted",
    )


ENTRIES: list[dict] = [
    # ── Possession value ─────────────────────────────────────────────────────
    metric(
        id="offensive_pva",
        name="Offensive PVA",
        sections=[MA, OA],
        module=BOTH,
        short_definition="Possession value a player added with the ball: how much their actions raised the team's chance of scoring.",
        formula="Σ over the player's on-ball actions of P(goal) after − P(goal) before",
        unit="PV",
        reading="higher_better",
        reading_note="Higher means the player moved the ball into more dangerous situations.",
        methodology=md(
            _PVA,
            "Each possession is scored event by event; an action's PVA is its "
            "score minus the previous event's score (pva_sequence). Offensive PVA "
            "sums this over the player's passes, touches, take-ons, shots, "
            "dispossessions and offside passes.",
            "Shown in 'Team PV Overview', the 'PVA per 90' bars (players under 20 "
            "minutes dimmed in Match Analysis), the 'Event Map — Possession Value "
            "Added' and the 'Possession Sequence Viewer'. Season values sum the "
            "match values before per-90 and shrinkage.",
        ),
        notes=(
            "possession-value-model.md documents the 16×12 grid model in "
            "analytics/possession_value.py; Player Analysis uses the separate ML "
            "model in utils/pv_model.py."
        ),
        source_doc=D_PV,
        season_aggregation="shrinkage_adjusted",
    ),
    metric(
        id="defensive_pva",
        name="Defensive PVA",
        sections=[MA, OA],
        module=BOTH,
        short_definition="Possession value a player's defensive actions denied the opponent.",
        formula="Σ over the player's defensive actions of P(goal) at the action's location and type",
        unit="PV",
        reading="higher_better",
        reading_note="Higher means the player's defending stopped more dangerous situations.",
        methodology=md(
            _PVA,
            "Each tackle, interception, ball recovery, clearance, blocked pass, "
            "challenge or aerial is scored as score(x, y, type_id) — the goal "
            "probability the action takes away at that spot. Always positive.",
            "Season values sum the match values before per-90 and shrinkage.",
        ),
        source_doc=D_PV,
        season_aggregation="shrinkage_adjusted",
    ),
    metric(
        id="total_pva",
        name="Total PVA",
        sections=[MA, OA],
        module=BOTH,
        short_definition="A player's offensive plus defensive possession value added.",
        formula="Offensive PVA + Defensive PVA",
        unit="PV",
        reading="higher_better",
        reading_note="Higher means more overall value contributed.",
        methodology=md(
            _PVA,
            "Sum of the two components. Opponent Analysis shows it per 90 "
            "('PVA per 90', 'Adj PVA/90' in Squad Overview).",
            _SEASON,
        ),
        source_doc=D_PV,
        season_aggregation="shrinkage_adjusted",
    ),
    metric(
        id="cumulative_possession_value",
        name="Cumulative Possession Value",
        sections=[MA],
        module={MA: PLAYER},
        short_definition="Running total of possession value along one possession, action by action.",
        formula="cumulative Σ of per-action PVA in the possession",
        unit="PV",
        reading="contextual",
        reading_note="Shows which actions built or lost danger within a sequence.",
        methodology=md(
            _PVA,
            "Shown in the 'Possession Sequence Viewer' for the team's "
            "highest-swing possessions (Σ |PV change| across the chain); each "
            "action is a bar (value added / value lost) with the running total.",
        ),
        source_doc=D_PV,
        season_aggregation=None,
    ),
    # ── In possession ────────────────────────────────────────────────────────
    _kpi("passes_completed", "Passes Completed",
         "Successful passes by the player.", "passes with outcome 1",
         "higher_better", "More completed passes means more involvement on the ball.",
         "Opta Pass events (type_id 1) by the player with outcome 1. The breakdown also shows attempts."),
    _kpi("pass_completion_pct", "Pass Completion %",
         "Share of the player's passes that reached a teammate.",
         "Passes Completed ÷ Passes Attempted × 100",
         "higher_better", "Higher means fewer wasted passes; depends on role and risk.",
         "Pass events with outcome 1 ÷ all Pass events by the player.", pct=True),
    _kpi("ball_progressions", "Ball Progressions",
         "Successful passes or take-ons that moved the ball at least 10 units towards goal.",
         "actions with outcome 1 and end x − start x ≥ 10",
         "higher_better", "More progressions means more ball advancement.",
         "Counted on completed passes and completed take-ons whose end point "
         "(`Pass End X`) is at least 10 x-units ahead of the start.",
         notes="The definition mentions carries; carries have no end point in the data and are not counted."),
    _kpi("line_breaks", "Line Breaks",
         "Completed forward passes that crossed a third-of-the-pitch line, advancing at least 8 units.",
         "completed passes with start x < 33.33 ≤ end x or start x < 66.67 ≤ end x, end x − start x ≥ 8",
         "higher_better", "More line breaks means more vertical progression past lines.",
         "The breakdown shows attempts (any outcome), completions and LB % "
         "(completed ÷ attempted × 100)."),
    _kpi("switches_of_play", "Switches of Play",
         "Passes that switched the play from one side of the pitch to the other.",
         "passes with the Switch of play qualifier (fallback: |end y − start y| ≥ 40)",
         "contextual", "A style trait; useful against compact blocks.",
         "Any pass (any outcome) with the Opta `Switch of play` qualifier; only "
         "when the qualifier column is absent, a pass spanning ≥ 40 y-units counts."),
    _kpi("crosses_completed", "Crosses Completed",
         "Crosses by the player that reached a teammate.",
         "passes with the Cross qualifier and outcome 1",
         "higher_better", "More completed crosses means more effective wide delivery.",
         "Pass events with the Opta `Cross` qualifier and outcome 1; the breakdown also shows attempts."),
    _kpi("take_ons", "Take-Ons",
         "Dribble attempts to beat an opponent.", "count of Take On events",
         "contextual", "Volume of dribbling attempts, successful or not.",
         "Opta Take On events (type_id 3) by the player, any outcome."),
    _kpi("attempts_at_goal", "Attempts at Goal",
         "Shots by the player, including penalties.", "count of type_id 13–16",
         "higher_better", "More attempts means more shooting involvement.",
         "Opta Miss, Post, Attempt Saved and Goal events by the player."),
    _kpi("player_goals", "Goals",
         "Goals scored by the player.", "count of Goal events (type_id 16)",
         "higher_better", "More goals is better.",
         "Opta Goal events credited to the player, penalties included.",
         notes="Own goals are not filtered out: an own goal (Goal event with the "
               "`own goal` qualifier) counts as a goal for the player who scored it."),
    # ── Out of possession ────────────────────────────────────────────────────
    _kpi("tackles_won", "Tackles Won",
         "Tackles in which the player won the ball.", "Tackle events with outcome 1",
         "higher_better", "More tackles won means more successful ground duels.",
         "Opta Tackle events (type_id 7) with outcome 1; the breakdown also shows tackles made."),
    _kpi("tackles_made", "Tackles Made",
         "All tackles attempted by the player.", "count of Tackle events",
         "contextual", "Volume of defensive engagement, successful or not.",
         "Opta Tackle events (type_id 7) by the player, any outcome."),
    _kpi("interceptions", "Interceptions",
         "Opponent passes the player cut out.", "count of Interception events (type_id 8)",
         "higher_better", "More interceptions means better reading of play.",
         "Opta Interception events by the player."),
    _kpi("blocks", "Blocks",
         "Opponent passes or crosses the player blocked.", "count of Blocked Pass events (type_id 74)",
         "higher_better", "More blocks means more passes stopped at source.",
         "Opta Blocked Pass events by the player."),
    _kpi("clearances", "Clearances",
         "Times the player cleared the ball away from danger.", "count of Clearance events (type_id 12)",
         "contextual", "High counts often reflect defending deep rather than quality.",
         "Opta Clearance events by the player."),
    _kpi("aerial_duels_won", "Aerial Duels Won",
         "Aerial duels the player won.", "Aerial events with outcome 1",
         "higher_better", "More aerials won means more dominance in the air.",
         "Opta Aerial events (type_id 44) with outcome 1; the breakdown also "
         "shows all aerial duels contested."),
    _kpi("possession_regains", "Possession Regains",
         "High regains: the player won the ball back in the attacking third in open play.",
         "ball recoveries, interceptions and won tackles at x ≥ 66.7, open play",
         "higher_better", "More regains means a more effective high press.",
         "Reuses high_regains.detect_high_regains(): Ball Recovery, Interception "
         "and Tackle (outcome 1) events at x ≥ 66.7 in " + OPEN_PLAY + ", "
         "counted by the acting player.",
         notes="Despite the general label, only regains in the attacking third count."),
    # ── Season squad overview (Opponent Analysis) ────────────────────────────
    metric(
        id="role_group",
        name="Role",
        sections=[OA],
        module={OA: PLAYER},
        short_definition="The player's season role group, from the positions of the matches they started.",
        formula="role group with the most started minutes",
        unit="category",
        reading="contextual",
        reading_note="Defines the peer group for percentiles and shrinkage.",
        methodology=md(
            "Opta per-event positions collapse to GK, CB, FB, DM, CM, WM, AM, W, CF; "
            "for each match the player started, their minutes are credited to that "
            "match's role and the role with the most started minutes wins. "
            "Players with no role are UNCL (Unclassified) and get no percentile.",
        ),
        source_doc=D_PLAYER,
        season_aggregation="sum",
    ),
    metric(
        id="appearances",
        name="Apps",
        sections=[OA],
        module={OA: PLAYER},
        short_definition="Season matches in which the player played at least one minute.",
        formula="count of matches with minutes > 0",
        unit="count",
        reading="contextual",
        reading_note="Shows availability and use.",
        methodology=md("Shown in Squad Overview. Players featuring in under 50% of the team's matchdays are flagged as partial-season."),
        source_doc=D_PLAYER,
        season_aggregation="sum",
    ),
    metric(
        id="season_minutes",
        name="Min",
        sections=[MA, OA],
        module=BOTH,
        short_definition="Minutes the player was on the pitch (in the match, or summed over the season).",
        formula="(off, dismissal or full-time minute) − (on minute or 0); Σ over matches for the season",
        unit="minutes",
        reading="contextual",
        reading_note="Context for every per-90 value; low minutes make rates unreliable.",
        methodology=md(
            "Per-match minutes = (substitution-off, dismissal or full-time minute) "
            "− (substitution-on minute or 0), clamped to the match length; the "
            "full-time minute is the last 'End' event, so stoppage time counts. "
            "Match Analysis dims players under 20 minutes in per-90 charts. "
            "Season minutes sum the match minutes; players under 450 minutes "
            "(MIN_MINUTES_DIM) are dimmed ('low min') and excluded from "
            "percentile baselines.",
        ),
        source_doc=D_PLAYER,
        season_aggregation="sum",
    ),
    metric(
        id="minutes_share",
        name="Min%",
        sections=[OA],
        module={OA: PLAYER},
        short_definition="The player's minutes as a share of all the minutes the team could have given them.",
        formula="minutes ÷ (team matchdays × 90) × 100",
        unit="%",
        reading="contextual",
        reading_note="High values mean a regular starter.",
        methodology=md("Stoppage time is not added to the 90-minute denominator, so values can slightly exceed 100%.", SEASON_RATIO),
        source_doc=D_PLAYER,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="pva_consistency",
        name="σ PVA",
        sections=[OA],
        module={OA: PLAYER},
        short_definition="How much the player's Total PVA varies from match to match.",
        formula="standard deviation of per-match Total PVA",
        unit="PV",
        reading="lower_better",
        reading_note="Lower means steadier contributions from match to match.",
        methodology=md(
            "Population standard deviation (ddof 0) of the player's per-match "
            "Total PVA over the matches they featured in; 0 with fewer than two matches.",
        ),
        source_doc=D_PLAYER,
        season_aggregation="sum",
    ),
    metric(
        id="adjusted_per90",
        name="Adj /90",
        sections=[OA],
        module={OA: PLAYER},
        short_definition="A player's per-90 value pulled towards the role average in proportion to how few minutes they played.",
        formula="w × raw per-90 + (1 − w) × role mean, w = minutes ÷ (minutes + K)",
        unit="per 90",
        reading="contextual",
        reading_note="Read with the metric it adjusts; it is the value players are ranked on.",
        methodology=md(_SEASON),
        source_doc=D_PLAYER,
        season_aggregation="shrinkage_adjusted",
    ),
    metric(
        id="raw_per90",
        name="Raw /90",
        sections=[OA],
        module={OA: PLAYER},
        short_definition="A player's observed season rate per 90 minutes, before any adjustment.",
        formula="season total ÷ season minutes × 90",
        unit="per 90",
        reading="contextual",
        reading_note="Read with the metric; unreliable for players with few minutes.",
        methodology=md(_SEASON, SEASON_RATIO),
        source_doc=D_PLAYER,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="season_pct",
        name="Season %",
        sections=[OA],
        module={OA: PLAYER},
        short_definition="For percentage KPIs, the player's season percentage from summed counts.",
        formula="Σ completed ÷ Σ attempted × 100",
        unit="%",
        reading="contextual",
        reading_note="Read with the KPI (Pass Completion %, Line Break %).",
        methodology=md(_SEASON_PCT, SEASON_RATIO),
        source_doc=D_PLAYER,
        season_aggregation="ratio_of_sums",
    ),
    metric(
        id="role_percentile",
        name="Role %ile",
        sections=[OA],
        module={OA: PLAYER},
        short_definition="Where the player ranks among Serie A players of the same role on a metric, from 0 to 100.",
        formula="pandas rank(pct=True) × 100 of the adjusted value within role group",
        unit="percentile",
        reading="higher_better",
        reading_note="Higher means better than more same-role players on that metric.",
        methodology=md(
            _SEASON,
            "Computed per metric over all Serie A teams of the season; roles with "
            "fewer than 3 qualifying players get no percentile.",
        ),
        source_doc=D_PLAYER,
        season_aggregation="rank_percentile",
    ),
]
