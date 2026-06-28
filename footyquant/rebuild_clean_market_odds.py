#!/usr/bin/env python3
"""Rebuild model-safe Kalshi and Polymarket odds for WC 2026 matches."""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from datetime import timedelta, timezone

import requests
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

from footyquant.clean_odds import (  # noqa: E402
    CLEAN_MARKET_ODDS_SOURCES,
    chunked,
    latest_kalshi_price_before_kickoff,
    latest_price_before_kickoff,
    polymarket_outcome_from_question,
)
from footyquant.db import get_engine  # noqa: E402
from footyquant.kalshi import (  # noqa: E402
    KALSHI_BASE,
    UA as KALSHI_UA,
    WC_SERIES,
    get_all_events,
    get_markets,
    parse_1x2_markets,
    parse_btts_markets,
    parse_match_title as parse_kalshi_title,
    parse_spread_markets,
    parse_total_markets,
)
from footyquant.polymarket import (  # noqa: E402
    classify_event,
    get_all_wc_events,
    get_event,
    get_price_history,
    parse_match_markets,
    parse_match_title as parse_poly_title,
)


TEAM_ALIASES = {
    "côte d'ivoire": "ivory coast",
    "cote d ivoire": "ivory coast",
    "ivory coast": "ivory coast",
    "curaçao": "curacao",
    "curacao": "curacao",
    "türkiye": "turkiye",
    "turkiye": "turkiye",
    "united states": "usa",
    "cabo verde": "cape verde",
    "cape verde": "cape verde",
    "bosnia-herzegovina": "bosnia and herzegovina",
    "bosnia herzegovina": "bosnia and herzegovina",
    "bosnia and herzegovina": "bosnia and herzegovina",
    "south korea": "south korea",
    "korea republic": "south korea",
    "ir iran": "iran",
    "iran": "iran",
    "dr congo": "dr congo",
    "congo dr": "dr congo",
    "usa": "usa",
}


DDL = """
CREATE TABLE IF NOT EXISTS public.clean_market_odds (
    id BIGSERIAL PRIMARY KEY,
    match_id TEXT NOT NULL,
    match_date TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    market_type TEXT NOT NULL,
    outcome TEXT NOT NULL,
    line DOUBLE PRECISION,
    probability DOUBLE PRECISION NOT NULL CHECK (probability > 0 AND probability < 1),
    captured_at_utc TIMESTAMPTZ,
    price_time_utc TIMESTAMPTZ,
    source_market_id TEXT,
    source_token_id TEXT,
    quality TEXT NOT NULL,
    is_prekickoff BOOLEAN NOT NULL DEFAULT TRUE,
    is_training_usable BOOLEAN NOT NULL DEFAULT TRUE,
    raw_response JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS clean_market_odds_unique_market_row
ON public.clean_market_odds (
    match_id,
    source,
    market_type,
    outcome,
    COALESCE(line, '-9999'::DOUBLE PRECISION)
);

CREATE INDEX IF NOT EXISTS clean_market_odds_match_source_idx
ON public.clean_market_odds (match_id, source, market_type);

COMMENT ON TABLE public.clean_market_odds IS
'Model-safe Kalshi, Polymarket, and xlsx bookmaker odds. Pinnacle is intentionally excluded.';
"""

SOURCE_CONSTRAINT_SQL = """
ALTER TABLE public.clean_market_odds
DROP CONSTRAINT IF EXISTS clean_market_odds_source_check;

ALTER TABLE public.clean_market_odds
ADD CONSTRAINT clean_market_odds_source_check
CHECK (source IN ({sources}));
""".format(
    sources=", ".join(f"'{source}'" for source in sorted(CLEAN_MARKET_ODDS_SOURCES))
)


