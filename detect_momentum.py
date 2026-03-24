"""
Detect probability momentum in prediction markets.

For each market we:
  1. Fetch recent bets and extract the probability series
  2. Compute drift (total prob change) and consistency (directional agreement)
  3. Apply time-decay weighting so recent bets count more than old ones
  4. Combine into drift_score = drift * weighted_consistency

Improvements over v1:
  - Time-decay: recent bets weighted ~7x more than oldest bets
  - Market age filter: skips markets younger than MIN_MARKET_AGE_HR
  - Uses centralized config
"""

import math
import time
import logging
import requests
from config import (
    API_BASE, MIN_POOL, BETS_WINDOW, MIN_BETS,
    DECAY_STRENGTH, MIN_MARKET_AGE_HR,
)

log = logging.getLogger(__name__)


def fetch_binary_markets(n: int) -> list[dict]:
    """Fetch open binary markets with enough liquidity and age."""
    try:
        resp = requests.get(
            f"{API_BASE}/markets",
            params={"limit": min(n * 4, 200)},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error("Failed to fetch markets: %s", e)
        return []

    now_ms = time.time() * 1000
    min_age_ms = MIN_MARKET_AGE_HR * 3_600_000
    results = []

    for m in resp.json():
        if m.get("outcomeType") != "BINARY":
            continue
        if m.get("isResolved"):
            continue

        # Liquidity filter
        pool = m.get("pool", {})
        pool_total = pool.get("YES", 0) + pool.get("NO", 0)
        if pool_total < MIN_POOL:
            continue

        # Market age filter — skip brand-new markets (just noise)
        created = m.get("createdTime", 0)
        if (now_ms - created) < min_age_ms:
            continue

        results.append(m)
        if len(results) >= n:
            break

    return results


def fetch_prob_series(market_id: str, limit: int = BETS_WINDOW) -> list[float]:
    """Return a time-ordered list of probabilities after each bet."""
    try:
        resp = requests.get(
            f"{API_BASE}/bets",
            params={"contractId": market_id, "limit": limit},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning("Failed to fetch bets for %s: %s", market_id, e)
        return []

    bets = resp.json()
    if not bets:
        return []

    bets.sort(key=lambda b: b.get("createdTime", 0))
    return [b["probAfter"] for b in bets if "probAfter" in b]


def compute_momentum(probs: list[float]) -> dict:
    """
    Compute momentum with time-decay weighting.

    Returns:
      drift       : total prob change in pp (+ = rising, - = falling)
      consistency : weighted fraction of steps moving with the drift (0-100%)
      drift_score : drift * consistency — the headline signal
    """
    if len(probs) < 2:
        return {"drift": 0.0, "consistency": 0.0, "drift_score": 0.0}

    drift = probs[-1] - probs[0]
    if drift == 0:
        return {"drift": 0.0, "consistency": 0.0, "drift_score": 0.0}

    direction = 1 if drift > 0 else -1
    steps = [probs[i + 1] - probs[i] for i in range(len(probs) - 1)]
    n = len(steps)

    # Time-decay weights: recent bets matter more
    # weight_i = exp(DECAY_STRENGTH * i / n)
    # With DECAY_STRENGTH=2.0: newest step is ~7.4x heavier than oldest
    weights = [math.exp(DECAY_STRENGTH * i / n) for i in range(n)]
    total_weight = sum(weights)

    # Weighted consistency: what fraction of weighted activity is directional?
    weighted_in_dir = sum(w for s, w in zip(steps, weights) if s * direction > 0)
    consistency = weighted_in_dir / total_weight

    return {
        "drift":       round(drift * 100, 2),
        "consistency": round(consistency * 100, 1),
        "drift_score": round(drift * consistency * 100, 2),
    }


def main():
    """Standalone demo: scan markets and rank by momentum."""
    from config import MARKETS_TO_SCAN

    print(f"Scanning {MARKETS_TO_SCAN} markets for momentum "
          f"(last {BETS_WINDOW} bets, time-decay={DECAY_STRENGTH})...\n")

    markets = fetch_binary_markets(MARKETS_TO_SCAN)
    if not markets:
        print("No markets fetched. API may be down.")
        return

    results = []
    for m in markets:
        probs = fetch_prob_series(m["id"])
        if len(probs) < MIN_BETS:
            continue
        mom = compute_momentum(probs)
        results.append({
            "question":  m["question"],
            "prob_now":  round(m["probability"] * 100, 1),
            "bets_used": len(probs),
            **mom,
        })

    results.sort(key=lambda r: abs(r["drift_score"]), reverse=True)

    if not results:
        print("No markets had enough bets to score.")
        return

    print(f"{'Score':>7}  {'Drift':>7}  {'Consist':>7}  {'Now%':>5}  {'Bets':>4}  Question")
    print("-" * 90)
    for r in results:
        arrow = "^" if r["drift"] > 0 else "v"
        q = r["question"][:55]
        if len(r["question"]) > 55:
            q += "..."
        print(
            f"{r['drift_score']:>+7.2f}  "
            f"{r['drift']:>+6.1f}pp  "
            f"{r['consistency']:>6.0f}%   "
            f"{r['prob_now']:>5.1f}  "
            f"{r['bets_used']:>4}  "
            f"{arrow} {q}"
        )


if __name__ == "__main__":
    main()
