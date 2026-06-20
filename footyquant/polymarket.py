"""Polymarket API client — Gamma + CLOB endpoints for WC 2026 data.

No auth required for read endpoints.
Rate limit: max 10 req/sec, 0.1s delay between calls.
Supports SOCKS5 proxy (Tor) via POLYMARKET_PROXY env var.
"""

import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

_raw_proxy = os.environ.get("POLYMARKET_PROXY") or os.environ.get("TOR_PROXY")
PROXY = _raw_proxy.replace("socks5://", "socks5h://") if _raw_proxy else None


class PolymarketError(Exception):
    pass


def _session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    if PROXY:
        s.proxies.update({"http": PROXY, "https": PROXY})
    return s


def _get(base: str, path: str, params: dict | None = None, delay: float = 0.1) -> Any:
    time.sleep(delay)
    url = f"{base}{path}"
    sess = _session()
    resp = sess.get(url, params=params, timeout=30)
    if resp.status_code != 200:
        raise PolymarketError(f"HTTP {resp.status_code} from {url}: {resp.text[:200]}")
    return resp.json()


def search_events(query: str) -> dict:
    """Search Polymarket events. Uses 'q' parameter (not 'query')."""
    return _get(GAMMA_BASE, "/public-search", {"q": query})


def get_event(event_id: int) -> dict:
    return _get(GAMMA_BASE, f"/events/{event_id}")


def get_markets(event_id: int | None = None, limit: int = 200) -> list[dict]:
    params = {"limit": limit}
    if event_id:
        params["event_id"] = event_id
    return _get(GAMMA_BASE, "/markets", params)


def get_market(market_id: int) -> dict:
    return _get(GAMMA_BASE, f"/markets/{market_id}")


def get_price(token_id: str) -> dict:
    return _get(CLOB_BASE, "/price", {"token_id": token_id})


def get_price_history(market_id: str, interval: str = "max") -> list[dict]:
    return _get(
        CLOB_BASE, "/prices-history", {"market": market_id, "interval": interval}
    )


def get_orderbook(token_id: str) -> dict:
    return _get(CLOB_BASE, "/book", {"token_id": token_id})


def get_midpoint(token_id: str) -> dict:
    return _get(CLOB_BASE, "/midpoint", {"token_id": token_id})


def compute_bid_ask_spread(orderbook: dict) -> float | None:
    bids = orderbook.get("bids", [])
    asks = orderbook.get("asks", [])
    if not bids or not asks:
        return None
    best_bid = float(bids[0].get("price", 0))
    best_ask = float(asks[0].get("price", 0))
    if best_bid <= 0 or best_ask <= 0:
        return None
    return round((best_ask - best_bid) / best_bid, 6)


def compute_liquidity(orderbook: dict) -> float | None:
    bids = orderbook.get("bids", [])
    asks = orderbook.get("asks", [])
    total = 0.0
    for side in [bids, asks]:
        for level in side[:5]:
            total += float(level.get("size", 0)) * float(level.get("price", 0))
    return round(total, 2) if total > 0 else None


def discover_wc_match_events(team_names: list[str]) -> list[dict]:
    """Discover WC match events by searching for each team."""
    seen = {}
    for team in team_names:
        try:
            data = search_events(f"{team} vs")
            for ev in data.get("events", []):
                title = ev.get("title", "")
                if " vs " not in title or "announcer" in title.lower():
                    continue
                eid = ev["id"]
                if eid not in seen:
                    seen[eid] = ev
        except PolymarketError:
            continue
    return list(seen.values())


def parse_market_snapshot(market: dict, match_id: int) -> dict | None:
    """Parse a single Polymarket binary market into a snapshot row."""
    outcomes = market.get("outcomes", [])
    raw_prices = market.get("outcomePrices", [])
    if not outcomes or not raw_prices:
        return None

    import json

    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(raw_prices, str):
        try:
            raw_prices = json.loads(raw_prices)
        except (json.JSONDecodeError, TypeError):
            return None

    question = (market.get("question") or "").lower()
    market_type = _classify_market(question)
    if not market_type:
        return None

    outcome = outcomes[0].lower() if outcomes else "yes"
    try:
        price = float(raw_prices[0]) if raw_prices else None
    except (ValueError, TypeError, IndexError):
        return None
    if price is None or price <= 0 or price >= 1:
        return None

    volume = market.get("volume")
    if volume:
        try:
            volume = float(volume)
        except (ValueError, TypeError):
            volume = None

    return {
        "match_id": match_id,
        "source": "polymarket",
        "market_type": market_type,
        "outcome": outcome,
        "line": _extract_line(question),
        "price": price,
        "volume": volume,
        "liquidity": None,
        "bid_ask_spread": None,
        "market_id": str(market.get("conditionId", "")),
        "captured_at_utc": datetime.now(timezone.utc),
        "raw_response": market,
    }


def _classify_market(question: str) -> str | None:
    if "win" in question and ("draw" in question or "tie" in question):
        return None
    if "will" in question and "win" in question:
        return "1x2"
    if "draw" in question or "tie" in question:
        return "1x2"
    if "over" in question or "under" in question:
        return "over_under"
    if "both teams" in question or "btts" in question:
        return "btts"
    if "total goals" in question:
        return "over_under"
    return None


def _extract_line(question: str) -> float | None:
    for m in re.finditer(r"(\d+\.?\d*)", question):
        val = float(m.group(1))
        if val < 100:  # skip years (2026) and dates
            return val
    return None
