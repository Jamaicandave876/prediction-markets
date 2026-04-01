"""
Real-time position tracking dashboard for the 10-bot trading system.
Run:  python dashboard.py
Open: http://localhost:8050
"""

import json
import time
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request

ROOT = Path(__file__).parent
PORT = 8050
API_BASE = "https://api.manifold.markets/v0"

# All bot trade files
BOT_FILES = [
    ("momentum",       "trades.json",                   "trades.backup.json"),
    ("fade",           "fade_trades.json",              "fade_trades.backup.json"),
    ("mean_reversion", "mean_reversion_trades.json",    "mean_reversion_trades.backup.json"),
    ("volume_surge",   "volume_trades.json",            "volume_trades.backup.json"),
    ("whale",          "whale_trades.json",             "whale_trades.backup.json"),
    ("contrarian",     "contrarian_trades.json",        "contrarian_trades.backup.json"),
    ("close_gravity",  "close_gravity_trades.json",     "close_gravity_trades.backup.json"),
    ("fresh_sniper",   "fresh_sniper_trades.json",      "fresh_sniper_trades.backup.json"),
    ("stability",      "stability_trades.json",         "stability_trades.backup.json"),
    ("breakout",       "breakout_trades.json",          "breakout_trades.backup.json"),
]

# ── Cache live prices ────────────────────────────────────────────────────────
_price_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL = 30


def fetch_live_prob(market_id: str) -> float | None:
    with _cache_lock:
        cached = _price_cache.get(market_id)
        if cached and time.time() - cached[1] < CACHE_TTL:
            return cached[0]
    try:
        url = f"{API_BASE}/market/{market_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "dashboard/2.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            prob = round(data.get("probability", 0) * 100, 1)
            with _cache_lock:
                _price_cache[market_id] = (prob, time.time())
            return prob
    except Exception:
        return None


def load_json(name: str):
    p = ROOT / name
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return [] if "trades" in name else {}


def detect_bot_type(trade: dict) -> str:
    """Detect which bot a trade belongs to based on its fields."""
    if "drift_score" in trade and "spike_size" not in trade:
        return "momentum"
    if "spike_size" in trade:
        return "fade"
    if "distance_from_center" in trade:
        return "mean_reversion"
    if "volume_ratio" in trade:
        return "volume_surge"
    if "whale_amount" in trade:
        return "whale"
    if "absorption_score" in trade:
        return "contrarian"
    if "breakout_strength" in trade:
        return "breakout"
    if "stability_score" in trade:
        return "stability"
    if "move_from_open" in trade:
        return "fresh_sniper"
    return "unknown"