def norm(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    clean = re.sub(r"[^a-z0-9 ]+", " ", name.lower()).strip()
    clean = re.sub(r"\s+", " ", clean)
    return TEAM_ALIASES.get(clean, clean)


def pair_key(home: str, away: str) -> frozenset[str]:
    return frozenset((norm(home), norm(away)))


def remap_outcome(outcome: str, reversed_orientation: bool) -> str:
    if not reversed_orientation:
        return outcome
    if outcome == "home":
        return "away"
    if outcome == "away":
        return "home"
    return outcome


def fixtures_by_pair() -> dict[frozenset[str], dict]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT match_id, match_date, home_team, away_team, home_score, away_score, result_1x2
                FROM public.wc_matches
                WHERE home_team NOT SIMILAR TO '[0-9]%'
                  AND away_team NOT SIMILAR TO '[0-9]%'
                  AND home_team NOT ILIKE '%Winner%'
                  AND home_team NOT ILIKE '%Loser%'
                  AND away_team NOT ILIKE '%Winner%'
                  AND away_team NOT ILIKE '%Loser%'
                  AND home_team NOT ILIKE '%/%'
                  AND away_team NOT ILIKE '%/%'
                ORDER BY match_date
            """),
        ).mappings()
        fixtures = []
        for row in rows:
            item = dict(row)
            item["played"] = (
                item["home_score"] is not None and item["away_score"] is not None
            )
            fixtures.append(item)
    return {pair_key(f["home_team"], f["away_team"]): f for f in fixtures}


def existing_odds_match_ids(source: str) -> set[str]:
    """Return match_ids that already have odds for this source."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT DISTINCT match_id FROM public.clean_market_odds
                WHERE source = :source AND is_prekickoff = true
            """),
            {"source": source},
        ).mappings()
    return {r["match_id"] for r in rows}


def prepare_table(truncate: bool = True) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        for stmt in DDL.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        for stmt in SOURCE_CONSTRAINT_SQL.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        if truncate:
            conn.execute(text("TRUNCATE TABLE public.clean_market_odds"))


def insert_rows(rows: list[dict], batch_size: int = 500) -> None:
    if not rows:
        return
    engine = get_engine()
    stmt = text("""
                INSERT INTO public.clean_market_odds
                (match_id, match_date, source, market_type, outcome, line, probability,
                 captured_at_utc, price_time_utc, source_market_id, source_token_id,
                 quality, is_prekickoff, is_training_usable, raw_response)
                VALUES
                (:match_id, :match_date, :source, :market_type, :outcome, :line, :probability,
                 :captured_at_utc, :price_time_utc, :source_market_id, :source_token_id,
                 :quality, :is_prekickoff, :is_training_usable, CAST(:raw_response AS jsonb))
                ON CONFLICT (match_id, source, market_type, outcome, COALESCE(line, '-9999'::DOUBLE PRECISION))
                DO UPDATE SET
                    probability = EXCLUDED.probability,
                    captured_at_utc = EXCLUDED.captured_at_utc,
                    price_time_utc = EXCLUDED.price_time_utc,
                    source_market_id = EXCLUDED.source_market_id,
                    source_token_id = EXCLUDED.source_token_id,
                    quality = EXCLUDED.quality,
                    is_prekickoff = EXCLUDED.is_prekickoff,
                    is_training_usable = EXCLUDED.is_training_usable,
                    raw_response = EXCLUDED.raw_response
            """)
    for batch in chunked(rows, batch_size):
        with engine.begin() as conn:
            conn.execute(stmt, batch)
        print(f"    inserted {len(batch)} rows", flush=True)


def api_proxies() -> dict[str, str] | None:
    proxy = (
        os.getenv("KALSHI_PROXY")
        or os.getenv("POLYMARKET_PROXY")
        or os.getenv("TOR_PROXY")
    )
    if not proxy:
        return None
    proxy = proxy.replace("socks5://", "socks5h://")
    return {"http": proxy, "https": proxy}


def kalshi_batch_candles(
    tickers: list[str], start_ts: int, end_ts: int
) -> dict[str, list[dict]]:
    if not tickers:
        return {}
    out = {}
    proxies = api_proxies()
    for i in range(0, len(tickers), 100):
        chunk = tickers[i : i + 100]
        time.sleep(0.2)
        resp = requests.get(
            f"{KALSHI_BASE}/markets/candlesticks",
            params={
                "market_tickers": ",".join(chunk),
                "start_ts": start_ts,
                "end_ts": end_ts,
                "period_interval": 60,
                "use_prepend": "true",
            },
            headers={"User-Agent": KALSHI_UA},
            proxies=proxies,
            timeout=60,
        )
        resp.raise_for_status()
        for market in resp.json().get("markets", []):
            out[market["market_ticker"]] = market.get("candlesticks", [])
    return out


def parse_kalshi_snapshots(
    market_type: str, title: str, markets: list[dict]
) -> list[dict]:
    event = {"title": title}
    if market_type == "1x2":
        return parse_1x2_markets(event, markets)
    if market_type == "btts":
        return parse_btts_markets(event, markets)
    if market_type == "over_under":
        return parse_total_markets(event, markets)
    if market_type == "spread":
        return parse_spread_markets(event, markets)
    return []


def rebuild_kalshi(fixtures: dict[frozenset[str], dict]) -> int:
    rows = []
    inserted = 0
    wanted = os.getenv("KALSHI_MARKETS")
    wanted_markets = (
        {m.strip() for m in wanted.split(",")} if wanted else set(WC_SERIES)
    )
    skip_existing = os.getenv("SKIP_EXISTING", "0") == "1"
    existing_ids = existing_odds_match_ids("kalshi") if skip_existing else set()
    if skip_existing:
        print(f"Kalshi: skipping {len(existing_ids)} matches already in DB", flush=True)
    for market_type, series in WC_SERIES.items():
        if market_type not in wanted_markets:
            continue
        events = []
        for status in ("open", "settled"):
            events.extend(get_all_events(series, status=status))
        print(f"Kalshi {market_type}: {len(events)} events", flush=True)

        for index, event in enumerate(events, start=1):
            parsed = parse_kalshi_title(event.get("title", ""))
            if not parsed:
                continue
            event_home, event_away = parsed
            fixture = fixtures.get(pair_key(event_home, event_away))
            if not fixture:
                continue
            if skip_existing and fixture["match_id"] in existing_ids:
                continue
            reversed_orientation = norm(event_home) == norm(fixture["away_team"])

            try:
                markets = get_markets(event.get("event_ticker", ""))
            except Exception as exc:
                print(
                    f"  Kalshi skip markets {event.get('event_ticker')}: {exc}",
                    flush=True,
                )
                continue
            snapshots = parse_kalshi_snapshots(
                market_type, event.get("title", ""), markets
            )
            if not snapshots:
                continue

            if fixture["played"]:
                kickoff_ts = int(fixture["match_date"].timestamp())
                start_ts = int((fixture["match_date"] - timedelta(days=14)).timestamp())
                try:
                    candles = kalshi_batch_candles(
                        [s["market_id"] for s in snapshots], start_ts, kickoff_ts
                    )
                except Exception as exc:
                    print(
                        f"  Kalshi skip candles {fixture['match_id']}: {exc}",
                        flush=True,
                    )
                    continue
            else:
                kickoff_ts = None
                candles = {}

            for snapshot in snapshots:
                if fixture["played"]:
                    price = latest_kalshi_price_before_kickoff(
                        candles.get(snapshot["market_id"], []),
                        int(fixture["match_date"].timestamp()),
                    )
                    quality = "recovered_prekickoff_candle"
                    price_time = fixture["match_date"]
                else:
                    price = snapshot["price"]
                    quality = "live_snapshot_before_kickoff"
                    price_time = snapshot["captured_at_utc"]

                if price is None or not 0 < price < 1:
                    continue

                rows.append(
                    {
                        "match_id": fixture["match_id"],
                        "match_date": fixture["match_date"],
                        "source": "kalshi",
                        "market_type": market_type,
                        "outcome": remap_outcome(
                            snapshot["outcome"], reversed_orientation
                        ),
                        "line": snapshot.get("line"),
                        "probability": price,
                        "captured_at_utc": snapshot["captured_at_utc"],
                        "price_time_utc": price_time,
                        "source_market_id": snapshot["market_id"],
                        "source_token_id": None,
                        "quality": quality,
                        "is_prekickoff": True,
                        "is_training_usable": bool(fixture["played"]),
                        "raw_response": json.dumps(
                            snapshot.get("raw_response", {}), default=str
                        ),
                    }
                )
            if len(rows) >= 500:
                insert_rows(rows)
                inserted += len(rows)
                rows.clear()
            if index % 20 == 0:
                print(
                    f"  Kalshi {market_type}: processed {index}/{len(events)}",
                    flush=True,
                )
        insert_rows(rows)
        inserted += len(rows)
        rows.clear()
    insert_rows(rows)
    inserted += len(rows)
    return inserted


def polymarket_events_by_fixture(
    fixtures: dict[frozenset[str], dict],
) -> dict[str, dict]:
    events = []
    events.extend(get_all_wc_events(active=True, closed=False))
    events.extend(get_all_wc_events(active=False, closed=True))

    mapped = {}
    for event in events:
        if classify_event(event) != "match":
            continue
        parsed = parse_poly_title(event.get("title", ""))
        if not parsed:
            continue
        event_home, event_away = parsed
        fixture = fixtures.get(pair_key(event_home, event_away))
        if not fixture:
            continue
        current = mapped.get(fixture["match_id"])
        if current is None or (event.get("volume") or 0) > (current.get("volume") or 0):
            event = dict(event)
            event["_event_home"] = event_home
            event["_event_away"] = event_away
            event["_fixture"] = fixture
            mapped[fixture["match_id"]] = event
    return mapped


def history_points(token_id: str) -> list[dict]:
    data = get_price_history(token_id)
    return data.get("history", data) if isinstance(data, dict) else data


def yes_token(raw_response: dict) -> str | None:
    token_ids = raw_response.get("clobTokenIds")
    if isinstance(token_ids, str):
        token_ids = json.loads(token_ids)
    if not token_ids:
        return None
    return str(token_ids[0])


def parse_poly_recovery_snapshots(
    event: dict, event_home: str, event_away: str
) -> list[dict]:
    snapshots = []
    for market in event.get("markets", []) or []:
        outcome = polymarket_outcome_from_question(
            market.get("question") or "", event_home, event_away
        )
        token_id = yes_token(market)
        if not outcome or not token_id:
            continue
        snapshots.append(
            {
                "source": "polymarket",
                "market_type": "1x2",
                "outcome": outcome,
                "line": None,
                "price": None,
                "volume": None,
                "liquidity": None,
                "bid_ask_spread": None,
                "market_id": str(market.get("conditionId", "")),
                "captured_at_utc": None,
                "raw_response": market,
            }
        )
    return snapshots


def rebuild_polymarket(fixtures: dict[frozenset[str], dict]) -> int:
    rows = []
    inserted = 0
    skip_existing = os.getenv("SKIP_EXISTING", "0") == "1"
    existing_ids = existing_odds_match_ids("polymarket") if skip_existing else set()
    if skip_existing:
        print(
            f"Polymarket: skipping {len(existing_ids)} matches already in DB",
            flush=True,
        )
    events = polymarket_events_by_fixture(fixtures)
    print(f"Polymarket mapped events: {len(events)}", flush=True)
    fixtures_by_id = {f["match_id"]: f for f in fixtures.values()}

    for index, (match_id, fixture) in enumerate(fixtures_by_id.items(), start=1):
        if skip_existing and match_id in existing_ids:
            continue
        event = events.get(match_id)
        if not event:
            print(f"  Polymarket missing event {match_id}", flush=True)
            continue
        full_event = event if event.get("markets") else get_event(event["id"])
        use_history = bool(fixture["played"] or full_event.get("closed"))
        if use_history:
            snapshots = parse_poly_recovery_snapshots(
                full_event, event["_event_home"], event["_event_away"]
            )
        else:
            snapshots = parse_match_markets(full_event)
        if not snapshots:
            print(f"  Polymarket no snapshots {match_id}", flush=True)
            continue
        reversed_orientation = norm(event["_event_home"]) == norm(fixture["away_team"])
        kickoff_ts = int(fixture["match_date"].timestamp())

        for snapshot in snapshots:
            token_id = yes_token(snapshot.get("raw_response", {}))
            if use_history:
                if not token_id:
                    continue
                try:
                    price = latest_price_before_kickoff(
                        history_points(token_id), kickoff_ts
                    )
                except Exception as exc:
                    print(
                        f"  Polymarket skip history {match_id} {token_id}: {exc}",
                        flush=True,
                    )
                    continue
                quality = "recovered_prekickoff"
                price_time = fixture["match_date"]
            else:
                price = snapshot["price"]
                quality = "live_snapshot_before_kickoff"
                price_time = snapshot["captured_at_utc"]

            if price is None or not 0 < price < 1:
                continue

            rows.append(
                {
                    "match_id": fixture["match_id"],
                    "match_date": fixture["match_date"],
                    "source": "polymarket",
                    "market_type": "1x2",
                    "outcome": remap_outcome(snapshot["outcome"], reversed_orientation),
                    "line": None,
                    "probability": price,
                    "captured_at_utc": snapshot["captured_at_utc"],
                    "price_time_utc": price_time,
                    "source_market_id": snapshot["market_id"],
                    "source_token_id": token_id,
                    "quality": quality,
                    "is_prekickoff": True,
                    "is_training_usable": bool(fixture["played"]),
                    "raw_response": json.dumps(
                        snapshot.get("raw_response", {}), default=str
                    ),
                }
            )
        if len(rows) >= 300:
            insert_rows(rows)
            inserted += len(rows)
            rows.clear()
        if index % 10 == 0:
            print(f"  Polymarket processed {index}/{len(fixtures_by_id)}", flush=True)
    insert_rows(rows)
    inserted += len(rows)
    return inserted


def rebuild_xlsx_odds() -> int:
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                WITH x_norm AS (
                    SELECT
                        x.*,
                        CASE x.home
                            WHEN 'Czech Republic' THEN 'Czechia'
                            WHEN 'Turkey' THEN 'Turkiye'
                            WHEN 'Bosnia & Herzegovina' THEN 'Bosnia and Herzegovina'
                            WHEN 'D.R. Congo' THEN 'DR Congo'
                            ELSE x.home
                        END AS home_norm,
                        CASE x.away
                            WHEN 'Czech Republic' THEN 'Czechia'
                            WHEN 'Turkey' THEN 'Turkiye'
                            WHEN 'Bosnia & Herzegovina' THEN 'Bosnia and Herzegovina'
                            WHEN 'D.R. Congo' THEN 'DR Congo'
                            ELSE x.away
                        END AS away_norm
                    FROM public.wc2026_matches x
                ), mapped AS (
                    SELECT
                        w.match_id,
                        w.match_date,
                        x.*,
                        to_jsonb(x.*) AS raw_row
                    FROM x_norm x
                    JOIN public.wc_matches w
                      ON x.date IN (w.match_date::date, (w.match_date + INTERVAL '1 day')::date)
                      AND w.home_team = x.home_norm
                      AND w.away_team = x.away_norm
                ), odds AS (
                    SELECT match_id, match_date, 'xlsx_bet365'::text AS source, 'home'::text AS outcome, b365_h AS decimal_odds, raw_row FROM mapped WHERE b365_h IS NOT NULL
                    UNION ALL SELECT match_id, match_date, 'xlsx_bet365', 'draw', b365_d, raw_row FROM mapped WHERE b365_d IS NOT NULL
                    UNION ALL SELECT match_id, match_date, 'xlsx_bet365', 'away', b365_a, raw_row FROM mapped WHERE b365_a IS NOT NULL
                    UNION ALL SELECT match_id, match_date, 'xlsx_betfair', 'home', bf_h, raw_row FROM mapped WHERE bf_h IS NOT NULL
                    UNION ALL SELECT match_id, match_date, 'xlsx_betfair', 'draw', bf_d, raw_row FROM mapped WHERE bf_d IS NOT NULL
                    UNION ALL SELECT match_id, match_date, 'xlsx_betfair', 'away', bf_a, raw_row FROM mapped WHERE bf_a IS NOT NULL
                    UNION ALL SELECT match_id, match_date, 'xlsx_max', 'home', max_h, raw_row FROM mapped WHERE max_h IS NOT NULL
                    UNION ALL SELECT match_id, match_date, 'xlsx_max', 'draw', max_d, raw_row FROM mapped WHERE max_d IS NOT NULL
                    UNION ALL SELECT match_id, match_date, 'xlsx_max', 'away', max_a, raw_row FROM mapped WHERE max_a IS NOT NULL
                    UNION ALL SELECT match_id, match_date, 'xlsx_avg', 'home', avg_h, raw_row FROM mapped WHERE avg_h IS NOT NULL
                    UNION ALL SELECT match_id, match_date, 'xlsx_avg', 'draw', avg_d, raw_row FROM mapped WHERE avg_d IS NOT NULL
                    UNION ALL SELECT match_id, match_date, 'xlsx_avg', 'away', avg_a, raw_row FROM mapped WHERE avg_a IS NOT NULL
                )
                INSERT INTO public.clean_market_odds
                (match_id, match_date, source, market_type, outcome, line, probability,
                 captured_at_utc, price_time_utc, source_market_id, source_token_id,
                 quality, is_prekickoff, is_training_usable, raw_response)
                SELECT
                    match_id,
                    match_date,
                    source,
                    '1x2'::text AS market_type,
                    outcome,
                    NULL::double precision AS line,
                    1.0 / decimal_odds AS probability,
                    NOW() AS captured_at_utc,
                    match_date AS price_time_utc,
                    source || ':' || match_id || ':' || outcome AS source_market_id,
                    NULL::text AS source_token_id,
                    'xlsx_curated_decimal_odds'::text AS quality,
                    TRUE AS is_prekickoff,
                    TRUE AS is_training_usable,
                    raw_row AS raw_response
                FROM odds
                WHERE decimal_odds > 1
                ON CONFLICT (match_id, source, market_type, outcome, COALESCE(line, '-9999'::DOUBLE PRECISION))
                DO UPDATE SET
                    probability = EXCLUDED.probability,
                    captured_at_utc = EXCLUDED.captured_at_utc,
                    price_time_utc = EXCLUDED.price_time_utc,
                    source_market_id = EXCLUDED.source_market_id,
                    quality = EXCLUDED.quality,
                    is_prekickoff = EXCLUDED.is_prekickoff,
                    is_training_usable = EXCLUDED.is_training_usable,
                    raw_response = EXCLUDED.raw_response
            """),
        )
        return result.rowcount or 0


def main() -> None:
    fixtures = fixtures_by_pair()
    print(f"Fixtures: {len(fixtures)} matches")
    truncate = os.getenv("TRUNCATE_CLEAN_ODDS", "1") != "0"
    prepare_table(truncate=truncate)
    sources = {
        s.strip() for s in os.getenv("SOURCES", "polymarket,kalshi,xlsx").split(",")
    }
    if "polymarket" in sources:
        poly_rows = rebuild_polymarket(fixtures)
        print(f"Polymarket clean rows: {poly_rows}", flush=True)
    if "kalshi" in sources:
        kalshi_rows = rebuild_kalshi(fixtures)
        print(f"Kalshi clean rows: {kalshi_rows}", flush=True)
    if "xlsx" in sources:
        xlsx_rows = rebuild_xlsx_odds()
        print(f"XLSX clean rows upserted: {xlsx_rows}", flush=True)


if __name__ == "__main__":
    main()
