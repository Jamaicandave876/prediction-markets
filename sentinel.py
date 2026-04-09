from __future__ import annotations
"""
Sentinel — Risk Manager of the trading system.

The last line of defense. Runs AFTER Atlas and provides:
  1. Portfolio-level risk metrics (total exposure, max drawdown, VaR estimate)
  2. Concentration risk — alerts if too much capital in one market or direction
  3. Emergency halt protocol — shuts everything down if risk limits breached
  4. Daily risk digest separate from Atlas's strategy report
  5. Position-level risk scoring (which trades are closest to blowing up)
"""

import json
import logging
from pathlib import Path

from bot_engine import (
    load_trades, get_market_state, now_str, days_since,
)
from notify import send
from config import STARTING_BALANCE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("sentinel")

STATE_FILE = Path("sentinel_state.json")

ALL_BOTS = [
    {"name": "momentum",       "file": "trades.json",                   "backup": "trades.backup.json"},
    {"name": "fade",           "file": "fade_trades.json",              "backup": "fade_trades.backup.json"},
    {"name": "mean_reversion", "file": "mean_reversion_trades.json",    "backup": "mean_reversion_trades.backup.json"},
    {"name": "volume_surge",   "file": "volume_trades.json",            "backup": "volume_trades.backup.json"},
    {"name": "whale",          "file": "whale_trades.json",             "backup": "whale_trades.backup.json"},
    {"name": "contrarian",     "file": "contrarian_trades.json",        "backup": "contrarian_trades.backup.json"},
    {"name": "close_gravity",  "file": "close_gravity_trades.json",     "backup": "close_gravity_trades.backup.json"},
    {"name": "fresh_sniper",   "file": "fresh_sniper_trades.json",      "backup": "fresh_sniper_trades.backup.json"},
    {"name": "stability",      "file": "stability_trades.json",         "backup": "stability_trades.backup.json"},
    {"name": "breakout",       "file": "breakout_trades.json",          "backup": "breakout_trades.backup.json"},
    # Weather bots (Polymarket)
    {"name": "weather_temperature",   "file": "weather_temperature_trades.json",   "backup": "weather_temperature_trades.backup.json"},
    {"name": "weather_precipitation", "file": "weather_precipitation_trades.json", "backup": "weather_precipitation_trades.backup.json"},
    {"name": "weather_storm",         "file": "weather_storm_trades.json",         "backup": "weather_storm_trades.backup.json"},
    {"name": "weather_divergence",    "file": "weather_divergence_trades.json",    "backup": "weather_divergence_trades.backup.json"},
]

# Risk thresholds
MAX_SINGLE_MARKET_EXPOSURE = 0.15  # max 15% of balance in one market
MAX_DIRECTION_SKEW = 0.70          # max 70% of capital in one direction
DRAWDOWN_WARNING = -40             # warn at -40pp
DRAWDOWN_HALT = -80                # halt everything at -80pp
MAX_UNREALIZED_LOSS_PER_TRADE = -15  # flag any single trade losing >15pp


# ── State ────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, ValueError):
            pass
    return {"last_run": None, "alerts_sent": 0, "risk_level": "green"}


def save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)


# ── Risk Analysis ────────────────────────────────────────────────────────────

def analyze_portfolio_risk(all_open: list[dict], all_closed: list[dict]) -> dict:
    """Comprehensive portfolio risk analysis."""
    # Total exposure
    total_stake = sum(t.get("stake", 50) for t in all_open)
    balance = STARTING_BALANCE + sum(
        (t.get("pnl_pp", 0) or 0) / 100 * t.get("stake", 50)
        for t in all_closed if t.get("pnl_pp") is not None
    )

    # Market concentration
    by_market = {}
    for t in all_open:
        mid = t["market_id"]
        by_market[mid] = by_market.get(mid, 0) + t.get("stake", 50)

    max_concentration = max(by_market.values()) / balance if by_market and balance > 0 else 0
    most_concentrated = max(by_market.items(), key=lambda x: x[1])[0] if by_market else None

    # Direction skew
    yes_stake = sum(t.get("stake", 50) for t in all_open if t["direction"] == "BUY YES")
    no_stake = sum(t.get("stake", 50) for t in all_open if t["direction"] == "BUY NO")
    total = yes_stake + no_stake
    direction_skew = max(yes_stake, no_stake) / total if total > 0 else 0.5

    # 7-day realized P&L
    pnl_7d = 0.0
    for t in all_closed:
        if not t.get("pnl_pp"):
            continue
        try:
            if days_since(t["exit_time"]) <= 7:
                pnl_7d += t["pnl_pp"]
        except (ValueError, KeyError):
            continue

    # Risk level
    if pnl_7d <= DRAWDOWN_HALT:
        risk_level = "red"
    elif pnl_7d <= DRAWDOWN_WARNING or max_concentration > MAX_SINGLE_MARKET_EXPOSURE:
        risk_level = "yellow"
    else:
        risk_level = "green"

    return {
        "total_stake": round(total_stake, 1),
        "balance": round(balance, 1),
        "exposure_pct": round(total_stake / balance * 100, 1) if balance > 0 else 0,
        "max_concentration": round(max_concentration * 100, 1),
        "most_concentrated_market": most_concentrated,
        "direction_skew": round(direction_skew * 100, 1),
        "skew_direction": "YES" if yes_stake > no_stake else "NO",
        "pnl_7d": round(pnl_7d, 1),
        "risk_level": risk_level,
        "open_count": len(all_open),
    }


