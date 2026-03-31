from __future__ import annotations
"""
Bot #7: Close Gravity — rides trends on markets about to resolve.

Theory: Markets closing within 24-72 hours with a clear directional trend
tend to resolve in that direction. The "gravity" of resolution pulls the
price harder as close time approaches.

Signal:
  - Markets closing in 1-3 days
  - Clear trend in recent bets (using momentum detection)
  - Follow the trend — ride it to resolution
"""

import logging
from bot_engine import (
    BotConfig, run_bot, fetch_binary_markets_flexible, fetch_rich_bets,
    bot_signal_alert, bot_exit_alert,
)
from detect_momentum import compute_momentum

log = logging.getLogger("close_gravity")

LABEL = "GRAVITY"

BOT_CONFIG = BotConfig(
    name="close_gravity",
    display_name="Close Gravity Bot",
    trades_file="close_gravity_trades.json",
    backup_file="close_gravity_trades.backup.json",
    target_yes=88,      # wider target — ride to resolution
    target_no=12,
    stop_pp=8,          # wider stop — these are volatile near close
    trailing_stop_pp=5,
    max_days=4,         # should resolve within this window
    confidence_field="drift_score",
)

MIN_DRIFT = 1.5       # lower threshold — even small trends near close are meaningful
MIN_CONSISTENCY = 55   # slightly relaxed


def detect_signals() -> list[dict]:
    # Only markets closing in 1-3 days
    markets = fetch_binary_markets_flexible(
        n=60,
        min_pool=300,       # lower pool OK for closing markets
        min_age_hr=48,      # must have existed a while
        min_close_days=0.5, # at least 12 hours left
        max_close_days=3,   # but closing within 3 days
    )
    if not markets:
        return []

    signals = []
    for m in markets:
        bets = fetch_rich_bets(m["id"], limit=30)
        if len(bets) < 8:
            continue

        probs = [b["prob_after"] for b in bets]
        mom = compute_momentum(probs)

        if abs(mom["drift_score"]) < MIN_DRIFT:
            continue
        if mom["consistency"] < MIN_CONSISTENCY:
            continue

        prob = round(m.get("probability", 0) * 100, 1)

        # Don't enter if already very extreme
        if prob > 90 or prob < 10:
            continue

        direction = "BUY YES" if mom["drift"] > 0 else "BUY NO"

        signals.append({
            "market_id": m["id"],
            "question": m["question"],
            "direction": direction,
            "entry_prob": prob,
            "drift_score": mom["drift_score"],
            "consistency": mom["consistency"],
            "signal_strength": abs(mom["drift_score"]) / 10,
            "url": m.get("url", ""),
        })

    signals.sort(key=lambda s: abs(s["drift_score"]), reverse=True)
    return signals[:3]


def _signal_alert(trade):
    bot_signal_alert(trade, LABEL,
                     f"Drift:       {trade.get('drift_score', 0):+.2f}\n"
                     f"Closing soon — riding to resolution\n")


def _exit_alert(trade):
    bot_exit_alert(trade, LABEL)


def main():
    run_bot(BOT_CONFIG, detect_signals, _signal_alert, _exit_alert)


if __name__ == "__main__":
    main()
