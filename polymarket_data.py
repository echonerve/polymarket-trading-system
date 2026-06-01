"""
polymarket_data.py — Where market prices come from.

Two sources, same output format so the rest of the bot doesn't care which is used:

  1. LIVE  : reads REAL, PUBLIC Polymarket data from the Gamma API.
             This is read-only. It needs no login, no wallet, no private key.
             It can ONLY look at prices. It cannot place an order or move money.

  2. OFFLINE: a built-in synthetic feed. Prices wander randomly each cycle.
             Use this on a plane, behind a firewall, or to test the bot's
             plumbing without hitting the network.

A "market" is normalised into a plain dict (see normalise_market) with the few
fields the bot actually uses. We parse exactly the fields the real API returned
when this was written, so the parser matches reality, not a guess.
"""

import json
import random
import urllib.request
import urllib.parse
from datetime import datetime, timezone

GAMMA_URL = "https://gamma-api.polymarket.com/markets"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_float(value, default=0.0):
    """Convert messy API strings/None to a float without ever crashing."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_json_list(value):
    """The API stores some lists as JSON *strings*, e.g. '["Yes", "No"]'.

    This safely turns that into a real Python list. Returns [] on anything odd.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _days_until(iso_date):
    """Whole days from now until an ISO date string. Big number if unknown."""
    if not iso_date:
        return 9999
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            end = datetime.strptime(iso_date, fmt).replace(tzinfo=timezone.utc)
            return max(0, (end - datetime.now(timezone.utc)).days)
        except ValueError:
            continue
    return 9999


def normalise_market(raw):
    """Turn one raw Gamma market record into the small dict the bot uses.

    Returns None if the record is missing the essentials (e.g. no prices yet).
    """
    outcomes = _parse_json_list(raw.get("outcomes"))         # ["Yes", "No"]
    prices = _parse_json_list(raw.get("outcomePrices"))      # ["0.67", "0.33"]
    token_ids = _parse_json_list(raw.get("clobTokenIds"))    # token id strings

    # We only handle clean binary (Yes/No) markets in this sandbox.
    if len(outcomes) != 2 or len(prices) != 2:
        return None

    yes_price = _to_float(prices[0])
    no_price = _to_float(prices[1])
    if yes_price <= 0 or no_price <= 0:
        return None

    return {
        "id": str(raw.get("id", "")),
        "question": raw.get("question", "(no question)"),
        "slug": raw.get("slug", ""),
        "yes_token": token_ids[0] if len(token_ids) > 0 else "",
        "no_token": token_ids[1] if len(token_ids) > 1 else "",
        "yes_price": yes_price,                 # mid price of YES (0..1)
        "no_price": no_price,                   # mid price of NO  (0..1)
        "best_bid": _to_float(raw.get("bestBid"), yes_price),
        "best_ask": _to_float(raw.get("bestAsk"), yes_price),
        "spread": _to_float(raw.get("spread"), 0.0),
        "volume": _to_float(raw.get("volumeNum") or raw.get("volume")),
        "liquidity": _to_float(raw.get("liquidityNum") or raw.get("liquidity")),
        "volume_24hr": _to_float(raw.get("volume24hr")),
        "one_day_change": _to_float(raw.get("oneDayPriceChange")),
        "one_hour_change": _to_float(raw.get("oneHourPriceChange")),
        "days_left": _days_until(raw.get("endDateIso") or raw.get("endDate")),
        "closed": bool(raw.get("closed")),
        "accepting_orders": bool(raw.get("acceptingOrders")),
    }


# ---------------------------------------------------------------------------
# LIVE source
# ---------------------------------------------------------------------------

def fetch_live_markets(limit=40):
    """Pull the most active open markets from the public Gamma API.

    Read-only HTTP GET. No credentials. Raises on network failure so the caller
    can decide to fall back to the offline feed.
    """
    params = urllib.parse.urlencode({
        "limit": limit,
        "active": "true",
        "closed": "false",
        "order": "volume24hr",   # busiest markets first
        "ascending": "false",
    })
    req = urllib.request.Request(
        f"{GAMMA_URL}?{params}",
        headers={"User-Agent": "paper-sandbox/1.0 (read-only)"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw_list = json.loads(resp.read().decode("utf-8"))

    markets = []
    for raw in raw_list:
        m = normalise_market(raw)
        if m:
            markets.append(m)
    return markets


# ---------------------------------------------------------------------------
# OFFLINE source (synthetic, random walk)
# ---------------------------------------------------------------------------

# A fixed set of pretend markets. Prices live in module state and drift each call.
_SYNTH = [
    {"id": "sim-1", "question": "Will it rain in London tomorrow?", "yes": 0.55},
    {"id": "sim-2", "question": "Team A wins the final?",            "yes": 0.40},
    {"id": "sim-3", "question": "Bitcoin above $X by Friday?",       "yes": 0.62},
    {"id": "sim-4", "question": "Candidate Y wins the by-election?", "yes": 0.48},
    {"id": "sim-5", "question": "Film Z opens #1 this weekend?",     "yes": 0.71},
    {"id": "sim-6", "question": "Rate cut at next meeting?",         "yes": 0.33},
]


def fetch_offline_markets(limit=40):
    """Synthetic markets whose YES price random-walks a little each call."""
    out = []
    for s in _SYNTH[:limit]:
        # Nudge the price by a small random step, keep it inside (0.05, 0.95).
        s["yes"] = min(0.95, max(0.05, s["yes"] + random.uniform(-0.03, 0.03)))
        yes = round(s["yes"], 3)
        no = round(1 - yes, 3)
        spread = 0.02
        # Wide synthetic hourly swings so the demo regularly crosses the edge
        # bar and you can watch the full buy -> fee -> journal pipeline work.
        hour_move = round(random.uniform(-0.16, 0.16), 3)
        out.append({
            "id": s["id"],
            "question": s["question"],
            "slug": s["id"],
            "yes_token": s["id"] + "-yes",
            "no_token": s["id"] + "-no",
            "yes_price": yes,
            "no_price": no,
            "best_bid": round(yes - spread / 2, 3),
            "best_ask": round(yes + spread / 2, 3),
            "spread": spread,
            "volume": 50_000,
            "liquidity": 20_000,
            "volume_24hr": 5_000,
            "one_day_change": round(random.uniform(-0.12, 0.12), 3),
            "one_hour_change": hour_move,
            "days_left": 7,
            "closed": False,
            "accepting_orders": True,
        })
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def get_markets(source="live", limit=40):
    """Return a list of normalised markets from the chosen source.

    If 'live' fails for any reason (no network, API change), we print a clear
    note and fall back to the offline feed so the sandbox never hard-crashes.
    """
    if source == "offline":
        return fetch_offline_markets(limit)
    try:
        return fetch_live_markets(limit)
    except Exception as exc:  # we want ANY failure to fall back, not crash
        print(f"  [data] live fetch failed ({exc}); using offline feed instead.")
        return fetch_offline_markets(limit)
