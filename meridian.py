from __future__ import annotations
"""
Meridian — President / COO of the trading system.

The tactical operations manager. Runs BEFORE Atlas and handles:
  1. Position deconfliction — finds markets where multiple bots have positions
     and flags overcrowding or opposing bets
  2. Capital allocation — redistributes capital weight to hot bots
  3. Correlation risk — detects if portfolio is too exposed to one direction
  4. Market overlap audit — tracks which markets are most popular across bots
  5. Stale position cleanup — flags trades that should have been closed
"""

import json
import logging
from pathlib import Path
from collections import defaultdict

from bot_engine import (
    load_trades, now_str, days_since,
)
from notify import send

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("meridian")

STATE_FILE = Path("meridian_state.json")

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
        "last_run": None,
        "conflicts": [],
        "overlaps": {},
        "direction_exposure": {},
        "capital_weights": {},
    }


def save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)


# ── Position Deconfliction ───────────────────────────────────────────────────

def find_conflicts(all_open: list[dict]) -> list[dict]:
    """Find markets where multiple bots have conflicting positions."""
    by_market = defaultdict(list)
    for t in all_open:
        by_market[t["market_id"]].append(t)

    conflicts = []
    for mid, positions in by_market.items():
        if len(positions) < 2:
            continue

        directions = set(t["direction"] for t in positions)
        if len(directions) > 1:
            # Active conflict — bots betting opposite directions
            conflicts.append({
                "type": "opposing",
                "market_id": mid,
                "question": positions[0]["question"],
                "positions": [
                    {"bot": t.get("_bot", "?"), "direction": t["direction"],
                     "entry_prob": t["entry_prob"]}
                    for t in positions
                ],
            })
        elif len(positions) >= 3:
            # Overcrowding — too many bots in the same market
            conflicts.append({
                "type": "overcrowded",
                "market_id": mid,
                "question": positions[0]["question"],
                "bot_count": len(positions),
                "direction": positions[0]["direction"],
            })

    return conflicts


# ── Correlation / Direction Exposure ─────────────────────────────────────────

def compute_direction_exposure(all_open: list[dict]) -> dict:
    """Check if the portfolio is lopsided (too many YES or NO bets)."""
    yes_count = sum(1 for t in all_open if t["direction"] == "BUY YES")
    no_count = sum(1 for t in all_open if t["direction"] == "BUY NO")
    total = yes_count + no_count

    yes_stake = sum(t.get("stake", 50) for t in all_open if t["direction"] == "BUY YES")
    no_stake = sum(t.get("stake", 50) for t in all_open if t["direction"] == "BUY NO")
    total_stake = yes_stake + no_stake

    return {
        "yes_count": yes_count,
        "no_count": no_count,
        "total": total,
        "yes_stake": round(yes_stake, 1),
        "no_stake": round(no_stake, 1),
        "total_stake": round(total_stake, 1),
        "yes_pct": round(yes_stake / total_stake * 100, 1) if total_stake > 0 else 50,
        "balance": "balanced" if total == 0 else
                   ("YES-heavy" if yes_stake > no_stake * 1.5 else
                    ("NO-heavy" if no_stake > yes_stake * 1.5 else "balanced")),
    }


# ── Market Overlap Audit ────────────────────────────────────────────────────

def audit_market_overlap(all_open: list[dict]) -> dict:
    """Track which markets have the most bot attention."""
    by_market = defaultdict(list)
    for t in all_open:
        by_market[t["market_id"]].append(t.get("_bot", "?"))

    multi = {mid: bots for mid, bots in by_market.items() if len(bots) >= 2}
    return multi


# ── Stale Position Detection ────────────────────────────────────────────────

def find_stale_positions(all_open: list[dict]) -> list[dict]:
    """Find positions that are older than expected max duration."""
    stale = []
    for t in all_open:
        try:
            age = days_since(t["entry_time"])
            if age > 14:  # any trade older than 14 days is suspicious
                stale.append({
                    "bot": t.get("_bot", "?"),
                    "question": t["question"][:50],
                    "age_days": round(age, 1),
                    "direction": t["direction"],
                })
        except (ValueError, KeyError):
            continue
    return stale


# ── Capital Allocation Weights ───────────────────────────────────────────────

def compute_capital_weights(bot_scores: dict) -> dict:
    """
    Assign capital weights to each bot based on Atlas's scores.
    Better-performing bots get more capital; struggling bots get less.
    Returns multipliers (1.0 = normal, 1.3 = bonus, 0.7 = reduced).
    """
    if not bot_scores:
        return {bd["name"]: 1.0 for bd in ALL_BOTS}

    weights = {}
    for bd in ALL_BOTS:
        sd = bot_scores.get(bd["name"], {})
        score = sd.get("score", 50)
        grade = sd.get("grade", "NEW")

        if grade == "A":
            weights[bd["name"]] = 1.3   # top performer bonus
        elif grade == "B":
            weights[bd["name"]] = 1.1
        elif grade in ("C", "NEW"):
            weights[bd["name"]] = 1.0   # neutral
        elif grade == "D":
            weights[bd["name"]] = 0.8   # reduced
        else:  # F
            weights[bd["name"]] = 0.6   # heavily reduced

    return weights


