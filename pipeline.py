#!/usr/bin/env python3
"""One-time data pipeline for WC 2026 — uses parse.bot (surgical), free APIs, and SQLAlchemy."""

import json, os, time, io
from datetime import datetime, timezone

import httpx
import pandas as pd
from sqlalchemy import text
from footyquant.db import get_engine

PARSE_KEY = os.environ["PARSE_API_KEY"]
PARSE_URL = "https://api.parse.bot/scraper/645b8e03-271d-4c85-97e7-35d5733a2d78"
POLY_GAMMA = "https://gamma-api.polymarket.com"
KALSHI = "https://external-api.kalshi.com/trade-api/v2"

FOOTBALL_DATA_CSVS = {
    "EPL_2526": "https://www.football-data.co.uk/mmz4281/2526/E0.csv",
    "EPL_2425": "https://www.football-data.co.uk/mmz4281/2425/E0.csv",
    "LaLiga_2526": "https://www.football-data.co.uk/mmz4281/2526/SP1.csv",
    "LaLiga_2425": "https://www.football-data.co.uk/mmz4281/2425/SP1.csv",
    "Bundesliga_2526": "https://www.football-data.co.uk/mmz4281/2526/D1.csv",
    "Bundesliga_2425": "https://www.football-data.co.uk/mmz4281/2425/D1.csv",
    "SerieA_2526": "https://www.football-data.co.uk/mmz4281/2526/I1.csv",
    "Ligue1_2526": "https://www.football-data.co.uk/mmz4281/2526/F1.csv",
}

CREDITS = 0
CREDIT_LIMIT = 180
engine = get_engine()


def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}")


def parse_get(endpoint: str, params: dict | None = None) -> dict:
    global CREDITS
    if CREDITS >= CREDIT_LIMIT:
        raise RuntimeError("Credit limit reached")
    CREDITS += 1
    with httpx.Client(timeout=60) as c:
        r = c.get(
            f"{PARSE_URL}/{endpoint}", params=params, headers={"X-API-Key": PARSE_KEY}
        )
    r.raise_for_status()
    return r.json()


def create_tables():
    log("Creating tables...")
    sqls = [
        """CREATE TABLE IF NOT EXISTS wc_matches (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            match_id TEXT UNIQUE NOT NULL,
            match_date TIMESTAMPTZ, stage TEXT, group_name TEXT,
            home_team TEXT NOT NULL, away_team TEXT NOT NULL,
            home_score INT, away_score INT, result_1x2 TEXT,
            btts BOOLEAN, total_goals INT, venue TEXT,
            source TEXT DEFAULT 'fotmob', created_at TIMESTAMPTZ DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS team_stats (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            team_name TEXT NOT NULL, competition TEXT NOT NULL,
            as_of_date DATE, matches_played INT, wins INT, draws INT, losses INT,
            goals_for INT, goals_against INT, xg_for FLOAT, xg_against FLOAT,
            form_last5 TEXT, source TEXT, created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(team_name, competition, as_of_date))""",
        """CREATE TABLE IF NOT EXISTS match_odds (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            match_id TEXT NOT NULL REFERENCES wc_matches(match_id),
            source TEXT NOT NULL, market_type TEXT NOT NULL,
            implied_probability FLOAT, raw_value TEXT,
            snapshot_time TIMESTAMPTZ DEFAULT NOW(), source_market_id TEXT,
            UNIQUE(match_id, source, market_type, snapshot_time))""",
        """CREATE TABLE IF NOT EXISTS historical_odds (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            date DATE NOT NULL, home_team TEXT NOT NULL, away_team TEXT NOT NULL,
            competition TEXT NOT NULL, b365_home FLOAT, b365_draw FLOAT, b365_away FLOAT,
            b365_over25 FLOAT, b365_under25 FLOAT, result_1x2 TEXT,
            home_score INT, away_score INT, btts BOOLEAN, total_goals INT,
            source TEXT DEFAULT 'football_data_co_uk', created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(date, home_team, away_team))""",
        """CREATE TABLE IF NOT EXISTS prediction_market_snapshots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            platform TEXT NOT NULL, market_id TEXT NOT NULL, market_title TEXT,
            match_id TEXT, outcome TEXT, implied_probability FLOAT,
            volume_usd FLOAT, snapshot_time TIMESTAMPTZ DEFAULT NOW(),
            raw_response JSONB, UNIQUE(platform, market_id, snapshot_time))""",
    ]
    with engine.begin() as conn:
        for sql in sqls:
            conn.execute(text(sql))
    log("  Tables ready")


