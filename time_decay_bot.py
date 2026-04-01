from __future__ import annotations
"""
Bot #14: Time Decay — bets that consensus solidifies as resolution approaches.

Theory: Markets between 7-30 days from close with a clear lean (>65% or <35%)
tend to drift further toward their lean as resolution approaches. Traders
who disagree have already sold; remaining holders are confident.

Different from Close Gravity (which targets 0.5-5 days and uses momentum).
Time Decay targets the broader 7-30 day window and uses the probability
level itself as the signal, not recent bet momentum.

Signal:
  - Market closing in 7-30 days
  - Current probability >65% or <35% (clear lean)
  - Market has been established (48h+ old, 500+ pool)
  - Bet WITH the lean — the consensus will solidify
"""

import logging
from bot_engine import (
    BotConfig, run_bot, fetch_binary_markets_flexible,
    bot_signal_alert, bot_exit_alert,
)

log = logging.getLogger("time_decay")

LABEL = "DECAY"

BOT_CONFIG = BotConfig(
    name="time_decay",
    display_name="Time Decay Bot",
    trades_file="time_decay_trades.json",
    backup_file="time_decay_trades.backup.json",
    target_yes=85,       # ride the consensus to near-resolution levels
    target_no=15,
    stop_pp=7,
    trailing_stop_pp=5,
    max_days=21,
    confidence_field="decay_strength",
)

LEAN_HIGH = 65   # prob above this = clear YES lean
LEAN_LOW = 35    # prob below this = clear NO lean
MAX_PROB = 85    # don't enter above this (not enough room)
MIN_PROB = 15    # don't enter below this


def detect_signals() -> list[dict]:
    markets = fetch_binary_markets_flexible(
        n=80,
        min_pool=500,
        min_age_hr=48,
        min_close_days=7,
        max_close_days=30,
    )
    if not markets:
        return []

    signals = []
    for m in markets:
        prob = round(m.get("probability", 0) * 100, 1)

        if prob > MAX_PROB or prob < MIN_PROB:
            continue

        if prob >= LEAN_HIGH:
            direction = "BUY YES"
            # Strength scales with how strong the lean is
            decay_strength = (prob - 50) / 50
        elif prob <= LEAN_LOW:
            direction = "BUY NO"
            decay_strength = (50 - prob) / 50
        else:
            continue  # no clear lean

        # Estimate days to close for signal strength
        import time
        now_ms = time.time() * 1000
        close_time = m.get("closeTime", 0)
        days_to_close = (close_time - now_ms) / 86_400_000 if close_time else 30

        # Closer to close + stronger lean = stronger signal
        time_factor = max(0.5, 1.0 - (days_to_close - 7) / 30)
        strength = decay_strength * time_factor

        signals.append({
            "market_id": m["id"],
            "question": m["question"],
            "direction": direction,
            "entry_prob": prob,
            "days_to_close": round(days_to_close, 1),
            "decay_strength": round(strength, 2),
            "signal_strength": round(strength, 2),
            "url": m.get("url", ""),
        })

    signals.sort(key=lambda s: s["decay_strength"], reverse=True)
    return signals[:4]


def _signal_alert(trade):
    bot_signal_alert(trade, LABEL,
                     f"Closes in:   {trade.get('days_to_close', '?')} days\n"
                     f"Decay str:   {trade.get('decay_strength', 0):.2f}\n")


def _exit_alert(trade):
    bot_exit_alert(trade, LABEL)


def main():
    run_bot(BOT_CONFIG, detect_signals, _signal_alert, _exit_alert)


if __name__ == "__main__":
    main()
