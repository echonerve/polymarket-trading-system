<div align="center">

# Polymarket Trading System

**by [echonerve](https://echonerve.com)** · build · test · decide with evidence

`paper trading` · `backtesting` · `risk controls` · `optional AI` · `guarded live execution`

</div>

---

A small, fully readable program that **simulates** trading on Polymarket using
**real, public market prices** but **pretend money**. It exists so you can test
whether a trading idea actually works *before* risking a single real dollar.

There is **no exchange connection, no wallet, and no private key anywhere in this
project**. It cannot move money. By design.

---

## Why this instead of the "money bot" from the guides?

You asked for a foolproof, error-free money-making system. I have to be straight
with you, because you asked me to find the blind spots:

**No such system exists — for anyone, at any budget.** Trading is adversarial and,
after fees, slightly negative-sum. A bot that automates a *losing* idea just loses
money faster, 24/7. The two guides you uploaded even admit this in their own fine
print: *"92% of Polymarket traders lose money,"* *"only 7.6% are profitable."*

They also contradict themselves: they say the profits come from arbitrage windows
that **last 2.7 seconds** and are captured by bots with **sub-100-millisecond**
execution — and then tell you to capture those same windows with a Python script
**polling every 5 seconds** on a free server. Those can't both be true. You cannot
win a sub-100ms race by checking every 5,000ms.

So the genuinely useful thing isn't a money printer. It's this: a safe way to
**measure** whether an idea has any edge, with fake money, where you understand
every line. If an idea makes money here over hundreds of trades, that's a lead
worth investigating. If it loses (the likely outcome), you learned it for free.

---

## What it does

Every "cycle" the bot:

1. Pulls the busiest open markets from Polymarket's public Gamma API (read-only).
2. Runs your strategies to look for a possible edge.
3. Places **simulated** bets, sized and gated by strict risk rules.
4. Logs every trade to a CSV and tracks a virtual balance.
5. Prints an honest report: P&L, fees paid, win rate, drawdown.

---

## How to run it

You need Python 3.9+. Nothing to install — it uses only the standard library.

```
cd Polymarket-Paper-Sandbox

python bot.py                 # one scan of LIVE markets, then a report
python bot.py --cycles 20     # 20 live scans, 30s apart (set in config.py)
python bot.py --offline       # synthetic prices, no internet needed
python bot.py --backtest 300  # 300 instant cycles on synthetic data

python bot.py --ai            # use the AI brain for decisions (needs an API key)
python bot.py --ai-mock --backtest 30   # demo the AI plumbing, no key, no cost

python bot.py --copy --cycles 10         # COPY real leaderboard wallets (simulated)
python bot.py --copy --offline --cycles 5  # copy demo with synthetic whales

python bot.py --screen                   # rank the wallets in config.py, then exit
python bot.py --screen --offline         # screener demo with synthetic wallets

python dashboard.py                      # build dashboard.html from the journal

python backtest.py --refresh --markets 200   # download real resolved markets, test strategies
python backtest.py                            # re-run on cached data (fast)
python backtest.py --offline                  # synthetic calibrated data, no network
```

### Backtest harness (`python backtest.py`)

The "build evidence first" tool. `--refresh` downloads a batch of REAL resolved
markets plus their real price histories (cached to `backtest_data.json`), then
replays several strategies over all of them — reporting win rate, net-of-fees
P&L, and ROI side by side, including a **random baseline**. If your "best"
strategy can't clearly beat random across 200+ settled bets, you have no edge.
That is the bar to clear before live trading is even a rational conversation.

### Results dashboard (`python dashboard.py`)

After a session, run `python dashboard.py` to turn `journal/trades.csv` into a
single `dashboard.html` you can double-click open (the data is baked into the
page — no server needed; it only pulls the Chart.js drawing library from a CDN).
It shows headline cards (trades, win rate, fees, realized P&L, net), an equity
curve, a cumulative **fees vs realized P&L** chart so you can literally watch the
house's cut eat returns, and a wins-vs-losses bar. Win rate and realized P&L
count only resolved (`SETTLE`) bets — open positions haven't happened yet.

### Wallet screener (`--screen`)

Before you copy anyone, this ranks the wallets in `config.py` (`TARGET_WALLETS`).
For each wallet it pulls recent trades and, for the markets that have since
**resolved**, measures how often the side they bought actually won — plus an
"avg edge" per resolved bet (a better signal than win rate alone). Wallets with
too few resolved bets are flagged as a thin sample (i.e. mostly luck). It prints
loud warnings about survivorship bias: the leaderboard only shows wallets that
haven't blown up yet, so a great past record is not a promise of future profit.

### Copy-trading mode (`--copy`)

Watches the real wallets in `TARGET_WALLETS` via Polymarket's public trade feed
and **simulates** copying their buys into your pretend portfolio. Get wallet
addresses from <https://polymarket.com/leaderboard>.

Two honest mechanics it makes visible:

- **"Lost to copy lag"** — it fills you at a slightly worse price than the whale
  got, because in reality you only see their trade seconds-to-minutes later. That
  lag tax is the main reason naive copy-trading underperforms.
- **Settlement** — when a market you copied into resolves, the position is paid
  out (1.00/share if your side won, 0.00 if it lost), so your win/loss and
  realized P&L are real outcomes, logged as `SETTLE` rows in the journal — not
  just paper marks that never get graded.

### AI brain mode (`--ai`)

Optionally asks an LLM (Claude, GPT, Gemini, Kimi…) whether each market is worth a
paper bet. It's **off** unless you put an API key in a `.env` file (copy
`.env.example`). With no key, the bot just uses the maths strategy. Use `--ai-mock`
to see the whole AI flow run with no key and no cost. Remember: an LLM has **no
live edge** on prices and will be confidently wrong sometimes — its "confidence"
is a vibe, not a probability. That's exactly why it only drives *paper* trades.

