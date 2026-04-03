"""
Reporting module — generates formatted digests and reports for multi-channel delivery.
Used by scheduled tasks to post to Slack, Gmail, and Notion.
"""

from __future__ import annotations
import json, os, logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)

# Bot name mapping (matches bot_engine.py BOT_TRADE_FILES order)
BOT_NAMES = {
    'momentum': 'Momentum', 'fade': 'Fade', 'mean_reversion': 'Mean Rev',
    'volume_surge': 'Vol Surge', 'whale': 'Whale', 'contrarian': 'Contrarian',
    'close_gravity': 'Gravity', 'fresh_sniper': 'Sniper', 'stability': 'Stable',
    'breakout': 'Breakout', 'calibration': 'Calibration', 'reversal': 'Reversal',
    'smart_money': 'Smart $', 'time_decay': 'Time Decay', 'sentiment': 'Sentiment',
    'accumulation': 'Accumulate', 'underdog': 'Underdog', 'late_mover': 'Late Mover',
    'hedge': 'Hedge', 'liquidation': 'Liquidation',
}

TRADE_FILES = [
    ('momentum', 'trades.json'), ('fade', 'fade_trades.json'),
    ('mean_reversion', 'mean_reversion_trades.json'), ('volume_surge', 'volume_trades.json'),
    ('whale', 'whale_trades.json'), ('contrarian', 'contrarian_trades.json'),
    ('close_gravity', 'close_gravity_trades.json'), ('fresh_sniper', 'fresh_sniper_trades.json'),
    ('stability', 'stability_trades.json'), ('breakout', 'breakout_trades.json'),
    ('calibration', 'calibration_trades.json'), ('reversal', 'reversal_trades.json'),
    ('smart_money', 'smart_money_trades.json'), ('time_decay', 'time_decay_trades.json'),
    ('sentiment', 'sentiment_trades.json'), ('accumulation', 'accumulation_trades.json'),
    ('underdog', 'underdog_trades.json'), ('late_mover', 'late_mover_trades.json'),
    ('hedge', 'hedge_trades.json'), ('liquidation', 'liquidation_trades.json'),
]


def _load_json(path):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return None


def load_all_data(base_dir='.'):
    """Load all trade files and state from the repo directory."""
    bot_trades = {}
    for bot_key, filename in TRADE_FILES:
        data = _load_json(os.path.join(base_dir, filename))
        bot_trades[bot_key] = data if isinstance(data, list) else []

    portfolio = _load_json(os.path.join(base_dir, 'portfolio.json')) or {}
    atlas = _load_json(os.path.join(base_dir, 'atlas_state.json')) or {}
    intel = _load_json(os.path.join(base_dir, 'intelligence_state.json')) or {}
    sentinel = _load_json(os.path.join(base_dir, 'sentinel_state.json')) or {}
    meridian = _load_json(os.path.join(base_dir, 'meridian_state.json')) or {}

    return {
        'bot_trades': bot_trades,
        'portfolio': portfolio,
        'atlas': atlas,
        'intel': intel,
        'sentinel': sentinel,
        'meridian': meridian,
    }


def compute_stats(data):
    """Compute portfolio and bot-level statistics."""
    portfolio = data['portfolio']
    starting = portfolio.get('starting_balance', 1000)
    realized = portfolio.get('realized_pnl', 0)
    balance = starting + realized
    ret_pct = round((balance - starting) / starting * 100, 1) if starting else 0

    all_open = []
    all_closed = []
    bot_stats = {}

    for bot_key, trades in data['bot_trades'].items():
        open_t = [t for t in trades if t.get('status') == 'open']
        closed_t = [t for t in trades if t.get('status') == 'closed']
        all_open.extend(open_t)
        all_closed.extend(closed_t)

        wins = [t for t in closed_t if (t.get('pnl_pp') or 0) > 0]
        losses = [t for t in closed_t if (t.get('pnl_pp') or 0) < 0]
        total_pnl = sum(t.get('pnl_pp', 0) for t in closed_t)
        wr = round(len(wins) / len(closed_t) * 100, 1) if closed_t else 0

        scores = (data['atlas'].get('bot_scores') or {}).get(bot_key, {})
        paused = (data['intel'].get('paused') or {}).get(bot_key, False)
        consec = (data['intel'].get('consecutive_losses') or {}).get(bot_key, 0)

        bot_stats[bot_key] = {
            'name': BOT_NAMES.get(bot_key, bot_key),
            'open': len(open_t),
            'closed': len(closed_t),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': wr,
            'total_pnl': round(total_pnl, 1),
            'avg_win': round(sum(t.get('pnl_pp', 0) for t in wins) / len(wins), 1) if wins else 0,
            'avg_loss': round(sum(t.get('pnl_pp', 0) for t in losses) / len(losses), 1) if losses else 0,
            'grade': scores.get('grade', 'NEW'),
            'paused': paused,
            'consec_losses': consec,
        }

    # Recent activity (last 24h)
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    recent_entries = [t for t in all_open if _parse_time(t.get('entry_time')) and _parse_time(t['entry_time']) > cutoff_24h]
    recent_exits = [t for t in all_closed if _parse_time(t.get('exit_time')) and _parse_time(t['exit_time']) > cutoff_24h]

    risk_level = data['sentinel'].get('risk_level', 'green')
    direction = (data['meridian'].get('direction_exposure') or {}).get('balance', 'balanced')

    return {
        'starting': starting,
        'balance': balance,
        'realized': realized,
        'return_pct': ret_pct,
        'total_open': len(all_open),
        'total_closed': len(all_closed),
        'bot_stats': bot_stats,
        'recent_entries': len(recent_entries),
        'recent_exits': len(recent_exits),
        'risk_level': risk_level,
        'direction': direction,
        'all_closed': all_closed,
    }


