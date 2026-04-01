from __future__ import annotations
"""
Bot #20: Liquidation Sniper — buys the dip after panic selling.

Theory: When a market drops sharply on a SINGLE large bet (panic sell /
liquidation), the price temporarily overshoots. Unlike the Fade bot
(which targets sustained spikes from many bets), Liquidation Sniper
targets single-bet waterfall drops.

A single bet that moves the price 5+pp usually creates a temporary
dislocation that reverts within hours as other traders see the opportunity.

Signal:
  - A single bet in the last 4 hours moved the price 5+pp
  - The bet was a large "dump" (100+ Mana)
  - The market has enough liquidity to absorb it (pool > 500)
  - Buy the dip — bet AGAINST the panic direction
"""

import logging
import time
from bot_engine import (
    BotConfig, run_bot, fetch_binary_markets_flexible, fetch_rich_bets,
    bot_signal_alert, bot_exit_alert,
)

log = logging.getLogger("liquidation")

LABEL = "LIQUID"

BOT_CONFIG = BotConfig(
    name="liquidation",
    display_name="Liquidation Sniper Bot",
    trades_file="liquidation_trades.json",
    backup_file="liquidation_trades.backup.json",
    target_yes=70,
    target_no=30,
    stop_pp=6,           # wider stop — these can be volatile
    trailing_stop_pp=4,
    max_days=5,
    confidence_field="impact_score",
)

MIN_IMPACT_PP = 5.0     # single bet must move price 5+pp
MIN_BET_SIZE = 100      # bet must be 100+ Mana
LOOKBACK_HOURS = 4      # only look at recent liquidations


def detect_signals() -> list[dict]:
    markets = fetch_binary_markets_flexible(n=80, min_pool=500, min_close_days=3)
    if not markets:
        return []

    now_ms = time.time() * 1000
    cutoff = now_ms - LOOKBACK_HOURS * 3_600_000

    signals = []
    for m in markets:
        bets = fetch_rich_bets(m["id"], limit=30)
        if len(bets) < 5:
            continue

        # Find any single large bet that caused a big price move
        liquidation = None
        for b in reversed(bets):  # check newest first
            if b["time_ms"] < cutoff:
                break

            impact = abs(b["prob_after"] - b["prob_before"]) * 100
            if impact >= MIN_IMPACT_PP and b["amount"] >= MIN_BET_SIZE:
                liquidation = b
                break

        if not liquidation:
            continue

        prob = round(m.get("probability", 0) * 100, 1)
        if prob > 88 or prob < 12:
            continue

        # Bet AGAINST the liquidation (buy the dip)
        liq_dir = liquidation["outcome"]
        if liq_dir == "YES":
            direction = "BUY NO"    # they panic bought YES, we fade it
        else:
            direction = "BUY YES"   # they panic sold (bought NO), we buy the dip

        impact = abs(liquidation["prob_after"] - liquidation["prob_before"]) * 100
        impact_score = (impact / 5) * (liquidation["amount"] / 200)

        signals.append({
            "market_id": m["id"],
            "question": m["question"],
            "direction": direction,
            "entry_prob": prob,
            "liquidation_size": round(liquidation["amount"]),
            "liquidation_impact": round(impact, 1),
            "liquidation_dir": liq_dir,
            "impact_score": round(impact_score, 2),
            "signal_strength": round(min(impact_score / 2, 1.5), 2),
            "url": m.get("url", ""),
        })

    signals.sort(key=lambda s: s["impact_score"], reverse=True)
    return signals[:3]


def _signal_alert(trade):
    bot_signal_alert(trade, LABEL,
                     f"Liquidation: {trade.get('liquidation_size', 0)} Mana "
                     f"({trade.get('liquidation_dir', '?')})\n"
                     f"Impact:      {trade.get('liquidation_impact', 0)}pp price move\n")


def _exit_alert(trade):
    bot_exit_alert(trade, LABEL)


def main():
    run_bot(BOT_CONFIG, detect_signals, _signal_alert, _exit_alert)


if __name__ == "__main__":
    main()
