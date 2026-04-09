"""
Central configuration for all trading bots + intelligence layer.
All tunable parameters in one place — change anything here.
Keep this file private (contains Telegram credentials).
"""

# ── API ───────────────────────────────────────────────────────────────────────
API_BASE = "https://api.manifold.markets/v0"

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = "8764048221:AAEgEYUvHlan4T8BdSFRYBSQ2KdgIWfylwA"
TELEGRAM_CHAT_ID = "8425023293"

# ── Market Scanning ───────────────────────────────────────────────────────────
MARKETS_TO_SCAN    = 80       # how many markets to scan each run
MIN_POOL           = 300      # minimum liquidity pool (YES + NO in Mana)
MIN_MARKET_AGE_HR  = 1        # skip markets younger than this (hours)
MIN_CLOSE_DAYS     = 2        # skip markets closing within this many days
                              # (prevents resolution-risk blowups on short-term markets)

# ── Momentum Detection ────────────────────────────────────────────────────────
BETS_WINDOW        = 30       # how many recent bets to analyze per market
MIN_BETS           = 8        # need at least this many bets to compute a signal
DECAY_STRENGTH     = 2.0      # how much more recent bets matter vs old ones
                              # (2.0 = newest bet weighted ~7x more than oldest)

# ── Signal Filters ────────────────────────────────────────────────────────────
ENTRY_PROB_LOW     = 15       # % — below this is too uncertain / early
ENTRY_PROB_HIGH    = 85       # % — above this may already be crowded
MIN_DRIFT_SCORE    = 1.5      # |drift_score| must exceed this
MIN_CONSISTENCY    = 55       # % of bets in trend direction

# ── Portfolio Simulation ──────────────────────────────────────────────────────
STARTING_BALANCE   = 1000    # hypothetical starting balance in Mana
                             # position sizing is dynamic — see portfolio.py

# ── Exit Conditions ───────────────────────────────────────────────────────────
EXIT_TARGET_YES    = 78       # close BUY YES when prob rises above this %
EXIT_TARGET_NO     = 22       # close BUY NO when prob falls below this %
REVERSAL_THRESHOLD = 8        # pp — close if market moves this far against entry
TRAILING_STOP_PP   = 6        # pp — close if trade drops this far from its peak profit
MAX_TRADE_DAYS     = 14       # close trades older than this many days

# ══════════════════════════════════════════════════════════════════════════════
# OVERREACTION FADE BOT
# ══════════════════════════════════════════════════════════════════════════════

# ── Spike Detection ───────────────────────────────────────────────────────────
SPIKE_BETS_TOTAL   = 20       # total bets to fetch per market
SPIKE_RECENT       = 5        # last N bets = the "spike window"
SPIKE_MIN_BETS     = 12       # need at least this many bets (recent + baseline)
SPIKE_MIN_SIZE     = 6        # pp — minimum spike size to consider
SPIKE_MIN_RATIO    = 2.5      # spike must be this many times larger than baseline moves
MAX_CONSISTENCY    = 50        # % — reject if consistency is TOO high (that's a trend, not a spike)
SPIKE_MAX_WINDOW_HR = 6       # spike window bets must span less than this many hours
                              # (if 5 bets took 6+ hours, it's not a real spike)

# ── Fade Exit Conditions ──────────────────────────────────────────────────────
FADE_NORMALIZE_PCT = 50       # % of spike to recover for a win (50 = expect half the spike to retrace)
FADE_STOP_PP       = 8        # pp — stop loss if price keeps going in spike direction
FADE_MAX_DAYS      = 7        # fade trades expire faster (spikes resolve quickly)
FADE_MIN_REWARD_RATIO = 0.8   # minimum reward/risk ratio (filters out bad risk-reward trades)

# ══════════════════════════════════════════════════════════════════════════════
# INTELLIGENCE LAYER
# ══════════════════════════════════════════════════════════════════════════════

# ── Risk Limits ───────────────────────────────────────────────────────────────
INTEL_MAX_OPEN_TOTAL       = 50   # max open trades across all 20 bots (~2-3 per bot)
INTEL_MAX_OPEN_PER_BOT     = 5    # max open trades per individual bot
INTEL_DRAWDOWN_LIMIT_PP    = -30  # pause if 7-day P&L (realized+unrealized) exceeds this
INTEL_PAUSE_AFTER_LOSSES   = 5    # pause a bot after this many consecutive losses
INTEL_MAX_PAUSE_DAYS       = 2    # auto-unpause after this many days (prevents deadlock)

# ── Auto-Adjustment ──────────────────────────────────────────────────────────
INTEL_LOOKBACK_TRADES      = 10   # how many recent closed trades to evaluate
INTEL_ADJUST_BOUNDS        = {
    "MIN_DRIFT_SCORE":     (1.0, 5.0,  0.3),   # (min, max, step)
    "MIN_CONSISTENCY":     (50,  85,   5),
    "REVERSAL_THRESHOLD":  (3,   8,    1),
    "SPIKE_MIN_RATIO":     (2.0, 8.0,  0.5),
    "SPIKE_MIN_SIZE":      (5,   15,   1),
    "FADE_STOP_PP":        (4,   12,   1),
}

# ── Reporting ─────────────────────────────────────────────────────────────────
INTEL_DAILY_REPORT_ENABLED = True  # set False to disable daily digest

# ── Runtime Overrides (auto-managed by intelligence layer) ───────────────────
# The intelligence layer writes parameter adjustments to config_overrides.json
# instead of modifying this file directly. Overrides are loaded below.
import json as _json
from pathlib import Path as _Path
_overrides_path = _Path(__file__).parent / "config_overrides.json"
if _overrides_path.exists():
    try:
        for _k, _v in _json.loads(_overrides_path.read_text()).items():
            if _k in globals():
                globals()[_k] = _v
    except Exception:
        pass
