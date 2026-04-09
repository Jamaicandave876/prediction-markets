"""
Evolution Engine — the system's learning brain.

This module makes the trading system get smarter over time by:
1. Analyzing WHY trades won or lost (trade autopsy)
2. Building market memory (which market traits predict success)
3. Per-bot adaptive tuning (individual parameter adjustment)
4. Loss reason → action pipeline (auto-fix recurring failure modes)
5. Regime-aware behavior (different modes for different market conditions)
6. Tracking system evolution over time (learning journal)

State is persisted in evolution_state.json.
"""

from __future__ import annotations
import json, logging, os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import Counter

log = logging.getLogger("evolution")

STATE_FILE = Path("evolution_state.json")

# Bot name mapping
BOT_NAMES = {
    'momentum': 'Momentum', 'fade': 'Fade', 'mean_reversion': 'Mean Rev',
    'volume_surge': 'Vol Surge', 'whale': 'Whale', 'contrarian': 'Contrarian',
    'close_gravity': 'Gravity', 'fresh_sniper': 'Sniper', 'stability': 'Stable',
    'breakout': 'Breakout', 'calibration': 'Calibration', 'reversal': 'Reversal',
    'smart_money': 'Smart $', 'time_decay': 'Time Decay', 'sentiment': 'Sentiment',
    'accumulation': 'Accumulate', 'underdog': 'Underdog', 'late_mover': 'Late Mover',
    'hedge': 'Hedge', 'liquidation': 'Liquidation',
    # Weather bots (Polymarket)
    'weather_temperature': 'Wx Temp', 'weather_precipitation': 'Wx Precip',
    'weather_storm': 'Wx Storm', 'weather_divergence': 'Wx Diverge',
}

# Per-bot adjustable parameters and their bounds
BOT_ADJUST_BOUNDS = {
    "stop_pp":          (3, 12, 1),      # stop loss distance
    "trailing_stop_pp": (2, 8,  1),      # trailing stop distance
    "max_days":         (3, 21, 2),      # max trade duration
    "target_spread":    (15, 40, 5),     # how far target is from entry
}

# Loss reason to parameter mapping
LOSS_REASON_ACTIONS = {
    "stopped_out":    {"param": "stop_pp",          "direction": "widen",  "reason": "Too many stop-outs — stops are too tight"},
    "stale":          {"param": "max_days",         "direction": "shorten","reason": "Too many stale exits — holding too long"},
    "trailing_stop":  {"param": "trailing_stop_pp", "direction": "widen",  "reason": "Trailing stops triggering too often — trail is too tight"},
    "reversal":       {"param": "stop_pp",          "direction": "tighten","reason": "Reversals causing big losses — need faster exit"},
    "drift_reversal": {"param": "stop_pp",          "direction": "tighten","reason": "Drift reversals too costly — tighter stops needed"},
    "resolved_loss":  {"param": "max_days",         "direction": "shorten","reason": "Holding to resolution and losing — exit earlier"},
}


def _default_state() -> dict:
    return {
        "market_memory": {},        # market_id -> traits that predicted outcome
        "bot_adjustments": {},      # bot_name -> {param: value} overrides
        "loss_patterns": {},        # bot_name -> {reason: count} rolling
        "win_patterns": {},         # bot_name -> {market_trait: count}
        "learning_journal": [],     # chronological log of lessons learned
        "trade_autopsies": [],      # last N trade analyses
        "regime": "normal",         # normal, cautious, aggressive
        "regime_history": [],       # regime change log
        "bot_confidence": {},       # bot_name -> 0.0-1.0 confidence score
        "last_evolution": None,     # timestamp of last evolution run
        "generation": 0,            # how many evolution cycles have run
    }


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, ValueError):
            pass
    return _default_state()


def save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)


def _load_json(path):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return None


