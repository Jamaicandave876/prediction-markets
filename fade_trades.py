"""
Overreaction Fade Bot — Paper Trade Engine

Each run:
  1. Load fade trades (separate file from momentum bot)
  2. Check exits on open fade trades
  3. Scan for new spike signals
  4. Log qualifying fade entries
  5. Save and send Telegram summary

Strategy:
  - Detect sharp spikes (abnormally large recent moves)
  - Enter AGAINST the spike (fade it)
    - Spike went UP   → we BUY NO  (expect price to come back down)
    - Spike went DOWN → we BUY YES (expect price to come back up)
  - Win when price normalizes back toward pre-spike level
  - Lose when spike continues (it was real, not an overreaction)

Reuses from momentum bot:
  - detect_momentum.py: fetch_binary_markets, fetch_prob_series, compute_momentum
  - detect_spike.py: detect_spike
  - paper_trades.py: load_trades, save_trades, get_market_state,
                     compute_resolution_pnl, compute_metrics, utilities
  - notify.py: fade_signal_alert, fade_exit_alert, summary_alert
"""

import logging
from pathlib import Path

from config import (
    MARKETS_TO_SCAN, SPIKE_BETS_TOTAL, SPIKE_MIN_BETS,
    SPIKE_MIN_SIZE, SPIKE_MIN_RATIO, MAX_CONSISTENCY,
    FADE_NORMALIZE_PCT, FADE_STOP_PP, FADE_MAX_DAYS,
)
from detect_momentum import fetch_binary_markets, fetch_prob_series, compute_momentum
from detect_spike import detect_spike
from paper_trades import (
    load_trades, save_trades, get_market_state,
    compute_resolution_pnl, compute_metrics,
    now_str, days_since, close_trade as _close_trade_momentum,
)
from notify import fade_signal_alert, fade_exit_alert, summary_alert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("fade")

TRADES_FILE = Path("fade_trades.json")
BACKUP_FILE = Path("fade_trades.backup.json")


# ── Close trade (uses fade-specific alerts) ───────────────────────────────────

def close_trade(t: dict, exit_prob: float | None, reason: str, pnl: float) -> None:
    """Mark a fade trade as closed and send fade-specific notification."""
    t["status"]      = "closed"
    t["exit_prob"]   = exit_prob
    t["exit_time"]   = now_str()
    t["exit_reason"] = reason
    t["pnl_pp"]      = round(pnl, 1)
    fade_exit_alert(t)
    log.info("CLOSED FADE: %s | reason=%s | pnl=%+.1fpp | %s",
             t["direction"], reason, pnl, t["question"][:50])


# ── Signal Detection ──────────────────────────────────────────────────────────

def find_fade_signals() -> list[dict]:
    """Scan markets for overreaction spikes worth fading."""
    markets = fetch_binary_markets(MARKETS_TO_SCAN)
    if not markets:
        log.warning("No markets returned — API may be down")
        return []

    signals = []
    for m in markets:
        probs = fetch_prob_series(m["id"], limit=SPIKE_BETS_TOTAL)
        if len(probs) < SPIKE_MIN_BETS:
            continue

        spike = detect_spike(probs)
        if spike is None:
            continue

        # Filter 1: spike must be large enough
        if spike["spike_size"] < SPIKE_MIN_SIZE:
            continue

        # Filter 2: spike must be abnormal relative to baseline
        if spike["spike_ratio"] < SPIKE_MIN_RATIO:
            continue

        # Filter 3: reject high consistency (that's a real trend, not a spike)
        mom = compute_momentum(probs)
        if mom["consistency"] > MAX_CONSISTENCY:
            continue

        prob_now = round(m.get("probability", 0) * 100, 1)

        # Fade direction: bet AGAINST the spike
        if spike["spike_dir"] == 1:
            direction = "BUY NO"   # spike went up, we bet it comes back down
        else:
            direction = "BUY YES"  # spike went down, we bet it comes back up

        signals.append({
            "market_id":      m["id"],
            "question":       m["question"],
            "direction":      direction,
            "entry_prob":     prob_now,
            "pre_spike_prob": spike["pre_spike_prob"],
            "spike_size":     spike["spike_size"],
            "spike_ratio":    spike["spike_ratio"],
            "spike_dir":      spike["spike_dir"],
            "consistency":    mom["consistency"],
            "url":            m.get("url", ""),
        })

    log.info("Fade signals found: %d (from %d markets)", len(signals), len(markets))
    return signals


# ── Trade Logging ─────────────────────────────────────────────────────────────

def log_new_signals(signals: list[dict], trades: list[dict]) -> tuple[list[dict], int]:
    """Append new fade signals. Prevents re-entry on same market."""
    all_ids = {t["market_id"] for t in trades}
    added = 0

    from intelligence import check_pre_trade_conflict

    for s in signals:
        if s["market_id"] in all_ids:
            continue
        if check_pre_trade_conflict(s["market_id"], s["direction"], "fade"):
            continue

        new_trade = {
            "market_id":      s["market_id"],
            "question":       s["question"],
            "direction":      s["direction"],
            "entry_prob":     s["entry_prob"],
            "pre_spike_prob": s["pre_spike_prob"],
            "spike_size":     s["spike_size"],
            "spike_ratio":    s["spike_ratio"],
            "spike_dir":      s["spike_dir"],
            "entry_time":     now_str(),
            "url":            s["url"],
            "status":         "open",
            "exit_prob":      None,
            "exit_time":      None,
            "exit_reason":    None,
            "pnl_pp":         None,
        }
        trades.append(new_trade)
        fade_signal_alert(new_trade)
        log.info("NEW FADE: %s %s @ %.1f%% (spike %+.1fpp, %.1fx)",
                 s["direction"], s["question"][:40], s["entry_prob"],
                 s["spike_size"], s["spike_ratio"])
        added += 1

    return trades, added


