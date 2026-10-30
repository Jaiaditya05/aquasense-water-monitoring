"""AquaSense Flask application.

Receives ESP32 measurements and stores them in PostgreSQL.
Supported measurements: turbidity, TDS and temperature only.
pH and flow-rate fields are intentionally not used.
"""

import time
from datetime import datetime
from types import SimpleNamespace

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

from sensors import WaterQualitySensor
from purification import PurificationSystem, ActionRecommender
from data_processing import WaterQualityAnalyzer, DataStorage
from config import SIMULATION_MODE, SERVER_HOST, SERVER_PORT, DEBUG_MODE


app = Flask(__name__)
CORS(app)

# Existing application components
sensor = WaterQualitySensor(simulation_mode=SIMULATION_MODE)
system = PurificationSystem()
storage = DataStorage()

# ESP32 readings are stored in PostgreSQL. This variable is only a convenient
# in-process cache; the database remains the persistent source of truth.
latest_esp32_reading = None


def _row_to_reading_payload(row):
    """Convert DataStorage's current SELECT row into an API response."""
    # PostgreSQL schema returned by data_processing.py:
    # id, timestamp, ph, turbidity, tds, temperature, flow_rate,
    # quality_score, status
    return {
        "id": row[0],
        "timestamp": row[1].isoformat() if row[1] else None,
        "turbidity": row[3],
        "tds": row[4],
        "temperature": row[5],
        "quality_score": row[7],
        "status": row[8],
        "source": "ESP32",
    }


@app.route("/")
def dashboard():
    """Render the existing dashboard page."""
    reading = sensor.get_all_readings()
    quality_score = WaterQualityAnalyzer.calculate_quality_score(reading)
    status = WaterQualityAnalyzer.get_status(quality_score)
    alert = WaterQualityAnalyzer.get_alert_message(quality_score)
    action = ActionRecommender.get_recommendation(reading, quality_score)

    history_rows = storage.get_latest_readings(limit=10)
    history = []
    for row in history_rows:
        # Existing PostgreSQL schema:
        # id, timestamp, ph, turbidity, tds, temperature, flow_rate,
        # quality_score, status.
        history.append({
            "label": row[1].isoformat() if row[1] else "",
            "turbidity": row[3],
            "tds": row[4],
            "temperature": row[5],
        })

    return render_template(
        "index.html",
        reading={
            "turbidity": round(reading.turbidity, 2),
            "tds": round(reading.tds, 2),
            "temperature": round(reading.temperature, 2),
        },
        quality={
            "score": quality_score,
            "status": status,
            "alert": alert,
        },
        action=action,
        history=history,
    )


@app.route("/api/readings/latest", methods=["GET"])
def api_latest_reading():
    """Return the newest stored ESP32 reading, or a clear empty response."""
    rows = storage.get_latest_readings(limit=1)
    if not rows:
        return jsonify({
            "success": True,
            "available": False,
            "message": "No ESP32 readings have been received yet.",
            "turbidity": None,
            "tds": None,
            "temperature": None,
            "quality_score": None,
            "status": "WAITING",
            "source": None,
        })

    payload = _row_to_reading_payload(rows[0])
    payload["success"] = True
    payload["available"] = True
    return jsonify(payload)


@app.route("/api/readings", methods=["POST"])
def api_receive_reading():
    """Receive JSON readings from the ESP32 and persist them.

    At least one real measurement is required. During the first hardware
    test, the ESP32 may send temperature only. Unmeasured TDS/turbidity are
    stored as SQL NULL, never as fabricated zero readings.
    """
    global latest_esp32_reading

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({
            "success": False,
            "error": "Request body must be a JSON object.",
        }), 400

    allowed = ("turbidity", "tds", "temperature")
    supplied = {key: data[key] for key in allowed if key in data}

    if not supplied:
        return jsonify({
            "success": False,
            "error": "At least one measurement is required.",
            "accepted_fields": list(allowed),
        }), 400

    values = {}
    limits = {
        "turbidity": (0.0, 100.0),
        "tds": (0.0, 2000.0),
        "temperature": (-10.0, 60.0),
    }

    for key, raw_value in supplied.items():
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return jsonify({
                "success": False,
                "error": f"{key} must be numeric.",
            }), 400

        low, high = limits[key]
        if not low <= value <= high:
            return jsonify({
                "success": False,
                "error": f"{key} must be between {low} and {high}.",
            }), 400
        values[key] = value

    # Keep absent measurements as None so PostgreSQL stores NULL rather than
    # pretending that an unconnected sensor measured zero.
    reading = SimpleNamespace(
        turbidity=values.get("turbidity"),
        tds=values.get("tds"),
        temperature=values.get("temperature"),
        timestamp=datetime.now(),
    )

    all_measurements_present = all(
        getattr(reading, key) is not None for key in allowed
    )

    if all_measurements_present:
        quality_score = WaterQualityAnalyzer.calculate_quality_score(reading)
        status = WaterQualityAnalyzer.get_status(quality_score)
    else:
        # A partial set cannot produce a defensible overall water-quality score.
        quality_score = None
        status = "INCOMPLETE"

    try:
        storage.save_reading(reading, quality_score, status)
    except Exception as exc:
        app.logger.exception("Could not save ESP32 reading")
        return jsonify({
            "success": False,
            "error": "Could not save the reading to the database.",
        }), 500

    latest_esp32_reading = {
        **values,
        "timestamp": reading.timestamp.isoformat(),
        "source": "ESP32",
        "quality_score": quality_score,
        "status": status,
    }

    return jsonify({
        "success": True,
        "message": "ESP32 reading received and saved.",
        "reading": latest_esp32_reading,
    }), 201


@app.route("/api/status", methods=["GET"])
def api_status():
    """Return application and purification-system status."""
    health = sensor.check_sensor_health()
    system_status = system.get_system_status()

    return jsonify({
        "system_online": True,
        "pump_active": system_status["pump_active"],
        "sensor_health": health,
        "uptime_seconds": int(time.time()),
        "esp32_last_reading": latest_esp32_reading,
    })


@app.route("/api/pump/on", methods=["POST"])
def pump_on():
    """Turn on the configured pump control."""
    system.activate_pump()
    return jsonify({"success": True, "message": "Pump activated"})


@app.route("/api/pump/off", methods=["POST"])
def pump_off():
    """Turn off the configured pump control."""
    system.deactivate_pump()
    return jsonify({"success": True, "message": "Pump deactivated"})


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    print("[INFO] Starting AquaSense...")
    print(f"[INFO] Dashboard: http://{SERVER_HOST}:{SERVER_PORT}")
    print(f"[INFO] ESP32 endpoint: http://<MAC-IP>:{SERVER_PORT}/api/readings")
    app.run(
        host=SERVER_HOST,
        port=SERVER_PORT,
        debug=DEBUG_MODE,
        use_reloader=False,
    )
