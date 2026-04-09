"""
Weather Storm Bot — trades extreme weather event markets on Polymarket.

Strategy: Targets hurricane, severe storm, and extreme weather markets.
Supplements Open-Meteo forecasts with NWS alerts API for real-time severe
weather intelligence. Higher edge thresholds due to thinner liquidity.
"""

from __future__ import annotations

import logging
from bot_engine import BotConfig, run_bot
from weather_config import (
    MIN_EDGE_STORM, WX_TARGET_YES, WX_TARGET_NO,
    WX_STOP_PP, WX_TRAILING_STOP_PP, WX_MAX_DAYS_STORM,
    CITY_COORDS,
)
from weather_engine import (
    scan_polymarket_weather_markets,
    parse_weather_market,
    fetch_forecast,
    generate_weather_signal,
    fetch_nws_alerts,
    compute_weather_edge,
)

log = logging.getLogger("wx_storm")

CFG = BotConfig(
    name="weather_storm",
    display_name="Wx Storm",
    trades_file="weather_storm_trades.json",
    backup_file="weather_storm_trades.backup.json",
    target_yes=WX_TARGET_YES,
    target_no=WX_TARGET_NO,
    stop_pp=WX_STOP_PP + 5,   # Wider stops — storm markets are volatile
    trailing_stop_pp=WX_TRAILING_STOP_PP + 4,
    max_days=WX_MAX_DAYS_STORM,
    confidence_field="edge",
)


def detect_signals() -> list[dict]:
    """Scan Polymarket storm/extreme weather markets and generate signals."""
    signals = []

    markets = scan_polymarket_weather_markets()
    log.info("Scanning %d Polymarket weather markets for storm signals", len(markets))

    # Fetch active NWS severe weather alerts
    nws_alerts = fetch_nws_alerts()
    active_severe_events = set()
    for alert in nws_alerts:
        event = alert.get("event", "").lower()
        if any(w in event for w in ["hurricane", "tropical", "tornado", "severe thunderstorm", "flood"]):
            active_severe_events.add(event)

    log.info("Active severe weather events: %d", len(active_severe_events))

    for market in markets:
        parsed = parse_weather_market(market["question"])
        if not parsed:
            # Also catch storm markets by keyword even if parser doesn't match
            q_lower = market["question"].lower()
            if not any(w in q_lower for w in ["hurricane", "tropical", "tornado", "storm", "cyclone", "flooding"]):
                continue
            parsed = {
                "market_type": "storm",
                "city": None,
                "date": None,
                "threshold": None,
                "storm_category": None,
            }

        if parsed["market_type"] != "storm":
            continue

        # For storm markets, use NWS alerts as signal boost
        q_lower = market["question"].lower()
        market_price = market.get("yes_price")
        if market_price is None:
            continue

        # Check if NWS has active alerts that relate to this market
        nws_boost = 0.0
        for event in active_severe_events:
            if any(w in q_lower for w in event.split()):
                nws_boost = 0.15  # NWS confirms active severe weather
                break

        # If market is about hurricane/storm category, estimate probability
        # based on NWS alerts + general weather forecast signals
        if parsed.get("storm_category"):
            # Higher categories are less likely — base probability
            cat = parsed["storm_category"]
            base_prob_map = {1: 0.30, 2: 0.15, 3: 0.08, 4: 0.03, 5: 0.01}
            base_prob = base_prob_map.get(cat, 0.05)
            model_prob = min(base_prob + nws_boost, 0.95)
        else:
            # Generic storm market — use NWS alerts as primary signal
            if nws_boost > 0:
                model_prob = 0.65 + nws_boost  # Active alert = high confidence
            else:
                model_prob = 0.20  # No alert = low probability

        edge_result = compute_weather_edge(model_prob, market_price, MIN_EDGE_STORM)
        if not edge_result:
            continue

        signal = {
            "market_id": market["condition_id"],
            "question": market["question"],
            "direction": edge_result["direction"],
            "entry_prob": round(market_price * 100, 1),
            "url": market.get("url", ""),
            "platform": "polymarket",
            "signal_strength": round(edge_result["edge"] * 10, 2),
            "weather_type": "storm",
            "city": parsed.get("city"),
            "forecast_date": parsed.get("date"),
            "threshold": parsed.get("storm_category"),
            "threshold_unit": "category",
            "gfs_forecast": None,
            "ecmwf_forecast": None,
            "model_prob": edge_result["model_prob"],
            "market_price": edge_result["market_price"],
            "edge": edge_result["edge"],
            "nws_alerts_active": len(active_severe_events),
            "nws_boost": nws_boost,
            "yes_token_id": market.get("yes_token_id"),
            "no_token_id": market.get("no_token_id"),
        }

        log.info(
            "STORM SIGNAL: %s | %s | model=%.0f%% market=%.0f%% edge=%.1f%% nws_boost=%.0f%%",
            signal["direction"], market["question"][:60],
            model_prob * 100, market_price * 100,
            edge_result["edge"] * 100, nws_boost * 100,
        )
        signals.append(signal)

    return signals


def main():
    def _alert(trade):
        from bot_engine import bot_signal_alert
        extra = (
            f"Storm Type:  {trade.get('threshold', 'general')}\n"
            f"NWS Alerts:  {trade.get('nws_alerts_active', 0)} active\n"
            f"Model Prob:  {(trade.get('model_prob', 0) * 100):.0f}%\n"
            f"Market:      {(trade.get('market_price', 0) * 100):.0f}%\n"
            f"Edge:        {(trade.get('edge', 0) * 100):.1f}%\n"
        )
        bot_signal_alert(trade, "WX STORM", extra)

    def _exit_alert(trade):
        from bot_engine import bot_exit_alert
        bot_exit_alert(trade, "WX STORM")

    run_bot(CFG, detect_signals, signal_alert_fn=_alert, exit_alert_fn=_exit_alert)


if __name__ == "__main__":
    main()