def step1_bootstrap():
    log("=== Step 1: Bootstrap (parse.bot) ===")
    data = parse_get("get_league_details", {"league_id": "77"})
    fixtures = data["data"]["fixtures"]["allMatches"]
    log(f"  Got {len(fixtures)} fixtures")

    match_rows = []
    for f in fixtures:
        mid = f["id"]
        home = f["home"]["name"]
        away = f["away"]["name"]
        group = f.get("group")
        utc = f["status"]["utcTime"]
        finished = f["status"].get("finished", False)
        score_str = f["status"].get("scoreStr", "")
        home_s = away_s = None
        if score_str and " - " in score_str:
            parts = score_str.split(" - ")
            home_s = int(parts[0]) if parts[0].isdigit() else None
            away_s = int(parts[1]) if parts[1].isdigit() else None

        row = {
            "match_id": mid,
            "match_date": utc,
            "stage": "group" if group else "knockout",
            "group_name": group,
            "home_team": home,
            "away_team": away,
            "home_score": home_s,
            "away_score": away_s,
            "result_1x2": "H"
            if home_s is not None and away_s is not None and home_s > away_s
            else "A"
            if home_s is not None and away_s is not None and away_s > home_s
            else "D"
            if home_s is not None and away_s is not None and home_s == away_s
            else None,
            "btts": home_s is not None
            and away_s is not None
            and home_s > 0
            and away_s > 0,
            "total_goals": home_s + away_s
            if home_s is not None and away_s is not None
            else None,
            "source": "fotmob",
        }
        match_rows.append(row)

    with engine.begin() as conn:
        for row in match_rows:
            conn.execute(
                text("""INSERT INTO wc_matches (match_id, match_date, stage, group_name,
                    home_team, away_team, home_score, away_score, result_1x2, btts, total_goals, source)
                    VALUES (:match_id, CAST(:match_date AS TIMESTAMPTZ), :stage, :group_name,
                    :home_team, :away_team, :home_score, :away_score, :result_1x2, :btts, :total_goals, :source)
                    ON CONFLICT (match_id) DO UPDATE SET
                    home_score=EXCLUDED.home_score, away_score=EXCLUDED.away_score,
                    result_1x2=EXCLUDED.result_1x2, btts=EXCLUDED.btts, total_goals=EXCLUDED.total_goals"""),
                row,
            )
    log(f"  Inserted {len(match_rows)} matches")

    teams_data = data["data"]["stats"]["teams"]
    team_rows = []
    for t in teams_data:
        name = t["participant"]["name"]
        val = t["participant"].get("value")
        stat_name = t["participant"]["stat"]["name"]
        if stat_name == "rating_team":
            team_rows.append(
                {
                    "team_name": name,
                    "competition": "WC2026",
                    "as_of_date": datetime.now(timezone.utc).date().isoformat(),
                    "source": "fotmob",
                }
            )
    if team_rows:
        with engine.begin() as conn:
            for row in team_rows:
                conn.execute(
                    text("""INSERT INTO team_stats (team_name, competition, as_of_date, source)
                        VALUES (:team_name, :competition, CAST(:as_of_date AS DATE), :source)
                        ON CONFLICT (team_name, competition, as_of_date) DO NOTHING"""),
                    row,
                )
    log(f"  Seeded {len(team_rows)} team stat rows")
    log(f"✓ Step 1 done — credits: {CREDITS}")


