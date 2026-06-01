"""
backtest.py — Replay REAL resolved markets to test whether a strategy has an edge.

This is the "build evidence first" tool. Live/paper trading shows you a handful of
outcomes; a backtest shows you hundreds of SETTLED bets at once, using the real
prices that markets actually traded at and the real outcomes they resolved to.

It answers the only question that matters before risking money:
    "Across many bets, after fees, does this rule make or lose money?"

HOW IT WORKS
------------
1. Fetch a batch of RESOLVED markets from Polymarket (we know who won).
2. For each, fetch its real YES-price history from the CLOB price API.
3. Pick an entry point in that history, let a strategy decide YES / NO / SKIP,
   then settle at the real outcome (1.0 if right, 0.0 if wrong) minus fees.
4. Do this for every market and report win rate, average edge, and net P&L —
   for several strategies side by side, including a random baseline.

The data is cached to backtest_data.json so you only download once.

USAGE
-----
    python backtest.py --refresh --markets 200   # download real data, then test
    python backtest.py                            # re-run on cached data (fast)
    python backtest.py --offline                  # synthetic data, no network

HONEST EXPECTATION
------------------
Prediction markets are usually well calibrated: a thing priced at 70% happens
~70% of the time. That means simple price rules tend to net roughly ZERO before
fees and NEGATIVE after. If a strategy here clears fees across 200+ bets, that's
genuinely interesting and worth a hard second look — not a green light to go live.
A random baseline is included so you can see whether a strategy beats luck at all.
"""

import argparse
import json
import os
import random
import urllib.request
import urllib.parse

import config
from polymarket_data import _parse_json_list, _to_float

GAMMA_URL = "https://gamma-api.polymarket.com/markets"
HISTORY_URL = "https://clob.polymarket.com/prices-history"
CACHE = "backtest_data.json"


# ---------------------------------------------------------------------------
# Fetching real data
# ---------------------------------------------------------------------------

def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "paper-sandbox/1.0 (read-only)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_resolved_markets(target=200, min_volume=20_000):
    """Pull resolved binary markets (known winner) with decent volume."""
    out = []
    offset = 0
    page = 100
    while len(out) < target and offset < 2000:
        q = urllib.parse.urlencode({
            "closed": "true", "limit": page, "offset": offset,
            "order": "volume", "ascending": "false",
        })
        batch = _get_json(f"{GAMMA_URL}?{q}")
        if not batch:
            break
        offset += page
        for m in batch:
            outcomes = _parse_json_list(m.get("outcomes"))
            prices = _parse_json_list(m.get("outcomePrices"))
            tokens = _parse_json_list(m.get("clobTokenIds"))
            if len(outcomes) != 2 or len(prices) != 2 or len(tokens) != 2:
                continue
            p0, p1 = _to_float(prices[0]), _to_float(prices[1])
            # Need a clean resolution: one side at ~1, the other at ~0.
            if max(p0, p1) < 0.95 or min(p0, p1) > 0.05:
                continue
            if _to_float(m.get("volumeNum") or m.get("volume")) < min_volume:
                continue
            out.append({
                "condition_id": m.get("conditionId", ""),
                "question": m.get("question", ""),
                "winner": "YES" if p0 >= p1 else "NO",   # index 0 = first outcome
                "yes_token": str(tokens[0]),
            })
            if len(out) >= target:
                break
    return out


def fetch_price_history(token_id, fidelity=720):
    q = urllib.parse.urlencode({"market": token_id, "interval": "max", "fidelity": fidelity})
    data = _get_json(f"{HISTORY_URL}?{q}")
    return [(int(pt["t"]), float(pt["p"])) for pt in data.get("history", [])]


def build_dataset(target, min_volume):
    """Download markets + price histories and cache them to CACHE."""
    print(f"Fetching up to {target} resolved markets (volume >= ${min_volume:,})…")
    markets = fetch_resolved_markets(target, min_volume)
    print(f"  got {len(markets)} markets; downloading price histories…")
    dataset = []
    for i, m in enumerate(markets):
        try:
            hist = fetch_price_history(m["yes_token"])
        except Exception as exc:
            print(f"  [{i+1}/{len(markets)}] history failed: {exc}")
            continue
        if len(hist) < 5:                      # need enough points to have an entry
            continue
        dataset.append({**m, "yes_prices": [p for _, p in hist]})
        if (i + 1) % 25 == 0:
            print(f"  {i+1}/{len(markets)} histories done…")
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(dataset, f)
    print(f"Cached {len(dataset)} markets to {CACHE}.")
    return dataset


