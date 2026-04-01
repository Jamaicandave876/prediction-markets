from __future__ import annotations
"""
Master orchestrator — runs all 10 trading bots, then the governance layer.

Execution order:
  1. Original bots (momentum, fade)
  2. New bots (mean reversion, volume, whale, contrarian, close gravity,
     fresh sniper, stability, breakout)
  3. Meridian (President/COO) — tactical operations
  4. Atlas (CEO) — strategic oversight
  5. Sentinel (Risk Manager) — portfolio-level risk check
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

    elapsed = time.time() - t_start
    print(f"\n{'=' * 60}")
    print(f"   SYSTEM RUN COMPLETE — {elapsed:.0f}s total")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
