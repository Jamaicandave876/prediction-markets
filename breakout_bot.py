from __future__ import annotations
"""
Bot #10: Breakout — detects when a stable market suddenly moves.

Theory: When a market has been range-bound for many bets and then suddenly
breaks out of its range, the breakout is usually real (not noise). This
combines stability detection with sudden movement detection.

Signal:
  - First 20 bets: price range < 5pp (stable baseline)
  - Last 10 bets: price moved 6+pp in one direction (breakout)
  - Follow the breakout direction
  - This is distinct from momentum (which doesn't require prior stability)
    and from fade (which bets AGAINST moves)
"""

import logging
from bot_engine import (
    BotConfig, run_bot, fetch_binary_markets_flexible, fetch_rich_bets,
    bot_signal_alert, bot_exit_alert,
)

log = logging.getLogger("breakout")

LABEL = "BREAKOUT"

BOT_CONFIG = BotConfig(
    name="breakout",
    display_name="Breakout Bot",
    trades_file="breakout_trades.json",
    backup_file="breakout_trades.backup.json",
    target_yes=80,
    target_no=20,
    stop_pp=5,           # tight stop — if it falls back into range, it's a fakeout
    trailing_stop_pp=4,
    max_days=7,
    confidence_field="breakout_strength",
)

BASELINE_BETS = 15      # how many older bets define the "range"
BREAKOUT_BETS = 5       # how many recent bets define the "breakout"
MAX_RANGE_PP = 8.0       # baseline must be within this range (stable)
MIN_BREAKOUT_PP = 5.0    # breakout must move this much


def detect_signals() -> list[dict]:
    markets = fetch_binary_markets_flexible(n=80, min_pool=300, min_close_days=2)
    if not markets:
        return []

    total_bets_needed = BASELINE_BETS + BREAKOUT_BETS
    signals = []

    for m in markets:
        bets = fetch_rich_bets(m["id"], limit=total_bets_needed + 5)
        if len(bets) < total_bets_needed:
            continue

        # Need multiple unique traders
        unique_traders = len(set(b["user_id"] for b in bets if b.get("user_id")))
        if unique_traders < 3:
            continue

        baseline_bets = bets[:BASELINE_BETS]
        breakout_bets = bets[-BREAKOUT_BETS:]  # use LAST N bets for breakout

        # Check baseline stability
        baseline_probs = [b["prob_after"] * 100 for b in baseline_bets]
        baseline_range = max(baseline_probs) - min(baseline_probs)
        if baseline_range > MAX_RANGE_PP:
            continue

        # Check breakout magnitude
        breakout_start = breakout_bets[0]["prob_before"] * 100
        breakout_end = breakout_bets[-1]["prob_after"] * 100
        breakout_move = breakout_end - breakout_start

        if abs(breakout_move) < MIN_BREAKOUT_PP:
            continue

        prob = round(m.get("probability", 0) * 100, 1)

        # Don't chase into extremes
        if prob > 88 or prob < 12:
            continue

        direction = "BUY YES" if breakout_move > 0 else "BUY NO"

        # Breakout strength = magnitude of move relative to prior range
        strength = abs(breakout_move) / max(baseline_range, 1)

        signals.append({
            "market_id": m["id"],
            "question": m["question"],
            "direction": direction,
            "entry_prob": prob,
            "baseline_range": round(baseline_range, 1),
            "breakout_move": round(breakout_move, 1),
            "breakout_strength": round(strength, 1),
            "signal_strength": min(strength / 3, 1.5),
            "url": m.get("url", ""),
        })

    signals.sort(key=lambda s: s["breakout_strength"], reverse=True)
    return signals[:3]


def _signal_alert(trade):
    bot_signal_alert(trade, LABEL,
                     f"Baseline:    {trade.get('baseline_range', 0)}pp range\n"
                     f"Breakout:    {trade.get('breakout_move', 0):+.1f}pp\n"
                     f"Strength:    {trade.get('breakout_strength', 0):.1f}x\n")


def _exit_alert(trade):
    bot_exit_alert(trade, LABEL)


def main():
    run_bot(BOT_CONFIG, detect_signals, _signal_alert, _exit_alert)


if __name__ == "__main__":
    main()
