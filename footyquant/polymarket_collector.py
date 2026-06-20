"""Polymarket collection orchestration — discover, snapshot, backfill."""

import json
import os
from datetime import datetime, timezone

from sqlalchemy import text

from .db import get_engine
from .polymarket import (
    discover_wc_match_events,
    get_markets,
    get_orderbook,
    parse_market_snapshot,
    compute_bid_ask_spread,
    compute_liquidity,
    PolymarketError,
)
from .team_mapping import WC_TEAMS

CACHE_FILE = "data/polymarket_event_map.json"


def _load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}


def _save_cache(data: dict):
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def _get_match_map(engine) -> dict:
    """Build {team_name_lower: match_id} for WC 2026 matches."""
    rows = engine.execute(
        text("""
            SELECT m.match_id, t1.name as home, t2.name as away
            FROM matches m
            JOIN teams t1 ON m.home_team_id = t1.canonical_id
            JOIN teams t2 ON m.away_team_id = t2.canonical_id
            WHERE m.tournament = 'WorldCup2026' OR m.tournament = 'FIFA World Cup 2026'
        """),
    ).fetchall()

    mapping = {}
    for mid, home, away in rows:
        mapping[home.lower()] = mid
        mapping[away.lower()] = mid
    return mapping


def discover_and_map() -> dict:
    """Discover WC match events from Polymarket and map to match_ids."""
    cache = _load_cache()
    if cache.get("events"):
        print(f"Using cached event map ({len(cache['events'])} events)")
        return cache

    print("Discovering Polymarket WC match events...")
    try:
        events = discover_wc_match_events(WC_TEAMS)
    except PolymarketError as e:
        print(f"  API error: {e}")
        return cache

    print(f"  Found {len(events)} match events")

    engine = get_engine()
    with engine.connect() as conn:
        match_map = _get_match_map(conn)

    mapped = []
    for ev in events:
        title = ev.get("title", "")
        import re

        parts = re.split(r"\s+vs\.?\s+", title, maxsplit=1)
        if len(parts) != 2:
            continue
        teams = [p.strip().lower() for p in parts]

        home_team = teams[0]
        away_team = teams[1]

        mid = match_map.get(home_team) or match_map.get(away_team)
        if mid:
            mapped.append(
                {
                    "match_id": mid,
                    "event_id": ev["id"],
                    "title": title,
                    "slug": ev.get("slug"),
                    "home": teams[0],
                    "away": teams[1],
                }
            )

    print(f"  Mapped {len(mapped)}/{len(events)} events to match_ids")

    cache["events"] = mapped
    cache["mapped_at"] = datetime.now(timezone.utc).isoformat()
    _save_cache(cache)

    return cache


def snapshot_all_matches() -> int:
    """Poll all mapped Polymarket events and store current snapshots."""
    cache = _load_cache()
    events = cache.get("events", [])
    if not events:
        print("No mapped events. Run discover_and_map() first.")
        return 0

    engine = get_engine()
    total_rows = 0

    for ev in events:
        match_id = ev["match_id"]
        event_id = ev["event_id"]

        try:
            markets = get_markets(event_id=event_id, limit=100)
        except PolymarketError as e:
            print(f"  SKIP event {event_id}: {e}")
            continue

        snapshots = []
        for m in markets:
            parsed = parse_market_snapshot(m, match_id)
            if parsed:
                token_ids = m.get("clobTokenIds", [])
                if token_ids:
                    try:
                        ob = get_orderbook(token_ids[0])
                        parsed["bid_ask_spread"] = compute_bid_ask_spread(ob)
                        parsed["liquidity"] = compute_liquidity(ob)
                    except PolymarketError:
                        pass
                snapshots.append(parsed)

        if not snapshots:
            continue

        with engine.begin() as conn:
            for s in snapshots:
                conn.execute(
                    text("""
                        INSERT INTO prediction_market_snapshots
                        (match_id, source, market_type, outcome, line, price,
                         volume, liquidity, bid_ask_spread, market_id,
                         captured_at_utc, raw_response)
                        VALUES (:match_id, :source, :market_type, :outcome, :line, :price,
                                :volume, :liquidity, :bid_ask_spread, :market_id,
                                :captured_at_utc, CAST(:raw_response AS jsonb))
                        ON CONFLICT DO NOTHING
                    """),
                    {
                        "match_id": s["match_id"],
                        "source": s["source"],
                        "market_type": s["market_type"],
                        "outcome": s["outcome"],
                        "line": s["line"],
                        "price": s["price"],
                        "volume": s["volume"],
                        "liquidity": s["liquidity"],
                        "bid_ask_spread": s["bid_ask_spread"],
                        "market_id": s["market_id"],
                        "captured_at_utc": s["captured_at_utc"],
                        "raw_response": json.dumps(s["raw_response"]),
                    },
                )

        total_rows += len(snapshots)
        print(f"  {ev['title']}: {len(snapshots)} snapshots")

    _update_coverage(engine)
    print(f"Total: {total_rows} Polymarket snapshots stored")
    return total_rows


def _update_coverage(engine):
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE data_coverage dc
                SET polymarket_available = TRUE,
                    source_count = source_count + 1,
                    last_updated_utc = NOW()
                FROM prediction_market_snapshots pms
                WHERE pms.match_id = dc.match_id
                  AND pms.source = 'polymarket'
                  AND dc.polymarket_available = FALSE
            """),
        )


def main():
    print("=== Phase B: Polymarket Ingestion ===")
    cache = discover_and_map()
    if cache.get("events"):
        snapshot_all_matches()
    else:
        print("No events discovered.")


if __name__ == "__main__":
    main()
