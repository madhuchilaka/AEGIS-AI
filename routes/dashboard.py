from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, jsonify, request
from sqlalchemy import func, or_
from models import db, Event, Person, Camera, Notification, RestrictedZone
from routes import login_required
from services.camera_service import camera_service
from services.storage_service import storage_service

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/")
@dashboard_bp.route("/dashboard")
@login_required
def index():
    # Fetch today's summary metrics
    today_start = datetime.combine(date.today(), datetime.min.time())

    today_events_count = Event.query.filter(Event.timestamp >= today_start).count()
    known_people = Event.query.filter(Event.timestamp >= today_start, Event.entity_type == "PERSON", Event.recognition_status == "KNOWN").count()
    unknown_people = Event.query.filter(Event.timestamp >= today_start, Event.entity_type == "PERSON", Event.recognition_status == "UNKNOWN").count()
    vehicles_count = Event.query.filter(Event.timestamp >= today_start, Event.entity_type == "VEHICLE").count()
    animals_count = Event.query.filter(Event.timestamp >= today_start, Event.entity_type == "ANIMAL").count()
    
    suspicious_count = Event.query.filter(
        Event.timestamp >= today_start,
        or_(Event.event_type.like("%SUSPICIOUS%"), Event.severity == "HIGH")
    ).count()

    unauthorized_count = Event.query.filter(
        Event.timestamp >= today_start,
        or_(Event.event_type.like("%UNAUTHORIZED%"), Event.event_type.like("%RESTRICTED%"), Event.severity == "CRITICAL")
    ).count()

    # Storage statistics
    storage_stats = storage_service.get_storage_statistics()

    # Recent 15 live stream events
    recent_events = Event.query.order_by(Event.timestamp.desc()).limit(15).all()

    # Available cameras & zones
    cameras = Camera.query.all()
    zones = RestrictedZone.query.all()

    return render_template(
        "dashboard.html",
        today_events=today_events_count,
        known_people=known_people,
        unknown_people=unknown_people,
        vehicles_count=vehicles_count,
        animals_count=animals_count,
        suspicious_count=suspicious_count,
        unauthorized_count=unauthorized_count,
        storage_stats=storage_stats,
        recent_events=recent_events,
        cameras=cameras,
        zones=zones,
        camera_status=camera_service.get_status()
    )

@dashboard_bp.route("/api/statistics")
@login_required
def api_statistics():
    time_range = request.args.get("range", "today").lower() # 'today', '7d', '30d'

    now = datetime.utcnow()
    if time_range == "7d":
        start_time = now - timedelta(days=7)
    elif time_range == "30d":
        start_time = now - timedelta(days=30)
    else: # today
        start_time = datetime.combine(date.today(), datetime.min.time())

    query = Event.query.filter(Event.timestamp >= start_time)

    total_events = query.count()
    known_people = query.filter(Event.entity_type == "PERSON", Event.recognition_status == "KNOWN").count()
    unknown_people = query.filter(Event.entity_type == "PERSON", Event.recognition_status == "UNKNOWN").count()
    vehicles_count = query.filter(Event.entity_type == "VEHICLE").count()
    animals_count = query.filter(Event.entity_type == "ANIMAL").count()

    suspicious_count = query.filter(
        or_(Event.event_type.like("%SUSPICIOUS%"), Event.severity == "HIGH")
    ).count()

    unauthorized_count = query.filter(
        or_(Event.event_type.like("%UNAUTHORIZED%"), Event.event_type.like("%RESTRICTED%"), Event.severity == "CRITICAL")
    ).count()

    entries_count = query.filter(Event.direction == "ENTRY").count()
    exits_count = query.filter(Event.direction == "EXIT").count()

    # Timeline Chart computation
    chart_labels = []
    chart_data = []

    if time_range == "today":
        hourly_counts = {f"{h:02d}:00": 0 for h in range(24)}
        for ev in query.all():
            h_key = ev.timestamp.strftime("%H:00")
            if h_key in hourly_counts:
                hourly_counts[h_key] += 1
        chart_labels = list(hourly_counts.keys())
        chart_data = list(hourly_counts.values())
    else:
        days_num = 7 if time_range == "7d" else 30
        daily_counts = {}
        for d in range(days_num, -1, -1):
            day_str = (now - timedelta(days=d)).strftime("%b %d")
            daily_counts[day_str] = 0
        for ev in query.all():
            d_key = ev.timestamp.strftime("%b %d")
            if d_key in daily_counts:
                daily_counts[d_key] += 1
        chart_labels = list(daily_counts.keys())
        chart_data = list(daily_counts.values())

    # Camera Activity Breakdown
    camera_counts = {}
    cameras = Camera.query.all()
    for c in cameras:
        camera_counts[c.name] = query.filter(Event.camera_id == c.id).count()

    storage_stats = storage_service.get_storage_statistics()
    recent_events = [e.to_dict() for e in Event.query.order_by(Event.timestamp.desc()).limit(12).all()]

    return jsonify({
        "status": "success",
        "range": time_range,
        "metrics": {
            "total_events": total_events,
            "known_people": known_people,
            "unknown_people": unknown_people,
            "vehicles": vehicles_count,
            "animals": animals_count,
            "suspicious_events": suspicious_count,
            "unauthorized_entries": unauthorized_count,
            "storage_used_mb": storage_stats["total_size_mb"]
        },
        "trends": {
            "today_events_label": f"+{total_events} today" if time_range == "today" else f"+{total_events} total",
            "known_trend": f"{known_people} recognized",
            "unknown_trend": f"{unknown_people} new faces",
            "unauth_trend": f"{unauthorized_count} breaches",
            "suspicious_trend": f"{suspicious_count} alerts"
        },
        "charts": {
            "timeline": {
                "labels": chart_labels,
                "data": chart_data
            },
            "recognition": {
                "labels": ["Known Individuals", "Unknown / Visitors"],
                "data": [known_people, unknown_people]
            },
            "entities": {
                "labels": ["People", "Vehicles", "Animals", "Other"],
                "data": [
                    known_people + unknown_people,
                    vehicles_count,
                    animals_count,
                    max(0, total_events - (known_people + unknown_people + vehicles_count + animals_count))
                ]
            },
            "flow": {
                "labels": ["Entries", "Exits"],
                "data": [entries_count, exits_count]
            },
            "security": {
                "labels": ["Standard Clear", "Suspicious Activity", "Unauthorized Entries"],
                "data": [
                    max(0, total_events - (suspicious_count + unauthorized_count)),
                    suspicious_count,
                    unauthorized_count
                ]
            },
            "cameras": {
                "labels": list(camera_counts.keys()),
                "data": list(camera_counts.values())
            }
        },
        "storage": storage_stats,
        "recent_events": recent_events,
        "camera_status": camera_service.get_status()
    })
