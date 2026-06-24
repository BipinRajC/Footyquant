"""Helpers for building model-safe market odds rows."""

import json
import re
import unicodedata
from collections.abc import Callable, Iterable
from typing import Any


CLEAN_MARKET_ODDS_SOURCES = {
    "kalshi",
    "polymarket",
    "xlsx_bet365",
    "xlsx_betfair",
    "xlsx_max",
    "xlsx_avg",
}


def chunked(items: list[Any], size: int):
    """Yield list chunks of at most size items."""
    if size <= 0:
        raise ValueError("size must be positive")
    for start in range(0, len(items), size):
        yield items[start : start + size]


def latest_price_before_kickoff(
    history: Iterable[dict[str, Any]], kickoff_ts: int
) -> float | None:
    """Return the latest valid price at or before kickoff."""
    best_t = None
    best_price = None
    for point in history:
        t = point.get("t")
        price = point.get("p")
        if t is None or price is None:
            continue
        try:
            t = int(t)
            price = float(price)
        except (TypeError, ValueError):
            continue
        if t > kickoff_ts or not 0 < price < 1:
            continue
        if best_t is None or t > best_t:
            best_t = t
            best_price = price
    return best_price


def latest_kalshi_price_before_kickoff(
    candlesticks: Iterable[dict[str, Any]], kickoff_ts: int
) -> float | None:
    """Return the latest Kalshi candle close at or before kickoff."""
    best_t = None
    best_price = None
    for candle in candlesticks:
        t = candle.get("end_period_ts")
        price = (candle.get("price") or {}).get("close_dollars")
        if t is None or price is None:
            continue
        try:
            t = int(t)
            price = float(price)
        except (TypeError, ValueError):
            continue
        if t > kickoff_ts or not 0 < price < 1:
            continue
        if best_t is None or t > best_t:
            best_t = t
            best_price = price
    return best_price


def build_polymarket_recovery_rows(
    snapshots: Iterable[dict[str, Any]],
    kickoff_ts: int,
    get_history: Callable[[str], Iterable[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Recover one pre-kickoff 1X2 price per Polymarket outcome snapshot."""
    rows = []
    for snapshot in snapshots:
        outcome = snapshot.get("outcome")
        if outcome not in {"home", "draw", "away"}:
            continue

        token_id = _yes_token_id(snapshot.get("raw_response") or {})
        if not token_id:
            continue

        price = latest_price_before_kickoff(get_history(token_id), kickoff_ts)
        if price is None:
            continue

        rows.append(
            {
                "match_id": str(snapshot["wc_match_id"]),
                "source": "polymarket",
                "market_type": "1x2",
                "outcome": outcome,
                "probability": price,
                "quality": "recovered_prekickoff",
                "source_market_id": str(snapshot.get("market_id") or ""),
                "source_token_id": token_id,
            }
        )
    return rows


def polymarket_outcome_from_question(
    question: str, home_team: str, away_team: str
) -> str | None:
    """Map a Polymarket binary question to home/draw/away."""
    q = _normalize_name(question)
    home = _normalize_name(home_team)
    away = _normalize_name(away_team)
    if "draw" in q:
        return "draw"
    if "win" not in q:
        return None
    if home and home in q:
        return "home"
    if away and away in q:
        return "away"
    return None


def normalize_market_team_name(value: str) -> str:
    return _normalize_name(value)


def is_kalshi_1x2_usable(
    *,
    match_state: str,
    result_1x2: str | None,
    home_prob: float | None,
    draw_prob: float | None,
    away_prob: float | None,
) -> bool:
    """Reject Kalshi 1X2 rows that are settled-result leakage."""
    if home_prob is None or draw_prob is None or away_prob is None:
        return False
    if not all(0 < p < 1 for p in (home_prob, draw_prob, away_prob)):
        return False

    if match_state != "played" or result_1x2 is None:
        return True

    result_prob = {
        "H": home_prob,
        "D": draw_prob,
        "A": away_prob,
    }.get(result_1x2)
    return not (result_prob is not None and result_prob >= 0.98)


def _yes_token_id(raw_response: dict[str, Any]) -> str | None:
    token_ids = raw_response.get("clobTokenIds")
    if isinstance(token_ids, str):
        try:
            token_ids = json.loads(token_ids)
        except json.JSONDecodeError:
            return None
    if not isinstance(token_ids, list) or not token_ids:
        return None
    return str(token_ids[0])


def _normalize_name(value: str) -> str:
    value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    value = re.sub(r"[^a-z0-9 ]+", " ", value.lower()).strip()
    value = re.sub(r"\s+", " ", value)
    aliases = {
        "bosnia herzegovina": "bosnia and herzegovina",
        "bosnia herz egovina": "bosnia and herzegovina",
        "cote d ivoire": "ivory coast",
        "czech republic": "czechia",
        "d r congo": "dr congo",
        "turkey": "turkiye",
        "united states": "usa",
        "dr congo": "dr congo",
        "congo dr": "dr congo",
    }
    return aliases.get(value, value)
