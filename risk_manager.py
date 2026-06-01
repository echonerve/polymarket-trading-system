"""
risk_manager.py — The brakes. Decides whether a proposed trade is allowed.

This is the part the marketing guides rush past. It is the most important file.
A bot with no brakes doesn't make you money faster — it loses it faster.

The four protection layers (all enforced here, all configurable in config.py):

  Daily stop     : down 5% on the day        -> no more trades today
  Monthly stop   : down 15% on the month     -> position sizes cut in half
  Drawdown halt  : down 25% from your peak    -> hard stop, manual restart
  Total-loss halt: down 40% from the start    -> permanent kill switch

Plus: a hard cap on trades per day and a cap on how big any single bet can be.
"""

import config


class RiskManager:
    def __init__(self, starting_balance):
        self.starting_balance = starting_balance
        self.peak_equity = starting_balance
        self.day_start_equity = starting_balance
        self.month_start_equity = starting_balance
        self.trades_today = 0
        self.halted = False          # set by drawdown / total-loss; needs restart
        self.halt_reason = ""

    # Called once per simulated day rollover.
    def start_new_day(self, equity):
        self.day_start_equity = equity
        self.trades_today = 0

    def start_new_month(self, equity):
        self.month_start_equity = equity

    def update_peak(self, equity):
        if equity > self.peak_equity:
            self.peak_equity = equity

    def can_trade(self, equity):
        """Return (allowed: bool, reason: str). Checks the hard halts first."""
        self.update_peak(equity)

        if self.halted:
            return False, f"HALTED: {self.halt_reason}"

        # Total-loss kill switch (permanent for this run).
        if equity <= self.starting_balance * (1 - config.TOTAL_LOSS_HALT_PCT):
            self.halted = True
            self.halt_reason = "total-loss halt (down 40% from start)"
            return False, self.halt_reason

        # Drawdown halt (permanent for this run).
        drawdown = (self.peak_equity - equity) / self.peak_equity if self.peak_equity else 0
        if drawdown >= config.DRAWDOWN_HALT_PCT:
            self.halted = True
            self.halt_reason = f"drawdown halt (down {drawdown*100:.0f}% from peak)"
            return False, self.halt_reason

        # Daily stop (resets next day).
        day_loss = (self.day_start_equity - equity) / self.day_start_equity
        if day_loss >= config.DAILY_STOP_PCT:
            return False, f"daily stop (down {day_loss*100:.1f}% today)"

        # Trade-count cap.
        if self.trades_today >= config.MAX_TRADES_PER_DAY:
            return False, "max trades for the day reached"

        return True, "ok"

    def position_size(self, equity):
        """How many dollars we're allowed to stake on the next single trade."""
        size = equity * config.MAX_POSITION_PCT

        # Monthly stop: if down 15% on the month, halve sizing.
        month_loss = (self.month_start_equity - equity) / self.month_start_equity
        if month_loss >= config.MONTHLY_STOP_PCT:
            size *= 0.5
        return size

    def record_trade(self):
        self.trades_today += 1
