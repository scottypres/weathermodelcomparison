import os

# Location (from your sample data — Royal Palm Beach, FL area)
LATITUDE = 26.8065
LONGITUDE = -80.2741

# Open-Meteo (free, no key needed)
OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"

# Tempest WeatherFlow API
TEMPEST_TOKEN = os.environ.get("TEMPEST_TOKEN", "")
TEMPEST_STATION_ID = os.environ.get("TEMPEST_STATION_ID", "")
TEMPEST_DEVICE_ID = os.environ.get("TEMPEST_DEVICE_ID", "")
TEMPEST_API_BASE = "https://swd.weatherflow.com/swd/rest"

# Forecast models to compare
# Group 1: Global models (MODELS1-style)
GLOBAL_MODELS = ["ecmwf_ifs", "icon_seamless", "gem_seamless", "gfs_seamless"]
# Group 2: High-res US models (MODELS2-style)
HIRES_MODELS = ["gfs_seamless", "gfs_hrrr"]

# Common weather variables to fetch per model
SURFACE_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_speed_80m",
    "wind_direction_10m",
    "wind_direction_80m",
    "wind_gusts_10m",
    "temperature_80m",
    "precipitation",
    "rain",
]

ALTITUDE_VARS = [
    "wind_speed_120m",
    "wind_speed_180m",
    "wind_direction_120m",
    "wind_direction_180m",
    "temperature_120m",
    "temperature_180m",
]

PRESSURE_LEVEL_VARS = [
    "temperature_1000hPa",
    "temperature_975hPa",
    "temperature_950hPa",
    "relative_humidity_1000hPa",
    "relative_humidity_975hPa",
    "relative_humidity_950hPa",
    "wind_speed_1000hPa",
    "wind_speed_975hPa",
    "wind_speed_950hPa",
    "wind_direction_1000hPa",
    "wind_direction_975hPa",
    "wind_direction_950hPa",
]

# Approximate pressure level to altitude mapping (for South FL conditions)
PRESSURE_TO_ALT_FT = {
    "1000hPa": 364,
    "975hPa": 1181,
    "950hPa": 1773,
}

# Altitude reference heights in feet
ALTITUDE_HEIGHTS_FT = {
    "10m": 33,
    "80m": 262,
    "120m": 394,
    "180m": 590,
}

# Database
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "weather.db")

# Upload paths
MISSIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "missions")
WINDY_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "windy")
