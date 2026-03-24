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

# ══════════════════════════════════════════════════════════════════════════════
# OVERREACTION FADE BOT
# ══════════════════════════════════════════════════════════════════════════════

# ── Spike Detection ───────────────────────────────────────────────────────────
SPIKE_BETS_TOTAL   = 20       # total bets to fetch per market
SPIKE_RECENT       = 5        # last N bets = the "spike window"
SPIKE_MIN_BETS     = 12       # need at least this many bets (recent + baseline)
SPIKE_MIN_SIZE     = 8        # pp — minimum spike size to consider
SPIKE_MIN_RATIO    = 3.0      # spike must be this many times larger than baseline moves
MAX_CONSISTENCY    = 50        # % — reject if consistency is TOO high (that's a trend, not a spike)

# ── Fade Exit Conditions ──────────────────────────────────────────────────────
FADE_NORMALIZE_PCT = 50       # % of spike to recover for a win (50 = expect half the spike to retrace)
FADE_STOP_PP       = 8        # pp — stop loss if price keeps going in spike direction
FADE_MAX_DAYS      = 7        # fade trades expire faster (spikes resolve quickly)
