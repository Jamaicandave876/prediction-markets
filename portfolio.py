from __future__ import annotations
"""
Portfolio simulator — tracks a hypothetical balance across both bots.

Position sizing is dynamic:
  - Base stake = BASE_STAKE_PCT of current balance
  - Scaled by signal confidence (drift_score, spike_ratio)
  - Reduced after consecutive losses
  - Floor: MIN_STAKE Mana, ceiling: MAX_STAKE_PCT of balance

Each trade stores its own `stake` field so P&L is always accurate.
"""

import json
import logging
from pathlib import Path
from config import STARTING_BALANCE

log = logging.getLogger("portfolio")

PORTFOLIO_FILE = Path("portfolio.json")

# ── Sizing Parameters ────────────────────────────────────────────────────────
BASE_STAKE_PCT  = 0.05    # 5% of balance per trade
MAX_STAKE_PCT   = 0.10    # never risk more than 10% on one trade
MIN_STAKE       = 20      # floor — always at least 20 Mana
CONSEC_LOSS_DAMPEN = 0.80 # multiply stake by this per consecutive loss


# ── Portfolio State ──────────────────────────────────────────────────────────

def _default_state() -> dict:
    return {
        "starting_balance": STARTING_BALANCE,
        "realized_pnl": 0.0,
        "total_trades_counted": 0,
    }


def load_portfolio() -> dict:
    if PORTFOLIO_FILE.exists():
        try:
            data = json.loads(PORTFOLIO_FILE.read_text())
            data["starting_balance"] = STARTING_BALANCE
            return data
        except (json.JSONDecodeError, ValueError):
            log.warning("Corrupt portfolio.json — resetting")
    return _default_state()


def save_portfolio(state: dict) -> None:
    PORTFOLIO_FILE.write_text(json.dumps(state, indent=2))


def get_balance(state: dict) -> float:
    """Current balance = starting + realized P&L."""
    return round(state["starting_balance"] + state["realized_pnl"], 2)


# ── Dynamic Position Sizing ─────────────────────────────────────────────────

def _count_recent_consecutive_losses(all_trades: list[dict]) -> int:
    """Count consecutive losses from the most recent closed trade backwards."""
    closed = [t for t in all_trades if t["status"] == "closed" and t.get("pnl_pp") is not None]
    closed.sort(key=lambda t: t.get("exit_time", ""), reverse=True)
    streak = 0
    for t in closed:
        if t["pnl_pp"] <= 0:
            streak += 1
        else:
            break
    return streak


def compute_stake(balance: float, signal: dict, all_trades: list[dict], bot: str = "momentum") -> float:
    """
    Compute dynamic stake for a new trade.

    Sizing logic:
      1. Base = BASE_STAKE_PCT * current_balance
      2. Confidence multiplier (0.7x – 1.5x) from signal strength
      3. Dampen after consecutive losses (0.8x per loss in streak)
      4. Clamp to [MIN_STAKE, MAX_STAKE_PCT * balance]
    """
    base = balance * BASE_STAKE_PCT

    # Confidence from signal strength
    if bot == "momentum":
        drift = abs(signal.get("drift_score", 0))
        # drift_score typically 2-15; map to 0.7-1.5
        confidence = min(1.5, max(0.7, 0.5 + drift / 15))
    else:  # fade
        ratio = signal.get("spike_ratio", 0)
        # spike_ratio typically 3-20; map to 0.7-1.5
        confidence = min(1.5, max(0.7, 0.4 + ratio / 20))

    stake = base * confidence

    # Dampen after consecutive losses
    streak = _count_recent_consecutive_losses(all_trades)
    if streak > 0:
        dampen = CONSEC_LOSS_DAMPEN ** min(streak, 5)  # cap at 5 losses
        stake *= dampen
        log.info("Loss streak %d → stake dampened by %.0f%%", streak, (1 - dampen) * 100)

    # Clamp
    ceiling = balance * MAX_STAKE_PCT
    stake = max(MIN_STAKE, min(stake, ceiling))

    return round(stake, 1)


# ── Portfolio Sync ───────────────────────────────────────────────────────────

def sync_portfolio(momentum_trades: list[dict], fade_trades: list[dict]) -> dict:
    """
    Recalculate portfolio from all closed trades across both bots.
    Uses per-trade stake if available, falls back to base sizing.
    """
    state = load_portfolio()

    all_closed = []
    for t in momentum_trades + fade_trades:
        if t["status"] == "closed" and t.get("pnl_pp") is not None:
            all_closed.append(t)

    realized_pnl = 0.0
    for t in all_closed:
        stake = t.get("stake", STARTING_BALANCE * BASE_STAKE_PCT)  # fallback for old trades
        realized_pnl += t["pnl_pp"] / 100 * stake

    state["realized_pnl"] = round(realized_pnl, 2)
    state["total_trades_counted"] = len(all_closed)

    save_portfolio(state)
    return state


# ── Unrealized P&L ───────────────────────────────────────────────────────────

def get_unrealized_pnl(open_trades: list[dict], current_probs: dict[str, float]) -> float:
    """Calculate unrealized P&L for open positions."""
    total = 0.0
    for t in open_trades:
        if t["market_id"] not in current_probs:
            continue
        prob = current_probs[t["market_id"]]
        stake = t.get("stake", STARTING_BALANCE * BASE_STAKE_PCT)
        if t["direction"] == "BUY YES":
            pnl_pp = prob - t["entry_prob"]
        else:
            pnl_pp = t["entry_prob"] - prob
        total += pnl_pp / 100 * stake
    return round(total, 2)


# ── Display ──────────────────────────────────────────────────────────────────

def format_balance_summary(state: dict, unrealized: float = 0.0) -> str:
    """Format portfolio summary for display/notifications."""
    balance = get_balance(state)
    starting = state["starting_balance"]
    realized = state["realized_pnl"]
    total_return = ((balance - starting) / starting) * 100 if starting else 0

    lines = [
        f"Balance:     {balance:,.0f} Mana (started {starting:,.0f})",
        f"Realized:    {realized:+,.0f} Mana",
    ]
    if unrealized != 0:
        lines.append(f"Unrealized:  {unrealized:+,.0f} Mana")
        lines.append(f"Total value: {balance + unrealized:,.0f} Mana")
    lines.append(f"Return:      {total_return:+.1f}%")
    return "\n".join(lines)
