from __future__ import annotations
"""
Bot #19: Hedge — finds probability inconsistencies between related markets.

Theory: Manifold has many markets asking similar or related questions.
When two related markets have inconsistent probabilities, one of them
must be wrong. We bet on the correction.

Approach: Search for market PAIRS where the questions overlap significantly
and the probabilities are inconsistent. For example:
  - "Will X happen by June?" at 70%
  - "Will X happen by December?" at 60%
  — This is logically impossible (if 70% by June, must be ≥70% by December)

Implementation: We look for markets with similar keywords in the same
probability band but different directions of recent movement.

Signal:
  - Two markets with overlapping question text (>40% word overlap)
  - Probability difference >15pp
  - The LOWER probability market is the one to bet on (underpriced)
"""

import logging
import re
from bot_engine import (
    BotConfig, run_bot, fetch_binary_markets_flexible,
    bot_signal_alert, bot_exit_alert,
)

log = logging.getLogger("hedge")

LABEL = "HEDGE"

BOT_CONFIG = BotConfig(
    name="hedge",
    display_name="Hedge Bot",
    trades_file="hedge_trades.json",
    backup_file="hedge_trades.backup.json",
    target_yes=75,
    target_no=25,
    stop_pp=6,
    trailing_stop_pp=5,
    max_days=14,
    confidence_field="mispricing_pp",
)

MIN_WORD_OVERLAP = 0.40   # 40% of words must match
MIN_PROB_DIFF = 15        # probabilities must differ by 15+pp
STOP_WORDS = {"will", "the", "a", "an", "in", "by", "be", "to", "of", "is", "it", "?"}


def _extract_keywords(question: str) -> set[str]:
    """Extract meaningful words from a market question."""
    words = set(re.findall(r'[a-zA-Z]+', question.lower()))
    return words - STOP_WORDS


def _word_overlap(q1_words: set[str], q2_words: set[str]) -> float:
    """Jaccard similarity between two keyword sets."""
    if not q1_words or not q2_words:
        return 0.0
    intersection = q1_words & q2_words
    union = q1_words | q2_words
    return len(intersection) / len(union)


def detect_signals() -> list[dict]:
    markets = fetch_binary_markets_flexible(
        n=80,
        min_pool=400,
        min_age_hr=24,
        min_close_days=5,
    )
    if not markets:
        return []

    # Extract keywords for all markets
    market_data = []
    for m in markets:
        prob = round(m.get("probability", 0) * 100, 1)
        if prob > 90 or prob < 10:
            continue
        keywords = _extract_keywords(m["question"])
        if len(keywords) < 3:
            continue
        market_data.append({
            "market": m,
            "prob": prob,
            "keywords": keywords,
        })

    signals = []
    seen_pairs = set()

    # Compare all pairs
    for i, m1 in enumerate(market_data):
        for m2 in market_data[i+1:]:
            overlap = _word_overlap(m1["keywords"], m2["keywords"])
            if overlap < MIN_WORD_OVERLAP:
                continue

            prob_diff = abs(m1["prob"] - m2["prob"])
            if prob_diff < MIN_PROB_DIFF:
                continue

            # Determine which is underpriced
            pair_key = tuple(sorted([m1["market"]["id"], m2["market"]["id"]]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            # If markets are about similar things and one is much lower,
            # that one might be underpriced
            if m1["prob"] < m2["prob"]:
                underpriced = m1
                overpriced = m2
            else:
                underpriced = m2
                overpriced = m1

            # Bet YES on the underpriced market
            signals.append({
                "market_id": underpriced["market"]["id"],
                "question": underpriced["market"]["question"],
                "direction": "BUY YES",
                "entry_prob": underpriced["prob"],
                "related_market": overpriced["market"]["question"][:50],
                "related_prob": overpriced["prob"],
                "word_overlap": round(overlap * 100, 1),
                "mispricing_pp": round(prob_diff, 1),
                "signal_strength": round(min(prob_diff / 30, 1.5), 2),
                "url": underpriced["market"].get("url", ""),
            })

    signals.sort(key=lambda s: s["mispricing_pp"], reverse=True)
    return signals[:3]


def _signal_alert(trade):
    bot_signal_alert(trade, LABEL,
                     f"Related:     {trade.get('related_market', '?')}\n"
                     f"Related @:   {trade.get('related_prob', '?')}%\n"
                     f"Mispricing:  {trade.get('mispricing_pp', 0)}pp gap\n")


def _exit_alert(trade):
    bot_exit_alert(trade, LABEL)


def main():
    run_bot(BOT_CONFIG, detect_signals, _signal_alert, _exit_alert)


if __name__ == "__main__":
    main()
