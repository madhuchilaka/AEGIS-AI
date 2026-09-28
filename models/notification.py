from datetime import datetime
from . import db

class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id", ondelete="CASCADE"), nullable=True, index=True)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20), default="warning", nullable=False) # 'critical', 'warning', 'info', 'high', 'medium', 'low'
    category = db.Column(db.String(30), default="ALL", nullable=False, index=True) # ALL, CRITICAL, UNAUTHORIZED, SUSPICIOUS, KNOWN, SYSTEM
    read_status = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_acknowledged = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        snapshot_url = ""
        event_dict = None
        if self.event:
            if self.event.snapshot_path:
                snapshot_url = f"/storage/{self.event.snapshot_path}"
            event_dict = {
                "id": self.event.id,
                "event_type": self.event.event_type,
                "entity_name": self.event.entity_name,
                "entity_type": self.event.entity_type,
                "recognition_status": self.event.recognition_status,
                "confidence": round(self.event.confidence, 2),
                "direction": self.event.direction,
                "zone_name": self.event.zone_name or "Premises Area"
            }

        return {
            "id": self.id,
            "event_id": self.event_id,
            "title": self.title,
            "message": self.message,
            "severity": self.severity.upper() if self.severity else "WARNING",
            "category": self.category or "ALL",
            "read_status": self.read_status,
            "is_acknowledged": bool(self.is_acknowledged),
            "snapshot_url": snapshot_url,
            "camera_name": self.event.camera.name if self.event and self.event.camera else "Camera #1",
            "event": event_dict,
            "date": self.created_at.strftime("%Y-%m-%d"),
            "time": self.created_at.strftime("%H:%M:%S"),
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }

    def __repr__(self):
        return f"<Notification #{self.id} {self.title} (Read={self.read_status})>"
