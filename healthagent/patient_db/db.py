"""SQLite persistence for patient profiles, daily records and simulation runs.

The database location is configurable via ``REHEALTH_DB_PATH`` and defaults to
``~/.rehealth/patients.db``.  (v0.1 hard-coded an author-local Windows path,
which meant the API could only ever run on its author's laptop.)

This module stores **synthetic / test data only**.  It is not encrypted and has
no access control of its own - do not point it at real patient data without
adding encryption, authentication and audit logging first.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFAULT_DB_PATH = Path.home() / ".rehealth" / "patients.db"
_SCHEMA_VERSION = 1
_init_lock = threading.Lock()
_initialised_paths: set[str] = set()


def db_path() -> Path:
    """Resolve the database path (``REHEALTH_DB_PATH`` overrides the default)."""
    configured = os.getenv("REHEALTH_DB_PATH")
    return Path(configured).expanduser() if configured else _DEFAULT_DB_PATH


def _get_conn() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(force: bool = False) -> Path:
    """Create the schema if needed.  Safe to call repeatedly."""
    path = db_path()
    key = str(path)
    with _init_lock:
        if not force and key in _initialised_paths and path.exists():
            return path
        conn = _get_conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS patients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    age INTEGER,
                    gender TEXT DEFAULT 'unknown',
                    bmi REAL DEFAULT 22.0,
                    height REAL DEFAULT 0.0,
                    weight REAL DEFAULT 0.0,
                    stress_level TEXT DEFAULT 'medium',
                    sleep_hours REAL DEFAULT 7.0,
                    primary_issue TEXT DEFAULT '',
                    medical_history TEXT DEFAULT '',
                    systolic_bp INTEGER DEFAULT 120,
                    diastolic_bp INTEGER DEFAULT 80,
                    fasting_glucose REAL DEFAULT 5.0,
                    postprandial_glucose REAL DEFAULT 7.0,
                    created_at TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS daily_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL,
                    record_date TEXT NOT NULL,
                    systolic_bp INTEGER,
                    diastolic_bp INTEGER,
                    fasting_glucose REAL,
                    postprandial_glucose REAL,
                    weight REAL,
                    bmi REAL,
                    steps INTEGER,
                    exercise_minutes INTEGER,
                    mood_score INTEGER,
                    sleep_hours REAL,
                    notes TEXT DEFAULT '',
                    FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_daily_records_patient_date
                    ON daily_records(patient_id, record_date DESC);

                CREATE TABLE IF NOT EXISTS simulations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER,
                    run_at TEXT,
                    days INTEGER,
                    mode TEXT,
                    seed INTEGER,
                    params TEXT,
                    result TEXT,
                    FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_simulations_patient
                    ON simulations(patient_id, run_at DESC);

                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
                (str(_SCHEMA_VERSION),),
            )
            conn.commit()
        finally:
            conn.close()
        _initialised_paths.add(key)
    return path


# --------------------------------------------------------------------- patients
def add_patient(
    name: str,
    age: int,
    gender: str = "unknown",
    bmi: float = 22.0,
    stress_level: str = "medium",
    sleep_hours: float = 7.0,
    primary_issue: str = "",
    medical_history: str = "",
    height: float = 0.0,
    weight: float = 0.0,
    systolic_bp: int = 120,
    diastolic_bp: int = 80,
    fasting_glucose: float = 5.0,
    postprandial_glucose: float = 7.0,
) -> Dict[str, Any]:
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _get_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO patients
               (name, age, gender, bmi, height, weight, stress_level, sleep_hours,
                primary_issue, medical_history, systolic_bp, diastolic_bp,
                fasting_glucose, postprandial_glucose, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                name, age, gender, bmi, height, weight, stress_level, sleep_hours,
                primary_issue, medical_history, systolic_bp, diastolic_bp,
                fasting_glucose, postprandial_glucose, now, now,
            ),
        )
        conn.commit()
        patient_id = cursor.lastrowid
    finally:
        conn.close()
    return {
        "status": "ok",
        "patient_id": patient_id,
        "id": patient_id,  # alias, so create/list shapes match
        "message": f"patient {name!r} created with id={patient_id}",
    }


def list_patients(limit: int = 200) -> List[Dict[str, Any]]:
    init_db()
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT id, name, age, gender, bmi, stress_level, sleep_hours,
                      primary_issue, systolic_bp, diastolic_bp, fasting_glucose,
                      created_at
               FROM patients ORDER BY id DESC LIMIT ?""",
            (int(limit),),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def get_patient(patient_id: int) -> Dict[str, Any]:
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return {"error": f"patient id={patient_id} not found"}
    return dict(row)


