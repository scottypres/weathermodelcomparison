"""Compare drone mission sensor data against forecast model predictions."""

import pandas as pd
import numpy as np
from datetime import timezone
from app.config import PRESSURE_TO_ALT_FT, ALTITUDE_HEIGHTS_FT


def _find_nearest_hour(forecast_df, target_utc):
    """Find the forecast row closest to the target UTC time."""
    fc_times = forecast_df["time"]
    # Ensure timezone compatibility
    if fc_times.dt.tz is None and target_utc.tzinfo is not None:
        fc_times = fc_times.dt.tz_localize("UTC")
    elif fc_times.dt.tz is not None and target_utc.tzinfo is None:
        target_utc = target_utc.replace(tzinfo=timezone.utc)
    diffs = abs(fc_times - target_utc)
    return forecast_df.loc[diffs.idxmin()]


def build_forecast_altitude_profile(forecast_row):
    """Extract an altitude profile from a single forecast time row.

    Returns a DataFrame with columns: altitude_ft, temp_f, wind_speed_mph,
    wind_dir_deg, humidity_pct, source_level
    """
    points = []

    # Surface & altitude levels
    alt_map = {
        "10m": ("temperature_2m", "wind_speed_10m", "wind_direction_10m", "relative_humidity_2m"),
        "80m": ("temperature_80m", "wind_speed_80m", "wind_direction_80m", "relative_humidity_2m"),
        "120m": ("temperature_120m", "wind_speed_120m", "wind_direction_120m", None),
        "180m": ("temperature_180m", "wind_speed_180m", "wind_direction_180m", None),
    }

    for level, (temp_col, ws_col, wd_col, rh_col) in alt_map.items():
        alt_ft = ALTITUDE_HEIGHTS_FT.get(level, 0)
        point = {
            "altitude_ft": alt_ft,
            "source_level": level,
        }
        if temp_col in forecast_row.index:
            point["temp_f"] = forecast_row.get(temp_col)
        if ws_col in forecast_row.index:
            point["wind_speed_mph"] = forecast_row.get(ws_col)
        if wd_col in forecast_row.index:
            point["wind_dir_deg"] = forecast_row.get(wd_col)
        if rh_col and rh_col in forecast_row.index:
            point["humidity_pct"] = forecast_row.get(rh_col)
        points.append(point)

    # Pressure levels
    pressure_map = {
        "1000hPa": ("temperature_1000hPa", "wind_speed_1000hPa", "wind_direction_1000hPa", "relative_humidity_1000hPa"),
        "975hPa": ("temperature_975hPa", "wind_speed_975hPa", "wind_direction_975hPa", "relative_humidity_975hPa"),
        "950hPa": ("temperature_950hPa", "wind_speed_950hPa", "wind_direction_950hPa", "relative_humidity_950hPa"),
    }

    for level, (temp_col, ws_col, wd_col, rh_col) in pressure_map.items():
        alt_ft = PRESSURE_TO_ALT_FT.get(level, 0)
        point = {
            "altitude_ft": alt_ft,
            "source_level": level,
        }
        if temp_col in forecast_row.index:
            point["temp_f"] = forecast_row.get(temp_col)
        if ws_col in forecast_row.index:
            point["wind_speed_mph"] = forecast_row.get(ws_col)
        if wd_col in forecast_row.index:
            point["wind_dir_deg"] = forecast_row.get(wd_col)
        if rh_col in forecast_row.index:
            point["humidity_pct"] = forecast_row.get(rh_col)
        points.append(point)

    df = pd.DataFrame(points)
    df = df.sort_values("altitude_ft").reset_index(drop=True)
    return df


def compare_drone_to_forecasts(drone_binned, forecast_models, mission_time_utc):
    """Compare altitude-binned drone data against forecast model profiles.

    Args:
        drone_binned: DataFrame from drone.bin_by_altitude()
        forecast_models: Dict of {model_name: DataFrame} from Open-Meteo
        mission_time_utc: datetime of the mission (UTC)

    Returns:
        Dict with comparison results per model
    """
    results = {}

    for model_name, forecast_df in forecast_models.items():
        # Find forecast row nearest to mission time
        if forecast_df.empty or "time" not in forecast_df.columns:
            continue

        nearest = _find_nearest_hour(forecast_df, mission_time_utc)
        forecast_profile = build_forecast_altitude_profile(nearest)
        forecast_profile["model"] = model_name

        # Compute deltas where drone and forecast altitudes overlap
        comparison_rows = []
        for _, drone_row in drone_binned.iterrows():
            drone_alt = drone_row.get("altitude_ft_mean", 0)
            if pd.isna(drone_alt):
                continue

            # Find nearest forecast altitude
            if forecast_profile.empty:
                continue
            idx = (forecast_profile["altitude_ft"] - drone_alt).abs().idxmin()
            fc_row = forecast_profile.loc[idx]

            row = {
                "drone_alt_bin": drone_row.get("alt_bin", ""),
                "drone_alt_ft": drone_alt,
                "forecast_alt_ft": fc_row["altitude_ft"],
                "forecast_level": fc_row["source_level"],
                "model": model_name,
            }

            # Temperature comparison
            drone_temp = drone_row.get("sht41_temp_f_mean")
            fc_temp = fc_row.get("temp_f")
            if pd.notna(drone_temp) and pd.notna(fc_temp):
                row["drone_temp_f"] = drone_temp
                row["forecast_temp_f"] = fc_temp
                row["temp_delta_f"] = drone_temp - fc_temp

            # Wind speed comparison
            drone_wind = drone_row.get("sdp811_wind_mph_mean")
            fc_wind = fc_row.get("wind_speed_mph")
            if pd.notna(drone_wind) and pd.notna(fc_wind):
                row["drone_wind_mph"] = drone_wind
                row["forecast_wind_mph"] = fc_wind
                row["wind_delta_mph"] = drone_wind - fc_wind

            # Humidity comparison
            drone_rh = drone_row.get("sht41_humidity_pct_mean")
            fc_rh = fc_row.get("humidity_pct")
            if pd.notna(drone_rh) and pd.notna(fc_rh):
                row["drone_humidity_pct"] = drone_rh
                row["forecast_humidity_pct"] = fc_rh
                row["humidity_delta_pct"] = drone_rh - fc_rh

            comparison_rows.append(row)

        if comparison_rows:
            results[model_name] = {
                "comparison": pd.DataFrame(comparison_rows),
                "forecast_profile": forecast_profile,
            }

    return results


def compute_model_scores(comparison_results):
    """Compute accuracy scores for each model based on drone comparison.

    Lower scores = better accuracy.
    Returns a DataFrame with one row per model.
    """
    scores = []
    for model_name, data in comparison_results.items():
        comp = data["comparison"]
        score = {
            "model": model_name,
        }
        if "temp_delta_f" in comp.columns:
            score["temp_mae_f"] = comp["temp_delta_f"].abs().mean()
            score["temp_rmse_f"] = np.sqrt((comp["temp_delta_f"] ** 2).mean())
        if "wind_delta_mph" in comp.columns:
            score["wind_mae_mph"] = comp["wind_delta_mph"].abs().mean()
            score["wind_rmse_mph"] = np.sqrt((comp["wind_delta_mph"] ** 2).mean())
        if "humidity_delta_pct" in comp.columns:
            score["humidity_mae_pct"] = comp["humidity_delta_pct"].abs().mean()
            score["humidity_rmse_pct"] = np.sqrt((comp["humidity_delta_pct"] ** 2).mean())
        scores.append(score)

    return pd.DataFrame(scores)
