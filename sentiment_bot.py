from __future__ import annotations
"""
Bot #15: Sentiment Divergence — bets when bet COUNT and PRICE disagree.

Theory: When many bets (by count) push one direction but the price barely
moves or moves the OTHER way, large counter-bets are absorbing the flow.
The large counter-bettors are usually smarter (they're risking more).

Different from Contrarian (which checks small-bet absorption).
Sentiment Divergence compares TOTAL bet count direction vs price direction
regardless of bet size.

Signal:
  - 60%+ of last 20 bets are in one direction (by count)
  - Price moved in the OPPOSITE direction
  - Someone big is absorbing — follow the money, not the crowd
"""

import logging
from bot_engine import (
    BotConfig, run_bot, fetch_binary_markets_flexible, fetch_rich_bets,
    bot_signal_alert, bot_exit_alert,
)

log = logging.getLogger("sentiment")

LABEL = "SENTIMENT"

BOT_CONFIG = BotConfig(
    name="sentiment_divergence",
    display_name="Sentiment Divergence Bot",
    trades_file="sentiment_trades.json",
    backup_file="sentiment_trades.backup.json",
    target_yes=72,
    target_no=28,
    stop_pp=6,
    trailing_stop_pp=4,
    max_days=7,
    confidence_field="divergence_score",
)

CROWD_MIN_PCT = 0.60    # 60% of bets in one direction
MIN_BETS = 15           # need enough bets
MIN_COUNTER_MOVE = 1.0  # price must have moved at least 1pp AGAINST the crowd


def detect_signals() -> list[dict]:
    markets = fetch_binary_markets_flexible(n=80, min_pool=400, min_close_days=3)
    if not markets:
        return []

    signals = []
    for m in markets:
        bets = fetch_rich_bets(m["id"], limit=25)
        if len(bets) < MIN_BETS:
            continue

        recent = bets[-20:] if len(bets) >= 20 else bets

        # Count bet directions
        yes_count = sum(1 for b in recent if b["outcome"] == "YES")
        no_count = sum(1 for b in recent if b["outcome"] == "NO")
        total = yes_count + no_count
        if total < MIN_BETS:
            continue

        yes_pct = yes_count / total

        # Determine crowd direction
        if yes_pct >= CROWD_MIN_PCT:
            crowd_dir = "YES"
        elif (1 - yes_pct) >= CROWD_MIN_PCT:
            crowd_dir = "NO"
        else:
            continue

        # Check price movement
        price_start = recent[0]["prob_before"] * 100
        price_end = recent[-1]["prob_after"] * 100
        price_move = price_end - price_start  # positive = price went up

        # Divergence: crowd buying YES but price going DOWN, or vice versa
        if crowd_dir == "YES" and price_move >= -MIN_COUNTER_MOVE:
            continue  # no divergence — price follows crowd
        if crowd_dir == "NO" and price_move <= MIN_COUNTER_MOVE:
            continue  # no divergence

        prob = round(m.get("probability", 0) * 100, 1)
        if prob > 85 or prob < 15:
            continue

        # Follow the price (big money), not the crowd
        if crowd_dir == "YES":
            direction = "BUY NO"   # crowd buys YES, price falls → follow price
            divergence = abs(price_move) * yes_pct
        else:
            direction = "BUY YES"  # crowd buys NO, price rises → follow price
            divergence = abs(price_move) * (1 - yes_pct)

        signals.append({
            "market_id": m["id"],
            "question": m["question"],
            "direction": direction,
            "entry_prob": prob,
            "crowd_dir": crowd_dir,
            "crowd_pct": round(max(yes_pct, 1 - yes_pct) * 100, 1),
            "price_move": round(price_move, 1),
            "divergence_score": round(divergence, 2),
            "signal_strength": round(min(divergence / 5, 1.5), 2),
            "url": m.get("url", ""),
        })

    signals.sort(key=lambda s: s["divergence_score"], reverse=True)
    return signals[:3]


def _signal_alert(trade):
    bot_signal_alert(trade, LABEL,
                     f"Crowd:       {trade.get('crowd_pct', 0)}% betting {trade.get('crowd_dir', '?')}\n"
                     f"Price move:  {trade.get('price_move', 0):+.1f}pp (opposite!)\n")


def _exit_alert(trade):
    bot_exit_alert(trade, LABEL)


def main():
    run_bot(BOT_CONFIG, detect_signals, _signal_alert, _exit_alert)


if __name__ == "__main__":
    main()
