"""Load reference data from OddspAPI: markets, bookmakers, fixtures."""

import json
import sys
from datetime import datetime, timezone

from sqlalchemy import text

from .db import get_engine
from .oddspapi import get_markets, get_bookmakers, get_fixtures, OddspAPIError


def load():
    engine = get_engine()

    print("Pulling markets...")
    markets = get_markets()
    print(f"  Got {len(markets)} markets")

    print("Pulling bookmakers...")
    bookmakers = get_bookmakers()
    print(f"  Got {len(bookmakers)} bookmakers")

    print("Pulling fixtures...")
    fixtures = get_fixtures()
    print(f"  Got {len(fixtures)} fixtures")

    teams_seen: dict[str, int] = {}

    with engine.begin() as conn:
        for fx in fixtures:
            for side in ("participant1", "participant2"):
                pid = fx.get(f"{side}Id")
                name = fx.get(f"{side}Name")
                if not pid or not name:
                    continue
                if pid not in teams_seen:
                    ext = fx.get("externalProviders", {})
                    row = conn.execute(
                        text(
                            "INSERT INTO teams (name, oddspapi_participant_id, sofascore_id) "
                            "VALUES (:n, :pid, :sid) "
                            "ON CONFLICT DO NOTHING RETURNING canonical_id"
                        ),
                        {
                            "n": name,
                            "pid": pid,
                            "sid": ext.get("sofascoreId"),
                        },
                    ).fetchone()
                    if row:
                        teams_seen[pid] = row[0]
                    else:
                        existing = conn.execute(
                            text(
                                "SELECT canonical_id FROM teams WHERE oddspapi_participant_id = :pid"
                            ),
                            {"pid": pid},
                        ).fetchone()
                        if existing:
                            teams_seen[pid] = existing[0]

        print(f"  Teams in DB: {len(teams_seen)}")

        for fx in fixtures:
            home_pid = fx.get("participant1Id")
            away_pid = fx.get("participant2Id")
            home_id = teams_seen.get(home_pid)
            away_id = teams_seen.get(away_pid)
            if not home_id or not away_id:
                print(f"  Skipping fixture {fx.get('fixtureId')}: missing team mapping")
                continue

            start_time = fx.get("startTime")
            if start_time:
                start_time = start_time.replace("Z", "+00:00")

            conn.execute(
                text(
                    """INSERT INTO matches
                    (oddspapi_fixture_id, date_utc, kickoff_utc, home_team_id, away_team_id, tournament, status)
                    VALUES (:fid, :date, :ko, :hid, :aid, :tourn, :status)
                    ON CONFLICT (oddspapi_fixture_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        kickoff_utc = EXCLUDED.kickoff_utc"""
                ),
                {
                    "fid": fx["fixtureId"],
                    "date": start_time[:10] if start_time else None,
                    "ko": start_time,
                    "hid": home_id,
                    "aid": away_id,
                    "tourn": "FIFA World Cup 2026",
                    "status": str(fx.get("statusId", "")),
                },
            )

        match_count = conn.execute(text("SELECT COUNT(*) FROM matches")).scalar()
        print(f"  Matches in DB: {match_count}")

    ref = {
        "markets": markets,
        "bookmakers": bookmakers,
        "fixture_count": len(fixtures),
        "team_count": len(teams_seen),
        "match_count": match_count,
        "loaded_at": datetime.now(timezone.utc).isoformat(),
    }
    with open("data/reference_meta.json", "w") as f:
        json.dump(ref, f, indent=2, default=str)
    print(f"  Metadata saved to data/reference_meta.json")


if __name__ == "__main__":
    try:
        load()
    except OddspAPIError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
