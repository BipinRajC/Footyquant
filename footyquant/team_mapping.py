"""Cross-source team ID mapping for WC 2026 teams.

Populates teams.polymarket_slug, teams.kalshi_ticker, teams.fbref_team_id,
and teams.confederation from known mappings and API discovery.
"""

import requests
from sqlalchemy import text

from .db import get_engine

WC_TEAMS = [
    "Algeria",
    "Argentina",
    "Australia",
    "Austria",
    "Belgium",
    "Bosnia and Herzegovina",
    "Brazil",
    "Canada",
    "Cape Verde",
    "Colombia",
    "Congo DR",
    "Croatia",
    "Curacao",
    "Czechia",
    "Ecuador",
    "Egypt",
    "England",
    "France",
    "Germany",
    "Ghana",
    "Haiti",
    "IR Iran",
    "Iraq",
    "Ivory Coast",
    "Japan",
    "Jordan",
    "Korea Republic",
    "Mexico",
    "Morocco",
    "Netherlands",
    "New Zealand",
    "Norway",
    "Panama",
    "Paraguay",
    "Portugal",
    "Qatar",
    "Saudi Arabia",
    "Scotland",
    "Senegal",
    "South Africa",
    "Spain",
    "Sweden",
    "Switzerland",
    "Tunisia",
    "Turkiye",
    "Uruguay",
    "USA",
    "Uzbekistan",
]

CONFEDERATIONS = {
    "Algeria": "CAF",
    "Argentina": "CONMEBOL",
    "Australia": "AFC",
    "Austria": "UEFA",
    "Belgium": "UEFA",
    "Bosnia and Herzegovina": "UEFA",
    "Brazil": "CONMEBOL",
    "Canada": "CONCACAF",
    "Cape Verde": "CAF",
    "Colombia": "CONMEBOL",
    "Congo DR": "CAF",
    "Croatia": "UEFA",
    "Curacao": "CONCACAF",
    "Czechia": "UEFA",
    "Ecuador": "CONMEBOL",
    "Egypt": "CAF",
    "England": "UEFA",
    "France": "UEFA",
    "Germany": "UEFA",
    "Ghana": "CAF",
    "Haiti": "CONCACAF",
    "IR Iran": "AFC",
    "Iraq": "AFC",
    "Ivory Coast": "CAF",
    "Japan": "AFC",
    "Jordan": "AFC",
    "Korea Republic": "AFC",
    "Mexico": "CONCACAF",
    "Morocco": "CAF",
    "Netherlands": "UEFA",
    "New Zealand": "OFC",
    "Norway": "UEFA",
    "Panama": "CONCACAF",
    "Paraguay": "CONMEBOL",
    "Portugal": "UEFA",
    "Qatar": "AFC",
    "Saudi Arabia": "AFC",
    "Scotland": "UEFA",
    "Senegal": "CAF",
    "South Africa": "CAF",
    "Spain": "UEFA",
    "Sweden": "UEFA",
    "Switzerland": "UEFA",
    "Tunisia": "CAF",
    "Turkiye": "UEFA",
    "Uruguay": "CONMEBOL",
    "USA": "CONCACAF",
    "Uzbekistan": "AFC",
}

POLYMARKET_SLUGS = {
    "Algeria": "algeria",
    "Argentina": "argentina",
    "Australia": "australia",
    "Austria": "austria",
    "Belgium": "belgium",
    "Bosnia and Herzegovina": "bosnia-and-herzegovina",
    "Brazil": "brazil",
    "Canada": "canada",
    "Cape Verde": "cape-verde",
    "Colombia": "colombia",
    "Congo DR": "congo-dr",
    "Croatia": "croatia",
    "Curacao": "curacao",
    "Czechia": "czechia",
    "Ecuador": "ecuador",
    "Egypt": "egypt",
    "England": "england",
    "France": "france",
    "Germany": "germany",
    "Ghana": "ghana",
    "Haiti": "haiti",
    "IR Iran": "iran",
    "Iraq": "iraq",
    "Ivory Coast": "ivory-coast",
    "Japan": "japan",
    "Jordan": "jordan",
    "Korea Republic": "south-korea",
    "Mexico": "mexico",
    "Morocco": "morocco",
    "Netherlands": "netherlands",
    "New Zealand": "new-zealand",
    "Norway": "norway",
    "Panama": "panama",
    "Paraguay": "paraguay",
    "Portugal": "portugal",
    "Qatar": "qatar",
    "Saudi Arabia": "saudi-arabia",
    "Scotland": "scotland",
    "Senegal": "senegal",
    "South Africa": "south-africa",
    "Spain": "spain",
    "Sweden": "sweden",
    "Switzerland": "switzerland",
    "Tunisia": "tunisia",
    "Turkiye": "turkiye",
    "Uruguay": "uruguay",
    "USA": "usa",
    "Uzbekistan": "uzbekistan",
}

