"""
Overreaction Fade Bot — Step 1: Spike Detection.

Detects sharp, sudden probability moves that are abnormally large
compared to the market's recent baseline activity.

This is the OPPOSITE of the momentum detector:
  - Momentum bot looks for: steady, consistent drift → ride the trend
  - Spike bot looks for:    sudden, outsized jump  → fade the overreaction

Logic:
  1. Split recent bets into "baseline" (older) and "spike window" (newest)
  2. Measure the spike: how much did prob move in the spike window?
  3. Measure the baseline: what's the normal step size for this market?
  4. Spike ratio = spike size / baseline step size
     (e.g., ratio 5.0 = this move was 5x larger than normal)
  5. Reject high-consistency moves (those are real trends, not overreactions)

Reuses: fetch_binary_markets, fetch_prob_series from detect_momentum.py
"""

import logging
from config import (
    MARKETS_TO_SCAN, SPIKE_BETS_TOTAL, SPIKE_RECENT, SPIKE_MIN_BETS,
    SPIKE_MIN_SIZE, SPIKE_MIN_RATIO, MAX_CONSISTENCY,
)
from detect_momentum import fetch_binary_markets, fetch_prob_series, compute_momentum

log = logging.getLogger(__name__)


def detect_spike(probs: list[float]) -> dict | None:
    """
    Detect if the most recent bets show a spike (potential overreaction).

    Args:
        probs: time-ordered probability series (oldest first)

    Returns:
        dict with spike metrics, or None if not enough data.
    """
    if len(probs) < SPIKE_MIN_BETS:
        return None

    # Split: baseline (older bets) vs spike window (newest bets)
    baseline_probs = probs[:-SPIKE_RECENT]
    spike_probs    = probs[-SPIKE_RECENT:]

    # Spike = total move in the recent window
    spike = spike_probs[-1] - spike_probs[0]
    spike_size = abs(spike) * 100  # in pp

    # Baseline = average absolute step size (what's "normal" for this market)
    baseline_steps = [abs(probs[i + 1] - probs[i]) for i in range(len(baseline_probs) - 1)]
    if not baseline_steps:
        return None
    avg_step = sum(baseline_steps) / len(baseline_steps) * 100  # in pp

    # Spike ratio: how many times larger than normal is this move?
    spike_ratio = spike_size / avg_step if avg_step > 0.01 else 0

    return {
        "spike_size":     round(spike_size, 1),              # pp
        "avg_step":       round(avg_step, 2),                # pp (baseline normal)
        "spike_ratio":    round(spike_ratio, 1),             # times larger than normal
        "spike_dir":      1 if spike > 0 else -1,            # +1 = spiked up, -1 = down
        "pre_spike_prob": round(spike_probs[0] * 100, 1),   # % before the spike began
    }


def main():
    """Standalone demo: scan markets and rank by spike strength."""
    print(f"Scanning {MARKETS_TO_SCAN} markets for overreaction spikes...")
    print(f"  Spike window: last {SPIKE_RECENT} bets")
    print(f"  Min spike:    {SPIKE_MIN_SIZE}pp")
    print(f"  Min ratio:    {SPIKE_MIN_RATIO}x baseline")
    print(f"  Max consist:  {MAX_CONSISTENCY}% (reject real trends)\n")

    markets = fetch_binary_markets(MARKETS_TO_SCAN)
    if not markets:
        print("No markets fetched. API may be down.")
        return

    results = []

    for m in markets:
        probs = fetch_prob_series(m["id"], limit=SPIKE_BETS_TOTAL)
        if len(probs) < SPIKE_MIN_BETS:
            continue

        spike = detect_spike(probs)
        if spike is None:
            continue

        # Also compute momentum to check consistency
        mom = compute_momentum(probs)

        results.append({
            "question":    m["question"],
            "prob_now":    round(m["probability"] * 100, 1),
            "bets_used":   len(probs),
            "spike_size":  spike["spike_size"],
            "avg_step":    spike["avg_step"],
            "spike_ratio": spike["spike_ratio"],
            "spike_dir":   spike["spike_dir"],
            "consistency": mom["consistency"],
        })

    # Show all markets with spike data, sorted by ratio
    results.sort(key=lambda r: r["spike_ratio"], reverse=True)

    if not results:
        print("No markets had enough bets to analyze.")
        return

    # Print everything first (unfiltered)
    print(f"{'Ratio':>6}  {'Spike':>7}  {'Avg':>6}  {'Consist':>7}  {'Now%':>5}  {'Dir':>4}  Question")
    print("-" * 95)
    for r in results:
        arrow = "^^" if r["spike_dir"] > 0 else "vv"
        q = r["question"][:50]
        if len(r["question"]) > 50:
            q += "..."
        print(
            f"{r['spike_ratio']:>5.1f}x  "
            f"{r['spike_size']:>+6.1f}pp  "
            f"{r['avg_step']:>5.2f}pp  "
            f"{r['consistency']:>6.0f}%   "
            f"{r['prob_now']:>5.1f}  "
            f" {arrow}  {q}"
        )

    # Now show only the ones that pass all filters
    candidates = [
        r for r in results
        if r["spike_size"] >= SPIKE_MIN_SIZE
        and r["spike_ratio"] >= SPIKE_MIN_RATIO
        and r["consistency"] <= MAX_CONSISTENCY
    ]

    print(f"\n--- FADE CANDIDATES (pass all filters) ---\n")
    if not candidates:
        print("  None this scan. Markets are calm or spikes are too consistent (real trends).")
        return

    for r in candidates:
        arrow = "SPIKED UP" if r["spike_dir"] > 0 else "SPIKED DOWN"
        fade = "FADE (sell YES)" if r["spike_dir"] > 0 else "FADE (buy YES)"
        print(f"  {r['question'][:65]}")
        print(f"    {arrow} {r['spike_size']:+.1f}pp in last {SPIKE_RECENT} bets "
              f"({r['spike_ratio']:.1f}x normal)")
        print(f"    Consistency: {r['consistency']:.0f}% (low = likely overreaction)")
        print(f"    Action: {fade} @ {r['prob_now']}%")
        print()


if __name__ == "__main__":
    main()
