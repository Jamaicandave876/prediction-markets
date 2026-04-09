"""
Weather Engine — shared library for all weather prediction market bots.

Handles:
  - Polymarket weather market scanning and pricing
  - Open-Meteo weather forecast fetching (GFS + ECMWF)
  - Market question parsing (extract city, date, threshold)
  - Probability estimation (forecast → probability)
  - Signal generation (model probability vs market price)
  - Forecast caching (6-hour TTL)
"""

from __future__ import annotations

import json
import re
import logging
import time
import math
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from weather_config import (
    POLYMARKET_GAMMA_API, POLYMARKET_CLOB_API,
    OPEN_METEO_FORECAST_API, NWS_ALERTS_API,
    FORECAST_CACHE_TTL, WEATHER_KEYWORDS,
    CITY_COORDS, CITY_ALIASES,
    TEMP_BASE_UNCERTAINTY_F, PRECIP_BASE_UNCERTAINTY_MM,
    UNCERTAINTY_GROWTH_RATE,
    MODEL_WEIGHT_GFS, MODEL_WEIGHT_ECMWF,
    WEATHER_MARKETS_TO_SCAN, MIN_MARKET_VOLUME,
    MIN_DAYS_TO_RESOLUTION, MAX_DAYS_TO_RESOLUTION,
)

log = logging.getLogger("weather_engine")

CACHE_FILE = Path("weather_forecasts_cache.json")
MARKET_MAP_FILE = Path("weather_market_map.json")


# ── Forecast Cache ───────────────────────────────────────────────────────────

def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except (json.JSONDecodeError, ValueError):
            pass
    return {}


def _save_cache(cache: dict) -> None:
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, indent=2))
    tmp.replace(CACHE_FILE)


def _cache_key(lat: float, lon: float, date: str) -> str:
    return f"{lat:.2f}_{lon:.2f}_{date}"


def _is_cache_valid(entry: dict) -> bool:
    cached_at = entry.get("cached_at", 0)
    return (time.time() - cached_at) < FORECAST_CACHE_TTL


# ── Polymarket Market Scanner ────────────────────────────────────────────────

def scan_polymarket_weather_markets(max_markets: int = WEATHER_MARKETS_TO_SCAN) -> list[dict]:
    """Scan Polymarket for active weather prediction markets."""
    markets = []

    for keyword in WEATHER_KEYWORDS[:8]:  # Use top keywords to avoid rate limits
        try:
            resp = requests.get(
                f"{POLYMARKET_GAMMA_API}/markets",
                params={
                    "tag": "weather",
                    "active": "true",
                    "closed": "false",
                    "limit": 50,
                },
                timeout=15,
            )
            if resp.status_code != 200:
                # Try keyword search as fallback
                resp = requests.get(
                    f"{POLYMARKET_GAMMA_API}/markets",
                    params={
                        "active": "true",
                        "closed": "false",
                        "limit": 50,
                        "tag_slug": "weather",
                    },
                    timeout=15,
                )
            if resp.status_code == 200:
                for m in resp.json():
                    markets.append(m)
                break  # Got results from tag search
        except requests.RequestException as e:
            log.warning("Polymarket scan failed for keyword '%s': %s", keyword, e)
            continue

    # Fallback: search by keywords in question text
    if not markets:
        for keyword in WEATHER_KEYWORDS[:5]:
            try:
                resp = requests.get(
                    f"{POLYMARKET_GAMMA_API}/markets",
                    params={
                        "active": "true",
                        "closed": "false",
                        "limit": 30,
                    },
                    timeout=15,
                )
                if resp.status_code == 200:
                    for m in resp.json():
                        q = (m.get("question", "") + " " + m.get("description", "")).lower()
                        if any(kw in q for kw in WEATHER_KEYWORDS):
                            markets.append(m)
            except requests.RequestException:
                continue

    # Deduplicate by condition_id
    seen = set()
    unique = []
    for m in markets:
        cid = m.get("condition_id") or m.get("id", "")
        if cid and cid not in seen:
            seen.add(cid)
            unique.append(m)

    # Filter by volume and resolution time
    now = datetime.now(timezone.utc)
    filtered = []
    for m in unique:
        volume = m.get("volume", 0) or m.get("volumeNum", 0) or 0
        try:
            volume = float(volume)
        except (ValueError, TypeError):
            volume = 0

        if volume < MIN_MARKET_VOLUME:
            continue

        end_date_str = m.get("end_date_iso") or m.get("endDate") or m.get("end_date", "")
        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                days_to_end = (end_date - now).total_seconds() / 86400
                if days_to_end < MIN_DAYS_TO_RESOLUTION:
                    continue
                if days_to_end > MAX_DAYS_TO_RESOLUTION:
                    continue
            except (ValueError, TypeError):
                pass

        # Normalize market dict
        tokens = m.get("tokens", [])
        yes_price = None
        no_price = None
        yes_token_id = None
        no_token_id = None

        for tok in tokens:
            outcome = tok.get("outcome", "").upper()
            price = tok.get("price")
            token_id = tok.get("token_id")
            if outcome == "YES":
                yes_price = float(price) if price else None
                yes_token_id = token_id
            elif outcome == "NO":
                no_price = float(price) if price else None
                no_token_id = token_id

        # Try top-level price fields
        if yes_price is None:
            yes_price = m.get("outcomePrices", {}).get("Yes") or m.get("yes_price")
            if yes_price is not None:
                yes_price = float(yes_price)
        if no_price is None:
            no_price = m.get("outcomePrices", {}).get("No") or m.get("no_price")
            if no_price is not None:
                no_price = float(no_price)

        if yes_price is None:
            continue

        if no_price is None and yes_price is not None:
            no_price = round(1.0 - yes_price, 4)

        filtered.append({
            "condition_id": m.get("condition_id") or m.get("id", ""),
            "question": m.get("question", ""),
            "description": m.get("description", ""),
            "slug": m.get("slug", ""),
            "end_date": end_date_str,
            "yes_price": yes_price,
            "no_price": no_price,
            "yes_token_id": yes_token_id,
            "no_token_id": no_token_id,
            "volume": volume,
            "url": f"https://polymarket.com/event/{m.get('slug', '')}",
        })

        if len(filtered) >= max_markets:
            break

    log.info("Scanned %d weather markets from Polymarket (%d after filtering)", len(unique), len(filtered))
    return filtered


