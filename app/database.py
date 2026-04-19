"""SQLite database for persisting comparison results and history."""

import sqlite3
import os
import json
from datetime import datetime
from app.config import DB_PATH


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS drone_missions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_name TEXT NOT NULL,
            filename TEXT NOT NULL,
            upload_time TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            max_altitude_ft REAL,
            latitude REAL,
            longitude REAL,
            total_readings INTEGER,
            summary_json TEXT
        );

        CREATE TABLE IF NOT EXISTS drone_comparisons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id INTEGER REFERENCES drone_missions(id),
            model_name TEXT NOT NULL,
            comparison_json TEXT NOT NULL,
            scores_json TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS station_comparisons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            model_name TEXT NOT NULL,
            comparison_json TEXT NOT NULL,
            scores_json TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS windy_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            data_json TEXT NOT NULL,
            screenshot_path TEXT,
            created_at TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def save_drone_mission(mission_name, filename, summary):
    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO drone_missions
           (mission_name, filename, upload_time, start_time, end_time,
            max_altitude_ft, latitude, longitude, total_readings, summary_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            mission_name, filename, datetime.utcnow().isoformat(),
            str(summary.get("start_time", "")),
            str(summary.get("end_time", "")),
            summary.get("max_altitude_ft"),
            summary.get("latitude"),
            summary.get("longitude"),
            summary.get("total_readings"),
            json.dumps(summary, default=str),
        )
    )
    conn.commit()
    mission_id = cursor.lastrowid
    conn.close()
    return mission_id


def save_drone_comparison(mission_id, model_name, comparison_df, scores):
    conn = get_db()
    conn.execute(
        """INSERT INTO drone_comparisons
           (mission_id, model_name, comparison_json, scores_json, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            mission_id, model_name,
            comparison_df.to_json(orient="records", default_handler=str),
            json.dumps(scores, default=str),
            datetime.utcnow().isoformat(),
        )
    )
    conn.commit()
    conn.close()


def save_station_comparison(date_str, model_name, comparison_df, scores):
    conn = get_db()
    conn.execute(
        """INSERT INTO station_comparisons
           (date, model_name, comparison_json, scores_json, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            date_str, model_name,
            comparison_df.to_json(orient="records", default_handler=str),
            json.dumps(scores, default=str),
            datetime.utcnow().isoformat(),
        )
    )
    conn.commit()
    conn.close()


def get_drone_missions():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM drone_missions ORDER BY upload_time DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_drone_comparison(mission_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM drone_comparisons WHERE mission_id = ?", (mission_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_station_comparisons(date_str=None):
    conn = get_db()
    if date_str:
        rows = conn.execute(
            "SELECT * FROM station_comparisons WHERE date = ? ORDER BY created_at DESC",
            (date_str,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM station_comparisons ORDER BY date DESC, created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
