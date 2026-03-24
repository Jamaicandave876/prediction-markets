"""
Telegram notifications for the paper trading bot.

Sends messages to your phone when:
  - A new signal fires (entry)
  - A trade closes (exit with P&L)
  - Each run completes (summary with metrics)
"""

import logging
import requests
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger(__name__)


def send(message: str) -> bool:
    """Send a Telegram message. Returns True if successful."""
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        if not r.ok:
            log.warning("Telegram API returned %s: %s", r.status_code, r.text[:200])
        return r.ok
    except Exception as e:
        log.error("Telegram send failed: %s", e)
        return False


def signal_alert(trade: dict) -> None:
    """Notify about a new paper trade entry."""
    arrow = "UP" if trade["direction"] == "BUY YES" else "DOWN"
    msg = (
        f"<b>New Signal [{arrow}]</b>\n"
        f"{trade['question']}\n\n"
        f"Direction:   {trade['direction']}\n"
        f"Prob now:    {trade['entry_prob']}%\n"
        f"Drift score: {trade['drift_score']:+.2f}\n"
        f"\n{trade.get('url', '')}"
    )
    send(msg)


def exit_alert(trade: dict) -> None:
    """Notify about a closed paper trade."""
    pnl = trade["pnl_pp"] or 0
    result = "WIN" if pnl > 0 else ("FLAT" if pnl == 0 else "LOSS")
    sign = "+" if pnl >= 0 else ""

    reason_labels = {
        "target_hit":     "Target reached",
        "reversal":       "Reversed against us",
        "resolved_win":   "Market resolved in our favor",
        "resolved_loss":  "Market resolved against us",
        "stale":          "Max duration reached",
        "drift_reversal": "Momentum flipped against us",
        "expired":        "Market expired/deleted",
    }

    msg = (
        f"<b>Trade Closed [{result}]</b>\n"
        f"{trade['question']}\n\n"
        f"Direction:  {trade['direction']}\n"
        f"Entry:      {trade['entry_prob']}%\n"
        f"Exit:       {trade.get('exit_prob', '?')}%\n"
        f"P&L:        {sign}{pnl:.1f}pp\n"
        f"Reason:     {reason_labels.get(trade.get('exit_reason', ''), trade.get('exit_reason', 'unknown'))}"
    )
    send(msg)


def summary_alert(metrics: dict, n_new: int, n_closed: int) -> None:
    """Send a run summary with performance metrics."""
    if not metrics:
        msg = (
            f"<b>Bot Run Complete</b>\n\n"
            f"New trades:    {n_new}\n"
            f"Trades closed: {n_closed}\n"
            f"No closed trades yet for stats."
        )
    else:
        msg = (
            f"<b>Bot Run Complete</b>\n\n"
            f"New trades:    {n_new}\n"
            f"Trades closed: {n_closed}\n"
            f"Open positions: {metrics['open_trades']}\n\n"
            f"<b>Performance (all time)</b>\n"
            f"Total closed: {metrics['total_trades']}\n"
            f"Win rate:     {metrics['win_rate']}%  "
            f"(W:{metrics['wins']} L:{metrics['losses']})\n"
            f"Total P&L:    {metrics['total_pnl']:+.1f}pp\n"
            f"Avg win:      {metrics['avg_win']:+.1f}pp\n"
            f"Avg loss:     {metrics['avg_loss']:+.1f}pp\n"
            f"Best trade:   {metrics['best_trade']:+.1f}pp\n"
            f"Worst trade:  {metrics['worst_trade']:+.1f}pp"
        )
    send(msg)
