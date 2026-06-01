"""
copy_trader.py — Watch real Polymarket wallets and SIMULATE copying their trades.

WHAT THIS DOES
--------------
- Reads the recent trades of one or more real wallets from Polymarket's public
  data API (read-only, no keys). You get wallet addresses from the public
  leaderboard at https://polymarket.com/leaderboard.
- When a watched wallet makes a NEW buy, it simulates copying it into your
  pretend portfolio, sized as a small fraction of your equity (not theirs).
- It deliberately fills you at a WORSE price than the whale got, to model the
  real-world lag: by the time a public API shows you their trade, the price has
  already moved. This is the single biggest reason naive copy-trading loses
  money, and the sandbox makes that cost visible instead of hiding it.

WHAT THIS IS NOT
----------------
- It is not a real copier. No order is ever placed. No key is ever used.
- It does not auto-resolve positions; copy positions stay open and are marked at
  their entry price. The point of this module is to show you WHAT you'd be
  copying and HOW MUCH the lag + fees cost you — not to promise a profit.

WHY THE HONEST VERSION MATTERS
------------------------------
The guide says "piggyback on the best traders." Reality: whales often trade
sizes and at prices you can't match, sometimes they're selling into your buy,
and the leaderboard is survivorship-biased (you see this month's winners, not
the blown-up accounts). Watch the lag cost add up here before trusting any of it.
"""

import json
import random
import urllib.request
import urllib.parse

import config
from market_resolution import get_resolution

TRADES_URL = "https://data-api.polymarket.com/trades"


# ---------------------------------------------------------------------------
# Fetching a wallet's recent trades (LIVE, read-only)
# ---------------------------------------------------------------------------

