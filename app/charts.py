"""Plotly chart builders for weather comparison visualizations."""

import json
import plotly
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd


def to_json(fig):
    """Convert a Plotly figure to JSON for embedding in templates."""
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


# ---------- Drone Mission Charts ----------

def drone_altitude_profile(drone_df):
    """Plot drone altitude over time colored by temperature."""
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        subplot_titles=("Altitude Profile", "Temperature", "Wind Speed"),
        vertical_spacing=0.08,
    )

    fig.add_trace(go.Scatter(
        x=drone_df["datetime_utc"], y=drone_df["altitude_ft"],
        mode="lines", name="Altitude",
        line=dict(color="#2196F3"),
    ), row=1, col=1)

    if "sht41_temp_f" in drone_df.columns:
        fig.add_trace(go.Scatter(
            x=drone_df["datetime_utc"], y=drone_df["sht41_temp_f"],
            mode="lines", name="SHT41 Temp",
            line=dict(color="#FF5722"),
        ), row=2, col=1)

    if "sdp811_wind_mph" in drone_df.columns:
        fig.add_trace(go.Scatter(
            x=drone_df["datetime_utc"], y=drone_df["sdp811_wind_mph"],
            mode="lines", name="SDP811 Wind",
            line=dict(color="#4CAF50"),
        ), row=3, col=1)

    fig.update_layout(
        height=700, template="plotly_dark",
        title_text="Drone Mission Flight Profile",
        showlegend=True,
    )
    fig.update_yaxes(title_text="Altitude (ft)", row=1, col=1)
    fig.update_yaxes(title_text="Temp (°F)", row=2, col=1)
    fig.update_yaxes(title_text="Wind (mph)", row=3, col=1)
    return to_json(fig)


def drone_vs_forecast_temp(comparison_results, drone_binned):
    """Plot temperature: drone measured vs forecast models by altitude."""
    fig = go.Figure()

    # Drone measured temperature
    if "sht41_temp_f_mean" in drone_binned.columns:
        fig.add_trace(go.Scatter(
            x=drone_binned["sht41_temp_f_mean"],
            y=drone_binned["altitude_ft_mean"],
            mode="markers+lines",
            name="Drone (SHT41)",
            marker=dict(size=10, color="#FF5722"),
            line=dict(width=3),
            error_x=dict(
                type="data",
                array=drone_binned.get("sht41_temp_f_std", []),
                visible=True,
            ) if "sht41_temp_f_std" in drone_binned.columns else None,
        ))

    colors = ["#2196F3", "#4CAF50", "#FFC107", "#9C27B0", "#00BCD4"]
    for i, (model_name, data) in enumerate(comparison_results.items()):
        profile = data["forecast_profile"]
        color = colors[i % len(colors)]
        fig.add_trace(go.Scatter(
            x=profile["temp_f"],
            y=profile["altitude_ft"],
            mode="markers+lines",
            name=model_name,
            marker=dict(size=7, color=color),
            line=dict(width=2, dash="dash", color=color),
        ))

    fig.update_layout(
        title="Temperature vs Altitude: Drone vs Forecast Models",
        xaxis_title="Temperature (°F)",
        yaxis_title="Altitude (ft)",
        height=500, template="plotly_dark",
    )
    return to_json(fig)


def drone_vs_forecast_wind(comparison_results, drone_binned):
    """Plot wind speed: drone measured vs forecast models by altitude."""
    fig = go.Figure()

    if "sdp811_wind_mph_mean" in drone_binned.columns:
        fig.add_trace(go.Scatter(
            x=drone_binned["sdp811_wind_mph_mean"],
            y=drone_binned["altitude_ft_mean"],
            mode="markers+lines",
            name="Drone (SDP811)",
            marker=dict(size=10, color="#4CAF50"),
            line=dict(width=3),
        ))

    colors = ["#2196F3", "#FF5722", "#FFC107", "#9C27B0", "#00BCD4"]
    for i, (model_name, data) in enumerate(comparison_results.items()):
        profile = data["forecast_profile"]
        color = colors[i % len(colors)]
        valid = profile.dropna(subset=["wind_speed_mph"])
        fig.add_trace(go.Scatter(
            x=valid["wind_speed_mph"],
            y=valid["altitude_ft"],
            mode="markers+lines",
            name=model_name,
            marker=dict(size=7, color=color),
            line=dict(width=2, dash="dash", color=color),
        ))

    fig.update_layout(
        title="Wind Speed vs Altitude: Drone vs Forecast Models",
        xaxis_title="Wind Speed (mph)",
        yaxis_title="Altitude (ft)",
        height=500, template="plotly_dark",
    )
    return to_json(fig)


def drone_vs_forecast_humidity(comparison_results, drone_binned):
    """Plot humidity: drone measured vs forecast models by altitude."""
    fig = go.Figure()

    if "sht41_humidity_pct_mean" in drone_binned.columns:
        fig.add_trace(go.Scatter(
            x=drone_binned["sht41_humidity_pct_mean"],
            y=drone_binned["altitude_ft_mean"],
            mode="markers+lines",
            name="Drone (SHT41)",
            marker=dict(size=10, color="#00BCD4"),
            line=dict(width=3),
        ))

    colors = ["#2196F3", "#FF5722", "#FFC107", "#9C27B0", "#4CAF50"]
    for i, (model_name, data) in enumerate(comparison_results.items()):
        profile = data["forecast_profile"]
        color = colors[i % len(colors)]
        valid = profile.dropna(subset=["humidity_pct"])
        if not valid.empty:
            fig.add_trace(go.Scatter(
                x=valid["humidity_pct"],
                y=valid["altitude_ft"],
                mode="markers+lines",
                name=model_name,
                marker=dict(size=7, color=color),
                line=dict(width=2, dash="dash", color=color),
            ))

    fig.update_layout(
        title="Humidity vs Altitude: Drone vs Forecast Models",
        xaxis_title="Relative Humidity (%)",
        yaxis_title="Altitude (ft)",
        height=500, template="plotly_dark",
    )
    return to_json(fig)


def model_scores_table(scores_df):
    """Create a styled comparison table of model accuracy scores."""
    fig = go.Figure(data=[go.Table(
        header=dict(
            values=[c.replace("_", " ").title() for c in scores_df.columns],
            fill_color="#1a237e",
            font=dict(color="white", size=12),
            align="center",
        ),
        cells=dict(
            values=[scores_df[col].apply(lambda x: f"{x:.2f}" if isinstance(x, float) else x)
                    for col in scores_df.columns],
            fill_color="#263238",
            font=dict(color="white", size=11),
            align="center",
        ),
    )])
    fig.update_layout(height=250, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
    return to_json(fig)


# ---------- Station Comparison Charts ----------

def station_time_series(comparison_results, metric="temp"):
    """Plot station observations vs forecast models over time.

    metric: 'temp', 'wind', 'gust', 'humidity', 'wind_dir'
    """
    metric_config = {
        "temp": {
            "obs_col": "obs_temp_f", "fc_col": "fc_temp_f",
            "title": "Temperature (°F)", "unit": "°F",
        },
        "wind": {
            "obs_col": "obs_wind_mph", "fc_col": "fc_wind_mph",
            "title": "Wind Speed (mph)", "unit": "mph",
        },
        "gust": {
            "obs_col": "obs_gust_mph", "fc_col": "fc_gust_mph",
            "title": "Wind Gusts (mph)", "unit": "mph",
        },
        "humidity": {
            "obs_col": "obs_humidity_pct", "fc_col": "fc_humidity_pct",
            "title": "Relative Humidity (%)", "unit": "%",
        },
        "wind_dir": {
            "obs_col": "obs_wind_dir", "fc_col": "fc_wind_dir",
            "title": "Wind Direction (°)", "unit": "°",
        },
    }

    cfg = metric_config.get(metric, metric_config["temp"])
    fig = go.Figure()

    # Plot observations once (from first model's comparison)
    obs_plotted = False
    colors = ["#2196F3", "#4CAF50", "#FFC107", "#9C27B0", "#00BCD4"]

    for i, (model_name, comp) in enumerate(comparison_results.items()):
        if not obs_plotted and cfg["obs_col"] in comp.columns:
            fig.add_trace(go.Scatter(
                x=comp["time"], y=comp[cfg["obs_col"]],
                mode="lines+markers",
                name="Tempest Station",
                line=dict(color="#FF5722", width=3),
                marker=dict(size=6),
            ))
            obs_plotted = True

        if cfg["fc_col"] in comp.columns:
            color = colors[i % len(colors)]
            fig.add_trace(go.Scatter(
                x=comp["time"], y=comp[cfg["fc_col"]],
                mode="lines",
                name=model_name,
                line=dict(color=color, width=2, dash="dash"),
            ))

    fig.update_layout(
        title=f"Station vs Forecasts: {cfg['title']}",
        xaxis_title="Time (UTC)",
        yaxis_title=f"{cfg['title']}",
        height=400, template="plotly_dark",
    )
    return to_json(fig)


def station_delta_chart(comparison_results, metric="temp"):
    """Plot forecast errors (deltas) over time per model."""
    delta_cols = {
        "temp": "temp_delta_f",
        "wind": "wind_delta_mph",
        "gust": "gust_delta_mph",
        "humidity": "humidity_delta_pct",
        "wind_dir": "wind_dir_delta",
    }
    col = delta_cols.get(metric, "temp_delta_f")

    fig = go.Figure()
    colors = ["#2196F3", "#4CAF50", "#FFC107", "#9C27B0", "#00BCD4"]

    fig.add_hline(y=0, line_dash="dot", line_color="white", opacity=0.5)

    for i, (model_name, comp) in enumerate(comparison_results.items()):
        if col in comp.columns:
            color = colors[i % len(colors)]
            fig.add_trace(go.Bar(
                x=comp["time"], y=comp[col],
                name=model_name,
                marker_color=color, opacity=0.7,
            ))

    fig.update_layout(
        title=f"Forecast Error (Observed - Predicted): {metric.title()}",
        xaxis_title="Time (UTC)",
        yaxis_title="Delta (Obs - Forecast)",
        barmode="group",
        height=350, template="plotly_dark",
    )
    return to_json(fig)
