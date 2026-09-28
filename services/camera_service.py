import time
import math
import threading
from datetime import datetime
from typing import Optional, Generator, Tuple, List
import cv2
import numpy as np
from config import Config
from models import Camera, SystemSetting, RestrictedZone
from services.detection_service import detection_service
from services.tracking_service import tracking_service
from services.event_service import event_service
from services.security_engine import security_engine

class CameraService:
    def __init__(self, app=None):
        self.app = app
        self.source = Config.CAMERA_SOURCE
        self.camera_id = 1
        self.camera_name = "Main Entrance"
        self.cap: Optional[cv2.VideoCapture] = None

        # Threading and control flags
        self.is_running = False
        self.is_paused = False
        self.is_connected = False
        self.use_synthetic_fallback = False
        self.last_error = ""
        self.lock = threading.Lock()
        self.worker_thread: Optional[threading.Thread] = None

        # Frame buffers
        self.latest_raw_frame: Optional[np.ndarray] = None
        self.latest_processed_frame: Optional[np.ndarray] = None
        self.active_tracks: List[dict] = []
        self.fps = 0.0

        # Processing parameters
        self.frame_skip = Config.FRAME_SKIP
        self.conf_threshold = Config.DETECTION_CONFIDENCE
        self.line_position = Config.LINE_POSITION
        self.line_orientation = Config.LINE_ORIENTATION
        self.frame_count = 0

        # Synthetic animation state (for offline/no-camera fallback)
        self.sim_tick = 0

    def init_app(self, app):
        self.app = app

    def configure_from_camera(self, camera: Camera):
        """Updates camera settings dynamically from database Camera model"""
        with self.lock:
            self.camera_id = camera.id
            self.camera_name = camera.name
            self.source = camera.source
            self.conf_threshold = camera.confidence_threshold
            self.line_position = camera.line_position
            self.line_orientation = camera.line_orientation

    def _open_capture(self) -> bool:
        """Attempts to open OpenCV VideoCapture for configured source"""
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

        # Parse source (int for webcam, string for RTSP / video file)
        src = self.source
        if isinstance(src, str) and src.isdigit():
            src = int(src)

        print(f"[CameraService] Attempting to connect to camera source: {src}...")
        try:
            # On Windows, cv2.CAP_DSHOW can make webcam initialize much faster
            if isinstance(src, int):
                cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
            else:
                cap = cv2.VideoCapture(src)

            if cap.isOpened():
                # Set resolution if available
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                ret, test_frame = cap.read()
                if ret and test_frame is not None:
                    self.cap = cap
                    self.is_connected = True
                    self.use_synthetic_fallback = False
                    self.last_error = ""
                    print(f"[CameraService] Successfully connected to camera source: {src}")
                    return True
                else:
                    cap.release()
        except Exception as e:
            self.last_error = str(e)
            print(f"[CameraService] Failed to open capture: {e}")

        # If physical camera could not be opened, use intelligent synthetic CCTV generator
        print(f"[CameraService] Camera source {src} unavailable. Activating intelligent synthetic security feed fallback.")
        self.cap = None
        self.is_connected = True
        self.use_synthetic_fallback = True
        self.last_error = "Using Synthetic Security Feed (No physical camera attached or busy)"
        return True

    def _generate_synthetic_frame(self) -> np.ndarray:
        """
        Generates a realistic simulated security camera frame with moving targets
        and premises backdrop so the entire pipeline works out of the box!
        """
        self.sim_tick += 1
        w, h = 640, 480
        frame = np.zeros((h, w, 3), dtype=np.uint8)

        # Draw premises background (parking lot / entrance floor and wall)
        # Wall (upper half)
        frame[0:int(h * 0.45), :] = (40, 44, 52)
        # Floor (lower half)
        frame[int(h * 0.45):, :] = (65, 70, 80)

        # Entrance door frame in background
        cv2.rectangle(frame, (240, 70), (400, int(h * 0.45)), (75, 80, 95), -1)
        cv2.rectangle(frame, (240, 70), (400, int(h * 0.45)), (110, 115, 130), 2)
        cv2.putText(frame, "PREMISES ENTRANCE", (255, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (160, 160, 170), 1)

        # Grid lines on floor for perspective
        for y_line in range(int(h * 0.45), h, 35):
            cv2.line(frame, (0, y_line), (w, y_line), (80, 85, 95), 1)

        # Simulated moving person target crossing the entry/exit line
        # Moves down then back up periodically
        cycle = 240
        phase = self.sim_tick % cycle
        if phase < 120:
            # Moving from top to bottom (ENTRY)
            target_y = int(140 + (phase / 120.0) * 220)
        else:
            # Moving from bottom to top (EXIT)
            target_y = int(360 - ((phase - 120) / 120.0) * 220)

        target_x = int(320 + 80 * math.sin(self.sim_tick * 0.05))

        # Draw a stylized person figure
        # Head
        cv2.circle(frame, (target_x, target_y - 45), 18, (190, 200, 210), -1)
        # Face details (eyes & mouth so YuNet / face detector can lock onto it)
        cv2.circle(frame, (target_x - 6, target_y - 47), 3, (40, 40, 40), -1)
        cv2.circle(frame, (target_x + 6, target_y - 47), 3, (40, 40, 40), -1)
        cv2.line(frame, (target_x - 5, target_y - 37), (target_x + 5, target_y - 37), (40, 40, 40), 2)
        # Body
        cv2.rectangle(frame, (target_x - 22, target_y - 25), (target_x + 22, target_y + 40), (80, 130, 210), -1)
        # Legs
        cv2.line(frame, (target_x - 12, target_y + 40), (target_x - 12, target_y + 80), (45, 50, 60), 6)
        cv2.line(frame, (target_x + 12, target_y + 40), (target_x + 12, target_y + 80), (45, 50, 60), 6)

        # Add simulated timestamp and camera overlay
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, f"CAM-01 [LIVE] {time_str}", (15, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)

        return frame

    def _worker_loop(self):
        """Main background processing thread for video capture and computer vision"""
        print("[CameraService] Background worker thread started.")
        self._open_capture()

        prev_time = time.time()
        reconnect_attempts = 0

        while self.is_running:
            # Handle pause
            if self.is_paused:
                time.sleep(0.1)
                continue

            frame = None

            if not self.use_synthetic_fallback and self.cap is not None and self.cap.isOpened():
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    print("[CameraService] Frame read failed or camera disconnected.")
                    self.is_connected = False
                    reconnect_attempts += 1
                    time.sleep(min(5.0, 0.5 * reconnect_attempts))
                    self._open_capture()
                    continue
                else:
                    reconnect_attempts = 0
            else:
                # Use synthetic stream
                frame = self._generate_synthetic_frame()
                time.sleep(0.04) # ~25 FPS

            if frame is None:
                continue

            self.frame_count += 1
            curr_time = time.time()
            dt = curr_time - prev_time
            prev_time = curr_time
            if dt > 0:
                self.fps = 0.9 * self.fps + 0.1 * (1.0 / dt)

            # Store raw frame
            with self.lock:
                self.latest_raw_frame = frame.copy()

            # Query active restricted zones for current camera
            active_zones = []
            if self.app:
                with self.app.app_context():
                    try:
                        active_zones = RestrictedZone.query.filter_by(camera_id=self.camera_id, enabled=True).all()
                    except Exception:
                        active_zones = []

            # Process frame through Computer Vision Pipeline
            # Use frame skipping to keep CPU light
            if self.frame_count % max(1, self.frame_skip) == 0:
                detections = detection_service.detect_objects(frame, conf_threshold=self.conf_threshold)
                
                # Update tracking and check line crossing
                tracks = tracking_service.update(
                    detections,
                    line_pos=self.line_position,
                    line_orientation=self.line_orientation,
                    frame_shape=frame.shape
                )

                # Evaluate security rules for each track
                if self.app:
                    with self.app.app_context():
                        for track in tracks:
                            eval_res = security_engine.evaluate_track(
                                track=track,
                                camera_id=self.camera_id,
                                zones=active_zones,
                                frame_shape=frame.shape
                            )
                            track["is_unauthorized"] = eval_res["is_unauthorized"]
                            track["is_misbehaving"] = eval_res.get("is_misbehaving", False)

                            direction = track.get("direction", "NONE")
                            entity_type = track["entity_type"]
                            rec_status = track.get("recognition_status", "NOT_APPLICABLE")
                            entity_name = track.get("person_name") or track["class_name"]
                            obj_conf = track.get("confidence", 0.0)

                            # Record event if alert, misbehavior, forced snapshot, or boundary crossing
                            should_record = eval_res["should_alert"] or eval_res.get("force_snapshot", False) or direction in ["ENTRY", "EXIT"]
                            if should_record:
                                event_service.record_detection_event(
                                    frame=frame,
                                    camera_id=self.camera_id,
                                    entity_type=entity_type,
                                    entity_name=entity_name,
                                    recognition_status=rec_status,
                                    person_id=track.get("person_id"),
                                    event_type=eval_res["event_type"],
                                    direction=direction,
                                    confidence=obj_conf,
                                    severity=eval_res["severity"],
                                    zone_name=eval_res.get("zone_name"),
                                    camera_name=self.camera_name,
                                    metadata={"reason": eval_res.get("reason"), "dwell_time": track.get("dwell_time", 0)},
                                    is_misbehaving=eval_res.get("is_misbehaving", False),
                                    force_snapshot=eval_res.get("force_snapshot", False)
                                )
                self.active_tracks = tracks

            # Render HUD overlays with active restricted zones
            annotated_frame = detection_service.draw_overlays(
                frame=frame,
                tracks=self.active_tracks,
                zones=active_zones,
                line_pos=self.line_position,
                line_orientation=self.line_orientation,
                fps=self.fps,
                camera_name=self.camera_name
            )

            with self.lock:
                self.latest_processed_frame = annotated_frame

        # Cleanup on exit
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        print("[CameraService] Background worker thread stopped.")

    def start_monitoring(self):
        """Starts background camera processing thread"""
        with self.lock:
            if self.is_running:
                self.is_paused = False
                return
            self.is_running = True
            self.is_paused = False
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
            print("[CameraService] Monitoring started.")

    def stop_monitoring(self):
        """Stops background camera processing thread"""
        with self.lock:
            self.is_running = False
            self.is_paused = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)
        print("[CameraService] Monitoring stopped.")

    def pause_monitoring(self):
        with self.lock:
            self.is_paused = True
            print("[CameraService] Monitoring paused.")

    def resume_monitoring(self):
        with self.lock:
            self.is_paused = False
            print("[CameraService] Monitoring resumed.")

    def get_latest_frame(self, processed: bool = True) -> Optional[np.ndarray]:
        with self.lock:
            if processed and self.latest_processed_frame is not None:
                return self.latest_processed_frame.copy()
            if self.latest_raw_frame is not None:
                return self.latest_raw_frame.copy()
        return None

    def get_status(self) -> dict:
        with self.lock:
            return {
                "camera_id": self.camera_id,
                "camera_name": self.camera_name,
                "running": self.is_running,
                "paused": self.is_paused,
                "online": self.is_connected,
                "source": str(self.source),
                "fps": round(self.fps, 1),
                "resolution": "1920 x 1080" if not self.use_synthetic_fallback else "640 x 480",
                "detection": "ACTIVE" if (self.is_running and not self.is_paused) else "STANDBY",
                "synthetic": self.use_synthetic_fallback,
                "active_tracks_count": len(self.active_tracks),
                "last_error": self.last_error
            }

    def generate_mjpeg_stream(self, camera_id: Optional[int] = None) -> Generator[bytes, None, None]:
        """
        Yields MJPEG multipart stream for <img> tag live streaming in browsers.
        Supports specific camera_id for multi-camera grids.
        """
        while True:
            # If camera_id requested matches active camera, stream live
            if camera_id is None or camera_id == self.camera_id:
                frame = self.get_latest_frame(processed=True)
            else:
                # Generate secondary camera simulated view
                frame = self._generate_synthetic_camera_view(camera_id)

            if frame is None:
                # Blank placeholder frame
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame, "CONNECTING TO CAMERA...", (160, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)

            ret, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not ret:
                time.sleep(0.05)
                continue

            frame_bytes = buffer.tobytes()
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
            time.sleep(0.04) # ~25 FPS stream rate

    def _generate_synthetic_camera_view(self, camera_id: int) -> np.ndarray:
        """Generates secondary view for camera grid when secondary camera not active"""
        w, h = 640, 480
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[0:int(h * 0.5), :] = (35, 38, 45)
        frame[int(h * 0.5):, :] = (55, 60, 70)
        cam_name = f"CAMERA #{camera_id}"
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, f"[GRID VIEW] {cam_name} | {time_str}", (20, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 180), 1, cv2.LINE_AA)
        cv2.putText(frame, "AUXILIARY STANDBY FEED", (200, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (140, 145, 160), 1, cv2.LINE_AA)
        return frame

# Global camera service singleton
camera_service = CameraService()
