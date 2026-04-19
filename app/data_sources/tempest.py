"""WeatherFlow Tempest weather station API client.

Requires a Personal Access Token from https://tempestwx.com/settings/tokens
Set TEMPEST_TOKEN and TEMPEST_STATION_ID as environment variables.
"""

import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
from app.config import TEMPEST_TOKEN, TEMPEST_STATION_ID, TEMPEST_DEVICE_ID, TEMPEST_API_BASE


def is_configured():
    """Check if Tempest API credentials are set."""
    return bool(TEMPEST_TOKEN and TEMPEST_STATION_ID and TEMPEST_DEVICE_ID)


def _headers():
    return {"Authorization": f"Bearer {TEMPEST_TOKEN}"}


def get_station_info():
    """Get station metadata."""
    if not is_configured():
        return None
    resp = requests.get(
        f"{TEMPEST_API_BASE}/stations/{TEMPEST_STATION_ID}",
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_observation_history(days_back=2):
    """Fetch historical observations for the past N days.

    Returns a DataFrame with columns matching Tempest observation format:
    timestamp, wind_avg_mph, wind_dir_deg, wind_gust_mph,
    temp_f, humidity_pct, pressure_mb, precip_in, solar_radiation,
    uv_index, lightning_count, lightning_avg_distance.
    """
    if not is_configured():
        return pd.DataFrame()

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days_back)
    start_epoch = int(start.timestamp())
    end_epoch = int(now.timestamp())

    # Use the observations endpoint for device history
    if not TEMPEST_DEVICE_ID:
        print("[tempest] TEMPEST_DEVICE_ID not set — run Auto-Discover on the Station page")
        return pd.DataFrame()

    resp = requests.get(
        f"{TEMPEST_API_BASE}/observations/device/{TEMPEST_DEVICE_ID}",
        params={
            "time_start": start_epoch,
            "time_end": end_epoch,
            "token": TEMPEST_TOKEN,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    obs_list = data.get("obs", [])
    if not obs_list:
        return pd.DataFrame()

    # Tempest Tempest device observation fields (type="obs_st"):
    # [0] timestamp, [1] wind_lull, [2] wind_avg, [3] wind_gust,
    # [4] wind_direction, [5] wind_sample_interval, [6] station_pressure,
    # [7] air_temperature, [8] relative_humidity, [9] illuminance,
    # [10] uv, [11] solar_radiation, [12] rain_last_min, [13] precip_type,
    # [14] lightning_avg_distance, [15] lightning_count, [16] battery,
    # [17] report_interval, [18] local_daily_rain, [19] rain_final,
    # [20] local_daily_rain_final, [21] precip_analysis_type
    rows = []
    for obs in obs_list:
        if len(obs) < 17:
            continue
        rows.append({
            "timestamp": obs[0],
            "wind_lull_mph": (obs[1] or 0) * 2.237,    # m/s to mph
            "wind_avg_mph": (obs[2] or 0) * 2.237,
            "wind_gust_mph": (obs[3] or 0) * 2.237,
            "wind_dir_deg": obs[4],
            "pressure_mb": obs[6],
            "temp_c": obs[7],
            "temp_f": (obs[7] or 0) * 9 / 5 + 32 if obs[7] is not None else None,
            "humidity_pct": obs[8],
            "uv_index": obs[10],
            "solar_radiation": obs[11],
            "rain_mm": obs[12],
            "lightning_count": obs[15] or 0,
        })

    df = pd.DataFrame(rows)
    df["datetime_utc"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    return df


def get_current_conditions():
    """Get latest observation from station."""
    if not is_configured():
        return None
    resp = requests.get(
        f"{TEMPEST_API_BASE}/observations/station/{TEMPEST_STATION_ID}",
        params={"token": TEMPEST_TOKEN},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def aggregate_hourly(df):
    """Aggregate minute-level Tempest observations into hourly averages."""
    if df.empty:
        return df

    df = df.set_index("datetime_utc")
    hourly = df.resample("1h").agg({
        "temp_f": "mean",
        "humidity_pct": "mean",
        "wind_avg_mph": "mean",
        "wind_gust_mph": "max",
        "wind_dir_deg": "mean",
        "pressure_mb": "mean",
        "rain_mm": "sum",
        "solar_radiation": "mean",
    }).dropna(how="all")

    hourly = hourly.reset_index()
    return hourly
