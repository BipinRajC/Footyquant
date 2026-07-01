"""Update clean_wc_fixtures bracket slots with actual team names after results.

Reads completed knockout results, resolves winners through the bracket,
and updates future round matches in clean_wc_fixtures with real team names.
"""

import os
from supabase import create_client

BRACKET = {
    "round_of_32": {
        "R32_1": {"teams": ["Germany", "Paraguay"], "winner_to": "R16_1"},
        "R32_2": {"teams": ["France", "Sweden"], "winner_to": "R16_1"},
        "R32_3": {"teams": ["South Africa", "Canada"], "winner_to": "R16_2"},
        "R32_4": {"teams": ["Netherlands", "Morocco"], "winner_to": "R16_2"},
        "R32_5": {"teams": ["Portugal", "Croatia"], "winner_to": "R16_3"},
        "R32_6": {"teams": ["Spain", "Austria"], "winner_to": "R16_3"},
        "R32_7": {"teams": ["USA", "Bosnia and Herzegovina"], "winner_to": "R16_4"},
        "R32_8": {"teams": ["Belgium", "Senegal"], "winner_to": "R16_4"},
        "R32_9": {"teams": ["Brazil", "Japan"], "winner_to": "R16_5"},
        "R32_10": {"teams": ["Ivory Coast", "Norway"], "winner_to": "R16_5"},
        "R32_11": {"teams": ["Mexico", "Ecuador"], "winner_to": "R16_6"},
        "R32_12": {"teams": ["England", "DR Congo"], "winner_to": "R16_6"},
        "R32_13": {"teams": ["Argentina", "Cape Verde"], "winner_to": "R16_7"},
        "R32_14": {"teams": ["Australia", "Egypt"], "winner_to": "R16_7"},
        "R32_15": {"teams": ["Switzerland", "Algeria"], "winner_to": "R16_8"},
        "R32_16": {"teams": ["Colombia", "Ghana"], "winner_to": "R16_8"},
    },
    "round_of_16": {
        "R16_1": {"teams": ["Winner(R32_1)", "Winner(R32_2)"], "winner_to": "QF_1"},
        "R16_2": {"teams": ["Winner(R32_3)", "Winner(R32_4)"], "winner_to": "QF_1"},
        "R16_3": {"teams": ["Winner(R32_5)", "Winner(R32_6)"], "winner_to": "QF_2"},
        "R16_4": {"teams": ["Winner(R32_7)", "Winner(R32_8)"], "winner_to": "QF_2"},
        "R16_5": {"teams": ["Winner(R32_9)", "Winner(R32_10)"], "winner_to": "QF_3"},
        "R16_6": {"teams": ["Winner(R32_11)", "Winner(R32_12)"], "winner_to": "QF_3"},
        "R16_7": {"teams": ["Winner(R32_13)", "Winner(R32_14)"], "winner_to": "QF_4"},
        "R16_8": {"teams": ["Winner(R32_15)", "Winner(R32_16)"], "winner_to": "QF_4"},
    },
    "quarterfinals": {
        "QF_1": {"teams": ["Winner(R16_1)", "Winner(R16_2)"], "winner_to": "SF_1"},
        "QF_2": {"teams": ["Winner(R16_3)", "Winner(R16_4)"], "winner_to": "SF_1"},
        "QF_3": {"teams": ["Winner(R16_5)", "Winner(R16_6)"], "winner_to": "SF_2"},
        "QF_4": {"teams": ["Winner(R16_7)", "Winner(R16_8)"], "winner_to": "SF_2"},
    },
    "semifinals": {
        "SF_1": {"teams": ["Winner(QF_1)", "Winner(QF_2)"], "winner_to": "FINAL"},
        "SF_2": {"teams": ["Winner(QF_3)", "Winner(QF_4)"], "winner_to": "FINAL"},
    },
    "final": {
        "FINAL": {"teams": ["Winner(SF_1)", "Winner(SF_2)"], "winner_to": None},
    },
}


def get_supabase():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.exists(dotenv_path):
            for line in open(dotenv_path):
                line = line.strip()
                if line.startswith("SUPABASE_URL="):
                    url = line.split("=", 1)[1]
                elif line.startswith("SUPABASE_ANON_KEY="):
                    key = line.split("=", 1)[1]
    return create_client(url, key)


