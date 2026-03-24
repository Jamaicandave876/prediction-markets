"""
Step 1: Fetch live prediction market data from Manifold Markets.
Goal: Prove we can see real binary markets and their current probabilities.
No trading logic yet — just data ingestion.
"""

import requests

# --- Config (easy to change) ---
API_BASE = "https://api.manifold.markets/v0"
MARKET_LIMIT = 20          # how many markets to fetch
MIN_POOL_TOTAL = 500       # rough liquidity filter (YES + NO pool in Mana)

def fetch_markets(limit: int = MARKET_LIMIT) -> list[dict]:
    """Fetch recent binary markets from Manifold Markets API."""
    url = f"{API_BASE}/markets"
    # Fetch more than we need so we have enough after filtering to BINARY
    params = {"limit": min(limit * 3, 100)}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    all_markets = resp.json()
    # Keep only binary (YES/NO) markets
    binary = [m for m in all_markets if m.get("outcomeType") == "BINARY"]
    return binary[:limit]


def summarize_market(market: dict) -> dict | None:
    """Extract the fields we care about from a raw market object."""
    # Only include markets that are still open
    if market.get("isResolved") or market.get("closeTime") is None:
        return None

    pool = market.get("pool", {})
    pool_yes = pool.get("YES", 0)
    pool_no = pool.get("NO", 0)
    pool_total = pool_yes + pool_no

    if pool_total < MIN_POOL_TOTAL:
        return None

    prob = market.get("probability")
    if prob is None:
        return None

    return {
        "id": market["id"],
        "question": market["question"],
        "probability": round(prob * 100, 1),   # as a percentage
        "pool_total": round(pool_total),
        "url": market.get("url", ""),
    }


def main():
    print("Fetching markets from Manifold Markets...")
    raw = fetch_markets()
    print(f"  Raw markets returned: {len(raw)}\n")

    markets = [m for r in raw if (m := summarize_market(r)) is not None]
    print(f"  After filters (open, pool >= {MIN_POOL_TOTAL}): {len(markets)} markets\n")

    print(f"{'#':<3}  {'Prob %':<8}  {'Pool':>7}  Question")
    print("-" * 80)
    for i, m in enumerate(markets, 1):
        q = m["question"][:60] + "…" if len(m["question"]) > 60 else m["question"]
        print(f"{i:<3}  {m['probability']:<8}  {m['pool_total']:>7}  {q}")

    print("\nDone. Data fetch working correctly.")


if __name__ == "__main__":
    main()