def get_polymarket_price(condition_id: str, yes_token_id: str = None) -> dict:
    """Get current price for a Polymarket market."""
    try:
        if yes_token_id:
            resp = requests.get(
                f"{POLYMARKET_CLOB_API}/price",
                params={"token_id": yes_token_id, "side": "buy"},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                price = float(data.get("price", 0))
                return {"status": "active", "probability": round(price * 100, 1)}

        # Fallback: use gamma API
        resp = requests.get(
            f"{POLYMARKET_GAMMA_API}/markets/{condition_id}",
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("closed") or data.get("resolved"):
                resolution = "YES" if data.get("resolutionSource") == "Yes" else "NO"
                return {"status": "resolved", "resolution": resolution}
            tokens = data.get("tokens", [])
            for tok in tokens:
                if tok.get("outcome", "").upper() == "YES":
                    price = float(tok.get("price", 0))
                    return {"status": "active", "probability": round(price * 100, 1)}

        return {"status": "error", "reason": "no_price_data"}

    except requests.exceptions.Timeout:
        return {"status": "error", "reason": "timeout"}
    except requests.exceptions.ConnectionError:
        return {"status": "error", "reason": "connection_failed"}
    except Exception as e:
        return {"status": "error", "reason": str(e)[:100]}


# ── Market Question Parser ───────────────────────────────────────────────────

# Month name mapping
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
}


def _resolve_city(city_text: str) -> Optional[str]:
    """Resolve a city name from market text to a canonical city name."""
    city_lower = city_text.strip().lower()

    # Direct alias match
    if city_lower in CITY_ALIASES:
        return CITY_ALIASES[city_lower]

    # Direct match in CITY_COORDS
    for canonical in CITY_COORDS:
        if canonical.lower() == city_lower:
            return canonical

    # Partial match
    for canonical in CITY_COORDS:
        if city_lower in canonical.lower() or canonical.lower() in city_lower:
            return canonical

    return None


def _parse_date(date_text: str) -> Optional[str]:
    """Parse a date string from market question. Returns YYYY-MM-DD or None."""
    now = datetime.now(timezone.utc)

    # Pattern: "April 15" or "April 15, 2026"
    m = re.search(
        r'(\w+)\s+(\d{1,2})(?:\s*,?\s*(\d{4}))?',
        date_text
    )
    if m:
        month_name = m.group(1).lower()
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        month = MONTHS.get(month_name)
        if month and 1 <= day <= 31:
            try:
                d = datetime(year, month, day)
                return d.strftime("%Y-%m-%d")
            except ValueError:
                pass

    # Pattern: "4/15" or "4/15/2026"
    m = re.search(r'(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?', date_text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        if year < 100:
            year += 2000
        if 1 <= month <= 12 and 1 <= day <= 31:
            try:
                d = datetime(year, month, day)
                return d.strftime("%Y-%m-%d")
            except ValueError:
                pass

    return None


def parse_weather_market(question: str) -> Optional[dict]:
    """
    Parse a Polymarket weather market question to extract structured parameters.
    Returns None if not a recognized weather market pattern.
    """
    q = question.strip()
    q_lower = q.lower()

    result = {
        "market_type": None,
        "city": None,
        "date": None,
        "threshold": None,
        "threshold_unit": "F",
        "direction": "above",  # above/below
        "precip_type": None,
        "storm_category": None,
    }

    # ── Temperature patterns ─────────────────────────────────────────────
    temp_patterns = [
        # "highest temperature in Hong Kong on April 8"
        r'(?:highest|high)\s+temperature\s+in\s+(.+?)\s+(?:on|for)\s+(.+?)(?:\?|$)',
        # "Will the high in NYC exceed 80F on April 15?"
        r'(?:high|temperature|temp)\s+in\s+(.+?)\s+(?:exceed|above|over|be above|surpass|reach)\s+(\d+)\s*[°]?\s*([FC])',
        # "temperature in {CITY} exceed/above/over {N}F on {DATE}"
        r'temperature\s+in\s+(.+?)\s+(?:exceed|above|over)\s+(\d+)\s*[°]?\s*([FC])\s+(?:on|for)\s+(.+?)(?:\?|$)',
        # "Will {CITY} high exceed {N} degrees on {DATE}"
        r'(.+?)\s+(?:high|temperature|temp)\s+(?:exceed|above|over)\s+(\d+)\s*(?:degrees|°)\s*([FC]?)',
        # "{CITY} temperature below/under {N}F"
        r'temperature\s+in\s+(.+?)\s+(?:below|under|fall below|drop below)\s+(\d+)\s*[°]?\s*([FC])',
        # "daily high in {CITY} be {N}+ degrees"
        r'daily\s+high\s+in\s+(.+?)\s+(?:be|reach|hit)\s+(\d+)\+?\s*(?:degrees|°)\s*([FC]?)',
    ]

    for pattern in temp_patterns:
        m = re.search(pattern, q_lower)
        if m:
            groups = m.groups()
            result["market_type"] = "temperature"

            # Extract city
            city_text = groups[0] if groups else None
            if city_text:
                result["city"] = _resolve_city(city_text)

            # Extract threshold
            for g in groups[1:]:
                if g and g.isdigit():
                    result["threshold"] = int(g)
                    break

            # Extract unit
            for g in groups:
                if g and g.upper() in ("F", "C"):
                    result["threshold_unit"] = g.upper()

            # Extract date from remaining text
            for g in groups:
                if g and not g.isdigit() and g.upper() not in ("F", "C"):
                    parsed_date = _parse_date(g)
                    if parsed_date:
                        result["date"] = parsed_date

            # Direction
            if any(w in q_lower for w in ["below", "under", "drop below", "fall below"]):
                result["direction"] = "below"

            if result["city"]:
                break

    # ── Fallback: scan for city names and numbers in the question ────────
    if not result["market_type"]:
        # Check if this is a temperature question at all
        if any(w in q_lower for w in ["temperature", "temp", "degrees", "°f", "°c", "high of", "low of"]):
            result["market_type"] = "temperature"

            # Find city
            for canonical in sorted(CITY_COORDS.keys(), key=len, reverse=True):
                if canonical.lower() in q_lower:
                    result["city"] = canonical
                    break
            if not result["city"]:
                for alias, canonical in CITY_ALIASES.items():
                    if alias in q_lower:
                        result["city"] = canonical
                        break

            # Find threshold number
            nums = re.findall(r'(\d+)\s*(?:°|degrees|[FC])', q)
            if nums:
                result["threshold"] = int(nums[0])

            # Find date
            date_match = _parse_date(q)
            if date_match:
                result["date"] = date_match

            # Unit detection
            if "celsius" in q_lower or "°c" in q_lower:
                result["threshold_unit"] = "C"

            # Direction
            if any(w in q_lower for w in ["below", "under", "drop", "fall"]):
                result["direction"] = "below"

    # ── Precipitation patterns ───────────────────────────────────────────
    if not result["market_type"]:
        if any(w in q_lower for w in ["rain", "snow", "precipitation", "inches", "flooding"]):
            result["market_type"] = "precipitation"

            # City
            for canonical in sorted(CITY_COORDS.keys(), key=len, reverse=True):
                if canonical.lower() in q_lower:
                    result["city"] = canonical
                    break
            if not result["city"]:
                for alias, canonical in CITY_ALIASES.items():
                    if alias in q_lower:
                        result["city"] = canonical
                        break

            # Precip type
            if "snow" in q_lower:
                result["precip_type"] = "snow"
            elif "rain" in q_lower:
                result["precip_type"] = "rain"
            else:
                result["precip_type"] = "any"

            # Threshold (inches)
            nums = re.findall(r'(\d+\.?\d*)\s*(?:inches|inch|in|")', q_lower)
            if nums:
                result["threshold"] = float(nums[0])
                result["threshold_unit"] = "in"

            # Date
            date_match = _parse_date(q)
            if date_match:
                result["date"] = date_match

    # ── Storm patterns ───────────────────────────────────────────────────
    if not result["market_type"]:
        if any(w in q_lower for w in ["hurricane", "tropical storm", "cyclone", "tornado", "category"]):
            result["market_type"] = "storm"

            # Storm category
            cat_match = re.search(r'category\s+(\d+)', q_lower)
            if cat_match:
                result["storm_category"] = int(cat_match.group(1))

            # Date
            date_match = _parse_date(q)
            if date_match:
                result["date"] = date_match

    if not result["market_type"]:
        return None

    return result


# ── Open-Meteo Weather Forecast Fetcher ──────────────────────────────────────

def fetch_forecast(lat: float, lon: float, target_date: str) -> Optional[dict]:
    """
    Fetch GFS and ECMWF weather forecasts for a location/date.
    Uses cache with 6-hour TTL.
    Returns dict with 'gfs' and 'ecmwf' sub-dicts containing forecast values.
    """
    cache = _load_cache()
    key = _cache_key(lat, lon, target_date)

    if key in cache and _is_cache_valid(cache[key]):
        return cache[key].get("data")

    try:
        # Fetch GFS forecast
        gfs_resp = requests.get(
            OPEN_METEO_FORECAST_API,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code",
                "models": "gfs_seamless",
                "forecast_days": 16,
                "temperature_unit": "fahrenheit",
                "precipitation_unit": "inch",
                "timezone": "auto",
            },
            timeout=15,
        )
        gfs_resp.raise_for_status()
        gfs_data = gfs_resp.json()

        # Fetch ECMWF forecast
        ecmwf_resp = requests.get(
            OPEN_METEO_FORECAST_API,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code",
                "models": "ecmwf_ifs025",
                "forecast_days": 16,
                "temperature_unit": "fahrenheit",
                "precipitation_unit": "inch",
                "timezone": "auto",
            },
            timeout=15,
        )
        ecmwf_resp.raise_for_status()
        ecmwf_data = ecmwf_resp.json()

    except requests.RequestException as e:
        log.warning("Open-Meteo fetch failed for (%.2f, %.2f): %s", lat, lon, e)
        return None

    # Find target date in forecast arrays
    result = {"gfs": None, "ecmwf": None}

    for model_name, model_data in [("gfs", gfs_data), ("ecmwf", ecmwf_data)]:
        daily = model_data.get("daily", {})
        dates = daily.get("time", [])

        try:
            idx = dates.index(target_date)
        except ValueError:
            log.debug("Target date %s not found in %s forecast for (%.2f, %.2f)", target_date, model_name, lat, lon)
            continue

        result[model_name] = {
            "temp_max": _safe_float(daily.get("temperature_2m_max", []), idx),
            "temp_min": _safe_float(daily.get("temperature_2m_min", []), idx),
            "precip_sum": _safe_float(daily.get("precipitation_sum", []), idx),
            "precip_probability": _safe_float(daily.get("precipitation_probability_max", []), idx),
            "weather_code": _safe_int(daily.get("weather_code", []), idx),
        }

    if result["gfs"] is None and result["ecmwf"] is None:
        return None

    # Cache the result
    cache[key] = {"data": result, "cached_at": time.time()}
    _save_cache(cache)

    return result


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


