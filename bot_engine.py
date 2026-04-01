from __future__ import annotations
"""
Shared bot engine — the backbone for all 10 trading bots.

Handles:
  - Trade file I/O (load, save with atomic backup)
  - Market state fetching from Manifold API
  - Generic exit checking (target, stop, trailing stop, max duration, resolution)
  - Portfolio integration (dynamic staking)
  - Telegram notifications
  - Main run loop template

Each bot just defines:
  - A detect_signals() function
  - A BotConfig with its parameters
  - Optionally a custom exit checker
"""

import json
import shutil
import logging
import time
import requests
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from config import API_BASE
from portfolio import sync_portfolio, get_balance, format_balance_summary, compute_stake, load_portfolio

log = logging.getLogger("engine")


# ── Bot Configuration ────────────────────────────────────────────────────────

@dataclass
class BotConfig:
    name: str              # e.g. "volume_surge"
    display_name: str      # e.g. "Volume Surge"
    trades_file: str       # e.g. "volume_trades.json"
    backup_file: str       # e.g. "volume_trades.backup.json"

    # Exit parameters
    target_yes: float = 78    # close BUY YES when prob >= this
    target_no: float = 22     # close BUY NO when prob <= this
    stop_pp: float = 5        # stop loss in pp against entry
    trailing_stop_pp: float = 4  # trailing stop from peak
    max_days: int = 7         # max trade duration

    # Signal strength field (for position sizing confidence)
    confidence_field: str = "signal_strength"

    # Optional custom exit function: (trade, prob, entry) -> (reason, pnl) or None
    custom_exit: Callable | None = None


# ── Time Utilities ───────────────────────────────────────────────────────────

def now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def parse_time(time_str: str) -> datetime:
    return datetime.strptime(time_str, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)


def days_since(time_str: str) -> float:
    return (datetime.now(timezone.utc) - parse_time(time_str)).total_seconds() / 86400


# ── Safe File I/O ────────────────────────────────────────────────────────────

def load_trades(trades_file: str | Path, backup_file: str | Path) -> list[dict]:
    trades_file = Path(trades_file)
    backup_file = Path(backup_file)
    for path in [trades_file, backup_file]:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
    return []


def save_trades(trades: list[dict], trades_file: str | Path, backup_file: str | Path) -> None:
    trades_file = Path(trades_file)
    backup_file = Path(backup_file)
    if trades_file.exists():
        shutil.copy2(str(trades_file), str(backup_file))
    tmp = trades_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(trades, indent=2))
    tmp.replace(trades_file)


# ── Market State ─────────────────────────────────────────────────────────────

def get_market_state(market_id: str) -> dict:
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
            return {"status": "error", "reason": "missing probability"}
        return {"status": "active", "probability": round(prob * 100, 1)}
    except requests.exceptions.Timeout:
        return {"status": "error", "reason": "timeout"}
    except requests.exceptions.ConnectionError:
        return {"status": "error", "reason": "connection_failed"}
    except Exception as e:
        return {"status": "error", "reason": str(e)[:100]}


# ── Bet Data Fetching (enriched) ─────────────────────────────────────────────

