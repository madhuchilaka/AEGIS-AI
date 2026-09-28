import json
import time
from flask import Blueprint, render_template, jsonify, Response, request
from models import db, Notification
from routes import login_required
from services.notification_service import notification_service

notifications_bp = Blueprint("notifications", __name__)

@notifications_bp.route("/notifications")
@login_required
def index():
    category = request.args.get("category", "ALL").upper()
    query = Notification.query.order_by(Notification.created_at.desc())

    if category != "ALL":
        query = query.filter_by(category=category)

    notifications = query.limit(100).all()

    # Category counts
    counts = {
        "ALL": Notification.query.count(),
        "CRITICAL": Notification.query.filter_by(severity="critical").count(),
        "UNAUTHORIZED": Notification.query.filter_by(category="UNAUTHORIZED").count(),
        "SUSPICIOUS": Notification.query.filter_by(category="SUSPICIOUS").count(),
        "KNOWN": Notification.query.filter_by(category="KNOWN").count(),
        "SYSTEM": Notification.query.filter_by(category="SYSTEM").count()
    }

    return render_template(
        "notifications.html",
        notifications=notifications,
        active_category=category,
        counts=counts
    )

@notifications_bp.route("/api/notifications", methods=["GET"])
@login_required
def get_notifications():
    unread_only = request.args.get("unread_only", "false").lower() == "true"
    category = request.args.get("category", "ALL")
    limit = request.args.get("limit", 50, type=int)
    notifs = notification_service.get_recent(limit=limit, unread_only=unread_only, category=category)
    return jsonify({
        "status": "success",
        "notifications": notifs,
        "unread_count": notification_service.get_unread_count()
    })

@notifications_bp.route("/api/notifications/<int:id>/read", methods=["POST"])
@login_required
def mark_read(id):
    success = notification_service.mark_as_read(id)
    return jsonify({"status": "success" if success else "error"})

@notifications_bp.route("/api/notifications/<int:id>/acknowledge", methods=["POST"])
@login_required
def acknowledge(id):
    success = notification_service.acknowledge_notification(id)
    return jsonify({"status": "success" if success else "error"})

@notifications_bp.route("/api/notifications/read-all", methods=["POST"])
@login_required
def mark_all_read():
    count = notification_service.mark_all_as_read()
    return jsonify({"status": "success", "marked_count": count})

@notifications_bp.route("/api/notifications/stream")
@login_required
def sse_stream():
    """Server-Sent Events endpoint for real-time notification push to frontend"""
    q = notification_service.subscribe()

    def event_stream():
        try:
            # Send initial keepalive
            yield f": keepalive\n\n"
            while True:
                try:
                    # Wait up to 20 seconds for new notification
                    notif_data = q.get(timeout=20.0)
                    yield f"data: {json.dumps(notif_data)}\n\n"
                except Exception:
                    # Send periodic heartbeat so connection stays open
                    yield f": ping\n\n"
        finally:
            notification_service.unsubscribe(q)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )
