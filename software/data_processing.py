# Data Processing Module
# Handles quality scoring, analysis, and reporting

import os
from datetime import datetime, timedelta
from config import (
    TURBIDITY_WEIGHT,
    TDS_WEIGHT,
    TEMP_WEIGHT,
    QUALITY_SCORE_GOOD,
    QUALITY_SCORE_FAIR,
    QUALITY_SCORE_POOR,
)


class WaterQualityAnalyzer:
    """Analyze supported AquaSense measurements: turbidity, TDS and temperature."""

    @staticmethod
    def calculate_quality_score(reading):
        """Calculate an indicative score using available sensor readings only.

        Missing measurements are excluded from the weighted average. This is a
        prototype indicator, not a drinking-water safety certification.
        """
        measurements = (
            ("turbidity", TURBIDITY_WEIGHT, WaterQualityAnalyzer._score_turbidity),
            ("tds", TDS_WEIGHT, WaterQualityAnalyzer._score_tds),
            ("temperature", TEMP_WEIGHT, WaterQualityAnalyzer._score_temperature),
        )

        available_scores = []
        for attribute, weight, scorer in measurements:
            value = getattr(reading, attribute, None)
            if value is None or weight <= 0:
                continue
            available_scores.append((scorer(float(value)), weight))

        if not available_scores:
            return None

        total_weight = sum(weight for _, weight in available_scores)
        weighted_score = sum(score * weight for score, weight in available_scores)
        return round(weighted_score / total_weight, 2)

    @staticmethod
    def _score_turbidity(turbidity):
        """Indicative turbidity score (0-100); assumes calibrated NTU input."""
        if turbidity <= 5:
            return 100
        elif turbidity <= 10:
            return 80
        elif turbidity <= 20:
            return 50
        elif turbidity <= 50:
            return 30
        return max(0, 100 - turbidity * 2)

    @staticmethod
    def _score_tds(tds):
        """Indicative TDS score (0-100), with TDS in ppm."""
        if tds <= 500:
            return 100
        elif tds <= 750:
            return 75
        elif tds <= 1000:
            return 50
        return max(0, 100 - (tds - 1000) * 0.05)

    @staticmethod
    def _score_temperature(temp):
        """Indicative temperature score (0-100), in degrees Celsius."""
        if 10 <= temp <= 40:
            return 100
        elif temp < 10:
            return max(0, 100 - (10 - temp) * 5)
        return max(0, 100 - (temp - 40) * 5)

    @staticmethod
    def get_status(quality_score):
        """Return INCOMPLETE when no supported measurements are available."""
        if quality_score is None:
            return "INCOMPLETE"
        if quality_score >= QUALITY_SCORE_GOOD:
            return "Good"
        elif quality_score >= QUALITY_SCORE_FAIR:
            return "Fair"
        elif quality_score >= QUALITY_SCORE_POOR:
            return "Poor"
        return "Critical"

    @staticmethod
    def get_alert_message(quality_score):
        """Describe the prototype score without certifying water as safe."""
        if quality_score is None:
            return "Waiting for supported sensor measurements"
        if quality_score >= QUALITY_SCORE_GOOD:
            return "Indicative sensor readings are within configured target ranges"
        elif quality_score >= QUALITY_SCORE_FAIR:
            return "Water-quality readings should be monitored"
        elif quality_score >= QUALITY_SCORE_POOR:
            return "Readings indicate that treatment may be required"
        return "Critical sensor readings: investigate before use"



class DataStorage:
    """PostgreSQL-backed storage for AquaSense water-quality data."""

    def __init__(self, db_path=None):
        import os
        import psycopg

        self.database_url = os.environ.get("DATABASE_URL")

        if not self.database_url:
            raise RuntimeError(
                "DATABASE_URL is missing. Add your PostgreSQL connection "
                "string to the environment variables."
            )

        self.psycopg = psycopg
        self._init_database()

    def _init_database(self):
        with self.psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS readings (
                        id BIGSERIAL PRIMARY KEY,
                        timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        ph DOUBLE PRECISION,
                        turbidity DOUBLE PRECISION,
                        tds DOUBLE PRECISION,
                        temperature DOUBLE PRECISION,
                        flow_rate DOUBLE PRECISION,
                        quality_score DOUBLE PRECISION,
                        status TEXT
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS alerts (
                        id BIGSERIAL PRIMARY KEY,
                        timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        alert_type TEXT,
                        severity TEXT,
                        message TEXT,
                        read INTEGER DEFAULT 0
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS maintenance_log (
                        id BIGSERIAL PRIMARY KEY,
                        timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        maintenance_type TEXT,
                        description TEXT,
                        duration_seconds INTEGER
                    )
                """)

    def save_reading(self, reading, quality_score, status):
        with self.psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO readings (
                        ph, turbidity, tds, temperature,
                        flow_rate, quality_score, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    getattr(reading, "ph", None),
                    getattr(reading, "turbidity", None),
                    getattr(reading, "tds", None),
                    getattr(reading, "temperature", None),
                    getattr(reading, "flow_rate", None),
                    quality_score,
                    status
                ))

    def get_latest_readings(self, limit=100):
        with self.psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, ph, turbidity, tds, temperature,
                           flow_rate, quality_score, status
                    FROM readings
                    ORDER BY timestamp DESC
                    LIMIT %s
                """, (limit,))
                return cursor.fetchall()

    def get_readings_since(self, hours=24):
        from datetime import datetime, timedelta

        cutoff = datetime.now() - timedelta(hours=hours)

        with self.psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, ph, turbidity, tds, temperature,
                           flow_rate, quality_score, status
                    FROM readings
                    WHERE timestamp >= %s
                    ORDER BY timestamp DESC
                """, (cutoff,))
                return cursor.fetchall()

    def save_alert(self, alert_type, severity, message):
        with self.psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO alerts (alert_type, severity, message)
                    VALUES (%s, %s, %s)
                """, (alert_type, severity, message))

    def log_maintenance(
        self, maintenance_type, description, duration=0
    ):
        with self.psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO maintenance_log (
                        maintenance_type, description, duration_seconds
                    )
                    VALUES (%s, %s, %s)
                """, (maintenance_type, description, duration))

    def get_statistics(self, hours=24):
        """Return statistics for supported measurements only."""
        readings = self.get_readings_since(hours)

        if not readings:
            return {
                "count": 0,
                "avg_turbidity": None,
                "avg_tds": None,
                "avg_temperature": None,
            }

        def average(column_index):
            values = [row[column_index] for row in readings
                      if row[column_index] is not None]
            return sum(values) / len(values) if values else None

        # Existing table order is:
        # id, timestamp, ph, turbidity, tds, temperature, flow_rate,
        # quality_score, status.
        return {
            "count": len(readings),
            "avg_turbidity": average(3),
            "avg_tds": average(4),
            "avg_temperature": average(5),
        }
