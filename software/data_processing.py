# Data Processing Module
# Handles quality scoring, analysis, and reporting

import os
from datetime import datetime, timedelta
from config import (
    PH_WEIGHT, TURBIDITY_WEIGHT, TDS_WEIGHT, TEMP_WEIGHT, FLOW_WEIGHT,
    QUALITY_SCORE_GOOD, QUALITY_SCORE_FAIR, QUALITY_SCORE_POOR,
    LOCAL_DB_PATH, PH_ALERT_MIN, PH_ALERT_MAX, TURBIDITY_ALERT_THRESHOLD,
    TDS_ALERT_THRESHOLD, TEMP_ALERT_MIN, TEMP_ALERT_MAX
)


class WaterQualityAnalyzer:
    """Analyze water quality readings and generate scores"""
    
    @staticmethod
    def calculate_quality_score(reading):
        """
        Calculate overall water quality score (0-100)
        Based on weighted parameters
        """
        
        # Calculate individual parameter scores (0-100)
        ph_score = WaterQualityAnalyzer._score_ph(reading.ph)
        turbidity_score = WaterQualityAnalyzer._score_turbidity(reading.turbidity)
        tds_score = WaterQualityAnalyzer._score_tds(reading.tds)
        temp_score = WaterQualityAnalyzer._score_temperature(reading.temperature)
        flow_score = WaterQualityAnalyzer._score_flow(reading.flow_rate)
        
        # Calculate weighted average
        total_weight = PH_WEIGHT + TURBIDITY_WEIGHT + TDS_WEIGHT + TEMP_WEIGHT + FLOW_WEIGHT
        
        quality_score = (
            (ph_score * PH_WEIGHT +
             turbidity_score * TURBIDITY_WEIGHT +
             tds_score * TDS_WEIGHT +
             temp_score * TEMP_WEIGHT +
             flow_score * FLOW_WEIGHT) / total_weight
        )
        
        return round(quality_score, 2)
    
    @staticmethod
    def _score_ph(ph):
        """Score pH level (0-100)"""
        # Ideal range: 6.5-8.5
        if 6.5 <= ph <= 8.5:
            return 100
        elif ph < 6.5:
            # Below ideal - deduct points linearly
            return max(0, 100 - (6.5 - ph) * 10)
        else:
            # Above ideal - deduct points linearly
            return max(0, 100 - (ph - 8.5) * 10)
    
    @staticmethod
    def _score_turbidity(turbidity):
        """Score turbidity level (0-100)"""
        # Ideal: < 5 NTU
        if turbidity <= 5:
            return 100
        elif turbidity <= 10:
            return 80
        elif turbidity <= 20:
            return 50
        elif turbidity <= 50:
            return 30
        else:
            return max(0, 100 - turbidity * 2)
    
    @staticmethod
    def _score_tds(tds):
        """Score TDS level (0-100) - ppm"""
        # Ideal: < 500 ppm
        if tds <= 500:
            return 100
        elif tds <= 750:
            return 75
        elif tds <= 1000:
            return 50
        else:
            return max(0, 100 - (tds - 1000) * 0.05)
    
    @staticmethod
    def _score_temperature(temp):
        """Score temperature level (0-100)"""
        # Ideal: 10-40°C
        if 10 <= temp <= 40:
            return 100
        elif temp < 10:
            return max(0, 100 - (10 - temp) * 5)
        else:
            return max(0, 100 - (temp - 40) * 5)
    
    @staticmethod
    def _score_flow(flow_rate):
        """Score flow rate (0-100) - L/min"""
        # Ideal: 0.5-10 L/min
        if 0.5 <= flow_rate <= 10:
            return 100
        elif flow_rate < 0.5:
            return max(0, 100 - (0.5 - flow_rate) * 50)
        else:
            return max(0, 100 - (flow_rate - 10) * 5)
    
    @staticmethod
    def get_status(quality_score):
        """Get quality status based on score"""
        if quality_score >= QUALITY_SCORE_GOOD:
            return 'Good'
        elif quality_score >= QUALITY_SCORE_FAIR:
            return 'Fair'
        elif quality_score >= QUALITY_SCORE_POOR:
            return 'Poor'
        else:
            return 'Critical'
    
    @staticmethod
    def get_alert_message(quality_score):
        """Get alert message based on quality score"""
        if quality_score >= QUALITY_SCORE_GOOD:
            return 'Water is safe for consumption'
        elif quality_score >= QUALITY_SCORE_FAIR:
            return 'Water quality is acceptable - Monitor closely'
        elif quality_score >= QUALITY_SCORE_POOR:
            return 'Water quality is poor - Treatment recommended'
        else:
            return 'CRITICAL - Water is unsafe - Stop usage immediately'



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
                    reading.ph,
                    reading.turbidity,
                    reading.tds,
                    reading.temperature,
                    reading.flow_rate,
                    quality_score,
                    status
                ))

    def get_latest_readings(self, limit=100):
        with self.psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM readings
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
                    SELECT * FROM readings
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
        readings = self.get_readings_since(hours)

        if not readings:
            return {
                "count": 0,
                "avg_ph": 0,
                "avg_turbidity": 0,
                "avg_tds": 0,
                "avg_temperature": 0
            }

        return {
            "count": len(readings),
            "avg_ph": sum(r[2] or 0 for r in readings) / len(readings),
            "avg_turbidity": sum(r[3] or 0 for r in readings) / len(readings),
            "avg_tds": sum(r[4] or 0 for r in readings) / len(readings),
            "avg_temperature": sum(r[5] or 0 for r in readings) / len(readings)
        }