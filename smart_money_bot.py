from __future__ import annotations
"""
Bot #13: Smart Money — follows users who make large, impactful bets consistently.

Theory: Some bettors are systematically better informed than others. When a
user places a large bet (100+ Mana) that significantly moves the price AND
they have a history of large bets on this market, they're likely informed.

Unlike the Whale bot (which just follows any big bet), Smart Money looks for
REPEAT large bettors on the same market — someone coming back to add to
their position signals strong conviction.

Signal:
  - A user has placed 2+ bets totaling 200+ Mana on the same market
  - All their bets are in the same direction (conviction, not hedging)
  - Their bets collectively moved the price 3+pp
"""

import logging
import time
from collections import defaultdict
from bot_engine import (
    BotConfig, run_bot, fetch_binary_markets_flexible, fetch_rich_bets,
    bot_signal_alert, bot_exit_alert,
)

log = logging.getLogger("smart_money")

LABEL = "SMART$"

BOT_CONFIG = BotConfig(
    name="smart_money",
    display_name="Smart Money Bot",
    trades_file="smart_money_trades.json",
    backup_file="smart_money_trades.backup.json",
    target_yes=75,
    target_no=25,
    stop_pp=5,
    trailing_stop_pp=4,
    max_days=10,
    confidence_field="conviction_score",
)

MIN_USER_BETS = 2        # user must have placed 2+ bets
MIN_USER_TOTAL = 200     # total Mana across their bets
MIN_IMPACT_PP = 3.0      # their bets must have moved price 3+pp
LOOKBACK_HOURS = 24      # only look at last 24 hours of activity


def detect_signals() -> list[dict]:
    markets = fetch_binary_markets_flexible(n=80, min_pool=400, min_close_days=3)
    if not markets:
        return []

    now_ms = time.time() * 1000
    cutoff = now_ms - LOOKBACK_HOURS * 3_600_000

    signals = []
    for m in markets:
        bets = fetch_rich_bets(m["id"], limit=50)
        if len(bets) < 5:
            continue

        # Group recent bets by user
        user_bets = defaultdict(list)
        for b in bets:
            if b["time_ms"] >= cutoff and b.get("user_id"):
                user_bets[b["user_id"]].append(b)

        # Find "smart money" users
        for user_id, ubets in user_bets.items():
            if len(ubets) < MIN_USER_BETS:
                continue

            total_mana = sum(b["amount"] for b in ubets)
            if total_mana < MIN_USER_TOTAL:
                continue

            # Check all bets are in same direction (conviction)
            directions = set(b["outcome"] for b in ubets)
            if len(directions) > 1:
                continue  # hedging, not conviction

            # Measure price impact
            first_prob = ubets[0]["prob_before"] * 100
            last_prob = ubets[-1]["prob_after"] * 100
            impact = abs(last_prob - first_prob)
            if impact < MIN_IMPACT_PP:
                continue

            prob = round(m.get("probability", 0) * 100, 1)
            bet_dir = ubets[0]["outcome"]
            direction = "BUY YES" if bet_dir == "YES" else "BUY NO"

            if prob > 88 or prob < 12:
                continue

            conviction = (total_mana / 500) * (impact / 5) * len(ubets)

            signals.append({
                "market_id": m["id"],
                "question": m["question"],
                "direction": direction,
                "entry_prob": prob,
                "smart_user_bets": len(ubets),
                "smart_user_mana": round(total_mana),
                "price_impact": round(impact, 1),
                "conviction_score": round(conviction, 2),
                "signal_strength": round(min(conviction / 3, 1.5), 2),
                "url": m.get("url", ""),
            })
            break  # one smart money signal per market is enough

    signals.sort(key=lambda s: s["conviction_score"], reverse=True)
    return signals[:3]


def _signal_alert(trade):
    bot_signal_alert(trade, LABEL,
                     f"Conviction:  {trade.get('smart_user_bets', 0)} bets, "
                     f"{trade.get('smart_user_mana', 0)} Mana\n"
                     f"Impact:      {trade.get('price_impact', 0)}pp\n")


def _exit_alert(trade):
    bot_exit_alert(trade, LABEL)


def main():
    run_bot(BOT_CONFIG, detect_signals, _signal_alert, _exit_alert)


if __name__ == "__main__":
    main()
