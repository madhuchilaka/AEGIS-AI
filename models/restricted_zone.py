import json
from datetime import datetime
from . import db

class RestrictedZone(db.Model):
    __tablename__ = "restricted_zones"

    id = db.Column(db.Integer, primary_key=True)
    camera_id = db.Column(db.Integer, db.ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    boundary_type = db.Column(db.String(20), default="rectangle", nullable=False) # 'rectangle' or 'polygon'
    # Stored as normalized coordinates (0.0 to 1.0)
    # Rectangle format: {"x1": 0.1, "y1": 0.2, "x2": 0.6, "y2": 0.8}
    # Polygon format: [{"x": 0.1, "y": 0.2}, ...]
    coordinates_json = db.Column(db.Text, nullable=False, default="{}")
    allowed_hours_start = db.Column(db.String(10), default="08:00", nullable=False) # "08:00"
    allowed_hours_end = db.Column(db.String(10), default="20:00", nullable=False)   # "20:00"
    authorized_person_ids_json = db.Column(db.Text, default="[]", nullable=False)   # "[1, 2]"
    alert_level = db.Column(db.String(20), default="HIGH", nullable=False) # 'CRITICAL', 'HIGH', 'MEDIUM'
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationship
    camera = db.relationship("Camera", backref=db.backref("restricted_zones", cascade="all, delete-orphan", lazy="dynamic"))

    def get_coordinates(self):
        try:
            return json.loads(self.coordinates_json) if self.coordinates_json else {}
        except Exception:
            return {}

    def set_coordinates(self, coords):
        self.coordinates_json = json.dumps(coords)

    def get_authorized_persons(self):
        try:
            return json.loads(self.authorized_person_ids_json) if self.authorized_person_ids_json else []
        except Exception:
            return []

    def set_authorized_persons(self, person_ids):
        self.authorized_person_ids_json = json.dumps(person_ids)

    def is_time_allowed(self, check_dt=None) -> bool:
        """Returns True if current time is within allowed hours"""
        if check_dt is None:
            check_dt = datetime.now()
        cur_time_str = check_dt.strftime("%H:%M")
        start = self.allowed_hours_start
        end = self.allowed_hours_end

        if start <= end:
            return start <= cur_time_str <= end
        else: # Spans midnight (e.g. 20:00 to 06:00)
            return cur_time_str >= start or cur_time_str <= end

    def contains_point(self, norm_x: float, norm_y: float) -> bool:
        """Checks if a normalized point (0.0-1.0) falls inside this zone"""
        coords = self.get_coordinates()
        if not coords:
            return False

        if self.boundary_type == "rectangle":
            x1 = coords.get("x1", 0.0)
            y1 = coords.get("y1", 0.0)
            x2 = coords.get("x2", 1.0)
            y2 = coords.get("y2", 1.0)
            min_x, max_x = min(x1, x2), max(x1, x2)
            min_y, max_y = min(y1, y2), max(y1, y2)
            return min_x <= norm_x <= max_x and min_y <= norm_y <= max_y
        elif self.boundary_type == "polygon":
            points = coords if isinstance(coords, list) else coords.get("points", [])
            if len(points) < 3:
                return False
            # Ray casting algorithm
            inside = False
            j = len(points) - 1
            for i in range(len(points)):
                xi, yi = points[i]["x"], points[i]["y"]
                xj, yj = points[j]["x"], points[j]["y"]
                intersect = ((yi > norm_y) != (yj > norm_y)) and (norm_x < (xj - xi) * (norm_y - yi) / (yj - yi + 1e-9) + xi)
                if intersect:
                    inside = not inside
                j = i
            return inside
        return False

    def to_dict(self):
        return {
            "id": self.id,
            "camera_id": self.camera_id,
            "camera_name": self.camera.name if self.camera else f"Camera #{self.camera_id}",
            "name": self.name,
            "boundary_type": self.boundary_type,
            "coordinates": self.get_coordinates(),
            "allowed_hours_start": self.allowed_hours_start,
            "allowed_hours_end": self.allowed_hours_end,
            "authorized_person_ids": self.get_authorized_persons(),
            "alert_level": self.alert_level,
            "enabled": self.enabled,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }

    def __repr__(self):
        return f"<RestrictedZone #{self.id} {self.name} (Cam {self.camera_id})>"
