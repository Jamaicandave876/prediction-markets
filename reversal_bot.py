from __future__ import annotations
"""
Bot #12: Momentum Reversal — detects when a trending market starts to turn.

Theory: After a sustained move in one direction, the first signs of reversal
(momentum slowing + a few bets going the other way) often signal that the
trend is exhausted. We enter AGAINST the prior trend at the inflection point.

This is different from Fade (which targets sudden spikes) and Contrarian
(which targets crowd absorption). Reversal targets gradual trend exhaustion.

Signal:
  - First 15 bets show clear trend (>60% consistency in one direction)
  - Last 10 bets show reversal (>55% consistency in OPPOSITE direction)
  - The turn has begun but isn't yet reflected in the price
"""

import logging
from bot_engine import (
    BotConfig, run_bot, fetch_binary_markets_flexible, fetch_rich_bets,
    bot_signal_alert, bot_exit_alert,
)

log = logging.getLogger("reversal")

LABEL = "REVERSAL"

BOT_CONFIG = BotConfig(
    name="reversal",
    display_name="Reversal Bot",
    trades_file="reversal_trades.json",
    backup_file="reversal_trades.backup.json",
    target_yes=72,
    target_no=28,
    stop_pp=6,
    trailing_stop_pp=4,
    max_days=7,
    confidence_field="reversal_strength",
)

TREND_BETS = 15         # older bets defining the trend
REVERSAL_BETS = 10      # recent bets showing reversal
TREND_CONSISTENCY = 0.60 # 60% of trend bets must agree
REVERSAL_CONSISTENCY = 0.55  # 55% of recent bets must go opposite
MIN_TREND_MOVE = 4.0    # trend must have moved at least 4pp


def detect_signals() -> list[dict]:
    markets = fetch_binary_markets_flexible(n=80, min_pool=400, min_close_days=3)
    if not markets:
        return []

    signals = []
    for m in markets:
        bets = fetch_rich_bets(m["id"], limit=TREND_BETS + REVERSAL_BETS)
        if len(bets) < TREND_BETS + REVERSAL_BETS:
            continue

        trend_bets = bets[:TREND_BETS]
        recent_bets = bets[-REVERSAL_BETS:]

        # Measure trend direction
        trend_start = trend_bets[0]["prob_before"] * 100
        trend_end = trend_bets[-1]["prob_after"] * 100
        trend_move = trend_end - trend_start

        if abs(trend_move) < MIN_TREND_MOVE:
            continue

        trend_dir = 1 if trend_move > 0 else -1

        # Check trend consistency
        trend_steps = [b["prob_after"] - b["prob_before"] for b in trend_bets]
        trend_in_dir = sum(1 for s in trend_steps if s * trend_dir > 0)
        if trend_in_dir / len(trend_steps) < TREND_CONSISTENCY:
            continue

        # Check reversal in recent bets
        reversal_steps = [b["prob_after"] - b["prob_before"] for b in recent_bets]
        reversal_against = sum(1 for s in reversal_steps if s * trend_dir < 0)
        reversal_pct = reversal_against / len(reversal_steps)
        if reversal_pct < REVERSAL_CONSISTENCY:
            continue

        prob = round(m.get("probability", 0) * 100, 1)

        # Don't enter at extremes
        if prob > 85 or prob < 15:
            continue

        # Bet against the prior trend (the reversal direction)
        direction = "BUY NO" if trend_dir > 0 else "BUY YES"

        strength = reversal_pct * abs(trend_move) / 10

        signals.append({
            "market_id": m["id"],
            "question": m["question"],
            "direction": direction,
            "entry_prob": prob,
            "trend_move": round(trend_move, 1),
            "reversal_pct": round(reversal_pct * 100, 1),
            "reversal_strength": round(strength, 2),
            "signal_strength": round(strength / 2, 2),
            "url": m.get("url", ""),
        })

    signals.sort(key=lambda s: s["reversal_strength"], reverse=True)
    return signals[:3]


def _signal_alert(trade):
    bot_signal_alert(trade, LABEL,
                     f"Prior trend: {trade.get('trend_move', 0):+.1f}pp\n"
                     f"Reversal:    {trade.get('reversal_pct', 0)}% of recent bets\n")


def _exit_alert(trade):
    bot_exit_alert(trade, LABEL)


def main():
    run_bot(BOT_CONFIG, detect_signals, _signal_alert, _exit_alert)


if __name__ == "__main__":
    main()
