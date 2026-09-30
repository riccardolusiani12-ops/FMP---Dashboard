# -*- coding: utf-8 -*-
"""
Conversione JSON Opta → CSV (logica di `1_opta event mapping_eng.ipynb`, cella 2).

Le funzioni tra i marcatori BEGIN/END sono copiate TESTUALMENTE dal notebook
(stesse colonne, stessi nomi file, stessa gestione JSONP, stesse mappature
formazioni). Non modificarle: ogni cambio romperebbe la compatibilità con i
CSV già presenti nella dash. Cambiano solo i percorsi dei transformer, che ora
vivono in pipeline/opta_lookups/, e il ciclo principale, ora `convert_file()`.
"""

import json
from pathlib import Path

import pandas as pd

from config import LOOKUPS_DIR

# ==========================
# LOAD TRANSFORMERS
# ==========================
event_types_path = LOOKUPS_DIR / "opta_event_types.csv"
qualifier_types_path = LOOKUPS_DIR / "opta_qualifier_types.csv"

event_types = pd.read_csv(event_types_path)
qualifier_types_df = pd.read_csv(qualifier_types_path)


# ───────────────────────── BEGIN: copia testuale dal notebook 1, cella 2 ─────────────────────────
# ==========================
# ROBUST JSON / JSONP LOADER
# ==========================
def load_json_robusto(json_path: Path):
    """
    Load JSON or Opta-JSON wrapped in JSONP:
    - Supports single-line or multi-line files.
    - Strips BOM.
    - If the file starts with a weird identifier (JSONP),
      it looks for the first '{' or '[' and the last '}' or ']'
      and only uses that part.
    - Raises ValueError if the file is empty or looks like HTML.
    """
    with open(json_path, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()

    if not raw or not raw.strip():
        raise ValueError("Empty file")

    # Remove BOM and weird whitespace at start/end
    raw = raw.lstrip("\ufeff").strip()

    if not raw:
        raise ValueError("Empty file after stripping BOM/whitespace")

    # --- Case 1: pure JSON already starting with { or [ ---
    first_non_space = None
    for ch in raw:
        if not ch.isspace():
            first_non_space = ch
            break

    if first_non_space in ("{", "["):
        return json.loads(raw)

    # --- Case 2: JSONP style "callback(...json...)" ---
    start_obj = raw.find("{")
    start_arr = raw.find("[")
    candidates = [pos for pos in (start_obj, start_arr) if pos != -1]

    if candidates:
        start = min(candidates)
        opening_char = raw[start]
        closing_char = "}" if opening_char == "{" else "]"

        end = raw.rfind(closing_char)
        if end == -1 or end <= start:
            raise ValueError("Could not find a valid closing bracket for JSON inside JSONP")

        possible_json = raw[start:end + 1]
        return json.loads(possible_json)

    # --- Case 3: looks like HTML (403/404 errors, etc.) ---
    if raw.lstrip().startswith("<"):
        raise ValueError("File looks like HTML, not JSON/JSONP")

    raise ValueError("Content not recognized as JSON/JSONP")


# ==========================
# MAIN PROCESSING FUNCTION
# ==========================
def process_opta_json_with_qualifier_columns(json_data, event_types, qualifier_types_df):
    # Extract matchInfo and contestant details
    match_info = json_data.get("matchInfo", {})
    match_id = match_info.get("id", "N/A")
    coverage_level = match_info.get("coverageLevel", "N/A")
    local_date = match_info.get("localDate", "N/A")
    local_time = match_info.get("localTime", "N/A")
    week = match_info.get("week", "N/A")
    number_of_periods = match_info.get("numberOfPeriods", "N/A")
    period_length = match_info.get("periodLength", "N/A")
    description = match_info.get("description", "N/A")

    # Extract competition details
    competition = match_info.get("competition", {}) or {}
    competition_id = competition.get("id", "N/A")
    competition_name = competition.get("name", "N/A")
    competition_known_name = competition.get("knownName", "N/A")
    competition_sponsor_name = competition.get("sponsorName", "N/A")
    competition_code = competition.get("competitionCode", "N/A")

    # Extract venue details
    venue = match_info.get("venue", {}) or {}
    venue_id = venue.get("id", "N/A")
    venue_long_name = venue.get("longName", "N/A")

    # Extract contestant details
    contestants = match_info.get("contestant", []) or []
    team_info = {
        contestant["id"]: {
            "name": contestant.get("officialName", "N/A"),
            "code": contestant.get("code", "N/A"),
            "position": contestant.get("position", "N/A")
        }
        for contestant in contestants
    }

    qualifier_types = qualifier_types_df["qualifierTypeName"].values
    qualifier_type_ids = qualifier_types_df["qualifierTypeId"].values

    events = json_data.get("liveData", {}).get("event", []) or []
    processed_events = []

    team_formations = {}
    team_player_mappings = {}  # {team_id: {player_id: {jersey, formation_pos, player_pos}}}

    for event in events:
        general_id = event.get("id")
        event_id = event.get("eventId")
        type_id = event.get("typeId")
        period_id = event.get("periodId")
        time_min = event.get("timeMin")
        time_sec = event.get("timeSec")
        contestant_id = event.get("contestantId")
        player_id = event.get("playerId")
        player_name = event.get("playerName")
        x = event.get("x")
        y = event.get("y")
        outcome = event.get("outcome")
        timeStamp = event.get("timeStamp")
        lastModified = event.get("lastModified")

        if type_id in event_types['eventTypeId'].values:
            event_name = event_types.loc[
                event_types['eventTypeId'] == type_id, 'eventTypeName'
            ].values[0]
        else:
            event_name = "Unknown"

        team_details = team_info.get(
            contestant_id,
            {"name": "N/A", "code": "N/A", "position": "N/A"}
        )

        qualifiers = event.get("qualifier", []) or []
        qualifier_values = {qualifier_name: "N/A" for qualifier_name in qualifier_types}
        represented_qualifiers = []
        non_represented_qualifiers = []

        for qualifier in qualifiers:
            qualifier_id = qualifier.get("qualifierId")
            qualifier_value = qualifier.get("value", None)
            if qualifier_id in qualifier_type_ids:
                qualifier_name = qualifier_types_df.loc[
                    qualifier_types_df["qualifierTypeId"] == qualifier_id, "qualifierTypeName"
                ].values[0]
                qualifier_values[qualifier_name] = qualifier_value if qualifier_value else "Si"
                represented_qualifiers.append(
                    f"{qualifier_name}: {qualifier_value if qualifier_value else 'Si'}"
                )
            else:
                non_represented_qualifiers.append(
                    f"ID: {qualifier_id}, Value: {qualifier_value if qualifier_value else 'N/A'}"
                )

        # Formation + player mapping block
        if event_name in ["Team setp up", "Formation change"]:
            team_formation_value = qualifier_values.get("Team Formation", None)
            if team_formation_value and team_formation_value != "N/A":
                team_formations[contestant_id] = team_formation_value

            involved = qualifier_values.get("Involved", "").split(", ")
            jersey_numbers = qualifier_values.get("Jersey Number", "").split(", ")
            team_player_formation = qualifier_values.get("Team Player Formation", "").split(", ")
            player_positions = qualifier_values.get("Player Position", "").split(", ")

            mapping = {}
            for idx, pid in enumerate(involved):
                pid = pid.strip()
                if not pid:
                    continue
                mapping[pid] = {
                    "Jersey Number": jersey_numbers[idx] if idx < len(jersey_numbers) else "N/A",
                    "Team Player Formation": team_player_formation[idx] if idx < len(team_player_formation) else "N/A",
                    "Player Position": player_positions[idx] if idx < len(player_positions) else "N/A"
                }
            team_player_mappings[contestant_id] = mapping

        qualifier_values["Team Formation"] = team_formations.get(contestant_id, "N/A")
        player_mapping = team_player_mappings.get(contestant_id, {}).get(player_id, {})

        qualifier_values["Jersey Number"] = player_mapping.get("Jersey Number", "N/A")
        qualifier_values["Team Player Formation"] = player_mapping.get("Team Player Formation", "N/A")
        qualifier_values["Player Position"] = player_mapping.get("Player Position", "N/A")

        processed_events.append({
            "general_id": general_id,
            "event_id": event_id,
            "event": event_name,
            "type_id": type_id,
            "period_id": period_id,
            "time_min": time_min,
            "time_sec": time_sec,
            "contestant_id": contestant_id,
            "team_name": team_details["name"],
            "team_code": team_details["code"],
            "team_position": team_details["position"],
            "player_id": player_id,
            "player_name": player_name,
            "x": x,
            "y": y,
            "outcome": outcome,
            "timeStamp": timeStamp,
            "lastModified": lastModified,
            "match_id": match_id,
            "coverage_level": coverage_level,
            "local_date": local_date,
            "local_time": local_time,
            "week": week,
            "number_of_periods": number_of_periods,
            "period_length": period_length,
            "description": description,
            "represented_qualifiers": "; ".join(represented_qualifiers),
            "non_represented_qualifiers": "; ".join(non_represented_qualifiers),
            **qualifier_values,

            "competition_id": competition_id,
            "competition_name": competition_name,
            "competition_known_name": competition_known_name,
            "competition_sponsor_name": competition_sponsor_name,
            "competition_code": competition_code,

            "venue_id": venue_id,
            "venue_long_name": venue_long_name,
        })

    return pd.DataFrame(processed_events)


# ==========================
# FORMATION MAPPINGS
# ==========================
formation_mapping = {
    "1": "",
    "2": "442",
    "3": "41212",
    "4": "433",
    "5": "451",
    "6": "4411",
    "7": "4141",
    "8": "4231",
    "9": "4321",
    "10": "532",
    "11": "541",
    "12": "352",
    "13": "343",
    "14": "31312",
    "15": "4222",
    "16": "3511",
    "17": "3421",
    "18": "3412",
    "19": "3142",
    "20": "",
    "21": "4132",
    "22": "",
    "23": "4312",
}

formation_position_mapping = {
    "442":   { "1": "GK", "2": "RB",  "3": "LB",  "4": "MC",  "5": "CB",  "6": "CB",  "7": "RM",  "8": "CM",  "9": "CF",  "10": "CF",  "11": "LM" },
    "41212": { "1": "GK", "2": "RB",  "3": "LB",  "4": "CDM", "5": "CB",  "6": "CB",  "7": "MC",  "8": "CAM", "9": "CF",  "10": "CF",  "11": "MC" },
    "433":   { "1": "GK", "2": "RB",  "3": "LB",  "4": "MC",  "5": "CB",  "6": "CB",  "7": "MC",  "8": "MC",  "9": "CF",  "10": "LW",  "11": "RW" },
    "451":   { "1": "GK", "2": "RB",  "3": "LB",  "4": "MC",  "5": "CB",  "6": "CB",  "7": "RM",  "8": "MC",  "9": "CAM", "10": "CF",  "11": "LM" },
    "4411":  { "1": "GK", "2": "RB",  "3": "LB",  "4": "MC",  "5": "CB",  "6": "CB",  "7": "RM",  "8": "MC",  "9": "CF",  "10": "SS",  "11": "LM" },
    "4141":  { "1": "GK", "2": "RB",  "3": "LB",  "4": "CDM", "5": "CB",  "6": "CB",  "7": "RM",  "8": "MC",  "9": "CF",  "10": "MC",  "11": "LM" },
    "4231":  { "1": "GK", "2": "RB",  "3": "LB",  "4": "CDM", "5": "CB",  "6": "CB",  "7": "RW",  "8": "CDM", "9": "CF",  "10": "CAM", "11": "LW" },
    "4321":  { "1": "GK", "2": "RB",  "3": "LB",  "4": "CDM", "5": "CB",  "6": "CB",  "7": "MC",  "8": "MC",  "9": "CF",  "10": "CAM", "11": "CAM" },
    "532":   { "1": "GK", "2": "RWB", "3": "LWB", "4": "CB",  "5": "CB",  "6": "CB",  "7": "MC",  "8": "CDM", "9": "CF",  "10": "CF",  "11": "MC" },
    "541":   { "1": "GK", "2": "RWB", "3": "LWB", "4": "CB",  "5": "CB",  "6": "CB",  "7": "RM",  "8": "MC",  "9": "CF",  "10": "MC",  "11": "LM" },
    "352":   { "1": "GK", "2": "RWB", "3": "LWB", "4": "CB",  "5": "CB",  "6": "CB",  "7": "MC",  "8": "MC",  "9": "CF",  "10": "CF",  "11": "CAM" },
    "343":   { "1": "GK", "2": "RWB", "3": "LWB", "4": "CB",  "5": "CB",  "6": "CB",  "7": "MC",  "8": "MC",  "9": "CF",  "10": "RW",  "11": "LW" },
    "31312": { "1": "GK", "2": "RWB", "3": "LWB", "4": "CDM","5": "CB",  "6": "CB",  "7": "CB",  "8": "MC",  "9": "CF",  "10": "CAM", "11": "SS" },
    "4222":  { "1": "GK", "2": "RB",  "3": "LB",  "4": "CDM","5": "CB",  "6": "CB",  "7": "CDM","8": "CAM", "9": "CF",  "10": "CF",  "11": "CAM" },
    "3511":  { "1": "GK", "2": "RWB", "3": "LWB", "4": "CB",  "5": "CB",  "6": "CB",  "7": "MC",  "8": "MC",  "9": "CF",  "10": "SS",  "11": "CAM" },
    "3421":  { "1": "GK", "2": "RWB", "3": "LWB", "4": "CB",  "5": "CB",  "6": "CB",  "7": "MC",  "8": "MC",  "9": "CAM", "10": "CAM", "11": "CF" },
    "3412":  { "1": "GK", "2": "RWB", "3": "LWB", "4": "CB",  "5": "CB",  "6": "CB",  "7": "MC",  "8": "MC",  "9": "CAM", "10": "CF",  "11": "CF" },
}

def get_position(row):
    formation = row.get("formation", "")
    pos_number = str(row.get("Team Player Formation", ""))
    return formation_position_mapping.get(formation, {}).get(pos_number, "N/A")


# ==========================
# 2) CHANGE: OUTPUT NAME LIKE SERIE A FOLDER
# ==========================
# ==========================
# TEAM NAME NORMALIZATION (for filenames)
# ==========================
TEAM_ALIASES = {
    "internazionale": "Inter",
    "inter": "Inter",
    "hellas verona": "Verona",
    "verona": "Verona",
}

def normalize_team_name(name: str) -> str:
    """
    Canonicalize team names so filenames are consistent with your existing CSVs.
    Specifically:
      - Internazionale / Inter -> Inter
      - Hellas Verona / Verona -> Verona
    """
    if not name:
        return name

    n = " ".join(str(name).strip().split())  # trim + collapse spaces
    nl = n.casefold()

    # exact matches first
    if nl in TEAM_ALIASES:
        return TEAM_ALIASES[nl]

    # robust contains-based fallback (covers things like "FC Internazionale Milano")
    if "internazionale" in nl:
        return "Inter"
    if "hellas verona" in nl:
        return "Verona"

    return n

def build_output_filename(json_data: dict) -> str:
    """
    Returns a filename like:
    week_home_away_matchid.csv
    Example: 1_Atalanta_Pisa_chhs4jqieq3l8wyuww0wt8h78.csv
    """
    mi = json_data.get("matchInfo", {}) or {}
    week = mi.get("week", "NA")
    match_id = mi.get("id", "NA")

    desc = (mi.get("description") or "").strip()

    home, away = "Home", "Away"
    if " v " in desc:
        home, away = [p.strip() for p in desc.split(" v ", 1)]
    elif " vs " in desc.lower():
        parts = desc.replace("VS", "vs").split(" vs ", 1)
        if len(parts) == 2:
            home, away = parts[0].strip(), parts[1].strip()
    else:
        contestants = mi.get("contestant", []) or []
        home_c = next((c for c in contestants if str(c.get("position", "")).lower() == "home"), None)
        away_c = next((c for c in contestants if str(c.get("position", "")).lower() == "away"), None)
        if home_c:
            home = home_c.get("officialName", home)
        if away_c:
            away = away_c.get("officialName", away)

    # ✅ Normalize team names so Inter/Internazionale and Verona/Hellas Verona become consistent
    home = normalize_team_name(home)
    away = normalize_team_name(away)

    def clean(s: str) -> str:
        return (
            str(s).replace("/", "-")
                  .replace("\\", "-")
                  .replace(":", "-")
                  .strip()
        )

    return f"{week}_{clean(home)}_{clean(away)}_{match_id}.csv"


# ───────────────────────── END: copia testuale dal notebook 1, cella 2 ─────────────────────────


def convert_file(json_path: Path, result_dir: Path, skip_existing: bool = True) -> Path:
    """
    Corpo del ciclo principale del notebook per un singolo file.
    Ritorna il percorso del CSV (creato ora o già esistente).
    """
    json_data = load_json_robusto(json_path)

    out_name = build_output_filename(json_data)
    out_path = result_dir / out_name
    if skip_existing and out_path.exists():
        return out_path

    df = process_opta_json_with_qualifier_columns(
        json_data, event_types, qualifier_types_df
    )

    df['formation'] = (
        df['Team Formation']
        .astype(str)
        .map(formation_mapping)
        .fillna("")
    )

    df["position"] = df.apply(get_position, axis=1)

    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    return out_path