def load_dataset():
    if not os.path.exists(CACHE):
        return None
    with open(CACHE, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Synthetic dataset (offline) — calibrated markets, so honest by construction
# ---------------------------------------------------------------------------

def synthetic_dataset(n=300, seed=1):
    """Make calibrated fake markets: a market that entered at price p wins with
    probability p (that's what 'calibrated' means). A realistic null world where
    no price rule should have an edge — the perfect honesty check for the engine.
    """
    rng = random.Random(seed)
    ds = []
    for i in range(n):
        # A market's "true" probability. The price hovers tightly around it, so
        # the entry price the engine sees ~= the true probability (calibrated).
        true_p = rng.uniform(0.08, 0.92)
        prices = [round(min(0.97, max(0.03, true_p + rng.gauss(0, 0.015))), 3)
                  for _ in range(rng.randint(8, 24))]
        won_yes = rng.random() < true_p          # calibrated: wins at rate true_p
        ds.append({
            "condition_id": f"syn-{i}", "question": f"Synthetic market {i}",
            "winner": "YES" if won_yes else "NO",
            "yes_token": f"syn-tok-{i}", "yes_prices": prices,
        })
    return ds


# ---------------------------------------------------------------------------
# Strategies — each sees the YES-price history up to entry; returns YES/NO/None
# ---------------------------------------------------------------------------

def s_favorite(hist):      # buy whichever side is currently favoured
    return "YES" if hist[-1] >= 0.5 else "NO"

def s_longshot(hist):      # buy the underdog
    return "NO" if hist[-1] >= 0.5 else "YES"

def s_yes_always(hist):
    return "YES"

def s_momentum(hist):      # ride the recent move
    if len(hist) < 3:
        return None
    return "YES" if hist[-1] > hist[-3] else "NO"

def s_mean_revert(hist):   # fade the recent move
    if len(hist) < 3:
        return None
    return "NO" if hist[-1] > hist[-3] else "YES"

def s_random(hist):
    return random.choice(["YES", "NO"])

STRATEGIES = {
    "buy favorite": s_favorite,
    "buy longshot": s_longshot,
    "always YES": s_yes_always,
    "momentum": s_momentum,
    "mean-revert": s_mean_revert,
    "random (baseline)": s_random,
}


# ---------------------------------------------------------------------------
# The backtest engine
# ---------------------------------------------------------------------------

def run_strategy(name, fn, dataset, entry_frac=0.5, stake=10.0):
    """Replay one strategy across all markets. Entry is the price `entry_frac`
    of the way through each market's history (0.5 = midpoint of its life)."""
    bets = wins = 0
    staked = 0.0
    pnl = 0.0
    fees = 0.0
    for m in dataset:
        prices = m["yes_prices"]
        if len(prices) < 3:
            continue
        idx = max(1, min(len(prices) - 1, int(len(prices) * entry_frac)))
        hist = prices[:idx + 1]
        side = fn(hist)
        if side is None:
            continue
        yes_price = hist[-1]
        # price you'd PAY for the side you chose, plus slippage
        entry = (yes_price if side == "YES" else (1 - yes_price)) + config.SLIPPAGE
        entry = min(0.99, max(0.01, entry))
        fee = stake * config.FEE_RATE
        shares = stake / entry
        won = (side == m["winner"])
        payout = shares * (1.0 if won else 0.0)
        pnl += payout - stake - fee
        fees += fee
        staked += stake
        bets += 1
        wins += 1 if won else 0
    win_rate = (wins / bets * 100) if bets else 0.0
    roi = (pnl / staked * 100) if staked else 0.0
    return {"name": name, "bets": bets, "win_rate": win_rate,
            "pnl": pnl, "fees": fees, "roi": roi}


def report(rows):
    rows.sort(key=lambda r: r["roi"], reverse=True)
    print("\n" + "=" * 76)
    print("  BACKTEST RESULTS  (real settled markets unless --offline)")
    print("=" * 76)
    print(f"  {'strategy':<20}{'bets':>7}{'win%':>8}{'net P&L':>12}{'fees':>10}{'ROI':>9}")
    print("  " + "-" * 72)
    for r in rows:
        print(f"  {r['name']:<20}{r['bets']:>7}{r['win_rate']:>7.1f}%"
              f"{('$%+.2f' % r['pnl']):>12}{('$%.2f' % r['fees']):>10}{('%+.1f%%' % r['roi']):>9}")
    print("=" * 76)
    best = rows[0]
    if best["roi"] > 0:
        print(f"  Best: '{best['name']}' at {best['roi']:+.1f}% ROI over {best['bets']} bets.")
        print("  Before trusting it: is it above the random baseline by a wide margin?")
        print("  Does it survive on fresh data (re-run with --refresh)? Small samples lie.")
    else:
        print("  Every strategy lost money after fees — the expected result for")
        print("  calibrated markets. No edge here. That is a real, useful finding.")
    print("  Past performance does not predict future results. Not financial advice.\n")


def sweep(dataset):
    """Grid-search momentum & mean-revert over lookbacks and entry points.

    This is how you HONESTLY probe the strategy space — and also how people fool
    themselves. Read the warning printed at the end before you believe anything.
    """
    def make_momentum(lb):
        def f(hist):
            if len(hist) <= lb:
                return None
            return "YES" if hist[-1] > hist[-1 - lb] else "NO"
        return f

    def make_mean_revert(lb):
        def f(hist):
            if len(hist) <= lb:
                return None
            return "NO" if hist[-1] > hist[-1 - lb] else "YES"
        return f

    lookbacks = [2, 3, 5, 10, 20]
    entry_fracs = [0.3, 0.5, 0.7]
    rows = []
    for lb in lookbacks:
        for ef in entry_fracs:
            r = run_strategy(f"mom lb={lb} ef={ef}", make_momentum(lb), dataset, entry_frac=ef)
            rows.append(r)
            r = run_strategy(f"rev lb={lb} ef={ef}", make_mean_revert(lb), dataset, entry_frac=ef)
            rows.append(r)
    # Reference points
    baseline = run_strategy("random (baseline)", s_random, dataset, entry_frac=0.5)
    favorite = run_strategy("buy favorite", s_favorite, dataset, entry_frac=0.5)
    combos = len(rows)
    rows.sort(key=lambda r: r["roi"], reverse=True)

    print("\n" + "=" * 76)
    print(f"  PARAMETER SWEEP — {combos} strategy variants tested")
    print("=" * 76)
    print(f"  {'variant':<20}{'bets':>7}{'win%':>8}{'net P&L':>12}{'fees':>10}{'ROI':>9}")
    print("  " + "-" * 72)
    for r in rows[:10]:
        print(f"  {r['name']:<20}{r['bets']:>7}{r['win_rate']:>7.1f}%"
              f"{('$%+.2f' % r['pnl']):>12}{('$%.2f' % r['fees']):>10}{('%+.1f%%' % r['roi']):>9}")
    print("  " + "-" * 72)
    print(f"  reference: random baseline ROI {baseline['roi']:+.1f}% | buy-favorite ROI {favorite['roi']:+.1f}%")
    print("=" * 76)
    best = rows[0]
    print(f"  Best variant: '{best['name']}' at {best['roi']:+.1f}% ROI.")
    print(f"  WARNING: you just tested {combos} variants. With that many tries, the")
    print("  best one looks good BY CHANCE even if none has real edge — that's")
    print("  overfitting. The only honest test is: does this exact variant still win")
    print("  on data you did NOT use to pick it? Re-run --refresh later and re-check.")
    print(f"  If the best variant barely beats the random baseline ({baseline['roi']:+.1f}%), it's noise.\n")


def main():
    p = argparse.ArgumentParser(description="Backtest strategies on real resolved markets")
    p.add_argument("--refresh", action="store_true", help="download fresh real data")
    p.add_argument("--offline", action="store_true", help="use synthetic calibrated data")
    p.add_argument("--markets", type=int, default=200, help="how many markets to fetch")
    p.add_argument("--min-volume", type=int, default=20_000)
    p.add_argument("--entry-frac", type=float, default=0.5, help="entry point in each market's life (0..1)")
    p.add_argument("--sweep", action="store_true", help="grid-search strategy parameters (with overfitting warning)")
    args = p.parse_args()

    if args.offline:
        dataset = synthetic_dataset()
        print(f"Using {len(dataset)} synthetic calibrated markets (offline).")
    elif args.refresh:
        dataset = build_dataset(args.markets, args.min_volume)
    else:
        dataset = load_dataset()
        if dataset is None:
            print("No cached data. Run:  python backtest.py --refresh   (or --offline)")
            return
        print(f"Loaded {len(dataset)} markets from {CACHE} (use --refresh to update).")

    if not dataset:
        print("No usable markets in dataset.")
        return

    if args.sweep:
        sweep(dataset)
        return

    rows = [run_strategy(name, fn, dataset, entry_frac=args.entry_frac)
            for name, fn in STRATEGIES.items()]
    report(rows)


if __name__ == "__main__":
    main()
