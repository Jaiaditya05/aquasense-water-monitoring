"""Data Processing Module.

Handles water-quality scoring, analysis, and SQLite storage/retrieval.
"""

import os
import sqlite3
from datetime import datetime, timedelta

from config import (
    PH_WEIGHT,
    TURBIDITY_WEIGHT,
    TDS_WEIGHT,
    TEMP_WEIGHT,
    FLOW_WEIGHT,
    QUALITY_SCORE_GOOD,
    QUALITY_SCORE_FAIR,
    QUALITY_SCORE_POOR,
    LOCAL_DB_PATH,
    PH_ALERT_MIN,
    PH_ALERT_MAX,
    TURBIDITY_ALERT_THRESHOLD,
    TDS_ALERT_THRESHOLD,
    TEMP_ALERT_MIN,
    TEMP_ALERT_MAX,
)


class WaterQualityAnalyzer:
    """Analyze water-quality readings and generate scores."""

    @staticmethod
    def calculate_quality_score(reading):
        """Calculate an overall water-quality score from 0 to 100."""
        ph_score = WaterQualityAnalyzer._score_ph(reading.ph)
        turbidity_score = WaterQualityAnalyzer._score_turbidity(reading.turbidity)
        tds_score = WaterQualityAnalyzer._score_tds(reading.tds)
        temp_score = WaterQualityAnalyzer._score_temperature(reading.temperature)
        flow_score = WaterQualityAnalyzer._score_flow(reading.flow_rate)

        total_weight = (
            PH_WEIGHT + TURBIDITY_WEIGHT + TDS_WEIGHT + TEMP_WEIGHT + FLOW_WEIGHT
        )
        if total_weight <= 0:
            raise ValueError("The total water-quality scoring weight must be positive.")

        quality_score = (
            ph_score * PH_WEIGHT
            + turbidity_score * TURBIDITY_WEIGHT
            + tds_score * TDS_WEIGHT
            + temp_score * TEMP_WEIGHT
            + flow_score * FLOW_WEIGHT
        ) / total_weight
        return round(quality_score, 2)

    @staticmethod
    def _score_ph(ph):
        """Score pH level from 0 to 100."""
        if 6.5 <= ph <= 8.5:
            return 100
        if ph < 6.5:
            return max(0, 100 - (6.5 - ph) * 10)
        return max(0, 100 - (ph - 8.5) * 10)

    @staticmethod
    def _score_turbidity(turbidity):
        """Score turbidity level from 0 to 100."""
        if turbidity <= 5:
            return 100
        if turbidity <= 10:
            return 80
        if turbidity <= 20:
            return 50
        if turbidity <= 50:
            return 30
        return max(0, 100 - turbidity * 2)

    @staticmethod
    def _score_tds(tds):
        """Score total dissolved solids (ppm) from 0 to 100."""
        if tds <= 500:
            return 100
        if tds <= 750:
            return 75
        if tds <= 1000:
            return 50
        return max(0, 100 - (tds - 1000) * 0.05)

    @staticmethod
    def _score_temperature(temp):
        """Score temperature in degrees Celsius from 0 to 100."""
        if 10 <= temp <= 40:
            return 100
        if temp < 10:
            return max(0, 100 - (10 - temp) * 5)
        return max(0, 100 - (temp - 40) * 5)

    @staticmethod
    def _score_flow(flow_rate):
        """Score flow rate in L/min from 0 to 100."""
        if 0.5 <= flow_rate <= 10:
            return 100
        if flow_rate < 0.5:
            return max(0, 100 - (0.5 - flow_rate) * 50)
        return max(0, 100 - (flow_rate - 10) * 5)

    @staticmethod
    def get_status(quality_score):
        """Get a text status based on the quality score."""
        if quality_score >= QUALITY_SCORE_GOOD:
            return "Good"
        if quality_score >= QUALITY_SCORE_FAIR:
            return "Fair"
        if quality_score >= QUALITY_SCORE_POOR:
            return "Poor"
        return "Critical"

    @staticmethod
    def get_alert_message(quality_score):
        """Return a guidance message based on the quality score."""
        if quality_score >= QUALITY_SCORE_GOOD:
            return "Water quality score is good; verify against applicable safety standards."
        if quality_score >= QUALITY_SCORE_FAIR:
            return "Water quality needs monitoring."
        if quality_score >= QUALITY_SCORE_POOR:
            return "Water quality is poor; treatment is recommended."
        return "Critical water-quality score; do not use until properly assessed."


