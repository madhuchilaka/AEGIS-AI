from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from config import Config
from models import db, SystemSetting
from routes import login_required, admin_required
from services.camera_service import camera_service

settings_bp = Blueprint("settings", __name__)

DEFAULT_SETTINGS = {
    "DETECTION_CONFIDENCE": (str(Config.DETECTION_CONFIDENCE), "Minimum object detection confidence threshold (0.1 - 0.95)"),
    "FACE_RECOGNITION_THRESHOLD": (str(Config.FACE_RECOGNITION_THRESHOLD), "Cosine similarity threshold for matching known faces (0.2 - 0.8)"),
    "EVENT_COOLDOWN": (str(Config.EVENT_COOLDOWN), "Seconds before recording duplicate events for the same entity"),
    "RETENTION_DAYS": (str(Config.RETENTION_DAYS), "Automatic data retention lifespan in days (older snapshots purged)"),
    "FRAME_SKIP": (str(Config.FRAME_SKIP), "Process every Nth frame for computer vision (1 = full FPS, 2 = half)"),
    "LINE_POSITION": (str(Config.LINE_POSITION), "Virtual boundary line position as fraction of frame (0.1 - 0.9)"),
    "LINE_ORIENTATION": (Config.LINE_ORIENTATION, "Virtual boundary orientation ('horizontal' or 'vertical')"),
    "LOITERING_THRESHOLD": (str(Config.LOITERING_THRESHOLD), "Dwell time in seconds before triggering Suspicious Activity Loitering"),
    "REPEATED_EVENT_THRESHOLD": (str(Config.REPEATED_EVENT_THRESHOLD), "Number of appearances in 15 mins before triggering Repeated Proximity Alert"),
    "AFTER_HOURS_START": (Config.AFTER_HOURS_START, "Start of restricted night hours (HH:MM, e.g. 22:00)"),
    "AFTER_HOURS_END": (Config.AFTER_HOURS_END, "End of restricted night hours (HH:MM, e.g. 06:00)"),
    "RESTRICTED_ZONE_ENABLED": ("true" if Config.RESTRICTED_ZONE_ENABLED else "false", "Enable spatial boundary checks for restricted zones"),
    "UNAUTHORIZED_ENTRY_WORKFLOW": ("true" if Config.UNAUTHORIZED_ENTRY_WORKFLOW else "false", "Automatically capture high-res snapshots and broadcast alerts on unauthorized entry")
}

@settings_bp.route("/settings", methods=["GET", "POST"])
@login_required
@admin_required
def index():
    if request.method == "POST":
        for key in DEFAULT_SETTINGS.keys():
            if key in request.form:
                val = request.form.get(key, "").strip()
                SystemSetting.set(key, val, description=DEFAULT_SETTINGS[key][1])

        # Apply settings to active camera service
        try:
            camera_service.conf_threshold = float(SystemSetting.get("DETECTION_CONFIDENCE", Config.DETECTION_CONFIDENCE))
            camera_service.frame_skip = int(SystemSetting.get("FRAME_SKIP", Config.FRAME_SKIP))
            camera_service.line_position = float(SystemSetting.get("LINE_POSITION", Config.LINE_POSITION))
            camera_service.line_orientation = SystemSetting.get("LINE_ORIENTATION", Config.LINE_ORIENTATION)
        except Exception:
            pass

        flash("System settings successfully updated.", "success")
        return redirect(url_for("settings.index"))

    # Fetch current settings from DB or defaults
    settings_dict = {}
    for key, (default_val, desc) in DEFAULT_SETTINGS.items():
        val = SystemSetting.get(key, default_val)
        settings_dict[key] = {"value": val, "description": desc}

    return render_template("settings.html", settings=settings_dict)

@settings_bp.route("/api/settings", methods=["GET", "POST"])
@login_required
@admin_required
def api_settings():
    if request.method == "POST":
        data = request.get_json() or {}
        for key, val in data.items():
            if key in DEFAULT_SETTINGS:
                SystemSetting.set(key, str(val), description=DEFAULT_SETTINGS[key][1])
        return jsonify({"status": "success", "message": "Settings updated"})

    settings_dict = {}
    for key, (default_val, desc) in DEFAULT_SETTINGS.items():
        settings_dict[key] = SystemSetting.get(key, default_val)
    return jsonify({"status": "success", "settings": settings_dict})
