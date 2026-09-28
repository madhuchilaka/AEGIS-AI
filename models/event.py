from datetime import datetime
from . import db

class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    camera_id = db.Column(db.Integer, db.ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True, index=True)
    person_id = db.Column(db.Integer, db.ForeignKey("persons.id", ondelete="SET NULL"), nullable=True, index=True)

    # Core event attributes
    entity_type = db.Column(db.String(50), nullable=False, index=True) # PERSON, VEHICLE, ANIMAL, OTHER
    entity_name = db.Column(db.String(100), nullable=False) # e.g. "John Doe", "Unknown Person", "car", "dog"
    recognition_status = db.Column(db.String(30), default="NOT_APPLICABLE", index=True) # KNOWN, UNKNOWN, NOT_APPLICABLE
    event_type = db.Column(db.String(50), default="DETECTION", index=True) # DETECTION, ENTRY, EXIT, SUSPICIOUS
    direction = db.Column(db.String(30), default="NONE") # ENTRY, EXIT, NONE
    confidence = db.Column(db.Float, default=0.0)
    snapshot_path = db.Column(db.String(255), nullable=True) # Relative path to snapshot
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    metadata_json = db.Column(db.Text, nullable=True)

    # Security Classification & Acknowledgment
    severity = db.Column(db.String(20), default="INFO", nullable=False, index=True) # INFO, LOW, MEDIUM, HIGH, CRITICAL
    zone_name = db.Column(db.String(100), nullable=True)
    is_acknowledged = db.Column(db.Boolean, default=False, nullable=False, index=True)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    acknowledged_by = db.Column(db.String(100), nullable=True)

    # Relationship to notifications
    notifications = db.relationship("Notification", backref="event", cascade="all, delete-orphan", lazy="dynamic")

    def to_dict(self):
        camera_name = self.camera.name if self.camera else "Camera #1"
        person_name = self.person.name if self.person else (self.entity_name if self.recognition_status == "KNOWN" else "N/A")
        
        return {
            "id": self.id,
            "camera_id": self.camera_id,
            "camera_name": camera_name,
            "person_id": self.person_id,
            "person_name": person_name,
            "entity_type": self.entity_type,
            "entity_name": self.entity_name,
            "recognition_status": self.recognition_status,
            "event_type": self.event_type,
            "direction": self.direction,
            "confidence": round(self.confidence, 2),
            "confidence_percent": f"{int(self.confidence * 100)}%",
            "snapshot_path": self.snapshot_path or "",
            "snapshot_url": f"/storage/{self.snapshot_path}" if self.snapshot_path else "",
            "severity": self.severity or "INFO",
            "zone_name": self.zone_name or "Premises Area",
            "is_acknowledged": bool(self.is_acknowledged),
            "acknowledged_at": self.acknowledged_at.strftime("%Y-%m-%d %H:%M:%S") if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
            "date": self.timestamp.strftime("%Y-%m-%d"),
            "time": self.timestamp.strftime("%H:%M:%S"),
            "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        }

    def __repr__(self):
        return f"<Event #{self.id} {self.entity_type}:{self.entity_name} ({self.recognition_status})>"
