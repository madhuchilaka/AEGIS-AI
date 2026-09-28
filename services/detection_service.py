import os
import threading
from typing import List, Dict, Tuple, Optional
import cv2
import numpy as np
from pathlib import Path
from config import Config
from services.face_recognition_service import face_recognition_service

# Safe YOLO import
try:
    from ultralytics import YOLO
except Exception as e:
    YOLO = None

class DetectionService:
    # Mappings from COCO classes to our high-level premise security categories
    PERSON_CLASSES = {"person"}
    VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck", "bicycle", "airplane", "boat", "train"}
    ANIMAL_CLASSES = {"dog", "cat", "bird", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"}

    COCO_CLASSES = [
        "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
        "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
        "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
        "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
        "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
        "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
        "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
        "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
        "hair drier", "toothbrush"
    ]

    def __init__(self, model_name: str = "yolov8n.pt"):
        self.model_name = model_name
        self.model = None
        self.nanodet_net = None
        self.lock = threading.Lock()
        self.is_loaded = False
        self.backend_engine = "NONE"
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=25, detectShadows=False)
        self._load_model()

    def _load_model(self):
        """Loads best available computer vision model (YOLO, NanoDet ONNX, or YuNet)"""
        with self.lock:
            # 1. Attempt YOLO if ultralytics imported successfully
            if YOLO is not None:
                try:
                    models_dir = Path(Config.MODELS_DIR)
                    local_path = models_dir / self.model_name
                    target = str(local_path) if local_path.exists() else self.model_name
                    print(f"[DetectionService] Attempting to load YOLO from {target}...")
                    self.model = YOLO(target)
                    self.is_loaded = True
                    self.backend_engine = "YOLO"
                    print("[DetectionService] YOLO model loaded successfully.")
                    return
                except Exception as e:
                    print(f"[DetectionService] YOLO load failed ({e}), falling back to ONNX...")

            # 2. Attempt NanoDet ONNX (native OpenCV DNN, no torch needed)
            nanodet_path = Path(Config.MODELS_DIR) / "object_detection_nanodet_2022nov.onnx"
            if nanodet_path.exists():
                try:
                    self.nanodet_net = cv2.dnn.readNetFromONNX(str(nanodet_path))
                    self.is_loaded = True
                    self.backend_engine = "NANODET_ONNX"
                    print("[DetectionService] NanoDet ONNX loaded successfully via OpenCV DNN.")
                    return
                except Exception as e:
                    print(f"[DetectionService] NanoDet ONNX load failed: {e}")

            # 3. Native OpenCV YuNet Face & Contour Object Engine
            self.is_loaded = True
            self.backend_engine = "YUNET_CONTOUR_CV"
            print("[DetectionService] Using OpenCV YuNet & Adaptive Contour CV Engine.")

    def categorize_class(self, class_name: str) -> str:
        name_lower = class_name.lower()
        if name_lower in self.PERSON_CLASSES:
            return "PERSON"
        elif name_lower in self.VEHICLE_CLASSES:
            return "VEHICLE"
        elif name_lower in self.ANIMAL_CLASSES:
            return "ANIMAL"
        return "OTHER"

    def detect_objects(self, frame: np.ndarray, conf_threshold: float = 0.45) -> List[dict]:
        """
        Runs object detection and facial identification on the frame.
        Returns a list of structured detections.
        """
        if frame is None or frame.size == 0:
            return []

        h, w = frame.shape[:2]
        detections = []

        # 1. If YOLO is active
        if self.backend_engine == "YOLO" and self.model is not None:
            with self.lock:
                try:
                    results = self.model.predict(source=frame, conf=conf_threshold, verbose=False, imgsz=640)
                    if results and len(results) > 0 and results[0].boxes:
                        for box in results[0].boxes:
                            cls_id = int(box.cls[0].item())
                            class_name = self.model.names.get(cls_id, f"class_{cls_id}")
                            conf = float(box.conf[0].item())
                            coords = box.xyxy[0].tolist()
                            x1, y1, x2, y2 = [int(v) for v in coords]
                            x1, y1 = max(0, min(w - 1, x1)), max(0, min(h - 1, y1))
                            x2, y2 = max(x1 + 1, min(w, x2)), max(y1 + 1, min(h, y2))

                            entity_type = self.categorize_class(class_name)
                            det_info = {
                                "bbox": [x1, y1, x2, y2],
                                "class_name": class_name,
                                "entity_type": entity_type,
                                "confidence": conf,
                                "recognition_status": "NOT_APPLICABLE",
                                "person_name": None,
                                "person_id": None
                            }

                            if entity_type == "PERSON":
                                self._enrich_person_recognition(frame, det_info, x1, y1, x2, y2)

                            detections.append(det_info)
                        return detections
                except Exception as e:
                    print(f"[DetectionService] YOLO predict error: {e}")

        # 2. Native YuNet & Adaptive Contour Computer Vision Detection
        # Detect faces with YuNet
        faces = face_recognition_service.detect_faces(frame, score_threshold=0.35)
        for face in faces:
            fx, fy, fw, fh = face[:4].astype(int)
            # Extrapolate full person bounding box from face position
            px1 = max(0, int(fx - fw * 0.4))
            py1 = max(0, int(fy - fh * 0.2))
            px2 = min(w, int(fx + fw * 1.4))
            py2 = min(h, int(fy + fh * 3.8))

            det_info = {
                "bbox": [px1, py1, px2, py2],
                "class_name": "person",
                "entity_type": "PERSON",
                "confidence": float(face[-1]),
                "recognition_status": "UNKNOWN",
                "person_name": "Unknown Person",
                "person_id": None
            }

            # Run SFace recognition
            pid, pname, score, status = face_recognition_service.recognize_face(frame, face)
            det_info["recognition_status"] = status
            det_info["person_name"] = pname
            det_info["person_id"] = pid
            det_info["face_score"] = score
            detections.append(det_info)

        # Detect moving objects via background subtraction
        fg_mask = self.bg_subtractor.apply(frame)
        _, thresh = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_DILATE, kernel, iterations=2)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 2500: # Ignore tiny noise
                continue
            cx, cy, cw, ch = cv2.boundingRect(cnt)

            # Check if this contour overlaps with any already detected person face
            overlaps = False
            for d in detections:
                dx1, dy1, dx2, dy2 = d["bbox"]
                if not (cx + cw < dx1 or cx > dx2 or cy + ch < dy1 or cy > dy2):
                    overlaps = True
                    break

            if not overlaps:
                aspect = cw / float(ch + 1e-5)
                # Classify based on geometry
                if aspect > 1.3 and area > 6000:
                    ent_type = "VEHICLE"
                    cls_name = "vehicle"
                elif 0.3 <= aspect <= 1.2 and ch > 70:
                    ent_type = "PERSON"
                    cls_name = "person"
                elif aspect > 0.8 and area < 8000:
                    ent_type = "ANIMAL"
                    cls_name = "animal"
                else:
                    ent_type = "OTHER"
                    cls_name = "object"

                det_info = {
                    "bbox": [cx, cy, cx + cw, cy + ch],
                    "class_name": cls_name,
                    "entity_type": ent_type,
                    "confidence": min(0.95, round(0.65 + (area / 50000.0) * 0.25, 2)),
                    "recognition_status": "UNKNOWN" if ent_type == "PERSON" else "NOT_APPLICABLE",
                    "person_name": "Unknown Person" if ent_type == "PERSON" else None,
                    "person_id": None
                }
                detections.append(det_info)

        return detections

    def _enrich_person_recognition(self, frame: np.ndarray, det_info: dict, x1: int, y1: int, x2: int, y2: int):
        det_info["recognition_status"] = "UNKNOWN"
        det_info["person_name"] = "Unknown Person"
        crop = frame[y1:y2, x1:x2]
        if crop.size > 0:
            faces = face_recognition_service.detect_faces(crop, score_threshold=0.4)
            if faces:
                pid, pname, score, status = face_recognition_service.recognize_face(crop, faces[0])
                det_info["recognition_status"] = status
                det_info["person_name"] = pname
                det_info["person_id"] = pid
                det_info["face_score"] = score

    def draw_overlays(
        self,
        frame: np.ndarray,
        tracks: List[dict],
        zones: Optional[List] = None,
        line_pos: float = 0.50,
        line_orientation: str = "horizontal",
        fps: float = 0.0,
        camera_name: str = "Camera #1"
    ) -> np.ndarray:
        """
        Renders Security Operations Center HUD overlay:
        - Semi-transparent top telemetry banner with live status
        - Virtual boundary lines with directional arrows
        - Active restricted zones with translucent wash and labels
        - Color-coded bounding boxes, corner brackets, and centroid tracks
        - Classification and authorization labels
        """
        if frame is None:
            return frame

        overlay = frame.copy()
        h, w = frame.shape[:2]

        # 1. Draw Restricted Zones
        if zones:
            for zone in zones:
                if not getattr(zone, "enabled", True):
                    continue
                z_name = getattr(zone, "name", "Restricted Area")
                z_level = getattr(zone, "alert_level", "HIGH").upper()
                coords = zone.get_coordinates() if hasattr(zone, "get_coordinates") else {}
                if not coords:
                    continue

                zx1 = int(coords.get("x1", 0.0) * w)
                zy1 = int(coords.get("y1", 0.0) * h)
                zx2 = int(coords.get("x2", 1.0) * w)
                zy2 = int(coords.get("y2", 1.0) * h)

                # Translucent fill
                zone_color = (0, 0, 220) if z_level == "CRITICAL" else (0, 140, 255) # BGR: Red or Amber
                sub = overlay.copy()
                cv2.rectangle(sub, (zx1, zy1), (zx2, zy2), zone_color, -1)
                cv2.addWeighted(sub, 0.15, overlay, 0.85, 0, overlay)

                # Dashed border
                cv2.rectangle(overlay, (zx1, zy1), (zx2, zy2), zone_color, 2, cv2.LINE_AA)
                # Zone label badge
                cv2.putText(overlay, f"ZONE: {z_name.upper()} [{z_level}]", (zx1 + 8, zy1 + 18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)

        # 2. Draw Virtual Entry/Exit Line
        line_color = (0, 225, 255) # Cyber Cyan / Yellow (BGR)
        if line_orientation == "horizontal":
            line_y = int(h * line_pos)
            cv2.line(overlay, (0, line_y), (w, line_y), line_color, 2, cv2.LINE_AA)
            cv2.putText(overlay, "▲ EXIT | ENTRY ▼", (15, line_y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, line_color, 1, cv2.LINE_AA)
        else:
            line_x = int(w * line_pos)
            cv2.line(overlay, (line_x, 0), (line_x, h), line_color, 2, cv2.LINE_AA)
            cv2.putText(overlay, "◄ EXIT | ENTRY ►", (line_x + 8, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, line_color, 1, cv2.LINE_AA)

        # 3. Draw Object Tracks & Bounding Boxes
        for track in tracks:
            bbox = track.get("bbox", [0, 0, 10, 10])
            x1, y1, x2, y2 = bbox
            entity_type = track.get("entity_type", "OTHER")
            rec_status = track.get("recognition_status", "NOT_APPLICABLE")
            person_name = track.get("person_name")
            obj_id = track.get("object_id", "?")
            confidence = track.get("confidence", 0.0)
            direction = track.get("direction", "NONE")
            is_unauth = track.get("is_unauthorized", False)
            dwell = int(track.get("dwell_time", 0))

            # Determine color scheme (BGR)
            if entity_type == "PERSON":
                if rec_status == "KNOWN":
                    box_color = (16, 185, 129) # Emerald Green
                    label_text = f"👤 {person_name} (KNOWN)"
                elif track.get("is_misbehaving", False):
                    box_color = (30, 30, 245) # Intense Alert Red
                    label_text = f"🚨 MISBEHAVING UNKNOWN #{obj_id}"
                elif is_unauth:
                    box_color = (50, 50, 240) # Bright Crimson Red
                    label_text = f"🚨 UNAUTHORIZED PERSON #{obj_id}"
                else:
                    box_color = (0, 140, 255) # Amber Orange (Unknown visitor)
                    label_text = f"👤 UNKNOWN PERSON #{obj_id}"
            elif entity_type == "VEHICLE":
                box_color = (255, 180, 50) # Blue
                label_text = f"🚗 VEHICLE: {track.get('class_name', 'car').upper()} #{obj_id}"
            elif entity_type == "ANIMAL":
                box_color = (50, 200, 255) # Gold
                label_text = f"🐾 ANIMAL: {track.get('class_name', 'fauna').upper()} #{obj_id}"
            else:
                box_color = (220, 100, 200) # Purple
                label_text = f"OBJECT #{obj_id}"

            if direction != "NONE":
                label_text += f" [{direction}]"
            if dwell > 5:
                label_text += f" {dwell}s"

            # Draw bounding box
            cv2.rectangle(overlay, (x1, y1), (x2, y2), box_color, 2, cv2.LINE_AA)

            # High-tech corner accents
            corner_len = min(16, int((x2 - x1) / 4), int((y2 - y1) / 4))
            thick = 3
            cv2.line(overlay, (x1, y1), (x1 + corner_len, y1), box_color, thick)
            cv2.line(overlay, (x1, y1), (x1, y1 + corner_len), box_color, thick)
            cv2.line(overlay, (x2, y1), (x2 - corner_len, y1), box_color, thick)
            cv2.line(overlay, (x2, y1), (x2, y1 + corner_len), box_color, thick)
            cv2.line(overlay, (x1, y2), (x1 + corner_len, y2), box_color, thick)
            cv2.line(overlay, (x1, y2), (x1, y2 - corner_len), box_color, thick)
            cv2.line(overlay, (x2, y2), (x2 - corner_len, y2), box_color, thick)
            cv2.line(overlay, (x2, y2), (x2, y2 - corner_len), box_color, thick)

            # Draw Centroid and Trajectory
            centroid = track.get("centroid")
            if centroid:
                cv2.circle(overlay, centroid, 4, box_color, -1)

            trajectory = track.get("trajectory", [])
            if len(trajectory) > 1:
                for i in range(1, len(trajectory)):
                    cv2.line(overlay, trajectory[i - 1], trajectory[i], box_color, 1, cv2.LINE_AA)

            # Label banner
            label_display = f"{label_text} ({int(confidence * 100)}%)"
            font_scale = 0.42
            (txt_w, txt_h), _ = cv2.getTextSize(label_display, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
            banner_y1 = max(0, y1 - txt_h - 10)
            banner_y2 = y1
            cv2.rectangle(overlay, (x1, banner_y1), (x1 + txt_w + 12, banner_y2), box_color, -1)
            cv2.putText(overlay, label_display, (x1 + 6, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1, cv2.LINE_AA)

        # 4. HUD Top Header Bar (Semi-transparent dark glass)
        header_h = 32
        hud = overlay.copy()
        cv2.rectangle(hud, (0, 0), (w, header_h), (12, 16, 24), -1)
        cv2.addWeighted(hud, 0.8, overlay, 0.2, 0, overlay)

        fps_text = f"FPS: {fps:.1f}" if fps > 0 else "FPS: --"
        cv2.putText(overlay, f"AI PREMISES MONITOR | {camera_name.upper()} | {fps_text} | ACTIVE TARGETS: {len(tracks)}", (15, 21),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 255, 180), 1, cv2.LINE_AA)

        # Blinking live green dot
        cv2.circle(overlay, (w - 20, 16), 5, (0, 255, 0), -1)
        cv2.circle(overlay, (w - 20, 16), 8, (0, 255, 0), 1, cv2.LINE_AA)

        return overlay

# Global detection service instance
detection_service = DetectionService()
