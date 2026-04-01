from __future__ import annotations
"""
Intelligence Layer — Meta-observer sitting above both trading bots.

Runs after both bots each cycle and:
  1. Detects cross-bot conflicts (opposing positions on same market)
  2. Analyzes performance trends (streaks, win rate shifts, loss patterns)
  3. Auto-adjusts parameters (tighten when losing, loosen when winning)
  4. Enforces risk limits (position caps, drawdown breaker, loss pause)
  5. Sends daily intelligence report to Telegram

Also provides pre-trade hooks called by each bot:
  - check_pre_trade_conflict() — blocks a trade if other bot disagrees
  - should_allow_new_trade()   — blocks if risk limits are breached
"""

import json
import logging
from pathlib import Path
from collections import Counter

from config import (
    INTEL_MAX_OPEN_TOTAL, INTEL_MAX_OPEN_PER_BOT,
    INTEL_DRAWDOWN_LIMIT_PP, INTEL_PAUSE_AFTER_LOSSES,
    INTEL_LOOKBACK_TRADES, INTEL_ADJUST_BOUNDS,
    INTEL_DAILY_REPORT_ENABLED, INTEL_MAX_PAUSE_DAYS,
)
from bot_engine import (
    load_trades, compute_metrics, now_str, parse_time, days_since,
    get_market_state, BOT_TRADE_FILES,
)
from notify import (
    intel_conflict_alert, intel_adjustment_alert, intel_report_alert,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("intel")

# All bot trade files — derived from bot_engine registry
ALL_BOT_FILES = BOT_TRADE_FILES

# Bot name mapping for display
BOT_NAMES = {
    "trades.json": "momentum",
    "fade_trades.json": "fade",
    "mean_reversion_trades.json": "mean_reversion",
    "volume_trades.json": "volume_surge",
    "whale_trades.json": "whale",
    "contrarian_trades.json": "contrarian",
    "close_gravity_trades.json": "close_gravity",
    "fresh_sniper_trades.json": "fresh_sniper",
    "stability_trades.json": "stability",
    "breakout_trades.json": "breakout",
    "calibration_trades.json": "calibration",
}

STATE_FILE    = Path("intelligence_state.json")
CONFIG_FILE   = Path("config.py")


# ── State Persistence ─────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            log.warning("Corrupt state file — starting fresh")
    return {
        "last_report": None,
        "adjustments": [],
        "paused": {"momentum": False, "fade": False},
        "consecutive_losses": {"momentum": 0, "fade": 0},
    }


def save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)


# ── Load All Bot Trades ──────────────────────────────────────────────────────

def _load_all_bot_trades() -> dict[str, list[dict]]:
    """Load trades from all bots, keyed by bot name."""
    result = {}
    for tf, bf in ALL_BOT_FILES:
        bot_name = BOT_NAMES.get(tf, tf.replace("_trades.json", ""))
        result[bot_name] = load_trades(tf, bf)
    return result


def _all_trades_flat(bot_trades: dict[str, list[dict]]) -> list[dict]:
    """Flatten all bot trades into a single list."""
    flat = []
    for trades in bot_trades.values():
        flat.extend(trades)
    return flat


# ── Conflict Detection ────────────────────────────────────────────────────────

def find_conflicts(bot_trades: dict[str, list[dict]]) -> list[dict]:
    """Find markets where ANY bots have open opposing positions."""
    # Group open trades by market
    market_positions: dict[str, list[tuple[str, dict]]] = {}
    for bot_name, trades in bot_trades.items():
        for t in trades:
            if t["status"] == "open":
                mid = t["market_id"]
                market_positions.setdefault(mid, []).append((bot_name, t))

    conflicts = []
    for mid, positions in market_positions.items():
        directions = set(t["direction"] for _, t in positions)
        if len(directions) > 1:  # opposing directions on same market
            conflicts.append({
                "market_id": mid,
                "question": positions[0][1]["question"],
                "positions": [
                    {"bot": bot, "direction": t["direction"], "entry_prob": t["entry_prob"]}
                    for bot, t in positions
                ],
            })
    return conflicts


def check_pre_trade_conflict(market_id: str, direction: str, bot: str) -> bool:
    """
    Called by a bot BEFORE logging a trade. Returns True to BLOCK the trade.
    Checks if ANY other bot has an open trade on this market in the opposite direction.
    """
    for tf, bf in ALL_BOT_FILES:
        other_bot = BOT_NAMES.get(tf, tf.replace("_trades.json", ""))
        if other_bot == bot:
            continue
        other_trades = load_trades(tf, bf)
        for t in other_trades:
            if t["market_id"] == market_id and t["status"] == "open":
                if t["direction"] != direction:
                    log.info("CONFLICT BLOCKED: %s wanted %s but %s has %s on %s",
                             bot, direction, other_bot, t["direction"], market_id)
                    return True
    return False


# ── Risk Management ───────────────────────────────────────────────────────────

def count_consecutive_losses(trades: list[dict]) -> int:
    """Count how many of the most recent closed trades are losses."""
    closed = [t for t in trades if t["status"] == "closed"]
    closed.sort(key=lambda t: t.get("exit_time", ""), reverse=True)
    streak = 0
    for t in closed:
        if (t["pnl_pp"] or 0) <= 0:
            streak += 1
        else:
            break
    return streak


def compute_7day_net_pnl(bot_trades: dict[str, list[dict]]) -> float:
    """Net realized P&L in the last 7 days across ALL bots."""
    total = 0.0
    for trades in bot_trades.values():
        for t in trades:
            if t["status"] != "closed":
                continue
            pnl = t["pnl_pp"] or 0
            try:
                if days_since(t["exit_time"]) <= 7:
                    total += pnl
            except (ValueError, KeyError):
                continue
    return round(total, 1)


def compute_unrealized_pnl(bot_trades: dict[str, list[dict]]) -> float:
    """Estimate unrealized P&L across all open positions."""
    total = 0.0
    for trades in bot_trades.values():
        for t in trades:
            if t["status"] != "open":
                continue
            state = get_market_state(t["market_id"])
            if state["status"] != "active":
                continue
            prob = state["probability"]
            entry = t["entry_prob"]
            if t["direction"] == "BUY YES":
                pnl = prob - entry
            else:
                pnl = entry - prob
            total += pnl
    return round(total, 1)


def check_risk_limits(bot_trades: dict[str, list[dict]], state: dict) -> dict:
    """Evaluate portfolio-level risk constraints across ALL bots."""
    # Count open positions per bot
    bot_open_counts = {}
    total_open = 0
    for bot_name, trades in bot_trades.items():
        n_open = sum(1 for t in trades if t["status"] == "open")
        bot_open_counts[bot_name] = n_open
        total_open += n_open

    # P&L checks
    realized_7d = compute_7day_net_pnl(bot_trades)
    unrealized = compute_unrealized_pnl(bot_trades)
    total_drawdown = realized_7d + unrealized  # include unrealized losses

    # Direction skew check
    all_open = [t for trades in bot_trades.values() for t in trades if t["status"] == "open"]
    yes_count = sum(1 for t in all_open if t["direction"] == "BUY YES")
    no_count = sum(1 for t in all_open if t["direction"] == "BUY NO")
    direction_skew = yes_count / max(yes_count + no_count, 1)

    warnings = []

    if total_open >= INTEL_MAX_OPEN_TOTAL:
        warnings.append(f"Position limit reached: {total_open}/{INTEL_MAX_OPEN_TOTAL}")

    for bot_name, n_open in bot_open_counts.items():
        if n_open >= INTEL_MAX_OPEN_PER_BOT:
            warnings.append(f"{bot_name} at per-bot limit: {n_open}/{INTEL_MAX_OPEN_PER_BOT}")

    if total_drawdown <= INTEL_DRAWDOWN_LIMIT_PP:
        warnings.append(f"7-day P&L (realized+unrealized) {total_drawdown:+.1f}pp exceeds limit {INTEL_DRAWDOWN_LIMIT_PP}pp")

    if total_open >= 4 and (direction_skew > 0.75 or direction_skew < 0.25):
        pct = round(max(direction_skew, 1 - direction_skew) * 100)
        warnings.append(f"Direction skew: {pct}% in one direction ({yes_count}Y/{no_count}N)")

    # Pause logic with deadlock recovery for ALL bots
    pause_start = state.get("pause_start", {})
    paused = state.get("paused", {})

    for bot_name, trades in bot_trades.items():
        losses = count_consecutive_losses(trades)
        was_paused = paused.get(bot_name, False)

        if losses >= INTEL_PAUSE_AFTER_LOSSES:
            if not was_paused:
                pause_start[bot_name] = now_str()
            paused[bot_name] = True
            warnings.append(f"{bot_name} PAUSED: {losses} consecutive losses")
        elif was_paused and losses < INTEL_PAUSE_AFTER_LOSSES:
            paused[bot_name] = False
            pause_start.pop(bot_name, None)

        # Deadlock recovery
        start = pause_start.get(bot_name)
        if start:
            try:
                pause_days = days_since(start)
                if pause_days >= INTEL_MAX_PAUSE_DAYS:
                    paused[bot_name] = False
                    pause_start.pop(bot_name, None)
                    warnings.append(f"{bot_name} AUTO-UNPAUSED after {pause_days:.1f} days")
            except (ValueError, KeyError):
                pass

    state["pause_start"] = pause_start
    state["paused"] = paused

    return {
        "total_open": total_open,
        "bot_open_counts": bot_open_counts,
        "realized_7d": realized_7d,
        "unrealized": unrealized,
        "total_drawdown": total_drawdown,
        "direction_skew": round(direction_skew, 2),
        "paused": paused,
        "warnings": warnings,
    }


def should_allow_new_trade(bot: str) -> bool:
    """Quick check called by each bot before scanning for signals."""
    state = load_state()

    if state.get("paused", {}).get(bot, False):
        log.warning("%s bot is PAUSED by intelligence layer", bot)
        return False

    # Count total open across ALL bots
    total_open = 0
    my_open = 0
    for tf, bf in ALL_BOT_FILES:
        bot_name = BOT_NAMES.get(tf, tf.replace("_trades.json", ""))
        trades = load_trades(tf, bf)
        n_open = sum(1 for t in trades if t["status"] == "open")
        total_open += n_open
        if bot_name == bot:
            my_open = n_open

    if total_open >= INTEL_MAX_OPEN_TOTAL:
        log.warning("Total position limit reached (%d/%d) — blocking %s",
                     total_open, INTEL_MAX_OPEN_TOTAL, bot)
        return False

    if my_open >= INTEL_MAX_OPEN_PER_BOT:
        log.warning("%s at per-bot limit (%d/%d)", bot, my_open, INTEL_MAX_OPEN_PER_BOT)
        return False

    return True


# ── Performance Analysis ──────────────────────────────────────────────────────

def get_recent_closed(trades: list[dict], n: int) -> list[dict]:
    """Get the last N closed trades in chronological order."""
    closed = [t for t in trades if t["status"] == "closed"]
    closed.sort(key=lambda t: t.get("exit_time", ""))
    return closed[-n:]


def detect_performance_trends(bot_trades: dict[str, list[dict]]) -> list[str]:
    """Identify notable patterns from trade history across all bots."""
    trends = []

    for name, trades in bot_trades.items():
        closed = [t for t in trades if t["status"] == "closed"]
        if len(closed) < 3:
            continue

        # Losing/winning streaks
        closed.sort(key=lambda t: t.get("exit_time", ""))
        streak_type = None
        streak_len = 0
        for t in reversed(closed):
            pnl = t["pnl_pp"] or 0
            s = "W" if pnl > 0 else "L"
            if streak_type is None:
                streak_type = s
                streak_len = 1
            elif s == streak_type:
                streak_len += 1
            else:
                break
        if streak_len >= 3:
            word = "winning" if streak_type == "W" else "losing"
            trends.append(f"{name}: {streak_len}-trade {word} streak")

        # Dominant loss reason
        losses = [t for t in closed if (t["pnl_pp"] or 0) < 0]
        if len(losses) >= 3:
            reasons = Counter(t.get("exit_reason", "unknown") for t in losses)
            top_reason, top_count = reasons.most_common(1)[0]
            pct = top_count / len(losses) * 100
            if pct >= 60:
                trends.append(f"{name}: {top_reason} exits = {pct:.0f}% of losses")

        # Win rate trend (recent vs all-time)
        if len(closed) >= INTEL_LOOKBACK_TRADES:
            recent = closed[-INTEL_LOOKBACK_TRADES:]
            all_wr = sum(1 for t in closed if (t["pnl_pp"] or 0) > 0) / len(closed) * 100
            rec_wr = sum(1 for t in recent if (t["pnl_pp"] or 0) > 0) / len(recent) * 100
            diff = rec_wr - all_wr
            if abs(diff) >= 15:
                direction = "improving" if diff > 0 else "declining"
                trends.append(f"{name}: win rate {direction} "
                              f"(recent {rec_wr:.0f}% vs all-time {all_wr:.0f}%)")

        # Direction bias
        yes_trades = [t for t in closed if t["direction"] == "BUY YES"]
        no_trades = [t for t in closed if t["direction"] == "BUY NO"]
        if len(yes_trades) >= 3 and len(no_trades) >= 3:
            yes_wr = sum(1 for t in yes_trades if (t["pnl_pp"] or 0) > 0) / len(yes_trades) * 100
            no_wr = sum(1 for t in no_trades if (t["pnl_pp"] or 0) > 0) / len(no_trades) * 100
            if abs(yes_wr - no_wr) >= 20:
                better = "BUY YES" if yes_wr > no_wr else "BUY NO"
                trends.append(f"{name}: {better} significantly outperforming "
                              f"(YES:{yes_wr:.0f}% vs NO:{no_wr:.0f}%)")

    if not trends:
        trends.append("Not enough data for trend analysis yet")

    return trends


# ── Auto-Adjustment ───────────────────────────────────────────────────────────

def compute_adjustments(bot_trades: dict[str, list[dict]]) -> list[dict]:
    """Decide what params to tighten/loosen based on recent performance across all bots."""
    adjustments = []

    # Aggregate all closed trades for system-wide analysis
    all_closed = []
    for trades in bot_trades.values():
        all_closed.extend([t for t in trades if t["status"] == "closed"])

    if len(all_closed) < INTEL_LOOKBACK_TRADES:
        return adjustments

    all_closed.sort(key=lambda t: t.get("exit_time", ""))
    recent = all_closed[-INTEL_LOOKBACK_TRADES:]
    wr = sum(1 for t in recent if (t["pnl_pp"] or 0) > 0) / len(recent) * 100
    losses = [t for t in recent if (t["pnl_pp"] or 0) < 0]
    avg_loss = sum(t["pnl_pp"] or 0 for t in losses) / len(losses) if losses else 0

    import config

    # System-wide drift score adjustment
    cur_drift = getattr(config, "MIN_DRIFT_SCORE", 1.5)
    if wr < 40:
        adj = _make_adjustment("MIN_DRIFT_SCORE", cur_drift, "tighten",
                               f"System WR {wr:.0f}% < 40% — tighten signals")
        if adj:
            adjustments.append(adj)
    elif wr > 65:
        adj = _make_adjustment("MIN_DRIFT_SCORE", cur_drift, "loosen",
                               f"System WR {wr:.0f}% > 65% — loosen signals")
        if adj:
            adjustments.append(adj)

    # Stop loss adjustment based on avg loss size
    cur_reversal = getattr(config, "REVERSAL_THRESHOLD", 4)
    if avg_loss < -8:
        adj = _make_adjustment("REVERSAL_THRESHOLD", cur_reversal, "tighten",
                               f"Avg loss {avg_loss:.1f}pp — tighten stops")
        if adj:
            adjustments.append(adj)

    # Fade-specific adjustments
    fade_trades_list = bot_trades.get("fade", [])
    fade_closed = [t for t in fade_trades_list if t["status"] == "closed"]
    if len(fade_closed) >= INTEL_LOOKBACK_TRADES:
        fade_recent = fade_closed[-INTEL_LOOKBACK_TRADES:]
        fade_wr = sum(1 for t in fade_recent if (t["pnl_pp"] or 0) > 0) / len(fade_recent) * 100
        cur_ratio = getattr(config, "SPIKE_MIN_RATIO", 2.5)
        if fade_wr < 40:
            adj = _make_adjustment("SPIKE_MIN_RATIO", cur_ratio, "tighten",
                                   f"Fade WR {fade_wr:.0f}% < 40%")
            if adj:
                adjustments.append(adj)

    return adjustments


