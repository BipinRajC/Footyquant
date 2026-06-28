"""Propagate group stage results from wc2026_matches to wc_matches.

wc2026_matches has all 72 group stage results from the Excel.
wc_matches only has 46 completed — the 26 Matchday 3 results are missing.
This script joins the two tables by team names and copies scores.
"""

import os
import pandas as pd
from supabase import create_client


def get_supabase():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        for dotenv_path in [".env", "../.env", "../../.env"]:
            if os.path.exists(dotenv_path):
                with open(dotenv_path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("SUPABASE_URL="):
                            url = line.split("=", 1)[1]
                        elif line.startswith("SUPABASE_ANON_KEY="):
                            key = line.split("=", 1)[1]
                        elif line.startswith("SUPABASE_KEY=") and not key:
                            key = line.split("=", 1)[1]
                if url and key:
                    break
    return create_client(url, key)


TEAM_NAME_MAP = {
    "Czech Republic": "Czechia",
    "Turkey": "Turkiye",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "D.R. Congo": "DR Congo",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Cabo Verde": "Cape Verde",
    "Korea Republic": "South Korea",
    "IR Iran": "Iran",
}


def normalize(name):
    if pd.isna(name):
        return None
    return TEAM_NAME_MAP.get(str(name).strip(), str(name).strip())


def main():
    print("  Propagating results from wc2026_matches to wc_matches...")

    supabase = get_supabase()

    # Get all wc2026_matches with results
    resp = supabase.table("wc2026_matches").select("*").execute()
    wc2026 = resp.data
    print(f"    wc2026_matches: {len(wc2026)} rows")

    # Get all wc_matches that need results (group + knockout)
    resp = (
        supabase.table("wc_matches")
        .select("match_id,home_team,away_team,home_score,away_score,match_date,stage")
        .in_("stage", ["group", "knockout"])
        .execute()
    )
    wc_matches = resp.data
    print(f"    wc_matches (group+knockout): {len(wc_matches)} rows")

    # Build a lookup of wc_matches by normalized team pair
    wc_lookup = {}
    for m in wc_matches:
        if m["home_score"] is not None:
            continue  # already has result
        key = frozenset([normalize(m["home_team"]), normalize(m["away_team"])])
        wc_lookup[key] = m

    # Match wc2026 rows to wc_matches
    updated = 0
    for row in wc2026:
        if row.get("hgft") is None:
            continue

        home = normalize(row["home"])
        away = normalize(row["away"])
        key = frozenset([home, away])

        match = wc_lookup.get(key)
        if not match:
            continue

        # Determine result
        hg = int(row["hgft"])
        ag = int(row["agft"])
        if hg > ag:
            result = "H"
        elif hg < ag:
            result = "A"
        else:
            result = "D"

        total_goals = hg + ag
        btts = hg > 0 and ag > 0

        try:
            supabase.table("wc_matches").update(
                {
                    "home_score": hg,
                    "away_score": ag,
                    "result_1x2": result,
                    "total_goals": total_goals,
                    "btts": btts,
                }
            ).eq("match_id", match["match_id"]).execute()
            updated += 1
            print(
                f"    {match['home_team']} {hg}-{ag} {match['away_team']} -> match_id={match['match_id']}"
            )
        except Exception as e:
            print(f"    ERROR updating {match['match_id']}: {e}")

    print(f"    Updated {updated} wc_matches rows with results")
    print("  Done.")


if __name__ == "__main__":
    main()
