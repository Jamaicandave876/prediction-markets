from __future__ import annotations
"""
Bot #5: Whale Tracker — piggybacks on large individual bets.

Theory: Bettors who risk large amounts (>200 Mana on a single bet) tend to
be more informed than small bettors. We follow their conviction.

Signal:
  - Scan recent bets for any single bet > 200 Mana in the last 6 hours
  - Follow the whale's direction
  - Stronger signal for larger bets
"""

import logging
import time
from bot_engine import (
    BotConfig, run_bot, fetch_binary_markets_flexible, fetch_rich_bets,
    bot_signal_alert, bot_exit_alert,
)

log = logging.getLogger("whale")

LABEL = "WHALE"

BOT_CONFIG = BotConfig(
    name="whale",
    display_name="Whale Tracker Bot",
    trades_file="whale_trades.json",
    backup_file="whale_trades.backup.json",
    target_yes=75,
    target_no=25,
    stop_pp=4,
    trailing_stop_pp=3,
    max_days=7,
    confidence_field="whale_amount",
)

WHALE_THRESHOLD = 200  # Mana — any single bet above this is a "whale"
LOOKBACK_HOURS = 6     # only care about recent whale activity
MIN_PROB_MOVE = 2.0    # whale bet must have moved the market at least 2pp


def detect_signals() -> list[dict]:
    markets = fetch_binary_markets_flexible(n=50, min_pool=500, min_close_days=3)
    if not markets:
        return []

    now_ms = time.time() * 1000
    cutoff = now_ms - LOOKBACK_HOURS * 3_600_000

    signals = []
    for m in markets:
        bets = fetch_rich_bets(m["id"], limit=50)
        if not bets:
            continue

        # Find whale bets in the lookback window
        whale_bets = [b for b in bets
                      if b["amount"] >= WHALE_THRESHOLD
                      and b["time_ms"] >= cutoff]

        if not whale_bets:
            continue

        # Take the largest whale bet
        biggest = max(whale_bets, key=lambda b: b["amount"])

        # Check price impact
        impact = abs(biggest["prob_after"] - biggest["prob_before"]) * 100
        if impact < MIN_PROB_MOVE:
            continue

        prob = round(m.get("probability", 0) * 100, 1)

        # Follow the whale
        if biggest["outcome"] == "YES":
            direction = "BUY YES"
        elif biggest["outcome"] == "NO":
            direction = "BUY NO"
        else:
            continue

        # Don't follow if prob is already extreme
        if prob > 85 or prob < 15:
            continue

        signals.append({
            "market_id": m["id"],
            "question": m["question"],
            "direction": direction,
            "entry_prob": prob,
            "whale_amount": round(biggest["amount"]),
            "price_impact": round(impact, 1),
            "signal_strength": min(biggest["amount"] / 1000, 1.5),
            "url": m.get("url", ""),
        })

    signals.sort(key=lambda s: s["whale_amount"], reverse=True)
    return signals[:3]


def _signal_alert(trade):
    bot_signal_alert(trade, LABEL,
                     f"Whale bet:   {trade.get('whale_amount', 0)} Mana\n"
                     f"Impact:      {trade.get('price_impact', 0)}pp\n")


def _exit_alert(trade):
    bot_exit_alert(trade, LABEL)


def main():
    run_bot(BOT_CONFIG, detect_signals, _signal_alert, _exit_alert)


if __name__ == "__main__":
    main()