def step2_match_details():
    log("=== Step 2: Match Details ===")
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT match_id FROM wc_matches WHERE home_score IS NOT NULL LIMIT 30"
            )
        ).fetchall()

    enriched = 0
    for (mid,) in rows:
        if CREDITS >= CREDIT_LIMIT:
            break
        try:
            data = parse_get("get_match_details", {"match_id": mid})
            general = data["data"]["general"]
            header = data["data"]["header"]
            home_s = header["teams"][0].get("score")
            away_s = header["teams"][1].get("score")
            venue = general.get("venue") or general.get("stadium")
            with engine.begin() as conn:
                updates = {}
                if home_s is not None:
                    updates["home_score"] = int(home_s)
                    updates["away_score"] = int(away_s)
                    hs, aws = int(home_s), int(away_s)
                    updates["result_1x2"] = (
                        "H" if hs > aws else "A" if aws > hs else "D"
                    )
                    updates["btts"] = hs > 0 and aws > 0
                    updates["total_goals"] = hs + aws
                if venue:
                    updates["venue"] = venue
                if updates:
                    updates["mid"] = mid
                    set_clause = ", ".join(f"{k}=:{k}" for k in updates if k != "mid")
                    conn.execute(
                        text(f"UPDATE wc_matches SET {set_clause} WHERE match_id=:mid"),
                        updates,
                    )
            enriched += 1
        except Exception as e:
            log(f"  WARN match {mid}: {e}")

    log(f"  Enriched {enriched} matches")
    log(f"✓ Step 2 done — credits: {CREDITS}")


def step3_historical_odds():
    log("=== Step 3: Historical Odds ===")
    total = 0
    with httpx.Client(timeout=30) as c:
        for comp, url in FOOTBALL_DATA_CSVS.items():
            try:
                r = c.get(url)
                r.raise_for_status()
                df = pd.read_csv(io.StringIO(r.text))
                if not {
                    "Date",
                    "HomeTeam",
                    "AwayTeam",
                    "B365H",
                    "B365D",
                    "B365A",
                }.issubset(set(df.columns)):
                    log(f"  SKIP {comp}: missing columns")
                    continue
                rows = []
                for _, rw in df.iterrows():
                    if pd.isna(rw.get("B365H")):
                        continue
                    fthg = rw.get("FTHG")
                    ftag = rw.get("FTAG")
                    hs = int(fthg) if pd.notna(fthg) else None
                    aws = int(ftag) if pd.notna(ftag) else None
                    result = rw.get("FTR") if pd.notna(rw.get("FTR")) else None
                    btts = hs is not None and aws is not None and hs > 0 and aws > 0
                    tg = (
                        (hs or 0) + (aws or 0)
                        if hs is not None and aws is not None
                        else None
                    )
                    o25 = rw.get("B365>2.5") if pd.notna(rw.get("B365>2.5")) else None
                    u25 = rw.get("B365<2.5") if pd.notna(rw.get("B365<2.5")) else None
                    rows.append(
                        {
                            "date": str(rw["Date"]),
                            "home_team": str(rw["HomeTeam"]),
                            "away_team": str(rw["AwayTeam"]),
                            "competition": comp,
                            "b365_home": float(rw["B365H"]),
                            "b365_draw": float(rw["B365D"]),
                            "b365_away": float(rw["B365A"]),
                            "b365_over25": float(o25) if o25 is not None else None,
                            "b365_under25": float(u25) if u25 is not None else None,
                            "result_1x2": result,
                            "home_score": hs,
                            "away_score": aws,
                            "btts": btts if hs is not None else None,
                            "total_goals": tg,
                        }
                    )
                with engine.begin() as conn:
                    for row in rows:
                        conn.execute(
                            text("""INSERT INTO historical_odds (date, home_team, away_team, competition,
                                b365_home, b365_draw, b365_away, b365_over25, b365_under25,
                                result_1x2, home_score, away_score, btts, total_goals)
                                VALUES (CAST(:date AS DATE), :home_team, :away_team, :competition,
                                :b365_home, :b365_draw, :b365_away, :b365_over25, :b365_under25,
                                :result_1x2, :home_score, :away_score, :btts, :total_goals)
                                ON CONFLICT (date, home_team, away_team) DO UPDATE SET
                                b365_home=EXCLUDED.b365_home, b365_draw=EXCLUDED.b365_draw,
                                b365_away=EXCLUDED.b365_away"""),
                            row,
                        )
                log(f"  {comp}: {len(rows)} rows")
                total += len(rows)
            except Exception as e:
                log(f"  ERROR {comp}: {e}")
    log(f"  Total: {total} rows")
    log(f"✓ Step 3 done — credits: {CREDITS}")


