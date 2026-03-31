from __future__ import annotations
"""
Atlas — CEO of the trading system.

The big-picture strategist. Atlas sits above all 10 bots and:
  1. Scores each bot's recent performance (win rate, P&L, Sharpe-like ratio)
  2. Ranks bots from best to worst performer
  3. Pauses underperformers and gives top performers more runway
  4. Auto-adjusts parameters based on aggregate patterns
  5. Detects systemic issues (all bots losing = market regime change)
  6. Sends comprehensive daily intelligence reports
  7. Manages the "bot roster" — can bench struggling bots entirely
"""

import json
import logging
from pathlib import Path
from collections import Counter

from bot_engine import (
    load_trades, compute_metrics, now_str, days_since,
    BOT_TRADE_FILES,
)
from notify import send

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("atlas")

STATE_FILE = Path("atlas_state.json")
OVERRIDES_FILE = Path("config_overrides.json")

# All bots Atlas oversees
ALL_BOTS = [
    {"name": "momentum",       "display": "Momentum",       "file": "trades.json",                   "backup": "trades.backup.json"},
    {"name": "fade",           "display": "Fade",           "file": "fade_trades.json",              "backup": "fade_trades.backup.json"},
    {"name": "mean_reversion", "display": "Mean Reversion", "file": "mean_reversion_trades.json",    "backup": "mean_reversion_trades.backup.json"},
    {"name": "volume_surge",   "display": "Volume Surge",   "file": "volume_trades.json",            "backup": "volume_trades.backup.json"},
    {"name": "whale",          "display": "Whale Tracker",  "file": "whale_trades.json",             "backup": "whale_trades.backup.json"},
    {"name": "contrarian",     "display": "Contrarian",     "file": "contrarian_trades.json",        "backup": "contrarian_trades.backup.json"},
    {"name": "close_gravity",  "display": "Close Gravity",  "file": "close_gravity_trades.json",     "backup": "close_gravity_trades.backup.json"},
    {"name": "fresh_sniper",   "display": "Fresh Sniper",   "file": "fresh_sniper_trades.json",      "backup": "fresh_sniper_trades.backup.json"},
    {"name": "stability",      "display": "Stability",      "file": "stability_trades.json",         "backup": "stability_trades.backup.json"},
    {"name": "breakout",       "display": "Breakout",       "file": "breakout_trades.json",          "backup": "breakout_trades.backup.json"},
]

# ── Risk Limits ──────────────────────────────────────────────────────────────

MAX_OPEN_TOTAL = 20          # across all 10 bots
MAX_OPEN_PER_BOT = 5         # per individual bot
PAUSE_AFTER_LOSSES = 4       # consecutive losses to pause a bot
MAX_PAUSE_DAYS = 3           # auto-unpause after this
DRAWDOWN_LIMIT_PP = -80      # emergency halt if 7-day net P&L drops below this
REGIME_CHANGE_THRESHOLD = 3  # if 3+ bots are losing, declare regime change


# ── State ────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
    return {
        "last_report": None,
        "paused": {},
        "consecutive_losses": {},
        "bot_scores": {},
        "regime": "normal",
        "pause_start": {},
    }


def save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)


# ── Bot Scoring ──────────────────────────────────────────────────────────────

def score_bot(trades: list[dict]) -> dict:
    """Score a bot based on recent performance. Higher = better."""
    closed = [t for t in trades if t["status"] == "closed" and t.get("pnl_pp") is not None]
    open_count = sum(1 for t in trades if t["status"] == "open")

    if len(closed) < 2:
        return {
            "score": 50,  # neutral — not enough data
            "win_rate": 0,
            "avg_pnl": 0,
            "total_pnl": 0,
            "closed": len(closed),
            "open": open_count,
            "grade": "NEW",
        }

    # Recent trades weighted more (last 10)
    recent = sorted(closed, key=lambda t: t.get("exit_time", ""))[-10:]
    pnls = [t["pnl_pp"] for t in recent]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    win_rate = len(wins) / len(recent) * 100 if recent else 0
    avg_pnl = sum(pnls) / len(pnls) if pnls else 0
    total_pnl = sum(t["pnl_pp"] for t in closed)

    # Score components (0-100 scale)
    wr_score = min(win_rate, 100)                    # 0-100
    pnl_score = max(0, min(100, 50 + avg_pnl * 5))  # center at 50
    consistency = (sum(1 for p in pnls if p > 0) / len(pnls) * 100) if pnls else 50

    score = round(wr_score * 0.4 + pnl_score * 0.4 + consistency * 0.2, 1)

    # Letter grade
    if score >= 80:
        grade = "A"
    elif score >= 65:
        grade = "B"
    elif score >= 50:
        grade = "C"
    elif score >= 35:
        grade = "D"
    else:
        grade = "F"

    return {
        "score": score,
        "win_rate": round(win_rate, 1),
        "avg_pnl": round(avg_pnl, 1),
        "total_pnl": round(total_pnl, 1),
        "closed": len(closed),
        "open": open_count,
        "grade": grade,
    }


