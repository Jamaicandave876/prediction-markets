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
BASE_STAKE_PCT  = 0.05    # 5% of balance per trade (fallback if Kelly unavailable)
MAX_STAKE_PCT   = 0.08    # never risk more than 8% on one trade
MIN_STAKE       = 20      # floor — always at least 20 Mana
CONSEC_LOSS_DAMPEN = 0.80 # multiply stake by this per consecutive loss
KELLY_FRACTION  = 0.25    # use 25% Kelly (conservative — protects against edge overestimation)


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


def _kelly_stake(balance: float, signal: dict) -> float | None:
    """
    Fractional Kelly criterion for prediction markets.

    In a binary market at price p_market, if we estimate true probability p_true:
      For BUY YES: edge = p_true - p_market
      For BUY NO:  edge = (1 - p_true) - (1 - p_market) = p_market - p_true

    Kelly fraction: f* = edge / odds
      For BUY YES at price p: odds = (1-p)/p, so f* = (p_true - p) / (1 - p)
      For BUY NO  at price p: odds = p/(1-p), so f* = (p - p_true) / p

    We use KELLY_FRACTION (0.25) of full Kelly for safety.
    """
    entry_prob = signal.get("entry_prob", 50) / 100  # convert to 0-1
    strength = signal.get("signal_strength", 0)
    direction = signal.get("direction", "")

    if strength <= 0:
        return None

    # Estimate our edge from signal_strength
    # signal_strength maps to how far we think true prob differs from market
    # Scale: strength 0.5 = ~5pp edge, strength 1.0 = ~10pp edge, 1.5 = ~15pp
    edge_pp = min(strength * 10, 20) / 100  # cap at 20pp estimated edge

    if direction == "BUY YES":
        p_market = entry_prob
        p_true = min(p_market + edge_pp, 0.95)
        if p_true <= p_market:
            return None
        kelly_f = (p_true - p_market) / (1 - p_market)
    elif direction == "BUY NO":
        p_market = entry_prob
        p_true = max(p_market - edge_pp, 0.05)
        if p_true >= p_market:
            return None
        kelly_f = (p_market - p_true) / p_market
    else:
        return None

    if kelly_f <= 0:
        return None

    # Apply fractional Kelly
    fraction = kelly_f * KELLY_FRACTION
    return balance * fraction


def compute_stake(balance: float, signal: dict, all_trades: list[dict], bot: str = "momentum") -> float:
    """
    Compute dynamic stake using fractional Kelly criterion.

    Sizing logic:
      1. Try Kelly criterion (0.25x full Kelly) based on signal strength
      2. Fall back to BASE_STAKE_PCT if Kelly unavailable
      3. Dampen after consecutive losses (0.8x per loss in streak)
      4. Clamp to [MIN_STAKE, MAX_STAKE_PCT * balance]
    """
    # Try Kelly first
    kelly = _kelly_stake(balance, signal)
    if kelly is not None and kelly > 0:
        stake = kelly
    else:
        # Fallback: base stake with signal confidence
        strength = signal.get("signal_strength", 0.5)
        confidence = min(1.5, max(0.7, 0.5 + strength))
        stake = balance * BASE_STAKE_PCT * confidence

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
