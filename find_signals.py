"""
Standalone signal scanner — run this manually to preview what the bot would trade.
Uses the same logic and thresholds as paper_trades.py.
"""

from config import (
    MARKETS_TO_SCAN, BETS_WINDOW, MIN_BETS,
    ENTRY_PROB_LOW, ENTRY_PROB_HIGH, MIN_DRIFT_SCORE, MIN_CONSISTENCY,
)
from detect_momentum import fetch_binary_markets, fetch_prob_series, compute_momentum


def main():
    print(f"Scanning {MARKETS_TO_SCAN} markets for paper-trade signals...")
    print(f"  Entry zone:   {ENTRY_PROB_LOW}% - {ENTRY_PROB_HIGH}%")
    print(f"  Min score:    {MIN_DRIFT_SCORE}")
    print(f"  Min consist:  {MIN_CONSISTENCY}%\n")

    markets = fetch_binary_markets(MARKETS_TO_SCAN)
    print(f"  Markets fetched: {len(markets)}")

    signals = []
    skipped_bets = 0
    skipped_zone = 0
    skipped_score = 0

    for m in markets:
        prob_now = round(m["probability"] * 100, 1)

        if not (ENTRY_PROB_LOW <= prob_now <= ENTRY_PROB_HIGH):
            skipped_zone += 1
            continue

        probs = fetch_prob_series(m["id"], limit=BETS_WINDOW)
        if len(probs) < MIN_BETS:
            skipped_bets += 1
            continue

        mom = compute_momentum(probs)

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

    print(f"  Skipped (outside zone):   {skipped_zone}")
    print(f"  Skipped (too few bets):   {skipped_bets}")
    print(f"  Skipped (weak signal):    {skipped_score}")
    print(f"  SIGNALS FOUND:            {len(signals)}\n")

    if not signals:
        print("No signals this scan. Try lowering MIN_DRIFT_SCORE or widening the entry zone.")
        return

    signals.sort(key=lambda s: abs(s["drift_score"]), reverse=True)

    print(f"{'Direction':<10}  {'Score':>6}  {'Drift':>7}  {'Consist':>7}  {'Now%':>5}  Question")
    print("-" * 95)
    for s in signals:
        q = s["question"][:52]
        if len(s["question"]) > 52:
            q += "..."
        print(
            f"{s['direction']:<10}  "
            f"{s['drift_score']:>+6.2f}  "
            f"{s['drift']:>+6.1f}pp  "
            f"{s['consistency']:>6.0f}%   "
            f"{s['prob_now']:>5.1f}  "
            f"{q}"
        )


if __name__ == "__main__":
    main()