def step4_polymarket():
    log("=== Step 4: Polymarket ===")
    with httpx.Client(timeout=30) as c:
        try:
            r = c.get(f"{POLY_GAMMA}/markets", params={"tag": "soccer", "limit": 200})
            markets = r.json()
        except Exception as e:
            log(f"  ERROR: {e}")
            markets = []

    if isinstance(markets, dict):
        markets = markets.get("data") or markets.get("markets") or []

    wc_kw = ["world cup", "fifa", "wc 2026", "worldcup2026"]
    wc_m = [
        m
        for m in markets
        if isinstance(m, dict)
        and any(
            kw in (m.get("question") or m.get("title") or "").lower() for kw in wc_kw
        )
    ]
    log(f"  Found {len(wc_m)} WC markets")

    with engine.connect() as conn:
        db_m = conn.execute(
            text("SELECT match_id, home_team, away_team FROM wc_matches")
        ).fetchall()

    snaps, odds = [], []
    for m in wc_m:
        mid = str(m.get("conditionId") or m.get("id", ""))
        title = m.get("question") or m.get("title") or ""
        outcomes = m.get("outcomes") or []
        prices = m.get("outcomePrices") or []
        if isinstance(outcomes, str):
            outcomes = json.loads(outcomes) if outcomes else []
        if isinstance(prices, str):
            prices = json.loads(prices) if prices else []
        volume = m.get("volume")
        try:
            volume = float(volume) if volume else None
        except (ValueError, TypeError):
            volume = None

        matched = None
        tl = title.lower()
        for dm in db_m:
            if dm.home_team.lower() in tl and dm.away_team.lower() in tl:
                matched = dm.match_id
                break

        for i, outcome in enumerate(outcomes):
            prob = float(prices[i]) if i < len(prices) and prices[i] else None
            if prob is None or prob <= 0 or prob >= 1:
                continue
            snaps.append(
                {
                    "platform": "polymarket",
                    "market_id": mid,
                    "market_title": title,
                    "match_id": matched,
                    "outcome": outcome.lower(),
                    "implied_probability": prob,
                    "volume_usd": volume,
                    "snapshot_time": datetime.now(timezone.utc).isoformat(),
                    "raw_response": json.dumps(m),
                }
            )
            if matched:
                odds.append(
                    {
                        "match_id": matched,
                        "source": "polymarket",
                        "market_type": f"1x2_{outcome.lower()}",
                        "implied_probability": prob,
                        "raw_value": str(prob),
                        "snapshot_time": datetime.now(timezone.utc).isoformat(),
                        "source_market_id": mid,
                    }
                )

    with engine.begin() as conn:
        for row in snaps:
            conn.execute(
                text("""INSERT INTO prediction_market_snapshots
                    (platform, market_id, market_title, match_id, outcome,
                     implied_probability, volume_usd, snapshot_time, raw_response)
                    VALUES (:platform, :market_id, :market_title, :match_id, :outcome,
                            :implied_probability, :volume_usd, CAST(:snapshot_time AS TIMESTAMPTZ), CAST(:raw_response AS JSONB))
                    ON CONFLICT (platform, market_id, snapshot_time) DO NOTHING"""),
                row,
            )
        for row in odds:
            conn.execute(
                text("""INSERT INTO match_odds
                    (match_id, source, market_type, implied_probability, raw_value, snapshot_time, source_market_id)
                    VALUES (:match_id, :source, :market_type, :implied_probability, :raw_value,
                            CAST(:snapshot_time AS TIMESTAMPTZ), :source_market_id)
                    ON CONFLICT (match_id, source, market_type, snapshot_time) DO NOTHING"""),
                row,
            )
    log(f"  Stored {len(snaps)} snapshots, {len(odds)} odds")
    log(f"✓ Step 4 done — credits: {CREDITS}")