def _parse_time(s):
    if not s:
        return None
    try:
        s = s.replace(' UTC', '+00:00').replace(' ', 'T')
        return datetime.fromisoformat(s)
    except Exception:
        return None


def format_daily_digest_slack(stats):
    """Format a daily digest for Slack (mrkdwn)."""
    date_str = datetime.now(timezone.utc).strftime('%b %d, %Y')
    sign = '+' if stats['realized'] >= 0 else ''

    lines = [
        f"*Daily Trading Digest -- {date_str}*",
        "",
        "*Portfolio*",
        f"Balance: {stats['balance']:,.0f} / {stats['starting']:,.0f} Mana | Return: {sign}{stats['return_pct']}%",
        f"Open: {stats['total_open']} positions | Risk: {stats['risk_level'].upper()} | Direction: {stats['direction']}",
        "",
        "*Bot Performance*",
    ]

    # Sort bots by total PnL
    sorted_bots = sorted(stats['bot_stats'].items(), key=lambda x: x[1]['total_pnl'], reverse=True)
    for key, bs in sorted_bots:
        status = 'PAUSED' if bs['paused'] else 'Active'
        if bs['closed'] > 0:
            lines.append(f"`{bs['name']:12s}` {status:7s} | WR {bs['win_rate']:5.1f}% | PnL {bs['total_pnl']:+.1f}pp | O:{bs['open']} C:{bs['closed']}")
        else:
            lines.append(f"`{bs['name']:12s}` {status:7s} | No trades yet | O:{bs['open']}")

    lines.extend([
        "",
        "*24h Activity*",
        f"{stats['recent_entries']} new entries, {stats['recent_exits']} exits",
        "",
        "_Dashboard:_ https://jamaicandave876.github.io/prediction-markets/",
    ])

    return '\n'.join(lines)


def format_weekly_report_slack(stats):
    """Format a weekly report for Slack (mrkdwn)."""
    date_str = datetime.now(timezone.utc).strftime('%b %d, %Y')
    sign = '+' if stats['realized'] >= 0 else ''

    # Find best and worst trades
    closed = stats['all_closed']
    best = max(closed, key=lambda t: t.get('pnl_pp', 0)) if closed else None
    worst = min(closed, key=lambda t: t.get('pnl_pp', 0)) if closed else None

    lines = [
        f"*Weekly Performance Report -- Week of {date_str}*",
        "",
        "*Portfolio Summary*",
        f"Balance: {stats['balance']:,.0f} / {stats['starting']:,.0f} Mana",
        f"Return: {sign}{stats['return_pct']}%",
        f"Total closed trades: {stats['total_closed']}",
        f"Open positions: {stats['total_open']}",
        f"Risk level: {stats['risk_level'].upper()}",
        "",
        "*Bot Grades*",
    ]

    for key, bs in sorted(stats['bot_stats'].items(), key=lambda x: x[1]['total_pnl'], reverse=True):
        grade = bs['grade']
        lines.append(f"`[{grade:3s}]` *{bs['name']}* — WR {bs['win_rate']}% | PnL {bs['total_pnl']:+.1f}pp | {bs['closed']} trades")

    if best:
        lines.extend([
            "",
            "*Best Trade*",
            f"> {best.get('question', '?')[:80]}",
            f"> {best.get('pnl_pp', 0):+.1f}pp | {BOT_NAMES.get(best.get('_bot', ''), '?')} | {best.get('exit_reason', '?')}",
        ])

    if worst and (worst.get('pnl_pp', 0) < 0):
        lines.extend([
            "",
            "*Worst Trade*",
            f"> {worst.get('question', '?')[:80]}",
            f"> {worst.get('pnl_pp', 0):+.1f}pp | {BOT_NAMES.get(worst.get('_bot', ''), '?')} | {worst.get('exit_reason', '?')}",
        ])

    # Recommendations
    recs = []
    active_bots = [b for b in stats['bot_stats'].values() if b['closed'] > 0]
    f_bots = [b for b in active_bots if b['grade'] == 'F']
    a_bots = [b for b in active_bots if b['grade'] == 'A']
    if f_bots:
        recs.append(f"Consider removing: {', '.join(b['name'] for b in f_bots)} (F grade)")
    if a_bots:
        recs.append(f"Top performers: {', '.join(b['name'] for b in a_bots)} (A grade)")
    no_trade_bots = [b for b in stats['bot_stats'].values() if b['closed'] == 0 and b['open'] == 0]
    if len(no_trade_bots) > 5:
        recs.append(f"{len(no_trade_bots)} bots haven't traded yet — filters may be too tight")

    if recs:
        lines.extend(["", "*Recommendations*"])
        for r in recs:
            lines.append(f"• {r}")

    lines.extend(["", "_Dashboard:_ https://jamaicandave876.github.io/prediction-markets/"])
    return '\n'.join(lines)


