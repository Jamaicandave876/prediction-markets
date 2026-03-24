"""
Telegram notifications for both trading bots.

Each bot's alerts are clearly labeled so you can tell them apart at a glance:
  [MOMENTUM]  = Consensus Momentum Trader
  [FADE]      = Overreaction Fade Bot
"""

import logging
import requests
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger(__name__)

BOT_LABELS = {
    "momentum": "MOMENTUM",
    "fade":     "FADE",
}


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


# ── Momentum Bot Alerts ───────────────────────────────────────────────────────

def signal_alert(trade: dict) -> None:
    """Momentum bot: new entry."""
    arrow = "UP" if trade["direction"] == "BUY YES" else "DOWN"
    msg = (
        f"<b>[MOMENTUM] New Signal [{arrow}]</b>\n"
        f"{trade['question']}\n\n"
        f"Direction:   {trade['direction']}\n"
        f"Prob now:    {trade['entry_prob']}%\n"
        f"Drift score: {trade['drift_score']:+.2f}\n"
        f"\n{trade.get('url', '')}"
    )
    send(msg)


def exit_alert(trade: dict) -> None:
    """Momentum bot: trade closed."""
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
        f"<b>[MOMENTUM] Trade Closed [{result}]</b>\n"
        f"{trade['question']}\n\n"
        f"Direction:  {trade['direction']}\n"
        f"Entry:      {trade['entry_prob']}%\n"
        f"Exit:       {trade.get('exit_prob', '?')}%\n"
        f"P&L:        {sign}{pnl:.1f}pp\n"
        f"Reason:     {reason_labels.get(trade.get('exit_reason', ''), trade.get('exit_reason', 'unknown'))}"
    )
    send(msg)


def summary_alert(metrics: dict, n_new: int, n_closed: int, bot: str = "momentum") -> None:
    """Run summary — works for either bot."""
    label = BOT_LABELS.get(bot, bot.upper())

    if not metrics or not metrics.get("total_trades"):
        msg = (
            f"<b>[{label}] Run Complete</b>\n\n"
            f"New trades:    {n_new}\n"
            f"Trades closed: {n_closed}\n"
            f"Open positions: {metrics.get('open_trades', 0)}\n"
            f"No closed trades yet for stats."
        )
    else:
        msg = (
            f"<b>[{label}] Run Complete</b>\n\n"
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


# ── Fade Bot Alerts ───────────────────────────────────────────────────────────

def fade_signal_alert(trade: dict) -> None:
    """Fade bot: new entry (fading a spike)."""
    spike_dir = "SPIKED UP" if trade["spike_dir"] == 1 else "SPIKED DOWN"
    msg = (
        f"<b>[FADE] Overreaction Detected</b>\n"
        f"{trade['question']}\n\n"
        f"Spike:       {spike_dir} {trade['spike_size']:+.1f}pp "
        f"({trade['spike_ratio']:.1f}x normal)\n"
        f"Pre-spike:   {trade['pre_spike_prob']}%\n"
        f"Spiked to:   {trade['entry_prob']}%\n"
        f"Fading with: {trade['direction']}\n"
        f"\n{trade.get('url', '')}"
    )
    send(msg)


def fade_exit_alert(trade: dict) -> None:
    """Fade bot: trade closed."""
    pnl = trade["pnl_pp"] or 0
    result = "WIN" if pnl > 0 else ("FLAT" if pnl == 0 else "LOSS")
    sign = "+" if pnl >= 0 else ""

    reason_labels = {
        "normalized":     "Price reverted (spike faded)",
        "stopped_out":    "Spike continued (we were wrong)",
        "resolved_win":   "Market resolved in our favor",
        "resolved_loss":  "Market resolved against us",
        "stale":          "Max duration reached",
        "expired":        "Market expired/deleted",
    }

    msg = (
        f"<b>[FADE] Trade Closed [{result}]</b>\n"
        f"{trade['question']}\n\n"
        f"Direction:  {trade['direction']}\n"
        f"Entry:      {trade['entry_prob']}%\n"
        f"Exit:       {trade.get('exit_prob', '?')}%\n"
        f"P&L:        {sign}{pnl:.1f}pp\n"
        f"Reason:     {reason_labels.get(trade.get('exit_reason', ''), trade.get('exit_reason', 'unknown'))}"
    )
    send(msg)
