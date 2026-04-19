"""Windy weather data — manual entry from screenshots.

Windy data is provided as screenshots, so this module handles:
1. Storing manually-entered Windy data alongside screenshot uploads
2. Structuring it for comparison with other data sources
"""

import os
import json
import pandas as pd
from datetime import datetime
from app.config import WINDY_DIR


# Standard Windy altitude levels seen in screenshots
WINDY_ALTITUDES_FT = [364, 1773, 2500, 3243, 4781, 6394]


def save_windy_entry(entry_data, screenshot_path=None):
    """Save a manual Windy data entry.

    entry_data should be a dict like:
    {
        "date": "2026-04-15",
        "hours": [11, 12, 13, 14, ...],  # local time hours
        "altitudes": {
            "364ft": {
                "wind_speed_mph": [13.8, 15.2, 14.9, 14.7, ...],
                "wind_gust_mph": [23, 23, 23, 23, ...],
                "wind_dir": ["E", "E", "E", "E", ...],
                "temp_f": [77, 79, 80, 81, ...],
                "dewpoint_f": [57, 57, 57, 57, ...],
                "humidity_pct": [48, 46, 44, 43, ...],
            },
            "1773ft": { ... },
            ...
        },
        "screenshot": "filename.jpg"  # optional
    }
    """
    os.makedirs(WINDY_DIR, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    date_str = entry_data.get("date", timestamp[:8])
    filename = f"windy_{date_str}_{timestamp}.json"
    filepath = os.path.join(WINDY_DIR, filename)

    if screenshot_path:
        entry_data["screenshot"] = screenshot_path

    with open(filepath, "w") as f:
        json.dump(entry_data, f, indent=2, default=str)

    return filepath


def load_windy_entries():
    """Load all saved Windy data entries."""
    if not os.path.exists(WINDY_DIR):
        return []

    entries = []
    for fname in sorted(os.listdir(WINDY_DIR)):
        if fname.endswith(".json"):
            fpath = os.path.join(WINDY_DIR, fname)
            with open(fpath) as f:
                entry = json.load(f)
                entry["_filename"] = fname
                entries.append(entry)
    return entries


def windy_entry_to_dataframe(entry):
    """Convert a Windy entry dict to a DataFrame for comparison."""
    rows = []
    hours = entry.get("hours", [])
    date_str = entry.get("date", "")

    for alt_label, alt_data in entry.get("altitudes", {}).items():
        alt_ft = int(alt_label.replace("ft", ""))
        for i, hour in enumerate(hours):
            row = {
                "date": date_str,
                "hour": hour,
                "altitude_ft": alt_ft,
                "source": "windy",
            }
            for metric, values in alt_data.items():
                if i < len(values):
                    row[metric] = values[i]
            rows.append(row)

    return pd.DataFrame(rows)


def get_windy_for_date(date_str):
    """Get Windy data for a specific date."""
    entries = load_windy_entries()
    for entry in entries:
        if entry.get("date") == date_str:
            return windy_entry_to_dataframe(entry)
    return pd.DataFrame()
