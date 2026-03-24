"""
Telegram notifications for the paper trading bot.
Sends a message to your phone when a signal fires or a trade closes.
"""

import requests
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID


def send(message: str) -> bool:
    """Send a Telegram message. Returns True if successful."""
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        return r.ok
    except Exception as e:
        print(f"  [notify] Failed to send Telegram message: {e}")
        return False


def signal_alert(trade: dict) -> None:
    direction = trade["direction"]
    prob      = trade["entry_prob"]
    score     = trade["drift_score"]
    question  = trade["question"]
    url       = trade.get("url", "")

    arrow = "UP" if direction == "BUY YES" else "DOWN"
    msg = (
        f"<b>New Signal [{arrow}]</b>\n"
        f"{question}\n\n"
        f"Direction:  {direction}\n"
        f"Prob now:   {prob}%\n"
        f"Score:      {score:+.2f}\n"
        f"\n{url}"
    )
    send(msg)


def exit_alert(trade: dict) -> None:
    pnl    = trade["pnl_pp"] or 0
    reason = trade["exit_reason"]
    result = "WIN" if pnl > 0 else ("FLAT" if pnl == 0 else "LOSS")
    sign   = "+" if pnl >= 0 else ""

    reason_labels = {
        "target_hit": "Target reached",
        "reversal":   "Reversed against us",
        "expired":    "Market expired",
    }

    msg = (
        f"<b>Trade Closed [{result}]</b>\n"
        f"{trade['question']}\n\n"
        f"Direction:  {trade['direction']}\n"
        f"Entry:      {trade['entry_prob']}%\n"
        f"Exit:       {trade['exit_prob']}%\n"
        f"P&L:        {sign}{pnl}pp\n"
        f"Reason:     {reason_labels.get(reason, reason)}"
    )
    send(msg)
