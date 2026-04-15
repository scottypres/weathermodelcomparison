"""Flask web application for weather model comparison."""

import os
import json
import traceback
from datetime import datetime, timezone

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
import pandas as pd
import requests as http_requests

from app.config import MISSIONS_DIR, WINDY_DIR, LATITUDE, LONGITUDE
from app.database import init_db, save_drone_mission, get_drone_missions, save_drone_comparison
from app.data_sources import drone, open_meteo, tempest, windy, windy_ocr
from app.comparisons import drone_comparison, station_comparison
from app import charts

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "weather-compare-dev-key")


@app.before_request
def ensure_db():
    init_db()


# ---------- Dashboard ----------

@app.route("/")
def dashboard():
    missions = get_drone_missions()
    tempest_configured = tempest.is_configured()
    return render_template("dashboard.html",
                           missions=missions,
                           tempest_configured=tempest_configured)


# ---------- Drone Mission Routes ----------

@app.route("/drone/upload", methods=["GET", "POST"])
def drone_upload():
    if request.method == "POST":
        if "mission_file" not in request.files:
            flash("No file selected", "error")
            return redirect(request.url)

        f = request.files["mission_file"]
        if f.filename == "":
            flash("No file selected", "error")
            return redirect(request.url)

        os.makedirs(MISSIONS_DIR, exist_ok=True)
        filename = secure_filename(f.filename)
        filepath = os.path.join(MISSIONS_DIR, filename)
        f.save(filepath)

        try:
            df = drone.parse_mission_csv(filepath)
            summary = drone.get_mission_summary(df)
            mission_id = save_drone_mission(summary["mission"], filename, summary)
            flash(f"Mission '{summary['mission']}' uploaded ({summary['total_readings']} readings, "
                  f"max alt {summary['max_altitude_ft']:.0f}ft)", "success")
            return redirect(url_for("drone_analyze", mission_id=mission_id))
        except Exception as e:
            flash(f"Error parsing CSV: {e}", "error")
            traceback.print_exc()

    return render_template("drone_upload.html")


@app.route("/drone/<int:mission_id>")
def drone_analyze(mission_id):
    missions = get_drone_missions()
    mission = next((m for m in missions if m["id"] == mission_id), None)
    if not mission:
        flash("Mission not found", "error")
        return redirect(url_for("dashboard"))

    filepath = os.path.join(MISSIONS_DIR, mission["filename"])
    if not os.path.exists(filepath):
        flash("Mission file not found on disk", "error")
        return redirect(url_for("dashboard"))

    try:
        df = drone.parse_mission_csv(filepath)
        summary = drone.get_mission_summary(df)
        binned = drone.bin_by_altitude(df)
        profile_df = drone.get_altitude_profile(df)

        # Build flight profile chart
        profile_chart = charts.drone_altitude_profile(profile_df)

        # Fetch forecast data for the mission time window
        mission_time = summary["start_time"]
        forecast_models = open_meteo.get_forecast_for_time_range(
            summary["start_time"], summary["end_time"],
            lat=summary["latitude"], lon=summary["longitude"],
        )

        # If API unavailable, try loading from sample files
        if not forecast_models:
            samples_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "SAMPLES")
            for sample_file in ["MODELS1", "MODELS2"]:
                sample_path = os.path.join(samples_dir, sample_file)
                if os.path.exists(sample_path):
                    forecast_models.update(open_meteo.load_from_sample_file(sample_path))
            if forecast_models:
                flash("Using cached sample forecast data (API unavailable)", "warning")

        # Compare drone data against each model
        comparison_results = drone_comparison.compare_drone_to_forecasts(
            binned, forecast_models, mission_time,
        )

        # Build comparison charts
        temp_chart = charts.drone_vs_forecast_temp(comparison_results, binned)
        wind_chart = charts.drone_vs_forecast_wind(comparison_results, binned)
        humidity_chart = charts.drone_vs_forecast_humidity(comparison_results, binned)

        # Score each model
        scores = drone_comparison.compute_model_scores(comparison_results)
        scores_chart = charts.model_scores_table(scores) if not scores.empty else None

        # Save comparisons to DB
        for model_name, data in comparison_results.items():
            model_scores = scores[scores["model"] == model_name].to_dict("records")
            model_score = model_scores[0] if model_scores else {}
            save_drone_comparison(mission_id, model_name, data["comparison"], model_score)

        return render_template("drone_analysis.html",
                               mission=mission, summary=summary,
                               profile_chart=profile_chart,
                               temp_chart=temp_chart,
                               wind_chart=wind_chart,
                               humidity_chart=humidity_chart,
                               scores_chart=scores_chart,
                               scores=scores.to_dict("records") if not scores.empty else [])
    except Exception as e:
        flash(f"Analysis error: {e}", "error")
        traceback.print_exc()
        return redirect(url_for("dashboard"))


