"""OddspAPI v4 client with budget guard."""

import os
from typing import Any

import requests
from dotenv import load_dotenv

from .db import can_spend, record_call

load_dotenv()

BASE_URL = "https://api.oddspapi.io/v4"
API_KEY = os.getenv("ODDS_PAPI_API_KEY")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

SHARP_BOOKS = {"pinnacle", "betfair-ex", "smarkets", "matchbook", "sbobet"}


class OddspAPIError(Exception):
    pass


def _get(path: str, params: dict | None = None) -> Any:
    if not can_spend("oddspapi", 1):
        raise OddspAPIError("Budget exhausted")
    params = dict(params or {})
    params["apiKey"] = API_KEY
    resp = requests.get(
        f"{BASE_URL}{path}",
        params=params,
        headers={"User-Agent": UA},
        timeout=30,
    )
    if resp.status_code == 403:
        raise OddspAPIError("403 Forbidden — Cloudflare block")
    if resp.status_code != 200:
        raise OddspAPIError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    record_call("oddspapi", 1)
    return resp.json()


def get_markets() -> Any:
    return _get("/markets")


def get_bookmakers() -> Any:
    return _get("/bookmakers")


def get_fixtures(sport_id: int = 10, tournament_id: int = 16) -> Any:
    return _get("/fixtures", {"sportId": sport_id, "tournamentId": tournament_id})


def get_odds(fixture_id: str) -> Any:
    return _get("/odds", {"fixtureId": fixture_id})


def get_historical_odds(fixture_id: str, bookmakers: list[str]) -> Any:
    return _get(
        "/historical-odds",
        {"fixtureId": fixture_id, "bookmakers": ",".join(bookmakers)},
    )


def is_sharp(book_slug: str) -> bool:
    return book_slug.lower() in SHARP_BOOKS


def implied_prob(decimal_odds: float) -> float:
    return round(1.0 / decimal_odds, 6)