def count_consecutive_losses(trades: list[dict]) -> int:
    closed = [t for t in trades if t["status"] == "closed"]
    closed.sort(key=lambda t: t.get("exit_time", ""), reverse=True)
    streak = 0
    for t in closed:
        if (t["pnl_pp"] or 0) <= 0:
            streak += 1
        else:
            break
    return streak


# ── Regime Detection ─────────────────────────────────────────────────────────

def detect_regime(all_bot_data: list[dict]) -> str:
    """Detect if we're in a normal or adverse market regime."""
    losing_bots = 0
    for bd in all_bot_data:
        if bd["score_data"]["closed"] >= 3 and bd["score_data"]["win_rate"] < 35:
            losing_bots += 1

    if losing_bots >= REGIME_CHANGE_THRESHOLD:
        return "adverse"
    return "normal"


# ── Pause / Unpause ─────────────────────────────────────────────────────────

def manage_pauses(all_bot_data: list[dict], state: dict) -> list[str]:
    """Decide which bots to pause/unpause."""
    warnings = []
    paused = state.get("paused", {})
    pause_start = state.get("pause_start", {})

    for bd in all_bot_data:
        name = bd["name"]
        losses = bd["consecutive_losses"]

        # Pause logic
        if losses >= PAUSE_AFTER_LOSSES and not paused.get(name, False):
            paused[name] = True
            pause_start[name] = now_str()
            warnings.append(f"{bd['display']} PAUSED — {losses} consecutive losses")
            log.warning("PAUSING %s: %d consecutive losses", name, losses)

        # Unpause if losses broken
        elif losses < PAUSE_AFTER_LOSSES and paused.get(name, False):
            paused[name] = False
            pause_start.pop(name, None)
            warnings.append(f"{bd['display']} UNPAUSED — loss streak broken")

        # Deadlock recovery
        start = pause_start.get(name)
        if start and paused.get(name, False):
            try:
                if days_since(start) >= MAX_PAUSE_DAYS:
                    paused[name] = False
                    pause_start.pop(name, None)
                    warnings.append(f"{bd['display']} AUTO-UNPAUSED after {MAX_PAUSE_DAYS} days")
            except (ValueError, KeyError):
                pass

    state["paused"] = paused
    state["pause_start"] = pause_start
    return warnings


# ── Parameter Adjustment ─────────────────────────────────────────────────────

ADJUST_BOUNDS = {
    "MIN_DRIFT_SCORE":     (1.0, 5.0,  0.3),
    "MIN_CONSISTENCY":     (50,  85,   5),
    "REVERSAL_THRESHOLD":  (3,   8,    1),
    "SPIKE_MIN_RATIO":     (2.0, 8.0,  0.5),
    "SPIKE_MIN_SIZE":      (5,   15,   1),
    "FADE_STOP_PP":        (4,   12,   1),
}


