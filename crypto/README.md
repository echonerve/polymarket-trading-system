# Crypto Spot Backtester

A small, honest tool to test whether any **spot** crypto timing strategy beats
simply **buying and holding** — using real daily price history, simulated money,
no exchange account, no API key, no leverage.

This is a separate system from the Polymarket sandbox in the folder above. They
share a philosophy (prove an edge on paper before risking a cent) but crypto is a
different market: continuous prices, you exit by selling, P&L is price-in vs
price-out. So this is its own code.

## Why spot, and why buy-and-hold is the benchmark

- **Spot only.** You're either 100% in the coin or 100% in cash. You can't be
  liquidated and can't lose more than you put in. It's the safe place to learn.
- **Buy & hold is the bar.** A strategy is only worth running if it ends with
  more money than doing nothing would have — *after fees*. Historically, for most
  people, holding has beaten trying to time the market. This tool checks that
  claim against real data instead of asking you to take it on faith.

## Run it

Needs Python 3.9+. Standard library only — nothing to install.

```
cd crypto

python crypto_backtest.py --refresh --product BTC-USD --days 1095
python crypto_backtest.py --product ETH-USD --days 730
python crypto_backtest.py --offline        # synthetic data, no network
```

`--refresh` downloads real daily candles from Coinbase's public API and caches
them next to the script. Re-runs without `--refresh` use the cache (instant).

It prints each strategy's final balance, total return, **return vs buy-and-hold**,
max drawdown, number of trades, and fees paid — sorted best to worst, with a
random baseline at the bottom so you can see whether anything beats luck.

## Files

| File | Job |
|------|-----|
| `crypto_data.py` | Fetches daily close prices from Coinbase (read-only), caches them, with an offline synthetic fallback. No keys, can't trade. |
| `crypto_backtest.py` | The strategies (SMA cross, momentum, mean-revert, random) and the long/flat engine that scores them against buy-and-hold, net of fees. |

## How to read it honestly

- **One winning window is not an edge.** If a strategy beats hold on BTC over 3
  years, re-run it on ETH, on SOL, on different `--days`. A rule that only wins on
  one chart is curve-fitting — you fit the past, not the future.
- **Watch the fee column.** Strategies that trade often (and the random baseline)
  hand a fortune to fees. That cost is real and unavoidable.
- **Watch max drawdown, not just return.** A strategy that returns more but with
  an 80% drawdown is one most people can't actually sit through.
- **Past performance does not predict the future.** This is educational software,
  not financial advice, and not a signal to deploy real money. Leverage/futures —
  which this tool deliberately does not touch — can liquidate an account on a
  normal price move.

## What's next

A crypto **paper-trading bot** (live prices, simulated money, like the Polymarket
one) is the planned next step — only worth wiring up for a strategy that has
already shown a real, repeatable edge here across multiple coins and windows.
