"""
dca_vs_trade.py — Compare three ways to put money into a coin, on real data:

  1. LUMP-SUM HOLD : invest everything on day one, do nothing.
  2. DCA           : dollar-cost-average — invest the same total in equal chunks
                     spread evenly across the period (the "boring" approach).
  3. ACTIVE TIMING : an SMA 20/50 long/flat strategy that tries to dodge dips.

All three start with the SAME total capital, so it's a fair fight. The output
shows final value, return, worst drawdown, fees, and trades for each.

Why this exists: the backtests showed active timing rarely beats just holding,
after fees. This tool lets you see, on real prices, how plain holding and DCA
stack up against trying to trade — so you can make an exposure decision based on
evidence instead of hope.

USAGE
    python dca_vs_trade.py --refresh --product BTC-USD --days 1095 --capital 1200
    python dca_vs_trade.py --offline          # synthetic data, no network

Simulation only. Not financial advice. Past performance != future results.
"""

import argparse

from crypto_data import get_candles

FEE_RATE = 0.005          # 0.5% per buy/switch — realistic retail spot fee.


def max_drawdown(equity):
    peak = equity[0]; worst = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak)
    return worst * 100


def lump_sum_hold(prices, capital):
    fee = capital * FEE_RATE
    units = (capital - fee) / prices[0]
    equity = [units * p for p in prices]
    return {"name": "lump-sum hold", "invested": capital, "final": equity[-1],
            "max_dd": max_drawdown(equity), "fees": fee, "trades": 1}


def dca(prices, capital, periods):
    """Invest capital/periods at `periods` evenly spaced days; hold the rest."""
    n = len(prices)
    periods = max(1, min(periods, n))
    buy_idxs = {int(i * (n - 1) / (periods - 1)) if periods > 1 else 0 for i in range(periods)}
    chunk = capital / periods
    units = 0.0
    invested = 0.0
    fees = 0.0
    cash_waiting = capital
    equity = []
    for i, p in enumerate(prices):
        if i in buy_idxs and cash_waiting > 0:
            spend = min(chunk, cash_waiting)
            fee = spend * FEE_RATE
            units += (spend - fee) / p
            cash_waiting -= spend
            invested += spend
            fees += fee
        equity.append(units * p + cash_waiting)
    return {"name": f"DCA x{periods}", "invested": capital, "final": equity[-1],
            "max_dd": max_drawdown(equity), "fees": fees, "trades": len(buy_idxs)}


def _sma(xs, k):
    return sum(xs[-k:]) / k if len(xs) >= k else None


def active_sma(prices, capital, fast=20, slow=50):
    cash = capital; units = 0.0; position = 0; fees = 0.0; trades = 0; equity = []
    for i, p in enumerate(prices):
        f, s = _sma(prices[:i + 1], fast), _sma(prices[:i + 1], slow)
        target = 1 if (f is not None and s is not None and f > s) else 0
        if target == 1 and position == 0:
            fee = cash * FEE_RATE; units = (cash - fee) / p; cash = 0.0
            fees += fee; position = 1; trades += 1
        elif target == 0 and position == 1:
            proceeds = units * p; fee = proceeds * FEE_RATE; cash = proceeds - fee
            units = 0.0; fees += fee; position = 0; trades += 1
        equity.append(cash + units * p)
    return {"name": "active SMA 20/50", "invested": capital, "final": cash + units * prices[-1],
            "max_dd": max_drawdown(equity), "fees": fees, "trades": trades}


def report(rows, product, n):
    rows_sorted = sorted(rows, key=lambda r: r["final"], reverse=True)
    print("\n" + "=" * 78)
    print(f"  HOLD vs DCA vs TRADE — {product}, {n} days, equal capital  (simulation)")
    print("=" * 78)
    print(f"  {'approach':<20}{'invested':>10}{'final':>12}{'return':>10}{'max DD':>9}{'fees':>9}{'trades':>8}")
    print("  " + "-" * 74)
    for r in rows_sorted:
        ret = (r["final"] / r["invested"] - 1) * 100
        print(f"  {r['name']:<20}{('$%.0f' % r['invested']):>10}{('$%.0f' % r['final']):>12}"
              f"{('%+.1f%%' % ret):>10}{('%.1f%%' % r['max_dd']):>9}{('$%.0f' % r['fees']):>9}{r['trades']:>8}")
    print("=" * 78)
    best = rows_sorted[0]
    print(f"  Highest ending value: {best['name']}.")
    print("  In a rising market, lump-sum usually wins on return but with the biggest")
    print("  drawdown; DCA lowers the drawdown and the 'bought at the top' risk; active")
    print("  timing usually trails after fees. Pick for the drawdown you can stomach,")
    print("  not just the headline return. Not financial advice.\n")


def main():
    p = argparse.ArgumentParser(description="Compare hold vs DCA vs active timing on real data")
    p.add_argument("--product", default="BTC-USD")
    p.add_argument("--days", type=int, default=1095)
    p.add_argument("--capital", type=float, default=1200.0, help="total capital, same for all three")
    p.add_argument("--dca-periods", type=int, default=52, help="number of DCA buys (e.g. 52 = weekly over the window)")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--offline", action="store_true")
    args = p.parse_args()

    source = "offline" if args.offline else "live"
    series = get_candles(args.product, days=args.days, source=source, use_cache=not args.refresh)
    if len(series) < 60:
        print("Not enough price history."); return
    prices = [pr for _, pr in series]
    print(f"Loaded {len(prices)} daily closes for {args.product} ({series[0][0]} to {series[-1][0]}).")

    rows = [
        lump_sum_hold(prices, args.capital),
        dca(prices, args.capital, args.dca_periods),
        active_sma(prices, args.capital),
    ]
    report(rows, args.product, len(prices))


if __name__ == "__main__":
    main()