# ---------------------------------------------------------------- daily records
def add_daily_record(
    patient_id: int,
    record_date: Optional[str] = None,
    systolic_bp: Optional[int] = None,
    diastolic_bp: Optional[int] = None,
    fasting_glucose: Optional[float] = None,
    postprandial_glucose: Optional[float] = None,
    weight: Optional[float] = None,
    bmi: Optional[float] = None,
    steps: Optional[int] = None,
    exercise_minutes: Optional[int] = None,
    mood_score: Optional[int] = None,
    sleep_hours: Optional[float] = None,
    notes: str = "",
) -> Dict[str, Any]:
    init_db()
    if record_date is None:
        record_date = datetime.now().strftime("%Y-%m-%d")
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO daily_records
               (patient_id, record_date, systolic_bp, diastolic_bp, fasting_glucose,
                postprandial_glucose, weight, bmi, steps, exercise_minutes,
                mood_score, sleep_hours, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                patient_id, record_date, systolic_bp, diastolic_bp, fasting_glucose,
                postprandial_glucose, weight, bmi, steps, exercise_minutes,
                mood_score, sleep_hours, notes,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "ok", "message": f"record for patient {patient_id} on {record_date} saved"}


def get_daily_records(patient_id: int, days: int = 30) -> List[Dict[str, Any]]:
    init_db()
    days = max(1, min(int(days), 3650))
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM daily_records WHERE patient_id=?
               ORDER BY record_date DESC LIMIT ?""",
            (patient_id, days),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def _bp_status(systolic: int, diastolic: int) -> str:
    if systolic < 120 and diastolic < 80:
        return "normal"
    if systolic < 130 and diastolic < 80:
        return "elevated"
    if systolic < 140 or diastolic < 90:
        return "stage_1_hypertension"
    return "stage_2_hypertension"


def _glucose_status(fasting: float) -> str:
    if fasting < 6.1:
        return "normal"
    if fasting < 7.0:
        return "impaired_fasting_glucose"
    return "diabetes_range"


def _mood_status(score: float) -> str:
    if score >= 8:
        return "good"
    if score >= 6:
        return "fair"
    if score >= 4:
        return "low"
    return "very_low"


def get_health_trend(patient_id: int) -> Dict[str, Any]:
    init_db()
    records = get_daily_records(patient_id, days=30)
    if not records:
        return {"error": "no records for this patient"}

    bp = [r for r in records if r["systolic_bp"]]
    glucose = [r for r in records if r["fasting_glucose"]]
    weight = [r for r in records if r["weight"]]
    steps = [r for r in records if r["steps"]]
    mood = [r for r in records if r["mood_score"]]

    trend: Dict[str, Any] = {"patient_id": patient_id, "record_count": len(records)}
    if bp:
        trend["blood_pressure"] = {
            "latest": f"{bp[0]['systolic_bp']}/{bp[0]['diastolic_bp']} mmHg",
            "avg_systolic": round(sum(r["systolic_bp"] for r in bp) / len(bp), 1),
            "avg_diastolic": round(sum(r["diastolic_bp"] for r in bp) / len(bp), 1),
            "status": _bp_status(bp[0]["systolic_bp"], bp[0]["diastolic_bp"]),
        }
    if glucose:
        trend["glucose"] = {
            "latest_fasting": f"{glucose[0]['fasting_glucose']} mmol/L",
            "avg_fasting": round(
                sum(r["fasting_glucose"] for r in glucose) / len(glucose), 2
            ),
            "status": _glucose_status(glucose[0]["fasting_glucose"]),
        }
    if weight:
        trend["weight"] = {
            "latest": f"{weight[0]['weight']} kg",
            "change": round(weight[0]["weight"] - weight[-1]["weight"], 1),
        }
    if steps:
        avg_steps = round(sum(r["steps"] for r in steps) / len(steps))
        trend["activity"] = {
            "avg_steps": avg_steps,
            "status": "on_target" if avg_steps >= 8000 else "below_target",
        }
    if mood:
        avg_mood = round(sum(r["mood_score"] for r in mood) / len(mood), 1)
        trend["mood"] = {"avg_score": avg_mood, "status": _mood_status(avg_mood)}
    return trend


# ------------------------------------------------------------------- simulations
def save_simulation(
    patient_id: int,
    days: int,
    params: Dict[str, Any],
    result: Dict[str, Any],
    mode: Optional[str] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode = mode or (result.get("meta", {}) or {}).get("mode")
    seed = seed if seed is not None else (result.get("meta", {}) or {}).get("seed")
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO simulations (patient_id, run_at, days, mode, seed, params, result)
               VALUES (?,?,?,?,?,?,?)""",
            (
                patient_id,
                now,
                days,
                mode,
                seed,
                json.dumps(params, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "ok", "message": f"simulation saved for patient {patient_id}"}


def get_patient_history(patient_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    init_db()
    limit = max(1, min(int(limit), 500))
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT id, run_at, days, mode, seed, params, result
               FROM simulations WHERE patient_id=? ORDER BY run_at DESC LIMIT ?""",
            (patient_id, limit),
        ).fetchall()
    finally:
        conn.close()

    history: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["params"] = json.loads(item["params"]) if item["params"] else None
        item["result"] = json.loads(item["result"]) if item["result"] else None
        history.append(item)
    return history
