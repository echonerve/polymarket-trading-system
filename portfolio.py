"""
portfolio.py — The pretend money: balance, open positions, and P&L.

NOTHING here connects to an exchange or a wallet. "Buying" just subtracts from a
number in memory. "Selling"/settlement adds to it. That is the whole point: you
get to see how a strategy would have done before a single real dollar is at risk.

Key ideas
---------
- A *share* of an outcome costs its price (0..1 USDC) and pays out 1 USDC if that
  outcome wins, or 0 if it loses. So if you buy YES at 0.40 and YES wins, each
  share returns 1.00 (a 0.60 profit). If it loses, the 0.40 is gone.
- We charge FEE_RATE on the cost of every fill, and assume SLIPPAGE so you fill
  slightly worse than the quoted price. Both make the sandbox honest, not rosy.
"""

import config


class Position:
    """One open bet: some shares of one outcome (YES or NO) in one market."""

    def __init__(self, market_id, question, outcome, token, shares, avg_price):
        self.market_id = market_id
        self.question = question
        self.outcome = outcome          # "YES" or "NO"
        self.token = token
        self.shares = shares            # number of outcome shares held
        self.avg_price = avg_price      # average price paid per share (0..1)

    def cost_basis(self):
        return self.shares * self.avg_price

    def market_value(self, current_price):
        """What the position is worth right now at the current outcome price."""
        return self.shares * current_price


class Portfolio:
    def __init__(self, starting_balance):
        self.cash = starting_balance            # uninvested pretend USDC
        self.starting_balance = starting_balance
        self.positions = {}                     # key -> Position
        self.fees_paid = 0.0
        self.realized_pnl = 0.0
        self.wins = 0
        self.losses = 0

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _key(market_id, outcome):
        return f"{market_id}:{outcome}"

    def open_value(self, price_lookup):
        """Total current value of all open positions.

        price_lookup(position) -> current price of that outcome (0..1).
        """
        total = 0.0
        for pos in self.positions.values():
            total += pos.market_value(price_lookup(pos))
        return total

    def equity(self, price_lookup):
        """Everything you'd have if you marked positions to current prices."""
        return self.cash + self.open_value(price_lookup)

    # -- actions ------------------------------------------------------------

    def buy(self, market, outcome, price, size_usd, extra_slippage=0.0):
        """Simulate buying `size_usd` worth of an outcome at `price`.

        Applies slippage and fee. `extra_slippage` models *additional* cost on
        top of the normal amount — the copy-trader uses it to represent the lag
        between a whale's trade and yours (you fill at a worse price than they
        got). Returns the Position, or None if not enough cash. Records nothing
        to disk — the caller (bot.py / copy_trader.py) logs to the journal.
        """
        fill_price = min(0.99, price + config.SLIPPAGE + extra_slippage)  # pay worse
        if fill_price <= 0:
            return None

        fee = size_usd * config.FEE_RATE
        total_cost = size_usd + fee
        if total_cost > self.cash:
            return None                                   # can't afford it

        shares = size_usd / fill_price
        self.cash -= total_cost
        self.fees_paid += fee

        token = market["yes_token"] if outcome == "YES" else market["no_token"]
        key = self._key(market["id"], outcome)
        if key in self.positions:
            # Average into the existing position.
            pos = self.positions[key]
            new_shares = pos.shares + shares
            pos.avg_price = (pos.cost_basis() + shares * fill_price) / new_shares
            pos.shares = new_shares
        else:
            pos = Position(market["id"], market["question"], outcome,
                           token, shares, fill_price)
            self.positions[key] = pos
        return pos

    def settle(self, market_id, outcome, won):
        """Resolve a position when its market closes.

        won=True  -> each share pays 1.00 USDC.
        won=False -> each share pays 0.00 (stake lost).
        """
        key = self._key(market_id, outcome)
        pos = self.positions.pop(key, None)
        if pos is None:
            return 0.0

        payout = pos.shares * (1.0 if won else 0.0)
        pnl = payout - pos.cost_basis()
        self.cash += payout
        self.realized_pnl += pnl
        if pnl >= 0:
            self.wins += 1
        else:
            self.losses += 1
        return pnl

    # -- reporting ----------------------------------------------------------

    def win_rate(self):
        total = self.wins + self.losses
        return (self.wins / total * 100) if total else 0.0

    def summary(self, price_lookup):
        eq = self.equity(price_lookup)
        return {
            "cash": round(self.cash, 2),
            "open_positions": len(self.positions),
            "open_value": round(self.open_value(price_lookup), 2),
            "equity": round(eq, 2),
            "starting_balance": round(self.starting_balance, 2),
            "total_pnl": round(eq - self.starting_balance, 2),
            "total_pnl_pct": round((eq - self.starting_balance)
                                   / self.starting_balance * 100, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "fees_paid": round(self.fees_paid, 2),
            "settled_wins": self.wins,
            "settled_losses": self.losses,
            "win_rate_pct": round(self.win_rate(), 1),
        }
