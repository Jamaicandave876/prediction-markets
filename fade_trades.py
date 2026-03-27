from __future__ import annotations
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
    FADE_MIN_REWARD_RATIO,
)
from detect_momentum import fetch_binary_markets, fetch_bet_data, compute_momentum
from detect_spike import detect_spike
from paper_trades import (
    load_trades, save_trades, get_market_state,
    compute_resolution_pnl, compute_metrics,
    now_str, days_since,
)
from notify import fade_signal_alert, fade_exit_alert, summary_alert
from portfolio import sync_portfolio, get_balance, format_balance_summary, compute_stake, load_portfolio

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
        bet_data = fetch_bet_data(m["id"], limit=SPIKE_BETS_TOTAL)
        if len(bet_data) < SPIKE_MIN_BETS:
            continue

        probs = [b["prob"] for b in bet_data]
        timestamps = [b["time_ms"] for b in bet_data]

        spike = detect_spike(probs, timestamps_ms=timestamps)
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

        # Filter 4: risk-reward check — don't take trades where
        # expected reward is too small relative to the stop loss
        expected_reward = spike["spike_size"] * (FADE_NORMALIZE_PCT / 100)
        expected_risk = FADE_STOP_PP
        if expected_risk > 0 and expected_reward / expected_risk < FADE_MIN_REWARD_RATIO:
            log.info("SKIP %s — bad risk-reward: %.1fpp reward vs %.1fpp risk (ratio %.2f < %.2f)",
                     m["question"][:40], expected_reward, expected_risk,
                     expected_reward / expected_risk, FADE_MIN_REWARD_RATIO)
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
    # Block re-entry on open trades and recently closed trades (48h cooldown)
    all_ids = {t["market_id"] for t in trades
               if t["status"] == "open"
               or (t["status"] == "closed" and days_since(t.get("exit_time", t["entry_time"])) < 2)}
    added = 0

    from intelligence import check_pre_trade_conflict

    # Get current balance for position sizing
    portfolio_state = load_portfolio()
    balance = get_balance(portfolio_state)

    for s in signals:
        if s["market_id"] in all_ids:
            continue
        if check_pre_trade_conflict(s["market_id"], s["direction"], "fade"):
            continue

        stake = compute_stake(balance, s, trades, bot="fade")

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
            "stake":          stake,
            "status":         "open",
            "exit_prob":      None,
            "exit_time":      None,
            "exit_reason":    None,
            "pnl_pp":         None,
        }
        trades.append(new_trade)
        fade_signal_alert(new_trade)
        log.info("NEW FADE: %s %s @ %.1f%% (spike %+.1fpp, %.1fx, stake: %.0f Mana)",
                 s["direction"], s["question"][:40], s["entry_prob"],
                 s["spike_size"], s["spike_ratio"], stake)
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

        is_stale = days_since(t["entry_time"]) >= FADE_MAX_DAYS

        # Fetch current market state (needed for accurate stale P&L too)
        state = get_market_state(t["market_id"])

        if state["status"] == "error":
            if is_stale:
                # Can't get real price, but trade must close — record 0pp
                close_trade(t, t["entry_prob"], "stale", 0.0)
                closed += 1
            else:
                api_errors += 1
                log.warning("API error for %s: %s — skipping", t["market_id"], state["reason"])
            continue

        # Exit 1: Market resolved
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

        # Market is active
        prob = state["probability"]
        entry = t["entry_prob"]

        # Exit 2: Max trade duration — now records REAL P&L
        if is_stale:
            if t["direction"] == "BUY NO":
                pnl = entry - prob
            else:
                pnl = prob - entry
            close_trade(t, prob, "stale", pnl)
            closed += 1
            continue

        # Exit 3: Fade-specific price exits
        pre_spike = t["pre_spike_prob"]
        spike_pp = entry - pre_spike

        if t["direction"] == "BUY NO":
            normalize_target = entry - abs(spike_pp) * (FADE_NORMALIZE_PCT / 100)
            pnl = entry - prob
            if prob <= normalize_target:
                close_trade(t, prob, "normalized", pnl)
                closed += 1
            elif prob >= entry + FADE_STOP_PP:
                close_trade(t, prob, "stopped_out", pnl)
                closed += 1
        else:
            normalize_target = entry + abs(spike_pp) * (FADE_NORMALIZE_PCT / 100)
            pnl = prob - entry
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

    # 6. Portfolio tracking
    from paper_trades import load_trades as _load
    momentum_path = Path("trades.json")
    momentum_backup = Path("trades.backup.json")
    momentum_trades = _load(momentum_path, momentum_backup) if momentum_path.exists() else []
    portfolio_state = sync_portfolio(momentum_trades, trades)
    balance = get_balance(portfolio_state)

    print("--- PORTFOLIO ---")
    print(f"  {format_balance_summary(portfolio_state)}")
    print()

    # 7. Telegram summary
    summary_alert(metrics, n_added, n_closed, bot="fade", portfolio=portfolio_state)


if __name__ == "__main__":
    main()
