import time
import math
from collections import OrderedDict, deque
from typing import Dict, List, Tuple, Optional
import numpy as np

class TrackedObject:
    def __init__(self, object_id: int, centroid: Tuple[int, int], bbox: List[int], class_name: str, entity_type: str):
        self.object_id = object_id
        self.centroid = centroid # (cx, cy)
        self.bbox = bbox # [x1, y1, x2, y2]
        self.class_name = class_name
        self.entity_type = entity_type # PERSON, VEHICLE, ANIMAL, OTHER
        self.trajectory = deque(maxlen=30)
        self.trajectory.append(centroid)
        self.disappeared_count = 0
        self.line_crossed = False
        self.last_direction = "NONE" # "ENTRY", "EXIT", "NONE"
        self.person_name = None
        self.person_id = None
        self.recognition_status = "NOT_APPLICABLE" # KNOWN, UNKNOWN, NOT_APPLICABLE
        self.confidence = 0.0

        # Security & Dwell Telemetry
        self.first_seen_time = time.time()
        self.last_seen_time = time.time()
        self.is_unauthorized = False
        self.loitering_flagged = False
        self.repeated_flagged = False
        self.security_flags: List[str] = []

    @property
    def dwell_time(self) -> float:
        return max(0.0, time.time() - self.first_seen_time)

