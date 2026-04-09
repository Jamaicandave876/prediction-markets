"""
Weather Temperature Bot — trades temperature prediction markets on Polymarket.

Strategy: Compare GFS/ECMWF temperature forecasts to Polymarket market prices.
When weather models predict a significantly different outcome than the market
implies, trade the gap.

Example: Market says 62% chance NYC exceeds 80F, but GFS/ECMWF say 72% → BUY YES.
"""

from __future__ import annotations

import logging
from bot_engine import BotConfig, run_bot
from weather_config import (
    MIN_EDGE_TEMPERATURE, WX_TARGET_YES, WX_TARGET_NO,
    WX_STOP_PP, WX_TRAILING_STOP_PP, WX_MAX_DAYS_TEMP,
    CITY_COORDS,
)
from weather_engine import (
    scan_polymarket_weather_markets,
    parse_weather_market,
    fetch_forecast,
    generate_weather_signal,
)

log = logging.getLogger("wx_temp")

CFG = BotConfig(
    name="weather_temperature",
    display_name="Wx Temperature",
    trades_file="weather_temperature_trades.json",
    backup_file="weather_temperature_trades.backup.json",
    target_yes=WX_TARGET_YES,
    target_no=WX_TARGET_NO,
    stop_pp=WX_STOP_PP,
    trailing_stop_pp=WX_TRAILING_STOP_PP,
    max_days=WX_MAX_DAYS_TEMP,
    confidence_field="edge",
)


def detect_signals() -> list[dict]:
    """Scan Polymarket temperature markets and generate signals."""
    signals = []

    markets = scan_polymarket_weather_markets()
    log.info("Scanning %d Polymarket weather markets for temperature signals", len(markets))

    for market in markets:
        # Parse the market question
        parsed = parse_weather_market(market["question"])
        if not parsed:
            continue
        if parsed["market_type"] != "temperature":
            continue
        if not parsed.get("city") or parsed["city"] not in CITY_COORDS:
            continue
        if not parsed.get("date"):
            continue

        # Fetch weather forecast
        lat, lon = CITY_COORDS[parsed["city"]]
        forecast = fetch_forecast(lat, lon, parsed["date"])
        if not forecast:
            continue

        # Generate signal
        signal = generate_weather_signal(
            market, parsed, forecast,
            min_edge=MIN_EDGE_TEMPERATURE,
        )
        if signal:
            log.info(
                "TEMP SIGNAL: %s %s | %s %.0fF | model=%.0f%% market=%.0f%% edge=%.1f%%",
                signal["direction"], parsed["city"],
                parsed["date"], parsed.get("threshold", 0),
                signal["model_prob"] * 100, signal["market_price"] * 100,
                signal["edge"] * 100,
            )
            signals.append(signal)

    return signals


def main():
    def _alert(trade):
        from bot_engine import bot_signal_alert
        extra = (
            f"City:        {trade.get('city', '?')}\n"
            f"Forecast:    GFS {trade.get('gfs_forecast', '?')}F / ECMWF {trade.get('ecmwf_forecast', '?')}F\n"
            f"Threshold:   {trade.get('threshold', '?')}F\n"
            f"Model Prob:  {(trade.get('model_prob', 0) * 100):.0f}%\n"
            f"Market:      {(trade.get('market_price', 0) * 100):.0f}%\n"
            f"Edge:        {(trade.get('edge', 0) * 100):.1f}%\n"
        )
        bot_signal_alert(trade, "WX TEMP", extra)

    def _exit_alert(trade):
        from bot_engine import bot_exit_alert
        bot_exit_alert(trade, "WX TEMP")

    run_bot(CFG, detect_signals, signal_alert_fn=_alert, exit_alert_fn=_exit_alert)


if __name__ == "__main__":
    main()