# ── Report ───────────────────────────────────────────────────────────────────

def build_report(conflicts: list[dict], exposure: dict,
                 overlaps: dict, stale: list[dict],
                 weights: dict, all_open: list[dict]) -> str:
    """Build Meridian's tactical operations report."""
    lines = [
        "<b>[MERIDIAN] President Operations Report</b>",
        "",
        f"<b>Position Overview</b>",
        f"Total open: {len(all_open)}",
        f"Direction: {exposure['yes_count']} YES / {exposure['no_count']} NO "
        f"({exposure['balance']})",
        f"Capital deployed: {exposure['total_stake']:.0f} Mana "
        f"(YES: {exposure['yes_stake']:.0f} / NO: {exposure['no_stake']:.0f})",
    ]

    if conflicts:
        lines.append("")
        lines.append(f"<b>Conflicts ({len(conflicts)})</b>")
        for c in conflicts:
            if c["type"] == "opposing":
                lines.append(f"- OPPOSING: {c['question'][:45]}...")
                for p in c["positions"]:
                    lines.append(f"  {p['bot']}: {p['direction']} @ {p['entry_prob']}%")
            else:
                lines.append(f"- CROWDED: {c['question'][:45]}... ({c['bot_count']} bots)")

    if overlaps:
        lines.append("")
        lines.append(f"<b>Multi-bot Markets</b>")
        for mid, bots in list(overlaps.items())[:5]:
            lines.append(f"- {len(bots)} bots: {', '.join(bots)}")

    if stale:
        lines.append("")
        lines.append(f"<b>Stale Positions ({len(stale)})</b>")
        for s in stale[:5]:
            lines.append(f"- {s['bot']}: {s['question']}... ({s['age_days']}d old)")

    # Capital allocation
    lines.append("")
    lines.append("<b>Capital Weights</b>")
    for bd in ALL_BOTS:
        w = weights.get(bd["name"], 1.0)
        bar = "+" * int(w * 5) if w >= 1.0 else "-" * int((1.0 - w) * 10)
        lines.append(f"  {bd['display']:20s} {w:.1f}x {bar}")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"Meridian (President/COO)  [{now_str()}]")
    print("=" * 60)

    state = load_state()

    # Load all open trades across all bots
    all_open = []
    for bd in ALL_BOTS:
        trades = load_trades(bd["file"], bd["backup"])
        for t in trades:
            if t["status"] == "open":
                t["_bot"] = bd["name"]
                all_open.append(t)

    print(f"\nTotal open positions: {len(all_open)}")

    # 1. Conflict detection
    conflicts = find_conflicts(all_open)
    if conflicts:
        print(f"\nConflicts: {len(conflicts)}")
        for c in conflicts:
            print(f"  [{c['type'].upper()}] {c['question'][:50]}...")
        # Alert on opposing conflicts
        for c in conflicts:
            if c["type"] == "opposing":
                from notify import send as _send
                _send(f"<b>[MERIDIAN] Conflict Detected</b>\n{c['question'][:60]}...\n"
                      f"Multiple bots have opposing positions on this market.")
    else:
        print("\nConflicts: None")

    # 2. Direction exposure
    exposure = compute_direction_exposure(all_open)
    print(f"Direction: {exposure['yes_count']} YES / {exposure['no_count']} NO ({exposure['balance']})")
    print(f"Capital: {exposure['total_stake']:.0f} Mana deployed")

    if exposure["balance"] != "balanced":
        log.warning("Portfolio is %s — consider rebalancing", exposure["balance"])

    # 3. Market overlap
    overlaps = audit_market_overlap(all_open)
    if overlaps:
        print(f"\nMulti-bot markets: {len(overlaps)}")

    # 4. Stale positions
    stale = find_stale_positions(all_open)
    if stale:
        print(f"\nStale positions: {len(stale)}")
        for s in stale:
            print(f"  {s['bot']}: {s['question']}... ({s['age_days']}d)")

    # 5. Capital weights (read Atlas's scores if available)
    atlas_state_file = Path("atlas_state.json")
    bot_scores = {}
    if atlas_state_file.exists():
        try:
            atlas_data = json.loads(atlas_state_file.read_text())
            bot_scores = atlas_data.get("bot_scores", {})
        except (json.JSONDecodeError, ValueError):
            pass

    weights = compute_capital_weights(bot_scores)
    print(f"\nCapital weights:")
    for bd in ALL_BOTS:
        w = weights.get(bd["name"], 1.0)
        print(f"  {bd['display']:20s} {w:.1f}x")

    # 6. Save state
    state["last_run"] = now_str()
    state["conflicts"] = conflicts
    state["overlaps"] = {k: v for k, v in overlaps.items()}
    state["direction_exposure"] = exposure
    state["capital_weights"] = weights
    save_state(state)

    # 7. Send report (every run — Meridian is tactical, reports frequently)
    report = build_report(conflicts, exposure, overlaps, stale, weights, all_open)
    send(report)

    print("\nMeridian (President/COO) complete.")


if __name__ == "__main__":
    main()
