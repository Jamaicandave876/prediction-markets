from __future__ import annotations
"""
Bot #9: Stability — bets that range-bound markets stay in range.

Theory: Markets where the probability hasn't moved much over many bets are
in equilibrium. The "correct" price has been discovered. We bet that it
stays near its current level — essentially selling volatility.

Signal:
  - Price range < 4pp across last 30 bets
  - Prob between 25-75% (not already extreme)
  - If prob > 55% → BUY YES (expect it stays/rises)
  - If prob < 45% → BUY NO (expect it stays/drops)
  - Skip the 45-55% zone (too uncertain to pick a side)
"""

import logging
from bot_engine import (
    BotConfig, run_bot, fetch_binary_markets_flexible, fetch_rich_bets,
    bot_signal_alert, bot_exit_alert,
)

log = logging.getLogger("stability")

LABEL = "STABLE"

BOT_CONFIG = BotConfig(
    name="stability",
    display_name="Stability Bot",
    trades_file="stability_trades.json",
    backup_file="stability_trades.backup.json",
    target_yes=75,
    target_no=25,
    stop_pp=6,          # if range breaks, we're wrong
    trailing_stop_pp=4,
    max_days=10,
    confidence_field="stability_score",
)

MAX_RANGE_PP = 6.0   # max price range to qualify as "stable"
MIN_BETS = 15        # need enough bets to confirm stability
BUY_YES_ABOVE = 52   # lean YES if prob above this
BUY_NO_BELOW = 48    # lean NO if prob below this


def detect_signals() -> list[dict]:
    markets = fetch_binary_markets_flexible(
        n=80,
        min_pool=400,
        min_age_hr=24,     # must be established
        min_close_days=5,  # not closing soon
    )
    if not markets:
        return []

    signals = []
    for m in markets:
        bets = fetch_rich_bets(m["id"], limit=30)
        if len(bets) < MIN_BETS:
            continue

        # Need multiple unique traders confirming the price level
        unique_traders = len(set(b["user_id"] for b in bets if b.get("user_id")))
        if unique_traders < 4:
            continue

        probs_pct = [b["prob_after"] * 100 for b in bets]
        price_range = max(probs_pct) - min(probs_pct)

        if price_range > MAX_RANGE_PP:
            continue

        prob = round(m.get("probability", 0) * 100, 1)

        # Must be in our tradeable zone
        if prob > 75 or prob < 25:
            continue

        if prob >= BUY_YES_ABOVE:
            direction = "BUY YES"
        elif prob <= BUY_NO_BELOW:
            direction = "BUY NO"
        else:
            continue  # skip the dead zone

        # Stability score: inverse of range (tighter range = stronger signal)
        stability = round(1 - (price_range / MAX_RANGE_PP), 2)

        signals.append({
            "market_id": m["id"],
            "question": m["question"],
            "direction": direction,
            "entry_prob": prob,
            "price_range": round(price_range, 1),
            "stability_score": stability,
            "signal_strength": stability,
            "url": m.get("url", ""),
        })

    signals.sort(key=lambda s: s["stability_score"], reverse=True)
    return signals[:3]


def _signal_alert(trade):
    bot_signal_alert(trade, LABEL,
                     f"Range:       {trade.get('price_range', 0)}pp (last 30 bets)\n"
                     f"Stability:   {trade.get('stability_score', 0):.0%}\n")


def _exit_alert(trade):
    bot_exit_alert(trade, LABEL)


def main():
    run_bot(BOT_CONFIG, detect_signals, _signal_alert, _exit_alert)


if __name__ == "__main__":
    main()
