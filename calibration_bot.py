from __future__ import annotations
"""
Bot #11: Calibration — exploits the favorite-longshot bias.

Theory (academically validated):
  Markets are systematically miscalibrated at the extremes:
  - Events priced at 90%+ resolve YES only ~84-87% of the time
  - Events priced at 5-10% resolve YES ~8-12% of the time (slight overpricing)

  The "favorite-longshot bias" is one of the most robust findings in
  prediction market research. We exploit it by:
  - Selling (BUY NO) on events priced >88% that have no imminent catalyst
  - Buying (BUY YES) on events priced <12% that have no imminent catalyst

  This is NOT mean reversion — we don't expect the price to move to 50%.
  We're betting that the binary resolution will reveal the mispricing.
  The edge is small per trade but highly consistent.

Signal:
  - Prob > 88% and market won't close for 14+ days → BUY NO
  - Prob < 12% and market won't close for 14+ days → BUY YES
  - Must have sufficient liquidity (informed market)
  - Must have 10+ unique traders (not just one person's opinion)
  - Exclude markets that have recently had large moves (those are news-driven)
"""

import logging
import time
from bot_engine import (
    BotConfig, run_bot, fetch_binary_markets_flexible, fetch_rich_bets,
    bot_signal_alert, bot_exit_alert,
)

log = logging.getLogger("calibration")

LABEL = "CALIBRATE"

BOT_CONFIG = BotConfig(
    name="calibration",
    display_name="Calibration Bot",
    trades_file="calibration_trades.json",
    backup_file="calibration_trades.backup.json",
    target_yes=30,       # BUY YES target: underpriced event rises to 30%
    target_no=70,        # BUY NO target: overpriced event drops to 70%
    stop_pp=8,           # stop if price keeps going to extreme
    trailing_stop_pp=6,
    max_days=21,         # longer hold — waiting for resolution, not price movement
    confidence_field="miscalibration",
)

# Thresholds
OVERPRICED_ABOVE = 88   # prob above this = favorite-longshot bias territory
UNDERPRICED_BELOW = 12  # prob below this = longshot bias territory
MIN_POOL = 600          # need solid liquidity
MIN_UNIQUE_TRADERS = 5  # at least 5 different bettors
MAX_RECENT_MOVE = 10    # skip if price moved >10pp in last 10 bets (news-driven)


def detect_signals() -> list[dict]:
    markets = fetch_binary_markets_flexible(
        n=80,
        min_pool=MIN_POOL,
        min_age_hr=48,       # must be established (2+ days)
        min_close_days=14,   # not closing for 2+ weeks (resolution risk)
    )
    if not markets:
        return []

    signals = []
    for m in markets:
        prob = round(m.get("probability", 0) * 100, 1)

        # Must be in the miscalibration zone
        if UNDERPRICED_BELOW < prob < OVERPRICED_ABOVE:
            continue

        # Check for recent large moves (skip news-driven markets)
        bets = fetch_rich_bets(m["id"], limit=20)
        if len(bets) < 5:
            continue

        # Count unique traders
        unique_traders = len(set(b["user_id"] for b in bets if b.get("user_id")))
        if unique_traders < MIN_UNIQUE_TRADERS:
            continue

        # Check recent price stability (last 10 bets shouldn't have moved much)
        recent_bets = bets[-10:] if len(bets) >= 10 else bets
        recent_probs = [b["prob_after"] * 100 for b in recent_bets]
        recent_move = max(recent_probs) - min(recent_probs)
        if recent_move > MAX_RECENT_MOVE:
            continue  # skip — this market is moving on news, not bias

        if prob >= OVERPRICED_ABOVE:
            direction = "BUY NO"
            # Miscalibration estimate: empirically ~3-6pp at 90%+
            miscal = min((prob - 85) * 0.5, 8)
        else:
            direction = "BUY YES"
            miscal = min((15 - prob) * 0.5, 8)

        signals.append({
            "market_id": m["id"],
            "question": m["question"],
            "direction": direction,
            "entry_prob": prob,
            "miscalibration": round(miscal, 1),
            "unique_traders": unique_traders,
            "recent_move": round(recent_move, 1),
            "signal_strength": round(miscal / 10, 2),
            "url": m.get("url", ""),
        })

    signals.sort(key=lambda s: s["miscalibration"], reverse=True)
    return signals[:4]


def _signal_alert(trade):
    bot_signal_alert(trade, LABEL,
                     f"Miscal:      ~{trade.get('miscalibration', 0)}pp estimated\n"
                     f"Traders:     {trade.get('unique_traders', 0)} unique\n"
                     f"Stability:   {trade.get('recent_move', 0)}pp recent range\n")


def _exit_alert(trade):
    bot_exit_alert(trade, LABEL)


def main():
    run_bot(BOT_CONFIG, detect_signals, _signal_alert, _exit_alert)


if __name__ == "__main__":
    main()
