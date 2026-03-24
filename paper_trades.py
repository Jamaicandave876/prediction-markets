"""
Consensus Momentum Trader — Paper Trade Engine (v2)

Each run:
  1. Load trades (with backup recovery if file is corrupt)
  2. Check exit conditions on all open trades
  3. Scan for new signals and log qualifying entries
  4. Save trades (atomic write with backup)
  5. Send Telegram summary with performance metrics

v2 improvements:
  - API failure vs market resolution properly separated
  - Safe file I/O with backup and atomic writes
  - Consistency threshold raised to 65% (from 50%)
  - Time-decay weighted momentum scoring
  - Market age filter (skips markets < 1 hour old)
  - Re-entry prevention (checks ALL market IDs, not just open)
  - Max trade duration (auto-close after 14 days)
  - Drift reversal exit (close if momentum flips against us)
  - Market resolution tracking (actual win/loss, not flat)
  - Performance metrics and daily summary notifications
  - Structured logging
"""

import json
import shutil
import logging
import time
import requests
from datetime import datetime, timezone
from pathlib import Path

from config import (
    API_BASE, MARKETS_TO_SCAN, BETS_WINDOW, MIN_BETS,
    ENTRY_PROB_LOW, ENTRY_PROB_HIGH, MIN_DRIFT_SCORE, MIN_CONSISTENCY,
    EXIT_TARGET_YES, EXIT_TARGET_NO, REVERSAL_THRESHOLD, MAX_TRADE_DAYS,
)
from detect_momentum import fetch_binary_markets, fetch_prob_series, compute_momentum
from notify import signal_alert, exit_alert, summary_alert

# ── Setup logging ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("trader")

TRADES_FILE  = Path("trades.json")
BACKUP_FILE  = Path("trades.backup.json")


# ── Utilities ─────────────────────────────────────────────────────────────────

def now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def parse_time(time_str: str) -> datetime:
    return datetime.strptime(time_str, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)


def days_since(time_str: str) -> float:
    return (datetime.now(timezone.utc) - parse_time(time_str)).total_seconds() / 86400


# ── Safe File I/O ─────────────────────────────────────────────────────────────

def load_trades(trades_file=None, backup_file=None) -> list[dict]:
    """Load trades from file, falling back to backup if corrupt."""
    trades_file = trades_file or TRADES_FILE
    backup_file = backup_file or BACKUP_FILE
    for path in [trades_file, backup_file]:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
            if isinstance(data, list):
                log.info("Loaded %d trades from %s", len(data), path.name)
                return data
        except (json.JSONDecodeError, ValueError) as e:
            log.warning("Corrupt file %s: %s — trying backup", path.name, e)
    return []


def save_trades(trades: list[dict], trades_file=None, backup_file=None) -> None:
    """Atomic save: backup current file, write to temp, rename."""
    trades_file = trades_file or TRADES_FILE
    backup_file = backup_file or BACKUP_FILE
    if trades_file.exists():
        shutil.copy2(str(trades_file), str(backup_file))

    tmp = trades_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(trades, indent=2))
    tmp.replace(trades_file)
    log.info("Saved %d trades to %s", len(trades), trades_file.name)


# ── Market State Fetching ─────────────────────────────────────────────────────

def get_market_state(market_id: str) -> dict:
    """
    Fetch current market state. Returns one of:
      {"status": "active",   "probability": 65.3}
      {"status": "resolved", "resolution": "YES" | "NO" | "UNKNOWN"}
      {"status": "error",    "reason": "timeout" | "connection" | ...}
    """
    try:
        r = requests.get(f"{API_BASE}/market/{market_id}", timeout=15)

        if r.status_code == 404:
            return {"status": "resolved", "resolution": "UNKNOWN"}
        r.raise_for_status()

        data = r.json()
        if data.get("isResolved"):
            resolution = data.get("resolution", "UNKNOWN")
            return {"status": "resolved", "resolution": str(resolution).upper()}

        prob = data.get("probability")
        if prob is None:
            return {"status": "error", "reason": "missing probability field"}
        return {"status": "active", "probability": round(prob * 100, 1)}

    except requests.exceptions.Timeout:
        return {"status": "error", "reason": "timeout"}
    except requests.exceptions.ConnectionError:
        return {"status": "error", "reason": "connection_failed"}
    except Exception as e:
        return {"status": "error", "reason": str(e)[:100]}


# ── Signal Detection ──────────────────────────────────────────────────────────

