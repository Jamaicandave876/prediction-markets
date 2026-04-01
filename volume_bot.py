from __future__ import annotations
"""
Bot #4: Volume Surge — detects unusual betting activity and follows the money.

Theory: A sudden spike in bet volume (3x+ above baseline) often signals
informed trading. We follow the net direction of the volume surge.

Signal:
  - Compare last 2 hours of bets vs previous 22 hours
  - If recent volume > 3x average hourly baseline
  - Follow the net Mana-weighted direction
"""

import logging
import time
from bot_engine import (
    BotConfig, run_bot, fetch_binary_markets_flexible, fetch_rich_bets,
    bot_signal_alert, bot_exit_alert,
)

log = logging.getLogger("volume")

LABEL = "VOLUME"

BOT_CONFIG = BotConfig(
    name="volume_surge",
    display_name="Volume Surge Bot",
    trades_file="volume_trades.json",
    backup_file="volume_trades.backup.json",
    target_yes=75,
    target_no=25,
    stop_pp=5,
    trailing_stop_pp=4,
    max_days=5,
    confidence_field="volume_ratio",
)

SURGE_RATIO = 2.0       # recent volume must be 2x baseline per hour
MIN_RECENT_BETS = 3     # need at least 3 bets in surge window
RECENT_HOURS = 4        # surge window (wider = catches more)
BASELINE_HOURS = 20     # baseline window
MIN_NET_FLOW_MANA = 50  # net directional flow must exceed 50 Mana


def detect_signals() -> list[dict]:
    markets = fetch_binary_markets_flexible(n=80, min_pool=300, min_close_days=2)
    if not markets:
        return []

    now_ms = time.time() * 1000
    recent_cutoff = now_ms - RECENT_HOURS * 3_600_000
    baseline_cutoff = now_ms - (RECENT_HOURS + BASELINE_HOURS) * 3_600_000

    signals = []
    for m in markets:
        bets = fetch_rich_bets(m["id"], limit=100)
        if len(bets) < 8:
            continue

        # Need multiple unique traders (not one person spamming)
        unique_traders = len(set(b["user_id"] for b in bets if b.get("user_id")))
        if unique_traders < 3:
            continue

        recent = [b for b in bets if b["time_ms"] >= recent_cutoff]
        baseline = [b for b in bets if baseline_cutoff <= b["time_ms"] < recent_cutoff]

        if len(recent) < MIN_RECENT_BETS:
            continue
        if not baseline:
            continue

        # Volume comparison (Mana per hour)
        recent_mana = sum(b["amount"] for b in recent)
        baseline_mana = sum(b["amount"] for b in baseline)
        baseline_per_hr = baseline_mana / BASELINE_HOURS if BASELINE_HOURS > 0 else 1
        recent_per_hr = recent_mana / RECENT_HOURS if RECENT_HOURS > 0 else 0

        if baseline_per_hr <= 0:
            continue
        volume_ratio = recent_per_hr / baseline_per_hr
        if volume_ratio < SURGE_RATIO:
            continue

        # Net flow direction (Mana-weighted)
        yes_flow = sum(b["amount"] for b in recent if b["outcome"] == "YES")
        no_flow = sum(b["amount"] for b in recent if b["outcome"] == "NO")
        net_flow = yes_flow - no_flow

        if abs(net_flow) < MIN_NET_FLOW_MANA:
            continue

        prob = round(m.get("probability", 0) * 100, 1)
        direction = "BUY YES" if net_flow > 0 else "BUY NO"

        signals.append({
            "market_id": m["id"],
            "question": m["question"],
            "direction": direction,
            "entry_prob": prob,
            "volume_ratio": round(volume_ratio, 1),
            "net_flow": round(net_flow),
            "recent_mana": round(recent_mana),
            "signal_strength": min(volume_ratio / 10, 1.5),
            "url": m.get("url", ""),
        })

    signals.sort(key=lambda s: s["volume_ratio"], reverse=True)
    return signals[:3]


def _signal_alert(trade):
    bot_signal_alert(trade, LABEL,
                     f"Volume:      {trade.get('volume_ratio', 0)}x surge\n"
                     f"Net flow:    {trade.get('net_flow', 0)} Mana\n")


def _exit_alert(trade):
    bot_exit_alert(trade, LABEL)


def main():
    run_bot(BOT_CONFIG, detect_signals, _signal_alert, _exit_alert)


if __name__ == "__main__":
    main()
