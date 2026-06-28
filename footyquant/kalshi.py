"""Kalshi API client — public read endpoints for WC 2026 data.

No auth required for read endpoints.
Rate limit: max 5 req/sec, 0.2s delay between calls.
Supports SOCKS5 proxy (Tor) via TOR_PROXY env var.

Key findings from API exploration:
- WC series tickers:
  KXWCGAME  = 1X2 match winner (3 markets: home, away, tie)
  KXWCBTTS  = Both teams to score (1 binary market)
  KXWCTOTAL = Over/under total goals (6 markets: 0.5, 1.5, 2.5, 3.5, 4.5, 5.5)
  KXWCSPREAD = Spread (4 markets: each team wins by 1.5+, 2.5+)
- Event ticker pattern: KXWCGAME-26JUN20NEDSWE (date + 3-letter team codes)
- Market price fields: yes_bid_dollars, yes_ask_dollars, last_price_dollars
- Volume: volume_fp, volume_24h_fp
- Liquidity: liquidity_dollars
- Market subtitle indicates which team (for 1X2) or line (for totals)
"""

import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests

KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

WC_SERIES = {
    "1x2": "KXWCGAME",
    "btts": "KXWCBTTS",
    "over_under": "KXWCTOTAL",
    "spread": "KXWCSPREAD",
}

_raw_proxy = os.environ.get("KALSHI_PROXY") or os.environ.get("TOR_PROXY")
PROXY = _raw_proxy.replace("socks5://", "socks5h://") if _raw_proxy else None


class KalshiError(Exception):
    pass


def _session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    if PROXY:
        s.proxies.update({"http": PROXY, "https": PROXY})
    return s


def _get(path: str, params: dict | None = None, delay: float = 0.2) -> Any:
    time.sleep(delay)
    url = f"{KALSHI_BASE}{path}"
    sess = _session()
    resp = sess.get(url, params=params, timeout=30)
    if resp.status_code != 200:
        raise KalshiError(f"HTTP {resp.status_code} from {url}: {resp.text[:200]}")
    return resp.json()


def get_events(
    series_ticker: str, status: str = "open", limit: int = 100
) -> list[dict]:
    """Get events for a series ticker."""
    params = {"series_ticker": series_ticker, "status": status, "limit": limit}
    data = _get("/events", params)
    return data.get("events", [])


def get_all_events(series_ticker: str, status: str = "open") -> list[dict]:
    """Paginate through all events for a series."""
    all_events = []
    cursor = None
    while True:
        params = {"series_ticker": series_ticker, "status": status, "limit": 100}
        if cursor:
            params["cursor"] = cursor
        data = _get("/events", params)
        events = data.get("events", [])
        all_events.extend(events)
        cursor = data.get("cursor")
        if not cursor or not events:
            break
    return all_events


def get_markets(event_ticker: str, limit: int = 50) -> list[dict]:
    """Get all markets for an event."""
    params = {"event_ticker": event_ticker, "limit": limit}
    data = _get("/markets", params)
    return data.get("markets", [])


def get_market(ticker: str) -> dict:
    """Get a single market by ticker."""
    data = _get(f"/markets/{ticker}")
    return data.get("market", data)