class TrackingService:
    def __init__(self, max_disappeared: int = 15, max_distance: float = 120.0):
        self.next_object_id = 1
        self.objects: Dict[int, TrackedObject] = OrderedDict()
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance

    def reset(self):
        self.next_object_id = 1
        self.objects.clear()

    def register(self, centroid: Tuple[int, int], bbox: List[int], class_name: str, entity_type: str) -> int:
        obj_id = self.next_object_id
        self.objects[obj_id] = TrackedObject(obj_id, centroid, bbox, class_name, entity_type)
        self.next_object_id += 1
        return obj_id

    def deregister(self, object_id: int):
        if object_id in self.objects:
            del self.objects[object_id]

    def update(self, detections: List[dict], line_pos: float = 0.5, line_orientation: str = "horizontal", frame_shape: Tuple[int, int] = (480, 640)) -> List[dict]:
        """
        Updates tracks with new detections [ {bbox, class_name, entity_type, confidence, ...} ]
        Checks for line crossings (ENTRY / EXIT).
        Returns list of updated tracks with crossing events if any.
        """
        h, w = frame_shape[:2]
        line_coord = int(h * line_pos) if line_orientation == "horizontal" else int(w * line_pos)

        # If no detections in this frame
        if len(detections) == 0:
            for obj_id in list(self.objects.keys()):
                self.objects[obj_id].disappeared_count += 1
                if self.objects[obj_id].disappeared_count > self.max_disappeared:
                    self.deregister(obj_id)
            return self._get_active_tracks()

        # Compute centroids for input detections
        input_centroids = []
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            input_centroids.append((cx, cy))

        # If currently tracking no objects, register all
        if len(self.objects) == 0:
            for i, det in enumerate(detections):
                self.register(input_centroids[i], det["bbox"], det["class_name"], det["entity_type"])
            return self._get_active_tracks()

        # Match existing tracked objects to input centroids using Euclidean distance
        object_ids = list(self.objects.keys())
        object_centroids = [self.objects[obj_id].centroid for obj_id in object_ids]

        # Distance matrix
        D = np.zeros((len(object_ids), len(input_centroids)), dtype=np.float32)
        for i, obj_pt in enumerate(object_centroids):
            for j, in_pt in enumerate(input_centroids):
                dist = math.hypot(obj_pt[0] - in_pt[0], obj_pt[1] - in_pt[1])
                D[i, j] = dist

        rows = D.min(axis=1).argsort()
        cols = D.argmin(axis=1)[rows]

        used_rows = set()
        used_cols = set()

        for (row, col) in zip(rows, cols):
            if row in used_rows or col in used_cols:
                continue

            # If distance exceeds threshold, do not associate
            if D[row, col] > self.max_distance:
                continue

            obj_id = object_ids[row]
            obj = self.objects[obj_id]
            new_centroid = input_centroids[col]
            det = detections[col]

            # Line crossing logic
            crossing_event = self._check_line_crossing(obj, new_centroid, line_coord, line_orientation)

            # Update object state
            obj.centroid = new_centroid
            obj.bbox = det["bbox"]
            obj.class_name = det["class_name"]
            obj.entity_type = det["entity_type"]
            obj.confidence = det.get("confidence", 0.0)
            obj.trajectory.append(new_centroid)
            obj.disappeared_count = 0

            if det.get("person_name"):
                obj.person_name = det["person_name"]
            if det.get("person_id"):
                obj.person_id = det["person_id"]
            if det.get("recognition_status"):
                obj.recognition_status = det["recognition_status"]

            if crossing_event != "NONE":
                obj.last_direction = crossing_event

            used_rows.add(row)
            used_cols.add(col)

        # Handle unused objects (disappeared)
        unused_rows = set(range(0, D.shape[0])).difference(used_rows)
        for row in unused_rows:
            obj_id = object_ids[row]
            self.objects[obj_id].disappeared_count += 1
            if self.objects[obj_id].disappeared_count > self.max_disappeared:
                self.deregister(obj_id)

        # Handle newly appeared objects
        unused_cols = set(range(0, D.shape[1])).difference(used_cols)
        for col in unused_cols:
            det = detections[col]
            new_id = self.register(input_centroids[col], det["bbox"], det["class_name"], det["entity_type"])
            self.objects[new_id].confidence = det.get("confidence", 0.0)
            if det.get("person_name"):
                self.objects[new_id].person_name = det["person_name"]
            if det.get("person_id"):
                self.objects[new_id].person_id = det["person_id"]
            if det.get("recognition_status"):
                self.objects[new_id].recognition_status = det["recognition_status"]

        return self._get_active_tracks()

    def _check_line_crossing(self, obj: TrackedObject, new_centroid: Tuple[int, int], line_coord: int, line_orientation: str) -> str:
        """
        Determines if object centroid crossed the virtual line between previous positions and new position.
        Returns: 'ENTRY', 'EXIT', or 'NONE'
        """
        prev_pt = obj.centroid

        if line_orientation == "horizontal":
            prev_val = prev_pt[1]
            curr_val = new_centroid[1]
            if prev_val < line_coord <= curr_val:
                return "ENTRY"
            elif prev_val > line_coord >= curr_val:
                return "EXIT"
        else:
            prev_val = prev_pt[0]
            curr_val = new_centroid[0]
            if prev_val < line_coord <= curr_val:
                return "ENTRY"
            elif prev_val > line_coord >= curr_val:
                return "EXIT"

        return "NONE"

    def _get_active_tracks(self) -> List[dict]:
        active = []
        for obj_id, obj in self.objects.items():
            if obj.disappeared_count == 0:
                active.append({
                    "object_id": obj.object_id,
                    "centroid": obj.centroid,
                    "bbox": obj.bbox,
                    "class_name": obj.class_name,
                    "entity_type": obj.entity_type,
                    "person_name": obj.person_name,
                    "person_id": obj.person_id,
                    "recognition_status": obj.recognition_status,
                    "confidence": obj.confidence,
                    "direction": obj.last_direction,
                    "trajectory": list(obj.trajectory),
                    "first_seen_time": obj.first_seen_time,
                    "dwell_time": obj.dwell_time,
                    "is_unauthorized": obj.is_unauthorized,
                    "loitering_flagged": obj.loitering_flagged,
                    "repeated_flagged": obj.repeated_flagged,
                    "security_flags": list(obj.security_flags)
                })
        return active

# Global tracker instance
tracking_service = TrackingService()