def resolve_team(team, winner_map):
    if team.startswith("Winner("):
        inner = team[6:-1]
        return winner_map.get(inner, team)
    if team.startswith("Loser("):
        inner = team[5:-1]
        return winner_map.get(inner, team)
    return team


def main():
    print("  Updating bracket with actual team names...")
    supabase = get_supabase()

    # Fetch all knockout matches from clean_wc_fixtures
    resp = (
        supabase.table("clean_wc_fixtures")
        .select(
            "match_id,match_date,home_team,away_team,home_score,away_score,result_1x2,stage"
        )
        .eq("is_knockout", True)
        .order("match_date")
        .execute()
    )
    all_matches = resp.data
    print(f"    Total knockout matches: {len(all_matches)}")

    # Build winner map from completed R32 matches
    winner_map = {}
    for m in all_matches:
        if m.get("result_1x2") and m["stage"] == "knockout":
            home = m["home_team"]
            away = m["away_team"]
            winner = home if m["result_1x2"] == "H" else away
            # Find which bracket slot this match belongs to
            for slot_id, slot in BRACKET["round_of_32"].items():
                if (slot["teams"][0] == home and slot["teams"][1] == away) or (
                    slot["teams"][0] == away and slot["teams"][1] == home
                ):
                    winner_map[slot_id] = winner
                    print(
                        f"      {slot_id}: {winner} (defeated {away if winner == home else home})"
                    )
                    break

    print(f"    Resolved winners: {len(winner_map)}")

    # Propagate winners through the bracket
    for round_name in ["round_of_16", "quarterfinals", "semifinals", "final"]:
        for slot_id, slot in BRACKET[round_name].items():
            team1 = resolve_team(slot["teams"][0], winner_map)
            team2 = resolve_team(slot["teams"][1], winner_map)
            if (
                not team1.startswith("Winner(")
                and not team1.startswith("Loser(")
                and not team2.startswith("Winner(")
                and not team2.startswith("Loser(")
            ):
                # Both teams resolved — update clean_wc_fixtures
                for m in all_matches:
                    if m["home_team"].startswith("Winner(") or m[
                        "home_team"
                    ].startswith("Loser("):
                        old_home = m["home_team"]
                        old_away = m["away_team"]
                        if (
                            old_home == slot["teams"][0] or old_home == slot["teams"][1]
                        ) or (
                            old_away == slot["teams"][0] or old_away == slot["teams"][1]
                        ):
                            new_home = (
                                team1
                                if old_home == slot["teams"][0]
                                or old_home == slot["teams"][1]
                                else old_home
                            )
                            new_away = (
                                team2
                                if old_away == slot["teams"][0]
                                or old_away == slot["teams"][1]
                                else old_away
                            )
                            # Only update if names actually changed
                            if new_home != old_home or new_away != old_away:
                                try:
                                    supabase.table("clean_wc_fixtures").update(
                                        {
                                            "home_team": new_home,
                                            "away_team": new_away,
                                        }
                                    ).eq("match_id", m["match_id"]).execute()
                                    print(
                                        f"      Updated {slot_id}: {old_home} vs {old_away} -> {new_home} vs {new_away}"
                                    )
                                except Exception as e:
                                    print(f"      ERROR updating {slot_id}: {e}")

    # Also update match_predictions with actual team names for fixture list
    print("    Updating match_predictions with actual team names...")
    for m in all_matches:
        if m["home_team"].startswith("Winner(") or m["home_team"].startswith("Loser("):
            old_home = m["home_team"]
            old_away = m["away_team"]
            new_home = resolve_team(old_home, winner_map)
            new_away = resolve_team(old_away, winner_map)
            if new_home != old_home or new_away != old_away:
                try:
                    supabase.table("match_predictions").update(
                        {
                            "home_team": new_home,
                            "away_team": new_away,
                        }
                    ).eq("match_id", m["match_id"]).execute()
                    print(
                        f"      Updated predictions {m['match_id']}: {old_home} vs {old_away} -> {new_home} vs {new_away}"
                    )
                except Exception as e:
                    print(f"      ERROR updating predictions {m['match_id']}: {e}")

    print("  Bracket update complete.")


if __name__ == "__main__":
    main()
