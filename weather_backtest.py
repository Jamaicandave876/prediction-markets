"""
Weather Backtest Engine — historical data analysis and strategy validation.

Three capabilities:
  A. Forecast Accuracy Tracking — compare past GFS/ECMWF forecasts vs actual outcomes
  B. Market Pattern Analysis — find profitable patterns in resolved Polymarket weather markets
  C. Backtest Engine — replay historical forecasts vs market prices to validate strategy

Data sources:
  - Open-Meteo Historical Weather API (actual observed data, 1940-present)
  - Open-Meteo Previous Runs API (past model forecasts, GFS from 2021, others from 2024)
  - Polymarket Gamma API (resolved markets with price history)

Usage:
  python weather_backtest.py              # Run all three analyses
  python weather_backtest.py --days 90    # Backtest last 90 days
  python weather_backtest.py --accuracy   # Only run accuracy tracking
  python weather_backtest.py --patterns   # Only run pattern analysis
"""

from __future__ import annotations

import json
import sys
import logging
import time
import math
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from weather_config import (
    POLYMARKET_GAMMA_API,
    OPEN_METEO_HISTORICAL_API, OPEN_METEO_PREVIOUS_RUNS_API,
    CITY_COORDS, CITY_ALIASES,
    BACKTEST_DEFAULT_DAYS, BACKTEST_STARTING_BALANCE, BACKTEST_BASE_STAKE_PCT,
    MIN_EDGE_TEMPERATURE, MIN_EDGE_PRECIPITATION,
    TEMP_BASE_UNCERTAINTY_F, PRECIP_BASE_UNCERTAINTY_MM,
)
from weather_engine import (
    parse_weather_market,
    forecast_to_probability,
    compute_weather_edge,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("wx_backtest")

HISTORY_FILE = Path("weather_history.json")
BACKTEST_RESULTS_FILE = Path("weather_backtest_results.json")


# ── Safe File I/O ────────────────────────────────────────────────────────────

def _load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except (json.JSONDecodeError, ValueError):
            pass
    return {"accuracy_records": [], "model_accuracy": {}, "patterns": {}, "updated_at": None}


def _save_history(data: dict) -> None:
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = HISTORY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(HISTORY_FILE)


def _load_backtest_results() -> dict:
    if BACKTEST_RESULTS_FILE.exists():
        try:
            return json.loads(BACKTEST_RESULTS_FILE.read_text())
        except (json.JSONDecodeError, ValueError):
            pass
    return {}


def _save_backtest_results(data: dict) -> None:
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = BACKTEST_RESULTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(BACKTEST_RESULTS_FILE)


# ── A. Forecast Accuracy Tracking ────────────────────────────────────────────

def fetch_actual_weather(lat: float, lon: float, date: str) -> Optional[dict]:
    """Fetch actual observed weather for a past date from Open-Meteo Historical API."""
    try:
        resp = requests.get(
            OPEN_METEO_HISTORICAL_API,
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": date,
                "end_date": date,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
                "temperature_unit": "fahrenheit",
                "precipitation_unit": "inch",
                "timezone": "auto",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        if date not in dates:
            return None
        idx = dates.index(date)
        return {
            "temp_max": _safe_float(daily.get("temperature_2m_max", []), idx),
            "temp_min": _safe_float(daily.get("temperature_2m_min", []), idx),
            "precip_sum": _safe_float(daily.get("precipitation_sum", []), idx),
            "weather_code": _safe_int(daily.get("weather_code", []), idx),
        }
    except requests.RequestException as e:
        log.warning("Historical weather fetch failed for %s: %s", date, e)
        return None


def fetch_past_forecast(lat: float, lon: float, target_date: str, days_before: int = 3) -> Optional[dict]:
    """
    Fetch what GFS/ECMWF predicted for a given date, using the Previous Runs API.
    Gets the forecast made 'days_before' days before the target date.
    """
    forecast_date = (datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=days_before)).strftime("%Y-%m-%d")

    result = {"gfs": None, "ecmwf": None}

    for model in ["gfs_seamless", "ecmwf_ifs025"]:
        model_key = "gfs" if "gfs" in model else "ecmwf"
        try:
            resp = requests.get(
                OPEN_METEO_PREVIOUS_RUNS_API,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "start_date": target_date,
                    "end_date": target_date,
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
                    "models": model,
                    "temperature_unit": "fahrenheit",
                    "precipitation_unit": "inch",
                    "past_days": days_before + 1,
                    "timezone": "auto",
                },
                timeout=15,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            daily = data.get("daily", {})
            dates = daily.get("time", [])
            if target_date in dates:
                idx = dates.index(target_date)
                result[model_key] = {
                    "temp_max": _safe_float(daily.get("temperature_2m_max", []), idx),
                    "temp_min": _safe_float(daily.get("temperature_2m_min", []), idx),
                    "precip_sum": _safe_float(daily.get("precipitation_sum", []), idx),
                }
        except requests.RequestException:
            continue

    if result["gfs"] is None and result["ecmwf"] is None:
        return None
    return result


def track_forecast_accuracy(history: dict) -> dict:
    """
    For resolved weather trades, compare forecasts vs actual outcomes.
    Updates model accuracy scores per city.
    """
    # Load all weather trade files
    from bot_engine import load_trades

    trade_files = [
        ("weather_temperature_trades.json", "weather_temperature_trades.backup.json"),
        ("weather_precipitation_trades.json", "weather_precipitation_trades.backup.json"),
        ("weather_storm_trades.json", "weather_storm_trades.backup.json"),
        ("weather_divergence_trades.json", "weather_divergence_trades.backup.json"),
    ]

    records = history.get("accuracy_records", [])
    tracked_ids = {r["market_id"] for r in records}

    new_records = 0
    for tf, bf in trade_files:
        trades = load_trades(tf, bf)
        for t in trades:
            if t["status"] != "closed":
                continue
            if t["market_id"] in tracked_ids:
                continue
            city = t.get("city")
            if not city or city not in CITY_COORDS:
                continue
            forecast_date = t.get("forecast_date")
            if not forecast_date:
                continue

            # Check if the forecast date has passed
            now = datetime.now(timezone.utc)
            try:
                target = datetime.strptime(forecast_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if target > now:
                    continue  # Not yet resolved
            except ValueError:
                continue

            lat, lon = CITY_COORDS[city]

            # Fetch actual weather
            actual = fetch_actual_weather(lat, lon, forecast_date)
            if not actual:
                continue

            record = {
                "market_id": t["market_id"],
                "city": city,
                "date": forecast_date,
                "weather_type": t.get("weather_type", "temperature"),
                "gfs_forecast": t.get("gfs_forecast"),
                "ecmwf_forecast": t.get("ecmwf_forecast"),
                "actual_temp_max": actual.get("temp_max"),
                "actual_precip": actual.get("precip_sum"),
                "gfs_error": None,
                "ecmwf_error": None,
                "trade_direction": t["direction"],
                "trade_pnl": t.get("pnl_pp", 0),
                "exit_reason": t.get("exit_reason"),
            }

            # Calculate errors
            if t.get("weather_type") == "temperature":
                actual_val = actual.get("temp_max")
                if actual_val is not None:
                    if t.get("gfs_forecast") is not None:
                        record["gfs_error"] = round(abs(t["gfs_forecast"] - actual_val), 1)
                    if t.get("ecmwf_forecast") is not None:
                        record["ecmwf_error"] = round(abs(t["ecmwf_forecast"] - actual_val), 1)
            elif t.get("weather_type") == "precipitation":
                actual_val = actual.get("precip_sum")
                if actual_val is not None:
                    if t.get("gfs_forecast") is not None:
                        record["gfs_error"] = round(abs(t["gfs_forecast"] - actual_val), 2)
                    if t.get("ecmwf_forecast") is not None:
                        record["ecmwf_error"] = round(abs(t["ecmwf_forecast"] - actual_val), 2)

            records.append(record)
            tracked_ids.add(t["market_id"])
            new_records += 1

    history["accuracy_records"] = records

    # Compute rolling accuracy per city per model
    city_errors = {}
    for r in records:
        city = r["city"]
        if city not in city_errors:
            city_errors[city] = {"gfs_errors": [], "ecmwf_errors": []}
        if r.get("gfs_error") is not None:
            city_errors[city]["gfs_errors"].append(r["gfs_error"])
        if r.get("ecmwf_error") is not None:
            city_errors[city]["ecmwf_errors"].append(r["ecmwf_error"])

    model_accuracy = {}
    for city, errors in city_errors.items():
        entry = {}
        if errors["gfs_errors"]:
            entry["gfs_avg_error"] = round(sum(errors["gfs_errors"]) / len(errors["gfs_errors"]), 2)
            entry["gfs_sample_size"] = len(errors["gfs_errors"])
        if errors["ecmwf_errors"]:
            entry["ecmwf_avg_error"] = round(sum(errors["ecmwf_errors"]) / len(errors["ecmwf_errors"]), 2)
            entry["ecmwf_sample_size"] = len(errors["ecmwf_errors"])
        if entry:
            model_accuracy[city] = entry

    history["model_accuracy"] = model_accuracy
    log.info("Accuracy tracking: %d new records, %d total, %d cities tracked", new_records, len(records), len(model_accuracy))
    return history


# ── B. Market Pattern Analysis ───────────────────────────────────────────────

def analyze_market_patterns(history: dict) -> dict:
    """Analyze resolved Polymarket weather markets to find profitable patterns."""
    records = history.get("accuracy_records", [])
    if not records:
        log.info("No accuracy records to analyze for patterns")
        return history

    patterns = {
        "by_weather_type": {},
        "by_city": {},
        "by_season": {},
        "by_direction": {},
        "overall": {},
    }

    # Aggregate by weather type
    type_pnls = {}
    for r in records:
        wtype = r.get("weather_type", "unknown")
        if wtype not in type_pnls:
            type_pnls[wtype] = {"pnls": [], "wins": 0, "total": 0}
        pnl = r.get("trade_pnl", 0)
        type_pnls[wtype]["pnls"].append(pnl)
        type_pnls[wtype]["total"] += 1
        if pnl > 0:
            type_pnls[wtype]["wins"] += 1

    for wtype, data in type_pnls.items():
        pnls = data["pnls"]
        patterns["by_weather_type"][wtype] = {
            "total_trades": data["total"],
            "win_rate": round(data["wins"] / data["total"] * 100, 1) if data["total"] else 0,
            "total_pnl": round(sum(pnls), 1),
            "avg_pnl": round(sum(pnls) / len(pnls), 1) if pnls else 0,
        }

    # Aggregate by city
    city_pnls = {}
    for r in records:
        city = r.get("city", "unknown")
        if city not in city_pnls:
            city_pnls[city] = {"pnls": [], "wins": 0, "total": 0}
        pnl = r.get("trade_pnl", 0)
        city_pnls[city]["pnls"].append(pnl)
        city_pnls[city]["total"] += 1
        if pnl > 0:
            city_pnls[city]["wins"] += 1

    for city, data in city_pnls.items():
        pnls = data["pnls"]
        patterns["by_city"][city] = {
            "total_trades": data["total"],
            "win_rate": round(data["wins"] / data["total"] * 100, 1) if data["total"] else 0,
            "total_pnl": round(sum(pnls), 1),
            "avg_pnl": round(sum(pnls) / len(pnls), 1) if pnls else 0,
        }

    # Aggregate by season
    season_pnls = {}
    for r in records:
        date_str = r.get("date", "")
        try:
            month = int(date_str.split("-")[1])
            if month in (12, 1, 2):
                season = "winter"
            elif month in (3, 4, 5):
                season = "spring"
            elif month in (6, 7, 8):
                season = "summer"
            else:
                season = "fall"
        except (IndexError, ValueError):
            season = "unknown"

        if season not in season_pnls:
            season_pnls[season] = {"pnls": [], "wins": 0, "total": 0}
        pnl = r.get("trade_pnl", 0)
        season_pnls[season]["pnls"].append(pnl)
        season_pnls[season]["total"] += 1
        if pnl > 0:
            season_pnls[season]["wins"] += 1

    for season, data in season_pnls.items():
        pnls = data["pnls"]
        patterns["by_season"][season] = {
            "total_trades": data["total"],
            "win_rate": round(data["wins"] / data["total"] * 100, 1) if data["total"] else 0,
            "total_pnl": round(sum(pnls), 1),
        }

    # Overall stats
    all_pnls = [r.get("trade_pnl", 0) for r in records]
    wins = sum(1 for p in all_pnls if p > 0)
    patterns["overall"] = {
        "total_trades": len(all_pnls),
        "win_rate": round(wins / len(all_pnls) * 100, 1) if all_pnls else 0,
        "total_pnl": round(sum(all_pnls), 1),
        "avg_pnl": round(sum(all_pnls) / len(all_pnls), 1) if all_pnls else 0,
        "best_trade": round(max(all_pnls), 1) if all_pnls else 0,
        "worst_trade": round(min(all_pnls), 1) if all_pnls else 0,
    }

    history["patterns"] = patterns
    log.info("Pattern analysis: %d records analyzed", len(records))
    return history


# ── C. Backtest Engine ───────────────────────────────────────────────────────

def fetch_resolved_weather_markets(days_back: int = BACKTEST_DEFAULT_DAYS) -> list[dict]:
    """Fetch resolved weather markets from Polymarket."""
    markets = []
    try:
        resp = requests.get(
            f"{POLYMARKET_GAMMA_API}/markets",
            params={
                "tag": "weather",
                "closed": "true",
                "limit": 200,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            all_markets = resp.json()
            cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

            for m in all_markets:
                end_date_str = m.get("end_date_iso") or m.get("endDate") or m.get("end_date", "")
                if end_date_str:
                    try:
                        end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                        if end_date < cutoff:
                            continue
                    except (ValueError, TypeError):
                        continue

                markets.append(m)

    except requests.RequestException as e:
        log.warning("Failed to fetch resolved markets: %s", e)

    # Fallback: keyword search
    if not markets:
        try:
            resp = requests.get(
                f"{POLYMARKET_GAMMA_API}/markets",
                params={"closed": "true", "limit": 200},
                timeout=30,
            )
            if resp.status_code == 200:
                for m in resp.json():
                    q = (m.get("question", "") + " " + m.get("description", "")).lower()
                    from weather_config import WEATHER_KEYWORDS
                    if any(kw in q for kw in WEATHER_KEYWORDS):
                        markets.append(m)
        except requests.RequestException:
            pass

    log.info("Fetched %d resolved weather markets for backtesting", len(markets))
    return markets


def run_backtest(days_back: int = BACKTEST_DEFAULT_DAYS) -> dict:
    """
    Replay historical weather forecasts against past Polymarket prices.
    Simulates the trading strategy and returns performance metrics.
    """
    log.info("Running backtest over last %d days", days_back)

    resolved_markets = fetch_resolved_weather_markets(days_back)
    if not resolved_markets:
        log.warning("No resolved markets found for backtest")
        return {"error": "no_markets_found"}

    # Simulate trading
    balance = BACKTEST_STARTING_BALANCE
    trades = []
    wins = 0
    losses = 0

    for market in resolved_markets:
        question = market.get("question", "")
        parsed = parse_weather_market(question)
        if not parsed:
            continue
        if parsed["market_type"] not in ("temperature", "precipitation"):
            continue
        if not parsed.get("city") or parsed["city"] not in CITY_COORDS:
            continue
        if not parsed.get("date") or not parsed.get("threshold"):
            continue

        lat, lon = CITY_COORDS[parsed["city"]]
        forecast_date = parsed["date"]

        # Fetch what the models predicted
        past_forecast = fetch_past_forecast(lat, lon, forecast_date, days_before=3)
        if not past_forecast:
            continue

        # Fetch actual outcome
        actual = fetch_actual_weather(lat, lon, forecast_date)
        if not actual:
            continue

        # Convert threshold
        threshold = parsed["threshold"]
        if parsed.get("threshold_unit") == "C":
            threshold = threshold * 9 / 5 + 32

        # Calculate what our model probability would have been
        from weather_engine import estimate_weather_probability
        model_prob = estimate_weather_probability(
            past_forecast, threshold, 3.0,
            direction=parsed.get("direction", "above"),
            weather_type=parsed["market_type"],
        )
        if model_prob is None:
            continue

        # Get the market price (use YES price from tokens)
        tokens = market.get("tokens", [])
        market_price = None
        for tok in tokens:
            if tok.get("outcome", "").upper() == "YES":
                market_price = float(tok.get("price", 0))
                break
        if market_price is None:
            market_price = market.get("outcomePrices", {}).get("Yes")
            if market_price is not None:
                market_price = float(market_price)
        if market_price is None or market_price <= 0:
            continue

        # Determine minimum edge based on type
        min_edge = MIN_EDGE_TEMPERATURE if parsed["market_type"] == "temperature" else MIN_EDGE_PRECIPITATION

        # Check for edge
        edge_result = compute_weather_edge(model_prob, market_price, min_edge)
        if not edge_result:
            continue

        # Simulate trade
        stake = balance * BACKTEST_BASE_STAKE_PCT
        direction = edge_result["direction"]

        # Determine actual outcome
        if parsed["market_type"] == "temperature":
            actual_val = actual.get("temp_max")
            if actual_val is None:
                continue
            if parsed.get("direction", "above") == "above":
                resolved_yes = actual_val > threshold
            else:
                resolved_yes = actual_val < threshold
        else:
            actual_val = actual.get("precip_sum")
            if actual_val is None:
                continue
            resolved_yes = actual_val > (threshold if threshold else 0)

        # P&L calculation (Polymarket style: pay $1 if correct, $0 if wrong)
        if direction == "BUY YES":
            if resolved_yes:
                pnl_pct = (1.0 - market_price) / market_price * 100  # profit per share
                pnl = stake * (1.0 - market_price)
                wins += 1
            else:
                pnl_pct = -100.0
                pnl = -stake * market_price
                losses += 1
        else:  # BUY NO
            if not resolved_yes:
                pnl_pct = (1.0 - (1.0 - market_price)) / (1.0 - market_price) * 100
                pnl = stake * market_price
                wins += 1
            else:
                pnl_pct = -100.0
                pnl = -stake * (1.0 - market_price)
                losses += 1

        balance += pnl

        trades.append({
            "market": question[:80],
            "city": parsed["city"],
            "date": forecast_date,
            "weather_type": parsed["market_type"],
            "direction": direction,
            "market_price": round(market_price, 3),
            "model_prob": round(model_prob, 3),
            "edge": round(edge_result["edge"], 3),
            "actual_value": actual_val,
            "threshold": threshold,
            "resolved_yes": resolved_yes,
            "pnl_usd": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 1),
            "balance_after": round(balance, 2),
        })

        # Rate limit protection
        time.sleep(0.2)

    # Calculate results
    total = wins + losses
    pnls = [t["pnl_usd"] for t in trades]

    # Max drawdown
    peak = BACKTEST_STARTING_BALANCE
    max_dd = 0
    for t in trades:
        bal = t["balance_after"]
        if bal > peak:
            peak = bal
        dd = (peak - bal) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Sharpe-like ratio (simplified)
    if len(pnls) > 1:
        avg_pnl = sum(pnls) / len(pnls)
        std_pnl = math.sqrt(sum((p - avg_pnl) ** 2 for p in pnls) / (len(pnls) - 1))
        sharpe = (avg_pnl / std_pnl * math.sqrt(252)) if std_pnl > 0 else 0
    else:
        sharpe = 0

    # Breakdown by type
    type_breakdown = {}
    for t in trades:
        wt = t["weather_type"]
        if wt not in type_breakdown:
            type_breakdown[wt] = {"wins": 0, "losses": 0, "pnl": 0}
        if t["pnl_usd"] > 0:
            type_breakdown[wt]["wins"] += 1
        else:
            type_breakdown[wt]["losses"] += 1
        type_breakdown[wt]["pnl"] += t["pnl_usd"]

    for wt in type_breakdown:
        total_wt = type_breakdown[wt]["wins"] + type_breakdown[wt]["losses"]
        type_breakdown[wt]["win_rate"] = round(type_breakdown[wt]["wins"] / total_wt * 100, 1) if total_wt else 0
        type_breakdown[wt]["pnl"] = round(type_breakdown[wt]["pnl"], 2)

    # City breakdown
    city_breakdown = {}
    for t in trades:
        city = t["city"]
        if city not in city_breakdown:
            city_breakdown[city] = {"wins": 0, "losses": 0, "pnl": 0}
        if t["pnl_usd"] > 0:
            city_breakdown[city]["wins"] += 1
        else:
            city_breakdown[city]["losses"] += 1
        city_breakdown[city]["pnl"] += t["pnl_usd"]

    for city in city_breakdown:
        total_c = city_breakdown[city]["wins"] + city_breakdown[city]["losses"]
        city_breakdown[city]["win_rate"] = round(city_breakdown[city]["wins"] / total_c * 100, 1) if total_c else 0
        city_breakdown[city]["pnl"] = round(city_breakdown[city]["pnl"], 2)

    results = {
        "period_days": days_back,
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / total * 100, 1) if total else 0,
        "starting_balance": BACKTEST_STARTING_BALANCE,
        "ending_balance": round(balance, 2),
        "total_pnl": round(balance - BACKTEST_STARTING_BALANCE, 2),
        "total_return_pct": round((balance - BACKTEST_STARTING_BALANCE) / BACKTEST_STARTING_BALANCE * 100, 1),
        "max_drawdown_pct": round(max_dd, 1),
        "sharpe_ratio": round(sharpe, 2),
        "avg_edge": round(sum(t["edge"] for t in trades) / len(trades), 3) if trades else 0,
        "by_weather_type": type_breakdown,
        "by_city": city_breakdown,
        "trades": trades[-50:],  # Keep last 50 for dashboard display
    }

    log.info(
        "Backtest complete: %d trades, %.1f%% win rate, $%.2f P&L (%.1f%% return), max DD %.1f%%",
        total, results["win_rate"], results["total_pnl"],
        results["total_return_pct"], results["max_drawdown_pct"],
    )

    return results


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_float(arr: list, idx: int) -> Optional[float]:
    try:
        val = arr[idx]
        return float(val) if val is not None else None
    except (IndexError, TypeError, ValueError):
        return None


def _safe_int(arr: list, idx: int) -> Optional[int]:
    try:
        val = arr[idx]
        return int(val) if val is not None else None
    except (IndexError, TypeError, ValueError):
        return None


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("   WEATHER BACKTEST ENGINE")
    print("=" * 60)

    args = sys.argv[1:]
    days = BACKTEST_DEFAULT_DAYS
    run_accuracy = True
    run_patterns = True
    run_bt = True

    for i, arg in enumerate(args):
        if arg == "--days" and i + 1 < len(args):
            days = int(args[i + 1])
        elif arg == "--accuracy":
            run_patterns = False
            run_bt = False
        elif arg == "--patterns":
            run_accuracy = False
            run_bt = False

    history = _load_history()

    # A. Forecast Accuracy
    if run_accuracy:
        print("\n--- FORECAST ACCURACY TRACKING ---\n")
        history = track_forecast_accuracy(history)

    # B. Pattern Analysis
    if run_patterns:
        print("\n--- MARKET PATTERN ANALYSIS ---\n")
        history = analyze_market_patterns(history)

    _save_history(history)

    # C. Backtest
    if run_bt:
        print(f"\n--- BACKTEST (last {days} days) ---\n")
        results = run_backtest(days)
        _save_backtest_results(results)

        if "error" not in results:
            print(f"\n  Trades:     {results['total_trades']}")
            print(f"  Win Rate:   {results['win_rate']}%")
            print(f"  Total P&L:  ${results['total_pnl']:.2f}")
            print(f"  Return:     {results['total_return_pct']}%")
            print(f"  Max DD:     {results['max_drawdown_pct']}%")
            print(f"  Sharpe:     {results['sharpe_ratio']}")

    print(f"\n{'=' * 60}")
    print("   BACKTEST ENGINE COMPLETE")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