def find_signals() -> list[dict]:
    """Scan markets and return candidates that pass all filters."""
    markets = fetch_binary_markets(MARKETS_TO_SCAN)
    if not markets:
        log.warning("No markets returned — API may be down")
        return []

    signals = []
    for m in markets:
        prob_now = round(m.get("probability", 0) * 100, 1)

        # Entry zone filter
        if not (ENTRY_PROB_LOW <= prob_now <= ENTRY_PROB_HIGH):
            continue

        probs = fetch_prob_series(m["id"], limit=BETS_WINDOW)
        if len(probs) < MIN_BETS:
            continue

        mom = compute_momentum(probs)

        if abs(mom["drift_score"]) < MIN_DRIFT_SCORE:
            continue
        if mom["consistency"] < MIN_CONSISTENCY:
            continue

        signals.append({
            "market_id":   m["id"],
            "question":    m["question"],
            "direction":   "BUY YES" if mom["drift"] > 0 else "BUY NO",
            "entry_prob":  prob_now,
            "drift":       mom["drift"],
            "consistency": mom["consistency"],
            "drift_score": mom["drift_score"],
            "url":         m.get("url", ""),
        })

    log.info("Signals found: %d (from %d markets)", len(signals), len(markets))
    return signals


# ── Trade Logging ─────────────────────────────────────────────────────────────

def log_new_signals(signals: list[dict], trades: list[dict]) -> tuple[list[dict], int]:
    """
    Append NEW signals to trade log.
    Prevents re-entry: checks ALL market IDs (open AND closed), not just open.
    """
    all_ids = {t["market_id"] for t in trades}
    added = 0

    from intelligence import check_pre_trade_conflict

    for s in signals:
        if s["market_id"] in all_ids:
            continue
        if check_pre_trade_conflict(s["market_id"], s["direction"], "momentum"):
            continue

        new_trade = {
            "market_id":   s["market_id"],
            "question":    s["question"],
            "direction":   s["direction"],
            "entry_prob":  s["entry_prob"],
            "entry_time":  now_str(),
            "drift_score": s["drift_score"],
            "url":         s["url"],
            "status":      "open",
            "exit_prob":   None,
            "exit_time":   None,
            "exit_reason": None,
            "pnl_pp":      None,
        }
        trades.append(new_trade)
        signal_alert(new_trade)
        log.info("NEW TRADE: %s %s @ %.1f%%", s["direction"], s["question"][:50], s["entry_prob"])
        added += 1

    return trades, added


# ── Exit Checking ─────────────────────────────────────────────────────────────

def close_trade(t: dict, exit_prob: float | None, reason: str, pnl: float) -> None:
    """Mark a trade as closed and send notification."""
    t["status"]      = "closed"
    t["exit_prob"]   = exit_prob
    t["exit_time"]   = now_str()
    t["exit_reason"] = reason
    t["pnl_pp"]      = round(pnl, 1)
    exit_alert(t)
    log.info("CLOSED: %s | reason=%s | pnl=%+.1fpp | %s",
             t["direction"], reason, pnl, t["question"][:50])


def compute_resolution_pnl(trade: dict, resolution: str) -> float:
    """Calculate P&L when a market resolves YES or NO."""
    entry = trade["entry_prob"]

    if resolution == "YES":
        resolved_prob = 100.0
    elif resolution == "NO":
        resolved_prob = 0.0
    else:
        return 0.0  # unknown resolution — record as flat

    if trade["direction"] == "BUY YES":
        return resolved_prob - entry
    else:  # BUY NO
        return entry - resolved_prob


def check_exits(trades: list[dict]) -> tuple[list[dict], int]:
    """
    Review all open trades for exit conditions.
    Properly distinguishes API errors from real events.
    """
    closed = 0
    api_errors = 0

    for t in trades:
        if t["status"] != "open":
            continue

        # Exit 1: Max trade duration
        if days_since(t["entry_time"]) >= MAX_TRADE_DAYS:
            close_trade(t, t["entry_prob"], "stale", 0.0)
            closed += 1
            continue

        # Fetch current market state
        state = get_market_state(t["market_id"])

        # API error — SKIP this trade, don't close it
        if state["status"] == "error":
            api_errors += 1
            log.warning("API error for %s: %s — skipping", t["market_id"], state["reason"])
            continue

        # Exit 2: Market resolved — record actual win/loss
        if state["status"] == "resolved":
            resolution = state["resolution"]
            pnl = compute_resolution_pnl(t, resolution)

            if resolution == "UNKNOWN":
                reason = "expired"
            elif (t["direction"] == "BUY YES" and resolution == "YES") or \
                 (t["direction"] == "BUY NO" and resolution == "NO"):
                reason = "resolved_win"
            else:
                reason = "resolved_loss"

            exit_prob = 100.0 if resolution == "YES" else (0.0 if resolution == "NO" else t["entry_prob"])
            close_trade(t, exit_prob, reason, pnl)
            closed += 1
            continue

        # Market is active — check price-based exits
        prob = state["probability"]
        entry = t["entry_prob"]

        if t["direction"] == "BUY YES":
            pnl = prob - entry
            if prob >= EXIT_TARGET_YES:
                close_trade(t, prob, "target_hit", pnl)
                closed += 1
            elif pnl <= -REVERSAL_THRESHOLD:
                close_trade(t, prob, "reversal", pnl)
                closed += 1
        else:  # BUY NO
            pnl = entry - prob
            if prob <= EXIT_TARGET_NO:
                close_trade(t, prob, "target_hit", pnl)
                closed += 1
            elif pnl <= -REVERSAL_THRESHOLD:
                close_trade(t, prob, "reversal", pnl)
                closed += 1

    if api_errors:
        log.warning("Skipped %d trades due to API errors (will retry next run)", api_errors)

    return trades, closed


