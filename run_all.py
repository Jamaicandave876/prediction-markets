from __future__ import annotations
"""
Master orchestrator — runs all 20 trading bots, governance layer, then evolution engine.

Execution order:
  1. 20 Trading bots (momentum through liquidation)
  2. Meridian (President/COO) — tactical operations
  3. Atlas (CEO) — strategic oversight
  4. Sentinel (Risk Manager) — portfolio-level risk check
  5. Evolution Engine — trade autopsy, market memory, per-bot tuning, regime detection
"""

import sys
import time
import logging
import traceback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("orchestrator")


def run_module(name: str, display: str):
    """Import and run a bot module's main()."""
    t0 = time.time()
    try:
        mod = __import__(name)
        mod.main()
        elapsed = time.time() - t0
        log.info("%s completed in %.1fs", display, elapsed)
    except Exception as e:
        elapsed = time.time() - t0
        log.error("%s FAILED after %.1fs: %s", display, elapsed, e)
        traceback.print_exc()


def main():
    print("=" * 60)
    print("   PREDICTION MARKETS — FULL SYSTEM RUN")
    print("=" * 60)
    t_start = time.time()

    # ── Trading Bots ─────────────────────────────────────────────────────
    bots = [
        ("paper_trades",        "1. Momentum Bot"),
        ("fade_trades",         "2. Fade Bot"),
        ("mean_reversion_bot",  "3. Mean Reversion Bot"),
        ("volume_bot",          "4. Volume Surge Bot"),
        ("whale_bot",           "5. Whale Tracker Bot"),
        ("contrarian_bot",      "6. Contrarian Bot"),
        ("close_gravity_bot",   "7. Close Gravity Bot"),
        ("fresh_sniper_bot",    "8. Fresh Sniper Bot"),
        ("stability_bot",       "9. Stability Bot"),
        ("breakout_bot",        "10. Breakout Bot"),
        ("calibration_bot",     "11. Calibration Bot"),
        ("reversal_bot",        "12. Reversal Bot"),
        ("smart_money_bot",     "13. Smart Money Bot"),
        ("time_decay_bot",      "14. Time Decay Bot"),
        ("sentiment_bot",       "15. Sentiment Divergence Bot"),
        ("accumulation_bot",    "16. Accumulation Bot"),
        ("underdog_bot",        "17. Underdog Bot"),
        ("late_mover_bot",      "18. Late Mover Bot"),
        ("hedge_bot",           "19. Hedge Bot"),
        ("liquidation_bot",     "20. Liquidation Sniper Bot"),
    ]

    print("\n--- TRADING BOTS ---\n")
    for module, display in bots:
        run_module(module, display)

    # ── Governance Layer ─────────────────────────────────────────────────
    governance = [
        ("meridian",  "Meridian (President/COO)"),
        ("atlas",     "Atlas (CEO)"),
        ("sentinel",  "Sentinel (Risk Manager)"),
    ]

    print("\n--- GOVERNANCE LAYER ---\n")
    for module, display in governance:
        run_module(module, display)

    # ── Evolution Engine ─────────────────────────────────────────────
    print("\n--- EVOLUTION ENGINE ---\n")
    run_module("evolution", "Evolution (Learning Brain)")

    elapsed = time.time() - t_start
    print(f"\n{'=' * 60}")
    print(f"   SYSTEM RUN COMPLETE — {elapsed:.0f}s total")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