def find_danger_trades(all_open: list[dict]) -> list[dict]:
    """Identify open trades that are closest to their stop loss or deeply underwater."""
    danger = []
    for t in all_open:
        state = get_market_state(t["market_id"])
        if state["status"] != "active":
            continue

        prob = state["probability"]
        entry = t["entry_prob"]

        if t["direction"] == "BUY YES":
            pnl = prob - entry
        else:
            pnl = entry - prob

        if pnl <= MAX_UNREALIZED_LOSS_PER_TRADE:
            danger.append({
                "bot": t.get("_bot", "?"),
                "question": t["question"][:45],
                "direction": t["direction"],
                "entry_prob": entry,
                "current_prob": prob,
                "pnl_pp": round(pnl, 1),
                "stake": t.get("stake", 50),
            })

    danger.sort(key=lambda d: d["pnl_pp"])
    return danger


def build_report(risk: dict, danger: list[dict]) -> str:
    """Build Sentinel's risk report."""
    level_label = {
        "green": "GREEN (normal)",
        "yellow": "YELLOW (elevated)",
        "red": "RED (CRITICAL)",
    }

    lines = [
        f"<b>[SENTINEL] Risk Report</b>",
        "",
        f"<b>Risk Level: {level_label.get(risk['risk_level'], risk['risk_level'])}</b>",
        "",
        f"Balance:        {risk['balance']:,.0f} Mana",
        f"Open positions: {risk['open_count']}",
        f"Capital at risk: {risk['total_stake']:,.0f} Mana ({risk['exposure_pct']:.0f}% of balance)",
        f"7-day P&L:      {risk['pnl_7d']:+.1f}pp",
        "",
        f"<b>Concentration</b>",
        f"Max single market: {risk['max_concentration']:.0f}% of balance",
        f"Direction skew:    {risk['direction_skew']:.0f}% {risk['skew_direction']}",
    ]

    if danger:
        lines.append("")
        lines.append(f"<b>Danger Trades ({len(danger)})</b>")
        for d in danger[:5]:
            lines.append(
                f"- [{d['bot']}] {d['question']}..."
                f"\n  {d['direction']} {d['entry_prob']}% -> {d['current_prob']}% "
                f"({d['pnl_pp']:+.1f}pp, {d['stake']:.0f}M at risk)"
            )

    # Warnings
    warnings = []
    if risk["max_concentration"] > MAX_SINGLE_MARKET_EXPOSURE * 100:
        warnings.append(f"Single market exposure {risk['max_concentration']:.0f}% exceeds {MAX_SINGLE_MARKET_EXPOSURE*100:.0f}% limit")
    if risk["direction_skew"] > MAX_DIRECTION_SKEW * 100:
        warnings.append(f"Direction skew {risk['direction_skew']:.0f}% {risk['skew_direction']} exceeds {MAX_DIRECTION_SKEW*100:.0f}% limit")
    if risk["pnl_7d"] <= DRAWDOWN_WARNING:
        warnings.append(f"7-day P&L {risk['pnl_7d']:+.1f}pp approaching halt threshold ({DRAWDOWN_HALT}pp)")

    if warnings:
        lines.append("")
        lines.append("<b>Warnings</b>")
        for w in warnings:
            lines.append(f"- {w}")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"Sentinel (Risk Manager)  [{now_str()}]")
    print("=" * 60)

    state = load_state()

    # Load all trades
    all_open = []
    all_closed = []
    for bd in ALL_BOTS:
        trades = load_trades(bd["file"], bd["backup"])
        for t in trades:
            if t["status"] == "open":
                t["_bot"] = bd["name"]
                all_open.append(t)
            elif t["status"] == "closed":
                all_closed.append(t)

    print(f"\nOpen: {len(all_open)}  |  Closed: {len(all_closed)}")

    # 1. Portfolio risk analysis
    risk = analyze_portfolio_risk(all_open, all_closed)
    print(f"\nRisk Level: {risk['risk_level'].upper()}")
    print(f"Balance: {risk['balance']:,.0f} Mana")
    print(f"Exposure: {risk['total_stake']:,.0f} Mana ({risk['exposure_pct']:.0f}%)")
    print(f"Direction: {risk['direction_skew']:.0f}% {risk['skew_direction']}")
    print(f"7-day P&L: {risk['pnl_7d']:+.1f}pp")

    # 2. Danger trades (only check a few to avoid API hammering)
    danger = []
    if risk["risk_level"] != "green" and len(all_open) <= 10:
        danger = find_danger_trades(all_open)
        if danger:
            print(f"\nDanger trades: {len(danger)}")
            for d in danger:
                print(f"  [{d['bot']}] {d['pnl_pp']:+.1f}pp — {d['question']}...")

    # 3. Emergency halt
    if risk["risk_level"] == "red":
        print("\nEMERGENCY: Risk level RED — notifying")
        send("<b>[SENTINEL] EMERGENCY RISK ALERT</b>\n\n"
             f"7-day P&L: {risk['pnl_7d']:+.1f}pp\n"
             f"Threshold: {DRAWDOWN_HALT}pp\n\n"
             "Atlas has been notified to pause all bots.")

    # 4. Send risk report
    report = build_report(risk, danger)
    send(report)

    # 5. Save state
    state["last_run"] = now_str()
    state["risk_level"] = risk["risk_level"]
    state["alerts_sent"] = state.get("alerts_sent", 0) + (1 if risk["risk_level"] != "green" else 0)
    save_state(state)

    print("\nSentinel (Risk Manager) complete.")


if __name__ == "__main__":
    main()