def compute_adjustments(all_bot_data: list[dict]) -> list[dict]:
    """Smart parameter adjustments based on aggregate performance."""
    adjustments = []
    import config

    # Momentum adjustments (based on momentum bot performance)
    mom = next((bd for bd in all_bot_data if bd["name"] == "momentum"), None)
    if mom and mom["score_data"]["closed"] >= 10:
        wr = mom["score_data"]["win_rate"]
        if wr < 40:
            cur = getattr(config, "MIN_DRIFT_SCORE", 2.0)
            new = min(5.0, cur + 0.3)
            if new != cur:
                adjustments.append({"param": "MIN_DRIFT_SCORE", "old": cur, "new": round(new, 1),
                                    "reason": f"Momentum WR {wr:.0f}% < 40% — tightening"})
        elif wr > 65:
            cur = getattr(config, "MIN_DRIFT_SCORE", 2.0)
            new = max(1.0, cur - 0.3)
            if new != cur:
                adjustments.append({"param": "MIN_DRIFT_SCORE", "old": cur, "new": round(new, 1),
                                    "reason": f"Momentum WR {wr:.0f}% > 65% — loosening"})

    # Fade adjustments
    fade = next((bd for bd in all_bot_data if bd["name"] == "fade"), None)
    if fade and fade["score_data"]["closed"] >= 10:
        wr = fade["score_data"]["win_rate"]
        if wr < 40:
            cur = getattr(config, "SPIKE_MIN_RATIO", 3.0)
            new = min(8.0, cur + 0.5)
            if new != cur:
                adjustments.append({"param": "SPIKE_MIN_RATIO", "old": cur, "new": round(new, 1),
                                    "reason": f"Fade WR {wr:.0f}% < 40% — tightening"})

    return adjustments


def apply_adjustments(adjustments: list[dict]) -> None:
    if not adjustments:
        return
    overrides = {}
    if OVERRIDES_FILE.exists():
        try:
            overrides = json.loads(OVERRIDES_FILE.read_text())
        except (json.JSONDecodeError, ValueError):
            pass
    for adj in adjustments:
        overrides[adj["param"]] = adj["new"]
    tmp = OVERRIDES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(overrides, indent=2))
    tmp.replace(OVERRIDES_FILE)


# ── 7-Day Net P&L ───────────────────────────────────────────────────────────

def compute_7day_pnl(all_trades: list[dict]) -> float:
    total = 0.0
    for t in all_trades:
        if t["status"] != "closed" or not t.get("pnl_pp"):
            continue
        try:
            if days_since(t["exit_time"]) <= 7:
                total += t["pnl_pp"]
        except (ValueError, KeyError):
            continue
    return round(total, 1)


# ── Daily Report ─────────────────────────────────────────────────────────────

def should_send_report(state: dict) -> bool:
    last = state.get("last_report")
    if last is None:
        return True
    try:
        return days_since(last) * 24 >= 23
    except (ValueError, KeyError):
        return True


def build_report(all_bot_data: list[dict], state: dict,
                 warnings: list[str], adjustments: list[dict],
                 regime: str, pnl_7d: float) -> str:
    """Build Atlas's comprehensive daily intelligence report."""
    lines = [
        "<b>[ATLAS] CEO Daily Intelligence Report</b>",
        "",
    ]

    # Regime status
    regime_emoji = "NORMAL" if regime == "normal" else "ADVERSE (caution)"
    lines.append(f"<b>Market Regime:</b> {regime_emoji}")
    lines.append(f"7-day Net P&L: {pnl_7d:+.1f}pp")
    lines.append("")

    # Bot scoreboard (sorted by score)
    ranked = sorted(all_bot_data, key=lambda b: b["score_data"]["score"], reverse=True)
    lines.append("<b>Bot Performance Rankings</b>")
    lines.append("─" * 30)

    total_open = 0
    total_closed = 0
    total_pnl = 0

    for i, bd in enumerate(ranked, 1):
        sd = bd["score_data"]
        paused = state.get("paused", {}).get(bd["name"], False)
        status = " [PAUSED]" if paused else ""
        lines.append(
            f"{i}. {bd['display']}{status}\n"
            f"   Grade: {sd['grade']} ({sd['score']}) | "
            f"WR: {sd['win_rate']}% | "
            f"P&L: {sd['total_pnl']:+.1f}pp | "
            f"Open: {sd['open']}"
        )
        total_open += sd["open"]
        total_closed += sd["closed"]
        total_pnl += sd["total_pnl"]

    lines.append("")
    lines.append(f"<b>Portfolio Totals</b>")
    lines.append(f"Open positions: {total_open}/{MAX_OPEN_TOTAL}")
    lines.append(f"Closed trades:  {total_closed}")
    lines.append(f"Combined P&L:   {total_pnl:+.1f}pp")

    # Warnings
    if warnings:
        lines.append("")
        lines.append("<b>Warnings</b>")
        for w in warnings:
            lines.append(f"- {w}")

    # Adjustments
    if adjustments:
        lines.append("")
        lines.append("<b>Parameter Adjustments</b>")
        for a in adjustments:
            lines.append(f"- {a['param']}: {a['old']} -> {a['new']}")
            lines.append(f"  {a['reason']}")

    return "\n".join(lines)


