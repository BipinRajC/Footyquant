"""Restore match_outcome data from local DB to Supabase after pipeline rebuild."""

import os, sys
from footyquant.db import get_engine
from sqlalchemy import text
from supabase import create_client

engine = get_engine()
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
url = key = ""
for line in (
    open(os.path.join(root, ".env"))
    if os.path.exists(os.path.join(root, ".env"))
    else []
):
    if line.startswith("SUPABASE_URL="):
        url = line.split("=", 1)[1].strip()
    elif line.startswith("SUPABASE_ANON_KEY="):
        key = line.split("=", 1)[1].strip()
if not url or not key:
    print("Supabase credentials not found")
    sys.exit(1)

supabase = create_client(url, key)
with engine.connect() as conn:
    rows = conn.execute(
        text(
            "SELECT fotmob_match_id, home_team, away_team, match_outcome, aet_home_score, aet_away_score, penalties_home_score, penalties_away_score, aet_xg_home, aet_xg_away FROM public.wcmatches_richstat_fotmob WHERE match_outcome IS NOT NULL"
        )
    ).fetchall()
    for r in rows:
        mid = conn.execute(
            text(
                "SELECT match_id FROM clean_wc_fixtures WHERE (home_team = :1 AND away_team = :2) OR (home_team = :2 AND away_team = :1) LIMIT 1",
            ),
            [r[1], r[2]],
        ).fetchone()
        if mid:
            upd = {
                k: v
                for k, v in [
                    ("match_outcome", r[3]),
                    ("aet_home_score", r[4]),
                    ("aet_away_score", r[5]),
                    ("penalties_home_score", r[6]),
                    ("penalties_away_score", r[7]),
                    ("aet_home_xg", r[8]),
                    ("aet_away_xg", r[9]),
                ]
                if v is not None
            }
            supabase.table("clean_wc_fixtures").update(upd).eq(
                "match_id", mid[0]
            ).execute()
    print(f"Restored match_outcome for {len(rows)} matches")
