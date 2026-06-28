"""Update wc_matches knockout fixtures with real team names from Excel.

Reads the Matches sheet with data_only=True to resolve team names,
then positionally matches by date to update DB knockout fixtures.
"""

import os
import pandas as pd
from supabase import create_client


def get_supabase():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
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
    return create_client(url, key)


TEAM_NAME_MAP = {
    "Bosnia/Herzeg.": "Bosnia and Herzegovina",
    "Cote d'Ivoire": "Ivory Coast",
    "Côte d'Ivoire": "Ivory Coast",
    "Cabo Verde": "Cape Verde",
    "Korea Republic": "South Korea",
    "DR Congo": "DR Congo",
    "D.R. Congo": "DR Congo",
    "IR Iran": "Iran",
}


def normalize(name):
    if pd.isna(name):
        return None
    return TEAM_NAME_MAP.get(str(name).strip(), str(name).strip())


def main():
    print("  Updating knockout fixtures from Excel...")

    root = os.path.dirname(os.path.dirname(__file__))
    df = pd.read_excel(
        os.path.join(root, "data", "auto-updating-schedule.xlsx"),
        sheet_name="Matches",
        header=2,
    )

    supabase = get_supabase()

    resp = (
        supabase.table("wc_matches")
        .select("match_id,home_team,away_team,match_date")
        .eq("stage", "knockout")
        .order("match_date")
        .execute()
    )
    db_rows = resp.data
    print(f"    DB knockout matches: {len(db_rows)}")

    excel_matches = []
    for _, r in df.iterrows():
        match_no = r.iloc[1]
        if pd.isna(match_no):
            continue
        match_str = str(match_no)
        if not match_str.isdigit() or int(match_str) < 73 or int(match_str) > 88:
            continue
        team1 = normalize(r.iloc[8])
        team2 = normalize(r.iloc[9])
        local_date = r.iloc[4]
        if not team1 or not team2 or pd.isna(local_date):
            continue
        excel_matches.append(
            {
                "match_no": int(match_str),
                "team1": team1,
                "team2": team2,
                "local_date": pd.to_datetime(local_date),
            }
        )

    excel_matches.sort(key=lambda x: x["local_date"])
    print(f"    Excel R32 matches with teams: {len(excel_matches)}")
    for m in excel_matches:
        print(
            f"      Match {m['match_no']}: {m['team1']} vs {m['team2']} ({m['local_date']})"
        )

    db_r32 = [
        r
        for r in db_rows
        if pd.to_datetime(r["match_date"], utc=True)
        < pd.Timestamp("2026-07-04", tz="UTC")
    ]
    db_r32.sort(key=lambda x: pd.to_datetime(x["match_date"], utc=True))
    print(f"    DB R32 matches: {len(db_r32)}")

    updates = []
    for i, (excel_m, db_m) in enumerate(zip(excel_matches, db_r32)):
        old_home = db_m["home_team"]
        old_away = db_m["away_team"]
        new_home = excel_m["team1"]
        new_away = excel_m["team2"]
        if old_home != new_home or old_away != new_away:
            updates.append(
                {
                    "match_id": db_m["match_id"],
                    "home_team": new_home,
                    "away_team": new_away,
                    "old": f"{old_home} vs {old_away}",
                    "new": f"{new_home} vs {new_away}",
                }
            )

    print(f"    Updates needed: {len(updates)}")
    for u in updates:
        print(f"      {u['match_id']}: {u['old']} -> {u['new']}")
        try:
            supabase.table("wc_matches").update(
                {
                    "home_team": u["home_team"],
                    "away_team": u["away_team"],
                }
            ).eq("match_id", u["match_id"]).execute()
        except Exception as e:
            print(f"      ERROR: {e}")

    print(f"    Updated {len(updates)} knockout fixtures")
    print("  Done.")


if __name__ == "__main__":
    main()
