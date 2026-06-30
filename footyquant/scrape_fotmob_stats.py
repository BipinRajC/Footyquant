"""Scrape rich match stats from Fotmob for knockout WC 2026 matches."""

import json
import os
import re
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from scrapling.fetchers import Fetcher
from sqlalchemy import text
from supabase import create_client

load_dotenv()

from footyquant.db import get_engine

TEAM_ALIASES = {
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Turkey": "Turkiye",
    "Iran": "IR Iran",
    "D.R. Congo": "DR Congo",
    "Czech Republic": "Czechia",
    "South Korea": "Korea Republic",
    "Curacao": "Curaçao",
}


def normalize(name):
    return TEAM_ALIASES.get(name, name)


def extract_int(val):
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def extract_float(val):
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def parse_stat_value(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return val
    s = str(val).strip()
    s = s.replace("%", "").strip()
    m = re.match(r"(\d+)", s)
    if m:
        return int(m.group(1))
    try:
        return float(s)
    except ValueError:
        return None


def get_stat(stats_list, section_key, stat_key, index):
    """Extract a stat value from the nested stats structure."""
    for section in stats_list:
        if section.get("key") == section_key or section.get("title") == section_key:
            for stat in section.get("stats", []):
                if stat.get("key") == stat_key or stat.get("title") == stat_key:
                    vals = stat.get("stats", [])
                    if len(vals) > index and vals[index] is not None:
                        return parse_stat_value(vals[index])
    return None


def get_stat_by_title(stats_list, section_title, stat_title, index):
    """Extract a stat value by title."""
    for section in stats_list:
        if section.get("title") == section_title:
            for stat in section.get("stats", []):
                if stat.get("title") == stat_title:
                    vals = stat.get("stats", [])
                    if len(vals) > index and vals[index] is not None:
                        return parse_stat_value(vals[index])
    return None


def parse_match_data(fotmob_id):
    """Fetch and parse match data from Fotmob."""
    page = Fetcher.get(
        f"https://www.fotmob.com/match/{fotmob_id}",
        impersonate="chrome",
    )
    if page.status != 200:
        print(f"    HTTP {page.status} for match {fotmob_id}")
        return None

    text = page.text
    for script in page.css("script"):
        s = str(script.text)
        if "pageProps" in s and "general" in s:
            start = s.find("{")
            data = json.loads(s[start:])
            break
    else:
        print(f"    No pageProps found for match {fotmob_id}")
        return None

    props = data["props"]["pageProps"]
    general = props["general"]
    header = props["header"]
    content = props.get("content", {})

    teams = header["teams"]
    home_name = teams[0]["name"]
    away_name = teams[1]["name"]
    home_score = teams[0].get("score", 0)
    away_score = teams[1].get("score", 0)
    status_info = header.get("status", {})
    finished = status_info.get("finished", False)

    if not finished:
        return None

    match_date_str = general.get("matchTimeUTCDate", "")
    try:
        match_date = datetime.fromisoformat(match_date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        match_date = None

    result = None
    if home_score is not None and away_score is not None:
        if home_score > away_score:
            result = "H"
        elif home_score < away_score:
            result = "A"
        else:
            result = "D"

    btts = bool(home_score and away_score and home_score > 0 and away_score > 0)
    total_goals = (home_score or 0) + (away_score or 0)

    # AET / penalties detection
    match_outcome = "regular"
    aet_home = teams[0].get("etScore")
    aet_away = teams[1].get("etScore")
    pens_home = teams[0].get("penaltyScore")
    pens_away = teams[1].get("penaltyScore")
    if pens_home is not None or pens_away is not None:
        match_outcome = "penalties"
    elif aet_home is not None or aet_away is not None:
        match_outcome = "aet"

    stats_data = content.get("stats", {})
    periods = stats_data.get("Periods", {})
    all_stats = (
        periods.get("All", {}).get("stats", []) if isinstance(periods, dict) else []
    )
    first_half_stats = (
        periods.get("FirstHalf", {}).get("stats", [])
        if isinstance(periods, dict)
        else []
    )
    second_half_stats = (
        periods.get("SecondHalf", {}).get("stats", [])
        if isinstance(periods, dict)
        else []
    )
    et_stats = (
        periods.get("ExtraTime", {}).get("stats", [])
        if isinstance(periods, dict)
        else []
    )

    row = {
        "fotmob_match_id": str(fotmob_id),
        "match_id": None,
        "match_date": match_date,
        "home_team": home_name,
        "away_team": away_name,
        "home_score": home_score,
        "away_score": away_score,
        "result_1x2": result,
        "btts": btts,
        "total_goals": total_goals,
        "match_outcome": match_outcome,
        "aet_home_score": aet_home,
        "aet_away_score": aet_away,
        "penalties_home_score": pens_home,
        "penalties_away_score": pens_away,
        "aet_xg_home": get_stat(et_stats, "top_stats", "expected_goals", 0),
        "aet_xg_away": get_stat(et_stats, "top_stats", "expected_goals", 1),
        "aet_shots_home": get_stat(et_stats, "top_stats", "total_shots", 0),
        "aet_shots_away": get_stat(et_stats, "top_stats", "total_shots", 1),
        "aet_shots_ontarget_home": get_stat(et_stats, "top_stats", "ShotsOnTarget", 0),
        "aet_shots_ontarget_away": get_stat(et_stats, "top_stats", "ShotsOnTarget", 1),
        "possession_home": get_stat(all_stats, "top_stats", "BallPossesion", 0),
        "possession_away": get_stat(all_stats, "top_stats", "BallPossesion", 1),
        "xg_home": get_stat(all_stats, "top_stats", "expected_goals", 0),
        "xg_away": get_stat(all_stats, "top_stats", "expected_goals", 1),
        "xgot_home": get_stat(
            all_stats, "expected_goals", "expected_goals_on_target", 0
        ),
        "xgot_away": get_stat(
            all_stats, "expected_goals", "expected_goals_on_target", 1
        ),
        "shots_home": get_stat(all_stats, "top_stats", "total_shots", 0),
        "shots_away": get_stat(all_stats, "top_stats", "total_shots", 1),
        "shots_ontarget_home": get_stat(all_stats, "top_stats", "ShotsOnTarget", 0),
        "shots_ontarget_away": get_stat(all_stats, "top_stats", "ShotsOnTarget", 1),
        "shots_offtarget_home": get_stat(all_stats, "shots", "ShotsOffTarget", 0),
        "shots_offtarget_away": get_stat(all_stats, "shots", "ShotsOffTarget", 1),
        "blocked_shots_home": get_stat(all_stats, "shots", "blocked_shots", 0),
        "blocked_shots_away": get_stat(all_stats, "shots", "blocked_shots", 1),
        "corners_home": get_stat(all_stats, "top_stats", "corners", 0),
        "corners_away": get_stat(all_stats, "top_stats", "corners", 1),
        "yellow_cards_home": get_stat(all_stats, "top_stats", "yellow_cards", 0),
        "yellow_cards_away": get_stat(all_stats, "top_stats", "yellow_cards", 1),
        "fouls_home": get_stat(all_stats, "discipline", "fouls", 0),
        "fouls_away": get_stat(all_stats, "discipline", "fouls", 1),
        "passes_accurate_home": get_stat(all_stats, "top_stats", "accurate_passes", 0),
        "passes_accurate_away": get_stat(all_stats, "top_stats", "accurate_passes", 1),
        "passes_total_home": get_stat(all_stats, "passes", "passes", 0),
        "passes_total_away": get_stat(all_stats, "passes", "passes", 1),
        "tackles_home": get_stat(all_stats, "defence", "matchstats.headers.tackles", 0),
        "tackles_away": get_stat(all_stats, "defence", "matchstats.headers.tackles", 1),
        "interceptions_home": get_stat(all_stats, "defence", "interceptions", 0),
        "interceptions_away": get_stat(all_stats, "defence", "interceptions", 1),
        "clearances_home": get_stat(all_stats, "defence", "clearances", 0),
        "clearances_away": get_stat(all_stats, "defence", "clearances", 1),
        "saves_home": get_stat(all_stats, "defence", "keeper_saves", 0),
        "saves_away": get_stat(all_stats, "defence", "keeper_saves", 1),
        "duels_won_home": get_stat(all_stats, "duels", "duel_won", 0),
        "duels_won_away": get_stat(all_stats, "duels", "duel_won", 1),
        "aerials_won_home": get_stat(all_stats, "duels", "aerials_won", 0),
        "aerials_won_away": get_stat(all_stats, "duels", "aerials_won", 1),
        "dribbles_successful_home": get_stat(
            all_stats, "duels", "dribbles_succeeded", 0
        ),
        "dribbles_successful_away": get_stat(
            all_stats, "duels", "dribbles_succeeded", 1
        ),
        "big_chances_home": get_stat(all_stats, "top_stats", "big_chance", 0),
        "big_chances_away": get_stat(all_stats, "top_stats", "big_chance", 1),
        "big_chances_missed_home": get_stat(
            all_stats, "top_stats", "big_chance_missed_title", 0
        ),
        "big_chances_missed_away": get_stat(
            all_stats, "top_stats", "big_chance_missed_title", 1
        ),
        "touches_opp_box_home": get_stat(all_stats, "top_stats", "touches_opp_box", 0),
        "touches_opp_box_away": get_stat(all_stats, "top_stats", "touches_opp_box", 1),
        "offsides_home": get_stat(all_stats, "passes", "Offsides", 0),
        "offsides_away": get_stat(all_stats, "passes", "Offsides", 1),
        "possession_ht_home": get_stat(
            first_half_stats, "top_stats", "BallPossesion", 0
        ),
        "possession_ht_away": get_stat(
            first_half_stats, "top_stats", "BallPossesion", 1
        ),
        "xg_firsthalf_home": get_stat(
            first_half_stats, "top_stats", "expected_goals", 0
        ),
        "xg_firsthalf_away": get_stat(
            first_half_stats, "top_stats", "expected_goals", 1
        ),
        "xg_secondhalf_home": get_stat(
            second_half_stats, "top_stats", "expected_goals", 0
        ),
        "xg_secondhalf_away": get_stat(
            second_half_stats, "top_stats", "expected_goals", 1
        ),
        "shots_firsthalf_home": get_stat(
            first_half_stats, "top_stats", "total_shots", 0
        ),
        "shots_firsthalf_away": get_stat(
            first_half_stats, "top_stats", "total_shots", 1
        ),
        "shots_secondhalf_home": get_stat(
            second_half_stats, "top_stats", "total_shots", 0
        ),
        "shots_secondhalf_away": get_stat(
            second_half_stats, "top_stats", "total_shots", 1
        ),
        "raw_response": "{}",
        "scraped_at": datetime.now(timezone.utc),
    }

    return row


def find_fotmob_id(home_team, away_team, match_date):
    """Try to find a Fotmob match ID by searching."""
    date_str = match_date.strftime("%Y%m%d") if match_date else ""
    for team in [home_team, away_team]:
        try:
            page = Fetcher.get(
                f"https://www.fotmob.com/search?q={team}",
                impersonate="chrome",
            )
            if page.status == 200:
                text = page.text
                ids = re.findall(rf"/matches/[^\"']+#(\d+)", text)
                if ids:
                    return ids[0]
        except Exception:
            pass
        time.sleep(0.5)
    return None


def main():
    engine = get_engine()

    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_ANON_KEY", "") or os.environ.get(
        "SUPABASE_KEY", ""
    )
    supabase = (
        create_client(supabase_url, supabase_key)
        if supabase_url and supabase_key
        else None
    )

    with engine.connect() as conn:
        existing = {
            row[0]
            for row in conn.execute(
                text("SELECT fotmob_match_id FROM public.wcmatches_richstat_fotmob")
            ).fetchall()
        }

    api_key = os.environ.get("PARSE_API_KEY", "")
    known_ids = []
    if api_key:
        print("    Fetching match IDs from Parse.bot API...")
        try:
            import urllib.request

            req = urllib.request.Request(
                "https://api.parse.bot/scraper/645b8e03-271d-4c85-97e7-35d5733a2d78/get_league_details?league_id=77",
                headers={"X-API-Key": api_key},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                api_data = json.loads(resp.read().decode())
            all_matches = api_data["data"]["fixtures"]["allMatches"]
            known_ids = [m["id"] for m in all_matches if m.get("id")]
            print(f"    Found {len(known_ids)} total WC2026 matches from API")
        except Exception as e:
            print(f"    API error: {e}")

    if not known_ids:
        print("    Falling back to DB query for fotmob IDs...")
        with engine.connect() as conn:
            known_ids = [
                row[0]
                for row in conn.execute(
                    text("""
                        SELECT DISTINCT m.fotmob_match_id
                        FROM public.matches m
                        WHERE m.tournament ILIKE '%world cup%'
                          AND m.date_utc >= '2026-06-11'
                          AND m.fotmob_match_id IS NOT NULL
                        ORDER BY m.fotmob_match_id
                    """)
                ).fetchall()
            ]

    # Filter to knockout matches only
    print("    Filtering to knockout matches...")
    with engine.connect() as conn:
        knockout_fotmob_ids = {
            row[0]
            for row in conn.execute(
                text("""
                    SELECT DISTINCT m.fotmob_match_id
                    FROM public.matches m
                    JOIN clean_wc_fixtures f ON m.match_id::text = f.match_id
                    WHERE f.is_knockout = true
                      AND m.fotmob_match_id IS NOT NULL
                """)
            ).fetchall()
        }
    known_ids = [fid for fid in known_ids if str(fid) in knockout_fotmob_ids]
    print(f"    Knockout matches to check: {len(known_ids)}")

    total = 0
    new = 0

    for fotmob_id in known_ids:
        fid = str(fotmob_id)
        if fid in existing:
            print(f"  [{total + 1}/{len(known_ids)}] Skipping {fid} (already exists)")
            total += 1
            continue

        print(
            f"  [{total + 1}/{len(known_ids)}] Fetching {fid}...", end=" ", flush=True
        )
        try:
            row = parse_match_data(fotmob_id)
            if row:
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            INSERT INTO public.wcmatches_richstat_fotmob
                            (fotmob_match_id, match_id, match_date, home_team, away_team,
                             home_score, away_score, result_1x2, btts, total_goals,
                             match_outcome, aet_home_score, aet_away_score,
                             penalties_home_score, penalties_away_score,
                             aet_xg_home, aet_xg_away,
                             aet_shots_home, aet_shots_away,
                             aet_shots_ontarget_home, aet_shots_ontarget_away,
                             possession_home, possession_away, xg_home, xg_away,
                             xgot_home, xgot_away, shots_home, shots_away,
                             shots_ontarget_home, shots_ontarget_away,
                             shots_offtarget_home, shots_offtarget_away,
                             blocked_shots_home, blocked_shots_away,
                             corners_home, corners_away,
                             yellow_cards_home, yellow_cards_away,
                             fouls_home, fouls_away,
                             passes_accurate_home, passes_accurate_away,
                             passes_total_home, passes_total_away,
                             tackles_home, tackles_away,
                             interceptions_home, interceptions_away,
                             clearances_home, clearances_away,
                             saves_home, saves_away,
                             duels_won_home, duels_won_away,
                             aerials_won_home, aerials_won_away,
                             dribbles_successful_home, dribbles_successful_away,
                             big_chances_home, big_chances_away,
                             big_chances_missed_home, big_chances_missed_away,
                             touches_opp_box_home, touches_opp_box_away,
                             offsides_home, offsides_away,
                             possession_ht_home, possession_ht_away,
                             xg_firsthalf_home, xg_firsthalf_away,
                             xg_secondhalf_home, xg_secondhalf_away,
                             shots_firsthalf_home, shots_firsthalf_away,
                             shots_secondhalf_home, shots_secondhalf_away,
                             raw_response, scraped_at)
                            VALUES (:fotmob_match_id, :match_id, :match_date,
                             :home_team, :away_team,
                             :home_score, :away_score, :result_1x2, :btts, :total_goals,
                             :match_outcome, :aet_home_score, :aet_away_score,
                             :penalties_home_score, :penalties_away_score,
                             :aet_xg_home, :aet_xg_away,
                             :aet_shots_home, :aet_shots_away,
                             :aet_shots_ontarget_home, :aet_shots_ontarget_away,
                             :possession_home, :possession_away, :xg_home, :xg_away,
                             :xgot_home, :xgot_away, :shots_home, :shots_away,
                             :shots_ontarget_home, :shots_ontarget_away,
                             :shots_offtarget_home, :shots_offtarget_away,
                             :blocked_shots_home, :blocked_shots_away,
                             :corners_home, :corners_away,
                             :yellow_cards_home, :yellow_cards_away,
                             :fouls_home, :fouls_away,
                             :passes_accurate_home, :passes_accurate_away,
                             :passes_total_home, :passes_total_away,
                             :tackles_home, :tackles_away,
                             :interceptions_home, :interceptions_away,
                             :clearances_home, :clearances_away,
                             :saves_home, :saves_away,
                             :duels_won_home, :duels_won_away,
                             :aerials_won_home, :aerials_won_away,
                             :dribbles_successful_home, :dribbles_successful_away,
                             :big_chances_home, :big_chances_away,
                             :big_chances_missed_home, :big_chances_missed_away,
                             :touches_opp_box_home, :touches_opp_box_away,
                             :offsides_home, :offsides_away,
                             :possession_ht_home, :possession_ht_away,
                             :xg_firsthalf_home, :xg_firsthalf_away,
                             :xg_secondhalf_home, :xg_secondhalf_away,
                             :shots_firsthalf_home, :shots_firsthalf_away,
                             :shots_secondhalf_home, :shots_secondhalf_away,
                             CAST(:raw_response AS jsonb), :scraped_at)
                            ON CONFLICT (fotmob_match_id) DO NOTHING
                        """),
                        row,
                    )
                new += 1
                outcome = row.get("match_outcome", "regular")
                outcome_tag = f" [{outcome}]" if outcome != "regular" else ""
                print(
                    f"OK ({row['home_team']} {row['home_score']}-{row['away_score']} {row['away_team']}{outcome_tag})"
                )

                # Update clean_wc_fixtures in Supabase with outcome data
                if supabase:
                    match_id = row.get("match_id")
                    if not match_id:
                        with engine.connect() as conn:
                            result = conn.execute(
                                text(
                                    "SELECT match_id FROM public.matches WHERE fotmob_match_id = :fid"
                                ),
                                {"fid": fid},
                            ).fetchone()
                            match_id = result[0] if result else None
                    if match_id:
                        update_data = {
                            "match_outcome": outcome,
                            "aet_home_score": row.get("aet_home_score"),
                            "aet_away_score": row.get("aet_away_score"),
                            "penalties_home_score": row.get("penalties_home_score"),
                            "penalties_away_score": row.get("penalties_away_score"),
                            "aet_home_xg": row.get("aet_xg_home"),
                            "aet_away_xg": row.get("aet_xg_away"),
                        }
                        update_data = {
                            k: v for k, v in update_data.items() if v is not None
                        }
                        try:
                            supabase.table("clean_wc_fixtures").update(update_data).eq(
                                "match_id", match_id
                            ).execute()
                        except Exception as e:
                            print(f"      Supabase update error: {e}")
            else:
                print("Not finished or no data")
                break
        except Exception as e:
            print(f"ERROR: {e}")

        total += 1
        time.sleep(0.3)

    print(f"\nDone. Scraped {new} new knockout matches (total checked: {total})")


if __name__ == "__main__":
    main()
