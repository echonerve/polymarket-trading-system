"""
bot.py — The main program. Ties everything together and runs the simulation.

WHAT THIS CAN AND CANNOT DO
---------------------------
CAN : read public Polymarket prices, decide on (pretend) trades, track a virtual
      balance, log every trade, and print honest performance numbers.
CANNOT: place a real order, touch a wallet, hold a private key, or move one cent
      of real money. There is no exchange connection anywhere in this project.

HOW TO RUN
----------
    python bot.py                 # one scan of LIVE markets (maths strategy)
    python bot.py --cycles 20     # 20 scans, ~CYCLE_SECONDS apart
    python bot.py --offline       # synthetic feed, no network
    python bot.py --backtest 200  # fast simulation, no waiting

    python bot.py --ai            # use the AI brain for decisions (needs a key)
    python bot.py --ai-mock --backtest 30   # demo the AI plumbing, no API key

    python bot.py --copy          # COPY-TRADING: watch real wallets, simulate copies
    python bot.py --copy --cycles 10        # poll the wallets 10 times

Kill switch: press Ctrl+C any time. The risk manager also halts on big losses.
"""

import argparse
import time

import config
from polymarket_data import get_markets
from portfolio import Portfolio
from risk_manager import RiskManager
from journal import Journal
from strategies import generate_signals
import ai_engine
from copy_trader import CopyTrader


def eligible(market):
    """Filter out markets we shouldn't touch (thin, about to resolve, closed)."""
    return (
        market["accepting_orders"]
        and not market["closed"]
        and market["volume"] >= config.MIN_VOLUME_USD
        and market["days_left"] >= config.MIN_DAYS_TO_RESOLUTION
    )


def price_lookup_factory(latest_prices):
    """Build the function Portfolio uses to mark positions to current prices."""
    def lookup(position):
        prices = latest_prices.get(position.market_id)
        if prices and position.outcome in prices:
            return prices[position.outcome]
        return position.avg_price
    return lookup


# ---------------------------------------------------------------------------
# AI decision path: turn AI verdicts into the same "signal" shape as strategies
# ---------------------------------------------------------------------------

def ai_signals(markets, use_mock):
    decide = ai_engine.mock_decide if use_mock else ai_engine.decide
    signals = []
    for m in markets:
        verdict = decide(m)
        if verdict["decision"] == "NO_TRADE":
            continue
        if verdict.get("confidence", 0) < config.AI_MIN_CONFIDENCE:
            continue
        if verdict["decision"] == "BUY_YES":
            outcome, price = "YES", (m["best_ask"] or m["yes_price"])
        else:  # BUY_NO
            outcome, price = "NO", ((1 - m["best_bid"]) if m["best_bid"] else m["no_price"])
        signals.append({
            "market": m, "outcome": outcome, "price": price,
            "reason": f"AI({verdict.get('confidence')}%): {verdict.get('reasoning', '')[:60]}",
        })
    return signals


def run_strategy_cycle(markets, portfolio, risk, jrnl, latest_prices, mode, use_mock, executor=None):
    """One scan: refresh prices, get signals (maths or AI), place allowed bets.

    If `executor` is provided, each paper buy is ALSO routed to it — dry-run logs
    the intended order; live (armed) sends a real, size-capped order."""
    for m in markets:
        latest_prices[m["id"]] = {"YES": m["yes_price"], "NO": m["no_price"]}

    lookup = price_lookup_factory(latest_prices)
    allowed, reason = risk.can_trade(portfolio.equity(lookup))
    if not allowed:
        return reason

    tradable = [m for m in markets if eligible(m)]
    signals = ai_signals(tradable, use_mock) if mode == "ai" else generate_signals(tradable)

    placed = 0
    for sig in signals:
        allowed, reason = risk.can_trade(portfolio.equity(lookup))
        if not allowed:
            return reason
        size = risk.position_size(portfolio.equity(lookup))

        if sig["outcome"] == "ARB_PAIR":
            jrnl.log("ARB_DETECTED", market=sig["market"], price=sig["price"],
                     reason=sig["reason"], equity_after=portfolio.equity(lookup))
            continue

        pos = portfolio.buy(sig["market"], sig["outcome"], sig["price"], size)
        if pos is None:
            continue
        risk.record_trade()
        jrnl.log("BUY", market=sig["market"], outcome=sig["outcome"],
                 price=sig["price"], size_usd=size,
                 shares=size / max(sig["price"], 0.01),
                 fee=size * config.FEE_RATE, reason=sig["reason"],
                 equity_after=portfolio.equity(lookup))
        placed += 1

        # Mirror the trade to the live executor (dry-run logs; armed sends real).
        if executor is not None:
            mkt = sig["market"]
            token = mkt.get("yes_token") if sig["outcome"] == "YES" else mkt.get("no_token")
            if token:
                executor.place_market_buy(token, size, label=mkt.get("question", "")[:40])
    return f"placed {placed} paper trade(s)"