KALSHI_TICKERS = {
    "Algeria": "ALG",
    "Argentina": "ARG",
    "Australia": "AUS",
    "Austria": "AUT",
    "Belgium": "BEL",
    "Bosnia and Herzegovina": "BIH",
    "Brazil": "BRA",
    "Canada": "CAN",
    "Cape Verde": "CPV",
    "Colombia": "COL",
    "Congo DR": "COD",
    "Croatia": "CRO",
    "Curacao": "CUR",
    "Czechia": "CZE",
    "Ecuador": "ECU",
    "Egypt": "EGY",
    "England": "ENG",
    "France": "FRA",
    "Germany": "GER",
    "Ghana": "GHA",
    "Haiti": "HAI",
    "IR Iran": "IRN",
    "Iraq": "IRQ",
    "Ivory Coast": "CIV",
    "Japan": "JPN",
    "Jordan": "JOR",
    "Korea Republic": "KOR",
    "Mexico": "MEX",
    "Morocco": "MAR",
    "Netherlands": "NED",
    "New Zealand": "NZL",
    "Norway": "NOR",
    "Panama": "PAN",
    "Paraguay": "PAR",
    "Portugal": "POR",
    "Qatar": "QAT",
    "Saudi Arabia": "KSA",
    "Scotland": "SCO",
    "Senegal": "SEN",
    "South Africa": "RSA",
    "Spain": "ESP",
    "Sweden": "SWE",
    "Switzerland": "SUI",
    "Tunisia": "TUN",
    "Turkiye": "TUR",
    "Uruguay": "URU",
    "USA": "USA",
    "Uzbekistan": "UZB",
}

FBREF_IDS = {
    "Algeria": "algeria",
    "Argentina": "argentina",
    "Australia": "australia",
    "Austria": "austria",
    "Belgium": "belgium",
    "Bosnia and Herzegovina": "bosnia-herzegovina",
    "Brazil": "brazil",
    "Canada": "canada",
    "Cape Verde": "cape-verde",
    "Colombia": "colombia",
    "Congo DR": "congo-dr",
    "Croatia": "croatia",
    "Curacao": "curacao",
    "Czechia": "czech-republic",
    "Ecuador": "ecuador",
    "Egypt": "egypt",
    "England": "england",
    "France": "france",
    "Germany": "germany",
    "Ghana": "ghana",
    "Haiti": "haiti",
    "IR Iran": "iran",
    "Iraq": "iraq",
    "Ivory Coast": "cote-d-ivoire",
    "Japan": "japan",
    "Jordan": "jordan",
    "Korea Republic": "south-korea",
    "Mexico": "mexico",
    "Morocco": "morocco",
    "Netherlands": "netherlands",
    "New Zealand": "new-zealand",
    "Norway": "norway",
    "Panama": "panama",
    "Paraguay": "paraguay",
    "Portugal": "portugal",
    "Qatar": "qatar",
    "Saudi Arabia": "saudi-arabia",
    "Scotland": "scotland",
    "Senegal": "senegal",
    "South Africa": "south-africa",
    "Spain": "spain",
    "Sweden": "sweden",
    "Switzerland": "switzerland",
    "Tunisia": "tunisia",
    "Turkiye": "turkey",
    "Uruguay": "uruguay",
    "USA": "united-states",
    "Uzbekistan": "uzbekistan",
}


def discover_polymarket_teams():
    """Try to discover team slugs from Polymarket API. Falls back to static mapping."""
    try:
        resp = requests.get(
            "https://gamma-api.polymarket.com/teams?sport=fifwc",
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code == 200:
            teams = resp.json()
            slugs = {}
            for t in teams:
                name = t.get("name", "")
                slug = t.get("slug", "")
                if name and slug:
                    slugs[name.lower()] = slug
            return slugs
    except Exception:
        pass
    return {}


def discover_kalshi_teams():
    """Try to discover team tickers from Kalshi API. Falls back to static mapping."""
    try:
        resp = requests.get(
            "https://external-api.kalshi.com/trade-api/v2/series?category=sports",
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            series_list = data.get("series", [])
            wc_series = [
                s
                for s in series_list
                if "worldcup" in s.get("series_title", "").lower()
            ]
            return wc_series
    except Exception:
        pass
    return []


def apply_mappings(engine=None):
    if engine is None:
        engine = get_engine()

    updated = 0
    with engine.begin() as conn:
        for name in WC_TEAMS:
            tid = conn.execute(
                text("SELECT canonical_id FROM teams WHERE name = :n"),
                {"n": name},
            ).fetchone()
            if not tid:
                print(f"  SKIP {name}: not found in teams table")
                continue

            tid = tid[0]
            updates = {}
            if name in CONFEDERATIONS:
                updates["confederation"] = CONFEDERATIONS[name]
            if name in POLYMARKET_SLUGS:
                updates["polymarket_slug"] = POLYMARKET_SLUGS[name]
            if name in KALSHI_TICKERS:
                updates["kalshi_ticker"] = KALSHI_TICKERS[name]
            if name in FBREF_IDS:
                updates["fbref_team_id"] = FBREF_IDS[name]

            if updates:
                set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
                updates["tid"] = tid
                conn.execute(
                    text(f"UPDATE teams SET {set_clauses} WHERE canonical_id = :tid"),
                    updates,
                )
                updated += 1

    print(f"Updated {updated}/{len(WC_TEAMS)} WC teams with cross-source IDs")
    return updated


def main():
    print("=== Team Mapping ===")
    apply_mappings()

    print("\nDone.")


if __name__ == "__main__":
    main()