def fetch_wallet_trades(wallet, limit=20):
    """Return a wallet's most recent trades from the public data API.

    Each normalised trade is a plain dict the simulator understands. Raises on
    network failure so the caller can fall back to the offline feed.
    """
    params = urllib.parse.urlencode({"user": wallet, "limit": limit})
    req = urllib.request.Request(
        f"{TRADES_URL}?{params}",
        headers={"User-Agent": "paper-sandbox/1.0 (read-only)"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    trades = []
    for t in raw:
        trades.append(_normalise_trade(t))
    return trades


def _normalise_trade(t):
    """Map one raw data-api trade record into our small dict."""
    return {
        "tx": t.get("transactionHash", ""),          # unique id, dedupe key
        "wallet": t.get("proxyWallet", ""),
        "side": t.get("side", "BUY"),                # BUY or SELL
        "token": str(t.get("asset", "")),            # outcome token id
        "condition_id": t.get("conditionId", ""),    # market id
        "size_shares": float(t.get("size", 0) or 0),
        "price": float(t.get("price", 0) or 0),      # 0..1 they paid
        "title": t.get("title", "(unknown market)"),
        "outcome": t.get("outcome", "?"),            # "Yes"/"No"/"Up"/...
        "trader": t.get("pseudonym") or t.get("name") or "whale",
    }


# ---------------------------------------------------------------------------
# Offline synthetic trade feed (so the module runs with no network)
# ---------------------------------------------------------------------------

_SYNTH_TITLES = [
    ("Will it rain in London tomorrow?", "Yes"),
    ("Team A wins the final?", "No"),
    ("Bitcoin above $X by Friday?", "Yes"),
    ("Rate cut at next meeting?", "No"),
]
_synth_counter = [0]


def fetch_offline_trades(wallet, limit=20):
    """Make up a few plausible new trades for a fake whale each poll."""
    out = []
    for _ in range(random.randint(0, 3)):                 # 0-3 new trades/poll
        _synth_counter[0] += 1
        title, outcome = random.choice(_SYNTH_TITLES)
        out.append({
            "tx": f"sim-tx-{wallet[-4:]}-{_synth_counter[0]}",
            "wallet": wallet,
            "side": "BUY",
            "token": f"tok-{abs(hash(title)) % 10000}",
            "condition_id": f"cond-{abs(hash(title)) % 10000}",
            "size_shares": random.choice([50, 120, 300, 800]),
            "price": round(random.uniform(0.2, 0.8), 2),
            "title": title,
            "outcome": outcome,
            "trader": "Vast-Mystery",
        })
    return out


# ---------------------------------------------------------------------------
# The simulator
# ---------------------------------------------------------------------------

class CopyTrader:
    def __init__(self, portfolio, risk, journal, wallets, source="live"):
        self.portfolio = portfolio
        self.risk = risk
        self.journal = journal
        self.wallets = wallets
        self.source = source
        self.seen = set()          # transaction hashes already processed
        self.copied = 0
        self.lag_cost = 0.0        # total $ lost purely to copy lag (modeled)
        self.settled = 0           # copy positions that have since resolved

    def _get_trades(self, wallet):
        if self.source == "offline":
            return fetch_offline_trades(wallet)
        try:
            return fetch_wallet_trades(wallet)
        except Exception as exc:  # any failure -> offline, never crash
            print(f"  [copy] live fetch failed for {wallet[:10]}… ({exc}); using offline feed.")
            return fetch_offline_trades(wallet)

    def poll_once(self):
        """One sweep of all watched wallets. Returns a short status string."""
        new_copies = 0
        for wallet in self.wallets:
            for tr in self._get_trades(wallet):
                if tr["tx"] in self.seen:
                    continue
                self.seen.add(tr["tx"])
                if tr["side"] != "BUY":
                    continue                       # this sim only copies buys
                if self._copy(tr):
                    new_copies += 1
        return f"copied {new_copies} new trade(s)"

    def settle_resolved(self):
        """Resolve any open copy position whose market has now settled.

        Looks each open position's market up by conditionId. If it has resolved,
        we pay out 1.00/share if our outcome won, 0.00 if it lost — turning paper
        positions into REAL (still virtual) win/loss numbers. Returns how many
        positions settled this sweep.
        """
        settled_now = 0
        # Copy a snapshot of positions because settling mutates the dict.
        for pos in list(self.portfolio.positions.values()):
            res = get_resolution(pos.market_id, source=self.source)
            if not res["closed"] or res["winner"] is None:
                continue
            won = (str(pos.outcome).lower() == str(res["winner"]).lower())
            pnl = self.portfolio.settle(pos.market_id, pos.outcome, won)
            self.settled += 1
            settled_now += 1
            self.journal.log(
                "SETTLE",
                market={"id": pos.market_id, "question": pos.question},
                outcome=pos.outcome, price=(1.0 if won else 0.0),
                size_usd=pnl,
                reason=f"resolved winner={res['winner']} -> {'WON' if won else 'LOST'}",
                equity_after=self.portfolio.cash,
            )
        return settled_now

    def _copy(self, tr):
        """Simulate copying one whale trade into the paper portfolio."""
        equity = self.portfolio.equity(lambda pos: pos.avg_price)
        allowed, reason = self.risk.can_trade(equity)
        if not allowed:
            return False

        # Size from YOUR equity, capped — never mirror the whale's raw size.
        size = min(
            self.risk.position_size(equity) * 1.0,
            equity * config.COPY_RATIO,
            config.COPY_MAX_USD,
        )
        if size < 1:
            return False

        # Build a minimal "market" dict so the portfolio can hold the position.
        market = {
            "id": tr["condition_id"],
            "question": tr["title"],
            "yes_token": tr["token"],
            "no_token": tr["token"],
        }

        # The honest part: we fill at the whale's price PLUS a lag penalty.
        pos = self.portfolio.buy(
            market, tr["outcome"], tr["price"], size,
            extra_slippage=config.COPY_LAG_SLIPPAGE,
        )
        if pos is None:
            return False

        self.risk.record_trade()
        self.copied += 1
        # The lag penalty in dollars = shares * extra cents paid vs the whale.
        shares = size / max(tr["price"] + config.SLIPPAGE + config.COPY_LAG_SLIPPAGE, 0.01)
        self.lag_cost += shares * config.COPY_LAG_SLIPPAGE
        fee = size * config.FEE_RATE

        self.journal.log(
            "COPY_BUY", market=market, outcome=tr["outcome"],
            price=tr["price"], size_usd=size, shares=shares, fee=fee,
            reason=f"copy {tr['trader']} ({tr['wallet'][:8]}…) +{config.COPY_LAG_SLIPPAGE:.2f} lag",
            equity_after=self.portfolio.equity(lambda p: p.avg_price),
        )
        return True