Stop anytime with **Ctrl+C** — that's your kill switch. The risk manager also
halts automatically on big losses.

---

## The files (what each one is for)

| File | Plain-English job |
|------|-------------------|
| `config.py` | Every setting in one place: starting balance, fees, risk limits, which strategies are on. Change a number, re-run. |
| `polymarket_data.py` | Gets prices. Real public data by default; synthetic offline feed as a fallback so it never hard-crashes. Read-only. |
| `portfolio.py` | The pretend money: balance, positions, fees, profit/loss. "Buying" just subtracts from a number. |
| `risk_manager.py` | The brakes: daily/monthly/drawdown/total-loss limits + trade caps. The most important file. |
| `strategies.py` | The "should we bet?" logic. Two hypotheses (mean-reversion + sum-to-one arb detector). **Neither is known to be profitable** — that's what you're testing. |
| `journal.py` | Writes every simulated trade to `journal/trades.csv` so you can audit the bot's claims yourself. |
| `copy_trader.py` | Watches real leaderboard wallets and simulates copying them, with an explicit "copy lag" cost. Settles copy positions to real win/loss once their markets resolve. |
| `market_resolution.py` | Looks up whether a market has resolved and which side won (by condition ID), with caching. Powers settlement and the screener. |
| `screener.py` | Ranks candidate wallets by resolved-market win rate and average edge before you decide to copy them. |
| `dashboard.py` | Reads the journal and writes a self-contained `dashboard.html` with charts (equity, fees vs P&L, win/loss) and headline metrics. |
| `backtest.py` | Replays REAL resolved markets (with real price history) to test strategies over hundreds of settled bets, net of fees, against a random baseline. The "build evidence first" tool. |
| `ai_engine.py` | Optional LLM decision brain (Claude/GPT/Gemini/Kimi via OpenRouter). Off unless you add an API key. Stdlib only. |
| `.env.example` | Template for your AI API key. Copy to `.env`. Deliberately has NO field for a wallet/private key — the sandbox never needs one. |
| `bot.py` | The main program that ties it together and prints the report. |
| `selftest.py` | One command (`python selftest.py`) that runs every mode offline and prints a PASS/FAIL board. Your "is the whole machine healthy?" check. |

---

## How to read the results honestly

- **Fees paid** is the house's cut. Watch how it quietly eats returns.
- **A few winning cycles mean nothing.** You need a few hundred trades before a
  win rate is anything more than luck.
- **Mark-to-market P&L moves around** as prices wander; only *settled* wins/losses
  (when a market actually resolves) are real outcomes.
