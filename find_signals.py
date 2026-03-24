"""
Step 3: Filter momentum scores into actionable paper-trade signals.

A market becomes a candidate only if it passes ALL of:
  1. Probability is inside the entry zone (not too early, not too crowded)
  2. Drift score is strong enough (big + consistent move)
  3. Consistency is high enough (moves are directional, not random noise)

Output: a short list of markets the bot *would* consider entering, with direction.
"""

from detect_momentum import fetch_binary_markets, fetch_prob_series, compute_momentum

# ── Config (change these freely) ──────────────────────────────────────────────
MARKETS_TO_SCAN   = 40      # cast a wider net now that we're filtering

BETS_WINDOW       = 30      # how many recent bets to analyse per market
MIN_BETS          = 8       # skip markets with fewer bets than this

# Entry zone: only enter while consensus is still forming
ENTRY_PROB_LOW    = 45      # % — below this is too uncertain / early
ENTRY_PROB_HIGH   = 72      # % — above this may already be crowded

# Signal quality thresholds
MIN_DRIFT_SCORE   = 2.0     # |drift_score| must exceed this
MIN_CONSISTENCY   = 50      # % of bets must be in the trend direction
# ──────────────────────────────────────────────────────────────────────────────


def evaluate_market(market: dict) -> dict | None:
    """
    Run momentum analysis on a single market.
    Returns a signal dict if it passes all filters, else None.
    """
    probs = fetch_prob_series(market["id"], limit=BETS_WINDOW)
    if len(probs) < MIN_BETS:
        return None

    mom = compute_momentum(probs)
    prob_now = round(market["probability"] * 100, 1)

    # Filter 1: must be inside the entry zone
    if not (ENTRY_PROB_LOW <= prob_now <= ENTRY_PROB_HIGH):
        return None

    # Filter 2: drift score strong enough
    if abs(mom["drift_score"]) < MIN_DRIFT_SCORE:
        return None

    # Filter 3: consistency high enough
    if mom["consistency"] < MIN_CONSISTENCY:
        return None

    direction = "BUY YES" if mom["drift"] > 0 else "BUY NO"

    return {
        "question":    market["question"],
        "direction":   direction,
        "prob_now":    prob_now,
        "drift":       mom["drift"],
        "consistency": mom["consistency"],
        "drift_score": mom["drift_score"],
        "bets_used":   len(probs),
        "url":         market.get("url", ""),
    }


def main():
    print(f"Scanning {MARKETS_TO_SCAN} markets for paper-trade signals...")
    print(f"  Entry zone:   {ENTRY_PROB_LOW}% – {ENTRY_PROB_HIGH}%")
    print(f"  Min score:    {MIN_DRIFT_SCORE}")
    print(f"  Min consist:  {MIN_CONSISTENCY}%\n")

    markets = fetch_binary_markets(MARKETS_TO_SCAN)
    print(f"  Markets fetched: {len(markets)}")

    signals = []
    skipped_bets = 0
    skipped_zone = 0
    skipped_score = 0

    for m in markets:
        probs = fetch_prob_series(m["id"], limit=BETS_WINDOW)
        prob_now = round(m["probability"] * 100, 1)

        if len(probs) < MIN_BETS:
            skipped_bets += 1
            continue

        mom = compute_momentum(probs)

        if not (ENTRY_PROB_LOW <= prob_now <= ENTRY_PROB_HIGH):
            skipped_zone += 1
            continue

        if abs(mom["drift_score"]) < MIN_DRIFT_SCORE:
            skipped_score += 1
            continue

        if mom["consistency"] < MIN_CONSISTENCY:
            skipped_score += 1
            continue

        direction = "BUY YES" if mom["drift"] > 0 else "BUY NO"
        signals.append({
            "question":    m["question"],
            "direction":   direction,
            "prob_now":    prob_now,
            "drift":       mom["drift"],
            "consistency": mom["consistency"],
            "drift_score": mom["drift_score"],
            "bets_used":   len(probs),
            "url":         m.get("url", ""),
        })

    print(f"  Skipped (too few bets):   {skipped_bets}")
    print(f"  Skipped (outside zone):   {skipped_zone}")
    print(f"  Skipped (weak signal):    {skipped_score}")
    print(f"  SIGNALS FOUND:            {len(signals)}\n")

    if not signals:
        print("No signals this scan. Try lowering MIN_DRIFT_SCORE or widening the entry zone.")
        return

    signals.sort(key=lambda s: abs(s["drift_score"]), reverse=True)

    print(f"{'Direction':<10}  {'Score':>6}  {'Drift':>7}  {'Consist':>7}  {'Now%':>5}  Question")
    print("-" * 95)
    for s in signals:
        q = s["question"][:52] + "..." if len(s["question"]) > 52 else s["question"]
        print(
            f"{s['direction']:<10}  "
            f"{s['drift_score']:>+6.2f}  "
            f"{s['drift']:>+6.1f}pp  "
            f"{s['consistency']:>6.0f}%   "
            f"{s['prob_now']:>5.1f}  "
            f"{q}"
        )

    print(f"\n--- Top signal ---")
    top = signals[0]
    print(f"  Action:      {top['direction']}")
    print(f"  Market:      {top['question']}")
    print(f"  Prob now:    {top['prob_now']}%")
    print(f"  Drift:       {top['drift']:+.1f}pp over last {top['bets_used']} bets")
    print(f"  Consistency: {top['consistency']:.0f}% of bets in trend direction")
    print(f"  URL:         {top['url']}")


if __name__ == "__main__":
    main()