def parse_match_title(title: str) -> tuple[str, str] | None:
    """Extract (home, away) from 'Netherlands vs Sweden: Spread' or 'Netherlands vs Sweden'."""
    clean = re.sub(
        r":\s*(Spread|BTTS|Total Goals|Winner\??|Regulation Time Moneyline|Moneyline)$",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()
    parts = re.split(r"\s+vs\.?\s+", clean, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None


def parse_1x2_markets(event: dict, markets: list[dict]) -> list[dict]:
    """Parse Kalshi 1X2 markets into snapshot rows.

    3 markets per event: -TIE, -{HOME_CODE}, -{AWAY_CODE}
    Each is binary Yes/No with yes_price = P(outcome).
    """
    snapshots = []
    title = event.get("title", "")
    parsed = parse_match_title(title)
    if not parsed:
        return snapshots

    home_team, away_team = parsed

    for m in markets:
        ticker = m.get("ticker", "")
        subtitle = (m.get("yes_sub_title") or m.get("subtitle") or "").strip()

        if "-TIE" in ticker or subtitle.lower() == "tie":
            side = "draw"
        elif "-TIE" not in ticker:
            if (
                home_team.lower() in subtitle.lower()
                or subtitle.lower() in home_team.lower()
            ):
                side = "home"
            elif (
                away_team.lower() in subtitle.lower()
                or subtitle.lower() in away_team.lower()
            ):
                side = "away"
            else:
                continue
        else:
            continue

        price = _extract_price(m)
        if price is None:
            continue

        snapshots.append(
            {
                "source": "kalshi",
                "market_type": "1x2",
                "outcome": side,
                "line": None,
                "price": price,
                "volume": _safe_float(m.get("volume_fp")),
                "liquidity": _safe_float(m.get("liquidity_dollars")),
                "bid_ask_spread": _compute_spread(m),
                "market_id": ticker,
                "captured_at_utc": datetime.now(timezone.utc),
                "raw_response": m,
            }
        )

    return snapshots


def parse_btts_markets(event: dict, markets: list[dict]) -> list[dict]:
    """Parse Kalshi BTTS market into snapshot row."""
    snapshots = []
    for m in markets:
        price = _extract_price(m)
        if price is None:
            continue

        snapshots.append(
            {
                "source": "kalshi",
                "market_type": "btts",
                "outcome": "yes",
                "line": None,
                "price": price,
                "volume": _safe_float(m.get("volume_fp")),
                "liquidity": _safe_float(m.get("liquidity_dollars")),
                "bid_ask_spread": _compute_spread(m),
                "market_id": m.get("ticker", ""),
                "captured_at_utc": datetime.now(timezone.utc),
                "raw_response": m,
            }
        )

    return snapshots


def parse_total_markets(event: dict, markets: list[dict]) -> list[dict]:
    """Parse Kalshi O/U total goals markets into snapshot rows.

    Multiple markets per event: over 0.5, 1.5, 2.5, 3.5, 4.5, 5.5
    """
    snapshots = []
    for m in markets:
        title = m.get("title", "")
        match = re.search(r"over\s+(\d+\.?\d*)", title, re.IGNORECASE)
        if not match:
            continue
        line = float(match.group(1))

        price = _extract_price(m)
        if price is None:
            continue

        snapshots.append(
            {
                "source": "kalshi",
                "market_type": "over_under",
                "outcome": "over",
                "line": line,
                "price": price,
                "volume": _safe_float(m.get("volume_fp")),
                "liquidity": _safe_float(m.get("liquidity_dollars")),
                "bid_ask_spread": _compute_spread(m),
                "market_id": m.get("ticker", ""),
                "captured_at_utc": datetime.now(timezone.utc),
                "raw_response": m,
            }
        )

    return snapshots


def parse_spread_markets(event: dict, markets: list[dict]) -> list[dict]:
    """Parse Kalshi spread markets into snapshot rows.

    Markets like 'Netherlands wins by more than 1.5 goals?'
    """
    snapshots = []
    title = event.get("title", "")
    parsed = parse_match_title(title)
    if not parsed:
        return snapshots
    home_team, away_team = parsed

    for m in markets:
        mtitle = m.get("title", "")
        match = re.search(r"wins by more than (\d+\.?\d*)", mtitle, re.IGNORECASE)
        if not match:
            continue
        line = float(match.group(1))

        if home_team.lower() in mtitle.lower():
            side = "home"
        elif away_team.lower() in mtitle.lower():
            side = "away"
        else:
            continue

        price = _extract_price(m)
        if price is None:
            continue

        snapshots.append(
            {
                "source": "kalshi",
                "market_type": "spread",
                "outcome": side,
                "line": line,
                "price": price,
                "volume": _safe_float(m.get("volume_fp")),
                "liquidity": _safe_float(m.get("liquidity_dollars")),
                "bid_ask_spread": _compute_spread(m),
                "market_id": m.get("ticker", ""),
                "captured_at_utc": datetime.now(timezone.utc),
                "raw_response": m,
            }
        )

    return snapshots


def _extract_price(m: dict) -> float | None:
    """Extract implied probability from market data.

    Priority: last_price_dollars > midpoint of bid/ask > yes_ask_dollars
    """
    last = _safe_float(m.get("last_price_dollars"))
    if last is not None and 0 < last < 1:
        return round(last, 6)

    yes_bid = _safe_float(m.get("yes_bid_dollars"))
    yes_ask = _safe_float(m.get("yes_ask_dollars"))
    if (
        yes_bid is not None
        and yes_ask is not None
        and 0 < yes_bid < 1
        and 0 < yes_ask < 1
    ):
        return round((yes_bid + yes_ask) / 2, 6)

    if yes_ask is not None and 0 < yes_ask < 1:
        return round(yes_ask, 6)

    return None


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f != 0 or "volume" not in str(type(v)) else None
    except (ValueError, TypeError):
        return None


def _compute_spread(m: dict) -> float | None:
    yes_bid = _safe_float(m.get("yes_bid_dollars"))
    yes_ask = _safe_float(m.get("yes_ask_dollars"))
    if yes_bid is not None and yes_ask is not None and yes_bid > 0:
        return round((yes_ask - yes_bid) / yes_bid, 6)
    return None