- If the strategy is profitable on paper, the next step is **more paper trading and
  scrutiny**, not real money. Ask: is this edge real, or am I just seeing noise?

---

## The hard truths you should keep in front of you

1. **Polymarket is blocked for U.S. persons** (a CFTC settlement). Depending on
   where you live, using it may breach their terms or local law. Check first.
2. **Blofin** (from the other guide) is an offshore exchange with minimal
   regulatory protection. If money disappears there, there is usually no recourse.
3. **Never paste a real private key into a document or an AI chat.** One of your
   uploaded files literally contains a private key in the text and trains you to
   do exactly this. A private key *is* the whole wallet — anyone who sees it can
   drain it instantly and irreversibly. If that key is yours, move any funds off
   it and never reuse it.
4. **"Let an AI agent hold my keys and trade 24/7" is the opposite of control.**
   You wanted everything in your control — this sandbox is that version: you read
   every line, no keys, no auto-spending.
5. The influencer guides are **lead magnets**. The repeated "get the full code in
   my community / sign up to this exchange" is the actual business model. The
   "missing secret" you sensed is not a hidden profitable method — it's the funnel.

---

## Testing every aspect (do this in order)

1. **Health check — `python selftest.py`.** Confirms every mode runs clean
   (maths, AI plumbing, screener, copy + settlement, backtest, dashboard). Green
   board = the machine works. It says nothing about profit.
2. **Edge check — `python backtest.py --refresh --markets 300`.** The real test.
   Replays hundreds of settled markets. Does any strategy beat the random
   baseline by a wide margin, after fees?
3. **Tune honestly — `python backtest.py --sweep`.** Grid-searches strategy
   parameters. Read its warning: testing many variants makes the best one look
   good *by chance*. A variant only counts if it still wins on data you didn't
   use to pick it (re-run `--refresh` later and re-check the SAME variant).
4. **Forward-test — `python bot.py --cycles 50`** over days, then
   `python dashboard.py`. Watch settled win/loss and fees on live data.

### Knobs to tune (all in `config.py`)

`FEE_RATE`, `SLIPPAGE` (keep these realistic — don't flatter yourself),
`MIN_EDGE` (how much edge the value strategy needs before betting),
`MAX_POSITION_PCT` and the four risk limits, `MIN_VOLUME_USD`,
`MARKETS_PER_SCAN`. Change one, re-run the backtest, compare.

## The gate to live — all four, or don't

You said you'll go live only with what you've tested. Hold yourself to this:

1. **Proven edge.** A specific, fixed strategy beats the random baseline across
   300+ settled bets, net of fees, AND still wins on a later `--refresh` it wasn't
   tuned on. If your "best" only appears after a sweep, that's overfitting, not edge.
2. **Regulation.** Polymarket is blocked for U.S. persons. Confirm it's legal and
   permitted where you are before risking anything.
3. **Key security.** Live needs a real wallet key. It lives in a local `.env`,
   never in a doc, chat, or repo. A throwaway wallet with only what you can lose.
4. **Tiny first.** Start at the smallest size that clears the order minimum, with
   the kill switch and risk limits on, for weeks — before scaling anything.

If you can't tick all four honestly, the evidence says keep paper-trading. That's
not me blocking you — it's the same standard any disciplined trader holds.

## If you want to go further

I'm happy to build, test, and stress-test new strategy ideas in this safe sandbox
first, or to wire up real execution **once gate item 1 is genuinely met** for a
specific validated strategy. That's where the real learning is.

*This is educational software, not financial advice. I'm not a financial adviser.
Trading involves real risk of loss.*

---

## Contributing & testing

Contributions, bug reports, and test feedback are welcome. Quick version:

- **Test it / report bugs:** run `python selftest.py`, then open an
  [issue](../../issues) (bug or idea templates provided).
- **Contribute code:** fork → branch → make sure `python selftest.py` passes →
  open a pull request against `main`. See [CONTRIBUTING.md](CONTRIBUTING.md).
- **Ground rule:** this project stays honest — no profit guarantees, risk
  disclaimers stay, and safety defaults (dry-run, TLS verification, risk limits)
  are never weakened.

---

<div align="center">

Built by **[echonerve](https://echonerve.com)** · © 2026 echonerve · [MIT License](LICENSE)

</div>