def step5_kalshi():
    log("=== Step 5: Kalshi ===")
    all_m = []
    with httpx.Client(timeout=30) as c:
        for status in ["open", "settled"]:
            try:
                r = c.get(f"{KALSHI}/markets", params={"status": status, "limit": 200})
                all_m.extend((r.json().get("markets") or []))
            except Exception as e:
                log(f"  ERROR {status}: {e}")

    wc_kw = ["world cup", "fifa", "wc 2026", "kxwc"]
    wc_m = [
        m
        for m in all_m
        if isinstance(m, dict)
        and any(kw in (m.get("title") or m.get("ticker") or "").lower() for kw in wc_kw)
    ]
    log(f"  Found {len(wc_m)} WC markets")

    with engine.connect() as conn:
        db_m = conn.execute(
            text("SELECT match_id, home_team, away_team FROM wc_matches")
        ).fetchall()

    snaps, odds = [], []
    for m in wc_m:
        ticker = m.get("ticker", "")
        title = m.get("title") or ticker
        yes_bid = m.get("yes_bid")
        yes_ask = m.get("yes_ask")
        if yes_bid is not None and yes_ask is not None:
            prob = (float(yes_bid) + float(yes_ask)) / 2.0
        elif m.get("last_price_dollars") is not None:
            prob = float(m["last_price_dollars"])
        else:
            prob = None
        volume = m.get("volume_dollars")
        try:
            volume = float(volume) if volume else None
        except (ValueError, TypeError):
            volume = None

        matched = None
        tl = title.lower()
        for dm in db_m:
            if dm.home_team.lower() in tl and dm.away_team.lower() in tl:
                matched = dm.match_id
                break

        outcome = m.get("outcome") or m.get("market_type") or "yes"
        snaps.append(
            {
                "platform": "kalshi",
                "market_id": ticker,
                "market_title": title,
                "match_id": matched,
                "outcome": str(outcome),
                "implied_probability": prob,
                "volume_usd": volume,
                "snapshot_time": datetime.now(timezone.utc).isoformat(),
                "raw_response": json.dumps(m),
            }
        )
        if matched and prob is not None:
            odds.append(
                {
                    "match_id": matched,
                    "source": "kalshi",
                    "market_type": f"1x2_{outcome}".lower(),
                    "implied_probability": prob,
                    "raw_value": str(prob),
                    "snapshot_time": datetime.now(timezone.utc).isoformat(),
                    "source_market_id": ticker,
                }
            )

    with engine.begin() as conn:
        for row in snaps:
            conn.execute(
                text("""INSERT INTO prediction_market_snapshots
                    (platform, market_id, market_title, match_id, outcome,
                     implied_probability, volume_usd, snapshot_time, raw_response)
                    VALUES (:platform, :market_id, :market_title, :match_id, :outcome,
                            :implied_probability, :volume_usd, CAST(:snapshot_time AS TIMESTAMPTZ), CAST(:raw_response AS JSONB))
                    ON CONFLICT (platform, market_id, snapshot_time) DO NOTHING"""),
                row,
            )
        for row in odds:
            conn.execute(
                text("""INSERT INTO match_odds
                    (match_id, source, market_type, implied_probability, raw_value, snapshot_time, source_market_id)
                    VALUES (:match_id, :source, :market_type, :implied_probability, :raw_value,
                            CAST(:snapshot_time AS TIMESTAMPTZ), :source_market_id)
                    ON CONFLICT (match_id, source, market_type, snapshot_time) DO NOTHING"""),
                row,
            )
    log(f"  Stored {len(snaps)} snapshots, {len(odds)} odds")
    log(f"✓ Step 5 done — credits: {CREDITS}")


