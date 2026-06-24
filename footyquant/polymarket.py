"""Polymarket API client — Gamma endpoints for WC 2026 data.

No auth required for read endpoints.
Rate limit: max 10 req/sec, 0.1s delay between calls.
Supports SOCKS5 proxy (Tor) via POLYMARKET_PROXY / TOR_PROXY env var.

Key findings from API exploration:
- WC sport slug: "fifwc" (id=174), tag_id=102232, series=11433
- Match events: GET /events?tag_id=102232&limit=100&active=true
- Each match event has 3 binary markets (home win, draw, away win) = decomposed 1X2
- Only 1X2 exists for WC matches (no O/U or BTTS)
- Market fields: outcomePrices, volume, bestBid, bestAsk, spread, clobTokenIds
- API returns max 100 events per request — paginate with offset
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests

from .clean_odds import normalize_market_team_name

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

WC_TAG_ID = "102232"

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


def get_wc_events(
    active: bool = True,
    closed: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Fetch WC events filtered by tag_id=102232."""
    params = {
        "tag_id": WC_TAG_ID,
        "limit": limit,
        "offset": offset,
        "active": str(active).lower(),
        "closed": str(closed).lower(),
    }
    return _get(GAMMA_BASE, "/events", params)


def get_all_wc_events(active: bool = True, closed: bool = False) -> list[dict]:
    """Paginate through all WC events (100 per page)."""
    all_events = []
    offset = 0
    while True:
        batch = get_wc_events(active=active, closed=closed, limit=100, offset=offset)
        if not batch:
            break
        all_events.extend(batch)
        if len(batch) < 100:
            break
        offset += 100
    return all_events


def get_event(event_id: int) -> dict:
    return _get(GAMMA_BASE, f"/events/{event_id}")


def get_markets(event_id: int | None = None, limit: int = 200) -> list[dict]:
    params = {"limit": limit}
    if event_id:
        params["event_id"] = event_id
    return _get(GAMMA_BASE, "/markets", params)


def get_price(token_id: str) -> dict:
    return _get(CLOB_BASE, "/price", {"token_id": token_id})


def get_price_history(market_id: str, interval: str = "max") -> list[dict]:
    return _get(
        CLOB_BASE, "/prices-history", {"market": market_id, "interval": interval}
    )


def get_orderbook(token_id: str) -> dict:
    return _get(CLOB_BASE, "/book", {"token_id": token_id})


def parse_match_markets(event: dict) -> list[dict]:
    """Parse a Polymarket match event into 1X2 snapshot rows.

    Each match event has 3 binary markets:
    - "Will {home} win on {date}?" → P(home)
    - "Will {home} vs {away} end in a draw?" → P(draw)
    - "Will {away} win on {date}?" → P(away)
    """
    markets = event.get("markets", [])
    if not markets:
        return []

    snapshots = []
    for m in markets:
        question = (m.get("question") or "").lower()

        outcomes_raw = m.get("outcomes", "[]")
        prices_raw = m.get("outcomePrices", "[]")
        if isinstance(outcomes_raw, str):
            outcomes_raw = json.loads(outcomes_raw)
        if isinstance(prices_raw, str):
            prices_raw = json.loads(prices_raw)

        if not outcomes_raw or not prices_raw:
            continue

        outcome_label = outcomes_raw[0].lower() if outcomes_raw else "yes"
        try:
            price = float(prices_raw[0])
        except (ValueError, TypeError, IndexError):
            continue
        if price <= 0 or price >= 1:
            continue

        if "draw" in question:
            side = "draw"
            market_type = "1x2"
        elif "win" in question:
            market_type = "1x2"
            title = event.get("title", "")
            parts = re.split(r"\s+vs\.?\s+", title, maxsplit=1)
            if len(parts) == 2:
                home_team, away_team = (
                    parts[0].strip().lower(),
                    parts[1].strip().lower(),
                )
                q = question
                if home_team in q:
                    side = "home"
                elif away_team in q:
                    side = "away"
                else:
                    home_norm = normalize_market_team_name(home_team)
                    away_norm = normalize_market_team_name(away_team)
                    if home_norm in q or any(a in q for a in [home_norm, home_team]):
                        side = "home"
                    elif away_norm in q or any(a in q for a in [away_norm, away_team]):
                        side = "away"
                    else:
                        continue
            else:
                continue
        else:
            continue

        if market_type != "1x2":
            continue

        volume = m.get("volume")
        if volume:
            try:
                volume = float(volume)
            except (ValueError, TypeError):
                volume = None

        best_bid = m.get("bestBid")
        best_ask = m.get("bestAsk")
        spread = m.get("spread")
        try:
            best_bid = float(best_bid) if best_bid is not None else None
        except (ValueError, TypeError):
            best_bid = None
        try:
            best_ask = float(best_ask) if best_ask is not None else None
        except (ValueError, TypeError):
            best_ask = None
        try:
            spread = float(spread) if spread is not None else None
        except (ValueError, TypeError):
            spread = None

        snapshots.append(
            {
                "source": "polymarket",
                "market_type": market_type,
                "outcome": side,
                "line": None,
                "price": price,
                "volume": volume,
                "liquidity": None,
                "bid_ask_spread": spread,
                "market_id": str(m.get("conditionId", "")),
                "captured_at_utc": datetime.now(timezone.utc),
                "raw_response": m,
                "best_bid": best_bid,
                "best_ask": best_ask,
            }
        )

    return snapshots


def classify_event(event: dict) -> str | None:
    """Classify an event. Only main 1X2 match events return 'match'.

    Main match events have titles like 'Netherlands vs. Sweden' — no suffix.
    Variants like 'Netherlands vs. Sweden - Halftime Result' or
    'Netherlands vs. Sweden - Exact Score' are filtered out.
    """
    title = event.get("title", "")
    if " vs " not in title.lower() and " vs." not in title.lower():
        return "tournament"

    parts = re.split(r"\s+vs\.?\s+", title, maxsplit=1)
    if len(parts) != 2:
        return "tournament"

    away_part = parts[1]
    if re.search(r"\s+[-:]\s+", away_part):
        return "variant"

    if "halftime" in title.lower() or "exact score" in title.lower():
        return "variant"

    return "match"


def parse_match_title(title: str) -> tuple[str, str] | None:
    """Extract (home, away) from a match title like 'Netherlands vs. Sweden'."""
    parts = re.split(r"\s+vs\.?\s+", title, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None
