from __future__ import annotations
"""
Bot #16: Accumulation — detects quiet position building.

Theory: When many small bets (under 50 Mana each) consistently go in one
direction without moving the price much, someone is quietly accumulating
a position. This is the opposite of a whale — it's someone trying NOT to
move the market while building size.

Signal:
  - 70%+ of bets under 50 Mana are in one direction
  - Total accumulated volume > 150 Mana
  - Price has moved < 3pp (they're being careful)
  - Follow the accumulator
"""

import logging
from bot_engine import (
    BotConfig, run_bot, fetch_binary_markets_flexible, fetch_rich_bets,
    bot_signal_alert, bot_exit_alert,
)

log = logging.getLogger("accumulation")

LABEL = "ACCUM"

BOT_CONFIG = BotConfig(
    name="accumulation",
    display_name="Accumulation Bot",
    trades_file="accumulation_trades.json",
    backup_file="accumulation_trades.backup.json",
    target_yes=74,
    target_no=26,
    stop_pp=5,
    trailing_stop_pp=4,
    max_days=10,
    confidence_field="accum_score",
)

MAX_BET_SIZE = 50       # only count "small" bets (quiet accumulation)
MIN_DIRECTION_PCT = 0.70 # 70% of small bets in same direction
MIN_TOTAL_VOLUME = 150   # total accumulated must exceed this
MAX_PRICE_MOVE = 3.0     # price shouldn't have moved much (stealth)
MIN_SMALL_BETS = 10      # need enough small bets


def detect_signals() -> list[dict]:
    markets = fetch_binary_markets_flexible(n=80, min_pool=400, min_close_days=3)
    if not markets:
        return []

    signals = []
    for m in markets:
        bets = fetch_rich_bets(m["id"], limit=40)
        if len(bets) < 10:
            continue

        # Filter to small bets only
        small_bets = [b for b in bets if b["amount"] <= MAX_BET_SIZE]
        if len(small_bets) < MIN_SMALL_BETS:
            continue

        # Count direction
        yes_vol = sum(b["amount"] for b in small_bets if b["outcome"] == "YES")
        no_vol = sum(b["amount"] for b in small_bets if b["outcome"] == "NO")
        total_vol = yes_vol + no_vol

        if total_vol < MIN_TOTAL_VOLUME:
            continue

        yes_pct = yes_vol / total_vol if total_vol > 0 else 0.5

        if yes_pct >= MIN_DIRECTION_PCT:
            accum_dir = "YES"
            accum_pct = yes_pct
        elif (1 - yes_pct) >= MIN_DIRECTION_PCT:
            accum_dir = "NO"
            accum_pct = 1 - yes_pct
        else:
            continue

        # Check that price hasn't moved much (stealth accumulation)
        if len(small_bets) >= 2:
            price_start = small_bets[0]["prob_before"] * 100
            price_end = small_bets[-1]["prob_after"] * 100
            price_move = abs(price_end - price_start)
            if price_move > MAX_PRICE_MOVE:
                continue
        else:
            continue

        prob = round(m.get("probability", 0) * 100, 1)
        if prob > 85 or prob < 15:
            continue

        direction = "BUY YES" if accum_dir == "YES" else "BUY NO"
        accum_score = accum_pct * (total_vol / 300) * (1 - price_move / MAX_PRICE_MOVE)

        signals.append({
            "market_id": m["id"],
            "question": m["question"],
            "direction": direction,
            "entry_prob": prob,
            "accum_direction": accum_dir,
            "accum_pct": round(accum_pct * 100, 1),
            "total_volume": round(total_vol),
            "price_move": round(price_move, 1),
            "accum_score": round(accum_score, 2),
            "signal_strength": round(min(accum_score / 2, 1.5), 2),
            "url": m.get("url", ""),
        })

    signals.sort(key=lambda s: s["accum_score"], reverse=True)
    return signals[:3]


def _signal_alert(trade):
    bot_signal_alert(trade, LABEL,
                     f"Direction:   {trade.get('accum_pct', 0)}% small bets {trade.get('accum_direction', '?')}\n"
                     f"Volume:      {trade.get('total_volume', 0)} Mana accumulated\n"
                     f"Price move:  {trade.get('price_move', 0)}pp (stealth)\n")


def _exit_alert(trade):
    bot_exit_alert(trade, LABEL)


def main():
    run_bot(BOT_CONFIG, detect_signals, _signal_alert, _exit_alert)


if __name__ == "__main__":
    main()
