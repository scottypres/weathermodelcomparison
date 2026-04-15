"""Compare Tempest weather station observations against forecast model predictions."""

import pandas as pd
import numpy as np


def compare_station_to_forecasts(station_hourly, forecast_models):
    """Compare hourly Tempest observations against hourly forecast data.

    Args:
        station_hourly: DataFrame from tempest.aggregate_hourly()
        forecast_models: Dict of {model_name: DataFrame} from Open-Meteo

    Returns:
        Dict with comparison results per model
    """
    if station_hourly.empty:
        return {}

    results = {}
    station = station_hourly.copy()
    station["hour_key"] = station["datetime_utc"].dt.floor("h")

    for model_name, forecast_df in forecast_models.items():
        if forecast_df.empty or "time" not in forecast_df.columns:
            continue

        fc = forecast_df.copy()
        fc["hour_key"] = pd.to_datetime(fc["time"]).dt.tz_localize("UTC") if fc["time"].dt.tz is None else fc["time"].dt.floor("h")

        merged = pd.merge(station, fc, on="hour_key", how="inner", suffixes=("_obs", "_fc"))
        if merged.empty:
            continue

        comp = pd.DataFrame()
        comp["time"] = merged["hour_key"]
        comp["model"] = model_name

        # Temperature
        if "temp_f" in merged.columns and "temperature_2m" in merged.columns:
            comp["obs_temp_f"] = merged["temp_f"]
            comp["fc_temp_f"] = merged["temperature_2m"]
            comp["temp_delta_f"] = merged["temp_f"] - merged["temperature_2m"]

        # Wind speed
        if "wind_avg_mph" in merged.columns and "wind_speed_10m" in merged.columns:
            comp["obs_wind_mph"] = merged["wind_avg_mph"]
            comp["fc_wind_mph"] = merged["wind_speed_10m"]
            comp["wind_delta_mph"] = merged["wind_avg_mph"] - merged["wind_speed_10m"]

        # Wind gusts
        if "wind_gust_mph" in merged.columns and "wind_gusts_10m" in merged.columns:
            comp["obs_gust_mph"] = merged["wind_gust_mph"]
            comp["fc_gust_mph"] = merged["wind_gusts_10m"]
            comp["gust_delta_mph"] = merged["wind_gust_mph"] - merged["wind_gusts_10m"]

        # Wind direction
        if "wind_dir_deg" in merged.columns and "wind_direction_10m" in merged.columns:
            comp["obs_wind_dir"] = merged["wind_dir_deg"]
            comp["fc_wind_dir"] = merged["wind_direction_10m"]
            # Circular difference
            diff = merged["wind_dir_deg"] - merged["wind_direction_10m"]
            comp["wind_dir_delta"] = (diff + 180) % 360 - 180

        # Humidity
        if "humidity_pct" in merged.columns and "relative_humidity_2m" in merged.columns:
            comp["obs_humidity_pct"] = merged["humidity_pct"]
            comp["fc_humidity_pct"] = merged["relative_humidity_2m"]
            comp["humidity_delta_pct"] = merged["humidity_pct"] - merged["relative_humidity_2m"]

        # Pressure
        if "pressure_mb" in merged.columns:
            comp["obs_pressure_mb"] = merged["pressure_mb"]

        # Precipitation
        if "rain_mm" in merged.columns and "rain" in merged.columns:
            comp["obs_rain_mm"] = merged["rain_mm"]
            comp["fc_rain_mm"] = merged["rain"]

        results[model_name] = comp

    return results


def compute_daily_scores(comparison_results):
    """Compute daily accuracy scores for each model vs station.

    Returns a DataFrame with one row per model.
    """
    scores = []
    for model_name, comp in comparison_results.items():
        score = {"model": model_name, "n_hours": len(comp)}

        for metric, col in [
            ("temp", "temp_delta_f"),
            ("wind", "wind_delta_mph"),
            ("gust", "gust_delta_mph"),
            ("wind_dir", "wind_dir_delta"),
            ("humidity", "humidity_delta_pct"),
        ]:
            if col in comp.columns:
                valid = comp[col].dropna()
                if not valid.empty:
                    score[f"{metric}_mae"] = valid.abs().mean()
                    score[f"{metric}_rmse"] = np.sqrt((valid ** 2).mean())
                    score[f"{metric}_bias"] = valid.mean()

        scores.append(score)

    return pd.DataFrame(scores)