# ---------- Station Comparison Routes ----------

@app.route("/station/discover")
def station_discover():
    """Auto-discover Tempest station and device IDs from the API token."""
    from app.config import TEMPEST_TOKEN, TEMPEST_API_BASE
    if not TEMPEST_TOKEN:
        flash("Set TEMPEST_TOKEN in .env first", "error")
        return redirect(url_for("station_view"))
    try:
        resp = http_requests.get(
            f"{TEMPEST_API_BASE}/stations",
            params={"token": TEMPEST_TOKEN},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        stations = data.get("stations", [])
        if not stations:
            flash("No stations found for this token", "warning")
            return redirect(url_for("station_view"))

        # Auto-pick the first station
        station = stations[0]
        station_id = station.get("station_id")
        devices = station.get("devices", [])
        device_id = devices[0].get("device_id") if devices else ""
        station_name = station.get("name", "Unknown")

        # Update .env file
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        lines = []
        if os.path.exists(env_path):
            with open(env_path) as f:
                lines = f.readlines()

        new_lines = []
        keys_written = set()
        for line in lines:
            if line.startswith("TEMPEST_STATION_ID="):
                new_lines.append(f"TEMPEST_STATION_ID={station_id}\n")
                keys_written.add("TEMPEST_STATION_ID")
            elif line.startswith("TEMPEST_DEVICE_ID="):
                new_lines.append(f"TEMPEST_DEVICE_ID={device_id}\n")
                keys_written.add("TEMPEST_DEVICE_ID")
            else:
                new_lines.append(line)
        if "TEMPEST_STATION_ID" not in keys_written:
            new_lines.append(f"TEMPEST_STATION_ID={station_id}\n")
        if "TEMPEST_DEVICE_ID" not in keys_written:
            new_lines.append(f"TEMPEST_DEVICE_ID={device_id}\n")

        with open(env_path, "w") as f:
            f.writelines(new_lines)

        # Update running config
        import app.config as cfg
        cfg.TEMPEST_STATION_ID = str(station_id)
        cfg.TEMPEST_DEVICE_ID = str(device_id)
        os.environ["TEMPEST_STATION_ID"] = str(station_id)
        os.environ["TEMPEST_DEVICE_ID"] = str(device_id)

        flash(f"Found station '{station_name}' (ID: {station_id}, Device: {device_id}). "
              f".env updated — station comparison is now active!", "success")
        return redirect(url_for("station_view"))

    except Exception as e:
        flash(f"Discovery failed: {e}", "error")
        return redirect(url_for("station_view"))


@app.route("/station")
def station_view():
    if not tempest.is_configured():
        return render_template("station_setup.html",
                               has_token=bool(os.environ.get("TEMPEST_TOKEN") or
                                              __import__('app.config', fromlist=['TEMPEST_TOKEN']).TEMPEST_TOKEN))

    try:
        # Fetch Tempest observations
        obs_df = tempest.get_observation_history(days_back=2)
        if obs_df.empty:
            flash("No Tempest observations available", "warning")
            return render_template("station.html", has_data=False)

        hourly = tempest.aggregate_hourly(obs_df)

        # Fetch forecast models
        forecast_models = open_meteo.fetch_all_models(past_days=2, forecast_days=1)

        # Compare
        results = station_comparison.compare_station_to_forecasts(hourly, forecast_models)
        scores = station_comparison.compute_daily_scores(results)

        # Build charts
        temp_ts = charts.station_time_series(results, "temp")
        wind_ts = charts.station_time_series(results, "wind")
        humidity_ts = charts.station_time_series(results, "humidity")
        temp_delta = charts.station_delta_chart(results, "temp")
        wind_delta = charts.station_delta_chart(results, "wind")
        scores_chart = charts.model_scores_table(scores) if not scores.empty else None

        return render_template("station.html",
                               has_data=True,
                               temp_ts=temp_ts, wind_ts=wind_ts,
                               humidity_ts=humidity_ts,
                               temp_delta=temp_delta, wind_delta=wind_delta,
                               scores_chart=scores_chart,
                               scores=scores.to_dict("records") if not scores.empty else [])
    except Exception as e:
        flash(f"Station comparison error: {e}", "error")
        traceback.print_exc()
        return render_template("station.html", has_data=False)


# ---------- Windy Data Entry Routes ----------

@app.route("/windy", methods=["GET", "POST"])
def windy_view():
    if request.method == "POST":
        try:
            # Check if this is an OCR upload or manual entry
            use_ocr = request.form.get("use_ocr") == "1"

            screenshot_path = None
            if "screenshot" in request.files:
                f = request.files["screenshot"]
                if f.filename:
                    os.makedirs(WINDY_DIR, exist_ok=True)
                    fname = secure_filename(f.filename)
                    screenshot_path = os.path.join(WINDY_DIR, fname)
                    f.save(screenshot_path)

            if use_ocr and screenshot_path:
                # Extract data from screenshot via Claude Vision
                entry_data = windy_ocr.extract_from_image(screenshot_path)
                entry_data["screenshot"] = screenshot_path
                windy.save_windy_entry(entry_data, screenshot_path)
                n_alts = len(entry_data.get("altitudes", {}))
                n_hours = len(entry_data.get("hours", []))
                flash(f"Extracted data from screenshot: {n_alts} altitude levels, "
                      f"{n_hours} hours ({entry_data.get('date', 'unknown date')})", "success")
            else:
                entry_data = _parse_windy_form(request)
                windy.save_windy_entry(entry_data, screenshot_path)
                flash("Windy data saved", "success")

            return redirect(url_for("windy_view"))
        except Exception as e:
            flash(f"Error: {e}", "error")
            traceback.print_exc()

    entries = windy.load_windy_entries()
    ocr_available = windy_ocr.is_configured()
    return render_template("windy.html", entries=entries, ocr_available=ocr_available)


@app.route("/windy/compare/<date>")
def windy_compare(date):
    """Compare Windy data against forecast models for a given date."""
    windy_df = windy.get_windy_for_date(date)
    if windy_df.empty:
        flash("No Windy data found for this date", "warning")
        return redirect(url_for("windy_view"))

    # Fetch matching forecast data
    forecast_models = open_meteo.fetch_all_models(past_days=2, forecast_days=1)

    return render_template("windy_compare.html",
                           date=date, windy_df=windy_df,
                           forecast_models=forecast_models)


def _parse_windy_form(req):
    """Parse the Windy manual data entry form."""
    date = req.form.get("date", "")
    hours_str = req.form.get("hours", "")
    hours = [int(h.strip()) for h in hours_str.split(",") if h.strip()]

    altitudes = {}

    # Surface level (33ft / ground level)
    surface_data = {}
    for metric in ["wind_speed_mph", "wind_gust_mph", "temp_f", "dewpoint_f", "humidity_pct"]:
        vals = req.form.get(f"surface_{metric}", "")
        if vals:
            surface_data[metric] = [float(v.strip()) for v in vals.split(",") if v.strip()]
    if surface_data:
        altitudes["33ft"] = surface_data

    # Altitude levels
    for alt in [364, 1773, 2500, 3243, 4781, 6394]:
        alt_data = {}
        for metric in ["wind_speed_mph", "wind_dir"]:
            vals = req.form.get(f"alt{alt}_{metric}", "")
            if vals:
                if metric == "wind_speed_mph":
                    alt_data[metric] = [float(v.strip()) for v in vals.split(",") if v.strip()]
                else:
                    alt_data[metric] = [v.strip() for v in vals.split(",") if v.strip()]
        if alt_data:
            altitudes[f"{alt}ft"] = alt_data

    return {"date": date, "hours": hours, "altitudes": altitudes}


# ---------- API Endpoints ----------

@app.route("/api/forecast")
def api_forecast():
    """Return current forecast data as JSON."""
    try:
        models = open_meteo.fetch_all_models()
        result = {}
        for name, df in models.items():
            result[name] = json.loads(df.to_json(orient="records", date_format="iso"))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