def print_report(portfolio, latest_prices, copier=None):
    lookup = price_lookup_factory(latest_prices) if latest_prices else (lambda p: p.avg_price)
    s = portfolio.summary(lookup)
    print("\n" + "=" * 60)
    print("  PAPER-TRADING REPORT  (all amounts are virtual)")
    print("=" * 60)
    print(f"  Starting balance : ${s['starting_balance']:.2f}")
    print(f"  Current equity   : ${s['equity']:.2f}")
    print(f"  Total P&L        : ${s['total_pnl']:.2f}  ({s['total_pnl_pct']:+.2f}%)")
    print(f"   - cash          : ${s['cash']:.2f}")
    print(f"   - open positions: {s['open_positions']}  worth ${s['open_value']:.2f}")
    print(f"  Realized P&L     : ${s['realized_pnl']:.2f}")
    print(f"  Fees paid        : ${s['fees_paid']:.2f}   <- the house's cut")
    print(f"  Settled W/L      : {s['settled_wins']}W / {s['settled_losses']}L"
          f"  (win rate {s['win_rate_pct']}%)")
    if copier is not None:
        print(f"  Copied trades    : {copier.copied}")
        print(f"  Lost to copy lag : ${copier.lag_cost:.2f}   <- cost of being late")
    print("=" * 60)
    print("  Reminder: paper results are NOT a promise of real results.")
    print("  Most prediction-market traders lose money. Risk nothing you")
    print("  can't afford to lose, and never with money you need.\n")


def main():
    p = argparse.ArgumentParser(description="Polymarket PAPER-trading sandbox (simulation only)")
    p.add_argument("--offline", action="store_true", help="synthetic feed, no network")
    p.add_argument("--cycles", type=int, default=1, help="number of scans/polls")
    p.add_argument("--backtest", type=int, default=0, help="fast cycles, no sleeping (offline)")
    p.add_argument("--ai", action="store_true", help="use the AI brain (needs an API key)")
    p.add_argument("--ai-mock", action="store_true", help="demo the AI path with no API key")
    p.add_argument("--copy", action="store_true", help="copy-trading mode: watch real wallets")
    p.add_argument("--screen", action="store_true", help="rank the wallets in config.py, then exit")
    p.add_argument("--live", action="store_true", help="route trades to Polymarket (DRY-RUN unless LIVE_ARMED=YES in .env)")
    p.add_argument("--dry-run", action="store_true", help="with --live: force dry-run (log orders, send nothing)")
    args = p.parse_args()

    source = "offline" if args.offline else config.DATA_SOURCE
    cycles = args.backtest if args.backtest else args.cycles
    fast = bool(args.backtest)
    if fast:
        source = "offline"

    # ----- WALLET SCREENER (no portfolio needed) -----------------------------
    if args.screen:
        import screener
        print(f"Screening {len(config.TARGET_WALLETS)} wallet(s) | source={source}")
        screener.screen(config.TARGET_WALLETS, source=source)
        return

    portfolio = Portfolio(config.STARTING_BALANCE_USD)
    risk = RiskManager(config.STARTING_BALANCE_USD)
    jrnl = Journal(config.JOURNAL_CSV)
    latest_prices = {}

    # ----- COPY-TRADING MODE -------------------------------------------------
    if args.copy:
        copier = CopyTrader(portfolio, risk, jrnl, config.TARGET_WALLETS, source=source)
        print(f"Copy-trading sandbox | wallets={len(config.TARGET_WALLETS)} | source={source} | cycles={cycles}")
        print("Watching real leaderboard wallets and SIMULATING copies. Ctrl+C to stop.")
        try:
            for i in range(cycles):
                status = copier.poll_once()
                settled_now = copier.settle_resolved()   # realize any resolved bets
                eq = portfolio.equity(lambda pos: pos.avg_price)
                extra = f" | settled {settled_now}" if settled_now else ""
                print(f"  poll {i+1}/{cycles} | equity=${eq:.2f} | {status}{extra}")
                if risk.halted:
                    print(f"  RISK HALT: {risk.halt_reason} — stopping.")
                    break
                if not fast and i < cycles - 1:
                    time.sleep(config.COPY_POLL_SECONDS)
        except KeyboardInterrupt:
            print("\n  Kill switch pressed — stopping now.")
        print_report(portfolio, latest_prices, copier=copier)
        return

    # ----- STRATEGY / AI MODE ------------------------------------------------
    mode = "ai" if (args.ai or args.ai_mock) else "maths"
    use_mock = args.ai_mock
    if mode == "ai" and not use_mock and not ai_engine.ai_available():
        print("  [ai] No API key found (.env). Falling back to the maths strategy.")
        mode = "maths"

    # Optional live execution. Defaults to DRY-RUN; real orders need --live,
    # NOT --dry-run, AND LIVE_ARMED=YES in .env (checked inside LiveExecutor).
    executor = None
    if args.live:
        from live_executor import LiveExecutor
        executor = LiveExecutor(dry_run=args.dry_run)
        try:
            executor.connect()
        except Exception as exc:
            print(f"  [live] could not arm live execution ({exc}); staying paper-only.")
            executor = None
        else:
            if not executor.dry_run:
                bal = executor.balance_usdc()
                print(f"  [live] ARMED. Wallet USDC: ${bal:.2f}. Orders capped at ${config.LIVE_MAX_USD}.")

    print(f"Paper sandbox | mode={mode}{' (mock)' if use_mock else ''} | source={source} | cycles={cycles}")
    print("Press Ctrl+C at any time to stop (kill switch).")

    try:
        for i in range(cycles):
            markets = get_markets(source=source, limit=config.MARKETS_PER_SCAN)
            status = run_strategy_cycle(markets, portfolio, risk, jrnl,
                                        latest_prices, mode, use_mock, executor=executor)
            eq = portfolio.equity(price_lookup_factory(latest_prices))
            print(f"  cycle {i+1}/{cycles} | markets={len(markets)} | equity=${eq:.2f} | {status}")
            if risk.halted:
                print(f"  RISK HALT: {risk.halt_reason} — stopping.")
                break
            if not fast and i < cycles - 1:
                time.sleep(config.CYCLE_SECONDS)
    except KeyboardInterrupt:
        print("\n  Kill switch pressed — stopping now.")

    print_report(portfolio, latest_prices)


if __name__ == "__main__":
    main()
