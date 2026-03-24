"""
Step 2: Detect probability momentum in prediction markets.

For each market we:
  1. Fetch recent bets and extract the probability series (probAfter each bet)
  2. Compute two simple numbers:
       drift      = total prob change over the window (+ means rising, - means falling)
       consistency = fraction of individual bet-moves in the same direction as the drift
  3. Combine into a drift_score = drift * consistency
     e.g. drift_score 0.12 means: prob moved up ~12pp AND moves were mostly upward
          drift_score -0.08 means: prob drifted down ~8pp consistently

No trading decisions yet — just ranking markets by momentum strength.
"""

import requests

# ── Config (change these freely) ──────────────────────────────────────────────
API_BASE        = "https://api.manifold.markets/v0"
MARKETS_TO_SCAN = 15      # how many markets to pull from the feed
MIN_POOL        = 500     # skip very thin markets
BETS_WINDOW     = 30      # how many recent bets to look back through
MIN_BETS        = 8       # need at least this many bets to have a signal
# ──────────────────────────────────────────────────────────────────────────────


def fetch_binary_markets(n: int) -> list[dict]:
    resp = requests.get(f"{API_BASE}/markets", params={"limit": n * 4}, timeout=10)
    resp.raise_for_status()
    return [
        m for m in resp.json()
        if m.get("outcomeType") == "BINARY"
        and not m.get("isResolved")
        and (m.get("pool", {}).get("YES", 0) + m.get("pool", {}).get("NO", 0)) >= MIN_POOL
    ][:n]


def fetch_prob_series(market_id: str, limit: int = BETS_WINDOW) -> list[float]:
    """Return a time-ordered list of probabilities after each bet."""
    resp = requests.get(
        f"{API_BASE}/bets",
        params={"contractId": market_id, "limit": limit},
        timeout=10,
    )
    resp.raise_for_status()
    bets = resp.json()
    if not bets:
        return []
    # API returns newest-first; reverse so we go oldest → newest
    bets.sort(key=lambda b: b["createdTime"])
    return [b["probAfter"] for b in bets if "probAfter" in b]


def compute_momentum(probs: list[float]) -> dict:
    """
    Given an ordered probability series, compute:
      drift       : total change (prob[-1] - prob[0])
      consistency : fraction of steps moving in the same direction as drift
      drift_score : drift * consistency  (the headline signal)
    """
    if len(probs) < 2:
        return {"drift": 0.0, "consistency": 0.0, "drift_score": 0.0}

    drift = probs[-1] - probs[0]
    if drift == 0:
        return {"drift": 0.0, "consistency": 0.0, "drift_score": 0.0}

    direction = 1 if drift > 0 else -1
    steps = [probs[i+1] - probs[i] for i in range(len(probs) - 1)]
    steps_in_direction = sum(1 for s in steps if s * direction > 0)
    consistency = steps_in_direction / len(steps)

    return {
        "drift":       round(drift * 100, 2),        # in percentage points
        "consistency": round(consistency * 100, 1),  # as a %
        "drift_score": round(drift * consistency * 100, 2),
    }


def main():
    print(f"Scanning {MARKETS_TO_SCAN} markets for momentum (last {BETS_WINDOW} bets each)...\n")

    markets = fetch_binary_markets(MARKETS_TO_SCAN)
    results = []

    for m in markets:
        probs = fetch_prob_series(m["id"])
        if len(probs) < MIN_BETS:
            continue
        mom = compute_momentum(probs)
        results.append({
            "question":   m["question"],
            "prob_now":   round(m["probability"] * 100, 1),
            "bets_used":  len(probs),
            **mom,
        })

    # Sort by absolute drift_score (strongest momentum first)
    results.sort(key=lambda r: abs(r["drift_score"]), reverse=True)

    if not results:
        print("No markets had enough bets to score. Try increasing MARKETS_TO_SCAN.")
        return

    print(f"{'Score':>7}  {'Drift':>7}  {'Consist':>7}  {'Now%':>5}  {'Bets':>4}  Question")
    print("-" * 90)
    for r in results:
        arrow = "^" if r["drift"] > 0 else "v"
        q = r["question"][:55] + "…" if len(r["question"]) > 55 else r["question"]
        print(
            f"{r['drift_score']:>+7.2f}  "
            f"{r['drift']:>+6.1f}pp  "
            f"{r['consistency']:>6.0f}%   "
            f"{r['prob_now']:>5.1f}  "
            f"{r['bets_used']:>4}  "
            f"{arrow} {q}"
        )

    print(f"\nHighest momentum: {results[0]['question'][:70]}")
    print(f"  drift_score={results[0]['drift_score']:+.2f}  "
          f"drift={results[0]['drift']:+.1f}pp  "
          f"consistency={results[0]['consistency']:.0f}%")


if __name__ == "__main__":
    main()
