import io
import csv
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, Response, session
from models import db, Event, Camera, Person
from routes import login_required, admin_required
from services.storage_service import storage_service

events_bp = Blueprint("events", __name__)

@events_bp.route("/events")
@login_required
def index():
    cameras = Camera.query.all()
    persons = Person.query.all()
    return render_template("events.html", cameras=cameras, persons=persons)

@events_bp.route("/events/<int:event_id>")
@login_required
def detail(event_id):
    event = Event.query.get_or_404(event_id)
    prev_event = Event.query.filter(Event.id < event_id).order_by(Event.id.desc()).first()
    next_event = Event.query.filter(Event.id > event_id).order_by(Event.id.asc()).first()
    related_events = Event.query.filter(
        Event.camera_id == event.camera_id,
        Event.id != event.id
    ).order_by(Event.timestamp.desc()).limit(6).all()

    return render_template(
        "event_detail.html",
        event=event,
        prev_event=prev_event,
        next_event=next_event,
        related_events=related_events
    )

@events_bp.route("/api/events", methods=["GET"])
@login_required
def list_events():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    per_page = min(100, max(5, per_page))

    # Filters
    query = Event.query

    date_str = request.args.get("date") # YYYY-MM-DD
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start = datetime.combine(target_date, datetime.min.time())
            end = datetime.combine(target_date, datetime.max.time())
            query = query.filter(Event.timestamp >= start, Event.timestamp <= end)
        except ValueError:
            pass

    entity_type = request.args.get("entity_type")
    if entity_type and entity_type.upper() != "ALL":
        query = query.filter(Event.entity_type == entity_type.upper())

    recognition_status = request.args.get("recognition_status")
    if recognition_status and recognition_status.upper() != "ALL":
        query = query.filter(Event.recognition_status == recognition_status.upper())

    direction = request.args.get("direction")
    if direction and direction.upper() != "ALL":
        query = query.filter(Event.direction == direction.upper())

    severity = request.args.get("severity")
    if severity and severity.upper() != "ALL":
        query = query.filter(Event.severity == severity.upper())

    event_type = request.args.get("event_type")
    if event_type and event_type.upper() != "ALL":
        query = query.filter(Event.event_type.like(f"%{event_type.upper()}%"))

    person_id = request.args.get("person_id")
    if person_id and person_id != "ALL" and person_id.isdigit():
        query = query.filter(Event.person_id == int(person_id))

    camera_id = request.args.get("camera_id")
    if camera_id and camera_id != "ALL" and camera_id.isdigit():
        query = query.filter(Event.camera_id == int(camera_id))

    min_confidence = request.args.get("confidence", type=float)
    if min_confidence:
        query = query.filter(Event.confidence >= min_confidence)

    # Sort descending
    query = query.order_by(Event.timestamp.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    events_data = [e.to_dict() for e in pagination.items]

    return jsonify({
        "status": "success",
        "events": events_data,
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev
    })

@events_bp.route("/api/events/<int:event_id>", methods=["GET"])
@login_required
def get_event(event_id):
    event = Event.query.get_or_404(event_id)
    prev_event = Event.query.filter(Event.id < event_id).order_by(Event.id.desc()).first()
    next_event = Event.query.filter(Event.id > event_id).order_by(Event.id.asc()).first()
    related = Event.query.filter(
        Event.camera_id == event.camera_id,
        Event.id != event.id
    ).order_by(Event.timestamp.desc()).limit(6).all()

    data = event.to_dict()
    data["prev_event_id"] = prev_event.id if prev_event else None
    data["next_event_id"] = next_event.id if next_event else None
    data["related_events"] = [r.to_dict() for r in related]

    return jsonify({"status": "success", "event": data})

@events_bp.route("/api/events/<int:event_id>/acknowledge", methods=["POST"])
@login_required
def acknowledge_event(event_id):
    event = Event.query.get_or_404(event_id)
    event.is_acknowledged = True
    event.acknowledged_at = datetime.utcnow()
    event.acknowledged_by = session.get("username", "Operator")

    # Mark associated notifications as read & acknowledged
    for n in event.notifications:
        n.is_acknowledged = True
        n.read_status = True

    db.session.commit()
    return jsonify({"status": "success", "message": "Event acknowledged", "event": event.to_dict()})

@events_bp.route("/api/events/<int:event_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_event(event_id):
    event = Event.query.get_or_404(event_id)
    if event.snapshot_path:
        storage_service.delete_file(event.snapshot_path)
    db.session.delete(event)
    db.session.commit()
    return jsonify({"status": "success", "message": "Event deleted successfully"})

@events_bp.route("/events/export/csv")
@login_required
def export_events_csv():
    """Generates and streams a CSV report of recent security events"""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Event ID", "Timestamp", "Camera", "Entity Type", "Entity Name",
        "Recognition Status", "Event Category", "Direction", "Confidence", "Severity", "Zone", "Snapshot Path"
    ])

    events = Event.query.order_by(Event.timestamp.desc()).limit(1000).all()
    for ev in events:
        cam_name = ev.camera.name if ev.camera else "Camera #1"
        writer.writerow([
            ev.id,
            ev.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            cam_name,
            ev.entity_type,
            ev.entity_name,
            ev.recognition_status,
            ev.event_type,
            ev.direction,
            f"{int(ev.confidence * 100)}%",
            ev.severity or "INFO",
            ev.zone_name or "Premises Area",
            ev.snapshot_path or ""
        ])

    output.seek(0)
    filename = f"security_events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
