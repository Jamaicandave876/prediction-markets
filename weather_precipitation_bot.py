"""
Weather Precipitation Bot — trades rain/snow prediction markets on Polymarket.

Strategy: Compare GFS/ECMWF precipitation forecasts to Polymarket market prices.
Precipitation forecasts are noisier than temperature, so uses wider thresholds.
"""

from __future__ import annotations

import logging
from bot_engine import BotConfig, run_bot
from weather_config import (
    MIN_EDGE_PRECIPITATION, WX_TARGET_YES, WX_TARGET_NO,
    WX_STOP_PP, WX_TRAILING_STOP_PP, WX_MAX_DAYS_PRECIP,
    CITY_COORDS,
)
from weather_engine import (
    scan_polymarket_weather_markets,
    parse_weather_market,
    fetch_forecast,
    generate_weather_signal,
)

log = logging.getLogger("wx_precip")

CFG = BotConfig(
    name="weather_precipitation",
    display_name="Wx Precipitation",
    trades_file="weather_precipitation_trades.json",
    backup_file="weather_precipitation_trades.backup.json",
    target_yes=WX_TARGET_YES,
    target_no=WX_TARGET_NO,
    stop_pp=WX_STOP_PP + 2,  # Wider stops for noisier precipitation
    trailing_stop_pp=WX_TRAILING_STOP_PP + 2,
    max_days=WX_MAX_DAYS_PRECIP,
    confidence_field="edge",
)


def detect_signals() -> list[dict]:
    """Scan Polymarket precipitation markets and generate signals."""
    signals = []

    markets = scan_polymarket_weather_markets()
    log.info("Scanning %d Polymarket weather markets for precipitation signals", len(markets))

    for market in markets:
        parsed = parse_weather_market(market["question"])
        if not parsed:
            continue
        if parsed["market_type"] != "precipitation":
            continue
        if not parsed.get("city") or parsed["city"] not in CITY_COORDS:
            continue

        lat, lon = CITY_COORDS[parsed["city"]]

        # Use today's date if no specific date parsed
        target_date = parsed.get("date")
        if not target_date:
            from datetime import datetime, timezone, timedelta
            # Default to tomorrow
            target_date = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
            parsed["date"] = target_date

        forecast = fetch_forecast(lat, lon, target_date)
        if not forecast:
            continue

        # For precipitation, use precipitation probability directly if available
        # and no specific threshold was parsed
        if parsed.get("threshold") is None:
            # Binary rain/no-rain market — use precipitation probability
            gfs_precip_prob = (forecast.get("gfs") or {}).get("precip_probability")
            ecmwf_precip_prob = (forecast.get("ecmwf") or {}).get("precip_probability")

            if gfs_precip_prob is not None or ecmwf_precip_prob is not None:
                probs = [p / 100.0 for p in [gfs_precip_prob, ecmwf_precip_prob] if p is not None]
                model_prob = sum(probs) / len(probs)

                market_price = market.get("yes_price")
                if market_price is None:
                    continue

                from weather_engine import compute_weather_edge
                edge_result = compute_weather_edge(model_prob, market_price, MIN_EDGE_PRECIPITATION)
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
                    "weather_type": "precipitation",
                    "city": parsed["city"],
                    "forecast_date": target_date,
                    "threshold": None,
                    "threshold_unit": "probability",
                    "gfs_forecast": gfs_precip_prob,
                    "ecmwf_forecast": ecmwf_precip_prob,
                    "model_prob": edge_result["model_prob"],
                    "market_price": edge_result["market_price"],
                    "edge": edge_result["edge"],
                    "precip_type": parsed.get("precip_type", "any"),
                    "yes_token_id": market.get("yes_token_id"),
                    "no_token_id": market.get("no_token_id"),
                }
                signals.append(signal)
                continue

        # Threshold-based precipitation market
        signal = generate_weather_signal(
            market, parsed, forecast,
            min_edge=MIN_EDGE_PRECIPITATION,
        )
        if signal:
            signal["precip_type"] = parsed.get("precip_type", "any")
            log.info(
                "PRECIP SIGNAL: %s %s | %s | edge=%.1f%%",
                signal["direction"], parsed["city"],
                parsed["date"], signal["edge"] * 100,
            )
            signals.append(signal)

    return signals


def main():
    def _alert(trade):
        from bot_engine import bot_signal_alert
        extra = (
            f"City:        {trade.get('city', '?')}\n"
            f"Type:        {trade.get('precip_type', 'any')}\n"
            f"Model Prob:  {(trade.get('model_prob', 0) * 100):.0f}%\n"
            f"Market:      {(trade.get('market_price', 0) * 100):.0f}%\n"
            f"Edge:        {(trade.get('edge', 0) * 100):.1f}%\n"
        )
        bot_signal_alert(trade, "WX PRECIP", extra)

    def _exit_alert(trade):
        from bot_engine import bot_exit_alert
        bot_exit_alert(trade, "WX PRECIP")

    run_bot(CFG, detect_signals, signal_alert_fn=_alert, exit_alert_fn=_exit_alert)


if __name__ == "__main__":
    main()