# ── Exit Checking ─────────────────────────────────────────────────────────────

def check_exits(trades: list[dict]) -> tuple[list[dict], int]:
    """
    Check fade-specific exit conditions on open trades.

    Exits:
      - normalized:    price returned toward pre-spike level (WIN)
      - stopped_out:   price kept going in spike direction (LOSS)
      - resolved:      market resolved
      - stale:         max duration exceeded
    """
    closed = 0
    api_errors = 0

    for t in trades:
        if t["status"] != "open":
            continue

        # Exit 1: Max trade duration (fades expire faster)
        if days_since(t["entry_time"]) >= FADE_MAX_DAYS:
            close_trade(t, t["entry_prob"], "stale", 0.0)
            closed += 1
            continue

        # Fetch current market state
        state = get_market_state(t["market_id"])

        if state["status"] == "error":
            api_errors += 1
            log.warning("API error for %s: %s — skipping", t["market_id"], state["reason"])
            continue

        # Exit 2: Market resolved
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

        # Market is active — check fade-specific exits
        prob = state["probability"]
        entry = t["entry_prob"]
        pre_spike = t["pre_spike_prob"]

        # How far has price moved back toward pre-spike?
        # Normalization target = pre_spike + (1 - FADE_NORMALIZE_PCT/100) * spike
        # i.e., we want FADE_NORMALIZE_PCT% of the spike to retrace
        spike_pp = entry - pre_spike  # signed: + if spike went up, - if went down

        if t["direction"] == "BUY NO":
            # We faded an upward spike. We win if price drops back toward pre-spike.
            normalize_target = entry - abs(spike_pp) * (FADE_NORMALIZE_PCT / 100)
            pnl = entry - prob  # BUY NO profits when prob drops
            if prob <= normalize_target:
                close_trade(t, prob, "normalized", pnl)
                closed += 1
            elif prob >= entry + FADE_STOP_PP:
                close_trade(t, prob, "stopped_out", pnl)
                closed += 1
        else:
            # We faded a downward spike. We win if price rises back toward pre-spike.
            normalize_target = entry + abs(spike_pp) * (FADE_NORMALIZE_PCT / 100)
            pnl = prob - entry  # BUY YES profits when prob rises
            if prob >= normalize_target:
                close_trade(t, prob, "normalized", pnl)
                closed += 1
            elif prob <= entry - FADE_STOP_PP:
                close_trade(t, prob, "stopped_out", pnl)
                closed += 1

    if api_errors:
        log.warning("Skipped %d fade trades due to API errors", api_errors)

    return trades, closed


# ── Display ───────────────────────────────────────────────────────────────────

def print_ledger(trades: list[dict]) -> None:
    if not trades:
        print("  (no trades yet)")
        return

    open_trades   = [t for t in trades if t["status"] == "open"]
    closed_trades = [t for t in trades if t["status"] == "closed"]

    if open_trades:
        print(f"OPEN FADE TRADES ({len(open_trades)})")
        print(f"  {'Direction':<10}  {'Entry%':>6}  {'Pre%':>5}  {'Spike':>7}  {'Days':>5}  Question")
        print("  " + "-" * 80)
        for t in open_trades:
            age = days_since(t["entry_time"])
            q = t["question"][:45]
            if len(t["question"]) > 45:
                q += "..."
            print(f"  {t['direction']:<10}  {t['entry_prob']:>6.1f}  "
                  f"{t['pre_spike_prob']:>5.1f}  "
                  f"{t['spike_size']:>+6.1f}pp  "
                  f"{age:>5.1f}  {q}")
        print()

    if closed_trades:
        metrics = compute_metrics(trades)
        total_pnl = metrics.get("total_pnl", 0)
        print(f"CLOSED FADE TRADES ({len(closed_trades)})  --  "
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
    print(f"Overreaction Fade Bot  [{now_str()}]")
    print("=" * 60)

    trades = load_trades(TRADES_FILE, BACKUP_FILE)
    print(f"\nLoaded {len(trades)} existing fade trade(s)\n")

    # 1. Check exits
    print("Checking exits on open fade trades...")
    trades, n_closed = check_exits(trades)
    print(f"  Closed: {n_closed}\n")

    # 2. Scan for new spikes (if intelligence layer allows)
    from intelligence import should_allow_new_trade
    if should_allow_new_trade("fade"):
        print(f"Scanning for overreaction spikes ({MARKETS_TO_SCAN} markets)...")
        signals = find_fade_signals()
        print(f"  Spike signals found: {len(signals)}")
        trades, n_added = log_new_signals(signals, trades)
        print(f"  New fade trades logged: {n_added}\n")
    else:
        print("Intelligence layer: new fade trades PAUSED (risk limit hit)\n")
        n_added = 0

    # 3. Save
    save_trades(trades, TRADES_FILE, BACKUP_FILE)

    # 4. Ledger
    print("--- FADE TRADE LEDGER ---\n")
    print_ledger(trades)
    print()

    # 5. Metrics
    metrics = compute_metrics(trades)
    if metrics.get("total_trades"):
        print("--- FADE PERFORMANCE ---")
        print(f"  Win rate:    {metrics['win_rate']}%  (W:{metrics['wins']} L:{metrics['losses']})")
        print(f"  Total P&L:   {metrics['total_pnl']:+.1f}pp")
        print(f"  Avg win:     {metrics['avg_win']:+.1f}pp")
        print(f"  Avg loss:    {metrics['avg_loss']:+.1f}pp")
        print()

    # 6. Telegram summary
    summary_alert(metrics, n_added, n_closed, bot="fade")


if __name__ == "__main__":
    main()
