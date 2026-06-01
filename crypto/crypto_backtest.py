"""
crypto_backtest.py — Test spot crypto strategies against just buying and holding.

SPOT ONLY. No leverage, no liquidation, no shorting. Each day a strategy is
either LONG the coin (100%) or FLAT (all cash). You can never lose more than you
put in. This is on purpose — it's the safe place to find out whether any timing
rule actually beats simply holding.

The benchmark to beat is BUY & HOLD. That is the honest bar: a strategy is only
worth anything if it ends with more money than you'd have by buying on day one
and doing nothing — AFTER fees. Most don't. This tool shows you, with real data.

USAGE
-----
    python crypto_backtest.py --refresh --product BTC-USD --days 1095
    python crypto_backtest.py                 # re-run on cached data
    python crypto_backtest.py --offline       # synthetic data, no network

NOTHING HERE TRADES REAL MONEY. No key, no exchange account. It reads prices and
simulates. Going live with real funds is a separate decision with separate risks
(see the warnings printed at the end of a run).
"""

import argparse
import statistics

from crypto_data import get_candles

# ---------------------------------------------------------------------------
# Settings (edit freely)
# ---------------------------------------------------------------------------
STARTING_CASH = 1000.0
FEE_RATE = 0.005          # 0.5% taker fee per switch — realistic retail spot fee.


# ---------------------------------------------------------------------------
# Strategies: given the closing prices SO FAR, return 1 (be long) or 0 (be flat)
# Using only past data (prices[:i+1]) means no peeking into the future.
# ---------------------------------------------------------------------------

def _sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


def s_buy_hold(prices):
    return 1


def s_sma_cross(prices, fast=20, slow=50):
    f, s = _sma(prices, fast), _sma(prices, slow)
    if f is None or s is None:
        return 0
    return 1 if f > s else 0


def s_momentum(prices, lookback=30):
    if len(prices) <= lookback:
        return 0
    return 1 if prices[-1] > prices[-1 - lookback] else 0


def s_mean_revert(prices, n=20):
    avg = _sma(prices, n)
    if avg is None:
        return 0
    return 1 if prices[-1] < avg else 0      # buy when below average ("buy the dip")


def s_random(prices):
    import random
    return random.randint(0, 1)


STRATEGIES = {
    "buy & hold": s_buy_hold,
    "SMA 20/50 cross": s_sma_cross,
    "momentum 30d": s_momentum,
    "mean-revert 20d": s_mean_revert,
    "random (baseline)": s_random,
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def max_drawdown(equity):
    """Worst peak-to-trough drop in the equity curve, as a positive %."""
    peak = equity[0]
    worst = 0.0
    for v in equity:
        peak = max(peak, v)
        worst = max(worst, (peak - v) / peak)
    return worst * 100


def run_strategy(name, fn, prices):
    cash = STARTING_CASH
    units = 0.0
    position = 0
    fees = 0.0
    trades = 0
    equity = []
    for i in range(len(prices)):
        price = prices[i]
        target = fn(prices[:i + 1])
        if target == 1 and position == 0:
            spend = cash
            fee = spend * FEE_RATE
            units = (spend - fee) / price
            cash = 0.0
            fees += fee
            position = 1
            trades += 1
        elif target == 0 and position == 1:
            proceeds = units * price
            fee = proceeds * FEE_RATE
            cash = proceeds - fee
            units = 0.0
            fees += fee
            position = 0
            trades += 1
        equity.append(cash + units * price)

    final = cash + units * prices[-1]
    return {
        "name": name,
        "final": final,
        "return_pct": (final / STARTING_CASH - 1) * 100,
        "max_dd": max_drawdown(equity),
        "trades": trades,
        "fees": fees,
    }


def report(rows, product, n_days, bh_return):
    rows.sort(key=lambda r: r["return_pct"], reverse=True)
    print("\n" + "=" * 80)
    print(f"  CRYPTO SPOT BACKTEST — {product}, {n_days} days  (simulation only)")
    print("=" * 80)
    print(f"  {'strategy':<20}{'final $':>11}{'return':>10}{'vs hold':>10}{'max DD':>9}{'trades':>8}{'fees':>9}")
    print("  " + "-" * 76)
    for r in rows:
        vs = r["return_pct"] - bh_return
        final_str = f"${r['final']:,.0f}"
        print(f"  {r['name']:<20}{final_str:>11}"
              f"{('%+.1f%%' % r['return_pct']):>10}{('%+.1f%%' % vs):>10}"
              f"{('%.1f%%' % r['max_dd']):>9}{r['trades']:>8}{('$%.0f' % r['fees']):>9}")
    print("=" * 80)
    beat = [r for r in rows if r["name"] != "buy & hold" and r["return_pct"] > bh_return]
    if beat:
        b = beat[0]
        print(f"  '{b['name']}' beat buy & hold by {b['return_pct'] - bh_return:+.1f}% over this window.")
        print("  BUT: one window is not proof. Re-test on other coins and date ranges")
        print("  (--product, --days). A rule that only wins on one chart is curve-fitting.")
    else:
        print("  Nothing beat buy & hold after fees over this window — the usual result.")
        print("  For most people, holding has beaten timing the market. That's the finding.")
    print("  Spot only: you can't be liquidated here. Live trading with leverage can")
    print("  wipe an account on a normal move. Not financial advice.\n")


def main():
    p = argparse.ArgumentParser(description="Spot crypto strategy backtester (simulation only)")
    p.add_argument("--product", default="BTC-USD", help="e.g. BTC-USD, ETH-USD, SOL-USD")
    p.add_argument("--days", type=int, default=1095, help="how many days of history")
    p.add_argument("--refresh", action="store_true", help="force a fresh download")
    p.add_argument("--offline", action="store_true", help="use synthetic data, no network")
    args = p.parse_args()

    source = "offline" if args.offline else "live"
    series = get_candles(args.product, days=args.days, source=source,
                         use_cache=not args.refresh)
    if len(series) < 60:
        print("Not enough price history to backtest.")
        return
    prices = [p for _, p in series]
    print(f"Loaded {len(prices)} daily closes for {args.product} "
          f"({series[0][0]} to {series[-1][0]}).")

    bh = run_strategy("buy & hold", s_buy_hold, prices)["return_pct"]
    rows = [run_strategy(name, fn, prices) for name, fn in STRATEGIES.items()]
    report(rows, args.product, len(prices), bh)


if __name__ == "__main__":
    main()
