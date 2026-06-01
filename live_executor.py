"""
live_executor.py — The ONLY part of this project that can touch real money.

It places real orders on Polymarket through the official py-clob-client. It is
built to be safe by default and loud about risk:

  - DRY-RUN by default: it logs the exact order it WOULD place and sends nothing.
  - Real orders require BOTH the --live flag AND an explicit arming token in .env
    (LIVE_ARMED=YES). Two independent switches, on purpose.
  - TLS certificate verification stays ON. We never disable it. If you ever see a
    certificate error, that means the connection is being intercepted — stop,
    don't bypass it (see HANDOFF.md).
  - Every order is hard-capped at config.LIVE_MAX_USD, no matter what the strategy
    asks for.
  - The wallet key is read only from the environment (.env), never hard-coded.

This module is intentionally only usable where Polymarket is permitted, by whoever
runs it. It cannot, and is not meant to, bypass any regional restriction.

IMPORTANT: live order placement has NOT been (and cannot be) tested from the
author's environment. Whoever runs it live MUST validate with the smallest
possible size first. See HANDOFF.md.
"""

import os

import config


class LiveExecutor:
    def __init__(self, dry_run=True):
        # Live sending requires dry_run=False AND the arming token in the env.
        self.armed = (not dry_run) and (os.environ.get("LIVE_ARMED", "").upper() == "YES")
        self.dry_run = not self.armed
        self.client = None
        self._ready = False

    # -- connection ---------------------------------------------------------

    def connect(self):
        """Initialise the Polymarket client. Lazy-imports py-clob-client so the
        rest of the project (and dry-run) works even if it isn't installed."""
        if self.dry_run:
            print("  [live] DRY-RUN — no connection, no orders will be sent.")
            self._ready = True
            return

        pk = os.environ.get("POLYMARKET_PK")
        funder = os.environ.get("FUNDER_ADDRESS")
        if not pk or not funder:
            raise RuntimeError("Live mode needs POLYMARKET_PK and FUNDER_ADDRESS in .env")

        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import ApiCreds  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "py-clob-client is not installed. Run: pip install py-clob-client"
            ) from exc

        sig_type = int(os.environ.get("SIGNATURE_TYPE", "1"))  # 0=MetaMask,1=email,2=safe
        # NOTE: default SSL verification is left ON by the client. Do not disable it.
        self.client = ClobClient(
            host="https://clob.polymarket.com",
            key=pk,
            chain_id=137,                 # Polygon mainnet
            signature_type=sig_type,
            funder=funder,
        )
        creds = self.client.create_or_derive_api_key()
        self.client.set_api_creds(creds)
        self._ready = True
        print("  [live] Connected to Polymarket CLOB. LIVE ORDERS ARE ARMED.")

    # -- account ------------------------------------------------------------

    def balance_usdc(self):
        if self.dry_run or not self.client:
            return None
        from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
        bal = self.client.get_balance_allowance(
            BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        )
        return int(bal["balance"]) / 1e6

    # -- orders -------------------------------------------------------------

    def place_market_buy(self, token_id, size_usd, label=""):
        """Buy `size_usd` of an outcome token. Returns a result dict.

        In dry-run it logs and returns a simulated acknowledgement. Live, it
        sends a Fill-or-Kill market order, capped at config.LIVE_MAX_USD.
        """
        size_usd = min(size_usd, config.LIVE_MAX_USD)
        if size_usd < 1:
            return {"status": "skipped", "reason": "below $1", "size": size_usd}

        if self.dry_run:
            print(f"  [DRY-RUN] would BUY ${size_usd:.2f} of {label or token_id[:10]} (FOK)")
            return {"status": "dry_run", "size": size_usd, "token": token_id}

        from py_clob_client.clob_types import MarketOrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY
        order = MarketOrderArgs(token_id=token_id, amount=size_usd, side=BUY,
                                order_type=OrderType.FOK)
        signed = self.client.create_market_order(order)
        resp = self.client.post_order(signed, OrderType.FOK)
        print(f"  [LIVE] BUY ${size_usd:.2f} of {label or token_id[:10]} -> {resp}")
        return {"status": "sent", "size": size_usd, "token": token_id, "response": resp}
