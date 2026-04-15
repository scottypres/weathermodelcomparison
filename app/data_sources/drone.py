"""Parse drone mission CSV files and bin data by altitude for comparison."""

import pandas as pd
import numpy as np
from datetime import datetime, timezone


# Altitude bins in feet — edges for grouping drone readings
# Matches pressure levels and model altitude levels
ALTITUDE_BINS_FT = [0, 50, 150, 300, 400, 500, 700, 900, 1200, 1500, 2000]
ALTITUDE_BIN_LABELS = [
    "0-50ft (surface)",
    "50-150ft",
    "150-300ft",
    "300-400ft (~80m)",
    "400-500ft (~120m)",
    "500-700ft (~180m)",
    "700-900ft",
    "900-1200ft (~975hPa)",
    "1200-1500ft (~950hPa)",
    "1500-2000ft",
]


def parse_mission_csv(filepath):
    """Parse a drone mission CSV and return a cleaned DataFrame."""
    df = pd.read_csv(filepath)

    # Convert Unix timestamp to datetime
    df["datetime_utc"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)

    # Convert sensor temps from Celsius to Fahrenheit
    for col in ["bmp390l_temp_c", "sht41_temp_c", "sdp811_temp_c", "tmp102_temp_c"]:
        if col in df.columns:
            f_col = col.replace("_c", "_f")
            df[f_col] = df[col] * 9.0 / 5.0 + 32.0

    return df


def get_mission_summary(df):
    """Return a summary dict for the mission."""
    return {
        "mission": df["mission"].iloc[0] if "mission" in df.columns else "unknown",
        "start_time": df["datetime_utc"].min(),
        "end_time": df["datetime_utc"].max(),
        "duration_seconds": (df["datetime_utc"].max() - df["datetime_utc"].min()).total_seconds(),
        "max_altitude_ft": df["altitude_ft"].max(),
        "min_altitude_ft": df["altitude_ft"].min(),
        "latitude": df["latitude"].median(),
        "longitude": df["longitude"].median(),
        "total_readings": len(df),
        "stages": df["mission_stage"].unique().tolist() if "mission_stage" in df.columns else [],
    }


def bin_by_altitude(df, sampling_only=True):
    """Bin drone readings by altitude and compute averages.

    Args:
        df: Parsed mission DataFrame
        sampling_only: If True, only use rows where sampling=1 or in Ascent/Wind Hold stages

    Returns:
        DataFrame with one row per altitude bin, averaged sensor values
    """
    filtered = df.copy()
    if sampling_only and "mission_stage" in filtered.columns:
        # Use Ascent and Wind Hold stages (active measurement phases)
        filtered = filtered[
            filtered["mission_stage"].isin(["Ascent", "Wind Hold", "Start Alt"])
        ]

    if filtered.empty:
        # Fall back to all data if no sampling stages found
        filtered = df.copy()

    # Create altitude bins
    bins = [b for b in ALTITUDE_BINS_FT if b <= filtered["altitude_ft"].max() + 100]
    labels = ALTITUDE_BIN_LABELS[: len(bins) - 1]

    if len(bins) < 2:
        bins = [0, filtered["altitude_ft"].max() + 10]
        labels = [f"0-{int(bins[1])}ft"]

    filtered["alt_bin"] = pd.cut(filtered["altitude_ft"], bins=bins, labels=labels, right=True)

    # Columns to average
    avg_cols = [
        "altitude_ft", "sht41_temp_f", "sht41_humidity_pct",
        "bmp390l_temp_f", "bmp390l_pressure_hpa",
        "sdp811_wind_mph", "sdp811_temp_f",
        "groundspeed_mph", "airspeed_mph",
    ]
    available_cols = [c for c in avg_cols if c in filtered.columns]

    binned = filtered.groupby("alt_bin", observed=True)[available_cols].agg(["mean", "std", "count"])
    binned.columns = ["_".join(col).strip() for col in binned.columns.values]

    return binned.reset_index()


def get_altitude_profile(df):
    """Get a continuous altitude profile for plotting (time vs altitude with sensor data)."""
    cols = [
        "datetime_utc", "altitude_ft", "sht41_temp_f", "sht41_humidity_pct",
        "bmp390l_temp_f", "bmp390l_pressure_hpa", "sdp811_wind_mph",
        "groundspeed_mph", "mission_stage",
    ]
    available = [c for c in cols if c in df.columns]
    return df[available].copy()
