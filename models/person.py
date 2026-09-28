from datetime import datetime
import json
import numpy as np
from . import db

class Person(db.Model):
    __tablename__ = "persons"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    person_code = db.Column(db.String(50), unique=True, nullable=True, index=True) # ID/Badge/Roll No
    email = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    status = db.Column(db.String(20), default="active", nullable=False) # 'active' or 'inactive'
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    embeddings = db.relationship("FaceEmbedding", backref="person", cascade="all, delete-orphan", lazy="dynamic")
    events = db.relationship("Event", backref="person", lazy="dynamic")

    @property
    def is_enrolled(self) -> bool:
        return self.embeddings.count() > 0

    @property
    def sample_count(self) -> int:
        return self.embeddings.count()

    def to_dict(self):
        last_event = self.events.order_by(db.desc("timestamp")).first()
        return {
            "id": self.id,
            "name": self.name,
            "person_code": self.person_code or "N/A",
            "email": self.email or "",
            "phone": self.phone or "",
            "status": self.status,
            "notes": self.notes or "",
            "is_enrolled": self.is_enrolled,
            "sample_count": self.sample_count,
            "event_count": self.events.count(),
            "last_seen": last_event.timestamp.strftime("%Y-%m-%d %H:%M:%S") if last_event else "Never",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None
        }

    def __repr__(self):
        return f"<Person {self.name} ({self.person_code})>"


class FaceEmbedding(db.Model):
    __tablename__ = "face_embeddings"

    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True)
    # Store embedding as JSON serialized list of floats for broad compatibility
    embedding_json = db.Column(db.Text, nullable=False)
    sample_image_path = db.Column(db.String(255), nullable=True)
    quality_score = db.Column(db.Float, default=1.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_vector(self, vector: np.ndarray):
        if isinstance(vector, np.ndarray):
            vector = vector.flatten().tolist()
        self.embedding_json = json.dumps(vector)

    def get_vector(self) -> np.ndarray:
        if not self.embedding_json:
            return np.array([], dtype=np.float32)
        arr = json.loads(self.embedding_json)
        return np.array(arr, dtype=np.float32)

    def to_dict(self):
        return {
            "id": self.id,
            "person_id": self.person_id,
            "sample_image_path": self.sample_image_path,
            "quality_score": round(self.quality_score, 2),
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }
