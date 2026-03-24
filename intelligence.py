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
import re
import logging
from pathlib import Path
from collections import Counter

from config import (
    INTEL_MAX_OPEN_TOTAL, INTEL_MAX_OPEN_PER_BOT,
    INTEL_DRAWDOWN_LIMIT_PP, INTEL_PAUSE_AFTER_LOSSES,
    INTEL_LOOKBACK_TRADES, INTEL_ADJUST_BOUNDS,
    INTEL_DAILY_REPORT_ENABLED,
)
from paper_trades import load_trades, compute_metrics, now_str, parse_time, days_since
from notify import (
    intel_conflict_alert, intel_adjustment_alert, intel_report_alert,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("intel")

MOMENTUM_FILE = Path("trades.json")
MOMENTUM_BAK  = Path("trades.backup.json")
FADE_FILE     = Path("fade_trades.json")
FADE_BAK      = Path("fade_trades.backup.json")
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


# ── Conflict Detection ────────────────────────────────────────────────────────

def find_conflicts(mom_trades: list[dict], fade_trades: list[dict]) -> list[dict]:
    """Find markets where both bots have open opposing positions."""
    mom_open = {t["market_id"]: t for t in mom_trades if t["status"] == "open"}
    fade_open = {t["market_id"]: t for t in fade_trades if t["status"] == "open"}

    conflicts = []
    for mid in set(mom_open) & set(fade_open):
        mt = mom_open[mid]
        ft = fade_open[mid]
        if mt["direction"] != ft["direction"]:
            conflicts.append({
                "market_id":      mid,
                "question":       mt["question"],
                "momentum_dir":   mt["direction"],
                "momentum_entry": mt["entry_prob"],
                "fade_dir":       ft["direction"],
                "fade_entry":     ft["entry_prob"],
            })
    return conflicts


def check_pre_trade_conflict(market_id: str, direction: str, bot: str) -> bool:
    """
    Called by a bot BEFORE logging a trade. Returns True to BLOCK the trade.
    Checks if the OTHER bot has an open trade on this market in the opposite direction.
    """
    if bot == "momentum":
        other_trades = load_trades(FADE_FILE, FADE_BAK)
    else:
        other_trades = load_trades(MOMENTUM_FILE, MOMENTUM_BAK)

    for t in other_trades:
        if t["market_id"] == market_id and t["status"] == "open":
            if t["direction"] != direction:
                log.info("CONFLICT BLOCKED: %s bot wanted %s but %s bot has %s on %s",
                         bot, direction, "fade" if bot == "momentum" else "momentum",
                         t["direction"], market_id)
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


def compute_7day_drawdown(mom_trades: list[dict], fade_trades: list[dict]) -> float:
    """Sum of realized losses in the last 7 days across both bots."""
    total = 0.0
    for trades in [mom_trades, fade_trades]:
        for t in trades:
            if t["status"] != "closed":
                continue
            pnl = t["pnl_pp"] or 0
            if pnl >= 0:
                continue
            try:
                if days_since(t["exit_time"]) <= 7:
                    total += pnl
            except (ValueError, KeyError):
                continue
    return round(total, 1)


def check_risk_limits(mom_trades: list[dict], fade_trades: list[dict],
                      state: dict) -> dict:
    """Evaluate portfolio-level risk constraints."""
    mom_open = [t for t in mom_trades if t["status"] == "open"]
    fade_open = [t for t in fade_trades if t["status"] == "open"]
    total_open = len(mom_open) + len(fade_open)

    mom_losses = count_consecutive_losses(mom_trades)
    fade_losses = count_consecutive_losses(fade_trades)
    drawdown = compute_7day_drawdown(mom_trades, fade_trades)

    warnings = []
    mom_paused = state.get("paused", {}).get("momentum", False)
    fade_paused = state.get("paused", {}).get("fade", False)

    if total_open >= INTEL_MAX_OPEN_TOTAL:
        warnings.append(f"Position limit reached: {total_open}/{INTEL_MAX_OPEN_TOTAL}")
    if len(mom_open) >= INTEL_MAX_OPEN_PER_BOT:
        warnings.append(f"Momentum at per-bot limit: {len(mom_open)}/{INTEL_MAX_OPEN_PER_BOT}")
    if len(fade_open) >= INTEL_MAX_OPEN_PER_BOT:
        warnings.append(f"Fade at per-bot limit: {len(fade_open)}/{INTEL_MAX_OPEN_PER_BOT}")
    if drawdown <= INTEL_DRAWDOWN_LIMIT_PP:
        warnings.append(f"7-day drawdown {drawdown}pp exceeds limit {INTEL_DRAWDOWN_LIMIT_PP}pp")

    if mom_losses >= INTEL_PAUSE_AFTER_LOSSES:
        mom_paused = True
        warnings.append(f"Momentum PAUSED: {mom_losses} consecutive losses")
    elif mom_paused and mom_losses < INTEL_PAUSE_AFTER_LOSSES:
        mom_paused = False

    if fade_losses >= INTEL_PAUSE_AFTER_LOSSES:
        fade_paused = True
        warnings.append(f"Fade PAUSED: {fade_losses} consecutive losses")
    elif fade_paused and fade_losses < INTEL_PAUSE_AFTER_LOSSES:
        fade_paused = False

    return {
        "total_open": total_open,
        "mom_open": len(mom_open),
        "fade_open": len(fade_open),
        "drawdown_7d": drawdown,
        "mom_consecutive_losses": mom_losses,
        "fade_consecutive_losses": fade_losses,
        "mom_paused": mom_paused,
        "fade_paused": fade_paused,
        "warnings": warnings,
    }


def should_allow_new_trade(bot: str) -> bool:
    """Quick check called by each bot before scanning for signals."""
    state = load_state()

    if state.get("paused", {}).get(bot, False):
        log.warning("%s bot is PAUSED by intelligence layer", bot)
        return False

    mom_trades = load_trades(MOMENTUM_FILE, MOMENTUM_BAK)
    fade_trades = load_trades(FADE_FILE, FADE_BAK)
    mom_open = sum(1 for t in mom_trades if t["status"] == "open")
    fade_open = sum(1 for t in fade_trades if t["status"] == "open")

    if mom_open + fade_open >= INTEL_MAX_OPEN_TOTAL:
        log.warning("Total position limit reached (%d/%d) — blocking %s",
                     mom_open + fade_open, INTEL_MAX_OPEN_TOTAL, bot)
        return False

    my_open = mom_open if bot == "momentum" else fade_open
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


def detect_performance_trends(mom_trades: list[dict],
                               fade_trades: list[dict]) -> list[str]:
    """Identify notable patterns from trade history."""
    trends = []

    for name, trades in [("Momentum", mom_trades), ("Fade", fade_trades)]:
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

def compute_adjustments(mom_trades: list[dict],
                         fade_trades: list[dict]) -> list[dict]:
    """Decide what params to tighten/loosen based on recent performance."""
    adjustments = []

    # Need enough data
    mom_closed = [t for t in mom_trades if t["status"] == "closed"]
    fade_closed = [t for t in fade_trades if t["status"] == "closed"]

    # Momentum bot adjustments
    if len(mom_closed) >= INTEL_LOOKBACK_TRADES:
        recent = mom_closed[-INTEL_LOOKBACK_TRADES:]
        wr = sum(1 for t in recent if (t["pnl_pp"] or 0) > 0) / len(recent) * 100
        losses = [t for t in recent if (t["pnl_pp"] or 0) < 0]
        avg_loss = sum(t["pnl_pp"] or 0 for t in losses) / len(losses) if losses else 0

        # Import current values
        import config
        cur_drift = getattr(config, "MIN_DRIFT_SCORE", 2.0)
        cur_consist = getattr(config, "MIN_CONSISTENCY", 65)
        cur_reversal = getattr(config, "REVERSAL_THRESHOLD", 6)

        if wr < 40:
            adj = _make_adjustment("MIN_DRIFT_SCORE", cur_drift, "tighten",
                                   f"Momentum recent WR {wr:.0f}% < 40%")
            if adj:
                adjustments.append(adj)
        elif wr > 65:
            adj = _make_adjustment("MIN_DRIFT_SCORE", cur_drift, "loosen",
                                   f"Momentum recent WR {wr:.0f}% > 65%")
            if adj:
                adjustments.append(adj)

        # Reversal threshold based on avg loss size
        if avg_loss < -8:
            adj = _make_adjustment("REVERSAL_THRESHOLD", cur_reversal, "tighten",
                                   f"Momentum avg loss {avg_loss:.1f}pp > 8pp")
            if adj:
                adjustments.append(adj)
        elif losses and avg_loss > -4:
            adj = _make_adjustment("REVERSAL_THRESHOLD", cur_reversal, "loosen",
                                   f"Momentum avg loss {avg_loss:.1f}pp < 4pp")
            if adj:
                adjustments.append(adj)

        # Consistency based on reversal exits
        reversal_losses = [t for t in losses if t.get("exit_reason") == "reversal"]
        if losses and len(reversal_losses) / len(losses) > 0.5:
            adj = _make_adjustment("MIN_CONSISTENCY", cur_consist, "tighten",
                                   f"Reversals = {len(reversal_losses)}/{len(losses)} of momentum losses")
            if adj:
                adjustments.append(adj)

    # Fade bot adjustments
    if len(fade_closed) >= INTEL_LOOKBACK_TRADES:
        recent = fade_closed[-INTEL_LOOKBACK_TRADES:]
        wr = sum(1 for t in recent if (t["pnl_pp"] or 0) > 0) / len(recent) * 100
        losses = [t for t in recent if (t["pnl_pp"] or 0) < 0]
        avg_loss = sum(t["pnl_pp"] or 0 for t in losses) / len(losses) if losses else 0

        import config
        cur_ratio = getattr(config, "SPIKE_MIN_RATIO", 3.0)
        cur_size = getattr(config, "SPIKE_MIN_SIZE", 8)
        cur_stop = getattr(config, "FADE_STOP_PP", 8)

        if wr < 40:
            adj = _make_adjustment("SPIKE_MIN_RATIO", cur_ratio, "tighten",
                                   f"Fade recent WR {wr:.0f}% < 40%")
            if adj:
                adjustments.append(adj)
        elif wr > 65:
            adj = _make_adjustment("SPIKE_MIN_RATIO", cur_ratio, "loosen",
                                   f"Fade recent WR {wr:.0f}% > 65%")
            if adj:
                adjustments.append(adj)

        stopped = [t for t in losses if t.get("exit_reason") == "stopped_out"]
        if losses and len(stopped) / len(losses) > 0.5:
            adj = _make_adjustment("SPIKE_MIN_SIZE", cur_size, "tighten",
                                   f"Stopped out = {len(stopped)}/{len(losses)} of fade losses")
            if adj:
                adjustments.append(adj)

        if avg_loss < -10:
            adj = _make_adjustment("FADE_STOP_PP", cur_stop, "tighten",
                                   f"Fade avg loss {avg_loss:.1f}pp > 10pp")
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


def apply_adjustments(adjustments: list[dict]) -> None:
    """Write adjusted values to config.py by modifying specific lines."""
    if not adjustments:
        return

    text = CONFIG_FILE.read_text()
    for adj in adjustments:
        param = adj["param"]
        new_val = adj["new"]
        # Match lines like: PARAM_NAME       = 2.0     # comment
        pattern = rf'^({param}\s*=\s*)[\d.]+(\s*#.*)?$'
        replacement = rf'\g<1>{new_val}\2'
        text, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
        if count:
            log.info("ADJUSTED: %s = %s (was %s) — %s",
                     param, new_val, adj["old"], adj["reason"])
        else:
            log.warning("Could not find %s in config.py to adjust", param)

    CONFIG_FILE.write_text(text)


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


def build_daily_report(mom_trades: list[dict], fade_trades: list[dict],
                       conflicts: list[dict], risk: dict,
                       trends: list[str], adjustments: list[dict]) -> str:
    """Build the Telegram daily intelligence report."""
    mom_m = compute_metrics(mom_trades)
    fade_m = compute_metrics(fade_trades)

    # Combined P&L
    mom_pnl = mom_m.get("total_pnl", 0)
    fade_pnl = fade_m.get("total_pnl", 0)
    total_pnl = round(mom_pnl + fade_pnl, 1)

    lines = [
        f"<b>[INTEL] Daily Intelligence Report</b>",
        "",
        f"<b>Portfolio</b>",
        f"Open: {risk['total_open']} (momentum: {risk['mom_open']}, fade: {risk['fade_open']})",
        f"Total P&L: {total_pnl:+.1f}pp",
        "",
    ]

    # Momentum summary
    if mom_m.get("total_trades"):
        status = "PAUSED" if risk["mom_paused"] else "ACTIVE"
        lines.append(f"<b>Momentum</b> [{status}]")
        lines.append(f"Closed: {mom_m['total_trades']}  |  "
                      f"WR: {mom_m['win_rate']}%  |  P&L: {mom_m['total_pnl']:+.1f}pp")
    else:
        lines.append(f"<b>Momentum</b> — No closed trades yet")

    # Fade summary
    if fade_m.get("total_trades"):
        status = "PAUSED" if risk["fade_paused"] else "ACTIVE"
        lines.append(f"<b>Fade</b> [{status}]")
        lines.append(f"Closed: {fade_m['total_trades']}  |  "
                      f"WR: {fade_m['win_rate']}%  |  P&L: {fade_m['total_pnl']:+.1f}pp")
    else:
        lines.append(f"<b>Fade</b> — No closed trades yet")

    lines.append("")

    # Conflicts
    if conflicts:
        lines.append(f"<b>Conflicts:</b> {len(conflicts)} detected")
        for c in conflicts:
            q = c["question"][:50]
            lines.append(f"  {q}...")
    else:
        lines.append("Conflicts: None")

    # Risk
    lines.append(f"Positions: {risk['total_open']}/{INTEL_MAX_OPEN_TOTAL} limit")
    lines.append(f"Drawdown (7d): {risk['drawdown_7d']}pp / {INTEL_DRAWDOWN_LIMIT_PP}pp limit")
    lines.append(f"Loss streaks: momentum {risk['mom_consecutive_losses']}, "
                  f"fade {risk['fade_consecutive_losses']}")

    if risk["warnings"]:
        lines.append("")
        for w in risk["warnings"]:
            lines.append(f"WARNING: {w}")

    # Trends
    lines.append("")
    lines.append("<b>Trends</b>")
    for t in trends[:5]:
        lines.append(f"- {t}")

    # Adjustments
    if adjustments:
        lines.append("")
        lines.append("<b>Adjustments</b>")
        for a in adjustments:
            lines.append(f"- {a['param']}: {a['old']} -> {a['new']}")
    else:
        lines.append("\nAdjustments: None this cycle")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"Intelligence Layer  [{now_str()}]")
    print("=" * 60)

    # Load data
    mom_trades  = load_trades(MOMENTUM_FILE, MOMENTUM_BAK)
    fade_trades = load_trades(FADE_FILE, FADE_BAK)
    state       = load_state()

    print(f"\nMomentum trades: {len(mom_trades)}  |  Fade trades: {len(fade_trades)}\n")

    # 1. Conflict detection
    conflicts = find_conflicts(mom_trades, fade_trades)
    if conflicts:
        print(f"CONFLICTS FOUND: {len(conflicts)}")
        for c in conflicts:
            print(f"  {c['question'][:50]}")
            print(f"    Momentum: {c['momentum_dir']}  vs  Fade: {c['fade_dir']}")
            intel_conflict_alert(c)
    else:
        print("Conflicts: None")

    # 2. Risk management
    risk = check_risk_limits(mom_trades, fade_trades, state)
    state["paused"] = {
        "momentum": risk["mom_paused"],
        "fade": risk["fade_paused"],
    }
    state["consecutive_losses"] = {
        "momentum": risk["mom_consecutive_losses"],
        "fade": risk["fade_consecutive_losses"],
    }
    print(f"\nRisk: {risk['total_open']}/{INTEL_MAX_OPEN_TOTAL} positions  "
          f"| Drawdown: {risk['drawdown_7d']}pp")
    if risk["warnings"]:
        for w in risk["warnings"]:
            print(f"  WARNING: {w}")

    # 3. Performance trends
    trends = detect_performance_trends(mom_trades, fade_trades)
    print(f"\nTrends:")
    for t in trends:
        print(f"  - {t}")

    # 4. Auto-adjustment
    adjustments = compute_adjustments(mom_trades, fade_trades)
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
        report = build_daily_report(
            mom_trades, fade_trades, conflicts, risk, trends, adjustments
        )
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
