"""
screener.py — Rank leaderboard wallets BEFORE you decide to copy them.

The copy-trading guide says "copy traders with a 60%+ win rate and consistent
profits." This module actually checks that, instead of trusting the leaderboard's
headline number. For each wallet it pulls recent trades and, for the markets that
have since RESOLVED, measures how often the side they bought actually won.

It reports, per wallet:
  - resolved trades   : how many of their bets we could actually grade
  - win rate          : % of those resolved bets that won
  - avg edge/bet      : average realized return per resolved bet
                        (won -> 1 - entry price; lost -> -entry price)
  - trades / markets  : raw activity in the window we can see
  - avg size          : typical position size in USD

HONEST LIMITS — read these, they matter:
  1. SURVIVORSHIP BIAS. The leaderboard shows this period's winners. Wallets that
     blew up are gone. A high past win rate is NOT a promise of future profit.
  2. SMALL SAMPLE. We only see recent trades via the public API. A 70% win rate
     over 12 bets is mostly luck. Trust nothing under ~30-50 resolved trades.
  3. WIN RATE != PROFIT. Someone can win 80% of bets at bad prices and still lose
     money. The "avg edge" column is a better signal than win rate alone.
  4. This is research, not advice. Even a genuinely skilled wallet trades sizes
     and at prices you can't match (see the copy-lag cost in copy mode).
"""

import random

import config
from copy_trader import fetch_wallet_trades
from market_resolution import get_resolution


# ---------------------------------------------------------------------------
# Offline synthetic history (so the screener runs with no network)
# ---------------------------------------------------------------------------

def _offline_history(wallet, n_markets=60):
    """Deterministic fake trade history for one wallet.

    Each wallet gets a hidden 'skill' in [0.40, 0.70]; for each market it tends
    to pick the (deterministic) winner with that probability. This produces a
    realistic SPREAD of win rates so the ranking has something to sort.
    """
    rng = random.Random(hash(wallet) & 0xFFFFFFFF)
    skill = 0.40 + rng.random() * 0.30
    trades = []
    for i in range(n_markets):
        cid = f"screen-{wallet[-4:]}-{i}"
        res = get_resolution(cid, source="offline")
        # Decide which side this wallet bought.
        if res["winner"] is not None and rng.random() < skill:
            outcome = res["winner"]                 # picked the eventual winner
        else:
            outcome = "No" if (res["winner"] == "Yes") else "Yes"
        trades.append({
            "tx": f"{cid}-tx", "wallet": wallet, "side": "BUY",
            "token": cid, "condition_id": cid,
            "size_shares": rng.choice([40, 100, 250, 600]),
            "price": round(rng.uniform(0.25, 0.75), 2),
            "title": f"Synthetic market {i}", "outcome": outcome,
            "trader": wallet[:8],
        })
    return trades


# ---------------------------------------------------------------------------
# Scoring one wallet
# ---------------------------------------------------------------------------

def score_wallet(wallet, source="live"):
    if source == "offline":
        trades = _offline_history(wallet)
    else:
        try:
            trades = fetch_wallet_trades(wallet, limit=config.SCREEN_TRADES_PER_WALLET)
        except Exception as exc:
            print(f"  [screen] live fetch failed for {wallet[:10]}… ({exc}); using offline.")
            trades = _offline_history(wallet)

    buys = [t for t in trades if t["side"] == "BUY"]
    notional = sum(t["size_shares"] * t["price"] for t in trades)
    markets = {t["condition_id"] for t in trades}

    resolved = 0
    wins = 0
    edge_sum = 0.0
    checked = 0
    for t in buys:
        if checked >= config.SCREEN_MAX_MARKETS:
            break
        checked += 1
        res = get_resolution(t["condition_id"], source=source)
        if not res["closed"] or res["winner"] is None:
            continue
        resolved += 1
        won = (str(t["outcome"]).lower() == str(res["winner"]).lower())
        if won:
            wins += 1
            edge_sum += (1.0 - t["price"])
        else:
            edge_sum += (-t["price"])

    win_rate = (wins / resolved * 100) if resolved else 0.0
    avg_edge = (edge_sum / resolved) if resolved else 0.0
    avg_size = (notional / len(trades)) if trades else 0.0

    return {
        "wallet": wallet,
        "trades": len(trades),
        "markets": len(markets),
        "resolved": resolved,
        "win_rate": win_rate,
        "avg_edge": avg_edge,
        "avg_size": avg_size,
    }


def _composite(row):
    """A single sort score. Rewards edge and win rate, but only trusts wallets
    with a big enough resolved sample (penalise thin samples heavily)."""
    if row["resolved"] < config.SCREEN_MIN_RESOLVED:
        confidence = row["resolved"] / max(config.SCREEN_MIN_RESOLVED, 1)
    else:
        confidence = 1.0
    return (row["avg_edge"] * 100 + (row["win_rate"] - 50)) * confidence


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def screen(wallets, source="live"):
    rows = [score_wallet(w, source=source) for w in wallets]
    rows.sort(key=_composite, reverse=True)

    print("\n" + "=" * 78)
    print("  WALLET SCREENER  (research only — read the honest limits in screener.py)")
    print("=" * 78)
    print(f"  {'rank':<5}{'wallet':<16}{'resolved':>9}{'win%':>8}{'avg edge':>10}"
          f"{'trades':>8}{'avg $':>9}")
    print("  " + "-" * 74)
    for i, r in enumerate(rows, 1):
        flag = "" if r["resolved"] >= config.SCREEN_MIN_RESOLVED else "  (thin sample!)"
        print(f"  {i:<5}{r['wallet'][:12]+'…':<16}{r['resolved']:>9}"
              f"{r['win_rate']:>7.1f}%{r['avg_edge']:>+10.3f}"
              f"{r['trades']:>8}{r['avg_size']:>8.0f}{flag}")
    print("=" * 78)
    print("  Win rate over a small sample is mostly luck. 'avg edge' > 0 across many")
    print("  resolved bets is the real signal — and even then, past != future.")
    print("  Survivorship bias: you're only seeing wallets that haven't blown up.\n")
    return rows
