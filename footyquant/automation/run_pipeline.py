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

    root = os.path.dirname(os.path.dirname(__file__))
    venv_python = os.path.join(root, ".venv", "bin", "python")

    steps = [
        (
            f"PYTHONPATH={root} {venv_python} {os.path.join(root, 'footyquant', 'update_wc2026_matches.py')}",
            "1/9 Update wc2026_matches from Excel",
        ),
        (
            f"PYTHONPATH={root} {venv_python} {os.path.join(root, 'footyquant', 'propagate_results.py')}",
            "2/9 Propagate results to wc_matches",
        ),
        (
            f"PYTHONPATH={root} {venv_python} {os.path.join(root, 'footyquant', 'update_knockout_fixtures.py')}",
            "3/9 Update knockout fixtures from Excel",
        ),
        (
            f"TRUNCATE_CLEAN_ODDS=0 SOURCES=xlsx PYTHONPATH={root} {venv_python} -m footyquant rebuild odds",
            "4/9 Rebuild xlsx odds (Bet365/Betfair/Max/Avg)",
        ),
        (
            f"TRUNCATE_CLEAN_ODDS=0 SKIP_EXISTING=1 SOURCES=kalshi PYTHONPATH={root} {venv_python} -m footyquant rebuild odds",
            "5/9 Fetch Kalshi odds (new matches only)",
        ),
        (
            f"TRUNCATE_CLEAN_ODDS=0 SKIP_EXISTING=1 SOURCES=polymarket PYTHONPATH={root} {venv_python} -m footyquant rebuild odds",
            "6/9 Fetch Polymarket odds (new matches only)",
        ),
        (
            f"PYTHONPATH={root} {venv_python} {os.path.join(root, 'footyquant', 'scrape_fotmob_stats.py')}",
            "7/9 Scrape Fotmob stats for completed matches",
        ),
        (
            f"PYTHONPATH={root} {venv_python} -m footyquant rebuild modeling",
            "8/9 Rebuild all clean modeling tables",
        ),
        (
            f"PYTHONPATH={root} {venv_python} {os.path.join(root, 'footyquant', 'modelling', 'model.py')}",
            "9/9 Retrain model and predict upcoming matches",
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
