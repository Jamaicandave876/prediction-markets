"""
Step 4: Paper trade tracker.

Each time this runs it:
  1. Scans for signals (reuses find_signals logic)
  2. Logs any NEW signals to trades.json (won't double-log the same market)
  3. Checks all OPEN trades for exit conditions
  4. Prints the full trade ledger with simulated P&L

P&L is in probability points (pp) — not real money.
  BUY YES: you want the probability to rise → pnl = exit_prob - entry_prob
  BUY NO:  you want the probability to fall → pnl = entry_prob - exit_prob

Exit conditions (checked in order):
  - Target hit:  prob reached the exit zone (configurable)
  - Reversal:    prob moved against the entry by more than REVERSAL_THRESHOLD
  - Expired:     market is now resolved/closed
"""

import json
import requests
from datetime import datetime, timezone
from pathlib import Path

from detect_momentum import fetch_binary_markets, fetch_prob_series, compute_momentum
from notify import signal_alert, exit_alert

# ── Config ────────────────────────────────────────────────────────────────────
MARKETS_TO_SCAN    = 40
BETS_WINDOW        = 30
MIN_BETS           = 8
ENTRY_PROB_LOW     = 45
ENTRY_PROB_HIGH    = 72
MIN_DRIFT_SCORE    = 2.0
MIN_CONSISTENCY    = 50

EXIT_TARGET_YES    = 78      # close BUY YES when prob rises above this
EXIT_TARGET_NO     = 22      # close BUY NO  when prob falls below this
REVERSAL_THRESHOLD = 6       # pp — close early if market moves this far against us

TRADES_FILE        = Path("trades.json")
API_BASE           = "https://api.manifold.markets/v0"
# ──────────────────────────────────────────────────────────────────────────────


def now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def load_trades() -> list[dict]:
    if TRADES_FILE.exists():
        return json.loads(TRADES_FILE.read_text())
    return []


def save_trades(trades: list[dict]) -> None:
    TRADES_FILE.write_text(json.dumps(trades, indent=2))


def find_signals() -> list[dict]:
    """Run the full signal scan; return candidate list."""
    markets = fetch_binary_markets(MARKETS_TO_SCAN)
    signals = []
    for m in markets:
        probs = fetch_prob_series(m["id"], limit=BETS_WINDOW)
        prob_now = round(m["probability"] * 100, 1)
        if len(probs) < MIN_BETS:
            continue
        mom = compute_momentum(probs)
        if not (ENTRY_PROB_LOW <= prob_now <= ENTRY_PROB_HIGH):
            continue
        if abs(mom["drift_score"]) < MIN_DRIFT_SCORE:
            continue
        if mom["consistency"] < MIN_CONSISTENCY:
            continue
        signals.append({
            "market_id":  m["id"],
            "question":   m["question"],
            "direction":  "BUY YES" if mom["drift"] > 0 else "BUY NO",
            "entry_prob": prob_now,
            "drift":      mom["drift"],
            "consistency":mom["consistency"],
            "drift_score":mom["drift_score"],
            "url":        m.get("url", ""),
        })
    return signals


def log_new_signals(signals: list[dict], trades: list[dict]) -> tuple[list[dict], int]:
    """Append signals not already in the trade log. Returns updated trades + count added."""
    open_ids = {t["market_id"] for t in trades if t["status"] == "open"}
    added = 0
    for s in signals:
        if s["market_id"] in open_ids:
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
        added += 1
    return trades, added


