"""
crypto_data.py — Daily price candles for the crypto backtester.

Source: Coinbase's public exchange API (read-only, no key, no login). It returns
daily OHLCV candles: [time, low, high, open, close, volume]. We only need the
close price for a spot backtest, plus the date.

Two sources, same output so the backtester doesn't care which it gets:
  LIVE   : real daily candles from Coinbase, paged back as far as you ask.
  OFFLINE: synthetic candles (a random walk) so it runs with no network.

This file CANNOT trade. It only reads prices. There is no key and no exchange
account anywhere in the crypto tools — same rule as the Polymarket sandbox.
"""

import json
import math
import os
import random
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

COINBASE = "https://api.exchange.coinbase.com/products/{product}/candles"
DAY = 86400


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "paper-sandbox/1.0 (read-only)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# LIVE: Coinbase daily candles (paged — the API caps each call at 300 candles)
# ---------------------------------------------------------------------------

def fetch_candles(product="BTC-USD", days=730):
    """Return [(date_str, close), ...] oldest-first for the last `days` days."""
    end = int(time.time())
    start_floor = end - days * DAY
    rows = {}
    cursor = end
    while cursor > start_floor:
        window_start = max(start_floor, cursor - 300 * DAY)
        q = urllib.parse.urlencode({
            "granularity": DAY,
            "start": datetime.fromtimestamp(window_start, timezone.utc).isoformat(),
            "end": datetime.fromtimestamp(cursor, timezone.utc).isoformat(),
        })
        batch = _get_json(f"{COINBASE.format(product=product)}?{q}")
        if not batch:
            break
        for c in batch:                      # [time, low, high, open, close, volume]
            t = int(c[0])
            rows[t] = float(c[4])            # close
        cursor = window_start
        time.sleep(0.25)                     # be polite to the API
    series = sorted(rows.items())
    return [(datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"), p)
            for t, p in series]


# ---------------------------------------------------------------------------
# OFFLINE: synthetic daily candles (geometric random walk)
# ---------------------------------------------------------------------------

def synthetic_candles(days=730, seed=1, start_price=30000.0,
                      drift=0.0003, vol=0.03):
    """A plausible-looking price path. `drift`>0 trends up over time; `vol` is
    daily volatility. Defaults loosely resemble a volatile, mildly up-trending
    coin — enough to exercise every strategy. Not real data."""
    rng = random.Random(seed)
    price = start_price
    out = []
    base = int(time.time()) - days * DAY
    for i in range(days):
        shock = rng.gauss(drift, vol)
        price = max(1.0, price * math.exp(shock))
        date = datetime.fromtimestamp(base + i * DAY, timezone.utc).strftime("%Y-%m-%d")
        out.append((date, round(price, 2)))
    return out


# ---------------------------------------------------------------------------
# Public entry point + caching
# ---------------------------------------------------------------------------

def _cache_path(product):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        f"candles_{product.replace('-', '_')}.json")


def get_candles(product="BTC-USD", days=730, source="live", use_cache=True):
    """Return [(date, close), ...]. Caches live data so re-runs are instant.

    source="live"    -> Coinbase (falls back to offline on any failure)
    source="offline" -> synthetic
    """
    if source == "offline":
        return synthetic_candles(days)

    path = _cache_path(product)
    if use_cache and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cached = json.load(f)
        if len(cached) >= days * 0.8:        # good enough, use it
            return [(d, p) for d, p in cached][-days:]

    try:
        series = fetch_candles(product, days)
        if series:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(series, f)
            return series
        raise ValueError("empty series")
    except Exception as exc:
        print(f"  [crypto-data] live fetch failed ({exc}); using offline synthetic series.")
        return synthetic_candles(days)
