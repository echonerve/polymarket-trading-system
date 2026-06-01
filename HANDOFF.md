# Polymarket Trading System — Client Handoff

This document is written to be handed to the person who will run this system.
Read it fully before risking any money. It is deliberately honest about what
this software is and is not.

---

## 1. What this system is

A modular Polymarket trading framework with:

- **Paper trading** — live market data, simulated money (default, risk-free).
- **Backtesting** — replays hundreds of *real, already-resolved* markets to test
  whether a strategy actually beats a random baseline after fees.
- **Strategies** — a simple value/mean-reversion rule and a sum-to-one arbitrage
  detector, plus an optional AI (Claude/GPT) decision step.
- **Copy trading** — watches public leaderboard wallets and can mirror them.
- **Risk controls** — daily/monthly/drawdown/total-loss limits, per-trade size
  caps, a kill switch.
- **Live execution** — can place real orders on Polymarket, off by default,
  behind two independent safety switches.
- **Dashboard + journal** — every trade logged; an HTML dashboard charts results.

## 2. What this system is NOT

**It is not a proven money-maker, and it is not sold as one.** During development
it was tested against real data and a random baseline. The honest finding, on the
data tested, was the same one professional research reports: simple strategies on
well-priced markets do **not** show a reliable edge after fees, and the optional
AI has **no predictive advantage** over the crowd-set odds. Treat any profit as
unproven until *you* demonstrate it with the backtester on current data.

Do not run real money on it until you have done section 4. If you skip the
evidence step, you are gambling, not trading.

## 3. Requirements & setup

- Python 3.9+ (`python --version`).
- The core (paper, backtest, screener, dashboard) needs **no installs**.
- Live trading only: `pip install py-clob-client`.
- A Polygon wallet funded with **USDC.e** and a little **MATIC** for gas.
- You must be in a jurisdiction where Polymarket is permitted **for you**. Confirm
  this before proceeding — see the checklist in section 6.

Copy `.env.example` to `.env` and fill in only what you need.

## 4. Do this BEFORE any real money (in order)

```
python selftest.py                            # 1. everything runs clean
python backtest.py --refresh --markets 300    # 2. does ANY strategy beat random, net of fees?
python backtest.py --sweep                    # 3. tune — but read the overfitting warning
python bot.py --cycles 50   then  python dashboard.py   # 4. forward-test on live data, paper money
```

If step 2 shows no strategy clearly beating the random baseline across 300+
settled bets — and it still holds on a later `--refresh` you did not tune on —
then there is **no validated edge to deploy**, and live trading is not justified.

## 5. Running live (real money) — two switches, on purpose

Live orders are sent ONLY when **both** are true:

1. You run with `--live` (and do **not** pass `--dry-run`).
2. `.env` contains exactly `LIVE_ARMED=YES`.

Recommended progression:

```
python bot.py --live --dry-run --cycles 5     # logs the orders it WOULD place, sends nothing
# then, only after validating, set LIVE_ARMED=YES in .env and:
python bot.py --live --cycles 5               # sends REAL orders, hard-capped at LIVE_MAX_USD
```

Start with `LIVE_MAX_USD = 5` (in `config.py`). Validate that a real order places
and fills correctly at that size before raising it. Live order placement was
**not testable by the developer** (Polymarket is not reachable from their region)
— so you must validate it yourself, tiny first.

## 6. Security & legal — non-negotiable

- **Private key = the whole wallet.** Put it only in `.env`, on the machine that
  trades. Never in chat, screenshots, git, or a shared doc. Add `.env` to
  `.gitignore`. Use a dedicated wallet holding only what you can afford to lose.
- **TLS certificate errors:** if you ever see "certificate verify failed" /
  "hostname mismatch", STOP. It means the connection is being intercepted. Do
  **not** disable verification — that hands your traffic and key to the
  interceptor. The code keeps verification on for this reason.
- **Jurisdiction:** confirm Polymarket is legally permitted where you operate,
  and that prediction-market trading is lawful for you. If a region is blocked,
  do not circumvent it — using a VPN to evade a geo-restriction for real-money
  trading violates the platform's terms and removes any recourse if funds are
  frozen or seized.

## 7. Kill switch & monitoring

- `Ctrl+C` stops the bot immediately.
- The risk manager auto-halts on daily/drawdown/total-loss limits.
- Review `journal/trades.csv` and `python dashboard.py` regularly.

---

*This is software, not financial advice. Trading involves real risk of loss,
including total loss. Past and simulated performance do not predict future
results. The author provides no warranty and accepts no liability for trading
losses; the operator is solely responsible for legal compliance and for any
funds at risk.*

---

Delivered by **echonerve** · https://echonerve.com · © 2026