# ── Performance Metrics ───────────────────────────────────────────────────────

def compute_metrics(trades: list[dict]) -> dict:
    """Calculate performance stats from closed trades."""
    open_trades  = [t for t in trades if t["status"] == "open"]
    closed       = [t for t in trades if t["status"] == "closed"]

    if not closed:
        return {"open_trades": len(open_trades)}

    pnls   = [t["pnl_pp"] or 0 for t in closed]
    wins   = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    return {
        "open_trades":  len(open_trades),
        "total_trades": len(closed),
        "wins":         len(wins),
        "losses":       len(losses),
        "win_rate":     round(len(wins) / len(closed) * 100, 1),
        "total_pnl":    round(sum(pnls), 1),
        "avg_win":      round(sum(wins) / len(wins), 1) if wins else 0.0,
        "avg_loss":     round(sum(losses) / len(losses), 1) if losses else 0.0,
        "best_trade":   round(max(pnls), 1),
        "worst_trade":  round(min(pnls), 1),
    }


# ── Display ───────────────────────────────────────────────────────────────────

def print_ledger(trades: list[dict]) -> None:
    if not trades:
        print("  (no trades yet)")
        return

    open_trades   = [t for t in trades if t["status"] == "open"]
    closed_trades = [t for t in trades if t["status"] == "closed"]

    if open_trades:
        print(f"OPEN TRADES ({len(open_trades)})")
        print(f"  {'Direction':<10}  {'Entry%':>6}  {'Score':>6}  {'Days':>5}  Question")
        print("  " + "-" * 75)
        for t in open_trades:
            age = days_since(t["entry_time"])
            q = t["question"][:48]
            if len(t["question"]) > 48:
                q += "..."
            print(f"  {t['direction']:<10}  {t['entry_prob']:>6.1f}  "
                  f"{t['drift_score']:>+6.2f}  {age:>5.1f}  {q}")
        print()

    if closed_trades:
        metrics = compute_metrics(trades)
        total_pnl = metrics.get("total_pnl", 0)
        print(f"CLOSED TRADES ({len(closed_trades)})  --  "
              f"W:{metrics.get('wins',0)} L:{metrics.get('losses',0)}  "
              f"WR:{metrics.get('win_rate',0)}%  "
              f"total P&L: {total_pnl:+.1f}pp")
        print(f"  {'P&L':>7}  {'Direction':<10}  {'Entry%':>6} -> {'Exit%':>5}  {'Reason':<15}  Question")
        print("  " + "-" * 85)
        for t in closed_trades:
            pnl  = t["pnl_pp"] or 0
            sign = "+" if pnl >= 0 else ""
            q    = t["question"][:38]
            if len(t["question"]) > 38:
                q += "..."
            print(
                f"  {sign}{pnl:>5.1f}pp  "
                f"{t['direction']:<10}  "
                f"{t['entry_prob']:>6.1f} -> {(t['exit_prob'] or 0):>5.1f}  "
                f"{t.get('exit_reason','?'):<15}  {q}"
            )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"Consensus Momentum Trader v2  [{now_str()}]")
    print("=" * 60)

    trades = load_trades()
    print(f"\nLoaded {len(trades)} existing trade(s)\n")

    # 1. Check exits on open trades
    print("Checking exits on open trades...")
    trades, n_closed = check_exits(trades)
    print(f"  Closed: {n_closed}\n")

    # 2. Scan for new signals (if intelligence layer allows)
    from intelligence import should_allow_new_trade
    if should_allow_new_trade("momentum"):
        print(f"Scanning for new signals ({MARKETS_TO_SCAN} markets)...")
        signals = find_signals()
        print(f"  Signals found: {len(signals)}")
        trades, n_added = log_new_signals(signals, trades)
        print(f"  New trades logged: {n_added}\n")
    else:
        print("Intelligence layer: new momentum trades PAUSED (risk limit hit)\n")
        n_added = 0

    # 3. Save (atomic with backup)
    save_trades(trades)

    # 4. Print ledger
    print("--- TRADE LEDGER ---\n")
    print_ledger(trades)
    print()

    # 5. Compute and display metrics
    metrics = compute_metrics(trades)
    if metrics.get("total_trades"):
        print("--- PERFORMANCE ---")
        print(f"  Win rate:    {metrics['win_rate']}%  (W:{metrics['wins']} L:{metrics['losses']})")
        print(f"  Total P&L:   {metrics['total_pnl']:+.1f}pp")
        print(f"  Avg win:     {metrics['avg_win']:+.1f}pp")
        print(f"  Avg loss:    {metrics['avg_loss']:+.1f}pp")
        print(f"  Best trade:  {metrics['best_trade']:+.1f}pp")
        print(f"  Worst trade: {metrics['worst_trade']:+.1f}pp")
        print()

    # 6. Send Telegram summary
    summary_alert(metrics, n_added, n_closed)


if __name__ == "__main__":
    main()
