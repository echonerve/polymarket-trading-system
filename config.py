"""
config.py — All the knobs for the paper-trading sandbox, in one place.

Everything here is plain data. Change a number, save, re-run. Nothing in this
file can touch real money: the whole project is simulation-only.

Read the comment next to each setting so you understand exactly what it does.
"""

# ----------------------------------------------------------------------------
# MONEY (all virtual — these are pretend dollars)
# ----------------------------------------------------------------------------

STARTING_BALANCE_USD = 500.0   # How much pretend USDC the bot starts with.

# Polymarket has begun charging a taker fee. Historically it was 0%. The exact
# rate varies by market and changes over time, so we model it as a single
# configurable number and apply it to every simulated fill. We deliberately
# keep it slightly pessimistic — a realistic sandbox should not flatter you.
FEE_RATE = 0.02                # 2% fee charged on the value of each fill.

# When you "take" liquidity you usually pay a bit worse than the quoted price.
# This models that. 0.01 = you assume you fill one cent worse than best ask.
SLIPPAGE = 0.01

# ----------------------------------------------------------------------------
# WHAT TO TRADE
# ----------------------------------------------------------------------------

MARKETS_PER_SCAN = 40          # How many top markets to pull each cycle.
MIN_VOLUME_USD = 10_000        # Ignore thin markets (you couldn't exit them).
MIN_DAYS_TO_RESOLUTION = 1     # Skip markets resolving within ~1 day (volatile).

# ----------------------------------------------------------------------------
# POSITION SIZING & RISK (mirrors the rules from the guides, enforced in code)
# ----------------------------------------------------------------------------

MAX_POSITION_PCT = 0.02        # Never stake more than 2% of equity on one bet.
MAX_TRADES_PER_DAY = 20        # Hard cap on simulated trades per simulated day.

DAILY_STOP_PCT = 0.05          # Down 5% in a day  -> stop trading that day.
MONTHLY_STOP_PCT = 0.15        # Down 15% in a month -> halve position sizes.
DRAWDOWN_HALT_PCT = 0.25       # Down 25% from peak -> halt, require restart.
TOTAL_LOSS_HALT_PCT = 0.40     # Down 40% total -> permanent stop (kill switch).

# ----------------------------------------------------------------------------
# STRATEGY SWITCHES
# ----------------------------------------------------------------------------

ENABLE_VALUE_STRATEGY = True   # The "edge" heuristic (see strategies.py).
ENABLE_ARBITRAGE = True        # Sum-to-one arbitrage *detector*.

# Minimum modeled edge before the value strategy will place a paper bet.
# Edge = (our estimated fair probability) - (price we'd pay). Must clear fees.
MIN_EDGE = 0.04                # 4 cents of edge required.

# ----------------------------------------------------------------------------
# LOOP TIMING
# ----------------------------------------------------------------------------

CYCLE_SECONDS = 30             # Seconds between scans when running live-loop.
DATA_SOURCE = "live"           # "live" = real Polymarket data; "offline" = synthetic.

# ----------------------------------------------------------------------------
# FILES
# ----------------------------------------------------------------------------

JOURNAL_CSV = "journal/trades.csv"   # Every simulated trade is logged here.
STATE_JSON = "journal/state.json"    # Portfolio snapshot, so runs can resume.

# ----------------------------------------------------------------------------
# COPY-TRADING (the `--copy` mode in bot.py)
# ----------------------------------------------------------------------------
# Wallet addresses to watch. Get real, profitable ones from the public
# leaderboard: https://polymarket.com/leaderboard  (copy the wallet address).
# These two defaults are real wallets seen in the live trade feed, so the demo
# works out of the box — they are NOT a recommendation, just examples.
TARGET_WALLETS = [
    "0x05a5741a0221a2ece7c92669b5856196c60a40ae",
    "0x36f5f90ebbdba50c5534dc02357927de11674c9d",
]

COPY_RATIO = 0.05          # Copy at 5% of YOUR equity per trade (never theirs).
COPY_MAX_USD = 25          # Hard cap on any single copied position.
COPY_LAG_SLIPPAGE = 0.02   # Extra cents you pay vs the whale, modeling your lag.
COPY_POLL_SECONDS = 15     # Seconds between leaderboard sweeps in live copy mode.

# ----------------------------------------------------------------------------
# WALLET SCREENER (the `--screen` mode in bot.py)
# ----------------------------------------------------------------------------
SCREEN_TRADES_PER_WALLET = 100   # How many recent trades to pull per wallet.
SCREEN_MAX_MARKETS = 40          # Cap resolution lookups per wallet (API budget).
SCREEN_MIN_RESOLVED = 20         # Below this many resolved bets, treat as luck.

# ----------------------------------------------------------------------------
# AI DECISION BRAIN (the `--ai` mode in bot.py) — OPTIONAL
# ----------------------------------------------------------------------------
# Off unless you set an API key in a .env file (see .env.example). With no key,
# the bot silently uses the simple maths strategy instead.
AI_PROVIDER = "openrouter"                  # "openrouter" | "openai" | "anthropic"
AI_MODEL = "anthropic/claude-3.5-sonnet"    # model name for your chosen provider
AI_MIN_CONFIDENCE = 60                      # ignore AI calls below this confidence
AI_TEMPERATURE = 0.1                        # low = steadier, less random

# ----------------------------------------------------------------------------
# LIVE EXECUTION (real money) — used only with `--live` AND LIVE_ARMED=YES
# ----------------------------------------------------------------------------
# Start tiny. This hard-caps the dollar size of any single real order, no matter
# what the strategy requests. Raise it ONLY after live validation at this size.
LIVE_MAX_USD = 5.0
# AI_PROVIDER above can be set to "anthropic" with ANTHROPIC_API_KEY in .env to
# use Claude for the decision step. Remember: the AI has no edge on priced odds.