def format_weekly_email_html(stats):
    """Format a weekly report as HTML for Gmail."""
    date_str = datetime.now(timezone.utc).strftime('%B %d, %Y')
    sign = '+' if stats['realized'] >= 0 else ''

    bot_rows = ''
    for key, bs in sorted(stats['bot_stats'].items(), key=lambda x: x[1]['total_pnl'], reverse=True):
        color = '#3fb950' if bs['total_pnl'] >= 0 else '#f85149'
        status = 'PAUSED' if bs['paused'] else 'Active'
        bot_rows += f'<tr><td>{bs["name"]}</td><td>{bs["grade"]}</td><td>{status}</td><td>{bs["win_rate"]}%</td><td style="color:{color}">{bs["total_pnl"]:+.1f}pp</td><td>{bs["closed"]}</td></tr>'

    html = f"""
    <div style="font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto;color:#333">
        <h1 style="color:#16213e;border-bottom:2px solid #58a6ff;padding-bottom:8px">Weekly Trading Report</h1>
        <p style="color:#666">Week of {date_str}</p>

        <h2 style="color:#0f3460">Portfolio</h2>
        <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
            <tr><td style="padding:4px 0;color:#666">Balance</td><td style="font-weight:700">{stats['balance']:,.0f} / {stats['starting']:,.0f} Mana</td></tr>
            <tr><td style="padding:4px 0;color:#666">Return</td><td style="font-weight:700;color:{'#3fb950' if stats['return_pct']>=0 else '#f85149'}">{sign}{stats['return_pct']}%</td></tr>
            <tr><td style="padding:4px 0;color:#666">Open Positions</td><td>{stats['total_open']}</td></tr>
            <tr><td style="padding:4px 0;color:#666">Closed Trades</td><td>{stats['total_closed']}</td></tr>
            <tr><td style="padding:4px 0;color:#666">Risk Level</td><td>{stats['risk_level'].upper()}</td></tr>
        </table>

        <h2 style="color:#0f3460">Bot Performance</h2>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
            <tr style="background:#16213e;color:white"><th style="padding:6px;text-align:left">Bot</th><th>Grade</th><th>Status</th><th>WR</th><th>PnL</th><th>Trades</th></tr>
            {bot_rows}
        </table>

        <p style="margin-top:20px"><a href="https://jamaicandave876.github.io/prediction-markets/" style="color:#58a6ff">View Dashboard</a> | <a href="https://www.notion.so/3378db84130281979730c3cf32d48cb0" style="color:#58a6ff">Notion HQ</a></p>
        <p style="font-size:11px;color:#999;margin-top:20px">Prediction Market Trading System | 20 Bots | Paper Trading on Manifold Markets</p>
    </div>
    """
    return html


def format_trade_alert_slack(trade, bot_key, is_entry=True):
    """Format a single trade alert for Slack."""
    name = BOT_NAMES.get(bot_key, bot_key.upper())

    if is_entry:
        direction = trade.get('direction', '?')
        prob = trade.get('entry_prob', '?')
        stake = trade.get('stake', 0)
        signal = trade.get('drift_score') or trade.get('signal_strength') or trade.get('spike_ratio') or 0
        return (
            f"*[{name}] New Trade*\n"
            f"> {trade.get('question', '?')}\n"
            f"Direction: `{direction}` | Entry: {prob}% | Stake: {stake:.0f}M\n"
            f"Signal: {signal:.2f}"
        )
    else:
        pnl = trade.get('pnl_pp', 0)
        result = 'WIN' if pnl > 0 else ('LOSS' if pnl < 0 else 'FLAT')
        stake = trade.get('stake', 50)
        mana = round(pnl / 100 * stake, 1)
        sign = '+' if pnl >= 0 else ''
        return (
            f"*[{name}] Trade Closed -- {result}*\n"
            f"> {trade.get('question', '?')}\n"
            f"PnL: `{sign}{pnl:.1f}pp` ({sign}{mana}M) | Reason: {trade.get('exit_reason', '?')}"
        )
