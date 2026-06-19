"""CLV helper and predictions writer."""

from datetime import datetime, timezone

from sqlalchemy import text

from .db import get_engine


def get_closing_line(
    fixture_id: str, market: str, book: str = "pinnacle"
) -> dict | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """SELECT selection, decimal_odds, implied_prob, captured_at_utc
                FROM odds_snapshots
                WHERE oddspapi_fixture_id = :fid
                  AND market = :mkt
                  AND book = :book
                  AND source = 'historical'
                ORDER BY captured_at_utc DESC
                LIMIT 1"""
            ),
            {"fid": fixture_id, "mkt": market, "book": book},
        ).fetchone()
        if row:
            return {
                "selection": row[0],
                "decimal_odds": float(row[1]),
                "implied_prob": float(row[2]),
                "captured_at": row[3],
            }
    return None


def get_opening_line(
    fixture_id: str, market: str, book: str = "pinnacle"
) -> dict | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """SELECT selection, decimal_odds, implied_prob, captured_at_utc
                FROM odds_snapshots
                WHERE oddspapi_fixture_id = :fid
                  AND market = :mkt
                  AND book = :book
                  AND source = 'historical'
                ORDER BY captured_at_utc ASC
                LIMIT 1"""
            ),
            {"fid": fixture_id, "mkt": market, "book": book},
        ).fetchone()
        if row:
            return {
                "selection": row[0],
                "decimal_odds": float(row[1]),
                "implied_prob": float(row[2]),
                "captured_at": row[3],
            }
    return None


def compute_clv(model_prob: float, closing_prob: float) -> float:
    return model_prob - closing_prob


def save_prediction(match_id: int, market: str, model_prob: float, fair_odds: float):
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO predictions
                (match_id, market, model_prob, fair_odds, created_at_utc)
                VALUES (:mid, :mkt, :prob, :odds, :now)"""
            ),
            {
                "mid": match_id,
                "mkt": market,
                "prob": model_prob,
                "odds": fair_odds,
                "now": datetime.now(timezone.utc),
            },
        )