# ── Probability Estimation ───────────────────────────────────────────────────

def _normal_cdf(x: float) -> float:
    """Approximate standard normal CDF using error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def forecast_to_probability(
    forecast_value: float,
    threshold: float,
    days_out: float,
    direction: str = "above",
    base_uncertainty: float = TEMP_BASE_UNCERTAINTY_F,
) -> float:
    """
    Convert a weather forecast value to a probability of exceeding/falling-below a threshold.

    Uses normal distribution assumption:
    - Mean = forecast value
    - Std dev = base_uncertainty * sqrt(days_out / 1 + growth)
    """
    if days_out < 0.5:
        days_out = 0.5

    # Uncertainty grows with forecast horizon
    std_dev = base_uncertainty * math.sqrt(1.0 + UNCERTAINTY_GROWTH_RATE * (days_out - 1))
    std_dev = max(std_dev, 0.5)  # Minimum uncertainty

    # Z-score: how many std devs is threshold from forecast
    z = (threshold - forecast_value) / std_dev

    if direction == "above":
        # P(actual > threshold) = 1 - CDF(z)
        return round(1.0 - _normal_cdf(z), 4)
    else:
        # P(actual < threshold) = CDF(z)
        return round(_normal_cdf(z), 4)


def estimate_weather_probability(
    forecast: dict,
    threshold: float,
    days_out: float,
    direction: str = "above",
    weather_type: str = "temperature",
    model_weights: dict = None,
) -> Optional[float]:
    """
    Estimate probability from GFS + ECMWF forecasts, weighted by model trust.
    Returns probability between 0.0 and 1.0, or None if no data.
    """
    if model_weights is None:
        model_weights = {"gfs": MODEL_WEIGHT_GFS, "ecmwf": MODEL_WEIGHT_ECMWF}

    if weather_type == "temperature":
        base_unc = TEMP_BASE_UNCERTAINTY_F
        gfs_val = forecast.get("gfs", {}).get("temp_max") if forecast.get("gfs") else None
        ecmwf_val = forecast.get("ecmwf", {}).get("temp_max") if forecast.get("ecmwf") else None
    elif weather_type == "precipitation":
        base_unc = PRECIP_BASE_UNCERTAINTY_MM
        gfs_val = forecast.get("gfs", {}).get("precip_sum") if forecast.get("gfs") else None
        ecmwf_val = forecast.get("ecmwf", {}).get("precip_sum") if forecast.get("ecmwf") else None
    else:
        return None

    probs = []
    weights = []

    if gfs_val is not None:
        p = forecast_to_probability(gfs_val, threshold, days_out, direction, base_unc)
        probs.append(p)
        weights.append(model_weights.get("gfs", 0.5))

    if ecmwf_val is not None:
        p = forecast_to_probability(ecmwf_val, threshold, days_out, direction, base_unc)
        probs.append(p)
        weights.append(model_weights.get("ecmwf", 0.5))

    if not probs:
        return None

    # Weighted average
    total_weight = sum(weights)
    weighted_prob = sum(p * w for p, w in zip(probs, weights)) / total_weight

    return round(weighted_prob, 4)


# ── Signal Generation ────────────────────────────────────────────────────────

def compute_weather_edge(model_prob: float, market_price: float, min_edge: float) -> Optional[dict]:
    """
    Compare model probability vs market price.
    Returns signal dict if edge exceeds threshold, else None.
    """
    edge = model_prob - market_price  # positive = YES is underpriced

    if abs(edge) >= min_edge:
        direction = "BUY YES" if edge > 0 else "BUY NO"
        return {
            "direction": direction,
            "edge": round(abs(edge), 4),
            "model_prob": round(model_prob, 4),
            "market_price": round(market_price, 4),
        }
    return None


def generate_weather_signal(
    market: dict,
    parsed: dict,
    forecast: dict,
    min_edge: float,
    model_weights: dict = None,
) -> Optional[dict]:
    """
    Full signal generation pipeline for a single weather market.
    Combines parsing, forecasting, probability estimation, and edge detection.
    """
    city = parsed.get("city")
    if not city or city not in CITY_COORDS:
        return None

    threshold = parsed.get("threshold")
    if threshold is None:
        return None

    # Convert Celsius to Fahrenheit if needed
    if parsed.get("threshold_unit") == "C":
        threshold = threshold * 9 / 5 + 32

    # Calculate days to resolution
    target_date = parsed.get("date")
    if not target_date:
        return None

    now = datetime.now(timezone.utc)
    try:
        target = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        days_out = (target - now).total_seconds() / 86400
    except ValueError:
        return None

    if days_out < 0.5 or days_out > 16:
        return None

    # Estimate probability
    model_prob = estimate_weather_probability(
        forecast,
        threshold,
        days_out,
        direction=parsed.get("direction", "above"),
        weather_type=parsed.get("market_type", "temperature"),
        model_weights=model_weights,
    )

    if model_prob is None:
        return None

    # Market price is YES share price
    market_price = market.get("yes_price")
    if market_price is None:
        return None

    # Check for edge
    edge_result = compute_weather_edge(model_prob, market_price, min_edge)
    if not edge_result:
        return None

    # Build signal
    gfs_data = forecast.get("gfs", {}) or {}
    ecmwf_data = forecast.get("ecmwf", {}) or {}

    signal = {
        "market_id": market["condition_id"],
        "question": market["question"],
        "direction": edge_result["direction"],
        "entry_prob": round(market_price * 100, 1),
        "url": market.get("url", ""),
        "platform": "polymarket",
        "signal_strength": round(edge_result["edge"] * 10, 2),  # Normalize for position sizing

        # Weather metadata
        "weather_type": parsed["market_type"],
        "city": city,
        "forecast_date": target_date,
        "threshold": threshold,
        "threshold_unit": "F",
        "gfs_forecast": gfs_data.get("temp_max") if parsed["market_type"] == "temperature" else gfs_data.get("precip_sum"),
        "ecmwf_forecast": ecmwf_data.get("temp_max") if parsed["market_type"] == "temperature" else ecmwf_data.get("precip_sum"),
        "model_prob": edge_result["model_prob"],
        "market_price": edge_result["market_price"],
        "edge": edge_result["edge"],
        "days_to_resolution": round(days_out, 1),

        # Token IDs for exit checking
        "yes_token_id": market.get("yes_token_id"),
        "no_token_id": market.get("no_token_id"),
    }

    return signal


# ── NWS Alerts (for Storm Bot) ───────────────────────────────────────────────

def fetch_nws_alerts(severity: str = "Extreme,Severe") -> list[dict]:
    """Fetch active weather alerts from NWS."""
    try:
        resp = requests.get(
            NWS_ALERTS_API,
            params={"severity": severity},
            headers={"User-Agent": "WeatherPredictionBot/1.0"},
            timeout=15,
        )
        resp.raise_for_status()
        features = resp.json().get("features", [])
        alerts = []
        for f in features:
            props = f.get("properties", {})
            alerts.append({
                "event": props.get("event", ""),
                "severity": props.get("severity", ""),
                "headline": props.get("headline", ""),
                "description": props.get("description", "")[:200],
                "area": props.get("areaDesc", ""),
                "onset": props.get("onset"),
                "expires": props.get("expires"),
            })
        return alerts
    except requests.RequestException as e:
        log.warning("NWS alerts fetch failed: %s", e)
        return []


# ── Model Divergence Detection ───────────────────────────────────────────────

def detect_model_divergence(forecast: dict, weather_type: str = "temperature") -> Optional[dict]:
    """
    Detect significant disagreement between GFS and ECMWF.
    Returns divergence info if models disagree significantly.
    """
    from weather_config import DIVERGENCE_THRESHOLD_F

    gfs = forecast.get("gfs")
    ecmwf = forecast.get("ecmwf")

    if not gfs or not ecmwf:
        return None

    if weather_type == "temperature":
        gfs_val = gfs.get("temp_max")
        ecmwf_val = ecmwf.get("temp_max")
        if gfs_val is None or ecmwf_val is None:
            return None

        diff = abs(gfs_val - ecmwf_val)
        if diff >= DIVERGENCE_THRESHOLD_F:
            return {
                "gfs_value": gfs_val,
                "ecmwf_value": ecmwf_val,
                "divergence": round(diff, 1),
                "higher_model": "gfs" if gfs_val > ecmwf_val else "ecmwf",
            }

    elif weather_type == "precipitation":
        gfs_val = gfs.get("precip_sum")
        ecmwf_val = ecmwf.get("precip_sum")
        if gfs_val is None or ecmwf_val is None:
            return None

        # For precipitation, use ratio since absolute differences are less meaningful
        max_val = max(gfs_val, ecmwf_val)
        min_val = min(gfs_val, ecmwf_val)
        if max_val > 0.1 and (min_val == 0 or max_val / max(min_val, 0.01) > 2.0):
            return {
                "gfs_value": gfs_val,
                "ecmwf_value": ecmwf_val,
                "divergence": round(abs(gfs_val - ecmwf_val), 2),
                "higher_model": "gfs" if gfs_val > ecmwf_val else "ecmwf",
            }

    return None
