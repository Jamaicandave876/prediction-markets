from __future__ import annotations
"""
Bot #17: Underdog — catches the first signs of life in dormant extreme markets.

Theory: Markets stuck at extreme probabilities (>80% or <20%) for a long
time become "priced in." When the FIRST significant counter-move appears
(someone bets against the consensus and moves the price 3+pp), it often
signals new information that the market hasn't fully absorbed yet.

Different from Mean Reversion (which just bets against any extreme).
Underdog requires evidence of a CATALYST — the first crack in consensus.

Signal:
  - Market at extreme probability (>80% or <20%)
  - Recent bets show first counter-move: 3+pp against the consensus
  - Market has been stable at this extreme for a while (low baseline volatility)
"""

import logging
from bot_engine import (
    BotConfig, run_bot, fetch_binary_markets_flexible, fetch_rich_bets,
    bot_signal_alert, bot_exit_alert,
)

log = logging.getLogger("underdog")

LABEL = "UNDERDOG"

BOT_CONFIG = BotConfig(
    name="underdog",
    display_name="Underdog Bot",
    trades_file="underdog_trades.json",
    backup_file="underdog_trades.backup.json",
    target_yes=45,       # underdog positions have big targets
    target_no=55,
    stop_pp=5,           # tight stop — if the crack seals, we're wrong
    trailing_stop_pp=4,
    max_days=14,
    confidence_field="crack_size",
)

EXTREME_HIGH = 80
EXTREME_LOW = 20
MIN_CRACK_PP = 3.0      # first counter-move must be 3+pp
MAX_BASELINE_RANGE = 5.0 # market must have been stable before the crack
BASELINE_BETS = 15       # bets to define the baseline
CRACK_BETS = 5           # recent bets to detect the crack


def detect_signals() -> list[dict]:
    markets = fetch_binary_markets_flexible(
        n=80,
        min_pool=400,
        min_age_hr=72,      # must be established (3+ days)
        min_close_days=7,
    )
    if not markets:
        return []

    signals = []
    for m in markets:
        prob = round(m.get("probability", 0) * 100, 1)

        # Must be at an extreme
        if EXTREME_LOW < prob < EXTREME_HIGH:
            continue

        bets = fetch_rich_bets(m["id"], limit=BASELINE_BETS + CRACK_BETS)
        if len(bets) < BASELINE_BETS + CRACK_BETS:
            continue

        baseline = bets[:BASELINE_BETS]
        crack_bets = bets[-CRACK_BETS:]

        # Check baseline stability
        baseline_probs = [b["prob_after"] * 100 for b in baseline]
        baseline_range = max(baseline_probs) - min(baseline_probs)
        if baseline_range > MAX_BASELINE_RANGE:
            continue  # market was already volatile, not "dormant"

        # Detect crack: recent bets moved against the consensus
        crack_start = crack_bets[0]["prob_before"] * 100
        crack_end = crack_bets[-1]["prob_after"] * 100
        crack_move = crack_end - crack_start

        if prob >= EXTREME_HIGH:
            # Market is high, crack = price dropping
            if crack_move >= -MIN_CRACK_PP:
                continue  # no crack
            direction = "BUY NO"
            crack_size = abs(crack_move)
        else:
            # Market is low, crack = price rising
            if crack_move <= MIN_CRACK_PP:
                continue  # no crack
            direction = "BUY YES"
            crack_size = abs(crack_move)

        strength = crack_size / baseline_range if baseline_range > 0 else crack_size

        signals.append({
            "market_id": m["id"],
            "question": m["question"],
            "direction": direction,
            "entry_prob": prob,
            "baseline_range": round(baseline_range, 1),
            "crack_move": round(crack_move, 1),
            "crack_size": round(crack_size, 1),
            "signal_strength": round(min(strength / 3, 1.5), 2),
            "url": m.get("url", ""),
        })

    signals.sort(key=lambda s: s["crack_size"], reverse=True)
    return signals[:3]


def _signal_alert(trade):
    bot_signal_alert(trade, LABEL,
                     f"Baseline:    {trade.get('baseline_range', 0)}pp range (dormant)\n"
                     f"Crack:       {trade.get('crack_move', 0):+.1f}pp counter-move\n")


def _exit_alert(trade):
    bot_exit_alert(trade, LABEL)


def main():
    run_bot(BOT_CONFIG, detect_signals, _signal_alert, _exit_alert)


if __name__ == "__main__":
    main()