def validate():
    log("=== Validation ===")
    with engine.connect() as conn:
        wc = conn.execute(
            text("SELECT COUNT(*) as c, COUNT(home_score) as p FROM wc_matches")
        ).fetchone()
        ts = conn.execute(
            text("SELECT COUNT(*) as c FROM team_stats WHERE competition='WC2026'")
        ).fetchone()
        ts_xg = conn.execute(
            text(
                "SELECT COUNT(*) as c FROM team_stats WHERE competition='WC2026' AND xg_for IS NOT NULL"
            )
        ).fetchone()
        mo = conn.execute(text("SELECT COUNT(*) as c FROM match_odds")).fetchone()
        mo_src = conn.execute(
            text("SELECT source, COUNT(*) as c FROM match_odds GROUP BY source")
        ).fetchall()
        ho = conn.execute(text("SELECT COUNT(*) as c FROM historical_odds")).fetchone()
        ho_comp = conn.execute(
            text(
                "SELECT competition, COUNT(*) as c FROM historical_odds GROUP BY competition"
            )
        ).fetchall()
        pms = conn.execute(
            text("SELECT COUNT(*) as c FROM prediction_market_snapshots")
        ).fetchone()
        pms_plat = conn.execute(
            text(
                "SELECT platform, COUNT(*) as c FROM prediction_market_snapshots GROUP BY platform"
            )
        ).fetchall()

    print()
    print("  ┌─────────────────────────────────────────┐")
    print("  │  DATA PIPELINE VALIDATION REPORT        │")
    print("  ├─────────────────────────────────────────┤")
    print(f"  │  wc_matches          total: {wc.c:<5}           │")
    print(f"  │    → with scores:    {wc.p:<5}  (played)       │")
    print(f"  │    → upcoming:       {wc.c - wc.p:<5}               │")
    print(f"  │  team_stats          total: {ts.c:<5} teams      │")
    print(f"  │    → with xG data:   {ts_xg.c:<5}                │")
    print(f"  │  match_odds          total: {mo.c:<5} rows       │")
    print(f"  │    → by source:                         │")
    for s in mo_src:
        print(f"  │       {s.source:<16} {s.c:<5}               │")
    print(f"  │  historical_odds     total: {ho.c:<5} rows  │")
    print(f"  │    → by competition:                    │")
    for c2 in ho_comp:
        print(f"  │       {c2.competition:<16} {c2.c:<5}               │")
    print(f"  │  prediction_market_  total: {pms.c:<5} rows      │")
    print(f"  │  snapshots                              │")
    for p in pms_plat:
        print(f"  │    → {p.platform:<16} {p.c:<5}               │")
    print(f"  │  parse.bot credits   used: {CREDITS} / 200    │")
    print("  ├─────────────────────────────────────────┤")

    gaps = []
    if wc.c < 48:
        gaps.append(f"wc_matches ({wc.c}) < 48")
    if ts.c < 16:
        gaps.append(f"team_stats ({ts.c}) < 16 teams")
    if mo.c == 0:
        gaps.append("match_odds has 0 rows")
    if ho.c < 500:
        gaps.append(f"historical_odds ({ho.c}) < 500 rows")

    if gaps:
        print(f"  │  VERDICT: GAPS FOUND — see below ✗       │")
        for g in gaps:
            print(f"  │    • {g:<37} │")
    else:
        print(f"  │  VERDICT: READY FOR MODELING ✓            │")
    print("  └─────────────────────────────────────────┘")
    print()
    return len(gaps) == 0


def main():
    log("=" * 50)
    log("WC 2026 Data Pipeline")
    log("=" * 50)
    create_tables()
    step1_bootstrap()
    step2_match_details()
    step3_historical_odds()
    step4_polymarket()
    step5_kalshi()
    validate()
    log("Done.")


if __name__ == "__main__":
    main()
