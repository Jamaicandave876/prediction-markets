"""
Real-time position tracking dashboard for Manifold Markets trading system.
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

# ── Cache live prices for 30s ────────────────────────────────────────────────
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
        req = urllib.request.Request(url, headers={"User-Agent": "dashboard/1.0"})
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
    return [] if name.endswith("trades.json") else {}


def build_api_data() -> dict:
    portfolio = load_json("portfolio.json")
    momentum = load_json("trades.json")
    fade = load_json("fade_trades.json")
    intel = load_json("intelligence_state.json")

    starting = portfolio.get("starting_balance", 1000)
    realized = portfolio.get("realized_pnl", 0)
    balance = starting + realized

    open_momentum = [t for t in momentum if t["status"] == "open"]
    open_fade = [t for t in fade if t["status"] == "open"]
    closed = [t for t in momentum + fade if t["status"] == "closed"]

    # Fetch live prices for open positions
    positions = []
    unrealized_total = 0.0
    for t in open_momentum + open_fade:
        live = fetch_live_prob(t["market_id"])
        entry = t["entry_prob"]
        bot = "momentum" if "drift_score" in t else "fade"
        stake = t.get("stake", starting * 0.05)

        if live is not None:
            if t["direction"] == "BUY YES":
                pnl_pp = live - entry
            else:
                pnl_pp = entry - live
            pnl_mana = round(pnl_pp / 100 * stake, 1)
            unrealized_total += pnl_mana
        else:
            pnl_pp = None
            pnl_mana = None
            live = None

        # Determine target and stop for progress bar
        if bot == "momentum":
            if t["direction"] == "BUY YES":
                target = 78
                stop = entry - 4
            else:
                target = 22
                stop = entry + 4
        else:
            spike_dir = t.get("spike_dir", 1)
            pre = t.get("pre_spike_prob", entry)
            spike_size = t.get("spike_size", 0)
            normalize_target = pre + spike_size * 0.5 if spike_dir == 1 else pre - spike_size * 0.5
            target = round(normalize_target, 1)
            if spike_dir == 1:
                stop = round(entry + 8, 1)
            else:
                stop = round(entry - 8, 1)

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
            "entry_time": t["entry_time"],
            "url": t.get("url", ""),
            "target": target,
            "stop": stop,
        })

    # Trade history
    history = []
    for t in sorted(closed, key=lambda x: x.get("exit_time", ""), reverse=True):
        stake = t.get("stake", starting * 0.05)
        pnl_mana = round((t.get("pnl_pp", 0) / 100) * stake, 1)
        history.append({
            "question": t["question"],
            "direction": t["direction"],
            "bot": "momentum" if "drift_score" in t else "fade",
            "entry_prob": t["entry_prob"],
            "exit_prob": t.get("exit_prob"),
            "pnl_pp": t.get("pnl_pp"),
            "pnl_mana": pnl_mana,
            "exit_reason": t.get("exit_reason", ""),
            "exit_time": t.get("exit_time", ""),
        })

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
        "intel": {
            "paused": intel.get("paused", {}),
            "consecutive_losses": intel.get("consecutive_losses", {}),
            "last_report": intel.get("last_report", ""),
        },
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Position Tracker</title>
<style>
  :root {
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #e6edf3; --dim: #8b949e; --green: #3fb950;
    --red: #f85149; --blue: #58a6ff; --orange: #d29922;
    --yellow: #e3b341;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, 'Segoe UI', sans-serif; padding: 16px; }
  .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
  .header h1 { font-size: 20px; font-weight: 600; }
  .live-dot { width: 8px; height: 8px; background: var(--green); border-radius: 50%; display: inline-block; margin-right: 6px; animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
  .meta { font-size: 12px; color: var(--dim); }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 24px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
  .card .label { font-size: 11px; color: var(--dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
  .card .value { font-size: 22px; font-weight: 700; }
  .card .sub { font-size: 12px; color: var(--dim); margin-top: 2px; }
  .pos { color: var(--green); } .neg { color: var(--red); } .neutral { color: var(--dim); }
  h2 { font-size: 15px; font-weight: 600; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
  .badge { font-size: 11px; background: var(--border); color: var(--dim); padding: 2px 8px; border-radius: 10px; font-weight: 400; }
  .position-list { display: flex; flex-direction: column; gap: 10px; margin-bottom: 28px; }
  .pos-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; }
  .pos-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
  .pos-question { font-size: 13px; font-weight: 500; line-height: 1.4; flex: 1; }
  .pos-question a { color: var(--blue); text-decoration: none; }
  .pos-question a:hover { text-decoration: underline; }
  .pos-pnl { font-size: 18px; font-weight: 700; white-space: nowrap; }
  .pos-meta { display: flex; gap: 16px; margin-top: 8px; font-size: 12px; color: var(--dim); flex-wrap: wrap; }
  .pos-meta span { display: flex; align-items: center; gap: 4px; }
  .tag { font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 600; text-transform: uppercase; }
  .tag-momentum { background: #1f3a5f; color: var(--blue); }
  .tag-fade { background: #3d2e00; color: var(--orange); }
  .tag-yes { background: #0f2d1a; color: var(--green); }
  .tag-no { background: #3d1419; color: var(--red); }
  .price-bar { margin-top: 10px; height: 6px; background: var(--border); border-radius: 3px; position: relative; overflow: visible; }
  .price-marker { position: absolute; top: -3px; width: 12px; height: 12px; border-radius: 50%; transform: translateX(-50%); }
  .marker-entry { background: var(--dim); border: 2px solid var(--surface); z-index: 1; }
  .marker-current { background: var(--blue); border: 2px solid var(--surface); z-index: 2; }
  .marker-target { position: absolute; top: -1px; width: 2px; height: 8px; background: var(--green); transform: translateX(-50%); }
  .marker-stop { position: absolute; top: -1px; width: 2px; height: 8px; background: var(--red); transform: translateX(-50%); }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; font-size: 11px; color: var(--dim); text-transform: uppercase; letter-spacing: 0.5px; padding: 8px 10px; border-bottom: 1px solid var(--border); }
  td { padding: 8px 10px; border-bottom: 1px solid var(--border); }
  tr:hover { background: rgba(255,255,255,0.02); }
  .status-bar { display: flex; gap: 12px; align-items: center; padding: 8px 12px; background: var(--surface); border: 1px solid var(--border); border-radius: 6px; margin-bottom: 20px; font-size: 12px; }
  .status-item { display: flex; align-items: center; gap: 4px; }
  .paused-tag { background: var(--red); color: white; font-size: 10px; padding: 1px 6px; border-radius: 3px; font-weight: 600; }
  .active-tag { background: var(--green); color: #0d1117; font-size: 10px; padding: 1px 6px; border-radius: 3px; font-weight: 600; }
  .refresh-btn { background: var(--surface); border: 1px solid var(--border); color: var(--dim); padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; }
  .refresh-btn:hover { color: var(--text); border-color: var(--dim); }
  .empty { text-align: center; color: var(--dim); padding: 40px; font-size: 14px; }
</style>
</head>
<body>

<div class="header">
  <h1><span class="live-dot"></span> Position Tracker</h1>
  <div style="display:flex;align-items:center;gap:10px;">
    <span class="meta" id="ts">Loading...</span>
    <button class="refresh-btn" onclick="refresh()">Refresh</button>
  </div>
</div>

<div id="status-bar" class="status-bar"></div>
<div class="cards" id="cards"></div>
<div id="positions"></div>
<div id="history"></div>

<script>
let autoTimer;

async function refresh() {
  try {
    const r = await fetch('/api/data');
    const d = await r.json();
    render(d);
  } catch(e) {
    document.getElementById('ts').textContent = 'Error loading data';
  }
}

function pnlClass(v) { return v > 0.05 ? 'pos' : v < -0.05 ? 'neg' : 'neutral'; }
function sign(v) { return v > 0 ? '+' : ''; }

function render(d) {
  const p = d.portfolio;
  document.getElementById('ts').textContent = 'Updated ' + d.timestamp;

  // Status bar
  const sb = document.getElementById('status-bar');
  const momPaused = d.intel.paused?.momentum;
  const fadePaused = d.intel.paused?.fade;
  sb.innerHTML = `
    <div class="status-item">Momentum: ${momPaused ? '<span class="paused-tag">PAUSED</span>' : '<span class="active-tag">ACTIVE</span>'}</div>
    <div class="status-item">Fade: ${fadePaused ? '<span class="paused-tag">PAUSED</span>' : '<span class="active-tag">ACTIVE</span>'}</div>
    <div class="status-item" style="color:var(--dim)">Losses: M=${d.intel.consecutive_losses?.momentum||0} F=${d.intel.consecutive_losses?.fade||0}</div>
    <div class="status-item" style="margin-left:auto;color:var(--dim)">Auto-refresh 30s</div>
  `;

  // Cards
  document.getElementById('cards').innerHTML = `
    <div class="card"><div class="label">Balance</div><div class="value">${p.balance.toLocaleString()}</div><div class="sub">of ${p.starting_balance.toLocaleString()} Mana</div></div>
    <div class="card"><div class="label">Realized P&L</div><div class="value ${pnlClass(p.realized_pnl)}">${sign(p.realized_pnl)}${p.realized_pnl.toLocaleString()}</div><div class="sub">${sign(p.return_pct)}${p.return_pct}%</div></div>
    <div class="card"><div class="label">Unrealized P&L</div><div class="value ${pnlClass(p.unrealized_pnl)}">${sign(p.unrealized_pnl)}${p.unrealized_pnl.toLocaleString()}</div><div class="sub">${d.positions.length} open</div></div>
    <div class="card"><div class="label">Total Value</div><div class="value ${pnlClass(p.total_value - p.starting_balance)}">${p.total_value.toLocaleString()}</div><div class="sub">${sign(p.total_return_pct)}${p.total_return_pct}% return</div></div>
  `;

  // Positions
  const posDiv = document.getElementById('positions');
  if (d.positions.length === 0) {
    posDiv.innerHTML = '<div class="empty">No open positions</div>';
  } else {
    posDiv.innerHTML = `<h2>Open Positions <span class="badge">${d.positions.length}</span></h2><div class="position-list">${d.positions.map(renderPos).join('')}</div>`;
  }

  // History
  const hDiv = document.getElementById('history');
  if (d.history.length === 0) {
    hDiv.innerHTML = '';
  } else {
    hDiv.innerHTML = `<h2>Trade History <span class="badge">${d.history.length}</span></h2>
    <table>
      <tr><th>Market</th><th>Bot</th><th>Direction</th><th>Entry</th><th>Exit</th><th>P&L</th><th>Mana</th><th>Reason</th><th>Time</th></tr>
      ${d.history.map(h => `<tr>
        <td style="max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${h.question}</td>
        <td><span class="tag tag-${h.bot}">${h.bot}</span></td>
        <td><span class="tag tag-${h.direction.includes('YES')?'yes':'no'}">${h.direction}</span></td>
        <td>${h.entry_prob}%</td>
        <td>${h.exit_prob != null ? h.exit_prob + '%' : '-'}</td>
        <td class="${pnlClass(h.pnl_pp)}">${h.pnl_pp != null ? sign(h.pnl_pp)+h.pnl_pp+'pp' : '-'}</td>
        <td class="${pnlClass(h.pnl_mana)}">${sign(h.pnl_mana)}${h.pnl_mana}</td>
        <td>${h.exit_reason || '-'}</td>
        <td style="color:var(--dim);white-space:nowrap">${h.exit_time || '-'}</td>
      </tr>`).join('')}
    </table>`;
  }
}

function renderPos(p) {
  const pnlText = p.pnl_pp != null ? `${sign(p.pnl_pp)}${p.pnl_pp}pp` : '...';
  const manaText = p.pnl_mana != null ? `${sign(p.pnl_mana)}${p.pnl_mana} M` : '';
  const cls = p.pnl_pp != null ? pnlClass(p.pnl_pp) : 'neutral';

  // Price bar: map 0-100% range
  const entryPct = Math.max(0, Math.min(100, p.entry_prob));
  const currPct = p.current_prob != null ? Math.max(0, Math.min(100, p.current_prob)) : null;
  const targetPct = Math.max(0, Math.min(100, p.target));
  const stopPct = Math.max(0, Math.min(100, p.stop));

  return `<div class="pos-card">
    <div class="pos-top">
      <div class="pos-question"><a href="${p.url}" target="_blank">${p.question}</a></div>
      <div class="pos-pnl ${cls}">${pnlText}${manaText ? `<div style="font-size:12px;font-weight:400;color:var(--dim)">${manaText}</div>` : ''}</div>
    </div>
    <div class="pos-meta">
      <span><span class="tag tag-${p.bot}">${p.bot}</span></span>
      <span><span class="tag tag-${p.direction.includes('YES')?'yes':'no'}">${p.direction}</span></span>
      <span>Entry: ${p.entry_prob}%</span>
      <span>Now: ${p.current_prob != null ? p.current_prob+'%' : '...'}</span>
      <span>Target: ${p.target}%</span>
      <span>Stop: ${p.stop}%</span>
      <span>Stake: ${p.stake} M</span>
      <span style="color:var(--dim)">${p.entry_time}</span>
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
autoTimer = setInterval(refresh, 30000);
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
        pass  # quiet


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Dashboard running at http://localhost:{PORT}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()
