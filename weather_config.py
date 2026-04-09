"""
Weather Prediction Markets — Configuration
All tunable parameters for weather bots, APIs, and backtesting.
"""

# ── Polymarket API ───────────────────────────────────────────────────────────
POLYMARKET_GAMMA_API = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB_API = "https://clob.polymarket.com"

# ── Open-Meteo APIs ──────────────────────────────────────────────────────────
OPEN_METEO_FORECAST_API = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_HISTORICAL_API = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_PREVIOUS_RUNS_API = "https://previous-runs-api.open-meteo.com/v1/forecast"

# ── NWS Alerts (for storm bot) ───────────────────────────────────────────────
NWS_ALERTS_API = "https://api.weather.gov/alerts/active"

# ── Forecast Cache ───────────────────────────────────────────────────────────
FORECAST_CACHE_TTL = 21600  # 6 hours in seconds (matches model update cycle)

# ── Signal Thresholds ────────────────────────────────────────────────────────
MIN_EDGE_TEMPERATURE = 0.08     # 8% minimum edge for temperature markets
MIN_EDGE_PRECIPITATION = 0.10   # 10% — precipitation forecasts are noisier
MIN_EDGE_STORM = 0.12           # 12% — storm markets have thin liquidity
MIN_EDGE_DIVERGENCE = 0.06      # 6% — model divergence is systematic

# ── Forecast Uncertainty ─────────────────────────────────────────────────────
TEMP_BASE_UNCERTAINTY_F = 3.0   # Base std dev in F for 1-day forecast
PRECIP_BASE_UNCERTAINTY_MM = 5.0
UNCERTAINTY_GROWTH_RATE = 0.5   # sqrt growth per day out

# ── Probability Estimation ───────────────────────────────────────────────────
MODEL_WEIGHT_GFS = 0.5          # Default GFS weight (adjusted by accuracy tracking)
MODEL_WEIGHT_ECMWF = 0.5       # Default ECMWF weight
DIVERGENCE_THRESHOLD_F = 5.0   # Minimum GFS-ECMWF disagreement for divergence bot

# ── Market Scanning ──────────────────────────────────────────────────────────
WEATHER_MARKETS_TO_SCAN = 100   # Max weather markets to scan per run
MIN_MARKET_VOLUME = 500         # Minimum volume in USD
MIN_DAYS_TO_RESOLUTION = 1      # Skip markets resolving today
MAX_DAYS_TO_RESOLUTION = 16     # Skip markets too far out (forecast unreliable)

# ── Weather Bot Exit Parameters ──────────────────────────────────────────────
WX_TARGET_YES = 85              # Close BUY YES when price >= this
WX_TARGET_NO = 15               # Close BUY NO when price <= this
WX_STOP_PP = 10                 # Stop loss (pp)
WX_TRAILING_STOP_PP = 8         # Trailing stop from peak
WX_MAX_DAYS_TEMP = 7            # Max hold for temperature trades
WX_MAX_DAYS_PRECIP = 5          # Max hold for precipitation trades
WX_MAX_DAYS_STORM = 14          # Max hold for storm trades
WX_MAX_DAYS_DIVERGE = 7         # Max hold for divergence trades

# ── Backtest Parameters ──────────────────────────────────────────────────────
BACKTEST_DEFAULT_DAYS = 90      # Default lookback for backtesting
BACKTEST_STARTING_BALANCE = 1000  # Simulated starting balance (USD)
BACKTEST_BASE_STAKE_PCT = 0.05  # 5% of balance per trade

# ── Polymarket Weather Search Keywords ───────────────────────────────────────
WEATHER_KEYWORDS = [
    "temperature", "weather", "rain", "snow", "hurricane",
    "high of", "degrees", "precipitation", "storm", "tornado",
    "celsius", "fahrenheit", "heatwave", "cold snap", "frost",
    "flooding", "wind speed", "tropical",
]

