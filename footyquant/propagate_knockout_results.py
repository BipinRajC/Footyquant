"""Propagate knockout match results from Fotmob stats to wc_matches."""

import os
from footyquant.db import get_engine
from sqlalchemy import text


def main():
    print("  Propagating knockout results from Fotmob stats...")

    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE wc_matches w
                SET
                    home_score = f.home_score,
                    away_score = f.away_score,
                    result_1x2 = f.result_1x2,
                    btts = f.btts,
                    total_goals = f.total_goals
                FROM wcmatches_richstat_fotmob f
                WHERE f.fotmob_match_id = w.match_id
                  AND w.stage = 'knockout'
                  AND f.home_score IS NOT NULL
                  AND (w.home_score IS NULL OR w.home_score != f.home_score
                       OR w.away_score IS NULL OR w.away_score != f.away_score)
            """)
        )
        print(f"    Updated {result.rowcount} knockout matches with Fotmob results")
    print("  Done.")


if __name__ == "__main__":
    main()
