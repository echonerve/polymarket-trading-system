"""
strategies.py — The "should we bet?" logic. Read this part carefully.

IMPORTANT, READ THIS:
A strategy is just a HYPOTHESIS about where the market is wrong. The sandbox
exists to TEST that hypothesis with fake money. None of these strategies is
known to be profitable. The honest expectation is that, after fees, a simple
hypothesis like the one below makes roughly zero or slightly negative money —
because the people on the other side of prediction markets are not fools.

If a strategy here ends up profitable in paper trading over hundreds of trades,
that is a *result worth investigating* — not proof, and not a reason to bet real
money yet. If it loses (likely), you learned that for free.

Each strategy returns a list of "signals". A signal is a plain dict:
    {"market": <market>, "outcome": "YES"|"NO", "price": <0..1>, "reason": str}
bot.py decides sizing and whether risk rules allow the trade.
"""

import config


# ---------------------------------------------------------------------------
# Strategy 1: a simple mean-reversion "value" hypothesis
# ---------------------------------------------------------------------------
#
# THE HYPOTHESIS (which may well be wrong): when a market's YES price jumps
# sharply in a short time, part of that move is overreaction and tends to come
# back. So if YES spiked UP a lot in the last hour, we guess "fair" is a bit
# LOWER than the current price, and consider buying NO; and vice versa.
#
# "Edge" = our guessed fair probability minus the price we'd actually pay.
# We only act if that edge clears MIN_EDGE (which must be bigger than fees).
#
# This is deliberately simple and transparent so you can see exactly why it
# fires. Swap in your own logic later — the rest of the bot won't change.

def value_signals(markets):
    signals = []
    for m in markets:
        move = m["one_hour_change"]            # e.g. +0.085 means YES rose 8.5c
        if abs(move) < 0.04:                   # ignore quiet markets
            continue

        # Guess a "fair" YES probability by fading ~half of the recent jump.
        fair_yes = m["yes_price"] - 0.5 * move
        fair_yes = min(0.97, max(0.03, fair_yes))

        # If we think fair YES is well ABOVE the ask, YES looks cheap -> buy YES.
        # If we think fair YES is well BELOW it, NO looks cheap -> buy NO.
        yes_ask = m["best_ask"] if m["best_ask"] > 0 else m["yes_price"]
        no_ask = (1 - m["best_bid"]) if m["best_bid"] > 0 else m["no_price"]

        edge_yes = fair_yes - yes_ask
        edge_no = (1 - fair_yes) - no_ask

        if edge_yes >= config.MIN_EDGE and edge_yes >= edge_no:
            signals.append({
                "market": m, "outcome": "YES", "price": yes_ask,
                "reason": f"mean-revert: fairYES~{fair_yes:.2f} vs ask {yes_ask:.2f}",
            })
        elif edge_no >= config.MIN_EDGE:
            signals.append({
                "market": m, "outcome": "NO", "price": no_ask,
                "reason": f"mean-revert: fairNO~{1-fair_yes:.2f} vs ask {no_ask:.2f}",
            })
    return signals


# ---------------------------------------------------------------------------
# Strategy 2: sum-to-one arbitrage DETECTOR
# ---------------------------------------------------------------------------
#
# THE IDEA: in a binary market, YES + NO must settle to exactly $1.00. If you
# could buy YES and NO together for LESS than $1.00, you'd lock in risk-free
# profit. The guides call this "100% win rate."
#
# THE REALITY (which this detector will show you): with public mid-price data,
# the executable cost of YES + NO is almost always >= $1.00 once you include the
# spread and fees. Real arbs exist for milliseconds and are taken by professional
# bots with co-located servers. This detector flags any apparent gap so you can
# SEE how rare/empty it is — that is the lesson, not a money machine.

def arbitrage_signals(markets):
    signals = []
    for m in markets:
        # Approximate the price you'd actually PAY to take each side.
        yes_cost = (m["best_ask"] if m["best_ask"] > 0 else m["yes_price"])
        no_cost = ((1 - m["best_bid"]) if m["best_bid"] > 0 else m["no_price"])
        combined = yes_cost + no_cost

        # Must beat $1.00 by more than the round-trip fee to be real profit.
        fee_drag = 2 * config.FEE_RATE
        if combined < (1.0 - fee_drag - 0.005):
            profit = 1.0 - combined - fee_drag
            signals.append({
                "market": m, "outcome": "ARB_PAIR", "price": combined,
                "reason": f"sum-to-one gap: pay {combined:.3f}, ~{profit:.3f} edge",
            })
    return signals


def generate_signals(markets):
    """Run all enabled strategies and return the combined signal list."""
    signals = []
    if config.ENABLE_VALUE_STRATEGY:
        signals += value_signals(markets)
    if config.ENABLE_ARBITRAGE:
        signals += arbitrage_signals(markets)
    return signals
