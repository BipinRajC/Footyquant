"""Surgical odds collector — pull current + historical odds for target fixtures."""

from datetime import datetime, timezone

from psycopg2.extras import execute_values
from sqlalchemy import text

from .db import get_engine
from .oddspapi import (
    get_odds,
    get_historical_odds,
    is_sharp,
    implied_prob,
    OddspAPIError,
)


def _bulk_insert(rows: list[dict]):
    if not rows:
        return
    engine = get_engine()
    with engine.begin() as conn:
        raw = conn.connection.driver_connection
        execute_values(
            raw.cursor(),
            """INSERT INTO odds_snapshots
            (oddspapi_fixture_id, market, book, selection, line,
             decimal_odds, implied_prob, is_sharp, captured_at_utc, source)
            VALUES %s
            ON CONFLICT DO NOTHING""",
            [
                (
                    r["fixture_id"],
                    r["market"],
                    r["book"],
                    r["selection"],
                    r["line"],
                    r["decimal_odds"],
                    r["implied_prob"],
                    r["is_sharp"],
                    r["captured_at"],
                    r["source"],
                )
                for r in rows
            ],
            template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        )


def _parse_historical_outcomes(
    outcomes: dict, market: str, book_slug: str, fixture_id: str
) -> list[dict]:
    rows = []
    for oid, oc in outcomes.items():
        selection = oc.get("name") or oc.get("type") or oid
        line = oc.get("line")
        timeline = oc.get("players", {}).get("0", [])
        if not isinstance(timeline, list):
            continue
        for tp in timeline:
            price = tp.get("price")
            if not price or float(price) <= 0:
                continue
            ip = implied_prob(float(price))
            if ip is None:
                continue
            rows.append(
                {
                    "fixture_id": fixture_id,
                    "market": market,
                    "book": book_slug,
                    "selection": selection,
                    "line": float(line) if line is not None else None,
                    "decimal_odds": float(price),
                    "implied_prob": ip,
                    "is_sharp": is_sharp(book_slug),
                    "captured_at": tp.get(
                        "createdAt", datetime.now(timezone.utc).isoformat()
                    ),
                    "source": "historical",
                }
            )
    return rows


def _parse_current_outcomes(
    outcomes: list, market: str, book_slug: str, fixture_id: str, captured_at: str
) -> list[dict]:
    rows = []
    for oc in outcomes:
        selection = oc.get("name") or oc.get("type") or ""
        line = oc.get("line")
        prices = oc.get("players", {}).get("0", {})
        price = prices.get("price") if isinstance(prices, dict) else None
        if not price or float(price) <= 0:
            continue
        ip = implied_prob(float(price))
        if ip is None:
            continue
        rows.append(
            {
                "fixture_id": fixture_id,
                "market": market,
                "book": book_slug,
                "selection": selection,
                "line": float(line) if line is not None else None,
                "decimal_odds": float(price),
                "implied_prob": ip,
                "is_sharp": is_sharp(book_slug),
                "captured_at": captured_at,
                "source": "oddspapi_current",
            }
        )
    return rows


def pull_current(fixture_id: str) -> int:
    data = get_odds(fixture_id)
    captured_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for book_entry in data.get("bookmakerOdds", []):
        book_slug = book_entry.get("slug", "")
        for market_entry in book_entry.get("markets", []):
            market = str(market_entry.get("marketId", ""))
            rows.extend(
                _parse_current_outcomes(
                    market_entry.get("outcomes", []),
                    market,
                    book_slug,
                    fixture_id,
                    captured_at,
                )
            )
    _bulk_insert(rows)
    return len(rows)


def pull_history(fixture_id: str, books: list[str] | None = None) -> int:
    books = books or ["pinnacle", "bet365"]
    data = get_historical_odds(fixture_id, books)
    rows = []
    for book_slug, book_data in data.get("bookmakers", {}).items():
        for mid, mdata in book_data.get("markets", {}).items():
            rows.extend(
                _parse_historical_outcomes(
                    mdata.get("outcomes", {}), mid, book_slug, fixture_id
                )
            )
    _bulk_insert(rows)
    return len(rows)


def collect_targets(fixture_ids: list[str], do_history: bool = True):
    for fid in fixture_ids:
        try:
            n = pull_current(fid)
            print(f"  Current {fid}: {n} rows")
        except OddspAPIError as e:
            print(f"  SKIP current {fid}: {e}")

        if do_history:
            try:
                n = pull_history(fid)
                print(f"  History {fid}: {n} rows")
            except OddspAPIError as e:
                print(f"  SKIP history {fid}: {e}")
