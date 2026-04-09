"""
Weather Divergence Bot — trades when GFS and ECMWF weather models disagree.

Strategy: When GFS and ECMWF forecasts diverge significantly for a location
with an active Polymarket weather market, the uncertainty creates pricing
inefficiency. This bot trades toward whichever model has been historically
more accurate for that city/season.

Unique edge: systematic, model-driven — not based on a single forecast.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from bot_engine import BotConfig, run_bot
from weather_config import (
    MIN_EDGE_DIVERGENCE, WX_TARGET_YES, WX_TARGET_NO,
    WX_STOP_PP, WX_TRAILING_STOP_PP, WX_MAX_DAYS_DIVERGE,
    CITY_COORDS, DIVERGENCE_THRESHOLD_F,
)
from weather_engine import (
    scan_polymarket_weather_markets,
    parse_weather_market,
    fetch_forecast,
    detect_model_divergence,
    forecast_to_probability,
    compute_weather_edge,
)

log = logging.getLogger("wx_diverge")

HISTORY_FILE = Path("weather_history.json")

CFG = BotConfig(
    name="weather_divergence",
    display_name="Wx Divergence",
    trades_file="weather_divergence_trades.json",
    backup_file="weather_divergence_trades.backup.json",
    target_yes=WX_TARGET_YES,
    target_no=WX_TARGET_NO,
    stop_pp=WX_STOP_PP,
    trailing_stop_pp=WX_TRAILING_STOP_PP,
    max_days=WX_MAX_DAYS_DIVERGE,
    confidence_field="edge",
)


def _load_model_accuracy() -> dict:
    """Load historical model accuracy data to determine which model to trust."""
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text())
            return data.get("model_accuracy", {})
        except (json.JSONDecodeError, ValueError):
            pass
    return {}


def _get_trusted_model(city: str, accuracy_data: dict) -> str:
    """Determine which model to trust more for a given city."""
    city_data = accuracy_data.get(city, {})
    gfs_error = city_data.get("gfs_avg_error")
    ecmwf_error = city_data.get("ecmwf_avg_error")

    if gfs_error is not None and ecmwf_error is not None:
        return "gfs" if gfs_error < ecmwf_error else "ecmwf"

    # Default: ECMWF is generally more accurate globally
    return "ecmwf"


def detect_signals() -> list[dict]:
    """Scan for markets where GFS and ECMWF disagree and trade the divergence."""
    signals = []

    markets = scan_polymarket_weather_markets()
    accuracy_data = _load_model_accuracy()

    log.info("Scanning %d markets for model divergence signals", len(markets))

    for market in markets:
        parsed = parse_weather_market(market["question"])
        if not parsed:
            continue
        if parsed["market_type"] not in ("temperature", "precipitation"):
            continue
        if not parsed.get("city") or parsed["city"] not in CITY_COORDS:
            continue
        if not parsed.get("date"):
            continue
        if parsed.get("threshold") is None:
            continue

        lat, lon = CITY_COORDS[parsed["city"]]
        forecast = fetch_forecast(lat, lon, parsed["date"])
        if not forecast:
            continue

        # Check for model divergence
        divergence = detect_model_divergence(forecast, parsed["market_type"])
        if not divergence:
            continue

        log.info(
            "Model divergence detected: %s | GFS=%.1f ECMWF=%.1f diff=%.1f",
            parsed["city"], divergence["gfs_value"], divergence["ecmwf_value"],
            divergence["divergence"],
        )

        # Determine which model to trust
        trusted_model = _get_trusted_model(parsed["city"], accuracy_data)

        # Use the trusted model's forecast to estimate probability
        threshold = parsed["threshold"]
        if parsed.get("threshold_unit") == "C":
            threshold = threshold * 9 / 5 + 32

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        try:
            target = datetime.strptime(parsed["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            days_out = (target - now).total_seconds() / 86400
        except ValueError:
            continue

        if days_out < 0.5 or days_out > 16:
            continue

        # Get the trusted model's forecast value
        trusted_forecast = forecast.get(trusted_model, {})
        if not trusted_forecast:
            continue

        if parsed["market_type"] == "temperature":
            trusted_value = trusted_forecast.get("temp_max")
            from weather_config import TEMP_BASE_UNCERTAINTY_F
            base_unc = TEMP_BASE_UNCERTAINTY_F
        else:
            trusted_value = trusted_forecast.get("precip_sum")
            from weather_config import PRECIP_BASE_UNCERTAINTY_MM
            base_unc = PRECIP_BASE_UNCERTAINTY_MM

        if trusted_value is None:
            continue

        model_prob = forecast_to_probability(
            trusted_value, threshold, days_out,
            direction=parsed.get("direction", "above"),
            base_uncertainty=base_unc,
        )

        market_price = market.get("yes_price")
        if market_price is None:
            continue

        edge_result = compute_weather_edge(model_prob, market_price, MIN_EDGE_DIVERGENCE)
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
            "weather_type": "divergence",
            "city": parsed["city"],
            "forecast_date": parsed["date"],
            "threshold": threshold,
            "threshold_unit": "F",
            "gfs_forecast": divergence["gfs_value"],
            "ecmwf_forecast": divergence["ecmwf_value"],
            "model_prob": edge_result["model_prob"],
            "market_price": edge_result["market_price"],
            "edge": edge_result["edge"],
            "model_divergence": divergence["divergence"],
            "trusted_model": trusted_model,
            "days_to_resolution": round(days_out, 1),
            "yes_token_id": market.get("yes_token_id"),
            "no_token_id": market.get("no_token_id"),
        }

        log.info(
            "DIVERGE SIGNAL: %s %s | GFS=%.0f ECMWF=%.0f trusted=%s | edge=%.1f%%",
            signal["direction"], parsed["city"],
            divergence["gfs_value"], divergence["ecmwf_value"],
            trusted_model, edge_result["edge"] * 100,
        )
        signals.append(signal)

    return signals


def main():
    def _alert(trade):
        from bot_engine import bot_signal_alert
        extra = (
            f"City:        {trade.get('city', '?')}\n"
            f"GFS:         {trade.get('gfs_forecast', '?')}F\n"
            f"ECMWF:       {trade.get('ecmwf_forecast', '?')}F\n"
            f"Divergence:  {trade.get('model_divergence', '?')}F\n"
            f"Trusted:     {trade.get('trusted_model', '?')}\n"
            f"Edge:        {(trade.get('edge', 0) * 100):.1f}%\n"
        )
        bot_signal_alert(trade, "WX DIVERGE", extra)

    def _exit_alert(trade):
        from bot_engine import bot_exit_alert
        bot_exit_alert(trade, "WX DIVERGE")

    run_bot(CFG, detect_signals, signal_alert_fn=_alert, exit_alert_fn=_exit_alert)


if __name__ == "__main__":
    main()
