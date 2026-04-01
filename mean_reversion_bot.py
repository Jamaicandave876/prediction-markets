from __future__ import annotations
"""
Bot #3: Mean Reversion — bets that extreme probabilities revert toward center.

Theory: Markets at >85% or <15% are often overcrowded. When there's no
imminent resolution catalyst, they tend to drift back toward the middle.

Signal:
  - Prob > 82% → BUY NO (expect it to come down)
  - Prob < 18% → BUY YES (expect it to come up)
  - Must not be closing soon (these might actually resolve at extremes)
  - Stronger signal the further from 50%
"""

import logging
from bot_engine import (
    BotConfig, run_bot, fetch_binary_markets_flexible,
    bot_signal_alert, bot_exit_alert,
)

log = logging.getLogger("mean_reversion")

LABEL = "MEAN REV"

# ── Config ───────────────────────────────────────────────────────────────────

BOT_CONFIG = BotConfig(
    name="mean_reversion",
    display_name="Mean Reversion Bot",
    trades_file="mean_reversion_trades.json",
    backup_file="mean_reversion_trades.backup.json",
    target_yes=40,      # BUY YES target: prob rises from <18% to 40%
    target_no=60,       # BUY NO target: prob drops from >82% to 60%
    stop_pp=6,          # stop if it goes 6pp further toward extreme
    trailing_stop_pp=5,
    max_days=10,
    confidence_field="distance_from_center",
)

# Thresholds
EXTREME_HIGH = 78  # prob above this = overbought
EXTREME_LOW = 22   # prob below this = oversold
MIN_POOL = 500     # liquidity requirement


# ── Signal Detection ─────────────────────────────────────────────────────────

def detect_signals() -> list[dict]:
    markets = fetch_binary_markets_flexible(
        n=80,
        min_pool=MIN_POOL,
        min_age_hr=12,      # must be at least half a day old
        min_close_days=7,   # not closing within a week
    )
    if not markets:
        return []

    signals = []
    for m in markets:
        prob = round(m.get("probability", 0) * 100, 1)

        if prob >= EXTREME_HIGH:
            direction = "BUY NO"
            distance = prob - 50
        elif prob <= EXTREME_LOW:
            direction = "BUY YES"
            distance = 50 - prob
        else:
            continue

        signals.append({
            "market_id": m["id"],
            "question": m["question"],
            "direction": direction,
            "entry_prob": prob,
            "distance_from_center": round(distance, 1),
            "signal_strength": round(distance / 50, 2),
            "url": m.get("url", ""),
        })

    signals.sort(key=lambda s: s["distance_from_center"], reverse=True)
    return signals[:5]  # max 5 new entries per run


def _signal_alert(trade):
    bot_signal_alert(trade, LABEL,
                     f"Distance:    {trade.get('distance_from_center', 0)}pp from center\n")


def _exit_alert(trade):
    bot_exit_alert(trade, LABEL)


def main():
    run_bot(BOT_CONFIG, detect_signals, _signal_alert, _exit_alert)


if __name__ == "__main__":
    main()
