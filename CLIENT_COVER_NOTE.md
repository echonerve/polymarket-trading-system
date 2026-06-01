# Cover note to client (template)

> Fill in the [bracketed] parts. Keep the honesty — it's what protects you if the
> system loses money later. Delete this top blockquote before sending.

---

Hi [Client name],

Here is the Polymarket trading system, delivered and documented. This note sets
out exactly what it does, what I've verified, and what you need to do before
risking real money — so we're aligned from day one.

**What you're getting**

A modular trading framework: live + paper trading, a backtesting engine, several
strategies (including an optional AI decision step), copy-trading, risk controls
with a kill switch, a results dashboard, and a guarded live-execution module.
Full setup and operating instructions are in `HANDOFF.md`. The code is commented
throughout and uses the standard library only (the live module is the one add-on,
`py-clob-client`).

**What I tested, and what I found — honestly**

I validated the engineering: every module runs cleanly (`python selftest.py`
passes), and the backtester replays real, resolved markets.

I also ran the strategies against real historical data and a random baseline.
**On the data I tested, no strategy showed a reliable edge after fees** —
[paste your `backtest.py --refresh` results here, or: "results attached"]. This
matches well-established findings: liquid prediction markets are close to fairly
priced, and the optional AI has no predictive advantage over the market's own
odds. I want to be upfront: this is a capable, risk-controlled *framework*, not a
guaranteed profit system, and I'm not representing it as one.

**Before you trade real money — please do this in order**

1. `python backtest.py --refresh --markets 300` on your connection, and review
   whether any strategy beats the random baseline net of fees.
2. Run in paper mode (`python bot.py --cycles 50`) and review the dashboard.
3. If you go live: validate with `--live --dry-run` first, then arm with the
   smallest size (`LIVE_MAX_USD = 5`) and confirm a real order fills before
   scaling. I could not test live placement myself (the platform isn't reachable
   from my region), so first-fill validation has to happen on your side.

**Your responsibilities**

- Confirm Polymarket is legally permitted for you in your jurisdiction.
- Keep your wallet private key only in the local `.env`; use a dedicated wallet
  funded with only what you can afford to lose. Never disable TLS verification.
- All trading decisions and funds are under your control and at your risk.

I'm happy to walk you through setup on a call, and to support reasonable changes.
What I can't do is promise returns — anyone who does is not being straight with
you.

Best,
[Your name]

---

*Suggested scope line for your invoice/contract: "Delivery of a documented trading
software framework with backtesting and risk controls. No representation or
warranty as to profitability. Client is solely responsible for legal compliance
and for all trading decisions and losses."*

---

**echonerve** · https://echonerve.com