def _make_adjustment(param: str, current: float, direction: str, reason: str) -> dict | None:
    """Create an adjustment dict, respecting bounds."""
    bounds = INTEL_ADJUST_BOUNDS.get(param)
    if not bounds:
        return None
    lo, hi, step = bounds

    if direction == "tighten":
        new_val = current + step
    else:
        new_val = current - step

    # Clamp to bounds
    new_val = max(lo, min(hi, new_val))

    # Skip if no change
    if new_val == current:
        return None

    # Round nicely
    if isinstance(current, float):
        new_val = round(new_val, 1)
    else:
        new_val = int(round(new_val))

    return {"param": param, "old": current, "new": new_val, "reason": reason}


OVERRIDES_FILE = Path("config_overrides.json")


def apply_adjustments(adjustments: list[dict]) -> None:
    """Write adjusted values to config_overrides.json (loaded by config.py at import).

    Previous version modified config.py source code via regex, which was fragile
    and risked corrupting the config file. JSON overrides are structured, safe,
    and cleanly separated from the base config.
    """
    if not adjustments:
        return

    # Load existing overrides
    overrides = {}
    if OVERRIDES_FILE.exists():
        try:
            overrides = json.loads(OVERRIDES_FILE.read_text())
        except (json.JSONDecodeError, ValueError):
            pass

    for adj in adjustments:
        overrides[adj["param"]] = adj["new"]
        log.info("ADJUSTED: %s = %s (was %s) — %s",
                 adj["param"], adj["new"], adj["old"], adj["reason"])

    # Atomic write
    tmp = OVERRIDES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(overrides, indent=2))
    tmp.replace(OVERRIDES_FILE)


# ── Daily Report ──────────────────────────────────────────────────────────────

def should_send_report(state: dict) -> bool:
    if not INTEL_DAILY_REPORT_ENABLED:
        return False
    last = state.get("last_report")
    if last is None:
        return True
    try:
        hours = days_since(last) * 24
        return hours >= 23
    except (ValueError, KeyError):
        return True


