"""
Central configuration for the Consensus Momentum Trader.
All tunable parameters in one place — change anything here.
Keep this file private (contains Telegram credentials).
"""

# ── API ───────────────────────────────────────────────────────────────────────
API_BASE = "https://api.manifold.markets/v0"

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = "8764048221:AAEgEYUvHlan4T8BdSFRYBSQ2KdgIWfylwA"
TELEGRAM_CHAT_ID = "8425023293"

# ── Market Scanning ───────────────────────────────────────────────────────────
MARKETS_TO_SCAN    = 40       # how many markets to scan each run
MIN_POOL           = 500      # minimum liquidity pool (YES + NO in Mana)
MIN_MARKET_AGE_HR  = 1        # skip markets younger than this (hours)

# ── Momentum Detection ────────────────────────────────────────────────────────
BETS_WINDOW        = 30       # how many recent bets to analyze per market
MIN_BETS           = 8        # need at least this many bets to compute a signal
DECAY_STRENGTH     = 2.0      # how much more recent bets matter vs old ones
                              # (2.0 = newest bet weighted ~7x more than oldest)

# ── Signal Filters ────────────────────────────────────────────────────────────
ENTRY_PROB_LOW     = 45       # % — below this is too uncertain / early
ENTRY_PROB_HIGH    = 72       # % — above this may already be crowded
MIN_DRIFT_SCORE    = 2.0      # |drift_score| must exceed this
MIN_CONSISTENCY    = 65       # % of bets in trend direction (raised from 50 to filter noise)

# ── Exit Conditions ───────────────────────────────────────────────────────────
EXIT_TARGET_YES    = 78       # close BUY YES when prob rises above this %
EXIT_TARGET_NO     = 22       # close BUY NO when prob falls below this %
REVERSAL_THRESHOLD = 6        # pp — close if market moves this far against entry
MAX_TRADE_DAYS     = 14       # close trades older than this many days
