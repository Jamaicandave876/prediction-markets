from __future__ import annotations
"""
Bot #8: Fresh Sniper — exploits mispricing in brand new markets.

Theory: New markets (< 24 hours old) start at ~50% and are inefficient.
When early bettors rapidly establish a consensus direction (moving the
price 15+pp from start), that early consensus is usually correct —
they're informed bettors who got there first.

Signal:
  - Market created < 24 hours ago
  - Already has 10+ bets
  - Price has moved 15+pp from opening probability
  - Follow the early consensus
"""

import logging
import time
from bot_engine import (
    BotConfig, run_bot, fetch_rich_bets,
    bot_signal_alert, bot_exit_alert,
)
import requests
from config import API_BASE

log = logging.getLogger("fresh_sniper")

LABEL = "SNIPER"

BOT_CONFIG = BotConfig(
    name="fresh_sniper",
    display_name="Fresh Sniper Bot",
    trades_file="fresh_sniper_trades.json",
    backup_file="fresh_sniper_trades.backup.json",
    target_yes=75,
    target_no=25,
    stop_pp=8,          # wider stop — new markets are volatile
    trailing_stop_pp=5,
    max_days=7,
    confidence_field="move_from_open",
)

MIN_BETS = 6           # need enough early bets
MIN_MOVE_PP = 10       # price must have moved 10pp from open
MAX_AGE_HR = 48        # market must be < 48 hours old
MIN_AGE_HR = 1         # at least 1 hour old (not just noise)
MIN_POOL = 150         # lower threshold for new markets


def detect_signals() -> list[dict]:
    # Fetch recent markets (the API returns newest first)
    try:
        resp = requests.get(
            f"{API_BASE}/markets",
            params={"limit": 100},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException:
        return []

    now_ms = time.time() * 1000
    signals = []

    for m in resp.json():
        if m.get("outcomeType") != "BINARY":
            continue
        if m.get("isResolved"):
            continue

        created = m.get("createdTime", 0)
        age_hr = (now_ms - created) / 3_600_000

        if age_hr < MIN_AGE_HR or age_hr > MAX_AGE_HR:
            continue

        pool = m.get("pool", {})
        pool_total = pool.get("YES", 0) + pool.get("NO", 0)
        if pool_total < MIN_POOL:
            continue

        bets = fetch_rich_bets(m["id"], limit=30)
        if len(bets) < MIN_BETS:
            continue

        # Opening probability (first bet's prob_before)
        open_prob = bets[0]["prob_before"] * 100
        current_prob = round(m.get("probability", 0) * 100, 1)
        move = current_prob - open_prob

        if abs(move) < MIN_MOVE_PP:
            continue

        direction = "BUY YES" if move > 0 else "BUY NO"

        # Don't enter if already at extremes
        if current_prob > 85 or current_prob < 15:
            continue

        signals.append({
            "market_id": m["id"],
            "question": m["question"],
            "direction": direction,
            "entry_prob": current_prob,
            "open_prob": round(open_prob, 1),
            "move_from_open": round(abs(move), 1),
            "age_hours": round(age_hr, 1),
            "signal_strength": min(abs(move) / 30, 1.5),
            "url": m.get("url", ""),
        })

    signals.sort(key=lambda s: s["move_from_open"], reverse=True)
    return signals[:3]


def _signal_alert(trade):
    bot_signal_alert(trade, LABEL,
                     f"Age:         {trade.get('age_hours', 0)}h old\n"
                     f"Opened at:   {trade.get('open_prob', 50)}%\n"
                     f"Moved:       {trade.get('move_from_open', 0)}pp\n")


def _exit_alert(trade):
    bot_exit_alert(trade, LABEL)


def main():
    run_bot(BOT_CONFIG, detect_signals, _signal_alert, _exit_alert)


if __name__ == "__main__":
    main()