def build_daily_report(bot_trades: dict[str, list[dict]],
                       conflicts: list[dict], risk: dict,
                       trends: list[str], adjustments: list[dict]) -> str:
    """Build the Telegram daily intelligence report for all bots."""
    lines = [
        f"<b>[INTEL] Daily Intelligence Report</b>",
        "",
        f"<b>Portfolio</b>",
        f"Open: {risk['total_open']}/{INTEL_MAX_OPEN_TOTAL}",
        f"P&L (7d): {risk['realized_7d']:+.1f}pp realized, {risk['unrealized']:+.1f}pp unrealized",
        f"Direction: {risk['direction_skew']:.0%} YES / {1-risk['direction_skew']:.0%} NO",
        "",
    ]

    # Per-bot summaries
    total_pnl = 0.0
    for bot_name, trades in bot_trades.items():
        metrics = compute_metrics(trades)
        is_paused = risk["paused"].get(bot_name, False)
        status = "PAUSED" if is_paused else "ACTIVE"
        n_open = risk["bot_open_counts"].get(bot_name, 0)

        if metrics.get("total_trades"):
            total_pnl += metrics["total_pnl"]
            lines.append(f"<b>{bot_name}</b> [{status}] Open:{n_open} "
                         f"WR:{metrics['win_rate']}% P&L:{metrics['total_pnl']:+.1f}pp")
        elif n_open > 0:
            lines.append(f"<b>{bot_name}</b> [{status}] Open:{n_open} (no closed trades)")

    lines.append(f"\nTotal P&L: {total_pnl:+.1f}pp")

    # Conflicts
    if conflicts:
        lines.append(f"\n<b>Conflicts:</b> {len(conflicts)}")
        for c in conflicts:
            lines.append(f"  {c['question'][:50]}...")
    else:
        lines.append("\nConflicts: None")

    # Warnings
    if risk["warnings"]:
        lines.append("")
        for w in risk["warnings"]:
            lines.append(f"WARNING: {w}")

    # Trends
    lines.append("\n<b>Trends</b>")
    for t in trends[:5]:
        lines.append(f"- {t}")

    # Adjustments
    if adjustments:
        lines.append("\n<b>Adjustments</b>")
        for a in adjustments:
            lines.append(f"- {a['param']}: {a['old']} -> {a['new']}")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"Intelligence Layer  [{now_str()}]")
    print("=" * 60)

    # Load ALL bot trades
    bot_trades = _load_all_bot_trades()
    state = load_state()

    total_trades = sum(len(t) for t in bot_trades.values())
    active_bots = sum(1 for t in bot_trades.values() if t)
    print(f"\nMonitoring {active_bots} bots, {total_trades} total trades\n")

    # 1. Conflict detection
    conflicts = find_conflicts(bot_trades)
    if conflicts:
        print(f"CONFLICTS FOUND: {len(conflicts)}")
        for c in conflicts:
            print(f"  {c['question'][:50]}")
            for p in c["positions"]:
                print(f"    {p['bot']}: {p['direction']}")
            intel_conflict_alert(c)
    else:
        print("Conflicts: None")

    # 2. Risk management
    risk = check_risk_limits(bot_trades, state)
    print(f"\nRisk: {risk['total_open']}/{INTEL_MAX_OPEN_TOTAL} positions  "
          f"| 7d P&L: {risk['realized_7d']:+.1f}pp realized, {risk['unrealized']:+.1f}pp unrealized")
    if risk["warnings"]:
        for w in risk["warnings"]:
            print(f"  WARNING: {w}")

    # 3. Performance trends
    trends = detect_performance_trends(bot_trades)
    print(f"\nTrends:")
    for t in trends:
        print(f"  - {t}")

    # 4. Auto-adjustment
    adjustments = compute_adjustments(bot_trades)
    if adjustments:
        print(f"\nAdjustments:")
        for a in adjustments:
            print(f"  {a['param']}: {a['old']} -> {a['new']} ({a['reason']})")
        apply_adjustments(adjustments)
        intel_adjustment_alert(adjustments)
        state.setdefault("adjustments", []).extend(adjustments)
    else:
        print("\nAdjustments: None")

    # 5. Daily report
    if should_send_report(state):
        print("\nSending daily intelligence report...")
        report = build_daily_report(bot_trades, conflicts, risk, trends, adjustments)
        intel_report_alert(report)
        state["last_report"] = now_str()
        print("  Sent.")
    else:
        print("\nDaily report: not due yet")

    # 6. Save state
    save_state(state)
    print("\nIntelligence layer complete.")


if __name__ == "__main__":
    main()