# ── City Coordinates (lat, lon) ──────────────────────────────────────────────
CITY_COORDS = {
    # US Major Cities
    "New York":      (40.7128, -74.0060),
    "Los Angeles":   (34.0522, -118.2437),
    "Chicago":       (41.8781, -87.6298),
    "Houston":       (29.7604, -95.3698),
    "Phoenix":       (33.4484, -112.0740),
    "Philadelphia":  (39.9526, -75.1652),
    "San Antonio":   (29.4241, -98.4936),
    "San Diego":     (32.7157, -117.1611),
    "Dallas":        (32.7767, -96.7970),
    "Miami":         (25.7617, -80.1918),
    "Atlanta":       (33.7490, -84.3880),
    "Boston":        (42.3601, -71.0589),
    "Seattle":       (47.6062, -122.3321),
    "Denver":        (39.7392, -104.9903),
    "Washington":    (38.9072, -77.0369),
    "Nashville":     (36.1627, -86.7816),
    "Las Vegas":     (36.1699, -115.1398),
    "Portland":      (45.5152, -122.6784),
    "Detroit":       (42.3314, -83.0458),
    "Minneapolis":   (44.9778, -93.2650),
    "San Francisco": (37.7749, -122.4194),
    "Austin":        (30.2672, -97.7431),
    "Tampa":         (27.9506, -82.4572),
    "Orlando":       (28.5383, -81.3792),
    "Charlotte":     (35.2271, -80.8431),
    "Indianapolis":  (39.7684, -86.1581),
    "Columbus":      (39.9612, -82.9988),
    "Kansas City":   (39.0997, -94.5786),
    "Salt Lake City":(40.7608, -111.8910),
    "Anchorage":     (61.2181, -149.9003),
    # International
    "London":        (51.5074, -0.1278),
    "Paris":         (48.8566, 2.3522),
    "Tokyo":         (35.6762, 139.6503),
    "Sydney":        (-33.8688, 151.2093),
    "Toronto":       (43.6532, -79.3832),
    "Mexico City":   (19.4326, -99.1332),
    "Berlin":        (52.5200, 13.4050),
    "Moscow":        (55.7558, 37.6173),
    "Dubai":         (25.2048, 55.2708),
    "Mumbai":        (19.0760, 72.8777),
    "Beijing":       (39.9042, 116.4074),
    "Shanghai":      (31.2304, 121.4737),
    "Hong Kong":     (22.3193, 114.1694),
    "Singapore":     (1.3521, 103.8198),
    "Istanbul":      (41.0082, 28.9784),
    "Tel Aviv":      (32.0853, 34.7818),
    "Cairo":         (30.0444, 31.2357),
    "São Paulo":     (-23.5505, -46.6333),
    "Buenos Aires":  (-34.6037, -58.3816),
    "Lagos":         (6.5244, 3.3792),
}

# ── City Aliases (fuzzy matching) ────────────────────────────────────────────
CITY_ALIASES = {
    "nyc": "New York", "new york city": "New York", "manhattan": "New York",
    "la": "Los Angeles", "l.a.": "Los Angeles",
    "sf": "San Francisco", "san fran": "San Francisco",
    "dc": "Washington", "washington dc": "Washington", "washington d.c.": "Washington",
    "philly": "Philadelphia", "phx": "Phoenix",
    "chi": "Chicago", "chiraq": "Chicago",
    "vegas": "Las Vegas", "lv": "Las Vegas",
    "nola": "Nashville",
    "slc": "Salt Lake City",
    "kc": "Kansas City",
    "indy": "Indianapolis",
    "det": "Detroit",
    "atl": "Atlanta",
    "bos": "Boston",
    "sea": "Seattle",
    "den": "Denver",
    "pdx": "Portland",
    "msp": "Minneapolis",
    "sat": "San Antonio",
    "orl": "Orlando",
    "clt": "Charlotte",
    "sao paulo": "São Paulo",
    "saopaulo": "São Paulo",
    "ba": "Buenos Aires",
    "hk": "Hong Kong",
}