class DataStorage:
    """Handle SQLite database storage and retrieval."""

    def __init__(self, db_path=LOCAL_DB_PATH):
        # Resolve relative paths consistently and create the parent directory.
        self.db_path = os.path.abspath(os.path.expanduser(os.fspath(db_path)))
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._init_database()

    def _connect(self):
        """Open a SQLite connection, ensuring the database directory exists."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        return sqlite3.connect(self.db_path, timeout=10)

    def _init_database(self):
        """Initialize SQLite database tables."""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS readings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        ph REAL,
                        turbidity REAL,
                        tds REAL,
                        temperature REAL,
                        flow_rate REAL,
                        quality_score REAL,
                        status TEXT
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        alert_type TEXT,
                        severity TEXT,
                        message TEXT,
                        read INTEGER DEFAULT 0
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS maintenance_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        maintenance_type TEXT,
                        description TEXT,
                        duration_seconds INTEGER
                    )
                    """
                )
            print(f"[INFO] Database initialized successfully at {self.db_path}")
        except Exception as exc:
            print(f"[ERROR] Database initialization failed at {self.db_path}: {exc}")
            raise

    def save_reading(self, reading, quality_score, status):
        """Save a sensor reading to the database."""
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO readings
                    (ph, turbidity, tds, temperature, flow_rate, quality_score, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        reading.ph,
                        reading.turbidity,
                        reading.tds,
                        reading.temperature,
                        reading.flow_rate,
                        quality_score,
                        status,
                    ),
                )
            return True
        except Exception as exc:
            print(f"[ERROR] Failed to save reading: {exc}")
            return False

    def get_latest_readings(self, limit=100):
        """Retrieve the most recent readings."""
        try:
            with self._connect() as conn:
                return conn.execute(
                    "SELECT * FROM readings ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        except Exception as exc:
            print(f"[ERROR] Failed to retrieve readings: {exc}")
            return []

    def get_readings_since(self, hours=24):
        """Retrieve readings from the last number of hours."""
        try:
            time_threshold = datetime.now() - timedelta(hours=hours)
            with self._connect() as conn:
                return conn.execute(
                    """
                    SELECT * FROM readings
                    WHERE timestamp > ?
                    ORDER BY timestamp DESC
                    """,
                    (time_threshold,),
                ).fetchall()
        except Exception as exc:
            print(f"[ERROR] Failed to retrieve readings since threshold: {exc}")
            return []

    def save_alert(self, alert_type, severity, message):
        """Save an alert."""
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO alerts (alert_type, severity, message) VALUES (?, ?, ?)",
                    (alert_type, severity, message),
                )
            return True
        except Exception as exc:
            print(f"[ERROR] Failed to save alert: {exc}")
            return False

    def log_maintenance(self, maintenance_type, description, duration=0):
        """Log a maintenance activity."""
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO maintenance_log
                    (maintenance_type, description, duration_seconds)
                    VALUES (?, ?, ?)
                    """,
                    (maintenance_type, description, duration),
                )
            return True
        except Exception as exc:
            print(f"[ERROR] Failed to log maintenance: {exc}")
            return False

    def get_statistics(self, hours=24):
        """Get aggregate statistics for the last number of hours."""
        try:
            time_threshold = datetime.now() - timedelta(hours=hours)
            with self._connect() as conn:
                result = conn.execute(
                    """
                    SELECT
                        AVG(ph), MIN(ph), MAX(ph), AVG(turbidity), AVG(tds),
                        AVG(temperature), AVG(quality_score), COUNT(*)
                    FROM readings
                    WHERE timestamp > ?
                    """,
                    (time_threshold,),
                ).fetchone()

            if not result:
                return None
            return {
                "avg_ph": round(result[0], 2) if result[0] is not None else 0,
                "min_ph": round(result[1], 2) if result[1] is not None else 0,
                "max_ph": round(result[2], 2) if result[2] is not None else 0,
                "avg_turbidity": round(result[3], 2) if result[3] is not None else 0,
                "avg_tds": round(result[4], 2) if result[4] is not None else 0,
                "avg_temp": round(result[5], 2) if result[5] is not None else 0,
                "avg_quality": round(result[6], 2) if result[6] is not None else 0,
                "reading_count": result[7],
            }
        except Exception as exc:
            print(f"[ERROR] Failed to get statistics: {exc}")
            return None


if __name__ == "__main__":
    print("=" * 60)
    print("Data Processing Test")
    print("=" * 60)

    class MockReading:
        def __init__(self):
            self.ph = 7.2
            self.turbidity = 2.5
            self.tds = 300
            self.temperature = 25
            self.flow_rate = 3.5

    reading = MockReading()
    score = WaterQualityAnalyzer.calculate_quality_score(reading)
    status = WaterQualityAnalyzer.get_status(score)
    alert = WaterQualityAnalyzer.get_alert_message(score)
    print(f"\nQuality Score: {score}/100")
    print(f"Status: {status}")
    print(f"Alert: {alert}")

    storage = DataStorage()
    print(f"Latest readings: {storage.get_latest_readings(limit=5)}")
