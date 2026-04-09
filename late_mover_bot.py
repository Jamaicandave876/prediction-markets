from __future__ import annotations
"""
Bot #18: Late Mover — finds markets with stale prices that haven't updated.

Theory: Some markets stop getting bets even though the underlying event
has new information. If no one has bet in 12+ hours, the price is stale.
We look for stale markets where the probability seems mispriced compared
to similar-probability markets that ARE active.

Signal:
  - No bets in the last 12+ hours (stale price)
  - Market still has significant time before close
  - Probability is in the 30-70% range (uncertain — most likely to be stale)
  - If stale price is above 55% → BUY YES (market leans YES but nobody's trading)
  - If stale price is below 45% → BUY NO (market leans NO)
  - Skip 45-55% dead zone
"""

import logging
import time
from bot_engine import (
    BotConfig, run_bot, fetch_binary_markets_flexible, fetch_rich_bets,
    bot_signal_alert, bot_exit_alert,
)

log = logging.getLogger("late_mover")

LABEL = "LATE"

BOT_CONFIG = BotConfig(
    name="late_mover",
    display_name="Late Mover Bot",
    trades_file="late_mover_trades.json",
    backup_file="late_mover_trades.backup.json",
    target_yes=73,
    target_no=27,
    stop_pp=8,
    trailing_stop_pp=6,
    max_days=10,
    confidence_field="staleness_score",
)

MIN_STALE_HOURS = 12    # no bets for this long = stale
MAX_STALE_HOURS = 168   # more than a week stale = probably dead market
LEAN_YES_ABOVE = 55     # follow the lean
LEAN_NO_BELOW = 45


def detect_signals() -> list[dict]:
    markets = fetch_binary_markets_flexible(
        n=80,
        min_pool=300,
        min_age_hr=48,
        min_close_days=7,
    )
    if not markets:
        return []

    now_ms = time.time() * 1000
    signals = []

    for m in markets:
        prob = round(m.get("probability", 0) * 100, 1)

        # Only interested in uncertain markets
        if prob > 75 or prob < 25:
            continue

        bets = fetch_rich_bets(m["id"], limit=10)
        if not bets:
            continue

        # Check staleness
        latest_bet_time = max(b["time_ms"] for b in bets)
        hours_since_bet = (now_ms - latest_bet_time) / 3_600_000

        if hours_since_bet < MIN_STALE_HOURS:
            continue  # not stale enough
        if hours_since_bet > MAX_STALE_HOURS:
            continue  # probably dead

        # Follow the existing lean
        if prob >= LEAN_YES_ABOVE:
            direction = "BUY YES"
        elif prob <= LEAN_NO_BELOW:
            direction = "BUY NO"
        else:
            continue  # dead zone

        # Staleness score: staler = stronger signal (up to a point)
        staleness = min(hours_since_bet / 48, 2.0)
        lean_strength = abs(prob - 50) / 50
        score = staleness * lean_strength

        signals.append({
            "market_id": m["id"],
            "question": m["question"],
            "direction": direction,
            "entry_prob": prob,
            "hours_stale": round(hours_since_bet, 1),
            "staleness_score": round(score, 2),
            "signal_strength": round(min(score, 1.5), 2),
            "url": m.get("url", ""),
        })

    signals.sort(key=lambda s: s["staleness_score"], reverse=True)
    return signals[:4]


def _signal_alert(trade):
    bot_signal_alert(trade, LABEL,
                     f"Stale:       {trade.get('hours_stale', 0):.0f}h since last bet\n")


def _exit_alert(trade):
    bot_exit_alert(trade, LABEL)


def main():
    run_bot(BOT_CONFIG, detect_signals, _signal_alert, _exit_alert)


if __name__ == "__main__":
    main()
