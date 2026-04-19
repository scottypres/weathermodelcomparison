"""Fetch forecast history from Open-Meteo for multiple weather models."""

import json
import requests
import pandas as pd
from datetime import datetime, timezone
from app.config import (
    OPEN_METEO_BASE, LATITUDE, LONGITUDE,
    GLOBAL_MODELS, HIRES_MODELS,
    SURFACE_VARS, ALTITUDE_VARS, PRESSURE_LEVEL_VARS,
)


def _build_url(models, include_altitude=True, past_days=2, forecast_days=1,
               lat=None, lon=None):
    """Build an Open-Meteo API URL for the given models and variables."""
    lat = lat or LATITUDE
    lon = lon or LONGITUDE

    hourly_vars = list(SURFACE_VARS) + list(PRESSURE_LEVEL_VARS)
    if include_altitude:
        hourly_vars += list(ALTITUDE_VARS)

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(hourly_vars),
        "models": ",".join(models),
        "past_days": past_days,
        "forecast_days": forecast_days,
        "wind_speed_unit": "mph",
        "temperature_unit": "fahrenheit",
    }
    return params


def fetch_forecasts(models, include_altitude=True, past_days=2, forecast_days=1,
                    lat=None, lon=None):
    """Fetch forecast data from Open-Meteo and return a dict of DataFrames keyed by model."""
    params = _build_url(models, include_altitude, past_days, forecast_days, lat, lon)
    try:
        resp = requests.get(OPEN_METEO_BASE, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return _parse_response(data, models)
    except requests.RequestException as e:
        print(f"[open_meteo] API request failed: {e}")
        return {}


def load_from_sample_file(filepath):
    """Load forecast data from a saved sample file (MODELS1/MODELS2 format).

    These files have the API URL on line 1, blank line 2, and JSON on line 3.
    """
    with open(filepath) as f:
        url = f.readline().strip()
        f.readline()  # blank
        data = json.loads(f.readline())

    # Detect models from the URL or data keys
    hourly_keys = list(data.get("hourly", {}).keys())
    models = set()
    known_models = [
        "ecmwf_ifs", "icon_seamless", "gem_seamless",
        "gfs_seamless", "gfs_hrrr",
    ]
    for key in hourly_keys:
        for model in known_models:
            if key.endswith(f"_{model}"):
                models.add(model)

    return _parse_response(data, list(models))


def _parse_response(data, models):
    """Parse Open-Meteo JSON response into per-model DataFrames."""
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])

    result = {}
    for model in models:
        model_cols = {"time": pd.to_datetime(times)}
        suffix = f"_{model}"
        for key, values in hourly.items():
            if key == "time":
                continue
            if key.endswith(suffix):
                clean_name = key[: -len(suffix)]
                model_cols[clean_name] = values
        if len(model_cols) > 1:
            df = pd.DataFrame(model_cols)
            df["model"] = model
            result[model] = df

    return result


def fetch_global_models(past_days=2, forecast_days=1, lat=None, lon=None):
    """Fetch ECMWF, ICON, GEM, GFS forecasts."""
    return fetch_forecasts(
        GLOBAL_MODELS, include_altitude=True,
        past_days=past_days, forecast_days=forecast_days,
        lat=lat, lon=lon,
    )


def fetch_hires_models(past_days=2, forecast_days=1, lat=None, lon=None):
    """Fetch GFS + HRRR high-resolution forecasts."""
    return fetch_forecasts(
        HIRES_MODELS, include_altitude=False,
        past_days=past_days, forecast_days=forecast_days,
        lat=lat, lon=lon,
    )


def fetch_all_models(past_days=2, forecast_days=1, lat=None, lon=None):
    """Fetch all available model forecasts and merge into one dict."""
    result = {}
    result.update(fetch_global_models(past_days, forecast_days, lat, lon))
    hires = fetch_hires_models(past_days, forecast_days, lat, lon)
    # Only add HRRR (GFS already present from global)
    if "gfs_hrrr" in hires:
        result["gfs_hrrr"] = hires["gfs_hrrr"]
    return result


def get_forecast_for_time_range(start_utc, end_utc, lat=None, lon=None):
    """Fetch forecasts covering a specific time range (for drone mission matching).

    Calculates appropriate past_days/forecast_days to cover the window.
    """
    now = datetime.now(timezone.utc)
    start_dt = start_utc if isinstance(start_utc, datetime) else datetime.fromisoformat(start_utc)
    end_dt = end_utc if isinstance(end_utc, datetime) else datetime.fromisoformat(end_utc)

    # Open-Meteo uses past_days relative to today
    days_ago_start = (now - start_dt).days + 1
    past_days = min(days_ago_start, 7)  # Open-Meteo free tier max
    forecast_days = 1

    return fetch_all_models(past_days=past_days, forecast_days=forecast_days,
                            lat=lat, lon=lon)