def build_api_data() -> dict:
    portfolio = load_json("portfolio.json")
    atlas_state = load_json("atlas_state.json")
    meridian_state = load_json("meridian_state.json")
    sentinel_state = load_json("sentinel_state.json")

    starting = portfolio.get("starting_balance", 1000)
    realized = portfolio.get("realized_pnl", 0)
    balance = starting + realized

    # Load all trades from all bots
    all_open = []
    all_closed = []
    bot_stats = {}

    for bot_name, tf, bf in BOT_FILES:
        trades = load_json(tf)
        if not isinstance(trades, list):
            trades = []
        open_t = [t for t in trades if t.get("status") == "open"]
        closed_t = [t for t in trades if t.get("status") == "closed"]
        for t in open_t:
            t["_bot"] = bot_name
        for t in closed_t:
            t["_bot"] = bot_name
        all_open.extend(open_t)
        all_closed.extend(closed_t)

        # Per-bot stats
        wins = sum(1 for t in closed_t if (t.get("pnl_pp") or 0) > 0)
        total = len(closed_t)
        total_pnl = sum(t.get("pnl_pp", 0) or 0 for t in closed_t)
        bot_scores = atlas_state.get("bot_scores", {}).get(bot_name, {})
        bot_stats[bot_name] = {
            "open": len(open_t),
            "closed": total,
            "wins": wins,
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
            "total_pnl": round(total_pnl, 1),
            "grade": bot_scores.get("grade", "NEW"),
            "score": bot_scores.get("score", 50),
            "paused": atlas_state.get("paused", {}).get(bot_name, False),
        }

    # Fetch live prices for open positions
    positions = []
    unrealized_total = 0.0
    for t in all_open:
        live = fetch_live_prob(t["market_id"])
        entry = t["entry_prob"]
        bot = t.get("_bot", detect_bot_type(t))
        stake = t.get("stake", starting * 0.05)

        if live is not None:
            pnl_pp = (live - entry) if t["direction"] == "BUY YES" else (entry - live)
            pnl_mana = round(pnl_pp / 100 * stake, 1)
            unrealized_total += pnl_mana
        else:
            pnl_pp = None
            pnl_mana = None

        # Generic target/stop (simplified for dashboard)
        if t["direction"] == "BUY YES":
            target = 78
            stop = round(entry - 5, 1)
        else:
            target = 22
            stop = round(entry + 5, 1)

        positions.append({
            "market_id": t["market_id"],
            "question": t["question"],
            "direction": t["direction"],
            "bot": bot,
            "entry_prob": entry,
            "current_prob": live,
            "pnl_pp": round(pnl_pp, 1) if pnl_pp is not None else None,
            "pnl_mana": pnl_mana,
            "stake": round(stake, 1),
            "entry_time": t.get("entry_time", ""),
            "url": t.get("url", ""),
            "target": target,
            "stop": stop,
        })

    # Trade history (last 50)
    history = []
    for t in sorted(all_closed, key=lambda x: x.get("exit_time", ""), reverse=True)[:50]:
        stake = t.get("stake", starting * 0.05)
        pnl_mana = round((t.get("pnl_pp", 0) or 0) / 100 * stake, 1)
        history.append({
            "question": t["question"],
            "direction": t["direction"],
            "bot": t.get("_bot", detect_bot_type(t)),
            "entry_prob": t["entry_prob"],
            "exit_prob": t.get("exit_prob"),
            "pnl_pp": t.get("pnl_pp"),
            "pnl_mana": pnl_mana,
            "exit_reason": t.get("exit_reason", ""),
            "exit_time": t.get("exit_time", ""),
        })

    # Governance data
    exposure = meridian_state.get("direction_exposure", {})
    risk_level = sentinel_state.get("risk_level", "green")
    regime = atlas_state.get("regime", "normal")

    return {
        "portfolio": {
            "starting_balance": starting,
            "realized_pnl": round(realized, 1),
            "balance": round(balance, 1),
            "unrealized_pnl": round(unrealized_total, 1),
            "total_value": round(balance + unrealized_total, 1),
            "return_pct": round(((balance - starting) / starting) * 100, 1) if starting else 0,
            "total_return_pct": round(((balance + unrealized_total - starting) / starting) * 100, 1) if starting else 0,
        },
        "positions": positions,
        "history": history,
        "bot_stats": bot_stats,
        "governance": {
            "regime": regime,
            "risk_level": risk_level,
            "direction": exposure.get("balance", "balanced"),
            "yes_pct": exposure.get("yes_pct", 50),
            "total_stake": exposure.get("total_stake", 0),
        },
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trading System HQ</title>
<style>
  :root {
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #e6edf3; --dim: #8b949e; --green: #3fb950;
    --red: #f85149; --blue: #58a6ff; --orange: #d29922;
    --yellow: #e3b341; --purple: #bc8cff; --pink: #f778ba;
    --cyan: #39d2c0; --teal: #2ea58f;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, 'Segoe UI', sans-serif; padding: 16px; max-width: 1400px; margin: 0 auto; }
  .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
  .header h1 { font-size: 20px; font-weight: 600; }
  .live-dot { width: 8px; height: 8px; background: var(--green); border-radius: 50%; display: inline-block; margin-right: 6px; animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
  .meta { font-size: 12px; color: var(--dim); }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 20px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
  .card .label { font-size: 10px; color: var(--dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
  .card .value { font-size: 20px; font-weight: 700; }
  .card .sub { font-size: 11px; color: var(--dim); margin-top: 2px; }
  .pos { color: var(--green); } .neg { color: var(--red); } .neutral { color: var(--dim); }
  h2 { font-size: 14px; font-weight: 600; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
  .badge { font-size: 10px; background: var(--border); color: var(--dim); padding: 2px 7px; border-radius: 10px; font-weight: 400; }
  .section { margin-bottom: 24px; }

  /* Governance bar */
  .gov-bar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
  .gov-item { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 8px 12px; font-size: 11px; display: flex; align-items: center; gap: 6px; }
  .risk-dot { width: 8px; height: 8px; border-radius: 50%; }
  .risk-green { background: var(--green); }
  .risk-yellow { background: var(--yellow); }
  .risk-red { background: var(--red); }

  /* Bot roster */
  .roster { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px; margin-bottom: 20px; }
  .bot-card { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; }
  .bot-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
  .bot-name { font-size: 12px; font-weight: 600; }
  .bot-grade { font-size: 11px; font-weight: 700; padding: 1px 6px; border-radius: 3px; }
  .grade-A { background: #0f2d1a; color: var(--green); }
  .grade-B { background: #1a2d0f; color: #7ee787; }
  .grade-C { background: #2d2a0f; color: var(--yellow); }
  .grade-D { background: #2d1a0f; color: var(--orange); }
  .grade-F { background: #3d1419; color: var(--red); }
  .grade-NEW { background: var(--border); color: var(--dim); }
  .bot-stats { font-size: 11px; color: var(--dim); }
  .bot-paused { opacity: 0.5; }

  /* Positions */
  .position-list { display: flex; flex-direction: column; gap: 8px; }
  .pos-card { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 10px 14px; }
  .pos-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
  .pos-question { font-size: 12px; font-weight: 500; line-height: 1.4; flex: 1; }
  .pos-question a { color: var(--blue); text-decoration: none; }
  .pos-question a:hover { text-decoration: underline; }
  .pos-pnl { font-size: 16px; font-weight: 700; white-space: nowrap; }
  .pos-meta { display: flex; gap: 12px; margin-top: 6px; font-size: 11px; color: var(--dim); flex-wrap: wrap; }
  .pos-meta span { display: flex; align-items: center; gap: 3px; }

  .tag { font-size: 9px; padding: 1px 5px; border-radius: 3px; font-weight: 600; text-transform: uppercase; }
  .tag-momentum { background: #1f3a5f; color: var(--blue); }
  .tag-fade { background: #3d2e00; color: var(--orange); }
  .tag-mean_reversion { background: #2d0f3d; color: var(--purple); }
  .tag-volume_surge { background: #0f3d2d; color: var(--cyan); }
  .tag-whale { background: #1a1a3d; color: #8b8bff; }
  .tag-contrarian { background: #3d0f2d; color: var(--pink); }
  .tag-close_gravity { background: #2d2d0f; color: var(--yellow); }
  .tag-fresh_sniper { background: #0f2d1a; color: var(--green); }
  .tag-stability { background: #1a2d2d; color: var(--teal); }
  .tag-breakout { background: #3d1a0f; color: #ff9a5c; }
  .tag-unknown { background: var(--border); color: var(--dim); }
  .tag-yes { background: #0f2d1a; color: var(--green); }
  .tag-no { background: #3d1419; color: var(--red); }

  .price-bar { margin-top: 8px; height: 5px; background: var(--border); border-radius: 3px; position: relative; overflow: visible; }
  .price-marker { position: absolute; top: -3px; width: 10px; height: 10px; border-radius: 50%; transform: translateX(-50%); }
  .marker-entry { background: var(--dim); border: 2px solid var(--surface); z-index: 1; }
  .marker-current { background: var(--blue); border: 2px solid var(--surface); z-index: 2; }
  .marker-target { position: absolute; top: -1px; width: 2px; height: 7px; background: var(--green); transform: translateX(-50%); }
  .marker-stop { position: absolute; top: -1px; width: 2px; height: 7px; background: var(--red); transform: translateX(-50%); }

  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th { text-align: left; font-size: 10px; color: var(--dim); text-transform: uppercase; letter-spacing: 0.5px; padding: 6px 8px; border-bottom: 1px solid var(--border); }
  td { padding: 6px 8px; border-bottom: 1px solid var(--border); }
  tr:hover { background: rgba(255,255,255,0.02); }

  .refresh-btn { background: var(--surface); border: 1px solid var(--border); color: var(--dim); padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; }
  .refresh-btn:hover { color: var(--text); border-color: var(--dim); }
  .empty { text-align: center; color: var(--dim); padding: 30px; font-size: 13px; }
  .filter-bar { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
  .filter-btn { background: var(--border); border: none; color: var(--dim); padding: 3px 8px; border-radius: 3px; cursor: pointer; font-size: 10px; text-transform: uppercase; }
  .filter-btn.active { background: var(--blue); color: #fff; }
  .filter-btn:hover { color: var(--text); }
</style>
</head>
<body>

<div class="header">
  <h1><span class="live-dot"></span> Trading System HQ</h1>
  <div style="display:flex;align-items:center;gap:10px;">
    <span class="meta" id="ts">Loading...</span>
    <button class="refresh-btn" onclick="refresh()">Refresh</button>
  </div>
</div>

<div id="gov-bar" class="gov-bar"></div>
<div class="cards" id="cards"></div>
<div id="roster" class="section"></div>
<div id="positions" class="section"></div>
<div id="history" class="section"></div>

<script>
const BOT_NAMES = {
  momentum: 'Momentum', fade: 'Fade', mean_reversion: 'Mean Rev',
  volume_surge: 'Vol Surge', whale: 'Whale', contrarian: 'Contrarian',
  close_gravity: 'Gravity', fresh_sniper: 'Sniper', stability: 'Stable', breakout: 'Breakout'
};
let currentFilter = 'all';
let lastData = null;

async function refresh() {
  try {
    const r = await fetch('/api/data');
    lastData = await r.json();
    render(lastData);
  } catch(e) {
    document.getElementById('ts').textContent = 'Error loading data';
  }
}

function pnlClass(v) { return v > 0.05 ? 'pos' : v < -0.05 ? 'neg' : 'neutral'; }
function sign(v) { return v > 0 ? '+' : ''; }

function setFilter(bot) {
  currentFilter = bot;
  if (lastData) render(lastData);
}

function render(d) {
  const p = d.portfolio;
  const g = d.governance;
  document.getElementById('ts').textContent = 'Updated ' + d.timestamp;

  // Governance bar
  const riskClass = g.risk_level === 'green' ? 'risk-green' : g.risk_level === 'yellow' ? 'risk-yellow' : 'risk-red';
  document.getElementById('gov-bar').innerHTML = `
    <div class="gov-item"><span class="risk-dot ${riskClass}"></span> Risk: ${g.risk_level.toUpperCase()}</div>
    <div class="gov-item">Regime: ${g.regime.toUpperCase()}</div>
    <div class="gov-item">Direction: ${g.direction} (${g.yes_pct}% YES)</div>
    <div class="gov-item">Deployed: ${g.total_stake} M</div>
    <div class="gov-item" style="margin-left:auto;color:var(--dim)">10 bots | 3 governors | 30s refresh</div>
  `;

  // Portfolio cards
  const botCount = Object.values(d.bot_stats).filter(b => b.open > 0).length;
  document.getElementById('cards').innerHTML = `
    <div class="card"><div class="label">Balance</div><div class="value">${p.balance.toLocaleString()}</div><div class="sub">of ${p.starting_balance.toLocaleString()} M</div></div>
    <div class="card"><div class="label">Realized</div><div class="value ${pnlClass(p.realized_pnl)}">${sign(p.realized_pnl)}${p.realized_pnl}</div><div class="sub">${sign(p.return_pct)}${p.return_pct}%</div></div>
    <div class="card"><div class="label">Unrealized</div><div class="value ${pnlClass(p.unrealized_pnl)}">${sign(p.unrealized_pnl)}${p.unrealized_pnl}</div><div class="sub">${d.positions.length} open</div></div>
    <div class="card"><div class="label">Total Value</div><div class="value ${pnlClass(p.total_value - p.starting_balance)}">${p.total_value.toLocaleString()}</div><div class="sub">${sign(p.total_return_pct)}${p.total_return_pct}%</div></div>
    <div class="card"><div class="label">Active Bots</div><div class="value">${botCount}/10</div><div class="sub">${Object.values(d.bot_stats).filter(b=>b.paused).length} paused</div></div>
  `;

  // Bot roster
  const roster = document.getElementById('roster');
  const entries = Object.entries(d.bot_stats).sort((a,b) => b[1].score - a[1].score);
  roster.innerHTML = `<h2>Bot Roster</h2><div class="roster">${entries.map(([name, s]) => {
    const grade = s.grade || 'NEW';
    return `<div class="bot-card ${s.paused ? 'bot-paused' : ''}" onclick="setFilter('${name}')" style="cursor:pointer">
      <div class="bot-top">
        <span class="bot-name"><span class="tag tag-${name}">${BOT_NAMES[name] || name}</span> ${s.paused ? '<span style="color:var(--red);font-size:10px">PAUSED</span>' : ''}</span>
        <span class="bot-grade grade-${grade}">${grade}</span>
      </div>
      <div class="bot-stats">
        ${s.closed > 0 ? `WR: ${s.win_rate}% | P&L: ${sign(s.total_pnl)}${s.total_pnl}pp | ` : ''}Open: ${s.open}
      </div>
    </div>`;
  }).join('')}</div>`;

  // Filter bar + positions
  const posDiv = document.getElementById('positions');
  const filtered = currentFilter === 'all' ? d.positions : d.positions.filter(p => p.bot === currentFilter);
  const filterBtns = `<div class="filter-bar">
    <button class="filter-btn ${currentFilter==='all'?'active':''}" onclick="setFilter('all')">All</button>
    ${Object.keys(BOT_NAMES).map(k => {
      const count = d.positions.filter(p=>p.bot===k).length;
      return count > 0 ? `<button class="filter-btn ${currentFilter===k?'active':''}" onclick="setFilter('${k}')">${BOT_NAMES[k]} (${count})</button>` : '';
    }).join('')}
  </div>`;

  if (filtered.length === 0) {
    posDiv.innerHTML = `<h2>Open Positions <span class="badge">${d.positions.length}</span></h2>${filterBtns}<div class="empty">${currentFilter === 'all' ? 'No open positions' : 'No positions for this bot'}</div>`;
  } else {
    posDiv.innerHTML = `<h2>Open Positions <span class="badge">${filtered.length}${currentFilter!=='all'?' / '+d.positions.length:''}</span></h2>${filterBtns}<div class="position-list">${filtered.map(renderPos).join('')}</div>`;
  }

  // History
  const hDiv = document.getElementById('history');
  const filteredH = currentFilter === 'all' ? d.history : d.history.filter(h => h.bot === currentFilter);
  if (filteredH.length === 0) {
    hDiv.innerHTML = '';
  } else {
    hDiv.innerHTML = `<h2>Trade History <span class="badge">${filteredH.length}</span></h2>
    <table>
      <tr><th>Market</th><th>Bot</th><th>Dir</th><th>Entry</th><th>Exit</th><th>P&L</th><th>Mana</th><th>Reason</th><th>Time</th></tr>
      ${filteredH.map(h => `<tr>
        <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${h.question}</td>
        <td><span class="tag tag-${h.bot}">${BOT_NAMES[h.bot]||h.bot}</span></td>
        <td><span class="tag tag-${h.direction.includes('YES')?'yes':'no'}">${h.direction.replace('BUY ','')}</span></td>
        <td>${h.entry_prob}%</td>
        <td>${h.exit_prob != null ? h.exit_prob + '%' : '-'}</td>
        <td class="${pnlClass(h.pnl_pp)}">${h.pnl_pp != null ? sign(h.pnl_pp)+h.pnl_pp+'pp' : '-'}</td>
        <td class="${pnlClass(h.pnl_mana)}">${sign(h.pnl_mana)}${h.pnl_mana}</td>
        <td>${h.exit_reason || '-'}</td>
        <td style="color:var(--dim);white-space:nowrap;font-size:10px">${h.exit_time || '-'}</td>
      </tr>`).join('')}
    </table>`;
  }
}

function renderPos(p) {
  const pnlText = p.pnl_pp != null ? `${sign(p.pnl_pp)}${p.pnl_pp}pp` : '...';
  const manaText = p.pnl_mana != null ? `${sign(p.pnl_mana)}${p.pnl_mana}M` : '';
  const cls = p.pnl_pp != null ? pnlClass(p.pnl_pp) : 'neutral';
  const entryPct = Math.max(0, Math.min(100, p.entry_prob));
  const currPct = p.current_prob != null ? Math.max(0, Math.min(100, p.current_prob)) : null;
  const targetPct = Math.max(0, Math.min(100, p.target));
  const stopPct = Math.max(0, Math.min(100, p.stop));

  return `<div class="pos-card">
    <div class="pos-top">
      <div class="pos-question"><a href="${p.url}" target="_blank">${p.question}</a></div>
      <div class="pos-pnl ${cls}">${pnlText}${manaText ? `<div style="font-size:11px;font-weight:400;color:var(--dim)">${manaText}</div>` : ''}</div>
    </div>
    <div class="pos-meta">
      <span><span class="tag tag-${p.bot}">${BOT_NAMES[p.bot]||p.bot}</span></span>
      <span><span class="tag tag-${p.direction.includes('YES')?'yes':'no'}">${p.direction}</span></span>
      <span>Entry: ${p.entry_prob}%</span>
      <span>Now: ${p.current_prob != null ? p.current_prob+'%' : '...'}</span>
      <span>Stake: ${p.stake}M</span>
      <span style="font-size:10px;color:var(--dim)">${p.entry_time}</span>
    </div>
    <div class="price-bar">
      <div class="marker-target" style="left:${targetPct}%"></div>
      <div class="marker-stop" style="left:${stopPct}%"></div>
      <div class="price-marker marker-entry" style="left:${entryPct}%"></div>
      ${currPct != null ? `<div class="price-marker marker-current" style="left:${currPct}%"></div>` : ''}
    </div>
  </div>`;
}

refresh();
setInterval(refresh, 30000);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/data":
            data = build_api_data()
            payload = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            page = DASHBOARD_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Dashboard running at http://localhost:{PORT}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()
