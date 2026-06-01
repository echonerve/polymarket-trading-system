"""
market_resolution.py — "Did this market settle yet, and which side won?"

Used in two places:
  - copy-trading settlement: turn an open copy position into a real win/loss
    once its market resolves.
  - the wallet screener: judge whether a wallet's past bets actually won.

It looks a market up by its conditionId on the public Gamma API. A resolved
binary market reports closed=true and outcomePrices like ["1","0"] (the winner
settles to 1.00, the loser to 0.00). Results are cached so we never ask twice.

Offline mode invents a stable, repeatable resolution per market id so the
settlement and screener paths can be demonstrated without a network.
"""

import json
import urllib.request
import urllib.parse

from polymarket_data import _parse_json_list, _to_float

GAMMA_URL = "https://gamma-api.polymarket.com/markets"

# conditionId -> {"closed": bool, "winner": "Yes"/"No"/None}
_CACHE = {}


def _winner_from(outcomes, prices):
    """Given outcome labels and their settled prices, return the winner label.

    Returns None if it doesn't look resolved (no price clearly near 1.0).
    """
    best_label, best_price = None, 0.0
    for label, price in zip(outcomes, prices):
        p = _to_float(price)
        if p > best_price:
            best_label, best_price = label, p
    return best_label if best_price >= 0.95 else None


def fetch_resolution_live(condition_id):
    params = urllib.parse.urlencode({"condition_ids": condition_id})
    req = urllib.request.Request(
        f"{GAMMA_URL}?{params}",
        headers={"User-Agent": "paper-sandbox/1.0 (read-only)"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data:
        return {"closed": False, "winner": None}
    m = data[0]
    outcomes = _parse_json_list(m.get("outcomes"))
    prices = _parse_json_list(m.get("outcomePrices"))
    closed = bool(m.get("closed"))
    winner = _winner_from(outcomes, prices) if closed else None
    return {"closed": closed, "winner": winner}


def fetch_resolution_offline(condition_id):
    """Deterministic fake resolution so offline demos can settle.

    ~60% of markets count as 'resolved'; the winner is decided by a stable hash
    of the id, so the same market always resolves the same way within a run.
    """
    h = abs(hash(condition_id))
    if h % 10 < 6:                       # 60% resolved
        winner = "Yes" if (h // 10) % 2 == 0 else "No"
        return {"closed": True, "winner": winner}
    return {"closed": False, "winner": None}


def get_resolution(condition_id, source="live"):
    """Cached resolution lookup. Never raises — unknown -> not resolved."""
    if not condition_id:
        return {"closed": False, "winner": None}
    if condition_id in _CACHE:
        return _CACHE[condition_id]
    try:
        if source == "offline":
            result = fetch_resolution_offline(condition_id)
        else:
            result = fetch_resolution_live(condition_id)
    except Exception:
        result = {"closed": False, "winner": None}
    # Only cache resolved results; an open market may resolve later in a long run.
    if result["closed"]:
        _CACHE[condition_id] = result
    return result
