"""
journal.py — Writes every simulated trade to a CSV you can open in Excel.

The guides say "keep a trading journal." This does it automatically. One row per
simulated fill, so afterwards you can check the bot's claims yourself instead of
trusting a summary line. Honesty you can audit.
"""

import csv
import os
from datetime import datetime, timezone


class Journal:
    HEADER = [
        "timestamp", "action", "market_id", "question", "outcome",
        "price", "size_usd", "shares", "fee", "reason", "equity_after",
    ]

    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        # Write the header once, if the file is new/empty.
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(self.HEADER)

    def log(self, action, market=None, outcome="", price=0.0, size_usd=0.0,
            shares=0.0, fee=0.0, reason="", equity_after=0.0):
        row = [
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            action,
            market.get("id", "") if market else "",
            (market.get("question", "") if market else "")[:80],
            outcome,
            round(price, 4),
            round(size_usd, 2),
            round(shares, 2),
            round(fee, 4),
            reason,
            round(equity_after, 2),
        ]
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)