def get_current_prob(market_id: str) -> float | None:
    """Fetch the current probability for a single market."""
    try:
        r = requests.get(f"{API_BASE}/market/{market_id}", timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("isResolved"):
            return None   # signal: market closed
        return round(data["probability"] * 100, 1)
    except Exception:
        return None


def check_exits(trades: list[dict]) -> tuple[list[dict], int]:
    """Review open trades and close any that hit an exit condition."""
    closed = 0
    for t in trades:
        if t["status"] != "open":
            continue

        prob = get_current_prob(t["market_id"])

        # Expired / resolved
        if prob is None:
            t["status"]      = "closed"
            t["exit_time"]   = now_str()
            t["exit_reason"] = "expired"
            t["exit_prob"]   = t["entry_prob"]   # no data — record as flat
            t["pnl_pp"]      = 0.0
            exit_alert(t)
            closed += 1
            continue

        entry = t["entry_prob"]

        if t["direction"] == "BUY YES":
            pnl = prob - entry
            if prob >= EXIT_TARGET_YES:
                reason = "target_hit"
            elif pnl <= -REVERSAL_THRESHOLD:
                reason = "reversal"
            else:
                continue   # still open
        else:  # BUY NO
            pnl = entry - prob
            if prob <= EXIT_TARGET_NO:
                reason = "target_hit"
            elif pnl <= -REVERSAL_THRESHOLD:
                reason = "reversal"
            else:
                continue

        t["status"]      = "closed"
        t["exit_prob"]   = prob
        t["exit_time"]   = now_str()
        t["exit_reason"] = reason
        t["pnl_pp"]      = round(pnl, 1)
        exit_alert(t)
        closed += 1

    return trades, closed


def print_ledger(trades: list[dict]) -> None:
    if not trades:
        print("  (no trades yet)")
        return

    open_trades   = [t for t in trades if t["status"] == "open"]
    closed_trades = [t for t in trades if t["status"] == "closed"]

    if open_trades:
        print(f"OPEN TRADES ({len(open_trades)})")
        print(f"  {'Direction':<10}  {'Entry%':>6}  {'Score':>6}  Question")
        print("  " + "-" * 70)
        for t in open_trades:
            q = t["question"][:50] + "..." if len(t["question"]) > 50 else t["question"]
            print(f"  {t['direction']:<10}  {t['entry_prob']:>6.1f}  {t['drift_score']:>+6.2f}  {q}")
        print()

    if closed_trades:
        wins   = [t for t in closed_trades if (t["pnl_pp"] or 0) > 0]
        losses = [t for t in closed_trades if (t["pnl_pp"] or 0) <= 0]
        total_pnl = sum(t["pnl_pp"] or 0 for t in closed_trades)

        print(f"CLOSED TRADES ({len(closed_trades)})  —  W:{len(wins)} L:{len(losses)}  total P&L: {total_pnl:+.1f}pp")
        print(f"  {'Result':>7}  {'Direction':<10}  {'Entry%':>6} -> {'Exit%':>5}  {'Reason':<12}  Question")
        print("  " + "-" * 80)
        for t in closed_trades:
            pnl  = t["pnl_pp"] or 0
            sign = "+" if pnl >= 0 else ""
            q    = t["question"][:40] + "..." if len(t["question"]) > 40 else t["question"]
            print(
                f"  {sign}{pnl:>5.1f}pp  "
                f"{t['direction']:<10}  "
                f"{t['entry_prob']:>6.1f} -> {t['exit_prob'] or 0:>5.1f}  "
                f"{t['exit_reason']:<12}  {q}"
            )


def main():
    print("=" * 60)
    print(f"Prediction Market Paper Trader  [{now_str()}]")
    print("=" * 60)

    trades = load_trades()
    print(f"\nLoaded {len(trades)} existing trade(s) from {TRADES_FILE}\n")

    # 1. Check exits on open trades first
    print("Checking exits on open trades...")
    trades, n_closed = check_exits(trades)
    print(f"  Closed: {n_closed}\n")

    # 2. Scan for new signals
    print(f"Scanning for new signals ({MARKETS_TO_SCAN} markets)...")
    signals = find_signals()
    print(f"  Signals found: {len(signals)}")
    trades, n_added = log_new_signals(signals, trades)
    print(f"  New trades logged: {n_added}\n")

    # 3. Save
    save_trades(trades)

    # 4. Print ledger
    print("--- TRADE LEDGER ---\n")
    print_ledger(trades)
    print()


if __name__ == "__main__":
    main()
