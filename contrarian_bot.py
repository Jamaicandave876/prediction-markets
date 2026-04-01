from __future__ import annotations
"""
Bot #6: Contrarian — bets against absorbed small-bet flow.

Theory: When many small bets all push one direction but the price barely
moves, that's "absorption" — the market is resisting. The small bettors
are wrong, and the price will eventually snap back.

Signal:
  - 70%+ of recent bets (by count) are in one direction
  - But price moved < 3pp in that direction
  - Bet AGAINST the crowd
"""

import logging
from bot_engine import (
    BotConfig, run_bot, fetch_binary_markets_flexible, fetch_rich_bets,
    bot_signal_alert, bot_exit_alert,
)

log = logging.getLogger("contrarian")

LABEL = "CONTRARIAN"

BOT_CONFIG = BotConfig(
    name="contrarian",
    display_name="Contrarian Bot",
    trades_file="contrarian_trades.json",
    backup_file="contrarian_trades.backup.json",
    target_yes=70,
    target_no=30,
    stop_pp=6,
    trailing_stop_pp=4,
    max_days=7,
    confidence_field="absorption_score",
)

CROWD_THRESHOLD = 0.65   # 65% of bets in one direction
MAX_PRICE_MOVE = 4.0     # price moved less than 4pp despite the crowd
MIN_BETS = 10            # need enough bets to establish a crowd
MAX_SINGLE_BET = 200     # only count "small" bets (< 200 Mana)


def detect_signals() -> list[dict]:
    markets = fetch_binary_markets_flexible(n=80, min_pool=400, min_close_days=2)
    if not markets:
        return []

    signals = []
    for m in markets:
        bets = fetch_rich_bets(m["id"], limit=40)
        if len(bets) < MIN_BETS:
            continue

        # Only look at small bets
        small_bets = [b for b in bets if b["amount"] < MAX_SINGLE_BET]
        if len(small_bets) < MIN_BETS:
            continue

        # Count direction
        yes_count = sum(1 for b in small_bets if b["outcome"] == "YES")
        no_count = sum(1 for b in small_bets if b["outcome"] == "NO")
        total = yes_count + no_count
        if total == 0:
            continue

        yes_pct = yes_count / total
        no_pct = no_count / total

        # Is the crowd lopsided?
        if yes_pct >= CROWD_THRESHOLD:
            crowd_dir = "YES"
            crowd_pct = yes_pct
        elif no_pct >= CROWD_THRESHOLD:
            crowd_dir = "NO"
            crowd_pct = no_pct
        else:
            continue

        # Has the price actually moved in the crowd's direction?
        first_prob = small_bets[0]["prob_before"] * 100
        last_prob = small_bets[-1]["prob_after"] * 100
        move = last_prob - first_prob  # positive = price went up

        if crowd_dir == "YES" and move > MAX_PRICE_MOVE:
            continue  # crowd is winning, don't fight it
        if crowd_dir == "NO" and -move > MAX_PRICE_MOVE:
            continue  # crowd is winning

        # Absorption detected! Bet against the crowd.
        prob = round(m.get("probability", 0) * 100, 1)
        if crowd_dir == "YES":
            direction = "BUY NO"   # crowd buying YES, we bet NO
        else:
            direction = "BUY YES"  # crowd buying NO, we bet YES

        absorption = crowd_pct * (1 - abs(move) / 10)  # higher = more absorbed

        signals.append({
            "market_id": m["id"],
            "question": m["question"],
            "direction": direction,
            "entry_prob": prob,
            "crowd_direction": crowd_dir,
            "crowd_pct": round(crowd_pct * 100, 1),
            "price_move": round(move, 1),
            "absorption_score": round(absorption, 2),
            "signal_strength": round(absorption, 2),
            "url": m.get("url", ""),
        })

    signals.sort(key=lambda s: s["absorption_score"], reverse=True)
    return signals[:4]  # max 4 per run


def _signal_alert(trade):
    bot_signal_alert(trade, LABEL,
                     f"Crowd:       {trade.get('crowd_pct', 0)}% betting {trade.get('crowd_direction', '?')}\n"
                     f"Price move:  {trade.get('price_move', 0)}pp (absorbed)\n")


def _exit_alert(trade):
    bot_exit_alert(trade, LABEL)


def main():
    run_bot(BOT_CONFIG, detect_signals, _signal_alert, _exit_alert)


if __name__ == "__main__":
    main()
