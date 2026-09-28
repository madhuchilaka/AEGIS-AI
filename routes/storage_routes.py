import os
from pathlib import Path
from flask import Blueprint, render_template, jsonify, request, send_from_directory, abort
from config import Config
from models import db, Event, Notification, SystemSetting
from routes import login_required, admin_required
from services.storage_service import storage_service
from services.retention_service import retention_service

storage_bp = Blueprint("storage_routes", __name__)

@storage_bp.route("/storage")
@login_required
def index():
    stats = storage_service.get_storage_statistics()
    retention_days = retention_service.get_retention_days()
    total_events = Event.query.count()
    total_notifications = Notification.query.count()

    cleanup_meta = retention_service.get_cleanup_metadata()

    return render_template(
        "storage.html",
        stats=stats,
        retention_days=retention_days,
        total_events=total_events,
        total_notifications=total_notifications,
        cleanup_meta=cleanup_meta
    )

@storage_bp.route("/api/storage/stats")
@login_required
def storage_stats():
    stats = storage_service.get_storage_statistics()
    stats["total_events"] = Event.query.count()
    stats["retention_days"] = retention_service.get_retention_days()
    return jsonify({"status": "success", "stats": stats})

@storage_bp.route("/api/cleanup", methods=["POST"])
@login_required
@admin_required
def trigger_cleanup():
    """Manual retention cleanup endpoint"""
    data = request.get_json(silent=True) or {}
    days = data.get("retention_days")
    if days is not None:
        try:
            days = int(days)
        except ValueError:
            days = None

    report = retention_service.run_cleanup(retention_days=days)
    return jsonify(report)

@storage_bp.route("/storage/<path:filename>")
@storage_bp.route("/storage/file/<path:filename>")
@login_required
def serve_storage_file(filename):
    """
    Secure file serving endpoint for snapshots and face crops.
    Verifies authentication and strictly protects against path traversal.
    """
    base_dir = Path(Config.STORAGE_DIR).resolve()
    # Normalize path and prevent directory traversal
    clean_path = (base_dir / filename).resolve()

    if not str(clean_path).startswith(str(base_dir)):
        abort(403) # Path traversal attempt

    if not clean_path.exists() or not clean_path.is_file():
        abort(404)

    rel_dir = clean_path.parent
    return send_from_directory(str(rel_dir), clean_path.name)