def fetch_rich_bets(market_id: str, limit: int = 50) -> list[dict]:
    """Fetch bet data with amount, direction, timestamps, and user info."""
    try:
        resp = requests.get(
            f"{API_BASE}/bets",
            params={"contractId": market_id, "limit": limit},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException:
        return []

    bets = resp.json()
    if not bets:
        return []

    bets.sort(key=lambda b: b.get("createdTime", 0))
    result = []
    for b in bets:
        if "probAfter" not in b:
            continue
        result.append({
            "prob_before": b.get("probBefore", b["probAfter"]),
            "prob_after":  b["probAfter"],
            "amount":      abs(b.get("amount", 0)),
            "time_ms":     b.get("createdTime", 0),
            "user_id":     b.get("userId", ""),
            "outcome":     b.get("outcome", ""),  # YES or NO
        })
    return result


def fetch_binary_markets_flexible(n: int, min_pool: int = 500,
                                   min_age_hr: float = 1,
                                   max_age_hr: float | None = None,
                                   min_close_days: float = 3,
                                   max_close_days: float | None = None) -> list[dict]:
    """Flexible market scanner with configurable filters."""
    try:
        resp = requests.get(
            f"{API_BASE}/markets",
            params={"limit": min(n * 4, 500)},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException:
        return []

    now_ms = time.time() * 1000
    results = []
    for m in resp.json():
        if m.get("outcomeType") != "BINARY":
            continue
        if m.get("isResolved"):
            continue

        pool = m.get("pool", {})
        pool_total = pool.get("YES", 0) + pool.get("NO", 0)
        if pool_total < min_pool:
            continue

        created = m.get("createdTime", 0)
        age_hr = (now_ms - created) / 3_600_000

        if age_hr < min_age_hr:
            continue
        if max_age_hr is not None and age_hr > max_age_hr:
            continue

        close_time = m.get("closeTime")
        if close_time:
            days_to_close = (close_time - now_ms) / 86_400_000
            if days_to_close < min_close_days:
                continue
            if max_close_days is not None and days_to_close > max_close_days:
                continue

        results.append(m)
        if len(results) >= n:
            break

    return results


# ── Resolution P&L ───────────────────────────────────────────────────────────

def compute_resolution_pnl(trade: dict, resolution: str) -> float:
    entry = trade["entry_prob"]
    if resolution == "YES":
        resolved_prob = 100.0
    elif resolution == "NO":
        resolved_prob = 0.0
    else:
        return 0.0
    if trade["direction"] == "BUY YES":
        return resolved_prob - entry
    else:
        return entry - resolved_prob


# ── Generic Exit Checker ─────────────────────────────────────────────────────

def check_exits(trades: list[dict], cfg: BotConfig,
                alert_fn: Callable | None = None) -> tuple[list[dict], int]:
    closed = 0
    for t in trades:
        if t["status"] != "open":
            continue

        is_stale = days_since(t["entry_time"]) >= cfg.max_days
        state = get_market_state(t["market_id"])

        if state["status"] == "error":
            if is_stale:
                _close(t, t["entry_prob"], "stale", 0.0, alert_fn)
                closed += 1
            continue

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
            _close(t, exit_prob, reason, pnl, alert_fn)
            closed += 1
            continue

        prob = state["probability"]
        entry = t["entry_prob"]

        if is_stale:
            pnl = (prob - entry) if t["direction"] == "BUY YES" else (entry - prob)
            _close(t, prob, "stale", pnl, alert_fn)
            closed += 1
            continue

        # Custom exit check (for bots with special exit logic)
        if cfg.custom_exit:
            result = cfg.custom_exit(t, prob, entry)
            if result:
                reason, pnl = result
                _close(t, prob, reason, pnl, alert_fn)
                closed += 1
                continue

        # Standard price-based exits
        if t["direction"] == "BUY YES":
            pnl = prob - entry
        else:
            pnl = entry - prob

        peak = t.get("peak_pnl", 0)
        if pnl > peak:
            t["peak_pnl"] = pnl
            peak = pnl

        if t["direction"] == "BUY YES" and prob >= cfg.target_yes:
            _close(t, prob, "target_hit", pnl, alert_fn)
            closed += 1
        elif t["direction"] == "BUY NO" and prob <= cfg.target_no:
            _close(t, prob, "target_hit", pnl, alert_fn)
            closed += 1
        elif pnl <= -cfg.stop_pp:
            _close(t, prob, "stopped_out", pnl, alert_fn)
            closed += 1
        elif peak > 0 and (peak - pnl) >= cfg.trailing_stop_pp:
            # Trailing stop: activates once ANY profit is seen
            _close(t, prob, "trailing_stop", pnl, alert_fn)
            closed += 1

    return trades, closed


def _close(t: dict, exit_prob: float | None, reason: str, pnl: float,
           alert_fn: Callable | None = None) -> None:
    t["status"] = "closed"
    t["exit_prob"] = exit_prob
    t["exit_time"] = now_str()
    t["exit_reason"] = reason
    t["pnl_pp"] = round(pnl, 1)
    if alert_fn:
        alert_fn(t)


# ── Metrics ──────────────────────────────────────────────────────────────────

def compute_metrics(trades: list[dict]) -> dict:
    open_trades = [t for t in trades if t["status"] == "open"]
    closed = [t for t in trades if t["status"] == "closed"]
    if not closed:
        return {"open_trades": len(open_trades)}
    pnls = [t["pnl_pp"] or 0 for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    return {
        "open_trades": len(open_trades),
        "total_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(closed) * 100, 1),
        "total_pnl": round(sum(pnls), 1),
        "avg_win": round(sum(wins) / len(wins), 1) if wins else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 1) if losses else 0.0,
        "best_trade": round(max(pnls), 1),
        "worst_trade": round(min(pnls), 1),
    }


# ── Notifications ────────────────────────────────────────────────────────────

def bot_signal_alert(trade: dict, bot_label: str, extra_lines: str = "") -> None:
    from notify import send
    arrow = "UP" if trade["direction"] == "BUY YES" else "DOWN"
    stake_line = f"Stake:       {trade['stake']:.0f} Mana\n" if trade.get("stake") else ""
    msg = (
        f"<b>[{bot_label}] New Signal [{arrow}]</b>\n"
        f"{trade['question']}\n\n"
        f"Direction:   {trade['direction']}\n"
        f"Prob now:    {trade['entry_prob']}%\n"
        f"{extra_lines}"
        f"{stake_line}"
        f"\n{trade.get('url', '')}"
    )
    send(msg)


def bot_exit_alert(trade: dict, bot_label: str) -> None:
    from notify import send
    pnl = trade["pnl_pp"] or 0
    result = "WIN" if pnl > 0 else ("FLAT" if pnl == 0 else "LOSS")
    sign = "+" if pnl >= 0 else ""
    stake = trade.get("stake")
    pnl_mana = pnl / 100 * stake if stake else None
    mana_line = f"P&L (Mana): {'+' if pnl_mana and pnl_mana >= 0 else ''}{pnl_mana:.0f} Mana\n" if pnl_mana is not None else ""
    msg = (
        f"<b>[{bot_label}] Trade Closed [{result}]</b>\n"
        f"{trade['question']}\n\n"
        f"Direction:  {trade['direction']}\n"
        f"Entry:      {trade['entry_prob']}%\n"
        f"Exit:       {trade.get('exit_prob', '?')}%\n"
        f"P&L:        {sign}{pnl:.1f}pp\n"
        f"{mana_line}"
        f"Reason:     {trade.get('exit_reason', 'unknown')}"
    )
    send(msg)


def bot_summary_alert(metrics: dict, n_new: int, n_closed: int,
                      bot_label: str, portfolio: dict | None = None) -> None:
    from notify import send
    if not metrics or not metrics.get("total_trades"):
        msg = (
            f"<b>[{bot_label}] Run Complete</b>\n\n"
            f"New trades:    {n_new}\n"
            f"Trades closed: {n_closed}\n"
            f"Open positions: {metrics.get('open_trades', 0)}\n"
            f"No closed trades yet."
        )
    else:
        msg = (
            f"<b>[{bot_label}] Run Complete</b>\n\n"
            f"New: {n_new} | Closed: {n_closed} | Open: {metrics['open_trades']}\n"
            f"WR: {metrics['win_rate']}% ({metrics['wins']}W/{metrics['losses']}L)\n"
            f"P&L: {metrics['total_pnl']:+.1f}pp"
        )
    if portfolio:
        balance = portfolio["starting_balance"] + portfolio["realized_pnl"]
        msg += f"\nBalance: {balance:,.0f} Mana"
    send(msg)


# ── Entry Logging (generic) ─────────────────────────────────────────────────

def log_new_entries(signals: list[dict], trades: list[dict], cfg: BotConfig,
                    alert_fn: Callable | None = None) -> tuple[list[dict], int]:
    """Generic entry logger. Prevents re-entry with 12h cooldown."""
    all_ids = {t["market_id"] for t in trades
               if t["status"] == "open"
               or (t["status"] == "closed" and days_since(t.get("exit_time", t["entry_time"])) < 0.5)}
    added = 0

    portfolio_state = load_portfolio()
    balance = get_balance(portfolio_state)

    # Cross-market position cap: max 2 open positions per market across ALL bots
    all_trades = _collect_all_trades()
    market_counts = {}
    for t in all_trades:
        if t["status"] == "open":
            mid = t["market_id"]
            market_counts[mid] = market_counts.get(mid, 0) + 1

    for s in signals:
        if s["market_id"] in all_ids:
            continue

        # Max 2 bots on the same market
        if market_counts.get(s["market_id"], 0) >= 2:
            continue

        # Cross-bot conflict check
        try:
            from intelligence import check_pre_trade_conflict
            if check_pre_trade_conflict(s["market_id"], s["direction"], cfg.name):
                continue
        except ImportError:
            pass

        stake = compute_stake(balance, s, trades, bot=cfg.name)

        new_trade = {
            "market_id": s["market_id"],
            "question": s["question"],
            "direction": s["direction"],
            "entry_prob": s["entry_prob"],
            "entry_time": now_str(),
            "url": s.get("url", ""),
            "stake": stake,
            "status": "open",
            "exit_prob": None,
            "exit_time": None,
            "exit_reason": None,
            "pnl_pp": None,
        }
        # Copy any extra signal-specific fields
        for key in s:
            if key not in new_trade:
                new_trade[key] = s[key]

        trades.append(new_trade)
        if alert_fn:
            alert_fn(new_trade)
        added += 1

    return trades, added


# ── Main Run Template ────────────────────────────────────────────────────────

def run_bot(cfg: BotConfig,
            detect_signals_fn: Callable,
            signal_alert_fn: Callable | None = None,
            exit_alert_fn: Callable | None = None) -> None:
    """Standard bot execution loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    bot_log = logging.getLogger(cfg.name)

    print(f"{'=' * 60}")
    print(f"{cfg.display_name}  [{now_str()}]")
    print(f"{'=' * 60}")

    trades = load_trades(cfg.trades_file, cfg.backup_file)
    bot_log.info("Loaded %d trades", len(trades))

    # 1. Check exits
    trades, n_closed = check_exits(trades, cfg, alert_fn=exit_alert_fn)
    bot_log.info("Closed %d trades", n_closed)

    # 2. Scan for new signals
    n_added = 0
    try:
        from intelligence import should_allow_new_trade
        allowed = should_allow_new_trade(cfg.name)
    except ImportError:
        allowed = True

    if allowed:
        signals = detect_signals_fn()
        bot_log.info("Signals found: %d", len(signals))
        trades, n_added = log_new_entries(signals, trades, cfg, alert_fn=signal_alert_fn)
        bot_log.info("New trades: %d", n_added)
    else:
        bot_log.info("%s paused by intelligence layer", cfg.name)

    # 3. Save
    save_trades(trades, cfg.trades_file, cfg.backup_file)

    # 4. Metrics + summary
    metrics = compute_metrics(trades)
    if metrics.get("total_trades"):
        print(f"  WR: {metrics['win_rate']}% | P&L: {metrics['total_pnl']:+.1f}pp | "
              f"Open: {metrics['open_trades']}")

    # 5. Portfolio sync (load all trades across all bots)
    all_trades = _collect_all_trades()
    portfolio_state = sync_portfolio_all(all_trades)

    bot_summary_alert(metrics, n_added, n_closed, cfg.display_name.upper(), portfolio_state)
    print(f"{cfg.display_name} complete.\n")


# ── Portfolio helpers ────────────────────────────────────────────────────────

# Registry of all bot trade files
BOT_TRADE_FILES = [
    ("trades.json", "trades.backup.json"),
    ("fade_trades.json", "fade_trades.backup.json"),
    ("mean_reversion_trades.json", "mean_reversion_trades.backup.json"),
    ("volume_trades.json", "volume_trades.backup.json"),
    ("whale_trades.json", "whale_trades.backup.json"),
    ("contrarian_trades.json", "contrarian_trades.backup.json"),
    ("close_gravity_trades.json", "close_gravity_trades.backup.json"),
    ("fresh_sniper_trades.json", "fresh_sniper_trades.backup.json"),
    ("stability_trades.json", "stability_trades.backup.json"),
    ("breakout_trades.json", "breakout_trades.backup.json"),
    ("calibration_trades.json", "calibration_trades.backup.json"),
]


def _collect_all_trades() -> list[dict]:
    """Load trades from all bot files."""
    all_trades = []
    for tf, bf in BOT_TRADE_FILES:
        all_trades.extend(load_trades(tf, bf))
    return all_trades


def sync_portfolio_all(all_trades: list[dict]) -> dict:
    """Sync portfolio from all closed trades across all bots."""
    from portfolio import load_portfolio, save_portfolio, BASE_STAKE_PCT
    from config import STARTING_BALANCE

    state = load_portfolio()
    closed = [t for t in all_trades if t["status"] == "closed" and t.get("pnl_pp") is not None]

    realized_pnl = 0.0
    for t in closed:
        stake = t.get("stake", STARTING_BALANCE * BASE_STAKE_PCT)
        realized_pnl += t["pnl_pp"] / 100 * stake

    state["realized_pnl"] = round(realized_pnl, 2)
    state["total_trades_counted"] = len(closed)
    save_portfolio(state)
    return state