# ── Pre-trade hooks (called by bots via intelligence.py compatibility) ───────

def should_allow_new_trade(bot: str) -> bool:
    """Quick check called by each bot before scanning."""
    state = load_state()
    if state.get("paused", {}).get(bot, False):
        return False

    # Count all open trades
    total_open = 0
    my_open = 0
    for bd in ALL_BOTS:
        trades = load_trades(bd["file"], bd["backup"])
        open_count = sum(1 for t in trades if t["status"] == "open")
        total_open += open_count
        if bd["name"] == bot:
            my_open = open_count

    if total_open >= MAX_OPEN_TOTAL:
        return False
    if my_open >= MAX_OPEN_PER_BOT:
        return False
    return True


def check_pre_trade_conflict(market_id: str, direction: str, bot: str) -> bool:
    """Block trade if another bot has an opposing open position."""
    for bd in ALL_BOTS:
        if bd["name"] == bot:
            continue
        trades = load_trades(bd["file"], bd["backup"])
        for t in trades:
            if t["market_id"] == market_id and t["status"] == "open":
                if t["direction"] != direction:
                    log.info("CONFLICT: %s blocked — %s has opposing position", bot, bd["name"])
                    return True
    return False


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"Atlas (CEO)  [{now_str()}]")
    print("=" * 60)

    state = load_state()

    # 1. Score every bot
    all_bot_data = []
    all_trades = []
    for bd in ALL_BOTS:
        trades = load_trades(bd["file"], bd["backup"])
        all_trades.extend(trades)
        score = score_bot(trades)
        losses = count_consecutive_losses(trades)
        all_bot_data.append({
            **bd,
            "trades": trades,
            "score_data": score,
            "consecutive_losses": losses,
        })

    # Print scoreboard
    ranked = sorted(all_bot_data, key=lambda b: b["score_data"]["score"], reverse=True)
    print("\nBot Rankings:")
    for i, bd in enumerate(ranked, 1):
        sd = bd["score_data"]
        print(f"  {i}. {bd['display']:20s} Grade:{sd['grade']}  Score:{sd['score']:5.1f}  "
              f"WR:{sd['win_rate']:5.1f}%  P&L:{sd['total_pnl']:+7.1f}pp  "
              f"Open:{sd['open']}  Closed:{sd['closed']}")

    # 2. Manage pauses
    warnings = manage_pauses(all_bot_data, state)
    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  {w}")

    # 3. Store scores + losses
    state["bot_scores"] = {bd["name"]: bd["score_data"] for bd in all_bot_data}
    state["consecutive_losses"] = {bd["name"]: bd["consecutive_losses"] for bd in all_bot_data}

    # 4. Regime detection
    regime = detect_regime(all_bot_data)
    state["regime"] = regime
    if regime == "adverse":
        print(f"\nREGIME: ADVERSE — multiple bots underperforming")
    else:
        print(f"\nRegime: normal")

    # 5. Parameter adjustments
    adjustments = compute_adjustments(all_bot_data)
    if adjustments:
        print("\nAdjustments:")
        for a in adjustments:
            print(f"  {a['param']}: {a['old']} -> {a['new']} ({a['reason']})")
        apply_adjustments(adjustments)

    # 6. 7-day P&L
    pnl_7d = compute_7day_pnl(all_trades)
    print(f"\n7-day net P&L: {pnl_7d:+.1f}pp")

    if pnl_7d <= DRAWDOWN_LIMIT_PP:
        print("EMERGENCY: Drawdown limit breached — pausing ALL bots")
        for bd in ALL_BOTS:
            state.setdefault("paused", {})[bd["name"]] = True
        warnings.append(f"EMERGENCY HALT: 7-day P&L {pnl_7d:+.1f}pp < {DRAWDOWN_LIMIT_PP}pp")

    # 7. Daily report
    if should_send_report(state):
        print("\nSending daily intelligence report...")
        report = build_report(all_bot_data, state, warnings, adjustments, regime, pnl_7d)
        send(report)
        state["last_report"] = now_str()

    save_state(state)
    print("\nAtlas (CEO) complete.")


if __name__ == "__main__":
    main()
