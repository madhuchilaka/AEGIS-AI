from flask import Blueprint, render_template, Response, jsonify, request
from models import Camera, Event, db
from routes import login_required
from services.camera_service import camera_service
from services.storage_service import storage_service

monitoring_bp = Blueprint("monitoring", __name__)

@monitoring_bp.route("/monitor")
@login_required
def monitor():
    cameras = Camera.query.filter_by(enabled=True).all()
    if not cameras:
        # Provide default camera view if none in DB
        cameras = [Camera(id=1, name="Default Camera", source="0")]
    current_status = camera_service.get_status()
    return render_template("monitor.html", cameras=cameras, status=current_status)

@monitoring_bp.route("/video_feed")
@monitoring_bp.route("/video_feed/<int:camera_id>")
@login_required
def video_feed(camera_id=None):
    """Returns MJPEG multipart stream for live display, optionally for specific camera"""
    return Response(
        camera_service.generate_mjpeg_stream(camera_id=camera_id),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

@monitoring_bp.route("/api/camera/status")
@login_required
def camera_status():
    return jsonify(camera_service.get_status())

@monitoring_bp.route("/api/camera/start", methods=["POST"])
@login_required
def start_camera():
    camera_service.start_monitoring()
    return jsonify({"status": "success", "message": "Camera monitoring started", "data": camera_service.get_status()})

@monitoring_bp.route("/api/camera/stop", methods=["POST"])
@login_required
def stop_camera():
    camera_service.stop_monitoring()
    return jsonify({"status": "success", "message": "Camera monitoring stopped", "data": camera_service.get_status()})

@monitoring_bp.route("/api/camera/pause", methods=["POST"])
@login_required
def pause_camera():
    camera_service.pause_monitoring()
    return jsonify({"status": "success", "message": "Camera monitoring paused", "data": camera_service.get_status()})

@monitoring_bp.route("/api/camera/resume", methods=["POST"])
@login_required
def resume_camera():
    camera_service.resume_monitoring()
    return jsonify({"status": "success", "message": "Camera monitoring resumed", "data": camera_service.get_status()})

@monitoring_bp.route("/api/camera/snapshot", methods=["POST"])
@login_required
def take_snapshot():
    """Captures manual snapshot from live feed and saves to storage and events"""
    frame = camera_service.get_latest_frame(processed=False)
    if frame is None or frame.size == 0:
        return jsonify({"status": "error", "message": "No active camera frame available"}), 400

    try:
        rel_path = storage_service.save_snapshot(frame, prefix="manual")
        # Record manual snapshot event
        ev = Event(
            camera_id=camera_service.camera_id,
            entity_type="MANUAL_SNAPSHOT",
            entity_name="Operator Snapshot",
            recognition_status="NOT_APPLICABLE",
            event_type="MANUAL",
            direction="NONE",
            confidence=1.0,
            snapshot_path=rel_path
        )
        db.session.add(ev)
        db.session.commit()
        return jsonify({"status": "success", "message": "Snapshot saved successfully", "snapshot_path": rel_path, "event_id": ev.id})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@monitoring_bp.route("/api/camera/switch", methods=["POST"])
@login_required
def switch_camera():
    data = request.get_json() or {}
    cam_id = data.get("camera_id")
    camera = Camera.query.get(cam_id)
    if not camera:
        return jsonify({"status": "error", "message": "Camera not found"}), 404

    camera_service.configure_from_camera(camera)
    # Restart capture with new source
    was_running = camera_service.is_running
    camera_service.stop_monitoring()
    if was_running:
        camera_service.start_monitoring()

    return jsonify({"status": "success", "message": f"Switched to {camera.name}", "data": camera_service.get_status()})
