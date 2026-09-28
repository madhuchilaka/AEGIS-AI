from datetime import datetime
from . import db

class Camera(db.Model):
    __tablename__ = "cameras"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    source = db.Column(db.String(255), nullable=False, default="0") # '0', '1', RTSP url, or video file path
    source_type = db.Column(db.String(20), nullable=False, default="webcam") # 'webcam', 'rtsp', 'video'
    resolution = db.Column(db.String(20), default="640x480")
    fps = db.Column(db.Integer, default=25)
    confidence_threshold = db.Column(db.Float, default=0.45)
    face_threshold = db.Column(db.Float, default=0.40)
    line_orientation = db.Column(db.String(20), default="horizontal") # 'horizontal' or 'vertical'
    line_position = db.Column(db.Float, default=0.50) # 0.0 to 1.0 (50% is center)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    events = db.relationship("Event", backref="camera", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "source_type": self.source_type,
            "resolution": self.resolution,
            "fps": self.fps,
            "confidence_threshold": self.confidence_threshold,
            "face_threshold": self.face_threshold,
            "line_orientation": self.line_orientation,
            "line_position": self.line_position,
            "enabled": self.enabled,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }

    def __repr__(self):
        return f"<Camera {self.name} ({self.source})>"