def _parse_time(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
    except Exception:
        return None


# ── 1. TRADE AUTOPSY ────────────────────────────────────────────────────────

def autopsy_trade(trade: dict, bot_key: str) -> dict:
    """Analyze a single closed trade to extract lessons."""
    pnl = trade.get("pnl_pp", 0)
    entry_prob = trade.get("entry_prob", 50)
    exit_prob = trade.get("exit_prob", entry_prob)
    direction = trade.get("direction", "")
    reason = trade.get("exit_reason", "unknown")
    stake = trade.get("stake", 50)

    # Duration
    entry_time = _parse_time(trade.get("entry_time"))
    exit_time = _parse_time(trade.get("exit_time"))
    duration_hours = (exit_time - entry_time).total_seconds() / 3600 if entry_time and exit_time else 0

    # Classify the trade
    if pnl > 5:
        outcome = "strong_win"
    elif pnl > 0:
        outcome = "small_win"
    elif pnl > -3:
        outcome = "small_loss"
    else:
        outcome = "big_loss"

    # Analyze market characteristics
    traits = []
    if entry_prob > 70:
        traits.append("high_prob_entry")
    elif entry_prob < 30:
        traits.append("low_prob_entry")
    else:
        traits.append("mid_prob_entry")

    if duration_hours < 24:
        traits.append("fast_trade")
    elif duration_hours > 168:
        traits.append("slow_trade")

    if direction == "BUY YES":
        traits.append("yes_direction")
    else:
        traits.append("no_direction")

    # Signal strength analysis
    strength = trade.get("signal_strength") or trade.get("drift_score") or trade.get("spike_ratio") or 0
    if abs(strength) > 1.0:
        traits.append("strong_signal")
    elif abs(strength) < 0.5:
        traits.append("weak_signal")

    return {
        "bot": bot_key,
        "market_id": trade.get("market_id", ""),
        "outcome": outcome,
        "pnl_pp": pnl,
        "exit_reason": reason,
        "duration_hours": round(duration_hours, 1),
        "traits": traits,
        "entry_prob": entry_prob,
        "direction": direction,
        "timestamp": trade.get("exit_time", ""),
        "lesson": _derive_lesson(outcome, reason, traits, duration_hours, pnl, bot_key),
    }


def _derive_lesson(outcome, reason, traits, duration_hours, pnl, bot_key):
    """Extract a human-readable lesson from the trade."""
    name = BOT_NAMES.get(bot_key, bot_key)
    if outcome == "big_loss" and reason == "stopped_out" and "weak_signal" in traits:
        return f"{name}: Weak signal led to stop-out. Need stronger signals to justify entry."
    if outcome == "big_loss" and reason == "stale":
        return f"{name}: Held too long with no resolution. Consider shorter max_days."
    if outcome == "big_loss" and reason == "resolved_loss":
        return f"{name}: Held to resolution and lost. Exit before resolution on uncertain markets."
    if outcome == "strong_win" and "fast_trade" in traits:
        return f"{name}: Quick strong win — this signal pattern works well."
    if outcome == "small_loss" and reason == "trailing_stop":
        return f"{name}: Had profit but trailing stop was too tight. Consider widening trail."
    if outcome == "strong_win" and "strong_signal" in traits:
        return f"{name}: Strong signal → strong win. Keep trusting high-confidence entries."
    return f"{name}: {outcome.replace('_', ' ')} via {reason}. PnL: {pnl:+.1f}pp in {duration_hours:.0f}h."


# ── 2. MARKET MEMORY ────────────────────────────────────────────────────────

def update_market_memory(state: dict, autopsy: dict) -> None:
    """Track which market traits correlate with wins/losses."""
    bot_key = autopsy["bot"]
    outcome = autopsy["outcome"]

    # Update per-bot win/loss pattern counts
    if outcome in ("strong_win", "small_win"):
        patterns = state.setdefault("win_patterns", {})
        bot_patterns = patterns.setdefault(bot_key, {})
        for trait in autopsy["traits"]:
            bot_patterns[trait] = bot_patterns.get(trait, 0) + 1
    else:
        patterns = state.setdefault("loss_patterns", {})
        bot_patterns = patterns.setdefault(bot_key, {})
        reason = autopsy["exit_reason"]
        bot_patterns[reason] = bot_patterns.get(reason, 0) + 1


# ── 3. PER-BOT ADAPTIVE TUNING ─────────────────────────────────────────────

def compute_bot_adjustments(state: dict, bot_trades: dict) -> list[dict]:
    """Compute per-bot parameter adjustments based on individual performance."""
    adjustments = []

    for bot_key, trades in bot_trades.items():
        closed = [t for t in trades if t.get("status") == "closed" and t.get("pnl_pp") is not None]
        if len(closed) < 5:
            continue  # Need minimum data

        recent = sorted(closed, key=lambda t: t.get("exit_time", ""), reverse=True)[:10]

        # Loss reason analysis for this specific bot
        loss_reasons = Counter(t.get("exit_reason", "unknown") for t in recent if t.get("pnl_pp", 0) < 0)
        total_losses = sum(loss_reasons.values())

        if total_losses < 3:
            continue

        # Find dominant loss reason (>= 50% of losses)
        for reason, count in loss_reasons.most_common(1):
            if count / total_losses < 0.50:
                continue

            action = LOSS_REASON_ACTIONS.get(reason)
            if not action:
                continue

            param = action["param"]
            direction = action["direction"]

            # Get current value (from bot_adjustments or default)
            current_overrides = state.get("bot_adjustments", {}).get(bot_key, {})
            bounds = BOT_ADJUST_BOUNDS.get(param)
            if not bounds:
                continue

            lo, hi, step = bounds
            current = current_overrides.get(param)

            # Default values if no override exists
            if current is None:
                defaults = {"stop_pp": 5, "trailing_stop_pp": 4, "max_days": 7, "target_spread": 28}
                current = defaults.get(param, lo)

            # Apply adjustment
            if direction == "widen":
                new_val = min(current + step, hi)
            elif direction == "tighten":
                new_val = max(current - step, lo)
            elif direction == "shorten":
                new_val = max(current - step, lo)
            else:
                continue

            if new_val == current:
                continue

            adjustments.append({
                "bot": bot_key,
                "param": param,
                "old_value": current,
                "new_value": new_val,
                "reason": action["reason"],
                "based_on": f"{count}/{total_losses} recent losses are {reason}",
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            })

    return adjustments


def apply_bot_adjustments(state: dict, adjustments: list[dict]) -> None:
    """Apply per-bot parameter adjustments to state."""
    bot_adj = state.setdefault("bot_adjustments", {})
    for adj in adjustments:
        bot_key = adj["bot"]
        if bot_key not in bot_adj:
            bot_adj[bot_key] = {}
        bot_adj[bot_key][adj["param"]] = adj["new_value"]

        # Log to learning journal
        state.setdefault("learning_journal", []).append({
            "type": "bot_adjustment",
            "bot": bot_key,
            "param": adj["param"],
            "old": adj["old_value"],
            "new": adj["new_value"],
            "reason": adj["reason"],
            "timestamp": adj["timestamp"],
        })

    # Keep journal manageable
    if len(state["learning_journal"]) > 200:
        state["learning_journal"] = state["learning_journal"][-100:]


def get_bot_overrides(bot_key: str) -> dict:
    """Get the current per-bot parameter overrides (called by bot_engine)."""
    state = load_state()
    return state.get("bot_adjustments", {}).get(bot_key, {})


# ── 4. CAPITAL WEIGHT INTEGRATION ──────────────────────────────────────────

def get_capital_weight(bot_key: str) -> float:
    """Get the capital weight multiplier for a bot based on Atlas grades.
    Called by portfolio.compute_stake() to scale position sizes.
    A=1.3x, B=1.1x, C=1.0x, D=0.8x, F=0.6x, NEW=0.9x"""
    try:
        atlas = _load_json("atlas_state.json") or {}
        scores = atlas.get("bot_scores", {}).get(bot_key, {})
        grade = scores.get("grade", "NEW")
    except Exception:
        grade = "NEW"

    weights = {"A": 1.3, "B": 1.1, "C": 1.0, "D": 0.8, "F": 0.6, "NEW": 0.9}
    return weights.get(grade, 1.0)


# ── 5. CONFIDENCE SCORING ──────────────────────────────────────────────────

def update_bot_confidence(state: dict, bot_trades: dict) -> None:
    """Update per-bot confidence scores (0.0-1.0) based on recent performance.
    Confidence affects how much the system trusts each bot's signals."""
    confidence = state.setdefault("bot_confidence", {})

    for bot_key, trades in bot_trades.items():
        closed = [t for t in trades if t.get("status") == "closed"]
        if not closed:
            confidence[bot_key] = 0.5  # neutral for untested bots
            continue

        recent = sorted(closed, key=lambda t: t.get("exit_time", ""), reverse=True)[:15]
        wins = sum(1 for t in recent if (t.get("pnl_pp") or 0) > 0)
        wr = wins / len(recent) if recent else 0.5

        # Weighted: 60% recent win rate, 40% all-time win rate
        all_wins = sum(1 for t in closed if (t.get("pnl_pp") or 0) > 0)
        all_wr = all_wins / len(closed) if closed else 0.5

        score = 0.6 * wr + 0.4 * all_wr

        # Penalty for consecutive losses
        consec = 0
        for t in recent:
            if (t.get("pnl_pp") or 0) <= 0:
                consec += 1
            else:
                break
        score *= max(0.5, 1.0 - consec * 0.1)  # -10% per consecutive loss, floor 0.5

        # Bonus for profitable bots
        total_pnl = sum(t.get("pnl_pp", 0) for t in closed)
        if total_pnl > 10:
            score = min(1.0, score + 0.1)
        elif total_pnl < -10:
            score = max(0.2, score - 0.1)

        confidence[bot_key] = round(min(1.0, max(0.1, score)), 2)


def get_bot_confidence(bot_key: str) -> float:
    """Get confidence score for a bot. Used to modulate signal trust."""
    state = load_state()
    return state.get("bot_confidence", {}).get(bot_key, 0.5)


# ── 6. REGIME DETECTION ────────────────────────────────────────────────────

def detect_regime(state: dict, bot_trades: dict) -> str:
    """Detect market regime based on system-wide performance.
    Returns: 'aggressive' (markets are predictable), 'normal', or 'cautious' (markets are choppy)"""
    all_recent = []
    for trades in bot_trades.values():
        closed = [t for t in trades if t.get("status") == "closed"]
        recent = sorted(closed, key=lambda t: t.get("exit_time", ""), reverse=True)[:5]
        all_recent.extend(recent)

    if len(all_recent) < 10:
        return "normal"

    wins = sum(1 for t in all_recent if (t.get("pnl_pp") or 0) > 0)
    wr = wins / len(all_recent)
    avg_pnl = sum(t.get("pnl_pp", 0) for t in all_recent) / len(all_recent)

    old_regime = state.get("regime", "normal")

    if wr > 0.60 and avg_pnl > 2:
        new_regime = "aggressive"
    elif wr < 0.35 or avg_pnl < -3:
        new_regime = "cautious"
    else:
        new_regime = "normal"

    if new_regime != old_regime:
        state.setdefault("regime_history", []).append({
            "from": old_regime,
            "to": new_regime,
            "reason": f"WR={wr:.0%}, avg_pnl={avg_pnl:+.1f}pp on {len(all_recent)} recent trades",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        })
        # Keep history manageable
        if len(state["regime_history"]) > 50:
            state["regime_history"] = state["regime_history"][-25:]

        log.info("Regime change: %s -> %s (WR=%.0f%%, avg_pnl=%+.1f)",
                 old_regime, new_regime, wr * 100, avg_pnl)

    state["regime"] = new_regime
    return new_regime


def get_regime() -> str:
    """Get current regime. Called by bots to adjust behavior."""
    state = load_state()
    return state.get("regime", "normal")


def get_regime_multipliers() -> dict:
    """Get regime-specific parameter multipliers.
    Bots use these to scale their thresholds."""
    regime = get_regime()
    if regime == "cautious":
        return {
            "signal_threshold": 1.3,   # require 30% stronger signals
            "stake_multiplier": 0.7,   # reduce position sizes 30%
            "stop_multiplier": 0.8,    # tighter stops (stop_pp * 0.8)
            "max_days_multiplier": 0.7, # shorter hold periods
        }
    elif regime == "aggressive":
        return {
            "signal_threshold": 0.8,   # accept 20% weaker signals
            "stake_multiplier": 1.2,   # increase position sizes 20%
            "stop_multiplier": 1.2,    # wider stops (more room)
            "max_days_multiplier": 1.3, # longer hold periods
        }
    else:
        return {
            "signal_threshold": 1.0,
            "stake_multiplier": 1.0,
            "stop_multiplier": 1.0,
            "max_days_multiplier": 1.0,
        }


# ── 7. MAIN EVOLUTION CYCLE ────────────────────────────────────────────────

def load_all_bot_trades() -> dict:
    """Load trades from all 20 bots."""
    from bot_engine import BOT_TRADE_FILES
    bot_trades = {}
    bot_keys = list(BOT_NAMES.keys())
    for i, (tf, bf) in enumerate(BOT_TRADE_FILES):
        if i < len(bot_keys):
            key = bot_keys[i]
            data = _load_json(tf)
            bot_trades[key] = data if isinstance(data, list) else []
    return bot_trades


def run_evolution() -> dict:
    """Main evolution cycle — called after all bots run.
    Analyzes recent trades, updates memory, adjusts parameters, detects regime."""
    state = load_state()
    bot_trades = load_all_bot_trades()

    state["generation"] = state.get("generation", 0) + 1
    log.info("=== Evolution cycle #%d ===", state["generation"])

    # 1. Trade autopsies on recently closed trades
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=4)  # trades closed since last run
    new_autopsies = []

    for bot_key, trades in bot_trades.items():
        for t in trades:
            if t.get("status") != "closed":
                continue
            exit_time = _parse_time(t.get("exit_time"))
            if not exit_time or exit_time < cutoff:
                continue
            autopsy = autopsy_trade(t, bot_key)
            new_autopsies.append(autopsy)
            update_market_memory(state, autopsy)

    # Store autopsies (keep last 100)
    state.setdefault("trade_autopsies", []).extend(new_autopsies)
    if len(state["trade_autopsies"]) > 100:
        state["trade_autopsies"] = state["trade_autopsies"][-100:]

    # 2. Per-bot adaptive tuning
    adjustments = compute_bot_adjustments(state, bot_trades)
    if adjustments:
        apply_bot_adjustments(state, adjustments)
        log.info("Applied %d bot-specific adjustments", len(adjustments))

    # 3. Update confidence scores
    update_bot_confidence(state, bot_trades)

    # 4. Detect regime
    regime = detect_regime(state, bot_trades)

    # 5. Log lessons
    for autopsy in new_autopsies:
        if autopsy["lesson"]:
            log.info("Lesson: %s", autopsy["lesson"])

    state["last_evolution"] = now.strftime("%Y-%m-%d %H:%M UTC")
    save_state(state)

    return {
        "generation": state["generation"],
        "autopsies": len(new_autopsies),
        "adjustments": adjustments,
        "regime": regime,
        "confidence": state.get("bot_confidence", {}),
    }


# ── Entry point ─────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
    result = run_evolution()
    print(f"\nEvolution #{result['generation']}:")
    print(f"  Autopsies: {result['autopsies']}")
    print(f"  Adjustments: {len(result['adjustments'])}")
    print(f"  Regime: {result['regime']}")
    print(f"  Confidence: {result['confidence']}")


if __name__ == "__main__":
    main()
