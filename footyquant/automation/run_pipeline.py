"""Matchday Pipeline — run after each matchday.

Usage: python footyquant/automation/run_pipeline.py

Does everything in order:
1. Update wc2026_matches from Excel (new results + stats + odds)
2. Propagate results to wc_matches
3. Update knockout fixtures from Excel (if new matchups determined)
4. Rebuild clean_market_odds (xlsx source — fast, has new match odds)
5. Fetch Kalshi odds (new matches only)
6. Fetch Polymarket odds (new matches only)
7. Scrape Fotmob stats for newly completed matches
8. Rebuild all clean modeling tables (feature view with new completed matches)
9. Retrain model and predict upcoming matches
"""

import os
import subprocess
import sys


def run(cmd: str, label: str) -> bool:
    print(f"\n  [{label}]")
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"  FAILED: {label}")
        return False
    print(f"  OK: {label}")
    return True


def main():
    print("=" * 60)
    print("  MATCHDAY PIPELINE")
    print("=" * 60)

    env_setup = " || true"  # don't crash on env errors

    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    venv_python = os.path.join(root, ".venv", "bin", "python")

    steps = [
        (
            f"PYTHONPATH={root} {venv_python} {os.path.join(root, 'footyquant', 'update_wc2026_matches.py')}",
            "1/10 Update wc2026_matches from Excel",
        ),
        (
            f"PYTHONPATH={root} {venv_python} {os.path.join(root, 'footyquant', 'propagate_results.py')}",
            "2/10 Propagate results to wc_matches",
        ),
        (
            f"PYTHONPATH={root} {venv_python} {os.path.join(root, 'footyquant', 'update_knockout_fixtures.py')}",
            "3/10 Update knockout fixtures from Excel",
        ),
        (
            f"TRUNCATE_CLEAN_ODDS=0 SOURCES=xlsx PYTHONPATH={root} {venv_python} -m footyquant rebuild odds",
            "4/10 Rebuild xlsx odds (Bet365/Betfair/Max/Avg)",
        ),
        (
            f"TRUNCATE_CLEAN_ODDS=0 SKIP_EXISTING=1 SOURCES=kalshi PYTHONPATH={root} {venv_python} -m footyquant rebuild odds",
            "5/10 Fetch Kalshi odds (new matches only)",
        ),
        (
            f"TRUNCATE_CLEAN_ODDS=0 SKIP_EXISTING=1 SOURCES=polymarket PYTHONPATH={root} {venv_python} -m footyquant rebuild odds",
            "6/10 Fetch Polymarket odds (new matches only)",
        ),
        (
            f"PYTHONPATH={root} {venv_python} {os.path.join(root, 'footyquant', 'scrape_fotmob_stats.py')}",
            "7/10 Scrape Fotmob stats for completed matches",
        ),
        (
            f"PYTHONPATH={root} {venv_python} {os.path.join(root, 'footyquant', 'propagate_knockout_results.py')}",
            "8/10 Propagate knockout results from Fotmob to wc_matches",
        ),
        (
            f"PYTHONPATH={root} {venv_python} -m footyquant rebuild modeling",
            "9/10 Rebuild all clean modeling tables",
        ),
        (
            f"""PYTHONPATH={root} {venv_python} -c "
from footyquant.db import get_engine
from sqlalchemy import text
engine = get_engine()
with engine.begin() as conn:
    for q in [
        'ALTER TABLE clean_wc_fixtures ADD COLUMN IF NOT EXISTS match_outcome TEXT',
        'ALTER TABLE clean_wc_fixtures ADD COLUMN IF NOT EXISTS aet_home_score INTEGER',
        'ALTER TABLE clean_wc_fixtures ADD COLUMN IF NOT EXISTS aet_away_score INTEGER',
        'ALTER TABLE clean_wc_fixtures ADD COLUMN IF NOT EXISTS penalties_home_score INTEGER',
        'ALTER TABLE clean_wc_fixtures ADD COLUMN IF NOT EXISTS penalties_away_score INTEGER',
        'ALTER TABLE clean_wc_fixtures ADD COLUMN IF NOT EXISTS aet_home_xg REAL',
        'ALTER TABLE clean_wc_fixtures ADD COLUMN IF NOT EXISTS aet_away_xg REAL',
    ]:
        conn.execute(text(q))
    print('AET/pens columns ensured')
" """,
            "9b/10 Ensure AET/pens columns exist",
        ),
        (
            f"""PYTHONPATH={root} {venv_python} -c "
from footyquant.db import get_engine
from sqlalchemy import text
import os
from supabase import create_client
engine = get_engine()
url = key = ''
for line in open(os.path.join('{root}', '.env')) if os.path.exists(os.path.join('{root}', '.env')) else []:
    if line.startswith('SUPABASE_URL='): url = line.split('=',1)[1].strip()
    elif line.startswith('SUPABASE_ANON_KEY='): key = line.split('=',1)[1].strip()
if url and key:
    supabase = create_client(url, key)
    with engine.connect() as conn:
        rows = conn.execute(text(\"\"\"SELECT fotmob_match_id, home_team, away_team, match_outcome, aet_home_score, aet_away_score, penalties_home_score, penalties_away_score, aet_xg_home, aet_xg_away FROM public.wcmatches_richstat_fotmob WHERE match_outcome IS NOT NULL\"\"\")).fetchall()
        for r in rows:
            mid = conn.execute(text(\"SELECT match_id FROM clean_wc_fixtures WHERE (home_team = :ht AND away_team = :at) OR (home_team = :at AND away_team = :ht) LIMIT 1\"), {"ht":r.home_team,'at':r.away_team}).fetchone()
            if mid:
                upd = {k:v for k,v in {'match_outcome':r.match_outcome,'aet_home_score':r.aet_home_score,'aet_away_score':r.aet_away_score,'penalties_home_score':r.penalties_home_score,'penalties_away_score':r.penalties_away_score,'aet_home_xg':r.aet_xg_home,'aet_away_xg':r.aet_xg_away}.items() if v is not None}
                supabase.table('clean_wc_fixtures').update(upd).eq('match_id',mid[0]).execute()
    print(f'Restored match_outcome for {len(rows)} matches')
" """,
            "9c/10 Restore match_outcome data from local DB",
        ),
        (
            f"PYTHONPATH={root} {venv_python} {os.path.join(root, 'footyquant', 'update_bracket.py')}",
            "9d/10 Update bracket with actual team names",
        ),
        (
            f"PYTHONPATH={root} {venv_python} {os.path.join(root, 'footyquant', 'modelling', 'model.py')}",
            "10/10 Retrain model and predict upcoming matches",
        ),
    ]

    for cmd, label in steps:
        if not run(cmd, label):
            print(f"\n  Pipeline stopped at: {label}")
            print("  Fix the error and re-run.")
            sys.exit(1)

    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETE")
    print("  TUI will now show updated predictions for upcoming matches.")
    print("=" * 60)


if __name__ == "__main__":
    main()
